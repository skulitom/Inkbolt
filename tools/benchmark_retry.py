"""B17 harness-owned lost response, recovery solve and independent history judge."""
import base64
import copy
import json
from pathlib import Path
import shutil

from benchmark_diagram import delivered
from benchmark_graphics import BLUE,GREEN,two_items,pixels,png_check,store,source_snapshot
from benchmark_runtime import require,strict_json
from workload_cases import save,save_json,sha

PROMPT=Path(__file__).with_name('benchmark_prompts')/'B17.md'
PREVIEW_FILES={'edited-pixels':'preview.png'}
SETUP_FILES=('lost-response.json',)
SETUP_COMMANDS=2


def edit_request():
    return dict(command='session.apply',session_id='work',request_id='move',expected_revision=0,response_mode='compact',
        action=dict(type='edit',operations=[dict(op='transform',id='target',matrix=[1,0,0,1,3,0],space='world')]))


def fixture(case):
    case.seed(two_items())
    case.source('retry-request.json',json.dumps(edit_request(),separators=(',',':')).encode())


def prepare(case):
    saved=store(case,dict(file_path='source.json',sha256=sha(delivered(case,'source.json'))))
    request=edit_request();command=request.pop('command')
    case.call('lost',command,discard=True,**request)
    # Only the harness sees the injected response. Recovery never reads results
    # or this evidence file; external setup logs live outside the workspace.
    save_json(getattr(case,'judge_root',case.root)/SETUP_FILES[0],dict(schema_version=1,observed=False,
        request=edit_request(),response=case.results['lost']['result'],creation_ref=saved))


def prepare_external(case):
    case.phase='setup'
    try:prepare(case)
    finally:case.phase='task'


def solve(case):
    request=strict_json(delivered(case,'retry-request.json'));command=request.pop('command');attempts={}
    recovered=case.call('recover-receipt','session.receipt',session_id='work',request_id='move',response_mode='compact')
    attempts['recovered']=recovered
    # The external driver records these as retries of the injected request;
    # the reference runtime also validates the exact original request hash.
    for step,revision in (('retry',1),('retry-after-undo',2)):
        result=case.call(step,command,retry_of='lost',**request)
        attempts[step]=dict(request=dict(command=command,**request),result=result)
        if revision==1:
            preview=case.call('preview','document.preview',document=dict(session_id='work',revision=1),options={},preview=True)
            save(case.root/'preview.png',base64.b64decode(preview['artifact']['data'],validate=True))
            case.call('undo','session.apply',session_id='work',request_id='undo',expected_revision=1,
                action=dict(type='undo'),response_mode='compact')
    source_snapshot(case,dict(session_id='work',revision=2))
    case.call('verify-history','session.verify',session_id='work')
    save_json(case.root/'attempts.json',attempts)


def expected_picture():return pixels(32,16,[(5,4,8,8,BLUE),(22,4,8,8,GREEN)])


def without_store_paths(value):
    value=copy.deepcopy(value)
    for key in ('document_ref','receipt_ref'):
        require(isinstance(value[key].pop('session_root'),str),'Missing recorded store root')
    return value


def same_request(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'))==json.dumps(edit_request(),sort_keys=True,separators=(',',':'))


def read_fault(case):
    path=getattr(case,'judge_root',case.root)/SETUP_FILES[0]
    require(path.is_file() and not path.is_symlink() and path.stat().st_size<=64*1024,'Missing or oversized harness response')
    value=strict_json(path.read_bytes())
    require(set(value)=={'schema_version','observed','request','response','creation_ref'} and value['schema_version']==1 and
        value['observed'] is False and same_request(value['request']),'The harness did not retain the intended unobserved request')
    return value


def copy_session(case):
    directory=getattr(case,'judge_root',case.root)/'judge-retry';directory.mkdir()
    source=case.root/'.inkbolt/sessions'
    require(source.is_dir() and not source.is_symlink() and not source.parent.is_symlink() and
        source.resolve().is_relative_to(case.root.resolve()),'Missing or linked captured session store')
    files=list(source.rglob('*'))
    require(all(not p.is_symlink() and p.resolve().is_relative_to(source.resolve()) and (p.is_file() or p.is_dir()) for p in files),
        'Session probe cannot follow linked or nonregular files')
    require(len(files)<=128 and sum(p.stat().st_size for p in files if p.is_file())<=4*1024*1024,'Session probe exceeds its small-fixture bound')
    shutil.copytree(source,directory/'.inkbolt/sessions')
    return directory


def judge(case):
    fault=read_fault(case);attempts=strict_json(delivered(case,'attempts.json'))
    require(set(attempts)=={'recovered','retry','retry-after-undo'},'Missing or extra recovery attempts')
    original=case.call('judge-template','document.validate',document=dict(file_path='source.json',sha256=case.sources['source.json']))
    edited=case.call('judge-edited','document.validate',document=dict(session_id='work',revision=1))
    final=case.call('judge-reopen','document.validate',document=dict(file_path='editable.json',sha256=sha(delivered(case,'editable.json'))))
    receipts={name:case.call('judge-receipt-'+name,'session.receipt',session_id='work',request_id=name) for name in ('create','move','undo')}
    current=case.call('judge-current','session.read',session_id='work')
    history=case.call('judge-history','session.verify',session_id='work')
    def receipt():
        lost=fault['response'];durable=receipts['move'];summary=copy.deepcopy(durable['receipt']);summary['change_count']=len(summary.pop('changes'))
        require(lost['replayed'] is False and lost['current_revision']==lost['current_state_id']==1 and lost['session_id']=='work' and
            lost['receipt_summary']==summary and lost['document_ref']['session_id']=='work' and lost['document_ref']['revision']==1 and
            lost['receipt_ref']['session_id']=='work' and lost['receipt_ref']['request_id']=='move' and lost['resources']==durable['resources'],
            'Injected response differs from the durable original receipt')
        require(fault['creation_ref']['session_id']=='work' and fault['creation_ref']['revision']==0 and
            receipts['create']['document']==original and receipts['create']['receipt']['revision']==0,'Injected creation differs from the original source')
        expected=without_store_paths(lost);expected['replayed']=True
        require(without_store_paths(attempts['recovered'])==expected,'Recovered receipt differs from the original response')
    case.check('original-receipt',receipt)
    def retry():
        expected=without_store_paths(fault['response']);expected['replayed']=True
        for key,revision,state in (('retry',1,1),('retry-after-undo',2,0)):
            row=attempts[key];expected['current_revision']=revision;expected['current_state_id']=state
            require(set(row)=={'request','result'} and same_request(row['request']) and without_store_paths(row['result'])==expected,
                'A retry changed the request, receipt or current revision')
        wanted=copy.deepcopy(original);wanted['revision']=1;wanted['items'][0]['transform']=[1,0,0,1,3,0]
        require(edited==wanted==receipts['move']['document'],'The original edit was duplicated or changed unrelated artwork')
    case.check('retry-idempotent',retry)
    preview=case.call('judge-preview','document.preview',document=edited,options={},preview=True)
    def picture():
        for raw in (delivered(case,'preview.png'),base64.b64decode(preview['artifact']['data'],validate=True)):
            png_check(raw,32,16,expected_picture())
    case.check('edited-pixels',picture)
    directory=copy_session(case)
    fresh=case.call('judge-retry','session.apply',judge_workspace=directory,**{k:v for k,v in edit_request().items() if k!='command'})
    probe=case.call('judge-retry-current','session.read',session_id='work',judge_workspace=directory)
    verified=case.call('judge-retry-history','session.verify',session_id='work',judge_workspace=directory)
    def undone():
        wanted=copy.deepcopy(original);wanted['revision']=2
        # Compare reopened semantics, including the required revision, rather
        # than requiring every optional default to be serialized in the file.
        require(final==wanted==current['document']==receipts['undo']['document']==probe['document'],
            'Undo or a historical retry changed the restored source')
        require(fresh['replayed'] is True and fresh['current_revision']==probe['revision']==2 and fresh['receipt_summary']==fault['response']['receipt_summary'] and
            fresh['document_ref']['revision']==1 and verified['valid'] and verified['revision']==2,'Fresh replay of the captured session reapplied the old edit')
    case.check('undo-preserved',undone)
    case.check('history-valid',lambda:require(history['valid'] and history['revision']==current['revision']==current['current_revision']==2 and
        receipts['undo']['receipt']['action']=='undo' and receipts['undo']['receipt']['from_revision']==1 and
        receipts['move']['receipt']['action']=='edit' and receipts['move']['receipt']['from_revision']==0 and
        receipts['create']['resources']==receipts['move']['resources']==receipts['undo']['resources']==current['resources'] and
        current['state_sha256']==receipts['undo']['receipt']['state_sha256']==receipts['create']['receipt']['state_sha256'],
        'History contains a duplicate edit, changed resources or a different undo state'))


def lost_response(case):
    fixture(case);case.begin(PROMPT.read_text(encoding='utf-8'));prepare(case);solve(case);case.begin_judging();judge(case)
    if any(c['name']=='edited-pixels' and c['status']=='pass' for c in case.checks):case.verified_preview(delivered(case,'preview.png'))
