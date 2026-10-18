//! Persistent scalar pixel selections in document coordinates; no rendering side effects.
use crate::control::Control;
use crate::{Error, geometry, model::*, render, scene};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::path::Path;

mod coverage;
mod native;
pub(crate) mod storage;
#[cfg(test)]
mod tests;
pub(crate) use storage::{Prepared, dense, selection_memory};

pub use crate::limits::selections::MAX_PIXELS;
pub use crate::limits::selections::MAX_POLYGON_POINTS;
pub use crate::limits::selections::MAX_RADIUS;
pub use crate::limits::selections::MAX_WORK;

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Selection {
    pub width: u32,
    pub height: u32,
    pub gray_hex: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub native: Option<crate::stored_scalars::Grid>,
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
                    return Err(invalid(&format!(
                        "Selection polygon requires 3..={MAX_POLYGON_POINTS} points"
                    )));
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
    if let Some(grid) = &selection.native {
        grid.validate()?;
        if (selection.width, selection.height) != (width, height)
            || (grid.base.spec.width, grid.base.spec.height) != (width, height)
            || !selection.gray_hex.is_empty()
        {
            return Err(invalid(
                "Native selection requires canvas-sized scalar storage and empty gray_hex",
            ));
        }
        return Ok(());
    }
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
        return Err(invalid(&format!(
            "Selection dimensions must be in 1..={MAX_DIMENSION}"
        )));
    }
    let n = width as u64 * height as u64;
    if n > MAX_PIXELS {
        return Err(limit(&format!(
            "Pixel selection exceeds {MAX_PIXELS} pixels"
        )));
    }
    Ok(n as usize)
}
fn active(document: &Document) -> Result<&Selection, Error> {
    document.selection.as_ref().ok_or_else(|| Error::new("INVALID_OPERATION","This operation requires an active pixel selection, including an explicit empty or full selection"))
}
fn inline_fill(document: &mut Document, selected: bool) -> Result<(), Error> {
    let n = check_size(document.width, document.height)?;
    document.selection = Some(Selection {
        native: None,
        width: document.width,
        height: document.height,
        gray_hex: if selected { "ff" } else { "00" }.repeat(n),
    });
    Ok(())
}
fn inline_shape(
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
    inline_combine_values(document, mask, combine)
}
fn inline_combine_values(
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
        native: None,
        width: document.width,
        height: document.height,
        gray_hex: render::hex(&values),
    });
    Ok(())
}
fn inline_invert(document: &mut Document) -> Result<(), Error> {
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
fn inline_refine(document: &mut Document, mode: Refine, radius: u32) -> Result<(), Error> {
    let selection = active(document)?;
    if radius > MAX_RADIUS {
        return Err(invalid(&format!(
            "Selection refinement radius must be in 0..={MAX_RADIUS} pixels"
        )));
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
    if let Some(grid) = &s.native {
        return json!({"width":s.width,"height":s.height,"storage":"native_scalar_blocks",
            "native_sha256":grid.base.sha256,"coordinates":"document_pixel_grid",
            "statistics":null,"statistics_availability":"resource_aware_document_inspect"});
    }
    let bytes = render::unhex(&s.gray_hex);
    json!({"width":s.width,"height":s.height,"bounds":bounds(s.width,s.height,&bytes),"selected_pixels":bytes.iter().filter(|&&v|v!=0).count(),"fully_selected_pixels":bytes.iter().filter(|&&v|v==255).count(),"coverage_sum":bytes.iter().map(|&v|v as u64).sum::<u64>() as f64/255.0,"sha256":crate::assets::sha256(&bytes),"coordinates":"document_pixel_grid","bounds_contract":"nonzero_end_exclusive"})
}
pub fn to_mask(
    document: &mut Document,
    index: usize,
    linked: bool,
    replace_existing: bool,
) -> Result<(), Error> {
    to_mask_controlled(
        document,
        index,
        linked,
        replace_existing,
        &Control::default(),
    )
}
pub(crate) fn to_mask_controlled(
    document: &mut Document,
    index: usize,
    linked: bool,
    replace_existing: bool,
    control: &Control,
) -> Result<(), Error> {
    control.check()?;
    if document.items[index].mask.is_some() && !replace_existing {
        return Err(Error::new(
            "INVALID_OPERATION",
            "Item already has a mask; explicitly set replace_existing to replace it",
        ));
    }
    let selection = active(document)?;
    if let Some(grid) = &selection.native {
        let transform = if linked {
            geometry::relative_transform(scene::world_transform(document, index)?, &[identity()])?
        } else {
            identity()
        };
        document.items[index].mask = Some(Box::new(crate::masks::Mask {
            native: Some(grid.clone()),
            constant: false,
            width: selection.width,
            height: selection.height,
            gray_hex: String::new(),
            transform,
            linked,
            enabled: true,
            clip: true,
            invert: false,
            density: 1.0,
            feather: 0,
            sampling: crate::assets::Sampling::Nearest,
        }));
        return Ok(());
    }
    let source = render::unhex(&selection.gray_hex);
    let b = bounds(selection.width, selection.height, &source).unwrap_or([0, 0, 1, 1]);
    let width = b[2] - b[0];
    let height = b[3] - b[1];
    let (native, gray_hex) = if width as usize * height as usize > MAX_STORED_PIXELS {
        let grid = storage::generate(width, height, None, None, control, |y, row| {
            let start = ((y + b[1]) * selection.width + b[0]) as usize;
            row.copy_from_slice(&source[start..start + width as usize]);
            Ok(())
        })?;
        (grid.native, String::new())
    } else {
        let mut pixels = Vec::with_capacity(width as usize * height as usize);
        for y in b[1]..b[3] {
            let start = (y * selection.width + b[0]) as usize;
            pixels.extend_from_slice(&source[start..start + width as usize]);
        }
        (None, render::hex(&pixels))
    };
    let position = [1.0, 0.0, 0.0, 1.0, b[0] as f64, b[1] as f64];
    let transform = if linked {
        geometry::relative_transform(scene::world_transform(document, index)?, &[position])?
    } else {
        position
    };
    document.items[index].mask = Some(Box::new(crate::masks::Mask {
        native,
        constant: false,
        width,
        height,
        gray_hex,
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
pub use crate::limits::selections::COVERAGE_SUBROWS;
fn coverage(
    boundary: &Boundary,
    width: u32,
    height: u32,
    antialias: bool,
    rule: FillRule,
) -> Result<Vec<u8>, Error> {
    let mut raster = coverage::Rasterizer::new(boundary, width, height, antialias, rule, MAX_WORK)?;
    let mut result = vec![0; width as usize * height as usize];
    for (y, row) in result.chunks_mut(width as usize).enumerate() {
        raster.read(y as u32, row)?;
    }
    Ok(result)
}

pub fn fill(document: &mut Document, selected: bool) -> Result<(), Error> {
    fill_with_resources(document, selected, None, &Control::default())
}
pub fn fill_with_resources(
    document: &mut Document,
    selected: bool,
    root: Option<&Path>,
    control: &Control,
) -> Result<(), Error> {
    control.check()?;
    if native::needed(document) {
        native::fill(document, selected, root, control)
    } else {
        inline_fill(document, selected)
    }
}
pub fn shape(
    document: &mut Document,
    boundary: &Boundary,
    combine: Combine,
    antialias: bool,
    rule: FillRule,
) -> Result<(), Error> {
    shape_with_resources(
        document,
        boundary,
        combine,
        antialias,
        rule,
        None,
        &Control::default(),
    )
}
pub fn shape_with_resources(
    document: &mut Document,
    boundary: &Boundary,
    combine: Combine,
    antialias: bool,
    rule: FillRule,
    root: Option<&Path>,
    control: &Control,
) -> Result<(), Error> {
    control.check()?;
    if native::needed(document) {
        native::shape(document, boundary, combine, antialias, rule, root, control)
    } else {
        inline_shape(document, boundary, combine, antialias, rule)
    }
}
pub fn invert(document: &mut Document) -> Result<(), Error> {
    invert_with_resources(document, None, &Control::default())
}
pub fn invert_with_resources(
    document: &mut Document,
    root: Option<&Path>,
    control: &Control,
) -> Result<(), Error> {
    control.check()?;
    if active(document)?.native.is_some() {
        native::invert(document, root, control)
    } else {
        inline_invert(document)
    }
}
pub fn refine(document: &mut Document, mode: Refine, radius: u32) -> Result<(), Error> {
    refine_with_resources(document, mode, radius, None, &Control::default())
}
pub fn refine_with_resources(
    document: &mut Document,
    mode: Refine,
    radius: u32,
    root: Option<&Path>,
    control: &Control,
) -> Result<(), Error> {
    control.check()?;
    if active(document)?.native.is_some() {
        native::refine(document, mode, radius, root, control)
    } else {
        inline_refine(document, mode, radius)
    }
}
pub fn inspect_with_resources(
    selection: Option<&Selection>,
    root: Option<&Path>,
    control: &Control,
) -> Result<Value, Error> {
    control.check()?;
    match selection {
        Some(s) if s.native.is_some() => storage::inspect(s, root, control),
        _ => Ok(inspect(selection)),
    }
}

pub(crate) fn combine_values(
    document: &mut Document,
    mask: Vec<u8>,
    combine: Combine,
    root: Option<&Path>,
    control: &Control,
) -> Result<(), Error> {
    if mask.len() != check_size(document.width, document.height)? {
        return Err(invalid("Selection operand must match the canvas"));
    }
    if !native::needed(document) {
        return inline_combine_values(document, mask, combine);
    }
    let mut source = if matches!(combine, Combine::Replace) {
        None
    } else {
        Some(storage::SourceRows::new(active(document)?, root, control)?)
    };
    let mut old = vec![0; document.width as usize];
    let width = document.width as usize;
    document.selection = Some(storage::generate(
        document.width,
        document.height,
        document.selection.as_ref(),
        root,
        control,
        |y, row| {
            if let Some(source) = &mut source {
                source.read(y, &mut old, control)?;
            }
            for (x, out) in row.iter_mut().enumerate() {
                *out = native::combine_byte(old[x], mask[y as usize * width + x], combine);
            }
            Ok(())
        },
    )?);
    Ok(())
}
