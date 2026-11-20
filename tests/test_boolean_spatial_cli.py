"""Independent regions and analytic curves at spatially admitted capacities."""
import copy
from fractions import Fraction as F
import math
import unittest
import test_booleans_cli as booleans
from test_boolean_ellipses_cli import ellipse, inside_output


def boxes_path(boxes):
    commands=[]
    for x,y,w,h in boxes:
        commands.extend(booleans.path([[x,y],[x+w,y],[x+w,y+h],[x,y+h]])['commands'])
    return dict(shape='path',commands=commands)


class SpatialBooleanTests(unittest.TestCase):
    invoke=booleans.BooleanTests.invoke
    document=booleans.BooleanTests.document
    combine=booleans.BooleanTests.combine

    def test_admitted_edge_ceiling_keeps_every_separate_region(self):
        ceiling=booleans.capabilities()['limits']['boolean_source_edges']
        self.assertEqual(ceiling,1024)
        boxes=[(i*4,(i%3)*4,2,2) for i in range(ceiling//4)]
        doc=self.document([boxes_path(boxes[::2]),boxes_path(boxes[1::2])]); saved=copy.deepcopy(doc)
        result=self.combine(doc,curve_tolerance=0)
        expected=sorted(booleans.polygons(boxes_path(boxes)))
        self.assertEqual(booleans.polygons(result['geometry']),expected)
        self.assertEqual(F(result['area_exact']),len(boxes)*4)
        self.assertEqual(result['positive_contours'],len(boxes))
        self.assertEqual(result['negative_contours'],0)
        self.assertEqual(result['rounding_deviation_squared'],'0')
        self.assertLess(result['work_units'],booleans.capabilities()['limits']['boolean_work'])
        reversed_result=self.invoke(dict(command='document.boolean',document=doc,ids=['s1','s0'],mode='union',precision='exact',curve_tolerance=0))
        self.assertEqual(result['geometry'],reversed_result['geometry'])
        extra=copy.deepcopy(doc)
        extra['items'][0]['content']['geometry']['commands'].extend(boxes_path([(0,20,1,1)])['commands'])
        error=self.combine(extra,expected=1)
        self.assertEqual(error['code'],'RESOURCE_LIMIT');self.assertIn('source edges',error['message'])
        self.assertEqual(doc,saved)

    def test_sixteen_ellipses_keep_analytic_interiors_and_declared_precision(self):
        shapes=[ellipse(20+i*40,20,12,8) for i in range(16)]
        doc=self.document(shapes);saved=copy.deepcopy(doc)
        result=self.combine(doc,precision='tolerance')
        self.assertGreater(sum(x['flattened_edges'] for x in result['inputs']),512)
        self.assertEqual(result['positive_contours'],16)
        self.assertEqual(result['negative_contours'],0)
        self.assertLess(abs(result['area']-16*math.pi*12*8),16*math.pi*12*8*.01)
        output=[[tuple(map(float,p)) for p in poly] for poly in booleans.polygons(result['geometry'])]
        for shape,source in zip(shapes,result['inputs']):
            error=sum(math.sqrt(float(F(source[key]))) for key in ('flattening_deviation_squared','snapping_deviation_squared'))
            error+=math.sqrt(float(F(source['primitive_conversion']['world_space_deviation_squared'])))
            for radius in (.5,1.5):
                for i in range(12):
                    theta=i*math.pi/6
                    x=shape['cx']+shape['rx']*radius*math.cos(theta)
                    y=shape['cy']+shape['ry']*radius*math.sin(theta)
                    self.assertGreater(abs(radius-1)*8,error)
                    self.assertEqual(inside_output(output,x,y),radius<1)
        self.assertEqual(doc,saved)

    def test_dense_crossings_still_refuse_the_atomic_edge_budget(self):
        count=48
        vertical=[(i*2,0,1,count*2) for i in range(count)]
        horizontal=[(0,i*2,count*2,1) for i in range(count)]
        doc=self.document([boxes_path(vertical),boxes_path(horizontal)]);saved=copy.deepcopy(doc)
        error=self.combine(doc,'intersection',expected=1)
        self.assertEqual(error['code'],'RESOURCE_LIMIT')
        self.assertIn('atomic edges',error['message'])
        self.assertNotIn('geometry',error)
        self.assertEqual(doc,saved)

    def test_dense_coincidence_still_refuses_the_work_budget(self):
        ceiling=booleans.capabilities()['limits']['boolean_source_edges']
        repeated=boxes_path([(0,0,2,2)]*(ceiling//8))
        doc=self.document([repeated,repeated]);saved=copy.deepcopy(doc)
        error=self.combine(doc,expected=1)
        self.assertEqual(error['code'],'RESOURCE_LIMIT')
        self.assertIn('work budget',error['message'])
        self.assertNotIn('geometry',error)
        self.assertEqual(doc,saved)

    def test_strict_separated_cubics_keep_analytic_vertices_and_area(self):
        shapes=[dict(shape='path',commands=[dict(verb='move',to=[i*40,0]),
            dict(verb='cubic',control1=[i*40+4,8],control2=[i*40+8,8],to=[i*40+12,0]),dict(verb='close')]) for i in range(16)]
        doc=self.document(shapes);saved=copy.deepcopy(doc)
        result=self.combine(doc,precision='exact')
        self.assertEqual(result['certificate'],'exact')
        self.assertEqual(result['positive_contours'],16)
        # Integrate y=2*x-x*x/6 independently. On an interval of width h,
        # the chord loses h^3/36 area and has at most h^2/24 vertical error.
        expected_area=F(0)
        for poly in booleans.polygons(result['geometry']):
            origin=min(x for x,y in poly)
            for x,y in poly:
                x-=origin
                self.assertEqual(y,2*x-x*x/6)
            xs=sorted({x-origin for x,y in poly})
            self.assertEqual((xs[0],xs[-1]),(0,12))
            widths=[b-a for a,b in zip(xs,xs[1:])]
            self.assertTrue(all(h*h/24<=F(1,8) for h in widths))
            expected_area+=48-sum(h**3/36 for h in widths)
        self.assertEqual(F(result['area_exact']),expected_area)
        self.assertEqual(doc,saved)


if __name__=='__main__':unittest.main()
