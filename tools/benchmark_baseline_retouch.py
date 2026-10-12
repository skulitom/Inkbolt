"""B09 engine-free editable pixel layer and pinned Pillow decoding."""
import subprocess

from benchmark_diagram import delivered
from benchmark_graphics import png_check
from benchmark_retouch import repaired_pixels
from benchmark_runtime import require, strict_json


def manifest():
    return dict(width=16,height=16,id='pixels',image='pixels.png',transform=[1,0,0,1,0,0])


def admitted_manifest(case):
    value = strict_json(delivered(case,'editable.json'))
    require(isinstance(value,dict) and set(value) == set(manifest()) and value == manifest() and
        type(value['width']) is int and type(value['height']) is int and
        all(type(v) in (int,float) for v in value['transform']),
        'Expected the original layer identity, dimensions and identity transform with one local pixel image')
    require(len(delivered(case,'pixels.png')) <= 64*1024,'The B09 pixel layer exceeds its delivery bound')
    return value


DECODE = '''from PIL import Image
from pathlib import Path
import json,sys
with Image.open(Path(sys.argv[1])/'pixels.png') as image:
    assert image.format == 'PNG' and image.size == (16,16) and getattr(image,'n_frames',1) == 1
    assert image.mode in ('RGB','RGBA')
    image.load()
    print(json.dumps(dict(pixels=image.convert('RGBA').tobytes().hex())))
'''


def decode_pixels(case, tools):
    result = subprocess.run([tools['python']['path'],'-I','-c',DECODE,str(case.root)],
        cwd=case.root,timeout=30,capture_output=True)
    require(result.returncode == 0,'Pinned Pillow could not decode the bounded pixel layer')
    data = strict_json(result.stdout)
    require(isinstance(data,dict) and set(data) == {'pixels'},'Invalid pinned decoding result')
    pixels = bytes.fromhex(data['pixels'])
    require(len(pixels) == 16*16*4,'Pinned decoding dimensions changed')
    return pixels


def judge_retouch(case, tools):
    admitted_manifest(case)
    pixels = decode_pixels(case,tools)
    case.check('exact-local-repair',lambda:require(pixels == repaired_pixels(),
        'The cloned defect samples or unaffected original samples differ'))
    def picture():
        require(pixels == repaired_pixels(),'The editable layer differs from the independent pixel oracle')
        png_check(delivered(case,'preview.png'),16,16,repaired_pixels())
    case.check('repaired-pixels',picture)
    case.not_applicable('historical-pixels','The baseline preserves source.json; this check reopens an Inkbolt saved revision.')
    case.not_applicable('history-valid','Inkbolt session history is unavailable to the no-engine arm.')
