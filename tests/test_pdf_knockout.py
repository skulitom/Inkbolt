"""Check PDF knockout colors and alpha against independent sibling-footprint math."""
from contextlib import closing
import base64
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


PANEL_W, PANEL_H = 60, 24
# The alpha ramps and owner controls vary independently in the overlap.
PATCHES = [
    ('horizontal', 2, 1, 46, 19, [25, 175, 90, 204], .25, .6),
    ('vertical', 17, 4, 38, 18, [216, 80, 35, 164], .8, 1),
    ('hole', 29, 6, 17, 9, [15, 22, 160, 255], 0, 1),
    ('top', 34, 11, 15, 10, [70, 115, 230, 255], 1, 1),
]


def faded_panel(kind, opacity):
    member = (dict(type='frame', frame=dict(role='frame', width=50, height=20, background=BLUE))
              if kind == 'frame' else dict(type='group', isolated=kind != 'through', knockout=kind == 'knockout'))
    items = [rect('page', w=30, h=PANEL_H, color=BACK),
             dict(id='root', content=dict(type='group', isolated=kind != 'through', knockout=True)),
             rect('prior', w=PANEL_W, h=PANEL_H, parent='root', color=RED, opacity=.65),
             dict(id='panel', parent='root', content=member, opacity=opacity, clip=box(1,1,56,21))]
    for name,x,y,w,h,rgba,weight,fill in PATCHES:
        paint = rgba
        if name in ('horizontal','vertical'):
            end = [x+w,y] if name=='horizontal' else [x,y+h]
            paint = dict(type='linear', start=[x,y], end=end, stops=[
                dict(offset=0,color=rgba[:3]+[0]),dict(offset=1,color=rgba)])
        items.append(rect(name,x=x,y=y,w=w,h=h,parent='panel',color=paint,opacity=weight,fill_opacity=fill))
    return paper(PANEL_W,PANEL_H,items)


def panel_reference(kind, opacity, px, py):
    def contribution(rgba, a):
        return [a*c/255 for c in rgba[:3]]+[a]
    f = 0.
    child = [0.]*4
    if 1 <= px < 57 and 1 <= py < 22 and (kind != 'frame' or (px < 50 and py < 20)):
        if kind == 'frame':
            f = BLUE[3]/255
            child = contribution(BLUE, f)
        for name,x,y,w,h,rgba,weight,fill in PATCHES:
            if x <= px < x+w and y <= py < y+h:
                coverage = rgba[3]/255
                if name == 'horizontal':
                    coverage *= (px-x)/w
                if name == 'vertical':
                    coverage *= (py-y)/h
                a = coverage*weight*fill
                retain = 1-(coverage if kind=='knockout' else a)
                child = [d*retain+s for d,s in zip(child,contribution(rgba,a))]
                f = coverage+f*(1-coverage)
    prior = contribution(RED, .65*RED[3]/255)
    group = [d*(1-f)+s*opacity for d,s in zip(prior,child)]
    backdrop = contribution(BACK, BACK[3]/255 if px<30 else 0)
    return [c+b*(1-group[3]) for c,b in zip(group,backdrop)]


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

    def test_separately_faded_subgroups_match_a_color_and_coverage_reference(self):
        for kind, weight in [('isolated',.65), ('through',1), ('knockout',.75), ('frame',.5), ('isolated',0)]:
            with self.subTest(kind=kind, weight=weight):
                doc = faded_panel(kind,weight)
                out = self.export(doc)
                pdf = Pdf(out)
                self.assertEqual(out['pdf']['image_pixels'], 0)
                if weight:
                    self.assertEqual(out['pdf']['knockout_field_masks'], 1)
                    self.assertEqual(out['pdf']['version'], '2.0')
                    self.assertIn(b'/BM /ColorDodge', pdf.data)
                else:
                    self.assertNotIn('knockout_field_masks',out['pdf'])
                png = png_pixels(base64.b64decode(self.cli('document.export',document=doc,format='png')['data']))[2]
                for y in range(PANEL_H):
                    for x in range(PANEL_W):
                        ref = panel_reference(kind,weight,x+.5,y+.5)
                        i = 4*(y*PANEL_W+x)
                        a = png[i+3]
                        self.assertLessEqual(abs(a-255*ref[3]),1)
                        self.assertLessEqual(max(abs(c*a/255-255*v) for c,v in zip(png[i:i+3],ref)),1)
                for reader, rgb in reader_samples(pdf.data, PANEL_W, PANEL_H):
                    errors = []
                    for y in range(PANEL_H):
                        for x in range(PANEL_W):
                            ref = panel_reference(kind,weight,x+.625,y+.625)
                            want = [round(255*(v+1-ref[3])) for v in ref[:3]]
                            errors.append(max(abs(c-e) for c,e in zip(white_pixel(rgb,PANEL_W,x,y),want)))
                    self.assertLessEqual(max(errors), 6, (reader,kind))
                    self.assertLessEqual(sum(errors)/len(errors), 2.1, (reader,kind))

    def test_nested_knockouts_propagate_the_union_through_two_boundaries(self):
        def knockout(id, **kw):
            return dict(id=id,content=dict(type='group',knockout=True),**kw)
        items = [knockout('root'), rect('red',w=16,h=4,parent='root',color=[255,0,0,255]),
                 knockout('inner',parent='root',opacity=.75),
                 rect('green',w=16,h=4,parent='inner',color=[0,255,0,128],opacity=.5),
                 dict(id='pair',parent='inner',content=dict(type='group'),opacity=.6),
                 rect('blue',w=12,h=4,parent='pair',color=[0,0,255,170],fill_opacity=.4),
                 rect('clear',x=8,w=8,h=4,parent='pair',color=[255,255,255,255],opacity=0)]
        out = self.export(paper(16,4,items))
        self.assertEqual(out['pdf']['knockout_field_masks'], 2)
        for reader, rgb in reader_samples(Pdf(out).data,16,4):
            for x in range(16):
                blue = 170/255 if x < 12 else 0
                pair_shape = 1 if x >= 8 else blue
                inner_shape = pair_shape+(1-pair_shape)*128/255
                green = .75*(1-pair_shape)*.5*128/255
                blue_ink = .75*.6*.4*blue
                red = 1-inner_shape
                white = 1-red-green-blue_ink
                want = [round(255*(v+white)) for v in [red,green,blue_ink]]
                self.assertLessEqual(max(abs(a-b) for a,b in zip(white_pixel(rgb,16,x,2),want)), 5, (reader,x))

    def test_masked_pass_through_descendant_keeps_its_internal_backdrop(self):
        items = [source(),rect('maskpatch',w=16,h=4,parent='source',color=[255,255,255,192]),
                 dict(id='k',content=dict(type='group',knockout=True)),
                 rect('red',w=16,h=4,parent='k',color=RED),
                 dict(id='panel',parent='k',content=dict(type='group'),opacity=.8),
                 rect('lower',w=14,h=4,parent='panel',color=BACK,opacity=.75),
                 dict(id='through',parent='panel',content=dict(type='group',isolated=False),opacity=.6,
                      artwork_mask=dict(source='source',mode='alpha',region=[0,0,16,4])),
                 rect('top',x=4,w=12,h=4,parent='through',color=BLUE,blend='multiply',fill_opacity=.7)]
        out = self.export(paper(16,4,items))
        for reader,rgb in reader_samples(Pdf(out).data,16,4):
            for x in range(16):
                lo = premul(BACK) if x<14 else [0]*4
                hi = premul(BLUE) if x>=4 else [0]*4
                base = [v*.75 for v in lo]
                painted = over(base,hi,opacity=.7,mode='multiply')
                member = [b+(t-b)*.6*192/255 for b,t in zip(base,painted)]
                shape = lo[3]+(1-lo[3])*hi[3]*192/255
                group = [s*.8+b*(1-shape) for s,b in zip(member,premul(RED))]
                want = [round(255*(v+1-group[3])) for v in group[:3]]
                self.assertLessEqual(max(abs(a-b) for a,b in zip(white_pixel(rgb,16,x,2),want)), 6, (reader,x))

    def test_first_member_needs_no_extra_footprint_paths(self):
        doc = faded_panel('frame',.5)
        doc['items'] = [item for item in doc['items'] if item['id']!='prior']
        knockout = self.export(doc)['pdf']
        self.assertNotIn('knockout_field_masks',knockout)
        self.assertEqual(knockout['version'],'1.7')
        root = next(item for item in doc['items'] if item['id']=='root')
        root['content']['knockout'] = False
        self.assertEqual(knockout['path_commands'],self.export(doc)['pdf']['path_commands'])

    def test_recursive_field_masks_charge_the_existing_reference_depth(self):
        items = []
        for i in range(7):
            placement = dict(parent=f'k{i-1}',opacity=.6) if i else {}
            items.append(dict(id=f'k{i}',content=dict(type='group',knockout=True),**placement))
            items.append(rect(f'paint{i}',w=5,h=4,color=[0,60,180,128],parent=f'k{i}',opacity=.5))
        doc = paper(6,4,items)
        output = dict(format='pdf',file_name='deep.pdf')
        self.assertFalse(self.cli('document.preflight',document=doc,output=output)['ready'])
        error = self.cli('document.publish',document=doc,output=output,error='RESOURCE_LIMIT')
        self.assertIn('reference depth',error['message'])
        self.assertIn(error['item_id'],[f'k{i}' for i in range(7)])
        self.assertFalse((self.root/'deep.pdf').exists())

    def test_one_masked_pixel_source_supplies_paint_and_footprint(self):
        mask_field = dict(width=4,height=1,gray_hex='ff8040ff',transform=[4,0,0,4,0,0],linked=False)
        reveal = dict(source='source',mode='alpha',region=[0,0,16,4])
        items = [source(), rect('patch',w=16,h=4,parent='source',color=[0,0,0,192]),
                 dict(id='k',content=dict(type='group',knockout=True)),
                 layer('prior',[[255,0,0,255]],parent='k',transform=[16,0,0,4,0,0]),
                 dict(id='panel',parent='k',content=dict(type='group'),opacity=.6,artwork_mask=reveal),
                 layer('pixels',[[0,0,255,a] for a in (0,128,255,160)],parent='panel',
                       transform=[4,0,0,4,0,0],opacity=.5,mask=mask_field)]
        doc = dict(paper(16,4,items),kind='raster')
        for member_mask in ['grid','artwork']:
            if member_mask == 'artwork':
                del items[-1]['mask']
                items[-1]['artwork_mask'] = dict(reveal,linked=False)
            out = self.export(doc)
            self.assertEqual(out['pdf']['image_pixels'], 5)
            self.assertEqual(out['pdf']['artwork_masks']['alpha'], 1 if member_mask=='grid' else 2)
            pdf = Pdf(out)
            images = [o for o in pdf.objects.values() if isinstance(o,dict) and o.get('Subtype')=='Image']
            self.assertEqual(len(images),4 if member_mask=='grid' else 3)
            for reader,rgb in reader_samples(pdf.data,16,4):
                for i, (alpha, grid) in enumerate(zip((0,128,255,160),(255,128,64,255))):
                    f = alpha/255 * (grid if member_mask=='grid' else 192)/255 * 192/255
                    a = f*.5*.6
                    want = [round(255*v) for v in (1-a,f-a,f)]
                    actual = white_pixel(rgb,16,4*i+2,2)
                    self.assertLessEqual(max(abs(c-v) for c,v in zip(actual,want)), 5, (reader,i,member_mask))

    @unittest.skipUnless(pymupdf, 'requires MuPDF')
    def test_working_profile_retains_independent_alpha_on_a_transparent_page(self):
        doc = dict(faded_panel('isolated',.65),output_profile=builtin('srgb'))
        pdf = Pdf(self.export(doc))
        self.assertIn(b'/ICCBased',pdf.data)
        with pymupdf.open(stream=pdf.data,filetype='pdf') as pages:
            pixels = pages[0].get_pixmap(dpi=288,alpha=True)
            for y in range(PANEL_H):
                for x in range(PANEL_W):
                    expected = panel_reference('isolated',.65,x+.625,y+.625)
                    actual = pixels.pixel(4*x+2,4*y+2)
                    self.assertLessEqual(abs(actual[3]-round(255*expected[3])), 5, (x,y))

    def test_imported_svg_with_a_faded_subgroup_can_publish_a_saved_revision(self):
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="20" height="12">'
               '<g id="stack"><rect width="20" height="12" fill="red"/>'
               '<g id="panel"><rect width="10" height="12" opacity=".4" fill="blue"/>'
               '<rect x="6" width="8" height="12" opacity="0" fill="black"/></g></g></svg>')
        doc = self.cli('svg.import',id='draw',source=dict(kind='text',text=svg))['document']
        stack, = [item['id'] for item in doc['items'] if item['name']=='stack']
        with closing(Client(('--tools','essentials'),workspace=self.root)) as client:
            client.initialize()
            def run(cmd, **args):
                return client.tool('run',command=cmd,arguments=args)['structuredContent']
            self.assertTrue(run('session.create',session_id='art',request_id='start',document=doc)['ok'])
            args = dict(session_id='art',expected_revision=0,request_id='cut',
                        action=dict(type='edit',operations=[dict(op='group_options',id=stack,isolated=True,knockout=True)]))
            self.assertTrue(run('session.apply',**args)['ok'])
            self.assertTrue(run('session.apply',**args)['ok'])
            self.assertTrue(run('session.apply',session_id='art',expected_revision=1,request_id='restore',
                                action=dict(type='undo'))['ok'])
            saved = dict(session_id='art',revision=1)
            out = dict(format='pdf',file_name='drawing.pdf')
            self.assertTrue(run('document.preflight',document=saved,output=out)['result']['ready'])
            self.assertEqual(run('document.publish',document=saved,output=out)['result']['pdf']['knockout_field_masks'],1)
            issued = (self.root/'drawing.pdf').read_bytes()
            self.assertEqual(issued,Pdf(self.export(saved)).data)
            self.assertEqual(Pdf(self.export(dict(saved,revision=2))).data,Pdf(self.export(doc)).data)
            self.assertEqual(run('document.publish',document=dict(saved,revision=2),output=out)['error']['code'],'OUTPUT_EXISTS')
            self.assertEqual((self.root/'drawing.pdf').read_bytes(),issued)

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
