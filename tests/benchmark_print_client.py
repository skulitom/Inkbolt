"""Original no-engine print client: retained recipe, classic PDF and ICC preview."""
import hashlib
import json
from fractions import Fraction
from pathlib import Path
import sys


def recipe(root):
    def profile(name):return dict(file=name,sha256=hashlib.sha256((root/name).read_bytes()).hexdigest())
    return dict(paper_mm=[210,297],resolution_ppi=72,bleed_px=[9,12,6,3],
        page_profile=profile('original-rgb.icc'),ink_profile=profile('original-cmyk.icc'),
        intent='relative_colorimetric',black_point_compensation=False,
        items=[dict(bounds=[20,30,100,80],kind='process',components=[.25,.5,.75,1]),
               dict(bounds=[140,30,80,80],kind='spot',id='spot',alternate=[0,1,0,0],tint=1)])


def pdf_bytes(scene,rgb,cmyk,*,commands=None,group_controls='/I true /K false',paint_controls=None,indirect_spaces=False):
    def number(v):return format(float(v),'.14f').rstrip('0').rstrip('.') or '0'
    def array(values):return '['+' '.join(number(v) for v in values)+']'
    width,height=[Fraction(mm)*360/127 for mm in scene['paper_mm']]
    top,right,bottom,left=scene['bleed_px'];media=[0,0,width+left+right,height+top+bottom]
    trim=[left,bottom,width+left,height+bottom]
    content=['q','1 0 0 -1 0 '+number(media[3])+' cm','/Paint gs']
    for i,item in enumerate(scene['items']):
        values=item['components'] if item['kind']=='process' else [item['tint']]
        content+=['/'+('Process' if i==0 else 'Spot')+' cs',' '.join(number(v) for v in values)+' scn']
        x,y,w,h=item['bounds'];x+=left;y+=top
        content += [f'{number(x)} {number(y)} m',f'{number(x+w)} {number(y)} l',
                    f'{number(x+w)} {number(y+h)} l',f'{number(x)} {number(y+h)} l','h','f']
    content.append('Q')
    if commands is None:commands=('\n'.join(content)+'\n').encode()
    if paint_controls is None:
        paint_controls='/ca 1 /CA 1 /BM /Normal /SMask /None /op false /OP false /OPM 0 /RI /RelativeColorimetric /UseBlackPtComp /OFF'
    def stream(data,extra=''):return f'<< /Length {len(data)} {extra} >>\nstream\n'.encode()+data+b'\nendstream'
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        (f'<< /Type /Page /Parent 2 0 R /MediaBox {array(media)} /TrimBox {array(trim)} /BleedBox {array(media)} '
         f'/Group << /Type /Group /S /Transparency /CS [/ICCBased 4 0 R] {group_controls} >> '
         '/Resources << /ColorSpace << /Process [/ICCBased 5 0 R] /Spot [/Separation /Inkbolt.spot [/ICCBased 5 0 R] 6 0 R] >> '
         '/ExtGState << /Paint 8 0 R >> >> /Contents 7 0 R >>').encode(),
        stream(rgb,'/N 3'),stream(cmyk,'/N 4'),
        ('<< /FunctionType 2 /Domain [0 1] /C0 [0 0 0 0] /C1 '+array(scene['items'][1]['alternate'])+' /N 1 >>').encode(),
        stream(commands),f'<< /Type /ExtGState {paint_controls} >>'.encode()]
    if indirect_spaces:
        objects[2]=objects[2].replace(b'/CS [/ICCBased 4 0 R]',b'/CS 9 0 R').replace(
            b'/Process [/ICCBased 5 0 R]',b'/Process 10 0 R').replace(
            b'/Spot [/Separation /Inkbolt.spot [/ICCBased 5 0 R] 6 0 R]',b'/Spot 11 0 R')
        objects += [b'[/ICCBased 4 0 R]',b'[/ICCBased 5 0 R]',b'[/Separation /Inkbolt.spot 10 0 R 6 0 R]']
    result=bytearray(b'%PDF-2.0\n');offsets=[0]
    for index,body in enumerate(objects,1):
        offsets.append(len(result));result.extend(f'{index} 0 obj\n'.encode()+body+b'\nendobj\n')
    start=len(result);result.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:result.extend(f'{offset:010d} 00000 n \n'.encode())
    result.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode())
    return bytes(result)


def author(root):
    scene=recipe(root);(root/'editable.json').write_text(json.dumps(scene),encoding='utf-8')
    raw=pdf_bytes(scene,(root/'original-rgb.icc').read_bytes(),(root/'original-cmyk.icc').read_bytes())
    assert not (root/'print.pdf').exists()
    with (root/'print.pdf').open('xb') as output:output.write(raw)
    (root/'delivery.json').write_text(json.dumps(dict(file='print.pdf',sha256=hashlib.sha256(raw).hexdigest(),losses=[
        'PDF does not carry the editable document model; retain the recipe and both original profiles.',
        'The display preview is not a print proof; native ink declarations do not prove press appearance or plate coverage.',
        'Managed paint uses relative colorimetric conversion with black point compensation off; consumer support and rounding can differ.'])),encoding='utf-8')
    return scene


def main():
    from PIL import Image,ImageDraw,ImageCms
    root=Path(sys.argv[1]);scene=author(root)
    preview=Image.new('RGBA',(240,130));draw=ImageDraw.Draw(preview)
    profile=ImageCms.ImageCmsProfile(str(root/scene['ink_profile']['file']))
    for item in scene['items']:
        values=item['components'] if item['kind']=='process' else item['alternate']
        sample=Image.new('CMYK',(1,1),tuple(round(255*v) for v in values))
        rgb=ImageCms.profileToProfile(sample,profile,ImageCms.createProfile('sRGB'),renderingIntent=1,outputMode='RGB',flags=0)
        x,y,w,h=item['bounds'];draw.rectangle((x,y,x+w-1,y+h-1),fill=rgb.getpixel((0,0))+(255,))
    preview.save(root/'preview.png')


if __name__=='__main__':main()
