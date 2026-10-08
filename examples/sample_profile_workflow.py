"""Show explicit source profile assignment and conversion on an original float chart."""
import argparse
import json
from pathlib import Path
import struct
from mask_workflow import invoke


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        with (out/name).open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    def publish(name,d):
        save(name+'.json',d)
        for fmt in ['png','snapshot']:
            receipt=invoke('document.publish',document=d,output=dict(output_root=str(out),file_name=name+'.'+('snapshot.json' if fmt=='snapshot' else fmt),format=fmt))
            save(name+'-'+fmt+'-receipt.json',receipt)
    w,h=48,32;values=[v for y in range(h) for x in range(w) for v in (x/(w-1),y/(h-1),(.2 if (x//8+y//8)%2 else .8),1.)]
    source=invoke('document.create',id='profile-example',kind='raster',width=w,height=h)
    item=dict(id='pixels',content=dict(type='samples',grid=dict(width=w,height=h,depth='f32',channels='rgba',data_hex=struct.pack('<'+'f'*len(values),*values).hex())))
    source=invoke('document.edit',document=source,expected_revision=0,operations=[dict(op='add',item=item)])['document'];publish('source',source)
    for name,action in [('assigned-linear',dict(type='assign',profile=dict(type='builtin',name='linear_srgb'))),('converted-linear',dict(type='convert',profile=dict(type='builtin',name='linear_srgb'),intent='relative_colorimetric'))]:
        request=dict(document=source,expected_revision=source['revision'],operations=[dict(op='sample_profile',id='pixels',action=action)])
        save(name+'-request.json',dict(command='document.edit',**request));result=invoke('document.edit',**request);save(name+'-response.json',result);publish(name,result['document'])
        changed=result['document']['items'][0]['content']['grid']['data_hex']!=source['items'][0]['content']['grid']['data_hex']
        assert changed==(action['type']=='convert')
    print('Saved source, assigned and converted charts, exact retained samples, snapshots and PNG deliveries in '+str(out))


if __name__=='__main__':main()
