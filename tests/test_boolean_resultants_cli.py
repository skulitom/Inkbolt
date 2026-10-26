"""Analytic nonlinear contacts, independently inverted filled regions and cusp areas."""
import copy
from decimal import Decimal as D, localcontext
from fractions import Fraction as F
import unittest
import test_booleans_cli as booleans
from test_booleans_cli import rect, polygons, winding, truth
from test_boolean_curves_cli import curve, blossom
from test_boolean_topology_cli import integrated_area

A=[[9,7],[19,10],[32,4],[48,16]]
B=[[4,16],[8,4],[18,10],[34,7]]
Q=[[0,6],[1,6],[3,7],[6,9]]
T=[[0,7],[1,5],[3,7],[6,13]]
MODES=('union','intersection','difference','xor')


class ResultantContactTests(unittest.TestCase):
    invoke=booleans.BooleanTests.invoke
    document=booleans.BooleanTests.document
    combine=booleans.BooleanTests.combine

    def certificate(self,result):
        topology=result['curves']['topology']
        self.assertEqual(topology['certificate'],'exact_simultaneous_curve_to_chord_homotopy')
        report=topology['algebraic_contacts']
        self.assertEqual(report['method'],'exact_resultants_gcd_and_verified_rational_roots')
        self.assertFalse(report['all_algebraic_contacts_located'])
        self.assertEqual(report['root_isolation_maximum_depth'],96)
        return report

    def samples(self,result,mode,quadratic=False):
        output=polygons(result['geometry']);checked=0
        with localcontext() as context:
            context.prec=50
            for xi in range(1,121):
                x=D(xi)/D(20) if quadratic else D(xi)/D(3)
                if quadratic:
                    t=((1+4*x/3).sqrt()-1)/2
                    bounds=[(6+3*t*t,6+x/2),(7-6*t+12*t*t,7+x)]
                    ranges=[(0,6),(0,6)]
                else:
                    s=(36+x-20).sqrt()-6 if 9<x<48 else D(0)
                    u=((144+8*(x-20)).sqrt()-12)/4 if 4<x<34 else D(0)
                    bounds=[(8+s**3,7+(x-9)*D(9)/39),(8-u**3,16-(x-4)*D(9)/30)]
                    ranges=[(9,48),(4,34)]
                for yi in range(9,71):
                    y=D(yi)/4+D(1)/37
                    if min(abs(y-v) for pair in bounds for v in pair)<D('.26'):continue
                    states=[lo<x<hi and min(pair)<y<max(pair) for pair,(lo,hi) in zip(bounds,ranges)]
                    self.assertEqual(sum(winding(p,F(x),F(y)) for p in output)!=0,truth(states,mode),(mode,x,y))
                    checked+=1
        self.assertGreater(checked,3000)

    def test_general_cubic_pair_with_no_shared_linear_coordinate(self):
        self.assertEqual(blossom(A,[F(1,3)]*3),(F(20),F(8)))
        self.assertEqual(blossom(B,[F(2,3)]*3),(F(20),F(8)))
        d=self.document([curve(A),curve(B)]);saved=copy.deepcopy(d)
        for mode in MODES:
            result=self.combine(d,mode)
            self.assertGreaterEqual(self.certificate(result)['parameter_splits'],2)
            self.assertIn((F(20),F(8)),{p for poly in polygons(result['geometry']) for p in poly})
            self.samples(result,mode)
        self.assertEqual(d,saved)

    def test_quadratic_projection_tangency_and_unequal_refinement(self):
        self.assertEqual(blossom(Q,[F(1,3)]*3),blossom(T,[F(1,3)]*3))
        d=self.document([curve(Q),curve(T)])
        for mode in MODES:
            result=self.combine(d,mode)
            self.assertGreaterEqual(self.certificate(result)['contact_points'],1)
            self.assertGreater(result['curves']['topology']['aligned_splits'],0)
            self.samples(result,mode,True)

    def test_exact_subdivision_reverse_operand_order_and_affine_mapping(self):
        transform=[-1,.5,.25,1,60,3]
        for a,b in [(A,B),(Q,T)]:
            base=self.document([curve(a),curve(b)],transforms=[transform,transform])
            divided=self.document([curve(a,(F(0),F(3,8),F(1)),True),curve(b,(F(0),F(1,4),F(3,4),F(1)),True)],transforms=[transform,transform])
            before=self.combine(base,'xor');after=self.combine(divided,'xor')
            self.assertEqual(before['geometry'],after['geometry'])
            self.assertEqual(before['area_exact'],after['area_exact'])
            swapped=self.invoke(dict(command='document.boolean',precision='exact',document=base,ids=['s1','s0'],mode='xor'))
            self.assertEqual(before['geometry'],swapped['geometry'])

    def test_non_dyadic_cusp_and_node_retain_area_and_junctions(self):
        # x=9+27(t-1/3)^2, y=8+27(t-1/3)^3.
        cusp=[[12,7],[6,10],[9,4],[21,16]]
        # x=9+108(t-1/2)^2, y=8+216(t-1/2)((t-1/2)^2-1/36).
        node=[[36,-16],[0,36],[0,-20],[36,32]]
        self.assertEqual(blossom(cusp,[F(1,3)]*3),(F(9),F(8)))
        self.assertEqual(blossom(node,[F(1,3)]*3),blossom(node,[F(2,3)]*3))
        for control,key,point,contours in [(cusp,'stationary_points',(F(9),F(8)),1),(node,'self_contact_points',(F(12),F(8)),2)]:
            d=self.document([curve(control),rect(-10,-40,80,100)])
            total=integrated_area(control)
            inner=integrated_area(control,F(1,3),F(2,3)) if control==node else F(0)
            exact=abs(inner)+abs(total-inner)
            previous=None
            for tolerance in (.5,.125,.03125):
                result=self.combine(d,'intersection',curve_tolerance=tolerance)
                self.assertEqual(self.certificate(result)[key],1)
                self.assertEqual(result['positive_contours'],contours)
                self.assertIn(point,{p for poly in polygons(result['geometry']) for p in poly})
                error=abs(F(result['area_exact'])-exact)
                if previous is not None:self.assertLess(error,previous)
                previous=error

    def test_irrational_node_at_a_corner_retains_its_shared_world_point(self):
        control=[[18,2],[2,22],[2,-6],[18,14]]
        # Both preimages of (12,8) are 1/2 +/- sqrt(1/8).
        d=self.document([curve(control),rect(12,8,5,5)]);saved=copy.deepcopy(d)
        result=self.combine(d,'xor')
        self.assertEqual(result['curves']['topology']['quadratic_contacts']['irrational_parameter_splits'],2)
        self.assertIn((F(12),F(8)),{p for poly in polygons(result['geometry']) for p in poly})
        self.assertEqual(d,saved)


if __name__=='__main__':unittest.main()
