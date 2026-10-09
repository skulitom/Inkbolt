//! Bounded original plane partitioning orders concave opaque extrusion faces.
use super::*;
fn epsilon(f: &Face) -> f64 {
    f.contours
        .iter()
        .flatten()
        .flatten()
        .map(|v| v.abs())
        .fold(1., f64::max)
        * f64::EPSILON
        * 2048.
}
fn split(f: &Face, n: Point3, d: f64, positive: bool, eps: f64) -> Option<Face> {
    let mut contours = vec![];
    for p in &f.contours {
        let mut out = vec![];
        for (i, &a) in p.iter().enumerate() {
            let b = p[(i + 1) % p.len()];
            let u = dot(n, a) - d;
            let v = dot(n, b) - d;
            let inside = |x: f64| if positive { x >= -eps } else { x <= eps };
            if inside(u) {
                out.push(a);
            }
            if (u > eps && v < -eps) || (u < -eps && v > eps) {
                let t = u / (u - v);
                out.push(std::array::from_fn(|k| a[k] + (b[k] - a[k]) * t));
            }
        }
        out.dedup();
        if out.len() > 1 && out.first() == out.last() {
            out.pop();
        }
        if out.len() >= 3 {
            contours.push(out);
        }
    }
    (!contours.is_empty()).then(|| Face {
        contours,
        ..f.clone()
    })
}
fn recurse(
    mut faces: Vec<Face>,
    camera: &Camera,
    depth: usize,
    budget: &mut usize,
    control: &crate::control::Control,
) -> Result<Vec<Face>, Error> {
    control.check()?;
    if faces.is_empty() {
        return Ok(vec![]);
    }
    if depth > 128 {
        return Err(limit("Volume face partition exceeds 128 levels"));
    }
    let root = faces.remove(0);
    let n = root.normal;
    let d = dot(n, root.contours[0][0]);
    let mut eps = epsilon(&root);
    let mut coplanar = vec![root];
    let mut front = vec![];
    let mut back = vec![];
    for f in faces {
        control.check()?;
        eps = eps.max(epsilon(&f));
        let mut positive = false;
        let mut negative = false;
        for &p in f.contours.iter().flatten() {
            let v = dot(n, p) - d;
            positive |= v > eps;
            negative |= v < -eps;
        }
        match (positive, negative) {
            (false, false) => coplanar.push(f),
            (true, false) => front.push(f),
            (false, true) => back.push(f),
            (true, true) => {
                *budget += 1;
                if *budget > MAX_FACES {
                    return Err(limit("Volume partition exceeds 192 faces"));
                }
                let a = split(&f, n, d, true, eps)
                    .ok_or_else(|| numeric("Volume split lost its front face"))?;
                let b = split(&f, n, d, false, eps)
                    .ok_or_else(|| numeric("Volume split lost its back face"))?;
                front.push(a);
                back.push(b);
            }
        }
    }
    let side = match *camera {
        Camera::Orthographic => n[2],
        Camera::Perspective {
            principal,
            distance,
            ..
        } => dot(n, [principal[0], principal[1], distance]) - d,
    };
    let (far, near) = if side >= 0. {
        (back, front)
    } else {
        (front, back)
    };
    let mut out = recurse(far, camera, depth + 1, budget, control)?;
    out.extend(coplanar);
    out.extend(recurse(near, camera, depth + 1, budget, control)?);
    Ok(out)
}
pub(super) fn ordered(
    faces: Vec<Face>,
    camera: &Camera,
    control: &crate::control::Control,
) -> Result<Vec<Face>, Error> {
    let mut budget = faces.len();
    if budget > MAX_FACES {
        return Err(limit("Volume exceeds 192 faces"));
    }
    recurse(faces, camera, 0, &mut budget, control)
}
