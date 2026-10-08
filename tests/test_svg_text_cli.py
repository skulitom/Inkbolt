"""Original geometric fonts and independent baseline, coverage and resource oracles."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from fractions import Fraction
from synthetic_font import geometric_font
import test_editing_cli as editing
from test_svg_import_cli import svg
from test_mcp import Client


class SvgTextTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.store=self.root/'fonts';self.source=self.root/'original.ttf';self.source.write_bytes(geometric_font())
        self.license=self.root/'LICENSE';self.license.write_bytes((Path(__file__).resolve().parents[1]/'LICENSE').read_bytes())
        self.font=self.invoke(dict(command='font.import',source_path=str(self.source),license_path=str(self.license),store_root=str(self.store)))
        self.bindings=[dict(family='Geometry',font_id='geometric',font=self.font)]
    def imported(self,body,attrs='width="32" height="24"',expected=0,**kw):
        args=dict(command='svg.import',id='labels',source=dict(kind='text',text=svg(body,attrs)),font_root=str(self.store),font_bindings=self.bindings);args.update(kw)
        return self.invoke(args,expected)
    def label(self,attrs='',text='AA',id='label'):
        return f'<text id="{id}" font-family="Geometry" font-size="10" x="3.5" y="12" {attrs}>{text}</text>'
    def item(self,r,id='label'):
        mapped=next(m['item_id'] for m in r['mapping'] if m['source_id']==id)
        return next(i for i in r['document']['items'] if i['id']==mapped)
    def pixels(self,d,scale=1):
        r=self.invoke(dict(command='document.export',document=d,format='png',scale=scale,font_root=str(self.store)))
        return editing.png_pixels(base64.b64decode(r['data']))[:3]
    def inspect(self,r,id='label'):
        return self.invoke(dict(command='text.inspect',document=r['document'],id=self.item(r,id)['id'],font_root=str(self.store)))['layout']
    def edit(self,d,ops):
        return self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=ops,font_root=str(self.store)))['document']
    def roundtrip(self,d):
        output=self.invoke(dict(command='document.export',document=d,format='svg',font_root=str(self.store)))
        self.assertTrue(any('Text exports as glyph outlines' in s for s in output['losses']))
        tree=ET.fromstring(output['data']);self.assertFalse(tree.findall('.//{*}text'))
        imported=self.invoke(dict(command='svg.import',id='outlined',source=dict(kind='text',text=output['data'])))['document']
        for scale in (1,2,3):self.assertEqual(self.pixels(d,scale),self.pixels(imported,scale))
        return tree

    def test_baseline_editable_characters_exact_rectangular_pixels_and_outlined_roundtrip(self):
        r=self.imported(self.label('fill="#205080"'));i=self.item(r);f=i['content']['frame']
        self.assertEqual(i['content']['type'],'text');self.assertEqual(f['text'],'AA');self.assertEqual(f['width'],12);self.assertEqual(f['height'],10)
        self.assertEqual(i['transform'],[1,0,0,1,3.5,4]);self.assertEqual(r['document']['fonts'],{'geometric':self.font})
        self.assertEqual(self.inspect(r)['ink_bounds'],[.5,1,10.5,8])
        w,h,p=self.pixels(r['document']);expected=bytes(v for y in range(h) for x in range(w) for v in ([32,80,128,255] if 5<=y<12 and (4<=x<8 or 10<=x<14) else [0]*4))
        self.assertEqual(p,expected);self.assertEqual(len(self.roundtrip(r['document']).findall('.//{*}path')),2)
        self.assertTrue(any('editable frame' in s for s in r['losses']))

    def test_anchor_alignment_uses_advance_not_ink_and_survives_text_edits(self):
        for anchor,shift,align in [('start',0,'left'),('middle',6,'center'),('end',12,'right')]:
            r=self.imported(f'<text id="label" x="20" y="12" font-family="Geometry" font-size="10" text-anchor="{anchor}">AA</text>');i=self.item(r)
            self.assertEqual(i['transform'][4:], [20-shift,4]);self.assertEqual(i['content']['frame']['align'],align)
            changed=self.edit(r['document'],[dict(op='text_range',id=i['id'],start=0,end=2,text='A')])
            layout=self.invoke(dict(command='text.inspect',document=changed,id=i['id'],font_root=str(self.store)))['layout']
            self.assertEqual(layout['lines'][0]['x'], {'start':0,'middle':3,'end':6}[anchor])
            self.assertEqual(i['content']['frame']['text'],'AA')

    def test_percent_em_absolute_units_viewbox_and_transform_order(self):
        r=self.imported('<g transform="translate(2 3)" font-family="Geometry" font-size="8"><text id="label" font-size="125%" x="25%" y="75%" dx="1em" dy="-1.5pt" transform="scale(1 .5)">AA</text></g>','width="64" height="48" viewBox="0 0 32 24"')
        i=self.item(r);self.assertEqual(i['transform'],[1,0,0,.5,18,4])
        self.assertEqual(i['content']['frame']['style']['size'],10)
        w,h,p=self.pixels(r['document'])
        # Local glyphs [18.5..22.5] and [24.5..28.5], y[9..16], then y*.5,
        # parent(+2,+3), then viewBox scale2 => integer rectangles.
        expected=bytes(v for y in range(h) for x in range(w) for v in ([0,0,0,255] if 15<=y<22 and (41<=x<49 or 53<=x<61) else [0]*4))
        self.assertEqual(p,expected);self.roundtrip(r['document'])

    def test_whitespace_legacy_and_modern_modes_entities_comments_and_unicode(self):
        for attrs,text,want,rootattrs in [
            ('',' \tA\nA  A ','AA A',''),('xml:space="preserve"',' A\nA\t A ',' A A  A ',''),
            ('',' A\nA\t A ','A A A','version="2.0"'),('style="white-space:normal"',' A\nA  ','A A',''),
            ('style="white-space:pre"','  A A  ','  A A  ',''),('', 'A<!-- spacer -->&#233;&#x1f600;','Aé😀','')]:
            r=self.imported(self.label(attrs,text),f'width="64" height="24" {rootattrs}')
            self.assertEqual(self.item(r)['content']['frame']['text'],want)
        r=self.imported('<g xml:space="preserve" font-family="Geometry" font-size="10"><text id="label" y="12"> A </text></g>')
        self.assertEqual(self.item(r)['content']['frame']['text'],' A ')

    def test_font_binding_order_aliases_weight_style_and_missing_glyph_no_substitution(self):
        bindings=[dict(family='First Family',font_id='chosen',font=self.font,weight=700,style='italic'),dict(family='serif',font_id='other',font=self.font)]
        r=self.imported('<g style="font-family:Missing, &quot;first family&quot;, serif;font-weight:bold;font-style:italic;color:#246"><text id="label" font-size="10" y="12" fill="currentColor">AB</text></g>',font_bindings=bindings)
        self.assertEqual(r['document']['fonts'],{'chosen':self.font});self.assertEqual(self.item(r)['content']['frame']['style']['fill'],[34,68,102,255])
        self.assertEqual([g['origin'] for g in self.inspect(r)['glyphs']],[[0,8],[5,8]])
        for body in [self.label('font-weight="bold"'),self.label('font-style="italic"')]:
            self.assertEqual(self.imported(body,expected=1)['code'],'SVG_FONT_NOT_BOUND')
        self.assertEqual(self.imported(self.label(text='C'),expected=1)['code'],'MISSING_GLYPH')
        self.assertEqual(self.imported(self.label(),expected=1,font_bindings=[])['code'],'SVG_FONT_NOT_BOUND')

    def test_gradient_text_bbox_uses_font_cells_and_user_coordinates_rebase_once(self):
        stops='<stop offset="0" stop-color="red"/><stop offset="1" stop-color="blue"/>'
        for units,x2,denom,start in [('objectBoundingBox','1',12,3.5),('userSpaceOnUse','32',32,0)]:
            body=f'<defs><linearGradient id="g" gradientUnits="{units}" x2="{x2}">{stops}</linearGradient></defs>'+self.label('fill="url(#g)"')
            r=self.imported(body);paint=self.item(r)['content']['frame']['style']['fill']
            self.assertEqual(paint['transform'],[12,0,0,10,0,0] if units=='objectBoundingBox' else [1,0,0,1,-3.5,-4])
            w,h,p=self.pixels(r['document']);expected=[]
            for y in range(h):
                for x in range(w):
                    t=(Fraction(2*x+1,2)-Fraction(start))/denom
                    expected.extend([int(255*(1-t)+Fraction(1,2)),0,int(255*t+Fraction(1,2)),255] if 5<=y<12 and (4<=x<8 or 10<=x<14) else [0]*4)
            self.assertLessEqual(max(abs(a-b) for a,b in zip(p,expected)),1);self.roundtrip(r['document'])

    def test_clips_and_group_object_bounds_include_text_cells_and_spaces(self):
        for units,shape in [('userSpaceOnUse','x="3.5" y="4" width="6" height="10"'),('objectBoundingBox','width=".5" height="1"')]:
            r=self.imported(f'<defs><clipPath id="c" clipPathUnits="{units}"><rect {shape}/></clipPath></defs>'+self.label('clip-path="url(#c)" fill="red"'))
            w,h,p=self.pixels(r['document']);expected=bytes(v for y in range(h) for x in range(w) for v in ([255,0,0,255] if 5<=y<12 and 4<=x<8 else [0]*4))
            self.assertEqual(p,expected);self.roundtrip(r['document'])
        r=self.imported('<defs><clipPath id="c" clipPathUnits="objectBoundingBox"><rect width="1" height="1"/></clipPath></defs><g id="g" clip-path="url(#c)"><text x="4" y="12" font-family="Geometry" font-size="10" xml:space="preserve" visibility="hidden"> A </text><rect x="5" y="7" width="2" height="2"/><text font-family="Geometry" x="100" display="none">A</text></g>')
        self.assertEqual(self.item(r,'g')['clip']['transform'],[12,0,0,10,4,4])

    def test_overlapping_translucent_glyphs_composite_separately_and_keep_object_opacity(self):
        source=self.root/'overlap.ttf';source.write_bytes(geometric_font(rectangle_advance=200))
        desc=self.invoke(dict(command='font.import',source_path=str(source),license_path=str(self.license),store_root=str(self.store)))
        r=self.imported(self.label('fill="red" fill-opacity=".5" opacity=".5"'),font_bindings=[dict(family='Geometry',font_id='overlap',font=desc)])
        w,h,p=self.pixels(r['document']);expected=[]
        for y in range(h):
            for x in range(w):
                n=int(4<=x<8)+int(6<=x<10) if 5<=y<12 else 0
                alpha=round((1-(1-Fraction(128,255))**n)*Fraction(1,2)*255)
                expected.extend([255,0,0,alpha] if alpha else [0]*4)
        self.assertEqual(p,bytes(expected));self.roundtrip(r['document'])

    def test_font_and_source_bytes_preserved_missing_corrupt_store_fails_explicitly(self):
        raw=svg(self.label()).encode();path=self.root/'input.svg';path.write_bytes(raw)
        initial={p:p.read_bytes() for p in [path,self.source,self.license,*self.store.iterdir()]}
        r=self.imported('',source=dict(kind='file',source_path=str(path)))
        self.assertEqual(r['source']['sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(initial,{p:p.read_bytes() for p in initial})
        self.assertEqual(self.imported(self.label(),expected=1,font_root=None)['code'],'FONT_ROOT_REQUIRED')
        fontfile=self.store/(self.font['sha256']+'.font');fontfile.write_bytes(b'bad')
        self.assertEqual(self.imported(self.label(),expected=1)['code'],'FONT_CORRUPT')
        self.assertEqual(path.read_bytes(),raw)

    def test_mcp_persistent_text_edits_reopen_retry_snapshot_and_undo(self):
        client=Client();self.addCleanup(client.close);client.initialize()
        r=client.success('svg.import',id='labels',source=dict(kind='text',text=svg(self.label())),font_bindings=self.bindings,font_root=str(self.store));i=self.item(r);d=r['document'];before=self.pixels(d)
        common=dict(session_root=str(self.root/'sessions'),session_id='labels')
        client.success('session.create',**common,request_id='create',document=d,resources=dict(font_root=str(self.store)))
        args=dict(**common,request_id='edit',expected_revision=0,action=dict(type='edit',operations=[dict(op='text_range',id=i['id'],start=0,end=1,text='B')]))
        edited=client.success('session.apply',**args);self.assertTrue(client.success('session.apply',**args)['replayed'])
        reopened=self.invoke(dict(command='session.read',**common));self.assertEqual(reopened['document'],edited['document'])
        self.assertNotEqual(self.pixels(reopened['document']),before)
        undo=client.success('session.apply',**common,request_id='undo',expected_revision=1,action=dict(type='undo'))
        self.assertEqual(self.pixels(undo['document']),before);self.assertEqual(i['content']['frame']['text'],'AA')
        restored=self.invoke(dict(command='document.validate',document=json.loads(self.invoke(dict(command='document.export',document=undo['document'],format='snapshot'))['data'])))
        self.assertEqual(self.pixels(restored),before)

    def test_unsupported_text_semantics_fail_even_hidden_without_partial_document(self):
        for attrs in ['stroke="red"','fill-rule="evenodd"','letter-spacing="1"','direction="rtl"','writing-mode="vertical-rl"','dominant-baseline="middle"','rotate="10"','textLength="12"','font-variant="small-caps"','font-size-adjust=".5"','font-stretch="condensed"']:
            r=self.imported('<rect width="1" height="1"/>'+self.label(attrs),expected=1);self.assertEqual(r['code'],'SVG_UNSUPPORTED',attrs)
        for text in ['<tspan>A</tspan>','<textPath href="#path">A</textPath>']:
            self.assertEqual(self.imported('<g display="none">'+self.label(text=text)+'</g>',expected=1)['code'],'SVG_UNSUPPORTED')
        for text in ['A\nA','A\tA']:
            self.assertEqual(self.imported(self.label('style="white-space:pre"',text),expected=1)['code'],'SVG_UNSUPPORTED')
        for attrs in ['x="1 2"','font-size="0"','font-size="1e300em"']:
            body='<text font-family="Geometry" '+attrs+'>A</text>'
            self.assertIn(self.imported(body,expected=1)['code'],['SVG_INVALID','SVG_UNSUPPORTED'])

    def test_binding_limits_conflicts_and_unused_bindings_do_not_load_or_persist(self):
        r=self.imported('<rect width="1" height="1"/>',font_root=None);self.assertEqual(r['document'].get('fonts',{}),{})
        for bindings,code in [(self.bindings*2,'SVG_INVALID'),([dict(family='A',font_id='bad/id',font=self.font)],'SVG_INVALID'),(self.bindings*9,'RESOURCE_LIMIT'),([dict(family='A',font_id='ok',font=self.font,weight=450)],'SVG_INVALID')]:
            self.assertEqual(self.imported(self.label(),expected=1,font_bindings=bindings)['code'],code)
        self.assertEqual(self.imported(self.label(text='A'*4097),expected=1)['code'],'RESOURCE_LIMIT')
        for families in ["'bad",'A,,B','A\\B','A()']:
            body='<text style="font-family:'+families.replace('"','&quot;')+'">A</text>'
            self.assertIn(self.imported(body,expected=1)['code'],['SVG_INVALID','SVG_UNSUPPORTED'])

    def test_empty_transparent_and_hidden_text_remain_editable_and_capabilities_declare_bounds(self):
        for attrs,text in [('', ''),('fill="none"','AA'),('visibility="hidden"','AA')]:
            r=self.imported(self.label(attrs,text));self.assertEqual(self.item(r)['content']['frame']['text'],text)
            self.assertFalse(any(self.pixels(r['document'])[2]))
        gradient='<defs><linearGradient id="g"><stop offset="0"/><stop offset="1" stop-color="red"/></linearGradient></defs>'
        self.assertEqual(self.imported(gradient+self.label('fill="url(#g)"',''),expected=1)['code'],'SVG_UNSUPPORTED')
        r=self.imported(self.label(text='<title>Editable label</title>AA'))
        self.assertEqual(self.item(r)['name'],'Editable label');self.assertEqual(self.item(r)['content']['frame']['text'],'AA')
        caps=self.invoke(dict(command='capabilities'));self.assertIn('text',caps['svg_import']['elements'])
        self.assertEqual(caps['svg_import']['text']['object_box'],'full_font_cells')
        self.assertFalse(caps['svg_import']['text']['span_children'])
        self.assertEqual(caps['svg_import']['text']['font_bindings'],8)


if __name__=='__main__':unittest.main()
