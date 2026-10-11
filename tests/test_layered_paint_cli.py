"""Original color components and non-equivalent legacy text-control encodings."""
import copy, hashlib, json, tempfile, unittest
from pathlib import Path
import test_layered_style_cli as c
import test_layered_story_cli as s
import layered_text_fixtures as t
import test_layered_cli as core
from test_mcp import Client


def paint(values):return {'99':s.Name('SimplePaint'),'0':{'0':1,'1':copy.deepcopy(values)}}
def color(values):return dict(Type=1,Values=copy.deepcopy(values))


class LayeredPaintTests(unittest.TestCase):
    invoke=core.LayeredTests.invoke
    read=core.LayeredTests.read
    def load(self,g,local):return self.read(c.source(g,local),1,color_policy='assume_srgb')
    def controls(self,g,local):return self.load(g,local)['details']['global_story']['character_styles']

    def test_color_components_normalize_numbers_and_compare_intersecting_runs(self):
        g,local=c.inputs(global_lengths=[1,2,2],local_lengths=[3,2])
        for i in range(3):c.gp(g,i).update({'53':paint([1,.25,.5,.75]),'54':paint([1,0,0,0])})
        for i in range(2):c.lp(local,i).update(FillColor=color([1.,.25,.5,.75]),StrokeColor=color([1.,0.,0.,0.]))
        a=self.controls(g,local);self.assertTrue(a['comparison']['all_compared_values_match'])
        self.assertTrue(a['comparison']['all_observed_controls_present_on_both_sides'])
        self.assertEqual(a['global']['unmapped_field_count'],0)
        c.gp(g,1)['53']['0']['1'][2]=.6;c.lp(local,1)['StrokeColor']['Values'][1]=.8
        b=self.controls(g,local);comp=b['comparison']
        self.assertEqual(comp['utf16_spans'],3);self.assertEqual(comp['differing_spans'],2)
        self.assertEqual(comp['different_controls'],['fill_color','stroke_color'])
        self.assertNotEqual(a['global']['run_controls_sha256'],b['global']['run_controls_sha256'])

    def test_fingerprint_binds_all_four_raw_components_without_clamping(self):
        g,local=c.inputs();values=[.4,-.25,1.5,2]
        c.gp(g)['53']=paint(values);c.lp(local)['FillColor']=color(values)
        v=self.controls(g,local)
        expected=[dict(end_utf16=5,controls=dict(fill_color=dict(components=[.4,-.25,1.5,2.],type=1),font_face_name='OriginalFixture-Second'))]
        sha=hashlib.sha256(json.dumps(expected,separators=(',',':')).encode()).hexdigest()
        for side in ['global','local']:self.assertEqual(v[side]['run_controls_sha256'],sha)
        c.gp(g)['53']['0']['1'][0]=.5
        self.assertEqual(self.controls(g,local)['comparison']['different_controls'],['fill_color'])
        self.assertFalse(v['rendering_equivalence_validated']);self.assertFalse(v['complete_style_semantics_validated'])

    def test_missing_paints_stay_missing_without_inheritance(self):
        g,local=c.inputs();c.gp(g)['53']=paint([1,1,0,0]);c.lp(local)['StrokeColor']=color([1,0,0,1])
        local['EngineDict']['StyleRun']['DefaultRunData']=dict(StyleSheet=dict(StyleSheetData=dict(FillColor=color([1,1,0,0]))))
        v=self.controls(g,local);comp=v['comparison']
        self.assertEqual(comp['missing_local_controls'],['fill_color']);self.assertEqual(comp['missing_global_controls'],['stroke_color'])
        self.assertFalse(v['missing_values_defaulted']);self.assertFalse(comp['all_observed_controls_present_on_both_sides'])

    def test_unknown_paint_classes_and_color_modes_remain_unmapped(self):
        g,local=c.inputs();c.gp(g)['53']={'99':s.Name('OriginalUnknownPaint'),'data':[3,5]}
        c.gp(g)['54']={'99':s.Name('SimplePaint'),'0':{'0':93,'original':True}}
        c.lp(local).update(FillColor=dict(Type=93,Original=True),StrokeColor=dict(Type=-2,Values=[1]))
        v=self.controls(g,local)
        self.assertEqual(v['global']['unmapped_fields'],['53','54']);self.assertEqual(v['local']['unmapped_fields'],['FillColor','StrokeColor'])
        for side in ['global','local']:self.assertEqual(v[side]['observed_controls'],['font_face_name'])
        self.assertFalse(v['unknown_fields_interpreted'])

    def test_nested_unknown_fields_remain_visible_and_bind_complete_data_only(self):
        g,local=c.inputs();c.gp(g)['53']=paint([1,.1,.2,.3]);c.lp(local)['FillColor']=color([1,.1,.2,.3])
        before=self.load(g,local);known=before['details']['global_story']['character_styles']['global']['run_controls_sha256']
        c.gp(g)['53']['OriginalOuter']={'flag':True};c.gp(g)['53']['0']['OriginalInner']=7;c.lp(local)['FillColor']['OriginalLocal']=[2,4]
        after=self.load(g,local);v=after['details']['global_story']['character_styles']
        self.assertEqual(v['global']['unmapped_fields'],['53/0/OriginalInner','53/OriginalOuter'])
        self.assertEqual(v['local']['unmapped_fields'],['FillColor/OriginalLocal'])
        self.assertTrue(v['comparison']['all_compared_values_match']);self.assertEqual(v['global']['run_controls_sha256'],known)
        self.assertNotEqual(before['details']['global_story']['global_data_sha256'],after['details']['global_story']['global_data_sha256'])
        for i in range(30):c.gp(g)['53']['0'][f'Original{i}']=True
        v=self.controls(g,local);self.assertEqual(v['global']['unmapped_field_count'],32);self.assertEqual(len(v['global']['unmapped_fields']),16)
        self.assertTrue(v['global']['unmapped_fields_truncated'])

    def test_known_paint_shapes_types_and_name_tokens_are_strict(self):
        for bad in [False,1,'color',[],{},dict(Type=True,Values=[1,0,0,0]),dict(Type=1.),dict(Type=1),dict(Type=1,Values=[]),dict(Type=1,Values=[1,0,0]),dict(Type=1,Values=[1,0,0,0,0]),dict(Type=1,Values=[True,0,0,0]),dict(Type=1,Values=[1,'0',0,0])]:
            g,local=c.inputs();c.lp(local)['FillColor']=bad
            self.assertEqual(self.load(g,local)['code'],'INVALID_LAYERED_FILE',bad)
        wrong=[False,[],{}, {'99':'SimplePaint'}, {'99':b'SimplePaint'}, {'99':1}, {'99':s.Name('SimplePaint')}, {'99':s.Name('SimplePaint'),'0':[]}, {'99':s.Name('SimplePaint'),'0':{'0':True}}, {'99':s.Name('SimplePaint'),'0':{'0':1.0}}]
        for values in [[],[1,0,0],[1,0,0,0,0],[1,s.Name('zero'),0,0],[1,b'zero',0,0],[1,False,0,0],[1,'0',0,0]]:wrong.append(paint(values))
        for bad in wrong:
            g,local=c.inputs();c.gp(g)['53']=bad;self.assertEqual(self.load(g,local)['code'],'INVALID_LAYERED_FILE',bad)

    def test_legacy_decoration_and_kerning_controls_are_not_equated(self):
        g,local=c.inputs();c.gp(g).update({'11':2,'13':1,'15':2,'16':1})
        c.lp(local).update(AutoKerning=True,FontBaseline=1,Strikethrough=True,Underline=True,YUnderline=1)
        v=self.controls(g,local);comp=v['comparison']
        self.assertEqual(comp['compared_controls'],['baseline_code','font_face_name']);self.assertTrue(comp['all_compared_values_match'])
        self.assertEqual(comp['missing_local_controls'],['kerning_code','strikethrough_code','underline_code'])
        self.assertEqual(comp['missing_global_controls'],['local_auto_kerning','local_strikethrough','local_underline','local_underline_position'])
        for key in ['11','15','16']:
            changed=copy.deepcopy(g);c.gp(changed)[key]=0
            self.assertNotEqual(v['global']['run_controls_sha256'],self.controls(changed,local)['global']['run_controls_sha256'])
        c.lp(local)['FontBaseline']=2;self.assertEqual(self.controls(g,local)['comparison']['different_controls'],['baseline_code'])

    def test_wrong_legacy_types_fail_and_local_validation_needs_no_global_story(self):
        for key in ['11','13','15','16']:
            for bad in [True,1.0,'1',[]]:
                g,local=c.inputs();c.gp(g)[key]=bad;self.assertEqual(self.load(g,local)['code'],'INVALID_LAYERED_FILE')
        for key,bad in [('AutoKerning',1),('FontBaseline',1.),('Strikethrough',1),('Underline',1),('YUnderline',False),('FillColor',dict(Type=1,Values=[1,0,0]))]:
            g,local=c.inputs();c.lp(local)[key]=bad
            self.assertEqual(self.read(t.source(text='A\U0001f600B',engine=t.data(local)),1,color_policy='assume_srgb')['code'],'INVALID_LAYERED_FILE')

    def test_cli_mcp_parity_source_integrity_cancellation_and_changed_text(self):
        g,local=c.inputs();c.gp(g)['53']=paint([1,.1,.2,.3]);c.lp(local)['FillColor']=color([1,.3,.2,.1])
        g['1']['1'][0]['0']['0']='B\U0001f600A\r'
        self.assertEqual(self.controls(g,local)['comparison'],dict(performed=False,reason='source_text_differs'))
        raw=c.source(g,local)
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'original.psd';p.write_bytes(raw)
            args=dict(source_path=str(p),expected_sha256=hashlib.sha256(raw).hexdigest(),id='incoming',color_policy='assume_srgb')
            expected=self.invoke(dict(command='layered.import',**args),1);self.assertEqual(expected['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
            self.assertLess(len(json.dumps(expected).encode()),8192)
            client=Client()
            try:
                client.initialize();got=client.tool('layered.import',**args)
                self.assertTrue(got['isError']);self.assertEqual(got['structuredContent']['error'],expected)
                self.assertEqual(client.tool('layered.import',**args,control=dict(timeout_ms=0))['structuredContent']['error']['code'],'TIMEOUT')
            finally:client.close()
            self.assertEqual(p.read_bytes(),raw);self.assertEqual(list(Path(root).iterdir()),[p])


if __name__=='__main__':unittest.main()
