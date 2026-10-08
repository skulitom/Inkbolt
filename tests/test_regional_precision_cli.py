"""Rational placements, analytic coverage and independently composited sparse scenes."""
import base64
import copy
import hashlib
from fractions import Fraction as F
import json
import math
import unittest

from test_editing_cli import png_pixels
import test_large_vector_cli as large
from test_images_cli import canonical


def commands(points):
    return [dict(verb='move' if i == 0 else 'line', to=list(map(float, p)))
            for i, p in enumerate(points)] + [dict(verb='close')]


def shape(geometry, id='art', color=None, **kw):
    return dict(id=id, content=dict(type='vector', geometry=geometry,
                fill=color or [40, 120, 220, 255]), **kw)


def rect(x=6.125, y=6.125, width=5.75, height=5.75):
    return dict(shape='rect', x=x, y=y, width=width, height=height)


def document(items, width=20, height=20, **kw):
    return dict(schema_version=2, id='regional-precision', kind='vector', width=width,
                height=height, color_space='srgb', resource_profile='large_vector', items=items, **kw)


def inverse_shear(points, origin, scale):
    anchor = F('6.125')
    matrix = [scale, scale, -scale, 1-scale, anchor, anchor-origin]
    local = []
    for x, y in points:
        dx, dy = x-anchor, y-anchor
        ly = origin+dy-dx
        local.append([ly+dx/scale, ly])
    mapped = [[matrix[0]*x+matrix[2]*y+matrix[4],
               matrix[1]*x+matrix[3]*y+matrix[5]] for x, y in local]
    assert mapped == points
    return local, list(map(float, matrix))


class RegionalPrecisionTests(unittest.TestCase):
    invoke = large.LargeVectorTests.invoke

    def pixels(self, source, **kw):
        out = self.invoke(dict(command='document.export', document=source, format='png', **kw))
        return png_pixels(base64.b64decode(out['data']))[:3]

    def test_exact_rational_extreme_affines_preserve_all_rectangle_coverage(self):
        points = [[F(x), F(y)] for x, y in [(6.125, 6.125), (11.875, 6.125),
                                           (11.875, 11.875), (6.125, 11.875)]]
        reference = self.pixels(document([shape(dict(shape='path', commands=commands(points)))]))[2]
        integrated = self.pixels(document([shape(dict(shape='path', commands=commands(points)))]),
                                 render_options=dict(antialias='supersample4'))[2]
        for y in range(20):
            for x in range(20):
                overlap = lambda k: max(F(0), min(F('11.875'), k+1)-max(F('6.125'), k))
                wanted = int(255*overlap(x)*overlap(y)+F(1, 2))
                self.assertLessEqual(abs(integrated[(y*20+x)*4+3]-wanted), 1)
        tested = 0
        for origin in [-30000, -10000, 10000, 30000]:
            for s in [F(1, 1024), F(1), F(16), F(256), F(1024), F(2048), F(8192), F(32768),
                      F(-1, 1024), F(-1), F(-256), F(-8192)]:
                local, matrix = inverse_shear(points, origin, s)
                if max(abs(v) for p in local for v in p) > 32768:
                    continue
                with self.subTest(origin=origin, scale=s):
                    source = document([shape(dict(shape='path', commands=commands(local)), transform=matrix)])
                    before = copy.deepcopy(source)
                    self.assertEqual(self.pixels(source)[2], reference)
                    # The ordinary profile uses the same corrected coverage path.
                    self.assertEqual(self.pixels(dict(source, resource_profile='standard'))[2], reference)
                    self.assertEqual(source, before)
                    tested += 1
        self.assertGreaterEqual(tested, 40)

    def test_extreme_cubic_controls_nested_placement_and_clip_mask(self):
        points = [[F(x), F(y)] for x, y in [(6.125, 6.125), (7.375, 2.25),
                                           (10.625, 15.5), (11.875, 6.125),
                                           (11.875, 14), (6.125, 14)]]
        def curve(p):
            return dict(shape='path', commands=[dict(verb='move', to=list(map(float, p[0]))),
                dict(verb='cubic', control1=list(map(float, p[1])), control2=list(map(float, p[2])), to=list(map(float, p[3]))),
                dict(verb='line', to=list(map(float, p[4]))), dict(verb='line', to=list(map(float, p[5]))), dict(verb='close')])
        expected = self.pixels(document([shape(curve(points))]))
        local, matrix = inverse_shear(points, 30000, F(8192))
        source = document([shape(curve(local), transform=list(matrix))])
        self.assertEqual(self.pixels(source), expected)
        source['items'][0]['parent'] = 'group'
        source['items'][0]['transform'][4] -= 1.5
        source['items'][0]['transform'][5] += 1.5
        source['items'].append(dict(id='group', transform=[1, 0, 0, 1, 1.5, -1.5], content=dict(type='group')))
        self.assertEqual(self.pixels(source), expected)
        # This takes the separate geometry-mask route and bypasses regional evaluation.
        clipped = document([shape(rect(0, 0, 20, 20), clip=dict(
            geometry=curve(local), transform=matrix, enabled=True))])
        actual = self.pixels(clipped)
        self.assertEqual(actual[:2], expected[:2])
        self.assertLessEqual(max(abs(a-b) for a, b in zip(actual[2], expected[2])), 1)

    def test_object_and_document_stroke_placements_use_output_space_coverage(self):
        source = document([shape(rect(16.005859375, 16.005859375, .005615234375, .005615234375),
                                         transform=[1024, 0, 0, 1024, -16384, -16384])])
        source['items'][0]['content']['fill'] = None
        source['items'][0]['content']['stroke'] = dict(color=[40, 120, 220, 255], width=.001953125)
        reference = document([shape(rect(6, 6, 5.75, 5.75))])
        reference['items'][0]['content'].update(fill=None, stroke=dict(color=[40, 120, 220, 255], width=2))
        self.assertEqual(self.pixels(source), self.pixels(reference))
        for scaling in ['object', 'document']:
            source['items'][0]['content']['stroke'].update(scaling=scaling, width=2 if scaling == 'document' else .001953125)
            self.assertEqual(self.pixels(source), self.pixels(reference))

    def test_ellipse_small_local_radii_and_large_centers_keep_coverage(self):
        for scale, center in [(F(2048), F(16)), (F(1024), F(16)), (F(1, 1024), F(16000))]:
            world_center = F(10)
            radius = F(13, 4)
            local = dict(shape='ellipse', cx=float(center), cy=float(center), rx=float(radius/scale), ry=float(radius/scale))
            matrix = [float(scale), 0, 0, float(scale), float(world_center-scale*center), float(world_center-scale*center)]
            source = document([shape(local, transform=matrix)])
            reference = document([shape(dict(shape='ellipse', cx=10, cy=10, rx=3.25, ry=3.25))])
            for aa in ['coverage', 'supersample4']:
                options = dict(render_options=dict(antialias=aa))
                actual = self.pixels(source, **options)[2]
                self.assertEqual(actual, self.pixels(reference, **options)[2])
                if aa == 'supersample4':
                    self.assertLess(abs(sum(actual[3::4])/255-math.pi*3.25**2), .15)

    def test_image_footprints_match_independent_placed_polygon_coverage(self):
        rgba = bytes([40, 120, 220, 255])
        asset = dict(width=1, height=1, sha256=hashlib.sha256(canonical(1, 1, rgba)).hexdigest(),
                     storage=dict(type='embedded', rgba_hex=rgba.hex()))
        for s in [F(1, 1024), F(1), F(8192), F(32768)]:
            matrix = [s, s, -s, 1-s, F('6.123456789'), F('6.234567891')]
            # Independent rational placement of the four image-frame corners.
            points = [[matrix[0]*x+matrix[2]*y+matrix[4], matrix[1]*x+matrix[3]*y+matrix[5]]
                      for x, y in [(0, 0), (1, 0), (1, 1), (0, 1)]]
            # The reference's factor-two placement keeps its source controls bounded.
            reference = document([shape(dict(shape='path', commands=commands([[x/2, y/2] for x, y in points])),
                                        transform=[2, 0, 0, 2, 0, 0])])
            source = document([dict(id='image', transform=list(map(float, matrix)),
                content=dict(type='image', asset_id='source', width=1, height=1))], assets={'source': asset})
            for aa in ['coverage', 'supersample4']:
                options = dict(render_options=dict(antialias=aa))
                actual, expected = self.pixels(source, **options), self.pixels(reference, **options)
                self.assertEqual(actual[:2], expected[:2])
                self.assertLessEqual(max(abs(a-b) for a, b in zip(actual[2], expected[2])), 1)

    def test_original_sparse_workload_and_large_preview_match_analytic_pixels(self):
        source = large.workload()
        source.update(width=128, height=96)
        for i, item in enumerate(source['items']):
            item['content']['geometry'].update(x=8+i % 100, y=8+i//100, width=.5, height=.5)
        for size in [(128, 96), (1024, 1024)]:
            with self.subTest(size=size):
                d = dict(source, width=size[0], height=size[1])
                w, h, rgba = self.pixels(d)
                expected = bytearray(w*h*4)
                for i in range(5000):
                    offset = ((8+i//100)*w+8+i % 100)*4
                    expected[offset:offset+4] = bytes([i % 100, i//100, 73, 64])
                self.assertEqual(rgba, bytes(expected))
        self.assertEqual(len(source['items']), 5000)

    def test_regional_order_gradients_opacity_strokes_curves_and_viewports(self):
        stops = [dict(offset=0, color=[255, 0, 0, 190]), dict(offset=1, color=[0, 0, 255, 230])]
        group = dict(id='group', transform=[1, .25, -.25, 1, 17, 6], content=dict(type='group'))
        curve = dict(shape='path', commands=[dict(verb='move', to=[-7, 2]),
            dict(verb='cubic', control1=[-20, -20], control2=[30, 25], to=[17, 2]),
            dict(verb='line', to=[-7, 8]), dict(verb='close')])
        items = [shape(rect(0, 0, 48, 32), 'back', [15, 80, 130, 180]),
                 shape(curve, 'curve', parent='group', opacity=.65, fill_opacity=.7),
                 shape(dict(shape='ellipse', cx=12, cy=12, rx=6, ry=10), 'oval', opacity=.5),
                 group,
                 shape(rect(-5, -6, 22, 17), 'child', parent='group', opacity=.6)]
        items[1]['content']['stroke'] = dict(width=1.25, color=[180, 20, 150, 240], scaling='document')
        items[4]['content']['fill'] = dict(type='linear', start=[-5, 0], end=[17, 0], stops=stops)
        source = document(items, 48, 32)
        original = copy.deepcopy(source)
        for aa in ['none', 'coverage', 'supersample2', 'supersample4']:
            for isolated in [True, False]:
                source['items'][3]['content']['isolated'] = isolated
                options = dict(render_options=dict(antialias=aa, padding=3, crop_to_canvas=False))
                actual = self.pixels(source, **options)
                expected = self.pixels(dict(source, resource_profile='standard'), **options)
                self.assertEqual(actual[:2], expected[:2])
                self.assertLessEqual(max(abs(a-b) for a, b in zip(actual[2], expected[2])), 1)
        source['items'][3]['visible'] = False
        self.assertEqual(self.pixels(source), self.pixels(dict(source, resource_profile='standard')))
        # Output-space operations never replace stored controls or the snapshot.
        validated = self.invoke(dict(command='document.validate', document=original))
        snapshot = self.invoke(dict(command='document.export', document=validated, format='snapshot'))
        self.assertEqual(json.loads(snapshot['data']), validated)

    def test_dense_work_and_incompatible_scene_keep_explicit_processing_limits(self):
        dense = document([shape(rect(0, 0, 1024, 1024), str(i)) for i in range(100)], 1024, 1024)
        for method in ['document.render', 'document.export']:
            request = dict(command=method, document=dense)
            if method == 'document.export': request['format'] = 'png'
            self.invoke(request, 'RESOURCE_LIMIT')
        # Group opacity changes the composition algebra and must use its buffer.
        ordinary = document([dict(id='g', opacity=.5, content=dict(type='group')),
                             shape(rect(), parent='g')])
        self.assertEqual(self.pixels(ordinary), self.pixels(dict(ordinary, resource_profile='standard')))
        sparse = large.workload()
        sparse.update(width=1024, height=1024)
        sparse['items'][0]['clip'] = dict(geometry=rect(0, 0, 100, 50))
        self.invoke(dict(command='document.export', document=sparse, format='png'), 'RESOURCE_LIMIT')
