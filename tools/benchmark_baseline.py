"""Pinned external baseline tools and B01 SVG artifact judging; never launches Inkbolt."""
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

from benchmark_diagram import FONT_FAMILY, delivered, expected_picture
from benchmark_graphics import png_check
from benchmark_runtime import require

RESVG_VERSION = '0.47.0'
PILLOW_VERSION = '12.3.0'


def file_hash(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def tool_identity(configuration):
    require(set(configuration) == {'resvg','python'}, 'Baseline tools require resvg and Python paths')
    paths = {name:Path(value) for name,value in configuration.items()}
    require(all(path.is_absolute() and path.is_file() for path in paths.values()), 'Baseline tools must be absolute executable paths')
    version = subprocess.check_output([str(paths['resvg']), '--version'], timeout=10, text=True).strip()
    require(version == RESVG_VERSION, 'Baseline requires pinned resvg '+RESVG_VERSION)
    probe = '''import hashlib, importlib.metadata, json
d=importlib.metadata.distribution('Pillow')
files={str(p):hashlib.sha256(d.locate_file(p).read_bytes()).hexdigest() for p in d.files if not str(p).endswith(('.pyc','.pyo'))}
print(json.dumps(dict(version=d.version,files_sha256=hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest())))'''
    pillow = json.loads(subprocess.check_output([str(paths['python']), '-I', '-c', probe], timeout=20, text=True))
    require(pillow['version'] == PILLOW_VERSION, 'Baseline requires pinned Pillow '+PILLOW_VERSION)
    return dict(resvg=dict(path=str(paths['resvg']),sha256=file_hash(paths['resvg']),version=version),
                python=dict(path=str(paths['python']),sha256=file_hash(paths['python'])),pillow=pillow)


def render_svg(case, tools):
    target = getattr(case,'judge_root',case.root)/'judge-baseline.png'
    require(not target.exists(), 'Judge output already exists')
    result = subprocess.run([tools['resvg']['path'],'--skip-system-fonts','--use-font-file',
        str(case.root/'original.ttf'),'--font-family',FONT_FAMILY,str(case.root/'editable.svg'),str(target)],
        cwd=case.root,timeout=30,capture_output=True)
    require(result.returncode == 0, 'Pinned baseline rasterizer failed')
    return target.read_bytes()


def _numbers(text):
    values = [float(value) for value in re.split(r'[\s,]+',text.strip()) if value]
    require(all(math.isfinite(value) for value in values), 'Nonfinite SVG coordinate')
    return values


def _multiply(a,b):
    return (a[0]*b[0]+a[2]*b[1],a[1]*b[0]+a[3]*b[1],a[0]*b[2]+a[2]*b[3],
            a[1]*b[2]+a[3]*b[3],a[0]*b[4]+a[2]*b[5]+a[4],a[1]*b[4]+a[3]*b[5]+a[5])


def _transform(text):
    matrix = (1,0,0,1,0,0)
    while text.strip():
        match = re.match(r'\s*(matrix|translate|scale|rotate)\s*\(([^()]*)\)\s*,?',text)
        require(match is not None, 'Unsupported transform in the B01 SVG judge')
        name = match[1];v = _numbers(match[2]);text = text[match.end():]
        if name == 'matrix' and len(v) == 6: local = tuple(v)
        elif name == 'translate' and len(v) in (1,2): local = (1,0,0,1,v[0],v[-1] if len(v)==2 else 0)
        elif name == 'scale' and len(v) in (1,2): local = (v[0],0,0,v[-1],0,0)
        elif name == 'rotate' and len(v) in (1,3):
            c,s = math.cos(math.radians(v[0])),math.sin(math.radians(v[0]))
            local = (c,s,-s,c,0,0)
            if len(v)==3: local = _multiply(_multiply((1,0,0,1,v[1],v[2]),local),(1,0,0,1,-v[1],-v[2]))
        else: raise ValueError('Invalid transform arguments')
        matrix = _multiply(matrix,local)
    return matrix


def _point(matrix,x,y):
    return (round(matrix[0]*x+matrix[2]*y+matrix[4],8),round(matrix[1]*x+matrix[3]*y+matrix[5],8))


def svg_diagram(raw):
    require(len(raw) <= 1024*1024 and b'<!DOCTYPE' not in raw.upper(), 'B01 SVG is too large or has a document type')
    root = ET.fromstring(raw)
    require(root.tag == '{http://www.w3.org/2000/svg}svg', 'Expected an SVG document')
    require(_numbers(root.get('width','')) == [128] and _numbers(root.get('height','')) == [56], 'Wrong SVG canvas')
    require(_numbers(root.get('viewBox','0 0 128 56')) == [0,0,128,56], 'Unexpected SVG viewBox')
    objects=[]
    def visit(node, matrix, inherited):
        tag = node.tag.removeprefix('{http://www.w3.org/2000/svg}')
        require(tag in ('svg','g','rect','text','title','desc'), 'B01 requires editable rectangles and text')
        allowed={'id','transform','x','y','width','height','viewBox','fill','font-family','font-size',
                 'stroke','stroke-width','opacity','style','rx','ry','version','text-anchor'}
        require(set(node.attrib)<=allowed and all('url(' not in v.lower() for v in node.attrib.values()),
                'B01 SVG has an unsupported attribute or resource reference')
        require(not any(key.endswith('href') for key in node.attrib), 'External SVG references are not task inputs')
        require(len(objects) < 32, 'Too many SVG objects')
        style = dict(inherited)
        style.update({key:value for key,value in node.attrib.items() if key in ('fill','font-size','font-family')})
        for item in node.get('style','').split(';'):
            if item.strip():
                key,value = item.split(':',1)
                require(key.strip() in ('fill','font-size','font-family','stroke','stroke-width','opacity'), 'Unsupported inline style in B01')
                style[key.strip()] = value.strip()
        matrix = _multiply(matrix,_transform(node.get('transform','')))
        require(all(math.isfinite(v) for v in matrix), 'Nonfinite SVG transform')
        if tag in ('rect','text'): objects.append((tag,node,matrix,style))
        for child in node:
            require(tag in ('svg','g'), 'Nested text/shape content is outside the B01 deliverable contract')
            visit(child,matrix,style)
    visit(root,(1,0,0,1,0,0),dict(fill='black'))
    rectangles = [row for row in objects if row[0]=='rect']
    texts = [row for row in objects if row[0]=='text']
    require(len(rectangles)==3 and len(texts)==2, 'Expected three rectangles and two editable labels')
    shapes=[]
    for _,node,matrix,_ in rectangles:
        x,y,w,h = [float(node.get(key,'0')) for key in ('x','y','width','height')]
        require(all(math.isfinite(v) for v in (x,y,w,h)) and w>0 and h>0 and
                float(node.get('rx','0'))==0 and float(node.get('ry','0'))==0, 'Wrong rectangle geometry')
        shapes.append({_point(matrix,x,y),_point(matrix,x+w,y),_point(matrix,x,y+h),_point(matrix,x+w,y+h)})
    for x,y,w,h in [(8,8,48,36),(80,8,40,36),(56,25,24,2)]:
        require(shapes.count({(x,y),(x+w,y),(x,y+h),(x+w,y+h)})==1, 'Rectangle placement differs')
    for text,x in [('AA',20),('A',96)]:
        require(sum(node.text==text and _point(matrix,float(node.get('x','0')),float(node.get('y','0'))) == (x,32)
                    for _,node,matrix,_ in texts)==1, 'Label content or baseline differs')
    return texts


def judge_diagram(case, tools):
    raw = delivered(case,'editable.svg')
    # Admission precedes rendering, so rejected SVG cannot load external assets
    # or request an unbounded output surface from the external rasterizer.
    texts = svg_diagram(raw)
    case.check('diagram-structure', lambda: svg_diagram(raw))
    def fonts():
        for _,_,_,style in texts:
            require(style.get('font-family','').strip("'\"") == FONT_FAMILY and
                    float(style.get('font-size','').removesuffix('px')) == 20, 'Expected the supplied font at size 20')
    case.check('font-identity', fonts)
    rendered = render_svg(case,tools)
    def pixels():
        png_check(delivered(case,'preview.png'),128,56,expected_picture())
        png_check(rendered,128,56,expected_picture())
    case.check('diagram-pixels', pixels)
    case.not_applicable('editable-source','This check validates an Inkbolt snapshot; the baseline delivers editable SVG.')
