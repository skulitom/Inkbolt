"""Analytic ellipse area and membership, separate from the engine's cubic model."""
import copy
from fractions import Fraction as F
import math
import unittest
import test_booleans_cli as booleans


MODES = ('union','intersection','difference','xor')
def ellipse(x,y,rx,ry=None):
    return dict(shape='ellipse',cx=x,cy=y,rx=rx,ry=rx if ry is None else ry)

def occupied(g,x,y):
    if g['shape']=='rect':return booleans.contains(g,x,y)
    return ((x-g['cx'])/g['rx'])**2+((y-g['cy'])/g['ry'])**2 < 1

def boundary_distance_lower(g,x,y):
    if g['shape']=='rect':
        return min(abs(x-g['x']),abs(x-g['x']-g['width']),abs(y-g['y']),abs(y-g['y']-g['height']))
    # The minimum singular value of the ellipse map times unit-circle distance.
    radius=math.hypot((x-g['cx'])/g['rx'],(y-g['cy'])/g['ry'])
    return abs(radius-1)*min(g['rx'],g['ry'])

def inside_output(polygons,x,y):
    total=0
    for poly in polygons:
        for a,b in zip(poly,poly[1:]+poly[:1]):
            cross=(b[0]-a[0])*(y-a[1])-(b[1]-a[1])*(x-a[0])
            if a[1]<=y<b[1] and cross>0:total+=1
            if b[1]<=y<a[1] and cross<0:total-=1
    return total!=0


class EllipseBooleanTests(unittest.TestCase):
    invoke=booleans.BooleanTests.invoke
    document=booleans.BooleanTests.document
    combine=booleans.BooleanTests.combine

    def check_samples(self,result,geometries):
        # Evaluate analytic operands independently, outside each input's error band.
        bounds=[]
        for source in result['inputs']:
            bound=math.sqrt(float(F(source['flattening_deviation_squared'])))
            bound+=math.sqrt(float(F(source.get('snapping_deviation_squared','0'))))
            conversion=source.get('primitive_conversion')
            if conversion:bound+=math.sqrt(float(F(conversion['world_space_deviation_squared'])))
            bounds.append(bound+1e-9)
        output=[[tuple(map(float,p)) for p in poly] for poly in booleans.polygons(result['geometry'])]
        checked=0
        for yi in range(65):
            y=yi/2+.137
            for xi in range(81):
                x=xi/2+.193
                if any(boundary_distance_lower(g,x,y)<=b for g,b in zip(geometries,bounds)):continue
                expected=booleans.truth([occupied(g,x,y) for g in geometries],result['mode'])
                self.assertEqual(inside_output(output,x,y),expected,(result['mode'],x,y,bounds))
                checked+=1
        self.assertGreater(checked,4000)

    def test_all_modes_containment_overlap_nesting_disjoint_and_tangent(self):
        a=math.pi*64
        lens=2*64*math.acos(.5)-4*math.sqrt(192)
        cases=[
            ([ellipse(12,12,8,5),booleans.rect(0,0,40,32)],(math.pi*40,1280,math.pi*40)),
            ([ellipse(12,12,8),ellipse(20,12,8)],(a,a,lens)),
            ([ellipse(12,12,8),ellipse(12,12,4)],(a,math.pi*16,math.pi*16)),
            ([ellipse(8,12,5),ellipse(26,12,5)],(math.pi*25,math.pi*25,0)),
            ([ellipse(8,12,8),ellipse(24,12,8)],(a,a,0)),
        ]
        for geometries,(aa,bb,overlap) in cases:
            doc=self.document(geometries);saved=copy.deepcopy(doc)
            expected=(aa+bb-overlap,overlap,aa-overlap,aa+bb-2*overlap)
            for mode,area in zip(MODES,expected):
                with self.subTest(geometries=geometries,mode=mode):
                    result=self.combine(doc,mode,precision='auto')
                    self.assertLess(abs(result['area']-area),3.5)
                    self.assertEqual(result['precision'],'auto')
                    self.assertIn(result['certificate'],('exact','tolerance_snap'))
                    self.assertLessEqual(result['work_units'],2_000_000)
                    self.check_samples(result,geometries)
                    for geometry,source in zip(geometries,result['inputs']):
                        if geometry['shape']=='ellipse':
                            conversion=source['primitive_conversion']
                            self.assertEqual(conversion['method'],'four_tangent_cubics')
                            self.assertGreater(F(conversion['world_space_deviation_squared']),0)
            self.assertEqual(doc,saved)

    def test_affine_nested_placement_uses_world_error_and_preserves_primitives(self):
        shape=ellipse(12,12,8,5)
        matrix=[-1,.5,.25,1,32,3]
        doc=self.document([shape,booleans.rect(0,0,40,32)],transforms=[matrix,matrix])
        group=dict(id='parent',transform=[1,0,0,1,2,1],content=dict(type='group'))
        doc=self.invoke(dict(command='document.edit',document=doc,expected_revision=doc['revision'],
            operations=[dict(op='add',item=group),dict(op='reparent',id='s0',parent='parent')]))['document']
        saved=copy.deepcopy(doc)
        result=self.invoke(dict(command='document.boolean',document=doc,ids=['s0','s1'],mode='intersection',precision='tolerance'))
        # Both placements still contain the ellipse; determinant scales its area.
        self.assertLess(abs(result['area']-math.pi*40*1.125),2)
        conversion=result['inputs'][0]['primitive_conversion']
        self.assertLess(float(F(conversion['world_space_deviation_squared'])),.0001)
        self.assertEqual(doc,saved)
        self.assertEqual(next(i for i in doc['items'] if i['id']=='s0')['content']['geometry'],shape)


if __name__=='__main__':unittest.main()
