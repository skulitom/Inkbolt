"""Independent analytic area, rational winding and decoded occupancy for path combinations."""
import base64
import copy
from fractions import Fraction as F
import json
import random
import tempfile
import unittest
import test_editing_cli as editing
from test_mcp import Client


def rect(x,y,w,h):return dict(shape='rect',x=x,y=y,width=w,height=h)
def path(points):return dict(shape='path',commands=[dict(verb='move',to=points[0])]+[dict(verb='line',to=p) for p in points[1:]]+[dict(verb='close')])
def contains(box,x,y):return box['x']<x<box['x']+box['width'] and box['y']<y<box['y']+box['height']
def truth(states,mode):return any(states) if mode=='union' else all(states) if mode=='intersection' else states[0] and not any(states[1:]) if mode=='difference' else sum(states)%2==1
def polygons(g):
    if g is None:return []
    result=[]
    for c in g['commands']:
        if c['verb']=='move':result.append([tuple(map(F,c['to']))])
        elif c['verb']=='line':result[-1].append(tuple(map(F,c['to'])))
        else:assert c['verb']=='close'
    return result
def winding(polygon,x,y):
    v=0
    for a,b in zip(polygon,polygon[1:]+polygon[:1]):
        cross=(b[0]-a[0])*(y-a[1])-(b[1]-a[1])*(x-a[0])
        if a[1]<=y<b[1] and cross>0:v+=1
        if b[1]<=y<a[1] and cross<0:v-=1
    return v
def area(polygon):return sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(polygon,polygon[1:]+polygon[:1]))/2


class BooleanTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def document(self,geometries,rules=None,transforms=None):
        d=self.invoke(dict(command='document.create',id='boolean-fixture',kind='vector',width=32,height=24))
        items=[dict(id='s'+str(i),transform=(transforms[i] if transforms else [1,0,0,1,0,0]),content=dict(type='vector',geometry=g,fill=[30,90,180,255],fill_rule=rules[i] if rules else 'nonzero')) for i,g in enumerate(geometries)]
        return self.invoke(dict(command='document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=i) for i in items]))['document']
    def combine(self,d,mode='union',expected=0,**kw):
        return self.invoke(dict(command='document.boolean',document=d,ids=['s'+str(i) for i in range(len(d['items']))],mode=mode,**kw),expected)
    def rendered(self,result):
        d=self.invoke(dict(command='document.create',id='boolean-output',kind='vector',width=32,height=24))
        if result['geometry'] is not None:
            d=self.invoke(dict(command='document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=dict(id='output',content=dict(type='vector',geometry=result['geometry'],fill=[30,90,180,255]))) ]))['document']
        raw=self.invoke(dict(command='document.export',document=d,format='png'))
        return editing.png_pixels(base64.b64decode(raw['data']))[2]
    def check_area(self,result,expected):
        self.assertEqual(F(result['area_exact']),expected)
        if result['rounding_deviation_squared']=='0':self.assertEqual(sum(area(p) for p in polygons(result['geometry'])),expected)

    def test_rectangle_operations_exact_area_and_every_pixel(self):
        cases=[(rect(2,3,12,8),rect(9,7,10,7)),(rect(2,2,16,16),rect(5,5,7,6)),(rect(2,2,5,5),rect(7,2,5,5)),(rect(2,2,5,5),rect(7,7,5,5)),(rect(2,2,5,5),rect(14,10,5,5)),(rect(2,2,5,5),rect(2,2,5,5))]
        for a,b in cases:
            d=self.document([a,b]);original=copy.deepcopy(d)
            overlap=max(0,min(a['x']+a['width'],b['x']+b['width'])-max(a['x'],b['x']))*max(0,min(a['y']+a['height'],b['y']+b['height'])-max(a['y'],b['y']))
            av=a['width']*a['height'];bv=b['width']*b['height']
            for mode,expected in [('union',av+bv-overlap),('intersection',overlap),('difference',av-overlap),('xor',av+bv-2*overlap)]:
                result=self.combine(d,mode,curve_tolerance=0);self.check_area(result,expected)
                self.assertEqual(result['empty'],expected==0);self.assertEqual(result['geometry'] is None,expected==0)
                pixels=self.rendered(result)
                for y in range(24):
                    for x in range(32):self.assertEqual(pixels[(y*32+x)*4+3],255 if truth([contains(g,x+.5,y+.5) for g in [a,b]],mode) else 0,(a,b,mode,x,y))
            self.assertEqual(d,original)

    def test_random_fractional_multisource_rectangles_match_exact_cell_partition(self):
        rng=random.Random(419)
        for _ in range(8):
            boxes=[rect(rng.randrange(-8,40)/4,rng.randrange(-8,40)/4,rng.randrange(1,32)/4,rng.randrange(1,32)/4) for _ in range(3)]
            xs=sorted({F(g['x'])+v*F(g['width']) for g in boxes for v in (0,1)});ys=sorted({F(g['y'])+v*F(g['height']) for g in boxes for v in (0,1)})
            d=self.document(boxes)
            for mode in ('union','intersection','difference','xor'):
                expected=sum((x1-x0)*(y1-y0) for x0,x1 in zip(xs,xs[1:]) for y0,y1 in zip(ys,ys[1:]) if truth([contains(g,(x0+x1)/2,(y0+y1)/2) for g in boxes],mode))
                result=self.combine(d,mode,curve_tolerance=0);self.check_area(result,expected)
                if mode!='difference':
                    reversed_result=self.invoke(dict(command='document.boolean',document=d,ids=['s2','s1','s0'],mode=mode,curve_tolerance=0))
                    self.assertEqual(result['geometry'],reversed_result['geometry'])

    def test_rational_rectangle_area_does_not_round_endpoint_sums(self):
        box=rect(.1,.2,.3,.7);d=self.document([box,box])
        for mode in ('union','intersection'):
            result=self.combine(d,mode,curve_tolerance=0)
            self.check_area(result,F(.3)*F(.7))
            self.assertGreater(F(result['rounding_deviation_squared']),0)

    def test_coincident_reversed_edges_self_crossings_and_fill_rules(self):
        square=path([[2,2],[10,2],[10,10],[2,10]])
        double=dict(shape='path',commands=square['commands']*2)
        for rule,expected in [('nonzero',64),('even_odd',0)]:
            d=self.document([double,rect(0,0,20,20)],[rule,'nonzero']);result=self.combine(d,'intersection');self.check_area(result,expected)
        reverse=path([[2,2],[2,10],[10,10],[10,2]])
        cancelled=dict(shape='path',commands=square['commands']+reverse['commands'])
        self.check_area(self.combine(self.document([cancelled,rect(0,0,20,20)]),'intersection'),0)
        crossed=path([[2,2],[10,10],[2,10],[10,2]])
        result=self.combine(self.document([crossed,rect(0,0,20,20)]),'intersection')
        self.check_area(result,32);self.assertEqual(result['positive_contours'],2);self.assertEqual(result['negative_contours'],0)
        p=polygons(result['geometry'])
        for x,y,w in [(6,3,True),(6,9,True),(3,6,False),(12,6,False)]:self.assertEqual(sum(winding(v,F(x),F(y)) for v in p)!=0,w)

    def test_nested_holes_disconnected_regions_and_shared_vertices(self):
        d=self.document([rect(1,1,20,20),rect(4,4,12,12),rect(18,5,2,8)])
        result=self.combine(d,'difference');self.check_area(result,240)
        self.assertEqual((result['positive_contours'],result['negative_contours']),(1,2))
        a=path([[0,0],[3,0],[6,0],[6,6],[0,6]])
        b=path([[6,6],[10,6],[10,10],[6,10]])
        result=self.combine(self.document([a,b]));self.check_area(result,52)
        self.assertEqual(result['positive_contours'],2)
        self.assertEqual(sum(p.count((F(6),F(6))) for p in polygons(result['geometry'])),2)

    def test_transformed_geometry_uses_world_coordinates_and_returns_editable_path(self):
        d=self.document([rect(0,0,6,4),rect(0,0,6,4)],transforms=[[1,.5,0,1,2,1],[-1,0,.25,1,12,3]])
        result=self.combine(d,'intersection',curve_tolerance=0)
        reference=[[(F(2),F(1)),(F(8),F(4)),(F(8),F(8)),(F(2),F(5))],[(F(12),F(3)),(F(6),F(3)),(F(7),F(7)),(F(13),F(7))]]
        output=polygons(result['geometry'])
        for y in range(20):
            for x in range(30):
                px=F(x,2)+F(1,7);py=F(y,2)+F(1,11)
                self.assertEqual(sum(winding(p,px,py) for p in output)!=0,all(winding(p,px,py)!=0 for p in reference))
        self.assertEqual(result['coordinates'],'document_root');self.assertGreater(F(result['area_exact']),0)
        saved=self.invoke(dict(command='document.export',document=d,format='snapshot'))
        self.assertEqual(self.combine(json.loads(saved['data']),'intersection',curve_tolerance=0),result)

    def test_cubic_flattening_has_exact_area_and_independent_deviation_bound(self):
        curve=dict(shape='path',commands=[dict(verb='move',to=[0,0]),dict(verb='cubic',control1=[4,8],control2=[8,8],to=[12,0]),dict(verb='close')])
        d=self.document([curve,rect(0,0,12,10)])
        last_error=None
        for tolerance in (.5,.125,.03125):
            result=self.combine(d,'intersection',curve_tolerance=tolerance)
            count=result['curves']['topology']['curve_arcs']
            self.assertEqual(F(result['area_exact']),48-F(48,count*count))
            bound=F(result['inputs'][0]['flattening_deviation_squared'])
            self.assertEqual(bound,F(64,count**4));self.assertLessEqual(bound,F(tolerance)**2)
            error=48-F(result['area_exact'])
            if last_error is not None:self.assertLess(error,last_error)
            last_error=error
            for polygon in polygons(result['geometry']):
                for x,y in polygon:
                    self.assertTrue(y==0 or y==2*x-x*x/6)
            self.assertEqual(result['curves']['topology']['certificate'],'exact_simultaneous_curve_to_chord_homotopy')

    def test_explicit_empty_errors_and_input_resource_limits_preserve_sources(self):
        d=self.document([rect(1,1,4,4),rect(10,10,4,4)]);saved=copy.deepcopy(d)
        for ids in ([],['s0'],['s0','s0'],['s0','missing']):self.invoke(dict(command='document.boolean',document=d,ids=ids,mode='union'),1)
        for value in (-1,65):self.combine(d,expected=1,curve_tolerance=value)
        self.assertTrue(self.combine(d,'intersection')['empty'])
        ellipse=dict(shape='ellipse',cx=10,cy=10,rx=4,ry=3)
        self.assertEqual(self.combine(self.document([ellipse,rect(0,0,20,20)]),expected=1)['code'],'UNSUPPORTED')
        many=self.document([dict(shape='regular_polygon',cx=10,cy=10,radius=8,sides=256) for _ in range(3)])
        self.assertEqual(self.combine(many,expected=1)['code'],'RESOURCE_LIMIT')
        curve=dict(shape='path',commands=[dict(verb='move',to=[0,0]),dict(verb='cubic',control1=[4,8],control2=[8,8],to=[12,0]),dict(verb='close')])
        curved=self.document([curve,rect(0,0,20,20)])
        self.assertEqual(self.combine(curved,expected=1,curve_tolerance=0)['code'],'UNSUPPORTED')
        self.assertEqual(self.combine(curved,expected=1,curve_tolerance=1e-12)['code'],'RESOURCE_LIMIT')
        self.assertEqual(d,saved)

    def test_mcp_materialization_snapshots_and_session_undo_preserve_operands(self):
        d=self.document([rect(2,2,20,16),rect(6,6,12,8)])
        with tempfile.TemporaryDirectory() as root:
            c=Client();args=dict(session_root=root,session_id='boolean-session')
            try:
                c.initialize();result=c.success('document.boolean',document=d,ids=['s0','s1'],mode='difference',curve_tolerance=0)
                self.check_area(result,224)
                c.success('session.create',**args,request_id='create',document=d)
                ops=[dict(op='properties',id=id,visible=False) for id in ['s0','s1']]+[dict(op='add',item=dict(id='result',content=dict(type='vector',geometry=result['geometry'],fill=[30,90,180,255])))]
                after=c.success('session.apply',**args,expected_revision=0,request_id='combine',action=dict(type='edit',operations=ops))['document']
                for source,retained in zip(d['items'],after['items'][:2]):self.assertEqual(source['content'],retained['content'])
                exported=c.success('document.export',document=after,format='svg');self.assertIn('<path',exported['data'])
                undo=c.success('session.apply',**args,expected_revision=1,request_id='undo',action=dict(type='undo'))['document']
                self.assertEqual(undo['items'],d['items']);c.success('session.verify',**args)
            finally:c.close()


if __name__=='__main__':unittest.main()
