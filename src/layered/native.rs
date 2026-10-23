//! Private native layers are prepared completely before any public blocks are written.
use super::{ImportOptions, Version, malformed, rows::Rows, unsupported};
use crate::{
    Error, assets,
    control::Control,
    model::*,
    sample_import::{
        NativeStore,
        pixels::{Builder, Prepared},
        source::Budget,
    },
};
use serde_json::{Value, json};

pub(super) struct Import {
    budget: Budget,
    layers: Vec<Prepared>,
}

impl Import {
    pub fn new(options: &ImportOptions, control: &Control) -> Result<Option<Self>, Error> {
        if options.resource_profile == ResourceProfile::LargeVector
            || (options.resource_profile == ResourceProfile::LargeRaster
                && options.storage.is_none())
        {
            return Err(unsupported(
                "Large layered canvases require resource_profile:large_raster and explicit native storage",
            ));
        }
        let Some(storage) = &options.storage else {
            return Ok(None);
        };
        if storage.storage_version != 2 {
            return Err(unsupported(
                "Native layered import requires block-manifest storage_version:2",
            ));
        }
        assets::absolute(&storage.store_root)?;
        crate::sample_store::check_root(Some(&storage.store_root), control)?;
        Ok(Some(Self {
            budget: Budget::new(crate::limits::layered::MAX_NATIVE_PIXELS as u64 * 4),
            layers: Vec::new(),
        }))
    }

    pub fn layer(
        &mut self,
        dimensions: [usize; 2],
        channels: Vec<(i16, super::input::Plane<'_>)>,
        version: Version,
        profile: Option<&[u8]>,
        control: &Control,
    ) -> Result<Content, Error> {
        let [width, height] = dimensions;
        let spec = crate::sample_store::Spec {
            width: width as u32,
            height: height as u32,
            depth: crate::samples::Depth::U8,
            channels: crate::samples::Channels::Rgba,
            encoding: crate::hdr::Encoding::EncodedSrgb,
        };
        spec.validate()?;
        let mut decoders = channels
            .into_iter()
            .map(|(id, bytes)| {
                Ok((
                    if id == -1 { 3 } else { id as usize },
                    Rows::new(bytes, width, height, version)?,
                ))
            })
            .collect::<Result<Vec<_>, Error>>()?;
        let source_profile = profile.map(|data| {
            use base64::Engine;
            crate::profiles::Profile::Icc {
                data: base64::engine::general_purpose::STANDARD.encode(data),
            }
        });
        let mut plane = vec![0; width];
        let candidate = Builder::from_rows(spec, &self.budget, control, |_, rgba| {
            rgba.fill(255);
            for (component, decoder) in &mut decoders {
                if *component > 3 {
                    return Err(malformed());
                }
                decoder.row(&mut plane, control)?;
                for (pixel, sample) in rgba.as_chunks_mut::<4>().0.iter_mut().zip(&plane) {
                    pixel[*component] = *sample;
                }
            }
            if let Some(profile) = &source_profile {
                let mut values = rgba.iter().map(|v| *v as f64 / 255.0).collect::<Vec<_>>();
                crate::profiles::convert_f64(
                    &mut values,
                    profile,
                    &crate::profiles::Profile::Builtin {
                        name: crate::profiles::Builtin::Srgb,
                    },
                    crate::profiles::Intent::RelativeColorimetric,
                    true,
                    Some(control),
                )?;
                for (out, value) in rgba.iter_mut().zip(values) {
                    *out = (value * 255.0).round() as u8;
                }
            }
            Ok(())
        })?;
        for (_, decoder) in decoders {
            decoder.finish(false, control)?;
        }
        let content = Content::StoredSamples {
            grid: Box::new(crate::stored_samples::Grid {
                storage_version: 2,
                base: candidate.manifest().clone(),
                patches: Vec::new(),
                profile: None,
                sampling: Default::default(),
                staged: None,
            }),
        };
        self.layers.push(candidate);
        Ok(content)
    }

    pub fn publish(self, storage: &NativeStore, control: &Control) -> Result<Value, Error> {
        let mut receipts = Vec::new();
        for layer in self.layers {
            let published = layer.publish(&storage.store_root, control)?;
            receipts.push(json!({"manifest_sha256":published.manifest.sha256,
                "created_tiles":published.created_tiles,"existing_tiles":published.existing_tiles,
                "decoded_bytes":published.manifest.spec.byte_len()?}));
        }
        Ok(
            json!({"kind":"native_tiles","storage_version":2,"store_root":storage.store_root,"layers":receipts}),
        )
    }
}
