"""Create a labeled original diagram using an explicitly supplied licensed local font.
All output is create-only in a fresh directory; the source font and license stay unchanged.
"""
import argparse
import base64
import json
from pathlib import Path
import subprocess


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--font',type=Path,required=True);p.add_argument('--license',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    root=Path(__file__).resolve().parents[1];exe=root/'target/debug/inkbolt.exe'
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    def call(**request):
        process=subprocess.run([str(exe)],input=json.dumps(request).encode(),capture_output=True,check=False)
        data=json.loads(process.stdout)
        if not data['ok']:raise RuntimeError(data['error'])
        return data['result']
    font=call(command='font.import',source_path=str(args.font.resolve()),license_path=str(args.license.resolve()),store_root=str(output/'fonts'))
    d=call(command='document.create',id='agent-diagram',kind='vector',width=640,height=360)
    operations=[dict(op='font_put',id='studio',font=font)]
    def shape(id,g,fill,stroke=None):
        operations.append(dict(op='add',item=dict(id=id,content=dict(type='vector',geometry=g,fill=fill,stroke=stroke))))
    def rect(id,x,y,w,h,fill):shape(id,dict(shape='rect',x=x,y=y,width=w,height=h),fill)
    def label(id,text,x,y,w,size,color):
        operations.append(dict(op='add',item=dict(id=id,transform=[1,0,0,1,x,y],content=dict(type='text',frame=dict(text=text,width=w,height=size*1.5,style=dict(font_id='studio',size=size,fill=color))))))
    navy=[15,23,35,255];cream=[238,242,228,255];muted=[157,174,187,255];lime=[195,238,107,255]
    rect('background',0,0,640,360,navy);rect('accent',32,30,30,4,lime)
    label('heading','Graphics, by agents.',32,52,576,38,cream)
    for n,(x,title) in enumerate([(32,'Plan'),(232,'Draw'),(432,'Refine')],1):
        rect(f'card-{n}',x,141,176,138,[27,39,54,255])
        label(f'number-{n}',f'0{n}',x+16,154,36,11,muted)
        label(f'title-{n}',title,x+16,229,144,23,cream)
    for i,w in enumerate([56,42,64]):rect(f'plan-line-{i}',50,185+i*9,w,3,lime)
    shape('draw-orbit',dict(shape='ellipse',cx=280,cy=197,rx=22,ry=13),None,dict(color=lime,width=2))
    shape('draw-center',dict(shape='ellipse',cx=280,cy=197,rx=5,ry=5),lime)
    shape('refine-check',dict(shape='path',commands=[dict(verb='move',to=[451,197]),dict(verb='line',to=[464,209]),dict(verb='line',to=[485,183])]),None,dict(color=lime,width=3,cap='round',join='round'))
    for x in [214,414]:
        shape(f'arrow-{x}',dict(shape='path',commands=[dict(verb='move',to=[x,202]),dict(verb='line',to=[x+10,202]),dict(verb='move',to=[x+5,197]),dict(verb='line',to=[x+10,202]),dict(verb='line',to=[x+5,207])]),None,dict(color=muted,width=1.5))
    label('footer','Editable. Inspectable. Local.',32,308,500,13,muted)
    d=call(command='document.edit',document=d,expected_revision=0,operations=operations)['document']
    for fmt in ['png','svg','snapshot']:
        result=call(command='document.export',document=d,format=fmt,font_root=str(output/'fonts'))
        path=output/('diagram.'+('json' if fmt=='snapshot' else fmt))
        with path.open('xb') as f:f.write(base64.b64decode(result['data']) if result['encoding']=='base64' else result['data'].encode())
    inspected={item['id']:call(command='text.inspect',document=d,id=item['id'],font_root=str(output/'fonts')) for item in d['items'] if item['content']['type']=='text'}
    (output/'text-inspection.json').write_text(json.dumps(inspected,indent=2)+'\n',encoding='utf8')
    print('Created editable diagram, PNG, SVG, text measurements and pinned fonts in '+str(output))


if __name__=='__main__':main()
