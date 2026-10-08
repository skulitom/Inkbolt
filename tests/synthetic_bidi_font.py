"""Original numbered geometry for directional-order and mirrored-glyph checks."""
from synthetic_unicode_font import unicode_font, MAPPING, sfnt, coverage, layout_table
from synthetic_variable_font import variable_font, tables
from synthetic_font import pack

MAPPING = dict(MAPPING)
MAPPING.update({ord(str(i)): 2+i for i in range(10)})
MAPPING.update({ord('('):29, ord(')'):30, ord('['):31, ord(']'):32,
    ord('+'):27, ord('-'):27, ord('.'):27, ord(':'):27, 0x5B0:6, 0x600:27})


def bidi_font(codes=None, *, variable=False):
    data=tables(variable_font() if variable else unicode_font())
    mapping={c:g for c,g in MAPPING.items() if codes is None or c in codes}
    cmap=pack('HHIII',12,0,16+12*len(mapping),0,len(mapping))+b''.join(
        pack('III',c,c,g) for c,g in sorted(mapping.items()))
    data[b'cmap']=pack('HHHHI',0,1,3,10,12)+cmap
    # Explicit mark anchors on each original base glyph used by these fixtures.
    bases=[2,3,4]+list(range(8,19));mc=coverage([6]);bc=coverage(bases)
    ma=pack('HHH',1,0,6)+pack('Hhh',1,0,0)
    offset=2+2*len(bases)
    ba=pack('H',len(bases))+b''.join(pack('H',offset+6*i) for i in range(len(bases)))
    ba+=pack('Hhh',1,300,750)*len(bases)
    sub=pack('HHHHHH',1,12,12+len(mc),1,12+len(mc)+len(bc),12+len(mc)+len(bc)+len(ma))+mc+bc+ma+ba
    data[b'GPOS']=layout_table({b'latn':[0],b'hebr':[0],b'arab':[0]}, {b'mark':[0]},[(4,sub)])
    return sfnt(data)
