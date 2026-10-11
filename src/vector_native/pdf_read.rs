//! Original bounded classic-xref PDF container reader. It does not execute pages.
use super::{invalid, unsupported};
use crate::{Error, control::Control};
use std::collections::{BTreeMap, BTreeSet};

pub const MAX_OBJECTS: usize = 4096;
const MAX_NODES: usize = 131072;
const MAX_DEPTH: usize = 32;
type Id = (u32, u16);
#[derive(Debug)]
pub enum Value {
    Integer(i64),
    Real,
    Name(Vec<u8>),
    Bytes,
    Array(Vec<Value>),
    Dict(BTreeMap<Vec<u8>, Value>),
    Ref(Id),
    Bool,
    Null,
}
impl Value {
    pub fn dict(&self) -> Result<&BTreeMap<Vec<u8>, Value>, Error> {
        if let Self::Dict(v) = self {
            Ok(v)
        } else {
            Err(invalid("Expected a PDF dictionary"))
        }
    }
    pub fn integer(&self) -> Result<usize, Error> {
        if let Self::Integer(v) = self {
            usize::try_from(*v).map_err(|_| invalid("Expected nonnegative PDF integer"))
        } else {
            Err(invalid("Expected a PDF integer"))
        }
    }
    fn named(&self, name: &[u8]) -> bool {
        matches!(self,Self::Name(v) if v==name)
    }
}
fn space(b: u8) -> bool {
    matches!(b, 0 | 9 | 10 | 12 | 13 | 32)
}
fn delimiter(b: u8) -> bool {
    space(b) || b"()<>[]{}/%".contains(&b)
}
struct Parser<'a, 'b> {
    data: &'a [u8],
    at: usize,
    nodes: &'b mut usize,
    control: &'b Control,
}
impl Parser<'_, '_> {
    fn skip(&mut self) {
        loop {
            while self.data.get(self.at).is_some_and(|v| space(*v)) {
                self.at += 1;
            }
            if self.data.get(self.at) != Some(&b'%') {
                break;
            }
            while self
                .data
                .get(self.at)
                .is_some_and(|v| !matches!(v, b'\r' | b'\n'))
            {
                self.at += 1;
            }
        }
    }
    fn word(&mut self) -> Result<&[u8], Error> {
        self.skip();
        let start = self.at;
        while self.data.get(self.at).is_some_and(|v| !delimiter(*v)) {
            self.at += 1;
        }
        if start == self.at || self.at - start > 128 {
            return Err(invalid("Invalid PDF token"));
        }
        Ok(&self.data[start..self.at])
    }
    fn keyword(&mut self, expected: &[u8]) -> Result<(), Error> {
        if self.word()? == expected {
            Ok(())
        } else {
            Err(invalid("Unexpected PDF token"))
        }
    }
    fn unsigned(&mut self) -> Result<usize, Error> {
        let word = self.word()?;
        if !word.iter().all(u8::is_ascii_digit) {
            return Err(invalid("Invalid PDF offset or identifier"));
        }
        std::str::from_utf8(word)
            .unwrap()
            .parse()
            .map_err(|_| invalid("PDF integer overflow"))
    }
    fn value(&mut self, depth: usize) -> Result<Value, Error> {
        if depth > MAX_DEPTH || *self.nodes >= MAX_NODES {
            return Err(super::limit("PDF syntax depth or node budget exceeded"));
        }
        *self.nodes += 1;
        if (*self.nodes).is_multiple_of(256) {
            self.control.check()?;
        }
        self.skip();
        let b = *self
            .data
            .get(self.at)
            .ok_or_else(|| invalid("Truncated PDF value"))?;
        self.at += 1;
        match b {
            b'/' => {
                let mut name = Vec::new();
                while let Some(&b) = self.data.get(self.at).filter(|v| !delimiter(**v)) {
                    self.at += 1;
                    name.push(if b == b'#' {
                        let v = self.hex_pair()?;
                        if v == 0 {
                            return Err(invalid("Null in PDF name"));
                        }
                        v
                    } else {
                        b
                    });
                    if name.len() > 256 {
                        return Err(super::limit("PDF name exceeds budget"));
                    }
                }
                Ok(Value::Name(name))
            }
            b'(' => {
                let mut nesting = 1;
                let mut length = 0;
                while nesting > 0 {
                    let b = *self
                        .data
                        .get(self.at)
                        .ok_or_else(|| invalid("Truncated PDF string"))?;
                    self.at += 1;
                    length += 1;
                    if length > 65536 {
                        return Err(super::limit("PDF string exceeds budget"));
                    }
                    match b {
                        b'\\' => {
                            self.data
                                .get(self.at)
                                .ok_or_else(|| invalid("Truncated PDF escape"))?;
                            self.at += 1;
                        }
                        b'(' => {
                            nesting += 1;
                            if nesting > MAX_DEPTH {
                                return Err(super::limit("PDF string nesting exceeds budget"));
                            }
                        }
                        b')' => nesting -= 1,
                        _ => {}
                    }
                }
                Ok(Value::Bytes)
            }
            b'<' if self.data.get(self.at) == Some(&b'<') => {
                self.at += 1;
                let mut fields = BTreeMap::new();
                loop {
                    self.skip();
                    if self.data.get(self.at..self.at + 2) == Some(b">>") {
                        self.at += 2;
                        break;
                    }
                    let Value::Name(key) = self.value(depth + 1)? else {
                        return Err(invalid("PDF dictionary key must be a name"));
                    };
                    let value = self.value(depth + 1)?;
                    if fields.insert(key, value).is_some() {
                        return Err(invalid("Duplicate PDF dictionary key"));
                    }
                }
                Ok(Value::Dict(fields))
            }
            b'<' => {
                let mut n = 0;
                loop {
                    let b = *self
                        .data
                        .get(self.at)
                        .ok_or_else(|| invalid("Truncated PDF hex string"))?;
                    self.at += 1;
                    if b == b'>' {
                        break;
                    }
                    if space(b) {
                        continue;
                    }
                    if !b.is_ascii_hexdigit() {
                        return Err(invalid("Invalid PDF hex string"));
                    }
                    n += 1;
                    if n > 131072 {
                        return Err(super::limit("PDF hex string exceeds budget"));
                    }
                }
                Ok(Value::Bytes)
            }
            b'[' => {
                let mut values = Vec::new();
                loop {
                    self.skip();
                    if self.data.get(self.at) == Some(&b']') {
                        self.at += 1;
                        break;
                    }
                    values.push(self.value(depth + 1)?);
                }
                Ok(Value::Array(values))
            }
            _ => {
                self.at -= 1;
                let word = self.word()?.to_vec();
                if word == b"true" || word == b"false" {
                    return Ok(Value::Bool);
                }
                if word == b"null" {
                    return Ok(Value::Null);
                }
                let text = std::str::from_utf8(&word).map_err(|_| invalid("Invalid PDF number"))?;
                let digits = text.trim_start_matches(['+', '-']);
                if digits.is_empty()
                    || !digits.bytes().all(|c| c.is_ascii_digit() || c == b'.')
                    || digits.bytes().filter(|c| *c == b'.').count() > 1
                {
                    return Err(invalid("Unsupported PDF value token"));
                }
                if text.contains('.') {
                    if !text.parse::<f64>().is_ok_and(f64::is_finite) {
                        return Err(invalid("Invalid PDF real"));
                    }
                    return Ok(Value::Real);
                }
                let number = text
                    .parse::<i64>()
                    .map_err(|_| invalid("PDF integer overflow"))?;
                let saved = self.at;
                if let Ok(generation) = self.unsigned()
                    && self.keyword(b"R").is_ok()
                {
                    return Ok(Value::Ref((
                        u32::try_from(number).map_err(|_| invalid("Invalid PDF reference"))?,
                        u16::try_from(generation).map_err(|_| invalid("Invalid PDF generation"))?,
                    )));
                }
                self.at = saved;
                Ok(Value::Integer(number))
            }
        }
    }
    fn hex_pair(&mut self) -> Result<u8, Error> {
        let pair = self
            .data
            .get(self.at..self.at + 2)
            .ok_or_else(|| invalid("Truncated PDF name escape"))?;
        let text = std::str::from_utf8(pair).map_err(|_| invalid("Invalid PDF name escape"))?;
        let v = u8::from_str_radix(text, 16).map_err(|_| invalid("Invalid PDF name escape"))?;
        self.at += 2;
        Ok(v)
    }
}
struct Object {
    value: Value,
    stream: Option<(usize, usize)>,
}
pub struct Container<'a> {
    bytes: &'a [u8],
    objects: BTreeMap<Id, Object>,
    root: Id,
}
impl<'a> Container<'a> {
    pub fn read(bytes: &'a [u8], control: &Control) -> Result<Self, Error> {
        control.check()?;
        if !bytes.starts_with(b"%PDF-") {
            return Err(unsupported("Native vector source requires a PDF container"));
        }
        let tail = bytes
            .windows(9)
            .rposition(|v| v == b"startxref")
            .ok_or_else(|| invalid("Missing PDF cross-reference pointer"))?;
        let mut nodes = 0;
        let mut p = Parser {
            data: bytes,
            at: tail + 9,
            nodes: &mut nodes,
            control,
        };
        let xref = p.unsigned()?;
        while p.data.get(p.at).is_some_and(|b| space(*b)) {
            p.at += 1;
        }
        if bytes.get(p.at..p.at + 5) != Some(b"%%EOF")
            || !bytes[p.at + 5..].iter().all(|b| space(*b))
            || xref >= tail
        {
            return Err(invalid("Invalid PDF ending"));
        }
        p.at = xref;
        if p.word()? != b"xref" {
            return Err(unsupported("Cross-reference streams are not yet supported"));
        }
        let mut offsets = BTreeMap::new();
        let mut ids = BTreeSet::new();
        loop {
            p.skip();
            if p.data.get(p.at..p.at + 7) == Some(b"trailer") {
                p.keyword(b"trailer")?;
                break;
            }
            let start = p.unsigned()?;
            let count = p.unsigned()?;
            if count > MAX_OBJECTS || start.checked_add(count).is_none_or(|n| n > MAX_OBJECTS) {
                return Err(super::limit("PDF object budget exceeded"));
            }
            for id in start..start + count {
                let at = p.unsigned()?;
                let generation = p.unsigned()?;
                let flag = p.word()?;
                let generation =
                    u16::try_from(generation).map_err(|_| invalid("Invalid PDF generation"))?;
                if !ids.insert(id) {
                    return Err(invalid("Duplicate cross-reference entry"));
                }
                match flag {
                    b"n" => {
                        if id == 0
                            || at < 8
                            || at >= xref
                            || offsets.insert(at, (id as u32, generation)).is_some()
                        {
                            return Err(invalid("Invalid PDF object offset"));
                        }
                    }
                    b"f" => {}
                    _ => return Err(invalid("Invalid cross-reference entry")),
                }
            }
        }
        let trailer = p.value(0)?;
        p.skip();
        if p.at != tail {
            return Err(invalid("Unexpected data after PDF trailer"));
        }
        let trailer = trailer.dict()?;
        if [b"Prev".as_slice(), b"XRefStm", b"Encrypt"]
            .iter()
            .any(|k| trailer.contains_key(*k))
        {
            return Err(unsupported(
                "Incremental, hybrid and encrypted PDF containers are not yet supported",
            ));
        }
        let size = field(trailer, b"Size")?.integer()?;
        if size > MAX_OBJECTS || ids.iter().any(|&id| id >= size) {
            return Err(invalid("Invalid PDF cross-reference size"));
        }
        let Value::Ref(root) = field(trailer, b"Root")? else {
            return Err(invalid("PDF root must be indirect"));
        };
        let root = *root;
        let offsets: Vec<_> = offsets.into_iter().collect();
        let mut objects = BTreeMap::new();
        for (index, &(at, id)) in offsets.iter().enumerate() {
            control.check()?;
            let end = offsets.get(index + 1).map_or(xref, |v| v.0);
            let mut p = Parser {
                data: &bytes[..end],
                at,
                nodes: &mut nodes,
                control,
            };
            if p.unsigned()? != id.0 as usize || p.unsigned()? != id.1 as usize {
                return Err(invalid(
                    "PDF object identity disagrees with cross-reference",
                ));
            }
            p.keyword(b"obj")?;
            let value = p.value(0)?;
            let terminator = p.word()?;
            let stream = if terminator == b"stream" {
                value.dict()?;
                if p.data.get(p.at) == Some(&b'\r') {
                    p.at += 1;
                    if p.data.get(p.at) == Some(&b'\n') {
                        p.at += 1;
                    }
                } else if p.data.get(p.at) == Some(&b'\n') {
                    p.at += 1;
                } else {
                    return Err(invalid("PDF stream requires a line ending"));
                }
                Some((p.at, end))
            } else {
                if terminator != b"endobj" {
                    return Err(invalid("Missing PDF object terminator"));
                }
                p.skip();
                if p.at != end {
                    return Err(invalid("Unexpected data after PDF object"));
                }
                None
            };
            objects.insert(id, Object { value, stream });
        }
        let doc = Self {
            bytes,
            objects,
            root,
        };
        for object in doc.objects.values() {
            if let Some((start, end)) = object.stream {
                let length = doc
                    .resolve(field(object.value.dict()?, b"Length")?)?
                    .integer()?;
                let finish = start
                    .checked_add(length)
                    .filter(|&n| n <= end)
                    .ok_or_else(|| invalid("Truncated PDF stream"))?;
                let mut p = Parser {
                    data: &bytes[..end],
                    at: finish,
                    nodes: &mut 0,
                    control,
                };
                p.keyword(b"endstream")?;
                p.keyword(b"endobj")?;
                p.skip();
                if p.at != end {
                    return Err(invalid("PDF stream length disagrees with object boundary"));
                }
            }
        }
        Ok(doc)
    }
    pub fn resolve<'b>(&'b self, mut value: &'b Value) -> Result<&'b Value, Error> {
        let mut seen = BTreeSet::new();
        while let Value::Ref(id) = value {
            if seen.len() >= MAX_DEPTH || !seen.insert(*id) {
                return Err(invalid("Cyclic or deep PDF reference"));
            }
            let object = self
                .objects
                .get(id)
                .ok_or_else(|| invalid("Missing PDF object"))?;
            if object.stream.is_some() {
                return Err(invalid("Expected a PDF value, found a stream"));
            }
            value = &object.value;
        }
        Ok(value)
    }
    pub fn stream(
        &self,
        value: &Value,
        maximum: usize,
        control: &Control,
    ) -> Result<Vec<u8>, Error> {
        let Value::Ref(id) = value else {
            return Err(invalid("PDF stream must be indirect"));
        };
        let object = self
            .objects
            .get(id)
            .ok_or_else(|| invalid("Missing PDF stream"))?;
        let (start, _) = object
            .stream
            .ok_or_else(|| invalid("Expected PDF stream"))?;
        let dict = object.value.dict()?;
        let length = self.resolve(field(dict, b"Length")?)?.integer()?;
        let bytes = &self.bytes[start..start + length];
        if dict.contains_key(b"F".as_slice()) || dict.contains_key(b"DecodeParms".as_slice()) {
            return Err(unsupported(
                "External streams and decode parameters are unsupported in editable vector blocks",
            ));
        }
        match dict.get(b"Filter".as_slice()) {
            None => {
                if bytes.len() > maximum {
                    return Err(super::limit("Native vector block budget exceeded"));
                }
                Ok(bytes.to_vec())
            }
            Some(value) if self.resolve(value)?.named(b"FlateDecode") => {
                let mut decoder = flate2::Decompress::new(true);
                let mut out = Vec::new();
                let mut buffer = [0u8; 16384];
                loop {
                    control.check()?;
                    let before = (decoder.total_in(), decoder.total_out());
                    let status = decoder
                        .decompress(
                            &bytes[before.0 as usize..],
                            &mut buffer,
                            flate2::FlushDecompress::None,
                        )
                        .map_err(|_| invalid("Invalid compressed PDF stream"))?;
                    let written = (decoder.total_out() - before.1) as usize;
                    if out.len() + written > maximum {
                        return Err(super::limit("Native vector block budget exceeded"));
                    }
                    out.extend_from_slice(&buffer[..written]);
                    if status == flate2::Status::StreamEnd {
                        break;
                    }
                    if before == (decoder.total_in(), decoder.total_out()) {
                        return Err(invalid("Incomplete compressed PDF stream"));
                    }
                }
                if decoder.total_in() != bytes.len() as u64 {
                    return Err(invalid("Trailing compressed PDF stream data"));
                }
                Ok(out)
            }
            _ => Err(unsupported("Unsupported editable-vector block filter")),
        }
    }
    pub fn editable(&self) -> Result<(&BTreeMap<Vec<u8>, Value>, usize), Error> {
        let root = self
            .resolve(
                &self
                    .objects
                    .get(&self.root)
                    .ok_or_else(|| invalid("Missing PDF root"))?
                    .value,
            )?
            .dict()?;
        if !field(root, b"Type")?.named(b"Catalog") {
            return Err(invalid("Invalid PDF catalog"));
        }
        let mut found = BTreeSet::new();
        self.pieces(root, &mut found)?;
        let mut seen = BTreeSet::new();
        let pages = self.pages(field(root, b"Pages")?, &mut seen, &mut found, 0)?;
        if found.len() != 1 {
            return Err(unsupported(
                "Expected one authoritative editable vector stream; preview pages are not editable source",
            ));
        }
        let object = &self.objects[found.first().unwrap()];
        Ok((object.value.dict()?, pages))
    }
    fn pieces(
        &self,
        dict: &BTreeMap<Vec<u8>, Value>,
        found: &mut BTreeSet<Id>,
    ) -> Result<(), Error> {
        if let Some(value) = dict.get(b"PieceInfo".as_slice()) {
            for entry in self.resolve(value)?.dict()?.values() {
                let entry = self.resolve(entry)?.dict()?;
                if let Some(private) = entry.get(b"Private".as_slice())
                    && let Value::Dict(fields) = self.resolve(private)?
                    && fields.contains_key(b"AIPrivateData1".as_slice())
                {
                    let Value::Ref(id) = private else {
                        return Err(unsupported(
                            "Editable container must have an indirect identity",
                        ));
                    };
                    found.insert(*id);
                }
            }
        }
        Ok(())
    }
    fn pages(
        &self,
        value: &Value,
        seen: &mut BTreeSet<Id>,
        found: &mut BTreeSet<Id>,
        depth: usize,
    ) -> Result<usize, Error> {
        if depth > MAX_DEPTH {
            return Err(super::limit("PDF page tree depth exceeded"));
        }
        let Value::Ref(id) = value else {
            return Err(invalid("PDF pages must be indirect"));
        };
        if !seen.insert(*id) {
            return Err(invalid("Repeated PDF page tree node"));
        }
        let dict = self.resolve(value)?.dict()?;
        if field(dict, b"Type")?.named(b"Page") {
            self.pieces(dict, found)?;
            return Ok(1);
        }
        if !field(dict, b"Type")?.named(b"Pages") {
            return Err(invalid("Invalid PDF page tree"));
        }
        let Value::Array(kids) = self.resolve(field(dict, b"Kids")?)? else {
            return Err(invalid("Invalid PDF page children"));
        };
        let mut count = 0;
        for child in kids {
            count += self.pages(child, seen, found, depth + 1)?;
            if count > 32 {
                return Err(super::limit("PDF page budget exceeded"));
            }
        }
        if count != field(dict, b"Count")?.integer()? {
            return Err(invalid("PDF page count disagrees with tree"));
        }
        Ok(count)
    }
}
pub fn field<'a>(dict: &'a BTreeMap<Vec<u8>, Value>, key: &[u8]) -> Result<&'a Value, Error> {
    dict.get(key)
        .ok_or_else(|| invalid("Missing required PDF field"))
}
