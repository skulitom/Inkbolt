"""Original 16-bit PNG import, retained-source conversion and explicit TIFF delivery."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib
from mask_workflow import invoke


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        with (out/name).open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    def publish(d,name,format,**kw):
        save(name+'-receipt.json',invoke('document.publish',document=d,output=dict(output_root=str(out),file_name=name,format=format,**kw)))
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
    width,height=96,32
    rows=[b'\0'+struct.pack('>'+'H'*(width*4),*[v for x in range(width) for v in [10000+x*401,2000+y*1901,54000-x*251,65535]]) for y in range(height)]
    png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,16,6,0,0,0))+chunk(b'sRGB',b'\0')+chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b'')
    source=out/'source.png'
    with source.open('xb') as f:f.write(png)
    imported=invoke('sample.import',source_path=str(source),id='precision-import',resolution_ppi=144)
    save('import-receipt.json',imported);d=imported['document'];publish(d,'original.json','snapshot')
    edited=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='sample_convert',id='pixels',conversion=dict(depth='f32',channels='gray_alpha',gray='linear_luminance'))])
    save('conversion-receipt.json',edited);gray=edited['document'];publish(gray,'grayscale.json','snapshot')
    publish(d,'color16.tiff','tiff',image_options=dict(depth='u16',compression='deflate'))
    for depth in ['u16','f32']:publish(gray,'gray-'+depth+'.tiff','tiff',image_options=dict(depth=depth,channels='gray_alpha',compression='deflate'))
    publish(gray,'preview.png','png')
    assert source.read_bytes()==png and imported['source_sha256']==hashlib.sha256(png).hexdigest()
    print('Saved original PNG, retained snapshots, explicit grayscale conversion, native TIFFs and preview in '+str(out))


if __name__=='__main__':main()
