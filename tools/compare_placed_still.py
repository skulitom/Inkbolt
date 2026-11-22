"""Compare editing and reviewing the same placed still through two native JSON CLIs."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import platform
import struct
import subprocess
import time

from benchmark_runtime import Trial, require
from workload_cases import ROOT, png, save, save_json, sha


WIDTH, HEIGHT = 32, 24
BADGE_WIDTH, BADGE_HEIGHT = 6, 4
BEFORE, AFTER = (3, 5), (17, 12)
ZERO = dict(num=0, den=1)
FRAME = dict(num=1, den=25)


def file_sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def artwork():
    paper = bytes(channel for y in range(HEIGHT) for x in range(WIDTH)
                  for channel in (25 + x * 3, 45 + y * 5, 75 + (x + 2 * y) % 100, 255))
    badge = bytes(channel for y in range(BADGE_HEIGHT) for x in range(BADGE_WIDTH)
                  for channel in (201 - x * 11, 83 + y * 23, 31 + x + y, 0 if (x + 2 * y) % 5 == 0 else 255))
    return paper, badge


def expected(paper, badge, position):
    image = bytearray(paper)
    for y in range(BADGE_HEIGHT):
        for x in range(BADGE_WIDTH):
            src = 4 * (y * BADGE_WIDTH + x)
            dst = 4 * ((position[1] + y) * WIDTH + position[0] + x)
            if badge[src + 3]:
                image[dst:dst + 4] = badge[src:src + 4]
    return bytes(image)


def inkbolt(case, observe):
    def item(name, width, height, position):
        return dict(id=name, transform=[1, 0, 0, 1, *position],
                    content=dict(type='image', asset_id=name, width=width, height=height))

    assets = {name: case.call('import-' + name, 'asset.import', source_path=name + '.png')['asset']
              for name in ('paper', 'badge')}
    document = dict(schema_version=2, id='sheet', kind='vector', width=WIDTH, height=HEIGHT, color_space='srgb',
                    assets=assets, items=[item('paper', WIDTH, HEIGHT, (0, 0)),
                                          item('badge', BADGE_WIDTH, BADGE_HEIGHT, BEFORE)])
    session = dict(session_id='placement')
    initial = case.call('create', 'session.create', **session, request_id='create', document=document, response_mode='compact')

    def preview(step, revision):
        result = case.call('preview-' + step, 'document.preview', document=dict(**session, revision=revision))
        save(case.root / (step + '.png'), base64.b64decode(result['artifact']['data'], validate=True))
        observe(step)

    first = initial['current_revision']
    preview('before', first)
    moved = case.call('move', 'session.apply', **session, expected_revision=first, request_id='move', response_mode='compact',
                      action=dict(type='edit', operations=[dict(op='transform', id='badge', matrix=[1, 0, 0, 1, *AFTER])]))
    preview('after', moved['current_revision'])
    preview('historical', first)


def cutbolt(case, observe):
    def layer(name, width, height, position):
        filename = name + '.png'
        image = dict(path=filename, sha256=case.sources[filename], bytes=(case.root / filename).stat().st_size)
        return dict(id=name, canvas=[width, height], start=ZERO, duration=FRAME, timing='strict', end='hold_last',
                    frames=[dict(image=image, hold=FRAME, offset=[0, 0], anchor=[0, 0])],
                    transform=dict(position=position, crop=[0, 0, width, height], scale=1, quarter_turns=0, opacity=255))

    def edit(action, **fields):
        return dict(op='tracks.edit', edit=dict(op=action, **fields))

    session = dict(project_id='placement')
    created = case.call('create', 'session.create', id='placement', width=WIDTH, height=HEIGHT,
                        frame_rate=dict(num=25, den=1), request_id='create')
    revision = created['revision']

    def preview(step, saved_revision):
        case.call('preview-' + step, 'preview.frame', project=dict(**session, revision=saved_revision),
                  output=step + '.png', time=ZERO)
        observe(step)

    for step, position in [('before', BEFORE), ('after', AFTER)]:
        scene = dict(schema_version=1, id='sheet', width=WIDTH, height=HEIGHT, output_scale=1, duration=FRAME,
                     background=[0, 0, 0], color='srgb_straight_encoded', audio=None,
                     layers=[layer('paper', WIDTH, HEIGHT, (0, 0)), layer('badge', BADGE_WIDTH, BADGE_HEIGHT, position)])
        # Keep the editable recipe and compiled media for both timeline revisions.
        recipe = step + '.scene.json'
        case.source(recipe, json.dumps(scene, separators=(',', ':')).encode())
        movie = case.root / (step + '.mkv')
        compiled = case.call('compile-' + step, 'scene.render', scene=dict(file=recipe), output=movie.name, detail='summary')
        asset = dict(compiled['asset'], id='graphic-' + step, path=movie.name)
        case.sources[movie.name] = sha(movie.read_bytes())
        clip = dict(id='graphic', asset_id=asset['id'], start=ZERO, source_in=ZERO, duration=FRAME)
        operations = [dict(op='media.add', asset=asset)]
        if step == 'before':
            operations.extend([edit('create', duration=FRAME), edit('add', track=dict(
                id='sheet', kind='video', enabled=True, locked=False, composite='alpha_over', clips=[]))])
        else:
            operations.append(edit('remove', clip_ids=['graphic'], links='reject_partial'))
        operations.append(edit('place', track_id='sheet', clip=clip, collision='reject'))
        saved = case.call('install-' + step, 'session.apply', **session, expected_revision=revision,
                          request_id='install-' + step, operations=operations)
        revision = saved['revision']
        if step == 'before':
            first = revision
        preview(step, revision)
    preview('historical', first)


def run_trial(case, engine, ffmpeg, report):
    paper, badge = artwork()
    case.source('paper.png', png(WIDTH, HEIGHT, paper))
    case.source('badge.png', png(BADGE_WIDTH, BADGE_HEIGHT, badge))
    previews = report['previews'] = {}
    report['calls'] = case.calls
    case.begin('Place the badge at (3,5), move it to (17,12), and review the original saved revision.')

    def observe(step):
        raw = (case.root / (step + '.png')).read_bytes()
        previews[step] = dict(png_sha256=sha(raw), bytes=len(raw),
                              observed_seconds=time.perf_counter() - case.agent_started)

    engine(case, observe)
    case.begin_judging()
    require(previews.keys() == {'before', 'after', 'historical'}, 'Missing preview')
    for step, position in [('before', BEFORE), ('after', AFTER), ('historical', BEFORE)]:
        path = case.root / (step + '.png')
        raw = path.read_bytes()
        require(sha(raw) == previews[step]['png_sha256'] and raw[:16] == b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR'
                and raw[16:24] == struct.pack('>II', WIDTH, HEIGHT), 'Changed preview or incorrect PNG dimensions')
        rgba = subprocess.run([str(ffmpeg), '-nostdin', '-v', 'error', '-i', str(path), '-frames:v', '1', '-f', 'rawvideo',
                               '-pix_fmt', 'rgba', 'pipe:1'], check=True, capture_output=True, timeout=30).stdout
        require(rgba == expected(paper, badge, position), 'Preview pixels differ at step ' + step)
        previews[step]['rgba_sha256'] = sha(rgba)
    require(all(sha((case.root / name).read_bytes()) == digest for name, digest in case.sources.items()),
            'Source or retained delivery changed')
    report.update(sources=case.sources, authored_scene_bytes=sum(path.stat().st_size for path in case.root.glob('*.scene.json')),
                  solve_seconds=case.solve_seconds,
                  first_verified_preview_seconds=previews['before']['observed_seconds'],
                  request_bytes=sum(call['request_bytes'] for call in case.calls),
                  response_bytes=sum(call['response_bytes'] for call in case.calls), status='passed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('inkbolt', 'cutbolt', 'ffmpeg', 'ffprobe', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    paths = {name: getattr(args, name).resolve(strict=True) for name in ('inkbolt', 'cutbolt', 'ffmpeg', 'ffprobe')}
    root = args.output.resolve()
    if root.is_relative_to(ROOT):
        parser.error('Use a new evidence directory outside the source checkout')
    root.mkdir(parents=True, exist_ok=False)
    os.environ.update(CUTBOLT_FFMPEG=str(paths['ffmpeg']), CUTBOLT_FFPROBE=str(paths['ffprobe']))
    hashes = {name: file_sha(path) for name, path in paths.items()}
    report = dict(schema_version=1, workflow='placed-still-cli-v1', scripted=True, system=platform.platform(),
                  executable_sha256=hashes, runner_sha256=sha(Path(__file__).read_bytes()), trials=[])
    engines = [('inkbolt', inkbolt), ('cutbolt', cutbolt)]
    try:
        for repetition in range(1, 6):
            for name, engine in (engines if repetition % 2 else reversed(engines)):
                row = dict(engine=name, repetition=repetition, status='started')
                report['trials'].append(row)
                case = Trial(paths[name], root / f'{name}-{repetition}', 'placed-still', repetition, 'cli', ())
                try:
                    run_trial(case, engine, paths['ffmpeg'], row)
                except (RuntimeError, ValueError, OSError, KeyError, subprocess.SubprocessError) as error:
                    row.update(status='failed', error=str(error))
    finally:
        report['executables_unchanged'] = all(file_sha(path) == hashes[name] for name, path in paths.items())
        save_json(root / 'report.json', report)
    passed = sum(row['status'] == 'passed' for row in report['trials'])
    print(f'{passed}/10 placed-still trials passed. {root / "report.json"}')
    return 0 if passed == 10 and report['executables_unchanged'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
