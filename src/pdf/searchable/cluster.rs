//! Paint a shaped cluster as one searchable character. The uncolored glyph
//! procedure reuses embedded font glyphs at their exact layout positions.
use super::*;
use std::fmt::Write;

pub(super) fn admit(group: &[PaintedGlyph<'_>]) -> Result<(), &'static str> {
    let first = group[0].glyph;
    if group
        .iter()
        .any(|p| p.glyph.path.is_some() || p.glyph.em_size != first.em_size)
    {
        return Err("cluster_baseline_or_scale");
    }
    let mut colors = group.iter().filter_map(|p| p.paint);
    if let Some(color) = colors.next()
        && (!matches!(color, Paint::Solid([_, _, _, 255])) || colors.any(|p| p != color))
    {
        return Err("cluster_paint");
    }
    Ok(())
}

pub(super) fn font(
    writer: &mut Writer,
    group: &[PaintedGlyph<'_>],
    source: &str,
    kinds: &BTreeMap<&str, Kind>,
) -> Result<usize, Error> {
    let base = group[0].glyph;
    let x_scale = 1000.0 / base.em_size[0];
    let y_scale = 1000.0 / base.em_size[1];
    let width = number(group.iter().map(|p| p.glyph.advance).sum::<f64>() * x_scale)?;
    let extent = group
        .iter()
        .filter_map(|p| p.glyph.ink_bounds)
        .reduce(crate::scene::union);
    let bounds = extent.map_or([0.0; 4], |[left, top, right, bottom]| {
        [
            (left - base.origin[0]) * x_scale,
            (base.origin[1] - bottom) * y_scale,
            (right - base.origin[0]) * x_scale,
            (base.origin[1] - top) * y_scale,
        ]
    });
    let bbox = numbers(&bounds)?;
    let mut body = format!("{width} 0 {bbox} d1\nBT\n");
    let mut fonts = BTreeSet::new();
    for p in group {
        let glyph = p.glyph;
        let (font, code) = register(writer, glyph, source, kinds[glyph.font_id.as_str()])?;
        fonts.insert(font);
        let x = number((glyph.origin[0] - base.origin[0]) * x_scale)?;
        let y = number((base.origin[1] - glyph.origin[1]) * y_scale)?;
        writeln!(body, "/R{font} 1000 Tf\n1 0 0 1 {x} {y} Tm <{code}> Tj").unwrap();
    }
    body.push_str("ET\n");
    let key = (body, source.to_owned());
    if let Some(id) = writer.text.clusters.get(&key) {
        return Ok(*id);
    }
    let procedure = writer.content_stream("", key.0.as_bytes())?;
    let map = program::cmap(
        writer,
        GLYPH_COLLECTION,
        2,
        true,
        &[format!("<01> <{}>", utf16(source))],
    )?;
    let resources = fonts
        .into_iter()
        .map(|id| format!("/R{id} {id} 0 R"))
        .collect::<Vec<_>>()
        .join(" ");
    let id = writer.add(format!(
        "<< /Type /Font /Subtype /Type3 /FontBBox [{bbox}] /FontMatrix [.001 0 0 .001 0 0] \
         /CharProcs << /Cluster {procedure} 0 R >> /Encoding << /Type /Encoding /Differences [1 /Cluster] >> \
         /FirstChar 1 /LastChar 1 /Widths [{width}] /Resources << /Font << {resources} >> >> /ToUnicode {map} 0 R >>"
    ))?;
    writer.text.clusters.insert(key, id);
    Ok(id)
}
