"""Original synthetic B13 editable SVG, direct RGBA paint and create-only PNG."""
import hashlib
import json
from pathlib import Path
import sys

SVG='<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080"><metadata>original private source note</metadata><rect x="10" y="20" width="200" height="100" fill="#145096" fill-opacity="0.5019607843137255"/></svg>'


def main():
    from PIL import Image,ImageDraw,PngImagePlugin
    root=Path(sys.argv[1])
    with (root/'editable.svg').open('x',encoding='utf-8') as source:source.write(SVG)
    image=Image.new('RGBA',(1920,1080));ImageDraw.Draw(image).rectangle((10,20,209,119),fill=(20,80,150,128))
    metadata=PngImagePlugin.PngInfo();metadata.add(b'sRGB',b'\0')
    def publish():
        with (root/'screen.png').open('xb') as output:image.save(output,format='PNG',pnginfo=metadata)
    publish();before=(root/'screen.png').read_bytes()
    try:publish()
    except FileExistsError:pass
    else:raise AssertionError('A duplicate screen publication was accepted')
    assert before==(root/'screen.png').read_bytes()
    result=dict(file='screen.png',mode='create_only',sha256=hashlib.sha256(before).hexdigest(),collision='output_exists')
    with (root/'delivery.json').open('x',encoding='utf-8') as output:json.dump(result,output)


if __name__=='__main__':main()
