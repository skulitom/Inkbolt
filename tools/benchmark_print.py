"""B14 original physical-print solve and independent retained-artifact checks."""
import base64
import copy
from fractions import Fraction as F
from pathlib import Path

from benchmark_diagram import delivered
from benchmark_graphics import rectangle,pixels,png_check,store,source_snapshot
from benchmark_large_layout import retained_session_store
from benchmark_runtime import require,safe_name,strict_json
from benchmark_stores import retained_publication_store
from cmyk_fixtures import cmyk_profile
from test_profiles_cli import embedded,linear_profile
from test_swatch_profiles_cli import managed
from test_ink_delivery_cli import painted
from pdf_reader import Pdf as BoundedPdf
from workload_cases import save,save_json,sha

PROMPT=Path(__file__).with_name('benchmark_prompts')/'B14.md'
PREVIEW_FILES={'print-preview':'preview.png'}
PRESET=dict(type='print_page',paper='a4',orientation='portrait',resolution_ppi=72,
            color='display_rgb',bleed_px=dict(top=9,right=12,bottom=6,left=3))


class Pdf(BoundedPdf):
    def get(self,value):
        # Resource dictionaries may contain direct color-space arrays or
        # graphics-state dictionaries as well as indirect object references.
        return value if isinstance(value,(list,dict)) else super().get(value)


def fixture(case):
    case.source('original-rgb.icc',linear_profile());case.source('original-cmyk.icc',cmyk_profile())


def source_document(preset,rgb,cmyk,names=None):
    names=names or dict(board='page',process='process',items=['process','spot'])
    doc=copy.deepcopy(preset['document']);doc['items'][0]['id']=names['board'];doc['output_profile']=embedded(rgb)
    doc['swatches']={names['process']:managed('cmyk',[.25,.5,.75,1],embedded(cmyk),untagged='reject'),
        'spot':managed('cmyk',[0,1,0,0],embedded(cmyk),spot=True,untagged='reject')}
    for index,(swatch,x,w) in enumerate([(names['process'],20,100),('spot',140,80)]):
        item=rectangle(names['items'][index],x,30,w,80);item['content']['fill']=dict(swatch=swatch)
        item['parent']=names['board'];doc['items'].append(item)
    return doc


def output_settings(preset,board):
    output=copy.deepcopy(preset['delivery']);output['file_name']='print.pdf'
    output['pdf_options']['color']='native_inks';output['pdf_options']['artboards']['ids']=[board]
    return output


def expected_picture():
    return pixels(240,130,[(20,30,100,80,[0,0,0,255]),(140,30,80,80,[255,0,255,255])])


def solve(case):
    preset=case.call('preset','preset.create',id='print',version=1,preset=PRESET)
    doc=source_document(preset,delivered(case,'original-rgb.icc'),delivered(case,'original-cmyk.icc'));saved=store(case,doc)
    preview=case.call('preview','document.preview',document=saved,options=dict(focus=dict(type='region',bounds=[0,0,240,130])),preview=True)
    save(case.root/'preview.png',base64.b64decode(preview['artifact']['data'],validate=True))
    output=output_settings(preset,doc['items'][0]['id'])
    ready=case.call('preflight','document.preflight',document=saved,output=output)
    require(ready['ready'] and not (case.root/'print.pdf').exists(),'Print preflight failed or wrote output')
    result=case.call('deliver','document.publish',document=saved,output=output,receipt=dict(request_id='print-delivery'))
    require(result['sha256']==ready['prepared_output']['sha256']==sha(delivered(case,'print.pdf')),'Preflight/publication identity differs')
    source_snapshot(case,saved);case.call('verify-history','session.verify',session_id=saved['session_id'])
    save_json(case.root/'delivery.json',dict(file='print.pdf',sha256=result['sha256'],losses=result['losses']))
    save_json(case.root/'session.json',dict(session_id=saved['session_id'],revision=saved['revision'],publication='print-delivery'))


def physical_boxes(pdf):
    require(len(pdf.pages)==1,'Print delivery changed page count')
    page=pdf.pages[0];unit=page.get('UserUnit',1);width,height=F(75600,127),F(106920,127)
    for key,expected in [('MediaBox',[0,0,width+15,height+15]),('TrimBox',[3,6,width+3,height+6]),('BleedBox',[0,0,width+15,height+15])]:
        require(all(abs(a*unit-float(e))<1e-9 for a,e in zip(page[key],expected,strict=True)),f'Incorrect physical {key}')


def profile_identities(pdf,rgb,cmyk):
    ink=painted(pdf);space=pdf.pages[0]['Group']['CS']
    require(space[0]=='ICCBased' and pdf.streams[space[1]]==rgb,'Page blending profile differs')
    require(ink[0]['space'][0]=='ICCBased' and pdf.streams[ink[0]['space'][1]]==cmyk,'Process source profile differs')
    for ref,n,alternate in ((space[1],3,'DeviceRGB'),(ink[0]['space'][1],4,'DeviceCMYK')):
        profile=pdf.get(ref)
        require(profile['N']==n and profile.get('Alternate',alternate)==alternate and profile.get('Range',[0,1]*n)==[0,1]*n,
            'Embedded profile channel count, fallback or component range changed')
    require(sum(v==rgb for v in pdf.streams.values())==1 and sum(v==cmyk for v in pdf.streams.values())==1,
        'Profile bytes were duplicated or replaced')


def native_inks(pdf,cmyk):
    ink=painted(pdf)
    require(len(ink)==2 and ink[0]['values']==[.25,.5,.75,1],'Process components changed')
    require(ink[1]['space'][:2]==['Separation','Inkbolt.spot'] and ink[1]['values']==[1],'Spot identity or tint changed')
    alternate=ink[1]['space'][2]
    require(alternate[0]=='ICCBased' and pdf.streams[alternate[1]]==cmyk,'Spot source profile changed')
    function=pdf.get(ink[1]['space'][3])
    require(function.get('FunctionType')==2 and function.get('Domain')==[0,1] and function.get('N')==1 and
        function.get('Range',[0,1]*4)==[0,1]*4 and function['C0']==[0,0,0,0] and function['C1']==[0,1,0,0],'Spot alternate changed')


def declared_losses(value,raw):
    require(isinstance(value,dict) and set(value)=={'file','sha256','losses'} and value['file']=='print.pdf' and
        value['sha256']==sha(raw) and isinstance(value['losses'],list) and all(isinstance(v,str) for v in value['losses']) and
        any('editable document model' in s for s in value['losses']) and any('not a print proof' in s for s in value['losses']),
        'Print delivery identity or declared limitations differ')


def artifact_checks(case,raws,rgb,cmyk,native_geometry=None):
    require(all(len(raw)<=1024*1024 for raw in raws),'Print PDF exceeds the bounded delivery contract')
    pdfs=[Pdf(raw) for raw in raws]
    def inks(pdf):
        native_inks(pdf,cmyk)
        if native_geometry:native_geometry(pdf)
    for name,fn in [('physical-boxes',physical_boxes),('profile-identities',lambda pdf:profile_identities(pdf,rgb,cmyk)),
                    ('native-inks',inks)]:
        case.check(name,lambda fn=fn:[fn(pdf) for pdf in pdfs])


def judge(case):
    rgb=delivered(case,'original-rgb.icc');cmyk=delivered(case,'original-cmyk.icc');raw=delivered(case,'print.pdf')
    source=delivered(case,'editable.json');actual=strict_json(source)
    reopened=case.call('judge-reopen','document.validate',document=dict(file_path='editable.json',sha256=sha(source)))
    preset=case.call('judge-preset','preset.create',id=actual['id'],version=1,preset=PRESET)
    require(len(actual['items'])==3,'Expected a print page and two editable rectangles')
    names=dict(board=actual['items'][0]['id'],process=actual['items'][1]['content']['fill']['swatch'],items=[i['id'] for i in actual['items'][1:]])
    expected=source_document(preset,rgb,cmyk,names);expected['revision']=actual['revision']
    expected['items'][0]['name']=actual['items'][0].get('name')
    normalized=case.call('judge-template','document.validate',document=expected)
    require(case.check('editable-print-source',lambda:require(actual==reopened==normalized,
        'Physical canvas, complete artwork, native swatches or embedded profiles changed')),'Print source was not admitted')
    preview=case.call('judge-preview','document.preview',document=reopened,options=dict(focus=dict(type='region',bounds=[0,0,240,130])),preview=True)
    def picture():
        for data in (delivered(case,'preview.png'),base64.b64decode(preview['artifact']['data'],validate=True)):
            png_check(data,240,130,expected_picture())
    case.check('print-preview',picture)
    directory=getattr(case,'judge_root',case.root);output=output_settings(preset,names['board'])
    output.update(file_name='judge-print.pdf',output_root=str(directory.resolve()))
    require(not (directory/'judge-print.pdf').exists(),'Print judge output must be new')
    ready=case.call('judge-preflight','document.preflight',document=reopened,output=output,judge_workspace=directory)
    require(ready['ready'] and not (directory/'judge-print.pdf').exists(),'Fresh preflight failed or wrote output')
    fresh_result=case.call('judge-deliver','document.publish',document=reopened,output=output,judge_workspace=directory)
    fresh=(directory/'judge-print.pdf').read_bytes();artifact_checks(case,(raw,fresh),rgb,cmyk)
    locator=strict_json(delivered(case,'session.json'))
    require(set(locator)=={'session_id','revision','publication'} and type(locator['revision']) is int and locator['revision']>=0,'Invalid print session locator')
    for key in ('session_id','publication'):safe_name(locator[key])
    receipt=case.call('judge-receipt','publication.receipt',request_id=locator['publication'],
        receipt_root=retained_publication_store(case,locator['publication']))
    def losses():
        value=strict_json(delivered(case,'delivery.json'));declared_losses(value,raw);result=receipt['result']
        require(receipt['state']=='complete' and result['sha256']==value['sha256']==sha(fresh)==fresh_result['sha256']==ready['prepared_output']['sha256'] and
            result['losses']==value['losses']==fresh_result['losses'] and result['format']=='pdf' and result['document_id']==actual['id'] and
            result['revision']==actual['revision'],'Delivered PDF or limitations differ from fresh preflight or the completed receipt')
    case.check('declared-losses',losses)
    session_root=retained_session_store(case,locator['session_id'])
    saved=case.call('judge-saved','document.validate',document=dict(session_root=session_root,session_id=locator['session_id'],revision=locator['revision']))
    history=case.call('judge-history','session.verify',session_root=session_root,session_id=locator['session_id'])
    case.check('history-valid',lambda:require(saved==actual and history['valid'] and history['revision']==locator['revision']==actual['revision'],
        'Saved source and verified current history differ'))


def physical_print(case):
    fixture(case);case.begin(PROMPT.read_text(encoding='utf-8'));solve(case);case.begin_judging();judge(case)
    if any(c['name']=='print-preview' and c['status']=='pass' for c in case.checks):case.verified_preview(delivered(case,'preview.png'))
