"""Independent rational transfer curves, spatial fields and shared-light tests."""
import base64
import copy
from decimal import Decimal,localcontext
from fractions import Fraction as F
import json
import math
import tempfile
import unittest
import test_blending_cli as blending
import test_effects_coverage_cli as basic
import test_editing_cli as editing
import test_knockout_cli as knockout
from test_blending_cli import premul,over,layer,rectangle,mask
from test_mcp import Client


def curve(knots,a):
    if not knots:return a
    if a==1:return F(str(knots[-1][1]))
    for (x,y),(u,v) in zip(knots,knots[1:]):
        x,y,u,v=map(lambda z:F(str(z)),[x,y,u,v])
        if x<=a<u:return (y*(u-a)+v*(a-x))/(u-x)
    raise AssertionError(a)


def direction(angle):
    a=F(str(angle))%360
    if a in (0,90,180,270):return [(1,0),(0,1),(-1,0),(0,-1)][int(a//90)]
    assert a in (30,225)
    with localcontext() as ctx:
        ctx.prec=60
        return [F(Decimal(3).sqrt()/2),F(1,2)] if a==30 else [-F(Decimal(2).sqrt()/2)]*2


def field(alpha,w,h,e,light,scale):
    op=e['operator'];kind=op['type'];s=F(str(e.get('scale',1)))*scale
    if kind in ['shadow','lit_shadow']:
        offset=op.get('offset')
        if kind=='lit_shadow':offset=[-F(str(op['distance']))*v for v in direction(op.get('azimuth',light))]
        params=dict(type='shadow',sigma=F(str(op['sigma']))*s,offset=[F(str(v))*s for v in offset])
        raw=basic.field(alpha,w,h,params)
    elif kind=='stroke':
        r=op['radius']*s;raw=[];position=op.get('position','outside');n=math.ceil(r)
        for y in range(h):
            for x in range(w):
                values=[basic.get(alpha,w,h,x+dx,y+dy) for dy in range(-n,n+1) for dx in range(-n,n+1) if dx*dx+dy*dy<=r*r]
                a=alpha[y*w+x];raw.append(max(values)-a if position=='outside' else a-min(values) if position=='inside' else max(values)-min(values))
    else:raw=alpha
    return [curve(e.get('contour'),a) for a in raw]


def evaluate(source,w,h,fx,light=225,fill=F(1),scale=1,colors=None):
    alpha=[p[3] for p in source];behind=[[F(0)]*4 for _ in source]
    colors=colors or (lambda e,i:[F(v,255) for v in e['color']])
    def ink(e,i):
        c=colors(e,i);return [v*c[3] for v in c[:3]]+[c[3]]
    for e in fx:
        if e.get('enabled',True) and e['operator']['type'] in ['shadow','lit_shadow']:
            coverage=field(alpha,w,h,e,light,scale);o=F(str(e.get('opacity',1)))
            behind=[over(p,ink(e,i),coverage[i]*o) for i,p in enumerate(behind)]
    content=[[v*fill for v in p] for p in source]
    for e in fx:
        if e.get('enabled',True) and e['operator']['type']=='overlay':
            coverage=field(alpha,w,h,e,light,scale)
            for i,p in enumerate(content):
                c=colors(e,i);q=c[3]*F(str(e.get('opacity',1)))
                content[i]=[v*(1-q)+coverage[i]*q*z for v,z in zip(p,c[:3]+[F(1)])]
    result=[over(b,p) for b,p in zip(behind,content)]
    for e in fx:
        if e.get('enabled',True) and e['operator']['type']=='stroke':
            coverage=field(alpha,w,h,e,light,scale);o=F(str(e.get('opacity',1)))
            result=[over(p,ink(e,i),coverage[i]*o) for i,p in enumerate(result)]
    return result


class ExtendedEffectTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    document=blending.BlendingTests.document
    add=blending.BlendingTests.add
    edit=blending.BlendingTests.edit
    matches=blending.BlendingTests.matches
    def pixels(self,d,scale=1):
        return editing.png_pixels(base64.b64decode(self.invoke(dict(command='document.export',document=d,format='png',scale=scale))['data']))[2]
    def source(self,w=7,h=5):
        colors=[[30+20*x,50+15*y,190,[0,73,128,255][(x+2*y)%4]] for y in range(h) for x in range(w)]
        return self.add(self.document(w,h),[basic.layer('art',colors,w)]),list(map(premul,colors))
    def effect(self,d,fx,**props):
        ops=[dict(op='effects',id='art',effects=fx)]
        if props:ops.append(dict(op='properties',id='art',**props))
        return self.edit(d,ops)

    def test_shared_lighting_cardinals_oblique_and_local_override(self):
        d,source=self.source();fx=[basic.effect('global','lit_shadow',[20,50,120,173],distance=1.25,sigma=.5),basic.effect('local','lit_shadow',[190,110,40,128],distance=1,sigma=0,azimuth=90)]
        d=self.effect(d,fx,fill_opacity=.25)
        for angle in [0,90,180,270,360,-90,30]:
            changed=self.edit(d,[dict(op='global_light',light=dict(azimuth=angle))]);self.matches(self.pixels(changed),evaluate(source,7,5,fx,angle,F(1,4)))
        # A local override does not respond to document lighting.
        local=self.effect(d,[fx[1]],fill_opacity=0)
        self.assertEqual(self.pixels(local),self.pixels(self.edit(local,[dict(op='global_light',light=dict(azimuth=0))])))

    def test_piecewise_contours_all_operators_alpha_endpoints_and_valleys(self):
        d,source=self.source();contours=[[[0,0],[.25,.75],[.5,.125],[1,1]],[[0,0],[.5,1],[1,0]],[[0,0],[1,.5]]]
        for kind,params in [('shadow',dict(offset=[.5,-.25],sigma=.5)),('stroke',dict(radius=1)),('stroke',dict(radius=1,position='inside')),('stroke',dict(radius=1,position='center')),('overlay',{})]:
            for knots in contours:
                fx=[dict(basic.effect('curve',kind,[40,210,120,173],**params),contour=knots,opacity=.625)]
                changed=self.effect(d,fx,fill_opacity=.375);self.matches(self.pixels(changed),evaluate(source,7,5,fx,fill=F(3,8)))
        empty=self.add(self.document(3),[layer('art',[[250,10,90,0]]*3)])
        self.assertEqual(self.pixels(self.effect(empty,[dict(basic.effect('curve','overlay',[0,255,0,255]),contour=contours[1])])),bytes(12))

    def test_fractional_effect_scaling_and_export_scale(self):
        d,source=self.source();base=[basic.effect('s','shadow',[20,40,100,128],offset=[1,-.5],sigma=.5),basic.effect('r','stroke',[230,120,30,255],radius=2),basic.effect('o','overlay',[70,190,160,73])]
        for factor in [.375,.75,1.5,2]:
            fx=[dict(e,scale=factor) for e in base];changed=self.effect(d,fx,fill_opacity=.625)
            for scale in [1,2]:
                enlarged=[source[(y//scale)*7+x//scale] for y in range(5*scale) for x in range(7*scale)]
                self.matches(self.pixels(changed,scale),evaluate(enlarged,7*scale,5*scale,fx,fill=F(5,8),scale=scale))

    def test_spatial_gradient_colors_for_each_effect_keep_transparent_coverage(self):
        d,source=self.source();paint=dict(type='linear',start=[0,0],end=[7,0],stops=[dict(offset=0,color=[20,60,220,0]),dict(offset=1,color=[220,180,40,255])])
        for kind,params in [('shadow',dict(offset=[.5,0],sigma=.5)),('stroke',dict(radius=1)),('overlay',{})]:
            fx=[dict(basic.effect('gradient',kind,paint,**params),contour=[[0,0],[.5,.75],[1,1]],opacity=.625)]
            changed=self.effect(d,fx,fill_opacity=.25)
            def colors(e,i):
                t=F(2*(i%7)+1,14);return [F(a,255)*(1-t)+F(b,255)*t for a,b in zip([20,60,220,0],[220,180,40,255])]
            self.matches(self.pixels(changed),evaluate(source,7,5,fx,fill=F(1,4),colors=colors))

    def test_gradient_layout_follows_item_while_kernel_scale_is_explicit(self):
        paint=dict(type='linear',start=[0,0],end=[4,0],stops=[dict(offset=0,color=[255,0,0,255]),dict(offset=1,color=[0,0,255,255])])
        fx=[dict(basic.effect('gradient','overlay',paint),scale=3)]
        d=self.add(self.document(6,5,kind='vector'),[rectangle('art',[10,20,30,255],4,2,transform=[0,1,-1,0,4,1])]);d=self.effect(d,fx,fill_opacity=0)
        for scale in [1,2]:
            expected=[]
            for y in range(5*scale):
                for x in range(6*scale):
                    px,py=F(2*x+1,2*scale),F(2*y+1,2*scale)
                    if 2<=px<4 and 1<=py<5:
                        t=(py-1)/4;expected.append([1-t,F(0),t,F(1)])
                    else:expected.append([F(0)]*4)
            self.matches(self.pixels(d,scale),expected)

    def test_radial_freeform_pattern_and_linear_light_effect_colors(self):
        a,b=[240,40,90,128],[20,190,220,255]
        stops=[dict(offset=0,color=a),dict(offset=1,color=b)]
        cases=[(dict(type='radial',center=[2,.5],radius=2,stops=stops),[F(3,4),F(1,4),F(1,4),F(3,4)]),(dict(type='freeform',anchors=[dict(point=[.5,.5],color=a),dict(point=[3.5,.5],color=b)]),[F(0),F(1,5),F(4,5),F(1)])]
        for paint,amounts in cases:
            d=self.add(self.document(4,kind='vector'),[rectangle('art',[40,90,180,255],4)]);d=self.effect(d,[basic.effect('paint','overlay',paint)],fill_opacity=0)
            colors=[[F(lo,255)*(1-t)+F(hi,255)*t for lo,hi in zip(a,b)] for t in amounts]
            self.matches(self.pixels(d),[[v*c[3] for v in c[:3]]+[c[3]] for c in colors])
        paint=dict(type='pattern',width=2,height=1,rgba_hex=bytes(a+b).hex())
        self.matches(self.pixels(self.effect(d,[basic.effect('paint','overlay',paint)],fill_opacity=0)),[premul(c) for c in [a,b,a,b]])
        paint=dict(type='linear',start=[0,0],end=[4,0],space='linear_rgb',stops=[dict(offset=0,color=[0,0,0,255]),dict(offset=1,color=[255,255,255,255])])
        with localcontext() as ctx:
            ctx.prec=60
            vals=[F(Decimal('1.055')*(Decimal(2*x+1)/8)**(Decimal(5)/12)-Decimal('.055')) for x in range(4)]
        self.matches(self.pixels(self.effect(d,[basic.effect('paint','overlay',paint)],fill_opacity=0)),[[v,v,v,F(1)] for v in vals])

    def test_multiple_effects_category_order_disable_and_fractional_fill(self):
        d,source=self.source();fx=[dict(basic.effect('stroke','stroke',[210,100,40,128],radius=2),scale=.75,contour=[[0,0],[.5,.125],[1,1]]),basic.effect('overlay-a','overlay',[10,190,220,128]),dict(basic.effect('shadow-a','lit_shadow',[30,60,140,173],distance=1.5,sigma=.5),scale=.5),dict(basic.effect('overlay-b','overlay',[230,80,50,73]),contour=[[0,0],[.5,1],[1,.25]]),dict(basic.effect('shadow-b','shadow',[90,50,180,128],offset=[-.5,1],sigma=0),enabled=False)]
        self.matches(self.pixels(self.effect(d,fx,fill_opacity=.375)),evaluate(source,7,5,fx,fill=F(3,8)))

        fx[1],fx[3]=fx[3],fx[1]
        self.matches(self.pixels(self.effect(d,fx,fill_opacity=.375)),evaluate(source,7,5,fx,fill=F(3,8)))

    def test_nonmonotone_group_contour_keeps_knockout_footprint_above_alpha(self):
        e=dict(basic.effect('curve','overlay',[40,210,150,255]),contour=[[0,0],[.25,.75],[1,0]])
        items=[knockout.group('outer'),rectangle('old',[220,40,90,255],parent='outer'),knockout.group('styled',True,False,parent='outer',effects=[e]),rectangle('art',[50,90,200,255],parent='styled',opacity=.25)]
        d=self.add(self.document(kind='vector'),items);source=[F(v,255)*F(3,4) for v in [40,210,150]]+[F(3,4)]
        expected=knockout.replace(premul([220,40,90,255]),[F(0)]*4,source,F(3,4));self.matches(self.pixels(d),[expected])

    def test_artboard_uses_saved_light_and_local_effect_coordinates(self):
        fx=[basic.effect('light','lit_shadow',[20,80,180,173],distance=1,sigma=0)]
        items=[dict(id='board',transform=[1,0,0,1,4,0],content=dict(type='frame',frame=dict(role='artboard',width=4,height=3))),rectangle('art',[220,70,100,255],1,1,parent='board',transform=[1,0,0,1,1,1],effects=fx,fill_opacity=0)]
        d=self.add(self.document(8,3,kind='vector'),items);d=self.edit(d,[dict(op='global_light',light=dict(azimuth=180))])
        result=self.invoke(dict(command='artboard.export',document=d,format='png'))
        actual=editing.png_pixels(base64.b64decode(result['artifacts'][0]['artifact']['data']))[2]
        self.matches(actual,[premul([20,80,180,173]) if (x,y)==(2,1) else [F(0)]*4 for y in range(3) for x in range(4)])

    def test_scale_batch_preserves_geometry_and_is_atomic_on_limits_or_locks(self):
        d,source=self.source();fx=[basic.effect('shadow','lit_shadow',[0,0,0,128],distance=8,sigma=2),dict(basic.effect('outline','stroke',[255,80,0,255],radius=3),enabled=False)]
        d=self.effect(d,fx);before=copy.deepcopy(d)
        scaled=self.edit(d,[dict(op='effects_scale',ids=['art'],factor=1.5)])
        self.assertEqual(scaled['items'][0]['content'],d['items'][0]['content']);self.assertEqual([e['scale'] for e in scaled['items'][0]['effects']],[1.5,1.5])
        self.matches(self.pixels(scaled),evaluate(source,7,5,[dict(e,scale=1.5) for e in fx]))
        self.assertEqual(self.edit(d,[dict(op='effects_scale',ids=['art'],factor=100)],1)['code'],'INVALID_DOCUMENT');self.assertEqual(d,before)
        locked=self.edit(d,[dict(op='properties',id='art',locked=True)])
        self.assertEqual(self.edit(locked,[dict(op='effects_scale',ids=['art'],factor=2)],1)['code'],'LOCKED')
        for ids,factor in [(['art','art'],2),([],1),(['art'],0),(['art'],-1),(['art'],1025)]:self.assertEqual(self.edit(d,[dict(op='effects_scale',ids=ids,factor=factor)],1)['code'],'INVALID_OPERATION')

    def test_global_light_honors_dependent_locks_including_disabled_effects(self):
        d,_=self.source();fx=[dict(basic.effect('shared','lit_shadow',[0,0,0,255],distance=1,sigma=0),enabled=False)];d=self.effect(d,fx);locked=self.edit(d,[dict(op='properties',id='art',locked=True)])
        self.assertEqual(self.edit(locked,[dict(op='global_light',light=dict(azimuth=0))],1)['code'],'LOCKED')
        fx[0]['operator']['azimuth']=90;d=self.effect(d,fx);locked=self.edit(d,[dict(op='properties',id='art',locked=True)])
        self.assertEqual(self.edit(locked,[dict(op='global_light',light=dict(azimuth=0))])['global_light'],dict(azimuth=0))
        for angle in [-361,361]:self.assertEqual(self.edit(d,[dict(op='global_light',light=dict(azimuth=angle))],1)['code'],'INVALID_DOCUMENT')

    def test_invalid_contours_paints_scales_and_scaled_kernel_bounds(self):
        d,_=self.source();base=basic.effect('a','overlay',[20,70,190,255])
        for knots in [[[0,0]],[[.1,0],[1,1]],[[0,.1],[1,1]],[[0,0],[.5,.5],[.5,.7],[1,1]],[[0,0],[1,1.1]],[[0,0],[.9,1]]]:
            self.assertEqual(self.edit(d,[dict(op='effects',id='art',effects=[dict(base,contour=knots)])],1)['code'],'INVALID_DOCUMENT' if len(knots)>1 else 'RESOURCE_LIMIT')
        self.assertEqual(self.edit(d,[dict(op='effects',id='art',effects=[dict(base,contour=[[i/64,i/64] for i in range(65)])])],1)['code'],'RESOURCE_LIMIT')
        for e in [dict(base,scale=0),dict(base,scale=1025),dict(basic.effect('a','stroke',[0,0,0,255],radius=32),scale=1.001),dict(basic.effect('a','shadow',[0,0,0,255],offset=[256,0],sigma=0),scale=2),dict(basic.effect('a','lit_shadow',[0,0,0,255],distance=0,sigma=16),scale=2)]:
            self.assertEqual(self.edit(d,[dict(op='effects',id='art',effects=[e])],1)['code'],'INVALID_DOCUMENT')
        bad=dict(base,color=dict(type='linear',start=[0,0],end=[0,0],stops=[dict(offset=0,color=[0,0,0,255]),dict(offset=1,color=[255,255,255,255])]))
        self.assertEqual(self.edit(d,[dict(op='effects',id='art',effects=[bad])],1)['code'],'INVALID_DOCUMENT')
        for op in [dict(op='global_light',light=dict(azimuth=0,elevation=45)),dict(op='effects',id='art',effects=[dict(base,contour=[[0,0,0],[1,1,1]])])]:self.assertEqual(self.edit(d,[op],1)['code'],'INVALID_REQUEST')

    def test_extended_work_and_shared_paint_storage_budgets(self):
        fx=[dict(basic.effect('s','stroke',[0,0,0,255],radius=1),scale=32)]
        d=self.add(self.document(512,512),[layer('art',[[0,0,0,255]],visible=False)]);self.assertEqual(self.invoke(dict(command='document.render',document=self.effect(d,fx)),1)['code'],'RESOURCE_LIMIT')
        # Stored effect paint participates in the same document inline-pixel
        # budget as ordinary content, even if every effect is disabled.
        tile=dict(type='pattern',width=64,height=64,rgba_hex='000000ff'*4096)
        fx=[dict(basic.effect(str(i),'overlay',tile),enabled=False) for i in range(8)]
        items=[dict(id=str(i),effects=fx,visible=False,content=dict(type='raster',width=1,height=1,rgba_hex='000000ff')) for i in range(3)]
        error=self.edit(self.document(),[dict(op='add',item=i) for i in items],1);self.assertEqual(error['code'],'RESOURCE_LIMIT');self.assertIn('Inline pixel storage',error['message'])

    def test_light_contours_and_paints_persist_mcp_history_inspect_and_diff(self):
        d,_=self.source();fx=[dict(basic.effect('s','lit_shadow',[30,80,190,128],distance=1,sigma=.5),scale=1.5,contour=[[0,0],[.5,.25],[1,1]])]
        ops=[dict(op='global_light',light=dict(azimuth=30)),dict(op='effects',id='art',effects=fx)];changed=self.edit(d,ops)
        info=self.invoke(dict(command='document.inspect',document=changed));self.assertEqual(info['global_light'],dict(azimuth=30));self.assertEqual(info['items'][0]['effects'][0]['scale'],1.5)
        diff=self.invoke(dict(command='document.diff',before=d,after=changed));self.assertIn('global_light',[v['field'] for v in diff['metadata']]);self.assertIn('effects',diff['items'][0]['fields'])
        snapshot=json.loads(self.invoke(dict(command='document.export',document=changed,format='snapshot'))['data']);self.assertEqual(self.pixels(snapshot),self.pixels(changed))
        with tempfile.TemporaryDirectory() as root:
            args=dict(session_root=root,session_id='extended-effects');c=Client();c.initialize()
            try:
                c.success('session.create',**args,request_id='create',document=d);action=dict(type='edit',operations=ops)
                result=c.success('session.apply',**args,request_id='edit',expected_revision=0,action=action);self.assertEqual(result['document']['items'],changed['items']);self.assertEqual(result['document']['global_light'],dict(azimuth=30))
                self.assertTrue(c.success('session.apply',**args,request_id='edit',expected_revision=0,action=action)['replayed'])
                undone=c.success('session.apply',**args,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'];self.assertNotIn('global_light',undone);self.assertEqual(undone['items'],d['items'])
                redone=c.success('session.apply',**args,request_id='redo',expected_revision=2,action=dict(type='redo'))['document'];self.assertEqual(self.pixels(redone),self.pixels(changed));c.success('session.verify',**args)
            finally:c.close()


if __name__=='__main__':unittest.main()
