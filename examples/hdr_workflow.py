"""Original signed radiance chart, reversible exposure and explicit display views."""
import argparse
import copy
import json
from pathlib import Path
import struct
from mask_workflow import invoke


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        with (out/name).open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    def publish(d,name,format,**kw):
        save(name+'-receipt.json',invoke('document.publish',document=d,output=dict(output_root=str(out),file_name=name,format=format,**kw)))
    d=invoke('document.create',id='radiance-chart',kind='raster',width=96,height=32)
    d['color_space']='linear_srgb'
    values=[v for y in range(32) for x in range(96) for v in [(x-8)/8,(y+1)/4,((x+y)%32)/2,1]]
    d['items']=[dict(id='pixels',content=dict(type='samples',grid=dict(width=96,height=32,depth='f32',channels='rgba',encoding='linear_srgb',data_hex=struct.pack('<'+'f'*len(values),*values).hex())))]
    d=invoke('document.validate',document=d);source=copy.deepcopy(d);publish(d,'original.json','snapshot')
    edited=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='hdr_grade',id='pixels',grade=dict(exposure=-1,gain=[1,.75,1]))])
    save('grade-receipt.json',edited);d=edited['document'];publish(d,'graded.json','snapshot')
    publish(d,'radiance.tiff','tiff',image_options=dict(depth='f32',compression='deflate'))
    for method in ['clip','reinhard']:publish(d,method+'.png','png',render_options=dict(view=dict(tone_map=method)))
    save('measurement.json',invoke('sample.measure',document=d,points=[[0,0],[48,16],[95,31]]))
    assert source['items'][0]['content']==d['items'][0]['content']
    print('Saved retained radiance, reversible grade, native float TIFF and explicit display views in '+str(out))


if __name__=='__main__':main()
