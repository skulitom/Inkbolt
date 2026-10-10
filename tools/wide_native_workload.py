"""Original wide native composition, retained edits and exact arithmetic channels."""
import struct
import workload_cases as measure

CASE = 'wide-mixed-native'
SUITE = 'wide-native-v1'


def scene(case, width=2560, height=1440):
    original = measure.native_pixels(width, height)
    source = case.source('source.png', measure.native_png(width, height, original))
    imported = case.call('import', 'sample.import', source_path=source, id='wide', storage={})
    document = imported['document'] if imported else None
    expected = bytearray(original)
    if document:
        for i in range(128):
            x, y = 60+(i % 16)*120, 80+(i//16)*140
            color = [20+i, 90, 160, 255]
            document['items'].append(dict(id=f'annotation-{i}', parent='layout',
                transform=[8, 0, 0, 8, x, y],
                clip=dict(geometry=dict(shape='rect', x=0, y=0, width=.5, height=1)),
                content=dict(type='raster', width=1, height=1, rgba_hex=bytes(color).hex())))
            sample = struct.pack('<4H', *(v*257 for v in color))
            for py in range(y+7, min(y+15, height)):
                left, right = min(x+11, width), min(x+15, width)
                start = (py*width+left)*8
                expected[start:start+(right-left)*8] = sample*(right-left)
        document['items'].append(dict(id='layout', transform=[1, 0, 0, 1, 11, 7],
                                     content=dict(type='group', isolated=True)))
        measure.save_json(case.root/'original-document.json', document)
    return document, expected


def run(case):
    try:
        document, expected = scene(case)
        saved = case.call('save', 'session.create', available=document is not None,
            session_id='wide', request_id='create', document=document, response_mode='compact')
        initial = saved['document_ref'] if saved else None
        options = dict(image_options=dict(depth='u16', channels='rgba', compression='none'))
        case.publish('initial', initial, 'tiff', lambda p: measure.check_tiff(p, 2560, 1440, expected), **options)
        replacement = bytes.fromhex('010002000300ffff')*4
        current_pixels = bytearray(expected)
        for y in range(2):
            offset = ((17+y)*2560+13)*8
            current_pixels[offset:offset+16] = replacement[y*16:(y+1)*16]
        changed = case.call('edit', 'session.apply', available=initial is not None, session_id='wide',
            expected_revision=0, request_id='replace', response_mode='compact',
            action=dict(type='edit', operations=[dict(op='sample_replace',
                id=document['items'][0]['id'] if document else 'source',
                region=dict(x=13, y=17, width=2, height=2), data_hex=replacement.hex())]))
        current = changed['document_ref'] if changed else None
        case.publish('edited', current, 'tiff', lambda p: measure.check_tiff(p, 2560, 1440, current_pixels), **options)
        case.publish('historical', initial, 'tiff', lambda p: measure.check_tiff(p, 2560, 1440, expected), **options)
        verified = case.call('verify', 'session.verify', available=initial is not None, session_id='wide')
        if verified:
            case.check('history-valid', lambda: measure.require(verified['valid'], 'Session history invalid'))
        if initial and current:
            case.check('revision-order', lambda: measure.require(
                (initial['revision'], current['revision']) == (0, 1), 'Revision sequence changed'))
    except Exception as error:
        case.checks.append(dict(name='harness', status='fail', error=f'{type(error).__name__}: {error}'))
    return case.finish()
