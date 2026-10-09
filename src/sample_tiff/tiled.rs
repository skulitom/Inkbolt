//! Assemble one bounded native strip from independently composed output tiles.
use super::*;
use std::io::{self, Seek, SeekFrom, Write};
use tiff::encoder::compression::{CompressionAlgorithm, Deflate, Lzw};
const MAX_STRIP_BYTES: usize = 16 * 1024 * 1024;

struct Output(Cursor<Vec<u8>>);
impl Write for Output {
    fn write(&mut self, data: &[u8]) -> io::Result<usize> {
        if self.0.position().saturating_add(data.len() as u64)
            > crate::publish::MAX_OUTPUT_BYTES as u64
        {
            return Err(io::Error::new(
                io::ErrorKind::OutOfMemory,
                "Encoded output bound",
            ));
        }
        self.0.write(data)
    }
    fn flush(&mut self) -> io::Result<()> {
        self.0.flush()
    }
}
impl Seek for Output {
    fn seek(&mut self, at: SeekFrom) -> io::Result<u64> {
        self.0.seek(at)
    }
}
fn error(value: tiff::TiffError) -> Error {
    if matches!(&value, tiff::TiffError::IoError(e) if e.kind()==io::ErrorKind::OutOfMemory) {
        crate::model::limit("Encoded image exceeds output byte limit")
    } else {
        Error::new(
            "EXPORT_ERROR",
            "Unable to encode retained-depth TIFF strips",
        )
    }
}

pub(super) fn encode<C: ColorType>(
    prepared: &crate::render::prepared::Prepared,
    (depth, channels, compression): (Depth, Channels, Compression),
    ppi: f64,
    metadata: Option<&str>,
    project: impl Fn(f64) -> C::Inner,
) -> Result<Vec<u8>, Error>
where
    [C::Inner]: TiffValue,
    C::Inner: Default + Copy,
{
    let [width, height] = prepared.sampling.output;
    let row_values = width as usize * channels.count();
    let rows = (MAX_STRIP_BYTES / (row_values * std::mem::size_of::<C::Inner>()))
        .max(1)
        .min((crate::render::tiled::EDGE / prepared.sampling.options.antialias.factor()) as usize)
        as u32;
    let method = match compression {
        Compression::None => 1u16,
        Compression::Lzw => 5,
        Compression::Deflate => 8,
    };
    let mut output = Output(Cursor::new(Vec::new()));
    {
        let mut encoder = tiff::encoder::TiffEncoder::new(&mut output).map_err(error)?;
        // Use public directory and compression APIs: ImageEncoder::write_strip
        // in the locked codec does not activate the configured compressor.
        let mut image = encoder.image_directory().map_err(error)?;
        image.write_tag(Tag::ImageWidth, width).map_err(error)?;
        image.write_tag(Tag::ImageLength, height).map_err(error)?;
        image
            .write_tag(Tag::BitsPerSample, C::BITS_PER_SAMPLE)
            .map_err(error)?;
        image
            .write_tag(
                Tag::SampleFormat,
                &vec![if depth == Depth::F32 { 3u16 } else { 1 }; channels.count()][..],
            )
            .map_err(error)?;
        image
            .write_tag(Tag::SamplesPerPixel, channels.count() as u16)
            .map_err(error)?;
        image
            .write_tag(
                Tag::PhotometricInterpretation,
                if channels == Channels::Rgba { 2u16 } else { 1 },
            )
            .map_err(error)?;
        image
            .write_tag(Tag::PlanarConfiguration, 1u16)
            .map_err(error)?;
        image.write_tag(Tag::Compression, method).map_err(error)?;
        image.write_tag(Tag::RowsPerStrip, rows).map_err(error)?;
        image
            .write_tag(Tag::ExtraSamples, &[2u16][..])
            .map_err(error)?;
        image.write_tag(Tag::Orientation, 1u16).map_err(error)?;
        if let Some(metadata) = metadata {
            image
                .write_tag(
                    Tag::ImageDescription,
                    format!("{}{}", crate::metadata::TEXT_PREFIX, metadata).as_str(),
                )
                .map_err(error)?;
        }
        image.write_tag(Tag::ResolutionUnit, 2u16).map_err(error)?;
        for tag in [Tag::XResolution, Tag::YResolution] {
            image
                .write_tag(
                    tag,
                    tiff::encoder::Rational {
                        n: (ppi * 1000.0).round() as u32,
                        d: 1000,
                    },
                )
                .map_err(error)?;
        }
        let mut offsets = Vec::new();
        let mut counts = Vec::new();
        let mut strip = Vec::new();
        prepared.visit_rows(rows, |origin, size, samples| {
            if origin[0] == 0 {
                strip.resize(row_values * size[1] as usize, C::Inner::default());
            }
            for (i, v) in samples.as_chunks::<4>().0.iter().enumerate() {
                if v.iter()
                    .any(|x| !x.is_finite() || x.abs() > f32::MAX as f64)
                {
                    return Err(Error::new(
                        "UNSUPPORTED_SAMPLE_RANGE",
                        "Rendered samples exceed finite binary32 delivery range",
                    ));
                }
                if channels == Channels::GrayAlpha && (v[0] != v[1] || v[1] != v[2]) {
                    return Err(Error::new(
                        "GRAYSCALE_CONVERSION_REQUIRED",
                        "Gray-alpha export requires exactly neutral rendered RGB",
                    ));
                }
                let q = v.map(|x| depth.quantize(x));
                let q = if q[3] == 0.0 { [0.0; 4] } else { q };
                let at = (i / size[0] as usize * width as usize
                    + origin[0] as usize
                    + i % size[0] as usize)
                    * channels.count();
                if channels == Channels::GrayAlpha {
                    strip[at] = project(q[0]);
                    strip[at + 1] = project(q[3]);
                } else {
                    for c in 0..4 {
                        strip[at + c] = project(q[c]);
                    }
                }
            }
            if origin[0] + size[0] == width {
                let raw = strip[..].data();
                let mut compressed = Output(Cursor::new(Vec::new()));
                let bytes = match compression {
                    Compression::None => raw.as_ref(),
                    Compression::Lzw => {
                        Lzw.write_to(&mut compressed, &raw)
                            .map_err(|e| error(e.into()))?;
                        compressed.0.get_ref().as_slice()
                    }
                    Compression::Deflate => {
                        Deflate::default()
                            .write_to(&mut compressed, &raw)
                            .map_err(|e| error(e.into()))?;
                        compressed.0.get_ref().as_slice()
                    }
                };
                offsets.push(image.write_data(bytes).map_err(error)? as u32);
                counts.push(bytes.len() as u32);
                strip.clear();
            }
            Ok(())
        })?;
        image
            .write_tag(Tag::StripOffsets, &offsets[..])
            .map_err(error)?;
        image
            .write_tag(Tag::StripByteCounts, &counts[..])
            .map_err(error)?;
        image.finish().map_err(error)?;
    }
    Ok(output.0.into_inner())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn output_bound_is_checked_before_a_seek_can_allocate() {
        let mut output = Output(Cursor::new(vec![7, 8]));
        output
            .seek(SeekFrom::Start(crate::publish::MAX_OUTPUT_BYTES as u64))
            .unwrap();
        assert_eq!(
            output.write(&[9]).unwrap_err().kind(),
            io::ErrorKind::OutOfMemory
        );
        assert_eq!(output.0.get_ref(), &[7, 8]);
        output.seek(SeekFrom::Start(0)).unwrap();
        output.write_all(&[1]).unwrap();
        assert_eq!(output.0.get_ref(), &[1, 8]);
    }
}
