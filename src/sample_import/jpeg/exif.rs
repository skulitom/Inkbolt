//! Bounded classic-TIFF metadata; only primary orientation and color are active.
use super::{malformed, unsupported};
use crate::{Error, limits::sample_import as bounds, model::limit};
use std::collections::BTreeSet;

#[derive(Default)]
pub(super) struct Metadata {
    pub orientation: Option<u8>,
    pub srgb: bool,
    pub photometric: Option<u16>,
    pub samples: Option<u16>,
    pub tags: usize,
}

#[derive(Clone, Copy, PartialEq)]
enum Role {
    Primary,
    Color,
    Other,
}

struct Reader<'a> {
    bytes: &'a [u8],
    little: bool,
}
impl Reader<'_> {
    fn bytes(&self, at: usize, length: usize) -> Result<&[u8], Error> {
        let end = at.checked_add(length).ok_or_else(malformed)?;
        self.bytes.get(at..end).ok_or_else(malformed)
    }
    fn word(&self, at: usize) -> Result<u16, Error> {
        let bytes = self.bytes(at, 2)?.try_into().unwrap();
        Ok(if self.little {
            u16::from_le_bytes(bytes)
        } else {
            u16::from_be_bytes(bytes)
        })
    }
    fn long(&self, at: usize) -> Result<u32, Error> {
        let bytes = self.bytes(at, 4)?.try_into().unwrap();
        Ok(if self.little {
            u32::from_le_bytes(bytes)
        } else {
            u32::from_be_bytes(bytes)
        })
    }
}

pub(super) fn parse(bytes: &[u8]) -> Result<Metadata, Error> {
    let little = match bytes.get(..2) {
        Some(b"II") => true,
        Some(b"MM") => false,
        _ => return Err(malformed()),
    };
    let reader = Reader { bytes, little };
    if reader.word(2)? != 42 {
        return Err(unsupported("JPEG EXIF requires classic TIFF metadata"));
    }
    let first = reader.long(4)? as usize;
    if first < 8 {
        return Err(malformed());
    }
    let mut pending = vec![(first, Role::Primary)];
    let mut visited = BTreeSet::new();
    let mut result = Metadata::default();
    let mut color_seen = false;
    while let Some((at, role)) = pending.pop() {
        if at < 8 || !visited.insert(at) {
            return Err(malformed());
        }
        if visited.len() > bounds::MAX_JPEG_EXIF_DIRECTORIES {
            return Err(limit("JPEG EXIF directory budget exceeded"));
        }
        let count = reader.word(at)? as usize;
        result.tags += count;
        if result.tags > bounds::MAX_JPEG_EXIF_ENTRIES {
            return Err(limit("JPEG EXIF entry budget exceeded"));
        }
        reader.bytes(at + 2, count * 12 + 4)?;
        let mut tags = BTreeSet::new();
        for index in 0..count {
            let entry = at + 2 + index * 12;
            let tag = reader.word(entry)?;
            if !tags.insert(tag) {
                return Err(malformed());
            }
            let kind = reader.word(entry + 2)?;
            let count = reader.long(entry + 4)? as usize;
            let unit = match kind {
                1 | 2 | 6 | 7 => 1,
                3 | 8 => 2,
                4 | 9 | 11 | 13 => 4,
                5 | 10 | 12 => 8,
                _ => return Err(unsupported("JPEG EXIF field type is unsupported")),
            };
            let length = count.checked_mul(unit).ok_or_else(malformed)?;
            let value = if length <= 4 {
                entry + 8
            } else {
                let offset = reader.long(entry + 8)? as usize;
                if offset < 8 {
                    return Err(malformed());
                }
                offset
            };
            reader.bytes(value, length)?;
            if tag == 274 || tag == 40961 {
                if kind != 3 || count != 1 {
                    return Err(malformed());
                }
                let number = reader.word(value)?;
                if tag == 274 {
                    if !(1..=8).contains(&number) {
                        return Err(malformed());
                    }
                    if role == Role::Primary {
                        result.orientation = Some(number as u8);
                    }
                } else if role == Role::Color {
                    if color_seen {
                        return Err(malformed());
                    }
                    color_seen = true;
                    result.srgb = match number {
                        1 => true,
                        65535 => false,
                        _ => return Err(unsupported("JPEG EXIF color space is unsupported")),
                    };
                } else if role == Role::Primary {
                    return Err(unsupported(
                        "JPEG EXIF color declaration is in an unsupported directory",
                    ));
                }
            } else if role == Role::Primary && matches!(tag, 262 | 277 | 531) {
                if kind != 3 || count != 1 {
                    return Err(malformed());
                }
                let number = reader.word(value)?;
                match tag {
                    262 => result.photometric = Some(number),
                    277 => result.samples = Some(number),
                    531 if number == 1 => {}
                    _ => return Err(unsupported("JPEG EXIF chroma positioning is unsupported")),
                }
            } else if role != Role::Other
                && matches!(tag, 301 | 318 | 319 | 529 | 532 | 34675 | 42240)
            {
                return Err(unsupported(
                    "JPEG EXIF color transfer semantics are unsupported",
                ));
            } else if matches!(tag, 34665 | 34853 | 40965) {
                if kind != 4 || count != 1 {
                    return Err(malformed());
                }
                let target = reader.long(value)? as usize;
                let next_role = if tag == 34665 && role == Role::Primary {
                    Role::Color
                } else {
                    Role::Other
                };
                pending.push((target, next_role));
            }
        }
        let next = reader.long(at + 2 + count * 12)? as usize;
        if next != 0 {
            pending.push((next, Role::Other));
        }
    }
    Ok(result)
}
