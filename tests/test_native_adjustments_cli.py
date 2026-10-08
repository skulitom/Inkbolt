"""Independent profile equations and coverage rules for explicit print adjustments."""
import base64
import copy
from fractions import Fraction as F
import hashlib
import itertools
from pathlib import Path
import tempfile
import unittest
import pdf_reader
import test_native_objects_cli as objects
import test_native_images_cli as images
from test_profiles_cli import embedded,encode_srgb
from test_sample_profiles_cli import solve3
from test_vector_plates_cli import color,named,spot
from test_blending_cli import mix,MODES
from test_native_print_cli import page_image
from test_mcp import Client
from cmyk_fixtures import cmyk_profile

POLICY='profiled_process_preserve_spots'

def observed(ink):
    # Original fixture AToB corners are exactly quantized product functions.
    c,m,y,k=map(F,ink);xyz=[F(round(v*65535),32768)*(1-a)*(1-k) for v,a in zip([.4821,.5,.41245],[c,m,y])]
    matrix=[[F(str(v)) for v in row] for row in images.MATRIX]
    return [encode_srgb(max(0,min(1,float(v)))) for v in solve3(matrix,xyz)]


def adjusted(ink,fn,weight=1,mode='normal'):
    before=observed(ink);after=fn(before);mixed=mix(list(map(F,before)),list(map(F,after)),mode)
    if not weight or all(a==b for a,b in zip(before,mixed)):return list(ink)
    return images.process([a+weight*(b-a) for a,b in zip(before,mixed)])


def adjustment(id='tone',operators=None,clip_to=None,**kw):
    return dict(id=id,content=dict(type='adjustment',adjustment=dict(operators=operators or [dict(type='invert')],clip_to=clip_to)),**kw)


class NativeAdjustmentTests(unittest.TestCase):
    invoke=objects.NativeObjectTests.invoke
    document=objects.NativeObjectTests.document
    assertRows=objects.NativeObjectTests.assertRows

    def planes(self,d,expected=0,**kw):return objects.NativeObjectTests.planes(self,d,expected,adjustment_policy=POLICY,**kw)
    def values(self,d,**kw):return [p['ink_fractions'] for p in self.planes(d,samples=[[x,y] for y in range(d['height']) for x in range(d['width'])],**kw)['samples']]
    def scene(self,w=1,h=1):
        d=self.document(w,h);d['swatches']=dict(p=color([.25,.5,.125,.375]),s=spot());d['items']=[images.fill('p',named('p'),box=(0,0,w,h)),images.fill('s',named('s',tint=.625,overprint='preserve'),box=(0,0,w,h))];return d

    def test_process_observation_rgb_operators_and_spot_identity(self):
        for operation,fn in [(dict(type='invert'),lambda p:[1-v for v in p]),(dict(type='threshold',level=.2),lambda p:[1]*3),(dict(type='color',adjustment=dict(type='channel_mixer',matrix=[[0,0,1],[1,0,0],[0,1,0]])),lambda p:[p[2],p[0],p[1]])]:
            d=self.scene();original=copy.deepcopy(d);d['items'].append(adjustment(operators=[operation]));expected=adjusted([.25,.5,.125,.375],fn)
            self.assertRows(self.values(d),[expected+[.625]],8e-5);self.assertEqual(d['items'][:2],original['items']);self.assertEqual(self.planes(d)['coverage_sources']['adjustments']['policy'],POLICY)

    def test_all_rgb_adjustment_blends_mask_weight_and_order(self):
        for mode in MODES:
            d=self.scene();d['items'].append(adjustment(operators=[dict(type='invert'),dict(type='levels',input=[0,1],output=[.125,.875],gamma=1)],opacity=.625,mask=dict(width=1,height=1,gray_hex='80'),blend=mode))
            expected=adjusted([.25,.5,.125,.375],lambda p:[.125+.75*(1-v) for v in p],.625*128/255,mode)
            with self.subTest(mode=mode):self.assertRows(self.values(d),[expected+[.625]],1.5e-4)

    def test_base_clipped_adjustment_closes_only_modified_process_channels(self):
        d=self.scene();d['items'].append(images.fill('base',named('s',tint=.375,opacity=.5,overprint='preserve'),box=(0,0,1,1),opacity=.625));d['items'].append(adjustment(clip_to='base'))
        expected=adjusted([.25,.5,.125,.375],lambda p:[1-v for v in p]);alpha=.5*.625;expected=[a*(1-alpha)+b*alpha for a,b in zip([.25,.5,.125,.375],expected)]+[.625*(1-alpha)+.375*alpha]
        self.assertRows(self.values(d),[expected],8e-5)
        self.assertAlmostEqual(self.values(d)[0][-1],expected[-1],places=14)

    def test_pass_through_adjustment_has_context_without_new_alpha(self):
        for nested in [False,True]:
            d=self.scene();d['items'].append(dict(id='group',opacity=.375,content=dict(type='group',isolated=False)))
            parent='group';g=.375
            if nested:
                d['items'].append(dict(id='inner',parent='group',opacity=.5,content=dict(type='group',isolated=False)));parent='inner';g*=.5
            d['items'].append(adjustment(parent=parent,opacity=.625));changed=adjusted([.25,.5,.125,.375],lambda p:[1-v for v in p],.625)
            expected=[a+g*(b-a) for a,b in zip([.25,.5,.125,.375],changed)]+[.625];self.assertRows(self.values(d),[expected],8e-5)

    def test_isolated_transparent_sources_and_zero_effect_leave_no_paint(self):
        d=self.scene();d['items'].extend([dict(id='group',opacity=.625,content=dict(type='group',isolated=True)),images.fill('inside',named('p',opacity=.5),box=(0,0,1,1),parent='group'),adjustment(parent='group')])
        converted=adjusted([.25,.5,.125,.375],lambda p:[1-v for v in p]);a=.5*.625;expected=[(1-a)*v+a*q for v,q in zip([.25,.5,.125,.375],converted)]+[.625*(1-a)];self.assertRows(self.values(d),[expected],8e-5)
        empty=self.document(1,1);empty['items']=[dict(id='empty',content=dict(type='group',isolated=True)),adjustment(parent='empty')];self.assertEqual(self.values(empty),[[0,0,0,0]])
        plain=self.scene();before=self.planes(plain)['interleaved_sha256']
        for item in [adjustment(opacity=0),adjustment(visible=False),adjustment(mask=dict(width=1,height=1,gray_hex='00')),adjustment(operators=[dict(type='brightness_contrast',brightness=0,contrast=0)])]:
            same=copy.deepcopy(plain);same['items'].append(item);self.assertEqual(self.planes(same)['interleaved_sha256'],before)

    def test_spatial_clip_and_stable_base_chain_preserve_untouched_pixels(self):
        d=self.scene(4,1);d['items'].extend([images.fill('base',named('p',opacity=.5),box=(0,0,4,1)),adjustment(clip_to='base',clip=dict(geometry=dict(shape='rect',x=1,y=0,width=2,height=1))),adjustment(id='identity',clip_to='base',operators=[dict(type='brightness_contrast',brightness=0,contrast=0)])])
        converted=adjusted([.25,.5,.125,.375],lambda p:[1-v for v in p]);base=[.25,.5,.125,.375];rows=self.values(d)
        expected=[base+[.3125],[(v+q)/2 for v,q in zip(base,converted)]+[.3125],[(v+q)/2 for v,q in zip(base,converted)]+[.3125],base+[.3125]];self.assertRows(rows,expected,8e-5)

    def test_policy_required_bounds_and_invalid_policy_fail_without_output(self):
        d=self.scene();d['items'].append(adjustment());self.assertEqual(objects.NativeObjectTests.planes(self,d,1)['code'],'UNSUPPORTED')
        error=self.invoke(dict(command='document.prepress',document=d,options=dict(profile=embedded(cmyk_profile()),adjustment_policy='guess')),1);self.assertIn(error['code'],['INVALID_REQUEST','INVALID_JSON'])
        large=self.scene(1024,1024);large['items'].append(adjustment());self.assertEqual(self.planes(large,1)['code'],'RESOURCE_LIMIT')
        with tempfile.TemporaryDirectory() as root:
            out=dict(output_root=root,file_name='absent.pdf',format='pdf',pdf_options=dict(prepress=dict(profile=embedded(cmyk_profile()),spot_fallback='multiplicative_declared')))
            self.assertEqual(self.invoke(dict(command='document.publish',document=d,output=out),1)['code'],'UNSUPPORTED');self.assertFalse((Path(root)/'absent.pdf').exists())

    def test_retained_adjustments_binding_history_and_pdf_keep_sources(self):
        source=self.scene(4,2);source['items'].append(adjustment());d=self.document(4,2);d['swatches']=dict(shared=spot());d['items']=[objects.placed(source)];d=self.invoke(dict(command='document.validate',document=d));original=copy.deepcopy(d)
        routes=[dict(object_path=['placed'],source_spot='s',target_spot='shared')];before=self.planes(d,ink_bindings=routes);source['items'][-1]['opacity']=.25
        with tempfile.TemporaryDirectory() as root:
            c=Client();c.initialize();self.addCleanup(c.close);session=dict(session_root=str(Path(root)/'sessions'),session_id='adjusted');c.success('session.create',**session,request_id='create',document=d)
            edit=dict(request_id='adjust',expected_revision=0,action=dict(type='edit',operations=[dict(op='object_replace',id='placed',object=objects.retained(source))]));changed=c.success('session.apply',**session,**edit)['document'];after=self.planes(changed,ink_bindings=routes);self.assertNotEqual(before['interleaved_sha256'],after['interleaved_sha256']);self.assertEqual(before['plates'][-1]['sample_sha256'],after['plates'][-1]['sample_sha256'])
            out=dict(output_root=root,file_name='adjusted.pdf',format='pdf',pdf_options=dict(prepress=dict(profile=embedded(cmyk_profile()),antialias='none',spot_fallback='multiplicative_declared',adjustment_policy=POLICY,ink_bindings=routes)))
            c.success('session.publish',**session,expected_revision=1,output=out);raw=(Path(root)/'adjusted.pdf').read_bytes();pdf=pdf_reader.Pdf(dict(data=base64.b64encode(raw).decode()));self.assertEqual(hashlib.sha256(page_image(pdf)[1]).hexdigest(),after['interleaved_sha256'])
            undone=c.success('session.apply',**session,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'];self.assertEqual(self.planes(undone,ink_bindings=routes)['interleaved_sha256'],before['interleaved_sha256']);c.success('session.apply',**session,request_id='redo',expected_revision=2,action=dict(type='redo'));self.assertTrue(c.success('session.apply',**session,**edit)['replayed']);self.assertTrue(c.success('session.verify',**session)['valid']);self.assertEqual(d,original)


if __name__=='__main__':unittest.main()
