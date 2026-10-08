"""Original source-color and reconstruction oracles for native print images."""
import base64
import copy
from fractions import Fraction as F
import hashlib
import itertools
import json
from pathlib import Path
import struct
import tempfile
import unittest
import pdf_reader
import test_editing_cli as editing
from cmyk_fixtures import cmyk_profile, separation, fixed
from test_profiles_cli import embedded, linear_profile, decode_srgb
from test_sample_profiles_cli import tags_of, repack, intent_profile
from test_samples_cli import layer, packed
from test_images_cli import canonical
from test_vector_plates_cli import rect, named, color, spot
from test_native_print_cli import page_image
from test_resampling_cli import reference
from test_mcp import Client

MATRIX=[[.4360747,.3850649,.1430804],[.2225045,.7168786,.0606169],[.0139322,.0971045,.7141733]]

def fill(id,paint,box=(0,0,8,4),**kw):
    x,y,w,h=box
    return dict(id=id,transform=[1,0,0,1,x,y],content=dict(type='fill',width=w,height=h,paint=paint),**kw)

def process(rgb, matrix=MATRIX, gamma=None, scale=(1,1,1)):
    linear=[decode_srgb(v) if gamma is None else v**gamma for v in rgb]
    xyz=[sum(row[c]*linear[c] for c in range(3))*s for row,s in zip(matrix,scale)]
    return separation([v*32768/65535 for v in xyz])

def raster(colors,w,**kw):
    return dict(id='pixels',content=dict(type='raster',width=w,height=len(colors)//w,rgba_hex=bytes(v for p in colors for v in p).hex()),**kw)

def image_asset(colors,w,stored=False):
    raw=bytes(v for p in colors for v in p);h=len(colors)//w
    return dict(width=w,height=h,sha256=hashlib.sha256(canonical(w,h,raw)).hexdigest(),storage=dict(type='stored') if stored else dict(type='embedded',rgba_hex=raw.hex()))


class NativeImageTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def document(self,w=8,h=4):
        d=self.invoke(dict(command='document.create',id='native-images',kind='raster',width=w,height=h))
        d['swatches']=dict(process=color([.5,.25,.125,0]),s=spot())
        return d
    def planes(self,d,expected=0,root=None,**kw):
        opts=dict(profile=embedded(cmyk_profile()),antialias='none');opts.update(kw)
        return self.invoke(dict(command='document.prepress',document=d,options=opts,**(dict(asset_root=str(root)) if root else {})),expected)
    def samples(self,d,**kw):
        points=[[x,y] for y in range(d['height']) for x in range(d['width'])]
        return [v['ink_fractions'] for v in self.planes(d,samples=points,**kw)['samples']]
    def assertColors(self,actual,expected,tolerance=.00008):
        for a,b in zip(actual,expected,strict=True):self.assertAlmostEqual(a,b,delta=tolerance)

    def test_inline_and_embedded_images_match_elementary_paints_over_named_inks(self):
        colors=[[(x*43+y*11)%256,(x*17+y*67)%256,(x*71+y*13)%256,[0,64,128,255][(x+y)%4]] for y in range(4) for x in range(8)]
        for isolated in [False,True]:
            d=self.document();d['items']=[fill('base',named('process')),fill('ink',named('s',tint=.75,overprint='preserve')),dict(id='g',opacity=.625,content=dict(type='group',isolated=isolated)),raster(colors,8,parent='g')]
            original=copy.deepcopy(d);reference_doc=copy.deepcopy(d);reference_doc['items'].pop()
            reference_doc['items'].extend(fill(f'p{i}',p,box=(i%8,i//8,1,1),parent='g') for i,p in enumerate(colors))
            wanted=self.planes(reference_doc)['interleaved_sha256']
            self.assertEqual(self.planes(d)['interleaved_sha256'],wanted)
            d['assets']=dict(original=image_asset(colors,8));d['items'][-1]['content']=dict(type='image',asset_id='original',width=8,height=4)
            self.assertEqual(self.planes(d)['interleaved_sha256'],wanted)
            observed=self.samples(d)
            for i,p in enumerate(colors):
                a=p[3]/255*.625;expected=[v*a+b*(1-a) for v,b in zip(process([v/255 for v in p[:3]]),[.5,.25,.125,0])]+[.75*(1-a)]
                self.assertColors(observed[i],expected)
            self.assertEqual(original['items'][-1]['content']['rgba_hex'],raster(colors,8)['content']['rgba_hex'])

    def test_all_native_depths_gray_and_source_alpha_are_converted_once(self):
        for depth,maximum in [('u8',255),('u16',65535),('f32',1)]:
            for channels in ['rgba','gray_alpha']:
                values=[]
                for i in range(8):
                    rgb=[(i+.3)/9,(8-i+.2)/9,(i*.7+.1)/9];a=[0,.125,.5,1][i%4]
                    values.extend(rgb+[a] if channels=='rgba' else [rgb[0],a])
                if depth!='f32':values=[round(v*maximum) for v in values]
                l=layer(values,depth,channels,w=8);d=self.document(8,1);d['items']=[l];before=copy.deepcopy(d)
                size=4 if channels=='rgba' else 2;fmt={'u8':'B','u16':'H','f32':'f'}[depth];raw=bytes.fromhex(l['content']['grid']['data_hex']);stored=struct.unpack('<'+fmt*(len(raw)//struct.calcsize(fmt)),raw)
                actual=self.samples(d)
                for i in range(8):
                    p=[v/maximum for v in stored[i*size:(i+1)*size]];rgb=p[:3] if size==4 else [p[0]]*3
                    self.assertColors(actual[i],[v*p[-1] for v in process(rgb)])
                r=self.planes(d);self.assertEqual(r['image_sources'][0]['sample_sha256'],hashlib.sha256(raw).hexdigest());self.assertEqual(d,before)
        d=self.document(8,1);d['items']=[layer([v for k in range(8) for v in [20000+k,20000,20000,65535]],w=8)]
        c=[p[0] for p in self.samples(d)];self.assertTrue(all(b>a for a,b in zip(c,c[1:])),c)

    def test_direct_wide_source_profile_avoids_display_clipping_and_preserves_profile(self):
        matrix=[[.8,.1,.05],[.2,.7,.1],[.01,.02,.79]]
        base=linear_profile(gamma=2);tags=tags_of(base)
        for c,key in enumerate([b'rXYZ',b'gXYZ',b'bXYZ']):tags[key]=b'XYZ '+bytes(4)+b''.join(fixed(row[c]) for row in matrix)
        profile=repack(base,tags);d=self.document(4,1);d['items']=[layer([1,0,0,1,.7,.4,.2,.5,0,1,0,1,.2,.3,.8,1],depth='f32',w=4)]
        grid=d['items'][0]['content']['grid'];grid.update(encoding='profiled_rgb',profile=embedded(profile));before=copy.deepcopy(d)
        actual=self.samples(d)
        for p,q in zip(actual,[(1,0,0,1),(.7,.4,.2,.5),(0,1,0,1),(.2,.3,.8,1)]):self.assertColors(p,[v*q[3] for v in process(q[:3],matrix,gamma=2)])
        self.assertGreater(abs(actual[0][0]-process([1,0,0])[0]),.03)
        self.assertEqual(self.planes(d)['image_sources'][0]['source_profile']['sha256'],hashlib.sha256(profile).hexdigest());self.assertEqual(d,before)

    def test_relative_absolute_source_matrix_and_table_white_scaling(self):
        for tables in [False,True]:
            source_white=(.8,.9,.7);target_white=(.9,.95,.8)
            source=intent_profile(source_white) if tables else linear_profile(gamma=1.5)
            tags=tags_of(source);tags[b'wtpt']=b'XYZ '+bytes(4)+b''.join(fixed(v) for v in source_white);source=repack(source,tags)
            output=cmyk_profile(white=target_white,intents=True)
            d=self.document(1,1);d['items']=[layer([.3,.5,.7,1],depth='f32',w=1)];d['items'][0]['content']['grid'].update(encoding='profiled_rgb',profile=embedded(source))
            for intent in ['relative_colorimetric','absolute_colorimetric']:
                scale=[s/t for s,t in zip(source_white,target_white)] if intent=='absolute_colorimetric' else [1]*3
                q=[.4*v*32768/65535*s for v,s in zip([.9642,1,.8249],scale)] if tables else [sum(row[c]*[.3,.5,.7][c]**1.5 for c in range(3))*32768/65535*s for row,s in zip(MATRIX,scale)]
                actual=self.samples(d,profile=embedded(output),intent=intent)[0];self.assertColors(actual,separation(q,.04),.00013)

    def test_bilinear_uses_associated_retained_profile_values_before_separation(self):
        d=self.document(4,1);p=[[.8,.2,.5,1],[.1,.7,.3,.25]];d['items']=[layer([v for q in p for v in q],depth='f32',w=2,transform=[2,0,0,1,0,0])]
        grid=d['items'][0]['content']['grid'];grid.update(sampling='bilinear',encoding='profiled_rgb',profile=embedded(linear_profile(gamma=2)))
        actual=self.samples(d)
        for i,t in enumerate([0,.25,.75,1]):
            alpha=(1-t)*p[0][3]+t*p[1][3];rgb=[((1-t)*p[0][c]*p[0][3]+t*p[1][c]*p[1][3])/alpha for c in range(3)]
            expected=[v*alpha for v in process(rgb,gamma=2)];self.assertColors(actual[i],expected)
        converted_first=[(.75*a+.25*b*.25) for a,b in zip(process(p[0][:3],gamma=2),process(p[1][:3],gamma=2))]
        self.assertGreater(max(abs(a-b) for a,b in zip(actual[1],converted_first)),.002)

    def test_advanced_reconstruction_crops_and_source_geometry_have_independent_kernels(self):
        colors=[[250,12,91,0],[20,230,40,255],[200,20,230,64],[30,80,140,128],[5,6,7,255],[220,180,90,192]]
        for method,(w,h) in itertools.product(['area','bicubic','lanczos3'],[(5,3),(2,1)]):
            d=self.document(w,h);d['kind']='vector';d['assets']=dict(original=image_asset(colors,3));d['items']=[dict(id='pixels',content=dict(type='image',asset_id='original',width=w,height=h,sampling=method))]
            actual=self.samples(d);wanted=reference(colors,3,2,w,h,method)
            for a,p in zip(actual,wanted):self.assertColors(a,[v*float(p[3])/255 for v in process([float(v)/255 for v in p[:3]])],.0001)
        # Crop discards the red border before reflecting the interior image.
        colors=[[255,0,0,255],[0,255,0,255],[0,0,255,255],[255,0,0,255]]
        d=self.document(2,1);d['assets']=dict(original=image_asset(colors,4));d['items']=[dict(id='pixels',transform=[-1,0,0,1,2,0],content=dict(type='image',asset_id='original',width=2,height=1,crop=dict(x=1,y=0,width=2,height=1)))]
        for p,q in zip(self.samples(d),[[0,0,1],[0,1,0]]):self.assertColors(p,process(q))

    def test_stored_assets_fail_atomically_and_original_bytes_remain_unchanged(self):
        colors=[[20,70,210,128]]*4;asset=image_asset(colors,2,stored=True);d=self.document(2,2);d['assets']=dict(original=asset);d['items']=[dict(id='pixels',content=dict(type='image',asset_id='original',width=2,height=2))]
        self.assertEqual(self.planes(d,1)['code'],'ASSET_ROOT_REQUIRED')
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);store=root/'assets';store.mkdir();path=store/(asset['sha256']+'.rgba8');raw=canonical(2,2,bytes(v for p in colors for v in p))
            self.assertEqual(self.planes(d,1,root=store)['code'],'ASSET_MISSING');path.write_bytes(raw)
            expected=self.planes(d,root=store)['interleaved_sha256'];self.assertEqual(path.read_bytes(),raw)
            bad=raw[:-1]+bytes([raw[-1]^1]);path.write_bytes(bad)
            output=dict(output_root=str(root),file_name='failed.pdf',format='pdf',pdf_options=dict(prepress=dict(profile=embedded(cmyk_profile()))))
            error=self.invoke(dict(command='document.publish',document=d,resources=dict(asset_root=str(store)),output=output),1)
            self.assertEqual(error['code'],'ASSET_CORRUPT');self.assertFalse((root/'failed.pdf').exists());self.assertEqual(path.read_bytes(),bad)
            path.write_bytes(raw);self.assertEqual(self.planes(d,root=store)['interleaved_sha256'],expected)

    def test_native_background_masks_clips_and_supersampling_preserve_retained_source(self):
        d=self.document(8,4);rgb=[.2,.6,.9];d['items']=[layer([v for _ in range(32) for v in rgb+[.5]],depth='f32',w=8,opacity=.5,fill_opacity=.75,mask=dict(width=8,height=4,gray_hex=(bytes([128])*32).hex()),clip=dict(geometry=dict(shape='rect',x=2,y=1,width=4,height=2)))]
        d['background']=dict(item_id='source',matte=[230,190,140]);before=copy.deepcopy(d)
        matte=process([v/255 for v in d['background']['matte']]);ink=process(rgb)
        for aa in ['none','coverage','supersample2','supersample4']:
            values=self.samples(d,antialias=aa)
            for i,p in enumerate(values):
                a=.5*.5*.75*128/255 if 2<=i%8<6 and 1<=i//8<3 else 0
                self.assertColors(p,[b*(1-a)+s*a for b,s in zip(matte,ink)])
        d['items'][0]['visible']=False
        self.assertTrue(all(v==0 for p in self.samples(d) for v in p))
        self.assertEqual(before['items'][0]['content'],d['items'][0]['content'])

    def test_vector_component_image_artboards_bleed_and_pdf_keep_exact_native_planes(self):
        colors=[[20,60,200,128]]*64;d=self.document(40,30);d['kind']='vector';d['assets']=dict(original=image_asset(colors,8))
        d['items']=[dict(id='master',content=dict(type='component_source')),dict(id='image',parent='master',transform=[1,0,0,1,-1,-2],content=dict(type='image',asset_id='original',width=8,height=8)),dict(id='page',transform=[1,0,0,1,10,10],content=dict(type='frame',frame=dict(role='artboard',width=6,height=4,bleed=dict(left=1,right=3,top=2,bottom=4)))),dict(id='placed',parent='page',content=dict(type='instance',instance=dict(source='master')))]
        original=copy.deepcopy(d)
        for bleed,size in [(False,(6,4)),(True,(10,10))]:
            opts=dict(profile=embedded(cmyk_profile()),antialias='none');p=self.planes(d,artboard_id='page',include_bleed=bleed)
            a=self.invoke(dict(command='document.export',document=d,format='pdf',pdf_options=dict(prepress=opts,artboards=dict(type='ids',ids=['page']),include_bleed=bleed)))
            pdf=pdf_reader.Pdf(a);image,data=page_image(pdf);self.assertEqual((image['Width'],image['Height']),size);self.assertEqual(hashlib.sha256(data).hexdigest(),p['interleaved_sha256'])
            ink=[round(v*128) for v in process([20/255,60/255,200/255])]
            expected=bytes(v for y in range(size[1]) for x in range(size[0]) for v in (ink if not bleed or x<8 and y<8 else [0]*4))
            self.assertEqual(data,expected);self.assertEqual(a['pages'][0]['image_sources'],p['image_sources'])
        self.assertEqual(d,original)

    def test_budget_profiles_unsupported_contexts_and_cancel_remain_explicit(self):
        d=self.document(2,1)
        for i in range(17):
            p=linear_profile(gamma=1+i/16);item=layer([.3,.4,.5,1],depth='f32',id=f'p{i}');item['content']['grid'].update(encoding='profiled_rgb',profile=embedded(p));d['items'].append(item)
        self.assertEqual(self.planes(d,1)['code'],'RESOURCE_LIMIT')
        d=self.document(256,256);d['items']=[raster([[20,70,210,128]]*(256*256),256,transform=[.01,0,0,.01,0,0])];d['items'][0]['content']['sampling']='area'
        self.assertEqual(self.planes(d,1)['code'],'RESOURCE_LIMIT')
        d=self.document(2,1);d['items']=[raster([[255,0,0,128]]*2,2,blend='multiply')]
        self.assertFalse(self.planes(d)['source_changed'])
        d['items'][0].pop('blend')
        self.assertEqual(self.invoke(dict(command='document.prepress',document=d,options=dict(profile=embedded(cmyk_profile())),control=dict(timeout_ms=0)),1)['code'],'TIMEOUT')

    def test_agent_profile_edit_plate_delivery_undo_and_source_preservation(self):
        d=self.document(16,16);d['items']=[layer([v for _ in range(16*16) for v in [.3,.6,.9,.5]],depth='f32',w=16)]
        c=Client();self.addCleanup(c.close);c.initialize()
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);s=dict(session_root=str(root/'sessions'),session_id='native-image');c.success('session.create',**s,request_id='create',document=d);before=c.success('session.read',**s)
            opts=dict(profile=embedded(cmyk_profile()),antialias='none');a=c.success('document.prepress',document=before['document'],options=opts)
            edit=dict(request_id='profile',expected_revision=0,action=dict(type='edit',operations=[dict(op='sample_profile',id='source',action=dict(type='assign',profile=embedded(linear_profile())))]))
            changed=c.success('session.apply',**s,**edit)['document'];b=c.success('document.prepress',document=changed,options=opts);self.assertNotEqual(a['interleaved_sha256'],b['interleaved_sha256'])
            self.assertEqual(changed['items'][0]['content']['grid']['data_hex'],before['document']['items'][0]['content']['grid']['data_hex'])
            out=dict(output_root=str(root),file_name='native.pdf',format='pdf',pdf_options=dict(prepress=dict(opts,marks={})))
            published=c.success('session.publish',**s,expected_revision=1,output=out);raw=(root/'native.pdf').read_bytes();self.assertEqual(published['sha256'],hashlib.sha256(raw).hexdigest())
            pdf=pdf_reader.Pdf(dict(data=base64.b64encode(raw).decode()));self.assertEqual(hashlib.sha256(page_image(pdf)[1]).hexdigest(),b['interleaved_sha256'])
            restored=c.success('session.apply',**s,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'];self.assertEqual(self.planes(restored)['interleaved_sha256'],a['interleaved_sha256'])
            c.success('session.apply',**s,request_id='redo',expected_revision=2,action=dict(type='redo'));self.assertTrue(c.success('session.apply',**s,**edit)['replayed']);self.assertEqual((root/'native.pdf').read_bytes(),raw)


if __name__=='__main__':unittest.main()
