"""Original synthetic external client for lifecycle tests; refuses model credit."""
import json
import hashlib
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from benchmark_diagram import solve,expected_picture
from benchmark_icons import solve as solve_icons, expected_board, COLORS
from benchmark_large_layout import solve as solve_layout, expected_picture as expected_layout
from benchmark_svg import solve as solve_svg, expected_picture as expected_svg
from benchmark_palette import solve as solve_palette, expected_picture as expected_palette
from benchmark_flow import solve as solve_flow, expected_picture as expected_flow, expected_lines, repaired, FONT_FAMILY
from benchmark_typography import (solve as solve_typography, expected_picture as expected_typography,
    FONT_FAMILY as TYPOGRAPHY_FAMILY, authored_geometry, shaping_report)
from benchmark_mask import solve as solve_mask, selected_pixels, expected_picture as expected_mask
from benchmark_baseline_mask import manifest as mask_manifest
from test_images_cli import png

SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="56" font-family="Inkbolt Diagram Fixture" font-size="20"><rect x="8" y="8" width="48" height="36" fill="#145096"/><rect x="80" y="8" width="40" height="36" fill="#1e9646"/><rect x="56" y="25" width="24" height="2" fill="#505050"/><text x="20" y="32" fill="white">AA</text><text x="96" y="32" fill="white">A</text></svg>'
ICONS_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="112" height="32">'+''.join(
    f'<svg id="board-{i}" x="{i*40}" y="0" width="32" height="32"><rect id="icon-{i}" '
    f'x="12" y="11" width="8" height="10" fill="#{bytes(color[:3]).hex()}"/></svg>'
    for i,color in enumerate(COLORS))+'</svg>'


def layout_svg(source):
    # This synthetic client converts the common JSON fixture without any engine.
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="500">']
    for item in source['items']:
        geometry = item['content']['geometry']
        attributes = ' '.join(f'{key}="{geometry[key]}"' for key in ('x','y','width','height'))
        transform = ' transform="translate(1,1)"' if item['id'] == 'cell-2473' else ''
        parts.append(f'<rect id="{item["id"]}" {attributes} fill="#145096"{transform}/>')
    return ''.join(parts)+'</svg>'


def palette_svg(source):
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="32" height="16">']
    for item in source['items']:
        geometry = item['content']['geometry']
        attributes = ' '.join(f'{key}="{geometry[key]}"' for key in ('x','y','width','height'))
        fill = item['content']['fill']
        color = [220,90,30] if isinstance(fill,dict) and fill.get('swatch') == 'shared' else fill[:3]
        parts.append(f'<rect id="{item["id"]}" {attributes} fill="#{bytes(color).hex()}"/>')
    return ''.join(parts)+'</svg>'


def flow_svg(source):
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="96" height="48">']
    for slot,x,width in (('first',0,24),('second',32,56)):
        parts.append(f'<svg id="{slot}" x="{x}" y="0" width="{width}" height="40">')
        lines = [row for row in expected_lines() if row['slot_id'] == slot]
        for index,row in enumerate(lines):
            text = source['stories']['article']['paragraphs'][0]['text'][row['start']:row['end']]
            parts.append(f'<text x="{row["column"]*32}" y="{16+20*(index%2)}" font-family="{FONT_FAMILY}" '
                f'font-size="20" fill="#145096" data-start="{row["start"]}" data-end="{row["end"]}">{text}</text>')
        parts.append('</svg>')
    return ''.join(parts)+'<rect id="unrelated" x="90" y="40" width="4" height="4" fill="#1e9646"/></svg>'


def typography_svg(texts, positioned=True):
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="960">']
    for i,text in enumerate(texts):
        if i == 3 and positioned:
            text = f'<tspan x="0">{text[:2]}</tspan><tspan x="260">{text[2:4]}</tspan><tspan x="460">{text[4:]}</tspan>'
        parts.append(f'<text x="0" y="{200+i*240}" font-family="{TYPOGRAPHY_FAMILY}" font-size="200" fill="#145096">{text}</text>')
    return ''.join(parts)+'</svg>'


def main():
    request=json.loads(Path(sys.argv[-1]).read_text(encoding='utf-8'))
    assert request['contract']['kind']=='synthetic', 'A fake driver cannot impersonate a model'
    if '--timeout' in sys.argv: time.sleep(30)
    root=Path(request['workspace']);events=[];task=request['contract']['task']
    assert task in ('B01','B02','B03','B04','B05','B06','B07','B08')
    if request['contract']['arm']=='model':
        def call(step,command,preview=False,**arguments):
            payload=json.dumps(dict(command=command,**arguments)).encode()
            process=subprocess.run([request['engine_executable'],'--workspace',str(root)],input=payload,capture_output=True,timeout=20)
            response=json.loads(process.stdout)
            events.append(dict(step=step,request=payload.decode(),response=process.stdout.decode()))
            assert response['ok'] and process.returncode==0
            return response['result']
        {'B01':solve, 'B02':solve_icons, 'B03':solve_layout, 'B04':solve_svg, 'B05':solve_palette,
         'B06':solve_flow, 'B07':solve_typography, 'B08':solve_mask}[task](SimpleNamespace(root=root,call=call))
    else:
        assert request['mcp_config'] is None and 'engine_executable' not in request
        if task=='B08':
            (root/'editable.json').write_text(json.dumps(mask_manifest()),encoding='utf-8')
        elif task=='B07':
            (root/'editable.svg').write_text(typography_svg(json.loads((root/'texts.json').read_bytes()),
                positioned='--naive-typography' not in sys.argv),encoding='utf-8')
            (root/'shaping.json').write_text(json.dumps(shaping_report(authored_geometry()[0])),encoding='utf-8')
        elif task=='B04':
            source=(root/'original.svg').read_text(encoding='utf-8').replace('<path ', '<path transform="translate(4,-1)" ')
            (root/'revised.svg').write_text(source,encoding='utf-8')
            (root/'import-report.json').write_text(json.dumps(dict(source_sha256=hashlib.sha256((root/'original.svg').read_bytes()).hexdigest(),
                mapping=dict(layer='layer',block='block'),losses=[])),encoding='utf-8')
        else:
            if task in ('B03','B05','B06'):
                layout = json.loads((root/'source.json').read_bytes())
                source = {'B03':layout_svg,'B05':palette_svg,'B06':flow_svg}[task](layout)
                if task == 'B06':
                    (root/'layout.json').write_text(json.dumps(repaired(layout)),encoding='utf-8')
                    (root/'flow-report.json').write_text(json.dumps(dict(original_overset=dict(paragraph=0,offset=8),
                        final_overset=None,lines=expected_lines())),encoding='utf-8')
            else: source = SVG if task == 'B01' else ICONS_SVG
            (root/'editable.svg').write_text(source,encoding='utf-8')
        renderer=request['baseline_tools']['resvg']
        if task=='B08':
            if renderer['version']=='synthetic-fixture':
                source=json.loads((root/'source.json').read_bytes())
                (root/'pixels.png').write_bytes(png(16,16,bytes.fromhex(source['items'][0]['content']['rgba_hex'])))
                gray=bytes(v for alpha in selected_pixels() for v in (alpha,alpha,alpha,255))
                for name in ('mask.png','selection.png'): (root/name).write_bytes(png(16,16,gray))
                (root/'preview.png').write_bytes(png(16,16,expected_mask()))
            else:
                script='''from PIL import Image, ImageDraw
from pathlib import Path
import json,sys
root=Path(sys.argv[1]);source=json.loads((root/'source.json').read_bytes())
layer=Image.frombytes('RGBA',(16,16),bytes.fromhex(source['items'][0]['content']['rgba_hex']))
mask=Image.new('L',(16,16));draw=ImageDraw.Draw(mask)
draw.rectangle((4,3,11,6),fill=255);draw.rectangle((4,7,7,12),fill=255)
layer.save(root/'pixels.png');mask.save(root/'mask.png');mask.save(root/'selection.png')
Image.composite(layer,Image.new('RGBA',(16,16)),mask).save(root/'preview.png')
'''
                subprocess.run([request['baseline_tools']['python']['path'],'-I','-c',script,str(root)],check=True)
        elif task=='B07':
            if renderer['version']=='synthetic-fixture':
                (root/'preview.png').write_bytes(png(1000,960,expected_typography()))
            else:
                subprocess.run([renderer['path'],'--skip-system-fonts','--use-font-file',str(root/'original.ttf'),
                    '--font-family',TYPOGRAPHY_FAMILY,str(root/'editable.svg'),str(root/'preview.png')],check=True)
        elif task=='B06':
            if renderer['version']=='synthetic-fixture':
                (root/'preview.png').write_bytes(png(96,48,expected_flow()))
            else:
                subprocess.run([renderer['path'],'--skip-system-fonts','--use-font-file',str(root/'original.ttf'),
                    '--font-family',FONT_FAMILY,str(root/'editable.svg'),str(root/'preview.png')],check=True)
        elif task=='B05':
            if renderer['version']=='synthetic-fixture':
                (root/'preview.png').write_bytes(png(32,16,expected_palette()))
            else:
                subprocess.run([renderer['path'],'--skip-system-fonts',str(root/'editable.svg'),str(root/'preview.png')],check=True)
        elif task=='B04':
            if renderer['version']=='synthetic-fixture':
                (root/'preview.png').write_bytes(png(32,24,expected_svg()))
            else:
                subprocess.run([renderer['path'],'--skip-system-fonts',str(root/'revised.svg'),str(root/'preview.png')],check=True)
        elif task=='B03':
            if renderer['version']=='synthetic-fixture':
                (root/'preview.png').write_bytes(png(1000,500,expected_layout()))
            else:
                subprocess.run([renderer['path'],'--skip-system-fonts',str(root/'editable.svg'),str(root/'preview.png')],check=True)
        elif task=='B02':
            if renderer['version']=='synthetic-fixture':
                for i in range(3): (root/f'board-{i}.png').write_bytes(png(32,32,expected_board(i)))
            else:
                subprocess.run([renderer['path'],'--skip-system-fonts',str(root/'editable.svg'),str(root/'sheet.png')],check=True)
                # The client uses the permitted pinned imaging tool; the judge
                # independently renders each source viewport as its own SVG.
                script='from PIL import Image; import sys; from pathlib import Path; r=Path(sys.argv[1]); im=Image.open(r/"sheet.png"); [im.crop((i*40,0,i*40+32,32)).save(r/f"board-{i}.png") for i in range(3)]'
                subprocess.run([request['baseline_tools']['python']['path'],'-I','-c',script,str(root)],check=True)
        elif renderer['version']=='synthetic-fixture':
            (root/'preview.png').write_bytes(png(128,56,expected_picture()))
        else:
            subprocess.run([renderer['path'],'--skip-system-fonts','--use-font-file',str(root/'original.ttf'),
                str(root/'editable.svg'),str(root/'preview.png')],check=True)
        events.append(dict(kind='synthetic',action='authored baseline fixture'))
    if '--changed-prompt' in sys.argv: (root/'task.txt').write_text('changed',encoding='utf-8')
    if '--wrong-image' in sys.argv: (root/('board-1.png' if task=='B02' else 'preview.png')).write_bytes(png(1,1,b'\0'*4))
    target=Path(request['result_path'])
    (target.parent/'transcript.jsonl').write_text('\n'.join(json.dumps(row) for row in events)+'\n',encoding='utf-8')
    observed=None
    if '--usage' in sys.argv:
        observed=dict(source='client_reported',token_usage=dict(input_tokens=20,output_tokens=10),model_calls=2,agent_seconds=1.5)
    if '--preview-usage' in sys.argv:
        preview=root/('board-1.png' if task=='B02' else 'preview.png')
        observed=dict(source='client_reported',agent_seconds=1.5,first_preview_seconds=.5,
                      first_preview_sha256=hashlib.sha256(preview.read_bytes()).hexdigest())
    if '--invalid-usage' in sys.argv: observed=dict(source='client_reported',model_calls=True)
    result=dict(schema_version=1,contract_sha256=request['contract_sha256'],kind='synthetic',
        client=request['contract']['client'],model=request['contract']['model'],transcript='transcript.jsonl',observations=observed)
    if '--wrong-contract' in sys.argv: result['contract_sha256']='0'*64
    target.write_text(json.dumps(result),encoding='utf-8')
    print('Synthetic driver console; not retained as transcript')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
