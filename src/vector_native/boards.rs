//! Typed artboard fields from data comments; unused resource definitions are not executed.
use super::{
    tokens::{self, Token},
    *,
};
use std::collections::{BTreeMap, BTreeSet};
#[derive(Debug)]
pub struct Board {
    pub name: String,
    pub bounds: [f64; 4],
    pub locked: bool,
}
pub fn read(setup: &[u8], control: &Control) -> Result<Vec<Board>, Error> {
    let mut data = Vec::new();
    for line in setup.split(|v| matches!(v, b'\r' | b'\n')) {
        if let Some(line) = line.strip_prefix(b"%_") {
            data.extend_from_slice(line);
            data.push(b'\n');
        }
    }
    let tokens = tokens::lex(&data, control)?;
    let mut stack = Vec::new();
    let mut selected = None;
    let mut bleeds = BTreeSet::new();
    for i in 0..tokens.len() {
        if matches!(tokens[i], Token::Name(_)) && tokens.get(i + 1) == Some(&Token::Mark(b':')) {
            stack.push(i);
            if stack.len() > 32 {
                return Err(limit("Native typed data nesting exceeded"));
            }
        }
        if tokens[i].mark(b';') {
            let start = stack
                .pop()
                .ok_or_else(|| invalid("Unbalanced native setup data"))?;
            if tokens.get(i + 1) == Some(&Token::Bytes(b"ArtboardArray".to_vec())) {
                if selected.replace((start, i)).is_some() {
                    return Err(invalid("Multiple native artboard arrays"));
                }
                if tokens.get(i + 2) != Some(&Token::Mark(b',')) {
                    return Err(invalid("Invalid native artboard field terminator"));
                }
            }
        }
        if let Token::Bytes(key) = &tokens[i]
            && [
                b"BleedTopValue".as_slice(),
                b"BleedRightValue",
                b"BleedBottomValue",
                b"BleedLeftValue",
            ]
            .contains(&key.as_slice())
        {
            if !bleeds.insert(key.clone())
                || i < 2
                || tokens[i - 1] != Token::Name("Real".into())
                || tokens.get(i + 1) != Some(&Token::Mark(b','))
            {
                return Err(invalid("Ambiguous native bleed field"));
            }
            if tokens[i - 2].number()? != 0.0 {
                return Err(unsupported(
                    "Nonzero native document bleed has not been mapped",
                ));
            }
        }
    }
    if !stack.is_empty() {
        return Err(invalid("Unclosed native setup data"));
    }
    if bleeds.len() != 4 {
        return Err(unsupported("Missing native document bleed declaration"));
    }
    let (start, finish) =
        selected.ok_or_else(|| unsupported("Native artboard array is required"))?;
    if tokens[start] != Token::Name("Array".into()) {
        return Err(invalid("Native artboards must be an array"));
    }
    let mut at = start + 2;
    let mut boards = Vec::new();
    while at < finish {
        if tokens[at] != Token::Name("Dictionary".into()) {
            return Err(invalid("Native artboard must be a dictionary"));
        }
        let stop = tokens::end(&tokens, at)?;
        if stop >= finish || tokens.get(stop + 1) != Some(&Token::Mark(b',')) {
            return Err(invalid("Invalid native artboard element"));
        }
        boards.push(board(&tokens[at + 2..stop])?);
        at = stop + 2;
        if boards.len() > crate::boards::MAX_ARTBOARDS {
            return Err(limit("Native artboard count exceeds engine budget"));
        }
    }
    if at != finish || boards.is_empty() {
        return Err(invalid("Empty or malformed native artboard array"));
    }
    Ok(boards)
}
fn board(tokens: &[Token]) -> Result<Board, Error> {
    let mut at = 0;
    let mut fields = BTreeMap::new();
    while at < tokens.len() {
        let start = at;
        if matches!(tokens[at], Token::Name(_)) && tokens.get(at + 1) == Some(&Token::Mark(b':')) {
            at = tokens::end(tokens, at)? + 1;
        } else {
            while at < tokens.len() && !matches!(tokens[at], Token::Bytes(_)) {
                at += 1;
            }
            // Strings can be scalar values, so the key is the final string before a comma.
            while at < tokens.len() && tokens.get(at + 1) != Some(&Token::Mark(b',')) {
                at += 1;
            }
        }
        let key = tokens
            .get(at)
            .ok_or_else(|| invalid("Missing native artboard field name"))?
            .text()?;
        if tokens.get(at + 1) != Some(&Token::Mark(b','))
            || fields.insert(key, &tokens[start..at]).is_some()
        {
            return Err(invalid("Duplicate or malformed native artboard field"));
        }
        at += 2;
    }
    let allowed = [
        "PAR",
        "Name",
        "PositionPoint1",
        "PositionPoint2",
        "RulerOrigin",
        "IsArtboardDefaultName",
        "DisplayMark",
        "IsArtboardLocked",
        "IsArtboardSelected",
        "EachArtboardColor",
        "ArtboardUUID",
    ];
    if fields.keys().any(|s| !allowed.contains(&s.as_str())) {
        return Err(unsupported("Unknown native artboard property"));
    }
    let numbers = |key: &str, kind: &str, count: usize| -> Result<Vec<f64>, Error> {
        let value = fields
            .get(key)
            .ok_or_else(|| invalid("Missing native artboard property"))?;
        if value.len() != count + 1 || value.last() != Some(&Token::Name(kind.into())) {
            return Err(invalid("Wrong native artboard property type"));
        }
        value[..count].iter().map(Token::number).collect()
    };
    if numbers("PAR", "Real", 1)? != [1.0] || numbers("DisplayMark", "Int", 1)? != [0.0] {
        return Err(unsupported(
            "Non-square pixel aspect or artboard display marks are unsupported",
        ));
    }
    numbers("RulerOrigin", "RealPoint", 2)?;
    let mut locked = false;
    for key in [
        "IsArtboardDefaultName",
        "IsArtboardLocked",
        "IsArtboardSelected",
    ] {
        let value = numbers(key, "Bool", 1)?[0];
        if value != 0.0 && value != 1.0 {
            return Err(invalid("Invalid artboard Boolean"));
        }
        if key == "IsArtboardLocked" {
            locked = value == 1.0;
        }
    }
    let text = fields
        .get("Name")
        .ok_or_else(|| invalid("Missing native artboard name"))?;
    if text.len() != 2 || text[1] != Token::Name("UnicodeString".into()) {
        return Err(invalid("Invalid native artboard name type"));
    }
    let name = text[0].text()?;
    let uuid = fields
        .get("ArtboardUUID")
        .ok_or_else(|| invalid("Missing native artboard identity"))?;
    if uuid.len() != 2 || uuid[1] != Token::Name("String".into()) {
        return Err(invalid("Invalid native artboard identity"));
    }
    uuid[0].text()?;
    // This display-only style is admitted only in the observed transparent/default form.
    let style = fields
        .get("EachArtboardColor")
        .ok_or_else(|| unsupported("Missing artboard display color declaration"))?;
    let expected = tokens::lex(
        b"/FillStyle : 0 1 0 0 0 Xy 0 J 0 j 1 w 10 M []0 d 0 XR 0 0 Xd /Def ;",
        &Control::default(),
    )?;
    if *style != expected {
        return Err(unsupported(
            "Nondefault native artboard display color is unsupported",
        ));
    }
    let a = numbers("PositionPoint1", "RealPointRelToROrigin", 2)?;
    let b = numbers("PositionPoint2", "RealPointRelToROrigin", 2)?;
    if a[0] >= b[0] || a[1] <= b[1] {
        return Err(invalid("Invalid native artboard rectangle"));
    }
    Ok(Board {
        name,
        bounds: [a[0], a[1], b[0], b[1]],
        locked,
    })
}
