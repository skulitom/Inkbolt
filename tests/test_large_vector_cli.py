"""Original large workloads checked against arithmetic, XML, PDF and SQLite readers."""
import base64
import copy
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

from test_cli import EXE
from test_editing_cli import png_pixels
from test_mcp import Client
from pdf_reader import Pdf

NS = '{http://www.w3.org/2000/svg}'


def cell(i):
    return dict(id=f'cell-{i}', content=dict(type='vector', geometry=dict(
        shape='rect', x=i % 100, y=i // 100, width=1, height=1),
        fill=[i % 100, i // 100, 73, 255]))


def workload(n=5000):
    return dict(schema_version=2, id='large-vector', kind='vector', width=100,
                height=50, color_space='srgb', resource_profile='large_vector',
                items=[cell(i) for i in range(n)])


class LargeVectorTests(unittest.TestCase):
    def invoke(self, request, error=None):
        p = subprocess.run([str(EXE)], input=json.dumps(request).encode(),
                           capture_output=True, timeout=90)
        self.assertEqual(p.stderr, b'')
        response = json.loads(p.stdout)
        self.assertEqual(p.returncode, 1 if error else 0, response.get('error', {'ok': response['ok'], 'response_bytes': len(p.stdout)}))
        if error:
            self.assertEqual(response['error']['code'], error, response)
            return response['error']
        self.assertTrue(response['ok'])
        return response['result']

    def edit(self, document, operations, error=None, **kw):
        return self.invoke(dict(command='document.edit', document=document,
                                expected_revision=document.get('revision', 0),
                                operations=operations, **kw), error)

    def export(self, document, format, **kw):
        return self.invoke(dict(command='document.export', document=document,
                                format=format, **kw))

    def test_profile_is_explicit_persisted_and_reversible_without_changing_artwork(self):
        request = dict(command='document.create', id='profile', kind='vector', width=4, height=3)
        standard = self.invoke(request)
        self.assertNotIn('resource_profile', standard)
        large = self.edit(standard, [dict(op='resource_profile', profile='large_vector')])['document']
        self.assertEqual(large, dict(standard, resource_profile='large_vector', revision=1))
        restored = self.edit(large, [dict(op='resource_profile', profile='standard')])['document']
        self.assertEqual(restored, dict(standard, revision=2))
        self.assertEqual(self.invoke(dict(command='document.inspect', document=large))['resource_profile'], 'large_vector')
        self.invoke(dict(request, resource_profile='invalid'), 'INVALID_REQUEST')
        self.invoke(dict(request, kind='raster', resource_profile='large_vector'), 'INVALID_DOCUMENT')
        self.invoke(dict(command='document.validate', document=dict(large, schema_version=1)), 'INVALID_DOCUMENT')
        changed = self.invoke(dict(command='document.diff', before=standard, after=large))
        self.assertIn('resource_profile', [v['field'] for v in changed['metadata']])

    def test_5000_objects_keep_exact_source_snapshot_svg_pdf_and_all_visible_pixels(self):
        source = workload()
        original = copy.deepcopy(source)
        document = self.invoke(dict(command='document.validate', document=source))
        snapshot = self.export(document, 'snapshot')['data']
        self.assertGreater(len(snapshot), 1024 * 1024)
        self.assertEqual(json.loads(snapshot), document)
        self.assertEqual(self.invoke(dict(command='document.validate', document=json.loads(snapshot))), document)
        svg = ET.fromstring(self.export(document, 'svg')['data'])
        rects = svg.findall('.//' + NS + 'rect')
        self.assertEqual(len(rects), 5000)
        for i, rect in enumerate(rects):
            self.assertEqual([float(rect.attrib[k]) for k in ['x', 'y', 'width', 'height']],
                             [i % 100, i // 100, 1, 1])
        pdf = Pdf(self.export(document, 'pdf'))
        paths = pdf.paths()
        self.assertEqual(len(paths), 5000)
        for i, path in enumerate(paths):
            self.assertEqual(path['path'][0], ('m', [[i % 100 * .75, i // 100 * .75]]))
            self.assertEqual(path['color'], [i % 100 / 255, i // 100 / 255, 73 / 255])
        png = self.export(document, 'png')
        width, height, pixels, _ = png_pixels(base64.b64decode(png['data']))
        self.assertEqual((width, height), (100, 50))
        self.assertEqual(pixels, b''.join(bytes([x, y, 73, 255]) for y in range(50) for x in range(100)))
        self.assertEqual(source, original)

    def test_large_svg_file_import_preserves_source_and_requires_the_profile(self):
        svg = '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50">' + ''.join(
            f'<rect id="cell-{i}" x="{i % 100}" y="{i // 100}" width="1" height="1" fill="rgb({i % 100},{i // 100},73)"/>'
            for i in range(5000)) + '</svg>'
        raw = svg.encode()
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'original.svg'
            source.write_bytes(raw)
            request = dict(command='svg.import', id='imported', source=dict(kind='file', source_path=str(source)))
            self.invoke(request, 'RESOURCE_LIMIT')
            result = self.invoke(dict(request, resource_profile='large_vector'))
            self.assertEqual(result['source']['sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(len(result['document']['items']), 5001)
            self.assertEqual(result['document']['resource_profile'], 'large_vector')
            self.assertEqual(len(result['mapping']), 5001)
            self.assertEqual(source.read_bytes(), raw)
            self.invoke(dict(request, resource_profile='large_vector', control=dict(timeout_ms=0)), 'TIMEOUT')
            self.assertEqual(source.read_bytes(), raw)

    def test_item_command_and_snapshot_limits_are_independent_and_defaults_stay_bounded(self):
        d = workload(257)
        standard = dict(d)
        standard.pop('resource_profile')
        self.invoke(dict(command='document.validate', document=standard), 'RESOURCE_LIMIT')
        self.invoke(dict(command='document.validate', document=d))
        self.invoke(dict(command='document.validate', document=workload(8193)), 'RESOURCE_LIMIT')
        d = workload(8192)
        self.invoke(dict(command='document.validate', document=d))
        commands = [dict(verb='move', to=[0, 0])] + [dict(verb='line', to=[i % 2, 1]) for i in range(4095)]
        d = workload(32)
        for item in d['items']:
            item['content']['geometry'] = dict(shape='path', commands=commands)
        self.invoke(dict(command='document.validate', document=d))
        too_many = copy.deepcopy(d)
        too_many['items'].append(dict(too_many['items'][0], id='extra'))
        self.invoke(dict(command='document.validate', document=too_many), 'RESOURCE_LIMIT')
        single = workload(1)
        single['items'][0]['content']['geometry'] = dict(shape='path', commands=commands + [dict(verb='close')])
        self.invoke(dict(command='document.validate', document=single), 'RESOURCE_LIMIT')
        d['items'] = d['items'][:16]
        cubic = dict(verb='cubic', to=[.12345678901234568, .9876543210987654], control1=[.12345678901234568, .9876543210987654], control2=[.12345678901234568, .9876543210987654])
        for item in d['items']:
            item['content']['geometry'] = dict(shape='path', commands=[commands[0]] + [cubic] * 4095)
        error = self.invoke(dict(command='document.validate', document=d), 'RESOURCE_LIMIT')
        self.assertIn('Snapshot', error['message'])

    def test_5000_id_group_edit_and_invalid_downgrade_are_atomic(self):
        d = self.invoke(dict(command='document.validate', document=workload()))
        grouped = self.edit(d, [dict(op='group', ids=[i['id'] for i in d['items']], new_id='all')])['document']
        self.assertEqual(len(grouped['items']), 5001)
        self.assertTrue(all(i['parent'] == 'all' for i in grouped['items'] if i['id'] != 'all'))
        self.edit(grouped, [dict(op='transform', id='all', matrix=[1, 0, 0, 1, 1, 0]),
                            dict(op='resource_profile', profile='standard')], 'RESOURCE_LIMIT')
        restored = self.edit(grouped, [dict(op='ungroup', id='all')])['document']
        self.assertEqual(restored['items'], d['items'])

    def test_large_session_mcp_history_retry_conflict_and_failed_downgrade_preserve_state(self):
        with tempfile.TemporaryDirectory() as temp:
            c = Client()
            self.addCleanup(c.close)
            c.initialize()
            context = dict(session_root=temp, session_id='large')
            first = c.success('session.create', **context, request_id='create', document=workload())
            initial = first['document']
            action = dict(type='edit', operations=[dict(op='transform', id='cell-4999', matrix=[1, 0, 0, 1, -.25, -.5])])
            updated = c.success('session.apply', **context, request_id='move', expected_revision=0, action=action)
            replay = c.success('session.apply', **context, request_id='move', expected_revision=0, action=action)
            self.assertTrue(replay['replayed'])
            self.assertEqual(updated['document'], replay['document'])
            conflict = c.tool('session.apply', **context, request_id='conflict', expected_revision=0, action=action)
            self.assertEqual(conflict['structuredContent']['error']['code'], 'REVISION_CONFLICT')
            failure = c.tool('session.apply', **context, request_id='small', expected_revision=1,
                             action=dict(type='edit', operations=[dict(op='resource_profile', profile='standard')]))
            self.assertEqual(failure['structuredContent']['error']['code'], 'RESOURCE_LIMIT')
            undo = c.success('session.apply', **context, request_id='undo', expected_revision=1, action=dict(type='undo'))
            self.assertEqual(undo['document'], dict(initial, revision=2))
            self.assertTrue(c.success('session.verify', **context)['valid'])
            db_path = Path(temp) / (hashlib.sha256(b'large').hexdigest() + '.sqlite3')
            with closing(sqlite3.connect(db_path)) as db:
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                for payload, digest in db.execute('SELECT payload,sha256 FROM states'):
                    self.assertGreater(len(payload), 768 * 1024)
                    self.assertEqual(hashlib.sha256(payload).hexdigest(), digest)
                    self.assertEqual(json.loads(payload)['document']['resource_profile'], 'large_vector')

    def test_20000_point_canvas_retains_physical_svg_and_pdf_size(self):
        d = self.invoke(dict(command='document.create', id='physical', kind='vector',
                             width=20000, height=8, resolution_ppi=72, resource_profile='large_vector'))
        d = self.edit(d, [dict(op='vector_canvas', action=dict(type='set', origin=[0, 0], size=[20000, 8], unit='pt'))])['document']
        d['items'] = [dict(id='far', content=dict(type='vector', geometry=dict(shape='rect', x=19998, y=2, width=1, height=3), fill=[3, 17, 89, 255]))]
        svg = ET.fromstring(self.export(d, 'svg')['data'])
        self.assertEqual(svg.attrib['width'], '20000pt')
        self.assertEqual(list(map(float, svg.attrib['viewBox'].split())), [0, 0, 20000, 8])
        pdf = Pdf(self.export(d, 'pdf'))
        page = pdf.pages[0]
        self.assertEqual(page['MediaBox'][2] * page['UserUnit'], 20000)
        self.assertEqual(page['MediaBox'][3] * page['UserUnit'], 8)
        png = self.export(d, 'png')
        w, h, pixels, _ = png_pixels(base64.b64decode(png['data']))
        self.assertEqual((w, h), (20000, 8))
        expected = bytearray(w * h * 4)
        for y in range(2, 5):
            expected[(y*w+19998)*4:(y*w+19999)*4] = bytes([3, 17, 89, 255])
        self.assertEqual(pixels, expected)

    def test_cancellation_and_render_budgets_leave_no_partial_artifact(self):
        d = workload()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            marker = root / 'cancel'
            marker.write_text('caller-owned')
            for format in ['png', 'svg', 'pdf', 'snapshot']:
                request = dict(command='document.publish', document=d, output=dict(
                    output_root=temp, file_name='blocked.' + ('json' if format == 'snapshot' else format), format=format),
                    control=dict(cancel_file=str(marker)))
                self.invoke(request, 'CANCELLED')
                self.invoke(dict(request, control=dict(timeout_ms=1)), 'TIMEOUT')
            self.assertEqual(list(root.iterdir()), [marker])
            self.assertEqual(marker.read_text(), 'caller-owned')
        self.invoke(dict(command='document.export', document=d, format='svg', control=dict(timeout_ms=1)), 'TIMEOUT')
        self.invoke(dict(command='document.render', document=d, control=dict(timeout_ms=1)), 'TIMEOUT')
        # Regional evaluation admits sparse scenes without raising either cap.
        self.invoke(dict(command='document.export', document=dict(d, width=1025, height=1024), format='png'), 'RESOURCE_LIMIT')
        dense = workload(100)
        dense.update(width=1000, height=1000)
        for item in dense['items']:
            item['content']['geometry'].update(x=0, y=0, width=1000, height=1000)
        self.invoke(dict(command='document.export', document=dense, format='png'), 'RESOURCE_LIMIT')


if __name__ == '__main__':
    unittest.main()
