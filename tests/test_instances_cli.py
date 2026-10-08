"""Original component fixtures with independent pixels, bounds and dependency checks."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import test_editing_cli as editing
from test_mcp import Client
from synthetic_font import geometric_font
from test_images_cli import png


def shape(id,parent,x,y,w,h,color):
    return dict(id=id,parent=parent,content=dict(type='vector',geometry=dict(shape='rect',x=x,y=y,width=w,height=h),fill=color))


def instance(id,source,transform=None,overrides=None,parent=None):
    return dict(id=id,parent=parent,transform=transform or [1,0,0,1,0,0],content=dict(type='instance',instance=dict(source=source,overrides=overrides or {})))


class InstanceTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke

    def document(self):
        d=self.invoke(dict(command='document.create',id='component-fixture',kind='vector',width=36,height=16))
        d['items']=[dict(id='icon',content=dict(type='component_source')),shape('body','icon',1,2,6,6,[240,60,20,255]),shape('mark','icon',3,4,2,2,[20,80,220,255]),instance('left','icon',[1,0,0,1,2,3]),instance('right','icon',[1,0,0,1,20,3])]
        self.invoke(dict(command='document.validate',document=d));return d

    def edit(self,d,*operations,expected=0):
        return self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=list(operations)),expected)

    def pixels(self,d,scale=1,**resources):
        result=self.invoke(dict(command='document.export',document=d,format='png',scale=scale,**resources))
        return editing.png_pixels(base64.b64decode(result['data']))[:3]

    def unlink(self,d,id):return self.edit(d,dict(op='instance_unlink',id=id))['document']

    def test_two_instances_match_independent_rectangles_and_hide_definition(self):
        d=self.document();w,h,p=self.pixels(d)
        expected=[]
        for y in range(h):
            for x in range(w):
                color=[0]*4
                for shift in (2,20):
                    if shift+1<=x<shift+7 and 5<=y<11:color=[240,60,20,255]
                    if shift+3<=x<shift+5 and 7<=y<9:color=[20,80,220,255]
                expected.extend(color)
        self.assertEqual(p,bytes(expected))
        inspected=self.invoke(dict(command='document.inspect',document=d))['items'];byid={i['id']:i for i in inspected}
        self.assertFalse(byid['icon']['effective_visible']);self.assertEqual(byid['left']['geometry_bounds'],[3,5,9,11]);self.assertEqual(byid['right']['geometry_bounds'],[21,5,27,11])
        self.assertEqual(byid['left']['instance']['source'],'icon');self.assertEqual(byid['left']['component_source_sha256'],byid['right']['component_source_sha256'])

    def test_definition_edits_propagate_while_style_overrides_keep_geometry_live(self):
        d=self.document();d['items'][-1]['content']['instance']['overrides']={'body':dict(vector_style=dict(fill=[30,190,80,255],stroke=None)),'mark':dict(visible=False)}
        original=copy.deepcopy(d)
        changed=self.edit(d,dict(op='vector',id='body',geometry=dict(shape='rect',x=0,y=1,width=8,height=8),fill=[100,40,220,255],stroke=None))['document']
        w,h,p=self.pixels(changed)
        for y in range(h):
            for x in range(w):
                color=[0]*4
                if 2<=x<10 and 4<=y<12:color=[100,40,220,255]
                if 5<=x<7 and 7<=y<9:color=[20,80,220,255]
                if 20<=x<28 and 4<=y<12:color=[30,190,80,255]
                self.assertEqual(p[(y*w+x)*4:(y*w+x+1)*4],bytes(color),(x,y))
        diff=self.invoke(dict(command='document.diff',before=d,after=changed,compare_pixels=True))
        records={i['id']:i for i in diff['items']}
        for id in ('left','right'):self.assertIn('derived.component_source_sha256',records[id]['fields'])
        self.assertEqual(d,original)

    def test_replace_unlink_duplicate_and_source_independence(self):
        d=self.document();d['items']+=[dict(id='badge',content=dict(type='component_source')),shape('badge-shape','badge',0,0,4,4,[20,200,100,255])]
        replaced=self.edit(d,dict(op='instance',id='right',instance=dict(source='badge')))['document']
        self.assertNotEqual(self.pixels(d),self.pixels(replaced))
        expanded=self.unlink(replaced,'left');self.assertEqual(self.pixels(expanded,3),self.pixels(replaced,3))
        later=self.edit(expanded,dict(op='properties',id='body',visible=False))['document'];self.assertEqual(self.pixels(later),self.pixels(expanded))
        duplicated=self.edit(replaced,dict(op='duplicate',id='left',new_id='copy'),dict(op='transform',id='copy',matrix=[1,0,0,1,10,0]))['document']
        self.assertEqual(next(i for i in duplicated['items'] if i['id']=='copy')['content'],replaced['items'][3]['content'])
        self.assertEqual(self.pixels(duplicated),self.pixels(self.unlink(duplicated,'copy')))

    def test_nested_components_bounds_and_nonuniform_reflection_match_direct_scene(self):
        d=self.document();d['items']=d['items'][:3]+[dict(id='pair',content=dict(type='component_source')),instance('inner-a','icon',parent='pair'),instance('inner-b','icon',[1,0,0,1,8,0],parent='pair'),instance('outer','pair',[-1,.25,.5,1,28,2])]
        d['items'][-1]['content']['instance']['overrides']={'inner-b':dict(transform=[.5,0,0,2,10,0])}
        expanded=self.unlink(d,'outer');self.assertEqual(self.pixels(d,3),self.pixels(expanded,3))
        expected=[]
        for a,b,c,e,tx,ty in ([1,0,0,1,0,0],[.5,0,0,2,10,0]):
            for x,y in ((1,2),(7,2),(7,8),(1,8)):
                u,v=a*x+c*y+tx,b*x+e*y+ty;expected.append([28-u+.5*v,2+.25*u+v])
        bounds=[min(p[0] for p in expected),min(p[1] for p in expected),max(p[0] for p in expected),max(p[1] for p in expected)]
        actual=next(i for i in self.invoke(dict(command='document.inspect',document=d))['items'] if i['id']=='outer')['geometry_bounds'];self.assertEqual(actual,bounds)
        svg=self.invoke(dict(command='document.export',document=d,format='svg'));self.assertTrue(any('Component instances' in s for s in svg['losses']))
        imported=self.invoke(dict(command='svg.import',id='instance-import',source=dict(kind='text',text=svg['data'])))['document'];self.assertEqual(self.pixels(imported,3),self.pixels(d,3))

    def test_snapshot_mcp_sessions_undo_redo_and_retry_preserve_definitions(self):
        d=self.document();self.assertEqual(json.loads(self.invoke(dict(command='document.export',document=d,format='snapshot'))['data'])['items'][0]['content'],dict(type='component_source'))
        c=Client();self.addCleanup(c.close);c.initialize()
        operation=dict(op='instance',id='right',instance=dict(source='icon',overrides={'mark':dict(visible=False)}))
        expected=self.edit(d,operation)['document'];self.assertEqual(c.success('document.edit',document=d,expected_revision=0,operations=[operation])['document'],expected)
        with tempfile.TemporaryDirectory() as root:
            session=dict(session_root=root,session_id='components');c.success('session.create',**session,request_id='create',document=d)
            args=dict(**session,request_id='override',expected_revision=0,action=dict(type='edit',operations=[operation]));r=c.success('session.apply',**args)
            self.assertEqual(r['document']['items'],expected['items']);self.assertTrue(c.success('session.apply',**args)['replayed'])
            undo=c.success('session.apply',**session,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'];self.assertEqual(self.pixels(undo),self.pixels(d))
            redo=c.success('session.apply',**session,request_id='redo',expected_revision=2,action=dict(type='redo'))['document'];self.assertEqual(self.pixels(redo),self.pixels(expected));c.success('session.verify',**session)
            args=dict(**session,request_id='unlink',expected_revision=3,action=dict(type='edit',operations=[dict(op='instance_unlink',id='right')]))
            unlinked=c.success('session.apply',**args);self.assertTrue(c.success('session.apply',**args)['replayed']);self.assertEqual(self.pixels(unlinked['document']),self.pixels(expected))
            undo=c.success('session.apply',**session,request_id='undo-unlink',expected_revision=4,action=dict(type='undo'))['document'];self.assertEqual(undo['items'],expected['items'])
            redo=c.success('session.apply',**session,request_id='redo-unlink',expected_revision=5,action=dict(type='redo'))['document'];self.assertEqual(redo['items'],unlinked['document']['items']);c.success('session.verify',**session)

    def test_missing_wrong_cycle_override_and_locked_dependencies_fail_atomically(self):
        d=self.document();before=copy.deepcopy(d)
        for target in ('missing','body'):
            self.edit(d,dict(op='instance',id='left',instance=dict(source=target)),expected=1)
        self.edit(d,dict(op='instance',id='left',instance=dict(source='icon',overrides={'missing':dict(visible=False)})),expected=1)
        for override in [dict(opacity=2),dict(transform=[0]*6),dict(vector_style=dict(fill=[1,2,3,4],stroke=None))]:
            self.edit(d,dict(op='instance',id='left',instance=dict(source='icon',overrides={'icon':override})),expected=1)
        cycle=copy.deepcopy(d);cycle['items'].append(instance('recursive','icon',parent='icon'));self.invoke(dict(command='document.validate',document=cycle),1)
        locked=copy.deepcopy(d);locked['items'][-1]['locked']=True
        self.assertEqual(self.edit(locked,dict(op='properties',id='body',visible=False),expected=1)['code'],'LOCKED')
        self.edit(d,dict(op='remove',id='icon'),expected=1);self.assertEqual(d,before)

    def test_instance_opacity_gradient_clips_and_unlinked_masks_have_independent_pixels(self):
        d=self.document();d['items']=d['items'][:2]+d['items'][3:]
        body=d['items'][1];body['content']['geometry']=dict(shape='rect',x=0,y=0,width=8,height=8)
        body['content']['fill']=dict(type='linear',start=[0,0],end=[8,0],stops=[dict(offset=0,color=[0,40,240,255]),dict(offset=1,color=[240,120,0,255])])
        body['mask']=dict(width=2,height=1,gray_hex='4080',transform=[4,0,0,8,0,0],linked=False)
        body['clip']=dict(geometry=dict(shape='rect',x=1,y=1,width=6,height=6))
        d['items'][0]['opacity']=.5
        for i in d['items'][2:]:i['opacity']=.5
        w,h,p=self.pixels(d)
        for shift in (2,20):
            for y in range(8):
                for x in range(8):
                    actual=p[((y+3)*w+x+shift)*4:((y+3)*w+x+shift+1)*4]
                    wanted=[int(240*(x+.5)/8+.5),int(40+80*(x+.5)/8+.5),int(240*(1-(x+.5)/8)+.5),16 if x<4 else 32] if 1<=x<7 and 1<=y<7 else [0]*4
                    self.assertEqual(actual,bytes(wanted),(shift,x,y))
        expanded=self.unlink(self.unlink(d,'left'),'right');self.assertEqual(self.pixels(expanded,3),self.pixels(d,3))
        ids=[i['id'] for i in expanded['items']];self.assertEqual(len(ids),len(set(ids)))

    def test_nested_appearance_filters_effects_equal_explicit_groups(self):
        d=self.document();d['items'][0].update(opacity=.75,fill_opacity=.5,effects=[dict(id='shadow',operator=dict(type='shadow',offset=[1,1],sigma=0),color=[10,20,30,128])])
        d['items'][1]['filters']=[dict(id='soft',operator=dict(type='box',radius=1))]
        d['items'][2]['blend']='multiply';d['items'][3].update(blend='screen',opacity=.625)
        back=shape('background',None,0,0,36,16,[60,110,150,255]);d['items'].insert(0,back)
        direct=copy.deepcopy(d);direct['items']=[back]
        for id,shift in [('left',2),('right',20)]:
            root=copy.deepcopy(next(i for i in d['items'] if i['id']==id));root['content']=dict(type='group',isolated=True);direct['items'].append(root)
            for src in d['items'][1:4]:
                item=copy.deepcopy(src);item['id']=id+'-'+src['id'];item['parent']=id if src['id']=='icon' else id+'-icon'
                if src['id']=='icon':item['content']=dict(type='group',isolated=True)
                direct['items'].append(item)
        for scale in (1,3):self.assertEqual(self.pixels(d,scale),self.pixels(direct,scale))
        self.assertEqual(self.pixels(d,3),self.pixels(self.unlink(d,'left'),3))

    def test_artboard_exports_and_publication_preserve_component_mask_coordinates(self):
        d=self.document();d['items']=d['items'][:2]+[dict(id='board',transform=[1,0,0,1,18,2],content=dict(type='frame',frame=dict(role='artboard',width=12,height=12))),instance('placed','icon',[1,0,0,1,2,3],parent='board')]
        d['items'][1]['mask']=dict(width=1,height=1,gray_hex='80',transform=[8,0,0,8,0,0],linked=False)
        expected=copy.deepcopy(d);expected['width']=expected['height']=12;expected['items'][2]['transform']=[1,0,0,1,0,0]
        wanted=self.pixels(expected,2)
        result=self.invoke(dict(command='artboard.export',document=d,format='png',scale=2));self.assertEqual(editing.png_pixels(base64.b64decode(result['artifacts'][0]['artifact']['data']))[:3],wanted)
        svg=self.invoke(dict(command='artboard.export',document=d,format='svg'))['artifacts'][0]['artifact'];self.assertTrue(any('Component instances' in s for s in svg['losses']))
        with tempfile.TemporaryDirectory() as root:
            output=dict(output_root=root,file_name='board.png',format='png',artboard_id='board',scale=2)
            result=self.invoke(dict(command='document.publish',document=d,output=output))
            self.assertEqual(editing.png_pixels(Path(result['path']).read_bytes())[:3],wanted)
            result=self.invoke(dict(command='document.publish',document=d,output=dict(output_root=root,file_name='components.json',format='snapshot')))
            saved=json.loads(Path(result['path']).read_text());self.assertEqual(self.pixels(saved,2),self.pixels(d,2))
            self.assertEqual(next(i for i in saved['items'] if i['id']=='body')['mask']['transform'],[8,0,0,8,0,0])

    def test_components_in_artwork_masks_and_transitive_dependency_locks(self):
        d=self.document();d['items']=d['items'][:3]+[dict(id='mask-source',content=dict(type='mask_source')),instance('masked-icon','icon',parent='mask-source'),shape('owner',None,0,0,12,12,[50,180,240,255])]
        d['items'][-1]['artwork_mask']=dict(source='mask-source',region=[0,0,12,12],mode='alpha');d['items'][-1]['locked']=True
        self.assertEqual(self.edit(d,dict(op='properties',id='body',visible=False),expected=1)['code'],'LOCKED')
        d['items'][-1]['locked']=False;w,h,p=self.pixels(d)
        for y in range(h):
            for x in range(w):self.assertEqual(p[(y*w+x)*4:(y*w+x+1)*4],bytes([50,180,240,255] if 1<=x<7 and 2<=y<8 else [0]*4))
        self.assertEqual(self.pixels(self.unlink(d,'masked-icon'),3),self.pixels(d,3))
        changed=self.edit(d,dict(op='properties',id='body',visible=False))['document']
        diff=self.invoke(dict(command='document.diff',before=d,after=changed,compare_pixels=True))
        self.assertIn('derived.artwork_mask_source_sha256',next(i for i in diff['items'] if i['id']=='owner')['fields'])
        # A locked instance also protects a separate mask used by its definition.
        d=self.document();d['items']+=[dict(id='opacity-source',content=dict(type='mask_source')),shape('opacity','opacity-source',0,0,8,8,[255]*4)]
        d['items'][1]['artwork_mask']=dict(source='opacity-source',region=[0,0,8,8],mode='alpha');d['items'][4]['locked']=True
        self.assertEqual(self.edit(d,dict(op='properties',id='opacity',visible=False),expected=1)['code'],'LOCKED')

    def test_content_overrides_text_images_fonts_and_input_files_remain_original(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);fontfile=root/'original.ttf';fontfile.write_bytes(geometric_font());license=root/'LICENSE.txt';license.write_bytes((Path(__file__).resolve().parents[1]/'LICENSE').read_bytes());store=root/'fonts'
            font=self.invoke(dict(command='font.import',source_path=str(fontfile),license_path=str(license),store_root=str(store)))
            imagefile=root/'original.png';pixels=bytes([240,30,20,255,20,210,60,128,30,80,240,255,240,220,30,255]);imagefile.write_bytes(png(2,2,pixels));assets=root/'assets'
            asset=self.invoke(dict(command='asset.import',source_path=str(imagefile),store_root=str(assets)))['asset']
            resources=dict(font_root=str(store),asset_root=str(assets));original=[fontfile.read_bytes(),imagefile.read_bytes()]
            d=self.document();d['fonts']={'font':font,'override-font':font};d['assets']={'image':asset,'override-image':asset};d['items'][1]['content']=dict(type='text',frame=dict(text='A',width=12,height=16,style=dict(font_id='font',size=10,fill=[20,80,180,255])))
            d['items'][2]['content']=dict(type='image',asset_id='image',width=2,height=2);d['items'][2]['transform']=[1,0,0,1,8,2]
            frame=copy.deepcopy(d['items'][1]['content']);frame['frame']['text']='B';frame['frame']['style']['font_id']='override-font';image_override=dict(type='image',asset_id='override-image',width=2,height=2)
            d['items'][-1]['content']['instance']['overrides']={'body':dict(content=frame),'mark':dict(content=image_override)}
            for op,id,error in [('font_remove','override-font','FONT_IN_USE'),('asset_remove','override-image','ASSET_IN_USE')]:
                self.assertEqual(self.edit(d,dict(op=op,id=id),expected=1)['code'],error)
            d['items'][-1]['locked']=True
            for operation in [dict(op='font_put',id='override-font',font=font),dict(op='asset_put',id='override-image',asset=asset)]:
                self.assertEqual(self.edit(d,operation,expected=1)['code'],'LOCKED')
            d['items'][-1]['locked']=False
            expanded=self.invoke(dict(command='document.edit',document=d,expected_revision=0,operations=[dict(op='instance_unlink',id='left'),dict(op='instance_unlink',id='right')],**resources))['document']
            self.assertEqual(self.pixels(d,2,**resources),self.pixels(expanded,2,**resources))
            for fmt in ('snapshot','svg'):
                result=self.invoke(dict(command='document.export',document=d,format=fmt,**resources));self.assertTrue(result['data'])
            self.assertEqual([fontfile.read_bytes(),imagefile.read_bytes()],original)
            broken=copy.deepcopy(d);broken['items'][-1]['content']['instance']['overrides']['body']['content']['frame']['style']['font_id']='missing';self.invoke(dict(command='document.validate',document=broken),1)

    def test_unused_cycles_nesting_and_generated_limits(self):
        d=self.document();chain=copy.deepcopy(d);chain['items']=[]
        for i in range(8):
            chain['items'].append(dict(id=f'd{i}',content=dict(type='component_source')))
            chain['items'].append(instance(f'n{i}',f'd{i+1}',parent=f'd{i}') if i<7 else shape('leaf','d7',0,0,1,1,[255]*4))
        chain['items'].append(instance('root','d0'));self.invoke(dict(command='document.validate',document=chain))
        cycle=copy.deepcopy(chain);cycle['items'][-2]=instance('leaf','d0',parent='d7');cycle['items'].pop();self.invoke(dict(command='document.validate',document=cycle),1)
        deep=copy.deepcopy(chain);deep['items'][-2]=instance('leaf','d8',parent='d7');deep['items'] += [dict(id='d8',content=dict(type='component_source')),shape('last','d8',0,0,1,1,[255]*4)];self.assertEqual(self.invoke(dict(command='document.validate',document=deep),1)['code'],'RESOURCE_LIMIT')
        many=copy.deepcopy(d);many['items']=[dict(id='source',content=dict(type='component_source'))]+[shape(f's{i}','source',0,0,1,1,[255]*4) for i in range(90)]+[dict(instance(f'copy{i}','source'),visible=False) for i in range(3)]
        self.assertEqual(self.invoke(dict(command='document.validate',document=many),1)['code'],'RESOURCE_LIMIT')
        huge=copy.deepcopy(d);huge['items']=[dict(id=f'd{i}',content=dict(type='component_source')) for i in range(33)];self.assertEqual(self.invoke(dict(command='document.validate',document=huge),1)['code'],'RESOURCE_LIMIT')
        # A copy may fit evaluation but exceed storage when unlinked alongside its definition.
        many['items']=many['items'][:1]+[shape(f's{i}','source',0,0,1,1,[255]*4) for i in range(130)]+[instance('copy','source')]
        self.invoke(dict(command='document.validate',document=many));self.assertEqual(self.edit(many,dict(op='instance_unlink',id='copy'),expected=1)['code'],'RESOURCE_LIMIT')

    def test_nested_replacement_dependency_closure_hash_locks_and_board_publication(self):
        d=self.document();d['items']=[]
        for id,color in [('b',[220,20,30,255]),('c',[20,200,40,255]),('e',[30,40,230,255])]:
            d['items'] += [dict(id=id,content=dict(type='component_source')),shape(id+'-shape',id,0,0,4,4,color)]
        d['items'] += [dict(id='a',content=dict(type='component_source')),instance('nested','b',parent='a'),dict(id='replacement',content=dict(type='component_source')),instance('nested-again','c',parent='replacement')]
        replacement=instance('unused','replacement',overrides={'nested-again':dict(content=instance('unused','e')['content'])})['content']
        d['items'] += [dict(id='board',content=dict(type='frame',frame=dict(role='artboard',width=8,height=8))),instance('host','a',overrides={'nested':dict(content=replacement)},parent='board')]
        p=self.pixels(d)[2];self.assertEqual(p[:4],bytes([30,40,230,255]))
        changed=self.edit(d,dict(op='properties',id='e-shape',opacity=.5))['document']
        diff=self.invoke(dict(command='document.diff',before=d,after=changed,compare_pixels=True))
        self.assertIn('derived.component_source_sha256',next(i for i in diff['items'] if i['id']=='host')['fields'])
        d['items'][-1]['locked']=True;self.assertEqual(self.edit(d,dict(op='properties',id='e-shape',opacity=.5),expected=1)['code'],'LOCKED');d['items'][-1]['locked']=False
        with tempfile.TemporaryDirectory() as root:
            r=self.invoke(dict(command='document.publish',document=d,output=dict(output_root=root,file_name='board.png',format='png',artboard_id='board')))
            w,h,p=editing.png_pixels(Path(r['path']).read_bytes())[:3];self.assertEqual((w,h),(8,8))
            self.assertEqual(p,bytes(v for y in range(h) for x in range(w) for v in ([30,40,230,255] if x<4 and y<4 else [0]*4)))

    def test_generated_id_collisions_ordering_and_invalid_overrides_are_explicit(self):
        d=self.document();collision='ib-instance-'+hashlib.sha256(json.dumps(['left','body'],separators=(',',':')).encode()).hexdigest()[:24]
        d['items'].append(dict(shape(collision,None,0,0,1,1,[255]*4),visible=False))
        d['items']=[d['items'][1],d['items'][0]]+d['items'][2:]
        result=self.edit(d,dict(op='instance_unlink',id='left'))['document']
        self.assertEqual(self.pixels(d,3),self.pixels(result,3));ids=[i['id'] for i in result['items']];self.assertIn(collision+'-1',ids);self.assertEqual(len(ids),len(set(ids)))
        for content in [dict(type='mask_source'),dict(type='frame',frame=dict(role='artboard',width=8,height=8))]:
            self.edit(d,dict(op='instance',id='left',instance=dict(source='icon',overrides={'body':dict(content=content)})),expected=1)
        c=Client();self.addCleanup(c.close);c.initialize()
        bad=dict(op='instance',id='left',instance=dict(source='icon',overrides={'body':dict(unknown_property=True)}))
        response=c.rpc('tools/call',dict(name='inkbolt_document_edit',arguments=dict(document=d,expected_revision=0,operations=[bad])))
        self.assertTrue('error' in response or response.get('result',{}).get('isError'))


if __name__=='__main__':unittest.main()
