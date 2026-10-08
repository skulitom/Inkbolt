"""Visible discretionary breaks preserve source and shape complete display fragments."""
import copy
import json
import unittest
from contextlib import closing
import test_story_cli as stories
import test_text_cli as text_tests
import test_editing_cli as editing
from synthetic_font import geometric_font
from synthetic_unicode_font import unicode_font
from test_mcp import Client


class StoryHyphenTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    edit=text_tests.TextCliTests.edit
    pixels=text_tests.TextCliTests.pixels
    paragraph=stories.StoryTests.paragraph
    inspect=stories.StoryTests.inspect

    def setUp(self):
        text_tests.TextCliTests.setUp(self)
        self.install(geometric_font(additional_mapping={45:2,46:2,0x2010:2}), 'hyphens')

    def install(self,data,name):
        path=self.directory/(name+'.ttf');path.write_bytes(data)
        self.font=self.invoke(dict(command='font.import',source_path=str(path),license_path=str(self.license),store_root=str(self.store)))

    def document(self,text='AAAAAAAA',width=24,rules=None,slots=None,paragraphs=None,**kw):
        rules=rules if rules is not None else dict(min_left=2,min_right=2,patterns=[dict(text='A',weights=[1,1])])
        paragraphs=paragraphs if paragraphs is not None else [self.paragraph(text,hyphenation=dict(rules_id='words'))]
        return stories.StoryTests.document(self,paragraphs,slots or [dict(id='first',width=width,height=60)],hyphenation_rules={'words':rules},**kw)

    def test_rule_breaks_include_visible_width_and_preserve_all_scalar_intervals(self):
        d=self.document();r=self.inspect(d)['layout'];self.assertIsNone(r['overset'])
        self.assertEqual([(l['start'],l['end'],l['consumed_end']) for l in r['lines']],[(0,3,3),(3,6,6),(6,8,8)])
        self.assertEqual([l.get('hyphen',{}).get('offset') for l in r['lines']],[3,6,None])
        self.assertEqual([l['advance'] for l in r['slots']['first']['lines']],[24,24,12])
        gs=r['slots']['first']['glyphs'];self.assertEqual([g['start'] for g in gs],[0,1,2,3,3,4,5,6,6,7])
        self.assertEqual([(g['start'],g['end'],g['generated']) for g in gs if 'generated' in g],[(3,3,dict(type='hyphen',offset=3)),(6,6,dict(type='hyphen',offset=6))])
        self.assertEqual(d['stories']['article']['paragraphs'][0]['text'],'AAAAAAAA')
        report=self.invoke(dict(command='text.hyphenate',rules=d['stories']['article']['hyphenation_rules']['words'],words=['AAAAAAAA']))
        self.assertEqual(r['lines'][0]['hyphen']['rules_sha256'],report['rules_sha256'])

    def test_full_fit_never_adds_a_hyphen_and_spaces_compete_with_rule_breaks(self):
        d=self.document('AAAA AAAA',width=42);r=self.inspect(d)['layout']
        self.assertEqual([(l['start'],l['end'],l['consumed_end']) for l in r['lines']],[(0,4,5),(5,9,9)])
        self.assertTrue(all('hyphen' not in l for l in r['lines']))
        d=self.document('AAAAAAAA',width=48);r=self.inspect(d)['layout'];self.assertEqual(len(r['lines']),1);self.assertNotIn('hyphen',r['lines'][0])

    def test_no_legal_fit_retains_source_unless_emergency_break_is_explicit(self):
        rules=dict(exceptions={'AAAAAAAA':[]})
        d=self.document(rules=rules,overset='retain');r=self.inspect(d)['layout'];self.assertEqual(r['overset'],dict(paragraph=0,offset=0));self.assertEqual(r['lines'],[])
        p=d['stories']['article']['paragraphs'][0];p['hyphenation']['emergency_break']=True
        r=self.inspect(d)['layout'];self.assertIsNone(r['overset']);self.assertEqual([l['end'] for l in r['lines']],[4,8]);self.assertTrue(all('hyphen' not in l for l in r['lines']))

    def test_joint_kerning_can_make_a_break_fit_that_separate_glyphs_cannot(self):
        self.install(geometric_font(additional_mapping={45:3}),'kerned')
        d=self.document('AAAAAA',slots=[dict(id='first',width=23,height=10),dict(id='second',width=24,height=10)])
        r=self.inspect(d)['layout'];self.assertIsNone(r['overset']);self.assertEqual([l['end'] for l in r['lines']],[2,6])
        gs=r['slots']['first']['glyphs'];self.assertEqual([g['origin'][0] for g in gs],[0,6,11]);self.assertEqual(r['slots']['first']['lines'][0]['advance'],23)
        self.assertEqual(gs[-1]['generated'],dict(type='hyphen',offset=2))

    def test_ligature_with_inserted_character_retains_mixed_cluster_provenance(self):
        self.install(unicode_font('latin',additional_mapping={45:25}),'ligature')
        d=self.document('fAAA',rules=dict(min_left=1,min_right=1,exceptions={'fAAA':[1]}),slots=[dict(id='first',width=5,height=12),dict(id='second',width=18,height=12)])
        r=self.inspect(d)['layout'];self.assertIsNone(r['overset']);g=r['slots']['first']['glyphs'][0]
        self.assertEqual((g['glyph_id'],g['start'],g['end'],g['advance']),(26,0,1,5));self.assertEqual(g['generated'],dict(type='hyphen',offset=1));self.assertEqual(len(r['slots']['first']['glyphs']),1)

    def test_range_style_is_inherited_from_preceding_source_not_following_run(self):
        p=self.paragraph('AAAAAA',hyphenation=dict(rules_id='words'),ranges=[dict(start=0,end=2,style=dict(font_id='geometry',size=20,fill=[200,20,10,255]))])
        d=self.document(paragraphs=[p],rules=dict(exceptions={'AAAAAA':[2]}),slots=[dict(id='first',width=36,height=20),dict(id='second',width=24,height=10)])
        r=self.inspect(d,include_outlines=True)['layout'];self.assertIsNone(r['overset']);slot=r['slots']['first']
        self.assertEqual([g['advance'] for g in slot['glyphs']],[12,12,12]);self.assertTrue(all(p['fill']==[200,20,10,255] for p in slot['paths']))
        self.assertEqual([g['advance'] for g in r['slots']['second']['glyphs']],[6]*4)

    def test_fallback_font_and_unicode_mark_are_selected_and_errors_are_explicit(self):
        fallback=self.font
        self.install(geometric_font(),'body-only');primary=self.font
        d=self.document();d['fonts']['fallback']=fallback;d['fonts']['geometry']=primary
        p=d['stories']['article']['paragraphs'][0];p['style']['fallback_fonts']=['fallback'];p['hyphenation']['mark']='hyphen'
        r=self.inspect(d)['layout'];self.assertEqual(r['lines'][0]['hyphen']['character'],'\u2010');self.assertTrue(all(g['font_id']=='fallback' for g in r['slots']['first']['glyphs'][:4]))
        p['style']['fallback_fonts']=[]
        e=self.invoke(dict(command='story.inspect',document=d,id='article',font_root=str(self.store)),1);self.assertEqual(e['code'],'MISSING_GLYPH')

    def test_unicode_word_boundaries_punctuation_and_combining_graphemes_are_preserved(self):
        self.install(unicode_font('all',additional_mapping={45:27}),'unicode')
        value='e\u0301e\u0301e\u0301e\u0301'
        p=self.paragraph(value,hyphenation=dict(rules_id='words'),bidi='unicode',direction='auto')
        d=self.document(paragraphs=[p],rules=dict(min_left=2,min_right=2,exceptions={value:[4]}),slots=[dict(id='first',width=13,height=12),dict(id='second',width=10,height=12)])
        r=self.inspect(d)['layout'];self.assertIsNone(r['overset']);self.assertEqual([l['end'] for l in r['lines']],[4,8]);self.assertEqual([g['glyph_id'] for g in r['slots']['first']['glyphs']],[5,5,27])
        # A comma is outside the matched Unicode word and remains original source.
        d=self.document('AAAA,AAAA',width=21,rules=dict(exceptions={'AAAA':[2]}),overset='retain')
        self.assertEqual(self.inspect(d)['layout']['lines'][0]['hyphen']['word_end'],4)

    def test_rtl_direction_and_arabic_joining_use_full_virtual_paragraph(self):
        self.install(unicode_font('all',additional_mapping={45:27}),'directional')
        for value,break_at,width,expected in [('\u05d0\u05d1\u05d0\u05d1',2,17,[27,18,17]),('\u0628\u0628\u062a',2,15,[27,11,9])]:
            p=self.paragraph(value,hyphenation=dict(rules_id='words'),bidi='unicode',direction='auto',align='start')
            d=self.document(paragraphs=[p],rules=dict(min_left=1,min_right=1,exceptions={value:[break_at]}),slots=[dict(id='first',width=width,height=12),dict(id='second',width=14,height=12)])
            r=self.inspect(d)['layout'];self.assertIsNone(r['overset']);self.assertEqual([g['glyph_id'] for g in r['slots']['first']['glyphs']],expected)
            self.assertEqual(r['slots']['first']['lines'][0]['direction'],'rtl');h=r['lines'][0]['hyphen'];self.assertEqual(h['display_bidi']['base_level'],1);self.assertEqual(h['display_bidi']['end'],3)
            self.assertEqual(r['slots']['first']['glyphs'][0]['generated'],dict(type='hyphen',offset=2))

    def test_lists_columns_transfer_outlines_and_history_retain_rules_and_body(self):
        p=self.paragraph('AAAAAAAA',hyphenation=dict(rules_id='words'),list=dict(id='steps',marker=dict(type='bullet',text='A'),gap=2),indent_start=8)
        d=self.document(paragraphs=[p],slots=[dict(id='first',width=68,height=20,columns=2,gutter=4)])
        r=self.inspect(d)['layout'];self.assertIsNone(r['overset']);self.assertEqual([bool(l.get('marker')) for l in r['lines']],[True,False,False]);self.assertEqual([bool(l.get('hyphen')) for l in r['lines']],[True,True,False])
        saved=json.loads(self.invoke(dict(command='document.export',document=d,format='snapshot'))['data']);self.assertEqual(saved,d)
        outlined=self.edit(d,[dict(op='text_outline',id='first')]);self.assertEqual(self.pixels(outlined),self.pixels(d));self.assertEqual(outlined['stories'],d['stories'])
        target=self.invoke(dict(command='document.create',id='destination',kind='vector',width=80,height=60));target=self.edit(target,[dict(op='transfer',transfer=dict(source=d,ids=['first'],prefix='copy',verify_resources=True))]);self.assertEqual(target['stories']['copy-article']['hyphenation_rules'],d['stories']['article']['hyphenation_rules']);self.assertEqual(self.pixels(target),self.pixels(d))
        for fmt in ['svg','pdf']:
            self.assertTrue(self.invoke(dict(command='document.export',document=d,format=fmt,font_root=str(self.store)))['data'])

    def test_rule_changes_reflow_and_obey_shared_locks_and_atomic_rollback(self):
        d=self.document();s=copy.deepcopy(d['stories']['article']);s['hyphenation_rules']['words']['exceptions']={'AAAAAAAA':[2,4,6]}
        changed=self.edit(d,[dict(op='story',id='article',story=s)]);self.assertEqual([l['end'] for l in self.inspect(changed)['layout']['lines']],[2,4,8])
        diff=self.invoke(dict(command='document.diff',before=d,after=changed));self.assertIn('derived.story_source_sha256',diff['items'][0]['fields'])
        locked=copy.deepcopy(d);locked['items'][0]['locked']=True;self.assertEqual(self.edit(locked,[dict(op='story',id='article',story=s)],1)['code'],'LOCKED')
        self.assertEqual(self.edit(d,[dict(op='story',id='article',story=s),dict(op='remove',id='missing')],1)['code'],'NOT_FOUND');self.assertEqual(d['stories']['article']['paragraphs'][0]['text'],'AAAAAAAA')

    def test_missing_rules_invalid_data_soft_hyphens_and_limits_fail_explicitly(self):
        d=self.document();original=d['stories']['article']
        for rules,code in [({},'INVALID_HYPHENATION'),({'words':dict(min_left=0)},'INVALID_HYPHENATION'),({'words':dict(exceptions={'AAAA':[1,1]})},'INVALID_HYPHENATION'),({str(i):dict() for i in range(17)},'RESOURCE_LIMIT')]:
            s=dict(original,hyphenation_rules=rules);self.assertEqual(self.edit(d,[dict(op='story',id='article',story=s)],1)['code'],code)
        s=copy.deepcopy(original);s['paragraphs'][0]['text']='AA\u00adAAAA';self.assertEqual(self.edit(d,[dict(op='story',id='article',story=s)],1)['code'],'UNSUPPORTED')
        s=copy.deepcopy(original);s['paragraphs'][0]['hyphenation']['unknown']=True;self.assertEqual(self.edit(d,[dict(op='story',id='article',story=s)],1)['code'],'INVALID_REQUEST')
        s=copy.deepcopy(original);s['paragraphs'][0]['text']='A'*257
        d=self.edit(d,[dict(op='story',id='article',story=s)])
        self.assertEqual(self.invoke(dict(command='story.inspect',document=d,id='article',font_root=str(self.store)),1)['code'],'RESOURCE_LIMIT')

    def test_many_words_and_4096_scalar_virtual_paragraph_have_bounded_extra_capacity(self):
        p=self.paragraph('A '*2044+'AAAAAAAA',hyphenation=dict(rules_id='words'),bidi='unicode')
        d=self.document(paragraphs=[p],slots=[dict(id='first',width=32768,height=10)],overset='retain')
        r=self.inspect(d)['layout'];self.assertEqual(r['lines'][0]['end'],4096);self.assertIsNone(r['overset'])
        # An early word must hyphenate while full-paragraph analysis includes all4096 source scalars.
        p['text']='AAAAAA'+'.'*4090
        d=self.document(paragraphs=[p],slots=[dict(id='first',width=24,height=10)],overset='retain');r=self.inspect(d)['layout'];self.assertEqual(r['lines'][0]['hyphen']['offset'],3)

    def test_mcp_hyphen_rules_edit_undo_redo_retry_and_snapshot(self):
        d=self.document();session=dict(session_root=str(self.directory/'sessions'),session_id='hyphens')
        with closing(Client()) as client:
            client.initialize()
            def call(command,**kw):
                v=client.tool(command,**kw)['structuredContent'];self.assertTrue(v['ok'],v);return v['result']
            call('session.create',**session,request_id='create',document=d,resources=dict(font_root=str(self.store)))
            source=copy.deepcopy(d['stories']['article']);source['hyphenation_rules']['words']['exceptions']={'AAAAAAAA':[2,4,6]};action=dict(type='edit',operations=[dict(op='story',id='article',story=source)])
            edited=call('session.apply',**session,request_id='edit',expected_revision=0,action=action);self.assertTrue(call('session.apply',**session,request_id='edit',expected_revision=0,action=action)['replayed'])
            self.assertEqual(call('story.inspect',document=edited['document'],id='article',font_root=str(self.store))['layout']['lines'][0]['hyphen']['offset'],2)
            undone=call('session.apply',**session,request_id='undo',expected_revision=1,action=dict(type='undo'));self.assertEqual(undone['document']['stories'],d['stories'])
            redone=call('session.apply',**session,request_id='redo',expected_revision=2,action=dict(type='redo'));self.assertEqual(redone['document']['stories'],edited['document']['stories']);self.assertTrue(call('session.verify',**session)['valid'])


if __name__=='__main__':unittest.main()
