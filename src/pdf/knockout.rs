use super::*;

/// A faded item needs an independent footprint through every ancestor up to
/// the last one that can cut out earlier siblings. A first member's ordinary
/// paint is sufficient unless an enclosing group needs its footprint.
pub(super) fn footprint_unions(
    document: &Document,
    control: &crate::control::Control,
) -> Result<BTreeSet<usize>, Error> {
    let mut unions = BTreeSet::new();
    let groups: BTreeSet<_> = document
        .items
        .iter()
        .filter(|i| i.content.is_knockout())
        .map(|i| i.id.as_str())
        .collect();
    if !groups.is_empty() {
        let mut seen = BTreeSet::new();
        let mut members_with_prior = BTreeSet::new();
        for (index, item) in document.items.iter().enumerate() {
            if let Some(parent) = item.parent.as_deref()
                && groups.contains(parent)
                && item.visible
                && !matches!(
                    item.content,
                    Content::WorkPath { .. }
                        | Content::MaskSource {}
                        | Content::ComponentSource { .. }
                )
                && !seen.insert(parent)
            {
                members_with_prior.insert(index);
            }
        }
        for (index, item) in document.items.iter().enumerate() {
            control.check()?;
            if (item.opacity == 1.0 && item.fill_opacity == 1.0)
                || !scene::effective_visible(document, index)?
                || matches!(item.content, Content::WorkPath { .. })
            {
                continue;
            }
            let parents = scene::ancestors(document, index)?;
            if let Some(end) = parents.iter().rposition(|i| members_with_prior.contains(i)) {
                unions.extend(&parents[..=end]);
            }
        }
    }
    Ok(unions)
}

pub(super) fn draw(
    writer: &mut Writer,
    target: &mut Stream,
    form: usize,
    opacity: f64,
    mask: Option<usize>,
) -> Result<(), Error> {
    target.content.push_str("q\n");
    graphics_state(writer, target, opacity, BlendMode::Normal)?;
    if let Some(state) = mask {
        target.use_resource("ExtGState", state, "gs");
    }
    target.use_resource("XObject", form, "Do");
    target.content.push_str("Q\n");
    Ok(())
}

pub(super) fn masked_form(
    writer: &mut Writer,
    form: usize,
    opacity: f64,
    mask: Option<usize>,
) -> Result<usize, Error> {
    if opacity == 1.0 && mask.is_none() {
        return Ok(form);
    }
    let mut masked = Stream {
        default_rgb: writer.default_rgb,
        ..Stream::default()
    };
    graphics_state(writer, &mut masked, opacity, BlendMode::Normal)?;
    if let Some(state) = mask {
        masked.use_resource("ExtGState", state, "gs");
    }
    masked.use_resource("XObject", form, "Do");
    writer.isolated_form(&masked)
}

fn alpha_mask(writer: &mut Writer, form: usize) -> Result<usize, Error> {
    writer.mask_state(
        format!("<< /Type /ExtGState /SMask << /S /Alpha /G {form} 0 R >> >>"),
        form,
    )
}

fn survival_mask(writer: &mut Writer, shape: usize, paint: usize) -> Result<usize, Error> {
    // Over opaque gray, ColorDodge(1-F,A) = min(1,(1-F)/(1-A)).
    // At A=1 the upper paint hides the previous color. At F=1,A<1
    // the precise PDF 2.0 endpoint is zero. Gray avoids any color conversion.
    let f = alpha_mask(writer, shape)?;
    let a = alpha_mask(writer, paint)?;
    let page = format!("{} re f\n", writer.page_bbox);
    let mut gray = Stream::default();
    gray.content.push_str(&format!("0 g {page}q\n"));
    gray.use_resource("ExtGState", a, "gs");
    gray.content.push_str(&format!("1 g {page}Q\n"));
    let alpha = opacity::gray_form(writer, &gray)?;
    let mut ratio = Stream::default();
    ratio.content.push_str(&format!("1 g {page}q\n"));
    ratio.use_resource("ExtGState", f, "gs");
    ratio.content.push_str(&format!("0 g {page}Q\n"));
    let dodge = writer.add("<< /Type /ExtGState /BM /ColorDodge >>")?;
    ratio.use_resource("ExtGState", dodge, "gs");
    ratio.use_resource("XObject", alpha, "Do");
    writer.knockout_field_masks += 1;
    opacity::field(writer, ratio, crate::artwork_masks::Mode::Luminance, 1.0)?.state(writer, 1.0)
}

fn uniform_survival_mask(
    writer: &mut Writer,
    footprint: usize,
    opacity: f64,
) -> Result<usize, Error> {
    // With uniform owner opacity p, a single-input transfer computes (1-f)/(1-p*f).
    let program = format!(
        "{{ dup 1 ge {{ pop 0 }} {{ dup 1 exch sub exch {} mul 1 exch sub div }} ifelse }}",
        number(opacity)?
    );
    let transfer = writer.stream(
        "/FunctionType 4 /Domain [0 1] /Range [0 1]",
        program.as_bytes(),
    )?;
    writer.mask_state(
        format!(
            "<< /Type /ExtGState /SMask << /S /Alpha /G {footprint} 0 R /TR {transfer} 0 R >> >>"
        ),
        footprint,
    )
}

pub(super) struct Group {
    prior: Stream,
    depth: usize,
}

impl Group {
    pub(super) fn new(writer: &Writer, depth: usize) -> Self {
        Self {
            prior: Stream {
                default_rgb: writer.default_rgb,
                ..Stream::default()
            },
            depth,
        }
    }

    pub(super) fn add(
        &mut self,
        writer: &mut Writer,
        mut form: usize,
        shape: Option<usize>,
        mut opacity: f64,
    ) -> Result<(), Error> {
        if (shape.is_some() || opacity < 1.0) && !self.prior.content.is_empty() {
            self.depth += 1;
            if self.depth > crate::limits::pdf::MAX_KNOCKOUT_DEPTH {
                return Err(limit(
                    "PDF knockout composition exceeds the supported form nesting depth",
                ));
            }
            // Source-over retains (1-A) of the preceding siblings. Scale them
            // first so that the final survival is (1-F) for this footprint.
            let mask = if let Some(footprint) = shape.filter(|_| opacity > 0.0) {
                form = masked_form(writer, form, opacity, None)?;
                opacity = 1.0;
                survival_mask(writer, footprint, form)?
            } else {
                uniform_survival_mask(writer, shape.unwrap_or(form), opacity)?
            };
            let prefix = writer.isolated_form(&self.prior)?;
            self.prior = Stream {
                default_rgb: writer.default_rgb,
                ..Stream::default()
            };
            self.prior.content.push_str("q\n");
            self.prior.use_resource("ExtGState", mask, "gs");
            self.prior.use_resource("XObject", prefix, "Do");
            self.prior.content.push_str("Q\n");
        }
        if opacity > 0.0 {
            draw(writer, &mut self.prior, form, opacity, None)?;
        }
        Ok(())
    }

    pub(super) fn finish(self, writer: &mut Writer, output: &mut Stream) -> Result<(), Error> {
        let form = writer.isolated_form(&self.prior)?;
        output.use_resource("XObject", form, "Do");
        writer.knockout_groups += 1;
        writer.page_requires_backdrop = true;
        Ok(())
    }
}
