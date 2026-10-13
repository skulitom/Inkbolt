"""B13 editable SVG admission and pinned straight-alpha PNG publication."""
import json
import subprocess
import xml.etree.ElementTree as ET

from benchmark_baseline import _numbers
from benchmark_baseline_flow import paint
from benchmark_diagram import delivered
from benchmark_graphics import png_check
from benchmark_runtime import require,strict_json
from benchmark_screen import NOTE,delivery_identity,screen_color,expected_picture
from workload_cases import save,sha

NS='{http://www.w3.org/2000/svg}'


def screen_shape(raw):
    require(len(raw)<=4096,'Screen SVG exceeds the bounded source contract')
    text=raw.decode('utf-8');require('<!DOCTYPE' not in text.upper(),'Document types are not screen inputs')
    root=ET.fromstring(text)
    require(root.tag==NS+'svg' and set(root.attrib)<={'width','height','viewBox','version'} and len(root)==2 and
        _numbers(root.get('width',''))==[1920] and _numbers(root.get('height',''))==[1080] and
        _numbers(root.get('viewBox','0 0 1920 1080'))==[0,0,1920,1080],'Screen canvas or source structure changed')
    metadata,rect=root
    require(metadata.tag==NS+'metadata' and not metadata.attrib and not list(metadata) and metadata.text==NOTE,
            'Retain the private note in editable source only')
    require(rect.tag==NS+'rect' and not list(rect) and set(rect.attrib)<={'id','x','y','width','height','fill','fill-opacity'} and
        [_numbers(rect.get(k,'')) for k in ('x','y','width','height')]==[[10],[20],[200],[100]] and
        paint(rect.get('fill',''),(20,80,150)) and _numbers(rect.get('fill-opacity',''))==[128/255],
        'Expected the original editable rectangle with exact straight-alpha paint')
    require(not (root.text or '').strip() and not (rect.text or '').strip() and
        all(not (node.tail or '').strip() for node in root),'Unexpected screen SVG text')
    return dict(size=[int(_numbers(root.get('width'))[0]),int(_numbers(root.get('height'))[0])],
        bounds=[float(rect.get(k)) for k in ('x','y','width','height')],color=[20,80,150,round(float(rect.get('fill-opacity'))*255)])


PUBLISH='''from PIL import Image,PngImagePlugin
from pathlib import Path
import hashlib,json,sys
directory=Path(sys.argv[1]);scene=json.loads(sys.argv[2]);w,h=scene['size'];x,y,rw,rh=map(int,scene['bounds'])
image=Image.new('RGBA',(w,h),(0,0,0,0));image.paste(Image.new('RGBA',(rw,rh),tuple(scene['color'])),(x,y))
tag=PngImagePlugin.PngInfo();tag.add(b'sRGB',bytes([0]))
def publish(path):
    with path.open('xb') as output:image.save(output,format='PNG',pnginfo=tag)
publish(directory/'judge-baseline-screen.png')
protected=directory/'judge-protected.png';before=hashlib.sha256(protected.read_bytes()).hexdigest()
try:
    publish(protected);collision=False
except FileExistsError:collision=True
print(json.dumps(dict(collision=collision,before=before,after=hashlib.sha256(protected.read_bytes()).hexdigest())))
'''


def render_and_probe(case,tools,shape,raw):
    directory=getattr(case,'judge_root',case.root)
    target=directory/'judge-baseline-screen.png';protected=directory/'judge-protected.png'
    require(not target.exists() and not protected.exists(),'Screen judge outputs must be new')
    save(protected,raw)
    result=subprocess.run([tools['python']['path'],'-I','-c',PUBLISH,str(directory),json.dumps(shape)],
                          cwd=case.root,timeout=30,capture_output=True)
    require(result.returncode==0,'Pinned straight-alpha screen publication failed')
    return target.read_bytes(),strict_json(result.stdout),protected.read_bytes()


def judge_screen(case,tools):
    raw=delivered(case,'screen.png');shape=screen_shape(delivered(case,'editable.svg'))
    # The admitted recipe has one fixed local destination and create-only mode;
    # the fresh encoder and repeat probe run outside the captured workspace.
    recipe=strict_json(delivered(case,'delivery.json'))
    require(recipe==delivery_identity(raw),'Screen delivery recipe or original identity changed')
    fresh,probe,protected=render_and_probe(case,tools,shape,raw)
    def picture():
        for data in (raw,fresh):png_check(data,1920,1080,expected_picture())
    case.check('transparent-pixels',picture)
    def color():
        for data in (raw,fresh):screen_color(data)
    case.check('screen-color',color)
    case.check('no-overwrite',lambda:require(type(probe.get('collision')) is bool and probe==dict(collision=True,before=sha(raw),after=sha(raw)) and
        protected==raw==delivered(case,'screen.png'),'Create-only duplicate publication failed to protect the original bytes'))
    case.not_applicable('editable-source','This check reopens an Inkbolt snapshot; the baseline retains the admitted editable SVG and private source note.')
