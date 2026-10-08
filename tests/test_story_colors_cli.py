"""Named body, list and generated-hyphen paints retain shared resource semantics."""
import copy
import unittest
import test_story_hyphens_cli as hyphens
import test_text_cli as text_tests
import test_story_cli as stories
import test_editing_cli as editing
import test_swatches_cli as swatches
import test_ink_delivery_cli as inks
from pdf_reader import Pdf


class StoryColorTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    edit=text_tests.TextCliTests.edit
    pixels=text_tests.TextCliTests.pixels
    paragraph=stories.StoryTests.paragraph
    inspect=stories.StoryTests.inspect
    install=hyphens.StoryHyphenTests.install
    setUp=hyphens.StoryHyphenTests.setUp

    def document(self,kind='vector'):
        d=hyphens.StoryHyphenTests.document(self,'AAAAAA',slots=[dict(id='first',width=32,height=10),dict(id='second',width=32,height=10)],kind=kind)
        p=d['stories']['article']['paragraphs'][0];p['indent_start']=8;p['style']['fill']=swatches.paint('shade',.5)
        p['list']=dict(id='steps',marker=dict(type='bullet',text='A'),gap=2,style=dict(p['style'],fill=swatches.paint('marker')))
        d['swatches']={'body':swatches.process(components=[.25,.5,.75]),'shade':swatches.tint('body',.5),'marker':swatches.process(components=[1,0,0])}
        return self.invoke(dict(command='document.validate',document=d))

    def test_body_marker_hyphen_preview_and_palette_inspection_are_complete(self):
        for kind in ['vector','raster']:
            d=self.document(kind);direct=copy.deepcopy(d);p=direct['stories']['article']['paragraphs'][0];p['style']['fill']=dict(rgba=[.8125,.875,.9375,1]);p['list']['style']['fill']=[255,0,0,255]
            self.assertEqual(self.pixels(d),self.pixels(direct))
            r=self.invoke(dict(command='swatch.inspect',document=d));entries={s['id']:s for s in r['swatches']}
            self.assertEqual(entries['body']['used_by'],['first','second']);self.assertEqual(entries['body']['story_users'],['article']);self.assertEqual(entries['marker']['story_users'],['article'])
            png=self.invoke(dict(command='document.export',document=d,format='png',font_root=str(self.store)));self.assertEqual(png['swatches']['used_ids'],['body','marker','shade'])

    def test_recolor_diffs_and_dependent_locks_cover_body_and_marker_resources(self):
        d=self.document();changed=self.edit(d,[dict(op='swatch',id='body',swatch=swatches.process(components=[1,0,0]))])
        self.assertEqual(changed['stories'],d['stories']);self.assertNotEqual(self.pixels(changed),self.pixels(d))
        delta=self.invoke(dict(command='document.diff',before=d,after=changed));self.assertTrue(all('derived.swatch_source_sha256' in i['fields'] for i in delta['items']))
        locked=copy.deepcopy(d);locked['items'][1]['locked']=True
        for id in ['body','marker']:
            self.assertEqual(self.edit(locked,[dict(op='swatch',id=id,swatch=swatches.process(components=[0,1,0]))],1)['code'],'LOCKED')

    def test_unplaced_stories_guard_deletion_without_forcing_preview_or_fonts(self):
        d=self.document();d['items']=[];d['swatches']['body']=swatches.process(space='cmyk',components=[.1,.2,.3,.4])
        self.assertEqual(self.edit(d,[dict(op='swatch',id='marker',swatch=None)],1)['code'],'SWATCH_IN_USE')
        r=self.invoke(dict(command='document.render',document=d));self.assertEqual(bytes.fromhex(r['data']),bytes(80*60*4))
        r=self.invoke(dict(command='swatch.inspect',document=d));self.assertEqual(next(s for s in r['swatches'] if s['id']=='marker')['story_users'],['article'])

    def test_cross_document_transfer_copies_tint_closure_and_remaps_both_styles(self):
        d=self.document();target=self.invoke(dict(command='document.create',id='target',kind='vector',width=80,height=60))
        target=self.edit(target,[dict(op='transfer',transfer=dict(source=d,ids=['first','second'],prefix='copy',verify_resources=True))])
        self.assertEqual(set(target['swatches']),{'copy-body','copy-shade','copy-marker'});p=target['stories']['copy-article']['paragraphs'][0]
        self.assertEqual(p['style']['fill']['swatch'],'copy-shade');self.assertEqual(p['list']['style']['fill']['swatch'],'copy-marker');self.assertEqual(target['swatches']['copy-shade']['definition']['base'],'copy-body');self.assertEqual(self.pixels(target),self.pixels(d))

    def test_selected_bake_copies_shared_story_and_preserves_unselected_live_binding(self):
        d=self.document();d['items'][1]['locked']=True
        baked=self.edit(d,[dict(op='swatch_bake',ids=['first'])]);binding=baked['items'][0]['content']['story_id']
        self.assertNotEqual(binding,'article');self.assertEqual(baked['stories']['article'],d['stories']['article']);self.assertEqual(baked['items'][1],d['items'][1]);self.assertEqual(self.pixels(baked),self.pixels(d))
        independent=baked['stories'][binding]['paragraphs'][0];self.assertEqual(independent['style']['fill']['rgba'],[.8125,.875,.9375,1]);self.assertEqual(independent['list']['style']['fill']['rgba'],[1,0,0,1])
        self.assertEqual(self.edit(baked,[dict(op='swatch',id='body',swatch=swatches.process(components=[1,0,0]))],1)['code'],'LOCKED')

    def test_bake_all_bindings_updates_one_source_and_allows_display_vector_delivery(self):
        d=self.document();d['swatches']['body']=swatches.spot();original=copy.deepcopy(d)
        for fmt in ['svg','pdf']:
            self.assertEqual(self.invoke(dict(command='document.export',document=d,format=fmt,font_root=str(self.store)),1)['code'],'UNSUPPORTED')
        baked=self.edit(d,[dict(op='swatch_bake',ids=['first','second'])]);self.assertEqual(set(baked['stories']),{'article'});self.assertEqual(self.pixels(baked),self.pixels(d))
        for fmt in ['svg','pdf']:self.assertTrue(self.invoke(dict(command='document.export',document=baked,format=fmt,font_root=str(self.store)))['data'])
        self.assertEqual(d,original)

    def test_native_ink_pdf_keeps_body_hyphen_and_marker_ink_operands(self):
        d=self.document();d['swatches']['body']=inks.cmyk([.1,.2,.3,.4],spot=True)
        d['stories']['article']['paragraphs'][0]['style']['fill']['overprint']='preserve'
        self.assertEqual(self.invoke(dict(command='document.render',document=d,font_root=str(self.store)),1)['code'],'OVERPRINT_PREVIEW_UNSUPPORTED')
        output=self.invoke(dict(command='document.export',document=d,format='pdf',font_root=str(self.store),pdf_options=dict(color='native_inks')))
        paints=inks.painted(Pdf(output));spot=[p for p in paints if isinstance(p['space'],list) and p['space'][0]=='Separation']
        self.assertEqual(len(spot),7);self.assertTrue(all(p['values']==[.25] for p in spot));self.assertTrue(all(p['state']['op'] for p in spot))
        marker=[p for p in paints if p['space']=='DeviceRGB'];self.assertEqual(len(marker),1);self.assertEqual(marker[0]['values'],[1,0,0])

    def test_component_and_mask_dependency_hashes_follow_story_palette(self):
        d=self.document();d['items'][0]['parent']='source';d['items'] += [dict(id='source',content=dict(type='component_source')),dict(id='instance',content=dict(type='instance',instance=dict(source='source')))]
        d=self.invoke(dict(command='document.validate',document=d));changed=self.edit(d,[dict(op='swatch',id='marker',swatch=swatches.process(components=[0,1,0]))]);delta=self.invoke(dict(command='document.diff',before=d,after=changed));self.assertIn('derived.swatch_source_sha256',next(i for i in delta['items'] if i['id']=='instance')['fields'])
        d['items'][-1]['locked']=True;self.assertEqual(self.edit(d,[dict(op='swatch',id='marker',swatch=swatches.process(components=[0,1,0]))],1)['code'],'LOCKED')

    def test_managed_body_hyphens_and_marker_keep_profiles_through_transfer_and_pdf(self):
        from test_swatch_profiles_cli import managed
        from test_profiles_cli import embedded,linear_profile,builtin
        d=self.document();raw=linear_profile(gamma=2);d['swatches']['body']=managed('rgb',[.25,.5,.75],embedded(raw),'saturation',spot=True);d['swatches']['marker']=managed('lab',[50,12,-8],intent='absolute_colorimetric');d['output_profile']=builtin('srgb');d=self.invoke(dict(command='document.validate',document=d));before=copy.deepcopy(d)
        artifact=self.invoke(dict(command='document.export',document=d,format='pdf',font_root=str(self.store),pdf_options=dict(color='native_inks')));reader=Pdf(artifact);paints=inks.painted(reader)
        body=[p for p in paints if isinstance(p['space'],list) and p['space'][0]=='Separation'];self.assertEqual(len(body),7);self.assertTrue(all(p['values']==[.25] and p['state']['RI']=='Saturation' and p['state']['UseBlackPtComp']=='OFF' for p in body));self.assertEqual(sum(s==raw for s in reader.streams.values()),1)
        marker=[p for p in paints if isinstance(p['space'],list) and p['space'][0]=='Lab'];self.assertEqual(len(marker),1);self.assertEqual(marker[0]['values'],[50,12,-8]);self.assertEqual(marker[0]['state']['RI'],'AbsoluteColorimetric')
        target=self.invoke(dict(command='document.create',id='copied',kind='vector',width=80,height=60));target=self.edit(target,[dict(op='transfer',transfer=dict(source=d,ids=['first','second'],prefix='copy',verify_resources=True))]);self.assertEqual(target['swatches']['copy-body'],d['swatches']['body']);self.assertEqual(target['swatches']['copy-marker'],d['swatches']['marker']);self.assertEqual(self.pixels(target),self.pixels(d));self.assertEqual(d,before)


if __name__=='__main__':unittest.main()
