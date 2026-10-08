//! Original bounded big-endian framing and byte-plane codecs.
use super::*;

pub(super) struct Reader<'a> {
    pub data: &'a [u8],
    pub at: usize,
}
impl<'a> Reader<'a> {
    pub fn new(data: &'a [u8]) -> Self {
        Self { data, at: 0 }
    }
    pub fn take(&mut self, count: usize) -> Result<&'a [u8], Error> {
        let end = self.at.checked_add(count).ok_or_else(malformed)?;
        let value = self.data.get(self.at..end).ok_or_else(malformed)?;
        self.at = end;
        Ok(value)
    }
    pub fn byte(&mut self) -> Result<u8, Error> {
        Ok(self.take(1)?[0])
    }
    pub fn short(&mut self) -> Result<u16, Error> {
        Ok(u16::from_be_bytes(self.take(2)?.try_into().unwrap()))
    }
    pub fn word(&mut self) -> Result<u32, Error> {
        Ok(u32::from_be_bytes(self.take(4)?.try_into().unwrap()))
    }
    pub fn length(&mut self, version: Version) -> Result<usize, Error> {
        let value = if version == Version::Large {
            u64::from_be_bytes(self.take(8)?.try_into().unwrap())
        } else {
            self.word()? as u64
        };
        if value > MAX_FILE_BYTES as u64 {
            return Err(limit("Layered section or channel exceeds 32 MiB"));
        }
        usize::try_from(value).map_err(|_| limit("Layered length exceeds address space"))
    }
    pub fn framed_section(&mut self, version: Version) -> Result<Reader<'a>, Error> {
        let n = self.length(version)?;
        Ok(Self::new(self.take(n)?))
    }
    pub fn tagged_section(&mut self, key: &[u8; 4], version: Version) -> Result<Reader<'a>, Error> {
        self.framed_section(tag_version(key, version))
    }
    pub fn signed(&mut self) -> Result<i32, Error> {
        Ok(i32::from_be_bytes(self.take(4)?.try_into().unwrap()))
    }
    pub fn section(&mut self) -> Result<Reader<'a>, Error> {
        let n = self.word()? as usize;
        Ok(Self::new(self.take(n)?))
    }
    pub fn left(&self) -> usize {
        self.data.len() - self.at
    }
    pub fn end(&self) -> Result<(), Error> {
        if self.left() == 0 {
            Ok(())
        } else {
            Err(malformed())
        }
    }
    pub fn zero_padding(&mut self, maximum: usize) -> Result<(), Error> {
        if self.left() > maximum || self.take(self.left())?.iter().any(|&v| v != 0) {
            return Err(malformed());
        }
        Ok(())
    }
    pub fn unicode(&mut self) -> Result<String, Error> {
        let n = self.word()? as usize;
        if n > 1024 {
            return Err(limit("Layer name exceeds 1024 UTF-16 units"));
        }
        let words = self
            .take(n * 2)?
            .as_chunks::<2>()
            .0
            .iter()
            .map(|b| u16::from_be_bytes([b[0], b[1]]))
            .collect::<Vec<_>>();
        String::from_utf16(&words).map_err(|_| malformed())
    }
}
pub(super) fn short(out: &mut Vec<u8>, v: u16) {
    out.extend(v.to_be_bytes());
}
pub(super) fn word(out: &mut Vec<u8>, v: u32) {
    out.extend(v.to_be_bytes());
}
pub(super) fn section(out: &mut Vec<u8>, data: &[u8]) {
    word(out, data.len() as u32);
    out.extend(data);
}
pub(super) fn length(out: &mut Vec<u8>, count: usize, version: Version) {
    if version == Version::Large {
        out.extend((count as u64).to_be_bytes());
    } else {
        word(out, count as u32);
    }
}
pub(super) fn framed_section(out: &mut Vec<u8>, data: &[u8], version: Version) {
    length(out, data.len(), version);
    out.extend(data);
}
fn tag_version(key: &[u8; 4], version: Version) -> Version {
    if version == Version::Large
        && matches!(
            key,
            b"LMsk"
                | b"Lr16"
                | b"Lr32"
                | b"Layr"
                | b"Mt16"
                | b"Mt32"
                | b"Mtrn"
                | b"Alph"
                | b"FMsk"
                | b"lnk2"
                | b"FEid"
                | b"FXid"
                | b"PxSD"
                | b"cinf"
        )
    {
        Version::Large
    } else {
        Version::Standard
    }
}
pub(super) fn tag_signature(
    signature: &[u8],
    key: &[u8; 4],
    version: Version,
) -> Result<(), Error> {
    if signature == b"8BIM" || (signature == b"8B64" && tag_version(key, version) == Version::Large)
    {
        Ok(())
    } else {
        Err(unsupported(
            "Tagged signature or wide-length key has no supported framing",
        ))
    }
}
pub(super) fn unicode(text: &str) -> Vec<u8> {
    let chars: Vec<u16> = text.encode_utf16().collect();
    let mut out = Vec::new();
    word(&mut out, chars.len() as u32);
    for c in chars {
        short(&mut out, c);
    }
    out
}
pub(super) fn resource(out: &mut Vec<u8>, id: u16, data: &[u8]) {
    out.extend(b"8BIM");
    short(out, id);
    short(out, 0);
    section(out, data);
    if !data.len().is_multiple_of(2) {
        out.push(0);
    }
}
pub(super) fn tagged(out: &mut Vec<u8>, key: &[u8; 4], data: &[u8]) {
    out.extend(b"8BIM");
    out.extend(key);
    section(out, data);
    if !data.len().is_multiple_of(2) {
        out.push(0);
    }
}
pub(super) fn decode(
    bytes: &[u8],
    width: usize,
    rows: usize,
    version: Version,
    control: &Control,
) -> Result<Vec<u8>, Error> {
    let expected = width
        .checked_mul(rows)
        .filter(|&n| n <= MAX_DECODED_BYTES)
        .ok_or_else(|| limit("Layered sample buffer exceeds its byte bound"))?;
    let mut input = Reader::new(bytes);
    let compression = input.short()?;
    let mut output = Vec::with_capacity(expected);
    match compression {
        0 => output.extend(input.take(expected)?),
        1 => {
            let sizes = (0..rows)
                .map(|_| {
                    if version == Version::Large {
                        input.word().map(|v| v as usize)
                    } else {
                        input.short().map(usize::from)
                    }
                })
                .collect::<Result<Vec<_>, _>>()?;
            for size in sizes {
                control.check()?;
                let mut row = Reader::new(input.take(size)?);
                let start = output.len();
                while row.left() != 0 {
                    let code = row.byte()?;
                    match code {
                        0..=127 => {
                            let count = code as usize + 1;
                            if output.len() - start + count > width {
                                return Err(malformed());
                            }
                            output.extend(row.take(count)?);
                        }
                        129..=255 => {
                            let count = 257 - code as usize;
                            if output.len() - start + count > width {
                                return Err(malformed());
                            }
                            let v = row.byte()?;
                            output.extend(std::iter::repeat_n(v, count));
                        }
                        _ => {}
                    }
                }
                if output.len() - start != width {
                    return Err(malformed());
                }
            }
        }
        2 | 3 => {
            // A fixed output buffer bounds both decompression and prediction work.
            let mut decoded = vec![0; expected + 1];
            let mut decoder = flate2::Decompress::new(true);
            let data = input.take(input.left())?;
            let status = decoder
                .decompress(data, &mut decoded, flate2::FlushDecompress::Finish)
                .map_err(|_| malformed())?;
            if status != flate2::Status::StreamEnd
                || decoder.total_out() != expected as u64
                || decoder.total_in() != data.len() as u64
            {
                return Err(malformed());
            }
            decoded.truncate(expected);
            if compression == 3 && width != 0 {
                for row in decoded.chunks_exact_mut(width) {
                    control.check()?;
                    for i in 1..row.len() {
                        row[i] = row[i].wrapping_add(row[i - 1]);
                    }
                }
            }
            output = decoded;
        }
        _ => return Err(unsupported("Unknown layered channel compression")),
    }
    input.end()?;
    control.check()?;
    Ok(output)
}

pub(super) fn encode(
    plane: &[u8],
    width: usize,
    compression: Compression,
    version: Version,
) -> Vec<u8> {
    if matches!(compression, Compression::Raw) {
        let mut out = vec![0, 0];
        out.extend(plane);
        return out;
    }
    let mut sizes = Vec::new();
    let mut data = Vec::new();
    for row in plane.chunks_exact(width) {
        let start = data.len();
        let mut at = 0;
        while at < row.len() {
            let mut repeat = 1;
            while at + repeat < row.len() && repeat < 128 && row[at + repeat] == row[at] {
                repeat += 1;
            }
            if repeat >= 3 {
                data.extend([(257 - repeat) as u8, row[at]]);
                at += repeat;
            } else {
                let first = at;
                at += repeat;
                while at < row.len() && at - first < 128 {
                    if at + 2 < row.len() && row[at] == row[at + 1] && row[at] == row[at + 2] {
                        break;
                    }
                    at += 1;
                }
                data.push((at - first - 1) as u8);
                data.extend(&row[first..at]);
            }
        }
        if version == Version::Large {
            word(&mut sizes, (data.len() - start) as u32);
        } else {
            short(&mut sizes, (data.len() - start) as u16);
        }
    }
    let mut out = vec![0, 1];
    out.extend(sizes);
    out.extend(data);
    out
}
