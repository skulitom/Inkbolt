//! Explicit scene-linear radiance, reversible grading and display projection.
use crate::{Error, model::*, scene};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Encoding {
    #[default]
    EncodedSrgb,
    LinearSrgb,
    ProfiledRgb,
}
impl Encoding {
    pub fn is_default(&self) -> bool {
        *self == Self::EncodedSrgb
    }
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Grade {
    #[serde(default)]
    pub exposure: f64,
    #[serde(default = "ones")]
    pub gain: [f64; 3],
}
fn ones() -> [f64; 3] {
    [1.0; 3]
}
impl Grade {
    pub fn validate(&self) -> Result<(), Error> {
        exposure(self.exposure)?;
        if self
            .gain
            .iter()
            .any(|v| !v.is_finite() || !(0.0..=16.0).contains(v))
        {
            return Err(invalid("HDR channel gains must be finite in 0..=16"));
        }
        Ok(())
    }
    pub fn apply(&self, pixels: &mut [f64]) {
        let gain = self.gain.map(|v| v * self.exposure.exp2());
        for p in pixels.as_chunks_mut::<4>().0 {
            for c in 0..3 {
                p[c] *= gain[c];
            }
        }
    }
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ToneMap {
    Clip,
    Reinhard,
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct View {
    pub tone_map: ToneMap,
    #[serde(default)]
    pub exposure: f64,
}
fn exposure(v: f64) -> Result<(), Error> {
    if !v.is_finite() || !(-32.0..=32.0).contains(&v) {
        return Err(invalid("HDR exposure must be finite in -32..=32 stops"));
    }
    Ok(())
}
impl View {
    pub fn validate(&self) -> Result<(), Error> {
        exposure(self.exposure)
    }
    pub fn project(&self, p: [f64; 4]) -> [f64; 4] {
        let mut out = p;
        for c in 0..3 {
            let v = (p[c] * self.exposure.exp2()).max(0.0);
            let v = match self.tone_map {
                ToneMap::Clip => v.min(1.0),
                ToneMap::Reinhard => {
                    if v.is_infinite() {
                        1.0
                    } else {
                        v / (1.0 + v)
                    }
                }
            };
            out[c] = encode(v).clamp(0.0, 1.0);
        }
        out
    }
}
pub fn decode(v: f64) -> f64 {
    if v <= 0.04045 {
        v / 12.92
    } else {
        ((v + 0.055) / 1.055).powf(2.4)
    }
}
pub fn encode(v: f64) -> f64 {
    if v <= 0.0031308 {
        v * 12.92
    } else {
        1.055 * v.powf(1.0 / 2.4) - 0.055
    }
}
pub fn linear(d: &Document) -> bool {
    d.color_space == ColorSpace::LinearSrgb
}
fn supported(mode: BlendMode) -> bool {
    matches!(
        mode,
        BlendMode::Normal
            | BlendMode::Multiply
            | BlendMode::LinearDodge
            | BlendMode::Darken
            | BlendMode::Lighten
            | BlendMode::Difference
            | BlendMode::Subtract
    )
}
pub(crate) fn mix(b: [f64; 3], s: [f64; 3], mode: BlendMode, linear: bool) -> [f64; 3] {
    if !linear {
        return crate::blending::mix(b, s, mode);
    }
    std::array::from_fn(|c| match mode {
        BlendMode::Normal => s[c],
        BlendMode::Multiply => b[c] * s[c],
        BlendMode::LinearDodge => b[c] + s[c],
        BlendMode::Darken => b[c].min(s[c]),
        BlendMode::Lighten => b[c].max(s[c]),
        BlendMode::Difference => (b[c] - s[c]).abs(),
        BlendMode::Subtract => b[c] - s[c],
        _ => unreachable!("HDR blend was validated"),
    })
}
fn unsupported(message: &str) -> Error {
    Error::new("UNSUPPORTED_HDR_MODE", message)
}
pub(crate) fn validate_document(d: &Document) -> Result<(), Error> {
    let active = linear(d);
    if active && (d.kind != DocumentKind::Raster || d.output_profile.is_some()) {
        return Err(unsupported(
            "Linear HDR requires a raster document without an output profile",
        ));
    }
    for (index, item) in d.items.iter().enumerate() {
        if matches!(&item.content, Content::Raw { raw } if matches!(raw.recipe.settings.output, crate::raw::Output::LinearSrgb32))
            && !active
        {
            return Err(unsupported(
                "Linear raw output requires explicit linear_srgb document compositing",
            ));
        }
        if let Content::Samples { grid } = &item.content
            && grid.encoding == Encoding::LinearSrgb
            && !active
        {
            return Err(unsupported(
                "Linear sample sources require explicit linear_srgb document compositing",
            ));
        }
        if let Some(grade) = &item.hdr_grade {
            grade.validate()?;
            if crate::artwork_masks::source_owner(d, index)?.is_some() {
                return Err(unsupported(
                    "Artwork-mask definitions retain their encoded scalar contract and cannot carry HDR grades",
                ));
            }
            if !active
                || matches!(
                    item.content,
                    Content::Group {
                        isolated: false,
                        ..
                    } | Content::WorkPath { .. }
                        | Content::Adjustment { .. }
                        | Content::MaskSource {}
                        | Content::ComponentSource {}
                )
            {
                return Err(unsupported(
                    "HDR grades require a compositable item in a linear_srgb document; pass-through and resource containers are unsupported",
                ));
            }
        }
        if active
            && (!supported(item.blend)
                || item.content.is_knockout()
                || matches!(item.content, Content::Adjustment { .. })
                || item.filters.iter().any(|f| f.enabled)
                || item.effects.iter().any(|e| e.enabled))
        {
            return Err(unsupported(
                "Linear HDR supports normal/multiply/add/darken/lighten/difference/subtract blending; normalized adjustments, active filters/effects and knockout require a supported explicit conversion",
            ));
        }
    }
    Ok(())
}
pub(crate) fn set_grade(d: &mut Document, id: &str, grade: Option<Grade>) -> Result<Value, Error> {
    let i = scene::index(d, id)?;
    scene::check_unlocked(d, i, false)?;
    if let Some(g) = grade {
        g.validate()?;
    }
    let before = d.items[i].hdr_grade;
    d.items[i].hdr_grade = grade;
    validate_document(d)?;
    Ok(
        json!({"id":id,"before":before,"after":grade,"source_samples_changed":false,"alpha_changed":false,"exposure_units":"stops","gain_space":"linear_srgb"}),
    )
}
pub(crate) fn set_space(d: &mut Document, space: ColorSpace) -> Result<Value, Error> {
    for i in 0..d.items.len() {
        scene::check_unlocked(d, i, false)?;
    }
    let before = d.color_space.clone();
    d.color_space = space;
    validate_document(d)?;
    Ok(
        json!({"before":before,"after":d.color_space,"source_samples_changed":false,"semantics":"Changes scene compositing; encoded sources decode before linear sampling. Convert retained linear grids explicitly before switching to encoded compositing."}),
    )
}
pub(crate) fn reject_page(d: &Document) -> Result<(), Error> {
    if linear(d) {
        Err(unsupported(
            "HDR page/vector delivery requires an explicit rendered display conversion",
        ))
    } else {
        Ok(())
    }
}

pub fn measure(
    d: &Document,
    points: &[[u32; 2]],
    asset_root: Option<&std::path::Path>,
    font_root: Option<&std::path::Path>,
) -> Result<Value, Error> {
    if points.len() > 256 || points.iter().any(|p| p[0] >= d.width || p[1] >= d.height) {
        return Err(invalid(
            "Sample measurement accepts at most 256 in-canvas pixel positions",
        ));
    }
    let image = crate::render::rasterize_samples_with_options(d, 1, asset_root, font_root, None)?;
    let mut minimum = [f64::INFINITY; 4];
    let mut maximum = [f64::NEG_INFINITY; 4];
    let mut negative = 0usize;
    let mut above_white = 0usize;
    for p in image.rgba.as_chunks::<4>().0 {
        for c in 0..4 {
            minimum[c] = minimum[c].min(p[c]);
            maximum[c] = maximum[c].max(p[c]);
        }
        negative += p[..3].iter().filter(|v| **v < 0.0).count();
        above_white += p[..3].iter().filter(|v| **v > 1.0).count();
    }
    let samples: Vec<_> = points
        .iter()
        .map(|p| {
            let at = (p[1] as usize * image.width as usize + p[0] as usize) * 4;
            json!({"point":p,"rgba":&image.rgba[at..at+4]})
        })
        .collect();
    Ok(
        json!({"width":image.width,"height":image.height,"working_space":d.color_space,"precision":"f64_before_output_projection","minimum":minimum,"maximum":maximum,"negative_color_channels":negative,"above_white_color_channels":above_white,"samples":samples,"source_changed":false,"semantics":"Straight rendered samples at scale one; encoded or linear working values as declared by the document. Transparent composite color is zero. No tone mapping, profile conversion or byte projection."}),
    )
}
