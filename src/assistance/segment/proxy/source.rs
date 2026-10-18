use super::*;
use crate::{native_pixels as native, native_pixels::Budget, samples::Depth};

// Global sampling decodes source blocks under the preparation budget. Feature
// construction and the two graph solves still share the original local budget.
struct Preparation<'a, 'b>(&'a mut Work<'b>);
impl Budget for Preparation<'_, '_> {
    fn charge(&mut self, pixels: usize) -> Result<(), Error> {
        self.prepare(pixels as u64)
    }
    fn control(&self) -> &Control {
        self.0.control
    }
    fn preparation(&mut self) -> &mut native::Preparation {
        &mut self.0.preparation
    }
}

enum Data<'a> {
    Native(native::Pixels<'a>),
    Asset {
        pixels: assets::Pixels,
        crop: assets::Crop,
    },
}

pub(super) struct Source<'a> {
    data: Data<'a>,
    pub region: crate::sample_store::Region,
    pub transform: Matrix,
    pub scale: u64,
    pub description: Value,
    pub memory: u64,
}

impl<'a> Source<'a> {
    pub fn new(
        document: &Document,
        id: &str,
        requested: Option<crate::sample_store::Region>,
        root: Option<&'a Path>,
        options: &Options,
        work: &mut Work<'_>,
    ) -> Result<Self, Error> {
        let item = &document.items[scene::index(document, id)?];
        crate::pixel_warps::reject_native(item)?;
        if let Content::Image {
            asset_id,
            width,
            height,
            crop,
            ..
        } = &item.content
        {
            let asset = &document.assets[asset_id];
            let crop = assets::crop(asset.width, asset.height, *crop)?;
            let region = region(crop.width, crop.height, requested)?;
            let memory = asset.width as u64 * asset.height as u64 * 16
                + match &asset.storage {
                    assets::Storage::Encoded { data_base64, .. } => {
                        data_base64.len() as u64 * 3 / 4
                    }
                    _ => 0,
                };
            admit(
                Grid::new(region.width, region.height, options.step)?.len(),
                0,
                memory,
                false,
            )?;
            work.prepare(asset.width as u64 * asset.height as u64 * 3)?;
            let pixels = assets::load(asset, root)?;
            let sx = width / crop.width as f64;
            let sy = height / crop.height as f64;
            return Ok(Self {
                data: Data::Asset { pixels, crop },
                region,
                transform: [sx, 0.0, 0.0, sy, region.x as f64 * sx, region.y as f64 * sy],
                scale: 1,
                memory,
                description: json!({"kind":"rgba8_image_asset","sha256":asset.sha256,"width":asset.width,"height":asset.height,"crop":crop,"feature_bits":8}),
            });
        }
        if !matches!(
            item.content,
            Content::Raster { .. } | Content::Samples { .. } | Content::StoredSamples { .. }
        ) {
            return Err(Error::new(
                "UNSUPPORTED",
                "Proxy selection requires native pixels or a verified image asset",
            ));
        }
        if let Content::Samples { grid } = &item.content
            && grid.profile.is_some()
        {
            return Err(Error::new(
                "PROFILE_CONVERSION_REQUIRED",
                "Selection requires explicit sample_profile conversion to working sRGB",
            ));
        }
        let spec = native::spec(&item.content)?;
        let region = region(spec.width, spec.height, requested)?;
        let memory = native::memory(&item.content);
        admit(
            Grid::new(region.width, region.height, options.step)?.len(),
            0,
            memory,
            false,
        )?;
        let pixels = native::Pixels::new(
            &item.content,
            root,
            "UNSUPPORTED_ASSISTANCE_ENCODING",
            &mut Preparation(work),
        )?;
        let bits = if spec.depth == Depth::U8 { 8 } else { 16 };
        let description = json!({"kind":pixels.identity_kind,"sha256":pixels.identity,"samples":spec,"feature_bits":bits,
            "feature_construction":"rounded_premultiplied_encoded_RGB_plus_alpha",
            "analysis_quantization":if spec.depth == Depth::F32 {json!({"method":"exact_binary32_premultiplication_then_u16_feature_rounding","maximum_feature_rounding_error":0.5/65535.0,"source_converted":false})} else {Value::Null}});
        Ok(Self {
            data: Data::Native(pixels),
            region,
            transform: [1.0, 0.0, 0.0, 1.0, region.x as f64, region.y as f64],
            scale: if bits == 8 { 1 } else { 257 * 257 },
            description,
            memory,
        })
    }

    pub fn features(
        &mut self,
        coordinates: &[[u32; 2]],
        work: &mut Work<'_>,
    ) -> Result<Vec<[i64; 4]>, Error> {
        let edge = crate::sample_store::TILE_EDGE;
        let mut order: Vec<_> = coordinates
            .iter()
            .enumerate()
            .map(|(i, &[x, y])| {
                let (x, y) = (x + self.region.x, y + self.region.y);
                ((y / edge, x / edge, y, x), i)
            })
            .collect();
        work.add(coordinates.len() as u64 * (coordinates.len().max(1).ilog2() as u64 + 1))?;
        order.sort_unstable();
        let mut features = vec![[0; 4]; coordinates.len()];
        for ((_, _, y, x), index) in order {
            work.add(4)?;
            features[index] = match &mut self.data {
                Data::Native(pixels) => {
                    let raw = pixels.raw(x as usize, y as usize, &mut Preparation(work))?;
                    super::super::input::native_feature(&raw, pixels.spec)?
                }
                Data::Asset { pixels, crop } => {
                    let at =
                        ((y + crop.y) as usize * pixels.width as usize + (x + crop.x) as usize) * 4;
                    feature(pixels.rgba[at..at + 4].try_into().unwrap())
                }
            };
        }
        Ok(features)
    }
}

fn region(
    width: u32,
    height: u32,
    requested: Option<crate::sample_store::Region>,
) -> Result<crate::sample_store::Region, Error> {
    let r = requested.unwrap_or(crate::sample_store::Region {
        x: 0,
        y: 0,
        width,
        height,
    });
    if r.width == 0
        || r.height == 0
        || r.x as u64 + r.width as u64 > width as u64
        || r.y as u64 + r.height as u64 > height as u64
    {
        return Err(invalid(
            "Selection region must be nonempty and inside the cropped native grid",
        ));
    }
    Ok(r)
}
