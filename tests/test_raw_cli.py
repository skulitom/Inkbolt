"""Original sensor fixtures; exact rational interpolation and independent colour equations."""
import base64
import copy
from decimal import Decimal as D, localcontext
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import test_editing_cli as editing
from test_editing_cli import png_pixels
from test_sample_conversion_cli import values
from test_samples_cli import decode
from test_mcp import Client


PATTERNS = {'rggb': (0, 1, 1, 2), 'grbg': (1, 0, 2, 1),
            'gbrg': (1, 2, 0, 1), 'bggr': (2, 1, 1, 0)}


def fixture(w=7, h=5, pattern='rggb', packing='u16_le', padding=3, signal=None):
    black = [10, 14, 20, 22]
    white = [v + 128 for v in black]
    size = 1 if packing == 'u8' else 2
    capture = dict(width=w, height=h, pattern=pattern, packing=packing,
                   row_stride=w*size+padding, black=black, white=white,
                   camera_to_linear_srgb=[[1, 0, 0], [0, 1, 0], [0, 0, 1]])
    signal = signal or (lambda x, y, c: 8+2*x+4*y+8*c)
    data = bytearray(); codes = []
    for y in range(h):
        for x in range(w):
            site = y % 2*2+x % 2
            v = black[site]+signal(x, y, PATTERNS[pattern][site])
            codes.append(v)
            data.extend(struct.pack({'u8': 'B', 'u16_le': '<H', 'u16_be': '>H'}[packing], v))
        data.extend(bytes([241])*padding)
    return bytes(data), capture, codes


def settings(**kw):
    result = dict(exposure_stops=0, white_balance=dict(type='gains', rgb=[1, 1, 1]),
                  output='linear_srgb32', range='preserve', resolution_ppi=144)
    result.update(kw)
    return result


def reference(capture, codes, options):
    """Separate stencil formulation, exact calibration/matrix, no engine helpers."""
    w, h = capture['width'], capture['height']; colors = PATTERNS[capture['pattern']]
    def site(x, y): return y % 2*2+x % 2
    def sample(x, y):
        i = site(x, y)
        return (F(codes[y*w+x])-F(capture['black'][i]))/(F(capture['white'][i])-F(capture['black'][i]))
    gain = list(map(F, options['white_balance']['rgb']))
    if options['white_balance']['type'] == 'neutral': gain = [gain[1]/v for v in gain]
    output = []
    for y in range(h):
        for x in range(w):
            rgb = []
            for c in range(3):
                if colors[site(x, y)] == c:
                    v = sample(x, y)
                else:
                    # Missing green is a cross; opposite red/blue is diagonal.
                    offsets = ([(0, -1), (-1, 0), (1, 0), (0, 1)] if c == 1 or colors[site(x, y)] == 1
                               else [(-1, -1), (1, -1), (-1, 1), (1, 1)])
                    neighbors = [sample(x+dx, y+dy) for dx, dy in offsets
                                 if 0 <= x+dx < w and 0 <= y+dy < h and colors[site(x+dx, y+dy)] == c]
                    v = sum(neighbors)/len(neighbors)
                rgb.append(v*gain[c])
            row = [float(sum(F(m)*v for m, v in zip(matrix, rgb)))*2**options['exposure_stops']
                   for matrix in capture['camera_to_linear_srgb']]
            output.extend(row+[1.0])
    return output


def floats(values):
    return list(struct.unpack('<'+'f'*len(values),struct.pack('<'+'f'*len(values),*values)))


def encoded(v, bits):
    with localcontext() as ctx:
        ctx.prec = 50
        v = max(D(0), min(D(1), D(str(v))))
        v = v*D('12.92') if v <= D('.0031308') else D('1.055')*v**(D(5)/D(12))-D('.055')
        return int(v*((1 << bits)-1)+D('.5'))


class RawTests(unittest.TestCase):
    invoke = editing.EditingCliTests.invoke

    def develop(self, data, capture, options=None, expected=0, **kw):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root)/'original.sensor';p.write_bytes(data)
            r = self.invoke(dict(command='raw.develop',source_path=str(p),id='raw-fixture',
                                 capture=capture,settings=options or settings(),**kw),expected)
            self.assertEqual(p.read_bytes(),data)
            self.assertEqual(list(Path(root).iterdir()),[p])
            if not expected:
                self.assertFalse(r['source_changed']);self.assertEqual(r['source_sha256'],hashlib.sha256(data).hexdigest())
                self.assertEqual(r['source_bytes'],len(data));self.assertEqual(r['recipe']['capture'],capture)
                self.assertEqual(r['recipe']['settings'],options or settings())
            return r

    def test_all_four_patterns_three_packings_odd_dimensions_and_padding(self):
        for pattern in PATTERNS:
            for packing in ('u8','u16_le','u16_be'):
                for w,h in [(2,2),(3,5),(7,4)]:
                    data,capture,codes=fixture(w,h,pattern,packing)
                    result=self.develop(data,capture);actual=values(result['document'])
                    self.assertEqual(actual,floats(reference(capture,codes,settings())))
                    self.assertEqual(result['document']['resolution_ppi'],144)
                    self.assertEqual(result['diagnostics']['clipped_channels'],0)

    def test_interior_affine_fields_reconstruct_and_native_sites_remain_exact(self):
        for pattern in PATTERNS:
            data,capture,codes=fixture(pattern=pattern)
            actual=values(self.develop(data,capture)['document'])
            for y in range(5):
                for x in range(7):
                    c=PATTERNS[pattern][y%2*2+x%2]
                    self.assertEqual(actual[(y*7+x)*4+c],(8+2*x+4*y+8*c)/128)
                    if 0<x<6 and 0<y<4:
                        self.assertEqual(actual[(y*7+x)*4:(y*7+x)*4+3],[(8+2*x+4*y+8*c)/128 for c in range(3)])

    def test_irregular_sensor_codes_and_nonintegral_site_levels(self):
        for pattern in PATTERNS:
            data,capture,codes=fixture(9,11,pattern,signal=lambda x,y,c:(x*37+y*53+c*19)%129)
            capture['black']=[10.5,14.25,20.75,22.125]
            capture['white']=[139.25,147.75,151.125,161.5]
            expected=reference(capture,codes,settings())
            actual=values(self.develop(data,capture)['document'])
            for a,e in zip(actual,expected):self.assertAlmostEqual(a,e,delta=max(1e-9,abs(e)*6e-8))

    def test_maximum_supported_buffer_returns_a_reusable_bounded_document(self):
        data,capture,_=fixture(128,128,padding=0,signal=lambda x,y,c:64)
        d=self.develop(data,capture)['document']
        self.assertEqual(values(d),[.5,.5,.5,1]*16384)
        self.assertLess(len(json.dumps(d).encode()),768*1024)
        self.assertEqual(self.invoke(dict(command='document.validate',document=d)),d)

    def test_matrix_white_balance_and_exposure_order(self):
        data,capture,codes=fixture()
        capture['camera_to_linear_srgb']=[[1.25,-.5,.25],[.125,.75,.125],[-.25,.25,1]]
        for balance in [dict(type='gains',rgb=[1.5,.75,2]),dict(type='neutral',rgb=[.25,.75,.5])]:
            for exposure in [-2,.5,3]:
                opts=settings(exposure_stops=exposure,white_balance=balance)
                actual=values(self.develop(data,capture,opts)['document']);wanted=reference(capture,codes,opts)
                for v,e in zip(actual,wanted):self.assertAlmostEqual(v,e,delta=max(1e-8,abs(e)*6e-8))

    def test_neutral_reference_is_gray_in_linear_camera_space(self):
        data,capture,_=fixture(signal=lambda x,y,c:[16,64,32][c])
        opts=settings(white_balance=dict(type='neutral',rgb=[.125,.5,.25]))
        r=self.develop(data,capture,opts)
        self.assertEqual(r['diagnostics']['effective_white_balance'],[4,1,2])
        self.assertEqual(values(r['document']),[.5,.5,.5,1]*35)

    def test_signed_radiance_clipping_and_saturation_diagnostics(self):
        data,capture,codes=fixture(signal=lambda x,y,c: -8 if x%3==0 else 160 if x%3==1 else 0)
        opts=settings(exposure_stops=1);wanted=reference(capture,codes,opts)
        r=self.develop(data,capture,opts);diag=r['diagnostics']
        self.assertEqual(values(r['document']),floats(wanted))
        self.assertEqual(diag['below_black_samples'],sum(v<capture['black'][y%2*2+x%2] for y in range(5) for x,v in enumerate(codes[y*7:y*7+7])))
        self.assertEqual(diag['at_or_above_white_samples'],10)
        channels=[v for i,v in enumerate(wanted) if i%4!=3]
        self.assertEqual(diag['below_zero_channels'],sum(v<0 for v in channels))
        self.assertEqual(diag['above_one_channels'],sum(v>1 for v in channels))
        self.assertEqual(diag['linear_rgb_minimum'],[min(wanted[c::4]) for c in range(3)])
        self.assertEqual(diag['linear_rgb_maximum'],[max(wanted[c::4]) for c in range(3)])
        opts['range']='clip';clipped=self.develop(data,capture,opts)
        self.assertEqual(values(clipped['document']),floats([max(0,min(1,v)) for v in wanted]))
        self.assertEqual(clipped['diagnostics']['clipped_channels'],sum(v<0 or v>1 for v in channels))

    def test_output_encoding_native_tiff_png_and_resolution(self):
        data,capture,codes=fixture(signal=lambda x,y,c: 1+3*x+5*y+11*c)
        for output,bits in [('srgb8',8),('srgb16',16)]:
            opts=settings(output=output,range='clip',resolution_ppi=300,exposure_stops=-1)
            d=self.develop(data,capture,opts)['document'];wanted=reference(capture,codes,opts)
            native=[encoded(v,bits) if i%4!=3 else (1<<bits)-1 for i,v in enumerate(wanted)]
            self.assertEqual(values(d),native)
            artifact=self.invoke(dict(command='document.export',document=d,format='tiff',image_options=dict(depth=f'u{bits}',channels='rgba')))
            actual,tags=decode(artifact);self.assertEqual(actual,native)
            self.assertEqual(F(*tags[282]),300);self.assertEqual(F(*tags[283]),300)
            png=self.invoke(dict(command='document.export',document=d,format='png'))
            w,h,pixels,chunks=png_pixels(base64.b64decode(png['data']))
            expected=native if bits==8 else [int(F(v*255,65535)+F(1,2)) for v in native]
            self.assertEqual(pixels,bytes(expected));self.assertEqual((w,h),(7,5));self.assertIn(b'sRGB',chunks)

    def test_float_tiff_snapshot_and_repeatable_source_pin(self):
        data,capture,codes=fixture(signal=lambda x,y,c:2*x+4*y+8*c)
        opts=settings(exposure_stops=3)
        result=self.develop(data,capture,opts,expected_sha256=hashlib.sha256(data).hexdigest().upper())
        d=result['document'];self.assertEqual(result,self.develop(data,capture,opts))
        artifact=self.invoke(dict(command='document.export',document=d,format='tiff',image_options=dict(depth='f32',channels='rgba')))
        actual,_=decode(artifact);self.assertEqual(actual,floats(reference(capture,codes,opts)))
        snapshot=self.invoke(dict(command='document.export',document=d,format='snapshot'))
        self.assertEqual(json.loads(snapshot['data']),d)
        self.assertEqual(self.develop(data,capture,opts,expected=1,expected_sha256='0'*64)['code'],'SOURCE_MISMATCH')

    def test_invalid_calibration_dimensions_layout_and_output_fail_without_writes(self):
        data,capture,_=fixture()
        bad=[]
        for key,v in [('width',1),('height',0),('row_stride',1),('row_stride',999999),('black',[10]*4),('white',[0]*4),('camera_to_linear_srgb',[[1]*3]*3)]:
            c=copy.deepcopy(capture);c[key]=v
            if key=='black':c['white']=[10]*4
            bad.append(c)
        for c in bad:self.assertEqual(self.develop(data,c,expected=1)['code'],'INVALID_RAW')
        for opts in [settings(exposure_stops=33),settings(resolution_ppi=0),settings(white_balance=dict(type='gains',rgb=[0,1,1])),settings(white_balance=dict(type='neutral',rgb=[.000001,1,1]))]:
            self.assertEqual(self.develop(data,capture,opts,expected=1)['code'],'INVALID_RAW')
        self.assertEqual(self.develop(data,capture,settings(output='srgb8'),expected=1)['code'],'UNSUPPORTED_RAW_OUTPUT')
        self.assertEqual(self.develop(data[:-1],capture,expected=1)['code'],'INVALID_RAW')
        self.assertEqual(self.develop(data+b'x',capture,expected=1)['code'],'RESOURCE_LIMIT')
        self.assertEqual(self.develop(data,capture,expected=1,expected_sha256='not-a-hash')['code'],'INVALID_RAW')
        c=copy.deepcopy(capture);c['width']=c['height']=129;c['row_stride']=258
        self.assertEqual(self.develop(data,c,expected=1)['code'],'RESOURCE_LIMIT')

    def test_missing_explicit_controls_unknown_fields_and_cancellation(self):
        data,capture,_=fixture()
        for location,key in [('capture','black'),('capture','camera_to_linear_srgb'),('settings','white_balance'),('settings','range'),('settings','output')]:
            c=copy.deepcopy(capture);s=settings();del {'capture':c,'settings':s}[location][key]
            self.assertEqual(self.develop(data,c,s,expected=1)['code'],'INVALID_REQUEST')
        c=copy.deepcopy(capture);c['container']='auto'
        self.assertEqual(self.develop(data,c,expected=1)['code'],'INVALID_REQUEST')
        self.assertEqual(self.develop(data,capture,expected=1,control=dict(timeout_ms=0))['code'],'TIMEOUT')
        with tempfile.TemporaryDirectory() as root:
            marker=Path(root)/'cancel';marker.write_bytes(b'')
            self.assertEqual(self.develop(data,capture,expected=1,control=dict(cancel_file=str(marker)))['code'],'CANCELLED')

    def test_mcp_discovery_development_and_editable_session_roundtrip(self):
        data,capture,_=fixture();client=Client();self.addCleanup(client.close);client.initialize()
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'original.sensor';p.write_bytes(data)
            args=dict(source_path=str(p),id='raw-fixture',capture=capture,settings=settings())
            r=client.success('raw.develop',**args)
            self.assertEqual(r,self.invoke(dict(command='raw.develop',**args)))
            d=r['document'];snapshot=client.success('document.export',document=d,format='snapshot')
            self.assertEqual(json.loads(snapshot['data']),d)
            c=client.success('capabilities');self.assertIn('raw.develop',c['commands'])
            self.assertEqual(c['raw_development']['algorithm'],r['recipe']['algorithm'])
            session=dict(session_root=str(Path(root)/'sessions'),session_id='raw')
            client.success('session.create',**session,request_id='create',document=d)
            action=dict(type='edit',operations=[dict(op='properties',id='developed',opacity=.5)])
            edited=client.success('session.apply',**session,request_id='edit',expected_revision=0,action=action)
            self.assertEqual(edited['document']['items'][0]['content'],d['items'][0]['content'])
            undo=client.success('session.apply',**session,request_id='undo',expected_revision=1,action=dict(type='undo'))
            self.assertEqual(undo['document'],dict(d,revision=2))
            redo=client.success('session.apply',**session,request_id='redo',expected_revision=2,action=dict(type='redo'))
            self.assertEqual(client.success('session.read',**session)['document'],redo['document'])
            self.assertTrue(client.success('session.apply',**session,request_id='edit',expected_revision=0,action=action)['replayed'])
            self.assertEqual(p.read_bytes(),data)


if __name__=='__main__':unittest.main()
