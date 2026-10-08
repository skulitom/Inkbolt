//! Preparation costs and declared source semantics for original sensor development.
use super::*;

pub(crate) fn receipt() -> Value {
    json!({"outputs":["srgb8","srgb16"],"range":"explicit_recipe_clip","development":"original_calibrated_sensor;noise;lens;detail;recipe_output_projection","order":"develop_once;associated_source_reconstruction;source_profile_conversion;native_ink_composition","source":"exact_retained_sensor_bytes_and_versioned_recipe","recipe_identity":"same_pretty_JSON_with_final_newline_as_raw.recipe","alpha":"developed_lens_alpha_at_recipe_output_depth","sampling":"all_existing_reconstruction_modes;warps_require_nearest_or_bilinear","source_changed":false,"unsupported":["implicit_scene_linear_or_signed_projection"]})
}

pub(super) use crate::raw::retained::preparation_costs as costs;
