"""Original PNG fixtures, independent asset identities and filesystem failure checks."""
import base64
import binascii
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zlib
import test_editing_cli as editing
from test_editing_cli import png_pixels
from test_layout_cli import NS


def chunk(kind, data):
    return struct.pack('>I',len(data))+kind+data+struct.pack('>I',binascii.crc32(kind+data))


def png(width,height,pixels,tagged=True,extra=(),depth=8,color=6,interlace=False,raw=None):
    if raw is None:
        if interlace:
            rows=[]
            for x0,y0,dx,dy in [(0,0,8,8),(4,0,8,8),(0,4,4,8),(2,0,4,4),(0,2,2,4),(1,0,2,2),(0,1,1,2)]:
                if x0>=width or y0>=height:
                    continue
                for y in range(y0,height,dy):
                    rows.append(b'\0'+b''.join(pixels[(y*width+x)*4:(y*width+x+1)*4] for x in range(x0,width,dx)))
            raw=b''.join(rows)
        else:
            raw=b''.join(b'\0'+pixels[y*width*4:(y+1)*width*4] for y in range(height))
    parts=[chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,depth,color,0,0,int(interlace)))]
    if tagged:
        parts.append(chunk(b'sRGB',b'\0'))
    parts += [chunk(kind,data) for kind,data in extra]
    parts += [chunk(b'IDAT',zlib.compress(raw)),chunk(b'IEND',b'')]
    return b'\x89PNG\r\n\x1a\n'+b''.join(parts)


def canonical(width,height,pixels):
    return b'INKRGBA1'+struct.pack('<II',width,height)+pixels


class ImageCliTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke

    def imported(self,directory,pixels,width=3,height=2,**options):
        root=Path(directory)
        source=root/'original.png'
        source.write_bytes(png(width,height,pixels,**options))
        store=root/'assets'
        result=self.invoke(dict(command='asset.import',source_path=str(source),store_root=str(store)))
        return source,store,result

    def placed(self,asset,kind='vector',width=None,height=None):
        width=asset['width'] if width is None else width
        height=asset['height'] if height is None else height
        d=self.invoke(dict(command='document.create',id='placed-original',kind=kind,width=width,height=height))
        operations=[dict(op='asset_put',id='source',asset=asset),dict(op='add',item=dict(id='image',content=dict(type='image',asset_id='source',width=width,height=height)))]
        return self.invoke(dict(command='document.edit',document=d,expected_revision=0,operations=operations))['document']

    def test_content_addressed_checkerboard_stored_embedded_identity_and_source_preservation(self):
        white=bytes([245,245,245,255]);black=bytes([15,20,25,255])
        pixels=white+black+white+black+white+black
        with tempfile.TemporaryDirectory() as directory:
            source,store,result=self.imported(directory,pixels)
            original=source.read_bytes();asset=result['asset'];digest=hashlib.sha256(canonical(3,2,pixels)).hexdigest()
            self.assertTrue(result['created'])
            self.assertEqual(asset['sha256'],digest)
            self.assertEqual(asset['provenance']['source_sha256'],hashlib.sha256(original).hexdigest())
            self.assertEqual((store/(digest+'.rgba8')).read_bytes(),canonical(3,2,pixels))
            duplicate=self.invoke(dict(command='asset.import',source_path=str(source),store_root=str(store)))
            self.assertFalse(duplicate['created']);self.assertEqual(duplicate['asset'],asset)
            embedded=self.invoke(dict(command='asset.embed',asset=asset,asset_root=str(store)))
            self.assertEqual(embedded['sha256'],digest)
            self.assertEqual(bytes.fromhex(embedded['storage']['rgba_hex']),pixels)
            for kind in ('vector','raster'):
                stored_doc=self.placed(asset,kind)
                embedded_doc=self.placed(embedded,kind)
                stored_preview=self.invoke(dict(command='document.render',document=stored_doc,asset_root=str(store)))
                embedded_preview=self.invoke(dict(command='document.render',document=embedded_doc))
                self.assertEqual(stored_preview,embedded_preview)
                self.assertEqual(bytes.fromhex(stored_preview['data']),pixels)
                inspection=self.invoke(dict(command='document.inspect',document=stored_doc))
                self.assertEqual(inspection['items'][0]['geometry_bounds'],[0,0,3,2])
                self.assertEqual(inspection['assets'][0]['sha256'],digest)
                self.assertEqual(inspection['assets'][0]['used_by'],['image'])
                self.assertNotIn(directory,json.dumps(stored_doc))
                self.assertEqual(json.loads(self.invoke(dict(command='document.export',document=stored_doc,format='snapshot'))['data']),stored_doc)
            self.assertEqual(source.read_bytes(),original)
            self.assertEqual([p.name for p in store.iterdir()],[digest+'.rgba8'])

    def test_missing_corrupt_assets_are_named_and_never_replaced(self):
        pixels=bytes([255,0,0,255,0,255,0,128,0,0,255,0])*2
        with tempfile.TemporaryDirectory() as directory:
            source,store,result=self.imported(directory,pixels)
            original=source.read_bytes();asset=result['asset'];d=self.placed(asset)
            embedded=self.invoke(dict(command='asset.embed',asset=asset,asset_root=str(store)))
            error=self.invoke(dict(command='document.render',document=d),1)
            self.assertEqual((error['code'],error['asset_id']),('ASSET_ROOT_REQUIRED','source'))
            error=self.invoke(dict(command='document.render',document=d,asset_root=str(Path(directory)/'absent')),1)
            self.assertEqual((error['code'],error['asset_id']),('ASSET_MISSING','source'))
            stored=store/(asset['sha256']+'.rgba8');corrupted=bytearray(stored.read_bytes());corrupted[-1]^=1;stored.write_bytes(corrupted)
            error=self.invoke(dict(command='document.render',document=d,asset_root=str(store)),1)
            self.assertEqual((error['code'],error['asset_id']),('ASSET_CORRUPT','source'))
            error=self.invoke(dict(command='asset.import',source_path=str(source),store_root=str(store)),1)
            self.assertEqual(error['code'],'ASSET_CORRUPT')
            self.assertEqual(stored.read_bytes(),corrupted)
            self.assertEqual(source.read_bytes(),original)
            self.invoke(dict(command='document.render',document=self.placed(embedded)))
            corrupted_descriptor=copy.deepcopy(embedded);corrupted_descriptor['storage']['rgba_hex']='00'+embedded['storage']['rgba_hex'][2:]
            self.assertEqual(self.invoke(dict(command='asset.verify',asset=corrupted_descriptor),1)['code'],'ASSET_CORRUPT')

    def test_external_source_update_requires_explicit_relink_and_preserves_old_snapshot(self):
        before=bytes([255,0,0,255])*6;after=bytes([0,80,255,128])*6
        with tempfile.TemporaryDirectory() as directory:
            source,store,result=self.imported(directory,before)
            old=self.placed(result['asset']);old_snapshot=copy.deepcopy(old)
            # Simulate an external editor updating this owned temporary source.
            source.write_bytes(png(3,2,after));updated_source=source.read_bytes()
            newer=self.invoke(dict(command='asset.import',source_path=str(source),store_root=str(store)))['asset']
            self.assertNotEqual(newer['sha256'],result['asset']['sha256'])
            self.assertEqual(bytes.fromhex(self.invoke(dict(command='document.render',document=old,asset_root=str(store)))['data']),before)
            changed=self.invoke(dict(command='document.edit',document=old,expected_revision=1,operations=[dict(op='asset_put',id='source',asset=newer)]))['document']
            self.assertEqual(bytes.fromhex(self.invoke(dict(command='document.render',document=changed,asset_root=str(store)))['data']),after)
            self.assertEqual(old,old_snapshot)
            self.assertEqual(source.read_bytes(),updated_source)
            self.assertEqual(len(list(store.glob('*.rgba8'))),2)

    def test_crop_transform_alpha_and_svg_embedded_pixels_are_original(self):
        pixels=bytes([255,0,0,255,0,255,0,128,0,0,255,0,200,100,40,255,40,100,200,255,100,200,40,255])
        with tempfile.TemporaryDirectory() as directory:
            source,store,result=self.imported(directory,pixels)
            d=self.placed(result['asset'],width=4,height=4)
            crop=dict(x=1,y=0,width=2,height=2)
            ops=[dict(op='image',id='image',asset_id='source',width=2,height=2,crop=crop),dict(op='transform',id='image',matrix=[0,1,-1,0,3,1])]
            d=self.invoke(dict(command='document.edit',document=d,expected_revision=1,operations=ops))['document']
            preview=self.invoke(dict(command='document.render',document=d,asset_root=str(store)))
            expected=bytearray(4*4*4)
            for x,y,c in [(1,1,[40,100,200,255]),(2,1,[0,255,0,128]),(1,2,[100,200,40,255]),(2,2,[0,0,0,0])]:
                expected[(y*4+x)*4:(y*4+x+1)*4]=bytes(c)
            self.assertEqual(bytes.fromhex(preview['data']),expected)
            exported=self.invoke(dict(command='document.export',document=d,asset_root=str(store),format='svg'))
            root=ET.fromstring(exported['data']);image=root.find(NS+'g/'+NS+'image')
            self.assertEqual((image.get('width'),image.get('height')),('2','2'))
            self.assertEqual(root.find(NS+'g').get('transform'),'matrix(0 1 -1 0 3 1)')
            payload=base64.b64decode(image.get('href').split(',',1)[1]);width,height,cropped,_=png_pixels(payload)
            self.assertEqual((width,height),(2,2))
            self.assertEqual(cropped,pixels[4:12]+pixels[16:24])
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),result['asset']['provenance']['source_sha256'])
            self.assertTrue(any('asset identities' in loss for loss in exported['losses']))

    def test_large_and_interlaced_pngs_keep_pixels_outside_the_snapshot(self):
        for width,height,interlace in [(512,256,False),(9,7,True)]:
            pixels=bytes(c for y in range(height) for x in range(width) for c in (x%256,y%256,(x+y)%256,255))
            with tempfile.TemporaryDirectory() as directory:
                source,store,result=self.imported(directory,pixels,width,height,interlace=interlace)
                d=self.placed(result['asset'])
                self.assertLess(len(json.dumps(d)),2000)
                p=self.invoke(dict(command='document.render',document=d,asset_root=str(store)))
                self.assertEqual(bytes.fromhex(p['data']),pixels)
                if width*height>65536:
                    self.assertEqual(self.invoke(dict(command='asset.embed',asset=result['asset'],asset_root=str(store)),1)['code'],'RESOURCE_LIMIT')
                self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),result['asset']['provenance']['source_sha256'])

    def test_palette_grayscale_and_untagged_interpretation_are_explicit(self):
        fixtures=[
            (png(2,2,b'',color=3,depth=2,raw=b'\0\x10\0\xb0',extra=[(b'PLTE',bytes([255,0,0,0,255,0,0,0,255,255,255,0])),(b'tRNS',bytes([255,128,0,255]))]),bytes([255,0,0,255,0,255,0,128,0,0,255,0,255,255,0,255])),
            (png(4,1,b'',color=0,depth=2,raw=b'\0\x1b'),bytes([0,0,0,255,85,85,85,255,170,170,170,255,255,255,255,255])),
        ]
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'fixture.png';store=Path(directory)/'assets'
            for data,expected in fixtures:
                source.write_bytes(data)
                asset=self.invoke(dict(command='asset.import',source_path=str(source),store_root=str(store)))['asset']
                embedded=self.invoke(dict(command='asset.embed',asset=asset,asset_root=str(store)))
                self.assertEqual(bytes.fromhex(embedded['storage']['rgba_hex']),expected)
            source.write_bytes(png(1,1,bytes([10,20,30,255]),tagged=False))
            request=dict(command='asset.import',source_path=str(source),store_root=str(store))
            self.assertEqual(self.invoke(request,1)['code'],'COLOR_POLICY_REQUIRED')
            asset=self.invoke({**request,'color_policy':'assume_srgb'})['asset']
            self.assertEqual(asset['provenance']['interpretation'],'assumed_srgb')
            source.write_bytes(png(1,1,bytes([10,20,30,255]),tagged=False,extra=[(b'gAMA',struct.pack('>I',50000))]))
            self.assertEqual(self.invoke({**request,'color_policy':'assume_srgb'},1)['code'],'UNSUPPORTED')

    def test_invalid_inputs_limits_and_metadata_never_publish_an_asset(self):
        good=png(1,1,bytes([20,40,80,255]));broken=bytearray(good);broken[-1]^=1
        fixtures=[(bytes(broken),'INVALID_IMAGE'),(good[:-4],'INVALID_IMAGE'),(good+b'trailing','INVALID_IMAGE'),
            (png(1,1,b'',depth=16,raw=b'\0'+b'\0'*8),'UNSUPPORTED'),
            (png(32768,32768,b'',raw=b''),'RESOURCE_LIMIT')]
        for kind,payload in [(b'iCCP',b'original\0\0'+zlib.compress(b'original test profile')),(b'eXIf',b'II*\0'),(b'acTL',struct.pack('>II',1,0)),(b'cICP',bytes([1,13,0,1])),(b'mDCV',bytes(24)),(b'cLLI',bytes(8))]:
            fixtures.append((png(1,1,bytes([20,40,80,255]),extra=[(kind,payload)]),'UNSUPPORTED'))
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'fixture.png'
            for i,(data,code) in enumerate(fixtures):
                source.write_bytes(data);store=Path(directory)/f'store-{i}'
                error=self.invoke(dict(command='asset.import',source_path=str(source),store_root=str(store)),1)
                self.assertEqual(error['code'],code)
                self.assertFalse(store.exists());self.assertEqual(source.read_bytes(),data)
                self.assertNotIn(directory,json.dumps(error))
            self.assertEqual(self.invoke(dict(command='asset.import',source_path='relative.png',store_root=directory),1)['code'],'INVALID_REQUEST')
            with source.open('wb') as stream:
                stream.truncate(32*1024*1024+1)
            store=Path(directory)/'oversized-store'
            self.assertEqual(self.invoke(dict(command='asset.import',source_path=str(source),store_root=str(store)),1)['code'],'RESOURCE_LIMIT')
            self.assertFalse(store.exists())
            self.assertEqual(source.stat().st_size,32*1024*1024+1)
            collision=Path(directory)/(hashlib.sha256(canonical(1,1,bytes([20,40,80,255]))).hexdigest()+'.rgba8')
            collision.write_bytes(good)
            self.assertEqual(self.invoke(dict(command='asset.import',source_path=str(collision),store_root=directory),1)['code'],'ASSET_CORRUPT')
            self.assertEqual(collision.read_bytes(),good)

    def test_concurrent_imports_publish_one_complete_asset(self):
        pixels=bytes([22,55,99,255])*16384
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'original.png';source.write_bytes(png(128,128,pixels));store=Path(directory)/'assets'
            request=dict(command='asset.import',source_path=str(source),store_root=str(store))
            with ThreadPoolExecutor(max_workers=6) as pool:
                results=list(pool.map(lambda _:self.invoke(request),range(6)))
            self.assertEqual(sum(r['created'] for r in results),1)
            self.assertEqual(len({r['asset']['sha256'] for r in results}),1)
            entries=list(store.iterdir());self.assertEqual(len(entries),1)
            self.assertEqual(entries[0].read_bytes(),canonical(128,128,pixels))
            self.invoke(dict(command='asset.verify',asset=results[0]['asset'],asset_root=str(store)))


if __name__=='__main__':
    unittest.main()
