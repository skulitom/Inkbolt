"""Independent delivery hashes, exact clocks, pixels, and pinned revision workflow."""
import base64
from contextlib import closing
import copy
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_cli import EXE
from test_editing_cli import png_pixels
from test_mcp import Client


def options(**changes):
    result=dict(link_key='title',selection=dict(type='still',frame_id=None),
        duration=dict(num=1,den=5),frame_rate=dict(num=25,den=1),
        timing='strict',end='hold_last',alpha=dict(type='transparent'))
    result.update(changes)
    return result


def raw_files(bundle):
    return {f['path']:base64.b64decode(f['data']) for f in bundle['files']}


def save(bundle,root):
    for name,data in raw_files(bundle).items():
        with (root/name).open('xb') as f:f.write(data)


class HandoffTests(unittest.TestCase):
    def invoke(self,command,error=None,workspace=None,**args):
        argv=[str(EXE)]+([] if workspace is None else ['--workspace',str(workspace)])
        p=subprocess.run(argv,input=json.dumps(dict(command=command,**args)).encode(),
                         capture_output=True,timeout=20)
        self.assertEqual(p.stderr,b'')
        result=json.loads(p.stdout)
        self.assertEqual(p.returncode,int(error is not None),result)
        if error:
            self.assertEqual(result['error']['code'],error,result)
            return result['error']
        self.assertTrue(result['ok'],result)
        return result['result']

    def document(self):
        d=self.invoke('document.create',id='graphic',kind='raster',width=4,height=2)
        rgba=bytes([200,80,30,128,10,220,70,255,0,0,0,0,77,33,22,64])*2
        return self.invoke('document.edit',document=d,expected_revision=0,operations=[
            dict(op='add',item=dict(id='art',content=dict(type='raster',width=4,height=2,rgba_hex=rgba.hex())))])['document']

    def sequence(self):
        d=self.document()
        second=copy.deepcopy(d['items'][0]);second['id']='other'
        second['content']['rgba_hex']=bytes([50,150,250,255]*8).hex()
        d=self.invoke('document.edit',document=d,expected_revision=d['revision'],operations=[
            dict(op='add',item=second),dict(op='sequence_from_layers',ids=['art','other'],
                delay=dict(numerator=1,denominator=25),plays=3)])['document']
        d['variants']['sequence']['frames'][0]['delay']=dict(numerator=10,denominator=0)
        return d

    def test_still_hashes_pixels_source_and_reproducible_files(self):
        d=self.document();before=copy.deepcopy(d)
        bundle=self.invoke('handoff.export',document=d,options=options())
        self.assertEqual(bundle,self.invoke('handoff.export',document=d,options=options()))
        manifest=bundle['handoff']['manifest'];files=raw_files(bundle)
        for file in bundle['files']:
            self.assertEqual(hashlib.sha256(files[file['path']]).hexdigest(),file['sha256'])
            self.assertEqual(len(files[file['path']]),file['bytes'])
        self.assertEqual(json.loads(files[manifest['source']['snapshot']['path']]),d)
        self.assertEqual(hashlib.sha256(files[bundle['manifest_file']['path']]).hexdigest(),bundle['handoff']['sha256'])
        pixels=png_pixels(files[manifest['frames'][0]['image']['path']])
        self.assertEqual(pixels[:2],(4,2))
        self.assertEqual(pixels[2],bytes.fromhex(d['items'][0]['content']['rgba_hex']))
        self.assertEqual(d,before)
        report=self.invoke('handoff.inspect',handoff=bundle['handoff'],include_schedule=True)
        self.assertTrue(report['manifest_verified']);self.assertFalse(report['files_verified'])
        self.assertEqual(report['selected_frames'],[0]*5)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);save(bundle,root)
            self.assertTrue(self.invoke('handoff.inspect',handoff=bundle['handoff'],input_root=str(root))['files_verified'])
            with self.assertRaises(FileExistsError):save(bundle,root)
        scene=json.loads(files[manifest['scene']['path']])
        self.assertTrue(scene['transparent']);self.assertEqual(scene['layers'][0]['alpha_mode'],'straight')
        self.assertEqual(scene['layers'][0]['frames'][0]['image'],manifest['frames'][0]['image'])

    def test_sequence_exact_sampling_loops_endings_and_still_selection(self):
        d=self.sequence()
        sequence_options=options(selection=dict(type='sequence'),duration=dict(num=2,den=5))
        self.invoke('handoff.export',document=d,options=sequence_options,error='UNALIGNED_TIME')
        sequence_options['timing']='sample_start'
        holds=[F(1,10),F(1,25)];cycle=sum(holds)
        for end in ('loop','transparent','hold_last'):
            opts=dict(sequence_options,end=end)
            bundle=self.invoke('handoff.export',document=d,options=opts)
            m=bundle['handoff']['manifest'];self.assertEqual(m['source']['sequence_plays'],3)
            self.assertEqual([f['source_delay'] for f in m['frames']],
                [f['delay'] for f in d['variants']['sequence']['frames']])
            expected=[]
            for i in range(10):
                t=F(i,25)
                if end=='loop':t%=cycle
                expected.append((None if end=='transparent' else 1) if t>=cycle else 0 if t<holds[0] else 1)
            actual=self.invoke('handoff.inspect',handoff=bundle['handoff'],include_schedule=True)
            self.assertEqual(actual['selected_frames'],expected)
            with tempfile.TemporaryDirectory() as td:
                root=Path(td);save(bundle,root)
                self.invoke('handoff.inspect',handoff=bundle['handoff'],input_root=str(root))
        self.invoke('handoff.export',document=d,options=options(),error='INVALID_HANDOFF')
        ident=d['variants']['sequence']['frames'][1]['id']
        still=self.invoke('handoff.export',document=d,options=options(selection=dict(type='still',frame_id=ident)))
        self.assertEqual(still['handoff']['manifest']['frames'][0]['id'],ident)
        d['variants']['sequence']['frames'][0]['delay']['numerator']=0
        self.invoke('handoff.export',document=d,options=sequence_options,error='UNSUPPORTED')

    def test_every_native_clock_has_exact_frame_and_audio_boundaries(self):
        for n,den in [(24,1),(25,1),(30,1),(50,1),(60,1),(24000,1001),(30000,1001),(60000,1001)]:
            frames=5 if n in (30000,60000) else 1
            duration=F(frames*den,n)
            opts=options(frame_rate=dict(num=n,den=den),duration=dict(num=duration.numerator,den=duration.denominator))
            bundle=self.invoke('handoff.export',document=self.document(),options=opts)
            self.assertEqual(self.invoke('handoff.inspect',handoff=bundle['handoff'],include_schedule=True)['selected_frames'],[0]*frames)
        for fields in [dict(frame_rate=dict(num=29,den=1)),dict(duration=dict(num=1,den=30)),
                       dict(duration=dict(num=121,den=1)),dict(duration=dict(num=1,den=0)),
                       dict(frame_rate=dict(num=30000,den=1001),duration=dict(num=1001,den=30000))]:
            self.invoke('handoff.export',document=self.document(),options=options(**fields),
                        error='UNSUPPORTED' if fields.get('frame_rate',{}).get('num')==29 else 'INVALID_HANDOFF')

    def test_missing_changed_manifest_scene_and_frame_files_fail_without_writes(self):
        bundle=self.invoke('handoff.export',document=self.document(),options=options())
        wrong=copy.deepcopy(bundle['handoff']);wrong['manifest']['options']['alpha']=dict(type='matte',background=[5,10,20])
        self.invoke('handoff.inspect',handoff=wrong,error='SOURCE_MISMATCH')
        wrong=copy.deepcopy(bundle['handoff']);wrong['manifest']['schema_version']=2
        self.invoke('handoff.inspect',handoff=wrong,error='UNSUPPORTED_HANDOFF_VERSION')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);save(bundle,root);original=raw_files(bundle)
            for name,raw in original.items():
                path=root/name;path.unlink()
                self.invoke('handoff.inspect',handoff=bundle['handoff'],input_root=str(root),error='IO_ERROR')
                damaged=bytearray(raw);damaged[len(damaged)//2]^=1
                path.write_bytes(damaged)
                self.invoke('handoff.inspect',handoff=bundle['handoff'],input_root=str(root),error='SOURCE_MISMATCH')
                self.assertEqual(path.read_bytes(),damaged)
                path.write_bytes(raw)
            self.assertEqual({p.name:p.read_bytes() for p in root.iterdir()},original)

    def test_pinned_mcp_revisions_require_explicit_predecessor_and_preserve_old_delivery(self):
        with tempfile.TemporaryDirectory() as td,closing(Client(workspace=td)) as c:
            c.initialize();d=self.document()
            initial=c.success('session.create',session_id='graphic',request_id='create',document=d)
            revision=initial['document']['revision']
            ref=dict(session_id='graphic',revision=revision)
            first=c.success('handoff.export',document=ref,options=options())
            old=copy.deepcopy(first)
            edited=c.success('session.apply',session_id='graphic',request_id='move',expected_revision=revision,
                action=dict(type='edit',operations=[dict(op='transform',id='art',matrix=[1,0,0,1,1,0])]))
            newref=dict(session_id='graphic',revision=edited['document']['revision'])
            second=c.success('handoff.export',document=newref,options=options(),previous=first['handoff'])
            self.assertEqual(second['handoff']['manifest']['previous'],dict(sha256=first['handoff']['sha256'],source_revision=revision))
            self.assertNotEqual(first['handoff']['manifest']['frames'][0]['image'],second['handoff']['manifest']['frames'][0]['image'])
            self.assertEqual(c.success('handoff.export',document=ref,options=options()),old)
            root=Path(td)/'delivered';root.mkdir();save(second,root)
            self.assertTrue(c.success('handoff.inspect',handoff=second['handoff'],input_root='delivered')['files_verified'])
            self.assertEqual(c.tool('handoff.export',document=ref,options=options(),previous=first['handoff'])['structuredContent']['error']['code'],'HANDOFF_CONFLICT')
            self.assertEqual(c.tool('handoff.export',document=newref,options=options(link_key='other'),previous=first['handoff'])['structuredContent']['error']['code'],'HANDOFF_CONFLICT')
            undone=c.success('session.apply',session_id='graphic',request_id='undo',expected_revision=newref['revision'],action=dict(type='undo'))
            undo_pin=c.success('handoff.export',document=dict(session_id='graphic',revision=undone['document']['revision']),options=options(),previous=second['handoff'])
            self.assertEqual(undo_pin['handoff']['manifest']['frames'][0]['image'],first['handoff']['manifest']['frames'][0]['image'])
            self.assertEqual(undo_pin['handoff']['manifest']['previous']['sha256'],second['handoff']['sha256'])
            self.assertTrue(c.success('session.verify',session_id='graphic')['valid'])

    def test_cancellation_unknown_fields_and_resource_limits_fail_explicitly(self):
        d=self.document()
        with tempfile.TemporaryDirectory() as td:
            cancel=Path(td)/'cancel';cancel.touch()
            self.invoke('handoff.export',document=d,options=options(),control=dict(cancel_file=str(cancel)),error='CANCELLED')
            self.assertEqual(list(Path(td).iterdir()),[cancel])
        bad=options();bad['implicit_fps']=True
        self.invoke('handoff.export',document=d,options=bad,error='INVALID_REQUEST')
        self.invoke('handoff.export',document=d,options=options(link_key='../bad'),error='INVALID_HANDOFF')
        large=copy.deepcopy(d);large.update(kind='vector',resource_profile='large_vector',width=5000,items=[])
        self.invoke('handoff.export',document=large,options=options(),error='RESOURCE_LIMIT')

    def test_self_consistent_rehashed_but_invalid_contract_is_rejected(self):
        bundle=self.invoke('handoff.export',document=self.document(),options=options())
        original=json.loads(raw_files(bundle)[bundle['manifest_file']['path']])
        for change in (lambda m:m['frames'][0]['image'].update(path='../escape.png'),
                       lambda m:m['scene'].update(sha256='0'*64),
                       lambda m:m['options'].update(duration=dict(num=3,den=25)),
                       lambda m:m.update(losses=[]),
                       lambda m:m.update(previous=dict(sha256='a'*64,source_revision=m['source']['revision']))):
            m=copy.deepcopy(original);change(m)
            digest=hashlib.sha256(json.dumps(m,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
            self.invoke('handoff.inspect',handoff=dict(sha256=digest,manifest=m),error='INVALID_HANDOFF')
        m=copy.deepcopy(original);m['options']['scale']=0
        digest=hashlib.sha256(json.dumps(m,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        self.invoke('handoff.inspect',handoff=dict(sha256=digest,manifest=m),error='INVALID_REQUEST')

    def test_documented_example_creates_three_verified_linked_deliveries_without_overwrite(self):
        script=Path(__file__).resolve().parents[1]/'examples/handoff_workflow.py'
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'example'
            cmd=[sys.executable,str(script),'--inkbolt',str(EXE),'--output',str(root)]
            result=subprocess.run(cmd,capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr.decode())
            receipts=[json.loads((root/(n+'-checked.json')).read_text()) for n in ('revision-0','revision-1','revision-2-sequence')]
            self.assertTrue(all(r['inspection']['files_verified'] for r in receipts))
            self.assertEqual(receipts[1]['handoff']['manifest']['previous']['sha256'],receipts[0]['handoff']['sha256'])
            self.assertEqual(receipts[2]['handoff']['manifest']['previous']['sha256'],receipts[1]['handoff']['sha256'])
            hashes={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
            self.assertNotEqual(subprocess.run(cmd,capture_output=True,timeout=10).returncode,0)
            self.assertEqual(hashes,{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()})


if __name__=='__main__':unittest.main()
