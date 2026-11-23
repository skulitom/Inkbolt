"""Reopen embedded image data, row prediction, alpha and independent placements."""
import base64
from contextlib import closing
import hashlib
import struct
import unittest

import test_pdf_import as pages
import synthetic_jpeg as jpeg
from test_mcp import Client


def image(width, height, samples, *, space='DeviceRGB', depth=8, extra=b'', compressed=False):
    color_space = space if isinstance(space, bytes) else b'/' + space.encode()
    fields = (f'/Type /XObject /Subtype /Image /Width {width} /Height {height} '
              f'/BitsPerComponent {depth} /ColorSpace ').encode() + color_space + b' '
    return pages.stream(samples, fields + extra, compressed)


def document(bitmap, program=b'q 6 0 0 4 2 3 cm /Picture Do Q', mask=None):
    objects = pages.page_objects(program, resources=b'<< /XObject << /Picture 5 0 R >> >>')
    objects[5] = bitmap
    if mask is not None:
        objects[6] = mask
    return pages.pdf(objects)


def identity(width, height, rgba):
    return hashlib.sha256(b'INKRGBA1' + struct.pack('<II', width, height) + rgba).hexdigest()


class PdfImageImport(unittest.TestCase):
    setUp = pages.EditablePdfPage.setUp
    invoke = pages.EditablePdfPage.invoke
    read = pages.EditablePdfPage.read
    edit = pages.EditablePdfPage.edit
    rgba = pages.EditablePdfPage.rgba

    def test_masked_rgb_two_placements_independent_edit_and_pdf_reopen(self):
        rgb = bytes([255,0,0, 0,255,0, 0,0,255, 11,22,33, 60,80,100, 250,250,0])
        alpha = bytes([255,128,64,0,200,255])
        rgba = b''.join(rgb[i*3:i*3+3] + alpha[i:i+1] for i in range(6))
        bitmap = image(3,2,rgb,extra=b'/SMask 6 0 R',compressed=True)
        data = document(bitmap,b'q 6 0 0 4 2 3 cm /Picture Do Q q 0 3 -2 0 20 10 cm /Picture Do Q',
                        image(3,2,alpha,space='DeviceGray'))
        result = self.read(data)
        doc = result['document']
        a,b = doc['items']
        key = a['content']['asset_id']
        self.assertEqual(b['content']['asset_id'],key)
        self.assertEqual(list(doc['assets']),[key])
        self.assertEqual(doc['assets'][key]['sha256'],identity(3,2,rgba))
        self.assertEqual(result['image_sources'][key]['soft_mask'],{'object':6,'generation':0})
        self.assertEqual([row['object'] for row in result['mapping']],[4,4])
        self.assertEqual(a['transform'],[2,0,0,2,2,33])
        self.assertEqual(b['transform'],[0,-1,1,0,18,30])
        pixels = self.rgba(doc)
        def pixel(x,y):
            return pixels[(y*48+x)*4:(y*48+x+1)*4]
        self.assertEqual(pixel(2,33),rgba[:4])
        self.assertEqual(pixel(4,33),rgba[4:8])
        self.assertEqual(pixel(3,36),bytes(4))
        self.assertEqual(pixel(6,36),rgba[-4:])
        moved = self.edit(doc,[dict(op='transform',id=b['id'],matrix=[1,0,0,1,30,10])])
        self.assertEqual(doc['assets'],moved['assets'])
        self.assertEqual(a,moved['items'][0])
        self.assertNotEqual(pixels,self.rgba(moved))
        delivered = base64.b64decode(self.invoke(dict(command='document.export',format='pdf',document=moved))['data'])
        reopened = self.read(delivered)['document']
        self.assertEqual(self.rgba(reopened),self.rgba(moved))
        self.assertEqual({a['sha256'] for a in reopened['assets'].values()},{identity(3,2,rgba)})

    def test_image_blend_and_ordinary_form_inheritance(self):
        objects = pages.page_objects(b'1 0 0 rg 0 0 48 40 re f /Diff gs /F Do',
            resources=b'<< /XObject << /F 5 0 R /P 6 0 R >> /ExtGState << /Diff << /BM /Difference >> /Reset << /BM /Compatible >> >> >>')
        objects[5] = pages.stream(b'q 5 0 0 5 0 0 cm /P Do Q /Reset gs 0 0 1 rg 5 0 5 5 re f',
            b'/Subtype /Form /BBox [0 0 10 5]')
        objects[6] = image(1, 1, bytes([0,0,255]))
        doc = self.read(pages.pdf(objects))['document']
        image_item, = [i for i in doc['items'] if i['content']['type'] == 'image']
        self.assertEqual(image_item['blend'], 'difference')
        pixels = self.rgba(doc)
        for x, rgb in [(2, [255,0,255]), (7, [0,0,255]), (12, [255,0,0])]:
            offset = 4 * (48*37+x)
            self.assertEqual(pixels[offset:offset+4], bytes([*rgb,255]))

    def test_indexed_packed_codes_decode_and_color_key_keep_hidden_rgb(self):
        colors = [(195,17,32), (48,170,69), (21,57,221)]
        for decode, indices in [(b'', [0,1,2,2]), (b'/Decode [3 0]', [2,2,1,0]),
                                (b'/Decode [0 2]', [0,1,1,2]), (b'/Decode [-1.5 2.25]', [0,0,1,2]),
                                (b'/Decode [-9007199254740992 18014398509481986]', [0,1,2,2])]:
            with self.subTest(decode=decode):
                program = b'q 4 0 0 2 0 0 cm /Picture Do Q q 4 0 0 2 5 0 cm /Picture Do Q'
                objects = pages.page_objects(program, resources=b'<< /XObject << /Picture 5 0 R >> >>')
                objects[5] = image(4,2,bytes([0x1b, 0xe4]),space=b'6 0 R',depth=2,
                                   extra=decode+b' /Mask 8 0 R',compressed=True)
                objects[6] = b'[/Indexed /DeviceRGB 2 7 0 R]'
                objects[7] = pages.stream(bytes(v for rgb in colors for v in rgb),compress=True)
                objects[8] = b'[1 2]'
                result = self.read(pages.pdf(objects))
                doc = result['document']
                key, = doc['assets']
                self.assertEqual([item['content']['asset_id'] for item in doc['items']], [key,key])
                self.assertEqual(result['image_sources'][key]['palette_entries'],3)
                self.assertEqual(result['image_sources'][key]['color_key'],[[1,2]])
                rgba = bytes(v for code in [0,1,2,3,3,2,1,0]
                             for v in (*colors[indices[code]],0 if code in (1,2) else 255))
                self.assertEqual(doc['assets'][key]['sha256'],identity(4,2,rgba))
                moved = self.edit(doc,[dict(op='transform',id=doc['items'][1]['id'],matrix=[1,0,0,1,8,5])])
                exported = self.invoke(dict(command='document.export',format='pdf',document=moved))
                reopened = self.read(base64.b64decode(exported['data']))['document']
                self.assertEqual(self.rgba(reopened), self.rgba(moved))
                self.assertEqual(next(iter(reopened['assets'].values()))['sha256'],identity(4,2,rgba))

    def test_gray_palette_index_255_and_soft_mask_override(self):
        palette = bytes(reversed(range(256))).hex().encode()
        bitmap = image(3,1,bytes([0,1,255]),space=b'[/Indexed /DeviceGray 255 <'+palette+b'>]',
                       extra=b'/Mask [0 255] /SMask 6 0 R')
        source = document(bitmap,mask=image(3,1,bytes([0,128,255]),space='DeviceGray'))
        result = self.read(source)
        key, = result['document']['assets']
        self.assertNotIn('color_key',result['image_sources'][key])
        self.assertTrue(result['image_sources'][key]['mask_overridden_by_soft_mask'])
        self.assertEqual(result['image_sources'][key]['palette_entries'],256)
        rgba = bytes([255,255,255,0, 254,254,254,128, 0,0,0,255])
        self.assertEqual(result['document']['assets'][key]['sha256'],identity(3,1,rgba))

    def test_ascii_hex_images_and_exact_length_termination(self):
        space = b'[/Indexed /DeviceGray 2 <0a809f>]'
        for payload, end in [(b' 0\n0\r\n0\t1\x0c0\x002 > ', 'marker'), (b'000102', 'stream_length')]:
            result = self.read(document(image(3,1,payload,space=space,extra=b'/Filter [/ASCIIHexDecode] /DecodeParms [null] /SMask 6 0 R'),
                                        mask=image(3,1,b'ff800>',space='DeviceGray',extra=b'/Filter /ASCIIHexDecode')))
            key, = result['document']['assets']
            src = result['image_sources'][key]
            self.assertEqual((src['filter'],src['ascii_hex_end']),('ASCIIHexDecode',end))
            self.assertEqual(src['soft_mask']['ascii_hex_end'],'marker')
            self.assertEqual(result['document']['assets'][key]['sha256'],
                             identity(3,1,bytes([10,10,10,255,128,128,128,128,159,159,159,0])))
        for payload in [b'00010', b'00010Z', b'0001020>', b'000102>FF', b'00>', b'00 01 02>>']:
            error = self.read(document(image(3,1,payload,space=space,extra=b'/Filter /ASCIIHexDecode')),1)
            self.assertEqual(error['details']['object'],5)

    def test_nonstandard_generation_only_applies_to_unused_free_list_head(self):
        data = document(image(1,1,b'123456>',extra=b'/Filter /ASCIIHexDecode'))
        free = b'0000000000 65535 f'
        self.assertNotIn('free_head_generation', self.read(data)['source'])
        row = self.read(data.replace(free,b'0000000000 65536 f'))
        self.assertEqual(row['source']['free_head_generation'],65536)
        self.assertEqual(next(iter(row['document']['assets'].values()))['sha256'],
                         identity(1,1,bytes.fromhex('123456ff')))
        for replacement in [b'0000000000 65536 n',b'0000000001 65536 f',b'0000000000 65537 f']:
            self.assertIn('generation', self.read(data.replace(free,replacement),1)['message'])
        self.assertIn('generation', self.read(data.replace(b' 00000 n ',b' 65536 n ',1),1)['message'])

    def test_device_color_key_checks_all_encoded_channels_before_decode(self):
        bitmap = image(3,1,bytes([25,51,75, 25,52,75, 24,51,75]),
                       extra=b'/Mask [25 30 49 51 70 80] /Decode [1 0 0 1 1 0]')
        result = self.read(document(bitmap))
        asset, = result['document']['assets'].values()
        rgba = bytes([230,51,180,0, 230,52,180,255, 231,51,180,255])
        self.assertEqual(asset['sha256'],identity(3,1,rgba))

    def test_packed_samples_reset_padding_each_row_and_apply_tiff_prediction(self):
        for bits in (1,2,4,8):
            for components in (1,3):
                with self.subTest(bits=bits,components=components):
                    maximum = (1 << bits)-1
                    rows = [[(i+3*y+i//3)% (maximum+1) for i in range(5*components)] for y in range(3)]
                    packed = bytearray()
                    expected = bytearray()
                    for row in rows:
                        deltas = [(v-(row[i-components] if i>=components else 0)) & maximum for i,v in enumerate(row)]
                        codes = ''.join(format(v,f'0{bits}b') for v in deltas)
                        codes += '1'*(-len(codes)%8)
                        packed.extend(int(codes[i:i+8],2) for i in range(0,len(codes),8))
                        for i in range(0,len(row),components):
                            color = [int(v*255/maximum) for v in row[i:i+components]]
                            color[0] = 255-color[0]
                            expected.extend((color*3 if components==1 else color)+[255])
                    params = (f'/DecodeParms << /Predictor 2 /Columns 5 /Colors {components} /BitsPerComponent {bits} >> '
                              f'/Decode [1 0 {"0 1 "*(components-1)}]').encode()
                    src = image(5,3,packed,space='DeviceGray' if components==1 else 'DeviceRGB',
                                depth=bits,extra=params,compressed=True)
                    asset = next(iter(self.read(document(src))['document']['assets'].values()))
                    self.assertEqual(asset['sha256'],identity(5,3,expected))

    def test_each_png_filter_and_reused_large_encoded_asset_over_mcp(self):
        width,height=513,137
        rows=[bytes((x*23+y*47+(x//3)%17)%256 for x in range(width*3)) for y in range(height)]
        filtered=bytearray()
        rgba=bytearray()
        for y,row in enumerate(rows):
            tag=y%5
            filtered.append(tag)
            for x,v in enumerate(row):
                a=row[x-3] if x>=3 else 0
                b=rows[y-1][x] if y else 0
                c=rows[y-1][x-3] if y and x>=3 else 0
                p=a+b-c
                nearest=min((a,b,c),key=lambda v:abs(p-v))
                filtered.append((v-(0,a,b,(a+b)//2,nearest)[tag])%256)
                rgba.append(v)
                if x%3==2:
                    rgba.append(255)
        params=f'/DecodeParms << /Predictor 15 /Colors 3 /BitsPerComponent 8 /Columns {width} >>'.encode()
        bitmap=image(width,height,filtered,compressed=True,extra=params)
        source=document(bitmap,b'q 40 0 0 30 0 0 cm /Picture Do Q /Picture Do')
        result=self.read(source)
        asset=next(iter(result['document']['assets'].values()))
        self.assertEqual(asset['sha256'],identity(width,height,rgba))
        with closing(Client(('--tools','essentials'),workspace=self.source.parent)) as client:
            client.initialize()
            response=client.tool('run',command='pdf.import',arguments=dict(
                id='reopened',source_path=self.source.name,color_policy='encoded_srgb'))
            self.assertFalse(response['isError'],response)
            self.assertEqual(response['structuredContent']['result'],result)

    def test_invalid_samples_and_unhandled_paint_semantics_are_located(self):
        for bitmap in [image(3,2,b'\0'*17), image(3,2,b'\0'*19,compressed=True),
                       image(1,1,b'\0',space='DeviceCMYK'),image(1,1,b'\0'*6,depth=16),
                       image(1,1,b'\0'*3,extra=b'/Interpolate true'),
                       image(1,1,b'\0'*3,extra=b'/Mask [1 0 0 0 0 0]'),
                       image(1,1,b'\0'*3,extra=b'/Mask [0 1]'),
                       image(1,1,b'\0',depth=2,space='DeviceGray',extra=b'/Mask [0 4]'),
                       image(1,1,b'\0',space=b'[/Indexed /DeviceRGB 2 <000000>]'),
                       image(1,1,b'\0'*3,extra=b'/Decode [0 0.5 0 1 0 1]'),
                       image(1,1,b'\7\0\0\0',compressed=True,extra=b'/DecodeParms << /Predictor 15 /Colors 3 >>'),
                       image(32768,32768,b'')]:
            with self.subTest(bitmap=bitmap):
                error=self.read(document(bitmap),1)
                self.assertEqual(error['details']['object'],5)
        for mask in [image(1,2,b'\0\0',space='DeviceGray'),image(1,1,b'\0'*3),
                     image(1,1,b'\0',space=b'[/Indexed /DeviceGray 0 <ff>]'),
                     image(1,1,b'\0',space='DeviceGray',extra=b'/Mask [0 0]'),
                     image(1,1,b'\0',space='DeviceGray',extra=b'/Matte [1 1 1]'),
                     image(1,1,b'\0',space='DeviceGray',extra=b'/SMask 6 0 R')]:
            error=self.read(document(image(1,1,b'\0'*3,extra=b'/SMask 6 0 R'),mask=mask),1)
            self.assertEqual(error['details']['object'],6)

    def test_jpeg_direct_rgb_with_grayscale_jpeg_mask_and_pdf_placement(self):
        width, height = 17, 9
        for progressive in (False, True):
            with self.subTest(progressive=progressive):
                color = jpeg.jpeg(width, height, progressive=progressive, extras=jpeg.exif(6))
                alpha = jpeg.jpeg(width, height, channels=1, progressive=progressive, restart=2)
                bitmap = image(width, height, color, extra=b'/Filter [/DCTDecode] /DecodeParms [<< /ColorTransform 0 >>] /SMask 6 0 R')
                mask = image(width, height, alpha, space='DeviceGray', extra=b'/Filter /DCTDecode /Decode [1 0]')
                result = self.read(document(bitmap, b'q 17 0 0 9 0 0 cm /Picture Do Q /Picture Do', mask))
                doc = result['document']
                key, = doc['assets']
                expected = bytearray()
                for y in range(height):
                    for x in range(width):
                        rgb = [jpeg.value(x, y, c) for c in range(3)]
                        expected.extend([*rgb, 255 - rgb[0]])
                self.assertEqual(doc['assets'][key]['sha256'], identity(width, height, expected))
                self.assertEqual([i['content']['asset_id'] for i in doc['items']], [key, key])
                self.assertEqual(result['image_sources'][key]['jpeg_components'], 'direct_rgb')
                self.assertEqual(result['image_sources'][key]['soft_mask']['object'], 6)
                delivered = self.invoke(dict(command='document.export', format='pdf', document=doc))
                reopened = self.read(base64.b64decode(delivered['data']))['document']
                self.assertEqual(self.rgba(reopened), self.rgba(doc))

    def test_jpeg_dictionary_selects_color_transform_and_inverts_decoded_channels(self):
        formats = self.invoke(dict(command='capabilities'))['pdf']['editable_import']['images']
        self.assertIn('DCTDecode', formats['filters'])
        self.assertEqual(formats['jpeg']['color_transform'], [0, 1])
        self.assertTrue(formats['jpeg']['app14'])
        self.assertEqual(formats['jpeg']['transform_precedence'], ['APP14', 'ColorTransform', 'PDF_default'])
        width, height = 17, 9
        encoded = jpeg.jpeg(width, height, subsampling=(2, 2))
        for params, converted in [(b'', True), (b'/DecodeParms << /ColorTransform 1 >>', True),
                                  (b'/DecodeParms << /ColorTransform 0 >>', False)]:
            with self.subTest(params=params):
                bitmap = image(width, height, encoded, extra=b'/Filter /DCTDecode /Decode [1 0 0 1 0 1] '+params)
                result = self.read(document(bitmap))
                key, = result['document']['assets']
                expected = bytearray()
                for y in range(height):
                    for x in range(width):
                        luma = jpeg.value(x, y, 0)
                        expected.extend([255 - luma, luma if converted else 128, luma if converted else 128, 255])
                self.assertEqual(result['document']['assets'][key]['sha256'], identity(width, height, expected))
                self.assertEqual(result['image_sources'][key]['filter'], 'DCTDecode')

        # Non-neutral chroma distinguishes the two color-difference components.
        chroma = jpeg.jpeg(8, 8, sample=lambda x, y, c: (128, 16, 240)[c])
        result = self.read(document(image(8, 8, chroma, extra=b'/Filter /DCTDecode /DecodeParms << /ColorTransform 1 >>')))
        sample = self.rgba(result['document'])[(33*48+2)*4:(33*48+3)*4]
        self.assertEqual((sample[0], sample[2], sample[3]), (255, 0, 255))
        self.assertLessEqual(abs(sample[1]-87), 1)

    def test_embedded_jpeg_transform_precedes_pdf_dictionary_and_reports_each_plane(self):
        gray = jpeg.jpeg(8, 8, channels=1, extras=jpeg.app14(0), sample=lambda x,y,c: 192)
        alpha = image(8, 8, gray, space='DeviceGray', extra=b'/Filter /DCTDecode /Decode [1 0]')
        for progressive in (False, True):
            for marker, rgb, interpretation in [(0, (80,128,128), 'direct_rgb'),
                                                 (1, (80,80,80), 'ycbcr_to_rgb')]:
                with self.subTest(progressive=progressive, marker=marker):
                    jfif = jpeg.segment(0xe0, b'JFIF\0\1\2\0\0\1\0\1\0\0')
                    encoded = jpeg.jpeg(8, 8, progressive=progressive,
                                        extras=jfif + jpeg.app14(marker, version=101, advisory=0x8000),
                                        sample=lambda x,y,c: (80,128,128)[c])
                    for params in (b'', f'/DecodeParms << /ColorTransform {1-marker} >>'.encode()):
                        bitmap = image(8, 8, encoded, extra=b'/Filter /DCTDecode /SMask 6 0 R '+params)
                        result = self.read(document(bitmap, mask=alpha))
                        key, = result['document']['assets']
                        expected = bytes([*rgb,63])*64
                        self.assertEqual(result['document']['assets'][key]['sha256'], identity(8, 8, expected))
                        source = result['image_sources'][key]
                        self.assertEqual(source['jpeg_components'], interpretation)
                        self.assertEqual(source['app14_color_transform'], marker)
                        self.assertEqual(source['soft_mask']['jpeg_components'], 'gray')
                        self.assertEqual(source['soft_mask']['app14_color_transform'], 0)

    def test_jpeg_dimensions_components_depth_and_coding_are_checked_at_the_source_object(self):
        color = jpeg.jpeg(8, 4)
        gray = jpeg.jpeg(8, 4, channels=1)
        for width, height, encoded, attrs, depth in [
            (4, 8, color, b'', 8), (8, 4, gray, b'', 8), (8, 4, color, b'', 4),
            (8, 4, color, b'/DecodeParms << /ColorTransform 2 >>', 8),
            (8, 4, color, b'/DecodeParms << /Predictor 15 >>', 8),
            (8, 4, color[:-2], b'', 8), (8, 4, color + b'extra', b'', 8),
            (8, 4, jpeg.jpeg(8, 4, extras=jpeg.segment(0xee, bytes(12))), b'', 8),
        ]:
            with self.subTest(width=width, attrs=attrs, depth=depth):
                bitmap = image(width, height, encoded, depth=depth, extra=b'/Filter /DCTDecode '+attrs)
                self.assertEqual(self.read(document(bitmap), 1)['details']['object'], 5)

    def test_array_filter_in_clipped_form_keeps_image_and_invocation_alpha_separate(self):
        objects = pages.page_objects(
            b'0 0 1 rg 0 0 48 40 re f q /Half gs 1 0 0 1 5 6 cm /Frame Do Q',
            resources=b'<< /XObject << /Frame 5 0 R >> /ExtGState << /Half 8 0 R >> >>')
        objects[5] = pages.stream(b'8 0 0 4 0 0 cm /P Do',
            b'/Type /XObject /Subtype /Form /BBox [2 0 8 4] /Resources << /XObject << /P 6 0 R >> >>')
        objects[6] = image(1,1,b'\0\xff\0\0',compressed=True,
            extra=b'/SMask 7 0 R /DecodeParms [<< /Predictor 15 /Colors 3 >>]'
        ).replace(b'/Filter /FlateDecode',b'/Filter [/FlateDecode]')
        objects[7] = image(1,1,b'\x55',space='DeviceGray',extra=b'/Decode [1 0]')
        objects[8] = b'<< /ca .5 >>'
        result = self.read(pages.pdf(objects))
        doc = result['document']
        item = next(i for i in doc['items'] if i['content']['type']=='image')
        self.assertEqual(item['opacity'],.5)
        asset = doc['assets'][item['content']['asset_id']]
        self.assertEqual(asset['sha256'],identity(1,1,bytes([255,0,0,170])))
        pixels = self.rgba(doc)
        for x,expected in [(5,(0,0,255,255)),(7,(85,0,170,255)),(13,(0,0,255,255))]:
            self.assertEqual(tuple(pixels[(31*48+x)*4:(31*48+x+1)*4]),expected)
