"""Create a diagram, discover selected anchors, reshape it, compare and undo.

Run: python examples/path_workflow.py C:/absolute/new-output-directory
"""
import json
from pathlib import Path
import sys
from mask_workflow import invoke


def main(destination):
    output = Path(destination)
    if not output.is_absolute():
        raise ValueError('Use an absolute new output directory')
    output.mkdir(parents=True, exist_ok=False)
    document = invoke('document.create', id='editable-path-diagram', kind='vector', width=320, height=144)
    def vector(id, geometry, fill, **properties):
        return dict(id=id, content=dict(type='vector', geometry=geometry, fill=fill), **properties)
    items = [
        vector('canvas', dict(shape='rect', x=0, y=0, width=320, height=144), [244,247,251,255], locked=True),
        vector('left-card', dict(shape='rounded_rect', x=24, y=24, width=96, height=96, radii=[16,16,16,16]), [220,234,246,255]),
        vector('right-card', dict(shape='rounded_rect', x=200, y=24, width=96, height=96, radii=[16,16,16,16]), [253,235,207,255]),
        vector('input-node', dict(shape='regular_polygon', cx=72, cy=72, radius=25, sides=6, rotation=30), [28,112,161,255]),
        vector('output-node', dict(shape='star', cx=248, cy=72, outer_radius=24, inner_radius=12, points=4), [204,103,28,255]),
        vector('route', dict(shape='path', commands=[dict(verb='move', to=[124,72]), dict(verb='cubic', control1=[142,72], control2=[178,72], to=[196,72])]), None),
    ]
    items[-1]['content']['stroke'] = dict(color=[54,72,95,255], width=3, cap='round')
    document = invoke('document.edit', document=document, expected_revision=0, operations=[dict(op='add',item=i) for i in items])['document']
    args = dict(session_root=str(output/'sessions'), session_id='path-diagram')
    invoke('session.create', **args, request_id='create', document=document)
    def publish(revision, name, format='png'):
        return invoke('session.publish', **args, expected_revision=revision, output=dict(output_root=str(output), file_name=name, format=format))
    receipts = [publish(0,'original.json','snapshot'), publish(0,'before.png')]
    source = invoke('session.read', **args)['document']
    stars = invoke('document.query', document=source, query=dict(shapes=['star']))
    routes = invoke('document.query', document=source, query=dict(shapes=['path'], region=dict(bounds=[120,60,200,80], relation='contains')))
    assert len(stars['ids']) == len(routes['ids']) == 1
    star, route = stars['ids'][0], routes['ids'][0]
    prepared = invoke('session.apply', **args, expected_revision=0, request_id='prepare', action=dict(type='edit', label='Expose nodes and split connector', operations=[
        dict(op='path', id=star, action=dict(type='convert')),
        dict(op='path', id=route, action=dict(type='split', command_index=1, t=0.5)),
    ]))['document']
    receipts.append(publish(1,'prepared.json','snapshot'))
    tip = invoke('document.query', document=prepared, query=dict(shapes=['path'], anchor_bounds=[270,70,274,74]))
    bend = invoke('document.query', document=prepared, query=dict(shapes=['path'], anchor_bounds=[159,71,161,73]))
    assert tip['ids'] == [star] and bend['ids'] == [route]
    def move(discovered, to):
        item = discovered['items'][0]
        assert len(item['anchors']) == 1
        return dict(op='path', id=item['id'], action=dict(type='anchors', space='world', points=[dict(command_index=item['anchors'][0]['command_index'], to=to)]))
    invoke('session.apply', **args, expected_revision=tip['revision'], request_id='reshape', action=dict(type='edit', label='Stretch output and bend connector', operations=[move(tip,[284,72]), move(bend,[160,52])]))
    receipts.extend([publish(2,'edited.json','snapshot'), publish(2,'edited.png'), publish(2,'edited.svg','svg')])
    comparison = invoke('session.diff', **args, from_revision=0, to_revision=2, compare_pixels=True)
    invoke('session.apply', **args, expected_revision=2, request_id='undo-reshape', action=dict(type='undo'))
    invoke('session.apply', **args, expected_revision=3, request_id='undo-conversion', action=dict(type='undo'))
    receipts.extend([publish(4,'restored.json','snapshot'), publish(4,'restored.png')])
    invoke('session.verify', **args)
    print(json.dumps(dict(receipts=receipts, discovered_tip=tip, discovered_bend=bend, diff=comparison), indent=2))


if __name__ == '__main__':
    main(sys.argv[1])
