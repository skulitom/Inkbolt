//! Exact integer-weighted measurements of the exported scale-one RGBA8 composite.
use crate::{Error, model::*, render};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::path::Path;
pub const MAX_SAMPLES: usize = 256;
pub const WEIGHT_DENOMINATOR: u64 = 65025;
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Alpha {
    #[default]
    Ignore,
    ExcludeTransparent,
    Weight,
}
#[derive(Clone, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Options {
    pub region: Option<crate::edit::PixelRect>,
    #[serde(default)]
    pub use_selection: bool,
    #[serde(default)]
    pub alpha: Alpha,
    #[serde(default)]
    pub samples: Vec<[u32; 2]>,
}
pub fn measure(
    document: &Document,
    options: &Options,
    asset_root: Option<&Path>,
    font_root: Option<&Path>,
) -> Result<Value, Error> {
    validate(document)?;
    let region = options.region.clone().unwrap_or(crate::edit::PixelRect {
        x: 0,
        y: 0,
        width: document.width,
        height: document.height,
    });
    if region.width == 0
        || region.height == 0
        || region.x as u64 + region.width as u64 > document.width as u64
        || region.y as u64 + region.height as u64 > document.height as u64
    {
        return Err(Error::new(
            "INVALID_REQUEST",
            "Measurement region must be nonempty and inside the canvas",
        ));
    }
    if options.samples.len() > MAX_SAMPLES
        || options.samples.iter().any(|[x, y]| {
            *x < region.x
                || *y < region.y
                || *x >= region.x + region.width
                || *y >= region.y + region.height
        })
    {
        return Err(Error::new(
            "INVALID_REQUEST",
            "Measurement samples require at most 256 pixel coordinates inside the region",
        ));
    }
    let selection = if options.use_selection {
        Some(render::unhex(
            &document
                .selection
                .as_ref()
                .ok_or_else(|| {
                    Error::new(
                        "INVALID_REQUEST",
                        "Selection-weighted measurements require an active pixel selection",
                    )
                })?
                .gray_hex,
        ))
    } else {
        None
    };
    let image = render::rasterize_with_resources(document, 1, asset_root, font_root)?;
    let coverage = |n: usize| selection.as_ref().map_or(255, |s| s[n]);
    let weight = |n: usize, a: u8| {
        coverage(n) as u64
            * match options.alpha {
                Alpha::Ignore => 255,
                Alpha::ExcludeTransparent => {
                    if a == 0 {
                        0
                    } else {
                        255
                    }
                }
                Alpha::Weight => a as u64,
            }
    };
    let mut histograms = vec![vec![0u64; 256]; 4];
    let mut total = 0u64;
    let mut included = 0u64;
    let mut sums = [0u64; 4];
    let mut squares = [0u64; 4];
    for y in region.y..region.y + region.height {
        for x in region.x..region.x + region.width {
            let n = (y * image.width + x) as usize;
            let pixel = &image.rgba[n * 4..n * 4 + 4];
            let w = weight(n, pixel[3]);
            total += w;
            included += u64::from(w > 0);
            for c in 0..4 {
                let value = pixel[c] as u64;
                histograms[c][value as usize] += w;
                sums[c] += value * w;
                squares[c] += value * value * w;
            }
        }
    }
    let channels:Vec<Value>=(0..4).map(|c|json!({
        "name":(["red","green","blue","alpha"][c]),"histogram_weight_units":histograms[c],
        "sum_weighted_values":sums[c],"sum_weighted_squares":squares[c],
        "minimum":histograms[c].iter().position(|&n|n>0),"maximum":histograms[c].iter().rposition(|&n|n>0),
        "mean":if total==0{None}else{Some(sums[c] as f64/total as f64)},
        "variance":if total==0{None}else{Some((squares[c] as f64/total as f64-(sums[c] as f64/total as f64).powi(2)).max(0.0))},
    })).collect();
    let samples:Vec<Value>=options.samples.iter().map(|&[x,y]|{
        let n=(y*image.width+x) as usize;let rgba=&image.rgba[n*4..n*4+4];json!({"position":[x,y],"rgba":rgba,"selection_coverage":coverage(n),"weight_units":weight(n,rgba[3])})
    }).collect();
    Ok(
        json!({"document_id":document.id,"revision":document.revision,"width":image.width,"height":image.height,"region":region,"depth":8,"color_space":"srgb","source":"rendered_composite_scale_one","alpha_policy":options.alpha,"use_selection":options.use_selection,"pixel_count":region.width as u64*region.height as u64,"included_pixel_count":included,"weight_denominator":WEIGHT_DENOMINATOR,"total_weight_units":total,"effective_pixel_count":total as f64/WEIGHT_DENOMINATOR as f64,"channels":channels,"samples":samples,"semantics":"Straight RGBA8 after final output quantization; zero-alpha RGB is canonical zero. Each histogram counts exact integer selection*alpha units with denominator 65025. Samples and region use canvas pixel indices; no source or snapshot mutation. Higher-depth inputs require an explicit supported conversion and are not silently accepted."}),
    )
}
