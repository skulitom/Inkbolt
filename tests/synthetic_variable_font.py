"""Original two-axis geometric font and public OpenType variation-table fixtures."""
import struct
from synthetic_unicode_font import unicode_font, sfnt, coverage, layout_table, ADVANCES
from synthetic_font import pack


def tables(data):
    result={}
    for i in range(struct.unpack_from('>H',data,4)[0]):
        tag,_,offset,length=struct.unpack_from('>4sIII',data,12+i*16)
        result[tag]=data[offset:offset+length]
    head=bytearray(result[b'head']);head[8:12]=bytes(4);result[b'head']=bytes(head)
    return result


def variation_store(rows):
    regions=[[(0,16384,16384),(0,0,0)],[(-16384,-16384,0),(0,0,0)],
        [(0,0,0),(0,16384,16384)],[(0,0,0),(-16384,-16384,0)]]
    region=pack('HH',2,4)+b''.join(pack('hhh',*axis) for r in regions for axis in r)
    item=pack('HHHHHHH',len(rows),4,4,0,1,2,3)+b''.join(pack('hhhh',*r) for r in rows)
    return pack('HIHI',1,12,1,12+len(region))+region+item


def variable_font(coverage_set='all', *, avar=False, hvar=False, metrics=False):
    data=tables(unicode_font(coverage_set))
    os2=bytearray(96)
    struct.pack_into('>HHHH',os2,0,4,600,400,5)
    os2[58:62]=b'INKB'
    struct.pack_into('>HHHhhhHH',os2,62,0xC0,32,0xFFFF,1000,-200,0,1000,200)
    struct.pack_into('>hhHHH',os2,86,500,700,0,32,2)
    data[b'OS/2']=bytes(os2)
    names={1:'Inkbolt Geometry',2:'Regular',4:'Inkbolt Geometry Variable',
        6:'InkboltGeometryVariable',256:'Weight',257:'Width'}
    records=b'';strings=b''
    for id,value in names.items():
        value=value.encode('utf-16-be')
        records+=pack('HHHHHH',3,1,0x409,id,len(value),len(strings));strings+=value
    data[b'name']=pack('HHH',0,len(names),6+12*len(names))+records+strings
    data[b'fvar']=pack('HHHHHHHH',1,0,16,2,2,20,0,12)+b''.join(
        tag+pack('iiiHH',minimum*65536,default*65536,maximum*65536,0,256+i)
        for i,(tag,minimum,default,maximum) in enumerate([(b'wght',100,400,900),(b'wdth',50,100,200)]))
    tuples=[(16384,0,200,100),(-16384,0,-20,-50),(0,16384,400,0),(0,-16384,-30,0)]
    records=b'';offsets=[0]
    for gid in range(len(ADVANCES)):
        if gid not in (0,1,6):
            headers=b'';payload=b''
            for weight,width,dx,dy in tuples:
                # Explicit all-points marker; four outline and four phantom points.
                xs=[0,0,dx,dx,0,dx,0,0];ys=[0,dy,dy,0,0,0,0,0]
                delta=b'\0'+bytes([0x47])+pack('h'*8,*xs)+bytes([0x47])+pack('h'*8,*ys)
                headers+=pack('HHhh',len(delta),0xA000,weight,width);payload+=delta
            records+=pack('HH',4,4+len(headers))+headers+payload
        offsets.append(len(records))
    data[b'gvar']=pack('HHHHIHHI',1,0,2,0,0,len(ADVANCES),1,20+4*len(offsets))+pack('I'*len(offsets),*offsets)+records
    if avar:
        # Weight's upper midpoint shifts to .75; width stays linear.
        maps=[[(-16384,-16384),(0,0),(8192,12288),(16384,16384)],[(-16384,-16384),(0,0),(16384,16384)]]
        data[b'avar']=pack('HHHH',1,0,0,2)+b''.join(pack('H',len(m))+b''.join(pack('hh',*p) for p in m) for m in maps)
    if hvar:
        rows=[[0]*4 if gid in (0,1,6) else [200,-20,400,-30] for gid in range(len(ADVANCES))]
        data[b'HVAR']=pack('HHIIII',1,0,20,0,0,0)+variation_store(rows)
    if metrics:
        entries=[(b'hasc',[200,-100,0,0]),(b'hdsc',[-100,50,0,0]),(b'hlgp',[50,-25,0,0])]
        data[b'MVAR']=pack('HHHHHH',1,0,0,8,len(entries),12+8*len(entries))+b''.join(
            tag+pack('HH',0,i) for i,(tag,_) in enumerate(entries))+variation_store([r for _,r in entries])
    # Include optional stylistic substitution and a numeric alternate selector.
    lookups=[]
    for delta in [4,2,1]:
        lookups.append((1,pack('HHHHH',2,10,2,7+delta,12+delta)+coverage([7,12])))
    lookups.append((4,pack('HHHH',1,8,1,14)+coverage([24])+pack('HHHHH',1,4,26,2,25)))
    lookups.append((1,pack('HHHHH',2,10,2,10,15)+coverage([7,12])))
    lookups.append((1,pack('HHHH',2,8,1,3)+coverage([2])))
    lookups.append((3,pack('HHHH',1,8,1,14)+coverage([2])+pack('HHH',2,3,5)))
    lookups.append((1,pack('HHHH',2,8,1,3)+coverage([2])))
    features={tag:[i] for i,tag in enumerate([b'fina',b'init',b'isol',b'liga',b'medi',b'locl',b'salt',b'ss01'])}
    data[b'GSUB']=layout_table({b'arab':[0,1,2,5],b'dev2':[],b'latn':[3,6,7]},features,lookups,
        languages={b'latn':{b'TRK ':[3,4,6,7]}})
    data[b'kern']=pack('HHHHHHHHHHHh',0,1,0,20,1,1,6,0,0,2,3,-100)
    return sfnt(data)
