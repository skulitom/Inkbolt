"""Independent layout records, sparse caches and strict conversion boundaries."""
import copy, hashlib, json, tempfile, unittest
from pathlib import Path
import layered_editable_text_fixtures as p
import test_layered_annotation_controls_cli as a
import test_layered_paragraph_cli as para
import test_layered_style_cli as s
from test_mcp import Client


CHARACTERS = {
    '43':('split_annotation_scale',{'0':.625}),
    '46':('split_annotation_alignment_code',3),
    '61':('stroke_cap_code',2),
    '62':('stroke_join_code',1),
    '66':('stroke_dash_pattern',[1.25,2.75,4.0]),
    '69':('direction_override_code',2),
    '71':('mark_position_code',3),
    '77':('fill_visible',False),
    '78':('stroke_visible',True),
}
PARAGRAPHS = {
    '14':('hyphenation_zone',18.75),
    '16':('hyphenation_preference',.375),
    '20':('single_word_justification_code',1),
    '22':('automatic_inline_grouping_code',3),
    '23':('keep_lines_together',False),
    '26':('repeated_character_processing',True),
    '31':('default_tab_width',42.5),
    '34':('justification_method_code',4),
}


class LayoutControlTests(unittest.TestCase):
    invoke=s.LayeredStyleTests.invoke
    read=s.LayeredStyleTests.read
    load=s.LayeredStyleTests.load
    controls=s.LayeredStyleTests.controls

    def test_character_controls_are_sparse_value_bound_and_global_only(self):
        g,local=s.inputs();base=self.controls(g,local)['global']
        for key,(name,value) in CHARACTERS.items():
            changed=copy.deepcopy(g);s.gp(changed)[key]=value
            report=self.controls(changed,local)
            self.assertEqual(report['comparison']['missing_local_controls'],[name])
            self.assertNotIn(name,base['observed_controls']);self.assertIn(name,report['global']['observed_controls'])
            self.assertEqual(report['global']['unmapped_field_count'],0)
            self.assertNotEqual(base['run_controls_sha256'],report['global']['run_controls_sha256'])
            self.assertFalse(report['complete_style_semantics_validated']);self.assertFalse(report['rendering_equivalence_validated'])
        # Codes remain raw source codes, including values with no engine mapping.
        s.gp(g)['69']=901;one=self.controls(g,local);s.gp(g)['69']=902
        self.assertNotEqual(one['global']['run_controls_sha256'],self.controls(g,local)['global']['run_controls_sha256'])

    def test_nested_scale_has_strict_framing_and_visible_unknown_fields(self):
        for bad in [.625,True,[],{}, {'0':False},{'0':'0.625'},{'0':[]},{'0':s.s.Name('scale')}]:
            g,local=s.inputs();s.gp(g)['43']=bad
            self.assertEqual(self.load(g,local)['code'],'INVALID_LAYERED_FILE')
        g,local=s.inputs();s.gp(g)['43']={'0':1}
        first=self.controls(g,local);s.gp(g)['43']={'0':1.0}
        self.assertEqual(first['global']['run_controls_sha256'],self.controls(g,local)['global']['run_controls_sha256'])
        s.gp(g)['43']['OriginalExtra']={'future':True};report=self.controls(g,local)
        self.assertEqual(report['global']['unmapped_fields'],['43/OriginalExtra'])
        self.assertEqual(first['global']['run_controls_sha256'],report['global']['run_controls_sha256'])
        self.assertFalse(report['unknown_fields_interpreted'])

    def test_dash_pattern_types_empty_order_and_exact_budget(self):
        g,local=s.inputs();s.gp(g)['66']=[];empty=self.controls(g,local)
        self.assertIn('stroke_dash_pattern',empty['global']['observed_controls'])
        s.gp(g)['66']=[-1,0,2.5];first=self.controls(g,local)
        s.gp(g)['66']=[2.5,0,-1];second=self.controls(g,local)
        self.assertNotEqual(first['global']['run_controls_sha256'],second['global']['run_controls_sha256'])
        # Numeric validity is separate from eventual dash-layout acceptance.
        s.gp(g)['66']=[1.25]*32;self.controls(g,local)
        s.gp(g)['66'].append(2.5);self.assertEqual(self.load(g,local)['code'],'RESOURCE_LIMIT')
        for bad in [0,False,{},'1 2',[1,True],[[]],[s.s.Name('dash')],['2']]:
            s.gp(g)['66']=bad;self.assertEqual(self.load(g,local)['code'],'INVALID_LAYERED_FILE')

    def test_new_scalar_types_never_coerce_flags_or_codes(self):
        for key,(_,value) in CHARACTERS.items():
            if key in ['43','66']:continue
            for bad in ([0,'false',{}] if type(value) is bool else [True,float(value),str(value)]):
                g,local=s.inputs();s.gp(g)[key]=bad
                self.assertEqual(self.load(g,local)['code'],'INVALID_LAYERED_FILE',(key,bad))

    def test_paragraph_zone_compares_unequal_partitions_and_other_values_stay_global(self):
        g,local=para.inputs(global_lengths=[4,2],local_lengths=[1,3,2])
        for i in range(2):para.gp(g,i).update({k:v for k,(_,v) in PARAGRAPHS.items()})
        for i in range(3):para.lp(local,i)['Zone']=18.75
        report=self.load(g,local)['details']['global_story']['paragraph_styles'];c=report['comparison']
        self.assertEqual(c['utf16_spans'],3);self.assertEqual(c['compared_controls'],['hyphenation_zone'])
        self.assertTrue(c['all_compared_values_match']);self.assertEqual(c['missing_local_controls'],sorted(n for k,(n,_) in PARAGRAPHS.items() if k!='14'))
        para.lp(local,1)['Zone']=9.5
        changed=self.load(g,local)['details']['global_story']['paragraph_styles']['comparison']
        self.assertEqual(changed['different_controls'],['hyphenation_zone']);self.assertEqual(changed['differing_spans'],1)
        for key in ['complete_style_semantics_validated','paragraph_boundaries_semantically_validated','missing_values_defaulted']:
            self.assertFalse(report[key])

    def test_paragraph_types_and_local_zone_validation(self):
        for key,(_,value) in PARAGRAPHS.items():
            wrong=[0,'false',{}] if type(value) is bool else [True,str(value),[]]
            if type(value) is int:wrong.append(float(value))
            for bad in wrong:
                g,local=para.inputs();para.gp(g)[key]=bad
                self.assertEqual(self.load(g,local)['code'],'INVALID_LAYERED_FILE',(key,bad))
        for bad in [False,'2',{},[]]:
            g,local=para.inputs();para.lp(local)['Zone']=bad
            self.assertEqual(self.load(g,local)['code'],'INVALID_LAYERED_FILE')

    def test_full_run_report_remains_compact_source_preserving_and_mcp_equivalent(self):
        g,local=s.inputs(text='A'*64,global_lengths=[1]*65,local_lengths=[1]*65)
        for i in range(65):s.gp(g,i).update({k:v for k,(_,v) in CHARACTERS.items()})
        raw=s.source(g,local)
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'input.psd';path.write_bytes(raw)
            args=dict(source_path=str(path),expected_sha256=hashlib.sha256(raw).hexdigest(),id='incoming',color_policy='assume_srgb')
            expected=self.invoke(dict(command='layered.import',**args),1);self.assertLess(len(json.dumps(expected).encode()),8192)
            client=Client()
            try:
                client.initialize();got=client.tool('layered.import',**args)
                self.assertEqual(got['structuredContent']['error'],expected)
            finally:client.close()
            self.assertEqual(path.read_bytes(),raw);self.assertEqual(list(Path(root).iterdir()),[path])


class LayoutAdmissionTests(unittest.TestCase):
    invoke=a.AnnotationAdmissionTests.invoke
    setUp=a.AnnotationAdmissionTests.setUp
    add_font=a.AnnotationAdmissionTests.add_font
    bindings=a.AnnotationAdmissionTests.bindings
    args=a.AnnotationAdmissionTests.args
    load=a.AnnotationAdmissionTests.load

    def test_new_recognition_keeps_unconverted_character_and_paragraph_controls_closed(self):
        self.load(p.source(g=p.global_data()))
        for fields,target in [(CHARACTERS,s.gp),(PARAGRAPHS,para.gp)]:
            for key,(_,value) in fields.items():
                for version in [1,2]:
                    g=p.global_data();target(g)[key]=value
                    error=self.load(p.source(g=g,version=version),1)
                    self.assertEqual(error['code'],'UNSUPPORTED_LAYERED_SEMANTICS',(key,version))
        for fields in [{'43':{'0':0.0}},{'66':[]},{'77':True,'78':False}]:
            g=p.global_data();s.gp(g).update(fields)
            self.assertEqual(self.load(p.source(g=g),1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')


if __name__=='__main__':unittest.main()
