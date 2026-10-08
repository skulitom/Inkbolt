"""Original charts with independent rational, complex-map and field reconstructions."""
import base64
import cmath
import copy
from decimal import Decimal, localcontext
from fractions import Fraction as F
import hashlib
import math
import struct
import tempfile
import unittest
import test_adjustments_cli as tone
import test_editing_cli as editing
import test_filters_cli as blur
from test_mcp import Client


def creative(**op): return dict(type='creative', operator=op)
def rgb(p, fallback): return [q/p[3] for q in p[:3]] if p[3] else fallback[:3]
def flat(p): return [v for q in p for v in q]
def field_value(seed, x, y, octaves):
    """Exact rational tensor interpolation and binary octave weights."""
    total = F(0)
    for o in range(octaves):
        x0, y0 = math.floor(x*2**o), math.floor(y*2**o)
        u, v = x*2**o-x0, y*2**o-y0
        u, v = 3*u*u-2*u**3, 3*v*v-2*v**3
        for dx, wx in ((0, 1-u), (1, u)):
            for dy, wy in ((0, 1-v), (1, v)):
                message = b'Inkbolt value field v1\0'+struct.pack('<IqqI', seed, x0+dx, y0+dy, o)
                n = int.from_bytes(hashlib.sha256(message).digest()[:8], 'little') >> 12
                total += F(2*n+1, 2**53)*wx*wy/F(2**o)
    return total/sum(F(1, 2**o) for o in range(octaves))


class CreativeTests(unittest.TestCase):
    invoke = editing.EditingCliTests.invoke
    document = tone.AdjustmentCliTests.document
    edit = tone.AdjustmentCliTests.edit
    source = tone.AdjustmentCliTests.source
    pixels = tone.AdjustmentCliTests.pixels
    saved = tone.AdjustmentCliTests.saved
    assert_quantized = tone.AdjustmentCliTests.assert_quantized
    filter = blur.FilterTests.filter
    filtered = blur.FilterTests.filtered
    chart = blur.FilterTests.chart

    def apply(self, d, op, **kw): return self.filtered(d, [self.filter(creative(**op), **kw)])
    def assert_projection(self, actual, ideal):
        self.assertEqual(len(actual), len(ideal))
        for i, (a, b) in enumerate(zip(actual, ideal)):
            self.assertLessEqual(abs(a-255*max(0, min(1, float(b)))), .50000001, (i, a, b))

    def test_extrema_square_order_statistics_all_borders_alpha_and_radius_zero(self):
        for w, h in ((7, 5), (1, 4), (4, 1), (1, 1)):
            values = self.chart(w, h); p = blur.premult(values); d = self.source(values, w)
            for mode in ('minimum', 'maximum'):
                reduce = min if mode == 'minimum' else max
                for border in ('transparent', 'reflect', 'clamp', 'wrap'):
                    for r in (0, 1, 3):
                        ideal = []
                        for y in range(h):
                            for x in range(w):
                                ns = [blur.fetch(p, w, h, x+dx, y+dy, border) for dy in range(-r,r+1) for dx in range(-r,r+1)]
                                ns = [q for q in ns if q[3]]; a = p[y*w+x][3]
                                ideal += [reduce(q[c]/q[3] for q in ns) for c in range(3)]+[a] if a else [F(0)]*4
                        self.assert_quantized(self.pixels(self.apply(d, dict(type='extrema', radius=r, mode=mode), border=border)), ideal)

    def test_fold_threshold_endpoint_equality_and_reversibility_of_storage(self):
        values = [(v, 255-v, v//2, a) for a in (0, 1, 79, 255) for v in range(256)]
        d = self.source(values, 256)
        for t in (F(0), F(64,255), F(1,2), F(1)):
            ideal = [[(1-F(c,255) if F(c,255)>t else F(c,255)) for c in q[:3]]+[F(q[3],255)] if q[3] else [F(0)]*4 for q in values]
            out = self.apply(d,dict(type='tone_fold', threshold=float(t)))
            self.assert_quantized(self.pixels(out),flat(ideal)); self.assertEqual(out, self.saved(out))
            self.assertEqual(out['items'][0]['content'],d['items'][0]['content'])

    def test_relief_independent_opposed_samples_flat_gray_and_borders(self):
        values=self.chart(7,5); p=blur.premult(values); d=self.source(values,7)
        for border in ('transparent','reflect','clamp','wrap'):
            for angle, distance, strength in ((0,0,8),(0,F(3,2),F(7,4)),(90,F(1),F(1)),(37,F(5,4),F(1,2))):
                z=cmath.rect(float(distance),math.radians(angle)); ideal=[]
                for y in range(5):
                    for x in range(7):
                        center=p[y*7+x]; fallback=rgb(center,[0]*4)
                        a=rgb(blur.bilinear(p,7,5,x-z.real,y-z.imag,border),fallback)
                        b=rgb(blur.bilinear(p,7,5,x+z.real,y+z.imag,border),fallback)
                        ideal += [F(1,2)+strength*(v-u)/2 for u,v in zip(a,b)]+[center[3]] if center[3] else [0]*4
                out=self.apply(d,dict(type='relief',angle=angle,distance=float(distance),strength=float(strength)),border=border)
                self.assert_projection(self.pixels(out),ideal)
        d=self.source([(71,122,219,a) for a in (0,1,17,255,0,255)])
        p=self.pixels(self.apply(d,dict(type='relief',angle=43,distance=2,strength=8)))
        self.assert_projection(p,flat([[.5,.5,.5,F(a,255)] if a else [0]*4 for a in (0,1,17,255,0,255)]))

    def test_high_pass_full_2d_decimal_kernel_impulses_alpha_and_flat_fields(self):
        values=self.chart(4,3); p=blur.premult(values); d=self.source(values,4)
        with localcontext() as ctx:
            ctx.prec=55
            for sigma in (Decimal(0),Decimal('.7'),Decimal('1.2')):
                r=math.ceil(3*sigma)
                k=[(-(Decimal(i)**2)/(2*sigma*sigma)).exp() for i in range(-r,r+1)] if sigma else [Decimal(1)]
                k=[F(v/sum(k)) for v in k]
                for border in ('transparent','reflect','clamp','wrap'):
                    ref=blur.convolution(p,4,3,k,border); ideal=[]
                    for a,b in zip(p,ref):
                        c=rgb(a,[0]*4); v=rgb(b,c)
                        ideal += [F(1,2)+x-y for x,y in zip(c,v)]+[a[3]] if a[3] else [F(0)]*4
                    self.assert_projection(self.pixels(self.apply(d,dict(type='high_pass',sigma=float(sigma)),border=border)),ideal)
        flatdoc=self.source([(211,33,128,255)]*9,3)
        self.assert_projection(self.pixels(self.apply(flatdoc,dict(type='high_pass',sigma=2))),[.5,.5,.5,1]*9)

    def test_edge_ink_rational_gradient_norms_alpha_and_constant_field(self):
        values=self.chart(7,5); p=blur.premult(values); d=self.source(values,7)
        for border in ('transparent','reflect','clamp','wrap'):
            ideal=[]
            for y in range(5):
                for x in range(7):
                    a=p[y*7+x]; fallback=rgb(a,[0]*4)
                    grid=[[sum(rgb(blur.fetch(p,7,5,x+dx,y+dy,border),fallback))/3 for dx in (-1,0,1)] for dy in (-1,0,1)]
                    gx=sum((row[2]-row[0])*weight for row,weight in zip(grid,(1,2,1)))
                    gy=sum((grid[2][i]-grid[0][i])*weight for i,weight in enumerate((1,2,1)))
                    value=1-1.5*math.sqrt(float(gx*gx+gy*gy))/4
                    ideal += [value]*3+[a[3]] if a[3] else [0]*4
            self.assert_projection(self.pixels(self.apply(d,dict(type='edge_ink',strength=1.5),border=border)),ideal)
        d=self.source([(9,140,211,255)]*16,4)
        self.assertEqual(self.pixels(self.apply(d,dict(type='edge_ink',strength=8))),bytes([255]*64))

    def test_stroke_rank_line_quantiles_direction_and_transparent_neighbors(self):
        values=self.chart(7,5); p=blur.premult(values); d=self.source(values,7)
        for border in ('transparent','reflect','clamp','wrap'):
            for angle,r,q in ((0,0,F(1,2)),(0,2,F(0)),(0,2,F(1,2)),(90,3,F(1)),(31,2,F(1,4))):
                direction=cmath.rect(1,math.radians(angle)); ideal=[]
                for y in range(5):
                    for x in range(7):
                        a=p[y*7+x]; ns=[blur.bilinear(p,7,5,x+k*direction.real,y+k*direction.imag,border) for k in range(-r,r+1)]
                        ns=[rgb(v,[0]*4) for v in ns if v[3]]
                        ideal += [sorted(v[c] for v in ns)[int(q*(len(ns)-1))] for c in range(3)]+[a[3]] if a[3] else [0]*4
                self.assert_projection(self.pixels(self.apply(d,dict(type='stroke_rank',angle=angle,radius=r,quantile=float(q)),border=border)),ideal)

    def test_twist_complex_inverse_map_all_borders_identity_and_source_retention(self):
        values=self.chart(7,5); p=blur.premult(values); d=self.source(values,7)
        for border in ('transparent','reflect','clamp','wrap'):
            for angle in (0,135,-280):
                ideal=[]; center=complex(3.25,2.125)
                for y in range(5):
                    for x in range(7):
                        z=complex(x+.5,y+.5)-center
                        factor=max(0,1-abs(z)/5)**2
                        src=center+z*cmath.exp(1j*math.radians(angle)*factor)-complex(.5,.5)
                        ideal.append(blur.bilinear(p,7,5,src.real,src.imag,border))
                out=self.apply(d,dict(type='twist',center=[center.real,center.imag],radius=5,angle=angle),border=border)
                self.assert_projection(self.pixels(out),blur.unpremult(ideal)); self.assertEqual(out['items'][0]['content'],d['items'][0]['content'])
        self.assertEqual(self.pixels(d),self.pixels(self.apply(d,dict(type='twist',center=[100,100],radius=1,angle=300))))

    def test_value_field_exact_rational_hash_interpolation_alpha_seeds_and_scales(self):
        values=[(23,45,89,(0,1,79,255)[i%4]) for i in range(20)]; d=self.source(values,5)
        for seed,octaves in ((0,1),(4294967295,4)):
            op=dict(type='value_field',seed=seed,cell_size=3,octaves=octaves,origin=[1.25,-.5],low=[23,67,211],high=[201,129,7])
            out=self.apply(d,op)
            for scale in (1,2,4):
                raw=bytes.fromhex(self.invoke(dict(command='document.render',document=out,scale=scale))['data']); ideal=[]
                for y in range(4*scale):
                    for x in range(5*scale):
                        t=field_value(seed,(F(2*x+1,2*scale)-F(5,4))/3,(F(2*y+1,2*scale)+F(1,2))/3,octaves)
                        alpha=F(values[(y//scale)*5+x//scale][3],255)
                        ideal += [(F(a)*(1-t)+F(b)*t)/255 for a,b in zip(op['low'],op['high'])]+[alpha] if alpha else [F(0)]*4
                self.assert_quantized(raw,ideal)
            self.assertEqual(self.pixels(out),self.pixels(self.saved(out)))
            self.assertNotEqual(self.pixels(out),self.pixels(self.apply(d,dict(op,seed=seed^789))))

    def test_field_repair_retained_lines_premultiplied_interpolation_endpoints_and_singleton(self):
        for w,h in ((3,7),(3,6),(1,2),(1,1)):
            values=[((x*43+y*17)%256,(y*47)%256,(x*13+y*73)%256,(0,1,79,255)[(x+y)%4]) for y in range(h) for x in range(w)]; d=self.source(values,w); p=blur.premult(values)
            for parity in (0,1):
                kept=list(range(parity,h,2)); ideal=[]
                for y in range(h):
                    rows=[y] if not kept or y in kept else [max((v for v in kept if v<y),default=kept[0]),min((v for v in kept if v>y),default=kept[-1])]
                    for x in range(w): ideal.append([sum(p[row*w+x][c] for row in rows)/len(rows) for c in range(4)])
                out=self.apply(d,dict(type='field_repair',keep_parity=parity))
                self.assert_quantized(self.pixels(out),blur.unpremult(ideal))
                self.assertEqual(self.pixels(out),self.pixels(self.apply(d,dict(type='field_repair',keep_parity=parity),border='wrap')))

    def test_stack_order_masks_disabled_controls_and_mcp_history(self):
        d=self.source(self.chart(7,5),7); original=copy.deepcopy(d)
        a=self.filter(creative(type='tone_fold',threshold=.5),id='fold')
        b=self.filter(creative(type='extrema',radius=1,mode='maximum'),id='max',border='clamp')
        ab=self.filtered(d,[a,b]); ba=self.filtered(d,[b,a]); self.assertNotEqual(self.pixels(ab),self.pixels(ba))
        self.assertEqual(self.pixels(d),self.pixels(self.filtered(d,[dict(a,enabled=False),dict(b,opacity=0)])))
        mask=dict(width=7,height=5,gray_hex='00'*17+'ff'+'00'*17)
        masked=self.filtered(d,[dict(a,mask=mask)]); p=self.pixels(masked); before=self.pixels(d); full=self.pixels(self.filtered(d,[a]))
        self.assertEqual(p[:68]+p[72:],before[:68]+before[72:]); self.assertEqual(p[68:72],full[68:72])
        with tempfile.TemporaryDirectory() as root:
            c=Client(); c.initialize()
            try:
                c.success('session.create',session_root=root,session_id='creative',request_id='create',document=d)
                changed=c.success('session.apply',session_root=root,session_id='creative',expected_revision=0,request_id='stack',action=dict(type='edit',operations=[dict(op='filters',id='source',filters=[a,b])]))['document']
                self.assertEqual(self.pixels(changed),self.pixels(ab))
                undone=c.success('session.apply',session_root=root,session_id='creative',expected_revision=1,request_id='undo',action=dict(type='undo'))['document']
                self.assertEqual(self.pixels(undone),self.pixels(d))
                c.success('session.apply',session_root=root,session_id='creative',expected_revision=2,request_id='redo',action=dict(type='redo'))
            finally:c.close()
            c=Client(); c.initialize()
            try:
                reopened=c.success('session.read',session_root=root,session_id='creative')['document']
                self.assertEqual(self.pixels(reopened),self.pixels(ab)); c.success('session.verify',session_root=root,session_id='creative')
            finally:c.close()
        self.assertEqual(d,original)

    def test_local_controls_follow_parent_transform_and_artboard_bleed(self):
        values=self.chart(7,5); base=self.source(values,7)
        operators=[dict(type='twist',center=[3.5,2.5],radius=4,angle=120),dict(type='value_field',seed=17,cell_size=2.5,octaves=3,origin=[-.5,1.5],low=[30,60,90],high=[240,180,120])]
        for op in operators:
            f=self.filter(creative(**op),border='transparent')
            grouped=self.edit(base,[dict(op='group',ids=['source'],new_id='g',isolated=True)])
            grouped=self.filtered(grouped,[f],id='g')
            framed=self.document(20,16)
            board=dict(id='board',transform=[1,0,0,1,4,3],filters=[f],content=dict(type='frame',frame=dict(role='artboard',width=7,height=5,bleed=dict(left=2,right=2,top=2,bottom=2))))
            child=copy.deepcopy(base['items'][0]); child['parent']='board'
            framed=self.edit(framed,[dict(op='add',item=board),dict(op='add',item=child)])
            for bleed in (False,True):
                artifact=self.invoke(dict(command='artboard.export',document=framed,format='png',include_bleed=bleed))['artifacts'][0]['artifact']
                actual=editing.png_pixels(base64.b64decode(artifact['data']))
                expected=self.invoke(dict(command='document.export',document=grouped,format='png',render_options=dict(padding=2 if bleed else 0,crop_to_canvas=False)))
                self.assertEqual(actual[:3],editing.png_pixels(base64.b64decode(expected['data']))[:3])
            # Translation of a complete isolated group preserves local field/map controls.
            moved=copy.deepcopy(grouped); moved['width']=12; moved['height']=9
            for item in moved['items']:
                if item['id']=='g':item['transform']=[1,0,0,1,2,2]
            actual=self.pixels(moved); cropped=b''.join(actual[((y+2)*12+2)*4:((y+2)*12+9)*4] for y in range(5))
            if op['type']=='value_field':self.assertEqual(cropped,self.pixels(grouped))

    def test_rejected_controls_contexts_limits_and_atomic_failure(self):
        d=self.source(self.chart(5,3),5)
        bad=[dict(type='twist',center=[0,0],radius=0,angle=0),dict(type='relief',angle=0,distance=33,strength=1),dict(type='high_pass',sigma=17),dict(type='extrema',mode='minimum',radius=9),dict(type='tone_fold',threshold=1.1),dict(type='edge_ink',strength=-1),dict(type='stroke_rank',radius=2,angle=0,quantile=1.1),dict(type='value_field',seed=0,cell_size=.5,octaves=2,origin=[0,0],low=[0,0,0],high=[255]*3),dict(type='field_repair',keep_parity=2)]
        for op in bad:self.assertEqual(self.filtered(d,[self.filter(creative(**op))],expected=1)['code'],'INVALID_DOCUMENT')
        f=self.filter(creative(type='edge_ink',strength=1))
        locked=self.edit(d,[dict(op='properties',id='source',locked=True)])
        self.assertEqual(self.filtered(locked,[f],expected=1)['code'],'LOCKED')
        group=self.edit(d,[dict(op='group',ids=['source'],new_id='g',isolated=False)])
        self.assertEqual(self.filtered(group,[f],id='g',expected=1)['code'],'UNSUPPORTED')
        hdr=copy.deepcopy(d); hdr['color_space']='linear_srgb'
        self.assertEqual(self.filtered(hdr,[f],expected=1)['code'],'UNSUPPORTED_HDR_MODE')
        indexed=copy.deepcopy(d); indexed['color_space']='indexed'
        self.assertEqual(self.invoke(dict(command='document.validate',document=indexed),1)['code'],'INVALID_REQUEST')
        original=copy.deepcopy(d)
        self.edit(d,[dict(op='filters',id='source',filters=[f]),dict(op='filters',id='source',filters=[self.filter(creative(**bad[0]))])],1)
        self.assertEqual(original,d)
        large=self.document(512,512); large=self.edit(large,[dict(op='add',item=dict(id='source',content=dict(type='fill',width=512,height=512,paint=[1,2,3,255])))])
        large=self.apply(large,dict(type='value_field',seed=0,cell_size=16,octaves=4,origin=[0,0],low=[0,0,0],high=[255]*3))
        self.assertEqual(self.invoke(dict(command='document.render',document=large),1)['code'],'RESOURCE_LIMIT')

    def test_twist_rotated_parent_and_export_scale_independent_source_map(self):
        values=self.chart(7,5); d=self.source(values,7)
        d=self.edit(d,[dict(op='group',ids=['source'],new_id='g',isolated=True),dict(op='transform',id='g',matrix=[0,1,-1,0,5,0])])
        d['width']=5; d['height']=7
        op=dict(type='twist',center=[3.25,2.125],radius=5,angle=117)
        out=self.filtered(d,[self.filter(creative(**op),border='reflect')],id='g')
        for scale in (1,2,4):
            w,h=5*scale,7*scale
            pixels=[values[(4-x//scale)*7+y//scale] for y in range(h) for x in range(w)]
            p=blur.premult(pixels); ideal=[]
            for y in range(h):
                for x in range(w):
                    local=complex((y+.5)/scale,5-(x+.5)/scale)
                    z=local-complex(*op['center']); rotation=cmath.exp(1j*math.radians(op['angle'])*max(0,1-abs(z)/op['radius'])**2)
                    q=complex(*op['center'])+z*rotation
                    ideal.append(blur.bilinear(p,w,h,(5-q.imag)*scale-.5,q.real*scale-.5,'reflect'))
            raw=bytes.fromhex(self.invoke(dict(command='document.render',document=out,scale=scale))['data'])
            self.assert_projection(raw,blur.unpremult(ideal))
        self.assertEqual(self.invoke(dict(command='document.edit',document=out,expected_revision=out['revision'],operations=[dict(op='filters',id='g',filters=[])],control=dict(timeout_ms=0)),1)['code'],'TIMEOUT')


if __name__ == '__main__': unittest.main()
