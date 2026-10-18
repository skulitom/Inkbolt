"""Independent scalar blocks, mask pixels, pure review and durable history."""
import copy
import hashlib
import struct
import unittest

import test_agent_workspace as workspace
from test_masks_cli import opacity, byte
from test_samples_cli import decode
import test_stored_samples as samples
from cmyk_fixtures import cmyk_profile
from test_profiles_cli import embedded
from test_sample_conversion_cli import tiff


def scalar(w, h, value):
    """Construct the documented format without using the engine's writer."""
    def header(width, height):
        return b'INKSCAL1' + struct.pack('<IIBBBB', width, height, 1, 1, 0, 0)
    tiles, blobs = [], {}
    for top in range(0, h, 128):
        for left in range(0, w, 128):
            tw, th = min(128, w-left), min(128, h-top)
            data = header(tw, th) + bytes(value(x, y) for y in range(top, top+th) for x in range(left, left+tw))
            digest = hashlib.sha256(data).hexdigest()
            tiles.append(digest)
            blobs[digest] = data
    identity = hashlib.sha256(b'INKSCGR1' + header(w, h) + struct.pack('<I', 128)
                              + b''.join(bytes.fromhex(v) for v in tiles)).hexdigest()
    manifest = dict(version=1, spec=dict(width=w, height=h), tiles=tiles, sha256=identity)
    return manifest, blobs


class NativeMaskTests(unittest.TestCase):
    setUp = workspace.AgentWorkspaceTests.setUp
    cli = workspace.AgentWorkspaceTests.cli
    save = workspace.AgentWorkspaceTests.save
    ref = workspace.AgentWorkspaceTests.ref
    imported = samples.StoredSampleTests.imported
    files = samples.StoredSampleTests.files
    blocks = samples.StoredSampleTests.blocks

    def mask(self, w=133, h=131, pending=False, **controls):
        value = lambda x, y: (x*71+y*13) % 256
        manifest, blobs = scalar(w, h, value)
        grid = dict(base=manifest)
        if pending:
            grid['staged'] = dict(version=1, manifest=manifest,
                                  pending=[dict(sha256=k, data_hex=v.hex()) for k, v in sorted(blobs.items())])
        else:
            store = self.root/'.inkbolt/assets'
            store.mkdir(parents=True, exist_ok=True)
            for name, data in blobs.items():
                path = store/(name+'.native-tile')
                if path.exists():
                    self.assertEqual(path.read_bytes(), data)
                else:
                    path.write_bytes(data)
        mask = dict(width=w, height=h, gray_hex='', native=grid, **controls)
        inline = dict(mask, gray_hex=bytes(value(x, y) for y in range(h) for x in range(w)).hex())
        del inline['native']
        return mask, inline

    def document(self, w=11, h=9):
        d = self.cli('document.create', id='mask-test', kind='vector', width=w, height=h)
        d['items'] = [dict(id='ink', content=dict(type='vector', geometry=dict(shape='rect', x=0, y=0, width=w, height=h), fill=[31,147,219,255]))]
        return d

    def test_pixels_controls_and_filter_masks_match_independent_coverage(self):
        for sampling in ['nearest', 'bilinear']:
            d = self.document()
            mask, inline = self.mask(feather=2, invert=True, density=.63, sampling=sampling,
                                     transform=[1,0,0,1,-125.25,-124.75], linked=False, clip=False)
            d['items'][0]['mask'] = mask
            result = self.cli('document.render', document=d)
            actual = bytes.fromhex(result['data'])
            for y in range(d['height']):
                for x in range(d['width']):
                    self.assertEqual(actual[(y*d['width']+x)*4+3], byte(opacity(inline, (x+.5,y+.5))))
            old = copy.deepcopy(d); old['items'][0]['mask'] = inline
            self.assertEqual(self.cli('document.render', document=old), result)
            for target in [d, old]:
                target['items'][0]['filters'] = [dict(id='blur',operator=dict(type='box',radius=1),mask=target['items'][0].pop('mask'),opacity=.73)]
            self.assertEqual(self.cli('document.render', document=d),self.cli('document.render', document=old))

    def test_tiled_filters_and_file_free_tiff_replay_match_whole_inline_output(self):
        d = self.document(253,129)
        mask, inline = self.mask(253,129,feather=2,sampling='bilinear',density=.77,clip=False)
        d['items'][0]['filters']=[dict(id='blur',operator=dict(type='box',radius=1),mask=mask,opacity=.6)]
        d['items'][0]['mask']=mask
        old=copy.deepcopy(d)
        old['items'][0]['mask']=inline
        old['items'][0]['filters'][0]['mask']=inline
        image_options=dict(depth='u16',channels='rgba',compression='none')
        expected=self.cli('document.export',document=old,format='tiff',image_options=image_options)
        actual=self.cli('document.export',document=d,format='tiff',image_options=image_options,render_options=dict(evaluation='tiled'))
        self.assertEqual(decode(actual)[0],decode(expected)[0])
        output=dict(file_name='native-mask.tiff',format='tiff',image_options=image_options,render_options=dict(evaluation='tiled'))
        before=self.files()
        preflight=self.cli('document.preflight',document=d,output=output)
        self.assertTrue(preflight['ready'],preflight)
        self.assertEqual(self.files(),before)
        published=self.cli('document.publish',document=d,output=output)
        self.assertEqual(preflight['prepared_output']['sha256'],published['sha256'])

    def test_prepress_item_and_filter_masks_match_inline_inks(self):
        d=self.document(7,5)
        mask, inline=self.mask(9,7,feather=1,invert=True,density=.6,sampling='bilinear')
        options=dict(profile=embedded(cmyk_profile()),antialias='none',samples=[[x,y] for y in range(5) for x in range(7)])
        for filtering in [False,True]:
            a=copy.deepcopy(d); b=copy.deepcopy(d)
            for target,plane in [(a,mask),(b,inline)]:
                target['items'][0]['mask']=plane
                if filtering:
                    target['items'][0]['filters']=[dict(id='blur',operator=dict(type='box',radius=1),mask=plane,opacity=.6)]
            actual=self.cli('document.prepress',document=a,options=options)
            expected=self.cli('document.prepress',document=b,options=options)
            self.assertEqual(actual['samples'],expected['samples'])
            self.assertEqual(actual['interleaved_sha256'],expected['interleaved_sha256'])

    def test_native_u16_source_keeps_rgb_and_uses_exact_mask_coverage(self):
        d = self.imported(133,131,storage={})
        mask, _ = self.mask()
        d['items'][0]['mask'] = mask
        d['width'], d['height'] = 7,6
        d['items'][0]['transform'] = [1,0,0,1,-125,-125]
        out = self.cli('document.export',document=d,format='tiff',image_options=dict(depth='u16',channels='rgba',compression='none'))
        actual, _ = decode(out)
        expected = []
        for y in range(125,131):
            for x in range(125,132):
                alpha = (x*71+y*13)%256
                expected.extend(samples.pixel(x,y)[:3]+[alpha*257] if alpha else [0,0,0,0])
        self.assertEqual(actual,expected)

    def test_all_six_native_sample_types_preserve_color_and_exact_alpha(self):
        mask, inline=self.mask(132,3)
        for depth, maximum in [('u8',255),('u16',65535),('f32',1)]:
            for channels in [2,4]:
                values=[]; expected=[]
                for y in range(3):
                    for x in range(132):
                        color=[((x*17+y*29+c*31)%256) * (maximum/256 if depth=='f32' else 1 if depth=='u8' else 257) for c in range(channels-1)]
                        values.extend(color+[maximum])
                        coverage=(x*71+y*13)%256
                        alpha=coverage*(maximum/255)
                        if depth=='f32':
                            alpha=struct.unpack('<f',struct.pack('<f',alpha))[0]
                        else:
                            alpha=round(alpha)
                        expected.extend(color+[alpha] if alpha else [0]*channels)
                name=f'source-{depth}-{channels}.tiff'
                source=tiff(132,3,values,depth=depth,n=channels)
                (self.root/name).write_bytes(source)
                d=self.cli('sample.import',source_path=name,id='native',color_policy='assume_srgb',storage={})['document']
                d['items'][0]['mask']=mask
                options=dict(depth=depth,channels='rgba' if channels==4 else 'gray_alpha',compression='none')
                actual=decode(self.cli('document.export',document=d,format='tiff',image_options=options))[0]
                self.assertEqual(actual,expected,(depth,channels))
                old=copy.deepcopy(d);old['items'][0]['mask']=inline
                self.assertEqual(actual,decode(self.cli('document.export',document=old,format='tiff',image_options=options))[0])
                self.assertEqual((self.root/name).read_bytes(),source)

    def test_private_review_commit_retry_undo_backup_and_old_identity(self):
        d = self.document()
        initial = self.save(d)['document']
        self.assertNotIn('native',str(initial))
        mask, _ = self.mask(pending=True)
        action = dict(type='edit',operations=[dict(op='mask',id='ink',mask=mask)])
        before = self.files()
        review = self.cli('session.dry_run',session_id='work',request_id='mask',expected_revision=0,
                          action=action,options=dict(include_document=True,preview=True,compare_pixels=True))
        self.assertEqual(self.files(),before)
        self.assertIn('staged',review['proposed_document']['items'][0]['mask']['native'])
        done = self.cli('session.apply_proposal',proposal=review['proposal'],action=action)
        self.assertNotIn('staged',done['document']['items'][0]['mask']['native'])
        self.assertEqual(done['receipt'],review['predicted_receipt'])
        self.assertTrue(self.cli('session.apply_proposal',proposal=review['proposal'],action=action)['replayed'])
        self.assertEqual(self.cli('document.render',document=self.ref(1)),self.cli('document.render',document=review['proposed_document']))
        committed_blocks = self.blocks()
        undo = self.cli('session.apply',session_id='work',request_id='undo',expected_revision=1,action=dict(type='undo'))
        self.assertEqual(undo['document'],dict(initial,revision=2))
        redo = self.cli('session.apply',session_id='work',request_id='redo',expected_revision=2,action=dict(type='redo'))
        self.assertEqual(redo['document'],dict(done['document'],revision=3))
        self.assertTrue(self.cli('session.verify',session_id='work')['valid'])
        backup = self.cli('session.backup',session_id='work',expected_revision=3,output=dict(file_name='mask-history.sqlite3'))
        self.cli('session.recover',session_id='work',session_root='recovered',source=backup['backup'])
        self.assertEqual(self.cli('document.render',document=dict(session_id='work',session_root='recovered',revision=3)),
                         self.cli('document.render',document=self.ref(3)))
        self.assertEqual(self.blocks(),committed_blocks)

    def test_hidden_unselected_corruption_refuses_render_edit_transfer_and_commit(self):
        d = self.document(1,1)
        mask, _ = self.mask()
        d['items'][0]['mask'] = mask
        self.save(d)
        path = self.root/'.inkbolt/assets'/(mask['native']['base']['tiles'][-1]+'.native-tile')
        data = path.read_bytes(); path.write_bytes(data[:-1]+bytes([data[-1]^1]))
        before = self.files()
        self.cli('document.render',document=d,error='SAMPLE_TILE_CORRUPT')
        d['items'][0]['visible'] = False
        d['items'][0]['mask']['enabled'] = False
        report = self.cli('document.check',document=d)
        self.assertEqual(report['status'],'fail')
        self.assertTrue(any('mask/native' in str(v) for v in report['issues']))
        self.cli('document.edit',document=d,expected_revision=0,operations=[dict(op='mask_link',id='ink',linked=False)],error='SAMPLE_TILE_CORRUPT')
        self.cli('document.edit',document=self.document(1,1),expected_revision=0,
                 operations=[dict(op='transfer',transfer=dict(source=d,ids=['ink'],prefix='copy',verify_resources=True))],error='SAMPLE_TILE_CORRUPT')
        self.cli('session.apply',session_id='work',request_id='bad',expected_revision=0,
                 action=dict(type='edit',operations=[dict(op='mask_link',id='ink',linked=False)]),error='SAMPLE_TILE_CORRUPT')
        self.assertEqual(self.files(),before)
        self.assertEqual(self.cli('session.read',session_id='work')['document']['revision'],0)

    def test_native_masks_above_inline_ceiling_and_explicit_structural_refusals(self):
        mask, _ = self.mask(1024,1024)
        d = self.document(7,5)
        mask['transform']=[1,0,0,1,-1017,-1019]
        d['items'][0]['mask']=mask
        result = bytes.fromhex(self.cli('document.render',document=d)['data'])
        self.assertEqual(result[3::4],bytes((x*71+y*13)%256 for y in range(1019,1024) for x in range(1017,1024)))
        self.cli('document.export',document=d,format='svg',error='UNSUPPORTED_NATIVE_MASK')
        self.cli('document.render',document=d,control=dict(timeout_ms=0),error='TIMEOUT')
        mask['gray_hex']='00'
        self.cli('document.render',document=d,error='INVALID_DOCUMENT')


if __name__ == '__main__':
    unittest.main()
