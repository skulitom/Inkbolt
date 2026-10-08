"""Publish source-preserving editable dash-phase variations for diagram links."""
import argparse
import copy
import json
from pathlib import Path
from mask_workflow import invoke


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    output=parser.parse_args().output.resolve();output.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        with (output/name).open('x',encoding='utf8',newline='\n') as f:f.write(json.dumps(value,indent=2)+'\n')
    def publish(name,d):
        for fmt,extension in [('snapshot','json'),('png','png'),('svg','svg')]:
            save(name+'-'+fmt+'-receipt.json',invoke('document.publish',document=d,output=dict(output_root=str(output),file_name=name+'.'+extension,format=fmt)))
    d=invoke('document.create',id='dashed-stroke-example',kind='vector',width=64,height=32)
    items=[]
    for i,(array,color) in enumerate([([8,4],[30,100,210,255]),([3,2,1],[30,160,110,192]),([0,3,4,2],[180,80,40,128])]):
        items.append(dict(id=f'link-{i}',content=dict(type='vector',geometry=dict(shape='path',commands=[dict(verb='move',to=[4,8+8*i]),dict(verb='line',to=[60,8+8*i])]),stroke=dict(color=color,width=2,dash=dict(array=array,offset=-2)))))
    original=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=i) for i in items])['document']
    save('original.json',original);publish('before',original)
    operations=[]
    for item in original['items']:
        content=copy.deepcopy(item['content']);content.pop('type');content['stroke']['dash']['offset']=3
        operations.append(dict(op='vector',id=item['id'],**content))
    changed=invoke('document.edit',document=original,expected_revision=original['revision'],operations=operations)['document']
    publish('phased',changed)
    save('diff.json',invoke('document.diff',before=original,after=changed,compare_pixels=True))
    assert json.loads((output/'original.json').read_text())==original
    assert [i['content']['geometry'] for i in original['items']]==[i['content']['geometry'] for i in changed['items']]
    print('Published two editable dash-phase variations in '+str(output))


if __name__=='__main__':main()
