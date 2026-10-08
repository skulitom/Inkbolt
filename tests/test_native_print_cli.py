"""Independent PDF structure, ink transport and physical mark measurements."""
import base64
import copy
import hashlib
import itertools
import json
import math
from pathlib import Path
import tempfile
import unittest
import pdf_reader
import test_editing_cli as editing
from cmyk_fixtures import cmyk_profile, separation
from test_profiles_cli import embedded, decode_srgb
from test_proof_cli import scalar, xyz
from test_vector_plates_cli import rect, named, color, spot
from test_ink_recipes_cli import calculator
from test_mcp import Client


def page_image(pdf, index=0):
    ref=pdf.pages[index]['Resources']['XObject']['Im']
    return pdf.get(ref),pdf.streams[ref]


def strokes(pdf,index=0):
    """Read actual page operators; return stroked paths in physical points."""
    page=pdf.pages[index];unit=page['UserUnit'];matrix=[1,0,0,1,0,0];stack=[]
    args=[];path=[];paths=[];width=None;color=None;result=[]
    for token in pdf.streams[page['Contents']].split():
        if token.startswith(b'/'):args.append(token[1:].decode());continue
        try:args.append(float(token));continue
        except ValueError:pass
        if token==b'q':stack.append(matrix[:])
        elif token==b'Q':matrix=stack.pop()
        elif token==b'cm':matrix=pdf_reader.multiply(matrix,args)
        elif token==b'CS':color=pdf.get(page['Resources']['ColorSpace'][args[0]])
        elif token==b'w':width=args[0]*unit
        elif token==b'm':
            if path:paths.append(path)
            path=[('m',[v*unit for v in pdf_reader.point(matrix,args)])]
        elif token in (b'l',b'c'):
            path.append((token.decode(),[v*unit for at in range(0,len(args),2) for v in pdf_reader.point(matrix,args[at:at+2])]))
        elif token==b'h':path.append(('h',[]))
        elif token==b'S':
            if path:paths.append(path)
            result.append(dict(width=width,color=color,paths=paths));path=[];paths=[]
        else:assert token in (b'ri',b'Do',b'SCN',b'J',b'j'),token
        args=[]
    assert not stack and not args and not path and not paths
    return result


class NativePrintTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke

    def document(self,n=2,width=32,height=24,ppi=96):
        d=self.invoke(dict(command='document.create',id='native-print',kind='vector',width=width,height=height,resolution_ppi=ppi))
        d['swatches']=dict(process=color([.75,.5,.25,.125]),front=color([0,.25,0,.5]))
        d['swatches'].update({f's{i}':spot('Same label') for i in range(n)})
        d['items']=[rect('base',named('process'),box=(0,0,width,height)),
                    dict(id='group',opacity=.75,content=dict(type='group',isolated=False)),
                    rect('front',named('front',opacity=.25,overprint='preserve_nonzero'),box=(2,2,width-4,height-4),parent='group')]
        d['items'].extend(rect(f'ink{i}',named(f's{i}',tint=(i+1)/(n+1),opacity=.5,overprint='preserve'),box=(i%4,0,width-4,height),parent='group') for i in range(n))
        return d

    def settings(self,**kw):
        return dict(profile=embedded(cmyk_profile()),antialias='none',spot_fallback='multiplicative_declared',**kw)

    def export(self,d,settings=None,expected=0,**pdf_options):
        return self.invoke(dict(command='document.export',document=d,format='pdf',pdf_options=dict(prepress=settings or self.settings(),**pdf_options)),expected)

    def plate_bytes(self,d,settings=None,**scope):
        options={k:v for k,v in (settings or self.settings()).items() if k not in ('marks','spot_fallback')}
        r=self.invoke(dict(command='document.prepress',document=d,options=dict(options,**scope)))
        return r,bytes(v for pixel in zip(*(scalar(p)[2] for p in r['plates'])) for v in pixel)

    def test_flattened_image_carries_every_exact_native_plane_without_transparency(self):
        for n,scale in [(0,1),(1,2),(2,4),(8,1),(28,1)]:
            d=self.document(n);original=copy.deepcopy(d);settings=self.settings(raster_scale=scale)
            artifact=self.export(d,settings);pdf=pdf_reader.Pdf(artifact);image,data=page_image(pdf)
            planes,expected=self.plate_bytes(d,settings)
            self.assertEqual(data,expected)
            self.assertEqual((image['Width'],image['Height'],image['BitsPerComponent']),(32*scale,24*scale,8))
            self.assertNotIn('SMask',image);self.assertNotIn('ExtGState',pdf.pages[0]['Resources']);self.assertNotIn('Group',pdf.pages[0])
            space=pdf.get(image['ColorSpace']);ids=sorted(f's{i}' for i in range(n))
            self.assertEqual(space[:2],['DeviceN',['Cyan','Magenta','Yellow','Black']+['Inkbolt.'+i for i in ids]])
            self.assertEqual(space[4]['Subtype'],'NChannel');self.assertEqual(space[4]['Process']['Components'],space[1][:4])
            self.assertEqual(pdf.streams[space[2][1]],cmyk_profile())
            self.assertEqual(artifact['pages'][0]['inks']['interleaved_sha256'],planes['interleaved_sha256'])
            self.assertEqual(artifact['pdf']['color_delivery'],'native_flattened_prepress')
            self.assertEqual(strokes(pdf),[])
            self.assertEqual(self.export(d,settings),artifact);self.assertEqual(d,original)

    def test_masks_clips_and_supersampling_use_the_shared_native_flattening(self):
        d=self.document();g=d['items'][1]
        g['content']['isolated']=True
        g['mask']=dict(width=32,height=24,gray_hex=bytes((i*37+19)%256 for i in range(32*24)).hex())
        g['clip']=dict(geometry=dict(shape='ellipse',cx=16,cy=12,rx=13,ry=10))
        for aa in ['coverage','supersample2','supersample4']:
            settings=self.settings();settings['antialias']=aa
            _,expected=self.plate_bytes(d,settings)
            pdf=pdf_reader.Pdf(self.export(d,settings));self.assertEqual(page_image(pdf)[1],expected)

    def test_declared_spot_alternates_and_calculator_have_independent_color_equations(self):
        d=self.document(4)
        declarations=[dict(space='cmyk',components=[.1,.2,.3,.4]),dict(space='srgb',components=[.2,.4,.7]),dict(space='gray',component=.4),dict(space='lab',components=[55,15,-20])]
        for i,p in enumerate(declarations):d['swatches'][f's{i}']['definition']['alternate']=p
        a=self.export(d);pdf=pdf_reader.Pdf(a);image,data=page_image(pdf);space=pdf.get(image['ColorSpace'])
        alts=a['pages'][0]['spot_fallback']['alternate_cmyk'];matrix=[[.4360747,.3850649,.1430804],[.2225045,.7168786,.0606169],[.0139322,.0971045,.7141733]]
        self.assertEqual(alts['s0'],[.1,.2,.3,.4])
        for i,values in [(1,[.2,.4,.7]),(2,[.4]*3),(3,[55,15,-20])]:
            pcs=xyz(values) if i==3 else [sum(row[c]*decode_srgb(values[c]) for c in range(3)) for row in matrix]
            expected=separation([v*32768/65535 for v in pcs])
            for x,y in zip(alts[f's{i}'],expected):self.assertAlmostEqual(x,y,delta=.00008)
        program=pdf.streams[space[3]]
        for at in [0,8*77,8*350]:
            q=[v/255 for v in data[at:at+8]]
            expected=[1-(1-q[c])*math.prod(1-q[4+i]*alts[f's{i}'][c] for i in range(4)) for c in range(4)]
            for x,y in zip(calculator(program,q,4,48),expected):self.assertAlmostEqual(x,y,places=13)

    def test_crop_registration_geometry_and_boxes_are_physical_and_outside_bleed(self):
        for ppi,scale in itertools.product([72,96,300],[1,2]):
            d=self.document(width=128,height=96,ppi=ppi)
            d['items'].insert(0,dict(id='board',content=dict(type='frame',frame=dict(role='artboard',width=128,height=96,bleed=dict(left=4,right=8,top=3,bottom=5)))))
            for item in d['items'][1:]:
                if 'parent' not in item:item['parent']='board'
            settings=self.settings(raster_scale=scale,marks={})
            a=self.export(d,settings,artboards=dict(type='ids',ids=['board']),include_bleed=True);pdf=pdf_reader.Pdf(a);page=pdf.pages[0];receipt=a['pages'][0]
            margin=12.25;factor=72/ppi;w=140*factor;h=104*factor
            media=[0,0,w+2*margin,h+2*margin];bounds=[margin,margin,margin+w,margin+h]
            trim=[margin+4*factor,margin+5*factor,margin+132*factor,margin+101*factor]
            for key,expected in [('MediaBox',media),('CropBox',media),('BleedBox',bounds),('TrimBox',trim)]:
                for x,y in zip(page[key],expected):self.assertAlmostEqual(x*page['UserUnit'],y,places=11)
            self.assertEqual((page_image(pdf)[0]['Width'],page_image(pdf)[0]['Height']),(140*scale,104*scale))
            result=strokes(pdf);self.assertEqual(len(result),1);s=result[0]
            self.assertEqual(s['color'][:3],['Separation','All','DeviceCMYK']);self.assertEqual(s['width'],.25)
            paths=s['paths'];self.assertEqual(len(paths),20)
            crop=paths[:8]
            for path in crop:
                self.assertEqual([v[0] for v in path],['m','l']);p,q=path[0][1],path[1][1]
                self.assertAlmostEqual(math.dist(p,q),6,places=11)
                self.assertTrue((p[0]==q[0] and any(abs(p[0]-v)<1e-10 for v in [trim[0],trim[2]])) or (p[1]==q[1] and any(abs(p[1]-v)<1e-10 for v in [trim[1],trim[3]])))
                self.assertTrue(max(p[0],q[0])<=bounds[0]-3 or min(p[0],q[0])>=bounds[2]+3 or max(p[1],q[1])<=bounds[1]-3 or min(p[1],q[1])>=bounds[3]+3)
            expected_centers=[[bounds[0]-7.625,(trim[1]+trim[3])/2],[bounds[2]+7.625,(trim[1]+trim[3])/2],[(trim[0]+trim[2])/2,bounds[1]-7.625],[(trim[0]+trim[2])/2,bounds[3]+7.625]]
            for j,center in enumerate(expected_centers):
                circle,horizontal,vertical=paths[8+3*j:11+3*j]
                self.assertEqual([op for op,_ in circle],['m','c','c','c','c','h'])
                self.assertAlmostEqual(math.dist(horizontal[0][1],horizontal[1][1]),9,places=11)
                self.assertAlmostEqual(math.dist(vertical[0][1],vertical[1][1]),9,places=11)
                for axis in range(2):self.assertAlmostEqual((horizontal[0][1][axis]+horizontal[1][1][axis])/2,center[axis],places=11)
                start=circle[0][1]
                for op,curve in circle[1:-1]:
                    for t in [i/40 for i in range(41)]:
                        point=[(1-t)**3*start[c]+3*(1-t)**2*t*curve[c]+3*(1-t)*t*t*curve[2+c]+t**3*curve[4+c] for c in range(2)]
                        self.assertAlmostEqual(math.dist(point,center),3,delta=.00083)
                        self.assertTrue(0<=point[0]<=media[2] and 0<=point[1]<=media[3])
                    start=curve[4:]
            self.assertEqual(receipt['marks']['margin_pt'],margin)
            _,expected=self.plate_bytes(d,settings,artboard_id='board',include_bleed=True);self.assertEqual(page_image(pdf)[1],expected)

    def test_large_physical_page_uses_bounded_user_units_without_resizing_marks(self):
        d=self.document(1,width=1024,height=16,ppi=1)
        a=self.export(d,self.settings(marks={}));pdf=pdf_reader.Pdf(a);page=pdf.pages[0]
        self.assertGreater(page['UserUnit'],1);self.assertLessEqual(max(page['MediaBox']),14400)
        s=strokes(pdf)[0];self.assertEqual(s['width'],.25)
        for path in s['paths'][:8]:self.assertAlmostEqual(math.dist(path[0][1],path[1][1]),6,places=8)
        self.assertEqual(a['pages'][0]['physical_points'],[1024*72+24.5,16*72+24.5])

    def test_mark_modes_and_explicit_failure_boundaries(self):
        d=self.document()
        for marks,count in [(dict(registration=False),8),(dict(crop=False),12)]:
            self.assertEqual(len(strokes(pdf_reader.Pdf(self.export(d,self.settings(marks=marks))))[0]['paths']),count)
        for marks in [dict(crop=False,registration=False),dict(gap_pt=0),dict(line_width_pt=5),dict(length_pt=0),dict(registration_radius_pt=.1),dict(line_width_pt=2),dict(unknown=True)]:
            self.assertEqual(self.export(d,self.settings(marks=marks),1)['code'],'INVALID_REQUEST')
        small=self.document(width=8,height=8)
        self.assertEqual(self.export(small,self.settings(marks={}),1)['code'],'INVALID_REQUEST')
        settings=self.settings();del settings['spot_fallback'];self.assertEqual(self.export(d,settings,1)['code'],'INVALID_REQUEST')
        self.export(self.document(0),settings)
        for conflicting in [dict(color='native_inks'),dict(print=dict(profile=embedded(cmyk_profile()),matte=[255]*3)),dict(ink_recipe={}),dict(include_bleed=True)]:
            self.assertEqual(self.export(d,expected=1,**conflicting)['code'],'INVALID_REQUEST')

    def test_ordered_pages_keep_separate_spot_sets_and_profile_identity(self):
        d=self.document();d['items']=[]
        for i in range(2):
            d['items'].append(dict(id=f'b{i}',content=dict(type='frame',frame=dict(role='artboard',width=32+i*8,height=24))))
            d['items'].append(rect(f'p{i}',named(f's{i}',tint=.5),parent=f'b{i}'))
        a=self.export(d,artboards=dict(type='ids',ids=['b1','b0']));pdf=pdf_reader.Pdf(a)
        for j,i in enumerate([1,0]):
            im,data=page_image(pdf,j);space=pdf.get(im['ColorSpace'])
            self.assertEqual(space[1],['Cyan','Magenta','Yellow','Black',f'Inkbolt.s{i}'])
            self.assertEqual(a['pages'][j]['artboard_id'],f'b{i}')
            self.assertEqual(pdf.streams[space[2][1]],cmyk_profile())
            _,expected=self.plate_bytes(d,artboard_id=f'b{i}');self.assertEqual(data,expected)

    def test_profile_file_and_private_source_remain_unchanged(self):
        d=self.document();d['metadata']=dict(title='Original marked page',private=dict(note='unpublished-native-note'))
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);p=root/'original.icc';raw=cmyk_profile();p.write_bytes(raw)
            settings=self.settings(marks={});settings['profile']=dict(type='file',source_path=str(p),sha256=hashlib.sha256(raw).hexdigest())
            for mode in ['public','strip']:
                artifact=self.invoke(dict(command='document.export',document=d,format='pdf',pdf_options=dict(prepress=settings),metadata_policy=dict(mode=mode)))
                payload=base64.b64decode(artifact['data']);self.assertNotIn(b'unpublished-native-note',payload);self.assertNotIn(str(p).encode(),payload)
                self.assertEqual(b'Original marked page' in payload,mode=='public')
                pdf=pdf_reader.Pdf(artifact);space=pdf.get(page_image(pdf)[0]['ColorSpace']);self.assertEqual(pdf.streams[space[2][1]],raw)
            self.assertEqual(p.read_bytes(),raw)
            settings['profile']['sha256']='0'*64;self.assertEqual(self.export(d,settings,1)['code'],'PROFILE_MISMATCH')

    def test_aggregate_page_pixel_and_ink_work_limits_leave_no_partial_file(self):
        # Each page is individually admissible; their selected range is not.
        for page_count,paint_count in [(17,0),(3,12)]:
            d=self.document(0,width=512,height=512);d['items']=[]
            for i in range(page_count):
                board=f'b{i}'
                d['items'].append(dict(id=board,content=dict(type='frame',frame=dict(role='artboard',width=512,height=512))))
                d['items'].extend(rect(f'p{i}-{j}',named('process'),parent=board,box=(0,0,512,512)) for j in range(paint_count))
            options=dict(prepress=self.settings(),artboards=dict(type='all'))
            with tempfile.TemporaryDirectory() as root:
                root=Path(root);sentinel=root/'source.json';source=json.dumps(d).encode();sentinel.write_bytes(source)
                output=dict(output_root=str(root),file_name='bounded.pdf',format='pdf',pdf_options=options)
                error=self.invoke(dict(command='document.publish',document=d,output=output),1)
                self.assertEqual(error['code'],'RESOURCE_LIMIT');self.assertIn('aggregate',error['message'])
                self.assertEqual(sorted(p.name for p in root.iterdir()),['source.json']);self.assertEqual(sentinel.read_bytes(),source)

    def test_agent_publication_history_retry_and_failed_pages_preserve_outputs(self):
        d=self.document();c=Client();self.addCleanup(c.close);c.initialize()
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);s=dict(session_root=str(root/'sessions'),session_id='native')
            c.success('session.create',**s,request_id='create',document=d)
            before=c.success('session.read',**s)
            out=dict(output_root=str(root),file_name='native.pdf',format='pdf',pdf_options=dict(prepress=self.settings(marks={})))
            published=c.success('session.publish',**s,expected_revision=0,output=out)
            raw=(root/'native.pdf').read_bytes();self.assertEqual(published['sha256'],hashlib.sha256(raw).hexdigest())
            self.assertEqual(c.tool('session.publish',**s,expected_revision=0,output=out)['structuredContent']['error']['code'],'OUTPUT_EXISTS')
            edit=dict(request_id='opacity',expected_revision=0,action=dict(type='edit',operations=[dict(op='properties',id='group',opacity=.5)]))
            changed=c.success('session.apply',**s,**edit)
            c.success('session.apply',**s,request_id='undo',expected_revision=1,action=dict(type='undo'))
            restored=c.success('session.read',**s)['document'];self.assertEqual(restored['items'],before['document']['items'])
            c.success('session.apply',**s,request_id='redo',expected_revision=2,action=dict(type='redo'))
            retry=c.success('session.apply',**s,**edit);self.assertTrue(retry['replayed']);self.assertEqual(retry['document'],changed['document'])
            failed=dict(out,file_name='cancelled.pdf');err=c.tool('session.publish',**s,expected_revision=3,output=failed,control=dict(timeout_ms=0))['structuredContent']['error']
            self.assertEqual(err['code'],'TIMEOUT');self.assertFalse((root/'cancelled.pdf').exists());self.assertEqual((root/'native.pdf').read_bytes(),raw)
            bad=self.document();bad['items']=[dict(id='a',content=dict(type='frame',frame=dict(role='artboard',width=32,height=24))),dict(id='b',content=dict(type='frame',frame=dict(role='artboard',width=32,height=24))),rect('valid',named('process'),parent='a'),dict(id='unsupported',parent='b',content=dict(type='group',isolated=False),filters=[dict(id='unsupported',operator=dict(type='surface',radius=1,threshold=.25))])]
            out['file_name']='failed.pdf';out['pdf_options']['artboards']=dict(type='ids',ids=['a','b'])
            self.assertEqual(c.tool('document.publish',document=bad,output=out)['structuredContent']['error']['code'],'UNSUPPORTED');self.assertFalse((root/'failed.pdf').exists())


if __name__=='__main__':unittest.main()
