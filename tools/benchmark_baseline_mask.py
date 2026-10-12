"""B08 engine-free layered mask manifest and pinned Pillow composition."""
import subprocess

from benchmark_diagram import delivered
from benchmark_graphics import png_check
from benchmark_mask import original_pixels, selected_pixels, expected_picture
from benchmark_runtime import require, strict_json


def manifest():
    return dict(width=16,height=16,id='pixels',image='pixels.png',mask='mask.png',selection='selection.png',
        linked=True,transform=[1,0,0,1,0,0])


def admitted_manifest(case):
    value = strict_json(delivered(case,'editable.json'))
    require(isinstance(value,dict) and set(value) == set(manifest()) and value == manifest() and
        type(value['width']) is int and type(value['height']) is int and value['linked'] is True and
        all(type(v) in (int,float) for v in value['transform']),
        'Expected the original layer identity, three local images and a linked mask sharing the identity transform')
    for name in ('pixels.png','mask.png','selection.png'):
        require(len(delivered(case,name)) <= 64*1024,'A B08 layer image exceeds its delivery bound')
    return value


DECODE_AND_COMPOSE = '''from PIL import Image
from pathlib import Path
import json, sys
root=Path(sys.argv[1])
def read(name):
    with Image.open(root/name) as image:
        assert image.format == 'PNG' and image.size == (16,16) and getattr(image,'n_frames',1) == 1
        assert image.mode in ('L','RGB','RGBA')
        image.load()
        return image.convert('RGBA')
def coverage(name):
    image=read(name)
    raw=image.tobytes(); samples=list(zip(raw[0::4],raw[1::4],raw[2::4],raw[3::4]))
    assert all(r == g == b and a == 255 for r,g,b,a in samples)
    return Image.frombytes('L',(16,16),bytes(r for r,g,b,a in samples))
layer=read('pixels.png'); mask=coverage('mask.png'); selection=coverage('selection.png')
rendered=Image.composite(layer,Image.new('RGBA',(16,16)),mask)
print(json.dumps(dict(pixels=layer.tobytes().hex(),mask=mask.tobytes().hex(),
    selection=selection.tobytes().hex(),rendered=rendered.tobytes().hex())))
'''


def decode_and_compose(case, tools):
    result = subprocess.run([tools['python']['path'],'-I','-c',DECODE_AND_COMPOSE,str(case.root)],
        cwd=case.root,timeout=30,capture_output=True)
    require(result.returncode == 0,'Pinned Pillow could not decode or compose the bounded layer/mask images')
    data = strict_json(result.stdout)
    require(isinstance(data,dict) and set(data) == {'pixels','mask','selection','rendered'},'Invalid pinned composition result')
    decoded = {key:bytes.fromhex(value) for key,value in data.items()}
    require(all(len(decoded[key]) == (256 if key in ('mask','selection') else 1024) for key in decoded),
        'Pinned composition dimensions changed')
    return decoded


def judge_mask(case, tools):
    admitted_manifest(case)
    data = decode_and_compose(case,tools)
    case.check('selection-coverage',lambda:require(data['selection'] == data['mask'] == selected_pixels(),
        'Retained selection and linked mask must cover exactly the requested foreground'))
    case.check('retained-pixels',lambda:require(data['pixels'] == original_pixels(),'Original layer samples changed'))
    def picture():
        require(data['rendered'] == expected_picture(),'Fresh composition differs from the independently authored foreground')
        png_check(delivered(case,'preview.png'),16,16,expected_picture())
    case.check('masked-pixels',picture)
    case.not_applicable('historical-pixels','The baseline preserves source.json and the original pixel layer; this check reopens an Inkbolt saved revision.')
    case.not_applicable('history-valid','Inkbolt session history is unavailable to the no-engine arm.')
