"""Original rational, geometric, XML and durable-history artwork mask fixtures."""
import base64
import copy
from fractions import Fraction as F
import json
from pathlib import Path
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
import test_editing_cli as editing
from test_masks_cli import byte, inverse
from test_layout_cli import local_point, shape_contains
from test_layer_clipping_cli import premul, over, atop, encoded, layer
from test_mcp import Client
from synthetic_font import geometric_font

NS = '{http://www.w3.org/2000/svg}'
WHITE = [255,255,255,255]
INK = [31,147,219,255]


def rect(id, x=0, y=0, w=12, h=8, color=None, **kw):
    return dict(id=id,content=dict(type='vector',geometry=dict(shape='rect',x=x,y=y,width=w,height=h),fill=WHITE if color is None else color),**kw)


def source(**kw):return dict(id='source',content=dict(type='mask_source'),**kw)
def mask(**kw):return dict(source='source',region=[0,0,12,8],**kw)
def group(id, **kw):return dict(id=id,content=dict(type='group'),**kw)


def svg_pixel(root, point):
    """Evaluate the rectangular normal-blend SVG fixture independently of JSON."""
    definitions={e.get('id'):e for e in root.iter() if e.get('id')}
    def ref(value):return definitions[re.fullmatch(r'url\(#([^)]+)\)',value)[1]]
    def visit(e,p):
        if e.get('display')=='none':return [F(0)]*4
        p=local_point(e,p)
        if e.tag in (NS+'g',NS+'svg',NS+'mask'):
            rgba=[F(0)]*4
            for child in e:
                if child.tag!=NS+'defs':rgba=over(rgba,visit(child,p))
        elif e.tag==NS+'rect':
            if not shape_contains(e,p) or e.get('fill')=='none':return [F(0)]*4
            fill=e.get('fill')
            rgb=list(bytes.fromhex(fill[1:])) if fill.startswith('#') else list(map(int,re.fullmatch(r'rgb\((\d+),(\d+),(\d+)\)',fill).groups()))
            a=F(e.get('fill-opacity','1'));rgba=[F(c,255)*a for c in rgb]+[a]
        else:return [F(0)]*4
        weight=F(e.get('opacity','1'))
        if e.get('clip-path') and not any(shape_contains(c,p) for c in ref(e.get('clip-path'))):weight=F(0)
        if e.get('mask'):
            m=ref(e.get('mask'));v=visit(m,p)
            weight*=v[3] if m.get('mask-type')=='alpha' else sum(v[c]*vcoeff for c,vcoeff in enumerate([F(2125,10000),F(7154,10000),F(721,10000)]))
        return [c*weight for c in rgba]
    return [int(v+F(1,2)) for v in encoded(visit(root,point))]


class ArtworkMaskTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke

    def document(self,items=(),kind='vector',width=12,height=8):
        d=self.invoke(dict(command='document.create',id='artwork-masks',kind=kind,width=width,height=height))
        return self.edit(d,[dict(op='add',item=i) for i in items]) if items else d

    def edit(self,d,ops,expected=0,**kw):
        r=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=ops,**kw),expected)
        return r if expected else r['document']

    def pixels(self,d,scale=1,**kw):
        r=self.invoke(dict(command='document.export',document=d,format='png',scale=scale,**kw))
        w,h,p,_=editing.png_pixels(base64.b64decode(r['data']))
        preview=self.invoke(dict(command='document.render',document=d,scale=scale,**kw))
        self.assertEqual(bytes.fromhex(preview['data']),p)
        return w,h,p

    def assert_alpha(self,d,oracle,scale=1,**kw):
        w,h,p=self.pixels(d,scale,**kw)
        for y in range(h):
            for x in range(w):
                a=byte(oracle((x+.5)/scale,(y+.5)/scale))
                self.assertEqual(p[(y*w+x)*4+3],a,(x,y,a))
                if not a:self.assertEqual(p[(y*w+x)*4:][:4],bytes(4))

    def test_alpha_and_luminance_overlaps_keep_float_precision_and_source_nonprinting(self):
        colors=[[200,40,90,83],[30,180,220,137]]
        for kind in ('vector','raster'):
            for mode in ('alpha','luminance'):
                owner=rect('ink',color=INK,artwork_mask=mask(mode=mode),opacity=.7) if kind=='vector' else layer('ink',[INK]*96,width=12,artwork_mask=mask(mode=mode),opacity=.7)
                d=self.document([source(opacity=.6),rect('a',w=8,color=colors[0],parent='source'),rect('b',x=4,color=colors[1],parent='source',opacity=.4),owner],kind)
                def expected(x,y):
                    v=premul(colors[0]) if x<8 else [F(0)]*4
                    if x>=4:v=over(v,premul(colors[1]),F(2,5))
                    a=v[3] if mode=='alpha' else sum(v[c]*coef for c,coef in enumerate([F(2125,10000),F(7154,10000),F(721,10000)]))
                    return float(a*F(3,5)*F(7,10))
                for scale in (1,2,3):self.assert_alpha(d,expected,scale)
                without=self.edit(d,[dict(op='remove',id='ink')]);self.assert_alpha(without,lambda x,y:0)
                self.assertEqual(self.invoke(dict(command='document.query',document=d,query={}))['ids'],['ink'])
                all_items=self.invoke(dict(command='document.query',document=d,query=dict(visible_only=False)))['items']
                self.assertEqual({v['id'] for v in all_items},{'source','a','b','ink'})
                self.assertEqual(next(v for v in all_items if v['id']=='source')['geometry_bounds'],None)

    def test_source_gradient_nested_clip_and_owner_clip_at_three_scales(self):
        gradient=dict(type='linear',start=[0,0],end=[12,0],stops=[dict(offset=0,color=[255,0,0,0]),dict(offset=1,color=[255,0,0,255])])
        clip=lambda x,w:dict(geometry=dict(shape='rect',x=x,y=1,width=w,height=6))
        d=self.document([source(clip=clip(1,10)),group('g',parent='source',opacity=.5,clip=clip(2,8)),rect('r',parent='g',color=gradient),rect('ink',artwork_mask=mask(mode='luminance'),clip=clip(3,6))])
        for scale in (1,2,3):self.assert_alpha(d,lambda x,y:.2125*.5*x/12 if 3<=x<9 and 1<=y<7 else 0,scale)
        revised=self.edit(d,[dict(op='properties',id='g',opacity=.8)])
        self.assert_alpha(revised,lambda x,y:.2125*.8*x/12 if 3<=x<9 and 1<=y<7 else 0)

    def test_shared_edits_diff_dependency_hash_snapshot_and_reference_removal(self):
        d=self.document([source(),rect('r',w=4,parent='source'),rect('left',w=6,artwork_mask=mask()),rect('right',w=6,transform=[1,0,0,1,6,0],artwork_mask=mask())])
        original=copy.deepcopy(d)
        revised=self.edit(d,[dict(op='properties',id='r',opacity=.25)])
        self.assert_alpha(revised,lambda x,y:.25 if x<4 or 6<=x<10 else 0)
        diff=self.invoke(dict(command='document.diff',before=d,after=revised,compare_pixels=True))
        entries={v['id']:v for v in diff['items']}
        for id in ('left','right'):self.assertIn('derived.artwork_mask_source_sha256',entries[id]['fields'])
        saved=self.invoke(dict(command='document.export',document=revised,format='snapshot'))
        restored=self.invoke(dict(command='document.validate',document=json.loads(saved['data'])))
        self.assertEqual(restored,revised);self.assertEqual(self.pixels(restored),self.pixels(revised))
        error=self.edit(d,[dict(op='properties',id='left',name='candidate'),dict(op='remove',id='source')],1)
        self.assertEqual(error['operation_index'],1);self.assertEqual(error['code'],'INVALID_DOCUMENT')
        detached=self.edit(d,[dict(op='artwork_mask',id=i,mask=None) for i in ('left','right')]+[dict(op='remove',id='source')])
        self.assertEqual({i['id'] for i in detached['items']},{'left','right'});self.assertEqual(d,original)

    def test_locks_protect_shared_dependents_even_disabled_masks_and_added_children(self):
        d=self.document([source(),rect('r',parent='source'),group('g',artwork_mask=mask()),rect('ink',parent='g')])
        for locked_id in ('g','ink'):
            for enabled in (True,False):
                locked=self.edit(d,[dict(op='artwork_mask',id='g',mask=mask(enabled=enabled)),dict(op='properties',id=locked_id,locked=True)])
                for op in (dict(op='properties',id='r',opacity=.5),dict(op='transform',id='source',matrix=[1,0,0,1,1,0]),dict(op='remove',id='r'),dict(op='add',item=rect('extra',parent='source')),dict(op='reparent',id='r',parent=None)):
                    self.assertEqual(self.edit(locked,[op],1)['code'],'LOCKED')
                query=self.invoke(dict(command='document.query',document=locked,query=dict(visible_only=False)))
                self.assertNotIn('r',query['ids']);self.assertNotIn('source',query['ids'])
        ancestor=self.edit(d,[dict(op='group',ids=['g'],new_id='outer'),dict(op='properties',id='outer',locked=True)])
        self.assertEqual(self.edit(ancestor,[dict(op='properties',id='r',visible=False)],1)['code'],'LOCKED')

    def test_link_switch_world_local_transforms_and_region_coordinates(self):
        d=self.document([source(),rect('r',w=2,h=2,parent='source'),group('g',transform=[2,0,0,2,2,2]),rect('ink',parent='g',artwork_mask=mask(region_transform=[1,0,0,1,1,0]))],width=16,height=12)
        self.assert_alpha(d,lambda x,y:1 if 4<=x<6 and 2<=y<6 else 0)
        unlinked=self.edit(d,[dict(op='artwork_mask_link',id='ink',linked=False)])
        self.assertEqual(self.pixels(unlinked),self.pixels(d))
        linked=self.edit(unlinked,[dict(op='artwork_mask_link',id='ink',linked=True)])
        self.assertEqual(self.pixels(linked),self.pixels(d))
        local=self.edit(d,[dict(op='artwork_mask_transform',id='ink',space='local',matrix=[1,0,0,1,1,0])])
        world=self.edit(d,[dict(op='artwork_mask_transform',id='ink',space='world',matrix=[1,0,0,1,2,0])])
        self.assertEqual(self.pixels(local),self.pixels(world));self.assert_alpha(local,lambda x,y:1 if 6<=x<8 and 2<=y<6 else 0)
        moved=self.edit(unlinked,[dict(op='transform',id='g',space='world',matrix=[1,0,0,1,-1,0])]);self.assertEqual(self.pixels(moved),self.pixels(d))
        empty=self.edit(d,[dict(op='artwork_mask',id='ink',mask=dict(mask(),region=[2,1,0,2]))]);self.assert_alpha(empty,lambda x,y:0)
        off=self.edit(empty,[dict(op='artwork_mask',id='ink',mask=dict(mask(),region=[2,1,0,2],enabled=False))]);self.assert_alpha(off,lambda x,y:1 if x>=2 and y>=2 else 0)
        # A reflected quarter-turn keeps integer edges: independent inverse membership.
        m=[0,1,1,0,3,4]
        rotated=self.edit(d,[dict(op='artwork_mask',id='ink',mask=dict(mask(),region=[0,0,2,2],linked=False,transform=m))])
        self.assert_alpha(rotated,lambda x,y:int(all(0<=v<2 for v in inverse(m,(x,y)))))

    def test_fractional_region_area_and_zero_extent_are_resolution_independent(self):
        d=self.document([source(),rect('r',parent='source'),rect('ink',artwork_mask=dict(mask(),region=[1.25,2.25,4.5,2.5]))])
        for scale in (1,2,4):
            w,h,p=self.pixels(d,scale)
            area=sum(p[3::4])/255/scale**2
            self.assertLess(abs(area-11.25),.04)
            for y in range(h):
                for x in range(w):
                    overlap=max(0,min((x+1)/scale,5.75)-max(x/scale,1.25))*max(0,min((y+1)/scale,4.75)-max(y/scale,2.25))*scale**2
                    self.assertLessEqual(abs(p[(y*w+x)*4+3]-byte(overlap)),1)

    def test_duplicate_reference_and_source_reparent_ungroup_keep_world_placement(self):
        d=self.document([source(),rect('r',w=3,parent='source'),group('g',transform=[1,0,0,1,2,0]),rect('ink',parent='g',artwork_mask=mask())])
        released=self.edit(d,[dict(op='ungroup',id='g')]);self.assertEqual(self.pixels(d),self.pixels(released))
        reparent=self.edit(d,[dict(op='reparent',id='ink',parent=None)]);self.assertEqual(self.pixels(d),self.pixels(reparent))
        duplicated=self.edit(d,[dict(op='duplicate',id='ink',new_id='ink-copy')]);self.assertEqual(next(i for i in duplicated['items'] if i['id']=='ink-copy')['artwork_mask']['source'],'source')
        independent=self.edit(d,[dict(op='duplicate',id='source',new_id='copy',descendant_ids={'r':'copy-r'}),dict(op='properties',id='copy-r',opacity=.2)])
        self.assertEqual(self.pixels(independent),self.pixels(d))
        masked=self.edit(d,[dict(op='artwork_mask',id='g',mask=mask())])
        self.assertEqual(self.edit(masked,[dict(op='ungroup',id='g')],1)['code'],'UNSUPPORTED')

    def test_artboard_bleed_retains_sources_and_rebases_owner_masks(self):
        board=dict(id='board',transform=[2,0,0,2,4,2],content=dict(type='frame',frame=dict(role='artboard',width=8,height=6,bleed=dict(left=1,top=2))))
        d=self.document([source(),rect('r',w=2,h=2,parent='source'),board,rect('ink',parent='board',w=8,h=6,artwork_mask=mask(linked=False,transform=[2,0,0,2,8,6]))],width=24,height=20)
        original=copy.deepcopy(d)
        for bleed in (False,True):
            r=self.invoke(dict(command='artboard.export',document=d,format='png',include_bleed=bleed))['artifacts'][0]['artifact']
            w,h,p,_=editing.png_pixels(base64.b64decode(r['data']));left,top=(3,4) if bleed else (2,2)
            for y in range(h):
                for x in range(w):self.assertEqual(p[(y*w+x)*4+3],255 if left<=x<left+2 and top<=y<top+2 else 0)
        own=self.edit(d,[dict(op='artwork_mask',id='ink',mask=None),dict(op='artwork_mask',id='board',mask=mask())])
        r=self.invoke(dict(command='artboard.export',document=own,format='png',include_bleed=True))['artifacts'][0]['artifact']
        w,h,p,_=editing.png_pixels(base64.b64decode(r['data']))
        for y in range(h):
            for x in range(w):self.assertEqual(p[(y*w+x)*4+3],255 if 1<=x<3 and 2<=y<4 else 0)
        self.assertEqual(d,original)

    def test_svg_copies_unique_ids_alpha_luminance_transforms_and_independent_pixels(self):
        for mode in ('alpha','luminance'):
            d=self.document([source(opacity=.75),rect('region',w=4,h=5,parent='source',color=[210,50,100,180]),rect('inkbolt-artmask-2-region',artwork_mask=mask(mode=mode,transform=[1,0,0,1,1,1])),rect('right',w=5,h=8,transform=[1,0,0,1,6,0],artwork_mask=mask(mode=mode))])
            result=self.invoke(dict(command='document.export',document=d,format='svg'))
            root=ET.fromstring(result['data']);ids=[e.get('id') for e in root.iter() if e.get('id')]
            self.assertEqual(len(ids),len(set(ids)))
            masks=list(root.iter(NS+'mask'));self.assertEqual(len(masks),2)
            for m in masks:self.assertEqual(m.get('mask-type'),mode);self.assertEqual(m.get('color-interpolation'),'sRGB')
            w,h,p=self.pixels(d)
            for y in range(h):
                for x in range(w):
                    expected=svg_pixel(root,(x+.5,y+.5));actual=list(p[(y*w+x)*4:][:4])
                    self.assertTrue(all(abs(a-b)<=1 for a,b in zip(actual,expected)),(x,y,actual,expected))
            self.assertTrue(any('shared editing identity' in loss for loss in result['losses']))

    def test_source_text_preserves_pinned_editability_and_exact_rectangular_glyph_pixels(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=root/'original.ttf';path.write_bytes(geometric_font());lic=root/'LICENSE';lic.write_bytes((Path(__file__).resolve().parents[1]/'LICENSE').read_bytes());store=root/'fonts'
            font=self.invoke(dict(command='font.import',source_path=str(path),license_path=str(lic),store_root=str(store)))
            d=self.document();d['fonts']={'geometry':font}
            text=dict(id='label',parent='source',content=dict(type='text',frame=dict(text='AA',width=12,height=10,overflow='visible',style=dict(font_id='geometry',size=10,fill=WHITE))))
            d=self.edit(d,[dict(op='add',item=i) for i in [source(),text,rect('ink',artwork_mask=mask())]],font_root=str(store))
            w,h,p=self.pixels(d,2,font_root=str(store))
            for y in range(h):
                for x in range(w):self.assertEqual(p[(y*w+x)*4+3],255 if 2<=y<16 and (1<=x<9 or 13<=x<21) else 0)
            changed=self.edit(d,[dict(op='text_range',id='label',start=0,end=2,text='A')],font_root=str(store))
            self.assertNotEqual(self.pixels(changed,font_root=str(store)),self.pixels(d,font_root=str(store)))
            self.assertEqual(next(i for i in d['items'] if i['id']=='label')['content']['type'],'text')
            svg=self.invoke(dict(command='document.export',document=d,format='svg',font_root=str(store)))
            self.assertEqual(len(list(ET.fromstring(svg['data']).iter(NS+'path'))),2)
            self.assertEqual(path.read_bytes(),geometric_font())
            self.assertEqual(self.invoke(dict(command='document.render',document=d),1)['code'],'FONT_ROOT_REQUIRED')

    def test_raster_clipping_and_pass_through_masks_match_rational_composition(self):
        base=[60,90,120,128];top=[210,30,40,192];back=[20,40,80,255]
        items=[source(),rect('r',parent='source',color=[255,255,255,128]),layer('back',[back]*4),group('g',artwork_mask=mask(),opacity=.6),layer('base',[base]*4,parent='g'),layer('top',[top]*4,parent='g',clip_to='base',artwork_mask=mask())]
        d=self.document(items,'raster',width=4,height=1)
        inner=atop(premul(base),premul(top),F(128,255));expected=over(premul(back),inner,F(128,255)*F(3,5))
        actual=self.pixels(d)[2][:4]
        self.assertTrue(all(abs(F(a)-b)<=F(1,2) for a,b in zip(actual,encoded(expected))))
        passthrough=self.edit(d,[dict(op='group_options',id='g',isolated=False)])
        after=over(premul(back),inner);weight=F(128,255)*F(3,5);expected=[b+(a-b)*weight for a,b in zip(after,premul(back))]
        actual=self.pixels(passthrough)[2][:4];self.assertTrue(all(abs(F(a)-b)<=F(1,2) for a,b in zip(actual,encoded(expected))))

    def test_invalid_references_source_semantics_and_resource_budgets_fail_atomically(self):
        d=self.document([source(),rect('r',parent='source'),rect('ink',artwork_mask=mask())]);original=copy.deepcopy(d)
        for m,code in ((dict(mask(),source='absent'),'INVALID_DOCUMENT'),(dict(mask(),source='ink'),'INVALID_DOCUMENT'),(dict(mask(),region=[0,0,-1,2]),'INVALID_DOCUMENT'),(dict(mask(),transform=[0,0,0,0,0,0]),'UNSUPPORTED')):
            error=self.edit(d,[dict(op='properties',id='ink',name='candidate'),dict(op='artwork_mask',id='ink',mask=dict(m,enabled=False))],1)
            self.assertEqual(error['code'],code);self.assertEqual(error['operation_index'],1)
        for op in (dict(op='artwork_mask',id='r',mask=mask()),dict(op='mask',id='ink',mask=dict(width=1,height=1,gray_hex='ff')),dict(op='properties',id='r',blend='multiply'),dict(op='add',item=dict(id='pass',parent='source',content=dict(type='group',isolated=False)))):
            self.assertEqual(self.edit(d,[op],1)['code'],'UNSUPPORTED')
        large=copy.deepcopy(d);large['items']=[source(),rect('r',parent='source')]+[rect(f'v{i}',artwork_mask=mask()) for i in range(33)]
        self.assertEqual(self.invoke(dict(command='document.validate',document=large),1)['code'],'RESOURCE_LIMIT')
        large['items']=large['items'][:4];large['width']=1024;large['height']=1024
        self.assertEqual(self.invoke(dict(command='document.render',document=large),1)['code'],'RESOURCE_LIMIT')
        copies=copy.deepcopy(d);copies['items']=[source()]+[rect(f'r{i}',parent='source') for i in range(150)]+[rect(f'v{i}',artwork_mask=mask()) for i in range(32)]
        self.assertEqual(self.invoke(dict(command='document.export',document=copies,format='svg'),1)['code'],'RESOURCE_LIMIT')
        self.assertEqual(d,original)

    def test_adjustments_skip_resource_roots_and_nested_masks_attenuate_once(self):
        color=[30,90,180,160]
        # A resource between a base and its bound correction must not break the chain.
        correction=dict(id='correction',artwork_mask=mask(),opacity=.5,content=dict(type='adjustment',adjustment=dict(operators=[dict(type='invert')],clip_to='base')))
        d=self.document([layer('base',[color]*4),source(),rect('r',w=2,parent='source',opacity=.5),correction],'raster',width=4,height=1)
        w,h,p=self.pixels(d)
        for x in range(w):
            expected=[byte(c/255+(1-2*c/255)*.25) if x<2 else c for c in color[:3]]+[160]
            self.assertEqual(list(p[x*4:][:4]),expected)
        backdrop=self.edit(d,[dict(op='adjustment',id='correction',adjustment=dict(operators=[dict(type='invert')]))])
        self.assertEqual(self.pixels(backdrop),self.pixels(d))
        nested=self.document([source(opacity=.5),rect('r',parent='source'),group('outer',artwork_mask=mask(),opacity=.7),group('inner',parent='outer',artwork_mask=mask(),opacity=.6),rect('ink',parent='inner',artwork_mask=mask(),opacity=.4)])
        self.assert_alpha(nested,lambda x,y:.5**3*.7*.6*.4)

    def test_unused_hidden_and_transformed_sources_keep_explicit_validation(self):
        d=self.document([source(),rect('r',parent='source'),rect('ink',artwork_mask=mask())])
        hidden=self.edit(d,[dict(op='properties',id='source',visible=False)]);self.assert_alpha(hidden,lambda x,y:0)
        # A source may not become a nested resource, and vector content stays auxiliary in raster documents.
        error=self.edit(d,[dict(op='group',ids=['source'],new_id='invalid')],1);self.assertEqual(error['code'],'INVALID_DOCUMENT')
        raster=self.document([source(),rect('r',parent='source')],'raster')
        self.assertEqual(self.edit(raster,[dict(op='reparent',id='r',parent=None)],1)['code'],'INVALID_DOCUMENT')
        excessive=self.edit(d,[dict(op='artwork_mask',id='ink',mask=dict(mask(),region=[0,0,0,0],transform=[10000,0,0,1,0,0]))])
        self.assertEqual(self.invoke(dict(command='document.render',document=excessive),1)['code'],'RESOURCE_LIMIT')

    def test_capabilities_and_strict_schema_disclose_native_mask_contract(self):
        caps=self.invoke(dict(command='capabilities'))
        self.assertEqual(caps['artwork_masks']['modes'],['alpha','luminance'])
        self.assertEqual(caps['limits']['artwork_mask_references'],32)
        self.assertEqual(caps['limits']['artwork_mask_coverage_pixels'],1048576)
        self.assertTrue(caps['artwork_masks']['svg_import'])
        self.assertEqual(caps['artwork_masks']['luminance_coefficients'],[.2125,.7154,.0721])
        d=self.document([source(),rect('r',parent='source'),rect('ink')])
        bad=self.edit(d,[dict(op='artwork_mask',id='ink',mask=dict(mask(),unsupported=True))],1)
        self.assertEqual(bad['code'],'INVALID_REQUEST')

    def test_mcp_session_retry_reopen_and_undo_restore_shared_mask_sources(self):
        d=self.document([source(),rect('r',w=4,parent='source'),rect('ink',artwork_mask=mask())]);before=self.pixels(d)
        with tempfile.TemporaryDirectory() as root:
            params=dict(session_root=root,session_id='artwork-mask')
            client=Client();client.initialize()
            try:
                client.success('session.create',**params,request_id='create',document=d)
                action=dict(type='edit',operations=[dict(op='properties',id='r',opacity=.3),dict(op='artwork_mask_link',id='ink',linked=False)])
                changed=client.success('session.apply',**params,expected_revision=0,request_id='change',action=action)
                after=self.pixels(changed['document']);self.assertNotEqual(after,before)
            finally:client.close()
            client=Client();client.initialize()
            try:
                replay=client.success('session.apply',**params,expected_revision=0,request_id='change',action=action);self.assertEqual(replay['document'],changed['document'])
                undo=client.success('session.apply',**params,expected_revision=1,request_id='undo',action=dict(type='undo'));self.assertEqual(self.pixels(undo['document']),before)
                redo=client.success('session.apply',**params,expected_revision=2,request_id='redo',action=dict(type='redo'));self.assertEqual(self.pixels(redo['document']),after)
                client.success('session.verify',**params)
            finally:client.close()


if __name__=='__main__':unittest.main()
