"""Original synthetic no-Inkbolt B20 author; the common consumer compiles video."""
import copy
import json
from pathlib import Path
import subprocess

from benchmark_baseline_handoff import manifest
from workload_cases import save_json,sha


AUTHOR='''from PIL import Image
from pathlib import Path
import json,sys
root=Path(sys.argv[1]);raw=(root/'original.rgba').read_bytes()
for revision in (0,1):
 folder=root/('delivery-'+str(revision));folder.mkdir()
 doc=json.loads((root/('before.json' if revision==0 else 'after.json')).read_bytes())
 for index,row in enumerate(doc['frames']):
  source=Image.frombytes('RGBA',(32,16),raw[index*2048:(index+1)*2048]);image=Image.new('RGBA',(32,16))
  image.paste(source,tuple(row['offset']));image.save(folder/('frame-'+str(index)+'.png'))
  if revision==1 and index==0:image.save(root/'preview.png')
'''


def solve_baseline(root,tools,call):
    root=Path(root);digest=sha((root/'original.rgba').read_bytes());before=manifest(digest);after=manifest(digest,4)
    save_json(root/'before.json',before);save_json(root/'after.json',after)
    save_json(root/'review.json',dict(base_sha256=sha((root/'before.json').read_bytes()),action=dict(frame='art',translate=[4,0]),
        proposed_sha256=sha((root/'after.json').read_bytes())))
    generated=subprocess.run([tools['python']['path'],'-I','-c',AUTHOR,str(root)],capture_output=True,timeout=30)
    assert generated.returncode==0,generated.stderr
    rate=dict(num=25,den=1);duration=dict(num=2,den=5);assets=[]
    for revision,doc in enumerate((before,after)):
        folder=root/f'delivery-{revision}';save_json(folder/'source.json',doc)
        def identity(name):
            raw=(folder/name).read_bytes();return dict(path=name,bytes=len(raw),sha256=sha(raw))
        frames=[dict(anchor=[0,0],offset=[0,0],hold=dict(num=3-i,den=25),image=identity(f'frame-{i}.png')) for i in range(2)]
        scene=dict(schema_version=1,id='graphic',width=32,height=16,duration=duration,frame_rate=rate,transparent=True,
            color='srgb_straight_encoded',background=[0,0,0],audio=None,output_scale=1,
            layers=[dict(id='graphic',alpha_mode='straight',canvas=[32,16],start=dict(num=0,den=1),duration=duration,end='loop',
                frames=frames,timing='strict',transform=dict(crop=[0,0,32,16],opacity=255,position=[0,0],quarter_turns=0,scale=1))])
        save_json(folder/'scene.json',scene)
        save_json(root/f'delivery-{revision}-handoff.json',dict(schema_version=1,source=identity('source.json'),scene=identity('scene.json'),
            frames=[dict(hold=row['hold'],image=row['image']) for row in frames],duration=duration,frame_rate=rate))
        call(f'delivery-{revision}-inspect','scene.inspect',scene=scene,input_root=str(folder))
        value=call(f'delivery-{revision}-compile','scene.render',scene=scene,input_root=str(folder),output_root=str(folder),output=str(folder/'compiled.mkv'))
        asset=value['asset'];asset['id']=f'graphic-r{revision}';asset['path']=f'delivery-{revision}/compiled.mkv';assets.append(asset)
    def clip(name,asset,start):return dict(id=name,asset_id=asset['id'],start=start,source_in=dict(num=0,den=1),duration=duration)
    original=dict(schema_version=1,id='linked',revision=1,width=32,height=16,frame_rate=rate,assets=[assets[0]],clips=[],
        tracks=dict(duration=dict(num=4,den=5),links=[],tracks=[dict(id='overlay',kind='video',locked=False,enabled=True,
            composite='alpha_over',clips=[clip('graphic',assets[0],dict(num=0,den=1)),clip('unrelated',assets[0],duration)])]))
    revised=copy.deepcopy(original);revised['revision']=2;revised['assets'].append(assets[1]);revised['tracks']['tracks'][0]['clips'][0]['asset_id']=assets[1]['id']
    for name,project in (('original',original),('revised',revised)):
        save_json(root/('timeline-before.json' if name=='original' else 'timeline-after.json'),project)
        call(name+'-render','render.run',project=project,input_root=str(root),output_root=str(root),output=str(root/(name+'.mkv')))
