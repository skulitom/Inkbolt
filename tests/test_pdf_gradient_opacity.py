"""Independent stop, placement and pixel checks for vector PDF opacity shadings."""
import base64
import bisect
from contextlib import closing
import math
from pathlib import Path
import shutil
import tempfile
import unittest

from pdf_reader import Pdf
import test_editing_cli as editing
from test_mcp import Client
from test_pdf_blends_cli import document, rectangle, poppler_rgb, pymupdf
from test_profiles_cli import builtin


WIDTH, HEIGHT = 128, 88
BACK = [27, 90, 148]
STOPS = [(0, [225, 38, 89, 0]), (.5, [40, 190, 80, 176]),
         (.5, [65, 80, 230, 68]), (1, [208, 65, 70, 208]), (1, [230, 180, 28, 255])]


def sheet(kind):
    field = dict(type=kind, transform=[1.5, 0, 0, .75, 4, 3],
                 stops=[dict(offset=t, color=c[:]) for t,c in STOPS])
    if kind == 'linear':
        field.update(start=[8, 0], end=[56, 0])
    else:
        field.update(center=[32, 38], radius=30)
    return document(WIDTH, HEIGHT, [
        rectangle('back', 64, 0, 64, HEIGHT, [*BACK, 255]),
        dict(id='group', transform=[1, 0, 0, 1, 6, 4], opacity=.75, content=dict(type='group', isolated=True)),
        rectangle('gradient', 0, 0, 110, 72, field, parent='group', transform=[1, 0, 0, 1, 4, 4], opacity=.8),
    ])


def ramp(t):
    t = min(1, max(0, t))
    hi = bisect.bisect_right([stop for stop, _ in STOPS], t)
    if hi == len(STOPS):
        return STOPS[-1][1]
    t0, a = STOPS[hi-1]
    t1, b = STOPS[hi]
    return [x+(y-x)*(t-t0)/(t1-t0) for x,y in zip(a,b)]


def samples(kind):
    # Upper bound on the gradient-parameter change from the center of a pixel
    # to its footprint. A reader can cover both sides of a hard stop in that pixel.
    half = .5/1.5/48 if kind == 'linear' else math.hypot(.5/1.5, .5/.75)/30
    for y in range(HEIGHT):
        for x in range(WIDTH):
            u = (x+.5-14)/1.5
            v = (y+.5-11)/.75
            t = (u-8)/48 if kind == 'linear' else math.hypot(u-32, v-38)/30
            color = ramp(t)
            painted = 10 <= x < 120 and 8 <= y < 80
            alpha = color[3]/255 * .6 if painted else 0
            back = BACK if x >= 64 else [255]*3
            rgb = [round(c*alpha+b*(1-alpha)) for c,b in zip(color,back)]
            expected = [*rgb, 255 if x >= 64 else round(255*alpha)]
            bounds = [(v,v) for v in expected]
            if painted and min(abs(t-.5), abs(t-1)) <= half:
                sides = [ramp(t-half), ramp(t+half)]
                sides.extend(c for pos,c in STOPS if abs(pos-t) <= half)
                opacities = [c[3]/255*.6 for c in sides]
                for i in range(3):
                    values = [round(c[i]*a + back[i]*(1-a)) for c in sides for a in opacities]
                    bounds[i] = min(values), max(values)
                if x < 64:
                    bounds[3] = round(255*min(opacities)), round(255*max(opacities))
            yield x, y, expected, bounds


def center(buf, channels, x, y, width=WIDTH):
    # Mean of the four center samples of a 4x raster, centered on the logical pixel.
    offsets = [((4*y+j)*(4*width)+4*x+i)*channels for j in (1, 2) for i in (1, 2)]
    return [round(sum(buf[o+c] for o in offsets)/4) for c in range(channels)]


class GradientOpacityTests(unittest.TestCase):
    invoke = editing.EditingCliTests.invoke

    def export(self, artwork, fmt='pdf', **kw):
        return self.invoke(dict(command='document.export', document=artwork, format=fmt, **kw))

    def test_mask_matches_gradient_geometry_stop_sides_and_resources(self):
        reported = self.invoke(dict(command='capabilities'))['pdf']['paints']
        for kind, name, shading_type in [('linear','axial',2), ('radial','radial',3)]:
            self.assertIn(f'{name}_pad_srgb_varying_alpha', reported)
            for profile in (None, builtin('srgb')):
                artwork = sheet(kind)
                if profile:
                    artwork['output_profile'] = profile
                artifact = self.export(artwork)
                reader = Pdf(artifact)
                self.assertEqual(artifact['pdf']['gradient_opacity_masks'], 1)
                self.assertTrue(any('hard stop' in loss for loss in artifact['losses']))
                self.assertEqual(artifact['pdf']['image_pixels'], 0)
                objects = [v for v in reader.objects.values() if isinstance(v, dict)]
                mask, = [v['SMask'] for v in objects if isinstance(v.get('SMask'), dict)]
                self.assertEqual((mask['S'], mask['BC']), ('Luminosity', [0]))
                form = reader.get(mask['G'])
                self.assertEqual(form['Group'], dict(S='Transparency', CS='DeviceGray', I=True))
                self.assertEqual(form['BBox'], [0, 0, WIDTH, HEIGHT])
                gray_id, = form['Resources']['Shading'].values()
                gray = reader.get(gray_id)
                rgb, = [v for v in objects if v.get('ColorSpace') == 'DeviceRGB' and 'ShadingType' in v]
                self.assertEqual(gray['ColorSpace'], 'DeviceGray')
                for key in ('ShadingType', 'Coords', 'Domain', 'Extend'):
                    self.assertEqual(gray[key], rgb[key])
                self.assertEqual(gray['ShadingType'], shading_type)
                self.assertIn(b'1.5 0 0 0.75 14 11 cm', reader.streams[mask['G']])
                for shading, channels in [(rgb,slice(0,3)), (gray,slice(3,4))]:
                    function = reader.get(shading['Function'])
                    self.assertEqual(function['Bounds'], [.5, 1])
                    pieces = [reader.get(ref) for ref in function['Functions']]
                    for side, stop_indices in [('C0', [0,2,4]), ('C1', [1,3,4])]:
                        self.assertEqual([p[side] for p in pieces],
                                         [[n/255 for n in STOPS[i][1][channels]] for i in stop_indices])

    def test_preview_agrees_with_transformed_independent_rgba(self):
        for kind in ('linear', 'radial'):
            data = base64.b64decode(self.export(sheet(kind),'png')['data'])
            w, h, rgba, _ = editing.png_pixels(data)
            self.assertEqual((w,h), (WIDTH,HEIGHT))
            for x,y,expected,_ in samples(kind):
                pos = (y*w+x)*4
                r,g,b,a = rgba[pos:pos+4]
                on_white = [round(v*a/255+255-a) for v in (r,g,b)]
                self.assertLessEqual(max(abs(p-q) for p,q in zip([*on_white,a],expected)), 1, (kind,x,y))

    def test_selected_artboards_use_their_own_mask_bounds_and_bleed(self):
        gradient = dict(type='linear',start=[0,0],end=[16,0],
                        stops=[dict(offset=0,color=[16,80,180,0]),dict(offset=1,color=[16,80,180,255])])
        def board(key, width, height, x):
            frame = dict(role='artboard',width=width,height=height,
                         bleed=dict(top=1,right=2,bottom=3,left=4))
            return dict(id=key,transform=[1,0,0,1,x,6],content=dict(type='frame',frame=frame))
        artwork = document(80,32,[board('first',32,16,1),board('second',18,24,45),
                                  rectangle('a',0,0,32,16,gradient,parent='first'),
                                  rectangle('b',0,0,18,24,gradient,parent='second')])
        result = self.export(artwork,pdf_options=dict(artboards=dict(type='ids',ids=['second','first']),include_bleed=True))
        reader = Pdf(result)
        masks = [reader.get(v['SMask']['G']) for v in reader.objects.values()
                 if isinstance(v,dict) and isinstance(v.get('SMask'),dict)]
        self.assertEqual(result['pdf']['gradient_opacity_masks'], 2)
        self.assertEqual([v['artboard_id'] for v in result['pages']], ['second','first'])
        self.assertEqual([mask['BBox'] for mask in masks], [[0,0,24,28],[0,0,38,20]])

    @unittest.skipUnless(shutil.which('pdftoppm'), 'PDF color check requires pdftoppm')
    def test_poppler_renders_transformed_gradients_over_paper_and_color(self):
        for kind in ('linear', 'radial'):
            rgb = poppler_rgb(Pdf(self.export(sheet(kind))).data, 384, WIDTH*4, HEIGHT*4)
            for x,y,_,bounds in samples(kind):
                for v,(low,high) in zip(center(rgb,3,x,y),bounds):
                    self.assertLessEqual(max(low-v,v-high), 4, (kind,x,y))

    @unittest.skipUnless(pymupdf, 'PDF color and alpha check requires PyMuPDF')
    def test_mupdf_renders_transformed_gradient_opacity_and_color(self):
        for kind in ('linear', 'radial'):
            with pymupdf.open(stream=Pdf(self.export(sheet(kind))).data, filetype='pdf') as pdf:
                rgb = pdf[0].get_pixmap(dpi=384, alpha=False).samples
                rgba = pdf[0].get_pixmap(dpi=384, alpha=True).samples
            for x,y,_,bounds in samples(kind):
                rendered = [*center(rgb,3,x,y), center(rgba,4,x,y)[3]]
                for v,(low,high) in zip(rendered,bounds):
                    self.assertLessEqual(max(low-v,v-high), 5, (kind,x,y))

    @unittest.skipUnless(pymupdf, 'PDF plate and stroke checks require PyMuPDF')
    def test_gradient_only_modulates_its_own_stroke_and_native_process_paint(self):
        fade = dict(type='linear',start=[0,0],end=[64,0],
                    stops=[dict(offset=0,color=[255,255,255,0]),dict(offset=1,color=[255,255,255,255])])
        artwork = document(64,32,[rectangle('blue',4,8,56,16,[0,0,255,255])])
        artwork['items'][0]['content']['stroke'] = dict(width=8,color=fade)
        # Inside and outside the blue fill, the same white stroke fades across x.
        with pymupdf.open(stream=Pdf(self.export(artwork)).data,filetype='pdf') as pdf:
            pixels = pdf[0].get_pixmap(dpi=384,alpha=True).samples
            for x in (12, 28, 44, 52):
                level = round(255*(x+.5)/64)
                for y,expected in [(6,[level]*4), (9,[level,level,255,255]), (16,[0,0,255,255])]:
                    self.assertLessEqual(max(abs(a-b) for a,b in zip(center(pixels,4,x,y,64),expected)), 4)
        artwork['swatches'] = dict(black=dict(name='Black',definition=dict(type='process',
                                        color=dict(space='cmyk',components=[0,0,0,1]))))
        artwork['items'] = [rectangle('k',0,0,64,32,dict(swatch='black')),
                            rectangle('fade',0,0,64,32,fade)]
        result = self.export(artwork,pdf_options=dict(color='native_inks'))
        with pymupdf.open(stream=Pdf(result).data,filetype='pdf') as pdf:
            plates = pdf[0].get_pixmap(dpi=96,colorspace=pymupdf.csCMYK,alpha=False)
            for x in range(64):
                c,m,y,k = plates.pixel(x,16)
                self.assertEqual((c,m,y), (0,0,0))
                self.assertLessEqual(abs(k-round(255*(1-(x+.5)/64))), 3)

    def test_stroke_mask_is_scoped_and_workspace_publication_is_create_only(self):
        artwork = sheet('linear')
        shape = artwork['items'][-1]['content']
        shape['stroke'] = dict(width=6, color=shape['fill'])
        shape['fill'] = [240, 240, 230, 255]
        expected = self.export(artwork)
        self.assertEqual(expected['pdf']['gradient_opacity_masks'], 1)
        with tempfile.TemporaryDirectory() as directory, closing(Client(('--tools','essentials'), workspace=directory)) as client:
            client.initialize()
            path = Path(directory)/'gradient.pdf'
            output = dict(format='pdf', file_name=path.name)
            def request(command):
                return client.tool('run',command=command,arguments=dict(document=artwork,output=output))['structuredContent']
            self.assertTrue(request('document.preflight')['result']['ready'])
            self.assertFalse(path.exists())
            self.assertEqual(request('document.publish')['result']['pdf']['gradient_opacity_masks'], 1)
            self.assertEqual(path.read_bytes(), Pdf(expected).data)
            self.assertEqual(request('document.publish')['error']['code'], 'OUTPUT_EXISTS')
            output.update(file_name='marked.pdf', pdf_options=dict(marks=dict(crop=True)))
            self.assertFalse(request('document.preflight')['result']['ready'])
            self.assertEqual(request('document.publish')['error']['code'], 'UNSUPPORTED')
            self.assertFalse((Path(directory)/'marked.pdf').exists())
