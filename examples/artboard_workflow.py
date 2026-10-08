"""Create original landscape, portrait and icon artboards with explicit licensed fonts."""
import argparse
import base64
import json
from pathlib import Path
import subprocess


def main():
    p=argparse.ArgumentParser();p.add_argument('--font',type=Path,required=True);p.add_argument('--license',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    root=Path(__file__).resolve().parents[1];exe=root/'target/debug/inkbolt.exe'
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    def call(**request):
        process=subprocess.run([str(exe)],input=json.dumps(request).encode(),capture_output=True,check=False)
        response=json.loads(process.stdout)
        if not response['ok']:raise RuntimeError(response['error'])
        return response['result']
    def save(path,artifact):
        with path.open('xb') as f:f.write(base64.b64decode(artifact['data']) if artifact['encoding']=='base64' else artifact['data'].encode())
    font=call(command='font.import',source_path=str(args.font.resolve()),license_path=str(args.license.resolve()),store_root=str(output/'fonts'))
    d=call(command='document.create',id='artboard-studio',kind='vector',width=1100,height=624)
    ops=[dict(op='font_put',id='studio',font=font)]
    navy=[15,23,35,255];cream=[238,242,228,255];muted=[157,174,187,255];lime=[195,238,107,255]
    def add(id,parent,content,x=0,y=0,name=''):
        ops.append(dict(op='add',item=dict(id=id,name=name,parent=parent,transform=[1,0,0,1,x,y],content=content)))
    def shape(id,parent,g,fill=None,stroke=None):add(id,parent,dict(type='vector',geometry=g,fill=fill,stroke=stroke))
    def label(id,parent,text,x,y,w,size,color):add(id,parent,dict(type='text',frame=dict(text=text,width=w,height=size*1.5*(1+text.count('\n')),style=dict(font_id='studio',size=size,fill=color))),x,y)
    def icon(id,parent,n,x,y):
        if n==0:
            for k,w in enumerate([56,42,64]):shape(f'{id}-{k}',parent,dict(shape='rect',x=x,y=y+k*9,width=w,height=3),lime)
        elif n==1:
            shape(id,parent,dict(shape='ellipse',cx=x+30,cy=y+9,rx=22,ry=13),stroke=dict(color=lime,width=2))
            shape(id+'-dot',parent,dict(shape='ellipse',cx=x+30,cy=y+9,rx=5,ry=5),lime)
        else:shape(id,parent,dict(shape='path',commands=[dict(verb='move',to=[x,y+9]),dict(verb='line',to=[x+13,y+21]),dict(verb='line',to=[x+34,y-5])]),stroke=dict(color=lime,width=3,cap='round',join='round'))
    for board,w,h,x,portrait in [('landscape',640,360,32,False),('portrait',360,560,704,True)]:
        add(board,None,dict(type='frame',frame=dict(role='artboard',width=w,height=h,background=navy,bleed=dict(top=8,right=8,bottom=8,left=8),guides=[dict(id='margin',axis='x',position=32)])),x,32,name=board.title()+' / editable layout')
        shape(board+'-accent',board,dict(shape='rect',x=32,y=30,width=30,height=4),lime)
        label(board+'-title',board,'Graphics,\nby agents.' if portrait else 'Graphics, by agents.',32,48,w-64,30 if portrait else 38,cream)
        for n,title in enumerate(['Plan','Draw','Refine']):
            bx,by,cw,ch=(32,155+n*120,296,104) if portrait else (32+n*200,141,176,138)
            card=board+'-card-'+str(n);add(card,board,dict(type='frame',frame=dict(width=cw,height=ch,background=[27,39,54,255])),bx,by)
            label(card+'-number',card,f'0{n+1}',16,10,40,11,muted)
            icon(card+'-icon',card,n,18 if not portrait else 210,46)
            label(card+'-label',card,title,16,47 if portrait else 88,176 if portrait else 144,23,cream)
        label(board+'-footer',board,'Editable. Inspectable. Local.',32,h-50,w-64,13,muted)
        # This owned stripe crosses the trim edge and becomes visible with bleed enabled.
        shape(board+'-bleed',board,dict(shape='rect',x=-8,y=h-12,width=16,height=20),lime)
    add('icon',None,dict(type='frame',frame=dict(role='artboard',width=128,height=128,background=navy)),32,432,name='Icon / standalone')
    icon('icon-mark','icon',2,44,54)
    for start in range(0,len(ops),64):d=call(command='document.edit',document=d,expected_revision=d['revision'],operations=ops[start:start+64])['document']
    context=dict(document=d,font_root=str(output/'fonts'))
    save(output/'contact-sheet.png',call(command='document.export',format='png',**context))
    save(output/'document.json',call(command='document.export',format='snapshot',**context))
    manifests={}
    for fmt in ['png','svg']:
        result=call(command='artboard.export',format=fmt,**context);manifests[fmt]=result
        for entry in result['artifacts']:save(output/(entry['id']+'.'+fmt),entry['artifact'])
    bleed=call(command='artboard.export',format='png',selection=dict(type='range',start=0,end=2),include_bleed=True,**context)
    for entry in bleed['artifacts']:save(output/(entry['id']+'-bleed.png'),entry['artifact'])
    (output/'inspection.json').write_text(json.dumps(call(command='document.inspect',document=d),indent=2)+'\n',encoding='utf8')
    for result in [*manifests.values(),bleed]:
        for entry in result['artifacts']:entry['artifact'].pop('data')
    (output/'export-receipts.json').write_text(json.dumps(dict(trim=manifests,bleed=bleed),indent=2)+'\n',encoding='utf8')
    print('Created three editable artboards, clipped PNG/SVG exports, bleed variants and contact sheet in '+str(output))


if __name__=='__main__':main()
