"""Independent rational device-ink algebra, implicit groups and delivery history."""
import base64
import copy
from fractions import Fraction as F
import hashlib
import itertools
from pathlib import Path
import random
import tempfile
import unittest
import pdf_reader
from test_blending_cli import MODES, channel, mix
import test_native_coverage_cli as coverage_tests
from test_native_coverage_cli import mask
from test_native_images_cli import fill, raster, process
from test_native_print_cli import page_image
from test_vector_plates_cli import color, named
from test_artwork_masks_cli import source, rect as mask_rect, group
from test_mcp import Client


NONSEPARABLE={'hue','saturation','color','luminosity','darker_color','lighter_color'}
def ink_mix(b,s,mode):
    if mode in {'darker_color','lighter_color'}:
        bsum,ssum=sum(b[:4]),sum(s[:4]);tied=abs(float(bsum-ssum))<=8*2**-52*max(1,abs(float(bsum)),abs(float(ssum)))
        take=not tied and (ssum>bsum if mode=='darker_color' else ssum<bsum)
        result=list(s[:4] if take else b[:4])
    elif mode in NONSEPARABLE:
        result=[1-v for v in mix([1-v for v in b[:3]],[1-v for v in s[:3]],mode)]+[s[3] if mode=='luminosity' else b[3]]
    else:result=[1-channel(1-x,1-y,mode) for x,y in zip(b[:4],s[:4])]
    return result+[y if mode in NONSEPARABLE or channel(F(1),F(1),mode)!=1 else 1-channel(1-x,1-y,mode) for x,y in zip(b[4:],s[4:])]

def over(b,ba,s,sa,addressed,mode='normal'):
    if sa==0:return list(b),ba
    # First paint the implicit compatible-overprint group against its initial
    # backdrop, then remove that backdrop and composite with the requested mode.
    group=[sa*y+(1-sa)*x if a else x for x,y,a in zip(b,s,addressed)]
    cs=[(g-(1-sa)*x)/sa for g,x in zip(group,b)]
    cb=[v/ba for v in b] if ba else [F(0)]*len(b)
    blended=ink_mix(cb,cs,mode)
    return [(1-sa)*x+(1-ba)*sa*y+ba*sa*z for x,y,z in zip(b,cs,blended)],ba+(1-ba)*sa

def addresses(values,policy,spot=False):
    if policy=='knockout':return [True]*len(values)
    return [c==4 if spot else c<4 and (policy!='preserve_nonzero' or v!=0) for c,v in enumerate(values)]


class NativeBlendingTests(unittest.TestCase):
    invoke=coverage_tests.NativeCoverageTests.invoke
    document=coverage_tests.NativeCoverageTests.document
    planes=coverage_tests.NativeCoverageTests.planes
    values=coverage_tests.NativeCoverageTests.values
    assertValues=coverage_tests.NativeCoverageTests.assertValues
    edit=coverage_tests.NativeCoverageTests.edit
    export=coverage_tests.NativeCoverageTests.export

    def test_all_process_modes_grid_endpoints_black_and_whole_color_ties(self):
        rng=random.Random(8571);pairs=[]
        for b,s in itertools.product([F(0),F(1,4),F(1,2),F(1)],[F(0),F(1,4),F(1,2),F(1)]):
            pairs.append(([b,1-b,F(1,2),b],[s,F(1,2),1-s,s]))
        pairs.extend(([F(rng.randrange(17),16) for _ in range(4)],[F(rng.randrange(17),16) for _ in range(4)]) for _ in range(16))
        pairs.extend([([F(1),F(0),F(0),F(0)],[F(0),F(0),F(0),F(1)]),([F(0)]*4,[F(1)]*4)])
        d=self.document(len(pairs),1,kind='vector');d['swatches']={};d['items']=[]
        for x,(b,s) in enumerate(pairs):
            for id,values in [('b',b),('s',s)]:
                key=id+str(x);d['swatches'][key]=color([float(v) for v in values]);d['items'].append(mask_rect(key,x=x,w=1,h=1,color=named(key)))
        for mode in MODES:
            for item in d['items'][1::2]:item['blend']=mode
            with self.subTest(mode=mode):
                for actual,(b,s) in zip(self.values(d),pairs):self.assertValues(actual,ink_mix(b,s,mode),3e-12)

    def test_partial_alpha_and_overprint_inside_isolated_or_pass_through_parents(self):
        back=[F(3,4),F(1,2),F(1,4),F(1,8),F(5,8)];base=[F(1,2),F(0),F(1,4),F(0),F(0)];top=[F(0),F(3,4),F(1,2),F(1,4),F(0)]
        for mode,isolated,policy in itertools.product(MODES,[False,True],['knockout','preserve','preserve_nonzero']):
            d=self.document(1,1);d['swatches'].update(back=color([float(v) for v in back[:4]]),base=color([float(v) for v in base[:4]]),top=color([float(v) for v in top[:4]]))
            d['items']=[fill('back',named('back'),box=(0,0,1,1)),fill('spot',named('s',tint=.625,overprint='preserve'),box=(0,0,1,1)),group('g',opacity=.375),fill('base',named('base',opacity=.5,overprint='preserve'),box=(0,0,1,1),parent='g'),fill('top',named('top',opacity=.625,overprint=policy),box=(0,0,1,1),parent='g',blend=mode)]
            d['items'][2]['content']['isolated']=isolated
            before,a=([F(0)]*5,F(0)) if isolated else (back,F(1))
            before,a=over(before,a,base,F(1,2),addresses(base,'preserve'))
            after,a=over(before,a,top,F(5,8),addresses(top,policy),mode)
            expected=[F(3,8)*v+(1-F(3,8)*a)*b for v,b in zip(after,back)] if isolated else [b+F(3,8)*(v-b) for b,v in zip(back,after)]
            with self.subTest(mode=mode,isolated=isolated,policy=policy):self.assertValues(self.values(d)[0],expected,3e-12)

    def test_named_inks_use_only_separable_white_preserving_modes(self):
        back=[F(3,4),F(1,2),F(1,4),F(1,8),F(5,8)];top=[F(0)]*4+[F(3,8)]
        for mode,policy in itertools.product(MODES,['knockout','preserve','preserve_nonzero']):
            d=self.document(1,1);d['swatches']['back']=color([float(v) for v in back[:4]])
            d['items']=[fill('back',named('back'),box=(0,0,1,1)),fill('spot',named('s',tint=.625,overprint='preserve'),box=(0,0,1,1)),fill('top',named('s',tint=.375,opacity=.625,overprint=policy),box=(0,0,1,1),blend=mode)]
            expected,_=over(back,F(1),top,F(5,8),addresses(top,policy,True),mode)
            with self.subTest(mode=mode,policy=policy):self.assertValues(self.values(d)[0],expected,3e-12)

    def test_nested_pass_through_children_see_actual_backdrop_with_group_masks(self):
        back=[F(1,2),F(1,4),F(3,4),F(1,8)];one=[F(1,4),F(3,4),F(1,2),F(1,4)];two=[F(3,4),F(1,2),F(1,4),F(1,2)]
        d=self.document(1,1);d['swatches']={k:color([float(v) for v in vals]) for k,vals in [('back',back),('one',one),('two',two)]}
        d['items']=[fill('back',named('back'),box=(0,0,1,1)),dict(id='outer',opacity=.5,content=dict(type='group',isolated=False)),fill('one',named('one',opacity=.625),box=(0,0,1,1),parent='outer',blend='multiply'),dict(id='inner',parent='outer',opacity=.75,mask=dict(width=1,height=1,gray_hex='80'),content=dict(type='group',isolated=False)),fill('two',named('two',opacity=.75),box=(0,0,1,1),parent='inner',blend='color')]
        a,_=over(back,F(1),one,F(5,8),[True]*4,'multiply');b,_=over(a,F(1),two,F(3,4),[True]*4,'color');g=F(3,4)*F(128,255)
        expected=[base+F(1,2)*(x+g*(y-x)-base) for base,x,y in zip(back,a,b)]
        self.assertValues(self.values(d)[0],expected,3e-12)

    def test_implicit_nonzero_overprint_matches_explicit_resolved_source(self):
        for mode,isolated in itertools.product(MODES,[False,True]):
            d=self.document(1,1);d['swatches']=dict(back=color([.75,.5,.25,.125]),base=color([.5,0,.25,0]),top=color([0,.75,.5,.25]))
            d['items']=[fill('back',named('back'),box=(0,0,1,1)),group('g',opacity=.375),fill('base',named('base',opacity=.5),box=(0,0,1,1),parent='g'),fill('top',named('top',opacity=.625,overprint='preserve_nonzero'),box=(0,0,1,1),parent='g',blend=mode)]
            d['items'][1]['content']['isolated']=isolated
            direct=copy.deepcopy(d);direct['swatches']['top']=color([.25 if isolated else .625,.75,.5,.25]);direct['items'][-1]['content']['paint']['overprint']='knockout'
            with self.subTest(mode=mode,isolated=isolated):
                self.assertValues(self.values(d)[0],self.values(direct)[0],3e-12)

    def test_clipped_blends_use_conditional_base_colors_and_preserve_base_alpha(self):
        back=[F(3,4),F(1,2),F(1,4),F(1,8),F(5,8)];base=[F(1,2),F(0),F(1,4),F(0),F(0)];top=[F(0)]*4+[F(3,8)]
        for mode,bp,tp in itertools.product(MODES,['knockout','preserve_nonzero'],['knockout','preserve']):
            d=self.document(1,1);d['swatches'].update(back=color([float(v) for v in back[:4]]),base=color([float(v) for v in base[:4]]))
            d['items']=[fill('back',named('back'),box=(0,0,1,1)),fill('spot',named('s',tint=.625,overprint='preserve'),box=(0,0,1,1)),fill('base',named('base',opacity=.5,overprint=bp),box=(0,0,1,1),opacity=.375),fill('clip',named('s',tint=.375,opacity=.625,overprint=tp),box=(0,0,1,1),clip_to='base',blend=mode)]
            conditional=[v if a else b for b,v,a in zip(back,base,addresses(base,bp))]
            painted,_=over(conditional,F(1),top,F(5,8),addresses(top,tp,True),mode)
            expected=[b*(1-F(1,2)*F(3,8))+v*F(1,2)*F(3,8) for b,v in zip(back,painted)]
            with self.subTest(mode=mode,bp=bp,tp=tp):self.assertValues(self.values(d)[0],expected,3e-12)

    def test_isolated_group_blend_and_shared_luminance_mask_apply_once(self):
        b=[F(1,2),F(1,4),F(1,8),F(0),F(0)];s=[F(0)]*4+[F(3,4)]
        for mode in MODES:
            d=self.document(4,1);d['items']=[source(opacity=.5),mask_rect('mask-red',w=4,h=1,color=[255,0,0,128],parent='source'),fill('back',named('b'),box=(0,0,4,1)),group('g',opacity=.625,blend=mode,artwork_mask=mask(region=[0,0,4,1],mode='luminance')),fill('spot',named('s',tint=.75,opacity=.5),box=(0,0,4,1),parent='g')]
            opacity=F(1,2)*F(5,8)*F(1,2)*F(128,255)*F(2125,10000)
            expected,_=over(b,F(1),s,opacity,[True]*5,mode)
            for actual in self.values(d):self.assertValues(actual,expected,3e-12)

    def test_opaque_background_blends_against_matte_before_clipped_layers(self):
        for mode in ['multiply','screen','color','luminosity','darker_color']:
            d=self.document(4,1);d['items']=[raster([[20,70,210,128]]*2,2,opacity=.5,blend=mode,transform=[1,0,0,1,1,0]),fill('clip',named('s',tint=.75,opacity=.5,overprint='preserve'),box=(0,0,4,1),clip_to='pixels')];d['background']=dict(item_id='pixels',matte=[230,190,140])
            matte=[F(v) for v in process([230/255,190/255,140/255])];paint=[F(v) for v in process([20/255,70/255,210/255])]
            p,_=over(matte,F(1),paint,F(128,255)*F(1,2),[True]*4,mode)
            for i,actual in enumerate(self.values(d)):self.assertValues(actual,list(p if i in (1,2) else matte)+[F(3,8)],5e-5)
            converted=self.edit(d,[dict(op='background',id='pixels',action=dict(type='to_layer',source_id='retained',matte_id='paper'))])
            self.assertEqual(self.planes(d)['interleaved_sha256'],self.planes(converted)['interleaved_sha256'])

    def test_blend_delivery_history_retry_and_source_preservation(self):
        d=self.document(16,16);d['items']=[fill('back',named('b'),box=(0,0,16,16)),fill('spot',named('s',tint=.75,overprint='preserve',opacity=.5),box=(0,0,16,16),blend='multiply')]
        d=self.invoke(dict(command='document.validate',document=d));before=copy.deepcopy(d);c=Client();c.initialize();self.addCleanup(c.close)
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);s=dict(session_root=str(root/'sessions'),session_id='native-blend');c.success('session.create',**s,request_id='create',document=d)
            a=self.planes(d);edit=dict(request_id='blend',expected_revision=0,action=dict(type='edit',operations=[dict(op='properties',id='spot',blend='screen')]))
            changed=c.success('session.apply',**s,**edit)['document'];b=self.planes(changed);self.assertNotEqual(a['interleaved_sha256'],b['interleaved_sha256'])
            artifact=self.export(changed)
            pdf=pdf_reader.Pdf(artifact);self.assertEqual(hashlib.sha256(page_image(pdf)[1]).hexdigest(),b['interleaved_sha256'])
            undo=c.success('session.apply',**s,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'];self.assertEqual(self.planes(undo)['interleaved_sha256'],a['interleaved_sha256'])
            c.success('session.apply',**s,request_id='redo',expected_revision=2,action=dict(type='redo'));self.assertTrue(c.success('session.apply',**s,**edit)['replayed']);self.assertTrue(c.success('session.verify',**s)['valid']);self.assertEqual(d,before)

    def test_blend_discovery_hidden_sources_and_aggregate_budgets(self):
        caps=self.invoke(dict(command='capabilities'))['native_prepress'];self.assertEqual(caps['blending']['modes'],MODES);self.assertNotIn('non_normal_blends',caps['unsupported'])
        d=self.document(512,512,kind='vector');d['items']=[mask_rect('base',w=512,h=512,color=named('b')),mask_rect('hidden',w=512,h=512,color=named('b'),blend='color',visible=False)]
        original=copy.deepcopy(d);self.assertFalse(self.planes(d)['source_changed']);self.assertEqual(d,original)
        d['items'][1]['visible']=True
        self.assertEqual(self.planes(d,1)['code'],'RESOURCE_LIMIT')


if __name__=='__main__':unittest.main()
