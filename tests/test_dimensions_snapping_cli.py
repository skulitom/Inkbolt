"""Original analytic lengths/areas, physical units and frozen-reference layout checks."""
import copy
from decimal import Decimal,localcontext
from fractions import Fraction as F
import json
import math
from pathlib import Path
import tempfile
import unittest
import test_editing_cli as editing
import test_boards_cli as boards
import test_render_quality_cli as quality
import test_instances_cli as instances
from test_mcp import Client


rect=quality.rect
def transform(p,m):return [m[0]*p[0]+m[2]*p[1]+m[4],m[1]*p[0]+m[3]*p[1]+m[5]]
def rotation(degrees):
    a=math.radians(degrees);return [math.cos(a),math.sin(a),-math.sin(a),math.cos(a),0,0]
def path(commands,id='curve',**kw):return dict(id=id,content=dict(type='vector',geometry=dict(shape='path',commands=commands),fill=[30,100,210,255]),**kw)
def parabola(closed=True):
    c=[dict(verb='move',to=[0,0]),dict(verb='cubic',control1=[1,0],control2=[2,1],to=[3,3])]
    return c+[dict(verb='close')] if closed else c


class DimensionsSnappingTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    document=quality.RenderQualityTests.document
    edit=quality.RenderQualityTests.edit
    def measure(self,d,ids=None,expected=0,**options):
        return self.invoke(dict(command='geometry.measure',document=d,options=dict(ids=ids or ['art'],**options)),expected)
    def metric(self,d,id='art',**kw):return self.measure(d,[id],**kw)['items'][0]
    def resize(self,d,id='art',expected=0,**kw):return self.edit(d,[dict(op='dimensions',id=id,dimensions=kw)],expected)
    def snap(self,d,ids=None,expected=0,**kw):
        return self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='snap',ids=ids or ['art'],snap=kw)]),expected)
    def encloses(self,metric,exact,tolerance):
        exact=F(exact);lo=F(metric['lower_exact']);hi=F(metric['upper_exact'])
        self.assertLessEqual(lo,exact);self.assertGreaterEqual(hi,exact)
        self.assertLessEqual(F(metric['lower']),lo);self.assertGreaterEqual(F(metric['upper']),hi)
        self.assertLessEqual(abs(F(metric['value'])-exact),F(metric['absolute_error_bound']))
        self.assertLessEqual(metric['absolute_error_bound'],tolerance)

    def test_exact_rectangle_dimensions_area_perimeter_and_all_physical_units(self):
        d=self.document([rect(x=-1.25,y=2.75,w=3,h=4,transform=[3,4,-4,3,10,20])]);d['resolution_ppi']=144
        source=copy.deepcopy(d)
        for unit,factor in [('px',F(1)),('pt',F(2)),('pc',F(24)),('mm',F(720,127)),('cm',F(7200,127)),('in',F(144))]:
            r=self.measure(d,unit=unit);m=r['items'][0]
            self.assertEqual(F(r['pixels_per_unit_exact']),factor)
            self.encloses(m['boundary_length'],F(70)/factor,1e-4)
            self.encloses(m['signed_area'],F(300)/factor**2,1e-6)
            self.assertAlmostEqual(m['width'],25/float(factor));self.assertAlmostEqual(m['height'],24/float(factor))
        self.assertEqual(d,source)

    def test_fractional_rectangles_use_declared_sizes_without_origin_cancellation(self):
        d=self.document([rect(x=8192.123456789,y=-2000.987654321,w=.00123456789,h=.00234567891)])
        g=d['items'][0]['content']['geometry'];m=self.metric(d)
        self.encloses(m['signed_area'],F(g['width'])*F(g['height']),1e-6)
        self.encloses(m['boundary_length'],2*(F(g['width'])+F(g['height'])),1e-4)

    def test_closed_parabolic_cubic_integral_and_length_against_independent_formula(self):
        d=self.document([path(parabola())]);m=self.metric(d,'curve',tolerance=1e-5)
        self.encloses(m['signed_area'],F(3,2),1e-6)
        with localcontext() as c:
            c.prec=60;length=Decimal(3)/4*(2*Decimal(5).sqrt()+(Decimal(2)+Decimal(5).sqrt()).ln())+Decimal(18).sqrt()
            self.encloses(m['boundary_length'],F(length),1e-5)
        self.assertEqual(m['components'][0]['closed_contours'],1)

    def test_open_cubic_length_has_no_implicit_closure_and_null_area(self):
        d=self.document([path(parabola(False))]);m=self.metric(d,'curve')
        self.assertIsNone(m['signed_area']);self.assertEqual(m['components'][0]['closed_contours'],0)
        with localcontext() as c:
            c.prec=60;length=Decimal(3)/4*(2*Decimal(5).sqrt()+(Decimal(2)+Decimal(5).sqrt()).ln())
            self.encloses(m['boundary_length'],F(length),1e-4)

    def test_cusp_backtracking_and_zero_length_segments_have_valid_length_bounds(self):
        d=self.document([path([dict(verb='move',to=[0,0]),dict(verb='cubic',control1=[1,0],control2=[-1,0],to=[0,0]),dict(verb='line',to=[0,0]),dict(verb='close')])])
        m=self.metric(d,'curve');self.encloses(m['signed_area'],0,1e-6)
        with localcontext() as c:c.prec=60;self.encloses(m['boundary_length'],F(Decimal(2)/Decimal(3).sqrt()),1e-4)

    def test_circle_and_sheared_ellipse_use_analytic_source_not_quarter_cubic(self):
        g=dict(shape='ellipse',cx=-2,cy=3,rx=5,ry=5)
        d=self.document([dict(id='art',content=dict(type='vector',geometry=g,fill=[255]*4))])
        m=self.metric(d);self.encloses(m['boundary_length'],F(str(10*math.pi)),1e-4)
        self.assertAlmostEqual(m['signed_area']['value'],25*math.pi,places=11)
        g['rx']=5;g['ry']=3;d['items'][0]['content']['geometry']=g;matrix=[1.25,.5,-.25,.75,2,3];d['items'][0]['transform']=matrix
        m=self.metric(d);n=16384;h=2*math.pi/n
        def speed(t):
            x,y=-5*math.sin(t),3*math.cos(t)
            return math.hypot(matrix[0]*x+matrix[2]*y,matrix[1]*x+matrix[3]*y)
        reference=h/3*(speed(0)+speed(n*h)+sum((4 if i%2 else 2)*speed(i*h) for i in range(1,n)))
        self.encloses(m['boundary_length'],F(reference),1e-4)
        self.assertAlmostEqual(m['signed_area']['value'],15*math.pi*(matrix[0]*matrix[3]-matrix[1]*matrix[2]),places=10)

    def test_compound_holes_reflection_and_self_intersection_have_explicit_signed_metrics(self):
        loops=[[(0,0),(10,0),(10,10),(0,10)],[(2,2),(2,8),(8,8),(8,2)]]
        commands=[]
        for loop in loops:commands += [dict(verb='move' if i==0 else 'line',to=p) for i,p in enumerate(loop)]+[dict(verb='close')]
        d=self.document([path(commands,id='art')]);m=self.metric(d)
        self.encloses(m['signed_area'],64,1e-6);self.encloses(m['boundary_length'],64,1e-4)
        d['items'][0]['transform']=[-1,0,0,1,12,0];self.encloses(self.metric(d)['signed_area'],-64,1e-6)
        crossed=[dict(verb='move',to=[0,0]),dict(verb='line',to=[4,4]),dict(verb='line',to=[0,4]),dict(verb='line',to=[4,0]),dict(verb='close')]
        d=self.document([path(crossed,id='art')]);r=self.measure(d);self.encloses(r['items'][0]['signed_area'],0,1e-6)
        self.assertIn('not_filled_union_area',r['area_semantics'])

    def test_rotated_bounds_use_actual_shapes_and_group_hierarchy(self):
        matrix=rotation(30);matrix[4:]=[10,20]
        d=self.document([dict(id='group',transform=matrix,content=dict(type='group')),rect('a',x=1,y=2,w=3,h=4,parent='group'),rect('b',x=5,y=4,w=2,h=3,parent='group')])
        m=self.metric(d,'group',angle=30)
        self.assertAlmostEqual(m['width'],6);self.assertAlmostEqual(m['height'],5)
        for actual,point in zip(m['corners_document'],[[1,2],[7,2],[7,7],[1,7]]):
            for x,y in zip(actual,transform(point,matrix)):self.assertAlmostEqual(x,y,places=11)
        with localcontext() as c:
            c.prec=60;length=24*(Decimal.from_float(matrix[0])**2+Decimal.from_float(matrix[1])**2).sqrt();self.encloses(m['boundary_length'],F(length),1e-4)
        # World transform numbers are exact binary64 coefficients, so area retains their determinant.
        self.encloses(m['signed_area'],F(18)*(F(matrix[0])*F(matrix[3])-F(matrix[1])*F(matrix[2])),1e-6)

    def test_unit_resize_keeps_rotated_anchor_and_source_geometry(self):
        matrix=rotation(30);matrix[4:]=[10,20]
        d=self.document([rect(w=8,h=4,transform=matrix)]);d['resolution_ppi']=144
        before=self.metric(d,angle=30,bounds_only=True);out=self.resize(d,width=8,height=6,unit='pt',angle=30,anchor=dict(x='min',y='max'))
        after=self.metric(out,angle=30,bounds_only=True)
        self.assertAlmostEqual(after['width'],16);self.assertAlmostEqual(after['height'],12)
        for a,b in zip(before['corners_document'][3],after['corners_document'][3]):self.assertAlmostEqual(a,b,places=11)
        self.assertEqual(out['items'][0]['content'],d['items'][0]['content'])

    def test_aspect_resize_through_parent_preserves_center_and_geometry(self):
        d=self.document([dict(id='g',content=dict(type='group'),transform=[2,.25,.5,1.5,10,5]),rect(parent='g',w=8,h=4)])
        before=self.metric(d,bounds_only=True)
        out=self.resize(d,width=2*before['width'],preserve_aspect=True)
        after=self.metric(out,bounds_only=True)
        self.assertAlmostEqual(after['width'],2*before['width']);self.assertAlmostEqual(after['height'],2*before['height'])
        for i in [0,1]:self.assertAlmostEqual(before['bounds'][i]+before['bounds'][i+2],after['bounds'][i]+after['bounds'][i+2])
        self.assertEqual(d['items'][1]['content'],out['items'][1]['content'])

    def test_component_measurement_and_resize_retain_shared_source_and_other_placement(self):
        d=self.invoke(dict(command='document.validate',document=instances.InstanceTests().document()));source=copy.deepcopy(d)
        before=self.metric(d,'left');self.assertEqual(before['bounds'],[3,5,9,11])
        self.encloses(before['signed_area'],40,1e-6);self.encloses(before['boundary_length'],32,1e-4)
        out=self.resize(d,'left',width=12,preserve_aspect=True)
        after=self.metric(out,'left');self.assertEqual(after['width'],12);self.assertEqual(after['height'],12)
        self.encloses(after['signed_area'],160,1e-6);self.encloses(after['boundary_length'],64,1e-4)
        self.assertEqual(self.metric(out,'right'),self.metric(d,'right'))
        self.assertEqual(out['items'][:3],d['items'][:3]);self.assertEqual(d,source)

    def test_raster_frame_measurement_and_layout_preserve_pixels_and_masks(self):
        pixels=[10,20,30,40,50,60,70,80,90,100,110,120,130,140,150,160,170,180,190,200,210,220,230,240]
        item=dict(id='art',content=dict(type='raster',width=3,height=2,rgba_hex=bytes(pixels).hex()),mask=dict(width=3,height=2,gray_hex=bytes([255,128,0,255,255,64]).hex(),linked=False))
        d=self.document([item],kind='raster');m=self.metric(d)
        self.encloses(m['signed_area'],6,1e-6);self.encloses(m['boundary_length'],10,1e-4)
        self.assertEqual(m['components'][0]['boundary'],'pixel_or_fill_frame')
        out=self.resize(d,width=6,height=4)
        out=self.snap(out,targets=[dict(type='point',point=[8,8])],max_distance=20)['document']
        self.assertEqual(out['items'][0]['content'],d['items'][0]['content']);self.assertEqual(out['items'][0]['mask'],d['items'][0]['mask'])
        self.assertEqual(self.metric(out)['bounds'],[5,6,11,10])

    def test_group_dependent_reference_rejected_but_own_frame_guides_remain_fixed(self):
        d=self.document([dict(id='g',content=dict(type='group')),rect(parent='g')])
        self.assertEqual(self.snap(d,targets=[dict(type='item',id='g')],max_distance=10,expected=1)['code'],'INVALID_OPERATION')
        b=boards.BoardCliTests().board('frame',20,20,guides=[dict(id='x',axis='x',position=6)])
        d=self.document([b,rect(parent='frame')])
        out=self.snap(d,targets=[dict(type='guide',frame_id='frame',id='x')],max_distance=10)['document']
        self.assertEqual(out['items'][0],d['items'][0]);self.assertEqual(self.metric(out)['bounds'],[4,0,8,4])

    def test_near_parallel_guides_report_exclusion_and_exact_quadrants_keep_ties(self):
        b=boards.BoardCliTests().board('frame',20,20,guides=[dict(id='x',axis='x',position=4),dict(id='xx',axis='x',position=6)])
        d=self.document([b,rect()]);out=self.snap(d,targets=[dict(type='guide',frame_id='frame',id=id) for id in ['x','xx']],max_distance=8)
        details=out['changes'][0]['details'];self.assertEqual(details['excluded_parallel_guide_pairs'],1);self.assertEqual(details['changes'][0]['target_document'],[4,2])
        for angle in [0,90,180,270,360,-90]:
            m=self.metric(d,angle=angle,bounds_only=True);self.assertEqual(m['width'],4);self.assertEqual(m['height'],4)

    def test_measurement_cancellation_marker_timeout_and_bounds_only_are_explicit(self):
        d=self.document([dict(id='art',content=dict(type='vector',geometry=dict(shape='ellipse',cx=100,cy=100,rx=100,ry=1),fill=[255]*4))])
        with tempfile.TemporaryDirectory() as root:
            marker=Path(root)/'cancel';marker.write_text('stop',encoding='utf8')
            q=dict(command='geometry.measure',document=d,options=dict(ids=['art'],tolerance=1e-6))
            self.assertEqual(self.invoke(dict(q,control=dict(cancel_file=str(marker))),1)['code'],'CANCELLED')
            self.assertEqual(self.invoke(dict(q,control=dict(timeout_ms=1)),1)['code'],'TIMEOUT')
        m=self.metric(d,bounds_only=True);self.assertNotIn('signed_area',m);self.assertNotIn('boundary_length',m);self.assertEqual(m['width'],200)

    def test_snap_point_tolerance_ties_and_no_match_are_explicit(self):
        d=self.document([rect(w=2,h=2)])
        targets=[dict(type='point',point=[2,1]),dict(type='point',point=[0,1])]
        r=self.snap(d,targets=targets,max_distance=1);change=r['changes'][0]['details']['changes'][0]
        self.assertEqual(change['target_index'],0);self.assertEqual(change['delta_document'],[1,0])
        self.assertEqual(r['document']['items'][0]['content'],d['items'][0]['content'])
        r=self.snap(d,targets=targets,max_distance=.999)
        self.assertFalse(r['changes'][0]['details']['changes'][0]['matched']);self.assertEqual(r['document']['items'],d['items'])

    def test_grid_snap_rotated_axes_units_and_lower_halfway_tie(self):
        d=self.document([rect(x=1,y=1,w=2,h=2)]);d['resolution_ppi']=144
        r=self.snap(d,targets=[dict(type='grid',origin=[0,0],spacing=[2,2])],max_distance=2,unit='pt')
        change=r['changes'][0]['details']['changes'][0];self.assertEqual(change['target_document'],[0,0]);self.assertEqual(change['target']['indices'],[0,0])
        d=self.document([rect(x=7,y=2,w=2,h=2)])
        r=self.snap(d,targets=[dict(type='grid',origin=[3,1],spacing=[4,2],angle=90)],max_distance=3)
        self.assertEqual(r['changes'][0]['details']['changes'][0]['target_document'],[9,1])

    def test_oblique_guide_projection_and_intersection_under_frame_transform(self):
        b=boards.BoardCliTests().board('frame',20,20,guides=[dict(id='x',axis='x',position=4),dict(id='y',axis='y',position=6)])
        b['transform']=[1,.5,.25,1,10,5];target=transform([4,6],b['transform'])
        d=self.document([b,rect(x=target[0]-.8,y=target[1]-.7,w=2,h=2)])
        guides=[dict(type='guide',frame_id='frame',id='x'),dict(type='guide',frame_id='frame',id='y')]
        r=self.snap(d,targets=guides,max_distance=1);v=r['changes'][0]['details']['changes'][0]
        self.assertEqual(v['target']['type'],'guide_intersection')
        for a,b in zip(v['target_document'],target):self.assertAlmostEqual(a,b,places=12)
        r=self.snap(d,targets=guides[:1],max_distance=1);v=r['changes'][0]['details']['changes'][0]
        direction=[.25,1];delta=v['delta_document'];self.assertAlmostEqual(sum(a*b for a,b in zip(direction,delta)),0,places=12)
        self.assertAlmostEqual((v['target_document'][0]-target[0])*direction[1]-(v['target_document'][1]-target[1])*direction[0],0,places=12)

    def test_together_and_individual_snap_use_frozen_bounds_and_keep_relative_spacing(self):
        d=self.document([dict(id='g',content=dict(type='group'),transform=[1,.25,.5,1,0,0]),rect('a',x=1,y=1,w=2,h=2,parent='g'),rect('b',x=6,y=1,w=2,h=2,parent='g')])
        targets=[dict(type='point',point=[5,5])]
        r=self.snap(d,['a','b'],targets=targets,max_distance=10)
        shifts=[transform([0,0],i['transform']) for i in r['document']['items'][1:]]
        self.assertAlmostEqual(shifts[0][0],shifts[1][0]);self.assertAlmostEqual(shifts[0][1],shifts[1][1])
        self.assertEqual(len(r['changes'][0]['details']['changes']),1)
        r=self.snap(d,['a','b'],targets=targets,max_distance=10,mode='individual')
        self.assertEqual(len(r['changes'][0]['details']['changes']),2)
        for id in ['a','b']:
            m=self.metric(r['document'],id,bounds_only=True);self.assertAlmostEqual((m['bounds'][0]+m['bounds'][2])/2,5);self.assertAlmostEqual((m['bounds'][1]+m['bounds'][3])/2,5)

    def test_locked_references_are_readable_but_selected_locks_and_moving_references_fail(self):
        d=self.document([rect(),rect('reference',x=8,y=2,w=4,h=4,locked=True)])
        r=self.snap(d,targets=[dict(type='item',id='reference',anchor=dict(x='min',y='max'))],max_distance=10)
        self.assertEqual(r['changes'][0]['details']['changes'][0]['target_document'],[8,6])
        locked=copy.deepcopy(d);locked['items'][0]['locked']=True
        self.assertEqual(self.snap(locked,targets=[dict(type='point',point=[4,4])],max_distance=10,expected=1)['code'],'LOCKED')
        self.assertEqual(self.resize(locked,width=8,expected=1)['code'],'LOCKED');self.metric(locked)
        self.assertEqual(self.snap(d,targets=[dict(type='item',id='art')],max_distance=10,expected=1)['code'],'INVALID_OPERATION')

    def test_invalid_dimensions_targets_and_measurement_settings_fail_without_source_changes(self):
        d=self.document([rect()]);source=copy.deepcopy(d)
        for kw in [{},dict(width=0),dict(width=3,height=4,preserve_aspect=True),dict(width=3,angle=360001),dict(width=3,unit='furlong')]:self.resize(d,expected=1,**kw)
        for kw in [dict(targets=[],max_distance=1),dict(targets=[dict(type='grid',origin=[0,0],spacing=[0,1])],max_distance=1),dict(targets=[dict(type='point',point=[0,0])],max_distance=-1)]:self.snap(d,expected=1,**kw)
        for kw in [dict(tolerance=0),dict(area_tolerance=0),dict(angle=360001)]:self.measure(d,expected=1,**kw)
        self.measure(d,['art','art'],expected=1)
        self.assertEqual(d,source)

    def test_batch_failure_rolls_back_prior_dimension_and_snap_edits(self):
        d=self.document([rect()]);operations=[dict(op='dimensions',id='art',dimensions=dict(width=8)),dict(op='snap',ids=['art'],snap=dict(targets=[dict(type='item',id='missing')],max_distance=2))]
        r=self.edit(d,operations,1);self.assertEqual(r['operation_index'],1);self.assertEqual(self.metric(d)['width'],4)

    def test_mcp_measurement_resize_snap_history_and_timeout(self):
        c=Client();self.addCleanup(c.close);c.initialize();d=self.document([rect()])
        self.assertEqual(c.success('geometry.measure',document=d,options=dict(ids=['art'])),self.measure(d))
        with tempfile.TemporaryDirectory() as root:
            session=dict(session_root=root,session_id='dimensions');c.success('session.create',**session,request_id='create',document=d)
            operations=[dict(op='dimensions',id='art',dimensions=dict(width=8,height=6)),dict(op='snap',ids=['art'],snap=dict(targets=[dict(type='point',point=[10,10])],max_distance=20))]
            action=dict(type='edit',operations=operations);changed=c.success('session.apply',**session,expected_revision=0,request_id='layout',action=action)['document']
            m=self.metric(changed);self.assertEqual(m['width'],8);self.assertEqual(m['height'],6);self.assertEqual(m['bounds'],[6,7,14,13])
            restored=c.success('session.apply',**session,expected_revision=1,request_id='undo',action=dict(type='undo'))['document'];self.assertEqual(restored,dict(d,revision=2))
            redone=c.success('session.apply',**session,expected_revision=2,request_id='redo',action=dict(type='redo'))['document'];self.assertEqual(redone,dict(changed,revision=3));self.assertTrue(c.success('session.verify',**session)['valid'])
        e=c.tool('geometry.measure',document=d,options=dict(ids=['art']),control=dict(timeout_ms=0));self.assertEqual(e['structuredContent']['error']['code'],'TIMEOUT')


if __name__=='__main__':unittest.main()
