"""Original folder grammar, independent records, pixels and durable workflows."""
from advertised_limits import capabilities
import base64,copy,hashlib,tempfile,unittest
from fractions import Fraction
from pathlib import Path
import layered_fixtures as f
import test_blending_cli as reference
import test_layered_cli as core
from test_mcp import Client

def marker(kind,name='folder',mode=b'norm',**kw):
    data=f.U32(kind)+(b'8BIM'+mode if kind in [1,2] else b'')
    return dict(name=name,width=0,height=0,rgba=[],extra=f.tag(b'lsct',data),**kw)
def pixel(name='pixels',**kw):return dict(name=name,width=2,height=1,rgba=[17,221,103,0,190,31,79,128],**kw)
def tree(d):
    def children(parent):
        return [(i['name'],i['content']['type'],i['visible'],i['opacity'],children(i['id'])) for i in d['items'] if i.get('parent')==parent]
    return children(None)


BLENDS = {
    'multiply': b'mul ', 'screen': b'scrn', 'darken': b'dark', 'lighten': b'lite',
    'overlay': b'over', 'hard_light': b'hLit', 'soft_light': b'sLit', 'exclusion': b'smud',
    'pin_light': b'pLit', 'subtract': b'fsub', 'hue': b'hue ', 'saturation': b'sat ',
    'color': b'colr', 'luminosity': b'lum ',
}
BACK = bytes.fromhex('265abaff 962b8e79 943a791f 54403100')
FIRST = bytes.fromhex('cd6523ff 63959b89 a0ae6fdb fc6bb895')
SECOND = bytes.fromhex('1676b960 f7a264c0 588cf100 ab1948b2')


def blended_sheet(mode, grouped):
    def strip(name, samples, **controls):
        return dict(name=name, width=4, height=1, rgba=samples, **controls)
    back = strip('paper', BACK)
    key = BLENDS[mode]
    if grouped:
        return [back, marker(3), strip('lower', FIRST), strip('upper', SECOND, blend=b'scrn'),
                marker(1, 'folder', mode=key, opacity=173)]
    return [back, strip('ink', FIRST, blend=key, opacity=173, extra=f.tag(b'iOpa',bytes([191,0,0,0])))]


def expected_strip(mode, grouped, fill=255, upper_mode='screen'):
    result = bytearray()
    for offset in range(0,len(BACK),4):
        back, first, second = (reference.premul(raw[offset:offset+4]) for raw in (BACK,FIRST,SECOND))
        if grouped:
            folder = reference.over(first, second, mode=upper_mode)
            color = reference.over(back, folder, Fraction(173*fill,255**2), mode)
        else:
            color = reference.over(back, first, Fraction(173*191,255**2), mode)
        result.extend(round(v) for v in reference.encoded(color))
    return bytes(result)

class GroupLayeredTests(unittest.TestCase):
    invoke=core.LayeredTests.invoke
    document=core.LayeredTests.document
    read=core.LayeredTests.read
    pixels=core.LayeredTests.pixels
    def export(self,d,version=1,expected=0):return self.invoke(dict(command='document.export',document=d,format='layered' if version==1 else 'layered_large'),expected)
    def scene(self):
        d=self.document(12,8)
        d['items']=[dict(id='back',content=dict(type='raster',width=2,height=1,rgba_hex='2864a0ff'*2)),dict(id='outer',name='folder Δ 🎨',opacity=153/255,transform=[1,0,0,1,2,1],content=dict(type='group',isolated=False)),dict(id='p',parent='inner',name='original',transform=[1,0,0,1,1,0],content=dict(type='raster',width=2,height=1,rgba_hex='11dd6700be1f4f80')),dict(id='inner',parent='outer',name='inner',opacity=128/255,content=dict(type='group',isolated=True)),dict(id='empty',parent='outer',name='empty',visible=False,locked=True,content=dict(type='group')),dict(id='above',name='original',transform=[1,0,0,1,3,2],content=dict(type='raster',width=1,height=1,rgba_hex='f08a3380'))]
        return self.invoke(dict(command='document.validate',document=d))
    def test_export_nested_folders_preserves_tree_original_pixels_and_absolute_placement(self):
        d=self.scene();before=copy.deepcopy(d)
        for version in [1,2]:
            artifact=self.export(d,version);raw=base64.b64decode(artifact['data']);native=f.parse(raw);records=native['layers'];self.assertEqual(len(records),9)
            self.assertEqual(artifact['layered']['empty_name_source_ids'],['back']);self.assertTrue(any('Empty names' in loss for loss in artifact['losses']))
            self.assertEqual([r['name'] for r in records],['','<group end>','<group end>','original','inner','<group end>','empty','folder Δ 🎨','original'])
            self.assertEqual(records[3]['bounds'],[1,3,2,5]);self.assertEqual(records[3]['rgba'].hex(),'11dd6700be1f4f80');self.assertEqual(records[7]['tags'][b'lsct'],f.U32(1)+b'8BIMpass')
            reopened=self.read(raw);self.assertEqual(reopened['layers'],6);self.assertEqual(reopened['groups'],3);self.assertEqual(reopened['serialized_records'],9)
            self.assertEqual(tree(reopened['document']),tree(d));self.assertEqual(self.pixels(reopened['document']),self.pixels(d));self.assertEqual(d,before)
            for item in reopened['document']['items']:
                if item['content']['type']=='group':self.assertEqual(item['transform'],[1,0,0,1,0,0])
    def test_original_nested_import_all_compressions_versions_and_folder_modes(self):
        records=[pixel('below'),marker(3),marker(3),pixel('same',xy=(2,1)),marker(2,'same',visible=False),pixel('second',xy=(1,2)),marker(1,'folder Δ 🎨',mode=b'pass',opacity=153),pixel('above',xy=(4,3))]
        outputs=[]
        for version in [1,2]:
            for compression in range(4):
                r=self.read(f.make(records,compression=compression,version=version),color_policy='assume_srgb');d=r['document'];self.assertEqual(r['groups'],2);self.assertEqual(len(d['items']),6)
                outer=next(i for i in d['items'] if i['name']=='folder Δ 🎨');self.assertFalse(outer['content']['isolated']);self.assertEqual(outer['opacity'],153/255)
                inner=next(i for i in d['items'] if i['content']['type']=='group' and i['name']=='same');self.assertEqual(inner['parent'],outer['id']);self.assertFalse(inner['visible'])
                child=next(i for i in d['items'] if i['content']['type']=='raster' and i['name']=='same');self.assertEqual(child['parent'],inner['id']);self.assertEqual(child['content']['rgba_hex'],'11dd6700be1f4f80');outputs.append(self.pixels(d))
        self.assertEqual(len(set(outputs)),1)
    def test_empty_folders_decode_zero_sample_channels_without_panics(self):
        for compression in range(4):
            for version in [1,2]:
                for channels in [[],[-1,0,1,2],[0,1,2]]:
                    records=[marker(3,channel_ids=channels),marker(1,'empty',channel_ids=channels)]
                    r=self.read(f.make(records,compression=compression,version=version),color_policy='assume_srgb');self.assertEqual(len(r['document']['items']),1);self.assertEqual(self.pixels(r['document']),'00000000'*48)

    def test_pixel_and_isolated_group_blends_preserve_channels_structure_and_composition(self):
        capability = capabilities()['layered_interchange']
        self.assertEqual(capability['pixel_blend_modes'], ['normal', *BLENDS])
        self.assertEqual(capability['groups']['modes'], ['normal_isolated','normal_pass_through',
                                                       *(mode+'_isolated' for mode in BLENDS)])
        for version in (1, 2):
            for mode, key in BLENDS.items():
                for grouped in (False, True):
                    with self.subTest(version=version, mode=mode, grouped=grouped):
                        layers = blended_sheet(mode, grouped)
                        if grouped:
                            layers[-1]['extra'] += f.tag(b'iOpa',bytes([63,0,0,0]))
                        raw = f.make(layers, w=4, h=1, version=version)
                        doc = self.read(raw, color_policy='assume_srgb')['document']
                        target = doc['items'][-1]
                        self.assertEqual(target['blend'], mode)
                        if grouped:
                            self.assertTrue(target['content']['isolated'])
                            self.assertEqual(doc['items'][2]['parent'], target['id'])
                            self.assertEqual(doc['items'][2]['blend'], 'screen')
                        pixels = bytes.fromhex(self.pixels(doc))
                        oracle = expected_strip(mode, grouped, fill=63)
                        self.assertLessEqual(max(abs(a-b) for a,b in zip(pixels, oracle, strict=True)), 1)
                        encoded = base64.b64decode(self.export(doc,version)['data'])
                        parsed = f.parse(encoded)
                        self.assertEqual(parsed['layers'][-1]['blend'], key)
                        if grouped:
                            self.assertEqual(parsed['layers'][-1]['tags'][b'lsct'], f.U32(1)+b'8BIM'+key)
                            self.assertEqual(parsed['layers'][1]['blend'], b'norm')
                            self.assertEqual(parsed['layers'][1]['tags'][b'iOpa'][0], 255)
                            self.assertEqual(parsed['layers'][-1]['tags'][b'iOpa'][0], 63)
                            self.assertEqual(parsed['layers'][-1]['opacity'], 173)
                        self.assertEqual([r['rgba'] for r in parsed['layers'] if r['rgba']],
                                         [BACK,FIRST,SECOND] if grouped else [BACK,FIRST])
                        again = self.read(encoded)['document']
                        self.assertEqual(self.pixels(again), pixels.hex())
                        self.assertEqual(again['items'][-1]['blend'], mode)

    def test_pass_through_folder_fill_preserves_pixels_and_editable_controls(self):
        for version in (1, 2):
            for fill, upper_mode in [(128,'normal'), (0,'screen'), (128,'screen')]:
                with self.subTest(version=version, fill=fill, upper_mode=upper_mode):
                    layers = blended_sheet('multiply', True)
                    layers[-2]['blend'] = b'norm' if upper_mode == 'normal' else b'scrn'
                    folder = marker(1, 'folder', mode=b'pass', opacity=173)
                    folder['extra'] += f.tag(b'iOpa', bytes([fill,0,0,0]))
                    layers[-1] = folder
                    # Non-normal children can blend against their own isolated
                    # group while the outer pass-through group stays editable.
                    if fill and upper_mode == 'screen':
                        layers.insert(2, marker(3))
                        layers.insert(-1, marker(1, 'inner'))
                    source = f.make(layers, w=4, h=1, version=version)
                    doc = self.read(source, color_policy='assume_srgb')['document']
                    expected = expected_strip('normal', True, fill, upper_mode)
                    actual = bytes.fromhex(self.pixels(doc))
                    self.assertLessEqual(max(abs(a-b) for a,b in zip(actual,expected,strict=True)), 1)
                    encoded = base64.b64decode(self.export(doc, version)['data'])
                    records = f.parse(encoded)['layers']
                    self.assertEqual([layer['rgba'] for layer in records if layer['rgba']], [BACK,FIRST,SECOND])
                    outer = self.read(encoded)['document']['items'][-1]
                    self.assertFalse(outer['content']['isolated'])
                    self.assertEqual((outer['opacity'],outer['fill_opacity']), (173/255,fill/255))

    def test_intermediate_pass_through_fill_rejects_backdrop_blend_in_file_and_edit(self):
        layers = blended_sheet('multiply', True)
        layers[-1] = marker(1, 'outer', mode=b'pass')
        full = self.read(f.make(layers,w=4,h=1), color_policy='assume_srgb')['document']
        group = full['items'][-1]
        operation = dict(op='properties', id=group['id'], fill_opacity=128/255)
        error = self.invoke(dict(command='document.edit', document=full, expected_revision=full['revision'], operations=[operation]),1)
        self.assertEqual(error['code'],'UNSUPPORTED')
        self.assertIn('backdrop', error['message'])
        layers[-1]['extra'] += f.tag(b'iOpa', bytes([128,0,0,0]))
        error = self.read(f.make(layers,w=4,h=1),1,color_policy='assume_srgb')
        self.assertEqual(error['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        self.assertIn('backdrop', error['message'])

    def test_folder_blend_header_fallback_and_conflicting_or_unknown_modes(self):
        for header, divider in [(b'mul ', f.U32(2)), (b'norm',f.U32(2)+b'8BIMmul '),
                                (b'mul ',f.U32(2)+b'8BIMmul ')]:
            folder = marker(2, blend=header)
            folder['extra'] = f.tag(b'lsct',divider)
            doc = self.read(f.make([marker(3),pixel(),folder]),color_policy='assume_srgb')['document']
            self.assertEqual(doc['items'][-1]['blend'],'multiply')
        for folder in [marker(1,blend=b'scrn',mode=b'mul '),marker(1,blend=b'pass',mode=b'mul ')]:
            error = self.read(f.make([marker(3),folder]),1,color_policy='assume_srgb')
            self.assertEqual(error['code'],'INVALID_LAYERED_FILE')
    def test_unbalanced_markers_unknown_modes_nonpixel_samples_and_subtypes_fail(self):
        for records in [[marker(3)],[marker(1)],[marker(1),marker(3)],[marker(3),marker(3),marker(1)]]:
            self.assertEqual(self.read(f.make(records),1,color_policy='assume_srgb')['code'],'INVALID_LAYERED_FILE')
        for extra in [f.U32(4),f.U32(1)+b'8BIMvLit',f.U32(1)+b'8BIMnorm'+f.U32(1)]:
            folder=marker(1);folder['extra']=f.tag(b'lsct',extra);self.assertEqual(self.read(f.make([marker(3),folder]),1,color_policy='assume_srgb')['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        for extra in [b'',b'\0'*5,f.U32(1)+b'BAD!norm']:
            folder=marker(1);folder['extra']=f.tag(b'lsct',extra);self.assertEqual(self.read(f.make([marker(3),folder]),1,color_policy='assume_srgb')['code'],'INVALID_LAYERED_FILE')
        for folder in [dict(marker(1),width=1,height=1,rgba=[1,2,3,4]),dict(marker(1),mask=bytes(17)+b'\4\0\0')]:
            self.assertEqual(self.read(f.make([marker(3),folder]),1,color_policy='assume_srgb')['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        boundary=marker(3)
        boundary['extra']+=f.tag(b'iOpa',b'\x80\0\0\0')
        self.assertEqual(self.read(f.make([boundary,marker(1)]),1,color_policy='assume_srgb')['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        bad=marker(1,channel_data=[b'\0\0x']*4);self.assertEqual(self.read(f.make([marker(3),bad]),1,color_policy='assume_srgb')['code'],'INVALID_LAYERED_FILE')
    def test_folder_record_budget_is_separate_from_editable_items_and_depth(self):
        cap = capabilities()['layered_interchange']
        maximum = cap['maximum_layers']
        records=[r for i in range(maximum) for r in [marker(3,id=0),marker(1,str(i),id=i+1)]]
        r=self.read(f.make(records),color_policy='assume_srgb');self.assertEqual((r['layers'],r['serialized_records']),(maximum,cap['groups']['serialized_records']))
        self.assertEqual(self.read(f.make(records+[pixel(id=5000)]),1,color_policy='assume_srgb')['code'],'RESOURCE_LIMIT')
        self.assertEqual(self.read(f.make([pixel(id=i+1) for i in range(maximum+1)]),1,color_policy='assume_srgb')['code'],'RESOURCE_LIMIT')
        maximum_depth = cap['groups']['ancestor_levels']
        for depth,wanted in [(maximum_depth,0),(maximum_depth+1,1)]:
            records=[marker(3) for _ in range(depth)]+[pixel()]+[marker(1,str(i)) for i in range(depth)]
            r=self.read(f.make(records),wanted,color_policy='assume_srgb')
            if wanted:self.assertEqual(r['code'],'RESOURCE_LIMIT')
        self.assertEqual(self.read(f.make([marker(3,id=9),pixel(id=1),marker(1,id=1)]),1,color_policy='assume_srgb')['code'],'INVALID_LAYERED_FILE')

    def test_folder_opacity_visibility_and_transform_losses_are_explicit(self):
        d=self.scene()
        for visible in [True,False]:
            for opacity in [0,64/255,1]:
                d['items'][1].update(visible=visible,opacity=opacity);encoded=base64.b64decode(self.export(d)['data']);self.assertEqual(self.pixels(self.read(encoded)['document']),self.pixels(d))
        for change in [dict(fill_opacity=.5,content=dict(type='group',isolated=True)),dict(blend='vivid_light',content=dict(type='group',isolated=True)),dict(transform=[1,0,0,1,.5,0]),dict(transform=[2,0,0,1,0,0]),dict(content=dict(type='group',knockout=True)),dict(content=dict(type='group',role='layer'))]:
            bad=copy.deepcopy(d);bad['items'][1].update(change);self.assertEqual(self.export(bad,expected=1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
    def test_nonpixel_flags_and_ordinary_channel_validation_are_not_weakened(self):
        for minimum in [70,80]:
            self.assertIn('lyvr:minimum_reader_'+str(minimum),self.read(f.make([pixel(extra=f.tag(b'lyvr',f.U32(minimum)))]),color_policy='assume_srgb')['omitted_nonappearance_records'])
        for minimum in [0,69,81,130,2**32-1]:
            self.assertEqual(self.read(f.make([pixel(extra=f.tag(b'lyvr',f.U32(minimum)))]),1,color_policy='assume_srgb')['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        compatibility = f.tag(b'lyvr',f.U32(130))
        folder = marker(1)
        folder['extra'] = compatibility + folder['extra']
        self.assertIn('lyvr:minimum_reader_130',self.read(f.make([marker(3),folder]),color_policy='assume_srgb')['omitted_nonappearance_records'])
        boundary = marker(3)
        boundary['extra'] += compatibility
        self.assertEqual(self.read(f.make([boundary,marker(1)]),1,color_policy='assume_srgb')['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        for channel_ids in [[],[0],[0,1],[-1,0,1]]:
            self.assertEqual(self.read(f.make([pixel(channel_ids=channel_ids)]),1,color_policy='assume_srgb')['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        for change in [dict(flags=24),dict(blend=b'pass'),dict(width=0,height=0,rgba=[])]:
            self.assertEqual(self.read(f.make([dict(pixel(),**change)]),1,color_policy='assume_srgb')['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
    def test_durable_group_import_edit_publication_and_history_preserve_source(self):
        d=self.scene()
        next(i for i in d['items'] if i['id']=='inner')['blend']='multiply'
        encoded=base64.b64decode(self.export(d,2)['data'])
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'original.psb';source.write_bytes(encoded);c=Client();c.initialize();s=dict(session_root=root,session_id='folders')
            try:
                capabilities=c.success('capabilities')['layered_interchange'];self.assertEqual(capabilities['groups']['serialized_records'],512);self.assertIn('empty_name_source_ids',capabilities['empty_layer_names'])
                imported=c.success('layered.import',source_path=str(source),id='folders',expected_sha256=hashlib.sha256(encoded).hexdigest())['document'];g=next(i['id'] for i in imported['items'] if i['name']=='inner')
                c.success('session.create',**s,request_id='create',document=imported);edit=dict(expected_revision=0,request_id='blend',action=dict(type='edit',operations=[dict(op='properties',id=g,blend='screen',fill_opacity=63/255)]));changed=c.success('session.apply',**s,**edit)
                c.success('session.publish',**s,expected_revision=1,output=dict(output_root=root,file_name='edited.psb',format='layered_large'));reopened=c.success('layered.import',source_path=str(Path(root)/'edited.psb'),id='reopened')['document'];self.assertEqual(tree(reopened),tree(changed['document']))
                folder = next(i for i in reopened['items'] if i['name']=='inner')
                self.assertEqual((folder['blend'],folder['fill_opacity'],folder['opacity']),('screen',63/255,128/255))
                undo=c.success('session.apply',**s,expected_revision=1,request_id='undo',action=dict(type='undo'));self.assertEqual(self.pixels(undo['document']),self.pixels(imported));self.assertTrue(c.success('session.apply',**s,**edit)['replayed']);self.assertTrue(c.success('session.verify',**s)['valid']);self.assertEqual(source.read_bytes(),encoded)
                self.assertEqual(next(i for i in undo['document']['items'] if i['id']==g)['blend'],'multiply')
            finally:c.close()

if __name__=='__main__':unittest.main()
