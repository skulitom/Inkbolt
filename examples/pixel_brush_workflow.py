"""Original native-pixel strokes, preserved sources and four-mode image delivery."""
import argparse
import json
from pathlib import Path
from mask_workflow import invoke


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        with (out/name).open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    def publish(name,d):
        for format,extension in [('snapshot','json'),('png','png'),('tiff','tif')]:
            save(name+'-'+format+'-receipt.json',invoke('document.publish',document=d,output=dict(output_root=str(out),file_name=name+'.'+extension,format=format)))
    w,h=64,48;rgba=bytes(v for y in range(h) for x in range(w) for v in ([20+3*x,40+3*y,180,224] if 8<=x<56 and 8<=y<40 else [0,0,0,0]))
    d=invoke('document.create',id='original-brush-source',kind='raster',width=w,height=h)
    d=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=dict(id='pixels',content=dict(type='raster',width=w,height=h,rgba_hex=rgba.hex())))])['document'];publish('source',d)
    modes=[('paint',dict(type='paint',color=[230,50,30,192])),('erase',dict(type='erase')),('smudge',dict(type='smudge',border='transparent')),('mixer',dict(type='mixer',color=[240,180,30,224],pickup=.35,load=.15))]
    for name,mode in modes:
        stroke=dict(points=[dict(point=[8,24],size=.4,opacity=.5),dict(point=[32,12],size=1,opacity=1),dict(point=[56,28],size=.6,opacity=.75)],diameter=12,hardness=.4,spacing=.35,flow=.65,opacity=.8,scatter=.2,seed=11,texture=dict(width=2,height=2,gray_hex='80ffbf40',origin=[-.5,0],scale=[2,2]),mode=mode)
        save(name+'-stroke.json',stroke);save(name+'-inspection.json',invoke('brush.inspect',stroke=stroke,include_dabs=True))
        edited=invoke('document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='brush_stroke',id='pixels',stroke=stroke)])
        save(name+'-edit.json',edited);publish(name,edited['document'])
    assert d['items'][0]['content']['rgba_hex']==rgba.hex()
    print('Saved original pixels, stroke parameters, inspections, edit receipts and lossless deliveries in '+str(out))


if __name__=='__main__':main()
