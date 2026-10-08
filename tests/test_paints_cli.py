"""Independent SVG-gradient evaluation and PNG-byte checks for original paint fixtures."""
import base64
import copy
import json
import math
import unittest
import xml.etree.ElementTree as ET
import test_editing_cli as editing
from test_editing_cli import png_pixels
from test_layout_cli import local_point, NS


def gradient_color(element, point):
    # Evaluate the exported public-format description, not an engine snapshot.
    transform = ET.Element('g', transform=element.get('gradientTransform'))
    x, y = local_point(transform, point)
    if element.tag == NS+'linearGradient':
        x1, y1, x2, y2 = (float(element.get(k)) for k in ('x1','y1','x2','y2'))
        length = math.hypot(x2-x1, y2-y1)
        t = ((x-x1)*(x2-x1)/length+(y-y1)*(y2-y1)/length)/length
    else:
        assert element.tag == NS+'radialGradient'
        t = math.hypot(x-float(element.get('cx')), y-float(element.get('cy')))/float(element.get('r'))
    spread = element.get('spreadMethod')
    if spread == 'repeat':
        t %= 1
    elif spread == 'reflect':
        t = 1-abs(t % 2-1)
    else:
        assert spread == 'pad'
        t = min(1, max(0, t))
    stops = []
    for stop in element:
        rgb = bytes.fromhex(stop.get('stop-color')[1:])
        stops.append((float(stop.get('offset')), [c/255 for c in rgb]+[float(stop.get('stop-opacity'))]))
    # Search from the right so equal offsets retain the last stop.
    lower = next((s for s in reversed(stops) if s[0] <= t), stops[0])
    upper = next((s for s in stops if s[0] > t), stops[-1])
    fraction = 0 if upper[0] == lower[0] else min(1,max(0,(t-lower[0])/(upper[0]-lower[0])))
    result = []
    for channel, (lo, hi) in enumerate(zip(lower[1], upper[1])):
        linear = channel < 3 and element.get('color-interpolation') == 'linearRGB'
        if linear:
            lo = lo/12.92 if lo <= 0.04045 else ((lo+0.055)/1.055)**2.4
            hi = hi/12.92 if hi <= 0.04045 else ((hi+0.055)/1.055)**2.4
        value = lo*(1-fraction)+hi*fraction
        if linear:
            value = value*12.92 if value <= 0.0031308 else 1.055*value**(1/2.4)-0.055
        result.append(int(math.floor(max(0,min(1,value))*255+0.5)))
    return result if result[3] else [0]*4


class PaintCliTests(unittest.TestCase):
    invoke = editing.EditingCliTests.invoke

    def test_exported_gradient_svg_matches_all_independently_decoded_png_pixels(self):
        stops = [dict(offset=0,color=[255,20,0,255]),dict(offset=1,color=[0,60,255,64])]
        paints = [
            dict(type='linear',start=[0.5,0.5],end=[7.5,0.5],stops=stops,spread='reflect',transform=[2,0,0,1,1,0]),
            dict(type='radial',center=[4,4],radius=3,stops=stops,space='linear_rgb',transform=[2,0,0,1,0,0]),
            dict(type='linear',start=[0,0],end=[4,0],spread='repeat',transform=[-1,0,0,1,15,0],stops=[dict(offset=0.1,color=[0,255,0,255]),dict(offset=0.5,color=[0,255,0,255]),dict(offset=0.5,color=[0,0,255,128]),dict(offset=0.9,color=[255,0,0,0])]),
        ]
        d = self.invoke(dict(command='document.create',id='gradient-fixture',kind='vector',width=48,height=8))
        operations = []
        for i, paint in enumerate(paints):
            item = dict(id=f'inkbolt-paint-{i}-0',transform=[1,0,0,1,i*16,0],content=dict(type='vector',geometry=dict(shape='rect',x=0,y=0,width=16,height=8),fill=paint))
            operations.append(dict(op='add',item=item))
        d = self.invoke(dict(command='document.edit',document=d,expected_revision=0,operations=operations))['document']
        root = ET.fromstring(self.invoke(dict(command='document.export',document=d,format='svg'))['data'])
        ids = [e.get('id') for e in root.iter() if e.get('id')]
        self.assertEqual(len(ids),len(set(ids)))
        gradients = {e.get('id'):e for e in root.iter() if e.tag in (NS+'linearGradient',NS+'radialGradient')}
        groups = root.findall(NS+'g')
        self.assertEqual(len(gradients),3)
        for e in gradients.values():
            self.assertEqual(e.get('gradientUnits'),'userSpaceOnUse')
        for scale in (1,2):
            result = self.invoke(dict(command='document.export',document=d,format='png',scale=scale))
            width,height,pixels,_ = png_pixels(base64.b64decode(result['data']))
            for y in range(height):
                for x in range(width):
                    group = groups[x//(16*scale)]
                    shape = group.find(NS+'rect')
                    gradient = gradients[shape.get('fill')[5:-1]]
                    expected = gradient_color(gradient,local_point(group,((x+0.5)/scale,(y+0.5)/scale)))
                    actual = pixels[(y*width+x)*4:(y*width+x+1)*4]
                    self.assertLessEqual(max(abs(a-b) for a,b in zip(actual,expected)),1,(x,y,actual,expected))
            preview = self.invoke(dict(command='document.render',document=d,scale=scale))
            self.assertEqual(bytes.fromhex(preview['data']),pixels)
        restored = json.loads(self.invoke(dict(command='document.export',document=d,format='snapshot'))['data'])
        self.assertEqual(restored,d)

    def test_raster_fill_edit_dither_transparency_and_pattern_png(self):
        d = self.invoke(dict(command='document.create',id='fill-fixture',kind='raster',width=4,height=4))
        linear = dict(type='linear',start=[0,0],end=[256,0],stops=[dict(offset=0,color=[0,0,0,255]),dict(offset=1,color=[255,255,255,255])])
        item = dict(id='fill',content=dict(type='fill',width=4,height=4,paint=linear,dither='ordered4x4'))
        d = self.invoke(dict(command='document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=item)]))['document']
        original = copy.deepcopy(d)
        data = self.invoke(dict(command='document.export',document=d,format='png'))['data']
        _,_,pixels,_ = png_pixels(base64.b64decode(data))
        levels = [0,2,2,4,1,1,3,3]*2
        self.assertEqual(pixels,bytes(v for level in levels for v in (level,level,level,255)))
        colors = ['ff0000ff','00ff0080','0000ffff','00000000']
        pattern = dict(type='pattern',width=2,height=2,rgba_hex=''.join(colors))
        changed = self.invoke(dict(command='document.edit',document=d,expected_revision=1,operations=[dict(op='fill',id='fill',paint=pattern)]))['document']
        result = self.invoke(dict(command='document.export',document=changed,format='png'))
        _,_,pixels,_ = png_pixels(base64.b64decode(result['data']))
        expected = bytes.fromhex(''.join(colors[(y%2)*2+x%2] for y in range(4) for x in range(4)))
        self.assertEqual(pixels,expected)
        self.assertEqual(d,original)
        self.assertEqual(changed['items'][0]['content']['dither'],'none')
        failure = self.invoke(dict(command='document.edit',document=changed,expected_revision=2,operations=[dict(op='fill',id='fill',paint=dict(type='radial',center=[0,0],radius=-1,stops=linear['stops']))]),expected=1)
        self.assertEqual(failure['operation_index'],0)

    def test_gradient_stroke_export_and_unrepresentable_paints_fail_explicitly(self):
        d = self.invoke(dict(command='document.create',id='stroke-fixture',kind='vector',width=8,height=8))
        paint = dict(type='radial',center=[4,4],radius=4,space='linear_rgb',stops=[dict(offset=0,color=[255,0,0,255]),dict(offset=1,color=[0,0,255,0])])
        content = dict(type='vector',geometry=dict(shape='rect',x=1,y=1,width=6,height=6),stroke=dict(color=paint,width=2))
        d = self.invoke(dict(command='document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=dict(id='outline',content=content))]))['document']
        root = ET.fromstring(self.invoke(dict(command='document.export',document=d,format='svg'))['data'])
        field = root.find(NS+'defs/'+NS+'radialGradient')
        shape = root.find(NS+'g/'+NS+'rect')
        self.assertEqual(shape.get('fill'),'none')
        self.assertEqual(shape.get('stroke'),f"url(#{field.get('id')})")
        self.assertEqual(shape.get('stroke-width'),'2')
        self.assertEqual(field.get('color-interpolation'),'linearRGB')
        for paint in [dict(type='pattern',width=1,height=1,rgba_hex='ff0000ff'),dict(type='freeform',anchors=[dict(point=[0,0],color=[255,0,0,255]),dict(point=[8,8],color=[0,0,255,255])])]:
            d['items'][0]['content']['stroke']['color'] = paint
            failure = self.invoke(dict(command='document.export',document=d,format='svg'),expected=1)
            self.assertEqual(failure['code'],'UNSUPPORTED')


if __name__ == '__main__':
    unittest.main()
