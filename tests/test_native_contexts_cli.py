"""Retained source colour contexts and explicit HDR print boundaries."""
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
import test_native_objects_cli as objects
import test_native_images_cli as images
import test_native_warps_cli as warps
import test_hdr_cli as hdr
from test_profiles_cli import embedded, linear_profile
from test_native_print_cli import page_image
from test_vector_plates_cli import color,named,spot
from test_mcp import Client
from test_prepress_extended_cli import attach_recipe
from cmyk_fixtures import cmyk_profile


def project(pixel,view):
    exposure=2**view.get('exposure',0)
    values=[max(0,v*exposure) for v in pixel[:3]]
    values=[min(1,v) if view['tone_map']=='clip' else v/(1+v) for v in values]
    return [float(hdr.encoded(str(v))) for v in values]+[pixel[3]]


class NativeContextTests(unittest.TestCase):
    invoke=objects.NativeObjectTests.invoke
    document=objects.NativeObjectTests.document
    planes=objects.NativeObjectTests.planes
    values=objects.NativeObjectTests.values
    assertRows=objects.NativeObjectTests.assertRows

    def source(self,pixels,w=4):
        d=self.document(w,len(pixels)//w);d['color_space']='linear_srgb';d['items']=[hdr.layer([v for p in pixels for v in p],w=w)];return d

    def scene(self,source,view,**kw):
        d=self.document(source['width'],source['height']);d['items']=[objects.placed(source,settings=dict(view=view,**kw))];return d

    def test_declared_maps_exposure_native_precision_and_source_identity(self):
        pixels=[[-2,.25,8,.5],[2**-126,1,2**32,.25],[.125,.5,.875,1],[4,2,-8,0]];source=self.source(pixels)
        for tone,exposure in itertools.product(['clip','reinhard'],[-2,0,2]):
            view=dict(tone_map=tone,exposure=exposure);d=self.scene(source,view);original=copy.deepcopy(d);r=self.planes(d,samples=[[x,0] for x in range(4)])
            expected=[[v*p[3] for v in images.process(project(p,view)[:3])] for p in pixels]
            self.assertRows([p['ink_fractions'] for p in r['samples']],expected,8e-5)
            receipt=r['image_sources'][0];self.assertEqual(receipt['view'],view);self.assertEqual(receipt['source_sha256'],d['items'][0]['content']['object']['sha256']);self.assertFalse(receipt['source_changed']);self.assertFalse(receipt['link_read']);self.assertEqual(d,original)

    def test_linear_composite_nested_grade_and_parent_spot_knockout(self):
        source=self.source([[4,-2,1.5,.25]],1);source['items'].append(hdr.layer([2,3,-8,.5],id='top',w=1,blend='multiply'))
        alpha=F(5,8);b=list(map(F,[4,-2,1.5]));s=list(map(F,[2,3,-8]));straight=[(F(1,2)*v*F(1,4)+F(1,2)*(F(3,4)*q+F(1,4)*v*q))/alpha for v,q in zip(b,s)]
        middle=self.document(1,1);middle['color_space']='linear_srgb';middle['items']=[objects.placed(source,id='inner',hdr_grade=dict(exposure=-1,gain=[1,.5,2]))]
        view=dict(tone_map='reinhard');d=self.scene(middle,view);d['swatches']=dict(s=spot());d['items'].insert(0,images.fill('spot',named('s',tint=.75),box=(0,0,1,1)))
        rgb=project([float(v*g/2) for v,g in zip(straight,[1,.5,2])]+[float(alpha)],view)
        self.assertRows(self.values(d),[[v*float(alpha) for v in images.process(rgb[:3])]+[float(F(3,4)*(1-alpha))]],8e-5)

    def test_all_associated_reconstruction_methods_project_before_placement(self):
        pixels=[[-2,4,.5,.25],[8,.125,1,.75],[.5,2,-4,.5],[1,0,16,1]];source=self.source(pixels);view=dict(tone_map='reinhard',exposure=-1)
        rgba=[project(p,view) for p in pixels];rows=[[v*p[3] for v in p[:3]]+[p[3]] for p in rgba]
        for method in ['nearest','bilinear','area','bicubic','lanczos3']:
            d=self.scene(source,view,width=7,height=1,sampling=method);d['width']=7
            expected=[]
            for x in range(7):
                p=list(map(float,objects.sample(rows,(4,1),(F(2*x+1,2)*F(4,7),F(1,2)),method,(F(4,7),1))))
                rgb=[v/p[3] for v in p[:3]] if p[3] else [0]*3;expected.append([v*p[3] for v in images.process(rgb)])
            with self.subTest(method=method):self.assertRows(self.values(d),expected,8e-5)

    def test_warped_views_preserve_associated_transparency(self):
        pixels=[[(-2 if i%3==0 else 4),.25,(i%7)/2,[.25,.5,1][i%3]] for i in range(64)];source=self.source(pixels,8);view=dict(tone_map='clip',exposure=-1)
        rgba=[project(p,view) for p in pixels];rows=[[v*p[3] for v in p[:3]]+[p[3]] for p in rgba]
        for warp,method in itertools.product(warps.warps(),['nearest','bilinear']):
            d=self.scene(source,view,sampling=method);d['items'][0]['pixel_warp']=warp;inverse=warps.maps(warp)[1];expected=[]
            for y in range(8):
                for x in range(8):
                    q=inverse([F(2*x+1,2),F(2*y+1,2)]);p=[0]*4 if q is None else list(map(float,objects.sample(rows,(8,8),q,method)))
                    rgb=[v/p[3] for v in p[:3]] if p[3] else [0]*3;expected.append([v*p[3] for v in images.process(rgb)])
            self.assertRows(self.values(d),expected,8e-5)

    def test_nonprinting_recipe_and_output_profile_preserve_working_source(self):
        source=self.document(4,2);source['swatches']=dict(p=color([.5,.25,.125,0]));source['items']=[images.fill('p',named('p'),box=(0,0,4,2))]
        plain=copy.deepcopy(source);attach_recipe(source);source['output_profile']=embedded(linear_profile(gamma=2));d=self.document(4,2);d['items']=[objects.placed(source)];original=copy.deepcopy(d)
        ref=copy.deepcopy(d);ref['items']=[objects.placed(plain)];r=self.planes(d);self.assertEqual(r['interleaved_sha256'],self.planes(ref)['interleaved_sha256'])
        context=r['image_sources'][0]['coverage_sources']['source_context'];self.assertTrue(context['has_ink_recipe']);self.assertTrue(context['has_RGB_output_profile']);self.assertEqual(d,original)
        self.assertEqual(self.planes(source,1)['code'],'UNSUPPORTED')

    def test_shared_artwork_mask_reaches_the_prepared_hdr_view(self):
        pixels=[[4,.5,-1,.5],[2,.25,8,1]];view=dict(tone_map='reinhard')
        for mode,weight in [('alpha',128/255),('luminance',.2125*128/255)]:
            source=self.source(pixels,2)
            source['items'][0]['artwork_mask']=dict(source='mask-source',mode=mode,region=[0,0,2,1])
            source['items'] += [dict(id='mask-source',content=dict(type='mask_source')),dict(id='mask-paint',parent='mask-source',content=dict(type='vector',geometry=dict(shape='rect',x=0,y=0,width=1,height=1),fill=[255,0,0,128]))]
            d=self.scene(source,view);original=copy.deepcopy(d)
            expected=[[v*pixels[0][3]*weight for v in images.process(project(pixels[0],view)[:3])],[0]*4]
            self.assertRows(self.values(d),expected,8e-5);self.assertEqual(d,original)

    def test_view_and_binding_boundaries_are_explicit(self):
        source=self.source([[4,-2,.5,1]],1);d=self.scene(source,dict(tone_map='clip'));source['swatches']=dict(s=spot());d['items']=[objects.placed(source,settings=dict(view=dict(tone_map='clip')))];d['swatches']=dict(s=spot())
        route=dict(object_path=['placed'],source_spot='s',target_spot='s');self.assertEqual(self.planes(d,1,ink_bindings=[route])['code'],'INVALID_INK_BINDING')
        d['items'][0]['content']['object'].pop('view');self.assertEqual(self.planes(d,1)['code'],'HDR_VIEW_REQUIRED')
        encoded=self.document(1,1);d=self.scene(encoded,dict(tone_map='clip'));self.assertEqual(self.planes(d,1)['code'],'INVALID_OBJECT')

    def test_projection_resources_nested_object_count_and_cancellation(self):
        source=self.source([[4,2,-1,.5]],1);d=self.scene(source,dict(tone_map='clip'))
        middle=self.document(1,1);middle['color_space']='linear_srgb';middle['items']=[objects.placed(source,id=f'o{i}') for i in range(32)];d=self.scene(middle,dict(tone_map='clip'));self.assertEqual(self.planes(d,1)['code'],'RESOURCE_LIMIT')
        d=self.scene(source,dict(tone_map='clip'))
        with tempfile.TemporaryDirectory() as root:
            marker=Path(root)/'cancel';marker.write_text('owned');output=dict(output_root=root,file_name='failed.pdf',format='pdf',pdf_options=dict(prepress=dict(profile=embedded(cmyk_profile()))))
            for control,code in [(dict(cancel_file=str(marker)),'CANCELLED'),(dict(timeout_ms=0),'TIMEOUT')]:
                self.assertEqual(self.invoke(dict(command='document.publish',document=d,output=output,control=control),1)['code'],code);self.assertFalse((Path(root)/'failed.pdf').exists())

    def test_source_view_edit_agent_history_and_exact_native_pdf(self):
        source=self.source([[4,2,-1,.5],[.125,.25,.5,1]],2);d=self.scene(source,dict(tone_map='clip'));d=self.invoke(dict(command='document.validate',document=d));original=copy.deepcopy(d)
        before=self.planes(d);obj=copy.deepcopy(d['items'][0]['content']['object']);obj['view']=dict(tone_map='reinhard')
        with tempfile.TemporaryDirectory() as root:
            c=Client();c.initialize();self.addCleanup(c.close);session=dict(session_root=str(Path(root)/'sessions'),session_id='view')
            c.success('session.create',**session,request_id='create',document=d);edit=dict(request_id='view',expected_revision=0,action=dict(type='edit',operations=[dict(op='object_replace',id='placed',object=obj)]))
            changed=c.success('session.apply',**session,**edit)['document'];after=self.planes(changed);self.assertNotEqual(before['interleaved_sha256'],after['interleaved_sha256'])
            output=dict(output_root=root,file_name='view.pdf',format='pdf',pdf_options=dict(prepress=dict(profile=embedded(cmyk_profile()),antialias='none')));c.success('session.publish',**session,expected_revision=1,output=output)
            raw=(Path(root)/'view.pdf').read_bytes();pdf=pdf_reader.Pdf(dict(data=base64.b64encode(raw).decode()));self.assertEqual(hashlib.sha256(page_image(pdf)[1]).hexdigest(),after['interleaved_sha256'])
            undo=c.success('session.apply',**session,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'];self.assertEqual(self.planes(undo)['interleaved_sha256'],before['interleaved_sha256']);c.success('session.apply',**session,request_id='redo',expected_revision=2,action=dict(type='redo'));self.assertTrue(c.success('session.apply',**session,**edit)['replayed']);self.assertTrue(c.success('session.verify',**session)['valid']);self.assertEqual(d,original)


if __name__=='__main__':unittest.main()
