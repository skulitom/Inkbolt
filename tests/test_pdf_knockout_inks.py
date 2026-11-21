"""Independent press separations for native-ink vector knockout delivery."""
from contextlib import closing
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from cmyk_fixtures import cmyk_profile
from pdf_reader import Pdf
import test_agent_workspace as workspace
from test_ink_recipes_cli import calculator
from test_mcp import Client
from test_profiles_cli import builtin, embedded
from test_proof_cli import scalar
from test_vector_plates_cli import color, named, rect, spot


def group(key, isolated=True, knockout=True, **properties):
    return dict(id=key, content=dict(type='group', isolated=isolated, knockout=knockout), **properties)


def sheet(isolated=True):
    swatches = dict(c=color([1,0,0,0]), y=color([0,0,1,0]), m=color([0,1,0,0]),
                    a=spot('Proof'), z=spot('Proof'))
    items = [rect('yellow', named('y'), (0,0,16,36)),
             rect('partial',named('y',opacity=.4),(16,0,16,36)), group('cut',isolated,opacity=.75),
             rect('cyan',named('c',opacity=.8),(0,0,48,36),parent='cut',fill_opacity=.7)]
    for j,p in enumerate((0,.36,1)):
        for i,f in enumerate((0,74/255,184/255,1)):
            key = ('m','a','z')[(i+j)%3]
            items.append(rect(f'patch-{i}-{j}',named(key,tint=.8,opacity=f),(i*12,j*12,12,12),
                              parent='cut',opacity=p))
    return dict(schema_version=2,id='proof',kind='vector',width=48,height=36,
                resolution_ppi=72,color_space='srgb',swatches=swatches,items=items)


def process_sheet():
    doc = sheet()
    doc['swatches']['under'] = color([.25,.375,.5,.625])
    doc['items'] = [rect('paper',named('y'),(0,0,48,36)), group('cut',False),
                    rect('prior',named('a'),(0,0,48,36),parent='cut'),
                    group('local',True,False,parent='cut',opacity=.8),
                    rect('ink',named('under'),(0,0,48,36),parent='local'),
                    rect('spot',named('z',overprint='preserve',tint=.6),(0,0,48,36),parent='local')]
    for mask in range(16):
        name = f'mix{mask}'
        doc['swatches'][name] = color([.875 if mask & (1 << i) else 0 for i in range(4)])
        for row,policy in enumerate(('preserve','preserve_nonzero')):
            doc['items'].append(rect(f'{name}-{row}',named(name,overprint=policy,opacity=.75),
                                     (3*mask,18*row,3,18),parent='local',opacity=.6))
    return doc


def separations(data, directory):
    from PIL import Image
    gs = shutil.which('gs') or shutil.which('gswin64c')
    (directory/'proof.pdf').write_bytes(data)
    subprocess.run([gs,'-dSAFER','-dBATCH','-dNOPAUSE','-sDEVICE=tiffsep','-r288',
                    '-sOutputFile=plate.tif','proof.pdf'],cwd=directory,check=True,
                   capture_output=True,timeout=30)
    planes = {}
    for path in directory.glob('plate(*).tif'):
        with Image.open(path) as image:
            planes[path.stem[6:-1]] = image.convert('L')
    return planes


class NativePdfKnockoutTests(unittest.TestCase):
    setUp = workspace.AgentWorkspaceTests.setUp
    cli = workspace.AgentWorkspaceTests.cli

    def export(self, doc, **extra):
        return self.cli('document.export',document=doc,format='pdf',pdf_options=dict(color='native_inks',**extra))

    def proof(self, doc):
        return self.cli('document.prepress',document=doc,options=dict(profile=embedded(cmyk_profile()),antialias='none'))

    def check_plates(self, doc, tolerance=3, **options):
        if not (shutil.which('gs') or shutil.which('gswin64c')):
            self.skipTest('Independent plate rendering requires Ghostscript')
        try:
            from PIL import Image
        except ImportError:
            self.skipTest('Independent TIFF plate reading requires Pillow')
        artifact = self.export(doc, **options)
        pdf = Pdf(artifact)
        self.assertEqual(pdf.pages[0]['Group']['CS'],'DeviceCMYK')
        with tempfile.TemporaryDirectory() as temp:
            plates = separations(pdf.data, Path(temp))
        proof = self.proof(doc)
        expected = {}
        for p in proof['plates']:
            channel = p['id'].title() if p['kind']=='process' else 'Inkbolt.'+p['id']
            w,h,samples,_ = scalar(p)
            expected[channel] = samples
        self.assertEqual(plates.keys(),expected.keys())
        margin = round(pdf.pages[0]['BleedBox'][0]*4)
        for channel,plane in plates.items():
            self.assertEqual(plane.size,(4*w+2*margin,4*h+2*margin))
            maximum = max(abs(255-plane.getpixel((margin+4*x+2,margin+4*y+2))-expected[channel][y*w+x])
                          for y in range(h) for x in range(w))
            self.assertLessEqual(maximum,tolerance,(channel, maximum))
        return artifact,plates

    def test_both_group_modes_preserve_named_separations_and_paths(self):
        for isolated in (True,False):
            doc = sheet(isolated)
            out = self.export(doc)
            pdf = Pdf(out)
            self.assertEqual(out['pdf']['knockout_groups'],1)
            self.assertEqual(out['pdf']['image_pixels'],0)
            self.assertEqual(pdf.pages[0]['Group']['CS'],'DeviceCMYK')
            self.assertIn(b'/Separation /Inkbolt.a',pdf.data)
            self.assertIn(b'/Separation /Inkbolt.z',pdf.data)
            self.assertNotIn(b'/Subtype /Image',pdf.data)

    def test_independent_process_and_spot_planes_with_fractional_cutouts(self):
        for isolated in (True,False):
            with self.subTest(isolated=isolated):
                self.check_plates(sheet(isolated))

    def test_nested_grid_artwork_masks_and_zero_opacity_shape_affect_every_plate(self):
        doc = sheet(False)
        doc['items'] = doc['items'][:4]
        doc['items'][:0] = [dict(id='source',content=dict(type='mask_source')),
                            rect('field',[255,255,255,164],(7,0,18,36),parent='source')]
        doc['items'].extend([
            group('panel',False,False,parent='cut',opacity=.6,clip=dict(geometry=dict(
                shape='rect',x=3,y=2,width=36,height=30))),
            rect('spot',named('a',tint=.7,opacity=.8),(0,0,34,36),parent='panel',opacity=.4),
            group('nested',parent='panel',opacity=.8,mask=dict(width=4,height=1,
                  gray_hex='0080c8ff',transform=[12,0,0,36,0,0])),
            rect('base',named('m'),(2,0,38,34),parent='nested',opacity=.55),
            rect('lacquer',named('z',tint=.45),(0,3,28,30),parent='nested',fill_opacity=.45,
                 artwork_mask=dict(source='source',mode='alpha',region=[0,0,48,36])),
            rect('hole',named('c',opacity=.73),(13,7,16,19),parent='nested',opacity=0)])
        out,_ = self.check_plates(doc,tolerance=5)
        self.assertGreater(out['pdf']['knockout_field_masks'],0)
        self.assertEqual(out['pdf']['knockout_groups'],2)
        self.assertEqual(out['pdf']['image_pixels'],0)

    def test_isolation_retains_local_overprint_and_clears_unaddressed_page_inks(self):
        for policy in ('preserve','preserve_nonzero'):
            for inner in (False,True):
                with self.subTest(policy=policy,inner=inner):
                    doc = sheet()
                    doc['swatches']['mix'] = color([.625,0,.25,0])
                    doc['items'] = [rect('background',named('y'),(0,0,48,36)),
                                    rect('varnish',named('z',overprint='preserve',tint=.8),(0,0,48,36)),
                                    group('k',not inner),
                                    rect('under',named('c',tint=.65),(0,0,45,36),parent='k',opacity=.7)]
                    parent = 'k'
                    if inner:
                        doc['items'].append(group('isolated',True,False,parent='k',opacity=.7))
                        parent = 'isolated'
                    doc['items'].extend([rect('wash',named('a',overprint=policy,tint=.75,opacity=.6),
                                              (0,0,32,36),parent=parent),
                                         rect('ink',named('mix',overprint=policy,opacity=.9),
                                              (8,0,32,36),parent=parent,opacity=.5)])
                    self.check_plates(doc,tolerance=4)

    def test_process_overprint_addresses_each_subset_of_the_four_plates(self):
        self.check_plates(process_sheet(), tolerance=3)

    def test_process_color_spaces_reuse_plate_sets_and_map_alternate_tints(self):
        pdf = Pdf(self.export(process_sheet()))
        spaces = [obj for obj in pdf.objects.values()
                  if isinstance(obj, list) and obj[0] == 'DeviceN']
        channels = ['Cyan', 'Magenta', 'Yellow', 'Black']
        all_sets = {tuple(c for i, c in enumerate(channels) if mask & (1 << i)) or ('None',)
                    for mask in range(16)}
        self.assertEqual({tuple(space[1]) for space in spaces}, all_sets)
        self.assertEqual(len(spaces), len(all_sets))
        for _, names, alternate, function in spaces:
            self.assertEqual(alternate, 'DeviceCMYK')
            tints = [(i + 1) / 8 for i in range(len(names))]
            expected = dict(zip(names, tints))
            self.assertEqual(calculator(pdf.streams[function], tints, outputs=4),
                             [expected.get(c, 0) for c in channels])


    def test_overprint_scope_profiles_and_publication_are_explicit(self):
        for policy in ('preserve','preserve_nonzero'):
            doc = sheet(False)
            doc['items'].append(group('pass',False,False,parent='cut'))
            doc['items'].append(rect('ink',named('z',overprint=policy),(0,0,48,36),parent='pass'))
            output = dict(format='pdf',file_name=f'{policy}.pdf',pdf_options=dict(color='native_inks'))
            self.assertTrue(self.cli('document.preflight',document=doc,output=output)['ready'])
            self.assertFalse((self.root/output['file_name']).exists())
            self.cli('document.publish',document=doc,output=output)
            self.assertEqual((self.root/output['file_name']).read_bytes(),Pdf(self.export(doc)).data)
        doc = dict(sheet(),output_profile=builtin('srgb'))
        output = dict(format='pdf',file_name='refused.pdf',pdf_options=dict(color='native_inks'))
        error = self.cli('document.publish',document=doc,output=output,error='UNSUPPORTED')
        self.assertEqual(error['item_id'],'cut')
        self.assertFalse((self.root/'refused.pdf').exists())

    def test_saved_revision_publishes_the_preflighted_plate_document(self):
        doc = sheet(False)
        doc['items'].append(rect('overprint',named('z',overprint='preserve',opacity=.51),
                                 (2,3,40,25),parent='cut'))
        with closing(Client(('--tools','essentials'),workspace=self.root)) as client:
            client.initialize()
            def run(command, **args):
                return client.tool('run',command=command,arguments=args)['structuredContent']
            self.assertTrue(run('session.create',session_id='press',request_id='s',document=doc)['ok'])
            edit = dict(session_id='press',expected_revision=0,request_id='tint',
                        action=dict(type='edit',operations=[dict(op='properties',id='cut',opacity=.2)]))
            self.assertTrue(run('session.apply',**edit)['ok'])
            self.assertTrue(run('session.apply',**edit)['ok'])
            ref = dict(session_id='press',revision=0)
            output = dict(format='pdf',file_name='proof.pdf',pdf_options=dict(color='native_inks'))
            self.assertTrue(run('document.preflight',document=ref,output=output)['result']['ready'])
            self.assertFalse((self.root/'proof.pdf').exists())
            self.assertTrue(run('document.publish',document=ref,output=output)['ok'])
            issued = (self.root/'proof.pdf').read_bytes()
            self.assertEqual(issued,Pdf(self.export(doc)).data)
            self.assertNotEqual(issued,Pdf(self.export(dict(ref,revision=1))).data)
            self.assertEqual(run('document.publish',document=ref,output=output)['error']['code'],'OUTPUT_EXISTS')
            self.assertEqual(issued,(self.root/'proof.pdf').read_bytes())

    def test_marks_do_not_change_artwork_or_spot_coverage(self):
        doc = sheet(False)
        _,plain = self.check_plates(doc)
        from PIL import ImageChops
        marked,plates = self.check_plates(doc,marks={})
        margin = round(Pdf(marked).pages[0]['BleedBox'][0]*4)
        box = (margin,margin,margin+4*doc['width'],margin+4*doc['height'])
        for channel,image in plates.items():
            self.assertIsNone(ImageChops.difference(plain[channel],image.crop(box)).getbbox())
            image.paste(255,box)
        margin_plate = plates['Black']
        self.assertGreater(margin_plate.histogram()[0],0)
        for plate in plates.values():
            self.assertIsNone(ImageChops.difference(plate,margin_plate).getbbox())
