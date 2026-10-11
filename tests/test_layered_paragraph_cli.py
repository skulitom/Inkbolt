"""Original explicit paragraph controls, legacy codes and stale cache oracles."""
import copy,hashlib,json,tempfile,unittest
from pathlib import Path
import test_layered_style_cli as c
import test_layered_story_cli as s
import layered_text_fixtures as t
import test_layered_cli as core
from test_mcp import Client


def inputs(text='A\U0001f600\rB',global_lengths=None,local_lengths=None):
    g,local=c.inputs(text)
    units=len(text.encode('utf-16-be'))//2+1
    global_lengths=[units] if global_lengths is None else global_lengths
    local_lengths=[units] if local_lengths is None else local_lengths
    g['1']['1'][0]['0']['5']['0']=[{'0':{'0':{'5':{}}},'1':n} for n in global_lengths]
    local['EngineDict']['ParagraphRun']=dict(RunArray=[dict(ParagraphSheet=dict(Properties={})) for _ in local_lengths],RunLengthArray=local_lengths)
    return g,local


def gp(g,i=0):return g['1']['1'][0]['0']['5']['0'][i]['0']['0']['5']
def lp(local,i=0):return local['EngineDict']['ParagraphRun']['RunArray'][i]['ParagraphSheet']['Properties']


class LayeredParagraphTests(unittest.TestCase):
    invoke=core.LayeredTests.invoke
    read=core.LayeredTests.read
    def load(self,g,local):return self.read(c.source(g,local),1,color_policy='assume_srgb')
    def controls(self,g,local):return self.load(g,local)['details']['global_story']['paragraph_styles']

    def test_explicit_numeric_and_array_values_compare_across_independent_partitions(self):
        g,local=inputs(global_lengths=[4,2],local_lengths=[1,3,2])
        global_values={'0':2,'1':-4,'2':16,'3':12,'4':8,'5':9.25,'7':1.5,'9':True,'10':7,'11':3,'12':2,'17':[.75,1,1.5],'18':[-.03,0,.05],'19':[.9,1,1.1],'21':True,'29':False}
        local_values=dict(Justification=2,FirstLineIndent=-4.,StartIndent=16.,EndIndent=12.,SpaceBefore=8.,SpaceAfter=9.25,AutoLeading=1.5,AutoHyphenate=True,HyphenatedWordSize=7,PreHyphen=3,PostHyphen=2,WordSpacing=[.75,1.,1.5],LetterSpacing=[-.03,0.,.05],GlyphSpacing=[.9,1.,1.1],Hanging=True,EveryLineComposer=False)
        for i in range(2):gp(g,i).update(global_values)
        for i in range(3):lp(local,i).update(local_values)
        v=self.controls(g,local);comp=v['comparison']
        self.assertEqual(comp['utf16_spans'],3);self.assertTrue(comp['all_compared_values_match']);self.assertTrue(comp['all_observed_controls_present_on_both_sides'])
        self.assertEqual(v['global']['run_ends_without_carriage_return'],0);self.assertEqual(v['local']['run_ends_without_carriage_return'],1)
        self.assertNotEqual(v['global']['run_controls_sha256'],v['local']['run_controls_sha256'])
        for key in ['complete_style_semantics_validated','missing_values_defaulted','unknown_fields_interpreted','rendering_equivalence_validated','paragraph_boundaries_semantically_validated','legacy_hyphen_limit_conversion_validated']:
            self.assertFalse(v[key])

    def test_conflicts_are_counted_on_utf16_intersections_not_run_indices(self):
        g,local=inputs(global_lengths=[1,3,2],local_lengths=[4,2])
        for i in range(3):gp(g,i).update({'2':16,'17':[.8,1,1.3]})
        for i in range(2):lp(local,i).update(StartIndent=16,WordSpacing=[.8,1,1.3])
        gp(g,1)['2']=20;lp(local,1)['WordSpacing'][2]=1.5
        comp=self.controls(g,local)['comparison']
        self.assertFalse(comp['all_compared_values_match']);self.assertEqual(comp['differing_spans'],2)
        self.assertEqual(comp['different_controls'],['start_indent','word_spacing_factors'])

    def test_missing_properties_and_default_sheets_never_supply_inherited_values(self):
        g,local=inputs();g['1']['1'][0]['0']['5']['0'][0]['0']={};local['EngineDict']['ParagraphRun']['RunArray'][0]={}
        local['EngineDict']['ParagraphRun']['DefaultRunData']=dict(ParagraphSheet=dict(Properties=dict(StartIndent=200)))
        local['ResourceDict']['ParagraphSheetSet']=[dict(Properties=dict(StartIndent=300))]
        v=self.controls(g,local)
        for side in ['local','global']:
            self.assertEqual(v[side]['absent_property_runs'],1);self.assertEqual(v[side]['observed_controls'],[])
        self.assertFalse(v['missing_values_defaulted'])
        g,local=inputs();gp(g)['2']=5;lp(local)['SpaceBefore']=7
        comp=self.controls(g,local)['comparison']
        self.assertEqual(comp['missing_local_controls'],['start_indent']);self.assertEqual(comp['missing_global_controls'],['space_before'])
        self.assertFalse(comp['all_observed_controls_present_on_both_sides'])
        self.assertEqual(self.controls(g,local)['global']['absent_property_runs'],0)

    def test_global_hyphen_limit_and_legacy_local_code_are_not_equated(self):
        g,local=inputs();gp(g).update({'9':True,'13':0,'15':True});lp(local).update(AutoHyphenate=True,ConsecutiveHyphens=8)
        v=self.controls(g,local);comp=v['comparison']
        self.assertEqual(comp['compared_controls'],['automatic_hyphenation']);self.assertTrue(comp['all_compared_values_match'])
        self.assertEqual(comp['missing_local_controls'],['hyphen_limit','hyphenate_capitalized'])
        self.assertEqual(comp['missing_global_controls'],['local_consecutive_hyphens_code'])
        self.assertIn('hyphenate_capitalized',v['global']['enabled_boolean_controls']);self.assertFalse(v['legacy_hyphen_limit_conversion_validated'])

    def test_wrong_types_and_wrong_triple_lengths_fail_without_coercion(self):
        for global_key,local_key,values in [('2','StartIndent',[True,'12',[],{}]),('9','AutoHyphenate',[0,1,'true',[]]),('0','Justification',[True,1.0,1.5,'2']),('17','WordSpacing',[0,[],[1,2],[1,2,3,4],[True,1,2],[1,'2',3],[1,{},3]])]:
            for value in values:
                for side in ['global','local']:
                    g,local=inputs()
                    if side=='global':gp(g)[global_key]=value
                    else:lp(local)[local_key]=value
                    self.assertEqual(self.load(g,local)['code'],'INVALID_LAYERED_FILE',(global_key,value,side))
        for value in [s.Name('true'),b'true']:
            g,local=inputs();gp(g)['15']=value;self.assertEqual(self.load(g,local)['code'],'INVALID_LAYERED_FILE')
        for value in [True,[],1,'original']:
            g,local=inputs();g['1']['1'][0]['0']['5']['0'][0]['0']['0']['5']=value
            self.assertEqual(self.load(g,local)['code'],'INVALID_LAYERED_FILE')
            g,local=inputs();local['EngineDict']['ParagraphRun']['RunArray'][0]['ParagraphSheet']['Properties']=value
            self.assertEqual(self.load(g,local)['code'],'INVALID_LAYERED_FILE')

    def test_comparison_skips_changed_authoritative_text_and_keeps_unknown_fields_visible(self):
        g,local=inputs();g['1']['1'][0]['0']['0']='B\U0001f600\rA\r';gp(g)['2']=12;lp(local)['StartIndent']=16
        v=self.controls(g,local);self.assertEqual(v['comparison'],dict(performed=False,reason='source_text_differs'))
        g,local=inputs()
        for i in range(40):gp(g)[f'Original{i:02}']={'unknown':True};lp(local)[f'Original{i:02}']=[1,2]
        error=self.load(g,local);v=error['details']['global_story']['paragraph_styles']
        for side in ['local','global']:
            self.assertEqual(v[side]['unmapped_field_count'],40);self.assertEqual(len(v[side]['unmapped_fields']),16);self.assertTrue(v[side]['unmapped_fields_truncated'])
        self.assertLess(len(json.dumps(error).encode()),8192);self.assertFalse(v['unknown_fields_interpreted'])

    def test_fingerprints_bind_known_values_and_full_data_hash_binds_unknown_fields(self):
        g,local=inputs();gp(g)['17']=[.8,1,1.33];lp(local)['WordSpacing']=[.8,1.,1.33]
        a=self.controls(g,local);self.assertEqual(a['global']['run_controls_sha256'],a['local']['run_controls_sha256'])
        gp(g)['17'][1]=1.1;b=self.controls(g,local);self.assertNotEqual(a['global']['run_controls_sha256'],b['global']['run_controls_sha256'])
        first=self.load(g,local)['details']['global_story']['global_data_sha256'];gp(g)['OriginalUnknown']=7
        self.assertEqual(b['global']['run_controls_sha256'],self.controls(g,local)['global']['run_controls_sha256'])
        self.assertNotEqual(first,self.load(g,local)['details']['global_story']['global_data_sha256'])

    def test_local_types_are_checked_without_global_and_surrogates_cannot_split(self):
        g,local=inputs();lp(local)['AutoHyphenate']=1
        self.assertEqual(self.read(t.source(text='A\U0001f600\rB',engine=t.data(local)),1,color_policy='assume_srgb')['code'],'INVALID_LAYERED_FILE')
        for side in ['global','local']:
            g,local=inputs(global_lengths=[2,4] if side=='global' else None,local_lengths=[2,4] if side=='local' else None)
            self.assertEqual(self.load(g,local)['code'],'INVALID_LAYERED_FILE')

    def test_direction_line_controls_and_legacy_hanging_remain_distinct(self):
        g,local=inputs();gp(g).update({'8':1,'24':2,'25':2,'33':1,'37':3,'40':3})
        lp(local).update(LeadingType=1,Burasagari=True)
        v=self.controls(g,local);c=v['comparison']
        self.assertEqual(c['compared_controls'],['leading_direction_code']);self.assertTrue(c['all_compared_values_match'])
        self.assertEqual(c['missing_global_controls'],['local_hanging_punctuation'])
        self.assertEqual(c['missing_local_controls'],['hanging_punctuation_code','joining_elongation_width_code','line_breaking_order_code','list_tier','paragraph_direction_code'])
        self.assertEqual(v['global']['unmapped_field_count'],0);self.assertEqual(v['local']['unmapped_field_count'],0)
        lp(local)['LeadingType']=0
        self.assertEqual(self.controls(g,local)['comparison']['different_controls'],['leading_direction_code'])
        for key in ['8','24','25','33','37','40']:
            for bad in [True,1.0,'1']:
                g,local=inputs();gp(g)[key]=bad
                self.assertEqual(self.load(g,local)['code'],'INVALID_LAYERED_FILE',(key,bad))
        for key,bad in [('LeadingType',False),('LeadingType',1.0),('Burasagari',1)]:
            g,local=inputs();lp(local)[key]=bad
            self.assertEqual(self.load(g,local)['code'],'INVALID_LAYERED_FILE')

    def test_cli_mcp_parity_maximum_runs_source_integrity_and_cancellation(self):
        g,local=inputs('A'*64,global_lengths=[1]*65,local_lengths=[1]*65)
        for i in range(65):gp(g,i)['2']=i;lp(local,i)['StartIndent']=i+1
        raw=c.source(g,local)
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'original.psd';p.write_bytes(raw)
            args=dict(source_path=str(p),expected_sha256=hashlib.sha256(raw).hexdigest(),id='incoming',color_policy='assume_srgb')
            expected=self.invoke(dict(command='layered.import',**args),1)
            self.assertEqual(expected['code'],'UNSUPPORTED_LAYERED_SEMANTICS');self.assertLess(len(json.dumps(expected).encode()),8192)
            v=expected['details']['global_story']['paragraph_styles'];self.assertEqual(v['comparison']['differing_spans'],65)
            client=Client()
            try:
                client.initialize();got=client.tool('layered.import',**args)
                self.assertTrue(got['isError']);self.assertEqual(got['structuredContent']['error'],expected)
                self.assertEqual(client.tool('layered.import',**args,control=dict(timeout_ms=0))['structuredContent']['error']['code'],'TIMEOUT')
            finally:client.close()
            self.assertEqual(p.read_bytes(),raw);self.assertEqual(list(Path(root).iterdir()),[p])


if __name__=='__main__':unittest.main()
