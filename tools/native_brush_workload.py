"""Original native texture with four local brush modes and immutable history."""
from fractions import Fraction as F
import struct
import workload_cases as measure

SUITE = 'native-brush-v1'
CASE = 'native-brush-history'
WIDTH, HEIGHT = 1920, 1080
DOMAIN = [(x,y) for y in range(125,133) for x in range(125,133)]


def pixel(x,y):
    return (5000+x*8+(y%32)*128,7000+y*16+(x%32)*64,
            9000+((x+y)%64)*128,65535)


def pixels():
    return b''.join(struct.pack('<4H',*pixel(x,y))
                    for y in range(HEIGHT) for x in range(WIDTH))


def operations():
    texture=bytes(255 if x in {0,1,2,3,4,61,62,63} and y in {0,1,2,3,4,61,62,63}
                  else 0 for y in range(64) for x in range(64)).hex()
    modes=[dict(type='paint',color=[45,100,155,255]),dict(type='erase'),
           dict(type='smudge',border='clamp'),
           dict(type='mixer',color=[100,100,100,128],pickup=.25,load=.25)]
    return [dict(op='brush_stroke',id='pixels',stroke=dict(
        points=[dict(point=p) for p in ([[128,128],[130,129]] if mode['type']=='smudge' else [[128,128]])],
        diameter=24,hardness=1,spacing=4,flow=.2 if mode["type"]=="smudge" else .25,opacity=1 if mode["type"]=="smudge" else .25,mode=mode,
        texture=dict(width=64,height=64,gray_hex=texture))) for mode in modes]


def reference(raw):
    """Exact rational deposition/transport/reservoir model on full-covered cells.

    The repeating texture is zero at every partial-coverage circle edge. Its
    8x8 nonzero patch lies wholly inside all dabs, across four source blocks.
    No numeric brush integration or engine receipt is used by this oracle.
    """
    current={p:pixel(*p) for p in DOMAIN}
    def pm(c,maximum=65535):
        a=F(c[3],maximum)
        return [F(v,maximum)*a for v in c[:3]]+[a]
    for operation in operations():
        mode=operation['stroke']['mode'];kind=mode['type']
        before={p:pm(c) for p,c in current.items()}
        color=pm(mode['color'],255) if 'color' in mode else None
        if kind=='mixer':
            average=[sum((v[k] for v in before.values()),F(0))/len(DOMAIN) for k in range(4)]
            color=[(3*a+b)/4 for a,b in zip(color,average)]
        for p in DOMAIN:
            a=before[p]
            if kind in ('paint','mixer'):
                after=[b/4+v*(1-color[3]/4) for v,b in zip(a,color)]
            elif kind=='erase':after=[v*F(3,4) for v in a]
            else:
                donor=(p[0]-2,p[1]-1)
                source=before[donor] if donor in before else pm(pixel(*donor))
                after=[(4*v+b)/5 for v,b in zip(a,source)]
            value=after if kind=="smudge" else [(3*v+b)/4 for v,b in zip(a,after)]
            codes=[v/value[3]*65535 for v in value[:3]]+[value[3]*65535]
            # Every expected channel is away from an exact half-code tie.
            assert all(v%1!=F(1,2) for v in codes), (kind,p,codes)
            current[p]=tuple(int(v+F(1,2)) for v in codes)
    result=bytearray(raw)
    for (x,y),c in current.items():struct.pack_into('<4H',result,(y*WIDTH+x)*8,*c)
    return result


def run(case):
    try:
        raw=pixels();expected=reference(raw)
        source=case.source('texture.png',measure.native_png(WIDTH,HEIGHT,raw))
        imported=case.call('import','sample.import',source_path=source,id='native',storage={})
        document=imported['document'] if imported else None
        saved=case.call('save','session.create',available=document is not None,session_id='brush',request_id='create',document=document,response_mode='compact')
        initial=saved['document_ref'] if saved else None
        options=dict(image_options=dict(depth='u16',channels='rgba',compression='none'))
        case.publish('initial',initial,'tiff',lambda p:measure.check_tiff(p,WIDTH,HEIGHT,raw),**options)
        changed=case.call('edit','session.apply',available=initial is not None,session_id='brush',request_id='stroke',expected_revision=0,response_mode='compact',action=dict(type='edit',operations=operations()))
        current=changed['document_ref'] if changed else None
        case.publish('edited',current,'tiff',lambda p:measure.check_tiff(p,WIDTH,HEIGHT,expected),**options)
        case.publish('historical',initial,'tiff',lambda p:measure.check_tiff(p,WIDTH,HEIGHT,raw),**options)
        verified=case.call('verify','session.verify',available=initial is not None,session_id='brush')
        if verified:case.check('history-valid',lambda:measure.require(verified['valid'],'Invalid history'))
        if initial and current:
            case.check('revision-order',lambda:measure.require((initial['revision'],current['revision'])==(0,1),'Wrong revisions'))
    except Exception as error:
        case.checks.append(dict(name='harness',status='fail',error=f'{type(error).__name__}: {error}'))
    return case.finish()
