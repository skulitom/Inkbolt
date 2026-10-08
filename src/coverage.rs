//! Deterministic coverage sampling on an explicit item-local unit-cell lattice.
use crate::model::Point;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Mode {
    Smooth {},
    Dissolve { seed: u32 },
}
impl Default for Mode {
    fn default() -> Self {
        Self::Smooth {}
    }
}
impl Mode {
    pub fn is_smooth(&self) -> bool {
        matches!(self, Self::Smooth {})
    }
    pub(crate) fn alpha(self, alpha: f64, local: Point) -> f64 {
        let alpha = alpha.clamp(0.0, 1.0);
        let Self::Dissolve { seed } = self else {
            return alpha;
        };
        if alpha == 0.0 || alpha == 1.0 {
            return alpha;
        }
        let mut hash = Sha256::new();
        hash.update(b"inkbolt.coverage.v1\0");
        hash.update(seed.to_le_bytes());
        for v in local {
            hash.update((v.floor() as i64).to_le_bytes());
        }
        let bytes = hash.finalize();
        let code = u32::from_le_bytes(bytes[..4].try_into().unwrap());
        let threshold = (code as f64 + 0.5) / 4294967296.0;
        f64::from(alpha > threshold)
    }
}

#[cfg(test)]
mod tests {
    use super::Mode;
    #[test]
    fn pinned_signed_cells_strict_thresholds_and_alpha_endpoints() {
        // First digest words independently calculated with a second SHA-256
        // implementation and explicitly encoded little-endian signed cells.
        for (seed, point, word) in [
            (7, [-0.2, 2.9], 1421107307_u32),
            (0, [0.5, 0.5], 33082988),
            (u32::MAX, [-2.1, -4.2], 2895719360),
        ] {
            let mode = Mode::Dissolve { seed };
            let threshold = (word as f64 + 0.5) / 4294967296.0;
            assert_eq!(mode.alpha(threshold, point), 0.0);
            assert_eq!(mode.alpha(threshold + f64::EPSILON, point), 1.0);
            assert_eq!(mode.alpha(threshold - f64::EPSILON, point), 0.0);
            assert_eq!(mode.alpha(0.0, point), 0.0);
            assert_eq!(mode.alpha(1.0, point), 1.0);
        }
    }
}
