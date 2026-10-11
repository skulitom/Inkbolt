"""Actual editable import: independent bytes, analytic pixels, repair and history."""
import base64,copy,hashlib,json,tempfile,unittest
from pathlib import Path
import layered_editable_text_fixtures as p
import layered_fixtures as f
import layered_object_fixtures as objects
import layered_text_fixtures as t
import test_layered_metadata_cli as m
import test_layered_font_bindings_cli as bindings
from test_layered_groups_cli import marker
from test_layered_masks_cli import masked
from test_mcp import Client


class EditableLayeredTextTests(unittest.TestCase):
    invoke=bindings.LayeredFontBindingTests.invoke
    setUp=bindings.LayeredFontBindingTests.setUp
    add_font=bindings.LayeredFontBindingTests.add_font
    bindings=bindings.LayeredFontBindingTests.bindings

    def args(self,raw):
        self.source.write_bytes(raw)
        return dict(command='layered.import',source_path=str(self.source),id='editable',color_policy='assume_srgb',
            expected_sha256=hashlib.sha256(raw).hexdigest(),text_fonts=dict(copy.deepcopy(self.bindings()),reconstruction='engine_layout'))

    def load(self,raw=None,expected=0,**changes):
        raw=p.source() if raw is None else raw;args=self.args(raw);args.update(changes)
        result=self.invoke(args,expected);self.assertEqual(self.source.read_bytes(),raw);return result

    def pixels(self,d):
        return bytes.fromhex(self.invoke(dict(command='document.render',document=d,font_root=str(self.store)))['data'])

    def test_independent_point_pixels_baseline_font_and_cache_separation(self):
        for version in [1,2]:
            r=self.load(p.source(version=version));d=r['document'];i=d['items'][0];frame=i['content']['frame']
            self.assertEqual(i['content']['type'],'text');self.assertEqual(frame['text'],'AA');self.assertEqual(i['transform'],[1,0,0,1,8,30])
            self.assertEqual(frame['first_baseline'],dict(metric='fixed',minimum=0));self.assertFalse(frame['wrap']);self.assertEqual(frame['overflow'],'visible')
            self.assertEqual(d['fonts'][frame['style']['font_id']],self.font);self.assertEqual(r['text'][0]['text_source'],'local_record')
            self.assertFalse(r['text'][0]['cached_pixels_used']);self.assertFalse(r['text'][0]['native_layout_equality'])
            self.assertEqual(r['text'][0]['cached_rgba_sha256'],hashlib.sha256(bytes([9,80,7,255])).hexdigest())
            # Original glyph A is x=50..450, y=0..700 / 1000, advance=600.
            expected=bytes(v for y in range(48) for x in range(64) for v in
                ([255,0,0,255] if 16<=y<30 and (9<=x<17 or 21<=x<29) else [0,0,0,0]))
            self.assertEqual(self.pixels(d),expected)
            self.assertEqual(self.invoke(dict(command='text.inspect',document=d,id=i['id'],font_root=str(self.store)))['layout']['lines'][0]['baseline'],0)

    def test_authoritative_global_text_styles_and_reordered_story_indices(self):
        g=p.global_data(('AA','A'));g['1']['1'][1]['0']['6']['0'][0]['0']['0']['6']['53']['0']['1']=[1.0,0.0,1.0,0.0]
        for version in [1,2]:
            layers=[p.layer('BB',index=1,id=10),p.layer('B',index=0,id=20,matrix=(1,0,0,1,8,46))]
            r=self.load(p.source(layers,g,version));by_id={i['id']:i for i in r['document']['items']}
            self.assertNotIn('global:Txt2',r['omitted_nonappearance_records'])
            self.assertEqual(by_id['layer-10']['content']['frame']['text'],'A');self.assertEqual(by_id['layer-20']['content']['frame']['text'],'AA')
            self.assertEqual(by_id['layer-10']['content']['frame']['style']['fill'],[0,255,0,255])
            for receipt in r['text']:
                self.assertEqual(receipt['text_source'],'global_story');self.assertFalse(receipt['local_text_matches']);self.assertFalse(receipt['cached_pixels_used'])
            pixels=self.pixels(r['document']);self.assertEqual(pixels[(20*64+10)*4:(20*64+10)*4+4],bytes([0,255,0,255]))

    def test_utf16_style_runs_convert_to_characters_and_preserve_scaled_tracking(self):
        text='A😀A';styles=[p.style(),p.style(FontSize=10.0,HorizontalScale=2.0,VerticalScale=.5,Tracking=75,BaselineShift=2.0),p.style()]
        payload=p.local(text,styles=styles,lengths=[1,2,2])
        frame=self.load(p.source([p.layer(text,payload)]))['document']['items'][0]['content']['frame']
        self.assertEqual(frame['text'],text);self.assertEqual(len(frame['ranges']),1);r=frame['ranges'][0]
        self.assertEqual((r['start'],r['end']),(1,2));self.assertEqual(r['style']['tracking'],1.5)
        self.assertEqual((r['style']['horizontal_scale'],r['style']['vertical_scale'],r['style']['baseline_shift']),(2,.5,2))

    def test_affine_point_matrix_has_independently_calculated_pixels(self):
        d=self.load(p.source([p.layer(matrix=(0,1,-1,0,35,8))]))['document']
        expected=bytes(v for y in range(48) for x in range(64) for v in
            ([255,0,0,255] if 35<=x<49 and (9<=y<17 or 21<=y<29) else [0,0,0,0]))
        self.assertEqual(self.pixels(d),expected)

    def test_nested_editable_sources_receive_the_same_explicit_font_policy(self):
        nested=p.source(g=p.global_data());expected=self.pixels(self.load(nested)['document'])
        for version in [1,2]:
            layer=dict(name='Placed text',width=1,height=1,rgba=[0,0,255,255],extra=objects.placement(size=(64,48),matrix=(1,0,0,1,0,0)))
            raw=f.make([layer],w=64,h=48,version=version,global_extra=objects.global_sources([objects.entry(nested)],version=version))
            r=self.load(raw,embedded_objects=objects.POLICY);i=r['document']['items'][0]
            source=json.loads(i['content']['object']['snapshot']);self.assertEqual(source['items'][0]['content']['type'],'text')
            self.assertEqual(r['embedded_sources'][0]['text'][0]['text_source'],'global_story')
            self.assertEqual(self.pixels(r['document']),expected)

    def test_editable_delivery_reimport_retains_point_origin_pixels_and_text(self):
        d=self.load()['document'];before=self.pixels(d)
        for version in ['layered','layered_large']:
            artifact=self.invoke(dict(command='document.export',document=d,format=version,font_root=str(self.store),
                layered_options=dict(text=dict(reconstruction='native_layout',shape_owner='OriginalGeometry'))))
            raw=base64.b64decode(artifact['data']);r=self.load(raw);frame=r['document']['items'][0]['content']['frame']
            self.assertEqual(frame['text'],'AA');self.assertEqual(self.pixels(r['document']),before)
            self.assertEqual(r['document']['items'][0]['transform'],d['items'][0]['transform'])

    def test_group_and_linked_or_unlinked_mask_preserve_world_coverage(self):
        for linked in [True,False]:
            layer=masked(p.layer(id=2),gray=bytes([255])*7*14,box=(16,10,30,17),flags=0 if linked else 1)
            r=self.load(p.source([marker(3,id=0),layer,marker(1,id=3)]));d=r['document'];i=next(i for i in d['items'] if i['id']=='layer-2')
            self.assertEqual(i['parent'],'layer-3');self.assertEqual(i['mask']['linked'],linked)
            self.assertEqual(i['mask']['transform'],[1,0,0,1,2,-14] if linked else [1,0,0,1,10,16])
            expected=bytes(v for y in range(48) for x in range(64) for v in ([255,0,0,255] if 16<=y<30 and 10<=x<17 else [0,0,0,0]))
            self.assertEqual(self.pixels(d),expected)

    def test_explicit_opt_in_missing_fields_unmapped_semantics_and_bad_modes(self):
        args=self.args(p.source());del args['text_fonts']['reconstruction']
        self.assertEqual(self.invoke(args,1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        for field,value in [('FontSize',None),('FauxBold',True),('Unknown',0),('AutoLeading',True),('FontCaps',1),('StrokeFlag',True),('Kerning',2),('FillFlag',False)]:
            payload=p.local();style=payload['EngineDict']['StyleRun']['RunArray'][0]['StyleSheet']['StyleSheetData']
            if value is None:del style[field]
            else:style[field]=value
            with self.subTest(field=field):self.assertEqual(self.load(p.source([p.layer(payload=payload)]),1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        for key,value in [('Ornt',m.enum('Ornt','Vrtc')),('AntA',m.enum('Annt','AnSm')),('TxMP',m.boolean(True)),('oldText',m.boolean(False))]:
            layer=p.layer();layer['extra']=f.tag(b'TySh',t.record('AA',engine=t.data(p.local()),changes={key:value}))
            self.assertEqual(self.load(p.source([layer]),1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        payload=p.local();payload['EngineDict']['Rendered']['Shapes']['Children'][0]['Cookie']['OriginalGeometry']['PointBase']=[1.0,0.0]
        self.assertEqual(self.load(p.source([p.layer(payload=payload)]),1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        payload=p.local();payload['ResourceDict']['StyleSheetSet']=[dict(Name='Unmapped default',StyleSheetData={'Underline':True})]
        self.assertEqual(self.load(p.source([p.layer(payload=payload)]),1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        payload=p.local();payload['EngineDict']['StyleRun']['RunArray'][0]['StyleSheet']['StyleSheetData']['Ligatures']=True
        self.assertEqual(self.load(p.source([p.layer(payload=payload)]),1)['code'],'FONT_FEATURE_UNAVAILABLE')
        payload=p.local();payload['ResourceDict']['FontSet'][0]['Synthetic']=1
        self.assertEqual(self.load(p.source([p.layer(payload=payload)]),1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')

    def test_empty_source_and_corrupt_caches_keep_their_distinct_meanings(self):
        d=self.load(p.source([p.layer('')]))['document'];self.assertEqual(d['items'][0]['content']['frame']['text'],'')
        self.assertEqual(self.pixels(d),bytes(64*48*4))
        self.assertEqual(self.load(p.source()[:-1],1)['code'],'INVALID_LAYERED_FILE')
        layer=p.layer();layer['channel_data']=[b'\x00\x00']*4
        self.assertEqual(self.load(p.source([layer]),1)['code'],'INVALID_LAYERED_FILE')

    def test_distinct_terminal_insertion_style_is_not_silently_discarded(self):
        payload=p.local('A',styles=[p.style(),p.style(FontSize=10.0)],lengths=[1,1])
        self.assertEqual(self.load(p.source([p.layer('A',payload)]),1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        payload=p.local('A',styles=[p.style(),p.style()],lengths=[1,1])
        self.assertEqual(self.load(p.source([p.layer('A',payload)]))['document']['items'][0]['content']['frame']['text'],'A')

    def test_global_references_unknown_controls_and_invalid_geometry_never_fall_back(self):
        g=p.global_data(('AA','A'))
        for layers in [[p.layer(index=0)],[p.layer(index=0,id=1),p.layer(index=0,id=2)]]:
            self.assertIn(self.load(p.source(layers,g),1)['code'],['INVALID_LAYERED_FILE','UNSUPPORTED_LAYERED_SEMANTICS'])
        for change in ['frame','style','paragraph','kerning','stroke']:
            g=p.global_data()
            if change=='frame':g['0']['8']['0'][0]['0']['2']['2']=[1,0,0,1,1,0]
            elif change=='paragraph':g['1']['1'][0]['0']['5']['0'][0]['0']['0']['5']['1']=1.0
            else:g['1']['1'][0]['0']['6']['0'][0]['0']['0']['6'][{'style':'999','kerning':'11','stroke':'54'}[change]]=0
            self.assertIn(self.load(p.source(g=g),1)['code'],['INVALID_LAYERED_FILE','UNSUPPORTED_LAYERED_SEMANTICS'])
        self.assertEqual(self.load(p.source([p.layer(index=-1)],p.global_data()),1)['code'],'INVALID_LAYERED_FILE')

    def test_edited_saved_text_retry_undo_and_cli_mcp_parity(self):
        raw=p.source(g=p.global_data());args=self.args(raw);r=self.invoke(args);d=r['document'];before=self.pixels(d)
        c=Client()
        try:
            c.initialize();response=c.tool('layered.import',**{k:v for k,v in args.items() if k!='command'})
            self.assertFalse(response.get('isError',False));self.assertEqual(response['structuredContent']['result'],r)
        finally:c.close()
        common=dict(session_root=str(self.root/'sessions'),session_id='text')
        created=self.invoke(dict(command='session.create',**common,request_id='create',document=d,resources=dict(font_root=str(self.store))))
        frame=copy.deepcopy(d['items'][0]['content']['frame']);frame['text']='A'
        edit=dict(command='session.apply',**common,request_id='edit',expected_revision=0,action=dict(type='edit',operations=[dict(op='text',id=d['items'][0]['id'],frame=frame)]))
        changed=self.invoke(edit);self.assertEqual(self.invoke(edit),dict(changed,replayed=True));self.assertNotEqual(self.pixels(changed['document']),before)
        undo=self.invoke(dict(command='session.apply',**common,request_id='undo',expected_revision=1,action=dict(type='undo')))
        self.assertEqual(undo['document']['items'],created['document']['items']);self.assertEqual(self.pixels(undo['document']),before)
        self.assertTrue(self.invoke(dict(command='session.verify',**common))['valid']);self.assertEqual(self.source.read_bytes(),raw)

    def test_invalid_fonts_hash_cancellation_and_missing_glyphs_fail_before_document(self):
        raw=p.source();args=self.args(raw);args['text_fonts']['bindings'][0]['font']['sha256']='0'*64
        self.assertEqual(self.invoke(args,1)['code'],'FONT_MISSING')
        args=self.args(raw);args['expected_sha256']='0'*64;self.assertEqual(self.invoke(args,1)['code'],'SOURCE_MISMATCH')
        args=self.args(raw);args['control']=dict(timeout_ms=0);self.assertEqual(self.invoke(args,1)['code'],'TIMEOUT')
        error=self.load(p.source([p.layer('X')]),1);self.assertNotIn('document',error)
        self.assertEqual(error['code'],'MISSING_GLYPH')


if __name__=='__main__':unittest.main()
