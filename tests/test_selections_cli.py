"""Independent set geometry, area integration, morphology and pixel application checks."""
import base64
import copy
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
import test_editing_cli as editing
from test_masks_cli import opacity,byte
from test_images_cli import png
from test_mcp import Client


def rect(x,y,w,h):return dict(shape='rect',x=x,y=y,width=w,height=h)


def polygon_area_in_pixel(points,x,y):
    """Clip an original polygon to a pixel with four half-planes, then shoelace area."""
    polygon=list(points)
    for axis,edge,lower in ((0,x,True),(0,x+1,False),(1,y,True),(1,y+1,False)):
        output=[]
        if not polygon:return 0.0
        for a,b in zip(polygon,polygon[1:]+polygon[:1]):
            ia=a[axis]>=edge if lower else a[axis]<=edge
            ib=b[axis]>=edge if lower else b[axis]<=edge
            if ia:output.append(a)
            if ia!=ib:
                t=(edge-a[axis])/(b[axis]-a[axis])
                output.append(tuple(a[k]+t*(b[k]-a[k]) for k in (0,1)))
        polygon=output
    return abs(sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(polygon,polygon[1:]+polygon[:1])))/2


def ellipse_area(cx,cy,rx,ry,x,y):
    # Midpoint numerical integration independent of the renderer's cubic approximation.
    n=2048
    total=0
    for k in range(n):
        xx=x+(k+0.5)/n
        a=1-((xx-cx)/rx)**2
        if a>0:
            dy=ry*math.sqrt(a)
            total+=max(0,min(y+1,cy+dy)-max(y,cy-dy))
    return total/n


class SelectionCliTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke

    def document(self,w=12,h=8,kind='raster'):
        return self.invoke(dict(command='document.create',id='selection-fixture',kind=kind,width=w,height=h))

    def edit(self,d,ops,expected=0,**kw):
        r=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=ops,**kw),expected)
        return r if expected else r['document']

    def values(self,d):return bytes.fromhex(d['selection']['gray_hex'])

    def pixels(self,d):
        r=self.invoke(dict(command='document.export',document=d,format='png'))
        return editing.png_pixels(base64.b64decode(r['data']))[2]

    def layer(self,id='pixels',w=12,h=8,**props):
        return dict(id=id,content=dict(type='raster',width=w,height=h,rgba_hex=bytes([60,150,210,255]).hex()*(w*h)),**props)

    def summary(self,d):return self.invoke(dict(command='document.inspect',document=d))['selection']

    def test_rectangle_set_operations_match_every_pixel_and_do_not_print(self):
        d=self.edit(self.document(),[dict(op='add',item=self.layer())]);original=self.pixels(d)
        expected=[0]*96
        for boundary,mode in ((rect(1,2,6,4),'replace'),(rect(5,1,5,4),'add'),(rect(3,3,4,4),'subtract'),(rect(2,0,7,6),'intersect')):
            d=self.edit(d,[dict(op='selection_shape',boundary=boundary,combine=mode)])
            b=[255 if boundary['x']<=x<boundary['x']+boundary['width'] and boundary['y']<=y<boundary['y']+boundary['height'] else 0 for y in range(8) for x in range(12)]
            expected=[b[i] if mode=='replace' else max(a,b[i]) if mode=='add' else max(0,a-b[i]) if mode=='subtract' else min(a,b[i]) for i,a in enumerate(expected)]
            self.assertEqual(self.values(d),bytes(expected));self.assertEqual(self.pixels(d),original)
        d=self.edit(d,[dict(op='selection_invert')]);expected=[255-v for v in expected]
        self.assertEqual(self.values(d),bytes(expected));info=self.summary(d)
        self.assertEqual(info['selected_pixels'],sum(v!=0 for v in expected));self.assertEqual(info['fully_selected_pixels'],sum(v==255 for v in expected))
        self.assertEqual(info['coverage_sum'],sum(expected)/255);self.assertEqual(info['sha256'],hashlib.sha256(bytes(expected)).hexdigest())
        snapshot=self.invoke(dict(command='document.export',document=d,format='snapshot'))
        self.assertEqual(self.invoke(dict(command='document.validate',document=json.loads(snapshot['data']))),d)
        cleared=self.edit(d,[dict(op='selection_set',selection=None)])
        delta=self.invoke(dict(command='document.diff',before=d,after=cleared,compare_pixels=True))
        self.assertEqual(delta['rendered_pixels']['changed_pixels'],0);self.assertEqual(delta['metadata'][0]['field'],'selection')

    def test_fractional_rectangles_polygons_and_binary_coverage_match_area(self):
        d=self.document(10,8)
        shapes=[(rect(1.25,2.5,5.5,3.25),[(1.25,2.5),(6.75,2.5),(6.75,5.75),(1.25,5.75)]),
                (dict(shape='polygon',points=[[1.25,1.5],[8.25,2.25],[4.25,6.5]]),[(1.25,1.5),(8.25,2.25),(4.25,6.5)]),
                (dict(shape='polygon',points=[[-2,0.25],[7,0.25],[7,2.5],[3,2.5],[3,7],[-2,7]]),[(-2,0.25),(7,0.25),(7,2.5),(3,2.5),(3,7),(-2,7)])]
        for boundary,points in shapes:
            selected=self.edit(d,[dict(op='selection_shape',boundary=boundary)])
            for i,actual in enumerate(self.values(selected)):
                expected=byte(polygon_area_in_pixel(points,i%10,i//10))
                self.assertLessEqual(abs(actual-expected),1,(boundary,i,actual,expected))
        binary=self.edit(d,[dict(op='selection_shape',boundary=rect(1.1,1.1,5.1,4.1),antialias=False)])
        self.assertEqual(self.values(binary),bytes(255 if 1<=x<6 and 1<=y<5 else 0 for y in range(8) for x in range(10)))
        # Explicit winding rule: twice around the same contour is full with nonzero, empty with even-odd.
        points=[[1,1],[6,1],[6,6],[1,6]]*2
        for rule,expected in (('nonzero',25),('even_odd',0)):
            selected=self.edit(d,[dict(op='selection_shape',boundary=dict(shape='polygon',points=points),fill_rule=rule)])
            self.assertEqual(self.summary(selected)['selected_pixels'],expected)

    def test_ellipse_antialiasing_matches_independent_area_integral(self):
        d=self.edit(self.document(10,8),[dict(op='selection_shape',boundary=dict(shape='ellipse',cx=4.25,cy=3.75,rx=3.1,ry=2.4))])
        self.assertTrue(any(0<v<255 for v in self.values(d)))
        for i,actual in enumerate(self.values(d)):
            expected=byte(ellipse_area(4.25,3.75,3.1,2.4,i%10,i//10))
            self.assertLessEqual(abs(actual-expected),1,(i,actual,expected))
        hard=self.edit(d,[dict(op='selection_shape',boundary=dict(shape='ellipse',cx=4.25,cy=3.75,rx=3.1,ry=2.4),antialias=False)])
        self.assertTrue(set(self.values(hard))<=set((0,255)))

    def test_empty_full_clear_inversion_and_partial_set_algebra(self):
        d=self.document(4,2)
        for selected in (False,True):
            filled=self.edit(d,[dict(op='selection_fill',selected=selected)])
            self.assertEqual(self.values(filled),bytes([255 if selected else 0])*8)
            self.assertEqual(self.summary(filled)['bounds'],[0,0,4,2] if selected else None)
            inverted=self.edit(filled,[dict(op='selection_invert')]);self.assertEqual(self.values(inverted),bytes([0 if selected else 255])*8)
            cleared=self.edit(inverted,[dict(op='selection_set',selection=None)]);self.assertIsNone(self.summary(cleared));self.assertNotIn('selection',cleared)
        outside=self.edit(d,[dict(op='selection_shape',boundary=rect(-5,-5,2,2))]);self.assertEqual(self.values(outside),bytes(8))
        original=[0,32,100,128,170,220,254,255]
        d=self.edit(d,[dict(op='selection_set',selection=dict(width=4,height=2,gray_hex=bytes(original).hex()))])
        operand=self.edit(d,[dict(op='selection_shape',boundary=rect(0.5,0,2,2))]);b=self.values(operand)
        for mode in ('add','subtract','intersect'):
            selected=self.edit(d,[dict(op='selection_shape',boundary=rect(0.5,0,2,2),combine=mode)])
            expected=[max(a,z) if mode=='add' else min(a,z) if mode=='intersect' else max(0,a-z) for a,z in zip(original,b)]
            self.assertEqual(self.values(selected),bytes(expected))

    def test_morphology_and_feather_match_direct_neighborhoods_and_bounds(self):
        w,h=9,7
        original=[255 if 3<=x<6 and 2<=y<5 else 0 for y in range(h) for x in range(w)];original[2*w+3]=80
        d=self.edit(self.document(w,h),[dict(op='selection_set',selection=dict(width=w,height=h,gray_hex=bytes(original).hex()))])
        def value(x,y):return original[y*w+x] if 0<=x<w and 0<=y<h else 0
        for radius in (0,1,2):
            for mode in ('expand','contract','feather'):
                result=self.edit(d,[dict(op='selection_refine',mode=mode,radius=radius)])
                expected=[]
                for y in range(h):
                    for x in range(w):
                        values=[value(x+dx,y+dy) for dy in range(-radius,radius+1) for dx in range(-radius,radius+1)]
                        if mode=='expand':v=max(values)
                        elif mode=='contract':v=min(values)
                        else:
                            v=sum(value(x+dx,y+dy)*(radius+1-abs(dx))*(radius+1-abs(dy)) for dy in range(-radius,radius+1) for dx in range(-radius,radius+1))
                            v=math.floor(Fraction(v,(radius+1)**4)+Fraction(1,2))
                        expected.append(v)
                self.assertEqual(self.values(result),bytes(expected))
                points=[(i%w,i//w) for i,v in enumerate(expected) if v]
                bounds=[min(x for x,y in points),min(y for x,y in points),max(x for x,y in points)+1,max(y for x,y in points)+1] if points else None
                self.assertEqual(self.summary(result)['bounds'],bounds)
        full=self.edit(d,[dict(op='selection_fill',selected=True),dict(op='selection_refine',mode='contract',radius=1)])
        self.assertEqual(self.summary(full)['bounds'],[1,1,8,6])

    def test_selection_to_mask_world_position_linkage_empty_and_replacement(self):
        d=self.edit(self.document(20,16),[dict(op='add',item=dict(id='g',transform=[2,0,0,2,2,2],content=dict(type='group'))),dict(op='add',item=self.layer(w=8,h=6,parent='g')),dict(op='selection_shape',boundary=rect(5,5,7,4))])
        saved=copy.deepcopy(d)
        for linked in (False,True):
            masked=self.edit(d,[dict(op='mask_from_selection',id='pixels',linked=linked)])
            mask=masked['items'][1]['mask'];self.assertEqual((mask['width'],mask['height']),(7,4));self.assertEqual(mask['gray_hex'],'ff'*28)
            self.assertEqual(mask['transform'],[0.5,0,0,0.5,1.5,1.5] if linked else [1,0,0,1,5,5])
            p=self.pixels(masked)
            for y in range(16):
                for x in range(20):self.assertEqual(p[(y*20+x)*4+3],255 if 5<=x<12 and 5<=y<9 else 0)
            moved=self.edit(masked,[dict(op='transform',id='g',matrix=[1,0,0,1,2,0],space='world')]);p=self.pixels(moved)
            for y in range(16):
                for x in range(20):self.assertEqual(p[(y*20+x)*4+3],255 if (7 if linked else 5)<=x<(14 if linked else 12) and 5<=y<9 else 0)
            self.assertEqual(self.edit(masked,[dict(op='mask_from_selection',id='pixels')],1)['code'],'INVALID_OPERATION')
            replaced=self.edit(masked,[dict(op='selection_fill',selected=False),dict(op='mask_from_selection',id='pixels',replace_existing=True)])
            self.assertEqual(replaced['items'][1]['mask']['gray_hex'],'00');self.assertEqual(self.pixels(replaced),bytes(20*16*4))
        self.assertEqual(d,saved)

    def test_mask_application_measured_native_alpha_preserves_other_properties(self):
        mask=dict(width=4,height=3,gray_hex='0080ff20'*3,transform=[1,0,0,1,3,2],linked=False,density=0.7,feather=1,invert=True,sampling='bilinear')
        rgba=bytes([60,150,210,173])*48
        item=self.layer(w=8,h=6,transform=[1,0,0,1,1,1],mask=mask,opacity=0.8,blend='multiply',clip=dict(geometry=rect(0,0,6,6)))
        item['content']['rgba_hex']=rgba.hex()
        d=self.edit(self.document(),[dict(op='add',item=item)]);original=copy.deepcopy(d)
        applied=self.edit(d,[dict(op='mask_apply',id='pixels')]);a=applied['items'][0]
        self.assertNotIn('mask',a)
        for key in ('id','transform','opacity','blend','clip','visible','locked'):self.assertEqual(a[key],d['items'][0][key])
        actual=bytes.fromhex(a['content']['rgba_hex'])
        for y in range(6):
            for x in range(8):
                alpha=byte(173/255*opacity(mask,(x+1.5,y+1.5)))
                expected=bytes([60,150,210,alpha]) if alpha else bytes(4)
                self.assertEqual(actual[(y*8+x)*4:][:4],expected)
        self.assertEqual(d,original)
        # Applying samples the native grid; half-pixel translation with nearest reconstruction is explicit.
        shifted=self.edit(d,[dict(op='transform',id='pixels',matrix=[1,0,0,1,0.25,0.5],space='world')])
        baked=self.edit(shifted,[dict(op='mask_apply',id='pixels')]);raw=bytes.fromhex(baked['items'][0]['content']['rgba_hex'])
        self.assertEqual(raw[3],byte(173/255*opacity(mask,(1.75,2.0))))
        disabled=self.edit(d,[dict(op='mask',id='pixels',mask=dict(mask,enabled=False))])
        self.assertEqual(self.edit(disabled,[dict(op='mask_apply',id='pixels')],1)['code'],'INVALID_OPERATION')
        removed=self.edit(disabled,[dict(op='mask',id='pixels',mask=None)])
        self.assertEqual(removed['items'][0]['content']['rgba_hex'],rgba.hex())

    def test_application_to_cropped_stored_image_preserves_sources_frame_and_clip(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source.png';store=root/'assets'
            rgba=bytes(v for y in range(4) for x in range(5) for v in (20+x*30,40+y*20,120,180+x*10))
            source.write_bytes(png(5,4,rgba));original=source.read_bytes()
            asset=self.invoke(dict(command='asset.import',source_path=str(source),store_root=str(store)))['asset']
            mask=dict(width=3,height=2,gray_hex='0080ffff4020',transform=[2,0,0,2,0,0])
            d=self.edit(self.document(10,8),[dict(op='asset_put',id='source',asset=asset),dict(op='add',item=dict(id='image',mask=mask,transform=[1,0,0,1,1,1],clip=dict(geometry=rect(0,0,4,4)),content=dict(type='image',asset_id='source',width=6,height=4,crop=dict(x=1,y=1,width=3,height=2),sampling='nearest')))])
            store_bytes={p.name:p.read_bytes() for p in store.iterdir()}
            self.assertEqual(self.edit(d,[dict(op='mask_apply',id='image')],1)['code'],'ASSET_ROOT_REQUIRED')
            applied=self.edit(d,[dict(op='mask_apply',id='image')],asset_root=str(store));item=applied['items'][0]
            self.assertEqual(item['transform'],[2,0,0,2,1,1]);self.assertEqual(item['clip']['transform'],[0.5,0,0,0.5,0,0])
            values=bytes.fromhex(mask['gray_hex']);actual=bytes.fromhex(item['content']['rgba_hex'])
            for y in range(2):
                for x in range(3):
                    src=rgba[((y+1)*5+x+1)*4:][:4];alpha=byte(src[3]/255*values[y*3+x]/255)
                    expected=src[:3]+bytes([alpha]) if alpha else bytes(4)
                    self.assertEqual(actual[(y*3+x)*4:][:4],expected)
            self.assertEqual(applied['assets'],d['assets']);self.assertEqual(source.read_bytes(),original)
            self.assertEqual({p.name:p.read_bytes() for p in store.iterdir()},store_bytes)
            before=self.invoke(dict(command='document.render',document=d,asset_root=str(store)))
            self.assertEqual(bytes.fromhex(before['data']),self.pixels(applied))

    def test_application_to_editable_gradient_fill_uses_unrounded_source_alpha(self):
        paint=dict(type='linear',start=[0,0],end=[8,0],stops=[dict(offset=0,color=[20,100,200,10]),dict(offset=1,color=[220,100,40,250])])
        mask=dict(width=8,height=4,gray_hex='80'*32)
        d=self.edit(self.document(8,4),[dict(op='add',item=dict(id='fill',mask=mask,content=dict(type='fill',width=8,height=4,paint=paint)))])
        result=self.edit(d,[dict(op='mask_apply',id='fill')]);c=result['items'][0]['content'];self.assertEqual(c['type'],'raster')
        raw=bytes.fromhex(c['rgba_hex'])
        for y in range(4):
            for x in range(8):
                t=(x+0.5)/8
                expected=bytes([byte((20+200*t)/255),100,byte((200-160*t)/255),byte((10+240*t)/255*128/255)])
                self.assertEqual(raw[(y*8+x)*4:][:4],expected)
        self.assertEqual(self.pixels(d),self.pixels(result))

    def test_sessions_mcp_selection_mask_application_undo_and_retry(self):
        c=Client();self.addCleanup(c.close);c.initialize()
        with tempfile.TemporaryDirectory() as root:
            args=dict(session_root=root,session_id='selection-mask')
            d=self.edit(self.document(),[dict(op='add',item=self.layer())]);c.success('session.create',**args,request_id='create',document=d)
            action=dict(type='edit',operations=[dict(op='selection_shape',boundary=rect(2,1,7,5)),dict(op='selection_refine',mode='feather',radius=1),dict(op='mask_from_selection',id='pixels')])
            selected=c.success('session.apply',**args,request_id='select',expected_revision=0,action=action)['document']
            c.success('session.apply',**args,request_id='save',expected_revision=1,action=dict(type='snapshot',name='editable'))
            applied=c.success('session.apply',**args,request_id='bake',expected_revision=2,action=dict(type='edit',operations=[dict(op='mask_apply',id='pixels'),dict(op='selection_set',selection=None)]))['document']
            self.assertEqual(self.pixels(selected),self.pixels(applied));self.assertNotIn('selection',applied)
            undo=c.success('session.apply',**args,request_id='undo',expected_revision=3,action=dict(type='undo'))['document']
            self.assertEqual(undo['selection'],selected['selection']);self.assertEqual(undo['items'],selected['items'])
            replay=c.success('session.apply',**args,request_id='select',expected_revision=0,action=action)
            self.assertEqual(replay['current_revision'],4);self.assertEqual(replay['document'],selected)
            saved=c.success('session.read',**args,snapshot='editable')['document'];self.assertEqual(saved['selection'],selected['selection'])
            diff=c.success('session.diff',**args,from_revision=0,to_revision=1,compare_pixels=True)
            self.assertTrue(any(m['field']=='selection' for m in diff['metadata']))
            c.success('session.verify',**args)

    def test_artboard_exports_discard_only_temporary_selection_coordinates(self):
        d=self.document(16,12,kind='vector')
        items=[dict(id='board',transform=[1,0,0,1,4,3],content=dict(type='frame',frame=dict(role='artboard',width=6,height=4,background=[20,60,180,255],bleed=dict(left=2)))),dict(id='shape',parent='board',content=dict(type='vector',geometry=rect(1,1,3,2),fill=[210,50,70,255]))]
        d=self.edit(d,[dict(op='add',item=i) for i in items]);plain=self.invoke(dict(command='artboard.export',document=d,format='png',include_bleed=True))
        selected=self.edit(d,[dict(op='selection_shape',boundary=rect(5,4,3,2))]);source=copy.deepcopy(selected)
        exported=self.invoke(dict(command='artboard.export',document=selected,format='png',include_bleed=True))
        self.assertEqual(plain['artifacts'],exported['artifacts']);self.assertEqual(selected,source)
        svg=self.invoke(dict(command='document.export',document=selected,format='svg'));self.assertTrue(any('Pixel selection' in loss for loss in svg['losses']))
        plain_svg=self.invoke(dict(command='artboard.export',document=d,format='svg',include_bleed=True))
        selected_svg=self.invoke(dict(command='artboard.export',document=selected,format='svg',include_bleed=True))
        self.assertEqual(plain_svg['artifacts'],selected_svg['artifacts'])

    def test_invalid_selections_resource_bounds_locks_and_atomicity(self):
        d=self.edit(self.document(),[dict(op='add',item=self.layer())]);original=copy.deepcopy(d)
        ops=[dict(op='selection_invert'),dict(op='selection_refine',mode='expand',radius=1),dict(op='mask_from_selection',id='pixels'),dict(op='selection_shape',boundary=rect(0,0,2,2),combine='add')]
        for op in ops:self.assertEqual(self.edit(d,[op],1)['code'],'INVALID_OPERATION')
        invalid=[dict(op='selection_set',selection=dict(width=1,height=1,gray_hex='ff')),dict(op='selection_set',selection=dict(width=12,height=8,gray_hex='zz'*96)),dict(op='selection_shape',boundary=rect(0,0,0,2)),dict(op='selection_shape',boundary=dict(shape='polygon',points=[[0,0],[1,1]]))]
        for op in invalid:
            error=self.edit(d,[dict(op='properties',id='pixels',name='pending'),op],1);self.assertEqual(error['operation_index'],1)
        self.assertEqual(d,original)
        selected=self.edit(d,[dict(op='selection_fill',selected=True)])
        self.assertEqual(self.edit(selected,[dict(op='selection_refine',mode='expand',radius=33)],1)['code'],'INVALID_DOCUMENT')
        locked=self.edit(selected,[dict(op='properties',id='pixels',locked=True)])
        self.assertEqual(self.edit(locked,[dict(op='mask_from_selection',id='pixels')],1)['code'],'LOCKED')
        crowded=self.document(512,256)
        boundary=dict(shape='polygon',points=[[0,0],[512,0],[512,256],[0,256]]*256)
        self.assertEqual(self.edit(crowded,[dict(op='selection_shape',boundary=boundary)],1)['code'],'RESOURCE_LIMIT')
        large=self.document(1024,1024)
        self.assertEqual(self.edit(large,[dict(op='selection_fill',selected=True)],1)['code'],'RESOURCE_LIMIT')
        # A valid large selection may exceed the separately bounded inline layer-mask grid.
        large=self.edit(self.document(512,256),[dict(op='add',item=self.layer(w=1,h=1)),dict(op='selection_fill',selected=True)])
        self.assertEqual(self.edit(large,[dict(op='mask_from_selection',id='pixels')],1)['code'],'RESOURCE_LIMIT')
        invalid=copy.deepcopy(selected);invalid['schema_version']=1
        self.assertEqual(self.invoke(dict(command='document.validate',document=invalid),1)['code'],'INVALID_DOCUMENT')


if __name__=='__main__':unittest.main()
