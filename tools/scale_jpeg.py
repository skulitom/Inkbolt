"""External pinned JPEG fixture/oracle worker; no Inkbolt implementation imports."""
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import sys
from PIL import Image, __version__


def main():
    if __version__!='10.3.0':raise ValueError('Scale-v2 requires external Pillow 10.3.0')
    root=Path(sys.argv[1]);w,h=map(int,sys.argv[2:4])
    if w<1 or h<1 or w*h>24_000_000:raise ValueError('Invalid JPEG fixture dimensions')
    # Original analytic studio scene: a textured background, smooth ellipsoids,
    # contact shadows, diffuse light and highlights. No source photograph.
    objects=[(.31,.52,.17,.30,(.03,.21,.27)),(.66,.60,.19,.24,(.65,.12,.025))]
    raw=bytearray(w*h*3)
    horizontal=[(x/w,math.sin(x/17),math.cos(x/43)) for x in range(w)]
    for y in range(h):
        yy=y/h;grain=hashlib.shake_256(b'Inkbolt scale-v2 studio grain '+str(y).encode()).digest(w)
        for x,(xx,fine,broad) in enumerate(horizontal):
            field=.17+.11*(1-yy)+.025*xx+.003*fine+.002*broad
            for cx,cy,rx,ry,_ in objects:
                distance=((xx-cx-.035)/(rx*1.1))**2+((yy-cy-ry*.92)/(ry*.18))**2
                field*=1-.45*math.exp(-distance*1.8)
            rgb=[field*1.06,field*1.02,field*.98]
            for cx,cy,rx,ry,color in objects:
                nx,ny=(xx-cx)/rx,(yy-cy)/ry;q=nx*nx+ny*ny
                if q>=1:continue
                nz=math.sqrt(1-q)
                diffuse=.18+.8*max(0,-.45*nx-.60*ny+.66*nz)
                highlight=.55*max(0,-.25*nx-.32*ny+.913*nz)**80
                coverage=min(1,(1-q)*min(rx*w,ry*h)/2)
                rgb=[back*(1-coverage)+(base*diffuse+highlight)*coverage for back,base in zip(rgb,color,strict=True)]
            for c,linear in enumerate(rgb):
                linear=max(0,min(1,linear+(grain[x]/255-.5)*.004))
                encoded=12.92*linear if linear<=.0031308 else 1.055*linear**(1/2.4)-.055
                raw[(y*w+x)*3+c]=int(encoded*255+.5)
    image=Image.frombytes('RGB',(w,h),bytes(raw))
    for progressive in (False,True):
        name='progressive' if progressive else 'baseline'
        with (root/(name+'.jpg')).open('xb') as stream:
            image.save(stream,format='JPEG',quality=93,subsampling=0,progressive=progressive)
        with Image.open(root/(name+'.jpg')) as decoded, (root/(name+'.rgba')).open('xb') as stream:
            stream.write(decoded.convert('RGBA').tobytes())
    distribution=importlib.metadata.distribution('Pillow')
    files={str(p):hashlib.sha256(distribution.locate_file(p).read_bytes()).hexdigest()
           for p in distribution.files if not str(p).endswith(('.pyc','.pyo'))}
    identity=dict(pillow_version=__version__,dimensions=[w,h],quality=93,subsampling=0,
        python_sha256=hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
        pillow_files_sha256=hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        source_rgb_sha256=hashlib.sha256(raw).hexdigest(),
        description='Original analytic studio scene; baseline/progressive JPEG; independent pinned decoder; three-code RGB tolerance, exact alpha')
    print(json.dumps(identity))


if __name__=='__main__':main()
