"""Original folder grammar, independent records, pixels and durable workflows."""
import base64,copy,hashlib,tempfile,unittest
from pathlib import Path
import layered_fixtures as f
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
    def test_unbalanced_markers_unknown_modes_nonpixel_samples_and_subtypes_fail(self):
        for records in [[marker(3)],[marker(1)],[marker(1),marker(3)],[marker(3),marker(3),marker(1)]]:
            self.assertEqual(self.read(f.make(records),1,color_policy='assume_srgb')['code'],'INVALID_LAYERED_FILE')
        for extra in [f.U32(4),f.U32(1)+b'8BIMmul ',f.U32(1)+b'8BIMnorm'+f.U32(1)]:
            folder=marker(1);folder['extra']=f.tag(b'lsct',extra);self.assertEqual(self.read(f.make([marker(3),folder]),1,color_policy='assume_srgb')['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        for extra in [b'',b'\0'*5,f.U32(1)+b'BAD!norm']:
            folder=marker(1);folder['extra']=f.tag(b'lsct',extra);self.assertEqual(self.read(f.make([marker(3),folder]),1,color_policy='assume_srgb')['code'],'INVALID_LAYERED_FILE')
        for folder in [dict(marker(1),width=1,height=1,rgba=[1,2,3,4]),dict(marker(1),mask=bytes(17)+b'\4\0\0'),dict(marker(1),extra=marker(1)['extra']+f.tag(b'iOpa',b'\x80\0\0\0'))]:
            self.assertEqual(self.read(f.make([marker(3),folder]),1,color_policy='assume_srgb')['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        bad=marker(1,channel_data=[b'\0\0x']*4);self.assertEqual(self.read(f.make([marker(3),bad]),1,color_policy='assume_srgb')['code'],'INVALID_LAYERED_FILE')
    def test_folder_record_budget_is_separate_from_editable_items_and_depth(self):
        records=[r for i in range(256) for r in [marker(3,id=0),marker(1,str(i),id=i+1)]]
        r=self.read(f.make(records),color_policy='assume_srgb');self.assertEqual((r['layers'],r['serialized_records']),(256,512))
        self.assertEqual(self.read(f.make(records+[pixel(id=5000)]),1,color_policy='assume_srgb')['code'],'RESOURCE_LIMIT')
        self.assertEqual(self.read(f.make([pixel(id=i+1) for i in range(257)]),1,color_policy='assume_srgb')['code'],'RESOURCE_LIMIT')
        for depth,wanted in [(16,0),(17,1)]:
            records=[marker(3) for _ in range(depth)]+[pixel()]+[marker(1,str(i)) for i in range(depth)]
            r=self.read(f.make(records),wanted,color_policy='assume_srgb')
            if wanted:self.assertEqual(r['code'],'RESOURCE_LIMIT')
        self.assertEqual(self.read(f.make([marker(3,id=9),pixel(id=1),marker(1,id=1)]),1,color_policy='assume_srgb')['code'],'INVALID_LAYERED_FILE')
    def test_folder_opacity_visibility_and_transform_losses_are_explicit(self):
        d=self.scene()
        for visible in [True,False]:
            for opacity in [0,64/255,1]:
                d['items'][1].update(visible=visible,opacity=opacity);encoded=base64.b64decode(self.export(d)['data']);self.assertEqual(self.pixels(self.read(encoded)['document']),self.pixels(d))
        for change in [dict(fill_opacity=.5,content=dict(type='group',isolated=True)),dict(blend='multiply',content=dict(type='group',isolated=True)),dict(transform=[1,0,0,1,.5,0]),dict(transform=[2,0,0,1,0,0]),dict(content=dict(type='group',knockout=True)),dict(content=dict(type='group',role='layer'))]:
            bad=copy.deepcopy(d);bad['items'][1].update(change);self.assertEqual(self.export(bad,expected=1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
    def test_nonpixel_flags_and_ordinary_channel_validation_are_not_weakened(self):
        for minimum in [70,80]:
            self.assertIn('lyvr:minimum_reader_'+str(minimum),self.read(f.make([pixel(extra=f.tag(b'lyvr',f.U32(minimum)))]),color_policy='assume_srgb')['omitted_nonappearance_records'])
        for minimum in [0,69,81,2**32-1]:
            self.assertEqual(self.read(f.make([pixel(extra=f.tag(b'lyvr',f.U32(minimum)))]),1,color_policy='assume_srgb')['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        for channel_ids in [[],[0],[0,1],[-1,0,1]]:
            self.assertEqual(self.read(f.make([pixel(channel_ids=channel_ids)]),1,color_policy='assume_srgb')['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        for change in [dict(flags=24),dict(blend=b'pass'),dict(width=0,height=0,rgba=[])]:
            self.assertEqual(self.read(f.make([dict(pixel(),**change)]),1,color_policy='assume_srgb')['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
    def test_durable_group_import_edit_publication_and_history_preserve_source(self):
        d=self.scene();encoded=base64.b64decode(self.export(d,2)['data'])
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'original.psb';source.write_bytes(encoded);c=Client();c.initialize();s=dict(session_root=root,session_id='folders')
            try:
                capabilities=c.success('capabilities')['layered_interchange'];self.assertEqual(capabilities['groups']['modes'],['normal_isolated','normal_pass_through']);self.assertEqual(capabilities['groups']['serialized_records'],512);self.assertIn('empty_name_source_ids',capabilities['empty_layer_names'])
                imported=c.success('layered.import',source_path=str(source),id='folders',expected_sha256=hashlib.sha256(encoded).hexdigest())['document'];g=next(i['id'] for i in imported['items'] if i['name']=='inner')
                c.success('session.create',**s,request_id='create',document=imported);edit=dict(expected_revision=0,request_id='hide',action=dict(type='edit',operations=[dict(op='properties',id=g,visible=False)]));changed=c.success('session.apply',**s,**edit)
                c.success('session.publish',**s,expected_revision=1,output=dict(output_root=root,file_name='edited.psb',format='layered_large'));reopened=c.success('layered.import',source_path=str(Path(root)/'edited.psb'),id='reopened')['document'];self.assertEqual(tree(reopened),tree(changed['document']))
                undo=c.success('session.apply',**s,expected_revision=1,request_id='undo',action=dict(type='undo'));self.assertEqual(self.pixels(undo['document']),self.pixels(imported));self.assertTrue(c.success('session.apply',**s,**edit)['replayed']);self.assertTrue(c.success('session.verify',**s)['valid']);self.assertEqual(source.read_bytes(),encoded)
            finally:c.close()

if __name__=='__main__':unittest.main()
