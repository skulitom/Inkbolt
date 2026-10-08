"""Original directional ICC charts for continuous native ink preparation."""
import itertools
import struct
from cmyk_fixtures import fixed, lookup, cmyk_profile
from test_profiles_cli import linear_profile
from test_sample_profiles_cli import tags_of, repack
from gamut_fixtures import curve, IDENTITY


def modern(fn, outputs, forward, inputs=None, matrix=None, middle=None, ending=None, grid=(2, 2, 2), precision=2):
    levels = 255 if precision == 1 else 65535
    values = [round(v*levels) for p in itertools.product(*(tuple(i/(n-1) for i in range(n)) for n in grid)) for v in fn(p)]
    packed = bytes(values) if precision == 1 else struct.pack('>'+str(len(values))+'H', *values)
    clut = bytes(grid)+bytes(13)+bytes([precision, 0, 0, 0])+packed
    clut += bytes(-len(clut)%4)
    incoming = b''.join(inputs or [IDENTITY]*3)
    outgoing = b''.join(ending or [IDENTITY]*outputs)
    parts = [outgoing if forward else incoming,
             b''.join(fixed(v) for v in matrix) if matrix else b'',
             b''.join(middle or [IDENTITY]*3) if matrix else b'',
             clut, incoming if forward else outgoing]
    offsets=[];at=32
    for part in parts:offsets.append(at if part else 0);at+=len(part)
    return (b'mAB ' if forward else b'mBA ')+bytes(4)+bytes([3,outputs,0,0])+struct.pack('>5I',*offsets)+b''.join(parts)


def eight(fn, outputs):
    return (b'mft1'+bytes(4)+bytes([3,outputs,2,0])
            + b''.join(fixed(v) for v in (1,0,0,0,1,0,0,0,1))
            + bytes(range(256))*3
            + bytes(round(v*255) for q in itertools.product((0,1),repeat=3) for v in fn(q))
            + bytes(range(256))*outputs)


def source_profile(pcs='Lab ', kind='legacy', table=None):
    original=linear_profile();header=bytearray(original[:128]);header[12:16]=b'scnr';header[20:24]=pcs.encode()
    tags={k:v for k,v in tags_of(original).items() if k in (b'desc',b'cprt',b'wtpt')}
    if table is None:
        scale=65280/65535 if kind=='legacy' and pcs=='Lab ' else 1
        fn=(lambda q:[(.2+.6*q[0])*scale, (.45+.1*q[1])*scale, (.45+.1*q[2])*scale]) if pcs=='Lab ' else (lambda q:[.1+.3*q[0],.1+.3*q[1],.1+.3*q[2]])
        table=eight(fn,3) if kind=='eight' else lookup(3,3,fn,modern=kind=='modern',forward=True)
    tags.update({b'A2B0':table,b'A2B1':table})
    return repack(header,tags)


def output_profile(table, pcs='XYZ '):
    original=cmyk_profile(pcs=pcs);tags=tags_of(original)
    tags.update({b'B2A0':table,b'B2A1':table})
    return repack(original[:128],tags)
