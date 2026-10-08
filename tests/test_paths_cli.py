"""Original analytic primitive/path/query fixtures, with independent SVG and curve arithmetic."""
import base64
import copy
import json
import math
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
import test_editing_cli as editing
from test_layout_cli import shape_contains, local_point
from test_mcp import Client

NS='{http://www.w3.org/2000/svg}'


def cubic(points,t):
    return [sum(w*p[i] for w,p in zip(((1-t)**3,3*(1-t)**2*t,3*(1-t)*t*t,t**3),points)) for i in (0,1)]


def svg_commands(element):
    tokens=element.get('d').split();commands=[];i=0
    while i<len(tokens):
        op=tokens[i];i+=1
        if op in ('M','L'):
            commands.append(dict(verb='move' if op=='M' else 'line',to=[float(tokens[i]),float(tokens[i+1])]))
            i+=2
        elif op=='C':
            n=list(map(float,tokens[i:i+6]));i+=6;commands.append(dict(verb='cubic',control1=n[:2],control2=n[2:4],to=n[4:]))
        elif op=='Z':commands.append(dict(verb='close'))
        else:raise AssertionError(op)
    return commands


def rectangle_path(x,y,w,h,reverse=False):
    points=[[x,y],[x+w,y],[x+w,y+h],[x,y+h]]
    if reverse:points=[points[0]]+points[:0:-1]
    return [dict(verb='move',to=points[0])]+[dict(verb='line',to=p) for p in points[1:]]+[dict(verb='close')]


class PathCliTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke

    def document(self,w=40,h=32):return self.invoke(dict(command='document.create',id='path-fixture',kind='vector',width=w,height=h))
    def item(self,g,id='shape',**kw):return dict(id=id,content=dict(type='vector',geometry=g,fill=[30,140,210,255]),**kw)
    def edit(self,d,ops,expected=0):
        r=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=ops),expected)
        return r if expected else r['document']
    def path(self,d,action,id='shape',expected=0):return self.edit(d,[dict(op='path',id=id,action=action)],expected)
    def geometry(self,d,id='shape'):return next(i['content']['geometry'] for i in d['items'] if i['id']==id)
    def pixels(self,d):
        p=self.invoke(dict(command='document.export',document=d,format='png'));return editing.png_pixels(base64.b64decode(p['data']))[:3]
    def saved(self,d):
        p=self.invoke(dict(command='document.export',document=d,format='snapshot'))
        return self.invoke(dict(command='document.validate',document=json.loads(p['data'])))
    def svg(self,d):return ET.fromstring(self.invoke(dict(command='document.export',document=d,format='svg'))['data'])
    def query(self,d,**q):return self.invoke(dict(command='document.query',document=d,query=q))

    def test_fractional_parametric_shapes_persist_and_svg_preserves_expansion(self):
        shapes=[dict(shape='polygon',points=[[1.25,2.5],[10.75,2.5],[8.5,9.25],[2,8]]),dict(shape='regular_polygon',cx=14.5,cy=12.25,radius=7.5,sides=6,rotation=30.25),dict(shape='star',cx=14.5,cy=12.25,outer_radius=9.5,inner_radius=4.25,points=5,rotation=-90.25)]
        for g in shapes:
            d=self.edit(self.document(),[dict(op='add',item=self.item(g))]);self.assertEqual(self.geometry(self.saved(d)),g)
            converted=self.path(d,dict(type='convert'));commands=self.geometry(converted)['commands']
            if g['shape']=='polygon':expected=g['points']
            else:
                count=g.get('sides',g.get('points',0)*2)
                expected=[]
                for i in range(count):
                    angle=math.radians(g['rotation'])+2*math.pi*i/count
                    radius=g.get('radius',g.get('outer_radius')) if g['shape']!='star' or i%2==0 else g['inner_radius']
                    expected.append([g['cx']+radius*math.cos(angle),g['cy']+radius*math.sin(angle)])
            for actual,wanted in zip(commands,expected):
                for a,b in zip(actual['to'],wanted):self.assertAlmostEqual(a,b,places=11)
            self.assertEqual(len(commands),len(expected)+1);self.assertEqual(commands[-1],dict(verb='close'))
            root=self.svg(d);self.assertEqual(svg_commands(root.find(NS+'g/'+NS+'path')),commands)
            self.assertEqual(self.pixels(d),self.pixels(converted))
            inspected=self.invoke(dict(command='document.inspect',document=d))['items'][0]
            bounds=[min(p[0] for p in expected),min(p[1] for p in expected),max(p[0] for p in expected),max(p[1] for p in expected)]
            for a,b in zip(inspected['geometry_bounds'],bounds):self.assertAlmostEqual(a,b,places=11)
            self.assertEqual(inspected['geometry'],g)

    def test_rounded_corners_normalize_proportionally_and_keep_editable_parameters(self):
        g=dict(shape='rounded_rect',x=2.25,y=3.5,width=18.5,height=12.25,radii=[10,20,6,4])
        d=self.edit(self.document(),[dict(op='add',item=self.item(g))]);converted=self.path(d,dict(type='convert'))
        commands=self.geometry(converted)['commands'];scale=min(1,18.5/30,12.25/26,18.5/10,12.25/14);r=[v*scale for v in g['radii']]
        k=4*(math.sqrt(2)-1)/3;right=20.75;bottom=15.75
        self.assertEqual(self.geometry(d),g);self.assertEqual(self.geometry(self.saved(d)),g)
        for a,b in zip(commands[0]['to'],[2.25+r[0],3.5]):self.assertAlmostEqual(a,b,places=13)
        self.assertEqual(len([c for c in commands if c['verb']=='cubic']),4)
        tr=commands[2]
        for actual,expected in ((tr['control1'],[right-r[1]+k*r[1],3.5]),(tr['control2'],[right,3.5+r[1]-k*r[1]]),(tr['to'],[right,3.5+r[1]])):
            for a,b in zip(actual,expected):self.assertAlmostEqual(a,b,places=13)
        self.assertEqual(svg_commands(self.svg(d).find(NS+'g/'+NS+'path')),commands)
        self.assertEqual(self.pixels(d),self.pixels(converted))
        w,h,p=self.pixels(d);self.assertEqual(p[(9*w+11)*4+3],255);self.assertEqual(p[(3*w+2)*4+3],0)
        sharp=dict(g,radii=[0]*4);base=dict(shape='rect',x=g['x'],y=g['y'],width=g['width'],height=g['height'])
        a=self.edit(self.document(),[dict(op='add',item=self.item(sharp))]);b=self.edit(self.document(),[dict(op='add',item=self.item(base))])
        self.assertEqual(self.pixels(a),self.pixels(b))

    def test_new_primitives_work_as_transformed_clips_and_reject_invalid_parameters(self):
        clip=dict(shape='regular_polygon',cx=12,cy=12,radius=8,sides=4,rotation=45)
        d=self.edit(self.document(),[dict(op='add',item=self.item(dict(shape='rect',x=0,y=0,width=30,height=28),clip=dict(geometry=clip,transform=[1,0,0,1,3,2])) )])
        w,h,p=self.pixels(d);self.assertEqual(p[(14*w+15)*4+3],255);self.assertEqual(p[(4*w+5)*4+3],0)
        root=self.svg(d);path=root.find('.//'+NS+'clipPath/'+NS+'path');self.assertIsNotNone(path)
        for y in range(6,21):
            for x in range(6,24):
                # Polygon is an axis-aligned square after a 45-degree four-sided rotation.
                xx,yy=local_point(path,(x+0.5,y+0.5));r=8/math.sqrt(2)
                if min(abs(xx-(12-r)),abs(xx-(12+r)),abs(yy-(12-r)),abs(yy-(12+r)))>0.75:
                    self.assertEqual(p[(y*w+x)*4+3],255 if abs(xx-12)<r and abs(yy-12)<r else 0)
        bad=[dict(shape='regular_polygon',cx=0,cy=0,radius=0,sides=4),dict(shape='regular_polygon',cx=0,cy=0,radius=3,sides=257),dict(shape='star',cx=0,cy=0,outer_radius=4,inner_radius=5,points=5),dict(shape='star',cx=0,cy=0,outer_radius=4,inner_radius=0,points=5),dict(shape='rounded_rect',x=0,y=0,width=4,height=0,radii=[0]*4),dict(shape='rounded_rect',x=0,y=0,width=4,height=4,radii=[-1,0,0,0]),dict(shape='polygon',points=[[1,1],[2,2]])]
        for g in bad:self.assertEqual(self.edit(self.document(),[dict(op='add',item=self.item(g))],1)['code'],'INVALID_DOCUMENT')
        # Equal star radii deliberately define an ordinary 2N-vertex polygon.
        g=dict(shape='star',cx=12,cy=12,outer_radius=7,inner_radius=7,points=4,rotation=0)
        star=self.edit(self.document(),[dict(op='add',item=self.item(g))]);regular=self.edit(self.document(),[dict(op='add',item=self.item(dict(shape='regular_polygon',cx=12,cy=12,radius=7,sides=8)))])
        self.assertEqual(self.pixels(star),self.pixels(regular))

    def test_degenerate_polygon_policy_and_ellipse_conversion_deviation(self):
        d=self.document()
        for points in ([[1,1]]*3,[[1,1],[2,2],[1,1]]):
            self.assertEqual(self.edit(d,[dict(op='add',item=self.item(dict(shape='polygon',points=points)))],1)['code'],'INVALID_DOCUMENT')
        collinear=self.edit(d,[dict(op='add',item=self.item(dict(shape='polygon',points=[[2,3],[5,3],[10,3]])))])
        self.assertEqual(self.pixels(collinear)[2],bytes(40*32*4))
        repeated=self.edit(d,[dict(op='add',item=self.item(dict(shape='polygon',points=[[2,3],[10,3],[10,9],[2,9],[2,3]])))])
        self.assertEqual(self.pixels(repeated)[2][(5*40+5)*4+3],255)
        ellipse=self.edit(d,[dict(op='add',item=self.item(dict(shape='ellipse',cx=15,cy=12,rx=8,ry=5)))])
        path=self.path(ellipse,dict(type='convert'));commands=self.geometry(path)['commands'];self.assertEqual(len(commands),6)
        start=commands[0]['to'];largest=0
        for c in commands[1:5]:
            controls=[start,c['control1'],c['control2'],c['to']]
            for i in range(1001):
                x,y=cubic(controls,i/1000);radial=math.hypot((x-15)/8,(y-12)/5)
                largest=max(largest,abs(radial-1))
            start=c['to']
        self.assertLess(largest,0.0003);self.assertGreater(largest,0.0002)
        self.assertEqual(self.geometry(ellipse)['shape'],'ellipse')

    def fixture(self):
        commands=[dict(verb='move',to=[2,4]),dict(verb='cubic',control1=[5,1],control2=[12,18],to=[18,6]),dict(verb='line',to=[22,10])]
        return self.edit(self.document(),[dict(op='add',item=self.item(dict(shape='path',commands=commands)))])

    def test_exact_split_preserves_curve_at_independent_parameters_and_svg(self):
        d=self.fixture();original=self.geometry(d)['commands'];control=[original[0]['to'],original[1]['control1'],original[1]['control2'],original[1]['to']]
        for t in (0.01,0.25,0.5,0.83,0.999):
            split=self.path(d,dict(type='split',command_index=1,t=t));c=self.geometry(split)['commands']
            a=[c[0]['to'],c[1]['control1'],c[1]['control2'],c[1]['to']];b=[c[1]['to'],c[2]['control1'],c[2]['control2'],c[2]['to']]
            for n in range(201):
                u=n/200
                result=cubic(a,u/t) if u<=t else cubic(b,(u-t)/(1-t))
                for x,y in zip(result,cubic(control,u)):self.assertAlmostEqual(x,y,places=11)
            self.assertEqual(svg_commands(self.svg(split).find(NS+'g/'+NS+'path')),c)
            self.assertEqual(self.geometry(self.saved(split)),self.geometry(split))
        line=self.path(d,dict(type='split',command_index=2,t=0.375));self.assertEqual(self.geometry(line)['commands'][2]['to'],[19.5,7.5])
        self.assertEqual(self.geometry(d)['commands'],original)

    def test_reverse_open_cubics_closed_seams_and_explicit_join_modes(self):
        d=self.fixture();reversed_doc=self.path(d,dict(type='reverse'));c=self.geometry(reversed_doc)['commands'];old=self.geometry(d)['commands']
        self.assertEqual(c[0]['to'],[22,10]);self.assertEqual(c[1]['to'],[18,6]);self.assertEqual(c[2]['control1'],old[1]['control2']);self.assertEqual(c[2]['control2'],old[1]['control1']);self.assertEqual(c[2]['to'],[2,4])
        self.assertEqual(self.geometry(self.path(reversed_doc,dict(type='reverse'))),self.geometry(d))
        closed=self.edit(self.document(),[dict(op='add',item=self.item(dict(shape='path',commands=rectangle_path(2,3,8,6))))])
        reverse=self.path(closed,dict(type='reverse'));self.assertEqual(self.geometry(reverse)['commands'][0]['to'],[2,3]);self.assertEqual(self.pixels(closed),self.pixels(reverse))
        self.assertEqual(self.geometry(self.path(reverse,dict(type='reverse'))),self.geometry(closed))
        second=[dict(verb='move',to=[22,10]),dict(verb='cubic',control1=[25,12],control2=[30,12],to=[32,6])]
        joined_source=self.edit(self.document(),[dict(op='add',item=self.item(dict(shape='path',commands=old+second)))])
        joined=self.path(joined_source,dict(type='join',first=0,second=1));self.assertEqual(self.geometry(joined)['commands'],old+second[1:])
        separated=copy.deepcopy(joined_source);separated['items'][0]['content']['geometry']['commands'][3]['to']=[23,11]
        self.assertEqual(self.path(separated,dict(type='join',first=0,second=1),expected=1)['code'],'INVALID_OPERATION')
        bridge=self.path(separated,dict(type='join',first=0,second=1,mode='bridge',close=True));c=self.geometry(bridge)['commands']
        self.assertEqual(c[3],dict(verb='line',to=[23,11]));self.assertEqual(c[-1],dict(verb='close'))

    def test_compound_winding_reversal_self_intersection_and_touching_persist(self):
        contours=rectangle_path(2,2,20,20)+rectangle_path(6,6,12,12)+rectangle_path(22,2,8,20)
        for rule in ('nonzero','even_odd'):
            item=self.item(dict(shape='path',commands=contours));item['content']['fill_rule']=rule
            d=self.edit(self.document(),[dict(op='add',item=item)])
            reverse=self.path(d,dict(type='reverse',contours=[1]))
            for doc,hole in ((d,rule=='even_odd'),(reverse,True)):
                self.assertEqual(self.pixels(doc),self.pixels(self.saved(doc)))
                w,h,p=self.pixels(doc);root=self.svg(doc);path=root.find(NS+'g/'+NS+'path')
                path.set('clip-rule',path.get('fill-rule'))
                for y in range(h):
                    for x in range(w):
                        expected=(2<=x<30 and 2<=y<22) and not (hole and 6<=x<18 and 6<=y<18)
                        self.assertEqual(p[(y*w+x)*4+3],255 if expected else 0)
                        self.assertEqual(shape_contains(path,(x+0.5,y+0.5)),expected)
            self.assertEqual(self.geometry(reverse)['commands'][5]['to'],[6,6])
        # A single crossed contour has two visible lobes; points safely away from boundaries agree.
        bow=[dict(verb='move',to=[2,2]),dict(verb='line',to=[18,18]),dict(verb='line',to=[2,18]),dict(verb='line',to=[18,2]),dict(verb='close')]
        d=self.edit(self.document(),[dict(op='add',item=self.item(dict(shape='path',commands=bow)))])
        for doc in (d,self.path(d,dict(type='reverse')),self.saved(d)):
            w,h,p=self.pixels(doc);path=self.svg(doc).find(NS+'g/'+NS+'path')
            for y in range(32):
                for x in range(40):
                    if min(abs(x-y),abs(x+y+1-20),abs(x+0.5-2),abs(x+0.5-18),abs(y+0.5-2),abs(y+0.5-18))>1.5:
                        self.assertEqual(p[(y*w+x)*4+3],255 if shape_contains(path,(x+0.5,y+0.5)) else 0)

    def test_query_type_bounds_anchor_coordinates_and_locked_ancestor_filters(self):
        d=self.fixture();d=self.edit(d,[dict(op='group',ids=['shape'],new_id='g'),dict(op='transform',id='g',matrix=[2,0,0,2,3,1]),dict(op='add',item=self.item(dict(shape='star',cx=5,cy=5,outer_radius=3,inner_radius=1,points=5),id='star')),dict(op='add',item=self.item(dict(shape='rect',x=30,y=2,width=4,height=4),id='hidden',visible=False))])
        self.assertEqual(self.query(d,types=['vector'],shapes=['star'])['ids'],['star'])
        self.assertEqual(self.query(d,types=['vector'],region=dict(bounds=[0,0,12,12],relation='contains'))['ids'],['star'])
        self.assertEqual(self.query(d,types=['vector'],region=dict(bounds=[6,8,8,10]))['ids'],['shape'])
        anchors=self.query(d,types=['vector'],anchor_bounds=[6,8,8,10])['items'][0]['anchors']
        self.assertEqual(len(anchors),1);self.assertEqual(anchors[0]['command_index'],0);self.assertEqual(anchors[0]['world'],[7,9]);self.assertEqual(anchors[0]['local'],[2,4])
        self.assertIn('hidden',self.query(d,types=['vector'],visible_only=False)['ids'])
        locked=self.edit(d,[dict(op='properties',id='g',locked=True)])
        self.assertNotIn('shape',self.query(locked,types=['vector'])['ids'])
        self.assertIn('shape',self.query(locked,types=['vector'],include_locked=True)['ids'])
        failed=self.edit(locked,[dict(op='properties',id='star',name='candidate'),dict(op='path',id='shape',action=dict(type='anchors',points=[dict(command_index=0,to=[1,1])]))],1)
        self.assertEqual((failed['code'],failed['operation_index']),('LOCKED',1));self.assertEqual(next(i for i in locked['items'] if i['id']=='star')['name'],'')
        child_locked=self.edit(d,[dict(op='properties',id='shape',locked=True)])
        self.assertNotIn('g',self.query(child_locked)['ids'])
        group=self.query(child_locked,types=['group'],include_locked=True)['items'][0]
        self.assertEqual(group['id'],'g');self.assertFalse(group['effective_locked']);self.assertTrue(group['edit_blocked_by_locks'])
        failed=self.edit(child_locked,[dict(op='transform',id='g',matrix=[1,0,0,1,5,0])],1)
        self.assertEqual(failed['code'],'LOCKED')

    def test_selected_anchor_handle_edits_world_space_and_atomic_failures(self):
        d=self.fixture();d=self.edit(d,[dict(op='transform',id='shape',matrix=[0,2,-2,0,30,1])])
        query=self.query(d,shapes=['path'],include_anchors=True);a=query['items'][0]['anchors'];self.assertEqual([v['command_index'] for v in a],[0,1,2])
        original=copy.deepcopy(d)
        changed=self.path(d,dict(type='anchors',space='world',points=[dict(command_index=0,to=[20,7]),dict(command_index=1,to=[16,41])]))
        c=self.geometry(changed)['commands'];self.assertEqual(c[0]['to'],[3,5]);self.assertEqual(c[1]['to'],[20,7]);self.assertEqual(c[1]['control1'],[6,2]);self.assertEqual(c[1]['control2'],[14,19])
        handles=self.path(changed,dict(type='handles',command_index=1,space='world',control1=[18,9],control2=[12,31]));c=self.geometry(handles)['commands'];self.assertEqual(c[1]['control1'],[4,6]);self.assertEqual(c[1]['control2'],[15,9])
        stationary=self.path(d,dict(type='anchors',move_handles=False,points=[dict(command_index=0,to=[10,10])]))
        self.assertEqual(self.geometry(stationary)['commands'][1]['control1'],self.geometry(d)['commands'][1]['control1'])
        for action in (dict(type='anchors',points=[dict(command_index=0,to=[1,1]),dict(command_index=99,to=[2,2])]),dict(type='anchors',points=[dict(command_index=0,to=[1,1])]*2),dict(type='handles',command_index=0,control1=[1,1]),dict(type='split',command_index=0,t=0.5),dict(type='split',command_index=1,t=1),dict(type='reverse',contours=[0,0]),dict(type='join',first=0,second=0)):
            self.assertEqual(self.path(d,action,expected=1)['code'],'INVALID_OPERATION')
        self.assertEqual(d,original)

    def test_mcp_query_edit_history_replay_and_snapshot_geometry(self):
        client=Client();self.addCleanup(client.close);client.initialize()
        with tempfile.TemporaryDirectory() as root:
            args=dict(session_root=root,session_id='path-edit')
            d=self.fixture();client.success('session.create',**args,request_id='create',document=d)
            discovered=client.success('document.query',document=d,query=dict(types=['vector'],include_anchors=True));self.assertEqual(discovered['ids'],['shape'])
            action=dict(type='edit',operations=[dict(op='path',id='shape',action=dict(type='split',command_index=1,t=0.4)),dict(op='path',id='shape',action=dict(type='anchors',points=[dict(command_index=2,to=[20,7])]))])
            result=client.success('session.apply',**args,request_id='reshape',expected_revision=0,action=action)['document']
            self.assertEqual(self.geometry(self.saved(result)),self.geometry(result));self.assertNotEqual(self.geometry(d),self.geometry(result))
            undone=client.success('session.apply',**args,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'];self.assertEqual(self.geometry(undone),self.geometry(d));self.assertEqual(self.pixels(undone),self.pixels(d))
            replay=client.success('session.apply',**args,request_id='reshape',expected_revision=0,action=action);self.assertEqual(replay['current_revision'],2);self.assertEqual(replay['document'],result)
            client.success('session.verify',**args)


if __name__=='__main__':unittest.main()
