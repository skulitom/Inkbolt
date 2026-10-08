//! Original encoded-sRGB color mixing. Coverage and compositing belong to callers.
use crate::model::BlendMode;

pub const MODES: [BlendMode; 26] = [
    BlendMode::Normal,
    BlendMode::Multiply,
    BlendMode::Screen,
    BlendMode::Darken,
    BlendMode::Lighten,
    BlendMode::ColorBurn,
    BlendMode::ColorDodge,
    BlendMode::Overlay,
    BlendMode::HardLight,
    BlendMode::SoftLight,
    BlendMode::Difference,
    BlendMode::Exclusion,
    BlendMode::Hue,
    BlendMode::Saturation,
    BlendMode::Color,
    BlendMode::Luminosity,
    BlendMode::LinearBurn,
    BlendMode::LinearDodge,
    BlendMode::VividLight,
    BlendMode::LinearLight,
    BlendMode::PinLight,
    BlendMode::HardMix,
    BlendMode::Subtract,
    BlendMode::Divide,
    BlendMode::DarkerColor,
    BlendMode::LighterColor,
];

fn light(b: f64, s: f64) -> f64 {
    if s <= 0.5 {
        2.0 * b * s
    } else {
        1.0 - 2.0 * (1.0 - b) * (1.0 - s)
    }
}
fn dodge(b: f64, s: f64) -> f64 {
    if b == 0.0 {
        0.0
    } else if s == 1.0 {
        1.0
    } else {
        (b / (1.0 - s)).min(1.0)
    }
}
fn burn(b: f64, s: f64) -> f64 {
    if b == 1.0 {
        1.0
    } else if s == 0.0 {
        0.0
    } else {
        1.0 - ((1.0 - b) / s).min(1.0)
    }
}
fn vivid(b: f64, s: f64) -> f64 {
    if s <= 0.5 {
        burn(b, 2.0 * s)
    } else {
        dodge(b, 2.0 * s - 1.0)
    }
}
// Quantized-alpha round trips can move an exact comparison boundary by a few
// ulps. Only discontinuous comparisons use this documented tie band.
fn compare(a: f64, b: f64) -> std::cmp::Ordering {
    if (a - b).abs() <= 8.0 * f64::EPSILON * a.abs().max(b.abs()).max(1.0) {
        std::cmp::Ordering::Equal
    } else {
        a.total_cmp(&b)
    }
}
fn lum(c: [f64; 3]) -> f64 {
    0.3 * c[0] + 0.59 * c[1] + 0.11 * c[2]
}
fn range(c: [f64; 3]) -> (f64, f64) {
    (
        c.into_iter().fold(1.0, f64::min),
        c.into_iter().fold(0.0, f64::max),
    )
}
fn sat(c: [f64; 3]) -> f64 {
    let (lo, hi) = range(c);
    hi - lo
}
fn with_sat(c: [f64; 3], amount: f64) -> [f64; 3] {
    let (lo, hi) = range(c);
    if hi == lo {
        [0.0; 3]
    } else {
        c.map(|v| (v - lo) * amount / (hi - lo))
    }
}
fn with_lum(c: [f64; 3], target: f64) -> [f64; 3] {
    // Translate to the target luminance, then contract along the neutral-axis
    // ray until all channels fit. One factor preserves luminance and hue.
    let offset = target - lum(c);
    let moved = c.map(|v| v + offset);
    let factor = moved.into_iter().fold(1.0_f64, |factor, v| {
        if v < 0.0 {
            factor.min(target / (target - v))
        } else if v > 1.0 {
            factor.min((1.0 - target) / (v - target))
        } else {
            factor
        }
    });
    moved.map(|v| (target + factor * (v - target)).clamp(0.0, 1.0))
}

/// Mix finite straight encoded-sRGB colors in [0,1]; no alpha or opacity here.
/// The first sixteen modes use the W3C compositing color equations. Additional
/// arithmetic families have the explicit project contract in docs/BLENDING.md.
pub fn mix(backdrop: [f64; 3], source: [f64; 3], mode: BlendMode) -> [f64; 3] {
    let b = backdrop.map(|v| v.clamp(0.0, 1.0));
    let s = source.map(|v| v.clamp(0.0, 1.0));
    match mode {
        BlendMode::Hue => return with_lum(with_sat(s, sat(b)), lum(b)),
        BlendMode::Saturation => return with_lum(with_sat(b, sat(s)), lum(b)),
        BlendMode::Color => return with_lum(s, lum(b)),
        BlendMode::Luminosity => return with_lum(b, lum(s)),
        BlendMode::DarkerColor => {
            return if compare(s.iter().sum(), b.iter().sum()).is_lt() {
                s
            } else {
                b
            };
        }
        BlendMode::LighterColor => {
            return if compare(s.iter().sum(), b.iter().sum()).is_gt() {
                s
            } else {
                b
            };
        }
        _ => {}
    }
    std::array::from_fn(|i| {
        let (b, s) = (b[i], s[i]);
        let result = match mode {
            BlendMode::Normal => s,
            BlendMode::Multiply => b * s,
            BlendMode::Screen => b + s - b * s,
            BlendMode::Darken => b.min(s),
            BlendMode::Lighten => b.max(s),
            BlendMode::ColorBurn => burn(b, s),
            BlendMode::ColorDodge => dodge(b, s),
            BlendMode::Overlay => light(s, b),
            BlendMode::HardLight => light(b, s),
            BlendMode::SoftLight => {
                if s <= 0.5 {
                    b - (1.0 - 2.0 * s) * b * (1.0 - b)
                } else {
                    let d = if b <= 0.25 {
                        ((16.0 * b - 12.0) * b + 4.0) * b
                    } else {
                        b.sqrt()
                    };
                    b + (2.0 * s - 1.0) * (d - b)
                }
            }
            BlendMode::Difference => (b - s).abs(),
            BlendMode::Exclusion => b + s - 2.0 * b * s,
            BlendMode::LinearBurn => b + s - 1.0,
            BlendMode::LinearDodge => b + s,
            BlendMode::VividLight => vivid(b, s),
            BlendMode::LinearLight => b + 2.0 * s - 1.0,
            BlendMode::PinLight => {
                if s <= 0.5 {
                    b.min(2.0 * s)
                } else {
                    b.max(2.0 * s - 1.0)
                }
            }
            BlendMode::HardMix => {
                if (b == 0.0 && s == 1.0) || compare(b + s, 1.0).is_lt() {
                    0.0
                } else {
                    1.0
                }
            }
            BlendMode::Subtract => b - s,
            BlendMode::Divide => {
                if s == 0.0 {
                    1.0
                } else {
                    b / s
                }
            }
            _ => unreachable!("Nonseparable families handled as RGB triples"),
        };
        result.clamp(0.0, 1.0)
    })
}
