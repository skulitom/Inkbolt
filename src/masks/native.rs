//! Windowed evaluation of scalar blocks with the inline mask's exact controls.
use super::*;
use crate::{
    control::Control,
    stored_scalars::{Grid, Reader},
};
use std::{
    cell::{Cell, RefCell},
    rc::Rc,
};

/// Shared by all item and filter masks in one prepared document.
#[derive(Clone, Default)]
pub(crate) struct Budget(Rc<Cell<u64>>);
impl Budget {
    fn charge(&self, work: u64) -> Result<(), Error> {
        let total = self.0.get().saturating_add(work);
        if total > MAX_FEATHER_WORK {
            return Err(limit(
                "Native mask windows exceed the cumulative feather work budget",
            ));
        }
        crate::objects::charge(work)?;
        self.0.set(total);
        Ok(())
    }
}

fn capacity(mask: &Mask) -> u64 {
    let [w, h] = mask.prepared_size();
    let edge = crate::scalar_store::TILE_EDGE;
    w.div_ceil(edge) as u64
        * (h.div_ceil(edge) as u64).min(crate::limits::masks::NATIVE_FILTER_CACHE_ROWS)
}

pub(super) fn buffer_values(mask: &Mask, grid: &Grid) -> u64 {
    let edge = crate::scalar_store::TILE_EDGE as u64;
    grid.cache_bytes().div_ceil(8)
        + if mask.feather == 0 {
            0
        } else {
            capacity(mask) * edge * edge + edge * (edge + 2 * mask.feather as u64) + edge * edge
        }
}

struct Tile {
    used: u64,
    width: u32,
    values: Vec<f64>,
}
#[derive(Default)]
struct Cache {
    clock: u64,
    tiles: BTreeMap<(u32, u32), Tile>,
}

pub(super) struct Prepared {
    source: Reader,
    mask: Mask,
    control: Control,
    budget: Budget,
    cache: RefCell<Cache>,
}
impl Prepared {
    pub(super) fn new(
        mask: &Mask,
        grid: &Grid,
        root: Option<&Path>,
        control: &Control,
        budget: Budget,
    ) -> Result<Self, Error> {
        Ok(Self {
            source: Reader::new(grid, root, control)?,
            mask: mask.clone(),
            control: control.clone(),
            budget,
            cache: RefCell::new(Cache::default()),
        })
    }
    fn raw(&self, x: i64, y: i64) -> Result<f64, Error> {
        let pad = self.mask.feather as i64 + 1;
        let x = x - pad;
        let y = y - pad;
        if x < 0 || y < 0 || x >= self.mask.width as i64 || y >= self.mask.height as i64 {
            return Ok(f64::from(!self.mask.clip));
        }
        let v = self.source.pixel(x as u32, y as u32)? as f64 / 255.0;
        Ok(if self.mask.invert { 1.0 - v } else { v })
    }
    fn density(&self, value: f64) -> f64 {
        (1.0 - self.mask.density * (1.0 - value)).clamp(0.0, 1.0)
    }
    pub(super) fn at(&self, x: u32, y: u32) -> Result<f64, Error> {
        if self.mask.feather == 0 {
            return self.raw(x as i64, y as i64).map(|v| self.density(v));
        }
        let edge = crate::scalar_store::TILE_EDGE;
        let key = (x / edge, y / edge);
        let mut cache = self.cache.borrow_mut();
        cache.clock += 1;
        let used = cache.clock;
        if used.is_multiple_of(crate::limits::control::PIXEL_CHECK_INTERVAL as u64) {
            self.control.check()?;
        }
        if !cache.tiles.contains_key(&key) {
            self.control.check()?;
            let [width, height] = self.mask.prepared_size();
            let left = key.0 * edge;
            let top = key.1 * edge;
            let w = edge.min(width - left);
            let h = edge.min(height - top);
            let r = self.mask.feather as i64;
            let rows = h as usize + 2 * r as usize;
            self.budget
                .charge(w as u64 * (rows as u64 + h as u64) * (2 * r as u64 + 1))?;
            if cache.tiles.len() >= capacity(&self.mask) as usize {
                let oldest = *cache.tiles.iter().min_by_key(|(_, t)| t.used).unwrap().0;
                cache.tiles.remove(&oldest);
            }
            let denominator = ((r + 1) * (r + 1)) as f64;
            let mut horizontal = vec![0.0; w as usize * rows];
            for row in 0..rows {
                self.control.check()?;
                let sy = top as i64 + row as i64 - r;
                for column in 0..w {
                    let mut sum = 0.0;
                    for d in -r..=r {
                        sum += self.raw(left as i64 + column as i64 + d, sy)?
                            * (r + 1 - d.abs()) as f64;
                    }
                    horizontal[row * w as usize + column as usize] = sum / denominator;
                }
            }
            let mut values = vec![0.0; w as usize * h as usize];
            for row in 0..h as usize {
                self.control.check()?;
                for column in 0..w as usize {
                    let mut sum = 0.0;
                    for d in -r..=r {
                        sum += horizontal[(row + (d + r) as usize) * w as usize + column]
                            * (r + 1 - d.abs()) as f64;
                    }
                    values[row * w as usize + column] = self.density(sum / denominator);
                }
            }
            cache.tiles.insert(
                key,
                Tile {
                    used,
                    width: w,
                    values,
                },
            );
        }
        let tile = cache.tiles.get_mut(&key).unwrap();
        tile.used = used;
        Ok(tile.values[((y % edge) * tile.width + x % edge) as usize])
    }
}
