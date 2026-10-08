//! Original PDF 1.7 appearance delivery using paths, transparency groups and images.
//! Snapshots remain the editable source; no external application or converter is used.
use crate::{
    Error, ExportFormat, assets, boards, geometry, metadata, model::*, scene, sessions::Resources,
};
use base64::{Engine, engine::general_purpose::STANDARD};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};

mod combined;
mod inks;
mod marks;
mod prepress;
mod print;
mod recipe;
pub use marks::Marks;
pub use prepress::{PrepressOptions, SpotFallback};
pub use print::PrintOptions;
pub use recipe::InkOptions;

pub const MAX_COMMANDS: usize = 262_144;
pub const MAX_OBJECTS: usize = 32_768;
pub const MAX_IMAGE_PIXELS: u64 = 4_194_304;

#[derive(Clone, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(default, deny_unknown_fields)]
pub struct Options {
    pub artboards: Option<boards::Selection>,
    pub include_bleed: bool,
    pub color: ColorDelivery,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub print: Option<PrintOptions>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub ink_recipe: Option<InkOptions>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub prepress: Option<PrepressOptions>,
}

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ColorDelivery {
    #[default]
    Display,
    NativeInks,
}

fn unsupported(message: &str) -> Error {
    Error::new("UNSUPPORTED", message)
}

// PDF numbers have no exponent notation. Rust's f64 Display uses positional,
// shortest round-trip decimal notation, including subnormal values.
fn number(value: f64) -> Result<String, Error> {
    if !value.is_finite() {
        return Err(limit("Nonfinite PDF coordinate"));
    }
    Ok(if value == 0.0 {
        "0".into()
    } else {
        value.to_string()
    })
}
fn numbers(values: &[f64]) -> Result<String, Error> {
    Ok(values
        .iter()
        .map(|&v| number(v))
        .collect::<Result<Vec<_>, _>>()?
        .join(" "))
}
fn xml(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
}

#[derive(Default)]
struct Writer {
    control: crate::control::Control,
    objects: Vec<Vec<u8>>,
    bytes: usize,
    commands: usize,
    pixels: u64,
    native_inks: bool,
    swatches: BTreeMap<String, crate::swatches::Swatch>,
    ink_spaces: BTreeMap<String, usize>,
    device_profiles: BTreeMap<String, usize>,
    blend_space: Option<String>,
    default_rgb: Option<usize>,
    explicit_black_point: bool,
}
impl Writer {
    fn group_space(&self) -> &str {
        self.blend_space.as_deref().unwrap_or(if self.native_inks {
            "/DeviceCMYK"
        } else {
            "/DeviceRGB"
        })
    }
    fn add(&mut self, data: impl Into<Vec<u8>>) -> Result<usize, Error> {
        self.control.check()?;
        let data = data.into();
        self.bytes += data.len() + 64;
        if self.bytes > crate::publish::MAX_OUTPUT_BYTES || self.objects.len() >= MAX_OBJECTS {
            return Err(limit("PDF exceeds its 32 MiB or object budget"));
        }
        self.objects.push(data);
        Ok(self.objects.len())
    }
    fn replace(&mut self, id: usize, data: String) -> Result<(), Error> {
        self.bytes += data.len();
        if self.bytes > crate::publish::MAX_OUTPUT_BYTES {
            return Err(limit("PDF exceeds 32 MiB"));
        }
        self.objects[id - 1] = data.into_bytes();
        Ok(())
    }
    fn stream(&mut self, entries: &str, data: &[u8]) -> Result<usize, Error> {
        if data.len() > crate::publish::MAX_OUTPUT_BYTES {
            return Err(limit("PDF stream exceeds 32 MiB"));
        }
        let mut bytes = format!("<< {entries} /Length {} >>\nstream\n", data.len()).into_bytes();
        bytes.extend_from_slice(data);
        bytes.extend_from_slice(b"\nendstream");
        self.add(bytes)
    }
    fn path(&mut self, output: &mut String, shape: &Geometry, matrix: Matrix) -> Result<(), Error> {
        let Geometry::Path { commands } = crate::primitives::expand(shape)? else {
            unreachable!()
        };
        self.commands += commands.len();
        if self.commands > MAX_COMMANDS {
            return Err(limit("PDF path commands exceed 262144"));
        }
        for command in commands {
            self.control.check()?;
            let (points, op) = match command {
                PathCommand::Move { to } => (vec![to], "m"),
                PathCommand::Line { to } => (vec![to], "l"),
                PathCommand::Cubic {
                    control1,
                    control2,
                    to,
                } => (vec![control1, control2, to], "c"),
                PathCommand::Close {} => (vec![], "h"),
            };
            for point in points {
                output.push_str(&numbers(&geometry::map(matrix, point))?);
                output.push(' ');
            }
            output.push_str(op);
            output.push('\n');
            if self.bytes + output.len() > crate::publish::MAX_OUTPUT_BYTES {
                return Err(limit("PDF path data exceeds 32 MiB"));
            }
        }
        Ok(())
    }
    fn finish(self, root: usize, info: usize) -> Result<Vec<u8>, Error> {
        let mut bytes = if self.explicit_black_point {
            b"%PDF-2.0\n%\xe2\xe3\xcf\xd3\n".to_vec()
        } else {
            b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n".to_vec()
        };
        let mut offsets = vec![0];
        self.control.check()?;
        for (i, object) in self.objects.iter().enumerate() {
            self.control.check()?;
            offsets.push(bytes.len());
            bytes.extend_from_slice(format!("{} 0 obj\n", i + 1).as_bytes());
            bytes.extend_from_slice(object);
            bytes.extend_from_slice(b"\nendobj\n");
        }
        let start = bytes.len();
        bytes.extend_from_slice(
            format!("xref\n0 {}\n0000000000 65535 f \n", offsets.len()).as_bytes(),
        );
        for offset in &offsets[1..] {
            bytes.extend_from_slice(format!("{offset:010} 00000 n \n").as_bytes());
        }
        bytes.extend_from_slice(format!("trailer\n<< /Size {} /Root {root} 0 R /Info {info} 0 R >>\nstartxref\n{start}\n%%EOF\n", offsets.len()).as_bytes());
        if bytes.len() > crate::publish::MAX_OUTPUT_BYTES {
            return Err(limit("PDF exceeds 32 MiB"));
        }
        Ok(bytes)
    }
}

#[derive(Default)]
struct Stream {
    content: String,
    resources: BTreeMap<&'static str, BTreeSet<usize>>,
    default_rgb: Option<usize>,
}
impl Stream {
    fn use_resource(&mut self, category: &'static str, id: usize, op: &str) {
        self.resources.entry(category).or_default().insert(id);
        self.content.push_str(&format!("/R{id} {op}\n"));
    }
    fn dictionary(&self) -> String {
        let mut entries: BTreeMap<_, Vec<_>> = self
            .resources
            .iter()
            .map(|(kind, ids)| {
                (
                    *kind,
                    ids.iter().map(|id| format!("/R{id} {id} 0 R")).collect(),
                )
            })
            .collect();
        if let Some(id) = self.default_rgb {
            entries
                .entry("ColorSpace")
                .or_default()
                .push(format!("/DefaultRGB {id} 0 R"));
        }
        let entries = entries
            .iter()
            .map(|(kind, values)| format!("/{kind} << {} >>", values.join(" ")))
            .collect::<Vec<_>>()
            .join(" ");
        format!("<< {entries} >>")
    }
}
fn alpha(writer: &mut Writer, stream: &mut Stream, opacity: f64) -> Result<(), Error> {
    let id = writer.add(format!(
        "<< /Type /ExtGState /ca {} /CA {} /BM /Normal /SMask /None /OP false /op false /OPM 0 >>",
        number(opacity)?,
        number(opacity)?
    ))?;
    stream.use_resource("ExtGState", id, "gs");
    Ok(())
}
fn clip(
    writer: &mut Writer,
    stream: &mut Stream,
    shape: &Geometry,
    matrix: Matrix,
    rule: FillRule,
) -> Result<(), Error> {
    writer.path(&mut stream.content, shape, matrix)?;
    stream.content.push_str(if rule == FillRule::EvenOdd {
        "W* n\n"
    } else {
        "W n\n"
    });
    Ok(())
}

fn gradient(writer: &mut Writer, field: &crate::paint::Field) -> Result<(usize, u8), Error> {
    use crate::paint::{Field, Interpolation, Spread};
    let (kind, coordinates, stops, spread, space) = match field {
        Field::Linear {
            start,
            end,
            stops,
            spread,
            space,
            ..
        } => (
            2,
            vec![
                start[0],
                start[1],
                2.0 * end[0] - start[0],
                2.0 * end[1] - start[1],
            ],
            stops,
            spread,
            space,
        ),
        Field::Radial {
            center,
            radius,
            stops,
            spread,
            space,
            ..
        } => (
            3,
            vec![
                center[0],
                center[1],
                0.0,
                center[0],
                center[1],
                2.0 * radius,
            ],
            stops,
            spread,
            space,
        ),
        _ => {
            return Err(unsupported(
                "PDF currently supports solid, axial and radial paints",
            ));
        }
    };
    if *spread != Spread::Pad
        || *space != Interpolation::Srgb
        || stops.iter().any(|s| s.color[3] != stops[0].color[3])
    {
        return Err(unsupported(
            "PDF gradients require pad spread, encoded-sRGB interpolation and constant alpha",
        ));
    }
    // Extend endpoint colors and retain duplicated-offset discontinuities by
    // selecting the last stop to the right and first stop to the left.
    let mut positions = vec![0.0];
    for stop in stops {
        if stop.offset > *positions.last().unwrap() {
            positions.push(stop.offset);
        }
    }
    if *positions.last().unwrap() < 1.0 {
        positions.push(1.0);
    }
    // Extend the function beyond the final stop so its right-continuous value
    // supplies padding even when offset 1 is a discontinuity. Doubling both the
    // shading extent and domain preserves the original gradient slope.
    positions.push(2.0);
    let mut functions = Vec::new();
    for interval in positions.windows(2) {
        let lo = stops
            .iter()
            .rev()
            .find(|s| s.offset <= interval[0])
            .unwrap_or(&stops[0]);
        let hi = stops
            .iter()
            .find(|s| s.offset >= interval[1])
            .unwrap_or(stops.last().unwrap());
        let c0 = numbers(
            &lo.color[..3]
                .iter()
                .map(|&v| v as f64 / 255.0)
                .collect::<Vec<_>>(),
        )?;
        let c1 = numbers(
            &hi.color[..3]
                .iter()
                .map(|&v| v as f64 / 255.0)
                .collect::<Vec<_>>(),
        )?;
        let f = writer.add(format!(
            "<< /FunctionType 2 /Domain [0 1] /C0 [{c0}] /C1 [{c1}] /N 1 >>"
        ))?;
        functions.push(format!("{f} 0 R"));
    }
    let bounds = numbers(&positions[1..positions.len() - 1])?;
    let function = writer.add(format!(
        "<< /FunctionType 3 /Domain [0 2] /Functions [{}] /Bounds [{bounds}] /Encode [{}] >>",
        functions.join(" "),
        vec!["0 1"; functions.len()].join(" ")
    ))?;
    let shading = writer.add(format!("<< /ShadingType {kind} /ColorSpace /DeviceRGB /Domain [0 2] /Coords [{}] /Function {function} 0 R /Extend [true true] >>", numbers(&coordinates)?))?;
    Ok((shading, stops[0].color[3]))
}

fn paint(
    writer: &mut Writer,
    stream: &mut Stream,
    shape: &Geometry,
    shape_matrix: Matrix,
    paint: &Paint,
    paint_matrix: Matrix,
    rule: FillRule,
) -> Result<(), Error> {
    stream.content.push_str("q\n");
    match paint {
        Paint::Solid(color) => {
            alpha(writer, stream, color[3] as f64 / 255.0)?;
            stream.content.push_str(&format!(
                "{} rg\n",
                numbers(
                    &color[..3]
                        .iter()
                        .map(|&v| v as f64 / 255.0)
                        .collect::<Vec<_>>()
                )?
            ));
            writer.path(&mut stream.content, shape, shape_matrix)?;
            stream.content.push_str(if rule == FillRule::EvenOdd {
                "f*\n"
            } else {
                "f\n"
            });
        }
        Paint::Field(field) => {
            let (shading, opacity) = gradient(writer, field)?;
            clip(writer, stream, shape, shape_matrix, rule)?;
            alpha(writer, stream, opacity as f64 / 255.0)?;
            stream.content.push_str(&format!(
                "{} cm\n",
                numbers(&geometry::multiply(paint_matrix, field.transform()))?
            ));
            stream.use_resource("Shading", shading, "sh");
        }
        Paint::Precise(color) => {
            alpha(writer, stream, color.rgba[3])?;
            stream
                .content
                .push_str(&format!("{} rg\n", numbers(&color.rgba[..3])?));
            writer.path(&mut stream.content, shape, shape_matrix)?;
            stream.content.push_str(if rule == FillRule::EvenOdd {
                "f*\n"
            } else {
                "f\n"
            });
        }
        Paint::Named(reference) => {
            inks::paint(writer, stream, reference)?;
            writer.path(&mut stream.content, shape, shape_matrix)?;
            stream.content.push_str(if rule == FillRule::EvenOdd {
                "f*\n"
            } else {
                "f\n"
            });
        }
    }
    stream.content.push_str("Q\n");
    Ok(())
}

fn image(
    writer: &mut Writer,
    stream: &mut Stream,
    dimensions: [u32; 2],
    rgba: &[u8],
    size: [f64; 2],
    world: Matrix,
) -> Result<(), Error> {
    let [width, height] = dimensions;
    writer.pixels += width as u64 * height as u64;
    if writer.pixels > MAX_IMAGE_PIXELS {
        return Err(limit("PDF embedded image copies exceed 4194304 pixels"));
    }
    let mut rgb = Vec::with_capacity(rgba.len() / 4 * 3);
    let mut gray = Vec::with_capacity(rgba.len() / 4);
    for pixel in rgba.as_chunks::<4>().0 {
        rgb.extend_from_slice(&pixel[..3]);
        gray.push(pixel[3]);
    }
    let mask = if gray.iter().any(|&a| a != 255) {
        let id = writer.stream(&format!("/Type /XObject /Subtype /Image /Width {width} /Height {height} /ColorSpace /DeviceGray /BitsPerComponent 8 /Interpolate false"), &gray)?;
        format!("/SMask {id} 0 R")
    } else {
        String::new()
    };
    let id = writer.stream(&format!("/Type /XObject /Subtype /Image /Width {width} /Height {height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Interpolate false {mask}"), &rgb)?;
    stream.content.push_str("q\n");
    // PDF images map the first sample row to the top of their unit square.
    let matrix = geometry::multiply(world, [size[0], 0.0, 0.0, -size[1], 0.0, size[1]]);
    stream
        .content
        .push_str(&format!("{} cm\n", numbers(&matrix)?));
    stream.use_resource("XObject", id, "Do");
    stream.content.push_str("Q\n");
    Ok(())
}

fn preflight(document: &Document) -> Result<(), Error> {
    let mut stroke_commands = 0;
    let mut pixels = 0;
    for (i, item) in document.items.iter().enumerate() {
        if item.blend != BlendMode::Normal
            || item.content.is_knockout()
            || !item.effects.is_empty()
            || !item.filters.is_empty()
            || !item.coverage.is_smooth()
            || item.pixel_warp.is_some()
            || item.clip_to.is_some()
            || item.mask.as_ref().is_some_and(|m| m.enabled)
            || item.artwork_mask.as_ref().is_some_and(|m| m.enabled)
        {
            return Err(unsupported("PDF does not preserve non-normal blends, knockout, effects, filters, dissolve, pixel warps, layer clipping or active opacity/artwork masks").at_item(&item.id));
        }
        match &item.content {
            Content::Object { .. } => return Err(unsupported("PDF does not retain editable object sources; deliver an explicit image or snapshot").at_item(&item.id)),
            Content::Raw { .. } | Content::Samples { .. } => return Err(unsupported("PDF delivery does not yet preserve retained sample-grid depths; use TIFF or a snapshot").at_item(&item.id)),
            Content::Raster { sampling, .. } | Content::Image { sampling, .. } => {
                if *sampling != assets::Sampling::Nearest {
                    return Err(unsupported("PDF image delivery requires nearest sampling; consumer interpolation cannot promise an exact reconstruction kernel").at_item(&item.id));
                }
                if let Content::Raster { width, height, .. } = &item.content {
                    pixels += *width as u64 * *height as u64;
                }
                if let Content::Image { asset_id, crop, .. } = &item.content {
                    let asset = &document.assets[asset_id];
                    let crop = assets::crop(asset.width, asset.height, *crop)?;
                    pixels += crop.width as u64 * crop.height as u64;
                }
            }
            Content::Vector {
                stroke: Some(_), ..
            } => {
                stroke_commands += crate::strokes::generated_item_work(
                    item,
                    scene::world_transform(document, i)?,
                )?;
            }
            Content::Fill { dither, .. } if *dither != crate::paint::Dither::None => {
                return Err(
                    unsupported("PDF does not preserve ordered pixel dither").at_item(&item.id)
                );
            }
            Content::Adjustment { .. } => {
                return Err(
                    unsupported("PDF does not preserve adjustment layers").at_item(&item.id)
                );
            }
            _ => {}
        }
    }
    if stroke_commands > MAX_COMMANDS as u64 || pixels > MAX_IMAGE_PIXELS {
        return Err(limit(
            "PDF scene exceeds generated-path or image-copy budget",
        ));
    }
    Ok(())
}

fn items(
    writer: &mut Writer,
    output: &mut Stream,
    document: &Document,
    parent: Option<&str>,
    pixels: &BTreeMap<String, assets::Pixels>,
    layouts: &BTreeMap<String, crate::text::Layout>,
) -> Result<(), Error> {
    for i in scene::children(document, parent) {
        writer.control.check()?;
        let item = &document.items[i];
        if !item.visible
            || matches!(
                item.content,
                Content::WorkPath { .. } | Content::MaskSource {} | Content::ComponentSource { .. }
            )
        {
            continue;
        }
        let world = scene::world_transform(document, i)?;
        let mut stream = Stream {
            default_rgb: writer.default_rgb,
            ..Stream::default()
        };
        if let Some(c) = item.clip.as_ref().filter(|c| c.enabled) {
            clip(
                writer,
                &mut stream,
                &c.geometry,
                geometry::multiply(world, c.transform),
                c.fill_rule,
            )?;
        }
        match &item.content {
            Content::Text { .. } | Content::StoryFrame { .. } => {
                if let Some(geometry) =
                    crate::text::clip_geometry(&item.content, &layouts[&item.id])
                {
                    clip(writer, &mut stream, &geometry, world, FillRule::Nonzero)?;
                }
                for path in &layouts[&item.id].paths {
                    paint(
                        writer,
                        &mut stream,
                        &path.geometry,
                        world,
                        &path.fill,
                        world,
                        FillRule::Nonzero,
                    )?;
                }
            }
            Content::Group { .. } => items(
                writer,
                &mut stream,
                document,
                Some(&item.id),
                pixels,
                layouts,
            )?,
            Content::Frame { frame } => {
                clip(
                    writer,
                    &mut stream,
                    &frame.geometry(),
                    world,
                    FillRule::Nonzero,
                )?;
                if let Some(color) = frame.background {
                    paint(
                        writer,
                        &mut stream,
                        &frame.geometry(),
                        world,
                        &Paint::Solid(color),
                        world,
                        FillRule::Nonzero,
                    )?;
                }
                items(
                    writer,
                    &mut stream,
                    document,
                    Some(&item.id),
                    pixels,
                    layouts,
                )?;
            }
            Content::Vector {
                geometry,
                fill,
                stroke,
                fill_rule,
            } => {
                if let Some(fill) = fill {
                    paint(
                        writer,
                        &mut stream,
                        geometry,
                        world,
                        fill,
                        world,
                        *fill_rule,
                    )?;
                }
                if let Some(stroke) = stroke
                    && let Some(outline) = crate::strokes::generate_placed(geometry, stroke, world)?
                {
                    paint(
                        writer,
                        &mut stream,
                        &outline,
                        stroke.scaling.matrix(world),
                        &stroke.color,
                        world,
                        FillRule::Nonzero,
                    )?;
                }
            }
            Content::Image {
                asset_id,
                width,
                height,
                crop,
                ..
            } => {
                let pixels = &pixels[asset_id];
                let crop = assets::crop(pixels.width, pixels.height, *crop)?;
                image(
                    writer,
                    &mut stream,
                    [crop.width, crop.height],
                    &pixels.cropped(crop),
                    [*width, *height],
                    world,
                )?;
            }
            Content::Raster {
                width,
                height,
                rgba_hex,
                ..
            } => image(
                writer,
                &mut stream,
                [*width, *height],
                &crate::render::unhex(rgba_hex),
                [*width as f64, *height as f64],
                world,
            )?,
            Content::Fill {
                width,
                height,
                paint: fill,
                ..
            } => paint(
                writer,
                &mut stream,
                &Geometry::Rect {
                    x: 0.0,
                    y: 0.0,
                    width: *width as f64,
                    height: *height as f64,
                },
                world,
                fill,
                world,
                FillRule::Nonzero,
            )?,
            _ => {
                return Err(
                    unsupported("PDF encountered unevaluated or unsupported content")
                        .at_item(&item.id),
                );
            }
        }
        let isolated = !matches!(
            item.content,
            Content::Group {
                isolated: false,
                ..
            }
        );
        let group = if writer.native_inks && !item.content.is_container() {
            "/I false".into()
        } else if isolated {
            format!("/I true /CS {}", writer.group_space())
        } else {
            "/I false".into()
        };
        // A unit-opacity leaf must paint directly into its ink backdrop. An
        // artificial isolated leaf group would erase overprint interaction.
        // Real containers retain their declared isolation; item opacity still
        // applies once to a composed fill/stroke through a transparency group.
        let group = if writer.native_inks
            && !item.content.is_container()
            && item.opacity * item.fill_opacity == 1.0
        {
            String::new()
        } else {
            format!("/Group << /S /Transparency {group} /K false >>")
        };
        let id = writer.stream(
            &format!(
                "/Type /XObject /Subtype /Form /FormType 1 /BBox [0 0 {} {}] /Resources {} {group}",
                document.width,
                document.height,
                stream.dictionary()
            ),
            stream.content.as_bytes(),
        )?;
        output.content.push_str("q\n");
        alpha(writer, output, item.opacity * item.fill_opacity)?;
        output.use_resource("XObject", id, "Do");
        output.content.push_str("Q\n");
    }
    Ok(())
}

pub fn export(
    document: &Document,
    resources: &Resources,
    options: &Options,
    policy: Option<metadata::Policy>,
) -> Result<Value, Error> {
    export_controlled(document, resources, options, policy, None)
}
pub fn export_controlled(
    document: &Document,
    resources: &Resources,
    options: &Options,
    policy: Option<metadata::Policy>,
    control: Option<&crate::control::Control>,
) -> Result<Value, Error> {
    validate_controlled(
        document,
        control.unwrap_or(&crate::control::Control::default()),
    )?;
    if [
        options.print.is_some(),
        options.ink_recipe.is_some(),
        options.prepress.is_some(),
    ]
    .into_iter()
    .filter(|&b| b)
    .count()
        > 1
    {
        return Err(Error::new(
            "INVALID_REQUEST",
            "Choose one PDF preparation mode: print, ink_recipe or prepress",
        ));
    }
    if let Some(prepress) = &options.prepress {
        return prepress::export(
            document,
            resources,
            options,
            prepress,
            policy,
            control.unwrap_or(&crate::control::Control::default()),
        );
    }
    if let Some(ink) = &options.ink_recipe {
        return recipe::export(
            document,
            options,
            ink,
            policy,
            control.unwrap_or(&crate::control::Control::default()),
        );
    }
    if let Some(print) = &options.print {
        crate::vector_canvas::reject_rgb_page(document)?;
        return print::export(document, resources, options, print, policy, control);
    }
    crate::hdr::reject_page(document)?;
    let source = document;
    let native_inks = options.color == ColorDelivery::NativeInks;
    if !native_inks || document.output_profile.is_some() {
        crate::vector_canvas::reject_rgb_page(document)?;
    }
    let colors = if native_inks {
        None
    } else {
        crate::swatches::vector_export(document)?;
        crate::swatches::evaluate(document)?
    };
    let document = colors.as_ref().unwrap_or(document);
    if options.include_bleed && options.artboards.is_none() {
        return Err(Error::new(
            "INVALID_REQUEST",
            "PDF bleed requires an artboard selection",
        ));
    }
    let instances = crate::instances::evaluate(document)?;
    let document = instances.as_ref().unwrap_or(document);
    let appearance = crate::appearance::evaluate(document)?;
    let document = appearance.as_ref().unwrap_or(document);
    let volume = crate::volumes::evaluate(document)?;
    let document = volume.as_ref().unwrap_or(document);
    let warps = crate::warps::evaluate(document)?;
    let document = warps.as_ref().unwrap_or(document);
    let repeats = crate::repeats::evaluate(document)?;
    let document = repeats.as_ref().unwrap_or(document);
    let interpolation = crate::interpolation::evaluate(document)?;
    let document = interpolation.as_ref().unwrap_or(document);
    let selection = options
        .artboards
        .as_ref()
        .map(|s| boards::select(document, s))
        .transpose()?;
    let pages: Vec<Option<usize>> = selection
        .map(|s| s.into_iter().map(Some).collect())
        .unwrap_or_else(|| vec![None]);
    let mut writer = Writer {
        control: control.cloned().unwrap_or_default(),
        native_inks,
        swatches: document.swatches.clone(),
        ..Writer::default()
    };
    let color_profile = if let Some(profile) = &document.output_profile {
        let encoding = crate::profiles::device::Endpoint {
            space: crate::profiles::device::Space::Rgb,
            profile: Some(profile.clone()),
            untagged: crate::profiles::device::Untagged::Reject,
        };
        // A blending space requires conversion both to and from its PCS.
        crate::profiles::device::Connection::new(
            &encoding,
            &encoding,
            crate::profiles::Intent::RelativeColorimetric,
        )?;
        writer.blend_space = Some(inks::device_space(&mut writer, &encoding)?);
        let source_space = inks::device_space(&mut writer, &crate::swatches::device::display())?;
        writer.default_rgb = Some(writer.add(source_space)?);
        let bytes = encoding.bytes()?;
        Some(
            json!({"icc_sha256":assets::sha256(&bytes),"icc_bytes":bytes.len(),"profile_embedded":true,"role":"ICCBased_RGB_page_and_isolated_group_blending","untagged_RGB":"explicit_builtin_srgb_DefaultRGB_in_every_resource_scope","rendering_intent":"retained_device_paint_intent;otherwise_relative_colorimetric","source_components_changed":false}),
        )
    } else {
        None
    };
    let catalog = writer.add(Vec::new())?;
    let tree = writer.add(Vec::new())?;
    let mut references = Vec::new();
    let mut receipts = Vec::new();
    let mut envelopes = Vec::new();
    let mut glyphs = 0;
    let mut ink_pages = Vec::new();
    for selection in pages {
        let scoped = selection
            .map(|i| boards::standalone(document, &document.items[i].id, options.include_bleed))
            .transpose()?;
        let page = scoped.as_ref().unwrap_or(document);
        let packet = metadata::packet(page, ExportFormat::Pdf, 1, policy.unwrap_or_default())?;
        let logical = crate::vector_canvas::logical_size(page);
        let viewport = page
            .vector_canvas
            .map(|c| crate::vector_canvas::translated(page, c.origin_px.map(|v| -v)))
            .transpose()?;
        let page = viewport.as_ref().unwrap_or(page);
        preflight(page)?;
        if native_inks {
            ink_pages.push(crate::swatches::ink_diagnostics(page)?);
        }
        let fonts = crate::fonts::resolve(page, resources.font_root.as_deref())?;
        let layouts = crate::text::prepare(page, &fonts)?;
        glyphs += layouts.values().map(|l| l.glyphs.len()).sum::<usize>();
        // Glyph paths are an evaluated delivery surface, not editable vector
        // items inserted into a raster snapshot. Keep the source scene intact.
        for (id, layout) in &layouts {
            let world = scene::world_transform(page, scene::index(page, id)?)?;
            for path in &layout.paths {
                crate::model::validate_world_geometry(&path.geometry, world)?;
            }
        }
        let pixels = assets::resolve(page, resources.asset_root.as_deref())?;
        let ppi = page.resolution_ppi;
        let physical = 72.0 / ppi;
        let user_unit = (logical[0].max(logical[1]) * physical / 14400.0)
            .ceil()
            .max(1.0);
        if user_unit > 75000.0 {
            return Err(limit("PDF page exceeds the supported physical size"));
        }
        let factor = physical / user_unit;
        let width = logical[0] * factor;
        let height = logical[1] * factor;
        let mut stream = Stream {
            default_rgb: writer.default_rgb,
            content: format!(
                "q\n{} 0 0 {} 0 {} cm\n",
                number(factor)?,
                number(-factor)?,
                number(height)?
            ),
            ..Stream::default()
        };
        if writer.blend_space.is_some() {
            let state = writer
                .add("<< /Type /ExtGState /RI /RelativeColorimetric /UseBlackPtComp /OFF >>")?;
            stream.use_resource("ExtGState", state, "gs");
        }
        if let Some([r, g, b]) = crate::backgrounds::visible_matte(page) {
            paint(
                &mut writer,
                &mut stream,
                &Geometry::Rect {
                    x: 0.0,
                    y: 0.0,
                    width: page.width as f64,
                    height: page.height as f64,
                },
                identity(),
                &Paint::Solid([r, g, b, 255]),
                identity(),
                FillRule::Nonzero,
            )?;
        }
        items(&mut writer, &mut stream, page, None, &pixels, &layouts)?;
        stream.content.push_str("Q\n");
        let content = writer.stream("", stream.content.as_bytes())?;
        let bleed = if options.include_bleed {
            selection
                .map(|i| {
                    let Content::Frame { frame } = &document.items[i].content else {
                        unreachable!()
                    };
                    frame.bleed
                })
                .unwrap_or_default()
        } else {
            boards::Insets::default()
        };
        let media = [0.0, 0.0, width, height];
        let trim = [
            bleed.left as f64 * factor,
            bleed.bottom as f64 * factor,
            width - bleed.right as f64 * factor,
            height - bleed.top as f64 * factor,
        ];
        let group_space = writer.group_space();
        let id=writer.add(format!("<< /Type /Page /Parent {tree} 0 R /MediaBox [{}] /CropBox [{}] /BleedBox [{}] /TrimBox [{}] /UserUnit {} /Resources {} /Contents {content} 0 R /Group << /Type /Group /S /Transparency /CS {group_space} /I true /K false >> >>",numbers(&media)?,numbers(&media)?,numbers(&media)?,numbers(&trim)?,number(user_unit)?,stream.dictionary()))?;
        references.push(format!("{id} 0 R"));
        let artboard_id = selection.map(|i| &document.items[i].id);
        receipts.push(json!({"index":receipts.len(),"artboard_id":artboard_id,"logical_size":logical,"physical_points":[logical[0]*physical,logical[1]*physical],"resolution_ppi":ppi,"media_box":media,"trim_box":trim,"user_unit":user_unit,"coordinates":"pdf_bottom_left_in_user_units"}));
        envelopes.push(json!({"artboard_id":artboard_id,"packet":packet.map(|s|serde_json::from_str::<Value>(&s).unwrap())}));
    }
    let packet = if envelopes.iter().any(|v| !v["packet"].is_null()) {
        Some(
            String::from_utf8(metadata::canonical(
                &json!({"schema":"inkbolt.pdf.metadata.v1","pages":envelopes}),
            ))
            .unwrap(),
        )
    } else {
        None
    };
    let meta = if let Some(packet) = &packet {
        let xmp = format!(
            "<rdf:RDF xmlns:rdf=\"http://www.w3.org/1999/02/22-rdf-syntax-ns#\"><rdf:Description rdf:about=\"\" xmlns:inkbolt=\"urn:inkbolt:pdf:metadata:1\"><inkbolt:packet>{}</inkbolt:packet></rdf:Description></rdf:RDF>",
            xml(packet)
        );
        let id = writer.stream("/Type /Metadata /Subtype /XML", xmp.as_bytes())?;
        format!("/Metadata {id} 0 R")
    } else {
        String::new()
    };
    writer.replace(
        tree,
        format!(
            "<< /Type /Pages /Count {} /Kids [{}] >>",
            references.len(),
            references.join(" ")
        ),
    )?;
    writer.replace(
        catalog,
        format!("<< /Type /Catalog /Pages {tree} 0 R {meta} >>"),
    )?;
    let info = writer.add("<< /Producer (Inkbolt) >>".to_string())?;
    let commands = writer.commands;
    let image_pixels = writer.pixels;
    let version = if writer.explicit_black_point {
        "2.0"
    } else {
        "1.7"
    };
    let bytes = writer.finish(catalog, info)?;
    let mut result = json!({"media_type":"application/pdf","encoding":"base64","data":STANDARD.encode(&bytes),"pages":receipts,"pdf":{"version":"1.7","include_bleed":options.include_bleed,"artboards":options.artboards,"path_commands":commands,"image_pixels":image_pixels,"text_glyphs":glyphs,"color":"DeviceRGB_encoded_working_samples_consumer_color_management","text":"vector_outlines","editable_source":"snapshot","deterministic":true},"losses":["Text is delivered as glyph outlines, without searchable text, embedded fonts or semantic tagging; retain the snapshot and pinned resources for editing.","Vector geometry remains paths. Ellipses use four cubic segments; complex strokes use the shared bounded outline evaluator.","DeviceRGB consumer color management, edge antialiasing and image sampling can differ from Inkbolt previews; this is not a print-profile or exact-pixel guarantee.","PDF does not carry the editable document model, guides, selections, channels or font controls. PDF reimport is not implemented."]});
    metadata::annotate(&mut result, packet.as_deref(), policy, false);
    result["pdf"]["version"] = json!(version);
    if version == "2.0" {
        result["pdf"]["black_point_compensation"] =
            json!("explicit_OFF_for_managed_paints_and_calibrated_page_sources");
        result["losses"].as_array_mut().unwrap().push(json!("Managed color uses PDF 2.0 UseBlackPtComp OFF to preserve the declared conversion policy. Older consumers may ignore this setting. Lookup interpolation and legacy v2 perceptual black normalization can differ across color engines."));
    }
    if volume.is_some() {
        result["losses"].as_array_mut().unwrap().push(json!("Dimensional artwork is delivered as projected painted vector faces. Retain the snapshot for editable profiles, extrusion, rotation, camera and material controls."));
    }
    if native_inks {
        result["pdf"]["color"] = json!(
            "native_named_inks;DeviceCMYK_blending;consumer_process_conversion_without_output_profile"
        );
        result["pdf"]["color_delivery"] = json!(options.color);
        result["losses"][2] = json!(
            "Native PDF color conversion, edge antialiasing and image sampling depend on the consumer; this is not an output-profile proof or exact-pixel guarantee."
        );
        result["swatches"] = json!({"native_ink_preservation":true,"ink_identity":"Inkbolt.<base_swatch_id>","editable_source":"snapshot","pages":ink_pages,"overprint":"explicit_OP_op_OPM;native_PDF_consumers_required","separations":"declared_spot_and_process_instructions;no_plate_raster_or_output_profile_proof"});
        result["losses"].as_array_mut().unwrap().push(json!("Native ink output retains spot identity, exact tints, CMYK/Lab declarations and overprint instructions. Display colors and unnamed RGB paints may require consumer conversion. This is not a profile-driven print proof or a plate-coverage report."));
    } else {
        crate::swatches::annotate(source, &mut result)?;
    }
    if let Some(profile) = color_profile {
        result["color_profile"] = profile;
        result["pdf"]["color"] =
            json!("calibrated_ICCBased_RGB_blending;retained_source_profiles_and_spot_identities");
        result["losses"][2] = json!(
            "The declared RGB profile calibrates page and isolated-group blending. Device RGB sources explicitly use sRGB; profiled paints retain their source profiles and intents. Consumer rounding, antialiasing and profile interpretation may differ; this is not a print proof or exact-pixel guarantee."
        );
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    #[test]
    fn decimal_numbers_roundtrip_without_pdf_forbidden_exponents() {
        for value in [
            f64::MIN_POSITIVE,
            f64::from_bits(1),
            1e-20,
            -1e20,
            f64::MAX,
            0.0,
            -0.0,
            0.1,
        ] {
            let text = super::number(value).unwrap();
            assert!(!text.contains(['e', 'E']));
            assert_eq!(text.parse::<f64>().unwrap(), value);
        }
        assert!(super::number(f64::NAN).is_err());
    }
}
