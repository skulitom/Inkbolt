"""Publish original transparent artwork at two sizes with three explicit kernels."""
import argparse
import json
from pathlib import Path
from mask_workflow import invoke


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True,type=Path)
    output=parser.parse_args().output.resolve();output.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        with (output/name).open('x',encoding='utf8',newline='\n') as f:f.write(json.dumps(value,indent=2)+'\n')
    colors=[[35+10*x,30+15*y,200 if (x+y)%2 else 40,255 if 4<=x<12 and 4<=y<8 else 160] if 2<=x<14 and 2<=y<10 else [220,30,170,0] for y in range(12) for x in range(16)]
    d=invoke('document.create',id='reconstruction-example',kind='raster',width=16,height=12)
    d=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=dict(id='artwork',content=dict(type='raster',width=16,height=12,rgba_hex=bytes(v for p in colors for v in p).hex())))])['document']
    save('original.json',d)
    def publish(name,document):
        for fmt,extension in [('snapshot','json'),('png','png')]:
            save(name+'-'+fmt+'-receipt.json',invoke('document.publish',document=document,output=dict(output_root=str(output),file_name=name+'.'+extension,format=fmt)))
    publish('before',d)
    for method in ('area','bicubic','lanczos3'):
        for label,w,h in [('small',5,4),('large',32,24)]:
            result=invoke('document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='canvas',action=dict(type='scale',width=w,height=h,sampling=method))])
            name=method+'-'+label;save(name+'-edit.json',result)
            assert result['document']['items'][0]['content']['rgba_hex']==d['items'][0]['content']['rgba_hex']
            publish(name,result['document'])
    assert json.loads((output/'original.json').read_text())==d
    print('Published area, bicubic and Lanczos3 size comparisons with immutable source artwork in '+str(output))


if __name__=='__main__':main()
