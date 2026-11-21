//! Paint a shaped cluster as one searchable character. The uncolored glyph
//! procedure reuses embedded font glyphs at their exact layout positions.
use super::*;
use std::fmt::Write;

pub(super) fn admit(group: &[PaintedGlyph<'_>]) -> Result<(), &'static str> {
    let mut colors = group.iter().filter_map(|p| p.paint);
    if let Some(color) = colors.next() {
        let opaque = match color {
            Paint::Solid(rgba) => rgba[3] == 255,
            Paint::Precise(color) => color.rgba[3] == 1.0,
            _ => false,
        };
        if !opaque || colors.any(|p| p != color) {
            return Err("cluster_paint");
        }
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
    let [w, h] = base.em_size;
    let [x, y] = base.path.as_ref().map_or([1.0, 0.0], |p| p.tangent);
    // Project onto the first glyph's tangent and normal, then undo its em scales.
    // Subtract its origin separately so placement on the page cancels out.
    let to_em = [x / w, y / h, y / w, -x / h, 0.0, 0.0];
    let to_units = to_em.map(|v| v * 1000.0);
    let offset = |point: Point| {
        geometry::map(
            to_units,
            [point[0] - base.origin[0], point[1] - base.origin[1]],
        )
    };
    let width = number(group.iter().map(|p| p.glyph.advance).sum::<f64>() * (1000.0 / w))?;
    let bounds = group
        .iter()
        .filter_map(|p| p.glyph.ink_bounds)
        .flat_map(|[l, t, r, b]| [[l, t], [l, b], [r, t], [r, b]])
        .map(|corner| {
            let [x, y] = offset(corner);
            [x, y, x, y]
        })
        .reduce(scene::union)
        .unwrap_or([0.0; 4]);
    let bbox = numbers(&bounds)?;
    let mut body = format!("{width} 0 {bbox} d1\nBT\n");
    let mut fonts = BTreeSet::new();
    for p in group {
        let glyph = p.glyph;
        let (font, code) = register(writer, glyph, source, kinds[glyph.font_id.as_str()])?;
        fonts.insert(font);
        let mut local = geometry::multiply(to_em, glyph_matrix(glyph));
        [local[4], local[5]] = offset(glyph.origin);
        writeln!(
            body,
            "/R{font} 1000 Tf\n{} Tm <{code}> Tj",
            numbers(&local)?
        )
        .unwrap();
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
