"""B20 no-Inkbolt artwork, common video artifacts and pinned Pillow judging."""
import subprocess

from benchmark_baseline_mixed import same_controls
from benchmark_diagram import delivered
from benchmark_handoff import (WIDTH,HEIGHT,RATE,DURATION,SCHEDULE,original_frames,shifted,
    consumer_rgba,over_black,decode_movie,check_decoded,check_delivery_preservation)
from benchmark_graphics import png_check
from benchmark_runtime import require,strict_json,safe_name
from benchmark_tasks import ENGINE_CHECKS
from workload_cases import sha


def manifest(digest,offset=0):
    return dict(schema_version=1,width=32,height=16,color_space='srgb',alpha='straight',
        source=dict(file='original.rgba',sha256=digest),selected='art',plays=0,
        frames=[dict(id='art',source_index=0,offset=[offset,0],hold=dict(num=3,den=25)),
            dict(id='other',source_index=1,offset=[0,0],hold=dict(num=2,den=25))])


RENDER='''from PIL import Image
from pathlib import Path
import json,sys
root=Path(sys.argv[1]);document=json.loads((root/'after.json').read_bytes());raw=(root/'original.rgba').read_bytes()
frames=[]
for row in document['frames']:
 source=Image.frombytes('RGBA',(32,16),raw[row['source_index']*2048:(row['source_index']+1)*2048])
 image=Image.new('RGBA',(32,16));image.paste(source,tuple(row['offset']));frames.append(image.tobytes().hex())
print(json.dumps(frames))
'''


def judge_handoff(case,tools):
    require(tools is not None,'B20 baseline requires pinned image tools')
    before=strict_json(delivered(case,'before.json'));after=strict_json(delivered(case,'after.json'))
    original=manifest(case.sources['original.rgba']);wanted=manifest(case.sources['original.rgba'],4)
    # Validate all controls before handing the delivered data to Pillow.
    require(same_controls(before,original) and same_controls(after,wanted),'Baseline source controls or requested edit changed')
    rendered=subprocess.run([tools['python']['path'],'-I','-c',RENDER,str(case.root)],cwd=case.root,timeout=30,capture_output=True)
    require(rendered.returncode==0,'Pinned Pillow could not reconstruct the baseline graphic')
    current=[bytes.fromhex(v) for v in strict_json(rendered.stdout)]
    first,second=original_frames();moved=shifted(first)
    review=strict_json(delivered(case,'review.json'))
    case.check('reviewed-source-only',lambda:require(current==[moved,second] and review==dict(
        base_sha256=sha(delivered(case,'before.json')),action=dict(frame='art',translate=[4,0]),
        proposed_sha256=sha(delivered(case,'after.json'))),'Baseline review or editable source differs'))
    case.check('revised-preview',lambda:png_check(delivered(case,'preview.png'),WIDTH,HEIGHT,current[0]))
    proof=strict_json((case.judge_root/'handoff-observations.json').read_bytes());inventory={}
    old_frames=[consumer_rgba((first,second)[i]) for i in SCHEDULE]
    new_frames=[consumer_rgba((moved,second)[i]) for i in SCHEDULE]
    def delivery(index):
        folder=f'delivery-{index}/';value=strict_json(delivered(case,folder[:-1]+'-handoff.json'))
        require(set(value)=={'schema_version','source','scene','frames','duration','frame_rate'} and value['schema_version']==1 and
            value['duration']==DURATION and value['frame_rate']==RATE and len(value['frames'])==2,'Baseline delivery clock or inventory changed')
        def file(entry):
            require(set(entry)=={'path','bytes','sha256'},'Invalid baseline file identity')
            name=folder+safe_name(entry['path']);raw=delivered(case,name)
            require(len(raw)==entry['bytes'] and sha(raw)==entry['sha256'],'Baseline delivery file differs from its identity')
            inventory[name]=sha(raw);return raw
        require(same_controls(strict_json(file(value['source'])),original if index==0 else wanted),'Editable delivery source changed')
        for row,hold,pixels in zip(value['frames'],(dict(num=3,den=25),dict(num=2,den=25)),(first if index==0 else moved,second),strict=True):
            require(set(row)=={'hold','image'} and row['hold']==hold,'Baseline animation hold changed')
            png_check(file(row['image']),WIDTH,HEIGHT,pixels)
        scene=strict_json(file(value['scene']))
        require(scene['width']==WIDTH and scene['height']==HEIGHT and scene['duration']==DURATION and scene['frame_rate']==RATE and
            scene['transparent'] is True and scene['color']=='srgb_straight_encoded','Baseline scene interpretation changed')
        movie=case.root/(folder+'compiled.mkv');inventory[folder+'compiled.mkv']=sha(delivered(case,folder+'compiled.mkv'))
        check_decoded(decode_movie(case.consumer,'judge-delivery-'+str(index),movie),old_frames if index==0 else new_frames)
    for index in range(2):case.check(f'delivery-{index}-pixels-clock',lambda i=index:delivery(i))
    for name,frames in (('original',old_frames*2),('revised',new_frames+old_frames)):
        case.check(name+'-timeline',lambda n=name,f=frames:check_decoded(decode_movie(case.consumer,'judge-'+n,case.root/(n+'.mkv')),
            [over_black(v) for v in f]))
    case.check('immutable-deliveries',lambda:check_delivery_preservation(case,proof['delivery_files'],inventory,10))
    for name in ENGINE_CHECKS['B20']:
        case.not_applicable(name,'The baseline supplies independently authored files and video artifacts; Inkbolt handoff/session and managed consumer-history guarantees are outside its arm.')
