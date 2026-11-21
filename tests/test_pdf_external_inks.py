"""Independent separations and screen alpha for native knockout overprint."""
from pathlib import Path
import shutil
import unittest

from pdf_reader import Pdf
from test_pdf_blends_cli import pymupdf
import test_pdf_knockout_inks as native
from test_vector_plates_cli import color, named, rect
from synthetic_font import geometric_font


def patches(owner=.75, swatch='mix', policy='preserve_nonzero'):
    doc = native.sheet(False)
    doc['swatches']['mix'] = color([0,.8,0,.25])
    doc['swatches']['empty'] = color([0,0,0,0])
    items = [rect('under',named('y',opacity=.55),(0,0,32,36)),
             rect('original-spot',named('z',tint=.65,opacity=.78,overprint='preserve'),(8,0,28,36)),
             native.group('cut',False,opacity=owner),
             rect('first',named('c',opacity=.7),(0,0,48,36),parent='cut')]
    for row, opacity in enumerate((0,.36,1)):
        for col, footprint in enumerate((0,74/255,184/255,1)):
            fill = named(swatch,opacity=footprint,tint=.8,overprint=policy)
            items.append(rect(f'patch-{col}-{row}',fill,(12*col,12*row,12,12),parent='cut',opacity=opacity))
    doc['items'] = items
    return doc


def nested():
    doc = patches()
    doc['items'] = doc['items'][:2] + [
        native.group('outer',False,False,opacity=.9,
                     clip=dict(geometry=dict(shape='rect',x=2,y=1,width=44,height=33))),
        rect('prior-spot',named('a',overprint='preserve',tint=.25),(0,0,48,36),parent='outer',opacity=.63),
        native.group('cut',False,parent='outer',opacity=.83),
        rect('cyan',named('c',opacity=.68),(0,0,48,36),parent='cut'),
        native.group('local',False,False,parent='cut',opacity=.72,
                     mask=dict(width=2,height=1,gray_hex='80ff',transform=[24,0,0,36,0,0])),
        rect('earlier',named('y',opacity=.8),(0,0,28,36),parent='local',opacity=.75),
        rect('printing',named('z',overprint='preserve',tint=.71,opacity=.53),(0,0,48,30),
             parent='local',opacity=.86),
        rect('mixed',named('mix',overprint='preserve_nonzero',tint=.8,opacity=.62),
             (4,4,40,27),parent='local',opacity=.67),
        rect('window',named('a',overprint='preserve',opacity=.77),(9,8,7,14),parent='cut',opacity=0)]
    return doc


class ExternalInkTests(unittest.TestCase):
    setUp = native.NativePdfKnockoutTests.setUp
    cli = native.NativePdfKnockoutTests.cli
    export = native.NativePdfKnockoutTests.export
    proof = native.NativePdfKnockoutTests.proof
    check_plates = native.NativePdfKnockoutTests.check_plates

    def test_process_spot_and_zero_ink_overprints_keep_the_external_plates(self):
        for owner, swatch, policy in [(1,'a','preserve'),(.75,'a','preserve_nonzero'),
                (1,'mix','preserve'),(.75,'mix','preserve_nonzero'),(.75,'empty','preserve_nonzero')]:
            with self.subTest(owner=owner,swatch=swatch,policy=policy):
                artifact,_ = self.check_plates(patches(owner,swatch,policy),tolerance=2)
                self.assertEqual(artifact['pdf']['external_overprint_paints'],12)
                self.assertEqual(artifact['pdf']['image_pixels'],0)

    @unittest.skipUnless(pymupdf,'MuPDF renders transparent page artwork')
    def test_every_patch_retains_one_shared_alpha(self):
        for owner, swatch in [(1,'a'),(.75,'mix'),(.75,'empty')]:
            with pymupdf.open(stream=Pdf(self.export(patches(owner,swatch))).data,filetype='pdf') as reader:
                pixels = reader[0].get_pixmap(dpi=288,alpha=True)
                for y in range(36):
                    for x in range(48):
                        entry = 1-(1-(.55 if x<32 else 0))*(1-(.78 if 8<=x<36 else 0))
                        f = (0,74/255,184/255,1)[x//12]
                        p = (0,.36,1)[y//12]
                        alpha = entry+(1-entry)*owner*((1-f)*.7+f*p)
                        self.assertLessEqual(abs(round(255*alpha)-pixels.pixel(4*x+2,4*y+2)[3]),2)

    def test_nested_pass_through_masks_and_isolated_entries(self):
        doc = nested()
        self.check_plates(doc)
        doc['items'].insert(0,dict(id='mask',content=dict(type='mask_source')))
        doc['items'].insert(1,rect('field',[255,255,255,200],(0,0,32,36),parent='mask'))
        group = next(i for i in doc['items'] if i['id']=='cut')
        group['artwork_mask'] = dict(source='mask',region=[0,0,48,36])
        self.check_plates(doc)
        outer = next(i for i in doc['items'] if i['id']=='outer')
        outer['content']['isolated'] = True
        self.check_plates(doc)
        group['content']['isolated'] = True
        self.assertNotIn('external_overprint_paints',self.export(doc)['pdf'])

    def test_stroke_sees_the_ink_from_the_fill(self):
        doc = nested()
        doc['items'] = [i for i in doc['items'] if i['id'] not in ('printing','mixed','window')]
        node = rect('outlined',named('a',overprint='preserve',opacity=.6),(5,5,34,21),
                    parent='local',opacity=.8)
        node['content']['stroke'] = dict(width=4,color=named('z',overprint='preserve',opacity=.7))
        doc['items'].append(node)
        artifact,_ = self.check_plates(doc)
        self.assertEqual(artifact['pdf']['external_overprint_paints'],2)

    def test_marks_keep_native_artwork_and_all_plate_margins(self):
        doc = patches(swatch='a')
        _,plain = self.check_plates(doc,tolerance=2)
        marked_result,marked = self.check_plates(doc,tolerance=2,marks={})
        margin = round(Pdf(marked_result).pages[0]['BleedBox'][0]*4)
        box = (margin,margin,margin+48*4,margin+36*4)
        margins = []
        for name,plane in marked.items():
            self.assertEqual(plane.crop(box).tobytes(),plain[name].tobytes(),name)
            plane.paste(255,box)
            margins.append(plane.tobytes())
        self.assertGreater(marked['Black'].histogram()[0],0)
        self.assertEqual(len(set(margins)),1)

    def test_saved_backdrops_observe_the_page_resource_budget(self):
        doc = patches()
        doc['items'] = doc['items'][:2]
        output = dict(format='pdf',file_name='deep.pdf',pdf_options=dict(color='native_inks'))
        for i in range(32):
            key = f'group-{i}'
            doc['items'].extend([native.group(key,False),
                rect('base-'+key,named('m',opacity=.7),(2,2,40,30),parent=key),
                rect('over-'+key,named('z',overprint='preserve',opacity=.75),(3,3,39,30),parent=key)])
            if i==3:
                self.assertTrue(self.cli('document.preflight',document=doc,output=output)['ready'])
        self.assertFalse(self.cli('document.preflight',document=doc,output=output)['ready'])
        error = self.cli('document.publish',document=doc,output=output,error='RESOURCE_LIMIT')
        self.assertIn('reference',error['message'])
        self.assertFalse((self.root/'deep.pdf').exists())

    @unittest.skipUnless(shutil.which('gs') or shutil.which('gswin64c'), 'Ghostscript renders the page plates')
    def test_selected_artboard_preserves_rebased_curves_and_compound_holes(self):
        try:
            from PIL import ImageChops
        except ImportError:
            self.skipTest('Pillow reads the independent TIFF plates')
        doc = patches(swatch='a')
        doc['resolution_ppi'] = 96
        doc['items'] = doc['items'][:4]
        shape = rect('blue-window',named('mix',overprint='preserve_nonzero',opacity=.7),
                     (0,0,20,20),parent='cut',opacity=.8)
        path = [dict(verb='move',to=[8,3]),dict(verb='cubic',control1=[42,3],control2=[42,32],to=[8,32]),
                dict(verb='close'),dict(verb='move',to=[13,12]),dict(verb='line',to=[19,12]),
                dict(verb='line',to=[19,19]),dict(verb='line',to=[13,19]),dict(verb='close')]
        shape['content'].update(geometry=dict(shape='path',commands=path),fill_rule='even_odd')
        doc['items'].append(shape)
        base = Pdf(self.export(doc))
        frame = dict(id='board',transform=[1,0,0,1,20,5],
                     content=dict(type='frame',frame=dict(width=48,height=36,role='artboard')))
        for item in doc['items']:
            item.setdefault('parent','board')
        doc['items'].insert(0,frame)
        selected = Pdf(self.export(doc,artboards=dict(type='ids',ids=['board'])))
        self.assertTrue(any(b'W* n' in s for s in selected.streams.values()))
        self.assertTrue(any(b' c\n' in s for s in selected.streams.values()))
        self.assertNotIn(b'/Subtype /Image',selected.data)
        plain = self.root/'plain'
        board = self.root/'board'
        plain.mkdir()
        board.mkdir()
        expected = native.separations(base.data,plain)
        actual = native.separations(selected.data,board)
        self.assertEqual(actual.keys(),expected.keys())
        for name,plate in expected.items():
            self.assertIsNone(ImageChops.difference(plate,actual[name]).getbbox(),name)

    def test_repeated_glyphs_share_the_full_coverage_ink(self):
        font_file = self.root/'label.ttf'
        font_file.write_bytes(geometric_font())
        license_file = self.root/'LICENSE'
        license_file.write_bytes((Path(__file__).resolve().parents[1]/'LICENSE').read_bytes())
        font = self.cli('font.import',source_path=str(font_file),license_path=str(license_file))
        doc = patches()
        doc['fonts'] = dict(label=font)
        doc['width'] = 400
        doc['items'] = doc['items'][:4] + [dict(id='label',parent='cut',content=dict(type='text',
            frame=dict(text='A'*32,width=400,height=36,style=dict(font_id='label',size=20,
            fill=named('z',overprint='preserve',opacity=.75)))))]
        artifact = self.export(doc)
        self.assertEqual(artifact['pdf']['external_overprint_paints'],32)
        self.assertEqual(artifact['pdf']['text_glyphs'],32)
        self.assertEqual(artifact['pdf']['image_pixels'],0)
        _,planes = self.check_plates(doc)
        self.assertLess(planes['Inkbolt.z'].getextrema()[0],255)
