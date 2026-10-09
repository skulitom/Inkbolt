//! Explicit delivery sampling and bounded effect evaluation over immutable scenes.
use crate::{Error, model::*, render::Rasterized};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::borrow::Cow;

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Antialias {
    None,
    #[default]
    Coverage,
    Supersample2,
    Supersample4,
}
impl Antialias {
    pub fn factor(self) -> u32 {
        match self {
            Self::Supersample2 => 2,
            Self::Supersample4 => 4,
            _ => 1,
        }
    }
    pub fn coverage(self) -> bool {
        !matches!(self, Self::None)
    }
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum AveragingSpace {
    #[default]
    EncodedSrgb,
    LinearSrgb,
}
fn yes() -> bool {
    true
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Evaluation {
    #[default]
    Whole,
    Tiled,
}
impl Evaluation {
    fn is_whole(&self) -> bool {
        *self == Self::Whole
    }
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(default, deny_unknown_fields)]
pub struct Options {
    #[serde(skip_serializing_if = "Evaluation::is_whole")]
    pub evaluation: Evaluation,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub view: Option<crate::hdr::View>,
    pub antialias: Antialias,
    pub averaging_space: AveragingSpace,
    pub padding: u32,
    #[serde(default = "yes")]
    pub crop_to_canvas: bool,
}
impl Default for Options {
    fn default() -> Self {
        Self {
            evaluation: Evaluation::Whole,
            view: None,
            antialias: Antialias::Coverage,
            averaging_space: AveragingSpace::EncodedSrgb,
            padding: 0,
            crop_to_canvas: true,
        }
    }
}
pub(crate) struct Plan {
    pub canvas: Option<crate::vector_canvas::Canvas>,
    pub logical_size: [f64; 2],
    pub linear: bool,
    pub options: Options,
    pub scale: u32,
    pub internal_scale: u32,
    pub evaluation: [u32; 2],
    pub output: [u32; 2],
    pub offset: u32,
}
impl Plan {
    pub fn for_document(
        document: &Document,
        scale: u32,
        options: Option<&Options>,
    ) -> Result<Self, Error> {
        let mut plan = Self::new(document.width, document.height, scale, options)?;
        plan.canvas = document.vector_canvas;
        plan.logical_size = crate::vector_canvas::logical_size(document);
        if plan.canvas.is_some() && plan.options.crop_to_canvas {
            plan.output = plan.logical_size.map(|v| (v * scale as f64).ceil() as u32);
        }
        plan.linear = crate::hdr::linear(document);
        if let Some(view) = plan.options.view {
            view.validate()?;
            if !plan.linear {
                return Err(Error::new(
                    "INVALID_REQUEST",
                    "An HDR view requires linear_srgb document compositing",
                ));
            }
        }
        Ok(plan)
    }
    pub fn new(
        width: u32,
        height: u32,
        scale: u32,
        options: Option<&Options>,
    ) -> Result<Self, Error> {
        let options = options.copied().unwrap_or_default();
        if let Some(view) = options.view {
            view.validate()?;
        }
        if !(1..=4).contains(&scale) || options.padding > 256 {
            return Err(Error::new(
                "INVALID_REQUEST",
                "Render scale must be 1..=4 and effect padding 0..=256 document units",
            ));
        }
        if matches!(options.averaging_space, AveragingSpace::LinearSrgb)
            && options.antialias.factor() == 1
        {
            return Err(Error::new(
                "INVALID_REQUEST",
                "Linear-light averaging requires supersampling; it does not change scene compositing",
            ));
        }
        let evaluation = [width, height].map(|v| v + 2 * options.padding);
        if evaluation.iter().any(|&v| v == 0 || v > MAX_DIMENSION) {
            return Err(limit("Padded render dimensions exceed 32768"));
        }
        let internal_scale = scale * options.antialias.factor();
        if evaluation[0] as u64 * evaluation[1] as u64 * (internal_scale as u64).pow(2)
            > if options.evaluation == Evaluation::Tiled {
                crate::render::tiled::MAX_PIXELS
            } else {
                crate::render::MAX_RENDER_PIXELS
            }
        {
            return Err(limit(
                "Render evaluation including padding and supersampling exceeds pixel limit",
            ));
        }
        let output = if options.crop_to_canvas {
            [width, height]
        } else {
            evaluation
        }
        .map(|v| v * scale);
        let offset = if options.crop_to_canvas {
            options.padding * internal_scale
        } else {
            0
        };
        Ok(Self {
            canvas: None,
            logical_size: [width as f64, height as f64],
            linear: false,
            options,
            scale,
            internal_scale,
            evaluation,
            output,
            offset,
        })
    }
    pub fn receipt(&self) -> Value {
        let mut value = json!({"antialias":self.options.antialias,"averaging_space":if self.linear {json!("linear_srgb")}else{json!(self.options.averaging_space)},
            "padding":self.options.padding,"crop_to_canvas":self.options.crop_to_canvas,
            "scale":self.scale,"internal_scale":self.internal_scale,
            "evaluation_dimensions":self.evaluation.map(|v|v*self.internal_scale),
            "output_dimensions":self.output,
            "origin":if self.options.crop_to_canvas {[0i64;2]}else{[-(self.options.padding as i64);2]},
            "compositing_space":if self.linear {"linear_srgb"}else{"encoded_srgb"},"view":self.options.view,"source_changed":false});
        if self.options.evaluation == Evaluation::Tiled {
            value["evaluation"] = json!("tiled");
            value["evaluation_tile_edge"] = json!(crate::render::tiled::EDGE);
            value["evaluation_neighborhood_units"] =
                json!(crate::render::traversal::NEIGHBORHOOD_UNITS);
            value["evaluation_tile_policy"] =
                json!("maximum_128;8_for_at_least_128_expanded_items");
        }
        if let Some(canvas) = self.canvas {
            value["vector_canvas"] = json!(canvas);
            value["logical_size"] = json!(self.logical_size);
            value["origin"] = json!(
                canvas
                    .origin_px
                    .map(|v| v - if self.options.crop_to_canvas {
                        0.0
                    } else {
                        self.options.padding as f64
                    })
            );
        }
        value
    }
    pub fn prepare<'a>(&self, document: &'a Document) -> Result<Cow<'a, Document>, Error> {
        if self.options.padding == 0 && self.canvas.is_none() {
            return Ok(Cow::Borrowed(document));
        }
        let origin = self.canvas.map_or([0.0; 2], |c| c.origin_px);
        let p = self.options.padding as f64;
        let mut copy = crate::vector_canvas::translated(document, [p - origin[0], p - origin[1]])?;
        copy.variants = None;
        copy.selection = None;
        copy.channels.clear();
        [copy.width, copy.height] = self.evaluation;
        crate::validate(&copy)?;
        Ok(Cow::Owned(copy))
    }
    /// Exact rectangular area of each evaluation cell inside the logical canvas.
    pub(crate) fn canvas_weight(&self, x: u32, y: u32) -> f64 {
        if self.canvas.is_none() || !self.options.crop_to_canvas {
            return 1.0;
        }
        let scale = self.internal_scale as f64;
        let pad = self.options.padding as f64 * scale;
        let lo = [x as f64 - pad, y as f64 - pad];
        let extent = self.logical_size.map(|v| v * scale);
        if matches!(self.options.antialias, Antialias::None) {
            return f64::from((0..2).all(|i| lo[i] + 0.5 >= 0.0 && lo[i] + 0.5 < extent[i]));
        }
        (0..2)
            .map(|i| ((lo[i] + 1.0).min(extent[i]) - lo[i].max(0.0)).max(0.0))
            .product::<f64>()
            .clamp(0.0, 1.0)
    }
    /// Average completed associated samples before the requested output depth.
    fn visit_samples(&self, accum: &[f64], width: u32, mut push: impl FnMut([f64; 4])) {
        self.visit_region(accum, width, [0; 2], [0; 2], self.output, &mut push)
    }
    pub(crate) fn visit_region(
        &self,
        accum: &[f64],
        width: u32,
        evaluation_origin: [u32; 2],
        output_origin: [u32; 2],
        output_size: [u32; 2],
        mut push: impl FnMut([f64; 4]),
    ) {
        let factor = self.options.antialias.factor();
        let linear =
            !self.linear && matches!(self.options.averaging_space, AveragingSpace::LinearSrgb);
        for y in output_origin[1]..output_origin[1] + output_size[1] {
            for x in output_origin[0]..output_origin[0] + output_size[0] {
                let mut sum = [0.0; 4];
                for sy in 0..factor {
                    for sx in 0..factor {
                        let at = (((self.offset + y * factor + sy - evaluation_origin[1])
                            as usize
                            * width as usize)
                            + (self.offset + x * factor + sx - evaluation_origin[0]) as usize)
                            * 4;
                        let p = &accum[at..at + 4];
                        let weight = self.canvas_weight(
                            self.offset + x * factor + sx,
                            self.offset + y * factor + sy,
                        );
                        for c in 0..3 {
                            sum[c] += weight
                                * if linear && p[3] > 0.0 {
                                    decode((p[c] / p[3]).clamp(0.0, 1.0)) * p[3]
                                } else {
                                    p[c]
                                };
                        }
                        sum[3] += p[3] * weight;
                    }
                }
                let a = sum[3] / (factor * factor) as f64;
                let mut sample = if a <= 0.0 {
                    [0.0; 4]
                } else {
                    [
                        if linear {
                            encode(sum[0] / sum[3])
                        } else {
                            sum[0] / sum[3]
                        },
                        if linear {
                            encode(sum[1] / sum[3])
                        } else {
                            sum[1] / sum[3]
                        },
                        if linear {
                            encode(sum[2] / sum[3])
                        } else {
                            sum[2] / sum[3]
                        },
                        a,
                    ]
                };
                if !self.linear {
                    sample = sample.map(|v| v.clamp(0.0, 1.0));
                }
                sample[3] = sample[3].clamp(0.0, 1.0);
                if let Some(view) = self.options.view {
                    sample = view.project(sample);
                }
                push(sample);
            }
        }
    }
    pub fn finish(&self, accum: &[f64], width: u32) -> Rasterized {
        let mut rgba = Vec::with_capacity(self.output[0] as usize * self.output[1] as usize * 4);
        self.visit_samples(accum, width, |p| {
            let bytes = p.map(|v| (v * 255.0).round() as u8);
            rgba.extend_from_slice(if bytes[3] == 0 { &[0; 4] } else { &bytes });
        });
        Rasterized {
            width: self.output[0],
            height: self.output[1],
            rgba,
        }
    }
    pub fn finish_samples(&self, accum: &[f64], width: u32) -> crate::render::SampleRaster {
        let mut rgba = Vec::with_capacity(self.output[0] as usize * self.output[1] as usize * 4);
        self.visit_samples(accum, width, |p| rgba.extend_from_slice(&p));
        crate::render::SampleRaster {
            width: self.output[0],
            height: self.output[1],
            rgba,
        }
    }
}
fn decode(v: f64) -> f64 {
    if v <= 0.04045 {
        v / 12.92
    } else {
        ((v + 0.055) / 1.055).powf(2.4)
    }
}
fn encode(v: f64) -> f64 {
    if v <= 0.0031308 {
        v * 12.92
    } else {
        1.055 * v.powf(1.0 / 2.4) - 0.055
    }
}
pub fn validate_format(
    format: crate::ExportFormat,
    options: Option<&Options>,
) -> Result<(), Error> {
    if options.is_some()
        && !matches!(
            format,
            crate::ExportFormat::Png
                | crate::ExportFormat::Gif
                | crate::ExportFormat::Bmp
                | crate::ExportFormat::Tga
                | crate::ExportFormat::Apng
                | crate::ExportFormat::Jpeg
                | crate::ExportFormat::Tiff
        )
    {
        return Err(Error::new(
            "INVALID_REQUEST",
            "render_options requires an image delivery format",
        ));
    }
    Ok(())
}
