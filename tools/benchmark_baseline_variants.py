"""B12 bounded editable SVG instances and independent pinned artboard renders."""
import base64
import subprocess
import xml.etree.ElementTree as ET

from benchmark_baseline import _numbers
from benchmark_baseline_flow import paint,same_json
from benchmark_diagram import delivered
from benchmark_graphics import png_check
from benchmark_runtime import require,strict_json
from benchmark_variants import BOARDS,ROWS,FONT_FAMILY,expected_picture
from workload_cases import save,sha

NS='{http://www.w3.org/2000/svg}'
HREF='{http://www.w3.org/1999/xlink}href'


def manifest():
    return dict(base=dict(text='A',position=[2,16],image='green.png'),selected=None,datasets={
        name:dict(**({'parent':'wide'} if name=='square' else {}),values=dict(text=label,position=position,image=image+'.png'))
        for name,(label,position,image) in ROWS.items()})


def svg_layout(case,raw,name):
    require(len(raw)<=64*1024 and b'<!DOCTYPE' not in raw.upper(),'Oversized or unsupported variant SVG')
    root=ET.fromstring(raw)
    require(root.tag==NS+'svg' and set(root.attrib)<={'width','height','viewBox','version'} and
        _numbers(root.get('width',''))==[96] and _numbers(root.get('height',''))==[96] and
        _numbers(root.get('viewBox','0 0 96 96'))==[0,0,96,96] and len(root)==4,'Wrong variant sheet canvas')
    defs=root[0]
    require(defs.tag==NS+'defs' and not defs.attrib and len(defs)==1,'Expected one shared component definition')
    group=defs[0]
    require(group.tag==NS+'g' and set(group.attrib)=={'id'} and group.get('id')=='shared' and len(group)==2,
            'Expected the shared editable label and image')
    label,position,image=('A',[2,16],'green') if name=='base' else ROWS[name]
    text,picture=group
    require(text.tag==NS+'text' and not list(text) and set(text.attrib)=={'x','y','font-family','font-size','fill'} and
        _numbers(text.get('x',''))==[2] and _numbers(text.get('y',''))==[16] and text.text==label and
        text.get('font-family')==FONT_FAMILY and _numbers(text.get('font-size',''))==[20] and
        paint(text.get('fill',''),(20,80,150)),'Editable label, placement, font or color changed')
    require(picture.tag==NS+'image' and not list(picture) and set(picture.attrib)=={'x','y','width','height',HREF} and
        [_numbers(picture.get(k,'')) for k in ('x','y','width','height')]==[[position[0]],[position[1]],[4],[4]] and
        picture.get(HREF)=='data:image/png;base64,'+base64.b64encode(delivered(case,image+'.png')).decode(),
        'The placed image must retain exactly the supplied PNG at its selected position')
    for board,(identity,w,h,x,y) in zip(root[1:],BOARDS,strict=True):
        require(board.tag==NS+'svg' and set(board.attrib)<={'id','x','y','width','height','viewBox','overflow'} and
            board.get('id')==identity and [_numbers(board.get(k,'')) for k in ('x','y','width','height')]==[[x],[y],[w],[h]] and
            _numbers(board.get('viewBox',f'0 0 {w} {h}'))==[0,0,w,h] and board.get('overflow','hidden')=='hidden' and len(board)==1,
            'Artboard dimensions, order or placement changed')
        use=board[0]
        require(use.tag==NS+'use' and set(use.attrib)=={HREF} and use.get(HREF)=='#shared' and not list(use),
                'Each artboard must instance the shared editable component')
    require(all(not (node.tail or '').strip() and (node.tag==NS+'text' or not (node.text or '').strip()) for node in root.iter()),
            'Unexpected visible text in variant SVG')
    return root


def render_variant(case,tools,name,root):
    directory=getattr(case,'judge_root',case.root)
    source,target=directory/('judge-'+name+'.svg'),directory/('judge-'+name+'.png')
    require(not source.exists() and not target.exists(),'Variant judge output already exists')
    _,w,h,_,_=next(b for b in BOARDS if b[0]==name)
    view=ET.Element(NS+'svg',dict(width=str(w),height=str(h)))
    view.append(ET.fromstring(ET.tostring(root[0])));view.append(ET.Element(NS+'use',{HREF:'#shared'}))
    save(source,ET.tostring(view,encoding='utf-8'))
    result=subprocess.run([tools['resvg']['path'],'--skip-system-fonts','--use-font-file',str(case.root/'renderer.ttf'),
        '--font-family',FONT_FAMILY,str(source),str(target)],cwd=case.root,timeout=30,capture_output=True)
    require(result.returncode==0,'Pinned variant rasterizer failed')
    return target.read_bytes()


def judge_variants(case,tools):
    # Admit every source/resource before invoking the renderer.
    original=delivered(case,'base.svg');restored=delivered(case,'editable.svg')
    svg_layout(case,original,'base');svg_layout(case,restored,'base')
    roots={name:svg_layout(case,delivered(case,name+'.svg'),name) for name in ROWS}
    case.check('base-preserved',lambda:require(original==restored and
        same_json(strict_json(delivered(case,'variants.json')),manifest()),'Base artwork or retained dataset definitions changed'))
    for name,w,h,_,_ in BOARDS:
        rendered=render_variant(case,tools,name,roots[name])
        def picture(name=name,w=w,h=h,rendered=rendered):
            png_check(delivered(case,name+'.png'),w,h,expected_picture(name))
            png_check(rendered,w,h,expected_picture(name))
        case.check(name+'-pixels',picture)
    case.check('outputs-preserved',lambda:require(strict_json(delivered(case,'outputs.json'))==
        {name:sha(delivered(case,name+'.png')) for name in ROWS},'An earlier delivery differs from its recorded hash'))
    case.not_applicable('variant-bindings','The baseline retains shared SVG instances and editable datasets; this check validates Inkbolt typed bindings.')
    case.not_applicable('history-valid','Inkbolt session history is unavailable to the no-engine arm.')
