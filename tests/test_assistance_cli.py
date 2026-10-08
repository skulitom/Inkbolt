"""Local layout assistance: independent optimization, geometry and durable execution."""
import base64
import copy
from fractions import Fraction as F
import itertools
import random
import tempfile
import unittest
import test_editing_cli as editing
import test_variants_cli as variants
from test_mcp import Client
from layout_reference import optimum, rectangle_bounds


def original(sizes):
    return dict(schema_version=2, id='ordered-artwork', kind='vector', width=128, height=128,
                color_space='srgb', items=[dict(id=f'tile-{i}', content=dict(type='vector',
                geometry=dict(shape='rect', x=0, y=0, width=w, height=h),
                fill=[(30+i*9)%256, 100, 180, 255])) for i, (w, h) in enumerate(sizes)])


class AssistanceTests(unittest.TestCase):
    invoke = editing.EditingCliTests.invoke
    edit = variants.VariantTests.edit

    def valid(self, d):
        return self.invoke(dict(command='document.validate', document=d))

    def plan(self, d, options, expected=0, **kw):
        return self.invoke(dict(command='assist.layout', document=d, options=options, **kw), expected)

    def options(self, d, **kw):
        return dict(ids=[i['id'] for i in d['items']], bounds=[0, 0, 100, 100], **kw)

    def test_optimizer_beats_greedy_and_reports_exact_certificate(self):
        d = self.valid(original([(6, 1), (4, 10), (6, 10)]))
        o = self.options(d); o['bounds'] = [0, 0, 10, 11]
        p = self.plan(d, o)
        self.assertEqual(p['row_ends'], [1, 3]); self.assertEqual(p['minimum_height'], 11)
        self.assertEqual(p['minimum_height_exact'], dict(numerator='11', denominator='1'))
        placed = self.edit(d, dict(op='assist_layout', options=o))
        self.assertEqual([i['transform'][4:] for i in placed['items']], [[0,0], [0,1], [4,1]])
        self.assertEqual([i['content'] for i in placed['items']], [i['content'] for i in d['items']])

    def test_exhaustive_partition_oracle_random_and_fractional_widths(self):
        rng = random.Random(731)
        for case in range(48):
            sizes = [(rng.randint(1,20)/4, rng.randint(1,32)/4) for _ in range(rng.randint(1,9))]
            w = rng.randint(4,25)/2; gap = (rng.randint(0,4)/4, rng.randint(0,4)/4)
            d = self.valid(original(sizes)); o = self.options(d, gap=gap); o['bounds'] = [0,0,w,100]
            expected = optimum(sizes, w, gap)
            with self.subTest(case=case):
                if expected is None:
                    self.assertEqual(self.plan(d,o,1)['code'], 'LAYOUT_NO_FIT'); continue
                p = self.plan(d,o)
                self.assertEqual(F(int(p['minimum_height_exact']['numerator']),int(p['minimum_height_exact']['denominator'])),expected[0])
                self.assertEqual(p['row_ends'],expected[2])
                self.assertEqual(p,self.plan(d,o))

    def test_every_alignment_has_exact_independently_computed_placement(self):
        d = self.valid(original([(6,2),(3,5),(5,3)]))
        for horizontal, vertical in itertools.product(['start','center','end'], repeat=2):
            o = self.options(d, gap=[1,2], horizontal=horizontal, vertical=vertical);o['bounds']=[-3.5,2.25,7.5,42.25]
            p = self.plan(d,o); changed=self.edit(d,dict(op='assist_layout',options=o))
            for row in p['rows']:
                spare=11-row['width'];x=-3.5+spare*{'start':0,'center':.5,'end':1}[horizontal]
                for k in range(row['start'],row['end']):
                    shape=d['items'][k]['content']['geometry'];w,h=shape['width'],shape['height']
                    y=row['y']+(row['height']-h)*{'start':0,'center':.5,'end':1}[vertical]
                    actual=rectangle_bounds(shape,changed['items'][k]['transform'])
                    self.assertEqual(actual,[x,y,x+w,y+h]);self.assertEqual(p['placements'][k]['actual'],actual);x+=w+1

    def test_exact_width_boundary_does_not_silently_round_to_fit(self):
        d=self.valid(original([(.1,1),(.2,1)]));o=self.options(d);o['bounds']=[0,0,.3,3]
        self.assertEqual(self.plan(d,o)['row_ends'],[1,2])
        o['bounds'][2]=.1+.2;self.assertEqual(self.plan(d,o)['row_ends'],[2])
        o['bounds'][3]=.9999999999999999;self.assertEqual(self.plan(d,o,1)['code'],'LAYOUT_NO_FIT')

    def test_parent_shear_reflection_and_rotation_preserve_linear_parts(self):
        d=original([(3,4),(7,2),(1,5)])
        d['items'].insert(0,dict(id='group',transform=[-2,.5,.25,1.5,16,7],content=dict(type='group')))
        for i in d['items'][1:]:i['parent']='group';i['transform']=[0,1,-1,0,2,3]
        d=self.valid(d);o=self.options(d);o['ids']=o['ids'][1:];o['bounds']=[-10,-10,50,80]
        p=self.plan(d,o);changed=self.edit(d,dict(op='assist_layout',options=o));self.assertEqual(changed['items'][0],d['items'][0])
        a,b,c,e,tx,ty=d['items'][0]['transform']
        for before,after,placement in zip(d['items'][1:],changed['items'][1:],p['placements']):
            self.assertEqual(before['transform'][:4],after['transform'][:4]);self.assertEqual(before['content'],after['content'])
            aa,bb,cc,dd,xx,yy=after['transform'];world=[a*aa+c*bb,b*aa+e*bb,a*cc+c*dd,b*cc+e*dd,a*xx+c*yy+tx,b*xx+e*yy+ty]
            actual=rectangle_bounds(after['content']['geometry'],world)
            self.assertLessEqual(max(abs(v-w) for v,w in zip(actual,placement['target'])),1e-7)

    def test_group_layout_keeps_descendants_and_unselected_artwork_identical(self):
        d=original([(3,4),(7,2)]);d['items'].insert(0,dict(id='group',content=dict(type='group')));d['items'][1]['parent']='group'
        d=self.valid(d);o=self.options(d);o['ids']=['group'];o['bounds']=[20,30,40,60]
        changed=self.edit(d,dict(op='assist_layout',options=o));self.assertEqual(changed['items'][1:],d['items'][1:])
        self.assertEqual(changed['items'][0]['transform'][4:],[20,30])
        o['ids']=['group','tile-0'];self.assertEqual(self.plan(d,o,1)['code'],'INVALID_OPERATION')

    def test_invalid_hidden_nonprinting_locked_duplicate_and_oversized_inputs(self):
        d=self.valid(original([(3,4),(7,2)]));o=self.options(d)
        for field,value in [('bounds',[0,0,0,2]),('gap',[-1,0]),('ids',['tile-0','tile-0']),('ids',['missing'])]:
            bad=dict(o);bad[field]=value;self.plan(d,bad,1)
        for field,value in [('visible',False),('locked',True)]:
            bad=copy.deepcopy(d);bad['items'][0][field]=value;self.plan(bad,o,1)
        bad=copy.deepcopy(d);bad['items'][0]['content']=dict(type='work_path',geometry=d['items'][0]['content']['geometry']);self.plan(bad,o,1)
        many=self.valid(original([(1,1)]*65));self.assertEqual(self.plan(many,self.options(many),1)['code'],'RESOURCE_LIMIT')
        self.assertEqual(self.plan(d,dict(o,learned_model='absent'),1)['code'],'INVALID_REQUEST')
        self.assertEqual(self.plan(d,o,1,control=dict(timeout_ms=0))['code'],'TIMEOUT')

    def test_maximum_selection_and_declared_environment(self):
        d=self.valid(original([(1,1)]*64));o=self.options(d);o['bounds']=[0,0,8,8];p=self.plan(d,o)
        self.assertEqual(p['row_ends'],list(range(8,65,8)));self.assertEqual(p['minimum_height'],8)
        self.assertLessEqual(p['candidates_examined'],64*65//2)
        self.assertEqual(p['dependencies'],dict(execution='builtin_cpu',models=[],gpu=False,network=False,external_resources_loaded=False))

    def test_integer_packed_rectangles_render_exact_independent_pixels(self):
        d=self.valid(original([(6,1),(4,10),(6,10)]));o=self.options(d);o['bounds']=[2,3,12,14]
        changed=self.edit(d,dict(op='assist_layout',options=o))
        pixels=editing.png_pixels(base64.b64decode(self.invoke(dict(command='document.export',document=changed,format='png',render_options=dict(antialias='none')))['data']))[2]
        expected=bytearray(128*128*4)
        for item,(x,y,w,h) in zip(d['items'],[(2,3,6,1),(2,4,4,10),(6,4,6,10)]):
            for yy in range(y,y+h):
                for xx in range(x,x+w):expected[(yy*128+xx)*4:(yy*128+xx+1)*4]=bytes(item['content']['fill'])
        self.assertEqual(pixels,bytes(expected))

    def test_mcp_atomic_apply_undo_retry_failure_and_source_history(self):
        d=self.valid(original([(6,1),(4,10),(6,10)]));o=self.options(d);o['bounds']=[0,0,10,11]
        client=Client();self.addCleanup(client.close);client.initialize()
        with tempfile.TemporaryDirectory() as root:
            s=dict(session_root=root,session_id='layout');client.success('session.create',**s,request_id='create',document=d)
            self.assertEqual(client.success('assist.layout',document=d,options=o),self.plan(d,o))
            a=dict(type='edit',operations=[dict(op='assist_layout',options=o)])
            result=client.success('session.apply',**s,request_id='arrange',expected_revision=0,action=a)
            self.assertEqual(result['document'],self.edit(d,dict(op='assist_layout',options=o)))
            self.assertTrue(client.success('session.apply',**s,request_id='arrange',expected_revision=0,action=a)['replayed'])
            undone=client.success('session.apply',**s,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'];self.assertEqual(undone['items'],d['items'])
            bad=dict(o,bounds=[0,0,10,1]);failure=client.tool('session.apply',**s,request_id='bad',expected_revision=2,action=dict(type='edit',operations=[dict(op='assist_layout',options=bad)]))
            self.assertTrue(failure['isError']);self.assertEqual(client.success('session.read',**s)['document'],undone)
            self.assertTrue(client.success('session.verify',**s)['valid'])
