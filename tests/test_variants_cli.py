"""Original dataset fixtures: independent samples, property ownership and durable history."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import test_editing_cli as editing
from test_images_cli import png
from test_mcp import Client
from synthetic_font import geometric_font


def value(type,value):return dict(type=type,value=value)
def binding(key,item,property):return dict(key=key,item_id=item,property=property)
def byid(d,id):return next(i for i in d['items'] if i['id']==id)


class VariantTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke

    def edit(self,d,*ops,expected=0,**resources):
        r=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=list(ops),**resources),expected)
        return r if expected else r['document']

    def document(self,kind='raster'):
        d=self.invoke(dict(command='document.create',id='variant-fixture',kind=kind,width=24,height=12))
        def item(id,color,transform):
            content=dict(type='vector',geometry=dict(shape='rect',x=0,y=0,width=4,height=4),fill=color) if kind=='vector' else dict(type='raster',width=4,height=4,rgba_hex=bytes(color).hex()*16)
            return dict(id=id,name=id,transform=transform,content=content)
        return self.edit(d,dict(op='add',item=item('tile',[200,40,20,255],[1,0,0,1,2,2])),dict(op='add',item=item('badge',[20,100,230,255],[1,0,0,1,12,2])))

    def definition(self):
        return dict(bindings=[binding('place','tile','position'),binding('show','badge','visible')],datasets=dict(
            moved=dict(values=dict(place=value('position',[6,4]))),
            child=dict(parent='moved',values=dict(show=value('visible',False))),
            alternate=dict(values=dict(place=value('position',[16,7])))))

    def define(self,d,definition=None):return self.edit(d,dict(op='variants_set',definition=definition or self.definition()))
    def select(self,d,name):return self.edit(d,dict(op='variant_select',dataset=name))
    def pixels(self,d,scale=1,**resources):
        p=self.invoke(dict(command='document.export',document=d,format='png',scale=scale,**resources))
        return editing.png_pixels(base64.b64decode(p['data']))[:3]

    def check_grid(self,d,x,y,show,scale=1):
        w,h,p=self.pixels(d,scale)
        expected=bytearray()
        for row in range(h):
            for col in range(w):
                xx,yy=(col+.5)/scale,(row+.5)/scale;color=[0]*4
                if x<=xx<x+4 and y<=yy<y+4:color=[200,40,20,255]
                if show and 12<=xx<16 and 2<=yy<6:color=[20,100,230,255]
                expected.extend(color)
        self.assertEqual(p,bytes(expected))

    def test_raster_visibility_position_mapping_and_every_pixel(self):
        original=self.document();saved=copy.deepcopy(original);d=self.define(original)
        for name,x,y,show in [(None,2,2,True),('moved',6,4,True),('child',6,4,False),('alternate',16,7,True),(None,2,2,True)]:
            d=self.select(d,name);self.check_grid(d,x,y,show,2)
            state=self.invoke(dict(command='document.inspect',document=d))['variants'];self.assertEqual(state['selected'],name)
        self.assertEqual(d['items'],original['items']);self.assertEqual(original,saved)

    def test_vector_visibility_positions_and_original_geometry_are_preserved(self):
        original=self.document('vector');d=self.define(original)
        for name,x,y,show in [('moved',6,4,True),('child',6,4,False),('alternate',16,7,True),(None,2,2,True)]:
            d=self.select(d,name);self.check_grid(d,x,y,show,3)
            for id in ('tile','badge'):self.assertEqual(byid(d,id)['content'],byid(original,id)['content'])
        self.assertEqual(d['items'],original['items'])

    def test_child_variants_override_property_subsets_without_incidental_edits(self):
        d=self.define(self.document());original=copy.deepcopy(d)
        d=self.select(d,'child');d=self.edit(d,dict(op='properties',id='tile',name='User note',opacity=.5))
        self.assertEqual(self.edit(d,dict(op='transform',id='tile',matrix=[1,0,0,1,1,1]),expected=1)['code'],'VARIANT_CONTROLLED')
        for name in ('alternate','moved',None,'child'):
            d=self.select(d,name);self.assertEqual(byid(d,'tile')['name'],'User note');self.assertEqual(byid(d,'tile')['opacity'],.5)
            self.assertEqual(byid(d,'tile')['content'],byid(original,'tile')['content'])
        self.assertEqual(d['variants']['base'],original['variants']['base'])
        # A parent update immediately changes the inherited value when reselected.
        definition=copy.deepcopy(d['variants']['definition']);definition['datasets']['moved']['values']['place']=value('position',[3,6])
        revised=self.define(d,definition);self.assertIsNone(revised['variants']['selected']);self.assertEqual(byid(revised,'tile')['transform'][4:],[2,2])
        child=self.select(revised,'child');self.assertEqual(byid(child,'tile')['transform'][4:],[3,6]);self.assertFalse(byid(child,'badge')['visible'])

    def test_full_transform_position_subsets_opacity_and_names(self):
        d=self.document();definition=dict(bindings=[binding('matrix','tile','transform'),binding('fade','tile','opacity'),binding('fill','tile','fill_opacity'),binding('label','tile','name')],datasets=dict(reflect=dict(values=dict(matrix=value('transform',[-1,0,0,1,9,3]),fade=value('opacity',.5),fill=value('fill_opacity',.5),label=value('name','Repeated label')))))
        current=self.select(self.define(d,definition),'reflect');w,h,p=self.pixels(current)
        self.assertEqual(byid(current,'tile')['transform'],[-1,0,0,1,9,3]);self.assertEqual(byid(current,'tile')['name'],'Repeated label')
        for y in range(3,7):
            for x in range(5,9):self.assertEqual(p[(y*w+x)*4:(y*w+x+1)*4],bytes([200,40,20,64]))
        self.assertEqual(self.select(current,None)['items'],d['items'])
        position=self.define(d);position=self.edit(position,dict(op='transform',id='tile',matrix=[-1,0,0,2,2,2]))
        changed=self.select(position,'moved');self.assertEqual(byid(changed,'tile')['transform'],[-1,0,0,2,6,4])

    def font(self,root):
        source=root/'original.ttf';source.write_bytes(geometric_font());license=root/'LICENSE.txt';license.write_bytes((Path(__file__).resolve().parents[1]/'LICENSE').read_bytes());store=root/'fonts'
        font=self.invoke(dict(command='font.import',source_path=str(source),license_path=str(license),store_root=str(store)))
        return font,store,source

    def test_vector_text_dataset_mapping_independent_glyph_pixels_and_exports(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);font,store,source=self.font(root);before=source.read_bytes();resources=dict(font_root=str(store))
            d=self.invoke(dict(command='document.create',id='text-variants',kind='vector',width=64,height=24))
            d=self.edit(d,dict(op='font_put',id='font',font=font),dict(op='add',item=dict(id='label',content=dict(type='text',frame=dict(text='A',width=64,height=24,style=dict(font_id='font',size=20,fill=[30,80,210,255]))))))
            definition=dict(bindings=[binding('title','label','text')],datasets=dict(short=dict(values=dict(title=value('text',dict(text='A')))),long=dict(values=dict(title=value('text',dict(text='AA')))),blank=dict(values=dict(title=value('text',dict(text=''))))))
            base=self.define(d,definition)
            for name,count in [('short',1),('long',2),('blank',0),('short',1)]:
                selected=self.select(base,name);w,h,p=self.pixels(selected,**resources)
                expected=bytes(v for y in range(h) for x in range(w) for v in ([30,80,210,255] if 2<=y<16 and any(1+12*i<=x<9+12*i for i in range(count)) else [0]*4))
                self.assertEqual(p,expected)
                self.assertEqual(byid(selected,'label')['content']['frame']['text'],'A'*count)
                for fmt in ('png','svg','snapshot'):
                    result=self.invoke(dict(command='document.export',document=selected,format=fmt,**resources));self.assertEqual(result['variant'],name);self.assertEqual(len(result['variant_state_sha256']),64)
                    if fmt=='snapshot':self.assertEqual(json.loads(result['data']),selected)
                    else:self.assertTrue(any('selected variant' in s for s in result['losses']))
                # Export each dataset under its own new name, preserving earlier results.
                path=root/(name+'.png')
                if not path.exists():self.invoke(dict(command='document.publish',document=selected,resources=resources,output=dict(output_root=str(root),file_name=name+'.png',format='png')))
                else:self.assertEqual(self.invoke(dict(command='document.publish',document=selected,resources=resources,output=dict(output_root=str(root),file_name=name+'.png',format='png')),1)['code'],'OUTPUT_EXISTS')
            self.assertEqual(source.read_bytes(),before);self.assertEqual(byid(base,'label')['content']['frame']['text'],'A')

    def test_styled_text_ranges_inactive_fonts_and_restoration(self):
        with tempfile.TemporaryDirectory() as root:
            font,store,_=self.font(Path(root));d=self.document('vector');d=self.edit(d,dict(op='font_put',id='base-font',font=font),dict(op='font_put',id='variant-font',font=font),dict(op='add',item=dict(id='label',content=dict(type='text',frame=dict(text='A',width=24,height=12,style=dict(font_id='base-font',size=10,fill=[255]*4))))))
            text=dict(text='AA',ranges=[dict(start=1,end=2,style=dict(font_id='variant-font',size=10,fill=[230,20,30,255]))])
            definition=dict(bindings=[binding('title','label','text')],datasets=dict(styled=dict(values=dict(title=value('text',text)))))
            base=self.define(d,definition);self.assertEqual(self.edit(base,dict(op='font_remove',id='variant-font'),expected=1)['code'],'FONT_IN_USE')
            locked=self.edit(base,dict(op='properties',id='label',locked=True));self.assertEqual(self.edit(locked,dict(op='font_put',id='variant-font',font=font),expected=1)['code'],'LOCKED')
            active=self.select(base,'styled');self.pixels(active,font_root=str(store));self.assertEqual(byid(active,'label')['content']['frame']['ranges'][0]['start'],1)
            self.assertEqual(self.select(active,None)['items'],d['items'])

    def images(self,root,kind):
        store=root/'assets';assets=[];sources=[]
        for n,color in enumerate(([230,30,20,255],[20,180,90,128])):
            p=root/f'original-{n}.png';p.write_bytes(png(2,2,bytes(color)*4));sources.append(p)
            assets.append(self.invoke(dict(command='asset.import',source_path=str(p),store_root=str(store)))['asset'])
        d=self.invoke(dict(command='document.create',id='image-variants',kind=kind,width=8,height=8));d=self.edit(d,*[dict(op='asset_put',id=f'image-{i}',asset=a) for i,a in enumerate(assets)],dict(op='add',item=dict(id='picture',content=dict(type='image',asset_id='image-0',width=4,height=4))))
        definition=dict(bindings=[binding('picture','picture','image')],datasets=dict(green=dict(values=dict(picture=value('image','image-1'))),red=dict(values=dict(picture=value('image','image-0')))))
        return self.define(d,definition),store,sources,assets

    def test_image_datasets_missing_assets_inactive_references_and_input_preservation(self):
        for kind in ('vector','raster'):
            with tempfile.TemporaryDirectory() as root:
                d,store,sources,assets=self.images(Path(root),kind);before=[p.read_bytes() for p in sources]
                for name,color in [('green',[20,180,90,128]),('red',[230,30,20,255])]:
                    active=self.select(d,name);w,h,p=self.pixels(active,asset_root=str(store));self.assertEqual(p,bytes(v for y in range(h) for x in range(w) for v in (color if x<4 and y<4 else [0]*4)))
                self.assertEqual(self.edit(d,dict(op='asset_remove',id='image-1'),expected=1)['code'],'ASSET_IN_USE')
                locked=self.edit(d,dict(op='properties',id='picture',locked=True));self.assertEqual(self.edit(locked,dict(op='asset_put',id='image-1',asset=assets[1]),expected=1)['code'],'LOCKED')
                broken=copy.deepcopy(d['variants']['definition']);broken['datasets']['green']['values']['picture']=value('image','missing')
                self.edit(d,dict(op='variants_set',definition=broken),expected=1)
                active=self.select(d,'green');err=self.invoke(dict(command='document.export',document=active,format='png',asset_root=str(Path(root)/'absent')),1);self.assertEqual(err['code'],'ASSET_MISSING');self.assertEqual(err['asset_id'],'image-1')
                self.assertEqual([p.read_bytes() for p in sources],before)

    def test_invalid_dataset_values_cycles_targets_and_stale_states_fail_atomically(self):
        d=self.document();definition=self.definition();saved=copy.deepcopy(d)
        cases=[]
        for change in [dict(place=value('opacity',.5)),dict(unknown=value('position',[0,0])),dict(place=value('position',[1e30,0]))]:
            bad=copy.deepcopy(definition);bad['datasets']['moved']['values']=change;cases.append(bad)
        bad=copy.deepcopy(definition);bad['datasets']['moved']['parent']='child';cases.append(bad)
        bad=copy.deepcopy(definition);bad['datasets']['moved']['parent']='missing';cases.append(bad)
        bad=copy.deepcopy(definition);bad['bindings'][0]['item_id']='missing';cases.append(bad)
        bad=copy.deepcopy(definition);bad['bindings'].append(binding('matrix','tile','transform'));cases.append(bad)
        bad=copy.deepcopy(definition);bad['bindings'].append(bad['bindings'][0]);cases.append(bad)
        for bad in cases:self.edit(d,dict(op='variants_set',definition=bad),expected=1)
        base=self.define(d);self.edit(base,dict(op='variant_select',dataset='missing'),expected=1);self.edit(base,dict(op='remove',id='tile'),expected=1)
        stale=copy.deepcopy(base);byid(stale,'tile')['transform'][4]=3;self.assertEqual(self.invoke(dict(command='document.validate',document=stale),1)['code'],'VARIANT_CONTROLLED')
        self.assertEqual(d,saved)

    def test_bounds_depth_and_nonempty_definition_limits(self):
        d=self.document();definition=self.definition()
        for count in (8,9):
            chain=copy.deepcopy(definition);chain['datasets']={f'v{i}':dict(values={},**(dict(parent=f'v{i-1}') if i else {})) for i in range(count)}
            if count==8:self.define(d,chain)
            else:self.assertEqual(self.edit(d,dict(op='variants_set',definition=chain),expected=1)['code'],'RESOURCE_LIMIT')
        for field,value_ in [('bindings',[]),('datasets',{}),('datasets',{f'v{i}':dict(values={}) for i in range(33)}),('bindings',[binding(f'k{i}','tile','position') for i in range(65)])]:
            bad=copy.deepcopy(definition);bad[field]=value_;self.assertEqual(self.edit(d,dict(op='variants_set',definition=bad),expected=1)['code'],'RESOURCE_LIMIT')

    def test_locked_targets_ancestors_and_component_dependents_are_protected(self):
        d=self.define(self.document());locked=self.edit(d,dict(op='properties',id='tile',locked=True))
        self.assertEqual(self.edit(locked,dict(op='variant_select',dataset='moved'),expected=1)['code'],'LOCKED');self.select(locked,None)
        d=self.document('vector');items=[dict(id='source',content=dict(type='component_source')),dict(byid(d,'tile'),parent='source'),dict(id='copy',locked=True,content=dict(type='instance',instance=dict(source='source')))]
        d['items']=items;definition=dict(bindings=[binding('show','tile','visible')],datasets=dict(hidden=dict(values=dict(show=value('visible',False)))))
        d=self.define(d,definition);self.assertEqual(self.edit(d,dict(op='variant_select',dataset='hidden'),expected=1)['code'],'LOCKED')
        d=self.document();d=self.edit(d,dict(op='group',ids=['tile'],new_id='group'));d=self.define(d);d=self.edit(d,dict(op='properties',id='group',locked=True))
        self.assertEqual(self.edit(d,dict(op='variant_select',dataset='moved'),expected=1)['code'],'LOCKED')

    def test_clear_restore_bake_redefine_and_unrelated_properties(self):
        original=self.document();active=self.select(self.define(original),'child');active=self.edit(active,dict(op='properties',id='tile',name='Retain this name'))
        restored=self.edit(active,dict(op='variants_clear'));self.assertNotIn('variants',restored);self.check_grid(restored,2,2,True);self.assertEqual(byid(restored,'tile')['name'],'Retain this name')
        baked=self.edit(active,dict(op='variants_clear',bake=True));self.assertNotIn('variants',baked);self.assertEqual(self.pixels(baked),self.pixels(active));self.edit(baked,dict(op='transform',id='tile',matrix=[1,0,0,1,1,1]))
        redefined=self.define(active);self.assertIsNone(redefined['variants']['selected']);self.check_grid(redefined,2,2,True)

    def test_mcp_durable_selection_undo_redo_retry_and_definition_diff(self):
        d=self.document();c=Client();self.addCleanup(c.close);c.initialize()
        with tempfile.TemporaryDirectory() as root:
            session=dict(session_root=root,session_id='variants');c.success('session.create',**session,request_id='create',document=d)
            configured=c.success('session.apply',**session,request_id='define',expected_revision=0,action=dict(type='edit',operations=[dict(op='variants_set',definition=self.definition())]))['document']
            args=dict(**session,request_id='select',expected_revision=1,action=dict(type='edit',operations=[dict(op='variant_select',dataset='child')]))
            active=c.success('session.apply',**args);self.assertTrue(c.success('session.apply',**args)['replayed']);self.check_grid(active['document'],6,4,False)
            snapshot=c.success('document.export',document=active['document'],format='snapshot');self.assertEqual(json.loads(snapshot['data']),active['document'])
            undo=c.success('session.apply',**session,request_id='undo',expected_revision=2,action=dict(type='undo'))['document'];self.assertEqual(undo['variants'],configured['variants']);self.assertEqual(undo['items'],configured['items'])
            redo=c.success('session.apply',**session,request_id='redo',expected_revision=3,action=dict(type='redo'))['document'];self.assertEqual(redo['variants'],active['document']['variants']);self.assertEqual(redo['items'],active['document']['items'])
            diff=c.success('document.diff',before=configured,after=redo,compare_pixels=True);self.assertTrue(any(i['field']=='variants' for i in diff['metadata']));self.assertEqual(diff['rendered_pixels']['changed_pixels'],48);c.success('session.verify',**session)
            invalid=dict(op='variant_select',dataset='child',unknown_field=True);r=c.rpc('tools/call',dict(name='inkbolt_document_edit',arguments=dict(document=redo,expected_revision=redo['revision'],operations=[invalid])));self.assertTrue('error' in r or r['result']['isError'])

    def test_artboard_publication_and_component_svg_use_selected_state(self):
        d=self.document('vector');d=self.edit(d,dict(op='add',item=dict(id='board',transform=[1,0,0,1,8,0],content=dict(type='frame',frame=dict(role='artboard',width=24,height=12)))),dict(op='reparent',id='tile',parent='board'),dict(op='reparent',id='badge',parent='board'))
        # Reparenting preserves world placement; use a local-position dataset.
        active=self.select(self.define(d),'child')
        result=self.invoke(dict(command='artboard.export',document=active,format='png'))['artifacts'][0]['artifact'];self.assertEqual(result['variant'],'child')
        w,h,p=editing.png_pixels(base64.b64decode(result['data']))[:3];self.assertEqual(p,bytes(v for y in range(h) for x in range(w) for v in ([200,40,20,255] if 6<=x<10 and 4<=y<8 else [0]*4)))
        with tempfile.TemporaryDirectory() as root:
            r=self.invoke(dict(command='document.publish',document=active,output=dict(output_root=root,file_name='selected.svg',format='svg',artboard_id='board')))
            self.assertTrue(any('selected variant' in s for s in r['losses']))
        source=dict(id='source',content=dict(type='component_source'));shape=copy.deepcopy(byid(self.document('vector'),'tile'));shape['parent']='source'
        d=self.document('vector');d['items']=[source,shape,dict(id='copy',content=dict(type='instance',instance=dict(source='source')))];definition=dict(bindings=[binding('move','tile','position')],datasets=dict(right=dict(values=dict(move=value('position',[8,4])))))
        active=self.select(self.define(d,definition),'right');self.assertEqual(self.pixels(active),self.pixels(self.edit(active,dict(op='variants_clear',bake=True))))
        svg=self.invoke(dict(command='document.export',document=active,format='svg'));self.assertTrue(any('selected variant' in s for s in svg['losses']))


    def test_shared_keys_owned_properties_and_independent_duplicates(self):
        for kind in ('vector','raster'):
            d=self.document(kind);definition=dict(bindings=[binding('show','tile','visible'),binding('show','badge','visible')],datasets=dict(hidden=dict(values=dict(show=value('visible',False)))))
            d=self.define(d,definition);active=self.select(d,'hidden');self.assertEqual(self.pixels(active)[2],bytes(24*12*4))
            active=self.edit(active,dict(op='duplicate',id='tile',new_id='independent'))
            restored=self.select(active,None);self.assertFalse(byid(restored,'independent')['visible']);self.assertTrue(byid(restored,'tile')['visible']);self.assertTrue(byid(restored,'badge')['visible'])
            bad=copy.deepcopy(definition);bad['bindings'][1]['property']='opacity';self.edit(d,dict(op='variants_set',definition=bad),expected=1)
            self.assertEqual(d['variants']['base'],[value('visible',True)]*2)

    def test_failed_batches_stale_revisions_and_selected_state_tampering(self):
        d=self.define(self.document());before=copy.deepcopy(d)
        error=self.edit(d,dict(op='variant_select',dataset='child'),dict(op='variant_select',dataset='missing'),expected=1)
        self.assertEqual(error['operation_index'],1);self.assertEqual(d,before)
        self.assertEqual(self.invoke(dict(command='document.edit',document=d,expected_revision=0,operations=[dict(op='variant_select',dataset='child')]),1)['code'],'REVISION_CONFLICT')
        stale=copy.deepcopy(d);stale['variants']['selected']='child';self.assertEqual(self.invoke(dict(command='document.validate',document=stale),1)['code'],'VARIANT_CONTROLLED')
        active=self.select(d,'child');locked=self.edit(active,dict(op='properties',id='tile',locked=True))
        self.assertEqual(self.edit(locked,dict(op='variants_clear'),expected=1)['code'],'LOCKED')
        baked=self.edit(locked,dict(op='variants_clear',bake=True));self.assertTrue(byid(baked,'tile')['locked']);self.assertEqual(self.pixels(baked),self.pixels(locked))


if __name__=='__main__':unittest.main()
