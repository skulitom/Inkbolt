"""Measure saved-result traffic with an original fixture, without claiming model task success."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import queue
import random
import subprocess
import sys
import tempfile
import threading
import time

from measure_discovery import ROOT, source_identity
sys.path.insert(0, str(ROOT / 'tests'))
from mcp_artifacts import restore, image_payloads


def measure_mcp(executable):
    """Measure actual JSON-RPC lines, retaining unsupported modes in old builds."""
    rng=random.Random(5101)
    pixels=bytes(channel for _ in range(128*128) for channel in (*rng.randbytes(3),255))
    request=dict(command='document.create',id='original-mcp-volume',kind='raster',width=128,height=128)
    def cli(request):
        result=subprocess.run([str(executable)],input=json.dumps(request).encode(),capture_output=True,timeout=30,check=True)
        envelope=json.loads(result.stdout)
        if not envelope['ok'] or result.stderr:raise RuntimeError('CLI measurement fixture failed')
        return envelope
    document=cli(request)['result']
    document['items']=[dict(id='pixels',content=dict(type='raster',width=128,height=128,rgba_hex=pixels.hex()))]
    cases=[('png','document.export',dict(document=document,format='png')),
           ('snapshot','document.validate',dict(document=document))]
    expected={name:cli(dict(command=command,**arguments)) for name,command,arguments in cases}
    process=subprocess.Popen([str(executable),'mcp','--tools','core'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    lines=queue.Queue()
    reader=threading.Thread(target=lambda:[lines.put(line) for line in process.stdout],daemon=True);reader.start()
    rows=[];rid=0
    def rpc(method,params):
        nonlocal rid
        rid+=1;wire=json.dumps(dict(jsonrpc='2.0',id=rid,method=method,params=params),separators=(',',':')).encode()+b'\n'
        start=time.perf_counter();process.stdin.write(wire);process.stdin.flush();raw=lines.get(timeout=30)
        packet=json.loads(raw)
        if packet.get('id')!=rid or 'error' in packet:raise RuntimeError('MCP measurement response failed')
        return packet['result'],raw,len(wire),time.perf_counter()-start
    try:
        rpc('initialize',dict(protocolVersion='2025-11-25',capabilities={},clientInfo=dict(name='original-response-measurement',version='1')))
        process.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n');process.stdin.flush()
        for name,command,arguments in cases:
            for mode in ('json','markdown','structured','preview'):
                options=dict(command=command,arguments=arguments)
                if mode!='json':options['response_format']=mode
                result,raw,input_bytes,seconds=rpc('tools/call',dict(name='inkbolt_run',arguments=options))
                error=result['structuredContent'].get('error')
                row=dict(case=name,response_format=mode,input_bytes=input_bytes,wire_bytes=len(raw),seconds=seconds,
                         status='unsupported' if error else 'passed',error=error)
                if error:
                    if error['code']!='INVALID_REQUEST':raise RuntimeError('Unexpected measurement failure')
                else:
                    if restore(result)!=expected[name]:raise RuntimeError('MCP presentation changed the original result')
                    row.update(original_result_recovered=True,png_payload_occurrences=[raw.count(data.encode()) for data in set(image_payloads(expected[name]))],
                               text_bytes=len(result['content'][0]['text'].encode()),
                               structured_bytes=len(json.dumps(result['structuredContent'],separators=(',',':')).encode()))
                rows.append(row)
    finally:
        process.stdin.close()
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.kill();process.wait();raise
        reader.join(timeout=2);stderr=process.stderr.read();process.stdout.close();process.stderr.close()
        if process.returncode or stderr:raise RuntimeError('MCP measurement did not exit cleanly')
    return dict(fixture=dict(kind='original_seeded_opaque_rgba8',width=128,height=128,pixels_sha256=hashlib.sha256(pixels).hexdigest()),rows=rows)


def measure(executable):
    calls = []
    with tempfile.TemporaryDirectory(prefix='inkbolt-volume-') as directory:
        def request(command, **arguments):
            payload = json.dumps(dict(command=command, **arguments), separators=(',', ':')).encode()
            started = time.perf_counter()
            process = subprocess.run([str(executable), '--workspace', directory], input=payload,
                                     capture_output=True, timeout=30, check=True)
            envelope = json.loads(process.stdout)
            if not envelope.get('ok') or process.stderr:
                raise RuntimeError('Measurement request failed')
            calls.append(dict(command=command, response_mode=arguments.get('response_mode', 'full'),
                              input_bytes=len(payload), output_bytes=len(process.stdout),
                              elapsed_seconds=time.perf_counter() - started))
            return envelope['result']

        doc = request('document.create', id='original-volume-fixture', kind='raster', width=256, height=256)
        pixels = bytes([17, 55, 142, 255] * 65536)
        doc['items'] = [dict(id='paint', content=dict(type='raster', width=256, height=256, rgba_hex=pixels.hex()))]
        request('session.create', session_id='volume', request_id='create', document=doc)
        full = request('session.receipt', session_id='volume', request_id='create', response_mode='full')
        full_output = calls[-1]['output_bytes']
        compact = request('session.receipt', session_id='volume', request_id='create', response_mode='compact')
        compact_output = calls[-1]['output_bytes']
        if compact['receipt_summary']['state_sha256'] != full['receipt']['state_sha256']:
            raise RuntimeError('Compact result changed state identity')
        if compact['document_ref']['revision'] != full['document']['revision']:
            raise RuntimeError('Compact result changed document revision')
        rendered = request('document.render', document=compact['document_ref'])
        if rendered['data'] != pixels.hex():
            raise RuntimeError('Referenced pixels differ from the original fixture')
        return dict(fixture=dict(kind='original_constant_rgba8', width=256, height=256,
                                 pixels_sha256=hashlib.sha256(pixels).hexdigest()),
                    full_receipt_stdout_bytes=full_output, compact_receipt_stdout_bytes=compact_output,
                    retained_bytes_ratio=compact_output / full_output,
                    compact_within_8kib=compact_output <= 8192,
                    original_pixels_recovered=True, calls=calls)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', type=Path, default=ROOT / 'target/debug' / ('inkbolt.exe' if platform.system() == 'Windows' else 'inkbolt'))
    parser.add_argument('--output', type=Path, help='New JSON report outside the repository; parent must exist')
    args = parser.parse_args()
    if args.output and args.output.resolve().is_relative_to(ROOT.resolve()):
        parser.error('Retain generated measurement reports outside the repository')
    executable = args.executable.resolve(strict=True)
    source_before = source_identity()
    executable_before = hashlib.sha256(executable.read_bytes()).hexdigest()
    measurement = measure(executable)
    mcp = measure_mcp(executable)
    report = dict(schema_version=2, measurement='session_receipt_and_mcp_response_volume', model_trials=False,
                  source_sha256=source_before, executable_sha256=executable_before,
                  source_unchanged=source_before == source_identity(),
                  executable_unchanged=executable_before == hashlib.sha256(executable.read_bytes()).hexdigest(),
                  build_provenance='Existing executable; source-to-binary correspondence requires a recorded build',
                  environment=dict(system=platform.system(), release=platform.release(), machine=platform.machine()),
                  mcp=mcp, **measurement)
    if not report['source_unchanged'] or not report['executable_unchanged']:
        raise RuntimeError('Measurement inputs changed; rerun on a stable build')
    rendered = json.dumps(report, indent=2) + '\n'
    if args.output:
        with args.output.open('x', encoding='utf-8') as output:
            output.write(rendered)
    print(rendered, end='')


if __name__ == '__main__':
    main()
