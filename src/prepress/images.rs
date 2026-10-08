//! Native process-image sources: reconstruct retained RGB, then separate it.
use super::*;

pub const MAX_SOURCE_PROFILES: usize = 16;
pub(super) struct Sources {
    assets: BTreeMap<String, assets::Pixels>,
    converters: BTreeMap<String, profiles::cmyk::SourceConverter>,
    profiles: BTreeMap<String, String>,
    raw: BTreeMap<String, crate::samples::Grid>,
    pub receipts: Vec<Value>,
}
pub(super) fn prepare(
    document: &Document,
    resources: &Resources,
    converter: &profiles::cmyk::PaintConverter,
    control: &Control,
) -> Result<Sources, Error> {
    control.check()?;
    let mut result = Sources {
        assets: assets::resolve(document, resources.asset_root.as_deref())?,
        converters: BTreeMap::new(),
        profiles: BTreeMap::new(),
        raw: BTreeMap::new(),
        receipts: Vec::new(),
    };
    for (i, item) in document.items.iter().enumerate() {
        if !scene::effective_visible(document, i)? {
            continue;
        }
        control.check()?;
        let mut receipt = match &item.content {
            Content::Raster {
                width,
                height,
                rgba_hex,
                sampling,
            } => {
                json!({"id":item.id,"type":"raster","native_size":[width,height],"depth":"u8","channels":"rgba","sampling":sampling,"sample_sha256":assets::sha256(&crate::render::unhex(rgba_hex))})
            }
            Content::Image {
                asset_id,
                crop,
                sampling,
                ..
            } => {
                let asset = &document.assets[asset_id];
                json!({"id":item.id,"type":"image","asset_id":asset_id,"native_size":[asset.width,asset.height],"depth":"u8","channels":"rgba","sampling":sampling,"crop":crop,"asset_sha256":asset.sha256})
            }
            Content::Samples { grid } => {
                let mut r = json!({"id":item.id,"type":"samples","native_size":[grid.width,grid.height],"depth":grid.depth,"channels":grid.channels,"sampling":grid.sampling,"sample_sha256":assets::sha256(&crate::render::unhex(&grid.data_hex))});
                if let Some(profile) = &grid.profile {
                    let bytes = profiles::resolve(profile)?.0;
                    let hash = assets::sha256(&bytes);
                    if !result.converters.contains_key(&hash) {
                        if result.converters.len() >= MAX_SOURCE_PROFILES {
                            return Err(limit(
                                "Native image preparation supports at most 16 distinct source profiles",
                            ));
                        }
                        result
                            .converters
                            .insert(hash.clone(), converter.source(profile)?);
                    }
                    result.profiles.insert(item.id.clone(), hash.clone());
                    r["source_profile"] =
                        json!({"sha256":hash,"bytes":bytes.len(),"retained":true});
                }
                r
            }
            Content::Raw { raw } => {
                let grid = raw.grid(control)?;
                let recipe_data = crate::raw::retained::recipe_data(&raw.recipe)?;
                let r = json!({"id":item.id,"type":"raw","native_size":[grid.width,grid.height],"depth":grid.depth,"channels":grid.channels,"sampling":grid.sampling,"sample_sha256":assets::sha256(&crate::render::unhex(&grid.data_hex)),"source_sha256":raw.recipe.source_sha256,"source_bytes":raw.source_hex.len()/2,"recipe_sha256":assets::sha256(recipe_data.as_bytes()),"recipe":raw.recipe,"development":raw_receipt()});
                result.raw.insert(item.id.clone(), grid);
                r
            }
            _ => continue,
        };
        receipt["sampling_space"] = json!(if result.profiles.contains_key(&item.id) {
            "retained_profile_RGB"
        } else {
            "encoded_sRGB"
        });
        receipt["conversion"] = json!({"target":"declared_CMYK_profile","intent":converter.process.intent,"order":"reconstruct_associated_source_RGB_then_separate_straight_RGB_then_compose_native_inks","alpha":"retained_separately","spot_behavior":"knockout_at_source_alpha","source_changed":false});
        if let Some(warp) = &item.pixel_warp {
            receipt["pixel_warp"] = json!({"controls":warp,"evaluation":pixel_warps_receipt()});
        }
        result.receipts.push(receipt);
    }
    control.check()?;
    Ok(result)
}

impl Context<'_> {
    pub(super) fn image(
        &self,
        item: &Item,
        world: Matrix,
        surface: &mut Surface,
    ) -> Result<(), Error> {
        let warp = crate::pixel_warps::plan(item)?;
        let decoded;
        let inline;
        let (source, crop, frame, sampling): (&dyn crate::samples::Source, _, _, _) =
            match &item.content {
                Content::Raster {
                    width,
                    height,
                    rgba_hex,
                    sampling,
                } => {
                    inline = assets::Pixels {
                        width: *width,
                        height: *height,
                        rgba: crate::render::unhex(rgba_hex),
                    };
                    (
                        &inline,
                        assets::crop(*width, *height, None)?,
                        [*width as f64, *height as f64],
                        *sampling,
                    )
                }
                Content::Image {
                    asset_id,
                    width,
                    height,
                    crop,
                    sampling,
                } => {
                    let pixels = &self.images.assets[asset_id];
                    (
                        pixels,
                        assets::crop(pixels.width, pixels.height, *crop)?,
                        [*width, *height],
                        *sampling,
                    )
                }
                Content::Samples { .. } | Content::Raw { .. } => {
                    let grid = match &item.content {
                        Content::Samples { grid } => grid.as_ref(),
                        Content::Raw { .. } => &self.images.raw[&item.id],
                        _ => unreachable!("Normalized source grid"),
                    };
                    // Keep encoded profile values at their original precision. A
                    // display-space decode here could clip printable source colors.
                    let values = crate::samples::decode_values(&grid.data_hex, grid.depth);
                    let rgba = values
                        .chunks_exact(grid.channels.count())
                        .flat_map(|p| match grid.channels {
                            crate::samples::Channels::Rgba => [p[0], p[1], p[2], p[3]],
                            crate::samples::Channels::GrayAlpha => [p[0], p[0], p[0], p[1]],
                        })
                        .collect();
                    decoded = crate::samples::Decoded::from_samples(grid.width, rgba, false);
                    (
                        &decoded,
                        assets::crop(grid.width, grid.height, None)?,
                        [grid.width as f64, grid.height as f64],
                        grid.sampling,
                    )
                }
                _ => unreachable!("Prepared native image source"),
            };
        let rgba = crate::render::image_pixels(
            source,
            crop,
            frame,
            sampling,
            (
                [self.width, self.height, self.scale],
                self.antialias,
                Some(self.control),
            ),
            world,
            warp.as_ref(),
        )?;
        self.image_rgba(&item.id, &rgba, surface)
    }
    pub(super) fn image_rgba(
        &self,
        id: &str,
        rgba: &[f64],
        surface: &mut Surface,
    ) -> Result<(), Error> {
        let n = self.channels();
        let mut values = vec![0.0; n];
        let addressed = vec![true; n];
        let converter = self
            .images
            .profiles
            .get(id)
            .map(|id| &self.images.converters[id]);
        for (batch, row) in rgba.chunks(4096 * 4).enumerate() {
            self.control.check()?;
            let rgb: Vec<f64> = row
                .as_chunks::<4>()
                .0
                .iter()
                .flat_map(|p| {
                    std::array::from_fn::<_, 3, _>(|c| if p[3] == 0.0 { 0.0 } else { p[c] / p[3] })
                })
                .collect();
            let inks = if let Some(converter) = converter {
                converter.convert(&rgb)?
            } else {
                self.converter.rgb(&rgb)?
            };
            for (j, (p, cmyk)) in row
                .as_chunks::<4>()
                .0
                .iter()
                .zip(inks.as_chunks::<4>().0)
                .enumerate()
            {
                values[..4].copy_from_slice(cmyk);
                surface.paint(batch * 4096 + j, &values, &addressed, p[3]);
            }
        }
        Ok(())
    }
}
