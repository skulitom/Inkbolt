"""Independent HLS, rational color-chart and lookup-polynomial verification."""
import colorsys
import copy
from decimal import Decimal,localcontext
from fractions import Fraction as F
import json
import math
import tempfile
import unittest
import test_adjustments_cli as tone
from test_mcp import Client


def color(**args):return dict(type='color',adjustment=args)
def shift(x,a):return x+(1-x)*a if a>=0 else x*(1+a)
def y(rgb):return sum(a*b for a,b in zip(rgb,[F(2126,10000),F(7152,10000),F(722,10000)]))
def chart():return [(r,g,b,a) for r in (0,51,127,204,255) for g in (0,85,170,255) for b in (0,64,192,255) for a in (1,79,255)]


class ColorAdjustmentCliTests(unittest.TestCase):
    invoke=tone.AdjustmentCliTests.invoke
    document=tone.AdjustmentCliTests.document
    edit=tone.AdjustmentCliTests.edit
    layer=tone.AdjustmentCliTests.layer
    pixels=tone.AdjustmentCliTests.pixels
    saved=tone.AdjustmentCliTests.saved
    source=tone.AdjustmentCliTests.source
    adjusted=tone.AdjustmentCliTests.adjusted
    assert_quantized=tone.AdjustmentCliTests.assert_quantized

    def verify_rational(self,values,operation,reference):
        d=self.source(values);edited=self.adjusted(d,[operation]);ideal=[]
        for p in values:ideal.extend(list(reference([F(v,255) for v in p[:3]]))+[F(p[3],255)] if p[3] else [F(0)]*4)
        self.assert_quantized(self.pixels(edited),ideal);self.assertEqual(edited['items'][0],d['items'][0]);self.assertEqual(self.saved(edited),edited)
        return edited

    def test_hue_saturation_matches_independent_hls_and_primary_rotations(self):
        values=chart();d=self.source(values)
        for hue,saturation,lightness in ((120,0,0),(-45,0.3,-0.1),(720,0,0),(0,-1,0),(0,0.5,0.25)):
            output=self.pixels(self.adjusted(d,[color(type='hue_saturation',hue=hue,saturation=saturation,lightness=lightness)]))
            expected=[]
            for p in values:
                h,l,s=colorsys.rgb_to_hls(*(v/255 for v in p[:3]));r,g,b=colorsys.hls_to_rgb((h+hue/360)%1,shift(l,lightness),shift(s,saturation));expected.extend([r,g,b,p[3]/255])
            for n,(a,v) in enumerate(zip(output,expected)):
                # Independent floating HLS arithmetic: <=2e-10 byte error before final rounding.
                low=math.floor(v*255+0.5-2e-10);high=math.floor(v*255+0.5+2e-10)
                self.assertIn(a,[max(0,low),min(255,high)],(n,a,v))
        primaries=self.source([(255,0,0,255),(0,255,0,255),(0,0,255,255)])
        self.assertEqual(self.pixels(self.adjusted(primaries,[color(type='hue_saturation',hue=120)])),bytes([0,255,0,255,0,0,255,255,255,0,0,255]))
        gray=self.source([(128,128,128,255)])
        self.assertEqual(self.pixels(self.adjusted(gray,[color(type='hue_saturation',saturation=1,hue=120)])),bytes([1,255,1,255]))

    def test_near_black_hue_conversion_remains_finite_before_later_amplification(self):
        source=self.source([(255,0,0,255)])
        operators=[color(type='channel_mixer',matrix=[[1e-100,0,0],[0,1,0],[0,0,1]]),color(type='hue_saturation',hue=120),dict(type='curve',points=[[0,0],[1e-100,1],[1,1]])]
        self.assertEqual(self.pixels(self.adjusted(source,operators)),bytes([0,255,0,255]))

    def test_desaturation_methods_amounts_and_alpha_match_exact_gray_definitions(self):
        values=chart()+[(255,35,90,0)]
        for method in ('luma','average','lightness'):
            for amount in (F(0),F(1,4),F(1)):
                def reference(rgb):
                    gray=y(rgb) if method=='luma' else (sum(rgb)/3 if method=='average' else (max(rgb)+min(rgb))/2)
                    return [v+amount*(gray-v) for v in rgb]
                self.verify_rational(values,color(type='desaturate',method=method,amount=float(amount)),reference)

    def test_channel_mixing_negative_coefficients_offsets_and_gamut_clamping(self):
        matrix=[[F(3,2),F(-1,2),F(0)],[F(0),F(0),F(1)],[F(1,4),F(1,2),F(1,4)]];offset=[F(1,10),F(-1,5),F(0)]
        self.verify_rational(chart(),color(type='channel_mixer',matrix=[[float(v) for v in row] for row in matrix],offset=list(map(float,offset))),lambda rgb:[sum(a*b for a,b in zip(row,rgb))+bias for row,bias in zip(matrix,offset)])
        self.verify_rational(chart(),color(type='channel_mixer',matrix=[[0,0,1],[1,0,0],[0,1,0]]),lambda c:[c[2],c[0],c[1]])

    def test_color_balance_tone_weights_and_luma_preserving_gamut_compression(self):
        shadows=[F(1),F(-1,2),F(1,4)];mid=[F(-1,4),F(1,2),F(0)];high=[F(-3,4),F(0),F(1)]
        values=chart()
        for preserve in (False,True):
            def reference(c):
                target=y(c);weights=[(1-target)**2,2*target*(1-target),target**2]
                mapped=[shift(v,sum(w*a for w,a in zip(weights,(shadows[i],mid[i],high[i])))) for i,v in enumerate(c)]
                if preserve:
                    mean=y(mapped);delta=[v-mean for v in mapped];scale=min([F(1)]+[(1-target)/v if v>0 else -target/v for v in delta if v])
                    mapped=[target+scale*v for v in delta]
                return mapped
            edited=self.verify_rational(values,color(type='balance',shadows=list(map(float,shadows)),midtones=list(map(float,mid)),highlights=list(map(float,high)),preserve_luma=preserve),reference)
            if preserve:
                p=self.pixels(edited)
                for n,original in enumerate(values):
                    delta=abs(y([F(v,255) for v in p[n*4:n*4+3]])-y([F(v,255) for v in original[:3]]))
                    self.assertLessEqual(float(delta),0.5/255+1e-15)

    def test_selective_chromatic_bands_wrap_hue_and_leave_neutrals_unchanged(self):
        values=[(255,0,0,255),(255,128,0,255),(255,0,128,255),(0,255,255,255),(100,100,100,255),(0,0,0,255),(255,255,255,255)]
        for mode in ('relative','absolute'):
            weights=[F(1),F(127,255),F(127,255),F(0),F(0),F(0),F(0)]
            correction=[F(1,5),F(-1,4),F(0),F(1,10)];ideal=[]
            for p,w in zip(values,weights):
                c=[F(v,255) for v in p[:3]];delta=[-w*(correction[i]+correction[3]) for i in range(3)]
                ideal.extend([c[i]+delta[i] if mode=='absolute' else shift(c[i],delta[i]) for i in range(3)]+[F(1)])
            d=self.source(values);op=color(type='selective',mode=mode,corrections=[dict(band='reds',cmyk=list(map(float,correction)))])
            self.assert_quantized(self.pixels(self.adjusted(d,[op])),ideal)
        for band,value in zip(('reds','yellows','greens','cyans','blues','magentas'),[(255,0,0),(255,255,0),(0,255,0),(0,255,255),(0,0,255),(255,0,255)]):
            self.verify_rational([(*value,255)],color(type='selective',mode='absolute',corrections=[dict(band=band,cmyk=[0,0,0,0.2])]),lambda c:[v-F(1,5) for v in c])

    def test_selective_neutral_partition_order_and_relative_absolute_endpoints(self):
        values=[(i,i,i,255) for i in range(256)]
        for band in ('whites','neutrals','blacks'):
            def reference(c):
                l=c[0];w=l*l if band=='whites' else ((1-l)**2 if band=='blacks' else 2*l*(1-l))
                return [v+w*F(1,4) for v in c]
            self.verify_rational(values,color(type='selective',mode='absolute',corrections=[dict(band=band,cmyk=[0,0,0,-0.25])]),reference)
        bands=['reds','yellows','greens','cyans','blues','magentas','whites','neutrals','blacks']
        corrections=[dict(band=b,cmyk=[0.1,-0.2,0.3,0]) for b in bands]
        d=self.source(chart());a=self.adjusted(d,[color(type='selective',mode='absolute',corrections=corrections)]);b=self.adjusted(d,[color(type='selective',mode='absolute',corrections=list(reversed(corrections)))])
        # The nine weights form a partition, independently giving a uniform channel offset.
        ideal=[v for p in chart() for v in [F(p[0],255)-F(1,10),F(p[1],255)+F(1,5),F(p[2],255)-F(3,10),F(p[3],255)]]
        self.assert_quantized(self.pixels(a),ideal);self.assert_quantized(self.pixels(b),ideal)

    def test_1d_lookup_custom_domain_strength_and_out_of_gamut_values(self):
        domain=[[0.2,0,0.1],[0.8,1,0.9]];table=[[-0.2,1,0],[0.4,0.5,1],[1.2,0,0.2]];exact=[[F(str(v)) for v in row] for row in table]
        def reference(c):
            result=[]
            for i,x in enumerate(c):
                lo,hi=F(str(domain[0][i])),F(str(domain[1][i]));p=max(0,min(1,(x-lo)/(hi-lo)))*2;n=min(1,int(p));v=exact[n][i]+(p-n)*(exact[n+1][i]-exact[n][i]);result.append(x+F(3,4)*(v-x))
            return result
        self.verify_rational(chart(),color(type='lut1d',values=table,domain=domain,strength=0.75),reference)
        self.verify_rational(chart(),color(type='lut1d',values=[[-16]*3,[16]*3],strength=0),lambda c:c)

    def test_3d_lookup_red_fastest_trilinear_polynomial_and_domain_endpoints(self):
        table=[[r*g,g*b,b*r] for b in (0,0.5,1) for g in (0,0.5,1) for r in (0,0.5,1)]
        self.verify_rational(chart(),color(type='lut3d',size=3,values=table),lambda c:[c[0]*c[1],c[1]*c[2],c[2]*c[0]])
        domain=[[0.1,0.2,0.3],[0.9,0.8,0.7]]
        def reference(c):
            v=[max(0,min(1,(c[i]-F(str(domain[0][i])))/(F(str(domain[1][i]))-F(str(domain[0][i]))))) for i in range(3)]
            return [c[i]+F(1,2)*(q-c[i]) for i,q in enumerate([v[2],v[0],v[1]])]
        permuted=[[b,r,g] for b in (0,1) for g in (0,1) for r in (0,1)]
        self.verify_rational(chart(),color(type='lut3d',size=2,values=permuted,domain=domain,strength=0.5),reference)
        self.verify_rational(chart(),color(type='lut3d',size=2,values=[[-1,2,0.5]]*8),lambda c:[F(0),F(1),F(1,2)])

    def test_gradient_maps_stops_hard_edges_and_linear_light_reference(self):
        values=[(i,i,i,255) for i in range(256)];stops=[dict(offset=0.2,color=[0,0,1]),dict(offset=0.5,color=[1,0,0]),dict(offset=0.5,color=[0,1,0]),dict(offset=0.8,color=[1,1,0])]
        def reference(c):
            t=c[0]
            if t<F(1,5):return [F(0),F(0),F(1)]
            if t<F(1,2):v=(t-F(1,5))/F(3,10);return [v,F(0),1-v]
            if t<F(4,5):return [(t-F(1,2))/F(3,10),F(1),F(0)]
            return [F(1),F(1),F(0)]
        self.verify_rational(values,color(type='gradient_map',stops=stops),reference)
        # Exact stop boundary after a levels operator must use the last duplicate stop.
        d=self.source([(20,20,20,255)]);ops=[dict(type='levels',input=[0,1],gamma=1,output=[0.5,0.5]),color(type='gradient_map',stops=stops)]
        self.assertEqual(self.pixels(self.adjusted(d,ops)),bytes([0,255,0,255]))
        d=self.source(values);actual=self.pixels(self.adjusted(d,[color(type='gradient_map',stops=[dict(offset=0,color=[0,0,0]),dict(offset=1,color=[1,1,1])],space='linear_rgb')]))
        with localcontext() as ctx:
            ctx.prec=40;D=Decimal;wanted=[]
            for i in range(256):
                v=D(i)/255;encoded=v*D('12.92') if v<=D('.0031308') else D('1.055')*v**(D(1)/D('2.4'))-D('.055');wanted.extend([int(encoded*255+D('.5'))]*3+[255])
        self.assertEqual(actual,bytes(wanted))

    def test_color_parameters_masks_stacks_snapshots_and_mcp_session_recovery(self):
        client=Client();self.addCleanup(client.close);client.initialize()
        with tempfile.TemporaryDirectory() as root:
            args=dict(session_root=root,session_id='color-edit');d=self.source([(255,0,0,255),(0,255,0,73),(0,0,255,0)])
            client.success('session.create',**args,request_id='create',document=d)
            op=color(type='hue_saturation',hue=120)
            layer=self.layer([op],clip_to='source',mask=dict(width=3,height=1,gray_hex='ff8000'))
            edited=client.success('session.apply',**args,request_id='recolor',expected_revision=0,action=dict(type='edit',operations=[dict(op='add',item=layer)]))['document']
            self.assertEqual(edited['items'][0],d['items'][0]);self.assertEqual(self.saved(edited),edited)
            self.assertEqual(self.pixels(edited),bytes([0,255,0,255,0,127,128,73,0,0,0,0]))
            updated=client.success('session.apply',**args,request_id='revise',expected_revision=1,action=dict(type='edit',operations=[dict(op='adjustment',id='adjust',adjustment=dict(operators=[color(type='channel_mixer',matrix=[[0,0,1],[1,0,0],[0,1,0]])],clip_to='source'))]))['document']
            self.assertEqual(self.pixels(updated),self.pixels(edited))
            client.success('session.apply',**args,request_id='undo2',expected_revision=2,action=dict(type='undo'))
            restored=client.success('session.apply',**args,request_id='undo1',expected_revision=3,action=dict(type='undo'))['document'];self.assertEqual(self.pixels(restored),self.pixels(d))
            client.success('session.verify',**args)

    def test_invalid_color_tables_controls_atomicity_and_work_limits(self):
        d=self.source([(10,20,30,255)])
        invalid=[dict(type='hue_saturation',hue=360001),dict(type='desaturate',amount=-1),dict(type='channel_mixer',matrix=[[5,0,0],[0,1,0],[0,0,1]]),dict(type='balance',shadows=[1.1,0,0]),dict(type='selective',corrections=[]),dict(type='selective',corrections=[dict(band='reds',cmyk=[0]*4)]*2),dict(type='lut1d',values=[[0]*3]),dict(type='lut1d',values=[[0]*3,[1]*3],domain=[[0]*3,[0]*3]),dict(type='lut3d',size=2,values=[[0]*3]*7),dict(type='lut3d',size=34,values=[]),dict(type='gradient_map',stops=[dict(offset=0.8,color=[0]*3),dict(offset=0.2,color=[1]*3)]),dict(type='gradient_map',stops=[dict(offset=0,color=[-1]*3),dict(offset=1,color=[1]*3)])]
        for op in invalid:
            error=self.edit(d,[dict(op='properties',id='source',name='candidate'),dict(op='add',item=self.layer([color(**op)]))],1);self.assertEqual(error['operation_index'],1)
        self.assertEqual(d['items'][0]['name'],'')
        big=self.document(1024,1024);big=self.edit(big,[dict(op='add',item=self.layer([color(type='lut3d',size=2,values=[[0]*3]*8)]*5))]);self.assertEqual(self.invoke(dict(command='document.render',document=big),1)['code'],'RESOURCE_LIMIT')
        oversized=self.document(1,1);op=color(type='lut1d',values=[[0]*3]*4096);oversized['items']=[self.layer([op]*16),self.layer([op],id='more')]
        error=self.invoke(dict(command='document.validate',document=oversized),1);self.assertEqual(error['code'],'RESOURCE_LIMIT');self.assertIn('65536',error['message'])


if __name__=='__main__':unittest.main()
