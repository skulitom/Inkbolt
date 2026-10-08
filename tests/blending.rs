use inkbolt::{blending::mix, model::BlendMode};

#[test]
fn discontinuous_comparison_bands_are_bounded_and_ties_explicit() {
    for delta in [-4.0, 0.0, 4.0] {
        assert_eq!(
            mix(
                [0.5; 3],
                [0.5 + delta * f64::EPSILON; 3],
                BlendMode::HardMix
            ),
            [1.0; 3]
        );
    }
    assert_eq!(
        mix([0.5; 3], [0.5 - 32.0 * f64::EPSILON; 3], BlendMode::HardMix),
        [0.0; 3]
    );
    assert_eq!(mix([0.0; 3], [1.0; 3], BlendMode::HardMix), [0.0; 3]);
    assert_eq!(mix([1.0; 3], [0.0; 3], BlendMode::HardMix), [1.0; 3]);
    let b = [0.75, 0.25, 0.0];
    let s = [0.0, 0.25, 0.75];
    for mode in [BlendMode::DarkerColor, BlendMode::LighterColor] {
        assert_eq!(mix(b, s, mode), b);
    }
    assert_eq!(
        mix(
            b,
            [0.0, 0.25, 0.75 + 32.0 * f64::EPSILON],
            BlendMode::LighterColor
        ),
        [0.0, 0.25, 0.75 + 32.0 * f64::EPSILON]
    );
}
