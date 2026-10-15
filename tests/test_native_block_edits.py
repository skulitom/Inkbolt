"""Versioned native block editing, independent samples and pure review boundaries."""
import copy
import hashlib
import json
import sqlite3
import struct
import unittest
from contextlib import closing

import test_stored_samples as native
from test_mcp import Client
from test_samples_cli import decode
from test_pixel_brush_cli import brush
from test_profiles_cli import embedded, linear_profile


class NativeBlockEditTests(unittest.TestCase):
    setUp = native.StoredSampleTests.setUp
    cli = native.StoredSampleTests.cli
    imported = native.StoredSampleTests.imported
    files = native.StoredSampleTests.files
    blocks = native.StoredSampleTests.blocks
    grid = native.StoredSampleTests.grid
    view = native.StoredSampleTests.view
    exported = native.StoredSampleTests.exported
    patch = native.StoredSampleTests.patch
    save = native.StoredSampleTests.save
    ref = native.StoredSampleTests.ref

    def edit(self, document, operations):
        return self.cli('document.edit', document=document,
                        expected_revision=document['revision'], operations=operations)

    def migration(self):
        return dict(op='sample_storage_migrate', id='pixels')

    def typed_blocks(self, spec, raw):
        width, height = spec['width'], spec['height']
        unit = dict(u8=1, u16=2, f32=4)[spec['depth']]
        channels = dict(rgba=4, gray_alpha=2)[spec['channels']]
        encoding = dict(encoded_srgb=0, linear_srgb=1, profiled_rgb=2)[spec['encoding']]
        stride = unit * channels
        self.assertEqual(len(raw), width * height * stride)
        names, blocks = [], {}
        for y in range(0, height, 128):
            for x in range(0, width, 128):
                w, h = min(128, width-x), min(128, height-y)
                blob = b'INKTILE1'+struct.pack('<IIBBBB', w, h, unit, channels, encoding, 0)
                blob += b''.join(raw[(row*width+x)*stride:(row*width+x+w)*stride] for row in range(y,y+h))
                name = hashlib.sha256(blob).hexdigest()
                names.append(name); blocks[name] = blob
        typed = b'INKTILE1'+struct.pack('<IIBBBB',width,height,unit,channels,encoding,0)
        identity = hashlib.sha256(b'INKGRID1'+typed+struct.pack('<I',128)
                                 +b''.join(bytes.fromhex(name) for name in names)).hexdigest()
        return dict(version=1,spec=spec,tiles=names,sha256=identity), blocks

    def assert_native_bits(self, document, raw):
        grid = self.grid(document)
        manifest, blocks = self.typed_blocks(grid['base']['spec'], raw)
        self.assertEqual(grid['base'], manifest)
        staged = grid.get('staged', {})
        pending = {row['sha256']:bytes.fromhex(row['data_hex']) for row in staged.get('pending', [])}
        root = self.root/'.inkbolt/assets'
        for name, blob in blocks.items():
            actual = pending[name] if name in pending else (root/(name+'.native-tile')).read_bytes()
            self.assertEqual(actual, blob)

    def check_native(self, document, expected, retained_blocks=None):
        grid = self.grid(document)
        self.assertEqual(grid['storage_version'], 2)
        self.assertNotIn('staged', grid)
        self.assertNotIn('patches', grid)
        manifest = grid['base']; spec = manifest['spec']
        self.assertEqual((spec['depth'], spec['channels']), ('u16', 'rgba'))
        width, height = spec['width'], spec['height']
        columns = (width + 127) // 128
        blocks = self.blocks() if retained_blocks is None else retained_blocks
        for index, identity in enumerate(manifest['tiles']):
            x, y = index % columns * 128, index // columns * 128
            w, h = min(128, width-x), min(128, height-y)
            header = b'INKTILE1'+struct.pack('<IIBBBB', w, h, 2, 4, 0, 0)
            payload = b''.join(struct.pack('<4H', *expected(xx, yy))
                               for yy in range(y, y+h) for xx in range(x, x+w))
            blob = header + payload
            self.assertEqual(blocks[identity+'.native-tile'], blob)
            self.assertEqual(hashlib.sha256(blob).hexdigest(), identity)
        typed = b'INKTILE1'+struct.pack('<IIBBBB', width, height, 2, 4, 0, 0)
        identity = hashlib.sha256(b'INKGRID1'+typed+struct.pack('<I',128)
                                 +b''.join(bytes.fromhex(v) for v in manifest['tiles'])).hexdigest()
        self.assertEqual(manifest['sha256'], identity)

    def states(self, session='work'):
        path = self.root/'.inkbolt/sessions'/(hashlib.sha256(session.encode()).hexdigest()+'.sqlite3')
        with closing(sqlite3.connect(path)) as db:
            rows = db.execute('SELECT payload,sha256 FROM states ORDER BY id').fetchall()
        for payload, identity in rows:
            self.assertEqual(hashlib.sha256(payload).hexdigest(), identity)
            state = json.loads(payload)
            for item in state['document']['items']:
                if item['content']['type'] == 'stored_samples':
                    self.assertNotIn('staged', item['content']['grid'])
        return rows

    def test_migration_and_260_committed_edits_preserve_samples_and_small_snapshots(self):
        original = self.imported(257, 3)
        original_files = self.blocks()
        first = self.patch(0, 1, 257, 1, [v for x in range(257) for v in [1000, x, 4321, 65535]])
        legacy = self.edit(original, [first])['document']
        legacy_snapshot = copy.deepcopy(legacy)
        with closing(Client(('--tools', 'core'), workspace=self.root)) as client:
            client.initialize()
            result = client.success('document.edit', document=legacy,
                                    expected_revision=legacy['revision'], operations=[self.migration()])
            current = result['document']
            self.check_native(current, lambda x,y: [1000,x,4321,65535] if y==1 else native.pixel(x,y))
            retained = [(copy.deepcopy(current), 1000)]
            edited_pixels = 0
            for index in range(260):
                value = 2000 + index
                op = self.patch(0, 1, 257, 1, [v for x in range(257) for v in [value,x,4321,65535]])
                current = client.success('document.edit', document=current,
                                         expected_revision=current['revision'], operations=[op])['document']
                edited_pixels += 257
                self.assertNotIn('patches', self.grid(current))
                self.assertNotIn('staged', self.grid(current))
                self.assertLess(len(json.dumps(current)), 2500)
                if index in (0, 129, 259):
                    self.check_native(current, lambda x,y,v=value: [v,x,4321,65535] if y==1 else native.pixel(x,y))
                    retained.append((copy.deepcopy(current), value))
            caps = self.cli('capabilities')['native_sample_store_library']
            self.assertGreater(edited_pixels, caps['retained_edits']['max_aggregate_patch_pixels'])
            self.assertGreater(260, caps['retained_edits']['max_patches'])
        for document, value in retained:
            self.check_native(document, lambda x,y,v=value: [v,x,4321,65535] if y==1 else native.pixel(x,y))
        for name, data in original_files.items():
            self.assertEqual(self.blocks()[name], data)
        self.assertEqual(legacy, legacy_snapshot)
        self.assertEqual(decode(self.exported(legacy))[0],
                         [v for y in range(3) for x in range(257)
                          for v in ([1000,x,4321,65535] if y==1 else native.pixel(x,y))])

    def test_review_migration_commit_undo_redo_and_missing_store_replay(self):
        original = self.view(self.imported())
        legacy = self.edit(original, [self.patch()])['document']
        initial = self.save(legacy)
        before = self.files(); original_rows = self.states()
        action = dict(type='edit', operations=[self.migration()])
        review = self.cli('session.dry_run', session_id='work', request_id='migrate', expected_revision=0,
                          action=action, options=dict(preview=True, compare_pixels=True, include_document=True))
        self.assertEqual(self.files(), before)
        proposed = review['proposed_document']
        self.assertIn('staged', self.grid(proposed))
        self.assertEqual(decode(self.exported(proposed))[0], decode(self.exported(legacy))[0])
        self.assertEqual(self.files(), before)
        committed = self.cli('session.apply_proposal', proposal=review['proposal'], action=action)
        durable = copy.deepcopy(proposed); self.grid(durable).pop('staged')
        self.assertEqual(committed['document'], durable)
        self.assertEqual(committed['receipt'], review['predicted_receipt'])
        actual_diff = self.cli('session.diff', session_id='work', from_revision=0, to_revision=1, compare_pixels=True)
        for key, value in review['difference'].items():
            self.assertEqual(actual_diff[key], value, key)
        rows = self.states()
        self.assertEqual(rows[:len(original_rows)], original_rows)
        self.assertEqual(rows[-1][1], review['proposal']['result_state_sha256'])
        self.assertLess(len(rows[-1][0]), 4000)
        undone = self.cli('session.apply', session_id='work', request_id='undo', expected_revision=1,
                          action=dict(type='undo', steps=1))
        restored = copy.deepcopy(initial['document']); restored['revision'] = 2
        self.assertEqual(undone['document'], restored)
        redone = self.cli('session.apply', session_id='work', request_id='redo', expected_revision=2,
                          action=dict(type='redo', steps=1))
        self.assertEqual(self.grid(redone['document']), self.grid(durable))
        store = self.root/'.inkbolt/assets'; held = self.root/'held-native-store'
        store.rename(held)
        try:
            replay = self.cli('session.apply_proposal', proposal=review['proposal'], action=action)
            self.assertTrue(replay['replayed'])
            self.assertEqual(replay['receipt'], committed['receipt'])
        finally:
            held.rename(store)

    def test_full_native_history_continues_past_old_patch_caps_without_rewriting_parent(self):
        original = self.imported(257,3)
        migrated = self.edit(original,[self.migration()])['document']
        self.save(migrated)
        caps = self.cli('capabilities')
        capacity = caps['limits']['session_states']
        session, revision = 'work', 0
        parent_rows = None
        with closing(Client(('--tools','core'),workspace=self.root)) as client:
            client.initialize()
            for index in range(capacity+4):
                value = 3000+index
                op = self.patch(0,1,257,1,[v for x in range(257) for v in [value,x,4321,65535]])
                result = client.success('session.apply',session_id=session,request_id=f'edit-{index}',
                                        expected_revision=revision,action=dict(type='edit',operations=[op]))
                revision += 1
                if index == 0:
                    first_receipt = result['receipt']
                    first_action = dict(type='edit',operations=[copy.deepcopy(op)])
                    client.success('session.apply',session_id=session,request_id='snapshot',
                                   expected_revision=revision,action=dict(type='snapshot',name='first'))
                    revision += 1
                if index == capacity-2:
                    parent_revision = revision
                    parent_rows = self.states()
                    parent_check = self.cli('session.verify',session_id='work')
                    self.assertEqual(parent_check['states'],capacity)
                    before = self.files()
                    extra = self.patch(0,1,257,1,[v for x in range(257) for v in [6000,x,4321,65535]])
                    self.cli('session.apply',session_id='work',request_id='over-capacity',expected_revision=revision,
                             action=dict(type='edit',operations=[extra]),error='HISTORY_LIMIT')
                    self.assertEqual(self.files(),before)
                    backup = self.cli('session.backup',session_id='work',expected_revision=revision,
                                      output=dict(file_name='native-parent.sqlite3'))['backup']
                    continued = self.cli('session.continue',session_id='next',request_id='continue',
                                         parent=dict(source=backup,session_id='work',revision=revision))
                    self.assertEqual(continued['lineage']['source_history_sha256'],parent_check['history_sha256'])
                    session, revision = 'next', 0
        self.assertEqual(session,'next')
        self.assertEqual(self.states(),parent_rows)
        self.assertEqual(self.cli('session.verify',session_id='work')['history_sha256'],parent_check['history_sha256'])
        self.assertGreater((capacity+4)*257,caps['native_sample_store_library']['retained_edits']['max_aggregate_patch_pixels'])
        self.assertGreater(capacity+4,caps['native_sample_store_library']['retained_edits']['max_patches'])
        blocks = self.blocks()
        for index,(payload,_) in enumerate(parent_rows):
            document = json.loads(payload)['document']
            self.assertLess(len(payload),4000)
            self.check_native(document, lambda x,y,i=index: native.pixel(x,y) if i==0 or y!=1
                              else [2999+i,x,4321,65535], blocks)
        for index,(payload,_) in enumerate(self.states('next')):
            document = json.loads(payload)['document']
            self.check_native(document,lambda x,y,i=index: [3000+capacity-2+i,x,4321,65535] if y==1
                              else native.pixel(x,y),blocks)
        snapshot = self.cli('session.read',session_id='work',snapshot='first')['document']
        self.check_native(snapshot,lambda x,y:[3000,x,4321,65535] if y==1 else native.pixel(x,y),blocks)
        replay = self.cli('session.apply',session_id='work',request_id='edit-0',expected_revision=0,action=first_action)
        self.assertTrue(replay['replayed']); self.assertEqual(replay['receipt'],first_receipt)
        self.cli('session.recover',session_id='work',session_root='restored',source=backup)
        restored = self.cli('session.read',session_id='work',session_root='restored')
        self.assertEqual(restored['current_revision'],parent_revision)
        self.check_native(restored['document'],lambda x,y:[3000+capacity-2,x,4321,65535] if y==1 else native.pixel(x,y),blocks)
        self.assertEqual(self.cli('session.verify',session_id='work',session_root='restored')['history_sha256'],
                         parent_check['history_sha256'])

    def test_failed_batches_and_corrupt_publication_do_not_commit_history(self):
        original = self.imported(8, 8)
        before = self.files()
        bad = self.patch(8, 0, 1, 1)
        self.cli('document.edit', document=original, expected_revision=0,
                 operations=[self.migration(), self.patch(1,1,1,1), bad], error='INVALID_SAMPLE_STORE')
        self.assertEqual(self.files(), before)
        self.save(original)
        action = dict(type='edit', operations=[self.migration(), self.patch(1,1,1,1)])
        review = self.cli('session.dry_run', session_id='work', request_id='change', expected_revision=0,
                          action=action, options=dict(include_document=True))
        staged = self.grid(review['proposed_document'])['staged']
        self.assertEqual(len(staged['pending']), 1)
        path = self.root/'.inkbolt/assets'/(staged['pending'][0]['sha256']+'.native-tile')
        path.write_bytes(b'foreign content')
        before = self.files(); states = self.states()
        self.cli('session.apply_proposal', proposal=review['proposal'], action=action, error='SAMPLE_TILE_CORRUPT')
        self.assertEqual(self.files(), before)
        self.assertEqual(self.states(), states)
        path.unlink() # Only this test's deliberately created collision.
        result = self.cli('session.apply_proposal', proposal=review['proposal'], action=action)
        self.assertEqual(result['receipt'], review['predicted_receipt'])
        self.check_native(result['document'], lambda x,y: [50001,60003,4321,65535] if (x,y)==(1,1) else native.pixel(x,y))

    def test_review_document_can_create_a_session_without_persisting_payloads(self):
        original = self.imported(8,8)
        self.save(original)
        action = dict(type='edit', operations=[self.migration(), self.patch(1,1,1,1)])
        review = self.cli('session.dry_run', session_id='work', request_id='new', expected_revision=0,
                          action=action, options=dict(include_document=True))
        proposed = review['proposed_document']; before = self.blocks()
        result = self.cli('session.create', session_id='copy', request_id='create', document=proposed)
        self.assertNotIn('staged', self.grid(result['document']))
        self.assertEqual(len(self.states('copy')), 1)
        self.assertEqual(self.states('work')[0][1], self.cli('session.read', session_id='work')['state_sha256'])
        for name, data in before.items(): self.assertEqual(self.blocks()[name], data)
        replay = self.cli('session.create', session_id='copy', request_id='create', document=proposed)
        self.assertTrue(replay['replayed']); self.assertEqual(replay['receipt'], result['receipt'])

    def test_versions_staged_corruption_and_hidden_legacy_dependencies_fail_explicitly(self):
        original = self.imported(4,4)
        legacy = self.edit(original, [self.patch(0,0,4,4)])['document']
        self.save(legacy)
        review = self.cli('session.dry_run', session_id='work', request_id='new', expected_revision=0,
                          action=dict(type='edit', operations=[self.migration()]), options=dict(include_document=True))
        proposed = review['proposed_document']; before = self.files()
        for version in [0,1,3]:
            bad = copy.deepcopy(proposed); self.grid(bad)['storage_version'] = version
            self.cli('document.validate', document=bad, error='INVALID_STORED_SAMPLES')
        bad = copy.deepcopy(proposed); self.grid(bad)['patches'] = self.grid(legacy)['patches']
        self.cli('document.validate', document=bad, error='INVALID_STORED_SAMPLES')
        bad = copy.deepcopy(proposed); self.grid(bad)['staged']['pending'][0]['data_hex'] = '00'
        self.cli('document.validate', document=bad, error='INVALID_REQUEST')
        self.assertEqual(self.files(), before)
        path = self.root/'.inkbolt/assets'/(self.grid(original)['base']['tiles'][0]+'.native-tile')
        path.write_bytes(b'corrupted hidden original')
        before = self.files()
        self.cli('document.edit', document=legacy, expected_revision=legacy['revision'],
                 operations=[self.migration()], error='SAMPLE_TILE_CORRUPT')
        self.assertEqual(self.files(), before)

    def test_all_native_depths_and_channels_keep_exact_bits_through_migration_and_edit(self):
        for depth, size, code in [('u8',1,'B'),('u16',2,'H'),('f32',4,'f')]:
            for channels in [2,4]:
                with self.subTest(depth=depth, channels=channels):
                    color, alpha = dict(u8=(23,255),u16=(5321,65535),f32=(.125,1.0))[depth]
                    values = ([color]*(channels-1)+[alpha])*8
                    if depth == 'f32':
                        values[0] = -0.0
                        values[channels*2] = struct.unpack('<f', b'\x01\0\0\0')[0]
                    source = native.tiff(4,2,values,depth=depth,n=channels)
                    original = self.imported(4,2,data=source)
                    replacement = ([color+1]*(channels-1)+[alpha] if depth!='f32'
                                   else [.25]*(channels-1)+[.75])
                    payload = struct.pack('<'+code*channels, *replacement)
                    op = dict(op='sample_replace',id='pixels',region=dict(x=1,y=0,width=1,height=1),data_hex=payload.hex())
                    legacy = self.edit(original,[op])['document']
                    current = self.edit(legacy,[self.migration()])['document']
                    expected = bytearray(struct.pack('<'+code*len(values),*values))
                    expected[channels*size:2*channels*size] = payload
                    header = b'INKTILE1'+struct.pack('<IIBBBB',4,2,size,channels,0,0)
                    identity = self.grid(current)['base']['tiles'][0]
                    self.assertEqual(self.blocks()[identity+'.native-tile'],header+expected)
                    op['region']['y'] = 1
                    current = self.edit(current,[op])['document']
                    expected[5*channels*size:6*channels*size] = payload
                    identity = self.grid(current)['base']['tiles'][0]
                    self.assertEqual(self.blocks()[identity+'.native-tile'],header+expected)
                    self.assertEqual(hashlib.sha256(header+expected).hexdigest(),identity)
                    self.assertNotIn('patches', self.grid(current))

    def test_native_brush_and_retouch_share_the_block_commit_path(self):
        original = self.imported(8,8)
        migrated = self.edit(original,[self.migration()])['document']
        operations = [
            dict(op='brush_stroke',id='pixels',stroke=brush([[4,4]],diameter=3)),
            dict(op='retouch',id='pixels',options=dict(source_id='pixels',region=dict(x=3,y=3,width=2,height=2),
                 mode=dict(type='clone'),source_transform=[1,0,0,1,-2,-2])),
        ]
        legacy = self.edit(original,operations)['document']
        changed = self.edit(migrated,operations)
        self.assertNotIn('patches',self.grid(changed['document']))
        self.assertNotIn('staged',self.grid(changed['document']))
        self.assertEqual(decode(self.exported(changed['document']))[0],decode(self.exported(legacy))[0])
        for change in changed['changes']:
            self.assertFalse(change['details']['preparation_writes_files'])
            self.assertNotIn('files_written',change['details'])

    def test_default_import_survives_260_edits_and_legacy_selection_stays_explicit(self):
        original = self.imported(257,3,storage={})
        self.assertEqual(self.grid(original)['storage_version'],2)
        explicit = self.cli('sample.import',scoped=False,source_path=str(self.root/'original.bin'),
                            id='native',color_policy='assume_srgb',
                            storage=dict(store_root=str(self.root/'.inkbolt/assets')))
        self.assertEqual(explicit['document'],original)
        legacy = self.imported(257,3)
        self.assertNotIn('storage_version',self.grid(legacy))
        self.assertEqual(dict(self.grid(original),storage_version=1),dict(self.grid(legacy),storage_version=1))
        originals = self.blocks()
        with closing(Client(('--tools','core'),workspace=self.root)) as client:
            client.initialize()
            response = client.tool('run',command='sample.import',arguments=dict(
                source_path='original.bin',id='native',storage={},color_policy='assume_srgb'))
            self.assertFalse(response['isError'],response)
            imported = response['structuredContent']['result']
            self.assertEqual(imported['document'],original)
            self.assertEqual(imported['storage']['storage_version'],2)
            self.assertEqual(imported['storage']['created_tiles'],0)
            current = original
            for index in range(260):
                values = [v for x in range(257) for v in [1000+index,x,4321,65535]]
                current = client.success('document.edit',document=current,expected_revision=current['revision'],
                                         operations=[self.patch(0,1,257,1,values)])['document']
                self.assertNotIn('patches',self.grid(current))
                self.assertNotIn('staged',self.grid(current))
                self.assertLess(len(json.dumps(current)),2500)
            self.check_native(current,lambda x,y:[1259,x,4321,65535] if y==1 else native.pixel(x,y))
        self.check_native(original,native.pixel)
        for name,blob in originals.items():self.assertEqual(self.blocks()[name],blob)
        before = self.files()
        self.cli('sample.import',source_path='original.bin',id='bad',storage=dict(storage_version=3),error='INVALID_REQUEST')
        self.assertEqual(self.files(),before)

    def test_profile_and_hdr_migration_review_commit_history_preserve_exact_bits(self):
        cases = [('profiled_rgb',depth,n) for depth in ['u8','u16','f32'] for n in [2,4]]
        cases += [('linear_srgb','f32',n) for n in [2,4]]
        for encoding,depth,n in cases:
            with self.subTest(encoding=encoding,depth=depth,channels=n):
                unit,code,maximum = dict(u8=(1,'B',255),u16=(2,'H',65535),f32=(4,'f',1))[depth]
                values = ([maximum//3]*(n-1)+[maximum])*258
                if depth=='f32':
                    values = ([.125]*(n-1)+[1.0])*258
                    values[0] = -0.0
                    values[n] = 2**-149
                    if encoding=='linear_srgb':values[2*n:3*n] = [-4]*(n-1)+[0.0]
                raw = bytearray(struct.pack('<'+code*len(values),*values))
                policy = 'assume_linear_srgb' if encoding=='linear_srgb' else 'assume_srgb'
                original = self.imported(data=native.tiff(129,2,values,depth=depth,n=n),color_policy=policy)
                grid = self.grid(original)
                if encoding=='profiled_rgb':
                    spec = dict(grid['base']['spec'],encoding=encoding)
                    manifest,blocks = self.typed_blocks(spec,raw)
                    for name,blob in blocks.items():
                        path = self.root/'.inkbolt/assets'/(name+'.native-tile')
                        if path.exists():self.assertEqual(path.read_bytes(),blob)
                        else:
                            with path.open('xb') as stream:stream.write(blob)
                    grid['base'] = manifest
                    grid['profile'] = embedded(linear_profile()) if n==4 else dict(type='builtin',name='linear_srgb')
                grid['sampling'] = 'bilinear'
                original['items'][0]['transform'] = [1,0,0,1,0.25,0.5]
                profile = copy.deepcopy(grid.get('profile'))
                replacement = [maximum//2]*(n-1)+[maximum] if depth!='f32' else [.375]*(n-1)+[.75]
                payload = struct.pack('<'+code*n,*replacement)
                op = dict(op='sample_replace',id='pixels',region=dict(x=127,y=1,width=2,height=1),data_hex=(payload*2).hex())
                legacy = self.edit(original,[op])['document']
                raw[(129+127)*n*unit:] = payload*2
                session = f'{encoding}-{depth}-{n}'
                initial = self.cli('session.create',session_id=session,request_id='create',document=legacy)
                before = self.files(); rows = self.states(session)
                action = dict(type='edit',operations=[self.migration()])
                review = self.cli('session.dry_run',session_id=session,request_id='migrate',expected_revision=0,
                                  action=action,options=dict(include_document=True))
                self.assertEqual(self.files(),before)
                self.assert_native_bits(review['proposed_document'],raw)
                committed = self.cli('session.apply_proposal',proposal=review['proposal'],action=action)
                current = committed['document']; current_grid = self.grid(current)
                self.assertEqual(committed['receipt'],review['predicted_receipt'])
                self.assertEqual(self.states(session)[:len(rows)],rows)
                self.assert_native_bits(current,raw)
                self.assertEqual(current_grid.get('profile'),profile)
                self.assertEqual(current_grid['sampling'],'bilinear')
                self.assertEqual(current['items'][0]['transform'],original['items'][0]['transform'])
                self.assertNotIn('staged',current_grid)
                self.assertEqual(decode(self.exported(current,'f32'))[0],decode(self.exported(legacy,'f32'))[0])
                undone = self.cli('session.apply',session_id=session,request_id='undo',expected_revision=1,action=dict(type='undo'))
                self.assertEqual(undone['document'],dict(initial['document'],revision=2))
                redone = self.cli('session.apply',session_id=session,request_id='redo',expected_revision=2,action=dict(type='redo'))
                self.assertEqual(redone['document'],dict(current,revision=3))
                op['region']['y'] = 0
                changed = self.edit(current,[op])['document']
                raw[127*n*unit:129*n*unit] = payload*2
                self.assert_native_bits(changed,raw)
                self.assertEqual(self.grid(changed).get('profile'),profile)
                self.assertTrue(self.cli('session.verify',session_id=session)['valid'])


if __name__ == '__main__':
    unittest.main()
