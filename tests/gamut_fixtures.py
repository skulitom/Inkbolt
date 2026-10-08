"""Original bounded ICC gamut tables; public encodings, synthetic functions."""
import itertools
import struct
from cmyk_fixtures import fixed, proof_profile, lookup
from test_sample_profiles_cli import tags_of, repack


IDENTITY = b'curv' + bytes(8)


def curve(values=None, params=None):
    if params is not None:
        kind = {1: 0, 3: 1, 4: 2, 5: 3, 7: 4}[len(params)]
        raw = b'para' + bytes(4) + struct.pack('>HH', kind, 0) + b''.join(fixed(x) for x in params)
    elif values is None:
        return IDENTITY
    else:
        raw = b'curv' + bytes(4) + struct.pack('>I', len(values)) + struct.pack('>' + str(len(values)) + 'H', *values)
    return raw + bytes(-len(raw) % 4)


def modern_table(fn, grid=(2, 2, 2), precision=2, inputs=None, matrix=None, middle=None, output=None):
    values = [round(max(0, min(1, fn(q))) * (255 if precision == 1 else 65535))
              for q in itertools.product(*(tuple(i/(n-1) for i in range(n)) for n in grid))]
    packed = bytes(values) if precision == 1 else struct.pack('>' + str(len(values)) + 'H', *values)
    clut = bytes(grid) + bytes(13) + bytes([precision, 0, 0, 0]) + packed
    clut += bytes(-len(clut) % 4)
    parts = [b''.join(inputs or [IDENTITY]*3),
             b''.join(fixed(x) for x in matrix) if matrix else b'',
             b''.join(middle or [IDENTITY]*3) if matrix else b'', clut, output or IDENTITY]
    offsets = []; at = 32
    for part in parts:
        offsets.append(at if part else 0); at += len(part)
    return b'mBA ' + bytes(4) + bytes([3, 1, 0, 0]) + struct.pack('>5I', *offsets) + b''.join(parts)


def eight_table(fn, grid=3):
    return (b'mft1' + bytes(4) + bytes([3, 1, grid, 0])
            + b''.join(fixed(v) for v in (1,0,0,0,1,0,0,0,1))
            + bytes(range(256))*3
            + bytes(round(max(0,min(1,fn(q)))*255) for q in itertools.product(tuple(i/(grid-1) for i in range(grid)),repeat=3))
            + bytes(range(256)))


def profile(table=None, pcs='Lab ', version=4, modern=False, white=(.9642,1,.8249)):
    base = proof_profile(pcs=pcs, version=version, modern=modern, white=white)
    tags = tags_of(base)
    tags[b'gamt'] = table or lookup(3,1,lambda q:[max(0,q[0]-.5)],modern=modern,grid=3)
    return repack(base[:128], tags)


def variants():
    """Every supported table/PCS family, with nontrivial stages and channel grids."""
    for pcs in ['Lab ', 'XYZ ']:
        for version in [2,4]:
            yield f'legacy-{version}-{pcs.strip()}', profile(pcs=pcs,version=version)
        yield f'modern-{pcs.strip()}', profile(pcs=pcs,modern=True)
        yield f'curved-{pcs.strip()}', profile(pcs=pcs,table=modern_table(
            lambda q: max(0,q[0]*q[1] + .2*q[2] - .25),grid=(3,4,5),
            inputs=[curve(params=[2]),curve(params=[1,.75,.125]),curve(values=[0,10000,45000,65535])],
            matrix=[.8,.1,0,0,.8,.1,.1,0,.8,.025,.05,.075],
            middle=[curve(params=[1,.75,0,.1]),curve(params=[2,1,0,.5,.25]),curve(params=[2,1,0,.5,.25,.125,.0625])],
            output=curve(params=[1.5])))
    for version in [2,4]:
        yield f'eight-{version}', profile(eight_table(lambda q:max(0,q[0]-.5)),version=version)
    yield 'modern-eight-clut', profile(modern_table(lambda q:q[0]*q[1]*q[2],grid=(3,4,2),precision=1))
