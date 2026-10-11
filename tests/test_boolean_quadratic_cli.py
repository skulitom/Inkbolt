"""Independent radical lobe areas and inverse-coordinate filled-region oracles."""
import copy
from decimal import Decimal as D, localcontext
from fractions import Fraction as F
import unittest
import test_booleans_cli as booleans
from test_booleans_cli import rect,polygons,winding,truth
from test_boolean_curves_cli import curve

NODE=[[18,2],[2,22],[2,-6],[18,14]]
A=[[24,-4],[-8,36],[-8,-20],[24,20]]
B=[[27,-7],[-5,35],[-5,-19],[27,23]]
MODES=('union','intersection','difference','xor')

def decimal(v):return D(v.numerator)/D(v.denominator)

def branches(x,kind):
    if kind=='node':
        if not 6<x<18:return None
        u=((x-6)/48).sqrt();half=abs(96*u*(u*u-D(1)/8))
    else:
        a=D(1)/8 if kind=='a' else D(3)/32
        if not 12-96*a<x<12+96*(D(1)/4-a):return None
        half=abs(2*(x-12)*(a+(x-12)/96).sqrt())
    return 8-half,8+half


class QuadraticContactTests(unittest.TestCase):
    invoke=booleans.BooleanTests.invoke
    document=booleans.BooleanTests.document
    combine=booleans.BooleanTests.combine

    def report(self,result):
        topology=result['curves']['topology']
        self.assertEqual(topology['certificate'],'exact_simultaneous_curve_to_chord_homotopy')
        self.assertLessEqual(topology['crossings_per_curved_arc_maximum'],1)
        report=topology['quadratic_contacts']
        self.assertEqual(report['method'],'exact_quadratic_parameters_with_rational_junctions')
        self.assertFalse(report['all_algebraic_contacts_located'])
        return report

    def samples(self,result,mode,two_fields=False):
        output=polygons(result['geometry']);checked=0
        with localcontext() as context:
            context.prec=60
            xs=[F(i)+F(1,37) for i in range(-1,29)] if two_fields else [F(6)+F(i,4)+F(1,37) for i in range(50)]
            ys=[F(i)+F(1,41) for i in range(-8,25)] if two_fields else [F(i,2)+F(1,41) for i in range(0,33)]
            for x in xs:
                xd=decimal(x)
                aa=branches(xd,'a' if two_fields else 'node')
                bb=branches(xd,'b') if two_fields else ((D(8),D(13)) if 12<xd<17 else None)
                boundaries=[v for pair in (aa,bb) if pair for v in pair]
                for y in ys:
                    yd=decimal(y)
                    if boundaries and min(abs(yd-v) for v in boundaries)<D('.26'):continue
                    expected=truth([pair is not None and pair[0]<yd<pair[1] for pair in (aa,bb)],mode)
                    self.assertEqual(sum(winding(p,x,y) for p in output)!=0,expected,(mode,x,y,two_fields))
                    checked+=1
        self.assertGreater(checked,600)

    def test_irrational_node_and_corner_all_four_operations(self):
        d=self.document([curve(NODE),rect(12,8,5,5)]);saved=copy.deepcopy(d)
        for mode in MODES:
            result=self.combine(d,mode);report=self.report(result)
            self.assertEqual(report['contact_points'],1)
            self.assertEqual(report['irrational_parameter_splits'],2)
            self.assertIn((F(12),F(8)),{p for poly in polygons(result['geometry']) for p in poly})
            self.samples(result,mode)
        self.assertEqual(d,saved)

    def test_two_different_quadratic_fields_share_one_exact_node(self):
        d=self.document([curve(A),curve(B)])
        for mode in MODES:
            result=self.combine(d,mode);report=self.report(result)
            self.assertEqual(report['contact_points'],1)
            self.assertEqual(report['irrational_parameter_splits'],4)
            self.assertIn((F(12),F(8)),{p for poly in polygons(result['geometry']) for p in poly})
            self.samples(result,mode,True)

    def test_analytic_lobe_area_converges_and_both_contours_keep_the_node(self):
        d=self.document([curve(NODE),rect(0,-10,32,32)])
        with localcontext() as context:
            context.prec=80
            a=D(1)/8;r=a.sqrt();end=D(1)/2
            # Integrate 18432*u^2*abs(u^2-a) from 0 to 1/2.
            primitive=lambda u:u**5/5-a*u**3/3
            exact=18432*(primitive(end)-2*primitive(r));errors=[]
            for tolerance in (.5,.125,.03125):
                result=self.combine(d,'intersection',curve_tolerance=tolerance);self.report(result)
                self.assertEqual((result['positive_contours'],result['negative_contours']),(2,0))
                self.assertEqual(sum(poly.count((F(12),F(8))) for poly in polygons(result['geometry'])),2)
                errors.append(abs(decimal(F(result['area_exact']))-exact))
            self.assertLess(errors[-1],errors[0]);self.assertLess(errors[-1],D('.5'))

    def test_exact_subdivision_reversal_affine_placement_and_operand_order(self):
        matrix=[-1,.5,.25,1,32,3]
        base=self.document([curve(NODE),rect(12,8,5,5)],transforms=[matrix,matrix])
        split=self.document([curve(NODE,(F(0),F(1,4),F(5,8),F(1)),True),rect(12,8,5,5)],transforms=[matrix,matrix])
        before=self.combine(base,'xor');after=self.combine(split,'xor')
        self.assertEqual(before['geometry'],after['geometry']);self.assertEqual(before['area_exact'],after['area_exact'])
        self.assertIn((F(22),F(17)),{p for poly in polygons(after['geometry']) for p in poly})
        swapped=self.invoke(dict(command='document.boolean',document=base,ids=['s1','s0'],mode='xor'))
        self.assertEqual(before['geometry'],swapped['geometry'])

    def test_tiny_irrational_node_keeps_two_lobes_at_loose_tolerance(self):
        for scale in (F(1,4096),F(1,2**30)):
            control=[[10+(F(x)-12)*scale,10+(F(y)-8)*scale] for x,y in NODE]
            d=self.document([curve(control),rect(0,0,24,24)])
            result=self.combine(d,'intersection',curve_tolerance=64);self.report(result)
            self.assertEqual((result['positive_contours'],result['negative_contours']),(2,0))
            self.assertEqual(sum(poly.count((F(10),F(10))) for poly in polygons(result['geometry'])),2)
            self.assertGreater(F(result['area_exact']),0)

    def test_single_branch_without_a_matching_contact_stays_rational(self):
        d=self.document([curve(NODE,(F(0),F(1,4))),rect(25,0,4,4)])
        result=self.combine(d);report=self.report(result)
        self.assertEqual(report['contact_points'],0)
        self.assertEqual(report['initial_algebraic_arcs'],0)

    def test_general_irrational_world_tangencies_still_fail_explicitly(self):
        # A=(s,s^2), B=(u+h,u^2+2uh), h=u^2-1/8, scaled by 12.
        # B_y-A_y(B_x)=-h^2. The two contacts have irrational x coordinates.
        a=[[10,11],[14,7],[18,7],[22,11]]
        b=[[11.5,9.5],[11.5,10.5],[15.5,3.5],[23.5,12.5]]
        d=self.document([curve(a),curve(b)]);saved=copy.deepcopy(d)
        error=self.combine(d,'union',expected=1)
        self.assertIn(error['code'],('CURVE_TOPOLOGY_UNRESOLVED','RESOURCE_LIMIT'))
        self.assertNotIn('geometry',error);self.assertEqual(d,saved)


if __name__=='__main__':unittest.main()
