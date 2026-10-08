"""Independent scalar coverage, convolution, affine coordinates, XML and history checks."""
import base64
import copy
import json
import math
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
import test_editing_cli as editing
from test_layout_cli import local_point, shape_contains
from test_mcp import Client

NS = '{http://www.w3.org/2000/svg}'


def byte(v):
    return max(0, min(255, math.floor(v*255+0.5)))


def inverse(matrix, p):
    a,b,c,d,e,f = matrix
    x,y = p[0]-e,p[1]-f
    det = a*d-b*c
    return ((d*x-c*y)/det, (a*y-b*x)/det)


def opacity(mask, p):
    """Direct 2D convolution of an infinite discrete field, then reconstruction."""
    if not mask.get('enabled', True):
        return 1.0
    w,h = mask['width'], mask['height']
    gray = bytes.fromhex(mask['gray_hex'])
    outside = 0 if mask.get('clip',True) else 1
    r = mask.get('feather',0)
    density = mask.get('density',1)
    def field(x,y):
        if not (0<=x<w and 0<=y<h):
            return outside
        v = gray[y*w+x]/255
        return 1-v if mask.get('invert',False) else v
    def filtered(x,y):
        v = sum(field(x+dx,y+dy)*(r+1-abs(dx))*(r+1-abs(dy))
                for dx in range(-r,r+1) for dy in range(-r,r+1))/(r+1)**4
        return 1-density*(1-v)
    x,y = inverse(mask.get('transform',[1,0,0,1,0,0]),p)
    if mask.get('sampling','nearest')=='nearest':
        return filtered(math.floor(x),math.floor(y))
    return sum(filtered(ix,iy)*max(0,1-abs(x-ix-0.5))*max(0,1-abs(y-iy-0.5))
               for ix in range(math.floor(x-0.5),math.floor(x-0.5)+2)
               for iy in range(math.floor(y-0.5),math.floor(y-0.5)+2))


def mask_svg_alpha(root, point):
    """Small independent SVG evaluator for these rectangular, nearest-sampled fixtures."""
    masks = {m.get('id'):m for m in root.iter(NS+'mask')}
    clips = {m.get('id'):m for m in root.iter(NS+'clipPath')}
    def key(value):
        return re.fullmatch(r'url\(#([^)]+)\)',value)[1]
    def mask_value(mask,p):
        assert mask.get('mask-type')=='luminance'
        assert mask.get('maskUnits')==mask.get('maskContentUnits')=='userSpaceOnUse'
        background = mask.find(NS+'rect')
        if not shape_contains(background,p):
            return 0.0
        value = int(re.fullmatch(r'rgb\((\d+),\d+,\d+\)',background.get('fill'))[1])/255
        image = mask.find(NS+'image')
        assert image.get('style')=='image-rendering:pixelated'
        x,y = local_point(image,p)
        x-=float(image.get('x'));y-=float(image.get('y'))
        w,h,pixels,_ = editing.png_pixels(base64.b64decode(image.get('href').split(',')[1]))
        assert (w,h)==(int(image.get('width')),int(image.get('height')))
        if 0<=x<w and 0<=y<h:
            rgb= pixels[(math.floor(y)*w+math.floor(x))*4:][:4]
            assert rgb[0]==rgb[1]==rgb[2] and rgb[3]==255
            value=rgb[0]/255
        return value
    def visit(element,p):
        if element.get('display')=='none':return 0.0
        if element.tag in (NS+'g',NS+'svg'):
            p=local_point(element,p)
            alpha=0
            for child in element:
                a=visit(child,p);alpha=a+alpha*(1-a)
            if element.get('clip-path') and not any(shape_contains(c,p) for c in clips[key(element.get('clip-path'))]):alpha=0
            if element.get('mask'):alpha*=mask_value(masks[key(element.get('mask'))],p)
            return alpha*float(element.get('opacity','1'))
        if element.tag==NS+'rect':
            return float(element.get('fill-opacity','1')) if shape_contains(element,p) else 0.0
        return 0.0
    return visit(root,point)


class MaskCliTests(unittest.TestCase):
    invoke = editing.EditingCliTests.invoke

    def document(self,kind='vector',width=12,height=8):
        return self.invoke(dict(command='document.create',id='masks',kind=kind,width=width,height=height))

    def shape(self,id='ink',kind='vector',width=12,height=8,**properties):
        color=[31,147,219,255]
        content=dict(type='vector',geometry=dict(shape='rect',x=0,y=0,width=width,height=height),fill=color) if kind=='vector' else dict(type='raster',width=width,height=height,rgba_hex=bytes(color).hex()*(width*height))
        return dict(id=id,content=content,**properties)

    def edit(self,d,ops,expected=0):
        r=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=ops),expected)
        return r if expected else r['document']

    def pixels(self,d,scale=1):
        out=self.invoke(dict(command='document.export',document=d,format='png',scale=scale))
        w,h,p,_=editing.png_pixels(base64.b64decode(out['data']))
        preview=self.invoke(dict(command='document.render',document=d,scale=scale))
        self.assertEqual(bytes.fromhex(preview['data']),p)
        return w,h,p

    def assert_alpha(self,d,expected,scale=1,tolerance=0):
        w,h,p=self.pixels(d,scale)
        for y in range(h):
            for x in range(w):
                actual=p[(y*w+x)*4+3]
                wanted=byte(expected((x+0.5)/scale,(y+0.5)/scale))
                self.assertLessEqual(abs(actual-wanted),tolerance,(x,y,actual,wanted))
                if wanted==actual==0:self.assertEqual(p[(y*w+x)*4:][:4],bytes(4))

    def test_grayscale_attenuation_all_pixels_and_snapshot_persistence(self):
        mask=dict(width=6,height=2,gray_hex=bytes([0,1,63,128,254,255]*2).hex(),transform=[1,0,0,1,2,3])
        for kind in ('vector','raster'):
            d=self.edit(self.document(kind),[dict(op='add',item=self.shape(kind=kind,opacity=0.75)),dict(op='mask',id='ink',mask=mask)])
            self.assert_alpha(d,lambda x,y:opacity(mask,(x,y))*0.75)
            saved=self.invoke(dict(command='document.export',document=d,format='snapshot'))
            restored=json.loads(saved['data'])
            self.invoke(dict(command='document.validate',document=restored))
            self.assertEqual(d,restored);self.assertEqual(restored['items'][0]['mask']['gray_hex'],mask['gray_hex'])
            self.assertEqual(self.pixels(d),self.pixels(restored))
            info=self.invoke(dict(command='document.inspect',document=d))['items'][0]
            self.assertEqual(info['mask'],d['items'][0]['mask']);self.assertEqual(info['mask_world_transform'],mask['transform'])
            w,h,p=self.pixels(d)
            for pixel in (p[i:i+4] for i in range(0,len(p),4)):
                if pixel[3]:self.assertEqual(pixel[:3],bytes([31,147,219]))

    def test_clip_invert_disable_density_and_feather_direct_convolution(self):
        for kind in ('vector','raster'):
            original=self.edit(self.document(kind),[dict(op='add',item=self.shape(kind=kind))])
            for radius in (0,1,3):
                for clipped in (False,True):
                    for inverted in (False,True):
                        mask=dict(width=3,height=2,gray_hex='007fff4080ff',transform=[1,0,0,1,4,3],clip=clipped,invert=inverted,density=0.625,feather=radius)
                        d=self.edit(original,[dict(op='mask',id='ink',mask=mask)])
                        self.assert_alpha(d,lambda x,y:opacity(mask,(x,y)),tolerance=1)
            for density,enabled in ((0,True),(1,False)):
                mask=dict(width=1,height=1,gray_hex='00',density=density,enabled=enabled,invert=True,feather=2)
                d=self.edit(original,[dict(op='mask',id='ink',mask=mask)])
                self.assertEqual(self.pixels(d),self.pixels(original))
                self.assertEqual(self.pixels(self.edit(d,[dict(op='mask',id='ink',mask=None)])),self.pixels(original))

    def test_fractional_affine_nearest_bilinear_and_scaled_samples(self):
        d=self.edit(self.document(width=8,height=6),[dict(op='add',item=self.shape(width=8,height=6))])
        for transform in ([1,0,0,1,2.25,1.5],[-1.5,0,0,1,5.25,2.25],[0,1,-1,0,5,1],[1,0.25,0.5,1,1,1]):
            for sampling in ('nearest','bilinear'):
                mask=dict(width=3,height=2,gray_hex='0040ff2080e0',transform=transform,sampling=sampling,feather=1,density=0.85)
                masked=self.edit(d,[dict(op='mask',id='ink',mask=mask)])
                for scale in (1,2,4):self.assert_alpha(masked,lambda x,y:opacity(mask,(x,y)),scale,tolerance=1)

    def test_link_switch_preserves_world_then_artwork_and_mask_move_independently(self):
        d=self.document(width=24,height=20)
        mask=dict(width=3,height=2,gray_hex='ff80ff80ff80',transform=[1,0,0,1,1,1])
        d=self.edit(d,[dict(op='add',item=dict(id='parent',transform=[1,0,0,1,2,3],content=dict(type='group'))),dict(op='add',item=self.shape(parent='parent',transform=[2,0,0,2,0,0],mask=mask,width=8,height=6))])
        original=copy.deepcopy(d);initial=self.pixels(d)
        unlinked=self.edit(d,[dict(op='mask_link',id='ink',linked=False)])
        self.assertEqual(self.pixels(unlinked),initial)
        self.assertEqual(unlinked['items'][1]['mask']['transform'],[2,0,0,2,4,5])
        linked=self.edit(unlinked,[dict(op='mask_link',id='ink',linked=True)])
        self.assertEqual(self.pixels(linked),initial);self.assertEqual(linked['items'][1]['mask']['transform'],mask['transform'])
        for source,linked_state in ((d,True),(unlinked,False)):
            moved=self.edit(source,[dict(op='transform',id='parent',matrix=[1,0,0,1,1,0],space='world')])
            worldmask=copy.deepcopy(mask);worldmask['transform']=[2,0,0,2,5 if linked_state else 4,5]
            self.assert_alpha(moved,lambda x,y:opacity(worldmask,(x,y)))
        mask_moved=self.edit(unlinked,[dict(op='mask_transform',id='ink',matrix=[1,0,0,1,2,0],space='world')])
        self.assertEqual(mask_moved['items'][1]['transform'],d['items'][1]['transform'])
        worldmask=copy.deepcopy(mask);worldmask['transform']=[2,0,0,2,6,5]
        self.assert_alpha(mask_moved,lambda x,y:opacity(worldmask,(x,y)))
        local=self.edit(d,[dict(op='mask_transform',id='ink',matrix=[1,0,0,1,1,0],space='local')])
        world=self.edit(d,[dict(op='mask_transform',id='ink',matrix=[1,0,0,1,2,0],space='world')])
        self.assertEqual(self.pixels(local),self.pixels(world))
        self.assertEqual(d,original)

    def test_nested_masks_clip_opacity_and_blend_match_independent_composite(self):
        def composite(dst,src,opacity,mode):
            cb,ab=dst[:3],dst[3];cs,alpha=src[:3],src[3]*opacity
            blend=[b*s if mode=='multiply' else b+s-b*s if mode=='screen' else s for b,s in zip(cb,cs)]
            a=alpha+ab*(1-alpha)
            premul=[alpha*((1-ab)*s+ab*m)+(1-alpha)*ab*b for b,s,m in zip(cb,cs,blend)]
            return [v/a if a else 0 for v in premul]+[a]
        childmask=dict(width=4,height=3,gray_hex='4080ff20'*3,transform=[1,0,0,1,2,2],clip=False,invert=True)
        groupmask=dict(width=6,height=4,gray_hex='2080c0ff4080'*4,transform=[1,0,0,1,1,1],density=0.8)
        outer=dict(width=8,height=6,gray_hex='b0'*48,clip=False)
        for blend in ('normal','multiply','screen'):
            d=self.document(width=8,height=6)
            back=self.shape('background',width=8,height=6);back['content']['fill']=[150,50,90,160]
            lower=self.shape('lower',parent='g',width=8,height=6);lower['content']['fill']=[20,180,120,180]
            top=self.shape('top',parent='g',mask=childmask,opacity=0.6,blend='screen',width=8,height=6);top['content']['fill']=[220,100,40,130]
            items=[back,dict(id='outer',mask=outer,content=dict(type='group')),dict(id='g',parent='outer',mask=groupmask,opacity=0.7,blend=blend,clip=dict(geometry=dict(shape='rect',x=1,y=1,width=5,height=4)),content=dict(type='group')),lower,top]
            d=self.edit(d,[dict(op='add',item=i) for i in items]);w,h,p=self.pixels(d)
            for y in range(h):
                for x in range(w):
                    point=(x+0.5,y+0.5)
                    group=composite([20/255,180/255,120/255,180/255],[220/255,100/255,40/255,130/255],0.6*opacity(childmask,point),'screen')
                    # g blends against a transparent isolated outer group, so its blend must not see the page.
                    group=composite([0,0,0,0],group,0.7*opacity(groupmask,point) if 1<=x<6 and 1<=y<5 else 0,blend)
                    result=composite([150/255,50/255,90/255,160/255],group,opacity(outer,point),'normal')
                    expected=bytes(byte(v) for v in result)
                    actual=p[(y*w+x)*4:][:4]
                    self.assertTrue(all(abs(a-b)<=1 for a,b in zip(actual,expected)),(x,y,actual,expected))
            # Move the masked blending group into the page: all three backdrop modes now differ.
            page=self.edit(d,[dict(op='reparent',id='g',parent=None)])
            w,h,p=self.pixels(page)
            group=composite([20/255,180/255,120/255,180/255],[220/255,100/255,40/255,130/255],0.6*opacity(childmask,(3.5,2.5)),'screen')
            result=composite([150/255,50/255,90/255,160/255],group,0.7*opacity(groupmask,(3.5,2.5)),blend)
            self.assertTrue(all(abs(a-byte(b))<=1 for a,b in zip(p[(2*w+3)*4:][:4],result)))

    def test_masked_hierarchy_duplicate_reparent_ungroup_and_artboard_bleed(self):
        mask=dict(width=2,height=2,gray_hex='ff408080',linked=False,transform=[2,0,0,2,8,6])
        items=[dict(id='board',transform=[2,0,0,2,4,2],content=dict(type='frame',frame=dict(role='artboard',width=8,height=6,bleed=dict(left=1,top=2)))),self.shape(parent='board',width=8,height=6,mask=mask)]
        d=self.edit(self.document(width=24,height=20),[dict(op='add',item=i) for i in items])
        for bleed in (False,True):
            result=self.invoke(dict(command='artboard.export',document=d,format='png',include_bleed=bleed))['artifacts'][0]['artifact']
            w,h,p,_=editing.png_pixels(base64.b64decode(result['data']))
            offset=(1,2) if bleed else (0,0)
            local=dict(mask,transform=[1,0,0,1,2+offset[0],2+offset[1]])
            for y in range(h):
                for x in range(w):self.assertEqual(p[(y*w+x)*4+3],byte(opacity(local,(x+0.5,y+0.5))))
        rootmask=dict(width=8,height=6,gray_hex='80'*48)
        masked=self.edit(d,[dict(op='mask',id='board',mask=rootmask)])
        export=self.invoke(dict(command='artboard.export',document=masked,format='png',include_bleed=True))['artifacts'][0]['artifact']
        w,h,p,_=editing.png_pixels(base64.b64decode(export['data']))
        self.assertEqual(p[(4*w+3)*4+3],128)
        # A linked mask on the board itself shifts into bleed exactly once.
        export=self.invoke(dict(command='artboard.export',document=masked,format='png'))['artifacts'][0]['artifact']
        self.assertEqual(editing.png_pixels(base64.b64decode(export['data']))[2][(2*8+2)*4+3],128)
        grouped=self.edit(d,[dict(op='group',ids=['ink'],new_id='g'),dict(op='transform',id='g',matrix=[1,0,0,1,1,0])])
        before=self.pixels(grouped)
        released=self.edit(grouped,[dict(op='ungroup',id='g')]);self.assertEqual(self.pixels(released),before)
        reparent=self.edit(released,[dict(op='reparent',id='ink',parent=None)])
        self.assertEqual(self.pixels(reparent),before)
        duplicate=self.edit(d,[dict(op='duplicate',id='board',new_id='copy',descendant_ids={'ink':'copy-ink'})])
        self.assertEqual(duplicate['items'][-1]['mask'],d['items'][-1]['mask'])

    def test_svg_mask_fields_transforms_identifiers_and_independent_alpha(self):
        for linked in (False,True):
            mask=dict(width=3,height=2,gray_hex='004080ffc020',linked=linked,transform=[1,0,0,1,2,1],clip=False,invert=True,density=0.75,feather=1)
            d=self.edit(self.document(width=10,height=8),[dict(op='add',item=dict(id='inkbolt-mask-1',content=dict(type='group'))),dict(op='add',item=self.shape(parent='inkbolt-mask-1',transform=[1,0,0,1,1,2],mask=mask,width=6,height=4))])
            result=self.invoke(dict(command='document.export',document=d,format='svg'))
            root=ET.fromstring(result['data']);ids=[e.get('id') for e in root.iter() if e.get('id')]
            self.assertEqual(len(ids),len(set(ids)));self.assertTrue(any('Opacity masks' in v for v in result['losses']))
            w,h,p=self.pixels(d)
            for y in range(h):
                for x in range(w):self.assertLessEqual(abs(p[(y*w+x)*4+3]-byte(mask_svg_alpha(root,(x+0.5,y+0.5)))),1)
            disabled=self.edit(d,[dict(op='mask',id='ink',mask=dict(mask,enabled=False))])
            svg=self.invoke(dict(command='document.export',document=disabled,format='svg'))
            self.assertFalse(list(ET.fromstring(svg['data']).iter(NS+'mask')))

    def test_invalid_masks_locks_atomic_batches_and_preparation_budgets(self):
        d=self.edit(self.document(),[dict(op='add',item=self.shape())]);original=copy.deepcopy(d)
        valid=dict(width=1,height=1,gray_hex='80')
        for changes,code in ((dict(width=0),'INVALID_DOCUMENT'),(dict(gray_hex='zz'),'INVALID_DOCUMENT'),(dict(gray_hex='8000'),'INVALID_DOCUMENT'),(dict(density=1.01),'INVALID_DOCUMENT'),(dict(feather=33),'INVALID_DOCUMENT'),(dict(transform=[0,0,0,0,0,0]),'UNSUPPORTED'),(dict(width=16384,gray_hex='ff'*16384,feather=8),'RESOURCE_LIMIT')):
            bad=dict(valid,**changes,enabled=False)
            error=self.edit(d,[dict(op='properties',id='ink',name='candidate'),dict(op='mask',id='ink',mask=bad)],1)
            self.assertEqual(error['code'],code);self.assertEqual(error['operation_index'],1)
        self.assertEqual(d,original)
        for op in (dict(op='mask_link',id='ink',linked=False),dict(op='mask_transform',id='ink',matrix=[1,0,0,1,1,0])):
            self.assertEqual(self.edit(d,[op],1)['code'],'INVALID_OPERATION')
        locked=self.edit(d,[dict(op='properties',id='ink',locked=True)])
        self.assertEqual(self.edit(locked,[dict(op='mask',id='ink',mask=valid)],1)['code'],'LOCKED')
        group=self.edit(d,[dict(op='group',ids=['ink'],new_id='g')])
        active=self.edit(group,[dict(op='mask',id='g',mask=valid)])
        self.assertEqual(self.edit(active,[dict(op='ungroup',id='g')],1)['code'],'UNSUPPORTED')
        passthrough=self.edit(active,[dict(op='group_options',id='g',isolated=False)])
        self.assertEqual(self.pixels(active),self.pixels(passthrough))
        # Independent accounting: 49*(130*82)*130 = 67,904,200 convolution taps, above 67,108,864.
        large=self.document();large['items']=[self.shape(id=f'm{i}',width=1,height=1,mask=dict(width=64,height=16,gray_hex='ff'*1024,feather=32)) for i in range(49)]
        self.assertEqual(self.invoke(dict(command='document.validate',document=large),1)['code'],'RESOURCE_LIMIT')
        large['items']=[self.shape(id=f'm{i}',width=1,height=1,mask=dict(width=2048,height=1,gray_hex='ff'*2048,feather=16)) for i in range(16)]
        self.assertEqual(self.invoke(dict(command='document.validate',document=large),1)['code'],'RESOURCE_LIMIT')
        raster=self.document('raster');raster['items']=[self.shape(kind='raster',mask=dict(width=256,height=256,gray_hex='ff'*65536))]
        self.assertEqual(self.invoke(dict(command='document.validate',document=raster),1)['code'],'RESOURCE_LIMIT')

    def test_mcp_session_retry_undo_snapshot_diff_and_mask_settings(self):
        client=Client();self.addCleanup(client.close);client.initialize()
        with tempfile.TemporaryDirectory() as root:
            params=dict(session_root=root,session_id='masked-session')
            d=self.edit(self.document(),[dict(op='add',item=self.shape())]);before=self.pixels(d)
            client.success('session.create',**params,request_id='create',document=d)
            mask=dict(width=3,height=2,gray_hex='0080ff20c0ff',transform=[1,0,0,1,3,2],invert=True,feather=2,density=0.6,linked=False)
            action=dict(type='edit',label='Editable mask',operations=[dict(op='mask',id='ink',mask=mask)])
            result=client.success('session.apply',**params,expected_revision=0,request_id='mask',action=action)
            after=self.pixels(result['document']);self.assertNotEqual(before,after)
            self.assert_alpha(result['document'],lambda x,y:opacity(mask,(x,y)),tolerance=1)
            client.success('session.apply',**params,expected_revision=1,request_id='snapshot',action=dict(type='snapshot',name='masked'))
            restored=client.success('session.apply',**params,expected_revision=2,request_id='undo',action=dict(type='undo'))
            self.assertEqual(self.pixels(restored['document']),before)
            replay=client.success('session.apply',**params,expected_revision=0,request_id='mask',action=action)
            self.assertEqual(replay['document'],result['document']);self.assertEqual(replay['current_revision'],3)
            saved=client.success('session.read',**params,snapshot='masked');self.assertEqual(self.pixels(saved['document']),after)
            delta=client.success('session.diff',**params,from_revision=0,to_revision=1,compare_pixels=True)
            self.assertIn('mask',delta['items'][0]['fields'])
            client.success('session.verify',**params)


if __name__=='__main__':unittest.main()
