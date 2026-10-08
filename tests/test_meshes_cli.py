"""Original mesh fixtures: rational bilinear and Hermite/Newton reference models."""
import base64
import copy
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import random
import tempfile
import unittest
import xml.etree.ElementTree as ET
import test_editing_cli as editing
import test_artwork_masks_cli as masks
import test_boards_cli as boards
from test_mcp import Client

NS='{http://www.w3.org/2000/svg}'


def mesh(columns=2,rows=2,size=(16,12),origin=(0,0),deform=False):
    knots=[]
    for y in range(rows):
        for x in range(columns):
            # Interior colors keep the independent smooth Hermite fixture away
            # from gamut limiting. Other tests deliberately exercise that limit.
            color=[max(0,min(255,c)) for c in [50+19*x+7*y,180-13*x-17*y,70+6*x*y,64+15*x+23*y]]
            offset=[.19*math.sin(x+y),-.13*math.cos(x-y)] if deform and 0<x<columns-1 and 0<y<rows-1 else [0,0]
            knots.append(dict(color=color,offset=offset))
    return dict(origin=list(origin),size=list(size),columns=columns,rows=rows,knots=knots,svg_samples_per_cell=16)


def decode(v):return v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4
def encode(v):return v*12.92 if v<=.0031308 else 1.055*v**(1/2.4)-.055
def byte(v):return max(0,min(255,math.floor(v*255+.5)))
def quantize(v):return bytes(map(byte,v)) if byte(v[3]) else bytes(4)
def paint(m,space='srgb',**kw):return dict(type='mesh',mesh=m,space=space,**kw)
def rect(p,id='art',**kw):return masks.rect(id,w=24,h=20,color=p,**kw)


def hermite(data,w,h,u,v,derivative=None):
    """Tensor Hermite basis directly from node differences, no Bezier controls."""
    x=min(int(u),w-2);y=min(int(v),h-2);a=u-x;b=v-y
    def basis(t):return ([2*t**3-3*t*t+1,-2*t**3+3*t*t],[t**3-2*t*t+t,t**3-t*t])
    hu,gu=basis(a);hv,gv=basis(b)
    def dbasis(t):return ([6*t*t-6*t,-6*t*t+6*t],[3*t*t-4*t+1,3*t*t-2*t])
    if derivative==0:hu,gu=dbasis(a)
    if derivative==1:hv,gv=dbasis(b)
    def node(i,j):return data[j*w+i]
    def du(i,j):
        lo=max(0,i-1);hi=min(w-1,i+1);return [(a-b)/(hi-lo) for a,b in zip(node(hi,j),node(lo,j))]
    def dv(i,j):
        lo=max(0,j-1);hi=min(h-1,j+1);return [(a-b)/(hi-lo) for a,b in zip(node(i,hi),node(i,lo))]
    def cross(i,j):
        lo=max(0,j-1);hi=min(h-1,j+1);return [(a-b)/(hi-lo) for a,b in zip(du(i,hi),du(i,lo))]
    result=[0.0]*len(data[0])
    for j in range(2):
        for i in range(2):
            for values,weight in [(node(x+i,y+j),hu[i]*hv[j]),(du(x+i,y+j),gu[i]*hv[j]),(dv(x+i,y+j),hu[i]*gv[j]),(cross(x+i,y+j),gu[i]*gv[j])]:
                for c in range(len(result)):result[c]+=values[c]*weight
    return result


def point_at(m,u,v):
    offset=hermite([k['offset'] for k in m['knots']],m['columns'],m['rows'],u,v)
    return [m['origin'][c]+(u if c==0 else v)*m['size'][c]/(m['columns' if c==0 else 'rows']-1)+offset[c] for c in range(2)]


def color_at(m,u,v,space='srgb'):
    values=[[decode(c/255) if i<3 and space=='linear_rgb' else c/255 for i,c in enumerate(k['color'])] for k in m['knots']]
    result=hermite(values,m['columns'],m['rows'],u,v)
    return [encode(c) if i<3 and space=='linear_rgb' else c for i,c in enumerate(result)]


def sample(m,p,space='srgb'):
    if any(not m['origin'][i]<=p[i]<=m['origin'][i]+m['size'][i] for i in range(2)):return [0]*4
    uv=[(p[i]-m['origin'][i])/m['size'][i]*(m['columns' if i==0 else 'rows']-1) for i in range(2)]
    # Independent Newton inversion with numerical Jacobian; the engine uses a
    # fixed-point contraction in normalized coordinates instead.
    for _ in range(12):
        f=point_at(m,*uv);error=[f[i]-p[i] for i in range(2)]
        if max(map(abs,error))<1e-12:break
        jac=[]
        for axis,n in enumerate((m['columns'],m['rows'])):
            lo=uv.copy();hi=uv.copy();lo[axis]=max(0,uv[axis]-1e-5);hi[axis]=min(n-1,uv[axis]+1e-5)
            a=point_at(m,*lo);b=point_at(m,*hi);jac.append([(b[c]-a[c])/(hi[axis]-lo[axis]) for c in range(2)])
        a,c=jac[0];b,d=jac[1];det=a*d-b*c
        uv[0]-=(d*error[0]-b*error[1])/det;uv[1]-=(-c*error[0]+a*error[1])/det
        uv=[max(0,min(n-1,v)) for n,v in zip((m['columns'],m['rows']),uv)]
    assert max(abs(a-b) for a,b in zip(point_at(m,*uv),p))<1e-9
    return color_at(m,*uv,space)


class MeshTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def document(self,m=None,space='srgb',kind='vector',items=None,width=24,height=20):
        d=self.invoke(dict(command='document.create',id='original-mesh',kind=kind,width=width,height=height))
        if items is None:
            p=paint(m or mesh(),space)
            items=[rect(p)] if kind=='vector' else [dict(id='art',content=dict(type='fill',width=width,height=height,paint=p))]
        return self.edit(d,[dict(op='add',item=i) for i in items])
    def edit(self,d,operations,expected=0):
        r=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=operations),expected)
        return r if expected else r['document']
    def inspect(self,m,parameters,space='srgb',expected=0):return self.invoke(dict(command='mesh.inspect',mesh=m,parameters=parameters,space=space),expected)
    def export(self,d,format='png',expected=0,**kw):return self.invoke(dict(command='document.export',document=d,format=format,**kw),expected)
    def pixels(self,d,scale=1):
        a=self.export(d,scale=scale);w,h,p,_=editing.png_pixels(base64.b64decode(a['data']))
        self.assertEqual(p,bytes.fromhex(self.invoke(dict(command='document.render',document=d,scale=scale))['data']))
        return w,h,p
    def assert_pixels(self,d,oracle,scale=1,tolerance=1):
        w,h,p=self.pixels(d,scale)
        for y in range(h):
            for x in range(w):
                actual=p[(y*w+x)*4:][:4];expected=quantize(oracle(((x+.5)/scale,(y+.5)/scale)))
                self.assertLessEqual(max(abs(a-b) for a,b in zip(actual,expected)),tolerance,(x,y,actual,expected))

    def test_four_corners_rational_bilinear_all_pixels_and_persistence(self):
        m=mesh();m['knots']=[dict(color=c,offset=[0,0]) for c in [[255,0,0,255],[0,255,0,192],[0,0,255,32],[255,255,0,128]]]
        d=self.document(m);saved=self.export(d,'snapshot');restored=json.loads(saved['data'])
        self.assertEqual(restored,d);self.assertEqual(restored['items'][0]['content']['fill']['mesh'],m)
        def oracle(p):
            x,y=map(F,p)
            if not 0<=x<=16 or not 0<=y<=12:return [0]*4
            u=x/16;v=y/12;weights=[(1-u)*(1-v),u*(1-v),(1-u)*v,u*v]
            return [sum(F(k['color'][c],255)*w for k,w in zip(m['knots'],weights)) for c in range(4)]
        for scale in (1,2):self.assert_pixels(restored,oracle,scale)
        self.assertGreater(len(set(self.pixels(d)[2][::4])),20)
        corners=self.inspect(m,[[0,0],[1,0],[0,1],[1,1]])['samples']
        self.assertEqual([list(quantize(s['encoded_rgba'])) for s in corners],[k['color'] for k in m['knots']])

    def test_linear_light_alpha_and_raster_fill_share_independent_values(self):
        m=mesh(3,3,deform=True)
        for kind in ('vector','raster'):
            d=self.document(m,'linear_rgb',kind)
            self.assert_pixels(d,lambda p:sample(m,p,'linear_rgb'))
            changed=self.edit(d,[dict(op='mesh_knot',id='art',column=1,row=1,color=[90,110,100,24],offset=[.1,-.2])])
            edited=copy.deepcopy(m);edited['knots'][4]=dict(color=[90,110,100,24],offset=[.1,-.2])
            self.assert_pixels(changed,lambda p:sample(edited,p,'linear_rgb'))
            self.assertEqual(d['items'][0]['content']['fill' if kind=='vector' else 'paint']['mesh'],m)

    def test_deformed_grid_matches_independent_hermite_newton_and_derivatives(self):
        m=mesh(4,4,size=(18,15),origin=(1.25,-.75),deform=True);rng=random.Random(19)
        params=[[rng.random()*3,rng.random()*3] for _ in range(96)]+[[x,y] for x in range(4) for y in range(4)]
        report=self.inspect(m,params);self.assertLess(report['geometry_contraction_upper_bound'],.75)
        for s,(u,v) in zip(report['samples'],params):
            for a,b in zip(s['point'],point_at(m,u,v)):self.assertAlmostEqual(a,b,11)
            for a,b in zip(s['encoded_rgba'],color_at(m,u,v)):self.assertAlmostEqual(a,b,12)
            for a,b in zip(s['inverse_parameter'],(u,v)):self.assertAlmostEqual(a,b,11)
            self.assertGreater(s['jacobian'],0)
            if 1e-5<u<3-1e-5 and 1e-5<v<3-1e-5:
                for axis,name in [(0,'tangent_u'),(1,'tangent_v')]:
                    expected=hermite([k['offset'] for k in m['knots']],4,4,u,v,axis)
                    expected[axis]+=m['size'][axis]/3
                    for a,b in zip(s[name],expected):self.assertAlmostEqual(a,b,11)
        self.assert_pixels(self.document(m),lambda p:sample(m,p))

    def test_c1_joins_color_geometry_transparency_and_extreme_color_limiting(self):
        m=mesh(4,4,deform=True)
        m['knots']=[dict(k,color=([255,0,255,0] if i%3 else [0,255,0,255])) for i,k in enumerate(m['knots'])]
        params=[]
        for axis in (0,1):
            for join in (1,2):
                for along in (.1,.65,1,1.6,2.9):
                    for delta in (-1e-8,0,1e-8):
                        p=[along,along];p[axis]=join+delta;params.append(p)
        r=self.inspect(m,params)
        for i in range(0,len(params),3):
            for field in ('point','tangent_u','tangent_v','interpolated_rgba','color_du','color_dv'):
                for a,b in zip(r['samples'][i][field],r['samples'][i+2][field]):self.assertLess(abs(a-b),2e-6)
        rng=random.Random(81);samples=self.inspect(m,[[rng.random()*3,rng.random()*3] for _ in range(1000)])['samples']
        for s in samples:
            self.assertTrue(all(-1e-14<=v<=1+1e-14 for v in s['interpolated_rgba']))
            self.assertGreater(s['jacobian'],0)
        corners=self.inspect(m,[[x,y] for y in range(4) for x in range(4)])['samples']
        for k,s in zip(m['knots'],corners):
            for a,b in zip(k['color'],s['interpolated_rgba']):self.assertAlmostEqual(a/255,b,14)

    def test_paint_transform_reflection_shear_and_parent_hierarchy(self):
        m=mesh(3,3,size=(9,8),origin=(-1.25,.5),deform=True)
        matrix=[-1,.25,.5,1,12,2];parent=[1,0,0,1,2,1]
        d=self.document(items=[masks.group('parent',transform=parent),rect(paint(m,transform=matrix),parent='parent',transform=[1,0,0,1,0,0])])
        def oracle(p):
            x,y=p[0]-2,p[1]-1
            if x<0 or y<0:return [0]*4
            return sample(m,masks.inverse(matrix,(x,y)))
        self.assert_pixels(d,oracle)

    def test_mesh_strokes_editable_and_transparent_outside_domain(self):
        m=mesh();item=rect(None);item['content'].pop('fill');item['content']['geometry']=dict(shape='rect',x=2,y=2,width=12,height=8)
        item['content']['stroke']=dict(width=2,color=paint(m))
        d=self.document(items=[item]);self.assert_pixels(d,lambda p:sample(m,p) if 1<p[0]<15 and 1<p[1]<11 and not(3<p[0]<13 and 3<p[1]<9) else [0]*4)
        changed=self.edit(d,[dict(op='mesh_knot',id='art',target='stroke',column=1,row=1,color=[80,60,140,2])])
        self.assertEqual(changed['items'][0]['content']['stroke']['color']['mesh']['knots'][3]['color'],[80,60,140,2])
        self.assertNotEqual(self.pixels(d)[2],self.pixels(changed)[2])

    def test_shared_artwork_mask_uses_continuous_mesh_alpha(self):
        m=mesh(3,3,deform=True)
        source=masks.source();ink=rect([40,90,150,255],id='ink',artwork_mask=dict(source='source',region=[0,0,24,20],mode='alpha'))
        d=self.document(items=[source,rect(paint(m),parent='source'),ink])
        self.assert_pixels(d,lambda p:[40/255,90/255,150/255,sample(m,p)[3]])
        export=self.export(d,'svg');self.assertTrue(export['mesh_textures']);self.assertIn('<mask ',export['data'])

    def test_svg_tile_pixels_bounds_and_explicit_editability_loss(self):
        for space in ('srgb','linear_rgb'):
            m=mesh(3,3,deform=True);m['svg_samples_per_cell']=12
            d=self.document(m,space);before=copy.deepcopy(d);a=self.export(d,'svg');root=ET.fromstring(a['data']);report=a['mesh_textures'][0]
            self.assertTrue(any('snapshot' in s.lower() and 'mesh' in s.lower() for s in a['losses']))
            pattern=root.find(NS+'defs/'+NS+'pattern');image=pattern.find(NS+'image');raw=base64.b64decode(image.get('href').split(',')[1]);w,h,p,_=editing.png_pixels(raw)
            self.assertEqual(report['dimensions'],[24,24]);self.assertEqual(report['sha256'],hashlib.sha256(raw).hexdigest())
            self.assertEqual(pattern.get('viewBox'),f"{pattern.get('x')} {pattern.get('y')} {pattern.get('width')} {pattern.get('height')}")
            bounds=report['premultiplied_interior_reconstruction_error_bound'];rng=random.Random(51)
            for y in range(h):
                for x in range(w):
                    expected=quantize(sample(m,[(x+.5)/w*16,(y+.5)/h*12],space));actual=p[(y*w+x)*4:][:4]
                    self.assertLessEqual(max(abs(a-b) for a,b in zip(actual,expected)),1)
            # Convex bilinear texture reconstruction in premultiplied space.
            for _ in range(100):
                tx=.5+rng.random()*(w-2);ty=.5+rng.random()*(h-2);ix=int(tx);iy=int(ty);dx=tx-ix;dy=ty-iy
                approx=[0.0]*4
                for xx,yy,weight in [(ix,iy,(1-dx)*(1-dy)),(ix+1,iy,dx*(1-dy)),(ix,iy+1,(1-dx)*dy),(ix+1,iy+1,dx*dy)]:
                    v=[b/255 for b in p[(yy*w+xx)*4:][:4]]
                    for c in range(4):approx[c]+=weight*(v[c]*v[3] if c<3 else v[3])
                truth=sample(m,[(tx+.5)/w*16,(ty+.5)/h*12],space)
                for c in range(4):self.assertLessEqual(abs(approx[c]-(truth[c]*truth[3] if c<3 else truth[3])),bounds[c])
            self.assertEqual(d,before)
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'mesh.svg';path.write_text(a['data'],encoding='utf8')
                failure=self.invoke(dict(command='svg.import',source=dict(kind='text',text=path.read_text(encoding='utf8')),id='imported'),1)
                self.assertEqual(failure['code'],'SVG_UNSUPPORTED')

    def test_svg_pattern_extent_covers_transformed_shared_mask_placements(self):
        m=mesh(size=(1,1));source=masks.source()
        target=rect([255]*4,id='ink',artwork_mask=dict(source='source',region=[0,0,24,20],mode='alpha',transform=[1,0,0,1,-90,0]))
        d=self.document(items=[source,rect(paint(m),parent='source'),target]);root=ET.fromstring(self.export(d,'svg')['data']);p=root.find(NS+'defs/'+NS+'pattern')
        lo=float(p.get('x'));hi=lo+float(p.get('width'))
        self.assertLess(lo,0);self.assertGreater(hi,114)

    def test_invalid_grids_offsets_folds_fields_and_sample_limits_fail(self):
        candidates=[]
        for key,value in [('columns',1),('rows',9),('knots',[]),('size',[0,1]),('origin',[32768,0]),('svg_samples_per_cell',0),('svg_samples_per_cell',257)]:
            m=mesh();m[key]=value;candidates.append(m)
        m=mesh();m['knots'][0]['offset']=[.1,0];candidates.append(m)
        m=mesh(3,3);m['knots'][4]['offset']=[10,10];candidates.append(m)
        m=mesh(8,8);m['svg_samples_per_cell']=256;candidates.append(m)
        for m in candidates:self.inspect(m,[],expected=1)
        self.assertEqual(self.inspect(candidates[-2],[],expected=1)['code'],'MESH_GEOMETRY_LIMIT')
        self.inspect(mesh(),[[1.1,0]],expected=1);self.inspect(mesh(),[[0,0]]*1025,expected=1)
        m=mesh();m['unknown']=True;self.assertEqual(self.inspect(m,[],expected=1)['code'],'INVALID_REQUEST')

    def test_knot_edit_locks_atomic_rollback_and_strict_targets(self):
        d=self.document(mesh(3,3));before=copy.deepcopy(d)
        for kw in [dict(column=3,row=1,color=[0]*4),dict(column=1,row=1),dict(column=0,row=0,offset=[1,0]),dict(column=1,row=1,offset=[100,0]),dict(column=1,row=1,target='stroke',color=[0]*4)]:
            result=self.edit(d,[dict(op='metadata',value=dict(title='Must not escape rollback')),dict(op='mesh_knot',id='art',**kw)],1)
            self.assertEqual(result['operation_index'],1);self.assertEqual(d,before)
        for locked in ('art','parent'):
            items=[masks.group('parent'),rect(paint(mesh(3,3)),parent='parent')]
            d=self.document(items=items)
            next(i for i in d['items'] if i['id']==locked)['locked']=True
            self.assertEqual(self.edit(d,[dict(op='mesh_knot',id='art',column=1,row=1,color=[0]*4)],1)['code'],'LOCKED')

    def test_svg_and_render_work_budgets_are_preflighted(self):
        m=mesh();m['svg_samples_per_cell']=256
        d=self.document(items=[rect(paint(m),id=f'art{i}') for i in range(3)])
        self.assertEqual(self.export(d,'svg',1)['code'],'RESOURCE_LIMIT')
        d=self.document(mesh(3,3,deform=True),width=2048,height=1024)
        self.assertEqual(self.export(d,'png',1)['code'],'RESOURCE_LIMIT')

    def test_near_contraction_limit_inverse_and_independent_jacobian_bound(self):
        m=mesh(3,3);m['knots'][4]['offset']=[.1,-.05]
        bound=self.inspect(m,[])['geometry_contraction_upper_bound']
        m['knots'][4]['offset']=[v*.749/bound for v in m['knots'][4]['offset']]
        params=[[x/10,y/10] for y in range(21) for x in range(21)];r=self.inspect(m,params)
        self.assertAlmostEqual(r['geometry_contraction_upper_bound'],.749,12)
        for s,uv in zip(r['samples'],params):
            for a,b in zip(s['inverse_parameter'],uv):self.assertAlmostEqual(a,b,11)
            self.assertGreater(s['jacobian'],0)
            for axis,scale in enumerate((8,6)):
                du=s['tangent_u'][axis]/scale-(1 if axis==0 else 0)
                dv=s['tangent_v'][axis]/scale-(1 if axis==1 else 0)
                self.assertLessEqual(abs(du)+abs(dv),r['geometry_contraction_upper_bound'])
        m['knots'][4]['offset']=[v*1.01 for v in m['knots'][4]['offset']]
        self.assertEqual(self.inspect(m,[],expected=1)['code'],'MESH_GEOMETRY_LIMIT')

    def test_fractional_physical_boundaries_invert_exactly_at_all_grid_limits(self):
        rng=random.Random(721)
        fixtures=[mesh(4,4,size=(.01+rng.random()*3,.01+rng.random()*3),origin=(rng.random(),rng.random())) for _ in range(50)]
        fixtures+=[mesh(n,n,size=(.001,.003),origin=(32760,-32760)) for n in (2,8)]
        for m in fixtures:
            end=[m['columns']-1,m['rows']-1];params=[[0,0],[end[0],0],[0,end[1]],end]
            for s,uv in zip(self.inspect(m,params)['samples'],params):
                self.assertEqual(s['inverse_parameter'],uv)
                self.assertEqual(s['point'],[m['origin'][i]+(m['size'][i] if uv[i] else 0) for i in range(2)])
        m=mesh(size=(2,2),origin=(.5,.5))
        self.assert_pixels(self.document(m),lambda p:sample(m,p))

    def test_publication_mesh_receipt_hashes_create_only_and_semantic_diff(self):
        m=mesh(3,3,deform=True);d=self.document(m)
        edited=self.edit(d,[dict(op='mesh_knot',id='art',column=1,row=1,color=[100,90,80,70],offset=[.3,-.2])])
        diff=self.invoke(dict(command='document.diff',before=d,after=edited,compare_pixels=True))
        self.assertGreater(diff['rendered_pixels']['changed_pixels'],0);self.assertIn('content.fill',diff['items'][0]['fields'])
        with tempfile.TemporaryDirectory() as directory:
            for format in ('svg','png','tiff','snapshot'):
                output=dict(output_root=directory,file_name='mesh.'+('json' if format=='snapshot' else format),format=format)
                receipt=self.invoke(dict(command='document.publish',document=edited,output=output));data=(Path(directory)/output['file_name']).read_bytes()
                self.assertEqual(receipt['sha256'],hashlib.sha256(data).hexdigest())
                artifact=self.export(edited,format)
                if format=='svg':self.assertEqual(receipt['mesh_textures'],artifact['mesh_textures'])
                if format=='snapshot':self.assertEqual(json.loads(data),edited)
                self.assertEqual(self.invoke(dict(command='document.publish',document=edited,output=output),1)['code'],'OUTPUT_EXISTS')
                self.assertEqual((Path(directory)/output['file_name']).read_bytes(),data)

    def test_artboard_mesh_bleed_scale_ranges_and_aggregate_texture_limit(self):
        m=mesh(3,3,size=(18,14),origin=(-1,-1),deform=True);B=boards.BoardCliTests()
        items=[]
        for i in range(3):
            items+=[B.board(f'b{i}',16,12,x=8*i,bleed=dict(top=1,right=1,bottom=1,left=1)),rect(paint(m),id=f'm{i}',parent=f'b{i}')]
            items[-1]['content']['geometry']=dict(shape='rect',x=-1,y=-1,width=18,height=14)
        d=self.document(items=items,width=40,height=20);before=copy.deepcopy(d)
        a=self.invoke(dict(command='artboard.export',document=d,format='png',include_bleed=True,scale=2,selection=dict(type='range',start=0,end=2)))['artifacts']
        self.assertEqual([v['id'] for v in a],['b0','b1'])
        for entry in a:
            w,h,p,_=editing.png_pixels(base64.b64decode(entry['artifact']['data']));self.assertEqual((w,h),(36,28))
            for y in range(h):
                for x in range(w):
                    expected=quantize(sample(m,[(x+.5)/2-1,(y+.5)/2-1]));actual=p[(y*w+x)*4:][:4]
                    self.assertLessEqual(max(abs(a-b) for a,b in zip(actual,expected)),1)
        svg=self.invoke(dict(command='artboard.export',document=d,format='svg',include_bleed=True))['artifacts']
        self.assertEqual(len(svg),3);self.assertTrue(all(e['artifact']['mesh_textures'] for e in svg));self.assertEqual(d,before)
        for item in d['items']:
            if item['id'].startswith('m'):item['content']['fill']['mesh']['svg_samples_per_cell']=128
        result=self.invoke(dict(command='artboard.export',document=d,format='svg'),1)
        self.assertEqual(result['code'],'RESOURCE_LIMIT')

    def test_durable_agent_mesh_edit_retry_undo_redo_and_snapshot(self):
        c=Client();self.addCleanup(c.close);c.initialize();m=mesh(3,3,deform=True)
        self.assertEqual(c.success('mesh.inspect',mesh=m,parameters=[[1,1]]),self.inspect(m,[[1,1]]))
        with tempfile.TemporaryDirectory() as directory:
            session=dict(session_root=directory,session_id='mesh');d=self.document(m)
            d=c.success('session.create',**session,request_id='create',document=d)['document']
            action=dict(type='edit',operations=[dict(op='mesh_knot',id='art',column=1,row=1,color=[90,100,130,12],offset=[.25,-.2])])
            result=c.success('session.apply',**session,request_id='edit',expected_revision=d['revision'],action=action)
            retry=c.success('session.apply',**session,request_id='edit',expected_revision=d['revision'],action=action)
            self.assertTrue(retry.pop('replayed'));self.assertEqual(retry,{k:v for k,v in result.items() if k!='replayed'})
            edited=result['document'];self.assertEqual(edited['items'][0]['content']['fill']['mesh']['knots'][4]['offset'],[.25,-.2])
            undone=c.success('session.apply',**session,request_id='undo',expected_revision=edited['revision'],action=dict(type='undo'))['document']
            self.assertEqual(undone['items'],d['items'])
            redone=c.success('session.apply',**session,request_id='redo',expected_revision=undone['revision'],action=dict(type='redo'))['document']
            self.assertEqual(redone['items'],edited['items'])
            self.assertEqual(json.loads(c.success('document.export',document=redone,format='snapshot')['data']),redone)


if __name__=='__main__':unittest.main()
