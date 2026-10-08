"""Independent polynomial certificates, occupancy/topology and recovery checks."""
from fractions import Fraction as F
import copy
import math
import tempfile
import unittest
import test_editing_cli as editing
from test_mcp import Client


def powers(c):
    return [[p[0],3*(p[1]-p[0]),3*(p[0]-2*p[1]+p[2]),-p[0]+3*p[1]-3*p[2]+p[3]] for p in zip(*c)]


def restrict_power(c,a,b):
    coefficients=powers(c);d=b-a;out=[]
    for p in coefficients:
        q=[sum(p[k]*math.comb(k,j)*a**(k-j)*d**j for k in range(j,4)) for j in range(4)]
        out.append([q[0],q[0]+q[1]/3,q[0]+2*q[1]/3+q[2]/3,sum(q)])
    return list(zip(*out))


def edges(commands):
    contours=[];current=None;start=None
    for c in commands:
        if c['verb']=='move':
            current=[];contours.append(current);start=tuple(map(F,c['to']))
        elif c['verb'] in ('line','cubic'):
            end=tuple(map(F,c['to']))
            if c['verb']=='line':controls=[tuple((2*a+b)/3 for a,b in zip(start,end)),tuple((a+2*b)/3 for a,b in zip(start,end))]
            else:controls=[tuple(map(F,c[k])) for k in ('control1','control2')]
            current.append([start,*controls,end]);start=end
    return contours


def segments(c,count):
    c=[tuple(map(F,p)) for p in c]
    result=[dict(verb='move',to=list(map(float,c[0])))]
    for i in range(count):
        q=restrict_power(c,F(i,count),F(i+1,count))
        result.append(dict(verb='cubic',control1=list(map(float,q[1])),control2=list(map(float,q[2])),to=list(map(float,q[3]))))
    return result


def lines(points,closed=False):
    return [dict(verb='move',to=points[0])]+[dict(verb='line',to=p) for p in points[1:]]+([dict(verb='close')] if closed else [])


def check_certificates(test,before,after,report):
    original=edges(before);result=edges(after);matrix=list(map(F,report['metric_matrix']));maximum=F(0)
    for reduction in report['reductions']:
        ci=reduction['contour_index'];indices=reduction['source_edge_indices'];q=result[ci][reduction['output_edge_index']]
        times=list(map(F,reduction['source_parameter_boundaries']));test.assertEqual(len(times),len(indices)+1)
        test.assertEqual((times[0],times[-1]),(0,1));test.assertTrue(all(a<b for a,b in zip(times,times[1:])))
        test.assertEqual(q[0],original[ci][indices[0]][0]);test.assertEqual(q[-1],original[ci][indices[-1]][-1])
        local_max=F(0)
        for k,index in enumerate(indices):
            restricted=restrict_power(q,times[k],times[k+1]);p=original[ci][index]
            for a,b in zip(p,restricted):
                dx,dy=[a[v]-b[v] for v in range(2)]
                world=(matrix[0]*dx+matrix[2]*dy,matrix[1]*dx+matrix[3]*dy)
                local_max=max(local_max,sum(v*v for v in world))
            # Dense paired samples check the actual deviation independently of the hull bound.
            for step in range(33):
                t=F(step,32);a=[sum(v*t**j for j,v in enumerate(axis)) for axis in powers(p)];b=[sum(v*t**j for j,v in enumerate(axis)) for axis in powers(restricted)]
                dx,dy=[a[v]-b[v] for v in range(2)]
                value=(matrix[0]*dx+matrix[2]*dy)**2+(matrix[1]*dx+matrix[3]*dy)**2
                test.assertLessEqual(value,local_max)
        test.assertEqual(local_max,F(reduction['deviation_squared']))
        maximum=max(maximum,local_max)
    test.assertEqual(maximum,F(report['maximum_deviation_squared']))
    test.assertLessEqual(maximum,F(report['tolerance'])**2)
    test.assertLessEqual(maximum,F(report['deviation_bound'])**2)


class SimplifyTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke

    def doc(self,commands,fill=None,**props):
        d=self.invoke(dict(command='document.create',id='simplify-fixture',kind='vector',width=64,height=48))
        item=dict(id='path',content=dict(type='vector',geometry=dict(shape='path',commands=commands),fill=fill,stroke=dict(color=[30,90,210,255],width=1)),**props)
        return self.invoke(dict(command='document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=item)]))['document']

    def commands(self,d):return next(i for i in d['items'] if i['id']=='path')['content']['geometry']['commands']

    def simplify(self,d,tolerance=0.05,expected=0,**kw):
        result=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='path',id='path',action=dict(type='simplify',tolerance=tolerance,**kw))]),expected)
        if expected:return result
        report=result['changes'][0]['details'];after=result['document']
        check_certificates(self,self.commands(d),self.commands(after),report)
        return after,report

    def test_exact_collinear_reduction_unequal_lengths_zero_tolerance(self):
        d=self.doc(lines([[2,4],[3,4],[6,4],[14,4],[18,4],[34,4]]))
        result,report=self.simplify(d,tolerance=0)
        self.assertEqual(self.commands(result),lines([[2,4],[34,4]]))
        self.assertEqual(report['maximum_deviation_squared'],'0');self.assertEqual(report['removed_edges'],4)
        again,no_change=self.simplify(result,tolerance=0)
        self.assertEqual(self.commands(again),self.commands(result));self.assertFalse(no_change['changed'])

    def test_subdivided_cubics_reduce_with_certified_deviation_and_persist(self):
        commands=segments([[2,28],[10,2],[36,2],[46,28]],8)
        d=self.doc(commands);original=copy.deepcopy(d)
        after,report=self.simplify(d,tolerance=1e-10,max_span=8)
        self.assertEqual((report['input_edges'],report['output_edges']),(8,1))
        self.assertEqual(self.commands(after)[1]['verb'],'cubic')
        self.assertEqual(d,original)
        snapshot=self.invoke(dict(command='document.export',document=after,format='snapshot'))
        import json
        self.assertEqual(self.invoke(dict(command='document.validate',document=json.loads(snapshot['data']))),after)
        from test_paths_cli import svg_commands, NS
        import xml.etree.ElementTree as ET
        svg=ET.fromstring(self.invoke(dict(command='document.export',document=after,format='svg'))['data'])
        self.assertEqual(svg_commands(svg.find(NS+'g/'+NS+'path')),self.commands(after))

    def test_local_and_world_metric_handle_nested_shear_reflection_and_scale(self):
        commands=segments([[2,28],[10,2],[36,2],[46,28]],4)
        d=self.doc(commands,transform=[2,0.3,0.5,1,0,0])
        d=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='group',ids=['path'],new_id='group'),dict(op='transform',id='group',matrix=[-1,0.2,0,2,60,0])]))['document']
        for space in ('local','world'):
            after,report=self.simplify(d,tolerance=.001,space=space)
            self.assertLess(report['output_edges'],report['input_edges'])
            if space=='world':
                item=self.invoke(dict(command='document.select',document=d,ids=['path']))['items'][0]
                self.assertEqual(report['metric_matrix'],item['world_transform'])
            self.assertEqual(after['items'][0]['transform'],d['items'][0]['transform'])

    def test_compound_holes_orientation_closure_and_selected_contours(self):
        outside=lines([[2,2],[8,2.01],[14,2],[20,2.01],[28,2],[38,2],[38,38],[2,38]],True)
        hole=lines([[12,12],[12,18],[12,26],[26,26],[26,12],[18,12]],True)
        d=self.doc(outside+hole,fill=[30,140,210,255])
        after,report=self.simplify(d,tolerance=.05,max_span=8,contours=[0])
        self.assertGreater(report['removed_edges'],0)
        new=self.commands(after);start=next(i for i,c in enumerate(new[1:],1) if c['verb']=='move')
        self.assertEqual(new[start:],hole);self.assertEqual(sum(c['verb']=='close' for c in new),2)
        def polygons(cmd):
            return [[tuple(map(float,c[0])) for c in contour]+[tuple(map(float,contour[-1][-1]))] for contour in edges(cmd)]
        def winding(poly,x,y):
            result=0
            for a,b in zip(poly,poly[1:]+poly[:1]):
                cross=(b[0]-a[0])*(y-a[1])-(b[1]-a[1])*(x-a[0])
                if a[1]<=y<b[1] and cross>0:result+=1
                if b[1]<=y<a[1] and cross<0:result-=1
            return result
        for y in range(48):
            for x in range(64):
                a=sum(winding(p,x+.5,y+.5) for p in polygons(outside+hole));b=sum(winding(p,x+.5,y+.5) for p in polygons(new))
                self.assertEqual(a,b,(x,y))
        # Solid occupancy has one hole in both independently decoded previews.
        for doc in (d,after):
            import base64
            pixels=editing.png_pixels(base64.b64decode(self.invoke(dict(command='document.export',document=doc,format='png'))['data']))[2]
            for x,y,alpha in [(5,10,255),(20,20,0),(45,20,0)]:self.assertEqual(pixels[(y*64+x)*4+3],alpha)

    def test_crossings_loops_and_nearby_contours_are_retained_without_false_certificate(self):
        # A flattening candidate would move a crossing through a separate vertical contour.
        first=lines([[1,4],[5,4.2],[9,4]])
        second=lines([[5,3],[5,5]])
        d=self.doc(first+second);after,report=self.simplify(d,tolerance=2,contours=[0])
        self.assertEqual(self.commands(after),self.commands(d));self.assertGreater(report['retained_candidates']['topology'],0)
        # A loop violates strict directional monotonicity and must retain its interior topology.
        loop=[dict(verb='move',to=[10,10]),dict(verb='cubic',control1=[30,40],control2=[-10,40],to=[12,10])]
        d=self.doc(loop);after,report=self.simplify(d,tolerance=100)
        self.assertEqual(self.commands(after),loop);self.assertGreater(report['retained_candidates']['monotonicity'],0)
        # Extremely small but exactly represented offsets still cannot be crossed.
        tiny=lines([[1,0],[2,1e-200],[3,0]])+lines([[2,-1e-200],[2,2e-200]])
        d=self.doc(tiny);after,report=self.simplify(d,tolerance=1,contours=[0])
        self.assertEqual(self.commands(after),tiny);self.assertGreater(report['retained_candidates']['topology'],0)

    def test_nonuniform_polyline_tolerance_and_straight_cubic_control_reduction(self):
        commands=lines([[2,10],[3,10.04],[10,9.96],[22,10.02],[40,10]])
        d=self.doc(commands);after,report=self.simplify(d,tolerance=.1)
        self.assertEqual(report['output_edges'],1);self.assertEqual(self.commands(after)[1]['verb'],'line')
        self.assertGreater(report['deviation_bound'],0)
        curved=segments([[2,10],[14,10.001],[26,9.999],[38,10]],1)
        d=self.doc(curved);after,report=self.simplify(d,tolerance=.002)
        self.assertEqual(report['removed_edges'],0);self.assertTrue(report['changed']);self.assertEqual(self.commands(after)[1]['verb'],'line')

    def test_invalid_parameters_locks_and_certificate_work_fail_atomically(self):
        d=self.doc(lines([[1,1],[2,1],[3,1]]));before=copy.deepcopy(d)
        for kw in [dict(tolerance=-1),dict(tolerance=32769),dict(max_span=1),dict(max_span=33),dict(contours=[0,0]),dict(contours=[1])]:self.simplify(d,expected=1,**kw)
        locked=self.doc(self.commands(d),locked=True)
        self.assertEqual(self.simplify(locked,expected=1)['code'],'LOCKED')
        large=self.doc(lines([[i/2,1] for i in range(2048)]))
        self.assertEqual(self.simplify(large,expected=1,max_span=2)['code'],'RESOURCE_LIMIT')
        self.assertEqual(d,before)

    def test_mcp_sessions_preserve_certificate_retry_and_undo_after_reopen(self):
        d=self.doc(segments([[2,28],[10,2],[36,2],[46,28]],8))
        with tempfile.TemporaryDirectory() as root:
            args=dict(session_root=root,session_id='simplify-session');c=Client()
            try:
                c.initialize();c.success('session.create',**args,request_id='create',document=d)
                action=dict(type='edit',operations=[dict(op='path',id='path',action=dict(type='simplify',tolerance=.001))])
                result=c.success('session.apply',**args,expected_revision=0,request_id='simplify',action=action)
                report=result['receipt']['changes'][0]['details'];after=result['document'];check_certificates(self,self.commands(d),self.commands(after),report)
                retry=c.success('session.apply',**args,expected_revision=0,request_id='simplify',action=action)
                self.assertEqual(retry['receipt']['changes'],result['receipt']['changes']);self.assertEqual(retry['document'],after)
            finally:c.close()
            c=Client()
            try:
                c.initialize();self.assertEqual(c.success('session.read',**args)['document'],after)
                undo=c.success('session.apply',**args,expected_revision=1,request_id='undo',action=dict(type='undo'))['document']
                self.assertEqual(self.commands(undo),self.commands(d));c.success('session.verify',**args)
            finally:c.close()

    def test_fill_closure_cannot_collapse_a_small_enclosed_region(self):
        commands=lines([[2,4],[5,4.2],[9,4]])
        outlined=self.doc(commands);reduced,report=self.simplify(outlined,tolerance=2)
        self.assertEqual(report['output_edges'],1)
        for closed in (False,True):
            source=commands+([dict(verb='close')] if closed else [])
            filled=self.doc(source,fill=[40,90,120,255]);after,report=self.simplify(filled,tolerance=2)
            self.assertEqual(self.commands(after),source);self.assertGreater(report['retained_candidates']['topology'],0)

    def test_generated_monotone_curves_validate_exact_bounds_for_both_metrics(self):
        import random
        rng=random.Random(20261004)
        for _ in range(8):
            control=[[2,20],[rng.randrange(4,22),rng.randrange(2,44)],[rng.randrange(32,54),rng.randrange(2,44)],[60,20]]
            d=self.doc(segments(control,4),transform=[1.2,.3,-.2,.8,-2,3])
            after,report=self.simplify(d,tolerance=1e-9,space='world')
            self.assertEqual(report['output_edges'],1)


if __name__=='__main__':unittest.main()
