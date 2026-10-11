"""Independent exact point placement, coverage, limits and durable revisions."""
import base64
import copy
from fractions import Fraction as F
import json
import tempfile
import unittest

import test_editing_cli as editing
from test_mcp import Client


def mapped(matrix, points):
    m=list(map(F,matrix))
    return [[m[k]*F(x)+m[k+2]*F(y)+m[k+4] for k in range(2)] for x,y in points]


def path(points, curve=False):
    p=[list(map(float,v)) for v in points]
    if curve:
        return dict(shape='path',commands=[dict(verb='move',to=p[0]),
            dict(verb='cubic',control1=p[1],control2=p[2],to=p[3]),
            dict(verb='line',to=p[4]),dict(verb='line',to=p[5]),dict(verb='close')])
    return dict(shape='path',commands=[dict(verb='move' if i==0 else 'line',to=v)
                                     for i,v in enumerate(p)]+[dict(verb='close')])


def fixture(origin=30000., factor=32767.1, curve=False):
    matrix=[factor,0,-factor,1,6.125,6.125-origin]
    local=lambda x,y:[origin+y+x/factor,origin+y]
    points=([local(x,y) for x,y in [(0,0),(1,-3),(4,8),(5.75,0),(5.75,8),(0,8)]]
            if curve else [local(x,y) for x,y in [(0,0),(5.75,0),(5.75,5.75),(0,5.75)]])
    item=dict(id='art',transform=matrix,content=dict(type='vector',
        geometry=path(points,curve),fill=[40,120,220,255]))
    d=dict(schema_version=2,id='point-arithmetic',kind='vector',width=20,height=20,
           color_space='srgb',items=[item])
    return d,points,mapped(matrix,points)


def reference(source, points, curve=False):
    d=copy.deepcopy(source);d['items'][0].pop('transform')
    d['items'][0]['content']['geometry']=path(points,curve)
    return d


class PointArithmeticTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke

    def pixels(self,source,**options):
        out=self.invoke(dict(command='document.export',document=source,format='png',**options))
        return editing.png_pixels(base64.b64decode(out['data']))[:3]

    def test_cancelling_point_products_preserve_independent_rational_bounds(self):
        old_failures=0
        for origin in (-30000.,-12345.7,12345.7,30000.):
            for factor in (32767.1,24576.3,16384.7,-32767.1,-18000.3):
                source,local,exact=fixture(origin,factor)
                wanted=[min(p[0] for p in exact),min(p[1] for p in exact),
                        max(p[0] for p in exact),max(p[1] for p in exact)]
                info=self.invoke(dict(command='document.inspect',document=source))['items'][0]
                for actual,expected in zip(info['geometry_bounds'],wanted):
                    self.assertLessEqual(abs(F(actual)-expected),F(1e-9),(origin,factor,actual,expected))
                m=source['items'][0]['transform']
                ordinary=[[m[k]*p[0]+m[k+2]*p[1]+m[k+4] for k in range(2)] for p in local]
                old_failures+=any(abs(F(a)-b)>F(1e-9) for p,q in zip(ordinary,exact) for a,b in zip(p,q))
                snapshot=json.loads(self.invoke(dict(command='document.export',document=source,format='snapshot'))['data'])
                self.assertEqual(snapshot['items'][0]['transform'],m)
                self.assertEqual(snapshot['items'][0]['content']['geometry'],source['items'][0]['content']['geometry'])
        self.assertGreater(old_failures,15)

    def test_placed_curves_and_clips_match_exact_reference_across_render_routes(self):
        for curve in (False,True):
            source,_,exact=fixture(curve=curve);expected=reference(source,exact,curve)
            for profile in ('standard','large_vector'):
                source['resource_profile']=expected['resource_profile']=profile
                for scale in (1,4):
                    for evaluation in ('whole','tiled'):
                        options=dict(scale=scale,render_options=dict(antialias='supersample4',evaluation=evaluation))
                        self.assertEqual(self.pixels(source,**options),self.pixels(expected,**options))
            # Item-local clip placement uses the same supplied finite matrix.
            clip=[(30000.,30000.),(30000.+3/32767.1,30000.),
                  (30006.+3/32767.1,30006.),(30006.,30006.)]
            source['items'][0]['clip']=dict(geometry=path(clip))
            expected['items'][0]['clip']=dict(geometry=path(mapped(source['items'][0]['transform'],clip)))
            self.assertEqual(self.pixels(source),self.pixels(expected))

    def test_5000_transformed_paths_match_independently_placed_scene(self):
        source,_,_=fixture();source.update(resource_profile='large_vector',width=128,height=96)
        matrix=source['items'][0]['transform'];source['items']=[]
        expected=copy.deepcopy(source)
        for i in range(5000):
            x,y=i%100,i//100
            points=[[30000.+yy+xx/matrix[0],30000.+yy]
                    for xx,yy in [(x,y),(x+.5,y),(x+.5,y+.5),(x,y+.5)]]
            item=dict(id=f'art-{i}',transform=matrix,content=dict(type='vector',
                      geometry=path(points),fill=[40,120,220,255]))
            source['items'].append(item)
            direct=copy.deepcopy(item);direct.pop('transform')
            direct['content']['geometry']=path(mapped(matrix,points));expected['items'].append(direct)
        self.assertEqual(self.pixels(source),self.pixels(expected))

    def test_saved_move_retry_undo_preserve_original_controls_and_exact_bounds(self):
        source,local,_=fixture();client=Client();self.addCleanup(client.close);client.initialize()
        with tempfile.TemporaryDirectory() as root:
            session=dict(session_root=root,session_id='points')
            original=client.success('session.create',**session,request_id='create',document=source)
            matrix=source['items'][0]['transform'].copy();matrix[4]+=2;matrix[5]+=1
            action=dict(type='edit',operations=[dict(op='transform',id='art',matrix=matrix,space='replace')])
            edited=client.success('session.apply',**session,request_id='move',expected_revision=0,action=action)
            exact=mapped(matrix,local)
            info=self.invoke(dict(command='document.inspect',document=edited['document']))['items'][0]
            for actual,wanted in zip(info['geometry_bounds'],[min(p[0] for p in exact),min(p[1] for p in exact),max(p[0] for p in exact),max(p[1] for p in exact)]):
                self.assertLessEqual(abs(F(actual)-wanted),F(1e-9))
            self.assertTrue(client.success('session.apply',**session,request_id='move',expected_revision=0,action=action)['replayed'])
            restored=client.success('session.apply',**session,request_id='undo',expected_revision=1,action=dict(type='undo'))
            self.assertEqual(restored['document']['items'],original['document']['items'])
            self.assertTrue(client.success('session.verify',**session)['valid'])

    def test_point_contract_keeps_matrix_admission_limits(self):
        capabilities=self.invoke(dict(command='capabilities'))['coordinate_precision']['point_arithmetic']
        self.assertEqual(capabilities['ordinary_or_compensated_absolute_error'],1e-9)
        self.assertFalse(capabilities['admission_limits_changed'])
        source,_,_=fixture();source['items'][0]['transform'][0]=32769
        self.assertEqual(self.invoke(dict(command='document.validate',document=source),1)['code'],'INVALID_DOCUMENT')


if __name__=='__main__':unittest.main()
