//! Retained sources are isolated native ink surfaces, never display previews.
use super::*;

pub(super) fn identity(item: &str, source: &str) -> String {
    if source.starts_with('/') {
        format!("/{item}{source}")
    } else {
        format!("/{item}/{source}")
    }
}

pub(crate) fn receipt() -> Value {
    json!({"source":"exact_retained_snapshot;never_implicit_link_refresh","boundary":"isolated_native_process_and_spot_surface_over_transparency","precision":"associated_binary64_inks_and_alpha;no_intermediate_byte_or_display_projection","spot_identity":"slash_prefixed_stable_item_path_and_document_local_spot_id;no_implicit_merging","bindings":"explicit_root_destination_spots_before_source_composition","sampling":["nearest","bilinear","area","bicubic","lanczos3"],"alpha":"reconstructed_source_alpha;all_parent_inks_closed_at_placement","range":"complete_2D_kernel_projection_into_zero_to_alpha","max_nesting":crate::objects::MAX_NESTING,"max_sources":crate::objects::MAX_RENDERED_OBJECTS,"resources":"recursive_preflight;aggregate_work_buffers_spots_and_source_profiles","source_changed":false,"unsupported":[]})
}

pub(super) fn work(
    object: &crate::objects::Object,
    source: &crate::render_quality::Plan,
    world: Matrix,
    scale: u32,
    pixels: u64,
) -> Result<u64, Error> {
    let crop = assets::crop(source.output[0], source.output[1], None)?;
    let plan = crate::resample::Plan::new(
        object.sampling,
        crate::resample::footprint(crop, [object.width, object.height], world, scale)?,
    )?;
    Ok(pixels.saturating_mul((5 + MAX_SPOTS) as u64 * (plan.work() + 16)))
}

pub(crate) fn projection_receipt() -> Value {
    json!({"boundary":"explicit_retained_HDR_view","order":"controlled_linear_source_composite;supersample_average;declared_view;associated_encoded_RGB_reconstruction;ICC_process_conversion;native_composition","precision":"binary64;no_intermediate_byte_projection","native_spots":"explicit_view_is_display_appearance;bindings_cannot_cross_boundary","source_changed":false})
}
pub(super) struct Projected {
    pub size: [u32; 2],
    pub values: crate::samples::Decoded,
}
pub(super) struct Source {
    pub size: [u32; 2],
    pub values: Vec<f64>,
    pub mapping: Vec<usize>,
}
impl Source {
    fn sample(
        &self,
        point: Point,
        plan: &crate::resample::Plan,
    ) -> Result<[f64; 5 + MAX_SPOTS], Error> {
        let n = self.mapping.len();
        let mut result = crate::resample::associated(point, plan, |x, y| {
            let x = x.clamp(0, self.size[0] as i64 - 1) as usize;
            let y = y.clamp(0, self.size[1] as i64 - 1) as usize;
            let at = (y * self.size[0] as usize + x) * (n + 1);
            let mut value = [0.0; 5 + MAX_SPOTS];
            value[..=n].copy_from_slice(&self.values[at..at + n + 1]);
            value
        })?;
        // An isolated source can retain overprinted amounts independently of
        // alpha internally. Its boundary presents a normalized associated ink
        // tuple; only the completed reconstruction is projected, never taps.
        result[n] = result[n].clamp(0.0, 1.0);
        for c in 0..n {
            result[c] = result[c].clamp(0.0, result[n]);
        }
        Ok(result)
    }
}

impl Context<'_> {
    pub(super) fn object(
        &self,
        item: &Item,
        world: Matrix,
        surface: &mut Surface,
    ) -> Result<(), Error> {
        let Content::Object { object } = &item.content else {
            unreachable!("Prepared native object")
        };
        if let Some(source) = self.projected.get(&item.id) {
            let warp = crate::pixel_warps::plan(item)?;
            let rgba = crate::render::image_pixels(
                &source.values,
                assets::crop(source.size[0], source.size[1], None)?,
                [object.width, object.height],
                object.sampling,
                (
                    [self.width, self.height, self.scale],
                    self.antialias,
                    Some(self.control),
                ),
                world,
                warp.as_ref(),
            )?;
            return self.image_rgba(&item.id, &rgba, surface);
        }
        let source = &self.objects[&item.id];
        let warp = crate::pixel_warps::plan(item)?;
        let crop = assets::crop(source.size[0], source.size[1], None)?;
        let n = self.channels();
        crate::render::image_map(
            crop,
            [object.width, object.height],
            object.sampling,
            (
                [self.width, self.height, self.scale],
                self.antialias,
                Some(self.control),
            ),
            world,
            warp.as_ref(),
            |i, point, plan, coverage| {
                let value = source.sample(point, plan)?;
                let alpha = value[source.mapping.len()] * coverage as f64 / 255.0;
                let dst = &mut surface.values[i * (n + 1)..(i + 1) * (n + 1)];
                for (c, &target) in source.mapping.iter().enumerate() {
                    dst[target] = value[c] * coverage as f64 / 255.0;
                }
                dst[n] = alpha;
                surface.removal[i * n..(i + 1) * n].fill(alpha);
                if let Some(shape) = &mut surface.shape {
                    shape[i] = alpha;
                }
                Ok(())
            },
        )
    }
}
