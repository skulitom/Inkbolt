"""Workspace and pinned-reference contracts checked through real CLI/MCP processes."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest

from test_cli import EXE
from test_agent_discovery import catalog
from test_images_cli import png
from test_mcp import Client
from synthetic_font import geometric_font


class AgentWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def cli(self, command, *, scoped=True, error=None, **arguments):
        args = ['--workspace', str(self.root)] if scoped else []
        p = subprocess.run([str(EXE), *args], input=json.dumps(dict(command=command, **arguments)).encode(), capture_output=True, timeout=20)
        self.assertEqual(p.stderr, b'')
        response = json.loads(p.stdout)
        self.assertEqual(p.returncode, int(error is not None), response)
        if error:
            self.assertEqual(response['error']['code'], error, response)
            return response['error']
        self.assertTrue(response['ok'], response)
        return response['result']

    def document(self):
        return self.cli('document.create', id='original', kind='vector', width=2, height=2)

    def save(self, doc=None, **kw):
        return self.cli('session.create', session_id='work', request_id='create', document=doc or self.document(), **kw)

    def ref(self, revision=0):
        return dict(session_id='work', revision=revision)

    def test_defaults_catalog_and_read_only_initialization(self):
        self.assertEqual(list(self.root.iterdir()), [])
        with closing(Client(('--tools', 'core'), workspace=self.root)) as c:
            c.initialize()
            tools = catalog(c)
            self.assertLessEqual(len(json.dumps(tools).encode()), 96 * 1024)
            create = next(t for t in tools if t['name'] == 'inkbolt_session_create')['inputSchema']
            self.assertNotIn('session_root', create['required'])
            ref = create['properties']['document']['anyOf'][1]
            self.assertNotIn('session_root', ref['required'])
            caps = c.tool('run', command='capabilities', arguments={})['structuredContent']['result']
            self.assertEqual(caps, self.cli('capabilities'))
            self.assertTrue(Path(caps['workspace']['root']).samefile(self.root))
            self.assertEqual(list(self.root.iterdir()), [])
            outline = c.success('schema.lookup', name='session.create')
            self.assertEqual(outline['detail'], 'outline')
            self.assertFalse(next(f for f in outline['fields'] if f['name'] == 'session_root')['required'])
            full = c.success('schema.lookup', name='session.create', full=True)
            self.assertEqual(full['schema_bytes'], len(json.dumps(full['schema'], separators=(',', ':'), ensure_ascii=False).encode()))
            state = c.success('session.create', session_id='work', request_id='create', document=self.document())
            self.assertEqual(state, self.cli('session.receipt', session_id='work', request_id='create') | {'replayed': False})
            for field, folder in [('asset_root', 'assets'), ('font_root', 'fonts')]:
                self.assertEqual(Path(state['resources'][field]), Path(caps['workspace']['root']) / '.inkbolt' / folder)
            self.assertTrue((self.root / '.inkbolt/sessions').is_dir())
            self.assertFalse((self.root / '.inkbolt/assets').exists())

    def test_historical_references_render_compare_and_publish_without_mutation(self):
        original = self.save()['document']
        item = dict(id='square', content=dict(type='vector', geometry=dict(shape='rect', x=0, y=0, width=2, height=2), fill=[10, 90, 210, 255]))
        edited = self.cli('session.apply', session_id='work', request_id='add', expected_revision=0,
                          action=dict(type='edit', operations=[dict(op='add', item=item)]))['document']
        with closing(Client(('--tools', 'core'), workspace=self.root)) as c:
            c.initialize()
            self.assertEqual(c.success('document.render', document=self.ref())['data'], bytes(16).hex())
            self.assertEqual(c.success('document.render', document=self.ref(1))['data'], bytes([10, 90, 210, 255] * 4).hex())
            for revision, expected in [(0, original), (1, edited)]:
                self.assertEqual(self.cli('document.validate', document=self.ref(revision)), expected)
            compared = c.tool('run', command='document.diff', arguments=dict(before=self.ref(), after=self.ref(1), compare_pixels=True))['structuredContent']['result']
            self.assertTrue(compared['changed'])
            self.assertEqual(compared, self.cli('document.diff', before=original, after=edited, compare_pixels=True))
        published = self.cli('document.publish', document=self.ref(), output=dict(file_name='old.json', format='snapshot'))
        data = (self.root / 'old.json').read_bytes()
        self.assertEqual(json.loads(data), original)
        self.assertEqual(hashlib.sha256(data).hexdigest(), published['sha256'])
        self.cli('document.publish', document=self.ref(1), output=dict(file_name='old.json', format='snapshot'), error='OUTPUT_EXISTS')
        self.assertEqual((self.root / 'old.json').read_bytes(), data)
        proposed = self.cli('document.edit', document=self.ref(), expected_revision=0, operations=[dict(op='add', item=item)])
        self.assertEqual(proposed['document'], edited)
        self.assertEqual(self.cli('session.read', session_id='work')['current_revision'], 1)

    def test_saved_resources_and_explicit_overrides_preserve_sources(self):
        source = self.root / 'source.png'
        pixels = bytes([21, 61, 141, 255] * 4)
        original = png(2, 2, pixels)
        source.write_bytes(original)
        imported = self.cli('asset.import', source_path='source.png', store_root='chosen-assets')['asset']
        doc = self.document()
        doc['assets'] = {'original': imported}
        doc['items'] = [dict(id='image', content=dict(type='image', asset_id='original', width=2, height=2))]
        saved = self.save(doc, resources=dict(asset_root='chosen-assets', font_root=None))
        self.assertTrue(Path(saved['resources']['asset_root']).samefile(self.root / 'chosen-assets'))
        self.assertEqual(self.cli('document.render', document=self.ref())['data'], pixels.hex())
        self.cli('document.render', document=self.ref(), asset_root=None, error='ASSET_ROOT_REQUIRED')
        self.cli('document.render', document=self.ref(), asset_root='missing-assets', error='ASSET_MISSING')
        font_bytes = geometric_font()
        (self.root / 'font.ttf').write_bytes(font_bytes)
        (self.root / 'license.txt').write_text('Original test fixture, permitted for all use.', encoding='utf-8')
        font = self.cli('font.import', source_path='font.ttf', license_path='license.txt')
        self.assertTrue(self.cli('font.verify', font=font)['valid'])
        self.assertTrue((self.root / '.inkbolt/fonts').is_dir())
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual((self.root / 'font.ttf').read_bytes(), font_bytes)

    def test_explicit_roots_without_workspace_and_strict_reference_errors(self):
        doc = self.document()
        self.save(doc, scoped=False, session_root=str(self.root), resources=dict(asset_root=None, font_root=None))
        reference = dict(self.ref(), session_root=str(self.root))
        self.assertEqual(self.cli('document.validate', scoped=False, document=reference), doc)
        ref_schema = self.cli('schema.lookup', scoped=False, name='document.render', full=True)['schema']['properties']['document']['anyOf'][1]
        self.assertIn('session_root', ref_schema['required'])
        for ref in [dict(session_id='work'), dict(reference, revision=-1), dict(reference, revision='0'),
                    dict(reference, extra=1), dict(reference, session_root=None)]:
            self.cli('document.validate', document=ref, error='INVALID_REQUEST')
        self.cli('document.validate', scoped=False, document=self.ref(), error='INVALID_REQUEST')
        self.cli('document.validate', scoped=False, document=dict(reference, revision=999), error='REVISION_NOT_FOUND')
        self.cli('document.edit', scoped=False, document=reference, expected_revision=1, operations=[dict(op='remove', id='absent')], error='REVISION_CONFLICT')
        self.assertFalse((self.root / '.inkbolt').exists())

    def test_paths_reject_escape_but_metadata_is_literal(self):
        paths = ['../outside.png', 'safe/../../outside.png', 'source.png:stream', str(self.root.parent / 'outside.png')]
        if os.name == 'nt':
            paths += ['C:relative.png', '\\root-relative.png', '\\\\server\\share\\source.png']
        for path in paths:
            expected = 'PATH_OUTSIDE_WORKSPACE' if path == str(self.root.parent / 'outside.png') else 'INVALID_PATH'
            self.cli('asset.import', source_path=path, error=expected)
        doc = self.document()
        doc['metadata'] = dict(private={'source_path': '../outside.png', 'session_root': 'C:unchanged'})
        self.assertEqual(self.cli('document.validate', document=doc)['metadata']['private'], doc['metadata']['private'])
        edited = self.cli('document.edit', document=doc, expected_revision=0, operations=[dict(op='metadata', value=doc['metadata'])])
        self.assertEqual(edited['document']['metadata']['private'], doc['metadata']['private'])
        (self.root / 'request.json').write_text(json.dumps(dict(command='document.validate', document=doc)), encoding='utf-8')
        p = subprocess.run([str(EXE), '--workspace', str(self.root), 'request.json'], capture_output=True, timeout=20)
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertEqual(json.loads(p.stdout)['result']['metadata']['private'], doc['metadata']['private'])

    def test_existing_link_escapes_are_resolved_before_any_output(self):
        with tempfile.TemporaryDirectory() as external:
            link = self.root / 'escape'
            if os.name == 'nt':
                # A junction tests reparse-point resolution without requiring symlink privileges.
                p = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), external], capture_output=True, timeout=10)
                self.assertEqual(p.returncode, 0, p.stderr)
            else:
                link.symlink_to(external, target_is_directory=True)
            doc = self.document()
            self.cli('document.publish', document=doc, output=dict(output_root='escape', file_name='must-not-exist.png', format='png'), error='PATH_OUTSIDE_WORKSPACE')
            self.cli('session.create', session_root='escape/missing', session_id='work', request_id='create', document=doc, error='PATH_OUTSIDE_WORKSPACE')
            self.cli('asset.import', source_path='escape/missing.png', error='PATH_OUTSIDE_WORKSPACE')
            self.assertEqual(list(Path(external).iterdir()), [])
            # Remove only the owned link, before either temporary directory is cleaned up.
            if os.name == 'nt': os.rmdir(link)
            else: link.unlink()

    def test_history_resource_checks_rollback_and_allow_explicit_repair(self):
        with tempfile.TemporaryDirectory() as external:
            store = self.root / '.inkbolt/sessions'
            original = self.save(scoped=False, session_root=str(store), resources=dict(asset_root=external))
            self.cli('document.render', document=self.ref(), error='PATH_OUTSIDE_WORKSPACE')
            self.cli('document.render', document=self.ref(), asset_root=None)
            self.cli('session.publish', session_id='work', expected_revision=0, output=dict(file_name='outside.png', format='png'), error='PATH_OUTSIDE_WORKSPACE')
            self.cli('session.apply', session_id='work', request_id='bad', expected_revision=0, action=dict(type='edit', operations=[dict(op='metadata', value={})]), error='PATH_OUTSIDE_WORKSPACE')
            self.assertEqual(self.cli('session.read', session_id='work')['current_revision'], 0)
            fixed = self.cli('session.apply', session_id='work', request_id='repair', expected_revision=0, action=dict(type='resources', resources={}))
            self.assertEqual(fixed['current_revision'], 1)
            self.cli('session.apply', session_id='work', request_id='undo', expected_revision=1, action=dict(type='undo'), error='PATH_OUTSIDE_WORKSPACE')
            self.cli('session.diff', session_id='work', from_revision=0, to_revision=1, compare_pixels=True, error='PATH_OUTSIDE_WORKSPACE')
            self.assertEqual(self.cli('session.read', session_id='work')['current_revision'], 1)
            self.assertTrue(self.cli('session.verify', session_id='work')['valid'])
            replay = self.cli('session.apply', session_id='work', request_id='repair', expected_revision=0, action=dict(type='resources', resources={}), control=dict(timeout_ms=0))
            self.assertTrue(replay['replayed'])
            self.assertEqual(replay['receipt'], fixed['receipt'])
            # Read-only receipt recovery remains possible even for old resource bindings.
            self.assertEqual(self.cli('session.receipt', session_id='work', request_id='create')['receipt'], original['receipt'])

    def test_reference_preparation_stays_off_mcp_reader_and_cancellation_is_safe(self):
        self.save()
        path = self.root / '.inkbolt/sessions' / (hashlib.sha256(b'work').hexdigest() + '.sqlite3')
        with closing(Client(('--tools', 'core'), workspace=self.root)) as c, closing(sqlite3.connect(path)) as db:
            c.initialize()
            db.execute('BEGIN EXCLUSIVE')
            first = c.send('tools/call', dict(name='inkbolt_document_render', arguments=dict(document=self.ref())))
            cancelled = c.send('tools/call', dict(name='inkbolt_session_apply', arguments=dict(session_id='work', request_id='cancelled', expected_revision=0, action=dict(type='snapshot', name='absent'))))
            c.send('notifications/cancelled', dict(requestId=cancelled), notification=True)
            self.assertEqual(c.rpc('ping')['result'], {})
            db.rollback()
            c.response(first)
            self.assertEqual(c.success('session.read', session_id='work')['current_revision'], 0)
            self.assertNotIn(cancelled, c.saved)
            self.cli('document.publish', document=self.ref(), control=dict(timeout_ms=0), output=dict(file_name='late.png', format='png'), error='TIMEOUT')
            self.assertFalse((self.root / 'late.png').exists())
        (self.root / 'cancel').touch()
        self.cli('document.publish', document=self.ref(), control=dict(cancel_file='cancel'), output=dict(file_name='cancelled.png', format='png'), error='CANCELLED')
        self.assertFalse((self.root / 'cancelled.png').exists())

    def test_corrupt_saved_revision_is_rejected_before_publication(self):
        self.save()
        path = self.root / '.inkbolt/sessions' / (hashlib.sha256(b'work').hexdigest() + '.sqlite3')
        with closing(sqlite3.connect(path)) as db:
            db.execute("UPDATE states SET sha256=? WHERE id=0", ('0' * 64,))
            db.commit()
        self.cli('document.publish', document=self.ref(), output=dict(file_name='corrupt.png', format='png'), error='SESSION_CORRUPT')
        self.assertFalse((self.root / 'corrupt.png').exists())

    def test_nested_frame_paths_use_the_workspace_and_preserve_sources(self):
        pixels = bytes([110, 12, 33, 255] * 4)
        data = png(2, 2, pixels)
        (self.root / 'frame.png').write_bytes(data)
        source = dict(type='images', frames=[dict(source_path='frame.png', delay=dict(numerator=1, denominator=10))])
        result = self.cli('sequence.import', id='frames', source=source)
        self.assertIn('document', result)
        self.assertTrue((self.root / '.inkbolt/assets').is_dir())
        self.assertEqual((self.root / 'frame.png').read_bytes(), data)
        source['frames'][0]['source_path'] = '../escape.png'
        self.cli('sequence.import', id='frames', source=source, error='INVALID_PATH')


if __name__ == '__main__':
    unittest.main()
