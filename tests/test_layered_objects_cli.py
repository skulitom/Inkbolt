"""Editable source, independent placement, strict framing and retry contracts."""
import copy,hashlib,json,struct,tempfile,unittest
from pathlib import Path
import layered_fixtures as f
import layered_object_fixtures as o
import test_layered_cli as core
import test_layered_metadata_cli as m
from test_layered_masks_cli import masked
from test_layered_groups_cli import marker
from test_profiles_cli import linear_profile
from test_mcp import Client


class LayeredObjectTests(unittest.TestCase):
    invoke=core.LayeredTests.invoke
    read=core.LayeredTests.read
    pixels=core.LayeredTests.pixels

    def load(self,raw=None,expected=0,**kwargs):
        return self.read(o.outer() if raw is None else raw,expected,
                         **dict(dict(color_policy='assume_srgb',embedded_objects=o.POLICY),**kwargs))

    def test_explicit_policy_source_hashes_and_editable_pixels_ignore_different_cache(self):
        raw=o.outer()
        error=self.read(raw,1,color_policy='assume_srgb')
        self.assertEqual(error['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        self.assertIn('embedded_objects',error['message'])
        r=self.load(raw);item=r['document']['items'][0];obj=item['content']['object']
        source=json.loads(obj['snapshot'])
        self.assertEqual(source['items'][0]['content']['rgba_hex'],o.PIXELS.hex())
        self.assertEqual(obj['sha256'],hashlib.sha256(obj['snapshot'].encode()).hexdigest())
        self.assertEqual(r['embedded_sources'][0]['native_source_sha256'],hashlib.sha256(o.source()).hexdigest())
        self.assertFalse(r['embedded_placements'][0]['cache_used_for_editable_reconstruction'])
        self.assertEqual(r['embedded_placements'][0]['cached_rgba_sha256'],hashlib.sha256(o.cache()['rgba']).hexdigest())
        self.assertEqual(r['embedded_placements'][0]['placed_id'],'placed-a')
        changed=self.load(o.outer(layers=[o.cache(rgba=bytes([255,0,0,0])*6)]))
        self.assertEqual(changed['document'],r['document'])
        self.assertEqual(self.pixels(changed['document']),self.pixels(r['document']))
        self.assertEqual(self.invoke(dict(command='document.export',document=r['document'],format='layered'),1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')

    def test_independent_affine_pixel_oracle_translation_scale_rotation_and_reflection(self):
        matrices=[(1,0,0,1,2,1),(2,0,0,2,1,1),(-1,0,0,1,5,2),(0,1,-1,0,5,1),(1,.5,0,1,1,.125)]
        for matrix in matrices:
            with self.subTest(matrix=matrix):
                d=self.load(o.outer(layers=[o.cache(extra=o.placement(matrix=matrix,legacy=True))]))['document']
                self.assertEqual(d['items'][0]['transform'],list(matrix))
                expected=bytearray();a,b,c,e,tx,ty=matrix;det=a*e-b*c
                for y in range(6):
                    for x in range(8):
                        sx=(e*(x+.5-tx)-c*(y+.5-ty))/det;sy=(-b*(x+.5-tx)+a*(y+.5-ty))/det
                        p=o.PIXELS[(int(sy)*3+int(sx))*4:(int(sy)*3+int(sx)+1)*4] if 0<=sx<3 and 0<=sy<2 else bytes(4)
                        expected.extend(p if p[3] else bytes(4))
                actual=self.invoke(dict(command='document.render',document=d,render_options=dict(antialias='none')))['data']
                self.assertEqual(bytes.fromhex(actual),expected)
                if matrix != matrices[-1]:self.assertEqual(bytes.fromhex(self.pixels(d)),expected)

    def test_compressions_file_versions_source_record_versions_and_reconstruction_choices(self):
        for version in [1,2]:
            for compression in range(4):
                data=o.source(compression,version)
                for record_version in [1,2,3,4,5,6,7,8]:
                    r=self.load(o.outer(data,version=version,compression=compression,
                        entries=[o.entry(data,version=record_version,opening=record_version%2==0)]))
                    obj=r['document']['items'][0]['content']['object']
                    self.assertEqual(json.loads(obj['snapshot'])['items'][0]['content']['rgba_hex'],o.PIXELS.hex())
        for sampling in ['nearest','bilinear','area','bicubic','lanczos3']:
            r=self.load(embedded_objects=dict(o.POLICY,sampling=sampling))
            self.assertEqual(r['document']['items'][0]['content']['object']['sampling'],sampling)
            self.pixels(r['document'])

    def test_placement_versions_and_known_color_policy_accept_only_explicit_fields(self):
        color=m.obj('ClMg',[('placedLayerOCIOConversion',m.enum('placedLayerOCIOConversion','placedLayerOCIOConvertEmbedded'))])
        for version in [4,5]:
            self.load(o.outer(layers=[o.cache(extra=o.placement(version=version,changes={'ClMg':color}))]))
        for policy in [{},dict(sampling='nearest'),dict(o.POLICY,sharing='shared'),dict(o.POLICY,unknown=True)]:
            self.load(expected=1,embedded_objects=policy)

    def test_shared_source_becomes_explicit_independent_copies(self):
        layers=[o.cache(),o.cache(identity=2,extra=o.placement(placed='placed-b',matrix=(1,0,0,1,5,1)))]
        r=self.load(o.outer(layers=layers));d=r['document']
        self.assertEqual(len(r['embedded_sources']),1)
        self.assertEqual([p['sharing'] for p in r['embedded_placements']],['independent_copies']*2)
        self.assertEqual(d['items'][0]['content'],d['items'][1]['content'])
        opened=self.invoke(dict(command='object.open',document=d,id='layer-1'))['document']
        opened['items'][0]['visible']=False
        replacement=self.invoke(dict(command='object.import',snapshot=json.dumps(opened)))['object']
        changed=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='object_replace',id='layer-1',object=replacement)]))['document']
        self.assertEqual(changed['items'][1],d['items'][1]);self.assertNotEqual(changed['items'][0]['content'],d['items'][0]['content'])

    def test_linked_and_unlinked_masks_rebase_from_cached_extents_to_source_space(self):
        for linked in [True,False]:
            layer=masked(o.cache(extra=o.placement(matrix=(2,0,0,2,1,1))),gray=bytes([0,80,160,255]),box=(1,2,3,4),flags=0 if linked else 1)
            d=self.load(o.outer(layers=[layer]))['document'];mask=d['items'][0]['mask']
            self.assertEqual(mask['linked'],linked)
            self.assertEqual(mask['transform'],[.5,0,0,.5,.5,0] if linked else [1,0,0,1,2,1])
            actual=bytes.fromhex(self.pixels(d))
            for y in range(6):
                for x in range(8):
                    value=0
                    if 2<=x<4 and 1<=y<3:
                        value=round(o.PIXELS[((y-1)//2*3+(x-1)//2)*4+3]*[0,80,160,255][(y-1)*2+x-2]/255)
                    self.assertLessEqual(abs(actual[(y*8+x)*4+3]-value),1)

    def test_nested_groups_sources_and_four_level_limit(self):
        grouped=f.make([marker(3),dict(name='Source pixels',width=3,height=2,rgba=o.PIXELS),marker(1)],w=3,h=2)
        d=self.load(o.outer(grouped))['document'];source=json.loads(d['items'][0]['content']['object']['snapshot'])
        self.assertEqual(sorted(i['content']['type'] for i in source['items']),['group','raster'])
        child=next(i for i in source['items'] if i['content']['type']=='raster')
        group=next(i for i in source['items'] if i['content']['type']=='group')
        self.assertEqual(child['parent'],group['id'])
        data=o.source()
        for level in range(1,6):
            data=o.outer(data,layers=[o.cache(extra=o.placement(matrix=(1,0,0,1,0,0)))],w=3,h=2)
            if level<=4:self.load(data)
            else:self.assertEqual(self.load(data,1)['code'],'RESOURCE_LIMIT')

    def test_zero_allocation_tail_is_embedded_only_aligned_bounded_and_validated(self):
        for compression in range(4):
            data=o.source(compression,2);padded=data+bytes(1024*1024-len(data))
            r=self.load(o.outer(padded))
            self.assertEqual(r['embedded_sources'][0]['embedded_zero_padding'],len(padded)-len(data))
            self.assertEqual(self.read(padded,1,color_policy='assume_srgb')['code'],'INVALID_LAYERED_FILE')
            for bad in [data+b'\0',padded[:-1]+b'\1',padded+bytes(1024*1024),data+b'trailing']:
                self.assertEqual(self.load(o.outer(bad),1)['code'],'INVALID_LAYERED_FILE')
        self.assertEqual(self.load(o.outer()+b'\0',1)['code'],'INVALID_LAYERED_FILE')

    def test_missing_unused_duplicate_external_and_malformed_sources_are_never_cached_fallbacks(self):
        data=o.source()
        for entries in [[],[o.entry(data,identity='other')],[o.entry(data),o.entry(data)],
                        [o.entry(data),o.entry(data,identity='unused')],[o.entry(data,kind=b'liFE')],
                        [o.entry(data,kind=b'liFA')],[o.entry(data,version=9)],[o.entry(data,suffix=b'\1')],
                        [o.entry(b'valid cache but invalid source')],[o.entry(data)[:-1]]]:
            with self.subTest(entries=[len(e) for e in entries]):
                self.assertIn(self.load(o.outer(entries=entries),1)['code'],['INVALID_LAYERED_FILE','UNSUPPORTED_LAYERED_SEMANTICS'])
        duplicate=[o.cache(),o.cache(identity=2)]
        self.assertEqual(self.load(o.outer(layers=duplicate),1)['code'],'INVALID_LAYERED_FILE')

    def test_source_record_padding_is_exact_zero_alignment_only(self):
        for version in range(1,9):
            entry=o.entry(o.source(),version=version);payload=entry[8:];padding=-len(payload)%4
            self.load(o.outer(entries=[f.large_section(payload+bytes(padding))]))
            for extra in [b'\1'*max(1,padding),bytes(padding+4),bytes(padding+1)]:
                self.assertEqual(self.load(o.outer(entries=[f.large_section(payload+extra)]),1)['code'],'INVALID_LAYERED_FILE')

    def test_active_warp_comp_animation_perspective_unknown_and_conflicting_metadata_fail(self):
        changes=[{'warp':m.obj('warp',o.warp(1))},{'comp':m.integer(1)},
                 {'compInfo':m.obj('null',o.comp(0))},{'frameCount':m.integer(2)},
                 {'duration':m.obj('null',[('numerator',m.integer(1)),('denominator',m.integer(24))])},
                 {'mystery':m.boolean(1)},{'Rslt':b'UntF#Pxl'+struct.pack('>d',72)},
                 {'Rslt':b'UntF#Rsl'+struct.pack('>d',float('nan'))},
                 {'nonAffineTransform':m.sequence([m.number(v) for v in [2,1,5,1,6,3,2,3]])}]
        for change in changes:
            self.assertIn(self.load(o.outer(layers=[o.cache(extra=o.placement(changes=change))]),1)['code'],
                          ['INVALID_LAYERED_FILE','UNSUPPORTED_LAYERED_SEMANTICS'])
        for params in [dict(size=(2,2)),dict(ppi=100),dict(matrix=(1,0,0,0,0,0))]:
            self.load(o.outer(layers=[o.cache(extra=o.placement(**params))]),1)
        legacy=o.placement(legacy=True);conflict=legacy.replace(b'source-a',b'source-b',1)
        self.assertEqual(self.load(o.outer(layers=[o.cache(extra=conflict)]),1)['code'],'INVALID_LAYERED_FILE')

    def test_profile_conversion_recurses_and_empty_annotations_are_the_only_omission(self):
        data=o.source(profile=linear_profile())
        self.assertEqual(self.load(o.outer(data),1)['code'],'COLOR_POLICY_REQUIRED')
        raw=o.outer(data,profile=linear_profile())
        r=self.load(raw,color_policy='convert_srgb')
        obj=r['document']['items'][0]['content']['object'];rgba=bytes.fromhex(json.loads(obj['snapshot'])['items'][0]['content']['rgba_hex'])
        self.assertEqual(rgba[3::4],o.PIXELS[3::4]);self.assertNotEqual(rgba,o.PIXELS)
        self.assertEqual(r['embedded_sources'][0]['interpretation'],'converted_srgb_per_layer')
        empty=f.U16(2)+f.U16(1)+f.U32(0)
        self.load(o.outer(o.source(global_extra=m.global_tag(b'Anno',empty))))
        self.load(o.outer(o.source(global_extra=m.global_tag(b'lnkE',b''))))
        self.load(o.outer(o.source(global_extra=m.global_tag(b'lnkE',b'external'))),1)
        for bad in [empty[:-1],f.U16(2)+f.U16(1)+f.U32(1),f.U16(3)+empty[2:],empty+b'\0']:
            self.load(o.outer(o.source(global_extra=m.global_tag(b'Anno',bad))),1)

    def test_aggregate_canvas_items_and_independent_snapshot_budgets_fail_before_return(self):
        small=dict(name='original',width=1,height=1,rgba=[20,40,60,255])
        source=f.make([small],w=1024,h=1024,compression=1)
        layers=[o.cache(extra=o.placement(size=(1024,1024)))]
        self.assertEqual(self.load(o.outer(source,layers=layers,w=1024,h=1024,compression=1),1)['code'],'RESOURCE_LIMIT')
        many=[dict(small,id=i+1) for i in range(255)]
        source=f.make(many+[dict(small,id=256)],w=3,h=2)
        for _ in range(4):source=o.outer(source,layers=many+[o.cache(identity=256)],w=3,h=2)
        self.assertEqual(self.load(source,1)['code'],'RESOURCE_LIMIT')
        source=f.make([dict(name='retained',width=128,height=128,rgba=[20,40,60,255]*16384)],w=128,h=128,compression=1)
        layers=[o.cache(identity=i+1,extra=o.placement(placed=f'copy-{i}',size=(128,128))) for i in range(65)]
        self.assertEqual(self.load(o.outer(source,layers=layers),1)['code'],'RESOURCE_LIMIT')

    def test_mcp_restart_retry_conflict_undo_cancellation_and_snapshot_delivery(self):
        raw=o.outer();source_hash=hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'source.psd';path.write_bytes(raw)
            session=dict(session_root=root,session_id='embedded');c=Client();c.initialize()
            try:
                cap=c.success('capabilities')['layered_interchange']
                self.assertEqual(cap['embedded_objects']['import'],'explicit_policy_required')
                self.assertEqual(cap['embedded_objects']['export'],'explicit_policy_required')
                self.assertFalse(cap['embedded_objects']['native_composite_equality'])
                self.assertEqual(cap['extended_status'],'partial_uncredited')
                self.assertEqual(cap['embedded_objects']['export_policy']['layered_options']['embedded_objects'],'native_reconstruction')
                d=c.success('layered.import',source_path=str(path),id='objects',expected_sha256=source_hash,
                            color_policy='assume_srgb',embedded_objects=o.POLICY)['document']
                c.success('session.create',**session,request_id='create',document=d)
                opened=c.success('object.open',document=d,id='layer-1')['document'];opened['items'][0]['visible']=False
                replacement=c.success('object.import',snapshot=json.dumps(opened))['object']
                edit=dict(request_id='replace',expected_revision=0,action=dict(type='edit',operations=[dict(op='object_replace',id='layer-1',object=replacement)]))
                first=c.success('session.apply',**session,**edit)
            finally:c.close()
            c=Client();c.initialize()
            try:
                replay=c.success('session.apply',**session,**edit);self.assertTrue(replay['replayed']);self.assertEqual(first['receipt'],replay['receipt'])
                stale=c.tool('session.apply',**session,**dict(edit,request_id='stale'))
                self.assertTrue(stale['isError'])
                restored=c.success('session.apply',**session,request_id='undo',expected_revision=1,action=dict(type='undo'))['document']
                self.assertEqual(dict(restored,revision=d['revision']),d)
                self.assertTrue(c.success('session.verify',**session)['valid'])
                output=dict(output_root=root,file_name='editable.json',format='snapshot')
                c.success('session.publish',**session,expected_revision=2,output=output)
                self.assertEqual(json.loads((Path(root)/'editable.json').read_text()),restored)
                error=c.tool('layered.import',source_path=str(path),id='cancel',embedded_objects=o.POLICY,control=dict(timeout_ms=0))
                self.assertEqual(error['structuredContent']['error']['code'],'TIMEOUT')
            finally:c.close()
            self.assertEqual(path.read_bytes(),raw)


if __name__=='__main__':unittest.main()
