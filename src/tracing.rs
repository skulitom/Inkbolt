//! Original exact cell-boundary vectorization of explicitly classified RGBA8 grids.
use crate::{Error, assets, control::Control, model::*, render};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{collections::BTreeMap, path::Path};

pub const MAX_PIXELS: usize = 1_048_576;
pub const MAX_COLORS: usize = 64;
pub const MAX_EDGES: usize = 262_144;
const ALGORITHM: &str = "inkbolt-cell-contours-v1";

#[derive(Clone, Debug, Deserialize, JsonSchema)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Source {
    Pixels {
        width: u32,
        height: u32,
        rgba_hex: String,
    },
    Asset {
        asset: assets::ImageAsset,
    },
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Channel {
    Alpha,
    Luma,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Mode {
    Binary {
        channel: Channel,
        threshold: u8,
        #[serde(default)]
        invert: bool,
        color: Color,
    },
    Exact {},
    Quantized {
        rgb_levels: u16,
        alpha_levels: u16,
    },
    Palette {
        colors: Vec<Color>,
    },
}
fn one() -> u32 {
    1
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Options {
    pub mode: Mode,
    #[serde(default = "one")]
    pub alpha_min: u32,
    #[serde(default = "one")]
    pub min_region_pixels: u32,
    #[serde(default)]
    pub max_hole_pixels: u32,
}
fn invalid(message: &str) -> Error {
    Error::new("INVALID_TRACE", message)
}
fn dimensions(w: u32, h: u32) -> Result<usize, Error> {
    let count = assets::dimensions(w, h)? as usize;
    if count > MAX_PIXELS {
        return Err(limit("Tracing exceeds 1048576 source pixels"));
    }
    Ok(count)
}
fn load(source: &Source, root: Option<&Path>) -> Result<assets::Pixels, Error> {
    match source {
        Source::Asset { asset } => {
            dimensions(asset.width, asset.height)?;
            assets::load(asset, root)
        }
        Source::Pixels {
            width,
            height,
            rgba_hex,
        } => {
            let n = dimensions(*width, *height)?;
            if rgba_hex.len() != n * 8 || !rgba_hex.bytes().all(|v| v.is_ascii_hexdigit()) {
                return Err(invalid(
                    "Trace pixels require width*height straight RGBA8 hex values",
                ));
            }
            Ok(assets::Pixels {
                width: *width,
                height: *height,
                rgba: render::unhex(rgba_hex),
            })
        }
    }
}
fn validate_options(o: &Options) -> Result<(), Error> {
    if o.alpha_min > 255
        || !(1..=MAX_PIXELS as u32).contains(&o.min_region_pixels)
        || o.max_hole_pixels > MAX_PIXELS as u32
    {
        return Err(invalid(
            "Trace alpha_min requires 0..255 and region/hole sizes must fit the pixel budget",
        ));
    }
    match &o.mode {
        Mode::Binary { color, .. } if color[3] == 0 => {
            return Err(invalid("Binary trace color must be visible"));
        }
        Mode::Quantized {
            rgb_levels,
            alpha_levels,
        } if !(2..=256).contains(rgb_levels) || !(2..=256).contains(alpha_levels) => {
            return Err(invalid(
                "Quantization requires 2..256 levels per declared channel family",
            ));
        }
        Mode::Palette { colors } => {
            if colors.is_empty() || colors.len() > MAX_COLORS {
                return Err(invalid("Palette requires 1..64 colors"));
            }
            for (i, c) in colors.iter().enumerate() {
                if (c[3] == 0 && *c != [0; 4]) || colors[..i].contains(c) {
                    return Err(invalid(
                        "Palette colors must be unique; transparent entries must be canonical zero RGBA",
                    ));
                }
            }
        }
        _ => (),
    }
    Ok(())
}
// All decisions use integer arithmetic. Palette ties choose the first entry.
fn premul(c: Color) -> [i64; 4] {
    [
        c[0] as i64 * c[3] as i64,
        c[1] as i64 * c[3] as i64,
        c[2] as i64 * c[3] as i64,
        c[3] as i64 * 255,
    ]
}
fn distance(a: Color, b: Color) -> i64 {
    premul(a)
        .into_iter()
        .zip(premul(b))
        .map(|(a, b)| (a - b) * (a - b))
        .sum()
}
fn quantize(v: u8, levels: u16) -> u8 {
    let steps = levels as u32 - 1;
    let index = (v as u32 * steps + 127) / 255;
    ((index * 255 + steps / 2) / steps) as u8
}
fn classify(c: Color, o: &Options) -> Color {
    if c[3] == 0 || (c[3] as u32) < o.alpha_min {
        return [0; 4];
    }
    let result = match &o.mode {
        Mode::Binary {
            channel,
            threshold,
            invert,
            color,
        } => {
            let value = match channel {
                Channel::Alpha => c[3] as u32 * 10000,
                Channel::Luma => 2126 * c[0] as u32 + 7152 * c[1] as u32 + 722 * c[2] as u32,
            };
            if (value >= *threshold as u32 * 10000) != *invert {
                *color
            } else {
                [0; 4]
            }
        }
        Mode::Exact {} => c,
        Mode::Quantized {
            rgb_levels,
            alpha_levels,
        } => std::array::from_fn(|i| {
            quantize(c[i], if i == 3 { *alpha_levels } else { *rgb_levels })
        }),
        Mode::Palette { colors } => *colors.iter().min_by_key(|p| distance(c, **p)).unwrap(),
    };
    if result[3] == 0 { [0; 4] } else { result }
}
fn neighbors(i: usize, w: usize, h: usize, diagonal: bool) -> impl Iterator<Item = usize> {
    let x = (i % w) as isize;
    let y = (i / w) as isize;
    [
        (-1, 0),
        (1, 0),
        (0, -1),
        (0, 1),
        (-1, -1),
        (1, -1),
        (-1, 1),
        (1, 1),
    ]
    .into_iter()
    .take(if diagonal { 8 } else { 4 })
    .filter_map(move |(dx, dy)| {
        let xx = x + dx;
        let yy = y + dy;
        (xx >= 0 && yy >= 0 && xx < w as isize && yy < h as isize)
            .then(|| yy as usize * w + xx as usize)
    })
}
type Region = (Vec<usize>, Option<Color>);
fn regions(
    grid: &[Color],
    w: usize,
    h: usize,
    holes: bool,
    control: &Control,
) -> Result<Vec<Region>, Error> {
    let mut seen = vec![false; grid.len()];
    let mut result = Vec::new();
    for seed in 0..grid.len() {
        if seed % 4096 == 0 {
            control.check()?;
        }
        if seen[seed] || (grid[seed][3] == 0) != holes {
            continue;
        }
        let color = grid[seed];
        let mut points = vec![seed];
        seen[seed] = true;
        let mut at = 0;
        let mut boundary = None;
        let mut mixed = false;
        while at < points.len() {
            if at % 4096 == 0 {
                control.check()?;
            }
            let p = points[at];
            at += 1;
            if holes && (p % w == 0 || p % w == w - 1 || p / w == 0 || p / w == h - 1) {
                mixed = true;
            }
            // Complement uses eight-connectivity so a diagonal opening remains open.
            for q in neighbors(p, w, h, holes) {
                if grid[q] == color {
                    if !seen[q] {
                        seen[q] = true;
                        points.push(q);
                    }
                } else if holes {
                    if boundary.is_some_and(|c| c != grid[q]) {
                        mixed = true;
                    }
                    boundary = Some(grid[q]);
                }
            }
        }
        result.push((points, if mixed { None } else { boundary }));
    }
    Ok(result)
}
#[derive(Clone, Copy)]
struct Vertex {
    all: u8,
    remaining: u8,
}
type Key = (Color, u32, u32);
fn end(x: u32, y: u32, d: u8) -> (u32, u32) {
    match d {
        0 => (x + 1, y),
        1 => (x, y + 1),
        2 => (x - 1, y),
        _ => (x, y - 1),
    }
}
fn contours(
    grid: &[Color],
    w: usize,
    h: usize,
    control: &Control,
) -> Result<(Vec<Item>, Vec<Value>, usize), Error> {
    let mut graph = BTreeMap::<Key, Vertex>::new();
    let mut edges = 0usize;
    let mut counts = BTreeMap::<Color, usize>::new();
    for y in 0..h {
        control.check()?;
        for x in 0..w {
            let c = grid[y * w + x];
            if c[3] == 0 {
                continue;
            }
            *counts.entry(c).or_default() += 1;
            if counts.len() > MAX_COLORS {
                return Err(limit(
                    "Trace exceeds 64 resulting colors; use an explicit palette or quantization",
                ));
            }
            let x = x as u32;
            let y = y as u32;
            for (ex, ey, d, present) in [
                (
                    x,
                    y,
                    0,
                    y > 0 && grid[(y as usize - 1) * w + x as usize] == c,
                ),
                (
                    x + 1,
                    y,
                    1,
                    x + 1 < w as u32 && grid[y as usize * w + x as usize + 1] == c,
                ),
                (
                    x + 1,
                    y + 1,
                    2,
                    y + 1 < h as u32 && grid[(y as usize + 1) * w + x as usize] == c,
                ),
                (
                    x,
                    y + 1,
                    3,
                    x > 0 && grid[y as usize * w + x as usize - 1] == c,
                ),
            ] {
                if present {
                    continue;
                }
                edges += 1;
                if edges > MAX_EDGES {
                    return Err(limit("Trace exceeds 262144 unit boundary edges"));
                }
                let entry = graph.entry((c, ex, ey)).or_insert(Vertex {
                    all: 0,
                    remaining: 0,
                });
                entry.all |= 1 << d;
                entry.remaining |= 1 << d;
            }
        }
    }
    let mut paths = BTreeMap::<Color, Vec<PathCommand>>::new();
    let mut stats = BTreeMap::<Color, (i64, usize, usize, usize)>::new();
    let mut command_count = 0;
    let mut steps = 0;
    // Fixed right-turn pairing keeps diagonally touching foreground components separate.
    let starts: Vec<_> = graph.keys().copied().collect();
    for start in starts {
        while graph[&start].remaining != 0 {
            let first = graph[&start].remaining.trailing_zeros() as u8;
            let (c, mut x, mut y) = start;
            let mut d = first;
            let mut points = Vec::new();
            loop {
                if steps % 4096 == 0 {
                    control.check()?;
                }
                steps += 1;
                let vertex = graph
                    .get_mut(&(c, x, y))
                    .ok_or_else(|| invalid("Broken trace boundary"))?;
                if vertex.remaining & (1 << d) == 0 {
                    return Err(invalid("Trace boundary reused a directed edge"));
                }
                vertex.remaining &= !(1 << d);
                points.push((x as i64, y as i64));
                (x, y) = end(x, y, d);
                let bits = graph
                    .get(&(c, x, y))
                    .ok_or_else(|| invalid("Open trace boundary"))?
                    .all;
                d = [(d + 1) % 4, d, (d + 3) % 4, (d + 2) % 4]
                    .into_iter()
                    .find(|next| bits & (1 << next) != 0)
                    .ok_or_else(|| invalid("Open trace vertex"))?;
                if (c, x, y) == start && d == first {
                    break;
                }
                if steps > edges {
                    return Err(invalid("Trace boundary did not close"));
                }
            }
            let n = points.len();
            let mut area2 = 0i64;
            let mut corners = Vec::new();
            for i in 0..n {
                let p = points[(i + n - 1) % n];
                let q = points[i];
                let r = points[(i + 1) % n];
                area2 += q.0 * r.1 - q.1 * r.0;
                if (q.0 - p.0) * (r.1 - q.1) != (q.1 - p.1) * (r.0 - q.0) {
                    corners.push([q.0 as f64, q.1 as f64]);
                }
            }
            if corners.len() < 4 || area2 == 0 {
                return Err(invalid("Degenerate trace contour"));
            }
            command_count += corners.len() + 1;
            if command_count > MAX_SEGMENTS {
                return Err(limit(
                    "Trace output exceeds 4096 editable path commands; adjust classification or noise controls",
                ));
            }
            let path = paths.entry(c).or_default();
            path.push(PathCommand::Move { to: corners[0] });
            path.extend(
                corners
                    .into_iter()
                    .skip(1)
                    .map(|to| PathCommand::Line { to }),
            );
            path.push(PathCommand::Close {});
            let stat = stats.entry(c).or_default();
            stat.0 += area2;
            stat.1 += n;
            if area2 > 0 {
                stat.2 += 1;
            } else {
                stat.3 += 1;
            }
        }
    }
    if steps != edges {
        return Err(invalid("Trace left unvisited boundary edges"));
    }
    let mut items = Vec::new();
    let mut reports = Vec::new();
    for (i, (color, commands)) in paths.into_iter().enumerate() {
        let (area2, perimeter, components, holes) = stats[&color];
        if area2 != 2 * counts[&color] as i64 {
            return Err(invalid("Trace area does not match classified cells"));
        }
        let id = format!("trace-color-{i}");
        reports.push(json!({"item_id":id,"rgba":color,"pixels":counts[&color],"area":area2/2,"perimeter":perimeter,"components":components,"holes":holes,"commands":commands.len()}));
        items.push(Item {
            hdr_grade: None,
            pixel_warp: None,
            metadata: None,
            id,
            name: format!("Trace {}", render::hex(&color)),
            visible: true,
            locked: false,
            opacity: 1.0,
            fill_opacity: 1.0,
            coverage: crate::coverage::Mode::Smooth {},
            effects: vec![],
            blend: BlendMode::Normal,
            transform: identity(),
            parent: None,
            clip_to: None,
            clip: None,
            mask: None,
            artwork_mask: None,
            filters: vec![],
            content: Content::Vector {
                geometry: Geometry::Path { commands },
                fill: Some(Paint::Solid(color)),
                stroke: None,
                fill_rule: FillRule::Nonzero,
            },
        });
    }
    Ok((items, reports, edges))
}

pub fn trace(
    id: String,
    source: &Source,
    options: &Options,
    root: Option<&Path>,
    control: &Control,
) -> Result<Value, Error> {
    control.check()?;
    validate_options(options)?;
    if !valid_id(&id) {
        return Err(invalid("Trace document ID must be a portable ID"));
    }
    let pixels = load(source, root)?;
    control.check()?;
    let w = pixels.width as usize;
    let h = pixels.height as usize;
    let mut grid = Vec::with_capacity(w * h);
    for (i, c) in pixels.rgba.as_chunks::<4>().0.iter().enumerate() {
        if i % 4096 == 0 {
            control.check()?;
        }
        grid.push(classify(*c, options));
    }
    let mut removed = 0usize;
    let mut filled = 0usize;
    if options.min_region_pixels > 1 {
        for (region, _) in regions(&grid, w, h, false, control)? {
            if region.len() < options.min_region_pixels as usize {
                removed += region.len();
                for i in region {
                    grid[i] = [0; 4];
                }
            }
        }
    }
    if options.max_hole_pixels > 0 {
        // One simultaneous pass. Mixed-color surrounds and edge-connected holes stay intact.
        let holes = regions(&grid, w, h, true, control)?;
        for (region, color) in holes {
            if region.len() <= options.max_hole_pixels as usize
                && let Some(c) = color
            {
                filled += region.len();
                for i in region {
                    grid[i] = c;
                }
            }
        }
    }
    let (items, reports, edges) = contours(&grid, w, h, control)?;
    let flat: Vec<_> = grid.iter().flatten().copied().collect();
    let source_identity = assets::identity(pixels.width, pixels.height, &pixels.rgba);
    let classified_identity = assets::identity(pixels.width, pixels.height, &flat);
    let mut max_error = 0i64;
    let mut squared_error = 0i64;
    for (i, (a, b)) in pixels.rgba.as_chunks::<4>().0.iter().zip(&grid).enumerate() {
        if i % 4096 == 0 {
            control.check()?;
        }
        let a = *a;
        squared_error += distance(a, *b);
        for (a, b) in premul(a).into_iter().zip(premul(*b)) {
            max_error = max_error.max((a - b).abs());
        }
    }
    let provenance = json!({"algorithm":ALGORITHM,"source_identity":source_identity,"classified_identity":classified_identity,
        "width":w,"height":h,"options":options,"foreground_connectivity":4,"background_connectivity":8,
        "geometry":"exact_union_of_classified_unit_pixel_cells","contour_error_pixels":0,
        "corner_policy":"preserve_all_noncollinear_grid_corners","removed_pixels":removed,"filled_hole_pixels":filled});
    let document = Document {
        resource_profile: Default::default(),
        vector_canvas: None,
        stories: BTreeMap::new(),
        swatches: Default::default(),
        background: None,
        metadata: Some(crate::metadata::Record {
            properties: BTreeMap::from([("inkbolt.trace".into(), provenance.to_string())]),
            ..Default::default()
        }),
        output_profile: None,
        variants: None,
        schema_version: 2,
        id,
        kind: DocumentKind::Vector,
        width: pixels.width,
        height: pixels.height,
        color_space: ColorSpace::Srgb,
        revision: 0,
        resolution_ppi: 96.0,
        global_light: Default::default(),
        items,
        assets: Default::default(),
        fonts: Default::default(),
        selection: None,
        channels: Default::default(),
        ink_recipe: None,
    };
    validate(&document)?;
    control.check()?;
    Ok(
        json!({"document":document,"provenance":provenance,"colors":reports,"unit_edges":edges,
        "comparison":{"space":"premultiplied_encoded_srgb_and_alpha","maximum_channel_error":max_error as f64/65025.0,
        "rms_channel_error":(squared_error as f64/(w*h*4) as f64).sqrt()/65025.0},
        "losses":["Contours follow classified pixel-cell boundaries; no inferred smooth source curve or photographic reconstruction is claimed.",
        "Classification and noise controls may change colors, alpha or topology; provenance records their exact parameters and resulting grid identity.",
        "Adjacent vector colors can show consumer antialias seams after non-grid-aligned placement; integer-grid output has exact cell coverage.",
        "Output geometry is editable and provenance is historical; source image bytes remain external and are required to retrace."]}),
    )
}
