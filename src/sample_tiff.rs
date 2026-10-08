//! Normalized high-depth TIFF delivery using the locked external codec.
use crate::{
    Document, Error,
    image_io::{Compression, Options},
    samples::{Channels, Depth},
    sessions::Resources,
};
use base64::{Engine, engine::general_purpose::STANDARD};
use serde_json::{Value, json};
use std::{io::Cursor, marker::PhantomData};
use tiff::{
    encoder::{
        TiffValue,
        colortype::{self, ColorType},
    },
    tags::{PhotometricInterpretation, SampleFormat, Tag},
};

// The codec accepts custom channel declarations. Prediction is explicitly disabled;
// compression remains independent of the number and depth of sample components.
struct GrayAlpha<C>(PhantomData<C>);
impl<C: ColorType> ColorType for GrayAlpha<C> {
    type Inner = C::Inner;
    const TIFF_VALUE: PhotometricInterpretation = PhotometricInterpretation::BlackIsZero;
    const BITS_PER_SAMPLE: &'static [u16] = &[C::BITS_PER_SAMPLE[0]; 2];
    const SAMPLE_FORMAT: &'static [SampleFormat] = &[C::SAMPLE_FORMAT[0]; 2];
    fn horizontal_predict(_: &[Self::Inner], _: &mut Vec<Self::Inner>) {
        unreachable!("Sample delivery always disables prediction")
    }
}
fn encode<C: ColorType>(
    size: [u32; 2],
    samples: &[C::Inner],
    compression: Compression,
    ppi: f64,
    metadata: Option<&str>,
) -> Result<Vec<u8>, Error>
where
    [C::Inner]: TiffValue,
{
    let mut bytes = Cursor::new(Vec::new());
    let result = (|| -> tiff::TiffResult<()> {
        let method = match compression {
            Compression::None => tiff::encoder::Compression::Uncompressed,
            Compression::Lzw => tiff::encoder::Compression::Lzw,
            Compression::Deflate => tiff::encoder::Compression::Deflate(Default::default()),
        };
        let mut encoder = tiff::encoder::TiffEncoder::new(&mut bytes)?
            .with_compression(method)
            .with_predictor(tiff::tags::Predictor::None);
        let mut image = encoder.new_image::<C>(size[0], size[1])?;
        image.encoder().write_tag(Tag::ExtraSamples, &[2u16][..])?;
        image.encoder().write_tag(Tag::Orientation, 1u16)?;
        if let Some(metadata) = metadata {
            image.encoder().write_tag(
                Tag::ImageDescription,
                format!("{}{}", crate::metadata::TEXT_PREFIX, metadata).as_str(),
            )?;
        }
        image.resolution(
            tiff::tags::ResolutionUnit::Inch,
            tiff::encoder::Rational {
                n: (ppi * 1000.0).round() as u32,
                d: 1000,
            },
        );
        image.write_data(samples)
    })();
    result.map_err(|_| {
        Error::new(
            "EXPORT_ERROR",
            "Unable to encode retained-depth TIFF samples",
        )
    })?;
    let bytes = bytes.into_inner();
    if bytes.len() > crate::publish::MAX_OUTPUT_BYTES {
        return Err(crate::model::limit(
            "Encoded image exceeds output byte limit",
        ));
    }
    Ok(bytes)
}
pub(crate) fn export(
    document: &Document,
    scale: u32,
    resources: &Resources,
    options: &Options,
    metadata: Option<&str>,
    render_options: Option<&crate::render_quality::Options>,
) -> Result<Value, Error> {
    if document.output_profile.is_some() {
        return Err(Error::new(
            "UNSUPPORTED",
            "Explicit sample-depth TIFF delivery does not yet support output profiles; no RGB8 conversion is performed",
        ));
    }
    let p = crate::render::rasterize_samples_with_options(
        document,
        scale,
        resources.asset_root.as_deref(),
        resources.font_root.as_deref(),
        render_options,
    )?;
    let depth = options.depth.unwrap_or_default();
    let channels = options.channels.unwrap_or_default();
    let compression = options.compression.unwrap_or_default();
    let linear = crate::hdr::linear(document) && render_options.is_none_or(|o| o.view.is_none());
    if linear && depth != Depth::F32 {
        return Err(Error::new(
            "HDR_VIEW_REQUIRED",
            "Integer TIFF delivery from linear HDR requires an explicit view; native HDR delivery requires f32 depth",
        ));
    }
    let mut samples = Vec::with_capacity(p.width as usize * p.height as usize * channels.count());
    for v in p.rgba.as_chunks::<4>().0 {
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
                "Gray-alpha export requires exactly neutral rendered RGB; an implicit luminance conversion is not performed",
            ));
        }
        let q = v.map(|x| depth.quantize(x));
        let q = if q[3] == 0.0 { [0.0; 4] } else { q };
        match channels {
            Channels::Rgba => samples.extend(q),
            Channels::GrayAlpha => samples.extend([q[0], q[3]]),
        }
    }
    let size = [p.width, p.height];
    let ppi = document.resolution_ppi * scale as f64;
    macro_rules! write {
        ($t:ty,$rgba:ty,$gray:ty,$value:expr) => {{
            let values: Vec<$t> = samples.iter().map($value).collect();
            match channels {
                Channels::Rgba => encode::<$rgba>(size, &values, compression, ppi, metadata)?,
                Channels::GrayAlpha => {
                    encode::<GrayAlpha<$gray>>(size, &values, compression, ppi, metadata)?
                }
            }
        }};
    }
    let bytes =
        match depth {
            Depth::U8 => write!(
                u8,
                colortype::RGBA8,
                colortype::Gray8,
                |v| (v * 255.0).round() as u8
            ),
            Depth::U16 => write!(u16, colortype::RGBA16, colortype::Gray16, |v| (v * 65535.0)
                .round()
                as u16),
            Depth::F32 => write!(f32, colortype::RGBA32Float, colortype::Gray32Float, |v| *v
                as f32),
        };
    let mut artifact = json!({"media_type":"image/tiff","encoding":"base64","width":p.width,"height":p.height,"color_space":"srgb","settings":{"depth":depth,"bits_per_sample":depth.bits(),"channels":channels,"compression":compression,"alpha":"unassociated","resolution_ppi":(ppi*1000.0).round()/1000.0},"losses":["Rendered normalized encoded-sRGB samples are rounded once to the requested integer or IEEE binary32 depth. Zero output alpha clears color. TIFF compression is lossless; layers and source bytes require snapshots. Untagged gray values use the encoded sRGB transfer interpretation. Profile conversion is unsupported on this path; an explicit HDR view precedes encoded projection when requested. Density is rounded to 0.001 pixels per inch."],"data":STANDARD.encode(bytes)});
    crate::swatches::annotate(document, &mut artifact)?;
    if linear {
        artifact["color_space"] = json!("linear_srgb");
        artifact["settings"]["encoding"] = json!("linear_srgb");
        artifact["losses"] = json!([
            "Signed scene-linear RGB or gray values are projected once to finite binary32. Alpha remains unassociated in 0..1; zero output alpha clears color. Compression is lossless. Untagged TIFF requires explicit assume_linear_srgb on reimport; source layers and retained values require snapshots. No display tone map or output profile is applied."
        ]);
    }
    crate::samples::annotate(document, &mut artifact, depth);
    Ok(artifact)
}
