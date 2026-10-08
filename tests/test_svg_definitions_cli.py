"""Original SVG reference fixtures; independent arithmetic, XML and pixel oracles."""
import base64
import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import test_editing_cli as editing
from test_mcp import Client
from test_svg_import_cli import svg

STOPS='<stop offset="0" stop-color="#e02040"/><stop offset="1" stop-color="#2050d0"/>'

def byte(v):return max(0,min(255,math.floor(v+0.5)))
def ramp(t,mode='pad',linear=False):
    t=t%1 if mode=='repeat' else 1-abs(t%2-1) if mode=='reflect' else max(0,min(1,t))
    a,b=(224,32,64),(32,80,208)
    if not linear:return [byte(x*(1-t)+y*t) for x,y in zip(a,b)]+[255]
    decode=lambda x:x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4
    encode=lambda x:12.92*x if x<=.0031308 else 1.055*x**(1/2.4)-.055
    return [byte(255*encode((1-t)*decode(x/255)+t*decode(y/255))) for x,y in zip(a,b)]+[255]


class SvgDefinitionTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def imported(self,body,attrs='width="32" height="24"',expected=0):
        return self.invoke(dict(command='svg.import',id='definitions',source=dict(kind='text',text=svg(body,attrs))),expected)
    def pixels(self,d,scale=1):
        r=self.invoke(dict(command='document.export',document=d,format='png',scale=scale))
        return editing.png_pixels(base64.b64decode(r['data']))[:3]
    def item(self,r,id):
        mapped=next(v['item_id'] for v in r['mapping'] if v['source_id']==id)
        return next(v for v in r['document']['items'] if v['id']==mapped)
    def exported(self,d):return self.invoke(dict(command='document.export',document=d,format='svg'))['data']
    def assert_bytes(self,a,b,tolerance=0):
        self.assertEqual(len(a),len(b));self.assertLessEqual(max(abs(x-y) for x,y in zip(a,b)),tolerance)

    def test_object_box_gradient_forward_reference_nonsquare_bounds_and_transform_order(self):
        body='<g transform="translate(2,1)"><rect id="r" x="4" y="3" width="16" height="8" fill="url(#g)"/></g><defs><linearGradient id="g" x2="50%" gradientTransform="translate(.25,0)">'+STOPS+'</linearGradient></defs>'
        r=self.imported(body);paint=self.item(r,'r')['content']['fill']
        self.assertEqual(paint['transform'],[16,0,0,8,8,3]);self.assertEqual(paint['start'],[0,0]);self.assertEqual(paint['end'],[.5,0])
        w,h,p=self.pixels(r['document']);expected=[]
        for y in range(h):
            for x in range(w):expected+=ramp((x+.5-10)/8) if 6<=x<22 and 4<=y<12 else [0]*4
        self.assert_bytes(p,expected)
        self.assertEqual({d['source_id'] for d in r['definitions']},{'g'})
        self.assertTrue(any('copied' in loss for loss in r['losses']))

    def test_user_space_gradients_percent_viewbox_spread_and_linear_light(self):
        for spread in ('pad','repeat','reflect'):
            for linear in (False,True):
                body=f'<defs><linearGradient id="g" gradientUnits="userSpaceOnUse" x1="25%" y1="0%" x2="50%" y2="0%" spreadMethod="{spread}" color-interpolation="{"linearRGB" if linear else "sRGB"}">{STOPS}</linearGradient></defs><rect width="16" height="8" fill="url(#g)"/>'
                r=self.imported(body,'width="32" height="16" viewBox="0 0 16 8"')
                w,h,p=self.pixels(r['document']);expected=[v for y in range(h) for x in range(w) for v in ramp(((x+.5)/2-4)/4,spread,linear)]
                self.assert_bytes(p,expected,1)
                output=self.exported(r['document']);tree=ET.fromstring(output);g=tree.find('.//{*}linearGradient')
                self.assertEqual(g.get('spreadMethod'),spread);self.assertEqual(float(g.get('x1')),4);self.assertEqual(float(g.get('x2')),8)
                again=self.invoke(dict(command='svg.import',id='again',source=dict(kind='text',text=output)))
                self.assertEqual(self.pixels(again['document']),self.pixels(r['document']))

    def test_radial_object_box_ellipse_and_user_space_diagonal_radius(self):
        body=f'<defs><radialGradient id="g">{STOPS}</radialGradient></defs><rect id="r" x="4" y="4" width="24" height="12" fill="url(#g)"/>'
        r=self.imported(body);paint=self.item(r,'r')['content']['fill'];self.assertEqual(paint['radius'],.5);self.assertEqual(paint['center'],[.5,.5])
        w,h,p=self.pixels(r['document']);expected=[]
        for y in range(h):
            for x in range(w):expected+=ramp(math.hypot((x+.5-16)/12,(y+.5-10)/6)) if 4<=x<28 and 4<=y<16 else [0]*4
        self.assert_bytes(p,expected,1)
        body=f'<defs><radialGradient id="g" gradientUnits="userSpaceOnUse" cx="25%" cy="50%" r="50%">{STOPS}</radialGradient></defs><rect id="r" width="32" height="24" fill="url(#g)"/>'
        r=self.imported(body);paint=self.item(r,'r')['content']['fill'];self.assertEqual(paint['center'],[8,12]);self.assertAlmostEqual(paint['radius'],20/math.sqrt(2))
        w,h,p=self.pixels(r['document']);expected=[v for y in range(h) for x in range(w) for v in ramp(math.hypot(x+.5-8,y+.5-12)/(20/math.sqrt(2)))]
        self.assert_bytes(p,expected,1)

    def test_gradient_templates_stop_override_and_definition_style_inheritance(self):
        body=f'<defs color="#123456"><linearGradient id="derived" href="#middle" x2=".5"/><linearGradient id="middle" href="#base" spreadMethod="repeat"/><linearGradient id="base" color-interpolation="linearRGB"><stop offset="0" stop-color="currentColor"/><stop offset="1" stop-color="#abcdef"/></linearGradient><linearGradient id="override" href="#derived"><stop offset="0" stop-color="lime"/></linearGradient></defs><rect id="a" width="16" height="12" fill="url(#derived)" color="red"/><rect id="b" x="16" width="16" height="12" fill="url(#override)"/>'
        r=self.imported(body);a=self.item(r,'a')['content']['fill'];b=self.item(r,'b')['content']['fill']
        self.assertEqual(a['stops'][0]['color'],[18,52,86,255]);self.assertEqual(a['end'],[.5,0]);self.assertEqual(a['spread'],'repeat');self.assertEqual(a['space'],'srgb')
        self.assertEqual(b,[0,255,0,255])
        # Presentation properties inherit from XML ancestors, not gradient href.
        r=self.imported('<defs color="#369" stop-color="red"><linearGradient id="g" stop-color="blue"><stop offset="0"/><stop offset="1" stop-color="inherit"/></linearGradient></defs><rect id="a" width="8" height="8" fill="url(#g)"/>')
        self.assertEqual([s['color'] for s in self.item(r,'a')['content']['fill']['stops']],[[0,0,0,255],[0,0,255,255]])
        r=self.imported('<defs xmlns:xlink="http://www.w3.org/1999/xlink"><linearGradient id="g" xlink:href="#base"/><linearGradient id="base"><stop offset="0" stop-color="red"/></linearGradient></defs><rect id="r" width="8" height="8" fill="url(\'#g\')"/>')
        self.assertEqual(self.item(r,'r')['content']['fill'],[255,0,0,255])
        # Cloned stops inherit from the final gradient's XML context, including
        # across two template links; explicit child properties still win.
        body='<defs color="red"><linearGradient id="base" stop-opacity=".25"><stop offset="0" stop-color="currentColor" stop-opacity="inherit"/><stop offset="1" style="color:lime;stop-color:currentColor"/></linearGradient></defs><defs color="blue"><linearGradient id="middle" href="#base"/><linearGradient id="derived" href="#middle" stop-opacity=".75"/></defs><rect id="base-art" width="12" height="12" fill="url(#base)"/><rect id="derived-art" x="12" width="12" height="12" fill="url(#derived)"/>'
        r=self.imported(body)
        self.assertEqual([s['color'] for s in self.item(r,'base-art')['content']['fill']['stops']],[[255,0,0,64],[0,255,0,255]])
        self.assertEqual([s['color'] for s in self.item(r,'derived-art')['content']['fill']['stops']],[[0,0,255,191],[0,255,0,255]])

    def test_curve_bounds_drive_object_coordinates_and_viewbox_percentages_remain_local(self):
        # Exact parabolic extrema: the control hull reaches y=10; the curve only y=8.
        r=self.imported(f'<defs><linearGradient id="g" x2="0" y2="1">{STOPS}</linearGradient><clipPath id="c" clipPathUnits="objectBoundingBox"><rect width="1" height="1"/></clipPath></defs><path id="p" d="M4 2 C9.333333333333334 10 14.666666666666666 10 20 2 Z" fill="url(#g)" clip-path="url(#c)"/>')
        p=self.item(r,'p');self.assertEqual(p['content']['fill']['transform'],[16,0,0,6,4,2]);self.assertEqual(p['clip']['transform'],[16,0,0,6,4,2])
        body=f'<linearGradient id="g" gradientUnits="userSpaceOnUse" x2="100%">{STOPS}</linearGradient><rect id="r" width="8" height="4" fill="url(#g)"/>'
        r=self.imported(body,'width="24" height="24" viewBox="0 0 8 4"')
        self.assertEqual(self.item(r,'r')['content']['fill']['end'],[8,0]);w,h,p=self.pixels(r['document'])
        expected=[v for y in range(h) for x in range(w) for v in (ramp((x+.5)/24) if 6<=y<18 else [0]*4)];self.assert_bytes(p,expected,1)

    def test_stop_clamping_order_duplicates_empty_single_and_degenerate_gradients(self):
        body='<defs><linearGradient id="g"><stop offset="-20%" stop-color="red"/><stop offset=".5" stop-color="lime"/><stop offset=".2" stop-color="blue"/><stop offset="120%" stop-color="white"/></linearGradient><linearGradient id="empty"/><linearGradient id="same" x1=".5" x2=".5">'+STOPS+'</linearGradient><radialGradient id="zero" r="0">'+STOPS+'</radialGradient></defs><rect id="a" width="16" height="8" fill="url(#g)"/><rect id="b" y="8" width="8" height="8" fill="url(#empty)" stroke="url(#empty)"/><rect id="c" x="8" y="8" width="8" height="8" fill="url(#same)"/><rect id="d" x="16" y="8" width="8" height="8" fill="url(#zero)"/>'
        r=self.imported(body);self.assertEqual([s['offset'] for s in self.item(r,'a')['content']['fill']['stops']],[0,.5,.5,1]);self.assertIsNone(self.item(r,'b')['content']['fill']);self.assertIsNone(self.item(r,'b')['content']['stroke'])
        self.assertEqual(self.item(r,'c')['content']['fill'],[32,80,208,255]);self.assertEqual(self.item(r,'d')['content']['fill'],[32,80,208,255])
        w,h,p=self.pixels(r['document']);self.assertEqual(p[(10*w+10)*4:(10*w+10)*4+4],bytes([32,80,208,255]))

    def test_gradient_alpha_stroke_roundtrip_keeps_source_and_pinned_geometry(self):
        body='<defs><linearGradient id="g" gradientUnits="userSpaceOnUse" x1="4" x2="28"><stop offset="0" stop-color="#a02030" stop-opacity=".5"/><stop offset="1" stop-color="#2040c0" stop-opacity=".25"/></linearGradient></defs><path id="p" d="M4 6 C10 2 22 14 28 6 L28 18 L4 18 Z" fill="url(#g)" fill-opacity=".5" stroke="url(#g)" stroke-opacity=".75" stroke-width="2"/>'
        r=self.imported(body);before=copy.deepcopy(r);content=self.item(r,'p')['content']
        self.assertEqual([s['color'][3] for s in content['fill']['stops']],[64,32]);self.assertEqual([s['color'][3] for s in content['stroke']['color']['stops']],[96,48])
        output=self.exported(r['document']);again=self.invoke(dict(command='svg.import',id='again',source=dict(kind='text',text=output)))
        for scale in (1,2,4):self.assertEqual(self.pixels(again['document'],scale),self.pixels(r['document'],scale))
        self.assertEqual(r,before)

    def test_user_space_compound_clip_rule_is_separate_from_fill_rule(self):
        body='<defs><clipPath id="c" clip-rule="evenodd"><path d="M2 2H22V20H2Z M8 6H16V16H8Z" fill-rule="nonzero" fill="none" stroke="red" stroke-width="8"/></clipPath></defs><rect id="r" width="32" height="24" fill="#2468ac" clip-path="url(#c)" clip-rule="nonzero"/>'
        r=self.imported(body);clip=self.item(r,'r')['clip'];self.assertEqual(clip['fill_rule'],'even_odd')
        w,h,p=self.pixels(r['document']);expected=[v for y in range(h) for x in range(w) for v in ([36,104,172,255] if 2<=x<22 and 2<=y<20 and not(8<=x<16 and 6<=y<16) else [0]*4)]
        self.assert_bytes(p,expected)
        inspection=self.invoke(dict(command='document.inspect',document=r['document']));id=self.item(r,'r')['id'];self.assertEqual(next(i for i in inspection['items'] if i['id']==id)['geometry_bounds'],[0,0,32,24])

    def test_object_box_clipping_composes_definition_child_and_item_transforms(self):
        body='<defs><clipPath id="c" clipPathUnits="objectBoundingBox" transform="translate(.25,0)"><rect x="0" y="0" width=".5" height=".5" transform="translate(0,.25)"/></clipPath></defs><g transform="translate(2,1)"><rect id="r" x="4" y="3" width="16" height="12" fill="#3a72bc" clip-path="url(#c)"/></g>'
        r=self.imported(body);self.assertEqual(self.item(r,'r')['clip']['transform'],[16,0,0,12,8,6])
        w,h,p=self.pixels(r['document']);expected=[v for y in range(h) for x in range(w) for v in ([58,114,188,255] if 10<=x<18 and 7<=y<13 else [0]*4)]
        self.assert_bytes(p,expected)

    def test_group_clip_bounds_ignore_stroke_and_display_none_but_include_hidden_geometry(self):
        body='<defs><clipPath id="half" clipPathUnits="objectBoundingBox"><rect width=".5" height="1"/></clipPath></defs><g id="group" transform="translate(2,2)" clip-path="url(#half)" fill="blue"><rect x="4" y="4" width="8" height="8"/><rect x="12" y="4" width="8" height="8" visibility="hidden"/><rect x="24" y="4" width="8" height="8" display="none" stroke="red" stroke-width="10"/></g>'
        r=self.imported(body);self.assertEqual(self.item(r,'group')['clip']['transform'],[16,0,0,8,4,4]);w,h,p=self.pixels(r['document'])
        expected=[v for y in range(h) for x in range(w) for v in ([0,0,255,255] if 6<=x<14 and 6<=y<14 else [0]*4)]
        self.assert_bytes(p,expected)

    def test_nested_clips_empty_hidden_and_ellipse_roundtrip(self):
        body='<defs><clipPath id="outer"><rect x="2" y="2" width="20" height="18"/></clipPath><clipPath id="inner"><rect x="8" y="6" width="20" height="18"/></clipPath><clipPath id="empty"/><clipPath id="hidden"><rect width="32" height="24" display="none"/></clipPath></defs><g clip-path="url(#outer)"><rect width="32" height="24" fill="red" clip-path="url(#inner)"/></g><rect width="32" height="24" fill="blue" clip-path="url(#empty)"/><rect width="32" height="24" fill="lime" clip-path="url(#hidden)"/>'
        r=self.imported(body);w,h,p=self.pixels(r['document']);expected=[v for y in range(h) for x in range(w) for v in ([255,0,0,255] if 8<=x<22 and 6<=y<20 else [0]*4)];self.assert_bytes(p,expected)
        r=self.imported('<defs><clipPath id="c"><ellipse cx="16" cy="12" rx="10" ry="6"/></clipPath></defs><rect width="32" height="24" fill="#2468ac" clip-path="url(#c)"/>')
        output=self.exported(r['document']);again=self.invoke(dict(command='svg.import',id='again',source=dict(kind='text',text=output)))
        for scale in (1,3):self.assertEqual(self.pixels(again['document'],scale),self.pixels(r['document'],scale))

    def test_copied_definitions_edit_independently_and_mcp_session_undo(self):
        body=f'<defs><linearGradient id="g">{STOPS}</linearGradient><clipPath id="c"><rect width="12" height="12"/></clipPath></defs><rect id="a" width="16" height="16" fill="url(#g)" clip-path="url(#c)"/><rect id="b" width="16" height="16" transform="translate(16,0)" fill="url(#g)" clip-path="url(#c)"/>'
        client=Client();self.addCleanup(client.close);client.initialize();r=client.success('svg.import',id='live',source=dict(kind='text',text=svg(body)))
        d=r['document'];a=self.item(r,'a');b=self.item(r,'b');original=copy.deepcopy(d);before=self.pixels(d)
        self.assertEqual(a['clip'],b['clip']);self.assertEqual(a['content']['fill'],b['content']['fill'])
        with tempfile.TemporaryDirectory() as root:
            args=dict(session_root=root,session_id='defs');client.success('session.create',**args,request_id='create',document=d)
            changed=client.success('session.apply',**args,request_id='change',expected_revision=0,action=dict(type='edit',operations=[dict(op='vector',id=a['id'],geometry=a['content']['geometry'],fill=[0,255,0,255],stroke=a['content']['stroke'],fill_rule=a['content']['fill_rule']),dict(op='clip',id=a['id'],clip=None)]))['document']
            self.assertEqual(next(i for i in changed['items'] if i['id']==b['id']),b);self.assertNotEqual(self.pixels(changed),before)
            undone=client.success('session.apply',**args,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'];self.assertEqual(self.pixels(undone),before)
            self.assertEqual(self.invoke(dict(command='session.read',**args))['document'],undone)
        self.assertEqual(d,original)

    def test_missing_wrong_type_cyclic_and_external_references_fail(self):
        bodies=['<rect width="8" height="8" fill="url(#missing)"/>','<rect width="8" height="8" clip-path="url(#missing)"/>','<defs><clipPath id="c"><rect width="8" height="8"/></clipPath></defs><rect width="8" height="8" fill="url(#c)"/>','<defs><linearGradient id="g">'+STOPS+'</linearGradient></defs><rect width="8" height="8" clip-path="url(#g)"/>','<defs><linearGradient id="a" href="#b"/><linearGradient id="b" href="#a"/></defs>','<defs><linearGradient id="a" href="#missing"/></defs>']
        for body in bodies:
            with self.subTest(body=body):self.assertEqual(self.imported(body,expected=1)['code'],'SVG_INVALID')
        for value in ('url(https://invalid.example/x)','url(file:///x)','url(#g) red',"url(')"):
            body=f'<rect width="8" height="8" fill="{value}"/>';self.assertEqual(self.imported(body,expected=1)['code'],'SVG_UNSUPPORTED')

    def test_explicit_remaining_limits_and_unknown_definition_content(self):
        bodies=['<defs><pattern id="p"/></defs>','<defs><radialGradient id="g" fx=".2">'+STOPS+'</radialGradient></defs>','<defs><clipPath id="c"><rect width="8" height="8"/><circle r="2"/></clipPath></defs>','<defs><clipPath id="c" clip-path="url(#c)"><rect width="8" height="8"/></clipPath></defs>','<defs><linearGradient id="g"><animate/></linearGradient></defs>','<defs><filter id="f"/></defs>','<g color-interpolation="linearRGB"/>']
        for body in bodies:
            with self.subTest(body=body):self.assertEqual(self.imported(body,expected=1)['code'],'SVG_UNSUPPORTED')
        self.assertEqual(self.imported('<defs>'+''.join(f'<linearGradient id="g{i}"/>' for i in range(65))+'</defs>',expected=1)['code'],'RESOURCE_LIMIT')
        chain='<defs>'+''.join(f'<linearGradient id="g{i}" href="#g{i+1}"/>' for i in range(17))+'<linearGradient id="g17"/></defs>'
        self.assertEqual(self.imported(chain,expected=1)['code'],'RESOURCE_LIMIT')
        many='<defs><linearGradient id="g">'+'<stop offset="0"/>'*65+'</linearGradient></defs>'
        self.assertEqual(self.imported(many,expected=1)['code'],'RESOURCE_LIMIT')
        body='<defs><linearGradient id="g">'+STOPS+'</linearGradient></defs><line x1="1" y1="1" x2="10" y2="1" stroke="url(#g)"/>'
        self.assertEqual(self.imported(body,expected=1)['code'],'SVG_UNSUPPORTED')
        self.assertEqual(self.imported('<linearGradient id="g"><stop offset="1px"/></linearGradient>',expected=1)['code'],'SVG_INVALID')
        self.assertEqual(self.imported('<linearGradient id="g" href="#name%20encoded"/>',expected=1)['code'],'SVG_UNSUPPORTED')


if __name__=='__main__':unittest.main()
