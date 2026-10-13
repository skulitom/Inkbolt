"""Original no-engine overflow repair client for synthetic lifecycle checks."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

FAMILY='Inkbolt Repair Fixture'


def svg(width):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="48" height="32">'
        f'<svg id="label" x="0" y="0" width="{width}" height="24">'
        f'<text x="0" y="16" font-family="{FAMILY}" font-size="20" fill="#145096">AA</text></svg>'
        '<rect id="other" x="32" y="20" width="8" height="8" fill="#1e9646"/></svg>')


def author(root):
    font=(root/'original.ttf').read_bytes();license_data=(root/'font-license.txt').read_bytes()
    tables={}
    for at in range(12,12+16*struct.unpack_from('>H',font,4)[0],16):
        tag,_,offset,length=struct.unpack_from('>4sIII',font,at);tables[tag]=font[offset:offset+length]
    width=2*struct.unpack_from('>H',tables[b'hmtx'],8)[0]*20/struct.unpack_from('>H',tables[b'head'],18)[0]
    assert width==24 and width>12
    scene=dict(schema_version=2,id='repair',kind='vector',width=48,height=32,color_space='srgb',
        fonts=dict(face=dict(sha256=hashlib.sha256(font).hexdigest(),license_sha256=hashlib.sha256(license_data).hexdigest(),face_index=0,bytes=len(font))),
        items=[dict(id='label',content=dict(type='text',frame=dict(text='AA',width=12,height=24,wrap=False,
            style=dict(font_id='face',size=20,fill=[20,80,150,255])))),
            dict(id='other',content=dict(type='vector',geometry=dict(shape='rect',x=32,y=20,width=8,height=8),fill=[30,150,70,255]))])
    repaired=copy.deepcopy(scene);repaired['items'][0]['content']['frame']['width']=width
    values={'before.json':scene,'editable.json':repaired,
        'diagnostics.json':dict(status='fail',ready=False,code='TEXT_OVERFLOW',pointer='/items/0/content',suggested_width=width)}
    for name,value in values.items():
        with (root/name).open('x',encoding='utf-8') as output:json.dump(value,output)
    for name,w in (('before.svg',12),('editable.svg',24)):
        with (root/name).open('x',encoding='utf-8') as output:output.write(svg(w))


def publish(root,raw):
    assert not (root/'repaired.png').exists()
    digest=hashlib.sha256(raw).hexdigest()
    with (root/'review.png').open('xb') as output:output.write(raw)
    with (root/'repaired.png').open('xb') as output:output.write(raw)
    with (root/'delivery.json').open('x',encoding='utf-8') as output:
        json.dump(dict(file='repaired.png',ready=True,preflight_sha256=digest,sha256=digest),output)


def main():
    from PIL import Image
    root=Path(sys.argv[1]);author(root);prepared=root/'prepared.png'
    assert not prepared.exists() and not (root/'repaired.png').exists()
    subprocess.run([sys.argv[2],'--skip-system-fonts','--use-font-file',str(root/'renderer.ttf'),
        '--font-family',FAMILY,str(root/'editable.svg'),str(prepared)],check=True)
    with Image.open(prepared) as image:
        assert image.format=='PNG' and image.size==(48,32);image.load()
    publish(root,prepared.read_bytes())


if __name__=='__main__':main()
