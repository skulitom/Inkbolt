//! Editable scalar coverage, independent of artwork color and alpha.
use crate::{Error, assets::Sampling, geometry, model::*, scene};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

pub const MAX_FEATHER: u32 = 32;
pub const MAX_PREPARED_PIXELS: u64 = 262_144;
pub const MAX_DOCUMENT_PIXELS: u64 = 1_048_576;
pub const MAX_FEATHER_WORK: u64 = 67_108_864;
fn yes() -> bool {
    true
}
fn one() -> f64 {
    1.0
}
fn is_false(value: &bool) -> bool {
    !value
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Mask {
    /// An empty authored plane with uniform outside coverage, not fabricated pixels.
    #[serde(default, skip_serializing_if = "is_false")]
    pub constant: bool,
    pub width: u32,
    pub height: u32,
    pub gray_hex: String,
    #[serde(default = "identity")]
    pub transform: Matrix,
    #[serde(default = "yes")]
    pub linked: bool,
    #[serde(default = "yes")]
    pub enabled: bool,
    #[serde(default = "yes")]
    pub clip: bool,
    #[serde(default)]
    pub invert: bool,
    #[serde(default = "one")]
    pub density: f64,
    #[serde(default)]
    pub feather: u32,
    #[serde(default)]
    pub sampling: Sampling,
}

impl Mask {
    pub fn world_transform(&self, item_world: Matrix) -> Matrix {
        if self.linked {
            geometry::multiply(item_world, self.transform)
        } else {
            self.transform
        }
    }
    pub fn prepared_size(&self) -> [u32; 2] {
        // One additional constant pixel on every edge defines bilinear sampling at the boundary.
        let pad = 2 * (self.feather + 1);
        [self.width + pad, self.height + pad]
    }
    pub fn validate(&self, item_world: Matrix) -> Result<usize, Error> {
        if self.sampling.advanced() {
            return Err(Error::new(
                "UNSUPPORTED",
                "Scalar masks currently support nearest and bilinear sampling",
            ));
        }
        if if self.constant {
            self.width != 0 || self.height != 0
        } else {
            !(1..=MAX_DIMENSION).contains(&self.width)
                || !(1..=MAX_DIMENSION).contains(&self.height)
        } {
            return Err(invalid(
                "Plane masks need dimensions in 1..=32768; explicit constant masks need zero dimensions",
            ));
        }
        let pixels = self.width as usize * self.height as usize;
        if pixels > MAX_STORED_PIXELS {
            return Err(limit("Mask exceeds inline pixel storage limit"));
        }
        if self.gray_hex.len() != pixels * 2
            || !self.gray_hex.bytes().all(|c| c.is_ascii_hexdigit())
        {
            return Err(invalid(
                "Mask data must contain exactly width*height grayscale8 hex values",
            ));
        }
        if !self.density.is_finite()
            || !(0.0..=1.0).contains(&self.density)
            || self.feather > MAX_FEATHER
        {
            return Err(invalid(
                "Mask density must be in 0..=1 and feather radius in 0..=32 mask pixels",
            ));
        }
        geometry::validate_matrix(self.transform)?;
        let world = self.world_transform(item_world);
        geometry::validate_matrix(world)?;
        let [width, height] = self.prepared_size();
        if width as u64 * height as u64 > MAX_PREPARED_PIXELS {
            return Err(limit("Prepared mask exceeds 262144 pixels"));
        }
        let pad = (self.feather + 1) as f64;
        validate_world_geometry(
            &Geometry::Rect {
                x: -pad,
                y: -pad,
                width: width as f64,
                height: height as f64,
            },
            world,
        )?;
        Ok(pixels)
    }
}

/// Aggregate limits include disabled masks, so switching a mask on cannot evade the budget.
pub(crate) fn validate_budget(document: &Document) -> Result<(), Error> {
    let mut pixels = 0;
    let mut work = 0;
    for mask in document.items.iter().flat_map(|i| {
        i.mask
            .iter()
            .chain(i.filters.iter().filter_map(|f| f.mask.as_ref()))
    }) {
        let [w, h] = mask.prepared_size();
        let n = w as u64 * h as u64;
        pixels += n;
        work += n * if mask.feather == 0 {
            1
        } else {
            2 * (2 * mask.feather as u64 + 1)
        };
    }
    if pixels > MAX_DOCUMENT_PIXELS || work > MAX_FEATHER_WORK {
        return Err(limit(
            "Masks exceed document preparation memory or feather work limit",
        ));
    }
    Ok(())
}

pub(crate) struct Prepared {
    pub width: u32,
    pub height: u32,
    pub pad: u32,
    pub values: Vec<f64>,
    pub outside: f64,
    inverse: Matrix,
    sampling: Sampling,
}
impl Prepared {
    fn at(&self, x: i64, y: i64) -> f64 {
        if x < 0 || y < 0 || x >= self.width as i64 || y >= self.height as i64 {
            self.outside
        } else {
            self.values[y as usize * self.width as usize + x as usize]
        }
    }
    pub fn sample(&self, world: Point) -> f64 {
        let p = geometry::map(self.inverse, world);
        let x = p[0] + self.pad as f64;
        let y = p[1] + self.pad as f64;
        // Bound before converting to integers or adding neighbor offsets.
        if x < -1.0 || y < -1.0 || x > self.width as f64 + 1.0 || y > self.height as f64 + 1.0 {
            return self.outside;
        }
        match self.sampling {
            Sampling::Nearest => {
                self.at(crate::assets::pixel_index(x), crate::assets::pixel_index(y))
            }
            Sampling::Bilinear => {
                let x = x - 0.5;
                let y = y - 0.5;
                let ix = x.floor() as i64;
                let iy = y.floor() as i64;
                let fx = x - ix as f64;
                let fy = y - iy as f64;
                (self.at(ix, iy) * (1.0 - fx) + self.at(ix + 1, iy) * fx) * (1.0 - fy)
                    + (self.at(ix, iy + 1) * (1.0 - fx) + self.at(ix + 1, iy + 1) * fx) * fy
            }
            _ => unreachable!("Mask sampling was validated"),
        }
    }
}

pub(crate) fn prepare(mask: &Mask, item_world: Matrix) -> Result<Prepared, Error> {
    mask.validate(item_world)?;
    let [width, height] = mask.prepared_size();
    let pad = mask.feather + 1;
    let outside = f64::from(!mask.clip);
    let mut values = vec![outside; width as usize * height as usize];
    let source = crate::render::unhex(&mask.gray_hex);
    for y in 0..mask.height as usize {
        for x in 0..mask.width as usize {
            let v = source[y * mask.width as usize + x] as f64 / 255.0;
            values[(y + pad as usize) * width as usize + x + pad as usize] =
                if mask.invert { 1.0 - v } else { v };
        }
    }
    if mask.feather != 0 {
        let r = mask.feather as i64;
        let denom = ((r + 1) * (r + 1)) as f64;
        let mut temporary = vec![outside; values.len()];
        for horizontal in [true, false] {
            for y in 0..height as i64 {
                for x in 0..width as i64 {
                    let mut sum = 0.0;
                    for d in -r..=r {
                        let sx = x + if horizontal { d } else { 0 };
                        let sy = y + if horizontal { 0 } else { d };
                        let v = if sx < 0 || sy < 0 || sx >= width as i64 || sy >= height as i64 {
                            outside
                        } else {
                            values[sy as usize * width as usize + sx as usize]
                        };
                        sum += v * (r + 1 - d.abs()) as f64;
                    }
                    temporary[y as usize * width as usize + x as usize] = sum / denom;
                }
            }
            std::mem::swap(&mut values, &mut temporary);
        }
    }
    for v in &mut values {
        *v = (1.0 - mask.density * (1.0 - *v)).clamp(0.0, 1.0);
    }
    Ok(Prepared {
        width,
        height,
        pad,
        values,
        outside: 1.0 - mask.density * (1.0 - outside),
        inverse: geometry::inverse(mask.world_transform(item_world))?,
        sampling: mask.sampling,
    })
}

pub(crate) fn prepare_document(document: &Document) -> Result<BTreeMap<String, Prepared>, Error> {
    document
        .items
        .iter()
        .enumerate()
        .filter_map(|(i, item)| {
            item.mask.as_ref().filter(|m| m.enabled).map(|m| {
                let world = scene::world_transform(document, i)?;
                prepare(m, world)
                    .map(|p| (item.id.clone(), p))
                    .map_err(|e| e.at_item(&item.id))
            })
        })
        .collect()
}

/// Commit coverage into a finite pixel plane at its native sample centers.
/// World-space mask evaluation precedes quantization; geometry/opacity/blending stay separate.
pub(crate) fn apply_pixels(
    document: &mut Document,
    index: usize,
    asset_root: Option<&std::path::Path>,
) -> Result<(), Error> {
    if document.kind != DocumentKind::Raster {
        return Err(Error::new(
            "UNSUPPORTED",
            "Permanent mask application requires a raster document",
        ));
    }
    let item = &document.items[index];
    crate::pixel_warps::reject_native(item)?;
    let mask = item
        .mask
        .as_ref()
        .ok_or_else(|| Error::new("INVALID_OPERATION", "Item has no opacity mask"))?;
    if !mask.enabled {
        return Err(Error::new(
            "INVALID_OPERATION",
            "Enable the mask before applying it, or remove it to discard its settings",
        ));
    }
    let world = scene::world_transform(document, index)?;
    let prepared = prepare(mask, world)?;
    let (width, height, grid, sampling) = match &item.content {
        Content::Raster {
            width,
            height,
            sampling,
            ..
        } => (*width, *height, identity(), *sampling),
        Content::Fill { width, height, .. } => (*width, *height, identity(), Sampling::Nearest),
        Content::Image {
            asset_id,
            width,
            height,
            crop,
            sampling,
        } => {
            let asset = &document.assets[asset_id];
            let crop = crate::assets::crop(asset.width, asset.height, *crop)?;
            (
                crop.width,
                crop.height,
                [
                    *width / crop.width as f64,
                    0.0,
                    0.0,
                    *height / crop.height as f64,
                    0.0,
                    0.0,
                ],
                *sampling,
            )
        }
        _ => {
            return Err(Error::new(
                "UNSUPPORTED",
                "Permanent mask application requires a pixel layer, placed image or procedural fill; other content needs explicit rasterization first",
            ));
        }
    };
    let count = width as usize * height as usize;
    if count > MAX_STORED_PIXELS {
        return Err(limit("Applied mask output exceeds inline pixel limit"));
    }
    let source: Vec<[f64; 4]> = match &item.content {
        Content::Raster { rgba_hex, .. } => crate::render::unhex(rgba_hex)
            .as_chunks::<4>()
            .0
            .iter()
            .map(|p| p.map(|v| v as f64 / 255.0))
            .collect(),
        Content::Image { asset_id, crop, .. } => {
            let pixels = crate::assets::load(&document.assets[asset_id], asset_root)
                .map_err(|e| e.at_asset(asset_id))?;
            let crop = crate::assets::crop(pixels.width, pixels.height, *crop)?;
            pixels
                .cropped(crop)
                .as_chunks::<4>()
                .0
                .iter()
                .map(|p| p.map(|v| v as f64 / 255.0))
                .collect()
        }
        Content::Fill { paint, dither, .. } => {
            if count as u64 * crate::paint::work(paint) > crate::paint::MAX_PAINT_WORK {
                return Err(limit("Applied fill exceeds paint work budget"));
            }
            let sampler = crate::paint::Sampler::new(paint, identity())?;
            (0..count)
                .map(|i| {
                    let p = [
                        (i % width as usize) as f64 + 0.5,
                        (i / width as usize) as f64 + 0.5,
                    ];
                    crate::paint::dither(sampler.sample(p), p, *dither)
                })
                .collect()
        }
        _ => unreachable!(),
    };
    let grid_world = geometry::multiply(world, grid);
    let byte = |v: f64| (v.clamp(0.0, 1.0) * 255.0).round() as u8;
    let mut pixels = Vec::with_capacity(count * 4);
    for (i, color) in source.iter().enumerate() {
        let point = [
            (i % width as usize) as f64 + 0.5,
            (i / width as usize) as f64 + 0.5,
        ];
        let alpha = byte(color[3] * prepared.sample(geometry::map(grid_world, point)));
        if alpha == 0 {
            pixels.extend_from_slice(&[0; 4]);
        } else {
            pixels.extend_from_slice(&[byte(color[0]), byte(color[1]), byte(color[2]), alpha]);
        }
    }
    let item = &mut document.items[index];
    item.transform = geometry::multiply(item.transform, grid);
    if let Some(clip) = &mut item.clip {
        clip.transform = geometry::multiply(geometry::inverse(grid)?, clip.transform);
    }
    item.content = Content::Raster {
        width,
        height,
        rgba_hex: crate::render::hex(&pixels),
        sampling,
    };
    item.mask = None;
    Ok(())
}
