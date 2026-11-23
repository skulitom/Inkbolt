//! Paint a shaped cluster as one searchable character using its embedded glyphs.
use super::*;
use crate::geometry::Bounds;
use std::fmt::Write;

fn opaque(paint: &Paint) -> bool {
    match paint {
        Paint::Solid(rgba) => rgba[3] == 255,
        Paint::Precise(color) => color.rgba[3] == 1.0,
        _ => false,
    }
}

pub(super) fn intrinsic_color(group: &[PaintedGlyph<'_>]) -> bool {
    let mut colors = group.iter().filter_map(PaintedGlyph::paint);
    let Some(first) = colors.next() else {
        return false;
    };
    !opaque(first) || colors.any(|p| p != first)
}

fn ink_bounds(group: &[PaintedGlyph<'_>], transform: impl Fn(Point) -> Point) -> Bounds {
    group
        .iter()
        .filter_map(|p| p.glyph.ink_bounds)
        .flat_map(|[l, t, r, b]| [[l, t], [l, b], [r, t], [r, b]])
        .map(|corner| {
            let [x, y] = transform(corner);
            [x, y, x, y]
        })
        .reduce(scene::union)
        .unwrap_or([0.0; 4])
}

fn enclosing_box([l, t, r, b]: Bounds) -> Result<String, Error> {
    numbers(&[l.floor(), t.floor(), r.ceil(), b.ceil()])
}

fn gradient_artwork(
    writer: &mut Writer,
    group: &[PaintedGlyph<'_>],
    source: &str,
    kinds: &BTreeMap<&str, Kind>,
    parent: &Stream,
    world: Matrix,
) -> Result<Stream, Error> {
    // Masks and shadings retain the page coordinates used in outline delivery.
    let mut drawing = Stream {
        default_rgb: parent.default_rgb,
        scalar_artwork: parent.scalar_artwork,
        ..Default::default()
    };
    let mut procedure = Stream::default();
    for component in group {
        let g = component.glyph;
        // Retain the pinned source font (including the full program when
        // required) alongside the visible Type 3 character's color artwork.
        let (font, _) = register(writer, g, source, kinds[g.font_id.as_str()])?;
        procedure.resources.entry("Font").or_default().insert(font);
        if let Some(path) = component.path {
            paint(
                writer,
                &mut drawing,
                &path.geometry,
                world,
                &path.fill,
                world,
                FillRule::Nonzero,
            )?;
        }
    }
    let bbox = enclosing_box(ink_bounds(group, |p| geometry::map(world, p)))?;
    let dictionary = format!(
        "/Type /XObject /Subtype /Form /BBox [{bbox}] /Resources {}",
        drawing.dictionary(None)
    );
    let form = writer.form(&dictionary, &drawing)?;
    procedure.use_resource("XObject", form, "Do");
    Ok(procedure)
}

pub(super) fn font(
    writer: &mut Writer,
    group: &[PaintedGlyph<'_>],
    source: &str,
    kinds: &BTreeMap<&str, Kind>,
    parent: &Stream,
    colored: bool,
    gradient_world: Option<Matrix>,
) -> Result<usize, Error> {
    let base = group[0].glyph;
    let rtl_cell = gradient_world.is_some() && base.direction == crate::text::Direction::Rtl;
    let [mut w, h] = base.em_size;
    if rtl_cell {
        w = base.advance;
    }
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
    let width = if rtl_cell {
        String::from("1000")
    } else {
        number(group.iter().map(|p| p.glyph.advance).sum::<f64>() * (1000.0 / w))?
    };
    let bounds = ink_bounds(group, offset);
    let bbox = if colored {
        enclosing_box(bounds)?
    } else {
        numbers(&bounds)?
    };
    if let Some(world) = gradient_world {
        let mut procedure = gradient_artwork(writer, group, source, kinds, parent, world)?;
        let mut local_to_units = to_units;
        [local_to_units[4], local_to_units[5]] = offset([0.0, 0.0]);
        let page_to_units = geometry::multiply(local_to_units, geometry::inverse(world)?);
        // Begin a colored character with a zero-area fill using the caller's
        // color. Readers that cache a self-contained Type 3 glyph as a bitmap
        // otherwise snap its origin and move the document-space gradient.
        procedure
            .content
            .insert_str(0, &format!("q\n0 0 m f\n{} cm\n", numbers(&page_to_units)?));
        procedure.content.push_str("Q\n");
        writer.text.gradient_clusters += 1;
        // This procedure draws paths. Replacement text inside it can add a
        // second copy of the character to the outer ToUnicode mapping.
        return type3(writer, procedure, source, &width, &bbox, colored, false);
    }
    let mut glyphs = Vec::with_capacity(group.len());
    for p in group {
        let glyph = p.glyph;
        let (font, code) = register(writer, glyph, source, kinds[glyph.font_id.as_str()])?;
        let mut local = geometry::multiply(to_em, glyph_matrix(glyph));
        [local[4], local[5]] = offset(glyph.origin);
        let show = format!("{} Tm <{code}> Tj", numbers(&local)?);
        glyphs.push((font, show, p.paint().filter(|_| colored)));
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
            String::from("BT\n")
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
    if !colored {
        stream.content.push_str("ET\n");
    } else if parent.default_rgb.is_some() {
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
    let id = type3(
        writer,
        stream,
        source,
        &width,
        &bbox,
        colored,
        group.len() > 1,
    )?;
    writer.text.clusters.insert(key, id);
    Ok(id)
}

fn type3(
    writer: &mut Writer,
    mut stream: Stream,
    source: &str,
    width: &str,
    bbox: &str,
    colored: bool,
    replace_component_text: bool,
) -> Result<usize, Error> {
    let unicode = utf16(source);
    let mut header = if colored {
        format!("{width} 0 d0\n")
    } else {
        format!("{width} 0 {bbox} d1\n")
    };
    if replace_component_text {
        // The component glyphs share one replacement inside the character.
        // The selectable character on the page uses its own ToUnicode entry.
        writeln!(header, "/Span << /ActualText <FEFF{unicode}> >> BDC").unwrap();
        stream.content.push_str("EMC\n");
    }
    stream.content.insert_str(0, &header);
    let procedure = writer.content_stream("", stream.content.as_bytes())?;
    let map = program::cmap(
        writer,
        GLYPH_COLLECTION,
        2,
        true,
        &[format!("<01> <{unicode}>")],
    )?;
    let resources = stream.dictionary(None);
    writer.add(format!(
        "<< /Type /Font /Subtype /Type3 /FontBBox [{bbox}] /FontMatrix [.001 0 0 .001 0 0] \
         /CharProcs << /Cluster {procedure} 0 R >> /Encoding << /Type /Encoding /Differences [1 /Cluster] >> \
         /FirstChar 1 /LastChar 1 /Widths [{width}] /Resources {resources} /ToUnicode {map} 0 R >>"
    ))
}
