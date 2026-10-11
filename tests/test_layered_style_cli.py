"""Original character controls, stale caches and independently partitioned runs."""
import copy, hashlib, json, tempfile, unittest
from pathlib import Path
import layered_fixtures as f
import layered_text_fixtures as t
import test_layered_story_cli as s
import test_layered_cli as core
from test_mcp import Client


def inputs(text='A\U0001f600B', global_lengths=None, local_lengths=None):
    g=s.global_data(text);g['1']['1']=[s.story(text,global_lengths)]
    local=t.payload(text,local_lengths)
    # The two independent tables deliberately use different numeric indices.
    g['0']['1']['0'][0]['0']['0']['0']='OriginalFixture-Second'
    for run in local['EngineDict']['StyleRun']['RunArray']:
        run['StyleSheet']['StyleSheetData']['Font']=1
    return g,local


def gp(g,i=0):return g['1']['1'][0]['0']['6']['0'][i]['0']['0']['6']
def lp(local,i=0):return local['EngineDict']['StyleRun']['RunArray'][i]['StyleSheet']['StyleSheetData']


def source(g,local):
    text=local['EngineDict']['Editor']['Text'][:-1]
    raw=t.record(text,engine=t.data(local))
    layer=dict(name='Original label',width=1,height=1,rgba=[7,11,19,255],extra=f.tag(b'TySh',raw))
    return s.source(global_=g,layers=[layer])


class LayeredStyleTests(unittest.TestCase):
    invoke=core.LayeredTests.invoke
    read=core.LayeredTests.read

    def load(self,g,local):return self.read(source(g,local),1,color_policy='assume_srgb')
    def controls(self,g,local):return self.load(g,local)['details']['global_story']['character_styles']

    def test_resolved_names_numeric_normalization_and_unequal_partitions(self):
        g,local=inputs(global_lengths=[1,4],local_lengths=[3,2])
        for r in range(2):
            gp(g,r).update({'1':17,'6':1.25,'7':.75,'8':-35,'9':2.5,'12':2})
            lp(local,r).update(FontSize=17.0,HorizontalScale=1.25,VerticalScale=.75,Tracking=-35,BaselineShift=2.5,FontCaps=2)
        v=self.controls(g,local);c=v['comparison']
        self.assertTrue(c['performed']);self.assertEqual(c['utf16_spans'],3)
        self.assertTrue(c['all_compared_values_match']);self.assertTrue(c['all_observed_controls_present_on_both_sides'])
        self.assertIn('font_face_name',c['compared_controls']);self.assertEqual(c['differing_spans'],0)
        # The fingerprints bind run boundaries as well as the known values.
        self.assertNotEqual(v['global']['run_controls_sha256'],v['local']['run_controls_sha256'])
        for key in ['complete_style_semantics_validated','font_file_identity_validated','missing_values_defaulted','unknown_fields_interpreted','rendering_equivalence_validated']:
            self.assertFalse(v[key])

    def test_conflicts_are_counted_over_actual_utf16_overlaps(self):
        g,local=inputs(global_lengths=[1,2,2],local_lengths=[3,2])
        for i in range(3):gp(g,i).update({'1':12,'2':False})
        for i in range(2):lp(local,i).update(FontSize=12,FauxBold=False)
        gp(g,1)['1']=19;lp(local,1)['FauxBold']=True
        c=self.controls(g,local)['comparison']
        self.assertEqual(c['different_controls'],['faux_bold','size']);self.assertEqual(c['differing_spans'],2)
        self.assertFalse(c['all_compared_values_match']);self.assertTrue(c['all_observed_controls_present_on_both_sides'])
        g['0']['1']['0'][0]['0']['0']['0']='OriginalDifferent-Regular'
        c=self.controls(g,local)['comparison'];self.assertIn('font_face_name',c['different_controls']);self.assertEqual(c['differing_spans'],3)

    def test_missing_fields_and_global_only_features_are_never_defaulted(self):
        g,local=inputs();gp(g).update({'18':False,'19':True,'20':False,'23':True,'24':True,'25':True,'26':True,'27':True,'28':True,'29':True,'75':True,'31':True,'32':True,'33':True,'52':False})
        lp(local).update(Ligatures=False,DLigatures=True,FontSize=11,NoBreak=False)
        v=self.controls(g,local);c=v['comparison']
        expected=['connection_forms','contextual_ligatures','fractions','italics','justification_alternates','kana','ordinals','ornaments','proportional_metrics','stylistic_alternates','swash','titling']
        self.assertEqual(c['missing_local_controls'],expected);self.assertEqual(c['missing_global_controls'],['size'])
        self.assertFalse(c['all_observed_controls_present_on_both_sides']);self.assertTrue(c['all_compared_values_match'])
        self.assertIn('fractions',v['global']['enabled_boolean_controls']);self.assertNotIn('contextual_ligatures',v['global']['enabled_boolean_controls'])
        self.assertIn('contextual_ligatures',v['global']['observed_controls']);self.assertNotIn('fractions',v['local']['observed_controls'])

    def test_comparison_is_not_attempted_when_authoritative_characters_differ(self):
        g,local=inputs();g['1']['1'][0]['0']['0']='B\U0001f600A\r';gp(g)['1']=19;lp(local)['FontSize']=12
        v=self.controls(g,local);self.assertEqual(v['comparison'],dict(performed=False,reason='source_text_differs'))
        self.assertIn('size',v['global']['observed_controls']);self.assertIn('size',v['local']['observed_controls'])
        self.assertFalse(self.load(g,local)['details']['global_story']['local_style_consistency_validated'])

    def test_known_controls_reject_wrong_types_without_coercion_or_inheritance(self):
        for global_key,local_key,bad_values in [('1','FontSize',[True,'12',[],{}]),('2','FauxBold',[0,1.0,'false',[],{}]),('8','Tracking',[True,1.5,1.0,'2',[],{}]),('12','FontCaps',[False,2.0,'2'])]:
            for value in bad_values:
                for side in ['global','local']:
                    g,local=inputs()
                    if side=='global':gp(g)[global_key]=value
                    else:lp(local)[local_key]=value
                    self.assertEqual(self.load(g,local)['code'],'INVALID_LAYERED_FILE',(global_key,value,side))
        for value in [s.Name('true'),b'true']:
            g,local=inputs();gp(g)['20']=value
            self.assertEqual(self.load(g,local)['code'],'INVALID_LAYERED_FILE')
        g,local=inputs();del lp(local)['Font']
        self.assertEqual(self.load(g,local)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')

    def test_unmapped_fields_are_visible_bounded_and_never_interpreted(self):
        g,local=inputs()
        for i in range(40):gp(g)[f'Original{i:02}']={'unknown':[True,False]};lp(local)[f'Original{i:02}']={'unknown':[1,2]}
        error=self.load(g,local);v=error['details']['global_story']['character_styles']
        for side in ['global','local']:
            self.assertEqual(v[side]['unmapped_field_count'],40);self.assertEqual(len(v[side]['unmapped_fields']),16)
            self.assertTrue(v[side]['unmapped_fields_truncated'])
        self.assertFalse(v['unknown_fields_interpreted']);self.assertFalse(v['complete_style_semantics_validated'])
        self.assertLess(len(json.dumps(error).encode()),8192)

    def test_run_fingerprints_bind_values_boundaries_but_not_unknown_semantics(self):
        g,local=inputs();gp(g)['1']=12;lp(local)['FontSize']=12.0
        a=self.controls(g,local);self.assertEqual(a['global']['run_controls_sha256'],a['local']['run_controls_sha256'])
        gp(g)['1']=13;b=self.controls(g,local);self.assertNotEqual(a['global']['run_controls_sha256'],b['global']['run_controls_sha256'])
        gp(g)['UnknownOriginal']=True;c=self.controls(g,local)
        self.assertEqual(b['global']['run_controls_sha256'],c['global']['run_controls_sha256'])
        self.assertEqual(c['global']['unmapped_fields'],['UnknownOriginal'])
        # The complete global-data identity still binds unknown values.
        before=self.load(g,local)['details']['global_story']['global_data_sha256'];gp(g)['UnknownOriginal']=False
        self.assertNotEqual(before,self.load(g,local)['details']['global_story']['global_data_sha256'])

    def test_cli_mcp_parity_source_integrity_and_compact_maximum_run_report(self):
        g,local=inputs(text='A'*64,global_lengths=[1]*65,local_lengths=[1]*65)
        for i in range(65):gp(g,i)['1']=i+1;lp(local,i)['FontSize']=i+2
        raw=source(g,local)
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'original.psd';p.write_bytes(raw)
            args=dict(source_path=str(p),expected_sha256=hashlib.sha256(raw).hexdigest(),id='incoming',color_policy='assume_srgb')
            expected=self.invoke(dict(command='layered.import',**args),1)
            self.assertEqual(expected['code'],'UNSUPPORTED_LAYERED_SEMANTICS');self.assertLess(len(json.dumps(expected).encode()),8192)
            v=expected['details']['global_story']['character_styles'];self.assertEqual(v['comparison']['differing_spans'],65)
            client=Client()
            try:
                client.initialize();got=client.tool('layered.import',**args)
                self.assertTrue(got['isError']);self.assertEqual(got['structuredContent']['error'],expected)
                self.assertEqual(client.tool('layered.import',**args,control=dict(timeout_ms=0))['structuredContent']['error']['code'],'TIMEOUT')
            finally:client.close()
            self.assertEqual(p.read_bytes(),raw);self.assertEqual(list(Path(root).iterdir()),[p])


if __name__=='__main__':unittest.main()
