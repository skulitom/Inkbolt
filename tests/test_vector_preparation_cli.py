"""Cancellation during retained geometry work and unchanged profile acceptance."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest

from test_cli import EXE
from test_mcp import Client


def document(kind='volume'):
    geometry = dict(shape='ellipse', cx=18, cy=18, rx=10, ry=8)
    if kind == 'volume':
        content = dict(type=kind, volume=dict(
            geometry=geometry, depth=0, tolerance=.000001,
            material=dict(type='unlit', color=[25,70,190])))
    else:
        content = dict(type=kind, warp=dict(
            geometry=geometry, tolerance=.000001, fill=[25,70,190,255],
            maps=[dict(type='affine', matrix=[1,0,0,1,0,0])]))
    return dict(schema_version=2, id='bounded-preparation', kind='vector',
                width=36, height=36, color_space='srgb',
                items=[dict(id='art', content=content)])


def path(contours):
    commands = []
    for points in contours:
        commands.append(dict(verb='move', to=points[0]))
        commands.extend(dict(verb='line', to=p) for p in points[1:])
        commands.append(dict(verb='close'))
    return dict(shape='path', commands=commands)


class VectorPreparationTests(unittest.TestCase):
    def invoke(self, request, code=None):
        # A deliberately generous cooperative-cancellation bound, including
        # process startup. The old uncancellable preparation takes many seconds.
        process = subprocess.run([str(EXE)], input=json.dumps(request).encode(),
                                 capture_output=True, timeout=5)
        self.assertEqual(process.stderr, b'')
        result = json.loads(process.stdout)
        self.assertEqual(process.returncode, 1 if code else 0, result)
        self.assertEqual(result['ok'], code is None, result)
        if code:
            self.assertEqual(result['error']['code'], code, result)
            return result['error']
        return result['result']

    def test_deadline_reaches_volume_and_warp_preparation_for_all_delivery_formats(self):
        for kind in ('volume', 'warp'):
            for format in ('snapshot', 'svg', 'pdf', 'png'):
                with self.subTest(kind=kind, format=format):
                    self.invoke(dict(command='document.export', document=document(kind),
                                     format=format, control=dict(timeout_ms=1)), 'TIMEOUT')

    def test_overbudget_curved_profile_is_rejected_without_full_expansion(self):
        source = document()
        before = copy.deepcopy(source)
        self.invoke(dict(command='document.validate', document=source), 'RESOURCE_LIMIT')
        self.assertEqual(source, before)

    def test_deadline_survives_component_and_appearance_validation(self):
        component = document('warp')
        component['items'][0]['parent'] = 'definition'
        component['items'].insert(0, dict(id='definition', content=dict(type='component_source')))
        component['items'].append(dict(id='placed', content=dict(type='instance',
                                                                instance=dict(source='definition'))))
        appearance = document('warp')
        spec = appearance['items'][0]['content']['warp']
        appearance['items'][0]['content'] = dict(type='appearance', appearance=dict(
            geometry=spec['geometry'], passes=[dict(id='paint', fill=spec['fill'],
                                                   maps=spec['maps'], tolerance=spec['tolerance'])]))
        for source in (component, appearance):
            self.invoke(dict(command='document.export', document=source, format='snapshot',
                             control=dict(timeout_ms=1)), 'TIMEOUT')

    def test_cancellation_marker_during_work_leaves_no_publication(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            marker = root / 'cancel'
            destination = root / 'cancelled.svg'
            request = dict(command='document.publish', document=document('warp'),
                           output=dict(output_root=str(root), file_name=destination.name, format='svg'),
                           control=dict(cancel_file=str(marker)))
            timer = threading.Timer(.1, lambda: marker.write_text('cancel', encoding='utf-8'))
            timer.start()
            try:
                self.invoke(request, 'CANCELLED')
            finally:
                timer.join()
            self.assertFalse(destination.exists())
            self.assertEqual(sorted(p.name for p in root.iterdir()), ['cancel'])

    def test_mcp_cancellation_interrupts_active_validation_and_releases_the_worker(self):
        client = Client()
        self.addCleanup(client.close)
        client.initialize()
        request_id = client.send('tools/call', dict(name='inkbolt_document_validate',
                                                  arguments=dict(document=document('warp'))))
        time.sleep(.05)
        started = time.monotonic()
        client.send('notifications/cancelled', dict(requestId=request_id), notification=True)
        self.assertIn('commands', client.success('capabilities'))
        self.assertLess(time.monotonic() - started, 5)
        self.assertNotIn(request_id, client.saved)

    def test_failed_preparation_edit_preserves_mcp_history_and_allows_retry(self):
        source = document()
        source['items'][0]['content']['volume']['tolerance'] = .1
        client = Client()
        self.addCleanup(client.close)
        client.initialize()
        with tempfile.TemporaryDirectory() as root:
            session = dict(session_root=root, session_id='preparation')
            original = client.success('session.create', **session, request_id='create', document=source)
            change = dict(type='edit', operations=[dict(op='volume', id='art',
                          volume=document()['items'][0]['content']['volume'])])
            failed = client.tool('session.apply', **session, request_id='change',
                                 expected_revision=0, action=change, control=dict(timeout_ms=1))
            self.assertEqual(failed['structuredContent']['error']['code'], 'TIMEOUT')
            current = client.success('session.read', **session)
            self.assertEqual(current['document'], original['document'])
            self.assertTrue(client.success('session.verify', **session)['valid'])
            accepted = client.success('session.apply', **session, request_id='change',
                expected_revision=0, action=dict(type='edit', operations=[
                    dict(op='properties', id='art', name='retained after cancellation')]))
            self.assertEqual(accepted['document']['revision'], 1)
            restored = client.success('session.apply', **session, request_id='undo',
                                     expected_revision=1, action=dict(type='undo'))
            self.assertEqual(restored['document']['items'], original['document']['items'])

    def test_redundant_points_above_edge_limit_preserve_the_same_faces(self):
        corners = [[4,4], [28,4], [28,28], [4,28]]
        dense = []
        for a, b in zip(corners, corners[1:] + corners[:1]):
            for i in range(48):
                dense.append([a[k] + (b[k]-a[k])*i/48 for k in range(2)])
        self.assertGreater(len(dense), 128)
        for points in (dense, dense[25:] + dense[:25], list(reversed(dense))):
            source = document()
            spec = source['items'][0]['content']['volume']
            spec['geometry'] = path([points])
            result = self.invoke(dict(command='volume.inspect', document=source, id='art'))
            self.assertEqual(result['profile_edges'], 4)
            self.assertEqual(result['source']['geometry'], spec['geometry'])
            self.assertEqual(result['local_bounds'], [4,4,28,28])
            self.assertEqual(len(result['faces']), 1)
            self.assertEqual(set(map(tuple, result['faces'][0]['vertices'][0])),
                             {(x,y,0) for x,y in corners})

    def test_profile_edge_limit_counts_disjoint_contours_after_simplification(self):
        contours = []
        for i in range(33):
            x, y = 1 + (i % 8)*4, 1 + (i // 8)*4
            contours.append([[x,y], [x+2,y], [x+2,y+2], [x,y+2]])
        source = document()
        source['items'][0]['content']['volume']['geometry'] = path(contours[:32])
        result = self.invoke(dict(command='volume.inspect', document=source, id='art'))
        self.assertEqual(result['profile_edges'], 128)
        bad = copy.deepcopy(source)
        bad['items'][0]['content']['volume']['geometry'] = path(contours)
        self.invoke(dict(command='document.validate', document=bad), 'RESOURCE_LIMIT')
        self.assertEqual(source['items'][0]['content']['volume']['geometry'], path(contours[:32]))

    def test_collinear_cubic_parameter_subdivision_does_not_spend_profile_edges(self):
        corners = [[4,4], [28,4], [28,28], [4,28]]
        commands = [dict(verb='move', to=corners[0])]
        for a, b in zip(corners, corners[1:] + corners[:1]):
            commands.append(dict(verb='cubic', control1=a, control2=a, to=b))
        commands.append(dict(verb='close'))
        source = document()
        spec = source['items'][0]['content']['volume']
        spec.update(geometry=dict(shape='path', commands=commands), tolerance=.01)
        result = self.invoke(dict(command='volume.inspect', document=source, id='art'))
        self.assertEqual(result['profile_edges'], 4)
        self.assertEqual(result['source']['geometry'], spec['geometry'])
        self.assertEqual(set(map(tuple, result['faces'][0]['vertices'][0])),
                         {(x,y,0) for x,y in corners})


if __name__ == '__main__':
    unittest.main()
