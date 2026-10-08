//! Original bounded tone operators over straight encoded sRGB, retaining source pixels.
use crate::{Error, model::*, scene};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

pub const MAX_OPERATORS: usize = 16;
pub const MAX_DOCUMENT_OPERATORS: usize = 256;
pub const MAX_CURVE_POINTS: usize = 64;
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Channel {
    #[default]
    Rgb,
    Red,
    Green,
    Blue,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Operator {
    Color {
        adjustment: Box<crate::color_adjustments::Adjustment>,
    },
    Invert {},
    Threshold {
        level: f64,
    },
    Levels {
        input: [f64; 2],
        gamma: f64,
        output: [f64; 2],
    },
    Posterize {
        levels: u16,
    },
    Curve {
        points: Vec<Point>,
        #[serde(default)]
        channel: Channel,
    },
    Exposure {
        stops: f64,
        #[serde(default)]
        offset: f64,
        #[serde(default = "one")]
        gamma: f64,
    },
    BrightnessContrast {
        brightness: f64,
        contrast: f64,
    },
    ShadowsHighlights {
        shadows: f64,
        highlights: f64,
    },
}
fn one() -> f64 {
    1.0
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Layer {
    pub operators: Vec<Operator>,
    #[serde(default)]
    pub clip_to: Option<String>,
}
fn range(x: f64, low: f64, high: f64) -> bool {
    x.is_finite() && (low..=high).contains(&x)
}
impl Layer {
    pub fn validate(&self) -> Result<(), Error> {
        if self.operators.is_empty() || self.operators.len() > MAX_OPERATORS {
            return Err(invalid("Adjustment layers require 1..=16 operators"));
        }
        for operator in &self.operators {
            let valid = match operator {
                Operator::Color { adjustment } => {
                    adjustment.validate()?;
                    true
                }
                Operator::Invert {} => true,
                Operator::Threshold { level } => range(*level, 0.0, 1.0),
                Operator::Levels {
                    input,
                    gamma,
                    output,
                } => {
                    input.iter().chain(output).all(|&x| range(x, 0.0, 1.0))
                        && input[0] < input[1]
                        && range(*gamma, 0.1, 10.0)
                }
                Operator::Posterize { levels } => (2..=256).contains(levels),
                Operator::Curve { points, .. } => {
                    (2..=MAX_CURVE_POINTS).contains(&points.len())
                        && points.iter().flatten().all(|&x| range(x, 0.0, 1.0))
                        && points[0][0] == 0.0
                        && points.last().unwrap()[0] == 1.0
                        && points.windows(2).all(|p| p[0][0] < p[1][0])
                }
                Operator::Exposure {
                    stops,
                    offset,
                    gamma,
                } => {
                    range(*stops, -16.0, 16.0)
                        && range(*offset, -1.0, 1.0)
                        && range(*gamma, 0.1, 10.0)
                }
                Operator::BrightnessContrast {
                    brightness,
                    contrast,
                } => range(*brightness, -1.0, 1.0) && range(*contrast, -1.0, 1.0),
                Operator::ShadowsHighlights {
                    shadows,
                    highlights,
                } => range(*shadows, -1.0, 1.0) && range(*highlights, -1.0, 1.0),
            };
            if !valid {
                return Err(invalid(
                    "Adjustment operator parameters are invalid or exceed declared bounds",
                ));
            }
        }
        Ok(())
    }
    pub fn work(&self) -> u64 {
        self.operators
            .iter()
            .map(|op| match op {
                Operator::Color { adjustment } => adjustment.work(),
                Operator::Curve { .. } => 8,
                _ => 4,
            })
            .sum()
    }
}
pub(crate) fn validate_document(document: &Document) -> Result<(), Error> {
    let mut count = 0;
    let mut lut_entries = 0;
    for (i, item) in document.items.iter().enumerate() {
        if let Content::Adjustment { adjustment } = &item.content {
            count += adjustment.operators.len();
            lut_entries += adjustment
                .operators
                .iter()
                .map(|op| match op {
                    Operator::Color { adjustment } => adjustment.entries(),
                    _ => 0,
                })
                .sum::<usize>();
            if let Some(base_id) = &adjustment.clip_to {
                let siblings = scene::children(document, item.parent.as_deref());
                let position = siblings.iter().position(|&j| j == i).unwrap();
                let base = siblings[..position].iter().rev().find(|&&j| {
                    !crate::layer_clipping::auxiliary(&document.items[j].content)
                        && !matches!(&document.items[j].content,Content::Adjustment{adjustment} if adjustment.clip_to.is_some())
                });
                if base.is_none_or(|&j| {
                    document.items[j].id != *base_id
                        || matches!(
                            document.items[j].content,
                            Content::Adjustment { .. }
                                | Content::WorkPath { .. }
                                | Content::MaskSource {}
                                | Content::Group {
                                    isolated: false,
                                    ..
                                }
                        )
                }) {
                    return Err(invalid(
                        "Clipped adjustments must reference their preceding drawable or isolated sibling base",
                    )
                    .at_item(&item.id));
                }
            }
        }
    }
    if count > MAX_DOCUMENT_OPERATORS {
        return Err(limit("Document exceeds 256 adjustment operators"));
    }
    if lut_entries > crate::color_adjustments::MAX_DOCUMENT_LUT_ENTRIES {
        return Err(limit("Document exceeds 65536 color lookup entries"));
    }
    Ok(())
}
fn luma(c: [f64; 3]) -> f64 {
    c[0] * 0.2126 + c[1] * 0.7152 + c[2] * 0.0722
}
fn shift(x: f64, amount: f64) -> f64 {
    if amount >= 0.0 {
        x + (1.0 - x) * amount
    } else {
        x * (1.0 + amount)
    }
}
pub(crate) fn evaluate(mut color: [f64; 3], layer: &Layer) -> [f64; 3] {
    for op in &layer.operators {
        color = match op {
            Operator::Color { adjustment } => crate::color_adjustments::evaluate(color, adjustment),
            Operator::Invert {} => color.map(|x| 1.0 - x),
            Operator::Threshold { level } => [if luma(color) >= *level { 1.0 } else { 0.0 }; 3],
            Operator::Levels {
                input,
                gamma,
                output,
            } => color.map(|x| {
                output[0]
                    + (output[1] - output[0])
                        * ((x - input[0]) / (input[1] - input[0]))
                            .clamp(0.0, 1.0)
                            .powf(1.0 / gamma)
            }),
            Operator::Posterize { levels } => {
                let n = (*levels - 1) as f64;
                color.map(|x| (x * n).round() / n)
            }
            Operator::Curve { points, channel } => std::array::from_fn(|i| {
                if !matches!(
                    (channel, i),
                    (Channel::Rgb, _)
                        | (Channel::Red, 0)
                        | (Channel::Green, 1)
                        | (Channel::Blue, 2)
                ) {
                    return color[i];
                }
                let x = color[i];
                let right = points
                    .partition_point(|p| p[0] <= x)
                    .clamp(1, points.len() - 1);
                let [a, b] = [points[right - 1], points[right]];
                a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0])
            }),
            Operator::Exposure {
                stops,
                offset,
                gamma,
            } => color.map(|x| {
                crate::paint::encode(
                    (crate::paint::decode(x) * stops.exp2() + offset)
                        .clamp(0.0, 1.0)
                        .powf(1.0 / gamma),
                )
            }),
            Operator::BrightnessContrast {
                brightness,
                contrast,
            } => color.map(|x| {
                shift(
                    ((x - 0.5) * (contrast * 4.0).exp2() + 0.5).clamp(0.0, 1.0),
                    *brightness,
                )
            }),
            Operator::ShadowsHighlights {
                shadows,
                highlights,
            } => {
                let y = luma(color);
                let amount = shadows * (1.0 - y).powi(2) - highlights * y.powi(2);
                color.map(|x| shift(x, amount))
            }
        }
        .map(|x| x.clamp(0.0, 1.0));
    }
    color
}
