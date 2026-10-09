"""Original mixed-composition, variant and physical-delivery task adapters."""
import copy
from fractions import Fraction as F

from benchmark_graphics import (BLUE, GREEN, ORANGE, document, rectangle, pixels,
    ref, store, apply, source_snapshot, view, verify_history, png_check, sha)
from benchmark_runtime import require
from benchmark_typography import LICENSE
from synthetic_font import geometric_font
from test_images_cli import png, canonical
from test_profiles_cli import embedded, linear_profile
from test_swatch_profiles_cli import managed
from cmyk_fixtures import cmyk_profile
from pdf_reader import Pdf
from test_ink_delivery_cli import painted


def mixed_pixels(source,offset):
    """Exact rational source-over; no engine evaluator or rendered reference."""
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


def mixed_composition(case):
    original=bytes(v for y in range(24) for x in range(32) for v in (x*5,y*7,(x+y)*4,255))
    case.source('original.png',png(32,24,original))
    case.begin('Import original.png into a 32x24 raster document with the large_raster profile. Above it place an isolated '
        'group at opacity .75 with a linked full-canvas scalar mask: 128 left of x=16, 255 elsewhere. '
        'Its child is a green RGBA (30,150,70,173) vector rectangle (8,6,12,10), fill opacity .5, '
        'and a black alpha-128 shadow at offset (3,2), sigma 0. Add unrelated orange artwork '
        '(25,2,4,4) above the group. Review and change only the shadow offset to (5,-1). '
        'Preserve the pinned image, masks, original controls and previous revision; review both.')
    imported=case.call('image','asset.import',source_path='original.png')['asset']
    shadow=dict(id='shadow',operator=dict(type='shadow',offset=[3,2],sigma=0),color=[0,0,0,128])
    group=dict(id='group',opacity=.75,mask=dict(width=32,height=24,
        gray_hex=bytes(128 if x<16 else 255 for y in range(24) for x in range(32)).hex(),linked=True),
        content=dict(type='group',isolated=True))
    art=rectangle('art',8,6,12,10,[30,150,70,173]);art.update(parent='group',fill_opacity=.5,effects=[shadow])
    items=[dict(id='image',content=dict(type='image',asset_id='photo',width=32,height=24)),group,art,rectangle('unrelated',25,2,4,4,ORANGE)]
    saved=store(case,document('mixed','raster',32,24,resource_profile='large_raster',assets=dict(photo=imported),items=items))
    before=source_snapshot(case,saved,'before')
    changed=copy.deepcopy(before['items'][2]['effects']);changed[0]['operator']['offset']=[5,-1]
    action=dict(type='edit',operations=[dict(op='effects',id='art',effects=changed)])
    proposal=case.call('review','session.dry_run',session_id='work',request_id='shadow',expected_revision=0,action=action)
    case.call('apply','session.apply_proposal',proposal=proposal['proposal'],action=action,response_mode='compact')
    current=source_snapshot(case,ref(1))
    wanted=copy.deepcopy(before);wanted['revision']=1;wanted['items'][2]['effects']=changed
    case.check('composition-retained',lambda:require(current==wanted,'Composition revision changed unrelated controls'))
    case.check('resource-identity',lambda:require(current['assets']['photo']['sha256']==sha(canonical(32,24,original)),
        'Original raster identity changed'))
    view(case,'preview',ref(1),'mixed-pixels',32,24,mixed_pixels(original,(5,-1)))
    view(case,'historical',saved,'historical-pixels',32,24,mixed_pixels(original,(3,2)))
    verify_history(case)


def layout_variants(case):
    case.source('original.ttf',geometric_font());case.source('font-license.txt',LICENSE)
    for name,color in [('green',GREEN),('orange',ORANGE)]:case.source(name+'.png',png(2,2,bytes(color)*4))
    case.begin('Build one editable shared component with blue size-20 original.ttf label A at '
        '(2,0), plus a 4x4 green image at (2,16). Place it on wide 48x24, square 32x32 and tall '
        '24x48 artboards. Define typed text, position and image bindings. Wide selects AAA and '
        'green at (36,16); square inherits wide but selects AA and orange at (24,24); tall selects '
        'A and green at (10,38). Export each corresponding artboard under its own name. '
        'Restore the base and preserve definitions, fonts, images, previous outputs and history.')
    font=case.call('font','font.import',source_path='original.ttf',license_path='font-license.txt')
    assets={name:case.call('image-'+name,'asset.import',source_path=name+'.png')['asset'] for name in ['green','orange']}
    items=[dict(id='shared',content=dict(type='component_source')),
        dict(id='title',parent='shared',transform=[1,0,0,1,2,0],content=dict(type='text',frame=dict(
            text='A',width=44,height=24,wrap=False,style=dict(font_id='face',size=20,fill=BLUE)))),
        dict(id='image',parent='shared',transform=[1,0,0,1,2,16],content=dict(type='image',asset_id='green',width=4,height=4))]
    boards=[('wide',48,24,0,0),('square',32,32,56,0),('tall',24,48,0,40)]
    for name,w,h,x,y in boards:
        items.extend([dict(id=name,transform=[1,0,0,1,x,y],content=dict(type='frame',frame=dict(role='artboard',width=w,height=h))),
            dict(id='copy-'+name,parent=name,content=dict(type='instance',instance=dict(source='shared')))])
    store(case,document('variants','vector',96,96,fonts=dict(face=font),assets=assets,items=items))
    val=lambda kind,value:dict(type=kind,value=value)
    definition=dict(bindings=[dict(key=k,item_id=i,property=p) for k,i,p in [('label','title','text'),('place','image','position'),('image','image','image')]],
        datasets=dict(wide=dict(values=dict(label=val('text',dict(text='AAA')),place=val('position',[36,16]),image=val('image','green'))),
            square=dict(parent='wide',values=dict(label=val('text',dict(text='AA')),place=val('position',[24,24]),image=val('image','orange'))),
            tall=dict(values=dict(label=val('text',dict(text='A')),place=val('position',[10,38]),image=val('image','green')))))
    apply(case,'define',0,[dict(op='variants_set',definition=definition)])
    base=source_snapshot(case,ref(1),'base');snapshots=[];outputs={}
    for index,(name,w,h,_,_) in enumerate(boards):
        revision=index+2
        apply(case,'select-'+name,revision-1,[dict(op='variant_select',dataset=name)])
        actual=source_snapshot(case,ref(revision),'source-'+name);snapshots.append(actual)
        count,x,y,color={'wide':(3,36,16,GREEN),'square':(2,24,24,ORANGE),'tall':(1,10,38,GREEN)}[name]
        output=dict(format='png',file_name=name+'.png',artboard_id=name)
        delivered=case.call('deliver-'+name,'document.publish',document=ref(revision),output=output)
        raw=(case.root/(name+'.png')).read_bytes();outputs[name]=sha(raw)
        expected=pixels(w,h,[(3+12*i,2,8,14,BLUE) for i in range(count)]+[(x,y,4,4,color)])
        case.check(name+'-pixels',lambda raw=raw,w=w,h=h,expected=expected:png_check(raw,w,h,expected),preview_step='deliver-'+name)
        require(delivered['sha256']==sha(raw),'Variant output identity changed')
    def bindings():
        require(base['fonts']['face']['sha256']==case.sources['original.ttf'] and
            base['fonts']['face']['license_sha256']==case.sources['font-license.txt'] and
            all(base['assets'][name]['sha256']==sha(canonical(2,2,bytes(color)*4)) for name,color in [('green',GREEN),('orange',ORANGE)]),
            'Variant font or image differs from its original source')
        for actual,(name,_,_,_,_) in zip(snapshots,boards,strict=True):
            wanted={'wide':('AAA',[36,16],'green'),'square':('AA',[24,24],'orange'),'tall':('A',[10,38],'green')}[name]
            require(actual['variants']['selected']==name and actual['variants']['definition']==base['variants']['definition'],
                'Variant definition/selection changed')
            require(actual['items'][1]['content']['frame']['text']==wanted[0] and actual['items'][2]['transform'][4:]==wanted[1]
                and actual['items'][2]['content']['asset_id']==wanted[2],'Variant resolved incorrect bindings')
            require(actual['fonts']==base['fonts'] and actual['assets']==base['assets'] and actual['items'][3:]==base['items'][3:],
                'A variant changed resources or shared placements')
    case.check('variant-bindings',bindings)
    apply(case,'restore-base',4,[dict(op='variant_select',dataset=None)])
    restored=source_snapshot(case,ref(5),'restored');wanted=copy.deepcopy(base);wanted['revision']=5
    case.check('base-preserved',lambda:require(restored==wanted,'Variant selection did not restore captured base'))
    case.check('outputs-preserved',lambda:require(all(sha((case.root/(name+'.png')).read_bytes())==digest for name,digest in outputs.items()),
        'A subsequent variant overwrote an earlier output'))
    verify_history(case)


def physical_print(case):
    rgb=linear_profile();cmyk=cmyk_profile()
    case.source('original-rgb.icc',rgb);case.source('original-cmyk.icc',cmyk)
    case.begin('Create an A4 portrait page at 72 ppi with bleed top=9, right=12, bottom=6, left=3 pixels. '
        'Use original-rgb.icc for RGB page blending. Preserve native ink declarations in PDF: '
        'a rectangle (20,30,100,80) using original-cmyk.icc and CMYK (.25,.5,.75,1), and a separate '
        'spot rectangle (140,30,80,80), spot ID spot, CMYK alternate (0,1,0,0) using that same '
        'source profile, profile-derived magenta preview and full tint. Review a focused preview, preflight and deliver print.pdf. '
        'Check physical boxes, exact embedded profiles and native ink operands; retain editable '
        'source, original profiles and all declared delivery limitations. The preview is not a press proof.')
    preset=case.call('preset','preset.create',id='print',version=1,preset=dict(type='print_page',paper='a4',
        orientation='portrait',resolution_ppi=72,color='display_rgb',bleed_px=dict(top=9,right=12,bottom=6,left=3)))
    doc=preset['document'];doc['output_profile']=embedded(rgb)
    doc['swatches']=dict(process=managed('cmyk',[.25,.5,.75,1],embedded(cmyk),untagged='reject'),
        spot=managed('cmyk',[0,1,0,0],embedded(cmyk),spot=True,untagged='reject'))
    for name,x,w in [('process',20,100),('spot',140,80)]:
        item=rectangle(name,x,30,w,80);item['content']['fill']=dict(swatch=name)
        item['parent']='page';doc['items'].append(item)
    saved=store(case,doc)
    view(case,'preview',saved,'print-preview',240,130,pixels(240,130,[(20,30,100,80,[0,0,0,255]),(140,30,80,80,[255,0,255,255])]),
        focus=dict(type='region',bounds=[0,0,240,130]))
    output=copy.deepcopy(preset['delivery']);output['file_name']='print.pdf';output['pdf_options']['color']='native_inks'
    ready=case.call('preflight','document.preflight',document=saved,output=output)
    require(ready['ready'] and not (case.root/'print.pdf').exists(),'Print preflight failed or wrote output: '+str(ready))
    delivered=case.call('deliver','document.publish',document=saved,output=output)
    raw=(case.root/'print.pdf').read_bytes();pdf=Pdf(raw)
    def boxes():
        require(len(pdf.pages)==1,'Print delivery changed page count')
        page=pdf.pages[0];unit=page.get('UserUnit',1)
        width,height=F(75600,127),F(106920,127)
        for key,expected in [('MediaBox',[0,0,width+15,height+15]),('TrimBox',[3,6,width+3,height+6]),('BleedBox',[0,0,width+15,height+15])]:
            require(all(abs(a*unit-float(e))<1e-9 for a,e in zip(page[key],expected,strict=True)),f'Incorrect physical {key}')
    case.check('physical-boxes',boxes)
    ink=painted(pdf)
    def profiles():
        space=pdf.pages[0]['Group']['CS']
        require(space[0]=='ICCBased' and pdf.streams[space[1]]==rgb,'Page blending profile differs')
        require(ink[0]['space'][0]=='ICCBased' and pdf.streams[ink[0]['space'][1]]==cmyk,'Process source profile differs')
        require(sum(v==rgb for v in pdf.streams.values())==1 and sum(v==cmyk for v in pdf.streams.values())==1,
            'Profile bytes were duplicated or replaced')
    case.check('profile-identities',profiles)
    def inks():
        require(len(ink)==2 and ink[0]['values']==[.25,.5,.75,1],'Process components changed')
        require(ink[1]['space'][:2]==['Separation','Inkbolt.spot'] and ink[1]['values']==[1],
            'Spot identity or tint changed')
        alternate=ink[1]['space'][2]
        require(alternate[0]=='ICCBased' and pdf.streams[alternate[1]]==cmyk,'Spot source profile changed')
        function=pdf.get(ink[1]['space'][3])
        require(function['C0']==[0,0,0,0] and function['C1']==[0,1,0,0],'Spot alternate changed')
    case.check('native-inks',inks)
    case.check('declared-losses',lambda:require(any('editable document model' in s for s in delivered['losses']) and
        any('not a print proof' in s for s in delivered['losses']) and sha(raw)==delivered['sha256']==ready['prepared_output']['sha256'],
        'Print losses or preflight/publication identity differ'))
    actual=source_snapshot(case,saved)
    case.check('editable-print-source',lambda:require(actual['swatches']==doc['swatches'] and actual['output_profile']==doc['output_profile']
        and len(actual['items'])==3,'Editable print colors/profiles or artwork changed'))
    verify_history(case)
