//! Close a native overprint against the artwork visible at group entry.
//! Its original geometry and alpha remain the knockout footprint.
use super::*;

#[derive(Clone)]
pub(super) struct Entry {
    form: usize,
    // Consecutive glyphs or shapes painted with the same ink cannot change
    // any plate the next invocation preserves.
    plane: Option<(crate::swatches::Reference, usize)>,
}

impl Entry {
    pub(super) fn new(form: usize) -> Self {
        Self { form, plane: None }
    }
    pub(super) fn invalidate(&mut self) {
        self.plane = None;
    }
}

pub(super) fn entries(
    doc: &Document,
    layouts: &BTreeMap<String, crate::text::Layout>,
    control: &crate::control::Control,
) -> Result<BTreeSet<usize>, Error> {
    let overprints = |p: &Paint| matches!(p, Paint::Named(r) if !r.overprint.is_knockout());
    let mut entries = BTreeSet::new();
    for (i, item) in doc.items.iter().enumerate() {
        control.check()?;
        let uses_ink = match &item.content {
            Content::Vector { fill, stroke, .. } => {
                fill.as_ref().is_some_and(overprints)
                    || stroke.as_ref().is_some_and(|s| overprints(&s.color))
            }
            Content::Fill { paint, .. } => overprints(paint),
            Content::Text { .. } | Content::StoryFrame { .. } => {
                layouts[&item.id].paths.iter().any(|p| overprints(&p.fill))
            }
            _ => false,
        };
        if !uses_ink || !scene::effective_visible(doc, i)? {
            continue;
        }
        let ancestors = scene::ancestors(doc, i)?;
        let through = ancestors
            .iter()
            .copied()
            .take_while(|&p| !doc.items[p].content.is_isolated());
        if through.clone().any(|p| doc.items[p].content.is_knockout()) {
            entries.insert(i);
            entries.extend(through);
        }
    }
    Ok(entries)
}

pub(super) fn snapshot(
    writer: &mut Writer,
    entry: Option<usize>,
    prefix: &Stream,
) -> Result<usize, Error> {
    if let Some(form) = entry
        && prefix.content.is_empty()
    {
        return Ok(form);
    }
    writer.charge_commands(prefix.path_commands)?;
    let mut combined = prefix.clone();
    if let Some(entry) = entry {
        let local = std::mem::take(&mut combined.content);
        combined.use_resource("XObject", entry, "Do");
        combined.content.push_str(&local);
    }
    writer.isolated_form(&combined)
}

pub(super) fn paint(
    writer: &mut Writer,
    stream: &mut Stream,
    shape: &Geometry,
    matrix: Matrix,
    rule: FillRule,
    reference: &crate::swatches::Reference,
) -> Result<(), Error> {
    // At full coverage the addressed plates take their new tints and every
    // other plate keeps its value at entry. Painting this closed result at
    // the original opacity interpolates both ink and alpha correctly, even
    // over a translucent entry or an external spot unknown to the new paint.
    let entry = stream.ink_entry.as_ref().expect("native overprint entry");
    let mut solid = reference.clone();
    solid.opacity = 1.;
    let source = if let Some((previous, plane)) = &entry.plane
        && *previous == solid
    {
        *plane
    } else {
        let backdrop = snapshot(writer, Some(entry.form), stream)?;
        let mut ink = Stream::default();
        ink.use_resource("XObject", backdrop, "Do");
        inks::paint(writer, &mut ink, &solid)?;
        writer.charge_commands(1)?;
        ink.content
            .push_str(&format!("{} re f\n", writer.page_bbox));
        let source = writer.isolated_form(&ink)?;
        stream.ink_entry.as_mut().unwrap().plane = Some((solid, source));
        source
    };
    stream.content.push_str("q\n");
    clip(writer, stream, shape, matrix, rule)?;
    graphics_state(writer, stream, reference.opacity, BlendMode::Normal)?;
    stream.use_resource("XObject", source, "Do");
    stream.content.push_str("Q\n");
    writer.external_overprints += 1;
    Ok(())
}
