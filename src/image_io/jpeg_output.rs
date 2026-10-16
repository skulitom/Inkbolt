//! Row-fed JPEG encoding with bounded tiled pixels and caller-owned output.
use super::*;
use crate::{control::Control, limits::jpeg_output as bounds, render::prepared::Bands};
use std::{
    cell::RefCell,
    io::{BufWriter, Write},
};

mod stream;

fn error() -> Error {
    Error::new("EXPORT_ERROR", "Unable to finish JPEG output stream")
}

pub(crate) fn export(
    document: &Document,
    scale: u32,
    resources: &Resources,
    options: Option<&Options>,
    metadata: Option<&str>,
    context: (Option<&crate::render_quality::Options>, &Control),
) -> Result<Value, Error> {
    let mut sink = crate::publish::payload::Sink::memory(context.1);
    let artifact = write(
        document, scale, resources, options, metadata, context, &mut sink,
    );
    let bytes = sink.finish()?;
    let mut artifact = artifact?;
    artifact["data"] = json!(STANDARD.encode(bytes.into_memory()));
    Ok(artifact)
}

struct Rows<'a> {
    document: &'a Document,
    control: &'a Control,
    bands: Option<Bands<'a>>,
    pixels: Vec<u8>,
    size: [u32; 2],
    band_rows: u32,
    start: u32,
    height: u32,
    matte: Option<[u8; 3]>,
}
impl Rows<'_> {
    fn prepare_pixels(&mut self) -> Result<(), Error> {
        for (i, pixel) in self.pixels.as_chunks_mut::<4>().0.iter_mut().enumerate() {
            if i.is_multiple_of(crate::limits::control::PIXEL_CHECK_INTERVAL) {
                self.control.check()?;
            }
            if pixel[3] != 255 && self.matte.is_none() {
                return Err(Error::new(
                    "ALPHA_POLICY_REQUIRED",
                    "RGB-only delivery cannot retain alpha; supply an explicit RGB matte",
                ));
            }
            let matte = self.matte.unwrap_or([0; 3]);
            for c in 0..3 {
                pixel[c] = ((u32::from(pixel[c]) * u32::from(pixel[3])
                    + u32::from(matte[c]) * (255 - u32::from(pixel[3]))
                    + 127)
                    / 255) as u8;
            }
            pixel[3] = 255;
        }
        crate::profiles::output(self.document, &mut self.pixels)?;
        self.control.check()
    }
    fn row(&mut self, y: u32) -> Result<&[u8], Error> {
        self.control.check()?;
        if y < self.start || y >= self.size[1] {
            return Err(error());
        }
        if y >= self.start + self.height {
            let start = self.start + self.height;
            let height = self.band_rows.min(self.size[1] - start);
            if y != start {
                return Err(error());
            }
            let row_bytes = self.size[0] as usize * 4;
            self.pixels.resize(row_bytes * height as usize, 0);
            let pixels = &mut self.pixels;
            let rendered =
                self.bands
                    .as_mut()
                    .ok_or_else(error)?
                    .next(|origin, size, values| {
                        for (row, samples) in values.chunks(size[0] as usize * 4).enumerate() {
                            let at = ((origin[1] - start) as usize + row) * row_bytes
                                + origin[0] as usize * 4;
                            for (sample, target) in samples
                                .as_chunks::<4>()
                                .0
                                .iter()
                                .zip(pixels[at..at + samples.len()].as_chunks_mut::<4>().0)
                            {
                                let bytes = sample.map(|v| (v * 255.0).round() as u8);
                                *target = if bytes[3] == 0 { [0; 4] } else { bytes };
                            }
                        }
                        Ok(())
                    })?;
            if rendered != Some((start, height)) {
                return Err(error());
            }
            self.start = start;
            self.height = height;
            self.prepare_pixels()?;
        }
        let at = (y - self.start) as usize * self.size[0] as usize * 4;
        Ok(&self.pixels[at..at + self.size[0] as usize * 4])
    }
}

struct Image<'a, 'b> {
    rows: RefCell<Rows<'a>>,
    size: [u16; 2],
    failure: &'b RefCell<Option<Error>>,
}
impl jpeg_encoder::ImageBuffer for Image<'_, '_> {
    fn get_jpeg_color_type(&self) -> jpeg_encoder::JpegColorType {
        jpeg_encoder::JpegColorType::Ycbcr
    }
    fn width(&self) -> u16 {
        self.size[0]
    }
    fn height(&self) -> u16 {
        self.size[1]
    }
    fn fill_buffers(&self, y: u16, buffers: &mut [Vec<u8>; 4]) {
        if self.failure.borrow().is_none() {
            match self.rows.borrow_mut().row(u32::from(y)) {
                Ok(row) => {
                    for pixel in row.as_chunks::<4>().0 {
                        let (y, cb, cr) = jpeg_encoder::rgb_to_ycbcr(pixel[0], pixel[1], pixel[2]);
                        buffers[0].push(y);
                        buffers[1].push(cb);
                        buffers[2].push(cr);
                    }
                    return;
                }
                Err(error) => *self.failure.borrow_mut() = Some(error),
            }
        }
        // The codec callback is infallible. Keep its MCU row well-formed until
        // its next write observes the shared failure; these pixels cannot escape.
        for buffer in &mut buffers[..3] {
            buffer.resize(buffer.len() + usize::from(self.size[0]), 0);
        }
    }
}

pub(crate) fn write(
    document: &Document,
    scale: u32,
    resources: &Resources,
    options: Option<&Options>,
    metadata: Option<&str>,
    (render_options, control): (Option<&crate::render_quality::Options>, &Control),
    output: &mut impl Write,
) -> Result<Value, Error> {
    validate_options(ExportFormat::Jpeg, options)?;
    let defaults = Options::default();
    let options = options.unwrap_or(&defaults);
    let plan = crate::render_quality::Plan::for_document(document, scale, render_options)?;
    let [width, height] = plan.output;
    let ppi = document.resolution_ppi * scale as f64;
    if width > u32::from(u16::MAX)
        || height > u32::from(u16::MAX)
        || ppi.round() > f64::from(u16::MAX)
    {
        return Err(limit(&format!(
            "JPEG dimensions or rounded density exceed {}",
            u16::MAX
        )));
    }
    let row_bytes = width as usize * 4;
    if row_bytes > bounds::MAX_BAND_BYTES {
        return Err(limit("JPEG row exceeds codec band budget"));
    }
    let tiled = plan.options.evaluation == crate::render_quality::Evaluation::Tiled;
    let prepared = if tiled {
        Some(crate::render::prepared::Prepared::new(
            document,
            scale,
            resources.asset_root.as_deref(),
            resources.font_root.as_deref(),
            render_options,
            false,
            control,
        )?)
    } else {
        None
    };
    let maximum_rows = (bounds::MAX_BAND_BYTES / row_bytes) as u32;
    let mut rows = Rows {
        document,
        control,
        bands: None,
        pixels: Vec::new(),
        size: [width, height],
        band_rows: maximum_rows,
        start: 0,
        height: 0,
        matte: options.matte,
    };
    if let Some(prepared) = &prepared {
        rows.band_rows = prepared.band_rows(maximum_rows);
        rows.bands = Some(prepared.bands(maximum_rows)?);
        // Exact initial capacity prevents geometric growth beyond the band bound.
        rows.pixels = Vec::with_capacity(row_bytes * rows.band_rows.min(height) as usize);
    } else {
        rows.pixels = crate::render::rasterize_controlled(
            document,
            scale,
            resources.asset_root.as_deref(),
            resources.font_root.as_deref(),
            render_options,
            control,
        )?
        .rgba;
        rows.height = height;
        rows.prepare_pixels()?;
    }
    let profile = document
        .output_profile
        .as_ref()
        .map(|p| Ok::<_, Error>((crate::profiles::resolve(p)?.0, crate::profiles::summary(p)?)))
        .transpose()?;
    let quality = options.quality.unwrap_or(limits::DEFAULT_JPEG_QUALITY);
    let chroma = options.chroma.unwrap_or(Chroma::Full);
    let failure = RefCell::new(None);
    let mut buffered = BufWriter::with_capacity(bounds::STREAM_BUFFER_BYTES, output);
    let result = (|| {
        let mut stream = stream::Stream::new(&mut buffered, metadata, control, &failure)?;
        let mut encoder = jpeg_encoder::Encoder::new(&mut stream, quality);
        if let Some((bytes, _)) = &profile {
            encoder.add_icc_profile(bytes).map_err(|_| error())?;
        }
        encoder.set_sampling_factor(match chroma {
            Chroma::Full => jpeg_encoder::SamplingFactor::F_1_1,
            Chroma::Half => jpeg_encoder::SamplingFactor::F_2_2,
        });
        encoder.set_density(jpeg_encoder::PixelDensity::dpi(ppi.round() as u16));
        let result = encoder.encode_image(Image {
            rows: RefCell::new(rows),
            size: [width as u16, height as u16],
            failure: &failure,
        });
        if let Some(error) = failure.take() {
            return Err(error);
        }
        result.map_err(|_| error())?;
        stream.finish()?;
        Ok(())
    })();
    let result = if let Some(error) = failure.take() {
        Err(error)
    } else {
        result
    };
    // Never flush a failed encoding implicitly from BufWriter::drop.
    let result = result.and_then(|()| buffered.flush().map_err(|_| error()));
    let _ = buffered.into_parts();
    result?;
    control.check()?;
    let losses = vec![
        "JPEG is lossy and cannot preserve alpha or editable layers. An explicit matte composites alpha in encoded sRGB before compression. Quality is an encoder setting, not a universal pixel-error guarantee.",
        if profile.is_some() {
            "Output uses the embedded RGB profile with relative colorimetric conversion and no black-point compensation. Gamut clipping and RGB8 quantization are not reversible. Density is rounded to whole pixels per inch."
        } else {
            "Output uses untagged sRGB sample interpretation; no ICC profile is embedded. Density is rounded to whole pixels per inch."
        },
    ];
    let mut artifact = json!({"media_type":"image/jpeg","encoding":"base64","width":width,"height":height,
        "color_space":"srgb","settings":{"quality":quality,"chroma":chroma,"matte":options.matte,"resolution_ppi":ppi.round()},"losses":losses});
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
    use jpeg_encoder::ImageBuffer;

    fn document() -> Document {
        serde_json::from_value(json!({"schema_version":2,"id":"jpeg-bands","kind":"raster",
            "width":3,"height":257,"color_space":"srgb","items":[{"id":"opaque",
            "transform":[3,0,0,256,0,0],"content":{"type":"raster","width":1,"height":1,"rgba_hex":"204060ff"}}]})).unwrap()
    }
    #[test]
    fn late_alpha_failure_is_returned_instead_of_encoding_placeholder_pixels() {
        let control = Control::default();
        let options: crate::render_quality::Options =
            serde_json::from_value(json!({"evaluation":"tiled"})).unwrap();
        let mut sink = Vec::new();
        let result = write(
            &document(),
            1,
            &Resources::default(),
            None,
            None,
            (Some(&options), &control),
            &mut sink,
        );
        assert_eq!(result.unwrap_err().code, "ALPHA_POLICY_REQUIRED");
        assert!(!sink.ends_with(&[255, 217]));
    }
    #[test]
    fn row_cancellation_poison_is_visible_to_the_next_encoded_write() {
        let document = document();
        let control = Control::default();
        let failure = RefCell::new(None);
        let image = Image {
            rows: RefCell::new(Rows {
                document: &document,
                control: &control,
                bands: None,
                pixels: vec![32, 64, 96, 255],
                size: [1, 1],
                band_rows: 1,
                start: 0,
                height: 1,
                matte: None,
            }),
            size: [1, 1],
            failure: &failure,
        };
        let mut buffers = std::array::from_fn(|_| Vec::new());
        image.fill_buffers(0, &mut buffers);
        assert!(failure.borrow().is_none());
        control.cancel();
        image.fill_buffers(0, &mut buffers);
        assert_eq!(failure.borrow().as_ref().unwrap().code, "CANCELLED");
        assert!(buffers[..3].iter().all(|b| b.len() == 2));
        let mut bytes = Vec::new();
        let mut stream = stream::Stream::new(&mut bytes, None, &control, &failure).unwrap();
        assert!(stream.write_all(&[255, 216]).is_err());
        assert!(bytes.is_empty());
    }
    struct RejectEnd {
        final_write: bool,
        flush: bool,
    }
    impl Write for RejectEnd {
        fn write(&mut self, data: &[u8]) -> std::io::Result<usize> {
            if self.final_write && data.ends_with(&[255, 217]) {
                return Err(std::io::Error::other("Original final JPEG write failure"));
            }
            Ok(data.len())
        }
        fn flush(&mut self) -> std::io::Result<()> {
            if self.flush {
                Err(std::io::Error::other("Original JPEG flush failure"))
            } else {
                Ok(())
            }
        }
    }
    #[test]
    fn final_marker_or_flush_failure_never_returns_an_artifact() {
        for evaluation in ["whole", "tiled"] {
            let render = serde_json::from_value(json!({"evaluation":evaluation})).unwrap();
            for final_write in [true, false] {
                let mut sink = RejectEnd {
                    final_write,
                    flush: !final_write,
                };
                let options = Options {
                    matte: Some([255; 3]),
                    ..Default::default()
                };
                let result = write(
                    &document(),
                    1,
                    &Resources::default(),
                    Some(&options),
                    Some("{}"),
                    (Some(&render), &Control::default()),
                    &mut sink,
                );
                assert_eq!(result.unwrap_err().code, "EXPORT_ERROR");
            }
        }
    }
}
