"""Original scripted task adapters with separate geometry/pixel/source oracles."""
import base64
import copy
import json
import xml.etree.ElementTree as ET

from benchmark_runtime import require
from workload_cases import document, rectangle, save, sha
from test_editing_cli import png_pixels
from synthetic_font import geometric_font
from test_images_cli import png, canonical


BLUE = [20, 80, 150, 255]
GREEN = [30, 150, 70, 255]
ORANGE = [220, 90, 30, 255]


def pixels(width, height, rectangles):
    """Independent integer rectangle oracle; fixtures deliberately avoid overlap blending."""
    out = bytearray(width*height*4)
    for x,y,w,h,color in rectangles:
        require(x >= 0 and y >= 0 and x+w <= width and y+h <= height, 'Oracle rectangle is out of bounds')
        for row in range(y,y+h):
            out[(row*width+x)*4:(row*width+x+w)*4] = bytes(color)*w
    return bytes(out)


def png_check(raw, width, height, expected):
    w,h,actual,_ = png_pixels(raw)
    require((w,h)==(width,height), 'Delivered image dimensions changed')
    require(actual==expected, 'Delivered pixels differ from independent authored geometry')


def ref(revision):
    return dict(session_id='work',revision=revision)


def store(case, doc, **options):
    return case.call('save','session.create',session_id='work',request_id='create',
                     document=doc,response_mode='compact',**options)['document_ref']


def apply(case,step,revision,operations,**kw):
    return case.call(step,'session.apply',session_id='work',request_id=step,
        expected_revision=revision,action=dict(type='edit',operations=operations),response_mode='compact',**kw)


def source_snapshot(case,doc,name='editable'):
    result=case.call(name,'document.publish',document=doc,
                     output=dict(format='snapshot',file_name=name+'.json'))
    raw=(case.root/(name+'.json')).read_bytes()
    require(sha(raw)==result['sha256'], 'Snapshot publication identity differs')
    return json.loads(raw)


def view(case,step,doc,check,width,height,expected,**options):
    result=case.call(step,'document.preview',document=doc,options=options,preview=True)
    raw=base64.b64decode(result['artifact']['data'],validate=True)
    save(case.root/(step+'.png'),raw)
    case.check(check,lambda:png_check(raw,width,height,expected),preview_step=step)
    return result


def verify_history(case):
    result=case.call('verify-history','session.verify',session_id='work')
    case.check('history-valid',lambda:require(result['valid'],'Invalid saved history'))


def diagram(case):
    font_bytes=geometric_font()
    case.source('original.ttf',font_bytes)
    case.source('font-license.txt',b'Original Inkbolt synthetic font. Permission to use, modify and redistribute with this notice.')
    case.begin('Create a 128x56 editable vector diagram: blue rectangle (8,8,48,36), green rectangle (80,8,40,36), '
        'gray connector (56,25,24,2). Use original.ttf at size 20, white labels AA at (20,16) and A at (96,16). '
        'Retain editable text and its licensed font, save a session, review a PNG and publish editable.json.')
    font=case.call('font','font.import',source_path='original.ttf',license_path='font-license.txt')
    doc=case.call('create','document.create',id='diagram',kind='vector',width=128,height=56)
    doc['fonts']={'face':font}
    items=[rectangle('left',8,8,48,36,BLUE),rectangle('right',80,8,40,36,GREEN),rectangle('connector',56,25,24,2,[80,80,80,255])]
    for ident,text,x in [('label-left','AA',20),('label-right','A',96)]:
        items.append(dict(id=ident,transform=[1,0,0,1,x,16],content=dict(type='text',frame=dict(
            text=text,width=32,height=24,style=dict(font_id='face',size=20,fill=[255]*4)))))
    doc['items']=items
    saved=store(case,doc)
    actual=source_snapshot(case,saved)
    def structure():
        require([i['id'] for i in actual['items']]==[i['id'] for i in items],'Diagram IDs/order changed')
        for a,e in zip(actual['items'],items):
            require(a['content']['type']==e['content']['type'],'Diagram content changed kind')
            if e['content']['type']=='text':
                require(a['content']['frame']['text']==e['content']['frame']['text'],'Label content changed')
                require(a['transform']==e['transform'],'Label moved')
            else: require(a['content']['geometry']==e['content']['geometry'],'Block geometry changed')
    case.check('diagram-structure',structure)
    case.check('font-identity',lambda:require(actual['fonts']['face']['sha256']==sha(font_bytes) and
        actual['fonts']['face']['license_sha256']==case.sources['font-license.txt'],'Font/license changed'))
    expected=pixels(128,56,[(8,8,48,36,BLUE),(80,8,40,36,GREEN),(56,25,24,2,[80,80,80,255]),
        (21,18,8,14,[255]*4),(33,18,8,14,[255]*4),(97,18,8,14,[255]*4)])
    view(case,'preview',saved,'diagram-pixels',128,56,expected)
    reopened=case.call('reopen','document.validate',document=dict(file_path='editable.json',sha256=sha((case.root/'editable.json').read_bytes())))
    case.check('editable-source',lambda:require(reopened==actual,'Editable document did not reopen exactly'))


def icons(case):
    case.begin('Create a 112x32 icon sheet with artboards board-0, board-1, board-2 at x=0,40,80; '
        'each is 32x32 with one 8x10 icon at local (12,11), respectively blue, green and orange. '
        'Keep stable IDs, review each independent board and publish an editable snapshot.')
    doc=case.call('create','document.create',id='icons',kind='vector',width=112,height=32)
    colors=[BLUE,GREEN,ORANGE]
    for index,color in enumerate(colors):
        board=f'board-{index}'
        doc['items'].append(dict(id=board,transform=[1,0,0,1,index*40,0],content=dict(type='frame',frame=dict(role='artboard',width=32,height=32))))
        item=rectangle(f'icon-{index}',12,11,8,10,color);item['parent']=board;doc['items'].append(item)
    saved=store(case,doc);actual=source_snapshot(case,saved)
    def structure():
        require([i['id'] for i in actual['items']]==['board-0','icon-0','board-1','icon-1','board-2','icon-2'],'IDs/order changed')
        for index in range(3):
            require(actual['items'][index*2]['transform']==[1,0,0,1,index*40,0],'Board spacing changed')
            require(actual['items'][index*2+1]['parent']==f'board-{index}','Icon ownership changed')
    case.check('sheet-structure',structure)
    for index,color in enumerate(colors):
        view(case,f'preview-{index}',saved,f'board-{index}-pixels',32,32,
             pixels(32,32,[(12,11,8,10,color)]),focus=dict(type='artboard',id=f'board-{index}'))
    case.check('editable-source',lambda:require(all(i['content']['type']=='vector' for i in actual['items'][1::2]),'Icons are no longer editable vector geometry'))


def large_layout(case):
    items=[rectangle(f'cell-{i}',(i%100)*10,(i//100)*10,6,6,BLUE) for i in range(5000)]
    seed=case.seed(document('large-layout','vector',1000,500,resource_profile='large_vector',items=items))
    case.begin('Open source.json as a large vector document, save it, inspect cell-2473, and move only '
        'that object one pixel right and one pixel down. Preserve the other 4,999 objects, the '
        'original revision and source file. Review current and historical images and verify history.')
    saved=store(case,seed)
    case.call('inspect-target','document.inspect.page',document=saved,
              options=dict(view=dict(collection='items',ids=['cell-2473'],fields=['geometry','transform','bounds'])))
    apply(case,'move',0,[dict(op='transform',id='cell-2473',matrix=[1,0,0,1,1,1],space='world')])
    current=source_snapshot(case,ref(1))
    def structure():
        require(len(current['items'])==5000,'Large layout lost objects')
        for index,item in enumerate(current['items']):
            require(item['id']==f'cell-{index}','Large layout identity/order changed')
            require(item['content']['geometry']==items[index]['content']['geometry'],'Source controls changed')
            require(item['content']['fill']==BLUE,'An unrelated paint changed')
            require(item['transform']==[1,0,0,1,1 if index==2473 else 0,1 if index==2473 else 0],'Unexpected object movement')
    case.check('only-target-changed',structure)
    rects=[((i%100)*10,(i//100)*10,6,6,BLUE) for i in range(5000)]
    original=pixels(1000,500,rects);rects[2473]=(731,241,6,6,BLUE)
    view(case,'preview',ref(1),'large-layout-pixels',1000,500,pixels(1000,500,rects),render_options=dict(evaluation='tiled'))
    view(case,'historical',saved,'historical-pixels',1000,500,original,render_options=dict(evaluation='tiled'))
    verify_history(case)


def svg_artwork(case):
    source=b'<svg xmlns="http://www.w3.org/2000/svg" width="32" height="24"><desc>Original benchmark description</desc><g id="layer" transform="translate(3,2)"><path id="block" d="M2 3 H10 V9 H2 Z" fill="#145096"/></g></svg>'
    case.source('original.svg',source)
    case.begin('Import original.svg, preserve its layer and editable path, then move the path four '
        'pixels right and one up in world coordinates. Inspect declared import losses, preserve '
        'the original bytes and publish the revised editable source and SVG. Review the result.')
    imported=case.call('import','svg.import',id='imported',source=dict(kind='file',source_path='original.svg'))
    mapping={m['source_id']:m['item_id'] for m in imported['mapping'] if m.get('source_id')}
    item=next(i for i in imported['document']['items'] if i['id']==mapping['block'])
    case.check('imported-structure',lambda:require(item['parent']==mapping['layer'] and
        item['content']['geometry']['shape']=='path' and imported['source']['sha256']==sha(source),'SVG structure or source identity changed'))
    case.check('declared-losses',lambda:require(isinstance(imported['losses'],list) and
        any('Source IDs' in loss for loss in imported['losses']) and any('Description' in loss for loss in imported['losses']),'Required XML/description loss disclosure is absent'))
    store(case,imported['document'])
    apply(case,'move',0,[dict(op='transform',id=mapping['block'],matrix=[1,0,0,1,4,-1],space='world')])
    actual=source_snapshot(case,ref(1))
    case.call('deliver-svg','document.publish',document=ref(1),output=dict(format='svg',file_name='revised.svg'))
    tree=ET.fromstring((case.root/'revised.svg').read_bytes())
    revised=next(i for i in actual['items'] if i['id']==mapping['block'])
    case.check('editable-source',lambda:require(revised['content']==item['content'] and
        revised['parent']==item['parent'] and len(tree.findall('.//{*}path'))==1,'SVG path editing structure changed'))
    view(case,'preview',ref(1),'revised-pixels',32,24,pixels(32,24,[(9,4,8,6,BLUE)]))


def palette(case):
    swatch=lambda color:dict(name='Shared',definition=dict(type='process',color=dict(space='srgb',components=[v/255 for v in color[:3]])))
    items=[rectangle('first',2,4,8,8),rectangle('second',12,4,8,8),rectangle('unrelated',22,4,8,8,GREEN)]
    for item in items[:2]: item['content']['fill']=dict(swatch='shared')
    seed=case.seed(document('palette','vector',32,16,swatches=dict(shared=swatch(BLUE)),items=items))
    case.begin('Open source.json and recolor shared from blue to RGBA (220,90,30,255). '
        'Keep both live swatch dependencies and the unrelated green artwork unchanged. '
        'Review current and original revisions and verify saved history.')
    saved=store(case,seed)
    case.call('inspect-palette','swatch.inspect',document=saved)
    apply(case,'recolor',0,[dict(op='swatch',id='shared',swatch=swatch(ORANGE))])
    actual=source_snapshot(case,ref(1))
    case.check('live-dependencies',lambda:require(all(i['content']['fill'].get('swatch')=='shared' for i in actual['items'][:2])
        and actual['items'][2]['content']['fill']==GREEN and actual['swatches']['shared']==swatch(ORANGE),'Shared dependencies or unrelated paint changed'))
    for step,revision,color,check in [('preview',1,ORANGE,'palette-pixels'),('historical',0,BLUE,'historical-pixels')]:
        view(case,step,ref(revision),check,32,16,pixels(32,16,[(2,4,8,8,color),(12,4,8,8,color),(22,4,8,8,GREEN)]))
    verify_history(case)


def transparent_delivery(case):
    case.begin('Create a transparent 1920x1080 vector screen graphic with one RGBA (20,80,150,128) '
        'rectangle at (10,20), size 200x100. Retain editable source and private source metadata. '
        'Preflight and deliver screen.png with sRGB straight alpha and no matte or descriptions. '
        'Prove a duplicate publication cannot overwrite the output.')
    preset=case.call('preset','preset.create',id='screen',version=1,preset=dict(type='screen',size='presentation_hd',
        kind='vector',background=dict(type='transparent')))
    doc=preset['document'];item=rectangle('graphic',10,20,200,100,[20,80,150,128]);item['parent']='canvas'
    doc['items'].append(item);doc['metadata']=dict(private={'note':'original private source note'})
    saved=store(case,doc)
    output=preset['delivery']|dict(file_name='screen.png')
    preflight=case.call('preflight','document.preflight',document=saved,output=output)
    require(preflight['ready'],'Screen output is not ready')
    delivered=case.call('deliver','document.publish',document=saved,output=output)
    raw=(case.root/'screen.png').read_bytes()
    case.check('transparent-pixels',lambda:png_check(raw,1920,1080,pixels(1920,1080,[(10,20,200,100,[20,80,150,128])])),preview_step='deliver')
    _,_,_,chunks=png_pixels(raw)
    case.check('screen-color',lambda:require(b'sRGB' in chunks and b'iCCP' not in chunks and b'tEXt' not in chunks
        and sha(raw)==delivered['sha256'],'Screen color/metadata or delivery identity changed'))
    actual=source_snapshot(case,saved)
    case.check('editable-source',lambda:require(actual['items'][1]['content']['geometry']==item['content']['geometry'] and
        actual['metadata']['private']['note']=='original private source note','Editable controls or private source metadata changed'))
    case.call('collision','document.publish',document=saved,output=output,expected_error='OUTPUT_EXISTS')
    case.check('no-overwrite',lambda:require((case.root/'screen.png').read_bytes()==raw,'Existing output was overwritten'))


def two_items():
    return document('revisions','vector',32,16,items=[rectangle('target',2,4,8,8,BLUE),rectangle('other',22,4,8,8,GREEN)])


def lost_response(case):
    seed=case.seed(two_items())
    case.begin('Open source.json, move target three pixels right and save the edit with request ID move. '
        'The adapter will drop that successful response. Recover the original receipt and retry safely. '
        'Undo, retry the old request again, and prove neither retry duplicates or reapplies the edit.')
    store(case,seed)
    request=dict(session_id='work',request_id='move',expected_revision=0,response_mode='compact',
        action=dict(type='edit',operations=[dict(op='transform',id='target',matrix=[1,0,0,1,3,0],space='world')]))
    case.call('lost','session.apply',discard=True,**request)
    recovered=case.call('recover-receipt','session.receipt',session_id='work',request_id='move',response_mode='compact')
    # The hidden response is inspected by this independent receipt oracle only;
    # the scripted recovery path uses the already-known request ID.
    original=case.results['lost']['result']
    case.check('original-receipt',lambda:require(recovered['receipt_summary']==original['receipt_summary'],'Recovered a different receipt'))
    retry=case.call('retry','session.apply',retry_of='lost',**request)
    case.check('retry-idempotent',lambda:require(retry['replayed'] and retry['receipt_summary']==original['receipt_summary'] and
        retry['document_ref']['revision']==1,'Retry changed the edit or its revision'))
    view(case,'preview',ref(1),'edited-pixels',32,16,pixels(32,16,[(5,4,8,8,BLUE),(22,4,8,8,GREEN)]))
    case.call('undo','session.apply',session_id='work',request_id='undo',expected_revision=1,action=dict(type='undo'),response_mode='compact')
    case.call('retry-after-undo','session.apply',retry_of='lost',**request)
    current=source_snapshot(case,ref(2))
    case.check('undo-preserved',lambda:require(current['revision']==2 and all(i['transform']==[1,0,0,1,0,0] for i in current['items']), 'Historical retry reapplied an undone change'))
    verify_history(case)


def conflicting_writers(case):
    seed=case.seed(two_items())
    case.begin('Open source.json. Review a proposal to move target three pixels right. A different '
        'writer moves other two pixels left first. Reject the stale proposal; review and apply '
        'a replacement on the new head, preserving both intents and original history.')
    saved=store(case,seed)
    action=dict(type='edit',operations=[dict(op='transform',id='target',matrix=[1,0,0,1,3,0],space='world')])
    stale=case.call('review-old','session.dry_run',session_id='work',request_id='move-target',expected_revision=0,action=action)
    apply(case,'other-writer',0,[dict(op='transform',id='other',matrix=[1,0,0,1,-2,0],space='world')])
    rejected=case.call('stale','session.apply_proposal',proposal=stale['proposal'],action=action,expected_error='REVISION_CONFLICT',response_mode='compact')
    case.check('stale-rejected',lambda:require(rejected['code']=='REVISION_CONFLICT','Stale proposal was accepted'))
    reviewed=case.call('review-current','session.dry_run',session_id='work',request_id='move-target',expected_revision=1,action=action)
    case.call('apply-reviewed','session.apply_proposal',proposal=reviewed['proposal'],action=action,response_mode='compact')
    current=source_snapshot(case,ref(2))
    case.check('both-intents-preserved',lambda:require([i['transform'] for i in current['items']]==[[1,0,0,1,3,0],[1,0,0,1,-2,0]] and
        [i['content']['geometry'] for i in current['items']]==[i['content']['geometry'] for i in two_items()['items']], 'Conflict resolution lost an intent or source geometry'))
    view(case,'preview',ref(2),'conflict-pixels',32,16,pixels(32,16,[(5,4,8,8,BLUE),(20,4,8,8,GREEN)]))
    view(case,'historical',saved,'historical-pixels',32,16,pixels(32,16,[(2,4,8,8,BLUE),(22,4,8,8,GREEN)]))
    verify_history(case)


def foreground_mask(case):
    original=bytes(v for y in range(16) for x in range(16) for v in (x*11,y*13,(x+y)*7,255))
    seed=case.seed(document('foreground','raster',16,16,items=[dict(id='pixels',content=dict(
        type='raster',width=16,height=16,rgba_hex=original.hex()))]))
    case.begin('Select the L-shaped foreground polygon (4,3),(12,3),(12,7),(8,7),(8,13),(4,13) '
        'in source.json and attach a linked editable mask. Retain the entire original pixel layer, '
        'the selection and old revision. Review masked/current and original images.')
    saved=store(case,seed)
    apply(case,'mask',0,[dict(op='selection_shape',boundary=dict(shape='polygon',points=[[4,3],[12,3],[12,7],[8,7],[8,13],[4,13]])),
                         dict(op='mask_from_selection',id='pixels',linked=True)])
    current=source_snapshot(case,ref(1))
    selected=bytes(255 if (4<=x<12 and 3<=y<7) or (4<=x<8 and 7<=y<13) else 0 for y in range(16) for x in range(16))
    case.check('selection-coverage',lambda:require(bytes.fromhex(current['selection']['gray_hex'])==selected,'Selection coverage differs'))
    case.check('retained-pixels',lambda:require(bytes.fromhex(current['items'][0]['content']['rgba_hex'])==original
        and current['items'][0]['mask']['linked'],'Mask destructively changed source pixels'))
    expected=b''.join(original[i*4:i*4+4] if alpha else bytes(4) for i,alpha in enumerate(selected))
    view(case,'preview',ref(1),'masked-pixels',16,16,expected)
    view(case,'historical',saved,'historical-pixels',16,16,original)
    verify_history(case)


def local_retouch(case):
    clean=bytes(v for y in range(16) for x in range(16) for v in (20+(x%4)*40,30+(y%4)*40,10+((x+y)%4)*50,255))
    original=bytearray(clean)
    for y in (10,11):original[(y*16+10)*4:(y*16+12)*4]=bytes([255,0,255,255])*2
    seed=case.seed(document('retouch','raster',16,16,items=[dict(id='pixels',content=dict(type='raster',width=16,height=16,rgba_hex=original.hex()))]))
    case.begin('Repair the 2x2 defect at (10,10) in source.json by cloning the original same-layer '
        'patch at (2,2), using nearest sampling. Retain all unaffected pixels, original source and history. '
        'Review corrected and original images and verify the saved history.')
    saved=store(case,seed)
    apply(case,'retouch',0,[dict(op='retouch',id='pixels',options=dict(source_id='pixels',
        region=dict(x=10,y=10,width=2,height=2),source_transform=[1,0,0,1,-8,-8],sampling='nearest',mode=dict(type='clone')))])
    current=source_snapshot(case,ref(1))
    case.check('exact-local-repair',lambda:require(bytes.fromhex(current['items'][0]['content']['rgba_hex'])==clean,'Repair or unaffected samples differ'))
    view(case,'preview',ref(1),'repaired-pixels',16,16,clean)
    view(case,'historical',saved,'historical-pixels',16,16,bytes(original))
    verify_history(case)


def resource_repair(case):
    assets={};items=[]
    for index,color in enumerate([BLUE,GREEN]):
        raw=bytes(color)*4
        case.source(f'original-{index}.png',png(2,2,raw))
        assets[f'asset-{index}']=dict(width=2,height=2,sha256=sha(canonical(2,2,raw)),storage=dict(type='stored'))
        items.append(dict(id=f'image-{index}',transform=[1,0,0,1,index*8,0],content=dict(type='image',asset_id=f'asset-{index}',width=8,height=8)))
    # Construct corrupt and missing cache fixtures directly; never replace a valid
    # resource or original media file to introduce the fault.
    corrupt='broken-assets/'+assets['asset-0']['sha256']+'.rgba8'
    case.source(corrupt,b'original deliberately corrupt cache fixture')
    seed=case.seed(document('resources','vector',16,8,assets=assets,items=items))
    case.begin('source.json binds one corrupt and one missing image cache under broken-assets. '
        'Diagnose both at their resource locations, recreate exact resources from original-0.png '
        'and original-1.png in repaired-assets, review and commit only the resource binding change. '
        'Preserve artwork, original media, the old broken cache and historical bindings.')
    saved=store(case,seed,resources=dict(asset_root='broken-assets'))
    diagnosed=case.call('diagnose','document.check',document=saved)
    case.check('located-diagnostics',lambda:require(diagnosed['status']=='fail' and
        {i['error']['code'] for i in diagnosed['issues']}=={'ASSET_MISSING','ASSET_CORRUPT'} and
        {i['location']['pointer'] for i in diagnosed['issues']}=={'/assets/asset-0','/assets/asset-1'},'Missing/corrupt resources were not independently located'))
    imported=[case.call(f'repair-{i}','asset.import',source_path=f'original-{i}.png',store_root='repaired-assets')['asset'] for i in range(2)]
    case.check('verified-replacements',lambda:require([a['sha256'] for a in imported]==[a['sha256'] for a in assets.values()], 'Replacement resource identity differs'))
    before=source_snapshot(case,saved,'before')
    action=dict(type='resources',resources=dict(asset_root='repaired-assets'))
    proposal=case.call('review','session.dry_run',session_id='work',request_id='repair',expected_revision=0,action=action)
    case.call('apply-repair','session.apply_proposal',proposal=proposal['proposal'],action=action,response_mode='compact')
    current=source_snapshot(case,ref(1))
    case.check('unchanged-artwork',lambda:require(current['items']==before['items'] and current['assets']==before['assets'],'Resource repair edited artwork'))
    view(case,'preview',ref(1),'repaired-pixels',16,8,pixels(16,8,[(0,0,8,8,BLUE),(8,0,8,8,GREEN)]))
    old=case.call('old-diagnostics','document.check',document=saved)
    case.check('old-bindings-preserved',lambda:require(old==diagnosed and not (case.root/'broken-assets'/(assets['asset-1']['sha256']+'.rgba8')).exists(),'Historical resource binding or missing cache was silently repaired'))
    verify_history(case)


def seeded_repair(case):
    case.source('original.ttf',geometric_font())
    case.source('font-license.txt',b'Original synthetic Inkbolt font; permission to use and redistribute.')
    case.begin('Diagnose an overflowing AA text frame: size 20, width 12, height 24, no wrapping. '
        'Change only its width to 24 through a reviewed proposal, preserving the text/font and '
        'unrelated rectangle at (32,20), size 8x8. Review, preflight and publish repaired.png.')
    font=case.call('font','font.import',source_path='original.ttf',license_path='font-license.txt')
    frame=dict(text='AA',width=12,height=24,wrap=False,style=dict(font_id='face',size=20,fill=BLUE))
    doc=document('repair','vector',48,32,fonts=dict(face=font),items=[dict(id='label',content=dict(type='text',frame=frame)),rectangle('other',32,20,8,8,GREEN)])
    saved=store(case,doc);before=source_snapshot(case,saved,'before')
    diagnosed=case.call('diagnose','document.check',document=saved)
    failed=case.call('failed-preflight','document.preflight',document=saved,output=dict(file_name='repaired.png',format='png'))
    case.check('seeded-diagnosis',lambda:require(diagnosed['status']=='fail' and not failed['ready'] and
        any(i['error']['code']=='TEXT_OVERFLOW' and i['error']['item_id']=='label' and
            'text.inspect' in i['recovery']['commands'] for i in diagnosed['issues']),'Overflow was not actionable'))
    fixed=copy.deepcopy(frame);fixed['width']=24
    action=dict(type='edit',operations=[dict(op='text',id='label',frame=fixed)])
    proposed=case.call('review','session.dry_run',session_id='work',request_id='repair',expected_revision=0,
        action=action,options=dict(preview=True),preview=True)
    raw=base64.b64decode(proposed['preview']['data'],validate=True)
    save(case.root/'review.png',raw)
    expected=pixels(48,32,[(1,2,8,14,BLUE),(13,2,8,14,BLUE),(32,20,8,8,GREEN)])
    case.check('repair-pixels',lambda:png_check(raw,48,32,expected),preview_step='review')
    case.call('apply-repair','session.apply_proposal',proposal=proposed['proposal'],action=action,response_mode='compact')
    current=source_snapshot(case,ref(1))
    wanted=copy.deepcopy(before);wanted['revision']=1;wanted['items'][0]['content']['frame']['width']=24
    case.check('no-collateral-edits',lambda:require(current==wanted and current['fonts']['face']['sha256']==case.sources['original.ttf'],'Repair changed collateral content'))
    ready=case.call('preflight','document.preflight',document=ref(1),output=dict(file_name='repaired.png',format='png'))
    require(ready['ready'] and not (case.root/'repaired.png').exists(),'Preflight wrote output or failed')
    delivered=case.call('deliver','session.publish',session_id='work',expected_revision=1,output=dict(file_name='repaired.png',format='png'))
    def delivered_correct():
        require(delivered['sha256']==ready['prepared_output']['sha256'],'Preflight/publication identity changed')
        png_check((case.root/'repaired.png').read_bytes(),48,32,expected)
    case.check('preflight-delivery',delivered_correct)
    verify_history(case)
