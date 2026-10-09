"""Measure paging and PNG transport traffic; this is not a model or memory benchmark."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import platform
import queue
import random
import subprocess
import tempfile
import threading
import time

from measure_discovery import ROOT, source_identity


def encoded(value):
    return json.dumps(value, separators=(',', ':')).encode() + b'\n'


def measure(executable):
    calls=[]
    with tempfile.TemporaryDirectory(prefix='inkbolt-inspection-') as directory:
        def cli(command, **arguments):
            data=encoded(dict(command=command, **arguments)); started=time.perf_counter()
            process=subprocess.run([str(executable),'--workspace',directory],input=data,capture_output=True,timeout=30,check=True)
            result=json.loads(process.stdout)
            if process.stderr or not result.get('ok'): raise RuntimeError('CLI measurement failed')
            calls.append(dict(transport='cli',command=command,input_bytes=len(data),output_bytes=len(process.stdout),elapsed_seconds=time.perf_counter()-started))
            return result['result']
        doc=cli('document.create',id='inspection-volume',kind='vector',width=1024,height=32)
        doc['resource_profile']='large_vector'
        doc['items']=[dict(id=f'item-{i:04}',name=f'Original item {i}',content=dict(type='vector',geometry=dict(shape='rect',x=i,y=2,width=1,height=3),fill=[20,80,170,255])) for i in range(513)]
        saved=cli('session.create',session_id='inventory',request_id='create',document=doc,response_mode='compact')
        ref=saved['document_ref']
        full=cli('document.inspect',document=ref); full_bytes=calls[-1]['output_bytes']
        cursor=None; records=[]; page_bytes=[]
        while True:
            page=cli('document.inspect.page',document=ref,options=dict(limit=128,cursor=cursor,view=dict(collection='items',fields=['name','bounds'])))
            page_bytes.append(calls[-1]['output_bytes']); records.extend(page['records'])
            cursor=page['next_cursor']
            if cursor is None: break
        if [r['id'] for r in records] != [i['id'] for i in doc['items']]: raise RuntimeError('Paged inventory changed IDs or ordering')
        for i,row in enumerate(records):
            if row['geometry_bounds'] != [i,2,i+1,5] or row['index'] != i: raise RuntimeError('Paged coordinates differ from original fixture')
        if len(full['items']) != len(records): raise RuntimeError('Paged inventory omitted items')
        pixels=random.Random(1709).randbytes(128*128*4)
        raster=cli('document.create',id='image-volume',kind='raster',width=128,height=128)
        raster['items']=[dict(id='pixels',content=dict(type='raster',width=128,height=128,rgba_hex=pixels.hex()))]
        image_ref=cli('session.create',session_id='image',request_id='create',document=raster,response_mode='compact')['document_ref']
        process=subprocess.Popen([str(executable),'--workspace',directory,'mcp','--tools','core'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        lines=queue.Queue()
        reader=threading.Thread(target=lambda:[lines.put(line) for line in process.stdout],daemon=True); reader.start()
        def rpc(rid, method, params):
            data=encoded(dict(jsonrpc='2.0',id=rid,method=method,params=params)); started=time.perf_counter()
            process.stdin.write(data);process.stdin.flush();raw=lines.get(timeout=30)
            response=json.loads(raw)
            if response.get('id') != rid or 'error' in response: raise RuntimeError('MCP measurement failed')
            calls.append(dict(transport='mcp',method=method,response_format=params.get('arguments',{}).get('response_format'),input_bytes=len(data),output_bytes=len(raw),elapsed_seconds=time.perf_counter()-started))
            return response['result']
        try:
            rpc(1,'initialize',dict(protocolVersion='2025-11-25',capabilities={},clientInfo=dict(name='original-transport-fixture',version='1')))
            process.stdin.write(encoded(dict(jsonrpc='2.0',method='notifications/initialized')));process.stdin.flush()
            args=dict(command='document.export',arguments=dict(document=image_ref,format='png'))
            normal=rpc(2,'tools/call',dict(name='inkbolt_run',arguments=args)); normal_bytes=calls[-1]['output_bytes']
            preview=rpc(3,'tools/call',dict(name='inkbolt_run',arguments=dict(**args,response_format='preview'))); preview_bytes=calls[-1]['output_bytes']
            if normal['isError'] or preview['isError']: raise RuntimeError('PNG fixture failed')
            artifact=preview['structuredContent']['result']; reference=artifact['payload_ref']
            data=preview['content'][reference['index']]['data']; raw=base64.b64decode(data,validate=True)
            if hashlib.sha256(raw).hexdigest()!=reference['sha256'] or len(raw)!=reference['bytes']: raise RuntimeError('PNG identity mismatch')
            restored=dict(artifact);del restored['payload_ref'];restored.update(encoding='base64',data=data)
            if restored!=normal['structuredContent']['result']: raise RuntimeError('Preview changed original artifact metadata or bytes')
            if encoded(preview).count(data.encode())!=1: raise RuntimeError('PNG data was duplicated')
        finally:
            process.stdin.close()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait();raise
            reader.join(timeout=2);stderr=process.stderr.read();process.stdout.close();process.stderr.close()
            if process.returncode or stderr: raise RuntimeError('MCP fixture did not exit cleanly')
        return dict(items=513,full_inspection_stdout_bytes=full_bytes,selected_page_stdout_bytes=page_bytes,
                    selected_inventory_stdout_bytes=sum(page_bytes),inventory_and_coordinates_verified=True,
                    source_pixels_sha256=hashlib.sha256(pixels).hexdigest(),png_sha256=reference['sha256'],
                    legacy_png_wire_bytes=normal_bytes,preview_png_wire_bytes=preview_bytes,
                    png_payload_occurrences=1,original_artifact_reconstructed=True,calls=calls)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable',type=Path,default=ROOT/'target/debug'/('inkbolt.exe' if platform.system()=='Windows' else 'inkbolt'))
    parser.add_argument('--output',type=Path,help='New report outside the repository; parent must exist')
    args=parser.parse_args()
    if args.output and args.output.resolve().is_relative_to(ROOT.resolve()):parser.error('Keep generated reports outside the repository')
    executable=args.executable.resolve(strict=True);source_before=source_identity();binary_before=hashlib.sha256(executable.read_bytes()).hexdigest()
    measured=measure(executable)
    report=dict(schema_version=1,measurement='inspection_and_image_traffic_only',model_trials=False,
                source_sha256=source_before,executable_sha256=binary_before,
                source_unchanged=source_before==source_identity(),executable_unchanged=binary_before==hashlib.sha256(executable.read_bytes()).hexdigest(),
                build_provenance='Existing executable; source-to-binary correspondence requires a recorded build',
                timing_scope='Observed process/RPC latency; uncontrolled background load; no performance gate or model-preview latency claim',
                environment=dict(system=platform.system(),release=platform.release(),machine=platform.machine()),**measured)
    if not report['source_unchanged'] or not report['executable_unchanged']:raise RuntimeError('Measurement inputs changed')
    rendered=json.dumps(report,indent=2)+'\n'
    if args.output:
        with args.output.open('x',encoding='utf-8') as file:file.write(rendered)
    print(rendered,end='')


if __name__=='__main__':main()
