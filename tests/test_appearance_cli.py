"""Original retained paint-stack, geometry/raster order, expansion and history checks."""
import base64
import copy
from fractions import Fraction as F
import json
from pathlib import Path
import tempfile
import unittest
import test_editing_cli as editing
import test_variants_cli as variants
from test_mcp import Client
import test_transfer_cli as transfer


def original():
    g=dict(shape='rect',x=8,y=6,width=8,height=6)
    spec=dict(geometry=g,passes=[
        dict(id='outer',stroke=dict(color=[20,40,60,255],width=6,join='miter')),
        dict(id='body',fill=[210,30,10,255]),
        dict(id='inner',stroke=dict(color=[20,80,230,128],width=2,join='miter')),
        dict(id='shifted',fill=[30,200,80,128],maps=[dict(type='affine',matrix=[1,0,0,1,3,4])])])
    return dict(schema_version=2,id='appearance-document',kind='vector',width=24,height=20,color_space='srgb',items=[dict(id='icon',content=dict(type='appearance',appearance=spec))])


def opaque_reference(reverse=False):
    layers=[(lambda x,y:5<=x<19 and 3<=y<15 and not(11<=x<13 and 9<=y<9),[20,40,60,255]),
            (lambda x,y:8<=x<16 and 6<=y<12,[210,30,10,255]),
            (lambda x,y:7<=x<17 and 5<=y<13 and not(9<=x<15 and 7<=y<11),[20,80,230,128]),
            (lambda x,y:11<=x<19 and 10<=y<16,[30,200,80,128])]
    if reverse:layers.reverse()
    pixels=[]
    for y in range(20):
        for x in range(24):
            color=[F(0)]*3;alpha=F(0)
            for hit,rgba in layers:
                if hit(x+.5,y+.5):
                    a=F(rgba[3],255);color=[F(rgba[c],255)*a+color[c]*(1-a) for c in range(3)];alpha=a+alpha*(1-a)
            pixels.extend([int(v/alpha*255+F(1,2)) for v in color]+[int(alpha*255+F(1,2))] if alpha else [0]*4)
    return bytes(pixels)


class AppearanceTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    edit=variants.VariantTests.edit
    def valid(self,d):return self.invoke(dict(command='document.validate',document=d))
    def image(self,d,**kw):return editing.png_pixels(base64.b64decode(self.invoke(dict(command='document.export',document=d,format='png',**kw))['data']))[2]

    def test_multiple_fills_strokes_order_and_exact_original_pixels(self):
        d=self.valid(original());before=copy.deepcopy(d);self.assertEqual(self.image(d),opaque_reference())
        spec=copy.deepcopy(d['items'][0]['content']['appearance']);spec['passes'].reverse();out=self.edit(d,dict(op='appearance',id='icon',appearance=spec))
        self.assertEqual(self.image(out),opaque_reference(True));self.assertNotEqual(self.image(d),self.image(out))
        self.assertEqual(json.loads(self.invoke(dict(command='document.export',document=d,format='snapshot'))['data']),before)
        report=self.invoke(dict(command='appearance.inspect',document=d,id='icon'));self.assertEqual(report['source'],original()['items'][0]['content']['appearance']['geometry']);self.assertEqual(report['order'],'bottom_to_top')

    def test_vector_map_order_preserved_through_editable_object_expansion(self):
        d=original();p=d['items'][0]['content']['appearance']['passes'][0];d['items'][0]['content']['appearance']['passes']=[p];p.pop('stroke');p['fill']=[10,80,200,255]
        p['maps']=[dict(type='affine',matrix=[1,0,0,1,2,1]),dict(type='affine',matrix=[.5,0,0,.5,0,0])]
        d=self.valid(d);rendered=self.image(d);expanded=self.edit(d,dict(op='appearance_expand',id='icon'))
        self.assertEqual(self.image(expanded),rendered);self.assertEqual(expanded['items'][0]['content']['type'],'group');self.assertEqual(expanded['items'][1]['content']['type'],'vector')
        spec=copy.deepcopy(d['items'][0]['content']['appearance']);spec['passes'][0]['maps'].reverse();reversed=self.edit(d,dict(op='appearance',id='icon',appearance=spec))
        self.assertNotEqual(self.image(reversed),rendered)
        svg=self.invoke(dict(command='document.export',document=d,format='svg'));self.assertIn('<path',svg['data'])

    def test_raster_filter_order_and_baking_preserve_pixels_and_source(self):
        d=original();spec=d['items'][0]['content']['appearance'];spec['passes']=[dict(id='filtered',fill=[120,80,230,255],filters=[dict(id='move',operator=dict(type='spatial',operator=dict(type='offset',offset=[1,0]))),dict(id='blocks',operator=dict(type='spatial',operator=dict(type='mosaic',size=4)))])]
        d=self.valid(d);before=copy.deepcopy(d);a=self.image(d)
        expected=[]
        for y in range(20):
            for x in range(24):
                bx=x//4*4;by=y//4*4
                count=sum(9<=xx<17 and 6<=yy<12 for yy in range(by,by+4) for xx in range(bx,bx+4))
                expected.extend([120,80,230,int(F(count,16)*255+F(1,2))] if count else [0]*4)
        self.assertEqual(a,bytes(expected))
        spec=copy.deepcopy(d['items'][0]['content']['appearance']);spec['passes'][0]['filters'].reverse();other=self.edit(d,dict(op='appearance',id='icon',appearance=spec));self.assertNotEqual(self.image(other),a)
        self.assertEqual(self.invoke(dict(command='document.export',document=d,format='svg'),1)['code'],'UNSUPPORTED')
        baked=self.edit(d,dict(op='appearance_bake',id='icon',asset_id='pixels',image_id='image',region=dict(origin=[0,0],width=24,height=20,scale=1)))
        self.assertEqual(self.image(baked),a);self.assertEqual(baked['items'][1]['content']['type'],'image')
        self.assertIn('<image',self.invoke(dict(command='document.export',document=baked,format='svg'))['data'])
        self.assertEqual(self.image(self.edit(d,dict(op='appearance_expand',id='icon'))),a);self.assertEqual(d,before)

    def test_per_pass_effects_outer_opacity_and_clipping_survive_expansion(self):
        d=original();s=d['items'][0]['content']['appearance'];s['passes'][1]['effects']=[dict(id='tint',operator=dict(type='overlay'),color=[0,255,0,128]),dict(id='shadow',operator=dict(type='shadow',offset=[2,1],sigma=0),color=[0,0,0,180])]
        d['items'][0].update(opacity=.5,clip=dict(geometry=dict(shape='rect',x=6,y=4,width=12,height=10)))
        d=self.valid(d);self.assertEqual(self.image(d),self.image(self.edit(d,dict(op='appearance_expand',id='icon'))))
        self.assertEqual(self.image(d),self.image(self.edit(d,dict(op='appearance_bake',id='icon',asset_id='pixels',image_id='image',region=dict(origin=[0,0],width=24,height=20,scale=1)))))
        self.assertLessEqual(max(self.image(d)[3::4]),128)

    def test_shared_geometry_edit_controls_all_passes_and_independent_duplicate(self):
        d=self.valid(original());spec=copy.deepcopy(d['items'][0]['content']['appearance']);spec['geometry']['width']=4
        changed=self.edit(d,dict(op='appearance',id='icon',appearance=spec));self.assertNotEqual(self.image(d),self.image(changed))
        expanded=self.edit(changed,dict(op='appearance_expand',id='icon'));self.assertEqual(self.image(changed),self.image(expanded))
        self.assertEqual(d['items'][0]['content']['appearance']['geometry']['width'],8)
        copied=copy.deepcopy(d);copied['items'].append(dict(copied['items'][0],id='other',transform=[1,0,0,1,-5,-5]));copied=self.valid(copied)
        edited=self.edit(copied,dict(op='appearance',id='other',appearance=spec));self.assertEqual(edited['items'][0],copied['items'][0])

    def test_named_paints_locks_and_inactive_pass_validation(self):
        d=original();d['swatches']={'shared':dict(name='Shared',definition=dict(type='process',color=dict(space='srgb',components=[1,0,0])))}
        spec=d['items'][0]['content']['appearance'];spec['passes'][1]['fill']=dict(swatch='shared');spec['passes'][0]['stroke']['color']=dict(swatch='shared');d=self.valid(d)
        before=self.image(d);changed=self.edit(d,dict(op='swatch',id='shared',swatch=dict(name='Shared',definition=dict(type='process',color=dict(space='srgb',components=[0,0,1])))))
        self.assertNotEqual(self.image(changed),before)
        locked=self.edit(d,dict(op='properties',id='icon',locked=True));self.assertEqual(self.edit(locked,dict(op='appearance_expand',id='icon'),expected=1)['code'],'LOCKED')
        self.assertEqual(self.edit(locked,dict(op='swatch',id='shared',swatch=None),expected=1)['code'],'LOCKED')
        bad=copy.deepcopy(d);bad['items'][0]['content']['appearance']['passes'][0].update(enabled=False,opacity=2);self.invoke(dict(command='document.validate',document=bad),1)

    def test_resource_limits_unknown_fields_and_atomic_failed_bake(self):
        d=self.valid(original());s=copy.deepcopy(d['items'][0]['content']['appearance']);s['passes']=[dict(id=f'f{i}',fill=[0,0,0,255]) for i in range(17)]
        self.assertEqual(self.edit(d,dict(op='appearance',id='icon',appearance=s),expected=1)['code'],'RESOURCE_LIMIT')
        bad=copy.deepcopy(d);bad['items'][0]['content']['appearance']['passes'][0]['extra']=True;self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],'INVALID_REQUEST')
        for region in [dict(origin=[0,0],width=257,height=256,scale=1),dict(origin=[0,0],width=24,height=20,scale=0)]:
            self.assertEqual(self.edit(d,dict(op='appearance_bake',id='icon',asset_id='pixels',image_id='image',region=region),expected=1)['code'],'RESOURCE_LIMIT')
        self.assertNotIn('pixels',d.get('assets',{}));self.assertEqual(self.image(d),opaque_reference())

    def test_mcp_history_reordering_expansion_bake_retry_and_source_snapshots(self):
        d=self.valid(original());client=Client();self.addCleanup(client.close);client.initialize()
        with tempfile.TemporaryDirectory() as root:
            session=dict(session_root=root,session_id='appearance');client.success('session.create',**session,request_id='create',document=d)
            s=copy.deepcopy(d['items'][0]['content']['appearance']);s['passes'].reverse();action=dict(type='edit',operations=[dict(op='appearance',id='icon',appearance=s)])
            edited=client.success('session.apply',**session,request_id='reorder',expected_revision=0,action=action)['document'];self.assertEqual(self.image(edited),opaque_reference(True))
            expanded=client.success('session.apply',**session,request_id='expand',expected_revision=1,action=dict(type='edit',operations=[dict(op='appearance_expand',id='icon')]))['document'];self.assertEqual(self.image(expanded),self.image(edited))
            undone=client.success('session.apply',**session,request_id='undo',expected_revision=2,action=dict(type='undo'))['document'];self.assertEqual(undone['items'],edited['items'])
            self.assertTrue(client.success('session.apply',**session,request_id='reorder',expected_revision=0,action=action)['replayed']);self.assertTrue(client.success('session.verify',**session)['valid'])
            baked=client.success('session.apply',**session,request_id='bake',expected_revision=3,action=dict(type='edit',operations=[dict(op='appearance_bake',id='icon',asset_id='pixels',image_id='image',region=dict(origin=[0,0],width=24,height=20,scale=1))]))['document'];self.assertEqual(self.image(baked),opaque_reference(True))
            self.assertEqual(client.success('appearance.inspect',document=d,id='icon')['source'],d['items'][0]['content']['appearance']['geometry'])
            self.assertEqual(client.tool('session.apply',**session,request_id='cancelled',expected_revision=4,action=dict(type='undo'),control=dict(timeout_ms=0))['structuredContent']['error']['code'],'TIMEOUT')


    def test_components_artboards_masks_and_native_page_output(self):
        base=self.valid(original());expected=self.image(base)
        d=original();d['items'][0]['parent']='definition';d['items'].insert(0,dict(id='definition',content=dict(type='component_source')))
        d['items'].append(dict(id='instance',content=dict(type='instance',instance=dict(source='definition'))));d=self.valid(d)
        self.assertEqual(self.image(d),expected)
        d=original();d['items'][0]['parent']='board';d['items'].insert(0,dict(id='board',transform=[1,0,0,1,2,3],content=dict(type='frame',frame=dict(role='artboard',width=24,height=20))));d['width']=32;d['height']=28;d=self.valid(d)
        a=self.invoke(dict(command='artboard.export',document=d,format='png'))['artifacts'][0]['artifact'];self.assertEqual(editing.png_pixels(base64.b64decode(a['data']))[2],expected)
        pdf=self.invoke(dict(command='document.export',document=base,format='pdf'));self.assertEqual(pdf['media_type'],'application/pdf')
        masked=original();masked['items'][0]['parent']='mask';masked['items'].insert(0,dict(id='mask',content=dict(type='mask_source')))
        masked['items'].append(dict(id='paint',content=dict(type='vector',geometry=dict(shape='rect',x=0,y=0,width=24,height=20),fill=[10,20,30,255]),artwork_mask=dict(source='mask',region=[0,0,24,20],mode='alpha')))
        masked=self.valid(masked);pixels=self.image(masked);self.assertEqual(pixels[3::4],expected[3::4])

    def test_transfer_keeps_pass_lighting_and_resource_identity(self):
        source=original();source['global_light']=dict(azimuth=90)
        source['items'][0]['content']['appearance']['passes'][1]['effects']=[dict(id='shadow',operator=dict(type='lit_shadow',distance=2,sigma=0),color=[0,0,0,255])]
        source=self.valid(source);destination=self.invoke(dict(command='document.create',id='destination',kind='vector',width=24,height=20))
        destination['global_light']=dict(azimuth=180)
        out=self.edit(destination,dict(op='transfer',transfer=dict(source=source,ids=['icon'],prefix='copied')))
        self.assertEqual(self.image(out),self.image(source));self.assertEqual(source['global_light']['azimuth'],90)
        self.assertEqual(out['items'][0]['content']['appearance']['passes'][1]['effects'][0]['operator']['azimuth'],90)


    def test_bake_freezes_document_scaled_strokes_and_transformed_placement(self):
        d=original();d['width']=48;d['height']=40;d['items'][0]['transform']=[2,0,0,1.5,1,2]
        for p in d['items'][0]['content']['appearance']['passes']:
            if p.get('stroke'):p['stroke']['scaling']='document'
        d=self.valid(d);expected=self.image(d)
        baked=self.edit(d,dict(op='appearance_bake',id='icon',asset_id='pixels',image_id='image',region=dict(origin=[0,0],width=48,height=40,scale=1)))
        self.assertEqual(self.image(baked),expected)
        region=dict(origin=[-2,-2],width=52,height=44,scale=2)
        high=self.edit(d,dict(op='appearance_bake',id='icon',asset_id='pixels',image_id='image',region=region))
        self.assertEqual(self.image(high,scale=2),self.image(d,scale=2))

    def test_combined_fill_stroke_passes_disabled_paints_and_local_filter_masks(self):
        d=original();spec=d['items'][0]['content']['appearance'];spec['passes']=[
            dict(id='both',fill=[30,100,220,255],stroke=dict(color=[240,50,20,255],width=2,join='miter')),
            dict(id='disabled',fill=[0,255,0,255],enabled=False)]
        d=self.valid(d);expected=[]
        for y in range(20):
            for x in range(24):
                stroke=7<=x<17 and 5<=y<13 and not(9<=x<15 and 7<=y<11)
                fill=8<=x<16 and 6<=y<12
                expected.extend([240,50,20,255] if stroke else [30,100,220,255] if fill else [0]*4)
        self.assertEqual(self.image(d),bytes(expected))
        masked=copy.deepcopy(d);p=masked['items'][0]['content']['appearance']['passes'][0]
        p['filters']=[dict(id='blur',operator=dict(type='box',radius=1),mask=dict(width=24,height=20,gray_hex='00'*480,linked=True))]
        self.assertEqual(self.image(self.valid(masked)),bytes(expected))
        p['filters'][0]['mask']['linked']=False
        self.assertEqual(self.invoke(dict(command='document.validate',document=masked),1)['code'],'UNSUPPORTED')
        self.assertEqual(self.image(d),bytes(expected))

    def test_aggregate_expansion_limit_and_failed_batch_leave_session_source_intact(self):
        d=original();d['items']=[dict(d['items'][0],id=f'icon-{i}') for i in range(52)]
        self.assertEqual(self.invoke(dict(command='document.validate',document=d),1)['code'],'RESOURCE_LIMIT')
        source=self.valid(original());client=Client();self.addCleanup(client.close);client.initialize()
        with tempfile.TemporaryDirectory() as root:
            session=dict(session_root=root,session_id='atomic')
            client.success('session.create',**session,request_id='create',document=source)
            changed=copy.deepcopy(source['items'][0]['content']['appearance']);changed['passes'].reverse()
            failed=client.tool('session.apply',**session,request_id='bad-bake',expected_revision=0,action=dict(type='edit',operations=[
                dict(op='appearance',id='icon',appearance=changed),
                dict(op='appearance_bake',id='icon',asset_id='pixels',image_id='icon',region=dict(origin=[0,0],width=24,height=20,scale=1))]))
            self.assertEqual(failed['structuredContent']['error']['code'],'INVALID_APPEARANCE')
            unchanged=client.success('session.read',**session)['document']
            self.assertEqual(unchanged,source);self.assertTrue(client.success('session.verify',**session)['valid'])


if __name__=='__main__':unittest.main()
