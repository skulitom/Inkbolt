"""Independent closed-loop areas, analytic intersections and filled-region topology."""
import copy
from decimal import Decimal, localcontext
from fractions import Fraction as F
import json
import unittest
import test_booleans_cli as booleans
from test_booleans_cli import rect, polygons, winding, truth, area
from test_boolean_curves_cli import curve, blossom


def closed_loop(x,y,size):
    return curve([[F(x),F(y)],[F(x)+size,F(y)+size],[F(x)-size,F(y)+size],[F(x),F(y)]])


def integrated_area(control,a=F(0),b=F(1),close=True):
    # Direct power-basis integration of x dy - y dx, independent of the engine.
    x,y=[[v[0],3*(v[1]-v[0]),3*(v[0]-2*v[1]+v[2]),-v[0]+3*v[1]-3*v[2]+v[3]] for v in zip(*[list(map(F,p)) for p in control])]
    result=sum((x[i]*j*y[j]-y[i]*j*x[j])*(b**(i+j)-a**(i+j))/F(2*(i+j)) for i in range(4) for j in range(1,4))
    if close:
        p=blossom(control,[b]*3);q=blossom(control,[a]*3)
        result+=(p[0]*q[1]-p[1]*q[0])/2
    return result


class CurveTopologyTests(unittest.TestCase):
    invoke=booleans.BooleanTests.invoke
    document=booleans.BooleanTests.document
    combine=booleans.BooleanTests.combine
    check_area=booleans.BooleanTests.check_area

    def certificate(self,result):
        report=result['curves']['topology']
        self.assertEqual(report['certificate'],'exact_simultaneous_curve_to_chord_homotopy')
        self.assertLessEqual(report['crossings_per_curved_arc_maximum'],1)
        return report

    def test_tiny_closed_loops_survive_loose_tolerance_and_preserve_originals(self):
        for size in (F(1,32),F(1,4096),F(1,2**30)):
            g=closed_loop(10,10,size);d=self.document([g,rect(0,0,32,24)]);saved=copy.deepcopy(d)
            for tolerance in (.125,64):
                result=self.combine(d,'intersection',curve_tolerance=tolerance)
                report=self.certificate(result)
                self.assertEqual((result['positive_contours'],result['negative_contours']),(1,0))
                self.assertEqual(report['curve_arcs'],4)
                self.check_area(result,F(27,128)*size**2)
                control=[[10,10],[10+size,10+size],[10-size,10+size],[10,10]]
                self.assertEqual(integrated_area(control),F(3,10)*size**2)
                expected={blossom(control,[F(i,4)]*3) for i in range(4)}
                self.assertEqual(set(polygons(result['geometry'])[0]),expected)
                self.assertFalse(result['empty'])
            self.assertEqual(d,saved)
            snapshot=self.invoke(dict(command='document.export',document=d,format='snapshot'))
            self.assertEqual(self.combine(json.loads(snapshot['data']),'intersection'),self.combine(d,'intersection'))

    def test_disconnected_curved_holes_remain_distinct_below_tolerance(self):
        size=F(1,32)
        one=closed_loop(6,6,size);two=closed_loop(14,12,size)
        holes=dict(shape='path',commands=one['commands']+two['commands'])
        d=self.document([rect(0,0,20,20),holes])
        result=self.combine(d,'difference',curve_tolerance=64)
        self.certificate(result)
        self.assertEqual((result['positive_contours'],result['negative_contours']),(1,2))
        self.check_area(result,F(400)-2*F(27,128)*size**2)
        output=polygons(result['geometry'])
        for x,y,inside in [(F(1),F(1),True),(F(6),F(6)+size/2,False),(F(14),F(12)+size/2,False)]:
            self.assertEqual(sum(winding(p,x,y) for p in output)!=0,inside)
        islands=self.combine(self.document([holes,rect(0,0,20,20)]),'intersection',curve_tolerance=64)
        self.assertEqual((islands['positive_contours'],islands['negative_contours']),(2,0))

    def test_nodal_self_intersection_keeps_both_lobes_and_shared_vertex(self):
        control=[[20,F(7,2)],[4,F(29,2)],[4,F(3,2)],[20,F(25,2)]]
        node=blossom(control,[F(1,4)]*3)
        self.assertEqual(node,blossom(control,[F(3,4)]*3));self.assertEqual(node,(F(11),F(8)))
        inner=integrated_area(control,F(1,4),F(3,4));total=integrated_area(control)
        true_filled_area=abs(inner)+abs(total-inner)
        d=self.document([curve(control),rect(0,0,32,24)])
        previous=None
        for tolerance in (1,.125,.03125):
            result=self.combine(d,'intersection',curve_tolerance=tolerance);self.certificate(result)
            self.assertEqual((result['positive_contours'],result['negative_contours']),(2,0))
            self.assertEqual(sum(p.count(node) for p in polygons(result['geometry'])),2)
            error=abs(F(result['area_exact'])-true_filled_area)
            if previous is not None:self.assertLess(error,previous)
            previous=error

    def test_transverse_curve_line_intersections_converge_to_analytic_area(self):
        d=self.document([curve([[0,0],[4,8],[8,8],[12,0]]),rect(0,3,12,10)])
        with localcontext() as context:
            context.prec=60;exact=Decimal(12)*Decimal(2).sqrt();previous=None
            for tolerance in (.5,.125,.03125):
                result=self.combine(d,'intersection',curve_tolerance=tolerance)
                certificate=self.certificate(result)
                self.assertEqual(certificate['transverse_crossings'],2)
                self.assertEqual((result['positive_contours'],result['negative_contours']),(1,0))
                q=F(result['area_exact']);actual=Decimal(q.numerator)/Decimal(q.denominator)
                error=exact-actual;self.assertGreater(error,0)
                if previous is not None:self.assertLess(error,previous)
                previous=error
                count=result['curves']['topology']['curve_arcs']
                samples=[(F(12*i,count),24*F(i,count)*(1-F(i,count))) for i in range(count+1)]
                clipped=[p for p in samples if p[1]>=3]
                for a,b in zip(samples,samples[1:]):
                    if (a[1]<3<b[1]) or (b[1]<3<a[1]):
                        clipped.append((a[0]+(b[0]-a[0])*(3-a[1])/(b[1]-a[1]),F(3)))
                clipped=sorted(set(clipped))
                self.assertEqual(q,abs(area(clipped)))
                rounded={tuple(F(float(v)) for v in p) for p in clipped}
                self.assertEqual(rounded,set(polygons(result['geometry'])[0]))
                maximum=max(sum((F(float(v))-v)**2 for v in p) for p in clipped)
                self.assertEqual(F(result['rounding_deviation_squared']),maximum)

    def test_curve_curve_crossings_match_independent_analytic_region_samples(self):
        d=self.document([curve([[0,0],[4,8],[8,8],[12,0]]),curve([[0,5],[4,-3],[8,-3],[12,5]])])
        for mode in ('union','intersection','difference','xor'):
            result=self.combine(d,mode,curve_tolerance=.125);certificate=self.certificate(result)
            self.assertEqual(certificate['transverse_crossings'],6)
            output=polygons(result['geometry']);checked=0
            for xi in range(49):
                x=F(xi,4)+F(1,13)
                if not 0<x<12:continue
                top=x*(12-x)/6;bottom=5-top
                for yi in range(-6,30):
                    y=F(yi,4)+F(1,17)
                    if min(abs(y-v) for v in [F(0),F(5),top,bottom])<F(1,4):continue
                    expected=truth([0<y<top,bottom<y<5],mode)
                    self.assertEqual(sum(winding(p,x,y) for p in output)!=0,expected,(mode,x,y))
                    checked+=1
            self.assertGreater(checked,800)

    def test_tangent_line_and_opposite_curves_do_not_create_filled_slivers(self):
        arch=curve([[0,0],[4,8],[8,8],[12,0]])
        for other in [rect(0,6,12,10),curve([[0,12],[4,4],[8,4],[12,12]])]:
            d=self.document([arch,other])
            intersection=self.combine(d,'intersection');self.certificate(intersection)
            self.assertTrue(intersection['empty']);self.check_area(intersection,0)
            union=self.combine(d,'union');self.certificate(union)
            self.assertEqual((union['positive_contours'],union['negative_contours']),(2,0))
            self.assertEqual(sum(p.count((F(6),F(6))) for p in polygons(union['geometry'])),2)

    def test_close_translated_curves_get_exact_shared_coordinate_certificate(self):
        control=[[0,0],[4,8],[8,8],[12,0]]
        shifted=[[x,F(y)+F(1,2**30)] for x,y in control]
        d=self.document([curve(control),curve(shifted)])
        result=self.combine(d,'xor');report=self.certificate(result)
        self.assertGreater(report['paired_coordinate_pairs'],0)
        self.assertGreater(F(result['area_exact']),0)
        self.assertEqual(result['curves']['canonical_groups'],2)

    def test_dense_curved_arrangement_limit_returns_no_partial_geometry(self):
        commands=[]
        for i in range(20):
            for points in [((i,0),(i+.5,0),(i+.5,20),(i,20)),((0,i),(20,i),(20,i+.5),(0,i+.5))]:
                commands.extend(booleans.path(points)['commands'])
        grid=dict(shape='path',commands=commands)
        d=self.document([grid,closed_loop(25,5,F(1))]);saved=copy.deepcopy(d)
        result=self.combine(d,'union',expected=1)
        self.assertEqual(result['code'],'RESOURCE_LIMIT');self.assertNotIn('geometry',result)
        self.assertEqual(d,saved)


if __name__=='__main__':unittest.main()
