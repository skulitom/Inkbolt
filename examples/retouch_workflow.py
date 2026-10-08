"""Clone and heal an original synthetic image without modifying its input snapshot."""
import argparse
import copy
import json
from pathlib import Path
from mask_workflow import invoke


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        with (out/name).open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    def publish(name,d):
        for fmt,ext in [('snapshot','json'),('png','png'),('tiff','tif')]:
            save(name+'-'+fmt+'-receipt.json',invoke('document.publish',document=d,output=dict(output_root=str(out),file_name=name+'.'+ext,format=fmt)))
    w,h=56,40
    source=[[50+2*x+((x+y)%5)*4,45+3*y,70+(x*3+y*7)%60,255] for y in range(h) for x in range(w)]
    clean=[[r+30,g+20,b+10,a] for r,g,b,a in source];target=copy.deepcopy(clean)
    region=dict(x=20,y=14,width=12,height=10)
    for y in range(14,24):
        for x in range(20,32):target[y*w+x]=[230,25,45,255]
    save('original-fixture.json',dict(width=w,height=h,source=source,target=target,clean=clean))
    d=invoke('document.create',id='original-retouch-source',kind='raster',width=w,height=h)
    items=[dict(id=id,visible=id=='pixels',content=dict(type='raster',width=w,height=h,rgba_hex=bytes(v for c in pixels for v in c).hex())) for id,pixels in [('pixels',target),('source',source)]]
    d=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=i) for i in items])['document'];publish('source',d)
    modes=[('clone',dict(source_id='source',region=region,mode=dict(type='clone'),source_transform=[1,0,0,1,-12.25,.25])),('heal',dict(source_id='source',region=region,mode=dict(type='heal'))),('soft-heal',dict(source_id='source',region=dict(**region,gray_hex=bytes(96 if x in [0,11] or y in [0,9] else 255 for y in range(10) for x in range(12)).hex()),mode=dict(type='heal',screening=.4),opacity=.75))]
    for name,options in modes:
        save(name+'-options.json',options)
        result=invoke('document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='retouch',id='pixels',options=options)])
        save(name+'-edit.json',result);publish(name,result['document'])
    assert all(d['items'][j]['content']['rgba_hex']==item['content']['rgba_hex'] for j,item in enumerate(items))
    print('Saved preserved input, original fixture, clone/heal settings, measured boundaries and lossless exports in '+str(out))


if __name__=='__main__':main()
