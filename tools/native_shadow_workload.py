"""Original translucent native image with an editable, integer-offset shadow."""
import array
import sys
import struct
import workload_cases as measure

SUITE = 'native-shadow-v1'
CASE = 'native-shadow-history'
WIDTH, HEIGHT = 1920, 1080
COLOR = (20, 40, 80)


def source_pixels(width, height):
    values = array.array('H')
    values.frombytes(measure.native_pixels(width, height))
    if sys.byteorder != 'little': values.byteswap()
    values[3::4] = array.array('H', [32768])*(width*height)
    if sys.byteorder != 'little': values.byteswap()
    return values.tobytes()


def reference(raw, width, height):
    """Exact integer source-over over alpha shifted two right and one down."""
    values = array.array('H');values.frombytes(raw)
    if sys.byteorder != 'little': values.byteswap()
    result = array.array('H');maximum=65535;halves=[]
    for y in range(height):
        for x in range(width):
            start=(y*width+x)*4;a=values[start+3]
            behind=values[((y-1)*width+x-2)*4+3] if y>=1 and x>=2 else 0
            shadow=behind*(maximum-a)
            alpha=a*maximum+shadow
            for c in range(3):
                numerator=values[start+c]*a*maximum+COLOR[c]*257*shadow
                if alpha and 2*(numerator % alpha)==alpha: halves.append(len(result))
                result.append((2*numerator+alpha)//(2*alpha) if alpha else 0)
            result.append((2*alpha+maximum)//(2*maximum))
    if sys.byteorder != 'little': result.byteswap()
    return result.tobytes(),halves


def check(path, expected, width=WIDTH, height=HEIGHT):
    # Match the existing numerical-effect policy: only an exact rational half
    # code may round to either adjacent integer after f64 composition. All
    # other channels, including unaffected source samples, remain exact.
    raw, halves=expected
    data=path.read_bytes();tags=measure.tiff_tags(data)
    actual=b''.join(data[offset:offset+size] for offset,size in zip(tags[273],tags[279]))
    endian='>' if data[:2]==b'MM' else '<'
    canonical=bytearray(raw)
    for index in halves:
        wanted=struct.unpack_from('<H',raw,index*2)[0]
        observed=struct.unpack_from(endian+'H',actual,index*2)[0]
        if observed==wanted-1: struct.pack_into('<H',canonical,index*2,observed)
    measure.check_tiff(path,width,height,canonical)


def run(case):
    try:
        raw=source_pixels(WIDTH,HEIGHT)
        source=case.source('source.png',measure.native_png(WIDTH,HEIGHT,raw))
        imported=case.call('import','sample.import',source_path=source,id='native',storage={})
        document=imported['document'] if imported else None
        if document:
            document['items'][0]['effects']=[dict(id='shadow',operator=dict(type='shadow',offset=[2,1],sigma=0),color=[*COLOR,255])]
        saved=case.call('save','session.create',available=document is not None,session_id='shadow',request_id='create',document=document,response_mode='compact')
        initial=saved['document_ref'] if saved else None
        expected=reference(raw,WIDTH,HEIGHT)
        options=dict(image_options=dict(depth='u16',channels='rgba',compression='none'))
        case.publish('initial',initial,'tiff',lambda p:check(p,expected),**options)
        patch=bytes.fromhex('010002000300c8af')*4
        edited=bytearray(raw)
        for y in range(2):
            start=((127+y)*WIDTH+127)*8
            edited[start:start+16]=patch[y*16:(y+1)*16]
        changed=case.call('edit','session.apply',available=initial is not None,session_id='shadow',request_id='patch',expected_revision=0,response_mode='compact',action=dict(type='edit',operations=[dict(op='sample_replace',id='pixels',region=dict(x=127,y=127,width=2,height=2),data_hex=patch.hex())]))
        current=changed['document_ref'] if changed else None
        after=reference(edited,WIDTH,HEIGHT)
        case.publish('edited',current,'tiff',lambda p:check(p,after),**options)
        case.publish('historical',initial,'tiff',lambda p:check(p,expected),**options)
        verified=case.call('verify','session.verify',available=initial is not None,session_id='shadow')
        if verified: case.check('history-valid',lambda:measure.require(verified['valid'],'Invalid history'))
        if initial and current:
            case.check('revision-order',lambda:measure.require((initial['revision'],current['revision'])==(0,1),'Wrong revisions'))
    except Exception as error:
        case.checks.append(dict(name='harness',status='fail',error=f'{type(error).__name__}: {error}'))
    return case.finish()
