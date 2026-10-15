"""Character-addressed placement with original fonts and independent geometry."""
import base64
import copy
import json
import unittest

import test_text_cli as base
from synthetic_unicode_font import unicode_font
from test_mcp import Client


class PositionedTextTests(unittest.TestCase):
    setUp = base.TextCliTests.setUp
    invoke = base.TextCliTests.invoke
    edit = base.TextCliTests.edit
    inspect = base.TextCliTests.inspect
    pixels = base.TextCliTests.pixels

    def document(self, text='AAAA', positions=None, origin=(3.5, 12), anchor='start', **options):
        return base.TextCliTests.document(self, text=text, wrap=False, overflow='visible',
            positioning=dict(origin=list(origin), anchor=anchor, positions=positions or []), **options)

    def frame(self, d):
        return d['items'][0]['content']['frame']

    def origins(self, d):
        return [g['origin'] for g in self.inspect(d)['layout']['glyphs']]

    def unicode(self, subset='all'):
        path = self.directory/'unicode.ttf'
        path.write_bytes(unicode_font(subset))
        self.font = self.invoke(dict(command='font.import', source_path=str(path),
            license_path=str(self.license), store_root=str(self.store)))

    def assert_rectangles(self, d, boxes):
        w, h, pixels = self.pixels(d)
        expected = bytes(v for y in range(h) for x in range(w)
            for v in next((color for left, top, right, bottom, color in reversed(boxes)
                if left <= x < right and top <= y < bottom), [0]*4))
        self.assertEqual(pixels, expected)

    def test_absolute_relative_and_partial_axis_resets_match_exact_pixels(self):
        d = self.document(positions=[dict(index=1, dx=2, dy=3), dict(index=2, x=25.5), dict(index=3, y=24, dx=-2)])
        self.assertEqual(self.origins(d), [[3.5,12], [11.5,15], [25.5,15], [29.5,24]])
        color = [25,100,200,255]
        self.assert_rectangles(d, [(4,5,8,12,color), (12,8,16,15,color), (26,8,30,15,color), (30,17,34,24,color)])
        self.assertEqual([(l['start'], l['end']) for l in self.inspect(d)['layout']['lines']], [(0,2),(2,3),(3,4)])

    def test_anchor_chunks_and_continuation_use_unanchored_pen(self):
        for anchor, expected in [('start',[20,29]), ('middle',[12.5,21.5]), ('end',[5,14])]:
            with self.subTest(anchor=anchor):
                d = self.document('AAAA', origin=(20,12), anchor=anchor,
                    positions=[dict(index=1,dx=3),dict(index=2,y=24,anchor='start')])
                self.assertEqual(self.origins(d), [[expected[0],12],[expected[1],12],[35,24],[41,24]])
        # Negative displacement makes the second cell the leftmost one.
        d = self.document('AA', origin=(20,12), anchor='middle', positions=[dict(index=1,dx=-12)])
        self.assertEqual(self.origins(d), [[20,12],[14,12]])
        self.assertEqual(self.inspect(d)['layout']['lines'][0]['advance'], 0)

    def test_mixed_size_fill_and_baseline_shift_preserve_common_baseline(self):
        d = self.document('AAA', positions=[dict(index=1,dx=2,dy=3)])
        style = dict(font_id='geometry',size=20,fill=[200,40,60,255],baseline_shift=2)
        d = self.edit(d,[dict(op='text_range',id='label',start=1,end=2,style=style)])
        self.assertEqual(self.origins(d), [[3.5,12],[11.5,13],[23.5,15]])
        self.assertEqual(self.frame(d)['ranges'][0]['style']['size'],20)
        self.assertEqual(self.frame(d)['positioning']['positions'],[dict(index=1,dx=2,dy=3)])
        self.assertEqual(self.inspect(d)['layout']['glyphs'][1]['ink_bounds'],[12.5,-1,20.5,13])

    def test_ligature_relative_interior_accumulates_and_absolute_breaks_shaping(self):
        self.unicode('latin')
        d = self.document('fiA', origin=(10,12), positions=[dict(index=1,dx=3,dy=2)])
        glyphs = self.inspect(d)['layout']['glyphs']
        self.assertEqual([(g['glyph_id'],g['start'],g['end']) for g in glyphs],[(26,0,2),(2,2,3)])
        self.assertEqual(self.origins(d),[[10,12],[18,14]])
        d = self.document('fiA', origin=(10,12), positions=[dict(index=1,dx=3),dict(index=2,y=24)])
        self.assertEqual(self.origins(d),[[10,12],[18,24]])
        d = self.document('fiA', origin=(10,12), positions=[dict(index=1,x=20)])
        self.assertEqual([g['glyph_id'] for g in self.inspect(d)['layout']['glyphs']],[24,25,2])
        self.assertEqual(self.origins(d),[[10,12],[20,12],[22,12]])

    def test_combining_cluster_keeps_marks_and_defers_interior_displacement(self):
        self.unicode('marks')
        plain = self.document('e\u0301A', origin=(10,12))
        moved = self.document('e\u0301A', origin=(10,12), positions=[dict(index=1,dx=3,dy=2)])
        before, after = self.origins(plain), self.origins(moved)
        self.assertEqual(after[:2],before[:2])
        self.assertEqual(after[2],[before[2][0]+3,before[2][1]+2])
        bad = copy.deepcopy(moved)
        self.frame(bad)['positioning']['positions']=[dict(index=1,x=10)]
        self.assertIn('grapheme',self.invoke(dict(command='document.validate',document=bad),1)['message'])

    def test_range_replacement_keeps_start_entry_and_shifts_later_entries(self):
        d = self.document('AAAA', positions=[dict(index=0,x=3.5,y=12),dict(index=1,dx=2),dict(index=2,x=30),dict(index=3,dy=4)])
        source = copy.deepcopy(d)
        changed = self.edit(d,[dict(op='text_range',id='label',start=1,end=3,text='AAA')])
        self.assertEqual(self.frame(changed)['text'],'AAAAA')
        self.assertEqual(self.frame(changed)['positioning']['positions'],[dict(index=0,x=3.5,y=12),dict(index=1,dx=2),dict(index=4,dy=4)])
        self.assertEqual(self.origins(changed),[[3.5,12],[11.5,12],[17.5,12],[23.5,12],[29.5,16]])
        deleted = self.edit(d,[dict(op='text_range',id='label',start=1,end=3,text='')])
        self.assertEqual(self.origins(deleted),[[3.5,12],[9.5,16]])
        inserted = self.edit(d,[dict(op='text_range',id='label',start=1,end=1,text='A')])
        self.assertEqual([p['index'] for p in self.frame(inserted)['positioning']['positions']],[0,1,3,4])
        self.assertEqual(d,source)

    def test_scalar_indices_include_non_bmp_characters_and_empty_text(self):
        d = self.document('A😀A',positions=[dict(index=2,x=30,y=20)])
        self.assertEqual(self.origins(d),[[3.5,12],[9.5,12],[30,20]])
        changed = self.edit(d,[dict(op='text_range',id='label',start=0,end=1,text='AA')])
        self.assertEqual(self.frame(changed)['positioning']['positions'],[dict(index=3,x=30,y=20)])
        self.assertEqual(self.origins(self.document('')),[])
        emptied = self.edit(d,[dict(op='text_range',id='label',start=0,end=3,text='')])
        self.assertEqual(self.frame(emptied)['positioning']['positions'],[])

    def test_invalid_indices_controls_coordinates_and_cumulative_bounds_fail(self):
        d = self.document()
        for positions in [[dict(index=4,x=1)],[dict(index=1,x=1),dict(index=1,y=2)],
                          [dict(index=2,x=1),dict(index=1,y=2)], [dict(index=1,anchor='middle')],
                          [dict(index=0,x=32769)],[dict(index=0,dy=-32769)]]:
            bad = copy.deepcopy(d); self.frame(bad)['positioning']['positions']=positions
            self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],'INVALID_DOCUMENT')
        for field, value in [('wrap',True),('direction','rtl'),('bidi','unicode'),('align','center'),
                             ('leading',12),('first_baseline',dict(metric='fixed',minimum=0)),('text','A\nA')]:
            bad = copy.deepcopy(d); self.frame(bad)[field]=value
            self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],'UNSUPPORTED')
        for positions in [[dict(index=0,dx=32000),dict(index=1,dx=32000)], [dict(index=0,x=32768)]]:
            bad=copy.deepcopy(d);self.frame(bad)['positioning']['positions']=positions
            self.assertEqual(self.inspect(bad,1)['code'],'INVALID_DOCUMENT')

    def test_overflow_uses_positioned_cells_and_clipping_uses_frame_box(self):
        d = self.document('AA',positions=[dict(index=1,x=70)])
        self.assertTrue(self.inspect(d)['layout']['overflowed'])
        bad=copy.deepcopy(d);self.frame(bad)['overflow']='error'
        self.assertEqual(self.inspect(bad,1)['code'],'TEXT_OVERFLOW')
        clipped=copy.deepcopy(d);self.frame(clipped)['overflow']='clip'
        color=[25,100,200,255]
        self.assert_rectangles(clipped,[(4,5,8,12,color)])
        d = self.document('  ',positions=[dict(index=1,y=59)])
        self.assertTrue(self.inspect(d)['layout']['overflowed'])

    def test_snapshot_outline_svg_pdf_and_affine_components_retain_layout(self):
        d = self.document(positions=[dict(index=1,dx=2,dy=3),dict(index=2,x=25.5,y=24)])
        snapshot=self.invoke(dict(command='document.export',document=d,format='snapshot'))
        restored=self.invoke(dict(command='document.validate',document=json.loads(snapshot['data'])))
        self.assertEqual(d,restored)
        outlined=self.edit(d,[dict(op='text_outline',id='label')])
        self.assertEqual(self.pixels(d),self.pixels(outlined))
        svg=self.invoke(dict(command='document.export',document=d,format='svg',font_root=str(self.store)))
        restored=self.invoke(dict(command='svg.import',id='outlined',source=dict(kind='text',text=svg['data'])))['document']
        self.assertEqual(self.pixels(d),self.pixels(restored))
        for source in (d,outlined):
            pdf=self.invoke(dict(command='document.export',document=source,format='pdf',font_root=str(self.store)))
            self.assertTrue(base64.b64decode(pdf['data']).startswith(b'%PDF-'))
        d['items'][0]['transform']=[1,0,0,1,4,3]
        reference=self.pixels(d)
        d['items'][0]['parent']='source';d['items'].insert(0,dict(id='source',content=dict(type='component_source')))
        d['items'].append(dict(id='copy',content=dict(type='instance',instance=dict(source='source'))))
        self.assertEqual(self.pixels(d),reference)

    def test_layered_editable_delivery_refuses_to_discard_positioning(self):
        d=self.document(kind='raster')
        error=self.invoke(dict(command='document.export',document=d,format='layered',font_root=str(self.store),
            layered_options=dict(text=dict(reconstruction='native_layout',shape_owner='OriginalFixture'))),1)
        self.assertEqual(error['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        self.assertIn('character positioning',error['message'])

    def test_mcp_dry_run_retry_and_history_preserve_positions_and_rollback(self):
        c=Client();self.addCleanup(c.close);c.initialize()
        caps=c.success('capabilities')['text_positioning']
        self.assertEqual(caps['absolute'],['x','y']);self.assertEqual(caps['max_positions'],4096)
        d=self.document(positions=[dict(index=1,dx=3),dict(index=3,x=40)])
        session=dict(session_root=str(self.directory/'sessions'),session_id='positioned')
        d=c.success('session.create',**session,request_id='create',document=d,resources=dict(font_root=str(self.store)))['document']
        args=dict(**session,expected_revision=0,request_id='replace',action=dict(type='edit',operations=[dict(op='text_range',id='label',start=1,end=2,text='AAA')]))
        # Session proposals and committed retries use exactly the same edit.
        dry=c.success('session.dry_run',**args,options=dict(include_document=True))
        self.assertFalse(dry['source_changed']);self.assertFalse(dry['committed'])
        self.assertEqual(c.success('session.read',**session)['document'],d)
        committed=c.success('session.apply_proposal',session_root=session['session_root'],proposal=dry['proposal'],action=args['action'])
        changed=committed['document']
        self.assertEqual(changed,dry['proposed_document'])
        self.assertEqual(committed['receipt'],dry['predicted_receipt'])
        self.assertTrue(c.success('session.apply',**args)['replayed'])
        self.assertEqual([p['index'] for p in self.frame(changed)['positioning']['positions']],[1,5])
        undone=c.success('session.apply',**session,expected_revision=1,request_id='undo',action=dict(type='undo'))['document']
        self.assertEqual(undone['items'],d['items'])
        redone=c.success('session.apply',**session,expected_revision=2,request_id='redo',action=dict(type='redo'))['document']
        self.assertEqual(redone['items'],changed['items'])
        before=copy.deepcopy(redone)
        failed=self.edit(redone,[dict(op='text_range',id='label',start=0,end=1,text='A'),dict(op='remove',id='missing')],1)
        self.assertEqual(failed['code'],'NOT_FOUND');self.assertEqual(redone,before)
        failed=c.tool('session.apply',**session,request_id='fail',expected_revision=3,
            action=dict(type='edit',operations=[dict(op='text_range',id='label',start=1,end=2,text='AA'),dict(op='remove',id='missing')]))
        self.assertEqual(failed['structuredContent']['error']['code'],'NOT_FOUND')
        self.assertEqual(c.success('session.read',**session)['document'],redone)
        self.assertEqual(c.tool('session.receipt',**session,request_id='fail')['structuredContent']['error']['code'],'REQUEST_NOT_FOUND')


if __name__ == '__main__':
    unittest.main()
