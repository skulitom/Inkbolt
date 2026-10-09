use crate::assets::{self, Crop, Pixels, Sampling};
use crate::{Error, geometry, model::*, scene};
use base64::{Engine, engine::general_purpose::STANDARD};
use serde_json::{Value, json};
use std::{collections::BTreeMap, path::Path};

mod coverage_path;
pub(crate) mod prepared;
mod sparse;

pub const MAX_RENDER_PIXELS: u64 = 1_048_576;
pub const MAX_RENDER_WORK: u64 = 67_108_864;
pub const MAX_BUFFER_PIXELS: u64 = 4_194_304;
pub fn hex(bytes: &[u8]) -> String {
    const DIGITS: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(bytes.len() * 2);
    for b in bytes {
        out.push(DIGITS[(b >> 4) as usize] as char);
        out.push(DIGITS[(b & 15) as usize] as char);
    }
    out
}
pub(crate) fn unhex(text: &str) -> Vec<u8> {
    fn digit(v: u8) -> u8 {
        if v.is_ascii_digit() {
            v - b'0'
        } else {
            v.to_ascii_lowercase() - b'a' + 10
        }
    }
    text.as_bytes()
        .as_chunks::<2>()
        .0
        .iter()
        .map(|b| digit(b[0]) * 16 + digit(b[1]))
        .collect()
}
fn paint(color: Color, antialias: bool) -> tiny_skia::Paint<'static> {
    let mut p = tiny_skia::Paint {
        anti_alias: antialias,
        ..Default::default()
    };
    p.set_color_rgba8(color[0], color[1], color[2], color[3]);
    p
}
fn painted_pixels(
    item: &Item,
    width: u32,
    height: u32,
    scale: u32,
    world: Matrix,
    (antialias, linear): (crate::render_quality::Antialias, bool),
) -> Result<Vec<f64>, Error> {
    painted_region(
        item,
        [width, height, scale],
        world,
        (antialias, linear),
        [0; 2],
        None,
    )
}
fn painted_region(
    item: &Item,
    [width, height, scale]: [u32; 3],
    world: Matrix,
    (antialias, linear): (crate::render_quality::Antialias, bool),
    origin: [u32; 2],
    control: Option<&crate::control::Control>,
) -> Result<Vec<f64>, Error> {
    let rectangle;
    let (geometry, fill, stroke, fill_rule, dither) = match &item.content {
        Content::Vector {
            geometry,
            fill,
            stroke,
            fill_rule,
        } => (
            geometry,
            fill.as_ref(),
            stroke.as_deref(),
            *fill_rule,
            Dither::None,
        ),
        Content::Fill {
            width,
            height,
            paint,
            dither,
        } => {
            rectangle = Geometry::Rect {
                x: 0.0,
                y: 0.0,
                width: *width as f64,
                height: *height as f64,
            };
            (&rectangle, Some(paint), None, FillRule::Nonzero, *dither)
        }
        _ => unreachable!(),
    };
    let mut coverage = tiny_skia::Pixmap::new(width, height)
        .ok_or_else(|| limit("Unable to allocate paint coverage"))?;
    let placed = |matrix: Matrix| {
        let mut matrix = matrix.map(|v| v * scale as f64);
        matrix[4] -= origin[0] as f64;
        matrix[5] -= origin[1] as f64;
        matrix
    };
    let transform = placed(world);
    let mut result = vec![0.0; width as usize * height as usize * 4];
    let local = geometry::inverse(world)?;
    for (source, stroke) in fill
        .map(|p| (p, None))
        .into_iter()
        .chain(stroke.map(|s| (&s.color, Some(s))))
    {
        if let Some(control) = control {
            control.check()?;
        }
        coverage.fill(tiny_skia::Color::TRANSPARENT);
        if let Some(stroke) = stroke {
            if let Some(outline) = crate::strokes::generate_placed(geometry, stroke, world)? {
                let stroke_transform = placed(stroke.scaling.matrix(world));
                coverage.fill_path(
                    &coverage_path::path(&outline, stroke_transform)?,
                    &paint([255; 4], antialias.coverage()),
                    tiny_skia::FillRule::Winding,
                    tiny_skia::Transform::identity(),
                    None,
                );
            }
        } else {
            coverage.fill_path(
                &coverage_path::path(geometry, transform)?,
                &paint([255; 4], antialias.coverage()),
                match fill_rule {
                    FillRule::Nonzero => tiny_skia::FillRule::Winding,
                    FillRule::EvenOdd => tiny_skia::FillRule::EvenOdd,
                },
                tiny_skia::Transform::identity(),
                None,
            );
        }
        let sampler = crate::paint::Sampler::new(source, world)?;
        for (i, (dst, pixel)) in result
            .as_chunks_mut::<4>()
            .0
            .iter_mut()
            .zip(coverage.pixels())
            .enumerate()
        {
            if i.is_multiple_of(4096)
                && let Some(control) = control
            {
                control.check()?;
            }
            if pixel.alpha() == 0 {
                continue;
            }
            let canvas = [
                origin[0] as f64 + (i % width as usize) as f64 + 0.5,
                origin[1] as f64 + (i / width as usize) as f64 + 0.5,
            ]
            .map(|v| v / scale as f64);
            let mut color =
                crate::paint::dither(sampler.sample(canvas), geometry::map(local, canvas), dither);
            if linear {
                for v in &mut color[..3] {
                    *v = crate::hdr::decode(*v);
                }
            }
            composite(
                dst,
                color,
                pixel.alpha() as f64 / 255.0,
                BlendMode::Normal,
                linear,
            );
        }
    }
    Ok(result)
}
pub(crate) fn image_pixels(
    pixels: &dyn crate::samples::Source,
    crop: Crop,
    frame: [f64; 2],
    sampling: Sampling,
    (size, antialias, control): (
        [u32; 3],
        crate::render_quality::Antialias,
        Option<&crate::control::Control>,
    ),
    world: Matrix,
    warp: Option<&crate::pixel_warps::Plan>,
) -> Result<Vec<f64>, Error> {
    let [width, height, _] = size;
    let mut result = vec![0.0; width as usize * height as usize * 4];
    image_map(
        crop,
        frame,
        sampling,
        (size, antialias, control),
        world,
        warp,
        |i, point, plan, coverage| {
            let color = pixels.sample_planned(crop, point, plan)?;
            let alpha = color[3] * coverage as f64 / 255.0;
            result[i * 4..i * 4 + 4].copy_from_slice(&[
                color[0] * alpha,
                color[1] * alpha,
                color[2] * alpha,
                alpha,
            ]);
            Ok(())
        },
    )?;
    Ok(result)
}
pub(crate) fn image_map(
    crop: Crop,
    frame: [f64; 2],
    sampling: Sampling,
    (size, antialias, control): (
        [u32; 3],
        crate::render_quality::Antialias,
        Option<&crate::control::Control>,
    ),
    world: Matrix,
    warp: Option<&crate::pixel_warps::Plan>,
    mut consume: impl FnMut(usize, Point, &crate::resample::Plan, u8) -> Result<(), Error>,
) -> Result<(), Error> {
    let [width, height, scale] = size;
    let geometry = warp.map_or(
        Geometry::Rect {
            x: 0.0,
            y: 0.0,
            width: frame[0],
            height: frame[1],
        },
        |p| p.geometry(),
    );
    let path = coverage_path::path(&geometry, world.map(|v| v * scale as f64))?;
    let mut mask = tiny_skia::Mask::new(width, height)
        .ok_or_else(|| limit("Unable to allocate image coverage"))?;
    mask.fill_path(
        &path,
        tiny_skia::FillRule::Winding,
        antialias.coverage(),
        tiny_skia::Transform::identity(),
    );
    let inverse = geometry::inverse(world)?;
    let sampling_plan = crate::resample::Plan::new(
        sampling,
        crate::resample::footprint(crop, frame, world, scale)?,
    )?;
    for i in 0..width as usize * height as usize {
        if i.is_multiple_of(4096)
            && let Some(control) = control
        {
            control.check()?;
        }
        if mask.data()[i] == 0 {
            continue;
        }
        let canvas = [
            (i % width as usize) as f64 + 0.5,
            (i / width as usize) as f64 + 0.5,
        ]
        .map(|v| v / scale as f64);
        let local = geometry::map(inverse, canvas);
        let local = warp.map_or(local, |p| p.inverse_edge_clamped(local));
        let point = [
            crop.x as f64 + local[0] / frame[0] * crop.width as f64,
            crop.y as f64 + local[1] / frame[1] * crop.height as f64,
        ];
        consume(i, point, &sampling_plan, mask.data()[i])?;
    }
    Ok(())
}
fn composite(dst: &mut [f64], src: [f64; 4], opacity: f64, blend: BlendMode, linear: bool) {
    let sa = src[3] * opacity;
    let da = dst[3];
    let mixed = crate::hdr::mix(
        std::array::from_fn(|c| if da == 0.0 { 0.0 } else { dst[c] / da }),
        [src[0], src[1], src[2]],
        blend,
        linear,
    );
    for c in 0..3 {
        let source = src[c];
        dst[c] = (1.0 - sa) * dst[c] + sa * ((1.0 - da) * source + da * mixed[c]);
    }
    dst[3] = sa + da * (1.0 - sa);
}
pub(crate) fn geometry_mask(
    geometry: &Geometry,
    fill_rule: FillRule,
    transform: Matrix,
    width: u32,
    height: u32,
    antialias: crate::render_quality::Antialias,
) -> Result<tiny_skia::Mask, Error> {
    let mut mask = tiny_skia::Mask::new(width, height)
        .ok_or_else(|| limit("Unable to allocate geometry mask"))?;
    if matches!(geometry, Geometry::Compound { .. }) {
        let values = crate::work_paths::coverage::evaluate(
            geometry,
            fill_rule,
            transform,
            width,
            height,
            antialias.coverage(),
        )?;
        mask.data_mut().copy_from_slice(&values);
        return Ok(mask);
    }
    let path = coverage_path::path(geometry, transform)?;
    mask.fill_path(
        &path,
        match fill_rule {
            FillRule::Nonzero => tiny_skia::FillRule::Winding,
            FillRule::EvenOdd => tiny_skia::FillRule::EvenOdd,
        },
        antialias.coverage(),
        tiny_skia::Transform::identity(),
    );
    Ok(mask)
}
fn clip_mask(
    item: &Item,
    world: Matrix,
    width: u32,
    height: u32,
    scale: u32,
    antialias: crate::render_quality::Antialias,
) -> Result<Option<tiny_skia::Mask>, Error> {
    let Some(clip) = item.clip.as_ref().filter(|clip| clip.enabled) else {
        return Ok(None);
    };
    let transform = geometry::multiply(world, clip.transform).map(|v| v * scale as f64);
    Ok(Some(geometry_mask(
        &clip.geometry,
        clip.fill_rule,
        transform,
        width,
        height,
        antialias,
    )?))
}
struct Resources {
    control: crate::control::Control,
    objects: BTreeMap<String, prepared::Prepared>,
    linear: bool,
    antialias: crate::render_quality::Antialias,
    light: crate::effects::Lighting,
    track_shape: bool,
    masks: BTreeMap<String, crate::masks::Prepared>,
    assets: BTreeMap<String, Pixels>,
    texts: BTreeMap<String, crate::text::Layout>,
}
struct ResourcesView<'a> {
    base: &'a Resources,
    artwork_masks: &'a BTreeMap<String, Vec<f64>>,
    control: &'a crate::control::Control,
}
impl std::ops::Deref for ResourcesView<'_> {
    type Target = Resources;
    fn deref(&self) -> &Resources {
        self.base
    }
}

fn text_pixels(
    item: &Item,
    layout: &crate::text::Layout,
    width: u32,
    height: u32,
    scale: u32,
    world: Matrix,
    (antialias, linear): (crate::render_quality::Antialias, bool),
) -> Result<Vec<f64>, Error> {
    let mut result = vec![0.0; width as usize * height as usize * 4];
    for p in &layout.paths {
        let mut glyph = item.clone();
        glyph.content = Content::Vector {
            geometry: p.geometry.clone(),
            fill: Some(p.fill.clone()),
            stroke: None,
            fill_rule: FillRule::Nonzero,
        };
        let pixels = painted_pixels(&glyph, width, height, scale, world, (antialias, linear))?;
        for (dst, src) in result
            .as_chunks_mut::<4>()
            .0
            .iter_mut()
            .zip(pixels.as_chunks::<4>().0)
        {
            let a = src[3];
            if a != 0.0 {
                composite(
                    dst,
                    [src[0] / a, src[1] / a, src[2] / a, a],
                    1.0,
                    BlendMode::Normal,
                    linear,
                );
            }
        }
    }
    if let Some(geometry) = crate::text::clip_geometry(&item.content, layout) {
        let mut clipped = item.clone();
        clipped.clip = Some(Clip {
            geometry,
            fill_rule: FillRule::Nonzero,
            transform: identity(),
            enabled: true,
        });
        let mask = clip_mask(&clipped, world, width, height, scale, antialias)?.unwrap();
        for (pixel, &coverage) in result.as_chunks_mut::<4>().0.iter_mut().zip(mask.data()) {
            for v in pixel {
                *v *= coverage as f64 / 255.0;
            }
        }
    }
    Ok(result)
}
fn apply_adjustment(
    document: &Document,
    i: usize,
    pixels: &mut [f64],
    size: [u32; 3],
    resources: &ResourcesView<'_>,
) -> Result<(), Error> {
    let item = &document.items[i];
    if !item.visible || item.opacity == 0.0 {
        return Ok(());
    }
    let Content::Adjustment { adjustment } = &item.content else {
        unreachable!()
    };
    let [width, height, scale] = size;
    let mask = clip_mask(
        item,
        scene::world_transform(document, i)?,
        width,
        height,
        scale,
        resources.antialias,
    )?;
    for (n, pixel) in pixels.as_chunks_mut::<4>().0.iter_mut().enumerate() {
        let alpha = pixel[3];
        if alpha == 0.0 {
            continue;
        }
        let weight = item.opacity
            * resources.artwork_masks.get(&item.id).map_or(1.0, |m| m[n])
            * mask.as_ref().map_or(1.0, |m| m.data()[n] as f64 / 255.0)
            * resources.masks.get(&item.id).map_or(1.0, |m| {
                m.sample([
                    (n % width as usize) as f64 / scale as f64 + 0.5 / scale as f64,
                    (n / width as usize) as f64 / scale as f64 + 0.5 / scale as f64,
                ])
            });
        if weight == 0.0 {
            continue;
        }
        let before = std::array::from_fn(|c| (pixel[c] / alpha).clamp(0.0, 1.0));
        let after = crate::adjustments::evaluate(before, adjustment);
        let adjusted = crate::blending::mix(before, after, item.blend);
        for c in 0..3 {
            pixel[c] = (before[c] + weight * (adjusted[c] - before[c])) * alpha;
        }
    }
    Ok(())
}
fn apply_clipped_adjustments(
    document: &Document,
    i: usize,
    pixels: &mut [f64],
    size: [u32; 3],
    resources: &ResourcesView<'_>,
) -> Result<(), Error> {
    let siblings = scene::children(document, document.items[i].parent.as_deref());
    let position = siblings.iter().position(|&j| j == i).unwrap();
    for &j in &siblings[position + 1..] {
        if matches!(
            document.items[j].content,
            Content::WorkPath { .. } | Content::MaskSource {}
        ) {
            continue;
        }
        if !matches!(&document.items[j].content,Content::Adjustment{adjustment} if adjustment.clip_to.is_some())
        {
            break;
        }
        apply_adjustment(document, j, pixels, size, resources)?;
    }
    Ok(())
}
struct Coverage<'a> {
    opacity: f64,
    width: u32,
    scale: u32,
    mask: Option<&'a crate::masks::Prepared>,
    artwork_mask: Option<&'a [f64]>,
    clip: Option<tiny_skia::Mask>,
    frame: Option<tiny_skia::Mask>,
    mode: crate::coverage::Mode,
    inverse: Matrix,
}
impl Coverage<'_> {
    fn alpha(&self, pixel: usize, alpha: f64) -> f64 {
        self.sample(pixel, alpha, self.opacity)
    }
    fn shape(&self, pixel: usize, shape: f64) -> f64 {
        self.sample(pixel, shape, 1.0)
    }
    fn sample(&self, pixel: usize, alpha: f64, opacity: f64) -> f64 {
        let point = [
            (pixel % self.width as usize) as f64 + 0.5,
            (pixel / self.width as usize) as f64 + 0.5,
        ]
        .map(|v| v / self.scale as f64);
        self.mode.alpha(
            alpha * opacity * self.mask_at(pixel),
            geometry::map(self.inverse, point),
        )
    }
    fn at(&self, pixel: usize) -> f64 {
        self.opacity * self.mask_at(pixel)
    }
    fn mask_at(&self, pixel: usize) -> f64 {
        self.artwork_mask.map_or(1.0, |m| m[pixel])
            * self.mask.map_or(1.0, |mask| {
                mask.sample([
                    (pixel % self.width as usize) as f64 / self.scale as f64
                        + 0.5 / self.scale as f64,
                    (pixel / self.width as usize) as f64 / self.scale as f64
                        + 0.5 / self.scale as f64,
                ])
            })
            * self
                .clip
                .as_ref()
                .map_or(1.0, |m| m.data()[pixel] as f64 / 255.0)
            * self
                .frame
                .as_ref()
                .map_or(1.0, |m| m.data()[pixel] as f64 / 255.0)
    }
}
fn coverage<'a>(
    item: &Item,
    world: Matrix,
    size: [u32; 3],
    resources: &'a ResourcesView<'_>,
) -> Result<Coverage<'a>, Error> {
    let [width, height, scale] = size;
    let clip = clip_mask(item, world, width, height, scale, resources.antialias)?;
    let frame = if let Content::Frame { frame } = &item.content {
        let mut temporary = item.clone();
        temporary.clip = Some(frame.clip());
        clip_mask(&temporary, world, width, height, scale, resources.antialias)?
    } else {
        None
    };
    Ok(Coverage {
        opacity: item.opacity,
        width,
        scale,
        mask: resources.masks.get(&item.id),
        artwork_mask: resources.artwork_masks.get(&item.id).map(Vec::as_slice),
        clip,
        frame,
        mode: item.coverage,
        inverse: geometry::inverse(world)?,
    })
}
// Shape is intrinsic evaluated alpha before item fill/opacity. Containers
// retain the union of child footprints independently of the resulting alpha.
struct Surface {
    pixels: Vec<f64>,
    shape: Option<Vec<f64>>,
}
fn alphas(pixels: &[f64]) -> Vec<f64> {
    pixels.as_chunks::<4>().0.iter().map(|p| p[3]).collect()
}
fn transform_shape(
    item: &Item,
    shape: &mut [f64],
    size: [u32; 3],
    world: Matrix,
    filters: bool,
    light: crate::effects::Lighting,
) -> Result<(), Error> {
    if (filters && item.filters.is_empty()) || (!filters && item.effects.is_empty()) {
        return Ok(());
    }
    let mut pixels: Vec<f64> = shape.iter().flat_map(|&a| [0.0, 0.0, 0.0, a]).collect();
    if filters {
        crate::filters::apply(item, &mut pixels, size, world)?;
    } else {
        let mut shape_item = item.clone();
        shape_item.fill_opacity = 1.0;
        crate::effects::apply(&shape_item, &mut pixels, size, world, light)?;
    }
    for (f, p) in shape.iter_mut().zip(pixels.as_chunks::<4>().0) {
        *f = p[3];
    }
    Ok(())
}
fn decorate(
    item: &Item,
    surface: &mut Surface,
    size: [u32; 3],
    world: Matrix,
    light: crate::effects::Lighting,
) -> Result<(), Error> {
    if let Some(shape) = &mut surface.shape {
        transform_shape(item, shape, size, world, false, light)?;
    }
    crate::effects::apply(item, &mut surface.pixels, size, world, light)?;
    if let Some(shape) = &mut surface.shape {
        // Alpha-dependent decorations and replacement filters need not be
        // monotone. A footprint always contains its actual visible coverage.
        for (f, p) in shape.iter_mut().zip(surface.pixels.as_chunks::<4>().0) {
            *f = f.max(p[3]);
        }
    }
    Ok(())
}
// Draw one independently compositable item before its own opacity, clips and
// masks. Those effects apply once after its entire clipping group is assembled.
fn drawable_pixels(
    document: &Document,
    i: usize,
    size: [u32; 3],
    resources: &ResourcesView<'_>,
) -> Result<Surface, Error> {
    resources.control.check()?;
    let item = &document.items[i];
    let [width, height, scale] = size;
    let world = scene::world_transform(document, i)?;
    let mut shape = None;
    let mut pixels = match &item.content {
        Content::Group { isolated: true, .. } | Content::Frame { .. } => {
            let mut pixels = if let Content::Frame { frame } = &item.content
                && let Some(color) = frame.background
            {
                let mut background = item.clone();
                background.content = Content::Vector {
                    geometry: frame.geometry(),
                    fill: Some(Paint::Solid(color)),
                    stroke: None,
                    fill_rule: FillRule::Nonzero,
                };
                painted_pixels(
                    &background,
                    width,
                    height,
                    scale,
                    world,
                    (resources.antialias, resources.linear),
                )?
            } else {
                vec![0.0; width as usize * height as usize * 4]
            };
            shape = resources.track_shape.then(|| alphas(&pixels));
            draw_items(
                document,
                Some(&item.id),
                &mut pixels,
                shape.as_deref_mut(),
                size,
                resources,
            )?;
            pixels
        }
        Content::Vector { .. } | Content::Fill { .. } => painted_pixels(
            item,
            width,
            height,
            scale,
            world,
            (resources.antialias, resources.linear),
        )?,
        Content::Text { .. } | Content::StoryFrame { .. } => text_pixels(
            item,
            &resources.texts[&item.id],
            width,
            height,
            scale,
            world,
            (resources.antialias, resources.linear),
        )?,
        Content::Object { object } => {
            let warp = crate::pixel_warps::plan(item)?;
            let source = &resources.objects[&item.id];
            let [w, h] = source.sampling.output;
            let pixels = source.object_surface(object, resources.linear)?;
            image_pixels(
                &pixels,
                assets::crop(w, h, None)?,
                [object.width, object.height],
                object.sampling,
                (size, resources.antialias, Some(resources.control)),
                world,
                warp.as_ref(),
            )?
        }
        Content::Samples { grid } => {
            let warp = crate::pixel_warps::plan(item)?;
            image_pixels(
                &grid.decode(resources.linear)?,
                assets::crop(grid.width, grid.height, None)?,
                [grid.width as f64, grid.height as f64],
                grid.sampling,
                (size, resources.antialias, Some(resources.control)),
                world,
                warp.as_ref(),
            )?
        }
        Content::Raw { raw } => {
            let grid = raw.grid(resources.control)?;
            let warp = crate::pixel_warps::plan(item)?;
            image_pixels(
                &grid.decode(resources.linear)?,
                assets::crop(grid.width, grid.height, None)?,
                [grid.width as f64, grid.height as f64],
                grid.sampling,
                (size, resources.antialias, Some(resources.control)),
                world,
                warp.as_ref(),
            )?
        }
        Content::Raster {
            width: w,
            height: h,
            rgba_hex,
            sampling,
        } => {
            let warp = crate::pixel_warps::plan(item)?;
            let inline = Pixels {
                width: *w,
                height: *h,
                rgba: unhex(rgba_hex),
            };
            let converted;
            let pixels: &dyn crate::samples::Source = if resources.linear {
                converted = crate::samples::Decoded::from_pixels(&inline);
                &converted
            } else {
                &inline
            };
            image_pixels(
                pixels,
                assets::crop(*w, *h, None)?,
                [*w as f64, *h as f64],
                *sampling,
                (size, resources.antialias, Some(resources.control)),
                world,
                warp.as_ref(),
            )?
        }
        Content::Image {
            asset_id,
            width: w,
            height: h,
            crop,
            sampling,
        } => {
            let warp = crate::pixel_warps::plan(item)?;
            let source = &resources.assets[asset_id];
            let converted;
            let pixels: &dyn crate::samples::Source = if resources.linear {
                converted = crate::samples::Decoded::from_pixels(source);
                &converted
            } else {
                source
            };
            image_pixels(
                pixels,
                assets::crop(source.width, source.height, *crop)?,
                [*w, *h],
                *sampling,
                (size, resources.antialias, Some(resources.control)),
                world,
                warp.as_ref(),
            )?
        }
        _ => unreachable!("Validated independently compositable item"),
    };
    if let Some(grade) = item.hdr_grade {
        grade.apply(&mut pixels);
    }
    if let Some(shape) = &mut shape {
        transform_shape(item, shape, size, world, true, resources.light)?;
    }
    crate::filters::apply(item, &mut pixels, size, world)?;
    if resources.track_shape && shape.is_none() {
        shape = Some(alphas(&pixels));
    }
    if crate::backgrounds::matte(document, &item.id).is_none() {
        apply_clipped_adjustments(document, i, &mut pixels, size, resources)?;
    }
    Ok(Surface { pixels, shape })
}
fn apply_clipped_layers(
    document: &Document,
    i: usize,
    pixels: &mut [f64],
    size: [u32; 3],
    resources: &ResourcesView<'_>,
) -> Result<(), Error> {
    let siblings = scene::children(document, document.items[i].parent.as_deref());
    let position = siblings.iter().position(|&j| j == i).unwrap();
    for &j in &siblings[position + 1..] {
        let item = &document.items[j];
        if crate::layer_clipping::auxiliary(&item.content) {
            continue;
        }
        if item.clip_to.as_deref() != Some(document.items[i].id.as_str()) {
            break;
        }
        if !item.visible || item.opacity == 0.0 {
            continue;
        }
        let mut source = drawable_pixels(document, j, size, resources)?;
        decorate(
            item,
            &mut source,
            size,
            scene::world_transform(document, j)?,
            resources.light,
        )?;
        let coverage = coverage(item, scene::world_transform(document, j)?, size, resources)?;
        for (pixel, (dst, src)) in pixels
            .as_chunks_mut::<4>()
            .0
            .iter_mut()
            .zip(source.pixels.as_chunks::<4>().0)
            .enumerate()
        {
            let alpha = dst[3];
            let weight = coverage.alpha(pixel, src[3]);
            if alpha == 0.0 || weight == 0.0 {
                continue;
            }
            let before = std::array::from_fn(|c| dst[c] / alpha);
            let color = std::array::from_fn(|c| src[c] / src[3]);
            let mixed = crate::hdr::mix(before, color, item.blend, resources.linear);
            for c in 0..3 {
                dst[c] = ((1.0 - weight) * before[c] + weight * mixed[c]) * alpha;
            }
            // Preserve base alpha, including antialiased/translucent edges.
        }
    }
    Ok(())
}
fn draw_items(
    document: &Document,
    parent: Option<&str>,
    accum: &mut [f64],
    mut shape: Option<&mut [f64]>,
    size: [u32; 3],
    resources: &ResourcesView<'_>,
) -> Result<(), Error> {
    let knockout = parent.is_some_and(|id| {
        document.items[scene::index(document, id).unwrap()]
            .content
            .is_knockout()
    });
    let initial = knockout.then(|| accum.to_vec());
    for i in scene::children(document, parent) {
        resources.control.check()?;
        let item = &document.items[i];
        let background = crate::backgrounds::matte(document, &item.id);
        if !item.visible
            || (!resources.track_shape && item.opacity == 0.0 && background.is_none())
            || item.clip_to.is_some()
            || matches!(
                item.content,
                Content::WorkPath { .. } | Content::MaskSource {}
            )
        {
            continue;
        }
        if let Content::Adjustment { adjustment } = &item.content {
            // Backdrop adjustments modify the current group result, retaining
            // its footprint. They are operators, not new painting elements.
            if adjustment.clip_to.is_none() {
                apply_adjustment(document, i, accum, size, resources)?;
            }
            continue;
        }
        let world = scene::world_transform(document, i)?;
        if matches!(
            item.content,
            Content::Group {
                isolated: false,
                ..
            }
        ) {
            if crate::layer_clipping::needs_buffer(item) || resources.track_shape {
                let backdrop = initial.as_deref().unwrap_or(accum);
                let mut after = backdrop.to_vec();
                let mut child_shape = resources.track_shape.then(|| vec![0.0; accum.len() / 4]);
                draw_items(
                    document,
                    Some(&item.id),
                    &mut after,
                    child_shape.as_deref_mut(),
                    size,
                    resources,
                )?;
                let coverage = coverage(item, world, size, resources)?;
                for (pixel, (dst, src)) in accum
                    .as_chunks_mut::<4>()
                    .0
                    .iter_mut()
                    .zip(after.as_chunks::<4>().0)
                    .enumerate()
                {
                    let f = child_shape
                        .as_ref()
                        .map_or(0.0, |s| coverage.shape(pixel, s[pixel]));
                    let weight = coverage.at(pixel);
                    if let Some(initial) = &initial {
                        let b = &initial[pixel * 4..pixel * 4 + 4];
                        for c in 0..4 {
                            dst[c] = (1.0 - f) * dst[c] + f * b[c] + weight * (src[c] - b[c]);
                        }
                        project_premultiplied(dst);
                    } else {
                        for c in 0..4 {
                            dst[c] += (src[c] - dst[c]) * weight;
                        }
                    }
                    if let Some(shape) = &mut shape {
                        shape[pixel] += (1.0 - shape[pixel]) * f;
                    }
                }
            } else {
                draw_items(document, Some(&item.id), accum, None, size, resources)?;
            }
            continue;
        }
        let mut surface = drawable_pixels(document, i, size, resources)?;
        if let Some(matte) = background {
            // The retained source keeps all its controls. Only its completed
            // appearance is composited onto an opaque current-canvas matte.
            // Clipped siblings then see that opaque base, including outside the
            // source grid. Applying the matte to the final backdrop would lose
            // those clipping and adjustment semantics.
            decorate(item, &mut surface, size, world, resources.light)?;
            let coverage = coverage(item, world, size, resources)?;
            for (pixel, src) in surface.pixels.as_chunks_mut::<4>().0.iter_mut().enumerate() {
                let mut dst = [
                    matte[0] as f64 / 255.0,
                    matte[1] as f64 / 255.0,
                    matte[2] as f64 / 255.0,
                    1.0,
                ];
                if resources.linear {
                    for v in &mut dst[..3] {
                        *v = crate::hdr::decode(*v);
                    }
                }
                let color = if src[3] == 0.0 {
                    [0.0; 3]
                } else {
                    [src[0] / src[3], src[1] / src[3], src[2] / src[3]]
                };
                composite(
                    &mut dst,
                    [color[0], color[1], color[2], coverage.alpha(pixel, src[3])],
                    1.0,
                    item.blend,
                    resources.linear,
                );
                *src = dst;
            }
            apply_clipped_adjustments(document, i, &mut surface.pixels, size, resources)?;
            apply_clipped_layers(document, i, &mut surface.pixels, size, resources)?;
            // Validation makes this the first printable root, never a nested
            // knockout member. There is no earlier visible backdrop to retain.
            accum.copy_from_slice(&surface.pixels);
            if let Some(shape) = &mut shape {
                shape.fill(1.0);
            }
            continue;
        }
        apply_clipped_layers(document, i, &mut surface.pixels, size, resources)?;
        decorate(item, &mut surface, size, world, resources.light)?;
        let coverage = coverage(item, world, size, resources)?;
        for (pixel, (dst, src)) in accum
            .as_chunks_mut::<4>()
            .0
            .iter_mut()
            .zip(surface.pixels.as_chunks::<4>().0)
            .enumerate()
        {
            let straight = if src[3] == 0.0 {
                [0.0; 4]
            } else {
                [src[0] / src[3], src[1] / src[3], src[2] / src[3], src[3]]
            };
            let alpha = coverage.alpha(pixel, straight[3]);
            let f = surface
                .shape
                .as_ref()
                .map_or(alpha, |s| coverage.shape(pixel, s[pixel]));
            if let Some(initial) = &initial {
                let b: &[f64; 4] = initial[pixel * 4..pixel * 4 + 4].try_into().unwrap();
                crate::knockout::composite(
                    dst,
                    [straight[0], straight[1], straight[2], alpha],
                    f,
                    *b,
                    item.blend,
                );
            } else {
                composite(
                    dst,
                    [straight[0], straight[1], straight[2], alpha],
                    1.0,
                    item.blend,
                    resources.linear,
                );
            }
            if let Some(shape) = &mut shape {
                shape[pixel] += (1.0 - shape[pixel]) * f;
            }
        }
    }
    Ok(())
}
fn project_premultiplied(p: &mut [f64; 4]) {
    p[3] = p[3].clamp(0.0, 1.0);
    for c in 0..3 {
        p[c] = p[c].clamp(0.0, p[3]);
    }
}
pub struct Rasterized {
    pub width: u32,
    pub height: u32,
    pub rgba: Vec<u8>,
}
pub fn rasterize(document: &Document, scale: u32) -> Result<Rasterized, Error> {
    rasterize_with_assets(document, scale, None)
}
pub fn rasterize_with_assets(
    document: &Document,
    scale: u32,
    asset_root: Option<&Path>,
) -> Result<Rasterized, Error> {
    rasterize_with_resources(document, scale, asset_root, None)
}
pub fn rasterize_with_resources(
    document: &Document,
    scale: u32,
    asset_root: Option<&Path>,
    font_root: Option<&Path>,
) -> Result<Rasterized, Error> {
    rasterize_with_options(document, scale, asset_root, font_root, None)
}
pub fn rasterize_with_options(
    document: &Document,
    scale: u32,
    asset_root: Option<&Path>,
    font_root: Option<&Path>,
    options: Option<&crate::render_quality::Options>,
) -> Result<Rasterized, Error> {
    rasterize_controlled(
        document,
        scale,
        asset_root,
        font_root,
        options,
        &crate::control::Control::default(),
    )
}
pub fn rasterize_controlled(
    document: &Document,
    scale: u32,
    asset_root: Option<&Path>,
    font_root: Option<&Path>,
    options: Option<&crate::render_quality::Options>,
    control: &crate::control::Control,
) -> Result<Rasterized, Error> {
    rasterize_final(
        document,
        scale,
        asset_root,
        font_root,
        options,
        crate::render_quality::Plan::finish,
        (false, control),
    )
}
/// Straight normalized samples before display-byte quantization.
pub struct SampleRaster {
    pub width: u32,
    pub height: u32,
    pub rgba: Vec<f64>,
}
pub fn rasterize_samples_with_options(
    document: &Document,
    scale: u32,
    asset_root: Option<&Path>,
    font_root: Option<&Path>,
    options: Option<&crate::render_quality::Options>,
) -> Result<SampleRaster, Error> {
    rasterize_final(
        document,
        scale,
        asset_root,
        font_root,
        options,
        crate::render_quality::Plan::finish_samples,
        (true, &crate::control::Control::default()),
    )
}
fn rasterize_final<T>(
    document: &Document,
    scale: u32,
    asset_root: Option<&Path>,
    font_root: Option<&Path>,
    options: Option<&crate::render_quality::Options>,
    finish: impl FnOnce(&crate::render_quality::Plan, &[f64], u32) -> T,
    context: (bool, &crate::control::Control),
) -> Result<T, Error> {
    let (native_samples, control) = context;
    let prepared = prepared::Prepared::new(
        document,
        scale,
        asset_root,
        font_root,
        options,
        native_samples,
        control,
    )?;
    let accum = prepared.render()?;
    Ok(finish(
        &prepared.sampling,
        &accum,
        prepared.document.width * prepared.sampling.internal_scale,
    ))
}

pub(crate) struct ArtworkMaskPlan {
    prepared: Vec<(
        String,
        crate::artwork_masks::Mask,
        Matrix,
        Document,
        Resources,
    )>,
    size: [u32; 3],
    antialias: crate::render_quality::Antialias,
    pub work: u64,
    pub buffer_values: u64,
    pub retained_values: u64,
    pub receipts: Vec<Value>,
}
pub(crate) fn plan_artwork_masks(
    document: &Document,
    size: [u32; 3],
    fonts: &crate::fonts::Cache,
    antialias: crate::render_quality::Antialias,
    initial_work: [u64; 3],
) -> Result<ArtworkMaskPlan, Error> {
    let [mut passes, mut paint_work, mut outline_work] = initial_work;
    let [width, height, _] = size;
    let count = width as u64 * height as u64;
    let mut prepared = Vec::new();
    let mut commands = 0;
    let mut depth = 0;
    let mut receipts = Vec::new();
    let mut dash_work = crate::strokes::document_work(document)?;
    // Validate every instance, transformed geometry and aggregate work before
    // allocating output-sized buffers. Sources cannot contain opacity masks.
    for (i, item) in document.items.iter().enumerate() {
        let Some(mask) = item.artwork_mask.as_ref().filter(|m| m.enabled) else {
            continue;
        };
        let world = scene::world_transform(document, i)?;
        let instance = crate::artwork_masks::instance(document, mask, world)?;
        let instance = crate::swatches::evaluate(&instance)?.unwrap_or(instance);
        validate(&instance).map_err(|e| e.at_item(&item.id))?;
        dash_work += crate::strokes::document_work(&instance)?;
        crate::strokes::check_work(dash_work, crate::strokes::MAX_INSTANCE_WORK)?;
        outline_work += crate::strokes::generated_work(&instance)?;
        if outline_work * height as u64 > MAX_RENDER_WORK {
            return Err(limit(
                "Artwork-mask stroke outline scan work exceeds render limit",
            ));
        }
        for j in 0..instance.items.len() {
            depth = depth.max(scene::ancestors(&instance, j)?.len() + 1);
        }
        let texts = crate::text::prepare(&instance, fonts)?;
        passes += instance.items.len() as u64
            + texts.values().map(|l| l.paths.len() as u64).sum::<u64>()
            + 1;
        for (j, node) in instance.items.iter().enumerate() {
            if let Some(layout) = texts.get(&node.id) {
                let world = scene::world_transform(&instance, j)?;
                for p in &layout.paths {
                    validate_world_geometry(&p.geometry, world)?;
                    if let Geometry::Path { commands: c } = &p.geometry {
                        commands += c.len();
                    }
                    paint_work += crate::paint::work(&p.fill);
                }
            }
            if let Content::Vector { fill, stroke, .. } = &node.content {
                paint_work += fill
                    .iter()
                    .chain(stroke.iter().map(|s| &s.color))
                    .map(crate::paint::work)
                    .sum::<u64>();
            }
        }
        paint_work += 4;
        if count * passes > MAX_RENDER_WORK
            || count * paint_work > crate::paint::MAX_PAINT_WORK
            || commands > crate::text::MAX_OUTLINE_COMMANDS
        {
            return Err(limit(
                "Artwork-mask instances exceed render, paint or glyph-outline work limits",
            ));
        }
        let evaluated_source_sha256 =
            crate::assets::sha256(&serde_json::to_vec(&instance.items).unwrap());
        receipts.push(json!({"id":item.id,"source":mask.source,"mode":mask.mode,"definition":mask,"source_sha256":crate::artwork_masks::dependency_hash(document,i)?,"evaluated_source_sha256":evaluated_source_sha256,"scalar_space":if mask.mode==crate::artwork_masks::Mode::Alpha {"source_alpha"} else {"encoded_sRGB;0.2125R+0.7154G+0.0721B"},"source_changed":false}));
        prepared.push((
            item.id.clone(),
            mask.as_ref().clone(),
            world,
            instance,
            Resources {
                control: crate::control::Control::default(),
                objects: BTreeMap::new(),
                linear: false,
                antialias,
                light: document.global_light,
                track_shape: false,
                masks: BTreeMap::new(),
                assets: BTreeMap::new(),
                texts,
            },
        ));
    }

    let retained_values = count * prepared.len() as u64;
    if retained_values > crate::artwork_masks::MAX_COVERAGE_PIXELS {
        return Err(limit(
            "Artwork mask coverage exceeds the aggregate sample bound",
        ));
    }
    let buffer_values = retained_values
        + if prepared.is_empty() {
            0
        } else {
            count * 4 * (depth + 2) as u64
        };
    if buffer_values > MAX_BUFFER_PIXELS * 4 {
        return Err(limit(
            "Artwork mask preparation exceeds the render memory bound",
        ));
    }
    Ok(ArtworkMaskPlan {
        prepared,
        size,
        antialias,
        work: count * ((passes - initial_work[0]) + (paint_work - initial_work[1]))
            + (outline_work - initial_work[2]) * height as u64,
        buffer_values,
        retained_values,
        receipts,
    })
}
impl ArtworkMaskPlan {
    pub fn render(
        self,
        control: Option<&crate::control::Control>,
    ) -> Result<BTreeMap<String, Vec<f64>>, Error> {
        self.render_ref(control)
    }
    fn render_ref(
        &self,
        control: Option<&crate::control::Control>,
    ) -> Result<BTreeMap<String, Vec<f64>>, Error> {
        let [width, height, scale] = self.size;
        let count = width as u64 * height as u64;
        let mut values = BTreeMap::new();
        let no_nested_masks = BTreeMap::new();
        for (id, mask, world, instance, instance_resources) in &self.prepared {
            if let Some(control) = control {
                control.check()?;
            }
            let mut rgba = vec![0.0; count as usize * 4];
            draw_items(
                instance,
                None,
                &mut rgba,
                None,
                [width, height, scale],
                &ResourcesView {
                    base: instance_resources,
                    artwork_masks: &no_nested_masks,
                    control: control.unwrap_or(&instance_resources.control),
                },
            )?;
            if let Some(control) = control {
                control.check()?;
            }
            let coverage = if !mask.clip_region {
                rgba.as_chunks::<4>()
                    .0
                    .iter()
                    .map(|p| mask.scalar(p))
                    .collect()
            } else if let Some(region) = mask.region_geometry() {
                let transform =
                    geometry::multiply(mask.world_transform(*world), mask.region_transform)
                        .map(|v| v * scale as f64);
                let region = geometry_mask(
                    &region,
                    FillRule::Nonzero,
                    transform,
                    width,
                    height,
                    self.antialias,
                )?;
                rgba.as_chunks::<4>()
                    .0
                    .iter()
                    .zip(region.data())
                    .map(|(p, &c)| mask.scalar(p) * c as f64 / 255.0)
                    .collect()
            } else {
                vec![0.0; count as usize]
            };
            values.insert(id.clone(), coverage);
        }

        if let Some(control) = control {
            control.check()?;
        }
        Ok(values)
    }
}
pub fn preview(document: &Document, scale: u32) -> Result<Value, Error> {
    preview_with_assets(document, scale, None)
}
pub fn preview_with_assets(
    document: &Document,
    scale: u32,
    root: Option<&Path>,
) -> Result<Value, Error> {
    preview_with_resources(document, scale, root, None)
}
pub fn preview_with_resources(
    document: &Document,
    scale: u32,
    root: Option<&Path>,
    font_root: Option<&Path>,
) -> Result<Value, Error> {
    preview_with_options(document, scale, root, font_root, None)
}
pub fn preview_with_options(
    document: &Document,
    scale: u32,
    root: Option<&Path>,
    font_root: Option<&Path>,
    options: Option<&crate::render_quality::Options>,
) -> Result<Value, Error> {
    preview_controlled(
        document,
        scale,
        root,
        font_root,
        options,
        &crate::control::Control::default(),
    )
}
pub fn preview_controlled(
    document: &Document,
    scale: u32,
    root: Option<&Path>,
    font_root: Option<&Path>,
    options: Option<&crate::render_quality::Options>,
    control: &crate::control::Control,
) -> Result<Value, Error> {
    let p = rasterize_controlled(document, scale, root, font_root, options, control)?;
    let mut artifact = json!({"width":p.width,"height":p.height,"color_space":"srgb","alpha":"straight","encoding":"rgba8_hex","data":hex(&p.rgba)});
    if options.is_some() {
        artifact["render_settings"] =
            crate::render_quality::Plan::for_document(document, scale, options)?.receipt();
    }
    crate::swatches::annotate(document, &mut artifact)?;
    crate::samples::annotate(document, &mut artifact, crate::samples::Depth::U8);
    Ok(artifact)
}
pub fn png(document: &Document, scale: u32) -> Result<Value, Error> {
    png_with_assets(document, scale, None)
}
pub fn png_with_assets(
    document: &Document,
    scale: u32,
    root: Option<&Path>,
) -> Result<Value, Error> {
    png_with_resources(document, scale, root, None)
}
pub fn png_with_resources(
    document: &Document,
    scale: u32,
    root: Option<&Path>,
    font_root: Option<&Path>,
) -> Result<Value, Error> {
    png_with_options(document, scale, root, font_root, None)
}
pub fn png_with_options(
    document: &Document,
    scale: u32,
    root: Option<&Path>,
    font_root: Option<&Path>,
    options: Option<&crate::render_quality::Options>,
) -> Result<Value, Error> {
    png_controlled(
        document,
        scale,
        root,
        font_root,
        options,
        &crate::control::Control::default(),
    )
}
pub fn png_controlled(
    document: &Document,
    scale: u32,
    root: Option<&Path>,
    font_root: Option<&Path>,
    options: Option<&crate::render_quality::Options>,
    control: &crate::control::Control,
) -> Result<Value, Error> {
    let p = rasterize_controlled(document, scale, root, font_root, options, control)?;
    let mut artifact = png_pixels(document, p, scale)?;
    if options.is_some() {
        artifact["render_settings"] =
            crate::render_quality::Plan::for_document(document, scale, options)?.receipt();
    }
    Ok(artifact)
}
/// Encode a completed working-space view with the ordinary PNG color contract.
pub(crate) fn png_pixels(
    document: &Document,
    mut p: Rasterized,
    scale: u32,
) -> Result<Value, Error> {
    let profile = crate::profiles::output(document, &mut p.rgba)?;
    let bytes = encode_png_with_profile(
        p.width,
        p.height,
        &p.rgba,
        document.resolution_ppi * scale as f64,
        profile.as_ref().map(|(bytes, _)| bytes.as_slice()),
    )?;
    let mut artifact = json!({"media_type":"image/png","encoding":"base64","width":p.width,"height":p.height,"data":STANDARD.encode(bytes)});
    if let Some((_, summary)) = profile {
        artifact["color_profile"] = summary;
        artifact["color_space"] = json!("icc_rgb");
        artifact["losses"] = json!([
            "RGB8 conversion uses relative colorimetric intent without black-point compensation; out-of-gamut colors clip and quantization is not reversible. Alpha is retained unchanged. The exact destination profile is embedded."
        ]);
    }
    crate::swatches::annotate(document, &mut artifact)?;
    crate::samples::annotate(document, &mut artifact, crate::samples::Depth::U8);
    Ok(artifact)
}
pub(crate) fn encode_png(width: u32, height: u32, rgba: &[u8], ppi: f64) -> Result<Vec<u8>, Error> {
    encode_png_with_profile(width, height, rgba, ppi, None)
}
pub(crate) fn encode_png_with_profile(
    width: u32,
    height: u32,
    rgba: &[u8],
    ppi: f64,
    profile: Option<&[u8]>,
) -> Result<Vec<u8>, Error> {
    let mut bytes = Vec::new();
    {
        let mut encoder = if let Some(profile) = profile {
            let mut info = png::Info::with_size(width, height);
            info.icc_profile = Some(std::borrow::Cow::Borrowed(profile));
            png::Encoder::with_info(&mut bytes, info)
                .map_err(|_| Error::new("EXPORT_ERROR", "Unable to encode PNG color profile"))?
        } else {
            png::Encoder::new(&mut bytes, width, height)
        };
        encoder.set_color(png::ColorType::Rgba);
        encoder.set_depth(png::BitDepth::Eight);
        if profile.is_none() {
            encoder.set_source_srgb(png::SrgbRenderingIntent::Perceptual);
        }
        let ppm = (ppi / 0.0254).round() as u32;
        encoder.set_pixel_dims(Some(png::PixelDimensions {
            xppu: ppm,
            yppu: ppm,
            unit: png::Unit::Meter,
        }));
        let mut writer = encoder
            .write_header()
            .map_err(|_| Error::new("EXPORT_ERROR", "Unable to encode PNG header"))?;
        writer
            .write_image_data(rgba)
            .map_err(|_| Error::new("EXPORT_ERROR", "Unable to encode PNG pixels"))?;
    }
    Ok(bytes)
}
pub fn svg(document: &Document) -> Result<Value, Error> {
    crate::svg::export(document)
}
