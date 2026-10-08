"""Create an original 26-cell editable blend chart with preserved source pixels."""
import argparse
import json
from pathlib import Path
from mask_workflow import invoke


MODES=('normal multiply screen darken lighten color_burn color_dodge overlay '
       'hard_light soft_light difference exclusion hue saturation color luminosity '
       'linear_burn linear_dodge vivid_light linear_light pin_light hard_mix '
       'subtract divide darker_color lighter_color').split()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    output=parser.parse_args().output.resolve();output.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        with (output/name).open('x',encoding='utf8',newline='\n') as f:f.write(json.dumps(value,indent=2)+'\n')
    def publish(name,d):
        for fmt,extension in [('snapshot','json'),('png','png')]:
            save(name+'-'+fmt+'-receipt.json',invoke('document.publish',document=d,output=dict(output_root=str(output),file_name=name+'.'+extension,format=fmt)))
    def layer(id,parent,colors):
        return dict(id=id,parent=parent,content=dict(type='raster',width=24,height=24,rgba_hex=bytes(v for p in colors for v in p).hex()))
    background=[[20+8*x,30+9*y,90,96 if (x+y)%7==0 else 255] for y in range(24) for x in range(24)]
    source=[[220,60+7*x,20+10*y,0 if (x-12)**2+(y-12)**2>100 else 128 if x<12 else 255] for y in range(24) for x in range(24)]
    operations=[];cells=[]
    for i,mode in enumerate(MODES):
        x,y=(i%13)*26,(i//13)*26;id=f'cell{i}'
        group=dict(id=id,name=mode,transform=[1,0,0,1,x,y],content=dict(type='group'))
        b=layer(id+'-back',id,background);s=layer(id+'-source',id,source);s['opacity']=.625
        operations += [dict(op='add',item=item) for item in (group,b,s)]
        cells.append(dict(mode=mode,source_id=s['id'],x=x,y=y,width=24,height=24))
    d=invoke('document.create',id='blend-chart',kind='raster',width=338,height=52)
    # Keep each atomic setup batch within the public 64-operation bound.
    before=d
    for start in range(0,len(operations),63):
        before=invoke('document.edit',document=before,expected_revision=before['revision'],operations=operations[start:start+63])['document']
    save('original.json',before);publish('before',before)
    edited=invoke('document.edit',document=before,expected_revision=before['revision'],operations=[dict(op='properties',id=c['source_id'],blend=c['mode']) for c in cells])
    save('blend-edit.json',edited);publish('blends',edited['document']);save('cells.json',cells)
    assert [i['content'] for i in before['items']]==[i['content'] for i in edited['document']['items']]
    assert json.loads((output/'original.json').read_text())==before
    print('Published 26 editable blend cells and preserved originals in '+str(output))


if __name__=='__main__':main()
