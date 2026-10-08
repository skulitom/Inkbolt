"""Original addressed-ink equations, full neighborhoods and stable identity hashes."""
import cmath
import copy
from fractions import Fraction as F
import hashlib
import itertools
import math
from pathlib import Path
import struct
import tempfile
import unittest
import pdf_reader
import test_native_coverage_cli as coverage
from test_native_filters_cli import transport,fetch,sample
from test_native_blending_cli import over,addresses,ink_mix,MODES
from test_native_images_cli import fill,process
from test_vector_plates_cli import rect,named,color,spot
from test_knockout_cli import group
from test_creative_filters_cli import field_value
from test_detail_spatial_cli import seeded
from test_masks_cli import inverse
from test_native_print_cli import page_image
from test_profiles_cli import embedded
from cmyk_fixtures import cmyk_profile
from test_mcp import Client


def detail(**kw):return dict(type='detail',operator=kw)
def creative(**kw):return dict(type='creative',operator=kw)
def clamp(v):return max(F(0),min(F(1),v))
def conditional(p,c,n,fallback):return p[c]/p[n+c] if p[n+c] else fallback

def spot_noise(seed,x,y,id,distribution):
    data=id.encode();digest=hashlib.sha256(b'Inkbolt ink noise v1\0'+struct.pack('<IIII',seed,x,y,len(data))+data).digest();a,b=struct.unpack('<QQ',digest[:16]);u=F(2*(a>>12)+1,2**53);v=F(2*(b>>12)+1,2**53)
    return 2*u-1 if distribution=='uniform' else F(math.sqrt(-2*math.log(u))*math.cos(math.tau*v))


def operators():
    return [dict(type='surface',radius=1,threshold=.5),detail(type='sharpen',amount=1.25),detail(type='unsharp',sigma=.6,amount=1.5,threshold=.125),detail(type='median',radius=1),detail(type='noise',amount=.125,seed=71,monochrome=False,distribution='uniform'),creative(type='twist',center=[2.5,1.5],radius=3.5,angle=135),creative(type='relief',angle=90,distance=1.25,strength=1.5),creative(type='high_pass',sigma=.6),creative(type='extrema',radius=1,mode='minimum'),creative(type='tone_fold',threshold=.5),creative(type='edge_ink',strength=1.25),creative(type='stroke_rank',radius=1,angle=90,quantile=.25),creative(type='value_field',seed=83,cell_size=2.5,octaves=3,origin=[-.5,.25],low=[30,90,170],high=[220,170,20]),creative(type='field_repair',keep_parity=1)]


def evaluate(rows,w,h,operator,border='transparent',scale=1,world=(1,0,0,1,0,0),ids=('s',)):
    n=(len(rows[0])-1)//2;kind=operator['type'];op=operator if kind=='surface' else operator['operator'];kind=op['type'];out=[list(row) for row in rows]
    if kind=='twist':
        for i in range(w*h):
            x,y=i%w,i//w;local=inverse(world,[(x+.5)/scale,(y+.5)/scale]);z=complex(local[0]-op['center'][0],local[1]-op['center'][1]);r=abs(z)/op['radius']
            if r>=1 or op['angle']==0:continue
            z*=cmath.exp(1j*math.radians(op['angle'])*(1-r)**2);z+=complex(*op['center']);a,b,c,d,e,f=world;q=complex(a*z.real+c*z.imag+e,b*z.real+d*z.imag+f)*scale-complex(.5,.5);out[i]=sample(rows,w,h,F(q.real),F(q.imag),border)
        return out
    if kind=='field_repair':
        retained=list(range(op['keep_parity'],h,2))
        for y in range(h):
            if y%2==op['keep_parity'] or h==1:continue
            before=max([yy for yy in retained if yy<y],default=retained[0]);after=min([yy for yy in retained if yy>y],default=retained[-1])
            for x in range(w):out[y*w+x]=[(a+b)/2 for a,b in zip(rows[before*w+x],rows[after*w+x])]
        return out
    if kind=='surface':
        r=op['radius']*scale;t=F(str(op['threshold']))
        def descriptor(p):return [v/p[-1] if p[-1] else F(0) for v in p[:-1]]+[p[-1]]
        for y in range(h):
            for x in range(w):
                center=descriptor(rows[y*w+x]);neighbors=[fetch(rows,w,h,x+dx,y+dy,border) for dy in range(-r,r+1) for dx in range(-r,r+1)];selected=[q for q in neighbors if max(abs(a-b) for a,b in zip(descriptor(q),center))<=t];out[y*w+x]=[sum(q[c] for q in selected)/len(selected) for c in range(2*n+1)]
        return out
    blurred=transport(rows,w,h,dict(type='gaussian',sigma=op['sigma']),border,scale,world) if kind in ['unsharp','high_pass'] else None
    for i,p in enumerate(rows):
        x,y=i%w,i//w
        rgb=None
        if kind=='value_field':
            point=inverse(world,[(x+.5)/scale,(y+.5)/scale]);t=field_value(op['seed'],(F(point[0])-F(op['origin'][0]))/F(op['cell_size']),(F(point[1])-F(op['origin'][1]))/F(op['cell_size']),op['octaves']);rgb=[(F(lo)*(1-t)+F(hi)*t)/255 for lo,hi in zip(op['low'],op['high'])];converted=process([float(v) for v in rgb])
        for c in range(n):
            if not p[n+c]:continue
            d=p[c]/p[n+c];get=lambda dx,dy:fetch(rows,w,h,x+dx,y+dy,border);read=lambda q:conditional(q,c,n,d)
            if kind=='sharpen':
                neighbors=[get(dx,dy) for dx,dy in [(-scale,0),(scale,0),(0,-scale),(0,scale)]];weight=sum(q[n+c] for q in neighbors);ref=sum(q[c] for q in neighbors)/weight if weight else d;value=d+F(str(op['amount']))*(d-ref)
            elif kind=='unsharp':
                delta=d-read(blurred[i]);value=d+F(str(op['amount']))*delta if abs(delta)>=F(str(op.get('threshold',0))) else d
            elif kind=='high_pass':value=F(1,2)+d-read(blurred[i])
            elif kind in ['median','extrema']:
                r=op['radius']*scale;neighbors=[get(dx,dy) for dy in range(-r,r+1) for dx in range(-r,r+1)];densities=sorted(read(q) for q in neighbors if q[n+c])
                value=densities[(len(densities)-1)//2] if kind=='median' else (max(densities) if op['mode']=='minimum' else min(densities))
            elif kind=='noise':
                distribution=op.get('distribution','uniform');mono=op.get('monochrome',True);noise=seeded(op['seed'],x//scale,y//scale,0 if mono else c,distribution) if mono or c<4 else spot_noise(op['seed'],x//scale,y//scale,ids[c-4],distribution);value=d-F(str(op['amount']))*F(noise)
            elif kind=='tone_fold':value=1-d if d<1-F(str(op['threshold'])) else d
            elif kind=='relief':
                z=cmath.rect(op['distance']*scale,math.radians(op['angle']));a=sample(rows,w,h,F(x-z.real),F(y-z.imag),border);b=sample(rows,w,h,F(x+z.real),F(y+z.imag),border);value=F(1,2)+F(str(op['strength']))*(read(b)-read(a))/2
            elif kind=='edge_ink':
                gx=sum(read(get(dx*scale,dy*scale))*dx*(2 if dy==0 else 1) for dy in [-1,0,1] for dx in [-1,0,1]);gy=sum(read(get(dx*scale,dy*scale))*dy*(2 if dx==0 else 1) for dy in [-1,0,1] for dx in [-1,0,1]);value=F(str(op['strength']))*F(math.hypot(gx,gy))/4
            elif kind=='stroke_rank':
                z=cmath.rect(1,math.radians(op['angle']));r=op['radius']*scale;points=[sample(rows,w,h,F(x+j*z.real),F(y+j*z.imag),border) for j in range(-r,r+1)];values=sorted((read(q) for q in points if q[n+c]),reverse=True);value=values[math.floor(F(str(op['quantile']))*(len(values)-1))]
            elif kind=='value_field':value=F(converted[c]) if c<4 else d
            else:raise AssertionError(kind)
            out[i][c]=p[n+c]*clamp(value)
    return out


def replacement(before,after,weight,mode):
    n=(len(before)-1)//2;a,b=before[-1],after[-1]
    if mode=='normal':return [(1-weight)*x+weight*y for x,y in zip(before,after)]
    base=[v/a if a else F(0) for v in before[:n]];resolved=[(after[c]+(b-after[n+c])*base[c]*a)/b if b else F(0) for c in range(n)];mixed=ink_mix(base,resolved,mode)
    q=[b*((1-a)*v+a*m) for v,m in zip(resolved,mixed)]+[b]*n+[b]
    return [(1-weight)*x+weight*y for x,y in zip(before,q)]


class NativeNonlinearTests(unittest.TestCase):
    invoke=coverage.NativeCoverageTests.invoke
    document=coverage.NativeCoverageTests.document
    planes=coverage.NativeCoverageTests.planes
    values=coverage.NativeCoverageTests.values
    assertValues=coverage.NativeCoverageTests.assertValues
    edit=coverage.NativeCoverageTests.edit
    export=coverage.NativeCoverageTests.export
    colors=[[F(1,2),F(1,4),F(1,8),F(0),F(0)],[F(1,8),F(3,4),F(0),F(1,4),F(0)],[F(0)]*4+[F(3,4)]]
    def scene(self,w=5,h=3):
        d=self.document(w,h);d['swatches']['p']=color(list(map(float,self.colors[1][:4])));alpha=[F([0,1,3,4][(x+2*y)%4],4) for y in range(h) for x in range(w)];d['items']=[group('art')]+[fill(f'c{i}',named(['b','p','s'][(i%w+i//w)%3],tint=.75 if (i%w+i//w)%3==2 else 1,opacity=float(a)),box=(i%w,i//w,1,1),parent='art') for i,a in enumerate(alpha)];rows=[[v*a for v in self.colors[(i%w+i//w)%3]]+[a]*5+[a] for i,a in enumerate(alpha)];return d,rows
    def filtered(self,d,op,border='transparent',**kw):
        d=copy.deepcopy(d);d['items'][0]['filters']=[dict(id='filter',operator=op,border=border,**kw)];return d
    def assertRows(self,d,rows,back=None,tolerance=5e-12,**kw):
        n=(len(rows[0])-1)//2;back=back or [F(0)]*n
        for actual,row in zip(self.values(d,**kw),rows,strict=True):
            expected=[row[c]+(1-row[n+c])*back[c] for c in range(n)];self.assertTrue(all(v==0 for v in expected[len(actual):]));self.assertValues(actual,expected[:len(actual)],tolerance)

    def test_fourteen_operators_against_independent_fields_and_neighborhoods(self):
        d,p=self.scene()
        for op,border in itertools.product(operators(),['transparent','clamp','wrap','reflect']):
            with self.subTest(operator=op,border=border):self.assertRows(self.filtered(d,op,border),evaluate(p,5,3,op,border),tolerance=.00008 if op.get('operator',{}).get('type')=='value_field' else 6e-12)

    def test_singletons_identities_extreme_controls_and_borders(self):
        ops=[detail(type='sharpen',amount=0),detail(type='unsharp',sigma=0,amount=8,threshold=0),detail(type='median',radius=0),detail(type='noise',amount=0,seed=71),creative(type='twist',center=[0,0],radius=1,angle=0),creative(type='field_repair',keep_parity=0),creative(type='field_repair',keep_parity=1),creative(type='extrema',radius=1,mode='maximum'),creative(type='tone_fold',threshold=0),creative(type='tone_fold',threshold=1),creative(type='stroke_rank',radius=0,angle=0,quantile=1)]
        for w,h in [(1,1),(1,4),(4,1)]:
            d,p=self.scene(w,h)
            for op,border in itertools.product(ops,['transparent','wrap','reflect','clamp']):
                with self.subTest(size=(w,h),operator=op,border=border):self.assertRows(self.filtered(d,op,border),evaluate(p,w,h,op,border))

    def test_all_replacement_modes_keep_original_intrinsic_backdrop(self):
        d,p=self.scene();ops=[operators()[0],operators()[1],operators()[3],operators()[4],operators()[8],operators()[10]]
        for op,mode in itertools.product(ops,MODES):
            q=evaluate(p,5,3,op,'reflect');expected=[replacement(a,b,F(3,8),mode) for a,b in zip(p,q)]
            with self.subTest(operator=op,mode=mode):self.assertRows(self.filtered(d,op,'reflect',opacity=.375,blend=mode),expected,tolerance=7e-12)

    def test_overprint_preserves_unaddressed_inks_for_every_color_operator(self):
        back=self.colors[1]
        for op,policy,paint_id in itertools.product(operators(),['knockout','preserve','preserve_nonzero'],['b','s']):
            d=self.document(5,3);d['swatches']['p']=color(list(map(float,back[:4])));c=self.colors[0][:4] if paint_id=='b' else self.colors[2];address=addresses(c,policy,paint_id=='s');alpha=[F(3,4) if 1<=x<4 and y==1 else F(0) for y in range(3) for x in range(5)]
            d['items']=[fill('ink',named(paint_id,opacity=.75,tint=.75 if paint_id=='s' else 1,overprint=policy),box=(1,1,3,1)),fill('back',named('p'),box=(0,0,5,3))];d['items'].reverse();d['items'][1]['filters']=[dict(id='filter',operator=op,border='reflect')]
            p=[[v*a if take else F(0) for v,take in zip(c,address)]+[a if take else F(0) for take in address]+[a] for a in alpha]
            q=evaluate(p,5,3,op,'reflect',world=[1,0,0,1,1,1]);self.assertRows(d,q,back=back,tolerance=.00008 if op.get('operator',{}).get('type')=='value_field' else 7e-12)

    def test_varying_fill_stroke_addressing_is_not_shared_alpha(self):
        w,h=8,7;d=self.document(w,h,kind='vector');d['swatches']['p']=color(list(map(float,self.colors[1][:4])));d['items']=[rect('back',named('p'),box=(0,0,w,h)),rect('art',named('b',opacity=.75,overprint='preserve_nonzero'),box=(2,2,4,3))];d['items'][1]['content']['stroke']=dict(color=named('s',tint=.75,opacity=.5,overprint='preserve'),width=2)
        p=[]
        for y in range(h):
            for x in range(w):
                a=F(3,4) if 2<=x<6 and 2<=y<5 else F(0);b=F(1,2) if 1<=x<7 and 1<=y<6 and not (3<=x<5 and 3<=y<4) else F(0);p.append([v*a for v in self.colors[0][:4]]+[F(3,4)*b]+[a,a,a,F(0),b]+[a+b-a*b])
        for op in operators():
            doc=copy.deepcopy(d);doc['items'][1]['filters']=[dict(id='filter',operator=op,border='reflect')];wanted=evaluate(p,w,h,op,'reflect')
            with self.subTest(operator=op):self.assertRows(doc,wanted,back=self.colors[1],tolerance=.00008 if op.get('operator',{}).get('type')=='value_field' else 8e-12)

    def test_scaled_fields_supersampling_and_maximum_named_inks(self):
        d,p=self.scene(3,2)
        for op in operators():
            source=[p[(y//2)*3+x//2] for y in range(4) for x in range(6)];q=evaluate(source,6,4,op,'reflect',scale=2);points=[[x,y] for y in range(4) for x in range(6)];tolerance=.00008 if op.get('operator',{}).get('type')=='value_field' else 8e-12;self.assertRows(self.filtered(d,op,'reflect'),q,points=points,raster_scale=2,tolerance=tolerance)
            mean=[[sum(q[(y*2+dy)*6+x*2+dx][c] for dy in range(2) for dx in range(2))/4 for c in range(11)] for y in range(2) for x in range(3)];self.assertRows(self.filtered(d,op,'reflect'),mean,antialias='supersample2',tolerance=tolerance)
        d=self.document(7,4);d['swatches']={f's{i:02}':spot() for i in range(28)};d['items']=[group('art')]+[fill(f'c{i}',named(f's{i:02}',tint=.625,opacity=.75),box=(i%7,i//7,1,1),parent='art') for i in range(28)];p=[[F(0)]*4+[F(15,32) if c==i else F(0) for c in range(28)]+[F(3,4)]*33 for i in range(28)]
        for op in [operators()[3],operators()[4],operators()[10]]:self.assertRows(self.filtered(d,op,'reflect'),evaluate(p,7,4,op,'reflect',ids=[f's{i:02}' for i in range(28)]))

    def test_surface_shape_contains_actual_coverage_when_range_gates_differ(self):
        d=self.document(3,1);d['swatches']['p']=color(list(map(float,self.colors[1][:4])));d['items']=[group('outer',knockout=True),fill('previous',named('p'),box=(0,0,3,1),parent='outer'),fill('ink',named('b',opacity=.25),box=(1,0,1,1),parent='outer',filters=[dict(id='surface',operator=dict(type='surface',radius=1,threshold=.25),border='clamp')])]
        # Intrinsic color/address rejects empty neighbors; neutral footprint
        # accepts them, yielding 1/12. Containment must retain actual alpha 1/4.
        shape=[F(1,12),F(1,4),F(1,12)];expected=[[(F(1,4)*c if i==1 else 0)+(1-f)*b for c,b in zip(self.colors[0],self.colors[1])] for i,f in enumerate(shape)]
        for actual,wanted in zip(self.values(d),expected):self.assertValues(actual,wanted[:4])

    def test_selected_artboard_bleed_and_local_creative_fields(self):
        for op in operators():
            d=self.document(12,8,kind='vector');d['items']=[dict(id='board',transform=[1,0,0,1,7,3],content=dict(type='frame',frame=dict(role='artboard',width=4,height=3,bleed=dict(left=1,right=1,top=1,bottom=1))),filters=[dict(id='filter',operator=op,border='reflect')]),rect('ink',named('b',opacity=.75),box=(1,1,1,1),parent='board')]
            p=[]
            for y in range(5):
                for x in range(6):
                    a=F(3,4) if (x,y)==(2,2) else F(0);p.append([v*a for v in self.colors[0][:4]]+[a]*5)
            expected=evaluate(p,6,5,op,'reflect',world=[1,0,0,1,1,1]);points=[[x,y] for y in range(5) for x in range(6)];result=self.planes(d,artboard_id='board',include_bleed=True,samples=points)
            for value,row in zip(result['samples'],expected):self.assertValues(value['ink_fractions'],row[:4],.00008 if op.get('operator',{}).get('type')=='value_field' else 8e-12)

    def test_profiled_float_source_and_native_filter_receipts(self):
        from test_samples_cli import layer
        from test_profiles_cli import linear_profile
        values=[[.125,.25,.5,.75],[.5,.75,.25,.25],[.75,.125,.25,1],[.25,.5,.75,0]];d=self.document(4,1);item=layer([v for p in values for v in p],depth='f32',w=4);item['content']['grid'].update(encoding='profiled_rgb',profile=embedded(linear_profile(gamma=2)));d['items']=[item]
        p=[[F(v)*F(raw[3]) for v in process(raw[:3],gamma=2)]+[F(raw[3])]*5 for raw in values]
        for op in operators():self.assertRows(self.filtered(d,op,'reflect'),evaluate(p,4,1,op,'reflect'),tolerance=.00015)
        capabilities=self.invoke(dict(command='capabilities'))['native_prepress']['filters'];self.assertEqual(len(capabilities['operators']),21);self.assertEqual(capabilities['unsupported'],[])
        result=self.planes(self.filtered(d,operators()[3]));artifact=self.export(self.filtered(d,operators()[3]));self.assertEqual(capabilities,result['coverage_sources']['filters']);self.assertEqual(result['coverage_sources'],artifact['pages'][0]['coverage_sources'])

    def test_work_bounds_and_cancelled_nonlinear_publication(self):
        d=self.document(512,512);d['items']=[fill('art',named('b'),box=(0,0,512,512),filters=[dict(id='surface',operator=dict(type='surface',radius=16,threshold=.5))])];self.assertEqual(self.planes(d,1)['code'],'RESOURCE_LIMIT')
        with tempfile.TemporaryDirectory() as root:
            out=dict(output_root=root,file_name='cancelled.pdf',format='pdf',pdf_options=dict(prepress=dict(profile=embedded(cmyk_profile()),spot_fallback='multiplicative_declared')));error=self.invoke(dict(command='document.publish',document=d,output=out,control=dict(timeout_ms=0)),1);self.assertEqual(error['code'],'TIMEOUT');self.assertFalse((Path(root)/'cancelled.pdf').exists())

    def test_uniform_gaussian_noise_identity_and_unrelated_spot_insertion(self):
        for distribution,mono in itertools.product(['uniform','gaussian'],[True,False]):
            d,p=self.scene();op=detail(type='noise',amount=.2,seed=0xffffffff,distribution=distribution,monochrome=mono);self.assertRows(self.filtered(d,op),evaluate(p,5,3,op),tolerance=7e-12)
            d=self.document(3,1);d['swatches']={'z-last':spot()};d['items']=[fill('ink',named('z-last',tint=.5,overprint='preserve'),box=(0,0,3,1),filters=[dict(id='noise',operator=op)])];before=self.planes(d);d['swatches']['a-first']=spot();d['items'].insert(0,fill('extra',named('a-first',opacity=0),box=(0,0,1,1)));after=self.planes(d);self.assertEqual(next(v['sample_sha256'] for v in before['plates'] if v['id']=='z-last'),next(v['sample_sha256'] for v in after['plates'] if v['id']=='z-last'))

    def test_faint_addressed_ink_and_coverage_survive_identity_operations(self):
        for tiny in [1e-20,1e-200]:
            d=self.document(1,1);d['swatches']['b']=color([tiny,.25,0,0]);d['items']=[fill('ink',named('b',opacity=tiny,overprint='preserve_nonzero'),box=(0,0,1,1))]
            for op in [detail(type='noise',amount=0,seed=3),detail(type='median',radius=0),detail(type='sharpen',amount=0),detail(type='unsharp',sigma=0,amount=8),creative(type='extrema',radius=0,mode='maximum'),creative(type='stroke_rank',radius=0,angle=0,quantile=0)]:
                actual=self.values(self.filtered(d,op))[0];self.assertEqual(actual[1],tiny*.25);self.assertEqual(actual[0],tiny*tiny)

    def test_surface_shape_uses_neutral_alpha_then_contains_actual_alpha(self):
        d=self.document(3,1);d['swatches']['p']=color([.125,.75,0,.25]);op=dict(type='surface',radius=1,threshold=.25);d['items']=[group('outer',knockout=True),fill('previous',named('p'),box=(0,0,3,1)),group('art',parent='outer',filters=[dict(id='surface',operator=op,border='clamp')]),fill('a',named('b',opacity=.75),box=(0,0,1,1),parent='art',opacity=0),fill('b',named('b',opacity=.5),box=(1,0,1,1),parent='art',opacity=.5),fill('c',named('b',opacity=.75),box=(2,0,1,1),parent='art',opacity=.25)];d['items'][1]['parent']='outer'
        alpha=[F(0),F(1,4),F(3,16)];shape=[F(3,4),F(1,2),F(3,4)];p=[[v*a for v in self.colors[0]]+[a]*5+[a] for a in alpha];q=evaluate(p,3,1,op,'clamp');foot=evaluate([[0,s,s] for s in shape],3,1,op,'clamp');expected=[[v+(1-max(f[-1],row[-1]))*b for v,b in zip(row[:5],self.colors[1])] for row,f in zip(q,foot)]
        for actual,wanted in zip(self.values(d),expected):self.assertValues(actual,wanted[:len(actual)])

    def test_mask_stack_order_and_source_preserving_history_PDF(self):
        d,p=self.scene();mask=[0,64,128,192,255]*3;ops=[operators()[1],operators()[4],operators()[13]];stack=[]
        for i,op in enumerate(ops):
            q=evaluate(p,5,3,op,'reflect');p=[replacement(a,b,F(m,510),'normal') for a,b,m in zip(p,q,mask)];stack.append(dict(id=f'f{i}',operator=op,border='reflect',opacity=.5,mask=dict(width=5,height=3,gray_hex=bytes(mask).hex())))
        changed=copy.deepcopy(d);changed['items'][0]['filters']=stack;self.assertRows(changed,p)
        c=Client();c.initialize();self.addCleanup(c.close);d=self.invoke(dict(command='document.validate',document=d));original=copy.deepcopy(d)
        with tempfile.TemporaryDirectory() as root:
            s=dict(session_root=str(Path(root)/'sessions'),session_id='nonlinear');c.success('session.create',**s,request_id='create',document=d);before=self.planes(d)
            req=dict(request_id='filters',expected_revision=0,action=dict(type='edit',operations=[dict(op='filters',id='art',filters=stack)]));saved=c.success('session.apply',**s,**req)['document'];after=self.planes(saved);artifact=self.export(saved);self.assertEqual(hashlib.sha256(page_image(pdf_reader.Pdf(artifact))[1]).hexdigest(),after['interleaved_sha256']);self.assertNotEqual(before['interleaved_sha256'],after['interleaved_sha256'])
            undone=c.success('session.apply',**s,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'];self.assertEqual(self.planes(undone)['interleaved_sha256'],before['interleaved_sha256']);c.success('session.apply',**s,request_id='redo',expected_revision=2,action=dict(type='redo'));self.assertTrue(c.success('session.apply',**s,**req)['replayed']);self.assertTrue(c.success('session.verify',**s)['valid']);self.assertEqual(d,original)


if __name__=='__main__':unittest.main()
