"""Original native image with 5,000 independently editable clipped annotations."""
import struct
import workload_cases as measure

CASE = 'mixed-native-5000'
SUITE = 'native-layout-v1'
WIDTH, HEIGHT, ITEMS = 2560, 1440, 5000


def annotation(index, dx=0):
    x, y = 20+(index % 100)*24+dx, 20+(index//100)*24
    color = [20+index % 150, 90, 160, 255]
    content = (dict(type='raster', width=1, height=1, rgba_hex=bytes(color).hex()) if index % 2 else
               dict(type='vector', geometry=dict(shape='rect', x=0, y=0, width=1, height=1), fill=color))
    item = dict(id=f'annotation-{index}', parent='layout', transform=[8, 0, 0, 8, x, y],
                clip=dict(geometry=dict(shape='rect', x=0, y=0, width=.5, height=1)), content=content)
    return item, (x+11, y+7, 4, 8), struct.pack('<4H', *(v*257 for v in color))


def paint(expected, region, pixel):
    x, y, w, h = region
    for row in range(y, y+h):
        start = (row*WIDTH+x)*8
        expected[start:start+w*8] = pixel*w


def scene(case, profile='large_raster'):
    original = measure.native_pixels(WIDTH, HEIGHT)
    source = case.source('source.png', measure.native_png(WIDTH, HEIGHT, original))
    imported = case.call('import', 'sample.import', source_path=source, id='layout-image', storage={})
    document = imported['document'] if imported else None
    expected = bytearray(original)
    if document:
        if profile is not None: document['resource_profile'] = profile
        for i in range(ITEMS):
            item, region, pixel = annotation(i)
            document['items'].append(item)
            paint(expected, region, pixel)
        document['items'].append(dict(id='layout', transform=[1, 0, 0, 1, 11, 7],
                                     content=dict(type='group', isolated=True)))
        measure.save_json(case.root/'original-document.json', document)
    return document, original, expected


def run(case, profile='large_raster'):
    try:
        document, original, expected = scene(case, profile)
        saved = case.call('save', 'session.create', available=document is not None,
            session_id='layout', request_id='create', document=document, response_mode='compact')
        initial = saved['document_ref'] if saved else None
        options = dict(image_options=dict(depth='u16', channels='rgba', compression='none'))
        case.publish('initial', initial, 'tiff', lambda p: measure.check_tiff(p, WIDTH, HEIGHT, expected), **options)
        current_pixels = bytearray(expected)
        moves = []
        # Move both a vector and a raster annotation. Restore each old footprint
        # from the untouched native source before painting its new placement.
        for index in (ITEMS-2, ITEMS-1):
            _, old, _ = annotation(index)
            for y in range(old[1], old[1]+old[3]):
                at = (y*WIDTH+old[0])*8
                current_pixels[at:at+old[2]*8] = original[at:at+old[2]*8]
            moved, region, pixel = annotation(index, dx=2)
            paint(current_pixels, region, pixel)
            moves.append(dict(op='transform', id=moved['id'], matrix=moved['transform']))
        replacement = bytes.fromhex('010002000300ffff')*4
        for y in range(2):
            at = ((17+y)*WIDTH+13)*8
            current_pixels[at:at+16] = replacement[y*16:(y+1)*16]
        changed = case.call('edit', 'session.apply', available=initial is not None, session_id='layout',
            expected_revision=0, request_id='revise', response_mode='compact',
            action=dict(type='edit', operations=[dict(op='sample_replace',
                id=document['items'][0]['id'] if document else 'source',
                region=dict(x=13, y=17, width=2, height=2), data_hex=replacement.hex())]+moves))
        current = changed['document_ref'] if changed else None
        case.publish('edited', current, 'tiff', lambda p: measure.check_tiff(p, WIDTH, HEIGHT, current_pixels), **options)
        case.publish('historical', initial, 'tiff', lambda p: measure.check_tiff(p, WIDTH, HEIGHT, expected), **options)
        verified = case.call('verify', 'session.verify', available=initial is not None, session_id='layout')
        if verified: case.check('history-valid', lambda: measure.require(verified['valid'], 'Session history invalid'))
        if initial and current:
            case.check('revision-order', lambda: measure.require(
                (initial['revision'], current['revision']) == (0, 1), 'Revision sequence changed'))
    except Exception as error:
        case.checks.append(dict(name='harness', status='fail', error=f'{type(error).__name__}: {error}'))
    return case.finish()
