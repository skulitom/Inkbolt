//! Shared renderer preflight and controlled evaluation of retained source trees.
use super::*;
use crate::control::Control;
pub(crate) struct Prepared {
    pub(super) document: Document,
    resources: Resources,
    mask_plan: ArtworkMaskPlan,
    sparse: Option<super::sparse::Plan>,
    pub sampling: crate::render_quality::Plan,
    pub work: u64,
    pub buffers: u64,
    pub object_count: usize,
    pub depth: usize,
    pub source_profiles: std::collections::BTreeSet<String>,
}
impl Prepared {
    pub fn new(
        document: &Document,
        scale: u32,
        asset_root: Option<&Path>,
        font_root: Option<&Path>,
        options: Option<&crate::render_quality::Options>,
        native_samples: bool,
        control: &Control,
    ) -> Result<Self, Error> {
        let _object_render = crate::objects::RenderGuard::enter(document)?;
        control.check()?;
        validate_controlled(document, control)?;
        let colors = crate::swatches::evaluate(document)?;
        let document = colors.as_ref().unwrap_or(document);
        let plan = crate::render_quality::Plan::for_document(document, scale, options)?;
        if plan.linear && !native_samples && plan.options.view.is_none() {
            return Err(Error::new(
                "HDR_VIEW_REQUIRED",
                "Display delivery from linear HDR requires explicit render_options.view",
            ));
        }
        let prepared = plan.prepare(document)?;
        let document = prepared.as_ref();
        let scale = plan.internal_scale;
        let expanded = crate::instances::evaluate(document)?;
        let document = expanded.as_ref().unwrap_or(document);
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
        let width = document.width * scale;
        let height = document.height * scale;
        let count = width as u64 * height as u64;
        if count > MAX_RENDER_PIXELS {
            return Err(limit("Render exceeds pixel limits"));
        }
        let generated = crate::strokes::generated_work(document)?;
        let sparse = super::sparse::Plan::new(document, [width, height, scale], control)?;
        let outline_work = if sparse.is_some() { 0 } else { generated };
        if outline_work * height as u64 > MAX_RENDER_WORK {
            return Err(limit("Stroke outline scan work exceeds render limit"));
        }
        if sparse.is_none() && count * document.items.len().max(1) as u64 > MAX_RENDER_WORK {
            return Err(limit("Render exceeds pixel or work limits"));
        }
        let filter_work: u64 = document
            .items
            .iter()
            .map(|i| crate::filters::work(i, scale))
            .sum();
        let reconstruction_work = crate::resample::document_work(document, scale)?;
        let pixel_warp_work = crate::pixel_warps::work(document, scale)?;
        let shape_work = crate::knockout::work(document, scale);
        if count * shape_work > MAX_RENDER_WORK {
            return Err(limit("Knockout footprint evaluation exceeds work limit"));
        }
        let effect_work: u64 = document
            .items
            .iter()
            .map(|i| crate::effects::work(i, scale))
            .sum();
        if count * effect_work > crate::effects::MAX_WORK {
            return Err(limit(
                "Render exceeds layer effect and coverage evaluation work limit",
            ));
        }
        if count * filter_work > crate::filters::MAX_WORK {
            return Err(limit("Render exceeds filter evaluation work limit"));
        }
        let fonts = crate::fonts::resolve(document, font_root)?;
        let texts = crate::text::prepare(document, &fonts)?;
        let passes = texts.values().map(|t| t.paths.len()).sum::<usize>()
            + document.items.len()
            + usize::from(document.background.is_some());
        if sparse.is_none() && count * passes.max(1) as u64 > MAX_RENDER_WORK {
            return Err(limit("Text rendering exceeds work limit"));
        }
        for (i, item) in document.items.iter().enumerate() {
            if let Some(layout) = texts.get(&item.id) {
                let world = scene::world_transform(document, i)?;
                for p in &layout.paths {
                    validate_world_geometry(&p.geometry, world)?;
                }
            }
        }
        let paint_work: u64 = document
            .items
            .iter()
            .map(|item| match &item.content {
                Content::Adjustment { adjustment } => adjustment.work(),
                Content::Vector { fill, stroke, .. } => fill
                    .iter()
                    .chain(stroke.iter().map(|s| &s.color))
                    .map(crate::paint::work)
                    .sum(),
                Content::Fill { paint, .. } => crate::paint::work(paint),
                Content::Text { .. } | Content::StoryFrame { .. } => texts[&item.id]
                    .paths
                    .iter()
                    .map(|p| crate::paint::work(&p.fill))
                    .sum(),
                _ => 1,
            })
            .sum();
        let mask_work = document
            .items
            .iter()
            .filter(|i| i.mask.as_ref().is_some_and(|m| m.enabled))
            .count() as u64
            * 4;
        if sparse.is_none() && count * (paint_work + mask_work) > crate::paint::MAX_PAINT_WORK {
            return Err(limit("Render exceeds paint evaluation work limit"));
        }
        let own_work = sparse.as_ref().map_or_else(
            || {
                count
                    .saturating_mul(
                        (passes as u64
                            + filter_work
                            + shape_work
                            + effect_work
                            + paint_work
                            + mask_work)
                            .max(1),
                    )
                    .saturating_add(reconstruction_work)
                    .saturating_add(pixel_warp_work)
                    .saturating_add(outline_work * height as u64)
            },
            |s| s.work,
        );
        crate::objects::charge(own_work)?;
        let mut buffer_depth = 0;
        for (i, item) in document.items.iter().enumerate() {
            let own = usize::from(crate::layer_clipping::needs_buffer(item));
            let parents = scene::ancestors(document, i)?
                .iter()
                .filter(|&&p| crate::layer_clipping::needs_buffer(&document.items[p]))
                .count();
            buffer_depth = buffer_depth.max(own + parents);
        }
        let clipping_buffers = if document.items.iter().any(|i| i.clip_to.is_some()) {
            buffer_depth + 1
        } else {
            0
        };
        let references = document
            .items
            .iter()
            .filter(|i| i.artwork_mask.as_ref().is_some_and(|m| m.enabled))
            .count();
        if count * references as u64 > crate::artwork_masks::MAX_COVERAGE_PIXELS {
            return Err(limit(
                "Artwork masks exceed aggregate viewport coverage storage",
            ));
        }
        let shape_buffers = if crate::knockout::active(document) {
            let depth = (0..document.items.len())
                .map(|i| scene::ancestors(document, i).map(|v| v.len()))
                .collect::<Result<Vec<_>, _>>()?
                .into_iter()
                .max()
                .unwrap_or(0);
            3 * (depth + 1) + 3
        } else {
            0
        };
        let buffer_pixels = sparse.as_ref().map_or_else(
            || {
                count
                    * (shape_buffers
                        + buffer_depth
                        + clipping_buffers
                        + 2
                        + usize::from(!texts.is_empty())
                        + 2 * usize::from(document.items.iter().any(|i| !i.filters.is_empty()))
                        + 2 * usize::from(document.items.iter().any(|i| !i.effects.is_empty())))
                        as u64
                    + (count * references as u64).div_ceil(4)
                    + count * 3 * u64::from(references != 0)
            },
            |s| s.buffer_pixels,
        );
        crate::objects::charge_buffers(buffer_pixels)?;
        if buffer_pixels > MAX_BUFFER_PIXELS {
            return Err(limit("Compositing buffers exceed render memory limit"));
        }

        let mask_plan = plan_artwork_masks(
            document,
            [width, height, scale],
            &fonts,
            plan.options.antialias,
            [passes as u64, paint_work + mask_work, outline_work],
        )?;
        let mut objects = BTreeMap::new();
        let mut object_count = 0;
        let mut source_profiles = std::collections::BTreeSet::new();
        let mut depth = 0;
        let mut work = own_work + mask_plan.work;
        let mut buffers = (buffer_pixels * 4).max(mask_plan.buffer_values);
        for (i, item) in document.items.iter().enumerate() {
            control.check()?;
            if !scene::effective_visible(document, i)? {
                continue;
            }
            if let Content::Raw { raw } = &item.content {
                let (raw_work, retained, scratch) = crate::raw::retained::preparation_costs(raw);
                work = work.saturating_add(raw_work);
                buffers = buffers.saturating_add(retained + scratch);
                crate::objects::charge(raw_work)?;
            }
            if let Content::StoredSamples { grid } = &item.content {
                let (native_work, native_buffers) = grid.preparation_costs();
                work = work.saturating_add(native_work);
                buffers = buffers.saturating_add(native_buffers);
                crate::objects::charge(native_work)?;
                if let Some(profile) = &grid.profile {
                    source_profiles.insert(assets::sha256(&crate::profiles::resolve(profile)?.0));
                }
            }
            if let Content::Samples { grid } = &item.content
                && let Some(profile) = &grid.profile
            {
                source_profiles.insert(assets::sha256(&crate::profiles::resolve(profile)?.0));
            }
            if let Content::Object { object } = &item.content {
                let child = Self::new(
                    &object.document()?,
                    object.surface_scale,
                    asset_root,
                    font_root,
                    None,
                    true,
                    control,
                )?;
                object_count += 1 + child.object_count;
                source_profiles.extend(child.source_profiles.iter().cloned());
                depth = depth.max(1 + child.depth);
                work = work.saturating_add(child.work);
                buffers = buffers.saturating_add(child.buffers);
                objects.insert(item.id.clone(), child);
            }
        }
        if object_count > crate::objects::MAX_RENDERED_OBJECTS
            || depth > crate::objects::MAX_NESTING
            || work > MAX_RENDER_WORK
            || buffers > MAX_BUFFER_PIXELS * 4
        {
            return Err(limit(
                "Prepared source tree exceeds render work, storage or nesting limits",
            ));
        }
        let resources = Resources {
            control: control.clone(),
            objects,
            linear: crate::hdr::linear(document),
            antialias: plan.options.antialias,
            light: document.global_light,
            track_shape: crate::knockout::active(document),
            masks: crate::masks::prepare_document(document)?,
            assets: assets::resolve(document, asset_root)?,
            stored_samples: document
                .items
                .iter()
                .enumerate()
                .filter_map(|(i, item)| match &item.content {
                    Content::StoredSamples { grid } => {
                        Some(scene::effective_visible(document, i).and_then(|visible| {
                            if visible {
                                crate::stored_samples::Reader::new(
                                    grid,
                                    asset_root,
                                    crate::hdr::linear(document),
                                    control,
                                )
                                .map(|reader| Some((item.id.clone(), reader)))
                            } else {
                                Ok(None)
                            }
                        }))
                    }
                    _ => None,
                })
                .collect::<Result<Vec<_>, Error>>()?
                .into_iter()
                .flatten()
                .collect(),
            texts,
        };
        control.check()?;
        Ok(Self {
            document: document.clone(),
            resources,
            mask_plan,
            sparse,
            sampling: plan,
            work,
            buffers,
            object_count,
            depth,
            source_profiles,
        })
    }
    pub fn render(&self) -> Result<Vec<f64>, Error> {
        self.resources.control.check()?;
        let width = self.document.width * self.sampling.internal_scale;
        let height = self.document.height * self.sampling.internal_scale;
        let masks = self.mask_plan.render_ref(Some(&self.resources.control))?;
        let mut accum = vec![0.0; width as usize * height as usize * 4];
        // Source plans and immutable stores are shared through this borrow.
        let resources = ResourcesView {
            base: &self.resources,
            artwork_masks: &masks,
            control: &self.resources.control,
        };
        let size = [width, height, self.sampling.internal_scale];
        if let Some(sparse) = &self.sparse {
            sparse.render(&self.document, size, &self.resources, &mut accum)?;
        } else {
            draw_items(&self.document, None, &mut accum, None, size, &resources)?;
        }
        self.resources.control.check()?;
        if accum.iter().any(|v| !v.is_finite()) {
            return Err(Error::new(
                "NONFINITE_RENDER",
                "Compositing exceeded finite working precision",
            ));
        }
        Ok(accum)
    }
    pub fn samples(&self) -> Result<SampleRaster, Error> {
        let values = self.render()?;
        let result = self
            .sampling
            .finish_samples(&values, self.document.width * self.sampling.internal_scale);
        self.resources.control.check()?;
        Ok(result)
    }
    pub fn object_surface(
        &self,
        object: &crate::objects::Object,
        linear: bool,
    ) -> Result<crate::samples::Decoded, Error> {
        let mut image = self.samples()?;
        let source_linear = crate::hdr::linear(&self.document);
        for (i, p) in image.rgba.as_chunks_mut::<4>().0.iter_mut().enumerate() {
            if i.is_multiple_of(4096) {
                self.resources.control.check()?;
            }
            if let Some(view) = object.view {
                *p = view.project(*p);
            }
            if linear && (!source_linear || object.view.is_some()) {
                for v in &mut p[..3] {
                    *v = crate::hdr::decode(*v);
                }
            }
        }
        Ok(crate::samples::Decoded::from_samples(
            image.width,
            image.rgba,
            linear,
        ))
    }
}
