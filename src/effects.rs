//! Original editable alpha-derived decoration, independent of content fill.
use crate::{Error, control::Control, model::*, paint, scene};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use std::borrow::Cow;
use std::collections::HashSet;

pub const MAX_STACK: usize = 8;
pub const MAX_DOCUMENT_EFFECTS: usize = 64;
pub const MAX_WORK: u64 = 67_108_864;
fn yes() -> bool {
    true
}
fn one() -> f64 {
    1.0
}
fn is_one(value: &f64) -> bool {
    *value == 1.0
}
fn default_azimuth() -> f64 {
    225.0
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Lighting {
    #[serde(default = "default_azimuth")]
    pub azimuth: f64,
}
impl Default for Lighting {
    fn default() -> Self {
        Self {
            azimuth: default_azimuth(),
        }
    }
}
impl Lighting {
    pub fn is_default(&self) -> bool {
        *self == Self::default()
    }
}
fn valid_angle(angle: f64) -> bool {
    angle.is_finite() && (-360.0..=360.0).contains(&angle)
}
fn shadow_offset(distance: f64, angle: f64) -> Point {
    let direction = match angle.rem_euclid(360.0) {
        0.0 => [1.0, 0.0],
        90.0 => [0.0, 1.0],
        180.0 => [-1.0, 0.0],
        270.0 => [0.0, -1.0],
        a => {
            let (s, c) = a.to_radians().sin_cos();
            [c, s]
        }
    };
    direction.map(|v| -distance * v)
}

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum StrokePosition {
    #[default]
    Outside,
    Inside,
    Center,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Operator {
    Shadow {
        offset: Point,
        sigma: f64,
    },
    LitShadow {
        distance: f64,
        sigma: f64,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        azimuth: Option<f64>,
    },
    Stroke {
        radius: u32,
        #[serde(default)]
        position: StrokePosition,
    },
    Overlay {},
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Effect {
    pub id: String,
    pub operator: Operator,
    pub color: Paint,
    #[serde(default = "one", skip_serializing_if = "is_one")]
    pub scale: f64,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub contour: Vec<Point>,
    #[serde(default = "yes")]
    pub enabled: bool,
    #[serde(default = "one")]
    pub opacity: f64,
}
pub(crate) fn validate(document: &Document) -> Result<(), Error> {
    if !valid_angle(document.global_light.azimuth) {
        return Err(invalid(
            "Global light azimuth must be finite and within -360..=360 degrees",
        ));
    }
    if document
        .items
        .iter()
        .map(|i| i.effects.len())
        .sum::<usize>()
        > MAX_DOCUMENT_EFFECTS
    {
        return Err(limit("Document exceeds 64 layer effects"));
    }
    for (i, item) in document.items.iter().enumerate() {
        if !item.fill_opacity.is_finite() || !(0.0..=1.0).contains(&item.fill_opacity) {
            return Err(invalid("Fill opacity must be in 0..=1").at_item(&item.id));
        }
        if (item.fill_opacity != 1.0 || !item.effects.is_empty() || !item.coverage.is_smooth())
            && (matches!(
                item.content,
                Content::WorkPath { .. }
                    | Content::MaskSource {}
                    | Content::Adjustment { .. }
                    | Content::Group {
                        isolated: false,
                        ..
                    }
            ) || crate::artwork_masks::source_owner(document, i)?.is_some())
        {
            return Err(Error::new("UNSUPPORTED","Fill, layer effects and coverage controls require an independently composited printable item outside a mask source").at_item(&item.id));
        }
        if item.effects.len() > MAX_STACK {
            return Err(limit("Item exceeds 8 layer effects").at_item(&item.id));
        }
        let mut ids = HashSet::new();
        for e in &item.effects {
            if !valid_id(&e.id)
                || !ids.insert(&e.id)
                || !e.scale.is_finite()
                || !(0.001..=1024.0).contains(&e.scale)
                || !e.opacity.is_finite()
                || !(0.0..=1.0).contains(&e.opacity)
            {
                return Err(
                    invalid("Layer effects require unique valid IDs and opacity in 0..=1")
                        .at_item(&item.id),
                );
            }
            if !e.contour.is_empty() {
                if !(2..=64).contains(&e.contour.len()) {
                    return Err(
                        limit("Effect contour requires 2 through 64 knots").at_item(&item.id)
                    );
                }
                if e.contour.first() != Some(&[0.0, 0.0])
                    || e.contour.last().unwrap()[0] != 1.0
                    || e.contour
                        .iter()
                        .flatten()
                        .any(|v| !v.is_finite() || !(0.0..=1.0).contains(v))
                    || e.contour.windows(2).any(|v| v[0][0] >= v[1][0])
                {
                    return Err(invalid("Effect contour requires increasing 0..1 inputs, bounded outputs, origin [0,0] and final input 1").at_item(&item.id));
                }
            }
            let sigma_ok = |sigma: f64| {
                sigma.is_finite() && (0.0..=16.0).contains(&sigma) && sigma * e.scale <= 16.0
            };
            let valid = match &e.operator {
                Operator::Shadow { offset, sigma } => {
                    offset
                        .iter()
                        .all(|v| v.is_finite() && v.abs() <= 256.0 && (v * e.scale).abs() <= 256.0)
                        && sigma_ok(*sigma)
                }
                Operator::LitShadow {
                    distance,
                    sigma,
                    azimuth,
                } => {
                    distance.is_finite()
                        && (0.0..=256.0).contains(distance)
                        && distance * e.scale <= 256.0
                        && sigma_ok(*sigma)
                        && azimuth.is_none_or(valid_angle)
                }
                Operator::Stroke { radius, .. } => {
                    *radius <= 32 && *radius as f64 * e.scale <= 32.0
                }
                Operator::Overlay {} => true,
            };
            if !valid {
                return Err(
                    invalid("Layer effect parameters exceed declared bounds").at_item(&item.id)
                );
            }
        }
    }
    Ok(())
}
fn sampler(effect: &Effect, world: Matrix) -> Result<paint::Sampler<'_>, Error> {
    paint::Sampler::new(
        &effect.color,
        if matches!(effect.color, Paint::Solid(_)) {
            identity()
        } else {
            world
        },
    )
}
impl Effect {
    fn contour(&self, alpha: f64) -> f64 {
        let a = alpha.clamp(0.0, 1.0);
        if self.contour.is_empty() {
            return a;
        }
        let right = self.contour.partition_point(|p| p[0] <= a);
        if right == self.contour.len() {
            return self.contour.last().unwrap()[1];
        }
        let [x0, y0] = self.contour[right - 1];
        let [x1, y1] = self.contour[right];
        y0 + (y1 - y0) * ((a - x0) / (x1 - x0))
    }
    fn shadow(&self, light: Lighting) -> Option<(Point, f64)> {
        match self.operator {
            Operator::Shadow { offset, sigma } => Some((offset, sigma)),
            Operator::LitShadow {
                distance,
                sigma,
                azimuth,
            } => Some((
                shadow_offset(distance, azimuth.unwrap_or(light.azimuth)),
                sigma,
            )),
            _ => None,
        }
    }
    pub(crate) fn field(
        &self,
        alpha: &[f64],
        size: [u32; 3],
        light: Lighting,
        control: &Control,
    ) -> Result<Vec<f64>, Error> {
        let [w, h, scale] = size;
        let s = self.scale * scale as f64;
        let mut result = if let Some((offset, sigma)) = self.shadow(light) {
            let blurred = blur_or_borrow(alpha, w, h, sigma * s, Some(control))?;
            let mut result = vec![0.0; alpha.len()];
            for (n, value) in result.iter_mut().enumerate() {
                if n.is_multiple_of(4096) {
                    control.check()?;
                }
                *value = shifted(
                    &blurred,
                    w,
                    h,
                    (n % w as usize) as f64 - offset[0] * s,
                    (n / w as usize) as f64 - offset[1] * s,
                );
            }
            result
        } else if let Operator::Stroke { radius, position } = self.operator {
            stroke(alpha, w, h, radius as f64 * s, position, Some(control))?
        } else {
            alpha.to_vec()
        };
        for (n, value) in result.iter_mut().enumerate() {
            if n.is_multiple_of(4096) {
                control.check()?;
            }
            *value = self.contour(*value);
        }
        Ok(result)
    }
}
pub(crate) fn support(item: &Item, scale: u32, light: Lighting) -> u32 {
    item.effects
        .iter()
        .filter(|e| e.enabled)
        .map(|e| {
            let s = e.scale * scale as f64;
            if let Some((offset, sigma)) = e.shadow(light) {
                (offset[0].abs().max(offset[1].abs()) * s).ceil() as u32
                    + (3.0 * sigma * s).ceil() as u32
                    + 1
            } else if let Operator::Stroke { radius, .. } = e.operator {
                (radius as f64 * s).ceil() as u32
            } else {
                0
            }
        })
        .max()
        .unwrap_or(0)
}
pub(crate) fn set_light(document: &mut Document, light: Lighting) -> Result<(), Error> {
    for (i, item) in document.items.iter().enumerate() {
        if item
            .effects
            .iter()
            .any(|e| matches!(e.operator, Operator::LitShadow { azimuth: None, .. }))
        {
            scene::check_unlocked(document, i, true)?;
        }
    }
    document.global_light = light;
    Ok(())
}
pub(crate) fn work(item: &Item, scale: u32) -> u64 {
    item.effects
        .iter()
        .filter(|e| e.enabled)
        .map(|e| {
            let s = e.scale * scale as f64;
            let base = match e.operator {
                Operator::Shadow { offset, sigma }
                    if sigma == 0.0 && offset.iter().all(|v| (v * s).fract() == 0.0) =>
                {
                    // Borrow original alpha and read one exact tap instead of
                    // allocating a blur copy and four weighted source taps.
                    16
                }
                Operator::Shadow { sigma, .. } | Operator::LitShadow { sigma, .. } => {
                    2 * (2 * (3.0 * sigma * s).ceil() as u64 + 1) + 24
                }
                Operator::Stroke { radius, .. } => {
                    (2 * (radius as f64 * s).ceil() as u64 + 1).pow(2) + 16
                }
                Operator::Overlay {} => 12,
            };
            base + e.contour.len() as u64
                + if matches!(e.color, Paint::Solid(_)) {
                    0
                } else {
                    8 + paint::work(&e.color)
                }
        })
        .sum::<u64>()
        + if item.coverage.is_smooth() { 0 } else { 32 }
}
fn at(alpha: &[f64], w: u32, h: u32, x: i64, y: i64) -> f64 {
    if x < 0 || y < 0 || x >= w as i64 || y >= h as i64 {
        0.0
    } else {
        alpha[y as usize * w as usize + x as usize]
    }
}
fn shifted(alpha: &[f64], w: u32, h: u32, x: f64, y: f64) -> f64 {
    let ix = x.floor() as i64;
    let iy = y.floor() as i64;
    let fx = x - x.floor();
    let fy = y - y.floor();
    if fx == 0.0 && fy == 0.0 {
        return at(alpha, w, h, ix, iy);
    }
    [(0, 1.0 - fx), (1, fx)]
        .into_iter()
        .map(|(dx, wx)| {
            [(0, 1.0 - fy), (1, fy)]
                .into_iter()
                .map(|(dy, wy)| wx * wy * at(alpha, w, h, ix + dx, iy + dy))
                .sum::<f64>()
        })
        .sum()
}
fn blur_or_borrow<'a>(
    alpha: &'a [f64],
    w: u32,
    h: u32,
    sigma: f64,
    control: Option<&Control>,
) -> Result<Cow<'a, [f64]>, Error> {
    if sigma == 0.0 {
        Ok(Cow::Borrowed(alpha))
    } else {
        blur(alpha, w, h, sigma, control).map(Cow::Owned)
    }
}
fn blur(
    alpha: &[f64],
    w: u32,
    h: u32,
    sigma: f64,
    control: Option<&Control>,
) -> Result<Vec<f64>, Error> {
    if sigma == 0.0 {
        return Ok(alpha.to_vec());
    }
    let r = (3.0 * sigma).ceil() as i64;
    let mut k: Vec<f64> = (-r..=r)
        .map(|d| (-0.5 * (d as f64 / sigma).powi(2)).exp())
        .collect();
    let total: f64 = k.iter().sum();
    for v in &mut k {
        *v /= total;
    }
    let mut temp = vec![0.0; alpha.len()];
    let mut result = vec![0.0; alpha.len()];
    for horizontal in [true, false] {
        let (src, dst) = if horizontal {
            (alpha, &mut temp)
        } else {
            (temp.as_slice(), &mut result)
        };
        for y in 0..h {
            if let Some(control) = control {
                control.check()?;
            }
            for x in 0..w {
                dst[(y * w + x) as usize] = k
                    .iter()
                    .enumerate()
                    .map(|(j, weight)| {
                        let d = j as i64 - r;
                        weight
                            * at(
                                src,
                                w,
                                h,
                                x as i64 + if horizontal { d } else { 0 },
                                y as i64 + if horizontal { 0 } else { d },
                            )
                    })
                    .sum();
            }
        }
    }
    Ok(result)
}
fn stroke(
    alpha: &[f64],
    w: u32,
    h: u32,
    radius: f64,
    position: StrokePosition,
    control: Option<&Control>,
) -> Result<Vec<f64>, Error> {
    let r = radius.ceil() as i64;
    let mut result = vec![0.0; alpha.len()];
    let disk: Vec<_> = (-r..=r)
        .flat_map(|y| {
            (-r..=r)
                .filter_map(move |x| ((x * x + y * y) as f64 <= radius * radius).then_some((x, y)))
        })
        .collect();
    for y in 0..h {
        if let Some(control) = control {
            control.check()?;
        }
        for x in 0..w {
            let n = (y * w + x) as usize;
            let mut lo = alpha[n];
            let mut hi = lo;
            for &(dx, dy) in &disk {
                let a = at(alpha, w, h, x as i64 + dx, y as i64 + dy);
                lo = lo.min(a);
                hi = hi.max(a);
            }
            result[n] = match position {
                StrokePosition::Outside => hi - alpha[n],
                StrokePosition::Inside => alpha[n] - lo,
                StrokePosition::Center => hi - lo,
            };
        }
    }
    Ok(result)
}
fn over(dst: &mut [f64], color: [f64; 4], weight: f64) {
    let alpha = color[3] * weight;
    for c in 0..3 {
        dst[c] = color[c] * alpha + (1.0 - alpha) * dst[c];
    }
    dst[3] = alpha + (1.0 - alpha) * dst[3];
}
pub(crate) fn apply_region(
    item: &Item,
    pixels: &mut [f64],
    size: [u32; 3],
    world: Matrix,
    light: Lighting,
    origin: [u32; 2],
) -> Result<(), Error> {
    let [w, h, scale] = size;
    if !item.effects.iter().any(|e| e.enabled) {
        if item.fill_opacity != 1.0 {
            for v in pixels {
                *v *= item.fill_opacity;
            }
        }
        return Ok(());
    }
    let alpha: Vec<_> = pixels.as_chunks::<4>().0.iter().map(|p| p[3]).collect();
    let mut decorated = vec![0.0; pixels.len()];
    let canvas_point = |n: usize| {
        [
            (origin[0] as usize + n % w as usize) as f64 + 0.5,
            (origin[1] as usize + n / w as usize) as f64 + 0.5,
        ]
        .map(|v| v / scale as f64)
    };
    // All shadows are below content, in list order. Their source is immutable.
    for e in item.effects.iter().filter(|e| e.enabled) {
        if let Some((offset, sigma)) = e.shadow(light) {
            let color = sampler(e, world)?;
            let s = e.scale * scale as f64;
            let blurred = blur_or_borrow(&alpha, w, h, sigma * s, None)?;
            for y in 0..h {
                for x in 0..w {
                    let amount = shifted(
                        &blurred,
                        w,
                        h,
                        x as f64 - offset[0] * s,
                        y as f64 - offset[1] * s,
                    );
                    over(
                        &mut decorated[((y * w + x) * 4) as usize..][..4],
                        color.sample(canvas_point((y * w + x) as usize)),
                        e.contour(amount) * e.opacity,
                    );
                }
            }
        }
    }
    // Content overlays are conditional on original coverage, rather than
    // duplicating alpha. At fill=1 they retain the source alpha exactly.
    for v in pixels.iter_mut() {
        *v *= item.fill_opacity;
    }
    for e in item
        .effects
        .iter()
        .filter(|e| e.enabled && matches!(e.operator, Operator::Overlay {}))
    {
        let sampler = sampler(e, world)?;
        for (n, (p, &a)) in pixels
            .as_chunks_mut::<4>()
            .0
            .iter_mut()
            .zip(&alpha)
            .enumerate()
        {
            let color = sampler.sample(canvas_point(n));
            let strength = color[3] * e.opacity;
            let a = e.contour(a);
            for (c, v) in p.iter_mut().take(3).enumerate() {
                let replacement = match e.color {
                    Paint::Solid(rgba) => a * strength * rgba[c] as f64 / 255.0,
                    _ => a * strength * color[c],
                };
                *v = *v * (1.0 - strength) + replacement;
            }
            p[3] = p[3] * (1.0 - strength) + a * strength;
        }
    }
    for (dst, src) in decorated
        .as_chunks_mut::<4>()
        .0
        .iter_mut()
        .zip(pixels.as_chunks::<4>().0)
    {
        for c in 0..4 {
            dst[c] = src[c] + (1.0 - src[3]) * dst[c];
        }
    }
    // Stroke decorations follow content, in list order, using source alpha.
    for e in item.effects.iter().filter(|e| e.enabled) {
        if let Operator::Stroke { radius, position } = e.operator {
            let sampler = sampler(e, world)?;
            let field = stroke(
                &alpha,
                w,
                h,
                radius as f64 * e.scale * scale as f64,
                position,
                None,
            )?;
            for (n, (dst, &a)) in decorated
                .as_chunks_mut::<4>()
                .0
                .iter_mut()
                .zip(&field)
                .enumerate()
            {
                over(
                    dst,
                    sampler.sample(canvas_point(n)),
                    e.contour(a) * e.opacity,
                );
            }
        }
    }
    pixels.copy_from_slice(&decorated);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn contour_subnormal_interval_and_cardinal_light_offsets() {
        let e = Effect {
            id: "curve".into(),
            operator: Operator::Overlay {},
            color: Paint::Solid([0, 0, 0, 255]),
            enabled: true,
            opacity: 1.0,
            scale: 1.0,
            contour: vec![[0.0, 0.0], [f64::from_bits(4), 0.25], [1.0, 1.0]],
        };
        assert_eq!(e.contour(f64::from_bits(2)), 0.125);
        assert_eq!(e.contour(0.0), 0.0);
        assert_eq!(e.contour(1.0), 1.0);
        assert_eq!(shadow_offset(3.0, 360.0), [-3.0, 0.0]);
        assert_eq!(shadow_offset(3.0, -90.0), [0.0, 3.0]);
        assert_eq!(shadow_offset(3.0, 180.0), [3.0, 0.0]);
    }
}
