"""Curve identities from independent rational blossoms, filled areas and invariants."""
import copy
from decimal import Decimal, localcontext
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

    def test_editable_clipped_arch_has_original_controls_area_and_coverage(self):
        # x=12t, y=24t(1-t). A cut at x=6 divides its area of 48 equally.
        controls = [[0,0],[4,8],[8,8],[12,0]]
        doc = self.document([curve(controls), rect(6,-2,10,12)])
        for precision in ('exact', 'tolerance', 'auto'):
            for mode, expected_area in [('union',144), ('intersection',24),
                                        ('difference',24), ('xor',120)]:
                with self.subTest(precision=precision, mode=mode):
                    result = self.combine(doc, mode, precision=precision, output='curves')
                    self.assertEqual(F(result['curve_output']['signed_area_exact']), expected_area)
                    self.assertEqual(F(result['curve_output']['source_curve_deviation_squared']), 0)
                    self.assertGreater(result['curve_output']['cubic_segments'], 0)
                    tolerance = F(result['curve_tolerance'])
                    bound = F(result['curve_output']['polygon_deviation_squared'])
                    self.assertLessEqual(bound, tolerance**2)
                    for command in result['geometry']['commands']:
                        if command['verb'] == 'cubic':
                            end = tuple(map(F, command['to']))
                            a, b = start[0]/12, end[0]/12
                            self.assertEqual(blossom(controls,[a,a,b]),tuple(map(F, command['control1'])))
                            self.assertEqual(blossom(controls,[a,b,b]),tuple(map(F, command['control2'])))
                            for i in range(9):
                                u = F(i,8)
                                p = blossom(controls, [a+(b-a)*u]*3)
                                q = [(1-u)*x+u*y for x,y in zip(start,end)]
                                self.assertLessEqual(sum((x-y)**2 for x,y in zip(p,q)), bound)
                        if 'to' in command:
                            start = tuple(map(F, command['to']))

    def test_curved_hole_and_cancelled_coincident_sources(self):
        controls = [[0,0],[4,8],[8,8],[12,0]]
        inner = curve(controls)
        doc = self.document([rect(-2,-2,16,12),inner])
        result = self.combine(doc, 'difference', output='curves')
        self.assertEqual(result['negative_contours'], 1)
        self.assertEqual(F(result['curve_output']['signed_area_exact']), 192-48)
        same = self.document([inner,curve(controls, (F(0),F(3,8),F(1)), reverse=True)])
        for mode in ('xor','difference'):
            empty = self.combine(same,mode,output='curves')
            self.assertIsNone(empty['geometry'])
            self.assertEqual(empty['curve_output']['cubic_segments'],0)
        request = dict(command='document.boolean', document=doc, ids=['s0','s1'], mode='difference')
        default = self.invoke(request)
        self.assertEqual(default, self.invoke(dict(request,output='curves')))
        self.assertEqual(F(default['curve_output']['signed_area_exact']), 192-48)
        polygon = self.invoke(dict(request,output='polygon'))
        self.assertNotEqual(polygon['geometry'], default['geometry'])
        self.assertNotIn('curve_output', polygon)
        for invalid in (None,'unspecified'):
            self.assertEqual(self.invoke(dict(request,output=invalid),1)['code'],'INVALID_REQUEST')
        self.assertEqual(self.invoke(dict(command='capabilities'))['booleans']['output_formats']['default'],'curves')
        operation = self.invoke(dict(command='schema.lookup',name='operation',select='boolean'))['schema']
        self.assertEqual(operation['properties']['output']['default'],'curves')

    def test_snapped_coincident_curves_refuse_ambiguous_handles(self):
        def arch(delta):
            return curve([[0,0],[4,8+delta],[8,8+delta],[12,0]])
        doc = self.document([arch(0),arch(F(1,1024))])
        error = self.combine(doc, precision='tolerance', output='curves', expected=1)
        self.assertEqual(error['code'],'CURVE_TOPOLOGY_UNRESOLVED')
        self.assertNotIn('geometry',error)
        self.assertFalse(self.combine(doc,precision='tolerance',output='polygon')['empty'])
        # A requested curved path can legitimately contain only straight edges.
        lines = self.document([rect(0,0,8,8),rect(4,4,8,8)])
        result = self.combine(lines,'intersection',output='curves')
        self.assertEqual(result['curve_output']['signed_area_exact'],'16')
        self.assertEqual(result['curve_output']['cubic_segments'],0)

    def test_irrational_clip_reflattens_inside_the_declared_band(self):
        # y=3 intersects the arch at x=6 +/- 3*sqrt(2).
        doc = self.document([curve([[0,0],[4,8],[8,8],[12,0]]),rect(0,3,12,6)])
        result = self.combine(doc,'intersection',precision='tolerance',output='curves')
        report = result['curve_output']
        self.assertGreater(report['cubic_segments'],0)
        self.assertGreater(F(report['source_curve_deviation_squared']),0)
        self.assertLessEqual(F(report['source_curve_deviation_squared']),F(1,8)**2)
        vertices = []
        for cmd in result['geometry']['commands']:
            if cmd['verb'] == 'cubic':
                points = [vertices[-1],cmd['control1'],cmd['control2'],cmd['to']]
                vertices.extend(blossom(points,[F(i,16)]*3) for i in range(1,17))
            elif 'to' in cmd:
                vertices.append(tuple(map(F,cmd['to'])))
        # Dense independent coverage check away from either analytic boundary.
        for x in (F(i,4) for i in range(1,48)):
            top = 2*x-x*x/6
            for y in (F(i,4) for i in range(1,28)):
                if min(abs(y-3),abs(y-top)) <= F(1,2):
                    continue
                self.assertEqual(bool(booleans.winding(vertices,x,y)),3 < y < top,(x,y))

    def test_exact_transverse_junctions_match_radical_vertices_and_integrals(self):
        arch = curve([[0,0],[4,8],[8,8],[12,0]])
        opposing = curve([[0,8],[4,0],[8,0],[12,8]])
        with localcontext() as ctx:
            ctx.prec = 80
            for other, y, radius, area in [
                (rect(0,3,12,6),3,3*Decimal(2).sqrt(),12*Decimal(2).sqrt()),
                (opposing,4,2*Decimal(3).sqrt(),32*Decimal(3).sqrt()/3),
            ]:
                doc = self.document([arch,other])
                result = self.combine(doc,'intersection',precision='exact',output='curves')
                self.assertEqual(result['certificate'],'exact')
                proof = result['curve_output']
                self.assertEqual(proof['resolved_transverse_junctions'],2)
                endpoints = {tuple(c['to']) for c in result['geometry']['commands'] if 'to' in c}
                for x in [6-radius,6+radius]:
                    self.assertIn((float(x),y),endpoints)
                measured = F(proof['signed_area_exact'])
                self.assertLess(abs(Decimal(measured.numerator)/Decimal(measured.denominator)-area),Decimal('1e-13'))
                self.assertLess(F(proof['source_curve_deviation_squared']),F(1,10**27))
                swapped = self.invoke(dict(command='document.boolean',document=doc,ids=['s1','s0'],
                    mode='intersection',precision='exact',output='curves'))
                self.assertEqual(result['geometry'],swapped['geometry'])

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
                swapped=self.invoke(dict(command='document.boolean',precision='exact',output='polygon',document=b,ids=['s1','s0'],mode=mode))
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
        ceiling=booleans.capabilities()['limits']['boolean_source_edges']
        many=curve(control,tuple(F(i,ceiling) for i in range(ceiling+1)))
        d=self.document([many,rect(0,0,16,16)]);saved=copy.deepcopy(d)
        result=self.combine(d,expected=1)
        self.assertEqual(result['code'],'RESOURCE_LIMIT');self.assertIn('source edges',result['message'])
        self.assertEqual(d,saved)


if __name__=='__main__':unittest.main()
