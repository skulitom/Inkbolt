"""Native brush precision, frozen transport, local buffers and pure history."""
import copy
from contextlib import closing
from fractions import Fraction as F
import hashlib
import struct
import unittest
import test_native_retouch as native
import test_pixel_brush_cli as legacy
from test_cli import EXE
from test_mcp import Client
from test_sample_conversion_cli import tiff
from test_samples_cli import packed
import native_brush_workload as workload


def pm(c,maximum=65535):
    a=F(c[-1])/maximum
    rgb=c[:3] if len(c)==4 else [c[0]]*3
    return [F(v)/maximum*a for v in rgb]+[a]


def encode(c):
    return [v/c[3]*65535 for v in c[:3]]+[c[3]*65535] if c[3] else [F(0)]*4


def texture(points):
    selected={(x%64,y%64) for x,y in points}
    return dict(width=64,height=64,gray_hex=bytes(255 if (x,y) in selected else 0 for y in range(64) for x in range(64)).hex())


class NativeBrushTests(unittest.TestCase):
    setUp=native.NativeRetouchTests.setUp
    cli=native.NativeRetouchTests.cli
    save=native.NativeRetouchTests.save
    imported=native.NativeRetouchTests.imported
    raw=native.NativeRetouchTests.raw
    files=native.NativeRetouchTests.files
    assert_codes=native.NativeRetouchTests.assert_codes

    def apply(self,d,stroke,**kwargs):
        return self.cli('document.edit',document=d,expected_revision=d['revision'],
            operations=[dict(op='brush_stroke',id='pixels',stroke=stroke)],**kwargs)

    def test_two_megapixel_four_mode_edit_and_exact_native_history(self):
        result=workload.run(native.measure.Case(EXE,self.root/'workload',workload.CASE,1))
        self.assertTrue(result['success'],result)
        self.assertEqual(result['process_calls'],7)
        self.assertEqual(result['blocked_steps'],0)

    def test_six_native_formats_inline_and_stored_erase_preserves_color_and_metadata(self):
        for depth in ['u8','u16','f32']:
            for n in [2,4]:
                alpha={'u8':240,'u16':60000,'f32':.5}[depth]
                colors=[((x+c+y)%8)/8 if depth=='f32' else (x+c+y)%128 for y in range(3) for x in range(131) for c in range(n-1)]
                values=[v for i in range(131*3) for v in colors[i*(n-1):(i+1)*(n-1)]+[alpha]]
                expected=list(values);expected[n-1::n]=[alpha*7/8 if depth=='f32' else int(alpha*7/8)]*(131*3)
                for stored in [False,True]:
                    d=self.imported(131,3,values,depth,n,stored);d["metadata"]={"title":"Original native fixture"};files=self.files()
                    s=legacy.brush([[65.5,1.5]],diameter=512,flow=.25,opacity=.5,mode=dict(type='erase'))
                    r=self.apply(d,s);self.assertEqual(self.raw(r['document']),bytes.fromhex(packed(expected,depth)))
                    self.assertEqual(self.files(),files)
                    self.assertEqual(r['document']['items'][0]['content']['type'],d['items'][0]['content']['type'])
                    self.assertEqual(r['document']['metadata'],d['metadata'])
                    receipt=r['changes'][0]['details'];self.assertEqual(receipt['working_window'],[0,0,131,3])
                    self.assertEqual(receipt['changed_pixels'],393);self.assertFalse(receipt['files_written'])
                    self.assertEqual(receipt['sample_type']['depth'],depth)
                    self.assertLessEqual(receipt['processing_memory_bound_bytes'],128*1024*1024)

    def test_high_depth_fractional_soft_tip_matches_independent_vertical_integrals(self):
        w,h=8,7;center=[3.23,3.8];diameter=6.1;hardness=.45
        s=legacy.brush([center],diameter=diameter,hardness=hardness,flow=.5,opacity=.75,mode=dict(type='paint',color=[100,30,210,180]))
        for depth in ['u16','f32']:
            maximum=65535 if depth=='u16' else 1
            source=([10000,20000,30000,50000] if depth=='u16' else [.125,.25,.5,.75])*(w*h)
            d=self.imported(w,h,source,depth=depth);raw=self.raw(self.apply(d,s)['document'])
            actual=struct.unpack('<'+('H' if depth=='u16' else 'f')*(w*h*4),raw)
            paint=legacy.pm(s['mode']['color']);expected=[]
            for y in range(h):
                for x in range(w):
                    a=source[(y*w+x)*4:(y*w+x+1)*4];alpha=a[3]/maximum
                    before=[v/maximum*alpha for v in a[:3]]+[alpha]
                    coverage=legacy.kernel_area(center,diameter,hardness,x,y)
                    out=legacy.lerp(before,legacy.over(before,paint,coverage*.5),.75)
                    colors=[v/out[3] for v in out[:3]]+[out[3]]
                    expected.extend(colors)
                    observed=actual[(y*w+x)*4:(y*w+x+1)*4];observed=[v/maximum for v in observed]
                    if depth=='f32':
                        # Compare premultiplied values; allowance includes the
                        # declared 1e-7 tip integration and final binary32 round.
                        actual_pm=[v*observed[3] for v in observed[:3]]+[observed[3]]
                        self.assertLessEqual(max(abs(a-b) for a,b in zip(actual_pm,out)),2e-7)
            if depth=='u16':self.assertEqual(list(actual),[int(v*65535+.5) for v in expected])

    def test_paint_and_mixer_quantize_all_six_formats_once_without_implicit_gray_conversion(self):
        caps=self.cli('capabilities')['pixel_brushes']
        self.assertEqual(caps['target'],['raster','samples','stored_samples'])
        self.assertEqual(caps['maximum_window_pixels'],65536)
        self.assertEqual(caps['maximum_processing_memory_bytes'],128*1024*1024)
        color=pm([85,85,85,128],255)
        for depth in ['u8','u16','f32']:
            maximum={'u8':255,'u16':65535,'f32':1}[depth]
            for n in [2,4]:
                original=([32]*(n-1)+[240] if depth=='u8' else
                          [10000]*(n-1)+[60000] if depth=='u16' else [.25]*(n-1)+[.5])
                before=pm(original,maximum)
                d=self.imported(2,1,original*2,depth,n)
                for mode in [dict(type='paint',color=[85,85,85,128]),dict(type='mixer',color=[85,85,85,128],pickup=.25,load=.5)]:
                    brush_color=color if mode['type']=='paint' else [(3*a+b)/4 for a,b in zip(color,before)]
                    value=[v*(1-brush_color[3]/8)+b/8 for v,b in zip(before,brush_color)]
                    straight=[v/value[3] for v in value[:3]]+[value[3]]
                    if n==2:straight=[straight[0],straight[3]]
                    s=legacy.brush([[1,.5]],diameter=8,flow=.25,opacity=.5,mode=mode)
                    raw=self.raw(self.apply(d,s)['document'])
                    if depth=='f32':self.assertEqual(raw,struct.pack('<'+'f'*(n*2),*map(float,straight*2)))
                    else:
                        actual=struct.unpack('<'+('B' if depth=='u8' else 'H')*(n*2),raw)
                        for observed,wanted in zip(actual,straight*2):
                            scaled=wanted*maximum;rounded=int(scaled+F(1,2))
                            self.assertIn(observed,[rounded,rounded-1] if scaled%1==F(1,2) else [rounded])

    def test_smudge_reads_immutable_donors_outside_window_and_real_image_borders(self):
        w,h=300,4
        values=[v for y in range(h) for x in range(w) for v in [x*101,y*501,10000,60000 if x%2 else 50000]]
        d=self.imported(w,h,values);original=self.raw(d)
        target=(130,1);a=pm(values[(w+130)*4:(w+131)*4])
        for first,border in [(40.5,'clamp'),(-20,'clamp'),(-20,'transparent')]:
            s=legacy.brush([[first,1.5],[130.75,1.5]],diameter=64,spacing=4,flow=.5,opacity=.5,
                mode=dict(type='smudge',border=border),texture=texture([target]))
            s['points'][0]['size']=0
            r=self.apply(d,s);receipt=r['changes'][0]['details']
            self.assertEqual(receipt['dab_count'],2);self.assertEqual(receipt['working_window'],[98,0,65,4])
            if first>0:
                left=pm(values[(w+39)*4:(w+40)*4]);right=pm(values[(w+40)*4:(w+41)*4])
                donor=[(x+3*y)/4 for x,y in zip(left,right)]
            elif border=='clamp':donor=pm(values[w*4:(w+1)*4])
            else:donor=[F(0)]*4
            wanted=encode([(3*x+y)/4 for x,y in zip(a,donor)])
            result=self.raw(r['document']);at=(w+130)*8
            self.assert_codes(result[at:at+8],[wanted])
            self.assertEqual(result[:at],original[:at]);self.assertEqual(result[at+8:],original[at+8:])

    def test_smudge_uses_each_frozen_dab_and_quantizes_only_after_whole_stroke(self):
        w=140;source=[[x*x+17,x*301,10000,65535] for x in range(w)]
        d=self.imported(w,1,[v for p in source for v in p]);selected=list(range(125,130))
        s=legacy.brush([[125,.5],[127,.5]],diameter=64,spacing=1/64,flow=.25,opacity=.5,
            mode=dict(type='smudge',border='clamp'),texture=texture([(x,0) for x in selected]))
        state={x:pm(p) for x,p in enumerate(source)};start=copy.deepcopy(state)
        for _ in range(2):
            frozen=copy.deepcopy(state)
            for x in selected:state[x]=[(3*a+b)/4 for a,b in zip(frozen[x],frozen[x-1])]
        expected=[encode([(a+b)/2 for a,b in zip(start[x],state[x])]) for x in range(w)]
        r=self.apply(d,s);self.assert_codes(self.raw(r['document']),expected)
        self.assertEqual(r['changes'][0]['details']['dab_count'],3)

    def test_native_selection_and_texture_keep_global_pixel_coordinates(self):
        w,h=140,4;source=[10000,20000,30000,60000]*(w*h)
        d=self.imported(w,h,source);d['width']=8;d['height']=4
        d['items'][0]['transform']=[1,0,0,1,-125,0]
        d['selection']=dict(width=8,height=4,gray_hex=bytes([128,255]*4*4).hex())
        s=legacy.brush([[129,2]],diameter=16,flow=.25,opacity=.5,use_selection=True,
            texture=dict(width=2,height=1,gray_hex='80ff',origin=[.5,0]),mode=dict(type='paint',color=[100,20,200,128]))
        result=self.apply(d,s);expected=[list(map(F,source[i:i+4])) for i in range(0,len(source),4)]
        a=pm(source[:4]);c=pm(s['mode']['color'],255)
        for y in range(h):
            for x in range(125,133):
                weight=F([128,255][x%2],255)*F([128,255][(x-125)%2],255)/8
                expected[y*w+x]=encode([v*(1-c[3]*weight)+b*weight for v,b in zip(a,c)])
        self.assert_codes(self.raw(result['document']),expected)
        self.assertEqual(result['document']['selection'],d['selection'])

    def test_noops_preserve_hidden_float_bits_and_color_domain_rejections_are_explicit(self):
        values=[-0.0,struct.unpack('<f',b'\1\0\0\0')[0],.5,0.0]*6
        d=self.imported(3,2,values,depth='f32');raw=self.raw(d)
        for extras in [dict(opacity=0),dict(flow=0),dict(mode=dict(type='paint',color=[10,20,30,0])),dict(points=[dict(point=[100,100])])]:
            stroke=legacy.brush([[1,1]]);stroke.update(extras)
            r=self.apply(d,stroke);self.assertEqual(r['document']['items'],d['items'])
            self.assertEqual(self.raw(r['document']),raw);self.assertEqual(r['changes'][0]['details']['changed_pixels'],0)
        gray=self.imported(3,2,[30000,65535]*6,n=2)
        self.apply(gray,legacy.brush([[1,1]]),error='GRAYSCALE_CONVERSION_REQUIRED')
        path=self.root/'linear.tiff';path.write_bytes(tiff(3,2,[.1,.2,.3,1.0]*6,depth='f32'))
        linear=self.cli('sample.import',source_path=str(path),id='linear',color_policy='assume_linear_srgb',storage={})['document']
        self.apply(linear,legacy.brush([[1,1]]),error='UNSUPPORTED_BRUSH_ENCODING')

    def test_mcp_dry_run_retry_undo_recovery_and_later_failure_write_no_blocks(self):
        d=self.imported(140,4,[10000,20000,30000,60000]*560);original=self.raw(d);self.save(d)
        s=legacy.brush([[128,2]],diameter=4,flow=.25)
        action=dict(type='edit',operations=[dict(op='brush_stroke',id='pixels',stroke=s)])
        blocks={p.name:p.read_bytes() for p in (self.root/'.inkbolt/assets').iterdir()};before=self.files()
        with closing(Client(('--tools','core'),workspace=self.root)) as c:
            c.initialize()
            proposal=c.success('session.dry_run',session_id='work',request_id='brush',expected_revision=0,action=action,options=dict(include_document=True))
            self.assertEqual(self.files(),before)
            saved=c.success('session.apply_proposal',proposal=proposal['proposal'],action=action)
            self.assertEqual(saved['document'],proposal['proposed_document']);self.assertEqual(saved['receipt'],proposal['predicted_receipt'])
            self.assertTrue(c.success('session.apply_proposal',proposal=proposal['proposal'],action=action)['replayed'])
            undone=c.success('session.apply',session_id='work',request_id='undo',expected_revision=1,action=dict(type='undo'))
            self.assertEqual(self.raw(undone['document']),original)
            redone=c.success('session.apply',session_id='work',request_id='redo',expected_revision=2,action=dict(type='redo'))
            self.assertEqual(self.raw(redone['document']),self.raw(saved['document']))
        backup=self.cli('session.backup',session_id='work',expected_revision=3,output=dict(file_name='backup.sqlite3'))
        self.cli('session.recover',session_id='work',session_root='recovered',source=backup['backup'])
        self.assertEqual(self.raw(self.cli('session.read',session_id='work',session_root='recovered')['document']),self.raw(saved['document']))
        self.cli('session.apply',session_id='work',request_id='fail',expected_revision=3,action=dict(type='edit',operations=action['operations']+[dict(op='remove',id='missing')]),error='NOT_FOUND')
        self.assertEqual(self.cli('session.read',session_id='work')['document'],redone['document'])
        self.assertEqual({p.name:p.read_bytes() for p in (self.root/'.inkbolt/assets').iterdir()},blocks)

    def test_corrupt_unselected_blocks_cancellation_locks_and_patch_limits_reject_atomically(self):
        d=self.imported(132,132,[10000,20000,30000,60000]*(132*132));s=legacy.brush([[1,1]],diameter=2)
        self.apply(d,s,control=dict(timeout_ms=0),error='TIMEOUT')
        locked=copy.deepcopy(d);locked['items'][0]['locked']=True;self.apply(locked,s,error='LOCKED')
        patched=copy.deepcopy(d);g=patched['items'][0]['content']['grid']
        g['patches']=[dict(region=dict(x=0,y=0,width=1,height=1),data_hex=packed([1,2,3,65535],'u16'))]*256
        self.apply(patched,s,error='RESOURCE_LIMIT')
        path=self.root/'.inkbolt/assets'/f"{d['items'][0]['content']['grid']['base']['tiles'][-1]}.native-tile"
        raw=bytearray(path.read_bytes());raw[-2]^=1;path.write_bytes(raw)
        before=self.files();self.apply(d,s,error='SAMPLE_TILE_CORRUPT');self.assertEqual(self.files(),before)

    def test_window_and_replacement_memory_limits_fail_before_missing_resource_reads(self):
        d=self.cli('document.create',id='bounded',kind='raster',resource_profile='large_raster',width=256,height=32768)
        spec=dict(width=256,height=32768,depth='f32',channels='rgba',encoding='encoded_srgb');tiles=['0'*64]*512
        header=b'INKTILE1'+struct.pack('<IIBBBB',256,32768,4,4,0,0)
        identity=hashlib.sha256(b'INKGRID1'+header+struct.pack('<I',128)+bytes(32)*512).hexdigest()
        d['items']=[dict(id='pixels',content=dict(type='stored_samples',grid=dict(base=dict(version=1,spec=spec,tiles=tiles,sha256=identity))))]
        before=self.files()
        s=legacy.brush([[128,1.5],[128,32765.5]],diameter=1,spacing=4)
        error=self.apply(d,s,error='RESOURCE_LIMIT');self.assertIn('memory bound',error['message'])
        error=self.apply(d,legacy.brush([[128,256]],diameter=512),error='RESOURCE_LIMIT')
        self.assertIn('local edit window',error['message']);self.assertEqual(self.files(),before)


if __name__=='__main__':unittest.main()
