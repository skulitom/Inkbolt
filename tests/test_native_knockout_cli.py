"""Conditional footprint probabilities and seeded native-ink coverage."""
import copy
from fractions import Fraction as F
import hashlib
import itertools
import math
from pathlib import Path
import tempfile
import unittest
import pdf_reader
import test_native_coverage_cli as coverage_tests
from test_native_blending_cli import MODES, over, addresses
from test_knockout_cli import group
from test_effects_coverage_cli import threshold
from test_native_images_cli import fill, raster, process
from test_native_print_cli import page_image
from test_vector_plates_cli import color, named, rect
from test_artwork_masks_cli import source, rect as mask_rect
from test_masks_cli import inverse
from test_mcp import Client


def partition(current, initial, paint, footprint, opacity, addressed, mode='normal'):
    """Condition on the incoming footprint; never use ink-retention recurrences."""
    inside,alpha=over(*initial,paint,opacity,addressed,mode)
    return ([footprint*x+(1-footprint)*y for x,y in zip(inside,current[0])],
            footprint*alpha+(1-footprint)*current[1])


def finish(back, result, isolated, weight=F(1)):
    values,alpha=result
    return ([weight*v+(1-weight*alpha)*b for v,b in zip(values,back)] if isolated
            else [b+weight*(v-b) for b,v in zip(back,values)])


class NativeKnockoutTests(unittest.TestCase):
    invoke=coverage_tests.NativeCoverageTests.invoke
    document=coverage_tests.NativeCoverageTests.document
    planes=coverage_tests.NativeCoverageTests.planes
    values=coverage_tests.NativeCoverageTests.values
    assertValues=coverage_tests.NativeCoverageTests.assertValues
    edit=coverage_tests.NativeCoverageTests.edit
    export=coverage_tests.NativeCoverageTests.export

    def scene(self,w=1,isolated=True):
        back=[F(3,4),F(1,2),F(1,4),F(1,8),F(5,8)]
        first=[F(1,2),F(0),F(1,4),F(0),F(0)]
        last=[F(0),F(3,4),F(1,2),F(1,4),F(0)]
        d=self.document(w,1)
        d['swatches'].update({k:color(list(map(float,v[:4]))) for k,v in [('back',back),('first',first),('last',last)]})
        d['items']=[fill('back',named('back'),box=(0,0,w,1)),fill('spot',named('s',tint=.625,overprint='preserve'),box=(0,0,w,1)),group('g',isolated),fill('first',named('first',opacity=.5,overprint='preserve'),box=(0,0,w,1),parent='g',opacity=.75),fill('last',named('last',opacity=.625),box=(0,0,w,1),parent='g',opacity=.375)]
        return d,back,first,last

    def test_every_blend_and_overprint_policy_uses_group_entry_backdrop(self):
        for mode,isolated,policy,spot in itertools.product(MODES,[False,True],['knockout','preserve','preserve_nonzero'],[False,True]):
            d,b,a,s=self.scene(isolated=isolated);d['items'][2]['opacity']=.625
            d['items'][-1]['blend']=mode
            d['items'][-1]['content']['paint']=named('s' if spot else 'last',tint=.375 if spot else 1,opacity=.625,overprint=policy)
            if spot:s=[F(0)]*4+[F(3,8)]
            initial=([F(0)]*5,F(0)) if isolated else (b,F(1))
            current=over(*initial,a,F(1,2)*F(3,4),addresses(a,'preserve'))
            result=partition(current,initial,s,F(5,8),F(3,8),addresses(s,policy,spot),mode)
            with self.subTest(mode=mode,isolated=isolated,policy=policy,spot=spot):self.assertValues(self.values(d)[0],finish(b,result,isolated,F(5,8)),3e-12)

    def test_zero_opacity_fill_and_hidden_or_intrinsically_empty_paint(self):
        for isolated,property in itertools.product([False,True],['opacity','fill_opacity','visible','intrinsic']):
            d,b,a,s=self.scene(isolated=isolated);last=d['items'][-1]
            if property=='intrinsic':last['content']['paint']['opacity']=0
            else:last[property]=False if property=='visible' else 0
            initial=([F(0)]*5,F(0)) if isolated else (b,F(1))
            current=over(*initial,a,F(3,8),addresses(a,'preserve'))
            result=current if property in ('visible','intrinsic') else partition(current,initial,s,F(5,8),F(0),[True]*5)
            self.assertValues(self.values(d)[0],finish(b,result,isolated))

    def test_fully_covered_previous_sibling_has_no_contribution(self):
        for mode,isolated,policy,spot in itertools.product(MODES,[False,True],['knockout','preserve'],[False,True]):
            d,*_=self.scene(isolated=isolated);d['items'][-1].update(blend=mode)
            d['items'][-1]['content']['paint']=named('s' if spot else 'last',tint=.375 if spot else 1,overprint=policy)
            reduced=copy.deepcopy(d);reduced['items'].pop(3)
            with self.subTest(mode=mode,isolated=isolated,policy=policy,spot=spot):self.assertValues(self.values(d)[0],self.values(reduced)[0])

    def test_nested_group_union_survives_zero_opacity_children(self):
        for oi,ok,ii,ik in itertools.product([False,True],repeat=4):
            d,b,a,s=self.scene(isolated=oi);d['items'][2]['content']['knockout']=ok
            d['items'][-1:]=[group('inner',ii,ik,parent='g',opacity=.375,mask=dict(width=1,height=1,gray_hex='80')),fill('last',named('last',opacity=.625),box=(0,0,1,1),parent='inner',opacity=.25,blend='multiply'),fill('zero',named('s',opacity=.5,overprint='preserve'),box=(0,0,1,1),parent='inner',opacity=0)]
            initial=([F(0)]*5,F(0)) if oi else (b,F(1));current=over(*initial,a,F(3,8),addresses(a,'preserve'))
            ib=initial if ok else current;seed=([F(0)]*5,F(0)) if ii else ib
            result=over(*seed,s,F(5,8)*F(1,4),[True]*5,'multiply')
            if ik:result=partition(result,seed,[F(0)]*4+[F(1)],F(1,2),F(0),addresses(s,'preserve',True))
            m=F(128,255);weight=F(3,8)*m;footprint=(F(5,8)+(1-F(5,8))*F(1,2))*m
            if ii:
                colors,alpha=result;sa=alpha*weight
                if sa:
                    paint=[v/alpha for v in colors]
                    result=partition(current,initial,paint,footprint,sa/footprint,[True]*5) if ok else over(*current,paint,sa,[True]*5)
                else:result=partition(current,initial,[F(0)]*5,footprint,F(0),[True]*5) if ok else current
            else:
                candidate=([x+weight*(y-x) for x,y in zip(ib[0],result[0])],ib[1]+weight*(result[1]-ib[1]))
                result=([footprint*x+(1-footprint)*c for x,c in zip([(v-(1-footprint)*i)/footprint for v,i in zip(candidate[0],initial[0])],current[0])],candidate[1]+(1-footprint)*(current[1]-initial[1])) if ok else candidate
            with self.subTest(oi=oi,ok=ok,ii=ii,ik=ik):self.assertValues(self.values(d)[0],finish(b,result,oi),3e-12)

    def test_shared_mask_clip_and_group_blend_attenuate_shape_and_color_once(self):
        for mode in MODES:
            d,b,a,s=self.scene(4);d['items'][:0]=[source(opacity=.5),mask_rect('mask',w=4,h=1,color=[255,0,0,128],parent='source')]
            d['items'][4].update(opacity=.625,blend=mode,artwork_mask=dict(source='source',region=[0,0,4,1],mode='luminance'))
            d['items'][-1].update(mask=dict(width=4,height=1,gray_hex='004080ff'),clip=dict(geometry=dict(shape='rect',x=1,y=0,width=2,height=1)))
            initial=([F(0)]*5,F(0));current=over(*initial,a,F(3,8),addresses(a,'preserve'))
            for x,actual in enumerate(self.values(d)):
                f=F([0,64,128,255][x],255)*F(5,8) if 1<=x<3 else F(0)
                colors,alpha=partition(current,initial,s,f,F(3,8),[True]*5)
                g=F(5,8)*F(1,2)*F(128,255)*F(2125,10000)
                expected,_=over(b,F(1),[v/alpha for v in colors],alpha*g,[True]*5,mode)
                self.assertValues(actual,expected,3e-12)

    def test_layer_clipping_preserves_base_footprint_inside_knockout(self):
        for isolated,mode in itertools.product([False,True],MODES):
            d,b,a,s=self.scene(isolated=isolated);last=d['items'][-1];last['content']['paint']['overprint']='preserve_nonzero'
            d['items'].append(fill('clip',named('s',tint=.375,opacity=.5,overprint='preserve'),box=(0,0,1,1),parent='g',clip_to='last',blend=mode))
            initial=([F(0)]*5,F(0)) if isolated else (b,F(1));current=over(*initial,a,F(3,8),addresses(a,'preserve'))
            conditional=[v if addressed else bg for v,bg,addressed in zip(s,initial[0],addresses(s,'preserve_nonzero'))]
            painted,_=over(conditional,F(1),[F(0)]*4+[F(3,8)],F(1,2),addresses(s,'preserve',True),mode)
            result=partition(current,initial,painted,F(5,8),F(3,8),[True]*5)
            self.assertValues(self.values(d)[0],finish(b,result,isolated),3e-12)

    def test_dissolve_uses_shared_threshold_for_shape_and_effective_alpha(self):
        for isolated,policy,mode in itertools.product([False,True],['knockout','preserve_nonzero'],['normal','multiply','color']):
            d,b,a,s=self.scene(32,isolated);d['items'][-1].update(coverage=dict(type='dissolve',seed=51),blend=mode,mask=dict(width=32,height=1,gray_hex='ad'*32));d['items'][-1]['content']['paint']['overprint']=policy
            initial=([F(0)]*5,F(0)) if isolated else (b,F(1));current=over(*initial,a,F(3,8),addresses(a,'preserve'))
            for x,actual in enumerate(self.values(d)):
                t=threshold(51,x,0);f=F(F(5,8)*F(173,255)>t);alpha=F(F(5,8)*F(173,255)*F(3,8)>t)
                result=partition(current,initial,s,f,alpha,addresses(s,policy),mode)
                self.assertValues(actual,finish(b,result,isolated),3e-12)

    def test_dissolve_local_cells_reflect_translate_and_supersample(self):
        for transform in [[1,0,0,1,0,0],[-1,0,0,1,8,0],[0,1,-1,0,8,0],[1,0,0,1,2,-2]]:
            d=self.document(8,8,kind='vector');d['swatches']={'b':color([.5,.25,.125,0])};d['items']=[rect('paint',named('b',opacity=.625),box=(0,0,8,8),opacity=.375,transform=transform,coverage=dict(type='dissolve',seed=4294967295))]
            for aa,factor in [('none',1),('supersample2',2),('supersample4',4)]:
                for index,actual in enumerate(self.values(d,antialias=aa)):
                    x,y=index%8,index//8;total=0
                    for j,i in itertools.product(range(factor),repeat=2):
                        q=inverse(transform,[x+(i+.5)/factor,y+(j+.5)/factor]);total+=int(0<=q[0]<8 and 0<=q[1]<8 and threshold(4294967295,*map(math.floor,q))<F(15,64))
                    self.assertValues(actual,[F(total,factor**2)*v for v in [F(1,2),F(1,4),F(1,8),F(0)]])

    def test_group_dissolve_retains_zero_opacity_child_shape_and_clipped_color(self):
        d,b,a,s=self.scene(32,False)
        d['items'][-1:]=[group('inner',True,False,parent='g',opacity=.625,coverage=dict(type='dissolve',seed=73)),fill('base',named('last',opacity=.5),box=(0,0,32,1),parent='inner',opacity=.5),fill('clip',named('s',tint=.75,opacity=.5),box=(0,0,32,1),parent='inner',clip_to='base',coverage=dict(type='dissolve',seed=99)),fill('zero',named('last',opacity=.625),box=(0,0,32,1),parent='inner',opacity=0)]
        current=over(b,F(1),a,F(3,8),addresses(a,'preserve'))
        for x,actual in enumerate(self.values(d)):
            paint=[F(0)]*4+[F(3,4)] if threshold(99,x,0)<F(1,2) else s
            f=F(threshold(73,x,0)<F(13,16));alpha=F(threshold(73,x,0)<F(5,32))
            expected=partition(current,(b,F(1)),paint,f,alpha,[True]*5)[0]
            self.assertValues(actual,expected)

    def test_intrinsic_image_alpha_controls_knockout_footprint(self):
        pixels=[[20,70,210,alpha] for alpha in [0,1,73,128,255]];p=[F(v) for v in process([20/255,70/255,210/255])]+[F(0)]
        for isolated in [False,True]:
            d,b,a,s=self.scene(5,isolated);d['items'][-1]=raster(pixels,5,parent='g',opacity=.375,blend='multiply')
            initial=([F(0)]*5,F(0)) if isolated else (b,F(1));current=over(*initial,a,F(3,8),addresses(a,'preserve'))
            for rgba,actual in zip(pixels,self.values(d)):
                result=partition(current,initial,p,F(rgba[3],255),F(3,8),[True]*5,'multiply');self.assertValues(actual,finish(b,result,isolated),5e-5)

    def test_fractional_geometry_and_output_scale_keep_independent_footprint(self):
        d=self.document(4,2,kind='vector');d['swatches']={'b':color([.5,.25,.125,0]),'s':color([.25,.75,0,.125])};d['items']=[group('g'),rect('base',named('b'),box=(0,0,4,2),parent='g'),rect('cut',named('s'),box=(0,0,2,2),parent='g',opacity=.25,transform=[-1,0,0,1,2.25,0])]
        b=[F(1,2),F(1,4),F(1,8),F(0)];s=[F(1,4),F(3,4),F(0),F(1,8)]
        for actual,f in zip(self.values(d,antialias='coverage'),[F(192,255),F(1),F(64,255),F(0)]*2):self.assertValues(actual,partition((b,F(1)),([F(0)]*4,F(0)),s,f,F(1,4),[True]*4)[0])
        values=self.values(d,points=[[x,y] for y in [0,3,7] for x in range(16)],raster_scale=4)
        for i,actual in enumerate(values):self.assertValues(actual,[v/4 for v in s] if 1<=i%16<9 else b)

    def test_delivery_history_retry_preserves_source_and_native_inks(self):
        d,*_=self.scene(16,False);d['items'][-1]['coverage']=dict(type='dissolve',seed=51)
        d=self.invoke(dict(command='document.validate',document=d));before=copy.deepcopy(d);c=Client();c.initialize();self.addCleanup(c.close)
        with tempfile.TemporaryDirectory() as root:
            s=dict(session_root=str(Path(root)/'sessions'),session_id='native-knockout');c.success('session.create',**s,request_id='create',document=d)
            a=self.planes(d);edit=dict(request_id='group',expected_revision=0,action=dict(type='edit',operations=[dict(op='group_options',id='g',isolated=True,knockout=False)]))
            changed=c.success('session.apply',**s,**edit)['document'];b=self.planes(changed);self.assertNotEqual(a['interleaved_sha256'],b['interleaved_sha256'])
            self.assertEqual(hashlib.sha256(page_image(pdf_reader.Pdf(self.export(changed)))[1]).hexdigest(),b['interleaved_sha256'])
            undo=c.success('session.apply',**s,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'];self.assertEqual(self.planes(undo)['interleaved_sha256'],a['interleaved_sha256'])
            c.success('session.apply',**s,request_id='redo',expected_revision=2,action=dict(type='redo'));self.assertTrue(c.success('session.apply',**s,**edit)['replayed']);self.assertTrue(c.success('session.verify',**s)['valid']);self.assertEqual(d,before)

    def test_hidden_knockout_and_dissolve_do_not_charge_printed_budgets(self):
        d=self.document(512,512,kind='vector');d['items']=[rect('base',named('b'),box=(0,0,512,512)),group('g',visible=False),group('inner',parent='g'),rect('cut',named('b'),box=(0,0,512,512),parent='inner')];self.planes(d)
        d['items'][1]['visible']=True;self.assertEqual(self.planes(d,1)['code'],'RESOURCE_LIMIT')
        d['items']=[rect('base',named('b'),box=(0,0,512,512))]+[rect(f'd{i}',named('b'),box=(0,0,512,512),visible=False,coverage=dict(type='dissolve',seed=i)) for i in range(4)];self.planes(d)
        for item in d['items'][1:]:item['visible']=True
        self.assertEqual(self.planes(d,1)['code'],'RESOURCE_LIMIT')

    def test_capabilities_and_plane_pdf_receipts_agree(self):
        caps=self.invoke(dict(command='capabilities'))['native_prepress'];d,*_=self.scene(8,False)
        d['items'][-1]['coverage']=dict(type='dissolve',seed=51);planes=self.planes(d);artifact=self.export(d)
        self.assertEqual(caps['coverage_composition'],planes['coverage_sources']['composition'])
        self.assertEqual(planes['coverage_sources'],artifact['pages'][0]['coverage_sources'])
        self.assertNotIn('knockout_groups',caps['unsupported']);self.assertNotIn('dissolve',caps['unsupported'])


if __name__=='__main__':unittest.main()
