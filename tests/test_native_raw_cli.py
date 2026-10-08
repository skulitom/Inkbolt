"""Independent sensor, recipe, reconstruction and native print integration checks."""
import base64
import copy
from fractions import Fraction as F
import hashlib
import itertools
import json
from pathlib import Path
import tempfile
import unittest
import pdf_reader
import test_editing_cli as editing
import test_raw_cli as raw
from test_raw_retained_cli import correction_reference,lens
import test_native_images_cli as image_tests
import test_native_warps_cli as warp_tests
from test_native_images_cli import fill,process
from test_native_warps_cli import warps,reconstructed
from test_native_blending_cli import MODES
from test_native_filters_cli import operators as spatial
from test_native_nonlinear_cli import operators as nonlinear
from test_effects_coverage_cli import effect
from test_samples_cli import packed
from test_profiles_cli import embedded
from test_vector_plates_cli import named,spot,color
from cmyk_fixtures import cmyk_profile
from test_native_print_cli import page_image
from test_mcp import Client


def corrections(border='transparent'):
    return dict(denoise=dict(radius=1,threshold=.15,amount=.625),lens=lens(8,8,radial=[.125,.03125,0],tangential=[.015625,-.0078125],border=border),detail=dict(radius=1,threshold=.005,amount=.5))


def developed(capture,codes,settings,correction):
    linear=correction_reference(raw.reference(capture,codes,settings),capture['width'],capture['height'],correction)
    bits=8 if settings['output']=='srgb8' else 16;maximum=(1<<bits)-1
    encoded=[raw.encoded(v,bits) if i%4!=3 else int(v*maximum+.5) for i,v in enumerate(linear)]
    return dict(width=capture['width'],height=capture['height'],depth='u8' if bits==8 else 'u16',channels='rgba',data_hex=packed(encoded,'u8' if bits==8 else 'u16')),[[F(v,maximum) for v in encoded[i:i+4]] for i in range(0,len(encoded),4)]


def retained(data,capture,settings,correction=None,**kw):
    recipe=dict(schema_version=2,algorithm='inkbolt-raw-linear-v2',source_sha256=hashlib.sha256(data).hexdigest(),capture=capture,settings=settings,corrections=correction or {})
    return dict(id='raw',content=dict(type='raw',raw=dict(source_hex=data.hex(),recipe=recipe)),**kw)


class NativeRawTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    document=image_tests.NativeImageTests.document
    planes=image_tests.NativeImageTests.planes
    values=warp_tests.NativeWarpTests.values
    assertRows=warp_tests.NativeWarpTests.assertRows

    def scene(self,pattern='rggb',packing='u16_le',output='srgb16',correction=None,w=8,h=8,settings=None):
        data,capture,codes=raw.fixture(w,h,pattern,packing,signal=lambda x,y,c:16+((x*7+y*11+c*13)%80))
        settings=settings or raw.settings(output=output,range='clip');d=self.document(w,h);d['items']=[retained(data,capture,settings,correction)]
        grid,rows=developed(capture,codes,settings,correction or {})
        return d,grid,rows,data

    def materialized(self,d,grid):
        r=copy.deepcopy(d)
        for item in r['items']:
            if item['id']=='raw':item['content']=dict(type='samples',grid=dict(grid,sampling=item['content']['raw'].get('sampling','nearest')))
        return r

    def test_all_patterns_packings_native_depths_and_padding_match_calibrated_stencils(self):
        for pattern,packing,output,size in itertools.product(raw.PATTERNS,['u8','u16_le','u16_be'],['srgb8','srgb16'],[(3,5),(8,8)]):
            d,grid,rows,data=self.scene(pattern,packing,output,w=size[0],h=size[1]);original=copy.deepcopy(d)
            with self.subTest(pattern=pattern,packing=packing,output=output,size=size):
                self.assertRows(self.values(d),[[v*float(p[3]) for v in process(list(map(float,p[:3])))] for p in rows])
                receipt=self.planes(d)['image_sources'][0];self.assertEqual(receipt['source_sha256'],hashlib.sha256(data).hexdigest());self.assertEqual(receipt['source_bytes'],len(data));self.assertEqual(receipt['sample_sha256'],hashlib.sha256(bytes.fromhex(grid['data_hex'])).hexdigest());self.assertEqual(receipt['depth'],grid['depth']);self.assertEqual(d,original)

    def test_calibration_exposure_white_balance_and_explicit_clip_precede_separation(self):
        for output,wb in itertools.product(['srgb8','srgb16'],[dict(type='gains',rgb=[2,.5,1.5]),dict(type='neutral',rgb=[.5,1,.75])]):
            data,capture,codes=raw.fixture(8,8,signal=lambda x,y,c:(x*17+y*3+c*11)%160)
            capture['camera_to_linear_srgb']=[[1.25,-.25,0],[.125,.75,.125],[-.25,.25,1]]
            settings=raw.settings(output=output,range='clip',exposure_stops=.5,white_balance=wb)
            d=self.document(8,8);d['items']=[retained(data,capture,settings)];grid,rows=developed(capture,codes,settings,{})
            self.assertRows(self.values(d),[[v for v in process(list(map(float,p[:3])))] for p in rows]);self.assertEqual(self.planes(d)['interleaved_sha256'],self.planes(self.materialized(d,grid))['interleaved_sha256'])

    def test_ordered_noise_lens_detail_and_transparent_alpha_match_fraction_reference(self):
        for border,output in itertools.product(['clamp','transparent'],['srgb8','srgb16']):
            full=corrections(border)
            for recipe in [dict(denoise=full['denoise']),dict(lens=full['lens']),dict(detail=full['detail']),full]:
                d,grid,rows,data=self.scene(output=output,correction=recipe)
                self.assertRows(self.values(d),[[v*float(p[3]) for v in process(list(map(float,p[:3])))] for p in rows])
                self.assertEqual(self.planes(d)['interleaved_sha256'],self.planes(self.materialized(d,grid))['interleaved_sha256'])
                if 'lens' in recipe and border=='transparent':self.assertTrue(any(0<p[3]<1 for p in rows))

    def test_depth_choice_and_recipe_identity_remain_visible_and_source_bytes_exact(self):
        a,ga,_,data=self.scene(output='srgb8');b,gb,_,_=self.scene(output='srgb16')
        av,bv=self.values(a),self.values(b);self.assertGreater(max(abs(x-y) for p,q in zip(av,bv) for x,y in zip(p,q)),.0001)
        for d,grid in [(a,ga),(b,gb)]:
            before=copy.deepcopy(d);receipt=self.planes(d)['image_sources'][0];sidecar=self.invoke(dict(command='raw.recipe',document=d,id='raw'))
            self.assertEqual(receipt['recipe_sha256'],hashlib.sha256(sidecar['data'].encode()).hexdigest());self.assertEqual(receipt['recipe'],json.loads(sidecar['data']));self.assertEqual(receipt['recipe'],sidecar['recipe']);self.assertEqual(bytes.fromhex(d['items'][0]['content']['raw']['source_hex']),data);self.assertEqual(d,before)
            self.assertNotEqual(d['resolution_ppi'],receipt['recipe']['settings']['resolution_ppi'])
        self.assertNotEqual(self.planes(a)['image_sources'][0]['sample_sha256'],self.planes(b)['image_sources'][0]['sample_sha256'])

    def test_retained_warps_reconstruct_developed_native_rgb_before_profile_conversion(self):
        for warp,sampling,output in itertools.product(warps(),['nearest','bilinear'],['srgb8','srgb16']):
            d,grid,rows,_=self.scene(output=output,correction=corrections());d['items'][0]['pixel_warp']=warp;d['items'][0]['content']['raw']['sampling']=sampling
            pixels=reconstructed(warp,rows,sampling);self.assertRows(self.values(d),[[v*float(p[3]) for v in process(list(map(float,p[:3])))] for p in pixels])
            self.assertEqual(self.planes(d)['interleaved_sha256'],self.planes(self.materialized(d,grid))['interleaved_sha256'])

    def test_advanced_sampling_transforms_and_supersampling_match_developed_native_grid(self):
        for sampling,output in itertools.product(['nearest','bilinear','area','bicubic','lanczos3'],['srgb8','srgb16']):
            d,grid,_,_=self.scene(output=output,correction=corrections());d['items'][0].update(transform=[-.75,0,0,.5,7,1],opacity=.625);d['items'][0]['content']['raw']['sampling']=sampling
            for aa in ['none','supersample2']:
                self.assertEqual(self.planes(d,antialias=aa)['interleaved_sha256'],self.planes(self.materialized(d,grid),antialias=aa)['interleaved_sha256'])

    def test_filters_blends_preserving_effects_and_knockout_share_developed_intrinsic_alpha(self):
        d,grid,_,_=self.scene(correction=corrections());item=d['items'][0];item.update(parent='g',opacity=.625,fill_opacity=.75,mask=dict(width=8,height=8,gray_hex=bytes([64,128,192,255]*16).hex()),pixel_warp=warps()[1]);item['content']['raw']['sampling']='bilinear'
        item['effects']=[effect('shadow','shadow',named('s',tint=.5,overprint='preserve'),offset=[1,-1],sigma=.5),effect('stroke','stroke',named('process',overprint='preserve_nonzero'),radius=1,position='outside')]
        d['items']=[fill('back',named('process'),box=(0,0,8,8)),dict(id='g',opacity=.75,content=dict(type='group',isolated=False,knockout=True)),fill('prior',named('s',opacity=.5),box=(0,0,8,8),parent='g'),item]
        for mode in MODES:
            item['blend']=mode;self.assertRows(self.values(d),self.values(self.materialized(d,grid)),2e-12)
        item['blend']='normal'
        for op in spatial()+nonlinear():
            item['filters']=[dict(id='f',operator=op,border='reflect',opacity=.5)];self.assertRows(self.values(d),self.values(self.materialized(d,grid)),2e-12)

    def test_artwork_masks_layer_clipping_background_and_page_bleed_preserve_raw_source(self):
        from test_artwork_masks_cli import source,rect
        d,grid,_,_=self.scene(correction=corrections());item=d['items'][0];item['artwork_mask']=dict(source='source',region=[0,0,8,8]);d['items']=[source(),rect('mask',w=8,h=8,color=[255,255,255,128],parent='source'),item,fill('clip',named('s',tint=.75,overprint='preserve'),box=(0,0,8,8),clip_to='raw')];d['background']=dict(item_id='raw',matte=[180,220,240])
        self.assertRows(self.values(d),self.values(self.materialized(d,grid)),2e-12)
        d.pop('background');item.pop('artwork_mask');d['items']=[dict(id='page',transform=[1,0,0,1,5,7],content=dict(type='frame',frame=dict(role='artboard',width=8,height=8,bleed=dict(left=1,right=2,top=2,bottom=1)))),item];item.update(parent='page',transform=[1,0,0,1,-1,-2],pixel_warp=warps()[2]);d.update(width=24,height=24)
        for bleed in [False,True]:
            self.assertEqual(self.planes(d,artboard_id='page',include_bleed=bleed)['interleaved_sha256'],self.planes(self.materialized(d,grid),artboard_id='page',include_bleed=bleed)['interleaved_sha256'])

    def test_distinct_recipes_share_sensor_identity_without_sharing_developed_values(self):
        d,_,_,_=self.scene();second=copy.deepcopy(d['items'][0]);second['id']='second';second['content']['raw']['recipe']['settings']['exposure_stops']=1;second['opacity']=.5;d['items'].append(second)
        before=copy.deepcopy(d);receipts=self.planes(d)['image_sources'];self.assertEqual(len(receipts),2);self.assertEqual(receipts[0]['source_sha256'],receipts[1]['source_sha256']);self.assertNotEqual(receipts[0]['recipe_sha256'],receipts[1]['recipe_sha256']);self.assertNotEqual(receipts[0]['sample_sha256'],receipts[1]['sample_sha256']);self.assertEqual(d,before)
        second['visible']=False;self.assertEqual(len(self.planes(d)['image_sources']),1)

    def test_work_bounds_source_validation_HDR_and_cancelled_publication_are_explicit(self):
        d,_,_,_=self.scene();bad=copy.deepcopy(d);bad['items'][0]['content']['raw']['source_hex']='00'+bad['items'][0]['content']['raw']['source_hex'][2:];self.assertEqual(self.planes(bad,1)['code'],'SOURCE_MISMATCH')
        bad=copy.deepcopy(d);bad['color_space']='linear_srgb';bad['items'][0]['content']['raw']['recipe']['settings'].update(output='linear_srgb32',range='preserve');self.assertEqual(self.planes(bad,1)['code'],'UNSUPPORTED')
        data,capture,_=raw.fixture(128,128,padding=0,signal=lambda x,y,c:64);item=retained(data,capture,raw.settings(output='srgb16',range='clip'),dict(denoise=dict(radius=4,threshold=16,amount=1),lens=lens(128,128),detail=dict(radius=4,threshold=0,amount=1)))
        big=self.document(8,8);big['items']=[dict(copy.deepcopy(item),id=f'raw{i}') for i in range(3)];error=self.planes(big,1);self.assertEqual(error['code'],'RESOURCE_LIMIT');self.assertIn('channel-aware',error['message'])
        with tempfile.TemporaryDirectory() as root:
            marker=Path(root)/'cancel';marker.write_text('cancel');output=dict(output_root=root,file_name='failed.pdf',format='pdf',pdf_options=dict(prepress=dict(profile=embedded(cmyk_profile()))))
            for control,code in [(dict(timeout_ms=0),'TIMEOUT'),(dict(cancel_file=str(marker)),'CANCELLED')]:
                self.assertEqual(self.invoke(dict(command='document.publish',document=d,output=output,control=control),1)['code'],code);self.assertFalse((Path(root)/'failed.pdf').exists())

    def test_original_sensor_and_sidecar_files_remain_unchanged_through_native_delivery(self):
        d,_,_,data=self.scene(correction=corrections());spec=d['items'][0]['content']['raw']
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'sensor.raw';source.write_bytes(data);sidecar=Path(root)/'recipe.json';recipe=self.invoke(dict(command='raw.recipe',document=d,id='raw'));sidecar.write_text(recipe['data'])
            opened=self.invoke(dict(command='raw.reopen',source_path=str(source),recipe_path=str(sidecar),id='reopened'))['document'];opened['resolution_ppi']=96;before=copy.deepcopy(opened);planes=self.planes(opened)
            artifact=self.invoke(dict(command='document.export',document=opened,format='pdf',pdf_options=dict(prepress=dict(profile=embedded(cmyk_profile()),antialias='none'))));self.assertEqual(hashlib.sha256(page_image(pdf_reader.Pdf(artifact))[1]).hexdigest(),planes['interleaved_sha256']);self.assertEqual(artifact['pages'][0]['image_sources'],planes['image_sources'])
            self.assertEqual(source.read_bytes(),data);self.assertEqual(sidecar.read_text(),recipe['data']);self.assertEqual(opened,before)

    def test_agent_settings_edit_undo_retry_and_exact_PDF_keep_sensor_recipe_and_history(self):
        d,_,_,data=self.scene(correction=corrections());d=self.invoke(dict(command='document.validate',document=d));original=copy.deepcopy(d);before=self.planes(d);caps=self.invoke(dict(command='capabilities'))['native_prepress'];self.assertEqual(caps['raw_sources']['outputs'],['srgb8','srgb16']);self.assertNotIn('retained_raw_and_objects',caps['unsupported'])
        c=Client();c.initialize();self.addCleanup(c.close)
        with tempfile.TemporaryDirectory() as root:
            s=dict(session_root=str(Path(root)/'sessions'),session_id='raw-native');c.success('session.create',**s,request_id='create',document=d)
            settings=raw.settings(output='srgb16',range='clip',exposure_stops=1);req=dict(request_id='develop',expected_revision=0,action=dict(type='edit',operations=[dict(op='raw_settings',id='raw',settings=settings,corrections=corrections('clamp'))]))
            changed=c.success('session.apply',**s,**req)['document'];after=self.planes(changed);self.assertNotEqual(before['interleaved_sha256'],after['interleaved_sha256']);self.assertEqual(changed['items'][0]['content']['raw']['source_hex'],data.hex())
            options=dict(profile=embedded(cmyk_profile()),antialias='none');output=dict(output_root=root,file_name='raw.pdf',format='pdf',pdf_options=dict(prepress=options));c.success('session.publish',**s,expected_revision=1,output=output);pdf=(Path(root)/'raw.pdf').read_bytes();self.assertEqual(hashlib.sha256(page_image(pdf_reader.Pdf(dict(data=base64.b64encode(pdf).decode())))[1]).hexdigest(),after['interleaved_sha256'])
            self.doCleanups();c=Client();c.initialize();self.addCleanup(c.close);undone=c.success('session.apply',**s,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'];self.assertEqual(self.planes(undone)['interleaved_sha256'],before['interleaved_sha256']);self.assertEqual(undone['items'][0]['content'],d['items'][0]['content'])
            redone=c.success('session.apply',**s,request_id='redo',expected_revision=2,action=dict(type='redo'))['document'];self.assertEqual(self.planes(redone)['interleaved_sha256'],after['interleaved_sha256']);self.assertTrue(c.success('session.apply',**s,**req)['replayed']);self.assertTrue(c.success('session.verify',**s)['valid']);self.assertEqual((Path(root)/'raw.pdf').read_bytes(),pdf);self.assertEqual(d,original)


if __name__=='__main__':unittest.main()
