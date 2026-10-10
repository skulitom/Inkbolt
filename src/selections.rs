//! Persistent scalar pixel selections in document coordinates; no rendering side effects.
use crate::{Error, geometry, model::*, render, scene};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

pub const MAX_PIXELS: u64 = 262_144;
pub const MAX_WORK: u64 = 67_108_864;
pub const MAX_RADIUS: u32 = 32;
pub const MAX_POLYGON_POINTS: usize = 1024;

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Selection {
    pub width: u32,
    pub height: u32,
    pub gray_hex: String,
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Combine {
    #[default]
    Replace,
    Add,
    Subtract,
    Intersect,
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Refine {
    Expand,
    Contract,
    Feather,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(tag = "shape", rename_all = "snake_case", deny_unknown_fields)]
pub enum Boundary {
    Rect {
        x: f64,
        y: f64,
        width: f64,
        height: f64,
    },
    Ellipse {
        cx: f64,
        cy: f64,
        rx: f64,
        ry: f64,
    },
    Polygon {
        points: Vec<Point>,
    },
}
impl Boundary {
    fn geometry(&self) -> Result<Geometry, Error> {
        Ok(match self {
            Self::Rect {
                x,
                y,
                width,
                height,
            } => Geometry::Rect {
                x: *x,
                y: *y,
                width: *width,
                height: *height,
            },
            Self::Ellipse { cx, cy, rx, ry } => Geometry::Ellipse {
                cx: *cx,
                cy: *cy,
                rx: *rx,
                ry: *ry,
            },
            Self::Polygon { points } => {
                if !(3..=MAX_POLYGON_POINTS).contains(&points.len()) {
                    return Err(invalid("Selection polygon requires 3..=1024 points"));
                }
                let commands = std::iter::once(PathCommand::Move { to: points[0] })
                    .chain(points[1..].iter().map(|p| PathCommand::Line { to: *p }))
                    .chain(std::iter::once(PathCommand::Close {}))
                    .collect();
                Geometry::Path { commands }
            }
        })
    }
}
pub fn validate(selection: &Selection, width: u32, height: u32) -> Result<(), Error> {
    let n = check_size(width, height)?;
    if (selection.width, selection.height) != (width, height)
        || selection.gray_hex.len() != n * 2
        || !selection.gray_hex.bytes().all(|c| c.is_ascii_hexdigit())
    {
        return Err(invalid(
            "Pixel selection requires canvas-sized grayscale8 data",
        ));
    }
    Ok(())
}
pub(crate) fn check_size(width: u32, height: u32) -> Result<usize, Error> {
    if !(1..=MAX_DIMENSION).contains(&width) || !(1..=MAX_DIMENSION).contains(&height) {
        return Err(invalid("Selection dimensions must be in 1..=32768"));
    }
    let n = width as u64 * height as u64;
    if n > MAX_PIXELS {
        return Err(limit("Pixel selection exceeds 262144 pixels"));
    }
    Ok(n as usize)
}
fn active(document: &Document) -> Result<&Selection, Error> {
    document.selection.as_ref().ok_or_else(|| Error::new("INVALID_OPERATION","This operation requires an active pixel selection, including an explicit empty or full selection"))
}
pub fn fill(document: &mut Document, selected: bool) -> Result<(), Error> {
    let n = check_size(document.width, document.height)?;
    document.selection = Some(Selection {
        width: document.width,
        height: document.height,
        gray_hex: if selected { "ff" } else { "00" }.repeat(n),
    });
    Ok(())
}
pub fn shape(
    document: &mut Document,
    boundary: &Boundary,
    combine: Combine,
    antialias: bool,
    fill_rule: FillRule,
) -> Result<(), Error> {
    check_size(document.width, document.height)?;
    geometry::validate_geometry(&boundary.geometry()?)?;
    let mask = coverage(
        boundary,
        document.width,
        document.height,
        antialias,
        fill_rule,
    )?;
    combine_values(document, mask, combine)
}
pub(crate) fn combine_values(
    document: &mut Document,
    mask: Vec<u8>,
    combine: Combine,
) -> Result<(), Error> {
    if mask.len() != check_size(document.width, document.height)? {
        return Err(invalid("Selection operand must match the canvas"));
    }
    let values = if matches!(combine, Combine::Replace) {
        mask
    } else {
        let old = render::unhex(&active(document)?.gray_hex);
        old.into_iter()
            .zip(&mask)
            .map(|(a, &b)| match combine {
                Combine::Add => a.max(b),
                Combine::Subtract => a.saturating_sub(b),
                Combine::Intersect => a.min(b),
                Combine::Replace => unreachable!(),
            })
            .collect()
    };
    document.selection = Some(Selection {
        width: document.width,
        height: document.height,
        gray_hex: render::hex(&values),
    });
    Ok(())
}
pub fn invert(document: &mut Document) -> Result<(), Error> {
    let mut s = active(document)?.clone();
    s.gray_hex = render::hex(
        &render::unhex(&s.gray_hex)
            .into_iter()
            .map(|v| 255 - v)
            .collect::<Vec<_>>(),
    );
    document.selection = Some(s);
    Ok(())
}
pub fn refine(document: &mut Document, mode: Refine, radius: u32) -> Result<(), Error> {
    let selection = active(document)?;
    if radius > MAX_RADIUS {
        return Err(invalid(
            "Selection refinement radius must be in 0..=32 pixels",
        ));
    }
    let w = selection.width as usize;
    let h = selection.height as usize;
    if (w * h) as u64 * 2 * (2 * radius as u64 + 1) > MAX_WORK {
        return Err(limit("Selection refinement exceeds work budget"));
    }
    let mut values: Vec<_> = render::unhex(&selection.gray_hex)
        .into_iter()
        .map(f64::from)
        .collect();
    let mut temporary = vec![0.0; values.len()];
    let r = radius as i64;
    for horizontal in [true, false] {
        for y in 0..h as i64 {
            for x in 0..w as i64 {
                let mut value = if matches!(mode, Refine::Contract) {
                    255.0_f64
                } else {
                    0.0_f64
                };
                for d in -r..=r {
                    let sx = x + if horizontal { d } else { 0 };
                    let sy = y + if horizontal { 0 } else { d };
                    let next = if sx < 0 || sy < 0 || sx >= w as i64 || sy >= h as i64 {
                        0.0
                    } else {
                        values[sy as usize * w + sx as usize]
                    };
                    value = match mode {
                        Refine::Expand => value.max(next),
                        Refine::Contract => value.min(next),
                        Refine::Feather => value + next * (r + 1 - d.abs()) as f64,
                    };
                }
                temporary[y as usize * w + x as usize] = if matches!(mode, Refine::Feather) {
                    value / ((r + 1) * (r + 1)) as f64
                } else {
                    value
                };
            }
        }
        std::mem::swap(&mut values, &mut temporary);
    }
    document.selection.as_mut().unwrap().gray_hex = render::hex(
        &values
            .into_iter()
            .map(|v| v.clamp(0.0, 255.0).round() as u8)
            .collect::<Vec<_>>(),
    );
    Ok(())
}
fn bounds(width: u32, height: u32, values: &[u8]) -> Option<[u32; 4]> {
    let mut b = [width, height, 0, 0];
    for (i, &v) in values.iter().enumerate() {
        if v != 0 {
            let x = i as u32 % width;
            let y = i as u32 / width;
            b = [b[0].min(x), b[1].min(y), b[2].max(x + 1), b[3].max(y + 1)];
        }
    }
    (b[2] > b[0] && b[3] > b[1]).then_some(b)
}
pub fn inspect(selection: Option<&Selection>) -> Value {
    let Some(s) = selection else {
        return Value::Null;
    };
    let bytes = render::unhex(&s.gray_hex);
    json!({"width":s.width,"height":s.height,"bounds":bounds(s.width,s.height,&bytes),"selected_pixels":bytes.iter().filter(|&&v|v!=0).count(),"fully_selected_pixels":bytes.iter().filter(|&&v|v==255).count(),"coverage_sum":bytes.iter().map(|&v|v as u64).sum::<u64>() as f64/255.0,"sha256":crate::assets::sha256(&bytes),"coordinates":"document_pixel_grid","bounds_contract":"nonzero_end_exclusive"})
}
pub fn to_mask(
    document: &mut Document,
    index: usize,
    linked: bool,
    replace_existing: bool,
) -> Result<(), Error> {
    if document.items[index].mask.is_some() && !replace_existing {
        return Err(Error::new(
            "INVALID_OPERATION",
            "Item already has a mask; explicitly set replace_existing to replace it",
        ));
    }
    let selection = active(document)?;
    let source = render::unhex(&selection.gray_hex);
    let b = bounds(selection.width, selection.height, &source).unwrap_or([0, 0, 1, 1]);
    let width = b[2] - b[0];
    let height = b[3] - b[1];
    if width as usize * height as usize > MAX_STORED_PIXELS {
        return Err(limit(
            "Selection mask exceeds inline pixel limit; refine its bounds or retain the selection",
        ));
    }
    let mut pixels = Vec::with_capacity(width as usize * height as usize);
    for y in b[1]..b[3] {
        let start = (y * selection.width + b[0]) as usize;
        pixels.extend_from_slice(&source[start..start + width as usize]);
    }
    let position = [1.0, 0.0, 0.0, 1.0, b[0] as f64, b[1] as f64];
    let transform = if linked {
        geometry::relative_transform(scene::world_transform(document, index)?, &[position])?
    } else {
        position
    };
    document.items[index].mask = Some(Box::new(crate::masks::Mask {
        constant: false,
        width,
        height,
        gray_hex: render::hex(&pixels),
        transform,
        linked,
        enabled: true,
        clip: true,
        invert: false,
        density: 1.0,
        feather: 0,
        sampling: crate::assets::Sampling::Nearest,
    }));
    Ok(())
}

// Exact horizontal interval coverage, integrated over 256 subrows. Rectangles use exact area.
// All geometry stays f64; this does not depend on the drawing backend's edge quantization.
pub const COVERAGE_SUBROWS: u32 = 256;
fn coverage(
    boundary: &Boundary,
    width: u32,
    height: u32,
    antialias: bool,
    rule: FillRule,
) -> Result<Vec<u8>, Error> {
    let mut values = vec![0.0_f64; width as usize * height as usize];
    let g = boundary.geometry()?;
    let b = crate::geometry::bounds(&g, identity());
    let top = b[1].floor().clamp(0.0, height as f64) as u32;
    let bottom = b[3].ceil().clamp(0.0, height as f64) as u32;
    let left = b[0].floor().clamp(0.0, width as f64) as u32;
    let right = b[2].ceil().clamp(0.0, width as f64) as u32;
    if let Boundary::Rect {
        x,
        y,
        width: w,
        height: h,
    } = boundary
    {
        for py in top..bottom {
            for px in left..right {
                values[(py * width + px) as usize] = if antialias {
                    ((px as f64 + 1.0).min(x + w) - (px as f64).max(*x)).max(0.0)
                        * ((py as f64 + 1.0).min(y + h) - (py as f64).max(*y)).max(0.0)
                } else {
                    f64::from(
                        px as f64 + 0.5 >= *x
                            && px as f64 + 0.5 < x + w
                            && py as f64 + 0.5 >= *y
                            && py as f64 + 0.5 < y + h,
                    )
                };
            }
        }
    } else {
        let rows = if antialias { COVERAGE_SUBROWS } else { 1 };
        let edges = match boundary {
            Boundary::Polygon { points } => points.len() as u64,
            _ => 2,
        };
        let work = (bottom - top) as u64
            * rows as u64
            * ((right - left) as u64 + edges * (edges.ilog2() as u64 + 2));
        if work > MAX_WORK {
            return Err(limit("Selection subrow integration exceeds work budget"));
        }
        let mut crossings = Vec::with_capacity(edges as usize);
        for py in top..bottom {
            let row = &mut values[(py * width) as usize..((py + 1) * width) as usize];
            for sub in 0..rows {
                let y = py as f64 + (sub as f64 + 0.5) / rows as f64;
                let mut span = |a: f64, b: f64| {
                    let a = a.max(0.0);
                    let b = b.min(width as f64);
                    if b <= a {
                        return;
                    }
                    for (x, value) in row
                        .iter_mut()
                        .enumerate()
                        .take(b.ceil() as usize)
                        .skip(a.floor() as usize)
                    {
                        let amount = if antialias {
                            ((x as f64 + 1.0).min(b) - (x as f64).max(a)).max(0.0)
                        } else {
                            f64::from(x as f64 + 0.5 >= a && x as f64 + 0.5 < b)
                        };
                        *value += amount / rows as f64;
                    }
                };
                match boundary {
                    Boundary::Ellipse { cx, cy, rx, ry } => {
                        let t = 1.0 - ((y - cy) / ry).powi(2);
                        if t > 0.0 {
                            let r = rx * t.sqrt();
                            span(cx - r, cx + r);
                        }
                    }
                    Boundary::Polygon { points } => {
                        crossings.clear();
                        for (a, b) in points
                            .iter()
                            .zip(points.iter().cycle().skip(1))
                            .take(points.len())
                        {
                            if (a[1] <= y && y < b[1]) || (b[1] <= y && y < a[1]) {
                                crossings.push((
                                    a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1]),
                                    if b[1] > a[1] { 1 } else { -1 },
                                ));
                            }
                        }
                        crossings.sort_by(|a, b| a.0.total_cmp(&b.0));
                        let mut winding = 0i32;
                        let mut previous = 0.0;
                        for &(x, delta) in &crossings {
                            if match rule {
                                FillRule::Nonzero => winding != 0,
                                FillRule::EvenOdd => winding % 2 != 0,
                            } {
                                span(previous, x);
                            }
                            winding += delta;
                            previous = x;
                        }
                    }
                    _ => unreachable!(),
                }
            }
        }
    }
    Ok(values
        .into_iter()
        .map(|v| (v.clamp(0.0, 1.0) * 255.0).round() as u8)
        .collect())
}
