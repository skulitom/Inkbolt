"""Original analytic ellipse/rectangle oracles; no external artwork or renderer."""
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest

from test_mcp import Client
import test_svg_import_cli as svg_import_tests
from test_svg_import_cli import svg


def point(center, radii, rotation, angle):
    x, y = radii[0]*math.cos(angle), radii[1]*math.sin(angle)
    c, s = math.cos(rotation), math.sin(rotation)
    return [center[0]+c*x-s*y, center[1]+s*x+c*y]


def cubic(points, t):
    weights = [(1-t)**3, 3*t*(1-t)**2, 3*t*t*(1-t), t**3]
    return [sum(w*p[i] for w, p in zip(weights, points)) for i in range(2)]


class SvgArcTests(unittest.TestCase):
    invoke = svg_import_tests.SvgImportTests.invoke
    imported = svg_import_tests.SvgImportTests.imported
    pixels = svg_import_tests.SvgImportTests.pixels
    item = svg_import_tests.SvgImportTests.item

    def path(self, data):
        return self.imported(svg(f'<path id="p" d="{data}"/>'))

    def commands(self, result, identifier='p'):
        return self.item(result, identifier)['content']['geometry']['commands']

    def assert_ellipse(self, result, center, radii, rotation, start, delta):
        record = result['approximations'][0]
        self.assertEqual(record['coordinate_space'], 'source_element_local_before_transforms')
        self.assertFalse(record['binary64_roundoff_included'])
        bound = record['arcs']['max_radial_error_local']
        self.assertGreater(bound, 0)
        self.assertLessEqual(bound, .001)
        commands = self.commands(result)
        previous = commands[0]['to']
        last_angle, travelled = start, 0
        c, s = math.cos(rotation), math.sin(rotation)
        segments = 0
        for command in commands[1:]:
            self.assertEqual(command['verb'], 'cubic')
            segments += 1
            controls = [previous, command['control1'], command['control2'], command['to']]
            for i in range(1, 65):
                p = cubic(controls, i/64)
                x, y = p[0]-center[0], p[1]-center[1]
                ux, uy = (c*x+s*y)/radii[0], (-s*x+c*y)/radii[1]
                angle = math.atan2(uy, ux)
                exact = point(center, radii, rotation, angle)
                self.assertLessEqual(math.dist(p, exact), bound+2e-10)
                increment = math.remainder(angle-last_angle, 2*math.pi)
                self.assertGreaterEqual(increment*delta, -1e-12)
                travelled += increment
                last_angle = angle
            previous = command['to']
        self.assertAlmostEqual(travelled, delta, delta=1e-10)
        self.assertEqual(segments, record['arcs']['cubic_segments'])
        self.assertLessEqual(abs(delta)/segments, math.pi/2+1e-14)

    def test_rotated_unequal_ellipses_all_flags_and_relative_coordinates(self):
        center, radii, start = [32, 24], [21, 5], .37
        for rotation in [0, .63, -1.1]:
            for delta in [1.8, -1.8, 4.7, -4.7, .0001, -.0001,
                          2*math.pi-.0001, -2*math.pi+.0001]:
                for relative in [False, True]:
                    with self.subTest(rotation=rotation, delta=delta, relative=relative):
                        p0 = point(center, radii, rotation, start)
                        p1 = point(center, radii, rotation, start+delta)
                        endpoint = [p1[i]-p0[i] for i in range(2)] if relative else p1
                        data = (f'M{p0[0]} {p0[1]} {"a" if relative else "A"}'
                                f'{radii[0]} {radii[1]} {math.degrees(rotation)} '
                                f'{int(abs(delta)>math.pi)} {int(delta>0)} {endpoint[0]} {endpoint[1]}')
                        result = self.path(data)
                        self.assertEqual(self.commands(result)[-1]['to'],
                                         [p0[i]+endpoint[i] for i in range(2)] if relative else p1)
                        self.assert_ellipse(result, center, radii, rotation, start, delta)

    def test_radius_correction_negative_radii_and_rotations(self):
        for radius in [1, -1, 5, -5, 1e-300]:
            result = self.path(f'M10 5 A{radius} {radius} 0 0 1 0 5')
            self.assert_ellipse(result, [5, 5], [5, 5], 0, 0, math.pi)
        self.assertEqual(self.path('M8 0 A8 3 450 0 1 0 8')['document'],
                         self.path('M8 0 A8 3 90 0 1 0 8')['document'])
        # Large coordinates still get the same absolute local error bound.
        result = self.path('M30000 0 A30000 30000 0 0 1 0 30000')
        self.assert_ellipse(result, [0, 0], [30000, 30000], 0, 0, math.pi/2)

    def test_compact_flags_repeated_groups_and_degenerate_reflection_resets(self):
        compact = self.path('M8 0 A8 8 0 010 8 8 8 0 018 0')
        spaced = self.path('M8 0 A8 8 0 0 1 0 8 A8 8 0 0 1 8 0')
        self.assertEqual(compact['document'], spaced['document'])
        result = self.path('M1 1 C2 3 4 5 6 6 A0 3 0 0 1 8 8 S10 9 12 8 A3 3 0 0 0 12 8 T16 8')
        cs = self.commands(result)
        self.assertEqual(cs[2], dict(verb='line', to=[8, 8]))
        self.assertEqual(cs[3]['control1'], [8, 8])
        self.assertEqual(cs[4]['control1'], [12, 8])
        receipt = result['approximations'][0]['arcs']
        self.assertEqual(receipt, dict(arc_commands=2, cubic_segments=0,
                                     zero_radius_lines=1, coincident_endpoints=1, max_radial_error_local=0))
        # A nondegenerate arc resets smooth cubic reflection too.
        result = self.path('M8 0 A8 8 0 0 1 0 8 S2 10 4 8')
        self.assertEqual(self.commands(result)[-1]['control1'], [0, 8])
        result = self.path('M8 0 L0 0 Z a8 8 0 0 1 -8 8')
        self.assertEqual(self.commands(result)[3], dict(verb='move', to=[8, 0]))
        self.assertEqual(self.commands(result)[-1]['to'], [0, 8])

    def test_invalid_flags_numbers_and_expansion_limits_fail_atomically(self):
        for flags in ['2 0', '-0 1', '+0 1', '.0 1', '0.0 1', '0 1e0', '0 1.0']:
            with self.subTest(flags=flags):
                error = self.imported(svg(f'<path d="M0 0 A8 8 0 {flags} 8 8"/>'), 1)
                self.assertEqual(error['code'], 'SVG_INVALID')
                self.assertNotIn('document', error)
        for data in ['M0 0 A8 8 0 0 1 8', 'M0 0 A8 8 1e999 0 1 8 8',
                     'M0 0 A1e-320 1e-320 0 0 1 8 8']:
            self.assertEqual(self.imported(svg(f'<path d="{data}"/>'), 1)['code'], 'SVG_INVALID')
        for data in ['M0 0 A1e300 8 0 0 1 8 8',
                     'M8 0 ' + 'A8 8 0 0 1 0 8 A8 8 0 0 1 8 0 '*1024]:
            self.assertEqual(self.imported(svg(f'<path d="{data}"/>'), 1)['code'], 'LIMIT_EXCEEDED')

    def test_circle_pixels_and_transformed_roundtrip(self):
        body = '<path id="p" d="M24 16 A8 8 0 0 1 8 16 A8 8 0 0 1 24 16 Z" fill="#2468ac"/>'
        result = self.imported(svg(body, 'width="32" height="32"'))
        width, height, pixels = self.pixels(result['document'])
        for y in range(height):
            for x in range(width):
                distance = math.hypot(x+.5-16, y+.5-16)
                color = pixels[(y*width+x)*4:(y*width+x+1)*4]
                if distance < 7: self.assertEqual(color, bytes([36, 104, 172, 255]))
                if distance > 9: self.assertEqual(color, bytes(4))
        self.assertAlmostEqual(sum(pixels[3::4])/255, math.pi*64, delta=2)
        transformed = self.imported(svg(f'<g transform="translate(1,2) scale(.7,1.1)">{body}</g>'))
        exported = self.invoke(dict(command='document.export', document=transformed['document'], format='svg'))['data']
        reimported = self.imported(exported)
        self.assertEqual(self.pixels(reimported['document']), self.pixels(transformed['document']))
        self.assertEqual(reimported['approximations'], [])

    def test_rounded_rect_auto_clamp_units_zero_and_unequal_radii(self):
        groups = [('rx="2"', 'rx="2" ry="2"'), ('ry="2"', 'rx="2" ry="2"'),
                  ('rx="auto" ry="2"', 'rx="2" ry="2"'),
                  ('rx="1pt"', 'rx="1.3333333333333333" ry="1.3333333333333333"'),
                  ('rx="100" ry="50"', 'rx="6" ry="4"'),
                  ('rx="10"', 'rx="6" ry="4"'),
                  ('rx="0" ry="2"', ''), ('rx="auto" ry="auto"', '')]
        for first, second in groups:
            with self.subTest(first=first):
                a = self.imported(svg(f'<rect id="r" x="4" y="5" width="12" height="8" {first}/>'))
                b = self.imported(svg(f'<rect id="r" x="4" y="5" width="12" height="8" {second}/>'))
                self.assertEqual(a['document'], b['document'])
        result = self.imported(svg('<rect id="r" x="4" y="5" width="12" height="8" rx="4" ry="2"/>'))
        cs = self.commands(result, 'r')
        self.assertEqual(cs[0], dict(verb='move', to=[8, 5]))
        self.assertEqual(cs[-1], dict(verb='close'))
        self.assertEqual(cs[-2]['to'], cs[0]['to'])
        receipt = result['approximations'][0]['arcs']
        self.assertEqual(receipt['arc_commands'], 4)
        self.assertLessEqual(receipt['max_radial_error_local'], .001)
        # Each emitted curve must lie on the analytic corner ellipse within its bound.
        centers = iter([[12, 7], [12, 11], [8, 11], [8, 7]])
        previous = cs[0]['to']
        for command in cs[1:]:
            if command['verb'] == 'line': center = next(centers)
            if command['verb'] == 'cubic':
                for j in range(33):
                    p = cubic([previous, command['control1'], command['control2'], command['to']], j/32)
                    angle = math.atan2((p[1]-center[1])/2, (p[0]-center[0])/4)
                    self.assertLessEqual(math.dist(p, point(center, [4, 2], 0, angle)), receipt['max_radial_error_local']+1e-12)
            if 'to' in command: previous = command['to']
        for attrs in ['rx="-1"', 'ry="-2"', 'rx="10%"']:
            self.imported(svg(f'<rect width="12" height="8" {attrs}/>'), 1)

    def test_clip_and_mask_definitions_report_approximations_and_match_direct_pixels(self):
        shape = '<rect id="rounded" x="4" y="5" width="12" height="8" rx="4" ry="2" fill="white"/>'
        direct = self.imported(svg(shape))
        for definition, reference in [('clipPath', 'clip-path'), ('mask', 'mask')]:
            with self.subTest(definition=definition):
                attrs = 'maskUnits="userSpaceOnUse" x="0" y="0" width="32" height="24"' if definition == 'mask' else ''
                text = svg(f'<defs><{definition} id="cut" {attrs}>{shape}</{definition}></defs>'
                           f'<rect width="32" height="24" fill="white" {reference}="url(#cut)"/>')
                result = self.imported(text)
                self.assertEqual(len(result['approximations']), 1)
                self.assertEqual(result['approximations'][0]['source_id'], 'rounded')
                self.assertEqual(self.pixels(result['document']), self.pixels(direct['document']))

    def test_mcp_file_session_snapshot_edit_undo_and_capabilities(self):
        text = svg('<rect id="r" x="3" y="4" width="12" height="10" rx="2" ry="4"/>'
                   '<path id="p" d="M24 8 A4 4 0 1 1 20 4" fill="none" stroke="red"/>')
        client = Client(); self.addCleanup(client.close); client.initialize()
        with tempfile.TemporaryDirectory() as root:
            source = Path(root)/'source.svg'; source.write_bytes(text.encode())
            result = client.success('svg.import', id='imported', source=dict(kind='file', source_path=str(source)))
            self.assertEqual(result, self.imported(text))
            self.assertEqual(result['source']['sha256'], hashlib.sha256(source.read_bytes()).hexdigest())
            common = dict(session_root=root, session_id='arcs')
            client.success('session.create', **common, request_id='create', document=result['document'])
            client.success('session.apply', **common, request_id='move', expected_revision=0,
                           action=dict(type='edit', operations=[dict(op='transform', id=self.item(result, 'r')['id'], matrix=[1, 0, 0, 1, 2, 1])]))
            undone = client.success('session.apply', **common, request_id='undo', expected_revision=1, action=dict(type='undo'))
            self.assertEqual(self.pixels(undone['document']), self.pixels(result['document']))
            snapshot = client.success('document.export', document=undone['document'], format='snapshot')['data']
            self.assertEqual(self.invoke(dict(command='document.validate', document=json.loads(snapshot))), undone['document'])
            self.assertEqual(source.read_bytes(), text.encode())
        caps = client.success('capabilities')['svg_import']
        self.assertIn('Aa', caps['path_commands'])
        self.assertEqual(caps['arcs']['max_radial_error_local'], .001)
        self.assertTrue(caps['rounded_rectangles'])


if __name__ == '__main__':
    unittest.main()
