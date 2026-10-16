//! Existing TIFF pixels and codec layout with caller-owned encoded storage.
use super::*;
use std::io::{Seek, Write};
mod encoding;
pub(crate) use encoding::Encoding;

pub(crate) fn export(
    document: &Document,
    scale: u32,
    resources: &Resources,
    options: Option<&Options>,
    metadata: Option<&str>,
    context: (
        Option<&crate::render_quality::Options>,
        &crate::control::Control,
    ),
) -> Result<Value, Error> {
    let mut sink = crate::publish::payload::SeekSink::memory(context.1);
    let artifact = write(
        document, scale, resources, options, metadata, context, &mut sink,
    );
    let bytes = sink.finish()?;
    let mut artifact = artifact?;
    artifact["data"] = json!(STANDARD.encode(bytes.into_memory()));
    Ok(artifact)
}

pub(crate) fn write(
    document: &Document,
    scale: u32,
    resources: &Resources,
    options: Option<&Options>,
    metadata: Option<&str>,
    (render_options, control): (
        Option<&crate::render_quality::Options>,
        &crate::control::Control,
    ),
    output: &mut (impl Write + Seek),
) -> Result<Value, Error> {
    write_encoding(
        document,
        scale,
        resources,
        options,
        metadata,
        (render_options, control),
        &mut Encoding::once(output, control),
    )
}

pub(crate) fn preflight(
    document: &Document,
    scale: u32,
    resources: &Resources,
    options: Option<&Options>,
    metadata: Option<&str>,
    context: (
        Option<&crate::render_quality::Options>,
        &crate::control::Control,
    ),
) -> Result<(Value, crate::publish::payload::Payload), Error> {
    let mut encoding = Encoding::preflight(context.1);
    let artifact = write_encoding(
        document,
        scale,
        resources,
        options,
        metadata,
        context,
        &mut encoding,
    )?;
    Ok((artifact, encoding.finish()?))
}

fn write_encoding(
    document: &Document,
    scale: u32,
    resources: &Resources,
    options: Option<&Options>,
    metadata: Option<&str>,
    (render_options, control): (
        Option<&crate::render_quality::Options>,
        &crate::control::Control,
    ),
    output: &mut Encoding<'_>,
) -> Result<Value, Error> {
    validate_options(ExportFormat::Tiff, options)?;
    let defaults = Options::default();
    let options = options.unwrap_or(&defaults);
    if options.depth.is_some() || options.channels.is_some() {
        if matches!(options.alpha, Some(Alpha::Associated)) {
            return Err(unsupported(
                "Associated TIFF delivery currently requires the RGBA8 image path; explicit native-depth delivery retains unassociated alpha",
            ));
        }
        return crate::sample_tiff::write(
            document,
            scale,
            resources,
            options,
            metadata,
            (render_options, control),
            output,
        );
    }
    let mut p = crate::render::rasterize_controlled(
        document,
        scale,
        resources.asset_root.as_deref(),
        resources.font_root.as_deref(),
        render_options,
        control,
    )?;
    let profile = crate::profiles::output(document, &mut p.rgba)?;
    let ppi = document.resolution_ppi * scale as f64;
    let compression = options.compression.unwrap_or_default();
    let alpha = options.alpha.unwrap_or_default();
    if matches!(alpha, Alpha::Associated) {
        for pixel in p.rgba.as_chunks_mut::<4>().0 {
            let a = u32::from(pixel[3]);
            for v in &mut pixel[..3] {
                *v = ((u32::from(*v) * a + 127) / 255) as u8;
            }
        }
    }
    output.run(|mut output| {
        let method = match compression {
            Compression::None => tiff::encoder::Compression::Uncompressed,
            Compression::Lzw => tiff::encoder::Compression::Lzw,
            Compression::Deflate => tiff::encoder::Compression::Deflate(Default::default()),
        };
        let mut encoder = tiff::encoder::TiffEncoder::new(&mut output)
            .map_err(|_| Error::new("EXPORT_ERROR", "Unable to create TIFF"))?
            .with_compression(method);
        let mut image = encoder
            .new_image::<tiff::encoder::colortype::RGBA8>(p.width, p.height)
            .map_err(|_| Error::new("EXPORT_ERROR", "Unable to encode TIFF header"))?;
        if let Some(metadata) = metadata {
            image
                .encoder()
                .write_tag(
                    Tag::ImageDescription,
                    format!("{}{}", crate::metadata::TEXT_PREFIX, metadata).as_str(),
                )
                .map_err(|_| Error::new("EXPORT_ERROR", "Unable to encode TIFF metadata"))?;
        }
        if let Some((bytes, _)) = &profile {
            image
                .encoder()
                .write_tag(Tag::from_u16_exhaustive(34675), bytes.as_slice())
                .map_err(|_| Error::new("EXPORT_ERROR", "Unable to embed TIFF profile"))?;
        }
        image
            .encoder()
            .write_tag(
                Tag::ExtraSamples,
                &[if matches!(alpha, Alpha::Associated) {
                    1u16
                } else {
                    2u16
                }][..],
            )
            .map_err(|_| Error::new("EXPORT_ERROR", "Unable to encode TIFF alpha semantics"))?;
        image
            .encoder()
            .write_tag(Tag::Orientation, 1u16)
            .map_err(|_| Error::new("EXPORT_ERROR", "Unable to encode TIFF orientation"))?;
        image.resolution(
            tiff::tags::ResolutionUnit::Inch,
            tiff::encoder::Rational {
                n: (ppi * 1000.0).round() as u32,
                d: 1000,
            },
        );
        image
            .write_data(&p.rgba)
            .map_err(|_| Error::new("EXPORT_ERROR", "Unable to encode TIFF samples"))?;
        Ok(())
    })?;
    let losses = vec![if profile.is_some() {
        "TIFF stores converted RGBA8 samples with the exact embedded RGB profile and declared alpha mode. Relative colorimetric conversion clips gamut and quantizes RGB8 without black-point compensation; that conversion is not reversible. Editable layers require snapshots. Density is rounded to 0.001 pixels per inch."
    } else {
        "TIFF retains rendered RGBA8 with declared alpha mode; unassociated samples are lossless. Editable layers and source metadata require snapshots. Output uses untagged sRGB sample interpretation with no ICC profile; density is rounded to 0.001 pixels per inch."
    }];
    control.check()?;
    let mut artifact = json!({"media_type":"image/tiff","encoding":"base64",
        "width":p.width,"height":p.height,"color_space":"srgb",
        "settings":{"compression":compression,"alpha":alpha,"resolution_ppi":(ppi*1000.0).round()/1000.0},
        "losses":losses});
    if matches!(alpha, Alpha::Associated) {
        artifact["losses"].as_array_mut().unwrap().push(json!("Associated alpha multiplies encoded destination color by alpha and rounds to RGB8. Unassociation cannot recover hidden RGB or every low-alpha source value; alpha bytes remain exact."));
    }
    if let Some((_, summary)) = profile {
        artifact["color_profile"] = summary;
        artifact["color_space"] = json!("icc_rgb");
    }
    crate::swatches::annotate(document, &mut artifact)?;
    crate::samples::annotate(document, &mut artifact, crate::samples::Depth::U8);
    Ok(artifact)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{self, Cursor, SeekFrom};

    struct RejectBackpatch {
        bytes: Cursor<Vec<u8>>,
        rejected: bool,
    }
    impl Write for RejectBackpatch {
        fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
            if self.bytes.position() == 4 && self.bytes.get_ref().len() > 32 {
                self.rejected = true;
                return Err(io::Error::other("Original final TIFF pointer failure"));
            }
            self.bytes.write(bytes)
        }
        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }
    impl Seek for RejectBackpatch {
        fn seek(&mut self, at: SeekFrom) -> io::Result<u64> {
            self.bytes.seek(at)
        }
    }
    #[test]
    fn final_directory_pointer_failure_cannot_return_a_successful_artifact() {
        let document: Document = serde_json::from_value(json!({"schema_version":2,
            "id":"final-write","kind":"raster","width":2,"height":2,"color_space":"srgb"}))
        .unwrap();
        for (image_options, render_options) in [
            (None, None),
            (Some(json!({"depth":"u16"})), None),
            (
                Some(json!({"depth":"f32"})),
                Some(json!({"evaluation":"tiled"})),
            ),
        ] {
            let options: Option<Options> =
                image_options.map(|v| serde_json::from_value(v).unwrap());
            let render = render_options.map(|v| serde_json::from_value(v).unwrap());
            let mut output = RejectBackpatch {
                bytes: Cursor::new(Vec::new()),
                rejected: false,
            };
            let result = write(
                &document,
                1,
                &Resources::default(),
                options.as_ref(),
                None,
                (render.as_ref(), &crate::control::Control::default()),
                &mut output,
            );
            assert!(output.rejected);
            assert!(output.bytes.get_ref().len() > 32);
            assert_eq!(result.unwrap_err().code, "EXPORT_ERROR");
        }
    }
}
