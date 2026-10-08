"""Original variable-font equations, OpenType controls and retained agent workflows."""
import base64
import copy
import json
from pathlib import Path
import tempfile
import unittest
import test_editing_cli as editing
import test_text_cli as base_text
from test_mcp import Client
from synthetic_variable_font import variable_font, tables
from synthetic_unicode_font import unicode_font, sfnt


def deformation(weight=400,width=100,remap=False):
    w=(weight-400)/(500 if weight>=400 else 300)
    d=(width-100)/(100 if width>=100 else 50)
    if remap and w>0: w=1.5*w if w<=.5 else .5*w+.5
    return (200*max(w,0)+20*min(w,0)+400*max(d,0)+30*min(d,0),
        100*max(w,0)+50*min(w,0),w,d)


class FontControlTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    edit=base_text.TextCliTests.edit
    inspect=base_text.TextCliTests.inspect
    pixels=base_text.TextCliTests.pixels

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name);self.store=self.directory/'store'
        self.license=self.directory/'LICENSE.txt';self.license.write_bytes((Path(__file__).resolve().parents[1]/'LICENSE').read_bytes())
        self.fonts={};self.sources={};self.add_font('variable',variable_font())

    def add_font(self,name,data):
        self.sources[name]=data;path=self.directory/(name+'.ttf');path.write_bytes(data)
        self.fonts[name]=self.invoke(dict(command='font.import',source_path=str(path),
            license_path=str(self.license),store_root=str(self.store)))

    def document(self,text='AA',kind='raster',font='variable',coords=None,features=None,**options):
        d=self.invoke(dict(command='document.create',id='font-controls',kind=kind,width=100,height=80))
        style=dict(font_id=font,size=10,fill=[25,100,200,255])
        if coords is not None:style['font_variations']={font:coords}
        if features is not None:style['features']=features
        frame=dict(text=text,width=100,height=80,style=style,wrap=False,overflow='visible');frame.update(options)
        return self.edit(d,[dict(op='font_put',id=id,font=desc) for id,desc in self.fonts.items()]+
            [dict(op='add',item=dict(id='label',content=dict(type='text',frame=frame)))])

    def font_info(self,name='variable',coords=None,expected=0):
        return self.invoke(dict(command='font.inspect',font=self.fonts[name],font_root=str(self.store),
            variations=coords or {}),expected)

    def glyphs(self,d):return self.inspect(d)['layout']['glyphs']

    def assert_points(self,a,b):
        self.assertEqual(len(a),len(b))
        for x,y in zip(a,b):self.assertAlmostEqual(x,y,places=11)

    def test_font_inspection_exposes_ranges_defaults_features_and_effective_coordinates(self):
        info=self.font_info()
        self.assertEqual((info['units_per_em'],info['glyph_count']),(1000,33))
        self.assertEqual([(a['tag'],a['minimum'],a['default'],a['maximum']) for a in info['axes']],
            [('wght',100,400,900),('wdth',50,100,200)])
        self.assertEqual(info['feature_tags'],['fina','init','isol','kern','liga','locl','mark','medi','salt','ss01'])
        for weight,width in [(100,50),(400,100),(650,150),(900,200)]:
            info=self.font_info(coords=dict(wght=weight,wdth=width))
            self.assertEqual([a['normalized_coordinate'] for a in info['axes']],list(deformation(weight,width)[2:]))
            self.assertEqual([a['effective_user_coordinate'] for a in info['axes']],[weight,width])

    def test_two_axis_outlines_and_phantom_advances_match_independent_equations(self):
        for kind in ['vector','raster']:
            for weight in [100,250,400,525,650,900]:
                for width in [50,75,100,150,200]:
                    coords=dict(wght=weight,wdth=width);d=self.document(kind=kind,coords=coords)
                    dx,dy,_,_=deformation(weight,width);advance=int(600+dx+.5)/100
                    for i,g in enumerate(self.glyphs(d)):
                        self.assertEqual(g['variations'],coords)
                        self.assertAlmostEqual(g['advance'],advance,places=11)
                        self.assert_points(g['origin'],[i*advance,10])
                        self.assert_points(g['ink_bounds'],[i*advance+.5,10-(410+dy)/100,i*advance+(170+dx)/100,10])

    def test_hvar_metrics_match_phantom_metrics_without_double_application(self):
        self.add_font('hvar',variable_font(hvar=True))
        for coords in [dict(wght=100,wdth=50),dict(wght=525,wdth=125),dict(wght=900,wdth=200)]:
            a=self.document(coords=coords);b=self.document(font='hvar',coords=coords)
            self.assertEqual(self.pixels(a),self.pixels(b))
            for x,y in zip(self.glyphs(a),self.glyphs(b)):
                self.assertEqual(x['advance'],y['advance']);self.assertEqual(x['ink_bounds'],y['ink_bounds'])

    def test_avar_remapping_controls_both_outlines_and_metrics(self):
        self.add_font('remapped',variable_font(avar=True,hvar=True))
        for weight in [400,525,650,775,900]:
            coords=dict(wght=weight,wdth=150);dx,dy,w,d=deformation(weight,150,True)
            info=self.font_info('remapped',coords)
            self.assertEqual([a['normalized_coordinate'] for a in info['axes']],[w,d])
            glyph=self.glyphs(self.document('A',font='remapped',coords=coords))[0]
            self.assertEqual(glyph['advance'],int(600+dx+.5)/100)
            self.assert_points(glyph['ink_bounds'],[.5,10-(410+dy)/100,(170+dx)/100,10])

    def test_mvar_instance_metrics_drive_baselines_and_paragraph_spacing(self):
        self.add_font('metrics',variable_font(avar=True,hvar=True,metrics=True))
        for weight in [100,400,650,900]:
            coords=dict(wght=weight);w=deformation(weight,100,True)[2]
            ascent=int(1000+200*max(w,0)+100*min(w,0))
            descent=int(-200-100*max(w,0)-50*min(w,0))
            gap=int(50*max(w,0)+25*min(w,0))
            info=self.font_info('metrics',coords)
            self.assertEqual((info['ascender'],info['descender'],info['line_gap']),(ascent,descent,gap))
            layout=self.inspect(self.document('A\nA',font='metrics',coords=coords))['layout']
            self.assert_points([l['baseline'] for l in layout['lines']],[ascent/100,(2*ascent-descent+gap)/100])

    def test_ligatures_explicit_disable_enable_and_tracking_precedence(self):
        for features,ids,advance in [({},[26,2],11),({'liga':0},[24,25,2],12),({'liga':1},[26,2],11)]:
            d=self.document('fiA',features=features);g=self.glyphs(d)
            self.assertEqual([v['glyph_id'] for v in g],ids)
            self.assertEqual(self.inspect(d)['layout']['lines'][0]['advance'],advance)
        d=self.document('fiA',features={'liga':1})
        frame=copy.deepcopy(d['items'][0]['content']['frame']);frame['style']['tracking']=2
        d=self.edit(d,[dict(op='text',id='label',frame=frame)])
        self.assertEqual([g['glyph_id'] for g in self.glyphs(d)],[26,2])
        self.assertEqual([g['advance'] for g in self.glyphs(d)],[7,6])
        del frame['style']['features']
        d=self.edit(d,[dict(op='text',id='label',frame=frame)])
        self.assertEqual([g['glyph_id'] for g in self.glyphs(d)],[24,25,2])

    def test_numeric_alternates_and_stylistic_substitution_use_selected_instance(self):
        for features,gid,advance in [({'salt':1},3,8.5),({'salt':2},5,7),({'ss01':1},3,8.5),({'ss01':0},2,8)]:
            d=self.document('A',features=features,coords={'wght':900});g=self.glyphs(d)[0]
            self.assertEqual((g['glyph_id'],g['advance']),(gid,advance))
            self.assert_points(g['ink_bounds'],[.5,10-(400+gid*5+100)/100,(150+gid*10+200)/100,10])
            self.assertEqual(g['features'],features)

    def test_kerning_control_changes_pair_spacing_and_preserves_cluster_indices(self):
        off=self.glyphs(self.document('AB',features={'kern':0}))
        on=self.glyphs(self.document('AB',features={'kern':1}))
        self.assertEqual([g['advance'] for g in off],[6,6.5]);self.assertEqual([g['advance'] for g in on],[5.5,6])
        self.assertEqual([g['origin'][0] for g in off],[0,6]);self.assertEqual([g['origin'][0] for g in on],[0,5])
        self.assertEqual([(g['start'],g['end']) for g in on],[(0,1),(1,2)])

    def test_feature_availability_errors_are_explicit_and_disabled_unknown_tags_are_noop(self):
        d=self.document('A',features={'zzzz':1})
        error=self.inspect(d,1);self.assertEqual((error['code'],error['font_id']),('FONT_FEATURE_UNAVAILABLE','variable'))
        off=self.document('A',features={'zzzz':0});self.assertEqual(self.pixels(off),self.pixels(self.document('A')))
        malformed=self.document();malformed['items'][0]['content']['frame']['style']['features']={'abc':1}
        self.assertEqual(self.invoke(dict(command='document.validate',document=malformed),1)['code'],'INVALID_DOCUMENT')
        malformed['items'][0]['content']['frame']['style']['features']={str(i).zfill(4):0 for i in range(65)}
        self.assertEqual(self.invoke(dict(command='document.validate',document=malformed),1)['code'],'RESOURCE_LIMIT')

    def test_axis_bounds_unknown_axes_inactive_fallbacks_and_strict_maps(self):
        for coords,code in [({'wght':99},'FONT_AXIS_RANGE'),({'wght':901},'FONT_AXIS_RANGE'),({'opsz':12},'FONT_AXIS_UNAVAILABLE')]:
            self.assertEqual(self.font_info(coords=coords,expected=1)['code'],code)
            self.assertEqual(self.inspect(self.document(coords=coords),1)['code'],code)
        self.add_font('static',unicode_font('arabic'))
        d=self.document();frame=d['items'][0]['content']['frame'];frame['style']['fallback_fonts']=['static']
        frame['style']['font_variations']={'static':{'wght':400}}
        self.assertEqual(self.inspect(d,1)['code'],'FONT_AXIS_UNAVAILABLE')
        frame['style']['font_variations']={'unknown':{}}
        self.assertEqual(self.invoke(dict(command='document.validate',document=d),1)['code'],'INVALID_DOCUMENT')
        frame['style']['font_variations']={'variable':{str(i).zfill(4):0 for i in range(17)}}
        self.assertEqual(self.invoke(dict(command='document.validate',document=d),1)['code'],'RESOURCE_LIMIT')

    def test_unreadable_variation_tables_fail_before_render_or_publication(self):
        data=tables(variable_font());data[b'avar']=b'\0\2\0\0\0\0\0\2'
        self.add_font('unsupported',sfnt(data))
        self.assertEqual(self.font_info('unsupported',{'wght':650},expected=1)['code'],'UNSUPPORTED')
        d=self.document(font='unsupported',coords={'wght':650});out=self.directory/'delivery';out.mkdir()
        error=self.invoke(dict(command='document.publish',document=d,resources=dict(font_root=str(self.store)),
            output=dict(output_root=str(out),file_name='invalid.png',format='png')),1)
        self.assertEqual(error['code'],'UNSUPPORTED');self.assertEqual(list(out.iterdir()),[])

    def test_font_specific_fallback_axes_and_metrics_follow_the_actual_font(self):
        self.add_font('latin',unicode_font('latin'));self.add_font('fallback',variable_font('arabic',metrics=True))
        d=self.document('\u0628\u0628',font='latin',direction='rtl')
        frame=d['items'][0]['content']['frame'];frame['style']['fallback_fonts']=['fallback']
        frame['style']['font_variations']={'fallback':{'wght':900}}
        g=self.glyphs(d)
        self.assertEqual([v['font_id'] for v in g],['fallback','fallback'])
        self.assertEqual([v['glyph_id'] for v in g],[11,9])
        self.assertEqual([v['advance'] for v in g],[8,8]);self.assertEqual([v['origin'][1] for v in g],[12,12])
        frame['style']['features']={'ss01':1}
        self.assertEqual([v['glyph_id'] for v in self.glyphs(d)],[11,9]) # font has tag; unrelated script stays unchanged.

    def test_style_ranges_keep_independent_instances_and_original_source_bytes(self):
        d=self.document('AAA');original=copy.deepcopy(d)
        for index,weight in [(0,100),(1,650),(2,900)]:
            s=dict(font_id='variable',font_variations={'variable':{'wght':weight}},size=10,fill=[25,100,200,255])
            d=self.edit(d,[dict(op='text_range',id='label',start=index,end=index+1,style=s)])
        self.assertEqual([g['advance'] for g in self.glyphs(d)],[5.8,7,8])
        self.assertEqual([g['variations'] for g in self.glyphs(d)],[{'wght':100},{'wght':650},{'wght':900}])
        self.assertEqual(original['items'][0]['content']['frame']['ranges'],[])
        self.assertEqual((self.directory/'variable.ttf').read_bytes(),self.sources['variable'])
        self.assertEqual(json.loads(self.invoke(dict(command='document.export',document=d,format='snapshot'))['data']),d)

    def test_path_text_offsets_transforms_and_actual_instance_outlines(self):
        path=dict(geometry=dict(shape='path',commands=[dict(verb='move',to=[5,30]),dict(verb='line',to=[90,30])]))
        for kind in ['raster','vector']:
            d=self.document('AA',kind,coords={'wght':900},path=path)
            for g,p in zip(self.glyphs(d),[[5,30],[13,30]]): self.assert_points(g['origin'],p)
            self.assert_points(self.glyphs(d)[0]['ink_bounds'],[5.5,24.9,8.7,30])
            d=self.edit(d,[dict(op='transform',id='label',matrix=[1.5,.25,.5,1.25,3,2])])
            if kind=='vector':
                outlined=self.edit(d,[dict(op='text_outline',id='label')]);self.assertEqual(self.pixels(d),self.pixels(outlined))
            self.assertEqual(self.inspect(d)['frame']['style']['font_variations'],{'variable':{'wght':900}})

    def test_exact_independent_variable_glyph_pixels_and_outline_svg_delivery(self):
        for kind in ['raster','vector']:
            d=self.document('AA',kind,coords={'wght':900,'wdth':200})
            d=self.edit(d,[dict(op='transform',id='label',matrix=[5,0,0,5,3,2])])
            result=self.invoke(dict(command='document.export',document=d,format='png',scale=4,font_root=str(self.store)))
            w,h,p=editing.png_pixels(base64.b64decode(result['data']))[:3]
            # A's authored x=[50,170+600], y=[0,410+100]; advance=1200font units.
            boxes=[[22+240*i,106,166+240*i,208] for i in range(2)]
            expected=bytes(v for y in range(h) for x in range(w) for v in
                ([25,100,200,255] if any(a<=x<c and b<=y<e for a,b,c,e in boxes) else [0]*4))
            self.assertEqual(p,expected)
            if kind=='vector':
                outline=self.edit(d,[dict(op='text_outline',id='label')]);self.assertEqual(self.pixels(d),self.pixels(outline))
                svg=self.invoke(dict(command='document.export',document=d,format='svg',font_root=str(self.store)))
                self.assertIn('<path',svg['data']);self.assertNotIn('<text',svg['data'])

    def test_transfer_remaps_instance_keys_and_preserves_independent_settings(self):
        source=self.document(kind='vector',coords={'wght':900},features={'ss01':1});before=copy.deepcopy(source)
        empty=self.invoke(dict(command='document.create',id='destination',kind='vector',width=100,height=80))
        copied=self.edit(empty,[dict(op='transfer',transfer=dict(source=source,ids=['label'],prefix='copy',verify_resources=True))])
        style=copied['items'][0]['content']['frame']['style']
        self.assertEqual(style['font_variations'],{'copy-variable':{'wght':900}})
        self.assertEqual(style['features'],{'ss01':1});self.assertEqual(self.pixels(copied),self.pixels(source));self.assertEqual(source,before)

    def test_missing_corrupt_and_hidden_fonts_keep_specific_diagnostics(self):
        d=self.document(coords={'wght':650});hidden=self.edit(d,[dict(op='properties',id='label',visible=False)])
        error=self.invoke(dict(command='text.inspect',document=d,id='label'),1)
        self.assertEqual((error['code'],error['font_id']),('FONT_ROOT_REQUIRED','variable'))
        path=self.store/(self.fonts['variable']['sha256']+'.font');original=path.read_bytes();path.unlink()
        error=self.inspect(hidden,1);self.assertEqual((error['code'],error['font_id']),('FONT_MISSING','variable'))
        path.write_bytes(bytes([original[0]^1])+original[1:])
        self.assertEqual(self.inspect(hidden,1)['code'],'FONT_CORRUPT')
        self.assertEqual(self.font_info(expected=1)['code'],'FONT_CORRUPT')

    def test_instance_edits_affect_wrap_bounds_and_allow_clearing_controls(self):
        plain=self.document('AAAA',wrap=True,width=13)
        changed=self.document('AAAA',coords={'wght':900,'wdth':200},wrap=True,width=13)
        self.assertEqual([(l['start'],l['end']) for l in self.inspect(plain)['layout']['lines']],[(0,2),(2,4)])
        self.assertEqual([(l['start'],l['end']) for l in self.inspect(changed)['layout']['lines']],[(0,1),(1,2),(2,3),(3,4)])
        frame=copy.deepcopy(changed['items'][0]['content']['frame']);frame['style']['font_variations']={}
        cleared=self.edit(changed,[dict(op='text',id='label',frame=frame)])
        self.assertEqual(self.pixels(plain),self.pixels(cleared));self.assertNotIn('font_variations',cleared['items'][0]['content']['frame']['style'])

    def test_instance_dependencies_components_and_locked_source_protection(self):
        d=self.document(kind='vector',coords={'wght':650});reference=self.pixels(d)
        d['items'][0]['parent']='source';d['items'].insert(0,dict(id='source',content=dict(type='component_source')))
        d['items'].append(dict(id='copy',content=dict(type='instance',instance=dict(source='source'))))
        self.assertEqual(self.pixels(d),reference)
        locked=copy.deepcopy(d);locked['items'][-1]['locked']=True
        self.assertEqual(self.edit(locked,[dict(op='font_put',id='variable',font=self.fonts['variable'])],1)['code'],'LOCKED')
        self.assertEqual(self.edit(d,[dict(op='font_remove',id='variable')],1)['code'],'FONT_IN_USE')

    def test_mcp_font_discovery_persistent_axis_feature_edits_and_undo_redo(self):
        c=Client();self.addCleanup(c.close);c.initialize();d=self.document()
        info=c.success('font.inspect',font=self.fonts['variable'],font_root=str(self.store),variations={'wght':900})
        self.assertEqual(info['axes'][0]['normalized_coordinate'],1)
        session=dict(session_root=str(self.directory/'sessions'),session_id='font-controls')
        d=c.success('session.create',**session,request_id='create',document=d,resources=dict(font_root=str(self.store)))['document']
        frame=copy.deepcopy(d['items'][0]['content']['frame'])
        frame['style'].update(font_variations={'variable':{'wght':900}},features={'salt':2})
        args=dict(**session,expected_revision=0,request_id='controls',action=dict(type='edit',operations=[dict(op='text',id='label',frame=frame)]))
        changed=c.success('session.apply',**args)['document'];self.assertTrue(c.success('session.apply',**args)['replayed'])
        self.assertEqual([g['glyph_id'] for g in self.glyphs(changed)],[5,5])
        undone=c.success('session.apply',**session,expected_revision=1,request_id='undo',action=dict(type='undo'))['document']
        self.assertEqual(undone['items'],d['items'])
        redone=c.success('session.apply',**session,expected_revision=2,request_id='redo',action=dict(type='redo'))['document']
        self.assertEqual(redone['items'],changed['items'])
        c.success('session.publish',**session,expected_revision=3,
            output=dict(output_root=str(self.directory),file_name='variable.png',format='png'))
        self.assertTrue((self.directory/'variable.png').is_file())


if __name__=='__main__':unittest.main()
