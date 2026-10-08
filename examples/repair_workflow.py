"""Four original repair tasks with preserved inputs and create-only image delivery."""
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
    w,h=40,28;r=dict(x=12,y=9,width=8,height=6)
    clean=[[30+(x%4)*40,50+(y%3)*60,80+((x+y)%3)*30,255] for y in range(h) for x in range(w)]
    damaged=copy.deepcopy(clean)
    for y in range(9,15):
        for x in range(12,20):damaged[y*w+x]=[245,10,210,255]
    cases=[
        ('patch',damaged,clean,clean,dict(region=r,action=dict(type='patch',source_id='source',source_origin=[11,10],search_radius=2,context_radius=1,max_context_rms=0,blend=dict(type='clone')))),
        ('fill',damaged,clean,clean,dict(region=r,action=dict(type='fill',fill=dict(source_id='pixels',patch_radius=1,max_context_rms=0)))),
    ]
    background=[[40,70,110,255] for _ in range(w*h)];object_pixels=copy.deepcopy(background);moved=copy.deepcopy(background)
    for y in range(8,12):
        for x in range(8,13):
            color=[180+(x-8)*12,30+(y-8)*15,70,255];object_pixels[y*w+x]=color;moved[(y+6)*w+x+10]=color
    cases.append(('move',object_pixels,background,moved,dict(region=dict(x=8,y=8,width=5,height=4),action=dict(type='move',offset=[10,6],fill=dict(source_id='pixels',patch_radius=1,max_context_rms=0)))))
    guide=[[220,180,50,255] if x==20 else ([30,60,100,255] if x<20 else [80,170,140,255]) for y in range(h) for x in range(w)]
    noisy=copy.deepcopy(guide)
    for x,y in [(10,6),(20,13),(30,17)]:noisy[y*w+x]=[250,20,220,255]
    cases.append(('edge',noisy,guide,guide,dict(region=dict(x=0,y=0,width=w,height=h),action=dict(type='edge_correct',guide_id='source',radius=2,range_sigma=.04,max_change_rms=1,minimum_effective_samples=2))))
    for name,target,source,expected,options in cases:
        fixture=dict(width=w,height=h,target=target,source=source,expected=expected);save(name+'-fixture.json',fixture)
        d=invoke('document.create',id='original-repair-'+name,kind='raster',width=w,height=h)
        items=[dict(id=id,visible=id=='pixels',content=dict(type='raster',width=w,height=h,rgba_hex=bytes(v for c in pixels for v in c).hex())) for id,pixels in [('pixels',target),('source',source)]]
        d=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=i) for i in items])['document'];publish(name+'-source',d)
        save(name+'-options.json',options);result=invoke('document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='repair',id='pixels',options=options)])
        save(name+'-edit.json',result);publish(name,result['document'])
        assert all(d['items'][j]['content']['rgba_hex']==item['content']['rgba_hex'] for j,item in enumerate(items))
        assert result['document']['items'][0]['content']['rgba_hex']==bytes(v for c in expected for v in c).hex()
    print('Saved four original repair tasks, unchanged inputs, parameters, quality receipts and lossless image/snapshot deliveries in '+str(out))


if __name__=='__main__':main()
