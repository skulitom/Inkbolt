"""Exact rational hierarchy oracles, retained controls, and shared-layout pixels."""
import base64
import copy
from fractions import Fraction as F
import json
import tempfile
import unittest

import test_editing_cli as editing
from test_mcp import Client


def product(a, b):
    a, b = list(map(F, a)), list(map(F, b))
    return [a[0]*b[0]+a[2]*b[1], a[1]*b[0]+a[3]*b[1],
            a[0]*b[2]+a[2]*b[3], a[1]*b[2]+a[3]*b[3],
            a[0]*b[4]+a[2]*b[5]+a[4], a[1]*b[4]+a[3]*b[5]+a[5]]


def point(matrix, p):
    x, y = map(F, p)
    return [matrix[0]*x+matrix[2]*y+matrix[4], matrix[1]*x+matrix[3]*y+matrix[5]]


def hierarchy(n=10000., gap=.00390625, reflected=False):
    a = [n,n,n,n+gap,0.,0.]
    determinant = n*gap
    b = [(n+gap)/determinant,-n/determinant,-n/determinant,n/determinant,0.,0.]
    matrices = [[-1 if reflected else 1,0,0,1,30020 if reflected else -30000,-30000]]
    matrices += [m for _ in range(7) for m in (a,b)]
    items = [dict(id=f'g{i}', content=dict(type='group'), transform=m,
                  **({} if i == 0 else dict(parent=f'g{i-1}')))
             for i,m in enumerate(matrices)]
    exact = list(map(F, [1,0,0,1,0,0]))
    for m in matrices:
        exact = product(exact, m)
    items.append(dict(id='art', parent='g14', content=dict(type='vector',
        geometry=dict(shape='rect',x=30006.5,y=30006.5,width=5.75,height=5.75),
        fill=[17,53,199,255])))
    return dict(schema_version=2,id='hierarchy-precision',kind='vector',width=20,
                height=20,color_space='srgb',items=items), exact


class HierarchyPrecisionTests(unittest.TestCase):
    invoke = editing.EditingCliTests.invoke

    def inspect_art(self, source):
        report = self.invoke(dict(command='document.inspect', document=source))
        return next(i for i in report['items'] if i['id'] == 'art')

    def pixels(self, source, **options):
        result = self.invoke(dict(command='document.export', document=source, format='png', **options))
        return editing.png_pixels(base64.b64decode(result['data']))[:3]

    def test_near_inverse_hierarchies_match_independent_exact_coefficients_and_bounds(self):
        for n, gap in [(1000.,.00390625),(10000.,.03125),(10000.,.00390625),
                       (30000.,.015625),(32760.,.00390625)]:
            for reflected in (False, True):
                with self.subTest(n=n,gap=gap,reflected=reflected):
                    source, exact = hierarchy(n, gap, reflected)
                    info = self.inspect_art(source)
                    self.assertEqual(info['world_transform'], list(map(float,exact)))
                    corners = [point(exact,[x,y]) for x in [30006.5,30012.25]
                               for y in [30006.5,30012.25]]
                    bounds = [min(p[0] for p in corners),min(p[1] for p in corners),
                              max(p[0] for p in corners),max(p[1] for p in corners)]
                    for actual, wanted in zip(info['geometry_bounds'],bounds):
                        self.assertLessEqual(abs(F(actual)-wanted), F('1e-9'))

    def test_curve_coverage_matches_independently_placed_controls_at_all_output_densities(self):
        source, exact = hierarchy()
        controls = [[30006.125,30006.125],[30007.375,30002.25],[30010.625,30015.5],
                    [30011.875,30006.125],[30011.875,30014.],[30006.125,30014.]]
        def geometry(p):
            return dict(shape='path',commands=[dict(verb='move',to=p[0]),
                dict(verb='cubic',control1=p[1],control2=p[2],to=p[3]),
                dict(verb='line',to=p[4]),dict(verb='line',to=p[5]),dict(verb='close')])
        source['items'][-1]['content']['geometry'] = geometry(controls)
        reference = copy.deepcopy(source)
        reference['items'] = [copy.deepcopy(source['items'][-1])]
        reference['items'][0].pop('parent')
        reference['items'][0]['content']['geometry'] = geometry([
            list(map(float,point(exact,p))) for p in controls])
        for scale in (1,2,3,4):
            for antialias in ('coverage','supersample4'):
                options = dict(scale=scale,render_options=dict(antialias=antialias))
                self.assertEqual(self.pixels(source,**options),self.pixels(reference,**options))
        snapshot = json.loads(self.invoke(dict(command='document.export',document=source,
                                                format='snapshot'))['data'])
        self.assertEqual(snapshot['items'][-1]['content']['geometry'],geometry(controls))
        self.assertEqual([i['transform'] for i in snapshot['items'][:-1]],
                         [i['transform'] for i in source['items'][:-1]])

    def test_5000_shared_hierarchy_objects_keep_analytic_sparse_pixels(self):
        source, _ = hierarchy()
        leaf = source['items'].pop()
        source.update(resource_profile='large_vector',width=128,height=96)
        for i in range(5000):
            item = copy.deepcopy(leaf)
            item['id'] = f'art-{i}'
            item['content']['geometry'].update(x=30004+i%100,y=30004+i//100,width=.5,height=.5)
            source['items'].append(item)
        width,height,actual = self.pixels(source)
        self.assertEqual((width,height),(128,96))
        expected = bytearray(width*height*4)
        for y in range(4,54):
            for x in range(4,104):
                expected[(y*width+x)*4:(y*width+x+1)*4] = bytes([17,53,199,64])
        self.assertEqual(actual, bytes(expected))

    def test_distinct_chains_beyond_cache_capacity_preserve_every_world_matrix(self):
        source, exact = hierarchy()
        leaf = source['items'].pop()
        source['resource_profile'] = 'large_vector'
        for i in range(140):
            item = copy.deepcopy(leaf)
            item.update(id=f'art-{i}',transform=[1,0,0,1,i/128,-i/256])
            source['items'].append(item)
        report = self.invoke(dict(command='document.inspect',document=source))
        for info in report['items'][15:]:
            i = int(info['id'].split('-')[1])
            self.assertEqual(info['world_transform'], list(map(float,
                product(exact,[1,0,0,1,i/128,-i/256]))))

    def test_mcp_parent_revision_undo_and_retry_never_reuse_previous_placement(self):
        source, exact = hierarchy()
        client = Client();self.addCleanup(client.close);client.initialize()
        with tempfile.TemporaryDirectory() as root:
            session = dict(session_root=root,session_id='precision')
            original = client.success('session.create',**session,request_id='create',document=source)
            changed_root = [1,0,0,1,-29997,-29998]
            action = dict(type='edit',operations=[dict(op='transform',id='g0',matrix=changed_root)])
            edited = client.success('session.apply',**session,request_id='move',expected_revision=0,action=action)
            expected = product([1,0,0,1,3,2],exact)
            self.assertEqual(self.inspect_art(edited['document'])['world_transform'],list(map(float,expected)))
            restored = client.success('session.apply',**session,request_id='undo',expected_revision=1,
                                      action=dict(type='undo'))
            self.assertEqual(self.inspect_art(restored['document'])['world_transform'],list(map(float,exact)))
            self.assertEqual(restored['document']['items'], original['document']['items'])
            self.assertTrue(client.success('session.apply',**session,request_id='move',expected_revision=0,
                                           action=action)['replayed'])
            self.assertTrue(client.success('session.verify',**session)['valid'])


if __name__ == '__main__':
    unittest.main()
