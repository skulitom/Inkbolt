"""Vector PDF artwork masks checked against compositing equations and two readers."""
from contextlib import closing
import base64
import math
import shutil
import unittest

from pdf_reader import Pdf
from synthetic_font import geometric_font
import test_agent_workspace as workspace
from test_artwork_masks_cli import group, mask, rect, source
from test_editing_cli import png_pixels
from test_ink_delivery_cli import cmyk, reference
from test_layer_clipping_cli import layer
from test_mcp import Client
from test_pdf_blends_cli import document, poppler_rgb, pymupdf
from test_profiles_cli import builtin
from test_swatches_cli import spot


BLACK = [0, 0, 0, 255]
RED = [230, 30, 22, 170]
GREEN = [10, 205, 145, 128]


def luminance(rgb):
    return sum(c * w for c, w in zip(rgb, (.2125, .7154, .0721))) / 255


def paper(width, height, items):
    return dict(document(width, height, items), resolution_ppi=72)


def shared_sheet():
    items = [source(opacity=.8, transform=[1, 0, 0, 1, 2, 3]),
             rect('red', w=18, h=16, color=RED, parent='source'),
             rect('green', x=9, y=4, w=18, h=14, color=GREEN, parent='source')]
    for x, mode in [(0, 'alpha'), (40, 'luminance')]:
        reveal = dict(source='source', mode=mode, region=[0, 0, 27, 20],
                      region_transform=[1, 0, 0, 1, 4, 1], transform=[1, 0, 0, 1, 0, 2])
        items.append(rect(mode, w=40, h=28, color=BLACK, artwork_mask=reveal,
                          transform=[1, 0, 0, 1, x, 0]))
    return paper(80, 28, items)


def shared_coverage(x, y):
    alpha_mode = x < 40
    x = x % 40
    if not (4 <= x < 31 and 3 <= y < 23):
        return 0
    a = RED[3]/255 if 2 <= x < 20 and 5 <= y < 21 else 0
    b = GREEN[3]/255 if 11 <= x < 29 and 9 <= y < 23 else 0
    if alpha_mode:
        return .8 * (b + a*(1-b))
    return .8 * (luminance(GREEN)*b + luminance(RED)*a*(1-b))


def gradient_sheet(kind):
    field = dict(type=kind, stops=[dict(offset=0, color=RED), dict(offset=1, color=GREEN)])
    if kind == 'linear':
        field.update(start=[0, 0], end=[32, 0])
    else:
        field.update(center=[16, 10], radius=14)
    items = [source(), group('cut', parent='source', opacity=.75,
                             clip=dict(geometry=dict(shape='rect', x=2, y=2, width=28, height=16))),
             rect('ramp', w=32, h=20, color=field, parent='cut')]
    for x, mode in [(0, 'alpha'), (32, 'luminance')]:
        items.append(rect(mode, w=32, h=20, color=BLACK, transform=[1, 0, 0, 1, x, 0],
                          artwork_mask=dict(source='source', mode=mode, region=[0, 0, 32, 20])))
    return paper(64, 20, items)


def gradient_coverage(kind, x, y):
    u = x % 32
    if not (2 <= u < 30 and 2 <= y < 18):
        return 0
    t = u/32 if kind == 'linear' else min(1, math.hypot(u-16, y-10)/14)
    rgba = [a + (b-a)*t for a, b in zip(RED, GREEN)]
    return .75 * rgba[3]/255 * (1 if x < 32 else luminance(rgba))


def read_mupdf(data, width, height):
    with pymupdf.open(stream=data, filetype='pdf') as pdf:
        pix = pdf[0].get_pixmap(dpi=288, alpha=False)
        assert (pix.width, pix.height) == (4*width, 4*height)
        return pix.samples


def reader_errors(rgb, width, height, coverage):
    for y in range(height):
        for x in range(width):
            seen = sum(rgb[3*((4*y+j)*4*width+4*x+i)] for i in (1, 2) for j in (1, 2))/4
            expected = 255*(1-coverage(x+.5, y+.5))
            yield abs(round(seen)-round(expected))


class PdfArtworkMaskTests(unittest.TestCase):
    setUp = workspace.AgentWorkspaceTests.setUp
    cli = workspace.AgentWorkspaceTests.cli

    def export(self, doc, **options):
        return self.cli('document.export', document=doc, format='pdf', pdf_options=options)

    def test_shared_source_is_nonprinting_and_both_modes_keep_their_own_placement(self):
        self.assertEqual(self.cli('capabilities')['pdf']['artwork_masks']['modes'], ['alpha', 'luminance'])
        doc = shared_sheet()
        result = self.export(doc)
        pdf = Pdf(result)
        states = [obj['SMask'] for obj in pdf.objects.values() if isinstance(obj.get('SMask'), dict)]
        self.assertEqual([state['S'] for state in states], ['Alpha', 'Luminosity'])
        self.assertNotIn('BC', states[0])
        self.assertEqual(states[1]['BC'], [0])
        for state in states:
            self.assertEqual(pdf.get(state['G'])['Group'], dict(S='Transparency', CS='DeviceGray', I=True))
        self.assertFalse(any(obj.get('Subtype') == 'Image' for obj in pdf.objects.values()))
        self.assertEqual((len(pdf.paths()), result['pdf']['image_pixels']), (2, 0))
        self.assertEqual(result['pdf']['artwork_masks'], dict(alpha=1, luminance=1))
        png = self.cli('document.export', document=doc, format='png')
        width, height, rgba, _ = png_pixels(base64.b64decode(png['data']))
        self.assertEqual(rgba[3::4], bytes(round(255*shared_coverage(x+.5, y+.5))
                                          for y in range(height) for x in range(width)))

    def compare_reader(self, read):
        for kind in ('shared', 'linear', 'radial'):
            with self.subTest(kind=kind):
                doc = shared_sheet() if kind == 'shared' else gradient_sheet(kind)
                coverage = shared_coverage if kind == 'shared' else lambda x, y: gradient_coverage(kind, x, y)
                pdf = Pdf(self.export(doc))
                if kind != 'shared':
                    shadings = [o for o in pdf.objects.values() if 'ShadingType' in o]
                    self.assertEqual(len(shadings), 4)
                    self.assertTrue(all(o['ColorSpace'] == 'DeviceGray' for o in shadings))
                w, h = doc['width'], doc['height']
                self.assertLessEqual(max(reader_errors(read(pdf.data, w, h), w, h, coverage)), 4)
        # Both soft-mask modes must attenuate a partially opaque owner once.
        doc = shared_sheet()
        for owner in doc['items'][-2:]:
            owner['opacity'] = .5
        rgb = read(Pdf(self.export(doc)).data, 80, 28)
        self.assertLessEqual(max(reader_errors(rgb, 80, 28, lambda x, y: .5*shared_coverage(x, y))), 4)

        # A multiply child in a pass-through group must see the original base.
        # Applying the same blend to a leaf should give the same result.
        back, front = [200, 120, 60], [60, 210, 0]
        alpha = .5*128/255
        expected = [round(b*(1-alpha)+b*f/255*alpha) for b, f in zip(back, front)]
        for settings in [dict(artwork_mask=mask(mode='luminance')),
                         dict(mask=dict(width=2, height=1, gray_hex='807f', transform=[12, 0, 0, 8, 0, 0]))]:
            for container in (False, True):
                items = [source(), rect('gray', parent='source', color=[128, 128, 128, 255]),
                         rect('base', color=[*back, 255])]
                if container:
                    items.append(dict(id='parent', content=dict(type='group', isolated=False), opacity=.5, **settings))
                    items.append(rect('top', parent='parent', color=[*front, 255], blend='multiply'))
                else:
                    items.append(rect('top', color=[*front, 255], blend='multiply', opacity=.5, **settings))
                rgb = read(Pdf(self.export(paper(12, 8, items))).data, 12, 8)
                offset = 3*(16*48+16)
                self.assertLessEqual(max(abs(a-b) for a, b in zip(rgb[offset:offset+3], expected)), 3,
                                     (settings, container))

    @unittest.skipUnless(pymupdf, 'PDF raster check requires PyMuPDF')
    def test_mupdf_matches_independent_alpha_and_luminance(self):
        self.compare_reader(read_mupdf)

    @unittest.skipUnless(shutil.which('pdftoppm'), 'PDF raster check requires pdftoppm')
    def test_poppler_matches_independent_alpha_and_luminance(self):
        self.compare_reader(lambda data, w, h: poppler_rgb(data, 288, 4*w, 4*h))

    @unittest.skipUnless(pymupdf, 'PDF group coverage check requires PyMuPDF')
    def test_nested_owners_fill_and_stroke_receive_each_mask_once(self):
        shape = rect('ink', x=2, y=2, w=8, h=4, color=BLACK, parent='outer', artwork_mask=mask())
        shape['content']['stroke'] = dict(width=2, color=BLACK)
        doc = paper(12, 8, [source(), rect('gray', color=[255, 255, 255, 128], parent='source'),
                            dict(group('outer', artwork_mask=mask()), content=dict(type='group', isolated=False)),
                            shape])
        with pymupdf.open(stream=Pdf(self.export(doc)).data, filetype='pdf') as pdf:
            pix = pdf[0].get_pixmap(dpi=72, alpha=True)
            for p in [(4, 1), (4, 2), (4, 4)]:
                self.assertLessEqual(abs(pix.pixel(*p)[3]-64), 2)
            self.assertEqual(pix.pixel(0, 0)[3], 0)
        reveal = shape['artwork_mask']
        reveal.update(region=[0, 0, 0, 0])
        for clipped, alpha in [(True, 0), (False, 64)]:
            reveal['clip_region'] = clipped
            with pymupdf.open(stream=Pdf(self.export(doc)).data, filetype='pdf') as pdf:
                self.assertLessEqual(abs(pdf[0].get_pixmap(dpi=72, alpha=True).pixel(4, 4)[3]-alpha), 2)

    def test_hidden_and_disabled_owners_validate_without_painting_mask_forms(self):
        doc = shared_sheet()
        doc['items'][-1]['visible'] = False
        doc['items'][-2]['artwork_mask']['enabled'] = False
        result = self.export(doc, marks=dict(crop=True))
        self.assertNotIn('artwork_masks', result['pdf'])
        self.assertFalse(any(isinstance(o, dict) and isinstance(o.get('SMask'), dict)
                             for o in Pdf(result).objects.values()))
        reveal = doc['items'][-1]['artwork_mask']
        reveal.update(region=[0, 0, 0, 0], region_transform=[1, 0, 0, 1, 0, 0], transform=[5000, 0, 0, 1, 0, 0])
        self.cli('document.validate', document=doc)
        err = self.cli('document.publish', document=doc, output=dict(format='pdf', file_name='bad.pdf'),
                       error='RESOURCE_LIMIT')
        self.assertEqual(err['item_id'], 'luminance')
        self.assertFalse((self.root/'bad.pdf').exists())

    @unittest.skipUnless(pymupdf, 'PDF artboard coverage check requires PyMuPDF')
    def test_artboard_extraction_rebases_unlinked_source_and_adds_bleed(self):
        board = dict(id='board', transform=[2, 0, 0, 2, 4, 2], content=dict(type='frame', frame=dict(
                     role='artboard', width=8, height=6, bleed=dict(left=1, top=2))))
        doc = paper(24, 20, [source(), rect('patch', w=2, h=2, parent='source'), board,
                             rect('ink', w=8, h=6, parent='board', color=BLACK,
                                  artwork_mask=mask(linked=False, transform=[2, 0, 0, 2, 8, 6]))])
        for bleed in (False, True):
            out = self.export(doc, artboards=dict(type='ids', ids=['board']), include_bleed=bleed)
            w, h, left, top = (9, 8, 3, 4) if bleed else (8, 6, 2, 2)
            coverage = lambda x, y: int(left <= x < left+2 and top <= y < top+2)
            self.assertEqual(max(reader_errors(read_mupdf(Pdf(out).data, w, h), w, h, coverage)), 0)

    def test_pinned_font_source_keeps_outlines_and_checks_missing_font(self):
        (self.root/'fixture.ttf').write_bytes(geometric_font())
        (self.root/'license.txt').write_text('Original geometric font fixture.', encoding='utf-8')
        font = self.cli('font.import', source_path='fixture.ttf', license_path='license.txt')
        text = dict(id='type', parent='source', content=dict(type='text', frame=dict(text='AA',
                    width=12, height=10, overflow='visible', style=dict(font_id='draw', size=10, fill=BLACK))))
        doc = dict(paper(12, 8, [source(), text, rect('ink', color=BLACK, artwork_mask=mask())]), fonts={'draw': font})
        pdf = Pdf(self.export(doc))
        self.assertFalse(any(o.get('Subtype') == 'Image' for o in pdf.objects.values()))
        if pymupdf:
            rgb = read_mupdf(pdf.data, 12, 8)
            for x, y, expected in [(2, 5, 0), (5, 5, 255), (8, 5, 0), (8, 0, 255)]:
                self.assertEqual(rgb[3*((4*y+2)*48+4*x+2)], expected)
        self.cli('document.publish', document=doc, resources=dict(font_root=None), output=dict(format='pdf', file_name='font.pdf'),
                 error='FONT_ROOT_REQUIRED')
        self.assertFalse((self.root/'font.pdf').exists())

    def test_raster_owner_keeps_intrinsic_image_alpha_under_a_vector_mask(self):
        doc = paper(12, 8, [source(), rect('left', w=6, parent='source', color=[128, 128, 128, 255]),
                            layer('pixel-layer', [[0, 0, 0, 128]]*96, width=12, artwork_mask=mask(mode='luminance'))])
        doc['kind'] = 'raster'
        result = self.export(doc)
        self.assertEqual(result['pdf']['image_pixels'], 96)
        pdf = Pdf(result)
        images = [obj for obj in pdf.objects.values() if obj.get('Subtype') == 'Image']
        self.assertEqual(len(images), 2)
        if pymupdf:
            rgb = read_mupdf(pdf.data, 12, 8)
            self.assertLessEqual(max(reader_errors(rgb, 12, 8, lambda x, y: (128/255)**2 if x < 6 else 0)), 2)

    @unittest.skipUnless(pymupdf, 'PDF calibrated artwork check requires PyMuPDF')
    def test_calibrated_page_keeps_encoded_mask_weights(self):
        doc = shared_sheet()
        doc['output_profile'] = builtin('srgb')
        pdf = Pdf(self.export(doc))
        self.assertIn(b'/ICCBased', pdf.data)
        states = [o['SMask'] for o in pdf.objects.values() if isinstance(o, dict) and isinstance(o.get('SMask'), dict)]
        self.assertEqual([pdf.get(s['G'])['Group']['CS'] for s in states], ['DeviceGray', 'DeviceGray'])
        # Alpha is independent of the page's color conversion.
        with pymupdf.open(stream=pdf.data, filetype='pdf') as source_pdf:
            pix = source_pdf[0].get_pixmap(dpi=288, alpha=True)
            for y in range(28):
                for x in range(80):
                    self.assertLessEqual(abs(pix.pixel(4*x+2, 4*y+2)[3]-round(255*shared_coverage(x+.5, y+.5))), 4)

    def test_named_source_is_projected_without_converting_printed_inks(self):
        doc = paper(12, 8, [source(), rect('swatch', color=reference('stencil'), parent='source'),
                            rect('ink', color=BLACK, artwork_mask=mask(mode='luminance'))])
        doc['swatches'] = dict(stencil=spot(rgb=[0, 1, 0]))
        for opts in ({}, dict(color='native_inks')):
            pdf = Pdf(self.export(doc, **opts))
            self.assertNotIn(b'/Inkbolt.stencil', pdf.data)
            self.assertIn(b'0.7154 g', pdf.data)
        doc['items'][-1]['artwork_mask']['enabled'] = False
        unused = self.export(doc)
        self.assertNotIn('artwork_masks', unused['pdf'])
        self.assertNotIn(b'/Inkbolt.stencil', Pdf(unused).data)
        doc['items'][-1]['artwork_mask']['enabled'] = True
        doc['items'][-1]['content']['fill'] = reference('stencil')
        self.cli('document.export', document=doc, format='pdf', error='UNSUPPORTED')
        self.assertIn(b'/Inkbolt.stencil', Pdf(self.export(doc, color='native_inks')).data)
        doc['swatches']['stencil'] = cmyk([0, 1, 0, 0], spot=True)
        self.cli('document.export', document=doc, format='pdf', pdf_options=dict(color='native_inks'),
                 error='SWATCH_PREVIEW_REQUIRED')
        doc['items'][1]['content']['fill'] = reference('stencil', overprint='preserve_nonzero')
        self.cli('document.export', document=doc, format='pdf', pdf_options=dict(color='native_inks'),
                 error='OVERPRINT_PREVIEW_UNSUPPORTED')

    @unittest.skipUnless(pymupdf, 'PDF separation preview requires PyMuPDF')
    def test_masked_cyan_overprint_preserves_black_on_marked_native_pages(self):
        doc = paper(12, 8, [source(), rect('gray', parent='source', color=[128, 128, 128, 255]),
                            rect('base', color=reference('k')), rect('over', artwork_mask=mask(mode='luminance'),
                            color=reference('cyan', overprint='preserve_nonzero'))])
        doc['swatches'] = dict(cyan=cmyk([1, 0, 0, 0]), k=cmyk([0, 0, 0, 1]))
        for options, opacity, cyan in [({}, 1, 128), (dict(marks=dict(crop=True, registration=False)), .5, 64)]:
            doc['items'][-1]['opacity'] = opacity
            with pymupdf.open(stream=Pdf(self.export(doc, color='native_inks', **options)).data, filetype='pdf') as pdf:
                api = pymupdf.mupdf
                pix = api.fz_new_pixmap_from_page_contents_with_separations(
                    pdf[0].this, api.fz_scale(4, 4), api.fz_device_cmyk(), api.fz_new_separations(0), 0)
                offset = pix.stride()*(pix.h()//2) + 4*(pix.w()//2)
                plates = api.fz_pixmap_samples_memoryview(pix)[offset:offset+4]
                self.assertLessEqual(max(abs(a-b) for a, b in zip(plates, [cyan, 0, 0, 255])), 3)

    def test_imported_svg_source_survives_revision_pinned_mcp_publication(self):
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="12" height="8"><defs>'
               '<mask id="m"><rect id="patch" width="12" height="8" fill="white"/></mask></defs>'
               '<rect width="12" height="8" mask="url(#m)"/></svg>')
        doc = self.cli('svg.import', id='masked', source=dict(kind='text', text=svg))['document']
        source_id, = [i['id'] for i in doc['items'] if i['content']['type'] == 'mask_source']
        patch_id, = [i['id'] for i in doc['items'] if i.get('parent') == source_id]
        with closing(Client(('--tools', 'essentials'), workspace=self.root)) as client:
            client.initialize()
            def run(command, **args):
                return client.tool('run', command=command, arguments=args)['structuredContent']
            created = run('session.create', session_id='work', request_id='create', document=doc)
            self.assertTrue(created['ok'], created)
            revised = run('session.apply', session_id='work', expected_revision=0, request_id='dim',
                          action=dict(type='edit', operations=[dict(op='properties', id=patch_id, opacity=.4)]))
            self.assertTrue(revised['ok'], revised)
            output = dict(format='pdf', file_name='mask.pdf')
            ref = dict(session_id='work', revision=0)
            marked = dict(output, pdf_options=dict(marks=dict(crop=True, registration=False)))
            self.assertFalse(run('document.preflight', document=ref, output=marked)['result']['ready'])
            self.assertEqual(run('document.publish', document=ref, output=marked)['error']['code'], 'UNSUPPORTED')
            self.assertFalse((self.root/'mask.pdf').exists())
            self.assertTrue(run('document.preflight', document=ref, output=output)['result']['ready'])
            self.assertEqual(run('document.publish', document=ref, output=output)['result']['pdf']['artwork_masks'],
                             dict(alpha=0, luminance=1))
            published = (self.root/'mask.pdf').read_bytes()
            self.assertEqual(published, Pdf(self.export(doc)).data)
            newer = dict(ref, revision=1)
            self.assertNotEqual(published, Pdf(self.export(newer)).data)
            self.assertEqual(run('document.publish', document=newer, output=output)['error']['code'], 'OUTPUT_EXISTS')
            self.assertEqual((self.root/'mask.pdf').read_bytes(), published)
