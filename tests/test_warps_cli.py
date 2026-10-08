"""Original deformation fixtures and independent rational point/certificate oracles."""
import base64
import copy
from fractions import Fraction as F
import json
import math
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import test_editing_cli as editing
import test_boards_cli as boards
from test_interpolation_cli import path,rect
from test_instances_cli import instance
from test_mcp import Client

INK=[40,120,220,255]
def affine(m=None):return dict(type='affine',matrix=m or [1,0,0,1,0,0])
def perspective():return dict(type='perspective',domain=[0,0,24,24],corners=[[12,8],[42,12],[38,40],[8,32]])
def envelope():
    p=[[[6+8*x,6+8*y] for x in range(4)] for y in range(4)]
    p[0][1][1]-=4;p[0][2][1]+=6;p[1][1][0]+=4;p[2][2][1]-=6
    return dict(type='envelope',domain=[0,0,24,24],points=p)
def spec(maps=None,g=None,**kw):return dict(geometry=g or rect(0,0,24,24),fill=INK,maps=maps or [perspective()],**kw)
def node(d,id='warp'):return next(i for i in d['items'] if i['id']==id)
def cubic():return dict(shape='path',commands=[dict(verb='move',to=[2,12]),dict(verb='cubic',control1=[4,1],control2=[20,23],to=[22,12]),dict(verb='close')])

def solve(rows):
    """Gauss-Jordan elimination, independent of the engine's four-corner formula."""
    a=[[F(v) for v in row] for row in rows];n=len(a)
    for k in range(n):
        pivot=next(i for i in range(k,n) if a[i][k]);a[k],a[pivot]=a[pivot],a[k]
        v=a[k][k];a[k]=[x/v for x in a[k]]
        for i in range(n):
            if i!=k:
                v=a[i][k];a[i]=[x-v*y for x,y in zip(a[i],a[k])]
    return [row[-1] for row in a]

def point_mapper(maps):
    stages=[]
    for m in maps:
        if m['type']=='perspective':
            rows=[]
            for (u,v),(x,y) in zip([(0,0),(1,0),(1,1),(0,1)],m['corners']):
                rows += [[u,v,1,0,0,0,-F(x)*u,-F(x)*v,x],[0,0,0,u,v,1,-F(y)*u,-F(y)*v,y]]
            stages.append((m,solve(rows)+[F(1)]))
        else:stages.append((m,None))
    def mapped(p):
        x,y=map(F,p)
        for m,h in stages:
            if m['type']=='affine':
                a,b,c,d,e,f=map(F,m['matrix']);x,y=a*x+c*y+e,b*x+d*y+f;continue
            dx,dy,w,hh=map(F,m['domain']);u=(x-dx)/w;v=(y-dy)/hh
            if h is not None:
                den=h[6]*u+h[7]*v+h[8];x,y=(h[0]*u+h[1]*v+h[2])/den,(h[3]*u+h[4]*v+h[5])/den
            else:
                bu=[(1-u)**3,3*u*(1-u)**2,3*u*u*(1-u),u**3];bv=[(1-v)**3,3*v*(1-v)**2,3*v*v*(1-v),v**3]
                x,y=[sum(bu[c]*bv[r]*F(m['points'][r][c][k]) for r in range(4) for c in range(4)) for k in range(2)]
        return [x,y]
    return mapped

def source_edges(g):
    if g['shape']=='rect':
        x,y,w,h=[g[k] for k in ['x','y','width','height']];g=path([[x,y],[x+w,y],[x+w,y+h],[x,y+h]])
    contours=[];edges=[];start=None;last=None
    for c in g['commands']:
        if c['verb']=='move':
            if edges:contours.append(edges)
            edges=[];start=c['to'];last=start
        elif c['verb']=='close':
            if last!=start:edges.append([last,start])
            contours.append(edges);edges=[];last=None
        else:
            controls=[c['control1'],c['control2']] if c['verb']=='cubic' else []
            edges.append([last,*controls,c['to']]);last=c['to']
    if edges:contours.append(edges)
    return contours

def bezier(points,t):
    n=len(points)-1
    return [sum(F(p[k])*math.comb(n,i)*t**i*(1-t)**(n-i) for i,p in enumerate(points)) for k in range(2)]

def check_certificate(s,result,subdivisions=8):
    """Exact point-wise squared-distance comparisons against every encoded bound."""
    contours=source_edges(s['geometry']);mapped=point_mapper(s['maps']);ends={};count=0;largest=0.
    for seg in result['segments']:
        key=seg['contour'],seg['edge'];lo,hi=map(F,seg['parameter'])
        assert lo==ends.get(key,F(0)) and hi>lo and hi<=1
        ends[key]=hi;bound=F(seg['error_bound']);assert 0<=bound<=F(s.get('tolerance',.01))
        for j in range(subdivisions+1):
            t=F(j,subdivisions);p=mapped(bezier(contours[key[0]][key[1]],lo+(hi-lo)*t))
            q=[F(a)*(1-t)+F(b)*t for a,b in zip(seg['from'],seg['to'])]
            error=sum((a-b)**2 for a,b in zip(p,q));assert error<=bound*bound,(seg,j,float(error),float(bound))
            largest=max(largest,math.sqrt(float(error)));count+=1
    assert len(ends)==sum(map(len,contours)) and all(v==1 for v in ends.values())
    return count,largest

class WarpTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def inspect(self,s,expected=0,**kw):return self.invoke(dict(command='warp.inspect',warp=s,include_geometry=True,include_segments=True,**kw),expected)
    def edit(self,d,*ops,expected=0):
        r=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=list(ops)),expected)
        return r if expected else r['document']
    def document(self,s=None):
        d=self.invoke(dict(command='document.create',id='warp-fixture',kind='vector',width=64,height=48))
        return self.edit(d,dict(op='add',item=dict(id='warp',content=dict(type='warp',warp=s or spec()))))
    def expand(self,d,expected=0):return self.edit(d,dict(op='warp_expand',id='warp'),expected=expected)
    def pixels(self,d,scale=1):
        r=self.invoke(dict(command='document.export',document=d,format='png',scale=scale))
        return editing.png_pixels(base64.b64decode(r['data']))[:3]
    def points(self,a,b):
        self.assertEqual(len(a),len(b))
        for p,q in zip(a,b):self.assertLessEqual(math.dist(p,[float(x) for x in q]),1e-12)
    def test_affine_reflection_shear_nested_order_and_exact_axis_pixels(self):
        maps=[affine([-1,0,.5,1,28,4]),affine([1,0,0,1,2,3])];s=spec(maps,rect(0,0,12,12));r=self.inspect(s)
        self.assertEqual(r['segments_count'],4);self.assertEqual(r['maximum_error_bound'],0);check_certificate(s,r)
        source=[[0,0],[12,0],[12,12],[0,12]];self.points([r['segments'][i]['from'] for i in range(4)],[point_mapper(maps)(p) for p in source])
        d=self.document(spec([affine([1,0,0,1,8,6])],rect(0,0,12,12)));w,h,p=self.pixels(d,2)
        for y in range(h):
            for x in range(w):self.assertEqual(p[(y*w+x)*4:][:4],bytes(INK if 16<=x<40 and 12<=y<36 else [0]*4))
    def test_perspective_corners_and_interior_points_match_independent_linear_system(self):
        s=spec();ps=[[x,y] for y in [0,6,12,24] for x in [0,6,12,24]];r=self.inspect(s,samples=ps)
        self.points([v['mapped'] for v in r['samples']],[point_mapper(s['maps'])(p) for p in ps]);self.assertEqual(r['maps'],s['maps']);check_certificate(s,r)
        for corners in [[[42,8],[12,12],[8,40],[38,32]],[[8,8],[32,8],[32,32],[8,32]]]:
            m=perspective();m['corners']=corners;s=spec([m]);r=self.inspect(s,samples=[[0,0],[24,0],[24,24],[0,24]]);self.points([v['mapped'] for v in r['samples']],corners)
    def test_nonlinear_envelope_controls_boundary_and_interior(self):
        s=spec([envelope()]);ps=[[x,y] for y in [0,6,12,24] for x in [0,6,12,24]];r=self.inspect(s,samples=ps)
        self.points([v['mapped'] for v in r['samples']],[point_mapper(s['maps'])(p) for p in ps]);check_certificate(s,r)
        self.assertGreater(r['segments_count'],4);self.assertEqual(r['maps'][0]['points'],s['maps'][0]['points'])
        d=self.document(s);self.assertEqual(self.pixels(d,2),self.pixels(self.expand(d),2))
    def test_cubic_and_implicit_closing_edge_have_independent_error_certificates(self):
        for maps in [[perspective()],[envelope()]]:
            s=spec(maps,cubic(),tolerance=.025);r=self.inspect(s);count,error=check_certificate(s,r,16)
            self.assertGreater(count,100);self.assertLessEqual(error,.025);self.assertEqual({v['edge'] for v in r['segments']},{0,1})
    def test_nested_perspective_envelope_affine_and_two_nonlinear_maps(self):
        e=envelope();e['domain']=[0,0,48,48];s=spec([perspective(),e,affine([1,0,.25,1,4,2])],path([[2,2],[22,20]],False),tolerance=.1);s['fill']=None
        r=self.inspect(s,samples=[[12,12]]);check_certificate(s,r);self.points([r['samples'][0]['mapped']],[point_mapper(s['maps'])([12,12])])
        e2=envelope();e2['domain']=[0,0,36,36];s=spec([envelope(),e2],path([[3,5],[21,19]],False),tolerance=.2);s['fill']=None
        r=self.inspect(s);check_certificate(s,r);self.assertEqual({v['degree'] for v in r['segments']},{36})
    def test_perspective_and_curved_grids_are_reusable_bounded_open_paths(self):
        for maps in [[perspective()],[envelope()]]:
            s=spec(maps);r=self.inspect(s,grid=dict(domain=[0,0,24,24],columns=2,rows=3));grid=r['grid']
            self.assertEqual(sum(c['verb']=='move' for c in grid['geometry']['commands']),7)
            commands=[]
            for x in [0,12,24]:commands += path([[x,0],[x,24]],False)['commands']
            for y in [0,8,16,24]:commands += path([[0,y],[24,y]],False)['commands']
            gs=spec(maps,dict(shape='path',commands=commands));gs['fill']=None;check_certificate(gs,grid)
            d=self.document(s);d=self.edit(d,dict(op='add',item=dict(id='grid',content=dict(type='work_path',geometry=grid['geometry']))));self.assertEqual(self.pixels(d),self.pixels(self.document(s)))
    def test_tighter_tolerance_preserves_source_and_refines_certified_curve(self):
        exact=dict(shape='path',commands=[dict(verb='move',to=[0,0]),dict(verb='cubic',control1=[1,1],control2=[2,1],to=[3,0])])
        edge=spec([affine()],exact,tolerance=1);edge['fill']=None;boundary=self.inspect(edge)
        self.assertEqual(boundary['segments_count'],1);self.assertEqual(boundary['maximum_error_bound'],1);check_certificate(edge,boundary)
        s=spec([envelope()],cubic(),tolerance=.2);coarse=self.inspect(s);fine=copy.deepcopy(s);fine['tolerance']=.005;r=self.inspect(fine)
        self.assertGreater(r['segments_count'],coarse['segments_count']);check_certificate(fine,r);self.assertEqual(r['tolerance'],.005)
        d=self.document(s);out=self.edit(d,dict(op='warp',id='warp',warp=fine));self.assertEqual(node(out)['content']['warp']['geometry'],s['geometry']);self.assertEqual(node(d)['content']['warp']['tolerance'],.2)
    def test_expanded_primitive_interpretation_ellipse_and_stroke_after_deformation(self):
        s=spec([affine([1,.1,.2,1,6,6])],dict(shape='ellipse',cx=12,cy=12,rx=8,ry=6),tolerance=.05);s['stroke']=dict(color=[200,30,60,255],width=2)
        r=self.inspect(s);self.assertEqual(r['source_interpretation'],'ordinary_line_cubic_primitive_expansion');self.assertEqual(r['appearance'],'paint_and_stroke_after_geometry_deformation')
        d=self.document(s);self.assertEqual(self.pixels(d,2),self.pixels(self.expand(d),2))
        s=spec([envelope()],path([[0,12],[24,12]],False));s['fill']=None;s['stroke']=dict(color=INK,width=2)
        d=self.document(s);self.assertEqual(self.pixels(d,2),self.pixels(self.expand(d),2))
    def test_compound_holes_fill_rules_and_reflection_survive_expansion(self):
        g=path([[0,0],[24,0],[24,24],[0,24]]);g['commands']+=path([[6,6],[6,18],[18,18],[18,6]])['commands']
        for rule in ['nonzero','even_odd']:
            s=spec([affine([-1,0,0,1,30,6])],g,fill_rule=rule);d=self.document(s);w,h,p=self.pixels(d)
            self.assertEqual(p[(18*w+18)*4+3],0);self.assertEqual(p[(8*w+8)*4+3],255);self.assertEqual(self.pixels(d,2),self.pixels(self.expand(d),2))
    def test_saved_controls_queries_transfer_svg_and_bounds(self):
        d=self.document();before=copy.deepcopy(d);r=self.inspect(node(d)['content']['warp'])
        item=self.invoke(dict(command='document.inspect',document=d))['items'][0];self.assertEqual(item['warp'],node(d)['content']['warp']);self.assertEqual(item['geometry_bounds'],r['bounds'])
        self.assertEqual(self.invoke(dict(command='document.query',document=d,query=dict(types=['warp'])))['ids'],['warp'])
        self.assertEqual(json.loads(self.invoke(dict(command='document.export',document=d,format='snapshot'))['data']),d)
        a=self.invoke(dict(command='document.export',document=d,format='svg'));b=self.invoke(dict(command='document.export',document=self.expand(d),format='svg'))
        self.assertEqual(a['data'],b['data']);self.assertTrue(any('Warp' in v for v in a['losses']));self.assertEqual(len(ET.fromstring(a['data']).findall('.//{*}path')),1)
        target=self.invoke(dict(command='document.create',id='copy',kind='vector',width=64,height=48));out=self.edit(target,dict(op='transfer',transfer=dict(source=d,ids=['warp'],prefix='copy')))
        self.assertEqual(node(out,'copy-warp')['content'],node(d)['content']);self.assertEqual(self.pixels(out),self.pixels(d));self.assertEqual(d,before)
    def test_appearance_parent_transform_masks_and_locks(self):
        d=self.document();node(d).update(parent='g',opacity=.7,transform=[1,0,.1,1,0,1],clip=dict(geometry=rect(0,0,30,40)),effects=[dict(id='tint',operator=dict(type='overlay'),color=[180,50,100,128])]);d['items'].insert(0,dict(id='g',transform=[1,0,0,1,2,0],content=dict(type='group')))
        before=copy.deepcopy(d);self.assertEqual(self.pixels(d,2),self.pixels(self.expand(d),2));self.assertEqual(d,before)
        node(d,'g')['locked']=True;self.assertEqual(self.expand(d,expected=1)['code'],'LOCKED');self.assertEqual(self.edit(d,dict(op='warp',id='warp',warp=spec()),expected=1)['code'],'LOCKED')
    def test_component_mask_sources_dependency_locks_and_raster_rejection(self):
        d=self.document(spec([affine([1,0,0,1,6,6])]));node(d)['parent']='source';d['items'].insert(0,dict(id='source',content=dict(type='component_source')));d['items'].append(instance('copy','source'))
        self.assertEqual(self.pixels(d,2),self.pixels(self.expand(d),2));node(d,'copy')['locked']=True;self.assertEqual(self.expand(d,expected=1)['code'],'LOCKED')
        d=self.document(spec([affine()]));d['kind']='raster';self.assertEqual(self.invoke(dict(command='document.validate',document=d),1)['code'],'INVALID_DOCUMENT')
        node(d)['parent']='source';d['items'].insert(0,dict(id='source',content=dict(type='mask_source')));d['items'].append(dict(id='pixels',content=dict(type='raster',width=64,height=48,rgba_hex='2878dcff'*(64*48)),artwork_mask=dict(source='source',region=[0,0,64,48],mode='alpha')))
        self.assertEqual(self.pixels(d,2),self.pixels(self.expand(d),2));self.assertGreater(sum(self.pixels(d)[2][3::4]),0)
    def test_artboard_and_create_only_publication_preserve_controls(self):
        d=self.document(spec([affine([1,0,0,1,6,6])]));d['items']=[boards.BoardCliTests().board('page',48,40,bleed=dict(top=1,right=1,bottom=1,left=1)),dict(node(d),parent='page')]
        for fmt in ['png','svg']:
            a=self.invoke(dict(command='artboard.export',document=d,format=fmt,include_bleed=True))['artifacts'][0]['artifact'];b=self.invoke(dict(command='artboard.export',document=self.expand(d),format=fmt,include_bleed=True))['artifacts'][0]['artifact']
            self.assertEqual(a['data'],b['data'])
            if fmt=='svg':self.assertTrue(any('Warp' in v for v in a['losses']))
        with tempfile.TemporaryDirectory() as root:
            output=dict(output_root=root,file_name='warp.json',format='snapshot');self.invoke(dict(command='document.publish',document=d,output=output));self.assertEqual(json.loads((Path(root)/'warp.json').read_text()),self.invoke(dict(command='document.validate',document=d)));self.assertEqual(self.invoke(dict(command='document.publish',document=d,output=output),1)['code'],'OUTPUT_EXISTS')
    def test_durable_mcp_restart_retry_control_edit_expand_undo_redo(self):
        c=Client();self.addCleanup(lambda client=c:client.close() if not client.process.stdin.closed else None);c.initialize();s=spec([affine([1,0,.5,1,6,6])]);d=self.document(spec([affine()]))
        self.assertEqual(c.success('warp.inspect',warp=s,include_geometry=True,include_segments=True),self.inspect(s))
        with tempfile.TemporaryDirectory() as root:
            session=dict(session_root=root,session_id='warp');c.success('session.create',**session,request_id='create',document=d)
            args=dict(**session,expected_revision=0,request_id='change',action=dict(type='edit',operations=[dict(op='warp',id='warp',warp=s)]));changed=c.success('session.apply',**args)['document'];self.assertTrue(c.success('session.apply',**args)['replayed']);c.close();c=Client();self.addCleanup(c.close);c.initialize()
            expanded=c.success('session.apply',**session,expected_revision=1,request_id='expand',action=dict(type='edit',operations=[dict(op='warp_expand',id='warp')]))['document'];self.assertEqual(self.pixels(changed,2),self.pixels(expanded,2))
            undone=c.success('session.apply',**session,expected_revision=2,request_id='undo',action=dict(type='undo'))['document'];self.assertEqual(undone['items'],changed['items'])
            redone=c.success('session.apply',**session,expected_revision=3,request_id='redo',action=dict(type='redo'))['document'];self.assertEqual(redone['items'],expanded['items']);c.success('session.publish',**session,expected_revision=4,output=dict(output_root=root,file_name='warp.png',format='png'));c.success('session.verify',**session)
    def test_invalid_quad_conditioning_domain_and_strict_controls(self):
        for corners in [[[0,0],[24,24],[24,0],[0,24]],[[0,0],[24,0],[12,1],[0,24]],[[0,0],[24,0],[24,0],[0,24]]]:
            m=perspective();m['corners']=corners;self.assertEqual(self.inspect(spec([m]),expected=1)['code'],'INVALID_WARP')
        m=perspective();m['corners']=[[0,0],[24,0],[.001,24],[0,24]];self.assertEqual(self.inspect(spec([m]),expected=1)['code'],'UNSUPPORTED')
        s=spec(g=rect(-1,0,24,24));self.assertEqual(self.inspect(s,expected=1)['code'],'WARP_DOMAIN')
        s=spec();s['maps'][0]['unknown']=1;self.inspect(s,expected=1)
        s=spec();s['maps'][0]['domain']=[0,0,0,24];self.assertEqual(self.inspect(s,expected=1)['code'],'INVALID_WARP')
        self.assertEqual(self.inspect(spec([affine([0,0,0,0,0,0])]),expected=1)['code'],'UNSUPPORTED')
        self.assertEqual(self.inspect(spec(),expected=1,samples=[[-1,0]])['code'],'WARP_DOMAIN')
    def test_open_fills_invalid_styles_and_atomic_rollback(self):
        self.assertEqual(self.inspect(spec(g=path([[0,0],[24,24]],False)),expected=1)['code'],'UNSUPPORTED')
        s=spec();s['stroke']=dict(color=INK,width=-1);self.inspect(s,expected=1)
        d=self.document(spec([affine()]));before=copy.deepcopy(d);self.edit(d,dict(op='warp_expand',id='warp'),dict(op='remove',id='missing'),expected=1);self.assertEqual(d,before)
        expanded=self.expand(d);self.assertEqual(self.expand(expanded,expected=1)['code'],'INVALID_OPERATION')
    def test_nested_degree_map_sample_grid_limits_and_coordinate_rejection(self):
        e=envelope();e['domain']=[0,0,36,36];s=spec([e,e,e],path([[3,5],[21,19]],False));s['fill']=None;self.assertEqual(self.inspect(s,expected=1)['code'],'RESOURCE_LIMIT')
        s=spec();s['maps']=[];self.assertEqual(self.inspect(s,expected=1)['code'],'RESOURCE_LIMIT')
        self.assertEqual(self.inspect(spec([affine()]*9),expected=1)['code'],'RESOURCE_LIMIT')
        self.assertEqual(self.inspect(spec([affine()]),expected=1,samples=[[1,1]]*257)['code'],'RESOURCE_LIMIT')
        self.assertEqual(self.inspect(spec([affine()]),expected=1,grid=dict(domain=[0,0,24,24],columns=17,rows=2))['code'],'RESOURCE_LIMIT')
        self.assertEqual(self.inspect(spec([affine([1,0,0,1,32768,0])]),expected=1)['code'],'INVALID_WARP')
        for tolerance in [0,1.1]:self.assertEqual(self.inspect(spec([affine()],tolerance=tolerance),expected=1)['code'],'INVALID_WARP')
    def test_hidden_aggregate_generated_commands_and_input_edge_budget(self):
        g=path([[i/16,2+i%2] for i in range(257)]);self.assertEqual(self.inspect(spec([affine()],g),expected=1)['code'],'RESOURCE_LIMIT')
        s=spec([affine()],path([[i/16,2+i%2] for i in range(250)]));d=self.document(s);node(d)['visible']=False
        for k in range(17):d['items'].append(dict(copy.deepcopy(node(d)),id='hidden'+str(k)))
        self.assertEqual(self.invoke(dict(command='document.validate',document=d),1)['code'],'RESOURCE_LIMIT')
        s=spec([affine()],cubic(),tolerance=.0001);d=self.document(s);node(d)['visible']=False
        for k in range(20):d['items'].append(dict(copy.deepcopy(node(d)),id='curve'+str(k)))
        self.assertLess(sum(len(node(d)['content']['warp']['geometry']['commands']) for _ in d['items']),4096)
        self.assertEqual(self.invoke(dict(command='document.validate',document=d),1)['code'],'RESOURCE_LIMIT')
    def test_cancellation_deadline_and_repeatability(self):
        s=spec([affine()]);self.assertEqual(self.inspect(s),self.inspect(s));self.assertEqual(self.inspect(s,expected=1,control=dict(timeout_ms=0))['code'],'TIMEOUT')
        with tempfile.TemporaryDirectory() as root:
            marker=Path(root)/'cancel';marker.write_text('cancel');self.assertEqual(self.inspect(s,expected=1,control=dict(cancel_file=str(marker)))['code'],'CANCELLED')
        self.assertEqual(self.inspect(spec([envelope()],cubic()),expected=1,control=dict(timeout_ms=1))['code'],'TIMEOUT')
    def test_warps_repeats_interpolation_share_scene_materialization(self):
        from test_repeats_cli import spec as repeated
        from test_interpolation_cli import spec as interpolated
        d=self.document(spec([affine()]));d=self.edit(d,dict(op='add',item=dict(id='repeat',content=dict(type='repeat',repeat=repeated()))),dict(op='add',item=dict(id='blend',content=dict(type='interpolation',interpolation=interpolated(count=3)))))
        expanded=self.edit(d,dict(op='warp_expand',id='warp'),dict(op='repeat_expand',id='repeat'),dict(op='interpolation_expand',id='blend'));self.assertEqual(self.pixels(d,2),self.pixels(expanded,2))

if __name__=='__main__':unittest.main()
