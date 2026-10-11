"""Original resource fixtures through creation, durable edits, delivery and reopen."""
import base64
from contextlib import closing
from fractions import Fraction as F
import hashlib
import json
import unittest
import xml.etree.ElementTree as ET

import test_agent_workspace as workspace
from test_editing_cli import png_pixels
from test_mcp import Client
from test_vector_overviews import rect, scene
from pdf_reader import Pdf


def original_grid():
    d = scene(128, [rect(f'grid{i}', 8+i % 100, 8+i//100, .5, .5,
                         [0,100,200,255]) for i in range(5000)])
    d['height'] = 96
    d['vector_canvas']['size_px'][1] = 96
    return d


def expected_grid():
    return bytes(c for y in range(96) for x in range(128)
                 for c in ([0,100,200,64] if 8 <= x < 108 and 8 <= y < 58 else [0,0,0,0]))


class VectorResourceAcceptance(unittest.TestCase):
    setUp = workspace.AgentWorkspaceTests.setUp
    cli = workspace.AgentWorkspaceTests.cli
    save = workspace.AgentWorkspaceTests.save
    ref = workspace.AgentWorkspaceTests.ref

    def specialist(self, client, command, **arguments):
        result = client.tool('run', command=command, arguments=arguments)
        self.assertFalse(result['isError'],result)
        return result['structuredContent']['result']

    def pixels(self, reference, size, **options):
        r = self.cli('document.preview', document=reference,
                     options=dict(max_size=list(size), **options))
        return png_pixels(base64.b64decode(r['artifact']['data']))[:3]

    def publish(self, reference, name):
        r = self.cli('document.publish', document=reference,
                     output=dict(file_name=name, format='snapshot'))
        raw = (self.root/name).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), r['sha256'])
        return dict(file_path=name, sha256=r['sha256']), raw

    def test_10000_square_atomic_million_point_rejection_and_saved_precision(self):
        self.save(scene())
        added = self.cli('session.apply', session_id='work', request_id='draw', expected_revision=0,
            action=dict(type='edit', operations=[
                dict(op='add', item=rect('fractional',9990.125,.125,.375,.625,[255,0,0,255])),
                dict(op='add', item=rect('marker',4000,4000,1000,1000,[0,0,255,255])),
                dict(op='transform', id='fractional', matrix=[1,0,0,1,.000123,-.000321])]))
        before = self.cli('session.read', session_id='work')
        self.cli('session.apply', session_id='work', request_id='oversize', expected_revision=1,
            action=dict(type='edit', operations=[dict(op='properties', id='marker', name='must roll back'),
                dict(op='vector_canvas', action=dict(type='set',origin=[0,0],size=[1000000,1000000],unit='pt'))]),
            error='INVALID_CANVAS')
        self.assertEqual(self.cli('session.read', session_id='work'), before)
        self.cli('session.receipt',session_id='work',request_id='oversize',error='REQUEST_NOT_FOUND')
        file, raw = self.publish(self.ref(1), 'large-board.json')
        self.assertEqual(json.loads(raw), added['document'])
        expected = [F('9990.125123'),F('.124679'),F('9990.500123'),F('.749679')]
        for reference in (self.ref(1), file):
            inspection = self.cli('document.inspect',document=reference)
            bounds = inspection['items'][0]['geometry_bounds']
            self.assertTrue(all(abs(F(a)-b) < F(1,10**7) for a,b in zip(bounds,expected,strict=True)))
        original = self.pixels(self.ref(1),(100,100))
        self.assertEqual(original,self.pixels(file,(100,100)))
        w,h,p = original
        self.assertEqual((w,h),(100,100))
        for y in range(h):
            for x in range(w):
                pixel = p[(y*w+x)*4:(y*w+x+1)*4]
                if 40 <= x < 50 and 40 <= y < 50:
                    self.assertEqual(pixel,bytes([0,0,255,255]))
                elif not ((39 <= x < 51 and 39 <= y < 51) or (98 <= x and y < 2)):
                    self.assertEqual(pixel,bytes(4))
        self.cli('document.publish',document=file,output=dict(file_name='large-board.json',format='snapshot'),error='OUTPUT_EXISTS')
        self.assertEqual((self.root/'large-board.json').read_bytes(),raw)
        self.assertEqual(self.cli('session.read',session_id='work'),before)
        self.assertTrue(self.cli('session.verify',session_id='work')['valid'])

    def test_20000_square_reopen_preserves_physical_page_and_original_controls(self):
        d = scene(20000,[rect('physical',1001.25,991.25,202.5,305,[255,0,0,255])])
        created = self.save(d)['document']
        file, raw = self.publish(self.ref(),'physical.json')
        self.assertEqual(json.loads(raw),created)
        expected = bytes(c for y in range(200) for x in range(200)
                         for c in ([255,0,0,255] if 1001.25 <= 100*x+50 < 1203.75
                                   and 991.25 <= 100*y+50 < 1296.25 else [0,0,0,0]))
        with closing(Client(('--tools','core'),workspace=self.root)) as client:
            client.initialize()
            self.assertEqual(self.specialist(client,'document.validate',document=file),created)
            for reference in (self.ref(),file):
                inspected = client.success('document.inspect',document=reference)
                self.assertEqual(inspected['items'][0]['geometry_bounds'],[1001.25,991.25,1203.75,1296.25])
                svg = ET.fromstring(self.specialist(client,'document.export',document=reference,format='svg')['data'])
                self.assertEqual([svg.attrib[k] for k in ('width','height')],['20000pt','20000pt'])
                page = Pdf(self.specialist(client,'document.export',document=reference,format='pdf')).pages[0]
                self.assertEqual([v*page['UserUnit'] for v in page['MediaBox']],[0,0,20000,20000])
                self.assertEqual(self.pixels(reference,(200,200),render_options=dict(antialias='none')),(200,200,expected))
        self.assertEqual((self.root/'physical.json').read_bytes(),raw)
        self.assertEqual(self.cli('session.read',session_id='work')['document'],created)

    def test_original_5000_geometry_delivery_reopen_edit_retry_and_undo(self):
        receipt = self.save(original_grid(),response_mode='compact')
        self.assertEqual(receipt['document_summary']['item_count'],5000)
        self.assertLessEqual(len(json.dumps(receipt).encode()),8192)
        initial = self.cli('document.validate',document=self.ref())
        self.assertEqual(len(initial['items']),5000)
        area = F(0)
        for i,item in enumerate(initial['items']):
            g = item['content']['geometry']
            self.assertEqual([g[k] for k in ('x','y','width','height')],[8+i % 100,8+i//100,.5,.5])
            self.assertEqual(item['transform'],[1,0,0,1,0,0])
            area += F(g['width'])*F(g['height'])
        self.assertEqual(area,1250)
        file, raw = self.publish(self.ref(),'many.json')
        self.assertEqual(json.loads(raw),initial)
        self.assertEqual(self.pixels(self.ref(),(128,96)),(128,96,expected_grid()))
        self.assertEqual(self.pixels(file,(128,96)),(128,96,expected_grid()))
        svg = ET.fromstring(self.cli('document.export',document=file,format='svg')['data'])
        rectangles = svg.findall('.//{http://www.w3.org/2000/svg}rect')
        paths = Pdf(self.cli('document.export',document=file,format='pdf')).paths()
        self.assertEqual(len(rectangles),5000)
        self.assertEqual(len(paths),5000)
        for i,(rectangle,path) in enumerate(zip(rectangles,paths,strict=True)):
            x,y = 8+i % 100,8+i//100
            self.assertEqual([float(rectangle.attrib[k]) for k in ('x','y','width','height')],[x,y,.5,.5])
            self.assertEqual(path['path'],[('m',[[x,y]]),('l',[[x+.5,y]]),('l',[[x+.5,y+.5]]),('l',[[x,y+.5]]),('h',[])])
            self.assertEqual(path['color'],[0,100/255,200/255])
        with closing(Client(('--tools','core'),workspace=self.root)) as client:
            client.initialize()
            change = dict(session_id='work',request_id='hide-last',expected_revision=0,
                          action=dict(type='edit',operations=[dict(op='properties',id='grid4999',visible=False)]),response_mode='compact')
            edited = client.success('session.apply',**change)
            replay = client.success('session.apply',**change)
            self.assertTrue(replay['replayed'])
            self.assertEqual(replay['document_ref'],edited['document_ref'])
            expected = bytearray(expected_grid())
            expected[(57*128+107)*4:(57*128+108)*4] = bytes(4)
            self.assertEqual(self.pixels(self.ref(1),(128,96)),(128,96,expected))
            client.success('session.apply',session_id='work',request_id='undo',expected_revision=1,action=dict(type='undo'),response_mode='compact')
            self.assertEqual(client.success('session.read',session_id='work')['document'],dict(initial,revision=2))
            self.assertTrue(self.specialist(client,'session.verify',session_id='work')['valid'])
        self.assertEqual(self.pixels(self.ref(2),(128,96)),(128,96,expected_grid()))
        self.assertEqual((self.root/'many.json').read_bytes(),raw)


if __name__ == '__main__':
    unittest.main()
