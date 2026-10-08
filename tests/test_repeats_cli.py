"""Original repeat lattices, affine oracles, seam coverage and durable controls."""
import base64
import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import test_editing_cli as editing
import test_boards_cli as boards
from test_mcp import Client
from test_stroke_outlines_cli import polygons,winding
from test_interpolation_cli import rect,path,map_point
from test_instances_cli import instance
from test_transform_policies_cli import matrix_product

INK=[40,120,220,255]
def spec(layout=None,g=None,**kw):
    return dict(geometry=g or rect(-2,-2,4,4),fill=INK,origin=[12,12],layout=layout or dict(type='grid',columns=3,rows=2,step=[12,10]),**kw)
def node(d,id='repeat'):return next(i for i in d['items'] if i['id']==id)
def signed(p):return sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(p,p[1:]+p[:1]))/2
def hexagon(radius,flat=False):
    a=radius*math.sqrt(3)/2
    points=[[0,-radius],[a,-radius/2],[a,radius/2],[0,radius],[-a,radius/2],[-a,-radius/2]]
    if flat:points=[[-y,x] for x,y in points]
    return path(points)
class RepeatTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def inspect(self,s,expected=0,**kw):return self.invoke(dict(command='repeat.inspect',repeat=s,include_geometry=True,**kw),expected)
    def edit(self,d,*ops,expected=0):
        r=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=list(ops)),expected)
        return r if expected else r['document']
    def document(self,s=None):
        d=self.invoke(dict(command='document.create',id='repeat-fixture',kind='vector',width=96,height=64))
        return self.edit(d,dict(op='add',item=dict(id='repeat',content=dict(type='repeat',repeat=s or spec()))))
    def expand(self,d,id='repeat',expected=0):return self.edit(d,dict(op='repeat_expand',id=id),expected=expected)
    def pixels(self,d,scale=1):
        p=self.invoke(dict(command='document.export',document=d,format='png',scale=scale))
        return editing.png_pixels(base64.b64decode(p['data']))[:3]
    def points(self,a,b,tolerance=1e-10):
        self.assertEqual(len(a),len(b))
        for x,y in zip(a,b):self.assertLessEqual(math.dist(x,y),tolerance,(x,y))
    def test_grid_exact_count_centers_bounds_and_pixels(self):
        s=spec();r=self.inspect(s)
        centers=[[12+12*c,12+10*row] for row in range(2) for c in range(3)]
        self.points([v['center'] for v in r['placements']],centers)
        self.assertEqual(r['count'],6);self.assertEqual(r['bounds'],[10,10,38,24]);self.assertEqual(r['commands'],30)
        d=self.document(s);w,h,p=self.pixels(d,2)
        for y in range(h):
            for x in range(w):
                inside=any(abs((x+.5)/2-cx)<2 and abs((y+.5)/2-cy)<2 for cx,cy in centers)
                self.assertEqual(p[(y*w+x)*4:][:4],bytes(INK if inside else [0]*4))
        self.assertEqual(self.pixels(d,3),self.pixels(self.expand(d),3))
    def test_brick_rows_columns_fractional_and_negative_steps(self):
        for axis in ['rows','columns']:
            s=spec(dict(type='brick',columns=3,rows=3,step=[-8,6],axis=axis,offset=.25))
            r=self.inspect(s)
            expected=[[12-8*(c+(.25*(row%2) if axis=='rows' else 0)),12+6*(row+(.25*(c%2) if axis=='columns' else 0))] for row in range(3) for c in range(3)]
            self.points([v['center'] for v in r['placements']],expected)
            d=self.document(s);self.assertEqual(self.pixels(d,2),self.pixels(self.expand(d),2))
    def test_hexagonal_lattices_have_independent_centers_and_no_internal_alpha_seams(self):
        for flat in (False,True):
            s=spec(dict(type='hex',columns=4,rows=4,radius=6,orientation='flat' if flat else 'pointy'),hexagon(6,flat))
            r=self.inspect(s)
            expected=[[12+(9*c if flat else math.sqrt(3)*6*(c+.5*(row%2))),12+(math.sqrt(3)*6*(row+.5*(c%2)) if flat else 9*row)] for row in range(4) for c in range(4)]
            self.points([v['center'] for v in r['placements']],expected)
            d=self.document(s);w,h,p=self.pixels(d,4)
            for y in range(18*4,32*4):
                for x in range(18*4,32*4):self.assertEqual(p[(y*w+x)*4:][:4],bytes(INK),(flat,x,y))
            self.assertEqual(self.pixels(d,2),self.pixels(self.expand(d),2))
    def test_touching_brick_and_mirrored_tiles_fill_once_without_internal_seams(self):
        for layout in [dict(type='grid',rows=3,columns=4,step=[8,6],mirror='both'),dict(type='brick',rows=3,columns=4,step=[8,6],offset=.5)]:
            d=self.document(spec(layout,rect(-4,-3,8,6)));w,h,p=self.pixels(d,3)
            for y in range(9*3,27*3):
                for x in range(12*3,40*3):self.assertEqual(p[(y*w+x)*4:][:4],bytes(INK))
        s=spec(dict(type='grid',rows=1,columns=2,step=[2,6],mirror='columns'),rect(-4,-3,8,6));s['fill']=[40,120,220,128]
        d=self.document(s);w,h,p=self.pixels(d)
        self.assertTrue(all(p[(y*w+x)*4+3]==128 for y in range(9,15) for x in range(8,18)))
    def test_mirror_parity_preserves_authored_winding_and_holes(self):
        g=path([[-4,-3],[4,-3],[4,3],[-4,3]])
        g['commands']+=path([[-2,-1],[-2,1],[0,1],[0,-1]])['commands']
        for mode in ['none','columns','rows','both']:
            s=spec(dict(type='grid',rows=2,columns=2,step=[12,10],mirror=mode),g)
            r=self.inspect(s);ps=polygons(r['geometry'])
            self.assertEqual([round(signed(p)) for p in ps],[48,-4]*4)
            for placement,outer,hole in zip(r['placements'],ps[::2],ps[1::2]):
                c=placement['column'];row=placement['row'];sx=-1 if mode in ['columns','both'] and c%2 else 1;sy=-1 if mode in ['rows','both'] and row%2 else 1
                self.assertEqual(placement['reflected'],sx*sy<0)
                self.assertEqual(sum(winding(poly,12+12*c-sx,12+10*row) for poly in [outer,hole]),0)
                self.assertNotEqual(sum(winding(poly,12+12*c+2*sx,12+10*row) for poly in [outer,hole]),0)
    def test_closed_radial_count_quadrants_orientation_and_seam_exclusion(self):
        for mode in ['fixed','radial','tangent']:
            s=spec(dict(type='radial',count=4,radius=10,orientation=mode),rect(-3,-1,6,2));s['origin']=[32,32]
            r=self.inspect(s);self.points([v['center'] for v in r['placements']],[[42,32],[32,42],[22,32],[32,22]])
            self.assertEqual(len({tuple(v['center']) for v in r['placements']}),4)
            for k,p in enumerate(r['placements']):
                rotations={'fixed':[[1,0]]*4,'radial':[[1,0],[0,1],[-1,0],[0,-1]],'tangent':[[0,1],[-1,0],[0,-1],[1,0]]}
                u=rotations[mode][k];cx,cy=p['center']
                self.points([map_point(p['matrix'],q) for q in [[-3,-1],[3,-1],[3,1],[-3,1]]],[[cx+u[0]*x-u[1]*y,cy+u[1]*x+u[0]*y] for x,y in [[-3,-1],[3,-1],[3,1],[-3,1]]])
    def test_open_radial_arcs_retain_both_endpoints_and_reverse_tangents(self):
        for sweep in [180,-180]:
            s=spec(dict(type='radial',count=3,radius=10,start_angle=0,sweep=sweep,closed=False,orientation='tangent'));s['origin']=[32,32]
            r=self.inspect(s);self.points([v['center'] for v in r['placements']],[[42,32],[32,32+(10 if sweep>0 else -10)],[22,32]])
            self.points([r['placements'][0]['matrix'][:2]],[[0,1 if sweep>0 else -1]])
        s=spec(dict(type='radial',count=1,radius=10));self.assertEqual(self.inspect(s)['count'],1)
    def test_layout_and_motif_transforms_custom_anchor_match_independent_matrices(self):
        s=spec(dict(type='grid',rows=2,columns=2,step=[12,8],mirror='both'),rect(0,0,4,2),anchor=[0,0],motif_transform=[2,0,.5,1,1,-1],transform=[1,.25,.5,1,2,3])
        r=self.inspect(s)
        for k,p in enumerate(r['placements']):
            c=k%2;row=k//2;sx=1-2*c;sy=1-2*row
            pose=[sx,0,0,sy,12+12*c,12+8*row]
            expected=matrix_product(s['transform'],matrix_product(pose,s['motif_transform']))
            self.assertEqual(p['matrix'],expected)
        d=self.document(s);node(d).update(parent='g',transform=[-1,0,.25,1,90,0]);d['items'].insert(0,dict(id='g',transform=[1,.1,0,1,0,2],content=dict(type='group')))
        self.assertEqual(self.pixels(d,3),self.pixels(self.expand(d),3))
    def test_cubic_controls_survive_reflection_and_closed_contour_reversal(self):
        g=dict(shape='path',commands=[dict(verb='move',to=[0,0]),dict(verb='cubic',control1=[0,6],control2=[6,6],to=[6,0]),dict(verb='close')])
        s=spec(dict(type='grid',rows=1,columns=2,step=[12,8],mirror='columns'),g,anchor=[0,0])
        cs=self.inspect(s)['geometry']['commands'];self.assertEqual([c['verb'] for c in cs],['move','cubic','close']*2)
        self.points([cs[1]['control1'],cs[1]['control2'],cs[1]['to']],[[12,18],[18,18],[18,12]])
        self.points([cs[3]['to'],cs[4]['control1'],cs[4]['control2'],cs[4]['to']],[[18,12],[18,18],[24,18],[24,12]])
    def test_evenodd_overlap_is_explicit_and_paint_stays_in_repeat_coordinates(self):
        s=spec(dict(type='grid',rows=1,columns=2,step=[2,8]),rect(-3,-2,6,4));s['fill_rule']='even_odd'
        d=self.document(s);w,h,p=self.pixels(d);self.assertEqual(p[(12*w+12)*4+3],0);self.assertEqual(p[(12*w+9)*4+3],255)
        s['fill_rule']='nonzero';s['fill']=dict(type='linear',start=[8,0],end=[18,0],stops=[dict(offset=0,color=[0,0,0,255]),dict(offset=1,color=[200,100,50,255])])
        d=self.document(s);w,h,p=self.pixels(d);self.assertEqual(p[(12*w+12)*4:][:4],bytes([90,45,23,255]))
        self.assertEqual(self.pixels(d,2),self.pixels(self.expand(d),2))
    def test_appearance_masks_effects_and_locked_edits_preserve_source(self):
        d=self.document();node(d).update(opacity=.6,clip=dict(geometry=rect(0,0,26,30)),effects=[dict(id='overlay',operator=dict(type='overlay'),color=[180,50,100,128])])
        before=copy.deepcopy(d);self.assertEqual(self.pixels(d,2),self.pixels(self.expand(d),2));self.assertEqual(d,before)
        node(d)['locked']=True;self.assertEqual(self.expand(d,expected=1)['code'],'LOCKED')
        self.assertEqual(self.edit(d,dict(op='repeat',id='repeat',repeat=spec()),expected=1)['code'],'LOCKED')
    def test_component_and_mask_sources_propagate_layout_edits_and_dependency_locks(self):
        d=self.document();node(d)['parent']='source';d['items'].insert(0,dict(id='source',content=dict(type='component_source')));d['items'].append(instance('copy','source'))
        self.assertEqual(self.pixels(d,2),self.pixels(self.expand(d),2))
        changed=self.edit(d,dict(op='repeat',id='repeat',repeat=spec(dict(type='radial',count=5,radius=10))))
        self.assertNotEqual(self.pixels(d),self.pixels(changed));node(d,'copy')['locked']=True
        self.assertEqual(self.expand(d,expected=1)['code'],'LOCKED')
        d=self.document();d['kind']='raster';self.assertEqual(self.invoke(dict(command='document.validate',document=d),1)['code'],'INVALID_DOCUMENT')
        node(d)['parent']='source';d['items'].insert(0,dict(id='source',content=dict(type='mask_source')))
        d['items'].append(dict(id='pixels',content=dict(type='raster',width=96,height=64,rgba_hex='2878dcff'*(96*64)),artwork_mask=dict(source='source',region=[0,0,96,64],mode='alpha')))
        self.assertEqual(self.pixels(d,2),self.pixels(self.expand(d),2));self.assertGreater(sum(self.pixels(d)[2][3::4]),0)
    def test_saved_controls_type_query_transfer_and_svg_expansion(self):
        d=self.document();before=copy.deepcopy(d)
        self.assertEqual(self.invoke(dict(command='document.inspect',document=d))['items'][0]['repeat'],node(d)['content']['repeat'])
        self.assertEqual(self.invoke(dict(command='document.query',document=d,query=dict(types=['repeat'])))['ids'],['repeat'])
        self.assertEqual(json.loads(self.invoke(dict(command='document.export',document=d,format='snapshot'))['data']),d)
        artifact=self.invoke(dict(command='document.export',document=d,format='svg'))
        self.assertTrue(any('Repeat layouts' in v for v in artifact['losses']))
        self.assertEqual(len(ET.fromstring(artifact['data']).findall('.//{*}path')),1)
        self.assertEqual(artifact['data'],self.invoke(dict(command='document.export',document=self.expand(d),format='svg'))['data'])
        target=self.invoke(dict(command='document.create',id='target',kind='vector',width=96,height=64))
        out=self.edit(target,dict(op='transfer',transfer=dict(source=d,ids=['repeat'],prefix='copy')))
        self.assertEqual(node(out,'copy-repeat')['content'],node(d)['content']);self.assertEqual(self.pixels(out),self.pixels(d));self.assertEqual(d,before)
    def test_artboard_delivery_and_publication_keep_controls_and_seams(self):
        d=self.document(spec(dict(type='brick',rows=3,columns=4,step=[8,6]),rect(-4,-3,8,6)))
        d['items']=[boards.BoardCliTests().board('page',64,40,bleed=dict(top=1,right=1,bottom=1,left=1)),dict(node(d),parent='page')]
        for fmt in ['png','svg']:
            a=self.invoke(dict(command='artboard.export',document=d,format=fmt,include_bleed=True))['artifacts'][0]['artifact']
            b=self.invoke(dict(command='artboard.export',document=self.expand(d),format=fmt,include_bleed=True))['artifacts'][0]['artifact']
            self.assertEqual(a['data'],b['data'])
            if fmt=='svg':self.assertTrue(any('Repeat layouts' in v for v in a['losses']))
        with tempfile.TemporaryDirectory() as root:
            output=dict(output_root=root,file_name='repeat.json',format='snapshot')
            self.invoke(dict(command='document.publish',document=d,output=output))
            self.assertEqual(json.loads((Path(root)/'repeat.json').read_text()),self.invoke(dict(command='document.validate',document=d)))
            self.assertEqual(self.invoke(dict(command='document.publish',document=d,output=output),1)['code'],'OUTPUT_EXISTS')
    def test_mcp_durable_layout_edit_restart_retry_expansion_undo_redo_publish(self):
        c=Client();self.addCleanup(lambda client=c:client.close() if not client.process.stdin.closed else None);c.initialize()
        d=self.document();s=spec(dict(type='radial',count=8,radius=12,orientation='radial'));s['origin']=[32,32]
        self.assertEqual(c.success('repeat.inspect',repeat=s,include_geometry=True),self.inspect(s))
        with tempfile.TemporaryDirectory() as root:
            session=dict(session_root=root,session_id='repeat')
            c.success('session.create',**session,request_id='create',document=d)
            args=dict(**session,expected_revision=0,request_id='change',action=dict(type='edit',operations=[dict(op='repeat',id='repeat',repeat=s)]))
            changed=c.success('session.apply',**args)['document'];self.assertTrue(c.success('session.apply',**args)['replayed'])
            c.close();c=Client();self.addCleanup(c.close);c.initialize()
            expanded=c.success('session.apply',**session,expected_revision=1,request_id='expand',action=dict(type='edit',operations=[dict(op='repeat_expand',id='repeat')]))['document']
            self.assertEqual(self.pixels(changed,2),self.pixels(expanded,2))
            undone=c.success('session.apply',**session,expected_revision=2,request_id='undo',action=dict(type='undo'))['document'];self.assertEqual(undone['items'],changed['items'])
            redone=c.success('session.apply',**session,expected_revision=3,request_id='redo',action=dict(type='redo'))['document'];self.assertEqual(redone['items'],expanded['items'])
            c.success('session.publish',**session,expected_revision=4,output=dict(output_root=root,file_name='repeat.png',format='png'));c.success('session.verify',**session)
    def test_strict_layouts_motifs_singular_transforms_and_atomic_rollback(self):
        for layout in [dict(type='grid',rows=0,columns=2,step=[1,1]),dict(type='grid',rows=2,columns=65,step=[1,1]),dict(type='grid',rows=1,columns=1,step=[0,1]),dict(type='brick',rows=2,columns=2,step=[1,1],offset=1.1),dict(type='hex',rows=2,columns=2,radius=0),dict(type='radial',count=4,radius=4,sweep=180),dict(type='radial',count=4,radius=4,sweep=360,closed=False),dict(type='radial',count=1,radius=4,sweep=180,closed=False),dict(type='radial',count=4,radius=4,start_angle=361)]:
            self.inspect(spec(layout),expected=1)
        s=spec();s['geometry']['shape']='rect';s['unknown']=1;self.inspect(s,expected=1)
        s=spec();s['transform']=[0,0,0,0,0,0];self.assertEqual(self.inspect(s,expected=1)['code'],'UNSUPPORTED')
        s=spec();s['geometry']=dict(shape='path',commands=[dict(verb='move',to=[0,0]),dict(verb='line',to=[1,0])]);self.assertEqual(self.inspect(s,expected=1)['code'],'UNSUPPORTED')
        d=self.document();before=copy.deepcopy(d);self.edit(d,dict(op='repeat_expand',id='repeat'),dict(op='remove',id='missing'),expected=1);self.assertEqual(d,before)
    def test_hidden_and_aggregate_geometry_limits_extreme_coordinates_and_cancellation(self):
        s=spec(dict(type='grid',rows=1,columns=128,step=[1,1]),path([[i*.1,i%2] for i in range(40)]))
        self.assertEqual(self.inspect(s,expected=1)['code'],'RESOURCE_LIMIT')
        s=spec(dict(type='grid',rows=1,columns=100,step=[1,1]),path([[i*.1,i%2] for i in range(20)]))
        d=self.document(s);node(d)['visible']=False;d['items'].append(dict(copy.deepcopy(node(d)),id='second'))
        self.assertEqual(self.invoke(dict(command='document.validate',document=d),1)['code'],'RESOURCE_LIMIT')
        s=spec(dict(type='grid',rows=1,columns=3,step=[32768,1]));self.inspect(s,expected=1)
        self.assertEqual(self.inspect(spec(),control=dict(timeout_ms=0),expected=1)['code'],'TIMEOUT')
        with tempfile.TemporaryDirectory() as root:
            marker=Path(root)/'cancel';marker.write_text('cancel')
            self.assertEqual(self.inspect(spec(),control=dict(cancel_file=str(marker)),expected=1)['code'],'CANCELLED')

    def test_arbitrary_radial_angles_have_uniform_distances_and_exact_saved_controls(self):
        s=spec(dict(type='radial',count=13,radius=15,start_angle=17,sweep=-360,orientation='radial'));s['origin']=[32,32]
        r=self.inspect(s);centers=[p['center'] for p in r['placements']]
        expected=[[32+15*math.cos(math.radians(17-360*k/13)),32+15*math.sin(math.radians(17-360*k/13))] for k in range(13)]
        self.points(centers,expected)
        distances=[math.dist(a,b) for a,b in zip(centers,centers[1:]+centers[:1])]
        for d in distances:self.assertAlmostEqual(d,30*math.sin(math.pi/13),places=12)
        d=self.document(s);stored=node(d)['content']['repeat'];self.assertEqual(stored['layout']['count'],13)
        self.assertEqual(stored['layout']['sweep'],-360);self.assertEqual(stored['layout']['start_angle'],17)
        self.assertEqual(self.pixels(d,2),self.pixels(self.expand(d),2))

    def test_repeat_and_interpolation_materialize_together_with_independent_controls(self):
        from test_interpolation_cli import spec as interpolation
        d=self.document()
        d=self.edit(d,dict(op='add',item=dict(id='sequence',transform=[1,0,0,1,0,28],content=dict(type='interpolation',interpolation=interpolation(count=3)))))
        expanded=self.edit(d,dict(op='repeat_expand',id='repeat'),dict(op='interpolation_expand',id='sequence'))
        self.assertEqual(self.pixels(d,2),self.pixels(expanded,2))
        self.assertEqual(node(d)['content']['type'],'repeat')

if __name__=='__main__':unittest.main()
