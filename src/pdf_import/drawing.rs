use super::*;
use crate::geometry::{map, multiply};
use crate::model::{BlendMode, Clip, Content, FillRule, Geometry, Item, Matrix, identity};

pub(super) struct Drawing<'a> {
    pub pdf: &'a Container<'a>,
    pub page_index: usize,
    page_size: [f64; 2],
    pub control: &'a Control,
    pub profile: ResourceProfile,
    pub document: Document,
    pub fonts: text::Fonts,
    pub mapping: Vec<serde_json::Value>,
    pub images: image::Images,
    pub swatches: print::Swatches,
    pub painted_swatches: BTreeSet<String>,
    device_rgb_group: bool,
    device_cmyk_group: bool,
    first_display_or_transparent: Option<(Id, usize)>,
    pub used_indexed_fill: bool,
    pub used_text_setup: bool,
    active: BTreeSet<Id>,
    pub remaining_bytes: usize,
    pub operations: usize,
}
#[derive(Clone)]
pub(super) struct State {
    pub font: Option<Id>,
    pub font_size: f64,
    pub leading: f64,
    pub matrix: Matrix,
    pub values: [f64; 4],
    pub space: color::FillSpace,
    pub blend: BlendMode,
    pub alpha: f64,
    pub parent: Option<String>,
    depth: usize,
    clip_bounds: [f64; 4],
}
impl Drawing<'_> {
    pub fn group(&mut self, value: &Value) -> Result<bool, Error> {
        let d = self.pdf.resolve(value)?.dict()?;
        allowed(d, &[b"Type", b"S", b"CS", b"I", b"K"])?;
        if !field(d, b"S")?.named(b"Transparency")
            || d.get(b"Type".as_slice())
                .is_some_and(|v| !v.named(b"Group"))
        {
            return Err(unsupported(
                "Unsupported PDF transparency group color space or subtype",
            ));
        }
        if let Some(cs) = d.get(b"CS".as_slice()) {
            let cs = self.pdf.resolve(cs)?;
            if cs.named(b"DeviceRGB") {
                self.device_rgb_group = true;
            } else if cs.named(b"DeviceCMYK") {
                self.device_cmyk_group = true;
            } else {
                return Err(unsupported(
                    "Unsupported PDF transparency group color space",
                ));
            }
        }
        if matches!(d.get(b"K".as_slice()),Some(v) if !matches!(v,Value::Bool(false))) {
            return Err(unsupported(
                "PDF knockout groups cannot yet be reopened as editable artwork",
            ));
        }
        match d.get(b"I".as_slice()) {
            None | Some(Value::Bool(false)) => Ok(false),
            Some(Value::Bool(true)) => Ok(true),
            _ => Err(invalid("Invalid PDF group isolation")),
        }
    }
    pub fn native_page(&self) -> Result<bool, Error> {
        let native = self.device_cmyk_group || !self.painted_swatches.is_empty();
        if native {
            if let Some((id, offset)) = self.first_display_or_transparent {
                return Err(located(
                    unsupported(
                        "Native PDF fills require opaque normal process or spot artwork throughout the page",
                    ),
                    self.page_index,
                    id,
                    Some(offset),
                ));
            }
            if self.device_rgb_group {
                return Err(unsupported(
                    "Native PDF fills inside explicit RGB blending groups are unsupported",
                ));
            }
        }
        Ok(native)
    }
}

pub(super) fn resource<'a>(
    pdf: &'a Container,
    resources: &'a Dict,
    kind: &[u8],
    name: &[u8],
) -> Result<&'a Value, Error> {
    pdf.resolve(field(resources, kind)?)?
        .dict()?
        .get(name)
        .ok_or_else(|| invalid("Undefined PDF drawing resource"))
}
fn check_resources(pdf: &Container, resources: &Dict) -> Result<(), Error> {
    if let Some(cs) = resources.get(b"ColorSpace".as_slice()) {
        let cs = pdf.resolve(cs)?.dict()?;
        if [b"DefaultRGB".as_slice(), b"DefaultGray", b"DefaultCMYK"]
            .iter()
            .any(|k| cs.contains_key(*k))
        {
            return Err(unsupported(
                "Remapped device color spaces are unsupported in PDF import",
            ));
        }
    }
    Ok(())
}
impl<'a> Drawing<'a> {
    pub fn new(
        pdf: &'a Container<'a>,
        page_index: usize,
        page_size: [f64; 2],
        document: Document,
        fonts: text::Fonts,
        control: &'a Control,
    ) -> Self {
        Self {
            pdf,
            page_index,
            page_size,
            control,
            profile: document.resource_profile,
            document,
            fonts,
            mapping: vec![],
            images: Default::default(),
            swatches: Default::default(),
            painted_swatches: Default::default(),
            device_rgb_group: false,
            device_cmyk_group: false,
            first_display_or_transparent: None,
            used_indexed_fill: false,
            used_text_setup: false,
            active: BTreeSet::new(),
            remaining_bytes: vector_native::MAX_DECODED_BYTES,
            operations: 0,
        }
    }
    pub fn add(
        &mut self,
        parent: Option<String>,
        content: Content,
        clip: Option<Clip>,
        (opacity, blend): (f64, BlendMode),
        transform: Matrix,
        loc: (Id, usize),
    ) -> Result<String, Error> {
        if self.document.items.len() >= self.profile.items() {
            return Err(limit("PDF editable item limit exceeded"));
        }
        let id = format!("pdf-{}", self.document.items.len() + 1);
        let native_compatible = match &content {
            Content::Group { .. } => true,
            Content::Vector {
                fill: Some(crate::paint::Paint::Named(reference)),
                ..
            } => {
                self.painted_swatches.insert(reference.swatch.clone());
                reference.opacity == 1.
            }
            _ => false,
        };
        if !native_compatible || opacity != 1. || blend != BlendMode::Normal {
            self.first_display_or_transparent.get_or_insert(loc);
        }
        self.document.items.push(Item {
            hdr_grade: None,
            pixel_warp: None,
            metadata: None,
            id: id.clone(),
            name: String::new(),
            visible: true,
            locked: false,
            opacity,
            fill_opacity: 1.,
            knockout_target: Default::default(),
            coverage: Default::default(),
            effects: vec![],
            blend,
            transform,
            parent,
            clip_to: None,
            clip,
            mask: None,
            artwork_mask: None,
            filters: vec![],
            content,
        });
        self.mapping.push(
            json!({"item_id":id,"object":loc.0.0,"generation":loc.0.1,"decoded_byte_offset":loc.1}),
        );
        Ok(id)
    }
    pub fn enter_group(
        &mut self,
        state: &mut State,
        clip: Option<(Geometry, FillRule)>,
        isolated: bool,
        composite: (f64, BlendMode),
        loc: (Id, usize),
    ) -> Result<(), Error> {
        // Several form and path clips can share the fractional page edge.
        // Applying the same coverage twice would darken or fade that edge.
        let clip = clip.filter(|(geometry, _)| {
            let Some([l, b, r, t]) = rectangle_bounds(geometry) else {
                return true;
            };
            let [left, bottom, right, top] = state.clip_bounds;
            state.clip_bounds = [left.max(l), bottom.max(b), right.min(r), top.min(t)];
            !(l <= left && b <= bottom && r >= right && t >= top)
        });
        if clip.is_none() && !isolated && composite == (1., BlendMode::Normal) {
            return Ok(());
        }
        if state.depth >= bounds::MAX_DEPTH {
            return Err(limit("PDF clipping and form hierarchy depth exceeded"));
        }
        let id = self.add(
            state.parent.clone(),
            Content::Group {
                isolated,
                role: Default::default(),
                knockout: false,
            },
            clip.map(|(geometry, fill_rule)| Clip {
                geometry,
                fill_rule,
                transform: identity(),
                enabled: true,
            }),
            composite,
            identity(),
            loc,
        )?;
        state.depth += 1;
        state.parent = Some(id);
        Ok(())
    }
    fn decode(&mut self, id: Id) -> Result<Vec<u8>, Error> {
        let bytes = filters::stream(
            self.pdf,
            id,
            self.remaining_bytes,
            &mut self.remaining_bytes,
            self.control,
        )
        .map_err(|e| located(e, self.page_index, id, None))?;
        self.remaining_bytes -= bytes.len();
        Ok(bytes)
    }
    pub fn page(
        &mut self,
        contents: Option<&Value>,
        resources: &Dict,
        matrix: Matrix,
    ) -> Result<(), Error> {
        check_resources(self.pdf, resources)?;
        let Some(v) = contents else { return Ok(()) };
        let mut program = program::Program::default();
        let pdf = self.pdf;
        let streams = match v {
            Value::Array(streams) => streams.as_slice(),
            Value::Ref(id) if pdf.stream_dict(*id).is_err() => {
                let Value::Array(streams) = pdf.resolve(v)? else {
                    return Err(invalid("Expected PDF page contents"));
                };
                streams.as_slice()
            }
            _ => std::slice::from_ref(v),
        };
        for v in streams {
            let id = reference(v)?;
            let page = self.page_index;
            allowed(
                pdf.stream_dict(id)?,
                &[b"Length", b"Filter", b"DecodeParms"],
            )
            .map_err(|e| located(e, page, id, None))?;
            program.append(id, self.decode(id)?);
        }
        let state = State {
            font: None,
            font_size: 0.,
            leading: 0.,
            matrix,
            alpha: 1.,
            values: [0.; 4],
            space: color::FillSpace::Gray,
            blend: Default::default(),
            parent: None,
            depth: 0,
            clip_bounds: [0., 0., self.page_size[0], self.page_size[1]],
        };
        program.run(self, resources, state)
    }
    pub fn xobject(
        &mut self,
        resources: &Dict,
        name: &[u8],
        state: &State,
        loc: (Id, usize),
    ) -> Result<(), Error> {
        let pdf = self.pdf;
        let v = resource(pdf, resources, b"XObject", name)?;
        let id = reference(v)?;
        let d = pdf.stream_dict(id)?;
        if field(d, b"Subtype")?.named(b"Image") {
            let (content, dimensions) = self
                .images
                .placement(
                    pdf,
                    id,
                    &mut self.remaining_bytes,
                    self.profile,
                    self.control,
                    self.page_index,
                )
                .map_err(|e| located(e, self.page_index, id, None))?;
            let [w, h] = dimensions.map(f64::from);
            let transform = multiply(state.matrix, [1. / w, 0., 0., -1. / h, 0., 1.]);
            self.add(
                state.parent.clone(),
                content,
                None,
                (state.alpha, state.blend),
                transform,
                loc,
            )?;
            return Ok(());
        }
        if self.active.len() >= bounds::MAX_DEPTH || !self.active.insert(id) {
            return Err(limit("Repeated or deep PDF form invocation"));
        }
        if !field(d, b"Subtype")?.named(b"Form") {
            return Err(unsupported("Unsupported PDF XObject subtype"));
        }
        allowed(
            d,
            &[
                b"Type",
                b"Subtype",
                b"FormType",
                b"BBox",
                b"Matrix",
                b"Group",
                b"Resources",
                b"Length",
                b"Filter",
                b"DecodeParms",
                b"Metadata",
                b"Name",
            ],
        )?;
        if d.get(b"Type".as_slice())
            .is_some_and(|v| !v.named(b"XObject"))
            || d.get(b"FormType".as_slice())
                .is_some_and(|v| !matches!(v, Value::Integer(1)))
        {
            return Err(unsupported("Unsupported PDF form type"));
        }
        let mut next = state.clone();
        if let Some(m) = d.get(b"Matrix".as_slice()) {
            next.matrix = multiply(state.matrix, numbers(pdf, m)?);
        }
        let [l, b, r, t] = rect(pdf, field(d, b"BBox")?)?;
        let corners = [[l, b], [r, b], [r, t], [l, t]].map(|p| map(next.matrix, p));
        let is_group = d
            .get(b"Group".as_slice())
            .map(|v| self.group(v))
            .transpose()?;
        if is_group == Some(false) && state.blend != BlendMode::Normal {
            return Err(unsupported(
                "A nonisolated PDF transparency group with an invocation blend cannot be represented",
            ));
        }
        let composite = if is_group.is_some() {
            let composite = (next.alpha, next.blend);
            next.alpha = 1.;
            next.blend = Default::default();
            composite
        } else {
            (1., Default::default())
        };
        if corners.iter().flatten().any(|p| !p.is_finite()) {
            return Err(limit("PDF form bounds overflow"));
        }
        self.enter_group(
            &mut next,
            Some((
                Geometry::Polygon {
                    points: corners.to_vec(),
                },
                FillRule::Nonzero,
            )),
            is_group.unwrap_or(false),
            composite,
            loc,
        )?;
        let local = d
            .get(b"Resources".as_slice())
            .map(|v| pdf.resolve(v)?.dict())
            .transpose()?
            .unwrap_or(resources);
        check_resources(pdf, local)?;
        let mut program = program::Program::default();
        program.append(id, self.decode(id)?);
        program.run(self, local, next)?;
        self.active.remove(&id);
        Ok(())
    }
}

fn rectangle_bounds(geometry: &Geometry) -> Option<[f64; 4]> {
    use crate::model::PathCommand::{Close, Line, Move};
    let [a, b, c, d] = match geometry {
        Geometry::Polygon { points } => <[_; 4]>::try_from(points.as_slice()).ok()?,
        Geometry::Path { commands } => match commands.as_slice() {
            [
                Move { to: a },
                Line { to: b },
                Line { to: c },
                Line { to: d },
                Close {},
            ] => [*a, *b, *c, *d],
            _ => return None,
        },
        _ => return None,
    };
    let horizontal = a[1] == b[1] && b[0] == c[0] && c[1] == d[1] && d[0] == a[0];
    let vertical = a[0] == b[0] && b[1] == c[1] && c[0] == d[0] && d[1] == a[1];
    (horizontal || vertical).then(|| {
        [
            a[0].min(c[0]),
            a[1].min(c[1]),
            a[0].max(c[0]),
            a[1].max(c[1]),
        ]
    })
}

pub(super) fn graphics_state(
    pdf: &Container,
    resources: &Dict,
    name: &[u8],
    state: &mut State,
) -> Result<(), Error> {
    let d = pdf
        .resolve(resource(pdf, resources, b"ExtGState", name)?)?
        .dict()?;
    allowed(
        d,
        &[b"Type", b"ca", b"CA", b"BM", b"SMask", b"OP", b"op", b"OPM"],
    )?;
    for (key, v) in d {
        let v = pdf.resolve(v)?;
        match key.as_slice() {
            b"Type" if v.named(b"ExtGState") => {}
            b"ca" | b"CA" => {
                let n = number(v)?;
                if !(0. ..=1.).contains(&n) {
                    return Err(invalid("PDF alpha must be in range"));
                }
                if key == b"ca" {
                    state.alpha = n;
                }
            }
            b"BM" if v.named(b"Compatible") => state.blend = Default::default(),
            b"BM" => {
                state.blend = crate::blending::MODES
                    .into_iter()
                    .find(|mode| {
                        crate::pdf::blend_name(*mode).is_some_and(|name| v.named(name.as_bytes()))
                    })
                    .ok_or_else(|| unsupported("Unsupported PDF blend mode"))?;
                if matches!(state.blend, BlendMode::ColorBurn | BlendMode::ColorDodge)
                    && !pdf.declares_pdf_2()?
                {
                    return Err(unsupported(
                        "PDF color burn and color dodge require the PDF 2.0 endpoint rules",
                    ));
                }
            }
            b"SMask" if v.named(b"None") => {}
            b"OP" | b"op" if matches!(v, Value::Bool(false)) => {}
            b"OPM" if matches!(v, Value::Integer(0)) => {}
            _ => {
                return Err(unsupported(&format!(
                    "Unsupported PDF graphics state /{}",
                    String::from_utf8_lossy(key)
                )));
            }
        }
    }
    Ok(())
}
