"""Original rational background, retained source, lock and history fixtures."""
import base64
import copy
from fractions import Fraction as F
import json
import tempfile
import unittest
import test_editing_cli as editing
import test_layer_clipping_cli as clipping
import test_effects_coverage_cli as effects
import test_blending_cli as blending
import test_artwork_masks_cli as artwork
from test_mcp import Client
from pdf_reader import Pdf

layer=clipping.layer
group=clipping.group


class BackgroundTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    document=clipping.LayerClippingTests.document
    edit=clipping.LayerClippingTests.edit
    add=clipping.LayerClippingTests.add
    pixels=clipping.LayerClippingTests.pixels
    assert_pixels=clipping.LayerClippingTests.assert_pixels

    def convert(self,d,type='promote',id='base',expected=0,**kw):
        if type=='promote':kw.setdefault('matte',[30,80,150])
        return self.edit(d,[dict(op='background',id=id,action=dict(type=type,**kw))],expected)

    def fixture(self,**kw):
        colors=[[220,50,10,a] for a in [0,1,64,128,192,254,255]]
        return self.add(self.document(9,2),[layer('base',colors,**kw)]),colors

    def test_promote_opaque_canvas_preserves_every_source_byte_and_restores_alpha(self):
        d,colors=self.fixture();before=copy.deepcopy(d);matte=[30,80,150]
        bg=self.convert(d)
        self.assertEqual(bg['items'],d['items']);self.assertEqual(d,before)
        self.assertEqual(bg['background'],dict(item_id='base',matte=matte))
        expected=[clipping.over(clipping.premul(matte+[255]),clipping.premul(p)) for p in colors]
        expected += [clipping.premul(matte+[255])]*(18-len(colors))
        self.assert_pixels(self.pixels(bg),expected)
        restored=self.convert(bg,'restore_source')
        self.assertNotIn('background',restored);self.assertEqual(restored['items'],d['items'])
        self.assertEqual(self.pixels(restored),self.pixels(d))

    def test_source_opacity_mask_fill_and_blend_precede_matte(self):
        for mode in ['normal','multiply','screen']:
            d,colors=self.fixture(opacity=.5,fill_opacity=.75,blend=mode,mask=clipping.mask([0,64,128,192,255,255,255]))
            bg=self.convert(d);expected=[]
            for p,m in zip(colors,[0,64,128,192,255,255,255]):
                expected.append(clipping.over(clipping.premul([30,80,150,255]),clipping.premul(p),F(1,2)*F(3,4)*F(m,255),mode))
            expected += [clipping.premul([30,80,150,255])]*(18-len(colors))
            self.assert_pixels(self.pixels(bg),expected)
            flat=self.convert(bg,'to_layer',source_id='retained',matte_id='paper')
            self.assertEqual(self.pixels(flat),self.pixels(bg))

    def test_zero_opacity_retains_matte_visibility_suppresses_whole_background(self):
        d,_=self.fixture(opacity=0);bg=self.convert(d)
        self.assertEqual(self.pixels(bg),bytes([30,80,150,255])*18)
        hidden=self.edit(bg,[dict(op='properties',id='base',visible=False)])
        self.assertEqual(self.pixels(hidden),bytes(18*4))
        ordinary=self.convert(hidden,'to_layer',source_id='source',matte_id='paper')
        self.assertFalse(ordinary['items'][0]['visible']);self.assertTrue(ordinary['items'][2]['visible'])
        self.assertEqual(self.pixels(ordinary),bytes(18*4))
        shown=self.edit(ordinary,[dict(op='properties',id='base',visible=True)])
        self.assertEqual(self.pixels(shown),self.pixels(bg))

    def test_all_blend_modes_match_independent_color_algebra_and_ordinary_conversion(self):
        colors=[[s,255-s,(s*7)%256,a] for s in [0,1,63,128,191,254,255] for a in [0,1,64,128,255]]
        for mode in blending.MODES:
            d=self.add(self.document(len(colors),1),[layer('base',colors,blend=mode,opacity=.75)])
            bg=self.convert(d)
            expected=[blending.over(blending.premul([30,80,150,255]),blending.premul(p),F(3,4),mode) for p in colors]
            blending.BlendingTests.matches(self,self.pixels(bg),expected)
            ordinary=self.convert(bg,'to_layer',source_id='retained',matte_id='paper')
            self.assertEqual(self.pixels(ordinary),self.pixels(bg),mode)

    def test_shared_artwork_mask_evaluation_excludes_matte_and_keeps_source_coordinates(self):
        d=self.add(self.document(4,2),[artwork.source(),artwork.rect('window',w=2,h=1,parent='source'),
            layer('base',[[210,30,90,255]]*8,width=4,artwork_mask=dict(source='source',region=[0,0,4,2]))])
        bg=self.convert(d);expected=bytes([210,30,90,255])*2+bytes([30,80,150,255])*6
        self.assertEqual(self.pixels(bg),expected)
        ordinary=self.convert(bg,'to_layer',source_id='retained',matte_id='paper')
        self.assertEqual(self.pixels(ordinary),expected)
        restored=self.convert(bg,'restore_source');self.assertEqual(self.pixels(restored),bytes([210,30,90,255])*2+bytes(24))

    def test_cross_document_transfer_copies_source_without_foreign_background_role(self):
        d,_=self.fixture();bg=self.convert(d);original=copy.deepcopy(bg)
        transferred=self.edit(self.document(9,2),[dict(op='transfer',transfer=dict(source=bg,ids=['base'],prefix='copied'))])
        self.assertNotIn('background',transferred);self.assertEqual(self.pixels(transferred),self.pixels(d))
        self.assertEqual(bg,original)

    def test_conversion_item_and_render_budgets_reject_before_output(self):
        d,_=self.fixture();bg=self.convert(d)
        crowded=copy.deepcopy(bg)
        crowded['items'] += [group('g'+str(i)) for i in range(254)]
        self.assertEqual(self.convert(crowded,'to_layer',source_id='retained',matte_id='paper',expected=1)['code'],'RESOURCE_LIMIT')
        oversized=copy.deepcopy(bg);oversized.update(width=32768,height=32768)
        self.assertEqual(self.invoke(dict(command='document.render',document=oversized),1)['code'],'RESOURCE_LIMIT')

    def test_capability_and_schema_discovery_describe_background_actions(self):
        c=self.invoke(dict(command='capabilities'))
        self.assertEqual(c['backgrounds']['actions'],['promote','restore_source','to_layer'])
        self.assertIn('retained_opaque_backgrounds',c['supported']['raster'])
        schema=json.dumps(self.invoke(dict(command='schema')))
        for name in ['Background','matte_id','restore_source']:
            self.assertIn(name,schema)

    def test_clipped_layers_and_bound_adjustments_use_completed_opaque_base(self):
        d=self.add(self.document(4,1),[layer('base',[[120,30,80,0],[120,30,80,128]]),
            dict(id='invert',content=dict(type='adjustment',adjustment=dict(operators=[dict(type='invert')],clip_to='base'))),
            layer('texture',[[80,140,210,128]]*4,clip_to='base',opacity=.5)])
        bg=self.convert(d);expected=[]
        for x in range(4):
            p=clipping.over(clipping.premul([30,80,150,255]),clipping.premul([120,30,80,128 if x==1 else 0]))
            p=[1-c for c in p[:3]]+[F(1)]
            expected.append(clipping.atop(p,clipping.premul([80,140,210,128]),F(1,2)))
        self.assert_pixels(self.pixels(bg),expected)
        ordinary=self.convert(bg,'to_layer',source_id='retained',matte_id='paper')
        self.assertEqual(self.pixels(ordinary),self.pixels(bg))
        self.assertEqual(next(i for i in ordinary['items'] if i['id']=='texture')['clip_to'],'base')
        self.assertEqual(next(i for i in ordinary['items'] if i['id']=='invert')['content']['adjustment']['clip_to'],'base')

    def test_effects_decorate_retained_source_before_background_and_conversion(self):
        colors=[[210,30,70,0],[210,30,70,128],[210,30,70,255],[210,30,70,0]]
        styles=[effects.effect('outline','stroke',[20,160,90,200],radius=1,position='outside'),effects.effect('tint','overlay',[60,110,230,120])]
        d=self.add(self.document(4,1),[layer('base',colors,effects=styles,fill_opacity=.5,opacity=.75)])
        bg=self.convert(d)
        decorated=effects.decorated([clipping.premul(p) for p in colors],4,1,styles,F(1,2))
        expected=[clipping.over(clipping.premul([30,80,150,255]),p,F(3,4)) for p in decorated]
        self.assert_pixels(self.pixels(bg),expected)
        self.assertEqual(self.pixels(self.convert(bg,'to_layer',source_id='retained',matte_id='paper')),self.pixels(bg))

    def test_nested_group_conversion_keeps_transforms_descendants_and_clipping(self):
        items=[group('base',transform=[1,0,0,1,2,1],opacity=.5),
            group('inner',parent='base',transform=[0,1,-1,0,2,0]),
            layer('a',[[80,120,200,255],[80,120,200,0]],parent='inner'),
            layer('b',[[210,40,90,128]]*2,parent='inner',clip_to='a')]
        d=self.add(self.document(6,4),items);bg=self.convert(d)
        ordinary=self.convert(bg,'to_layer',source_id='retained',matte_id='paper')
        self.assertEqual(self.pixels(ordinary),self.pixels(bg));self.assertNotIn('background',ordinary)
        byid={i['id']:i for i in ordinary['items']}
        self.assertEqual(byid['inner']['parent'],'retained');self.assertEqual(byid['a']['parent'],'inner')
        self.assertEqual(byid['b']['clip_to'],'a');self.assertEqual(byid['retained']['transform'],items[0]['transform'])
        self.assertEqual(byid['base']['transform'],[1,0,0,1,0,0])
        self.assertEqual(byid['paper']['content']['paint'],[30,80,150,255])
        wanted=[clipping.premul([30,80,150,255]) for _ in range(24)]
        content=clipping.atop(clipping.premul([80,120,200,255]),clipping.premul([210,40,90,128]))
        wanted[1*6+3]=clipping.over(wanted[9],content,F(1,2))
        self.assert_pixels(self.pixels(bg),wanted)

    def test_duplicate_edits_preserve_original_pixels_controls_role_and_names(self):
        d,_=self.fixture(name='same',transform=[1,0,0,1,1,0]);bg=self.convert(d);original=copy.deepcopy(bg['items'][0])
        duplicated=self.edit(bg,[dict(op='duplicate',id='base',new_id='copy')])
        changed=self.edit(duplicated,[dict(op='pixel_fill',id='copy',rect=dict(x=0,y=0,width=2,height=1),color=[10,240,90,255])])
        self.assertEqual(changed['items'][0],original);self.assertEqual(changed['background'],bg['background'])
        clone=next(i for i in changed['items'] if i['id']=='copy')
        self.assertEqual(clone['name'],'same');self.assertNotEqual(clone['content']['rgba_hex'],original['content']['rgba_hex'])
        removed=self.edit(changed,[dict(op='remove',id='copy')]);self.assertEqual(self.pixels(removed),self.pixels(bg))
        self.assertEqual(removed['items'],bg['items'])

    def test_locks_prevent_removal_conversion_source_edits_and_locked_descendants(self):
        d,_=self.fixture();bg=self.convert(d);locked=self.edit(bg,[dict(op='properties',id='base',locked=True)])
        for op in [dict(op='remove',id='base'),dict(op='background',id='base',action=dict(type='restore_source')),
            dict(op='background',id='base',action=dict(type='to_layer',source_id='s',matte_id='m')),
            dict(op='pixel_fill',id='base',rect=dict(x=0,y=0,width=1,height=1),color=[1,2,3,4]),
            dict(op='transform',id='base',matrix=[1,0,0,1,2,3])]:
            self.assertEqual(self.edit(locked,[op],1)['code'],'LOCKED')
        duplicated=self.edit(locked,[dict(op='duplicate',id='base',new_id='copy')])
        self.assertTrue(next(i for i in duplicated['items'] if i['id']=='copy')['locked'])
        unlocked=self.edit(duplicated,[dict(op='properties',id='copy',locked=False),dict(op='remove',id='copy')])
        self.assertEqual(unlocked['items'],locked['items'])
        nested=self.add(self.document(),[group('base'),layer('child',[[1,2,3,4]],parent='base',locked=True)])
        self.assertEqual(self.convert(nested,expected=1)['code'],'LOCKED')
        self.assertEqual(self.edit(nested,[dict(op='remove',id='base')],1)['code'],'LOCKED')

    def test_remove_background_clears_role_and_subtree_with_atomic_reference_errors(self):
        d=self.add(self.document(3,1),[group('base'),layer('child',[[10,20,30,255]],parent='base'),layer('top',[[90,80,70,255]])])
        bg=self.convert(d);removed=self.edit(bg,[dict(op='remove',id='base')])
        self.assertNotIn('background',removed);self.assertEqual([i['id'] for i in removed['items']],['top'])
        self.assertEqual(self.pixels(removed),bytes([90,80,70,255])+bytes(8))
        clipped=self.edit(bg,[dict(op='layer_clip',id='top',clip_to='base')])
        self.assertEqual(self.edit(clipped,[dict(op='remove',id='base')],1)['code'],'INVALID_DOCUMENT')
        removed=self.edit(clipped,[dict(op='remove',id='top'),dict(op='remove',id='base')])
        self.assertEqual(removed['items'],[]);self.assertNotIn('background',removed)

    def test_promote_reorders_and_replaces_only_explicit_role_with_lock_checks(self):
        d=self.add(self.document(2,1),[layer('other',[[10,20,30,255]]),layer('base',[[240,80,20,255]])])
        bg=self.convert(d);self.assertEqual([i['id'] for i in bg['items']],['base','other'])
        self.assertEqual(self.pixels(bg),bytes([10,20,30,255,30,80,150,255]))
        replaced=self.convert(bg,id='other',matte=[1,2,3]);self.assertEqual(replaced['background']['item_id'],'other')
        self.assertEqual(replaced['items'],d['items'])
        locked=self.edit(bg,[dict(op='properties',id='base',locked=True)])
        self.assertEqual(self.convert(locked,id='other',expected=1)['code'],'LOCKED')

    def test_current_canvas_matte_follows_crop_extent_scale_and_ordinary_matte_freezes(self):
        d=self.add(self.document(2,1),[layer('base',[[250,20,30,255]])]);bg=self.convert(d)
        large=self.edit(bg,[dict(op='canvas',action=dict(type='extent',width=4,height=3,anchor='top_left'))])
        self.assertEqual(self.pixels(large),bytes([250,20,30,255])+bytes([30,80,150,255])*11)
        cropped=self.edit(bg,[dict(op='canvas',action=dict(type='crop',x=5,y=5,width=3,height=2))])
        self.assertEqual(self.pixels(cropped),bytes([30,80,150,255])*6)
        scaled=self.edit(bg,[dict(op='canvas',action=dict(type='scale',width=4,height=2,sampling='nearest'))])
        self.assertEqual(self.pixels(scaled),bytes([250,20,30,255])*2+bytes([30,80,150,255])*2+bytes([250,20,30,255])*2+bytes([30,80,150,255])*2)
        ordinary=self.convert(bg,'to_layer',source_id='retained',matte_id='paper')
        extended=self.edit(ordinary,[dict(op='canvas',action=dict(type='extent',width=4,height=1,anchor='top_left'))])
        self.assertEqual(self.pixels(extended),self.pixels(bg)+bytes(8))

    def test_snapshot_inspection_diff_and_pdf_matte_are_explicit(self):
        d,_=self.fixture();bg=self.convert(d)
        artifact=self.invoke(dict(command='document.export',document=bg,format='snapshot'))
        self.assertEqual(self.invoke(dict(command='document.validate',document=json.loads(artifact['data']))),bg)
        info=self.invoke(dict(command='document.inspect',document=bg))['background']
        self.assertEqual(info['canvas_bounds'],[0,0,9,2]);self.assertEqual(info['source_alpha'],'retained');self.assertFalse(info['implicit_lock'])
        pdf=Pdf(self.invoke(dict(command='document.export',document=bg,format='pdf')))
        self.assertEqual(pdf.paths()[0]['color'],[30/255,80/255,150/255])
        self.assertEqual(pdf.paths()[0]['path'][0],('m',[[0,0]]))
        self.assertTrue(any(o.get('Subtype')=='Image' for o in pdf.objects.values()))
        hidden=self.edit(bg,[dict(op='properties',id='base',visible=False)])
        self.assertEqual(Pdf(self.invoke(dict(command='document.export',document=hidden,format='pdf'))).paths(),[])

    def test_artboard_export_excludes_foreign_background_and_retains_owned_background(self):
        board=dict(id='board',content=dict(type='frame',frame=dict(role='artboard',width=3,height=2)))
        d=self.add(self.document(5,3),[layer('base',[[250,20,30,255]]),board])
        bg=self.convert(d)
        artifact=self.invoke(dict(command='artboard.export',document=bg,format='png'))['artifacts'][0]['artifact']
        self.assertEqual(editing.png_pixels(base64.b64decode(artifact['data']))[2],bytes(24))
        owned=self.convert(bg,id='board')
        artifact=self.invoke(dict(command='artboard.export',document=owned,format='png'))['artifacts'][0]['artifact']
        self.assertEqual(editing.png_pixels(base64.b64decode(artifact['data']))[2],bytes([30,80,150,255])*6)

    def test_invalid_background_contexts_and_order_fail_without_partial_edits(self):
        d,_=self.fixture();bg=self.convert(d);before=copy.deepcopy(bg)
        for op in [dict(op='background',id='base',action=dict(type='to_layer',source_id='base',matte_id='m')),
            dict(op='add',index=0,item=layer('below',[[1,2,3,255]])),
            dict(op='group',ids=['base'],new_id='wrapper')]:
            error=self.edit(bg,[dict(op='properties',id='base',name='pending'),op],1)
            self.assertEqual(error['operation_index'],1)
        self.assertEqual(bg,before)
        invalid=copy.deepcopy(bg);invalid['background']['item_id']='missing'
        self.assertEqual(self.invoke(dict(command='document.validate',document=invalid),1)['code'],'INVALID_DOCUMENT')
        invalid=copy.deepcopy(bg);invalid['background']['matte']=[1,2,300]
        self.assertEqual(self.invoke(dict(command='document.validate',document=invalid),1)['code'],'INVALID_REQUEST')
        nested=self.add(self.document(),[group('parent'),layer('base',[[1,2,3,4]],parent='parent')])
        self.assertEqual(self.convert(nested,expected=1)['code'],'INVALID_OPERATION')
        passthrough=self.add(self.document(),[dict(id='base',content=dict(type='group',isolated=False))])
        self.assertEqual(self.convert(passthrough,expected=1)['code'],'INVALID_OPERATION')
        vector=self.add(self.document(kind='vector'),[group('base')])
        self.assertEqual(self.convert(vector,expected=1)['code'],'INVALID_OPERATION')

    def test_mcp_history_retry_restart_and_background_diff(self):
        c=Client();self.addCleanup(c.close);c.initialize();d,_=self.fixture()
        with tempfile.TemporaryDirectory() as root:
            args=dict(session_root=root,session_id='background')
            c.success('session.create',**args,request_id='create',document=d)
            action=dict(type='edit',operations=[dict(op='background',id='base',action=dict(type='promote',matte=[30,80,150]))])
            bg=c.success('session.apply',**args,request_id='promote',expected_revision=0,action=action)['document']
            changed=c.success('session.diff',**args,from_revision=0,to_revision=1,compare_pixels=True)
            self.assertIn('background',[m['field'] for m in changed['metadata']])
            self.assertEqual(changed['rendered_pixels']['changed_pixels'],17)
            ordinary=c.success('session.apply',**args,request_id='ordinary',expected_revision=1,action=dict(type='edit',operations=[dict(op='background',id='base',action=dict(type='to_layer',source_id='retained',matte_id='paper'))]))['document']
            self.assertEqual(self.pixels(ordinary),self.pixels(bg))
            undo=c.success('session.apply',**args,request_id='undo',expected_revision=2,action=dict(type='undo'))['document']
            self.assertEqual(undo,dict(bg,revision=3))
            redo=c.success('session.apply',**args,request_id='redo',expected_revision=3,action=dict(type='redo'))['document']
            self.assertEqual(redo,dict(ordinary,revision=4))
            replay=c.success('session.apply',**args,request_id='promote',expected_revision=0,action=action)
            self.assertEqual(replay['document'],bg);self.assertEqual(replay['current_revision'],4)
            self.assertEqual(self.invoke(dict(command='session.read',**args))['document'],redo)
            c.success('session.verify',**args)


if __name__=='__main__':unittest.main()
