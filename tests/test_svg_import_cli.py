"""Independent XML, geometry, analytic pixels and persistence checks for SVG import."""
import base64
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
import test_editing_cli as editing
from test_mcp import Client


def svg(body, attrs='width="32" height="24"'):
    return f'<svg xmlns="http://www.w3.org/2000/svg" {attrs}>{body}</svg>'

def bounds(pixels,w,h):
    points=[(x,y) for y in range(h) for x in range(w) if pixels[(y*w+x)*4+3]]
    return [min(x for x,y in points),min(y for x,y in points),max(x for x,y in points)+1,max(y for x,y in points)+1] if points else None

def curve_bounds(points):
    """Independent polynomial derivative roots, not sampled bounds."""
    out=[]
    for axis in range(2):
        p0,p1,p2,p3=[p[axis] for p in points]
        a=-p0+3*p1-3*p2+p3;b=3*p0-6*p1+3*p2;c=3*(p1-p0)
        candidates=[0,1]
        if a:
            disc=4*b*b-12*a*c
            if disc>=0:candidates += [(-2*b+math.sqrt(disc))/(6*a),(-2*b-math.sqrt(disc))/(6*a)]
        elif b:candidates.append(-c/(2*b))
        values=[((a*t+b)*t+c)*t+p0 for t in candidates if 0<=t<=1]
        out.append((min(values),max(values)))
    return [out[0][0],out[1][0],out[0][1],out[1][1]]


class SvgImportTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def imported(self,text,expected=0,**kw):
        return self.invoke(dict(command='svg.import',id='imported',source=dict(kind='text',text=text),**kw),expected)
    def pixels(self,d,scale=1):
        r=self.invoke(dict(command='document.export',document=d,format='png',scale=scale))
        return editing.png_pixels(base64.b64decode(r['data']))[:3]
    def item(self,result,source_id):
        id=next(m['item_id'] for m in result['mapping'] if m['source_id']==source_id)
        return next(i for i in result['document']['items'] if i['id']==id)

    def test_rectangles_export_import_xml_geometry_and_exact_extent(self):
        source=svg('<g transform="translate(3,2)" opacity="0.5"><rect id="box" x="2" y="3" width="8" height="6" fill="#2c80d2"/></g>')
        r=self.imported(source);d=r['document'];before=copy.deepcopy(d)
        self.assertEqual(self.item(r,'box')['content']['geometry'],dict(shape='rect',x=2,y=3,width=8,height=6))
        w,h,p=self.pixels(d)
        expected=b''.join(bytes([44,128,210,128]) if 5<=x<13 and 5<=y<11 else bytes(4) for y in range(h) for x in range(w))
        self.assertEqual(p,expected);self.assertEqual(bounds(p,w,h),[5,5,13,11])
        output=self.invoke(dict(command='document.export',document=d,format='svg'))['data']
        tree=ET.fromstring(output);self.assertEqual(tree.attrib['viewBox'],'0 0 32 24')
        rect=tree.find('.//{*}rect');self.assertEqual({k:float(rect.attrib[k]) for k in ('x','y','width','height')},dict(x=2,y=3,width=8,height=6))
        self.assertEqual(rect.attrib['fill'],'#2c80d2')
        self.assertEqual(self.pixels(self.imported(output)['document']),self.pixels(d))
        self.assertEqual(d,before)

    def test_cubics_export_import_independent_analytic_bounds_and_coverage(self):
        # Parabolic cap y=2+24t(1-t), x=4+16t: exact extent [4,2,20,8].
        text=svg('<path id="cap" d="M4 2 C9.333333333333334 10 14.666666666666666 10 20 2 Z" fill="#9a5030"/>')
        r=self.imported(text);d=r['document'];item=self.item(r,'cap')
        commands=item['content']['geometry']['commands'];points=[commands[0]['to'],commands[1]['control1'],commands[1]['control2'],commands[1]['to']]
        wanted=curve_bounds(points);self.assertEqual(wanted,[4,2,20,8])
        inspection=self.invoke(dict(command='document.inspect',document=d))
        observed=next(i for i in inspection['items'] if i['id']==item['id'])['geometry_bounds']
        self.assertEqual(observed,wanted)
        output=self.invoke(dict(command='document.export',document=d,format='svg'))['data']
        path=ET.fromstring(output).find('.//{*}path').attrib['d']
        nums=[float(v) for v in re.findall(r'[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?',path)]
        self.assertEqual(nums,[v for p in points for v in p]);self.assertEqual(re.sub(r'[^A-Za-z]','',path),'MCZ')
        for scale in (1,3):
            w,h,p=self.pixels(d,scale);self.assertEqual(bounds(p,w,h),[4*scale,2*scale,20*scale,8*scale])
            area=sum(p[3::4])/255/scale**2;self.assertAlmostEqual(area,64,delta=1)
            for y in range(h):
                for x in range(w):
                    xx,yy=(x+.5)/scale,(y+.5)/scale
                    ts=[(x/scale-4)/16,((x+1)/scale-4)/16]
                    lowest_edge=min(2+24*t*(1-t) for t in ts)
                    # The entire pixel, including its corners, lies inside the cap.
                    if 4.6<xx<19.4 and y/scale>2.1 and (y+1)/scale<lowest_edge-.1:self.assertEqual(p[(y*w+x)*4:(y*w+x+1)*4],bytes([154,80,48,255]))
            self.assertEqual(self.pixels(self.imported(output)['document'],scale),(w,h,p))

    def test_relative_repeated_smooth_quadratic_and_post_close_commands(self):
        r=self.imported(svg('<path id="p" d="m2 3 4 0 h2 v4 c1 2 3 2 4 0 s3-2 4 0 q3 3 6 0 t6 0 z l2 2"/>'))
        cs=self.item(r,'p')['content']['geometry']['commands']
        self.assertEqual(cs[:4],[dict(verb='move',to=[2,3]),dict(verb='line',to=[6,3]),dict(verb='line',to=[8,3]),dict(verb='line',to=[8,7])])
        self.assertEqual(cs[4],dict(verb='cubic',control1=[9,9],control2=[11,9],to=[12,7]))
        self.assertEqual(cs[5],dict(verb='cubic',control1=[13,5],control2=[15,5],to=[16,7]))
        self.assertEqual(cs[6],dict(verb='cubic',control1=[18,9],control2=[20,9],to=[22,7]))
        self.assertEqual(cs[7],dict(verb='cubic',control1=[24,5],control2=[26,5],to=[28,7]))
        self.assertEqual(cs[8:],[dict(verb='close'),dict(verb='move',to=[2,3]),dict(verb='line',to=[4,5])])
        # Smooth reflection resets after an unrelated command; exponent and adjacent decimal forms.
        r=self.imported(svg('<path id="p" d="M1e1,.5L12.5.5S14 2 16 3 T20 5"/>'))
        cs=self.item(r,'p')['content']['geometry']['commands'];self.assertEqual(cs[2]['control1'],[12.5,.5]);self.assertEqual(cs[3]['control1'],[16,3])

    def test_nested_transforms_order_center_rotation_skew_and_negative_scale(self):
        r=self.imported(svg('<g transform="translate(4,6) scale(2,3)"><rect id="r" x="1" y="2" width="3" height="4" transform="rotate(90,2,3) scale(-1,1)"/></g>'))
        record=next(i for i in self.invoke(dict(command='document.inspect',document=r['document']))['items'] if i['id']==self.item(r,'r')['id'])
        for a,b in zip(record['world_transform'],[0,-3,-2,0,14,9]):self.assertAlmostEqual(a,b,places=12)
        for axis,matrix in [('X',[1,0,1,1,0,0]),('Y',[1,1,0,1,0,0])]:
            r=self.imported(svg(f'<rect id="r" width="3" height="4" transform="skew{axis}(45)"/>'))
            for a,b in zip(self.item(r,'r')['transform'],matrix):self.assertAlmostEqual(a,b)

    def test_viewbox_units_meet_slice_and_none_pixels(self):
        body='<rect x="10" y="20" width="8" height="4" fill="#3a72bc"/>'
        for align,expected in [('none',[0,0,24,24]),('xMidYMid meet',[0,6,24,18]),('xMinYMax meet',[0,12,24,24]),('xMaxYMin slice',[0,0,24,24])]:
            r=self.imported(svg(body,f'width=".25in" height="18pt" viewBox="10 20 8 4" preserveAspectRatio="{align}"'))
            w,h,p=self.pixels(r['document']);self.assertEqual((w,h),(24,24));self.assertEqual(bounds(p,w,h),expected)
            x0,y0,x1,y1=expected
            self.assertEqual(p,b''.join(bytes([58,114,188,255]) if x0<=x<x1 and y0<=y<y1 else bytes(4) for y in range(24) for x in range(24)))
        for unit in ('6.35mm','0.635cm','1.5pc','24px','24'):
            d=self.imported(svg('',f'width="{unit}" height="24"'))['document'];self.assertEqual(d['width'],24)

    def test_inherited_style_precedence_current_color_visibility_and_group_opacity(self):
        body='<g fill="red" color="#123456" fill-opacity="0.5" visibility="hidden" opacity="0.5"><rect id="hidden" width="4" height="4"/><rect id="shown" x="4" width="4" height="4" visibility="visible" fill="green" style="fill:currentColor;fill-opacity:1"/><g display="none"><rect width="16" height="16" visibility="visible"/></g></g>'
        r=self.imported(svg(body));w,h,p=self.pixels(r['document'])
        self.assertFalse(self.item(r,'hidden')['visible']);self.assertTrue(self.item(r,'shown')['visible'])
        self.assertEqual(p,b''.join(bytes([18,52,86,128]) if 4<=x<8 and y<4 else bytes(4) for y in range(h) for x in range(w)))
        r=self.imported(svg('<g fill="currentColor" color="blue"><rect id="r" width="4" height="4" style="color:#abc;fill:inherit;fill-opacity:.5"/></g>'))
        self.assertEqual(self.item(r,'r')['content']['fill'],[170,187,204,128])

    def test_group_opacity_is_once_after_overlap_and_paint_alpha_is_separate(self):
        text=svg('<g opacity="0.5"><rect x="2" y="2" width="8" height="8" fill="red"/><rect x="6" y="2" width="8" height="8" fill="blue"/></g>')
        w,h,p=self.pixels(self.imported(text)['document'])
        expected=b''.join(bytes(([255,0,0] if x<6 else [0,0,255])+[128]) if 2<=x<14 and 2<=y<10 else bytes(4) for y in range(h) for x in range(w))
        self.assertEqual(p,expected)
        text=svg('<rect x="4" y="4" width="8" height="8" fill="red" fill-opacity=".5" stroke="blue" stroke-opacity=".25" stroke-width="2" opacity=".5"/>')
        w,h,p=self.pixels(self.imported(text)['document'])
        pixel=lambda x,y:p[(y*w+x)*4:(y*w+x+1)*4]
        self.assertEqual(pixel(8,8),bytes([255,0,0,64]));self.assertEqual(pixel(3,8),bytes([0,0,255,32]))
        from fractions import Fraction as F
        fill,stroke=F(128,255),F(64,255);alpha=stroke+fill*(1-stroke)
        encoded=lambda v:int(v*255+F(1,2))
        self.assertEqual(pixel(4,8),bytes([encoded(fill*(1-stroke)/alpha),0,encoded(stroke/alpha),encoded(alpha/2)]))

    def test_absolute_cubic_export_roundtrip_preserves_original_engine_document_pixels(self):
        d=self.invoke(dict(command='document.create',id='original',kind='vector',width=32,height=24))
        items=[dict(id='box',name='Original & editable',transform=[1,0,0,1,3,2],content=dict(type='vector',geometry=dict(shape='rect',x=2.25,y=1.5,width=5.75,height=4.5),fill=[37,83,159,173])),
               dict(id='cubic',content=dict(type='vector',geometry=dict(shape='path',commands=[dict(verb='move',to=[4,14]),dict(verb='cubic',control1=[8,1],control2=[24,23],to=[28,14]),dict(verb='line',to=[20,20]),dict(verb='close')]),fill=[191,69,43,211],stroke=dict(color=[31,51,71,193],width=1.5)))]
        d=self.invoke(dict(command='document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=i) for i in items]))['document'];original=copy.deepcopy(d)
        output=self.invoke(dict(command='document.export',document=d,format='svg'))['data'];r=self.imported(output)
        tree=ET.fromstring(output);path=tree.find('.//{*}path').attrib['d']
        values=[float(v) for v in re.findall(r'[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?',path)]
        self.assertEqual(values,[4,14,8,1,24,23,28,14,20,20]);self.assertEqual(curve_bounds([[4,14],[8,1],[24,23],[28,14]])[::2],[4,28])
        for scale in (1,2,4):self.assertEqual(self.pixels(r['document'],scale),self.pixels(d,scale))
        self.assertEqual(d,original)

    def test_compound_winding_colors_stroke_and_primitives(self):
        body='<path id="p" d="M2 2H18V18H2Z M6 6H14V14H6Z" fill="rgb(20,80,160)" fill-rule="evenodd" stroke="#F0A" stroke-width="2" stroke-linecap="round" stroke-linejoin="bevel" stroke-miterlimit="8"/>'
        r=self.imported(svg(body));item=self.item(r,'p')
        self.assertEqual(item['content']['fill_rule'],'even_odd');self.assertEqual(item['content']['stroke'],dict(color=[255,0,170,255],width=2,cap='round',join='bevel',miter_limit=8))
        w,h,p=self.pixels(r['document']);self.assertEqual(p[(10*w+10)*4:(10*w+10)*4+4],bytes(4));self.assertEqual(bounds(p,w,h),[1,1,19,19])
        r=self.imported(svg('<circle id="c" cx="8" cy="8" r="4" fill="rgb(100%,0%,50%)"/><ellipse id="e" cx="20" cy="8" rx="3" ry="2"/><line id="l" x1="2" y1="20" x2="8" y2="20" fill="none" stroke="blue"/><polygon id="p" points="20,16 28,16 24,22"/><polyline id="q" points="1,1 2,1 2,2" fill="none"/>'))
        self.assertEqual(self.item(r,'c')['content']['geometry'],dict(shape='ellipse',cx=8,cy=8,rx=4,ry=4));self.assertEqual(self.item(r,'c')['content']['fill'],[255,0,128,255])
        self.assertEqual(self.item(r,'e')['content']['geometry']['ry'],2)
        self.assertEqual(self.item(r,'p')['content']['geometry']['commands'][-1],dict(verb='close'));self.assertEqual(self.item(r,'q')['content']['geometry']['commands'][-1]['verb'],'line')

    def test_utf8_titles_source_hash_id_mapping_and_file_preservation(self):
        text='\ufeff'+svg('<title>Agent &amp; cafÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©</title><desc>Original fixture</desc><!-- note --><rect id="input:box" width="5" height="6"><title>Box &lt;1&gt;</title></rect>')
        data=text.encode('utf8');r=self.imported(text)
        self.assertEqual(r['document']['items'][0]['name'],'Agent & cafÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©');self.assertEqual(self.item(r,'input:box')['name'],'Box <1>')
        self.assertEqual(r['source'],dict(sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),media_type='image/svg+xml'));self.assertTrue(any('Description' in s for s in r['losses']))
        self.assertEqual(r,self.imported(text))
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'source.svg';source.write_bytes(data);before=source.stat().st_mtime_ns
            file_result=self.invoke(dict(command='svg.import',id='imported',source=dict(kind='file',source_path=str(source))))
            self.assertEqual(file_result,r);self.assertEqual(source.read_bytes(),data);self.assertEqual(source.stat().st_mtime_ns,before);self.assertEqual(list(Path(root).iterdir()),[source])
            source.write_bytes(b'\xff\xfe'+data);self.assertEqual(self.invoke(dict(command='svg.import',id='x',source=dict(kind='file',source_path=str(source))),1)['code'],'SVG_INVALID')

    def test_mcp_import_edit_session_reopen_undo_and_source_unchanged(self):
        text=svg('<rect id="r" x="2" y="3" width="6" height="5" fill="#224488"/>');source=text
        client=Client();self.addCleanup(client.close);client.initialize()
        r=client.success('svg.import',id='session-svg',source=dict(kind='text',text=text));d=r['document'];id=self.item(r,'r')['id'];before=self.pixels(d)
        self.assertIn('svg.import',client.success('capabilities')['commands'])
        with tempfile.TemporaryDirectory() as root:
            common=dict(session_root=root,session_id='imported')
            created=client.success('session.create',**common,request_id='create',document=d)
            edit=client.success('session.apply',**common,request_id='move',expected_revision=0,action=dict(type='edit',operations=[dict(op='transform',id=id,matrix=[1,0,0,1,4,1])]))
            retry=client.success('session.apply',**common,request_id='move',expected_revision=0,action=dict(type='edit',operations=[dict(op='transform',id=id,matrix=[1,0,0,1,4,1])]))
            self.assertTrue(retry['replayed']);self.assertEqual(retry,{**edit,'replayed':True})
            read=self.invoke(dict(command='session.read',**common));self.assertEqual(read['document'],edit['document']);self.assertNotEqual(self.pixels(read['document']),before)
            undo=client.success('session.apply',**common,request_id='undo',expected_revision=1,action=dict(type='undo'))
            self.assertEqual(self.pixels(undo['document']),before);self.assertEqual(text,source)
            snapshot=self.invoke(dict(command='document.export',document=undo['document'],format='snapshot'))['data']
            self.assertEqual(self.invoke(dict(command='document.validate',document=json.loads(snapshot))),undo['document'])

    def test_unsupported_elements_attributes_and_hidden_content_fail_whole_import(self):
        bodies=['<text><tspan>words</tspan></text>','<image href="https://invalid.example/asset.png"/>','<use href="#a"/>','<defs><pattern id="g"/></defs>','<script>bad()</script>','<svg width="2" height="2"/>','<rect width="4" height="4" rx="1"/>','<path d="M0 0 A2 3 0 0 0 4 5"/>','<rect width="4" height="4" class="x"/>','<rect width="4" height="4" clip-path="url(#a)"/>','<rect width="4" height="4" fill="url(#a)"/>','<rect width="4" height="4" style="filter:blur(2px)"/>','<rect width="4" height="4" style="fill:red!important"/>','<g display="none"><text><tspan>still unsupported</tspan></text></g>','<g opacity="inherit"/>','<path d="M0 0L2 3" pathLength="2"/>','<g xmlns="urn:foreign"/>']
        for body in bodies:
            with self.subTest(body=body):self.assertEqual(self.imported(svg('<rect width="1" height="1"/>'+body),1)['code'],'SVG_INVALID' if 'url(#a)' in body else 'SVG_UNSUPPORTED')
        self.assertEqual(self.imported('<?xml-stylesheet href="missing.css"?>'+svg(''),1)['code'],'SVG_UNSUPPORTED')

    def test_malformed_numbers_paths_and_xml_fail_explicitly(self):
        for d in ('M,1 2L3 4','M1,,2L3 4','M1 2,','M1e 2L3 4','M0 0C1 2 3 4 5','M0 0L','L1 2','M0 0ZZ','M0 0C1 2 3 4 NaN 5','M0 0L1e309 2','M0 0Z1 2'):
            with self.subTest(path=d):self.assertIn(self.imported(svg(f'<path d="{d}"/>'),1)['code'],('SVG_INVALID','SVG_UNSUPPORTED','INVALID_DOCUMENT'))
        for text in ('<svg>','<svg width="3" width="4" height="3"/>',svg('<rect id="a" width="1" height="1"/><g id="a"/>'),svg('<rect width="1" height="1" fill="&#x0;"/>')):
            self.assertEqual(self.imported(text,1)['code'],'SVG_INVALID')
        for attrs in ('width="10%" height="12"','width="0" height="12"','height="12"','width="12" height="12" viewBox="0 0 0 4"'):
            self.assertIn(self.imported(svg('',attrs),1)['code'],('SVG_INVALID','SVG_UNSUPPORTED'))
        self.assertEqual(self.imported('<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///never-read">]>'+svg('&x;'),1)['code'],'SVG_UNSUPPORTED')

    def test_resource_limits_file_errors_and_schema_are_discoverable(self):
        for body in ('<rect width="1" height="1"/>'*256,'<g>'*18+'</g>'*18,'<path d="M0 0'+' L1 1'*4096+'"/>'):
            self.assertIn(self.imported(svg(body),1)['code'],('RESOURCE_LIMIT','LIMIT_EXCEEDED'))
        self.assertEqual(self.imported(svg(' '*262144),1)['code'],'RESOURCE_LIMIT')
        self.assertEqual(self.imported(svg('<!--x-->'*4100),1)['code'],'SVG_INVALID')
        for transform in ('scale(0)','matrix(1 0 0 1 1e9 0)'):
            self.assertIn(self.imported(svg(f'<g transform="{transform}"/>'),1)['code'],('INVALID_DOCUMENT','RESOURCE_LIMIT','UNSUPPORTED'))
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'large.svg';source.write_bytes(b'x'*262145)
            self.assertEqual(self.invoke(dict(command='svg.import',id='x',source=dict(kind='file',source_path=str(source))),1)['code'],'RESOURCE_LIMIT')
            self.assertEqual(self.invoke(dict(command='svg.import',id='x',source=dict(kind='file',source_path=str(source)+'missing')),1)['code'],'SVG_IO')
        caps=self.invoke(dict(command='capabilities'));self.assertEqual(caps['svg_import']['source_bytes'],262144);self.assertEqual(caps['svg_import']['xml_nodes'],4096)
        self.assertIn('svg_editable_geometry_gradients_clips',caps['supported']['imports'])


if __name__=='__main__':unittest.main()
