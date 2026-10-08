//! Original device-ink blending; alpha and compatible overprint belong to callers.
use crate::model::BlendMode;

fn nonseparable(mode: BlendMode) -> bool {
    matches!(
        mode,
        BlendMode::Hue
            | BlendMode::Saturation
            | BlendMode::Color
            | BlendMode::Luminosity
            | BlendMode::DarkerColor
            | BlendMode::LighterColor
    )
}

pub(super) fn mix(backdrop: &[f64], source: &[f64], mode: BlendMode, out: &mut [f64]) {
    if mode == BlendMode::Normal {
        out.copy_from_slice(source);
        return;
    }
    if matches!(mode, BlendMode::DarkerColor | BlendMode::LighterColor) {
        // The project whole-color extension selects the complete process tuple.
        // More total subtractive ink is darker; the backdrop wins bounded ties.
        let b: f64 = backdrop[..4].iter().sum();
        let s: f64 = source[..4].iter().sum();
        let tied = (b - s).abs() <= 8.0 * f64::EPSILON * b.abs().max(s.abs()).max(1.0);
        let choose_source = !tied
            && if mode == BlendMode::DarkerColor {
                s > b
            } else {
                s < b
            };
        out[..4].copy_from_slice(if choose_source {
            &source[..4]
        } else {
            &backdrop[..4]
        });
    } else {
        let cmy = crate::blending::mix(
            std::array::from_fn(|c| 1.0 - backdrop[c]),
            std::array::from_fn(|c| 1.0 - source[c]),
            mode,
        );
        for c in 0..3 {
            out[c] = 1.0 - cmy[c];
        }
        out[3] = if nonseparable(mode) {
            if mode == BlendMode::Luminosity {
                source[3]
            } else {
                backdrop[3]
            }
        } else {
            1.0 - crate::blending::mix([1.0 - backdrop[3]; 3], [1.0 - source[3]; 3], mode)[0]
        };
    }
    // Only separable, white-preserving modes affect named inks. The project
    // subtract extension also fails B(1,1)=1 and therefore uses Normal here.
    let spot_normal = nonseparable(mode)
        || matches!(
            mode,
            BlendMode::Difference | BlendMode::Exclusion | BlendMode::Subtract
        );
    for c in 4..out.len() {
        out[c] = if spot_normal {
            source[c]
        } else {
            1.0 - crate::blending::mix([1.0 - backdrop[c]; 3], [1.0 - source[c]; 3], mode)[0]
        };
    }
}
