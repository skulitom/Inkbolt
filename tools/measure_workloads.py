"""Reproducible original scale workloads; failed tasks are evidence, never passes."""
import argparse
import array
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import struct
import subprocess
import sys
import time

from measure_discovery import ROOT, source_identity

sys.path.insert(0, str(ROOT / 'tests'))
from test_images_cli import png
from test_editing_cli import png_pixels
from test_image_io_cli import tiff_tags
from pdf_reader import Pdf

SUITE_VERSION = 'scale-v1'
CASES = ('native-control', 'native-screen', 'stored-screen', 'social-square',
         'sparse-5000', 'mixed-5001', 'print-page')
COLOR = bytes([20, 80, 150, 255])


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, data):
    with path.open('xb') as output:
        output.write(data)


def save_json(path, data):
    save(path, (json.dumps(data, indent=2) + '\n').encode())


class MemoryCounters(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('faults', wintypes.DWORD)] + [
        (name, ctypes.c_size_t) for name in ('peak_working_set', 'working_set',
        'peak_paged_pool', 'paged_pool', 'peak_nonpaged_pool', 'nonpaged_pool',
        'commit', 'peak_commit')]


def process_memory(process):
    """Read OS lifetime high-water marks through the still-owned process handle.

    These are whole-process working set and commit, not sampled RSS, heap size,
    child aggregation, system memory or the Python fixture/oracle process.
    """
    if os.name != 'nt':
        return dict(available=False, reason='Only the Windows backend is verified')
    api = ctypes.WinDLL('psapi', use_last_error=True)
    api.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE,
        ctypes.POINTER(MemoryCounters), wintypes.DWORD]
    api.GetProcessMemoryInfo.restype = wintypes.BOOL
    counters = MemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    if not api.GetProcessMemoryInfo(int(process._handle), ctypes.byref(counters), counters.cb):
        return dict(available=False, reason=f'GetProcessMemoryInfo: {ctypes.get_last_error()}')
    return dict(available=True, method='Windows lifetime high-water marks on owned handle after exit',
                peak_working_set_bytes=counters.peak_working_set,
                peak_commit_bytes=counters.peak_commit)


def run_process(argv, payload, timeout):
    """Only used for synchronous commands; these workloads never start job workers."""
    start = time.perf_counter()
    with subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE,
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0) as process:
        timed_out = False
        try:
            stdout, stderr = process.communicate(payload, timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()  # This exact owned synchronous process only.
            stdout, stderr = process.communicate(timeout=10)
        elapsed = time.perf_counter() - start
        return dict(exit_code=process.returncode, seconds=elapsed, timed_out=timed_out,
                    memory=process_memory(process)), stdout, stderr


def document(name, kind, width, height, **fields):
    return dict(schema_version=2, id=name, kind=kind, width=width, height=height,
                color_space='srgb', **fields)


def rectangle(ident, x, y, width, height, fill=COLOR):
    return dict(id=ident, content=dict(type='vector', geometry=dict(shape='rect',
                x=x, y=y, width=width, height=height), fill=list(fill)))


def native_pixels(width, height):
    # Adjacent 16-bit codes, spatial variation and exact opaque alpha. Original
    # synthetic data, with no byte-depth plateaus or external image dependency.
    return b''.join(b''.join(struct.pack('<4H', (x + y * 17) % 65536,
        (x * 19 + y * 31) % 65536, 65535 - ((x * 7 + y) % 65536), 65535)
        for x in range(width)) for y in range(height))


def native_png(width, height, pixels):
    values = array.array('H')
    values.frombytes(pixels)
    if sys.byteorder == 'little':
        values.byteswap()
    raw = values.tobytes()
    return png(width, height, b'', depth=16,
               raw=b''.join(b'\0' + raw[y*width*8:(y+1)*width*8] for y in range(height)))


def rgba_pattern(width, height):
    palette = (bytes(4), bytes([23, 81, 147, 128]), COLOR, bytes([150, 80, 20, 255]))
    rows = [b''.join(palette[(x // 16 + y // 16) % 4] for x in range(width))
            for y in range(min(height, 64))]
    return b''.join(rows[y % len(rows)] for y in range(height))


def check_png(path, width, height, expected):
    w, h, actual, _ = png_pixels(path.read_bytes())
    assert (w, h) == (width, height), 'PNG dimensions changed'
    assert actual == expected, 'PNG pixels differ from the independent fixture'


def check_tiff(path, width, height, expected):
    data = path.read_bytes()
    tags = tiff_tags(data)
    assert tags[256] == (width,) and tags[257] == (height,), 'TIFF dimensions changed'
    assert tags[258] == (16,)*4 and tags[277] == (4,), 'Native depth/channels changed'
    assert tags[339] == (1,)*4 and tags[338] == (2,), 'Sample/alpha meaning changed'
    assert tags[259] == (1,) and tags[274] == (1,), 'Unexpected compression/orientation'
    assert tags.get(284, (1,)) == (1,), 'Unexpected planar configuration'
    assert len(tags[273]) == len(tags[279]), 'Incomplete TIFF strips'
    actual = b''.join(data[offset:offset+size] for offset, size in zip(tags[273], tags[279]))
    if data[:2] == b'MM':
        values = array.array('H'); values.frombytes(actual); values.byteswap()
        actual = values.tobytes()
    assert actual == expected, 'Native samples differ, including outside the edited region'


def check_pdf(path):
    pdf = Pdf(path.read_bytes())
    assert len(pdf.pages) == 1
    box = pdf.pages[0]['MediaBox']
    assert all(abs(a-b) <= 1e-8 for a, b in zip(box, [0, 0, 2480*.24, 3508*.24], strict=True))
    paths = pdf.paths()
    assert len(paths) == 1
    assert paths[0]['path'] == [('m', [[24, 24]]), ('l', [[72, 24]]),
                               ('l', [[72, 72]]), ('l', [[24, 72]]), ('h', [])]
    assert all(abs(a-b) <= 1e-8 for a, b in zip(paths[0]['color'], [20/255, 80/255, 150/255], strict=True))


class Case:
    def __init__(self, executable, root, name, repetition, timeout=90):
        self.executable, self.root, self.timeout = executable, root, timeout
        self.name, self.repetition = name, repetition
        root.mkdir()
        self.calls, self.checks, self.sources = [], [], {}
        self.first_preview = None

    def source(self, name, data):
        path = self.root / name
        save(path, data)
        self.sources[name] = sha(data)
        return str(path)

    def call(self, step, command, available=True, **arguments):
        if not available:
            self.calls.append(dict(step=step, command=command, status='blocked',
                                   reason='Required earlier result is unavailable'))
            return None
        payload = json.dumps(dict(command=command, **arguments), separators=(',', ':')).encode()
        prefix = self.root / f'{len(self.calls):02d}-{step}'
        save(prefix.with_suffix('.request.json'), payload)
        metrics, stdout, stderr = run_process([str(self.executable), '--workspace', str(self.root)],
                                             payload, self.timeout)
        save(prefix.with_suffix('.response.json'), stdout)
        save(prefix.with_suffix('.stderr.txt'), stderr)
        row = dict(step=step, command=command, request_bytes=len(payload), response_bytes=len(stdout),
                   retries=0, **metrics)
        self.calls.append(row)
        try:
            if metrics['timed_out']:
                raise ValueError('Owned process exceeded the measurement deadline')
            response = json.loads(stdout)
            if stderr or not isinstance(response, dict) or type(response.get('ok')) is not bool:
                raise ValueError('Invalid CLI envelope or unexpected stderr')
            if metrics['exit_code'] != (0 if response['ok'] else 1):
                raise ValueError('Exit code does not match CLI envelope')
            if not response['ok']:
                if not isinstance(response.get('error'), dict) or not response['error'].get('code'):
                    raise ValueError('Missing structured engine failure')
                row.update(status='engine_failure', error=response['error'])
                return None
            if not isinstance(response.get('result'), dict):
                raise ValueError('Missing structured engine result')
            row['status'] = 'success'
            return response['result']
        except (ValueError, TypeError) as error:
            row.update(status='harness_failure', error=str(error))
            return None

    def check(self, name, predicate):
        try:
            predicate()
            self.checks.append(dict(name=name, status='pass'))
            return True
        except (AssertionError, ValueError, KeyError, OSError, struct.error) as error:
            self.checks.append(dict(name=name, status='fail', error=f'{type(error).__name__}: {error}'))
            return False

    def publish(self, step, doc, format, oracle, **options):
        path = self.root / f'{step}.{format}'
        result = self.call(step, 'document.publish', available=doc is not None, document=doc,
                           output=dict(file_name=path.name, format=format, **options))
        if result is not None:
            correct = self.check(step, lambda: oracle(path))
            if correct and format == 'png' and self.first_preview is None:
                self.first_preview = sum(row.get('seconds', 0) for row in self.calls)
            return result
        self.check(step + '-no-partial-output', lambda: require(not path.exists(), 'Failed output exists'))
        return None

    def finish(self):
        self.check('source-preservation', lambda: require(all(
            sha((self.root / name).read_bytes()) == digest for name, digest in self.sources.items()),
            'Original fixture source changed'))
        success = bool(self.calls) and all(row['status'] == 'success' for row in self.calls)
        success = success and all(row['status'] == 'pass' for row in self.checks)
        memory = [row['memory'] for row in self.calls if 'memory' in row]
        available = bool(memory) and all(value['available'] for value in memory)
        result = dict(case=self.name, repetition=self.repetition, success=success,
            calls=self.calls, checks=self.checks, fixture_sources=self.sources,
            engine_seconds=sum(row.get('seconds', 0) for row in self.calls),
            request_bytes=sum(row.get('request_bytes', 0) for row in self.calls),
            response_bytes=sum(row.get('response_bytes', 0) for row in self.calls),
            process_calls=sum('exit_code' in row for row in self.calls),
            blocked_steps=sum(row['status'] == 'blocked' for row in self.calls),
            first_verified_png_engine_seconds=self.first_preview,
            memory_complete=available,
            peak_working_set_bytes=max(m['peak_working_set_bytes'] for m in memory) if available else None,
            peak_commit_bytes=max(m['peak_commit_bytes'] for m in memory) if available else None)
        save_json(self.root / 'case.json', result)
        return result


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def native_case(case, width, height):
    original = native_pixels(width, height)
    source = case.source('source.png', native_png(width, height, original))
    imported = case.call('import', 'sample.import', source_path=source, id='native')
    created = case.call('save', 'session.create', available=imported is not None,
        session_id='native', request_id='create', document=imported['document'] if imported else None,
        response_mode='compact')
    initial = created['document_ref'] if created else None
    options = dict(image_options=dict(depth='u16', channels='rgba', compression='none'))
    case.publish('initial', initial, 'tiff', lambda p: check_tiff(p, width, height, original), **options)
    replacement = bytes.fromhex('010002000300ffff') * 4
    edited = bytearray(original)
    for y in range(2):
        offset = ((17+y)*width+13)*8
        edited[offset:offset+16] = replacement[y*16:(y+1)*16]
    layer_id = imported['document']['items'][0]['id'] if imported else 'source'
    changed = case.call('edit', 'session.apply', available=initial is not None, session_id='native',
        expected_revision=0, request_id='replace', response_mode='compact',
        action=dict(type='edit', operations=[dict(op='sample_replace', id=layer_id,
            region=dict(x=13, y=17, width=2, height=2), data_hex=replacement.hex())]))
    current = changed['document_ref'] if changed else None
    case.publish('edited', current, 'tiff', lambda p: check_tiff(p, width, height, edited), **options)
    case.publish('historical', initial, 'tiff', lambda p: check_tiff(p, width, height, original), **options)
    undone = case.call('undo', 'session.apply', available=current is not None, session_id='native',
        expected_revision=1, request_id='undo', action=dict(type='undo'), response_mode='compact')
    restored = undone['document_ref'] if undone else None
    case.publish('restored', restored, 'tiff', lambda p: check_tiff(p, width, height, original), **options)
    verified = case.call('verify', 'session.verify', available=initial is not None, session_id='native')
    if verified:
        case.check('history-valid', lambda: require(verified['valid'], 'Session history is invalid'))
    if changed and undone:
        case.check('revision-order', lambda: require(
            (initial['revision'], current['revision'], restored['revision']) == (0, 1, 2),
            'Revision sequence changed'))


def sparse_document():
    items = [rectangle(f'cell-{i}', i % 100, i // 100, 1, 1, [i % 100, i // 100, 73, 255])
             for i in range(5000)]
    return document('cells', 'vector', 1024, 1024, resource_profile='large_vector', items=items)


def _run_case(case):
    if case.name in ('native-control', 'native-screen'):
        native_case(case, *( (128, 128) if case.name == 'native-control' else (1920, 1080)))
    elif case.name == 'stored-screen':
        pixels = rgba_pattern(1920, 1080)
        source = case.source('source.png', png(1920, 1080, pixels))
        imported = case.call('import', 'asset.import', source_path=source)
        doc = document('stored', 'raster', 1920, 1080, assets={'image': imported['asset']}, items=[
            dict(id='image', content=dict(type='image', asset_id='image', width=1920, height=1080))]) if imported else None
        case.publish('screen', doc, 'png', lambda p: check_png(p, 1920, 1080, pixels))
    elif case.name == 'social-square':
        doc = document('social', 'vector', 1080, 1080, items=[rectangle('field', 0, 0, 1080, 1080)])
        case.publish('social', doc, 'png', lambda p: check_png(p, 1080, 1080, COLOR*1080*1080))
    elif case.name in ('sparse-5000', 'mixed-5001'):
        doc = sparse_document()
        expected = bytearray(1024*1024*4)
        for i in range(5000):
            offset = ((i//100)*1024+i%100)*4
            expected[offset:offset+4] = bytes([i%100, i//100, 73, 255])
        if case.name == 'mixed-5001':
            # Put all alpha classes in this small image, away from vector cells.
            pixels = rgba_pattern(64, 64)
            source = case.source('source.png', png(64, 64, pixels))
            imported = case.call('import', 'asset.import', source_path=source)
            if imported:
                doc['assets'] = {'image': imported['asset']}
                doc['items'].append(dict(id='image', transform=[1, 0, 0, 1, 200, 100],
                    content=dict(type='image', asset_id='image', width=64, height=64)))
                for y in range(64):
                    offset = ((100+y)*1024+200)*4
                    expected[offset:offset+64*4] = pixels[y*64*4:(y+1)*64*4]
            else:
                doc = None
        case.publish('scene', doc, 'png', lambda p: check_png(p, 1024, 1024, expected))
    elif case.name == 'print-page':
        doc = document('print', 'vector', 2480, 3508, resolution_ppi=300,
                       items=[rectangle('ink', 100, 100, 200, 200)])
        case.publish('page', doc, 'pdf', check_pdf)
        expected = bytearray(2480*3508*4)
        for y in range(100, 300):
            offset = (y*2480+100)*4
            expected[offset:offset+200*4] = COLOR*200
        case.publish('preview', doc, 'png', lambda p: check_png(p, 2480, 3508, expected))
    else:
        raise ValueError('Unknown benchmark case')


def run_case(case):
    try:
        _run_case(case)
    except Exception as error:
        # A broken harness/oracle must remain a failed attempted workload, not
        # disappear from the denominator or prevent other cases being measured.
        case.checks.append(dict(name='harness', status='fail',
                                error=f'{type(error).__name__}: {error}'))
    return case.finish()


def statistics_of(values):
    if not values:
        return None
    return dict(min=min(values), median=statistics.median(values), max=max(values),
                population_stddev=statistics.pstdev(values))


def aggregate(rows):
    results = []
    for name in CASES:
        group = [row for row in rows if row['case'] == name]
        if not group:
            continue
        successes = [row for row in group if row['success']]
        results.append(dict(case=name, attempted=len(group), successful=len(successes),
            failed=len(group)-len(successes), success_rate=len(successes)/len(group),
            all_attempt_engine_seconds=statistics_of([row['engine_seconds'] for row in group]),
            successful_engine_seconds=statistics_of([row['engine_seconds'] for row in successes]),
            all_attempt_peak_commit_bytes=statistics_of([row['peak_commit_bytes'] for row in group
                                                         if row['peak_commit_bytes'] is not None]),
            successful_peak_commit_bytes=statistics_of([row['peak_commit_bytes'] for row in successes
                                                        if row['peak_commit_bytes'] is not None]),
            response_bytes=statistics_of([row['response_bytes'] for row in group])))
    return results


def candidate_identity():
    # Include generators and imported oracles, not just engine source. Ignored
    # application research, artifacts and package caches never enter this list.
    names = subprocess.check_output(['git', 'ls-files', '--cached', '--others',
                                    '--exclude-standard', '-z'], cwd=ROOT).decode().split('\0')
    return {name: sha((ROOT/name).read_bytes()) for name in sorted(set(names)) if name}


def release_build(output):
    command = ['cargo', 'build', '--locked', '--release', '--message-format=json']
    start = time.perf_counter()
    build = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=1200)
    save(output/'build.stdout.jsonl', build.stdout)
    save(output/'build.stderr.txt', build.stderr)
    if build.returncode:
        raise RuntimeError('Release build failed; retained its complete logs')
    artifacts = [json.loads(line) for line in build.stdout.splitlines()]
    binaries = [value for value in artifacts if value.get('reason') == 'compiler-artifact'
                and value.get('target', {}).get('name') == 'inkbolt'
                and 'bin' in value.get('target', {}).get('kind', []) and value.get('executable')]
    if len(binaries) != 1 or binaries[0]['profile']['opt_level'] == '0':
        raise RuntimeError('Expected exactly one optimized Inkbolt binary')
    executable = Path(binaries[0]['executable']).resolve(strict=True)
    return executable, dict(command=command, seconds=time.perf_counter()-start,
                            artifact=binaries[0], executable_sha256=sha(executable.read_bytes()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', required=True, type=Path,
                        help='New directory outside the repository; parent must exist')
    parser.add_argument('--repetitions', type=int, default=5, choices=range(1, 11))
    parser.add_argument('--case', action='append', choices=CASES, dest='cases')
    parser.add_argument('--conditions', required=True, help='Describe machine load and other measurement conditions')
    args = parser.parse_args()
    if sys.flags.optimize:
        parser.error('Correctness oracles require Python assertions; do not use -O')
    output = args.output_root.resolve()
    if output.is_relative_to(ROOT.resolve()) or not output.parent.is_dir() or output.exists():
        parser.error('Use a new external output directory under an existing parent')
    output.mkdir()
    candidates = candidate_identity()
    source = source_identity()
    executable, build = release_build(output)
    rows = []
    cases = tuple(dict.fromkeys(args.cases or CASES))
    for repetition in range(args.repetitions):
        # Rotate order deterministically. Each trial uses fresh process/workspace;
        # OS disk/page caches are not flushed and no cold-cache claim is made.
        offset = repetition % len(cases)
        for name in cases[offset:] + cases[:offset]:
            case = Case(executable, output/f'{repetition+1:02d}-{name}', name, repetition+1)
            row = run_case(case)
            rows.append(row)
            print(json.dumps(dict(case=name, repetition=repetition+1, success=row['success'],
                                  seconds=row['engine_seconds'], peak_commit=row['peak_commit_bytes'])), flush=True)
    unchanged = candidates == candidate_identity()
    report = dict(schema_version=1, suite=SUITE_VERSION, model_trials=False,
        full_readiness_benchmark=False, selected_cases=list(cases), repetitions=args.repetitions,
        source_sha256=source, source_unchanged=source == source_identity(),
        candidate_files=candidates, candidate_files_unchanged=unchanged, build=build,
        executable_unchanged=sha(executable.read_bytes()) == build['executable_sha256'],
        git_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(),
        git_status=subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT).decode(),
        toolchain=subprocess.check_output(['rustc', '--version']).decode().strip(),
        environment=dict(system=platform.system(), release=platform.release(), version=platform.version(),
                         machine=platform.machine(), pointer_bits=struct.calcsize('P')*8,
                         processor=os.environ.get('PROCESSOR_IDENTIFIER'),
                         logical_cpus=os.cpu_count(), python=sys.version),
        conditions=args.conditions, rows=rows, aggregates=aggregate(rows),
        timing='Synchronous CLI process startup, JSON transfer, execution and exit; excludes fixture generation, oracle and report work',
        memory='Max of per-command Windows lifetime working-set/commit peaks; excludes driver and no child processes are started',
        cache_conditions='Fresh workspace and process per case/call; OS caches may be warm, no application cache reuse across cases',
        token_usage=None, model_calls=None, agent_time=None,
        latency_memory_gates='Not established; failed workloads cannot set successful-task budgets',
        outcome='baseline_recorded_with_failures' if any(not row['success'] for row in rows) else 'all_selected_workloads_passed')
    report['valid_inputs'] = unchanged and report['source_unchanged'] and report['executable_unchanged']
    if not report['valid_inputs']:
        report['outcome'] = 'invalid_inputs_changed'
    save_json(output/'report.json', report)
    if not report['valid_inputs']:
        raise RuntimeError('Measurement inputs changed; retained report is invalid')
    print(str(output/'report.json'))
    return 2 if any(not row['success'] for row in rows) else 0


if __name__ == '__main__':
    sys.exit(main())
