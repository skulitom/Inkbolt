"""Linked animated graphics, real consumer revisions and independent frame judges."""
import base64
import copy
from fractions import Fraction as F
import json
from pathlib import Path

from benchmark_consumer import Consumer
from benchmark_graphics import ref, source_snapshot, store, png_check
from benchmark_runtime import Trial, require, safe_name
from workload_cases import save, save_json, sha


WIDTH,HEIGHT=32,16
RATE=dict(num=25,den=1)
DURATION=dict(num=2,den=5)
SCHEDULE=(0,0,0,1,1)*2
PROMPT=Path(__file__).with_name('benchmark_prompts')/'B20.md'
PREVIEW_FILES={'revised-preview':'preview.png'}


def original_frames():
    colors=([200,80,30,128],[10,220,70,255],[0,0,0,0],[77,33,22,64])
    first=b''.join(bytes(colors[x//8]) for y in range(HEIGHT) for x in range(WIDTH))
    second=b''.join(bytes([50+x*3,150-y*5,250-x*4,192]) for y in range(HEIGHT) for x in range(WIDTH))
    return first,second


def shifted(raw):
    return b''.join(bytes(16)+raw[y*WIDTH*4:(y*WIDTH+WIDTH-4)*4] for y in range(HEIGHT))


def consumer_rgba(raw):
    # Public straight-alpha scene contract: encoded-sRGB color/matte passes,
    # then nearest-integer unassociation. No consumer/Inkbolt renderer is used.
    result=bytearray()
    for i in range(0,len(raw),4):
        alpha=raw[i+3]
        result.extend([0,0,0] if alpha==0 else [min(255,((v*alpha+127)//255*510+alpha)//(2*alpha)) for v in raw[i:i+3]])
        result.append(alpha)
    return bytes(result)


def over_black(raw):
    result=bytearray()
    for i in range(0,len(raw),4):
        result.extend((v*raw[i+3]+127)//255 for v in raw[i:i+3]);result.append(255)
    return bytes(result)


def check_timestamps(report, count):
    frames=report.get('frames',[])
    require(len(frames)==count, 'Consumer output frame count changed')
    errors=[abs(F(row['best_effort_timestamp_time'])-F(i,25)) for i,row in enumerate(frames)]
    require(max(errors,default=F(0))<=F(1001,1000000), 'Consumer frame clock changed')


def decode_movie(consumer, name, movie):
    common=['-nostdin','-v','error','-i',str(movie)]
    actual=consumer.judge(name+'-rgba','ffmpeg',common+['-map','0:v:0','-f','rawvideo','-pix_fmt','rgba','-'])
    pcm=consumer.judge(name+'-pcm','ffmpeg',common+['-map','0:a:0','-f','s16le','-acodec','pcm_s16le','-'])
    times=consumer.judge(name+'-time','ffprobe',['-v','error','-select_streams','v:0','-show_frames',
        '-show_entries','frame=best_effort_timestamp_time','-of','json',str(movie)])
    stream=consumer.judge(name+'-stream','ffprobe',['-v','error','-show_streams',
        '-show_entries','stream=codec_type,width,height,avg_frame_rate,codec_name,pix_fmt,sample_rate,channels','-of','json',str(movie)])
    return dict(rgba=actual,pcm=pcm,times=json.loads(times),streams=json.loads(stream)['streams'])


def check_decoded(value,frames):
    require(value['rgba']==b''.join(frames),'Consumer decoded pixels/alpha or frame order differ')
    require(len(value['pcm'])==len(frames)*1920*4 and not any(value['pcm']),'Consumer silent audio sample clock changed')
    check_timestamps(value['times'],len(frames));streams=value['streams']
    video=[s for s in streams if s['codec_type']=='video'];audio=[s for s in streams if s['codec_type']=='audio']
    require(len(streams)==2 and len(video)==len(audio)==1 and (video[0]['width'],video[0]['height'])==(WIDTH,HEIGHT)
        and F(video[0]['avg_frame_rate'])==25 and video[0]['codec_name']=='ffv1',
        'Consumer dimensions, rate or lossless codec changed')
    require(audio[0]['codec_name']=='pcm_s16le' and audio[0]['sample_rate']=='48000' and audio[0]['channels']==2,
            'Consumer audio format, rate or channels changed')


def check_movie(consumer,name,movie,frames):check_decoded(decode_movie(consumer,name,movie),frames)


def write_bundle(bundle, root):
    files={}
    for file in bundle['files']:
        name=safe_name(file['path']);require(name not in files,'Duplicate handoff filename')
        raw=base64.b64decode(file['data'],validate=True)
        require(len(raw)==file['bytes'] and sha(raw)==file['sha256'],'Handoff file identity differs')
        files[name]=raw
    pin=bundle['handoff'];manifest=pin['manifest'];manifest_file=bundle['manifest_file']
    scene=json.loads(files[manifest['scene']['path']])
    root.mkdir()
    for name in [n for n in files if n!=manifest_file['path']]+[manifest_file['path']]:save(root/name,files[name])
    return scene,{str(root/name):sha(raw) for name,raw in files.items()}


class HandoffTrial(Trial):
    def __init__(self,*args,consumer_tools=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.consumer_tools=consumer_tools or {};self.consumer=None;self.consumer_checked=False;self.delivery_hashes={}

    def begin(self,prompt):
        self.consumer=Consumer(self.root/'consumer',self.consumer_tools,self.timeout)
        super().begin(prompt)

    def observe_delivery(self,identities):
        for name,digest in identities.items():
            relative=Path(name).relative_to(self.root).as_posix()
            require(relative not in self.delivery_hashes,'Delivery was already observed')
            self.delivery_hashes[relative]=digest

    def begin_judging(self):
        super().begin_judging()
        save_json(getattr(self,'judge_root',self.root)/'handoff-observations.json',dict(schema_version=1,
            consumer=self.consumer.result(),records=copy.deepcopy(self.consumer.records),delivery_files=self.delivery_hashes))
        self.consumer.phase='judge'

    def close(self):
        super().close()
        if self.consumer is not None and not self.consumer_checked:
            self.consumer_checked=True
            try:require(self.consumer.unchanged(),'Consumer executables changed during the task')
            except Exception as error:self.error=self.error or f'{type(error).__name__}: {error}'
            save_json(self.root/'consumer-report.json',self.consumer.result())

    def extra_results(self):
        consumer=self.consumer.result() if self.consumer is not None else None
        calls=[r for r in self.calls if r['phase']!='judge']
        traffic=[r for r in (self.calls if self.transport=='cli' else self.protocol) if r['phase']!='judge']
        return dict(consumer=consumer,total_engine_commands=len(calls)+(consumer['commands'] if consumer else 0),
            total_engine_retries=sum(r['retry_of'] is not None for r in calls)+(consumer['retries'] if consumer else 0),
            total_request_bytes=sum(r.get('request_bytes',0) for r in traffic)+(consumer['request_bytes'] if consumer else 0),
            total_response_bytes=sum(r.get('response_bytes',0) for r in traffic)+(consumer['response_bytes'] if consumer else 0),
            total_engine_roundtrip_seconds=sum(r.get('seconds',0) for r in traffic)+(consumer['roundtrip_seconds'] if consumer else 0),
            consumer_peak_tree_commit_bytes=consumer['peak_tree_commit_bytes'] if consumer else None)


def fixture(case):
    first,second=original_frames()
    case.source('original.rgba',first+second)


def solve(case):
    first,second=original_frames()
    consumer=case.consumer
    doc=case.call('create','document.create',id='linked-graphic',kind='raster',width=WIDTH,height=HEIGHT)
    items=[dict(id=name,content=dict(type='raster',width=WIDTH,height=HEIGHT,rgba_hex=raw.hex()))
           for name,raw in [('art',first),('other',second)]]
    doc=case.call('animate','document.edit',document=doc,expected_revision=0,operations=[
        *[dict(op='add',item=item) for item in items],dict(op='sequence_from_layers',ids=['art','other'],
            delay=dict(numerator=2,denominator=25),plays=0)])['document']
    doc['variants']['sequence']['frames'][0]['delay']=dict(numerator=3,denominator=25)
    saved=store(case,doc);before=source_snapshot(case,saved,'before')
    options=dict(link_key='graphic',selection=dict(type='sequence'),duration=DURATION,frame_rate=RATE,
                 timing='strict',end='loop',alpha=dict(type='transparent'))
    def deliver(revision,previous=None):
        name=f'delivery-{revision}'
        bundle=case.call(name,'handoff.export',document=ref(revision),options=options,previous=previous)
        folder=case.root/name;scene,identities=write_bundle(bundle,folder)
        save_json(case.root/(name+'-handoff.json'),bundle['handoff'])
        case.call(name+'-inspect','handoff.inspect',handoff=bundle['handoff'],input_root=name,include_schedule=True)
        consumer.call(name+'-inspect','scene.inspect',scene=scene,input_root=str(folder))
        movie=folder/'compiled.mkv'
        rendered=consumer.call(name+'-compile','scene.render',scene=scene,input_root=str(folder),
            output_root=str(folder),output=str(movie))
        asset=copy.deepcopy(rendered['asset']);asset['id']=f'graphic-r{revision}';asset['path']=name+'/compiled.mkv'
        identities[str(movie)]=sha(movie.read_bytes());case.observe_delivery(identities)
        return bundle['handoff'],asset
    old,old_asset=deliver(0)
    session=dict(store_root=str(case.root/'cutbolt-store'),project_id='linked')
    (case.root/'cutbolt-store').mkdir()
    consumer.call('create','session.create',store_root=session['store_root'],id='linked',width=WIDTH,height=HEIGHT,
        frame_rate=RATE,request_id='create')
    def edit(op,**fields):return dict(op='tracks.edit',edit=dict(op=op,**fields))
    def clip(ident,asset,start):return dict(id=ident,asset_id=asset['id'],start=start,source_in=dict(num=0,den=1),duration=DURATION)
    original=consumer.call('initial','session.apply',**session,request_id='initial',expected_revision=0,operations=[
        dict(op='media.add',asset=old_asset),edit('create',duration=dict(num=4,den=5)),
        edit('add',track=dict(id='overlay',kind='video',locked=False,enabled=True,composite='alpha_over',clips=[])),
        edit('place',track_id='overlay',clip=clip('graphic',old_asset,dict(num=0,den=1)),collision='reject'),
        edit('place',track_id='overlay',clip=clip('unrelated',old_asset,DURATION),collision='reject')])
    def snapshot(step,revision=None):
        result=consumer.call(step,'session.get',**session,**({} if revision is None else dict(revision=revision)))
        value=result.get('project',result);save_json(case.root/(step+'.json'),value);return value
    timeline_before=snapshot('timeline-before',original['revision'])
    action=dict(type='edit',operations=[dict(op='transform',id='art',matrix=[1,0,0,1,4,0])])
    proposed=case.call('review','session.dry_run',session_id='work',request_id='move',expected_revision=0,
        action=action,options=dict(include_document=True))
    save_json(case.root/'review.json',proposed)
    case.call('commit','session.apply_proposal',proposal=proposed['proposal'],action=action,response_mode='compact')
    after=source_snapshot(case,ref(1),'after')
    preview=case.call('preview','document.preview',document=ref(1),options={},preview=True)
    save(case.root/'preview.png',base64.b64decode(preview['artifact']['data'],validate=True))
    _,new_asset=deliver(1,old)
    snapshot('before-relink')
    operations=[dict(op='media.add',asset=new_asset),edit('remove',clip_ids=['graphic'],links='reject_partial'),
        edit('place',track_id='overlay',clip=clip('graphic',new_asset,dict(num=0,den=1)),collision='reject')]
    attempts={};attempts['review']=consumer.call('review-relink','session.preview',**session,expected_revision=original['revision'],operations=operations)
    snapshot('after-review')
    changed=consumer.call('relink','session.apply',**session,request_id='relink',expected_revision=original['revision'],operations=operations)
    timeline_after=snapshot('timeline-after',changed['revision'])
    snapshot('historical',original['revision'])
    attempts['stale']=consumer.call('stale','session.apply',**session,request_id='stale',expected_revision=original['revision'],
        operations=operations,expected_error='REVISION_CONFLICT')
    undone=consumer.call('undo','session.undo',**session,request_id='undo',expected_revision=changed['revision'])
    restored=snapshot('restored',undone['revision'])
    replay=consumer.call('retry','session.apply',**session,request_id='relink',expected_revision=original['revision'],
        operations=operations,retry_of='relink')
    snapshot('after-retry');attempts.update(initial=original,relink=changed,undo=undone,retry=replay)
    save_json(case.root/'consumer-attempts.json',attempts)
    for name,project in [('original',timeline_before),('revised',timeline_after),('undone',restored)]:
        movie=case.root/(name+'.mkv')
        consumer.call(name+'-render','render.run',project=project,input_root=str(case.root),output_root=str(case.root),output=str(movie))
    case.call('old-inspect','handoff.inspect',handoff=old,input_root='delivery-0')
    source_snapshot(case,saved,'historical-source')
    case.call('verify-history','session.verify',session_id='work')


def judge(case):
    from benchmark_handoff_judge import judge as independent_judge
    independent_judge(case)


def linked_graphic(case):
    fixture(case);case.begin(PROMPT.read_text(encoding='utf-8'));solve(case);case.begin_judging();judge(case)
