"""B12 unchanged layout fixture, external solve and delivered-evidence judging."""
import base64
import copy
from pathlib import Path

from benchmark_diagram import delivered,retained_font_store
from benchmark_graphics import BLUE,GREEN,ORANGE,document,pixels,png_check,store,source_snapshot
from benchmark_large_layout import retained_session_store
from benchmark_stores import retained_asset_store,retained_publication_store
from benchmark_runtime import require,safe_name,strict_json
from benchmark_typography import LICENSE
from synthetic_font import geometric_font
from test_images_cli import png,canonical
from workload_cases import save_json,sha

PROMPT=Path(__file__).with_name('benchmark_prompts')/'B12.md'
FONT_FAMILY='Inkbolt Variant Fixture'
BOARDS=(('wide',48,24,0,0),('square',32,32,56,0),('tall',24,48,0,40))
ROWS={'wide':('AAA',[36,16],'green'),'square':('AA',[24,24],'orange'),'tall':('A',[10,38],'green')}
PREVIEW_FILES={name+'-pixels':name+'.png' for name,*_ in BOARDS}


def fixture(case):
    case.source('original.ttf',geometric_font());case.source('font-license.txt',LICENSE)
    for name,color in [('green',GREEN),('orange',ORANGE)]:case.source(name+'.png',png(2,2,bytes(color)*4))
    # The unnamed original stays byte-identical. SVG font selection requires a
    # family; this original companion differs only in naming/checksum metadata.
    case.source('renderer.ttf',geometric_font(family=FONT_FAMILY))


def names_from(base):
    items=base['items'];require(len(items)==9,'Expected one shared source and three instances')
    return dict(document=base['id'],shared=items[0]['id'],title=items[1]['id'],image=items[2]['id'],
        face=items[1]['content']['frame']['style']['font_id'],green=items[2]['content']['asset_id'],
        orange=base['variants']['definition']['datasets']['square']['values']['image']['value'],
        copies=[items[i]['id'] for i in (4,6,8)])


def initial_document(font,assets,names=None):
    n=names or dict(document='variants',shared='shared',title='title',image='image',face='face',
                   green='green',orange='orange',copies=['copy-wide','copy-square','copy-tall'])
    items=[dict(id=n['shared'],content=dict(type='component_source')),
        dict(id=n['title'],parent=n['shared'],transform=[1,0,0,1,2,0],content=dict(type='text',frame=dict(
            text='A',width=44,height=24,wrap=False,style=dict(font_id=n['face'],size=20,fill=BLUE)))),
        dict(id=n['image'],parent=n['shared'],transform=[1,0,0,1,2,16],
             content=dict(type='image',asset_id=n['green'],width=4,height=4))]
    for index,(name,w,h,x,y) in enumerate(BOARDS):
        items.extend([dict(id=name,transform=[1,0,0,1,x,y],content=dict(type='frame',frame=dict(role='artboard',width=w,height=h))),
            dict(id=n['copies'][index],parent=name,content=dict(type='instance',instance=dict(source=n['shared'])))])
    return document(n['document'],'vector',96,96,fonts={n['face']:font},assets={n[k]:v for k,v in assets.items()},items=items)


def definition(names):
    def value(kind,value):return dict(type=kind,value=value)
    datasets={}
    for name,(label,position,image) in ROWS.items():
        row=dict(values=dict(label=value('text',dict(text=label,ranges=[])),
                             place=value('position',position),image=value('image',names[image])))
        if name=='square':row['parent']='wide'
        datasets[name]=row
    return dict(bindings=[dict(key=k,item_id=i,property=p) for k,i,p in
        [('label',names['title'],'text'),('place',names['image'],'position'),('image',names['image'],'image')]],datasets=datasets)


def solve(case):
    font=case.call('font','font.import',source_path='original.ttf',license_path='font-license.txt')
    assets={name:case.call('image-'+name,'asset.import',source_path=name+'.png')['asset'] for name in ('green','orange')}
    doc=initial_document(font,assets);saved=store(case,doc);session=saved['session_id']
    n=dict(title=doc['items'][1]['id'],image=doc['items'][2]['id'],green=doc['items'][2]['content']['asset_id'],
           orange=next(k for k in doc['assets'] if k!=doc['items'][2]['content']['asset_id']))
    def edit(step,operation):
        nonlocal saved
        saved=case.call(step,'session.apply',session_id=session,request_id=step,expected_revision=saved['revision'],
            action=dict(type='edit',operations=[operation]),response_mode='compact')['document_ref']
    edit('define',dict(op='variants_set',definition=definition(n)))
    base=source_snapshot(case,saved,'base');revisions=dict(base=base['revision']);receipts={};outputs={}
    for name,*_ in BOARDS:
        edit('select-'+name,dict(op='variant_select',dataset=name));revisions[name]=saved['revision']
        source_snapshot(case,saved,'source-'+name)
        request='delivery-'+name
        result=case.call('deliver-'+name,'document.publish',document=saved,
            output=dict(format='png',file_name=name+'.png',artboard_id=name),receipt=dict(request_id=request))
        outputs[name]=result['sha256'];receipts[name]=request
    edit('restore-base',dict(op='variant_select',dataset=None));source_snapshot(case,saved,'restored')
    revisions['restored']=saved['revision']
    case.call('verify-history','session.verify',session_id=session)
    save_json(case.root/'outputs.json',outputs)
    save_json(case.root/'session.json',dict(session_id=session,revisions=revisions,publications=receipts))


def expected_picture(name):
    _,w,h,_,_=next(b for b in BOARDS if b[0]==name)
    label,(x,y),image=ROWS[name]
    return pixels(w,h,[(3+12*i,2,8,14,BLUE) for i in range(len(label))]+[(x,y,4,4,GREEN if image=='green' else ORANGE)])


def expected_base(case,base,n):
    font=dict(sha256=case.sources['original.ttf'],license_sha256=case.sources['font-license.txt'],face_index=0,bytes=len(geometric_font()))
    assets={name:dict(width=2,height=2,sha256=sha(canonical(2,2,bytes(color)*4)),storage=dict(type='stored'),
        provenance=dict(source_sha256=case.sources[name+'.png'],interpretation='declared_srgb')) for name,color in [('green',GREEN),('orange',ORANGE)]}
    value=initial_document(font,assets,n);value['revision']=base['revision']
    wanted_definition=definition(n);bindings={row['key']:row for row in wanted_definition['bindings']}
    order=[row['key'] for row in base['variants']['definition']['bindings']]
    require(len(order)==3 and all(isinstance(key,str) for key in order) and set(order)==set(bindings),
            'Expected exactly the label, place and image binding keys')
    wanted_definition['bindings']=[bindings[key] for key in order]
    initial=dict(label=dict(type='text',value=dict(text='A',ranges=[])),
                 place=dict(type='position',value=[2,16]),image=dict(type='image',value=n['green']))
    value['variants']=dict(definition=wanted_definition,selected=None,base=[initial[key] for key in order])
    return case.call('judge-template','document.validate',document=value)


def judge(case):
    files={'base':'base.json',**{name:'source-'+name+'.json' for name,*_ in BOARDS},'restored':'restored.json'}
    snapshots={key:strict_json(delivered(case,name)) for key,name in files.items()}
    base=snapshots['base'];names=names_from(base);template=expected_base(case,base,names)
    reopened={key:case.call('judge-reopen-'+key,'document.validate',document=dict(file_path=name,sha256=sha(delivered(case,name))))
              for key,name in files.items()}
    font_root=asset_root=None
    def preserved():
        nonlocal font_root,asset_root
        require(base==template and base==reopened['base'],'The complete base layout or variant definition changed')
        wanted=copy.deepcopy(base);wanted['revision']=snapshots['restored']['revision']
        require(wanted==snapshots['restored']==reopened['restored'],'The complete base was not restored')
        font_root=retained_font_store(case)
        asset_root=retained_asset_store(case,[canonical(2,2,bytes(color)*4) for color in (GREEN,ORANGE)])
    require(case.check('base-preserved',preserved),'The complete base and original resources were not retained')
    def bindings():
        require(base==template,'The variant definition differs from the requested bindings/inheritance')
        for name,(label,position,image) in ROWS.items():
            actual=snapshots[name];wanted=copy.deepcopy(base);wanted['revision']=actual['revision']
            wanted['variants']['selected']=name;wanted['items'][1]['content']['frame']['text']=label
            wanted['items'][2]['transform'][4:]=position;wanted['items'][2]['content']['asset_id']=names[image]
            require(wanted==actual==reopened[name],'Selection changed bindings or unrelated shared state: '+name)
    case.check('variant-bindings',bindings)
    for name,w,h,_,_ in BOARDS:
        rendered=case.call('judge-render-'+name,'document.preview',document=reopened[name],
                          font_root=font_root,asset_root=asset_root,options=dict(focus=dict(type='artboard',id=name)),preview=True)
        def picture(name=name,w=w,h=h,rendered=rendered):
            png_check(delivered(case,name+'.png'),w,h,expected_picture(name))
            png_check(base64.b64decode(rendered['artifact']['data'],validate=True),w,h,expected_picture(name))
        case.check(name+'-pixels',picture)
    locator=strict_json(delivered(case,'session.json'))
    require(set(locator)=={'session_id','revisions','publications'} and set(locator['revisions'])==set(files) and
            set(locator['publications'])==set(ROWS),'Invalid variant session locator')
    safe_name(locator['session_id'])
    revisions=[locator['revisions'][name] for name in files]
    require(all(type(v) is int and v>=0 for v in revisions) and all(a<b for a,b in zip(revisions,revisions[1:])),
            'Base, selected and restored revisions must be in increasing order')
    session_root=retained_session_store(case,locator['session_id'])
    saved={name:case.call('judge-saved-'+name,'document.validate',document=dict(session_root=session_root,session_id=locator['session_id'],revision=revision))
           for name,revision in locator['revisions'].items()}
    receipts={}
    for name,request in locator['publications'].items():
        safe_name(request);receipts[name]=case.call('judge-receipt-'+name,'publication.receipt',
            receipt_root=retained_publication_store(case,request),request_id=request)
    def outputs():
        identities=strict_json(delivered(case,'outputs.json'))
        require(set(identities)==set(ROWS),'All three delivery identities must be retained')
        for name in ROWS:
            row=receipts[name];result=row['result']
            require(row['state']=='complete' and result['sha256']==identities[name]==sha(delivered(case,name+'.png')) and
                result['revision']==snapshots[name]['revision'] and result['document_id']==base['id'] and
                result['artboard_id']==name and result['variant']==name and result['format']=='png',
                'Earlier output differs from its completed publication receipt: '+name)
    case.check('outputs-preserved',outputs)
    verified=case.call('judge-history','session.verify',session_root=session_root,session_id=locator['session_id'])
    case.check('history-valid',lambda:require(verified['valid'] and verified['revision']==revisions[-1] and
        all(saved[name]==snapshots[name] and saved[name]['revision']==locator['revisions'][name] for name in files),
        'History must bind every selected snapshot and the restored current head'))


def layout_variants(case):
    fixture(case);case.begin(PROMPT.read_text(encoding='utf-8'));solve(case);case.begin_judging();judge(case)
    for check,name in PREVIEW_FILES.items():
        if any(c['name']==check and c['status']=='pass' for c in case.checks):case.verified_preview(delivered(case,name))
