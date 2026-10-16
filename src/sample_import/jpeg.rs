//! Explicit JPEG orientation and pre-admitted whole-frame codec storage.
use super::{DecodedPixels, DecodedSource, malformed, pixels, source, unsupported};
use crate::{
    Error,
    assets::{ColorPolicy, Interpretation},
    control::Control,
    hdr::Encoding,
    limits::sample_import as bounds,
    sample_store::Spec,
    samples::{Channels, Depth},
};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::io::{self, BufReader, Read, Seek};
mod entropy;
mod exif;
mod framing;

#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Orientation {
    Apply,
    Ignore,
}

struct Checked<'a, R> {
    input: R,
    control: &'a Control,
}
impl<R: Read> Read for Checked<'_, R> {
    fn read(&mut self, output: &mut [u8]) -> io::Result<usize> {
        self.control
            .check()
            .map_err(|_| io::Error::other("JPEG decode interrupted by control"))?;
        self.input.read(output)
    }
}

fn decoded_error(error: jpeg_decoder::Error, control: &Control) -> Error {
    if let Err(error) = control.check() {
        return error;
    }
    match error {
        jpeg_decoder::Error::Unsupported(_) => {
            unsupported("JPEG coding or color transform is unsupported")
        }
        _ => malformed(),
    }
}

fn source_pixel(x: u32, y: u32, width: u32, height: u32, orientation: u8) -> (u32, u32) {
    match orientation {
        1 => (x, y),
        2 => (width - 1 - x, y),
        3 => (width - 1 - x, height - 1 - y),
        4 => (x, height - 1 - y),
        5 => (y, x),
        6 => (y, height - 1 - x),
        7 => (width - 1 - y, height - 1 - x),
        8 => (width - 1 - y, x),
        _ => unreachable!(),
    }
}

pub(super) fn decode<R: Read + Seek>(
    mut input: R,
    length: u64,
    policy: ColorPolicy,
    orientation: Orientation,
    max_pixels: usize,
    staging: Option<&source::Budget>,
    control: &Control,
) -> Result<(DecodedSource, Interpretation, Value), Error> {
    let plan = framing::inspect(&mut input, length, max_pixels, control)?;
    entropy::validate(&mut input, length, &plan, control)?;
    let declared = plan.exif.as_ref().is_some_and(|m| m.srgb);
    let interpretation = if declared {
        Interpretation::DeclaredSrgb
    } else if policy == ColorPolicy::AssumeSrgb {
        Interpretation::AssumedSrgb
    } else {
        return Err(unsupported(
            "Untagged JPEG requires explicit assume_srgb interpretation",
        ));
    };
    let source_orientation = plan.exif.as_ref().and_then(|m| m.orientation);
    let mapping = if orientation == Orientation::Apply {
        source_orientation.unwrap_or(1)
    } else {
        1
    };
    let (width, height) = if mapping >= 5 {
        (plan.height, plan.width)
    } else {
        (plan.width, plan.height)
    };
    let spec = Spec {
        width,
        height,
        depth: Depth::U8,
        channels: if plan.channels == 1 {
            Channels::GrayAlpha
        } else {
            Channels::Rgba
        },
        encoding: Encoding::EncodedSrgb,
    };
    spec.validate()?;
    input.rewind().map_err(|_| malformed())?;
    let mut decoder = jpeg_decoder::Decoder::new(BufReader::with_capacity(
        bounds::INPUT_BUFFER_BYTES,
        Checked { input, control },
    ));
    decoder.set_max_decoding_buffer_size(bounds::MAX_JPEG_OUTPUT_BYTES);
    decoder.read_info().map_err(|e| decoded_error(e, control))?;
    let info = decoder.info().ok_or_else(malformed)?;
    let expected_format = if plan.channels == 1 {
        jpeg_decoder::PixelFormat::L8
    } else {
        jpeg_decoder::PixelFormat::RGB24
    };
    if u32::from(info.width) != plan.width
        || u32::from(info.height) != plan.height
        || info.pixel_format != expected_format
    {
        return Err(malformed());
    }
    control.check()?;
    let decoded = decoder.decode().map_err(|e| decoded_error(e, control))?;
    // Progressive coefficients belong to the decoder, not the native staging phase.
    drop(decoder);
    control.check()?;
    if decoded.len() != plan.output_bytes {
        return Err(malformed());
    }
    let normalize = |y: u32, row: &mut [u8]| -> Result<(), Error> {
        control.check()?;
        for (x, pixel) in row.chunks_exact_mut(spec.channels.count()).enumerate() {
            let (sx, sy) = source_pixel(x as u32, y, plan.width, plan.height, mapping);
            let at = (sy as usize * plan.width as usize + sx as usize) * plan.channels;
            pixel[..plan.channels].copy_from_slice(&decoded[at..at + plan.channels]);
            pixel[plan.channels] = 255;
        }
        Ok(())
    };
    let pixels = if let Some(staging) = staging {
        DecodedPixels::Tiles(pixels::Builder::from_rows(
            spec, staging, control, normalize,
        )?)
    } else {
        let mut bytes = vec![0; spec.byte_len()?];
        for (y, row) in bytes
            .chunks_exact_mut(width as usize * spec.channels.count())
            .enumerate()
        {
            normalize(y as u32, row)?;
        }
        DecodedPixels::Bytes(bytes)
    };
    let normalization = json!({"input_depth":8,"input_color":if plan.channels==1 {"grayscale"} else {"rgb"},
        "coding":if plan.progressive {"progressive"} else {"baseline"},
        "decode_storage":if staging.is_some() {"complete_codec_frame_to_private_native_rows"} else {"complete_decoded_frame"},
        "normalization":"decoded_8bit_channels;missing_alpha_opaque;explicit_orientation_mapping",
        "orientation":{"policy":orientation,"source":source_orientation,"effective":mapping,"transformed":mapping!=1,
            "source_width":plan.width,"source_height":plan.height,"output_width":width,"output_height":height},
        "decoder":{"whole_frame":true,"entropy_validation":"strict_huffman_scans","output_bytes":plan.output_bytes,"estimated_working_bytes":plan.estimated_working_bytes,
            "scans":plan.scans,"scan_work":plan.scan_work},
        "other_exif_metadata_retained":false,"source_exif_tags":plan.exif.as_ref().map_or(0,|m|m.tags)});
    Ok((
        DecodedSource {
            width,
            height,
            depth: Depth::U8,
            channels: spec.channels,
            pixels,
        },
        interpretation,
        normalization,
    ))
}
