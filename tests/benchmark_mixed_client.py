"""Original synthetic B11 baseline: editable controls and decimal composition."""
from decimal import Decimal as D
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image


def main():
    root=Path(sys.argv[1])
    scene=dict(width=32,height=24,image=dict(file='original.png',sha256=hashlib.sha256((root/'original.png').read_bytes()).hexdigest()),
        group=dict(isolated=True,opacity=.75,mask=dict(file='mask.png',linked=True)),
        art=dict(bounds=[8,6,12,10],fill=[30,150,70,173],fill_opacity=.5,
                 shadow=dict(offset=[5,-1],sigma=0,color=[0,0,0,128])),
        unrelated=dict(bounds=[25,2,4,4],fill=[220,90,30,255]))
    with (root/'editable.json').open('x',encoding='utf-8') as output:json.dump(scene,output)
    with Image.open(root/scene['image']['file']) as image:
        assert image.size==(32,24);source=image.convert('RGBA').tobytes()
    mask=bytes(128 if x<16 else 255 for y in range(24) for x in range(32))
    with (root/'mask.png').open('xb') as output:Image.frombytes('L',(32,24),mask).save(output,format='PNG')
    def premultiplied(color,opacity=D(1)):
        alpha=D(color[3])/255*opacity
        return [D(channel)/255*alpha for channel in color[:3]]+[alpha]
    def over(back,front):return [front[c]+back[c]*(1-front[3]) for c in range(4)]
    def contains(bounds,x,y):
        left,top,width,height=bounds;return left<=x<left+width and top<=y<top+height
    result=bytearray();art=scene['art'];shadow=art['shadow'];top=scene['unrelated']
    for y in range(24):
        for x in range(32):
            index=y*32+x
            layer=[D(0)]*4
            if contains(art['bounds'],x-shadow['offset'][0],y-shadow['offset'][1]):
                layer=premultiplied(shadow['color'],D(art['fill'][3])/255)
            if contains(art['bounds'],x,y):layer=over(layer,premultiplied(art['fill'],D(str(art['fill_opacity']))))
            layer=[v*D(mask[index])/255*D(str(scene['group']['opacity'])) for v in layer]
            color=over(premultiplied(source[index*4:index*4+4]),layer)
            if contains(top['bounds'],x,y):color=over(color,premultiplied(top['fill']))
            result.extend(int(v/color[3]*255+D('.5')) for v in color[:3]);result.append(int(color[3]*255+D('.5')))
    with (root/'preview.png').open('xb') as output:Image.frombytes('RGBA',(32,24),bytes(result)).save(output,format='PNG')


if __name__=='__main__':main()
