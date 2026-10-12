//! Bounded data tokens only. No program execution, includes or file operators.
use super::*;
use crate::limits::vector_native_tokens::{
    MAX_CONTAINER_DEPTH, MAX_STRING_BYTES, MAX_STRING_DEPTH, MAX_TOKENS, MAX_WORD_BYTES,
};
#[derive(Clone, Debug, PartialEq)]
pub enum Token {
    Word(String),
    Name(String),
    Bytes(Vec<u8>),
    Mark(u8),
    Comment(Vec<u8>),
}
impl Token {
    pub fn mark(&self, c: u8) -> bool {
        *self == Self::Mark(c)
    }
    pub fn number(&self) -> Result<f64, Error> {
        match self {
            Self::Word(v) => v
                .parse::<f64>()
                .ok()
                .filter(|v| v.is_finite())
                .ok_or_else(|| invalid("Expected a finite native number")),
            _ => Err(invalid("Expected native number")),
        }
    }
    pub fn text(&self) -> Result<String, Error> {
        let Self::Bytes(v) = self else {
            return Err(invalid("Expected a native text value"));
        };
        if !v.is_ascii() {
            return Err(unsupported(
                "Native non-ASCII text encoding has not been verified",
            ));
        }
        String::from_utf8(v.clone()).map_err(|_| invalid("Invalid native text"))
    }
}
pub fn lex(bytes: &[u8], control: &Control) -> Result<Vec<Token>, Error> {
    let mut out = Vec::new();
    let mut at = 0;
    while at < bytes.len() {
        if out.len() >= MAX_TOKENS {
            return Err(limit("Native syntax token budget exceeded"));
        }
        if out
            .len()
            .is_multiple_of(crate::limits::vector_native::PARSE_CHECK_INTERVAL)
        {
            control.check()?;
        }
        let b = bytes[at];
        at += 1;
        if b.is_ascii_whitespace() {
            continue;
        }
        let token = match b {
            b'%' => {
                let start = at;
                while at < bytes.len() && !matches!(bytes[at], b'\r' | b'\n') {
                    at += 1;
                }
                Token::Comment(bytes[start..at].to_vec())
            }
            b'(' => {
                let mut value = Vec::new();
                let mut depth = 1;
                while depth > 0 {
                    let b = *bytes
                        .get(at)
                        .ok_or_else(|| invalid("Unclosed native string"))?;
                    at += 1;
                    match b {
                        b'\\' => {
                            let escaped = *bytes
                                .get(at)
                                .ok_or_else(|| invalid("Incomplete native escape"))?;
                            at += 1;
                            match escaped {
                                b'\r' => {
                                    if bytes.get(at) == Some(&b'\n') {
                                        at += 1;
                                    }
                                }
                                b'\n' => {}
                                b'0'..=b'7' => {
                                    let mut n = (escaped - b'0') as u16;
                                    for _ in 0..2 {
                                        if let Some(&v @ b'0'..=b'7') = bytes.get(at) {
                                            n = 8 * n + (v - b'0') as u16;
                                            at += 1;
                                        } else {
                                            break;
                                        }
                                    }
                                    value.push(n as u8);
                                }
                                b'n' => value.push(b'\n'),
                                b'r' => value.push(b'\r'),
                                b't' => value.push(b'\t'),
                                b'b' => value.push(8),
                                b'f' => value.push(12),
                                v => value.push(v),
                            }
                        }
                        b'(' => {
                            depth += 1;
                            if depth > MAX_STRING_DEPTH {
                                return Err(limit("Native string nesting exceeded"));
                            }
                            value.push(b);
                        }
                        b')' => {
                            depth -= 1;
                            if depth > 0 {
                                value.push(b);
                            }
                        }
                        b'\r' => {
                            if bytes.get(at) == Some(&b'\n') {
                                at += 1;
                            }
                            value.push(b'\n');
                        }
                        v => value.push(v),
                    }
                    if value.len() > MAX_STRING_BYTES {
                        return Err(limit("Native string length exceeded"));
                    }
                }
                Token::Bytes(value)
            }
            b':' | b';' | b',' | b'[' | b']' | b'<' | b'>' => Token::Mark(b),
            b')' => return Err(invalid("Unexpected native string terminator")),
            _ => {
                let start = at - 1;
                while at < bytes.len()
                    && !bytes[at].is_ascii_whitespace()
                    && !b"():;,[]<>%/".contains(&bytes[at])
                {
                    at += 1;
                }
                let word = &bytes[start..at];
                if word.len() > MAX_WORD_BYTES || !word.is_ascii() {
                    return Err(limit("Native token length or encoding exceeded"));
                }
                let text = String::from_utf8(word.to_vec()).unwrap();
                if b == b'/' {
                    Token::Name(text[1..].to_owned())
                } else {
                    Token::Word(text)
                }
            }
        };
        out.push(token);
    }
    Ok(out)
}
pub fn end(tokens: &[Token], start: usize) -> Result<usize, Error> {
    if !matches!(tokens.get(start), Some(Token::Name(_)))
        || tokens.get(start + 1) != Some(&Token::Mark(b':'))
    {
        return Err(invalid("Expected native typed container"));
    }
    let mut depth = 0usize;
    for i in start..tokens.len() {
        if matches!(tokens[i], Token::Name(_)) && tokens.get(i + 1) == Some(&Token::Mark(b':')) {
            depth += 1;
            if depth > MAX_CONTAINER_DEPTH {
                return Err(limit("Native container nesting exceeded"));
            }
        }
        if tokens[i].mark(b';') {
            depth = depth
                .checked_sub(1)
                .ok_or_else(|| invalid("Unbalanced native container"))?;
            if depth == 0 {
                return Ok(i);
            }
        }
    }
    Err(invalid("Unclosed native typed container"))
}
