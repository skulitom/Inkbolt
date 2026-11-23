//! Turn the same positioned font instance used by the layout engine into a
//! static PDF font. Write the used contours, metrics and embedding permissions.
use super::*;
use rustybuzz::ttf_parser::OutlineBuilder;
use subsetter::GlyphRemapper;
use write_fonts::{
    FontBuilder,
    from_obj::ToOwnedTable,
    read::{FontRef, TableProvider, tables::glyf::CurvePoint},
    tables::{
        glyf::{GlyfLocaBuilder, SimpleGlyph},
        head::Head,
        hhea::Hhea,
        hmtx::{Hmtx, LongMetric},
        maxp::Maxp,
        os2::Os2,
        post::Post,
    },
    types::{Fixed, Tag, Version16Dot16},
};

#[derive(Default)]
struct Pen {
    glyph: SimpleGlyph,
    contour: Vec<CurvePoint>,
    current: [f64; 2],
    reverse_winding: bool,
    points: usize,
    invalid: bool,
}
impl Pen {
    fn encodable(&self) -> bool {
        if self.invalid || self.glyph.contours.len() >= i16::MAX as usize {
            return false;
        }
        // TrueType stores signed deltas continuously, including between contours.
        let mut previous = (0, 0);
        self.glyph.contours.iter().flat_map(|c| c.iter()).all(|p| {
            let fits =
                p.x.checked_sub(previous.0).is_some() && p.y.checked_sub(previous.1).is_some();
            previous = (p.x, p.y);
            fits
        })
    }

    fn point(&mut self, point: [f64; 2], on_curve: bool) {
        if on_curve {
            self.current = point;
        }
        let [x, y] = point.map(f64::round);
        let units = f64::from(i16::MIN)..=f64::from(i16::MAX);
        if self.points >= usize::from(u16::MAX) || !units.contains(&x) || !units.contains(&y) {
            self.invalid = true;
            return;
        }
        self.contour
            .push(CurvePoint::new(x as i16, y as i16, on_curve));
        self.points += 1;
    }

    fn cubic(&mut self, [a, b, c, d]: [[f64; 2]; 4]) {
        if self.invalid {
            return;
        }
        // Elevating a quadratic back to cubic gives two inner controls.
        // Choose the quadratic control that balances their errors. Bounding
        // each control error bounds the entire curve by convexity.
        let q = std::array::from_fn(|i| (3.0 * (b[i] + c[i]) - a[i] - d[i]) / 4.0);
        // Rounding controls and endpoints to the nearest font unit uses up to half a unit.
        let fit_error = crate::limits::pdf::MAX_CFF2_CURVE_ERROR - 0.5;
        if (0..2).all(|i| {
            ((a[i] + 2.0 * q[i]) / 3.0 - b[i]).abs() <= fit_error
                && ((d[i] + 2.0 * q[i]) / 3.0 - c[i]).abs() <= fit_error
        }) {
            self.point(q, false);
            self.point(d, true);
            return;
        }
        let mid = |p: [f64; 2], r: [f64; 2]| [(p[0] + r[0]) * 0.5, (p[1] + r[1]) * 0.5];
        let (ab, bc, cd) = (mid(a, b), mid(b, c), mid(c, d));
        let (abc, bcd) = (mid(ab, bc), mid(bc, cd));
        let center = mid(abc, bcd);
        self.cubic([a, ab, abc, center]);
        self.cubic([center, bcd, cd, d]);
    }
}
impl OutlineBuilder for Pen {
    fn move_to(&mut self, x: f32, y: f32) {
        self.close();
        self.point([x.into(), y.into()], true);
    }
    fn line_to(&mut self, x: f32, y: f32) {
        self.point([x.into(), y.into()], true);
    }
    fn quad_to(&mut self, cx: f32, cy: f32, x: f32, y: f32) {
        self.point([cx.into(), cy.into()], false);
        self.point([x.into(), y.into()], true);
    }
    fn curve_to(&mut self, bx: f32, by: f32, cx: f32, cy: f32, x: f32, y: f32) {
        let points = [
            self.current,
            [bx.into(), by.into()],
            [cx.into(), cy.into()],
            [x.into(), y.into()],
        ];
        if points.iter().flatten().all(|v| v.is_finite()) {
            self.cubic(points);
        } else {
            self.invalid = true;
        }
    }
    fn close(&mut self) {
        if self.contour.len() > 1 && self.contour.first() == self.contour.last() {
            self.contour.pop();
            self.points -= 1;
        }
        if !self.contour.is_empty() {
            if self.reverse_winding {
                // CFF and TrueType use opposite directions for filled contours.
                self.contour[1..].reverse();
            }
            self.glyph
                .contours
                .push(std::mem::take(&mut self.contour).into());
        }
    }
}

pub(super) fn program(
    data: &[u8],
    index: u32,
    face: &Face<'_>,
    axes: &[([u8; 4], u32)],
    mapper: &GlyphRemapper,
    control: &crate::control::Control,
) -> Result<Vec<u8>, Error> {
    let invalid = || unsupported("Unable to encode the static TrueType font instance");
    let font = FontRef::from_index(data, index).map_err(|_| invalid())?;
    let mut loca_builder = GlyfLocaBuilder::new();
    let mut metrics = Vec::with_capacity(mapper.num_gids().into());
    let mut head: Head = font.head().map_err(|_| invalid())?.to_owned_table();
    let mut hhea: Hhea = font.hhea().map_err(|_| invalid())?.to_owned_table();
    let mut os2: Os2 = font.os2().map_err(|_| invalid())?.to_owned_table();
    let mut maxp = Maxp {
        num_glyphs: mapper.num_gids(),
        max_points: Some(0),
        max_contours: Some(0),
        max_composite_points: Some(0),
        max_composite_contours: Some(0),
        max_zones: Some(1),
        max_twilight_points: Some(0),
        max_storage: Some(0),
        max_function_defs: Some(0),
        max_instruction_defs: Some(0),
        max_stack_elements: Some(0),
        max_size_of_instructions: Some(0),
        max_component_elements: Some(0),
        max_component_depth: Some(0),
    };
    let mut bbox: Option<[i16; 4]> = None;
    let mut bearings: Option<[i16; 3]> = None;
    let mut point_count = 0;
    let mut advance_max = 0;
    for gid in mapper.remapped_gids().map(GlyphId) {
        control.check()?;
        let mut pen = Pen {
            reverse_winding: face.tables().cff2.is_some(),
            ..Pen::default()
        };
        let outlined = crate::fonts::draw_outline(face, gid, &mut pen)?;
        pen.close();
        if !pen.encodable() || (!outlined && pen.points > 0) {
            return Err(invalid());
        }
        point_count += pen.points;
        if point_count > MAX_COMMANDS {
            return Err(limit("PDF font instance exceeds the outline point budget"));
        }
        pen.glyph.recompute_bounding_box();
        let b = pen.glyph.bbox;
        let advance = face.glyph_hor_advance(gid).ok_or_else(invalid)?;
        advance_max = advance_max.max(advance);
        metrics.push(LongMetric::new(advance, b.x_min));
        if !pen.glyph.contours.is_empty() {
            let bounds = [b.x_min, b.y_min, b.x_max, b.y_max];
            bbox = Some(bbox.map_or(bounds, |[l, t, r, d]| {
                [
                    l.min(b.x_min),
                    t.min(b.y_min),
                    r.max(b.x_max),
                    d.max(b.y_max),
                ]
            }));
            let right =
                i16::try_from(i32::from(advance) - i32::from(b.x_max)).map_err(|_| invalid())?;
            let extents = [b.x_min, right, b.x_max];
            bearings = Some(bearings.map_or(extents, |[l, r, x]| {
                [l.min(b.x_min), r.min(right), x.max(b.x_max)]
            }));
        }
        maxp.max_points = maxp.max_points.max(Some(pen.points as u16));
        maxp.max_contours = maxp.max_contours.max(Some(pen.glyph.contours.len() as u16));
        loca_builder.add_glyph(&pen.glyph).map_err(|_| invalid())?;
    }
    let (glyf, loca, format) = loca_builder.build();
    head.index_to_loc_format = format as i16;
    [head.x_min, head.y_min, head.x_max, head.y_max] = bbox.unwrap_or_default();
    hhea.number_of_h_metrics = mapper.num_gids();
    hhea.advance_width_max = advance_max.into();
    [
        hhea.min_left_side_bearing,
        hhea.min_right_side_bearing,
        hhea.x_max_extent,
    ] = bearings.unwrap_or_default().map(Into::into);
    os2.s_typo_ascender = face.typographic_ascender().ok_or_else(invalid)?;
    os2.s_typo_descender = face.typographic_descender().ok_or_else(invalid)?;
    os2.s_typo_line_gap = face.typographic_line_gap().ok_or_else(invalid)?;
    os2.sx_height = face.x_height();
    os2.s_cap_height = face.capital_height();
    for (tag, bits) in axes {
        let value = f32::from_bits(*bits);
        match tag {
            b"wght" => os2.us_weight_class = value.clamp(1.0, 1000.0).round() as u16,
            b"wdth" => {
                // Midpoints between the nine standard OS/2 width class percentages.
                let midpoints = [56.25, 68.75, 81.25, 93.75, 106.25, 118.75, 137.5, 175.0];
                os2.us_width_class = 1 + midpoints.partition_point(|mid| value >= *mid) as u16;
            }
            _ => {}
        }
    }
    let underline = face.underline_metrics();
    let post = Post {
        version: Version16Dot16::VERSION_3_0,
        italic_angle: Fixed::from_f64(f64::from(face.italic_angle())),
        is_fixed_pitch: u32::from(face.is_monospaced()),
        underline_position: underline.map_or(0, |line| line.position).into(),
        underline_thickness: underline.map_or(0, |line| line.thickness).into(),
        ..Post::default()
    };
    let mut builder = FontBuilder::new();
    builder
        .add_table(&head)
        .and_then(|b| b.add_table(&hhea))
        .and_then(|b| b.add_table(&maxp))
        .and_then(|b| b.add_table(&Hmtx::new(metrics, vec![])))
        .and_then(|b| b.add_table(&glyf))
        .and_then(|b| b.add_table(&loca))
        .and_then(|b| b.add_table(&os2))
        .and_then(|b| b.add_table(&post))
        .map_err(|_| invalid())?;
    if let Some(name) = font.data_for_tag(Tag::new(b"name")) {
        builder.add_raw(Tag::new(b"name"), name.as_bytes());
    }
    Ok(builder.build())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn signed_point_deltas_span_contours() {
        let mut pen = Pen::default();
        pen.move_to(-20000.0, 0.0);
        pen.line_to(-20000.0, 25.0);
        pen.close();
        assert!(pen.encodable());
        pen.move_to(20000.0, 0.0);
        pen.line_to(20000.0, 25.0);
        pen.close();
        assert!(!pen.encodable());
    }

    #[test]
    fn cubic_reduction_bounds_rounded_quadratics_at_the_same_parameter() {
        let [a, b, c, d] = [
            [1.25, -17.5],
            [-337.75, 862.5],
            [781.0, -421.25],
            [66.5, 72.25],
        ];
        let mut pen = Pen::default();
        pen.point(a, true);
        pen.cubic([a, b, c, d]);
        assert!(pen.encodable());
        let segments = (pen.contour.len() - 1) / 2;
        assert!(segments > 1 && segments.is_power_of_two());
        for (index, piece) in pen.contour.windows(3).step_by(2).enumerate() {
            assert!(piece[0].on_curve && !piece[1].on_curve && piece[2].on_curve);
            for sample in 0..=128 {
                let u = f64::from(sample) / 128.0;
                let t = (index as f64 + u) / segments as f64;
                for axis in 0..2 {
                    let value = |p: &CurvePoint| f64::from(if axis == 0 { p.x } else { p.y });
                    let quadratic = (1.0 - u).powi(2) * value(&piece[0])
                        + 2.0 * u * (1.0 - u) * value(&piece[1])
                        + u * u * value(&piece[2]);
                    let cubic = (1.0 - t).powi(3) * a[axis]
                        + 3.0 * t * (1.0 - t).powi(2) * b[axis]
                        + 3.0 * t * t * (1.0 - t) * c[axis]
                        + t.powi(3) * d[axis];
                    assert!((quadratic - cubic).abs() <= 0.75);
                }
            }
        }
    }
}
