"""Original variant and physical-delivery task adapters."""
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
