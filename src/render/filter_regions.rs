//! Conservative source neighborhoods for spatially varying filter reads.
//! A dependency path follows output-to-source order through parents and clips.
use super::*;
use crate::{control::Control, filters::Operator};

use crate::limits::render_filter_regions::MAX_REFERENCES;
type Region = [u32; 4];

pub(super) enum Step {
    Local(u32),
    Radial {
        center: Point,
        samples: Vec<[f64; 3]>,
    },
    Twist {
        inverse: Matrix,
        world: Matrix,
        center: Point,
        radius: f64,
        source: [f64; 4],
        displacement: f64,
        scale: f64,
    },
}

fn margin(values: &[f64]) -> f64 {
    1e-9 + 64.0 * f64::EPSILON * values.iter().map(|v| v.abs()).sum::<f64>()
}

fn mapped_bounds(matrix: Matrix, bounds: [f64; 4]) -> [f64; 4] {
    let mut out = [
        f64::INFINITY,
        f64::INFINITY,
        f64::NEG_INFINITY,
        f64::NEG_INFINITY,
    ];
    for x in [bounds[0], bounds[2]] {
        for y in [bounds[1], bounds[3]] {
            let p = geometry::map(matrix, [x, y]);
            if p.iter().any(|v| !v.is_finite()) {
                return [
                    f64::NEG_INFINITY,
                    f64::NEG_INFINITY,
                    f64::INFINITY,
                    f64::INFINITY,
                ];
            }
            for i in 0..2 {
                let error = margin(&[matrix[i] * x, matrix[i + 2] * y, matrix[i + 4], p[i]]);
                out[i] = out[i].min(p[i] - error);
                out[i + 2] = out[i + 2].max(p[i] + error);
            }
        }
    }
    out
}

impl Step {
    pub fn new(operator: &Operator, world: Matrix, scale: u32) -> Result<Self, Error> {
        if let Some(radius) = super::tiled::local_support(operator, scale) {
            return Ok(Self::Local(radius));
        }
        let s = scale as f64;
        Ok(match operator {
            Operator::Radial {
                center,
                angle,
                zoom,
                samples,
            } => {
                let center = geometry::map(world, *center).map(|v| v * s - 0.5);
                if center.iter().any(|v| !v.is_finite()) {
                    return Ok(Self::Local(u32::MAX));
                }
                let samples = (0..*samples)
                    .map(|j| {
                        let t = j as f64 / (*samples - 1) as f64 - 0.5;
                        let (sn, cs) = (angle.to_radians() * t).sin_cos();
                        [sn, cs, 1.0 + zoom * t]
                    })
                    .collect();
                Self::Radial { center, samples }
            }
            Operator::Creative { operator } => {
                let crate::creative_filters::Operator::Twist {
                    center,
                    radius,
                    angle,
                } = **operator
                else {
                    unreachable!()
                };
                if angle == 0.0 {
                    return Ok(Self::Local(0));
                }
                // Rotation remains inside its source circle. Its enclosing
                // square is conservative under every finite affine transform.
                let source = mapped_bounds(
                    world,
                    [
                        center[0] - radius,
                        center[1] - radius,
                        center[0] + radius,
                        center[1] + radius,
                    ],
                )
                .map(|v| v * s - 0.5);
                Self::Twist {
                    inverse: geometry::inverse(world)?,
                    world,
                    center,
                    radius,
                    source,
                    // |rotation(q)-q| <= min(2r, |angle| r (1-r/R)^2).
                    // The second profile has maximum 4R/27 on [0,R].
                    displacement: radius * 2.0_f64.min(angle.to_radians().abs() * 4.0 / 27.0),
                    scale: s,
                }
            }
            _ => unreachable!(),
        })
    }

    fn cost(&self) -> u64 {
        match self {
            Self::Local(_) => 1,
            Self::Radial { samples, .. } => 32 * samples.len() as u64,
            Self::Twist { .. } => 128,
        }
    }

    fn radius(&self, region: Region, extent: [u32; 2]) -> u32 {
        let cap = extent[0].max(extent[1]);
        let mut distance: f64 = 0.0;
        match self {
            Self::Local(radius) => return *radius,
            Self::Radial { center, samples } => {
                // Each discrete sample is affine. The extrema of its offset
                // lie at rectangle corners; account for arithmetic roundoff.
                for x in [region[0], region[2] - 1] {
                    for y in [region[1], region[3] - 1] {
                        let a = x as f64 - center[0];
                        let b = y as f64 - center[1];
                        for &[sn, cs, k] in samples {
                            let dx = a * (cs * k - 1.0) - b * sn * k;
                            let dy = a * sn * k + b * (cs * k - 1.0);
                            let error = margin(&[x as f64, y as f64, center[0], center[1], a, b])
                                * (1.0 + k.abs());
                            distance = distance.max(dx.abs().max(dy.abs()) + error);
                        }
                    }
                }
            }
            Self::Twist {
                inverse,
                world,
                center,
                radius,
                source,
                displacement,
                scale,
            } => {
                if source.iter().any(|v| !v.is_finite()) {
                    return cap;
                }
                let bounds = mapped_bounds(
                    *inverse,
                    [
                        (region[0] as f64 + 0.5) / scale,
                        (region[1] as f64 + 0.5) / scale,
                        (region[2] as f64 - 0.5) / scale,
                        (region[3] as f64 - 0.5) / scale,
                    ],
                );
                let dx = (bounds[0] - center[0]).max(0.0).max(center[0] - bounds[2]);
                let dy = (bounds[1] - center[1]).max(0.0).max(center[1] - bounds[3]);
                if dx.hypot(dy) > radius + margin(&[dx, dy, *radius]) {
                    return 0;
                }
                for i in 0..2 {
                    distance = distance
                        .max((source[i] - (region[i + 2] - 1) as f64).abs())
                        .max((source[i + 2] - region[i] as f64).abs());
                }
                let mut motion: f64 = 0.0;
                for x in [region[0], region[2] - 1] {
                    for y in [region[1], region[3] - 1] {
                        let p = [(x as f64 + 0.5) / scale, (y as f64 + 0.5) / scale];
                        let q = geometry::map(*inverse, p);
                        let back = geometry::map(*world, q);
                        let q_error = (0..2)
                            .map(|i| {
                                margin(&[
                                    inverse[i] * p[0],
                                    inverse[i + 2] * p[1],
                                    inverse[i + 4],
                                    q[i],
                                ])
                            })
                            .fold(0.0_f64, f64::max);
                        for i in 0..2 {
                            let norm = world[i].hypot(world[i + 2]);
                            let error = (world[i].abs() + world[i + 2].abs())
                                * (2.0 * q_error + margin(&[center[0], center[1], *radius]))
                                + 2.0
                                    * margin(&[
                                        world[i] * q[0],
                                        world[i + 2] * q[1],
                                        world[i + 4],
                                        back[i],
                                        p[i],
                                    ]);
                            motion = motion.max(
                                (displacement * norm + (back[i] - p[i]).abs() + error) * scale,
                            );
                        }
                    }
                }
                if motion.is_finite() {
                    distance = distance.min(motion);
                }
            }
        }
        // Symmetric expansion also contains reflected/clamped source samples
        // at the real viewport border. The bilinear stencil needs one neighbor.
        if !distance.is_finite() {
            cap
        } else {
            (distance.ceil() as u32).saturating_add(2).min(cap)
        }
    }
}

pub(super) struct Plan {
    steps: Vec<Step>,
    paths: Vec<Vec<usize>>,
    pub work: u64,
    pub buffer_values: u64,
}

impl Plan {
    pub fn new(document: &Document, scale: u32, control: &Control) -> Result<Self, Error> {
        let worlds = scene::world_transforms(document, control)?;
        let ids: BTreeMap<_, _> = document
            .items
            .iter()
            .enumerate()
            .map(|(i, item)| (item.id.as_str(), i))
            .collect();
        let mut steps = Vec::new();
        let mut own = Vec::new();
        let mut effects = Vec::new();
        let mut sample_count = 0;
        for (i, item) in document.items.iter().enumerate() {
            control.check()?;
            let effect = crate::effects::support(item, scale, document.global_light);
            effects.push((effect != 0).then(|| {
                let n = steps.len();
                steps.push(Step::Local(effect));
                n
            }));
            let mut refs: Vec<_> = effects[i].into_iter().collect();
            for filter in item
                .filters
                .iter()
                .rev()
                .filter(|f| f.enabled && f.opacity != 0.0)
            {
                if let Operator::Radial { samples, .. } = filter.operator {
                    sample_count += samples as usize;
                    if sample_count > MAX_REFERENCES {
                        return Err(limit(&format!(
                            "Filter source mappings exceed {MAX_REFERENCES} samples"
                        )));
                    }
                }
                refs.push(steps.len());
                steps.push(Step::new(&filter.operator, worlds[i], scale)?);
            }
            own.push(refs);
        }
        let mut paths = Vec::new();
        let mut references = 0;
        let mut work = 0;
        for i in 0..document.items.len() {
            control.check()?;
            if own[i].is_empty() {
                continue;
            }
            let mut chain = scene::ancestors(document, i)?;
            chain.reverse();
            chain.push(i);
            let mut path = Vec::new();
            for p in chain {
                if let Some(base) = document.items[p].clip_to.as_deref() {
                    path.extend(effects[ids[base]]);
                }
                path.extend(&own[p]);
            }
            references += path.len();
            if references > MAX_REFERENCES {
                return Err(limit(&format!(
                    "Filter dependency paths exceed {MAX_REFERENCES} references"
                )));
            }
            work += path.iter().map(|&i| steps[i].cost()).sum::<u64>();
            paths.push(path);
        }
        let bytes = steps.capacity() * std::mem::size_of::<Step>()
            + paths.capacity() * std::mem::size_of::<Vec<usize>>()
            + paths
                .iter()
                .map(|p| p.capacity() * std::mem::size_of::<usize>())
                .sum::<usize>()
            + steps
                .iter()
                .map(|s| match s {
                    Step::Radial { samples, .. } => {
                        samples.capacity() * std::mem::size_of::<[f64; 3]>()
                    }
                    _ => 0,
                })
                .sum::<usize>();
        Ok(Self {
            steps,
            paths,
            work,
            buffer_values: (bytes as u64).div_ceil(8),
        })
    }

    pub fn region(
        &self,
        origin: [u32; 2],
        size: [u32; 2],
        extent: [u32; 2],
        control: &Control,
    ) -> Result<([u32; 2], [u32; 2]), Error> {
        let input = [
            origin[0],
            origin[1],
            origin[0] + size[0],
            origin[1] + size[1],
        ];
        let mut result = input;
        for path in &self.paths {
            control.check()?;
            let mut region = input;
            for &step in path {
                let radius = self.steps[step].radius(region, extent);
                for i in 0..2 {
                    region[i] = region[i].saturating_sub(radius);
                    region[i + 2] = region[i + 2].saturating_add(radius).min(extent[i]);
                }
            }
            for i in 0..2 {
                result[i] = result[i].min(region[i]);
                result[i + 2] = result[i + 2].max(region[i + 2]);
            }
        }
        Ok((
            [result[0], result[1]],
            [result[2] - result[0], result[3] - result[1]],
        ))
    }
}
