"""Original per-pixel canvas, coordinate, resource and durable-history fixtures."""
import base64
import copy
from fractions import Fraction as F
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
import test_editing_cli as editing
from test_layer_clipping_cli import layer, group
from test_artwork_masks_cli import rect, source
from test_images_cli import png
from synthetic_font import geometric_font
from test_mcp import Client


def checker(w,h):
    return [[17,89,211,255] if (x+y)%2 else [243,167,41,255] for y in range(h) for x in range(w)]


class CanvasTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def document(self,w=6,h=4,items=None):
        d=self.invoke(dict(command='document.create',id='canvas-fixture',kind='raster',width=w,height=h))
        return self.edit(d,[dict(op='add',item=i) for i in (items if items is not None else [layer('pixels',checker(w,h),w)])])
    def edit(self,d,ops,expected=0):
        r=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=ops),expected)
        return r if expected else r['document']
    def canvas(self,d,type,**kw):return self.edit(d,[dict(op='canvas',action=dict(type=type,**kw))])
    def pixels(self,d,scale=1,**kw):
        r=self.invoke(dict(command='document.export',document=d,format='png',scale=scale,**kw))
        return editing.png_pixels(base64.b64decode(r['data']))
    def crop_bytes(self,p,w,h,x,y,nw,nh):
        return b''.join(p[(sy*w+sx)*4:(sy*w+sx+1)*4] if 0<=sx<w and 0<=sy<h else bytes(4) for sy in range(y,y+nh) for sx in range(x,x+nw))

    def test_crop_every_pixel_and_reveal_retained_outside_layer_content(self):
        d=self.document();original=copy.deepcopy(d);p=self.pixels(d)[2]
        for x,y,w,h in [(1,1,4,2),(-2,-1,10,7),(5,3,4,3),(10,10,2,2)]:
            c=self.canvas(d,'crop',x=x,y=y,width=w,height=h)
            self.assertEqual(self.pixels(c)[2],self.crop_bytes(p,6,4,x,y,w,h))
            self.assertEqual(c['items'][0]['content'],d['items'][0]['content'])
            restored=self.canvas(c,'crop',x=-x,y=-y,width=6,height=4)
            self.assertEqual(self.pixels(restored)[2],p)
            self.assertEqual(restored['items'],d['items'])
        self.assertEqual(d,original)

    def test_all_nine_extent_anchors_odd_deltas_and_transparent_padding(self):
        d=self.document(5,3);p=self.pixels(d)[2]
        names=['top_left','top','top_right','left','center','right','bottom_left','bottom','bottom_right']
        for nw,nh in [(8,6),(2,2),(5,3)]:
            for n,name in enumerate(names):
                dx=((nw-5)*(n%3))//2;dy=((nh-3)*(n//3))//2
                c=self.canvas(d,'extent',width=nw,height=nh,anchor=name)
                self.assertEqual(self.pixels(c)[2],self.crop_bytes(p,5,3,-dx,-dy,nw,nh),(name,nw,nh))
        self.assertEqual(self.canvas(d,'extent',width=8,height=6)['items'],self.canvas(d,'extent',width=8,height=6,anchor='center')['items'])

    def test_nearest_checkerboard_enlarge_reduce_anisotropic_and_export_scale(self):
        d=self.document();colors=checker(6,4)
        for nw,nh in [(12,8),(3,2),(9,6),(7,5),(2,12),(1,1)]:
            c=self.canvas(d,'scale',width=nw,height=nh,sampling='nearest')
            self.assertEqual(c['items'][0]['content']['rgba_hex'],d['items'][0]['content']['rgba_hex'])
            for scale in (1,2,3):
                w,h,p,_=self.pixels(c,scale)
                expected=bytes(v for y in range(h) for x in range(w) for v in colors[((2*y+1)*4//(2*h))*6+(2*x+1)*6//(2*w)])
                self.assertEqual(p,expected,(nw,nh,scale))
            self.assertEqual(c['resolution_ppi'],96)

    def test_bilinear_premultiplied_alpha_matches_independent_rational_weights(self):
        colors=[[250,20,10,255],[10,230,40,64],[200,40,250,0],[30,70,210,128],[180,160,10,192],[20,10,40,255]]
        d=self.document(3,2,[layer('pixels',colors,3)])
        for nw,nh in [(7,5),(2,1),(1,1),(3,2)]:
            c=self.canvas(d,'scale',width=nw,height=nh,sampling='bilinear');p=self.pixels(c)[2]
            for y in range(nh):
                for x in range(nw):
                    sx,sy=F(2*x+1,2)*3/nw-F(1,2),F(2*y+1,2)*2/nh-F(1,2)
                    ix,iy=sx.numerator//sx.denominator,sy.numerator//sy.denominator;fx,fy=sx-ix,sy-iy
                    rgba=[F(0)]*4
                    for dx,wx in [(0,1-fx),(1,fx)]:
                        for dy,wy in [(0,1-fy),(1,fy)]:
                            v=colors[max(0,min(1,iy+dy))*3+max(0,min(2,ix+dx))];a=F(v[3],255)
                            for channel in range(3):rgba[channel]+=v[channel]*a*wx*wy
                            rgba[3]+=a*wx*wy
                    wanted=[v/rgba[3] for v in rgba[:3]]+[255*rgba[3]] if rgba[3]*255>=F(1,2) else [F(0)]*4
                    for actual,value in zip(p[(y*nw+x)*4:][:4],wanted):
                        rounded=(value+F(1,2)).numerator//(value+F(1,2)).denominator
                        if actual!=rounded:self.assertEqual(value.denominator,2);self.assertEqual(actual,rounded-1)

    def test_hierarchy_work_paths_frames_and_masks_follow_canvas_once(self):
        grid=dict(width=6,height=4,gray_hex=bytes([255 if x<4 else 0 for y in range(4) for x in range(6)]).hex(),linked=False)
        items=[group('g',transform=[1,0,0,1,1,1]),layer('a',checker(6,4),6,parent='g',mask=grid),dict(id='path',content=dict(type='work_path',geometry=dict(shape='rect',x=1,y=1,width=3,height=2)))]
        d=self.document(8,6,items);p=self.pixels(d)[2]
        c=self.canvas(d,'crop',x=2,y=1,width=5,height=4)
        self.assertEqual(self.pixels(c)[2],self.crop_bytes(p,8,6,2,1,5,4))
        a=next(i for i in c['items'] if i['id']=='a');path=next(i for i in c['items'] if i['id']=='path')
        self.assertEqual(a['transform'],[1,0,0,1,0,0])
        self.assertEqual(a['mask']['transform'],[1,0,0,1,-2,-1])
        self.assertEqual(path['transform'],[1,0,0,1,-2,-1])
        scaled=self.canvas(d,'scale',width=16,height=12,sampling='nearest')
        wanted=bytes(v for y in range(12) for x in range(16) for v in p[((y//2)*8+x//2)*4:][:4])
        self.assertEqual(self.pixels(scaled)[2],wanted)

    def test_shared_artwork_mask_source_stays_local_and_both_link_modes_move(self):
        for linked in (False,True):
            items=[source(),rect('window',x=1,y=1,w=3,h=2,parent='source'),layer('pixels',checker(6,4),6,artwork_mask=dict(source='source',region=[0,0,6,4],linked=linked))]
            d=self.document(items=items);d=self.edit(d,[dict(op='properties',id='source',locked=True)]);p=self.pixels(d)[2]
            c=self.canvas(d,'crop',x=1,y=1,width=4,height=2)
            resources=lambda d:[i for i in d['items'] if i['id']!='pixels']
            self.assertEqual(resources(c),resources(d))
            self.assertEqual(self.pixels(c)[2],self.crop_bytes(p,6,4,1,1,4,2))
            scaled=self.canvas(d,'scale',width=12,height=8,sampling='nearest')
            self.assertEqual(resources(scaled),resources(d))
            self.assertEqual(self.pixels(scaled)[2],bytes(v for y in range(8) for x in range(12) for v in p[((y//2)*6+x//2)*4:][:4]))

    def test_selection_and_named_channels_crop_pad_scale_and_keep_identity(self):
        d=self.document(4,3);gray=bytes(range(0,240,20));plane=dict(width=4,height=3,gray_hex=gray.hex())
        d=self.edit(d,[dict(op='selection_set',selection=plane),dict(op='channel_put',id='ink',channel=dict(name='Original ink',role=dict(type='spot',ink_id='warm',alternate_srgb=[200,30,10]),plane=plane))])
        for x,y,w,h in [(1,1,2,2),(-1,-2,7,6)]:
            c=self.canvas(d,'crop',x=x,y=y,width=w,height=h)
            expected=bytes(gray[sy*4+sx] if 0<=sx<4 and 0<=sy<3 else 0 for sy in range(y,y+h) for sx in range(x,x+w))
            self.assertEqual(bytes.fromhex(c['selection']['gray_hex']),expected)
            self.assertEqual(c['channels']['ink']['plane'],c['selection'])
            self.assertEqual(c['channels']['ink']['role'],d['channels']['ink']['role'])
        for sampling in ('nearest','bilinear'):
            c=self.canvas(d,'scale',width=8,height=6,sampling=sampling);values=bytes.fromhex(c['selection']['gray_hex'])
            for y in range(6):
                for x in range(8):
                    if sampling=='nearest':wanted=gray[(y//2)*4+x//2]
                    else:
                        # An affine scalar ramp reproduces its clamped coordinate
                        # exactly under linear reconstruction, independently of taps.
                        wanted=20*max(0,min(3,F(2*x-1,4)))+80*max(0,min(2,F(2*y-1,4)))
                    self.assertEqual(values[y*8+x],int(wanted+F(1,2)))
            self.assertEqual(c['channels']['ink']['plane'],c['selection'])


    def test_placed_cropped_image_keeps_external_source_and_asset_bytes(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);path=root/'original.png';raw=bytes(v for p in checker(6,4) for v in p);path.write_bytes(png(6,4,raw));store=root/'assets'
            asset=self.invoke(dict(command='asset.import',source_path=str(path),store_root=str(store)))['asset']
            d=self.invoke(dict(command='document.create',id='placed',kind='raster',width=4,height=2))
            d=self.edit(d,[dict(op='asset_put',id='original',asset=asset),dict(op='add',item=dict(id='placed',content=dict(type='image',asset_id='original',width=4,height=2,crop=dict(x=1,y=1,width=4,height=2))))])
            hashes={f:hashlib.sha256(f.read_bytes()).hexdigest() for f in root.rglob('*') if f.is_file()}
            original=self.crop_bytes(raw,6,4,1,1,4,2)
            for w,h in [(8,6),(2,1),(7,5)]:
                c=self.canvas(d,'scale',width=w,height=h,sampling='nearest')
                actual=self.pixels(c,asset_root=str(store))[2]
                expected=b''.join(original[(((2*y+1)*2//(2*h))*4+(2*x+1)*4//(2*w))*4:][:4] for y in range(h) for x in range(w))
                self.assertEqual(actual,expected);self.assertEqual(c['assets'],d['assets'])
                self.assertEqual(c['items'][0]['content']['crop'],dict(x=1,y=1,width=4,height=2))
            self.assertEqual({f:hashlib.sha256(f.read_bytes()).hexdigest() for f in hashes},hashes)

    def test_editable_text_scales_geometry_without_rewriting_font_or_glyph_settings(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);font=root/'original.ttf';font.write_bytes(geometric_font());license=root/'LICENSE';license.write_bytes((Path(__file__).resolve().parents[1]/'LICENSE').read_bytes());store=root/'fonts'
            desc=self.invoke(dict(command='font.import',source_path=str(font),license_path=str(license),store_root=str(store)))
            imported=self.invoke(dict(command='svg.import',id='labels',source=dict(kind='text',text='<svg width="32" height="24"><text x="3.5" y="12" font-size="10" font-family="Geometry" fill="#205080">AA</text></svg>'),font_bindings=[dict(family='Geometry',font_id='original',font=desc)],font_root=str(store)))
            d=imported['document'];d['kind']='raster';hashes={f:hashlib.sha256(f.read_bytes()).hexdigest() for f in root.rglob('*') if f.is_file()}
            c=self.canvas(d,'scale',width=96,height=72,sampling='nearest')
            p=self.pixels(c,font_root=str(store))[2]
            expected=bytes(v for y in range(72) for x in range(96) for v in ([32,80,128,255] if 15<=y<36 and (12<=x<24 or 30<=x<42) else [0]*4))
            self.assertEqual(p,expected);self.assertEqual(c['fonts'],d['fonts'])
            self.assertEqual([i['content'] for i in c['items']],[i['content'] for i in d['items']])
            self.assertEqual({f:hashlib.sha256(f.read_bytes()).hexdigest() for f in hashes},hashes)

    def test_nearest_boundary_rounding_is_bounded_and_planes_agree_at_odd_sizes(self):
        colors=[[25,90,170,255],[240,180,50,255]];d=self.document(3,1,[layer('pixels',colors,2)])
        for epsilon,chosen in [(0,1),(2**-51,1),(2**-47,0),(-2**-47,1)]:
            c=copy.deepcopy(d);c['items'][0]['transform']=[1,0,0,1,.5+epsilon,0]
            self.assertEqual(self.pixels(c)[2][4:8],bytes(colors[chosen]))
        d=self.document();plane=dict(width=6,height=4,gray_hex=bytes(c[0] for c in checker(6,4)).hex())
        d=self.edit(d,[dict(op='selection_set',selection=plane)])
        c=self.canvas(d,'scale',width=7,height=5,sampling='nearest');p=self.pixels(c)[2]
        self.assertEqual(bytes.fromhex(c['selection']['gray_hex']),p[0::4])

    def test_frame_clips_scale_with_scene_and_standalone_keeps_local_artboard_extent(self):
        frame=dict(id='board',transform=[1,0,0,1,2,1],content=dict(type='frame',frame=dict(role='artboard',width=4,height=3)))
        d=self.document(8,6,[frame,layer('pixels',checker(6,4),6,parent='board')]);p=self.pixels(d)[2]
        c=self.canvas(d,'scale',width=16,height=12,sampling='nearest')
        self.assertEqual(self.pixels(c)[2],b''.join(p[((y//2)*8+x//2)*4:][:4] for y in range(12) for x in range(16)))
        self.assertEqual(c['items'][0]['content'],d['items'][0]['content'])
        a=self.invoke(dict(command='artboard.export',document=d,format='png'));b=self.invoke(dict(command='artboard.export',document=c,format='png'))
        self.assertEqual((a.pop('revision'),b.pop('revision')),(d['revision'],c['revision']))
        self.assertEqual(a,b)

    def test_resolution_only_keeps_pixels_and_all_layers_including_locked(self):
        d=self.document();d['items'][0]['locked']=True;before=self.pixels(d)[2]
        for ppi in (1,72,300.25,9600):
            c=self.canvas(d,'resolution',ppi=ppi);w,h,p,chunks=self.pixels(c)
            self.assertEqual((w,h,p),(6,4,before));self.assertEqual(c['items'],d['items'])
            self.assertEqual(struct.unpack('>IIB',chunks[b'pHYs']), (int(ppi/0.0254+.5),)*2+(1,))

    def test_filters_require_explicit_policy_and_rebase_unlinked_filter_masks(self):
        d=self.document();m=dict(width=6,height=4,gray_hex='ff'*24,linked=False)
        d=self.edit(d,[dict(op='filters',id='pixels',filters=[dict(id='blur',operator=dict(type='box',radius=1),mask=m)])])
        for type,kw in [('crop',dict(x=1,y=1,width=4,height=2)),('extent',dict(width=8,height=6)),('scale',dict(width=12,height=8,sampling='nearest'))]:
            error=self.edit(d,[dict(op='canvas',action=dict(type=type,**kw))],1);self.assertEqual(error['code'],'UNSUPPORTED')
            c=self.canvas(d,type,effect_policy='preserve_parameters',**kw)
            self.assertEqual(c['items'][0]['filters'][0]['operator'],d['items'][0]['filters'][0]['operator'])
            self.assertEqual(c['items'][0]['filters'][0]['mask']['transform'],c['items'][0]['transform'])
            self.pixels(c)

    def test_invalid_sizes_origins_kinds_locks_limits_and_batch_are_atomic(self):
        d=self.document();original=copy.deepcopy(d)
        bad=[dict(type='crop',x=-2147483648,y=0,width=1,height=1),dict(type='crop',x=0,y=0,width=0,height=1),dict(type='extent',width=32769,height=1),dict(type='scale',width=1,height=0,sampling='nearest'),dict(type='resolution',ppi=.9),dict(type='resolution',ppi=9601),dict(type='scale',width=2,height=2,sampling='unknown')]
        for action in bad:
            self.edit(d,[dict(op='canvas',action=dict(type='crop',x=1,y=1,width=4,height=2)),dict(op='canvas',action=action)],1)
            self.assertEqual(d,original)
        for hidden in (True,False):
            locked=copy.deepcopy(d);locked['items'][0].update(locked=True,visible=not hidden)
            self.assertEqual(self.edit(locked,[dict(op='canvas',action=dict(type='extent',width=8,height=6,anchor='top_left'))],1)['code'],'LOCKED')
        vector=self.invoke(dict(command='document.create',id='v',kind='vector',width=2,height=2))
        self.assertEqual(self.edit(vector,[dict(op='canvas',action=dict(type='resolution',ppi=72))],1)['code'],'UNSUPPORTED')
        selected=self.edit(d,[dict(op='selection_fill',selected=True)])
        self.assertEqual(self.edit(selected,[dict(op='canvas',action=dict(type='extent',width=513,height=512))],1)['code'],'RESOURCE_LIMIT')
        ch=self.edit(d,[dict(op='channel_put',id=str(i),channel=dict(name='plane',plane=dict(width=6,height=4,gray_hex='ff'*24))) for i in range(2)])
        self.assertEqual(self.edit(ch,[dict(op='canvas',action=dict(type='extent',width=512,height=512))],1)['code'],'RESOURCE_LIMIT')

    def test_mcp_crop_scale_history_reopen_retry_undo_and_original_snapshot(self):
        d=self.document();before=self.pixels(d)[2]
        with tempfile.TemporaryDirectory() as root:
            params=dict(session_root=root,session_id='canvas');client=Client();client.initialize()
            action=dict(type='edit',label='Prepare output size',operations=[dict(op='canvas',action=dict(type='crop',x=1,y=1,width=4,height=2)),dict(op='canvas',action=dict(type='scale',width=8,height=4,sampling='nearest'))])
            try:
                client.success('session.create',**params,request_id='create',document=d)
                result=client.success('session.apply',**params,request_id='resize',expected_revision=0,action=action)
                self.assertEqual((result['document']['width'],result['document']['height']),(8,4))
                client.success('session.apply',**params,request_id='save',expected_revision=1,action=dict(type='snapshot',name='output'))
            finally:client.close()
            client=Client();client.initialize()
            try:
                replay=client.success('session.apply',**params,request_id='resize',expected_revision=0,action=action);self.assertEqual(replay['document'],result['document'])
                saved=client.success('session.read',**params,snapshot='output');self.assertEqual(saved['document']['items'],result['document']['items'])
                diff=client.success('session.diff',**params,from_revision=0,to_revision=1)
                self.assertEqual({m['field'] for m in diff['metadata']},{'width'})
                undo=client.success('session.apply',**params,request_id='undo',expected_revision=2,action=dict(type='undo'))
                self.assertEqual(self.pixels(undo['document'])[2],before);self.assertEqual(undo['document']['items'],d['items'])
                client.success('session.verify',**params)
            finally:client.close()

    def test_canvas_capabilities_and_change_receipts_match_supported_actions(self):
        c=self.invoke(dict(command='capabilities'))['canvas_operations']
        self.assertEqual(c['actions'],['crop','extent','scale','resolution'])
        self.assertEqual(c['sampling'],['nearest','bilinear','area','bicubic','lanczos3'])
        self.assertEqual(c['sampling_boundary_epsilon_factor'],8)
        self.assertEqual(c['document_kinds'],['raster'])
        d=self.document()
        r=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='canvas',action=dict(type='crop',x=2,y=1,width=3,height=2))]))
        detail=r['changes'][0]['details'];self.assertEqual(detail['before_dimensions'],[6,4]);self.assertEqual(detail['after_dimensions'],[3,2])
        self.assertEqual(detail['content_transform'],[1,0,0,1,-2,-1]);self.assertTrue(detail['source_content_retained'])


    def test_extent_reveals_retained_artwork_and_editable_clip_keeps_crop_window(self):
        d=self.document();p=self.pixels(d)[2]
        cropped=self.canvas(d,'crop',x=1,y=1,width=4,height=2)
        expanded=self.canvas(cropped,'extent',width=6,height=4)
        self.assertEqual(self.pixels(expanded)[2],p)
        clipped=self.edit(d,[dict(op='group',ids=['pixels'],new_id='window'),dict(op='clip',id='window',clip=dict(geometry=dict(shape='rect',x=1,y=1,width=4,height=2)))])
        expanded=self.canvas(self.canvas(clipped,'crop',x=1,y=1,width=4,height=2),'extent',width=6,height=4)
        expected=b''.join(p[(y*6+x)*4:][:4] if 1<=x<5 and 1<=y<3 else bytes(4) for y in range(4) for x in range(6))
        self.assertEqual(self.pixels(expanded)[2],expected)
        revealed=self.edit(expanded,[dict(op='clip',id='window',clip=None)])
        self.assertEqual(self.pixels(revealed)[2],p)


if __name__=='__main__':unittest.main()
