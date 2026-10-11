"""Language-dependent shaping and independent native language-byte round trips."""
import base64,copy,unittest
import layered_editable_text_fixtures as p
import layered_fixtures as f
import layered_text_delivery_reader as reader
from synthetic_unicode_font import unicode_font, sfnt
from synthetic_font import geometric_font
from synthetic_variable_font import tables
import test_layered_editable_text_cli as e
from test_mcp import Client


class LayeredLanguageTests(unittest.TestCase):
    invoke=e.EditableLayeredTextTests.invoke
    setUp=e.EditableLayeredTextTests.setUp
    add_font=e.EditableLayeredTextTests.add_font
    bindings=e.EditableLayeredTextTests.bindings
    args=e.EditableLayeredTextTests.args
    load=e.EditableLayeredTextTests.load
    pixels=e.EditableLayeredTextTests.pixels

    def authored(self,code,global_=False,text='AA'):
        payload=p.local(text)
        payload['EngineDict']['StyleRun']['RunArray'][0]['StyleSheet']['StyleSheetData']['Language']=code
        g=p.global_data((text,)) if global_ else None
        if g is not None:
            g['1']['1'][0]['0']['6']['0'][0]['0']['0']['6']['38']=code
            # Deliberately stale local language must not override the selected story.
            payload['EngineDict']['StyleRun']['RunArray'][0]['StyleSheet']['StyleSheetData']['Language']=2 if code!=2 else 26
        return p.source([p.layer(text,payload)],g)

    def export(self,d,version='layered',expected=0):
        return self.invoke(dict(command='document.export',document=d,format=version,font_root=str(self.store),
            layered_options=dict(text=dict(reconstruction='native_layout',shape_owner='OriginalGeometry'))),expected)

    def test_explicit_language_selection_survives_both_sources_and_delivery(self):
        for global_ in [False,True]:
            for code,language in [(0,'en-US'),(14,'en-GB'),(2,'fr'),(26,'tr')]:
                d=self.load(self.authored(code,global_))['document']
                self.assertEqual(d['items'][0]['content']['frame']['style']['language'],language)
                for version in ['layered','layered_large']:
                    raw=base64.b64decode(self.export(d,version)['data'])
                    # A separate byte reader checks the writer; reimport alone is insufficient.
                    decoded=f.parse(raw)
                    record=reader.record(next(l['tags'][b'TySh'] for l in decoded['layers'] if b'TySh' in l['tags']))
                    run=record['data']['EngineDict']['StyleRun']['RunArray'][0]
                    self.assertEqual(run['StyleSheet']['StyleSheetData']['Language'],code)
                    incoming=self.load(raw)['document']
                    self.assertEqual(incoming['items'][0]['content']['frame']['style']['language'],language)
                    self.assertEqual(self.pixels(d),self.pixels(incoming))

    def test_language_changes_glyph_selection_advance_and_pixels(self):
        font_tables=tables(unicode_font('latin'))
        font_tables[b'kern']=tables(geometric_font())[b'kern']
        self.font=self.add_font('localized',reader.named_font(self.name,source=sfnt(font_tables)))
        for global_ in [False,True]:
            documents=[self.load(self.authored(code,global_,text='AA'))['document'] for code in [0,26]]
            for d,glyph,advance in zip(documents,[2,3],[12,13]):
                layout=self.invoke(dict(command='text.inspect',document=d,id=d['items'][0]['id'],font_root=str(self.store)))['layout']
                self.assertEqual([g['glyph_id'] for g in layout['glyphs']],[glyph,glyph])
                self.assertEqual(layout['glyphs'][0]['advance'],advance)
                self.assertEqual([g['origin'] for g in layout['glyphs']],[[0,0],[advance,0]])
            self.assertNotEqual(self.pixels(documents[0]),self.pixels(documents[1]))
            self.assertEqual(self.pixels(documents[1]),self.pixels(self.load(base64.b64decode(self.export(documents[1])['data']))['document']))

    def test_language_ranges_and_terminal_style_are_not_lost(self):
        payload=p.local('AAA',styles=[p.style(Language=14),p.style(Language=26),p.style(Language=2)],lengths=[1,1,2])
        d=self.load(p.source([p.layer('AAA',payload)]))['document'];frame=d['items'][0]['content']['frame']
        self.assertEqual(frame['style']['language'],'en-GB')
        self.assertEqual([(r['start'],r['end'],r['style']['language']) for r in frame['ranges']],[(1,2,'tr'),(2,3,'fr')])
        incoming=self.load(base64.b64decode(self.export(d)['data']))['document']['items'][0]['content']['frame']
        self.assertEqual(incoming['style'],frame['style']);self.assertEqual(incoming['ranges'],frame['ranges'])
        payload=p.local('A',styles=[p.style(Language=14),p.style(Language=26)],lengths=[1,1])
        self.assertEqual(self.load(p.source([p.layer('A',payload)]),1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')

    def test_unknown_codes_types_absent_language_and_unsupported_tags(self):
        for global_ in [False,True]:
            for code in [-1,1,27,999]:
                self.assertEqual(self.load(self.authored(code,global_),1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
            for bad in [True,14.0,'14',[],{}]:
                self.assertEqual(self.load(self.authored(bad,global_),1)['code'],'INVALID_LAYERED_FILE')
        d=self.load()['document'];self.assertNotIn('language',d['items'][0]['content']['frame']['style'])
        for language in ['en','en-us','fr-CA','de','tr-TR']:
            bad=copy.deepcopy(d);bad['items'][0]['content']['frame']['style']['language']=language
            self.assertEqual(self.export(bad,expected=1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        # Validate a later range even when it shares the already checked face.
        bad=copy.deepcopy(d);frame=bad['items'][0]['content']['frame'];style=dict(frame['style'],language='de')
        frame['ranges']=[dict(start=1,end=2,style=style)]
        self.assertEqual(self.export(bad,expected=1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')

    def test_mcp_language_source_and_capability_contract_match_cli(self):
        args=self.args(self.authored(26,True));expected=self.invoke(args);c=Client()
        try:
            c.initialize();result=c.tool('layered.import',**{k:v for k,v in args.items() if k!='command'})
            self.assertEqual(result['structuredContent']['result'],expected)
        finally:c.close()
        cap=self.invoke(dict(command='capabilities'))['layered_interchange']
        self.assertIs(cap['text_delivery']['editable_import'],True)
        self.assertEqual(cap['text_import']['language_tags'],['en-US','en-GB','fr','tr'])
        self.assertEqual(cap['text_delivery']['language_tags'],cap['text_import']['language_tags'])


if __name__=='__main__':unittest.main()
