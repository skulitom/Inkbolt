"""Combined page geometry and named-ink contracts for original print fixtures."""
import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
import pdf_reader
import test_boards_cli as boards
import test_ink_delivery_cli as inks
import test_swatches_cli as swatches
from test_mcp import Client


class PrepressTests(unittest.TestCase):
    invoke=boards.BoardCliTests.invoke
    board=boards.BoardCliTests.board

    def fixture(self):
        d=self.invoke(dict(command='document.create',id='prepress',kind='vector',width=512,height=128))
        d['swatches']={
            'process':inks.cmyk([.5,.25,0,0]),
            'a':inks.cmyk([0,0,1,0],name='Same label',spot=True),
            'b':inks.cmyk([0,0,0,1],name='Same label',spot=True)}
        for i in range(2):
            id='page'+str(i)
            d['items'].append(self.board(id,192,48,x=31+256*i,y=17,
                bleed=dict(left=8+8*i,right=16-8*i,top=8+8*i,bottom=16-8*i)))
            for n,(color,mode) in enumerate([('process','knockout'),('a','preserve'),('b','preserve_nonzero')]):
                item=swatches.rectangle(id+'-'+color,inks.reference(color,tint=.5,overprint=mode),x=-8+n*8,w=32)
                item['parent']=id;d['items'].append(item)
        return self.invoke(dict(command='document.validate',document=d))

    def pdf(self,d,**options):
        return self.invoke(dict(command='document.export',document=d,format='pdf',pdf_options=dict(color='native_inks',**options)))

    def test_combined_boxes_units_order_spots_and_overprint(self):
        d=self.fixture();before=copy.deepcopy(d)
        for ppi in [1,72,96,300]:
            d['resolution_ppi']=ppi
            for bleed in [False,True]:
                for ids in [['page0','page1'],['page1','page0']]:
                    a=self.pdf(d,artboards=dict(type='ids',ids=ids),include_bleed=bleed);pdf=pdf_reader.Pdf(a)
                    self.assertEqual([r['artboard_id'] for r in a['pages']],ids)
                    for page,id,r in zip(pdf.pages,ids,a['pages']):
                        i=int(id[-1]);left,right,top,bottom=(8+8*i,16-8*i,8+8*i,16-8*i) if bleed else (0,0,0,0)
                        w,h=192+left+right,48+top+bottom;unit=max(1,math.ceil(max(w,h)*72/ppi/14400));factor=72/ppi/unit
                        for key in ['MediaBox','BleedBox','CropBox']:
                            for actual,expected in zip(page[key],[0,0,w*factor,h*factor]):self.assertAlmostEqual(actual,expected,places=10)
                        for actual,expected in zip(page['TrimBox'],[left*factor,bottom*factor,(w-right)*factor,(h-top)*factor]):self.assertAlmostEqual(actual,expected,places=10)
                        self.assertEqual(page['UserUnit'],unit);self.assertEqual(page['Group']['CS'],'DeviceCMYK')
                        self.assertEqual(r['logical_size'],[w,h]);self.assertEqual(r['physical_points'],[w*(72/ppi),h*(72/ppi)])
                    painted=inks.painted(pdf);self.assertEqual(len(painted),6)
                    self.assertEqual([p['state']['op'] for p in painted],[False,True,True]*2)
                    self.assertEqual([p['state']['OPM'] for p in painted],[0,0,1]*2)
                    self.assertEqual([p['values'] for p in painted],[[.25,.125,0,0],[.5],[.5]]*2)
                    self.assertEqual([p['space'][1] for p in painted if isinstance(p['space'],list)],['Inkbolt.a','Inkbolt.b']*2)
                    spaces=[o for o in pdf.objects.values() if isinstance(o,list) and o[0]=='Separation']
                    self.assertEqual(len(spaces),2)
                    self.assertTrue(a['swatches']['native_ink_preservation'])
                    self.assertEqual(json.loads(self.invoke(dict(command='document.export',document=d,format='snapshot'))['data']),d)
        d['resolution_ppi']=before['resolution_ppi'];self.assertEqual(d,before)

    def test_native_pages_are_independent_of_canvas_placement(self):
        d=self.fixture();options=dict(artboards=dict(type='ids',ids=['page1','page0']),include_bleed=True)
        original=self.pdf(d,**options)
        for item in d['items']:
            if item['content']['type']=='frame':item['transform']=[0,-2,3,0,400,80]
        self.assertEqual(self.pdf(d,**options),original)

    def test_unselected_unsupported_ink_is_excluded_but_selected_page_fails_atomically(self):
        d=self.fixture();d['swatches']['off']=swatches.process(space='srgb',components=[1,0,0])
        item=swatches.rectangle('unsupported',inks.reference('off',overprint='preserve'));item['parent']='page1';d['items'].append(item)
        self.assertTrue(self.pdf(d,artboards=dict(type='ids',ids=['page0']),include_bleed=True)['swatches']['native_ink_preservation'])
        with tempfile.TemporaryDirectory() as root:
            output=dict(output_root=root,file_name='pages.pdf',format='pdf',pdf_options=dict(color='native_inks',artboards=dict(type='all'),include_bleed=True))
            error=self.invoke(dict(command='document.publish',document=d,output=output),1)
            self.assertEqual(error['code'],'UNSUPPORTED');self.assertFalse((Path(root)/'pages.pdf').exists())

    def test_agent_history_preserves_page_geometry_and_ink_controls(self):
        d=self.fixture();frame=copy.deepcopy(d['items'][0]['content']['frame']);frame['bleed']=dict(top=3,right=5,bottom=7,left=9)
        client=Client();self.addCleanup(client.close);client.initialize()
        with tempfile.TemporaryDirectory() as root:
            session=dict(session_root=root,session_id='prepress')
            client.success('session.create',**session,request_id='create',document=d)
            action=dict(type='edit',operations=[dict(op='frame',id='page0',frame=frame),dict(op='swatch_convert',id='a',kind='process')])
            changed=client.success('session.apply',**session,request_id='edit',expected_revision=0,action=action)['document']
            output=dict(output_root=root,file_name='pages.pdf',format='pdf',pdf_options=dict(color='native_inks',artboards=dict(type='ids',ids=['page1','page0']),include_bleed=True))
            receipt=client.success('session.publish',**session,expected_revision=1,output=output)
            page=pdf_reader.Pdf((Path(root)/'pages.pdf').read_bytes()).pages[1]
            self.assertEqual(page['TrimBox'],[6.75,5.25,150.75,41.25]);self.assertEqual(receipt['pages'][1]['logical_size'],[206,58])
            self.assertEqual(client.success('session.apply',**session,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'],dict(d,revision=2))
            self.assertEqual(client.success('session.apply',**session,request_id='redo',expected_revision=2,action=dict(type='redo'))['document'],dict(changed,revision=3))
            self.assertTrue(client.success('session.apply',**session,request_id='edit',expected_revision=0,action=action)['replayed'])
            self.assertTrue(client.success('session.verify',**session)['valid'])
            self.assertEqual(client.tool('session.publish',**session,expected_revision=3,output=output)['structuredContent']['error']['code'],'OUTPUT_EXISTS')


if __name__=='__main__':unittest.main()
