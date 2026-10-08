//! Original shared-knot bicubic color fields with contraction-bounded geometry.
use crate::{
    Document, Error,
    model::{Color, Content, Paint, Point, invalid, limit},
    paint::{Field, Interpolation},
};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

pub const MAX_AXIS: usize = 8;
pub const MAX_SAMPLES: usize = 1024;
pub const INVERSE_STEPS: usize = 128;
pub const MAX_CONTRACTION: f64 = 0.75;
pub const MAX_TEXTURE_PIXELS: usize = 65536;
pub const MAX_SVG_TEXTURE_PIXELS: usize = 131072;
fn texture_samples() -> u32 {
    16
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Knot {
    pub color: Color,
    #[serde(default)]
    pub offset: Point,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Mesh {
    pub origin: Point,
    pub size: Point,
    pub columns: usize,
    pub rows: usize,
    pub knots: Vec<Knot>,
    #[serde(default = "texture_samples")]
    pub svg_samples_per_cell: u32,
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Target {
    #[default]
    Fill,
    Stroke,
}
type Patch<const N: usize> = [[[f64; N]; 4]; 4];
#[derive(Clone, Copy)]
struct Jet<const N: usize> {
    value: [f64; N],
    u: [f64; N],
    v: [f64; N],
    uv: [f64; N],
}
fn differences<const N: usize>(
    data: &[[f64; N]],
    w: usize,
    h: usize,
    axis: usize,
) -> Vec<[f64; N]> {
    (0..w * h)
        .map(|i| {
            let (x, y) = (i % w, i / w);
            let index = if axis == 0 { x } else { y };
            let n = if axis == 0 { w } else { h };
            let stride = if axis == 0 { 1 } else { w };
            let left = i - if index > 0 { stride } else { 0 };
            let right = i + if index + 1 < n { stride } else { 0 };
            let denominator = if index > 0 && index + 1 < n { 2.0 } else { 1.0 };
            std::array::from_fn(|c| (data[right][c] - data[left][c]) / denominator)
        })
        .collect()
}
fn jets<const N: usize>(data: Vec<[f64; N]>, w: usize, h: usize) -> Vec<Jet<N>> {
    let u = differences(&data, w, h, 0);
    let v = differences(&data, w, h, 1);
    let uv = differences(&u, w, h, 1);
    (0..w * h)
        .map(|i| Jet {
            value: data[i],
            u: u[i],
            v: v[i],
            uv: uv[i],
        })
        .collect()
}
fn patches<const N: usize>(jets: &[Jet<N>], w: usize, h: usize) -> Vec<Patch<N>> {
    (0..(w - 1) * (h - 1))
        .map(|n| {
            let x = n % (w - 1);
            let y = n / (w - 1);
            let mut patch = [[[0.0; N]; 4]; 4];
            for dy in 0..2 {
                for dx in 0..2 {
                    let j = jets[(y + dy) * w + x + dx];
                    let bx = dx * 3;
                    let by = dy * 3;
                    let ix = if dx == 0 { 1 } else { 2 };
                    let iy = if dy == 0 { 1 } else { 2 };
                    let sx = if dx == 0 { 1.0 } else { -1.0 };
                    let sy = if dy == 0 { 1.0 } else { -1.0 };
                    patch[by][bx] = j.value;
                    for (c, _) in j.value.iter().enumerate() {
                        patch[by][ix][c] = j.value[c] + sx * j.u[c] / 3.0;
                        patch[iy][bx][c] = j.value[c] + sy * j.v[c] / 3.0;
                        patch[iy][ix][c] = j.value[c]
                            + sx * j.u[c] / 3.0
                            + sy * j.v[c] / 3.0
                            + sx * sy * j.uv[c] / 9.0;
                    }
                }
            }
            patch
        })
        .collect()
}
/// Scale each knot's three color derivatives together. Shared jets retain C1
/// joins while every Bernstein color/alpha control stays inside its range.
fn limit_colors(jets: &mut [Jet<4>], w: usize, h: usize) {
    for (i, j) in jets.iter_mut().enumerate() {
        let x = i % w;
        let y = i / w;
        for c in 0..4 {
            let mut factor: f64 = 1.0;
            for sx in [-1.0, 1.0] {
                for sy in [-1.0, 1.0] {
                    if (sx < 0.0 && x == 0)
                        || (sx > 0.0 && x + 1 == w)
                        || (sy < 0.0 && y == 0)
                        || (sy > 0.0 && y + 1 == h)
                    {
                        continue;
                    }
                    for delta in [
                        sx * j.u[c] / 3.0,
                        sy * j.v[c] / 3.0,
                        sx * j.u[c] / 3.0 + sy * j.v[c] / 3.0 + sx * sy * j.uv[c] / 9.0,
                    ] {
                        if delta > 0.0 {
                            factor = factor.min((1.0 - j.value[c]) / delta);
                        } else if delta < 0.0 {
                            factor = factor.min(-j.value[c] / delta);
                        }
                    }
                }
            }
            // A small inward margin protects the control bounds from rounding.
            if factor < 1.0 {
                factor = (factor - 16.0 * f64::EPSILON).max(0.0);
            }
            j.u[c] *= factor;
            j.v[c] *= factor;
            j.uv[c] *= factor;
        }
    }
}
fn basis(t: f64) -> ([f64; 4], [f64; 4]) {
    let s = 1.0 - t;
    (
        [s * s * s, 3.0 * s * s * t, 3.0 * s * t * t, t * t * t],
        [
            -3.0 * s * s,
            3.0 * s * s - 6.0 * s * t,
            6.0 * s * t - 3.0 * t * t,
            3.0 * t * t,
        ],
    )
}
fn evaluate<const N: usize>(patch: &Patch<N>, u: f64, v: f64) -> Jet<N> {
    let (bu, du) = basis(u);
    let (bv, dv) = basis(v);
    let mut out = Jet {
        value: [0.0; N],
        u: [0.0; N],
        v: [0.0; N],
        uv: [0.0; N],
    };
    for y in 0..4 {
        for x in 0..4 {
            for (c, value) in patch[y][x].iter().enumerate() {
                out.value[c] += value * bu[x] * bv[y];
                out.u[c] += patch[y][x][c] * du[x] * bv[y];
                out.v[c] += patch[y][x][c] * bu[x] * dv[y];
                out.uv[c] += patch[y][x][c] * du[x] * dv[y];
            }
        }
    }
    out
}
fn derivative_bounds<const N: usize>(patch: &Patch<N>) -> [[f64; 2]; N] {
    std::array::from_fn(|c| {
        std::array::from_fn(|axis| {
            let mut bound: f64 = 0.0;
            for (a, _) in patch.iter().enumerate() {
                for b in 0..3 {
                    let (p, q) = if axis == 0 {
                        (patch[a][b][c], patch[a][b + 1][c])
                    } else {
                        (patch[b][a][c], patch[b + 1][a][c])
                    };
                    // Outward-rounded subtraction and multiplication enclose the exact
                    // derivative of the actual encoded Bernstein controls.
                    let delta = q - p;
                    let lo = (delta.next_down() * 3.0).next_down();
                    let hi = (delta.next_up() * 3.0).next_up();
                    bound = bound.max(lo.abs().max(hi.abs()));
                }
            }
            bound
        })
    })
}
pub struct Prepared {
    columns: usize,
    rows: usize,
    origin: Point,
    size: Point,
    space: Interpolation,
    geometry: Vec<Patch<2>>,
    colors: Vec<Patch<4>>,
    pub contraction: f64,
    pub color_derivatives: [[f64; 2]; 4],
}
impl Mesh {
    pub fn texture_size(&self) -> Result<[usize; 2], Error> {
        if !(2..=MAX_AXIS).contains(&self.columns)
            || !(2..=MAX_AXIS).contains(&self.rows)
            || !(1..=256).contains(&self.svg_samples_per_cell)
        {
            return Err(limit(
                "Mesh requires 2..8 rows/columns and 1..256 texture samples per cell",
            ));
        }
        let size = [
            (self.columns - 1) * self.svg_samples_per_cell as usize,
            (self.rows - 1) * self.svg_samples_per_cell as usize,
        ];
        if size[0] * size[1] > MAX_TEXTURE_PIXELS {
            return Err(limit("Mesh texture exceeds 65536 samples"));
        }
        Ok(size)
    }
    pub fn prepare(&self, space: Interpolation) -> Result<Prepared, Error> {
        self.texture_size()?;
        if self.knots.len() != self.columns * self.rows {
            return Err(invalid("Mesh knot count must equal rows times columns"));
        }
        for c in 0..2 {
            if !self.origin[c].is_finite()
                || !self.size[c].is_finite()
                || !(0.001..=crate::model::MAX_COORDINATE).contains(&self.size[c])
                || self.origin[c].abs() > crate::model::MAX_COORDINATE
                || (self.origin[c] + self.size[c]).abs() > crate::model::MAX_COORDINATE
            {
                return Err(invalid(
                    "Mesh rectangle must be finite and inside coordinate limits",
                ));
            }
        }
        let mut offsets = Vec::new();
        let mut colors = Vec::new();
        for (i, knot) in self.knots.iter().enumerate() {
            if knot
                .offset
                .iter()
                .any(|v| !v.is_finite() || v.abs() > crate::model::MAX_COORDINATE)
            {
                return Err(invalid("Mesh offsets must be finite and bounded"));
            }
            if (i % self.columns == 0
                || i % self.columns + 1 == self.columns
                || i / self.columns == 0
                || i / self.columns + 1 == self.rows)
                && knot.offset != [0.0; 2]
            {
                return Err(invalid(
                    "Boundary mesh offsets must be zero; use the paint transform to place the rectangular domain",
                ));
            }
            offsets.push([
                knot.offset[0] / self.size[0] * (self.columns - 1) as f64,
                knot.offset[1] / self.size[1] * (self.rows - 1) as f64,
            ]);
            colors.push(crate::paint::color(knot.color, space));
        }
        let geometry = patches(
            &jets(offsets, self.columns, self.rows),
            self.columns,
            self.rows,
        );
        let mut colors = jets(colors, self.columns, self.rows);
        limit_colors(&mut colors, self.columns, self.rows);
        let colors = patches(&colors, self.columns, self.rows);
        let mut contraction: f64 = 0.0;
        let mut color_derivatives = [[0.0f64; 2]; 4];
        for patch in &geometry {
            for row in derivative_bounds(patch) {
                contraction = contraction.max((row[0] + row[1]).next_up());
            }
        }
        if contraction > MAX_CONTRACTION {
            return Err(Error::new(
                "MESH_GEOMETRY_LIMIT",
                "Mesh displacement derivative exceeds the certified contraction bound of 0.75; reduce interior offsets",
            ));
        }
        for patch in &colors {
            let bounds = derivative_bounds(patch);
            for c in 0..4 {
                for a in 0..2 {
                    color_derivatives[c][a] = color_derivatives[c][a].max(bounds[c][a]);
                }
            }
        }
        Ok(Prepared {
            columns: self.columns,
            rows: self.rows,
            origin: self.origin,
            size: self.size,
            space,
            geometry,
            colors,
            contraction,
            color_derivatives,
        })
    }
}
impl Prepared {
    fn locate(&self, uv: Point) -> (usize, Point) {
        let u = uv[0].clamp(0.0, (self.columns - 1) as f64);
        let v = uv[1].clamp(0.0, (self.rows - 1) as f64);
        let x = (u.floor() as usize).min(self.columns - 2);
        let y = (v.floor() as usize).min(self.rows - 2);
        (y * (self.columns - 1) + x, [u - x as f64, v - y as f64])
    }
    fn displacement(&self, uv: Point) -> Jet<2> {
        let (i, p) = self.locate(uv);
        evaluate(&self.geometry[i], p[0], p[1])
    }
    fn color(&self, uv: Point) -> Jet<4> {
        let (i, p) = self.locate(uv);
        evaluate(&self.colors[i], p[0], p[1])
    }
    pub fn inverse(&self, p: Point) -> Option<Point> {
        let far = [self.origin[0] + self.size[0], self.origin[1] + self.size[1]];
        if (0..2).any(|i| !p[i].is_finite() || p[i] < self.origin[i] || p[i] > far[i]) {
            return None;
        }
        // Classify against saved physical endpoints before normalizing. For a
        // fractional origin, (origin + size - origin) / size can exceed one.
        let normalized = std::array::from_fn::<_, 2, _>(|i| {
            if p[i] == far[i] {
                1.0
            } else {
                ((p[i] - self.origin[i]) / self.size[i]).clamp(0.0, 1.0)
            }
        });
        let target = [
            normalized[0] * (self.columns - 1) as f64,
            normalized[1] * (self.rows - 1) as f64,
        ];
        let mut uv = target;
        for _ in 0..INVERSE_STEPS {
            let w = self.displacement(uv).value;
            let next = [
                (target[0] - w[0]).clamp(0.0, (self.columns - 1) as f64),
                (target[1] - w[1]).clamp(0.0, (self.rows - 1) as f64),
            ];
            let delta = (uv[0] - next[0]).abs().max((uv[1] - next[1]).abs());
            uv = next;
            if delta <= 1e-13 * (1.0 - self.contraction) {
                break;
            }
        }
        Some(uv)
    }
    pub fn sample(&self, p: Point) -> [f64; 4] {
        self.inverse(p)
            .map(|uv| {
                crate::paint::output(self.color(uv).value.map(|v| v.clamp(0.0, 1.0)), self.space)
            })
            .unwrap_or([0.0; 4])
    }
    pub fn inspect(&self, uv: Point) -> Value {
        let w = self.displacement(uv);
        let c = self.color(uv);
        let scales = [
            self.size[0] / (self.columns - 1) as f64,
            self.size[1] / (self.rows - 1) as f64,
        ];
        let ends = [(self.columns - 1) as f64, (self.rows - 1) as f64];
        let point = std::array::from_fn::<_, 2, _>(|i| {
            if uv[i] == 0.0 {
                self.origin[i]
            } else if uv[i] == ends[i] {
                self.origin[i] + self.size[i]
            } else {
                (self.origin[i] + self.size[i] * ((uv[i] + w.value[i]) / ends[i]))
                    .clamp(self.origin[i], self.origin[i] + self.size[i])
            }
        });
        let u = [scales[0] * (1.0 + w.u[0]), scales[1] * w.u[1]];
        let v = [scales[0] * w.v[0], scales[1] * (1.0 + w.v[1])];
        json!({"parameter":uv,"point":point,"tangent_u":u,"tangent_v":v,"jacobian":u[0]*v[1]-u[1]*v[0],"interpolated_rgba":c.value,"color_du":c.u,"color_dv":c.v,"encoded_rgba":crate::paint::output(c.value.map(|v|v.clamp(0.0,1.0)),self.space),"inverse_parameter":self.inverse(point)})
    }
}
pub fn inspect(mesh: &Mesh, space: Interpolation, parameters: &[Point]) -> Result<Value, Error> {
    let p = mesh.prepare(space)?;
    if parameters.len() > MAX_SAMPLES {
        return Err(limit("Mesh inspection exceeds 1024 parameter samples"));
    }
    if parameters.iter().any(|v| {
        !v[0].is_finite()
            || !v[1].is_finite()
            || !(0.0..=(mesh.columns - 1) as f64).contains(&v[0])
            || !(0.0..=(mesh.rows - 1) as f64).contains(&v[1])
    }) {
        return Err(invalid(
            "Mesh inspection parameters lie outside the mesh grid",
        ));
    }
    Ok(
        json!({"columns":mesh.columns,"rows":mesh.rows,"patches":p.geometry.len(),"domain":[mesh.origin,mesh.size],"space":space,"geometry_contraction_upper_bound":p.contraction,"color_derivative_upper_bounds":p.color_derivatives,"continuity":"shared_knot_jets_C1_up_to_f64_roundoff","inverse_steps":INVERSE_STEPS,"samples":parameters.iter().map(|uv|p.inspect(*uv)).collect::<Vec<_>>()}),
    )
}
pub fn knot_edit(
    document: &mut Document,
    id: &str,
    target: Target,
    column: usize,
    row: usize,
    color: Option<Color>,
    offset: Option<Point>,
) -> Result<(), Error> {
    let i = crate::scene::index(document, id)?;
    crate::scene::check_unlocked(document, i, true)?;
    let paint = match (&mut document.items[i].content, target) {
        (Content::Vector { fill: Some(p), .. }, Target::Fill)
        | (Content::Fill { paint: p, .. }, Target::Fill) => p,
        (
            Content::Vector {
                stroke: Some(s), ..
            },
            Target::Stroke,
        ) => &mut s.color,
        _ => {
            return Err(invalid(
                "Mesh knot edit requires a mesh fill or vector stroke",
            ));
        }
    };
    let Paint::Field(Field::Mesh { mesh, space, .. }) = paint else {
        return Err(invalid("Selected paint is not a mesh"));
    };
    if column >= mesh.columns || row >= mesh.rows || color.is_none() && offset.is_none() {
        return Err(invalid(
            "Mesh knot edit requires an existing knot and a color or offset",
        ));
    }
    let knot = &mut mesh.knots[row * mesh.columns + column];
    if let Some(color) = color {
        knot.color = color;
    }
    if let Some(offset) = offset {
        knot.offset = offset;
    }
    mesh.prepare(*space)?;
    Ok(())
}

pub struct Texture {
    pub size: [usize; 2],
    pub png: Vec<u8>,
    pub premultiplied_error: [f64; 4],
}
pub fn texture(mesh: &Mesh, space: Interpolation) -> Result<Texture, Error> {
    let size = mesh.texture_size()?;
    let prepared = mesh.prepare(space)?;
    let mut rgba = Vec::with_capacity(size[0] * size[1] * 4);
    for y in 0..size[1] {
        for x in 0..size[0] {
            let p = [
                mesh.origin[0] + mesh.size[0] * (x as f64 + 0.5) / size[0] as f64,
                mesh.origin[1] + mesh.size[1] * (y as f64 + 0.5) / size[1] as f64,
            ];
            rgba.extend(
                prepared
                    .sample(p)
                    .map(|v| (v.clamp(0.0, 1.0) * 255.0).round() as u8),
            );
        }
    }
    let step = 1.0 / mesh.svg_samples_per_cell as f64 / (1.0 - prepared.contraction);
    let encoding_slope = if space == Interpolation::LinearRgb {
        12.92
    } else {
        1.0
    };
    let slopes = prepared.color_derivatives.map(|d| (d[0] + d[1]).next_up());
    // Interior reconstruction with source centers at most one texel away.
    // Premultiplied comparison remains meaningful at zero alpha.
    let error = std::array::from_fn(|c| {
        let slope = if c == 3 {
            slopes[3]
        } else {
            slopes[c] * encoding_slope + slopes[3]
        };
        (slope * step + 1.0 / 255.0 + 1e-10).min(1.0)
    });
    Ok(Texture {
        size,
        png: crate::render::encode_png(size[0] as u32, size[1] as u32, &rgba, 96.0)?,
        premultiplied_error: error,
    })
}
pub fn item_texture_pixels(item: &crate::model::Item) -> Result<usize, Error> {
    let mut total = 0;
    if let Content::Vector { fill, stroke, .. } = &item.content {
        for p in fill.iter().chain(stroke.iter().map(|s| &s.color)) {
            if let Paint::Field(Field::Mesh { mesh, .. }) = p {
                let size = mesh.texture_size()?;
                total += size[0] * size[1];
            }
        }
    }
    Ok(total)
}
pub fn svg_texture_pixels(document: &Document) -> Result<usize, Error> {
    let mut total = 0;
    for item in &document.items {
        total += item_texture_pixels(item)?;
    }
    for item in &document.items {
        if let Some(mask) = item.artwork_mask.as_ref().filter(|m| m.enabled) {
            for i in crate::scene::subtree(document, crate::scene::index(document, &mask.source)?) {
                total += item_texture_pixels(&document.items[i])?;
            }
        }
    }
    if total > MAX_SVG_TEXTURE_PIXELS {
        return Err(limit("SVG mesh textures exceed 131072 aggregate samples"));
    }
    Ok(total)
}
