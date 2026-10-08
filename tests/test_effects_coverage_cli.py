"""Independent scalar fields, coverage hashing and decorated-alpha composition."""
import base64
import copy
from decimal import Decimal,localcontext
from fractions import Fraction as F
import hashlib
import json
import math
import tempfile
import unittest
import xml.etree.ElementTree as ET
import test_editing_cli as editing
import test_blending_cli as blending
from test_blending_cli import MODES,premul,over,straight
from test_mcp import Client


def effect(id,type,color,**params):return dict(id=id,operator=dict(type=type,**params),color=color)
def layer(id,colors,w,**kw):return dict(id=id,content=dict(type='raster',width=w,height=len(colors)//w,rgba_hex=bytes(v for p in colors for v in p).hex()),**kw)
def get(a,w,h,x,y):return a[y*w+x] if 0<=x<w and 0<=y<h else F(0)
def sample(a,w,h,x,y):
    left,top=math.floor(x),math.floor(y);fx=x-left;fy=y-top
    return sum(get(a,w,h,left+i,top+j)*wx*wy for i,wx in [(0,1-fx),(1,fx)] for j,wy in [(0,1-fy),(1,fy)])
def field(alpha,w,h,operator,scale=1):
    kind=operator['type']
    if kind=='stroke':
        r=operator['radius']*scale;p=operator.get('position','outside');out=[]
        for y in range(h):
            for x in range(w):
                values=[get(alpha,w,h,i,j) for j in range(y-r,y+r+1) for i in range(x-r,x+r+1) if math.hypot(x-i,y-j)<=r]
                a=get(alpha,w,h,x,y)
                out.append(max(values)-a if p=='outside' else a-min(values) if p=='inside' else max(values)-min(values))
        return out
    if kind=='shadow':
        sigma=F(str(operator['sigma']))*scale;r=math.ceil(3*sigma)
        with localcontext() as ctx:
            ctx.prec=55
            weights=[(-(Decimal(i)**2)/(2*(Decimal(sigma.numerator)/Decimal(sigma.denominator))**2)).exp() for i in range(-r,r+1)] if sigma else [Decimal(1)]
            total=sum(weights);weights=[F(v/total) for v in weights]
        # Direct full 2D convolution, independently of the engine's two passes.
        blurred=[sum(get(alpha,w,h,x+dx,y+dy)*weights[dx+r]*weights[dy+r] for dy in range(-r,r+1) for dx in range(-r,r+1)) for y in range(h) for x in range(w)]
        dx,dy=[F(str(v))*scale for v in operator['offset']]
        return [sample(blurred,w,h,F(x)-dx,F(y)-dy) for y in range(h) for x in range(w)]
    raise AssertionError(kind)
def decorated(source,w,h,effects,fill=F(1),scale=1):
    alpha=[p[3] for p in source];behind=[[F(0)]*4 for _ in source]
    for e in effects:
        if e.get('enabled',True) and e['operator']['type']=='shadow':
            a=field(alpha,w,h,e['operator'],scale);opacity=F(str(e.get('opacity',1)))
            behind=[over(b,premul(e['color']),v*opacity) for b,v in zip(behind,a)]
    content=[[v*fill for v in p] for p in source]
    for e in effects:
        if e.get('enabled',True) and e['operator']['type']=='overlay':
            strength=F(e['color'][3],255)*F(str(e.get('opacity',1)))
            color=[F(v,255) for v in e['color'][:3]]+[F(1)]
            content=[[v*(1-strength)+a*strength*c for v,c in zip(p,color)] for p,a in zip(content,alpha)]
    result=[over(b,c) for b,c in zip(behind,content)]
    for e in effects:
        if e.get('enabled',True) and e['operator']['type']=='stroke':
            a=field(alpha,w,h,e['operator'],scale);opacity=F(str(e.get('opacity',1)))
            result=[over(b,premul(e['color']),v*opacity) for b,v in zip(result,a)]
    return result
def threshold(seed,x,y):
    message=b'inkbolt.coverage.v1\0'+seed.to_bytes(4,'little')+math.floor(x).to_bytes(8,'little',signed=True)+math.floor(y).to_bytes(8,'little',signed=True)
    code=int.from_bytes(hashlib.sha256(message).digest()[:4],'little')
    return F(2*code+1,2**33)


class EffectsCoverageTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    edit=blending.BlendingTests.edit
    add=blending.BlendingTests.add
    document=blending.BlendingTests.document
    matches=blending.BlendingTests.matches
    def pixels(self,d,scale=1):return editing.png_pixels(base64.b64decode(self.invoke(dict(command='document.export',document=d,format='png',scale=scale))['data']))[2]
    def chart(self,w=7,h=5):return [[30+20*x,20+35*y,190,255 if 2<=x<5 and 1<=y<4 else 73 if x==1 and y==2 else 0] for y in range(h) for x in range(w)]
    def source(self,colors,w):return self.add(self.document(w,len(colors)//w),[layer('art',colors,w)])
    def settings(self,d,effects=None,**props):
        ops=[]
        if effects is not None:ops.append(dict(op='effects',id='art',effects=effects))
        if props:ops.append(dict(op='properties',id='art',**props))
        return self.edit(d,ops)

    def test_stroke_positions_full_boundaries_holes_and_transparency(self):
        colors=self.chart();colors[2*7+3][3]=0;d=self.source(colors,7)
        for position in ('outside','inside','center'):
            for radius in (0,1,2):
                e=effect('outline','stroke',[230,45,20,173],radius=radius,position=position)
                changed=self.settings(d,[e]);expected=decorated([premul(p) for p in colors],7,5,[e])
                self.matches(self.pixels(changed),expected);self.assertEqual(changed['items'][0]['content'],d['items'][0]['content'])
        # Euclidean radius one excludes diagonal neighbors, radius two includes them.
        colors=[[80,170,230,255] if (x,y)==(2,2) else [3,7,11,0] for y in range(5) for x in range(5)]
        d=self.source(colors,5);e=effect('ring','stroke',[220,20,80,255],radius=1)
        self.assertEqual(self.pixels(self.settings(d,[e]))[(1*5+1)*4+3],0)
        e['operator']['radius']=2;self.assertEqual(self.pixels(self.settings(d,[e]))[(1*5+1)*4+3],255)

    def test_shadow_gaussian_fractional_offsets_and_source_alpha(self):
        colors=self.chart();d=self.source(colors,7)
        for sigma,offset in [(0,[1,1]),(0,[-1.25,.5]),(.65,[1.5,-.25]),(1.1,[0,0]),(1e-200,[0,0])]:
            e=effect('shadow','shadow',[25,45,100,173],sigma=sigma,offset=offset)
            expected=decorated([premul(p) for p in colors],7,5,[e],F(3,8))
            changed=self.settings(d,[e],fill_opacity=.375)
            self.matches(self.pixels(changed),expected)
        self.assertEqual(self.pixels(d),self.pixels(self.source(colors,7)))

    def test_fill_and_overall_opacity_independently_control_effects(self):
        colors=self.chart();d=self.source(colors,7);effects=[effect('shadow','shadow',[15,20,30,200],sigma=0,offset=[2,1]),effect('stroke','stroke',[230,90,35,255],radius=1)]
        for fill,opacity in [(0,1),(.375,1),(1,.375),(.5,.5),(0,0)]:
            changed=self.settings(d,effects,fill_opacity=fill,opacity=opacity)
            expected=decorated([premul(p) for p in colors],7,5,effects,F(str(fill)))
            expected=[[v*F(str(opacity)) for v in p] for p in expected]
            self.matches(self.pixels(changed),expected)
        empty=self.settings(d,effects,fill_opacity=0)
        self.assertGreater(sum(self.pixels(empty)[3::4]),0)
        self.assertNotEqual(self.pixels(self.settings(d,effects,fill_opacity=.375)),self.pixels(self.settings(d,effects,opacity=.375)))
        self.assertEqual(self.pixels(self.settings(d,[],fill_opacity=.375)),self.pixels(self.settings(d,[],opacity=.375)))

    def test_overlay_conditional_alpha_multiple_effect_order_and_disable(self):
        colors=self.chart();d=self.source(colors,7)
        overlays=[effect('a','overlay',[210,40,60,128]),effect('b','overlay',[30,170,100,73])]
        overlays[1]['opacity']=.625
        for fill in [0,.375,1]:
            for effects in [overlays,list(reversed(overlays)),[dict(overlays[0],enabled=False),overlays[1]]]:
                expected=decorated([premul(p) for p in colors],7,5,effects,F(str(fill)))
                actual=self.pixels(self.settings(d,effects,fill_opacity=fill));self.matches(actual,expected)
                if fill==1:self.assertEqual(list(actual[3::4]),[p[3] for p in colors])
        self.assertNotEqual(self.pixels(self.settings(d,overlays)),self.pixels(self.settings(d,list(reversed(overlays)))))
        # Category order is fixed; the declared list orders effects within a category.
        allfx=overlays+[effect('s','shadow',[5,10,30,100],sigma=0,offset=[1,1]),effect('r','stroke',[240,200,20,173],radius=1)]
        self.matches(self.pixels(self.settings(d,allfx)),decorated([premul(p) for p in colors],7,5,allfx))

    def test_fill_and_effect_composites_use_all_color_modes_over_partial_alpha(self):
        colors=[[190,80,20,a] for a in (0,1,73,128,255)];back=[[40,130,220,a] for a in (128,0,255,73,173)]
        effects=[effect('tint','overlay',[80,220,140,73]),effect('shadow','shadow',[90,20,50,173],sigma=0,offset=[1,0])]
        source=decorated([premul(p) for p in colors],5,1,effects,F(3,8))
        for mode in MODES:
            d=self.add(self.document(5),[layer('b',back,5),layer('art',colors,5,fill_opacity=.375,opacity=.625,blend=mode,effects=effects)])
            self.matches(self.pixels(d),[over(premul(b),s,F(5,8),mode) for b,s in zip(back,source)])

    def test_filter_then_effect_then_mask_and_opacity_order(self):
        colors=self.chart();d=self.source(colors,7);m=[255 if x<4 else 73 for y in range(5) for x in range(7)]
        f=dict(id='blur',operator=dict(type='box',radius=1));e=effect('s','shadow',[20,40,80,173],sigma=0,offset=[1,.5])
        raw=[premul(p) for p in colors]
        blurred=[[sum((raw[yy*7+xx][c] if 0<=xx<7 and 0<=yy<5 else 0) for yy in range(y-1,y+2) for xx in range(x-1,x+2))/9 for c in range(4)] for y in range(5) for x in range(7)]
        d=self.edit(d,[dict(op='filters',id='art',filters=[f]),dict(op='effects',id='art',effects=[e]),dict(op='mask',id='art',mask=dict(width=7,height=5,gray_hex=bytes(m).hex())),dict(op='properties',id='art',fill_opacity=.375,opacity=.625)])
        expected=decorated(blurred,7,5,[e],F(3,8));self.matches(self.pixels(d),[[v*F(5*k,8*255) for v in p] for p,k in zip(expected,m)])
        self.assertEqual(self.edit(d,[dict(op='mask_apply',id='art')],1)['code'],'UNSUPPORTED')

    def test_isolated_group_fill_effects_and_clipping_members(self):
        first=[[40,120,210,a] for a in (255,73,0,128)];second=[[200,80,50,a] for a in (128,255,73,0)]
        e=effect('edge','stroke',[210,200,60,173],radius=1)
        d=self.add(self.document(4),[dict(id='art',fill_opacity=.375,effects=[e],content=dict(type='group')),layer('a',first,4,parent='art'),layer('b',second,4,parent='art')])
        source=[over(premul(a),premul(b)) for a,b in zip(first,second)]
        self.matches(self.pixels(d),decorated(source,4,1,[e],F(3,8)))
        self.assertEqual(self.edit(d,[dict(op='ungroup',id='art')],1)['code'],'UNSUPPORTED')
        srcfx=[effect('tint','overlay',[100,200,20,128])]
        d=self.add(self.document(4),[layer('base',first,4,fill_opacity=.625,effects=[e]),layer('member',second,4,clip_to='base',fill_opacity=.375,effects=srcfx)])
        members=decorated([premul(p) for p in second],4,1,srcfx,F(3,8));clipped=[]
        for p,s in zip(first,members):
            base=premul(p);b=straight(base);color=straight(s)
            clipped.append([((1-s[3])*x+s[3]*y)*base[3] for x,y in zip(b,color)]+[base[3]])
        self.matches(self.pixels(d),decorated(clipped,4,1,[e],F(5,8)))

    def test_dissolve_exact_hash_alpha_endpoints_seed_and_monotonic_density(self):
        colors=[[200,50,110,255]]*(32*16);d=self.source(colors,32);sets=[]
        for amount in [0,.125,.375,.625,.875,1]:
            changed=self.settings(d,fill_opacity=amount,coverage=dict(type='dissolve',seed=9876));actual=self.pixels(changed);expected=[];selected=set()
            for y in range(16):
                for x in range(32):
                    keep=F(str(amount))>threshold(9876,x,y);expected+=([200,50,110,255] if keep else [0]*4)
                    if keep:selected.add(y*32+x)
            self.assertEqual(actual,bytes(expected));sets.append(selected)
            self.assertEqual(actual,self.pixels(changed))
        self.assertTrue(all(a<=b for a,b in zip(sets,sets[1:])))
        a=self.settings(d,opacity=.5,coverage=dict(type='dissolve',seed=0));b=self.settings(d,opacity=.5,coverage=dict(type='dissolve',seed=4294967295))
        self.assertNotEqual(self.pixels(a),self.pixels(b));self.assertTrue(set(self.pixels(a)[3::4])<={0,255})

    def test_dissolve_after_source_alpha_masks_fill_opacity_and_all_blends(self):
        colors=[[220,70,30,a] for a in (0,1,73,128,255)]*8;back=[[30,90,200,a] for a in (255,128,73,0,191)]*8;m=[255,73,128,255,255]*8
        for mode in MODES:
            d=self.add(self.document(40),[layer('b',back,40),layer('art',colors,40,fill_opacity=.625,opacity=.875,blend=mode,coverage=dict(type='dissolve',seed=11),mask=dict(width=40,height=1,gray_hex=bytes(m).hex()))])
            expected=[]
            for x,(a,b,k) in enumerate(zip(colors,back,m)):
                alpha=F(a[3]*k,255**2)*F(5,8)*F(7,8);s=premul(a[:3]+[255]) if alpha>threshold(11,x,0) else [F(0)]*4
                expected.append(over(premul(b),s,mode=mode))
            self.matches(self.pixels(d),expected)

    def test_dissolve_local_coordinates_translation_rotation_reflection_export_scale(self):
        colors=[[100,180,230,128]]*12
        for matrix,w,h,local in [([1,0,0,1,2,1],8,6,lambda x,y:(x-2,y-1)),([0,1,-1,0,4,1],7,7,lambda x,y:(y-1,4-x)),([-1,0,0,1,6,1],8,6,lambda x,y:(6-x,y-1))]:
            d=self.add(self.document(w,h),[layer('art',colors,4,transform=matrix,coverage=dict(type='dissolve',seed=4))])
            for scale in (1,2):
                expected=[]
                for y in range(h*scale):
                    for x in range(w*scale):
                        lx,ly=local(F(2*x+1,2*scale),F(2*y+1,2*scale));keep=0<=lx<4 and 0<=ly<3 and F(128,255)>threshold(4,lx,ly)
                        expected+=([100,180,230,255] if keep else [0]*4)
                self.assertEqual(self.pixels(d,scale),bytes(expected))

    def test_dissolve_decoration_signed_cells_and_clipped_base_alpha(self):
        colors=[[220,80,40,255]]*4;e=effect('shadow','shadow',[30,60,120,128],sigma=0,offset=[-3,-1])
        d=self.add(self.document(8,4),[layer('art',colors,2,transform=[1,0,0,1,4,2],effects=[e],fill_opacity=0,coverage=dict(type='dissolve',seed=9))])
        expected=[]
        for y in range(4):
            for x in range(8):
                keep=1<=x<3 and 1<=y<3 and F(128,255)>threshold(9,F(2*x+1,2)-4,F(2*y+1,2)-2)
                expected+=([30,60,120,255] if keep else [0]*4)
        self.assertEqual(self.pixels(d),bytes(expected))
        base=[[40,100,200,a] for a in (0,73,128,255)]*8;src=[[230,60,90,128]]*32
        d=self.add(self.document(32),[layer('b',base,32),layer('s',src,32,clip_to='b',coverage=dict(type='dissolve',seed=42))]);expected=[]
        for x,b in enumerate(base):expected.append(premul((src[x][:3] if F(128,255)>threshold(42,x,0) else b[:3])+[b[3]]))
        self.matches(self.pixels(d),expected)

    def test_export_scaling_effect_units_and_explicit_canvas_policy(self):
        colors=[[80,180,230,255] if (x,y)==(2,2) else [10,20,30,0] for y in range(5) for x in range(5)];d=self.source(colors,5)
        effects=[effect('s','shadow',[20,30,70,173],sigma=0,offset=[.5,1]),effect('r','stroke',[230,80,30,255],radius=1)]
        d=self.settings(d,effects,fill_opacity=.625)
        for scale in (1,2):
            enlarged=[premul(colors[(y//scale)*5+x//scale]) for y in range(5*scale) for x in range(5*scale)]
            self.matches(self.pixels(d,scale),decorated(enlarged,5*scale,5*scale,effects,F(5,8),scale))
        action=dict(type='scale',width=10,height=10,sampling='nearest')
        self.assertEqual(self.edit(d,[dict(op='canvas',action=action)],1)['code'],'UNSUPPORTED')
        action['effect_policy']='preserve_parameters';resized=self.edit(d,[dict(op='canvas',action=action)])
        self.assertEqual(resized['items'][0]['effects'],d['items'][0]['effects'])

    def test_atomic_validation_locks_non_drawables_and_svg_losses(self):
        d=self.source(self.chart(),7);original=copy.deepcopy(d);e=effect('a','overlay',[20,90,160,128])
        for value in (-.1,1.01):self.assertEqual(self.edit(d,[dict(op='properties',id='art',fill_opacity=value)],1)['code'],'INVALID_DOCUMENT')
        bad=[effect('bad','shadow',[1,2,3,255],sigma=-1,offset=[0,0]),effect('bad','stroke',[1,2,3,255],radius=33),effect('bad','shadow',[1,2,3,255],sigma=1,offset=[257,0])]
        for fx in bad:
            self.assertEqual(self.edit(d,[dict(op='properties',id='art',fill_opacity=.5),dict(op='effects',id='art',effects=[fx])],1)['code'],'INVALID_DOCUMENT');self.assertEqual(d,original)
        self.assertEqual(self.edit(d,[dict(op='effects',id='art',effects=[e,e])],1)['code'],'INVALID_DOCUMENT')
        locked=self.edit(d,[dict(op='properties',id='art',locked=True)])
        for op in [dict(op='effects',id='art',effects=[e]),dict(op='properties',id='art',fill_opacity=.5),dict(op='properties',id='art',coverage=dict(type='dissolve',seed=1)),dict(op='properties',id='art',locked=False,fill_opacity=.5)]:
            self.assertEqual(self.edit(locked,[op],1)['code'],'LOCKED')
        for content in [dict(type='group',isolated=False),dict(type='adjustment',adjustment=dict(operators=[dict(type='invert')]))]:
            for settings in [dict(fill_opacity=.5),dict(effects=[e]),dict(coverage=dict(type='dissolve',seed=1))]:
                self.assertEqual(self.edit(d,[dict(op='add',item=dict(id='bad',content=content,**settings))],1)['code'],'UNSUPPORTED')
        for coverage in [dict(type='dissolve',seed=-1),dict(type='dissolve',seed=2**32),dict(type='dissolve'),dict(type='smooth',seed=1)]:
            self.assertEqual(self.edit(d,[dict(op='properties',id='art',coverage=coverage)],1)['code'],'INVALID_REQUEST')
        vector=self.add(self.document(kind='vector'),[dict(id='art',opacity=.5,fill_opacity=.375,content=dict(type='vector',geometry=dict(shape='rect',x=0,y=0,width=1,height=1),fill=[20,40,80,255]))])
        exported=self.invoke(dict(command='document.export',document=vector,format='svg'));svg=exported['data'];root=ET.fromstring(svg)
        self.assertTrue(any('fill opacity' in loss for loss in exported['losses']))
        group=next(n for n in root.iter() if n.attrib.get('id')=='art');self.assertEqual(float(group.attrib['opacity']),.1875)
        for changed in [self.settings(vector,[e]),self.settings(vector,coverage=dict(type='dissolve',seed=4))]:self.assertEqual(self.invoke(dict(command='document.export',document=changed,format='svg'),1)['code'],'UNSUPPORTED')

    def test_item_document_work_memory_and_artboard_budgets(self):
        d=self.source([[30,90,160,255]],1);e=effect('a','overlay',[20,90,160,128])
        self.assertEqual(self.edit(d,[dict(op='effects',id='art',effects=[dict(e,id=str(i)) for i in range(9)])],1)['code'],'RESOURCE_LIMIT')
        items=[layer(str(i),[[0]*4],1,visible=False,effects=[dict(e,id=str(j),enabled=False) for j in range(8)]) for i in range(9)]
        self.assertEqual(self.edit(self.document(),[dict(op='add',item=i) for i in items],1)['code'],'RESOURCE_LIMIT')
        huge=self.add(self.document(512,512),[layer('art',[[30,90,160,255]],1,visible=False,effects=[effect('r','stroke',[0,0,0,255],radius=32)])])
        self.assertEqual(self.invoke(dict(command='document.render',document=huge),1)['code'],'RESOURCE_LIMIT')
        items=[dict(id='a',content=dict(type='group')),dict(id='b',parent='a',content=dict(type='group')),dict(id='c',parent='b',content=dict(type='group')),layer('art',[[30,90,160,255]],1,parent='c',effects=[e])]
        huge=self.add(self.document(1024,768),items);error=self.invoke(dict(command='document.render',document=huge),1);self.assertEqual(error['code'],'RESOURCE_LIMIT');self.assertIn('memory',error['message'])
        boards=[]
        for i in range(8):boards += [dict(id=f'b{i}',content=dict(type='frame',frame=dict(role='artboard',width=256,height=256))),layer(f'p{i}',[[30,90,160,255]],1,parent=f'b{i}',effects=[effect('r','stroke',[0,0,0,255],radius=8)])]
        d=self.add(self.document(256,256),boards);self.assertEqual(self.invoke(dict(command='artboard.export',document=d,format='png'),1)['code'],'RESOURCE_LIMIT')

    def test_edit_inspect_diff_snapshot_and_mcp_durable_history(self):
        d=self.source(self.chart(),7);e=effect('edge','stroke',[220,100,30,255],radius=1)
        ops=[dict(op='effects',id='art',effects=[e]),dict(op='properties',id='art',fill_opacity=.375,coverage=dict(type='dissolve',seed=9))]
        changed=self.edit(d,ops);record=self.invoke(dict(command='document.inspect',document=changed))['items'][0]
        self.assertEqual(record['fill_opacity'],.375);self.assertEqual(record['coverage'],dict(type='dissolve',seed=9));self.assertEqual(record['effects'][0]['id'],'edge')
        delta=self.invoke(dict(command='document.diff',before=d,after=changed));self.assertTrue({'fill_opacity','effects','coverage'}<=set(delta['items'][0]['fields']))
        snapshot=self.invoke(dict(command='document.export',document=changed,format='snapshot'))
        saved=self.invoke(dict(command='document.validate',document=json.loads(snapshot['data'])));self.assertEqual(saved,changed);self.assertEqual(self.pixels(saved),self.pixels(changed))
        with tempfile.TemporaryDirectory() as root:
            args=dict(session_root=root,session_id='appearance');c=Client();c.initialize();action=dict(type='edit',operations=ops)
            try:
                c.success('session.create',**args,request_id='create',document=d)
                result=c.success('session.apply',**args,request_id='decorate',expected_revision=0,action=action)
                self.assertEqual(result['document']['items'],changed['items']);c.success('session.apply',**args,request_id='save',expected_revision=1,action=dict(type='snapshot',name='decorated'))
            finally:c.close()
            c=Client();c.initialize()
            try:
                replay=c.success('session.apply',**args,request_id='decorate',expected_revision=0,action=action);self.assertTrue(replay['replayed']);self.assertEqual(replay['receipt'],result['receipt']);self.assertEqual(replay['document'],result['document'])
                reread=c.success('session.read',**args,snapshot='decorated')['document'];self.assertEqual(self.pixels(reread),self.pixels(changed))
                undo=c.success('session.apply',**args,request_id='undo',expected_revision=2,action=dict(type='undo'))['document'];self.assertEqual(self.pixels(undo),self.pixels(d));self.assertEqual(undo['items'],d['items']);c.success('session.verify',**args)
            finally:c.close()

    def test_coverage_effects_capabilities_and_legacy_defaults(self):
        c=self.invoke(dict(command='capabilities'));self.assertTrue(c['blending']['fill_opacity']);self.assertTrue(c['blending']['dissolve']);self.assertTrue(c['blending']['knockout'])
        self.assertEqual(c['coverage']['modes'],['smooth','dissolve']);self.assertEqual(c['layer_effects']['operators'],['shadow','lit_shadow','stroke','overlay'])
        d=self.source([[20,40,80,128]],1)
        for key in ('fill_opacity','coverage','effects'):self.assertNotIn(key,d['items'][0])
        same=self.settings(d,[],fill_opacity=1,coverage=dict(type='smooth'));self.assertEqual(same['items'],d['items']);self.assertEqual(self.pixels(same),self.pixels(d))


if __name__=='__main__':unittest.main()
