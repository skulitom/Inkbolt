"""Original color resources: exact declarations, independent tint pixels and history."""
import base64
import copy
from fractions import Fraction as F
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import test_editing_cli as editing
import test_instances_cli as instances
import test_boards_cli as boards
import test_text_cli as text_tests
from test_mcp import Client


def process(name='Process',space='srgb',components=None,**kw):
    color=dict(space=space,**kw)
    if components is not None:color['components']=components
    return dict(name=name,definition=dict(type='process',color=color))
def spot(name='Spot',rgb=None):return dict(name=name,definition=dict(type='spot',alternate=dict(space='srgb',components=rgb or [.125,.5,.875])))
def tint(base,value,name='Tint'):return dict(name=name,definition=dict(type='tint',base=base,tint=value))
def paint(id='ink',tint=1,opacity=1):return dict(swatch=id,tint=tint,opacity=opacity)
def rectangle(id='art',fill=None,x=0,y=0,w=4,h=4,**kw):return dict(id=id,content=dict(type='vector',geometry=dict(shape='rect',x=x,y=y,width=w,height=h),fill=fill or paint()),**kw)
def byte(v):return int(F(v)*255+F(1,2))


class SwatchTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def document(self,swatches=None,items=None,kind='vector',w=16,h=8):
        d=self.invoke(dict(command='document.create',id='swatch-fixture',kind=kind,width=w,height=h));d['swatches']=swatches or {'ink':spot()};d['items']=items or [rectangle()]
        return self.invoke(dict(command='document.validate',document=d))
    def edit(self,d,ops,expected=0,**kw):
        v=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=ops,**kw),expected)
        return v if expected else v['document']
    def set(self,d,id,swatch,expected=0):return self.edit(d,[dict(op='swatch',id=id,swatch=swatch)],expected)
    def inspect(self,d):return self.invoke(dict(command='swatch.inspect',document=d))
    def pixels(self,d,**kw):
        r=self.invoke(dict(command='document.render',document=d,**kw));return r,bytes.fromhex(r['data'])
    def export(self,d,format='snapshot',expected=0,**kw):return self.invoke(dict(command='document.export',document=d,format=format,**kw),expected)

    def test_exact_process_spot_and_named_tint_declarations_survive_snapshot(self):
        values={'rgb':process('Signal <&> \u03bb','srgb',[.12345678901234567,.4567890123456789,.8765432109876543]),
            'gray':process('Neutral','gray',component=.23456789012345678),
            'cmyk':process('Ink fractions','cmyk',[.0123456789012345,.2345678901234567,.4567890123456789,.67890123456789]),
            'lab':process('Lab declaration','lab',[52.1234567890123,-33.2345678901234,41.9876543210987]),
            'ink':spot(),'shade':tint('ink',.3456789012345678),'pale':tint('shade',.12345678901234567)}
        d=self.document(values,[rectangle(fill=paint('pale',.2345678901234567,.4567890123456789))]);before=copy.deepcopy(d)
        restored=self.invoke(dict(command='document.validate',document=json.loads(self.export(d)['data'])))
        self.assertEqual(restored,d);self.assertEqual(d['swatches'],values);self.assertEqual(restored['items'],d['items'])
        r=self.inspect(d);entries={s['id']:s for s in r['swatches']};self.assertIsNone(entries['cmyk']['preview_rgba']);self.assertIsNone(entries['lab']['preview_rgba'])
        self.assertEqual(entries['pale']['resolved']['spot_id'],'ink');self.assertEqual(entries['ink']['used_by'],['art']);self.assertEqual(d,before)

    def test_all_tints_and_opacities_match_independent_rational_pixels_without_early_rounding(self):
        for kind in ['vector','raster']:
            for amount in [0,.125,.5,.875,1]:
                for opacity in [0,.25,1]:
                    p=paint('pale',amount,opacity);item=rectangle(fill=p) if kind=='vector' else dict(id='art',content=dict(type='fill',width=4,height=4,paint=p))
                    d=self.document({'ink':spot(),'shade':tint('ink',.5),'pale':tint('shade',.25)},[item],kind)
                    r,pixels=self.pixels(d);t=F(1,8)*F(amount)
                    rgba=bytes([byte(1+t*(F(c)-1)) for c in [.125,.5,.875]]+[byte(opacity)]) if opacity else bytes(4)
                    expected=b''.join(rgba if x<4 and y<4 else bytes(4) for y in range(8) for x in range(16));self.assertEqual(pixels,expected)
                    self.assertFalse(r['swatches']['native_ink_preservation']);self.assertIn('display',r['swatches']['color'])

    def test_precise_solid_is_validated_and_keeps_sub_byte_color_until_compositing(self):
        d=self.document({'ink':spot()},[rectangle(fill=dict(rgba=[1/1024,.25,.5,.5]))])
        _,p=self.pixels(d);self.assertEqual(p[:4],bytes([0,64,128,128]))
        self.assertEqual(json.loads(self.export(d)['data'])['items'][0]['content']['fill']['rgba'],[1/1024,.25,.5,.5])
        for rgba in [[-1,0,0,1],[0,0,0,2]]:
            bad=copy.deepcopy(d);bad['items'][0]['content']['fill']=dict(rgba=rgba);self.invoke(dict(command='document.validate',document=bad),1)

    def test_non_rgb_requires_explicit_preview_and_never_replaces_native_values(self):
        for space,components in [('cmyk',[.1,.2,.3,.4]),('lab',[50,-20,30])]:
            s=process(space,space,components);d=self.document({'ink':s});before=copy.deepcopy(d)
            self.assertEqual(self.export(d,'png',1)['code'],'SWATCH_PREVIEW_REQUIRED');self.assertEqual(json.loads(self.export(d)['data']),d)
            s=copy.deepcopy(s);s['definition']['color']['preview_srgb']=[.25,.5,.75];preview=self.set(d,'ink',s)
            _,p=self.pixels(preview);self.assertEqual(p[:4],bytes([64,128,191,255]));self.assertEqual(preview['swatches']['ink']['definition']['color']['components'],components)
            self.assertEqual(self.export(preview,'svg',1)['code'],'UNSUPPORTED');self.assertEqual(self.export(preview,'pdf',1)['code'],'UNSUPPORTED');self.assertEqual(d,before)

    def test_spot_vector_delivery_requires_explicit_bake_and_palette_survives(self):
        d=self.document({'ink':spot(),'shade':tint('ink',.5)},[rectangle(fill=paint('shade',.5,.75))]);source=copy.deepcopy(d)
        for format in ['svg','pdf']:self.assertEqual(self.export(d,format,1)['code'],'UNSUPPORTED')
        baked=self.edit(d,[dict(op='swatch_bake',ids=['art'])]);self.assertEqual(baked['swatches'],d['swatches']);self.assertEqual(self.pixels(baked)[1],self.pixels(d)[1])
        rgba=baked['items'][0]['content']['fill']['rgba'];self.assertEqual(rgba,[.78125,.875,.96875,.75])
        svg=self.export(baked,'svg');ET.fromstring(svg['data']);self.export(baked,'pdf')
        recolored=self.set(baked,'ink',spot(rgb=[1,0,0]));self.assertEqual(self.pixels(recolored)[1],self.pixels(baked)[1]);self.assertEqual(d,source)

    def test_process_srgb_and_gray_svg_pdf_use_precise_numeric_paints_with_losses(self):
        for swatch in [process(components=[.125,.5,.875]),process(space='gray',component=.375)]:
            d=self.document({'ink':swatch});svg=self.export(d,'svg');root=ET.fromstring(svg['data']);shape=next(e for e in root.iter() if e.tag.endswith('rect') and 'fill' in e.attrib)
            self.assertIn('%',shape.attrib['fill']);self.assertIn('swatches',svg)
            pdf=self.export(d,'pdf');self.assertTrue(base64.b64decode(pdf['data']).startswith(b'%PDF-1.7'));self.assertIn('swatches',pdf)

    def test_recolor_changes_all_live_users_and_tints_but_preserves_source_geometry(self):
        d=self.document({'ink':spot(),'shade':tint('ink',.5)},[rectangle('a'),rectangle('b',fill=paint('shade'),x=6)])
        changed=self.set(d,'ink',spot('Renamed',rgb=[1,0,0]));_,p=self.pixels(changed)
        self.assertEqual(p[:4],bytes([255,0,0,255]));self.assertEqual(p[6*4:7*4],bytes([255,128,128,255]));self.assertEqual(changed['items'],d['items'])
        diff=self.invoke(dict(command='document.diff',before=d,after=changed,compare_pixels=True));self.assertEqual({v['id'] for v in diff['items']},{'a','b'})
        for item in diff['items']:self.assertIn('derived.swatch_source_sha256',item['fields'])
        self.assertEqual(diff['resources'][0]['kind'],'swatches')

    def test_palette_names_are_labels_and_duplicate_names_keep_distinct_ids(self):
        d=self.document({'ink':spot('Same'), 'other':process('Same',components=[0,1,0])},[rectangle(),rectangle('other-art',paint('other'),x=6)])
        entries=self.inspect(d)['swatches'];self.assertEqual([v['id'] for v in entries],['ink','other']);self.assertEqual([v['swatch']['name'] for v in entries],['Same','Same'])
        _,p=self.pixels(d);self.assertNotEqual(p[:4],p[24:28])

    def test_cycles_depth_missing_ids_and_invalid_values_fail_atomically(self):
        d=self.document();before=copy.deepcopy(d)
        for s in [tint('missing',.5),tint('ink',.5),tint('ink',-1),process(components=[0,2,0]),process(space='lab',components=[101,0,0]),spot('')]:
            self.set(d,'ink',s,1)
        bad=copy.deepcopy(d);bad['items'][0]['content']['fill']=paint('missing');self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],'SWATCH_NOT_FOUND')
        for n in range(7):d=self.set(d,'t'+str(n),tint('ink' if n==0 else 't'+str(n-1),.5))
        self.assertEqual(self.set(d,'too-deep',tint('t6',.5),1)['code'],'RESOURCE_LIMIT')
        self.assertEqual(before['swatches'],{'ink':spot()})

    def test_palette_limit_legacy_and_strict_reference_fields(self):
        d=self.document();d['swatches'].update({f's{i}':process(components=[0,0,0]) for i in range(256)})
        self.assertEqual(self.invoke(dict(command='document.validate',document=d),1)['code'],'RESOURCE_LIMIT')
        d=self.document();d['schema_version']=1;d['items']=[];self.invoke(dict(command='document.validate',document=d),1)
        for extra in [dict(unknown=True),dict(tint=1.1),dict(opacity=-.1)]:
            d=self.document();d['items'][0]['content']['fill'].update(extra);self.invoke(dict(command='document.validate',document=d),1)

    def test_used_resources_cannot_be_removed_and_locked_dependents_protect_palette(self):
        d=self.document({'ink':spot(),'shade':tint('ink',.5)},[rectangle(fill=paint('shade'))])
        self.assertEqual(self.set(d,'ink',None,1)['code'],'SWATCH_IN_USE');self.assertEqual(self.set(d,'shade',None,1)['code'],'SWATCH_IN_USE')
        locked=self.edit(d,[dict(op='properties',id='art',locked=True)])
        self.assertEqual(self.set(locked,'ink',spot(rgb=[1,0,0]),1)['code'],'LOCKED')
        self.assertEqual(self.edit(locked,[dict(op='swatch_bake',ids=['art'])],1)['code'],'LOCKED')
        self.pixels(locked);self.inspect(locked)
        baked=self.edit(d,[dict(op='swatch_bake',ids=['art'])]);baked=self.set(baked,'shade',None);baked=self.set(baked,'ink',None);self.assertNotIn('swatches',baked)

    def test_component_definitions_overrides_and_locked_instances_keep_resource_contract(self):
        d=instances.InstanceTests().document();d['swatches']={'ink':spot(),'other':spot(rgb=[1,0,0])};d['items'][1]['content']['fill']=paint()
        d['items'][-1]['content']['instance']['overrides']={'body':dict(vector_style=dict(fill=paint('other'),stroke=None))}
        d=self.invoke(dict(command='document.validate',document=d));changed=self.set(d,'ink',spot(rgb=[0,1,0]));_,p=self.pixels(changed)
        self.assertEqual(p[(5*36+3)*4:(5*36+4)*4],bytes([0,255,0,255]));self.assertEqual(p[(5*36+21)*4:(5*36+22)*4],bytes([255,0,0,255]))
        diff=self.invoke(dict(command='document.diff',before=d,after=changed));byid={i['id']:i for i in diff['items']};self.assertIn('derived.swatch_source_sha256',byid['left']['fields'])
        locked=self.edit(d,[dict(op='properties',id='left',locked=True)]);self.assertEqual(self.set(locked,'ink',spot(rgb=[0,0,0]),1)['code'],'LOCKED')

    def test_transfer_copies_only_transitive_palette_dependencies_and_remaps_independently(self):
        source=self.document({'ink':spot(),'shade':tint('ink',.5),'unused':process(components=[0,0,0])},[rectangle(fill=paint('shade'))])
        destination=self.invoke(dict(command='document.create',id='destination',kind='vector',width=16,height=8))
        operation=dict(op='transfer',transfer=dict(source=source,ids=['art'],prefix='copy'))
        changed=self.edit(destination,[operation]);self.assertEqual(set(changed['swatches']),{'copy-ink','copy-shade'});self.assertEqual(changed['swatches']['copy-shade']['definition']['base'],'copy-ink')
        self.assertEqual(changed['items'][0]['content']['fill']['swatch'],'copy-shade');self.assertEqual(self.pixels(changed)[1],self.pixels(source)[1])
        changed=self.set(changed,'copy-ink',spot(rgb=[1,0,0]));self.assertNotEqual(self.pixels(changed)[1],self.pixels(source)[1]);self.assertEqual(source['swatches']['ink'],spot())

    def test_artboard_export_retains_named_paints_and_exact_preview_samples(self):
        board=boards.BoardCliTests().board('page',8,6);d=self.document({'ink':spot()},[board,rectangle(parent='page')])
        result=self.invoke(dict(command='artboard.export',document=d,format='png',selection=dict(type='ids',ids=['page'])))
        artifact=result['artifacts'][0]['artifact'];self.assertIn('swatches',artifact)
        w,h,p,*_=editing.png_pixels(base64.b64decode(artifact['data']));self.assertEqual((w,h),(8,6));self.assertEqual(p[:4],bytes([32,128,223,255]))

    def test_named_stroke_and_effect_colors_share_tint_evaluation(self):
        item=rectangle(x=2,y=2,w=4,h=4);item['content']['fill']=None;item['content']['stroke']=dict(color=paint('ink',.5),width=2)
        d=self.document(items=[item]);_,p=self.pixels(d);color=bytes([143,191,239,255])
        expected=b''.join(color if 1<=x<7 and 1<=y<7 and not (3<=x<5 and 3<=y<5) else bytes(4) for y in range(8) for x in range(16));self.assertEqual(p,expected)
        item=rectangle(fill=[0,0,0,255],effects=[dict(id='ink-overlay',operator=dict(type='overlay'),color=paint('ink',.5))]);d=self.document(items=[item]);self.assertEqual(self.pixels(d)[1][:4],color)
        self.assertEqual(self.pixels(self.set(d,'ink',spot(rgb=[1,0,0])))[1][:4],bytes([255,128,128,255]))

    def test_named_mask_color_recolors_coverage_and_protects_locked_dependents(self):
        source=dict(id='source',content=dict(type='mask_source'))
        mask=rectangle('mask',fill=paint(),parent='source');art=rectangle('art',fill=[255,0,0,255],artwork_mask=dict(source='source',mode='luminance',region=[0,0,4,4]))
        d=self.document({'ink':process(space='gray',component=.5)},[source,mask,art]);_,p=self.pixels(d);self.assertEqual(p[:4],bytes([255,0,0,128]))
        changed=self.set(d,'ink',process(space='gray',component=.25));self.assertEqual(self.pixels(changed)[1][:4],bytes([255,0,0,64]))
        locked=self.edit(d,[dict(op='properties',id='art',locked=True)]);self.assertEqual(self.set(locked,'ink',process(space='gray',component=0),1)['code'],'LOCKED')

    def test_named_repeat_fill_stays_live_after_expansion(self):
        spec=dict(geometry=dict(shape='rect',x=0,y=0,width=2,height=2),fill=paint('ink',.5),origin=[1,1],anchor=[0,0],layout=dict(type='grid',columns=2,rows=2,step=[4,3]))
        d=self.document(items=[dict(id='repeated',content=dict(type='repeat',repeat=spec))]);_,p=self.pixels(d)
        color=bytes([143,191,239,255]);expected=b''.join(color if any(a<=x<a+2 and b<=y<b+2 for a in [1,5] for b in [1,4]) else bytes(4) for y in range(8) for x in range(16));self.assertEqual(p,expected)
        expanded=self.edit(d,[dict(op='repeat_expand',id='repeated')]);self.assertEqual(self.pixels(expanded)[1],p);self.assertEqual(expanded['items'][0]['content']['fill'],paint('ink',.5))
        self.assertEqual(self.pixels(self.set(expanded,'ink',spot(rgb=[1,0,0])))[1][(1*16+1)*4:(1*16+2)*4],bytes([255,128,128,255]))

    def test_atomic_batch_rolls_back_palette_changes_on_later_failure(self):
        d=self.document();s=self.export(d)['data'];ops=[dict(op='swatch',id='ink',swatch=spot(rgb=[1,0,0])),dict(op='remove',id='missing')]
        e=self.edit(d,ops,1);self.assertEqual(e['operation_index'],1);self.assertEqual(self.export(d)['data'],s)

    def test_text_ranges_variant_values_and_retained_glyph_geometry(self):
        t=text_tests.TextCliTests();t.setUp();self.addCleanup(t.doCleanups)
        d=t.document(text='AA');d['swatches']={'ink':spot(),'other':spot(rgb=[1,0,0])};frame=d['items'][0]['content']['frame'];frame['style']['fill']=paint();d=self.invoke(dict(command='document.validate',document=d))
        old=t.inspect(d)['layout'];recolored=self.set(d,'ink',spot(rgb=[0,1,0]));new=t.inspect(recolored)['layout'];self.assertEqual(old['ink_bounds'],new['ink_bounds'])
        _,p=self.pixels(recolored,font_root=str(t.store));self.assertEqual(p[(2*80+2)*4:(2*80+3)*4],bytes([0,255,0,255]))
        style=copy.deepcopy(frame['style']);style['fill']=paint('other');value=dict(type='text',value=dict(text='AA',ranges=[dict(start=0,end=1,style=style)]))
        definition=dict(bindings=[dict(key='caption',item_id='label',property='text')],datasets=dict(red=dict(values=dict(caption=value))))
        d=t.edit(d,[dict(op='variants_set',definition=definition)]);self.assertEqual(self.set(d,'other',None,1)['code'],'SWATCH_IN_USE')
        d=t.edit(d,[dict(op='variant_select',dataset='red')]);_,p=self.pixels(d,font_root=str(t.store));self.assertEqual(p[(2*80+2)*4:(2*80+3)*4],bytes([255,0,0,255]))

    def test_durable_mcp_palette_update_undo_redo_retry_and_publication(self):
        c=Client();self.addCleanup(c.close);c.initialize();d=self.document();self.assertEqual(c.success('swatch.inspect',document=d),self.inspect(d))
        with tempfile.TemporaryDirectory() as root:
            session=dict(session_root=root,session_id='swatches');c.success('session.create',**session,request_id='create',document=d)
            action=dict(type='edit',operations=[dict(op='swatch',id='ink',swatch=spot(rgb=[1,0,0]))]);changed=c.success('session.apply',**session,expected_revision=0,request_id='recolor',action=action)['document']
            output=dict(output_root=root,file_name='preview.png',format='png');receipt=c.success('session.publish',**session,expected_revision=1,output=output);self.assertIn('swatches',receipt)
            restored=c.success('session.apply',**session,expected_revision=1,request_id='undo',action=dict(type='undo'))['document'];self.assertEqual(restored,dict(d,revision=2))
            redone=c.success('session.apply',**session,expected_revision=2,request_id='redo',action=dict(type='redo'))['document'];self.assertEqual(redone,dict(changed,revision=3));self.assertTrue(c.success('session.verify',**session)['valid'])
            retry=c.success('session.apply',**session,expected_revision=0,request_id='recolor',action=action);self.assertTrue(retry['replayed']);self.assertEqual(retry['current_revision'],3)
            e=c.tool('session.publish',**session,expected_revision=3,output=output);self.assertEqual(e['structuredContent']['error']['code'],'OUTPUT_EXISTS')
            e=c.tool('session.apply',**session,expected_revision=3,request_id='cancel',action=action,control=dict(timeout_ms=0));self.assertEqual(e['structuredContent']['error']['code'],'TIMEOUT');self.assertEqual(c.success('session.read',**session)['document'],redone)


if __name__=='__main__':unittest.main()
