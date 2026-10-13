"""Original synthetic photographic fixture and exact native-edit benchmark judge."""
import base64
import copy
from functools import lru_cache
import math
import struct
from pathlib import Path

from benchmark_diagram import delivered
from benchmark_graphics import store, source_snapshot, png_check
from benchmark_runtime import require, safe_name, strict_json
from workload_cases import document, native_png, check_tiff, save, save_json, sha

WIDTH, HEIGHT = 1920, 1080
REGION = dict(x=1150, y=766, width=12, height=14)
DONOR_DX = -96
# Fixed before measurements: engine process lifetime commit, including import,
# review and delivery. The fixture/oracle Python process is separately excluded.
MAX_PEAK_COMMIT_BYTES = 256*1024*1024
PROMPT = Path(__file__).with_name('benchmark_prompts')/'B10.md'
PREVIEW_FILES = {'photo-preview':'preview.png'}


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
    require(bool(observations) and all(isinstance(m,dict) and m.get('available') is True for m in observations),
            'The fixed photo memory budget requires complete process observations')
    require(all(type(m.get('peak_commit_bytes')) is int and 0<m['peak_commit_bytes']<=MAX_PEAK_COMMIT_BYTES for m in observations),
            'Photo editing exceeded the fixed 256 MiB engine commit budget')


def fixture(case):
    case.source('original.png',native_png(WIDTH,HEIGHT,photographic_source()))


def solve(case):
    imported=case.call('import','sample.import',source_path='original.png',id='photo',storage={},color_policy='assume_srgb')
    save_json(case.root/'import-report.json',imported)
    saved=store(case,imported['document']);source_snapshot(case,saved,'before')
    session=saved['session_id']
    action=dict(type='edit',operations=[dict(op='retouch',id='pixels',options=dict(source_id='pixels',
        source_transform=[1,0,0,1,DONOR_DX,0],region=REGION,mode=dict(type='clone')))])
    proposal=case.call('review','session.dry_run',session_id=session,request_id='repair',expected_revision=0,
                       action=action,options=dict(include_document=True))
    save_json(case.root/'review.json',proposal)
    edited=case.call('commit','session.apply_proposal',proposal=proposal['proposal'],action=action,response_mode='compact')['document_ref']
    source_snapshot(case,edited,'edited')
    preview=case.call('preview','document.preview',document=edited,preview=True,options=preview_options())
    save(case.root/'preview.png',base64.b64decode(preview['artifact']['data'],validate=True))
    publications={}
    for name,reference in [('edited',edited),('historical',saved)]:
        publications[name]=case.call(name+'-tiff','document.publish',document=reference,output=tiff_output(name+'.tiff'))
    save_json(case.root/'publication-report.json',publications)
    for name,revision,filename in [('undo',1,'undo-source'),('redo',2,'editable')]:
        result=case.call(name,'session.apply',session_id=session,request_id=name,expected_revision=revision,
                        action=dict(type=name),response_mode='compact')
        source_snapshot(case,result['document_ref'],filename)
    case.call('verify-history','session.verify',session_id=session)
    save_json(case.root/'session.json',dict(session_id=session,requests=dict(create='create',edit='repair',undo='undo',redo='redo')))


def preview_options():
    return dict(focus=dict(type='region',bounds=[REGION['x'],REGION['y'],
        REGION['x']+REGION['width'],REGION['y']+REGION['height']]),render_options=dict(evaluation='tiled'))


def tiff_output(name):
    return dict(file_name=name,format='tiff',render_options=dict(evaluation='tiled'),
                image_options=dict(depth='u16',channels='rgba',compression='none'))


@lru_cache(maxsize=1)
def original_manifest():
    """Independent v1 native-block identities from the original channel bytes."""
    raw=photographic_source(); hashes=[]
    for y in range(0,HEIGHT,128):
        for x in range(0,WIDTH,128):
            w,h=min(128,WIDTH-x),min(128,HEIGHT-y)
            payload=b''.join(raw[(row*WIDTH+x)*8:(row*WIDTH+x+w)*8] for row in range(y,y+h))
            hashes.append(sha(b'INKTILE1'+struct.pack('<IIBBBB',w,h,2,4,0,0)+payload))
    identity=b'INKGRID1INKTILE1'+struct.pack('<IIBBBBI',WIDTH,HEIGHT,2,4,0,0,128)+b''.join(bytes.fromhex(h) for h in hashes)
    return dict(version=1,spec=dict(width=WIDTH,height=HEIGHT,depth='u16',channels='rgba',encoding='encoded_srgb'),
                tiles=hashes,sha256=sha(identity))


def check_tiles(case):
    paths=list((case.root/'.inkbolt/assets').glob('*.native-tile'))
    expected={digest+'.native-tile':digest for digest in original_manifest()['tiles']}
    require(all(p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(case.root.resolve()) for p in paths)
            and {p.name:sha(p.read_bytes()) for p in paths}==expected,
            'Immutable native base files differ from the independently encoded original samples')


def check_review(review, receipts, edited):
    creation,commit=receipts['create'],receipts['edit']
    proposal=review['proposal']; receipt=commit['receipt']
    require(review['dry_run'] is True and review['committed'] is False and review['source_changed'] is False and
        review['proposed_document']==edited and review['predicted_receipt']==receipt and
        proposal['session_id']==commit['session_id'] and proposal['request_id']==receipt['request_id'] and
        proposal['expected_revision']==0 and proposal['base_state_sha256']==creation['receipt']['state_sha256'] and
        proposal['result_state_sha256']==receipt['state_sha256'],
        'Delivered review must bind the exact original state and committed native patch')


def judge_memory(case):
    if case.arm=='reference':
        case.close()  # Include the persistent MCP lifetime through independent judging.
        observations,scope=case.memory_observations()
        evidence=dict(kind='engine_process_observations',scope=scope,observations=observations)
        predicate=lambda:check_memory(observations)
    else:
        # The enclosing client/launcher peak is a conservative upper bound for
        # every owned engine/tool process, not an exact engine-only observation.
        from benchmark_driver import execution_memory
        captured=case.driver_evidence or {}
        memory=execution_memory(captured.get('execution',case.driver_execution))
        evidence=dict(kind='owned_tree_process_upper_bound',memory=memory)
        def predicate():
            require(memory['available'] and type(memory['peak_process_commit_bytes']) is int and
                    0<memory['peak_process_commit_bytes']<=MAX_PEAK_COMMIT_BYTES,
                    'The captured owned-tree process peak does not establish the fixed 256 MiB budget')
    save_json(getattr(case,'judge_root',case.root)/'memory-budget.json',
              dict(maximum_peak_commit_bytes=MAX_PEAK_COMMIT_BYTES,**evidence))
    case.check('memory-budget',predicate)


def judge(case):
    raw=photographic_source();expected,patch=patched(raw)
    names={'create':'before.json','edit':'edited.json','undo':'undo-source.json','redo':'editable.json'}
    snapshots={role:strict_json(delivered(case,name)) for role,name in names.items()}
    before,edited,current=(snapshots[k] for k in ('create','edit','redo'))
    imported=strict_json(delivered(case,'import-report.json'))
    wanted_before=case.call('judge-original-shape','document.validate',document=document(before['id'],'raster',WIDTH,HEIGHT,
        items=[dict(id='pixels',content=dict(type='stored_samples',grid=dict(base=original_manifest())))]))
    case.check('native-import',lambda:require(before==wanted_before and imported['document']==before and
        imported['source_sha256']==case.sources['original.png'] and imported['source_changed'] is False and
        imported['storage']['kind']=='native_tiles' and imported['storage']['manifest_sha256']==original_manifest()['sha256'],
        'Import must retain original identity, dimensions, native depth and all exact base samples'))
    case.check('immutable-tiles',lambda:check_tiles(case))
    locator=strict_json(delivered(case,'session.json'))
    require(isinstance(locator,dict) and set(locator)=={'session_id','requests'} and
            isinstance(locator['requests'],dict) and set(locator['requests'])==set(names),'Invalid photo session locator')
    safe_name(locator['session_id'])
    require(len(set(locator['requests'].values()))==4,'Photo request IDs must be distinct')
    receipts={}
    for role in names:
        safe_name(locator['requests'][role])
        receipts[role]=case.call('judge-'+role+'-receipt','session.receipt',session_id=locator['session_id'],request_id=locator['requests'][role])
    wanted=copy.deepcopy(wanted_before);wanted['revision']=1
    wanted['items'][0]['content']['grid']['patches']=[dict(region=REGION,data_hex=patch.hex())]
    review=strict_json(delivered(case,'review.json'))
    def exact_patch():
        require(edited==wanted and receipts['edit']['document']==edited,'Only the exact clone patch and revision may change')
        check_review(review,receipts,edited)
    case.check('editable-exact-patch',exact_patch)
    for role,revision,source in [('undo',2,wanted_before),('redo',3,wanted)]:
        wanted_state=copy.deepcopy(source);wanted_state['revision']=revision
        case.check(role+'-editability',lambda role=role,w=wanted_state:require(
            snapshots[role]==w and receipts[role]['document']==w and receipts[role]['receipt']['action']==role,
            'Undo/redo must restore the entire editable native state'))
    rendered=case.call('judge-preview','document.preview',document=current,preview=True,options=preview_options())
    def picture():
        pixels=preview_samples(expected)
        png_check(delivered(case,'preview.png'),REGION['width'],REGION['height'],pixels)
        png_check(base64.b64decode(rendered['artifact']['data'],validate=True),REGION['width'],REGION['height'],pixels)
    case.check('photo-preview',picture)
    publications=strict_json(delivered(case,'publication-report.json'))
    require(isinstance(publications,dict) and set(publications)=={'edited','historical'},'Missing native publication receipts')
    for name,doc,samples in [('edited',current,expected),('historical',before,raw)]:
        target='judge-'+name+'.tiff'
        options=tiff_output(target);options.pop('file_name')
        export=case.call('judge-'+name,'document.export',document=doc,**options)
        path=getattr(case,'judge_root',case.root)/target
        save(path,base64.b64decode(export['data'],validate=True))
        def native(name=name,path=path,samples=samples):
            require(publications[name]['sha256']==sha(delivered(case,name+'.tiff')),
                    'Native delivery hash differs from its publication receipt')
            check_tiff(case.root/(name+'.tiff'),WIDTH,HEIGHT,samples)
            check_tiff(path,WIDTH,HEIGHT,samples)
        case.check(name+'-native-samples',native)
    verified=case.call('judge-history','session.verify',session_id=locator['session_id'])
    case.check('history-valid',lambda:require(verified['valid'] and verified['revision']==3 and
        all(receipts[role]['document']==snapshots[role] and receipts[role]['receipt']['revision']==revision and
            receipts[role]['receipt']['request_id']==locator['requests'][role]
            for revision,role in enumerate(names)) and receipts['create']['document']==wanted_before,
        'History must bind the original, reviewed edit, undo, redo and final current head'))
    judge_memory(case)


def photograph(case):
    fixture(case);case.begin(PROMPT.read_text(encoding='utf-8'));solve(case)
    case.begin_judging();judge(case)
    if any(c['name']=='photo-preview' and c['status']=='pass' for c in case.checks):
        case.verified_preview(delivered(case,'preview.png'))
