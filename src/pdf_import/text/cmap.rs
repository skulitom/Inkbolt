use super::super::*;
use crate::vector_native::pdf_read::{delimiter, object_at, space};

/// A ToUnicode resource is declarative. Accept only the resource wrapper,
/// metadata and mapping operators whose effects we can represent.
pub(super) struct CharacterMap {
    pub width: usize,
    pub values: BTreeMap<u16, String>,
    pub cids: BTreeMap<u16, u16>,
    pub system: Option<SystemInfo>,
    pub name: Option<Vec<u8>>,
}

#[derive(Debug, PartialEq)]
pub(super) struct SystemInfo {
    pub registry: Vec<u8>,
    pub ordering: Vec<u8>,
    pub supplement: usize,
}
impl SystemInfo {
    pub fn read(value: &Value) -> Result<Self, Error> {
        let fields = value.dict()?;
        allowed(fields, &[b"Registry", b"Ordering", b"Supplement"])?;
        let string = |key: &[u8]| match field(fields, key)? {
            Value::Bytes(bytes) if !bytes.is_empty() => Ok(bytes.clone()),
            _ => Err(invalid("Invalid PDF character collection identifier")),
        };
        Ok(Self {
            registry: string(b"Registry")?,
            ordering: string(b"Ordering")?,
            supplement: field(fields, b"Supplement")?.integer()?,
        })
    }
}

struct Reader<'a> {
    bytes: &'a [u8],
    at: usize,
    nodes: usize,
    control: &'a Control,
}
impl<'a> Reader<'a> {
    fn peek(&mut self) -> Option<u8> {
        loop {
            while self.bytes.get(self.at).is_some_and(|&c| space(c)) {
                self.at += 1;
            }
            if self.bytes.get(self.at) != Some(&b'%') {
                return self.bytes.get(self.at).copied();
            }
            while self
                .bytes
                .get(self.at)
                .is_some_and(|c| !matches!(c, b'\r' | b'\n'))
            {
                self.at += 1;
            }
        }
    }
    fn word(&mut self) -> Result<&'a [u8], Error> {
        self.peek();
        let start = self.at;
        while self.bytes.get(self.at).is_some_and(|&c| !delimiter(c)) {
            self.at += 1;
        }
        if self.at == start || self.at - start > bounds::MAX_TOKEN_BYTES {
            return Err(invalid("Expected a bounded CMap token"));
        }
        Ok(&self.bytes[start..self.at])
    }
    fn expect(&mut self, expected: &[u8]) -> Result<(), Error> {
        if self.word()? != expected {
            return Err(unsupported("Unsupported CMap resource or operator"));
        }
        Ok(())
    }
    fn object(&mut self) -> Result<Value, Error> {
        object_at(self.bytes, &mut self.at, &mut self.nodes, self.control)
    }
    fn name(&mut self) -> Result<Vec<u8>, Error> {
        match self.object()? {
            Value::Name(n) => Ok(n),
            _ => Err(invalid("Expected a CMap name")),
        }
    }
    fn hex(&mut self) -> Result<Vec<u8>, Error> {
        if self.peek() == Some(b'<')
            && let Value::Bytes(bytes) = self.object()?
        {
            return Ok(bytes);
        }
        Err(invalid("Expected a CMap hexadecimal string"))
    }
}
fn code(raw: &[u8], width: usize) -> Result<u16, Error> {
    if raw.len() != width {
        return Err(invalid("Inconsistent CMap character-code width"));
    }
    match raw {
        [a] => Ok(u16::from(*a)),
        [a, b] => Ok(u16::from_be_bytes([*a, *b])),
        _ => Err(unsupported(
            "Only one- and two-byte horizontal text codes are supported",
        )),
    }
}
fn unicode(bytes: &[u8]) -> Result<String, Error> {
    if bytes.is_empty() || !bytes.len().is_multiple_of(2) {
        return Err(invalid("Invalid UTF-16BE destination in PDF ToUnicode map"));
    }
    char::decode_utf16(
        bytes
            .as_chunks::<2>()
            .0
            .iter()
            .copied()
            .map(u16::from_be_bytes),
    )
    .collect::<Result<String, _>>()
    .map_err(|_| invalid("Invalid surrogate in PDF ToUnicode map"))
}

pub(super) fn read(
    bytes: &[u8],
    for_cids: bool,
    remaining: &mut usize,
    control: &Control,
) -> Result<CharacterMap, Error> {
    let mut r = Reader {
        bytes,
        at: 0,
        nodes: 0,
        control,
    };
    if r.name()? != b"CIDInit" || r.name()? != b"ProcSet" {
        return Err(unsupported("Unsupported ToUnicode resource header"));
    }
    r.expect(b"findresource")?;
    r.expect(b"begin")?;
    r.object()?.integer()?;
    r.expect(b"dict")?;
    r.expect(b"begin")?;
    r.expect(b"begincmap")?;
    let mut codespace = None;
    let mut values = BTreeMap::new();
    let mut cids = BTreeMap::new();
    let mut metadata = BTreeSet::new();
    let mut system = None;
    let mut map_name = None;
    loop {
        control.check()?;
        match r.peek() {
            Some(b'/') => {
                let name = r.name()?;
                if !metadata.insert(name.clone()) {
                    return Err(invalid("Duplicate ToUnicode metadata"));
                }
                let value = r.object()?;
                match name.as_slice() {
                    b"CIDSystemInfo" => {
                        system = Some(SystemInfo::read(&value)?);
                    }
                    b"CMapName" => match value {
                        Value::Name(n) => map_name = Some(n),
                        _ => return Err(invalid("Invalid CMap name")),
                    },
                    b"CMapType" if value.integer()? == if for_cids { 1 } else { 2 } => (),
                    b"WMode" if value.integer()? == 0 => (),
                    _ => return Err(unsupported("Unsupported ToUnicode metadata")),
                }
                r.expect(b"def")?;
            }
            Some(b'0'..=b'9') => {
                let count = r.object()?.integer()?;
                let op = r.word()?;
                if op == b"begincodespacerange" {
                    if codespace.is_some() || count != 1 {
                        return Err(unsupported(
                            "Expected one fixed-width PDF character-code range",
                        ));
                    }
                    let low = r.hex()?;
                    let width = low.len();
                    let lo = code(&low, width)?;
                    let hi = code(&r.hex()?, width)?;
                    if lo > hi {
                        return Err(invalid("Reversed CMap codespace"));
                    }
                    codespace = Some((width, lo, hi));
                    r.expect(b"endcodespacerange")?;
                    continue;
                }
                let (width, min, max) =
                    codespace.ok_or_else(|| invalid("Missing CMap codespace"))?;
                let (range, end): (bool, &[u8]) = match (for_cids, op) {
                    (false, b"beginbfchar") => (false, b"endbfchar"),
                    (false, b"beginbfrange") => (true, b"endbfrange"),
                    (true, b"begincidchar") => (false, b"endcidchar"),
                    (true, b"begincidrange") => (true, b"endcidrange"),
                    _ => return Err(unsupported("Unsupported PDF character mapping operator")),
                };
                if count > usize::from(max - min) + 1 {
                    return Err(invalid("Too many mappings for CMap codespace"));
                }
                for _ in 0..count {
                    let lo = code(&r.hex()?, width)?;
                    let hi = if range { code(&r.hex()?, width)? } else { lo };
                    if lo < min || hi > max || lo > hi {
                        return Err(invalid("Invalid CMap source range"));
                    }
                    if for_cids {
                        let first = u16::try_from(r.object()?.integer()?)
                            .map_err(|_| invalid("Invalid CMap CID"))?;
                        for n in lo..=hi {
                            let dest = first
                                .checked_add(n - lo)
                                .ok_or_else(|| invalid("Overflowing CMap CID range"))?;
                            if cids.insert(n, dest).is_some() {
                                return Err(invalid("Duplicate PDF character code"));
                            }
                            *remaining = remaining
                                .checked_sub(4)
                                .ok_or_else(|| limit("Expanded CID map exceeds decode budget"))?;
                        }
                        continue;
                    }
                    let mut dest = r.hex()?;
                    for value in lo..=hi {
                        if value != lo {
                            let last = dest
                                .last_mut()
                                .ok_or_else(|| invalid("Empty CMap range destination"))?;
                            *last = last.checked_add(1).ok_or_else(|| {
                                unsupported("CMap range exceeds final destination byte")
                            })?;
                        }
                        *remaining = remaining.checked_sub(dest.len()).ok_or_else(|| {
                            limit("Expanded PDF character map exceeds decode budget")
                        })?;
                        if values.insert(value, unicode(&dest)?).is_some() {
                            return Err(invalid("Duplicate ToUnicode character code"));
                        }
                    }
                }
                r.expect(end)?;
            }
            _ => break,
        }
    }
    for word in [b"endcmap".as_slice(), b"CMapName", b"currentdict"] {
        r.expect(word)?;
    }
    if r.name()? != b"CMap" {
        return Err(invalid("Expected CMap resource registration"));
    }
    for word in [b"defineresource".as_slice(), b"pop", b"end", b"end"] {
        r.expect(word)?;
    }
    if r.peek().is_some() {
        return Err(unsupported("Trailing ToUnicode instructions"));
    }
    let (width, _, _) = codespace.ok_or_else(|| invalid("Missing ToUnicode codespace"))?;
    if !metadata.contains(b"CMapType".as_slice()) || map_name.is_none() {
        return Err(invalid("Missing PDF character map type or name"));
    }
    Ok(CharacterMap {
        width,
        values,
        cids,
        system,
        name: map_name,
    })
}
