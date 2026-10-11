"""Original typed diagnostics; unconverted authoring never becomes editable."""
import copy, hashlib, json, tempfile, unittest
from pathlib import Path
import layered_editable_text_fixtures as p
import test_layered_editable_text_cli as editable
import test_layered_style_cli as s
from test_mcp import Client


# Deliberately varied original inputs, not source application defaults.
FIELDS = [
    ('10',None,'character_rotation',13.75),
    ('17',None,'underline_offset',-2.25),
    ('21',None,'legacy_alternate_ligatures',True),
    ('22',None,'legacy_old_style_figures',True),
    ('34',None,'phonetic_annotation',False),
    ('40',None,'split_annotation',True),
    ('41',None,'split_annotation_lines',4),
    ('42',None,'split_annotation_line_gap',7),
    ('44',None,'split_annotation_widow',5),
    ('45',None,'split_annotation_orphan',3),
    ('47',None,'inline_vertical_offset',-3),
    ('48',None,'inline_horizontal_offset',6),
    ('49',None,'space_before_character',.625),
    ('50',None,'space_after_character',.125),
    ('51',None,'character_cell_width',3),
    ('56','FillFlag','fill_enabled',False),
    ('57','StrokeFlag','stroke_enabled',True),
    ('58','FillFirst','fill_before_stroke',False),
    ('59',None,'fill_overprint',True),
    ('60',None,'stroke_overprint',False),
    ('63','OutlineWidth','stroke_width',2.75),
    ('64',None,'stroke_miter_limit',8.5),
    ('65',None,'stroke_dash_phase',-1.25),
]


def populate(g,local):
    for run in range(len(g['1']['1'][0]['0']['6']['0'])):
        s.gp(g,run).update({key:value for key,_,_,value in FIELDS})
    for run in range(len(local['EngineDict']['StyleRun']['RunArray'])):
        s.lp(local,run).update({key:value for _,key,_,value in FIELDS if key})


class AnnotationControlTests(unittest.TestCase):
    invoke=s.LayeredStyleTests.invoke
    read=s.LayeredStyleTests.read
    load=s.LayeredStyleTests.load
    controls=s.LayeredStyleTests.controls

    def test_partitioned_comparison_names_real_paint_cache_conflicts(self):
        g,local=s.inputs(global_lengths=[1,4],local_lengths=[3,2]);populate(g,local)
        report=self.controls(g,local);c=report['comparison']
        self.assertEqual(c['utf16_spans'],3);self.assertTrue(c['all_compared_values_match'])
        self.assertEqual(c['compared_controls'],['fill_before_stroke','fill_enabled','font_face_name','stroke_enabled','stroke_width'])
        self.assertEqual(c['missing_local_controls'],sorted(name for _,key,name,_ in FIELDS if key is None))
        self.assertEqual(report['global']['unmapped_field_count'],0);self.assertEqual(report['local']['unmapped_field_count'],0)
        self.assertIn('split_annotation',report['global']['enabled_boolean_controls'])
        self.assertNotIn('phonetic_annotation',report['global']['enabled_boolean_controls'])
        s.lp(local,1)['OutlineWidth']=4.5;s.gp(g,1)['56']=True
        changed=self.controls(g,local)['comparison']
        self.assertEqual(changed['different_controls'],['fill_enabled','stroke_width']);self.assertEqual(changed['differing_spans'],2)
        for key in ['complete_style_semantics_validated','rendering_equivalence_validated','missing_values_defaulted']:
            self.assertFalse(report[key])

    def test_sparse_controls_stay_absent_and_each_value_binds_the_fingerprint(self):
        g,local=s.inputs();baseline=self.controls(g,local)['global']
        for key,_,name,value in FIELDS:
            one=copy.deepcopy(g);s.gp(one)[key]=value
            report=self.controls(one,local)['global']
            self.assertIn(name,report['observed_controls']);self.assertNotIn(name,baseline['observed_controls'])
            self.assertNotEqual(report['run_controls_sha256'],baseline['run_controls_sha256'])
            s.gp(one)[key]=(not value) if type(value) is bool else value+1
            self.assertNotEqual(report['run_controls_sha256'],self.controls(one,local)['global']['run_controls_sha256'])
        s.gp(g).update({'22':True,'30':2,'21':True,'19':False})
        names=self.controls(g,local)['global']['observed_controls']
        for name in ['legacy_old_style_figures','figure_style_code','legacy_alternate_ligatures','discretionary_ligatures']:
            self.assertIn(name,names)

    def test_types_reject_coercion_and_unknown_fields_remain_visible(self):
        for key,local_key,_,value in FIELDS:
            wrong=[0,'true',[]] if type(value) is bool else [True,str(value),{}]
            if type(value) is int:wrong.append(float(value))
            for bad in wrong:
                g,local=s.inputs();s.gp(g)[key]=bad
                self.assertEqual(self.load(g,local)['code'],'INVALID_LAYERED_FILE',(key,bad))
                if local_key:
                    g,local=s.inputs();s.lp(local)[local_key]=bad
                    self.assertEqual(self.load(g,local)['code'],'INVALID_LAYERED_FILE',(local_key,bad))
        g,local=s.inputs();populate(g,local);s.gp(g)['OriginalUnmappedAnnotation']={'active':False}
        report=self.controls(g,local)
        self.assertEqual(report['global']['unmapped_fields'],['OriginalUnmappedAnnotation'])
        self.assertFalse(report['unknown_fields_interpreted'])

    def test_complete_report_is_compact_and_identical_over_cli_and_mcp(self):
        g,local=s.inputs(text='A'*64,global_lengths=[1]*65,local_lengths=[1]*65);populate(g,local)
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
            self.assertEqual(path.read_bytes(),raw);self.assertEqual(list(Path(root).iterdir()),[path])


class AnnotationAdmissionTests(unittest.TestCase):
    invoke=editable.EditableLayeredTextTests.invoke
    setUp=editable.EditableLayeredTextTests.setUp
    add_font=editable.EditableLayeredTextTests.add_font
    bindings=editable.EditableLayeredTextTests.bindings
    args=editable.EditableLayeredTextTests.args
    load=editable.EditableLayeredTextTests.load
    pixels=editable.EditableLayeredTextTests.pixels

    def test_recognition_does_not_admit_unconverted_global_controls(self):
        baseline=self.pixels(self.load()['document'])
        for key,_,name,value in FIELDS:
            for candidate in [value,False if type(value) is bool else 0]:
                g=p.global_data();s.gp(g)[key]=candidate
                error=self.load(p.source(g=g),1)
                self.assertEqual(error['code'],'UNSUPPORTED_LAYERED_SEMANTICS',(key,candidate))
                self.assertIn('Unconverted character controls',error['message'])
                self.assertIn(name,error['details']['global_story']['character_styles']['global']['observed_controls'])
        self.assertEqual(self.pixels(self.load()['document']),baseline)

    def test_existing_local_fill_contract_and_extra_paint_rejections(self):
        for version in [1,2]:
            self.load(p.source(version=version))
            for controls in [dict(FillFlag=False),dict(StrokeFlag=True),dict(FillFirst=True),dict(OutlineWidth=0.0)]:
                local=p.local();s.lp(local).update(controls)
                self.assertEqual(self.load(p.source([p.layer(payload=local)],version=version),1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')


if __name__=='__main__':unittest.main()
