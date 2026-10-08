"""Original analytic ICC lookup fixtures; no device profile or third-party asset."""
import itertools
import struct
from test_profiles_cli import linear_profile
from test_sample_profiles_cli import tags_of, repack


def fixed(x):
    return struct.pack('>i', round(x * 65536))


def separation(q, shift=0):
    return [.1 + .2*q[0] + shift, .15 + .3*q[1] + shift,
            .05 + .4*q[2] + shift, .2 + .1*q[0] + .2*q[1] + .1*q[2] + shift]


def lookup(n, m, fn, modern=False, grid=2, forward=False):
    values = [round(max(0, min(1, v))*65535)
              for point in itertools.product((i/(grid-1) for i in range(grid)), repeat=n) for v in fn(point)]
    packed = struct.pack('>' + str(len(values)) + 'H', *values)
    if not modern:
        return (b'mft2' + bytes(4) + bytes([n, m, grid, 0])
                + b''.join(fixed(v) for v in (1, 0, 0, 0, 1, 0, 0, 0, 1))
                + struct.pack('>HH', 2, 2) + struct.pack('>2H', 0, 65535)*n
                + packed + struct.pack('>2H', 0, 65535)*m)
    # Public ICC v4 BToA stages: input B curves, CLUT, output A curves.
    curve = b'curv' + bytes(4) + struct.pack('>I', 0)
    b_curves = curve*(m if forward else n)
    clut = bytes([grid]*n) + bytes(16-n) + bytes([2, 0, 0, 0]) + packed
    clut += bytes(-len(clut) % 4)
    return ((b'mAB ' if forward else b'mBA ') + bytes(4) + bytes([n, m, 0, 0])
            + struct.pack('>5I', 32, 0, 0, 32+len(b_curves), 32+len(b_curves)+len(clut))
            + b_curves + clut + curve*(n if forward else m))


def proof_profile(pcs='XYZ ', modern=False, white=(.9642, 1, .8249), version=4, grid=2):
    """Affine AToB chart makes independent interpolation algorithms comparable."""
    original=cmyk_profile(pcs=pcs,modern=modern,white=white,version=version,grid=grid)
    tags=tags_of(original)
    for j in (0,1,2):
        if pcs=='XYZ ':
            model=lambda q:[.40-.10*q[0]-.05*q[1]-.10*q[3], .42-.05*q[0]-.10*q[1]-.10*q[3], .35-.10*q[2]-.10*q[3]]
        else:
            model=lambda q:[.85-.05*q[0]-.05*q[1]-.10*q[3], .5+.10*q[1]-.10*q[0], .5+.10*q[2]-.10*q[1]]
        tags[b'A2B'+str(j).encode()]=lookup(4,3,model,modern=modern,grid=grid,forward=True)
    return repack(original[:128],tags)


def cmyk_profile(pcs='XYZ ', modern=False, intents=False, white=(.9642, 1, .8249), version=4, grid=2):
    original = linear_profile()
    header = bytearray(original[:128])
    header[12:24] = b'prtrCMYK' + pcs.encode('ascii')
    tags = {k:v for k,v in tags_of(original).items() if k in (b'desc', b'cprt', b'wtpt')}
    tags[b'wtpt'] = b'XYZ ' + bytes(4) + b''.join(fixed(v) for v in white)
    if version == 2:
        assert not modern
        header[8:12] = b'\x02\x40\0\0'
        label=b'Inkbolt original CMYK fixture\0'
        tags[b'desc']=b'desc'+bytes(4)+struct.pack('>I',len(label))+label+bytes(4+4+2+1+67)
        tags[b'cprt']=b'text'+bytes(4)+b'Original synthetic fixture; MIT\0'
    for j in (0, 1, 2):
        shift = (.04*j) if intents else 0
        tags[b'B2A'+str(j).encode()] = lookup(3, 4, lambda q:separation(q, shift), modern, grid)
        # A smooth original observation model, deliberately not an inverse press model.
        model = (lambda q:[.4821*(1-q[0])*(1-q[3]), .5*(1-q[1])*(1-q[3]), .41245*(1-q[2])*(1-q[3])]) if pcs == 'XYZ ' else (lambda q:[(1-q[3])*.8, .5+.1*(q[1]-q[0]), .5+.1*(q[2]-q[1])])
        tags[b'A2B'+str(j).encode()] = lookup(4, 3, model, grid=grid)
    return repack(header, tags)


def neutral_print_profile():
    """An original mutually consistent neutral printing model: L*=100*(1-K)."""
    original=cmyk_profile(pcs='Lab ',modern=True)
    tags=tags_of(original)
    for j in (0,1,2):
        tags[b'B2A'+str(j).encode()]=lookup(3,4,lambda q:[0,0,0,1-q[0]],modern=True)
        tags[b'A2B'+str(j).encode()]=lookup(4,3,lambda q:[(1-q[3])*65280/65535,32768/65535,32768/65535])
    return repack(original[:128],tags)
