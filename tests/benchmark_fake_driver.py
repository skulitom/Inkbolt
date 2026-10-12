"""Original synthetic external client for lifecycle tests; refuses model credit."""
import json
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from benchmark_diagram import solve,expected_picture
from test_images_cli import png

SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="56" font-family="Inkbolt Diagram Fixture" font-size="20"><rect x="8" y="8" width="48" height="36" fill="#145096"/><rect x="80" y="8" width="40" height="36" fill="#1e9646"/><rect x="56" y="25" width="24" height="2" fill="#505050"/><text x="20" y="32" fill="white">AA</text><text x="96" y="32" fill="white">A</text></svg>'


def main():
    request=json.loads(Path(sys.argv[-1]).read_text(encoding='utf-8'))
    assert request['contract']['kind']=='synthetic', 'A fake driver cannot impersonate a model'
    if '--timeout' in sys.argv: time.sleep(30)
    root=Path(request['workspace']);events=[]
    if request['contract']['arm']=='model':
        def call(step,command,preview=False,**arguments):
            payload=json.dumps(dict(command=command,**arguments)).encode()
            process=subprocess.run([request['engine_executable'],'--workspace',str(root)],input=payload,capture_output=True,timeout=20)
            response=json.loads(process.stdout)
            events.append(dict(step=step,request=payload.decode(),response=process.stdout.decode()))
            assert response['ok'] and process.returncode==0
            return response['result']
        solve(SimpleNamespace(root=root,call=call))
    else:
        assert request['mcp_config'] is None and 'engine_executable' not in request
        (root/'editable.svg').write_text(SVG,encoding='utf-8')
        renderer=request['baseline_tools']['resvg']
        if renderer['version']=='synthetic-fixture':
            (root/'preview.png').write_bytes(png(128,56,expected_picture()))
        else:
            subprocess.run([renderer['path'],'--skip-system-fonts','--use-font-file',str(root/'original.ttf'),
                str(root/'editable.svg'),str(root/'preview.png')],check=True)
        events.append(dict(kind='synthetic',action='authored baseline fixture'))
    if '--changed-prompt' in sys.argv: (root/'task.txt').write_text('changed',encoding='utf-8')
    if '--wrong-image' in sys.argv: (root/'preview.png').write_bytes(png(1,1,b'\0'*4))
    target=Path(request['result_path'])
    (target.parent/'transcript.jsonl').write_text('\n'.join(json.dumps(row) for row in events)+'\n',encoding='utf-8')
    observed=None
    if '--usage' in sys.argv:
        observed=dict(source='client_reported',token_usage=dict(input_tokens=20,output_tokens=10),model_calls=2,agent_seconds=1.5)
    if '--invalid-usage' in sys.argv: observed=dict(source='client_reported',model_calls=True)
    result=dict(schema_version=1,contract_sha256=request['contract_sha256'],kind='synthetic',
        client=request['contract']['client'],model=request['contract']['model'],transcript='transcript.jsonl',observations=observed)
    if '--wrong-contract' in sys.argv: result['contract_sha256']='0'*64
    target.write_text(json.dumps(result),encoding='utf-8')
    print('Synthetic driver console; not retained as transcript')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
