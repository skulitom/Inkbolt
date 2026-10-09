"""Real release-process cancellation and restart with independent output checks."""
from contextlib import closing
import hashlib
import json
import sqlite3
import time

from benchmark_graphics import (GREEN, ORANGE, document, rectangle, store, apply,
    source_snapshot, ref, view, verify_history, png_check, sha)
from benchmark_runtime import require
from test_images_cli import png, canonical


def terminal(case, request_id, expected):
    deadline=time.monotonic()+25
    for index in range(30):
        require(time.monotonic()<deadline, 'Background output exceeded its observation deadline')
        result=case.call(f'{request_id}-wait-{index}','job.wait',request_id=request_id,wait_ms=1000)
        if result['state'] not in ('queued','running'):
            require(result['state']==expected, 'Unexpected final job state: '+str(result))
            return result
    raise RuntimeError('Background output did not reach a terminal state')


def recovery(case):
    width=height=1024
    colors=hashlib.shake_256(b'Inkbolt original recovery texture v1').digest(width*height*3)
    original=bytearray(width*height*4)
    for channel in range(3):original[channel::4]=colors[channel::3]
    original[3::4]=b'\xff'*(width*height)
    case.source('original.png',png(width,height,original))
    expected=bytearray(original)
    for y in range(40,60):expected[(y*width+32)*4:(y*width+56)*4]=bytes(GREEN)*24
    case.begin('Import the original 1024x1024 synthetic texture, place a green 24x20 badge at (32,40), '
        'save revision 0 and review the badge. Cancel one export after it starts rendering. Queue another '
        'export of revision 0, then change the current badge to orange before running that export. '
        'After its supervisor is interrupted during rendering, inspect without publishing, explicitly resume, '
        'and recover the pinned green output. Repeated submission/result/resume must preserve its receipt and '
        'physical file. An existing destination must never be overwritten. Preserve original image and history.')
    asset=case.call('image','asset.import',source_path='original.png')['asset']
    saved=store(case,document('recovery','vector',width,height,assets=dict(photo=asset),items=[
        dict(id='image',content=dict(type='image',asset_id='photo',width=width,height=height)),
        rectangle('badge',32,40,24,20,GREEN)]))
    view(case,'preview',saved,'review-pixels',24,20,bytes(GREEN)*480,
         focus=dict(type='region',bounds=[32,40,56,60]))
    case.outputs=('cancelled.png','recovered.png')
    args=dict(document=saved,output=dict(file_name='cancelled.png',format='png'))
    with case.launch_boundary('cancel-start','job.start','cancel',**args) as cancelling:
        require(not (case.root/'cancelled.png').exists(), 'Cancel boundary followed publication')
        case.event('cancel-requested',request_id='cancel',runner=cancelling['runner'])
        case.call('cancel','job.cancel',request_id='cancel')
    cancelled=terminal(case,'cancel','cancelled')
    no_restart=case.call('cancel-resume','job.resume',request_id='cancel')
    case.call('cancel-result','job.result',request_id='cancel',expected_error='JOB_NOT_COMPLETED')
    case.check('active-cancellation',lambda:require(cancelled['attempt']==1 and cancelled['cancel_requested']
        and no_restart['state']=='cancelled' and not (case.root/'cancelled.png').exists(),
        'Active cancellation published output or permitted a restart'))

    # Ensure the first supervisor has released the lease before acquiring our
    # own queue gate. The completed runner remains represented by a held handle.
    deadline=time.monotonic()+5
    while case.snapshot()['runtime']['owner'] is not None:
        require(time.monotonic()<deadline,'Cancelled queue did not become idle');time.sleep(.01)
    args=dict(document=saved,output=dict(file_name='recovered.png',format='png'))
    with case.blocked_queue():
        case.call('recover-start','job.start',request_id='recover',**args)
        apply(case,'newer',0,[dict(op='vector',id='badge',geometry=dict(shape='rect',x=32,y=40,width=24,height=20),fill=ORANGE)])
    with case.launch_boundary('launch','job.resume','recover') as interrupted:
        require(not (case.root/'recovered.png').exists(), 'Interruption boundary followed publication')
        case.interrupt_supervisor(interrupted)
    status=case.call('interrupted-status','job.status',request_id='recover')
    waiting=case.call('interrupted-wait','job.wait',request_id='recover',wait_ms=0)
    case.call('interrupted-result','job.result',request_id='recover',expected_error='JOB_NOT_COMPLETED')
    case.check('interrupted-unpublished',lambda:require(status['state']=='interrupted' and status['recovery_required']
        and waiting['state']=='interrupted' and not (case.root/'recovered.png').exists(),
        'Inspection restarted or published interrupted output'))
    case.call('restart','job.resume',request_id='recover')
    finished=terminal(case,'recover','completed')
    receipt=case.call('result','job.result',request_id='recover')
    path=case.root/'recovered.png';raw=path.read_bytes();identity=path.stat().st_ino
    case.check('recovered-pixels',lambda:png_check(raw,width,height,bytes(expected)))
    current=source_snapshot(case,ref(1))
    case.check('revision-resource-pinning',lambda:require(receipt['revision']==0 and finished['attempt']==2
        and current['items'][1]['content']['fill']==ORANGE
        and current['assets']['photo']['sha256']==sha(canonical(width,height,original)),
        'Recovery did not retain the admitted revision and original resource'))
    replay=case.call('start-replay','job.start',request_id='recover',retry_of='recover-start',**args)
    resumed=case.call('resume-completed','job.resume',request_id='recover',retry_of='restart')
    repeated=case.call('result-replay','job.result',request_id='recover',retry_of='result')
    case.call('overwrite','document.publish',document=ref(1),output=args['output'],expected_error='OUTPUT_EXISTS')
    def once():
        require(repeated==receipt and replay['replayed'] and replay['state']==resumed['state']=='completed'
            and replay['attempt']==resumed['attempt']==2,'Replay changed receipt or repeated work')
        require(path.read_bytes()==raw and path.stat().st_ino==identity and receipt['sha256']==sha(raw)
            and receipt['bytes']==len(raw),'Publication bytes, physical identity or receipt changed')
        ledger=case.ledger.parent/'publications/publications.sqlite3'
        with closing(sqlite3.connect(ledger.as_uri()+'?mode=ro',uri=True)) as db:
            rows=db.execute('SELECT request_id,payload,sha256 FROM publications').fetchall()
        require(len(rows)==1 and rows[0][0]=='recover' and sha(rows[0][1])==rows[0][2], 'Duplicate or invalid publication rows')
        record=json.loads(rows[0][1]);case.event('final-publication',record=record)
        require(record['phase']=='complete' and record['sha256']==sha(raw),'Publication was not durably completed')
    case.check('single-publication-no-overwrite',once)
    def atomic():
        with case.lock:
            observed=[e for e in case.events if e['kind']=='output-observed']
        require(observed and all(e['name']=='recovered.png' and e['sha256']==sha(raw)
            and e['bytes']==len(raw) and e['identity'][0]==identity for e in observed),
            'A final output observation contained partial, cancelled or replaced content')
    case.check('no-partial-final',atomic)
    verify_history(case)
