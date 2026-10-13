"""B15 original image decoding, retained resource recipe and engine-free repair."""
import subprocess

from benchmark_baseline_mixed import same_controls
from benchmark_diagram import delivered
from benchmark_graphics import BLUE,GREEN,png_check
from benchmark_resources import binding_manifest,replacements,expected_diagnostics,expected_picture,reported_diagnostics
from benchmark_runtime import require,strict_json
from test_images_cli import canonical


def admitted_manifest(case):
    raw=delivered(case,'editable.json');require(len(raw)<=16*1024,'Resource recipe exceeds its declared bound')
    require(same_controls(strict_json(raw),strict_json(delivered(case,'source.json'))),
        'Repair changed editable artwork or pinned resource descriptors')
    binding_manifest(case)
    for index in range(2):require(len(delivered(case,f'original-{index}.png'))<=4096,'Original image exceeds its fixture bound')


DECODE='''from PIL import Image
from pathlib import Path
import hashlib,json,struct,sys
root=Path(sys.argv[1]);scene=json.loads((root/'editable.json').read_bytes());resources=[]
for i in range(2):
    with Image.open(root/f'original-{i}.png') as image:
        assert image.format=='PNG' and image.size==(2,2) and image.mode=='RGBA' and getattr(image,'n_frames',1)==1
        image.load();resources.append(b'INKRGBA1'+struct.pack('<II',2,2)+image.tobytes())
canvas=Image.new('RGBA',(16,8))
for item in scene['items']:
    asset=scene['assets'][item['content']['asset_id']]
    raw=(root/'repaired-assets'/(asset['sha256']+'.rgba8')).read_bytes()
    assert len(raw)==32 and raw[:8]==b'INKRGBA1' and struct.unpack('<II',raw[8:16])==(2,2)
    assert hashlib.sha256(raw).hexdigest()==asset['sha256']
    image=Image.frombytes('RGBA',(2,2),raw[16:]).resize((8,8),Image.Resampling.NEAREST)
    canvas.paste(image,tuple(int(v) for v in item['transform'][4:6]))
print(json.dumps(dict(resources=[data.hex() for data in resources],rendered=canvas.tobytes().hex())))
'''


def decode_and_render(case,tools):
    result=subprocess.run([tools['python']['path'],'-I','-c',DECODE,str(case.root)],cwd=case.root,timeout=30,capture_output=True)
    require(result.returncode==0,'Pinned Pillow could not decode originals or render the repaired cache')
    value=strict_json(result.stdout)
    require(isinstance(value,dict) and set(value)=={'resources','rendered'} and len(value['resources'])==2,'Invalid resource decoder response')
    resources=[bytes.fromhex(v) for v in value['resources']];rendered=bytes.fromhex(value['rendered'])
    require(all(len(v)==32 for v in resources) and len(rendered)==16*8*4,'Resource or preview dimensions changed')
    return resources,rendered


def judge_resources(case,tools):
    require(case.check('unchanged-artwork',lambda:admitted_manifest(case)),'Resource recipe was not admitted')
    case.check('located-diagnostics',lambda:require(reported_diagnostics(delivered(case,'diagnostics.json'))==expected_diagnostics(),
        'Corrupt and missing resource locations differ from the original fixture'))
    decoded=[]
    def verified():
        replacements(case)
        resources,rendered=decode_and_render(case,tools)
        require(resources==[canonical(2,2,bytes(color)*4) for color in (BLUE,GREEN)],'Pinned decoding changed original resource identities')
        decoded.append(rendered)
    require(case.check('verified-replacements',verified),'Replacement cache was not admitted')
    rendered=decoded[0]
    def picture():
        require(rendered==expected_picture(),'Fresh rendering from the repaired cache differs')
        png_check(delivered(case,'preview.png'),16,8,expected_picture())
    case.check('repaired-pixels',picture)
    case.not_applicable('old-bindings-preserved','The baseline preserves the old cache and binding recipe; this check reopens Inkbolt durable historical states and receipts.')
    case.not_applicable('history-valid','Inkbolt saved history is unavailable to the no-engine arm.')
