"""Wide sources keep native precision without raising cache or decode-work limits."""
import base64
import copy
import struct
import sys
import unittest
from test_cli import EXE, ROOT
import test_agent_workspace as workspace
import test_samples_cli as samples
from test_editing_cli import png_pixels
from test_image_io_cli import tiff_tags

sys.path.insert(0,str(ROOT/'tools'))
import measure_workloads as measure
import wide_native_workload as wide


class NativeLocalityTests(unittest.TestCase):
    setUp=workspace.AgentWorkspaceTests.setUp
    cli=workspace.AgentWorkspaceTests.cli

    def test_original_wide_composition_and_edit_history_match_every_native_sample(self):
        case=measure.Case(EXE,self.root/'wide',wide.CASE,1)
        row=wide.run(case)
        self.assertTrue(row['success'],row)
        self.assertEqual(row['process_calls'],7)
        self.assertEqual(row['blocked_steps'],0)
        self.assertEqual((case.root/'initial.tiff').read_bytes(),(case.root/'historical.tiff').read_bytes())
        self.assertNotEqual((case.root/'initial.tiff').read_bytes(),(case.root/'edited.tiff').read_bytes())
        tags=tiff_tags((case.root/'initial.tiff').read_bytes())
        self.assertGreater(tags[278][0],8)
        self.assertTrue(all(v<=16*1024*1024 for v in tags[279]))

    def imported_scene(self,width,height):
        original=measure.native_pixels(width,height)
        source=measure.native_png(width,height,original)
        (self.root/'original.png').write_bytes(source)
        d=self.cli('sample.import',source_path='original.png',id='native',storage={})['document']
        # Indexed scene with actual one-pixel annotations outside the output.
        # Source width exceeds the 16 native blocks resident in the reader.
        d['items'] += [dict(id=f'outside-{i}',transform=[1,0,0,1,0,1000+i],
            content=dict(type='raster',width=1,height=1,rgba_hex='145096ff')) for i in range(128)]
        return d,original,source

    def test_wide_thin_sources_keep_png_native_scale_padding_and_supersampling(self):
        w,h=2065,19
        d,original,source=self.imported_scene(w,h)
        values=struct.unpack('<'+'H'*(w*h*4),original)
        encoded=bytes((v*255+32767)//65535 for v in values)
        before=copy.deepcopy(d)
        for scale,aa,padding in [(1,'none',0),(1,'coverage',3),(1,'supersample4',3),(4,'coverage',0)]:
            options=dict(evaluation='tiled',antialias=aa,padding=padding)
            result=self.cli('document.export',document=d,format='png',scale=scale,render_options=options)
            actual=png_pixels(base64.b64decode(result['data']))[:3]
            rows=[b''.join(encoded[(y*w+x)*4:(y*w+x+1)*4]*scale for x in range(w)) for y in range(h)]
            expected=b''.join(row*scale for row in rows)
            self.assertEqual(actual,(w*scale,h*scale,expected))
            tiff=self.cli('document.export',document=d,format='tiff',scale=scale,render_options=options,
                          image_options=dict(depth='u16',compression='deflate'))
            got,_=samples.decode(tiff)
            rows=[[v for x in range(w) for _ in range(scale) for v in values[(y*w+x)*4:(y*w+x+1)*4]] for y in range(h)]
            self.assertEqual(got,[v for row in rows for _ in range(scale) for v in row])
        self.assertEqual((self.root/'original.png').read_bytes(),source)
        self.assertEqual(d,before)

    def test_partial_bands_keep_compression_depth_channels_and_no_partial_publication(self):
        d=self.cli('document.create',kind='raster',id='gray',width=519,height=271)
        d['items']=[dict(id='fill',content=dict(type='samples',grid=dict(width=1,height=1,depth='u16',
            channels='gray_alpha',data_hex='3930ffff')),transform=[519,0,0,271,0,0])]
        d['items'] += [dict(id=f'outside-{i}',transform=[1,0,0,1,0,1000+i],
            content=dict(type='raster',width=1,height=1,rgba_hex='145096ff')) for i in range(128)]
        for depth in ('u8','u16','f32'):
            for channels in ('rgba','gray_alpha'):
                for compression in ('none','lzw','deflate'):
                    artifact=self.cli('document.export',document=d,format='tiff',render_options=dict(evaluation='tiled'),
                        image_options=dict(depth=depth,channels=channels,compression=compression))
                    if compression=='lzw':
                        # Independent decoder in these tests covers none/deflate;
                        # reimport verifies the external LZW codec path separately.
                        (self.root/'compressed.tiff').write_bytes(base64.b64decode(artifact['data']))
                        imported=self.cli('sample.import',source_path='compressed.tiff',id='again',storage={},color_policy='assume_srgb')['document']
                        artifact=self.cli('document.export',document=imported,format='tiff',render_options=dict(evaluation='tiled'),
                            image_options=dict(depth=depth,channels=channels,compression='none'))
                    actual,tags=samples.decode(artifact)
                    color=12345/65535
                    expected=round(color*255) if depth=='u8' else 12345 if depth=='u16' else struct.unpack('<f',struct.pack('<f',color))[0]
                    alpha=255 if depth=='u8' else 65535 if depth=='u16' else 1.0
                    self.assertEqual(actual,([expected]*(3 if channels=='rgba' else 1)+[alpha])*(519*271))
                    self.assertGreater(len(tags[273]),1)
        output=dict(file_name='cancelled.tiff',format='tiff',render_options=dict(evaluation='tiled'),image_options=dict(depth='u16'))
        self.cli('document.publish',document=d,output=output,control=dict(timeout_ms=0),error='TIMEOUT')
        self.assertFalse((self.root/'cancelled.tiff').exists())

    def test_wide_native_reconstruction_respects_work_and_cache_limits(self):
        w,h=2177,273
        d,original,source=self.imported_scene(w,h)
        expected=list(struct.unpack('<'+'H'*(w*h*4),original))
        for sampling in ('nearest','bilinear','area','bicubic','lanczos3'):
            d['items'][0]['content']['grid']['sampling']=sampling
            with self.subTest(sampling=sampling):
                if sampling=='lanczos3':
                    # Its conservative 128 units/pixel exceed the independent
                    # 67,108,864 reconstruction budget at the full extent.
                    # Preserve that rejection, then check every sample in a
                    # supported full-width region of the same immutable source.
                    failure=self.cli('document.export',document=d,format='tiff',render_options=dict(evaluation='tiled'),
                        image_options=dict(depth='u16',compression='deflate'),error='RESOURCE_LIMIT')
                    self.assertIn('aggregate reconstruction work',failure['message'])
                    # Leave room for spatial-index and source preparation work
                    # as well as the kernel itself, without changing any limit.
                    d['height']=192
                result=self.cli('document.export',document=d,format='tiff',render_options=dict(evaluation='tiled'),
                                image_options=dict(depth='u16',compression='deflate'))
                self.assertEqual(samples.decode(result)[0],expected[:w*d['height']*4])
        # A second supported region crosses the 256-row traversal boundary,
        # with the same wide source and reconstruction halo.
        d['width'],d['height']=1664,h
        result=self.cli('document.export',document=d,format='tiff',render_options=dict(evaluation='tiled'),
                        image_options=dict(depth='u16',compression='deflate'))
        region=[v for y in range(h) for v in expected[y*w*4:(y*w+1664)*4]]
        self.assertEqual(samples.decode(result)[0],region)
        self.assertEqual((self.root/'original.png').read_bytes(),source)


if __name__=='__main__':unittest.main()
