"""Original shape correspondence, independent color/placement and editable sequence checks."""
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
from test_path_text_cli import ArcOracle,CURVE,curved
from test_instances_cli import instance
from test_mcp import Client
from test_strokes_cli import line
from test_stroke_outlines_cli import polygons,area,winding

def rect(x,y,w,h):return dict(shape='rect',x=x,y=y,width=w,height=h)
def endpoint(g,color,**kw):return dict(geometry=g,fill=color,**kw)
def spec(count=5,**kw):
    return dict({'from':endpoint(rect(4,8,4,4),[240,40,20,255]),'to':endpoint(rect(52,20,12,8),[20,80,240,255]),'count':count},**kw)
def node(d,id='blend'):return next(i for i in d['items'] if i['id']==id)
def path(points,closed=True):
    g=line(points)
    if closed:g['commands'].append(dict(verb='close'))
    return g
def identity():return [1,0,0,1,0,0]
def map_point(m,p):return [m[0]*p[0]+m[2]*p[1]+m[4],m[1]*p[0]+m[3]*p[1]+m[5]]
def rgb(a,b,t,linear=False):
    alpha=(F(a[3])*(1-t)+F(b[3])*t)/255
    def decode(x):
        v=x/255
        return v/12.92 if linear and v<=.04045 else (((v+.055)/1.055)**2.4 if linear else F(x,255))
    out=[]
    for x,y in zip(a[:3],b[:3]):
        v=(decode(x)*F(a[3],255)*(1-t)+decode(y)*F(b[3],255)*t)/alpha if alpha else 0
        if linear:v=12.92*v if v<=.0031308 else 1.055*float(v)**(1/2.4)-.055
        out.append(math.floor(v*255+F(1,2)))
    return out+[math.floor(alpha*255+F(1,2))]

class InterpolationTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def inspect(self,s,geometry=True,expected=0,**kw):
        return self.invoke(dict(command='interpolation.inspect',interpolation=s,include_geometry=geometry,**kw),expected)
    def document(self,s=None):
        d=self.invoke(dict(command='document.create',id='interpolation-fixture',kind='vector',width=96,height=64))
        return self.edit(d,dict(op='add',item=dict(id='blend',content=dict(type='interpolation',interpolation=s or spec()))))
    def edit(self,d,*ops,expected=0):
        r=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=list(ops)),expected)
        return r if expected else r['document']
    def expand(self,d,id='blend',expected=0):return self.edit(d,dict(op='interpolation_expand',id=id),expected=expected)
    def pixels(self,d,scale=1):
        p=self.invoke(dict(command='document.export',document=d,format='png',scale=scale))
        return editing.png_pixels(base64.b64decode(p['data']))[:3]
    def assert_points(self,a,b,tol=1e-10):
        self.assertEqual(len(a),len(b))
        for x,y in zip(a,b):self.assertLessEqual(math.dist(x,y),tol,(x,y))

    def test_fixed_count_geometry_placement_colors_and_exact_interior_pixels(self):
        s=spec();report=self.inspect(s);self.assertEqual(report['count'],5)
        for k,v in enumerate(report['samples']):
            t=F(k,4);cx=6+13*k;cy=10+F(7*k,2);w=4+2*k;h=4+k
            self.assertEqual(v['center'],[cx,float(cy)])
            self.assertEqual(v['bounds'],list(map(float,[cx-F(w,2),cy-F(h,2),cx+F(w,2),cy+F(h,2)])))
            self.assertEqual(v['fill'],rgb(s['from']['fill'],s['to']['fill'],t))
        self.assertEqual(report['samples'][0]['geometry'],s['from']['geometry'])
        self.assertEqual(report['samples'][-1]['geometry'],s['to']['geometry'])
        d=self.document(s);w,h,p=self.pixels(d,2)
        for y in range(h):
            for x in range(w):
                px,py=(x+.5)/2,(y+.5)/2
                sample=next((v for v in report['samples'] if v['bounds'][0]<=px<v['bounds'][2] and v['bounds'][1]<=py<v['bounds'][3]),None)
                self.assertEqual(p[(y*w+x)*4:(y*w+x+1)*4],bytes(sample['fill'] if sample else [0]*4))
        expanded=self.expand(d);self.assertEqual(len(expanded['items']),6)
        self.assertEqual(self.pixels(d,3),self.pixels(expanded,3))

    def test_premultiplied_color_spaces_hidden_rgb_missing_fill_and_opacity(self):
        for linear in (False,True):
            s=spec(count=3,space='linear_rgb' if linear else 'srgb')
            s['from']['fill']=[240,10,50,64];s['to']['fill']=[10,80,250,192]
            s['from']['opacity']=.25;s['to']['opacity']=.75
            r=self.inspect(s);self.assertEqual(r['samples'][1]['fill'],rgb(s['from']['fill'],s['to']['fill'],F(1,2),linear));self.assertEqual(r['samples'][1]['opacity'],.5)
            s['from']['fill']=[255,10,40,0];r=self.inspect(s)
            self.assertEqual(r['samples'][0]['fill'],[255,10,40,0]);self.assertEqual(r['samples'][1]['fill'],[10,80,250,96])
            s['from']['fill']=None;r=self.inspect(s)
            self.assertIsNone(r['samples'][0]['fill']);self.assertEqual(r['samples'][1]['fill'],[10,80,250,96])

    def test_triangle_rectangle_topology_uses_independent_rational_correspondence(self):
        a=[[0,0],[6,0],[3,6]];b=[[12,0],[18,0],[18,6],[12,6]]
        s=spec(count=3);s['from']['geometry']=path(a);s['to']['geometry']=path(b)
        r=self.inspect(s);p=polygons(r['samples'][1]['geometry'])[0]
        def position(points,t):
            n=len(points);i=min(int(t*n),n-1);f=t*n-i
            return [F(points[i][k])*(1-f)+F(points[(i+1)%n][k])*f for k in (0,1)]
        cuts=[F(0),F(1,4),F(1,3),F(1,2),F(2,3),F(3,4),F(1)]
        expected=[[float((x+y)/2) for x,y in zip(position(a,t),position(b,t))] for t in cuts]
        self.assert_points(p,expected);self.assertEqual(r['matched_commands'],8)
        self.assertEqual(r['samples'][0]['geometry'],s['from']['geometry']);self.assertEqual(r['samples'][-1]['geometry'],s['to']['geometry'])

    def test_cubic_line_correspondence_retains_exact_split_controls(self):
        g=dict(shape='path',commands=[dict(verb='move',to=[0,0]),dict(verb='cubic',control1=[0,4],control2=[4,4],to=[4,0])])
        s=spec(count=3);s['from']['geometry']=g;s['to']['geometry']=line([[8,0],[10,0],[12,0]])
        commands=self.inspect(s)['samples'][1]['geometry']['commands']
        self.assertEqual([c['verb'] for c in commands],['move','cubic','cubic'])
        self.assert_points([commands[0]['to'],commands[1]['control1'],commands[1]['control2'],commands[1]['to'],commands[2]['control1'],commands[2]['control2'],commands[2]['to']],
            [[4,0],[13/3,1],[31/6,1.5],[6,1.5],[41/6,1.5],[23/3,1],[8,0]])

    def test_unmatched_holes_collapse_and_grow_with_preserved_endpoint_geometry(self):
        outer=path([[0,0],[12,0],[12,12],[0,12]])
        hole=path([[4,4],[4,8],[8,8],[8,4]])
        ring=copy.deepcopy(outer);ring['commands']+=hole['commands']
        s=spec(count=3);s['from']['geometry']=ring;s['to']['geometry']=outer
        r=self.inspect(s);ps=polygons(r['samples'][1]['geometry'])
        self.assertEqual(len(ps),2);self.assertEqual([area(p) for p in ps],[144,4])
        self.assertEqual(sum(winding(p,6,6) for p in ps),0);self.assertNotEqual(sum(winding(p,4.5,6) for p in ps),0)
        s['reverse_order']=True;reversed_samples=self.inspect(s)['samples']
        self.assertEqual(reversed_samples[1]['geometry'],r['samples'][1]['geometry'])
        self.assertEqual(reversed_samples[0]['geometry'],outer);self.assertEqual(reversed_samples[-1]['geometry'],ring)

    def test_closed_seam_correspondence_is_editable_without_changing_endpoints(self):
        a=path([[4,4],[12,4],[12,12],[4,12]])
        b=path([[28,12],[20,12],[20,4],[28,4]])
        s=spec(count=3);s['from']['geometry']=a;s['to']['geometry']=b
        s['contours']=[{'from':0,'to':0,'to_start':2}]
        r=self.inspect(s);ps=polygons(r['samples'][1]['geometry'])
        self.assertAlmostEqual(area(ps[0]),64);self.assertEqual(r['samples'][-1]['geometry'],b)
        self.assert_points(ps[0],[[12,4],[20,4],[20,12],[12,12],[12,4]])
        d=self.document(s);self.assertEqual(self.pixels(d,2),self.pixels(self.expand(d),2))

    def test_reverse_order_and_spine_direction_have_separate_placement_semantics(self):
        s=spec(count=3,spine=dict(geometry=line([[12,12],[76,12]]),normal_offset=4),reverse_order=True)
        r=self.inspect(s)['samples'];self.assert_points([v['center'] for v in r],[[12,16],[44,16],[76,16]])
        self.assertEqual(r[0]['fill'],s['to']['fill']);self.assertEqual(r[-1]['fill'],s['from']['fill'])
        self.assertEqual(r[0]['bounds'],[6,12,18,20])
        s['spine']['reverse']=True;r=self.inspect(s)['samples']
        self.assert_points([v['center'] for v in r],[[76,8],[44,8],[12,8]])
        self.assertEqual(r[0]['fill'],s['to']['fill']);self.assertEqual(r[0]['tangent'],[-1,0])
        s['spine'].update(start=.25,end=.75);r=self.inspect(s)['samples']
        self.assert_points([v['center'] for v in r],[[60,8],[44,8],[28,8]])

    def test_curved_spine_count_positions_orientation_and_reversal_against_integrals(self):
        oracle=ArcOracle(CURVE)
        for reverse in (False,True):
            s=spec(count=7,spine=dict(curved(tolerance=.00001),start=.1,end=.9,reverse=reverse,normal_offset=2),orientation='tangent')
            r=self.inspect(s);report=r['spine']
            self.assertLessEqual(report['length_interval'][0],oracle.length);self.assertGreaterEqual(report['length_interval'][1],oracle.length)
            for k,v in enumerate(r['samples']):
                u=k/6;p,tangent=oracle.sample(oracle.length*(.1+.8*u),reverse)
                center=[p[0]-2*tangent[1],p[1]+2*tangent[0]]
                # The table reports baseline-position error; normal offset adds
                # angular sensitivity, bounded here independently from derivatives.
                self.assert_points([v['center']],[center],report['baseline_position_error_bound']+1e-5)
                self.assert_points([v['tangent']],[tangent],2e-6)
                w=4+8*u;h=4+4*u
                expected=[[center[0]+tangent[0]*x-tangent[1]*y,center[1]+tangent[1]*x+tangent[0]*y] for x,y in [(-w/2,-h/2),(w/2,-h/2),(w/2,h/2),(-w/2,h/2)]]
                actual=polygons(v['geometry'])[0][:4]
                self.assert_points(actual,expected,report['baseline_position_error_bound']+2e-5)
            d=self.document(s);self.assertEqual(self.pixels(d,3),self.pixels(self.expand(d),3))

    def test_closed_spine_endpoint_policy_subspan_and_custom_anchors(self):
        s=spec(count=5,spine=dict(geometry=path([[12,12],[44,12],[44,44],[12,44]])),orientation='tangent')
        r=self.inspect(s);self.assertTrue(r['spine']['closed'])
        self.assert_points([v['center'] for v in r['samples']],[[12,12],[44,12],[44,44],[12,44],[12,12]])
        s['spine']['end']=.75
        self.assert_points([v['center'] for v in self.inspect(s)['samples']],[[12,12],[36,12],[44,28],[36,44],[12,44]])
        s=spec(count=3);s['from']['anchor']=[0,0];s['to']['anchor']=[80,40]
        r=self.inspect(s);self.assertEqual(r['anchors'],[[0,0],[80,40]]);self.assertEqual(r['samples'][1]['center'],[40,20])
        self.assertEqual(r['samples'][1]['bounds'],[28,14,36,20])

    def test_explicit_contour_reordering_and_open_closed_collapse_grow(self):
        a=path([[0,0],[4,0],[4,4],[0,4]]);a['commands']+=path([[10,0],[14,0],[14,4],[10,4]])['commands']
        b=path([[30,0],[34,0],[34,4],[30,4]]);b['commands']+=path([[20,0],[24,0],[24,4],[20,4]])['commands']
        s=spec(count=3,contours=[{'from':0,'to':1},{'from':1,'to':0}]);s['from']['geometry']=a;s['to']['geometry']=b
        ps=polygons(self.inspect(s)['samples'][1]['geometry'])
        self.assert_points([p[0] for p in ps],[[10,0],[20,0]])
        s=spec(count=3);s['from']['geometry']=line([[0,0],[8,0]]);s['to']['geometry']=path([[16,0],[24,0],[20,8]])
        r=self.inspect(s);cs=r['samples'][1]['geometry']['commands']
        self.assertEqual(sum(c['verb']=='move' for c in cs),2);self.assertEqual(sum(c['verb']=='close' for c in cs),1)
        explicit=copy.deepcopy(s);explicit['contours']=[{'from':0,'to':None},{'from':None,'to':0}]
        self.assertEqual(self.inspect(explicit),r)
        explicit['contours']=[{'from':0,'to':0}];self.assertEqual(self.inspect(explicit,expected=1)['code'],'UNSUPPORTED')

    def test_strokes_interpolate_width_color_and_missing_opacity_preserve_controls(self):
        s=spec(count=3);s['from']['stroke']=dict(width=2,color=[20,40,200,255],dash=dict(array=[2,1]),cap='round')
        s['to']['stroke']=dict(width=6,color=[200,80,20,127],dash=dict(array=[2,1]),cap='round')
        r=self.inspect(s);middle=r['samples'][1]['stroke']
        self.assertEqual(middle['width'],4);self.assertEqual(middle['color'],rgb([20,40,200,255],[200,80,20,127],F(1,2)))
        self.assertEqual(middle['dash']['array'],[2,1]);self.assertEqual(middle['cap'],'round')
        d=self.document(s);self.assertEqual(self.pixels(d,2),self.pixels(self.expand(d),2))
        s['from']['stroke']=None;r=self.inspect(s);self.assertIsNone(r['samples'][0]['stroke']);self.assertEqual(r['samples'][1]['stroke']['width'],6)
        self.assertEqual(r['samples'][1]['stroke']['color'],[200,80,20,64])
        s['from']['stroke']=dict(width=2,color=[0,0,0,255],cap='square');self.assertEqual(self.inspect(s,expected=1)['code'],'UNSUPPORTED')

    def test_hierarchy_shear_reflection_opacity_clip_and_effects_match_expansion(self):
        d=self.document();node(d).update(parent='g',opacity=.7,transform=[-1,.1,.2,1,85,0],clip=dict(geometry=rect(0,0,52,50)))
        d['items'].insert(0,dict(id='g',opacity=.6,transform=[1,0,.2,1,1,2],content=dict(type='group',isolated=True)))
        d=self.invoke(dict(command='document.validate',document=d));e=self.expand(d);self.assertEqual(self.pixels(d,3),self.pixels(e,3))
        self.assertEqual(node(d)['transform'],node(e)['transform']);self.assertEqual(node(d)['clip'],node(e)['clip'])
        a=self.invoke(dict(command='document.inspect',document=d))['items'][-1]['geometry_bounds']
        b=next(v for v in self.invoke(dict(command='document.inspect',document=e))['items'] if v['id']=='blend')['geometry_bounds']
        self.assert_points([a[:2],a[2:]],[b[:2],b[2:]])
        node(d).pop('clip');node(d)['effects']=[dict(id='overlay',operator=dict(type='overlay'),color=[180,20,120,128])]
        self.assertEqual(self.pixels(d,2),self.pixels(self.expand(d),2))

    def test_component_and_raster_mask_sources_derive_edits_and_obey_dependency_locks(self):
        d=self.document();node(d)['parent']='source'
        d['items'].insert(0,dict(id='source',content=dict(type='component_source')))
        d['items']+=[instance('copy','source')]
        self.assertEqual(self.pixels(d,2),self.pixels(self.expand(d),2))
        before=self.invoke(dict(command='document.inspect',document=d))['items'][-1]['component_source_sha256']
        changed=self.edit(d,dict(op='interpolation',id='blend',interpolation=spec(count=3)))
        after=self.invoke(dict(command='document.inspect',document=changed))['items'][-1]['component_source_sha256']
        self.assertNotEqual(before,after);node(d,'copy')['locked']=True
        self.assertEqual(self.expand(d,expected=1)['code'],'LOCKED')
        d=self.document();d['kind']='raster'
        self.assertEqual(self.invoke(dict(command='document.validate',document=d),1)['code'],'INVALID_DOCUMENT')
        node(d)['parent']='source';d['items'].insert(0,dict(id='source',content=dict(type='mask_source')))
        d['items'].append(dict(id='pixels',content=dict(type='raster',width=96,height=64,rgba_hex='2878dcff'*(96*64)),artwork_mask=dict(source='source',region=[0,0,96,64],mode='alpha')))
        self.assertEqual(self.pixels(d,2),self.pixels(self.expand(d),2))
        self.assertGreater(sum(self.pixels(d)[2][3::4]),0);node(d,'pixels')['locked']=True
        self.assertEqual(self.expand(d,expected=1)['code'],'LOCKED')

    def test_svg_artboard_delivery_and_create_only_publication_keep_editable_input(self):
        d=self.document(spec(count=7,spine=curved(),orientation='tangent'));before=copy.deepcopy(d)
        svg=self.invoke(dict(command='document.export',document=d,format='svg'))
        self.assertTrue(any('Interpolation' in v for v in svg['losses']))
        self.assertEqual(len(ET.fromstring(svg['data']).findall('.//{*}path')),7)
        d['items']=[boards.BoardCliTests().board('page',96,64,bleed=dict(top=1,right=2,bottom=3,left=4)),dict(node(d),parent='page')]
        for format in ('png','svg'):
            a=self.invoke(dict(command='artboard.export',document=d,format=format,include_bleed=True))['artifacts'][0]['artifact']
            b=self.invoke(dict(command='artboard.export',document=self.expand(d),format=format,include_bleed=True))['artifacts'][0]['artifact']
            self.assertEqual(a['data'],b['data'])
            if format=='svg':self.assertTrue(any('Interpolation' in v for v in a['losses']))
        with tempfile.TemporaryDirectory() as directory:
            output=dict(output_root=directory,file_name='original.json',format='snapshot')
            self.invoke(dict(command='document.publish',document=before,output=output))
            self.assertEqual(json.loads((Path(directory)/'original.json').read_text()),before)
            self.assertEqual(self.invoke(dict(command='document.publish',document=before,output=output),1)['code'],'OUTPUT_EXISTS')

    def test_mcp_durable_count_spine_edits_reopen_retry_undo_redo_expand_and_publish(self):
        c=Client();self.addCleanup(lambda client=c:client.close() if not client.process.stdin.closed else None);c.initialize()
        d=self.document();s=spec(count=7,spine=curved(),orientation='tangent',reverse_order=True)
        self.assertEqual(c.success('interpolation.inspect',interpolation=s,include_geometry=True),self.inspect(s))
        with tempfile.TemporaryDirectory() as directory:
            session=dict(session_root=directory,session_id='interpolation')
            c.success('session.create',**session,request_id='create',document=d)
            args=dict(**session,expected_revision=0,request_id='change',action=dict(type='edit',operations=[dict(op='interpolation',id='blend',interpolation=s)]))
            changed=c.success('session.apply',**args)['document'];self.assertTrue(c.success('session.apply',**args)['replayed'])
            c.close();c=Client();self.addCleanup(c.close);c.initialize()
            expanded=c.success('session.apply',**session,expected_revision=1,request_id='expand',action=dict(type='edit',operations=[dict(op='interpolation_expand',id='blend')]))['document']
            self.assertEqual(self.pixels(changed,2),self.pixels(expanded,2))
            undone=c.success('session.apply',**session,expected_revision=2,request_id='undo',action=dict(type='undo'))['document'];self.assertEqual(undone['items'],changed['items'])
            redone=c.success('session.apply',**session,expected_revision=3,request_id='redo',action=dict(type='redo'))['document'];self.assertEqual(redone['items'],expanded['items'])
            c.success('session.publish',**session,expected_revision=4,output=dict(output_root=directory,file_name='steps.png',format='png'))
            self.assertTrue((Path(directory)/'steps.png').exists());c.success('session.verify',**session)
            stale=c.tool('session.apply',**session,expected_revision=0,request_id='stale',action=dict(type='undo'))
            self.assertTrue(stale['isError'])

    def test_strict_pairing_stroke_spine_limits_atomic_failure_and_cancellation(self):
        for patch in [dict(count=1),dict(count=129),dict(count=3.5),dict(extra=1),dict(orientation='upright'),dict(contours=[{'from':0,'to':0,'to_start':4}]),dict(contours=[{'from':None,'to':None}]),dict(contours=[{'from':0,'to':0},{'from':0,'to':0}]),dict(contours=[{'from':0,'to':None}]),dict(contours=[{'from':1,'to':0}])]:
            self.inspect(spec(**patch),expected=1)
        for patch in [dict(start=-.1),dict(end=1.1),dict(start=.5,end=.5),dict(tolerance=0),dict(normal_offset=32769)]:
            self.inspect(spec(spine=dict(geometry=line([[0,0],[1,0]]),**patch)),expected=1)
        compound=line([[0,0],[1,0]]);compound['commands']+=line([[2,0],[3,0]])['commands']
        self.assertEqual(self.inspect(spec(spine=dict(geometry=compound)),expected=1)['code'],'UNSUPPORTED')
        self.inspect(spec(spine=dict(geometry=line([[0,0],[0,0]]))),expected=1)
        s=spec();s['from']['stroke']=dict(width=2,color=dict(type='linear',start=[0,0],end=[1,0],stops=[dict(offset=0,color=[0,0,0,255]),dict(offset=1,color=[255]*4)]))
        self.assertEqual(self.inspect(s,expected=1)['code'],'UNSUPPORTED')
        d=self.document();before=copy.deepcopy(d)
        self.edit(d,dict(op='interpolation',id='blend',interpolation=spec(count=3)),dict(op='remove',id='missing'),expected=1);self.assertEqual(d,before)
        with tempfile.TemporaryDirectory() as directory:
            marker=Path(directory)/'cancel';marker.write_text('cancel')
            self.assertEqual(self.inspect(spec(),control=dict(cancel_file=str(marker)),expected=1)['code'],'CANCELLED')
        self.assertEqual(self.inspect(spec(),control=dict(timeout_ms=0),expected=1)['code'],'TIMEOUT')

    def test_hidden_generated_command_item_and_world_limits_are_enforced(self):
        d=self.document(spec(count=128));node(d)['visible']=False
        d['items'].append(dict(copy.deepcopy(node(d)),id='second'))
        self.assertEqual(self.invoke(dict(command='document.validate',document=d),1)['code'],'RESOURCE_LIMIT')
        s=spec(count=128);s['from']['geometry']=path([[k/10,k%2] for k in range(40)])
        self.assertEqual(self.inspect(s,expected=1)['code'],'RESOURCE_LIMIT')
        d=self.document();node(d)['visible']=False;node(d)['transform']=[2000,0,0,1,0,0]
        self.assertEqual(self.invoke(dict(command='document.validate',document=d),1)['code'],'RESOURCE_LIMIT')
        d=self.document();node(d)['content']['interpolation']['from']['geometry']=path([[k/10,k%2] for k in range(4090)])
        self.assertEqual(self.invoke(dict(command='document.validate',document=d),1)['code'],'RESOURCE_LIMIT')

    def test_geometry_queries_saved_controls_and_atomic_expansion_keep_sources(self):
        d=self.document();before=copy.deepcopy(d)
        inspected=self.invoke(dict(command='document.inspect',document=d));self.assertEqual(inspected['items'][0]['interpolation'],node(d)['content']['interpolation'])
        q=self.invoke(dict(command='document.query',document=d,query=dict(types=['interpolation'])));self.assertEqual(q['ids'],['blend'])
        expanded=self.expand(d);self.assertEqual(d,before)
        self.assertEqual(node(expanded)['content']['type'],'group')
        self.assertEqual(len({i['id'] for i in expanded['items']}),6)
        self.assertEqual(self.pixels(d,3),self.pixels(expanded,3))
        snapshot=json.loads(self.invoke(dict(command='document.export',document=d,format='snapshot'))['data'])
        self.assertEqual(snapshot,d)
        locked=copy.deepcopy(d);node(locked)['locked']=True
        self.assertEqual(self.expand(locked,expected=1)['code'],'LOCKED')

    def test_spine_subdivision_limits_are_shared_even_for_hidden_objects(self):
        s=spec(count=2,spine=curved([[0,0],[100,100],[-100,100],[0,0]],tolerance=.00001))
        leaves=self.inspect(s)['spine']['leaves'];self.assertGreater(leaves,65536/3);self.assertLess(leaves,32768)
        d=self.document(s);node(d)['visible']=False
        d['items']+=[dict(copy.deepcopy(node(d)),id='second')]
        self.invoke(dict(command='document.validate',document=d))
        d['items']+=[dict(copy.deepcopy(node(d)),id='third')]
        r=self.invoke(dict(command='document.validate',document=d),1);self.assertEqual(r['code'],'RESOURCE_LIMIT');self.assertIn('65536',r['message'])
        s['spine']['geometry']=curved([[0,0],[32000,32000],[-32000,32000],[0,0]])['geometry'];s['spine']['tolerance']=.000001
        self.assertEqual(self.inspect(s,expected=1)['code'],'RESOURCE_LIMIT')

    def test_generated_ids_avoid_collisions_and_transfer_keeps_editable_spec(self):
        d=self.document();first=self.expand(d)['items'][1]['id']
        d=self.edit(d,dict(op='add',item=dict(id=first,visible=False,content=dict(type='vector',geometry=rect(0,0,1,1),fill=[0,0,0,255]))))
        a=self.expand(d);b=self.expand(d);self.assertEqual(a,b)
        ids=[i['id'] for i in a['items']];self.assertEqual(len(ids),len(set(ids)));self.assertIn(first+'-1',ids)
        target=self.invoke(dict(command='document.create',id='target',kind='vector',width=96,height=64))
        transferred=self.edit(target,dict(op='transfer',transfer=dict(source=d,ids=['blend'],prefix='copy')))
        self.assertEqual(node(transferred,'copy-blend')['content'],node(d)['content'])
        self.assertEqual(self.pixels(transferred,2),self.pixels(d,2))
        expanded=self.expand(transferred,'copy-blend');self.assertEqual(self.pixels(transferred,2),self.pixels(expanded,2))

if __name__=='__main__':unittest.main()
