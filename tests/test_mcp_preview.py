"""Preview transport reconstruction, byte uniqueness and source preservation."""
from contextlib import closing
import base64
import copy
import hashlib
import json
import random
import unittest

import test_agent_workspace as workspace
from test_mcp import Client
from test_editing_cli import png_pixels
from test_ink_recipes_cli import channel, recipe
from test_profiles_cli import embedded
from cmyk_fixtures import proof_profile


from mcp_artifacts import restore, image_payloads


class McpPreviewTests(unittest.TestCase):
    setUp = workspace.AgentWorkspaceTests.setUp
    cli = workspace.AgentWorkspaceTests.cli
    document = workspace.AgentWorkspaceTests.document

    def check_preview(self, client, command, **arguments):
        expected = self.cli(command, **arguments)
        for mode in ('json','markdown','structured','preview'):
            with self.subTest(command=command,mode=mode):
                options={} if mode=='json' else dict(response_format=mode)
                result = client.tool('run', command=command, arguments=arguments, **options)
                self.assertFalse(result['isError'], result)
                self.assertEqual(restore(result), dict(ok=True, result=expected))
                wire = json.dumps(result, separators=(',', ':'))
                for data in set(image_payloads(expected)):
                    self.assertEqual(wire.count(data), 1)
                self.assertLessEqual(sum(v['type']=='image' for v in result['content']), 4)
                text=result['content'][0]['text']
                if mode in ('json','markdown'):
                    serialized=text if mode=='json' else text.split('```json\n',1)[1].rsplit('\n```',1)[0]
                    self.assertEqual(restore(result,json.loads(serialized)),dict(ok=True,result=expected))
                else:self.assertNotIn('```',text)
        return result, expected

    def test_single_png_roundtrip_independent_pixels_and_byte_reduction(self):
        rng = random.Random(1709); pixels = rng.randbytes(128*128*4)
        doc = self.cli('document.create',id='preview',kind='raster',width=128,height=128)
        doc['items'] = [dict(id='pixels',content=dict(type='raster',width=128,height=128,rgba_hex=pixels.hex()))]
        before = copy.deepcopy(doc)
        with closing(Client(('--tools','core'),workspace=self.root)) as c:
            c.initialize()
            result, expected = self.check_preview(c, 'document.export', document=doc,format='png')
            normal = c.tool('run',command='document.export',arguments=dict(document=doc,format='png'))
            self.assertEqual(restore(normal)['result'], expected)
            self.assertEqual(json.dumps(normal).count(expected['data']),1)
            self.assertEqual(len(result['content']),2)
            width,height,actual,_=png_pixels(base64.b64decode(result['content'][1]['data']))
            self.assertEqual((width,height),(128,128))
            # Rendering clears RGB only when alpha is zero, keeping source pixels intact.
            self.assertEqual(actual,b''.join(pixels[i:i+4] if pixels[i+3] else bytes(4) for i in range(0,len(pixels),4)))
        self.assertEqual(doc,before)

    def test_many_artboards_deduplicate_images_and_keep_overflow_recoverable(self):
        doc = self.document(); doc['items']=[]
        for i,color in enumerate([10,30,50,70,90,110,90,10]):
            doc['items'].append(dict(id=f'board-{i}',content=dict(type='frame',frame=dict(role='artboard',width=2,height=2,background=[color,20,40,255]))))
        with closing(Client(('--tools','core'),workspace=self.root)) as c:
            c.initialize()
            result, expected = self.check_preview(c,'artboard.export',document=doc,format='png')
            self.assertEqual(len(result['content']),5)
            projected=result['structuredContent']['result']['artifacts']
            self.assertEqual(projected[6]['artifact']['payload_ref']['kind'],'structured_content')
            self.assertEqual(projected[7]['artifact']['payload_ref']['index'],1)
            self.assertIn('2 additional unique image payloads',result['content'][0]['text'])
            self.assertEqual(len(expected['artifacts']),8)

    def test_sequence_frames_and_print_artifacts_reconstruct_without_duplicate_bytes(self):
        doc=self.cli('document.create',id='sequence',kind='raster',width=2,height=2)
        doc['items']=[dict(id=f'frame-{i}',content=dict(type='raster',width=2,height=2,rgba_hex=bytes([i*30,20,40,255]).hex()*4)) for i in range(6)]
        sequence=self.cli('document.edit',document=doc,expected_revision=0,operations=[dict(op='sequence_from_layers',ids=[i['id'] for i in doc['items']],delay=dict(numerator=1,denominator=24))])['document']
        plates=self.cli('document.create',id='plates',kind='raster',width=2,height=2)
        plates['channels']={'gray':channel([0,64,128,255],2,2)};plates['ink_recipe']=recipe(6)
        with closing(Client(('--tools','core'),workspace=self.root)) as c:
            c.initialize()
            self.check_preview(c,'sequence.export',document=sequence)
            separated,_=self.check_preview(c,'document.separations',document=plates)
            self.assertLess(len(separated['content']),5) # equal scalar plates share one payload
            self.check_preview(c,'channel.export',document=plates,id='gray')
            options=dict(print=dict(profile=embedded(proof_profile()),matte=[255,255,255]),delta_e76_threshold=20)
            self.check_preview(c,'document.proof',document=doc,options=options)

    def test_non_image_results_errors_and_metadata_stay_literal(self):
        doc=self.document();doc['metadata']=dict(note='{"media_type":"image/png","encoding":"base64","data":"AAAA"}')
        with closing(Client(('--tools','core'),workspace=self.root)) as c:
            c.initialize()
            result=c.tool('document.create',id='new',kind='vector',width=2,height=2,response_format='preview')
            self.assertEqual(len(result['content']),1);self.assertEqual(result['structuredContent']['result']['id'],'new')
            self.check_preview(c,'document.validate',document=doc)
            self.check_preview(c,'document.export',document=doc,format='snapshot')
            for mode in ('json','markdown','structured','preview'):
                failed=c.tool('document.create',id='bad',kind='vector',width=0,height=2,response_format=mode)
                self.assertTrue(failed['isError']);self.assertEqual(failed['structuredContent']['error']['code'],'INVALID_DOCUMENT')
                self.assertEqual(len(failed['content']),1)
            # Presentation stays outside dispatcher engine arguments.
            invalid=c.tool('run',command='session.create',arguments=dict(response_format='preview'))
            self.assertEqual(invalid['structuredContent']['error']['code'],'INVALID_REQUEST')
        self.assertFalse((self.root/'.inkbolt').exists())

    def test_structured_avoids_snapshot_text_duplication_and_reports_its_contract(self):
        doc=self.document();doc['metadata']=dict(note='original snapshot metadata '*200)
        with closing(Client(('--tools','core'),workspace=self.root)) as client:
            client.initialize()
            normal=client.tool('run',command='document.validate',arguments=dict(document=doc))
            structured=client.tool('run',command='document.validate',arguments=dict(document=doc),response_format='structured')
            self.assertEqual(json.loads(normal['content'][0]['text']),normal['structuredContent'])
            self.assertEqual(normal['structuredContent'],structured['structuredContent'])
            self.assertLess(len(json.dumps(structured)),len(json.dumps(normal))*.55)
            contract=client.tool('run',command='capabilities',arguments={})['structuredContent']['result']['mcp_responses']
            self.assertEqual(contract['default'],'json');self.assertIn('structured',contract['formats'])


if __name__ == '__main__': unittest.main()
