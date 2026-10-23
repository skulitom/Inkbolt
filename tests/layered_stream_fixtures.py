"""Original coordinate-plane layered files written without whole-image buffers."""
import hashlib
import struct
import layered_fixtures as framing


def row(channel, y, width):
    if channel == 0:
        return (bytes(range(256))*((width+255)//256))[:width]
    if channel == 1:
        return bytes([y%256])*width
    if channel == 2:
        return b''.join(bytes([(tile+y//128)%256])*min(128,width-tile*128)
                        for tile in range((width+127)//128))
    return (bytes(128)+bytes([255])*128)* (width//256) + (bytes(128)+bytes([255])*128)[:width%256]


def write(path, width, height, *, version=1, compression=0):
    """Use raw planes or independently encoded RLE literals; the cache is all zero."""
    assert version in (1,2) and compression in (0,1)
    length = framing.U64 if version==2 else framing.U32
    row_length = framing.U32 if version==2 else framing.U16
    width_bytes = width if compression==0 else width+(width+127)//128
    count_bytes = 0 if compression==0 else (4 if version==2 else 2)
    channel_bytes = 2+height*(width_bytes+count_bytes)
    extra = framing.section(b'')+framing.section(b'')+bytes(4)
    extra += framing.tag(b'luni',framing.unicode('Original coordinate planes'))+framing.tag(b'lyid',framing.U32(1))
    ids = [-1,0,1,2]
    record = struct.pack('>4iH',0,0,height,width,len(ids))
    record += b''.join(framing.I16(i)+length(channel_bytes) for i in ids)
    record += b'8BIMnorm'+bytes([255,0,8,0])+framing.section(extra)
    layer_bytes = 2+len(record)+len(ids)*channel_bytes
    padding = layer_bytes%2
    outer_bytes = (8 if version==2 else 4)+layer_bytes+padding+4
    header = b'8BPS'+framing.U16(version)+bytes(6)+struct.pack('>HIIHH',4,height,width,8,3)
    header += framing.section(b'')+framing.section(b'')+length(outer_bytes)+length(layer_bytes+padding)+framing.I16(-1)+record
    digest = hashlib.sha256()
    with path.open('xb') as stream:
        def emit(data):
            stream.write(data)
            digest.update(data)
        def plane(channel, rows):
            emit(framing.U16(compression))
            if compression==1: emit(row_length(width_bytes)*rows)
            for y in range(rows):
                values = bytes(width) if channel is None else row(channel,y,width)
                if compression==1:
                    values = b''.join(bytes([len(values[x:x+128])-1])+values[x:x+128] for x in range(0,width,128))
                emit(values)
        emit(header)
        for channel in ids: plane(3 if channel==-1 else channel,height)
        emit(bytes(padding)+framing.section(b''))
        plane(None,height*4)
    return dict(sha256=digest.hexdigest(),bytes=path.stat().st_size,channel_bytes=channel_bytes,
                width=width,height=height,version=version,compression=compression)
