"""B11 editable layer manifest and independently composed pinned Pillow samples."""
import subprocess

from benchmark_diagram import delivered
from benchmark_graphics import png_check
from benchmark_mixed import original_pixels,mask_samples,mixed_pixels
from benchmark_runtime import require,strict_json


def manifest(source_sha256):
    return dict(width=32,height=24,image=dict(file='original.png',sha256=source_sha256),
        group=dict(isolated=True,opacity=.75,mask=dict(file='mask.png',linked=True)),
        art=dict(bounds=[8,6,12,10],fill=[30,150,70,173],fill_opacity=.5,
                 shadow=dict(offset=[5,-1],sigma=0,color=[0,0,0,128])),
        unrelated=dict(bounds=[25,2,4,4],fill=[220,90,30,255]))


def same_controls(value,expected):
    if isinstance(expected,dict):
        return isinstance(value,dict) and set(value)==set(expected) and all(same_controls(value[k],v) for k,v in expected.items())
    if isinstance(expected,list):
        return isinstance(value,list) and len(value)==len(expected) and all(same_controls(v,e) for v,e in zip(value,expected,strict=True))
    if type(expected) in (int,float):return type(value) in (int,float) and value==expected
    return type(value) is type(expected) and value==expected


def admitted_manifest(case):
    value=strict_json(delivered(case,'editable.json'))
    require(same_controls(value,manifest(case.sources['original.png'])),
            'The editable image, group, mask, vector or effect controls changed beyond the requested offset')
    for name in ('original.png','mask.png'):
        require(len(delivered(case,name))<=64*1024,'A mixed-composition image exceeds its declared delivery bound')
    return value


COMPOSE='''from PIL import Image
from pathlib import Path
import json,sys
root=Path(sys.argv[1]);scene=json.loads((root/'editable.json').read_bytes())
def image(name):
    with Image.open(root/name) as im:
        assert im.format=='PNG' and im.size==(32,24) and getattr(im,'n_frames',1)==1 and im.mode in ('L','RGB','RGBA')
        im.load();return im.convert('RGBA').tobytes()
source=image(scene['image']['file']);mask_rgba=image(scene['group']['mask']['file'])
mask=[]
for at in range(0,len(mask_rgba),4):
    r,g,b,a=mask_rgba[at:at+4];assert r==g==b and a==255;mask.append(r)
art=scene['art'];shadow=art['shadow'];group=scene['group'];unrelated=scene['unrelated']
def inside(bounds,x,y):
    left,top,width,height=bounds;return left<=x<left+width and top<=y<top+height
rendered=bytearray()
for y in range(24):
    for x in range(32):
        i=y*32+x;bg=source[i*4:i*4+4];ba=bg[3]/255
        a=art['fill'][3]/255*art['fill_opacity'] if inside(art['bounds'],x,y) else 0
        sa=art['fill'][3]/255*shadow['color'][3]/255 if inside(art['bounds'],x-shadow['offset'][0],y-shadow['offset'][1]) else 0
        ga=a+sa*(1-a);scale=group['opacity']*mask[i]/255
        alpha=ga*scale+ba*(1-ga*scale)
        color=[(art['fill'][c]/255*a+shadow['color'][c]/255*sa*(1-a))*scale+
               bg[c]/255*ba*(1-ga*scale) for c in range(3)]
        if inside(unrelated['bounds'],x,y):
            ua=unrelated['fill'][3]/255
            color=[unrelated['fill'][c]/255*ua+color[c]*(1-ua) for c in range(3)]
            alpha=ua+alpha*(1-ua)
        rendered.extend(min(255,max(0,int(v/alpha*255+.5))) if alpha else 0 for v in color)
        rendered.append(min(255,max(0,int(alpha*255+.5))))
print(json.dumps(dict(pixels=source.hex(),mask=bytes(mask).hex(),rendered=rendered.hex())))
'''


def decode_and_compose(case,tools):
    result=subprocess.run([tools['python']['path'],'-I','-c',COMPOSE,str(case.root)],
                          cwd=case.root,timeout=30,capture_output=True)
    require(result.returncode==0,'Pinned Pillow could not decode or compose the bounded mixed document')
    value=strict_json(result.stdout)
    require(isinstance(value,dict) and set(value)=={'pixels','mask','rendered'},'Invalid mixed composition response')
    decoded={key:bytes.fromhex(data) for key,data in value.items()}
    require(all(len(data)==(768 if key=='mask' else 3072) for key,data in decoded.items()),'Mixed composition dimensions changed')
    return decoded


def judge_mixed(case,tools):
    # Admission must precede decoding: external paths and unsupported controls
    # must never reach the isolated imaging process, even after a failed check.
    require(case.check('composition-retained',lambda:admitted_manifest(case)),'The mixed composition was not admitted')
    data=decode_and_compose(case,tools)
    case.check('resource-identity',lambda:require(data['pixels']==original_pixels() and data['mask']==mask_samples(),
        'Original image pixels or the retained linked mask changed'))
    def picture():
        expected=mixed_pixels(original_pixels(),(5,-1))
        require(data['rendered']==expected,'Fresh composition differs from the independent rational oracle')
        png_check(delivered(case,'preview.png'),32,24,expected)
    case.check('mixed-pixels',picture)
    case.not_applicable('historical-pixels','The baseline preserves the original PNG and editable controls; this check reopens an Inkbolt saved revision.')
    case.not_applicable('history-valid','Inkbolt session history is unavailable to the no-engine arm.')
