"""Original two-megapixel native blur, patch revision and historical output."""
import array
import sys
import measure_workloads as measure

SUITE = 'native-filter-v1'
CASE = 'native-box-blur'
WIDTH, HEIGHT = 1920, 1080


def box_reference(raw, width, height):
    """Integer 3x3 clamp convolution; never quantize between the two axes."""
    values = array.array('H')
    values.frombytes(raw)
    if sys.byteorder != 'little': values.byteswap()
    assert all(values[i] == 65535 for i in range(3, len(values), 4))
    def row(y):
        start = y*width*4
        return [sum(values[start+min(width-1,max(0,x+dx))*4+c] for dx in (-1,0,1))
                for x in range(width) for c in range(3)]
    before = current = row(0)
    output = array.array('H')
    for y in range(height):
        after = row(y+1) if y+1 < height else current
        for x in range(width):
            output.extend((before[x*3+c]+current[x*3+c]+after[x*3+c]+4)//9 for c in range(3))
            output.append(65535)
        before, current = current, after
    if sys.byteorder != 'little': output.byteswap()
    return output.tobytes()


def run(case):
    try:
        raw = measure.native_pixels(WIDTH, HEIGHT)
        source = case.source('source.png', measure.native_png(WIDTH, HEIGHT, raw))
        imported = case.call('import', 'sample.import', source_path=source, id='native', storage={})
        document = imported['document'] if imported else None
        if document:
            document['items'][0]['filters'] = [dict(id='blur',operator=dict(type='box',radius=1),border='clamp')]
        saved = case.call('save','session.create',available=document is not None,session_id='blur',request_id='create',document=document,response_mode='compact')
        initial = saved['document_ref'] if saved else None
        expected = box_reference(raw, WIDTH, HEIGHT)
        options = dict(image_options=dict(depth='u16',channels='rgba',compression='none'))
        case.publish('initial',initial,'tiff',lambda p: measure.check_tiff(p,WIDTH,HEIGHT,expected),**options)
        edited = bytearray(raw)
        patch = bytes.fromhex('010002000300ffff')*4
        for y in range(2):
            start = ((127+y)*WIDTH+127)*8
            edited[start:start+16] = patch[y*16:(y+1)*16]
        changed = case.call('edit','session.apply',available=initial is not None,session_id='blur',request_id='patch',expected_revision=0,response_mode='compact',
                           action=dict(type='edit',operations=[dict(op='sample_replace',id='pixels',region=dict(x=127,y=127,width=2,height=2),data_hex=patch.hex())]))
        current = changed['document_ref'] if changed else None
        after = box_reference(edited,WIDTH,HEIGHT)
        case.publish('edited',current,'tiff',lambda p: measure.check_tiff(p,WIDTH,HEIGHT,after),**options)
        case.publish('historical',initial,'tiff',lambda p: measure.check_tiff(p,WIDTH,HEIGHT,expected),**options)
        verified = case.call('verify','session.verify',available=initial is not None,session_id='blur')
        if verified: case.check('history-valid',lambda: measure.require(verified['valid'],'Invalid history'))
        if initial and current:
            case.check('revision-order',lambda: measure.require((initial['revision'],current['revision'])==(0,1),'Wrong revisions'))
    except Exception as error:
        case.checks.append(dict(name='harness',status='fail',error=f'{type(error).__name__}: {error}'))
    return case.finish()
