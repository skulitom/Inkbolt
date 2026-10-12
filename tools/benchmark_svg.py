"""B04 original SVG fixture, reference solve and independent artifact checks."""
import base64
import copy
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from benchmark_baseline import _numbers, _transform, _multiply
from benchmark_diagram import delivered
from benchmark_graphics import BLUE, pixels, png_check, store, apply, source_snapshot
from benchmark_runtime import require, strict_json
from workload_cases import save, save_json, sha

PROMPT = Path(__file__).with_name('benchmark_prompts')/'B04.md'
PREVIEW_FILES = {'revised-pixels':'preview.png'}
DESCRIPTION = 'Original benchmark description'
SOURCE = b'<svg xmlns="http://www.w3.org/2000/svg" width="32" height="24"><desc>Original benchmark description</desc><g id="layer" transform="translate(3,2)"><path id="block" d="M2 3 H10 V9 H2 Z" fill="#145096"/></g></svg>'
IDENTITY = (1,0,0,1,0,0)
NS = '{http://www.w3.org/2000/svg}'


def fixture(case):
    case.source('original.svg', SOURCE)


def solve(case):
    imported = case.call('import', 'svg.import', id='imported', source=dict(kind='file', source_path='original.svg'))
    save_json(case.root/'import-receipt.json', imported)
    mapping = {row['source_id']:row['item_id'] for row in imported['mapping'] if row.get('source_id')}
    store(case, imported['document'])
    changed = apply(case, 'move', 0, [dict(op='transform', id=mapping['block'], matrix=[1,0,0,1,4,-1], space='world')])
    source_snapshot(case, changed['document_ref'])
    case.call('deliver-svg', 'document.publish', document=changed['document_ref'], output=dict(format='svg', file_name='revised.svg'))
    result = case.call('preview', 'document.preview', document=changed['document_ref'], options={}, preview=True)
    save(case.root/'preview.png', base64.b64decode(result['artifact']['data'], validate=True))
    save_json(case.root/'import-report.json', dict(source_sha256=sha(delivered(case,'original.svg')), mapping=mapping,
        losses=['source_ids_remapped','description_omitted']))


def expected_picture():
    return pixels(32,24,[(9,4,8,6,BLUE)])


def path_controls(value):
    """Independent, deliberately bounded absolute M/L/H/V/Z delivery grammar."""
    tokens=[];end=0
    for match in re.finditer(r'[MLHVZ]|[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?',value):
        require(not value[end:match.start()].strip(' ,\t\r\n'), 'Unsupported SVG path syntax')
        tokens.append(match[0]);end=match.end()
    require(not value[end:].strip(' ,\t\r\n') and len(tokens)<=32, 'Invalid or oversized path controls')
    points=[];index=0
    while index < len(tokens):
        command=tokens[index];index+=1
        if command=='Z':
            require(index==len(tokens) and points==[(2,3),(10,3),(10,9),(2,9)], 'Path controls changed')
            return
        require(command in ('M','L','H','V') and (command=='M')== (not points), 'Expected explicit original path commands')
        count=2 if command in ('M','L') else 1
        values=[float(v) for v in tokens[index:index+count]];index+=count
        require(len(values)==count and all(math.isfinite(v) for v in values), 'Invalid path coordinate')
        points.append(tuple(values) if count==2 else (values[0],points[-1][1]) if command=='H' else (points[-1][0],values[0]))
    require(False, 'The original closed path must remain closed')


def svg_artifact(raw, mapping):
    require(len(raw)<=1024*1024, 'B04 SVG exceeds its delivery bound')
    text=raw.decode('utf-8')
    require('<!DOCTYPE' not in text.upper(), 'Document types are not task inputs')
    require(isinstance(mapping,dict) and set(mapping)=={'layer','block'} and
        all(isinstance(v,str) and v for v in mapping.values()) and len(set(mapping.values()))==2, 'Expected distinct layer/path mappings')
    root=ET.fromstring(text)
    require(root.tag==NS+'svg' and set(root.attrib)<={'width','height','viewBox','version','color-interpolation'} and
        _numbers(root.get('width',''))==[32] and _numbers(root.get('height',''))==[24] and
        _numbers(root.get('viewBox','0 0 32 24'))==[0,0,32,24] and root.get('color-interpolation','sRGB')=='sRGB', 'SVG canvas changed')
    rows=[];ids={};descriptions=[]
    def visit(node, ancestors, matrix):
        require(len(rows)<16 and len(ancestors)<=8, 'SVG structure exceeds the task bound')
        tag=node.tag.removeprefix(NS)
        require(node.tag==NS+tag and tag in ('svg','g','path','title','desc'), 'Unexpected SVG element')
        allowed={'id','transform','opacity','style'} if tag=='g' else {'id','transform','opacity','d','fill','fill-opacity','fill-rule','stroke'} if tag=='path' else set() if tag in ('title','desc') else set(root.attrib)
        require(set(node.attrib)<=allowed and not (node.tail or '').strip(), 'Unexpected SVG attributes or text')
        if tag in ('title','desc'):
            require(not list(node), 'Nested text markup is outside this task')
            if tag=='desc':
                require(ancestors==[root] and node.text==DESCRIPTION, 'Unexpected description or ownership')
                descriptions.append(node.text)
            return
        require(not (node.text or '').strip(), 'Unexpected text content')
        require(_numbers(node.get('opacity','1'))==[1], 'Original opacity changed')
        require(node.get('style','').replace(' ','').strip(';') in ('','isolation:isolate'), 'Unexpected style')
        local=_transform(node.get('transform',''));world=_multiply(matrix,local)
        require(all(math.isfinite(v) for v in world), 'Invalid SVG transform')
        ident=node.get('id')
        if ident:
            require(ident not in ids, 'Duplicate SVG ID');ids[ident]=node
        rows.append((node,ancestors,local,world))
        children=[child for child in node if child.tag not in (NS+'title',NS+'desc')]
        if tag in ('svg','g'): require(len(children)==1, 'Expected one retained group/path chain')
        else:
            require(not list(node), 'The path cannot contain extra content')
            path_controls(node.get('d',''))
            fill=node.get('fill','').strip().lower();rgb=re.fullmatch(r'rgb\(([^()]*)\)',fill)
            require((fill=='#145096' or (rgb is not None and _numbers(rgb[1])==[20,80,150])) and
                _numbers(node.get('fill-opacity','1'))==[1] and node.get('fill-rule','nonzero')=='nonzero' and
                node.get('stroke','none')=='none', 'Original path paint changed')
        for child in node: visit(child,ancestors+[node],world)
    visit(root,[],IDENTITY)
    paths=[row for row in rows if row[0].tag==NS+'path']
    require(len(paths)==1 and len(descriptions)<=1, 'Expected one editable path and at most the original description')
    path,ancestors,_,world=paths[0]
    layer,block=ids.get(mapping['layer']),ids.get(mapping['block'])
    require(layer is not None and layer.tag==NS+'g' and layer in ancestors and
        block is not None and block in ancestors[ancestors.index(layer)+1:]+[path], 'Required layer/path ownership changed')
    for node,_,local,_ in rows:
        wanted=(1,0,0,1,3,2) if node is layer else (1,0,0,1,4,-1) if node is block else IDENTITY
        require(local==wanted, 'The requested path translation must be the only transform change')
    require(world==(1,0,0,1,7,1), 'Revised world placement changed')
    return dict(description_preserved=bool(descriptions))


def declared_losses(case, report, artifact):
    require(set(report)=={'source_sha256','mapping','losses'} and report['source_sha256']==case.sources['original.svg'],
        'The report must identify the exact original source')
    expected=[]
    if report['mapping']!={'layer':'layer','block':'block'}: expected.append('source_ids_remapped')
    if not artifact['description_preserved']: expected.append('description_omitted')
    require(isinstance(report['losses'],list) and sorted(report['losses'])==sorted(expected), 'Loss disclosure differs from the delivered SVG')


def judge(case):
    report=strict_json(delivered(case,'import-report.json'))
    receipt=strict_json(delivered(case,'import-receipt.json'))
    raw=delivered(case,'editable.json');actual=strict_json(raw)
    artifact=svg_artifact(delivered(case,'revised.svg'),report['mapping'])
    imported=case.call('judge-import','svg.import',id=receipt['document']['id'],source=dict(kind='file',source_path='original.svg'))
    mapped={row['source_id']:row['item_id'] for row in imported['mapping'] if row.get('source_id')}
    expected=copy.deepcopy(imported['document'])
    expected['revision']=actual['revision']
    next(item for item in expected['items'] if item['id']==mapped['block'])['transform']=[1,0,0,1,4,-1]
    def structure():
        require(receipt['source']==imported['source'] and receipt['document']==imported['document'] and
            receipt['mapping']==imported['mapping'] and report['mapping']==mapped, 'Import receipt or source mapping changed')
        require(type(actual['revision']) is int and actual['revision']>0 and actual['items']==expected['items'] and
            all(actual[key]==expected[key] for key in ('width','height','kind','color_space')), 'Imported structure or controls changed')
    case.check('imported-structure',structure)
    def losses():
        declared_losses(case,report,artifact)
        require(receipt.keys()==imported.keys() and all(receipt[key]==imported[key]
            for key in ('losses','approximations','definitions')), 'The original import loss receipt must remain complete')
    case.check('declared-losses',losses)
    reopened=case.call('judge-reopen','document.validate',document=dict(file_path='editable.json',sha256=sha(raw)))
    svg=case.call('judge-svg','svg.import',id='judge-svg',source=dict(kind='file',source_path='revised.svg'))
    previews=[case.call(name,'document.preview',document=doc,options={},preview=True)
        for name,doc in (('judge-preview',reopened),('judge-svg-preview',svg['document']))]
    def picture():
        png_check(delivered(case,'preview.png'),32,24,expected_picture())
        for result in previews:
            png_check(base64.b64decode(result['artifact']['data'],validate=True),32,24,expected_picture())
    case.check('revised-pixels',picture)
    case.check('editable-source',lambda:require(reopened==actual and actual['items']==expected['items'], 'The final snapshot must reopen with retained editable structure'))


def svg_artwork(case):
    fixture(case);case.begin(PROMPT.read_text(encoding='utf-8'));solve(case)
    case.begin_judging();judge(case)
    if any(row['name']=='revised-pixels' and row['status']=='pass' for row in case.checks):
        case.verified_preview(delivered(case,'preview.png'))
