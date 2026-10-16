"""Original image bytes, independent placement pixels and atomic resource checks."""
import base64
import copy
import hashlib
from pathlib import Path
import random
import tempfile
import unittest
from urllib.parse import quote_from_bytes
import zlib
import test_images_cli as fixtures
import test_svg_import_cli as support
import test_svg_symbols_cli as symbols
import test_session_proposals as proposals
import test_profiles_cli as profiles
from test_mcp import Client


RED = [255, 0, 0, 255]
BLUE = [0, 0, 255, 255]


def data_uri(data, media='image/png'):
    return f'data:{media};base64,' + base64.b64encode(data).decode()


def picture(attrs='', data=None, href=None):
    if data is None:
        data = fixtures.png(2, 2, bytes(RED)*4)
    return f'<image href="{href or data_uri(data)}" {attrs}/>'


class SvgImageTests(unittest.TestCase):
    invoke = support.SvgImportTests.invoke
    pixels = support.SvgImportTests.pixels
    check = symbols.SvgSymbolTests.check

    def imported(self, text, expected=0, **options):
        options.setdefault('images', dict(sampling='nearest'))
        return self.invoke(dict(command='svg.import', id='images', source=dict(kind='text', text=text), **options), expected)

    def test_encoded_source_identity_exact_pixels_and_svg_roundtrip(self):
        raw = bytes(RED + BLUE + [0, 255, 0, 255] + [0, 0, 0, 0])
        source = fixtures.png(2, 2, raw)
        result = self.check(picture('id="art" x="4" y="2" width="4" height="4"', source),
                            [(4, 2, 6, 4, RED), (6, 2, 8, 4, BLUE), (4, 4, 6, 6, [0, 255, 0, 255])])
        asset = next(iter(result['document']['assets'].values()))
        self.assertEqual(asset['storage']['type'], 'encoded')
        self.assertEqual(base64.b64decode(asset['storage']['data_base64']), source)
        self.assertEqual(asset['sha256'], hashlib.sha256(fixtures.canonical(2, 2, raw)).hexdigest())
        self.assertEqual(asset['provenance']['source_sha256'], hashlib.sha256(source).hexdigest())
        self.invoke(dict(command='asset.verify', asset=asset))
        mapped = next(row for row in result['mapping'] if row['source_id'] == 'art')
        self.assertIn(mapped['asset_id'], result['document']['assets'])
        self.assertEqual(next(i for i in result['document']['items'] if i['id'] == mapped['image_item_id'])['content']['type'], 'image')
        exported = self.invoke(dict(command='document.export', document=result['document'], format='svg'))
        again = self.imported(exported['data'])
        for scale in (1, 2):
            self.assertEqual(self.pixels(result['document'], scale), self.pixels(again['document'], scale))

    def test_encoded_images_exceed_raw_inline_capacity_without_store_writes(self):
        raw = bytes(RED) * (257*257)
        source = fixtures.png(257, 257, raw)
        result = self.check(picture('width="8" height="8"', source), [(0, 0, 8, 8, RED)])
        asset = next(iter(result['document']['assets'].values()))
        self.assertEqual((asset['width'], asset['height']), (257, 257))
        self.assertLess(len(asset['storage']['data_base64']), 4096)
        self.invoke(dict(command='asset.verify', asset=asset))
        # The old raw-pixel embedding limit is unchanged.
        error = self.invoke(dict(command='asset.embed', asset=asset), 1)
        self.assertEqual(error['code'], 'RESOURCE_LIMIT')

    def test_intrinsic_auto_and_percentage_dimensions(self):
        source = fixtures.png(4, 2, bytes(RED)*8)
        for attrs, box in [('', (0, 0, 4, 2)), ('width="8"', (0, 0, 8, 4)),
                           ('height="4" width="auto"', (0, 0, 8, 4)),
                           ('x="25%" y="25%" width="50%" height="50%" preserveAspectRatio="none"', (8, 6, 24, 18))]:
            self.check(picture(attrs, source), [(*box, RED)])
        self.check('<svg x="4" width="16" height="16" viewBox="0 0 8 8">' +
                   picture('x="50%" width="50%" height="50%"', source) + '</svg>', [(12, 2, 20, 6, RED)])

    def test_all_meet_alignments_slice_and_none(self):
        for hx, dx in [('Min', 0), ('Mid', 4), ('Max', 8)]:
            for vy, dy in [('Min', 0), ('Mid', 4), ('Max', 8)]:
                aspect = f'x{hx}Y{vy}'
                self.check(picture(f'width="16" height="8" preserveAspectRatio="{aspect}"'), [(dx, 0, dx+8, 8, RED)])
                self.check(picture(f'width="8" height="16" preserveAspectRatio="{aspect}"'), [(0, dy, 8, dy+8, RED)])
        source = fixtures.png(2, 1, bytes(RED+BLUE))
        for aspect, boxes in [('xMidYMid slice', [(4, 2, 8, 10, RED), (8, 2, 12, 10, BLUE)]),
                              ('none', [(4, 2, 8, 10, RED), (8, 2, 12, 10, BLUE)]),
                              ('none slice', [(4, 2, 8, 10, RED), (8, 2, 12, 10, BLUE)])]:
            self.check(picture(f'x="4" y="2" width="8" height="8" preserveAspectRatio="{aspect}"', source), boxes)
        self.check(picture('x="8" y="2" width="8" height="8" preserveAspectRatio="xMidYMid slice" overflow="visible"', source),
                   [(4, 2, 12, 10, RED), (12, 2, 20, 10, BLUE)])

    def test_masks_and_object_box_clips_use_the_positioning_rectangle(self):
        source = fixtures.png(4, 2, bytes(RED)*8)
        for definition, effect in [('<clipPath id="c" clipPathUnits="objectBoundingBox"><rect y=".25" width="1" height=".25"/></clipPath>', 'clip-path="url(#c)"'),
                                   ('<mask id="m" maskContentUnits="objectBoundingBox"><rect y=".25" width="1" height=".25" fill="white"/></mask>', 'mask="url(#m)"')]:
            self.check('<defs>'+definition+'</defs>'+picture(f'x="4" y="2" width="8" height="8" {effect}', source),
                       [(4, 4, 12, 6, RED)])
        self.check(picture('x="2" y="2" width="4" height="4" transform="translate(2,2) scale(2)" opacity=".5"'),
                   [(6, 6, 14, 14, [255, 0, 0, 128])])

    def test_reuse_shares_assets_and_remaps_all_stored_item_ids(self):
        result = self.check('<defs>'+picture('id="art" width="4" height="4"')+'</defs>'
                            '<use href="#art" x="4"/><use href="#art" x="12"/>',
                            [(4, 0, 8, 4, RED), (12, 0, 16, 4, RED)])
        self.assertEqual(len(result['document']['assets']), 1)
        ids = {i['id'] for i in result['document']['items']}
        rows = [row for row in result['mapping'] if row['source_id'] == 'art']
        self.assertEqual(len({row['image_item_id'] for row in rows}), 1)
        for row in rows:
            self.assertIn(row['image_item_id'], ids)
            self.assertIn(row['viewport_item_id'], ids)
        changed = self.invoke(dict(command='document.edit', document=result['document'], expected_revision=0,
            operations=[dict(op='transform', id=rows[0]['image_item_id'], matrix=[1, 0, 0, 1, 0, 0])]))['document']
        expected = self.check('<rect x="4" width="2" height="2" fill="red"/><rect x="12" width="2" height="2" fill="red"/>',
                              [(4, 0, 6, 2, RED), (12, 0, 14, 2, RED)])
        self.assertEqual(self.pixels(changed), self.pixels(expected['document']))

    def test_local_paths_require_root_preserve_bytes_and_embed_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root/'tile space.png'; original = fixtures.png(2, 2, bytes(RED)*4)
            path.write_bytes(original)
            text = support.svg(picture('width="4" height="4"', href='tile%20space.png'))
            self.assertEqual(self.imported(text, 1)['code'], 'SVG_IMAGE_ROOT_REQUIRED')
            result = self.imported(text, images=dict(source_root=temporary))
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(sorted(p.name for p in root.iterdir()), ['tile space.png'])
            path.unlink()
            self.assertEqual(self.pixels(result['document']), self.pixels(self.check(picture('width="4" height="4"'), [(0, 0, 4, 4, RED)])['document']))
            for name in ('../tile.png', '%2e%2e/tile.png', '/tile.png', 'C:/tile.png', 'https://invalid.example/tile.png', '//host/tile.png', 'folder%5ctile.png', 'tile.png?query', 'tile.png#part'):
                with self.subTest(name=name):
                    self.imported(support.svg(picture(href=name)), 1, images=dict(source_root=temporary))

    def test_symlink_cannot_escape_the_explicit_source_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); inside=root/'inside'; inside.mkdir()
            external=root/'external.png'; external.write_bytes(fixtures.png(2, 2, bytes(RED)*4))
            try: (inside/'link.png').symlink_to(external)
            except OSError as error: self.skipTest(f'Host cannot create fixture symlink: {error}')
            self.assertEqual(self.imported(support.svg(picture(href='link.png')), 1,
                                          images=dict(source_root=str(inside)))['code'], 'SVG_UNSUPPORTED')

    def test_uri_forms_default_color_and_sampling_and_jpeg(self):
        source = fixtures.png(2, 2, bytes(RED)*4, tagged=False)
        result = self.invoke(dict(command='svg.import', id='default', source=dict(kind='text', text=support.svg(picture(data=source)))))
        asset = next(iter(result['document']['assets'].values()))
        self.assertEqual(asset['provenance']['interpretation'], 'assumed_srgb')
        self.assertEqual(next(i['content']['sampling'] for i in result['document']['items'] if i['content']['type']=='image'), 'bilinear')
        self.imported(support.svg(picture(data=source)), 1, images=dict(color_policy='require_srgb'))
        for href in ('data:image/png,'+quote_from_bytes(source, safe=''), data_uri(source).replace('=', '%3D')):
            self.check(picture(href=href), [(0, 0, 2, 2, RED)])
        legacy = picture().replace('href=', 'xlink:href=')
        self.check(legacy, [(0, 0, 2, 2, RED)], attrs='width="32" height="24" xmlns:xlink="http://www.w3.org/1999/xlink"')
        gray = self.imported(support.svg(picture(data=fixtures.png(4, 4, bytes([128,128,128,255])*16)), 'width="4" height="4"'))
        jpeg = self.invoke(dict(command='document.export', document=gray['document'], format='jpeg',
                               image_options=dict(quality=100, chroma='full', matte=[0,0,0])))
        encoded = base64.b64decode(jpeg['data'])
        self.check(picture('width="4" height="4"', href=data_uri(encoded,'image/jpeg')),
                   [(0, 0, 4, 4, [128,128,128,255])])

    def test_zero_hidden_and_unused_images_validate_resources(self):
        result = self.check(picture('id="zero" width="0"')+picture('x="4" display="none"')+
                            '<rect x="8" width="2" height="2" fill="blue"/>', [(8, 0, 10, 2, BLUE)])
        row=next(row for row in result['mapping'] if row['source_id']=='zero')
        self.assertTrue(row['empty_image'])
        self.assertIn(row['image_item_id'], {i['id'] for i in result['document']['items']})
        bad=data_uri(b'not an image')
        for body in [picture('width="0"',href=bad), picture('display="none"',href=bad), '<defs>'+picture(href=bad)+'</defs>']:
            self.imported(support.svg(body),1)

    def test_sampling_styles_cascade_and_inherit_without_losing_source_pixels(self):
        source = fixtures.png(2, 1, bytes(RED + BLUE))
        text = '<style>.smooth {image-rendering:auto}</style><g image-rendering="pixelated">' + \
            picture('id="pixel" width="4" height="2" image-rendering="inherit"', source) + \
            picture('id="smooth" class="smooth" x="8" width="4" height="2"', source) + '</g>'
        result = self.imported(support.svg(text), images={})
        items = {i['id']:i for i in result['document']['items']}
        for name, sampling in [('pixel','nearest'),('smooth','bilinear')]:
            row = next(row for row in result['mapping'] if row['source_id']==name)
            self.assertEqual(items[row['image_item_id']]['content']['sampling'], sampling)
        self.assertTrue(any('noninteger' in loss for loss in result['losses']))
        self.imported(support.svg('<style>.unused {image-rendering:unknown}</style>'+picture()),1)

    def test_explicit_profile_conversion_preserves_source_and_verifiable_interpretation(self):
        profile = profiles.linear_profile()
        raw = bytes([64,128,192,255])*4
        source = fixtures.png(2,2,raw,tagged=False,extra=[(b'iCCP',b'original\0\0'+zlib.compress(profile))])
        self.imported(support.svg(picture(data=source)),1)
        result = self.imported(support.svg(picture(data=source)), images=dict(color_policy='convert_srgb',sampling='nearest'))
        asset = next(iter(result['document']['assets'].values()))
        self.assertEqual(asset['provenance']['source_profile_sha256'],hashlib.sha256(profile).hexdigest())
        self.assertEqual(base64.b64decode(asset['storage']['data_base64']),source)
        normalized = self.invoke(dict(command='asset.embed',asset=asset))
        rgba = bytes.fromhex(normalized['storage']['rgba_hex'])
        expected = bytes(v if i%4==3 else round(255*profiles.encode_srgb(v/255)) for i,v in enumerate(raw))
        self.assertLessEqual(max(abs(a-b) for a,b in zip(rgba,expected)),1)
        self.assertTrue(any('Gamut clipping' in loss or 'gamut clipping' in loss for loss in result['losses']))

    def test_snapshot_and_aggregate_decoded_budgets_stay_enforced(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = random.Random(207).randbytes(400*400*4)
            source = fixtures.png(400,400,raw)
            (root/'noise.png').write_bytes(source)
            text = support.svg(picture('width="4" height="4"',href='noise.png'))
            self.assertEqual(self.imported(text,1,images=dict(source_root=temporary))['code'],'RESOURCE_LIMIT')
            large = self.imported(text,resource_profile='large_vector',images=dict(source_root=temporary))
            asset = next(iter(large['document']['assets'].values()))
            self.assertEqual(asset['sha256'],hashlib.sha256(fixtures.canonical(400,400,raw)).hexdigest())
            self.invoke(dict(command='asset.verify',asset=asset))
            self.assertEqual(sorted(p.name for p in root.iterdir()),['noise.png'])
        body = picture(data=fixtures.png(8192,4096,bytes(RED)*(8192*4096))) + \
            picture(data=fixtures.png(8192,4097,bytes(BLUE)*(8192*4097)))
        error = self.imported(support.svg(body),1,resource_profile='large_vector')
        self.assertEqual(error['code'],'RESOURCE_LIMIT')
        self.assertIn('SVG images exceed the decoded-pixel budget',error['message'])

    def test_workspace_root_is_explicit_and_failed_batch_leaves_no_resources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); inputs=root/'inputs'; inputs.mkdir()
            original=fixtures.png(2,2,bytes(RED)*4); (inputs/'art.png').write_bytes(original)
            client=Client(('--tools','core'),workspace=root); self.addCleanup(client.close); client.initialize()
            document=client.success('document.create',id='atomic',kind='vector',width=32,height=24)
            client.success('session.create',session_id='atomic',request_id='create',document=document)
            action=dict(type='edit',operations=[dict(op='add_svg',svg=picture(href='art.png'),images=dict(source_root='inputs')),
                                               dict(op='transform',id='missing',matrix=[1,0,0,1,0,0])])
            before={str(p):p.read_bytes() for p in proposals.workspace_files(root) if p.is_file()}
            preview=client.success('session.dry_run',session_id='atomic',request_id='preview',expected_revision=0,
                                   action=dict(type='edit',operations=action['operations'][:1]),options=dict(include_document=True))
            self.assertEqual(len(preview['proposed_document']['assets']),1)
            failed=client.tool('session.apply',session_id='atomic',request_id='batch',expected_revision=0,action=action)
            self.assertTrue(failed['isError'])
            self.assertEqual(failed['structuredContent']['error']['code'],'NOT_FOUND')
            self.assertEqual(client.success('session.read',session_id='atomic')['document'],document)
            self.assertEqual(before,{str(p):p.read_bytes() for p in proposals.workspace_files(root) if p.is_file()})
            accepted=client.tool('run',command='svg.import',arguments=dict(id='local',source=dict(kind='text',text=support.svg(picture(href='art.png'))),images=dict(source_root='inputs')))
            self.assertFalse(accepted['isError'])
            self.assertEqual(len(accepted['structuredContent']['result']['document']['assets']),1)
            error=client.tool('run',command='svg.import',arguments=dict(id='local',source=dict(kind='text',text=support.svg(picture(href='inputs/art.png')))))
            self.assertEqual(error['structuredContent']['error']['code'],'SVG_IMAGE_ROOT_REQUIRED')

    def test_corruption_limits_and_unsupported_image_semantics(self):
        source=fixtures.png(2,2,bytes(RED)*4)
        for href in ['data:image/svg+xml,%3Csvg/%3E', 'data:image/png;base64,???', 'data:image/jpeg;base64,'+base64.b64encode(source).decode(),
                     data_uri(source[:-4]), 'missing%2.png']:
            self.imported(support.svg(picture(href=href)),1)
        for attrs in ['width="-1"','height="-1%"','preserveAspectRatio="bad"','style="object-fit:contain"','image-rendering="unknown"']:
            self.imported(support.svg(picture(attrs)),1)
        # Finite percentage tokens can overflow only after viewport resolution.
        # Nonpainting images must not bypass this and return null size receipts.
        for attrs in ['width="0" height="1e308%"', 'width="2" height="1e308%" display="none"',
                      'height="0" width="1e308%"', 'width="0" y="1e308%"']:
            with self.subTest(attrs=attrs):
                error=self.imported(support.svg(picture(attrs),'width="32768" height="32768"'),1)
                self.assertEqual(error['code'],'SVG_INVALID')
                self.assertIn('Nonfinite',error['message'])
        self.assertEqual(self.imported(support.svg('<mask id="m">'+picture()+'</mask>'),1)['code'],'SVG_UNSUPPORTED')
        too_big=fixtures.png(8193,8192,b'',raw=b'')
        self.assertEqual(self.imported(support.svg(picture(data=too_big)),1)['code'],'RESOURCE_LIMIT')
        result=self.imported(support.svg(picture()))
        asset=next(iter(result['document']['assets'].values()))
        altered=copy.deepcopy(asset); altered['sha256']='0'*64
        self.assertEqual(self.invoke(dict(command='asset.verify',asset=altered),1)['code'],'ASSET_CORRUPT')
        altered=copy.deepcopy(asset); altered['storage']['data_base64']=base64.b64encode(b'changed').decode()
        self.assertEqual(self.invoke(dict(command='asset.verify',asset=altered),1)['code'],'ASSET_CORRUPT')

    def test_mcp_file_proposal_detects_changed_source_and_retry_undo_remain_atomic(self):
        client=Client(('--tools','core')); self.addCleanup(client.close); client.initialize()
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); path=root/'source.png'; original=fixtures.png(2,2,bytes(RED)*4); path.write_bytes(original)
            common=dict(session_root=str(root/'sessions'),session_id='images')
            document=self.invoke(dict(command='document.create',id='target',kind='vector',width=32,height=24))
            client.success('session.create',**common,request_id='create',document=document)
            action=dict(type='edit',operations=[dict(op='add_svg',svg=picture('id="art" width="4" height="4"',href='source.png'),images=dict(source_root=temporary))])
            before={str(p):p.read_bytes() for p in proposals.workspace_files(root) if p.is_file()}
            preview=client.success('session.dry_run',**common,request_id='insert',expected_revision=0,action=action,options=dict(include_document=True))
            self.assertEqual(before,{str(p):p.read_bytes() for p in proposals.workspace_files(root) if p.is_file()})
            path.write_bytes(fixtures.png(2,2,bytes(BLUE)*4))
            failed=self.invoke(dict(command='session.apply_proposal',session_root=common['session_root'],proposal=preview['proposal'],action=action),1)
            self.assertEqual(failed['code'],'PROPOSAL_MISMATCH')
            self.assertEqual(client.success('session.read',**common)['document'],document)
            path.write_bytes(original)
            applied=client.success('session.apply_proposal',session_root=common['session_root'],proposal=preview['proposal'],action=action)
            self.assertEqual(applied['document'],preview['proposed_document'])
            ids={i['id'] for i in applied['document']['items']}
            receipt=applied['receipt']['changes'][0]['details']
            row=next(row for row in receipt['mapping'] if row['source_id']=='art')
            self.assertIn(row['image_item_id'],ids); self.assertIn(row['asset_id'],applied['document']['assets'])
            path.unlink()
            retry=client.success('session.apply',**common,request_id='insert',expected_revision=0,action=action)
            self.assertTrue(retry['replayed'])
            self.assertEqual(self.pixels(applied['document']),self.pixels(preview['proposed_document']))
            undone=client.success('session.apply',**common,request_id='undo',expected_revision=1,action=dict(type='undo'))
            self.assertEqual(undone['document']['items'],[])
            redone=client.success('session.apply',**common,request_id='redo',expected_revision=2,action=dict(type='redo'))
            self.assertEqual(redone['document']['assets'],applied['document']['assets'])
