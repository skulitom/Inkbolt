"""Typed source selectors, explicit empty references and separate cache codes."""
import copy, hashlib, json, tempfile, unittest
from pathlib import Path
import layered_editable_text_fixtures as p
import test_layered_annotation_controls_cli as a
import test_layered_paragraph_cli as para
import test_layered_style_cli as s
from test_mcp import Client


REFERENCES = {'27':'line_breaking_preset_reference',
              '28':'spacing_preset_reference','36':'list_style_reference'}
SCALARS = {'6':'drop_cap_multiplier','35':'composer_code'}
LEGACY = {'Kinsoku':'local_line_breaking_preset_code',
          'MojiKumi':'local_spacing_preset_code'}


def fingerprint(runs):
    return hashlib.sha256(json.dumps(runs,separators=(',',':')).encode()).hexdigest()


class ParagraphSelectorTests(unittest.TestCase):
    invoke=s.LayeredStyleTests.invoke
    read=s.LayeredStyleTests.read
    load=s.LayeredStyleTests.load
    controls=para.LayeredParagraphTests.controls

    def test_absent_empty_and_zero_have_independently_computed_fingerprints(self):
        for key,name in REFERENCES.items():
            g,local=para.inputs(text='AB');end=3
            absent=self.controls(g,local)
            self.assertEqual(absent['global']['run_controls_sha256'],fingerprint([dict(end_utf16=end,controls={})]))
            para.gp(g)[key]=s.s.Name('nil');empty=self.controls(g,local)
            self.assertEqual(empty['global']['run_controls_sha256'],fingerprint([dict(end_utf16=end,controls={name:None})]))
            para.gp(g)[key]=0;zero=self.controls(g,local)
            self.assertEqual(zero['global']['run_controls_sha256'],fingerprint([dict(end_utf16=end,controls={name:0})]))
            self.assertEqual(len({v['global']['run_controls_sha256'] for v in [absent,empty,zero]}),3)
            for v in [empty,zero]:
                self.assertEqual(v['global']['observed_controls'],[name])
                self.assertEqual(v['global']['unmapped_field_count'],0)
                self.assertEqual(v['comparison']['missing_local_controls'],[name])
                self.assertFalse(v['preset_references_resolved']);self.assertFalse(v['legacy_preset_conversion_validated'])
                self.assertFalse(v['missing_values_defaulted']);self.assertFalse(v['complete_style_semantics_validated'])

    def test_reference_types_never_coerce_names_text_flags_or_numbers(self):
        wrong=[True,False,-1,0.0,1.5,'nil',b'nil','0',[],{},s.s.Name('Nil'),s.s.Name('none')]
        for key in REFERENCES:
            for value in wrong:
                g,local=para.inputs();para.gp(g)[key]=value
                self.assertEqual(self.load(g,local)['code'],'INVALID_LAYERED_FILE',(key,value))

    def test_indices_remain_unresolved_without_guessing_a_table_or_default(self):
        for key,name in REFERENCES.items():
            g,local=para.inputs(text='AB')
            for index in [0,513,2**63-1]:
                para.gp(g)[key]=index;v=self.controls(g,local)
                self.assertEqual(v['global']['run_controls_sha256'],fingerprint([dict(end_utf16=3,controls={name:index})]))
                self.assertFalse(v['preset_references_resolved'])
            before=self.controls(g,local)
            # Unknown resource definitions remain bound by the complete source
            # hash, but never enter a partial known-control fingerprint.
            for table in ['3','4','9']:g['0'][table]={'OriginalFuture':True}
            self.assertEqual(before,self.controls(g,local))
            para.gp(g)['OriginalFutureSelector']=17
            self.assertEqual(self.controls(g,local)['global']['unmapped_fields'],['OriginalFutureSelector'])

    def test_source_codes_are_integers_and_preserve_uninterpreted_values(self):
        for key,name in SCALARS.items():
            for value in [True,1.0,'1',[],{},s.s.Name('nil')]:
                g,local=para.inputs();para.gp(g)[key]=value
                self.assertEqual(self.load(g,local)['code'],'INVALID_LAYERED_FILE',(key,value))
            g,local=para.inputs(text='AB');para.gp(g)[key]=-7
            v=self.controls(g,local)
            self.assertEqual(v['global']['run_controls_sha256'],fingerprint([dict(end_utf16=3,controls={name:-7})]))
            self.assertEqual(v['comparison']['missing_local_controls'],[name])

    def test_legacy_codes_do_not_compare_as_global_indices_even_when_equal(self):
        g,local=para.inputs(global_lengths=[4,2],local_lengths=[1,3,2])
        for i in range(2):para.gp(g,i).update({'27':7,'28':7})
        for i in range(3):para.lp(local,i).update(Kinsoku=7,MojiKumi=7)
        report=self.controls(g,local);c=report['comparison']
        self.assertEqual(c['utf16_spans'],3);self.assertEqual(c['compared_controls'],[])
        self.assertEqual(c['missing_global_controls'],sorted(LEGACY.values()))
        self.assertEqual(c['missing_local_controls'],sorted(REFERENCES[k] for k in ['27','28']))
        self.assertEqual(report['local']['unmapped_field_count'],0)
        self.assertFalse(report['legacy_preset_conversion_validated'])
        for key in LEGACY:
            for bad in [True,0.0,'1',[],{}]:
                changed=copy.deepcopy(local);para.lp(changed)[key]=bad
                self.assertEqual(self.load(g,changed)['code'],'INVALID_LAYERED_FILE')

    def test_all_runs_compact_mcp_equivalence_and_source_preservation(self):
        g,local=para.inputs(text='A'*64,global_lengths=[1]*65,local_lengths=[1]*65)
        for i in range(65):
            para.gp(g,i).update({'6':i,'35':i,'27':s.s.Name('nil'),'28':i,'36':64-i})
            para.lp(local,i).update(Kinsoku=i,MojiKumi=64-i)
        raw=s.source(g,local)
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'original.psd';path.write_bytes(raw)
            args=dict(source_path=str(path),expected_sha256=hashlib.sha256(raw).hexdigest(),id='incoming',color_policy='assume_srgb')
            expected=self.invoke(dict(command='layered.import',**args),1)
            self.assertLess(len(json.dumps(expected).encode()),8192)
            client=Client()
            try:
                client.initialize();got=client.tool('layered.import',**args)
                self.assertEqual(got['structuredContent']['error'],expected)
            finally:client.close()
            report=expected['details']['global_story']['paragraph_styles']
            self.assertEqual(report['comparison']['utf16_spans'],65)
            self.assertEqual(report['global']['unmapped_field_count'],0)
            self.assertEqual(path.read_bytes(),raw);self.assertEqual(list(Path(root).iterdir()),[path])


class ParagraphSelectorAdmissionTests(unittest.TestCase):
    invoke=a.AnnotationAdmissionTests.invoke
    setUp=a.AnnotationAdmissionTests.setUp
    add_font=a.AnnotationAdmissionTests.add_font
    bindings=a.AnnotationAdmissionTests.bindings
    args=a.AnnotationAdmissionTests.args
    load=a.AnnotationAdmissionTests.load

    def test_recognition_never_admits_empty_zero_or_selected_layout(self):
        for version in [1,2]:
            self.load(p.source(g=p.global_data(),version=version))
            for key in [*SCALARS,*REFERENCES]:
                for value in ([0,3,s.s.Name('nil')] if key in REFERENCES else [0,1]):
                    g=p.global_data();para.gp(g)[key]=value
                    error=self.load(p.source(g=g,version=version),1)
                    self.assertEqual(error['code'],'UNSUPPORTED_LAYERED_SEMANTICS',(version,key,value))
            for key in LEGACY:
                local=p.local();para.lp(local)[key]=0
                error=self.load(p.source([p.layer(payload=local)],version=version),1)
                self.assertEqual(error['code'],'UNSUPPORTED_LAYERED_SEMANTICS')


if __name__=='__main__':unittest.main()
