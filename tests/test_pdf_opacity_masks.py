"""Check authored PDF mask samples, placement, composition and create-only delivery."""
from contextlib import closing
from functools import lru_cache
import shutil
import struct
import unittest

from pdf_reader import Pdf, multiply
import test_agent_workspace as workspace
from test_ink_delivery_cli import cmyk, reference
from test_masks_cli import byte, inverse, opacity
from test_mcp import Client
import test_native_masks as native
from test_pdf_blends_cli import document, poppler_rgb, pymupdf, rectangle


W, H = 88, 56


def sheet(sampling):
    # Non-clipping feathered fade and clipped, rotated nearest cells. Both
    # shapes cover the entire page despite the two ancestor translations.
    bilinear = sampling == 'bilinear'
    matrix = [12,0,0,10,20,16] if bilinear else [0,8,-9,0,55,11]
    mask = dict(width=3, height=2, gray_hex='1060ff00b430', transform=matrix,
                clip=not bilinear, invert=True, feather=int(bilinear), density=.75,
                sampling=sampling, linked=not bilinear)
    item = rectangle('ink',-20,-12,W+20,H+12,[0,0,0,255], parent='group',
                     transform=[1,0,0,1,3,2],mask=mask)
    doc = document(W,H,[dict(id='group', transform=[1,0,0,1,4,3], content=dict(type='group')), item])
    doc['resolution_ppi'] = 72
    world = matrix if bilinear else multiply([1,0,0,1,7,5],matrix)
    return doc, dict(mask,transform=world)


@lru_cache(maxsize=2)
def expected_sheet(sampling):
    _, mask = sheet(sampling)
    return bytes(byte(opacity(mask,(x+.5,y+.5))) for y in range(H) for x in range(W))


def center(rgb, x, y):
    return round(sum(rgb[3*((4*y+j)*4*W+4*x+i)] for i in (1,2) for j in (1,2))/4)


class PdfOpacityMaskTests(unittest.TestCase):
    setUp = workspace.AgentWorkspaceTests.setUp
    cli = workspace.AgentWorkspaceTests.cli
    mask = native.NativeMaskTests.mask

    def export(self, doc, **options):
        return self.cli('document.export',document=doc,format='pdf',pdf_options=options)

    def test_each_exported_sample_matches_direct_convolution_and_mapping(self):
        for sampling in ('nearest','bilinear'):
            doc, mask = sheet(sampling)
            result = self.export(doc)
            pdf = Pdf(result)
            states = [o['SMask'] for o in pdf.objects.values() if isinstance(o.get('SMask'),dict)]
            self.assertEqual(len(states),1)
            state = states[0]
            self.assertEqual((state['S'],state['BC']),('Luminosity',[1 if sampling=='bilinear' else .25]))
            group = pdf.get(state['G'])
            self.assertEqual(group['Group'],dict(S='Transparency',CS='DeviceGray',I=True))
            self.assertEqual(group['BBox'],[0,0,W,H])
            pad = mask['feather']+1
            w,h = mask['width']+2*pad,mask['height']+2*pad
            if sampling == 'bilinear':
                ref, = group['Resources']['Shading'].values()
                shading = pdf.get(ref)
                self.assertEqual(shading['ShadingType'],1)
                ref = shading['Function']
                function = pdf.get(ref)
                self.assertEqual((function['Order'],function['Size'],function['BitsPerSample']),(1,[w,h],16))
                domain = [.5-pad,w-.5-pad,.5-pad,h-.5-pad]
                self.assertEqual(shading['Domain'],domain)
                self.assertEqual(function['Domain'],domain)
                matrix = mask['transform']
            else:
                ref, = group['Resources']['XObject'].values()
                obj = pdf.get(ref)
                self.assertEqual((obj['Subtype'],obj['Interpolate'],obj['BitsPerComponent']),('Image',False,16))
                self.assertEqual((obj['Width'],obj['Height']),(w,h))
                matrix = multiply(mask['transform'],[w,0,0,-h,-pad,h-pad])
            self.assertIn((' '.join(map(str,matrix))+' cm').encode(),pdf.streams[state['G']])
            actual = struct.unpack(f'>{w*h}H',pdf.streams[ref])
            local = dict(mask,transform=[1,0,0,1,0,0])
            for i,value in enumerate(actual):
                exact = opacity(local,(i%w-pad+.5,i//w-pad+.5))*65535
                self.assertLessEqual(abs(value-exact),.5000000001)
            self.assertEqual((result['pdf']['grid_masks'],result['pdf']['grid_mask_samples'],result['pdf']['image_pixels']),
                             (1,w*h,0))
            self.assertEqual(len(pdf.paths()),1)
            rgba = bytes.fromhex(self.cli('document.render',document=doc)['data'])
            self.assertLessEqual(max(abs(a-b) for a,b in zip(rgba[3::4],expected_sheet(sampling))),1)

    def compare_reader(self, read):
        for sampling in ('nearest','bilinear'):
            data = Pdf(self.export(sheet(sampling)[0])).data
            rgb = read(data)
            expected = expected_sheet(sampling)
            errors = [abs(center(rgb,x,y)-(255-expected[y*W+x])) for y in range(H) for x in range(W)]
            self.assertLessEqual(max(errors),3,(sampling,max(errors)))

    @unittest.skipUnless(pymupdf,'PDF raster check requires PyMuPDF')
    def test_mupdf_matches_independent_pixel_centers(self):
        def read(data):
            with pymupdf.open(stream=data,filetype='pdf') as pdf:
                return pdf[0].get_pixmap(dpi=288,alpha=False).samples
        self.compare_reader(read)

    @unittest.skipUnless(shutil.which('pdftoppm'),'PDF raster check requires pdftoppm')
    def test_poppler_matches_independent_pixel_centers(self):
        self.compare_reader(lambda data: poppler_rgb(data,288,4*W,4*H))

    def test_dense_bilinear_grid_keeps_shared_knots_and_reconstructs_fine_detail(self):
        n = 64
        def value(x,y):
            return 255*((x+y)%2) if 0 <= x < n and 0 <= y < n else 0
        gray = bytes(value(x,y) for y in range(n) for x in range(n))
        mask = dict(width=n,height=n,gray_hex=gray.hex(),sampling='bilinear')
        doc = document(n,n,[rectangle('checker',0,0,n,n,[0,0,0,255],mask=mask)])
        doc['resolution_ppi'] = 72
        pdf = Pdf(self.export(doc))
        cells = set()
        for obj in pdf.objects.values():
            if obj.get('ShadingType') != 1:
                continue
            function = pdf.get(obj['Function'])
            w,h = function['Size']
            left,right,top,bottom = [int(v-.5) for v in obj['Domain']]
            self.assertEqual((w,h),(right-left+1,bottom-top+1))
            self.assertEqual(obj['Domain'],function['Domain'])
            self.assertEqual(obj['BBox'], [left+.5,top+.5,right+.5,bottom+.5])
            actual = struct.unpack(f'>{w*h}H',pdf.streams[obj['Function']])
            self.assertEqual(list(actual),[257*value(x,y) for y in range(top,bottom+1) for x in range(left,right+1)])
            region = {(x,y) for y in range(top,bottom) for x in range(left,right)}
            cells.update(region)
        self.assertEqual(cells,{(x,y) for y in range(-1,n) for x in range(-1,n)})
        readers = {}
        if pymupdf:
            with pymupdf.open(stream=pdf.data,filetype='pdf') as source:
                readers['MuPDF'] = source[0].get_pixmap(dpi=288,alpha=False).samples
        if shutil.which('pdftoppm'):
            readers['Poppler'] = poppler_rgb(pdf.data,288,4*n,4*n)
        for name,rgb in readers.items():
            errors = []
            for y in range(n):
                for x in range(n):
                    # Average of the four central subpixels of a bilinear cell.
                    weights = [(-1,1),(0,14),(1,1)]
                    predicted = 255-sum(value(x+i,y+j)*a*b for i,a in weights for j,b in weights)/256
                    seen = sum(rgb[3*((4*y+j)*4*n+4*x+i)] for j in (1,2) for i in (1,2))/4
                    errors.append(abs(seen-predicted))
            self.assertLessEqual(max(errors),32,name)
            self.assertLessEqual(sum(errors)/len(errors),3,name)

    @unittest.skipUnless(shutil.which('pdftoppm'),'PDF patch-join check requires pdftoppm')
    def test_sheared_bilinear_patches_do_not_expose_the_backdrop_at_their_joins(self):
        w,h = 96,80
        matrix = [1.8,.44,-.6,1.6,18,6]
        values = bytes(170+(x//8+y//6)*7 for y in range(27) for x in range(32))
        mask = dict(width=32,height=27,gray_hex=values.hex(),sampling='bilinear',transform=matrix)
        doc = document(w,h,[rectangle('ink',0,0,w,h,[0,0,0,255],mask=mask)])
        doc['resolution_ppi'] = 72
        rgb = poppler_rgb(Pdf(self.export(doc)).data,288,4*w,4*h)
        for y in range(h):
            for x in range(w):
                u,v = inverse(matrix,(x+.5,y+.5))
                if 1<=u<=31 and 1<=v<=26:
                    expected = sum(255*(1-opacity(mask,(x+a,y+b))) for a in (.375,.625) for b in (.375,.625))/4
                    seen = sum(rgb[3*((4*y+j)*4*w+4*x+i)] for i in (1,2) for j in (1,2))/4
                    self.assertLessEqual(abs(expected-seen),3,(x,y))

    @unittest.skipUnless(pymupdf,'PDF composition check requires PyMuPDF')
    def test_mask_applies_once_to_each_group_fill_and_stroke_and_preserves_ink_backdrop(self):
        mask = dict(width=1,height=1,gray_hex='80',transform=[24,0,0,12,0,0])
        ink = rectangle('ink',2,2,20,8,[0,0,0,255],mask=mask,parent='outer')
        ink['content']['stroke'] = dict(width=4,color=[0,0,0,255])
        doc = document(24,12,[dict(id='outer',mask=mask,content=dict(type='group')),ink])
        with pymupdf.open(stream=Pdf(self.export(doc)).data,filetype='pdf') as pdf:
            rgba = pdf[0].get_pixmap(dpi=96,alpha=True)
            for point in [(8,1),(8,3),(8,6)]:
                self.assertLessEqual(abs(rgba.pixel(*point)[3]-64),2)
        # A child multiply inside a masked pass-through group sees the base.
        doc['items'] = [rectangle('base',0,0,24,12,[200,100,50,255]),
                        dict(id='through',mask=mask,content=dict(type='group',isolated=False)),
                        rectangle('child',0,0,24,12,[128,255,0,255],parent='through',blend='multiply')]
        with pymupdf.open(stream=Pdf(self.export(doc)).data,filetype='pdf') as pdf:
            actual = pdf[0].get_pixmap(dpi=96).pixel(8,6)
            self.assertLessEqual(max(abs(a-b) for a,b in zip(actual,[150,100,25])),3)
        ramp = dict(type='linear',start=[0,0],end=[24,0],stops=[
            dict(offset=0,color=[0,0,0,0]),dict(offset=1,color=[0,0,0,255])])
        doc['items'] = [rectangle('fade',0,0,24,12,ramp,mask=mask)]
        result = self.export(doc)
        self.assertEqual((result['pdf']['gradient_opacity_masks'],result['pdf']['grid_masks']),(1,1))
        with pymupdf.open(stream=Pdf(result).data,filetype='pdf') as pdf:
            rgba = pdf[0].get_pixmap(dpi=96,alpha=True)
            for x in range(24):
                self.assertLessEqual(abs(rgba.pixel(x,6)[3]-128*(x+.5)/24),4)
        doc['swatches'] = dict(cyan=cmyk([1,0,0,0]),k=cmyk([0,0,0,1]))
        doc['items'] = [rectangle('base',0,0,24,12,reference('k')),
                        rectangle('color',0,0,24,12,reference('cyan',overprint='preserve_nonzero'),mask=mask)]
        for options in ({},dict(marks=dict(crop=True,registration=False))):
            result = self.export(doc,color='native_inks',**options)
            with pymupdf.open(stream=Pdf(result).data,filetype='pdf') as pdf:
                # An explicit separation device enables overprint simulation.
                api = pymupdf.mupdf
                image = api.fz_new_pixmap_from_page_contents_with_separations(
                    pdf[0].this, api.fz_scale(4/3,4/3), api.fz_device_cmyk(), api.fz_new_separations(0), 0)
                start = image.stride()*(image.h()//2) + 4*(image.w()//2)
                plates = api.fz_pixmap_samples_memoryview(image)[start:start+4]
                self.assertLessEqual(max(abs(a-b) for a,b in zip(plates,[128,0,0,255])),3)

    def test_constant_and_disabled_masks_preserve_marks_and_publication_rules(self):
        doc, _ = sheet('nearest')
        shape = doc['items'][-1]
        for mask,visited in [(dict(width=1,height=1,gray_hex='ff',clip=False),9),
                             (dict(width=0,height=0,gray_hex='',constant=True,clip=False,invert=True),0),
                             (dict(width=1,height=1,gray_hex='10',density=0),0)]:
            shape['mask'] = mask
            result = self.export(doc,marks=dict(crop=True))
            self.assertEqual(result['pdf']['grid_mask_samples'],visited)
            self.assertFalse(any(isinstance(o,dict) and isinstance(o.get('SMask'),dict)
                                 for o in Pdf(result).objects.values()))
        shape['mask'] = dict(width=0,height=0,gray_hex='',constant=True,clip=True,density=.6)
        result = self.export(doc)
        self.assertAlmostEqual(Pdf(result).paths()[0]['alpha'],.4)
        shape['mask']['enabled'] = False
        self.assertNotIn('grid_masks',self.export(doc,marks=dict(crop=True))['pdf'])
        doc, _ = sheet('bilinear')
        with closing(Client(('--tools','essentials'),workspace=self.root)) as client:
            client.initialize()
            output = dict(format='pdf',file_name='mask.pdf')
            def request(command):
                return client.tool('run', command=command, arguments=dict(document=doc,output=output))['structuredContent']
            output['pdf_options'] = dict(marks=dict(crop=True))
            self.assertFalse(request('document.preflight')['result']['ready'])
            self.assertEqual(request('document.publish')['error']['code'],'UNSUPPORTED')
            self.assertFalse((self.root/'mask.pdf').exists())
            del output['pdf_options']
            self.assertTrue(request('document.preflight')['result']['ready'])
            self.assertFalse((self.root/'mask.pdf').exists())
            self.assertEqual(request('document.publish')['result']['pdf']['grid_mask_samples'],42)
            self.assertEqual((self.root/'mask.pdf').read_bytes(),Pdf(self.export(doc)).data)
            self.assertEqual(request('document.publish')['error']['code'],'OUTPUT_EXISTS')

    def test_stored_tiles_match_inline_and_corrupt_disabled_blocks_refuse_publication(self):
        doc, _ = sheet('bilinear')
        mask,inline = self.mask(133,132,feather=1,density=.8,invert=True,sampling='bilinear')
        doc['items'][-1]['mask'] = inline
        expected = self.export(doc)
        doc['items'][-1]['mask'] = mask
        self.assertEqual(self.export(doc),expected)
        path = self.root/'.inkbolt/assets'/(mask['native']['base']['tiles'][-1]+'.native-tile')
        data = path.read_bytes()
        path.write_bytes(data[:-1]+bytes([data[-1]^1]))
        doc['items'][-1]['visible'] = mask['enabled'] = False
        self.cli('document.publish',document=doc,output=dict(file_name='bad.pdf',format='pdf'),
                 error='SAMPLE_TILE_CORRUPT')
        self.assertFalse((self.root/'bad.pdf').exists())

    def test_preflight_counts_padded_grid_before_opening_native_blocks(self):
        # Exactly 2048 squared source bytes fill the PDF budget even before padding.
        manifest, _ = native.scalar(2048,2048,lambda x,y: 0)
        doc,_ = sheet('nearest')
        doc['items'][-1]['mask'] = dict(width=2048,height=2048,gray_hex='',native=dict(base=manifest))
        error = self.cli('document.publish',document=doc,output=dict(file_name='big.pdf',format='pdf'),
                         error='RESOURCE_LIMIT')
        self.assertEqual(error['item_id'],'ink')
        self.assertFalse((self.root/'big.pdf').exists())

    def test_selected_pages_rebase_unlinked_grids_and_account_for_their_own_bleed(self):
        def board(key,x):
            return dict(id=key,transform=[1,0,0,1,x,5],content=dict(type='frame',
                        frame=dict(role='artboard',width=20,height=16,bleed=dict(left=3,top=2))))
        base = dict(width=2,height=1,gray_hex='50ff',sampling='bilinear',
                    linked=False,transform=[6,0,0,4,14,8])
        doc = document(70,30,[board('a',6),board('b',36),
                            rectangle('paint-a',0,0,20,16,[0,0,0,255],parent='a',mask=base),
                            rectangle('paint-b',0,0,20,16,[0,0,0,255],parent='b',mask=base)])
        out = self.export(doc,artboards=dict(type='ids',ids=['b','a']),include_bleed=True)
        pdf = Pdf(out)
        self.assertEqual([p['artboard_id'] for p in out['pages']],['b','a'])
        self.assertEqual((out['pdf']['grid_masks'],out['pdf']['grid_mask_samples']),(2,24))
        refs = [o['SMask']['G'] for o in pdf.objects.values() if isinstance(o.get('SMask'),dict)]
        self.assertEqual([pdf.get(ref)['BBox'] for ref in refs],[[0,0,23,18]]*2)
        for ref, x in zip(refs,[-19,11]):
            self.assertIn(f'6 0 0 4 {x} 5 cm'.encode(),pdf.streams[ref])
