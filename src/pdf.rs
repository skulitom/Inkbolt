//! Original PDF appearance delivery using paths, transparency groups and images.
//! Snapshots remain the editable source; no external application or converter is used.
use crate::{
    Error, ExportFormat, assets, boards, geometry, metadata, model::*, scene, sessions::Resources,
};
use base64::{Engine, engine::general_purpose::STANDARD};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};

mod artwork;
mod combined;
mod inks;
mod marks;
mod opacity;
mod prepress;
mod print;
mod recipe;
pub use marks::Marks;
pub use prepress::{PrepressOptions, SpotFallback};
pub use print::PrintOptions;
pub use recipe::InkOptions;

pub use crate::limits::pdf::MAX_COMMANDS;
pub use crate::limits::pdf::MAX_IMAGE_PIXELS;
pub use crate::limits::pdf::MAX_OBJECTS;

#[derive(Clone, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(default, deny_unknown_fields)]
pub struct Options {
    pub artboards: Option<boards::Selection>,
    pub include_bleed: bool,
    pub color: ColorDelivery,
    /// Physical crop and registration marks for vector page delivery.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub marks: Option<Marks>,
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
    grid_mask_samples: u64,
    grid_masks: usize,
    artwork_alpha_masks: usize,
    artwork_luminance_masks: usize,
    native_inks: bool,
    swatches: BTreeMap<String, crate::swatches::Swatch>,
    ink_spaces: BTreeMap<String, usize>,
    page_has_spot_paint: bool,
    page_requires_backdrop: bool,
    page_bbox: String,
    gradient_opacity_masks: usize,
    page_uses_blends: bool,
    non_normal_modes: BTreeSet<&'static str>,
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
            return Err(limit(&format!(
                "PDF exceeds its {} MiB or object budget",
                crate::publish::MAX_OUTPUT_BYTES as f64 / 1_048_576.0
            )));
        }
        self.objects.push(data);
        Ok(self.objects.len())
    }
    fn replace(&mut self, id: usize, data: String) -> Result<(), Error> {
        self.bytes += data.len();
        if self.bytes > crate::publish::MAX_OUTPUT_BYTES {
            return Err(limit(&format!(
                "PDF exceeds {} MiB",
                crate::publish::MAX_OUTPUT_BYTES as f64 / 1_048_576.0
            )));
        }
        self.objects[id - 1] = data.into_bytes();
        Ok(())
    }
    fn stream(&mut self, entries: &str, data: &[u8]) -> Result<usize, Error> {
        if data.len() > crate::publish::MAX_OUTPUT_BYTES {
            return Err(limit(&format!(
                "PDF stream exceeds {} MiB",
                crate::publish::MAX_OUTPUT_BYTES as f64 / 1_048_576.0
            )));
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
            return Err(limit(&format!("PDF path commands exceed {MAX_COMMANDS}")));
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
                return Err(limit(&format!(
                    "PDF path data exceeds {} MiB",
                    crate::publish::MAX_OUTPUT_BYTES as f64 / 1_048_576.0
                )));
            }
        }
        Ok(())
    }
    fn corrected_blend_endpoints(&self) -> bool {
        self.non_normal_modes.contains("ColorDodge") || self.non_normal_modes.contains("ColorBurn")
    }
    fn version(&self) -> &'static str {
        if self.explicit_black_point || self.corrected_blend_endpoints() {
            "2.0"
        } else {
            "1.7"
        }
    }
    fn finish(self, root: usize, info: usize) -> Result<Vec<u8>, Error> {
        let mut bytes = format!("%PDF-{}\n", self.version()).into_bytes();
        bytes.extend_from_slice(b"%\xe2\xe3\xcf\xd3\n");
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
            return Err(limit(&format!(
                "PDF exceeds {} MiB",
                crate::publish::MAX_OUTPUT_BYTES as f64 / 1_048_576.0
            )));
        }
        Ok(bytes)
    }
}

#[derive(Default)]
struct Stream {
    content: String,
    resources: BTreeMap<&'static str, BTreeSet<usize>>,
    rgb8_solids: BTreeSet<String>,
    default_rgb: Option<usize>,
    artwork_blend_space: Option<String>,
    scalar_artwork: bool,
}
impl Stream {
    fn solid_color(&mut self, rgb: [f64; 3]) -> Result<(), Error> {
        if self.scalar_artwork {
            let [r, g, b] = rgb;
            let gray = crate::artwork_masks::encoded_luminance(r, g, b);
            self.content.push_str(&format!("{} g\n", number(gray)?));
        } else {
            self.content.push_str(&format!("{} rg\n", numbers(&rgb)?));
        }
        Ok(())
    }

    fn use_resource(&mut self, category: &'static str, id: usize, op: &str) {
        self.resources.entry(category).or_default().insert(id);
        self.content.push_str(&format!("/R{id} {op}\n"));
    }
    fn dictionary(&self, marks: Option<usize>) -> String {
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
        if !self.rgb8_solids.is_empty() {
            let base = self
                .default_rgb
                .map_or_else(|| "/DeviceRGB".into(), |id| format!("{id} 0 R"));
            let spaces = entries.entry("ColorSpace").or_default();
            for rgb in &self.rgb8_solids {
                spaces.push(format!("/C{rgb} [/Indexed {base} 0 <{rgb}>]"));
            }
        }
        if let Some(id) = self.default_rgb {
            entries
                .entry("ColorSpace")
                .or_default()
                .push(format!("/DefaultRGB {id} 0 R"));
        }
        if let Some(id) = marks {
            entries
                .entry("ColorSpace")
                .or_default()
                .push(format!("/Marks {id} 0 R"));
        }
        if let Some(space) = &self.artwork_blend_space {
            entries
                .entry("ColorSpace")
                .or_default()
                .push(format!("/ArtworkBlend {space}"));
        }
        let entries = entries
            .iter()
            .map(|(kind, values)| format!("/{kind} << {} >>", values.join(" ")))
            .collect::<Vec<_>>()
            .join(" ");
        format!("<< {entries} >>")
    }
}
pub(crate) fn blend_name(mode: BlendMode) -> Option<&'static str> {
    Some(match mode {
        BlendMode::Normal => "Normal",
        BlendMode::Multiply => "Multiply",
        BlendMode::Screen => "Screen",
        BlendMode::Darken => "Darken",
        BlendMode::Lighten => "Lighten",
        BlendMode::ColorBurn => "ColorBurn",
        BlendMode::ColorDodge => "ColorDodge",
        BlendMode::Overlay => "Overlay",
        BlendMode::HardLight => "HardLight",
        BlendMode::SoftLight => "SoftLight",
        BlendMode::Difference => "Difference",
        BlendMode::Exclusion => "Exclusion",
        BlendMode::Hue => "Hue",
        BlendMode::Saturation => "Saturation",
        BlendMode::Color => "Color",
        BlendMode::Luminosity => "Luminosity",
        _ => return None,
    })
}

fn graphics_state(
    writer: &mut Writer,
    stream: &mut Stream,
    opacity: f64,
    mode: BlendMode,
) -> Result<(), Error> {
    let name =
        blend_name(mode).ok_or_else(|| unsupported("Blend mode has no standard PDF equivalent"))?;
    if mode != BlendMode::Normal {
        writer.non_normal_modes.insert(name);
    }
    writer.page_requires_backdrop |= opacity != 1.0 || mode != BlendMode::Normal;
    let id = writer.add(format!(
        "<< /Type /ExtGState /ca {} /CA {} /BM /{name} /SMask /None /OP false /op false /OPM 0 >>",
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

fn gradient(
    writer: &mut Writer,
    stream: &mut Stream,
    field: &crate::paint::Field,
    paint_matrix: Matrix,
) -> Result<(), Error> {
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
    if *spread != Spread::Pad || *space != Interpolation::Srgb {
        return Err(unsupported(
            "PDF gradients require pad spread and encoded-sRGB interpolation",
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
    let coords = numbers(&coordinates)?;
    let transform = numbers(&geometry::multiply(paint_matrix, field.transform()))?;
    let channels = if stream.scalar_artwork {
        ShadingChannels::Luminance
    } else {
        ShadingChannels::Rgb
    };
    let color = gradient_shading(writer, kind, &coords, stops, &positions, channels)?;
    let alpha = stops[0].color[3];
    if stops.iter().all(|s| s.color[3] == alpha) {
        graphics_state(writer, stream, f64::from(alpha) / 255.0, BlendMode::Normal)?;
    } else {
        let opacity = gradient_shading(
            writer,
            kind,
            &coords,
            stops,
            &positions,
            ShadingChannels::Alpha,
        )?;
        // The mask is established in the item's page coordinates. Apply the
        // paint transform inside the mask, just as for the color shading below.
        let mut mask_stream = Stream {
            default_rgb: writer.default_rgb,
            content: format!("{transform} cm\n"),
            ..Stream::default()
        };
        mask_stream.use_resource("Shading", opacity, "sh");
        let dictionary = opacity::mask_dictionary(
            writer,
            mask_stream,
            crate::artwork_masks::Mode::Luminance,
            0.0,
            1.0,
        )?;
        graphics_state(writer, stream, 1.0, BlendMode::Normal)?;
        let state = writer.add(dictionary)?;
        stream.use_resource("ExtGState", state, "gs");
        writer.page_requires_backdrop = true;
        writer.gradient_opacity_masks += 1;
    }
    stream.content.push_str(&format!("{transform} cm\n"));
    stream.use_resource("Shading", color, "sh");
    Ok(())
}

enum ShadingChannels {
    Rgb,
    Luminance,
    Alpha,
}

fn gradient_shading(
    writer: &mut Writer,
    kind: u8,
    coords: &str,
    stops: &[crate::paint::Stop],
    positions: &[f64],
    channels: ShadingChannels,
) -> Result<usize, Error> {
    let space = match channels {
        ShadingChannels::Rgb => "DeviceRGB",
        _ => "DeviceGray",
    };
    let components = |color: Color| {
        let [r, g, b, a] = color.map(|v| f64::from(v) / 255.0);
        match channels {
            ShadingChannels::Rgb => numbers(&[r, g, b]),
            ShadingChannels::Luminance => number(crate::artwork_masks::encoded_luminance(r, g, b)),
            ShadingChannels::Alpha => number(a),
        }
    };
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
        let c0 = components(lo.color)?;
        let c1 = components(hi.color)?;
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
    writer.add(format!("<< /ShadingType {kind} /ColorSpace /{space} /Domain [0 2] /Coords [{coords}] /Function {function} 0 R /Extend [true true] >>"))
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
            graphics_state(writer, stream, color[3] as f64 / 255.0, BlendMode::Normal)?;
            let [r, g, b, _] = *color;
            if writer.page_uses_blends && !stream.scalar_artwork {
                // A reader truncating a decimal RGB operand by one byte level
                // can turn a near-neutral hue gray or reverse a dodge result.
                // A single-entry Indexed space carries the source bytes exactly.
                let rgb = format!("{r:02x}{g:02x}{b:02x}");
                stream.content.push_str(&format!("/C{rgb} cs 0 scn\n"));
                stream.rgb8_solids.insert(rgb);
            } else {
                stream.solid_color([r, g, b].map(|v| f64::from(v) / 255.0))?;
            }
            writer.path(&mut stream.content, shape, shape_matrix)?;
            stream.content.push_str(if rule == FillRule::EvenOdd {
                "f*\n"
            } else {
                "f\n"
            });
        }
        Paint::Field(field) => {
            clip(writer, stream, shape, shape_matrix, rule)?;
            gradient(writer, stream, field, paint_matrix)?;
        }
        Paint::Precise(color) => {
            graphics_state(writer, stream, color.rgba[3], BlendMode::Normal)?;
            let [r, g, b, _] = color.rgba;
            stream.solid_color([r, g, b])?;
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
    if writer.pixels + writer.grid_mask_samples > MAX_IMAGE_PIXELS {
        return Err(limit(&format!(
            "PDF image copies and opacity grids exceed {MAX_IMAGE_PIXELS} samples"
        )));
    }
    let mut rgb = Vec::with_capacity(rgba.len() / 4 * 3);
    let mut gray = Vec::with_capacity(rgba.len() / 4);
    for pixel in rgba.as_chunks::<4>().0 {
        rgb.extend_from_slice(&pixel[..3]);
        gray.push(pixel[3]);
    }
    let mask = if gray.iter().any(|&a| a != 255) {
        writer.page_requires_backdrop = true;
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

fn preflight(document: &Document, display_blends: bool) -> Result<(), Error> {
    let mut stroke_commands = 0;
    // Validate each page's inputs here, including hidden items. The writer
    // charges only painted copies to the cumulative delivery budget.
    let mut pixels = 0;
    for (i, item) in document.items.iter().enumerate() {
        if blend_name(item.blend).is_none() {
            return Err(unsupported("Blend mode has no standard PDF equivalent").at_item(&item.id));
        }
        if item.blend != BlendMode::Normal && !display_blends {
            return Err(unsupported("Non-normal vector PDF blending requires display color with the working RGB blending space").at_item(&item.id));
        }
        if item.content.is_knockout()
            || !item.effects.is_empty()
            || !item.filters.is_empty()
            || !item.coverage.is_smooth()
            || item.pixel_warp.is_some()
            || item.clip_to.is_some()
        {
            return Err(unsupported("PDF does not preserve knockout, effects, filters, dissolve, pixel warps or layer clipping").at_item(&item.id));
        }
        if let Some(mask) = item
            .mask
            .as_ref()
            .filter(|m| m.enabled && !m.constant && m.density != 0.0)
        {
            let [w, h] = mask.prepared_size();
            pixels += u64::from(w) * u64::from(h);
        }
        match &item.content {
            Content::Object { .. } => return Err(unsupported("PDF does not retain editable object sources; deliver an explicit image or snapshot").at_item(&item.id)),
            Content::Raw { .. } | Content::Samples { .. } | Content::StoredSamples { .. } => return Err(unsupported("PDF delivery does not yet preserve retained sample-grid depths; use TIFF or a snapshot").at_item(&item.id)),
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
        if pixels > MAX_IMAGE_PIXELS {
            return Err(limit(&format!(
                "PDF image copies and opacity grids exceed {MAX_IMAGE_PIXELS} samples"
            ))
            .at_item(&item.id));
        }
    }
    if stroke_commands > MAX_COMMANDS as u64 {
        return Err(limit("PDF scene exceeds generated-path budget"));
    }
    Ok(())
}

#[derive(Default)]
struct PageResources {
    pixels: BTreeMap<String, assets::Pixels>,
    layouts: BTreeMap<String, crate::text::Layout>,
    masks: crate::masks::PreparedDocument,
    artwork_masks: BTreeMap<String, usize>,
}

fn checked_layouts(
    document: &Document,
    fonts: &crate::fonts::Cache,
) -> Result<BTreeMap<String, crate::text::Layout>, Error> {
    let layouts = crate::text::prepare(document, fonts)?;
    for (id, layout) in &layouts {
        let world = scene::world_transform(document, scene::index(document, id)?)?;
        for path in &layout.paths {
            validate_world_geometry(&path.geometry, world)?;
        }
    }
    Ok(layouts)
}

fn items(
    writer: &mut Writer,
    output: &mut Stream,
    document: &Document,
    parent: Option<&str>,
    resources: &PageResources,
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
            scalar_artwork: output.scalar_artwork,
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
                    crate::text::clip_geometry(&item.content, &resources.layouts[&item.id])
                {
                    clip(writer, &mut stream, &geometry, world, FillRule::Nonzero)?;
                }
                for path in &resources.layouts[&item.id].paths {
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
            Content::Group { .. } => {
                items(writer, &mut stream, document, Some(&item.id), resources)?
            }
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
                items(writer, &mut stream, document, Some(&item.id), resources)?;
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
                let pixels = &resources.pixels[asset_id];
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
        let mut opacity = item.opacity * item.fill_opacity;
        let mut mask_state = resources.artwork_masks.get(&item.id).copied();
        if let Some(prepared) = resources.masks.items.get(&item.id) {
            let mask = item.mask.as_deref().expect("prepared item mask");
            writer.grid_masks += 1;
            mask_state = opacity::grid_state(writer, mask, prepared, world, opacity)
                .map_err(|e| e.at_item(&item.id))?;
            if mask_state.is_none() {
                opacity *= prepared.outside;
            }
        }
        if mask_state.is_some() {
            opacity = 1.0;
        }
        let isolated = !matches!(
            item.content,
            Content::Group {
                isolated: false,
                ..
            }
        );
        let native_ink_leaf =
            writer.native_inks && !stream.scalar_artwork && !item.content.is_container();
        let group = if stream.scalar_artwork {
            "/I true /CS /DeviceGray".into()
        } else if native_ink_leaf {
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
        let group = if native_ink_leaf && opacity == 1.0 && mask_state.is_none() {
            String::new()
        } else {
            format!("/Group << /S /Transparency {group} /K false >>")
        };
        let id = writer.stream(
            &format!(
                "/Type /XObject /Subtype /Form /FormType 1 /BBox [{}] /Resources {} {group}",
                writer.page_bbox,
                stream.dictionary(None)
            ),
            stream.content.as_bytes(),
        )?;
        output.content.push_str("q\n");
        graphics_state(writer, output, opacity, item.blend)?;
        if let Some(state) = mask_state {
            output.use_resource("ExtGState", state, "gs");
            writer.page_requires_backdrop = true;
        }
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
    if options.marks.is_some()
        && (options.print.is_some() || options.ink_recipe.is_some() || options.prepress.is_some())
    {
        return Err(Error::new(
            "INVALID_REQUEST",
            "pdf_options.marks requires vector page delivery. For native flattened plates use prepress.marks.",
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
        crate::swatches::vector_export(document, ExportFormat::Pdf)?;
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
    let volume = crate::volumes::evaluate(
        document,
        control.unwrap_or(&crate::control::Control::default()),
    )?;
    let document = volume.as_ref().unwrap_or(document);
    let warps = crate::warps::evaluate_controlled(
        document,
        control.unwrap_or(&crate::control::Control::default()),
    )?;
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
    let (color_profile, working_blend_space) = if let Some(profile) = &document.output_profile {
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
        // Profile streams are deduplicated by their exact ICC bytes. This also
        // admits an explicitly embedded copy of the working profile.
        let working = writer.blend_space.as_ref() == Some(&source_space);
        writer.default_rgb = Some(writer.add(source_space)?);
        let bytes = encoding.bytes()?;
        (
            Some(
                json!({"icc_sha256":assets::sha256(&bytes),"icc_bytes":bytes.len(),"profile_embedded":true,"role":"ICCBased_RGB_page_and_isolated_group_blending","untagged_RGB":"explicit_builtin_srgb_DefaultRGB_in_every_resource_scope","rendering_intent":"retained_device_paint_intent;otherwise_relative_colorimetric","source_components_changed":false}),
            ),
            working,
        )
    } else {
        (None, true)
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
        writer.page_bbox = format!("0 0 {} {}", page.width, page.height);
        let viewport = page
            .vector_canvas
            .map(|c| crate::vector_canvas::translated(page, c.origin_px.map(|v| -v)))
            .transpose()?;
        let page = viewport.as_ref().unwrap_or(page);
        preflight(page, !native_inks && working_blend_space)?;
        writer.page_uses_blends = page
            .items
            .iter()
            .any(|item| item.visible && item.blend != BlendMode::Normal);
        if native_inks {
            ink_pages.push(crate::swatches::ink_diagnostics(page)?);
        }
        let fonts = crate::fonts::resolve(page, resources.font_root.as_deref())?;
        let layouts = checked_layouts(page, &fonts)?;
        glyphs += layouts.values().map(|l| l.glyphs.len()).sum::<usize>();
        let pixels = assets::resolve(page, resources.asset_root.as_deref())?;
        let masks =
            crate::masks::prepare_document(page, resources.asset_root.as_deref(), &writer.control)?;
        let artwork_masks = artwork::prepare(&mut writer, page, &fonts)?;
        let page_resources = PageResources {
            pixels,
            layouts,
            masks,
            artwork_masks,
        };
        let ppi = page.resolution_ppi;
        let physical = 72.0 / ppi;
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
        let marked = options
            .marks
            .map(|settings| marks::Layout::new(logical, ppi, bleed, Some(settings)))
            .transpose()?;
        let user_unit = marked.as_ref().map_or_else(
            || {
                (logical[0].max(logical[1]) * physical / crate::limits::pdf::MAX_PAGE_COORDINATE)
                    .ceil()
                    .max(1.0)
            },
            |layout| layout.user_unit,
        );
        if user_unit > f64::from(crate::limits::pdf::MAX_USER_UNIT) {
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
        writer.page_has_spot_paint = false;
        writer.page_requires_backdrop = false;
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
        items(&mut writer, &mut stream, page, None, &page_resources)?;
        stream.content.push_str("Q\n");
        let mut page_group = format!(
            " /Group << /Type /Group /S /Transparency /CS {} /I true /K false >>",
            writer.group_space()
        );
        let (media, bounds, trim, mark_space) = if let Some(layout) = &marked {
            if writer.page_requires_backdrop && (!native_inks || writer.blend_space.is_some()) {
                return Err(unsupported(
                    "Marked pages with RGB blending require opaque knockout artwork. Keep the unmarked vector page or use prepress.marks for a flattened plate sheet.",
                ));
            }
            let bounds = layout.coordinates(layout.bleed);
            let placement = format!(
                "q\n1 0 0 1 {} {} cm\n0 0 {} {} re W n\n",
                number(bounds[0])?,
                number(bounds[1])?,
                number(width)?,
                number(height)?
            );
            if native_inks && (writer.blend_space.is_none() || writer.page_has_spot_paint) {
                // Isolating native separations in another form can change
                // process plate values. Opaque spot paints need no page blend.
                if writer.blend_space.is_some() {
                    stream.artwork_blend_space.clone_from(&writer.blend_space);
                    page_group.clear();
                }
                stream.content.insert_str(0, &placement);
            } else {
                // Keep RGB blending and explicit source-profile conversions on
                // the artwork. Passing All through them can erase spot marks.
                let form = writer.stream(&format!("/Type /XObject /Subtype /Form /FormType 1 /BBox [0 0 {} {}] /Resources {}{page_group}",
                    number(width)?, number(height)?, stream.dictionary(None)), stream.content.as_bytes())?;
                page_group.clear();
                stream = Stream {
                    content: placement,
                    ..Stream::default()
                };
                stream.use_resource("XObject", form, "Do");
            }
            stream.content.push_str("Q\n");
            let mark_space = layout.emit(&mut writer, &mut stream.content)?;
            (
                layout.coordinates(layout.media),
                bounds,
                layout.coordinates(layout.trim),
                mark_space,
            )
        } else {
            let media = [0.0, 0.0, width, height];
            (
                media,
                media,
                [
                    bleed.left as f64 * factor,
                    bleed.bottom as f64 * factor,
                    width - bleed.right as f64 * factor,
                    height - bleed.top as f64 * factor,
                ],
                None,
            )
        };
        let content = writer.stream("", stream.content.as_bytes())?;
        let id=writer.add(format!("<< /Type /Page /Parent {tree} 0 R /MediaBox [{}] /CropBox [{}] /BleedBox [{}] /TrimBox [{}] /UserUnit {} /Resources {} /Contents {content} 0 R{page_group} >>",numbers(&media)?,numbers(&media)?,numbers(&bounds)?,numbers(&trim)?,number(user_unit)?,stream.dictionary(mark_space)))?;
        references.push(format!("{id} 0 R"));
        let artboard_id = selection.map(|i| &document.items[i].id);
        let mut receipt = json!({"index":receipts.len(),"artboard_id":artboard_id,"logical_size":logical,"physical_points":[logical[0]*physical,logical[1]*physical],"resolution_ppi":ppi,"media_box":media,"trim_box":trim,"user_unit":user_unit,"coordinates":"pdf_bottom_left_in_user_units"});
        if let Some(layout) = &marked {
            receipt["artwork_physical_points"] = receipt["physical_points"].clone();
            receipt["physical_points"] = json!([layout.media[2], layout.media[3]]);
            receipt["bleed_box"] = json!(bounds);
            receipt["marks"] = layout.receipt();
            if stream.artwork_blend_space.is_some() {
                receipt["artwork_blending"] =
                    json!("opaque_knockout_paints;declared_RGB_profile_retained_in_ArtworkBlend");
            }
        }
        receipts.push(receipt);
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
    let grid_masks = writer.grid_masks;
    let artwork_alpha_masks = writer.artwork_alpha_masks;
    let artwork_luminance_masks = writer.artwork_luminance_masks;
    let grid_mask_samples = writer.grid_mask_samples;
    let version = writer.version();
    let black_point = writer.explicit_black_point;
    let corrected_endpoints = writer.corrected_blend_endpoints();
    let blend_modes = writer.non_normal_modes.clone();
    let gradient_opacity_masks = writer.gradient_opacity_masks;
    let bytes = writer.finish(catalog, info)?;
    let mut result = json!({"media_type":"application/pdf","encoding":"base64","data":STANDARD.encode(&bytes),"pages":receipts,"pdf":{"version":"1.7","include_bleed":options.include_bleed,"artboards":options.artboards,"path_commands":commands,"image_pixels":image_pixels,"text_glyphs":glyphs,"color":"DeviceRGB_encoded_working_samples_consumer_color_management","text":"vector_outlines","editable_source":"snapshot","deterministic":true},"losses":["Text is delivered as glyph outlines, without searchable text, embedded fonts or semantic tagging; retain the snapshot and pinned resources for editing.","Vector geometry remains paths. Ellipses use four cubic segments; complex strokes use the shared bounded outline evaluator.","DeviceRGB consumer color management, edge antialiasing and image sampling can differ from Inkbolt previews; this is not a print-profile or exact-pixel guarantee.","PDF does not carry the editable document model, guides, selections, channels or font controls. PDF reimport is not implemented."]});
    metadata::annotate(&mut result, packet.as_deref(), policy, false);
    result["pdf"]["version"] = json!(version);
    if artwork_alpha_masks + artwork_luminance_masks > 0 {
        result["pdf"]["artwork_masks"] =
            json!({"alpha":artwork_alpha_masks,"luminance":artwork_luminance_masks});
        result["losses"].as_array_mut().unwrap().push(json!("Artwork mask sources are delivered as placed vector soft masks. Keep the snapshot to edit a shared source or change its links. Reader antialiasing can differ from the PNG proof."));
    }
    if grid_masks != 0 {
        result["pdf"]["grid_masks"] = json!(grid_masks);
        result["pdf"]["grid_mask_samples"] = json!(grid_mask_samples);
        if grid_mask_samples != 0 {
            result["losses"].as_array_mut().unwrap().push(json!("PDF stores sampled opacity grids at 16-bit precision. Readers can soften fine checkerboards and stripes or shift a cell edge. Use a PNG proof for exact preview pixels and keep the snapshot to edit the mask."));
        }
    }
    if gradient_opacity_masks > 0 {
        result["pdf"]["gradient_opacity_masks"] = json!(gradient_opacity_masks);
        result["losses"].as_array_mut().unwrap().push(json!("Gradient opacity is retained as a vector shading. At a hard stop, a PDF reader can sample both sides of the transition within one pixel and display a different edge color from the Inkbolt preview."));
    }
    if !blend_modes.is_empty() {
        result["pdf"]["blend_modes"] = json!(blend_modes);
        result["losses"].as_array_mut().unwrap().push(json!("The PDF reader computes the native blends. Readers can differ on translucent colors and produce visible hue or saturation shifts, especially near gray. Use a PNG proof when the exact rendered pixels matter."));
    }
    if corrected_endpoints {
        result["losses"].as_array_mut().unwrap().push(json!("ColorBurn and ColorDodge use PDF 2.0 endpoint rules. Readers using the earlier formulas can render a white backdrop channel burned with black as black, or a black backdrop channel dodged with white as white."));
    }
    if black_point {
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
    if let Some(mut profile) = color_profile {
        if options.marks.is_some() {
            profile["role"] =
                json!("RGB_artwork_blending;opaque_spot_pages_retain_profile_in_ArtworkBlend");
        }
        result["color_profile"] = profile;
        result["pdf"]["color"] =
            json!("calibrated_ICCBased_RGB_blending;retained_source_profiles_and_spot_identities");
        result["losses"][2] = json!(
            "The declared RGB profile calibrates page and isolated-group blending. Device RGB sources explicitly use sRGB; profiled paints retain their source profiles and intents. Consumer rounding, antialiasing and profile interpretation may differ; this is not a print proof or exact-pixel guarantee."
        );
        if options.marks.is_some() {
            result["losses"][2] = json!(
                "RGB artwork groups use the declared blending profile. Opaque calibrated spot pages retain that profile in ArtworkBlend and paint directly on the sheet. Device RGB uses sRGB and profiled paints retain their source profiles and intents. Rasterization and colour conversion depend on the consumer."
            );
        }
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    #[test]
    fn opacity_grid_and_image_copies_share_one_export_budget() {
        use super::*;
        let mask: crate::masks::Mask = serde_json::from_value(json!({
            "width": 1, "height": 1, "gray_hex":"80"
        }))
        .unwrap();
        let plane = crate::masks::prepare(&mask, identity()).unwrap();
        let mut writer = Writer {
            pixels: MAX_IMAGE_PIXELS - 9,
            page_bbox: "0 0 1 1".into(),
            ..Writer::default()
        };
        assert!(
            opacity::grid_state(&mut writer, &mask, &plane, identity(), 1.0)
                .unwrap()
                .is_some()
        );
        assert_eq!(writer.grid_mask_samples, 9);
        assert_eq!(
            opacity::grid_state(&mut writer, &mask, &plane, identity(), 1.0)
                .unwrap_err()
                .code,
            "RESOURCE_LIMIT"
        );
        let error = image(
            &mut writer,
            &mut Stream::default(),
            [1, 1],
            &[255; 4],
            [1.0; 2],
            identity(),
        )
        .unwrap_err();
        assert_eq!(error.code, "RESOURCE_LIMIT");
    }

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
