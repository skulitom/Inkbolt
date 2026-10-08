"""Original retained sources, independent pixels and explicit link lifecycle."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import test_editing_cli as editing
import test_images_cli as images
import test_samples_cli as samples
import test_hdr_cli as hdr
from test_mcp import Client


def sha(s): return hashlib.sha256(s.encode()).hexdigest()


class ObjectTests(unittest.TestCase):
    invoke = editing.EditingCliTests.invoke
    edit = samples.SampleTests.edit

    def doc(self, items=(), w=2, h=2, kind='raster', **kw):
        d = self.invoke(dict(command='document.create', id='original', kind=kind, width=w, height=h))
        d.update(items=list(items), **kw)
        return d

    def source(self, color=(23, 71, 149, 255), w=2, h=2):
        return self.doc([dict(id='pixels', content=dict(type='raster', width=w, height=h, rgba_hex=(bytes(color)*w*h).hex()))], w, h)

    def object(self, source, **kw):
        raw = source if isinstance(source, str) else json.dumps(source)
        obj = self.invoke(dict(command='object.import', snapshot=raw))['object']
        obj.update(kw)
        return obj

    def placed(self, obj, **kw):
        return self.doc([dict(id='placed', content=dict(type='object', object=obj), **kw)], int(obj['width']), int(obj['height']))

    def pixels(self, d, **kw):
        return bytes.fromhex(self.invoke(dict(command='document.render', document=d, **kw))['data'])

    def test_exact_utf8_source_hidden_color_reopen_and_snapshot(self):
        source = self.source((90, 20, 200, 0)); source['items'][0]['name'] = 'Original ÃƒÅ½Ã‚Â©'
        raw = '\n' + json.dumps(source, ensure_ascii=False, indent=3) + '\n'
        obj = self.object(raw); d = self.placed(obj); before = copy.deepcopy(d)
        opened = self.invoke(dict(command='object.open', document=d, id='placed'))
        self.assertEqual(opened['snapshot'], raw); self.assertEqual(opened['sha256'], sha(raw))
        self.assertEqual(opened['document']['items'][0]['content'], dict(source['items'][0]['content'], sampling='nearest'))
        self.assertEqual(self.pixels(d), bytes(16))
        self.assertEqual(json.loads(self.invoke(dict(command='document.export', document=d, format='snapshot'))['data']), self.invoke(dict(command='document.validate', document=d)))
        self.assertEqual(d, before)

    def test_transforms_reconstruct_original_pixels_at_integer_placements(self):
        colors = bytes([255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255, 255, 255, 0, 255])
        source = self.source(); source['items'][0]['content']['rgba_hex'] = colors.hex(); obj = self.object(source)
        cases = [([1, 0, 0, 1, 0, 0], colors), ([-1, 0, 0, 1, 2, 0], colors[4:8]+colors[:4]+colors[12:]+colors[8:12]), ([0, 1, -1, 0, 2, 0], colors[8:12]+colors[:4]+colors[12:]+colors[4:8])]
        for matrix, expected in cases:
            d = self.placed(obj, transform=matrix); self.assertEqual(self.pixels(d), expected)
            self.assertEqual(self.invoke(dict(command='document.inspect', document=d))['items'][0]['geometry_bounds'], [0, 0, 2, 2])
        d = self.placed(obj, transform=[2, 0, 0, 2, 0, 0]); d.update(width=4, height=4)
        expected = b''.join(colors[(y//2*2+x//2)*4:(y//2*2+x//2+1)*4] for y in range(4) for x in range(4))
        self.assertEqual(self.pixels(d), expected)

    def test_vector_sources_and_surface_resolution_preserve_editability(self):
        source = self.doc([dict(id='shape', content=dict(type='vector', geometry=dict(shape='rect', x=0, y=0, width=1, height=2), fill=[180, 70, 30, 255], stroke=None))], kind='vector')
        raw = json.dumps(source)
        for scale in [1, 2, 4]:
            obj = self.object(raw, surface_scale=scale); d = self.placed(obj)
            self.assertEqual(self.pixels(d), bytes([180, 70, 30, 255, 0, 0, 0, 0])*2)
            self.assertEqual(self.invoke(dict(command='object.open', document=d, id='placed'))['snapshot'], raw)

    def test_replacement_keeps_placement_and_duplicate_sources_independent(self):
        original = self.source(); obj = self.object(original); d = self.placed(obj)
        d['items'].append(dict(id='copy', transform=[1, 0, 0, 1, 2, 0], content=dict(type='object', object=copy.deepcopy(obj)))); d['width'] = 4
        replacement = self.object(self.source((201, 101, 51, 255), w=1, h=1))
        changed = self.edit(d, [dict(op='object_replace', id='placed', object=replacement)])
        self.assertEqual(changed['items'][0]['content']['object']['width'], 2)
        self.assertEqual(changed['items'][1]['content']['object'], obj)
        self.assertEqual(self.pixels(changed), (bytes([201, 101, 51, 255])*2+bytes([23, 71, 149, 255])*2)*2)
        changed = self.edit(d, [dict(op='object_replace', id='placed', object=replacement, keep_frame=False)])
        self.assertEqual(changed['items'][0]['content']['object']['width'], 1)
        self.assertEqual(self.invoke(dict(command='object.open', document=d, id='placed'))['sha256'], obj['sha256'])

    def test_reopened_content_edits_replace_only_explicit_owner(self):
        d = self.placed(self.object(self.source()))
        opened = self.invoke(dict(command='object.open', document=d, id='placed'))['document']
        edited = self.edit(opened, [dict(op='remove', id='pixels')])
        changed = self.edit(d, [dict(op='object_replace', id='placed', object=self.object(edited))])
        self.assertEqual(self.pixels(changed), bytes(16)); self.assertNotEqual(self.pixels(d), bytes(16))

    def test_link_status_update_conflict_missing_and_detach_preserve_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root/'source.json'; original = json.dumps(self.source(), indent=2); path.write_text(original)
            obj = self.invoke(dict(command='object.import', source_path=str(path), link_key='source.json'))['object']; d = self.placed(obj)
            status = lambda d: self.invoke(dict(command='object.status', document=d, id='placed', link_root=directory))
            self.assertEqual(status(d)['status'], 'current')
            new = json.dumps(self.source((10, 220, 80, 255))); path.write_text(new)
            self.assertEqual(status(d)['status'], 'changed'); self.assertEqual(self.pixels(d), bytes([23, 71, 149, 255])*4)
            op = dict(op='object_refresh', id='placed', link_root=directory, source_sha256=sha(new))
            self.assertEqual(self.edit(d, [dict(op, source_sha256=sha(original))], 1)['code'], 'OBJECT_SOURCE_CONFLICT')
            changed = self.edit(d, [op]); self.assertEqual(self.pixels(changed), bytes([10, 220, 80, 255])*4); self.assertEqual(path.read_text(), new)
            path.unlink(); self.assertEqual(status(changed)['status'], 'missing'); self.assertEqual(self.pixels(changed), bytes([10, 220, 80, 255])*4)
            self.assertEqual(self.edit(changed, [op], 1)['code'], 'OBJECT_SOURCE_MISSING')
            detached = self.edit(changed, [dict(op='object_detach', id='placed')]); self.assertEqual(status(detached)['status'], 'embedded')
            self.assertEqual(detached['items'][0]['content']['object']['snapshot'], new)

    def test_invalid_links_and_changed_malformed_sources_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'source.json'; path.write_text(json.dumps(self.source()))
            for key in ['', '../source.json', 'a/b.json', 'C:source.json', 'NUL.json', 'COM1', 'trailing.']:
                self.assertEqual(self.invoke(dict(command='object.import', source_path=str(path), link_key=key), 1)['code'], 'INVALID_OBJECT')
            d = self.placed(self.invoke(dict(command='object.import', source_path=str(path), link_key='source.json'))['object'])
            path.write_text('{"id":1,"id":2}')
            self.assertEqual(self.invoke(dict(command='object.status', document=d, id='placed', link_root=directory))['status'], 'invalid')
            self.assertEqual(self.edit(d, [dict(op='object_refresh', id='placed', link_root=directory, source_sha256=sha(path.read_text()))], 1)['code'], 'INVALID_JSON')
            self.assertEqual(self.pixels(d), bytes([23, 71, 149, 255])*4)

    def test_locked_ancestors_and_failed_batches_do_not_change_objects(self):
        obj = self.object(self.source()); d = self.placed(obj)
        replacement = self.object(self.source((1, 2, 3, 255))); op = dict(op='object_replace', id='placed', object=replacement)
        d['items'].insert(0, dict(id='parent', locked=True, content=dict(type='group'))); d['items'][1]['parent'] = 'parent'
        self.assertEqual(self.edit(d, [op], 1)['code'], 'LOCKED')
        d['items'][0]['locked'] = False; before = copy.deepcopy(d)
        result = self.edit(d, [op, dict(op='remove', id='missing')], 1)
        self.assertEqual(result['operation_index'], 1); self.assertEqual(d, before)

    def test_hash_tampering_strict_json_dimensions_and_mode_errors(self):
        obj = self.object(self.source())
        for bad in [dict(obj, sha256='0'*64), dict(obj, snapshot=obj['snapshot']+' '), dict(obj, width=0), dict(obj, surface_scale=5)]:
            d = self.placed(obj); d['items'][0]['content']['object'] = bad; self.invoke(dict(command='document.validate', document=d), 1)
        d = self.placed(obj); d['kind'] = 'vector'; self.assertEqual(self.invoke(dict(command='document.validate', document=d), 1)['code'], 'INVALID_OBJECT')
        for source in ['{}', '{"id":1,"id":2}', 'not json']:
            self.invoke(dict(command='object.import', snapshot=source), 1)
        self.invoke(dict(command='document.export', document=self.placed(obj), format='pdf'), 1)

    def test_nested_sources_are_retained_with_bounded_depth_and_evaluation_count(self):
        source = self.source()
        for _ in range(4): source = self.placed(self.object(source))
        self.assertEqual(self.pixels(source), bytes([23, 71, 149, 255])*4)
        self.assertEqual(self.invoke(dict(command='object.import', snapshot=json.dumps(source)), 1)['code'], 'RESOURCE_LIMIT')
        obj = self.object(self.source()); d = self.doc([dict(id='o'+str(i), content=dict(type='object', object=obj)) for i in range(33)])
        self.assertEqual(self.invoke(dict(command='document.render', document=d), 1)['code'], 'RESOURCE_LIMIT')

    def test_nested_metadata_privacy_strips_private_records_and_detaches_links(self):
        source = self.source(); source['metadata'] = dict(description='public', private={'secret':'private-marker'})
        obj = self.object(source, link=dict(key='source.json')); d = self.placed(obj)
        artifact = self.invoke(dict(command='document.export', document=d, format='snapshot', metadata_policy=dict(mode='public')))
        delivered = json.loads(artifact['data']); nested = delivered['items'][0]['content']['object']; inner = json.loads(nested['snapshot'])
        self.assertNotIn('private-marker', artifact['data']); self.assertEqual(inner['metadata']['description'], 'public'); self.assertNotIn('link', nested)
        self.assertEqual(nested['sha256'], sha(nested['snapshot'])); self.assertIn('private-marker', obj['snapshot'])

    def test_hdr_and_high_depth_objects_keep_native_values_and_require_explicit_views(self):
        source = self.doc([hdr.layer([-2, 8, 16, .5], w=1)], 1, 1, color_space='linear_srgb'); obj = self.object(source)
        d = self.placed(obj); self.assertEqual(self.invoke(dict(command='document.validate', document=d), 1)['code'], 'HDR_VIEW_REQUIRED')
        d['color_space'] = 'linear_srgb'; exported = self.invoke(dict(command='document.export', document=d, format='tiff', image_options=dict(depth='f32', compression='none')))
        self.assertEqual(samples.decode(exported)[0], [-2, 8, 16, .5])
        obj['view'] = dict(tone_map='clip'); d = self.placed(obj); self.assertEqual(self.pixels(d), bytes([0, 255, 255, 128]))
        source = self.doc([samples.layer([12345, 12346, 54321, 65535])], 1, 1); d = self.placed(self.object(source))
        exported = self.invoke(dict(command='document.export', document=d, format='tiff', image_options=dict(depth='u16', compression='none')))
        self.assertEqual(samples.decode(exported)[0], [12345, 12346, 54321, 65535])

    def test_explicit_external_image_store_resolves_inside_retained_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); p = root/'image.png'; pixels = bytes([23, 71, 149, 255])*4; p.write_bytes(images.png(2, 2, pixels)); original = p.read_bytes()
            asset = self.invoke(dict(command='asset.import', source_path=str(p), store_root=str(root/'store')))['asset']
            source = self.doc([dict(id='image', content=dict(type='image', asset_id='pinned', width=2, height=2))], assets={'pinned':asset})
            d = self.placed(self.object(source)); self.invoke(dict(command='document.render', document=d), 1)
            self.assertEqual(self.pixels(d, asset_root=str(root/'store')), pixels); self.assertEqual(p.read_bytes(), original)
            self.assertEqual(self.invoke(dict(command='object.open', document=d, id='placed'))['document']['assets']['pinned'], asset)

    def test_mcp_refresh_undo_redo_retry_and_create_only_publication(self):
        c = Client(); self.addCleanup(c.close); c.initialize()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root/'source.json'; path.write_text(json.dumps(self.source()))
            obj = c.success('object.import', source_path=str(path), link_key='source.json')['object']; d = self.placed(obj)
            args = dict(session_root=directory, session_id='objects'); c.success('session.create', **args, request_id='create', document=d)
            new = json.dumps(self.source((200, 20, 40, 255))); path.write_text(new)
            action = dict(type='edit', operations=[dict(op='object_refresh', id='placed', link_root=directory, source_sha256=sha(new))])
            changed = c.success('session.apply', **args, request_id='refresh', expected_revision=0, action=action)['document']
            self.assertEqual(c.success('object.open', document=changed, id='placed')['snapshot'], new)
            output = dict(output_root=directory, file_name='delivered.png', format='png'); c.success('session.publish', **args, expected_revision=1, output=output)
            self.assertEqual(editing.png_pixels((root/'delivered.png').read_bytes())[2], bytes([200, 20, 40, 255])*4)
            self.assertTrue(c.tool('session.publish', **args, expected_revision=1, output=output)['isError'])
            self.assertEqual(c.success('session.apply', **args, request_id='undo', expected_revision=1, action=dict(type='undo'))['document']['items'][0]['content']['object']['sha256'], obj['sha256'])
            c.success('session.apply', **args, request_id='redo', expected_revision=2, action=dict(type='redo')); path.unlink()
            self.assertTrue(c.success('session.apply', **args, request_id='refresh', expected_revision=0, action=action)['replayed']); self.assertTrue(c.success('session.verify', **args)['valid'])

    def test_nested_composition_preserves_alpha_masks_and_parent_blending(self):
        source = self.source((200, 100, 40, 128))
        obj = self.object(source)
        base = self.source((40, 60, 80, 255))['items'][0]
        placed = dict(id='placed', opacity=.5, blend='multiply', content=dict(type='object', object=obj), clip=dict(geometry=dict(shape='rect', x=0, y=0, width=1, height=2)))
        d = self.doc([base, placed]); a = 128/255*.5
        expected = bytes(int((b*(1-a)+b*s/255*a)+.5) for b, s in zip([40,60,80],[200,100,40]))+bytes([255])
        self.assertEqual(self.pixels(d), (expected+bytes([40,60,80,255]))*2)
        placed['blend'] = 'normal'; placed['clip_to'] = 'pixels'; self.assertEqual(self.pixels(d)[4:8], bytes([40,60,80,255]))
        self.assertEqual(obj['snapshot'], json.dumps(source))

    def test_reconstruction_and_supersampling_do_not_reduce_high_depth(self):
        source = self.doc([samples.layer([12345,12346,54321,65535]*4, w=2)], 2, 2)
        for method in ['nearest','bilinear','area','bicubic','lanczos3']:
            d = self.placed(self.object(source, sampling=method))
            for antialias in ['coverage','supersample2']:
                artifact = self.invoke(dict(command='document.export', document=d, format='tiff', image_options=dict(depth='u16',compression='none'), render_options=dict(antialias=antialias)))
                self.assertEqual(samples.decode(artifact)[0], [12345,12346,54321,65535]*4)

    def test_retained_object_pixel_deformation_and_background_keep_source(self):
        obj = self.object(self.source((23,71,149,128))); d = self.placed(obj)
        d['items'][0]['pixel_warp'] = dict(type='perspective',corners=[[2,0],[0,0],[0,2],[2,2]])
        self.assertEqual(self.pixels(d),bytes([23,71,149,128])*4)
        changed = self.edit(d,[dict(op='background',id='placed',action=dict(type='promote',matte=[255,255,255]))])
        expected = bytes(int(c*128/255+255*(1-128/255)+.5) for c in [23,71,149])+bytes([255])
        self.assertEqual(self.pixels(changed),expected*4)
        self.assertEqual(self.invoke(dict(command='object.open',document=changed,id='placed'))['sha256'],obj['sha256'])

    def test_artboard_delivery_clips_object_without_rewriting_source(self):
        obj = self.object(self.source()); source = copy.deepcopy(obj)
        frame = dict(id='page',transform=[1,0,0,1,8,9],content=dict(type='frame',frame=dict(role='artboard',width=2,height=2)))
        d = self.doc([frame,dict(id='placed',parent='page',content=dict(type='object',object=obj))],12,12)
        artifact = self.invoke(dict(command='artboard.export',document=d,format='png'))['artifacts'][0]['artifact']
        self.assertEqual(editing.png_pixels(base64.b64decode(artifact['data']))[2],bytes([23,71,149,255])*4)
        self.assertEqual(obj,source)

    def test_aggregate_nested_render_budget_fails_before_unbounded_work_and_recovers(self):
        source = self.doc([],1024,1024); obj = self.object(source); d = self.placed(obj)
        # Parent drawable and inner evaluation exceed the shared four-million buffer-pixel budget.
        self.assertEqual(self.invoke(dict(command='document.render',document=d),1)['code'],'RESOURCE_LIMIT')
        c=Client();self.addCleanup(c.close);c.initialize()
        self.assertTrue(c.tool('document.render',document=d)['isError'])
        small=self.placed(self.object(self.source()))
        self.assertEqual(bytes.fromhex(c.success('document.render',document=small)['data']),bytes([23,71,149,255])*4)

    def test_duplicate_operation_and_diff_keep_object_identity_visible(self):
        d = self.placed(self.object(self.source()))
        # Ordinary duplication clones the complete retained object, never an external mutable alias.
        changed = self.edit(d,[dict(op='duplicate',id='placed',new_id='copy')])
        self.assertEqual(changed['items'][0]['content'],changed['items'][1]['content'])
        replacement=self.object(self.source((1,2,3,255)))
        edited=self.edit(changed,[dict(op='object_replace',id='copy',object=replacement)])
        comparison=self.invoke(dict(command='document.diff',before=changed,after=edited))
        self.assertIn('content.object',comparison['items'][0]['fields'])
        inspection=self.invoke(dict(command='document.inspect',document=edited))
        self.assertEqual(inspection['items'][1]['object']['sha256'],replacement['sha256'])

    def test_object_font_resources_manifest_and_transfer_verify_nested_bindings(self):
        from synthetic_font import geometric_font
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); font_path=root/'original.ttf';font_path.write_bytes(geometric_font());license_path=root/'LICENSE.txt';license_path.write_bytes((Path(__file__).resolve().parents[1]/'LICENSE').read_bytes());store=root/'fonts'
            font=self.invoke(dict(command='font.import',source_path=str(font_path),license_path=str(license_path),store_root=str(store)))
            frame=dict(text='A',width=16,height=16,style=dict(font_id='original',size=10,fill=[20,80,160,255]))
            source=self.doc([dict(id='label',content=dict(type='text',frame=frame))],16,16,fonts={'original':font})
            obj=self.object(source);d=self.placed(obj);self.invoke(dict(command='document.render',document=d),1)
            direct=self.pixels(source,font_root=str(store));self.assertTrue(any(direct));self.assertEqual(self.pixels(d,font_root=str(store)),direct)
            empty=self.doc([],16,16);op=dict(op='transfer',transfer=dict(source=d,ids=['placed'],prefix='copy',verify_resources=True))
            self.edit(empty,[op],1)
            copied=self.invoke(dict(command='document.edit',document=empty,expected_revision=0,operations=[op],font_root=str(store)))['document']
            self.assertEqual(copied['items'][0]['content']['object'],obj);self.assertEqual(self.pixels(copied,font_root=str(store)),direct)
            receipt=self.invoke(dict(command='object.import',snapshot=json.dumps(d)))
            self.assertEqual(receipt['resources']['objects']['placed']['resources']['fonts']['original']['sha256'],font['sha256'])

    def test_invalid_utf8_oversize_and_directory_links_preserve_cached_artwork(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'source.json';path.write_text(json.dumps(self.source()))
            obj=self.invoke(dict(command='object.import',source_path=str(path),link_key='source.json'))['object'];d=self.placed(obj)
            for data in [b'\xff',b' '*(768*1024+1)]:
                path.write_bytes(data);status=self.invoke(dict(command='object.status',document=d,id='placed',link_root=directory));self.assertEqual(status['status'],'unavailable');self.assertEqual(self.pixels(d),bytes([23,71,149,255])*4)
            path.unlink();path.mkdir();status=self.invoke(dict(command='object.status',document=d,id='placed',link_root=directory));self.assertIn(status['status'],['missing','unavailable']);self.assertEqual(self.pixels(d),bytes([23,71,149,255])*4)


if __name__ == '__main__': unittest.main()
