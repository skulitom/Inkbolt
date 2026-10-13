"""B13 original transparent-screen solve and independent delivery checks."""
import copy
from functools import lru_cache
from pathlib import Path

from benchmark_diagram import delivered
from benchmark_graphics import pixels,png_check,rectangle,store,source_snapshot
from benchmark_runtime import require,strict_json
from sequence_fixtures import chunks
from workload_cases import save,save_json,sha

PROMPT=Path(__file__).with_name('benchmark_prompts')/'B13.md'
PREVIEW_FILES={'transparent-pixels':'screen.png'}
NOTE='original private source note'


def fixture(case):
    """Creation task: the shared prompt is the only immutable input."""


def source_document(preset,identity='graphic',board=None):
    doc=copy.deepcopy(preset['document']);board=board or preset['content_parent_id']
    doc['items'][0]['id']=board
    item=rectangle(identity,10,20,200,100,[20,80,150,128]);item['parent']=board
    doc['items'].append(item);doc['metadata']=dict(private={'note':NOTE})
    return doc


def delivery_identity(raw):
    return dict(file='screen.png',mode='create_only',sha256=sha(raw),collision='output_exists')


def solve(case):
    preset=case.call('preset','preset.create',id='screen',version=1,preset=dict(type='screen',size='presentation_hd',
        kind='vector',background=dict(type='transparent')))
    doc=source_document(preset);saved=store(case,doc)
    output=preset['delivery']|dict(file_name='screen.png',artboard_id=doc['items'][0]['id'])
    ready=case.call('preflight','document.preflight',document=saved,output=output)
    require(ready['ready'] and not (case.root/'screen.png').exists(),'Preflight must be ready without creating output')
    result=case.call('deliver','document.publish',document=saved,output=output)
    raw=delivered(case,'screen.png')
    require(result['sha256']==ready['prepared_output']['sha256']==sha(raw),'Prepared and delivered output differ')
    source_snapshot(case,saved)
    case.call('collision','document.publish',document=saved,output=output,expected_error='OUTPUT_EXISTS')
    require(delivered(case,'screen.png')==raw,'Duplicate publication changed the first delivery')
    save_json(case.root/'delivery.json',delivery_identity(raw))


@lru_cache(maxsize=1)
def expected_picture():
    return pixels(1920,1080,[(10,20,200,100,[20,80,150,128])])


def screen_color(raw):
    require(raw.startswith(b'\x89PNG\r\n\x1a\n'),'Expected a PNG screen delivery')
    records=chunks(raw);srgb=[data for kind,data in records if kind==b'sRGB']
    require(len(srgb)==1 and len(srgb[0])==1 and srgb[0][0]<=3,'Expected exactly one valid sRGB declaration')
    require(not any(kind in (b'iCCP',b'tEXt',b'zTXt',b'iTXt',b'eXIf',b'acTL',b'fcTL',b'fdAT') for kind,_ in records),
            'Screen delivery must strip profiles and descriptive/private records')


def contains_source_note(value):
    """The prompt fixes the note's text, not its author-chosen metadata keys."""
    if isinstance(value,dict):return any(contains_source_note(v) for v in value.values())
    if isinstance(value,list):return any(contains_source_note(v) for v in value)
    return value==NOTE


def judge(case):
    raw=delivered(case,'screen.png');source=delivered(case,'editable.json');actual=strict_json(source)
    reopened=case.call('judge-reopen','document.validate',document=dict(file_path='editable.json',sha256=sha(source)))
    preset=case.call('judge-preset','preset.create',id=actual['id'],version=1,preset=dict(type='screen',size='presentation_hd',
        kind='vector',background=dict(type='transparent')))
    require(len(actual['items'])==2,'Expected an artboard and one editable rectangle')
    expected=source_document(preset,actual['items'][1]['id'],actual['items'][0]['id']);expected['revision']=actual['revision']
    expected['items'][0]['name']=actual['items'][0].get('name')
    expected['metadata']=actual.get('metadata')
    normalized=case.call('judge-template','document.validate',document=expected)
    require(case.check('editable-source',lambda:require(actual==normalized==reopened and contains_source_note(actual.get('metadata')),
        'Editable geometry, private note or screen document controls changed')),'The editable screen source was not admitted')
    directory=getattr(case,'judge_root',case.root)
    target=directory/'judge-screen.png';protected=directory/'judge-protected.png'
    require(not target.exists() and not protected.exists(),'Screen judge outputs must be new')
    output=preset['delivery']|dict(file_name=target.name,output_root=str(directory.resolve()),artboard_id=actual['items'][0]['id'])
    ready=case.call('judge-preflight','document.preflight',document=reopened,output=output,judge_workspace=directory)
    require(ready['ready'] and not target.exists(),'Fresh preflight changed output or was not ready')
    result=case.call('judge-deliver','document.publish',document=reopened,output=output,judge_workspace=directory);fresh=target.read_bytes()
    def picture():
        for data in (raw,fresh):png_check(data,1920,1080,expected_picture())
    case.check('transparent-pixels',picture)
    def color():
        for data in (raw,fresh):screen_color(data)
        require(result['sha256']==ready['prepared_output']['sha256']==sha(fresh),'Fresh preflight/publication identity differs')
    case.check('screen-color',color)
    def collision():
        require(strict_json(delivered(case,'delivery.json'))==delivery_identity(raw),'Delivery identity or create-only contract changed')
        save(protected,raw)
        case.call('judge-collision','document.publish',document=reopened,output=output|dict(file_name=protected.name),
                  expected_error='OUTPUT_EXISTS',judge_workspace=directory)
        require(protected.read_bytes()==raw==delivered(case,'screen.png'),'A duplicate publication overwrote the protected delivery')
    case.check('no-overwrite',collision)


def transparent_delivery(case):
    fixture(case);case.begin(PROMPT.read_text(encoding='utf-8'));solve(case);case.begin_judging();judge(case)
    if any(c['name']=='transparent-pixels' and c['status']=='pass' for c in case.checks):case.verified_preview(delivered(case,'screen.png'))
