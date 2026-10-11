"""Original geometric text with independent character scale and baseline oracles."""
import copy,json,unittest
import test_text_cli as text
import test_story_cli as stories
import test_path_text_cli as path
import test_layered_text_export_cli as delivery
from test_first_baseline_cli import metric_font
from synthetic_unicode_font import unicode_font
from synthetic_variable_font import variable_font
from synthetic_font import geometric_font
from test_mcp import Client


class CharacterTransformTests(unittest.TestCase):
    setUp=text.TextCliTests.setUp
    invoke=text.TextCliTests.invoke
    document=text.TextCliTests.document
    edit=text.TextCliTests.edit
    inspect=text.TextCliTests.inspect
    pixels=text.TextCliTests.pixels

    def changed(self,d,**options):
        frame=copy.deepcopy(d['items'][0]['content']['frame']);frame['style'].update(options)
        return self.edit(d,[dict(op='text',id='label',frame=frame)])

    def test_scaled_outlines_metrics_pixels_and_default_snapshot_compatibility(self):
        for kind in ['vector','raster']:
            d=self.document(kind,text='AA',overflow='visible');style=d['items'][0]['content']['frame']['style']
            for key in ['horizontal_scale','vertical_scale','baseline_shift']:self.assertNotIn(key,style)
            explicit=self.changed(d,horizontal_scale=1,vertical_scale=1,baseline_shift=0)
            self.assertEqual(explicit['items'],d['items'])
            scaled=self.changed(d,horizontal_scale=2,vertical_scale=1.5,baseline_shift=-2)
            layout=self.inspect(scaled)['layout']
            self.assertEqual(layout['lines'][0]['baseline'],12);self.assertEqual(layout['lines'][0]['advance'],24)
            self.assertEqual([g['origin'] for g in layout['glyphs']],[[0,14],[12,14]])
            self.assertEqual(layout['ink_bounds'],[1,3.5,21,14])
            w,h,p=self.pixels(scaled)
            for y in range(h):
                for x in range(w):
                    pixel=p[(y*w+x)*4:][:4]
                    if 4<=y<14 and (1<=x<9 or 13<=x<21):self.assertEqual(pixel,bytes([25,100,200,255]))
                    elif y<3 or y>=14 or x<1 or x>=21:self.assertEqual(pixel,bytes(4))
            if kind=='vector':self.assertEqual(self.pixels(scaled),self.pixels(self.edit(scaled,[dict(op='text_outline',id='label')])))

    def test_tracking_remains_local_pixels_after_glyph_scaling_and_wrapping(self):
        d=self.document(text='AA AA',width=29,height=50,overflow='visible')
        d=self.changed(d,horizontal_scale=2,tracking=2)
        layout=self.inspect(d)['layout']
        self.assertEqual([(l['start'],l['end'],l['advance']) for l in layout['lines']],[(0,2,26),(3,5,26)])
        self.assertEqual([g['origin'][0] for g in layout['glyphs']],[0,14,0,14])
        # Positive shifts move ink up, without changing line baselines/advances.
        shifted=self.changed(d,baseline_shift=3);a=self.inspect(shifted)['layout']
        self.assertEqual(a['lines'],layout['lines'])
        for x,y in zip(a['glyphs'],layout['glyphs']):
            self.assertEqual(x['origin'],[y['origin'][0],y['origin'][1]-3]);self.assertEqual(x['advance'],y['advance'])

    def test_mixed_ranges_scaled_kerning_and_explicit_leading(self):
        d=self.document(text='AB\nAA',leading=20,overflow='visible')
        d=self.changed(d,horizontal_scale=1.5,vertical_scale=2,baseline_shift=4)
        layout=self.inspect(d)['layout']
        self.assertEqual([l['baseline'] for l in layout['lines']],[16,36])
        self.assertEqual([g['origin'] for g in layout['glyphs']],[[0,12],[7.5,12],[0,32],[9,32]])
        self.assertEqual(layout['lines'][0]['advance'],25.5)
        style=dict(font_id='geometry',size=10,fill=[100,20,50,255],horizontal_scale=.5,vertical_scale=3,baseline_shift=-2)
        mixed=self.edit(d,[dict(op='text_range',id='label',start=1,end=2,style=style)])
        g=self.inspect(mixed)['layout']['glyphs'];self.assertEqual(g[1]['origin'][1],26)
        self.assertEqual(g[1]['ink_bounds'][2]-g[1]['ink_bounds'][0],5)
        self.assertEqual(g[1]['ink_bounds'][3]-g[1]['ink_bounds'][1],15)

    def test_baseline_shift_overflow_and_clipping_do_not_move_the_frame(self):
        d=self.changed(self.document(text='A',width=20,height=10),baseline_shift=4)
        self.assertEqual(self.inspect(d,1)['code'],'TEXT_OVERFLOW')
        frame=copy.deepcopy(d['items'][0]['content']['frame']);frame['overflow']='clip'
        clip=self.edit(d,[dict(op='text',id='label',frame=frame),dict(op='transform',id='label',matrix=[1,0,0,1,0,10])])
        w,h,p=self.pixels(clip);self.assertTrue(any(p));self.assertTrue(all(p[(y*w+x)*4+3]==0 for y in range(10) for x in range(w)))
        outlined=self.edit(clip,[dict(op='text_outline',id='label')]);self.assertEqual(self.pixels(clip),self.pixels(outlined))

    def test_path_text_rotates_the_scaled_glyph_and_shift_as_one_placement(self):
        d=self.document(text='AA',wrap=False,path=path.line((20,5),(20,55)),overflow='visible')
        d=self.changed(d,horizontal_scale=2,vertical_scale=1.5,baseline_shift=3)
        layout=self.inspect(d)['layout']
        self.assertEqual([g['origin'] for g in layout['glyphs']],[[23,5],[23,17]])
        self.assertEqual(layout['glyphs'][0]['ink_bounds'],[23,6,33.5,14])
        self.assertEqual(layout['lines'][0]['advance'],24)
        self.assertEqual(self.pixels(d),self.pixels(self.edit(d,[dict(op='text_outline',id='label')])))

    def test_linked_columns_use_scaled_metrics_and_keep_source_intervals(self):
        p=stories.StoryTests.paragraph(self,'AAAAAA');p['style'].update(horizontal_scale=2,vertical_scale=1.5,baseline_shift=1)
        d=stories.StoryTests.document(self,[p],[dict(id='first',width=24,height=15),dict(id='second',width=24,height=30)])
        r=stories.StoryTests.inspect(self,d)['layout'];self.assertIsNone(r['overset'])
        self.assertEqual([(l['slot_id'],l['start'],l['end']) for l in r['lines']],[('first',0,2),('second',2,4),('second',4,6)])
        self.assertEqual([g['origin'] for g in r['slots']['first']['glyphs']],[[0,11],[12,11]])
        self.assertEqual([g['origin'][1] for g in r['slots']['second']['glyphs']],[11,11,26,26])
        self.assertEqual(d['stories']['article']['paragraphs'][0]['text'],'AAAAAA')
        outlined=self.edit(d,[dict(op='text_outline',id='first'),dict(op='text_outline',id='second')]);self.assertEqual(self.pixels(d),self.pixels(outlined))

    def add_font(self,name,raw):
        p=self.directory/(name+'.ttf');p.write_bytes(raw)
        return self.invoke(dict(command='font.import',source_path=str(p),license_path=str(self.license),store_root=str(self.store)))

    def test_first_baseline_metrics_fallbacks_and_variable_instances_scale_together(self):
        metrics=self.add_font('metrics',metric_font());east=self.add_font('east',metric_font(cap=900,raw=unicode_font('east')))
        d=self.document(text='A\u4e00',overflow='visible');d=self.edit(d,[dict(op='font_put',id='geometry',font=metrics),dict(op='font_put',id='east',font=east)])
        d=self.changed(d,fallback_fonts=['east'],horizontal_scale=1.5,vertical_scale=2,baseline_shift=3)
        frame=copy.deepcopy(d['items'][0]['content']['frame']);frame['first_baseline']=dict(metric='cap_height')
        d=self.edit(d,[dict(op='text',id='label',frame=frame)]);layout=self.inspect(d)['layout']
        self.assertEqual(layout['lines'][0]['baseline'],18);self.assertEqual([g['origin'][1] for g in layout['glyphs']],[15,15])
        self.assertEqual([g['font_id'] for g in layout['glyphs']],['geometry','east'])
        variable=self.add_font('variable',variable_font());d=self.document(text='AA',overflow='visible')
        d=self.edit(d,[dict(op='font_put',id='geometry',font=variable)])
        d=self.changed(d,font_variations={'geometry':{'wght':900}});base=self.inspect(d)['layout']
        scaled=self.changed(d,horizontal_scale=2,vertical_scale=1.5,baseline_shift=-2);after=self.inspect(scaled)['layout']
        self.assertEqual(after['lines'][0]['baseline'],base['lines'][0]['baseline']*1.5)
        for a,b in zip(base['glyphs'],after['glyphs']):
            self.assertEqual(b['advance'],a['advance']*2);self.assertEqual(b['origin'],[a['origin'][0]*2,a['origin'][1]*1.5+2])
            self.assertEqual(b['variations'],a['variations'])

    def test_generated_markers_and_hyphens_keep_character_controls(self):
        p=stories.StoryTests.paragraph(self,'AA');p['indent_start']=20
        p['list']=dict(id='bullets',level=0,marker=dict(type='bullet',text='A'),gap=2,
                       style=dict(p['style'],horizontal_scale=2,vertical_scale=2,baseline_shift=-2))
        d=stories.StoryTests.document(self,[p],[dict(id='first',width=60,height=30)])
        layout=stories.StoryTests.inspect(self,d)['layout'];marker=layout['lines'][0]['marker']
        g=layout['slots']['first']['glyphs'][marker['glyph_start']]
        self.assertEqual(g['advance'],12);self.assertEqual(g['origin'],[6,18])
        self.assertEqual(g['ink_bounds'],[7,4,15,18])
        self.assertEqual(self.pixels(d),self.pixels(self.edit(d,[dict(op='text_outline',id='first')])))
        self.font=self.add_font('hyphens',geometric_font(additional_mapping={45:2,0x2010:2}))
        p=stories.StoryTests.paragraph(self,'AAAAAAAA');p['style'].update(horizontal_scale=1.5,vertical_scale=1.5,baseline_shift=-1)
        p['hyphenation']=dict(rules_id='words');rules=dict(min_left=2,min_right=2,patterns=[dict(text='A',weights=[1,1])])
        d=stories.StoryTests.document(self,[p],[dict(id='first',width=36,height=60)],hyphenation_rules={'words':rules})
        layout=stories.StoryTests.inspect(self,d)['layout'];glyphs=layout['slots']['first']['glyphs']
        generated=[g for g in glyphs if g.get('generated',{}).get('type')=='hyphen']
        self.assertEqual(len(generated),2);self.assertEqual([g['advance'] for g in generated],[9,9])
        self.assertEqual([g['origin'][1] for g in generated],[13,28]);self.assertEqual([g['ink_bounds'][3]-g['ink_bounds'][1] for g in generated],[10.5,10.5])
        self.assertEqual(d['stories']['article']['paragraphs'][0]['text'],'AAAAAAAA')
        self.assertEqual(self.pixels(d),self.pixels(self.edit(d,[dict(op='text_outline',id='first')])))

    def test_limits_source_preservation_and_mcp_durable_retries(self):
        d=self.document(text='AA',overflow='visible');original=self.source.read_bytes()
        for key in ['horizontal_scale','vertical_scale']:
            for value in [0,-1,.0099,10.0001]:
                bad=copy.deepcopy(d);bad['items'][0]['content']['frame']['style'][key]=value
                self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],'INVALID_DOCUMENT')
        for value in [-32768.01,32768.01]:
            bad=copy.deepcopy(d);bad['items'][0]['content']['frame']['style']['baseline_shift']=value
            self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],'INVALID_DOCUMENT')
        shifted=self.changed(d,horizontal_scale=1.25,vertical_scale=.75,baseline_shift=-3)
        self.assertEqual(json.loads(self.invoke(dict(command='document.export',document=shifted,format='snapshot'))['data']),shifted)
        args=dict(session_root=str(self.directory/'sessions'),session_id='characters')
        created=self.invoke(dict(command='session.create',**args,request_id='create',document=d,resources=dict(font_root=str(self.store))))
        request=dict(command='session.apply',**args,request_id='change',expected_revision=0,action=dict(type='edit',operations=[dict(op='text',id='label',frame=shifted['items'][0]['content']['frame'])]))
        changed=self.invoke(request);self.assertEqual(self.invoke(request),dict(changed,replayed=True))
        undo=self.invoke(dict(command='session.apply',**args,request_id='undo',expected_revision=1,action=dict(type='undo')))
        self.assertEqual(undo['document']['items'],created['document']['items'])
        redo=self.invoke(dict(command='session.apply',**args,request_id='redo',expected_revision=2,action=dict(type='redo')))
        self.assertEqual(self.pixels(redo['document']),self.pixels(shifted))
        client=Client()
        try:
            client.initialize();self.assertEqual(client.success('text.inspect',document=shifted,id='label',font_root=str(self.store)),self.inspect(shifted))
        finally:client.close()
        self.assertTrue(self.invoke(dict(command='session.verify',**args))['valid']);self.assertEqual(self.source.read_bytes(),original)


class CharacterDeliveryTests(unittest.TestCase):
    invoke=delivery.LayeredTextExportTests.invoke
    document=delivery.LayeredTextExportTests.document
    setUp=delivery.LayeredTextExportTests.setUp
    add_font=delivery.LayeredTextExportTests.add_font
    scene=delivery.LayeredTextExportTests.scene
    export=delivery.LayeredTextExportTests.export
    parse=delivery.LayeredTextExportTests.parse

    def test_native_fields_tracking_compensation_and_scaled_leading(self):
        for h,v,shift,tracking,units in [(1.5,2,4,3,83),(.5,.75,-3,3,250),(2,1.5,0,6,125)]:
            d=self.scene('AA',overflow='visible');d['items'][0]['content']['frame']['style'].update(horizontal_scale=h,vertical_scale=v,baseline_shift=shift,tracking=tracking)
            original=copy.deepcopy(d);artifact,_,record=self.parse(d)
            s=record['data']['EngineDict']['StyleRun']['RunArray'][0]['StyleSheet']['StyleSheetData']
            self.assertEqual((s['HorizontalScale'],s['VerticalScale'],s['BaselineShift'],s['Tracking'],s['Leading']),(h,v,shift,units,24*v))
            self.assertEqual(record['matrix'][:5],[1,0,0,1,8])
            self.assertAlmostEqual(record['matrix'][5],10+19.2*v,places=12)
            receipt=artifact['layered']['text'][0]['tracking_quantization']
            expected=[] if h!=1.5 else [dict(style_index=0,source_pixels=3,native_thousandths_em=83,delivered_pixels=83*24*1.5/1000)]
            self.assertEqual(receipt,expected);self.assertEqual(d,original)
            self.assertFalse(artifact['layered']['text'][0]['native_layout_equality'])

    def test_native_decimal_spelling_is_short_fixed_and_round_trips(self):
        for scale,shift in [(.01,1e-7),(.1,-1e-7),(.01001,.1),(.123456789,0)]:
            d=self.scene('A',overflow='visible');d['items'][0]['content']['frame']['style'].update(horizontal_scale=scale,vertical_scale=scale,baseline_shift=shift)
            _,parsed,r=self.parse(d);raw=parsed['layers'][0]['tags'][b'TySh']
            self.assertIn(('/HorizontalScale '+str(scale)+' ').encode(),raw)
            if shift==1e-7:self.assertIn(b'/BaselineShift 0.0000001 ',raw)
            if shift==-1e-7:self.assertIn(b'/BaselineShift -0.0000001 ',raw)
            style=r['data']['EngineDict']['StyleRun']['RunArray'][0]['StyleSheet']['StyleSheetData']
            self.assertEqual((style['HorizontalScale'],style['VerticalScale'],style['BaselineShift']),(scale,scale,shift))
        # A fixed literal for this finite value exceeds the existing native-data
        # parser's token bound. Refuse delivery without rounding away its value.
        d=self.scene('A',overflow='visible');d['items'][0]['content']['frame']['style']['baseline_shift']=5e-324
        error=self.export(d,expected=1);self.assertEqual(error['code'],'UNSUPPORTED_LAYERED_SEMANTICS');self.assertIn('128-byte',error['message'])

    def test_native_tracking_integer_bound_is_checked_after_scale_compensation(self):
        for units in [-2147483649,-2147483648,-2147483647,2147483647,2147483648,10240000000]:
            d=self.scene('A',overflow='visible')
            d['items'][0]['content']['frame']['style'].update(size=.01,horizontal_scale=.01,tracking=units*.0001/1000)
            if -2147483647<=units<=2147483647:
                _,_,r=self.parse(d)
                self.assertEqual(r['data']['EngineDict']['StyleRun']['RunArray'][0]['StyleSheet']['StyleSheetData']['Tracking'],units)
            else:
                error=self.export(d,expected=1);self.assertEqual(error['code'],'UNSUPPORTED_LAYERED_SEMANTICS');self.assertIn('32-bit',error['message']);self.assertEqual(error['item_id'],'text')


if __name__=='__main__':unittest.main()
