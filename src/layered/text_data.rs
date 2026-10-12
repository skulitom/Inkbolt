//! Original bounded parser for dictionary-based text data. Parsing grants no
//! permission to discard unknown layout semantics or use a cached image.
use super::*;
use crate::limits::layered_text_data as bounds;
use serde_json::Number;
use std::collections::BTreeMap;

use crate::limits::layered_text_data::MAX_CONTAINER;
use crate::limits::layered_text_data::MAX_DEPTH;
use crate::limits::layered_text_data::MAX_NODES;
use crate::limits::layered_text_data::MAX_STRING_BYTES;

// Names and opaque strings must remain distinct from Unicode text. In
// particular, a named value cannot impersonate a story or a font face.
#[derive(PartialEq)]
pub(super) enum Node {
    Dictionary(BTreeMap<String, Node>),
    Array(Vec<Node>),
    Text(String),
    Bytes(Vec<u8>),
    Name(String),
    Scalar(Value),
}
impl Node {
    pub fn optional(&self, key: &str) -> Result<Option<&Self>, Error> {
        match self {
            Self::Dictionary(d) => Ok(d.get(key)),
            _ => Err(malformed()),
        }
    }
    pub fn field(&self, key: &str) -> Result<&Self, Error> {
        match self {
            Self::Dictionary(d) => d.get(key).ok_or_else(malformed),
            _ => Err(malformed()),
        }
    }
    pub fn array(&self) -> Result<&[Self], Error> {
        match self {
            Self::Array(v) => Ok(v),
            _ => Err(malformed()),
        }
    }
    pub fn text(&self) -> Result<&str, Error> {
        match self {
            Self::Text(v) => Ok(v),
            _ => Err(malformed()),
        }
    }
    pub fn unsigned(&self) -> Result<usize, Error> {
        match self {
            Self::Scalar(v) => v
                .as_u64()
                .and_then(|n| usize::try_from(n).ok())
                .ok_or_else(malformed),
            _ => Err(malformed()),
        }
    }
    pub fn number(&self) -> Result<f64, Error> {
        match self {
            Self::Scalar(v) => v.as_f64().filter(|n| n.is_finite()).ok_or_else(malformed),
            _ => Err(malformed()),
        }
    }
    fn into_json(self) -> Result<Value, Error> {
        Ok(match self {
            Self::Dictionary(d) => Value::Object(
                d.into_iter()
                    .map(|(k, v)| Ok((k, v.into_json()?)))
                    .collect::<Result<_, Error>>()?,
            ),
            Self::Array(a) => Value::Array(
                a.into_iter()
                    .map(Self::into_json)
                    .collect::<Result<_, _>>()?,
            ),
            Self::Text(t) => Value::String(t),
            Self::Scalar(v) => v,
            // These forms are framed only by the global parser, not admitted to
            // the local dictionary contract or interpreted as Unicode strings.
            Self::Bytes(bytes) => {
                return Err(unsupported(&format!(
                    "Opaque text-data string ({} bytes) has no local mapping",
                    bytes.len()
                )));
            }
            Self::Name(name) => {
                return Err(unsupported(&format!(
                    "Named text-data value ({} bytes) has no local mapping",
                    name.len()
                )));
            }
        })
    }
}

struct Parser<'a> {
    bytes: &'a [u8],
    at: usize,
    nodes: usize,
    control: &'a Control,
    global: bool,
}
impl Parser<'_> {
    fn space(&mut self) {
        while self
            .bytes
            .get(self.at)
            .is_some_and(|b| b.is_ascii_whitespace())
        {
            self.at += 1;
        }
    }
    fn accept(&mut self, token: &[u8]) -> bool {
        if self.bytes[self.at..].starts_with(token) {
            self.at += token.len();
            true
        } else {
            false
        }
    }
    fn token(&mut self) -> Result<&[u8], Error> {
        let start = self.at;
        while self
            .bytes
            .get(self.at)
            .is_some_and(|b| !b.is_ascii_whitespace() && !b"<>[]()/\\".contains(b))
        {
            self.at += 1;
        }
        if start == self.at || self.at - start > bounds::MAX_TOKEN_BYTES {
            return Err(malformed());
        }
        Ok(&self.bytes[start..self.at])
    }
    fn key(&mut self) -> Result<String, Error> {
        if !self.accept(b"/") {
            return Err(malformed());
        }
        let token = self.token()?;
        if token.iter().any(|b| !(33..=126).contains(b)) {
            return Err(malformed());
        }
        String::from_utf8(token.to_vec()).map_err(|_| malformed())
    }
    fn string(&mut self) -> Result<Node, Error> {
        let mut bytes = Vec::new();
        loop {
            let b = *self.bytes.get(self.at).ok_or_else(malformed)?;
            self.at += 1;
            match b {
                b')' => break,
                b'(' => return Err(malformed()),
                b'\\' => {
                    let b = *self.bytes.get(self.at).ok_or_else(malformed)?;
                    self.at += 1;
                    // Only the byte escapes with an unambiguous observed mapping
                    // are admitted; unsupported escape forms fail explicitly.
                    if !b"()\\".contains(&b) {
                        return Err(unsupported("Unsupported text-data string escape"));
                    }
                    bytes.push(b);
                }
                _ => bytes.push(b),
            }
            if bytes.len() > MAX_STRING_BYTES {
                return Err(limit(&format!(
                    "Text-data string exceeds {MAX_STRING_BYTES} bytes"
                )));
            }
        }
        if self.global && !bytes.starts_with(&[254, 255]) {
            return Ok(Node::Bytes(bytes));
        }
        if !bytes.starts_with(&[254, 255]) || !bytes.len().is_multiple_of(2) {
            return Err(malformed());
        }
        let words = bytes[2..]
            .as_chunks::<2>()
            .0
            .iter()
            .map(|b| u16::from_be_bytes(*b))
            .collect::<Vec<_>>();
        String::from_utf16(&words)
            .map(Node::Text)
            .map_err(|_| malformed())
    }
    fn container_limit(&self) -> usize {
        if self.global {
            bounds::MAX_GLOBAL_CONTAINER
        } else {
            MAX_CONTAINER
        }
    }
    fn dictionary(&mut self, depth: usize, implicit: bool) -> Result<Node, Error> {
        let mut fields = BTreeMap::new();
        loop {
            self.space();
            if (implicit && self.at == self.bytes.len()) || (!implicit && self.accept(b">>")) {
                break;
            }
            if fields.len() >= self.container_limit() {
                return Err(limit("Text-data dictionary exceeds its entry budget"));
            }
            let key = self.key()?;
            let value = self.value(depth + 1)?;
            if fields.insert(key, value).is_some() {
                return Err(malformed());
            }
        }
        Ok(Node::Dictionary(fields))
    }
    fn value(&mut self, depth: usize) -> Result<Node, Error> {
        self.control.check()?;
        self.nodes += 1;
        let (nodes, levels) = if self.global {
            (bounds::MAX_GLOBAL_NODES, bounds::MAX_GLOBAL_DEPTH)
        } else {
            (MAX_NODES, MAX_DEPTH)
        };
        if self.nodes > nodes || depth > levels {
            return Err(limit("Text data exceeds its value or depth budget"));
        }
        self.space();
        if self.accept(b"<<") {
            self.dictionary(depth, false)
        } else if self.accept(b"[") {
            let mut values = Vec::new();
            loop {
                self.space();
                if self.accept(b"]") {
                    break;
                }
                if values.len() >= self.container_limit() {
                    return Err(limit("Text-data array exceeds its entry budget"));
                }
                values.push(self.value(depth + 1)?);
            }
            Ok(Node::Array(values))
        } else if self.accept(b"(") {
            self.string()
        } else if self.global && self.bytes.get(self.at) == Some(&b'/') {
            Ok(Node::Name(self.key()?))
        } else {
            let token = self.token()?;
            match token {
                b"true" => Ok(Node::Scalar(Value::Bool(true))),
                b"false" => Ok(Node::Scalar(Value::Bool(false))),
                _ => {
                    let s = std::str::from_utf8(token).map_err(|_| malformed())?;
                    let digits = s.strip_prefix(['+', '-']).unwrap_or(s);
                    if !digits.bytes().any(|b| b.is_ascii_digit())
                        || digits.bytes().any(|b| !b.is_ascii_digit() && b != b'.')
                        || digits.bytes().filter(|b| *b == b'.').count() > 1
                    {
                        return Err(malformed());
                    }
                    let number = if s.contains('.') {
                        Number::from_f64(s.parse().map_err(|_| malformed())?)
                            .ok_or_else(malformed)?
                    } else {
                        Number::from(s.parse::<i64>().map_err(|_| malformed())?)
                    };
                    Ok(Node::Scalar(Value::Number(number)))
                }
            }
        }
    }
}
pub(super) fn parse(bytes: &[u8], control: &Control) -> Result<Value, Error> {
    if bytes.len() > bounds::MAX_BYTES {
        return Err(limit(&format!(
            "Text data exceeds {} KiB",
            bounds::MAX_BYTES / 1024
        )));
    }
    let mut parser = Parser {
        bytes,
        at: 0,
        nodes: 0,
        control,
        global: false,
    };
    let result = parser.value(0)?.into_json()?;
    parser.space();
    if parser.at != bytes.len() || !result.is_object() {
        return Err(malformed());
    }
    Ok(result)
}

pub(super) fn parse_global(bytes: &[u8], control: &Control) -> Result<Node, Error> {
    if bytes.len() > bounds::MAX_GLOBAL_BYTES {
        return Err(limit(&format!(
            "Global text data exceeds {} KiB",
            bounds::MAX_GLOBAL_BYTES / 1024
        )));
    }
    let mut parser = Parser {
        bytes,
        at: 0,
        nodes: 1,
        control,
        global: true,
    };
    // The global stream is a sequence of root dictionary entries without an
    // outer delimiter pair. It is not the local dictionary's grammar.
    parser.dictionary(0, true)
}
