"""B11 original mixed composition, prompt, reference solve and independent judge."""
import base64
import copy
from fractions import Fraction as F
from pathlib import Path

from benchmark_diagram import delivered
from benchmark_graphics import ORANGE, document, rectangle, store, source_snapshot, png_check
from benchmark_large_layout import retained_session_store
from benchmark_stores import retained_asset_store
from benchmark_runtime import require, safe_name, strict_json
from test_images_cli import png, canonical
from workload_cases import save, save_json, sha

PROMPT=Path(__file__).with_name('benchmark_prompts')/'B11.md'
PREVIEW_FILES={'mixed-pixels':'preview.png','historical-pixels':'historical.png'}


def original_pixels():
    return bytes(v for y in range(24) for x in range(32) for v in (x*5,y*7,(x+y)*4,255))


def mask_samples():
    return bytes(128 if x<16 else 255 for y in range(24) for x in range(32))


def mixed_pixels(source,offset):
    """Unchanged exact rational source-over oracle; no engine-rendered reference."""
    def premul(rgba):return [F(c*rgba[3],255**2) for c in rgba[:3]]+[F(rgba[3],255)]
    def over(back,front):return [s+b*(1-front[3]) for b,s in zip(back,front,strict=True)]
    result=bytearray()
    for y in range(24):
        for x in range(32):
            p=premul(source[(y*32+x)*4:(y*32+x+1)*4])
            shadow=[F(0)]*4
            if 8+offset[0]<=x<20+offset[0] and 6+offset[1]<=y<16+offset[1]:
                shadow=[v*F(173,255) for v in premul([0,0,0,128])]
            ink=[v/2 for v in premul([30,150,70,173])] if 8<=x<20 and 6<=y<16 else [F(0)]*4
            group=over(shadow,ink)
            mask=F(128,255) if x<16 else F(1)
            p=over(p,[v*mask*F(3,4) for v in group])
            if 25<=x<29 and 2<=y<6:p=premul(ORANGE)
            result.extend(int(v/p[3]*255+F(1,2)) for v in p[:3])
            result.append(int(p[3]*255+F(1,2)))
    return bytes(result)


def initial_document(asset,identities=None):
    names=identities or dict(document='mixed',image='image',group='group',art='art',unrelated='unrelated',asset='photo',effect='shadow')
    shadow=dict(id=names['effect'],operator=dict(type='shadow',offset=[3,2],sigma=0),color=[0,0,0,128])
    group=dict(id=names['group'],opacity=.75,mask=dict(width=32,height=24,gray_hex=mask_samples().hex(),linked=True),
               content=dict(type='group',isolated=True))
    art=rectangle(names['art'],8,6,12,10,[30,150,70,173]);art.update(parent=names['group'],fill_opacity=.5,effects=[shadow])
    items=[dict(id=names['image'],content=dict(type='image',asset_id=names['asset'],width=32,height=24)),group,art,
           rectangle(names['unrelated'],25,2,4,4,ORANGE)]
    return document(names['document'],'raster',32,24,resource_profile='large_raster',assets={names['asset']:asset},items=items)


def fixture(case):
    case.source('original.png',png(32,24,original_pixels()))


def solve(case):
    asset=case.call('image','asset.import',source_path='original.png')['asset']
    saved=store(case,initial_document(asset));before=source_snapshot(case,saved,'before')
    changed=copy.deepcopy(before['items'][2]['effects']);changed[0]['operator']['offset']=[5,-1]
    action=dict(type='edit',operations=[dict(op='effects',id=before['items'][2]['id'],effects=changed)])
    proposal=case.call('review','session.dry_run',session_id=saved['session_id'],request_id='shadow',expected_revision=0,action=action)
    edited=case.call('apply','session.apply_proposal',proposal=proposal['proposal'],action=action,response_mode='compact')['document_ref']
    source_snapshot(case,edited)
    for name,reference in [('preview',edited),('historical',saved)]:
        result=case.call(name,'document.preview',document=reference,preview=True)
        save(case.root/(name+'.png'),base64.b64decode(result['artifact']['data'],validate=True))
    case.call('verify-history','session.verify',session_id=saved['session_id'])
    save_json(case.root/'session.json',dict(session_id=saved['session_id'],original_revision=0,current_revision=edited['revision']))


def identities(before):
    require(len(before['items'])==4,'The original composition must retain four ordered items')
    items=before['items']
    return dict(document=before['id'],image=items[0]['id'],group=items[1]['id'],art=items[2]['id'],
                unrelated=items[3]['id'],asset=items[0]['content']['asset_id'],effect=items[2]['effects'][0]['id'])


def expected_asset(case):
    return dict(width=32,height=24,sha256=sha(canonical(32,24,original_pixels())),storage=dict(type='stored'),
                provenance=dict(source_sha256=case.sources['original.png'],interpretation='declared_srgb'))


def judge(case):
    before=strict_json(delivered(case,'before.json'));raw=delivered(case,'editable.json');actual=strict_json(raw)
    names=identities(before);asset=expected_asset(case)
    original=case.call('judge-template','document.validate',document=initial_document(asset,names))
    reopened=case.call('judge-reopen','document.validate',document=dict(file_path='editable.json',sha256=sha(raw)))
    def retained():
        require(before==original and actual==reopened and type(actual['revision']) is int and actual['revision']>0,
                'The saved original must match the full requested composition')
        wanted=copy.deepcopy(original);wanted['revision']=actual['revision']
        wanted['items'][2]['effects'][0]['operator']['offset']=[5,-1]
        require(actual==wanted,'Only the shadow offset and revision may change')
    case.check('composition-retained',retained)
    asset_root=None
    def resources():
        nonlocal asset_root
        require(before['assets']==actual['assets']=={names['asset']:asset},'Pinned original image identity or interpretation changed')
        asset_root=retained_asset_store(case,[canonical(32,24,original_pixels())])
    require(case.check('resource-identity',resources),'The original image store was not retained')
    rendered=case.call('judge-preview','document.preview',document=reopened,asset_root=asset_root,preview=True)
    def picture():
        expected=mixed_pixels(original_pixels(),(5,-1))
        png_check(delivered(case,'preview.png'),32,24,expected)
        png_check(base64.b64decode(rendered['artifact']['data'],validate=True),32,24,expected)
    case.check('mixed-pixels',picture)
    locator=strict_json(delivered(case,'session.json'))
    require(isinstance(locator,dict) and set(locator)=={'session_id','original_revision','current_revision'},'Invalid session locator')
    safe_name(locator['session_id'])
    require(type(locator['original_revision']) is int and locator['original_revision']==0 and
            type(locator['current_revision']) is int and locator['current_revision']==actual['revision']>0,'Invalid original/current revisions')
    session_root=retained_session_store(case,locator['session_id'])
    old=case.call('judge-original-revision','document.validate',document=dict(session_root=session_root,session_id=locator['session_id'],revision=0))
    current=case.call('judge-current-revision','document.validate',document=dict(session_root=session_root,session_id=locator['session_id'],revision=actual['revision']))
    historical=case.call('judge-historical','document.preview',document=old,asset_root=asset_root,preview=True)
    def old_picture():
        require(old==original,'Saved original revision differs from the requested composition')
        expected=mixed_pixels(original_pixels(),(3,2))
        png_check(delivered(case,'historical.png'),32,24,expected)
        png_check(base64.b64decode(historical['artifact']['data'],validate=True),32,24,expected)
    case.check('historical-pixels',old_picture)
    verified=case.call('judge-history','session.verify',session_root=session_root,session_id=locator['session_id'])
    case.check('history-valid',lambda:require(verified['valid'] and verified['revision']==actual['revision'] and
        old==original and current==actual,'History must bind the original composition, final delivery and current head'))


def mixed_composition(case):
    fixture(case);case.begin(PROMPT.read_text(encoding='utf-8'));solve(case)
    case.begin_judging();judge(case)
    for check,name in PREVIEW_FILES.items():
        if any(c['name']==check and c['status']=='pass' for c in case.checks):case.verified_preview(delivered(case,name))
