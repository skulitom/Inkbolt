"""Original layered icon: crop, enlarge, pad, tag resolution, publish and undo."""
import argparse
import json
from pathlib import Path
from mask_workflow import invoke


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True,type=Path)
    output=parser.parse_args().output.resolve();output.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        with (output/name).open('x',encoding='utf8',newline='\n') as f:f.write(json.dumps(value,indent=2)+'\n')
    def pixels(id,width,height,rgba,**kw):
        return dict(id=id,content=dict(type='raster',width=width,height=height,rgba_hex=bytes(v for p in rgba for v in p).hex()),**kw)
    base=[[31,147,219,255] if (x//4+y//4)%2 else [243,168,72,255] for y in range(16) for x in range(24)]
    mark=[[250,250,250,128] if x in (3,4) or y in (3,4) else [0,0,0,0] for y in range(8) for x in range(8)]
    d=invoke('document.create',id='canvas-icon',kind='raster',width=24,height=16)
    d=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=i) for i in [pixels('background',24,16,base),pixels('mark',8,8,mark,transform=[1,0,0,1,8,4])]])['document']
    save('original.json',d)
    common=dict(session_root=str(output/'sessions'),session_id='canvas-icon')
    invoke('session.create',**common,request_id='create',document=d)
    def publish(name,revision):
        for fmt,extension in [('snapshot','json'),('png','png')]:
            save(name+'-'+fmt+'-receipt.json',invoke('session.publish',**common,expected_revision=revision,output=dict(output_root=str(output),file_name=name+'.'+extension,format=fmt)))
    publish('before',0)
    actions=[dict(type='crop',x=4,y=2,width=16,height=12),dict(type='scale',width=80,height=60,sampling='nearest'),dict(type='extent',width=96,height=80,anchor='center'),dict(type='resolution',ppi=150)]
    # A persistent editable clip keeps the chosen window when a later extent
    # edit reveals the document's retained off-canvas artwork.
    operations=[dict(op='group',ids=['background','mark'],new_id='cropped'),dict(op='clip',id='cropped',clip=dict(geometry=dict(shape='rect',x=4,y=2,width=16,height=12)))]
    operations += [dict(op='canvas',action=a) for a in actions]
    save('edit.json',invoke('session.apply',**common,request_id='prepare',expected_revision=0,action=dict(type='edit',label='Prepare framed icon',operations=operations)))
    publish('prepared',1)
    save('difference.json',invoke('session.diff',**common,from_revision=0,to_revision=1))
    save('undo.json',invoke('session.apply',**common,request_id='undo',expected_revision=1,action=dict(type='undo')))
    save('undo-png-receipt.json',invoke('session.publish',**common,expected_revision=2,output=dict(output_root=str(output),file_name='undo.png',format='png')))
    assert (output/'before.png').read_bytes()==(output/'undo.png').read_bytes()
    invoke('session.verify',**common)
    print('Published original and prepared layered icon, canvas edit receipts and exact undo in '+str(output))


if __name__=='__main__':main()
