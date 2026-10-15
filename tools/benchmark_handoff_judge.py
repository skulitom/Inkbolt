"""B20 durable-state, delivered-artifact and observed-consumer oracles."""
import base64
import copy
import json

from benchmark_diagram import delivered
from benchmark_handoff import (WIDTH,HEIGHT,RATE,DURATION,SCHEDULE,original_frames,shifted,
    consumer_rgba,over_black,decode_movie,check_decoded,check_delivery_preservation)
from benchmark_graphics import png_check
from benchmark_large_layout import retained_session_store
from benchmark_resources import reported_review
from benchmark_runtime import require,safe_name,strict_json
from workload_cases import document,sha


def authored():
    first,second=original_frames()
    items=[dict(id=name,visible=index==0,content=dict(type='raster',width=WIDTH,height=HEIGHT,rgba_hex=raw.hex()))
        for index,(name,raw) in enumerate((('art',first),('other',second)))]
    variants=dict(sequence=dict(plays=0,frames=[dict(id='frame-'+str(i),dataset='frame-'+str(i),
        delay=dict(numerator=3-i,denominator=25)) for i in range(2)]),
        definition=dict(bindings=[dict(key='layer-'+str(i),item_id=name,property='visible') for i,name in enumerate(('art','other'))],
            datasets={'frame-'+str(i):dict(values={'layer-'+str(j):dict(type='visible',value=i==j) for j in range(2)}) for i in range(2)}),
        base=[dict(type='visible',value=True)]*2,selected='frame-0')
    return document('linked-graphic','raster',WIDTH,HEIGHT,items=items,variants=variants)


def read_json(case,name):return strict_json(delivered(case,name))


def consumer_roles(report,records):
    """Locate workflow observations by requests/order, never client step names."""
    from pathlib import Path
    rows=report['calls'];roles={}
    def pick(role,command,predicate=lambda request:True,after=-1,before=None,error=False,revision=None):
        def returned_revision(record):
            value=record['response'].get('result',{})
            project=value.get('project',value) if isinstance(value,dict) else {}
            return isinstance(project,dict) and type(project.get('revision')) is int and project['revision']==revision
        matches=[i for i,row in enumerate(rows) if after<i<(len(rows) if before is None else before) and
            row['command']==command and row['step'] in records and records[row['step']]['response'].get('ok') is (not error) and
            predicate(records[row['step']]['request']) and (revision is None or returned_revision(records[row['step']]))]
        require(matches,'Missing observed consumer workflow role: '+role)
        index=matches[0];roles[role]=rows[index]['step'];return index
    initial=pick('initial','session.apply',lambda r:r.get('request_id')=='initial')
    compiled=pick('delivery-1-compile','scene.render',lambda r:Path(r.get('output','')).parent.name=='delivery-1',after=initial)
    relink=pick('relink','session.apply',lambda r:r.get('request_id')=='relink',after=compiled)
    reviewed=pick('review-relink','session.preview',lambda r:r.get('expected_revision')==1,after=compiled,before=relink)
    undo=pick('undo','session.undo',lambda r:r.get('request_id')=='undo',after=relink)
    retry=pick('retry','session.apply',lambda r:r.get('request_id')=='relink',after=undo)
    pick('stale','session.apply',lambda r:r.get('request_id')=='stale',after=relink,before=undo,error=True)
    for role,after,before in (('timeline-before',initial,compiled),('before-relink',compiled,reviewed),
        ('after-review',reviewed,relink),('restored',undo,retry),('after-retry',retry,None)):
        pick(role,'session.get',after=after,before=before)
    # Reading the current head between relink and undo is equivalent to an
    # explicit revision-2 read. Bind either form to the actual returned revision.
    pick('timeline-after','session.get',lambda r:'revision' not in r or r['revision']==2,
        after=relink,before=undo,revision=2)
    pick('historical','session.get',lambda r:r.get('revision')==1,after=relink,revision=1)
    return roles


def durable_inputs(case):
    session=dict(session_root=retained_session_store(case,'work'),session_id='work')
    original=case.call('judge-authored','document.validate',document=authored())
    receipts={name:case.call('judge-receipt-'+name,'session.receipt',**session,request_id=name) for name in ('create','move')}
    current=case.call('judge-current','session.read',**session)
    history=case.call('judge-history','session.verify',**session)
    final=case.call('judge-final','document.validate',document=dict(file_path='after.json',sha256=sha(delivered(case,'after.json'))))
    before=case.call('judge-before','document.validate',document=dict(file_path='before.json',sha256=sha(delivered(case,'before.json'))))
    historical=case.call('judge-historical-source','document.validate',document=dict(file_path='historical-source.json',sha256=sha(delivered(case,'historical-source.json'))))
    preview=case.call('judge-preview','document.preview',document=current['document'],options={},preview=True)
    inspections=[case.call('judge-handoff-'+str(i),'handoff.inspect',handoff=read_json(case,f'delivery-{i}-handoff.json'),
        input_root=f'delivery-{i}',include_schedule=True) for i in range(2)]
    consumer=case.consumer;session=dict(store_root=str(case.root/'cutbolt-store'),project_id='linked')
    projects={i:consumer.call('judge-project-'+str(i),'session.get',**session,revision=i) for i in range(4)}
    projects={i:v.get('project',v) for i,v in projects.items()}
    head=consumer.call('judge-head','session.get',**session);head=head.get('project',head)
    saved={name:consumer.call('judge-receipt-'+name,'session.receipt',**session,request_id=name) for name in ('initial','relink','undo')}
    checked=consumer.call('judge-history','session.check',store_root=session['store_root'])
    movies={name:decode_movie(consumer,'judge-'+name,case.root/path) for name,path in (
        ('delivery-0','delivery-0/compiled.mkv'),('delivery-1','delivery-1/compiled.mkv'),
        ('original','original.mkv'),('revised','revised.mkv'),('undone','undone.mkv'))}
    return dict(original=original,receipts=receipts,current=current,history=history,final=final,before=before,historical=historical,preview=preview,
        inspections=inspections,projects=projects,head=head,saved=saved,checked=checked,movies=movies)


def judge_retained(case,original,receipts,current,history,final,before,historical,preview,inspections,projects,head,saved,checked,movies):
    evidence=getattr(case,'judge_root',case.root)/'handoff-observations.json'
    require(evidence.is_file() and not evidence.is_symlink() and evidence.stat().st_size<=16*1024*1024,'Missing or oversized harness observations')
    observed=strict_json(evidence.read_bytes())
    require(set(observed)=={'schema_version','consumer','records','delivery_files'} and observed['schema_version']==1,
        'Unexpected handoff observation fields')
    records=observed['records'];report=observed['consumer'];attempts=read_json(case,'consumer-attempts.json')
    roles=consumer_roles(report,records)
    def record(role):return records[roles[role]]
    require(set(attempts)=={'initial','review','relink','stale','undo','retry'},'Unexpected retained consumer attempts')
    def response(step,error=False):
        value=record(step)['response'];require(value.get('ok') is (not error),'Unexpected observed consumer response')
        return value['error' if error else 'result']
    def project_response(step):
        value=response(step);return value.get('project',value)
    wanted=copy.deepcopy(original);wanted['revision']=1;wanted['items'][0]['transform']=[1,0,0,1,4,0]
    first,second=original_frames();moved=shifted(first)
    old_frames=[consumer_rgba((first,second)[i]) for i in SCHEDULE]
    new_frames=[consumer_rgba((moved,second)[i]) for i in SCHEDULE]
    pins=[read_json(case,f'delivery-{i}-handoff.json') for i in range(2)]
    def revision(name,expected):
        value=read_json(case,name).get('revision')
        require(type(value) is int and value==expected,'Missing or different retained source revision: '+name)
    def source():
        revision('before.json',0);revision('after.json',1)
        require(final==current['document']==receipts['move']['document']==wanted and
            original==receipts['create']['document']==before,'Source edit or unrelated controls changed')
        review=reported_review(delivered(case,'review.json'))
        require(review['proposed_document']==wanted and review['predicted_receipt']==receipts['move']['receipt'] and
            review['proposed_resources']==receipts['move']['resources'] and review['dry_run'] is True and
            review['committed'] is False and review['source_changed'] is False and review['base_ref']['revision']==0 and
            review['base_ref']['session_id']=='work' and review['proposal']['session_id']=='work' and
            review['proposal']['request_id']=='move' and review['proposal']['expected_revision']==0 and
            review['proposal']['base_state_sha256']==receipts['create']['receipt']['state_sha256'] and
            review['proposal']['result_state_sha256']==receipts['move']['receipt']['state_sha256'],
            'Retained source review differs from the durable edit')
    case.check('reviewed-source-only',source)
    def picture():
        for raw in (delivered(case,'preview.png'),base64.b64decode(preview['artifact']['data'],validate=True)):
            png_check(raw,WIDTH,HEIGHT,moved)
        case.verified_preview(delivered(case,'preview.png'))
    case.check('revised-preview',picture)
    required_files={}
    def bundle(index):
        folder=f'delivery-{index}/';pin=pins[index];manifest=pin['manifest']
        raw=delivered(case,folder+'handoff-'+pin['sha256']+'.json')
        require(sha(raw)==pin['sha256'] and strict_json(raw)==manifest,'Pinned manifest differs from its delivered bytes')
        required_files[folder+'handoff-'+pin['sha256']+'.json']=sha(raw)
        def file(value):
            name=folder+safe_name(value['path']);data=delivered(case,name)
            require(len(data)==value['bytes'] and sha(data)==value['sha256'],'Handoff file identity differs')
            required_files[name]=sha(data);return data
        require(strict_json(file(manifest['source']['snapshot']))==(original if index==0 else wanted),'Editable handoff source changed')
        require(len(manifest['frames'])==2 and inspections[index]['files_verified'] and
            inspections[index]['selected_frames']==list(SCHEDULE),'Pinned frame schedule changed')
        for frame,expected in zip(manifest['frames'],(first if index==0 else moved,second),strict=True):
            png_check(file(frame['image']),WIDTH,HEIGHT,expected)
        scene=strict_json(file(manifest['scene']))
        require(scene['transparent'] and scene['color']=='srgb_straight_encoded' and
            scene['layers'][0]['alpha_mode']=='straight','Handoff color or alpha interpretation changed')
        required_files[folder+'compiled.mkv']=sha(delivered(case,folder+'compiled.mkv'))
        check_decoded(movies['delivery-'+str(index)],old_frames if index==0 else new_frames)
    for index in range(2):case.check(f'delivery-{index}-pixels-clock',lambda i=index:bundle(i))
    case.check('pinned-successor',lambda:require(pins[1]['manifest']['previous']['sha256']==pins[0]['sha256'] and
        pins[1]['manifest']['source']['revision']==1 and pins[0]['manifest']['source']['revision']==0 and
        pins[0]['manifest']['previous'] is None,'Invalid source revision predecessor'))
    def asset(index):
        path=f'delivery-{index}/compiled.mkv';raw=delivered(case,path)
        return dict(id=f'graphic-r{index}',path=path,duration=DURATION,identity=dict(bytes=len(raw),sha256=sha(raw)))
    def clip(ident,index,start):return dict(id=ident,asset_id=f'graphic-r{index}',start=start,source_in=dict(num=0,den=1),duration=DURATION)
    base=dict(schema_version=1,id='linked',revision=0,width=WIDTH,height=HEIGHT,frame_rate=RATE,assets=[],clips=[])
    expected=copy.deepcopy(base);expected.update(revision=1,assets=[asset(0)],tracks=dict(duration=dict(num=4,den=5),links=[],
        tracks=[dict(id='overlay',kind='video',locked=False,enabled=True,composite='alpha_over',clips=[
            clip('graphic',0,dict(num=0,den=1)),clip('unrelated',0,DURATION)])]))
    def no_relink():
        require(projects[0]==base and projects[1]==expected==read_json(case,'timeline-before.json')==
            read_json(case,'before-relink.json')==read_json(case,'after-review.json')==
            project_response('timeline-before')==project_response('before-relink')==project_response('after-review'),
            'Export or preview implicitly changed the consumer timeline')
        steps=[r['step'] for r in report['calls']]
        order=['initial','timeline-before','delivery-1-compile','before-relink','review-relink','after-review','relink']
        require([steps.index(roles[step]) for step in order]==sorted(steps.index(roles[step]) for step in order),'Consumer review/relink order changed')
    case.check('no-implicit-relink',no_relink)
    def explicit():
        target=copy.deepcopy(expected);target['revision']=2;target['assets'].append(asset(1));target['tracks']['tracks'][0]['clips'][0]['asset_id']='graphic-r1'
        actual=copy.deepcopy(projects[2])
        for value in (actual,target):value['tracks']['tracks'][0]['clips'].sort(key=lambda c:c['id'])
        require(actual==target and projects[2]==read_json(case,'timeline-after.json')==project_response('timeline-after') and
            projects[1]==read_json(case,'historical.json')==project_response('historical'),'Replacement changed unrelated state or old history')
        require(attempts['initial']==saved['initial']==response('initial') and attempts['relink']==saved['relink']==response('relink') and
            attempts['review']==response('review-relink')==saved['relink']['changes'] and
            record('review-relink')['request']['operations']==record('relink')['request']['operations'] and
            record('review-relink')['request']['expected_revision']==record('relink')['request']['expected_revision']==1,
            'Explicit relink or its review differs from durable receipts')
    case.check('explicit-consumer-revision',explicit)
    def undo_retry():
        restored=copy.deepcopy(expected);restored['revision']=3
        require(projects[3]==head==restored==read_json(case,'restored.json')==read_json(case,'after-retry.json')==
            project_response('restored')==project_response('after-retry'),'Undo or retry changed the restored consumer state')
        require(attempts['undo']==saved['undo']==response('undo') and attempts['retry']==saved['relink']==response('retry') and
            record('retry')['request']==record('relink')['request'] and attempts['stale']==response('stale',True) and
            attempts['stale']['code']=='REVISION_CONFLICT' and record('stale')['request']['expected_revision']==1 and
            record('stale')['request']['operations']==record('relink')['request']['operations'] and
            record('stale')['request']['request_id']=='stale','Undo, stale rejection or exact retry evidence differs')
        require(checked==dict(valid=True,migration_required=False,store_schema_version=2,projects=[dict(project_id='linked',revision=3)],
            requests=4,revisions=4),'Consumer history contains extra or invalid revisions')
    case.check('consumer-undo-retry',undo_retry)
    for name,frames in (('original',old_frames*2),('revised',new_frames+old_frames),('undone',old_frames*2)):
        case.check(name+'-timeline',lambda n=name,f=frames:check_decoded(movies[n],[over_black(v) for v in f]))
    def old_source():
        revision('historical-source.json',0)
        require(receipts['create']['document']==original==historical,'Original Inkbolt revision changed')
    case.check('old-source-history',old_source)
    case.check('immutable-deliveries',lambda:check_delivery_preservation(case,observed['delivery_files'],required_files,12))
    case.check('history-valid',lambda:require(history['valid'] and history['revision']==current['revision']==current['current_revision']==1 and
        receipts['create']['receipt']['revision']==0 and receipts['move']['receipt']['from_revision']==0 and
        current['state_sha256']==receipts['move']['receipt']['state_sha256'] and
        receipts['create']['resources']==receipts['move']['resources']==current['resources'],'Invalid, extra or different source history'))
    def processes():
        require(report['memory_complete'] and report['tools']==case.consumer.identities and case.consumer.unchanged() and
            report['commands']==len(report['calls'])==len(records) and report['commands']>0,'Missing consumer process accounting')
        for row in report['calls']:
            returned_error=row['status']=='failure' and isinstance(row.get('engine_error'),dict) and records[row['step']]['response'].get('ok') is False
            require(row['phase']=='task' and (row['status'] in ('success','expected_error') or returned_error) and row['memory_available'] and
                row['active_processes']==0 and row['processes']>=1 and row['peak_tree_commit_bytes']>0 and
                row['peak_process_commit_bytes']>0 and row['step'] in records,'Incomplete observed consumer process lifetime')
            request=records[row['step']]['request']
            raw=json.dumps(request,separators=(',',':')).encode()
            require(row['request_sha256']==sha(raw) and row['request_bytes']==len(raw),'Consumer request identity differs')
        require(report['peak_tree_commit_bytes']==max(r['peak_tree_commit_bytes'] for r in report['calls']) and
            report['request_bytes']==sum(r['request_bytes'] for r in report['calls']) and
            report['response_bytes']==sum(r['response_bytes'] for r in report['calls']) and
            report['roundtrip_seconds']==sum(r['seconds'] for r in report['calls']) and
            report['retries']==sum(r['retry_of'] is not None for r in report['calls']),
            'Consumer summary differs from its measured calls')
        require(all(r['status']=='success' and r['memory_available'] for r in case.consumer.result()['judge_calls']),
            'Independent consumer queries failed')
    case.check('consumer-processes',processes)


def judge(case):judge_retained(case,**durable_inputs(case))
