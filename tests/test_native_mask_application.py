"""Whole native mask baking against independent bytes, coverage and history."""
import copy
import hashlib
import math
import struct
import unittest

import test_native_masks as masks
from test_masks_cli import opacity


class NativeMaskApplicationTests(unittest.TestCase):
    setUp = masks.NativeMaskTests.setUp
    cli = masks.NativeMaskTests.cli
    save = masks.NativeMaskTests.save
    ref = masks.NativeMaskTests.ref
    files = masks.NativeMaskTests.files
    blocks = masks.NativeMaskTests.blocks
    mask = masks.NativeMaskTests.mask
    imported = masks.NativeMaskTests.imported

    def source(self, raw, w, h, depth='u16', channels=4, encoding='encoded_srgb', stored=True):
        unit = {'u8':1, 'u16':2, 'f32':4}[depth]
        spec = dict(width=w, height=h, depth=depth,
                    channels='rgba' if channels == 4 else 'gray_alpha', encoding=encoding)
        d = self.cli('document.create', id='bake', kind='raster', width=w, height=h)
        if encoding == 'linear_srgb': d['color_space'] = 'linear_srgb'
        grid = dict(spec, data_hex=raw.hex(), sampling='nearest')
        if stored:
            def header(width, height):
                return b'INKTILE1' + struct.pack('<IIBBBB',width,height,unit,channels,
                    ['encoded_srgb','linear_srgb','profiled_rgb'].index(encoding),0)
            store = self.root/'.inkbolt/assets'; store.mkdir(parents=True, exist_ok=True)
            ids = []
            for top in range(0,h,128):
                for left in range(0,w,128):
                    tw,th=min(128,w-left),min(128,h-top)
                    blob=header(tw,th)+b''.join(raw[(y*w+left)*unit*channels:(y*w+left+tw)*unit*channels] for y in range(top,top+th))
                    digest=hashlib.sha256(blob).hexdigest();ids.append(digest)
                    path=store/(digest+'.native-tile')
                    if path.exists(): self.assertEqual(path.read_bytes(),blob)
                    else: path.write_bytes(blob)
            identity=hashlib.sha256(b'INKGRID1'+header(w,h)+struct.pack('<I',128)+b''.join(bytes.fromhex(v) for v in ids)).hexdigest()
            grid=dict(storage_version=2,base=dict(version=1,spec=spec,tiles=ids,sha256=identity),sampling='nearest')
        if encoding=='profiled_rgb': grid['profile']=dict(type='builtin',name='linear_srgb')
        d['items']=[dict(id='pixels',name='source',content=dict(type='stored_samples' if stored else 'samples',grid=grid))]
        return d

    def raw(self, d):
        grid=d['items'][0]['content']['grid']
        if 'data_hex' in grid: return bytes.fromhex(grid['data_hex'])
        manifest=grid['base'];s=manifest['spec'];w,h=s['width'],s['height']
        stride={'u8':1,'u16':2,'f32':4}[s['depth']]*(4 if s['channels']=='rgba' else 2)
        result=bytearray(w*h*stride)
        pending={v['sha256']:bytes.fromhex(v['data_hex']) for v in grid.get('staged',{}).get('pending',[])}
        for i,digest in enumerate(manifest['tiles']):
            blob=pending[digest] if digest in pending else (self.root/'.inkbolt/assets'/(digest+'.native-tile')).read_bytes()
            self.assertEqual(hashlib.sha256(blob).hexdigest(),digest)
            tw,th=struct.unpack_from('<II',blob,8)
            left,top=i%math.ceil(w/128)*128,i//math.ceil(w/128)*128
            for y in range(th):
                offset=((top+y)*w+left)*stride
                result[offset:offset+tw*stride]=blob[20+y*tw*stride:20+(y+1)*tw*stride]
        return bytes(result)

    def bake(self,d,**kw):
        return self.cli('document.edit',document=d,expected_revision=d['revision'],
                        operations=[dict(op='mask_apply',id='pixels')],**kw)

    def test_all_layouts_color_bits_hidden_color_profile_and_float_rounding(self):
        w,h=132,3
        mask,inline=self.mask(w,h)
        for depth,fmt,maximum in [('u8','B',255),('u16','H',65535),('f32','f',1)]:
            for channels in [2,4]:
                for encoding in ['encoded_srgb','profiled_rgb']+(['linear_srgb'] if depth=='f32' else []):
                    raw=bytearray();expected=bytearray()
                    for y in range(h):
                        for x in range(w):
                            color=[((x*17+y*19+c*31)%256)/256 for c in range(channels-1)]
                            if depth!='f32': color=[int(v*maximum) for v in color]
                            elif encoding=='linear_srgb': color=[[-0.0,-3.5,8.25][(x+c)%3] for c in range(channels-1)]
                            alpha=([0,1,maximum//3,maximum] if depth!='f32' else [-0.0,2**-149,.5,1.0])[x%4]
                            pixel=struct.pack('<'+fmt*channels,*(color+[alpha]));raw.extend(pixel)
                            coverage=(x*71+y*13)%256
                            # Exact rational integer rounding; float cases retain one binary32 rounding.
                            out=(alpha*coverage*2+255)//510 if depth!='f32' else alpha*(coverage/255)
                            expected.extend(pixel[:-struct.calcsize(fmt)]+struct.pack('<'+fmt,out))
                    for stored in [False,True]:
                        d=self.source(raw,w,h,depth,channels,encoding,stored)
                        d['items'][0]['mask']=mask if stored else inline
                        before=copy.deepcopy(d)
                        baked=self.bake(d)['document']
                        self.assertEqual(self.raw(baked),expected,(depth,channels,encoding,stored))
                        self.assertNotIn('mask',baked['items'][0])
                        self.assertEqual(baked['items'][0]['content']['grid'].get('profile'),d['items'][0]['content']['grid'].get('profile'))
                        self.assertEqual(d,before)

    def test_controls_transformed_centers_and_full_plane_outside_document_view(self):
        w,h=133,131
        raw=struct.pack('<4H',101,202,303,65535)*(w*h)
        for sampling,linked in [('nearest',True),('bilinear',False)]:
            mask,inline=self.mask(w,h,sampling=sampling,linked=linked,feather=1,invert=True,density=.63,clip=False,
                                  transform=[1,0,0,1,-.25,.75])
            d=self.source(raw,w,h);d['width']=d['height']=3
            d['items'][0].update(mask=mask,transform=[1,0,0,1,3.5,-2.5])
            actual=self.raw(self.bake(d)['document']);expected=bytearray()
            for y in range(h):
                for x in range(w):
                    point=(x+.5,y+.5) if linked else (x+4,y-2)
                    alpha=math.floor(opacity(inline,point)*65535+.5)
                    expected.extend(struct.pack('<4H',101,202,303,alpha))
            self.assertEqual(actual,expected)

    def test_full_coverage_reuses_blocks_and_legacy_requires_explicit_migration(self):
        d=self.imported(133,131,storage={})
        d['items'][0]['mask']=dict(width=1,height=1,gray_hex='ff',clip=False)
        before=self.blocks();old_grid=copy.deepcopy(d['items'][0]['content']['grid'])
        baked=self.bake(d)['document']
        self.assertEqual(baked['items'][0]['content']['grid'],old_grid)
        self.assertEqual(self.blocks(),before)
        legacy=copy.deepcopy(d);legacy['items'][0]['content']['grid']['storage_version']=1
        self.bake(legacy,error='MIGRATION_REQUIRED')
        baked=self.cli('document.edit',document=legacy,expected_revision=0,operations=[
            dict(op='sample_storage_migrate',id='pixels'),dict(op='mask_apply',id='pixels')])['document']
        self.assertEqual(baked['items'][0]['content']['grid'],old_grid)

    def test_review_commit_retry_undo_redo_backup_and_late_failure(self):
        d=self.imported(133,131,storage={});mask,_=self.mask();d['items'][0]['mask']=mask
        original=self.save(d)['document'];before=self.files();old=self.raw(original)
        action=dict(type='edit',operations=[dict(op='mask_apply',id='pixels')])
        review=self.cli('session.dry_run',session_id='work',request_id='bake',expected_revision=0,action=action,
                        options=dict(include_document=True,preview=True,compare_pixels=True))
        self.assertEqual(self.files(),before)
        expected=self.raw(review['proposed_document'])
        self.assertNotEqual(old,expected)
        self.cli('session.apply',session_id='work',request_id='bad',expected_revision=0,action=dict(type='edit',operations=action['operations']+[
            dict(op='remove',id='missing')]),error='NOT_FOUND')
        self.assertEqual(self.files(),before)
        done=self.cli('session.apply_proposal',proposal=review['proposal'],action=action)
        self.assertEqual(done['receipt'],review['predicted_receipt'])
        self.assertTrue(self.cli('session.apply_proposal',proposal=review['proposal'],action=action)['replayed'])
        self.assertEqual(self.raw(done['document']),expected)
        self.assertEqual(self.raw(original),old)
        undo=self.cli('session.apply',session_id='work',request_id='undo',expected_revision=1,action=dict(type='undo'))
        self.assertEqual(undo['document'],dict(original,revision=2))
        redo=self.cli('session.apply',session_id='work',request_id='redo',expected_revision=2,action=dict(type='redo'))
        self.assertEqual(self.raw(redo['document']),expected)
        backup=self.cli('session.backup',session_id='work',expected_revision=3,output=dict(file_name='bake.sqlite3'))
        self.cli('session.recover',session_id='work',session_root='recovered',source=backup['backup'])
        self.assertTrue(self.cli('session.verify',session_id='work',session_root='recovered')['valid'])
        self.assertEqual(self.raw(self.cli('session.read',session_id='work',session_root='recovered')['document']),expected)

    def test_hidden_source_corruption_and_cancel_preserve_workspace(self):
        d=self.imported(133,131,storage={});d['items'][0]['mask']=self.mask()[0]
        before=self.files()
        self.bake(d,control=dict(timeout_ms=0),error='TIMEOUT')
        self.assertEqual(self.files(),before)
        d['width']=d['height']=1
        path=self.root/'.inkbolt/assets'/(d['items'][0]['content']['grid']['base']['tiles'][-1]+'.native-tile')
        raw=path.read_bytes();path.write_bytes(raw[:-1]+bytes([raw[-1]^1]));before=self.files()
        self.bake(d,error='SAMPLE_TILE_CORRUPT')
        self.assertEqual(self.files(),before)

    def test_large_review_keeps_transport_bound_and_can_commit_without_returning_private_bytes(self):
        d=self.imported(1024,1024,storage={});d['items'][0]['mask']=self.mask(1024,1024)[0]
        original=self.raw(d);self.save(d);before=self.files()
        action=dict(type='edit',operations=[dict(op='mask_apply',id='pixels')])
        self.cli('session.dry_run',session_id='work',request_id='large',expected_revision=0,action=action,
                 options=dict(include_document=True),error='RESOURCE_LIMIT')
        review=self.cli('session.dry_run',session_id='work',request_id='large',expected_revision=0,action=action)
        self.assertNotIn('proposed_document',review)
        self.assertEqual(self.files(),before)
        committed=self.cli('session.apply_proposal',proposal=review['proposal'],action=action)
        self.assertEqual(committed['receipt'],review['predicted_receipt'])
        actual=self.raw(committed['document'])
        for channel in range(6): self.assertEqual(actual[channel::8],original[channel::8])
        expected=bytes((x*71+y*13)%256 for y in range(1024) for x in range(1024))
        self.assertEqual(actual[6::8],expected)
        self.assertEqual(actual[7::8],expected)


if __name__=='__main__': unittest.main()
