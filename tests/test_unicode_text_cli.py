"""Independent original-font shaping, fallback, resource and delivery checks."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import test_editing_cli as editing
import test_text_cli as text_tests
from test_mcp import Client
from synthetic_unicode_font import unicode_font, rectangle, ADVANCES


class UnicodeTextTests(unittest.TestCase):
    invoke = editing.EditingCliTests.invoke
    edit = text_tests.TextCliTests.edit
    inspect = text_tests.TextCliTests.inspect
    pixels = text_tests.TextCliTests.pixels

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name); self.store = self.directory/'store'
        self.license = self.directory/'LICENSE.txt'
        self.license.write_bytes((Path(__file__).resolve().parents[1]/'LICENSE').read_bytes())
        self.fonts = {}; self.sources = {}
        self.add_font('latin')

    def add_font(self, name, coverage=None, **kw):
        path = self.directory/(name+'.ttf')
        data = unicode_font(coverage or name, **kw); path.write_bytes(data)
        self.sources[name] = data
        self.fonts[name] = self.invoke(dict(command='font.import', source_path=str(path),
            license_path=str(self.license), store_root=str(self.store)))
        return name

    def document(self, text='A', kind='vector', font='latin', fallback=None, **options):
        d = self.invoke(dict(command='document.create', id='unicode-fixture', kind=kind, width=100, height=60))
        frame = dict(text=text, width=100, height=60, wrap=False, overflow='visible',
            style=dict(font_id=font, size=10, fill=[25,100,200,255]))
        if fallback is not None: frame['style']['fallback_fonts'] = fallback
        frame.update(options)
        return self.edit(d, [dict(op='font_put',id=id,font=f) for id,f in self.fonts.items()] +
            [dict(op='add',item=dict(id='label',content=dict(type='text',frame=frame)))])

    def glyphs(self,d): return self.inspect(d)['layout']['glyphs']

    def assert_rectangles(self, d, expected, baseline=10):
        """Expected rows (glyph, scalar-start, scalar-end, x, y, advance, font)."""
        glyphs = self.glyphs(d); self.assertEqual(len(glyphs),len(expected))
        for g,(gid,start,end,x,y,advance,font) in zip(glyphs,expected):
            self.assertEqual((g['glyph_id'],g['start'],g['end'],g['origin'],g['advance'],g['font_id']),
                (gid,start,end,[x,y],advance,font))
            box = rectangle(gid)
            ink = None if box is None else [x+box[0]/100,y-box[3]/100,x+box[2]/100,y-box[1]/100]
            if ink is None: self.assertIsNone(g['ink_bounds'])
            else:
                for a,b in zip(g['ink_bounds'],ink): self.assertAlmostEqual(a,b,places=12)

    def test_arabic_joining_forms_declared_rtl_and_logical_cluster_indices(self):
        self.add_font('arabic')
        for kind in ('vector','raster'):
            d=self.document('\u0628\u0628\u062a',kind,fallback=['arabic'],direction='rtl')
            self.assert_rectangles(d,[(16,2,3,0,10,6,'arabic'),(10,1,2,6,10,6,'arabic'),(9,0,1,12,10,6,'arabic')])
            self.assertEqual({g['script'] for g in self.glyphs(d)},{'Arab'})
            self.assertEqual(d['items'][0]['content']['frame']['text'],'\u0628\u0628\u062a')
        isolated=self.document('\u0628',fallback=['arabic'],direction='rtl')
        self.assertEqual([g['glyph_id'] for g in self.glyphs(isolated)],[8])

    def test_arabic_joining_context_crosses_style_and_selected_font_boundaries(self):
        self.add_font('beh',{0x628});self.add_font('teh',{0x62A})
        d=self.document('\u0628\u062a\u0628',font='beh',fallback=['teh'],direction='rtl')
        self.assert_rectangles(d,[(11,2,3,0,10,6,'beh'),(15,1,2,6,10,6,'teh'),(9,0,1,12,10,6,'beh')])
        style=copy.deepcopy(d['items'][0]['content']['frame']['style']);style['fill']=[220,20,40,128]
        revised=self.edit(d,[dict(op='text_range',id='label',start=1,end=2,style=style)])
        self.assertEqual(self.glyphs(d),self.glyphs(revised))
        outlines=self.inspect(revised,include_outlines=True)['layout']['paths']
        self.assertEqual(outlines[1]['fill'],[220,20,40,128])

    def test_canonical_composition_coverage_and_indivisible_mark_fallback(self):
        self.add_font('marks')
        # Latin face covers the composed glyph but neither decomposed acute nor A+acute.
        self.assert_rectangles(self.document('e\u0301',fallback=['marks']),[(5,0,2,0,10,5,'latin')])
        d=self.document('e\u0301A\u0301',fallback=['marks'])
        self.assert_rectangles(d,[(4,0,2,0,10,5,'marks'),(6,0,2,3,2.5,0,'marks'),(2,2,4,5,10,6,'marks'),(6,2,4,8,2.5,0,'marks')])
        self.assertEqual(self.edit(d,[dict(op='text_range',id='label',start=3,end=4,text='A')],1)['code'],'INVALID_DOCUMENT')
        self.add_font('acute',{0x301})
        split=self.document('A\u0301',fallback=['acute'])
        error=self.inspect(split,1)
        self.assertEqual(error['code'],'MISSING_GLYPH');self.assertIn('0..2',error['message'])
        self.assertIn('U+0301',error['message'])

    def test_indic_prebase_reordering_and_grapheme_clusters(self):
        self.add_font('indic')
        for kind in ('vector','raster'):
            d=self.document('\u0915\u093f\u0915',kind,fallback=['indic'])
            self.assert_rectangles(d,[(23,0,2,0,10,3,'indic'),(22,0,2,3,10,7,'indic'),(22,2,3,10,10,7,'indic')])
            self.assertEqual({g['script'] for g in self.glyphs(d)},{'Deva'})

    def test_script_extensions_cjk_hangul_greek_and_cyrillic_itemization(self):
        self.add_font('east');self.add_font('all')
        d=self.document('\u4e00\u3042\u30fc\u30a2\u30fc',fallback=['east'])
        self.assertEqual([g['script'] for g in self.glyphs(d)],['Hani','Hira','Hira','Kana','Kana'])
        self.assertEqual([g['origin'][0] for g in self.glyphs(d)],[0,10,20,30,40])
        hangul=self.document('\u1100\u1161',fallback=['east'])
        self.assert_rectangles(hangul,[(28,0,2,0,10,10,'east')])
        d=self.document('A\u03b1\u0416',fallback=['all'])
        self.assertEqual([g['script'] for g in self.glyphs(d)],['Latn','Grek','Cyrl'])
        self.assertEqual([g['font_id'] for g in self.glyphs(d)],['latin','all','all'])

    def test_whole_run_preference_order_actual_face_metrics_and_no_system_fonts(self):
        self.add_font('a',{65});self.add_font('b',{66},ascent=1400,advance_scale=2)
        self.add_font('whole',{65,66},ascent=1300,advance_scale=2)
        d=self.document('AB',font='a',fallback=['b','whole'])
        self.assert_rectangles(d,[(2,0,1,0,13,12,'whole'),(3,1,2,12,13,13,'whole')])
        d=self.document('AB',font='a',fallback=['b'])
        self.assert_rectangles(d,[(2,0,1,0,14,6,'a'),(3,1,2,6,14,13,'b')])
        self.assertEqual(self.inspect(self.document('X'),1)['code'],'MISSING_GLYPH')

    def test_default_ignorables_join_controls_and_empty_layout(self):
        self.add_font('arabic')
        d=self.document('\u0628\u200c\u0628',fallback=['arabic'],direction='rtl')
        self.assertEqual([g['glyph_id'] for g in self.glyphs(d)],[8,8])
        d=self.document('\u0628\u200d\u0628',fallback=['arabic'],direction='rtl')
        self.assertEqual([g['glyph_id'] for g in self.glyphs(d)],[11,9])
        d=self.document('\u200b\ufe0f')
        self.assertEqual(self.glyphs(d),[]);self.assertEqual(self.inspect(d)['layout']['lines'][0]['advance'],0)

    def test_wrap_reshapes_joining_at_line_boundaries_and_keeps_graphemes(self):
        self.add_font('arabic');self.add_font('marks')
        d=self.document('\u0628\u0628\u0628',fallback=['arabic'],direction='rtl',wrap=True,width=6)
        layout=self.inspect(d)['layout']
        self.assertEqual([(l['start'],l['end']) for l in layout['lines']],[(0,1),(1,2),(2,3)])
        self.assertEqual([g['glyph_id'] for g in layout['glyphs']],[8,8,8])
        d=self.document('A\u0301A\u0301',fallback=['marks'],wrap=True,width=6)
        self.assertEqual([(l['start'],l['end']) for l in self.inspect(d)['layout']['lines']],[(0,2),(2,4)])
        self.assertEqual([g['start'] for g in self.glyphs(d)],[0,0,2,2])

    def test_nonmonotone_ligature_advance_does_not_break_longest_fitting_prefix(self):
        self.add_font('compact','latin',ligature_advance=100)
        d=self.document('AffiB',font='compact',wrap=True,width=11)
        # A=6, Af=10, Aff=14, Affi=11, AffiB=17.5.
        layout=self.inspect(d)['layout']
        self.assertEqual([(l['start'],l['end'],l['advance']) for l in layout['lines']],[(0,4,11),(4,5,6.5)])
        self.assertEqual([g['glyph_id'] for g in layout['glyphs']],[2,24,26,3])

    def test_tracking_does_not_separate_marks_and_retains_required_joining(self):
        self.add_font('marks');self.add_font('arabic')
        d=self.document('A\u0301A\u0301',fallback=['marks'])
        frame=copy.deepcopy(d['items'][0]['content']['frame']);frame['style']['tracking']=2
        d=self.edit(d,[dict(op='text',id='label',frame=frame)])
        self.assertEqual([g['origin'][0] for g in self.glyphs(d)],[0,3,8,11])
        d=self.document('\u0628\u0628',fallback=['arabic'],direction='rtl')
        frame=copy.deepcopy(d['items'][0]['content']['frame']);frame['style']['tracking']=1
        d=self.edit(d,[dict(op='text',id='label',frame=frame)])
        self.assertEqual([g['glyph_id'] for g in self.glyphs(d)],[11,9])
        self.assertEqual([g['advance'] for g in self.glyphs(d)],[7,6])

    def test_strict_font_preferences_language_and_missing_resources(self):
        self.add_font('arabic')
        d=self.document('A',fallback=['arabic']);before=copy.deepcopy(d)
        for field,value,code in [('fallback_fonts',['latin'],'INVALID_DOCUMENT'),('fallback_fonts',['absent'],'INVALID_DOCUMENT'),
            ('fallback_fonts',['arabic']*8,'RESOURCE_LIMIT'),('language','','INVALID_DOCUMENT'),
            ('language','en--GB','INVALID_DOCUMENT'),('language','x'*65,'INVALID_DOCUMENT')]:
            bad=copy.deepcopy(d);bad['items'][0]['content']['frame']['style'][field]=value
            self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],code)
        frame=copy.deepcopy(d['items'][0]['content']['frame']);frame['style']['language']='ar-EG'
        changed=self.edit(d,[dict(op='text',id='label',frame=frame)])
        self.assertEqual(changed['items'][0]['content']['frame']['style']['language'],'ar-EG')
        self.assertEqual(self.inspect(changed)['layout'],self.inspect(d)['layout'])
        frame['style']['language']='tr'
        localized=self.edit(d,[dict(op='text',id='label',frame=frame)])
        self.assertEqual([g['glyph_id'] for g in self.glyphs(localized)],[3])
        self.assertEqual([g['advance'] for g in self.glyphs(localized)],[6.5])
        hidden=self.edit(d,[dict(op='properties',id='label',visible=False)])
        blob=self.store/(self.fonts['arabic']['sha256']+'.font');blob.unlink()
        error=self.invoke(dict(command='document.render',document=hidden,font_root=str(self.store)),1)
        self.assertEqual((error['code'],error['font_id']),('FONT_MISSING','arabic'))
        self.assertEqual(d,before)

    def test_fallback_resource_deletion_locking_and_atomic_rollback(self):
        self.add_font('arabic')
        d=self.document('\u0628',fallback=['arabic']);before=copy.deepcopy(d)
        self.assertEqual(self.edit(d,[dict(op='font_remove',id='arabic')],1)['code'],'FONT_IN_USE')
        locked=self.edit(d,[dict(op='properties',id='label',locked=True)])
        self.assertEqual(self.edit(locked,[dict(op='font_put',id='arabic',font=self.fonts['arabic'])],1)['code'],'LOCKED')
        self.assertEqual(self.edit(d,[dict(op='text_range',id='label',start=0,end=1,text='A'),dict(op='font_remove',id='arabic')],1)['operation_index'],1)
        self.assertEqual(d,before)

    def test_transfer_remaps_primary_and_fallback_fonts_and_preserves_sources(self):
        self.add_font('arabic');self.add_font('marks')
        source=self.document('A\u0301\u0628',fallback=['marks','arabic']);before=copy.deepcopy(source)
        empty=self.invoke(dict(command='document.create',id='destination',kind='vector',width=100,height=60))
        copied=self.edit(empty,[dict(op='transfer',transfer=dict(source=source,ids=['label'],prefix='copy',verify_resources=True))])
        style=copied['items'][0]['content']['frame']['style']
        self.assertEqual(style['font_id'],'copy-latin');self.assertEqual(style['fallback_fonts'],['copy-marks','copy-arabic'])
        self.assertEqual(set(copied['fonts']),{'copy-latin','copy-arabic','copy-marks'})
        self.assertEqual(self.pixels(source),self.pixels(copied));self.assertEqual(source,before)
        for name,data in self.sources.items(): self.assertEqual((self.directory/(name+'.ttf')).read_bytes(),data)

    def test_snapshot_source_ranges_replacement_and_default_compatibility(self):
        self.add_font('arabic')
        d=self.document('AA',fallback=['arabic'])
        style=copy.deepcopy(d['items'][0]['content']['frame']['style']);style['language']='ar'
        d=self.edit(d,[dict(op='text_range',id='label',start=0,end=1,text='\u0628',style=style)])
        snapshot=self.invoke(dict(command='document.export',document=d,format='snapshot'))
        self.assertEqual(json.loads(snapshot['data']),d)
        self.assertEqual(d['items'][0]['content']['frame']['ranges'][0]['style']['fallback_fonts'],['arabic'])
        old=self.document('A');s=old['items'][0]['content']['frame']['style']
        self.assertNotIn('fallback_fonts',s);self.assertNotIn('language',s)
        rtl=self.document('AB',direction='rtl')
        self.assertEqual([g['start'] for g in self.glyphs(rtl)],[1,0])

    def test_independent_rectangle_pixels_outlines_svg_and_transform(self):
        self.add_font('arabic')
        for kind in ('vector','raster'):
            d=self.document('\u0628\u0628\u062a',kind,fallback=['arabic'],direction='rtl')
            # Scale20 puts every original rectangle boundary on an integer pixel.
            d=self.edit(d,[dict(op='transform',id='label',matrix=[5,0,0,5,3,2])])
            result=self.invoke(dict(command='document.export',document=d,format='png',scale=4,font_root=str(self.store)))
            w,h,p=editing.png_pixels(base64.b64decode(result['data']))[:3]
            rects=[]
            for gid,x in [(16,0),(10,6),(9,12)]:
                x0,y0,x1,y1=rectangle(gid)
                rects.append([round(12+20*x+x0/5),round(208-y1/5),round(12+20*x+x1/5),round(208-y0/5)])
            expected=bytes(v for y in range(h) for x in range(w) for v in ([25,100,200,255] if any(a<=x<c and b<=y<e for a,b,c,e in rects) else [0]*4))
            self.assertEqual(p,expected)
            if kind=='vector':
                outlined=self.edit(d,[dict(op='text_outline',id='label')]);self.assertEqual(self.pixels(d),self.pixels(outlined))
                svg=self.invoke(dict(command='document.export',document=d,format='svg',font_root=str(self.store)))
                self.assertNotIn('<text',svg['data']);self.assertIn('<path',svg['data'])

    def test_path_text_uses_selected_face_and_retains_unicode_clusters(self):
        self.add_font('arabic')
        path=dict(geometry=dict(shape='path',commands=[dict(verb='move',to=[5,25]),dict(verb='line',to=[80,25])]))
        d=self.document('\u0628\u0628',fallback=['arabic'],direction='rtl',path=path)
        self.assertEqual([g['font_id'] for g in self.glyphs(d)],['arabic','arabic'])
        self.assertEqual([g['glyph_id'] for g in self.glyphs(d)],[11,9])
        self.assertEqual([g['origin'] for g in self.glyphs(d)],[[5,25],[11,25]])
        outlined=self.edit(d,[dict(op='text_outline',id='label')]);self.assertEqual(self.pixels(d),self.pixels(outlined))

    def test_inactive_dataset_fallback_references_are_kept_and_locked(self):
        self.add_font('arabic')
        d=self.document('A');style=dict(font_id='latin',fallback_fonts=['arabic'],size=10,fill=[10,20,30,255])
        value=dict(type='text',value=dict(text='\u0628',ranges=[dict(start=0,end=1,style=style)]))
        definition=dict(bindings=[dict(key='title',item_id='label',property='text')],
            datasets=dict(localized=dict(values=dict(title=value))))
        base=self.edit(d,[dict(op='variants_set',definition=definition)])
        self.assertEqual(self.edit(base,[dict(op='font_remove',id='arabic')],1)['code'],'FONT_IN_USE')
        locked=self.edit(base,[dict(op='properties',id='label',locked=True)])
        self.assertEqual(self.edit(locked,[dict(op='font_put',id='arabic',font=self.fonts['arabic'])],1)['code'],'LOCKED')
        active=self.edit(base,[dict(op='variant_select',dataset='localized')])
        self.assertEqual([g['font_id'] for g in self.glyphs(active)],['arabic'])
        restored=self.edit(active,[dict(op='variant_select',dataset=None)])
        self.assertEqual(restored['items'],d['items'])

    def test_component_fallback_dependencies_and_shared_mask_delivery(self):
        self.add_font('arabic');d=self.document('\u0628\u0628',fallback=['arabic'],direction='rtl')
        reference=self.pixels(d);d['items'][0]['parent']='source'
        d['items'].insert(0,dict(id='source',content=dict(type='component_source')))
        d['items'].append(dict(id='copy',content=dict(type='instance',instance=dict(source='source'))))
        self.assertEqual(self.pixels(d),reference)
        locked=copy.deepcopy(d);locked['items'][-1]['locked']=True
        self.assertEqual(self.edit(locked,[dict(op='font_put',id='arabic',font=self.fonts['arabic'])],1)['code'],'LOCKED')
        mask=self.document('\u0628\u0628',fallback=['arabic'],direction='rtl')
        mask['items'][0]['parent']='mask'
        mask['items'].insert(0,dict(id='mask',content=dict(type='mask_source')))
        mask['items'].append(dict(id='art',artwork_mask=dict(source='mask',mode='alpha',region=[0,0,100,60]),
            content=dict(type='vector',geometry=dict(shape='rect',x=0,y=0,width=100,height=60),fill=[25,100,200,255])))
        self.assertEqual(self.pixels(mask),reference)

    def test_shaping_budget_and_explicit_direction_control_boundaries(self):
        d=self.document('A'*4096,wrap=True,width=.1)
        self.assertEqual(self.inspect(d,1)['code'],'RESOURCE_LIMIT')
        for c in ('\u061c','\u200e','\u200f','\u2028','\u2029','\u2067'):
            bad=self.document()
            bad['items'][0]['content']['frame']['text']='A'+c+'B'
            self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],'UNSUPPORTED')
        self.add_font('arabic')
        d=self.document('\u0628\n\u0628',fallback=['arabic'],direction='rtl')
        self.assertEqual([g['glyph_id'] for g in self.glyphs(d)],[8,8])
        self.assertEqual([g['start'] for g in self.glyphs(d)],[0,2])

    def test_mcp_schema_persistent_fallback_history_retry_and_publication(self):
        self.add_font('arabic')
        d=self.document('AA',fallback=['arabic']);c=Client();self.addCleanup(lambda:c.close() if not c.process.stdin.closed else None);c.initialize()
        tools=[];cursor=None
        while True:
            page=c.rpc('tools/list',{} if cursor is None else dict(cursor=cursor))['result']
            tools.extend(page['tools']);cursor=page.get('nextCursor')
            if cursor is None: break
        schema=json.dumps(next(t for t in tools if t['name']=='inkbolt_document_edit'))
        self.assertIn('fallback_fonts',schema);self.assertIn('language',schema)
        session=dict(session_root=str(self.directory/'sessions'),session_id='unicode')
        c.success('session.create',**session,request_id='create',document=d,resources=dict(font_root=str(self.store)))
        args=dict(**session,expected_revision=0,request_id='shape',
            action=dict(type='edit',operations=[dict(op='text_range',id='label',start=0,end=2,text='\u0628\u0628')]))
        result=c.success('session.apply',**args);self.assertTrue(c.success('session.apply',**args)['replayed'])
        changed=result['document'];self.assertEqual([g['font_id'] for g in self.glyphs(changed)],['arabic','arabic'])
        c.close();c=Client();c.initialize()
        current=c.success('session.read',**session)['document'];self.assertEqual(current,changed)
        undone=c.success('session.apply',**session,expected_revision=current['revision'],request_id='undo',action=dict(type='undo'))['document']
        self.assertEqual(undone['items'],d['items'])
        redone=c.success('session.apply',**session,expected_revision=undone['revision'],request_id='redo',action=dict(type='redo'))['document']
        self.assertEqual(redone['items'],changed['items'])
        (self.directory/'delivery').mkdir()
        published=c.success('session.publish',**session,expected_revision=redone['revision'],
            output=dict(output_root=str(self.directory/'delivery'),file_name='text.png',format='png'))
        self.assertTrue((self.directory/'delivery/text.png').is_file())
        self.assertTrue(published)


if __name__=='__main__': unittest.main()
