//! Separate bounded metadata from encoded channel ranges in an immutable private snapshot.
use super::{MAX_FILE_BYTES, Version, binary::Reader, malformed, unsupported};
use crate::{
    Error,
    control::Control,
    model::limit,
    sample_import::source::{ReadSeek, Source},
};
use std::{
    borrow::Cow,
    cell::RefCell,
    collections::VecDeque,
    io::{self, BufRead, BufReader, Cursor, Read, Seek, SeekFrom},
    rc::Rc,
};

type Shared = Rc<RefCell<Box<dyn ReadSeek>>>;

pub(super) struct Range {
    source: Shared,
    start: u64,
    position: u64,
    length: usize,
}
impl Read for Range {
    fn read(&mut self, bytes: &mut [u8]) -> io::Result<usize> {
        let count = bytes.len().min(self.length - self.position as usize);
        if count == 0 {
            return Ok(0);
        }
        let mut file = self
            .source
            .try_borrow_mut()
            .map_err(|_| io::Error::other("Private layered input is already borrowed"))?;
        file.seek(SeekFrom::Start(self.start + self.position))?;
        let read = file.read(&mut bytes[..count])?;
        self.position += read as u64;
        Ok(read)
    }
}

pub(super) enum Plane<'a> {
    Bytes(&'a [u8]),
    File(Range),
}
impl<'a> Plane<'a> {
    pub fn reader(self) -> (Box<dyn BufRead + 'a>, usize) {
        match self {
            Self::Bytes(bytes) => (Box::new(Cursor::new(bytes)), bytes.len()),
            Self::File(range) => {
                let length = range.length;
                (
                    Box::new(BufReader::with_capacity(
                        crate::limits::sample_import::INPUT_BUFFER_BYTES,
                        range,
                    )),
                    length,
                )
            }
        }
    }
}

pub(super) struct Parts<'a> {
    pub prefix: Cow<'a, [u8]>,
    pub layers: Cow<'a, [u8]>,
    pub tail: Cow<'a, [u8]>,
    pub channels: Option<VecDeque<Range>>,
    pub merged: Plane<'a>,
    pub layer_bytes: usize,
    pub source_bytes: usize,
}

impl<'a> Parts<'a> {
    pub fn memory(bytes: &'a [u8]) -> Result<Self, Error> {
        let mut input = Reader::new(bytes);
        if input.take(4)? != b"8BPS" {
            return Err(malformed());
        }
        let version = Version::read(input.short()?)?;
        input.take(20)?;
        input.section()?;
        input.section()?;
        let prefix = Cow::Borrowed(&bytes[..input.at]);
        let mut section = input.framed_section(version)?;
        if section.left() == 0 {
            return Err(unsupported("Flattened input has no editable layer records"));
        }
        let layers = section.framed_section(version)?;
        Ok(Self {
            prefix,
            layer_bytes: layers.data.len(),
            layers: Cow::Borrowed(layers.data),
            tail: Cow::Borrowed(section.take(section.left())?),
            channels: None,
            merged: Plane::Bytes(input.take(input.left())?),
            source_bytes: bytes.len(),
        })
    }

    pub fn captured(source: Source, control: &Control) -> Result<Parts<'static>, Error> {
        let length = source.bytes;
        if length > crate::limits::layered::MAX_NATIVE_FILE_BYTES {
            return Err(limit("Native layered input exceeds its encoded byte bound"));
        }
        let mut input = Metadata {
            source: Rc::new(RefCell::new(source.reader)),
            at: 0,
            end: length as u64,
            bytes: 0,
        };
        let mut prefix = input.take(26, control)?;
        if &prefix[..4] != b"8BPS" {
            return Err(malformed());
        }
        let version = Version::read(u16::from_be_bytes(prefix[4..6].try_into().unwrap()))?;
        for _ in 0..2 {
            let size = input.take(4, control)?;
            let count = u32::from_be_bytes(size[..].try_into().unwrap()) as usize;
            prefix.extend(size);
            prefix.extend(input.take(count, control)?);
        }
        let section_length = input.length(version, control)?;
        if section_length == 0 {
            return Err(unsupported("Flattened input has no editable layer records"));
        }
        let section_end = input.extent(section_length)?;
        input.end = section_end;
        let layer_bytes = input.length(version, control)?;
        let layer_end = input.extent(layer_bytes)?;
        input.end = layer_end;
        let mut layers = input.take(2, control)?;
        let count = i16::from_be_bytes(layers[..].try_into().unwrap());
        if count == 0
            || count == i16::MIN
            || count.unsigned_abs() as usize > crate::limits::layered::MAX_SERIALIZED_RECORDS
        {
            return Err(limit(
                "Layered input exceeds its serialized layer and boundary record bound",
            ));
        }
        let mut channel_lengths = Vec::new();
        for _ in 0..count.unsigned_abs() {
            control.check()?;
            let record = input.take(18, control)?;
            let channels = u16::from_be_bytes(record[16..].try_into().unwrap()) as usize;
            if channels > crate::limits::layered::MAX_IMPORT_LAYER_CHANNELS {
                return Err(unsupported(
                    "Layered import requires RGB with optional transparency and one authored scalar mask",
                ));
            }
            layers.extend(record);
            for _ in 0..channels {
                layers.extend(input.take(2, control)?);
                let field = input.take(if version == Version::Large { 8 } else { 4 }, control)?;
                let length = if version == Version::Large {
                    u64::from_be_bytes(field[..].try_into().unwrap())
                } else {
                    u32::from_be_bytes(field[..].try_into().unwrap()) as u64
                };
                if length > crate::limits::layered::MAX_NATIVE_FILE_BYTES as u64 {
                    return Err(limit("Layered channel exceeds the encoded byte bound"));
                }
                channel_lengths.push(length as usize);
                layers.extend(field);
            }
            let attributes = input.take(16, control)?;
            let extra = u32::from_be_bytes(attributes[12..].try_into().unwrap()) as usize;
            layers.extend(attributes);
            layers.extend(input.take(extra, control)?);
        }
        let mut channels = VecDeque::new();
        for length in channel_lengths {
            let end = input.extent(length)?;
            channels.push_back(Range {
                source: input.source.clone(),
                start: input.at,
                position: 0,
                length,
            });
            input.at = end;
        }
        let padding = (layer_end - input.at) as usize;
        if padding > 3 {
            return Err(malformed());
        }
        layers.extend(input.take(padding, control)?);
        input.end = section_end;
        let tail = input.take((section_end - input.at) as usize, control)?;
        let merged = Plane::File(Range {
            source: input.source,
            start: section_end,
            position: 0,
            length: length - section_end as usize,
        });
        Ok(Parts {
            prefix: Cow::Owned(prefix),
            layers: Cow::Owned(layers),
            tail: Cow::Owned(tail),
            channels: Some(channels),
            merged,
            layer_bytes,
            source_bytes: length,
        })
    }
}

pub(super) fn channel<'a>(
    ranges: &mut Option<VecDeque<Range>>,
    inline: &mut Reader<'a>,
    count: usize,
) -> Result<Plane<'a>, Error> {
    if let Some(ranges) = ranges {
        let range = ranges.pop_front().ok_or_else(malformed)?;
        if range.length != count {
            return Err(malformed());
        }
        Ok(Plane::File(range))
    } else {
        Ok(Plane::Bytes(inline.take(count)?))
    }
}

struct Metadata {
    source: Shared,
    at: u64,
    end: u64,
    bytes: usize,
}
impl Metadata {
    fn extent(&self, count: usize) -> Result<u64, Error> {
        self.at
            .checked_add(count as u64)
            .filter(|end| *end <= self.end)
            .ok_or_else(malformed)
    }
    fn take(&mut self, count: usize, control: &Control) -> Result<Vec<u8>, Error> {
        let end = self.extent(count)?;
        self.bytes = self
            .bytes
            .checked_add(count)
            .filter(|n| *n <= MAX_FILE_BYTES)
            .ok_or_else(|| {
                limit(&format!(
                    "Layered metadata and embedded source bytes exceed their {} MiB bound",
                    MAX_FILE_BYTES / (1024 * 1024)
                ))
            })?;
        let mut bytes = vec![0; count];
        let mut reader = Range {
            source: self.source.clone(),
            start: self.at,
            position: 0,
            length: count,
        };
        for chunk in bytes.chunks_mut(crate::limits::sample_import::INPUT_BUFFER_BYTES) {
            control.check()?;
            reader
                .read_exact(chunk)
                .map_err(|_| crate::assets::io_error())?;
        }
        self.at = end;
        Ok(bytes)
    }
    fn length(&mut self, version: Version, control: &Control) -> Result<usize, Error> {
        let bytes = self.take(if version == Version::Large { 8 } else { 4 }, control)?;
        let value = if version == Version::Large {
            u64::from_be_bytes(bytes[..].try_into().unwrap())
        } else {
            u32::from_be_bytes(bytes[..].try_into().unwrap()) as u64
        };
        if value > crate::limits::layered::MAX_NATIVE_FILE_BYTES as u64 {
            return Err(limit("Layered section exceeds the encoded byte bound"));
        }
        Ok(value as usize)
    }
}
