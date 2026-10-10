//! Original bounded parser for dictionary-based text data. Parsing grants no
//! permission to discard unknown layout semantics or use a cached image.
use super::*;
use serde_json::{Map, Number};

const MAX_NODES: usize = 4096;
const MAX_CONTAINER: usize = 512;
const MAX_DEPTH: usize = 16;
const MAX_STRING_BYTES: usize = 16388;

struct Parser<'a> {
    bytes: &'a [u8],
    at: usize,
    nodes: usize,
    control: &'a Control,
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
        if start == self.at || self.at - start > 128 {
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
    fn string(&mut self) -> Result<String, Error> {
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
                return Err(limit("Text-data string exceeds 16388 bytes"));
            }
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
        String::from_utf16(&words).map_err(|_| malformed())
    }
    fn value(&mut self, depth: usize) -> Result<Value, Error> {
        self.control.check()?;
        self.nodes += 1;
        if self.nodes > MAX_NODES || depth > MAX_DEPTH {
            return Err(limit("Text data exceeds 4096 values or depth 16"));
        }
        self.space();
        if self.accept(b"<<") {
            let mut fields = Map::new();
            loop {
                self.space();
                if self.accept(b">>") {
                    break;
                }
                if fields.len() >= MAX_CONTAINER {
                    return Err(limit("Text-data dictionary exceeds 512 entries"));
                }
                let key = self.key()?;
                let value = self.value(depth + 1)?;
                if fields.insert(key, value).is_some() {
                    return Err(malformed());
                }
            }
            Ok(Value::Object(fields))
        } else if self.accept(b"[") {
            let mut values = Vec::new();
            loop {
                self.space();
                if self.accept(b"]") {
                    break;
                }
                if values.len() >= MAX_CONTAINER {
                    return Err(limit("Text-data array exceeds 512 entries"));
                }
                values.push(self.value(depth + 1)?);
            }
            Ok(Value::Array(values))
        } else if self.accept(b"(") {
            Ok(Value::String(self.string()?))
        } else {
            let token = self.token()?;
            match token {
                b"true" => Ok(Value::Bool(true)),
                b"false" => Ok(Value::Bool(false)),
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
                    Ok(Value::Number(number))
                }
            }
        }
    }
}
pub(super) fn parse(bytes: &[u8], control: &Control) -> Result<Value, Error> {
    if bytes.len() > 65536 {
        return Err(limit("Text data exceeds 64 KiB"));
    }
    let mut parser = Parser {
        bytes,
        at: 0,
        nodes: 0,
        control,
    };
    let result = parser.value(0)?;
    parser.space();
    if parser.at != bytes.len() || !result.is_object() {
        return Err(malformed());
    }
    Ok(result)
}
