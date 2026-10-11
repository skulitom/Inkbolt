"""Shared artwork, independent crop oracles, page paths and saved scene views."""
import base64
import copy
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
import test_boards_cli as boards
from test_editing_cli import png_pixels
from pdf_reader import Pdf


class SceneArtboards(unittest.TestCase):
    invoke = boards.BoardCliTests.invoke
    edit = boards.BoardCliTests.edit
    board = boards.BoardCliTests.board
    rectangle = boards.BoardCliTests.rectangle
    exports = boards.BoardCliTests.exports

    def fixture(self):
        d = self.invoke(dict(command='document.create', id='scene-views', kind='vector', width=24, height=12))
        items = [
            self.board('left', 8, 6, 2, 3, scope='scene', bleed=dict(left=1, top=2, right=2, bottom=1)),
            self.board('right', 8, 6, 8, 3, scope='scene'),
            dict(id='base', name='Shared base', content=dict(type='group', role='layer')),
            self.rectangle('paper', 'base', 'vector', -2, -2, 28, 18, [20,40,60,255]),
            dict(id='top', name='Shared top', transform=[1,0,0,1,1,1], content=dict(type='group', role='layer')),
            self.rectangle('crossing', 'top', 'vector', 6, 3, 4, 3, [220,30,40,255]),
        ]
        return self.edit(d, [dict(op='add', item=i) for i in items])

    def check_pixels(self, entry, origin, red=True, mask=False):
        w,h,p,_ = png_pixels(base64.b64decode(entry['artifact']['data']))
        for y in range(h):
            for x in range(w):
                wx,wy = x+origin[0], y+origin[1]
                hit = red and 7<=wx<11 and 4<=wy<7
                if mask:
                    hit = hit and wx==8
                expected = bytes([220,30,40,255] if hit else [20,40,60,255])
                self.assertEqual(p[(y*w+x)*4:][:4], expected, (x,y,origin))
        return w,h,p

    def test_shared_layers_cross_views_with_exact_independent_pixels_and_bleed(self):
        d = self.fixture(); before = copy.deepcopy(d)
        for bleed in (False, True):
            result = self.exports(d, include_bleed=bleed)
            self.assertEqual(result['scope'], 'artboard_per_item_local')
            self.assertEqual([e['scope'] for e in result['artifacts']], ['scene','scene'])
            self.check_pixels(result['artifacts'][0], (1,1) if bleed else (2,3))
            self.check_pixels(result['artifacts'][1], (8,3))
        # One shared visibility edit affects both views; no artwork is cloned.
        hidden = self.edit(d, [dict(op='properties', id='top', visible=False)])
        for e,origin in zip(self.exports(hidden)['artifacts'], [(2,3),(8,3)]):
            self.check_pixels(e, origin, red=False)
        self.assertEqual(len(hidden['items']), len(d['items']))
        self.assertEqual(d, before)

    def test_viewport_move_resize_duplicate_remove_and_reorder_preserve_artwork(self):
        d = self.fixture()
        artwork = {i['id']:i for i in d['items'] if i['id'] not in ('left','right')}
        moved = self.edit(d, [dict(op='transform', id='left', matrix=[1,0,0,1,5,2]),
                             dict(op='duplicate', id='right', new_id='copy'),
                             dict(op='reorder', id='copy', index=0),
                             dict(op='remove', id='right')])
        self.assertEqual([e['id'] for e in self.exports(moved)['artifacts']], ['copy','left'])
        for e,origin in zip(self.exports(moved)['artifacts'], [(8,3),(5,2)]):
            self.check_pixels(e, origin)
        self.assertEqual({i['id']:i for i in moved['items'] if i['id'] in artwork}, artwork)
        # Locate by ID rather than assuming the storage order matches display order.
        frame = copy.deepcopy(next(i for i in moved['items'] if i['id']=='left')['content']['frame'])
        frame.update(width=5, height=4)
        resized = self.edit(moved, [dict(op='frame', id='left', frame=frame)])
        self.assertEqual(self.check_pixels(self.exports(resized)['artifacts'][1], (5,2))[:2], (5,4))
        self.assertEqual({i['id']:i for i in resized['items'] if i['id'] in artwork}, artwork)

    def test_unlinked_world_mask_and_preview_coordinates_rebase_once(self):
        d = self.fixture()
        target = next(i for i in d['items'] if i['id']=='crossing')
        target['mask'] = dict(width=4, height=3, gray_hex='00ff0000'*3,
                              transform=[1,0,0,1,7,4], linked=False)
        d = self.invoke(dict(command='document.validate', document=d))
        for e,origin in zip(self.exports(d)['artifacts'], [(2,3),(8,3)]):
            self.check_pixels(e, origin, mask=True)
        preview = self.invoke(dict(command='document.preview', document=d,
                                  options=dict(focus=dict(type='artboard', id='right'))))
        self.check_pixels(preview, (8,3), mask=True)
        self.assertEqual(preview['mapping']['world_to_pixel'], [1,0,0,1,-8,-3])

    def test_snapshot_saved_edit_retry_and_undo_keep_one_layer_tree(self):
        d = self.fixture()
        data = self.invoke(dict(command='document.export', document=d, format='snapshot'))['data']
        restored = self.invoke(dict(command='document.validate', document=json.loads(data)))
        self.assertEqual(restored, d)
        with tempfile.TemporaryDirectory() as root:
            args = dict(session_root=root, session_id='scene-history')
            created = self.invoke(dict(command='session.create', request_id='create', document=d, **args))
            rev = created['document']['revision']
            request = dict(command='session.apply', expected_revision=rev, request_id='hide', **args,
                           action=dict(type='edit', operations=[dict(op='properties', id='top', visible=False)]))
            changed = self.invoke(request)
            retried = self.invoke(request)
            self.assertTrue(retried['replayed'])
            self.assertEqual(retried['document'], changed['document'])
            undo = self.invoke(dict(command='session.apply', expected_revision=changed['document']['revision'],
                                    request_id='undo', action=dict(type='undo'), **args))
            self.assertEqual(undo['document']['items'], d['items'])
            for e,origin in zip(self.exports(undo['document'])['artifacts'], [(2,3),(8,3)]):
                self.check_pixels(e, origin)

    def test_pdf_svg_and_mixed_selection_preserve_shared_paths_and_old_subtrees(self):
        d = self.fixture()
        pdf = self.invoke(dict(command='document.export', document=d, format='pdf',
                               pdf_options=dict(artboards=dict(type='all'))))
        parsed = Pdf(pdf)
        self.assertEqual([p['MediaBox'] for p in parsed.pages], [[0,0,6,4.5]]*2)
        for page, origin in enumerate([(2,3),(8,3)]):
            paths = parsed.paths(page)
            self.assertEqual(len(paths), 2)
            vertices = {tuple(p) for verb,points in paths[1]['path'] if verb in ('m','l') for p in points}
            # The independent PDF reader returns page paths in top-left points.
            self.assertEqual(vertices, {((x-origin[0])*.75, (y-origin[1])*.75) for x in (7,11) for y in (4,7)})
        svg = self.invoke(dict(command='artboard.export', document=d, format='svg'))
        ns = {'s':'http://www.w3.org/2000/svg'}
        for e,origin in zip(svg['artifacts'], [(2,3),(8,3)]):
            root = ET.fromstring(e['artifact']['data'])
            groups = {g.get('id'):g for g in root.findall('.//s:g',ns)}
            self.assertNotIn('left', groups); self.assertNotIn('right', groups)
            self.assertEqual(groups['top'].get('transform'), f'matrix(1 0 0 1 {1-origin[0]} {1-origin[1]})')
            self.assertIn('crossing', groups)
        # The default scope still exports only owned children, even in a mixed scene.
        d = self.edit(d, [dict(op='add', item=self.board('owned', 2, 2, 20, 0, background=[1,2,3,255]))])
        mixed = self.exports(d, selection=dict(type='ids', ids=['owned','right']))
        self.assertEqual([e['scope'] for e in mixed['artifacts']], ['subtree','scene'])
        self.assertEqual(png_pixels(base64.b64decode(mixed['artifacts'][0]['artifact']['data']))[2], bytes([1,2,3,255])*4)
        self.check_pixels(mixed['artifacts'][1], (8,3))

    def test_reject_ambiguous_scene_ownership_appearance_and_incomplete_range(self):
        d = self.fixture()
        for modify in [lambda v:v.update(kind='raster'),
                       lambda v:v['items'][0].update(parent='base'),
                       lambda v:v['items'][2].update(parent='left'),
                       lambda v:v['items'][0].update(opacity=.5),
                       lambda v:v['items'][0]['content']['frame'].update(background=[0,0,0,255]),
                       lambda v:v['items'][0]['content']['frame'].update(role='frame')]:
            bad = copy.deepcopy(d); modify(bad)
            self.assertEqual(self.invoke(dict(command='document.validate', document=bad), 1)['code'], 'INVALID_DOCUMENT')
        self.assertEqual(self.edit(d, [dict(op='transform', id='left', matrix=[0,1,-1,0,2,3])], 1)['code'], 'UNSUPPORTED')
        locked = self.edit(d, [dict(op='properties', id='left', locked=True)])
        self.assertEqual(self.edit(locked, [dict(op='remove', id='left')], 1)['code'], 'LOCKED')
        large = copy.deepcopy(d)
        large['items'] = [self.board('b'+str(n), 1024, 1024, scope='scene') for n in range(5)]
        failed = self.exports(large, 1)
        self.assertEqual(failed['code'], 'RESOURCE_LIMIT'); self.assertEqual(failed['artboard_id'], 'b4')
        self.assertNotIn('artifacts', failed)
        cap = self.invoke(dict(command='capabilities'))
        self.assertEqual(cap['supported']['artboards']['scope']['choices'], ['subtree','scene'])

    def test_scene_range_charges_all_shared_artwork_and_requires_all_resources(self):
        d = self.fixture()
        # Each view fits; 20 * 256 * 256 * 120 exceeds aggregate work, not pixels.
        d['items'] = [self.board('b'+str(n), 256, 256, scope='scene') for n in range(20)]
        d['items'] += [self.rectangle('r'+str(n), None, 'vector', 0, 0, 1, 1, [1,2,3,255]) for n in range(120)]
        error = self.exports(d, 1)
        self.assertEqual(error['code'], 'RESOURCE_LIMIT')
        self.assertEqual(error['artboard_id'], 'b17')
        self.assertNotIn('artifacts', error)
        d = self.fixture()
        d = self.edit(d, [dict(op='asset_put', id='missing', asset=dict(width=1,height=1,sha256='a'*64,storage=dict(type='stored'))),
                          dict(op='add', item=dict(id='outside', transform=[1,0,0,1,20,10], content=dict(type='image', asset_id='missing', width=1,height=1)))])
        error = self.exports(d, 1, selection=dict(type='ids', ids=['left']))
        self.assertEqual(error['code'], 'ASSET_ROOT_REQUIRED')
        self.assertEqual(error['asset_id'], 'missing')

    def test_fractional_scene_extent_keeps_exact_canvas_coverage(self):
        d = self.fixture()
        frame = d['items'][0]['content']['frame']
        frame.update(width=3,height=3,logical_size=[2.5,2.25])
        e = self.exports(d, selection=dict(type='ids',ids=['left']))['artifacts'][0]
        self.assertEqual(e['logical_size'], [2.5,2.25])
        w,h,p,_ = png_pixels(base64.b64decode(e['artifact']['data']))
        self.assertEqual((w,h),(3,3))
        for y in range(h):
            for x in range(w):
                alpha = int(255 * min(1,2.5-x) * min(1,2.25-y)+.5)
                self.assertEqual(p[(y*w+x)*4:][:4], bytes([20,40,60,alpha]))


if __name__ == '__main__':
    unittest.main()
