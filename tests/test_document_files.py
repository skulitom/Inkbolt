"""Content-pinned snapshot files, independent hashes and source-preserving round trips."""
from contextlib import closing
import hashlib
import json
import unittest

import test_agent_workspace as workspace
from test_images_cli import png
from test_mcp import Client


class DocumentFileTests(unittest.TestCase):
    setUp = workspace.AgentWorkspaceTests.setUp
    cli = workspace.AgentWorkspaceTests.cli
    document = workspace.AgentWorkspaceTests.document
    save = workspace.AgentWorkspaceTests.save
    ref = workspace.AgentWorkspaceTests.ref

    def file(self, name, data):
        path = self.root / name
        path.write_bytes(data)
        return dict(file_path=name, sha256=hashlib.sha256(data).hexdigest())

    def publish(self, doc, name):
        receipt = self.cli('document.publish', document=doc, output=dict(file_name=name, format='snapshot'))
        self.assertEqual(receipt['sha256'], hashlib.sha256((self.root / name).read_bytes()).hexdigest())
        return dict(file_path=name, sha256=receipt['sha256'])

    def test_cli_mcp_read_edit_compare_and_create_only_snapshot_round_trip(self):
        original = self.document()
        original['items'] = [dict(id='square', content=dict(type='vector', geometry=dict(shape='rect', x=0, y=0, width=2, height=2), fill=[19, 103, 171, 255]))]
        file = self.publish(original, 'original.json')
        raw = (self.root / 'original.json').read_bytes()
        canonical = json.loads(raw)
        self.assertEqual(self.cli('document.validate', document=file), canonical)
        absolute = dict(file, file_path=str(self.root / 'original.json'))
        self.assertEqual(self.cli('document.validate', scoped=False, document=absolute), canonical)
        with closing(Client(('--tools', 'core'), workspace=self.root)) as c:
            c.initialize()
            self.assertEqual(c.success('document.render', document=file)['data'], bytes([19, 103, 171, 255] * 4).hex())
            edited = c.success('document.edit', document=file, expected_revision=0, operations=[dict(op='remove', id='square')])['document']
            other = self.publish(edited, 'edited.json')
            result = c.tool('run', command='document.diff', arguments=dict(before=file, after=other, compare_pixels=True))['structuredContent']['result']
            self.assertTrue(result['changed'])
            self.assertEqual(result, self.cli('document.diff', before=canonical, after=edited, compare_pixels=True))
        self.cli('document.publish', document=other, output=dict(file_name='original.json', format='snapshot'), error='OUTPUT_EXISTS')
        self.assertEqual((self.root / 'original.json').read_bytes(), raw)
        self.assertFalse((self.root / '.inkbolt').exists())

    def test_changed_or_malformed_files_never_recurse_or_publish(self):
        file = self.publish(self.document(), 'pinned.json')
        original = (self.root / 'pinned.json').read_bytes()
        self.cli('document.validate', document=dict(file, sha256='0' * 64), error='SOURCE_MISMATCH')
        for ref in [dict(file_path='pinned.json'), dict(file, sha256='A' * 64), dict(file, sha256='short'),
                    dict(file, extra=True), dict(file, session_id='work', revision=0)]:
            self.cli('document.validate', document=ref, error='INVALID_REQUEST')
        self.cli('document.validate', document=dict(file, file_path='../escape.json'), error='INVALID_PATH')
        self.cli('document.validate', document=dict(file, file_path='missing.json'), error='IO_ERROR')
        self.cli('document.validate', scoped=False, document=file, error='INVALID_REQUEST')
        for i, data in enumerate([b'{', b'{}{}', b'\xff', b'{"id":"duplicate",' + original[1:],
                                  json.dumps(file).encode(), json.dumps(self.ref()).encode(),
                                  json.dumps(dict(ok=True, result=json.loads(original))).encode()]):
            malformed = self.file(f'malformed-{i}.json', data)
            self.cli('document.publish', document=malformed, output=dict(file_name='must-not-exist.json', format='snapshot'), error='INVALID_DOCUMENT_FILE')
        self.assertFalse((self.root / 'must-not-exist.json').exists())
        # Simulate an external source change after the agent recorded its hash.
        (self.root / 'pinned.json').write_bytes(original + b'\n')
        self.cli('document.publish', document=file, output=dict(file_name='changed.json', format='snapshot'), error='SOURCE_MISMATCH')
        self.assertEqual((self.root / 'pinned.json').read_bytes(), original + b'\n')
        self.assertFalse((self.root / 'changed.json').exists())

    def test_file_resources_are_explicit_and_durable_creation_replays(self):
        pixels = bytes([22, 35, 66, 255] * 4)
        source = self.root / 'source.png'
        source.write_bytes(png(2, 2, pixels))
        asset = self.cli('asset.import', source_path='source.png', store_root='chosen-assets')['asset']
        doc = self.document()
        doc['assets'] = {'original': asset}
        doc['items'] = [dict(id='image', content=dict(type='image', asset_id='original', width=2, height=2))]
        file = self.publish(doc, 'stored-image.json')
        self.cli('document.render', document=file, error='ASSET_MISSING')
        self.assertEqual(self.cli('document.render', document=file, asset_root='chosen-assets')['data'], pixels.hex())
        first = self.save(file, resources=dict(asset_root='chosen-assets', font_root=None))
        replay = self.save(file, resources=dict(asset_root='chosen-assets', font_root=None), control=dict(timeout_ms=0))
        self.assertTrue(replay['replayed'])
        self.assertEqual(replay['receipt'], first['receipt'])
        self.assertEqual(self.cli('document.render', document=self.ref())['data'], pixels.hex())
        self.assertEqual(source.read_bytes(), png(2, 2, pixels))
        self.cli('session.create', session_id='late', request_id='create', document=file,
                 resources=dict(asset_root='chosen-assets'), control=dict(timeout_ms=0), error='TIMEOUT')
        self.cli('session.read', session_id='late', error='SESSION_NOT_FOUND')

    def test_file_and_combined_expansion_limits_fail_before_execution(self):
        oversized = self.root / 'oversized.json'
        with oversized.open('wb') as output:
            output.truncate(16 * 1024 * 1024 + 1)
        self.cli('document.validate', document=dict(file_path='oversized.json', sha256='0' * 64), error='RESOURCE_LIMIT')
        doc = self.document()
        doc['metadata'] = dict(private={'large-original-fixture': 'x' * (9 * 1024 * 1024)})
        file = self.file('large.json', json.dumps(doc).encode())
        self.cli('document.diff', before=file, after=file, compare_pixels=False, error='REQUEST_TOO_LARGE')
        self.assertFalse((self.root / '.inkbolt').exists())


if __name__ == '__main__':
    unittest.main()
