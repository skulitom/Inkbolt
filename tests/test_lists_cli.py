"""Original marker fixtures: exact counters, separate source ranges and placement."""
import copy
import json
import string
import unittest
from contextlib import closing
import test_story_cli as stories
import test_text_cli as text_tests
import test_editing_cli as editing
from synthetic_font import geometric_font
from test_mcp import Client


class ListTests(unittest.TestCase):
    invoke = editing.EditingCliTests.invoke
    edit = text_tests.TextCliTests.edit
    pixels = text_tests.TextCliTests.pixels
    paragraph = stories.StoryTests.paragraph
    document = stories.StoryTests.document
    inspect = stories.StoryTests.inspect

    def setUp(self):
        text_tests.TextCliTests.setUp(self)
        self.marker_path = self.directory/'markers.ttf'
        self.marker_path.write_bytes(geometric_font(additional_mapping={ord(c):2 for c in string.ascii_letters+string.digits+'.()[]-'}))
        self.font = self.invoke(dict(command='font.import',source_path=str(self.marker_path),license_path=str(self.license),store_root=str(self.store)))

    def item(self, text='A', level=0, restart=None, id='tasks', format='decimal', **kw):
        marker=dict(type='ordered',format=format,suffix='.')
        options=dict(id=id,level=level,marker=marker,gap=2)
        if restart is not None:options['restart']=restart
        options.update(kw.pop('list_options',{}))
        return self.paragraph(text,indent_start=50,list=options,**kw)

    def labels(self, paragraphs):
        d=self.document(paragraphs,[dict(id='first',width=80,height=500)])
        return [l['marker'] for l in self.inspect(d)['layout']['lines'] if 'marker' in l]

    def test_nested_counters_resume_across_plain_paragraphs_and_other_lists(self):
        paragraphs=[self.item(), self.item(level=1,format='lower_alpha'), self.paragraph('A'), self.item(level=1,format='lower_alpha'), self.item(id='aside',restart=7), self.item(), self.item(level=1,format='lower_roman'), self.item(level=1,restart=9,format='upper_roman'), self.item(), self.item(restart=4), self.item()]
        markers=self.labels(paragraphs)
        self.assertEqual([m['text'] for m in markers],['1.','a.','b.','7.','2.','i.','IX.','3.','4.','5.'])
        self.assertEqual([m['counters'] for m in markers],[[1],[1,1],[1,2],[7],[2],[2,1],[2,9],[3],[4],[5]])

    def test_ordered_formats_boundaries_and_literal_affixes(self):
        cases=[('decimal',999999,'999999'),('lower_alpha',26,'z'),('lower_alpha',27,'aa'),('upper_alpha',702,'ZZ'),('upper_alpha',703,'AAA'),('lower_roman',4,'iv'),('upper_roman',9,'IX'),('upper_roman',49,'XLIX'),('lower_roman',3999,'mmmcmxcix')]
        for format,n,label in cases:
            p=self.item(restart=n,format=format);p['indent_start']=100
            p['list']['marker'].update(prefix='[',suffix=']')
            d=self.document([p],[dict(id='first',width=128,height=20)])
            self.assertEqual(self.inspect(d)['layout']['lines'][0]['marker']['text'],'['+label+']')

    def test_first_line_marker_survives_threading_once_without_consuming_source(self):
        p=self.item('AAAAAA');p['indent_start']=16
        d=self.document([p],[dict(id='first',width=28,height=10),dict(id='second',width=60,height=10,columns=2,gutter=4)])
        r=self.inspect(d)['layout'];self.assertIsNone(r['overset'])
        self.assertEqual([(l['start'],l['end'],l['consumed_end']) for l in r['lines']],[(0,2,2),(2,4,4),(4,6,6)])
        self.assertEqual([bool(l.get('marker')) for l in r['lines']],[True,False,False])
        l=r['lines'][0];m=l['marker'];self.assertEqual((m['x'],m['advance']),(2,12))
        gs=r['slots']['first']['glyphs']
        self.assertEqual((l['glyph_start'],l['glyph_end'],m['glyph_start'],m['glyph_end']),(0,2,2,4))
        self.assertTrue(all('generated' not in g for g in gs[:2]))
        self.assertEqual([g['generated'] for g in gs[2:]],[dict(type='list_marker',start=0,end=1),dict(type='list_marker',start=1,end=2)])
        self.assertEqual([(g['start'],g['end']) for g in gs[2:]],[(0,0)]*2)
        self.assertEqual(d['stories']['article']['paragraphs'][0]['text'],'AAAAAA')

    def test_bullet_style_line_metrics_and_empty_item(self):
        p=self.item('');p['list'].update(marker=dict(type='bullet',text='A'),style=dict(p['style'],size=20,fill=[200,30,20,255]))
        d=self.document([p],[dict(id='first',width=80,height=19),dict(id='second',width=80,height=20)])
        r=self.inspect(d)['layout'];self.assertEqual(r['slots']['first']['lines'],[])
        line=r['lines'][0];self.assertEqual((line['start'],line['end'],line['glyph_start'],line['glyph_end']),(0,0,0,0))
        self.assertEqual(r['slots']['second']['lines'][0]['baseline'],16)
        self.assertEqual(r['slots']['second']['glyphs'][0]['origin'],[36,16])
        self.assertEqual(line['marker']['text'],'A');self.assertIsNone(r['overset'])

    def test_logical_start_hanging_geometry_and_body_alignment_are_independent(self):
        for direction,align,x,mx in [('ltr','start',30,16),('ltr','end',70,16),('rtl','start',44,52),('rtl','end',4,52)]:
            p=self.item(direction=direction,align=align,first_indent=10,indent_end=4);p['indent_start']=20
            d=self.document([p],[dict(id='first',width=80,height=10)])
            r=self.inspect(d)['layout'];self.assertEqual(r['lines'][0]['marker']['x'],mx)
            self.assertEqual(r['slots']['first']['lines'][0]['x'],x)

    def test_unicode_marker_is_isolated_from_body_direction_analysis(self):
        from synthetic_bidi_font import bidi_font
        path=self.directory/'bidi.ttf';path.write_bytes(bidi_font())
        self.font=self.invoke(dict(command='font.import',source_path=str(path),license_path=str(self.license),store_root=str(self.store)))
        p=self.item('\u05d0 A',bidi='unicode',direction='auto',align='start',list_options=dict(marker=dict(type='bullet',text='A')))
        p['indent_start']=12
        d=self.document([p],[dict(id='first',width=40,height=12)])
        r=self.inspect(d)['layout'];line=r['slots']['first']['lines'][0]
        self.assertEqual(line['direction'],'rtl');self.assertEqual(r['lines'][0]['marker']['x'],30)
        marker=r['lines'][0]['marker'];self.assertEqual(marker['bidi']['base_level'],1)
        g=r['slots']['first']['glyphs'][marker['glyph_start']];self.assertEqual(g['direction'],'ltr')

    def test_marker_space_is_required_and_overset_source_is_unchanged(self):
        p=self.item();p['indent_start']=13
        d=self.document([p],[dict(id='first',width=80,height=20)],overset='retain')
        r=self.inspect(d)['layout'];self.assertEqual(r['overset'],dict(paragraph=0,offset=0));self.assertEqual(r['lines'],[])
        self.assertEqual(self.pixels(d)[2],bytes(80*60*4))
        d['stories']['article']['overset']='error'
        e=self.invoke(dict(command='document.render',document=d,font_root=str(self.store)),1)
        self.assertEqual(e['code'],'STORY_OVERFLOW')

    def test_invalid_nesting_counters_literals_gap_and_unknown_fields(self):
        d=self.document([self.item()],[dict(id='first',width=80,height=20)])
        for update in [dict(level=1),dict(level=9),dict(id='bad id'),dict(restart=0),dict(restart=1000000),dict(gap=-1),dict(gap=32769),dict(marker=dict(type='bullet',text='')),dict(marker=dict(type='bullet',text=' \t')),dict(marker=dict(type='bullet',text='A'*33)),dict(marker=dict(type='bullet',text='A\u202e')),dict(restart=4000,marker=dict(type='ordered',format='upper_roman')),dict(marker=dict(type='ordered',format='decimal',prefix='A\n'))]:
            s=copy.deepcopy(d['stories']['article']);s['paragraphs'][0]['list'].update(update)
            self.assertEqual(self.edit(d,[dict(op='story',id='article',story=s)],1)['code'],'INVALID_LIST',update)
        s=copy.deepcopy(d['stories']['article']);s['paragraphs']=[self.item(restart=999999),self.item()]
        self.assertEqual(self.edit(d,[dict(op='story',id='article',story=s)],1)['code'],'INVALID_LIST')
        s=copy.deepcopy(d['stories']['article']);s['paragraphs'][0]['list']['unrecognized']=True
        self.assertEqual(self.edit(d,[dict(op='story',id='article',story=s)],1)['code'],'INVALID_REQUEST')

    def test_marker_fonts_follow_dependency_locks_transfer_and_removal_rules(self):
        p=self.item();p['list']['style']=dict(p['style'],font_id='markers')
        d=self.document([self.paragraph('A')],[dict(id='first',width=80,height=20)])
        d=self.edit(d,[dict(op='font_put',id='markers',font=self.font),dict(op='story',id='article',story=dict(paragraphs=[p],slots=d['stories']['article']['slots']))])
        info=self.invoke(dict(command='document.inspect',document=d));self.assertEqual(next(f for f in info['fonts'] if f['id']=='markers')['used_by'],['first'])
        self.assertEqual(self.edit(d,[dict(op='font_remove',id='markers')],1)['code'],'FONT_IN_USE')
        locked=copy.deepcopy(d);locked['items'][0]['locked']=True
        self.assertEqual(self.edit(locked,[dict(op='font_put',id='markers',font=self.font)],1)['code'],'LOCKED')
        dest=self.invoke(dict(command='document.create',id='destination',kind='vector',width=80,height=60))
        dest=self.edit(dest,[dict(op='transfer',transfer=dict(source=d,ids=['first'],prefix='copy',verify_resources=True))])
        self.assertEqual(dest['stories']['copy-article']['paragraphs'][0]['list']['style']['font_id'],'copy-markers')
        self.assertEqual(self.pixels(d),self.pixels(dest))

    def test_snapshot_outline_and_exports_preserve_marker_pixels_in_both_document_kinds(self):
        for kind in ['vector','raster']:
            d=self.document([self.item('AA')],[dict(id='first',width=80,height=20)],kind=kind)
            saved=json.loads(self.invoke(dict(command='document.export',document=d,format='snapshot'))['data'])
            self.assertEqual(saved,d);self.assertEqual(self.pixels(saved),self.pixels(d))
            if kind=='vector':
                for fmt in ['svg','pdf']:
                    self.assertTrue(self.invoke(dict(command='document.export',document=d,format=fmt,font_root=str(self.store)))['data'])
                outlined=self.edit(d,[dict(op='text_outline',id='first')]);self.assertEqual(self.pixels(outlined),self.pixels(d));self.assertEqual(outlined['stories'],d['stories'])

    def test_source_edits_independent_copies_and_marker_diff(self):
        d=self.document([self.item('AA')],[dict(id='first',width=80,height=20)])
        text=self.edit(d,[dict(op='story_range',id='article',paragraph=0,start=0,end=1,text='BA')])
        self.assertEqual(text['stories']['article']['paragraphs'][0]['list'],d['stories']['article']['paragraphs'][0]['list'])
        self.assertEqual(self.inspect(text)['layout']['lines'][0]['marker']['text'],'1.')
        source=copy.deepcopy(d['stories']['article']);source['paragraphs'][0]['list']['restart']=3
        changed=self.edit(d,[dict(op='story',id='article',story=source)])
        delta=self.invoke(dict(command='document.diff',before=d,after=changed));self.assertIn('derived.story_source_sha256',delta['items'][0]['fields'])
        copied=self.edit(d,[dict(op='story',id='copy',story=source)])
        self.assertEqual(copied['stories']['article'],d['stories']['article'])

    def test_resource_limits_include_generated_labels_and_list_identity(self):
        d=self.document([self.item()],[dict(id='first',width=80,height=20)])
        for paragraphs in [[self.item('A'*4095)],[self.item('',id='l'+str(i)) for i in range(65)],[self.item('',list_options=dict(marker=dict(type='ordered',format='decimal',prefix='A'*32,suffix='A'*32))) for _ in range(64)]]:
            s=copy.deepcopy(d['stories']['article']);s['paragraphs']=paragraphs
            self.assertEqual(self.edit(d,[dict(op='story',id='article',story=s)],1)['code'],'RESOURCE_LIMIT')

    def test_mcp_list_edit_history_retry_schema_and_source_preservation(self):
        d=self.document([self.item()],[dict(id='first',width=80,height=20)])
        session=dict(session_root=str(self.directory/'sessions'),session_id='lists')
        with closing(Client()) as client:
            client.initialize()
            def call(command,**kw):
                value=client.tool(command,**kw)['structuredContent'];self.assertTrue(value['ok'],value);return value['result']
            call('session.create',**session,request_id='create',document=d,resources=dict(font_root=str(self.store)))
            s=copy.deepcopy(d['stories']['article']);s['paragraphs'][0]['list']['restart']=9
            action=dict(type='edit',operations=[dict(op='story',id='article',story=s)])
            edited=call('session.apply',**session,request_id='edit',expected_revision=0,action=action)
            self.assertTrue(call('session.apply',**session,request_id='edit',expected_revision=0,action=action)['replayed'])
            report=call('story.inspect',document=edited['document'],id='article',font_root=str(self.store))
            self.assertEqual(report['layout']['lines'][0]['marker']['text'],'9.')
            undone=call('session.apply',**session,request_id='undo',expected_revision=1,action=dict(type='undo'))
            self.assertEqual(undone['document']['stories'],d['stories'])
            redone=call('session.apply',**session,request_id='redo',expected_revision=2,action=dict(type='redo'))
            self.assertEqual(redone['document']['stories'],edited['document']['stories']);self.assertTrue(call('session.verify',**session)['valid'])


if __name__=='__main__':unittest.main()
