"""Check PDF knockout colors and alpha against independent sibling-footprint math."""
from contextlib import closing
import base64
import copy
import math
import shutil
import unittest

from pdf_reader import Pdf
from synthetic_font import geometric_font
import test_agent_workspace as workspace
from test_artwork_masks_cli import mask, rect, source
from test_editing_cli import png_pixels
from test_layer_clipping_cli import layer, over, premul
from test_mcp import Client
from test_pdf_artwork_masks import paper, read_mupdf
from test_pdf_blends_cli import poppler_rgb, pymupdf
from test_profiles_cli import builtin


W, H = 64, 26
BACK = [34, 150, 85, 113]
RED = [220, 38, 72, 203]
RAMP = ([215, 20, 30, 0], [20, 210, 180, 240])
BLUE = [35, 45, 200, 192]


def box(x, y, w, h):
    return dict(geometry=dict(shape='rect', x=x, y=y, width=w, height=h))


def sheet(isolated):
    ramp = dict(type='linear', start=[0, 0], end=[48, 0],
                stops=[dict(offset=i, color=rgba) for i, rgba in enumerate(RAMP)])
    group = dict(id='knock', transform=[1, 0, 0, 1, 2, 1], opacity=.75,
                 clip=box(1, 1, 57, 21), content=dict(type='group', knockout=True, isolated=isolated))
    return paper(W, H, [
        rect('back', w=32, h=H, color=BACK), group,
        rect('red', x=0, y=1, w=60, h=20, color=RED, opacity=.8, parent='knock'),
        rect('ramp', x=8, y=2, w=47, h=17, color=ramp, opacity=.5, fill_opacity=.75,
             blend='screen' if isolated else 'normal', parent='knock'),
        rect('clear', x=18, y=6, w=24, h=12, color=BLUE, opacity=0, parent='knock'),
        rect('last', x=37, y=12, w=16, h=10, color=BLUE, parent='knock'),
        rect('hidden', w=64, h=26, visible=False, parent='knock')])


def expected(x, y):
    back = [v/255 for v in BACK] if x < 32 else [0., 0., 0., 0.]
    u, v = x-2, y-1
    rgba = [0.] * 4  # premultiplied contribution of the group over transparent
    if 1 <= u < 58 and 1 <= v < 22:
        t = min(1., max(0., u/48))
        ramp = [lo+(hi-lo)*t for lo, hi in zip(*RAMP)]
        for inside, c, weight in [(0 <= u < 60 and 1 <= v < 21, RED, .8),
                                  (8 <= u < 55 and 2 <= v < 19, ramp, .375),
                                  (18 <= u < 42 and 6 <= v < 18, BLUE, 0),
                                  (37 <= u < 53 and 12 <= v < 22, BLUE, 1)]:
            if inside:
                f = c[3]/255
                # Outside the child's footprint retain the accumulated sibling
                # color. Inside it only the incoming paint and group entry count.
                rgba = [(1-f)*d + f*weight*s for d, s in zip(rgba, [*(v/255 for v in c[:3]), 1.])]
    a = rgba[3]*.75
    back_a = back[3]*(1-a)
    return [c*.75 + b*back_a for c,b in zip(rgba[:3],back[:3])] + [a+back_a]


def sample_errors(rgb):
    for y in range(H):
        for x in range(W):
            r, g, b, a = expected(x+.5, y+.5)
            i = 3*((4*y+2)*4*W+4*x+2)
            yield max(abs(actual-round(255*(c+1-a))) for actual,c in zip(rgb[i:i+3], [r,g,b]))


def reader_samples(data, w, h):
    if pymupdf:
        yield 'MuPDF', read_mupdf(data, w, h)
    if shutil.which('pdftoppm'):
        yield 'Poppler', poppler_rgb(data, 288, 4*w, 4*h)


def white_pixel(rgb, w, x, y):
    pos = 3*((4*y+2)*4*w+4*x+2)
    return list(rgb[pos:pos+3])


class PdfKnockoutTests(unittest.TestCase):
    setUp = workspace.AgentWorkspaceTests.setUp
    cli = workspace.AgentWorkspaceTests.cli

    def export(self, doc, **options):
        return self.cli('document.export', document=doc, format='pdf', pdf_options=options)

    def test_sources_remain_vector_and_native_alpha_matches_the_partition(self):
        for isolated in [True, False]:
            doc = sheet(isolated)
            result = self.export(doc)
            pdf = Pdf(result)
            self.assertEqual(result['pdf']['knockout_groups'], 1)
            self.assertEqual(result['pdf']['image_pixels'], 0)
            functions = [o for o in pdf.objects.values() if isinstance(o,dict) and o.get('FunctionType') == 4]
            self.assertEqual(len(functions), 2)
            self.assertFalse(any(isinstance(o,dict) and o.get('Subtype') == 'Image' for o in pdf.objects.values()))
            self.assertIn(b'/ShadingType 2', pdf.data)
            original = png_pixels(base64.b64decode(self.cli('document.export',document=doc,format='png')['data']))[2]
            for y in range(H):
                for x in range(W):
                    p = original[4*(y*W+x):4*(y*W+x)+4]
                    e = expected(x+.5,y+.5)
                    self.assertLessEqual(abs(p[3]-round(255*e[3])),1)
                    self.assertLessEqual(max(abs(c*p[3]/255 - 255*z) for c,z in zip(p[:3],e[:3])),1)

    def compare(self, read):
        for isolated in [True, False]:
            data = Pdf(self.export(sheet(isolated))).data
            errors = list(sample_errors(read(data,W,H)))
            self.assertLessEqual(max(errors), 6, (isolated,max(errors)))
            self.assertLessEqual(sum(errors)/len(errors), 2)

    @unittest.skipUnless(pymupdf,'requires MuPDF')
    def test_mupdf_overlaps_and_transparent_page(self):
        self.compare(read_mupdf)
        with pymupdf.open(stream=Pdf(self.export(sheet(True))).data,filetype='pdf') as pdf:
            pix = pdf[0].get_pixmap(dpi=288,alpha=True)
            for y in range(H):
                for x in range(W):
                    self.assertLessEqual(abs(pix.pixel(4*x+2,4*y+2)[3]-round(255*expected(x+.5,y+.5)[3])), 5)

    @unittest.skipUnless(shutil.which('pdftoppm'),'requires Poppler')
    def test_poppler_overlaps_and_transparent_page(self):
        self.compare(lambda data,w,h: poppler_rgb(data,288,4*w,4*h))

    def test_masked_fill_and_stroke_form_one_footprint(self):
        items = [source(), rect('gray',w=32,h=12,parent='source',color=[255,255,255,128]),
                 dict(id='k',content=dict(type='group',knockout=True)),
                 rect('base',w=32,h=12,parent='k',color=[255,0,0,255])]
        ink = rect('ink',x=4,y=3,w=23,h=6,parent='k',color=[0,0,255,128],fill_opacity=.5)
        ink['content']['stroke'] = dict(width=4,color=[0,0,255,128])
        doc = paper(32,12,[*items,ink])
        cases = [dict(artwork_mask=dict(mask(mode='alpha'),region=[0,0,32,12])),
                 dict(mask=dict(width=2,height=1,gray_hex='807f',transform=[32,0,0,12,0,0])),
                 dict(mask=dict(width=0,height=0,constant=True,clip=True,density=127/255,gray_hex=''))]
        for controls in cases:
            doc['items'][-1] = dict(ink,**controls)
            result = self.export(doc)
            self.assertEqual(result['pdf']['knockout_groups'], 1)
            self.assertEqual(result['pdf']['image_pixels'], 0)
            for reader, rgb in reader_samples(Pdf(result).data, 32, 12):
                for y, coverage in [(1,128/255), (3,1-(1-128/255)**2), (6,128/255)]:
                    f = coverage*128/255
                    actual = white_pixel(rgb, 32, 10, y)
                    # Over white: red remains outside, white comes through the
                    # knocked out part, and the blue fill contributes f/2.
                    want = [1-f/2,f/2,f]
                    self.assertLessEqual(max(abs(b-round(255*c)) for b,c in zip(actual,want)), 4, reader)

    def test_nested_member_replaces_siblings_as_a_unit(self):
        lower, upper = [60, 210, 40, 145], [130, 50, 230, 160]
        cases = [(True, 'through', 'multiply'), (False, 'through', 'normal'),
                 (False, 'isolated', 'multiply'), (False, 'frame', 'multiply'),
                 (True, 'knockout', 'normal')]
        for isolated, kind, blend in cases:
            with self.subTest(isolated=isolated, kind=kind, blend=blend):
                member = (dict(type='frame', frame=dict(role='frame', width=16, height=10))
                          if kind == 'frame' else dict(type='group', isolated=kind != 'through',
                                                      knockout=kind == 'knockout'))
                items = [rect('page', w=30, h=10, color=BACK),
                         dict(id='k', content=dict(type='group', isolated=isolated, knockout=True)),
                         rect('base', w=30, h=10, color=RED, parent='k'),
                         dict(id='pair', parent='k', opacity=.5, content=member,
                              transform=[1, 0, 0, 1, 3, 0], clip=box(1, 0, 16, 10)),
                         rect('lower', w=11, h=10, color=lower, parent='pair'),
                         rect('upper', x=7, w=15, h=10, color=upper, blend=blend, parent='pair'),
                         rect('hidden', w=30, h=10, parent='pair', opacity=0, visible=False)]
                doc = paper(30, 10, items)
                result = self.export(doc)
                self.assertEqual(result['pdf']['knockout_groups'], 1 + (kind == 'knockout'))
                png = png_pixels(base64.b64decode(self.cli('document.export', document=doc, format='png')['data']))[2]
                rendered = list(reader_samples(Pdf(result).data, 30, 10))
                for x in range(30):
                    pair = [0]*4
                    if 4 <= x < (19 if kind == 'frame' else 20):
                        if x < 14:
                            pair = premul(lower)
                        if x >= 10:
                            pair = over(pair, premul(upper), mode=blend)
                    # The pair's retained footprint is the union of both paints.
                    within = [c*.5 + r*(1-pair[3]) for c, r in zip(pair, premul(RED))]
                    actual = over(premul(BACK), within)
                    pos = 4*(5*30+x)
                    self.assertLessEqual(abs(png[pos+3]-round(255*actual[3])), 1)
                    for i in range(3):
                        self.assertLessEqual(abs(png[pos+i]*png[pos+3]/255-255*actual[i]), 1)
                    white = [round(255*(c+1-actual[3])) for c in actual[:3]]
                    for reader, rgb in rendered:
                        self.assertLessEqual(max(abs(a-b) for a,b in zip(white_pixel(rgb, 30, x, 5), white)), 5,
                                             (reader, x, white))
                if kind == 'through' and not isolated:
                    items[-2]['blend'] = 'multiply'
                    error = self.cli('document.export', document=doc, format='pdf', error='UNSUPPORTED')
                    self.assertEqual(error['item_id'], 'upper')

    def test_raster_member_reuses_intrinsic_alpha_without_copying_pixels(self):
        values = [0, 64, 128, 255]
        items = [dict(id='k', content=dict(type='group', knockout=True)),
                 layer('red', [[255, 0, 0, 255]], parent='k', transform=[16, 0, 0, 4, 0, 0]),
                 layer('blue', [[0, 0, 255, a] for a in values], parent='k',
                       transform=[4, 0, 0, 4, 0, 0], opacity=.5)]
        result = self.export(dict(paper(16, 4, items), kind='raster'))
        pdf = Pdf(result)
        images = [o for o in pdf.objects.values() if isinstance(o, dict) and o.get('Subtype') == 'Image']
        self.assertEqual([len(images), result['pdf']['image_pixels']], [3, 5])
        for reader, rgb in reader_samples(pdf.data, 16, 4):
            for i, a in enumerate(values):
                expected = [255-a/2, a/2, a]
                actual = white_pixel(rgb, 16, i*4+2, 2)
                self.assertLessEqual(max(abs(c-round(v)) for c,v in zip(actual, expected)), 3, reader)

    def test_member_artwork_mask_and_group_mask_have_distinct_roles(self):
        for mode, weight in [('alpha', 1), ('luminance', .7154)]:
            patch = rect('patch', w=8, h=6, parent='source', color=[0,255,0,128])
            group_mask = dict(width=0, height=0, constant=True, clip=True, gray_hex='', density=.5)
            k = dict(id='k', content=dict(type='group', knockout=True), mask=group_mask, opacity=.8)
            child = rect('blue', w=16, h=6, parent='k', color=[0,0,255,255], opacity=.25,
                         artwork_mask=mask(mode=mode, transform=[1,0,0,1,3,0]))
            doc = paper(16, 6, [source(), patch, k, rect('red', w=16, h=6, parent='k', color=[255,0,0,255]), child])
            pdf = Pdf(self.export(doc))
            for reader, rgb in reader_samples(pdf.data, 16, 6):
                for x in range(16):
                    f = (128/255)*weight if 3 <= x < 11 else 0
                    # The group mask fades the complete red/blue result over white.
                    inside = [1-.25*f, .75*f, f]
                    white = [round(255*(.6+.4*c)) for c in inside]
                    actual = white_pixel(rgb, 16, x, 2)
                    self.assertLessEqual(max(abs(a-b) for a,b in zip(actual,white)), 4, (mode, reader, x))

    def test_working_profile_and_opacity_near_one(self):
        k = dict(id='k', content=dict(type='group', knockout=True))
        items = [k, rect('red', w=16, h=6, parent='k', color=[255,0,0,255])]
        for i, alpha in enumerate((0, 128, 254, 255)):
            items.append(rect(f'gray-{i}', x=4*i, w=4, h=6, parent='k', color=[0,0,0,alpha],
                              opacity=math.nextafter(1., 0.)))
        pdf = Pdf(self.export(dict(paper(16, 6, items), output_profile=builtin('srgb'))))
        self.assertIn(b'/ICCBased', pdf.data)
        if pymupdf:
            with pymupdf.open(stream=pdf.data, filetype='pdf') as document:
                pix = document[0].get_pixmap(dpi=288, alpha=True)
                for i, alpha in enumerate((0, 128, 254, 255)):
                    r,g,b,a = pix.pixel(16*i+8, 10)
                    self.assertGreaterEqual(a, 254)
                    self.assertLessEqual(max(abs(r-(255-alpha)), g, b), 4)

    def test_text_cuts_a_vector_hole_on_a_selected_artboard(self):
        (self.root/'fixture.ttf').write_bytes(geometric_font())
        (self.root/'license.txt').write_text('Original geometric font fixture.', encoding='utf-8')
        font = self.cli('font.import', source_path='fixture.ttf', license_path='license.txt')
        board = dict(id='board', transform=[1, 0, 0, 1, 16, 3], content=dict(type='frame', frame=dict(
                     role='artboard', width=12, height=8, bleed=dict(left=1, top=2))))
        text = dict(id='letters', parent='k', opacity=0, content=dict(type='text', frame=dict(text='AA',
                    width=12, height=10, overflow='visible', style=dict(font_id='draw', size=10, fill=BLUE[:3]+[255]))))
        doc = dict(paper(32, 16, [board, rect('page', parent='board', color=[0,0,255,255]),
                   dict(id='k', parent='board', content=dict(type='group', knockout=True)),
                   rect('red', parent='k', color=[255,0,0,255]), text]), fonts={'draw': font})
        result = self.export(doc, artboards=dict(type='ids', ids=['board']), include_bleed=True)
        pdf = Pdf(result)
        self.assertEqual(result['pdf']['image_pixels'], 0)
        self.assertIn(b'/Subtype /Form', pdf.data)
        for reader, rgb in reader_samples(pdf.data, 13, 10):
            for x, y, color in [(3, 7, [0,0,255]), (6, 7, [255,0,0]), (9, 7, [0,0,255]),
                                (9, 2, [255,0,0]), (0, 0, [255]*3)]:
                self.assertEqual(white_pixel(rgb, 13, x, y), color, (reader, x, y))

    def test_explicit_color_container_mark_and_depth_boundaries_are_atomic(self):
        doc = sheet(True)
        for opts in (dict(color='native_inks'),dict(marks=dict(crop=True,registration=False))):
            self.cli('document.publish',document=doc,output=dict(format='pdf',file_name='bad.pdf',pdf_options=opts),
                     error='UNSUPPORTED')
        self.cli('document.export',document=dict(doc,output_profile=builtin('linear_srgb')),format='pdf',error='UNSUPPORTED')
        nested = copy.deepcopy(doc)
        nested['items'].append(dict(id='inner',parent='knock',content=dict(type='group')))
        nested['items'].append(rect('faded',parent='inner',opacity=0))
        self.assertEqual(self.cli('document.export',document=nested,format='pdf',error='UNSUPPORTED')['item_id'],'faded')
        through = sheet(False)
        through['items'][3]['blend'] = 'screen'
        self.assertEqual(self.cli('document.export',document=through,format='pdf',error='UNSUPPORTED')['item_id'],'ramp')
        depth = self.cli('capabilities')['pdf']['knockout_groups']['max_attenuation_depth_including_ancestors']
        g = dict(id='k',content=dict(type='group',knockout=True))
        items = [g,rect('first',w=6,h=4,parent='k')]
        color = [0, 55, 200, 128]
        items.extend(rect(f'partial-{i}',w=3,h=4,parent='k',opacity=.5,color=color) for i in range(depth))
        full = paper(6,4,items)
        pdf = Pdf(self.export(full))
        retained = (1-color[3]/255)**depth
        white = [round(255*retained+(255+c)*.5*(1-retained)) for c in color[:3]]
        for reader, rgb in reader_samples(pdf.data, 6, 4):
            self.assertLessEqual(max(abs(a-b) for a,b in zip(white_pixel(rgb, 6, 1, 2), white)), 5, reader)
            self.assertEqual(white_pixel(rgb, 6, 4, 2), [255]*3)
        items.append(rect('overflow',w=3,h=4,parent='k',opacity=.5))
        error = self.cli('document.publish',document=full,output=dict(format='pdf',file_name='bad.pdf'),error='RESOURCE_LIMIT')
        self.assertEqual(error['item_id'],'overflow')
        self.assertFalse((self.root/'bad.pdf').exists())

    def test_pinned_mcp_publication_survives_a_knockout_edit_and_retry(self):
        doc = sheet(True)
        with closing(Client(('--tools','essentials'),workspace=self.root)) as client:
            client.initialize()
            def run(cmd,**args):
                return client.tool('run',command=cmd,arguments=args)['structuredContent']
            self.assertTrue(run('session.create',session_id='work',request_id='start',document=doc)['ok'])
            op = dict(type='edit',operations=[dict(op='properties',id='clear',opacity=.6)])
            args = dict(session_id='work',expected_revision=0,request_id='edit',action=op)
            self.assertTrue(run('session.apply',**args)['ok'])
            self.assertTrue(run('session.apply',**args)['ok'])
            out = dict(format='pdf',file_name='original.pdf')
            ref = dict(session_id='work',revision=0)
            self.assertTrue(run('document.preflight',document=ref,output=out)['result']['ready'])
            self.assertTrue(run('document.publish',document=ref,output=out)['ok'])
            published = (self.root/'original.pdf').read_bytes()
            self.assertEqual(published,Pdf(self.export(doc)).data)
            self.assertNotEqual(published,Pdf(self.export(dict(ref,revision=1))).data)
            self.assertEqual(run('document.publish',document=ref,output=out)['error']['code'],'OUTPUT_EXISTS')

    def test_depth_follows_masked_descendants_and_independent_branches(self):
        items = []
        def branch(label, steps):
            items.append(dict(id=label, content=dict(type='group', knockout=True)))
            parent = label
            for i in range(4):
                name = f'{label}-group-{i}'
                grid = dict(width=2, height=1, gray_hex='80ff', transform=[3,0,0,4,0,0])
                items.append(dict(id=name, parent=parent, mask=grid, content=dict(type='group', knockout=True)))
                parent = name
            items.append(rect(label+'-red', w=6, h=4, parent=parent, color=[255,0,0,255]))
            for i in range(steps):
                items.append(rect(f'{label}-paint-{i}', w=2, h=4, parent=label, opacity=.5, color=[0,0,200,128]))
        branch('a', 12)
        branch('b', 12)
        doc = paper(6, 4, items)
        pdf = Pdf(self.export(doc))
        for reader, rgb in reader_samples(pdf.data, 6, 4):
            self.assertEqual(white_pixel(rgb, 6, 4, 2), [255,0,0], reader)
        branch('deep', 24)
        error = self.cli('document.publish', document=doc, output=dict(format='pdf', file_name='deep.pdf'),
                         error='RESOURCE_LIMIT')
        self.assertIn('reference depth', error['message'])
        self.assertFalse((self.root/'deep.pdf').exists())
