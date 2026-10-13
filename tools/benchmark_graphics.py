"""Original scripted task adapters with separate geometry/pixel/source oracles."""
import base64
import json

from benchmark_runtime import require
from workload_cases import document, rectangle, save, sha
from test_editing_cli import png_pixels


BLUE = [20, 80, 150, 255]
GREEN = [30, 150, 70, 255]
ORANGE = [220, 90, 30, 255]


def pixels(width, height, rectangles):
    """Independent integer rectangle oracle; fixtures deliberately avoid overlap blending."""
    out = bytearray(width*height*4)
    for x,y,w,h,color in rectangles:
        require(x >= 0 and y >= 0 and x+w <= width and y+h <= height, 'Oracle rectangle is out of bounds')
        for row in range(y,y+h):
            out[(row*width+x)*4:(row*width+x+w)*4] = bytes(color)*w
    return bytes(out)


def png_check(raw, width, height, expected):
    w,h,actual,_ = png_pixels(raw)
    require((w,h)==(width,height), 'Delivered image dimensions changed')
    require(actual==expected, 'Delivered pixels differ from independent authored geometry')


def ref(revision):
    return dict(session_id='work',revision=revision)


def store(case, doc, **options):
    return case.call('save','session.create',session_id='work',request_id='create',
                     document=doc,response_mode='compact',**options)['document_ref']


def apply(case,step,revision,operations,**kw):
    return case.call(step,'session.apply',session_id='work',request_id=step,
        expected_revision=revision,action=dict(type='edit',operations=operations),response_mode='compact',**kw)


def source_snapshot(case,doc,name='editable'):
    result=case.call(name,'document.publish',document=doc,
                     output=dict(format='snapshot',file_name=name+'.json'))
    raw=(case.root/(name+'.json')).read_bytes()
    require(sha(raw)==result['sha256'], 'Snapshot publication identity differs')
    return json.loads(raw)


def view(case,step,doc,check,width,height,expected,**options):
    result=case.call(step,'document.preview',document=doc,options=options,preview=True)
    raw=base64.b64decode(result['artifact']['data'],validate=True)
    save(case.root/(step+'.png'),raw)
    case.check(check,lambda:png_check(raw,width,height,expected),preview_step=step)
    return result


def verify_history(case):
    result=case.call('verify-history','session.verify',session_id='work')
    case.check('history-valid',lambda:require(result['valid'],'Invalid saved history'))


def two_items():
    return document('revisions','vector',32,16,items=[rectangle('target',2,4,8,8,BLUE),rectangle('other',22,4,8,8,GREEN)])


def lost_response(case):
    seed=case.seed(two_items())
    case.begin('Open source.json, move target three pixels right and save the edit with request ID move. '
        'The adapter will drop that successful response. Recover the original receipt and retry safely. '
        'Undo, retry the old request again, and prove neither retry duplicates or reapplies the edit.')
    store(case,seed)
    request=dict(session_id='work',request_id='move',expected_revision=0,response_mode='compact',
        action=dict(type='edit',operations=[dict(op='transform',id='target',matrix=[1,0,0,1,3,0],space='world')]))
    case.call('lost','session.apply',discard=True,**request)
    recovered=case.call('recover-receipt','session.receipt',session_id='work',request_id='move',response_mode='compact')
    # The hidden response is inspected by this independent receipt oracle only;
    # the scripted recovery path uses the already-known request ID.
    original=case.results['lost']['result']
    case.check('original-receipt',lambda:require(recovered['receipt_summary']==original['receipt_summary'],'Recovered a different receipt'))
    retry=case.call('retry','session.apply',retry_of='lost',**request)
    case.check('retry-idempotent',lambda:require(retry['replayed'] and retry['receipt_summary']==original['receipt_summary'] and
        retry['document_ref']['revision']==1,'Retry changed the edit or its revision'))
    view(case,'preview',ref(1),'edited-pixels',32,16,pixels(32,16,[(5,4,8,8,BLUE),(22,4,8,8,GREEN)]))
    case.call('undo','session.apply',session_id='work',request_id='undo',expected_revision=1,action=dict(type='undo'),response_mode='compact')
    case.call('retry-after-undo','session.apply',retry_of='lost',**request)
    current=source_snapshot(case,ref(2))
    case.check('undo-preserved',lambda:require(current['revision']==2 and all(i['transform']==[1,0,0,1,0,0] for i in current['items']), 'Historical retry reapplied an undone change'))
    verify_history(case)


def conflicting_writers(case):
    seed=case.seed(two_items())
    case.begin('Open source.json. Review a proposal to move target three pixels right. A different '
        'writer moves other two pixels left first. Reject the stale proposal; review and apply '
        'a replacement on the new head, preserving both intents and original history.')
    saved=store(case,seed)
    action=dict(type='edit',operations=[dict(op='transform',id='target',matrix=[1,0,0,1,3,0],space='world')])
    stale=case.call('review-old','session.dry_run',session_id='work',request_id='move-target',expected_revision=0,action=action)
    apply(case,'other-writer',0,[dict(op='transform',id='other',matrix=[1,0,0,1,-2,0],space='world')])
    rejected=case.call('stale','session.apply_proposal',proposal=stale['proposal'],action=action,expected_error='REVISION_CONFLICT',response_mode='compact')
    case.check('stale-rejected',lambda:require(rejected['code']=='REVISION_CONFLICT','Stale proposal was accepted'))
    reviewed=case.call('review-current','session.dry_run',session_id='work',request_id='move-target',expected_revision=1,action=action)
    case.call('apply-reviewed','session.apply_proposal',proposal=reviewed['proposal'],action=action,response_mode='compact')
    current=source_snapshot(case,ref(2))
    case.check('both-intents-preserved',lambda:require([i['transform'] for i in current['items']]==[[1,0,0,1,3,0],[1,0,0,1,-2,0]] and
        [i['content']['geometry'] for i in current['items']]==[i['content']['geometry'] for i in two_items()['items']], 'Conflict resolution lost an intent or source geometry'))
    view(case,'preview',ref(2),'conflict-pixels',32,16,pixels(32,16,[(5,4,8,8,BLUE),(20,4,8,8,GREEN)]))
    view(case,'historical',saved,'historical-pixels',32,16,pixels(32,16,[(2,4,8,8,BLUE),(22,4,8,8,GREEN)]))
    verify_history(case)
