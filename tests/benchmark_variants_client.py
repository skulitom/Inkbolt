"""Original synthetic B12 SVG client; renders sheets and crops with pinned tools."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys

BOARDS=(('wide',48,24,0,0),('square',32,32,56,0),('tall',24,48,0,40))
VALUES={'wide':('AAA',36,16,'green'),'square':('AA',24,24,'orange'),'tall':('A',10,38,'green')}


def svg(root,text,x,y,image):
    image=base64.b64encode((root/(image+'.png')).read_bytes()).decode()
    parts=['<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="96" height="96">',
        '<defs><g id="shared"><text x="2" y="16" font-family="Inkbolt Variant Fixture" font-size="20" fill="#145096">',
        text,f'</text><image x="{x}" y="{y}" width="4" height="4" xlink:href="data:image/png;base64,{image}"/></g></defs>']
    for name,w,h,x,y in BOARDS:
        parts.append(f'<svg id="{name}" x="{x}" y="{y}" width="{w}" height="{h}"><use xlink:href="#shared"/></svg>')
    return (''.join(parts)+'</svg>').encode()


def author(root):
    base=svg(root,'A',2,16,'green')
    with (root/'base.svg').open('xb') as output:output.write(base)
    data=dict(base=dict(text='A',position=[2,16],image='green.png'),selected=None,datasets={})
    for name,(text,x,y,image) in VALUES.items():
        row=dict(values=dict(text=text,position=[x,y],image=image+'.png'))
        if name=='square':row['parent']='wide'
        data['datasets'][name]=row
        with (root/(name+'.svg')).open('xb') as output:output.write(svg(root,text,x,y,image))
    with (root/'variants.json').open('x',encoding='utf-8') as output:json.dump(data,output)


def main():
    from PIL import Image
    root=Path(sys.argv[1]);renderer=sys.argv[2];author(root);identities={}
    for name,w,h,x,y in BOARDS:
        sheet=root/(name+'-sheet.png');assert not sheet.exists()
        subprocess.run([renderer,'--skip-system-fonts','--use-font-file',str(root/'renderer.ttf'),
                        '--font-family','Inkbolt Variant Fixture',str(root/(name+'.svg')),str(sheet)],check=True)
        with Image.open(sheet) as image:
            with (root/(name+'.png')).open('xb') as output:image.crop((x,y,x+w,y+h)).save(output,format='PNG')
        identities[name]=hashlib.sha256((root/(name+'.png')).read_bytes()).hexdigest()
    with (root/'editable.svg').open('xb') as output:output.write((root/'base.svg').read_bytes())
    with (root/'outputs.json').open('x',encoding='utf-8') as output:json.dump(identities,output)


if __name__=='__main__':main()
