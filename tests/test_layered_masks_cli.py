"""Independent authored-mask records, scalar coverage and source retention."""
import base64,copy,struct,tempfile,unittest
from pathlib import Path
import layered_fixtures as f
import test_layered_cli as core
from test_layered_groups_cli import marker
from test_mcp import Client


def masked(layer,gray=b'\x00\x40\xff\x80\xc0\x20',box=(2,3,4,6),outside=0,flags=0,parameters=b'',compression=0,version=1):
    layer=copy.deepcopy(layer);layer['mask']=struct.pack('>4iBB',*box,outside,flags)+parameters
    layer['mask']+=bytes((-len(layer['mask']))%2)
    if len(layer['mask'])==18:layer['mask']+=bytes(2)
    ids=[-1,0,1,2];p=bytes(layer['rgba'])
    layer['channel_ids']=ids+[-2]
    layer['channel_data']=[f.plane(p[(3 if c==-1 else c)::4],layer['width'],compression,version) for c in ids]+[f.plane(gray,box[3]-box[1],compression,version)]
    return layer

class LayeredMaskTests(unittest.TestCase):
    invoke=core.LayeredTests.invoke
    document=core.LayeredTests.document
    read=core.LayeredTests.read
    pixels=core.LayeredTests.pixels
    export=core.LayeredTests.export
    def layer(self):return dict(name='authored',width=6,height=4,xy=(1,1),rgba=[210,40,80,255]*24)
    def test_independent_inputs_keep_scalar_bytes_bounds_and_link_controls(self):
        for version in [1,2]:
            for compression in range(4):
                for linked in [True,False]:
                    l=masked(self.layer(),flags=0 if linked else 1,compression=compression,version=version)
                    r=self.read(f.make([l],version=version,compression=compression),color_policy='assume_srgb');i=r['document']['items'][0];m=i['mask']
                    self.assertEqual(m['gray_hex'],'0040ff80c020');self.assertEqual(i['content']['rgba_hex'],bytes(l['rgba']).hex());self.assertEqual(m['linked'],linked)
                    self.assertEqual(m['transform'],[1,0,0,1,2 if linked else 3,1 if linked else 2])
                    actual=bytes.fromhex(self.pixels(r['document']))
                    for y in range(6):
                        for x in range(8):
                            alpha=bytes.fromhex(m['gray_hex'])[(y-2)*3+x-3] if 3<=x<6 and 2<=y<4 else 0
                            self.assertEqual(actual[(y*8+x)*4+3],alpha)
    def test_density_disabled_outside_and_constant_fields_match_scalar_formula(self):
        for outside in [0,255]:
            for density in [0,128,255]:
                for disabled in [False,True]:
                    for constant in [False,True]:
                        box=(0,0,0,0) if constant else (2,3,4,6);gray=b'' if constant else b'\x00\x40\xff\x80\xc0\x20'
                        l=masked(self.layer(),gray=gray,box=box,outside=outside,flags=16+2*disabled,parameters=bytes([1,density]));d=self.read(f.make([l]),color_policy='assume_srgb')['document'];m=d['items'][0]['mask'];self.assertEqual(m.get('constant',False),constant)
                        actual=bytes.fromhex(self.pixels(d))
                        for y in range(6):
                            for x in range(8):
                                v=gray[(y-2)*3+x-3] if not constant and 3<=x<6 and 2<=y<4 else outside
                                alpha=255 if disabled else round(255-density*(1-v/255))
                                if not (1<=x<7 and 1<=y<5):alpha=0
                                self.assertLessEqual(abs(actual[(y*8+x)*4+3]-alpha),1)
    def test_export_independent_reader_preserves_sources_and_mask_receipts(self):
        for constant in [False,True]:
            source=masked(self.layer(),gray=b'' if constant else b'\x00\x40\xff\x80\xc0\x20',box=(0,0,0,0) if constant else (2,3,4,6),flags=17,parameters=bytes([1,128]),outside=255)
            d=self.read(f.make([source]),color_policy='assume_srgb')['document'];before=copy.deepcopy(d)
            for format in ['layered','layered_large']:
                a=self.invoke(dict(command='document.export',document=d,format=format));b=base64.b64decode(a['data']);l=f.parse(b)['layers'][0]
                self.assertEqual(l['rgba'],bytes(source['rgba']));self.assertEqual(l['mask_gray'].hex(),d['items'][0]['mask']['gray_hex']);self.assertEqual(l['mask'],source['mask']);self.assertEqual(a['layered']['layers'][0]['mask']['density'],128)
                reopened=self.read(b)['document'];self.assertEqual(self.pixels(reopened),self.pixels(d));self.assertEqual(reopened['items'][0]['mask'],d['items'][0]['mask'])
            self.assertEqual(d,before)
    def test_group_masks_and_linked_unlinked_movement_use_document_coordinates(self):
        for isolated in [True,False]:
            for linked in [True,False]:
                folder=masked(marker(1,mode=b'norm' if isolated else b'pass'),flags=0 if linked else 1)
                d=self.read(f.make([marker(3),self.layer(),folder]),color_policy='assume_srgb')['document'];group=next(i for i in d['items'] if i['content']['type']=='group')
                group['transform']=[1,0,0,1,1,0]
                raw=base64.b64decode(self.export(d)['data']);parsed=f.parse(raw);box=struct.unpack('>4i',parsed['layers'][-1]['mask'][:16]);self.assertEqual(box,(2,4,4,7) if linked else (2,3,4,6));self.assertEqual(parsed['layers'][0]['mask'],b'');self.assertEqual(self.pixels(self.read(raw)['document']),self.pixels(d))
    def test_malformed_mask_channel_pairs_records_and_compression_fail(self):
        good=masked(self.layer())
        bad=[]
        a=copy.deepcopy(good);a['mask']=b'';bad.append(a)
        a=copy.deepcopy(good);a['channel_ids']=a['channel_ids'][:-1];a['channel_data']=a['channel_data'][:-1];bad.append(a)
        for data in [b'x',good['mask'][:-1],good['mask']+b'\0\0\0\0',good['mask'][:-1]+b'\1']:
            a=copy.deepcopy(good);a['mask']=data;bad.append(a)
        for data in [b'\0\0',b'\0\0'+b'x'*7,f.plane(b'x'*100,3,2)]:
            a=copy.deepcopy(good);a['channel_data'][-1]=data;bad.append(a)
        for a in bad:
            self.assertEqual(self.read(f.make([a]),1,color_policy='assume_srgb')['code'],'INVALID_LAYERED_FILE')
    def test_unsupported_mask_semantics_are_never_silently_discarded(self):
        for flags,parameters in [(4,b''),(8,b''),(32,b''),(16,b'\x04\xff'),(16,b'\x02'+struct.pack('>d',.5))]:
            self.assertEqual(self.read(f.make([masked(self.layer(),flags=flags,parameters=parameters)]),1,color_policy='assume_srgb')['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        a=masked(self.layer());a['channel_ids'][-1]=-3;self.assertEqual(self.read(f.make([a]),1,color_policy='assume_srgb')['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        for change in [dict(invert=True),dict(feather=1),dict(sampling='bilinear'),dict(density=.5),dict(transform=[1,0,0,1,.5,0])]:
            d=self.read(f.make([masked(self.layer())]),color_policy='assume_srgb')['document'];d['items'][0]['mask'].update(change);self.assertEqual(self.export(d,1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
    def test_constant_masks_require_explicit_empty_plane_and_keep_old_validation(self):
        d=self.document(2,1);d['items']=[dict(id='p',content=dict(type='raster',width=2,height=1,rgba_hex='214365ff'*2))]
        for m in [dict(width=0,height=0,gray_hex=''),dict(constant=True,width=1,height=1,gray_hex='ff'),dict(constant=True,width=0,height=0,gray_hex='ff')]:
            d['items'][0]['mask']=m;self.assertEqual(self.invoke(dict(command='document.validate',document=d),1)['code'],'INVALID_DOCUMENT')
        for clip in [True,False]:
            d['items'][0]['mask']=dict(constant=True,width=0,height=0,gray_hex='',clip=clip);self.assertEqual(self.pixels(d),'00000000'*2 if clip else '214365ff'*2)
    def test_masks_share_retained_pixel_budget_even_when_disabled(self):
        l=dict(name='large',width=256,height=128,rgba=[1,2,3,255]*32768)
        mask=masked(l,gray=b'\xff'*32895,box=(0,0,129,255),flags=2)
        self.assertEqual(self.read(f.make([mask]),1,color_policy='assume_srgb')['code'],'RESOURCE_LIMIT')
    def test_agent_mask_edit_undo_publication_and_cancel_preserve_source(self):
        raw=f.make([masked(self.layer())]);d=self.read(raw,color_policy='assume_srgb')['document'];identity=d['items'][0]['id']
        with tempfile.TemporaryDirectory() as root:
            c=Client();c.initialize();self.addCleanup(c.close);s=dict(session_root=root,session_id='masks');c.success('session.create',**s,request_id='create',document=d)
            m=copy.deepcopy(d['items'][0]['mask']);m.update(enabled=False,density=128/255)
            changed=c.success('session.apply',**s,expected_revision=0,request_id='disable',action=dict(type='edit',operations=[dict(op='mask',id=identity,mask=m)]))['document']
            c.success('session.publish',**s,expected_revision=1,output=dict(output_root=root,file_name='mask.psd',format='layered'))
            re=c.success('layered.import',source_path=str(Path(root)/'mask.psd'),id='read')['document'];self.assertEqual(re['items'][0]['mask'],m);self.assertEqual(self.pixels(re),self.pixels(changed))
            undo=c.success('session.apply',**s,expected_revision=1,request_id='undo',action=dict(type='undo'))['document'];self.assertEqual(undo['items'][0]['mask'],d['items'][0]['mask']);self.assertTrue(c.success('session.verify',**s)['valid'])
            source=Path(root)/'original.psd';source.write_bytes(raw);self.assertEqual(self.invoke(dict(command='layered.import',source_path=str(source),id='cancel',control=dict(timeout_ms=0)),1)['code'],'TIMEOUT');self.assertEqual(source.read_bytes(),raw)

    def test_display_overlay_metadata_delegates_to_layer_coverage_and_reports_omission(self):
        l=masked(self.layer());overlay=bytes(10)+f.U16(50)+b'\x80'+bytes(3)
        result=self.read(f.make([l],global_mask=overlay),color_policy='assume_srgb')
        self.assertIn('global_mask:per_layer_display_overlay',result['omitted_nonappearance_records'])
        self.assertEqual(self.pixels(result['document']),self.pixels(self.read(f.make([l]),color_policy='assume_srgb')['document']))
        for blob in [bytes(10)+f.U16(101)+b'\x80',bytes(12)+b'\0',bytes(12)+b'\1']:
            self.assertEqual(self.read(f.make([l],global_mask=blob),1,color_policy='assume_srgb')['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        for blob in [b'x',overlay+b'\0',overlay[:-1]+b'\1']:
            self.assertEqual(self.read(f.make([l],global_mask=blob),1,color_policy='assume_srgb')['code'],'INVALID_LAYERED_FILE')

    def test_mask_effect_order_is_reported_only_for_supported_no_effect_sources(self):
        for order in [0,1]:
            l=masked(self.layer());l['extra']=f.tag(b'lmgm',bytes([order,0,0,0]))+f.tag(b'lyvr',f.U32(110))
            r=self.read(f.make([l]),color_policy='assume_srgb');self.assertIn('lyvr:minimum_reader_110',r['omitted_nonappearance_records']);self.assertIn(f'lmgm:effect_order_{order}_inactive_without_effects',r['omitted_nonappearance_records'])
            l['extra']+=f.tag(b'lfx2',bytes(8));self.assertEqual(self.read(f.make([l]),1,color_policy='assume_srgb')['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        for l in [self.layer(),masked(self.layer())]:
            l['extra']=f.tag(b'lmgm',bytes([2,0,0,0]));self.assertEqual(self.read(f.make([l]),1,color_policy='assume_srgb')['code'],'UNSUPPORTED_LAYERED_SEMANTICS')

if __name__=='__main__':unittest.main()
