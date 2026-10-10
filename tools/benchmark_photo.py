"""Original synthetic photographic fixture and exact native-edit benchmark judge."""
import array
import copy
from functools import lru_cache
import math
import struct
import sys

from benchmark_graphics import store, ref, source_snapshot, view, verify_history
from benchmark_runtime import require
from workload_cases import native_png, check_tiff, save_json, sha

WIDTH, HEIGHT = 1920, 1080
REGION = dict(x=1150, y=766, width=12, height=14)
DONOR_DX = -96
# Fixed before measurements: engine process lifetime commit, including import,
# review and delivery. The fixture/oracle Python process is separately excluded.
MAX_PEAK_COMMIT_BYTES = 256*1024*1024


@lru_cache(maxsize=1)
def photographic_source():
    """A deterministic studio study, not a camera capture or an 8-bit upconversion.

    Original analytic ellipsoids, soft contact shadows, surface texture and
    sensor-like grain produce linear light, encoded directly into 16-bit sRGB.
    No Inkbolt renderer, external picture, font or graphics package is involved.
    """
    objects=[(1500,675,165,190,(.32,.046,.018)),
             (600,550,245,320,(.018,.16,.21)),
             (1200,615,265,265,(.70,.13,.024))]
    result=bytearray(WIDTH*HEIGHT*8)
    for y in range(HEIGHT):
        for x in range(WIDTH):
            noise=((x*73856093)^(y*19349663))&0xffffffff
            noise=((noise^(noise>>13))*1274126177)&0xffffffff
            grain=(noise/4294967295-.5)*.0015
            field=.14+.10*(1-y/HEIGHT)+.018*x/WIDTH
            for cx,cy,rx,ry,_ in objects:
                distance=((x-cx-65)/(rx*1.12))**2+((y-cy-ry*.91)/(ry*.19))**2
                field*=1-.48*math.exp(-distance*1.7)
            rgb=[field*1.06,field*1.02,field*.98]
            for cx,cy,rx,ry,color in objects:
                nx,ny=(x-cx)/rx,(y-cy)/ry
                q=nx*nx+ny*ny
                if q>=1:continue
                nz=math.sqrt(1-q)
                diffuse=.18+.8*max(0,-.45*nx-.60*ny+.66*nz)
                highlight=.55*max(0,-.25*nx-.32*ny+.913*nz)**80
                rim=.025*(1-nz)**2
                coverage=min(1,(1-q)*min(rx,ry)/2)
                rgb=[back*(1-coverage)+(base*diffuse+highlight+rim)*coverage
                     for back,base in zip(rgb,color,strict=True)]
            encoded=[]
            for linear in rgb:
                linear=max(0,min(1,linear+grain))
                value=12.92*linear if linear<=.0031308 else 1.055*linear**(1/2.4)-.055
                encoded.append(int(value*65535+.5))
            if REGION['x']<=x<REGION['x']+REGION['width'] and REGION['y']<=y<REGION['y']+REGION['height']:
                encoded=[61003,4007,54011]
            struct.pack_into('<4H',result,(y*WIDTH+x)*8,*encoded,65535)
    return bytes(result)


def patched(raw):
    result=bytearray(raw);patch=bytearray()
    for y in range(REGION['y'],REGION['y']+REGION['height']):
        start=(y*WIDTH+REGION['x']+DONOR_DX)*8
        row=raw[start:start+REGION['width']*8]
        offset=(y*WIDTH+REGION['x'])*8
        result[offset:offset+len(row)]=row;patch.extend(row)
    return bytes(result),bytes(patch)


def preview_samples(raw):
    result=bytearray()
    for y in range(REGION['y'],REGION['y']+REGION['height']):
        start=(y*WIDTH+REGION['x'])*8
        for values in struct.iter_unpack('<4H',raw[start:start+REGION['width']*8]):
            result.extend((v*255+32767)//65535 for v in values)
    return bytes(result)


def check_memory(observations):
    require(bool(observations) and all(m and m.get('available') for m in observations),
            'The fixed photo memory budget requires complete process observations')
    require(all(0<m['peak_commit_bytes']<=MAX_PEAK_COMMIT_BYTES for m in observations),
            'Photo editing exceeded the fixed 256 MiB engine commit budget')


def photograph(case):
    raw=photographic_source();expected,patch=patched(raw)
    case.source('original.png',native_png(WIDTH,HEIGHT,raw))
    case.begin('Edit the original 1920x1080 16-bit synthetic studio photograph. Import native tiled samples, '
        'save its original revision, review a clone repair of the blemish rectangle (1150,766,12,14) '
        'from the same layer 96 pixels left, and commit the reviewed edit. Keep exact native samples '
        'everywhere else, the immutable source tiles and editable history. Review the repaired region, '
        'deliver a full-size uncompressed RGBA16 TIFF, and prove the original revision still exports '
        'exactly. Undo/redo must restore the complete editable states. Engine lifetime peak committed '
        'memory must stay at or below 256 MiB, including import and delivery.')
    imported=case.call('import','sample.import',source_path='original.png',id='photo',storage={},color_policy='assume_srgb')
    saved=store(case,imported['document']);before=source_snapshot(case,saved,'before')
    base=before['items'][0]['content']['grid']['base']
    tile_root=case.root/'.inkbolt/assets'
    tiles={p.name:sha(p.read_bytes()) for p in tile_root.glob('*.native-tile')}
    values=array.array('H');values.frombytes(raw)
    if sys.byteorder!='little':values.byteswap()
    case.check('native-import',lambda:require(imported['source_sha256']==case.sources['original.png']
        and imported['source_changed'] is False and imported['storage']['kind']=='native_tiles'
        and base['spec']==dict(width=WIDTH,height=HEIGHT,depth='u16',channels='rgba',encoding='encoded_srgb')
        and len(base['tiles'])==135 and any(v%257!=0 for v in values),
        'Import lost original identity, native depth, dimensions or precision'))
    action=dict(type='edit',operations=[dict(op='retouch',id='pixels',options=dict(source_id='pixels',
        source_transform=[1,0,0,1,DONOR_DX,0],region=REGION,mode=dict(type='clone')))])
    proposal=case.call('review','session.dry_run',session_id='work',request_id='repair',expected_revision=0,
                       action=action,options=dict(include_document=True))
    case.call('commit','session.apply_proposal',proposal=proposal['proposal'],action=action,response_mode='compact')
    current=source_snapshot(case,ref(1))
    wanted=copy.deepcopy(before);wanted['revision']=1
    wanted['items'][0]['content']['grid']['patches']=[dict(region=REGION,data_hex=patch.hex())]
    case.check('editable-exact-patch',lambda:require(current==wanted and proposal['proposed_document']==wanted,
        'Review/commit changed more than the exact native clone patch'))
    view(case,'preview',ref(1),'photo-preview',REGION['width'],REGION['height'],preview_samples(expected),
         focus=dict(type='region',bounds=[REGION['x'],REGION['y'],REGION['x']+REGION['width'],REGION['y']+REGION['height']]),
         render_options=dict(evaluation='tiled'))
    for name,reference,samples in [('edited',ref(1),expected),('historical',saved,raw)]:
        receipt=case.call(name,'document.publish',document=reference,output=dict(file_name=name+'.tiff',format='tiff',
            render_options=dict(evaluation='tiled'),image_options=dict(depth='u16',channels='rgba',compression='none')))
        path=case.root/(name+'.tiff')
        require(receipt['sha256']==sha(path.read_bytes()), 'Native delivery hash differs from its receipt')
        case.check(name+'-native-samples',lambda p=path,s=samples:check_tiff(p,WIDTH,HEIGHT,s))
    for name,revision in [('undo',1),('redo',2)]:
        case.call(name,'session.apply',session_id='work',request_id=name,expected_revision=revision,
                  action=dict(type=name),response_mode='compact')
        actual=source_snapshot(case,ref(revision+1),name+'-source')
        wanted_state=copy.deepcopy(before if name=='undo' else wanted);wanted_state['revision']=revision+1
        case.check(name+'-editability',lambda a=actual,w=wanted_state:require(a==w,'Undo/redo lost editable native state'))
    case.check('immutable-tiles',lambda:require(tiles=={p.name:sha(p.read_bytes()) for p in tile_root.glob('*.native-tile')},
        'Reviewed editing or history rewrote native base resources'))
    verify_history(case)
    case.close()  # Include the complete persistent MCP lifetime in the budget.
    observations,scope=case.memory_observations()
    save_json(case.root/'memory-budget.json',dict(maximum_peak_commit_bytes=MAX_PEAK_COMMIT_BYTES,
              scope=scope,observations=observations))
    case.check('memory-budget',lambda:check_memory(observations))
