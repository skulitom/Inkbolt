"""Original inverse geometry and unquantized source reconstruction for native inks."""
import base64
import copy
from fractions import Fraction as F
import hashlib
import itertools
import json
import math
from pathlib import Path
import struct
import tempfile
import unittest
import pdf_reader
import test_editing_cli as editing
import test_native_images_cli as images
from test_pixel_warps_cli import maps, mesh_points
from test_samples_cli import layer
from test_profiles_cli import embedded, linear_profile
from cmyk_fixtures import cmyk_profile
from test_vector_plates_cli import named, color
from test_native_print_cli import page_image
from test_native_blending_cli import MODES
from test_native_filters_cli import operators as spatial
from test_native_nonlinear_cli import operators as nonlinear
from test_effects_coverage_cli import effect
from test_interpolation_cli import path
from test_mcp import Client


def warps():
    return [dict(type='perspective',corners=[[0,0],[8,0],[6,8],[0,8]]),
            dict(type='mesh',columns=2,rows=2,points=[[0,0],[4,0],[8,0],[0,4],[5,3],[8,4],[0,8],[4,8],[8,8]]),
            dict(type='articulated',columns=2,rows=2,joints=[dict(parent=None,pivot=[0,0],angle=0,translation=[0,0]),dict(parent=0,pivot=[2,2],angle=25,translation=[0,0])],weights=[[.25,.75] if i==4 else [1,0] for i in range(9)])]


def chart():
    return [[(x*29+y*7)%256,(x*11+y*31)%256,(x*19+y*23)%256,[0,64,192,255][(x+2*y)%4]] for y in range(8) for x in range(8)]


def reconstruct(rows,w,h,p,sampling,crop=None,frame=(8,8)):
    """Exact rational associated interpolation, retaining straight source colour."""
    cx,cy,cw,ch=crop or (0,0,w,h)
    x,y=[F(start)+F(q)*size/F(n) for start,q,size,n in zip((cx,cy),p,(cw,ch),frame)]
    def fetch(x,y):return list(map(F,rows[max(cy,min(cy+ch-1,y))*w+max(cx,min(cx+cw-1,x))]))
    if sampling=='nearest':return fetch(math.floor(x),math.floor(y))
    x-=F(1,2);y-=F(1,2);ix,iy=math.floor(x),math.floor(y);fx,fy=x-ix,y-iy
    values=[(fetch(ix+a,iy+b),u*v) for a,u in [(0,1-fx),(1,fx)] for b,v in [(0,1-fy),(1,fy)]]
    alpha=sum(p[3]*q for p,q in values)
    return [sum(p[c]*p[3]*q for p,q in values)/alpha if alpha else F(0) for c in range(3)]+[alpha]


def reconstructed(warp,rows,sampling='bilinear',size=(8,8),scale=1,crop=None,frame=(8,8),world=(1,0,0,1,0,0)):
    _,inverse=maps(warp,frame);a,b,c,d,e,f=map(F,world);det=a*d-b*c;result=[]
    for y in range(size[1]*scale):
        for x in range(size[0]*scale):
            px,py=F(2*x+1,2*scale)-e,F(2*y+1,2*scale)-f
            q=inverse([(d*px-c*py)/det,(-b*px+a*py)/det])
            result.append(reconstruct(rows,8,8,q,sampling,crop,frame) if q is not None else [F(0)]*4)
    return result


def boundary(warp):
    _,points,_=mesh_points(warp);c,r=warp.get('columns',1),warp.get('rows',1)
    indices=list(range(c+1))+[y*(c+1)+c for y in range(1,r+1)]+[r*(c+1)+x for x in reversed(range(c))]+[y*(c+1) for y in reversed(range(1,r))]
    return [list(map(F,points[i])) for i in indices]


def edge_inverse(warp,p):
    _,inverse=maps(warp);q=inverse(p)
    if q is not None:return q
    vertices=boundary(warp);candidates=[]
    for a,b in zip(vertices,vertices[1:]+vertices[:1]):
        delta=[y-x for x,y in zip(a,b)];t=max(F(0),min(F(1),sum((p[k]-a[k])*delta[k] for k in range(2))/sum(v*v for v in delta)))
        q=[a[k]+t*delta[k] for k in range(2)];candidates.append((sum((x-y)**2 for x,y in zip(q,p)),q))
    return inverse(min(candidates,key=lambda a:a[0])[1])


class NativeWarpTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    document=images.NativeImageTests.document
    planes=images.NativeImageTests.planes

    def scene(self,warp=None,sampling='bilinear'):
        d=self.document(8,8);d['items']=[images.raster(chart(),8,pixel_warp=warp or warps()[1])]
        d['items'][0]['content']['sampling']=sampling
        return d

    def values(self,d,**kw):
        scale=kw.get('raster_scale',1);points=[[x,y] for y in range(d['height']*scale) for x in range(d['width']*scale)];result=[]
        for start in range(0,len(points),64):result.extend(p['ink_fractions'] for p in self.planes(d,samples=points[start:start+64],**kw)['samples'])
        return result

    def assertRows(self,actual,expected,tolerance=.00008):
        for i,(a,b) in enumerate(zip(actual,expected,strict=True)):
            self.assertEqual(len(a),len(b))
            self.assertLessEqual(max(abs(float(x)-float(y)) for x,y in zip(a,b)),tolerance,(i,a,b))

    def reference(self,d):
        """Replace the independently inverse-sampled image by native scalar paints."""
        r=copy.deepcopy(d);item=next(i for i in r['items'] if i['id']=='pixels');warp=item.pop('pixel_warp');sampling=item['content'].get('sampling','nearest')
        rows=[[F(v,255) for v in p] for p in chart()];pixels=reconstructed(warp,rows,sampling)
        item['content']=dict(type='group',isolated=True);index=r['items'].index(item)+1
        cells=[]
        for i,p in enumerate(pixels):
            id=f'cell{i}';r['swatches'][id]=dict(name=id,definition=dict(type='process',color=dict(space='srgb',components=list(map(float,p[:3])))))
            cells.append(images.fill(id,named(id,opacity=float(p[3])),box=(i%8,i//8,1,1),parent='pixels'))
        r['items'][index:index]=cells
        return r

    def test_all_maps_sampling_and_reflections_match_unquantized_rational_inverse(self):
        rows=[[F(v,255) for v in p] for p in chart()]
        for original,sampling,reflect in itertools.product(warps(),['nearest','bilinear'],[False,True]):
            warp=copy.deepcopy(original)
            if reflect:
                _,dst,_=mesh_points(warp);warp=dict(type='mesh',columns=warp.get('columns',1),rows=warp.get('rows',1),points=[[8-x,y] for x,y in dst])
            d=self.scene(warp,sampling);source=copy.deepcopy(d);expected=reconstructed(warp,rows,sampling)
            with self.subTest(warp=warp['type'],sampling=sampling,reflect=reflect):
                self.assertRows(self.values(d),[[v*float(p[3]) for v in images.process(list(map(float,p[:3])))] for p in expected])
                self.assertEqual(d,source);self.assertEqual(self.planes(d)['image_sources'][0]['pixel_warp']['controls'],warp)

    def test_profiled_rgb_gray_and_all_depths_retain_source_precision(self):
        for warp,depth,channels,sampling in itertools.product(warps(),['u8','u16','f32'],['rgba','gray_alpha'],['nearest','bilinear']):
            maximum={'u8':255,'u16':65535,'f32':1}[depth];values=[]
            for i in range(64):
                p=[(.7+i%8)/9,(.4+i//8)/9,(.2+i%6)/7,[0,.25,.75,1][i%4]]
                values.extend(p if channels=='rgba' else [p[0],p[3]])
            if depth!='f32':values=[round(v*maximum) for v in values]
            item=layer(values,depth,channels,w=8,id='pixels',pixel_warp=warp);grid=item['content']['grid'];grid.update(sampling=sampling,encoding='profiled_rgb',profile=embedded(linear_profile(gamma=2)))
            raw=bytes.fromhex(grid['data_hex']);fmt={'u8':'B','u16':'H','f32':'f'}[depth];decoded=[v/maximum for v in struct.unpack('<'+fmt*(len(raw)//struct.calcsize(fmt)),raw)];n=4 if channels=='rgba' else 2
            rows=[p if n==4 else [p[0]]*3+[p[1]] for p in [decoded[i:i+n] for i in range(0,len(decoded),n)]]
            d=self.document(8,8);d['items']=[item];expected=reconstructed(warp,rows,sampling)
            self.assertRows(self.values(d),[[v*float(p[3]) for v in images.process(list(map(float,p[:3])),gamma=2)] for p in expected])
            receipt=self.planes(d)['image_sources'][0];self.assertEqual(receipt['sample_sha256'],hashlib.sha256(raw).hexdigest());self.assertTrue(receipt['source_profile']['retained']);self.assertEqual(receipt['depth'],depth)

    def test_source_reconstruction_precedes_nonlinear_colour_conversion(self):
        d=self.scene();rows=[[F(v,255) for v in p] for p in chart()];warp=d['items'][0]['pixel_warp'];q=reconstructed(warp,rows)
        wanted=[[v*float(p[3]) for v in images.process(list(map(float,p[:3])))] for p in q]
        self.assertRows(self.values(d),wanted)
        converted=[images.process(list(map(float,p[:3])))+[p[3]] for p in rows];_,inverse=maps(warp);wrong=[]
        # Interpolating already-separated four inks differs from reconstructing source RGB.
        for y in range(8):
            for x in range(8):
                pos=inverse([F(2*x+1,2),F(2*y+1,2)]);channels=[]
                for c in range(4):
                    values=[[p[c]]*3+[p[-1]] for p in converted];v=reconstruct(values,8,8,pos,'bilinear');channels.append(float(v[0]*v[3]))
                wrong.append(channels)
        self.assertGreater(max(abs(a-b) for p,q in zip(wanted,wrong) for a,b in zip(p,q)),.005)

    def test_cropped_embedded_and_stored_assets_keep_warp_frame_and_exact_inputs(self):
        rows=[[F(v,255) for v in p] for p in chart()];asset=images.image_asset(chart(),8)
        for warp in warps():
            d=self.scene(warp);d['kind']='vector';d['assets']={'source':asset};d['items'][0]['content']=dict(type='image',asset_id='source',width=8,height=8,crop=dict(x=2,y=1,width=4,height=5),sampling='bilinear')
            expected=reconstructed(warp,rows,crop=(2,1,4,5));self.assertRows(self.values(d),[[v*float(p[3]) for v in images.process(list(map(float,p[:3])))] for p in expected])
            embedded_hash=self.planes(d)['interleaved_sha256'];stored=copy.deepcopy(d);stored['assets']['source']['storage']=dict(type='stored')
            with tempfile.TemporaryDirectory() as root:
                store=Path(root);raw=images.canonical(8,8,bytes(v for p in chart() for v in p));source=store/(asset['sha256']+'.rgba8');source.write_bytes(raw)
                self.assertEqual(self.planes(stored,root=store)['interleaved_sha256'],embedded_hash);self.assertEqual(source.read_bytes(),raw)

    def test_mesh_seams_scale_and_supersampling_average_native_inks(self):
        for warp in warps()[1:]:
            d=self.scene(warp);rows=[[F(v,255) for v in p] for p in chart()]
            for scale in [1,2,3]:
                expected=reconstructed(warp,rows,scale=scale)
                self.assertRows(self.values(d,raster_scale=scale),[[v*float(p[3]) for v in images.process(list(map(float,p[:3])))] for p in expected])
            for factor in [2,4]:
                high=reconstructed(warp,rows,scale=factor);inks=[[v*float(p[3]) for v in images.process(list(map(float,p[:3])))] for p in high]
                expected=[[sum(inks[((y*factor+dy)*8*factor+x*factor+dx)][c] for dy in range(factor) for dx in range(factor))/factor**2 for c in range(4)] for y in range(8) for x in range(8)]
                self.assertRows(self.values(d,antialias=f'supersample{factor}'),expected)
            d['items'][0]['content']['rgba_hex']=bytes([20,60,170,255]*64).hex();constant=self.values(d,antialias='supersample4')
            self.assertRows(constant,[images.process([20/255,60/255,170/255])]*64)
            self.assertLess(max(abs(a-b) for p in constant for a,b in zip(p,constant[0])),1e-13)

    def test_boundary_coverage_and_outside_centers_use_projective_edge_inverse(self):
        warp=dict(type='perspective',corners=[[.7,1.3],[7.4,2.2],[6.2,7.1],[1.2,6.4]]);d=self.scene(warp);rows=[[F(v,255) for v in p] for p in chart()]
        stencil=self.document(8,8);stencil['kind']='vector';stencil['swatches']['solid']=color([1,0,0,0]);stencil['items']=[dict(id='shape',content=dict(type='vector',geometry=path(warp['corners']),fill=named('solid')))];coverage=[p[0] for p in self.values(stencil,antialias='coverage')]
        expected=[];outside=0;_,inverse=maps(warp)
        for i,a in enumerate(coverage):
            pos=[F(2*(i%8)+1,2),F(2*(i//8)+1,2)]
            if a:
                outside+=inverse(pos) is None;q=edge_inverse(warp,pos);self.assertIsNotNone(q);p=reconstruct(rows,8,8,q,'bilinear');expected.append([v*float(p[3])*a for v in images.process(list(map(float,p[:3])))])
            else:expected.append([0]*4)
        self.assertGreater(outside,0);self.assertRows(self.values(d,antialias='coverage'),expected)

    def test_all_filters_run_after_warp_and_separation_with_masked_replacement(self):
        for warp,op in itertools.product(warps(),spatial()+nonlinear()):
            d=self.scene(warp);d['items'][0]['filters']=[dict(id='filter',operator=op,border='reflect',opacity=.625,mask=dict(width=8,height=8,gray_hex=bytes([0,64,192,255]*16).hex()))]
            with self.subTest(warp=warp['type'],operator=op):self.assertRows(self.values(d),self.values(self.reference(d)),2e-12)

    def test_all_blends_knockout_masks_clipping_and_effects_use_warped_intrinsic_alpha(self):
        for index,(warp,mode) in enumerate(itertools.product(warps(),MODES)):
            d=self.scene(warp);item=d['items'][0];item.update(parent='group',blend=mode,opacity=.625,fill_opacity=.75,mask=dict(width=8,height=8,gray_hex=bytes([64,128,192,255]*16).hex()),clip=dict(geometry=dict(shape='rect',x=1,y=0,width=6,height=8)))
            # Isolated groups close completed decorations. All-addressed effects
            # make that materialized reference equivalent to a closed image;
            # preserving effects are checked separately against scalar equations.
            item['effects']=[effect('shadow','shadow',named('s',tint=.5),offset=[1,-1],sigma=.5),effect('stroke','stroke',named('process'),radius=1,position='outside'),effect('overlay','overlay',named('s',tint=.75))]
            d['items']=[images.fill('back',named('process'),box=(0,0,8,8)),dict(id='group',opacity=.75,content=dict(type='group',isolated=index%2==0,knockout=True)),images.fill('prior',named('s',opacity=.5),box=(0,0,8,8),parent='group'),item]
            if index%3==0:
                base=images.fill('base',[40,90,170,128],box=(0,0,8,8),parent='group');d['items'].insert(-1,base);item['clip_to']='base'
            if index%2:
                from test_artwork_masks_cli import source,rect
                item.pop('mask');item['artwork_mask']=dict(source='source',region=[0,0,8,8])
                d['items'][0:0]=[source(),rect('mask-left',w=4,h=8,color=[255,255,255,128],parent='source'),rect('mask-right',x=4,w=4,h=8,color=[255,255,255,224],parent='source')]
            with self.subTest(warp=warp['type'],mode=mode):self.assertRows(self.values(d),self.values(self.reference(d)),3e-12)

    def test_preserving_native_effects_match_independent_decorated_alpha_equations(self):
        from test_native_effects_cli import evaluate
        from test_native_blending_cli import addresses
        bg=[F(1,2),F(1,4),F(1,8),F(0),F(5,8)]
        def ink(e,i):
            p=e['color'];spot=p['swatch']=='s';v=([F(0)]*4+[F(1)]) if spot else bg[:4]+[F(0)]
            v=[c*F(p.get('tint',1)) for c in v]
            return v,F(p.get('opacity',1)),addresses(v,p.get('overprint','knockout'),spot)
        for warp in warps():
            d=self.scene(warp);item=d['items'][0];item['fill_opacity']=.75
            fx=[effect('shadow','shadow',named('process',opacity=.75,overprint='preserve_nonzero'),offset=[1,-1],sigma=.5),effect('overlay','overlay',named('s',tint=.75,opacity=.5,overprint='preserve')),effect('outline','stroke',named('s',tint=.5,overprint='preserve'),radius=1,position='outside')]
            item['effects']=fx;d['items']=[images.fill('back',named('process'),box=(0,0,8,8)),images.fill('back-spot',named('s',tint=.625,overprint='preserve'),box=(0,0,8,8)),item]
            pixels=reconstructed(warp,[[F(v,255) for v in p] for p in chart()]);colors=[[F(v) for v in images.process(list(map(float,p[:3])))]+[F(0)] for p in pixels]
            expected=evaluate(colors,[p[3] for p in pixels],8,8,fx,ink,back=[bg]*64,back_alpha=[F(1)]*64,fill_opacity=F(3,4))
            self.assertRows(self.values(d),[p for p,a in expected])

    def test_parent_transform_and_selected_artboard_bleed_preserve_local_fields(self):
        for warp in warps():
            d=self.scene(warp);item=d['items'][0];item['transform']=[0,1,-1,0,8,0];item['parent']='group';d['items'].insert(0,dict(id='group',transform=[-1,0,0,1,8,0],content=dict(type='group')))
            world=[0,1,1,0,0,0];expected=reconstructed(warp,[[F(v,255) for v in p] for p in chart()],world=world)
            self.assertRows(self.values(d),[[v*float(p[3]) for v in images.process(list(map(float,p[:3])))] for p in expected])
            d=self.scene(warp);d.update(width=24,height=24);item=d['items'][0];item.update(parent='page',transform=[1,0,0,1,-1,-2]);d['items'].insert(0,dict(id='page',transform=[1,0,0,1,5,7],content=dict(type='frame',frame=dict(role='artboard',width=8,height=8,bleed=dict(left=1,right=2,top=2,bottom=1)))))
            for bleed in [False,True]:
                ref=self.scene(warp);ref.update(width=11 if bleed else 8,height=11 if bleed else 8);ref['items'][0]['transform']=[1,0,0,1,0 if bleed else -1,0 if bleed else -2]
                self.assertEqual(self.planes(d,artboard_id='page',include_bleed=bleed)['interleaved_sha256'],self.planes(ref)['interleaved_sha256'])

    def test_limits_invalid_maps_sampling_and_cancelled_publication_are_explicit(self):
        d=self.scene();original=copy.deepcopy(d)
        for method in ['area','bicubic','lanczos3']:
            bad=copy.deepcopy(d);bad['items'][0]['content']['sampling']=method;self.assertEqual(self.planes(bad,1)['code'],'UNSUPPORTED')
        bad=copy.deepcopy(d);bad['items'][0]['pixel_warp']['points'][4]=[20,20];self.assertEqual(self.planes(bad,1)['code'],'NONINVERTIBLE_WARP')
        big=self.scene(dict(type='mesh',columns=16,rows=16,points=[[x/2,y/2] for y in range(17) for x in range(17)]));big.update(width=512,height=256)
        error=self.planes(big,1);self.assertEqual(error['code'],'RESOURCE_LIMIT');self.assertIn('inverse sampling',error['message'])
        with tempfile.TemporaryDirectory() as root:
            marker=Path(root)/'cancel';marker.write_text('cancel');output=dict(output_root=root,file_name='failed.pdf',format='pdf',pdf_options=dict(prepress=dict(profile=embedded(cmyk_profile()))))
            for control,code in [(dict(timeout_ms=0),'TIMEOUT'),(dict(cancel_file=str(marker)),'CANCELLED')]:
                self.assertEqual(self.invoke(dict(command='document.publish',document=d,output=output,control=control),1)['code'],code);self.assertFalse((Path(root)/'failed.pdf').exists())
        self.assertEqual(d,original)

    def test_agent_edit_undo_restart_and_exact_PDF_receipts_preserve_original_samples(self):
        d=self.invoke(dict(command='document.validate',document=self.scene(warps()[0])));original=copy.deepcopy(d);before=self.planes(d)
        caps=self.invoke(dict(command='capabilities'))['native_prepress'];self.assertNotIn('pixel_warps',caps['unsupported']);self.assertEqual(caps['pixel_warps']['types'],['perspective','mesh','articulated'])
        c=Client();c.initialize();self.addCleanup(c.close)
        with tempfile.TemporaryDirectory() as root:
            s=dict(session_root=str(Path(root)/'sessions'),session_id='native-warps');c.success('session.create',**s,request_id='create',document=d)
            req=dict(request_id='warp',expected_revision=0,action=dict(type='edit',operations=[dict(op='pixel_warp',id='pixels',warp=warps()[2])]))
            changed=c.success('session.apply',**s,**req)['document'];after=self.planes(changed);self.assertNotEqual(before['interleaved_sha256'],after['interleaved_sha256']);self.assertEqual(changed['items'][0]['content'],d['items'][0]['content'])
            options=dict(profile=embedded(cmyk_profile()),antialias='none');output=dict(output_root=root,file_name='warped.pdf',format='pdf',pdf_options=dict(prepress=options));c.success('session.publish',**s,expected_revision=1,output=output)
            raw=(Path(root)/'warped.pdf').read_bytes();pdf=pdf_reader.Pdf(dict(data=base64.b64encode(raw).decode()));self.assertEqual(hashlib.sha256(page_image(pdf)[1]).hexdigest(),after['interleaved_sha256'])
            export=self.invoke(dict(command='document.export',document=changed,format='pdf',pdf_options=dict(prepress=options)));self.assertEqual(export['pages'][0]['image_sources'],after['image_sources'])
            self.doCleanups();c=Client();c.initialize();self.addCleanup(c.close);undone=c.success('session.apply',**s,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'];self.assertEqual(self.planes(undone)['interleaved_sha256'],before['interleaved_sha256'])
            redone=c.success('session.apply',**s,request_id='redo',expected_revision=2,action=dict(type='redo'))['document'];self.assertEqual(self.planes(redone)['interleaved_sha256'],after['interleaved_sha256']);self.assertTrue(c.success('session.apply',**s,**req)['replayed']);self.assertTrue(c.success('session.verify',**s)['valid']);self.assertEqual((Path(root)/'warped.pdf').read_bytes(),raw);self.assertEqual(d,original)


if __name__=='__main__':unittest.main()
