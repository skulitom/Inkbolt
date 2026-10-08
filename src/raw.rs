//! Original bounded development of explicitly described Bayer sensor buffers.
use crate::{
    Error, assets,
    control::Control,
    hdr,
    model::*,
    samples::{Channels, Depth, Grid},
};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::path::Path;

pub const ALGORITHM: &str = "inkbolt-bayer-bilinear-v1";
pub const MAX_PIXELS: usize = 16384;
mod corrections;
pub mod retained;
pub use corrections::{Border, Corrections, Denoise, Detail, Lens};

#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Packing {
    U8,
    U16Le,
    U16Be,
}
impl Packing {
    fn bytes(self) -> usize {
        match self {
            Self::U8 => 1,
            _ => 2,
        }
    }
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Pattern {
    Rggb,
    Grbg,
    Gbrg,
    Bggr,
}
impl Pattern {
    fn colors(self) -> [usize; 4] {
        match self {
            Self::Rggb => [0, 1, 1, 2],
            Self::Grbg => [1, 0, 2, 1],
            Self::Gbrg => [1, 2, 0, 1],
            Self::Bggr => [2, 1, 1, 0],
        }
    }
}

/// Calibration is caller-supplied factual sensor data, never inferred from a filename.
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Capture {
    pub width: u32,
    pub height: u32,
    pub packing: Packing,
    pub row_stride: usize,
    pub pattern: Pattern,
    /// Row-major 2x2 sensor-site levels, before interpolation.
    pub black: [f64; 4],
    pub white: [f64; 4],
    /// Row-major matrix applied to white-balanced linear camera RGB.
    pub camera_to_linear_srgb: [[f64; 3]; 3],
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum WhiteBalance {
    /// Direct linear channel multipliers; no hidden normalization.
    Gains { rgb: [f64; 3] },
    /// A measured neutral camera triplet; green gain is normalized to one.
    Neutral { rgb: [f64; 3] },
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Output {
    Srgb8,
    Srgb16,
    LinearSrgb32,
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Range {
    Clip,
    Preserve,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Settings {
    pub exposure_stops: f64,
    pub white_balance: WhiteBalance,
    pub output: Output,
    pub range: Range,
    pub resolution_ppi: f64,
}

fn invalid_raw(message: &str) -> Error {
    Error::new("INVALID_RAW", message)
}
impl Capture {
    fn validate(&self) -> Result<usize, Error> {
        if !(2..=MAX_DIMENSION).contains(&self.width) || !(2..=MAX_DIMENSION).contains(&self.height)
        {
            return Err(invalid_raw("Bayer dimensions must be in 2..=32768"));
        }
        let count = self.width as u64 * self.height as u64;
        if count > MAX_PIXELS as u64 {
            return Err(limit("Raw development exceeds 16384 sensor pixels"));
        }
        let minimum = self.width as usize * self.packing.bytes();
        if self.row_stride < minimum || self.row_stride > minimum + 4096 {
            return Err(invalid_raw(
                "Raw row stride must include every sample and at most 4096 padding bytes",
            ));
        }
        let length = self.row_stride as u64 * self.height as u64;
        if length > assets::MAX_IMPORT_BYTES {
            return Err(limit("Raw buffer exceeds 32 MiB"));
        }
        let max = if matches!(self.packing, Packing::U8) {
            255.0
        } else {
            65535.0
        };
        for i in 0..4 {
            if !self.black[i].is_finite()
                || !self.white[i].is_finite()
                || self.black[i] < 0.0
                || self.white[i] > max
                || self.white[i] - self.black[i] < 1.0
            {
                return Err(invalid_raw(
                    "Each sensor site's finite black/white interval must span at least one code within the packing range",
                ));
            }
        }
        if self
            .camera_to_linear_srgb
            .iter()
            .flatten()
            .any(|v| !v.is_finite() || v.abs() > 16.0)
        {
            return Err(invalid_raw(
                "Camera matrix entries must be finite in -16..=16",
            ));
        }
        let m = self.camera_to_linear_srgb;
        let det = m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
            - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]);
        if det.abs() < 1e-12 {
            return Err(invalid_raw(
                "Camera matrix must be nonsingular (|det| >= 1e-12)",
            ));
        }
        Ok(length as usize)
    }
}
impl Settings {
    fn gains(&self) -> Result<[f64; 3], Error> {
        if !self.exposure_stops.is_finite() || !(-32.0..=32.0).contains(&self.exposure_stops) {
            return Err(invalid_raw("Exposure must be finite in -32..=32 stops"));
        }
        if !self.resolution_ppi.is_finite() || !(1.0..=9600.0).contains(&self.resolution_ppi) {
            return Err(invalid_raw(
                "Output resolution must be finite in 1..=9600 ppi",
            ));
        }
        if matches!(self.range, Range::Preserve) && !matches!(self.output, Output::LinearSrgb32) {
            return Err(Error::new(
                "UNSUPPORTED_RAW_OUTPUT",
                "Signed scene range requires linear_srgb32 output; encoded integer output requires explicit clip",
            ));
        }
        let rgb = match self.white_balance {
            WhiteBalance::Gains { rgb } | WhiteBalance::Neutral { rgb } => rgb,
        };
        if rgb.iter().any(|v| !v.is_finite() || *v <= 0.0 || *v > 64.0) {
            return Err(invalid_raw(
                "White-balance components must be finite in (0,64]",
            ));
        }
        let gains = match self.white_balance {
            WhiteBalance::Gains { .. } => rgb,
            WhiteBalance::Neutral { .. } => rgb.map(|v| rgb[1] / v),
        };
        if gains.iter().any(|v| !(1.0 / 64.0..=64.0).contains(v)) {
            return Err(invalid_raw(
                "Effective white-balance gains must be in 1/64..=64",
            ));
        }
        Ok(gains)
    }
}

/// Develop exact raw bytes without opening or changing any file.
/// Missing channels use separable bilinear weights on same-colour sensor sites.
/// At the boundary only available sites contribute; weights are renormalized.
pub fn develop(
    bytes: &[u8],
    id: String,
    capture: &Capture,
    settings: &Settings,
    control: &Control,
) -> Result<Value, Error> {
    develop_corrected(
        bytes,
        id,
        capture,
        settings,
        &Corrections::default(),
        control,
    )
}
fn develop_corrected(
    bytes: &[u8],
    id: String,
    capture: &Capture,
    settings: &Settings,
    corrections: &Corrections,
    control: &Control,
) -> Result<Value, Error> {
    control.check()?;
    let length = capture.validate()?;
    let gains = settings.gains()?;
    corrections.validate(capture)?;
    if bytes.len() != length {
        return Err(invalid_raw(
            "Raw byte length must equal row_stride times height exactly",
        ));
    }
    let width = capture.width as usize;
    let height = capture.height as usize;
    let mut sensor = Vec::with_capacity(width * height);
    let mut below_black = 0usize;
    let mut at_or_above_white = 0usize;
    let colors = capture.pattern.colors();
    for y in 0..height {
        control.check()?;
        for x in 0..width {
            let at = y * capture.row_stride + x * capture.packing.bytes();
            let code = match capture.packing {
                Packing::U8 => bytes[at] as f64,
                Packing::U16Le => u16::from_le_bytes([bytes[at], bytes[at + 1]]) as f64,
                Packing::U16Be => u16::from_be_bytes([bytes[at], bytes[at + 1]]) as f64,
            };
            let site = (y % 2) * 2 + x % 2;
            below_black += usize::from(code < capture.black[site]);
            at_or_above_white += usize::from(code >= capture.white[site]);
            // Retain below-black noise and above-white values until explicit output projection.
            sensor.push((code - capture.black[site]) / (capture.white[site] - capture.black[site]));
        }
    }
    let mut values = Vec::with_capacity(width * height * 4);
    for y in 0..height {
        control.check()?;
        for x in 0..width {
            let known = colors[(y % 2) * 2 + x % 2];
            let mut rgb = [0.0; 3];
            for (c, channel) in rgb.iter_mut().enumerate() {
                if c == known {
                    *channel = sensor[y * width + x];
                } else {
                    let mut total = 0.0;
                    let mut weight = 0.0;
                    for yy in y.saturating_sub(1)..=(y + 1).min(height - 1) {
                        for xx in x.saturating_sub(1)..=(x + 1).min(width - 1) {
                            if colors[(yy % 2) * 2 + xx % 2] == c {
                                let w = if xx == x || yy == y { 2.0 } else { 1.0 };
                                total += w * sensor[yy * width + xx];
                                weight += w;
                            }
                        }
                    }
                    // Every 2x2 Bayer cell contains all three channels.
                    *channel = total / weight;
                }
                *channel *= gains[c];
            }
            for row in capture.camera_to_linear_srgb.iter() {
                let v = (row[0] * rgb[0] + row[1] * rgb[1] + row[2] * rgb[2])
                    * settings.exposure_stops.exp2();
                values.push(v);
            }
            values.push(1.0);
        }
    }
    corrections::apply(&mut values, capture, corrections, control)?;
    let mut below_zero = 0usize;
    let mut above_one = 0usize;
    let mut minimum = [f64::INFINITY; 3];
    let mut maximum = [f64::NEG_INFINITY; 3];
    for pixel in values.as_chunks_mut::<4>().0 {
        for c in 0..3 {
            let v = &mut pixel[c];
            minimum[c] = minimum[c].min(*v);
            maximum[c] = maximum[c].max(*v);
            below_zero += usize::from(*v < 0.0);
            above_one += usize::from(*v > 1.0);
            if matches!(settings.range, Range::Clip) {
                *v = v.clamp(0.0, 1.0);
            }
            if !matches!(settings.output, Output::LinearSrgb32) {
                *v = hdr::encode(*v);
            }
        }
    }
    let (depth, encoding) = match settings.output {
        Output::Srgb8 => (Depth::U8, hdr::Encoding::EncodedSrgb),
        Output::Srgb16 => (Depth::U16, hdr::Encoding::EncodedSrgb),
        Output::LinearSrgb32 => (Depth::F32, hdr::Encoding::LinearSrgb),
    };
    let grid = Grid {
        profile: None,
        encoding,
        width: capture.width,
        height: capture.height,
        depth,
        channels: Channels::Rgba,
        data_hex: crate::samples::encode_values(&values, depth),
        sampling: Default::default(),
    };
    let document: Document = serde_json::from_value(json!({
        "schema_version":2,"id":id,"kind":"raster","width":capture.width,"height":capture.height,
        "resolution_ppi":settings.resolution_ppi,
        "color_space":if matches!(settings.output,Output::LinearSrgb32){"linear_srgb"}else{"srgb"},
        "items":[{"id":"developed","content":{"type":"samples","grid":grid}}]
    }))
    .map_err(|_| invalid_raw("Unable to construct developed document"))?;
    crate::validate(&document)?;
    control.check()?;
    let hash = assets::sha256(bytes);
    Ok(json!({
        "document":document,"source_sha256":hash,"source_bytes":bytes.len(),"source_changed":false,
        "recipe":{"schema_version":1,"algorithm":ALGORITHM,"source_sha256":hash,"capture":capture,"settings":settings},
        "diagnostics":{"effective_white_balance":gains,"below_black_samples":below_black,
            "at_or_above_white_samples":at_or_above_white,"linear_rgb_minimum":minimum,"linear_rgb_maximum":maximum,
            "below_zero_channels":below_zero,"above_one_channels":above_one,
            "clipped_channels":if matches!(settings.range,Range::Clip){below_zero+above_one}else{0}},
        "losses":["Developed pixels are a new opaque image. Sensor sites are interpolated, not recovered scene detail; row padding does not become artwork. The recipe pins the exact original bytes, which remain external. Integer output clips only by explicit policy and quantizes encoded sRGB. No camera-container metadata, lens correction, denoise, detail enhancement, automatic white balance or highlight reconstruction is applied."]
    }))
}

pub fn import(
    source: &Path,
    expected_sha256: Option<&str>,
    id: String,
    capture: &Capture,
    settings: &Settings,
    control: &Control,
) -> Result<Value, Error> {
    control.check()?;
    let length = capture.validate()?;
    settings.gains()?;
    if expected_sha256.is_some_and(|v| v.len() != 64 || !v.bytes().all(|c| c.is_ascii_hexdigit())) {
        return Err(invalid_raw(
            "Expected source identity must contain 64 hexadecimal characters",
        ));
    }
    assets::absolute(source)?;
    let bytes = assets::read_bounded(source, length as u64)?;
    if expected_sha256.is_some_and(|v| !v.eq_ignore_ascii_case(&assets::sha256(&bytes))) {
        return Err(Error::new(
            "SOURCE_MISMATCH",
            "Raw source bytes do not match the expected identity",
        ));
    }
    develop(&bytes, id, capture, settings, control)
}
