"""Explicit rendering conversion, source reconciliation and bounded diagnostics."""
import base64,copy,json,unittest
import layered_editable_text_fixtures as p
import layered_fixtures as f
import layered_object_fixtures as objects
import layered_text_fixtures as text
import test_layered_editable_text_cli as editable
import test_layered_metadata_cli as metadata
import test_layered_story_cli as story
from test_mcp import Client

MODES=[('Anno',0,'none'),('AnCr',1,'crisp'),('AnSt',2,'strong'),('AnSm',3,'smooth'),('antiAliasSharp',4,'sharp')]


class LayeredRenderingTests(unittest.TestCase):
    invoke=editable.EditableLayeredTextTests.invoke
    setUp=editable.EditableLayeredTextTests.setUp
    add_font=editable.EditableLayeredTextTests.add_font
    bindings=editable.EditableLayeredTextTests.bindings
    args=editable.EditableLayeredTextTests.args
    load=editable.EditableLayeredTextTests.load
    pixels=editable.EditableLayeredTextTests.pixels

    def encoded(self,mode=MODES[1],fractional=True,global_mode=False,version=1,payload=None,g=None,changes=None):
        descriptor,code,_=mode
        payload=p.local() if payload is None else copy.deepcopy(payload)
        payload['EngineDict'].update(AntiAlias=code,UseFractionalGlyphWidths=fractional)
        values={'TextIndex':metadata.integer(0),'AntA':metadata.enum('Annt',descriptor)};values.update(changes or {})
        layer=p.layer();layer['extra']=f.tag(b'TySh',text.record('AA',engine=text.data(payload),transform=(1,0,0,1,8,30),changes=values))
        if global_mode and g is None:
            g=p.global_data();g['1']['1'][0]['0']['10']={'0':code,'2':fractional}
        return p.source([layer],g,version)

    def policy(self):
        return dict(self.bindings(),reconstruction='engine_layout',rendering='engine')

    def test_known_modes_require_explicit_choice_and_preserve_analytic_editable_output(self):
        expected=self.pixels(self.load()['document'])
        for version in [1,2]:
            for global_mode in [False,True]:
                for mode in MODES:
                    for fractional in [False,True]:
                        raw=self.encoded(mode,fractional,global_mode,version)
                        if mode[2]!='none' or not fractional:
                            error=self.load(raw,1);self.assertEqual(error['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
                            self.assertIn('text_fonts.rendering:engine',error['message'])
                        result=self.load(raw,text_fonts=self.policy());d=result['document'];r=result['text'][0]['rendering']
                        self.assertEqual(d['items'][0]['content']['type'],'text');self.assertEqual(self.pixels(d),expected)
                        self.assertEqual(d['items'][0]['transform'],[1,0,0,1,8,30])
                        self.assertEqual(r['source']['descriptor']['antialias_mode'],mode[2])
                        self.assertEqual(r['source']['local'],dict(antialias_code=mode[1],antialias_mode=mode[2],fractional_widths=fractional))
                        self.assertEqual(r['global_source']['present'],global_mode)
                        self.assertEqual(r['differences'],dict(native_edge_smoothing_reconstructed=True,fractional_spacing_reconstructed=not fractional))
                        self.assertEqual(r['output'],dict(edge_smoothing='engine',fractional_widths=True))
                        self.assertFalse(r['native_rendering_equivalence']);self.assertFalse(result['text'][0]['cached_pixels_used'])

    def test_global_absence_is_reported_without_inventing_values(self):
        for mode in [MODES[1],MODES[3]]:
            for data in [None,{}, {'0':mode[1]}, {'2':True}]:
                g=p.global_data()
                if data is not None:g['1']['1'][0]['0']['10']=data
                r=self.load(self.encoded(mode,g=g),text_fonts=self.policy())['text'][0]['rendering']['global_source']
                self.assertEqual(r['present'],data is not None)
                self.assertEqual(r['antialias_code'],None if data is None else data.get('0'))
                self.assertEqual(r['fractional_widths'],None if data is None else data.get('2'))
                self.assertFalse(r['missing_values_inferred'])
        raw=self.encoded(MODES[0]);r=self.load(raw)['text'][0]['rendering']
        self.assertEqual(r['choice'],'existing_point_reconstruction')

    def test_conflicts_unknown_modes_and_unknown_global_fields_cannot_use_conversion_escape(self):
        cases=[self.encoded(('unknown',1,'unknown')),self.encoded(('AnCr',5,'unknown')),
               self.encoded(('AnCr',0,'none')),self.encoded(changes={'AntA':metadata.enum('Unknown','AnCr')})]
        for data in [{'0':2,'2':True},{'0':1,'2':False},{'0':999,'2':True},{'0':1,'2':True,'99':False}]:
            g=p.global_data();g['1']['1'][0]['0']['10']=data;cases.append(self.encoded(g=g))
        for raw in cases:
            error=self.load(raw,1,text_fonts=self.policy());self.assertEqual(error['code'],'UNSUPPORTED_LAYERED_SEMANTICS');self.assertNotIn('document',error)
        g=p.global_data();g['1']['1'][0]['0']['10']={str(i):True for i in range(20,52)}
        error=self.load(self.encoded(g=g),1,text_fonts=self.policy());r=error['details']['global_story']['rendering']
        self.assertEqual(r['unknown_field_count'],32);self.assertEqual(len(r['unknown_fields']),8)

    def test_missing_local_values_and_wrong_types_remain_distinct_errors(self):
        for field in ['AntiAlias','UseFractionalGlyphWidths']:
            payload=p.local();del payload['EngineDict'][field]
            layer=p.layer(payload=payload);raw=p.source([layer])
            self.assertEqual(self.load(raw,1,text_fonts=self.policy())['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        for code in [True,1.0,-1,'1']:
            self.assertEqual(self.load(self.encoded(('AnCr',code,'crisp')),1,text_fonts=self.policy())['code'],'INVALID_LAYERED_FILE')
        for value in [0,1,'true',[]]:
            self.assertEqual(self.load(self.encoded(fractional=value),1,text_fonts=self.policy())['code'],'INVALID_LAYERED_FILE')
        for data in [True,{'0':False},{'0':1.0},{'2':1},{'0':story.Name('none')}]:
            g=p.global_data();g['1']['1'][0]['0']['10']=data
            self.assertEqual(self.load(self.encoded(g=g),1,text_fonts=self.policy())['code'],'INVALID_LAYERED_FILE')

    def test_rendering_choice_does_not_bypass_other_text_semantics(self):
        for changes in [{'Ornt':metadata.enum('Ornt','Vrtc')},{'textGridding':metadata.enum('textGridding','Grid')},{'TxMP':metadata.boolean(True)}]:
            self.assertEqual(self.load(self.encoded(changes=changes),1,text_fonts=self.policy())['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        payload=p.local();payload['EngineDict']['StyleRun']['RunArray'][0]['StyleSheet']['StyleSheetData']['UnknownControl']=False
        self.assertEqual(self.load(self.encoded(payload=payload),1,text_fonts=self.policy())['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        g=p.global_data();g['1']['2']={'0':0}
        error=self.load(self.encoded(g=g),1,text_fonts=self.policy())
        self.assertEqual(error['code'],'UNSUPPORTED_LAYERED_SEMANTICS');self.assertIn('global authoring /1: ["2"] (1 total)',error['message'])
        self.assertEqual(error['details']['rendering']['descriptor']['antialias_mode'],'crisp')
        for policies in [dict(self.bindings(),rendering='engine'),dict(self.policy(),rendering='native')]:
            self.assertEqual(self.load(self.encoded(),1,text_fonts=policies)['code'],'INVALID_REQUEST')

    def test_nested_sources_share_choice_and_cli_mcp_schema_and_receipts_agree(self):
        raw=self.encoded(fractional=False,global_mode=True,version=2)
        expected=self.load(raw,text_fonts=self.policy())
        layer=dict(name='Placed text',width=1,height=1,rgba=[0,0,255,255],extra=objects.placement(size=(64,48),matrix=(1,0,0,1,0,0)))
        nested=f.make([layer],w=64,h=48,global_extra=objects.global_sources([objects.entry(raw)]))
        result=self.load(nested,text_fonts=self.policy(),embedded_objects=objects.POLICY)
        self.assertEqual(self.pixels(result['document']),self.pixels(expected['document']))
        self.assertEqual(result['embedded_sources'][0]['text'][0]['rendering'],expected['text'][0]['rendering'])
        args=self.args(raw);args['text_fonts']=self.policy();client=Client()
        try:
            client.initialize();self.assertEqual(client.success('layered.import',**{k:v for k,v in args.items() if k!='command'}),expected)
            defs=client.success('schema.lookup',name='layered.import',full=True)['schema']['$defs']
            self.assertEqual(defs['TextImportRendering']['enum'],['engine']);self.assertIn('rendering',defs['TextFonts']['properties'])
            cap=client.success('capabilities')['layered_interchange']['text_import']['rendering']
            self.assertEqual(cap['choice'],'engine');self.assertFalse(cap['native_rendering_equivalence'])
        finally:client.close()

    def test_delivery_reimport_preserves_reconstructed_text_pixels_and_baseline(self):
        result=self.load(self.encoded(),text_fonts=self.policy());d=result['document'];before=self.pixels(d)
        for format in ['layered','layered_large']:
            artifact=self.invoke(dict(command='document.export',document=d,format=format,font_root=str(self.store),
                layered_options=dict(text=dict(reconstruction='native_layout',shape_owner='OriginalGeometry'))))
            reopened=self.load(base64.b64decode(artifact['data']))
            self.assertEqual(self.pixels(reopened['document']),before)
            self.assertEqual(reopened['document']['items'][0]['content']['frame'],d['items'][0]['content']['frame'])
            self.assertEqual(reopened['document']['items'][0]['transform'],d['items'][0]['transform'])


if __name__=='__main__':unittest.main()
