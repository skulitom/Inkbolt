"""Fixed 50 MP studio input and bounded independent row/block expectations."""
import json
import mmap
import os
from pathlib import Path
import struct
import subprocess
import tempfile

from benchmark_runtime import require
from scale_oracles import file_hash, write_tiff
from workload_cases import save_json, sha, tiff_tags

VARIANT = 'photo-50mp-v1'
WIDTH, HEIGHT = 8192, 6144
REGION = dict(x=5114, y=3835, width=20, height=16)
DONOR_DX = -96
MAX_PEAK_COMMIT_BYTES = 512*1024*1024


def generate(case):
    """Only the fixed profile is exposed by the benchmark CLI."""
    write_fixture(case, WIDTH, HEIGHT, REGION)


def write_fixture(case, width, height, region):
    source = Path(__file__).with_name('benchmark_photo_fixture.rs')
    support = case.root.parent/'.photo-fixture-tools'
    support.mkdir(exist_ok=True)
    compiler = subprocess.check_output(['rustc', '--version'], text=True).strip()
    identity = dict(source_sha256=file_hash(source), compiler=compiler)
    binary = support/('photo-fixture.exe' if os.name=='nt' else 'photo-fixture')
    record = support/'identity.json'
    if record.exists():
        saved = json.loads(record.read_text())
        require(saved['source']==identity and saved['executable_sha256']==file_hash(binary),
                'Fixture generator changed during the run')
    else:
        require(not binary.exists(), 'Unrecorded fixture generator already exists')
        result = subprocess.run(['rustc', '--edition=2024', '-C', 'opt-level=2', str(source), '-o', str(binary)],
                                capture_output=True, timeout=60)
        require(result.returncode==0, 'Standalone fixture compilation failed: '+result.stderr.decode(errors='replace'))
        save_json(record, dict(source=identity, executable_sha256=file_hash(binary)))
    # Private temporary raw rows avoid a full-frame Python allocation and are
    # excluded from measured solver lifetimes. The retained TIFF is create-only.
    with tempfile.TemporaryFile() as raw:
        result = subprocess.run([str(binary),str(width),str(height),*(str(region[k]) for k in ('x','y','width','height'))],
                                stdout=raw, stderr=subprocess.PIPE, timeout=120)
        require(result.returncode==0 and not result.stderr and raw.tell()==width*height*8,
                'Standalone fixture generation failed')
        raw.seek(0)
        write_tiff(case.root/'original.tiff',width,height,lambda _:raw.read(width*8))
    case.sources['original.tiff'] = file_hash(case.root/'original.tiff')
    case.source('fixture-profile.json',json.dumps(dict(variant=VARIANT,width=width,height=height,
        region=region,donor_dx=DONOR_DX,maximum_peak_commit_bytes=MAX_PEAK_COMMIT_BYTES,
        fixed_fixture=(width,height,region)==(WIDTH,HEIGHT,REGION),generator_source_sha256=identity['source_sha256']),
        sort_keys=True,separators=(',',':')).encode())


class Rows:
    def __init__(self,path,width=WIDTH,height=HEIGHT,region=None):
        self.width,self.height,self.region=width,height,REGION if region is None else region
        self.stream=path.open('rb')
        try:
            self.data=mmap.mmap(self.stream.fileno(),0,access=mmap.ACCESS_READ)
            tags=tiff_tags(self.data)
            require(self.data[:2]==b'II' and tags[256]==(width,) and tags[257]==(height,) and
                tags[258]==(16,)*4 and tags[259]==(1,) and tags[262]==(2,) and tags[277]==(4,) and
                tags[338]==(2,) and tags[339]==(1,)*4 and tags.get(274,(1,))==(1,) and tags.get(284,(1,))==(1,),
                'Wrong original native TIFF meaning')
            self.offsets=[]
            for offset,size in zip(tags[273],tags[279],strict=True):
                require(size%(width*8)==0 and offset+size<=len(self.data),'Invalid original TIFF strip')
                self.offsets.extend(range(offset,offset+size,width*8))
            require(len(self.offsets)==height,'Missing original TIFF rows')
        except BaseException:
            self.close();raise
    def close(self):
        if hasattr(self,'data'):self.data.close()
        self.stream.close()
    def __enter__(self):return self
    def __exit__(self,*_):self.close()
    def row(self,y,edited=False):
        start=self.offsets[y];raw=self.data[start:start+self.width*8]
        r=self.region
        if edited and r['y']<=y<r['y']+r['height']:
            x=r['x']*8;size=r['width']*8;donor=x+DONOR_DX*8
            raw=raw[:x]+raw[donor:donor+size]+raw[x+size:]
        return raw
    def blocks(self,edited=False):
        for top in range(0,self.height,128):
            rows=[self.row(y,edited) for y in range(top,min(self.height,top+128))]
            for left in range(0,self.width,128):
                width=min(128,self.width-left)
                blob=b'INKTILE1'+struct.pack('<IIBBBB',width,len(rows),2,4,0,0)
                blob+=b''.join(row[left*8:(left+width)*8] for row in rows)
                yield sha(blob),blob
    def manifest(self,edited=False):
        names=[name for name,_ in self.blocks(edited)]
        raw=b'INKGRID1INKTILE1'+struct.pack('<IIBBBBI',self.width,self.height,2,4,0,0,128)
        raw+=b''.join(bytes.fromhex(name) for name in names)
        return dict(version=1,spec=dict(width=self.width,height=self.height,depth='u16',channels='rgba',encoding='encoded_srgb'),
                    tiles=names,sha256=sha(raw))
    def preview(self):
        r=self.region;result=bytearray()
        for y in range(r['y'],r['y']+r['height']):
            raw=self.row(y,True)[r['x']*8:(r['x']+r['width'])*8]
            result.extend((v[0]*255+32767)//65535 for v in struct.iter_unpack('<H',raw))
        return bytes(result)
