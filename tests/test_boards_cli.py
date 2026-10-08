"""Independent artboard pixels, SVG structure, range selection and persistence fixtures."""
import base64
import copy
import json
import unittest
import xml.etree.ElementTree as ET
import test_editing_cli as editing


class BoardCliTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke

    def edit(self,d,ops,expected=0):
        r=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=ops),expected)
        return r if expected else r['document']

    def board(self,id,w,h,x=0,y=0,parent=None,role='artboard',**options):
        return dict(id=id,name='Original '+id,parent=parent,transform=[1,0,0,1,x,y],content=dict(type='frame',frame=dict(role=role,width=w,height=h,**options)))

    def rectangle(self,id,parent,kind,x,y,w,h,color):
        if kind=='vector':
            return dict(id=id,parent=parent,content=dict(type='vector',geometry=dict(shape='rect',x=x,y=y,width=w,height=h),fill=color))
        return dict(id=id,parent=parent,transform=[1,0,0,1,x,y],content=dict(type='raster',width=w,height=h,rgba_hex=bytes(color).hex()*(w*h)))

    def fixture(self,kind='vector'):
        d=self.invoke(dict(command='document.create',id='board-fixture',kind=kind,width=32,height=24))
        items=[self.board('wide',5,4,2,3,background=[20,30,40,255],bleed=dict(top=1,right=2,bottom=2,left=1),guides=[dict(id='column',axis='x',position=2)]),self.rectangle('red','wide',kind,-1,1,8,2,[210,20,30,255]),self.rectangle('off','wide',kind,8,0,2,2,[0,200,0,255]),self.board('tall',3,6,14,1),self.rectangle('blue','tall',kind,1,-1,1,8,[20,50,220,255]),self.rectangle('pasteboard',None,kind,2,3,2,2,[0,200,0,255])]
        return self.edit(d,[dict(op='add',item=item) for item in items])

    def exports(self,d,expected=0,**kwargs):
        return self.invoke(dict(command='artboard.export',document=d,format='png',**kwargs),expected)

    def pixels(self,entry):
        return editing.png_pixels(base64.b64decode(entry['artifact']['data']))[:3]

    def test_named_unequal_artboards_clip_every_pixel_at_two_scales(self):
        for kind in ('vector','raster'):
            d=self.fixture(kind);before=copy.deepcopy(d)
            for scale in (1,2):
                result=self.exports(d,scale=scale)
                self.assertEqual([e['id'] for e in result['artifacts']],['wide','tall'])
                self.assertEqual([e['name'] for e in result['artifacts']],['Original wide','Original tall'])
                for entry in result['artifacts']:
                    w,h,p=self.pixels(entry);expected_size=(5,4) if entry['id']=='wide' else (3,6)
                    self.assertEqual((w,h),tuple(v*scale for v in expected_size))
                    for y in range(h):
                        for x in range(w):
                            if entry['id']=='wide':color=[210,20,30,255] if 1<=y//scale<3 else [20,30,40,255]
                            else:color=[20,50,220,255] if x//scale==1 else [0,0,0,0]
                            self.assertEqual(p[(y*w+x)*4:(y*w+x+1)*4],bytes(color))
            self.assertEqual(d,before)
            # Board exports retain off-board source and exclude unrelated pasteboard artwork.
            self.assertIn('off',[i['id'] for i in d['items']])
            whole=self.invoke(dict(command='document.render',document=d));raw=bytes.fromhex(whole['data'])
            self.assertEqual(raw[(3*32+2)*4:(3*32+3)*4],bytes([0,200,0,255]))

    def test_asymmetric_bleed_reveals_owned_pixels_and_preserves_original_geometry(self):
        for kind in ('vector','raster'):
            d=self.fixture(kind);source=json.dumps(d,sort_keys=True)
            e=self.exports(d,include_bleed=True,selection=dict(type='ids',ids=['wide']))['artifacts'][0]
            self.assertEqual(e['source_bounds'],[-1,-1,7,6]);self.assertEqual(e['trim_box'],[1,1,6,5])
            w,h,p=self.pixels(e);self.assertEqual((w,h),(8,7))
            for y in range(h):
                for x in range(w):
                    expected=[210,20,30,255] if 2<=y<4 else [20,30,40,255]
                    self.assertEqual(p[(y*w+x)*4:(y*w+x+1)*4],bytes(expected))
            self.assertEqual(json.dumps(d,sort_keys=True),source)
            moved=self.edit(d,[dict(op='transform',id='wide',matrix=[0,2,-2,0,18,3])])
            self.assertEqual(self.exports(moved,include_bleed=True,selection=dict(type='ids',ids=['wide']))['artifacts'][0]['artifact'],e['artifact'])

    def test_reorder_duplicate_remove_ranges_and_roundtrip_keep_board_contents(self):
        for kind in ('vector','raster'):
            d=self.fixture(kind);original=copy.deepcopy(d)
            changed=self.edit(d,[dict(op='duplicate',id='wide',new_id='copy',descendant_ids={'red':'red-copy','off':'off-copy'}),dict(op='reorder',id='copy',index=0)])
            inspected=self.invoke(dict(command='document.inspect',document=changed))
            self.assertEqual([e['id'] for e in inspected['artboards']],['copy','wide','tall'])
            self.assertEqual(inspected['artboards'][0]['frame'],inspected['artboards'][1]['frame'])
            ranged=self.exports(changed,selection=dict(type='range',start=0,end=2),include_bleed=True)
            self.assertEqual([e['id'] for e in ranged['artifacts']],['copy','wide'])
            self.assertEqual(self.pixels(ranged['artifacts'][0]),self.pixels(ranged['artifacts'][1]))
            reversed=self.exports(changed,selection=dict(type='ids',ids=['tall','wide']))
            self.assertEqual([e['id'] for e in reversed['artifacts']],['tall','wide'])
            removed=self.edit(changed,[dict(op='remove',id='wide')]);self.assertNotIn('red',[i['id'] for i in removed['items']]);self.assertIn('red-copy',[i['id'] for i in removed['items']]);self.assertIn('off-copy',[i['id'] for i in removed['items']])
            saved=self.invoke(dict(command='document.export',document=removed,format='snapshot'))
            reopened=self.invoke(dict(command='document.validate',document=json.loads(saved['data'])))
            self.assertEqual(removed,reopened);self.assertEqual(self.exports(removed),self.exports(reopened));self.assertEqual(d,original)

    def test_nested_raster_frames_guides_and_independent_inner_board_exports(self):
        d=self.invoke(dict(command='document.create',id='nested',kind='raster',width=16,height=16))
        items=[self.board('outer',8,8,background=[20,30,40,255]),self.board('frame',4,4,1,1,parent='outer',role='frame'),self.rectangle('red','frame','raster',0,0,6,6,[210,20,30,255]),self.board('inner',2,3,3,3,parent='frame',background=[20,50,220,255])]
        d=self.edit(d,[dict(op='add',item=i) for i in items]);before=self.exports(d)
        d=self.edit(d,[dict(op='guide_put',id='frame',guide=dict(id='left',axis='x',position=2)),dict(op='guide_put',id='frame',guide=dict(id='top',axis='y',position=3))])
        result=self.exports(d)
        self.assertEqual([e['id'] for e in result['artifacts']],['outer','inner'])
        self.assertEqual([e['artifact'] for e in before['artifacts']],[e['artifact'] for e in result['artifacts']])
        w,h,p=self.pixels(result['artifacts'][0]);self.assertEqual((w,h),(8,8))
        for y in range(h):
            for x in range(w):
                expected=[20,30,40,255]
                if 1<=x<5 and 1<=y<5:expected=[210,20,30,255]
                if x==4 and y==4:expected=[20,50,220,255]
                self.assertEqual(p[(y*w+x)*4:(y*w+x+1)*4],bytes(expected))
        w,h,p=self.pixels(result['artifacts'][1]);self.assertEqual((w,h),(2,3));self.assertEqual(p,bytes([20,50,220,255])*6)
        saved=self.invoke(dict(command='document.export',document=d,format='snapshot'))
        restored=self.invoke(dict(command='document.validate',document=json.loads(saved['data'])));self.assertEqual(d,restored)
        self.assertEqual(self.exports(restored),result)

    def test_svg_board_and_nested_frame_clips_are_independently_parsed(self):
        d=self.fixture();ns={'s':'http://www.w3.org/2000/svg'}
        for bleed in (False,True):
            r=self.invoke(dict(command='artboard.export',document=d,format='svg',include_bleed=bleed))
            for e in r['artifacts']:
                root=ET.fromstring(e['artifact']['data']);w,h=e['logical_size']
                self.assertEqual([int(root.attrib[k]) for k in ['width','height']],[w,h])
                ids=[n.attrib['id'] for n in root.iter() if 'id' in n.attrib];self.assertEqual(len(ids),len(set(ids)))
                clip=root.find('.//s:clipPath/s:rect',ns);self.assertEqual([float(clip.attrib[k]) for k in ['x','y','width','height']],[0,0,w,h])
                group=root.find('s:g',ns);self.assertEqual(group.attrib['transform'],'matrix(1 0 0 1 0 0)')
                self.assertTrue(any('artboards' in text for text in e['artifact']['losses']))
                if e['id']=='wide':
                    children={g.attrib.get('id'):g for g in root.findall('.//s:g',ns)}
                    self.assertNotIn('pasteboard',children);self.assertNotIn('tall',children)
                    self.assertIn('off',children)
                    red=children['red'];self.assertEqual(red.attrib['transform'],'matrix(1 0 0 1 1 1)' if bleed else 'matrix(1 0 0 1 0 0)')
                    rect=red.find('s:rect',ns);self.assertEqual([float(rect.attrib[k]) for k in ['x','y','width','height']],[-1,1,8,2])

    def test_invalid_selections_frame_edits_and_batch_limits_fail_without_partial_results(self):
        d=self.fixture();before=copy.deepcopy(d)
        for selection in [dict(type='ids',ids=[]),dict(type='ids',ids=['wide','wide']),dict(type='ids',ids=['red']),dict(type='range',start=1,end=3),dict(type='range',start=2,end=2)]:
            error=self.exports(d,1,selection=selection);self.assertEqual(error['code'],'INVALID_OPERATION');self.assertNotIn('artifacts',error)
        error=self.exports(d,1,selection=dict(type='ids',ids=['absent']));self.assertEqual(error['artboard_id'],'absent')
        self.assertEqual(self.exports(d,1,selection=dict(type='all',unexpected=True))['code'],'INVALID_REQUEST')
        frame=copy.deepcopy(d['items'][0]['content']['frame']);frame['width']=0
        error=self.edit(d,[dict(op='reorder',id='tall',index=0),dict(op='frame',id='wide',frame=frame)],1)
        self.assertEqual(error['operation_index'],1);self.assertEqual(d,before)
        large=self.invoke(dict(command='document.create',id='large',kind='raster',width=1,height=1))
        large=self.edit(large,[dict(op='add',item=self.board('b'+str(i),1024,1024)) for i in range(5)])
        error=self.exports(large,1);self.assertEqual(error['code'],'RESOURCE_LIMIT');self.assertEqual(error['artboard_id'],'b4')

    def test_selected_subtree_ignores_unrelated_missing_assets_and_reports_failed_board(self):
        d=self.fixture()
        missing=dict(width=1,height=1,sha256='a'*64,storage=dict(type='stored'))
        d=self.edit(d,[dict(op='asset_put',id='missing',asset=missing),dict(op='add',item=dict(id='missing-image',parent='tall',content=dict(type='image',asset_id='missing',width=1,height=1)))])
        result=self.exports(d,selection=dict(type='ids',ids=['wide']))
        self.assertEqual(len(result['artifacts']),1)
        failure=self.exports(d,1)
        self.assertEqual(failure['code'],'ASSET_ROOT_REQUIRED');self.assertEqual(failure['artboard_id'],'tall');self.assertEqual(failure['asset_id'],'missing');self.assertNotIn('artifacts',failure)


if __name__=='__main__':unittest.main()
