"""Independent full-neighborhood ink transport and conditional-color references."""
import copy
from decimal import Decimal, localcontext
from fractions import Fraction as F
import hashlib
import itertools
import math
from pathlib import Path
import tempfile
import unittest
import pdf_reader
import test_native_coverage_cli as coverage
from test_native_blending_cli import addresses, over, MODES
from test_native_effects_cli import evaluate as decorate
from test_effects_coverage_cli import effect
from test_knockout_cli import group
from test_native_images_cli import fill
from test_vector_plates_cli import named, color
from test_native_print_cli import page_image
from test_mcp import Client
from test_masks_cli import inverse


def fetch(p,w,h,x,y,border):
    def at(v,n):
        if border=='transparent': return v if 0<=v<n else None
        if border=='clamp': return min(n-1,max(0,v))
        if border=='wrap': return v%n
        return (list(range(n))+list(range(n-1,-1,-1)))[v%(2*n)]
    x,y=at(x,w),at(y,h)
    return [F(0)]*len(p[0]) if x is None or y is None else p[y*w+x]


def sample(p,w,h,x,y,border):
    ix,iy=math.floor(x),math.floor(y);fx,fy=F(x)-ix,F(y)-iy
    return [sum(fetch(p,w,h,ix+dx,iy+dy,border)[c]*wx*wy for dx,wx in ((0,1-fx),(1,fx)) for dy,wy in ((0,1-fy),(1,fy))) for c in range(len(p[0]))]


def transport(p,w,h,op,border='transparent',scale=1,world=(1,0,0,1,0,0)):
    """Direct full 2D sums, independent of the engine's separable traversal."""
    kind=op['type'];n=len(p[0]);kernel=None
    if kind=='box':
        r=op['radius']*scale;kernel=[F(1,2*r+1)]*(2*r+1)
    if kind=='gaussian':
        if not op['sigma']:return copy.deepcopy(p)
        with localcontext() as ctx:
            ctx.prec=48;s=Decimal(str(op['sigma']))*scale;r=math.ceil(3*s)
            k=[(-(Decimal(i)/s)**2/2).exp() for i in range(-r,r+1)];total=sum(k);kernel=[F(v/total) for v in k]
    if kernel is not None:
        r=len(kernel)//2
        return [[sum(fetch(p,w,h,x+dx,y+dy,border)[c]*kernel[dx+r]*kernel[dy+r] for dx in range(-r,r+1) for dy in range(-r,r+1)) for c in range(n)] for y in range(h) for x in range(w)]
    if kind=='spatial':op=op['operator'];kind=op['type']
    if kind=='mosaic':
        if op['size']==1:return copy.deepcopy(p)
        block=op['size']*scale
        return [[sum(p[yy*w+xx][c] for yy in range(y//block*block,min(h,(y//block+1)*block)) for xx in range(x//block*block,min(w,(x//block+1)*block)))/((min(h,(y//block+1)*block)-y//block*block)*(min(w,(x//block+1)*block)-x//block*block)) for c in range(n)] for y in range(h) for x in range(w)]
    out=[]
    for y in range(h):
        for x in range(w):
            points=[]
            if kind in ['directional','radial']:
                count=op.get('samples',33)
                for j in range(count):
                    t=F(j,count-1)-F(1,2)
                    angle=F(str(op['angle']))*(t if kind=='radial' else 1)
                    if angle%90==0:
                        sn,cs=[(0,1),(1,0),(0,-1),(-1,0)][int(angle/90)%4]
                    else:sn,cs=map(F,(math.sin(math.radians(angle)),math.cos(math.radians(angle))))
                    if kind=='directional':points.append((x+cs*F(str(op['length']))*scale*t,y+sn*F(str(op['length']))*scale*t))
                    else:
                        a,b,c,d,e,f=map(F,world);cx,cy=map(F,op['center']);cx,cy=(a*cx+c*cy+e)*scale-F(1,2),(b*cx+d*cy+f)*scale-F(1,2)
                        u,v=F(x)-cx,F(y)-cy;q=1+F(str(op.get('zoom',0)))*t
                        points.append((cx+(u*cs-v*sn)*q,cy+(u*sn+v*cs)*q))
            elif kind=='offset':points=[(F(x)-F(str(op['offset'][0]))*scale,F(y)-F(str(op['offset'][1]))*scale)]
            elif kind=='displace':
                m=op['map'];point=inverse(world,[(x+.5)/scale,(y+.5)/scale]);point=inverse(m.get('transform',[1,0,0,1,0,0]),point)
                if m.get('sampling','nearest')=='nearest':
                    xx=min(m['width']-1,max(0,math.floor(point[0])));yy=min(m['height']-1,max(0,math.floor(point[1])));v=list(map(F,m['vectors'][yy*m['width']+xx]))
                else:v=sample([list(map(F,r)) for r in m['vectors']],m['width'],m['height'],max(0,min(m['width']-1,point[0]-.5)),max(0,min(m['height']-1,point[1]-.5)),'clamp')
                points=[(x+v[0]*F(str(op['amount'][0]))*scale,y+v[1]*F(str(op['amount'][1]))*scale)]
            else:raise AssertionError(kind)
            values=[sample(p,w,h,a,b,border) for a,b in points]
            out.append([sum(v[c] for v in values)/len(values) for c in range(n)])
    return out


def operators():
    return [dict(type='box',radius=1),dict(type='gaussian',sigma=.6),dict(type='directional',length=2.5,angle=90,samples=5),dict(type='radial',center=[2.5,1.5],angle=180,zoom=.5,samples=3),dict(type='spatial',operator=dict(type='offset',offset=[.5,-1.25])),dict(type='spatial',operator=dict(type='displace',map=dict(width=2,height=2,vectors=[[0,1],[-1,.5],[.5,-1],[1,0]],sampling='bilinear',transform=[2,0,0,1.5,.25,-.5]),amount=[1.5,.5])),dict(type='spatial',operator=dict(type='mosaic',size=2))]


class NativeFilterTests(unittest.TestCase):
    invoke=coverage.NativeCoverageTests.invoke
    document=coverage.NativeCoverageTests.document
    planes=coverage.NativeCoverageTests.planes
    values=coverage.NativeCoverageTests.values
    assertValues=coverage.NativeCoverageTests.assertValues
    edit=coverage.NativeCoverageTests.edit
    export=coverage.NativeCoverageTests.export
    colors=[[F(1,2),F(1,4),F(1,8),F(0),F(0)],[F(1,8),F(3,4),F(0),F(1,4),F(0)],[F(0)]*4+[F(3,4)]]

    def scene(self,w=5,h=3):
        d=self.document(w,h);d['swatches']['p']=color(list(map(float,self.colors[1][:4])))
        alpha=[F([0,1,3,4][(x+2*y)%4],4) for y in range(h) for x in range(w)]
        colors=[self.colors[(x+y)%3] for y in range(h) for x in range(w)]
        d['items']=[group('art')]+[fill(f'cell{i}',named(['b','p','s'][(i%w+i//w)%3],tint=.75 if (i%w+i//w)%3==2 else 1,opacity=float(a)),box=(i%w,i//w,1,1),parent='art') for i,a in enumerate(alpha)]
        return d,[list(c*a for c in color)+[a] for color,a in zip(colors,alpha)]

    def filtered(self,d,op,border='transparent',**kw):
        d=copy.deepcopy(d);d['items'][0]['filters']=[dict(id='filter',operator=op,border=border,**kw)];return d

    def assertRows(self,d,expected,**kw):
        for actual,row in zip(self.values(d,**kw),expected,strict=True):
            self.assertTrue(all(v==0 for v in row[len(actual):5]))
            self.assertValues(actual,row[:len(actual)],4e-12)

    def test_seven_native_transports_all_borders_full_neighborhood_reference(self):
        for w,h in [(5,3),(1,1),(1,4),(4,1)]:
            d,p=self.scene(w,h)
            for op,border in itertools.product(operators(),['transparent','clamp','wrap','reflect']):
                with self.subTest(size=(w,h),operator=op,border=border):self.assertRows(self.filtered(d,op,border),transport(p,w,h,op,border))

    def test_source_and_named_ink_policy_survive_spatial_transport(self):
        # Enumerate possible paint coverage at each sampled position against the
        # output-position backdrop; the backdrop is never blurred or displaced.
        w,h=5,3;back=self.colors[1]
        for kind,policy,op in itertools.product(['b','s'],['knockout','preserve','preserve_nonzero'],operators()):
            d=self.document(w,h);d['swatches']['p']=color(list(map(float,back[:4])))
            c=self.colors[0 if kind=='b' else 2];address=addresses(c,policy,kind=='s')
            a=[F(5,8) if 1<=x<4 and y==1 else F(0) for y in range(h) for x in range(w)]
            d['items']=[fill('back',named('p'),box=(0,0,w,h)),fill('ink',named(kind,opacity=.625,tint=.75 if kind=='s' else 1,overprint=policy),box=(1,1,3,1),filters=[dict(id='filter',operator=op,border='reflect')])]
            weights=transport([[v] for v in a],w,h,op,'reflect',world=[1,0,0,1,1,1])
            expected=[[b*(1-q[0])+v*q[0] if take else b for v,b,take in zip(c,back,address)] for q in weights]
            with self.subTest(kind=kind,policy=policy,op=op):self.assertRows(d,expected)

    def test_replacement_all_modes_uses_intrinsic_content_before_item_blend(self):
        d,p=self.scene();op=operators()[0];q=transport(p,5,3,op,'reflect');weight=F(3,8)
        for mode in MODES:
            expected=[]
            for old,new in zip(p,q):
                a,b=old[-1],new[-1];before=old[:5];after=[v/b if b else 0 for v in new[:5]]
                composed,_=over(before,a,after,b,[True]*5,mode)
                replacement=[v-(1-b)*base for v,base in zip(composed,before)]
                expected.append([(1-weight)*v+weight*r for v,r in zip(before,replacement)])
            self.assertRows(self.filtered(d,op,'reflect',blend=mode,opacity=float(weight)),expected)

    def test_nonnormal_overprint_closes_only_filtered_replacement(self):
        for mode in ['multiply','color','difference','darken']:
            d=self.document(3,1);d['swatches']['p']=color(list(map(float,self.colors[1][:4])))
            c=self.colors[0];back=self.colors[1];address=addresses(c,'preserve_nonzero');a=[F(0),F(3,4),F(0)];b=[F(1,4)]*3;weight=F(1,2)
            d['items']=[fill('back',named('p'),box=(0,0,3,1)),fill('ink',named('b',opacity=.75,overprint='preserve_nonzero'),box=(1,0,1,1),filters=[dict(id='filter',operator=dict(type='directional',length=2,angle=0,samples=3),blend=mode,opacity=.5)])]
            expected=[]
            for aa,bb in zip(a,b):
                intrinsic=[v*aa if take else F(0) for v,take in zip(c,address)]
                composed,_=over(intrinsic,aa,c,bb,address,mode)
                replacement=[v-(1-bb)*base for v,base in zip(composed,intrinsic)]
                original,_=over(back,F(1),c,aa,address)
                expected.append([(1-weight)*v+weight*(r+(1-bb)*bg) for v,r,bg in zip(original,replacement,back)])
            self.assertRows(d,expected)

    def test_ordered_stack_mask_then_effects_and_item_controls(self):
        d,p=self.scene();a,b=operators()[0],operators()[4];mask=[0,64,128,192,255]*3
        d['items'][0]['filters']=[dict(id='first',operator=a,border='reflect',opacity=.5,mask=dict(width=5,height=3,gray_hex=bytes(mask).hex())),dict(id='second',operator=b,border='wrap')]
        q=transport(p,5,3,a,'reflect');p=[[(1-F(m,510))*old+F(m,510)*new for old,new in zip(x,y)] for m,x,y in zip(mask,p,q)];p=transport(p,5,3,b,'wrap')
        fx=effect('shadow','shadow',named('s',tint=.75,opacity=.5,overprint='preserve'),sigma=0,offset=[1,0]);d['items'][0].update(effects=[fx],fill_opacity=.25,opacity=.625)
        expected=decorate([[v/r[-1] if r[-1] else F(0) for v in r[:5]] for r in p],[r[-1] for r in p],5,3,[fx],lambda e,i:(self.colors[2],F(1,2),[False]*4+[True]),fill_opacity=F(1,4))
        self.assertRows(d,[[v*F(5,8) for v in row] for row,a in expected])

    def test_knockout_shape_is_filtered_separately_from_intrinsic_opacity(self):
        d=self.document(5,1);d['swatches']['p']=color(list(map(float,self.colors[1][:4])))
        d['items']=[group('outer',knockout=True),fill('previous',named('p'),box=(0,0,5,1),parent='outer'),group('art',parent='outer',filters=[dict(id='blur',operator=dict(type='directional',length=2,angle=0,samples=3))]),fill('ink',named('b',opacity=.75),box=(2,0,1,1),parent='art',opacity=.25)]
        shape=[F(0),F(1,4),F(1,4),F(1,4),F(0)]
        expected=[[b*(1-s)+v*s/4 for b,v in zip(self.colors[1],self.colors[0])] for s in shape];self.assertRows(d,expected)

    def test_faint_filtered_coverage_can_be_amplified_without_lost_process_inks(self):
        for tiny in [1e-20,1e-200]:
            d=self.document(3,1);f=effect('boost','overlay',named('s',tint=.75,overprint='preserve'));f['contour']=[[0,0],[tiny/3,1],[1,1]]
            d['items']=[fill('ink',named('b',opacity=tiny),box=(1,0,1,1),filters=[dict(id='blur',operator=dict(type='directional',length=2,angle=0,samples=3))],effects=[f])]
            self.assertRows(d,[self.colors[0][:4]+[F(3,4)]]*3)

    def test_scale_transforms_and_supersampling_follow_declared_coordinates(self):
        d,p=self.scene(3,2)
        for op in operators():
            for scale in [1,2]:
                # Expanded original cells are an exact source reference at this scale.
                w,h=3*scale,2*scale;source=[p[(y//scale)*3+x//scale] for y in range(h) for x in range(w)]
                expected=transport(source,w,h,op,'wrap',scale=scale)
                actual=self.filtered(d,op,'wrap');points=[[x,y] for y in range(h) for x in range(w)]
                self.assertRows(actual,expected,points=points,raster_scale=scale)
        op=operators()[1];source=[p[(y//2)*3+x//2] for y in range(4) for x in range(6)];q=transport(source,6,4,op,'reflect',scale=2)
        expected=[[sum(q[(y*2+dy)*6+x*2+dx][c] for dy in range(2) for dx in range(2))/4 for c in range(6)] for y in range(2) for x in range(3)]
        self.assertRows(self.filtered(d,op,'reflect'),expected,antialias='supersample2')

    def test_clipped_member_filters_precede_stack_and_preserve_filtered_base_alpha(self):
        d=self.document(5,1);base=[F(0),F(1,4),F(1,4),F(1,4),F(0)];top=[F(0),F(0),F(1,6),F(1,6),F(1,6)]
        d['items']=[fill('base',named('b',opacity=.75),box=(2,0,1,1),opacity=.5,filters=[dict(id='baseblur',operator=dict(type='directional',length=2,angle=0,samples=3))]),fill('top',named('s',tint=.75,opacity=.5,overprint='preserve'),box=(3,0,1,1),clip_to='base',filters=[dict(id='topblur',operator=dict(type='directional',length=2,angle=0,samples=3))])]
        self.assertRows(d,[[v*a/2 for v in self.colors[0][:4]]+[F(3,4)*a*b/2] for a,b in zip(base,top)])

    def test_profiled_float_source_converts_before_native_filtering(self):
        from test_native_images_cli import process
        from test_samples_cli import layer
        from test_profiles_cli import embedded, linear_profile
        values=[[.125,.25,.5,.75],[.5,.75,.25,.25],[.75,.125,.25,1],[.25,.5,.75,0]]
        d=self.document(4,1);item=layer([v for p in values for v in p],depth='f32',w=4);profile=linear_profile();item['content']['grid'].update(encoding='profiled_rgb',profile=embedded(profile));d['items']=[item]
        # The source profile is a deliberately linear original matrix profile.
        # Use the profile fixture's declared matrix, not an implicit display conversion.
        import struct
        tags={profile[132+j*12:136+j*12]:struct.unpack_from('>II',profile,136+j*12) for j in range(struct.unpack_from('>I',profile,128)[0])}
        matrix=[[struct.unpack_from('>i',profile,tags[tag][0]+8+4*c)[0]/65536 for tag in [b'rXYZ',b'gXYZ',b'bXYZ']] for c in range(3)]
        expected_color=[process(v[:3],matrix=matrix,gamma=1) for v in values]
        p=[[F(str(v))*F(str(raw[3])) for v in ink]+[F(str(raw[3]))] for ink,raw in zip(expected_color,values)]
        for op in operators():
            doc=copy.deepcopy(d);doc['items'][0]['filters']=[dict(id='filter',operator=op,border='reflect')];expected=transport(p,4,1,op,'reflect')
            for actual,row in zip(self.values(doc),expected):self.assertValues(actual,row[:4],.00008)

    def test_native_channel_work_limit_timeout_and_no_partial_publication(self):
        from test_profiles_cli import embedded
        from cmyk_fixtures import cmyk_profile
        d=self.document(512,512);d['items']=[fill('ink',named('b'),box=(0,0,512,512),filters=[dict(id='blur',operator=dict(type='gaussian',sigma=16),enabled=False)])]
        original=copy.deepcopy(d);self.planes(d);d['items'][0]['filters'][0]['enabled']=True
        self.assertEqual(self.planes(d,1)['code'],'RESOURCE_LIMIT')
        with tempfile.TemporaryDirectory() as root:
            output=dict(output_root=root,file_name='filter.pdf',format='pdf',pdf_options=dict(prepress=dict(profile=embedded(cmyk_profile()),spot_fallback='multiplicative_declared')))
            error=self.invoke(dict(command='document.publish',document=d,output=output,control=dict(timeout_ms=0)),1);self.assertEqual(error['code'],'TIMEOUT');self.assertFalse((Path(root)/'filter.pdf').exists())
        d['items'][0]['filters'][0]['enabled']=False;self.assertEqual(d,original)

    def test_maximum_named_channels_keep_separate_ink_transport(self):
        from test_vector_plates_cli import spot
        d=self.document(7,4);d['swatches']={f's{i:02}':spot() for i in range(28)}
        d['items']=[group('art')]+[fill(f'c{i}',named(f's{i:02}',tint=.625,opacity=.75),box=(i%7,i//7,1,1),parent='art') for i in range(28)]
        op=operators()[0];d['items'][0]['filters']=[dict(id='filter',operator=op,border='wrap')]
        p=[[F(0)]*4+[F(15,32) if c==i else F(0) for c in range(28)]+[F(3,4)] for i in range(28)]
        for actual,wanted in zip(self.values(d),transport(p,7,4,op,'wrap')):self.assertValues(actual,wanted[:32],4e-12)

    def test_selected_artboard_bleed_preserves_local_filter_fields(self):
        for op,scale in itertools.product(operators(),[1,2]):
            d=self.document(12,8,kind='vector');d['items']=[dict(id='board',transform=[1,0,0,1,7,3],content=dict(type='frame',frame=dict(role='artboard',width=4,height=3,bleed=dict(left=1,right=1,top=1,bottom=1))),filters=[dict(id='filter',operator=op,border='wrap')]),dict(id='ink',parent='board',content=dict(type='vector',geometry=dict(shape='rect',x=1,y=1,width=1,height=1),fill=named('b',opacity=.75)))]
            w,h=6*scale,5*scale;source=[[v*F(3,4) if 2*scale<=x<3*scale and 2*scale<=y<3*scale else F(0) for v in self.colors[0]] for y in range(h) for x in range(w)]
            expected=transport(source,w,h,op,'wrap',scale=scale,world=[1,0,0,1,1,1]);points=[[x,y] for y in range(h) for x in range(w)][:64]
            result=self.planes(d,artboard_id='board',include_bleed=True,raster_scale=scale,samples=points);self.assertEqual((result['width'],result['height']),(w,h))
            for point,value in zip(points,result['samples']):self.assertValues(value['ink_fractions'],expected[point[1]*w+point[0]][:4],4e-12)

    def test_disabled_and_zero_weight_filters_preserve_source_and_context_validation(self):
        d,p=self.scene()
        for kw in [dict(enabled=False),dict(opacity=0)]:self.assertRows(self.filtered(d,dict(type='surface',radius=1,threshold=.25),**kw),p)
        d['items'][0]['content']['isolated']=False
        self.assertEqual(self.planes(self.filtered(d,dict(type='surface',radius=1,threshold=.25)),1)['code'],'UNSUPPORTED')

    def test_exact_PDF_transport_capability_receipts_and_durable_history(self):
        d,_=self.scene();d=self.invoke(dict(command='document.validate',document=d));original=copy.deepcopy(d);c=Client();c.initialize();self.addCleanup(c.close)
        with tempfile.TemporaryDirectory() as root:
            s=dict(session_root=str(Path(root)/'sessions'),session_id='native-filters');c.success('session.create',**s,request_id='create',document=d);before=self.planes(d)
            req=dict(request_id='filter',expected_revision=0,action=dict(type='edit',operations=[dict(op='filters',id='art',filters=[dict(id='blur',operator=operators()[1],border='reflect')])]))
            changed=c.success('session.apply',**s,**req)['document'];after=self.planes(changed);self.assertNotEqual(before['interleaved_sha256'],after['interleaved_sha256']);artifact=self.export(changed)
            self.assertEqual(hashlib.sha256(page_image(pdf_reader.Pdf(artifact))[1]).hexdigest(),after['interleaved_sha256'])
            cap=self.invoke(dict(command='capabilities'))['native_prepress']['filters'];self.assertEqual(cap,after['coverage_sources']['filters']);self.assertEqual(after['coverage_sources'],artifact['pages'][0]['coverage_sources'])
            undo=c.success('session.apply',**s,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'];self.assertEqual(self.planes(undo)['interleaved_sha256'],before['interleaved_sha256'])
            c.success('session.apply',**s,request_id='redo',expected_revision=2,action=dict(type='redo'));self.assertTrue(c.success('session.apply',**s,**req)['replayed']);self.assertTrue(c.success('session.verify',**s)['valid']);self.assertEqual(d,original)


if __name__=='__main__':unittest.main()
