"""Curve identities from independent rational blossoms, filled areas and invariants."""
import copy
from fractions import Fraction as F
import unittest
import test_booleans_cli as booleans
from test_booleans_cli import rect, polygons, area


def blossom(control, parameters):
    points=[tuple(map(F,p)) for p in control]
    for t in parameters:
        points=[tuple((1-t)*a+t*b for a,b in zip(p,q)) for p,q in zip(points,points[1:])]
    return points[0]


def curve(control, knots=(F(0),F(1)), reverse=False):
    pieces=[]
    for a,b in zip(knots,knots[1:]):
        pieces.append([blossom(control,[a]*(3-i)+[b]*i) for i in range(4)])
    if reverse:pieces=[p[::-1] for p in pieces[::-1]]
    def encoded(p):
        values=list(map(float,p));assert tuple(map(F,values))==tuple(p)
        return values
    return dict(shape='path',commands=[dict(verb='move',to=encoded(pieces[0][0]))]+[dict(verb='cubic',control1=encoded(p[1]),control2=encoded(p[2]),to=encoded(p[3])) for p in pieces]+[dict(verb='close')])


class CurveBooleanTests(unittest.TestCase):
    invoke=booleans.BooleanTests.invoke
    document=booleans.BooleanTests.document
    combine=booleans.BooleanTests.combine
    check_area=booleans.BooleanTests.check_area

    def test_coincident_subdivisions_and_reversals_have_exactly_empty_difference(self):
        controls=[[[0,0],[4,8],[8,8],[12,0]],[[2,2],[4,15],[12,-3],[18,8]],[[2,2],[2,2],[5,2],[11,11]]]
        for control in controls:
            whole=curve(control)
            baseline=self.combine(self.document([whole,whole]),'union')
            for knots,reverse in [((F(0),F(3,8),F(1)),False),((F(0),F(1,8),F(1,2),F(7,8),F(1)),True)]:
                divided=curve(control,knots,reverse)
                d=self.document([whole,divided]);saved=copy.deepcopy(d)
                for mode in ('difference','xor'):
                    result=self.combine(d,mode)
                    self.assertTrue(result['empty']);self.assertIsNone(result['geometry']);self.check_area(result,0)
                    self.assertEqual(result['curves']['canonical_groups'],1)
                    self.assertEqual(result['curves']['shared_runs'],1)
                    self.assertEqual(result['curves']['removed_parameter_knots'],len(knots)-2)
                for mode in ('union','intersection'):
                    result=self.combine(d,mode)
                    self.assertEqual(result['geometry'],baseline['geometry'])
                    self.assertEqual(result['area_exact'],baseline['area_exact'])
                self.assertEqual(d,saved)

    def test_subdivision_invariance_against_other_geometry_and_operand_order(self):
        control=[[2,2],[4,15],[12,-3],[18,8]]
        whole=curve(control);split=curve(control,(F(0),F(1,4),F(3,8),F(3,4),F(1)))
        clipping=rect(5,1,8,12)
        a=self.document([whole,clipping]);b=self.document([split,clipping])
        for mode in ('union','intersection','difference','xor'):
            before=self.combine(a,mode);after=self.combine(b,mode)
            for key in ('geometry','area_exact','positive_contours','negative_contours','inputs'):
                self.assertEqual(before[key],after[key],key)
            if mode!='difference':
                swapped=self.invoke(dict(command='document.boolean',document=b,ids=['s1','s0'],mode=mode))
                self.assertEqual(after['geometry'],swapped['geometry'])

    def test_exact_coincidence_survives_world_affine_mapping(self):
        control=[[2,2],[4,15],[12,-3],[18,8]]
        m=[-1,F(1,2),F(1,4),1,24,3]
        mapped=[[m[0]*F(x)+m[2]*F(y)+m[4],m[1]*F(x)+m[3]*F(y)+m[5]] for x,y in control]
        source=curve(control,(F(0),F(3,8),F(1)))
        d=self.document([source,curve(mapped,reverse=True)],transforms=[list(map(float,m)),[1,0,0,1,0,0]])
        for mode in ('difference','xor'):
            result=self.combine(d,mode);self.check_area(result,0)
            self.assertEqual(result['curves']['canonical_groups'],1)

    def test_partially_coincident_curves_share_runs_and_converge_to_analytic_area(self):
        control=[[0,0],[4,8],[8,8],[12,0]]
        a=[curve(control,(F(0),F(3,4))),curve(control,(F(1,4),F(1)))]
        b=[curve(control,(F(0),F(1,8),F(1,2),F(3,4))),curve(control,(F(1,4),F(3,8),F(7,8),F(1)))]
        da=self.document(a);db=self.document(b)
        # Integrating y=24t(1-t), x=12t above the closing chords gives these areas.
        exact={'union':F(30),'intersection':F(21,2),'difference':F(39,4),'xor':F(39,2)}
        for mode,expected in exact.items():
            previous=None
            for tolerance in (.25,.0625):
                result=self.combine(da,mode,curve_tolerance=tolerance)
                subdivided=self.combine(db,mode,curve_tolerance=tolerance)
                self.assertEqual(result['geometry'],subdivided['geometry'])
                self.assertEqual(result['area_exact'],subdivided['area_exact'])
                self.assertEqual(result['curves']['canonical_groups'],1)
                self.assertEqual(result['curves']['shared_runs'],3)
                actual=F(result['area_exact']);self.assertGreater(actual,0)
                self.assertEqual(actual,sum(area(p) for p in polygons(result['geometry'])))
                error=abs(actual-expected)
                if previous is not None:self.assertLess(error,previous)
                previous=error
                self.assertLess(error,F(3))

    def test_signed_curve_multiplicities_respect_fill_rules_and_exact_cancellation(self):
        control=[[0,0],[4,8],[8,8],[12,0]]
        whole=curve(control);split=curve(control,(F(0),F(3,8),F(1)));reverse=curve(control,(F(0),F(1,4),F(1)),True)
        box=rect(-1,-1,15,10)
        reference=self.combine(self.document([whole,box]),'intersection')
        for pieces,rule,empty in [([whole,split],'even_odd',True),([whole,split],'nonzero',False),([whole,reverse],'nonzero',True),([whole,split,reverse],'nonzero',False)]:
            compound=dict(shape='path',commands=sum((p['commands'] for p in pieces),[]))
            result=self.combine(self.document([compound,box],[rule,'nonzero']),'intersection')
            self.assertEqual(result['empty'],empty)
            if not empty:self.assertEqual(result['geometry'],reference['geometry'])
        cancelled=dict(shape='path',commands=whole['commands']+reverse['commands'])
        zero=self.combine(self.document([cancelled,box]),'intersection',curve_tolerance=0)
        self.assertTrue(zero['empty']);self.assertEqual(zero['curves']['shared_runs'],0)

    def test_nearby_curves_are_not_merged_and_collinear_retracing_preserves_fill(self):
        control=[[0,0],[4,8],[8,8],[12,0]]
        shifted=[[x,F(y)+F(1,2**30)] for x,y in control]
        result=self.combine(self.document([curve(control),curve(shifted)]),'xor')
        self.assertGreater(F(result['area_exact']),0);self.assertEqual(result['curves']['canonical_groups'],2)
        side=curve([[2,2],[18,2],[-8,2],[10,2]])
        side['commands'][-1:]=[dict(verb='line',to=[10,10]),dict(verb='line',to=[2,10]),dict(verb='close')]
        d=self.document([side,rect(0,0,20,20)])
        for tolerance in (.5,.125):
            output=self.combine(d,'intersection',curve_tolerance=tolerance)
            self.check_area(output,64);self.assertEqual(output['curves']['collinear_cubics'],1)

    def test_source_edge_budget_is_explicit_even_for_mergeable_subdivision(self):
        control=[[0,0],[4,8],[8,8],[12,0]]
        many=curve(control,tuple(F(i,512) for i in range(513)))
        d=self.document([many,rect(0,0,16,16)]);saved=copy.deepcopy(d)
        result=self.combine(d,expected=1)
        self.assertEqual(result['code'],'RESOURCE_LIMIT');self.assertIn('source edges',result['message'])
        self.assertEqual(d,saved)


if __name__=='__main__':unittest.main()
