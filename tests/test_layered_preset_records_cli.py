"""Independent preset slots, bounded source names and list control diagnostics."""
import copy,hashlib,json,tempfile,unittest
from pathlib import Path
import layered_editable_text_fixtures as p
import test_layered_annotation_controls_cli as a
import test_layered_inheritance_cli as inheritance
import test_layered_paragraph_cli as para
import test_layered_paragraph_selectors_cli as q
import test_layered_style_cli as s
from test_mcp import Client


class PresetRecordTests(unittest.TestCase):
    invoke=s.LayeredStyleTests.invoke
    read=s.LayeredStyleTests.read
    load=s.LayeredStyleTests.load
    controls=para.LayeredParagraphTests.controls

    def test_each_family_uses_record_slots_not_auxiliary_order(self):
        for key,table in q.TABLES.items():
            g,local=para.inputs();q.preset_tables(g,2);para.gp(g)[key]=0
            first=self.controls(g,local)
            g['0'][table]['1']=[{'0':1},{'0':0}]
            self.assertEqual(first,self.controls(g,local))
            g['0'][table]['0'].reverse();changed=self.controls(g,local)
            self.assertNotEqual(first['global']['run_controls_sha256'],changed['global']['run_controls_sha256'])
            record=changed['preset_records']['selected'][0]
            self.assertEqual(record['index'],0)
            self.assertEqual(record['control'],q.REFERENCES[key])
            self.assertEqual(record['name_preview'],f'OriginalPreset-{table}-1'[:16])
            self.assertTrue(changed['preset_references_resolved'])
            self.assertFalse(changed['preset_records']['definition_semantics_validated'])
            self.assertFalse(changed['preset_records']['other_records_validated'])

    def test_missing_dangling_and_malformed_selected_records_fail_without_fallback(self):
        for key,table in q.TABLES.items():
            mutations=[lambda g:g['0'].pop(table),lambda g:g['0'].__setitem__(table,[]),
                       lambda g:g['0'][table].__setitem__('0',{}),lambda g:g['0'][table].__setitem__('0',[])]
            for bad in [False,{}, {'0':False},{'0':{}},{'0':{'0':s.s.Name('name')}},{'0':{'0':b'name'}},{'0':{'0':7}}]:
                mutations.append(lambda g,bad=bad:g['0'][table].__setitem__('0',[bad]))
            for change in mutations:
                g,local=para.inputs();q.preset_tables(g);para.gp(g)[key]=0;change(g)
                self.assertEqual(self.load(g,local)['code'],'INVALID_LAYERED_FILE',(key,change))
            for bad in [1,2**63-1]:
                g,local=para.inputs();q.preset_tables(g);para.gp(g)[key]=bad
                self.assertEqual(self.load(g,local)['code'],'INVALID_LAYERED_FILE')
            g,local=para.inputs();para.gp(g)[key]=s.s.Name('nil');g['0'][table]=False
            self.assertEqual(self.controls(g,local)['preset_records']['selected_count'],0)

    def test_table_and_unicode_name_budgets_are_exact(self):
        g,local=para.inputs();q.preset_tables(g,256);para.gp(g)['36']=255
        self.assertEqual(self.controls(g,local)['preset_records']['selected'][0]['index'],255)
        g['0']['9']['0'].append({'0':{'0':'OriginalExtra'}})
        self.assertEqual(self.load(g,local)['code'],'RESOURCE_LIMIT')
        for name,valid in [('',True),('x'*128,True),('\u00e9'*64,True),('x'*129,False),('\u00e9'*65,False)]:
            g,local=para.inputs();q.preset_tables(g);para.gp(g)['27']=0;g['0']['4']['0'][0]['0']['0']=name
            if valid:
                record=self.controls(g,local)['preset_records']['selected'][0]
                self.assertEqual(record['name_utf8_bytes'],len(name.encode()))
                self.assertEqual(record['name_sha256'],hashlib.sha256(name.encode()).hexdigest())
                self.assertEqual(record['name_preview'],name[:16]);self.assertEqual(record['name_truncated'],len(name)>16)
            else:self.assertEqual(self.load(g,local)['code'],'RESOURCE_LIMIT')

    def test_names_bind_full_value_without_normalization_or_definition_claims(self):
        g,local=para.inputs(text='A');q.preset_tables(g);para.gp(g)['28']=0
        for name in ['\u00e9','e\u0301','x'*32+'A','x'*32+'B']:
            g['0']['3']['0'][0]['0']['0']=name
            report=self.controls(g,local)
            expected=q.fingerprint([dict(end_utf16=2,controls={q.REFERENCES['28']:dict(index=0,name=name)})])
            self.assertEqual(report['global']['run_controls_sha256'],expected)
        before=self.load(g,local)['details']['global_story'];g['0']['3']['0'][0]['0']['OriginalDefinition']=[1,2,3]
        g['0']['3']['0'].append(False)
        after=self.load(g,local)['details']['global_story']
        self.assertNotEqual(before['global_data_sha256'],after['global_data_sha256'])
        self.assertEqual(before['paragraph_styles'],after['paragraph_styles'])

    def test_selected_summary_deduplicates_pairs_but_not_equal_names(self):
        g,local=para.inputs(global_lengths=[4,2]);q.preset_tables(g,2)
        for table in q.TABLES.values():
            for record in g['0'][table]['0']:record['0']['0']='Original shared name'
        for i in range(2):para.gp(g,i).update({'27':0,'28':i,'36':0})
        report=self.controls(g,local)['preset_records']
        self.assertEqual(report['selected_count'],4);self.assertFalse(report['truncated'])
        self.assertEqual(len(report['selected']),4);self.assertTrue(report['names_untrusted'])
        self.assertEqual(len({r['name_sha256'] for r in report['selected']}),1)

    def test_named_source_inheritance_and_explicit_empty_override_select_actual_targets(self):
        g=inheritance.graph();q.preset_tables(g,2);local=p.local('AA')
        g['1']['3']['27']=1;g['0']['6']['0'][1]['0']['5']['27']=1
        g['0']['6']['0'][0]['0']['5']['28']=0
        report=self.controls(g,local)['preset_records']
        self.assertEqual(report['selected_count'],2)
        self.assertEqual([(r['control'],r['index']) for r in report['selected']],
                         [(q.REFERENCES['27'],1),(q.REFERENCES['28'],0)])
        g['1']['1'][0]['0']['5']['0'][0]['0']={'0':{'6':0,'5':{'27':s.s.Name('nil')}}}
        g['0']['4']=False
        report=self.controls(g,local)['preset_records']
        self.assertEqual(report['selected_count'],1)
        self.assertEqual(report['selected'][0]['control'],q.REFERENCES['28'])

    def test_list_suppression_and_restart_are_distinct_typed_source_controls(self):
        g,local=para.inputs(text='A');para.gp(g).update({'38':True,'39':7})
        report=self.controls(g,local)
        self.assertEqual(report['global']['run_controls_sha256'],q.fingerprint([dict(end_utf16=2,controls=dict(list_item_suppressed=True,list_start_number=7))]))
        self.assertEqual(report['comparison']['missing_local_controls'],['list_item_suppressed','list_start_number'])
        for key,values in [('38',[0,1,'true',[]]),('39',[True,7.0,'7',[]])]:
            for bad in values:
                changed=copy.deepcopy(g);para.gp(changed)[key]=bad
                self.assertEqual(self.load(changed,local)['code'],'INVALID_LAYERED_FILE')
        para.gp(g).update({'41':2,'47':True})
        self.assertEqual(self.controls(g,local)['global']['unmapped_fields'],['41','47'])

    def test_maximum_runs_and_untrusted_names_keep_cli_mcp_report_compact(self):
        g,local=para.inputs(text='A'*64,global_lengths=[1]*65,local_lengths=[1]*65);q.preset_tables(g,65)
        for table in q.TABLES.values():
            for record in g['0'][table]['0']:record['0']['0']='\x00'*128
        for i in range(65):para.gp(g,i).update({'27':i,'28':i,'36':i,'38':i%2==0,'39':i})
        raw=s.source(g,local)
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'original.psd';path.write_bytes(raw)
            args=dict(source_path=str(path),expected_sha256=hashlib.sha256(raw).hexdigest(),id='incoming',color_policy='assume_srgb')
            expected=self.invoke(dict(command='layered.import',**args),1);self.assertLess(len(json.dumps(expected).encode()),8192)
            report=expected['details']['global_story']['paragraph_styles']['preset_records']
            self.assertEqual(report['selected_count'],195);self.assertTrue(report['truncated']);self.assertEqual(len(report['selected']),4)
            client=Client()
            try:
                client.initialize();got=client.tool('layered.import',**args)
                self.assertEqual(got['structuredContent']['error'],expected)
            finally:client.close()
            self.assertEqual(path.read_bytes(),raw);self.assertEqual(list(Path(root).iterdir()),[path])


class PresetAdmissionTests(unittest.TestCase):
    invoke=a.AnnotationAdmissionTests.invoke
    setUp=a.AnnotationAdmissionTests.setUp
    add_font=a.AnnotationAdmissionTests.add_font
    bindings=a.AnnotationAdmissionTests.bindings
    args=a.AnnotationAdmissionTests.args
    load=a.AnnotationAdmissionTests.load

    def test_resolved_names_and_known_list_controls_do_not_admit_layout(self):
        for version in [1,2]:
            self.load(p.source(g=p.global_data(),version=version))
            for values in [{'38':False},{'38':True},{'39':0},{'39':7},{'38':True,'39':7}]:
                g=p.global_data();para.gp(g).update(values)
                self.assertEqual(self.load(p.source(g=g,version=version),1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
            for key in q.REFERENCES:
                g=p.global_data();q.preset_tables(g);para.gp(g)[key]=0
                result=self.load(p.source(g=g,version=version),1)
                self.assertEqual(result['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
                self.assertTrue(result['details']['global_story']['paragraph_styles']['preset_references_resolved'])


if __name__=='__main__':unittest.main()
