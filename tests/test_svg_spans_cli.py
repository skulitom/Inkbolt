"""Original SVG span fixtures with independent position, pixel and source oracles."""
import base64
import copy
import json
import unittest

import test_svg_text_cli as text_base
import test_editing_cli as editing
from synthetic_unicode_font import unicode_font
from test_mcp import Client


class SvgSpanTests(unittest.TestCase):
    setUp = text_base.SvgTextTests.setUp
    invoke = text_base.SvgTextTests.invoke
    imported = text_base.SvgTextTests.imported
    label = text_base.SvgTextTests.label
    item = text_base.SvgTextTests.item
    pixels = text_base.SvgTextTests.pixels
    inspect = text_base.SvgTextTests.inspect
    edit = text_base.SvgTextTests.edit
    roundtrip = text_base.SvgTextTests.roundtrip

    def frame(self,r):
        return self.item(r)['content']['frame']

    def origins(self,r):
        item=self.item(r)
        return [[g['origin'][0]+item['transform'][4],g['origin'][1]+item['transform'][5]] for g in self.inspect(r)['glyphs']]

    def rectangles(self,r,boxes):
        for scale in (1,2):
            w,h,p=self.pixels(r['document'],scale)
            expected=bytes(v for y in range(h) for x in range(w) for v in next(
                (color for left,top,right,bottom,color in reversed(boxes) if left*scale<=x<right*scale and top*scale<=y<bottom*scale),[0]*4))
            self.assertEqual(p,expected)

    def test_nested_styles_tail_text_and_ranges_have_exact_pixels(self):
        r=self.imported(self.label('fill="red"',text='A<tspan id="blue" fill="blue">A<tspan id="green" fill="#00ff00">A</tspan>A</tspan>A'),attrs='width="40" height="24"')
        self.assertEqual(self.frame(r)['text'],'AAAAA')
        self.assertEqual(self.origins(r),[[3.5,12],[9.5,12],[15.5,12],[21.5,12],[27.5,12]])
        self.assertEqual([m['text_range'] for m in r['mapping'] if m['element']=='tspan'],[[1,4],[2,3]])
        self.assertEqual(len(self.frame(r)['ranges']),5)
        self.rectangles(r,[(4,5,8,12,[255,0,0,255]),(10,5,14,12,[0,0,255,255]),(16,5,20,12,[0,255,0,255]),(22,5,26,12,[0,0,255,255]),(28,5,32,12,[255,0,0,255])])
        self.roundtrip(r['document'])

    def test_parent_lists_child_overrides_and_cumulative_relative_axes(self):
        r=self.imported('<text id="label" font-family="Geometry" font-size="10" x="3.5,15.5 27.5 39.5" y="12" dx="0 1 2 3">A<tspan id="s" x="8.5" dx="4" dy="2">AA</tspan>A</text>',attrs='width="64" height="32"')
        self.assertEqual(self.origins(r),[[3.5,12],[12.5,14],[29.5,14],[42.5,14]])
        color=[0,0,0,255]
        self.rectangles(r,[(4,5,8,12,color),(13,7,17,14,color),(30,7,34,14,color),(43,7,47,14,color)])
        # Lists on a text element use the same path even without spans.
        r=self.imported('<text id="label" font-family="Geometry" font-size="10" x="3.5 15.5" y="12 20">AA</text>')
        self.assertEqual(self.origins(r),[[3.5,12],[15.5,20]])

    def test_absolute_chunks_anchor_independently_and_relative_shift_keeps_tail(self):
        r=self.imported('<text id="label" font-family="Geometry" font-size="10" x="20" y="12" text-anchor="middle">A<tspan dx="3">A</tspan><tspan x="40" y="24" text-anchor="end">AA</tspan>A</text>',attrs='width="60" height="32"')
        self.assertEqual(self.origins(r),[[12.5,12],[21.5,12],[22,24],[28,24],[34,24]])
        self.assertEqual(len(self.inspect(r)['lines']),2)

    def test_embedded_cascade_mixed_sizes_and_explicit_child_font_binding(self):
        r=self.imported('<style>.small{font-size:50%;fill:blue}tspan.small{fill:currentColor}</style><text id="label" font-family="Geometry" font-size="20" x="3.5" y="20" color="red">A<tspan class="small" color="green">AA</tspan>A</text>',attrs='width="48" height="32"')
        self.assertEqual(self.origins(r),[[3.5,20],[15.5,20],[21.5,20],[27.5,20]])
        self.assertEqual([s['style']['size'] for s in self.frame(r)['ranges']],[20,10,20])
        self.assertEqual(self.frame(r)['ranges'][1]['style']['fill'],[0,128,0,255])
        r=self.imported('<text id="label" x="3.5" y="12"><tspan font-family="Geometry" font-size="10">AA</tspan></text>')
        self.assertEqual(self.origins(r),[[3.5,12],[9.5,12]])
        self.assertEqual(r['document']['fonts'],{'geometric':self.font})

    def test_whitespace_collapses_across_nodes_and_maps_retained_scalars(self):
        r=self.imported(self.label(text='  A <tspan id="s">  A  </tspan> A  '))
        self.assertEqual(self.frame(r)['text'],'A A A')
        span=next(m for m in r['mapping'] if m['source_id']=='s')
        self.assertEqual(span['text_range'],[2,4])
        r=self.imported(self.label(text='A\n<tspan>A</tspan>\nA'))
        self.assertEqual(self.frame(r)['text'],'AAA')
        r=self.imported(self.label(text='A\n<tspan>A</tspan>\nA'),attrs='width="48" height="24" version="2.0"')
        self.assertEqual(self.frame(r)['text'],'A A A')
        r=self.imported(self.label('xml:space="preserve"',text=' A<tspan>  A </tspan>A '),attrs='width="64" height="24"')
        self.assertEqual(self.frame(r)['text'],' A  A A ')

    def test_display_none_removes_addressing_visibility_keeps_advance(self):
        r=self.imported('<text id="label" font-family="Geometry" font-size="10" x="3.5 9.5 15.5" y="12" visibility="hidden">A<tspan id="removed" display="none" x="100">AA</tspan><tspan id="visible" visibility="visible">A</tspan>A</text>')
        self.assertEqual(self.frame(r)['text'],'AAA')
        self.assertEqual(self.origins(r),[[3.5,12],[9.5,12],[15.5,12]])
        self.assertEqual(next(m['text_range'] for m in r['mapping'] if m['source_id']=='removed'),[1,1])
        self.rectangles(r,[(10,5,14,12,[0,0,0,255])])

    def test_units_percentage_viewports_and_nested_style_em(self):
        r=self.imported('<svg x="4.5" y="2" width="48" height="24" viewBox="0 0 24 12"><text id="label" font-family="Geometry" font-size="5" x="25%" y="50%"><tspan dx="1em">A</tspan>A</text></svg>',attrs='width="64" height="32"')
        self.assertEqual(self.origins(r),[[11,6],[14,6]])
        self.rectangles(r,[(27,7,31,14,[0,0,0,255]),(33,7,37,14,[0,0,0,255])])

    def test_gradients_share_entire_text_box_and_root_clip_survives_rebase(self):
        gradient='<linearGradient id="g"><stop offset="0" stop-color="red"/><stop offset="1" stop-color="blue"/></linearGradient>'
        r=self.imported(gradient+self.label('fill="url(#g)"',text='A<tspan>A</tspan>'))
        reference=self.imported(gradient+self.label('fill="url(#g)"'))
        self.assertEqual(self.pixels(r['document']),self.pixels(reference['document']))
        clip='<clipPath id="c" clipPathUnits="objectBoundingBox"><rect width=".5" height="1"/></clipPath>'
        r=self.imported(clip+self.label('clip-path="url(#c)"',text='A<tspan>A</tspan>'))
        self.rectangles(r,[(4,5,8,12,[0,0,0,255])])

    def test_reused_text_clones_style_context_and_span_mappings(self):
        r=self.imported('<defs><text id="label" x="3.5" y="12"><tspan id="s" fill="currentColor">A</tspan>A</text></defs><use href="#label" font-family="Geometry" font-size="10" color="red"/><use href="#label" x="16" font-family="Geometry" font-size="10" color="blue"/>',attrs='width="48" height="24"')
        spans=[m for m in r['mapping'] if m['source_id']=='s']
        self.assertEqual(len(spans),2);self.assertTrue(all(m['text_range']==[0,1] for m in spans))
        self.rectangles(r,[(4,5,8,12,[255,0,0,255]),(10,5,14,12,[0,0,0,255]),(20,5,24,12,[0,0,255,255]),(26,5,30,12,[0,0,0,255])])

    def test_span_gradient_reference_is_scoped_and_mask_artwork_keeps_ranges(self):
        template='<text id="label" x="3.5" y="12"><tspan fill="url(#g)">A</tspan>A</text>'
        gradient='<linearGradient id="g"><stop offset="0" stop-color="currentColor"/><stop offset="1" stop-color="currentColor"/></linearGradient>'
        r=self.imported('<defs><g id="source">'+gradient+template+'</g></defs><use href="#source" font-family="Geometry" font-size="10" color="red"/><use href="#source" x="16" font-family="Geometry" font-size="10" color="blue"/>',attrs='width="48" height="24"')
        self.rectangles(r,[(4,5,8,12,[255,0,0,255]),(10,5,14,12,[0,0,0,255]),(20,5,24,12,[0,0,255,255]),(26,5,30,12,[0,0,0,255])])
        mask='<mask id="m" maskUnits="userSpaceOnUse" x="0" y="0" width="32" height="24">'+self.label('fill="white"',text='A<tspan>A</tspan>')+'</mask>'
        r=self.imported(mask+'<rect width="32" height="24" fill="red" mask="url(#m)"/>')
        self.rectangles(r,[(4,5,8,12,[255,0,0,255]),(10,5,14,12,[255,0,0,255])])

    def test_dom_boundaries_prevent_ligatures_and_relative_interior_preserves_them(self):
        self.source.write_bytes(unicode_font('latin'))
        self.font=self.invoke(dict(command='font.import',source_path=str(self.source),license_path=str(self.license),store_root=str(self.store)))
        self.bindings=[dict(family='Geometry',font_id='geometric',font=self.font)]
        r=self.imported(self.label(text='f<tspan>i</tspan>A'))
        self.assertEqual([g['glyph_id'] for g in self.inspect(r)['glyphs']],[24,25,2])
        r=self.imported(self.label(text='<tspan dx="0 3">fiA</tspan>'))
        self.assertEqual([g['glyph_id'] for g in self.inspect(r)['glyphs']],[26,2])
        self.assertEqual(self.origins(r),[[3.5,12],[11.5,12]])

    def test_errors_are_located_in_unused_hidden_and_visible_spans(self):
        for attr in ['rotate="10"','textLength="5"','transform="translate(1)"','opacity=".5"','opacity="bad"','clip-path="url(#c)"','mask="url(#m)"','font-size="1e308em"','x="1,,2"']:
            for wrapper in ('{}','<g display="none">{}</g>','<defs>{}</defs>'):
                body=self.label(text=f'<tspan id="bad" {attr}>A</tspan>')
                error=self.imported(wrapper.format(body),expected=1)
                self.assertIn(error['code'],['SVG_UNSUPPORTED','SVG_INVALID'])
                self.assertEqual(error['details']['element'],'tspan')
        for text in ['<tspan display="none" fill="url(#missing)">A</tspan>','<tspan>A</tspan><tspan dx="1e308%">A</tspan>']:
            self.assertEqual(self.imported(self.label(text=text),attrs='width="32768" height="24"',expected=1)['code'],'SVG_INVALID')

    def test_grapheme_boundaries_missing_fonts_and_native_range_budget(self):
        self.source.write_bytes(unicode_font('marks'))
        self.font=self.invoke(dict(command='font.import',source_path=str(self.source),license_path=str(self.license),store_root=str(self.store)))
        self.bindings=[dict(family='Geometry',font_id='geometric',font=self.font)]
        r=self.imported(self.label(text='e<tspan id="mark">\u0301A</tspan>'))
        self.assertEqual(self.frame(r)['text'],'e\u0301A')
        self.assertEqual(len(self.frame(r)['ranges']),1)
        self.assertEqual(next(m['text_range'] for m in r['mapping'] if m['source_id']=='mark'),[1,3])
        for attrs in ['fill="red"','x="8"']:
            error=self.imported(self.label(text=f'e<tspan {attrs}>\u0301A</tspan>'),expected=1)
            self.assertEqual(error['code'],'SVG_UNSUPPORTED');self.assertEqual(error['details']['element'],'tspan')
        error=self.imported(self.label(text='<tspan font-family="missing">A</tspan>'),expected=1)
        self.assertEqual(error['code'],'SVG_FONT_NOT_BOUND');self.assertEqual(error['details']['element'],'tspan')
        r=self.imported(self.label(text='A<tspan display="none" font-family="missing">A</tspan>'))
        self.assertEqual(self.frame(r)['text'],'A')
        limit=self.invoke(dict(command='capabilities'))['limits']['text_ranges_per_frame']
        r=self.imported(self.label(text='<tspan>A</tspan>'*limit))
        self.assertEqual(len(self.frame(r)['ranges']),limit)
        error=self.imported(self.label(text='<tspan>A</tspan>'*(limit+1)),expected=1)
        self.assertEqual(error['code'],'RESOURCE_LIMIT')

    def test_add_svg_ranges_proposal_retry_undo_and_source_preservation(self):
        c=Client();self.addCleanup(c.close);c.initialize()
        d=self.invoke(dict(command='document.create',id='inserted',kind='vector',width=40,height=24))
        d=self.edit(d,[dict(op='font_put',id='geometric',font=self.font)])
        source=self.label(text='A<tspan id="s" dx="2" fill="blue">AA</tspan>A')
        inserted=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],font_root=str(self.store),operations=[dict(op='add_svg',svg=source,font_bindings=[dict(family='Geometry',font_id='geometric')])]))
        mapping=next(m for m in inserted['changes'][0]['details']['mapping'] if m['source_id']=='s')
        mapped=next(i for i in inserted['document']['items'] if i['id']==mapping['item_id'])
        self.assertEqual(mapped['content']['frame']['text'],'AAAA')
        self.assertEqual(mapping['text_range'],[1,3])
        self.assertEqual(mapping['byte_offset'],source.encode().index(b'<tspan'))
        session=dict(session_root=str(self.root/'sessions'),session_id='spans')
        original=c.success('session.create',**session,request_id='create',document=d,resources=dict(font_root=str(self.store)))['document']
        action=dict(type='edit',operations=[dict(op='add_svg',svg=source,font_bindings=[dict(family='Geometry',font_id='geometric')])])
        dry=c.success('session.dry_run',**session,request_id='insert',expected_revision=0,action=action,options=dict(include_document=True))
        self.assertEqual(c.success('session.read',**session)['document'],original)
        committed=c.success('session.apply_proposal',session_root=session['session_root'],proposal=dry['proposal'],action=action)
        self.assertEqual(committed['document'],dry['proposed_document'])
        self.assertTrue(c.success('session.apply',**session,request_id='insert',expected_revision=0,action=action)['replayed'])
        item=next(i for i in committed['document']['items'] if i['content']['type']=='text')
        changed=c.success('session.apply',**session,request_id='edit',expected_revision=1,action=dict(type='edit',operations=[dict(op='text_range',id=item['id'],start=1,end=2,text='AA')]))['document']
        self.assertEqual(next(i for i in changed['items'] if i['id']==item['id'])['content']['frame']['text'],'AAAAA')
        undone=c.success('session.apply',**session,request_id='undo',expected_revision=2,action=dict(type='undo'))['document']
        self.assertEqual(undone['items'],committed['document']['items'])
        self.assertEqual(item['content']['frame']['text'],'AAAA')


if __name__=='__main__':unittest.main()
