"""B10 no-engine native delivery: exact channel oracle plus pinned image admission."""
import subprocess

from benchmark_diagram import delivered
from benchmark_graphics import png_check
from benchmark_photo import WIDTH, HEIGHT, REGION, photographic_source, patched, preview_samples, judge_memory
from benchmark_runtime import require, strict_json
from benchmark_tasks import ENGINE_CHECKS
from workload_cases import check_tiff


def manifest():
    return dict(width=WIDTH,height=HEIGHT,image='edited.tiff',depth='u16',channels='rgba',
                encoding='encoded_srgb',transform=[1,0,0,1,0,0])


def admitted_manifest(case):
    value=strict_json(delivered(case,'editable.json'))
    require(value==manifest() and type(value['width']) is int and type(value['height']) is int and
            all(type(v) in (int,float) for v in value['transform']),
            'Expected one editable native layer with unchanged dimensions, interpretation and transform')
    require(len(delivered(case,'edited.tiff'))<=WIDTH*HEIGHT*8+1024*1024,
            'The native TIFF exceeds its bounded delivery size')


DECODE='''from PIL import Image
import json,sys
with Image.open(sys.argv[1]) as image:
    assert image.format=='TIFF' and image.size==(1920,1080) and image.n_frames==1 and image.mode=='RGBA'
    assert image.tag_v2[262]==2 and image.tag_v2[258]==(16,16,16,16)
    image.load()
    print(json.dumps(dict(width=image.width,height=image.height,channels='rgba',depth='u16')))
'''


def inspect_tiff(case,tools):
    result=subprocess.run([tools['python']['path'],'-I','-c',DECODE,str(case.root/'edited.tiff')],
                          cwd=case.root,timeout=30,capture_output=True)
    require(result.returncode==0 and strict_json(result.stdout)==dict(width=WIDTH,height=HEIGHT,channels='rgba',depth='u16'),
            'Pinned Pillow could not reopen the declared single-image RGBA16 TIFF')


def judge_photo(case,tools):
    expected,_=patched(photographic_source())
    def native():
        admitted_manifest(case)
        check_tiff(case.root/'edited.tiff',WIDTH,HEIGHT,expected)
        inspect_tiff(case,tools)
    case.check('edited-native-samples',native)
    case.check('photo-preview',lambda:png_check(delivered(case,'preview.png'),REGION['width'],REGION['height'],preview_samples(expected)))
    for name in ENGINE_CHECKS['B10']:
        case.not_applicable(name,'This check requires Inkbolt native import, proposal, immutable tile storage or saved session history.')
    judge_memory(case)
