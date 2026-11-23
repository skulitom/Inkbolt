"""Reopen embedded image data, row prediction, alpha and independent placements."""
import base64
from contextlib import closing
import hashlib
import struct
import unittest

import test_pdf_import as pages
from test_mcp import Client


def image(width, height, samples, *, space='DeviceRGB', depth=8, extra=b'', compressed=False):
    fields = (f'/Type /XObject /Subtype /Image /Width {width} /Height {height} '
              f'/ColorSpace /{space} /BitsPerComponent {depth} ').encode()
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
                       image(1,1,b'\0'*3,extra=b'/Mask [0 0 0 0 0 0]'),
                       image(1,1,b'\0'*3,extra=b'/Decode [0 0.5 0 1 0 1]'),
                       image(1,1,b'\7\0\0\0',compressed=True,extra=b'/DecodeParms << /Predictor 15 /Colors 3 >>'),
                       image(32768,32768,b'')]:
            with self.subTest(bitmap=bitmap):
                error=self.read(document(bitmap),1)
                self.assertEqual(error['details']['object'],5)
        for mask in [image(1,2,b'\0\0',space='DeviceGray'),image(1,1,b'\0'*3),
                     image(1,1,b'\0',space='DeviceGray',extra=b'/Matte [1 1 1]'),
                     image(1,1,b'\0',space='DeviceGray',extra=b'/SMask 6 0 R')]:
            error=self.read(document(image(1,1,b'\0'*3,extra=b'/SMask 6 0 R'),mask=mask),1)
            self.assertEqual(error['details']['object'],6)

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
