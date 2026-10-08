"""Independent layer-transfer pixels, reference closure, identity and history checks."""
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
from test_transform_policies_cli import matrix_product, inverse, point


def rect(id,parent=None,x=0,y=0,width=4,height=4,color=None):
    return dict(id=id,parent=parent,name='Repeated name',content=dict(type='vector',geometry=dict(shape='rect',x=x,y=y,width=width,height=height),fill=color or [40,100,220,255]))
def byid(d,id):return next(i for i in d['items'] if i['id']==id)
def group(id,parent=None,**settings):return dict(id=id,parent=parent,name='Repeated name',content=dict(type='group',role='layer',isolated=True),**settings)
def instance(id,source,parent=None,**settings):return dict(id=id,parent=parent,content=dict(type='instance',instance=dict(source=source,**settings)))


class TransferTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def create(self,id='destination',kind='vector',width=48,height=32):return self.invoke(dict(command='document.create',id=id,kind=kind,width=width,height=height))
    def edit(self,d,*ops,expected=0,**resources):return self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=list(ops),**resources),expected)
    def transfer(self,d,source,ids,prefix='copy',expected=0,resources=None,**settings):return self.edit(d,dict(op='transfer',transfer=dict(source=source,ids=ids,prefix=prefix,**settings)),expected=expected,**(resources or {}))
    def pixels(self,d,scale=1,**resources):
        r=self.invoke(dict(command='document.export',document=d,format='png',scale=scale,**resources));return editing.png_pixels(base64.b64decode(r['data']))[:3]
    def inspect(self,d):return {i['id']:i for i in self.invoke(dict(command='document.inspect',document=d))['items']}
    def nested(self):
        s=self.create('source');s['items']=[group('layer',transform=[2,0,0,1,4,3],opacity=.5),group('nested','layer',transform=[1,0,0,2,2,1]),rect('shape','nested',1,1,4,3),rect('excluded','layer',16,16)]
        return s

    def test_nested_layers_duplicate_names_world_placement_and_every_pixel(self):
        source=self.nested();original=copy.deepcopy(source);d=self.create();d['items']=[group('destination-parent',transform=[2,0,0,2,10,2]),rect('shape',x=32,y=2,color=[30,180,100,255])];before=copy.deepcopy(d)
        result=self.transfer(d,source,['shape'],parent='destination-parent');out=result['document'];receipt=result['changes'][0]['details']
        self.assertEqual(receipt['item_ids'],dict(layer='copy-layer',nested='copy-nested',shape='copy-shape'));self.assertEqual(receipt['included_context_ids'],['layer','nested'])
        normalized=self.invoke(dict(command='document.validate',document=source));self.assertEqual(receipt['source_snapshot_sha256'],hashlib.sha256(json.dumps(normalized,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest())
        self.assertEqual(byid(out,'copy-layer')['parent'],'destination-parent');self.assertEqual(byid(out,'copy-shape')['parent'],'copy-nested');self.assertEqual(self.inspect(out)['copy-shape']['geometry_bounds'],[10,6,18,12])
        self.assertTrue(all(byid(out,id)['name']=='Repeated name' for id in receipt['item_ids'].values()))
        for scale in (1,3):
            w,h,p=self.pixels(out,scale)
            self.assertEqual(p,bytes(v for y in range(h) for x in range(w) for v in ([40,100,220,128] if 10<=(x+.5)/scale<18 and 6<=(y+.5)/scale<12 else [30,180,100,255] if 32<=(x+.5)/scale<36 and 2<=(y+.5)/scale<6 else [0]*4)))
        self.assertEqual(out['items'][:2],self.invoke(dict(command='document.validate',document=before))['items']);self.assertEqual(source,original);self.assertEqual(d,before)
        snapshot=self.invoke(dict(command='document.export',document=out,format='snapshot'));self.assertEqual(json.loads(snapshot['data']),out)

    def test_overlapping_selection_deduplicates_and_preserves_sibling_order(self):
        s=self.create('source');s['items']=[group('layer'),rect('first','layer',x=2,y=2,color=[255,0,0,255]),rect('second','layer',x=4,y=2,color=[0,0,255,255])]
        a=self.transfer(self.create(),s,['layer','second'])['document'];b=self.transfer(self.create(),s,['second','layer'])['document']
        self.assertEqual(a,b);self.assertEqual([i['id'] for i in a['items']],['copy-layer','copy-first','copy-second'])
        w,h,p=self.pixels(a)
        self.assertEqual(p,bytes(v for y in range(h) for x in range(w) for v in ([0,0,255,255] if 4<=x<8 and 2<=y<6 else [255,0,0,255] if 2<=x<4 and 2<=y<6 else [0]*4)))

    def components(self):
        s=self.create('source');body=rect('body','icon',width=8,height=8);body['artwork_mask']=dict(source='mask',region=[0,0,8,8],mode='alpha')
        nested=instance('outer','pair',overrides={'inner-b':dict(content=dict(type='instance',instance=dict(source='alternate',overrides={'alternate-body':dict(vector_style=dict(fill=[30,180,100,255],stroke=None))})))})
        nested['transform']=[1,0,0,1,2,3]
        s['items']=[dict(id='mask',content=dict(type='mask_source')),rect('mask-shape','mask',width=4,height=8,color=[255]*4),dict(id='icon',content=dict(type='component_source')),body,dict(id='alternate',content=dict(type='component_source')),rect('alternate-body','alternate',width=4,height=4,color=[255,0,0,255]),dict(id='pair',content=dict(type='component_source')),instance('inner-a','icon','pair'),dict(instance('inner-b','icon','pair'),transform=[1,0,0,1,12,0]),nested]
        return s

    def test_transitive_components_masks_nested_overrides_and_svg_match_independent_pixels(self):
        source=self.components();result=self.transfer(self.create(),source,['outer']);out=result['document'];mapping=result['changes'][0]['details']['item_ids'];self.assertEqual(len(mapping),10)
        self.assertEqual(byid(out,'copy-body')['artwork_mask']['source'],'copy-mask')
        nested=byid(out,'copy-outer')['content']['instance'];self.assertEqual(nested['source'],'copy-pair');inner=nested['overrides']['copy-inner-b']['content']['instance'];self.assertEqual(inner['source'],'copy-alternate');self.assertIn('copy-alternate-body',inner['overrides'])
        for scale in (1,3):
            w,h,p=self.pixels(out,scale)
            self.assertEqual(p,bytes(v for y in range(h) for x in range(w) for v in ([40,100,220,255] if 2<=(x+.5)/scale<6 and 3<=(y+.5)/scale<11 else [30,180,100,255] if 14<=(x+.5)/scale<18 and 3<=(y+.5)/scale<7 else [0]*4)))
            self.assertEqual(self.pixels(source,scale),(w,h,p))
        svg=self.invoke(dict(command='document.export',document=out,format='svg'))['data'];imported=self.invoke(dict(command='svg.import',id='imported',source=dict(kind='text',text=svg)))['document'];self.assertEqual(self.pixels(imported,3),self.pixels(out,3))
        changed=self.edit(out,dict(op='properties',id='copy-mask-shape',visible=False))['document'];self.assertNotEqual(self.pixels(changed),self.pixels(out));self.assertTrue(byid(source,'mask-shape').get('visible',True))

    def test_reference_deletion_fails_until_dependents_are_removed(self):
        out=self.transfer(self.create(),self.components(),['outer'])['document'];before=copy.deepcopy(out)
        for id in ['copy-mask','copy-icon','copy-pair','copy-alternate-body']:
            self.edit(out,dict(op='remove',id=id),expected=1)
        removed=self.edit(out,dict(op='remove',id='copy-outer'),dict(op='remove',id='copy-pair'),dict(op='remove',id='copy-icon'),dict(op='remove',id='copy-mask'),dict(op='remove',id='copy-alternate'))['document'];self.assertEqual(removed['items'],[]);self.assertEqual(out,before)

    def test_independent_copies_source_locks_and_transferred_dependency_locks(self):
        source=self.components();source_before=copy.deepcopy(source);out=self.transfer(self.create(),source,['outer'],'one')['document'];out=self.transfer(out,source,['outer'],'two')['document']
        out=self.edit(out,dict(op='properties',id='one-mask-shape',visible=False))['document'];self.assertTrue(byid(out,'two-mask-shape')['visible']);self.assertEqual(source,source_before)
        locked=self.edit(out,dict(op='properties',id='two-outer',locked=True))['document'];self.assertEqual(self.edit(locked,dict(op='properties',id='two-body',visible=False),expected=1)['code'],'LOCKED')
        source['items'][-1]['locked']=True;copylocked=self.transfer(self.create(),source,['outer'])['document'];self.assertTrue(byid(copylocked,'copy-outer')['locked'])

    def test_resource_descriptors_fonts_ranges_and_override_images_are_remapped(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);f=root/'source.ttf';f.write_bytes(geometric_font());lic=root/'LICENSE.txt';lic.write_bytes((Path(__file__).resolve().parents[1]/'LICENSE').read_bytes());im=root/'source.png';pixels=bytes([220,40,80,255])*4;im.write_bytes(png(2,2,pixels))
            font=self.invoke(dict(command='font.import',source_path=str(f),license_path=str(lic),store_root=str(root/'fonts')));asset=self.invoke(dict(command='asset.import',source_path=str(im),store_root=str(root/'assets')))['asset']
            source=self.create('source');source['fonts']={'font':font,'unused':font};source['assets']={'image':asset,'unused':asset}
            frame=dict(text='AA',width=30,height=20,style=dict(font_id='font',size=10,fill=[40,100,220,255]),ranges=[dict(start=1,end=2,style=dict(font_id='font',size=10,fill=[30,180,100,255]))])
            source['items']=[dict(id='source',content=dict(type='component_source')),rect('slot','source'),instance('copy','source',overrides={'slot':dict(content=dict(type='image',asset_id='image',width=4,height=4))}),dict(id='text',transform=[1,0,0,1,8,8],content=dict(type='text',frame=frame))]
            destination=self.create();destination['assets']={'image':asset};destination['fonts']={'font':font};before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()};resources=dict(font_root=str(root/'fonts'),asset_root=str(root/'assets'))
            result=self.transfer(destination,source,['copy','text'],verify_resources=True,resources=resources);out=result['document'];details=result['changes'][0]['details']
            self.assertEqual(details['asset_ids'],dict(image='copy-image'));self.assertEqual(details['font_ids'],dict(font='copy-font'));self.assertEqual(len(out['assets']),2);self.assertEqual(len(out['fonts']),2)
            self.assertEqual(byid(out,'copy-text')['content']['frame']['ranges'][0]['style']['font_id'],'copy-font');self.assertEqual(byid(out,'copy-copy')['content']['instance']['overrides']['copy-slot']['content']['asset_id'],'copy-image')
            self.assertEqual(self.pixels(out,2,**resources),self.pixels(source,2,**resources));self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
            self.assertEqual(self.transfer(self.create(),source,['copy'],verify_resources=True,expected=1)['code'],'ASSET_ROOT_REQUIRED')
            self.assertEqual(self.transfer(self.create(),source,['text'],verify_resources=True,expected=1)['code'],'FONT_ROOT_REQUIRED')
            refs=self.transfer(self.create(),source,['text'])['document'];self.assertIn('copy-font',refs['fonts']);self.invoke(dict(command='document.export',document=refs,format='png'),1)
            self.assertEqual(self.edit(out,dict(op='font_remove',id='copy-font'),expected=1)['code'],'FONT_IN_USE');self.edit(out,dict(op='asset_remove',id='copy-image'),expected=1)

    def test_clipped_raster_layers_and_bound_adjustments_retain_dependency_closure(self):
        s=self.create('source','raster');s['items']=[group('layer'),dict(id='base',parent='layer',transform=[1,0,0,1,4,4],content=dict(type='fill',width=4,height=4,paint=[40,100,220,128])),dict(id='clip',parent='layer',clip_to='base',transform=[1,0,0,1,6,4],content=dict(type='fill',width=4,height=4,paint=[30,180,100,255])),dict(id='adjust',parent='layer',content=dict(type='adjustment',adjustment=dict(clip_to='clip',operators=[dict(type='invert')])))]
        out=self.transfer(self.create(kind='raster'),s,['adjust'])['document'];self.assertEqual(byid(out,'copy-clip')['clip_to'],'copy-base');self.assertEqual(byid(out,'copy-adjust')['content']['adjustment']['clip_to'],'copy-clip')
        w,h,p=self.pixels(out);self.assertEqual(p,bytes(v for y in range(h) for x in range(w) for v in ([225,75,155,128] if 6<=x<8 and 4<=y<8 else [40,100,220,128] if 4<=x<6 and 4<=y<8 else [0]*4)))
        self.assertEqual(self.pixels(s),(w,h,p));self.edit(out,dict(op='remove',id='copy-base'),expected=1)

    def test_selected_variants_copy_values_without_changing_destination_datasets(self):
        s=self.create('source');s['items']=[rect('shape')];definition=dict(bindings=[dict(key='position',item_id='shape',property='position')],datasets=dict(wide=dict(values=dict(position=dict(type='position',value=[12,8])))))
        source=self.edit(s,dict(op='variants_set',definition=definition),dict(op='variant_select',dataset='wide'))['document'];target=self.edit(s,dict(op='variants_set',definition=definition))['document'];retained=copy.deepcopy(target)
        result=self.transfer(target,source,['shape']);out=result['document'];self.assertEqual(out['variants'],target['variants']);self.assertEqual(result['changes'][0]['details']['source_variant'],'wide');self.assertEqual(byid(out,'copy-shape')['transform'],[1,0,0,1,12,8]);self.assertEqual(target,retained)
        changed=self.edit(out,dict(op='variant_select',dataset='wide'))['document'];self.assertEqual(byid(changed,'copy-shape'),byid(out,'copy-shape'))

    def test_global_lighting_is_pinned_and_destination_context_is_unchanged(self):
        s=self.create('source');s['global_light']=dict(azimuth=180);shape=rect('shape',x=10,y=10);shape['effects']=[dict(id='shadow',operator=dict(type='lit_shadow',distance=4,sigma=0),color=[0,0,0,255])];s['items']=[shape]
        d=self.create();d['global_light']=dict(azimuth=0);result=self.transfer(d,s,['shape']);out=result['document'];self.assertEqual(out['global_light'],d['global_light']);self.assertEqual(byid(out,'copy-shape')['effects'][0]['operator']['azimuth'],180)
        self.assertEqual(result['changes'][0]['details']['pinned_lighting'],[dict(item_id='copy-shape',effect_id='shadow')]);w,h,p=self.pixels(out)
        self.assertEqual(p,bytes(v for y in range(h) for x in range(w) for v in ([40,100,220,255] if 10<=x<14 and 10<=y<14 else [0,0,0,255] if 14<=x<18 and 10<=y<14 else [0]*4)))
        self.assertEqual(self.pixels(s),(w,h,p))

    def test_unlinked_masks_and_artboard_frames_keep_source_coordinates(self):
        s=self.create('source');item=rect('shape','board',width=12,height=12);item['mask']=dict(width=2,height=2,gray_hex='ff0000ff',transform=[4,0,0,4,4,4],linked=False)
        s['items']=[dict(id='board',transform=[1,0,0,1,4,4],content=dict(type='frame',frame=dict(role='artboard',width=16,height=16,guides=[dict(id='guide',axis='x',position=3)]))),item]
        d=self.create();d['items']=[group('parent',transform=[2,0,0,2,2,2])];out=self.transfer(d,s,['shape'],parent='parent')['document'];self.assertEqual(self.pixels(s,2),self.pixels(out,2));self.assertEqual(byid(out,'copy-shape')['mask']['transform'],item['mask']['transform'])
        a=self.invoke(dict(command='artboard.export',document=s,format='png'));b=self.invoke(dict(command='artboard.export',document=out,format='png'));self.assertEqual(a['artifacts'][0]['artifact']['data'],b['artifacts'][0]['artifact']['data']);self.assertEqual(byid(out,'copy-board')['content']['frame']['guides'][0]['id'],'guide')

    def test_long_ids_collisions_limits_invalid_sources_and_batches_fail_atomically(self):
        s=self.create('source');id='a'*128;s['items']=[rect(id)];prefix='b'*32;r=self.transfer(self.create(),s,[id],prefix);expected=prefix+'-'+hashlib.sha256(id.encode()).hexdigest();self.assertEqual(r['changes'][0]['details']['item_ids'][id],expected)
        out=r['document'];before=copy.deepcopy(out);self.assertEqual(self.transfer(out,s,[id],prefix,expected=1)['code'],'ID_CONFLICT')
        collision=copy.deepcopy(s);collision['items'].append(rect(hashlib.sha256(id.encode()).hexdigest()));self.assertEqual(self.transfer(self.create(),collision,[i['id'] for i in collision['items']],prefix,expected=1)['code'],'ID_CONFLICT')
        for ids,prefix in [([], 'ok'),([id,id],'ok'),(['missing'],'ok'),([id],'bad prefix'),([id],'x'*33)]:self.transfer(self.create(),s,ids,prefix,expected=1)
        bad=copy.deepcopy(s);bad['items'][0]['parent']='missing';self.transfer(self.create(),bad,[id],expected=1)
        full=self.create();full['items']=[rect('i'+str(i)) for i in range(256)];self.assertEqual(self.transfer(full,s,[id],expected=1)['code'],'RESOURCE_LIMIT')
        self.edit(self.create(),dict(op='transfer',transfer=dict(source=s,ids=[id],prefix='ok')),dict(op='remove',id='missing'),expected=1);self.assertEqual(out,before)
        locked=self.create();locked['items']=[dict(group('locked'),locked=True)];self.assertEqual(self.transfer(locked,s,[id],parent='locked',expected=1)['code'],'LOCKED')

    def test_reflected_sheared_parent_preserves_rational_bounds_and_fixed_strokes(self):
        source=self.create('source');matrix=[2,.5,-.5,1,14,6];source['items']=[group('root',transform=matrix),rect('shape','root',x=1,y=2,width=4,height=3)]
        byid(source,'shape')['content']['stroke']=dict(color=[30,180,100,255],width=2,scaling='document')
        parent=[-1,.5,1,1,30,4];destination=self.create();destination['items']=[group('parent',transform=parent)]
        out=self.transfer(destination,source,['shape'],parent='parent')['document'];wanted=list(map(float,matrix_product(inverse(parent),matrix)))
        for actual,expected in zip(byid(out,'copy-root')['transform'],wanted):self.assertAlmostEqual(actual,expected,places=12)
        inspected=self.inspect(out)['copy-shape'];self.assertEqual(inspected['world_transform'],matrix)
        corners=[point(matrix,p) for p in [(1,2),(5,2),(5,5),(1,5)]];self.assertEqual(inspected['geometry_bounds'],[min(p[0] for p in corners),min(p[1] for p in corners),max(p[0] for p in corners),max(p[1] for p in corners)])
        self.assertEqual(self.pixels(source,3),self.pixels(out,3))

    def test_resource_id_collisions_and_locked_target_definitions_fail_without_overwrite(self):
        source=self.components();destination=self.create();destination['items']=[dict(id='component',content=dict(type='component_source')),rect('body','component'),dict(instance('instance','component'),locked=True)]
        self.assertEqual(self.transfer(destination,source,['outer'],parent='component',expected=1)['code'],'LOCKED')
        source=self.create('source');pixels=bytes([40,100,220,255]);asset=dict(width=1,height=1,sha256=hashlib.sha256(b'INKRGBA1'+(1).to_bytes(4,'little')*2+pixels).hexdigest(),storage=dict(type='embedded',rgba_hex=pixels.hex()))
        source['assets']={'asset':asset};source['items']=[dict(id='image',content=dict(type='image',asset_id='asset',width=4,height=4))]
        destination=self.create();destination['assets']={'copy-asset':asset};before=copy.deepcopy(destination)
        self.assertEqual(self.transfer(destination,source,['image'],expected=1)['code'],'ID_CONFLICT');self.assertEqual(destination,before)
        wrong_kind=self.create(kind='raster');self.transfer(wrong_kind,self.nested(),['shape'],expected=1)

    def test_mcp_transfer_is_atomic_durable_replayable_and_source_preserving(self):
        source=self.nested();d=self.create();c=Client();self.addCleanup(c.close);c.initialize();op=dict(op='transfer',transfer=dict(source=source,ids=['shape'],prefix='saved'))
        expected=self.transfer(d,source,['shape'],'saved')['document']
        with tempfile.TemporaryDirectory() as directory:
            session=dict(session_root=directory,session_id='transfer');c.success('session.create',**session,request_id='create',document=d)
            args=dict(**session,request_id='copy',expected_revision=0,action=dict(type='edit',operations=[op]));result=c.success('session.apply',**args);self.assertEqual(result['document'],expected);self.assertTrue(c.success('session.apply',**args)['replayed'])
            undo=c.success('session.apply',**session,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'];self.assertEqual(undo['items'],[])
            redo=c.success('session.apply',**session,request_id='redo',expected_revision=2,action=dict(type='redo'))['document'];self.assertEqual(redo['items'],expected['items']);c.success('session.verify',**session)
            self.assertEqual(self.pixels(redo),self.pixels(expected));self.assertEqual(byid(source,'shape')['id'],'shape')


if __name__=='__main__':unittest.main()
