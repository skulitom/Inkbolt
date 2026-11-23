use super::{
    drawing::{Drawing, State},
    *,
};
use crate::{
    geometry::{map, multiply},
    model::{Content, FillRule, Geometry, PathCommand, Point},
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
pub(super) fn scalar(token: &[u8]) -> Result<f64, Error> {
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
            in_text: false,
            text_matrix: crate::model::identity(),
            line_matrix: crate::model::identity(),
            painted_text: false,
        };
        let mut at = 0;
        let mut operands = Vec::new();
        let mut text_operand = None;
        let mut text_nodes = 0;
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
            if matches!(c, b'(' | b'<' | b'[') && self.bytes.get(start..start + 2) != Some(b"<<") {
                if !execution.in_text || text_operand.is_some() || !operands.is_empty() {
                    return Err(fail(unsupported("Unsupported PDF text operand")));
                }
                at = start;
                text_operand = Some(
                    vector_native::pdf_read::object_at(
                        &self.bytes,
                        &mut at,
                        &mut text_nodes,
                        drawing.control,
                    )
                    .map_err(fail)?,
                );
                continue;
            }
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
                if text_operand.is_some() {
                    return Err(fail(invalid("Unexpected operand after a PDF text operand")));
                }
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
            if text_operand.is_some() && !matches!(token, b"Tj" | b"TJ") {
                return Err(fail(unsupported("Unsupported PDF text-showing operator")));
            }
            execution
                .step(
                    drawing,
                    resources,
                    token,
                    &operands,
                    text_operand.take().as_ref(),
                    loc,
                )
                .map_err(|e| located(e, page, loc.0, Some(loc.1)))?;
            operands.clear();
        }
        if text_operand.is_some()
            || !operands.is_empty()
            || !execution.saved.is_empty()
            || !execution.path.is_empty()
            || execution.clip.is_some()
            || execution.in_text
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
    in_text: bool,
    text_matrix: crate::model::Matrix,
    line_matrix: crate::model::Matrix,
    painted_text: bool,
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
        text_operand: Option<&Value>,
        loc: (Id, usize),
    ) -> Result<(), Error> {
        if self.clip.is_some() && !matches!(op, b"f" | b"F" | b"f*" | b"n") {
            return Err(unsupported(
                "PDF clipping must be followed by an admitted path ending",
            ));
        }
        if self.in_text {
            match op {
                b"ET" => {
                    args::<0>(operands)?;
                    self.in_text = false;
                    d.used_text_setup |= !self.painted_text;
                }
                b"Tf" => {
                    let [font, size] = operands else {
                        return Err(invalid("Expected a PDF font name and size"));
                    };
                    let font = drawing::resource(d.pdf, resources, b"Font", &name(&[*font])?)?;
                    let dict = d.pdf.resolve(font)?.dict()?;
                    if !d.pdf.resolve(field(dict, b"Type")?)?.named(b"Font") {
                        return Err(invalid("Expected a PDF font resource"));
                    }
                    self.state.font = match font {
                        Value::Ref(id) => Some(*id),
                        _ => None,
                    };
                    self.state.font_size = scalar(size)?;
                }
                b"TL" => {
                    self.state.leading = args::<1>(operands)?[0];
                }
                b"Tm" => {
                    self.text_matrix = args(operands)?;
                    self.line_matrix = self.text_matrix;
                }
                b"Td" | b"TD" | b"T*" => {
                    let [x, y] = if op == b"T*" {
                        args::<0>(operands)?;
                        [0., -self.state.leading]
                    } else {
                        args(operands)?
                    };
                    if op == b"TD" {
                        self.state.leading = -y;
                    }
                    self.line_matrix = multiply(self.line_matrix, [1., 0., 0., 1., x, y]);
                    self.text_matrix = self.line_matrix;
                }
                b"Tj" | b"TJ" => {
                    args::<0>(operands)?;
                    let parts = match (op, text_operand) {
                        (b"Tj", Some(value @ Value::Bytes(_))) => std::slice::from_ref(value),
                        (b"TJ", Some(Value::Array(parts))) => parts.as_slice(),
                        _ => return Err(invalid("Tj requires a string and TJ requires an array")),
                    };
                    for part in parts {
                        d.control.check()?;
                        let advance = match part {
                            Value::Bytes(bytes) => {
                                self.painted_text |= !bytes.is_empty();
                                d.show_text(&self.state, self.text_matrix, bytes, loc)?
                            }
                            Value::Integer(_) | Value::Real(_) => {
                                // Horizontal writing, with default text scaling.
                                -number(part)? * (self.state.font_size / 1000.)
                            }
                            _ => return Err(invalid("TJ accepts only strings and numbers")),
                        };
                        self.text_matrix =
                            multiply(self.text_matrix, [1., 0., 0., 1., advance, 0.]);
                        if !self.text_matrix.iter().all(|v| v.is_finite()) {
                            return Err(limit("PDF text matrix overflow"));
                        }
                    }
                }
                _ => {
                    return Err(unsupported(
                        "Unsupported operator in editable PDF text object",
                    ));
                }
            }
            return Ok(());
        }
        match op {
            b"BT" => {
                args::<0>(operands)?;
                if !self.path.is_empty() {
                    return Err(invalid("PDF text object inside an unfinished path"));
                }
                self.in_text = true;
                self.text_matrix = crate::model::identity();
                self.line_matrix = self.text_matrix;
                self.painted_text = false;
            }
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
                        d.used_indexed_fill |=
                            matches!(self.state.space, color::FillSpace::Indexed(_));
                        let paint = self.state.space.paint(
                            self.state.values,
                            self.state.alpha,
                            &mut d.swatches,
                        )?;
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
                            (1., self.state.blend),
                            crate::model::identity(),
                            loc,
                        )?;
                    }
                    if let Some(rule) = clip_rule {
                        d.enter_group(
                            &mut self.state,
                            Some((Geometry::Path { commands }, rule)),
                            false,
                            (1., Default::default()),
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
                self.state.space = color::FillSpace::select(
                    d.pdf,
                    resources,
                    &cs,
                    &mut d.swatches,
                    &mut d.remaining_bytes,
                    d.control,
                )?;
                self.state.values = self.state.space.initial();
            }
            b"rg" | b"g" | b"k" | b"sc" | b"scn" => {
                match op {
                    b"g" => self.state.space = color::FillSpace::Gray,
                    b"rg" => self.state.space = color::FillSpace::Rgb,
                    b"k" => self.state.space = color::FillSpace::Cmyk,
                    _ => {}
                }
                let values = match &self.state.space {
                    color::FillSpace::Gray
                    | color::FillSpace::Indexed(_)
                    | color::FillSpace::Spot(_) => [args::<1>(operands)?[0], 0., 0., 0.],
                    color::FillSpace::Cmyk => args::<4>(operands)?,
                    color::FillSpace::Rgb => {
                        let [r, g, b] = args(operands)?;
                        [r, g, b, 0.]
                    }
                };
                if !matches!(self.state.space, color::FillSpace::Indexed(_))
                    && values.iter().any(|v| !(0. ..=1.).contains(v))
                {
                    return Err(unsupported("PDF color components outside the unit range"));
                }
                self.state.values = values;
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
