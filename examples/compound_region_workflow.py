"""Keep an original looping curve editable through compound selection and mask edits."""
import argparse
import json
from pathlib import Path
from mask_workflow import invoke


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    output=parser.parse_args().output.resolve();output.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        with (output/name).open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    def edit(name,d,operations):
        request=dict(command='document.edit',document=d,expected_revision=d['revision'],operations=operations);save(name+'-request.json',request)
        response=invoke('document.edit',document=d,expected_revision=d['revision'],operations=operations);save(name+'-response.json',response);return response['document']
    def publish(name,d):
        save(name+'.json',d)
        for fmt,extension in [('png','png'),('snapshot','snapshot.json')]:
            receipt=invoke('document.publish',document=d,output=dict(output_root=str(output),file_name=name+'.'+extension,format=fmt));save(name+'-'+fmt+'-receipt.json',receipt)
    g=dict(shape='path',commands=[dict(verb='move',to=[24,18]),dict(verb='cubic',control1=[8,38],control2=[8,10],to=[24,30]),dict(verb='close')])
    source=invoke('document.create',id='compound-region-example',kind='raster',width=32,height=40)
    source=edit('source',source,[dict(op='add',item=dict(id='curve',name='Original loop',content=dict(type='work_path',geometry=g))),dict(op='add',item=dict(id='corner',content=dict(type='work_path',geometry=dict(shape='rect',x=18,y=24,width=10,height=12)))),dict(op='add',item=dict(id='pixels',content=dict(type='fill',width=32,height=40,paint=[26,139,168,255])))])
    save('source.json',source)
    variants={}
    for mode in ['union','intersection','difference','xor']:
        d=edit(mode,source,[dict(op='work_path_combine',ids=['curve','corner'],new_id='region',mode=mode),dict(op='clip_from_path',id='pixels',path_id='region')]);publish(mode,d);variants[mode]=d
    modified=edit('edited-mask',variants['difference'],[dict(op='path_component',id='pixels',clip=True,component=[0],action=dict(type='handles',command_index=1,control1=[4,34],control2=[4,14]))]);publish('edited-mask',modified)
    selected=edit('selection',variants['xor'],[dict(op='selection_path',id='region')]);save('selection.json',selected)
    print('Saved five editable compound-mask examples, snapshots, source paths and selection receipts in '+str(output))


if __name__=='__main__':main()
