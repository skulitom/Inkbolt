"""Original native texture with a local blemish, clone edit and healed history."""
import struct
import measure_workloads as measure

SUITE = 'native-retouch-v1'
CASE = 'native-retouch-history'
WIDTH, HEIGHT = 1920, 1080


def pixel(x, y):
    return (5000+x*8+(y%32)*128, 7000+y*16+(x%32)*64,
            9000+((x+y)%64)*128, 65535)


def pixels(blemished):
    return b''.join(struct.pack('<4H', *( (50000, 51000, 52000, 65535)
        if blemished and 125 <= x < 133 and 125 <= y < 133 else pixel(x,y)))
        for y in range(HEIGHT) for x in range(WIDTH))


def operations():
    def op(x,y,w,h,mode):
        return dict(op='retouch',id='pixels',options=dict(source_id='pixels',
            source_transform=[1,0,0,1,-64,0],region=dict(x=x,y=y,width=w,height=h),
            mode=dict(type=mode,**(dict(tolerance=1e-12) if mode=='heal' else {}))))
    return [op(450,250,4,4,'clone'),op(125,125,8,8,'heal')]


def run(case):
    try:
        raw=pixels(True)
        source=case.source('blemished.png',measure.native_png(WIDTH,HEIGHT,raw))
        imported=case.call('import','sample.import',source_path=source,id='native',storage={})
        document=imported['document'] if imported else None
        saved=case.call('save','session.create',available=document is not None,session_id='retouch',request_id='create',document=document,response_mode='compact')
        initial=saved['document_ref'] if saved else None
        options=dict(image_options=dict(depth='u16',channels='rgba',compression='none'))
        case.publish('initial',initial,'tiff',lambda p:measure.check_tiff(p,WIDTH,HEIGHT,raw),**options)
        # The donor texture differs by a constant red offset of 512. The exact
        # boundary-constrained correction is that constant over the entire heal
        # domain, so the blemish is restored to the original arithmetic texture.
        expected=bytearray(pixels(False))
        for y in range(250,254):
            for x in range(450,454):
                struct.pack_into('<4H',expected,(y*WIDTH+x)*8,*pixel(x-64,y))
        changed=case.call('edit','session.apply',available=initial is not None,session_id='retouch',request_id='repair',expected_revision=0,response_mode='compact',action=dict(type='edit',operations=operations()))
        current=changed['document_ref'] if changed else None
        case.publish('edited',current,'tiff',lambda p:measure.check_tiff(p,WIDTH,HEIGHT,expected),**options)
        case.publish('historical',initial,'tiff',lambda p:measure.check_tiff(p,WIDTH,HEIGHT,raw),**options)
        verified=case.call('verify','session.verify',available=initial is not None,session_id='retouch')
        if verified: case.check('history-valid',lambda:measure.require(verified['valid'],'Invalid history'))
        if initial and current:
            case.check('revision-order',lambda:measure.require((initial['revision'],current['revision'])==(0,1),'Wrong revisions'))
    except Exception as error:
        case.checks.append(dict(name='harness',status='fail',error=f'{type(error).__name__}: {error}'))
    return case.finish()
