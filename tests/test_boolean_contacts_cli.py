"""Rational contact locations and independent polynomial region classifications."""
import copy
from fractions import Fraction as F
import unittest
import test_booleans_cli as booleans
from test_booleans_cli import rect, polygons, winding, truth
from test_boolean_curves_cli import curve, blossom

A=[[0,5],[4,5],[8,6],[12,8]]
B=[[0,4],[4,7],[8,2],[12,16]]


class AlgebraicContactTests(unittest.TestCase):
    invoke=booleans.BooleanTests.invoke
    document=booleans.BooleanTests.document
    combine=booleans.BooleanTests.combine

    def samples(self,result,a,b,mode):
        output=polygons(result['geometry']);checked=0
        for xi in range(24):
            x=F(xi,2)+F(1,17);t=x/12
            boundaries=[(blossom(c,[t]*3)[1],(1-t)*F(c[0][1])+t*F(c[3][1])) for c in (a,b)]
            for yi in range(6,36):
                y=F(yi,2)+F(1,19)
                if min(abs(y-v) for pair in boundaries for v in pair)<F(1,4):continue
                expected=truth([min(pair)<y<max(pair) for pair in boundaries],mode)
                self.assertEqual(sum(winding(p,x,y) for p in output)!=0,expected,(mode,x,y))
                checked+=1
        self.assertGreater(checked,400)

    def test_matching_tangent_cubic_crossing_has_exact_contact_and_correct_regions(self):
        # B_y-A_y=(3t-1)^3; all input controls are exact integers.
        d=self.document([curve(A),curve(B)]);saved=copy.deepcopy(d)
        contact=(F(4),F(float(F(16,3))))
        for mode in ('union','intersection','difference','xor'):
            result=self.combine(d,mode)
            report=result['curves']['topology']
            self.assertEqual(report['certificate'],'exact_simultaneous_curve_to_chord_homotopy')
            self.assertGreaterEqual(report['algebraic_contacts']['contact_points'],1)
            self.assertGreaterEqual(report['algebraic_contacts']['parameter_splits'],2)
            self.assertGreater(report['aligned_splits'],0)
            self.assertIn(contact,{p for polygon in polygons(result['geometry']) for p in polygon})
            self.samples(result,A,B,mode)
        self.assertEqual(d,saved)

    def test_even_multiplicity_contact_keeps_the_two_graphs_on_the_same_side(self):
        tangent=[[0,6],[4,4],[8,6],[12,12]]
        for t in (F(1,4),F(1,3),F(1,2)):
            self.assertEqual(blossom(tangent,[t]*3)[1]-blossom(A,[t]*3)[1],(3*t-1)**2)
        d=self.document([curve(A),curve(tangent)])
        for mode in ('union','intersection','difference','xor'):
            result=self.combine(d,mode)
            self.assertGreaterEqual(result['curves']['topology']['algebraic_contacts']['contact_points'],1)
            self.samples(result,A,tangent,mode)

    def test_nonlinear_curve_line_tangency_and_segment_range(self):
        control=[[0,4],[4,2],[9,3],[18,7]]
        self.assertEqual(blossom(control,[F(1,3)]*3),(F(40,9),F(3)))
        d=self.document([curve(control),rect(0,0,20,3)])
        result=self.combine(d,'intersection')
        self.assertTrue(result['empty'])
        self.assertGreaterEqual(result['curves']['topology']['algebraic_contacts']['contact_points'],1)
        combined=self.combine(d,'union')
        self.assertEqual((combined['positive_contours'],combined['negative_contours']),(2,0))
        point=(F(float(F(40,9))),F(3))
        self.assertEqual(sum(p.count(point) for p in polygons(combined['geometry'])),2)
        outside=self.combine(self.document([curve(control),rect(10,0,2,3)]),'intersection')
        self.assertTrue(outside['empty'])
        self.assertEqual(outside['curves']['topology']['algebraic_contacts']['contact_points'],0)

    def test_curve_endpoint_preimage_is_split_at_non_dyadic_parameter(self):
        control=[[0,0],[27,81],[81,0],[108,81]]
        self.assertEqual(blossom(control,[F(1,3)]*3),(F(34),F(39)))
        triangle=booleans.path([[34,39],[40,50],[28,55]])
        d=self.document([curve(control),triangle])
        result=self.combine(d,'xor')
        self.assertGreaterEqual(result['curves']['topology']['algebraic_contacts']['contact_points'],1)
        self.assertIn((F(34),F(39)),{p for polygon in polygons(result['geometry']) for p in polygon})

    def test_contact_is_invariant_under_exact_subdivision_reversal_and_affine_mapping(self):
        transform=[-1,.5,.25,1,24,3]
        plain=self.document([curve(A),curve(B)],transforms=[transform,transform])
        divided=self.document([curve(A,(F(0),F(3,8),F(1)),True),curve(B,(F(0),F(1,4),F(3,4),F(1)),True)],transforms=[transform,transform])
        before=self.combine(plain,'xor');after=self.combine(divided,'xor')
        self.assertEqual(before['geometry'],after['geometry']);self.assertEqual(before['area_exact'],after['area_exact'])
        point=(F(float(F(64,3))),F(float(F(31,3))))
        self.assertIn(point,{p for polygon in polygons(after['geometry']) for p in polygon})

    def test_nearby_curve_is_not_snapped_to_the_old_matching_tangent_contact(self):
        shifted=[[x,F(y)+F(1,4096)] for x,y in B]
        t=F(5,16)
        self.assertEqual(blossom(A,[t]*3),blossom(shifted,[t]*3))
        self.assertNotEqual(blossom(A,[F(1,3)]*3),blossom(shifted,[F(1,3)]*3))
        d=self.document([curve(A),curve(shifted)])
        result=self.combine(d,'union')
        point=blossom(A,[t]*3)
        vertices={p for polygon in polygons(result['geometry']) for p in polygon}
        self.assertLess(min(sum((v-w)**2 for v,w in zip(p,point)) for p in vertices),F(1,32)**2)
        original=self.combine(self.document([curve(A),curve(B)]),'union')
        self.assertNotEqual(result['geometry'],original['geometry'])
        self.samples(result,A,shifted,'union')


if __name__=='__main__':unittest.main()
