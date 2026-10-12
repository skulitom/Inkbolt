//! Original SVG endpoint-to-center normalization and tangent-cubic expansion.
//! Equations: https://www.w3.org/TR/SVG/implnote.html#ArcImplementationNotes
use super::numbers::invalid;
use crate::{Error, limits::svg_import::ARC_RADIAL_TOLERANCE, model::*};
use serde::Serialize;
use std::f64::consts::{FRAC_PI_2, TAU};

#[derive(Default, Serialize)]
pub(super) struct Summary {
    pub arc_commands: usize,
    cubic_segments: usize,
    zero_radius_lines: usize,
    coincident_endpoints: usize,
    max_radial_error_local: f64,
}

fn limit() -> Error {
    Error::new(
        "LIMIT_EXCEEDED",
        "SVG arc expansion exceeds the path command limit",
    )
}

// A tangent cubic spanning delta on the unit circle has squared radial excess
// 16*h^6/(1+h^2)^2 * t^2*(1-t)^2*(2*t-1)^2, h=tan(delta/4).
// The t polynomial is at most 1/108. sqrt(1+x)-1 <= x/2 gives this
// conservative distance bound; stretching to an ellipse costs max(rx,ry).
fn radial_bound(delta: f64, radius: f64) -> f64 {
    let h = (delta.abs() / 4.0).tan();
    radius * 2.0 * h.powi(6) / (27.0 * (1.0 + h * h).powi(2))
}

pub(super) fn append(
    commands: &mut Vec<PathCommand>,
    from: Point,
    to: Point,
    parameters: &[f64],
    summary: &mut Summary,
) -> Result<(), Error> {
    summary.arc_commands += 1;
    if from == to {
        summary.coincident_endpoints += 1;
        return Ok(());
    }
    let mut rx = parameters[0].abs();
    let mut ry = parameters[1].abs();
    if rx == 0.0 || ry == 0.0 {
        if commands.len() >= MAX_SEGMENTS {
            return Err(limit());
        }
        commands.push(PathCommand::Line { to });
        summary.zero_radius_lines += 1;
        return Ok(());
    }
    let large = parameters[3] != 0.0;
    let sweep = parameters[4] != 0.0;
    let (sin, cos) = (parameters[2].rem_euclid(360.0).to_radians()).sin_cos();
    let half = [(from[0] - to[0]) / 2.0, (from[1] - to[1]) / 2.0];
    let prime = [
        cos * half[0] + sin * half[1],
        -sin * half[0] + cos * half[1],
    ];
    let mut unit = [prime[0] / rx, prime[1] / ry];
    let mut norm = unit[0].hypot(unit[1]);
    if !norm.is_finite() || norm == 0.0 {
        return Err(invalid(
            "Arc radii/endpoints cannot be normalized at binary64 precision",
        ));
    }
    // The hypot form avoids overflow from squaring large ratios. After radius
    // correction the unique center is the midpoint, with exactly a half turn.
    if norm > 1.0 {
        rx *= norm;
        ry *= norm;
        unit = [unit[0] / norm, unit[1] / norm];
        norm = 1.0;
    }
    if !rx.is_finite() || !ry.is_finite() || rx > MAX_COORDINATE || ry > MAX_COORDINATE {
        return Err(Error::new(
            "LIMIT_EXCEEDED",
            format!("Normalized SVG arc radii must not exceed {MAX_COORDINATE} local units"),
        ));
    }
    let sign = if large == sweep { -1.0 } else { 1.0 };
    let offset = sign * ((1.0 - norm) * (1.0 + norm)).sqrt();
    let cp = [
        rx * (unit[1] / norm) * offset,
        -ry * (unit[0] / norm) * offset,
    ];
    let center = [
        cos * cp[0] - sin * cp[1] + (from[0] + to[0]) / 2.0,
        sin * cp[0] + cos * cp[1] + (from[1] + to[1]) / 2.0,
    ];
    let theta = ((prime[1] - cp[1]) / ry).atan2((prime[0] - cp[0]) / rx);
    let minor = 2.0 * norm.asin();
    let magnitude = if large { TAU - minor } else { minor };
    let delta = if sweep { magnitude } else { -magnitude };
    let at = |angle: f64| {
        let (s, c) = angle.sin_cos();
        (
            [
                center[0] + rx * cos * c - ry * sin * s,
                center[1] + rx * sin * c + ry * cos * s,
            ],
            [-rx * cos * s - ry * sin * c, -rx * sin * s + ry * cos * c],
        )
    };
    let distance = |a: Point, b: Point| (a[0] - b[0]).hypot(a[1] - b[1]);
    // Preserve the supplied endpoints exactly. Adjusting both adjacent control
    // points by the same endpoint delta preserves the computed tangent. By the
    // convex-hull property this adds at most the larger endpoint correction.
    let correction = distance(at(theta).0, from).max(distance(at(theta + delta).0, to));
    if !correction.is_finite() || correction >= ARC_RADIAL_TOLERANCE {
        return Err(invalid(
            "Arc endpoint reconstruction exceeds the declared local tolerance",
        ));
    }
    let mut count = (magnitude / FRAC_PI_2).ceil().max(1.0) as usize;
    while radial_bound(delta / count as f64, rx.max(ry)) + correction > ARC_RADIAL_TOLERANCE {
        count *= 2;
        if count > MAX_SEGMENTS {
            return Err(limit());
        }
    }
    if commands.len() + count > MAX_SEGMENTS {
        return Err(limit());
    }
    let step = delta / count as f64;
    let tangent = (4.0 / 3.0) * (step / 4.0).tan();
    let mut previous = from;
    for index in 0..count {
        let (_, d0) = at(theta + index as f64 * step);
        let (point, d1) = at(theta + (index + 1) as f64 * step);
        let endpoint = if index + 1 == count { to } else { point };
        commands.push(PathCommand::Cubic {
            control1: [previous[0] + tangent * d0[0], previous[1] + tangent * d0[1]],
            control2: [endpoint[0] - tangent * d1[0], endpoint[1] - tangent * d1[1]],
            to: endpoint,
        });
        previous = endpoint;
    }
    summary.cubic_segments += count;
    summary.max_radial_error_local = summary
        .max_radial_error_local
        .max(radial_bound(step, rx.max(ry)) + correction);
    Ok(())
}
