"""Original shared stories: independent frame metrics, pixels and source retention."""
import base64
from contextlib import closing
import copy
import json
from pathlib import Path
import tempfile
import unittest
import test_text_cli as text_tests
import test_editing_cli as editing
from test_mcp import Client


class StoryTests(unittest.TestCase):
    setUp = text_tests.TextCliTests.setUp
    invoke = editing.EditingCliTests.invoke
    edit = text_tests.TextCliTests.edit
    pixels = text_tests.TextCliTests.pixels

    def paragraph(self, value='AAAAAAAAAAAA', **kw):
        return dict(text=value, style=dict(font_id='geometry', size=10, fill=[25,100,200,255]), **kw)

    def document(self, paragraphs=None, slots=None, kind='vector', **kw):
        d=self.invoke(dict(command='document.create',id='story-fixture',kind=kind,width=80,height=60))
        story=dict(paragraphs=paragraphs if paragraphs is not None else [self.paragraph()],slots=slots if slots is not None else [dict(id='first',width=12,height=20),dict(id='second',width=28,height=20,columns=2,gutter=4)],**kw)
        ops=[dict(op='font_put',id='geometry',font=self.font),dict(op='story',id='article',story=story)]
        for i,s in enumerate(story['slots']):
            ops.append(dict(op='add',item=dict(id=s['id'],transform=[1,0,0,1,i*30,0],content=dict(type='story_frame',story_id='article',slot_id=s['id']))))
        return self.edit(d,ops)

    def inspect(self,d,**kw):
        return self.invoke(dict(command='story.inspect',document=d,id='article',font_root=str(self.store),**kw))

    def test_ordered_thread_columns_source_intervals_and_glyph_metrics(self):
        d=self.document();r=self.inspect(d,include_outlines=True)['layout']
        self.assertIsNone(r['overset'])
        self.assertEqual([(l['slot_id'],l['column'],l['start'],l['end'],l['consumed_end']) for l in r['lines']], [('first',0,0,2,2),('first',0,2,4,4),('second',0,4,6,6),('second',0,6,8,8),('second',1,8,10,10),('second',1,10,12,12)])
        self.assertEqual([g['origin'] for g in r['slots']['first']['glyphs']],[[0,8],[6,8],[0,18],[6,18]])
        self.assertEqual([g['origin'] for g in r['slots']['second']['glyphs']],[[0,8],[6,8],[0,18],[6,18],[16,8],[22,8],[16,18],[22,18]])
        for slot in r['slots'].values():
            self.assertEqual([l['advance'] for l in slot['lines']],[12]*len(slot['lines']))
        selected=self.invoke(dict(command='text.inspect',document=d,id='second',font_root=str(self.store)))
        self.assertEqual(selected['layout']['glyphs'],r['slots']['second']['glyphs'])
        self.assertNotIn('paths',selected['layout'])
        self.assertEqual(selected['geometry_bounds'],[30,0,58,20])

    def test_full_render_matches_independently_placed_original_text_frames(self):
        for kind in ['vector','raster']:
            d=self.document(kind=kind)
            expected=self.invoke(dict(command='document.create',id='expected',kind=kind,width=80,height=60));expected['fonts']=d['fonts']
            expected['items']=[dict(id=f'line-{i}',transform=[1,0,0,1,x,y],content=dict(type='text',frame=dict(text='AA',width=12,height=10,style=self.paragraph()['style']))) for i,(x,y) in enumerate([(0,0),(0,10),(30,0),(30,10),(46,0),(46,10)])]
            self.assertEqual(self.pixels(d),self.pixels(expected))
            _,_,pixels=self.pixels(d)
            for x,y in [(1,1),(7,11),(31,1),(37,11),(47,1),(53,11)]:self.assertEqual(pixels[(y*80+x)*4:(y*80+x+1)*4],bytes([25,100,200,255]))
            for x,y in [(15,1),(43,1),(60,1),(1,25)]:self.assertEqual(pixels[(y*80+x)*4:(y*80+x+1)*4],bytes(4))

    def test_frame_order_size_and_column_direction_reflow_original_source(self):
        d=self.document();before=copy.deepcopy(d);s=copy.deepcopy(d['stories']['article'])
        s['slots'].reverse();s['slots'][0]['reverse_columns']=True
        changed=self.edit(d,[dict(op='story',id='article',story=s)]);r=self.inspect(changed)['layout']
        self.assertEqual([(l['slot_id'],l['column'],l['start']) for l in r['lines']],[('second',1,0),('second',1,2),('second',0,4),('second',0,6),('first',0,8),('first',0,10)])
        s['slots'][0]['width']=40
        resized=self.edit(changed,[dict(op='story',id='article',story=s)])
        self.assertEqual([l['end']-l['start'] for l in self.inspect(resized)['layout']['lines']],[3,3,3,3])
        self.assertEqual(d,before);self.assertEqual(resized['stories']['article']['paragraphs'],d['stories']['article']['paragraphs'])

    def test_before_after_leading_indents_and_empty_paragraphs(self):
        p=[self.paragraph('AAAA',before=2,after=3,leading=12,indent_start=2,indent_end=2,first_indent=6),self.paragraph('',before=1,after=2),self.paragraph('AA')]
        d=self.document(p,[dict(id='first',width=22,height=60)])
        r=self.inspect(d)['layout'];lines=r['slots']['first']['lines']
        self.assertEqual([(l['x'],l['baseline'],l['start'],l['end']) for l in lines],[(8,10,0,2),(2,22,2,4),(0,38,0,0),(0,50,0,2)])
        self.assertEqual([l['paragraph'] for l in r['lines']],[0,0,1,2]);self.assertIsNone(r['overset'])

    def test_spaces_are_accounted_for_without_rewriting_or_losing_the_tail(self):
        d=self.document([self.paragraph('AA   AA AA')],[dict(id='first',width=12,height=10)],overset='retain')
        r=self.inspect(d)['layout'];self.assertEqual(r['lines'][0]['end'],2);self.assertEqual(r['lines'][0]['consumed_end'],5)
        self.assertEqual(r['overset'],dict(paragraph=0,offset=5));self.pixels(d)
        self.assertEqual(d['stories']['article']['paragraphs'][0]['text'],'AA   AA AA')
        s=copy.deepcopy(d['stories']['article']);s['overset']='error';strict=self.edit(d,[dict(op='story',id='article',story=s)])
        self.assertEqual(self.inspect(strict)['layout']['overset'],r['overset'])
        self.assertEqual(self.invoke(dict(command='document.render',document=strict,font_root=str(self.store)),1)['code'],'STORY_OVERFLOW')

    def test_oversized_grapheme_skips_narrow_slots_without_discarding_text(self):
        d=self.document([self.paragraph('AA')],[dict(id='first',width=5,height=10),dict(id='second',width=12,height=10)])
        r=self.inspect(d)['layout'];self.assertEqual(r['slots']['first']['glyphs'],[]);self.assertEqual(r['lines'][0]['start'],0);self.assertEqual(r['lines'][0]['slot_id'],'second')
        self.assertIsNone(r['overset'])

    def test_shared_edits_independent_story_copy_and_dependency_locks(self):
        d=self.document();d=self.edit(d,[dict(op='add',item=dict(id='duplicate',transform=[1,0,0,1,0,30],content=dict(type='story_frame',story_id='article',slot_id='first')))])
        changed=self.edit(d,[dict(op='story_range',id='article',paragraph=0,start=0,end=1,text='B')])
        self.assertEqual(changed['stories']['article']['paragraphs'][0]['text'],'BAAAAAAAAAAA')
        self.assertEqual(d['stories']['article']['paragraphs'][0]['text'],'AAAAAAAAAAAA')
        copied=self.edit(d,[dict(op='story',id='copy',story=d['stories']['article']),dict(op='story_range',id='copy',paragraph=0,start=0,end=2,text='BB')])
        self.assertEqual(copied['stories']['article'],d['stories']['article'])
        locked=copy.deepcopy(d);locked['items'][-1]['locked']=True
        self.assertEqual(self.edit(locked,[dict(op='story_range',id='article',paragraph=0,start=0,end=1,text='B')],1)['code'],'LOCKED')
        self.assertEqual(self.edit(locked,[dict(op='font_put',id='geometry',font=self.font)],1)['code'],'LOCKED')
        self.assertEqual(self.edit(d,[dict(op='story',id='article',story=None)],1)['code'],'STORY_IN_USE')
        self.assertEqual(self.edit(d,[dict(op='font_remove',id='geometry')],1)['code'],'FONT_IN_USE')

    def test_snapshot_svg_pdf_outline_retain_source(self):
        d=self.document();before=copy.deepcopy(d)
        snapshot=json.loads(self.invoke(dict(command='document.export',document=d,format='snapshot'))['data'])
        self.assertEqual(snapshot,d);self.assertEqual(self.pixels(snapshot),self.pixels(d))
        for fmt in ['svg','pdf']:
            exported=self.invoke(dict(command='document.export',document=d,format=fmt,font_root=str(self.store)))
            self.assertTrue(exported['data'])
        outlined=self.edit(d,[dict(op='text_outline',id='first'),dict(op='text_outline',id='second')])
        self.assertEqual(self.pixels(outlined),self.pixels(d));self.assertEqual(outlined['stories'],d['stories'])
        self.assertEqual(d,before)

    def test_transfer_one_frame_preserves_all_flow_slots_and_remaps_font(self):
        source=self.document();dest=self.invoke(dict(command='document.create',id='destination',kind='vector',width=80,height=60))
        result=self.invoke(dict(command='document.edit',document=dest,expected_revision=0,font_root=str(self.store),operations=[dict(op='transfer',transfer=dict(source=source,ids=['second'],prefix='copy',verify_resources=True))]))
        copied=result['document'];story=copied['stories']['copy-article']
        self.assertEqual(story['slots'],source['stories']['article']['slots']);self.assertEqual(story['paragraphs'][0]['style']['font_id'],'copy-geometry')
        selected=self.invoke(dict(command='text.inspect',document=copied,id='copy-second',font_root=str(self.store)))
        self.assertEqual([l['start'] for l in selected['lines']],[4,6,8,10])
        self.assertEqual(source['stories']['article']['paragraphs'][0]['style']['font_id'],'geometry')

    def test_invalid_stories_and_batch_rollback_are_explicit(self):
        d=self.document();original=copy.deepcopy(d['stories']['article'])
        for change in [dict(slots=[]),dict(paragraphs=[]),dict(slots=[dict(id='x',width=2,height=10,columns=2,gutter=3)]),dict(slots=[dict(id='x',width=12,height=10,columns=0)])]:
            s={**original,**change};self.assertEqual(self.edit(d,[dict(op='story',id='article',story=s)],1)['code'],'INVALID_STORY')
        changed=copy.deepcopy(original);changed['paragraphs'][0]['text']='A\nA'
        self.assertEqual(self.edit(d,[dict(op='story',id='article',story=changed)],1)['code'],'INVALID_STORY')
        self.assertEqual(self.edit(d,[dict(op='story_range',id='article',paragraph=0,start=0,end=1,text='B'),dict(op='remove',id='missing')],1)['code'],'NOT_FOUND')
        self.assertEqual(d['stories']['article'],original)

    def test_mcp_history_retry_diff_and_overset_discovery(self):
        d=self.document();root=str(self.directory/'sessions');session=dict(session_root=root,session_id='flow')
        with closing(Client()) as client:
            client.initialize()
            def call(command,**kw):
                value=client.tool(command,**kw)['structuredContent'];self.assertTrue(value['ok'],value);return value['result']
            created=call('session.create',**session,request_id='create',document=d,resources=dict(font_root=str(self.store)))
            action=dict(type='edit',operations=[dict(op='story_range',id='article',paragraph=0,start=0,end=2,text='AB')])
            edited=call('session.apply',**session,request_id='edit',expected_revision=0,action=action)
            self.assertTrue(call('session.apply',**session,request_id='edit',expected_revision=0,action=action)['replayed'])
            delta=call('document.diff',before=created['document'],after=edited['document'])
            self.assertIn('stories',[r['kind'] for r in delta['resources']])
            self.assertTrue(any('derived.story_source_sha256' in i['fields'] for i in delta['items']))
            undone=call('session.apply',**session,request_id='undo',expected_revision=edited['document']['revision'],action=dict(type='undo'))
            self.assertEqual(undone['document']['stories'],d['stories'])
            redone=call('session.apply',**session,request_id='redo',expected_revision=undone['document']['revision'],action=dict(type='redo'))
            self.assertEqual(redone['document']['stories'],edited['document']['stories'])
            report=call('story.inspect',document=d,id='article',font_root=str(self.store));self.assertIsNone(report['layout']['overset'])
            self.assertTrue(call('session.verify',**session)['valid'])

    def test_bidi_paragraph_direction_and_joining_survive_frame_boundaries(self):
        from synthetic_bidi_font import bidi_font
        path=self.directory/'directional.ttf';path.write_bytes(bidi_font())
        self.font=self.invoke(dict(command='font.import',source_path=str(path),license_path=str(self.license),store_root=str(self.store)))
        paragraph=self.paragraph('\u05d0 A B',bidi='unicode',direction='auto',align='start')
        d=self.document([paragraph],[dict(id=name,width=8,height=12) for name in ['first','second','third']])
        r=self.inspect(d)['layout']
        self.assertEqual([l['start'] for l in r['lines']],[0,2,4])
        self.assertEqual([r['slots'][name]['lines'][0]['direction'] for name in ['first','second','third']],['rtl']*3)
        self.assertEqual([r['slots'][name]['lines'][0]['x'] for name in ['first','second','third']],[1,2,1.5])
        arabic=self.document([self.paragraph('\u0628\u0628\u062a',bidi='unicode',direction='auto')],[dict(id='first',width=12,height=12),dict(id='second',width=12,height=12)])
        r=self.inspect(arabic)['layout'];self.assertEqual([g['glyph_id'] for name in ['first','second'] for g in r['slots'][name]['glyphs']],[11,9,13])
        self.assertEqual([g['start'] for g in r['slots']['first']['glyphs']],[1,0]);self.assertEqual(r['slots']['second']['glyphs'][0]['start'],2)

    def test_artboard_export_keeps_preceding_flow_slots_without_their_items(self):
        d=self.document();d['items'][0]['parent']='board1';d['items'][1]['parent']='board2';d['items'][1]['transform']=[1,0,0,1,0,0]
        d['items'] += [dict(id='board1',content=dict(type='frame',frame=dict(role='artboard',width=12,height=20))),dict(id='board2',transform=[1,0,0,1,30,0],content=dict(type='frame',frame=dict(role='artboard',width=28,height=20)))]
        result=self.invoke(dict(command='artboard.export',document=d,format='png',font_root=str(self.store),selection=dict(type='ids',ids=['board2'])))
        artifact=result['artifacts'][0]['artifact'];w,h,pixels=editing.png_pixels(base64.b64decode(artifact['data']))[:3]
        self.assertEqual((w,h),(28,20))
        for y in range(h):
            for x in range(w):
                # Avoid antialiased half-pixel edges; every remaining sample is analytic.
                if x in [0,4,6,10,16,20,22,26]:continue
                ink=y%10 in range(1,8) and (x in range(1,4) or x in range(7,10) or x in range(17,20) or x in range(23,26))
                self.assertEqual(pixels[(y*w+x)*4:(y*w+x+1)*4],bytes([25,100,200,255]) if ink else bytes(4))
        self.assertEqual(d['stories']['article']['paragraphs'][0]['text'],'AAAAAAAAAAAA')

    def test_component_and_mask_dependencies_propagate_locks_and_diffs(self):
        d=self.document();d['items'][0]['parent']='source';d['items'] += [dict(id='source',content=dict(type='component_source')),dict(id='instance',transform=[1,0,0,1,0,30],content=dict(type='instance',instance=dict(source='source')))]
        d=self.invoke(dict(command='document.validate',document=d));self.pixels(d)
        changed=self.edit(d,[dict(op='story_range',id='article',paragraph=0,start=0,end=1,text='B')])
        diff=self.invoke(dict(command='document.diff',before=d,after=changed))
        instance=next(i for i in diff['items'] if i['id']=='instance');self.assertIn('derived.story_source_sha256',instance['fields'])
        locked=copy.deepcopy(d);next(i for i in locked['items'] if i['id']=='instance')['locked']=True
        self.assertEqual(self.edit(locked,[dict(op='story_range',id='article',paragraph=0,start=0,end=1,text='B')],1)['code'],'LOCKED')
        mask=self.document();mask['items'][0]['parent']='mask';mask['items'] += [dict(id='mask',content=dict(type='mask_source')),dict(id='owner',locked=True,artwork_mask=dict(source='mask',mode='alpha',region=[0,0,12,20]),content=dict(type='vector',geometry=dict(shape='rect',x=0,y=0,width=12,height=20),fill=[255,0,0,255]))]
        mask=self.invoke(dict(command='document.validate',document=mask))
        self.assertEqual(self.edit(mask,[dict(op='story_range',id='article',paragraph=0,start=0,end=1,text='B')],1)['code'],'LOCKED')

    def test_unplaced_source_retention_and_unused_fonts_after_outline(self):
        d=self.document();unplaced=copy.deepcopy(d);unplaced['items']=[]
        self.assertIsNone(self.inspect(unplaced)['layout']['overset'])
        self.assertEqual(bytes.fromhex(self.invoke(dict(command='document.render',document=unplaced))['data']),bytes(80*60*4))
        outlined=self.edit(d,[dict(op='text_outline',id='first'),dict(op='text_outline',id='second')])
        raw=self.invoke(dict(command='document.render',document=outlined))
        self.assertTrue(any(bytes.fromhex(raw['data'])))
        s=copy.deepcopy(d['stories']['article']);s['paragraphs'][0]['indent_start']=10;s['slots'][0]['width']=5
        s['overset']='retain';changed=self.edit(d,[dict(op='story',id='article',story=s)])
        r=self.inspect(changed)['layout'];self.assertEqual(r['slots']['first']['lines'],[])

    def test_storage_strict_fields_named_paints_and_unfitted_text_are_not_silent(self):
        d=self.document();s=copy.deepcopy(d['stories']['article'])
        s['paragraphs'][0]['text']='A'*4097
        self.assertEqual(self.edit(d,[dict(op='story',id='article',story=s)],1)['code'],'RESOURCE_LIMIT')
        s=copy.deepcopy(d['stories']['article']);s['slots']=[dict(id='f'+str(i),width=12,height=10) for i in range(65)]
        self.assertEqual(self.edit(d,[dict(op='story',id='article',story=s)],1)['code'],'RESOURCE_LIMIT')
        s=copy.deepcopy(d['stories']['article']);s['paragraphs'][0]['list']='unsupported'
        self.assertEqual(self.edit(d,[dict(op='story',id='article',story=s)],1)['code'],'INVALID_REQUEST')
        s=copy.deepcopy(d['stories']['article']);s['paragraphs'][0]['style']['fill']={'swatch':'not-bound'}
        self.assertEqual(self.edit(d,[dict(op='story',id='article',story=s)],1)['code'],'SWATCH_NOT_FOUND')
        s=copy.deepcopy(d['stories']['article']);s['paragraphs'][0]['before']=20;s['slots']=[dict(id='first',width=12,height=10),dict(id='second',width=12,height=10)]
        no_room=self.edit(d,[dict(op='story',id='article',story=s)])
        self.assertEqual(self.inspect(no_room)['layout']['overset'],dict(paragraph=0,offset=0))

    def test_line_cell_uses_independent_ascent_and_descent_maxima_across_styles(self):
        from synthetic_unicode_font import unicode_font
        fonts={}
        for name,ascent in [('high',1000),('low',300)]:
            path=self.directory/(name+'.ttf');path.write_bytes(unicode_font('latin',ascent=ascent))
            fonts[name]=self.invoke(dict(command='font.import',source_path=str(path),license_path=str(self.license),store_root=str(self.store)))
        d=self.invoke(dict(command='document.create',id='line-metrics',kind='vector',width=64,height=32));d['fonts']=fonts
        style=dict(font_id='high',size=10,fill=[10,100,200,255])
        paragraph=dict(text='AB',style=style,ranges=[dict(start=1,end=2,style=dict(style,font_id='low',size=20))])
        d['stories']={'article':dict(paragraphs=[paragraph],slots=[dict(id='first',width=30,height=13),dict(id='second',width=30,height=14)])}
        d['items']=[dict(id='placed',content=dict(type='story_frame',story_id='article',slot_id='second'))]
        report=self.inspect(d)['layout'];self.assertEqual(report['slots']['first']['lines'],[])
        line=report['slots']['second']['lines'][0];self.assertEqual(line['baseline'],10)
        self.assertEqual([g['origin'][1] for g in report['slots']['second']['glyphs']],[10,10]);self.assertIsNone(report['overset'])


if __name__=='__main__':unittest.main()
