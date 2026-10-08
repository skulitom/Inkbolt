"""Independent exact-rational color algebra and full compositing contexts.

The reference keeps colors/alpha rational, uses 60-digit square roots for soft
light, and partitions source-over into three disjoint coverage regions. It does
not call the engine's blend evaluator or derive expected bytes from renders.
"""
import base64
import copy
from decimal import Decimal, localcontext
from fractions import Fraction as F
import json
import random
import tempfile
import unittest
import test_editing_cli as editing
from test_mcp import Client

MODES = ('normal multiply screen darken lighten color_burn color_dodge overlay '
         'hard_light soft_light difference exclusion hue saturation color luminosity '
         'linear_burn linear_dodge vivid_light linear_light pin_light hard_mix '
         'subtract divide darker_color lighter_color').split()


def clamp(v): return max(F(0), min(F(1), v))
def luminance(c): return sum(v*w for v,w in zip(c, (F(30,100), F(59,100), F(11,100))))
def saturation(c): return max(c)-min(c)
def setsat(c, amount):
    order=sorted(range(3), key=lambda i:c[i]);lo,mid,hi=order;result=[F(0)]*3
    if c[hi]!=c[lo]:
        result[mid]=(c[mid]-c[lo])*amount/(c[hi]-c[lo]);result[hi]=amount
    return result
def setlum(c, amount):
    d=amount-luminance(c);c=[v+d for v in c]
    low,high=min(c),max(c)
    if low<0:c=[amount+(v-amount)*amount/(amount-low) for v in c]
    if high>1:c=[amount+(v-amount)*(1-amount)/(high-amount) for v in c]
    return c


def channel(b,s,mode):
    if mode=='normal':return s
    if mode=='multiply':return b*s
    if mode=='screen':return 1-(1-b)*(1-s)
    if mode=='darken':return min(b,s)
    if mode=='lighten':return max(b,s)
    if mode=='color_burn':return F(1) if b==1 else F(0) if s==0 else max(F(0),(b+s-1)/s)
    if mode=='color_dodge':return F(0) if b==0 else F(1) if s==1 else min(F(1),b/(1-s))
    if mode=='overlay':return channel(s,b,'hard_light')
    if mode=='hard_light':return channel(b,2*s,'multiply') if s<=F(1,2) else channel(b,2*s-1,'screen')
    if mode=='soft_light':
        if s<=F(1,2):return b*b+(2*s)*b*(1-b)
        with localcontext() as ctx:
            ctx.prec=60
            d=16*b**3-12*b*b+4*b if b<=F(1,4) else F((Decimal(b.numerator)/Decimal(b.denominator)).sqrt())
        return 2*(1-s)*b+(2*s-1)*d
    if mode=='difference':return abs(b-s)
    if mode=='exclusion':return b*(1-s)+s*(1-b)
    if mode=='linear_burn':return max(F(0),b+s-1)
    if mode=='linear_dodge':return min(F(1),b+s)
    if mode=='vivid_light':return channel(b,2*s,'color_burn') if s<=F(1,2) else channel(b,2*s-1,'color_dodge')
    if mode=='linear_light':return clamp(b+2*s-1)
    if mode=='pin_light':return min(b,2*s) if s<=F(1,2) else max(b,2*s-1)
    if mode=='hard_mix':return F(channel(b,s,'vivid_light')>=F(1,2))
    if mode=='subtract':return max(F(0),b-s)
    if mode=='divide':return F(1) if s==0 else min(F(1),b/s)
    raise AssertionError(mode)


def mix(b,s,mode):
    if mode=='hue':return setlum(setsat(s,saturation(b)),luminance(b))
    if mode=='saturation':return setlum(setsat(b,saturation(s)),luminance(b))
    if mode=='color':return setlum(s,luminance(b))
    if mode=='luminosity':return setlum(b,luminance(s))
    if mode=='darker_color':return s if sum(s)<sum(b) else b
    if mode=='lighter_color':return s if sum(s)>sum(b) else b
    return [channel(a,z,mode) for a,z in zip(b,s)]


def premul(p):return [F(c*p[3],65025) for c in p[:3]]+[F(p[3],255)]
def straight(p):return [v/p[3] for v in p[:3]] if p[3] else [F(0)]*3
def over(b,s,opacity=F(1),mode='normal'):
    cb,cs=straight(b),straight(s);a,t=b[3],s[3]*opacity
    overlap=a*t;source_only=(1-a)*t;back_only=a*(1-t)
    color=mix(cb,cs,mode)
    return [source_only*cs[i]+back_only*cb[i]+overlap*color[i] for i in range(3)]+[overlap+source_only+back_only]
def encoded(p):
    if p[3]*255<F(1,2):return [F(0)]*4
    return [v*255 for v in straight(p)]+[p[3]*255]
def layer(id,colors,**kw):
    return dict(id=id,content=dict(type='raster',width=len(colors),height=1,rgba_hex=bytes(v for p in colors for v in p).hex()),**kw)
def rectangle(id,color,w=1,h=1,**kw):
    return dict(id=id,content=dict(type='vector',geometry=dict(shape='rect',x=0,y=0,width=w,height=h),fill=color),**kw)
def mask(values):return dict(width=len(values),height=1,gray_hex=bytes(values).hex())


class BlendingTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def document(self,w=1,h=1,kind='raster'):
        return self.invoke(dict(command='document.create',id='blending',kind=kind,width=w,height=h))
    def edit(self,d,ops,expected=0):
        r=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=ops),expected)
        return r if expected else r['document']
    def add(self,d,items):return self.edit(d,[dict(op='add',item=i) for i in items])
    def pixels(self,d):return editing.png_pixels(base64.b64decode(self.invoke(dict(command='document.export',document=d,format='png'))['data']))[2]
    def matches(self,actual,pixels):
        ideal=[v for p in pixels for v in encoded(p)];self.assertEqual(len(actual),len(ideal))
        for i,(a,v) in enumerate(zip(actual,ideal)):
            v=max(F(0),min(F(255),v));nearest=int(v+F(1,2))
            if a!=nearest:
                # Only a half-byte within 1e-8 channel units admits its two
                # neighboring bytes; this is never a blanket one-byte tolerance.
                self.assertLessEqual(abs(float(v)-(int(v)+.5)),1e-8,(i,a,float(v)))
                self.assertIn(a,(int(v),int(v)+1),(i,a,float(v)))

    def chart(self):
        rng=random.Random(8137);pairs=[]
        points=(0,1,63,64,127,128,191,254,255)
        for b in points:
            for s in points:pairs.append(([b,(3*b)%256,255-b,255],[s,255-s,(7*s)%256,255]))
        pairs += [([rng.randrange(256) for _ in range(3)]+[255],[rng.randrange(256) for _ in range(3)]+[255]) for _ in range(240)]
        # Gray, tied extrema, primaries, and RGB-sum ties are deliberately kept.
        colors=[[0,0,0],[255,255,255],[128,128,128],[255,0,0],[0,255,0],[0,0,255],[255,255,0],[90,90,210],[210,90,90]]
        pairs += [(b+[255],s+[255]) for b in colors for s in colors]
        pairs += [([i,255-i,0,255],[255-i,i,0,255]) for i in range(256)]
        return pairs

    def test_all_families_exact_color_grid_and_nonlinear_boundaries(self):
        pairs=self.chart();b,s=zip(*pairs)
        for mode in MODES:
            with self.subTest(mode=mode):
                d=self.add(self.document(len(b)),[layer('b',b),layer('s',s,blend=mode)])
                self.matches(self.pixels(d),[over(premul(x),premul(y),mode=mode) for x,y in pairs])

    def test_all_families_source_over_partial_alpha_opacity_and_mask(self):
        pairs=self.chart();alphas=(0,1,73,128,254,255);b=[];s=[];m=[]
        for i,(x,y) in enumerate(pairs):
            b.append(x[:3]+[alphas[i%6]]);s.append(y[:3]+[alphas[(i//6)%6]]);m.append((0,73,128,255)[i%4])
        for mode in MODES:
            with self.subTest(mode=mode):
                d=self.add(self.document(len(b)),[layer('b',b),layer('s',s,blend=mode,opacity=.625,mask=mask(m))])
                self.matches(self.pixels(d),[over(premul(x),premul(y),F(5*k,8*255),mode) for x,y,k in zip(b,s,m)])
                self.assertEqual(d['items'][1]['content']['rgba_hex'],bytes(v for p in s for v in p).hex())

    def test_vector_isolated_and_pass_through_groups_use_same_modes(self):
        b=[35,190,225,173];s=[200,75,115,131]
        for mode in MODES:
            for isolated in (False,True):
                d=self.add(self.document(kind='vector'),[rectangle('b',b),dict(id='g',opacity=.375,content=dict(type='group',isolated=isolated)),rectangle('s',s,parent='g',blend=mode)])
                before=premul(b)
                if isolated:expected=over(before,premul(s),F(3,8))
                else:
                    after=over(before,premul(s),mode=mode);expected=[x+F(3,8)*(y-x) for x,y in zip(before,after)]
                self.matches(self.pixels(d),[expected])
                # Blending an isolated group uses its completed child composite.
                if isolated:
                    d=self.edit(d,[dict(op='properties',id='s',blend='normal'),dict(op='properties',id='g',blend=mode)])
                    self.matches(self.pixels(d),[over(before,premul(s),F(3,8),mode)])

    def test_adjustment_replacement_preserves_alpha_with_all_rgb_modes(self):
        values=[[13,210,70,0],[200,50,90,1],[60,120,240,73],[80,80,80,128],[25,200,190,255]];m=[255,73,128,255,0]
        for mode in MODES:
            d=self.add(self.document(5),[layer('b',values),dict(id='a',blend=mode,opacity=.375,mask=mask(m),content=dict(type='adjustment',adjustment=dict(operators=[dict(type='invert')])) )])
            ideal=[]
            for p,k in zip(values,m):
                before=premul(p);b=straight(before);mixed=mix(b,[1-v for v in b],mode);weight=F(3*k,8*255)
                ideal.append([(x+(y-x)*weight)*before[3] for x,y in zip(b,mixed)]+[before[3]])
            self.matches(self.pixels(d),ideal)

    def test_filter_replacement_blends_triples_and_interpolates_alpha(self):
        values=[[210,35,90,255],[20,240,70,73],[80,20,250,0],[200,110,20,128],[95,130,180,255]];m=[255,128,255,73,255]
        for mode in MODES:
            f=dict(id='offset',operator=dict(type='spatial',operator=dict(type='offset',offset=[1,0])),blend=mode,opacity=.625,mask=mask(m),border='transparent')
            d=self.add(self.document(5),[layer('s',values,filters=[f])]);ideal=[]
            for i,p in enumerate(values):
                b=premul(p);s=premul(values[i-1]) if i else [F(0)]*4;cb,cs=straight(b),straight(s);mixed=mix(cb,cs,mode);weight=F(5*m[i],8*255)
                alpha=(1-weight)*b[3]+weight*s[3]
                rgb=[(1-weight)*b[c]+weight*s[3]*((1-b[3])*cs[c]+b[3]*mixed[c]) for c in range(3)]
                ideal.append(rgb+[alpha])
            self.matches(self.pixels(d),ideal)

    def test_clipped_members_keep_base_alpha_before_base_effects(self):
        base=[[50,180,220,a] for a in (0,1,128,255)];src=[[190,90,40,a] for a in (255,128,73,255)];background=[[80,40,200,173]]*4;m=[255,73,128,255]
        for mode in MODES:
            d=self.add(self.document(4),[layer('back',background),layer('b',base,opacity=.625,blend='color'),layer('s',src,clip_to='b',opacity=.375,blend=mode,mask=mask(m))]);ideal=[]
            for x,y,z,k in zip(base,src,background,m):
                b,s=premul(x),premul(y);cb,cs=straight(b),straight(s);mixed=mix(cb,cs,mode);w=s[3]*F(3*k,8*255)
                clipped=[((1-w)*cb[c]+w*mixed[c])*b[3] for c in range(3)]+[b[3]]
                ideal.append(over(premul(z),clipped,F(5,8),'color'))
            self.matches(self.pixels(d),ideal)

    def test_continuous_modes_preserve_neutral_colors_and_duality(self):
        values=[[i,255-i,(i*31)%256,255] for i in range(256)]
        for mode,neutral in [('multiply',255),('screen',0),('color_burn',255),('color_dodge',0),('difference',0),('exclusion',0),('subtract',0),('divide',255)]:
            d=self.add(self.document(256),[layer('b',values),layer('s',[[neutral]*3+[255]]*256,blend=mode)])
            self.assertEqual(self.pixels(d),bytes(v for p in values for v in p),mode)
        b=[v[0] for v in self.chart()];s=[v[1] for v in self.chart()]
        d1=self.add(self.document(len(b)),[layer('b',b),layer('s',s,blend='overlay')]);d2=self.add(self.document(len(b)),[layer('s',s),layer('b',b,blend='hard_light')])
        self.assertEqual(self.pixels(d1),self.pixels(d2))

    def test_nonseparable_luminance_saturation_and_hue_invariants(self):
        # Verify observable relationships as well as the equation oracle.
        values=[[i,80,180,255] for i in range(0,256,5)];source=[[180,i,60,255] for i in range(0,256,5)]
        for mode in ('hue','saturation','color','luminosity'):
            d=self.add(self.document(len(values)),[layer('b',values),layer('s',source,blend=mode)]);actual=self.pixels(d)
            for i,(b,s) in enumerate(zip(values,source)):
                observed=actual[i*4:i*4+3];wanted=luminance(s[:3] if mode=='luminosity' else b[:3])
                self.assertLessEqual(abs(luminance(observed)-wanted),F(1,2))
        d=self.add(self.document(1),[layer('b',[[83,83,83,255]]),layer('s',[[245,4,160,255]],blend='saturation')])
        self.assertEqual(self.pixels(d),bytes([83,83,83,255]))

    def test_persist_edit_inspect_diff_and_rejected_contexts(self):
        d=self.add(self.document(kind='vector'),[rectangle('b',[20,180,150,200]),rectangle('s',[220,60,70,128])]);original=copy.deepcopy(d)
        for mode in MODES:
            edited=self.edit(d,[dict(op='properties',id='s',blend=mode)])
            snapshot=self.invoke(dict(command='document.export',document=edited,format='snapshot'))
            saved=self.invoke(dict(command='document.validate',document=json.loads(snapshot['data'])))
            self.assertEqual(saved,edited);self.assertEqual(self.pixels(saved),self.pixels(edited))
            inspected=self.invoke(dict(command='document.inspect',document=saved));self.assertEqual(inspected['items'][1]['blend'],mode)
            diff=self.invoke(dict(command='document.diff',before=d,after=edited))
            self.assertEqual(diff['changed'],mode!='normal')
            if mode!='normal':self.assertEqual(self.invoke(dict(command='document.export',document=saved,format='svg'),1)['code'],'UNSUPPORTED')
        self.assertEqual(d,original)
        bad=self.edit(d,[dict(op='properties',id='s',blend='unknown')],1);self.assertEqual(bad['code'],'INVALID_REQUEST')
        error=self.edit(d,[dict(op='properties',id='b',opacity=.25),dict(op='properties',id='s',blend='overlay',opacity=-1)],1)
        self.assertEqual(error['code'],'INVALID_DOCUMENT');self.assertEqual(d,original)
        group=dict(id='g',blend='color',content=dict(type='group',isolated=False))
        self.assertEqual(self.edit(d,[dict(op='add',item=group)],1)['code'],'UNSUPPORTED')
        locked=self.edit(d,[dict(op='properties',id='s',locked=True)])
        self.assertEqual(self.edit(locked,[dict(op='properties',id='s',blend='color')],1)['code'],'LOCKED')

    def test_nested_transformed_antialias_edges_use_measured_coverage(self):
        # A separate white-only geometry render supplies coverage, not colors.
        # Compare every edge against independent alpha composition. This tests
        # color blending without making claims about another rasterizer's AA.
        transform=[1,.125,.25,1,.375,.25];back=[45,170,95,191];source=[210,80,155,255]
        geom=rectangle('s',[255]*4,w=3,h=2,transform=transform)
        coverage=self.pixels(self.add(self.document(5,4,'vector'),[geom]))[3::4]
        self.assertTrue(any(0<a<255 for a in coverage))
        for mode in MODES:
            items=[rectangle('b',back,w=5,h=4),dict(id='g',content=dict(type='group'),opacity=.625),rectangle('s',source,w=3,h=2,transform=transform,parent='g')]
            items[1]['blend']=mode
            d=self.add(self.document(5,4,'vector'),items)
            self.matches(self.pixels(d),[over(premul(back),premul(source[:3]+[a]),F(5,8),mode) for a in coverage])

    def test_mcp_persistent_blends_retry_reopen_snapshot_and_undo(self):
        d=self.add(self.document(),[layer('b',[[40,100,180,191]]),layer('s',[[230,80,60,128]])])
        with tempfile.TemporaryDirectory() as root:
            params=dict(session_root=root,session_id='blends');c=Client();c.initialize()
            action=dict(type='edit',operations=[dict(op='properties',id='s',blend='hue',opacity=.625)])
            try:
                c.success('session.create',**params,request_id='create',document=d)
                changed=c.success('session.apply',**params,request_id='blend',expected_revision=0,action=action)
                self.matches(self.pixels(changed['document']),[over(premul([40,100,180,191]),premul([230,80,60,128]),F(5,8),'hue')])
                c.success('session.apply',**params,request_id='save',expected_revision=1,action=dict(type='snapshot',name='hue'))
            finally:c.close()
            c=Client();c.initialize()
            try:
                replay=c.success('session.apply',**params,request_id='blend',expected_revision=0,action=action)
                self.assertEqual(replay['document'],changed['document']);self.assertEqual(replay['current_revision'],2)
                self.assertTrue(replay['replayed']);self.assertEqual(replay['receipt'],changed['receipt'])
                reopened=c.success('session.read',**params)['document'];self.assertEqual(reopened['items'][1]['blend'],'hue')
                self.assertEqual(c.success('session.read',**params,snapshot='hue')['document']['items'],changed['document']['items'])
                undone=c.success('session.apply',**params,request_id='undo',expected_revision=2,action=dict(type='undo'))['document']
                self.assertEqual(undone['items'],d['items']);self.assertEqual(self.pixels(undone),self.pixels(d))
            finally:c.close()

    def test_capabilities_schema_and_complete_scope_remain_honest(self):
        c=self.invoke(dict(command='capabilities'))
        self.assertEqual(c['supported']['blend_modes'],MODES);self.assertEqual(c['filters']['blend_modes'],MODES)
        self.assertEqual(c['blending']['families'],26);self.assertTrue(c['blending']['fill_opacity']);self.assertTrue(c['blending']['knockout']);self.assertTrue(c['blending']['dissolve'])
        schema=self.invoke(dict(command='schema'));self.assertEqual(schema['$defs']['BlendMode']['enum'],MODES)
        status=self.invoke(dict(command='implementation.status'))
        features={f['id']:f for f in status['features']}
        self.assertEqual(features['vector.blending.extended']['status'],'verified')
        self.assertEqual(features['raster.effects.extended']['status'],'verified')
        self.assertNotEqual(features['vector.booleans.extended']['status'],'verified')


if __name__=='__main__':unittest.main()
