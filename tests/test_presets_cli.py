"""Preset contracts checked against independent pixel and physical-page arithmetic."""
import base64
from contextlib import closing
import copy
from fractions import Fraction
import hashlib
import itertools
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import pdf_reader
from test_cli import EXE, ROOT
import test_editing_cli as editing
from test_editing_cli import png_pixels
from test_mcp import Client


SIZES = {'icon256': (256, 256), 'presentation_hd': (1920, 1080),
         'presentation_qhd': (2560, 1440), 'social_square': (1080, 1080),
         'social_portrait': (1080, 1350), 'social_story': (1080, 1920)}
PAPERS = {'a4': (Fraction(1050, 127), Fraction(1485, 127)),
          'a5': (Fraction(740, 127), Fraction(1050, 127)),
          'letter': (Fraction(17, 2), Fraction(11))}


def screen(size='icon256', kind='vector', background=None, **kw):
    return dict(type='screen', size=size, kind=kind,
                background=background or dict(type='transparent'), **kw)


def print_page(paper='a4', orientation='portrait', resolution_ppi=300, color='display_rgb', **kw):
    return dict(type='print_page', paper=paper, orientation=orientation,
                resolution_ppi=resolution_ppi, color=color, **kw)


def box(parent, color, rect=(4, 6, 10, 8)):
    x, y, width, height = rect
    return dict(id='art', parent=parent, content=dict(type='vector',
        geometry=dict(shape='rect', x=x, y=y, width=width, height=height), fill=color))


class PresetTests(unittest.TestCase):
    invoke = editing.EditingCliTests.invoke

    def create(self, preset, **kw):
        return self.invoke(dict(command='preset.create', version=1, id='original', preset=preset, **kw))

    def export(self, p, d=None):
        # Publication settings, minus the destination, are ordinary export arguments.
        options = copy.deepcopy(p['delivery'])
        options.pop('artboard_id')
        options.pop('include_bleed')
        return self.invoke(dict(command='document.export', document=d or p['document'], **options))

    def test_catalog_dimensions_determinism_and_shared_cli_mcp_schemas(self):
        catalog = self.invoke(dict(command='preset.list'))
        self.assertEqual({s['size']: tuple(s['pixels']) for s in catalog['screen']}, SIZES)
        self.assertLess(len(json.dumps(catalog).encode()), 4096)
        caps = self.invoke(dict(command='capabilities'))
        self.assertEqual(caps['presets'], catalog)
        self.assertTrue({'preset.list', 'preset.create'} <= set(caps['commands']))
        with closing(Client(('--tools', 'core'))) as client:
            client.initialize()
            def call(command, **args):
                r = client.tool('run', command=command, arguments=args)
                self.assertFalse(r['isError'], r)
                return r['structuredContent']['result']
            self.assertEqual(call('preset.list'), catalog)
            for size, kind in itertools.product(SIZES, ['vector', 'raster']):
                p = call('preset.create', version=1, id='original', preset=screen(size, kind))
                self.assertEqual(p, self.create(screen(size, kind)))
                d = p['document']
                self.assertEqual((d['width'], d['height']), SIZES[size])
                self.assertEqual(d['kind'], kind)
                self.assertEqual(d['revision'], 0)
                canonical = json.dumps(p['specification'], sort_keys=True, separators=(',', ':')).encode()
                self.assertEqual(p['specification_sha256'], hashlib.sha256(canonical).hexdigest())
                self.assertEqual(p['content_parent_id'], 'canvas')
                self.assertIsNone(d['items'][0]['content']['frame']['background'])
                self.assertEqual(call('document.validate', document=d), d)
                self.assertLess(len(json.dumps(p).encode()), 8192)
            schema = call('schema.lookup', name='preset.create', full=True)
            text = json.dumps(schema)
            self.assertIn('PresetSpec', text)
            self.assertIn('PresetBackground', text)
            self.assertNotIn('additionalProperties": true', text)

    def test_alpha_backgrounds_and_independent_pixels_preserve_editable_sources(self):
        for kind, background in itertools.product(['vector', 'raster'],
                [dict(type='transparent'), dict(type='solid', color=[30, 70, 100])]):
            p = self.create(screen(kind=kind, background=background))
            d = p['document']
            if kind == 'vector':
                item = box('canvas', [210, 110, 20, 128])
            else:
                item = dict(id='art', parent='canvas', transform=[1, 0, 0, 1, 4, 6],
                            content=dict(type='raster', width=10, height=8,
                                         rgba_hex='d26e1480'*80))
            d = self.invoke(dict(command='document.edit', document=d, expected_revision=0,
                                operations=[dict(op='add', item=item)]))['document']
            original = copy.deepcopy(d)
            d['metadata'] = dict(private={'secret': 'source only'})
            a = self.export(p, d)
            w, h, pixels, chunks = png_pixels(base64.b64decode(a['data']))
            self.assertEqual((w, h), (256, 256))
            bg = background.get('color')
            expected = bytearray(bytes(bg+[255] if bg else [0]*4)*(w*h))
            rgba = [210, 110, 20, 128] if bg is None else [
                (v*128+b*127+127)//255 for v, b in zip([210, 110, 20], bg)] + [255]
            for y in range(6, 14):
                for x in range(4, 14):
                    expected[(y*w+x)*4:(y*w+x+1)*4] = bytes(rgba)
            self.assertEqual(pixels, expected)
            self.assertNotIn(b'tEXt', chunks)
            self.assertEqual(d['items'], original['items'])
            self.assertEqual(d['metadata']['private']['secret'], 'source only')
            preview = self.invoke(dict(command='document.preview', document=d, options=p['preview']))
            self.assertEqual(png_pixels(base64.b64decode(preview['artifact']['data']))[:3], (w, h, pixels))

    def test_every_screen_size_delivers_all_independently_checked_pixels(self):
        for size, dimensions in SIZES.items():
            with self.subTest(size=size):
                p = self.create(screen(size, background=dict(type='solid', color=[18, 42, 70])))
                d = p['document']
                d['items'].append(box('canvas', [210, 110, 20, 255]))
                before = copy.deepcopy(d)
                a = self.export(p, d)
                w, h, pixels, chunks = png_pixels(base64.b64decode(a['data']))
                self.assertEqual((w, h), dimensions)
                expected = bytearray(bytes([18, 42, 70, 255])*(w*h))
                for y in range(6, 14):
                    expected[(y*w+4)*4:(y*w+14)*4] = bytes([210, 110, 20, 255])*10
                self.assertEqual(pixels, expected)
                self.assertEqual(d, before)

    def test_physical_pages_all_sizes_orientations_densities_and_asymmetric_bleed(self):
        bleed = dict(top=9, right=12, bottom=6, left=3)
        for paper, orientation, ppi in itertools.product(PAPERS, ['portrait', 'landscape'], [72, 96, 150, 300]):
            with self.subTest(paper=paper, orientation=orientation, ppi=ppi):
                p = self.create(print_page(paper, orientation, ppi, bleed_px=bleed))
                d = p['document']
                size = PAPERS[paper][::(-1 if orientation == 'landscape' else 1)]
                pixels = [float(v*ppi) for v in size]
                self.assertEqual(d['vector_canvas']['size_px'], pixels)
                self.assertEqual([d['width'], d['height']], [math.ceil(v) for v in pixels])
                frame = d['items'][0]['content']['frame']
                self.assertEqual(frame['logical_size'], pixels)
                self.assertEqual(frame['bleed'], bleed)
                self.assertEqual(d['revision'], 0)
                # Native PDF parsing reads physical boxes, not the engine's receipt.
                a = self.export(p)
                pdf = pdf_reader.Pdf(a)
                page = pdf.pages[0]
                unit = page.get('UserUnit', 1)
                expected_media = [0, 0, float(size[0]*72)+15*72/ppi, float(size[1]*72)+15*72/ppi]
                for actual, expected in zip(page['MediaBox'], expected_media):
                    self.assertAlmostEqual(actual*unit, expected, delta=1e-9)
                expected_trim = [3*72/ppi, 6*72/ppi,
                                 float(size[0]*72)+3*72/ppi, float(size[1]*72)+6*72/ppi]
                for actual, expected in zip(page['TrimBox'], expected_trim):
                    self.assertAlmostEqual(actual*unit, expected, delta=1e-9)
                self.assertEqual(p['physical']['calibrated'], False)
                self.assertIsNone(p['physical']['output_profile'])

    def test_native_inks_remain_explicit_and_do_not_offer_an_uncalibrated_rgb_preview(self):
        p = self.create(print_page(color='native_inks'))
        self.assertIsNone(p['preview'])
        d = p['document']
        self.assertEqual(d['vector_canvas']['process_space'], 'cmyk')
        d['swatches'] = dict(ink=dict(name='Original ink', definition=dict(type='process',
            color=dict(space='cmyk', components=[.25, .5, .75, .125]))))
        d['items'].append(box('page', dict(swatch='ink')))
        pdf = pdf_reader.Pdf(self.export(p, d))
        self.assertTrue(any(b'0.25 0.5 0.75 0.125 k' in data for data in pdf.streams.values()))
        self.assertNotIn(b'/ICCBased', pdf.data)
        e = self.invoke(dict(command='document.preview', document=d,
                             options=dict(render_options=dict(evaluation='tiled'))), 1)
        self.assertEqual(e['code'], 'SWATCH_PREVIEW_REQUIRED')

    def test_unknown_versions_choices_fields_and_mismatched_resource_profiles_fail(self):
        for request in [dict(version=0), dict(version=2), dict(version=2**32-1),
                        dict(preset=screen(size='guess')), dict(preset=screen(extra=1)),
                        dict(preset=screen(background=dict(type='solid', color=[0, 0, 256]))),
                        dict(preset=screen(background=dict(type='transparent', color=[0, 0, 0]))),
                        dict(preset=print_page(resolution_ppi=200)),
                        dict(preset=print_page(resolution_ppi=-1)),
                        dict(preset=print_page(bleed_px=dict(left=4097))),
                        dict(preset=screen(kind='raster', resource_profile='large_vector')),
                        dict(preset=print_page(resource_profile='large_raster')),
                        dict(id='../escape'), dict(output_root='C:/unexpected')]:
            with self.subTest(request=request):
                self.invoke(dict(command='preset.create', version=1, id='original', preset=screen()) | request, 1)
        self.assertEqual(self.invoke(dict(command='preset.create', version=1, id='original',
            preset=screen(), control=dict(timeout_ms=0)), 1)['code'], 'TIMEOUT')

    def test_saved_proposal_delivery_retry_history_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory, closing(Client(('--tools', 'core'), workspace=directory)) as client:
            client.initialize()
            def call(command, **args):
                r = client.tool('run', command=command, arguments=args)
                self.assertFalse(r['isError'], r)
                return r['structuredContent']['result']
            p = call('preset.create', version=1, id='original', preset=screen())
            call('session.create', session_id='design', request_id='create', document=p['document'], response_mode='compact')
            action = dict(type='edit', operations=[dict(op='add', item=box('canvas', [10, 60, 200, 255]))])
            review = call('session.dry_run', session_id='design', request_id='art', expected_revision=0,
                          action=action, options=dict(preview=True))
            receipt = call('session.apply_proposal', proposal=review['proposal'], action=action, response_mode='compact')
            replay = call('session.apply_proposal', proposal=review['proposal'], action=action, response_mode='compact')
            self.assertEqual(receipt['receipt_summary'], replay['receipt_summary'])
            self.assertTrue(replay['replayed'])
            ref = dict(session_id='design', revision=1)
            output = p['delivery'] | dict(file_name='original.png')
            checked = call('document.preflight', document=ref, output=output)
            self.assertTrue(checked['ready'])
            self.assertFalse((Path(directory)/'original.png').exists())
            published = call('session.publish', session_id='design', expected_revision=1, output=output)
            raw = (Path(directory)/'original.png').read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), published['sha256'])
            self.assertEqual(png_pixels(raw)[:3], png_pixels(base64.b64decode(review['preview']['data']))[:3])
            collision = client.tool('run', command='session.publish', arguments=dict(session_id='design', expected_revision=1, output=output))
            self.assertEqual(collision['structuredContent']['error']['code'], 'OUTPUT_EXISTS')
            call('session.apply', session_id='design', request_id='undo', expected_revision=1, action=dict(type='undo'))
            old = call('document.validate', document=dict(session_id='design', revision=0))
            self.assertEqual(old, p['document'])
            current = call('session.read', session_id='design')
            self.assertEqual(current['document']['items'], p['document']['items'])
            self.assertEqual((Path(directory)/'original.png').read_bytes(), raw)

    def test_packaged_workflow_runs_and_preserves_existing_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'workflow'
            argv = [sys.executable, str(ROOT/'examples/preset_workflow.py'), '--inkbolt', str(EXE), '--output', str(output)]
            process = subprocess.run(argv, capture_output=True, timeout=30)
            self.assertEqual(process.returncode, 0, process.stderr.decode())
            self.assertTrue((output/'artwork.png').is_file())
            self.assertTrue((output/'page.pdf').is_file())
            original = {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()}
            repeated = subprocess.run(argv, capture_output=True, timeout=15)
            self.assertNotEqual(repeated.returncode, 0)
            self.assertEqual(original, {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()})


if __name__ == '__main__':
    unittest.main()
