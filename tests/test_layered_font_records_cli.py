"""Original font provenance records; chosen bytes remain the rendering source."""
from advertised_limits import capabilities
import base64,copy,unittest
import layered_editable_text_fixtures as p
import layered_fixtures as f
import layered_object_fixtures as objects
import test_layered_editable_text_cli as editable
from test_layered_story_cli import Name
from test_mcp import Client


def font_record(technology=1,version='Original version 42.7'):
    return {'0':{'99':Name('CoolTypeFont'),'0':{'0':p.NAME,'2':technology,'5':version}}}


def source(record=None,version=1):
    g=p.global_data();g['0']['1']['0']=[font_record() if record is None else record]
    return p.source(g=g,version=version)


class LayeredFontRecordTests(unittest.TestCase):
    invoke=editable.EditableLayeredTextTests.invoke
    setUp=editable.EditableLayeredTextTests.setUp
    add_font=editable.EditableLayeredTextTests.add_font
    bindings=editable.EditableLayeredTextTests.bindings
    args=editable.EditableLayeredTextTests.args
    load=editable.EditableLayeredTextTests.load
    pixels=editable.EditableLayeredTextTests.pixels

    def diagnostics(self,raw):
        args=self.args(raw);del args['text_fonts']
        return self.invoke(args,1)['details']['global_story']['font_records']

    def test_provenance_does_not_replace_chosen_font_or_change_pixels(self):
        plain=self.load(p.source(g=p.global_data()))['document']
        for version in [1,2]:
            for technology in [0,1]:
                r=self.load(source(font_record(technology),version));self.assertEqual(r['document'],plain)
                self.assertEqual(self.pixels(r['document']),self.pixels(plain))
                metadata=r['text'][0]['source_fonts'];self.assertTrue(metadata['all_table_records_validated'])
                self.assertFalse(metadata['source_font_file_identity_declared']);self.assertFalse(metadata['chosen_font_version_checked'])
                self.assertFalse(metadata['system_font_lookup']);self.assertFalse(metadata['technology_interpreted_as_outline_format'])
                self.assertEqual(metadata['selected_records'],[dict(index=0,face_name=p.NAME,class_declared=True,technology_code=technology,version='Original version 42.7',metadata_supported=True)])

    def test_missing_metadata_stays_absent_and_missing_bindings_keep_provenance(self):
        raw=p.source(g=p.global_data());d=self.diagnostics(raw);row=d['selected_records'][0]
        self.assertIsNone(row['technology_code']);self.assertIsNone(row['version']);self.assertFalse(row['class_declared'])
        self.assertFalse(d['all_table_records_validated'])
        args=self.args(source());args['text_fonts']['bindings'][0]['face_name']='OtherFixture-Regular'
        e=self.invoke(args,1);self.assertEqual(e['code'],'FONT_BINDING_REQUIRED')
        self.assertEqual(e['details']['source_font_records']['selected_records'][0]['version'],'Original version 42.7')
        local=p.local();local['ResourceDict']['FontSet'][0]['Name']='StaleCache-Regular'
        g=p.global_data();g['0']['1']['0']=[font_record()]
        self.assertEqual(self.load(p.source([p.layer(payload=local)],g))['text'][0]['source_fonts']['selected_records'][0]['face_name'],p.NAME)

    def test_malformed_fields_and_unknown_semantics_are_distinct(self):
        for key,values in [('2',[-1,True,0.0,'1',Name('one')]),('5',[0,False,[],Name('Version'),b'opaque',''])]:
            for value in values:
                record=font_record();record['0']['0'][key]=value
                self.assertEqual(self.load(source(record),1)['code'],'INVALID_LAYERED_FILE',(key,value))
        for value in ['CoolTypeFont',0,False]:
            record=font_record();record['0']['99']=value
            self.assertEqual(self.load(source(record),1)['code'],'INVALID_LAYERED_FILE')
        for changed in ['class','technology','outer','object','properties']:
            record=font_record()
            if changed=='class':record['0']['99']=Name('OriginalUnknownFontClass')
            elif changed=='technology':record['0']['0']['2']=19
            else:
                target={'outer':record,'object':record['0'],'properties':record['0']['0']}[changed];target['Unmapped']=False
            self.assertFalse(self.diagnostics(source(record))['selected_metadata_supported'])
            self.assertEqual(self.load(source(record),1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')

    def test_unused_records_are_validated_before_editable_admission(self):
        for fault,code in [('unknown','UNSUPPORTED_LAYERED_SEMANTICS'),('malformed','INVALID_LAYERED_FILE'),('name','UNSUPPORTED_LAYERED_SEMANTICS')]:
            g=p.global_data();extra=font_record()
            if fault=='unknown':extra['0']['0']['Unmapped']=True
            elif fault=='name':extra['0']['0']['0']='Invalid Face Name'
            else:extra['0']['0']['5']=False
            g['0']['1']['0'].append(extra);raw=p.source(g=g)
            diagnostic=self.diagnostics(raw);self.assertTrue(diagnostic['selected_metadata_supported'])
            self.assertFalse(diagnostic['all_table_records_validated']);self.assertEqual(diagnostic['font_table_records'],2)
            self.assertEqual(len(diagnostic['selected_records']),1)
            self.assertEqual(self.load(raw,1)['code'],code)

    def test_version_table_and_selected_record_budgets(self):
        cap = capabilities()['layered_interchange']['text_import']['source_fonts']
        version = cap['version_utf8_bytes']
        name = '\u00e9'*(version//2) + 'x'*(version%2)
        self.load(source(font_record(version=name)))
        self.assertEqual(self.load(source(font_record(version=name+'x')),1)['code'],'RESOURCE_LIMIT')
        g=p.global_data();g['0']['1']['0']=[{'0':{'0':{'0':p.NAME}}} for _ in range(cap['table_records'])]
        self.load(p.source(g=g));g['0']['1']['0'].append(copy.deepcopy(g['0']['1']['0'][0]))
        self.assertEqual(self.load(p.source(g=g),1)['code'],'RESOURCE_LIMIT')
        selected = cap['selected_records']
        g=p.global_data(('A'*selected,));g['0']['1']['0']=[font_record(version='Original '+str(i)) for i in range(selected+1)]
        a=g['1']['1'][0]['0'];run=a['6']['0'][0];a['6']['0']=[]
        for i in range(selected+1):
            entry=copy.deepcopy(run);entry['1']=1;entry['0']['0']['6']['0']=i;a['6']['0'].append(entry)
        self.assertEqual(self.load(p.source([p.layer('A'*selected)],g),1)['code'],'RESOURCE_LIMIT')
        a['6']['0'].pop();a['6']['0'][-1]['1']=2
        self.assertEqual(len(self.load(p.source([p.layer('A'*selected)],g))['text'][0]['source_fonts']['selected_records']),selected)

    def test_equal_face_names_keep_distinct_selected_source_versions(self):
        g=p.global_data();g['0']['1']['0']=[font_record(version='Original first'),font_record(version='Original second')]
        a=g['1']['1'][0]['0'];one=copy.deepcopy(a['6']['0'][0]);two=copy.deepcopy(one)
        one['1']=1;two['1']=2;two['0']['0']['6']['0']=1;a['6']['0']=[one,two]
        r=self.load(p.source(g=g));rows=r['text'][0]['source_fonts']['selected_records']
        self.assertEqual([(v['index'],v['version']) for v in rows],[(0,'Original first'),(1,'Original second')])
        self.assertEqual(len(r['document']['fonts']),1)

    def test_nested_sources_mcp_and_delivery_keep_chosen_editable_content(self):
        raw=source();expected=self.load(raw);client=Client()
        try:
            client.initialize();args=self.args(raw)
            self.assertEqual(client.success('layered.import',**{k:v for k,v in args.items() if k!='command'}),expected)
            cap=client.success('capabilities')['layered_interchange']['text_import']['source_fonts']
            self.assertEqual((cap['table_records'],cap['selected_records'],cap['version_utf8_bytes']),(256,8,512))
            self.assertEqual(cap['technology_codes'],[0,1])
        finally:client.close()
        nested=f.make([dict(name='Placed',width=1,height=1,rgba=[0,0,0,255],extra=objects.placement(size=(64,48),matrix=(1,0,0,1,0,0)))],w=64,h=48,global_extra=objects.global_sources([objects.entry(raw)]))
        r=self.load(nested,embedded_objects=objects.POLICY)
        self.assertEqual(r['embedded_sources'][0]['text'][0]['source_fonts'],expected['text'][0]['source_fonts'])
        self.assertEqual(self.pixels(r['document']),self.pixels(expected['document']))
        artifact=self.invoke(dict(command='document.export',document=expected['document'],format='layered_large',font_root=str(self.store),layered_options=dict(text=dict(reconstruction='native_layout',shape_owner='OriginalGeometry'))))
        reopened=self.load(base64.b64decode(artifact['data']))['document']
        self.assertEqual(reopened['items'][0]['content']['frame'],expected['document']['items'][0]['content']['frame'])
        self.assertEqual(self.pixels(reopened),self.pixels(expected['document']))


if __name__=='__main__':unittest.main()
