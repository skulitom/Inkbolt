"""Actual marked display PDFs compared with their unmarked artwork and press plates."""
import hashlib
from contextlib import closing
from pathlib import Path
import shutil
import tempfile
import unittest

from pdf_reader import Pdf
import test_agent_workspace as workspace
from test_artwork_masks_cli import rect
from test_images_cli import canonical
from test_mcp import Client
from test_pdf_artwork_masks import paper
from test_pdf_blends_cli import poppler_rgb, pymupdf
from test_pdf_knockout_inks import separations
from cmyk_fixtures import cmyk_profile
from test_profiles_cli import builtin, embedded


W, H = 48, 32
BLUE = [42, 96, 178]


def sheet(background=False, knockout=False):
    gradient = dict(type='linear', start=[0, 0], end=[W, 0], stops=[
        dict(offset=0, color=[30, 200, 67, 30]), dict(offset=1, color=[196, 48, 115, 215])])
    items = [
        rect('back', x=7, y=3, w=32, h=22, color=[145, 39, 184, 155]),
        dict(id='set', content=dict(type='group', isolated=False, knockout=knockout), opacity=.78),
        rect('wash', w=37, h=26, color=gradient, parent='set'),
        rect('multiply', x=12, y=5, w=34, h=22, color=[50, 180, 83, 174], parent='set',
             blend='multiply', opacity=.7, mask=dict(width=2, height=1, gray_hex='90e0',
             transform=[24, 0, 0, 32, 0, 0])),
        rect('hole', x=17, y=8, w=8, h=10, color=[40, 30, 100, 241], opacity=0, parent='set')]
    if background:
        items.insert(0, rect('paper', w=W, h=H, color=BLUE+[255]))
    return paper(W, H, items)


def image_paper():
    doc = sheet()
    pixels = bytes.fromhex('010203000a4080ff102060ff')
    doc['assets'] = dict(bg=dict(width=3, height=1, sha256=hashlib.sha256(canonical(3,1,pixels)).hexdigest(),
                                 storage=dict(type='embedded', rgba_hex=pixels.hex())))
    doc['items'].insert(0, dict(id='photo', content=dict(type='image', asset_id='bg', width=W,
        height=H, crop=dict(x=1, y=0, width=2, height=1))))
    return doc


def cases():
    for calibrated in (False, True):
        for knockout in (False, True):
            for authored in (False, True):
                doc = sheet(authored, knockout)
                if calibrated:
                    doc['output_profile'] = builtin('srgb')
                yield doc, {} if authored else dict(matte=BLUE)


class MarkedRgbTests(unittest.TestCase):
    setUp = workspace.AgentWorkspaceTests.setUp
    cli = workspace.AgentWorkspaceTests.cli

    def export(self, doc, **options):
        return self.cli('document.export', document=doc, format='pdf', pdf_options=options)

    def test_artwork_forms_and_receipts_preserve_the_selected_paper(self):
        for doc, options in cases():
            with self.subTest(options=options, profile=doc.get('output_profile')):
                plain = Pdf(self.export(doc, **options))
                result = self.export(doc, marks={}, **options)
                marked = Pdf(result)
                page = marked.pages[0]
                form, = page['Resources']['XObject'].values()
                self.assertNotIn('Group', page)
                self.assertEqual(marked.get(form)['Group'], plain.pages[0]['Group'])
                self.assertEqual(marked.streams[form], plain.streams[plain.pages[0]['Contents']])
                self.assertEqual(marked.get(form)['Resources'], plain.pages[0]['Resources'])
                receipt = result['pages'][0]
                expected = dict(source='export_matte') if options else dict(source='item',item_id='paper')
                self.assertEqual(receipt['opaque_rgb_paper'], expected)
                self.assertEqual(receipt.get('matte'), options.get('matte'))
                self.assertEqual(result['pdf']['image_pixels'], 0)
                self.assertEqual(receipt['marks']['colorant'], 'All')

    def test_nonprinting_partial_or_knocked_out_sources_cannot_establish_paper(self):
        full = rect('paper', w=W, h=H)
        for attrs in [dict(visible=False), dict(opacity=.999), dict(fill_opacity=.999),
                      dict(clip=dict(geometry=dict(shape='rect', x=0, y=0, width=W-.01, height=H))),
                      dict(mask=dict(width=1, height=1, gray_hex='c0')),
                      dict(transform=[1,0,0,1,.000000001,0]),
                      dict(transform=[1,.25,-.25,1,5,-4])]:
            doc = sheet()
            doc['items'].insert(0, dict(full, **attrs))
            self.refused(doc)
        for parent in [dict(type='mask_source'), dict(type='group', knockout=True),
                       dict(type='frame', frame=dict(width=W-1, height=H))]:
            doc = sheet()
            doc['items'][:0] = [dict(id='hidden_paper', content=parent),
                                dict(full, parent='hidden_paper')]
            self.refused(doc)
        doc = image_paper()
        doc['items'][0]['content']['crop']['x'] = 0
        self.refused(doc)

    def refused(self, doc):
        output = dict(format='pdf', file_name='partial.pdf', pdf_options=dict(marks={}))
        self.assertFalse(self.cli('document.preflight', document=doc, output=output)['ready'])
        self.cli('document.publish', document=doc, output=output, error='UNSUPPORTED')
        self.assertFalse((self.root/'partial.pdf').exists())

    def test_frame_fill_path_crop_and_visible_raster_matte(self):
        frame = dict(id='board', content=dict(type='frame', frame=dict(role='artboard', width=W,
            height=H, background=BLUE+[255], bleed=dict(left=1,right=2,top=3,bottom=4))))
        doc = sheet()
        for item in doc['items']:
            item.setdefault('parent', 'board')
        doc['items'].insert(0, frame)
        receipt = self.export(doc, marks={}, artboards=dict(type='all'), include_bleed=True)['pages'][0]
        self.assertEqual(receipt['opaque_rgb_paper']['item_id'], 'board')
        self.assertEqual(receipt['logical_size'], [W+3, H+7])
        # A background covering trim inside a transparent frame leaves its bleed clear.
        frame['content']['frame'].pop('background')
        doc['items'].insert(1, rect('trim', w=W, h=H, parent='board'))
        selection = dict(marks={}, artboards=dict(type='all'), include_bleed=True)
        self.cli('document.export', document=doc, format='pdf', pdf_options=selection, error='UNSUPPORTED')
        self.assertEqual(self.export(doc, **selection, matte=BLUE)['pages'][0]['matte'], BLUE)

        doc = sheet()
        points = [[0,0],[0,H],[W,H],[W,0]]
        for geometry in (dict(shape='polygon', points=points), dict(shape='path', commands=[
                dict(verb='move',to=points[0]), *[dict(verb='line',to=p) for p in points[1:]],
                dict(verb='close')])):
            base = rect('rectangle', transform=[-1,0,0,1,W,0])
            base['content']['geometry'] = geometry
            out = self.export(dict(doc, items=[base]+doc['items']), marks={})
            self.assertEqual(out['pages'][0]['opaque_rgb_paper']['item_id'],'rectangle')
        self.assertEqual(self.export(image_paper(), marks={})['pages'][0]['opaque_rgb_paper']['item_id'],'photo')
        gradient = dict(type='linear', start=[0,0], end=[W,0],
                        stops=[dict(offset=0,color=[0,12,94,255]),dict(offset=1,color=BLUE+[255])])
        group = dict(id='holder',content=dict(type='group',isolated=True))
        fill = rect('ground', w=W, h=H, color=gradient, parent='holder',
                    clip=dict(geometry=dict(shape='rect',x=0,y=0,width=W,height=H)))
        self.assertEqual(self.export(dict(doc,items=[group,fill]+doc['items']),marks={})
                         ['pages'][0]['opaque_rgb_paper']['item_id'],'ground')
        group['opacity'] = .99
        self.refused(dict(doc,items=[group,fill]+doc['items']))
        layer = dict(id='pixels',content=dict(type='raster',width=W,height=H,rgba_hex='043CA8FF'*(W*H)))
        raster_fill = dict(id='tint',content=dict(type='fill',width=W,height=H,paint=[150,80,40,120]))
        pixels = dict(doc,kind='raster',items=[layer,raster_fill])
        self.assertEqual(self.export(pixels,marks={})['pages'][0]['opaque_rgb_paper']['item_id'],'pixels')
        layer['content']['rgba_hex'] = layer['content']['rgba_hex'][:-2]+'fe'
        self.refused(pixels)
        raster = dict(doc,kind='raster',background=dict(item_id='bottom',matte=BLUE))
        raster['items'] = [dict(id='bottom',content=dict(type='group',isolated=True)),
                           raster_fill]
        self.assertEqual(self.export(raster,marks={})['pages'][0]['opaque_rgb_paper']['source'],'document_matte')

    def test_all_selected_pages_need_paper_before_publication(self):
        doc = sheet()
        items = []
        for key, opaque in [('cover',True),('detail',False)]:
            frame = dict(role='artboard',width=W,height=H)
            if opaque:
                frame['background'] = BLUE+[255]
            items.extend([dict(id=key,content=dict(type='frame',frame=frame)),
                          rect(key+'-paint',w=W,h=H,parent=key,color=[52,184,84,130])])
        doc['items'] = items
        output = dict(format='pdf',file_name='both.pdf',pdf_options=dict(marks={},artboards=dict(type='all')))
        self.assertFalse(self.cli('document.preflight',document=doc,output=output)['ready'])
        self.cli('document.publish',document=doc,output=output,error='UNSUPPORTED')
        self.assertFalse((self.root/'both.pdf').exists())
        output['pdf_options']['matte'] = BLUE
        result = self.cli('document.publish',document=doc,output=output)
        self.assertEqual(len(Pdf((self.root/'both.pdf').read_bytes()).pages),2)
        self.assertEqual([page['matte'] for page in result['pages']],[BLUE,BLUE])

    @unittest.skipUnless(shutil.which('gs') or shutil.which('gswin64c'), 'Ghostscript renders the press plates')
    def test_independent_marked_and_unmarked_plates_match_inside_the_bleed(self):
        try:
            from PIL import ImageChops
        except ImportError:
            self.skipTest('Pillow reads the independent TIFF plates')
        for doc, options in cases():
            with self.subTest(options=options, profile=doc.get('output_profile')), tempfile.TemporaryDirectory() as tmp:
                plates = []
                for name, extra in [('plain', {}), ('marked', dict(marks={}))]:
                    folder = Path(tmp)/name
                    folder.mkdir()
                    plates.append(separations(Pdf(self.export(doc, **options, **extra)).data, folder))
                plain, marked = plates
                self.assertEqual(set(marked), {'Cyan','Magenta','Yellow','Black'})
                self.assertEqual(plain.keys(), marked.keys())
                margin = 49
                box = (margin,margin,margin+W*4,margin+H*4)
                for channel, target in plain.items():
                    self.assertEqual(target.tobytes(), marked[channel].crop(box).tobytes(), channel)
                    marked[channel].paste(255, box)
                self.assertGreater(marked['Black'].histogram()[0], 0)
                for plane in marked.values():
                    self.assertIsNone(ImageChops.difference(plane, marked['Black']).getbbox())

    @unittest.skipUnless(shutil.which('gs') or shutil.which('gswin64c'), 'Ghostscript renders the press plates')
    def test_knockout_restores_actual_background_plates(self):
        try:
            from PIL import ImageChops
        except ImportError:
            self.skipTest('Pillow reads the independent TIFF plates')
        doc = sheet(background=True, knockout=True)
        doc['items'][-1]['content']['fill'][-1] = 255
        reference = dict(doc, items=doc['items'][:2])
        # A zero-opacity child with full paint coverage exposes the original
        # background, even after the knockout group's own opacity is applied.
        with tempfile.TemporaryDirectory() as tmp:
            truth = Path(tmp)/'truth'
            truth.mkdir()
            original = separations(Pdf(self.export(reference)).data, truth)
            for name, extra, offset in [('plain', {}, 0), ('marked', dict(marks={}), 49)]:
                folder = Path(tmp)/name
                folder.mkdir()
                result = separations(Pdf(self.export(doc, **extra)).data, folder)
                box = (18*4,9*4,24*4,17*4)
                for channel, target in original.items():
                    actual = result[channel].crop(tuple(x+offset for x in box))
                    self.assertIsNone(ImageChops.difference(target.crop(box), actual).getbbox(), channel)

    @unittest.skipUnless(pymupdf, 'MuPDF renders associated RGBA')
    def test_export_matte_composites_after_blending_and_matches_rgba(self):
        doc = sheet(knockout=True)
        def render(**opts):
            with pymupdf.open(stream=Pdf(self.export(doc, **opts)).data, filetype='pdf') as pdf:
                return pdf[0].get_pixmap(dpi=288, alpha=True)
        original, opaque, marked = render(), render(matte=BLUE), render(matte=BLUE, marks={})
        margin = 49
        for x in range(original.width):
            for y in range(original.height):
                r,g,b,a = original.pixel(x,y)
                actual = opaque.pixel(x,y)
                expected = [p+(1-a/255)*c for p,c in zip([r,g,b],BLUE)] + [255]
                self.assertLessEqual(max(abs(v-w) for v,w in zip(actual,expected)), 2)
                self.assertEqual(marked.pixel(x+margin,y+margin),actual)
        self.assertEqual(original.pixel(original.width-1,original.height-1)[3],0)

    @unittest.skipUnless(shutil.which('pdftoppm'), 'Poppler renders RGB')
    def test_second_reader_preserves_all_artwork_pixels(self):
        for doc, options in cases():
            plain = poppler_rgb(Pdf(self.export(doc, **options)).data,288,W*4,H*4)
            w,h = W*4+98,H*4+98
            marked = poppler_rgb(Pdf(self.export(doc, **options, marks={})).data,288,w,h)
            for y in range(H*4):
                start = 3*((y+49)*w+49)
                self.assertEqual(marked[start:start+W*12],plain[y*W*12:(y+1)*W*12])

    def test_matte_scope_and_pinned_publication_are_atomic(self):
        doc = sheet()
        with closing(Client(('--tools','essentials'),workspace=self.root)) as client:
            client.initialize()
            def run(command, **args):
                return client.tool('run',command=command,arguments=args)['structuredContent']
            create = dict(session_id='proof',request_id='create',document=doc)
            self.assertTrue(run('session.create', **create)['ok'])
            ref = dict(session_id='proof',revision=0)
            out = dict(format='pdf',file_name='marked.pdf',pdf_options=dict(matte=BLUE,marks={}))
            apply = dict(session_id='proof', request_id='fade',expected_revision=0,
                         action=dict(type='edit',operations=[dict(op='properties',id='back',opacity=.1)]))
            self.assertTrue(run('session.apply', **apply)['ok'])
            self.assertTrue(run('session.apply', **apply)['ok'])
            self.assertTrue(run('document.preflight', document=ref,output=out)['result']['ready'])
            self.assertFalse((self.root/'marked.pdf').exists())
            self.assertTrue(run('document.publish', document=ref,output=out)['ok'])
            self.assertEqual((self.root/'marked.pdf').read_bytes(),Pdf(self.export(doc,**out['pdf_options'])).data)
            self.assertEqual(run('document.publish',document=ref,output=out)['error']['code'],'OUTPUT_EXISTS')
        for mode in (dict(color='native_inks'), dict(ink_recipe={}),
                     dict(print=dict(matte=BLUE,profile=embedded(cmyk_profile()))),
                     dict(prepress=dict(profile=embedded(cmyk_profile())))):
            output = dict(format='pdf',file_name='mix.pdf',pdf_options=dict(matte=BLUE,**mode))
            error = self.cli('document.publish',document=doc,output=output,error='INVALID_REQUEST')
            self.assertIn('pdf_options.matte', error['message'])
            self.assertFalse((self.root/'mix.pdf').exists())
