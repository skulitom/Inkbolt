"""Check blend operators, composed groups and independent rasterization of vector PDF."""
import base64
from contextlib import closing
from fractions import Fraction
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest

from native_vector_fixture import pdf as fixture_pdf
from pdf_reader import Pdf
from test_blending_cli import encoded, over, premul
import test_editing_cli as editing
from test_profiles_cli import builtin, embedded
from test_mcp import Client

try:
    import pymupdf
except ModuleNotFoundError as error:
    if error.name != 'pymupdf':
        raise
    pymupdf = None


MODES = ('normal multiply screen darken lighten color_burn color_dodge overlay hard_light '
         'soft_light difference exclusion hue saturation color luminosity').split()
PAPER = premul([255, 255, 255, 255])


def rectangle(key, x, y, width, height, rgba, **controls):
    return dict(id=key, content=dict(type='vector', fill=rgba,
                geometry=dict(shape='rect', x=x, y=y, width=width, height=height)), **controls)


def document(width, height, items):
    return dict(schema_version=2, id='blend-sheet', kind='vector', width=width, height=height,
                color_space='srgb', items=items)


def mode_sheet():
    items, samples = [], []
    colors = [([30, 110, 220, 255], [202, 46, 137, 255]),
              ([210, 74, 31, 140], [37, 205, 120, 183]),
              ([0, 0, 0, 0], [202, 46, 137, 185]),
              ([0, 255, 110, 255], [255, 0, 255, 255])]
    for row, mode in enumerate(MODES):
        for column, (back, front) in enumerate(colors):
            x, y = 4*column, 4*row
            opacity = Fraction(3, 4) if column in (1, 2) else Fraction(1)
            items.append(rectangle(f'b-{row}-{column}', x, y, 4, 4, back))
            items.append(rectangle(f's-{row}-{column}', x, y, 4, 4, front,
                                   blend=mode, opacity=float(opacity)))
            result = over(premul(back), premul(front), opacity, mode)
            samples.append((mode, x+2, y+2, encoded(over(PAPER, result))[:3]))
    return document(4*len(colors), 4*len(MODES), items), samples


def palette_sheets():
    rng = random.Random(74021)
    pairs = [([rng.randrange(256) for _ in range(4)], [rng.randrange(256) for _ in range(4)])
             for _ in range(24)]
    pairs.extend([([1, 254, 128, 255], [254, 1, 127, 255]),
                  ([127, 128, 128, 255], [1, 240, 188, 255]),
                  ([1, 240, 188, 255], [127, 128, 128, 255]),
                  ([250, 250, 250, 255], [0, 255, 1, 255])])
    for mode in MODES:
        items, samples = [], []
        for i, (back, front) in enumerate(pairs):
            items.extend([rectangle(f'back-{i}', i*4, 0, 4, 4, back),
                          rectangle(f'front-{i}', i*4, 0, 4, 4, front, blend=mode)])
            rgb = encoded(over(PAPER, over(premul(back), premul(front), mode=mode)))[:3]
            samples.append((mode, i*4+2, 2, rgb))
        yield document(4*len(pairs), 4, items), samples


def group_sheet():
    back, front, stripe = [80, 130, 205, 255], [200, 66, 90, 255], [60, 165, 31, 180]
    outlined = rectangle('outlined', 25, 1, 6, 6, front, blend='difference', opacity=.75)
    outlined['content']['stroke'] = dict(width=4, color=stripe)
    groups = document(32, 8, [
        rectangle('base', 0, 0, 32, 8, back),
        dict(id='isolated', content=dict(type='group', isolated=True), blend='screen', opacity=.5),
        rectangle('a', 0, 0, 8, 8, front, parent='isolated'),
        rectangle('b', 4, 0, 4, 8, stripe, parent='isolated', blend='multiply'),
        dict(id='through', content=dict(type='group', isolated=False)),
        rectangle('c', 8, 0, 8, 8, front, parent='through', blend='overlay'),
        dict(id='faded', content=dict(type='group', isolated=False), opacity=.5),
        rectangle('d', 16, 0, 8, 8, front, parent='faded', blend='overlay'),
        outlined,
    ])
    first = over(premul(back), premul(front), Fraction(1, 2), 'screen')
    both = over(premul(back), over(premul(front), premul(stripe), mode='multiply'), Fraction(1, 2), 'screen')
    through = over(premul(back), premul(front), mode='overlay')
    faded = over(premul(back), premul(front), Fraction(1, 2), 'overlay')
    overlap = over(premul(back), over(premul(front), premul(stripe)), Fraction(3, 4), 'difference')
    group_samples = [('isolated', 2, 4, encoded(first)[:3]), ('overlap', 6, 4, encoded(both)[:3]),
                     ('pass-through', 12, 4, encoded(through)[:3]), ('faded group', 20, 4, encoded(faded)[:3]),
                     ('fill and stroke', 26, 4, encoded(overlap)[:3])]
    return groups, group_samples


def direct_patch_pdf(artwork):
    """Paint the paired rectangles directly on paper, without forms or Inkbolt."""
    items = artwork['items']
    states, colors, commands = [], [], []
    for i, item in enumerate(items):
        rgba = item['content']['fill']
        mode = ''.join(word.title() for word in item.get('blend', 'normal').split('_'))
        alpha = rgba[3]/255 * item.get('opacity', 1)
        states.append(f'/A{i} << /ca {alpha} /BM /{mode} >>')
        colors.append(f'/C{i} [/Indexed /DeviceRGB 0 <{bytes(rgba[:3]).hex()}>]')
        commands.append(f'q /A{i} gs /C{i} cs 0 scn {4*(i//2)} 0 4 4 re f Q')
    data = '\n'.join(commands).encode()
    resources = f"/ExtGState << {' '.join(states)} >> /ColorSpace << {' '.join(colors)} >>"
    page = (f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {2*len(items)} 4] '
            f'/Group << /S /Transparency /CS /DeviceRGB /I true >> /Resources << {resources} >> /Contents 4 0 R >>')
    return fixture_pdf({1: b'<< /Type /Catalog /Pages 2 0 R >>',
                        2: b'<< /Type /Pages /Count 1 /Kids [3 0 R] >>',
                        3: page.encode(), 4: f'<< /Length {len(data)} >>\nstream\n'.encode() + data + b'\nendstream'
                        }).replace(b'%PDF-1.7', b'%PDF-2.0', 1)


def poppler_rgb(data, dpi, width, height):
    with tempfile.TemporaryDirectory() as directory:
        stem = Path(directory)/'sheet'
        path = stem.with_suffix('.pdf')
        path.write_bytes(data)
        subprocess.run(['pdftoppm', '-r', str(dpi), '-singlefile', str(path), str(stem)], check=True, timeout=20)
        magic, size, maximum, pixels = stem.with_suffix('.ppm').read_bytes().split(b'\n', 3)
    assert (magic, maximum) == (b'P6', b'255') and list(map(int, size.split())) == [width, height]
    assert len(pixels) == width*height*3
    return pixels


class PdfBlendTests(unittest.TestCase):
    invoke = editing.EditingCliTests.invoke

    def pdf(self, doc, **options):
        return self.invoke(dict(command='document.export', format='pdf', document=doc, pdf_options=options))

    def test_standard_forms_and_version_follow_painted_modes(self):
        doc, _ = mode_sheet()
        result = self.pdf(doc)
        reader = Pdf(result)
        names = {''.join(word.title() for word in mode.split('_')) for mode in MODES}
        self.assertEqual(set(self.invoke(dict(command='capabilities'))['pdf']['display_blend_modes']), set(MODES))
        self.assertEqual(set(result['pdf']['blend_modes']), names - {'Normal'})
        self.assertEqual(result['pdf']['version'], '2.0')
        self.assertTrue(reader.data.startswith(b'%PDF-2.0'))
        self.assertNotIn('black_point_compensation', result['pdf'])
        self.assertTrue(any('PDF 2.0 endpoint' in loss for loss in result['losses']))
        self.assertEqual(result['pdf']['image_pixels'], 0)
        self.assertEqual(len(reader.paths()), len(doc['items']))
        self.assertEqual([path['color'] for path in reader.paths()],
                         [[v/255 for v in item['content']['fill'][:3]] for item in doc['items']])
        self.assertEqual({v['BM'] for v in reader.objects.values() if v.get('Type') == 'ExtGState'}, names)
        for mode, version in [('multiply', '1.7'), ('color_burn', '2.0'), ('color_dodge', '2.0')]:
            doc['items'] = [rectangle('top', 0, 0, 4, 4, [12, 44, 99, 255], blend=mode)]
            self.assertEqual(self.pdf(doc)['pdf']['version'], version)
        doc['output_profile'] = builtin('srgb')
        calibrated = Pdf(self.pdf(doc))
        doc['output_profile'] = embedded(calibrated.streams[calibrated.pages[0]['Group']['CS'][1]])
        self.assertEqual(self.pdf(doc)['pdf']['blend_modes'], ['ColorDodge'])

    def test_unsupported_blends_fail_before_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            output = dict(format='pdf', output_root=directory, file_name='blend.pdf')
            for mode, options, profile in [('linear_burn', {}, None), ('hue', {'color':'native_inks'}, None),
                                            ('multiply', {}, builtin('linear_srgb'))]:
                doc = document(4, 4, [rectangle('top', 0, 0, 4, 4, [10, 50, 70, 255], blend=mode)])
                if profile:
                    doc['output_profile'] = profile
                error = self.invoke(dict(command='document.publish', document=doc,
                                         output=dict(output, pdf_options=options)), 1)
                self.assertEqual((error['code'], error['item_id']), ('UNSUPPORTED', 'top'))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_workspace_preflight_and_publication_keep_the_composed_forms(self):
        artwork, _ = group_sheet()
        direct = self.pdf(artwork)
        with tempfile.TemporaryDirectory() as directory, closing(Client(('--tools', 'essentials'), workspace=directory)) as client:
            client.initialize()
            output = dict(format='pdf', file_name='proof.pdf')
            def request(command):
                return client.tool('run', command=command, arguments=dict(document=artwork, output=output))['structuredContent']
            self.assertTrue(request('document.preflight')['result']['ready'])
            path = Path(directory)/'proof.pdf'
            self.assertFalse(path.exists())
            receipt = request('document.publish')['result']
            self.assertEqual(receipt['pdf']['blend_modes'], ['Difference','Multiply','Overlay','Screen'])
            self.assertEqual(path.read_bytes(), Pdf(direct).data)
            self.assertEqual(request('document.publish')['error']['code'], 'OUTPUT_EXISTS')
            artwork.update(width=128, height=96)
            output.update(file_name='marked.pdf', pdf_options=dict(marks=dict(crop=True)))
            self.assertFalse(request('document.preflight')['result']['ready'])
            self.assertEqual(request('document.publish')['error']['code'], 'UNSUPPORTED')
            self.assertFalse((Path(directory)/'marked.pdf').exists())

    def test_working_rgb_preview_agrees_with_the_independent_color_oracle(self):
        for artwork, samples in [mode_sheet(), group_sheet(), *palette_sheets()]:
            result = self.invoke(dict(command='document.export', document=artwork, format='png'))
            width, _, rgba, _ = editing.png_pixels(base64.b64decode(result['data'], validate=True))
            for label, x, y, rgb in samples:
                start = (y*width+x)*4
                actual = encoded(over(PAPER, premul(rgba[start:start+4])))[:3]
                with self.subTest(mode=label, x=x, y=y):
                    self.assertLessEqual(max(abs(round(a)-round(b)) for a,b in zip(actual,rgb)), 1)

    @unittest.skipUnless(shutil.which('pdftoppm'), 'independent PDF pixel check requires pdftoppm')
    def test_independent_renderer_matches_mode_and_group_samples(self):
        for artwork, expected in [mode_sheet(), group_sheet(), *palette_sheets()]:
            width = artwork['width']
            pixels = poppler_rgb(Pdf(self.pdf(artwork)).data, 96, width, artwork['height'])
            # Reader versions disagree on hue, saturation and two singular
            # endpoints. Measure this reader on independently authored operators.
            paired = all(item['content']['type'] == 'vector' for item in artwork['items'])
            if paired:
                direct_width = 4*len(expected)
                direct = poppler_rgb(direct_patch_pdf(artwork), 72, direct_width, 4)
            for i, (mode, x, y, rgb) in enumerate(expected):
                pos = (y*width+x)*3
                with self.subTest(mode=mode, x=x, y=y):
                    actual = pixels[pos:pos+3]
                    target = list(map(round, rgb))
                    if paired:
                        offset = (2*direct_width + 4*i+2)*3
                        reference = direct[offset:offset+3]
                        for channel in range(3):
                            sensitive = (mode in ('hue', 'saturation') or
                                         (mode,x,y,channel) in (('color_burn',14,22,1), ('color_dodge',14,26,0)))
                            if sensitive and abs(reference[channel]-target[channel]) > 3:
                                target[channel] = reference[channel]
                    self.assertLessEqual(max(abs(a-b) for a,b in zip(actual,target)), 3, (list(actual),target))

    @unittest.skipUnless(pymupdf, 'independent PDF 2.0 pixel check requires PyMuPDF')
    def test_pdf2_renderer_matches_the_corrected_endpoints_and_all_mode_samples(self):
        for artwork, samples in [mode_sheet(), group_sheet()]:
            for profile in (None, builtin('srgb')):
                if profile:
                    artwork['output_profile'] = profile
                artifact = self.pdf(artwork)
                with pymupdf.open(stream=Pdf(artifact).data, filetype='pdf') as pdf:
                    raster = pdf[0].get_pixmap(dpi=96, alpha=False)
                    for label, x, y, rgb in samples:
                        with self.subTest(mode=label, x=x, y=y, calibrated=bool(profile)):
                            actual = raster.pixel(x,y)
                            target = [round(v) for v in rgb]
                            self.assertLessEqual(max(abs(a-b) for a,b in zip(actual,target)), 3, (actual,target))

    @unittest.skipUnless(pymupdf, 'independent byte-color check requires PyMuPDF')
    def test_reader_retains_adjacent_byte_colors_before_dodge(self):
        back, front = [1, 254, 128, 255], [254, 1, 127, 255]
        artwork = document(12, 4, [rectangle('back', 0, 0, 4, 4, back),
                                   rectangle('front', 0, 0, 4, 4, front, blend='color_dodge'),
                                   rectangle('back-swatch', 4, 0, 4, 4, back),
                                   rectangle('front-swatch', 8, 0, 4, 4, front)])
        for profile in (None, builtin('srgb')):
            if profile:
                artwork['output_profile'] = profile
            encoded_page = Pdf(self.pdf(artwork))
            self.assertEqual([path['color'] for path in encoded_page.paths()],
                             [[v/255 for v in rgba[:3]] for rgba in (back, front, back, front)])
            with pymupdf.open(stream=encoded_page.data, filetype='pdf') as pdf:
                raster = pdf[0].get_pixmap(dpi=96, alpha=False)
                self.assertEqual(raster.pixel(2, 2), (255, 255, 255))
                # An explicit ICC profile adds the reader's conversion to its output RGB.
                for x, rgba in [(6, back), (10, front)]:
                    error = max(abs(a-b) for a,b in zip(raster.pixel(x, 2), rgba[:3]))
                    self.assertLessEqual(error, 1 if profile else 0)
