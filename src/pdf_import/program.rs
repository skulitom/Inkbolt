use super::{
    drawing::{Drawing, State},
    *,
};
use crate::{
    geometry::{map, multiply},
    model::{Content, FillRule, Geometry, PathCommand, Point},
    paint::{Paint, Precise},
};

#[derive(Default)]
pub(super) struct Program {
    bytes: Vec<u8>,
    starts: Vec<(usize, Id)>,
}
fn space(b: u8) -> bool {
    matches!(b, 0 | 9 | 10 | 12 | 13 | 32)
}
fn delimiter(b: u8) -> bool {
    space(b) || b"()<>[]{}/%".contains(&b)
}
fn scalar(token: &[u8]) -> Result<f64, Error> {
    let digits = token
        .strip_prefix(b"+")
        .or_else(|| token.strip_prefix(b"-"))
        .unwrap_or(token);
    if digits.is_empty() || !digits.iter().all(|b| b.is_ascii_digit() || *b == b'.') {
        return Err(invalid("Invalid PDF drawing number"));
    }
    std::str::from_utf8(token)
        .ok()
        .and_then(|s| s.parse::<f64>().ok())
        .filter(|v| v.is_finite())
        .ok_or_else(|| invalid("Invalid PDF drawing number"))
}
fn args<const N: usize>(tokens: &[&[u8]]) -> Result<[f64; N], Error> {
    if tokens.len() != N {
        return Err(invalid("Wrong PDF operator operand count"));
    }
    let mut values = [0.; N];
    for (out, v) in values.iter_mut().zip(tokens) {
        *out = scalar(v)?;
    }
    Ok(values)
}
fn name(tokens: &[&[u8]]) -> Result<Vec<u8>, Error> {
    let [token] = tokens else {
        return Err(invalid("Expected one PDF resource name"));
    };
    let mut text = token
        .strip_prefix(b"/")
        .ok_or_else(|| invalid("Expected PDF name operand"))?;
    let mut result = Vec::new();
    while let Some((&c, rest)) = text.split_first() {
        if c == b'#' {
            let (pair, tail) = rest
                .split_at_checked(2)
                .ok_or_else(|| invalid("Incomplete PDF name escape"))?;
            let value = std::str::from_utf8(pair)
                .ok()
                .and_then(|s| u8::from_str_radix(s, 16).ok())
                .filter(|v| *v != 0)
                .ok_or_else(|| invalid("Invalid PDF name escape"))?;
            result.push(value);
            text = tail;
        } else {
            result.push(c);
            text = rest;
        }
        if result.len() > bounds::MAX_NAME_BYTES {
            return Err(limit("PDF resource name limit exceeded"));
        }
    }
    Ok(result)
}

impl Program {
    pub fn append(&mut self, id: Id, bytes: Vec<u8>) {
        // A page Contents array is one program, including its path and graphics stack.
        if !bytes.is_empty() {
            // Stream boundaries separate lexical tokens but do not end a comment.
            if !self.bytes.is_empty() {
                self.bytes.push(b' ');
            }
            self.starts.push((self.bytes.len(), id));
            self.bytes.extend(bytes);
        }
    }
    fn location(&self, at: usize) -> (Id, usize) {
        let (start, id) = self.starts[self.starts.partition_point(|(p, _)| *p <= at) - 1];
        (id, at - start)
    }
    pub fn run(&self, drawing: &mut Drawing, resources: &Dict, state: State) -> Result<(), Error> {
        let mut execution = Execution {
            state,
            saved: vec![],
            path: vec![],
            current: None,
            start: None,
            clip: None,
        };
        let mut at = 0;
        let mut operands = Vec::new();
        while let Some(&c) = self.bytes.get(at) {
            if space(c) {
                at += 1;
                continue;
            }
            if c == b'%' {
                at += 1;
                while self
                    .bytes
                    .get(at)
                    .is_some_and(|b| !matches!(b, b'\r' | b'\n'))
                {
                    at += 1;
                }
                continue;
            }
            let start = at;
            at += 1;
            let loc = self.location(start);
            let fail = |e| located(e, drawing.page_index, loc.0, Some(loc.1));
            if c != b'/' && delimiter(c) {
                return Err(fail(unsupported(
                    "Unsupported PDF drawing operand or delimiter",
                )));
            }
            while self.bytes.get(at).is_some_and(|b| !delimiter(*b)) {
                at += 1;
            }
            let token = &self.bytes[start..at];
            if token.len()
                > if c == b'/' {
                    3 * bounds::MAX_NAME_BYTES + 1
                } else {
                    bounds::MAX_TOKEN_BYTES
                }
            {
                return Err(fail(limit("PDF content token limit exceeded")));
            }
            if c == b'/' || c.is_ascii_digit() || matches!(c, b'.' | b'+' | b'-') {
                if operands.len() >= crate::limits::vector_native::MAX_OPERANDS {
                    return Err(fail(limit("PDF drawing operand limit exceeded")));
                }
                operands.push(token);
                continue;
            }
            drawing.control.check()?;
            drawing.operations += 1;
            if drawing.operations > crate::limits::pdf::MAX_COMMANDS {
                return Err(fail(limit("PDF drawing operation limit exceeded")));
            }
            let page = drawing.page_index;
            execution
                .step(drawing, resources, token, &operands, loc)
                .map_err(|e| located(e, page, loc.0, Some(loc.1)))?;
            operands.clear();
        }
        if !operands.is_empty()
            || !execution.saved.is_empty()
            || !execution.path.is_empty()
            || execution.clip.is_some()
        {
            let (id, offset) = self.location(self.bytes.len());
            return Err(located(
                invalid("Unfinished PDF drawing or graphics state"),
                drawing.page_index,
                id,
                Some(offset),
            ));
        }
        Ok(())
    }
}

struct Execution {
    state: State,
    saved: Vec<State>,
    path: Vec<PathCommand>,
    current: Option<Point>,
    start: Option<Point>,
    clip: Option<FillRule>,
}
impl Execution {
    fn point(&self, x: f64, y: f64) -> Result<Point, Error> {
        let p = map(self.state.matrix, [x, y]);
        if p.iter()
            .any(|c| !c.is_finite() || c.abs() > crate::model::MAX_COORDINATE)
        {
            return Err(limit("PDF path point exceeds document coordinate bounds"));
        }
        Ok(p)
    }
    fn move_to(&mut self, p: Point) {
        self.path.push(PathCommand::Move { to: p });
        self.current = Some(p);
        self.start = Some(p);
    }
    fn line_to(&mut self, p: Point) {
        self.path.push(PathCommand::Line { to: p });
        self.current = Some(p);
    }
    fn close(&mut self) {
        self.path.push(PathCommand::Close {});
        self.current = self.start;
    }
    fn step(
        &mut self,
        d: &mut Drawing,
        resources: &Dict,
        op: &[u8],
        operands: &[&[u8]],
        loc: (Id, usize),
    ) -> Result<(), Error> {
        if self.clip.is_some() && !matches!(op, b"f" | b"F" | b"f*" | b"n") {
            return Err(unsupported(
                "PDF clipping must be followed by an admitted path ending",
            ));
        }
        match op {
            b"m" => {
                let [x, y] = args(operands)?;
                self.move_to(self.point(x, y)?);
            }
            b"re" => {
                let [x, y, w, h] = args(operands)?;
                self.move_to(self.point(x, y)?);
                for [a, b] in [[x + w, y], [x + w, y + h], [x, y + h]] {
                    self.line_to(self.point(a, b)?);
                }
                self.close();
            }
            b"l" | b"c" | b"v" | b"y" | b"h" => {
                let current = self
                    .current
                    .ok_or_else(|| invalid("PDF path requires a current point"))?;
                match op {
                    b"l" => {
                        let [x, y] = args(operands)?;
                        self.line_to(self.point(x, y)?);
                    }
                    b"h" => {
                        args::<0>(operands)?;
                        self.close();
                    }
                    _ => {
                        let (control1, control2, to) = if op == b"c" {
                            let [a, b, c, e, x, y] = args(operands)?;
                            (self.point(a, b)?, self.point(c, e)?, self.point(x, y)?)
                        } else {
                            let [a, b, x, y] = args(operands)?;
                            let p = self.point(a, b)?;
                            let to = self.point(x, y)?;
                            if op == b"v" {
                                (current, p, to)
                            } else {
                                (p, to, to)
                            }
                        };
                        self.path.push(PathCommand::Cubic {
                            control1,
                            control2,
                            to,
                        });
                        self.current = Some(to);
                    }
                }
            }
            b"W" | b"W*" => {
                args::<0>(operands)?;
                if self.path.is_empty() {
                    return Err(unsupported("Empty PDF clip"));
                }
                self.clip = Some(rule(op));
            }
            b"f" | b"F" | b"f*" | b"n" => {
                args::<0>(operands)?;
                if !self.path.is_empty() {
                    let mut commands = std::mem::take(&mut self.path);
                    let clip_rule = self.clip.take();
                    if op != b"n" {
                        let [r, g, b] = self.state.rgb;
                        let rgba = [r, g, b, self.state.alpha];
                        let bytes = rgba.map(|v| (v * 255.).round() as u8);
                        let paint = if bytes.map(|v| f64::from(v) / 255.) == rgba {
                            Paint::Solid(bytes)
                        } else {
                            Paint::Precise(Precise { rgba })
                        };
                        d.add(
                            self.state.parent.clone(),
                            Content::Vector {
                                geometry: Geometry::Path {
                                    commands: if clip_rule.is_some() {
                                        commands.clone()
                                    } else {
                                        std::mem::take(&mut commands)
                                    },
                                },
                                fill: Some(paint),
                                stroke: None,
                                fill_rule: rule(op),
                            },
                            None,
                            1.,
                            crate::model::identity(),
                            loc,
                        )?;
                    }
                    if let Some(rule) = clip_rule {
                        d.enter_group(
                            &mut self.state,
                            Some((Geometry::Path { commands }, rule)),
                            false,
                            1.,
                            loc,
                        )?;
                    }
                }
                self.current = None;
                self.start = None;
            }
            _ if !self.path.is_empty() => {
                return Err(unsupported(&format!(
                    "Unsupported PDF operator {} within a path",
                    String::from_utf8_lossy(op)
                )));
            }
            b"q" => {
                args::<0>(operands)?;
                if self.saved.len() >= bounds::MAX_DEPTH {
                    return Err(limit("PDF graphics stack limit exceeded"));
                }
                self.saved.push(self.state.clone());
            }
            b"Q" => {
                args::<0>(operands)?;
                self.state = self
                    .saved
                    .pop()
                    .ok_or_else(|| invalid("Unmatched graphics restore"))?;
            }
            b"cm" => {
                self.state.matrix = multiply(self.state.matrix, args(operands)?);
                if !self.state.matrix.iter().all(|v| v.is_finite()) {
                    return Err(limit("PDF matrix overflow"));
                }
            }
            b"cs" => {
                let cs = name(operands)?;
                self.state.gray_space = match cs.as_slice() {
                    b"DeviceRGB" => false,
                    b"DeviceGray" => true,
                    _ => return Err(unsupported("Unsupported PDF fill color space")),
                };
                self.state.rgb = [0.; 3];
            }
            b"rg" | b"g" | b"sc" | b"scn" => {
                let gray = op == b"g" || (matches!(op, b"sc" | b"scn") && self.state.gray_space);
                let rgb = if gray {
                    [args::<1>(operands)?[0]; 3]
                } else {
                    args::<3>(operands)?
                };
                if rgb.iter().any(|v| !(0. ..=1.).contains(v)) {
                    return Err(unsupported("PDF color components outside the unit range"));
                }
                self.state.rgb = rgb;
                self.state.gray_space = gray;
            }
            b"gs" => drawing::graphics_state(d.pdf, resources, &name(operands)?, &mut self.state)?,
            b"Do" => d.xobject(resources, &name(operands)?, &self.state, loc)?,
            _ => {
                return Err(unsupported(&format!(
                    "Unsupported PDF drawing operator {}",
                    String::from_utf8_lossy(op)
                )));
            }
        }
        if self.path.len() > d.profile.commands() {
            return Err(limit("PDF editable path segment limit exceeded"));
        }
        Ok(())
    }
}
fn rule(op: &[u8]) -> FillRule {
    if op.ends_with(b"*") {
        FillRule::EvenOdd
    } else {
        FillRule::Nonzero
    }
}
