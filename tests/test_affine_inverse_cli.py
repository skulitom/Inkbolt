"""Exact Fraction determinant decisions and atomic saved-transform failures."""
import copy
from fractions import Fraction as F
import math
import random
import struct
import tempfile
import unittest
import test_editing_cli as editing
from test_mcp import Client
from test_sessions_cli import invoke


BELOW = [
    [24220.7099609375,10600.763671875,11346.4423828125,4966.037511316861,0,0],
    [17601.9013671875,11422.0576171875,9665.5810546875,6272.096485896673,0,0],
    [21570.9453125,9324.669921875,13317.0869140625,5756.6990224853525,0,0],
    [24515.2080078125,12982.1474609375,10101.38671875,5349.238395243359,0,0],
]
ABOVE = [
    [28082.236328125,19869.3466796875,21177.486328125,14983.94973752266,12345.25,-23456.5],
    [20828.6787109375,24176.8720703125,8651.3291015625,10042.023300153625,12345.25,-23456.5],
    [19225.697265625,9854.1689453125,23490.9345703125,12040.324714413737,12345.25,-23456.5],
]


def determinant(m):
    a,b,c,d = map(F,m[:4])
    return a*d-b*c


def f32(x):
    return struct.unpack('<f',struct.pack('<f',x))[0]


def renderer_determinant(m):
    a,b,c,d = map(f32,m[:4])
    return f32(a*d)-f32(b*c)


def document(matrix):
    return dict(schema_version=2,id='affine-boundary',kind='vector',width=128,height=128,
                color_space='srgb',items=[dict(id='thin',transform=matrix,
                content=dict(type='vector',geometry=dict(shape='rect',x=0,y=0,width=.001,height=.001),
                             fill=[20,80,150,255]))])


class AffineInverseTests(unittest.TestCase):
    invoke = editing.EditingCliTests.invoke

    def test_cancelled_determinants_respect_the_exact_existing_boundary(self):
        for source,valid in [(m,False) for m in BELOW]+[(m,True) for m in ABOVE]:
            for sign in (-1,1):
                m = source.copy();m[0]*=sign;m[1]*=sign
                with self.subTest(matrix=m):
                    self.assertNotEqual(renderer_determinant(m),0)
                    self.assertEqual(abs(determinant(m))>=F(1e-8),valid)
                    ordinary = m[0]*m[3]-m[1]*m[2]
                    self.assertEqual(abs(ordinary)>=1e-8,not valid)
                    result = self.invoke(dict(command='document.validate',document=document(m)),0 if valid else 1)
                    if valid:
                        self.assertEqual(result['items'][0]['transform'],m)
                    else:
                        self.assertEqual(result['code'],'UNSUPPORTED')
                        self.assertIn('near-singular',result['message'])

    def test_boundary_neighbors_and_seeded_cancellation_match_independent_fraction(self):
        client=Client();self.addCleanup(client.close);client.initialize()
        matrices=[[1,0,0,sign*d,0,0] for sign in (-1,1)
                  for d in (math.nextafter(1e-8,0),1e-8,math.nextafter(1e-8,math.inf))]
        rng=random.Random(37126)
        while len(matrices)<100:
            a,b,c=[rng.randrange(8000000,33000000)/1024 for _ in range(3)]
            d=b*c/a
            if d>32768:continue
            d=math.nextafter(d,rng.choice([0,math.inf]))
            matrices.append([a,b,c,d,0,0])
        accepted=rejected=0
        for m in matrices:
            expected=abs(determinant(m))>=F(1e-8) and renderer_determinant(m)!=0
            result=client.tool('document.validate',document=document(m))['structuredContent']
            self.assertEqual(result['ok'],expected,m)
            accepted+=expected;rejected+=not expected
            if not expected:self.assertEqual(result['error']['code'],'UNSUPPORTED')
        self.assertGreater(accepted,10);self.assertGreater(rejected,10)

    def test_coordinate_and_renderer_limits_still_fail_explicitly(self):
        for m,code in [([32769,0,0,1,0,0],'INVALID_DOCUMENT'),
                       ([1,0,0,1,0,32769],'INVALID_DOCUMENT'),
                       ([1,1,1,1,0,0],'UNSUPPORTED'),
                       ([1,1,1,1+2**-25,0,0],'UNSUPPORTED')]:
            result=self.invoke(dict(command='document.validate',document=document(m)),1)
            self.assertEqual(result['code'],code)
        self.assertGreater(abs(determinant([1,1,1,1+2**-25,0,0])),F(1e-8))

    def test_cli_and_mcp_failures_preserve_history_then_allow_edit_retry_and_undo(self):
        client=Client();self.addCleanup(client.close);client.initialize()
        for transport in ('cli','mcp'):
            with tempfile.TemporaryDirectory() as root:
                session=dict(session_root=root,session_id='boundary')
                def call(command,**kw):
                    args=dict(**session,**kw)
                    return (invoke(dict(command=command,**args)) if transport=='cli'
                            else client.tool(command,**args)['structuredContent'])
                original=call('session.create',request_id='create',document=document([1,0,0,1,0,0]))
                self.assertTrue(original['ok'],original)
                before=call('session.history',limit=128)
                failed=dict(request_id='correctable',expected_revision=0,
                            action=dict(type='edit',operations=[dict(op='transform',id='thin',space='replace',matrix=BELOW[0])]))
                result=call('session.apply',**failed)
                self.assertFalse(result['ok']);self.assertEqual(result['error']['code'],'UNSUPPORTED')
                self.assertEqual(call('session.history',limit=128),before)
                self.assertEqual(call('session.read')['result']['document'],original['result']['document'])
                corrected=copy.deepcopy(failed);corrected['action']['operations'][0]['matrix']=ABOVE[0]
                edited=call('session.apply',**corrected)
                self.assertTrue(edited['ok'],edited)
                self.assertEqual(edited['result']['document']['items'][0]['transform'],ABOVE[0])
                replay=call('session.apply',**corrected)
                self.assertTrue(replay['result']['replayed'])
                undo=call('session.apply',request_id='undo',expected_revision=1,action=dict(type='undo'))
                self.assertEqual(undo['result']['document']['items'],original['result']['document']['items'])
                self.assertTrue(call('session.verify')['result']['valid'])

    def test_capabilities_describe_the_coefficient_bound_without_a_sampling_claim(self):
        info=self.invoke(dict(command='capabilities'))['coordinate_precision']['affine_inverse']
        self.assertEqual(info['minimum_absolute_determinant'],1e-8)
        self.assertEqual(info['fast_coefficient_point_error'],1e-9)
        self.assertEqual(info['point_coordinate_absolute_limit'],65536)
        self.assertTrue(info['renderer_nonsingular_check'])
        self.assertIn('sampling_are_separate',info['error_scope'])


if __name__=='__main__':unittest.main()
