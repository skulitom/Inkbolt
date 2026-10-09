//! Retained normalized integer/float sample grids, independent of display encoding.
use crate::{
    Error,
    assets::{Crop, Sampling},
    model::*,
    resample,
};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Depth {
    #[default]
    U8,
    U16,
    F32,
}
impl Depth {
    pub fn bytes(self) -> usize {
        match self {
            Self::U8 => 1,
            Self::U16 => 2,
            Self::F32 => 4,
        }
    }
    pub fn bits(self) -> usize {
        self.bytes() * 8
    }
    pub fn quantize(self, value: f64) -> f64 {
        match self {
            Self::U8 => (value * 255.0).round() / 255.0,
            Self::U16 => (value * 65535.0).round() / 65535.0,
            Self::F32 => (value as f32) as f64,
        }
    }
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Channels {
    #[default]
    Rgba,
    GrayAlpha,
}
impl Channels {
    pub fn count(self) -> usize {
        match self {
            Self::Rgba => 4,
            Self::GrayAlpha => 2,
        }
    }
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Grid {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub profile: Option<crate::profiles::Profile>,
    #[serde(default, skip_serializing_if = "crate::hdr::Encoding::is_default")]
    pub encoding: crate::hdr::Encoding,
    pub width: u32,
    pub height: u32,
    pub depth: Depth,
    pub channels: Channels,
    pub data_hex: String,
    #[serde(default)]
    pub sampling: Sampling,
}
impl Grid {
    pub fn geometry(&self) -> Geometry {
        Geometry::Rect {
            x: 0.0,
            y: 0.0,
            width: self.width as f64,
            height: self.height as f64,
        }
    }
    pub fn validate(&self) -> Result<usize, Error> {
        if self.profile.is_some() != (self.encoding == crate::hdr::Encoding::ProfiledRgb) {
            return Err(invalid(
                "profiled_rgb encoding requires exactly one RGB source profile; other encodings cannot carry a source profile",
            ));
        }
        if let Some(profile) = &self.profile {
            crate::profiles::resolve(profile)?;
        }
        if !(1..=MAX_DIMENSION).contains(&self.width) || !(1..=MAX_DIMENSION).contains(&self.height)
        {
            return Err(invalid("Sample grid dimensions must be in 1..=32768"));
        }
        let count = self.width as usize * self.height as usize;
        if count > MAX_STORED_PIXELS {
            return Err(limit("Sample grid exceeds 65536 inline pixels"));
        }
        validate_data(
            &self.data_hex,
            count * self.channels.count(),
            self.depth,
            self.channels,
            self.encoding,
        )?;
        Ok(count)
    }
    pub(crate) fn decode(&self, linear: bool) -> Result<Decoded, Error> {
        self.validate()?;
        decode_native(
            self.width,
            &crate::render::unhex(&self.data_hex),
            self.depth,
            self.channels,
            self.encoding,
            self.profile.as_ref(),
            linear,
        )
    }
}
pub(crate) fn decode_native(
    width: u32,
    bytes: &[u8],
    depth: Depth,
    channels: Channels,
    encoding: crate::hdr::Encoding,
    profile: Option<&crate::profiles::Profile>,
    linear: bool,
) -> Result<Decoded, Error> {
    let values = decode_native_values(bytes, depth);
    let mut rgba: Vec<f64> = values
        .chunks_exact(channels.count())
        .flat_map(|p| match channels {
            Channels::Rgba => [p[0], p[1], p[2], p[3]],
            Channels::GrayAlpha => [p[0], p[0], p[0], p[1]],
        })
        .collect();
    if let Some(profile) = profile {
        crate::profiles::convert_f64(
            &mut rgba,
            profile,
            &crate::profiles::Profile::Builtin {
                name: if linear {
                    crate::profiles::Builtin::LinearSrgb
                } else {
                    crate::profiles::Builtin::Srgb
                },
            },
            crate::profiles::Intent::default(),
            !linear,
            None,
        )?;
    } else if linear && encoding == crate::hdr::Encoding::EncodedSrgb {
        for p in rgba.as_chunks_mut::<4>().0 {
            for v in &mut p[..3] {
                *v = crate::hdr::decode(*v);
            }
        }
    }
    Ok(Decoded {
        width,
        rgba,
        linear,
    })
}
fn validate_data(
    hex: &str,
    count: usize,
    depth: Depth,
    channels: Channels,
    encoding: crate::hdr::Encoding,
) -> Result<(), Error> {
    let linear = encoding == crate::hdr::Encoding::LinearSrgb;
    if linear && depth != Depth::F32 {
        return Err(Error::new(
            "UNSUPPORTED_HDR_MODE",
            "Linear HDR source samples require binary32 depth",
        ));
    }
    if hex.len() != count * depth.bytes() * 2 || !hex.bytes().all(|c| c.is_ascii_hexdigit()) {
        return Err(invalid(
            "Sample data must contain the exact declared count of little-endian channel values",
        ));
    }
    if depth == Depth::F32
        && decode_values(hex, depth).iter().enumerate().any(|(i, v)| {
            !v.is_finite()
                || ((!linear || i % channels.count() == channels.count() - 1)
                    && !(0.0..=1.0).contains(v))
        })
    {
        return Err(Error::new(
            "UNSUPPORTED_SAMPLE_RANGE",
            "Samples must be finite; alpha and encoded values require 0..=1. Explicit linear_srgb binary32 color retains signed HDR values",
        ));
    }
    Ok(())
}
pub(crate) fn decode_values(hex: &str, depth: Depth) -> Vec<f64> {
    let bytes = crate::render::unhex(hex);
    decode_native_values(&bytes, depth)
}
fn decode_native_values(bytes: &[u8], depth: Depth) -> Vec<f64> {
    bytes
        .chunks_exact(depth.bytes())
        .map(|v| match depth {
            Depth::U8 => v[0] as f64 / 255.0,
            Depth::U16 => u16::from_le_bytes(v.try_into().unwrap()) as f64 / 65535.0,
            Depth::F32 => f32::from_le_bytes(v.try_into().unwrap()) as f64,
        })
        .collect()
}

pub(crate) fn encode_values(values: &[f64], depth: Depth) -> String {
    let mut bytes = Vec::with_capacity(values.len() * depth.bytes());
    for &value in values {
        match depth {
            Depth::U8 => bytes.push((value * 255.0).round() as u8),
            Depth::U16 => bytes.extend(((value * 65535.0).round() as u16).to_le_bytes()),
            Depth::F32 => bytes.extend((value as f32).to_le_bytes()),
        }
    }
    crate::render::hex(&bytes)
}
pub(crate) trait Source {
    fn sample_planned(
        &self,
        crop: Crop,
        point: Point,
        plan: &resample::Plan,
    ) -> Result<[f64; 4], Error>;
}
impl Source for crate::assets::Pixels {
    fn sample_planned(
        &self,
        crop: Crop,
        point: Point,
        plan: &resample::Plan,
    ) -> Result<[f64; 4], Error> {
        crate::assets::Pixels::sample_planned(self, crop, point, plan)
    }
}
pub(crate) struct Decoded {
    width: u32,
    rgba: Vec<f64>,
    linear: bool,
}
impl Decoded {
    pub(crate) fn premultiplied_at(&self, x: usize, y: usize) -> [f64; 4] {
        let at = (y * self.width as usize + x) * 4;
        let p = &self.rgba[at..at + 4];
        [p[0] * p[3], p[1] * p[3], p[2] * p[3], p[3]]
    }
    pub(crate) fn from_samples(width: u32, rgba: Vec<f64>, linear: bool) -> Self {
        Self {
            width,
            rgba,
            linear,
        }
    }
    pub(crate) fn from_pixels(p: &crate::assets::Pixels) -> Self {
        Self {
            width: p.width,
            linear: true,
            rgba: p
                .rgba
                .as_chunks::<4>()
                .0
                .iter()
                .flat_map(|p| {
                    [
                        crate::hdr::decode(p[0] as f64 / 255.0),
                        crate::hdr::decode(p[1] as f64 / 255.0),
                        crate::hdr::decode(p[2] as f64 / 255.0),
                        p[3] as f64 / 255.0,
                    ]
                })
                .collect(),
        }
    }
}
impl Source for Decoded {
    fn sample_planned(
        &self,
        crop: Crop,
        point: Point,
        plan: &resample::Plan,
    ) -> Result<[f64; 4], Error> {
        resample::straight_range(point, plan, self.linear, |x, y| {
            let x = x.clamp(crop.x as i64, (crop.x + crop.width - 1) as i64) as usize;
            let y = y.clamp(crop.y as i64, (crop.y + crop.height - 1) as i64) as usize;
            let at = (y * self.width as usize + x) * 4;
            let p = &self.rgba[at..at + 4];
            [p[0] * p[3], p[1] * p[3], p[2] * p[3], p[3]]
        })
    }
}

pub(crate) fn replace(
    d: &mut Document,
    id: &str,
    region: &crate::edit::PixelRect,
    data: &str,
    asset_root: Option<&std::path::Path>,
    control: &crate::control::Control,
) -> Result<Value, Error> {
    let i = crate::scene::index(d, id)?;
    crate::scene::check_unlocked(d, i, false)?;
    crate::pixel_warps::reject_native(&d.items[i])?;
    if let Content::StoredSamples { grid } = &mut d.items[i].content {
        let patch = crate::stored_samples::Patch {
            region: crate::sample_store::Region {
                x: region.x,
                y: region.y,
                width: region.width,
                height: region.height,
            },
            data_hex: data.to_owned(),
        };
        let (next, before, after) = grid.replace(asset_root, patch, control)?;
        **grid = next;
        return Ok(
            json!({"id":id,"region":region,"depth":grid.base.spec.depth,"channels":grid.base.spec.channels,
            "before_native_sha256":before,"after_native_sha256":after,"conversion":false,"outside_region_preserved":true,
            "storage":"immutable_native_blocks_with_retained_patches","files_written":false}),
        );
    }
    let Content::Samples { grid } = &mut d.items[i].content else {
        return Err(Error::new(
            "INVALID_OPERATION",
            "sample_replace requires retained sample-grid content",
        ));
    };
    if region.width == 0
        || region.height == 0
        || region.x as u64 + region.width as u64 > grid.width as u64
        || region.y as u64 + region.height as u64 > grid.height as u64
    {
        return Err(invalid(
            "Sample replacement rectangle must be nonempty and within the native grid",
        ));
    }
    validate_data(
        data,
        region.width as usize * region.height as usize * grid.channels.count(),
        grid.depth,
        grid.channels,
        grid.encoding,
    )?;
    let before = crate::assets::sha256(grid.data_hex.as_bytes());
    let stride = grid.channels.count() * grid.depth.bytes() * 2;
    for row in 0..region.height as usize {
        let dst = ((region.y as usize + row) * grid.width as usize + region.x as usize) * stride;
        let src = row * region.width as usize * stride;
        let len = region.width as usize * stride;
        grid.data_hex
            .replace_range(dst..dst + len, &data[src..src + len]);
    }
    Ok(
        json!({"id":id,"region":region,"depth":grid.depth,"channels":grid.channels,"before_data_text_sha256":before,"after_data_text_sha256":crate::assets::sha256(grid.data_hex.as_bytes()),"conversion":false,"outside_region_preserved":true}),
    )
}

pub(crate) fn annotate(document: &Document, artifact: &mut Value, depth: Depth) {
    let sources: Vec<_> = document
        .items
        .iter()
        .filter_map(|i| match &i.content {
            Content::Raw { raw } => Some(json!({"id":i.id,"content":"raw","output":raw.recipe.settings.output,"source_sha256":raw.recipe.source_sha256})),
            Content::Samples { grid } => {
                Some(json!({"id":i.id,"depth":grid.depth,"channels":grid.channels,"encoding":grid.encoding}))
            }
            Content::StoredSamples { grid } => Some(json!({"id":i.id,"content":"stored_samples","depth":grid.base.spec.depth,"channels":grid.base.spec.channels,"encoding":grid.base.spec.encoding})),
            _ => None,
        })
        .collect();
    if !sources.is_empty() || crate::hdr::linear(document) {
        artifact["sample_precision"] = json!({"sources":sources,"output_depth":depth,"working_samples":if crate::hdr::linear(document){"signed_f64_linear_srgb"}else{"normalized_f64_encoded_srgb"},"source_changed":false,"quantization":"once_at_requested_output_depth","coverage":"existing_f32_geometric_coverage","note":"Encoded sources remain normalized. Explicit linear binary32 sources retain signed HDR color and normalized alpha. Display output requires an explicit view; native linear TIFF requires f32. Preview/export never replaces retained source values."});
    }
}

pub(crate) fn inspect(content: &Content) -> Option<Value> {
    if let Content::StoredSamples { grid } = content {
        let spec = grid.base.spec;
        return Some(
            json!({"content":"stored_samples","width":spec.width,"height":spec.height,
            "depth":spec.depth,"channels":spec.channels,"sampling":grid.sampling,"sample_encoding":spec.encoding,
            "source_profile":grid.profile.as_ref().map(crate::sample_profiles::identity).transpose().ok().flatten(),
            "native_bytes":spec.width as u64 * spec.height as u64 * spec.depth.bytes() as u64 * spec.channels.count() as u64,
            "base_manifest_sha256":grid.base.sha256,"recipe_sha256":grid.recipe_sha256(),"patch_count":grid.patches.len(),
            "storage":"immutable_native_blocks_with_retained_patches","verification":"identities_only_not_file_verification"}),
        );
    }
    if let Content::Raw { raw } = content {
        return Some(
            json!({"content":"raw","width":raw.recipe.capture.width,"height":raw.recipe.capture.height,
            "source_bytes":raw.source_hex.len()/2,"source_sha256":raw.recipe.source_sha256,"recipe":raw.recipe,
            "sampling":raw.sampling,"lens_jacobian_perturbation_bound":raw.recipe.corrections.lens.as_ref().and_then(|l| l.bound(&raw.recipe.capture).ok())}),
        );
    }
    let Content::Samples { grid } = content else {
        return None;
    };
    Some(
        json!({"width":grid.width,"height":grid.height,"depth":grid.depth,"channels":grid.channels,"sampling":grid.sampling,"sample_encoding":grid.encoding,"source_profile":grid.profile.as_ref().map(crate::sample_profiles::identity).transpose().ok().flatten(),"data_bytes":grid.data_hex.len()/2,"data_sha256":crate::assets::sha256(&crate::render::unhex(&grid.data_hex)),"encoding":"little_endian_straight_channel_bytes"}),
    )
}
