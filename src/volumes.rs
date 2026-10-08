//! Original retained profile extrusion, rigid rotation and flat-lit vector projection.
use crate::{Error, geometry, model::*, scene};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::HashSet;
mod bsp;
mod profile;

pub const MAX_EDGES: usize = 128;
pub const MAX_FACES: usize = 192;
pub type Point3 = [f64; 3];
fn tolerance() -> f64 {
    0.1
}
#[derive(Clone, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Camera {
    #[default]
    Orthographic,
    Perspective {
        principal: Point,
        distance: f64,
        near: f64,
        far: f64,
    },
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Light {
    pub direction: Point3,
    pub color: Point3,
    pub intensity: f64,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Material {
    Unlit {
        color: [u8; 3],
    },
    Diffuse {
        color: [u8; 3],
        ambient: Point3,
        lights: Vec<Light>,
    },
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Spec {
    pub geometry: Geometry,
    #[serde(default)]
    pub fill_rule: FillRule,
    pub depth: f64,
    #[serde(default)]
    pub rotation: Point3,
    #[serde(default)]
    pub pivot: Point3,
    #[serde(default)]
    pub translation: Point3,
    #[serde(default)]
    pub camera: Camera,
    pub material: Material,
    #[serde(default = "tolerance")]
    pub tolerance: f64,
}
fn invalid(s: &str) -> Error {
    Error::new("INVALID_VOLUME", s)
}
fn numeric(s: &str) -> Error {
    Error::new("NUMERIC_PRECISION", s)
}
fn range(v: f64, lo: f64, hi: f64) -> bool {
    v.is_finite() && (lo..=hi).contains(&v)
}
pub(crate) fn dot(a: Point3, b: Point3) -> f64 {
    a.into_iter().zip(b).map(|(a, b)| a * b).sum()
}
fn sub(a: Point3, b: Point3) -> Point3 {
    std::array::from_fn(|i| a[i] - b[i])
}
fn normalized(v: Point3) -> Result<Point3, Error> {
    let n = dot(v, v).sqrt();
    if !range(n, 1e-8, 65536.) {
        return Err(invalid("A finite nonzero bounded direction is required"));
    }
    Ok(v.map(|v| v / n))
}
fn sincos(angle: f64) -> (f64, f64) {
    match angle.rem_euclid(360.) {
        0. => (0., 1.),
        90. => (1., 0.),
        180. => (0., -1.),
        270. => (-1., 0.),
        value => value.to_radians().sin_cos(),
    }
}
fn rotate(mut p: Point3, angles: Point3) -> Point3 {
    for (axis, angle) in angles.into_iter().enumerate() {
        let (s, c) = sincos(angle);
        let (a, b) = match axis {
            0 => (1, 2),
            1 => (2, 0),
            _ => (0, 1),
        };
        let (x, y) = (p[a], p[b]);
        p[a] = c * x - s * y;
        p[b] = s * x + c * y;
    }
    p
}
fn placed(s: &Spec, p: Point3) -> Result<Point3, Error> {
    let q = rotate(sub(p, s.pivot), s.rotation);
    let q = std::array::from_fn(|i| q[i] + s.pivot[i] + s.translation[i]);
    if q.iter()
        .any(|&x| !range(x, -MAX_COORDINATE, MAX_COORDINATE))
    {
        return Err(invalid("Rotated volume exceeds coordinate limits"));
    }
    Ok(q)
}
fn project(camera: &Camera, p: Point3) -> Result<Point, Error> {
    let q = match *camera {
        Camera::Orthographic => [p[0], p[1]],
        Camera::Perspective {
            principal,
            distance,
            near,
            far,
        } => {
            let z = distance - p[2];
            if z < near || z > far {
                return Err(Error::new(
                    "UNSUPPORTED",
                    "Volume crosses the declared camera depth range; clipping is not implicit",
                ));
            }
            [
                principal[0] + (p[0] - principal[0]) * distance / z,
                principal[1] + (p[1] - principal[1]) * distance / z,
            ]
        }
    };
    if q.iter()
        .any(|&x| !range(x, -MAX_COORDINATE, MAX_COORDINATE))
    {
        return Err(invalid("Projected volume exceeds coordinate limits"));
    }
    Ok(q)
}
pub(crate) fn stored(s: &Spec) -> Result<usize, Error> {
    let commands = geometry::validate_geometry(&s.geometry)?;
    if !range(s.depth, 0., 4096.)
        || !range(s.tolerance, 0.000001, 1.)
        || s.rotation.iter().any(|&v| !range(v, -360000., 360000.))
        || s.pivot
            .iter()
            .chain(&s.translation)
            .any(|&v| !range(v, -MAX_COORDINATE, MAX_COORDINATE))
    {
        return Err(invalid(
            "Depth, tolerance or rigid-transform controls exceed declared bounds",
        ));
    }
    if let Camera::Perspective {
        principal,
        distance,
        near,
        far,
    } = s.camera
        && (principal
            .iter()
            .any(|&v| !range(v, -MAX_COORDINATE, MAX_COORDINATE))
            || !range(distance, 1., 32768.)
            || !range(near, 0.01, distance)
            || !range(far, distance, 65536.)
            || distance / near > 128.)
    {
        return Err(invalid(
            "Perspective requires finite distance 1..32768, near 0.01..distance, far distance..65536 and magnification at most 128",
        ));
    }
    if let Material::Diffuse {
        ambient, lights, ..
    } = &s.material
    {
        if ambient.iter().any(|&v| !range(v, 0., 1.)) || lights.len() > 8 {
            return Err(invalid(
                "Diffuse material requires bounded ambient RGB and at most eight lights",
            ));
        }
        for light in lights {
            normalized(light.direction)?;
            if light.color.iter().any(|&v| !range(v, 0., 1.)) || !range(light.intensity, 0., 8.) {
                return Err(invalid(
                    "Light color must be linear RGB 0..1 and intensity 0..8",
                ));
            }
        }
    }
    Ok(commands)
}
fn shade(material: &Material, normal: Point3) -> Result<[f64; 4], Error> {
    let decode = |v: f64| {
        if v <= 0.04045 {
            v / 12.92
        } else {
            ((v + 0.055) / 1.055).powf(2.4)
        }
    };
    let encode = |v: f64| {
        if v <= 0.0031308 {
            12.92 * v
        } else {
            1.055 * v.powf(1. / 2.4) - 0.055
        }
    };
    let color = match material {
        Material::Unlit { color } => color.map(|v| v as f64 / 255.),
        Material::Diffuse {
            color,
            ambient,
            lights,
        } => {
            let mut energy = *ambient;
            for light in lights {
                let amount = dot(normal, normalized(light.direction)?).max(0.) * light.intensity;
                for (e, c) in energy.iter_mut().zip(light.color) {
                    *e += amount * c;
                }
            }
            std::array::from_fn(|i| {
                encode((decode(color[i] as f64 / 255.) * energy[i]).clamp(0., 1.))
            })
        }
    };
    Ok([color[0], color[1], color[2], 1.])
}
#[derive(Clone, Debug)]
pub(crate) struct Face {
    pub contours: Vec<Vec<Point3>>,
    pub normal: Point3,
    pub part: String,
    pub rgba: [f64; 4],
}
impl Face {
    fn visible(&self, camera: &Camera) -> bool {
        let v = match *camera {
            Camera::Orthographic => [0., 0., 1.],
            Camera::Perspective {
                principal,
                distance,
                ..
            } => sub([principal[0], principal[1], distance], self.contours[0][0]),
        };
        dot(self.normal, v) > 0.
    }
    fn geometry(&self, camera: &Camera) -> Result<Geometry, Error> {
        let mut commands = Vec::new();
        for points in &self.contours {
            commands.push(PathCommand::Move {
                to: project(camera, points[0])?,
            });
            for &p in points.iter().skip(1) {
                commands.push(PathCommand::Line {
                    to: project(camera, p)?,
                });
            }
            commands.push(PathCommand::Close {});
        }
        Ok(Geometry::Path { commands })
    }
}
pub(crate) struct Plan {
    pub faces: Vec<Face>,
    pub bounds: geometry::Bounds,
    pub projected_vertices: Vec<Point>,
    pub profile_edges: usize,
    pub error: f64,
}
pub(crate) fn plan(s: &Spec) -> Result<Plan, Error> {
    stored(s)?;
    let profile = profile::build(s)?;
    let mut faces = vec![];
    let front: Vec<Vec<Point3>> = profile
        .contours
        .iter()
        .map(|c| c.iter().map(|p| placed(s, [p[0], p[1], 0.])).collect())
        .collect::<Result<_, _>>()?;
    let back: Vec<Vec<Point3>> = profile
        .contours
        .iter()
        .map(|c| {
            c.iter()
                .rev()
                .map(|p| placed(s, [p[0], p[1], -s.depth]))
                .collect()
        })
        .collect::<Result<_, _>>()?;
    let projected_vertices = front
        .iter()
        .chain(&back)
        .flatten()
        .map(|&p| project(&s.camera, p))
        .collect::<Result<Vec<_>, _>>()?;
    let mut projected = projected_vertices.iter().copied();
    let first = projected
        .next()
        .ok_or_else(|| invalid("No filled profile"))?;
    let mut bounds = [first[0], first[1], first[0], first[1]];
    for p in projected {
        bounds = scene::union(bounds, [p[0], p[1], p[0], p[1]]);
    }
    for (part, contours, n) in [
        ("front", front, [0., 0., 1.]),
        ("back", back, [0., 0., -1.]),
    ] {
        let normal = rotate(n, s.rotation);
        faces.push(Face {
            contours,
            normal,
            part: part.into(),
            rgba: shade(&s.material, normal)?,
        });
    }
    if s.depth > 0. {
        for (ci, c) in profile.contours.iter().enumerate() {
            for (i, &a) in c.iter().enumerate() {
                let b = c[(i + 1) % c.len()];
                let normal = rotate(normalized([b[1] - a[1], a[0] - b[0], 0.])?, s.rotation);
                let points = [
                    [a[0], a[1], 0.],
                    [a[0], a[1], -s.depth],
                    [b[0], b[1], -s.depth],
                    [b[0], b[1], 0.],
                ];
                let contours = vec![
                    points
                        .into_iter()
                        .map(|p| placed(s, p))
                        .collect::<Result<_, _>>()?,
                ];
                faces.push(Face {
                    contours,
                    normal,
                    part: format!("side-{ci}-{i}"),
                    rgba: shade(&s.material, normal)?,
                });
            }
        }
    }
    faces.retain(|f| f.visible(&s.camera));
    let faces = bsp::ordered(faces, &s.camera)?;
    let mut commands = 0;
    for f in &faces {
        commands += geometry::validate_geometry(&f.geometry(&s.camera)?)?;
    }
    if commands > MAX_SEGMENTS {
        return Err(limit("Projected volume exceeds 4096 commands"));
    }
    Ok(Plan {
        faces,
        bounds,
        projected_vertices,
        profile_edges: profile.edges,
        error: profile.error,
    })
}
fn generated(item: &Item, used: &mut HashSet<String>) -> Result<Vec<Item>, Error> {
    let Content::Volume { volume } = &item.content else {
        return Err(invalid("A volume item is required"));
    };
    let plan = plan(volume)?;
    let mut out = vec![Item {
        content: Content::Group {
            isolated: true,
            role: GroupRole::Group,
            knockout: false,
        },
        ..item.clone()
    }];
    for (index, face) in plan.faces.iter().enumerate() {
        let prefix = format!(
            "ib-volume-{}",
            &crate::assets::sha256(&serde_json::to_vec(&(&item.id, index)).unwrap())[..24]
        );
        let mut id = prefix.clone();
        let mut n = 0;
        while !used.insert(id.clone()) {
            n += 1;
            id = format!("{prefix}-{n}");
        }
        let mut child:Item=serde_json::from_value(json!({"id":id,"parent":item.id,"name":face.part,"content":{"type":"vector","geometry":face.geometry(&volume.camera)?,"fill":{"rgba":face.rgba}}})).map_err(|_|invalid("Unable to create projected face"))?;
        child.locked = false;
        out.push(child);
    }
    Ok(out)
}
pub(crate) fn evaluate(d: &Document) -> Result<Option<Document>, Error> {
    if !d
        .items
        .iter()
        .any(|i| matches!(i.content, Content::Volume { .. }))
    {
        return Ok(None);
    }
    let mut used = d.items.iter().map(|i| i.id.clone()).collect();
    let mut items = vec![];
    for i in &d.items {
        if matches!(i.content, Content::Volume { .. }) {
            items.extend(generated(i, &mut used)?);
        } else {
            items.push(i.clone());
        }
        if items.len() > d.resource_profile.items() {
            return Err(limit(
                "Evaluated volume exceeds the document resource-profile item budget",
            ));
        }
    }
    let mut copy = d.clone();
    copy.items = items;
    copy.variants = None;
    Ok(Some(copy))
}
pub(crate) fn validate(d: &Document) -> Result<(), Error> {
    if let Some(copy) = evaluate(d)? {
        crate::model::validate(&copy)?;
    }
    Ok(())
}
pub(crate) fn bounds(s: &Spec, matrix: Matrix) -> Result<geometry::Bounds, Error> {
    Ok(plan(s)?
        .projected_vertices
        .into_iter()
        .map(|p| {
            let p = geometry::map(matrix, p);
            [p[0], p[1], p[0], p[1]]
        })
        .reduce(scene::union)
        .unwrap())
}
pub(crate) fn expand(d: &mut Document, index: usize) -> Result<Value, Error> {
    let mut used = d.items.iter().map(|i| i.id.clone()).collect();
    let items = generated(&d.items[index], &mut used)?;
    let ids: Vec<_> = items.iter().skip(1).map(|i| i.id.clone()).collect();
    d.items.splice(index..=index, items);
    Ok(
        json!({"created":ids,"source_retained_in_input":true,"losses":["Projected ordinary vector faces freeze profile tessellation, extrusion, rotation, camera and lighting. Keep the original snapshot or undo history for dimensional editing."]}),
    )
}
pub fn inspect(d: &Document, id: &str) -> Result<Value, Error> {
    crate::validate(d)?;
    let i = scene::index(d, id)?;
    let Content::Volume { volume } = &d.items[i].content else {
        return Err(invalid("Volume inspection requires a volume item"));
    };
    let p = plan(volume)?;
    let faces=p.faces.iter().map(|f|Ok(json!({"part":f.part,"normal":f.normal,"rgba":f.rgba,"vertices":f.contours,"geometry":f.geometry(&volume.camera)?}))).collect::<Result<Vec<_>,Error>>()?;
    Ok(
        json!({"id":id,"source":volume,"profile_edges":p.profile_edges,"source_curve_error_bound":p.error,"local_bounds":p.bounds,"faces":faces,"order":"far_to_near_bsp","lighting_space":"linear_srgb_diffuse_then_encoded_srgb_paints","dependencies":"built_in_cpu_geometry_and_materials;no_models_gpu_files_or_network","source_preserved":true}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn nonfinite_library_controls_and_zero_light_directions_fail() {
        let base: Spec = serde_json::from_value(json!({"geometry":{"shape":"rect","x":0,"y":0,"width":4,"height":4},"depth":2,"material":{"type":"unlit","color":[10,20,30]}})).unwrap();
        for value in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            let mut s = base.clone();
            s.depth = value;
            assert!(stored(&s).is_err());
            let mut s = base.clone();
            s.rotation[0] = value;
            assert!(stored(&s).is_err());
            let mut s = base.clone();
            s.pivot[1] = value;
            assert!(stored(&s).is_err());
            let mut s = base.clone();
            s.camera = Camera::Perspective {
                principal: [0., 0.],
                distance: 100.,
                near: 1.,
                far: value,
            };
            assert!(stored(&s).is_err());
            let mut s = base.clone();
            s.material = Material::Diffuse {
                color: [10, 20, 30],
                ambient: [value, 0., 0.],
                lights: vec![],
            };
            assert!(stored(&s).is_err());
        }
        let mut s = base;
        s.material = Material::Diffuse {
            color: [10, 20, 30],
            ambient: [0.; 3],
            lights: vec![Light {
                direction: [0.; 3],
                color: [1.; 3],
                intensity: 1.,
            }],
        };
        assert!(stored(&s).is_err());
    }
}
