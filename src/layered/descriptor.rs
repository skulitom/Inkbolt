//! Bounded original reader for the public typed descriptor framing.
use super::{binary::Reader, *};
use std::collections::BTreeMap;

pub(super) struct Descriptor {
    class: String,
    fields: BTreeMap<String, Datum>,
}
pub(super) enum Datum {
    Bool(bool),
    Integer(i32),
    Number(f64),
    Text(String),
    Enum(String, String),
    Object(Descriptor),
    List(Vec<Datum>),
}
impl Descriptor {
    pub fn field(&mut self, key: &str) -> Result<Datum, Error> {
        self.fields
            .remove(key)
            .ok_or_else(|| unsupported("Required metadata field is missing"))
    }
    pub fn finish(self, class: &str) -> Result<(), Error> {
        if self.class != class || !self.fields.is_empty() {
            return Err(unsupported(
                "Unknown metadata class or fields cannot be discarded",
            ));
        }
        Ok(())
    }
}
impl Datum {
    pub fn object(self) -> Result<Descriptor, Error> {
        match self {
            Self::Object(d) => Ok(d),
            _ => Err(malformed()),
        }
    }
    pub fn text(self) -> Result<String, Error> {
        match self {
            Self::Text(s) => Ok(s),
            _ => Err(malformed()),
        }
    }
    pub fn integer(self) -> Result<i32, Error> {
        match self {
            Self::Integer(n) => Ok(n),
            _ => Err(malformed()),
        }
    }
    pub fn boolean(self) -> Result<bool, Error> {
        match self {
            Self::Bool(b) => Ok(b),
            _ => Err(malformed()),
        }
    }
}
fn identifier(input: &mut Reader<'_>) -> Result<String, Error> {
    let count = input.word()? as usize;
    if count > 128 {
        return Err(limit("Descriptor identifier exceeds 128 bytes"));
    }
    let bytes = input.take(if count == 0 { 4 } else { count })?;
    if bytes.iter().any(|b| !(32..=126).contains(b)) {
        return Err(malformed());
    }
    String::from_utf8(bytes.to_vec()).map_err(|_| malformed())
}
fn text(input: &mut Reader<'_>) -> Result<String, Error> {
    let s = input.unicode()?;
    let s = s.strip_suffix('\0').unwrap_or(&s);
    if s.contains('\0') {
        return Err(malformed());
    }
    Ok(s.to_owned())
}
struct Budget<'a> {
    nodes: usize,
    control: &'a Control,
}
impl Budget<'_> {
    fn charge(&mut self, depth: usize) -> Result<(), Error> {
        self.control.check()?;
        self.nodes += 1;
        if depth > 8 || self.nodes > 512 {
            return Err(limit("Descriptor exceeds depth 8 or 512 values"));
        }
        Ok(())
    }
    fn count(input: &mut Reader<'_>) -> Result<usize, Error> {
        let count = input.word()? as usize;
        if count > 128 {
            return Err(limit("Descriptor container exceeds 128 entries"));
        }
        Ok(count)
    }
    fn object(&mut self, input: &mut Reader<'_>, depth: usize) -> Result<Descriptor, Error> {
        self.charge(depth)?;
        text(input)?;
        let class = identifier(input)?;
        let count = Self::count(input)?;
        let mut fields = BTreeMap::new();
        for _ in 0..count {
            let key = identifier(input)?;
            let value = self.value(input, depth + 1)?;
            if fields.insert(key, value).is_some() {
                return Err(malformed());
            }
        }
        Ok(Descriptor { class, fields })
    }
    fn value(&mut self, input: &mut Reader<'_>, depth: usize) -> Result<Datum, Error> {
        self.charge(depth)?;
        Ok(match input.take(4)? {
            b"bool" => match input.byte()? {
                0 => Datum::Bool(false),
                1 => Datum::Bool(true),
                _ => return Err(malformed()),
            },
            b"long" => Datum::Integer(input.signed()?),
            b"doub" => {
                let n = f64::from_be_bytes(input.take(8)?.try_into().unwrap());
                if !n.is_finite() {
                    return Err(malformed());
                }
                Datum::Number(n)
            }
            b"TEXT" => Datum::Text(text(input)?),
            b"enum" => Datum::Enum(identifier(input)?, identifier(input)?),
            b"Objc" | b"GlbO" => Datum::Object(self.object(input, depth)?),
            b"VlLs" => {
                let count = Self::count(input)?;
                let mut values = Vec::with_capacity(count);
                for _ in 0..count {
                    values.push(self.value(input, depth + 1)?);
                }
                Datum::List(values)
            }
            _ => return Err(unsupported("Unsupported typed descriptor value")),
        })
    }
}
pub(super) fn versioned(input: &mut Reader<'_>, control: &Control) -> Result<Descriptor, Error> {
    if input.left() > 65536 {
        return Err(limit("Descriptor record exceeds 64 KiB"));
    }
    if input.word()? != 16 {
        return Err(unsupported("Unknown descriptor version"));
    }
    Budget { nodes: 0, control }.object(input, 0)
}
