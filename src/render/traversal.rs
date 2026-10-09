//! Visit neighboring small tiles together without allocating a larger surface.
pub const NEIGHBORHOOD_UNITS: u32 = 256;
pub(super) struct Plan {
    size: [u32; 2],
    edge: u32,
    neighborhood: u32,
    pub rows: u32,
    tile_rows: u32,
    pub total: u64,
}
impl Plan {
    pub fn new(size: [u32; 2], edge: u32, scale: u32, max_rows: u32) -> Self {
        let neighborhood = NEIGHBORHOOD_UNITS * scale;
        let rows = max_rows.max(1).min(neighborhood);
        // Keep the original composition grid, including when a codec requires
        // shorter bands. Neighborhood width is divisible by every tile edge.
        let rows = if rows >= edge {
            rows / edge * edge
        } else {
            rows
        };
        let tile_rows = edge.min(rows);
        Self {
            size,
            edge,
            neighborhood,
            rows,
            tile_rows,
            total: u64::from(size[0].div_ceil(edge)) * u64::from(size[1].div_ceil(tile_rows)),
        }
    }
    pub fn tiles(&self) -> impl Iterator<Item = ([u32; 2], [u32; 2])> {
        let [width, height] = self.size;
        (0..height)
            .step_by(self.rows as usize)
            .flat_map(move |band| {
                let bottom = (band + self.rows).min(height);
                (0..width)
                    .step_by(self.neighborhood as usize)
                    .flat_map(move |block| {
                        let right = (block + self.neighborhood).min(width);
                        (band..bottom)
                            .step_by(self.tile_rows as usize)
                            .flat_map(move |y| {
                                (block..right).step_by(self.edge as usize).map(move |x| {
                                    (
                                        [x, y],
                                        [self.edge.min(right - x), self.tile_rows.min(bottom - y)],
                                    )
                                })
                            })
                    })
            })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn every_pixel_is_written_once_in_complete_bands_including_short_codec_rows() {
        for edge in [2, 4, 8, 32, 64, 128] {
            for rows in [1, 3, 8, 71, 255, 256, 1000] {
                let plan = Plan::new([519, 271], edge, 1, rows);
                let mut seen = vec![false; 519 * 271];
                let mut count = 0;
                let mut band_pixels = 0;
                for ([x, y], [w, h]) in plan.tiles() {
                    count += 1;
                    assert!(w <= edge && h <= edge && h <= rows);
                    band_pixels += w * h;
                    for py in y..y + h {
                        for px in x..x + w {
                            assert!(!std::mem::replace(
                                &mut seen[(py * 519 + px) as usize],
                                true
                            ));
                        }
                    }
                    let band = y / plan.rows * plan.rows;
                    if x + w == 519 && y + h == (band + plan.rows).min(271) {
                        assert_eq!(band_pixels, 519 * plan.rows.min(271 - band));
                        band_pixels = 0;
                    }
                }
                assert!(seen.into_iter().all(|p| p));
                assert_eq!(count, plan.total);
                assert_eq!(band_pixels, 0);
            }
        }
    }
    #[test]
    fn wide_identity_sources_reuse_the_fixed_sixteen_block_cache() {
        for scale in [1, 2, 4] {
            for factor in [1, 2, 4] {
                let plan = Plan::new([2560 * scale, 273 * scale], 8 / factor, scale, u32::MAX);
                let mut cache = std::collections::BTreeMap::new();
                let mut decoded = 0;
                for (tick, ([x, y], [w, h])) in plan.tiles().enumerate() {
                    for by in y / scale / 128..=((y + h - 1) / scale) / 128 {
                        for bx in x / scale / 128..=((x + w - 1) / scale) / 128 {
                            let key = by * 20 + bx;
                            if !cache.contains_key(&key) {
                                if cache.len() == 16 {
                                    let oldest =
                                        *cache.iter().min_by_key(|(_, time)| *time).unwrap().0;
                                    cache.remove(&oldest);
                                }
                                decoded += 128 * (273 - by * 128).min(128);
                            }
                            cache.insert(key, tick);
                        }
                    }
                }
                assert_eq!(decoded, 2560 * 273);
            }
        }
    }
}
