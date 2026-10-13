"""B14 bounded editable print recipe, independent PDF geometry and ICC preview."""
import subprocess

from benchmark_diagram import delivered
from benchmark_baseline_mixed import same_controls
from benchmark_graphics import png_check
from benchmark_print import artifact_checks,declared_losses,expected_picture
from benchmark_runtime import require,strict_json
from pdf_reader import multiply,point


def manifest(sources):
    return dict(paper_mm=[210,297],resolution_ppi=72,bleed_px=[9,12,6,3],
        page_profile=dict(file='original-rgb.icc',sha256=sources['original-rgb.icc']),
        ink_profile=dict(file='original-cmyk.icc',sha256=sources['original-cmyk.icc']),
        intent='relative_colorimetric',black_point_compensation=False,
        items=[dict(bounds=[20,30,100,80],kind='process',components=[.25,.5,.75,1]),
               dict(bounds=[140,30,80,80],kind='spot',id='spot',alternate=[0,1,0,0],tint=1)])


def admitted_manifest(case):
    raw=delivered(case,'editable.json');require(len(raw)<=8192,'Print recipe exceeds its bounded contract')
    value=strict_json(raw)
    require(same_controls(value,manifest(case.sources)),'Print paper, bleed, native inks or source profile identities changed')
    return value


def page_geometry(pdf):
    """Interpret the bounded native vector content; never treat a PNG as PDF proof."""
    page=pdf.pages[0];height=page['MediaBox'][3];unit=page.get('UserUnit',1);paths=[]
    require(set(pdf.catalog)=={'Type','Pages'} and set(page)<={'Type','Parent','MediaBox','TrimBox','BleedBox','CropBox',
        'Resources','Contents','Group','UserUnit','Rotate'} and page.get('Rotate',0)==0 and
        page.get('CropBox',page['MediaBox'])==page['MediaBox'],'Unsupported print page controls or crop')
    group=page['Group']
    require(set(group)<={'Type','S','CS','I','K'} and group.get('S')=='Transparency' and group.get('I') is True and
        group.get('K',False) is False,'Unsupported print page blending group')
    def visit(data,resources,matrix):
        args=[];path=[];stack=[];state={}
        for token in data.split():
            if token.startswith(b'/'):args.append(token[1:].decode());continue
            try:args.append(float(token));continue
            except ValueError:pass
            if token==b'q':stack.append((matrix[:],state.copy()))
            elif token==b'Q':matrix,state=stack.pop()
            elif token==b'cm':
                require(len(args)==6,'Invalid print transform');matrix=multiply(matrix,args)
            elif token==b'gs':state=pdf.get(resources['ExtGState'][args[0]])
            elif token in (b'm',b'l'):
                require(len(args)==2,'Invalid print path');p=point(matrix,args);path.append((token,[p[0]*unit,(height-p[1])*unit]))
            elif token==b'h':path.append((token,[]))
            elif token==b'n':path=[]
            elif token==b'f':
                require(set(state)<={'Type','ca','CA','BM','SMask','op','OP','OPM','RI','UseBlackPtComp'} and
                    state.get('ca',1)==1 and state.get('BM','Normal')=='Normal' and state.get('SMask','None')=='None' and
                    not state.get('op',False) and state.get('RI','RelativeColorimetric')=='RelativeColorimetric' and
                    state.get('UseBlackPtComp')=='OFF','Print paint opacity, compositing or conversion policy changed')
                paths.append(path);path=[]
            else:require(token in (b'cs',b'sc',b'scn'),'Unsupported print geometry operator')
            args=[]
        require(not args and not stack and not path,'Incomplete print content')
    visit(pdf.streams[page['Contents']],page['Resources'],[1,0,0,1,0,0])
    expected=[]
    for x,w in ((23,100),(143,80)):
        expected.append([(b'm',[x,39]),(b'l',[x+w,39]),(b'l',[x+w,119]),(b'l',[x,119]),(b'h',[])])
    require(len(paths)==2,'Expected exactly two native rectangle paints')
    for actual,wanted in zip(paths,expected,strict=True):
        require(len(actual)==len(wanted) and all(op==eop and len(p)==len(ep) and all(abs(a-b)<1e-9 for a,b in zip(p,ep,strict=True))
            for (op,p),(eop,ep) in zip(actual,wanted,strict=True)),'Delivered PDF artwork geometry differs')


COMPOSE='''from PIL import Image,ImageCms
from pathlib import Path
import json,sys
root=Path(sys.argv[1]);scene=json.loads((root/'editable.json').read_bytes())
profile=ImageCms.ImageCmsProfile(str(root/scene['ink_profile']['file']))
transform=ImageCms.buildTransformFromOpenProfiles(profile,ImageCms.createProfile('sRGB'),'CMYK','RGB',renderingIntent=1,flags=0)
canvas=Image.new('RGBA',(240,130))
for item in scene['items']:
    values=item['components'] if item['kind']=='process' else item['alternate']
    sample=Image.new('CMYK',(1,1),tuple(round(v*255) for v in values))
    color=ImageCms.applyTransform(sample,transform).getpixel((0,0))+(255,)
    x,y,w,h=item['bounds'];canvas.paste(color,(x,y,x+w,y+h))
print(canvas.tobytes().hex())
'''


def render_preview(case,tools):
    result=subprocess.run([tools['python']['path'],'-I','-c',COMPOSE,str(case.root)],cwd=case.root,timeout=30,capture_output=True)
    require(result.returncode==0,'Pinned Pillow could not render the admitted ICC print preview')
    pixels=bytes.fromhex(result.stdout.decode('ascii').strip())
    require(len(pixels)==240*130*4,'Print preview dimensions changed');return pixels


def judge_print(case,tools):
    admitted_manifest(case)
    raw=delivered(case,'print.pdf');rgb=delivered(case,'original-rgb.icc');cmyk=delivered(case,'original-cmyk.icc')
    # Native declarations alone do not prove that the delivered page paints the
    # requested geometry. Keep this assertion within the existing ink criterion.
    artifact_checks(case,(raw,),rgb,cmyk,native_geometry=page_geometry)
    rendered=render_preview(case,tools)
    def picture():
        require(rendered==expected_picture(),'Fresh ICC preview differs from the original oracle')
        png_check(delivered(case,'preview.png'),240,130,expected_picture())
    case.check('print-preview',picture)
    case.check('declared-losses',lambda:declared_losses(strict_json(delivered(case,'delivery.json')),raw))
    case.not_applicable('editable-print-source','This check reopens an Inkbolt snapshot; the baseline retains the admitted editable print recipe and original profiles.')
    case.not_applicable('history-valid','Inkbolt saved history is unavailable to the no-engine arm.')
