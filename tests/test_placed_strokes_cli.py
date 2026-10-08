"""Analytic cubic length, scaled source controls, independent delivery and history."""
import base64
import copy
import json
from pathlib import Path
import tempfile
import unittest

import test_large_vector_cli as large
from test_editing_cli import png_pixels
from test_mcp import Client
from cmyk_fixtures import cmyk_profile
from test_profiles_cli import embedded
from test_proof_cli import scalar
from test_vector_plates_cli import color
from pdf_reader import Pdf


def arch(scale=1, span=6, width=2, origin=0, reflection=False, scaling='object'):
    points = [[origin, origin], [origin, origin+span/scale],
              [origin+span/scale, origin+span/scale], [origin+span/scale, origin]]
    geometry = dict(shape='path', commands=[dict(verb='move', to=points[0]),
        dict(verb='cubic', control1=points[1], control2=points[2], to=points[3])])
    matrix = [-scale if reflection else scale, 0, 0, scale,
              6+span+scale*origin if reflection else 6-scale*origin, 6-scale*origin]
    stroke = dict(width=width/scale if scaling == 'object' else width,
                  color=[40, 120, 220, 255], scaling=scaling)
    item = dict(id='curve', transform=matrix, content=dict(type='vector',
                geometry=geometry, fill=None, stroke=stroke))
    return dict(schema_version=2, id='placed-stroke', kind='vector', width=20, height=20,
                color_space='srgb', resource_profile='large_vector', items=[item])


class PlacedStrokeTests(unittest.TestCase):
    invoke = large.LargeVectorTests.invoke

    def pixels(self, document, **kw):
        out = self.invoke(dict(command='document.export', document=document, format='png', **kw))
        return png_pixels(base64.b64decode(out['data']))[:3]

    def assertPixels(self, actual, expected, tolerance=1):
        self.assertEqual(actual[:2], expected[:2])
        self.assertLessEqual(max(abs(a-b) for a, b in zip(actual[2], expected[2])), tolerance)

    def expand(self, document):
        return self.invoke(dict(command='document.edit', document=document,
            expected_revision=document.get('revision', 0), operations=[dict(op='stroke_expand',
                id='curve', fill_id='centerline', stroke_id='outline')]))

    def test_magnified_cubic_matches_placed_reference_and_exact_tube_area(self):
        # x=6+18t^2-12t^3, y=6+18t-18t^2. Speed is exactly
        # 18(2t^2-2t+1), so the length is 12 and the width-two butt tube area is 24.
        for scaling in ['object', 'document']:
            for factor in [1, 64, 256, 1024]:
                for reflection in [False, True]:
                    source = arch(factor, origin=16, reflection=reflection, scaling=scaling)
                    reference = arch(reflection=reflection, scaling=scaling)
                    before = copy.deepcopy(source)
                    for aa in ['coverage', 'supersample4']:
                        options = dict(render_options=dict(antialias=aa))
                        actual = self.pixels(source, **options)
                        self.assertPixels(actual, self.pixels(reference, **options))
                        if aa == 'supersample4':
                            self.assertLess(abs(sum(actual[2][3::4])/255-24), .08)
                    self.assertEqual(source, before)
        # A shrinking placement retains the more accurate declared local bound.
        actual = self.pixels(arch(1/256, origin=16), render_options=dict(antialias='supersample4'))
        self.assertLess(abs(sum(actual[2][3::4])/255-24), .08)

    def test_maximum_scale_and_internal_refinement_below_saved_tolerance_floor(self):
        source = arch(32768, span=64, width=40, origin=.5)
        reference = arch(span=64, width=40)
        source.update(width=100, height=100)
        reference.update(width=100, height=100)
        source['items'][0]['content']['stroke']['curve_tolerance'] = 1e-7
        self.assertPixels(self.pixels(source, render_options=dict(antialias='supersample4')),
                          self.pixels(reference, render_options=dict(antialias='supersample4')))
        expanded = self.expand(source)
        detail = expanded['changes'][0]['details']
        self.assertEqual(detail['curve_tolerance'], 1e-7)
        self.assertGreater(detail['evaluated_curve_tolerance'], 0)
        self.assertLess(detail['evaluated_curve_tolerance'], 1e-7)
        self.assertEqual(detail['outline_resolution'], 16)
        bad = copy.deepcopy(source)
        bad['items'][0]['content']['stroke']['curve_tolerance'] = 1e-8
        self.invoke(dict(command='document.validate', document=bad), 'INVALID_DOCUMENT')

    def test_dash_profiles_arrows_rounds_and_brushes_follow_scaled_original_controls(self):
        styles = [dict(cap='round', join='round'),
                  dict(dash=dict(array=[3, 2], offset=-.5), cap='round', width_profile=[[0, .5], [.5, 1.5], [1, 1]]),
                  dict(start_arrow=dict(kind='triangle', length=2, width=2), end_arrow=dict(kind='ellipse', length=2.5, width=2)),
                  dict(brush=dict(motif=dict(shape='rect', x=-.2, y=-.3, width=.4, height=.6), spacing=1.5, phase=.25))]
        for style in styles:
            reference = arch()
            reference['items'][0]['content']['stroke'].update(copy.deepcopy(style))
            source = arch(1024, origin=16)
            local = copy.deepcopy(style)
            if 'dash' in local:
                local['dash']['array'] = [v/1024 for v in local['dash']['array']]
                local['dash']['offset'] /= 1024
            for field in ['start_arrow', 'end_arrow']:
                if field in local:
                    for dimension in ['length', 'width']: local[field][dimension] /= 1024
            source['items'][0]['content']['stroke'].update(local)
            self.assertPixels(self.pixels(source, render_options=dict(antialias='supersample4')),
                              self.pixels(reference, render_options=dict(antialias='supersample4')))

    def test_nested_shear_and_reflection_keep_document_scaled_centerline(self):
        source = arch(1024, origin=16, scaling='document')
        parent = [1.25, .5, -.25, .75, 2, 1]
        source['items'][0]['parent'] = 'group'
        source['items'].append(dict(id='group', content=dict(type='group'), transform=parent))
        reference = arch(scaling='document')
        # Independently apply the parent's affine equations to the known world cubic.
        points = [[6, 6], [6, 12], [12, 12], [12, 6]]
        mapped = [[parent[0]*x+parent[2]*y+parent[4], parent[1]*x+parent[3]*y+parent[5]] for x, y in points]
        reference['items'][0]['transform'] = [1, 0, 0, 1, 0, 0]
        reference['items'][0]['content']['geometry']['commands'] = [dict(verb='move', to=mapped[0]),
            dict(verb='cubic', control1=mapped[1], control2=mapped[2], to=mapped[3])]
        self.assertPixels(self.pixels(source, scale=4), self.pixels(reference, scale=4))

    def test_expansion_svg_pdf_and_all_render_scales_share_the_refined_outline(self):
        source = arch(1024, origin=16)
        source['items'][0]['content']['stroke']['curve_tolerance'] = .25
        original = copy.deepcopy(source)
        expanded = self.expand(source)['document']
        svg = self.invoke(dict(command='document.export', document=source, format='svg'))
        imported = self.invoke(dict(command='svg.import', id='imported', source=dict(kind='text', text=svg['data']),
                                   resource_profile='large_vector'))['document']
        for scale in [1, 2, 4]:
            for aa in ['coverage', 'supersample4']:
                options = dict(scale=scale, render_options=dict(antialias=aa))
                actual = self.pixels(source, **options)
                self.assertPixels(actual, self.pixels(expanded, **options), 0)
                self.assertPixels(actual, self.pixels(imported, **options), 0)
        reference = arch()
        reference['items'][0]['content']['stroke']['curve_tolerance'] = .25
        actual = Pdf(self.invoke(dict(command='document.export', document=source, format='pdf'))).paths()
        expected = Pdf(self.invoke(dict(command='document.export', document=reference, format='pdf'))).paths()
        self.assertEqual(len(actual), len(expected))
        for a, b in zip(actual, expected):
            self.assertEqual(len(a['path']), len(b['path']))
            for (va, pa), (vb, pb) in zip(a['path'], b['path']):
                self.assertEqual(va, vb)
                for qa, qb in zip(pa, pb):
                    self.assertLessEqual(max(abs(x-y) for x, y in zip(qa, qb)), 1e-8)
        self.assertEqual(source, original)

    def test_shared_mask_and_native_ink_planes_use_the_same_refinement(self):
        source, reference = arch(1024, origin=16), arch()
        options = dict(profile=embedded(cmyk_profile()), antialias='supersample4')
        for document in [source, reference]:
            document['swatches'] = dict(ink=color([0, 1, 0, 0]))
            document['items'][0]['content']['stroke']['color'] = dict(swatch='ink')
        a = self.invoke(dict(command='document.prepress', document=source, options=options))
        b = self.invoke(dict(command='document.prepress', document=reference, options=options))
        for pa, pb in zip(a['plates'], b['plates']):
            self.assertEqual(scalar(pa)[:3], scalar(pb)[:3])
        def masked(d):
            result = copy.deepcopy(d)
            result['items'][0]['parent'] = 'source'
            result['items'][0]['content']['stroke']['color'] = [255]*4
            result['items'] += [dict(id='source', content=dict(type='mask_source')),
                dict(id='owner', artwork_mask=dict(source='source', region=[0, 0, 20, 20], mode='alpha'),
                     content=dict(type='vector', geometry=dict(shape='rect', x=0, y=0, width=20, height=20), fill=[40,120,220,255]))]
            return result
        self.assertPixels(self.pixels(masked(source), scale=4), self.pixels(masked(reference), scale=4))

    def test_refined_geometry_limits_and_cancelled_publication_leave_no_artifacts(self):
        source = arch(1024, origin=16)
        source['items'] = [dict(copy.deepcopy(source['items'][0]), id='curve-'+str(i)) for i in range(256)]
        error = self.invoke(dict(command='document.validate', document=source), 'RESOURCE_LIMIT')
        self.assertIn('stroke-outline', error['message'])
        with tempfile.TemporaryDirectory() as temp:
            request = dict(command='document.publish', document=source, output=dict(output_root=temp, file_name='too-large.png', format='png'))
            self.invoke(request, 'RESOURCE_LIMIT')
            request['document'] = arch(1024, origin=16)
            request['control'] = dict(timeout_ms=0)
            self.invoke(request, 'TIMEOUT')
            self.assertEqual(list(Path(temp).iterdir()), [])

    def test_agent_history_retains_saved_tolerance_and_original_cubic_handles(self):
        with tempfile.TemporaryDirectory() as temp:
            c = Client()
            self.addCleanup(c.close)
            c.initialize()
            context = dict(session_root=temp, session_id='stroke')
            initial = c.success('session.create', **context, request_id='create', document=arch(1024, origin=16))['document']
            action = dict(type='edit', operations=[dict(op='stroke_expand', id='curve', fill_id='centerline', stroke_id='outline')])
            changed = c.success('session.apply', **context, request_id='expand', expected_revision=0, action=action)
            self.assertEqual(changed['document']['items'][1]['content']['geometry'], initial['items'][0]['content']['geometry'])
            replay = c.success('session.apply', **context, request_id='expand', expected_revision=0, action=action)
            self.assertTrue(replay['replayed'])
            undone = c.success('session.apply', **context, request_id='undo', expected_revision=1, action=dict(type='undo'))['document']
            self.assertEqual(undone['items'], initial['items'])
            self.assertTrue(c.success('session.verify', **context)['valid'])

    def test_distinct_authored_knots_below_coordinate_precision_fail_explicitly(self):
        source = arch()
        item = source['items'][0]
        item['transform'] = [1, 0, 0, 1, 0, 0]
        item['content']['geometry'] = dict(shape='path', commands=[
            dict(verb='move', to=[30000, 10]), dict(verb='line', to=[30001, 10])])
        item['content']['stroke']['width_profile'] = [[0, 1], [.5, 1], [.5000000000000001, 2], [1, 2]]
        error = self.invoke(dict(command='document.validate', document=source), 'UNSUPPORTED')
        self.assertIn('coordinate precision', error['message'])
        caps = self.invoke(dict(command='capabilities'))['vector_strokes']['curve_tolerance']
        self.assertEqual(caps['outline_resolution'], 16)
        self.assertTrue(caps['stored_controls_preserved'])
