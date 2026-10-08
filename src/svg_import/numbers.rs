use crate::{Error, geometry, model::*};

pub(super) fn invalid(message: impl Into<String>) -> Error {
    Error::new("SVG_INVALID", message)
}
pub(super) fn unsupported(message: impl Into<String>) -> Error {
    Error::new("SVG_UNSUPPORTED", message)
}

#[derive(Clone, Copy, Debug)]
enum Token {
    Number(f64),
    Command(u8),
}

// Original scanner for the public SVG numeric grammar. A comma must separate
// two numbers; signs and decimal points can start an adjacent number.
fn tokens(s: &str) -> Result<Vec<Token>, Error> {
    let b = s.as_bytes();
    let mut i = 0;
    let mut result = Vec::new();
    let mut number_before = false;
    while i < b.len() {
        if b[i].is_ascii_whitespace() {
            i += 1;
            continue;
        }
        if b[i] == b',' {
            if !number_before {
                return Err(invalid("Unexpected comma in numeric sequence"));
            }
            i += 1;
            while i < b.len() && b[i].is_ascii_whitespace() {
                i += 1;
            }
            if i == b.len() || !(b[i].is_ascii_digit() || b"+-.".contains(&b[i])) {
                return Err(invalid("Comma must be followed by a number"));
            }
        }
        if b[i].is_ascii_alphabetic() {
            result.push(Token::Command(b[i]));
            number_before = false;
            i += 1;
        } else {
            let start = i;
            if b"+-".contains(&b[i]) {
                i += 1;
            }
            let mut digits = 0;
            while i < b.len() && b[i].is_ascii_digit() {
                i += 1;
                digits += 1;
            }
            if i < b.len() && b[i] == b'.' {
                i += 1;
                while i < b.len() && b[i].is_ascii_digit() {
                    i += 1;
                    digits += 1;
                }
            }
            if digits == 0 {
                return Err(invalid("Expected a finite SVG number"));
            }
            if i < b.len() && b"eE".contains(&b[i]) {
                i += 1;
                if i < b.len() && b"+-".contains(&b[i]) {
                    i += 1;
                }
                let exponent = i;
                while i < b.len() && b[i].is_ascii_digit() {
                    i += 1;
                }
                if i == exponent {
                    return Err(invalid("Incomplete numeric exponent"));
                }
            }
            let value = s[start..i]
                .parse::<f64>()
                .map_err(|_| invalid("Invalid number"))?;
            if !value.is_finite() {
                return Err(invalid("Number is not finite"));
            }
            result.push(Token::Number(value));
            number_before = true;
        }
        if result.len() > MAX_SEGMENTS * 8 {
            return Err(Error::new(
                "LIMIT_EXCEEDED",
                "SVG numeric token limit exceeded",
            ));
        }
    }
    Ok(result)
}
pub(super) fn list(s: &str) -> Result<Vec<f64>, Error> {
    tokens(s)?
        .into_iter()
        .map(|t| match t {
            Token::Number(n) => Ok(n),
            _ => Err(invalid("Unexpected letter in numeric list")),
        })
        .collect()
}
pub(super) fn number(s: &str) -> Result<f64, Error> {
    let n = list(s)?;
    if n.len() != 1 {
        return Err(invalid("Expected one number"));
    }
    Ok(n[0])
}
pub(super) fn length_list(s: &str) -> Result<Vec<f64>, Error> {
    let s = s.trim();
    if s.is_empty() {
        return Err(invalid("Expected a nonempty length list"));
    }
    let mut values = Vec::new();
    for part in s.split(',') {
        if part.trim().is_empty() {
            return Err(invalid("Unexpected comma in length list"));
        }
        for token in part.split_ascii_whitespace() {
            values.push(length(token)?);
            if values.len() > crate::strokes::MAX_INTERVALS {
                return Err(unsupported("Too many stroke dash intervals"));
            }
        }
    }
    Ok(values)
}
pub(super) fn length(s: &str) -> Result<f64, Error> {
    let s = s.trim();
    for (unit, factor) in [
        ("px", 1.0),
        ("in", 96.0),
        ("cm", 96.0 / 2.54),
        ("mm", 96.0 / 25.4),
        ("pt", 96.0 / 72.0),
        ("pc", 16.0),
    ] {
        if let Some(n) = s.strip_suffix(unit) {
            let value = number(n)? * factor;
            if value.is_finite() {
                return Ok(value);
            }
            return Err(invalid("Length overflow"));
        }
    }
    if s.ends_with('%') || s.chars().any(|c| c.is_alphabetic() && c != 'e' && c != 'E') {
        return Err(unsupported(
            "Only user units, px, in, cm, mm, pt and pc lengths are supported",
        ));
    }
    number(s)
}

pub(super) fn transform(s: &str) -> Result<Matrix, Error> {
    let mut rest = s.trim();
    let mut matrix = identity();
    let mut count = 0;
    while !rest.is_empty() {
        count += 1;
        if count > 64 {
            return Err(Error::new(
                "LIMIT_EXCEEDED",
                "At most 64 transforms per element",
            ));
        }
        let open = rest
            .find('(')
            .ok_or_else(|| invalid("Expected transform arguments"))?;
        let close = rest
            .find(')')
            .ok_or_else(|| invalid("Unclosed transform"))?;
        if close < open {
            return Err(invalid("Malformed transform"));
        }
        let name = rest[..open].trim();
        let n = list(&rest[open + 1..close])?;
        let next = match (name, n.as_slice()) {
            ("matrix", [a, b, c, d, e, f]) => [*a, *b, *c, *d, *e, *f],
            ("translate", [x]) => [1.0, 0.0, 0.0, 1.0, *x, 0.0],
            ("translate", [x, y]) => [1.0, 0.0, 0.0, 1.0, *x, *y],
            ("scale", [x]) => [*x, 0.0, 0.0, *x, 0.0, 0.0],
            ("scale", [x, y]) => [*x, 0.0, 0.0, *y, 0.0, 0.0],
            ("rotate", [a]) | ("rotate", [a, _, _]) => {
                let (sin, cos) = a.to_radians().sin_cos();
                let rotation = [cos, sin, -sin, cos, 0.0, 0.0];
                if n.len() == 3 {
                    geometry::multiply(
                        [1.0, 0.0, 0.0, 1.0, n[1], n[2]],
                        geometry::multiply(rotation, [1.0, 0.0, 0.0, 1.0, -n[1], -n[2]]),
                    )
                } else {
                    rotation
                }
            }
            ("skewX", [a]) => [1.0, 0.0, a.to_radians().tan(), 1.0, 0.0, 0.0],
            ("skewY", [a]) => [1.0, a.to_radians().tan(), 0.0, 1.0, 0.0, 0.0],
            _ => {
                return Err(unsupported(format!(
                    "Unsupported transform or arity: {name}"
                )));
            }
        };
        matrix = geometry::multiply(matrix, next);
        if matrix.iter().any(|v| !v.is_finite()) {
            return Err(invalid("Transform overflow"));
        }
        rest = rest[close + 1..].trim_start();
        if let Some(r) = rest.strip_prefix(',') {
            rest = r.trim_start();
            if rest.is_empty() {
                return Err(invalid("Trailing transform comma"));
            }
        }
    }
    Ok(matrix)
}

pub(super) fn path(s: &str) -> Result<Geometry, Error> {
    let ts = tokens(s)?;
    let mut i = 0;
    let mut active = 0u8;
    let mut current = [0.0; 2];
    let mut start = current;
    let mut cubic: Option<Point> = None;
    let mut quadratic: Option<Point> = None;
    let mut closed = false;
    let mut commands = Vec::new();
    while i < ts.len() {
        if let Token::Command(c) = ts[i] {
            active = c;
            i += 1;
        } else if active == 0 {
            return Err(invalid("Path requires a command"));
        }
        let op = active.to_ascii_uppercase();
        if commands.is_empty() && op != b'M' {
            return Err(invalid("Path must start with moveto"));
        }
        let count = match op {
            b'M' | b'L' | b'T' => 2,
            b'H' | b'V' => 1,
            b'C' => 6,
            b'S' | b'Q' => 4,
            b'Z' => 0,
            b'A' => return Err(unsupported("Elliptical path arcs are not yet supported")),
            _ => return Err(invalid("Unknown path command")),
        };
        let mut n = [0.0; 6];
        for value in n.iter_mut().take(count) {
            if let Some(Token::Number(v)) = ts.get(i) {
                *value = *v;
                i += 1;
            } else {
                return Err(invalid("Incomplete path parameter group"));
            }
        }
        let relative = active.is_ascii_lowercase();
        let p = |x: f64, y: f64| {
            if relative {
                [current[0] + x, current[1] + y]
            } else {
                [x, y]
            }
        };
        let mut next_cubic = None;
        let mut next_quad = None;
        if closed && op != b'M' && op != b'Z' {
            commands.push(PathCommand::Move { to: current });
        }
        let command = match op {
            b'M' => {
                let to = p(n[0], n[1]);
                current = to;
                start = to;
                active = if relative { b'l' } else { b'L' };
                PathCommand::Move { to }
            }
            b'L' | b'H' | b'V' => {
                let to = match op {
                    b'H' => [if relative { current[0] + n[0] } else { n[0] }, current[1]],
                    b'V' => [current[0], if relative { current[1] + n[0] } else { n[0] }],
                    _ => p(n[0], n[1]),
                };
                current = to;
                PathCommand::Line { to }
            }
            b'C' | b'S' => {
                let (control1, control2, to) = if op == b'C' {
                    (p(n[0], n[1]), p(n[2], n[3]), p(n[4], n[5]))
                } else {
                    (
                        cubic.map_or(current, |q| {
                            [2.0 * current[0] - q[0], 2.0 * current[1] - q[1]]
                        }),
                        p(n[0], n[1]),
                        p(n[2], n[3]),
                    )
                };
                next_cubic = Some(control2);
                current = to;
                PathCommand::Cubic {
                    control1,
                    control2,
                    to,
                }
            }
            b'Q' | b'T' => {
                let (q, to) = if op == b'Q' {
                    (p(n[0], n[1]), p(n[2], n[3]))
                } else {
                    (
                        quadratic.map_or(current, |q| {
                            [2.0 * current[0] - q[0], 2.0 * current[1] - q[1]]
                        }),
                        p(n[0], n[1]),
                    )
                };
                let control1 = [
                    current[0] + (q[0] - current[0]) * 2.0 / 3.0,
                    current[1] + (q[1] - current[1]) * 2.0 / 3.0,
                ];
                let control2 = [
                    to[0] + (q[0] - to[0]) * 2.0 / 3.0,
                    to[1] + (q[1] - to[1]) * 2.0 / 3.0,
                ];
                next_quad = Some(q);
                current = to;
                PathCommand::Cubic {
                    control1,
                    control2,
                    to,
                }
            }
            b'Z' => {
                if closed {
                    return Err(unsupported("Repeated close commands are not supported"));
                }
                current = start;
                active = 0;
                PathCommand::Close {}
            }
            _ => unreachable!(),
        };
        closed = op == b'Z';
        cubic = next_cubic;
        quadratic = next_quad;
        commands.push(command);
        if commands.len() > MAX_SEGMENTS {
            return Err(Error::new(
                "LIMIT_EXCEEDED",
                "SVG path command limit exceeded",
            ));
        }
    }
    Ok(Geometry::Path { commands })
}
