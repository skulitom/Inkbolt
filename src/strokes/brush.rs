//! Original rigid motif placement in a declared stroke coordinate system.
use super::outline::{Centerline, radius};
use super::*;

pub const MAX_PLACEMENTS: usize = 8192;
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Fit {
    #[default]
    Fixed,
    Uniform,
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Orientation {
    #[default]
    Bisector,
    Incoming,
    Outgoing,
}
fn angle() -> f64 {
    30.0
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Brush {
    pub motif: Geometry,
    pub spacing: f64,
    #[serde(default)]
    pub phase: f64,
    #[serde(default)]
    pub fit: Fit,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub start_motif: Option<Geometry>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub end_motif: Option<Geometry>,
    #[serde(default)]
    pub end_clearance: f64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub corner_motif: Option<Geometry>,
    #[serde(default = "angle")]
    pub corner_angle: f64,
    #[serde(default)]
    pub corner_orientation: Orientation,
    #[serde(default)]
    pub corner_clearance: f64,
}
impl Brush {
    fn motifs(&self) -> impl Iterator<Item = &Geometry> {
        std::iter::once(&self.motif)
            .chain(self.start_motif.iter())
            .chain(self.end_motif.iter())
            .chain(self.corner_motif.iter())
    }
}
pub(crate) fn stored_segments(s: &Stroke) -> Result<usize, Error> {
    s.brush.as_ref().map_or(Ok(0), |b| {
        b.motifs()
            .try_fold(0, |n, g| Ok(n + crate::geometry::validate_geometry(g)?))
    })
}
pub(super) fn validate(s: &Stroke) -> Result<(), Error> {
    let Some(b) = &s.brush else { return Ok(()) };
    if s.dash.is_some()
        || s.start_arrow.is_some()
        || s.end_arrow.is_some()
        || s.cap != Cap::Butt
        || s.join != Join::Miter
        || s.miter_limit != 4.0
    {
        return Err(Error::new(
            "UNSUPPORTED",
            "Brushes use motif endpoints/corners and spacing; dash, arrow, nondefault cap/join/miter controls cannot be combined",
        ));
    }
    if !b.spacing.is_finite()
        || !(0.001..=1024.0).contains(&b.spacing)
        || !b.phase.is_finite()
        || b.phase.abs() > MAX_COORDINATE
        || !b.corner_angle.is_finite()
        || !(0.1..=180.0).contains(&b.corner_angle)
        || [b.corner_clearance, b.end_clearance]
            .iter()
            .any(|v| !v.is_finite() || !(0.0..=1024.0).contains(v))
    {
        return Err(invalid(
            "Brush spacing must be 0.001..=1024 base widths, phase -32768..=32768 base widths, clearances 0..=1024 base widths and corner angle 0.1..=180 degrees",
        ));
    }
    if (b.corner_motif.is_none()
        && (b.corner_clearance != 0.0
            || b.corner_angle != angle()
            || b.corner_orientation != Orientation::Bisector))
        || (b.start_motif.is_none() && b.end_motif.is_none() && b.end_clearance != 0.0)
    {
        return Err(invalid(
            "Custom corner/end controls require the corresponding motif",
        ));
    }
    for g in b.motifs() {
        crate::geometry::validate_geometry(g)?;
        let expanded = crate::primitives::expand(g)?;
        if crate::geometry::control_points(&expanded)
            .iter()
            .flatten()
            .any(|v| v.abs() > 16.0)
            || contours(&expanded)?.iter().any(|c| !c.closed)
        {
            return Err(invalid(
                "Brush motifs require closed geometry with all expanded controls in -16..=16 normalized units",
            ));
        }
    }
    Ok(())
}
/// Bound generated commands and body-to-corner clearance comparisons before
/// traversing placements. A control polygon bounds evaluated centerline length.
pub(super) fn work(g: &Geometry, s: &Stroke, b: &Brush) -> Result<u64, Error> {
    let command_cost = b
        .motifs()
        .map(|g| {
            let Geometry::Path { commands } = crate::primitives::expand(g)? else {
                unreachable!()
            };
            Ok(commands.len() as u64)
        })
        .collect::<Result<Vec<_>, Error>>()?
        .into_iter()
        .max()
        .unwrap_or(1);
    let mut work = 0u64;
    let mut placements = 0u64;
    for c in contours(g)? {
        let regular = ((length_upper(&c) * 1.00000001 / (b.spacing * s.width)).ceil() as u64)
            .saturating_add(2);
        let corners = if b.corner_motif.is_some() {
            (c.edges.len() + 1) as u64
        } else {
            0
        };
        let ends = if c.closed {
            0
        } else {
            u64::from(b.start_motif.is_some()) + u64::from(b.end_motif.is_some())
        };
        let count = regular.saturating_add(corners).saturating_add(ends);
        placements = placements.saturating_add(count);
        if placements > MAX_PLACEMENTS as u64 {
            return Err(Error::new(
                "LIMIT_EXCEEDED",
                "Brush exceeds conservative 8192 placement limit",
            ));
        }
        work = work
            .saturating_add(count.saturating_mul(command_cost))
            .saturating_add(regular.saturating_mul(corners));
        check_work(work, MAX_DOCUMENT_WORK)?;
    }
    Ok(work)
}
fn direction(a: Point, b: Point) -> Point {
    let l = distance(a, b);
    if l == 0.0 {
        [1.0, 0.0]
    } else {
        [(b[0] - a[0]) / l, (b[1] - a[1]) / l]
    }
}
fn corner_positions(center: &Centerline, closed: bool, b: &Brush) -> Vec<(f64, Point)> {
    if b.corner_motif.is_none() || center.points.len() < 3 {
        return vec![];
    }
    let last = center.points.len() - 1;
    center
        .anchors
        .iter()
        .filter_map(|&i| {
            if i == last || (!closed && i == 0) {
                return None;
            }
            let incoming = direction(
                center.points[if i == 0 { last - 1 } else { i - 1 }],
                center.points[i],
            );
            let outgoing = direction(center.points[i], center.points[i + 1]);
            let cross = incoming[0] * outgoing[1] - incoming[1] * outgoing[0];
            let dot = incoming[0] * outgoing[0] + incoming[1] * outgoing[1];
            let turn = cross.abs().atan2(dot).to_degrees();
            if turn < b.corner_angle {
                return None;
            }
            let bisector = [incoming[0] + outgoing[0], incoming[1] + outgoing[1]];
            let tangent = match b.corner_orientation {
                Orientation::Incoming => incoming,
                Orientation::Outgoing => outgoing,
                Orientation::Bisector if bisector[0].hypot(bisector[1]) < 1e-12 => outgoing,
                Orientation::Bisector => direction([0.0, 0.0], bisector),
            };
            Some((center.lengths[i], tangent))
        })
        .collect()
}
fn append(
    commands: &mut Vec<PathCommand>,
    motif: &Geometry,
    p: Point,
    u: Point,
    scale: f64,
) -> Result<(), Error> {
    if scale == 0.0 {
        return Ok(());
    }
    let matrix = [
        scale * u[0],
        scale * u[1],
        -scale * u[1],
        scale * u[0],
        p[0],
        p[1],
    ];
    let Geometry::Path { commands: copy } = super::mapped(motif, matrix)? else {
        unreachable!()
    };
    if commands.len() + copy.len() > MAX_OUTLINE_COMMANDS {
        return Err(Error::new(
            "LIMIT_EXCEEDED",
            "Brush exceeds generated outline command limit",
        ));
    }
    commands.extend(copy);
    Ok(())
}
pub(super) fn generate(
    g: &Geometry,
    s: &Stroke,
    b: &Brush,
    tolerance: f64,
) -> Result<Option<Geometry>, Error> {
    work(g, s, b)?;
    let mut commands = vec![];
    for contour in contours(g)? {
        if contour.closed
            && !s.width_profile.is_empty()
            && s.width_profile[0][1] != s.width_profile.last().unwrap()[1]
        {
            return Err(invalid(
                "Closed-contour width profiles must have equal endpoint factors",
            ));
        }
        let center = Centerline::new(&contour, tolerance)?;
        let length = center.length();
        let corners = corner_positions(&center, contour.closed, b);
        let nominal = b.spacing * s.width;
        let intervals = (length / nominal).round().max(1.0);
        let step = if b.fit == Fit::Uniform && length > 0.0 {
            length / intervals
        } else {
            nominal
        };
        // Bound coordinate subtraction and accumulated distance roundoff.
        // Without this, decimal paths can retain an almost-duplicate seam
        // center or fail to replace a body motif at an authored corner.
        let precision = 16.0
            * f64::EPSILON
            * (center.points.len() as f64 * length
                + center
                    .points
                    .iter()
                    .map(|p| p[0].abs().max(p[1].abs()))
                    .sum::<f64>());
        if length > 0.0 && precision > step / 4.0 {
            return Err(Error::new(
                "UNSUPPORTED",
                "Brush spacing is below the conservative centerline-distance precision bound",
            ));
        }
        let fraction = b.phase.rem_euclid(b.spacing) / b.spacing;
        let phase = fraction * step;
        let normalized = |pos: f64| if length == 0.0 { 0.0 } else { pos / length };
        let stamp = |commands: &mut Vec<PathCommand>, motif: &Geometry, pos: f64, u: Point| {
            append(
                commands,
                motif,
                center.at(pos),
                u,
                radius(s, normalized(pos)) * 2.0,
            )
        };
        // Integer indexing avoids accumulated phase drift. A zero-length
        // contour has one body motif at its origin, independent of phase.
        let count = if length == 0.0 {
            1
        } else {
            (length / step).ceil() as usize + 1
        };
        for k in 0..count {
            let mut pos = if length == 0.0 {
                0.0
            } else if b.fit == Fit::Uniform {
                length * ((k as f64 + fraction) / intervals)
            } else {
                phase + k as f64 * step
            };
            if pos != 0.0 && (pos - length).abs() <= precision {
                pos = length;
            }
            if pos > length || (contour.closed && length > 0.0 && pos == length) {
                break;
            }
            if !contour.closed
                && ((b.start_motif.is_some() && pos <= b.end_clearance * s.width + precision)
                    || (b.end_motif.is_some()
                        && length - pos <= b.end_clearance * s.width + precision))
            {
                continue;
            }
            if corners.iter().any(|(at, _)| {
                let d = (at - pos).abs();
                let d = if contour.closed { d.min(length - d) } else { d };
                d <= b.corner_clearance * s.width + precision
            }) {
                continue;
            }
            stamp(&mut commands, &b.motif, pos, center.direction(pos))?;
        }
        if !contour.closed {
            for (motif, pos) in [(&b.start_motif, 0.0), (&b.end_motif, length)] {
                if let Some(motif) = motif {
                    stamp(&mut commands, motif, pos, center.direction(pos))?;
                }
            }
        }
        if let Some(motif) = &b.corner_motif {
            for (pos, u) in corners {
                stamp(&mut commands, motif, pos, u)?;
            }
        }
    }
    Ok((!commands.is_empty()).then_some(Geometry::Path { commands }))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn brush_library_rejects_nonfinite_controls() {
        let base: Stroke = serde_json::from_value(serde_json::json!({
            "color":[0,0,0,255],"width":2,
            "brush":{"motif":{"shape":"rect","x":-0.5,"y":-0.5,"width":1,"height":1},"spacing":2}
        }))
        .unwrap();
        for v in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            for field in 0..5 {
                let mut s = base.clone();
                let b = s.brush.as_mut().unwrap();
                match field {
                    0 => b.spacing = v,
                    1 => b.phase = v,
                    2 => b.corner_angle = v,
                    3 => b.corner_clearance = v,
                    _ => b.end_clearance = v,
                }
                assert!(validate(&s).is_err());
            }
        }
    }
}
