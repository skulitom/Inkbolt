"""B01 fixture, versioned prompt, reference solver and delivered-artifact judge."""
import base64
from pathlib import Path

from benchmark_graphics import BLUE, GREEN, pixels, png_check, store, source_snapshot
from benchmark_runtime import require, strict_json
from synthetic_font import geometric_font
from workload_cases import rectangle, save, sha

PROMPT = Path(__file__).with_name('benchmark_prompts')/'B01.md'
FONT_FAMILY = 'Inkbolt Diagram Fixture'
PREVIEW_FILES = {'diagram-pixels':'preview.png'}


def fixture(case):
    case.source('original.ttf', geometric_font(family=FONT_FAMILY))
    case.source('font-license.txt', b'Original Inkbolt synthetic font. Permission to use, modify and redistribute with this notice.')


def solve(case):
    """Reference implementation; its chosen IDs are not judge requirements."""
    font = case.call('font', 'font.import', source_path='original.ttf', license_path='font-license.txt')
    doc = case.call('create', 'document.create', id='diagram', kind='vector', width=128, height=56)
    doc['fonts'] = {'face':font}
    doc['items'] = [rectangle('left', 8, 8, 48, 36, BLUE),
                    rectangle('right', 80, 8, 40, 36, GREEN),
                    rectangle('connector', 56, 25, 24, 2, [80, 80, 80, 255])]
    for ident, text, x in [('label-left', 'AA', 20), ('label-right', 'A', 96)]:
        doc['items'].append(dict(id=ident, transform=[1,0,0,1,x,16], content=dict(type='text', frame=dict(
            text=text, width=32, height=24, style=dict(font_id='face', size=20, fill=[255]*4)))))
    saved = store(case, doc)
    source_snapshot(case, saved)
    preview = case.call('preview', 'document.preview', document=saved, options={}, preview=True)
    save(case.root/'preview.png', base64.b64decode(preview['artifact']['data'], validate=True))


def delivered(case, name):
    path = case.root/name
    require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(case.root.resolve()),
            'Missing or external deliverable: '+name)
    return path.read_bytes()


def expected_picture():
    return pixels(128,56,[(8,8,48,36,BLUE), (80,8,40,36,GREEN), (56,25,24,2,[80,80,80,255]),
        (21,18,8,14,[255]*4), (33,18,8,14,[255]*4), (97,18,8,14,[255]*4)])


def rectangle_corners(item):
    geometry=item['content']['geometry']
    require(geometry['shape']=='rect', 'Expected editable rectangle geometry')
    x,y,w,h=(geometry[key] for key in ('x','y','width','height'))
    a,b,c,d,e,f=item['transform']
    return {(round(a*px+c*py+e,8),round(b*px+d*py+f,8)) for px,py in ((x,y),(x+w,y),(x,y+h),(x+w,y+h))}


def retained_font_store(case):
    """Find the pinned imported font/license pair without assuming the agent's store name."""
    root = case.root.resolve()
    font_hash = case.sources['original.ttf']
    license_hash = case.sources['font-license.txt']
    expected = [(font_hash, (root/'original.ttf').stat().st_size),
                (license_hash, (root/'font-license.txt').stat().st_size)]
    for font in sorted(root.rglob('*.font')):
        if font.name != font_hash+'.font':
            continue
        paths = [font, font.with_name(license_hash+'.license')]
        if any(not path.is_file() or path.is_symlink() or
               not path.resolve().is_relative_to(root) or
               any((root/parent).is_symlink() for parent in path.relative_to(root).parents)
               for path in paths):
            continue
        if all(path.stat().st_size == size and sha(path.read_bytes()) == digest
               for path, (digest, size) in zip(paths, expected)):
            return font.parent.relative_to(root).as_posix()
    require(False, 'Missing intact workspace font store with the pinned font and retained license')


def judge(case):
    """Read deliverables, never the reference solver's locals or chosen IDs."""
    raw = delivered(case, 'editable.json')
    actual = strict_json(raw)

    def structure():
        items = actual['items']
        require(len(items) == 5, 'The diagram must retain five editable objects')
        vectors = [item for item in items if item['content']['type'] == 'vector']
        texts = [item for item in items if item['content']['type'] == 'text']
        require(len(vectors) == 3 and len(texts) == 2, 'Diagram content changed kind')
        for x, y, w, h, color in [(8,8,48,36,BLUE), (80,8,40,36,GREEN), (56,25,24,2,[80,80,80,255])]:
            expected = {(x,y),(x+w,y),(x,y+h),(x+w,y+h)}
            require(sum(rectangle_corners(item) == expected and item['content']['fill'] == color for item in vectors) == 1,
                    'Block geometry or paint changed')
        for text, x in [('AA', 20), ('A', 96)]:
            require(sum(item['content']['frame']['text'] == text and item['transform'] == [1,0,0,1,x,16]
                        for item in texts) == 1, 'Label text or position changed')

    def fonts():
        texts = [item for item in actual['items'] if item['content']['type'] == 'text']
        require(len(texts) == 2, 'Missing editable labels')
        for item in texts:
            frame = item['content']['frame']
            font = actual['fonts'][frame['style']['font_id']]
            require(font['sha256'] == case.sources['original.ttf'] and
                    font['license_sha256'] == case.sources['font-license.txt'], 'Font/license changed')
            require(frame['style']['size'] == 20 and frame['style']['fill'] == [255]*4 and
                    (frame['width'],frame['height']) == (32,24), 'Label style or frame changed')

    case.check('diagram-structure', structure)
    case.check('font-identity', fonts)
    expected = expected_picture()
    preview = delivered(case, 'preview.png')
    reopened = case.call('judge-reopen', 'document.validate',
                        document=dict(file_path='editable.json', sha256=sha(raw)))
    rendered = case.call('judge-render', 'document.preview',
                         document=dict(file_path='editable.json', sha256=sha(raw)),
                         font_root=retained_font_store(case), options={}, preview=True)
    def picture():
        png_check(preview,128,56,expected)
        png_check(base64.b64decode(rendered['artifact']['data'], validate=True),128,56,expected)
    case.check('diagram-pixels', picture)
    case.check('editable-source', lambda: require(reopened == actual, 'Editable document did not reopen exactly'))


def diagram(case):
    fixture(case)
    case.begin(PROMPT.read_text(encoding='utf-8'))
    solve(case)
    case.begin_judging()
    judge(case)
    if any(row['name'] == 'diagram-pixels' and row['status'] == 'pass' for row in case.checks):
        case.verified_preview(delivered(case, 'preview.png'))
