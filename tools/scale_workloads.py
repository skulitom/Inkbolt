"""Fixed scale-v2 workloads: complete large-image edits and independent delivery."""
import functools
import hashlib
import json
import struct
import subprocess
from pathlib import Path
import workload_cases as measure
import scale_oracles as oracle

SUITE = 'scale-v2'
CASES = ('jpeg-24mp', 'photo-50mp', 'print-a2', 'rgba8-8192')
DIMENSIONS = {'jpeg-24mp':(6000,4000), 'photo-50mp':(8192,6144),
              'print-a2':(4961,7016), 'rgba8-8192':(8192,8192)}
MAX_PEAK_COMMIT_BYTES = 512*1024*1024
PILLOW_VERSION = '10.3.0'


class Photo:
    """Full-depth texture, local defects and analytic edits, independent of Inkbolt."""
    def __init__(self,width,height):
        measure.require(width>=256 and height>=256, 'Photo fixture needs at least 256x256')
        self.width,self.height=width,height
        self.diameter=min(512,width//2,height//2)
        self.side=int(self.diameter*.7)
        self.bx,self.by=width//2-self.side//2,height//2-self.side//2
        self.px,self.py=width-35,height-35

    @functools.lru_cache(maxsize=128)
    def original(self,y):
        w=self.width
        rgb=hashlib.shake_256(b'Inkbolt scale-v2 original RGBA16 row '+str(y).encode()).digest(w*6)
        raw=bytearray(w*8)
        for c in range(6):raw[c::8]=rgb[c::6]
        raw[6::8]=raw[7::8]=bytes([255])*w
        # A known constant donor island and one damaged cell. Every legal donor
        # patch in the explicit 5x5 source has the same analytic repair value.
        if 24<=y<40:raw[24*8:40*8]=struct.pack('<4H',12003,22007,32011,65535)*16
        if y==34:struct.pack_into('<4H',raw,34*8,61003,4007,54011,65535)
        return bytes(raw)

    def coverage(self,x,y):
        w,h=self.width,self.height
        def base(xx,yy):
            if not (0<=xx<w and 0<=yy<h):return 0
            xe,ye=xx in (0,w-1),yy in (0,h-1)
            return 96 if xe and ye else 191 if xe else 128 if ye else 255
        return (sum(base(x+dx,y+dy)*(2-abs(dx))*(2-abs(dy))
                    for dy in (-1,0,1) for dx in (-1,0,1))+8)//16

    def row(self,y,stage):
        raw=bytearray(self.original(y));w=self.width
        if stage>=1 and self.py<=y<self.py+4:
            raw[self.px*8:(self.px+4)*8]=self.original(50+y-self.py)[50*8:54*8]
        if stage>=3 and self.by<=y<self.by+self.side:
            raw[self.bx*8:(self.bx+self.side)*8]=b'\xff'*(self.side*8)
        if stage>=4 and y==34:struct.pack_into('<4H',raw,34*8,12003,22007,32011,65535)
        if stage>=6:
            coverage=bytearray([self.coverage(2,y)])*w
            for x in (0,1,w-2,w-1):coverage[x]=self.coverage(x,y)
            raw[6::8]=raw[7::8]=coverage
        return bytes(raw)

    def actions(self):
        region=dict(x=self.px,y=self.py,width=4,height=4)
        return [
            [dict(op='retouch',id='pixels',options=dict(source_id='pixels',
                source_transform=[1,0,0,1,50-self.px,50-self.py],sampling='nearest',
                region=region,mode=dict(type='clone')))],
            [dict(op='selection_shape',boundary=dict(shape='rect',x=self.bx,y=self.by,width=self.side,height=self.side))],
            [dict(op='brush_stroke',id='pixels',stroke=dict(points=[dict(point=[self.width//2,self.height//2])],
                diameter=self.diameter,hardness=1,use_selection=True,mode=dict(type='paint',color=[255]*4)))],
            [dict(op='repair',id='pixels',options=dict(region=dict(x=34,y=34,width=1,height=1),
                action=dict(type='fill',fill=dict(source_id='pixels',patch_radius=1,max_context_rms=0,
                    donor_region=dict(x=25,y=25,width=5,height=5)))))],
            [dict(op='selection_shape',boundary=dict(shape='rect',x=.25,y=.5,width=self.width-.5,height=self.height-1)),
             dict(op='selection_refine',mode='feather',radius=1)],
            [dict(op='mask_from_selection',id='pixels',linked=False),dict(op='mask_apply',id='pixels')],
        ]


def call(case,step,command,**arguments):
    result=case.call(step,command,**arguments)
    measure.require(result is not None, 'Required step failed: '+step)
    return result


def photo(case,width,height):
    fixture=Photo(width,height);source=case.root/'original.tiff'
    oracle.write_tiff(source,width,height,fixture.original)
    case.sources[source.name]=oracle.file_hash(source)
    imported=call(case,'import','sample.import',source_path=source.name,id='photo',color_policy='assume_srgb',storage={})
    case.check('native-import',lambda:oracle.check_native(case.root,imported['document'],width,height,fixture.original))
    created=call(case,'save','session.create',session_id='photo',request_id='create',document=imported['document'],response_mode='full')
    snapshots=[created['document']]
    for stage,(name,operations) in enumerate(zip(('patch','selection','brush','repair','mask-selection','mask'),fixture.actions(),strict=True),1):
        action=dict(type='edit',operations=operations)
        review=call(case,name+'-review','session.dry_run',session_id='photo',request_id=name,expected_revision=stage-1,action=action)
        edited=call(case,name,'session.apply_proposal',proposal=review['proposal'],action=action,response_mode='full')
        case.check(name+'-review-bound',lambda:measure.require(edited['receipt']==review['predicted_receipt'], 'Review differs from commit'))
        snapshots.append(edited['document'])
        case.check(name+'-samples',lambda:oracle.check_native(case.root,edited['document'],width,height,lambda y:fixture.row(y,stage)))
    # TIFF export checks every output sample, separately from native block checks.
    options=dict(render_options=dict(evaluation='tiled'),image_options=dict(depth='u16',channels='rgba',compression='none'))
    case.publish('edited',dict(session_id='photo',revision=6),'tiff',lambda p:oracle.check_tiff(p,width,height,lambda y:fixture.row(y,6)),**options)
    revision=6
    for direction,stages in [('undo',range(5,-1,-1)),('redo',range(1,7))]:
        for stage in stages:
            step=f'{direction}-{stage}'
            state=call(case,step,'session.apply',session_id='photo',request_id=step,expected_revision=revision,
                       action=dict(type=direction),response_mode='full');revision+=1
            case.check(step,lambda:measure.require(state['document']==dict(snapshots[stage],revision=revision), 'History changed document state'))
    historical=call(case,'historical','document.validate',document=dict(session_id='photo',revision=0))
    case.check('historical',lambda:measure.require(historical==snapshots[0], 'Original snapshot changed'))
    case.check('immutable-source-blocks',lambda:oracle.check_native(case.root,historical,width,height,fixture.original))
    case.publish('restored',dict(session_id='photo',revision=revision),'tiff',lambda p:oracle.check_tiff(p,width,height,lambda y:fixture.row(y,6)),**options)
    verified=call(case,'verify','session.verify',session_id='photo')
    case.check('history-valid',lambda:measure.require(verified['valid'], 'Invalid saved history'))


def print_page(case,width,height):
    doc=measure.document('a2','vector',width,height,resolution_ppi=300,
        items=[measure.rectangle('ink',100,100,200,200)])
    def row(y):
        return bytes(width*4) if not 100<=y<300 else bytes(400)+measure.COLOR*200+bytes((width-300)*4)
    def pdf(path):
        result=measure.Pdf(path.read_bytes());paths=result.paths()
        measure.require(len(result.pages)==1 and all(abs(a-b)<1e-8 for a,b in
            zip(result.pages[0]['MediaBox'],[0,0,width*.24,height*.24],strict=True)), 'Wrong A2 page extent')
        measure.require(len(paths)==1 and paths[0]['path']==[('m',[[24,24]]),('l',[[72,24]]),('l',[[72,72]]),('l',[[24,72]]),('h',[])], 'Wrong PDF artwork')
        measure.require(all(abs(a-b)<1e-8 for a,b in zip(paths[0]['color'],[20/255,80/255,150/255],strict=True)), 'Wrong PDF color')
    case.publish('page',doc,'pdf',pdf)
    case.publish('preview',doc,'png',lambda p:oracle.check_png(p,width,height,row))


def rgba8(case,width,height):
    palette=(bytes([23,81,147,255]),bytes([150,80,20,128]),bytes([41,133,79,255]),bytes(4))
    items=[]
    for i in range(3):
        x,y=(i%2)*(width//2),(i//2)*(height//2)
        items.append(measure.rectangle('quadrant-'+str(i),x,y,width//2,height//2,palette[i]))
    doc=measure.document('rgba8','vector',width,height,items=items)
    def row(y):
        at=0 if y<height//2 else 2
        return palette[at]*(width//2)+palette[at+1]*(width//2)
    case.publish('image',doc,'png',lambda p:oracle.check_png(p,width,height,row))


def jpeg(case,width,height,python):
    helper=Path(__file__).with_name('scale_jpeg.py')
    args=[str(python),'-I',str(helper),str(case.root),str(width),str(height)]
    result=subprocess.run(args,capture_output=True,timeout=600)
    measure.save(case.root/'jpeg-generator.stdout',result.stdout)
    measure.save(case.root/'jpeg-generator.stderr',result.stderr)
    measure.require(result.returncode==0 and not result.stderr, 'Pinned JPEG generator failed; see retained logs')
    identity=json.loads(result.stdout)
    measure.require(identity['pillow_version']==PILLOW_VERSION and identity['dimensions']==[width,height], 'Wrong JPEG fixture tools or dimensions')
    for progressive in (False,True):
        name='progressive' if progressive else 'baseline'
        source=case.root/(name+'.jpg');raw=case.root/(name+'.rgba')
        case.sources[source.name]=oracle.file_hash(source);case.sources[raw.name]=oracle.file_hash(raw)
        imported=call(case,'import-'+name,'sample.import',source_path=source.name,id=name,storage={},color_policy='assume_srgb',orientation='apply')
        with raw.open('rb') as stream:
            def row(y):
                stream.seek(y*width*4);return stream.read(width*4)
            case.check(name+'-samples',lambda:oracle.check_native(case.root,imported['document'],width,height,row,depth='u8',tolerance=3))
    return identity


def run(case, *, dimensions=None, jpeg_python=None):
    width,height=dimensions or DIMENSIONS[case.name]
    extra={}
    try:
        if case.name=='jpeg-24mp':extra['jpeg_tools']=jpeg(case,width,height,jpeg_python)
        elif case.name=='photo-50mp':photo(case,width,height)
        elif case.name=='print-a2':print_page(case,width,height)
        elif case.name=='rgba8-8192':rgba8(case,width,height)
        else:raise ValueError('Unknown scale-v2 case')
    except Exception as error:
        case.checks.append(dict(name='harness',status='fail',error=f'{type(error).__name__}: {error}'))
    # Workflow correctness and D7 memory acceptance are distinct. Unavailable
    # commit counters never become a pass via Linux resident measurements.
    memory=[c['memory'] for c in case.calls if 'memory' in c]
    complete=bool(memory) and all(m.get('available') is True for m in memory)
    budget=('passed' if max(m['peak_commit_bytes'] for m in memory)<=MAX_PEAK_COMMIT_BYTES else 'failed') if complete else 'unavailable'
    if budget=='failed':case.checks.append(dict(name='commit-budget',status='fail',error='Exceeded the fixed 512 MiB ceiling'))
    result=case.finish()
    result.update(dimensions=[width,height],fixed_fixture=(width,height)==DIMENSIONS[case.name],
        commit_budget=dict(status=budget,maximum_bytes=MAX_PEAK_COMMIT_BYTES),**extra)
    measure.save_json(case.root/'scale-case.json',result)
    return result
