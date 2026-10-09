"""Exact native bytes, rational sampling and independent dense healing systems."""
import copy
from contextlib import closing
from fractions import Fraction as F
import hashlib
from pathlib import Path
import struct
import sys
import unittest
import test_agent_workspace as workspace
import test_retouch_cli as legacy
from test_cli import EXE
from test_mcp import Client
from test_sample_conversion_cli import tiff
from test_samples_cli import packed
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import measure_workloads as measure
import native_retouch_workload as workload


def oracle(target,source,w,h,options):
    """Exact rational reference; independent dense elimination, no sparse solver."""
    maximum=65535
    def pm(p):
        a=F(p[3],maximum)
        return [F(c,maximum)*a for c in p[:3]]+[a]
    def sample(x,y):
        x-=F(1,2);y-=F(1,2);ix=x//1;iy=y//1;fx=x-ix;fy=y-iy
        out=[F(0)]*4
        for xx,yy,weight in [(ix,iy,(1-fx)*(1-fy)),(ix+1,iy,fx*(1-fy)),(ix,iy+1,(1-fx)*fy),(ix+1,iy+1,fx*fy)]:
            if not weight: continue
            if options.get('border')=='clamp': xx=max(0,min(w-1,xx));yy=max(0,min(h-1,yy))
            if 0<=xx<w and 0<=yy<h:
                out=[a+weight*b for a,b in zip(out,pm(source[yy*w+xx]))]
            else: assert options.get('border')=='transparent'
        return out
    r=options['region'];mask=bytes.fromhex(r['gray_hex']) if r.get('gray_hex') else bytes([255])*r['width']*r['height']
    weights={y*w+x:F(mask[(y-r['y'])*r['width']+x-r['x']],255) for y in range(r['y'],r['y']+r['height']) for x in range(r['x'],r['x']+r['width'])}
    weights={i:v for i,v in weights.items() if v};ids=list(weights);lookup={i:j for j,i in enumerate(ids)}
    adjacent=lambda i:legacy.adjacent(i,w,h)
    needed=set(ids)
    if options['mode']['type']=='heal': needed.update(j for i in ids for j in adjacent(i))
    m=list(map(F,options.get('source_transform',[1,0,0,1,0,0])))
    field={}
    for i in needed:
        x,y=F(i%w)+F(1,2),F(i//w)+F(1,2)
        field[i]=sample(m[0]*x+m[2]*y+m[4],m[1]*x+m[3]*y+m[5])
    before=list(map(pm,target));values={i:field[i][:] for i in ids}
    if options['mode']['type']=='heal' and ids:
        matrix=[]
        for i in ids:
            row=[F(0)]*len(ids);row[lookup[i]]=len(adjacent(i))+F(options['mode'].get('screening',0))
            for j in adjacent(i):
                if j in lookup:row[lookup[j]]-=1
            matrix.append(row)
        for c in range(4):
            rhs=[sum((before[j][c]-field[j][c] for j in adjacent(i) if j not in weights),F(0)) for i in ids]
            for i,v in zip(ids,legacy.dense_solve(matrix,rhs)):values[i][c]+=v
    result=[list(map(F,p)) for p in target]
    for i in ids:
        p=values[i];a=max(F(0),min(F(1),p[3]));p=[max(F(0),min(a,c)) for c in p[:3]]+[a]
        strength=weights[i]*F(options.get('opacity',1))
        p=[a+(b-a)*strength for a,b in zip(before[i],p)]
        if p!=before[i]:result[i]=[c/p[3]*maximum for c in p[:3]]+[p[3]*maximum] if p[3] else [F(0)]*4
    return result


class NativeRetouchTests(unittest.TestCase):
    setUp=workspace.AgentWorkspaceTests.setUp
    cli=workspace.AgentWorkspaceTests.cli
    save=workspace.AgentWorkspaceTests.save
    ref=workspace.AgentWorkspaceTests.ref

    def imported(self,w,h,values,depth='u16',n=4,stored=True,**kwargs):
        path=self.root/f'source-{len(list(self.root.glob("source-*")))}.tiff'
        path.write_bytes(tiff(w,h,values,depth=depth,n=n))
        args=dict(source_path=str(path),id='retouch',color_policy='assume_srgb',**kwargs)
        if stored:args['storage']={}
        return self.cli('sample.import',**args)['document']

    def raw(self,d,index=0):
        content=d['items'][index]['content']
        if content['type']=='raster':return bytes.fromhex(content['rgba_hex'])
        g=content['grid']
        if content['type']=='samples':return bytes.fromhex(g['data_hex'])
        spec=g['base']['spec'];w,h=spec['width'],spec['height'];stride={'u8':1,'u16':2,'f32':4}[spec['depth']]*(4 if spec['channels']=='rgba' else 2)
        data=bytearray(w*h*stride);columns=(w+127)//128
        for i,name in enumerate(g['base']['tiles']):
            raw=(self.root/'.inkbolt/assets'/f'{name}.native-tile').read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),name)
            tw,th=struct.unpack_from('<II',raw,8);x,y=i%columns*128,i//columns*128
            for row in range(th):
                at=((y+row)*w+x)*stride;data[at:at+tw*stride]=raw[20+row*tw*stride:20+(row+1)*tw*stride]
        for patch in g.get('patches',[]):
            r=patch['region'];raw=bytes.fromhex(patch['data_hex'])
            for row in range(r['height']):
                at=((r['y']+row)*w+r['x'])*stride;data[at:at+r['width']*stride]=raw[row*r['width']*stride:(row+1)*r['width']*stride]
        return bytes(data)

    def files(self):
        return {str(p.relative_to(self.root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.rglob('*') if p.is_file()}

    def apply(self,d,options,**kwargs):
        return self.cli('document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='retouch',id='pixels',options=options)],**kwargs)

    def options(self,**kwargs):
        return dict(source_id='pixels',region=dict(x=127,y=1,width=5,height=3),mode=dict(type='clone'),source_transform=[1,0,0,1,-2,0],**kwargs)

    def assert_codes(self,raw,expected):
        actual=struct.unpack('<'+'H'*(len(raw)//2),raw)
        expected=[c for p in expected for c in p]
        self.assertEqual(len(actual),len(expected))
        for actual,wanted in zip(actual,expected):
            rounded=(wanted+F(1,2))//1
            allowed=[rounded,rounded-1] if wanted%1==F(1,2) else [rounded]
            self.assertIn(actual,allowed)

    def test_full_two_megapixel_clone_heal_and_native_history(self):
        result=workload.run(measure.Case(EXE,self.root/'workload',workload.CASE,1))
        self.assertTrue(result['success'],result)
        self.assertEqual(result['process_calls'],7)
        self.assertEqual(result['blocked_steps'],0)

    def test_six_native_formats_clone_overlapping_frozen_samples_across_blocks(self):
        for depth in ['u8','u16','f32']:
            for n in [2,4]:
                maximum={'u8':255,'u16':65535,'f32':1}[depth]
                pixels=[]
                for y in range(5):
                    for x in range(138):
                        colors=[((x+c*3+y)%16)*maximum//16 for c in range(n-1)] if depth!='f32' else [((x+c*3+y)%16)/16 for c in range(n-1)]
                        alpha=maximum if x%3 else (.5 if depth=='f32' else maximum//2)
                        pixels.extend(colors+[alpha])
                for stored in [False,True]:
                    d=self.imported(138,5,pixels,depth,n,stored);original=self.raw(d);files=self.files()
                    result=self.apply(d,self.options());after=result['document'];expected=bytearray(original)
                    stride=n*{'u8':1,'u16':2,'f32':4}[depth]
                    for y in range(1,4):
                        for x in range(127,132):
                            a=(y*138+x)*stride;b=(y*138+x-2)*stride
                            expected[a:a+stride]=original[b:b+stride]
                    self.assertEqual(self.raw(after),expected)
                    self.assertEqual(self.raw(d),original);self.assertEqual(self.files(),files)
                    receipt=result['changes'][0]['details']
                    self.assertEqual(receipt['working_window'],[126,0,7,5]);self.assertFalse(receipt['files_written'])
                    self.assertEqual(receipt['changed_bounds'],[127,1,132,4])

    def test_rational_affine_clone_and_dense_healing_with_alpha_and_hole_mask(self):
        w,h=6,5
        target=[[5000+(x*73+y*19)%27000,9000+x*53,17000+y*307,45000+x*83] for y in range(h) for x in range(w)]
        source=[[7000+y*701,14000+x*133,11000+x*y*193,42000+y*307] for y in range(h) for x in range(w)]
        for mode in ['clone','heal']:
            for stored in [False,True]:
                d=self.imported(w,h,[v for p in target for v in p],stored=stored)
                src=self.imported(w,h,[v for p in source for v in p],stored=not stored)['items'][0]
                src['id']='source';src['visible']=False;d['items'].append(src)
                options=dict(source_id='source',region=dict(x=1,y=1,width=3,height=3,gray_hex='ff8040ff00ffffff80'),mode=dict(type=mode,**(dict(tolerance=1e-12,screening=.25) if mode=='heal' else {})),source_transform=[1,.25,.5,1,-.375,.125],border='clamp',opacity=.625)
                expected=oracle(target,source,w,h,options);files=self.files()
                result=self.apply(d,options);self.assert_codes(self.raw(result['document']),expected)
                self.assertEqual(result['document']['items'][1],src);self.assertEqual(self.files(),files)
                receipt=result['changes'][0]['details'];self.assertEqual(receipt['region_bounds'],[1,1,4,4])
                self.assertEqual(receipt['components'],1);self.assertEqual(receipt['boundary_edges'],16)
                self.assertTrue(all(v<=1e-12 for v in receipt['solver_residuals']))

    def test_noop_preserves_hidden_float_bits_and_invalid_color_domains_reject(self):
        values=[-0.0,struct.unpack('<f',b'\1\0\0\0')[0],.5,0.0]*6
        d=self.imported(3,2,values,depth='f32');raw=self.raw(d)
        options=dict(source_id='pixels',region=dict(x=0,y=0,width=3,height=2),mode=dict(type='clone'))
        for extras in [{},dict(opacity=0,source_transform=[1,0,0,1,9999,0])]:
            result=self.apply(d,dict(options,**extras))
            self.assertEqual(result['document']['items'],d['items']);self.assertEqual(self.raw(result['document']),raw)
            self.assertEqual(result['changes'][0]['details']['changed_pixels'],0)
        gray=self.imported(3,2,[30000,65535]*6,n=2)
        src=self.imported(3,2,[10000,20000,30000,65535]*6)['items'][0];src['id']='source';gray['items'].append(src)
        self.apply(gray,dict(options,source_id='source'),error='GRAYSCALE_CONVERSION_REQUIRED')
        # Import a valid linear descriptor rather than changing a pinned manifest.
        path=self.root/'linear.tiff';path.write_bytes(tiff(3,2,[.1,.2,.3,1.0]*6,depth='f32'))
        linear=self.cli('sample.import',source_path=str(path),id='linear',color_policy='assume_linear_srgb',storage={})['document']
        self.apply(linear,options,error='UNSUPPORTED_RETOUCH_ENCODING')

    def test_mcp_proposal_retry_undo_backup_and_later_failure_write_no_native_blocks(self):
        d=self.imported(138,5,[v for y in range(5) for x in range(138) for v in [x*307,y*701,15000,65535]])
        original=self.raw(d);self.save(d)
        action=dict(type='edit',operations=[dict(op='retouch',id='pixels',options=self.options())])
        blocks={p.name:p.read_bytes() for p in (self.root/'.inkbolt/assets').iterdir()}
        before=self.files()
        with closing(Client(('--tools','core'),workspace=self.root)) as c:
            c.initialize()
            proposal=c.success('session.dry_run',session_id='work',request_id='retouch',expected_revision=0,action=action,options=dict(include_document=True))
            self.assertEqual(self.files(),before)
            saved=c.success('session.apply_proposal',proposal=proposal['proposal'],action=action)
            self.assertEqual(saved['document'],proposal['proposed_document']);self.assertEqual(saved['receipt'],proposal['predicted_receipt'])
            self.assertTrue(c.success('session.apply_proposal',proposal=proposal['proposal'],action=action)['replayed'])
            self.assertNotEqual(self.raw(saved['document']),original)
            undone=c.success('session.apply',session_id='work',request_id='undo',expected_revision=1,action=dict(type='undo'))
            self.assertEqual(self.raw(undone['document']),original)
            redone=c.success('session.apply',session_id='work',request_id='redo',expected_revision=2,action=dict(type='redo'))
            self.assertEqual(self.raw(redone['document']),self.raw(saved['document']))
        backup=self.cli('session.backup',session_id='work',expected_revision=3,output=dict(file_name='backup.sqlite3'))
        self.cli('session.recover',session_id='work',session_root='recovered',source=backup['backup'])
        recovered=self.cli('session.read',session_id='work',session_root='recovered')['document']
        self.assertEqual(self.raw(recovered),self.raw(saved['document']))
        self.cli('session.apply',session_id='work',request_id='fail',expected_revision=3,action=dict(type='edit',operations=action['operations']+[dict(op='remove',id='missing')]),error='NOT_FOUND')
        self.assertEqual(self.cli('session.read',session_id='work')['document'],redone['document'])
        self.assertEqual({p.name:p.read_bytes() for p in (self.root/'.inkbolt/assets').iterdir()},blocks)

    def test_unselected_corruption_cancellation_locks_and_patch_limits_are_atomic(self):
        d=self.imported(132,132,[v for y in range(132) for x in range(132) for v in [x*307,y*307,15000,65535]])
        options=dict(source_id='pixels',region=dict(x=1,y=1,width=2,height=2),mode=dict(type='clone'),source_transform=[1,0,0,1,-1,0])
        self.apply(d,options,control=dict(timeout_ms=0),error='TIMEOUT')
        locked=copy.deepcopy(d);locked['items'][0]['locked']=True;self.apply(locked,options,error='LOCKED')
        blocked=copy.deepcopy(d);g=blocked['items'][0]['content']['grid']
        g['patches']=[dict(region=dict(x=0,y=0,width=1,height=1),data_hex=packed([1,2,3,65535],'u16'))]*256
        self.apply(blocked,options,error='RESOURCE_LIMIT')
        path=self.root/'.inkbolt/assets'/f"{d['items'][0]['content']['grid']['base']['tiles'][-1]}.native-tile"
        raw=bytearray(path.read_bytes());raw[-2]^=1;path.write_bytes(raw)
        before=self.files();self.apply(d,options,error='SAMPLE_TILE_CORRUPT');self.assertEqual(self.files(),before)

    def test_skinny_maximum_region_has_true_image_edges_and_bounded_window(self):
        w,h=32768,4
        d=self.imported(w,h,[v for y in range(h) for x in range(w) for v in [x,y*7001,5000,65535]])
        # The exact 65536-pixel RGBA16 patch occupies more than the standard
        # snapshot allowance once encoded. Use the existing explicit profile.
        d['resource_profile']='large_raster'
        d=self.cli('document.validate',document=d)
        original=self.raw(d)
        options=dict(source_id='pixels',region=dict(x=0,y=1,width=w,height=2),mode=dict(type='clone'),source_transform=[1,0,0,1,0,-1])
        result=self.apply(d,options);expected=bytearray(original);expected[w*8:3*w*8]=original[:2*w*8]
        self.assertEqual(self.raw(result['document']),expected)
        receipt=result['changes'][0]['details'];self.assertEqual(receipt['working_window'],[0,0,w,h])
        self.assertEqual(receipt['image_edge_faces'],4);self.assertEqual(receipt['boundary_edges'],2*w)
        self.apply(d,dict(options,region=dict(x=0,y=0,width=w,height=3)),error='RESOURCE_LIMIT')

    def test_native_selection_uses_global_centers_and_ignores_source_appearance(self):
        w,h=138,5
        d=self.imported(w,h,[v for y in range(h) for x in range(w) for v in [x*307,y*701,15000,65535]])
        original=self.raw(d);source=copy.deepcopy(d['items'][0])
        source.update(id='source',locked=True,visible=False,opacity=.1,transform=[2,0,0,2,500,600])
        d['items'].append(source);d['items'][0]['transform']=[1,0,0,1,-125,0]
        d['width']=7;d['height']=5
        d['selection']=dict(width=7,height=5,gray_hex=bytes(255 if x%2==0 else 0 for y in range(5) for x in range(7)).hex())
        options=dict(self.options(),source_id='source',use_selection=True)
        result=self.apply(d,options);expected=bytearray(original)
        for y in range(1,4):
            for x in [127,129,131]:
                a=(y*w+x)*8;b=(y*w+x-2)*8;expected[a:a+8]=original[b:b+8]
        self.assertEqual(self.raw(result['document']),expected)
        self.assertEqual(result['document']['items'][1],source)
        self.assertEqual(result['document']['selection'],d['selection'])

    def test_replacement_block_memory_rejects_before_reading_missing_resources(self):
        d=self.cli('document.create',id='bounded',kind='raster',resource_profile='large_raster',width=256,height=32768)
        spec=dict(width=256,height=32768,depth='f32',channels='rgba',encoding='encoded_srgb')
        tiles=['0'*64]*512
        header=b'INKTILE1'+struct.pack('<IIBBBB',256,32768,4,4,0,0)
        identity=hashlib.sha256(b'INKGRID1'+header+struct.pack('<I',128)+bytes(32)*512).hexdigest()
        d['items']=[dict(id='pixels',content=dict(type='stored_samples',grid=dict(base=dict(version=1,spec=spec,tiles=tiles,sha256=identity))))]
        # Only 65536 selected cells, but crossing two block columns would retain
        # 128 MiB of new binary32 blocks in addition to all solver/preparation data.
        options=dict(source_id='pixels',region=dict(x=127,y=0,width=2,height=32768),mode=dict(type='clone'))
        before=self.files();error=self.apply(d,options,error='RESOURCE_LIMIT')
        self.assertIn('memory bound',error['message']);self.assertEqual(self.files(),before)

    def test_cross_depth_and_channel_sources_quantize_once_at_target_depth(self):
        for depth,n in [('u8',2),('u16',4),('f32',4)]:
            maximum={'u8':255,'u16':65535,'f32':1}[depth]
            d=self.imported(2,1,[maximum]*n*2,depth=depth,n=n)
            source=self.imported(2,1,[.125,.5,.75,.25],depth='f32',n=2,stored=False)['items'][0]
            source['id']='source';source['visible']=False;d['items'].append(source)
            options=dict(source_id='source',region=dict(x=0,y=0,width=2,height=1),mode=dict(type='clone'))
            result=self.apply(d,options);values=[]
            for gray,alpha in [(.125,.5),(.75,.25)]:
                samples=[gray]*(n-1)+[alpha]
                values.extend(samples if depth=='f32' else [int(v*maximum+.5) for v in samples])
            self.assertEqual(self.raw(result['document']),bytes.fromhex(packed(values,depth)))
            self.assertEqual(result['document']['items'][1],source)


if __name__=='__main__':unittest.main()
