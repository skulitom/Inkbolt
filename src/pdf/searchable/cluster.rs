//! Paint a shaped cluster as one searchable character using its embedded glyphs.
use super::*;
use std::fmt::Write;

fn opaque(paint: &Paint) -> bool {
    match paint {
        Paint::Solid(rgba) => rgba[3] == 255,
        Paint::Precise(color) => color.rgba[3] == 1.0,
        _ => false,
    }
}

pub(super) fn intrinsic_color(group: &[PaintedGlyph<'_>]) -> bool {
    let mut colors = group.iter().filter_map(|p| p.paint);
    let Some(first) = colors.next() else {
        return false;
    };
    !opaque(first) || colors.any(|p| p != first)
}

pub(super) fn font(
    writer: &mut Writer,
    group: &[PaintedGlyph<'_>],
    source: &str,
    kinds: &BTreeMap<&str, Kind>,
    parent: &Stream,
    colored: bool,
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
    let [left, bottom, right, top] = bounds;
    let bbox = if colored {
        numbers(&[left.floor(), bottom.floor(), right.ceil(), top.ceil()])?
    } else {
        numbers(&bounds)?
    };
    let mut glyphs = Vec::with_capacity(group.len());
    for p in group {
        let glyph = p.glyph;
        let (font, code) = register(writer, glyph, source, kinds[glyph.font_id.as_str()])?;
        let mut local = geometry::multiply(to_em, glyph_matrix(glyph));
        [local[4], local[5]] = offset(glyph.origin);
        let show = format!("{} Tm <{code}> Tj", numbers(&local)?);
        glyphs.push((font, show, p.paint.filter(|_| colored)));
    }
    // Key the drawing before allocating paint resources. Repeated accents at
    // different page positions share the relative glyph motions and paint.
    let scope = colored.then_some((parent.default_rgb, parent.scalar_artwork));
    // d1 includes its bounding box in the glyph procedure. A d0 procedure
    // draws solely from its positioned glyphs. The conservative box can vary
    // with page-space rounding even when those instructions are identical.
    let identity = serde_json::to_string(&(&width, (!colored).then_some(&bbox), scope, &glyphs))
        .map_err(|_| Error::new("EXPORT_ERROR", "Unable to serialize PDF cluster paint"))?;
    let key = (identity, source.to_owned());
    if let Some(id) = writer.text.clusters.get(&key) {
        return Ok(*id);
    }
    let mut stream = Stream {
        default_rgb: if colored { parent.default_rgb } else { None },
        scalar_artwork: parent.scalar_artwork,
        content: if colored {
            String::new()
        } else {
            format!("{width} 0 {bbox} d1\nBT\n")
        },
        ..Default::default()
    };
    for (font, show, paint) in glyphs {
        if colored {
            if let Some(fill) = paint {
                flat_paint(writer, &mut stream, fill)?;
            }
            stream.content.push_str("BT\n");
        }
        stream.use_resource("Font", font, "1000 Tf");
        writeln!(stream.content, "{show}").unwrap();
        if colored {
            stream.content.push_str("ET\n");
        }
    }
    if colored {
        let metrics = format!("{width} 0 d0\n");
        if parent.default_rgb.is_some() {
            // Let the page composite calibrated glyph paints directly against
            // its backdrop. A plain form introduces no transparency group.
            let dictionary = format!(
                "/Type /XObject /Subtype /Form /BBox [{bbox}] /Resources {}",
                stream.dictionary(None)
            );
            let drawing = writer.form(&dictionary, &stream)?;
            stream = Stream {
                default_rgb: parent.default_rgb,
                ..Default::default()
            };
            stream.use_resource("XObject", drawing, "Do");
        }
        stream.content.insert_str(0, &metrics);
    } else {
        stream.content.push_str("ET\n");
    }
    let procedure = writer.content_stream("", stream.content.as_bytes())?;
    let map = program::cmap(
        writer,
        GLYPH_COLLECTION,
        2,
        true,
        &[format!("<01> <{}>", utf16(source))],
    )?;
    let resources = stream.dictionary(None);
    let id = writer.add(format!(
        "<< /Type /Font /Subtype /Type3 /FontBBox [{bbox}] /FontMatrix [.001 0 0 .001 0 0] \
         /CharProcs << /Cluster {procedure} 0 R >> /Encoding << /Type /Encoding /Differences [1 /Cluster] >> \
         /FirstChar 1 /LastChar 1 /Widths [{width}] /Resources {resources} /ToUnicode {map} 0 R >>"
    ))?;
    writer.text.clusters.insert(key, id);
    Ok(id)
}
