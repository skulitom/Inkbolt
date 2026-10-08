//! Original pixel relocation, editable displacement fields and block averaging.
use crate::{Error, assets::Sampling, geometry, model::*};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

pub const MAX_MAP_PIXELS: usize = 4096;
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Map {
    pub width: u32,
    pub height: u32,
    pub vectors: Vec<Point>,
    #[serde(default = "identity")]
    pub transform: Matrix,
    #[serde(default)]
    pub sampling: Sampling,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Operator {
    Offset { offset: Point },
    Displace { map: Map, amount: Point },
    Mosaic { size: u32 },
}
impl Operator {
    pub fn stored_pixels(&self) -> usize {
        if let Self::Displace { map, .. } = self {
            map.vectors.len()
        } else {
            0
        }
    }
    pub fn validate(&self, world: Matrix) -> Result<(), Error> {
        let bounded = |p: Point| p.iter().all(|v| v.is_finite() && v.abs() <= 256.0);
        let valid = match self {
            Self::Offset { offset } => bounded(*offset),
            Self::Mosaic { size } => (1..=128).contains(size),
            Self::Displace { map, amount } => {
                if map.sampling.advanced() {
                    return Err(Error::new(
                        "UNSUPPORTED",
                        "Displacement fields currently support nearest and bilinear sampling",
                    ));
                }
                if !(1..=256).contains(&map.width)
                    || !(1..=256).contains(&map.height)
                    || map.vectors.len() != map.width as usize * map.height as usize
                {
                    return Err(invalid(
                        "Displacement field requires exact width*height vectors and dimensions in 1..=256",
                    ));
                }
                if map.vectors.len() > MAX_MAP_PIXELS {
                    return Err(limit("Displacement field exceeds 4096 vectors"));
                }
                geometry::validate_matrix(map.transform)?;
                let placement = geometry::multiply(world, map.transform);
                geometry::validate_matrix(placement)?;
                validate_world_geometry(
                    &Geometry::Rect {
                        x: 0.0,
                        y: 0.0,
                        width: map.width as f64,
                        height: map.height as f64,
                    },
                    placement,
                )?;
                bounded(*amount)
                    && map
                        .vectors
                        .iter()
                        .flatten()
                        .all(|v| v.is_finite() && v.abs() <= 1.0)
            }
        };
        if valid {
            Ok(())
        } else {
            Err(invalid(
                "Spatial filter offsets, vectors or block size exceed declared limits",
            ))
        }
    }
    pub fn work(&self) -> u64 {
        match self {
            Self::Mosaic { .. } => 4,
            Self::Offset { .. } => 4,
            Self::Displace { .. } => 16,
        }
    }
}
pub(crate) fn field(map: &Map, local: Point) -> Point {
    let at = |x: i64, y: i64| {
        map.vectors[y.clamp(0, map.height as i64 - 1) as usize * map.width as usize
            + x.clamp(0, map.width as i64 - 1) as usize]
    };
    match map.sampling {
        Sampling::Nearest => at(
            crate::assets::pixel_index(local[0]),
            crate::assets::pixel_index(local[1]),
        ),
        Sampling::Bilinear => {
            let x = (local[0] - 0.5).clamp(0.0, (map.width - 1) as f64);
            let y = (local[1] - 0.5).clamp(0.0, (map.height - 1) as f64);
            let ix = x.floor() as i64;
            let iy = y.floor() as i64;
            let fx = x - x.floor();
            let fy = y - y.floor();
            let mut v = [0.0; 2];
            for (dx, wx) in [(0, 1.0 - fx), (1, fx)] {
                for (dy, wy) in [(0, 1.0 - fy), (1, fy)] {
                    let p = at(ix + dx, iy + dy);
                    for c in 0..2 {
                        v[c] += p[c] * wx * wy;
                    }
                }
            }
            v
        }
        _ => unreachable!("Displacement sampling was validated"),
    }
}
