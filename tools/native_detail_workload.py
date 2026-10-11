"""Original native two-megapixel sharpening, exact local edit and saved history."""
import array
import sys
import workload_cases as measure

SUITE='native-detail-v1'
CASE='native-sharpen-history'
WIDTH,HEIGHT=1920,1080


def reference(raw,width,height):
    """Amount four gives exact integer 5*center-left-right-up-down channels."""
    values=array.array('H');values.frombytes(raw)
    if sys.byteorder!='little':values.byteswap()
    assert all(values[i]==65535 for i in range(3,len(values),4))
    result=array.array('H')
    for y in range(height):
        for x in range(width):
            center=(y*width+x)*4
            adjacent=((y*width+max(0,x-1))*4,(y*width+min(width-1,x+1))*4,
                      (max(0,y-1)*width+x)*4,(min(height-1,y+1)*width+x)*4)
            result.extend(max(0,min(65535,5*values[center+c]-sum(values[i+c] for i in adjacent))) for c in range(3))
            result.append(65535)
    if sys.byteorder!='little':result.byteswap()
    return result.tobytes()


def run(case):
    try:
        raw=measure.native_pixels(WIDTH,HEIGHT)
        source=case.source('source.png',measure.native_png(WIDTH,HEIGHT,raw))
        imported=case.call('import','sample.import',source_path=source,id='native',storage={})
        document=imported['document'] if imported else None
        if document:
            document['items'][0]['filters']=[dict(id='detail',operator=dict(type='detail',
                operator=dict(type='sharpen',amount=4)),border='clamp')]
        saved=case.call('save','session.create',available=document is not None,session_id='detail',
                       request_id='create',document=document,response_mode='compact')
        initial=saved['document_ref'] if saved else None
        expected=reference(raw,WIDTH,HEIGHT)
        options=dict(image_options=dict(depth='u16',channels='rgba',compression='none'))
        case.publish('initial',initial,'tiff',lambda p:measure.check_tiff(p,WIDTH,HEIGHT,expected),**options)
        patch=bytes.fromhex('010002000300ffff')*4
        edited=bytearray(raw)
        for y in range(2):
            start=((127+y)*WIDTH+127)*8
            edited[start:start+16]=patch[y*16:(y+1)*16]
        changed=case.call('edit','session.apply',available=initial is not None,session_id='detail',
            request_id='patch',expected_revision=0,response_mode='compact',action=dict(type='edit',
            operations=[dict(op='sample_replace',id='pixels',region=dict(x=127,y=127,width=2,height=2),data_hex=patch.hex())]))
        current=changed['document_ref'] if changed else None
        after=reference(edited,WIDTH,HEIGHT)
        case.publish('edited',current,'tiff',lambda p:measure.check_tiff(p,WIDTH,HEIGHT,after),**options)
        case.publish('historical',initial,'tiff',lambda p:measure.check_tiff(p,WIDTH,HEIGHT,expected),**options)
        verified=case.call('verify','session.verify',available=initial is not None,session_id='detail')
        if verified:case.check('history-valid',lambda:measure.require(verified['valid'],'Invalid history'))
        if initial and current:
            case.check('revision-order',lambda:measure.require((initial['revision'],current['revision'])==(0,1),'Wrong revisions'))
    except Exception as error:
        case.checks.append(dict(name='harness',status='fail',error=f'{type(error).__name__}: {error}'))
    return case.finish()
