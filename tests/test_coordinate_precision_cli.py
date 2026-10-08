"""Independent binary64, rational geometry, XML and exchange fidelity fixtures."""
import base64
import copy
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import random
import re
import struct
import tempfile
import unittest
import xml.etree.ElementTree as ET
import test_editing_cli as editing
import test_svg_import_cli as importing
import test_transform_policies_cli as transforms
from test_mcp import Client

NS='{http://www.w3.org/2000/svg}'
NUM=r'[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?'
def numbers(s):return [float(v) for v in re.findall(NUM,s)]
def bits(v):return struct.pack('>d',float(v))
def scalars(v):
    if isinstance(v,dict):return [x for k in sorted(v) for x in scalars(v[k])]
    if isinstance(v,list):return [x for a in v for x in scalars(a)]
    return [float(v)] if isinstance(v,(int,float)) and not isinstance(v,bool) else []
def controls(g):
    return [v for c in g['commands'] for k in ['control1','control2','to'] if k in c for v in c[k]]
def leaf(d):return next(i for i in d['items'] if i['content']['type']=='vector')
def vector(g,id='art',**kw):return dict(id=id,content=dict(type='vector',geometry=g,fill=[30,100,210,255]),**kw)
def rectangle(x=-3.125,y=-2.375,w=9.625,h=7.875):return dict(shape='rect',x=x,y=y,width=w,height=h)
def corpus():
    fixed=[0.,-0.,math.ulp(0.),-math.ulp(0.),float.fromhex('0x0.fffffffffffffp-1022'),float.fromhex('0x1p-1022'),
        .1,-.1,1/3,-1/3,23.952095808383234,-15.146750185997725,math.nextafter(1,0),math.nextafter(1,2),
        -32768.,32768.,math.nextafter(-32768.,0),math.nextafter(32768.,0)]
    rng=random.Random(57123)
    for exponent in [-1074,-1022,-996,-600,-300,-100,-32,-20,-10,-1,0,7,14]:
        for sign in [-1,1]:fixed.append(sign*math.ldexp(1+rng.random(),exponent))
    return fixed


class CoordinatePrecisionTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    pixels=importing.SvgImportTests.pixels
    def document(self,items=None,w=64,h=48):
        d=self.invoke(dict(command='document.create',id='coordinate-fidelity',kind='vector',width=w,height=h))
        return self.edit(d,[dict(op='add',item=i) for i in items]) if items else d
    def edit(self,d,ops,expected=0):
        result=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=ops),expected)
        return result if expected else result['document']
    def exported(self,d):return self.invoke(dict(command='document.export',document=d,format='svg'))['data']
    def imported(self,text):return self.invoke(dict(command='svg.import',id='coordinates-imported',source=dict(kind='text',text=text)))
    def exact(self,a,b,zero_sign=True):
        self.assertEqual(len(a),len(b))
        for x,y in zip(a,b):
            if not zero_sign and x==y==0:continue
            self.assertEqual(bits(x),bits(y),(x,y))
    def snapshot(self,d):
        value=self.invoke(dict(command='document.export',document=d,format='snapshot'))
        reopened=self.invoke(dict(command='document.validate',document=json.loads(value['data'])))
        self.assertEqual(reopened,d);self.exact(scalars(reopened),scalars(d));return reopened

    def test_binary64_corpus_survives_json_snapshot_svg_and_import_without_rounding(self):
        values=corpus();commands=[dict(verb='move',to=[values[0],values[1]])]
        commands += [dict(verb='line',to=[v,values[-i-1]]) for i,v in enumerate(values[2:])]
        g=dict(shape='path',commands=commands);d=self.document([vector(g)]);original=copy.deepcopy(d)
        self.exact(controls(leaf(d)['content']['geometry']),controls(g))
        self.snapshot(d);text=self.exported(d);path=ET.fromstring(text).find('.//'+NS+'path')
        self.exact(numbers(path.attrib['d']),controls(g))
        imported=self.imported(text)['document'];self.exact(controls(leaf(imported)['content']['geometry']),controls(g))
        self.snapshot(imported);self.assertEqual(d,original)

    def test_rectangles_and_ellipses_preserve_negative_fractional_parameters(self):
        for g in [rectangle(-15.146750185997725,math.nextafter(-.1,0),23.952095808383234,7/3),
            dict(shape='ellipse',cx=-123.45678901234567,cy=.12345678901234567,rx=9.87654321098765,ry=1.2345678901234567),
            rectangle(-32768,math.nextafter(32767,0),.001,.125)]:
            d=self.document([vector(g)]);self.snapshot(d);text=self.exported(d)
            element=ET.fromstring(text).find('.//'+NS+('rect' if g['shape']=='rect' else 'ellipse'))
            for key,value in g.items():
                if key!='shape':self.exact([float(element.attrib[key])],[value])
            imported=leaf(self.imported(text)['document'])['content']['geometry'];self.exact(scalars(imported),scalars(g))

    def test_matrix_components_and_nested_world_points_match_rational_algebra(self):
        matrices=[[1.125,.03125,-.0625,.875,19.125,12.625],[.9375,-.125,.25,1.0625,-.3125,.1875],[1.1,.03,-.04,.9,-.12345678901234567,.9876543210987654]]
        g=rectangle();items=[dict(id='outer',transform=matrices[0],content=dict(type='group')),
            dict(id='inner',parent='outer',transform=matrices[1],content=dict(type='group')),vector(g,parent='inner',transform=matrices[2])]
        d=self.document(items);text=self.exported(d);root=ET.fromstring(text)
        for id,m in zip(['outer','inner','art'],matrices):self.exact(numbers(root.find('.//'+NS+f'g[@id="{id}"]').attrib['transform']),m)
        total=transforms.matrix_product(matrices[0],transforms.matrix_product(matrices[1],matrices[2]))
        corners=[[g['x'],g['y']],[g['x']+g['width'],g['y']],[g['x'],g['y']+g['height']],[g['x']+g['width'],g['y']+g['height']]]
        wanted=[transforms.point(total,p) for p in corners]
        bounds=[min(p[0] for p in wanted),min(p[1] for p in wanted),max(p[0] for p in wanted),max(p[1] for p in wanted)]
        for doc in [d,self.imported(text)['document']]:
            item=leaf(doc);info=next(i for i in self.invoke(dict(command='document.inspect',document=doc))['items'] if i['id']==item['id'])
            for a,b in zip(info['world_transform'],total):self.assertAlmostEqual(a,float(b),delta=1e-11)
            for a,b in zip(info['geometry_bounds'],bounds):self.assertAlmostEqual(a,b,delta=1e-11)
        self.assertEqual(self.pixels(d,4),self.pixels(self.imported(text)['document'],4))

    def test_cubic_handles_and_compound_contours_remain_exact_in_svg(self):
        cs=[dict(verb='move',to=[-12.123456789012345,-3.25]),dict(verb='cubic',control1=[-9.999999999999998,6.123456789012345],control2=[-.000000000000001,-8.75],to=[11.345678901234567,-.5]),dict(verb='line',to=[8.125,12.25]),dict(verb='close'),dict(verb='move',to=[-2.375,3.125]),dict(verb='line',to=[4.625,3.125]),dict(verb='line',to=[1.125,7.875]),dict(verb='close')]
        d=self.document([vector(dict(shape='path',commands=cs),transform=[1,0,0,1,20.125,15.375])])
        d['items'][0]['content']['fill_rule']='even_odd';self.snapshot(d)
        for _ in range(3):
            text=self.exported(d);path=ET.fromstring(text).find('.//'+NS+'path')
            self.exact(numbers(path.attrib['d']),controls(dict(commands=cs)))
            self.assertEqual(path.attrib['fill-rule'],'evenodd')
            d=self.imported(text)['document'];self.exact(controls(leaf(d)['content']['geometry']),controls(dict(commands=cs)))

    def test_relative_smooth_and_quadratic_normalization_has_rational_error_bound(self):
        # Decimal fractions are evaluated independently as exact rational numbers.
        path='m-7.1,-3.3 c.2,-.4 1.7,2.6 3.9,1.2 s2.3,-1.4 4.7,.9 q1.1,2.2 3.3,4.4 t-2.7,1.3'
        d=self.imported(importing.svg('<path id="p" d="'+path+'"/>'))['document']
        cs=leaf(d)['content']['geometry']['commands'];p=[F('-7.1'),F('-3.3')]
        add=lambda a,b:[x+y for x,y in zip(a,map(F,b))]
        c1=add(p,['.2','-.4']);c2=add(p,['1.7','2.6']);end=add(p,['3.9','1.2'])
        expected=[p,c1,c2,end];p=end
        c1=[2*p[i]-c2[i] for i in range(2)];c2=add(p,['2.3','-1.4']);end=add(p,['4.7','.9']);expected +=[c1,c2,end];p=end
        q=add(p,['1.1','2.2']);end=add(p,['3.3','4.4'])
        expected +=[[p[i]+F(2,3)*(q[i]-p[i]) for i in range(2)],[end[i]+F(2,3)*(q[i]-end[i]) for i in range(2)],end];p=end
        q=[2*p[i]-q[i] for i in range(2)];end=add(p,['-2.7','1.3'])
        expected +=[[p[i]+F(2,3)*(q[i]-p[i]) for i in range(2)],[end[i]+F(2,3)*(q[i]-end[i]) for i in range(2)],end]
        for a,b in zip(controls(dict(commands=cs)),[v for p in expected for v in p]):self.assertAlmostEqual(a,float(b),delta=1e-12)
        exchanged=leaf(self.imported(self.exported(d))['document'])['content']['geometry']
        self.exact(controls(exchanged),controls(dict(commands=cs)))

    def test_units_and_fractional_negative_viewbox_match_exact_mapping(self):
        body='<rect id="r" x="-1.23456789mm" y="-.123456789cm" width="3.141592653589793pt" height=".03125in"/>'
        result=self.imported(importing.svg(body,'width="64" height="48" viewBox="-10.125 -5.375 32.5 24.25" preserveAspectRatio="none"'))
        d=result['document'];g=leaf(d)['content']['geometry']
        desired=[F('-1.23456789')*960/254,F('-.123456789')*9600/254,F('3.141592653589793')*4/3,F('.03125')*96]
        for a,b in zip([g['x'],g['y'],g['width'],g['height']],desired):self.assertAlmostEqual(a,float(b),delta=1e-12)
        expected=[F(64)/F('32.5'),0,0,F(48)/F('24.25'),F('10.125')*64/F('32.5'),F('5.375')*48/F('24.25')]
        root=d['items'][0]
        for a,b in zip(root['transform'],expected):self.assertAlmostEqual(a,float(b),delta=1e-12)
        reopened=self.imported(self.exported(d))['document'];self.exact(scalars(leaf(reopened)['content']['geometry']),scalars(g))
        self.assertEqual(self.pixels(d,4),self.pixels(reopened,4))

    def test_gradient_and_clip_numbers_keep_fractional_coordinate_fields(self):
        paint=dict(type='linear',start=[-3.123456789012345,-.25],end=[12.345678901234567,7.125],transform=[1.125,.0625,-.03125,.875,.12345678901234567,-.9876543210987654],stops=[dict(offset=0,color=[20,60,190,255]),dict(offset=.12345678901234567,color=[180,20,60,128]),dict(offset=1,color=[240,180,30,255])])
        cs=[dict(verb='move',to=[-3.125,-2.25]),dict(verb='cubic',control1=[-.12345678901234567,8.125],control2=[8.875,-4.75],to=[11.625,5.125]),dict(verb='line',to=[-3.125,9.75]),dict(verb='close')]
        clip=dict(geometry=dict(shape='path',commands=cs),transform=[1.125,0,0,.875,-.12345678901234567,.9876543210987654],fill_rule='even_odd')
        item=vector(rectangle(),transform=[1,0,0,1,18.25,12.75],clip=clip);item['content']['fill']=paint
        d=self.document([item]);before=copy.deepcopy(d);self.snapshot(d);text=self.exported(d);root=ET.fromstring(text)
        gradient=root.find('.//'+NS+'linearGradient')
        self.exact([float(gradient.attrib[k]) for k in ['x1','y1','x2','y2']],paint['start']+paint['end'])
        self.exact(numbers(gradient.attrib['gradientTransform']),paint['transform'])
        self.exact([float(s.attrib['offset']) for s in gradient], [v['offset'] for v in paint['stops']])
        clipxml=root.find('.//'+NS+'clipPath');self.exact(numbers(clipxml.find(NS+'path').attrib['d']),controls(dict(commands=cs)))
        imported=self.imported(text)['document'];actual=leaf(imported)
        self.exact(scalars(actual['content']['fill']),scalars(d['items'][0]['content']['fill']))
        owner=next(i for i in imported['items'] if i.get('clip'));self.exact(controls(owner['clip']['geometry']),controls(dict(commands=cs)))
        self.exact(owner['clip']['transform'],clip['transform']);self.assertEqual(d,before)
        self.assertEqual(self.pixels(d,3),self.pixels(imported,3))

    def test_repeated_exchange_keeps_local_scalars_world_bounds_and_pixels(self):
        d=self.document([vector(rectangle(),transform=[1.125,.0625,-.03125,.875,23.952095808383234,15.146750185997725])])
        g=leaf(d)['content']['geometry'];original=copy.deepcopy(d);pixels=self.pixels(d,4)
        first=next(v for v in self.invoke(dict(command='document.inspect',document=d))['items'] if v['id']=='art')['geometry_bounds']
        for _ in range(5):
            d=self.imported(self.exported(d))['document'];self.snapshot(d)
            self.exact(scalars(leaf(d)['content']['geometry']),scalars(g));self.assertEqual(self.pixels(d,4),pixels)
            bounds=next(v for v in self.invoke(dict(command='document.inspect',document=d))['items'] if v['id']==leaf(d)['id'])['geometry_bounds']
            for a,b in zip(bounds,first):self.assertAlmostEqual(a,b,delta=1e-11)
        self.assertEqual(original['items'][0]['content']['geometry'],g)

    def test_fractional_rectangle_interiors_and_exteriors_match_exact_geometry(self):
        g=rectangle();matrix=[1,0,0,1,9.25,7.125];d=self.document([vector(g,transform=matrix)],w=24,h=20)
        left,top=F(g['x'])+F(matrix[4]),F(g['y'])+F(matrix[5]);right,bottom=left+F(g['width']),top+F(g['height'])
        for scale in [1,2,4]:
            w,h,p=self.pixels(d,scale);other=self.pixels(self.imported(self.exported(d))['document'],scale)
            self.assertEqual((w,h,p),other)
            for y in range(h):
                for x in range(w):
                    area=max(F(0),min(F(x+1,scale),right)-max(F(x,scale),left))*max(F(0),min(F(y+1,scale),bottom)-max(F(y,scale),top))*scale**2
                    # Display coverage is not exact geometric cell area. Prove
                    # fully contained/excluded cells independently; partial edge
                    # samples keep their renderer contract and must survive
                    # exchange unchanged (the complete image equality above).
                    alpha=p[(y*w+x)*4+3]
                    if area==0:self.assertEqual(alpha,0)
                    elif area==1:self.assertEqual(alpha,255)
                    else:self.assertTrue(0<alpha<255)
                    if p[(y*w+x)*4+3]:self.assertEqual(list(p[(y*w+x)*4:(y*w+x)*4+3]),[30,100,210])

    def test_source_file_and_create_only_publication_preserve_coordinates(self):
        d=self.document([vector(rectangle(-15.146750185997725,-.1,23.952095808383234,7.875))]);text=self.exported(d)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);p=root/'source.svg';p.write_text(text,encoding='utf8');old=p.read_bytes();time=p.stat().st_mtime_ns
            imported=self.invoke(dict(command='svg.import',id='file-coordinates',source=dict(kind='file',source_path=str(p))))
            self.assertEqual(imported['source']['sha256'],hashlib.sha256(old).hexdigest())
            self.assertEqual((p.read_bytes(),p.stat().st_mtime_ns),(old,time))
            self.exact(scalars(leaf(imported['document'])['content']['geometry']),scalars(leaf(d)['content']['geometry']))
            output=dict(output_root=directory,file_name='new.svg',format='svg')
            receipt=self.invoke(dict(command='document.publish',document=d,output=output));self.assertEqual((root/'new.svg').read_bytes(),old)
            self.assertEqual(receipt['sha256'],hashlib.sha256(old).hexdigest())
            self.assertEqual(self.invoke(dict(command='document.publish',document=d,output=output),1)['code'],'OUTPUT_EXISTS')

    def test_nonfinite_out_of_bounds_singular_reject_and_fractional_canvas_preserve(self):
        d=self.document([vector(rectangle())]);before=copy.deepcopy(d)
        for x in [math.nextafter(32768,math.inf),-32769,math.inf,math.nan]:
            bad=copy.deepcopy(d);bad['items'][0]['content']['geometry']['x']=x
            self.invoke(dict(command='document.validate',document=bad),1)
        for attr in ['x="1e309" width="1"','x="-32769" width="1"','x="NaN" width="1"']:
            self.invoke(dict(command='svg.import',id='invalid',source=dict(kind='text',text=importing.svg('<rect '+attr+' height="1"/>'))),1)
        for extra in ['transform="scale(.000000001)"','transform="matrix(1 1 1 1 0 0)"']:
            self.invoke(dict(command='svg.import',id='invalid',source=dict(kind='text',text=importing.svg('<rect width="2" height="2" '+extra+'/>'))),1)
        imported=self.invoke(dict(command='svg.import',id='fractional',source=dict(kind='text',text=importing.svg('','width="16.25" height="16"'))))['document']
        self.assertEqual(imported['vector_canvas']['size_px'],[16.25,16]);self.assertEqual([imported['width'],imported['height']],[17,16])
        rendered=self.invoke(dict(command='document.render',document=imported));self.assertEqual([rendered['width'],rendered['height']],[17,16])
        self.assertEqual(d,before)

    def test_mcp_history_preserves_fractional_edits_and_undo_exactly(self):
        c=Client();self.addCleanup(c.close);c.initialize();d=self.document([vector(rectangle())])
        matrix=[1.125,.03125,-.0625,.875,23.952095808383234,-15.146750185997725]
        with tempfile.TemporaryDirectory() as directory:
            args=dict(session_root=directory,session_id='coordinates')
            c.success('session.create',**args,request_id='create',document=d)
            action=dict(type='edit',operations=[dict(op='transform',id='art',matrix=matrix)])
            moved=c.success('session.apply',**args,request_id='move',expected_revision=0,action=action)['document']
            self.exact(moved['items'][0]['transform'],matrix)
            c.success('session.apply',**args,request_id='undo',expected_revision=1,action=dict(type='undo'))
            redone=c.success('session.apply',**args,request_id='redo',expected_revision=2,action=dict(type='redo'))['document']
            self.exact(redone['items'][0]['transform'],matrix);self.snapshot(redone)
            read=self.invoke(dict(command='session.read',**args))['document'];self.assertEqual(read,redone)
            svg=c.success('document.export',document=read,format='svg')['data'];self.exact(numbers(ET.fromstring(svg).find('.//'+NS+'g[@id="art"]').attrib['transform']),matrix)
            self.assertEqual(c.success('session.apply',**args,request_id='move',expected_revision=0,action=action)['document'],moved)
            c.success('session.verify',**args)

    def test_precision_discovery_distinguishes_transport_normalization_and_coverage(self):
        p=self.invoke(dict(command='capabilities'))['coordinate_precision']
        self.assertEqual(p['storage'],'IEEE754_binary64')
        self.assertEqual(p['direct_transport_absolute_error'],0)
        self.assertEqual(p['geometry_control_point_absolute_limit'],32768)
        self.assertIn('binary64_arithmetic',p['svg_normalization'])
        self.assertIn('not_exact_geometric_pixel_area',p['preview'])


if __name__=='__main__':unittest.main()
