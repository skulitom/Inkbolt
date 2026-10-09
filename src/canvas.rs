//! Layer-preserving raster canvas geometry and explicit resolution edits.
use crate::{Error, assets::Sampling, geometry, model::*, scene, selections};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Anchor {
    TopLeft,
    Top,
    TopRight,
    Left,
    #[default]
    Center,
    Right,
    BottomLeft,
    Bottom,
    BottomRight,
}
impl Anchor {
    fn factors(self) -> [i64; 2] {
        match self {
            Self::TopLeft => [0, 0],
            Self::Top => [1, 0],
            Self::TopRight => [2, 0],
            Self::Left => [0, 1],
            Self::Center => [1, 1],
            Self::Right => [2, 1],
            Self::BottomLeft => [0, 2],
            Self::Bottom => [1, 2],
            Self::BottomRight => [2, 2],
        }
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum EffectPolicy {
    PreserveParameters,
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Action {
    /// Integral current-canvas coordinates; negative origins add transparent space.
    Crop {
        x: i32,
        y: i32,
        width: u32,
        height: u32,
        effect_policy: Option<EffectPolicy>,
    },
    Extent {
        width: u32,
        height: u32,
        #[serde(default)]
        anchor: Anchor,
        effect_policy: Option<EffectPolicy>,
    },
    Scale {
        width: u32,
        height: u32,
        sampling: Sampling,
        effect_policy: Option<EffectPolicy>,
    },
    Resolution {
        ppi: f64,
    },
}

fn size(width: u32, height: u32) -> Result<(), Error> {
    if width == 0 || height == 0 || width > MAX_DIMENSION || height > MAX_DIMENSION {
        Err(Error::new(
            "INVALID_OPERATION",
            "Canvas dimensions must be in 1..=32768",
        ))
    } else {
        Ok(())
    }
}

/// Canvas-bound auxiliary planes are cropped/padded or resampled once. The
/// original plane remains in the caller's snapshot and durable undo history.
fn plane(
    source: &selections::Selection,
    width: u32,
    height: u32,
    transform: Matrix,
    sampling: Option<Sampling>,
) -> Result<selections::Selection, Error> {
    let original = crate::render::unhex(&source.gray_hex);
    let inverse = geometry::inverse(transform)?;
    let plan = crate::resample::Plan::new(
        sampling.unwrap_or_default(),
        [inverse[0].abs(), inverse[3].abs()],
    )?;
    let at = |x: i64, y: i64| -> f64 {
        // Scaling reconstructs within the original canvas, clamping boundary
        // samples. Reframing extends with zero rather than repeated edge pixels.
        let (x, y) = if sampling.is_some() {
            (
                x.clamp(0, source.width as i64 - 1),
                y.clamp(0, source.height as i64 - 1),
            )
        } else {
            (x, y)
        };
        if x < 0 || y < 0 || x >= source.width as i64 || y >= source.height as i64 {
            0.0
        } else {
            original[y as usize * source.width as usize + x as usize] as f64
        }
    };
    let mut pixels = Vec::with_capacity(width as usize * height as usize);
    for y in 0..height {
        for x in 0..width {
            let p = geometry::map(inverse, [x as f64 + 0.5, y as f64 + 0.5]);
            let value = match sampling.unwrap_or_default() {
                Sampling::Nearest => at(
                    crate::assets::pixel_index(p[0]),
                    crate::assets::pixel_index(p[1]),
                ),
                Sampling::Bilinear => {
                    let x = p[0] - 0.5;
                    let y = p[1] - 0.5;
                    let (ix, iy) = (x.floor() as i64, y.floor() as i64);
                    let (fx, fy) = (x - x.floor(), y - y.floor());
                    at(ix, iy) * (1.0 - fx) * (1.0 - fy)
                        + at(ix + 1, iy) * fx * (1.0 - fy)
                        + at(ix, iy + 1) * (1.0 - fx) * fy
                        + at(ix + 1, iy + 1) * fx * fy
                }
                _ => plan.sample(p, |x, y| [at(x, y)])?[0],
            };
            pixels.push(value.clamp(0.0, 255.0).round() as u8);
        }
    }
    Ok(selections::Selection {
        width,
        height,
        gray_hex: crate::render::hex(&pixels),
    })
}

pub(crate) fn edit(document: &mut Document, action: &Action) -> Result<Value, Error> {
    if document.kind != DocumentKind::Raster {
        return Err(Error::new(
            "UNSUPPORTED",
            "Canvas operations currently require a raster document",
        ));
    }
    if let Action::Resolution { ppi } = action {
        if !ppi.is_finite() || !(1.0..=9600.0).contains(ppi) {
            return Err(Error::new(
                "INVALID_OPERATION",
                "Resolution must be in 1..=9600 pixels per inch",
            ));
        }
        let old = document.resolution_ppi;
        document.resolution_ppi = *ppi;
        return Ok(json!({"before_ppi":old,"after_ppi":ppi,"pixels_changed":false}));
    }
    let old_size = [document.width, document.height];
    let (width, height, transform, sampling, policy) = match *action {
        Action::Crop {
            x,
            y,
            width,
            height,
            effect_policy,
        } => {
            if x.unsigned_abs() > MAX_DIMENSION || y.unsigned_abs() > MAX_DIMENSION {
                return Err(Error::new(
                    "INVALID_OPERATION",
                    "Crop origins exceed coordinate limits",
                ));
            }
            (
                width,
                height,
                [1.0, 0.0, 0.0, 1.0, -(x as f64), -(y as f64)],
                None,
                effect_policy,
            )
        }
        Action::Extent {
            width,
            height,
            anchor,
            effect_policy,
        } => {
            let factors = anchor.factors();
            let x = ((width as i64 - document.width as i64) * factors[0]).div_euclid(2);
            let y = ((height as i64 - document.height as i64) * factors[1]).div_euclid(2);
            (
                width,
                height,
                [1.0, 0.0, 0.0, 1.0, x as f64, y as f64],
                None,
                effect_policy,
            )
        }
        Action::Scale {
            width,
            height,
            sampling,
            effect_policy,
        } => (
            width,
            height,
            [
                width as f64 / document.width as f64,
                0.0,
                0.0,
                height as f64 / document.height as f64,
                0.0,
                0.0,
            ],
            Some(sampling),
            effect_policy,
        ),
        Action::Resolution { .. } => unreachable!(),
    };
    size(width, height)?;
    if document.items.iter().any(|i| {
        !i.filters.is_empty() || !i.effects.is_empty() || crate::appearance::has_effects(i)
    }) && policy.is_none()
    {
        return Err(Error::new(
            "UNSUPPORTED",
            "Canvas edits with viewport filters or layer effects require explicit preserve_parameters effect_policy; parameters are retained while coverage and viewport boundaries are re-evaluated",
        ));
    }
    let count = width as u64 * height as u64;
    if let Some(method) = sampling.filter(|m| m.advanced()) {
        let plan = crate::resample::Plan::new(
            method,
            [
                document.width as f64 / width as f64,
                document.height as f64 / height as f64,
            ],
        )?;
        let planes = document.channels.len() as u64 + u64::from(document.selection.is_some());
        if count.saturating_mul(planes).saturating_mul(plan.work()) > crate::resample::MAX_WORK {
            return Err(limit(
                "Canvas auxiliary planes exceed reconstruction work limit",
            ));
        }
    }
    if (document.selection.is_some() && count > selections::MAX_PIXELS)
        || count * document.channels.len() as u64 > crate::channels::MAX_SAMPLES as u64
    {
        return Err(Error::new(
            "RESOURCE_LIMIT",
            "Resized auxiliary planes exceed selection or aggregate channel storage",
        ));
    }
    let mut edited = Vec::new();
    for i in 0..document.items.len() {
        if crate::artwork_masks::source_owner(document, i)?.is_none() {
            scene::check_unlocked(document, i, false)?;
            edited.push(i);
        }
    }
    for i in edited {
        let item = &mut document.items[i];
        if item.parent.is_none() {
            item.transform = geometry::multiply(transform, item.transform);
        }
        for mask in item
            .mask
            .iter_mut()
            .chain(item.filters.iter_mut().filter_map(|f| f.mask.as_mut()))
        {
            if !mask.linked {
                mask.transform = geometry::multiply(transform, mask.transform);
            }
        }
        if let Some(mask) = item.artwork_mask.as_mut().filter(|m| !m.linked) {
            mask.transform = geometry::multiply(transform, mask.transform);
        }
        if let Some(method) = sampling {
            match &mut item.content {
                Content::Object { object } => object.sampling = method,
                Content::Samples { grid } => grid.sampling = method,
                Content::StoredSamples { grid } => grid.sampling = method,
                Content::Raw { raw } => raw.sampling = method,
                Content::Raster { sampling, .. } | Content::Image { sampling, .. } => {
                    *sampling = method
                }
                _ => {}
            }
        }
    }
    if let Some(source) = &document.selection {
        document.selection = Some(plane(source, width, height, transform, sampling)?);
    }
    for channel in document.channels.values_mut() {
        channel.plane = plane(&channel.plane, width, height, transform, sampling)?;
    }
    document.width = width;
    document.height = height;
    Ok(
        json!({"before_dimensions":old_size,"after_dimensions":[width,height],"content_transform":transform,"sampling":sampling,"source_content_retained":true,"auxiliary_planes":"canvas_bound_crop_pad_or_resample","effect_policy":policy,"resolution_ppi":document.resolution_ppi}),
    )
}
