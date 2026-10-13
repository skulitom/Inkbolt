"""B19 original recovery fixture, controlled solve and independent durable judge."""
import base64
import copy
from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import time

from benchmark_diagram import delivered
from benchmark_graphics import GREEN,ORANGE,document,rectangle,store,apply,source_snapshot,ref,png_check
from benchmark_runtime import require,strict_json
from test_images_cli import png,canonical
from workload_cases import save,save_json,sha

PROMPT=Path(__file__).with_name('benchmark_prompts')/'B19.md'
PREVIEW_FILES={'review-pixels':'preview.png','recovered-pixels':'recovered.png'}
WIDTH=HEIGHT=1024


def original_pixels():
    colors=hashlib.shake_256(b'Inkbolt original recovery texture v1').digest(WIDTH*HEIGHT*3)
    original=bytearray(WIDTH*HEIGHT*4)
    for channel in range(3):original[channel::4]=colors[channel::3]
    original[3::4]=b'\xff'*(WIDTH*HEIGHT)
    return bytes(original)


def expected_pixels():
    expected=bytearray(original_pixels())
    for y in range(40,60):expected[(y*WIDTH+32)*4:(y*WIDTH+56)*4]=bytes(GREEN)*24
    return bytes(expected)


def fixture(case):case.source('original.png',png(WIDTH,HEIGHT,original_pixels()))


def authored(asset):
    return document('recovery','vector',WIDTH,HEIGHT,assets=dict(photo=asset),items=[
        dict(id='image',content=dict(type='image',asset_id='photo',width=WIDTH,height=HEIGHT)),
        rectangle('badge',32,40,24,20,GREEN)])


def terminal(case,request_id,expected):
    deadline=time.monotonic()+25
    for index in range(30):
        require(time.monotonic()<deadline,'Background output exceeded its observation deadline')
        result=case.call(f'{request_id}-wait-{index}','job.wait',request_id=request_id,wait_ms=1000)
        if result['state'] not in ('queued','running'):
            require(result['state']==expected,'Unexpected final job state: '+str(result))
            return result
    raise RuntimeError('Background output did not reach a terminal state')


def solve(case):
    asset=case.call('image','asset.import',source_path='original.png')['asset']
    saved=store(case,authored(asset))
    preview=case.call('preview','document.preview',document=saved,options=dict(focus=dict(type='region',bounds=[32,40,56,60])),preview=True)
    save(case.root/'preview.png',base64.b64decode(preview['artifact']['data'],validate=True))
    case.outputs=('cancelled.png','recovered.png');attempts={}
    args=dict(document=saved,output=dict(file_name='cancelled.png',format='png'))
    with case.launch_boundary('cancel-start','job.start','cancel',**args) as cancelling:
        case.event('cancel-requested',request_id='cancel',runner=cancelling['runner'])
        case.call('cancel','job.cancel',request_id='cancel')
    attempts['cancelled']=terminal(case,'cancel','cancelled')
    attempts['cancel-resume']=case.call('cancel-resume','job.resume',request_id='cancel')
    attempts['cancel-error']=case.call('cancel-result','job.result',request_id='cancel',expected_error='JOB_NOT_COMPLETED')
    # Admit revision 0 before the revision 1 edit using an OS queue lease,
    # without an engine test hook or any database writes by the harness.
    deadline=time.monotonic()+5
    while case.snapshot()['runtime']['owner'] is not None:
        require(time.monotonic()<deadline,'Cancelled queue did not become idle');time.sleep(.01)
    args=dict(document=saved,output=dict(file_name='recovered.png',format='png'))
    with case.blocked_queue():
        case.call('recover-start','job.start',request_id='recover',**args)
        apply(case,'newer',0,[dict(op='vector',id='badge',geometry=dict(shape='rect',x=32,y=40,width=24,height=20),fill=ORANGE)])
    with case.launch_boundary('launch','job.resume','recover') as interrupted:case.interrupt_supervisor(interrupted)
    attempts['interrupted-status']=case.call('interrupted-status','job.status',request_id='recover')
    attempts['interrupted-wait']=case.call('interrupted-wait','job.wait',request_id='recover',wait_ms=0)
    attempts['interrupted-error']=case.call('interrupted-result','job.result',request_id='recover',expected_error='JOB_NOT_COMPLETED')
    case.output_checkpoint('after-inspection')
    case.call('restart','job.resume',request_id='recover')
    attempts['completed']=terminal(case,'recover','completed')
    attempts['receipt']=case.call('result','job.result',request_id='recover')
    case.output_checkpoint('before-replays')
    source_snapshot(case,ref(1))
    attempts['start-replay']=case.call('start-replay','job.start',request_id='recover',retry_of='recover-start',**args)
    attempts['resume-completed']=case.call('resume-completed','job.resume',request_id='recover',retry_of='restart')
    attempts['result-replay']=case.call('result-replay','job.result',request_id='recover',retry_of='result')
    attempts['overwrite-error']=case.call('overwrite','document.publish',document=ref(1),output=args['output'],expected_error='OUTPUT_EXISTS')
    case.output_checkpoint('after-replays')
    case.call('verify-history','session.verify',session_id='work')
    save_json(case.root/'attempts.json',attempts)


def observation_events(case):
    path=getattr(case,'judge_root',case.root)/'recovery-observations.json'
    require(path.is_file() and not path.is_symlink() and path.stat().st_size<=8*1024*1024,'Missing, linked or oversized recovery observations')
    evidence=strict_json(path.read_bytes())
    require(set(evidence)=={'schema_version','events'} and evidence['schema_version']==1 and isinstance(evidence['events'],list),
        'Invalid recovery observation envelope')
    return evidence['events']


def one(events,kind,**fields):
    rows=[e for e in events if e['kind']==kind and all(e.get(k)==v for k,v in fields.items())]
    require(len(rows)==1,'Expected exactly one recovery observation: '+kind+' '+str(fields))
    return rows[0]


def terminal_identity(value):
    value=copy.deepcopy(value)
    # Publication can finish before the supervisor attaches the runner's final
    # process report. Container-wide lifetime accounting is checked at close.
    for key in ('job_root','replayed','last_process_report','updated_ms'):value.pop(key)
    return value


def durable_inputs(case):
    asset=dict(width=WIDTH,height=HEIGHT,sha256=sha(canonical(WIDTH,HEIGHT,original_pixels())),storage=dict(type='stored'),
        provenance=dict(source_sha256=case.sources['original.png'],interpretation='declared_srgb'))
    original=case.call('judge-original','document.validate',document=authored(asset))
    receipts={name:case.call('judge-receipt-'+name,'session.receipt',session_id='work',request_id=name) for name in ('create','newer')}
    final=case.call('judge-reopen','document.validate',document=dict(file_path='editable.json',sha256=sha(delivered(case,'editable.json'))))
    current=case.call('judge-current','session.read',session_id='work')
    history=case.call('judge-history','session.verify',session_id='work')
    cancelled=case.call('judge-cancelled','job.status',request_id='cancel')
    completed=case.call('judge-completed','job.status',request_id='recover')
    receipt=case.call('judge-result','job.result',request_id='recover')
    preview=case.call('judge-preview','document.preview',document=original,options=dict(focus=dict(type='region',bounds=[32,40,56,60])),preview=True)
    fresh=case.call('judge-render','document.preview',document=original,options={},preview=True)
    overwrite=case.call('judge-overwrite','document.publish',document=current['document'],output=dict(file_name='recovered.png',format='png'),expected_error='OUTPUT_EXISTS')
    return dict(original=original,receipts=receipts,final=final,current=current,history=history,cancelled=cancelled,completed=completed,
        receipt=receipt,preview=preview,fresh=fresh,overwrite=overwrite)


def judge_retained(case,original,receipts,final,current,history,cancelled,completed,receipt,preview,fresh,overwrite):
    events=observation_events(case);attempts=strict_json(delivered(case,'attempts.json'))
    require(set(attempts)=={'cancelled','cancel-resume','cancel-error','interrupted-status','interrupted-wait','interrupted-error',
        'completed','receipt','start-replay','resume-completed','result-replay','overwrite-error'},'Missing or extra recovery attempts')
    raw=delivered(case,'recovered.png');digest=sha(raw)
    def review():
        for data in (delivered(case,'preview.png'),base64.b64decode(preview['artifact']['data'],validate=True)):
            png_check(data,24,20,bytes(GREEN)*480)
    case.check('review-pixels',review)
    def boundary(request_id):
        event=one(events,'fault-boundary',request_id=request_id);state=event['state']
        require(event['outputs_absent'] is True and state['id']==request_id and state['phase']=='running' and state['attempt']==1 and
            state['progress']['phase']=='rendering_and_encoding','Fault was not observed during active rendering before publication')
        for key in ('worker','runner'):
            require(state[key] is not None and any(e['kind']=='process-retained' and e['identity']==state[key] and
                e['seconds']<=event['seconds'] for e in events),'Fault process was not retained before intervention')
        return event,state
    def cancellation():
        event,state=boundary('cancel');requested=one(events,'cancel-requested',request_id='cancel')
        require(requested['runner']==state['runner'] and requested['seconds']>=event['seconds'],'Cancellation targeted a different rendering attempt')
        require(cancelled['state']=='cancelled' and cancelled['attempt']==1 and cancelled['cancel_requested'] and
            all(terminal_identity(attempts[k])==terminal_identity(cancelled) for k in ('cancelled','cancel-resume')) and
            attempts['cancel-resume']['replayed'] is True and attempts['cancel-error']['code']=='JOB_NOT_COMPLETED' and
            not (case.root/'cancelled.png').exists(),'Cancellation published, restarted or lost its original terminal state')
    case.check('active-cancellation',cancellation)
    def interruption():
        event,state=boundary('recover');killed=one(events,'supervisor-interrupted');exited=one(events,'interrupted-tree-exited')
        require(killed['identity']==exited['worker']==state['worker'] and exited['runner']==state['runner'] and
            event['seconds']<=killed['seconds']<=exited['seconds'],'Interruption did not stop the exact retained supervisor and runner')
        inspected=one(events,'output-checkpoint',label='after-inspection')
        require(exited['seconds']<=inspected['seconds'] and inspected['outputs']=={'cancelled.png':None,'recovered.png':None},
            'Inspection published or restarted the interrupted output')
        status=attempts['interrupted-status']
        require(status==attempts['interrupted-wait'] and status['state']=='interrupted' and status['recovery_required'] and
            status['attempt']==1 and status['worker']==state['worker'] and status['runner']==state['runner'] and
            status['output'] is None and attempts['interrupted-error']['code']=='JOB_NOT_COMPLETED',
            'Retained inspection differs from the interrupted process identities or state')
        observed=inspected['snapshot']['jobs']['recover']
        require(observed['phase']=='interrupted' and observed['attempt']==1 and observed['worker']==state['worker'] and
            observed['runner']==state['runner'] and observed['result'] is None,
            'The inspection checkpoint did not independently observe the interrupted unpublished job')
    case.check('interrupted-unpublished',interruption)
    def picture():
        for data in (raw,base64.b64decode(fresh['artifact']['data'],validate=True)):png_check(data,WIDTH,HEIGHT,expected_pixels())
    case.check('recovered-pixels',picture)
    wanted=copy.deepcopy(original);wanted['revision']=1;wanted['items'][1]['content']['fill']=ORANGE
    def pinning():
        require(receipts['create']['document']==original and final==strict_json(delivered(case,'editable.json'))==wanted==current['document']==receipts['newer']['document'],
            'Pinned or current artwork changed geometry, resources or unrelated controls')
        require(receipt['revision']==0 and completed['attempt']==2 and completed['document']['revision']==0 and
            terminal_identity(attempts['completed'])==terminal_identity(completed),'Recovery did not retain the admitted revision and original resource')
    case.check('revision-resource-pinning',pinning)
    def once():
        require(attempts['receipt']==attempts['result-replay']==receipt and receipt['sha256']==digest and receipt['bytes']==len(raw) and
            attempts['overwrite-error']==overwrite and all(attempts[k]['replayed'] is True and
                terminal_identity(attempts[k])==terminal_identity(completed) for k in ('start-replay','resume-completed')),
            'Replay or overwrite changed the publication receipt, attempt or terminal state')
        before=one(events,'output-checkpoint',label='before-replays');after=one(events,'output-checkpoint',label='after-replays')
        require(before['seconds']<=after['seconds'] and before['outputs']==after['outputs'] and
            before['outputs']['cancelled.png'] is None and before['outputs']['recovered.png']['sha256']==digest and
            before['outputs']['recovered.png']['bytes']==len(raw) and
            ((getattr(case,'driver_evidence',None) or {}).get('imported') is True or
             (case.root/'recovered.png').stat().st_ino==after['outputs']['recovered.png']['identity'][0]),
            'Replay replaced or altered the physical publication')
        ledger=case.root/'.inkbolt/jobs/publications/publications.sqlite3'
        require(ledger.is_file() and not ledger.is_symlink() and ledger.resolve().is_relative_to(case.root.resolve()),'Missing or linked publication ledger')
        with closing(sqlite3.connect(ledger.as_uri()+'?mode=ro',uri=True)) as db:
            rows=db.execute('SELECT request_id,payload,sha256 FROM publications').fetchall()
        require(len(rows)==1 and rows[0][0]=='recover' and sha(rows[0][1])==rows[0][2],'Duplicate or invalid publication rows')
        record=strict_json(rows[0][1]);require(record['phase']=='complete' and record['sha256']==digest,'Publication is not durably complete')
    case.check('single-publication-no-overwrite',once)
    def atomic():
        observed=[e for e in events if e['kind']=='output-observed'];last=one(events,'output-checkpoint',label='after-replays')['outputs']['recovered.png']
        require(observed and all(e['name']=='recovered.png' and e['sha256']==digest and e['bytes']==len(raw) and
            e['identity'][0]==last['identity'][0] for e in observed) and not (case.root/'cancelled.png').exists(),
            'An observed final file was partial, cancelled or replaced')
    case.check('no-partial-final',atomic)
    case.check('history-valid',lambda:require(history['valid'] and history['revision']==current['revision']==current['current_revision']==1 and
        receipts['create']['receipt']['revision']==0 and receipts['newer']['receipt']['from_revision']==0 and
        current['state_sha256']==receipts['newer']['receipt']['state_sha256'] and
        receipts['create']['resources']==receipts['newer']['resources']==current['resources'],'History changed revisions or resource bindings'))


def judge(case):judge_retained(case,**durable_inputs(case))


def recovery(case):
    fixture(case);case.begin(PROMPT.read_text(encoding='utf-8'));solve(case);case.begin_judging();judge(case)
    if any(c['name']=='review-pixels' and c['status']=='pass' for c in case.checks):case.verified_preview(delivered(case,'preview.png'))
