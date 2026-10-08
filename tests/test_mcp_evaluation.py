"""Ten fixed read-only agent questions, solved and checked through MCP tool calls."""
import base64
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from test_cli import ROOT
from test_mcp import Client
from test_editing_cli import png_pixels


class EvaluationTests(unittest.TestCase):
    def test_ten_independent_readonly_evaluation_answers(self):
        with tempfile.TemporaryDirectory() as directory:
            c=Client()
            try:
                c.initialize();s=dict(session_root=str(Path(directory)),session_id='evaluation')
                d=c.success('document.create',id='evaluation-artwork',kind='vector',width=32,height=20)
                def board(id,w,h,x):return dict(id=id,transform=[1,0,0,1,x,2],content=dict(type='frame',frame=dict(role='artboard',width=w,height=h)))
                def rect(id,parent,name,x,y,w,h,color):return dict(id=id,parent=parent,name=name,content=dict(type='vector',geometry=dict(shape='rect',x=x,y=y,width=w,height=h),fill=color))
                items=[board('wide',12,12,2),board('tall',8,10,20),rect('warm','wide','Warm',2,3,6,4,[200,40,10,255]),rect('cool','tall','Cool',1,2,4,5,[10,80,200,255])]
                d=c.success('document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=i) for i in items])['document']
                c.success('session.create',**s,request_id='create',document=d)
                c.success('session.apply',**s,request_id='shift',expected_revision=0,action=dict(type='edit',operations=[dict(op='transform',id='warm',matrix=[1,0,0,1,1,0])]))
                c.success('session.apply',**s,request_id='save',expected_revision=1,action=dict(type='snapshot',name='moved'))
                c.success('session.apply',**s,request_id='undo',expected_revision=2,action=dict(type='undo'))
                # All evaluation work from here is read-only and can be repeated independently.
                initial=c.success('session.receipt',**s,request_id='create')['document']
                moved=c.success('session.receipt',**s,request_id='shift')['document']
                inspection=c.success('document.inspect',document=moved)
                delta=c.success('session.diff',**s,from_revision=0,to_revision=1,compare_pixels=True)
                changed_leaf=next(v['id'] for v in delta['items'] if 'transform' in v['fields'])
                right=next(v['geometry_bounds'][2] for v in inspection['items'] if v['id']==changed_leaf)
                history=[];cursor=None
                while True:
                    page=c.success('session.history',**s,limit=1,**({} if cursor is None else dict(after_revision=cursor)))
                    history+=page['entries']
                    if not page['has_more']:break
                    cursor=page['next_after_revision']
                undo=next(h for h in history if h['action']=='undo')
                restored=c.success('session.diff',**s,from_revision=0,to_revision=undo['revision'],compare_pixels=True)
                exports=c.tool('artboard.export',document=initial,format='png')
                self.assertEqual(sum(v['type']=='image' for v in exports['content']),2)
                boards={v['id']:png_pixels(base64.b64decode(v['artifact']['data'])) for v in exports['structuredContent']['result']['artifacts']}
                large=max(boards,key=lambda k:boards[k][0]*boards[k][1])
                occupied={k:sum(v[2][n+3]>0 for n in range(0,len(v[2]),4)) for k,v in boards.items()}
                painted_board=max(occupied,key=occupied.get)
                name=next(i['name'] for i in initial['items'] if i.get('parent')==painted_board)
                saved=c.success('session.read',**s,snapshot='moved')
                self.assertFalse(c.success('document.diff',before=moved,after=saved['document'])['changed'])
                shift=next(h for h in history if h['action']=='edit')
                receipt=c.success('session.receipt',**s,request_id=shift['request_id'])
                self.assertEqual(receipt['document'],moved);self.assertEqual(receipt['current_revision'],3)
                answers=[str(int(right)),str(delta['rendered_pixels']['changed_pixels']),undo['action'],large,name,str(saved['revision']),str(not restored['changed'] and restored['rendered_pixels']['changed_pixels']==0),str(boards[large][0]*boards[large][1]-occupied[large]),str(sum(v[0]*v[1] for v in boards.values())),shift['request_id']]
                questions=ET.fromstring((ROOT/'examples/mcp_evaluation.md').read_text(encoding='utf8').split('```xml\n',1)[1].split('```',1)[0]).findall('qa_pair')
                self.assertEqual(len(questions),10)
                self.assertEqual(answers,[q.findtext('answer') for q in questions])
                self.assertEqual(c.success('session.verify',**s)['revision'],3)
            finally:c.close()


if __name__=='__main__':unittest.main()
