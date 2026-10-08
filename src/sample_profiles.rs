//! Explicit per-source RGB profile assignment and conversion, preserving alpha and history.
use crate::{
    Error,
    control::Control,
    model::*,
    profiles::{self, Intent, Profile},
    samples::{Channels, Depth, Grid},
    scene,
};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Action {
    Assign {
        profile: Option<Profile>,
    },
    Convert {
        profile: Option<Profile>,
        #[serde(default)]
        intent: Intent,
    },
}
pub const MAX_ENCODED_PROFILE_BYTES: usize = 512 * 1024;
fn working() -> Profile {
    Profile::Builtin {
        name: profiles::Builtin::Srgb,
    }
}
pub(crate) fn identity(profile: &Profile) -> Result<Value, Error> {
    let (bytes, _) = profiles::resolve(profile)?;
    Ok(json!({"sha256":crate::assets::sha256(&bytes),"bytes":bytes.len(),"color_model":"rgb"}))
}
fn hash(profile: Option<&Profile>) -> Result<String, Error> {
    Ok(crate::assets::sha256(
        &profiles::resolve(profile.unwrap_or(&working()))?.0,
    ))
}
pub(crate) fn apply(
    d: &mut Document,
    id: &str,
    action: &Action,
    control: &Control,
) -> Result<Value, Error> {
    control.check()?;
    let i = scene::index(d, id)?;
    scene::check_unlocked(d, i, false)?;
    let (mut grid, promoted) = match &d.items[i].content {
        Content::Samples { grid } => (grid.as_ref().clone(), false),
        Content::Raster {
            width,
            height,
            rgba_hex,
            sampling,
        } => (
            Grid {
                profile: None,
                encoding: Default::default(),
                width: *width,
                height: *height,
                depth: Depth::U8,
                channels: Channels::Rgba,
                data_hex: rgba_hex.clone(),
                sampling: *sampling,
            },
            true,
        ),
        _ => {
            return Err(Error::new(
                "UNSUPPORTED",
                "Source profile edits require retained sample grids or inline RGBA8 pixels",
            ));
        }
    };
    grid.validate()?;
    if grid.encoding == crate::hdr::Encoding::LinearSrgb {
        return Err(Error::new(
            "UNSUPPORTED_HDR_MODE",
            "Source profile edits require normalized RGB values; project signed linear HDR explicitly first",
        ));
    }
    let profile = match action {
        Action::Assign { profile } | Action::Convert { profile, .. } => profile.as_ref(),
    };
    if let Some(profile) = profile {
        profiles::validate_source(profile)?;
    }
    let before_data = crate::assets::sha256(&crate::render::unhex(&grid.data_hex));
    let source_profile = hash(grid.profile.as_ref())?;
    let destination_profile = hash(profile)?;
    let mut clipped = 0;
    let mut quantized = 0;
    let mut error = 0.0f64;
    let channels = grid.channels;
    if let Action::Convert { intent, .. } = action
        && source_profile != destination_profile
    {
        let values = crate::samples::decode_values(&grid.data_hex, grid.depth);
        let mut rgba: Vec<f64> = values
            .chunks_exact(grid.channels.count())
            .flat_map(|p| match grid.channels {
                Channels::Rgba => [p[0], p[1], p[2], p[3]],
                Channels::GrayAlpha => [p[0], p[0], p[0], p[1]],
            })
            .collect();
        clipped = profiles::convert_f64(
            &mut rgba,
            grid.profile.as_ref().unwrap_or(&working()),
            profile.unwrap_or(&working()),
            *intent,
            true,
            Some(control),
        )?;
        for p in rgba.as_chunks_mut::<4>().0 {
            for v in &mut p[..3] {
                let q = grid.depth.quantize(*v);
                error = error.max((*v - q).abs());
                quantized += usize::from(*v != q);
                *v = q;
            }
        }
        grid.data_hex = crate::samples::encode_values(&rgba, grid.depth);
        grid.channels = Channels::Rgba;
    }
    grid.profile = profile.cloned();
    grid.encoding = if profile.is_some() {
        crate::hdr::Encoding::ProfiledRgb
    } else {
        crate::hdr::Encoding::EncodedSrgb
    };
    grid.validate()?;
    control.check()?;
    let after_data = crate::assets::sha256(&crate::render::unhex(&grid.data_hex));
    let details = json!({"id":id,"action":action,"promoted_inline_rgba8":promoted,"source_profile_sha256":source_profile,"destination_profile_sha256":destination_profile,"before_data_sha256":before_data,"after_data_sha256":after_data,"sample_values_changed":before_data!=after_data,"depth":grid.depth,"source_channels":channels,"channels":grid.channels,"clipped_color_channels":clipped,"quantized_color_channels":quantized,"maximum_quantization_error":error,"alpha":"exact_native_values_retained","transparent_color":"retained_and_converted","view_intent":"relative_colorimetric","black_point_compensation":false,"source_preservation":"caller_snapshot_and_durable_history","appearance":"assignment_reinterprets_values;conversion_preserves_color_subject_to_profile_gamut_and_quantization"});
    d.items[i].content = Content::Samples {
        grid: Box::new(grid),
    };
    Ok(details)
}
