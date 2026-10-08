"""Independent geometric font, byte-store, editable layout and export checks."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import test_editing_cli as editing
from synthetic_font import geometric_font


class TextCliTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name);self.source=self.directory/'original.ttf';self.source.write_bytes(geometric_font())
        self.license=self.directory/'LICENSE.txt';self.license.write_bytes((Path(__file__).resolve().parents[1]/'LICENSE').read_bytes())
        self.store=self.directory/'fonts'
        self.font=self.invoke(dict(command='font.import',source_path=str(self.source),license_path=str(self.license),store_root=str(self.store)))

    def document(self,kind='vector',text='AA',**options):
        d=self.invoke(dict(command='document.create',id='text-fixture',kind=kind,width=80,height=60))
        frame=dict(text=text,width=60,height=50,style=dict(font_id='geometry',size=10,fill=[25,100,200,255]))
        frame.update(options)
        return self.edit(d,[dict(op='font_put',id='geometry',font=self.font),dict(op='add',item=dict(id='label',content=dict(type='text',frame=frame)))])

    def edit(self,d,operations,expected=0):
        result=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],font_root=str(self.store),operations=operations),expected)
        return result if expected else result['document']

    def inspect(self,d,expected=0,**options):
        return self.invoke(dict(command='text.inspect',document=d,id='label',font_root=str(self.store),**options),expected)

    def pixels(self,d):
        result=self.invoke(dict(command='document.export',document=d,format='png',font_root=str(self.store)))
        return editing.png_pixels(base64.b64decode(result['data']))[:3]

    def test_font_store_identity_retained_license_dedup_and_source_preservation(self):
        original=self.source.read_bytes();license=self.license.read_bytes()
        self.assertEqual(self.font['sha256'],hashlib.sha256(original).hexdigest())
        self.assertEqual(self.font['license_sha256'],hashlib.sha256(license).hexdigest())
        self.assertEqual((self.store/(self.font['sha256']+'.font')).read_bytes(),original)
        self.assertEqual((self.store/(self.font['license_sha256']+'.license')).read_bytes(),license)
        second=self.invoke(dict(command='font.import',source_path=str(self.source),license_path=str(self.license),store_root=str(self.store)))
        self.assertEqual(self.font,second);self.assertEqual(len(list(self.store.iterdir())),2)
        self.assertTrue(self.invoke(dict(command='font.verify',font=self.font,font_root=str(self.store)))['valid'])
        self.assertEqual(self.source.read_bytes(),original);self.assertEqual(self.license.read_bytes(),license)

    def test_editable_vector_and_raster_text_glyph_bounds_and_independent_pixels(self):
        for kind in ('vector','raster'):
            d=self.document(kind);r=self.inspect(d,include_outlines=True)
            self.assertEqual(r['layout']['ink_bounds'],[0.5,1.0,10.5,8.0])
            self.assertEqual([g['origin'] for g in r['layout']['glyphs']],[[0,8],[6,8]])
            self.assertEqual(r['layout']['lines'][0]['advance'],12)
            w,h,p=self.pixels(d)
            for y in range(h):
                for x in range(w):
                    pixel=p[(y*w+x)*4:(y*w+x+1)*4]
                    if 1<=y<8 and (1<=x<4 or 7<=x<10):self.assertEqual(pixel,bytes([25,100,200,255]))
                    elif y<1 or y>=8 or x>=11:self.assertEqual(pixel,bytes(4))
            revised=self.edit(d,[dict(op='text_range',id='label',start=0,end=1,text='B')])
            self.assertEqual(d['items'][0]['content']['frame']['text'],'AA')
            self.assertEqual(revised['items'][0]['content']['frame']['text'],'BA')
            saved=self.invoke(dict(command='document.export',document=revised,format='snapshot'))
            restored=self.invoke(dict(command='document.validate',document=json.loads(saved['data'])))
            self.assertEqual(revised,restored);self.assertEqual(self.pixels(restored),self.pixels(revised))

    def test_character_ranges_quadratic_bounds_outline_and_svg_agree(self):
        d=self.document(text='AB')
        layout=self.inspect(d,include_outlines=True)['layout']
        # A has a 600-unit advance, with a declared AB kern of -100. B is an arch
        # with control y=1000 and true maximum y=500, not its control-box maximum.
        self.assertEqual(layout['glyphs'][1]['origin'],[5,8])
        self.assertEqual(layout['glyphs'][1]['ink_bounds'],[5,3,15,8])
        style=dict(font_id='geometry',size=20,fill=[220,30,70,255])
        revised=self.edit(d,[dict(op='text_range',id='label',start=1,end=2,style=style)])
        self.assertEqual(revised['items'][0]['content']['frame']['ranges'],[dict(start=1,end=2,style={**style,'tracking':0.0})])
        outlined=self.edit(revised,[dict(op='text_outline',id='label')])
        self.assertEqual(self.pixels(revised),self.pixels(outlined))
        self.assertEqual(revised['items'][0]['content']['type'],'text')
        self.assertEqual(outlined['items'][0]['id'],'label');self.assertEqual(outlined['items'][0]['content']['type'],'group')
        svg=self.invoke(dict(command='document.export',document=revised,format='svg',font_root=str(self.store)))
        root=ET.fromstring(svg['data']);ns={'s':'http://www.w3.org/2000/svg'}
        self.assertFalse(root.findall('.//s:text',ns));self.assertEqual(len(root.findall('.//s:path',ns)),2)
        self.assertIn('C',root.findall('.//s:path',ns)[1].attrib['d'])
        self.assertTrue(any('Text exports as glyph outlines' in loss for loss in svg['losses']))

    def test_wrap_alignment_tracking_leading_and_unicode_contents_persist(self):
        for kind in ('vector','raster'):
            d=self.document(kind,text='AA AA',width=15,leading=14,align='center')
            layout=self.inspect(d)['layout'];self.assertEqual([(l['start'],l['end']) for l in layout['lines']],[(0,2),(3,5)])
            self.assertEqual([l['x'] for l in layout['lines']],[1.5,1.5]);self.assertEqual([l['baseline'] for l in layout['lines']],[8,22])
            frame=copy.deepcopy(d['items'][0]['content']['frame']);frame['style']['tracking']=2;frame['width']=20;frame['align']='right'
            changed=self.edit(d,[dict(op='text',id='label',frame=frame)])
            layout=self.inspect(changed)['layout'];self.assertEqual([l['advance'] for l in layout['lines']],[14,14]);self.assertEqual([l['x'] for l in layout['lines']],[6,6])
            self.assertEqual(changed['items'][0]['content']['frame']['text'],'AA AA')
            unicode=self.document(kind,text='é😀');glyphs=self.inspect(unicode)['layout']['glyphs']
            self.assertEqual([(g['start'],g['end']) for g in glyphs],[(0,1),(1,2)])
            unicode=self.edit(unicode,[dict(op='text_range',id='label',start=1,end=2,text='A')])
            self.assertEqual(unicode['items'][0]['content']['frame']['text'],'éA')

    def test_overflow_clip_visible_transform_and_opacity_preserve_outlines(self):
        d=self.document(text='AA',width=8,height=5,wrap=False)
        self.assertEqual(self.inspect(d,1)['code'],'TEXT_OVERFLOW')
        error=self.invoke(dict(command='document.render',document=d,font_root=str(self.store)),1)
        self.assertEqual(error['code'],'TEXT_OVERFLOW');self.assertEqual(error['item_id'],'label')
        for overflow in ('clip','visible'):
            d=self.document(text='AA',width=8,height=5,wrap=False,overflow=overflow)
            d=self.edit(d,[dict(op='transform',id='label',matrix=[2,0,0,2,3,4]),dict(op='properties',id='label',opacity=0.5)])
            self.assertEqual(self.inspect(d)['world_ink_bounds'],[4,6,24,20])
            outlined=self.edit(d,[dict(op='text_outline',id='label')]);self.assertEqual(self.pixels(d),self.pixels(outlined))
            w,h,p=self.pixels(d)
            self.assertEqual(p[(10*w+7)*4:(10*w+7+1)*4],bytes([25,100,200,128]))
            if overflow=='clip':self.assertTrue(all(p[(y*w+x)*4+3]==0 for y in range(14,h) for x in range(w)))

    def test_missing_corrupt_and_locked_fonts_and_atomic_text_failure(self):
        d=self.document();before=copy.deepcopy(d)
        self.assertEqual(self.invoke(dict(command='text.inspect',document=d,id='label'),1)['code'],'FONT_ROOT_REQUIRED')
        bad=self.document(text='X');error=self.inspect(bad,1);self.assertEqual(error['code'],'MISSING_GLYPH');self.assertEqual(error['font_id'],'geometry')
        self.assertEqual(self.edit(d,[dict(op='font_remove',id='geometry')],1)['code'],'FONT_IN_USE')
        locked=self.edit(d,[dict(op='properties',id='label',locked=True)])
        self.assertEqual(self.edit(locked,[dict(op='font_put',id='geometry',font=self.font)],1)['code'],'LOCKED')
        self.assertEqual(self.edit(d,[dict(op='text_range',id='label',start=0,end=1,text='B'),dict(op='remove',id='absent')],1)['operation_index'],1)
        self.assertEqual(d,before)
        file=self.store/(self.font['sha256']+'.font');data=file.read_bytes();file.unlink()
        error=self.inspect(d,1);self.assertEqual(error['code'],'FONT_MISSING');self.assertEqual(error['font_id'],'geometry')
        file.write_bytes(bytes([data[0]^1])+data[1:]);self.assertEqual(self.inspect(d,1)['code'],'FONT_CORRUPT')
        self.assertEqual(self.invoke(dict(command='font.import',source_path=str(self.source),license_path=str(self.license),store_root=str(self.store)),1)['code'],'FONT_CORRUPT')
        self.assertNotEqual(file.read_bytes(),data)

    def test_ranges_grapheme_boundaries_limits_and_unsupported_controls(self):
        d=self.document(text='A\u0301');style=dict(font_id='geometry',size=10,fill=[0,0,0,255])
        self.assertEqual(self.edit(d,[dict(op='text_range',id='label',start=1,end=2,style=style)],1)['code'],'INVALID_DOCUMENT')
        for field,value in [('text','A'*4097),('ranges',[dict(start=0,end=1,style=style)]*65)]:
            bad=copy.deepcopy(d);bad['items'][0]['content']['frame'][field]=value
            self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],'RESOURCE_LIMIT')
        for text in ('A\tA','A\u202eA'):
            bad=copy.deepcopy(d);bad['items'][0]['content']['frame']['text']=text
            self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],'UNSUPPORTED')
        d=self.document(text='AA',direction='rtl');glyphs=self.inspect(d)['layout']['glyphs']
        self.assertEqual([g['start'] for g in glyphs],[1,0])

    def test_outline_expansion_limits_hidden_fonts_and_retained_license_failures(self):
        d=self.document(text='A'*1000,width=10000,height=20)
        self.assertGreater(len(self.inspect(d)['layout']['glyphs']),900)
        self.assertTrue(any(self.pixels(d)[2]))
        self.assertEqual(self.edit(d,[dict(op='text_outline',id='label')],1)['code'],'RESOURCE_LIMIT')
        self.assertEqual(self.invoke(dict(command='document.export',document=d,format='svg',font_root=str(self.store)),1)['code'],'RESOURCE_LIMIT')
        raster=self.document(kind='raster')
        self.assertEqual(self.invoke(dict(command='document.export',document=raster,format='svg'),1)['code'],'UNSUPPORTED')
        hidden=self.edit(self.document(),[dict(op='properties',id='label',visible=False)])
        license_file=self.store/(self.font['license_sha256']+'.license');license_file.unlink()
        error=self.invoke(dict(command='document.render',document=hidden,font_root=str(self.store)),1)
        self.assertEqual(error['code'],'FONT_MISSING');self.assertEqual(error['font_id'],'geometry')
        self.source.write_bytes(b'not a font')
        self.assertEqual(self.invoke(dict(command='font.import',source_path=str(self.source),license_path=str(self.license),store_root=str(self.store)),1)['code'],'INVALID_FONT')


if __name__=='__main__':unittest.main()
