"""Independent rational compositing, hierarchy and persistent clipping-group tests."""
import base64
import copy
from fractions import Fraction as F
import json
import tempfile
import unittest
import test_editing_cli as editing
from test_mcp import Client


def layer(id, colors, width=None, **kw):
    width=width or len(colors)
    return dict(id=id,content=dict(type='raster',width=width,height=len(colors)//width,rgba_hex=bytes(c for p in colors for c in p).hex()),**kw)
def group(id,**kw):return dict(id=id,content=dict(type='group'),**kw)
def mask(values):return dict(width=len(values),height=1,gray_hex=bytes(values).hex())
def premul(rgba):
    a=F(rgba[3],255);return [F(c,255)*a for c in rgba[:3]]+[a]
def blend(a,b,mode):return b if mode=='normal' else a*b if mode=='multiply' else a+b-a*b
def atop(base,source,opacity=F(1),mode='normal'):
    a,s=base[3],source[3]*opacity
    if not a or not s:return base[:]
    return [((1-s)*base[c]/a+s*blend(base[c]/a,source[c]/source[3],mode))*a for c in range(3)]+[a]
def over(base,source,opacity=F(1),mode='normal'):
    a,s=base[3],source[3]*opacity
    if not s:return base[:]
    color=[source[c]/source[3] for c in range(3)]
    result=[]
    for c in range(3):
        mixed=blend(base[c]/a if a else F(0),color[c],mode)
        result.append((1-s)*base[c]+s*((1-a)*color[c]+a*mixed))
    return result+[s+a*(1-s)]
def encoded(pixel):
    if pixel[3]*255<F(1,2):return [F(0)]*4
    return [pixel[c]/pixel[3]*255 for c in range(3)]+[pixel[3]*255]


class LayerClippingTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def document(self,w=8,h=6,kind='raster'):
        return self.invoke(dict(command='document.create',id='layer-clipping',kind=kind,width=w,height=h))
    def edit(self,d,ops,expected=0):
        r=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=ops),expected)
        return r if expected else r['document']
    def add(self,d,items):return self.edit(d,[dict(op='add',item=i) for i in items])
    def pixels(self,d):
        r=self.invoke(dict(command='document.export',document=d,format='png'))
        return editing.png_pixels(base64.b64decode(r['data']))[2]
    def assert_pixels(self,actual,pixels):
        wanted=[v for p in pixels for v in encoded(p)]
        self.assertEqual(len(actual),len(wanted))
        for a,v in zip(actual,wanted):
            rounded=(v+F(1,2)).numerator//(v+F(1,2)).denominator
            if a!=rounded:
                # The declared f64 compositing contract permits either adjacent
                # byte at an exact rational half-byte tie, and nowhere else.
                self.assertEqual(v.denominator,2,(a,v));self.assertEqual(a,rounded-1,(a,v))

    def test_capability_discovery_matches_implemented_contracts(self):
        c=self.invoke(dict(command='capabilities'))
        self.assertTrue(c['paths']['simplify'])
        self.assertNotIn('curve_simplification',c['unsupported'])
        self.assertIn('layer_alpha_clipping',c['supported']['raster'])
        self.assertNotIn('ordinary_pixel_layer_alpha_clipping',c['unsupported'])
        self.assertNotIn('pass_through_group_effects',c['unsupported'])
        self.assertEqual(c['layer_clipping']['binding'],'contiguous_sibling_base_id')
        self.assertIn('pass_through_group_filters',c['unsupported'])

    def test_nested_hierarchy_rotation_and_visible_alpha_boundaries(self):
        alphas=[255,0,128,255,64,192];color=[201,30,90]
        items=[group('outer',transform=[1,0,0,1,2,1]),group('inner',parent='outer',transform=[0,1,-1,0,4,0]),
               layer('base',[[20,80,190,a] for a in alphas],width=2,parent='inner'),
               layer('texture',[color+[255]]*6,width=2,parent='inner',clip_to='base')]
        d=self.add(self.document(10,8),items);original=copy.deepcopy(d)
        expected=[]
        for y in range(8):
            for x in range(10):
                lx,ly=y-1,5-x
                a=alphas[ly*2+lx] if 0<=lx<2 and 0<=ly<3 else 0
                expected+=color+[a] if a else [0,0,0,0]
        self.assertEqual(self.pixels(d),bytes(expected));self.assertEqual(d,original)
        records=self.invoke(dict(command='document.inspect',document=d))['items']
        texture=next(i for i in records if i['id']=='texture')
        self.assertEqual(texture['clip_to'],'base');self.assertEqual(texture['world_transform'],[0,1,-1,0,6,1])
        saved=self.invoke(dict(command='document.export',document=d,format='snapshot'))
        self.assertEqual(self.invoke(dict(command='document.validate',document=json.loads(saved['data']))),d)

    def test_alpha_masks_opacity_and_blend_modes_apply_once(self):
        base=[[200,60,30,a] for a in (0,64,128,255)]
        source=[[30,170,220,a] for a in (255,128,64,127)]
        background=[[80,120,160,a] for a in (128,255,0,255)]
        bm,sm=[255,128,64,255],[128,255,128,0]
        for mode in ('normal','multiply','screen'):
            d=self.add(self.document(4,1),[
                layer('back',background),layer('base',base,opacity=.5,blend='multiply',mask=mask(bm)),
                layer('source',source,clip_to='base',opacity=.75,blend=mode,mask=mask(sm))])
            expected=[]
            for b,s,bg,bmask,smask in zip(base,source,background,bm,sm):
                clipped=atop(premul(b),premul(s),F(3,4)*F(smask,255),mode)
                expected.append(over(premul(bg),clipped,F(1,2)*F(bmask,255),'multiply'))
            self.assert_pixels(self.pixels(d),expected)

    def test_filtered_antialiased_base_retains_its_complete_alpha_field(self):
        base=layer('base',[[30,70,190,255]]*9,width=3,opacity=.5,transform=[1,.4,.2,1,2.25,1.25],filters=[dict(id='blur',operator=dict(type='box',radius=1))])
        d=self.add(self.document(12,10),[base]);before=self.pixels(d)
        clipped=self.add(d,[dict(id='texture',clip_to='base',content=dict(type='fill',width=12,height=10,paint=[220,90,30,255]))])
        after=self.pixels(clipped)
        self.assertEqual(after[3::4],before[3::4])
        self.assertGreater(len(set(before[3::4])),4)
        for offset in range(0,len(after),4):
            self.assertEqual(after[offset:offset+3],bytes([220,90,30]) if after[offset+3] else bytes(3))

    def test_stacked_sources_adjustments_order_and_nonprinting_paths(self):
        base=[40,90,140,128];a=[200,100,30,192];b=[20,210,70,96]
        adjust=lambda id,target:dict(id=id,content=dict(type='adjustment',adjustment=dict(clip_to=target,operators=[dict(type='invert')])))
        work=dict(id='path',content=dict(type='work_path',geometry=dict(shape='rect',x=0,y=0,width=1,height=1)))
        d=self.add(self.document(1,1),[layer('base',[base]),adjust('base-tone','base'),work,layer('a',[a],clip_to='base'),adjust('a-tone','a'),layer('b',[b],clip_to='base')])
        inverted=lambda c:[255-v for v in c[:3]]+[c[3]]
        expected=atop(atop(premul(inverted(base)),premul(inverted(a))),premul(b))
        self.assert_pixels(self.pixels(d),[expected])
        hidden=self.edit(d,[dict(op='properties',id='a',visible=False)])
        self.assert_pixels(self.pixels(hidden),[atop(premul(inverted(base)),premul(b))])
        # Disconnect the source's adjustment before changing sibling order.
        reordered=self.edit(d,[dict(op='remove',id='a-tone'),dict(op='reorder',id='b',index=3)])
        self.assert_pixels(self.pixels(reordered),[atop(atop(premul(inverted(base)),premul(b)),premul(a))])

    def test_hidden_base_and_clipped_container_visibility_in_discovery(self):
        d=self.add(self.document(2,1),[layer('base',[[100,20,40,255]]*2),group('source',clip_to='base'),layer('child',[[20,180,60,255]]*2,parent='source')])
        hidden=self.edit(d,[dict(op='properties',id='base',visible=False)])
        self.assertEqual(self.pixels(hidden),bytes(8))
        q=self.invoke(dict(command='document.query',document=hidden,query={}))
        self.assertEqual(q['ids'],[])
        all_items=self.invoke(dict(command='document.query',document=hidden,query=dict(visible_only=False)))['items']
        self.assertTrue(all(not i['effective_visible'] for i in all_items))
        source_hidden=self.edit(d,[dict(op='properties',id='source',visible=False)])
        self.assertEqual(self.pixels(source_hidden),bytes([100,20,40,255])*2)
        self.assertEqual(self.edit(d,[dict(op='ungroup',id='source')],1)['code'],'UNSUPPORTED')

    def test_isolated_base_group_union_and_transformed_clipped_group(self):
        d=self.add(self.document(6,4),[group('base'),
            layer('left',[[100,20,40,128]]*6,width=2,parent='base'),
            layer('right',[[20,50,180,128]]*6,width=2,parent='base',transform=[1,0,0,1,1,1]),
            group('texture',clip_to='base',transform=[1,0,0,1,1,0]),
            layer('ink',[[10,210,70,255]]*16,width=4,parent='texture')])
        expected=[]
        for y in range(4):
            for x in range(6):
                first=premul([100,20,40,128]) if x<2 and y<3 else [F(0)]*4
                second=premul([20,50,180,128]) if 1<=x<3 and 1<=y<4 else [F(0)]*4
                base=over(first,second)
                expected.append(atop(base,premul([10,210,70,255])) if 1<=x<5 else base)
        self.assert_pixels(self.pixels(d),expected)

    def test_pass_through_group_opacity_masks_and_clips_interpolate_backdrop(self):
        bg=[100,150,200,192];base=[200,100,50,128];src=[20,210,80,128]
        for isolated in (False,True):
            g=group('group',opacity=.5,mask=mask([255,128,0,255]),clip=dict(geometry=dict(shape='rect',x=1,y=0,width=3,height=1)))
            g['content']['isolated']=isolated
            d=self.add(self.document(4,1),[layer('back',[bg]*4),g,layer('base',[base]*4,parent='group',blend='multiply'),layer('src',[src]*4,parent='group',clip_to='base')])
            clipped=atop(premul(base),premul(src))
            expected=[]
            for x,m in enumerate([255,128,0,255]):
                weight=F(1,2)*F(m,255) if x>=1 else F(0)
                before=premul(bg)
                if isolated:expected.append(over(before,over([F(0)]*4,clipped,mode='multiply'),weight))
                else:
                    after=over(before,clipped,mode='multiply')
                    expected.append([a+(b-a)*weight for a,b in zip(before,after)])
            self.assert_pixels(self.pixels(d),expected)

    def test_pass_through_backdrop_adjustment_preserves_alpha_and_outside_pixels(self):
        colors=[[20,100,210,a] for a in (64,128,192,255)]
        g=group('group',opacity=.25,clip=dict(geometry=dict(shape='rect',x=1,y=0,width=2,height=1)))
        g['content']['isolated']=False
        d=self.add(self.document(4,1),[layer('back',colors),g,dict(id='invert',parent='group',content=dict(type='adjustment',adjustment=dict(operators=[dict(type='invert')])) )])
        expected=[]
        for x,c in enumerate(colors):
            old=premul(c);new=premul([255-v for v in c[:3]]+[c[3]])
            expected.append([a+(b-a)/4 for a,b in zip(old,new)] if 1<=x<3 else old)
        self.assert_pixels(self.pixels(d),expected)

    def test_duplicate_group_remaps_references_and_edits_preserve_originals(self):
        d=self.add(self.document(4,2),[group('group'),layer('base',[[90,30,50,128]]*4,width=2,parent='group'),layer('source',[[10,190,60,255]]*4,width=2,parent='group',clip_to='base')])
        original=copy.deepcopy(d)
        copy_d=self.edit(d,[dict(op='duplicate',id='group',new_id='copy',descendant_ids={'base':'base-copy','source':'source-copy'}),dict(op='transform',id='copy',matrix=[1,0,0,1,2,0])])
        source=next(i for i in copy_d['items'] if i['id']=='source-copy')
        self.assertEqual(source['clip_to'],'base-copy');self.assertEqual(d,original)
        self.assertEqual(self.pixels(copy_d),bytes([10,190,60,128])*8)
        changed=self.edit(copy_d,[dict(op='layer_clip',id='source-copy',clip_to=None),dict(op='remove',id='base-copy')])
        expected=bytes([10,190,60,128])*2+bytes([10,190,60,255])*2
        self.assertEqual(self.pixels(changed),expected*2)

    def test_standalone_artboard_excludes_external_clipping_membership(self):
        d=self.add(self.document(8,4),[
            layer('base',[[100,20,40,255]]*4,width=1,transform=[1,0,0,1,3,0]),
            dict(id='board',clip_to='base',transform=[1,0,0,1,3,1],content=dict(type='frame',frame=dict(role='artboard',width=2,height=2))),
            layer('art',[[20,180,60,255]]*4,width=2,parent='board')])
        original=copy.deepcopy(d)
        exported=self.invoke(dict(command='artboard.export',document=d,format='png'))
        artifact=exported['artifacts'][0]['artifact'];w,h,pixels,_=editing.png_pixels(base64.b64decode(artifact['data']))
        self.assertEqual((w,h),(2,2));self.assertEqual(pixels,bytes([20,180,60,255])*4)
        self.assertEqual(d,original)

    def test_mcp_session_clipping_undo_retry_reopen_and_diff(self):
        c=Client();self.addCleanup(c.close);c.initialize()
        d=self.add(self.document(2,1),[layer('base',[[90,30,50,128],[90,30,50,0]]),layer('source',[[10,190,60,255]]*2)])
        with tempfile.TemporaryDirectory() as root:
            args=dict(session_root=root,session_id='clipping')
            c.success('session.create',**args,request_id='create',document=d)
            action=dict(type='edit',operations=[dict(op='layer_clip',id='source',clip_to='base')])
            changed=c.success('session.apply',**args,request_id='clip',expected_revision=0,action=action)['document']
            self.assertEqual(self.pixels(changed),bytes([10,190,60,128,0,0,0,0]))
            self.assertEqual(self.invoke(dict(command='session.read',**args))['document'],changed)
            c.success('session.apply',**args,request_id='snapshot',expected_revision=1,action=dict(type='snapshot',name='clipped'))
            undo=c.success('session.apply',**args,request_id='undo',expected_revision=2,action=dict(type='undo'))['document']
            self.assertEqual(undo['items'],d['items'])
            redo=c.success('session.apply',**args,request_id='redo',expected_revision=3,action=dict(type='redo'))['document']
            self.assertEqual(redo['items'],changed['items'])
            replay=c.success('session.apply',**args,request_id='clip',expected_revision=0,action=action)
            self.assertEqual(replay['document'],changed);self.assertEqual(replay['current_revision'],4)
            diff=c.success('session.diff',**args,from_revision=0,to_revision=1,compare_pixels=True)
            self.assertIn('clip_to',next(i for i in diff['items'] if i['id']=='source')['fields'])
            self.assertEqual(diff['rendered_pixels']['changed_pixels'],2)
            self.assertEqual(c.success('session.read',**args,snapshot='clipped')['document']['items'],changed['items'])
            c.success('session.verify',**args)

    def test_invalid_references_locking_atomicity_and_buffer_limits(self):
        d=self.add(self.document(2,1),[layer('base',[[90,30,50,128]]*2),layer('source',[[10,190,60,255]]*2,clip_to='base')]);original=copy.deepcopy(d)
        for op in [dict(op='remove',id='base'),dict(op='reorder',id='base',index=1),dict(op='layer_clip',id='base',clip_to='source'),dict(op='layer_clip',id='source',clip_to='missing')]:
            error=self.edit(d,[dict(op='properties',id='source',name='pending'),op],1)
            self.assertEqual(error['code'],'INVALID_DOCUMENT');self.assertEqual(error['operation_index'],1)
        self.assertEqual(d,original)
        locked=self.edit(d,[dict(op='properties',id='source',locked=True)])
        self.assertEqual(self.edit(locked,[dict(op='layer_clip',id='source',clip_to=None)],1)['code'],'LOCKED')
        passthrough=group('pass');passthrough['content']['isolated']=False
        bad=self.add(self.document(2,1),[passthrough,layer('source',[[10,190,60,255]]*2)])
        self.assertEqual(self.edit(bad,[dict(op='layer_clip',id='source',clip_to='pass')],1)['code'],'INVALID_DOCUMENT')
        bad=self.add(self.document(2,1),[layer('base',[[90,30,50,128]]*2),dict(passthrough,clip_to=None)])
        self.assertEqual(self.edit(bad,[dict(op='layer_clip',id='pass',clip_to='base')],1)['code'],'UNSUPPORTED')
        deep=self.document(1024,512)
        deep=self.add(deep,[group('a'),group('b',parent='a'),group('c',parent='b'),dict(id='base',parent='c',content=dict(type='fill',width=1024,height=512,paint=[20,60,190,255])),dict(id='source',parent='c',clip_to='base',content=dict(type='fill',width=1024,height=512,paint=[200,40,80,255]))])
        self.assertEqual(self.invoke(dict(command='document.render',document=deep),1)['code'],'RESOURCE_LIMIT')


if __name__=='__main__':unittest.main()
