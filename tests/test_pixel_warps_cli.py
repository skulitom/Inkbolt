"""Independent point, inverse, articulated-pose and native pixel warp oracles."""
import base64
import copy
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
import test_editing_cli as editing
import test_boards_cli as boards
from test_images_cli import canonical
from test_interpolation_cli import rect
from test_transform_policies_cli import matrix_product
from test_warps_cli import solve
from test_mcp import Client

def perspective():return dict(type='perspective',corners=[[2,2],[12,3],[11,12],[1,10]])
def mesh():return dict(type='mesh',columns=2,rows=2,points=[[2,2],[6,2],[10,2],[2,6],[7,5],[10,6],[2,10],[6,10],[10,10]])
def articulated():
    return dict(type='articulated',columns=2,rows=4,joints=[dict(pivot=[0,0],angle=0,translation=[2,2]),dict(parent=0,pivot=[4,4],angle=35)],weights=[[1-r/4,r/4] for r in range(5) for c in range(3)])
def chart(w=8,h=8):return bytes(v for y in range(h) for x in range(w) for v in [x*24,y*24,(x^y)*24,64+32*((x+y)%6)])
def node(d,id='pixels'):return next(i for i in d['items'] if i['id']==id)
def poses(s):
    out=[]
    for j in s['joints']:
        a=math.radians(j['angle']);sn=math.sin(a);cs=math.cos(a)
        if j['angle']%90==0:sn=round(sn);cs=round(cs)
        x,y=j['pivot'];tx,ty=j.get('translation',[0,0]);m=[cs,sn,-sn,cs,x-cs*x+sn*y+tx,y-sn*x-cs*y+ty]
        if j.get('parent') is not None:m=matrix_product(out[j['parent']],m)
        out.append(m)
    return out
def mesh_points(s,frame=(8,8)):
    c,r=s.get('columns',1),s.get('rows',1);src=[[frame[0]*x/c,frame[1]*y/r] for y in range(r+1) for x in range(c+1)]
    if s['type']=='mesh':dst=s['points']
    elif s['type']=='perspective':dst=[s['corners'][i] for i in [0,1,3,2]]
    else:
        matrices=poses(s);dst=[]
        for p,w in zip(src,s['weights']):
            mapped=[[m[0]*p[0]+m[2]*p[1]+m[4],m[1]*p[0]+m[3]*p[1]+m[5]] for m in matrices]
            dst.append([sum(wi*qi[k] for wi,qi in zip(w,mapped))/sum(w) for k in range(2)])
    triangles=[]
    for y in range(r):
        for x in range(c):
            a=y*(c+1)+x;triangles.extend([[a,a+1,a+c+2],[a,a+c+2,a+c+1]])
    return src,dst,triangles
def maps(s,frame=(8,8)):
    src,dst,triangles=mesh_points(s,frame);src=[[F(x) for x in p] for p in src];dst=[[F(x) for x in p] for p in dst]
    def bary(p,t):
        a,b,c=t;det=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
        u=((p[0]-a[0])*(c[1]-a[1])-(p[1]-a[1])*(c[0]-a[0]))/det
        v=((b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0]))/det
        return [1-u-v,u,v]
    if s['type']=='perspective':
        rows=[]
        for (u,v),(x,y) in zip([(0,0),(1,0),(1,1),(0,1)],s['corners']):rows.extend([[u,v,1,0,0,0,-F(x)*u,-F(x)*v,x],[0,0,0,u,v,1,-F(y)*u,-F(y)*v,y]])
        h=solve(rows)
        def forward(p):
            u,v=[F(x)/n for x,n in zip(p,frame)];w=h[6]*u+h[7]*v+1
            return [(h[0]*u+h[1]*v+h[2])/w,(h[3]*u+h[4]*v+h[5])/w]
        def inv(p):
            x,y=map(F,p);a=h[0]-x*h[6];b=h[1]-x*h[7];c=h[3]-y*h[6];d=h[4]-y*h[7];e=x-h[2];f=y-h[5];det=a*d-b*c
            if not det:return None
            q=[(e*d-b*f)/det*frame[0],(a*f-e*c)/det*frame[1]]
            return q if all(0<=v<=n for v,n in zip(q,frame)) else None
        return forward,inv
    def mapped(p,from_points,to_points):
        p=list(map(F,p))
        for ids in triangles:
            w=bary(p,[from_points[i] for i in ids])
            if min(w)>=0:return [sum(q*to_points[i][k] for q,i in zip(w,ids)) for k in range(2)]
        return None
    return lambda p:mapped(p,src,dst),lambda p:mapped(p,dst,src)
def sample(raw,w,h,p,method):
    def get(x,y):
        x=max(0,min(w-1,x));y=max(0,min(h-1,y));return raw[(y*w+x)*4:][:4]
    if method=='nearest':return get(math.floor(p[0]),math.floor(p[1]))
    x,y=p[0]-F(1,2),p[1]-F(1,2);ix,iy=math.floor(x),math.floor(y);fx,fy=x-ix,y-iy
    colors=[(get(ix,iy),(1-fx)*(1-fy)),(get(ix+1,iy),fx*(1-fy)),(get(ix,iy+1),(1-fx)*fy),(get(ix+1,iy+1),fx*fy)]
    a=sum(F(c[3])*q for c,q in colors);rgb=[sum(F(c[k])*c[3]*q for c,q in colors)/a if a else F(0) for k in range(3)]
    return bytes([math.floor(v+F(1,2)) for v in rgb+[a]])

class PixelWarpTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def inspect(self,s,expected=0,**kw):return self.invoke(dict(command='pixel_warp.inspect',warp=s,width=8,height=8,include_mesh=True,**kw),expected)
    def edit(self,d,*ops,expected=0):
        r=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=list(ops)),expected)
        return r if expected else r['document']
    def document(self,s=None,sampling='nearest',raw=None):
        d=self.invoke(dict(command='document.create',id='pixel-warp-fixture',kind='raster',width=16,height=16))
        item=dict(id='pixels',content=dict(type='raster',width=8,height=8,rgba_hex=(raw or chart()).hex(),sampling=sampling))
        if s is not None:item['pixel_warp']=s
        return self.edit(d,dict(op='add',item=item))
    def pixels(self,d,scale=1):
        a=self.invoke(dict(command='document.export',document=d,format='png',scale=scale));return editing.png_pixels(base64.b64decode(a['data']))[:3]
    def points(self,a,b,tol=1e-10):
        self.assertEqual(len(a),len(b))
        for p,q in zip(a,b):self.assertIsNotNone(p);self.assertLessEqual(math.dist(p,list(map(float,q))),tol,(p,q))
    def test_perspective_forward_inverse_matches_independent_linear_system(self):
        s=perspective();ps=[[x,y] for y in [0,2,4,8] for x in [0,2,4,8]];forward,inverse=maps(s);dest=[[4,4],[8,8],[0,0],[15,15]];r=self.inspect(s,samples=ps,inverse_samples=dest)
        self.points([v['mapped'] for v in r['samples']],[forward(p) for p in ps]);self.points(r['destination_points'],mesh_points(s)[1])
        for p,v in zip(dest,r['inverse_samples']):
            q=inverse(p)
            if q is None:self.assertIsNone(v['source'])
            else:self.points([v['source']],[q]);self.points([v['forward']],[p])
        for v in r['samples']:
            if v['inverse'] is not None:self.points([v['inverse']],[v['source']])
    def test_mesh_controls_triangle_diagonal_and_interior_inverse(self):
        s=mesh();src,dst,tri=mesh_points(s);ps=[[1,1],[3,2],[5,5],[7,6],[4,4]];forward,inverse=maps(s);r=self.inspect(s,samples=ps,inverse_samples=[[7,5],[4,4],[0,0]])
        self.assertEqual(r['source_points'],src);self.assertEqual(r['destination_points'],dst);self.assertEqual(r['triangles'],tri)
        self.points([v['mapped'] for v in r['samples']],[forward(p) for p in ps]);self.points([v['inverse'] for v in r['samples']],ps)
        self.points([r['inverse_samples'][0]['source']],[[4,4]]);self.assertIsNone(r['inverse_samples'][2]['source'])
    def test_articulated_joint_hierarchy_weights_and_nonlinear_bend(self):
        s=articulated();src,dst,tri=mesh_points(s);r=self.inspect(s,samples=[[2,2],[4,4],[6,6]])
        self.points(r['destination_points'],dst);self.assertEqual(r['triangles'],tri)
        for a,b in zip(r['joint_matrices'],poses(s)):
            for x,y in zip(a,b):self.assertAlmostEqual(x,y,places=12)
        self.assertNotEqual(dst[-1][0]-dst[-3][0],dst[2][0]-dst[0][0]);self.points([v['inverse'] for v in r['samples']],[[2,2],[4,4],[6,6]])
        s['joints'].append(dict(parent=1,pivot=[4,6],angle=-10));s['weights']=[w+[0] for w in s['weights']];r=self.inspect(s);self.points(r['destination_points'],dst)
    def test_identity_translation_and_reflection_have_exact_pixels(self):
        for corners in [[[0,0],[8,0],[8,8],[0,8]],[[2,3],[10,3],[10,11],[2,11]],[[10,3],[2,3],[2,11],[10,11]]]:
            s=dict(type='perspective',corners=corners);d=self.document(s);w,h,p=self.pixels(d);_,inverse=maps(s)
            for y in range(h):
                for x in range(w):
                    q=inverse([F(2*x+1,2),F(2*y+1,2)]);expected=sample(chart(),8,8,q,'nearest') if q is not None else bytes(4)
                    self.assertEqual(p[(y*w+x)*4:][:4],expected,(corners,x,y))
        identity=self.document(dict(type='mesh',columns=2,rows=2,points=[[x,y] for y in [0,4,8] for x in [0,4,8]]));self.assertEqual(self.pixels(identity,3),self.pixels(self.document(),3))
    def test_coordinate_chart_nearest_and_premultiplied_bilinear_match_independent_inverse(self):
        for s in [perspective(),mesh(),articulated()]:
            _,inverse=maps(s)
            for method in ['nearest','bilinear']:
                w,h,p=self.pixels(self.document(s,method),2);checked=0
                for y in range(h):
                    for x in range(w):
                        q=inverse([F(2*x+1,4),F(2*y+1,4)])
                        # Deep interior avoids the separately tested edge-coverage rasterizer.
                        if q is None or not all(1<=v<=7 for v in q):continue
                        expected=sample(chart(),8,8,q,method);actual=p[(y*w+x)*4:][:4]
                        self.assertLessEqual(max(abs(a-b) for a,b in zip(actual,expected)),0 if method=='nearest' else 1,(s['type'],method,x,y,q,actual,expected));checked+=1
                self.assertGreater(checked,80)
    def test_opaque_mesh_has_no_internal_alpha_seams_and_reflection_is_supported(self):
        for s in [mesh(),dict(mesh(),points=[[12-x,y] for x,y in mesh()['points']])]:
            w,h,p=self.pixels(self.document(s,raw=bytes([30,100,210,255])*64),4)
            for y in range(9,39):
                for x in range(9,39):self.assertEqual(p[(y*w+x)*4:][:4],bytes([30,100,210,255]))
    def test_controls_clear_reapply_source_edit_and_undoable_persistence(self):
        d=self.document(mesh());before=copy.deepcopy(d);original=node(d)['content']['rgba_hex'];r=self.invoke(dict(command='document.inspect',document=d))
        self.assertEqual(r['items'][0]['pixel_warp'],mesh());self.assertEqual(r['items'][0]['geometry_bounds'],[2,2,10,10]);self.assertEqual(json.loads(self.invoke(dict(command='document.export',document=d,format='snapshot'))['data']),d)
        clear=self.edit(d,dict(op='pixel_warp',id='pixels',warp=None));self.assertNotIn('pixel_warp',node(clear));self.assertEqual(self.pixels(clear),self.pixels(self.document()))
        again=self.edit(clear,dict(op='pixel_warp',id='pixels',warp=mesh()));self.assertEqual(self.pixels(again,2),self.pixels(d,2));self.assertEqual(node(again)['content']['rgba_hex'],original);self.assertEqual(d,before)
        filled=self.edit(d,dict(op='pixel_fill',id='pixels',rect=dict(x=0,y=0,width=2,height=2),color=[255,0,0,255]));self.assertEqual(node(filled)['pixel_warp'],mesh());self.assertNotEqual(self.pixels(filled),self.pixels(d))
    def test_crop_image_assets_match_inline_native_source(self):
        raw=chart();asset=dict(width=8,height=8,sha256=hashlib.sha256(canonical(8,8,raw)).hexdigest(),storage=dict(type='embedded',rgba_hex=raw.hex()))
        d=self.document(mesh());d['assets']={'source':asset};node(d)['content']=dict(type='image',asset_id='source',width=8,height=8,crop=dict(x=2,y=1,width=4,height=4),sampling='bilinear')
        crop=b''.join(raw[(y*8+2)*4:(y*8+6)*4] for y in range(1,5));other=copy.deepcopy(d);other['assets']={};node(other)['content']=dict(type='raster',width=4,height=4,rgba_hex=crop.hex(),sampling='bilinear')
        self.assertEqual(self.pixels(d,3),self.pixels(other,3));self.assertEqual(node(d)['content']['crop'],dict(x=2,y=1,width=4,height=4))
    def test_parent_transform_geometric_clip_opacity_and_mask(self):
        d=self.document(mesh());node(d).update(parent='g',opacity=.5,clip=dict(geometry=rect(0,0,6,16)),mask=dict(width=1,height=1,gray_hex='80',transform=[16,0,0,16,0,0]));d['items'].insert(0,dict(id='g',transform=[1,0,0,1,2,1],content=dict(type='group')))
        w,h,p=self.pixels(d);self.assertTrue(any(p[3::4]));self.assertTrue(all(p[(y*w+x)*4+3]==0 for y in range(h) for x in range(8,16)))
        full=self.document(mesh());full['items'].insert(0,dict(id='g',transform=[1,0,0,1,2,1],content=dict(type='group')));node(full)['parent']='g';base=self.pixels(full)[2]
        for y in range(4,9):
            for x in range(5,7):self.assertLessEqual(abs(p[(y*w+x)*4+3]-base[(y*w+x)*4+3]*.5*128/255),1)
    def test_artboard_export_transfer_and_create_only_publication(self):
        d=self.document(mesh());d['items']=[boards.BoardCliTests().board('page',16,16),dict(node(d),parent='page')]
        a=self.invoke(dict(command='artboard.export',document=d,format='png'))['artifacts'][0]['artifact'];self.assertEqual(editing.png_pixels(base64.b64decode(a['data']))[:3],self.pixels(d))
        target=self.invoke(dict(command='document.create',id='target',kind='raster',width=16,height=16));out=self.edit(target,dict(op='transfer',transfer=dict(source=d,ids=['pixels'],prefix='copy')));self.assertEqual(self.pixels(out),self.pixels(d));self.assertEqual(node(out,'copy-pixels')['pixel_warp'],mesh())
        with tempfile.TemporaryDirectory() as root:
            output=dict(output_root=root,file_name='warped.png',format='png');self.invoke(dict(command='document.publish',document=d,output=output));self.assertEqual(self.invoke(dict(command='document.publish',document=d,output=output),1)['code'],'OUTPUT_EXISTS')

    def test_boundary_coverage_uses_inverse_of_nearest_projective_boundary_point(self):
        s=dict(type='perspective',corners=[[.7,1.3],[11.4,2.7],[10.2,12.1],[1.2,10.4]]);_,inverse=maps(s);d=self.document(s);w,h,p=self.pixels(d)
        v=self.invoke(dict(command='document.create',id='coverage',kind='vector',width=16,height=16))
        from test_interpolation_cli import path
        v=self.edit(v,dict(op='add',item=dict(id='boundary',content=dict(type='vector',geometry=path(s['corners']),fill=[255]*4))))
        alpha=self.pixels(v)[2][3::4];outside=0;corners=[list(map(F,c)) for c in s['corners']]
        for y in range(h):
            for x in range(w):
                coverage=alpha[y*w+x]
                if not coverage:continue
                pos=[F(2*x+1,2),F(2*y+1,2)];q=inverse(pos)
                if q is None:
                    candidates=[]
                    for a,b in zip(corners,corners[1:]+corners[:1]):
                        delta=[b[k]-a[k] for k in range(2)];t=max(F(0),min(F(1),sum((pos[k]-a[k])*delta[k] for k in range(2))/sum(v*v for v in delta)))
                        point=[a[k]+t*delta[k] for k in range(2)];candidates.append((sum((a-b)**2 for a,b in zip(point,pos)),point))
                    q=inverse(min(candidates,key=lambda a:a[0])[1]);self.assertIsNotNone(q);outside+=1
                color=sample(chart(),8,8,q,'nearest');wanted=list(color);wanted[3]=math.floor(F(color[3]*coverage,255)+F(1,2))
                if wanted[3]==0:wanted=[0]*4
                self.assertLessEqual(max(abs(a-b) for a,b in zip(p[(y*w+x)*4:][:4],wanted)),1,(x,y,q))
        self.assertGreater(outside,5)
    def test_mesh_boundary_overlap_is_rejected_even_with_consistent_triangle_orientation(self):
        s=dict(type='mesh',columns=1,rows=4,points=[[12,8],[14,8],[8,12],[8,14],[4,8],[2,8],[8,4],[8,2],[12,8],[14,8]])
        e=self.inspect(s,expected=1);self.assertEqual(e['code'],'NONINVERTIBLE_WARP');self.assertIn('boundary',e['message'])
        folded=mesh();folded['points'][4]=[20,20];self.assertEqual(self.inspect(folded,expected=1)['code'],'NONINVERTIBLE_WARP')
        collapsed=mesh();collapsed['points'][4]=collapsed['points'][0];self.assertEqual(self.inspect(collapsed,expected=1)['code'],'NONINVERTIBLE_WARP')
    def test_invalid_joint_weights_parent_cycles_and_strict_controls(self):
        for modify in [lambda s:s['weights'][0].__setitem__(0,.2),lambda s:s['weights'][0].__setitem__(0,-1),lambda s:s['joints'][0].update(parent=1),lambda s:s['joints'][1].update(parent=1),lambda s:s['joints'][0].update(angle=361),lambda s:s['weights'].pop()]:
            s=articulated();modify(s);self.assertEqual(self.inspect(s,expected=1)['code'],'INVALID_PIXEL_WARP')
        s=mesh();s['unknown']=1;self.inspect(s,expected=1)
        s=mesh();s['points'].pop();self.assertEqual(self.inspect(s,expected=1)['code'],'INVALID_PIXEL_WARP')
        s=perspective();s['corners']=[[0,0],[8,8],[8,0],[0,8]];self.inspect(s,expected=1)
        s=dict(type='mesh',columns=1,rows=1,points=[[0,0],[8,0],[0,.0001],[8,.0001]]);self.assertEqual(self.inspect(s,expected=1)['code'],'UNSUPPORTED')
    def test_native_grid_operations_require_clearing_deformation_and_errors_are_atomic(self):
        from test_pixel_brush_cli import brush
        from test_retouch_cli import options
        d=self.document(mesh());before=copy.deepcopy(d)
        self.assertEqual(self.edit(d,dict(op='brush_stroke',id='pixels',stroke=brush()),expected=1)['code'],'UNSUPPORTED')
        self.assertEqual(self.edit(d,dict(op='retouch',id='pixels',options=options(source_id='pixels')),expected=1)['code'],'UNSUPPORTED')
        self.edit(d,dict(op='pixel_warp',id='pixels',warp=None),dict(op='remove',id='missing'),expected=1);self.assertEqual(d,before)
        node(d)['locked']=True;self.assertEqual(self.edit(d,dict(op='pixel_warp',id='pixels',warp=None),expected=1)['code'],'LOCKED')
        plain=self.edit(before,dict(op='pixel_warp',id='pixels',warp=None));painted=self.edit(plain,dict(op='brush_stroke',id='pixels',stroke=brush()));self.assertNotEqual(node(painted)['content']['rgba_hex'],node(plain)['content']['rgba_hex'])
    def test_sampling_context_svg_and_unsupported_items_fail_explicitly(self):
        d=self.document(mesh());node(d)['content']['sampling']='area';self.assertEqual(self.invoke(dict(command='document.validate',document=d),1)['code'],'UNSUPPORTED')
        d=self.document(mesh());raw=chart();asset=dict(width=8,height=8,sha256=hashlib.sha256(canonical(8,8,raw)).hexdigest(),storage=dict(type='embedded',rgba_hex=raw.hex()))
        d['kind']='vector';d['assets']={'source':asset};node(d)['content']=dict(type='image',asset_id='source',width=8,height=8)
        self.assertEqual(self.invoke(dict(command='document.export',document=d,format='svg'),1)['code'],'UNSUPPORTED');self.assertEqual(self.pixels(d),self.pixels(self.document(mesh())))
        node(d)['content']=dict(type='vector',geometry=rect(0,0,8,8),fill=[255]*4);self.assertEqual(self.invoke(dict(command='document.validate',document=d),1)['code'],'UNSUPPORTED')
    def test_hidden_control_and_render_work_limits_and_cancellation(self):
        s=dict(type='mesh',columns=16,rows=16,points=[[x/2,y/2] for y in range(17) for x in range(17)])
        d=self.document(s);d['width']=d['height']=512;node(d)['visible']=False;self.assertEqual(self.invoke(dict(command='document.render',document=d),1)['code'],'RESOURCE_LIMIT')
        d=self.document(s)
        for k in range(14):d['items'].append(dict(copy.deepcopy(node(d)),id='copy'+str(k),visible=False))
        self.assertEqual(self.invoke(dict(command='document.validate',document=d),1)['code'],'RESOURCE_LIMIT')
        self.assertEqual(self.inspect(dict(s,columns=17),expected=1)['code'],'RESOURCE_LIMIT');self.assertEqual(self.inspect(mesh(),expected=1,samples=[[1,1]]*257)['code'],'RESOURCE_LIMIT')
        self.assertEqual(self.inspect(mesh(),expected=1,control=dict(timeout_ms=0))['code'],'TIMEOUT')
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'cancel';p.write_text('cancel');self.assertEqual(self.inspect(mesh(),expected=1,control=dict(cancel_file=str(p)))['code'],'CANCELLED')
    def test_mcp_durable_controls_restart_retry_undo_redo_and_publication(self):
        c=Client();self.addCleanup(lambda client=c:client.close() if not client.process.stdin.closed else None);c.initialize();d=self.document()
        self.assertEqual(c.success('pixel_warp.inspect',warp=mesh(),width=8,height=8,include_mesh=True),self.inspect(mesh()))
        with tempfile.TemporaryDirectory() as root:
            session=dict(session_root=root,session_id='pixel-warp');c.success('session.create',**session,request_id='create',document=d)
            args=dict(**session,expected_revision=0,request_id='deform',action=dict(type='edit',operations=[dict(op='pixel_warp',id='pixels',warp=articulated())]));changed=c.success('session.apply',**args)['document'];self.assertTrue(c.success('session.apply',**args)['replayed']);c.close();c=Client();self.addCleanup(c.close);c.initialize()
            undo=c.success('session.apply',**session,expected_revision=1,request_id='undo',action=dict(type='undo'))['document'];self.assertEqual(undo['items'],d['items'])
            redo=c.success('session.apply',**session,expected_revision=2,request_id='redo',action=dict(type='redo'))['document'];self.assertEqual(redo['items'],changed['items']);self.assertEqual(self.pixels(redo,2),self.pixels(changed,2))
            c.success('session.publish',**session,expected_revision=3,output=dict(output_root=root,file_name='bent.png',format='png'));c.success('session.verify',**session)
    def test_canvas_scaling_and_duplicate_independence_preserve_native_pixels(self):
        d=self.document(mesh());source=copy.deepcopy(d);scaled=self.edit(d,dict(op='canvas',action=dict(type='scale',width=32,height=32,sampling='nearest')))
        self.assertEqual(self.pixels(scaled),self.pixels(d,2));self.assertEqual(node(scaled)['pixel_warp'],mesh());self.assertEqual(node(scaled)['content']['rgba_hex'],node(d)['content']['rgba_hex'])
        duplicate=copy.deepcopy(d);duplicate['items'].append(dict(copy.deepcopy(node(d)),id='copy'));out=self.edit(duplicate,dict(op='pixel_warp',id='copy',warp=perspective()))
        self.assertEqual(node(out)['pixel_warp'],mesh());self.assertEqual(node(out,'copy')['pixel_warp'],perspective());self.assertEqual(source,d)
    def test_shared_image_component_keeps_deformation_and_dependency_locks(self):
        from test_instances_cli import instance
        raw=chart();asset=dict(width=8,height=8,sha256=hashlib.sha256(canonical(8,8,raw)).hexdigest(),storage=dict(type='embedded',rgba_hex=raw.hex()))
        d=self.document(mesh());d['kind']='vector';d['assets']={'source':asset};node(d)['content']=dict(type='image',asset_id='source',width=8,height=8);node(d)['parent']='definition'
        d['items'].insert(0,dict(id='definition',content=dict(type='component_source')));d['items'].append(instance('copy','definition'))
        self.assertEqual(self.pixels(d,2),self.pixels(self.document(mesh()),2));changed=self.edit(d,dict(op='pixel_warp',id='pixels',warp=perspective()));self.assertNotEqual(self.pixels(d),self.pixels(changed))
        node(d,'copy')['locked']=True;self.assertEqual(self.edit(d,dict(op='pixel_warp',id='pixels',warp=None),expected=1)['code'],'LOCKED')
    def test_control_vertices_mask_baking_and_deformed_donor_diagnostics(self):
        for s in [perspective(),mesh(),articulated()]:
            src,dst,_=mesh_points(s);r=self.inspect(s,samples=src,inverse_samples=dst)
            self.points([v['mapped'] for v in r['samples']],dst);self.points([v['source'] for v in r['inverse_samples']],src)
        d=self.document(mesh());node(d)['mask']=dict(width=1,height=1,gray_hex='80',transform=[8,0,0,8,0,0]);self.assertEqual(self.edit(d,dict(op='mask_apply',id='pixels'),expected=1)['code'],'UNSUPPORTED')
        from test_retouch_cli import options
        d=self.document();d['items'].append(dict(copy.deepcopy(node(d)),id='source',visible=False,pixel_warp=mesh()))
        self.assertEqual(self.edit(d,dict(op='retouch',id='pixels',options=options()),expected=1)['code'],'UNSUPPORTED')

if __name__=='__main__':unittest.main()
