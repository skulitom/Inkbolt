//! Original color-distance selections, bounded connectivity and image-guided edge refinement.
use crate::{Error, model::*, render, selections};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use std::{collections::VecDeque, path::Path};
pub const MAX_TARGETS: usize = 32;
pub const MAX_EDGE_RADIUS: u32 = 8;
fn white() -> u8 {
    255
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Components {
    Rgb,
    #[default]
    Rgba,
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Connectivity {
    #[default]
    Four,
    Eight,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Method {
    ColorRange {
        colors: Vec<Color>,
        tolerance: u8,
        #[serde(default)]
        feather: u8,
        #[serde(default)]
        components: Components,
    },
    Connected {
        seeds: Vec<[u32; 2]>,
        tolerance: u8,
        #[serde(default)]
        feather: u8,
        #[serde(default)]
        components: Components,
        #[serde(default)]
        connectivity: Connectivity,
    },
    Edge {
        radius: u32,
        tolerance: u8,
        #[serde(default)]
        components: Components,
        #[serde(default)]
        black: u8,
        #[serde(default = "white")]
        white: u8,
    },
}
fn distance(a: &Color, b: &Color, components: Components) -> u8 {
    (0..if matches!(components, Components::Rgb) {
        3
    } else {
        4
    })
        .map(|c| a[c].abs_diff(b[c]))
        .max()
        .unwrap()
}
fn coverage(d: u8, tolerance: u8, feather: u8) -> u8 {
    if d <= tolerance {
        255
    } else if feather == 0 || d as u32 >= tolerance as u32 + feather as u32 {
        0
    } else {
        (((tolerance as u32 + feather as u32 - d as u32) * 255 + feather as u32 / 2)
            / feather as u32) as u8
    }
}
pub fn evaluate(
    document: &Document,
    method: &Method,
    asset_root: Option<&Path>,
    font_root: Option<&Path>,
) -> Result<Vec<u8>, Error> {
    let n = selections::check_size(document.width, document.height)?;
    let w = document.width as usize;
    let h = document.height as usize;
    let work = match method {
        Method::ColorRange { colors, .. } => {
            if !(1..=MAX_TARGETS).contains(&colors.len()) {
                return Err(invalid("Color range requires 1..=32 colors"));
            }
            n as u64 * colors.len() as u64 * 4
        }
        Method::Connected { seeds, .. } => {
            if !(1..=MAX_TARGETS).contains(&seeds.len())
                || seeds
                    .iter()
                    .any(|p| p[0] >= document.width || p[1] >= document.height)
            {
                return Err(invalid(
                    "Connected selection requires 1..=32 canvas pixel seeds",
                ));
            }
            n as u64 * (seeds.len() as u64 * 4 + 8)
        }
        Method::Edge {
            radius,
            black,
            white,
            ..
        } => {
            if *radius > MAX_EDGE_RADIUS || black >= white {
                return Err(invalid(
                    "Edge radius must be in 0..=8 and black below white",
                ));
            }
            if document.selection.is_none() {
                return Err(Error::new(
                    "INVALID_OPERATION",
                    "Edge refinement requires an active selection",
                ));
            }
            n as u64 * (2 * (*radius as u64) + 1).pow(2) * 4
        }
    };
    if work > selections::MAX_WORK {
        return Err(limit("Image-guided selection exceeds work budget"));
    }
    let image = render::rasterize_with_resources(document, 1, asset_root, font_root)?;
    let pixels = image.rgba.as_chunks::<4>().0;
    if let Method::Edge {
        radius,
        tolerance,
        components,
        black,
        white,
    } = *method
    {
        let old = render::unhex(&document.selection.as_ref().unwrap().gray_hex);
        let r = radius as i64;
        let mut out = vec![0; n];
        for y in 0..h {
            for x in 0..w {
                let i = y * w + x;
                let mut sum = 0u64;
                let mut total = 0u64;
                for dy in -r..=r {
                    for dx in -r..=r {
                        let sx = x as i64 + dx;
                        let sy = y as i64 + dy;
                        if sx < 0 || sy < 0 || sx >= w as i64 || sy >= h as i64 {
                            continue;
                        }
                        let j = sy as usize * w + sx as usize;
                        if distance(&pixels[i], &pixels[j], components) <= tolerance {
                            let weight = ((r + 1 - dx.abs()) * (r + 1 - dy.abs())) as u64;
                            sum += old[j] as u64 * weight;
                            total += weight;
                        }
                    }
                }
                let numerator = sum.saturating_sub(black as u64 * total);
                let denominator = (white - black) as u64 * total;
                out[i] = ((numerator * 255 + denominator / 2) / denominator).min(255) as u8;
            }
        }
        return Ok(out);
    }
    let (colors, tolerance, feather, components) = match method {
        Method::ColorRange {
            colors,
            tolerance,
            feather,
            components,
        } => (colors.clone(), *tolerance, *feather, *components),
        Method::Connected {
            seeds,
            tolerance,
            feather,
            components,
            ..
        } => (
            seeds
                .iter()
                .map(|p| pixels[p[1] as usize * w + p[0] as usize])
                .collect(),
            *tolerance,
            *feather,
            *components,
        ),
        _ => unreachable!(),
    };
    let candidate: Vec<_> = pixels
        .iter()
        .map(|p| {
            coverage(
                colors
                    .iter()
                    .map(|c| distance(p, c, components))
                    .min()
                    .unwrap(),
                tolerance,
                feather,
            )
        })
        .collect();
    if let Method::Connected {
        seeds,
        connectivity,
        ..
    } = method
    {
        let mut visited = vec![false; n];
        let mut queue = VecDeque::new();
        let mut out = vec![0; n];
        for seed in seeds {
            let i = seed[1] as usize * w + seed[0] as usize;
            if !visited[i] {
                visited[i] = true;
                queue.push_back(i);
            }
        }
        while let Some(i) = queue.pop_front() {
            out[i] = candidate[i];
            let x = (i % w) as i64;
            let y = (i / w) as i64;
            for dy in -1_i64..=1 {
                for dx in -1_i64..=1 {
                    if (dx == 0 && dy == 0)
                        || (matches!(connectivity, Connectivity::Four) && dx != 0 && dy != 0)
                    {
                        continue;
                    }
                    let sx = x + dx;
                    let sy = y + dy;
                    if sx < 0 || sy < 0 || sx >= w as i64 || sy >= h as i64 {
                        continue;
                    }
                    let j = sy as usize * w + sx as usize;
                    if !visited[j] && candidate[j] > 0 {
                        visited[j] = true;
                        queue.push_back(j);
                    }
                }
            }
        }
        Ok(out)
    } else {
        Ok(candidate)
    }
}
