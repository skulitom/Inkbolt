"""B18 harness-owned stale proposal and independent two-writer recovery judge."""
import base64
import copy
import json
from pathlib import Path

from benchmark_diagram import delivered
from benchmark_graphics import BLUE,GREEN,two_items,pixels,png_check,store,apply,source_snapshot
from benchmark_resources import reported_review
from benchmark_runtime import require,strict_json
from workload_cases import save,save_json,sha

PROMPT=Path(__file__).with_name('benchmark_prompts')/'B18.md'
PREVIEW_FILES={'conflict-pixels':'preview.png'}
SETUP_FILES=('conflict-setup.json','conflict.sqlite3')
SETUP_COMMANDS=3
STORE='.inkbolt/sessions/'+sha(b'work')+'.sqlite3'


def target_action():
    return dict(type='edit',operations=[dict(op='transform',id='target',matrix=[1,0,0,1,3,0],space='world')])


def fixture(case):case.seed(two_items())


def prepare(case):
    saved=store(case,dict(file_path='source.json',sha256=sha(delivered(case,'source.json'))))
    old=case.call('review-old','session.dry_run',session_id='work',request_id='move-target',expected_revision=0,action=target_action())
    other=apply(case,'other-writer',0,[dict(op='transform',id='other',matrix=[1,0,0,1,-2,0],space='world')])
    save_json(case.root/'stale-request.json',dict(command='session.apply_proposal',proposal=old['proposal'],action=target_action(),response_mode='compact'))
    # All commands have returned and closed their database before this copy.
    # Keep the pre-client state: probing the final head would test request-ID
    # reuse instead of the original revision conflict.
    raw=delivered(case,STORE);require(len(raw)<=1024*1024,'Conflict fixture store exceeds its evidence bound')
    evidence=getattr(case,'judge_root',case.root)
    save(evidence/SETUP_FILES[1],raw)
    save_json(evidence/SETUP_FILES[0],dict(schema_version=1,creation_ref=saved,review=old,other=other,
        store_sha256=sha(raw),stale_request_sha256=sha(delivered(case,'stale-request.json'))))


def prepare_external(case):
    case.phase='setup'
    try:prepare(case)
    finally:case.phase='task'


def solve(case):
    request=strict_json(delivered(case,'stale-request.json'));arguments=copy.deepcopy(request);command=arguments.pop('command')
    rejected=case.call('stale',command,expected_error='REVISION_CONFLICT',**arguments)
    save_json(case.root/'rejected.json',dict(request=request,error=rejected))
    reviewed=case.call('review-current','session.dry_run',session_id='work',request_id='move-target',expected_revision=1,action=target_action())
    save_json(case.root/'review.json',reviewed)
    case.call('apply-reviewed','session.apply_proposal',proposal=reviewed['proposal'],action=target_action(),response_mode='compact')
    source_snapshot(case,dict(session_id='work',revision=2))
    for name,revision in (('preview',2),('historical',0)):
        result=case.call(name,'document.preview',document=dict(session_id='work',revision=revision),options={},preview=True)
        save(case.root/(name+'.png'),base64.b64decode(result['artifact']['data'],validate=True))
    case.call('verify-history','session.verify',session_id='work')


def read_setup(case):
    evidence=getattr(case,'judge_root',case.root);raw={}
    for name in SETUP_FILES:
        path=evidence/name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size<=1024*1024,'Missing, linked or oversized conflict setup')
        raw[name]=path.read_bytes()
    setup=strict_json(raw[SETUP_FILES[0]])
    require(set(setup)=={'schema_version','creation_ref','review','other','store_sha256','stale_request_sha256'} and setup['schema_version']==1 and
        setup['store_sha256']==sha(raw[SETUP_FILES[1]]) and setup['stale_request_sha256']==sha(delivered(case,'stale-request.json')),
        'Conflict setup or supplied request identity changed')
    return setup,raw[SETUP_FILES[1]]


def action_fingerprint(revision):
    # The public typed action normalizes default label/anchor and f64 values.
    action=target_action();action['label']='';action['operations'][0]['anchor']=None
    action['operations'][0]['matrix']=[float(v) for v in action['operations'][0]['matrix']]
    return sha(json.dumps(dict(expected_revision=revision,action=action),sort_keys=True,separators=(',',':')).encode())


def judge(case):
    setup,raw=read_setup(case);request=strict_json(delivered(case,'stale-request.json'))
    rejected=strict_json(delivered(case,'rejected.json'))
    original=case.call('judge-source','document.validate',document=dict(file_path='source.json',sha256=case.sources['source.json']))
    final=case.call('judge-reopen','document.validate',document=dict(file_path='editable.json',sha256=sha(delivered(case,'editable.json'))))
    receipts={name:case.call('judge-receipt-'+name,'session.receipt',session_id='work',request_id=name) for name in ('create','other-writer','move-target')}
    current=case.call('judge-current','session.read',session_id='work')
    history=case.call('judge-history','session.verify',session_id='work')
    # Reproduce the stale application against the captured pre-client state in
    # a private store, never by rewinding or modifying the delivered session.
    directory=getattr(case,'judge_root',case.root)/'judge-conflict';directory.mkdir()
    destination=directory/STORE;destination.parent.mkdir(parents=True);save(destination,raw)
    before=case.call('judge-before','session.read',session_id='work',judge_workspace=directory)
    error=case.call('judge-stale','session.apply_proposal',proposal=setup['review']['proposal'],action=target_action(),response_mode='compact',
        expected_error='REVISION_CONFLICT',judge_workspace=directory)
    after=case.call('judge-after','session.read',session_id='work',judge_workspace=directory)
    probe_history=case.call('judge-probe-history','session.verify',session_id='work',judge_workspace=directory)
    other=copy.deepcopy(original);other['revision']=1;other['items'][1]['transform']=[1,0,0,1,-2,0]
    wanted=copy.deepcopy(other);wanted['revision']=2;wanted['items'][0]['transform']=[1,0,0,1,3,0]
    def stale():
        old=setup['review'];proposal=old['proposal']
        require(request==dict(command='session.apply_proposal',proposal=proposal,action=target_action(),response_mode='compact') and
            set(rejected)=={'request','error'} and rejected['request']==request and rejected['error']==error and error['code']=='REVISION_CONFLICT',
            'The retained rejection does not match the supplied stale request and fresh probe')
        require(old['dry_run'] is True and old['committed'] is False and old['source_changed'] is False and
            old['base_ref']==setup['creation_ref'] and proposal['expected_revision']==0 and proposal['session_id']=='work' and
            proposal['request_id']=='move-target' and proposal['request_fingerprint']==action_fingerprint(0) and
            proposal['base_state_sha256']==receipts['create']['receipt']['state_sha256'] and
            proposal['result_state_sha256']!=before['state_sha256'],'Setup did not retain a proposal from before the other writer')
        require(before==after and before['document']==other and before['revision']==1 and probe_history['valid'] and probe_history['revision']==1,
            'Rejected stale proposal changed the captured other-writer state')
    case.check('stale-rejected',stale)
    def intents():
        reviewed=reported_review(delivered(case,'review.json'))
        # document.validate has reopened defaults and retained the saved
        # revision; equivalent JSON need not serialize every default field.
        require(receipts['create']['document']==original and receipts['other-writer']['document']==other==before['document'] and
            receipts['move-target']['document']==wanted==current['document']==final,
            'Recovery lost an edit or changed source geometry, appearance or unrelated controls')
        require(reviewed['proposal']==dict(version=1,session_id='work',request_id='move-target',expected_revision=1,
            request_fingerprint=action_fingerprint(1),base_state_sha256=receipts['other-writer']['receipt']['state_sha256'],
            result_state_sha256=receipts['move-target']['receipt']['state_sha256']) and
            reviewed['predicted_receipt']==receipts['move-target']['receipt'] and reviewed['dry_run'] is True and
            reviewed['committed'] is False and reviewed['source_changed'] is False and reviewed['base_ref']['session_id']=='work' and
            reviewed['base_ref']['revision']==1 and reviewed['proposed_resources']==receipts['move-target']['resources'],
            'Replacement review differs from the intended action, base state or committed edit receipt')
    case.check('both-intents-preserved',intents)
    for name,doc,rectangles,check in (
        ('preview',wanted,[(5,4,8,8,BLUE),(20,4,8,8,GREEN)],'conflict-pixels'),
        ('historical',receipts['create']['document'],[(2,4,8,8,BLUE),(22,4,8,8,GREEN)],'historical-pixels')):
        fresh=case.call('judge-'+name,'document.preview',document=doc,options={},preview=True)
        def picture():
            for data in (delivered(case,name+'.png'),base64.b64decode(fresh['artifact']['data'],validate=True)):
                png_check(data,32,16,pixels(32,16,rectangles))
        case.check(check,picture)
    def valid_history():
        compact=copy.deepcopy(setup['other']);summary=copy.deepcopy(receipts['other-writer']['receipt']);summary['change_count']=len(summary.pop('changes'))
        require(compact['receipt_summary']==summary and compact['replayed'] is False and compact['current_revision']==1 and
            compact['resources']==receipts['other-writer']['resources'],'Harness writer differs from the retained commit')
        require(history['valid'] and history['revision']==current['revision']==current['current_revision']==2 and
            receipts['create']['receipt']['revision']==0 and receipts['other-writer']['receipt']['from_revision']==0 and
            receipts['move-target']['receipt']['from_revision']==1 and
            current['state_sha256']==receipts['move-target']['receipt']['state_sha256'] and
            receipts['create']['resources']==receipts['other-writer']['resources']==receipts['move-target']['resources']==current['resources'],
            'History has extra revisions, changed resources or a different final state')
    case.check('history-valid',valid_history)


def conflicting_writers(case):
    fixture(case);case.begin(PROMPT.read_text(encoding='utf-8'));prepare(case);solve(case);case.begin_judging();judge(case)
    if any(c['name']=='conflict-pixels' and c['status']=='pass' for c in case.checks):case.verified_preview(delivered(case,'preview.png'))
