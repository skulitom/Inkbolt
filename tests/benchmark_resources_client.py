"""Original no-engine resource repair client; preserves the broken store."""
import hashlib
import json
from pathlib import Path
import struct
import sys


def author(root,decoded):
    source=json.loads((root/'source.json').read_bytes());issues=[];repaired=root/'repaired-assets';repaired.mkdir()
    for i in range(2):
        identity='asset-'+str(i);asset=source['assets'][identity];path=root/'broken-assets'/(asset['sha256']+'.rgba8')
        if not path.exists():code='ASSET_MISSING'
        elif hashlib.sha256(path.read_bytes()).hexdigest()!=asset['sha256']:code='ASSET_CORRUPT'
        else:raise AssertionError('Expected a broken resource')
        issues.append(dict(code=code,pointer='/assets/'+identity))
        raw=b'INKRGBA1'+struct.pack('<II',2,2)+decoded[i]
        assert hashlib.sha256(raw).hexdigest()==asset['sha256']
        with (repaired/(asset['sha256']+'.rgba8')).open('xb') as output:output.write(raw)
    values={'editable.json':source,'bindings.json':dict(before='broken-assets',after='repaired-assets'),
            'diagnostics.json':dict(status='fail',issues=issues)}
    for name,value in values.items():
        with (root/name).open('x',encoding='utf-8') as output:json.dump(value,output)
    return source


def main():
    from PIL import Image
    root=Path(sys.argv[1]);decoded=[]
    for i in range(2):
        with Image.open(root/f'original-{i}.png') as image:
            assert image.size==(2,2);decoded.append(image.convert('RGBA').tobytes())
    scene=author(root,decoded);preview=Image.new('RGBA',(16,8))
    for i,item in enumerate(scene['items']):
        tile=Image.frombytes('RGBA',(2,2),decoded[i]);expanded=Image.new('RGBA',(8,8))
        for y in range(8):
            for x in range(8):expanded.putpixel((x,y),tile.getpixel((x//4,y//4)))
        preview.paste(expanded,tuple(item['transform'][4:6]))
    with (root/'preview.png').open('xb') as output:preview.save(output,format='PNG')


if __name__=='__main__':main()
