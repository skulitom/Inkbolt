//! Native process and named ink composition before a single delivery projection.
//! The paper starts opaque with zero ink; display RGB is never the ink backdrop.
use crate::{
    Error, assets, boards, control::Control, geometry, model::*, paint, profiles,
    render_quality::Antialias, scene, sessions::Resources, swatches,
};
use base64::{Engine, engine::general_purpose::STANDARD};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};

mod adjustments;
pub use adjustments::Policy as AdjustmentPolicy;
pub(crate) use adjustments::receipt as adjustments_receipt;
pub(crate) mod bindings;
mod blending;
mod effects;
mod filters;
mod images;
mod objects;
mod raw;
pub use bindings::InkBinding;
pub use images::MAX_SOURCE_PROFILES;
pub(crate) use objects::receipt as objects_receipt;
pub(crate) use raw::receipt as raw_receipt;

pub const MAX_SPOTS: usize = 28;
pub const MAX_BUFFER_VALUES: u64 = 16_777_216;
pub const MAX_WORK: u64 = 134_217_728;

pub(crate) fn blending_receipt() -> Value {
    json!({"modes":crate::blending::MODES,"process":"subtractive_complements;CMY_nonseparable_with_K_backdrop_except_luminosity_source","whole_color":"select_complete_CMYK_by_total_ink;backdrop_wins_ties","spots":"separable_white_preserving_modes;otherwise_normal","overprint":"implicit_nonisolated_group_before_requested_blend","clipping":"blend_conditional_base_color_without_increasing_base_alpha","fill_stroke":"separate_normal_paints_then_combined_item_blend","arithmetic":"binary64;no_intermediate_byte_projection"})
}

pub(crate) fn coverage_receipt() -> Value {
    json!({"knockout":"child_footprints_replace_siblings;blend_against_group_entry_backdrop","footprint":"intrinsic_paint_or_reconstructed_alpha;child_union;independent_of_item_and_fill_opacity","attenuation":"clips_and_masks_affect_shape_and_alpha;clipped_layers_preserve_base_shape","dissolve":"item_local_unit_cells;inkbolt.coverage.v1_SHA256;shared_threshold_for_shape_and_final_alpha","dissolve_inks":"preserve_conditional_ink_fractions_and_per_ink_retention;no_byte_projection"})
}

pub(crate) fn pixel_warps_receipt() -> Value {
    json!({"types":["perspective","mesh","articulated"],"sources":["raster","image","normalized_samples","retained_encoded_raw","retained_native_object"],"sampling":["nearest","bilinear"],"order":"inverse_placement;inverse_local_warp;associated_source_reconstruction;straight_source_profile_conversion;native_ink_composition","object_order":"isolated_native_source;inverse_placement;inverse_local_warp;associated_native_ink_reconstruction;native_ink_composition","boundary":"one_outer_coverage_pass;nearest_destination_boundary_point_for_covered_outside_centers","alpha":"reconstructed_source_alpha_times_geometry_coverage;independent_intrinsic_footprint","source_changed":false,"work_limit":crate::pixel_warps::MAX_WORK,"arithmetic":"binary64_source_reconstruction;no_intermediate_display_or_byte_projection"})
}

pub(crate) fn effects_receipt() -> Value {
    json!({"operators":["shadow","lit_shadow","stroke","overlay"],"field":"immutable_source_alpha;viewport_transparent_border;shared_lighting_scale_contours","color":"native_process_and_named_inks;other_paints_convert_before_compositing","order":"clipping_stack;shadows;content_fill;overlays;content_over_shadows;strokes;mask_clip_opacity_dissolve;item_blend","overlay_overprint":"retain_current_conditional_ink_fractions_and_ambient_contribution;empty_content_preserves_ambient","isolated_groups":"close_completed_decoration_against_transparent_backdrop","knockout_shape":"decorate_intrinsic_footprint_with_fill_one;contain_actual_alpha","arithmetic":"binary64;store_removed_backdrop_fraction_without_subtraction_from_one"})
}

pub(crate) fn filters_receipt() -> Value {
    json!({"operators":["box","gaussian","directional","radial","spatial.offset","spatial.displace","spatial.mosaic","surface","detail.sharpen","detail.unsharp","detail.median","detail.noise","creative.twist","creative.relief","creative.high_pass","creative.extrema","creative.tone_fold","creative.edge_ink","creative.stroke_rank","creative.value_field","creative.field_repair"],"transport":"same_positive_kernel_for_ink_contribution_removed_backdrop_fraction_alpha_and_shape","order":"drawable;isolated_closure;filter_stack;clipping_stack;effects;item_controls","normal":"interpolate_native_affine_ink_operations_without_closing_overprint","other_blends":"implicit_group_against_original_intrinsic_content_on_transparency;close_replacement_inks;interpolate_without_source_over","mask":"select_replacement_at_output_centers;do_not_mask_neighborhood_input","coordinates":"shared_viewport_kernel_and_item_local_pull_map_contract","color_operators":"conditional_addressed_ink_density;preserve_removed_fraction_alpha_and_shape;complement_light_polarity","surface_gate":"common_alpha_and_alpha_normalized_contribution_and_removal;shape_gates_its_own_alpha","edge_ink":"independent_addressed_ink_Sobel_magnitude","value_field":"convert_interpolated_RGB_to_process;retain_named_inks","noise":"process_v1_coordinates;independent_spots_hash_identity;shared_monochrome","unsupported":[],"arithmetic":"binary64;no_display_color_or_byte_projection"})
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Options {
    pub profile: profiles::cmyk::Source,
    #[serde(default)]
    pub intent: profiles::Intent,
    #[serde(default = "crate::scale")]
    pub raster_scale: u32,
    #[serde(default)]
    pub antialias: Antialias,
    pub artboard_id: Option<String>,
    #[serde(default)]
    pub include_bleed: bool,
    #[serde(default)]
    pub samples: Vec<[u32; 2]>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub ink_bindings: Vec<InkBinding>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub adjustment_policy: Option<AdjustmentPolicy>,
}

#[derive(Clone)]
pub(crate) struct Spot {
    pub id: String,
    pub name: String,
    alternate: swatches::Process,
    binding: Option<String>,
}
pub(crate) struct Prepared {
    pub dimensions: [u32; 2],
    pub logical_size: [f64; 2],
    canvas: Option<crate::vector_canvas::Canvas>,
    pub resolution_ppi: f64,
    pub raster_scale: u32,
    pub antialias: Antialias,
    pub spots: Vec<Spot>,
    pub work: u64,
    pub samples: Vec<u8>,
    pub image_sources: Vec<Value>,
    pub coverage_sources: Value,
    continuous: Vec<f64>,
    converter: profiles::cmyk::PaintConverter,
}
impl Prepared {
    pub fn profile(&self) -> &[u8] {
        &self.converter.process.bytes
    }
    pub fn profile_receipt(&self, embedded: bool) -> Value {
        json!({"icc_sha256":assets::sha256(self.profile()),"icc_bytes":self.profile().len(),"intent":self.converter.process.intent,"profile_embedded":embedded,"black_point_compensation":false,"endpoint_fixups":false,"native_interpolation":"continuous_tensor_f64","intent_connection":"directional_profile_tables;v4_reference_medium_bridge_for_perceptual_saturation;legacy_v2_direct_PCS;absolute_media_white_scaling","source_transfer":"original_ICC_equations_and_linear_curve_tables_f64","PCS_range":"legacy_colourimetric_paints_reject_XYZ_outside_encoding;managed_source_connections_report_or_clamp_destination_encoding_limits"})
    }
    pub fn channels(&self) -> usize {
        4 + self.spots.len()
    }
    pub fn alternates(&self) -> Result<Vec<(String, [f64; 4])>, Error> {
        self.spots
            .iter()
            .map(|s| {
                Ok((
                    s.id.clone(),
                    process_color(&self.converter, &s.alternate, 1.0)?,
                ))
            })
            .collect()
    }
    pub fn sampling_receipt(&self) -> Value {
        let mut value = json!({"scale":self.raster_scale,"antialias":self.antialias,"averaging":"premultiplied_ink_amounts","projection":"single_nearest_u8_ties_up"});
        if let Some(canvas) = self.canvas {
            value["vector_canvas"] = json!(canvas);
            value["logical_size"] = json!(self.logical_size);
        }
        value
    }
    pub fn ink_receipt(&self) -> Value {
        json!({"process":["cyan","magenta","yellow","black"],"spots":self.spots.iter().map(|s|s.id.as_str()).collect::<Vec<_>>(),"interleaved_sha256":assets::sha256(&self.samples),"components":self.channels(),"source_changed":false})
    }
}
fn process_color(
    converter: &profiles::cmyk::PaintConverter,
    color: &swatches::Process,
    tint: f64,
) -> Result<[f64; 4], Error> {
    use swatches::Process;
    match color {
        Process::Device {
            encoding,
            components,
            ..
        } => {
            use base64::Engine;
            let destination = profiles::device::Endpoint {
                space: profiles::device::Space::Cmyk,
                profile: Some(profiles::Profile::Icc {
                    data: base64::engine::general_purpose::STANDARD
                        .encode(&converter.process.bytes),
                }),
                untagged: profiles::device::Untagged::Reject,
            };
            let values = swatches::device::tinted(encoding, components, tint);
            let converted = profiles::device::Connection::new(
                encoding,
                &destination,
                converter.process.intent,
            )?
            .sample(&values)?;
            Ok(converted.values.try_into().unwrap())
        }
        Process::Cmyk { components, .. } => Ok(components.map(|v| v * tint)),
        Process::Srgb { components } => Ok(converter
            .rgb(&components.map(|v| 1.0 + (v - 1.0) * tint))?
            .try_into()
            .unwrap()),
        Process::Gray { component } => Ok(converter
            .rgb(&[1.0 + (component - 1.0) * tint; 3])?
            .try_into()
            .unwrap()),
        Process::Lab { components, .. } => converter.lab([
            100.0 + (components[0] - 100.0) * tint,
            components[1] * tint,
            components[2] * tint,
        ]),
    }
}

fn unsupported(message: &str) -> Error {
    Error::new("UNSUPPORTED", message)
}

/// Amounts are premultiplied by the common alpha. On an opaque surface they
/// directly describe ink coverage. Zero ink with alpha one is unmarked paper.
/// Per-ink removal is the fraction of the initial backdrop replaced by this
/// operation. Store the small removed fraction, not one minus that fraction:
/// contours can amplify coverage far below the precision of subtraction from
/// one. Overprint can preserve a channel as the common alpha increases.
#[derive(Clone)]
struct Surface {
    values: Vec<f64>,
    removal: Vec<f64>,
    shape: Option<Vec<f64>>,
    channels: usize,
}
impl Surface {
    fn new(pixels: usize, channels: usize, paper: bool, track_shape: bool) -> Self {
        let mut values = vec![0.0; pixels * (channels + 1)];
        if paper {
            for pixel in values.chunks_exact_mut(channels + 1) {
                pixel[channels] = 1.0;
            }
        }
        Self {
            values,
            removal: vec![0.0; pixels * channels],
            shape: track_shape.then(|| vec![f64::from(paper); pixels]),
            channels,
        }
    }
    fn paint(&mut self, pixel: usize, values: &[f64], addressed: &[bool], alpha: f64) {
        let stride = self.channels + 1;
        let dst = &mut self.values[pixel * stride..(pixel + 1) * stride];
        for c in 0..self.channels {
            if addressed[c] {
                dst[c] = dst[c] * (1.0 - alpha) + values[c] * alpha;
                let removal = &mut self.removal[pixel * self.channels + c];
                *removal += (1.0 - *removal) * alpha;
            }
            // Compatible overprint preserves the *amount*, not the straight
            // color, of an unspecified ink even when common alpha increases.
        }
        dst[self.channels] += (1.0 - dst[self.channels]) * alpha;
        if let Some(shape) = &mut self.shape {
            shape[pixel] += (1.0 - shape[pixel]) * alpha;
        }
    }
    fn actual(&self, initial: Option<&Surface>, control: &Control) -> Result<Self, Error> {
        control.check()?;
        let mut result = self.clone();
        if let Some(initial) = initial {
            let n = self.channels;
            for (pixel, (dst, base)) in result
                .values
                .chunks_exact_mut(n + 1)
                .zip(initial.values.chunks_exact(n + 1))
                .enumerate()
            {
                if pixel.is_multiple_of(4096) {
                    control.check()?;
                }
                for c in 0..n {
                    dst[c] += (1.0 - self.removal[pixel * n + c]) * base[c];
                }
                dst[n] += (1.0 - dst[n]) * base[n];
            }
        }
        Ok(result)
    }
}

struct Context<'a> {
    document: &'a Document,
    converter: profiles::cmyk::PaintConverter,
    observer: Option<profiles::proof::Observer>,
    spots: Vec<String>,
    ink_ids: BTreeMap<String, String>,
    noise_ids: Vec<String>,
    layouts: BTreeMap<String, crate::text::Layout>,
    images: images::Sources,
    objects: BTreeMap<String, objects::Source>,
    projected: BTreeMap<String, objects::Projected>,
    artwork_masks: BTreeMap<String, Vec<f64>>,
    width: u32,
    height: u32,
    scale: u32,
    antialias: Antialias,
    blending: bool,
    track_shape: bool,
    control: &'a Control,
}
struct Solid {
    values: Vec<f64>,
    addressed: Vec<bool>,
    opacity: f64,
}
#[derive(Clone, Copy, PartialEq, Eq)]
enum Composition {
    Over,
    Clipped,
    Knockout,
}
impl Context<'_> {
    fn channels(&self) -> usize {
        4 + self.spots.len()
    }
    fn point(&self, pixel: usize) -> Point {
        [
            (pixel % self.width as usize) as f64 + 0.5,
            (pixel / self.width as usize) as f64 + 0.5,
        ]
        .map(|v| v / self.scale as f64)
    }
    fn mask(
        &self,
        shape: &Geometry,
        rule: FillRule,
        world: Matrix,
    ) -> Result<tiny_skia::Mask, Error> {
        validate_world_geometry(shape, world)?;
        crate::render::geometry_mask(
            shape,
            rule,
            world.map(|v| v * self.scale as f64),
            self.width,
            self.height,
            self.antialias,
        )
    }
    fn process(&self, color: &swatches::Process, tint: f64) -> Result<[f64; 4], Error> {
        process_color(&self.converter, color, tint)
    }
    fn solid(&self, paint: &Paint) -> Result<Option<Solid>, Error> {
        let n = self.channels();
        let mut values = vec![0.0; n];
        let mut addressed = vec![true; n];
        let opacity = match paint {
            Paint::Named(reference) => {
                let p = swatches::native(&self.document.swatches, reference)?;
                if !p.overprint.is_knockout() {
                    addressed.fill(false);
                }
                if let Some(id) = &p.spot_id {
                    let id = self.ink_ids.get(id).unwrap_or(id);
                    let c = 4 + self.spots.binary_search(id).map_err(|_| {
                        Error::new("INVALID_DOCUMENT", "A printed spot was not prepared")
                    })?;
                    values[c] = p.tint;
                    addressed[c] = true;
                } else {
                    values[..4].copy_from_slice(&self.process(&p.color, p.tint)?);
                    for c in 0..4 {
                        addressed[c] = p.overprint != swatches::Overprint::PreserveNonzero
                            || !matches!(p.color, swatches::Process::Cmyk { .. })
                            || values[c] != 0.0;
                    }
                }
                p.opacity
            }
            Paint::Solid(rgba) => {
                values[..4].copy_from_slice(
                    &self.converter.rgb(
                        &rgba[..3]
                            .iter()
                            .map(|&v| v as f64 / 255.0)
                            .collect::<Vec<_>>(),
                    )?,
                );
                rgba[3] as f64 / 255.0
            }
            Paint::Precise(p) => {
                values[..4].copy_from_slice(&self.converter.rgb(&p.rgba[..3])?);
                p.rgba[3]
            }
            Paint::Field(_) => return Ok(None),
        };
        Ok(Some(Solid {
            values,
            addressed,
            opacity,
        }))
    }
    fn paint(
        &self,
        surface: &mut Surface,
        coverage: &tiny_skia::Mask,
        source: &Paint,
        world: Matrix,
        dither: paint::Dither,
    ) -> Result<(), Error> {
        self.control.check()?;
        if let Some(Solid {
            values,
            addressed,
            opacity,
        }) = self.solid(source)?
        {
            if dither != paint::Dither::None {
                return Err(unsupported(
                    "Native solid ink painting does not apply display dither",
                ));
            }
            for (pixel, &amount) in coverage.data().iter().enumerate() {
                if pixel.is_multiple_of(4096) {
                    self.control.check()?;
                }
                if amount != 0 {
                    surface.paint(pixel, &values, &addressed, opacity * amount as f64 / 255.0);
                }
            }
        } else {
            let sampler = paint::Sampler::new(source, world)?;
            let inverse = geometry::inverse(world)?;
            let n = self.channels();
            let addressed = vec![true; n];
            let mut values = vec![0.0; n];
            for (batch, chunk) in coverage.data().chunks(4096).enumerate() {
                self.control.check()?;
                let mut rgb = Vec::with_capacity(chunk.len() * 3);
                let mut alphas = Vec::with_capacity(chunk.len());
                for (j, &amount) in chunk.iter().enumerate() {
                    let point = self.point(batch * 4096 + j);
                    let rgba =
                        paint::dither(sampler.sample(point), geometry::map(inverse, point), dither);
                    rgb.extend_from_slice(&rgba[..3]);
                    alphas.push(rgba[3] * amount as f64 / 255.0);
                }
                let process = self.converter.rgb(&rgb)?;
                for (j, (cmyk, alpha)) in process.as_chunks::<4>().0.iter().zip(alphas).enumerate()
                {
                    values[..4].copy_from_slice(cmyk);
                    surface.paint(batch * 4096 + j, &values, &addressed, alpha);
                }
            }
        }
        Ok(())
    }
    // Normal painting is an affine operation for each ink: contribution plus
    // retained backdrop. Keep that retention separate from common alpha so
    // overprinted channels and alpha-preserving clipping remain independent.
    fn combine(
        &self,
        backdrop: &mut Surface,
        source: &Surface,
        composition: Composition,
    ) -> Result<(), Error> {
        let n = self.channels();
        for (pixel, (dst, src)) in backdrop
            .values
            .chunks_exact_mut(n + 1)
            .zip(source.values.chunks_exact(n + 1))
            .enumerate()
        {
            if pixel.is_multiple_of(4096) {
                self.control.check()?;
            }
            let base_alpha = dst[n];
            let clipped = composition == Composition::Clipped;
            let knockout = composition == Composition::Knockout;
            let footprint = source.shape.as_ref().map_or(src[n], |v| v[pixel]);
            for c in 0..n {
                let at = pixel * n + c;
                let removed = source.removal[at];
                let retained = 1.0 - removed;
                if clipped {
                    dst[c] = dst[c] * retained + base_alpha * src[c];
                    backdrop.removal[at] = backdrop.removal[at] * retained + base_alpha * removed;
                } else if knockout {
                    // Replace previous siblings within the source footprint.
                    // Both operations refer to the same group-entry backdrop.
                    dst[c] = (1.0 - footprint) * dst[c] + src[c];
                    backdrop.removal[at] = (1.0 - footprint) * backdrop.removal[at] + removed;
                } else {
                    dst[c] = dst[c] * retained + src[c];
                    backdrop.removal[at] += (1.0 - backdrop.removal[at]) * removed;
                }
            }
            if !clipped {
                if knockout {
                    dst[n] = (1.0 - footprint) * dst[n] + src[n];
                } else {
                    dst[n] += (1.0 - dst[n]) * src[n];
                }
                if let Some(shape) = &mut backdrop.shape {
                    shape[pixel] += (1.0 - shape[pixel]) * footprint;
                }
            }
        }
        Ok(())
    }
    fn apply_blend(
        &self,
        source: &mut Surface,
        backdrop: &Surface,
        initial: Option<&Surface>,
        mode: BlendMode,
        clipped: bool,
    ) -> Result<(), Error> {
        if mode == BlendMode::Normal {
            return Ok(());
        }
        let n = self.channels();
        let mut b = [0.0; 4 + MAX_SPOTS];
        let mut s = [0.0; 4 + MAX_SPOTS];
        let mut mixed = [0.0; 4 + MAX_SPOTS];
        for (pixel, (src, dst)) in source
            .values
            .chunks_exact_mut(n + 1)
            .zip(backdrop.values.chunks_exact(n + 1))
            .enumerate()
        {
            if pixel.is_multiple_of(4096) {
                self.control.check()?;
            }
            let a = src[n];
            if a == 0.0 {
                continue;
            }
            let alpha = if clipped { 1.0 } else { dst[n] };
            for c in 0..n {
                b[c] = if dst[n] == 0.0 {
                    0.0
                } else if clipped {
                    // Color conditional on intrinsic base coverage. Unaddressed
                    // ink can still refer to the surrounding actual backdrop.
                    let initial = initial.map_or(0.0, |v| v.values[pixel * (n + 1) + c]);
                    (dst[c] + (dst[n] - backdrop.removal[pixel * n + c]) * initial) / dst[n]
                } else {
                    dst[c] / dst[n]
                }
                .clamp(0.0, 1.0);
                // Remove the implicit non-isolated group's initial backdrop.
                // Compatible overprint retains premultiplied missing colorants;
                // a channel mask applied after blending is not equivalent.
                s[c] = ((src[c] + (a - source.removal[pixel * n + c]) * b[c] * alpha) / a)
                    .clamp(0.0, 1.0);
            }
            blending::mix(&b[..n], &s[..n], mode, &mut mixed[..n]);
            for c in 0..n {
                src[c] = a * ((1.0 - alpha) * s[c] + alpha * mixed[c]);
                source.removal[pixel * n + c] = a;
            }
        }
        Ok(())
    }
    fn drawable(&self, i: usize, initial: Option<&Surface>) -> Result<Surface, Error> {
        self.control.check()?;
        let item = &self.document.items[i];
        let world = scene::world_transform(self.document, i)?;
        let mut local = Surface::new(
            (self.width * self.height) as usize,
            self.channels(),
            false,
            self.track_shape,
        );
        match &item.content {
            Content::Group { isolated, .. } => self.children(
                Some(&item.id),
                &mut local,
                if *isolated { None } else { initial },
            )?,
            Content::Frame { frame } => {
                if let Some(color) = frame.background {
                    let mask = self.mask(&frame.geometry(), FillRule::Nonzero, world)?;
                    self.paint(
                        &mut local,
                        &mask,
                        &Paint::Solid(color),
                        world,
                        paint::Dither::None,
                    )?;
                }
                self.children(Some(&item.id), &mut local, None)?;
            }
            Content::Vector {
                geometry,
                fill,
                stroke,
                fill_rule,
            } => {
                if let Some(fill) = fill {
                    let mask = self.mask(geometry, *fill_rule, world)?;
                    self.paint(&mut local, &mask, fill, world, paint::Dither::None)?;
                }
                if let Some(stroke) = stroke
                    && let Some(outline) = crate::strokes::generate_placed(geometry, stroke, world)?
                {
                    let mask =
                        self.mask(&outline, FillRule::Nonzero, stroke.scaling.matrix(world))?;
                    self.paint(&mut local, &mask, &stroke.color, world, paint::Dither::None)?;
                }
            }
            Content::Fill {
                width,
                height,
                paint,
                dither,
            } => {
                let shape = Geometry::Rect {
                    x: 0.0,
                    y: 0.0,
                    width: *width as f64,
                    height: *height as f64,
                };
                let mask = self.mask(&shape, FillRule::Nonzero, world)?;
                self.paint(&mut local, &mask, paint, world, *dither)?;
            }
            Content::Text { .. } | Content::StoryFrame { .. } => {
                for path in &self.layouts[&item.id].paths {
                    let mask = self.mask(&path.geometry, FillRule::Nonzero, world)?;
                    self.paint(&mut local, &mask, &path.fill, world, paint::Dither::None)?;
                }
            }
            Content::Object { .. } => self.object(item, world, &mut local)?,
            Content::Raster { .. }
            | Content::Image { .. }
            | Content::Samples { .. }
            | Content::Raw { .. } => self.image(item, world, &mut local)?,
            _ => {
                return Err(
                    unsupported("Native ink composition needs expanded vector artwork")
                        .at_item(&item.id),
                );
            }
        }
        if item.content.is_isolated() {
            let n = self.channels();
            for (src, removed) in local
                .values
                .chunks_exact(n + 1)
                .zip(local.removal.chunks_exact_mut(n))
            {
                removed.fill(src[n]);
            }
        }
        self.filter(i, &mut local)?;
        if crate::backgrounds::matte(self.document, &item.id).is_none() {
            self.clipped_adjustments(i, &mut local, initial)?;
        }
        Ok(local)
    }
    fn apply_coverage(&self, i: usize, surface: &mut Surface) -> Result<(), Error> {
        let item = &self.document.items[i];
        let world = scene::world_transform(self.document, i)?;
        let clip = item
            .clip
            .as_ref()
            .filter(|c| c.enabled)
            .map(|c| {
                self.mask(
                    &c.geometry,
                    c.fill_rule,
                    geometry::multiply(world, c.transform),
                )
            })
            .transpose()?;
        let frame = match &item.content {
            Content::Frame { frame } => {
                Some(self.mask(&frame.geometry(), FillRule::Nonzero, world)?)
            }
            Content::Text { .. } | Content::StoryFrame { .. } => {
                crate::text::clip_geometry(&item.content, &self.layouts[&item.id])
                    .map(|g| self.mask(&g, FillRule::Nonzero, world))
                    .transpose()?
            }
            _ => None,
        };
        let mask = item
            .mask
            .as_ref()
            .filter(|m| m.enabled)
            .map(|m| crate::masks::prepare(m, world))
            .transpose()?;
        let n = self.channels();
        let inverse = (!item.coverage.is_smooth())
            .then(|| geometry::inverse(world))
            .transpose()?;
        let opacity = item.opacity
            * if item.effects.iter().any(|e| e.enabled) {
                1.0
            } else {
                item.fill_opacity
            };
        for (pixel, src) in surface.values.chunks_exact_mut(n + 1).enumerate() {
            if pixel.is_multiple_of(4096) {
                self.control.check()?;
            }
            let mut g = opacity;
            let mut shape_weight = 1.0;
            for coverage in [&clip, &frame].into_iter().flatten() {
                g *= coverage.data()[pixel] as f64 / 255.0;
                shape_weight *= coverage.data()[pixel] as f64 / 255.0;
            }
            if let Some(mask) = &mask {
                let amount = mask.sample(self.point(pixel));
                g *= amount;
                shape_weight *= amount;
            }
            if let Some(mask) = self.artwork_masks.get(&item.id) {
                g *= mask[pixel];
                shape_weight *= mask[pixel];
            }
            let point = inverse.map_or([0.0, 0.0], |m| geometry::map(m, self.point(pixel)));
            if let Some(shape) = &mut surface.shape {
                shape[pixel] = item.coverage.alpha(shape[pixel] * shape_weight, point);
            }
            if !item.coverage.is_smooth() {
                let alpha = src[n];
                g = if alpha == 0.0 {
                    0.0
                } else {
                    item.coverage.alpha(alpha * g, point) / alpha
                };
            }
            for value in src {
                *value *= g;
            }
            for removed in &mut surface.removal[pixel * n..(pixel + 1) * n] {
                *removed *= g;
            }
        }
        Ok(())
    }
    fn clipped_layers(
        &self,
        i: usize,
        base: &mut Surface,
        initial: Option<&Surface>,
    ) -> Result<(), Error> {
        let siblings = scene::children(self.document, self.document.items[i].parent.as_deref());
        let position = siblings.iter().position(|&j| j == i).unwrap();
        for &j in &siblings[position + 1..] {
            let item = &self.document.items[j];
            if crate::layer_clipping::auxiliary(&item.content) {
                continue;
            }
            if item.clip_to.as_deref() != Some(self.document.items[i].id.as_str()) {
                break;
            }
            if !item.visible {
                continue;
            }
            let mut source = self.drawable(j, None)?;
            self.decorate(j, &mut source)?;
            self.apply_coverage(j, &mut source)?;
            self.apply_blend(&mut source, base, initial, item.blend, true)?;
            self.combine(base, &source, Composition::Clipped)?;
        }
        Ok(())
    }
    fn children(
        &self,
        parent: Option<&str>,
        backdrop: &mut Surface,
        initial: Option<&Surface>,
    ) -> Result<(), Error> {
        let knockout = parent.is_some_and(|id| {
            self.document.items[scene::index(self.document, id).unwrap()]
                .content
                .is_knockout()
        });
        for i in scene::children(self.document, parent) {
            let item = &self.document.items[i];
            if !item.visible || item.clip_to.is_some() || nonprinting(item) {
                continue;
            }
            if let Content::Adjustment { adjustment } = &item.content {
                if adjustment.clip_to.is_none() {
                    self.adjust(i, backdrop, initial, false)?;
                }
                continue;
            }
            let actual = if self.blending {
                Some(if knockout {
                    self.control.check()?;
                    initial.cloned().unwrap_or_else(|| {
                        Surface::new(
                            (self.width * self.height) as usize,
                            self.channels(),
                            false,
                            self.track_shape,
                        )
                    })
                } else {
                    backdrop.actual(initial, self.control)?
                })
            } else {
                None
            };
            let mut local = self.drawable(i, actual.as_ref())?;
            if let Some(matte) = crate::backgrounds::matte(self.document, &item.id) {
                self.decorate(i, &mut local)?;
                self.apply_coverage(i, &mut local)?;
                let cmyk = self.converter.rgb(&matte.map(|v| v as f64 / 255.0))?;
                let n = self.channels();
                if item.blend != BlendMode::Normal {
                    let mut paper = Surface::new(
                        (self.width * self.height) as usize,
                        n,
                        true,
                        self.track_shape,
                    );
                    for pixel in paper.values.chunks_exact_mut(n + 1) {
                        pixel[..4].copy_from_slice(&cmyk);
                    }
                    self.apply_blend(&mut local, &paper, None, item.blend, false)?;
                }
                for (pixel, src) in local.values.chunks_exact_mut(n + 1).enumerate() {
                    for c in 0..4 {
                        src[c] += cmyk[c] * (1.0 - local.removal[pixel * n + c]);
                    }
                    src[n] = 1.0;
                }
                local.removal.fill(1.0);
                if let Some(shape) = &mut local.shape {
                    shape.fill(1.0);
                }
                self.clipped_adjustments(i, &mut local, None)?;
                self.clipped_layers(i, &mut local, actual.as_ref())?;
            } else {
                self.clipped_layers(i, &mut local, actual.as_ref())?;
                self.decorate(i, &mut local)?;
                self.apply_coverage(i, &mut local)?;
                if let Some(actual) = &actual {
                    self.apply_blend(&mut local, actual, None, item.blend, false)?;
                }
            }
            self.combine(
                backdrop,
                &local,
                if knockout {
                    Composition::Knockout
                } else {
                    Composition::Over
                },
            )?;
        }
        Ok(())
    }
}

fn nonprinting(item: &Item) -> bool {
    matches!(
        item.content,
        Content::WorkPath { .. } | Content::MaskSource {} | Content::ComponentSource {}
    )
}
fn paints<'a>(
    item: &'a Item,
    layouts: &'a BTreeMap<String, crate::text::Layout>,
) -> Vec<&'a Paint> {
    let mut result = match &item.content {
        Content::Vector { fill, stroke, .. } => {
            fill.iter().chain(stroke.iter().map(|s| &s.color)).collect()
        }
        Content::Fill { paint, .. } => vec![paint],
        Content::Text { .. } | Content::StoryFrame { .. } => {
            layouts[&item.id].paths.iter().map(|p| &p.fill).collect()
        }
        _ => Vec::new(),
    };
    result.extend(item.effects.iter().filter(|e| e.enabled).map(|e| &e.color));
    result
}

struct NativePlan {
    document: Document,
    root: bool,
    ink_ids: BTreeMap<String, String>,
    sampling: crate::render_quality::Plan,
    layouts: BTreeMap<String, crate::text::Layout>,
    mask_plan: crate::render::ArtworkMaskPlan,
    spots: Vec<Spot>,
    objects: BTreeMap<String, NativePlan>,
    projected: BTreeMap<String, Box<crate::render::prepared::Prepared>>,
    work: u64,
    buffers: u64,
    blending: bool,
    adjustments: bool,
    track_shape: bool,
}
struct Evaluated {
    values: Vec<f64>,
    images: Vec<Value>,
    coverage: Value,
    converter: profiles::cmyk::PaintConverter,
}
#[derive(Default)]
struct NativeBudget {
    objects: usize,
    source_profiles: BTreeSet<String>,
    used_bindings: BTreeSet<bindings::Key>,
}
impl NativePlan {
    fn evaluate(
        self,
        options: &Options,
        resources: &Resources,
        control: &Control,
        paper: bool,
    ) -> Result<Evaluated, Error> {
        control.check()?;
        let document = &self.document;
        let width = document.width * self.sampling.internal_scale;
        let height = document.height * self.sampling.internal_scale;
        let n = 4 + self.spots.len();
        let converter = profiles::cmyk::PaintConverter::new(&options.profile, options.intent)?;
        let mask_receipts = self.mask_plan.receipts.clone();
        let artwork_masks = self.mask_plan.render(Some(control))?;
        let mut images = images::prepare(document, resources, &converter, control)?;
        let mut objects = BTreeMap::new();
        for (id, child) in self.objects {
            control.check()?;
            let source_size = child.sampling.output;
            let source_spots = child.spots.clone();
            let source = child.evaluate(options, resources, control, false)?;
            let item = &document.items[scene::index(document, &id)?];
            let Content::Object { object } = &item.content else {
                unreachable!()
            };
            let mapping: Vec<usize> = (0..4)
                .chain(source_spots.iter().map(|spot| {
                    4 + self
                        .spots
                        .binary_search_by(|p| p.id.cmp(&bindings::placed_id(&id, spot, self.root)))
                        .expect("Planned object ink")
                }))
                .collect();
            let mut receipt = json!({"id":id,"type":"object","source_sha256":object.sha256,"source_bytes":object.snapshot.len(),"native_size":source_size,"surface_scale":object.surface_scale,"sampling":object.sampling,"link":object.link,"link_read":false,"source_changed":false,"evaluation":objects::receipt(),"spot_mapping":source_spots.iter().map(|s|bindings::mapping(&id,s)).collect::<Vec<_>>(),"image_sources":source.images,"coverage_sources":source.coverage});
            if let Some(warp) = &item.pixel_warp {
                receipt["pixel_warp"] = json!({"controls":warp,"evaluation":pixel_warps_receipt()});
            }
            images.receipts.push(receipt);
            objects.insert(
                id.clone(),
                objects::Source {
                    size: source_size,
                    values: source.values,
                    mapping,
                },
            );
        }
        let mut projected = BTreeMap::new();
        for (id, child) in self.projected {
            control.check()?;
            let item = &document.items[scene::index(document, &id)?];
            let Content::Object { object } = &item.content else {
                unreachable!()
            };
            let raster = child.samples()?;
            let size = [raster.width, raster.height];
            images.receipts.push(json!({"id":id,"type":"object","source_sha256":object.sha256,"source_bytes":object.snapshot.len(),"native_size":size,"surface_scale":object.surface_scale,"sampling":object.sampling,"view":object.view,"source_changed":false,"link_read":false,"evaluation":objects::projection_receipt(),"spot_mapping":[]}));
            projected.insert(
                id,
                objects::Projected {
                    size,
                    values: crate::samples::Decoded::from_samples(raster.width, raster.rgba, false),
                },
            );
        }
        let mut coverage_sources = json!({"artwork_masks":mask_receipts,"layer_clipping":document.items.iter().filter_map(|i| i.clip_to.as_ref().map(|base|json!({"id":i.id,"base_id":base}))).collect::<Vec<_>>(),"layer_clipping_alpha":"preserve_intrinsic_base_alpha;apply_base_controls_once_after_stack;opaque_background_controls_before_stack","native_overprint":"separate_per_ink_backdrop_retention","composition":coverage_receipt(),"effects":effects_receipt(),"filters":filters_receipt(),"source_changed":false});
        if !self.root && (document.ink_recipe.is_some() || document.output_profile.is_some()) {
            coverage_sources["source_context"] = json!({"working_space":document.color_space,"ink_recipe":"nonprinting;retained_without_application","has_ink_recipe":document.ink_recipe.is_some(),"RGB_output_profile":"delivery_metadata;working_source_unconverted","has_RGB_output_profile":document.output_profile.is_some(),"source_changed":false});
        }
        if self.adjustments {
            coverage_sources["adjustments"] = adjustments::receipt();
            coverage_sources["adjustments"]["observation_intent"] = json!(if options.intent
                == profiles::Intent::AbsoluteColorimetric
            {
                options.intent
            } else {
                profiles::Intent::RelativeColorimetric
            });
            coverage_sources["adjustments"]["separation_intent"] = json!(options.intent);
        }
        let context = Context {
            document,
            observer: if self.adjustments {
                Some(profiles::proof::Observer::new(
                    &converter.process.bytes,
                    if options.intent == profiles::Intent::AbsoluteColorimetric {
                        options.intent
                    } else {
                        profiles::Intent::RelativeColorimetric
                    },
                )?)
            } else {
                None
            },
            converter,
            images,
            objects,
            projected,
            artwork_masks,
            spots: self.spots.iter().map(|s| s.id.clone()).collect(),
            ink_ids: self.ink_ids,
            noise_ids: self
                .spots
                .iter()
                .map(|s| s.binding.as_ref().unwrap_or(&s.id).clone())
                .collect(),
            layouts: self.layouts,
            width,
            height,
            scale: self.sampling.internal_scale,
            antialias: options.antialias,
            blending: self.blending,
            track_shape: self.track_shape,
            control,
        };
        let mut surface = Surface::new((width * height) as usize, n, paper, self.track_shape);
        context.children(None, &mut surface, None)?;
        let factor = options.antialias.factor();
        let mut averaged = Vec::with_capacity(
            (self.sampling.output[0] * self.sampling.output[1]) as usize * (n + 1),
        );
        for y in 0..self.sampling.output[1] {
            control.check()?;
            for x in 0..self.sampling.output[0] {
                for c in 0..=n {
                    let mut value = 0.0;
                    for dy in 0..factor {
                        for dx in 0..factor {
                            let pixel = ((y * factor + dy) * width + x * factor + dx) as usize;
                            let weight = if paper && c == n {
                                1.0
                            } else {
                                self.sampling
                                    .canvas_weight(x * factor + dx, y * factor + dy)
                            };
                            value += surface.values[pixel * (n + 1) + c] * weight;
                        }
                    }
                    averaged.push(value / (factor * factor) as f64);
                }
            }
        }
        Ok(Evaluated {
            values: averaged,
            images: context.images.receipts,
            coverage: coverage_sources,
            converter: context.converter,
        })
    }
}

pub(crate) fn prepare(
    document: &Document,
    options: &Options,
    resources: &Resources,
    control: &Control,
) -> Result<Prepared, Error> {
    let routes = bindings::Resolved::new(document, &options.ink_bindings, control)?;
    prepare_resolved(document, options, resources, control, &routes)
}

pub(crate) fn prepare_resolved(
    document: &Document,
    options: &Options,
    resources: &Resources,
    control: &Control,
    routes: &bindings::Resolved,
) -> Result<Prepared, Error> {
    let mut budget = NativeBudget::default();
    let plan = native_plan(
        document,
        options,
        resources,
        control,
        &[],
        routes,
        &mut budget,
    )?;
    let dimensions = plan.sampling.output;
    let logical_size = plan.sampling.logical_size;
    let canvas = plan.sampling.canvas;
    let resolution_ppi = plan.document.resolution_ppi;
    let work = plan.work;
    let spots = plan.spots.clone();
    let n = 4 + plan.spots.len();
    let mut evaluated = plan.evaluate(options, resources, control, true)?;
    let receipts = routes.receipts(&budget.used_bindings);
    if !receipts.is_empty() {
        evaluated.coverage["ink_bindings"] = json!(receipts);
    }
    let continuous: Vec<f64> = evaluated
        .values
        .chunks_exact(n + 1)
        .flat_map(|p| p[..n].iter().copied())
        .collect();
    let samples = continuous
        .iter()
        .map(|v| (v.clamp(0.0, 1.0) * 255.0).round() as u8)
        .collect();
    Ok(Prepared {
        dimensions,
        logical_size,
        canvas,
        resolution_ppi,
        raster_scale: options.raster_scale,
        antialias: options.antialias,
        spots,
        work,
        samples,
        image_sources: evaluated.images,
        coverage_sources: evaluated.coverage,
        continuous,
        converter: evaluated.converter,
    })
}

fn native_plan(
    document: &Document,
    options: &Options,
    resources: &Resources,
    control: &Control,
    path: &[String],
    routes: &bindings::Resolved,
    budget: &mut NativeBudget,
) -> Result<NativePlan, Error> {
    control.check()?;
    let level = path.len();
    crate::validate(document)?;
    if document.color_space != ColorSpace::Srgb
        || (path.is_empty() && (document.ink_recipe.is_some() || document.output_profile.is_some()))
    {
        return Err(unsupported(
            "Native ink preparation requires an encoded document without a separate channel recipe or RGB output profile",
        ));
    }
    if options.samples.len() > 64 || (options.include_bleed && options.artboard_id.is_none()) {
        return Err(Error::new(
            "INVALID_REQUEST",
            "At most 64 output samples are supported; bleed needs an artboard",
        ));
    }
    // A selected board can place a definition stored outside its subtree.
    // Resolve those owned references before making the independent page copy.
    let expanded = crate::instances::evaluate(document)?;
    let document = expanded.as_ref().unwrap_or(document);
    let scoped = options
        .artboard_id
        .as_ref()
        .map(|id| boards::standalone(document, id, options.include_bleed))
        .transpose()?;
    let document = scoped.as_ref().unwrap_or(document);
    let plan = crate::render_quality::Plan::for_document(
        document,
        options.raster_scale,
        Some(&crate::render_quality::Options {
            antialias: options.antialias,
            ..Default::default()
        }),
    )?;
    if options
        .samples
        .iter()
        .any(|p| p[0] >= plan.output[0] || p[1] >= plan.output[1])
    {
        return Err(Error::new(
            "INVALID_REQUEST",
            "Native ink samples must address output pixels",
        ));
    }
    let viewport = plan.prepare(document)?;
    let document = viewport.as_ref();
    let appearance = crate::appearance::evaluate(document)?;
    let document = appearance.as_ref().unwrap_or(document);
    let volume = crate::volumes::evaluate(document)?;
    let document = volume.as_ref().unwrap_or(document);
    let warped = crate::warps::evaluate(document)?;
    let document = warped.as_ref().unwrap_or(document);
    let repeated = crate::repeats::evaluate(document)?;
    let document = repeated.as_ref().unwrap_or(document);
    let interpolated = crate::interpolation::evaluate(document)?;
    let document = interpolated.as_ref().unwrap_or(document);
    control.check()?;
    let fonts = crate::fonts::resolve(document, resources.font_root.as_deref())?;
    let layouts = crate::text::prepare(document, &fonts)?;
    let width = document.width * plan.internal_scale;
    let height = document.height * plan.internal_scale;
    let pixels = width as u64 * height as u64;
    let mut spots = BTreeSet::new();
    let mut objects = BTreeMap::new();
    let mut projected = BTreeMap::new();
    let mut object_work = 0;
    let mut object_buffers = 0;
    let mut depth = 0;
    let mut work = u64::from(crate::backgrounds::visible_matte(document).is_some());
    let mut image_count = 0u64;
    let mut source_pixels = 0u64;
    let mut raw_work = 0;
    let mut raw_retained = 0;
    let mut raw_scratch = 0;
    let mut blending = false;
    let mut adjustments = false;
    let mut adjustment_work = 0;
    let mut track_shape = false;
    let mut dissolve_count = 0;
    let mut effect_count = 0;
    let mut effect_work = 0;
    let mut filter_count = 0;
    let mut filter_work = 0;
    let mut filter_mask_work = 0;
    let mut filter_mask_pixels = 0;
    let mut filter_scratch = 0;
    let mut warp_buffers = 0;
    for (i, item) in document.items.iter().enumerate() {
        if !scene::effective_visible(document, i)? || nonprinting(item) {
            continue;
        }
        blending |= item.blend != BlendMode::Normal;
        if let Content::Adjustment { adjustment } = &item.content {
            if options.adjustment_policy.is_none() {
                return Err(unsupported("Native adjustments require explicit adjustment_policy: profiled_process_preserve_spots").at_item(&item.id));
            }
            adjustments = true;
            blending = true;
            adjustment_work += adjustment.work() + 256;
        }
        track_shape |= item.content.is_knockout();
        dissolve_count += u64::from(!item.coverage.is_smooth());
        let enabled_effects = item.effects.iter().filter(|e| e.enabled).count() as u64;
        effect_count += enabled_effects;
        if enabled_effects != 0 {
            effect_work += crate::effects::work(item, plan.internal_scale);
        }
        for filter in item
            .filters
            .iter()
            .filter(|f| f.enabled && f.opacity != 0.0)
        {
            filter_scratch =
                filter_scratch.max(filters::scratch(&filter.operator, plan.internal_scale));
            filter_count += 1;
            filter_work += filter.operator.work(plan.internal_scale);
            if let Some(mask) = &filter.mask
                && mask.enabled
            {
                let [w, h] = mask.prepared_size();
                let count = w as u64 * h as u64;
                filter_mask_pixels = filter_mask_pixels.max(count);
                filter_mask_work += count * (4 * mask.feather as u64 + 4);
            }
        }
        if let Some(warp) = &item.pixel_warp {
            warp_buffers = warp_buffers.max(crate::pixel_warps::buffer_values(warp));
        }
        if item.hdr_grade.is_some() {
            return Err(
                unsupported("Native ink composition does not yet support HDR grades")
                    .at_item(&item.id),
            );
        }
        if !matches!(
            item.content,
            Content::Vector { .. }
                | Content::Fill { .. }
                | Content::Group { .. }
                | Content::Frame { .. }
                | Content::Text { .. }
                | Content::StoryFrame { .. }
                | Content::Raster { .. }
                | Content::Image { .. }
                | Content::Samples { .. }
                | Content::Raw { .. }
                | Content::Object { .. }
                | Content::Adjustment { .. }
        ) {
            return Err(unsupported("Native ink composition needs expanded vector paints, groups, outlined text or normalized image/sample/raw or retained object content").at_item(&item.id));
        }
        if let Content::Object { object } = &item.content {
            if level >= crate::objects::MAX_NESTING
                || budget.objects >= crate::objects::MAX_RENDERED_OBJECTS
            {
                return Err(limit(
                    "Native retained objects exceed four levels or 32 visible sources",
                ));
            }
            if object.view.is_some() {
                let mut child_path = path.to_vec();
                child_path.push(item.id.clone());
                routes.reject_projected(&child_path)?;
                let source = object.document()?;
                let child = crate::render::prepared::Prepared::new(
                    &source,
                    object.surface_scale,
                    resources.asset_root.as_deref(),
                    resources.font_root.as_deref(),
                    Some(&crate::render_quality::Options {
                        view: object.view,
                        antialias: options.antialias,
                        ..Default::default()
                    }),
                    true,
                    control,
                )?;
                budget.objects += 1 + child.object_count;
                budget
                    .source_profiles
                    .extend(child.source_profiles.iter().cloned());
                if budget.source_profiles.len() > MAX_SOURCE_PROFILES {
                    return Err(limit(
                        "Native preparation exceeds 16 source profiles across projected and native objects",
                    ));
                }
                if budget.objects > crate::objects::MAX_RENDERED_OBJECTS
                    || level + 1 + child.depth > crate::objects::MAX_NESTING
                {
                    return Err(limit(
                        "Projected source tree exceeds aggregate object bounds",
                    ));
                }
                let source_pixels =
                    child.sampling.output[0] as u64 * child.sampling.output[1] as u64;
                object_work += child.work
                    + source_pixels * 16
                    + objects::work(
                        object,
                        &child.sampling,
                        scene::world_transform(document, i)?,
                        plan.internal_scale,
                        pixels,
                    )?;
                object_buffers += child.buffers + source_pixels * 4 + pixels * 4;
                projected.insert(item.id.clone(), Box::new(child));
            } else {
                budget.objects += 1;
                let source = object.document()?;
                let mut source_options = options.clone();
                source_options.raster_scale = object.surface_scale;
                source_options.samples.clear();
                source_options.artboard_id = None;
                source_options.include_bleed = false;
                let mut child_path = path.to_vec();
                child_path.push(item.id.clone());
                let child = native_plan(
                    &source,
                    &source_options,
                    resources,
                    control,
                    &child_path,
                    routes,
                    budget,
                )
                .map_err(|e| e.at_item(&item.id))?;
                object_work += child.work
                    + objects::work(
                        object,
                        &child.sampling,
                        scene::world_transform(document, i)?,
                        plan.internal_scale,
                        pixels,
                    )?;
                object_buffers += child.buffers;
                objects.insert(item.id.clone(), child);
            }
        }
        if let Content::Raw { raw } = &item.content {
            if matches!(raw.recipe.settings.output, crate::raw::Output::LinearSrgb32) {
                return Err(unsupported("Native raw inks require an explicit encoded output recipe; signed scene-linear projection is not implicit").at_item(&item.id));
            }
            let (work, retained, scratch) = raw::costs(raw);
            raw_work += work;
            raw_retained += retained;
            raw_scratch = raw_scratch.max(scratch);
            source_pixels = source_pixels
                .max(raw.recipe.capture.width as u64 * raw.recipe.capture.height as u64);
        }
        if let Content::Samples { grid } = &item.content {
            if grid.encoding == crate::hdr::Encoding::LinearSrgb {
                return Err(unsupported("Native image inks require normalized source values; explicitly project signed HDR first").at_item(&item.id));
            }
            source_pixels = source_pixels.max(grid.width as u64 * grid.height as u64);
            if let Some(profile) = &grid.profile {
                budget
                    .source_profiles
                    .insert(assets::sha256(&profiles::resolve(profile)?.0));
                if budget.source_profiles.len() > MAX_SOURCE_PROFILES {
                    return Err(limit(
                        "Native preparation supports at most 16 distinct source profiles across retained objects",
                    ));
                }
            }
        }
        if matches!(
            item.content,
            Content::Raster { .. }
                | Content::Image { .. }
                | Content::Samples { .. }
                | Content::Raw { .. }
        ) {
            image_count += 1;
        }
        depth = depth.max(scene::ancestors(document, i)?.len() + 1);
        let paints = paints(item, &layouts);
        work += paints.iter().map(|p| paint::work(p) + 1).sum::<u64>() + 2;
        for paint in paints {
            if let Paint::Named(r) = paint
                && let Some(id) = swatches::native(&document.swatches, r)?.spot_id
            {
                spots.insert(id);
            }
        }
    }
    let mut spot_definitions = BTreeMap::new();
    let mut ink_ids = BTreeMap::new();
    for id in &spots {
        let prepared = if let Some(bound) = routes.get(path, id) {
            budget.used_bindings.insert((path.to_vec(), id.clone()));
            bound
        } else {
            let entry = &document.swatches[id];
            let swatches::Definition::Spot { alternate } = &entry.definition else {
                unreachable!()
            };
            Spot {
                id: id.clone(),
                name: entry.name.clone(),
                alternate: alternate.clone(),
                binding: None,
            }
        };
        ink_ids.insert(id.clone(), prepared.id.clone());
        spot_definitions.insert(prepared.id.clone(), prepared);
    }
    for (id, child) in &objects {
        for spot in &child.spots {
            let mut placed = spot.clone();
            placed.id = bindings::placed_id(id, spot, path.is_empty());
            spot_definitions.insert(placed.id.clone(), placed);
        }
    }
    if spot_definitions.len() > MAX_SPOTS {
        return Err(limit(
            "Native ink composition supports at most 28 printed spot identities",
        ));
    }
    let n = 4 + spot_definitions.len();
    let reconstruction_work = crate::resample::document_work(document, plan.internal_scale)?;
    let pixel_warp_work = crate::pixel_warps::work(document, plan.internal_scale)?;
    let image_work = pixels * image_count * (n as u64 + 16);
    let outline_work = crate::strokes::generated_work(document)? * height as u64;
    let mask_plan = crate::render::plan_artwork_masks(
        document,
        [width, height, plan.internal_scale],
        &fonts,
        options.antialias,
        [0, 0, 0],
    )?;
    let channel_work =
        if blending { 8 * n + 32 } else { 2 * n + 1 } + if track_shape { 4 * n + 8 } else { 0 };
    let total_work = pixels * work * channel_work as u64
        + pixels * adjustment_work
        + image_work
        + object_work
        + raw_work
        + reconstruction_work
        + pixel_warp_work
        + outline_work
        + pixels * dissolve_count * if track_shape { 256 } else { 128 }
        + pixels
            * (effect_work * if track_shape { 2 } else { 1 } + effect_count * (8 * n as u64 + 32))
        + pixels
            * (filter_work * (2 * n as u64 + 1 + u64::from(track_shape))
                + filter_count * (8 * n as u64 + 40))
        + filter_mask_work
        + mask_plan.work;
    let image_buffers = if image_count == 0 {
        0
    } else {
        pixels * 4 + source_pixels * 8
    };
    let color_buffers = 4096 * 16;
    // One surface per active ancestor and current leaf, root, masks, and the
    // final averaged surface. Batch color arrays are independently bounded.
    let clipping_depth = if document.items.iter().any(|i| i.clip_to.is_some()) {
        depth
    } else {
        0
    };
    let blend_buffers = if blending {
        depth + clipping_depth + 2
    } else {
        0
    };
    let surface_values = 2 * n + 1 + usize::from(track_shape);
    let effect_buffers = if effect_count == 0 {
        0
    } else {
        pixels * (surface_values + 8) as u64
    };
    let filter_buffers = if filter_count == 0 {
        0
    } else {
        // Completed filtered fields plus the largest two-pass kernel scratch,
        // and prepared/temporary filter-mask storage. Traversal is sequential.
        pixels * (3 * surface_values) as u64 + 3 * filter_mask_pixels
    };
    let buffers = pixels * ((depth + clipping_depth + blend_buffers + 4) * surface_values) as u64
        + image_buffers
        + raw_retained
        + raw_scratch
        + color_buffers
        + effect_buffers
        + filter_buffers
        + filter_scratch
        + warp_buffers
        + mask_plan.retained_values
        + object_buffers;
    let buffers = buffers.max(mask_plan.buffer_values + object_buffers);
    if buffers > MAX_BUFFER_VALUES
        || total_work > MAX_WORK
        || outline_work > crate::render::MAX_RENDER_WORK
    {
        return Err(limit(
            "Native ink composition exceeds its channel-aware buffer or work bound",
        ));
    }
    Ok(NativePlan {
        document: document.clone(),
        root: path.is_empty(),
        ink_ids,
        sampling: plan,
        layouts,
        mask_plan,
        spots: spot_definitions.into_values().collect(),
        objects,
        projected,
        work: total_work,
        buffers,
        blending,
        adjustments,
        track_shape,
    })
}

pub fn inspect(
    document: &Document,
    options: &Options,
    resources: &Resources,
    control: &Control,
) -> Result<Value, Error> {
    let prepared = prepare(document, options, resources, control)?;
    let n = prepared.channels();
    let ppi = prepared.resolution_ppi * prepared.raster_scale as f64;
    let mut plates = Vec::with_capacity(n);
    for c in 0..n {
        control.check()?;
        let ink: Vec<u8> = prepared
            .samples
            .iter()
            .skip(c)
            .step_by(n)
            .copied()
            .collect();
        let bytes =
            crate::proof::scalar_png(prepared.dimensions[0], prepared.dimensions[1], &ink, ppi)?;
        let id = ["cyan", "magenta", "yellow", "black"][c.min(3)];
        let mut plate = json!({"kind":"process","id":id,"media_type":"image/png","encoding":"base64","data":STANDARD.encode(&bytes),"sha256":assets::sha256(&bytes),"sample_sha256":assets::sha256(&ink)});
        if c >= 4 {
            let spot = &prepared.spots[c - 4];
            plate["kind"] = json!("spot");
            plate["id"] = json!(spot.id);
            plate["name"] = json!(spot.name);
        }
        plates.push(plate);
    }
    let observations: Vec<Value> = options
        .samples
        .iter()
        .map(|p| {
            let at = (p[1] * prepared.dimensions[0] + p[0]) as usize * n;
            json!({"point":p,"ink_fractions":&prepared.continuous[at..at+n],"ink8":&prepared.samples[at..at+n]})
        })
        .collect();
    Ok(
        json!({"width":prepared.dimensions[0],"height":prepared.dimensions[1],"resolution_ppi":ppi,"plates":plates,"samples":observations,"interleaved_sha256":assets::sha256(&prepared.samples),"profile":prepared.profile_receipt(false),"source_changed":false,"image_sources":prepared.image_sources,"coverage_sources":prepared.coverage_sources,"sampling":prepared.sampling_receipt(),"compositing":{"paper":"opaque_zero_ink","space":"device_cmyk_plus_named_inks","arithmetic":"binary64","native_cmyk":"retained_without_profile_conversion","other_paints":"convert_before_ink_compositing","overprint":"normal_preserves_unaddressed_premultiplied_amounts;other_modes_use_implicit_group","blending":blending_receipt(),"nonprinting_saved_channels":"excluded"}}),
    )
}
