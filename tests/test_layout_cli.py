"""Independent evaluation of exported nested clips and real CLI hierarchy queries."""
import json
import base64
import re
import unittest
import xml.etree.ElementTree as ET
import test_editing_cli as editing_cli
from test_editing_cli import png_pixels

NS="{http://www.w3.org/2000/svg}"


def local_point(element, point):
    text=element.get('transform')
    if text is None:
        return point
    values=[float(v) for v in re.fullmatch(r'matrix\(([^)]+)\)',text)[1].split()]
    a,b,c,d,e,f=values
    x,y=point[0]-e,point[1]-f
    determinant=a*d-b*c
    return ((d*x-c*y)/determinant,(-b*x+a*y)/determinant)


def shape_contains(element, point):
    x,y=local_point(element,point)
    tag=element.tag.removeprefix(NS)
    if tag=='rect':
        left,top,width,height=(float(element.get(k)) for k in ('x','y','width','height'))
        return left<=x<left+width and top<=y<top+height
    if tag!='path':
        raise AssertionError(f'Unexpected test shape {tag}')
    tokens=element.get('d').split()
    i=0
    contours=[]
    current=[]
    while i<len(tokens):
        verb=tokens[i];i+=1
        if verb=='M':
            assert not current
            current=[(float(tokens[i]),float(tokens[i+1]))];i+=2
        elif verb=='L':
            current.append((float(tokens[i]),float(tokens[i+1])));i+=2
        elif verb=='Z':
            contours.append(current);current=[]
        else:
            raise AssertionError('Independent clip fixture only uses polygons')
    assert not current
    crossings=winding=0
    for contour in contours:
        for (x1,y1),(x2,y2) in zip(contour,contour[1:]+contour[:1]):
            if (y1<=y<y2) or (y2<=y<y1):
                intersection=x1+(y-y1)*(x2-x1)/(y2-y1)
                if intersection>x:
                    crossings+=1
                    winding+=1 if y2>y1 else -1
    return crossings%2==1 if element.get('clip-rule')=='evenodd' else winding!=0


def svg_alpha(root,point):
    clips={element.get('id'):element for element in root.iter(NS+'clipPath')}
    def visit(element,point):
        if element.get('display')=='none':
            return 0.0
        point=local_point(element,point) if element.tag in (NS+'svg',NS+'g') else point
        if element.get('clip-path'):
            key=re.fullmatch(r'url\(#([^)]+)\)',element.get('clip-path'))[1]
            if not any(shape_contains(child,point) for child in clips[key]):
                return 0.0
        if element.tag in (NS+'rect',NS+'path'):
            return float(element.get('fill-opacity','1')) if shape_contains(element,point) and element.get('fill')!='none' else 0.0
        if element.tag not in (NS+'svg',NS+'g'):
            return 0.0
        alpha=0.0
        for child in element:
            source=visit(child,point)
            alpha=source+alpha*(1-source)
        return alpha*float(element.get('opacity','1'))
    return visit(root,point)


class LayoutCliTests(unittest.TestCase):
    invoke=editing_cli.EditingCliTests.invoke

    def fixture(self):
        d=self.invoke(dict(command='document.create',id='clips',kind='vector',width=32,height=32))
        commands=[]
        for left,top,right,bottom in [(0,0,24,24),(8,8,12,12)]:
            commands += [{'verb':'move','to':[left,top]},{'verb':'line','to':[right,top]},{'verb':'line','to':[right,bottom]},{'verb':'line','to':[left,bottom]},{'verb':'close'}]
        operations=[
            {'op':'add','item':{'id':'inkbolt-clip-1','content':{'type':'vector','geometry':{'shape':'rect','x':0,'y':0,'width':32,'height':32},'fill':[20,160,90,255]}}},
            {'op':'clip','id':'inkbolt-clip-1','clip':{'geometry':{'shape':'path','commands':commands},'fill_rule':'even_odd','transform':[1,0,0,1,2,2]}},
            {'op':'group','ids':['inkbolt-clip-1'],'new_id':'frame','name':'Frame','role':'layer'},
            {'op':'clip','id':'frame','clip':{'geometry':{'shape':'rect','x':4,'y':4,'width':20,'height':20}}},
            {'op':'transform','id':'frame','matrix':[0,1,-1,0,28,0]},
            {'op':'properties','id':'frame','opacity':0.5}
        ]
        return self.invoke(dict(command='document.edit',document=d,expected_revision=0,operations=operations))['document']

    def test_nested_compound_clip_svg_matches_independent_coverage_and_png(self):
        d=self.fixture()
        exported=self.invoke(dict(command='document.export',document=d,format='svg'))
        root=ET.fromstring(exported['data'])
        ids=[element.get('id') for element in root.iter() if element.get('id')]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertEqual(len(list(root.iter(NS+'clipPath'))),2)
        self.assertEqual(root.find(NS+'g').get('id'),'frame')
        self.assertEqual(root.find(NS+'g/'+NS+'g').get('id'),'inkbolt-clip-1')
        self.assertEqual(root.find(NS+'g').get('transform'),'matrix(0 1 -1 0 28 0)')
        self.assertEqual(root.find(NS+'g').get('style'),'isolation:isolate')
        image=self.invoke(dict(command='document.export',document=d,format='png'))
        width,height,pixels,_=png_pixels(base64.b64decode(image['data']))
        self.assertEqual((width,height),(32,32))
        opaque=0
        for y in range(32):
            for x in range(32):
                alpha=int(svg_alpha(root,(x+0.5,y+0.5))*255+0.5)
                expected=bytes([20,160,90,alpha]) if alpha else bytes(4)
                self.assertEqual(pixels[(y*width+x)*4:(y*width+x+1)*4],expected)
                opaque+=bool(alpha)
        self.assertEqual(opaque,20*20-4*4)
        saved=self.invoke(dict(command='document.export',document=d,format='snapshot'))
        reopened=self.invoke(dict(command='document.validate',document=json.loads(saved['data'])))
        self.assertEqual(reopened,d)
        self.assertEqual(self.invoke(dict(command='document.export',document=reopened,format='svg')),exported)

    def test_queries_are_readonly_and_invalid_selection_is_structured(self):
        d=self.fixture()
        selected=self.invoke(dict(command='document.select',document=d,ids=['frame','inkbolt-clip-1']))
        self.assertEqual(selected['items'][1]['parent'],'frame')
        self.assertEqual(selected['items'][1]['world_transform'],[0,1,-1,0,28,0])
        self.assertEqual(self.invoke(dict(command='document.validate',document=d)),d)
        self.assertEqual(self.invoke(dict(command='document.select',document=d,ids=['missing']),1)['code'],'NOT_FOUND')
        self.assertEqual(self.invoke(dict(command='document.select',document=d,ids=['frame','frame']),1)['code'],'INVALID_OPERATION')
        request=dict(command='document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='group_options',id='frame',isolated=False)])
        passthrough=self.invoke(request)['document']
        before=self.invoke(dict(command='document.export',document=d,format='png'))
        after=self.invoke(dict(command='document.export',document=passthrough,format='png'))
        self.assertEqual(before,after)


if __name__=='__main__':
    unittest.main()
