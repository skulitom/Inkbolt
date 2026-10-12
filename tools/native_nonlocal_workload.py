"""Original two-megapixel radial resampling, native patch and saved history."""
import array
import struct
import sys
import workload_cases as measure

SUITE='native-nonlocal-v1'
CASE='native-radial-history'
WIDTH,HEIGHT=1920,1080
Q=1024
PATCH=(1,2,3)


def pixel(x,y):return 37+12*x,59+18*y,1000+7*x+11*y,65535


def fixture(width,height):
    return b''.join(struct.pack('<4H',*pixel(x,y)) for y in range(height) for x in range(width))


def coordinates(length):
    # Three zoom factors 1-1/512, 1, 1+1/512, around the pixel-center midpoint.
    return [[max(0,min(Q*(length-1),Q*x+t*(2*x-length+1))) for t in (-1,0,1)] for x in range(length)]


def reference(width,height,patched=False):
    """Exact integer bilinear sampling; source ramps separate into the two axes.

    Only samples whose four taps touch the explicit patch need a correction.
    Accumulate those corrections before the single final native quantization.
    """
    xs,ys=coordinates(width),coordinates(height);denominator=3*Q*Q
    sums_x=[sum(v) for v in xs];sums_y=[sum(v) for v in ys]
    def totals(x,y):
        return [(37*3*Q+12*sums_x[x])*Q,(59*3*Q+18*sums_y[y])*Q,
                (1000*3*Q+7*sums_x[x]+11*sums_y[y])*Q]
    def quantize(v):return (v+denominator//2)//denominator
    result=array.array('H')
    for y in range(height):
        for x in range(width):
            result.extend(map(quantize,totals(x,y)));result.append(65535)
    if patched:
        def taps(n,length):
            at,rem=divmod(n,Q)
            return [(min(length-1,at),Q-rem),(min(length-1,at+1),rem)]
        xt=[[[(at,weight) for at,weight in taps(n,width) if at in (127,128) and weight] for n in row] for row in xs]
        yt=[[[(at,weight) for at,weight in taps(n,height) if at in (127,128) and weight] for n in row] for row in ys]
        for y in [i for i,row in enumerate(yt) if any(row)]:
            for x in [i for i,row in enumerate(xt) if any(row)]:
                values=totals(x,y)
                for j in range(3):
                    for xx,wx in xt[x][j]:
                        for yy,wy in yt[y][j]:
                            before=pixel(xx,yy)
                            for c in range(3):values[c]+=(PATCH[c]-before[c])*wx*wy
                result[(y*width+x)*4:(y*width+x)*4+3]=array.array('H',map(quantize,values))
    if sys.byteorder!='little':result.byteswap()
    return result.tobytes()


def run(case):
    try:
        raw=fixture(WIDTH,HEIGHT)
        source=case.source('source.png',measure.native_png(WIDTH,HEIGHT,raw))
        imported=case.call('import','sample.import',source_path=source,id='native',storage={})
        document=imported['document'] if imported else None
        if document:
            document['items'][0]['filters']=[dict(id='radial',operator=dict(type='radial',
                center=[WIDTH/2,HEIGHT/2],angle=0,zoom=1/256,samples=3),border='clamp')]
        saved=case.call('save','session.create',available=document is not None,session_id='radial',
            request_id='create',document=document,response_mode='compact')
        initial=saved['document_ref'] if saved else None
        expected=reference(WIDTH,HEIGHT)
        options=dict(image_options=dict(depth='u16',channels='rgba',compression='none'))
        case.publish('initial',initial,'tiff',lambda p:measure.check_tiff(p,WIDTH,HEIGHT,expected),**options)
        patch=struct.pack('<4H',*PATCH,65535)*4
        changed=case.call('edit','session.apply',available=initial is not None,session_id='radial',
            request_id='patch',expected_revision=0,response_mode='compact',action=dict(type='edit',
            operations=[dict(op='sample_replace',id='pixels',region=dict(x=127,y=127,width=2,height=2),data_hex=patch.hex())]))
        current=changed['document_ref'] if changed else None
        after=reference(WIDTH,HEIGHT,True)
        case.publish('edited',current,'tiff',lambda p:measure.check_tiff(p,WIDTH,HEIGHT,after),**options)
        case.publish('historical',initial,'tiff',lambda p:measure.check_tiff(p,WIDTH,HEIGHT,expected),**options)
        verified=case.call('verify','session.verify',available=initial is not None,session_id='radial')
        if verified:case.check('history-valid',lambda:measure.require(verified['valid'],'Invalid history'))
        if initial and current:
            case.check('revision-order',lambda:measure.require((initial['revision'],current['revision'])==(0,1),'Wrong revisions'))
    except Exception as error:
        case.checks.append(dict(name='harness',status='fail',error=f'{type(error).__name__}: {error}'))
    return case.finish()
