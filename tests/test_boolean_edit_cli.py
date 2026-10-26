"""Atomic combinations checked with independent area, pixels and durable history."""
import base64
import copy
from contextlib import closing
from fractions import Fraction
from pathlib import Path
import tempfile
import unittest

from external_workspace import files
from test_editing_cli import png_pixels
from test_mcp import Client
from test_sessions_cli import invoke


def item(name, x, y, width, height, **extra):
    return dict(id=name, content=dict(type='vector', geometry=dict(shape='rect',
        x=x, y=y, width=width, height=height), fill=[30,90,180,255]), **extra)


class BooleanEditTests(unittest.TestCase):
    def call(self, command, **args):
        result = invoke(dict(command=command, **args))
        self.assertTrue(result['ok'], result)
        return result['result']

    def document(self, items=None):
        doc = self.call('document.create', id='atomic-combination', kind='vector', width=32, height=24)
        return self.call('document.edit', document=doc, expected_revision=0,
            operations=[dict(op='add', item=i) for i in (items or [
                item('outer',2,3,12,8), item('opening',9,7,10,7), item('other',25,1,3,3)])])['document']

    def operation(self, **changes):
        return dict(dict(op='boolean', ids=['outer','opening'], new_id='frame',
            mode='difference', fill=[35,100,180,255], sources='hide', curve_tolerance=0), **changes)

    def apply(self, doc, operation):
        return self.call('document.edit', document=doc, expected_revision=doc['revision'], operations=[operation])

    def pixels(self, doc):
        png = self.call('document.export', document=doc, format='png')
        return png_pixels(base64.b64decode(png['data']))[2]

    def test_all_modes_have_exact_area_pixels_and_source_policy(self):
        for mode, area in [('union',146),('intersection',20),('difference',76),('xor',126)]:
            for policy in ['hide','remove']:
                with self.subTest(mode=mode, policy=policy):
                    doc=self.document(); before=copy.deepcopy(doc)
                    result=self.apply(doc,self.operation(mode=mode,sources=policy)); after=result['document']
                    receipt=result['changes'][0]['details']
                    self.assertEqual(Fraction(receipt['area_exact']),area)
                    self.assertEqual(receipt['result_id'],'frame');self.assertTrue(receipt['created'])
                    self.assertNotIn('geometry',receipt)
                    self.assertEqual(doc,before);self.assertEqual(after['revision'],doc['revision']+1)
                    by_id={i['id']:i for i in after['items']}
                    self.assertEqual(by_id['other'],doc['items'][2])
                    self.assertEqual(by_id['frame']['transform'],[1,0,0,1,0,0])
                    self.assertNotIn('parent',by_id['frame'])
                    if policy=='hide':
                        for old in doc['items'][:2]:
                            wanted=copy.deepcopy(old);wanted['visible']=False
                            self.assertEqual(by_id[old['id']],wanted)
                    else:self.assertEqual(set(by_id),{'other','frame'})
                    pixels=self.pixels(after)
                    for y in range(24):
                        for x in range(32):
                            a=2<=x<14 and 3<=y<11;b=9<=x<19 and 7<=y<14
                            selected={'union':a or b,'intersection':a and b,'difference':a and not b,'xor':a!=b}[mode]
                            color=[35,100,180,255] if selected else [30,90,180,255] if 25<=x<28 and 1<=y<4 else [0,0,0,0]
                            self.assertEqual(list(pixels[(y*32+x)*4:(y*32+x+1)*4]),color,(mode,x,y))

    def test_default_keeps_locked_sources_and_world_transforms(self):
        group=dict(id='group',transform=[1,0,0,1,3,2],content=dict(type='group'))
        doc=self.document([group,item('outer',0,0,8,8,parent='group',locked=True),item('opening',7,4,8,8)])
        operation=self.operation(mode='intersection');del operation['sources']
        result=self.apply(doc,operation)
        by_id={i['id']:i for i in result['document']['items']}
        self.assertEqual([i for i in result['document']['items'] if i['id']!='frame'],doc['items'])
        self.assertEqual(Fraction(result['changes'][0]['details']['area_exact']),24)
        points=[c['to'] for c in by_id['frame']['content']['geometry']['commands'] if 'to' in c]
        self.assertEqual({tuple(p) for p in points},{(7,4),(11,4),(11,10),(7,10)})
        for policy in ['hide','remove']:
            bad=invoke(dict(command='document.edit',document=doc,expected_revision=doc['revision'],operations=[self.operation(sources=policy)]))
            self.assertFalse(bad['ok']);self.assertEqual(bad['error']['code'],'LOCKED')
            # Bound admission must precede per-operand lock/dependency traversal.
            excessive=self.operation(ids=['outer']*17,sources=policy)
            bad=invoke(dict(command='document.edit',document=doc,expected_revision=doc['revision'],operations=[excessive]))
            self.assertFalse(bad['ok']);self.assertEqual(bad['error']['code'],'INVALID_REQUEST')

    def test_empty_results_do_not_create_dummy_items(self):
        for policy in ['keep','hide','remove']:
            doc=self.document([item('outer',2,2,5,5),item('opening',2,2,5,5)])
            result=self.apply(doc,self.operation(sources=policy));detail=result['changes'][0]['details']
            self.assertTrue(detail['empty']);self.assertFalse(detail['created']);self.assertIsNone(detail['result_id'])
            self.assertEqual(detail['area_exact'],'0')
            self.assertNotIn('frame',[i['id'] for i in result['document']['items']])
            if policy=='keep':self.assertEqual(result['document']['items'],doc['items'])
            elif policy=='hide':self.assertTrue(all(not i['visible'] for i in result['document']['items']))
            else:self.assertEqual(result['document']['items'],[])

    def test_failures_leave_session_and_whole_batch_unchanged(self):
        doc=self.document()
        with tempfile.TemporaryDirectory() as directory:
            args=dict(session_root=directory,session_id='boolean')
            self.call('session.create',**args,request_id='create',document=doc)
            original=self.call('session.read',**args)
            for number,operation in enumerate([
                self.operation(new_id='other'),self.operation(ids=['outer','outer']),
                self.operation(ids=['outer','missing']),self.operation(curve_tolerance=-1),
                self.operation(fill={'type':'missing-paint'}),
            ]):
                bad=invoke(dict(command='session.apply',**args,request_id=f'bad-{number}',expected_revision=0,
                    action=dict(type='edit',operations=[dict(op='properties',id='other',visible=False),operation])))
                self.assertFalse(bad['ok']);self.assertEqual(self.call('session.read',**args),original)
            bad=invoke(dict(command='session.apply',**args,request_id='late-failure',expected_revision=0,
                action=dict(type='edit',operations=[self.operation(sources='remove'),dict(op='remove',id='missing')])))
            self.assertFalse(bad['ok']);self.assertEqual(self.call('session.read',**args),original)
            stale=invoke(dict(command='session.apply',**args,request_id='stale',expected_revision=1,
                action=dict(type='edit',operations=[self.operation()])))
            self.assertEqual(stale['error']['code'],'REVISION_CONFLICT')

    def test_curved_result_retains_certificates_and_analytic_area(self):
        curved=item('outer',0,0,1,1)
        curved['content']['geometry']=dict(shape='path',commands=[dict(verb='move',to=[0,0]),
            dict(verb='cubic',control1=[4,8],control2=[8,8],to=[12,0]),dict(verb='close')])
        doc=self.document([curved,item('opening',0,0,12,10)])
        previous=None
        for tolerance in [.5,.125]:
            result=self.apply(doc,self.operation(mode='intersection',curve_tolerance=tolerance))
            details=result['changes'][0]['details'];count=details['curves']['topology']['curve_arcs']
            # x=12t, y=24t(1-t): uniform chords enclose 48 - 48/n^2.
            actual=Fraction(details['area_exact'])
            self.assertEqual(actual,48-Fraction(48,count*count))
            error=48-actual
            if previous is not None:self.assertLess(error,previous)
            previous=error
            self.assertEqual(details['curves']['topology']['certificate'],'exact_simultaneous_curve_to_chord_homotopy')
            self.assertLessEqual(Fraction(details['inputs'][0]['flattening_deviation_squared']),Fraction(tolerance)**2)
            frame=next(i for i in result['document']['items'] if i['id']=='frame')
            for command in frame['content']['geometry']['commands']:
                if 'to' in command:
                    x,y=map(Fraction,command['to']);self.assertTrue(y==0 or y==2*x-x*x/6)

    def test_work_paths_are_materialized_and_solver_refusals_stay_explicit(self):
        region=dict(id='outer',content=dict(type='work_path',geometry=dict(shape='rect',x=2,y=3,width=12,height=8)))
        doc=self.document([region,item('opening',9,7,10,7)])
        result=self.apply(doc,self.operation(mode='intersection'))
        self.assertEqual(Fraction(result['changes'][0]['details']['area_exact']),20)
        curve=dict(shape='path',commands=[dict(verb='move',to=[0,0]),
            dict(verb='cubic',control1=[4,8],control2=[8,8],to=[12,0]),dict(verb='close')])
        cases=[([dict(shape='ellipse',cx=10,cy=10,rx=4,ry=3)],'UNSUPPORTED'),
               ([curve],'UNSUPPORTED'),
               ([dict(shape='regular_polygon',cx=10,cy=10,radius=8,sides=256)]*3,'RESOURCE_LIMIT')]
        for geometries,code in cases:
            source=[item(f's{n}',0,0,1,1) for n in range(len(geometries))]
            for i,g in zip(source,geometries):i['content']['geometry']=g
            source.append(item('opening',0,0,20,20));doc=self.document(source)
            with tempfile.TemporaryDirectory() as directory:
                args=dict(session_root=directory,session_id='refused')
                self.call('session.create',**args,request_id='create',document=doc)
                before=self.call('session.read',**args)
                bad=invoke(dict(command='session.apply',**args,request_id='combine',expected_revision=0,
                    action=dict(type='edit',operations=[self.operation(ids=[i['id'] for i in source],sources='remove')])))
                self.assertFalse(bad['ok']);self.assertEqual(bad['error']['code'],code)
                self.assertEqual(self.call('session.read',**args),before)

    def test_ancestor_and_component_locks_and_dangling_references(self):
        for kind in ['group','component_source']:
            container=dict(id='container',content=dict(type=kind))
            source=[container,item('outer',2,3,12,8,parent='container'),item('opening',9,7,10,7)]
            if kind=='component_source':
                source.append(dict(id='copy',locked=True,content=dict(type='instance',instance=dict(source='container'))))
            doc=self.document(source)
            if kind=='group':
                doc=self.call('document.edit',document=doc,expected_revision=doc['revision'],
                    operations=[dict(op='properties',id='container',locked=True)])['document']
            for policy in ['hide','remove']:
                bad=invoke(dict(command='document.edit',document=doc,expected_revision=doc['revision'],operations=[self.operation(sources=policy)]))
                self.assertFalse(bad['ok']);self.assertEqual(bad['error']['code'],'LOCKED')
            self.apply(doc,self.operation(sources='keep'))
        # A saved instance override cannot silently lose its referenced source child.
        doc=self.document([dict(id='component',content=dict(type='component_source')),
            item('outer',2,3,12,8,parent='component'),item('opening',9,7,10,7),
            dict(id='copy',content=dict(type='instance',instance=dict(source='component',overrides={'outer':dict(visible=False)})))])
        with tempfile.TemporaryDirectory() as directory:
            args=dict(session_root=directory,session_id='references')
            self.call('session.create',**args,request_id='create',document=doc)
            before=self.call('session.read',**args)
            bad=invoke(dict(command='session.apply',**args,request_id='remove',expected_revision=0,
                action=dict(type='edit',operations=[self.operation(sources='remove')])))
            self.assertFalse(bad['ok']);self.assertEqual(self.call('session.read',**args),before)

    def test_schema_example_cli_mcp_review_retry_and_undo(self):
        query=dict(name='operation',select='boolean')
        example=self.call('schema.lookup',**query)['example']['value']
        self.assertEqual(example['op'],'boolean')
        for transport in ['cli','mcp']:
            with self.subTest(transport=transport), tempfile.TemporaryDirectory() as directory, closing(Client()) as client:
                client.initialize();call=self.call if transport=='cli' else client.success
                self.assertEqual(client.success('schema.lookup',**query),self.call('schema.lookup',**query))
                args=dict(session_root=directory,session_id='combination')
                doc=self.document();call('session.create',**args,request_id='create',document=doc)
                before=call('session.read',**args)['document'];action=dict(type='edit',operations=[example])
                inventory={str(p):p.read_bytes() for p in files(Path(directory))}
                review=call('session.dry_run',**args,request_id='combine',expected_revision=0,action=action,
                    options=dict(preview=True,include_document=True))
                self.assertEqual({str(p):p.read_bytes() for p in files(Path(directory))},inventory)
                commit=call('session.apply_proposal',session_root=directory,proposal=review['proposal'],action=action)
                self.assertEqual(commit['document'],review['proposed_document'])
                self.assertEqual(png_pixels(base64.b64decode(review['preview']['data']))[2],self.pixels(commit['document']))
                retry=call('session.apply_proposal',session_root=directory,proposal=review['proposal'],action=action)
                self.assertTrue(retry['replayed']);self.assertEqual(retry['receipt'],commit['receipt'])
                restored=call('session.apply',**args,request_id='undo',expected_revision=1,action=dict(type='undo'))
                self.assertEqual(restored['document']['items'],before['items'])
                redone=call('session.apply',**args,request_id='redo',expected_revision=2,action=dict(type='redo'))
                self.assertEqual(redone['document']['items'],commit['document']['items'])
                call('session.verify',**args)


if __name__=='__main__':unittest.main()
