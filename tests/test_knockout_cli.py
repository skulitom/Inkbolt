"""Original exact-rational footprint partitions, nesting and editing fixtures."""
import base64
import copy
from fractions import Fraction as F
import json
import tempfile
import unittest
import test_blending_cli as blending
import test_effects_coverage_cli as effects
import test_editing_cli as editing
from test_blending_cli import MODES, premul, over, layer, rectangle, mask
from test_mcp import Client


def group(id,isolated=True,knockout=True,**kw):
    return dict(id=id,content=dict(type='group',isolated=isolated,knockout=knockout),**kw)


def replace(current, initial, source, footprint, opacity=F(1), mode='normal'):
    # Condition on being inside/outside the incoming footprint, rather than
    # substituting the engine's expanded premultiplied recurrence.
    if not footprint:return current
    inside=over(initial,[v/footprint for v in source],opacity,mode)
    return [footprint*x+(1-footprint)*y for x,y in zip(inside,current)]


class KnockoutTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    document=blending.BlendingTests.document
    edit=blending.BlendingTests.edit
    add=blending.BlendingTests.add
    matches=blending.BlendingTests.matches
    def pixels(self,d,scale=1):
        return editing.png_pixels(base64.b64decode(self.invoke(dict(command='document.export',document=d,format='png',scale=scale))['data']))[2]

    def test_knockout_partitions_every_blend_family_and_both_backdrops(self):
        back=[[31,170,220,a] for a in [0,1,73,128,255]]
        first=[[210,50,110,a] for a in [255,128,73,0,255]]
        last=[[190,140,25,a] for a in [73,255,128,255,0]]
        for isolated in [False,True]:
            for mode in MODES:
                items=[layer('back',back),group('g',isolated),layer('a',first,parent='g',opacity=.625),layer('b',last,parent='g',opacity=.375,blend=mode)]
                d=self.add(self.document(5),items);expected=[]
                for b,a,s in zip(map(premul,back),map(premul,first),map(premul,last)):
                    initial=[F(0)]*4 if isolated else b
                    current=over(initial,a,F(5,8))
                    result=replace(current,initial,s,s[3],F(3,8),mode)
                    expected.append(over(b,result) if isolated else result)
                self.matches(self.pixels(d),expected)

    def test_zero_opacity_fill_and_visibility_have_distinct_footprints(self):
        b,a,s=[40,80,120,173],[250,20,60,255],[20,220,100,255]
        for isolated in [False,True]:
            for kw in [dict(opacity=0),dict(fill_opacity=0),dict(visible=False),dict(opacity=.25),dict(fill_opacity=.25)]:
                d=self.add(self.document(kind='vector'),[rectangle('back',b),group('g',isolated),rectangle('a',a,parent='g'),rectangle('s',s,parent='g',**kw)])
                initial=[F(0)]*4 if isolated else premul(b)
                if kw.get('visible') is False:result=over(initial,premul(a))
                else:result=over(initial,premul(s),F(str(kw.get('opacity',kw.get('fill_opacity',1)))))
                self.matches(self.pixels(d),[over(premul(b),result) if isolated else result])
        # Intrinsic transparent paint is empty; paint alpha is the declared
        # footprint, while item opacity/fill leave that footprint intact.
        d=self.add(self.document(kind='vector'),[group('g'),rectangle('a',a,parent='g'),rectangle('s',s[:3]+[0],parent='g')])
        self.matches(self.pixels(d),[premul(a)])

    def test_nested_group_footprints_do_not_collapse_to_composite_alpha(self):
        b=premul([70,110,210,128]);first=premul([220,40,100,173])
        a=premul([20,230,140,128]);z=premul([180,110,20,73]);union=a[3]+(1-a[3])*z[3]
        for outer_isolated in [False,True]:
            for inner_isolated in [False,True]:
                for inner_knockout in [False,True]:
                    for outer_knockout in [False,True]:
                        items=[layer('back',[[70,110,210,128]]),group('outer',outer_isolated,outer_knockout),layer('first',[[220,40,100,173]],parent='outer',opacity=.75),group('inner',inner_isolated,inner_knockout,parent='outer',opacity=.375,mask=mask([128])),layer('a',[[20,230,140,128]],parent='inner',opacity=.25,blend='multiply'),layer('z',[[180,110,20,73]],parent='inner',opacity=0)]
                        d=self.add(self.document(),items)
                        initial=[F(0)]*4 if outer_isolated else b
                        current=over(initial,first,F(3,4));ib=initial if outer_knockout else current
                        seed=[F(0)]*4 if inner_isolated else ib
                        result=over(seed,a,F(1,4),'multiply')
                        if inner_knockout:result=replace(result,seed,z,z[3],F(0))
                        weight=F(3,8)*F(128,255);f=union*F(128,255)
                        if inner_isolated:
                            source=[v*weight for v in result]
                            result=replace(current,initial,source,f) if outer_knockout else over(current,source)
                        else:
                            candidate=[x+(y-x)*weight for x,y in zip(ib,result)]
                            result=[(1-f)*c+v-(1-f)*i for c,v,i in zip(current,candidate,initial)] if outer_knockout else candidate
                        self.matches(self.pixels(d),[over(b,result) if outer_isolated else result])

    def test_masks_clips_and_group_blend_apply_once(self):
        values=[0,1,73,128,255];back=premul([45,130,200,173]);a=premul([220,40,80,255]);z=premul([80,230,100,255])
        for mode in MODES:
            items=[layer('back',[[45,130,200,173]]*5),group('g',True,opacity=.625,blend=mode,mask=mask(values)),layer('a',[[220,40,80,255]]*5,parent='g'),layer('z',[[80,230,100,255]]*5,parent='g',opacity=.375,mask=mask(values),clip=dict(geometry=dict(shape='rect',x=1,y=0,width=3,height=1)))]
            d=self.add(self.document(5),items);expected=[]
            for x,m in enumerate(values):
                f=F(m,255) if 1<=x<4 else F(0)
                result=replace(a,[F(0)]*4,[v*f for v in z],f,F(3,8))
                expected.append(over(back,result,F(5*m,8*255),mode))
            self.matches(self.pixels(d),expected)

    def test_fractional_edges_affine_reflection_and_export_scale(self):
        # At scale one the backend rectangle has exact gray8 edge samples;
        # scaling by four aligns every edge with the pixel grid.
        d=self.add(self.document(4,2,kind='vector'),[group('g'),rectangle('base',[200,30,90,255],4,2,parent='g'),rectangle('cut',[20,140,230,255],2,2,parent='g',opacity=.25,transform=[-1,0,0,1,2.25,0])])
        a=premul([200,30,90,255]);z=premul([20,140,230,255])
        self.matches(self.pixels(d),[replace(a,[F(0)]*4,[v*f for v in z],f,F(1,4)) for _ in range(2) for f in [F(192,255),F(1),F(64,255),F(0)]])
        self.matches(self.pixels(d,4),[replace(a,[F(0)]*4,z,F(1),F(1,4)) if 1<=x<9 else a for _ in range(8) for x in range(16)])

    def test_seeded_dissolve_uses_shared_threshold_for_shape_and_alpha(self):
        n=32;source=[210,70,160,128];back=premul([20,100,190,173]);first=premul([150,210,20,255]);s=premul(source)
        d=self.add(self.document(n),[layer('back',[[20,100,190,173]]*n),group('g',False),layer('a',[[150,210,20,255]]*n,parent='g'),layer('s',[source]*n,parent='g',opacity=.375,mask=mask([173]*n),coverage=dict(type='dissolve',seed=51))])
        expected=[]
        for x in range(n):
            threshold=effects.threshold(51,x,0);f=F(s[3]*F(173,255)>threshold);a=F(s[3]*F(173,255)*F(3,8)>threshold)
            expected.append(replace(first,back,[v/s[3]*a for v in s],f))
        self.matches(self.pixels(d),expected)

    def test_effect_footprints_survive_fill_zero_and_partial_alpha(self):
        w=5;colors=[[20,80,160,0],[230,40,90,128],[80,190,210,255],[40,120,70,73],[10,40,60,0]]
        fx=[effects.effect('shadow','shadow',[40,80,180,128],sigma=0,offset=[1,0]),effects.effect('edge','stroke',[200,140,40,173],radius=1),effects.effect('tint','overlay',[80,230,110,73])]
        b=[premul([20,30,70,128])]*w;old=[premul([180,70,200,255])]*w
        source=list(map(premul,colors));decorated=effects.decorated(source,w,1,fx,F(0));footprints=effects.decorated(source,w,1,fx)
        d=self.add(self.document(w),[layer('back',[[20,30,70,128]]*w),group('g',False),layer('old',[[180,70,200,255]]*w,parent='g'),layer('art',colors,parent='g',effects=fx,fill_opacity=0,opacity=.625)])
        self.matches(self.pixels(d),[replace(c,bg,s,f[3],F(5,8)) for c,bg,s,f in zip(old,b,decorated,footprints)])

    def test_filtered_nested_footprint_moves_with_source(self):
        f=dict(id='shift',operator=dict(type='spatial',operator=dict(type='offset',offset=[1,0])),border='transparent')
        items=[group('g'),rectangle('old',[220,50,90,255],4,parent='g'),group('inner',True,False,parent='g',filters=[f]),rectangle('low',[20,190,230,255],1,parent='inner',opacity=.25)]
        d=self.add(self.document(4,kind='vector'),items);old=premul([220,50,90,255]);src=premul([20,190,230,255])
        self.matches(self.pixels(d),[old,[v/F(4) for v in src],old,old])

    def test_gradient_alpha_artwork_masks_and_group_zero_opacity(self):
        gradient=dict(type='linear',start=[0,0],end=[4,0],stops=[dict(offset=0,color=[40,200,150,0]),dict(offset=1,color=[40,200,150,255])])
        source=[dict(id='mask-source',content=dict(type='mask_source')),rectangle('mask-art',[100,180,210,128],4,parent='mask-source')]
        mask=dict(source='mask-source',mode='luminance',region=[0,0,4,1])
        old=premul([230,70,100,255]);m=F(128,255)*sum(F(c,255)*w for c,w in zip([100,180,210],[F(2125,10000),F(7154,10000),F(721,10000)]))
        for opacity in [0,.375,1]:
            d=self.add(self.document(4,kind='vector'),source+[group('g'),rectangle('old',[230,70,100,255],4,parent='g'),group('inner',True,False,parent='g',opacity=opacity,artwork_mask=mask),rectangle('gradient',gradient,4,parent='inner',opacity=.5)])
            for scale in [1,2,4]:
                expected=[]
                for _ in range(scale):
                    for x in range(4*scale):
                        f=F(2*x+1,8*scale)*m;s=[F(v,255)*f/2 for v in [40,200,150]]+[f/2]
                        expected.append(replace(old,[F(0)]*4,s,f,F(str(opacity))))
                self.matches(self.pixels(d,scale),expected)

    def test_frame_background_and_artboard_extraction_keep_knockout(self):
        items=[dict(id='board',transform=[1,0,0,1,4,0],content=dict(type='frame',frame=dict(role='artboard',width=4,height=2,background=[30,80,130,128]))),group('g',False,parent='board'),rectangle('old',[220,30,100,255],4,2,parent='g'),dict(id='frame',parent='g',opacity=.25,content=dict(type='frame',frame=dict(width=2,height=2,background=[20,210,180,255])))]
        d=self.add(self.document(8,2,kind='vector'),items)
        background=premul([30,80,130,128]);old=premul([220,30,100,255]);src=premul([20,210,180,255]);p=replace(old,background,src,F(1),F(1,4))
        expected=[p,p,old,old]*2
        result=self.invoke(dict(command='artboard.export',document=d,format='png'))
        pixels=editing.png_pixels(base64.b64decode(result['artifacts'][0]['artifact']['data']))[2];self.matches(pixels,expected)
        self.matches(self.pixels(d),[v for row in range(2) for v in [[F(0)]*4]*4+expected[row*4:row*4+4]])

    def test_grouping_options_duplication_ungroup_and_strict_atomic_errors(self):
        d=self.add(self.document(kind='vector'),[rectangle('a',[200,20,60,255]),rectangle('b',[30,180,90,255],opacity=.5)])
        normal=self.edit(d,[dict(op='group',ids=['a','b'],new_id='g')]);self.assertNotIn('knockout',normal['items'][0]['content'])
        changed=self.edit(normal,[dict(op='group_options',id='g',isolated=True,knockout=True)])
        self.matches(self.pixels(changed),[[v/F(2) for v in premul([30,180,90,255])]])
        self.assertEqual(self.edit(changed,[dict(op='ungroup',id='g')],1)['code'],'UNSUPPORTED')
        same=self.edit(changed,[dict(op='group_options',id='g',isolated=False)]);self.assertTrue(same['items'][0]['content']['knockout'])
        for value in ['true',1,None]:
            bad=copy.deepcopy(changed);bad['items'][0]['content']['knockout']=value
            self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],'INVALID_REQUEST')
        locked=self.edit(changed,[dict(op='properties',id='g',locked=True)])
        self.assertEqual(self.edit(locked,[dict(op='group_options',id='g',isolated=True,knockout=False)],1)['code'],'LOCKED')
        child=self.edit(changed,[dict(op='group',ids=['a','b'],new_id='inner')])
        self.assertEqual(self.edit(child,[dict(op='ungroup',id='inner')],1)['code'],'UNSUPPORTED')
        copied=self.edit(changed,[dict(op='duplicate',id='g',new_id='copy',descendant_ids=dict(a='ca',b='cb'))])
        self.assertTrue(next(i for i in copied['items'] if i['id']=='copy')['content']['knockout'])
        self.assertEqual(self.invoke(dict(command='document.export',document=changed,format='svg'),1)['code'],'UNSUPPORTED')
        self.assertEqual(self.invoke(dict(command='document.validate',document=json.loads(self.invoke(dict(command='document.export',document=changed,format='snapshot'))['data']))),changed)

    def test_unsupported_mask_sources_and_unbound_adjustments_fail_explicitly(self):
        d=self.document()
        for items in [[dict(id='source',content=dict(type='mask_source')),group('g',parent='source')],[group('g'),dict(id='adjust',parent='g',content=dict(type='adjustment',adjustment=dict(operators=[dict(type='invert')])) )]]:
            self.assertEqual(self.edit(d,[dict(op='add',item=i) for i in items],1)['code'],'UNSUPPORTED')
        # Bound adjustments and alpha-clipped siblings operate on the base
        # before it replaces previous members of the knockout group.
        d=self.add(d,[group('g'),layer('old',[[10,20,30,255]],parent='g'),layer('base',[[80,120,160,128]],parent='g',opacity=.5),layer('clip',[[220,50,20,255]],parent='g',clip_to='base')])
        expected=replace(premul([10,20,30,255]),[F(0)]*4,premul([220,50,20,128]),F(128,255),F(1,2));self.matches(self.pixels(d),[expected])
        d=self.edit(d,[dict(op='add',index=2,item=dict(id='adjust',parent='g',content=dict(type='adjustment',adjustment=dict(clip_to='base',operators=[dict(type='invert')]))))]);self.matches(self.pixels(d),[expected])

    def test_memory_work_and_artboard_aggregate_preflight(self):
        for width,height,items,reason in [(1024,512,[group('g')],'memory'),(512,512,[group('g')]+[rectangle(f'p{i}',[0,0,0,255],parent='g',visible=False) for i in range(12)],'work')]:
            d=self.add(self.document(width,height,kind='vector'),items);error=self.invoke(dict(command='document.render',document=d),1)
            self.assertEqual(error['code'],'RESOURCE_LIMIT');self.assertIn(reason,error['message'])
        items=[]
        for i in range(8):
            items.extend([dict(id=f'board{i}',content=dict(type='frame',frame=dict(role='artboard',width=256,height=256))),group(f'g{i}',parent=f'board{i}')])
            items.extend(rectangle(f'p{i}-{j}',[20,30,60,255],parent=f'g{i}') for j in range(12))
        d=self.document(256,256,kind='vector')
        for at in range(0,len(items),64):d=self.add(d,items[at:at+64])
        self.assertEqual(self.invoke(dict(command='artboard.export',document=d,format='png'),1)['code'],'RESOURCE_LIMIT')

    def test_mcp_edit_diff_and_durable_history(self):
        d=self.add(self.document(kind='vector'),[group('g',True,False),rectangle('a',[200,30,90,255],parent='g'),rectangle('b',[20,210,120,255],parent='g',opacity=.25)])
        ops=[dict(op='group_options',id='g',isolated=True,knockout=True)];changed=self.edit(d,ops)
        info=self.invoke(dict(command='document.inspect',document=changed))['items'][0];self.assertEqual(info['group'],dict(isolated=True,knockout=True,role='group'))
        delta=self.invoke(dict(command='document.diff',before=d,after=changed));self.assertIn('content.knockout',delta['items'][0]['fields'])
        self.assertTrue(self.invoke(dict(command='capabilities'))['blending']['knockout'])
        with tempfile.TemporaryDirectory() as root:
            args=dict(session_root=root,session_id='knockout');c=Client();c.initialize()
            try:
                c.success('session.create',**args,request_id='create',document=d)
                action=dict(type='edit',operations=ops)
                result=c.success('session.apply',**args,request_id='enable',expected_revision=0,action=action)
                self.assertEqual(self.pixels(result['document']),self.pixels(changed))
                self.assertTrue(c.success('session.apply',**args,request_id='enable',expected_revision=0,action=action)['replayed'])
                c.success('session.apply',**args,request_id='save',expected_revision=1,action=dict(type='snapshot',name='knockout'))
                self.assertEqual(c.success('session.read',**args,snapshot='knockout')['document']['items'],changed['items'])
                undone=c.success('session.apply',**args,request_id='undo',expected_revision=2,action=dict(type='undo'))['document'];self.assertEqual(undone['items'],d['items'])
                redone=c.success('session.apply',**args,request_id='redo',expected_revision=3,action=dict(type='redo'))['document'];self.assertEqual(redone['items'],changed['items'])
                c.success('session.verify',**args)
            finally:c.close()


if __name__=='__main__':unittest.main()
