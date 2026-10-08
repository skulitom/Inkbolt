"""Original bidi/layout cases with logical-index, geometry and pixel oracles."""
import base64
import copy
import json
from pathlib import Path
import unittest
import test_unicode_text_cli as unicode_tests
import test_editing_cli as editing
from test_mcp import Client
from synthetic_bidi_font import bidi_font, MAPPING
from synthetic_unicode_font import rectangle, ADVANCES


class BidiTextTests(unittest.TestCase):
    invoke=unicode_tests.UnicodeTextTests.invoke
    edit=unicode_tests.UnicodeTextTests.edit
    inspect=unicode_tests.UnicodeTextTests.inspect
    pixels=unicode_tests.UnicodeTextTests.pixels
    glyphs=unicode_tests.UnicodeTextTests.glyphs
    document=unicode_tests.UnicodeTextTests.document
    setUp=unicode_tests.UnicodeTextTests.setUp

    def add_font(self,name,codes=None,**kw):
        path=self.directory/(name+'.ttf');data=bidi_font(codes,**kw);path.write_bytes(data)
        self.sources[name]=data
        self.fonts[name]=self.invoke(dict(command='font.import',source_path=str(path),
            license_path=str(self.license),store_root=str(self.store)))
        return name

    def make(self,text,kind='vector',**kw):
        return self.document(text,kind,bidi='unicode',direction=kw.pop('direction','auto'),**kw)

    def directions(self,text,direction='auto',lines=None,status=0):
        return self.invoke(dict(command='text.directions',text=text,direction=direction,lines=lines or []),status)

    def order(self,d):return [g['start'] for g in self.glyphs(d)]

    def test_mixed_hebrew_latin_and_numbers_have_logical_clusters_visual_placement(self):
        for kind in ('vector','raster'):
            d=self.make('A \u05d0\u05d1 12 B',kind)
            self.assertEqual(self.order(d),[0,1,5,6,4,3,2,7,8])
            g=self.glyphs(d)
            self.assertEqual([v['glyph_id'] for v in g],[2,1,3,4,1,18,17,1,3])
            self.assertEqual([v['level'] for v in g],[0,0,2,2,1,1,1,0,0])
            self.assertEqual([v['direction'] for v in g],['ltr','ltr','ltr','ltr','rtl','rtl','rtl','ltr','ltr'])
            self.assertEqual(d['items'][0]['content']['frame']['text'],'A \u05d0\u05d1 12 B')

    def test_auto_base_explicit_base_and_legacy_single_run_compatibility(self):
        text='\u05d0\u05d1 AB'
        self.assertEqual(self.order(self.make(text)),[3,4,2,1,0])
        self.assertEqual(self.order(self.make(text,direction='ltr')),[1,0,2,3,4])
        legacy=self.document('AB',direction='rtl')
        self.assertEqual(self.order(legacy),[1,0]);self.assertNotIn('bidi',legacy['items'][0]['content']['frame'])
        self.assertEqual(self.order(self.make('AB',direction='rtl')),[0,1])
        self.assertNotIn('level',self.glyphs(legacy)[0])

    def test_paragraph_base_is_independent_and_start_end_alignment_follows_it(self):
        d=self.make('AB\n\u05d0\u05d1\n12\n',align='start')
        lines=self.inspect(d)['layout']['lines']
        self.assertEqual([v['direction'] for v in lines],['ltr','rtl','ltr','ltr'])
        self.assertEqual([v['x'] for v in lines],[0,86,0,0])
        self.assertEqual([(v['start'],v['end']) for v in lines],[(0,2),(3,5),(6,8),(9,9)])
        f=copy.deepcopy(d['items'][0]['content']['frame']);f['align']='end'
        e=self.edit(d,[dict(op='text',id='label',frame=f)])
        self.assertEqual([v['x'] for v in self.inspect(e)['layout']['lines']],[87.5,0,88.5,100])

    def test_wrapping_retains_original_paragraph_base_and_resets_trailing_spaces(self):
        d=self.make('\u05d0 A B',width=8,wrap=True,align='start')
        lines=self.inspect(d)['layout']['lines']
        self.assertEqual([(v['start'],v['end'],v['direction']) for v in lines],[(0,1,'rtl'),(2,3,'rtl'),(4,5,'rtl')])
        self.assertEqual([v['x'] for v in lines],[1,2,1.5])
        r=self.directions('A \u05d0  B',lines=[dict(start=0,end=4),dict(start=4,end=6)])
        self.assertEqual(r['lines'][0]['levels'],[0,0,1,0])
        self.assertEqual(r['lines'][0]['visual_order'],[0,1,2,3])

    def test_arabic_joining_wrap_and_style_boundaries_preserve_forms(self):
        d=self.make('A \u0628\u0628\u062a B')
        self.assertEqual([g['glyph_id'] for g in self.glyphs(d)],[2,1,16,10,9,1,3])
        s=copy.deepcopy(d['items'][0]['content']['frame']['style']);s['fill']=[200,30,60,128]
        styled=self.edit(d,[dict(op='text_range',id='label',start=3,end=4,style=s)])
        self.assertEqual(self.glyphs(d),self.glyphs(styled))
        wrap=self.make('\u0628\u0628\u062a',width=12,wrap=True)
        self.assertEqual([g['glyph_id'] for g in self.glyphs(wrap)],[11,9,13])

    def test_numeric_subruns_keep_decimal_sequence_and_mirrored_brackets(self):
        d=self.make('\u05d0 (12) \u05d1')
        self.assertEqual(self.order(d),[7,6,5,3,4,2,1,0])
        g=self.glyphs(d)
        self.assertEqual([v['glyph_id'] for v in g],[18,1,29,3,4,30,1,17])

    def test_nested_isolates_and_explicit_overrides_do_not_escape_their_scope(self):
        text='A\u2067\u05d0\u2066AB\u2069\u05d1\u2069B'
        d=self.make(text)
        self.assertEqual(self.order(d),[0,7,4,5,2,9])
        self.assertEqual([g['glyph_id'] for g in self.glyphs(d)],[2,18,2,3,17,3])
        override=self.make('A\u202eAB\u202cB')
        self.assertEqual([g['glyph_id'] for g in self.glyphs(override)],[2,3,2,3])
        self.assertEqual(self.order(override),[0,3,2,5])

    def test_isolate_auto_direction_ignores_nested_first_strong_for_outer_paragraph(self):
        text='\u2067\u05d0\u05d1\u2069 A'
        r=self.directions(text)
        self.assertEqual(r['paragraphs'][0]['level'],0)
        # Removed PDI participates in the following blank's logical cluster.
        self.assertEqual(self.order(self.make(text)),[2,1,3,5])
        self.assertEqual(self.order(self.make('A\u2068\u05d0\u05d1\u2069B')),[0,3,2,5])

    def test_combining_marks_stay_with_base_and_have_independent_anchor_geometry(self):
        d=self.make('A \u05d0\u05b0\u05d1 B')
        g=self.glyphs(d)
        self.assertEqual([v['glyph_id'] for v in g],[2,1,18,6,17,1,3])
        self.assertEqual([(v['start'],v['end']) for v in g[3:5]],[(2,4),(2,4)])
        self.assertEqual(g[3]['origin'],[g[4]['origin'][0]+3,2.5])
        self.assertEqual(g[3]['advance'],0)
        self.assertEqual(self.edit(d,[dict(op='text_range',id='label',start=3,end=4,text='')],1)['code'],'INVALID_DOCUMENT')

    def test_script_fallback_and_rtl_run_order_across_style_boundaries(self):
        self.add_font('latin_only',{32,65,66});self.add_font('rtl_only',{32,0x5D0,0x5D1})
        d=self.make('A \u05d0\u05d1 B',font='latin_only',fallback=['rtl_only'])
        g=self.glyphs(d)
        self.assertEqual([v['font_id'] for v in g],['latin_only','latin_only','rtl_only','rtl_only','latin_only','latin_only'])
        s=copy.deepcopy(d['items'][0]['content']['frame']['style']);s['size']=20
        d=self.edit(d,[dict(op='text_range',id='label',start=2,end=3,style=s)])
        g=self.glyphs(d);self.assertEqual([v['start'] for v in g],[0,1,3,2,4,5])
        self.assertEqual(g[2]['advance'],7);self.assertEqual(g[3]['advance'],14)

    def test_variable_axes_ligatures_cjk_and_marks_share_mixed_direction_layout(self):
        self.add_font('variable',variable=True)
        d=self.make('\u05d0 fi \u4e00 A\u0301',font='variable')
        f=copy.deepcopy(d['items'][0]['content']['frame']);f['style']['font_variations']={'variable':{'wght':900,'wdth':200}}
        d=self.edit(d,[dict(op='text',id='label',frame=f)])
        g=self.glyphs(d);self.assertIn(26,[v['glyph_id'] for v in g]);self.assertIn(19,[v['glyph_id'] for v in g])
        self.assertEqual({tuple(v['variations'].items()) for v in g},{(('wdth',200.0),('wght',900.0))})
        self.assertEqual(next(v['advance'] for v in g if v['glyph_id']==26),11)
        self.assertEqual(next(v['advance'] for v in g if v['glyph_id']==19),16)
        f['style']['features']={'liga':0};d=self.edit(d,[dict(op='text',id='label',frame=f)])
        self.assertNotIn(26,[v['glyph_id'] for v in self.glyphs(d)])

    def test_controls_only_have_no_ink_and_source_is_preserved(self):
        text='\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u202c\u2066\u2067\u2068\u2069'
        d=self.make(text);r=self.inspect(d)['layout']
        self.assertEqual(r['glyphs'],[]);self.assertIsNone(r['ink_bounds'])
        self.assertEqual(r['lines'][0]['advance'],0)
        self.assertEqual(d['items'][0]['content']['frame']['text'],text)

    def test_directional_diagnostics_ranges_controls_bounds_and_utf8_indices(self):
        r=self.directions('A\u202e\u05d0\u202cB')
        self.assertEqual(r['unicode_version'],[16,0,0]);self.assertEqual(r['indices'],'unicode_scalars')
        self.assertEqual(r['lines'][0]['levels'],[0,None,1,None,0])
        self.assertEqual(r['lines'][0]['visual_order'],[0,2,4])
        for lines in [[dict(start=0,end=4)],[dict(start=3,end=2)],[dict(start=0,end=1),dict(start=0,end=1)]]:
            self.assertEqual(self.directions('A\nB',lines=lines,status=1)['code'],'INVALID_OPERATION')
        self.assertEqual(self.directions('A'*4097,status=1)['code'],'RESOURCE_LIMIT')
        self.assertEqual(self.directions('',direction='rtl')['lines'][0]['base_level'],1)
        self.assertEqual(self.directions('A\n',lines=[dict(start=2,end=2)])['lines'][0]['base_level'],0)

    def test_strict_edit_validation_and_unsupported_separators_are_atomic(self):
        d=self.make('A');before=json.dumps(d,sort_keys=True)
        for changes,code in [({'bidi':'other'},'INVALID_REQUEST'),({'bidi':'single_run'},'INVALID_DOCUMENT'),
            ({'text':'A\tB'},'UNSUPPORTED'),({'text':'A\u2028B'},'UNSUPPORTED'),({'text':'A\u2029B'},'UNSUPPORTED')]:
            f=copy.deepcopy(d['items'][0]['content']['frame']);f.update(changes)
            e=self.edit(d,[dict(op='text',id='label',frame=f)],1);self.assertEqual(e['code'],code)
        self.assertEqual(json.dumps(d,sort_keys=True),before)

    def test_snapshot_edits_preserve_logical_text_styles_and_undoable_controls(self):
        d=self.make('A \u05d0\u05d1 B');original=copy.deepcopy(d)
        d=self.edit(d,[dict(op='text_range',id='label',start=2,end=4,text='\u0628\u062a')])
        self.assertEqual(d['items'][0]['content']['frame']['text'],'A \u0628\u062a B')
        self.assertEqual([g['glyph_id'] for g in self.glyphs(d)],[2,1,16,9,1,3])
        self.assertEqual(original['items'][0]['content']['frame']['text'],'A \u05d0\u05d1 B')
        out=self.invoke(dict(command='document.export',document=d,format='snapshot'))
        reopened=json.loads(out['data']);self.assertEqual(reopened,d)
        self.assertEqual(self.glyphs(d),self.glyphs(reopened))

    def test_path_start_alignment_uses_base_direction_and_visual_glyph_order(self):
        d=self.make('\u05d0\u05d1 AB',align='start',path=dict(geometry=dict(shape='path',commands=[
            dict(verb='move',to=[0,20]),dict(verb='line',to=[100,20])]),start_offset=0))
        r=self.inspect(d)['layout'];self.assertEqual(self.order(d),[3,4,2,1,0])
        self.assertEqual(r['lines'][0]['x'],70.5)
        self.assertAlmostEqual(r['glyphs'][0]['origin'][0],70.5,places=11)
        self.assertTrue(all(v['path']['drawn'] for v in r['glyphs']))

    def test_independent_rectangle_pixels_svg_and_outline_delivery_match(self):
        d=self.make('A \u05d0\u05d1 B')
        expected_gids=[2,1,18,17,1,3];pen=0;boxes=[]
        for gid in expected_gids:
            box=rectangle(gid)
            if box:boxes.append((pen+box[0]/100,10-box[3]/100,pen+box[2]/100,10-box[1]/100))
            pen+=ADVANCES[gid]/100
        # Integer enlargement makes all original rectangle boundaries exact pixels.
        d=self.edit(d,[dict(op='transform',id='label',matrix=[20,0,0,20,0,0])])
        d['width']=1600;d['height']=400
        w,h,pixels=self.pixels(d);expected=[]
        for y in range(h):
            for x in range(w):expected.extend([25,100,200,255] if any(a*20<=x+.5<c*20 and b*20<=y+.5<e*20 for a,b,c,e in boxes) else [0,0,0,0])
        self.assertEqual(pixels,bytes(expected))
        outlined=self.edit(d,[dict(op='text_outline',id='label')]);self.assertEqual(self.pixels(outlined),self.pixels(d))
        svg=self.invoke(dict(command='document.export',document=d,format='svg',font_root=str(self.store)))
        self.assertNotIn('<text',svg['data']);self.assertIn('<path',svg['data'])

    def test_prepend_direction_boundary_keeps_following_grapheme_during_fallback(self):
        # Arabic-number prepend + a Latin base is one edit grapheme, but two bidi levels.
        self.add_font('base',{65});self.add_font('fallback',{0x5D0})
        d=self.make('\u0600A',font='base',fallback=['fallback'])
        # The prepend is not default-ignorable and lacks an outline mapping.
        self.assertEqual(self.inspect(d,1)['code'],'MISSING_GLYPH')
        self.add_font('prepend',{0x600})
        d=self.make('\u0600A',font='base',fallback=['prepend'])
        self.assertEqual([(v['glyph_id'],v['start'],v['end'],v['font_id']) for v in self.glyphs(d)],[(27,0,1,'prepend'),(2,1,2,'base')])
        info=self.inspect(d)
        self.assertEqual((info['indices'],info['edit_boundaries'],info['glyph_clusters']),('unicode_scalars','graphemes','logical_scalar_intervals'))
        self.assertEqual(self.edit(d,[dict(op='text_range',id='label',start=1,end=2,text='B')],1)['code'],'INVALID_DOCUMENT')
        d=self.make('\u00adA',font='base')
        self.assertEqual([v['glyph_id'] for v in self.glyphs(d)],[2])

    def test_mcp_discovery_direction_analysis_and_durable_text_history(self):
        c=Client();self.addCleanup(c.close);c.initialize()
        self.assertEqual(c.success('text.directions',text='A \u05d0\u05d1',direction='auto'),self.directions('A \u05d0\u05d1'))
        session=dict(session_root=str(self.directory/'sessions'),session_id='bidi');d=self.make('A \u05d0\u05d1')
        d=c.success('session.create',**session,request_id='create',document=d,resources=dict(font_root=str(self.store)))['document']
        f=copy.deepcopy(d['items'][0]['content']['frame']);f['direction']='rtl'
        args=dict(**session,expected_revision=0,request_id='direction',action=dict(type='edit',operations=[dict(op='text',id='label',frame=f)]))
        result=c.success('session.apply',**args)
        self.assertTrue(c.success('session.apply',**args)['replayed'])
        self.assertEqual(result['document']['items'][0]['content']['frame']['direction'],'rtl')
        undo=c.success('session.apply',**session,expected_revision=1,request_id='undo',action=dict(type='undo'))
        self.assertEqual(undo['document']['items'][0]['content']['frame']['direction'],'auto')
        redo=c.success('session.apply',**session,expected_revision=2,request_id='redo',action=dict(type='redo'))
        self.assertEqual(redo['document']['items'][0]['content']['frame']['direction'],'rtl')

    def test_source_fonts_are_unchanged_and_missing_resources_fail_explicitly(self):
        d=self.make('A \u05d0\u05d1');self.glyphs(d)
        for name,data in self.sources.items():self.assertEqual((self.directory/(name+'.ttf')).read_bytes(),data)
        self.assertEqual(self.invoke(dict(command='text.inspect',document=d,id='label'),1)['code'],'FONT_ROOT_REQUIRED')


if __name__=='__main__':unittest.main()
