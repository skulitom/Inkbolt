"""Editable clipping relationships in both layered RGB8 containers."""
import base64
import unittest

from advertised_limits import capabilities
import layered_fixtures as f
import test_layered_cli as core
from test_layered_groups_cli import marker


BASE = bytes(v for alpha in (0, 64, 128, 255) for v in (255, 0, 0, alpha))
BLUE = bytes([0, 0, 255, 128]) * 4
CLIPPED = '000000007f0080407f0080807f0080ff'
RELEASED = '0000ff803300cca05500aac07f0080ff'


def strip(name, rgba, **options):
    return dict(name=name, width=4, height=1, rgba=rgba, **options)


class LayeredClippingTests(unittest.TestCase):
    invoke = core.LayeredTests.invoke
    read = core.LayeredTests.read
    pixels = core.LayeredTests.pixels

    def exported(self, doc, version):
        result = self.invoke(dict(command='document.export', document=doc,
                                  format='layered' if version == 1 else 'layered_large'))
        return base64.b64decode(result['data'])

    def test_release_and_reapply_clipping_preserve_original_channels_and_identities(self):
        for version in (1, 2):
            records = [strip('same', BASE, id=72), strip('same', BLUE, clipping=1, id=3)]
            raw = f.make(records, w=4, h=1, version=version)
            doc = self.read(raw, color_policy='assume_srgb')['document']
            base, member = doc['items']
            self.assertEqual((base['id'], member['clip_to']), ('layer-72', 'layer-72'))
            for target, expected in [(base['id'], CLIPPED), (None, RELEASED), (base['id'], CLIPPED)]:
                if doc['items'][1].get('clip_to') != target:
                    edit = dict(op='layer_clip', id=member['id'], clip_to=target)
                    doc = self.invoke(dict(command='document.edit', document=doc,
                                           expected_revision=doc['revision'], operations=[edit]))['document']
                self.assertEqual(self.pixels(doc), expected)
                out = self.exported(doc, version)
                records = f.parse(out)['layers']
                self.assertEqual([r['clipping'] for r in records], [0, int(target is not None)])
                self.assertEqual([r['rgba'] for r in records], [BASE, BLUE])
                again = self.read(out)['document']
                self.assertEqual(again['items'][1].get('clip_to'),
                                 again['items'][0]['id'] if target else None)
                self.assertEqual(self.pixels(again), expected)

    def test_stacked_members_and_folder_bases_resolve_only_among_siblings(self):
        clear = bytes(16)
        records = [strip('outer base', clear), marker(3), strip('inner base', BASE),
                   strip('inner blue', BLUE, clipping=1), strip('inner clear', clear, clipping=1),
                   marker(1, 'folder'), strip('outer clear', clear, clipping=1)]
        cap = capabilities()['layered_interchange']['clipping']
        self.assertIn('isolated_group', cap['bases'])
        self.assertNotIn('isolated_group', cap['members'])
        for version in (1, 2):
            doc = self.read(f.make(records, w=4, h=1, version=version), color_policy='assume_srgb')['document']
            out = self.exported(doc, version)
            self.assertEqual([r['clipping'] for r in f.parse(out)['layers']], [0,0,0,1,1,0,1])
            for d in (doc, self.read(out)['document']):
                items = {i['name']: i for i in d['items']}
                for member in ('inner blue', 'inner clear'):
                    self.assertEqual(items[member]['clip_to'], items['inner base']['id'])
                    self.assertEqual(items[member]['parent'], items['folder']['id'])
                self.assertEqual(items['outer clear']['clip_to'], items['folder']['id'])
                self.assertEqual(self.pixels(d), CLIPPED)

    def test_unsupported_members_and_missing_sibling_base_fail_explicitly(self):
        base = strip('base', BASE)
        member = strip('member', BLUE, clipping=1)
        for records in ([member], [base, marker(3), member, marker(1)],
                        [base, marker(3), marker(1, mode=b'pass'), member],
                        [base, marker(3, clipping=1), marker(1)],
                        [base, marker(3), marker(1, clipping=1)],
                        [base, dict(member, clipping=2)]):
            with self.subTest(records=[r['name'] for r in records]):
                self.assertEqual(self.read(f.make(records, w=4, h=1), 1, color_policy='assume_srgb')['code'],
                                 'UNSUPPORTED_LAYERED_SEMANTICS')
        doc = self.read(f.make([base, marker(3), marker(1)], w=4, h=1), color_policy='assume_srgb')['document']
        doc['items'][1]['clip_to'] = doc['items'][0]['id']
        error = self.invoke(dict(command='document.export', format='layered', document=doc), 1)
        self.assertEqual(error['code'], 'UNSUPPORTED_LAYERED_SEMANTICS')
        self.assertIn('folder', error['message'])
