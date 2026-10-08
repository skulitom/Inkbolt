"""Original local selection, removal, denoise and upscale workflow with retained sources."""
import base64
import copy
import json
import math
from pathlib import Path
import random
import subprocess
import sys


def document(id,pixels,width,height):
    return dict(schema_version=2,id=id,kind='raster',width=width,height=height,color_space='srgb',items=[dict(id='pixels',content=dict(type='raster',width=width,height=height,rgba_hex=bytes(v for p in pixels for v in p).hex()))])


def main():
    if len(sys.argv)!=3:raise SystemExit('Usage: python examples/pixel_assistance.py PATH_TO_ENGINE NEW_OUTPUT_DIRECTORY')
    engine,output=Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve();output.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        with (output/name).open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    def call(name,command,**values):
        request=dict(command=command,**values);save(name+'-request.json',request)
        p=subprocess.run([str(engine)],input=json.dumps(request).encode(),capture_output=True,check=True);value=json.loads(p.stdout);assert value['ok'],value;save(name+'-response.json',value);return value['result']
    def edit(name,source,op):return call(name,'document.edit',document=source,expected_revision=source['revision'],operations=[op])['document']
    def publish(name,source):
        value=call(name,'document.export',document=source,format='png')
        with (output/(name+'.png')).open('xb') as f:f.write(base64.b64decode(value['data']))
    w,h=24,18;clean=[[40+20*(x%2),70+30*(y%2),100+10*((x+y)%2),255] for y in range(h) for x in range(w)];damaged=copy.deepcopy(clean)
    for y in range(7,11):
        for x in range(10,14):damaged[y*w+x]=[230,20,210,255]
    source=call('object-source','document.validate',document=document('original-object',damaged,w,h));save('object-source.json',source)
    options=dict(foreground=[[11,8]],background=[[0,0],[1,0],[0,1],[1,1]])
    plan=call('select','assist.segment',document=source,id='pixels',options=options)
    masked=edit('mask',source,dict(op='assist_mask',id='pixels',options=options))
    removal=dict(region=dict(x=0,y=0,width=w,height=h,gray_hex=plan['mask']['gray_hex']),action=dict(type='fill',fill=dict(source_id='pixels',patch_radius=2,max_context_rms=0)))
    restored=edit('remove',source,dict(op='repair',id='pixels',options=removal))
    publish('object',source);publish('selected',masked);publish('removed',restored)
    imported=call('asset','asset.import',source_path=str(output/'object.png'),store_root=str(output/'asset-store'))
    asset_source=copy.deepcopy(source);asset_source['assets']={'original':imported['asset']};asset_source['items'][0]['content']=dict(type='image',asset_id='original',width=w,height=h)
    asset_source=call('asset-source','document.validate',document=asset_source);save('asset-source.json',asset_source)
    call('asset-select','assist.segment',document=asset_source,id='pixels',options=options,asset_root=str(output/'asset-store'))
    w,h=32,24;clean_noise=[[50,95,145,255] if x<16 else [185,120,55,255] for y in range(h) for x in range(w)];rng=random.Random(72)
    noisy=[[max(0,min(255,v+rng.randint(-9,9))) for v in p[:3]]+[255] for p in clean_noise]
    noise_source=call('noise-source','document.validate',document=document('original-noise',noisy,w,h));save('noise-source.json',noise_source)
    denoise=dict(region=dict(x=0,y=0,width=w,height=h),action=dict(type='edge_correct',guide_id='pixels',radius=2,range_sigma=.1,max_change_rms=.1))
    corrected=edit('denoise',noise_source,dict(op='repair',id='pixels',options=denoise));publish('noisy',noise_source);publish('denoised',corrected)
    w,h=12,10
    small=[[round(v) for v in [110+45*math.sin(2*math.pi*(x+.5)/w),120+35*math.cos(2*math.pi*(y+.5)/h),50+4*(x+.5)+3*(y+.5),255]] for y in range(h) for x in range(w)]
    small_source=call('small-source','document.validate',document=document('original-smooth-chart',small,w,h));save('small-source.json',small_source)
    enlarged=edit('upscale',small_source,dict(op='canvas',action=dict(type='scale',width=36,height=30,sampling='lanczos3')));publish('small',small_source);publish('upscaled',enlarged)
    for name,value in [('masked.json',masked),('removed.json',restored),('denoised.json',corrected),('upscaled.json',enlarged),('references.json',dict(removal=clean,denoise=clean_noise))]:save(name,value)
    print(json.dumps(dict(output=str(output),selected_pixels=plan['foreground_pixels'],minimum_energy=plan['minimum_energy'],source_preserved=True,models=[])))


if __name__=='__main__':main()
