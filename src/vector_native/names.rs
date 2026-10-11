//! Display labels encoded as native data identities, independently of literal strings.
use super::*;
use std::fmt::Write;

pub fn encode(value: &str) -> Result<String, Error> {
    if value.is_empty() || !value.bytes().all(|b| (32..=126).contains(&b)) {
        return Err(unsupported(
            "Native path names require nonempty printable ASCII",
        ));
    }
    let mut out = String::new();
    for (i, b) in value.bytes().enumerate() {
        if b.is_ascii_alphabetic() || (i > 0 && (b.is_ascii_digit() || b"-.:".contains(&b))) {
            out.push(b as char);
        } else if b == b' ' {
            out.push('_');
        } else {
            write!(out, "_x{b:02X}_").unwrap();
        }
    }
    if decode(&out)? != value {
        return Err(unsupported(
            "Native path name has an ambiguous encoded identity",
        ));
    }
    Ok(out)
}
pub fn decode(value: &str) -> Result<String, Error> {
    let bytes = value.as_bytes();
    let mut at = 0;
    let mut out = String::new();
    while at < bytes.len() {
        let b = bytes[at];
        if b == b'_' {
            if bytes.get(at + 1) == Some(&b'x') {
                let mut end = at + 2;
                while bytes.get(end).is_some_and(u8::is_ascii_hexdigit) {
                    end += 1;
                }
                if bytes.get(end) == Some(&b'_') && end - at - 2 > 2 {
                    return Err(unsupported("Wide native name escapes have not been mapped"));
                }
            }
            if bytes.get(at + 1) == Some(&b'x')
                && bytes.get(at + 4) == Some(&b'_')
                && bytes[at + 2..at + 4].iter().all(u8::is_ascii_hexdigit)
            {
                let b = u8::from_str_radix(&value[at + 2..at + 4], 16)
                    .map_err(|_| invalid("Invalid native name escape"))?;
                if !(33..=126).contains(&b) {
                    return Err(unsupported(
                        "Native encoded name is outside printable ASCII",
                    ));
                }
                out.push(b as char);
                at += 5;
                continue;
            }
            out.push(' ');
        } else if b.is_ascii_alphabetic()
            || b == b':'
            || (at > 0 && (b.is_ascii_digit() || b"-.".contains(&b)))
        {
            out.push(b as char);
        } else {
            return Err(invalid("Unescaped native identity name character"));
        }
        at += 1;
    }
    Ok(out)
}
