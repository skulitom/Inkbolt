//! Shared renderer preflight and controlled evaluation of retained source trees.
use super::*;
use crate::control::Control;
pub(crate) struct Prepared {
    pub(super) document: Document,
    resources: Resources,
    mask_plan: ArtworkMaskPlan,
    sparse: Option<super::sparse::Plan>,
    neighborhood: Option<super::tiled::Neighborhood>,
    tile_work: u64,
    pub sampling: crate::render_quality::Plan,
    pub work: u64,
    pub buffers: u64,
    pub object_count: usize,
    pub depth: usize,
    pub source_profiles: std::collections::BTreeSet<String>,
}
impl Prepared {
    pub(crate) fn tile_edge(&self) -> u32 {
        if self.resources.spatial.is_some() {
            super::spatial::EDGE
        } else {
            super::tiled::EDGE
        }
    }
    fn traversal(&self, max_rows: u32) -> super::traversal::Plan {
        super::traversal::Plan::new(
            self.sampling.output,
            self.tile_edge() / self.sampling.options.antialias.factor(),
            self.sampling.scale,
            max_rows,
        )
    }
    pub(crate) fn band_rows(&self, max_rows: u32) -> u32 {
        self.traversal(max_rows).rows
    }
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
        let tiled = plan.options.evaluation == crate::render_quality::Evaluation::Tiled;
        let neighborhood = if tiled {
            super::tiled::validate(document, scale)?
        } else {
            None
        };
        if count
            > if tiled {
                super::tiled::MAX_PIXELS
            } else {
                MAX_RENDER_PIXELS
            }
        {
            return Err(limit("Render exceeds pixel limits"));
        }
        let fonts = crate::fonts::resolve(document, font_root)?;
        let texts = crate::text::prepare(document, &fonts)?;
        let spatial = if tiled && document.items.len() >= 128 {
            Some(super::spatial::Plan::new(
                document,
                &texts,
                [width, height, scale],
                plan.offset,
                plan.options.antialias,
                control,
            )?)
        } else {
            None
        };
        let generated = crate::strokes::generated_work(document)?;
        let sparse = if tiled {
            None
        } else {
            super::sparse::Plan::new(document, [width, height, scale], control)?
        };
        let outline_work = if sparse.is_some() || spatial.is_some() {
            0
        } else {
            generated
        };
        let outline_scan_work = outline_work
            * height as u64
            * if tiled {
                width.div_ceil(super::tiled::EDGE) as u64
            } else {
                1
            };
        if outline_scan_work > MAX_RENDER_WORK {
            return Err(limit("Stroke outline scan work exceeds render limit"));
        }
        if sparse.is_none()
            && spatial.is_none()
            && count * document.items.len().max(1) as u64 > MAX_RENDER_WORK
        {
            return Err(limit("Render exceeds pixel or work limits"));
        }
        let filter_work: u64 = document
            .items
            .iter()
            .map(|i| crate::filters::work(i, scale))
            .sum();
        let regional_pixels = spatial.as_ref().map(|p| p.pixels.as_slice());
        let reconstruction_work =
            crate::resample::document_work_for_pixels(document, scale, regional_pixels)?;
        let pixel_warp_work =
            crate::pixel_warps::work_for_pixels(document, scale, regional_pixels)?;
        let shape_work = crate::knockout::work(document, scale);
        if spatial.is_none() && count * shape_work > MAX_RENDER_WORK {
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
        if !tiled && count * filter_work > crate::filters::MAX_WORK {
            return Err(limit("Render exceeds filter evaluation work limit"));
        }
        let tiled_path_work = if tiled && spatial.is_none() {
            super::tiled::path_work(document, &texts, [width, height])?
        } else {
            0
        };
        if tiled_path_work > MAX_RENDER_WORK {
            return Err(limit("Tiled coverage preparation exceeds work limit"));
        }
        let passes = texts.values().map(|t| t.paths.len()).sum::<usize>()
            + document.items.len()
            + usize::from(document.background.is_some());
        if sparse.is_none() && spatial.is_none() && count * passes.max(1) as u64 > MAX_RENDER_WORK {
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
        if sparse.is_none()
            && spatial.is_none()
            && count * (paint_work + mask_work) > crate::paint::MAX_PAINT_WORK
        {
            return Err(limit("Render exceeds paint evaluation work limit"));
        }
        let own_work = if let Some(neighborhood) = &neighborhood {
            neighborhood.work(document, &texts, spatial.as_ref(), &plan, u32::MAX, control)?
        } else if let Some(plan) = &spatial {
            if plan.paint_work > crate::paint::MAX_PAINT_WORK {
                return Err(limit("Spatial paint work exceeds limit"));
            }
            plan.work
                .saturating_add(reconstruction_work)
                .saturating_add(pixel_warp_work)
        } else {
            sparse.as_ref().map_or_else(
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
                        .saturating_add(outline_scan_work)
                        .saturating_add(tiled_path_work)
                },
                |s| s.work,
            )
        };
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
        let buffer_count = if tiled {
            let edge = super::tiled::EDGE + 2 * neighborhood.as_ref().map_or(0, |p| p.halo);
            u64::from(width.min(edge)) * u64::from(height.min(edge))
        } else {
            count
        };
        let buffer_pixels = sparse.as_ref().map_or_else(
            || {
                buffer_count
                    * (shape_buffers
                        + buffer_depth
                        + clipping_buffers
                        + 2
                        + usize::from(!texts.is_empty())
                        + 2 * usize::from(document.items.iter().any(|i| !i.filters.is_empty()))
                        + 2 * usize::from(document.items.iter().any(|i| !i.effects.is_empty())))
                        as u64
                    + (buffer_count * references as u64).div_ceil(4)
                    + buffer_count * 3 * u64::from(references != 0)
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
        let mut buffers = (buffer_pixels * 4).max(mask_plan.buffer_values)
            + spatial.as_ref().map_or(0, |p| p.buffer_values);
        for (i, item) in document.items.iter().enumerate() {
            control.check()?;
            if !scene::effective_visible(document, i)? {
                continue;
            }
            if tiled {
                let pixels = match &item.content {
                    Content::Samples { grid } => grid.width as u64 * grid.height as u64,
                    Content::Raster { width, height, .. } => *width as u64 * *height as u64,
                    _ => 0,
                };
                work = work.saturating_add(pixels * 3);
                buffers = buffers.saturating_add(pixels * 8);
                crate::objects::charge(pixels * 3)?;
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
            spatial,
            control: control.clone(),
            objects,
            linear: crate::hdr::linear(document),
            antialias: plan.options.antialias,
            light: document.global_light,
            track_shape: crate::knockout::active(document),
            masks: crate::masks::prepare_document(document)?,
            assets: assets::resolve(document, asset_root)?,
            inline_samples: if tiled {
                let mut values = BTreeMap::new();
                for (i, item) in document.items.iter().enumerate() {
                    control.check()?;
                    if !scene::effective_visible(document, i)? {
                        continue;
                    }
                    let decoded = match &item.content {
                        Content::Samples { grid } => {
                            Some(grid.decode(crate::hdr::linear(document))?)
                        }
                        Content::Raster {
                            width, rgba_hex, ..
                        } => Some(crate::samples::decode_native(
                            *width,
                            &unhex(rgba_hex),
                            crate::samples::Depth::U8,
                            crate::samples::Channels::Rgba,
                            crate::hdr::Encoding::EncodedSrgb,
                            None,
                            crate::hdr::linear(document),
                        )?),
                        _ => None,
                    };
                    if let Some(decoded) = decoded {
                        values.insert(item.id.clone(), decoded);
                    }
                }
                values
            } else {
                BTreeMap::new()
            },
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
            neighborhood,
            tile_work: own_work,
            sampling: plan,
            work,
            buffers,
            object_count,
            depth,
            source_profiles,
        })
    }
    pub fn render(&self) -> Result<Vec<f64>, Error> {
        if self.sampling.options.evaluation == crate::render_quality::Evaluation::Tiled {
            return Err(Error::new(
                "UNSUPPORTED_TILED_RENDER",
                "Use the regional sample visitor for tiled evaluation; a complete floating-point surface is not allocated",
            ));
        }
        self.resources.control.check()?;
        let width = self.document.width * self.sampling.internal_scale;
        let height = self.document.height * self.sampling.internal_scale;
        let masks = self.mask_plan.render_ref(Some(&self.resources.control))?;
        let mut accum = vec![0.0; width as usize * height as usize * 4];
        // Source plans and immutable stores are shared through this borrow.
        let resources = ResourcesView {
            tile: None,
            base: &self.resources,
            artwork_masks: &masks,
            control: &self.resources.control,
            origin: [0; 2],
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
    /// Output bands arrive top-to-bottom; small tiles within each band visit
    /// neighboring regions together. Samples retain exact global coordinates.
    pub(crate) fn visit(
        &self,
        consume: impl FnMut([u32; 2], [u32; 2], &[f64]) -> Result<(), Error>,
    ) -> Result<(), Error> {
        self.visit_rows(u32::MAX, consume)
    }
    pub(crate) fn visit_rows(
        &self,
        max_rows: u32,
        mut consume: impl FnMut([u32; 2], [u32; 2], &[f64]) -> Result<(), Error>,
    ) -> Result<(), Error> {
        if self.sampling.options.evaluation != crate::render_quality::Evaluation::Tiled {
            let result = self.samples()?;
            return consume([0; 2], [result.width, result.height], &result.rgba);
        }
        let factor = self.sampling.options.antialias.factor();
        let traversal = self.traversal(max_rows);
        if let Some(neighborhood) = &self.neighborhood
            && traversal.rows != self.traversal(u32::MAX).rows
        {
            let work = neighborhood.work(
                &self.document,
                &self.resources.texts,
                self.resources.spatial.as_ref(),
                &self.sampling,
                max_rows,
                &self.resources.control,
            )?;
            if self.work - self.tile_work + work > MAX_RENDER_WORK {
                return Err(limit(
                    "Codec band filter neighborhoods exceed render work limit",
                ));
            }
        }
        let empty_masks = BTreeMap::new();
        let total = traversal.total;
        let mut completed = 0;
        self.resources
            .control
            .progress("render_tiles", completed, Some(total));
        for ([x, y], output_size) in traversal.tiles() {
            self.resources.control.check()?;
            let mut size = [
                output_size[0] * factor,
                output_size[1] * factor,
                self.sampling.internal_scale,
            ];
            let mut origin = [
                self.sampling.offset + x * factor,
                self.sampling.offset + y * factor,
            ];
            if let Some(neighborhood) = &self.neighborhood {
                let (start, extent) = neighborhood.region(
                    origin,
                    [size[0], size[1]],
                    self.sampling
                        .evaluation
                        .map(|v| v * self.sampling.internal_scale),
                );
                origin = start;
                [size[0], size[1]] = extent;
            }
            let tile = self
                .resources
                .spatial
                .as_ref()
                .map(|p| p.tile(origin, [size[0], size[1]]));
            let resources = ResourcesView {
                tile: tile.as_ref(),
                base: &self.resources,
                artwork_masks: &empty_masks,
                control: &self.resources.control,
                origin,
            };
            let mut accum = vec![0.0; size[0] as usize * size[1] as usize * 4];
            draw_items(&self.document, None, &mut accum, None, size, &resources)?;
            if accum.iter().any(|v| !v.is_finite()) {
                return Err(Error::new(
                    "NONFINITE_RENDER",
                    "Compositing exceeded finite working precision",
                ));
            }
            let mut samples =
                Vec::with_capacity(output_size[0] as usize * output_size[1] as usize * 4);
            self.sampling
                .visit_region(&accum, size[0], origin, [x, y], output_size, |p| {
                    samples.extend_from_slice(&p)
                });
            consume([x, y], output_size, &samples)?;
            completed += 1;
            self.resources
                .control
                .progress("render_tiles", completed, Some(total));
        }
        self.resources.control.check()
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
