"""Original scripted task adapters with separate geometry/pixel/source oracles."""
import base64
import json

from benchmark_runtime import require
from workload_cases import document, rectangle, save, sha
from test_editing_cli import png_pixels


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


def two_items():
    return document('revisions','vector',32,16,items=[rectangle('target',2,4,8,8,BLUE),rectangle('other',22,4,8,8,GREEN)])
