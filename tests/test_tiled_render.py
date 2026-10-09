"""Original regional-composition oracles and full-size output contracts."""
import base64
import copy
import hashlib
import struct
import unittest
import test_agent_workspace as workspace
import test_stored_samples as native
import test_samples_cli as samples
import test_hdr_cli as hdr
import test_pixel_warps_cli as warps
from test_image_io_cli import tiff_tags
from test_editing_cli import png_pixels
from test_render_quality_cli import rect


class TiledRenderTests(unittest.TestCase):
    setUp = workspace.AgentWorkspaceTests.setUp
    cli = workspace.AgentWorkspaceTests.cli
    imported = native.StoredSampleTests.imported

    def document(self, items, w=263, h=139, kind='vector'):
        d = self.cli('document.create', id='tiles', kind=kind, width=w, height=h)
        d['items'] = items
        return self.cli('document.validate', document=d)

    def exported(self,d,tiled=True,**options):
        return self.cli('document.export',document=d,format='png',render_options=dict(evaluation='tiled' if tiled else 'whole',**options))

    def pixels(self,d,tiled=True,**options):
        return png_pixels(base64.b64decode(self.exported(d,tiled,**options)['data']))[:3]

    def test_multiple_tiles_preserve_groups_clips_masks_blends_and_padding(self):
        group = dict(id='group',content=dict(type='group',isolated=True),opacity=.625)
        front = rect('front',x=107.25,y=119.5,w=130.25,h=11.75,color=[210,30,100,173],parent='group',blend='multiply')
        front['clip'] = dict(geometry=dict(shape='rect',x=111,y=0,width=110,height=140),transform=[1,0,0,1,0,0])
        front['mask'] = dict(width=2,height=2,gray_hex='8040ffcc',transform=[100,0,0,80,0,0])
        d=self.document([rect(w=263,h=139,color=[10,120,240,127]),group,front]); before=copy.deepcopy(d)
        for antialias in ['none','coverage','supersample2']:
            for padding,crop in [(0,True),(3,True),(3,False)]:
                options=dict(antialias=antialias,padding=padding,crop_to_canvas=crop)
                self.assertEqual(self.pixels(d,True,**options),self.pixels(d,False,**options))
        self.assertEqual(d,before)

    def test_social_and_print_dimensions_are_fully_evaluated(self):
        for w,h in [(1080,1080),(2480,3508)]:
            d=self.document([rect(w=w,h=h,color=[20,80,150,255])],w,h)
            width,height,raw=self.pixels(d)
            self.assertEqual((width,height),(w,h)); self.assertEqual(raw,bytes([20,80,150,255])*(w*h))
            self.cli('document.render',document=d,error='RESOURCE_LIMIT')

    def test_native_two_megapixel_source_exports_every_pixel(self):
        d=self.imported(1920,1080)
        w,h,raw=self.pixels(d)
        self.assertEqual((w,h),(1920,1080))
        expected=bytes(round(v*255/65535) for y in range(h) for x in range(w) for v in native.pixel(x,y))
        self.assertEqual(raw,expected)
        # Independently parse native strips, avoiding a second full Python-int frame.
        artifact=self.cli('document.export',document=d,format='tiff',
                          image_options=dict(depth='u16',compression='none'),
                          render_options=dict(evaluation='tiled'))
        data=base64.b64decode(artifact['data']); tags=tiff_tags(data)
        self.assertEqual(tags[258],(16,)*4); self.assertEqual(tags[338],(2,))
        self.assertGreater(len(tags[273]),1)
        y=0
        for offset,count in zip(tags[273],tags[279]):
            rows=count//(w*8)
            self.assertEqual(data[offset:offset+count], b''.join(
                struct.pack('<4H',*native.pixel(x,j)) for j in range(y,y+rows) for x in range(w)))
            y+=rows
        self.assertEqual(y,h)

    def test_native_strips_keep_all_depths_channels_hdr_and_compression(self):
        for depth,maximum in [('u8',255),('u16',65535),('f32',1)]:
            for channels in ['rgba','gray_alpha']:
                values=[v for x in range(263) for v in
                        ([x%17/16 if depth=='f32' else x%17, maximum//2 if depth!='f32' else .5]
                         if channels=='gray_alpha' else
                         [x%17/16 if depth=='f32' else x%17]*3+[maximum])]
                d=self.document([samples.layer(values,depth,channels)],263,131,'raster')
                for compression in ['none','deflate']:
                    options=dict(depth=depth,channels=channels,compression=compression)
                    a=self.cli('document.export',document=d,format='tiff',image_options=options,render_options=dict(evaluation='tiled'))
                    b=self.cli('document.export',document=d,format='tiff',image_options=options)
                    self.assertEqual(samples.decode(a)[0],samples.decode(b)[0])
                options=dict(depth=depth,channels=channels,compression='lzw')
                artifact=self.cli('document.export',document=d,format='tiff',image_options=options,render_options=dict(evaluation='tiled'))
                path=self.root/'compressed.tiff';path.write_bytes(base64.b64decode(artifact['data']))
                reopened=self.cli('sample.import',source_path='compressed.tiff',id='return',color_policy='assume_srgb',storage={})['document']
                checked=self.cli('document.export',document=reopened,format='tiff',image_options=dict(options,compression='none'))
                self.assertEqual(samples.decode(checked)[0],samples.decode(b)[0])
        values=[v for x in range(263) for v in [-.25,x/16,2.,.5]]
        d=self.document([],263,1,'raster');d['color_space']='linear_srgb';d['items']=[hdr.layer(values)]
        artifact=self.cli('document.export',document=d,format='tiff',image_options=dict(depth='f32',compression='none'),render_options=dict(evaluation='tiled'))
        self.assertEqual(samples.decode(artifact)[0],values)
        self.assertEqual(artifact['color_space'],'linear_srgb')
        self.cli('document.export',document=d,format='tiff',image_options=dict(depth='u16'),render_options=dict(evaluation='tiled'),error='HDR_VIEW_REQUIRED')

    def test_inline_native_and_byte_sources_share_linear_sampling_across_tiles(self):
        raw=bytes([40,80,230,155,200,40,110,255,5,150,220,0,15,160,70,32])
        for sampling in ['nearest','bilinear','bicubic','lanczos3','area']:
            sources=[dict(type='raster',width=2,height=2,rgba_hex=raw.hex(),sampling=sampling),
                     dict(type='samples',grid=dict(width=2,height=2,depth='u8',channels='rgba',data_hex=raw.hex(),sampling=sampling))]
            for content in sources:
                d=self.document([dict(id='pixels',content=content,transform=[110,0,0,70,21.25,8.5])],263,151,'raster')
                d['color_space']='linear_srgb'
                options=dict(view=dict(exposure=0,tone_map='clip'),antialias='supersample2')
                self.assertEqual(self.pixels(d,True,**options),self.pixels(d,False,**options))

    def test_curved_edges_and_pixel_warps_cross_tile_boundaries(self):
        curve=rect('ellipse',color=[30,100,210,255])
        curve['content']['geometry']=dict(shape='ellipse',cx=128.125,cy=127.625,rx=80.75,ry=61.25)
        curve['content']['stroke']=dict(width=1.75,color=[210,60,30,255])
        d=self.document([curve],263,200)
        for antialias in ['none','coverage','supersample2']:
            a=self.pixels(d,True,antialias=antialias)[2];b=self.pixels(d,False,antialias=antialias)[2]
            self.assertEqual(a,b)
        item=dict(id='pixels',content=dict(type='raster',width=8,height=8,rgba_hex=warps.chart().hex(),sampling='bilinear'),
                  transform=[14,0,0,12,33.25,11.5],pixel_warp=warps.mesh())
        d=self.document([item],263,151,'raster')
        self.assertEqual(self.pixels(d),self.pixels(d,False))

    def test_nonlocal_content_and_work_limits_fail_explicitly(self):
        item=rect(w=5,h=5); item['filters']=[dict(id='blur',operator=dict(type='box',radius=1),border='clamp')]
        d=self.document([item],10,10)
        self.cli('document.export',document=d,format='png',render_options=dict(evaluation='tiled'),error='UNSUPPORTED_TILED_RENDER')
        d=self.document([],4097,4096)
        self.cli('document.export',document=d,format='png',render_options=dict(evaluation='tiled'),error='RESOURCE_LIMIT')
        self.cli('document.export',document=self.document([],10,10),format='png',render_options=dict(evaluation='tiled'),control=dict(timeout_ms=0),error='TIMEOUT')
        commands=[dict(verb='move',to=[0,0])]+[dict(verb='cubic',control1=[.25,.25],control2=[.75,.75],to=[1,1]) for _ in range(512)]+[dict(verb='close')]
        item=rect();item['content']['geometry']=dict(shape='path',commands=commands)
        d=self.document([item],32768,1)
        self.cli('document.export',document=d,format='png',scale=4,render_options=dict(evaluation='tiled',antialias='supersample4'),error='RESOURCE_LIMIT')

    def test_fractional_canvas_and_dissolve_keep_global_coordinates(self):
        d=self.document([rect(x=-10,y=-10,w=300,h=160)])
        d=self.cli('document.edit',document=d,expected_revision=0,operations=[dict(op='vector_canvas',action=dict(type='set',origin=[-2.25,1.5],size=[260.25,132.5],unit='px',process_space='rgb'))])['document']
        self.assertEqual(self.pixels(d),self.pixels(d,False))
        self.assertEqual(self.pixels(d)[2][-1],32)
        d=self.document([rect(w=263,h=139,color=[30,100,210,127],coverage=dict(type='dissolve',seed=7))])
        raw=self.pixels(d)[2]
        expected=bytearray()
        for y in range(139):
            for x in range(263):
                code=int.from_bytes(hashlib.sha256(b'inkbolt.coverage.v1\0'+struct.pack('<Iqq',7,x,y)).digest()[:4],'little')
                expected.extend([30,100,210,255] if 127/255>(code+.5)/2**32 else [0]*4)
        self.assertEqual(raw,expected)

    def test_artboard_admission_and_failed_publication_are_consistent(self):
        frame=dict(id='board',content=dict(type='frame',frame=dict(role='artboard',width=1080,height=1080,background=[20,80,150,255])))
        d=self.document([frame],1080,1080)
        result=self.cli('artboard.export',document=d,format='png',render_options=dict(evaluation='tiled'))
        self.assertEqual(png_pixels(base64.b64decode(result['artifacts'][0]['artifact']['data']))[2],bytes([20,80,150,255])*1080**2)
        d=self.document([rect(x=250,y=130,w=10,h=5,color=[20,80,150,255])])
        output=dict(file_name='failed.tiff',format='tiff',image_options=dict(depth='u16',channels='gray_alpha'),render_options=dict(evaluation='tiled'))
        self.cli('document.publish',document=d,output=output,error='GRAYSCALE_CONVERSION_REQUIRED')
        self.assertFalse((self.root/'failed.tiff').exists())


if __name__ == '__main__': unittest.main()
