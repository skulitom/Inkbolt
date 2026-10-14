"""B16 bounded editable text repair, original metrics and pinned SVG rendering."""
import copy
import struct
import subprocess
import xml.etree.ElementTree as ET

from benchmark_baseline import _numbers
from benchmark_baseline_flow import same_json,paint
from benchmark_diagram import delivered
from benchmark_graphics import png_check
from benchmark_repair import initial_document,original_font,diagnosis,delivery_identity,expected_picture,FONT_FAMILY
from benchmark_runtime import require,strict_json
from workload_cases import sha

NS='{http://www.w3.org/2000/svg}'


def svg_source(raw,width):
    require(len(raw)<=16*1024 and b'<!DOCTYPE' not in raw.upper(),'Oversized or unsupported repair SVG')
    root=ET.fromstring(raw)
    require(root.tag==NS+'svg' and set(root.attrib)<={'width','height','viewBox','version'} and
        [_numbers(root.get(k,'')) for k in ('width','height')]==[[48],[32]] and
        _numbers(root.get('viewBox','0 0 48 32'))==[0,0,48,32] and len(root)==2,'Repair canvas changed')
    frame,other=root
    require(frame.tag==NS+'svg' and set(frame.attrib)<={'id','x','y','width','height','viewBox'} and
        frame.get('id')=='label' and [_numbers(frame.get(k,'')) for k in ('x','y','width','height')]==[[0],[0],[width],[24]] and
        _numbers(frame.get('viewBox',f'0 0 {width} 24'))==[0,0,width,24] and len(frame)==1,'Text frame changed')
    text=frame[0]
    require(text.tag==NS+'text' and set(text.attrib)=={'x','y','font-family','font-size','fill'} and not list(text) and
        text.text=='AA' and [_numbers(text.get(k,'')) for k in ('x','y','font-size')]==[[0],[16],[20]] and
        text.get('font-family')==FONT_FAMILY and paint(text.get('fill',''),(20,80,150)),'Editable text/font/placement changed')
    require(other.tag==NS+'rect' and not list(other) and set(other.attrib)=={'id','x','y','width','height','fill'} and
        other.get('id')=='other' and [_numbers(other.get(k,'')) for k in ('x','y','width','height')]==[[32],[20],[8],[8]] and
        paint(other.get('fill',''),(30,150,70)),'Unrelated artwork changed')
    require(all(not (n.tail or '').strip() and (n.tag==NS+'text' or not (n.text or '').strip()) for n in root.iter()),
            'Unexpected visible text in repair SVG')


def admitted_sources(case):
    expected=initial_document(original_font(case));after=copy.deepcopy(expected);after['items'][0]['content']['frame']['width']=24
    for name,value in (('before.json',expected),('editable.json',after)):
        raw=delivered(case,name);require(len(raw)<=16*1024 and same_json(strict_json(raw),value),'Only frame width may change in the repair recipe')
    svg_source(delivered(case,'before.svg'),12);svg_source(delivered(case,'editable.svg'),24)


def measured_width(raw):
    # Original fixture: cmap glyph A = 2, no AA kerning, 20 units at 1000 UPEM.
    # Read original SFNT metrics rather than trusting the solver's diagnosis.
    count=struct.unpack_from('>H',raw,4)[0]
    tables={}
    for at in range(12,12+16*count,16):
        tag,_,offset,length=struct.unpack_from('>4sIII',raw,at);tables[tag]=raw[offset:offset+length]
    units=struct.unpack_from('>H',tables[b'head'],18)[0]
    advance=struct.unpack_from('>H',tables[b'hmtx'],8)[0]
    return advance*2*20/units


def render_repair(case,tools):
    target=getattr(case,'judge_root',case.root)/'judge-repair.png'
    require(not target.exists(),'Repair judge output must be new')
    result=subprocess.run([tools['resvg']['path'],'--skip-system-fonts','--use-font-file',str(case.root/'renderer.ttf'),
        '--font-family',FONT_FAMILY,str(case.root/'editable.svg'),str(target)],cwd=case.root,timeout=30,capture_output=True)
    require(result.returncode==0,'Pinned repair rasterizer failed')
    return target.read_bytes()


def judge_repair(case,tools):
    require(case.check('no-collateral-edits',lambda:admitted_sources(case)),'Repair source was not admitted')
    def overflow():
        width=measured_width(delivered(case,'original.ttf'))
        require(12<width==24 and same_json(strict_json(delivered(case,'diagnostics.json')),diagnosis()),
            'Original font metrics and actionable overflow diagnosis differ')
    case.check('seeded-diagnosis',overflow)
    rendered=render_repair(case,tools)
    def picture():
        for raw in (rendered,delivered(case,'review.png')):png_check(raw,48,32,expected_picture())
    case.check('repair-pixels',picture)
    def delivery():
        raw=delivered(case,'repaired.png');value=strict_json(delivered(case,'delivery.json'))
        require(same_json(value,delivery_identity(raw,sha(raw))) and value['sha256']==value['preflight_sha256'],
            'Retained prepared and delivered PNG identities differ')
        png_check(raw,48,32,expected_picture())
    case.check('preflight-delivery',delivery)
    case.not_applicable('history-valid','The baseline retains before/after sources and delivery identities; Inkbolt durable proposal/session history is unavailable.')
