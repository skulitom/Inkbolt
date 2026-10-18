//! Row-streamed selection authoring with bounded private output blocks.
use super::storage::{SourceRows, generate};
use super::*;
use std::collections::VecDeque;

pub(super) fn needed(document: &Document) -> bool {
    document.width as u64 * document.height as u64 > MAX_PIXELS
        || document
            .selection
            .as_ref()
            .is_some_and(|s| s.native.is_some())
}
pub(super) fn fill(
    document: &mut Document,
    selected: bool,
    root: Option<&Path>,
    control: &Control,
) -> Result<(), Error> {
    document.selection = Some(generate(
        document.width,
        document.height,
        document.selection.as_ref(),
        root,
        control,
        |_, row| {
            row.fill(if selected { 255 } else { 0 });
            Ok(())
        },
    )?);
    Ok(())
}
pub(super) fn shape(
    document: &mut Document,
    boundary: &Boundary,
    combine: Combine,
    antialias: bool,
    rule: FillRule,
    root: Option<&Path>,
    control: &Control,
) -> Result<(), Error> {
    let mut raster = super::coverage::Rasterizer::new(
        boundary,
        document.width,
        document.height,
        antialias,
        rule,
        crate::limits::selections::MAX_NATIVE_WORK,
    )?;
    let mut old = if matches!(combine, Combine::Replace) {
        None
    } else {
        Some(SourceRows::new(active(document)?, root, control)?)
    };
    let mut prior = vec![0; document.width as usize];
    document.selection = Some(generate(
        document.width,
        document.height,
        document.selection.as_ref(),
        root,
        control,
        |y, row| {
            raster.read(y, row)?;
            if let Some(source) = &mut old {
                source.read(y, &mut prior, control)?;
                for (a, b) in row.iter_mut().zip(&prior) {
                    *a = combine_byte(*b, *a, combine);
                }
            }
            Ok(())
        },
    )?);
    Ok(())
}
pub(super) fn combine_byte(a: u8, b: u8, combine: Combine) -> u8 {
    match combine {
        Combine::Replace => b,
        Combine::Add => a.max(b),
        Combine::Subtract => a.saturating_sub(b),
        Combine::Intersect => a.min(b),
    }
}
pub(super) fn invert(
    document: &mut Document,
    root: Option<&Path>,
    control: &Control,
) -> Result<(), Error> {
    let s = active(document)?;
    let mut source = SourceRows::new(s, root, control)?;
    document.selection = Some(generate(
        s.width,
        s.height,
        Some(s),
        root,
        control,
        |y, row| {
            source.read(y, row, control)?;
            for v in row {
                *v = 255 - *v;
            }
            Ok(())
        },
    )?);
    Ok(())
}
pub(super) fn refine(
    document: &mut Document,
    mode: Refine,
    radius: u32,
    root: Option<&Path>,
    control: &Control,
) -> Result<(), Error> {
    let s = active(document)?;
    if radius > MAX_RADIUS {
        return Err(invalid(
            "Selection refinement radius exceeds its declared limit",
        ));
    }
    let work = s.width as u64 * s.height as u64 * 2 * (2 * radius as u64 + 1);
    if work > crate::limits::selections::MAX_NATIVE_WORK {
        return Err(limit("Native selection refinement exceeds work budget"));
    }
    let mut source = SourceRows::new(s, root, control)?;
    let mut raw = vec![0; s.width as usize];
    let mut rows: VecDeque<(u32, Vec<f64>)> = VecDeque::new();
    let r = radius as i64;
    let divisor = ((r + 1) * (r + 1)) as f64;
    let initial = || {
        if matches!(mode, Refine::Contract) {
            255.0f64
        } else {
            0.0f64
        }
    };
    let accumulate = |value: f64, next: f64, d: i64| match mode {
        Refine::Expand => value.max(next),
        Refine::Contract => value.min(next),
        Refine::Feather => value + next * (r + 1 - d.abs()) as f64,
    };
    let finish = |value: f64| {
        if matches!(mode, Refine::Feather) {
            value / divisor
        } else {
            value
        }
    };
    let mut next_row = 0;
    document.selection = Some(generate(
        s.width,
        s.height,
        Some(s),
        root,
        control,
        |y, output| {
            let low = y.saturating_sub(radius);
            while rows.front().is_some_and(|(row, _)| *row < low) {
                rows.pop_front();
            }
            let high = y.saturating_add(radius).min(s.height - 1);
            while next_row <= high {
                source.read(next_row, &mut raw, control)?;
                let mut horizontal = vec![0.0; raw.len()];
                for (x, value) in horizontal.iter_mut().enumerate() {
                    *value = initial();
                    for d in -r..=r {
                        let sx = x as i64 + d;
                        let next = if sx >= 0 && sx < s.width as i64 {
                            raw[sx as usize] as f64
                        } else {
                            0.0
                        };
                        *value = accumulate(*value, next, d);
                    }
                    *value = finish(*value);
                }
                rows.push_back((next_row, horizontal));
                next_row += 1;
            }
            for (x, out) in output.iter_mut().enumerate() {
                let mut value = initial();
                for d in -r..=r {
                    let sy = y as i64 + d;
                    let next = if sy >= 0 && sy < s.height as i64 {
                        rows[(sy as u32 - low) as usize].1[x]
                    } else {
                        0.0
                    };
                    value = accumulate(value, next, d);
                }
                *out = finish(value).clamp(0.0, 255.0).round() as u8;
            }
            Ok(())
        },
    )?);
    Ok(())
}
