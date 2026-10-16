//! Encode complete output bands without retaining a full tiled RGBA8 surface.
use crate::{Document, Error, control::Control, limits::png_output as limits};
use serde_json::{Value, json};
use std::{io::Write, path::Path};

fn error(_: impl std::fmt::Debug) -> Error {
    Error::new("EXPORT_ERROR", "Unable to finish PNG output stream")
}

pub(crate) fn write(
    document: &Document,
    scale: u32,
    roots: (Option<&Path>, Option<&Path>),
    options: Option<&crate::render_quality::Options>,
    metadata: Option<&str>,
    control: &Control,
    output: impl Write,
) -> Result<Value, Error> {
    let prepared =
        super::prepared::Prepared::new(document, scale, roots.0, roots.1, options, false, control)?;
    let [width, height] = prepared.sampling.output;
    let row_bytes = width as usize * 4;
    if row_bytes > limits::MAX_BAND_BYTES {
        return Err(crate::model::limit("PNG row exceeds codec band budget"));
    }
    let maximum_rows = (limits::MAX_BAND_BYTES / row_bytes) as u32;
    let tiled = prepared.sampling.options.evaluation == crate::render_quality::Evaluation::Tiled;
    let rows = if tiled {
        prepared.band_rows(maximum_rows)
    } else {
        maximum_rows
    };
    let profile = document
        .output_profile
        .as_ref()
        .map(|p| Ok::<_, Error>((crate::profiles::resolve(p)?.0, crate::profiles::summary(p)?)))
        .transpose()?;
    let mut encoder = if let Some((bytes, _)) = &profile {
        let mut info = png::Info::with_size(width, height);
        info.icc_profile = Some(std::borrow::Cow::Borrowed(bytes));
        png::Encoder::with_info(output, info).map_err(error)?
    } else {
        png::Encoder::new(output, width, height)
    };
    encoder.set_color(png::ColorType::Rgba);
    encoder.set_depth(png::BitDepth::Eight);
    if profile.is_none() {
        encoder.set_source_srgb(png::SrgbRenderingIntent::Perceptual);
    }
    let ppm = (document.resolution_ppi * scale as f64 / 0.0254).round() as u32;
    encoder.set_pixel_dims(Some(png::PixelDimensions {
        xppu: ppm,
        yppu: ppm,
        unit: png::Unit::Meter,
    }));
    let mut writer = encoder.write_header().map_err(error)?;
    {
        let mut stream = writer
            .stream_writer_with_size(limits::STREAM_CHUNK_BYTES)
            .map_err(error)?;
        let mut band = Vec::new();
        let mut write_band = |band: &mut [u8]| -> Result<(), Error> {
            control.check()?;
            crate::profiles::output(document, band)?;
            stream.write_all(band).map_err(error)?;
            control.check()
        };
        let quantize = |values: &[f64], target: &mut [u8]| {
            for (p, target) in values
                .as_chunks::<4>()
                .0
                .iter()
                .zip(target.as_chunks_mut::<4>().0)
            {
                let bytes = p.map(|v| (v * 255.0).round() as u8);
                *target = if bytes[3] == 0 { [0; 4] } else { bytes };
            }
        };
        prepared.visit_rows(rows, |origin, size, samples| {
            if !tiled {
                for values in samples.chunks(row_bytes * rows as usize) {
                    band.resize(values.len(), 0);
                    quantize(values, &mut band);
                    write_band(&mut band)?;
                }
                return Ok(());
            }
            let band_y = origin[1] / rows * rows;
            let band_height = rows.min(height - band_y);
            if band.is_empty() {
                band.resize(row_bytes * band_height as usize, 0);
            }
            for (y, values) in samples.chunks(size[0] as usize * 4).enumerate() {
                let at = ((origin[1] - band_y) as usize + y) * row_bytes + origin[0] as usize * 4;
                quantize(values, &mut band[at..at + values.len()]);
            }
            if origin[0] + size[0] == width && origin[1] + size[1] == band_y + band_height {
                write_band(&mut band)?;
                band.clear();
            }
            Ok(())
        })?;
        stream.finish().map_err(error)?;
    }
    if let Some(packet) = metadata {
        let mut payload = crate::metadata::PNG_KEY.to_vec();
        payload.extend_from_slice(&[0; 5]);
        payload.extend_from_slice(packet.as_bytes());
        writer
            .write_chunk(png::chunk::iTXt, &payload)
            .map_err(error)?;
    }
    writer.finish().map_err(error)?;
    control.check()?;
    let mut artifact =
        json!({"media_type":"image/png","encoding":"base64","width":width,"height":height});
    if let Some((_, summary)) = profile {
        artifact["color_profile"] = summary;
        artifact["color_space"] = json!("icc_rgb");
        artifact["losses"] = json!([
            "RGB8 conversion uses relative colorimetric intent without black-point compensation; out-of-gamut colors clip and quantization is not reversible. Alpha is retained unchanged. The exact destination profile is embedded."
        ]);
    }
    crate::swatches::annotate(document, &mut artifact)?;
    crate::samples::annotate(document, &mut artifact, crate::samples::Depth::U8);
    if options.is_some() {
        artifact["render_settings"] = prepared.sampling.receipt();
    }
    Ok(artifact)
}

#[cfg(test)]
mod tests {
    use super::*;
    struct RejectEnd {
        bytes: Vec<u8>,
        rejected: bool,
    }
    impl Write for RejectEnd {
        fn write(&mut self, bytes: &[u8]) -> std::io::Result<usize> {
            if bytes.windows(4).any(|part| part == b"IEND") {
                self.rejected = true;
                return Err(std::io::Error::other("Original final-chunk failure"));
            }
            self.bytes.extend_from_slice(bytes);
            Ok(bytes.len())
        }
        fn flush(&mut self) -> std::io::Result<()> {
            Ok(())
        }
    }
    #[test]
    fn final_chunk_write_failure_cannot_return_a_successful_artifact() {
        let document: Document =
            serde_json::from_value(json!({"schema_version":2,"id":"final-write",
            "kind":"raster","width":2,"height":2,"color_space":"srgb"}))
            .unwrap();
        let mut output = RejectEnd {
            bytes: Vec::new(),
            rejected: false,
        };
        let result = write(
            &document,
            1,
            (None, None),
            None,
            None,
            &Control::default(),
            &mut output,
        );
        assert!(output.rejected);
        assert!(output.bytes.windows(4).any(|part| part == b"IDAT"));
        assert_eq!(result.unwrap_err().code, "EXPORT_ERROR");
    }
}
