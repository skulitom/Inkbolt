//! Original local layout assistance with exact ordered shelf optimization.
pub mod segment;
use crate::{Error, control::Control, geometry, model::*, scene};
use num_rational::BigRational as R;
use num_traits::{ToPrimitive, Zero};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

pub const MAX_ITEMS: usize = 64;
pub const PLACEMENT_ERROR: f64 = 1e-7;

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Alignment {
    #[default]
    Start,
    Center,
    End,
}
impl Alignment {
    fn offset(self, spare: R) -> R {
        match self {
            Self::Start => R::zero(),
            Self::Center => spare / R::from_integer(2.into()),
            Self::End => spare,
        }
    }
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Layout {
    pub ids: Vec<String>,
    pub bounds: geometry::Bounds,
    #[serde(default)]
    pub gap: Point,
    #[serde(default)]
    pub horizontal: Alignment,
    #[serde(default)]
    pub vertical: Alignment,
}
fn invalid(message: &str) -> Error {
    Error::new("INVALID_ASSISTANCE", message)
}
fn exact(value: f64) -> R {
    R::from_float(value).expect("validated finite coordinate")
}
fn number(value: &R) -> f64 {
    value.to_f64().expect("bounded rational coordinate")
}
fn fraction(value: &R) -> Value {
    json!({"numerator":value.numer().to_string(),"denominator":value.denom().to_string()})
}
#[derive(Clone)]
struct Solution {
    height: R,
    ends: Vec<usize>,
}
impl Solution {
    fn better_than(&self, other: &Self) -> bool {
        (&self.height, self.ends.len(), &self.ends) < (&other.height, other.ends.len(), &other.ends)
    }
}
struct Plan {
    moves: Vec<(usize, Matrix)>,
    report: Value,
}

fn plan(document: &Document, options: &Layout, control: &Control) -> Result<Plan, Error> {
    control.check()?;
    validate(document)?;
    if options.ids.is_empty() || options.ids.len() > MAX_ITEMS {
        return Err(Error::new(
            "RESOURCE_LIMIT",
            "Automatic layout requires 1..64 IDs",
        ));
    }
    let area = options.bounds;
    if area
        .iter()
        .any(|v| !v.is_finite() || v.abs() > MAX_COORDINATE)
        || area[0] >= area[2]
        || area[1] >= area[3]
        || options
            .gap
            .iter()
            .any(|v| !v.is_finite() || *v < 0.0 || *v > MAX_COORDINATE)
    {
        return Err(invalid(
            "Layout requires finite positive ordered bounds and nonnegative gaps within coordinate limits",
        ));
    }
    let selected = scene::selection(document, &options.ids, true)?;
    let mut bounds = Vec::new();
    for &i in &selected {
        control.check()?;
        scene::check_unlocked(document, i, true)?;
        if !scene::effective_visible(document, i)? {
            return Err(invalid(
                "Automatic layout requires visible printing artwork",
            ));
        }
        for j in scene::subtree(document, i) {
            if matches!(
                document.items[j].content,
                Content::WorkPath { .. }
                    | Content::Adjustment { .. }
                    | Content::MaskSource {}
                    | Content::ComponentSource {}
                    | Content::Frame { .. }
            ) {
                return Err(invalid(
                    "Frames, adjustments and nonprinting sources cannot participate in automatic layout",
                ));
            }
        }
        let b = scene::bounds(document, i)?.ok_or_else(|| invalid("Layout item has no bounds"))?;
        if b.iter().any(|v| !v.is_finite()) || b[0] >= b[2] || b[1] >= b[3] {
            return Err(invalid(
                "Layout item must have positive finite two-dimensional bounds",
            ));
        }
        bounds.push(b);
    }
    let sizes: Vec<_> = bounds
        .iter()
        .map(|b| [exact(b[2]) - exact(b[0]), exact(b[3]) - exact(b[1])])
        .collect();
    let width = exact(area[2]) - exact(area[0]);
    let height = exact(area[3]) - exact(area[1]);
    let [gx, gy] = options.gap.map(exact);
    let n = selected.len();
    let mut best: Vec<Option<Solution>> = vec![None; n + 1];
    best[n] = Some(Solution {
        height: R::zero(),
        ends: vec![],
    });
    let mut candidates = 0;
    for start in (0..n).rev() {
        control.check()?;
        let mut w = R::zero();
        let mut h = R::zero();
        for end in start + 1..=n {
            candidates += 1;
            w += &sizes[end - 1][0];
            if end > start + 1 {
                w += &gx;
            }
            h = h.max(sizes[end - 1][1].clone());
            if w > width {
                break;
            }
            if let Some(tail) = &best[end] {
                let mut ends = vec![end];
                ends.extend_from_slice(&tail.ends);
                let candidate = Solution {
                    height: &h + &tail.height + if end == n { R::zero() } else { gy.clone() },
                    ends,
                };
                if best[start]
                    .as_ref()
                    .is_none_or(|old| candidate.better_than(old))
                {
                    best[start] = Some(candidate);
                }
            }
        }
    }
    let solution = best[0].as_ref().ok_or_else(|| {
        Error::new(
            "LAYOUT_NO_FIT",
            "At least one item exceeds the available row width",
        )
    })?;
    if solution.height > height {
        return Err(Error::new(
            "LAYOUT_NO_FIT",
            "Minimum ordered row height exceeds the available area",
        ));
    }
    let mut candidate = document.clone();
    let mut moves = Vec::new();
    let mut placements = Vec::new();
    let mut rows = Vec::new();
    let mut start = 0;
    let mut y = exact(area[1]);
    let mut maximum_error = 0.0_f64;
    for (row, &end) in solution.ends.iter().enumerate() {
        control.check()?;
        let row_width = sizes[start..end].iter().map(|s| s[0].clone()).sum::<R>()
            + &gx * R::from_integer((end - start - 1).into());
        let row_height = sizes[start..end]
            .iter()
            .map(|s| s[1].clone())
            .max()
            .unwrap();
        let mut x = exact(area[0]) + options.horizontal.offset(&width - &row_width);
        rows.push(json!({"start":start,"end":end,"width":number(&row_width),"height":number(&row_height),"y":number(&y)}));
        for k in start..end {
            let i = selected[k];
            let top = &y + options.vertical.offset(&row_height - &sizes[k][1]);
            let target = [&x, &top, &(&x + &sizes[k][0]), &(&top + &sizes[k][1])].map(number);
            let dx = number(&(&x - exact(bounds[k][0])));
            let dy = number(&(&top - exact(bounds[k][1])));
            let matrix = geometry::translated_local(
                scene::parent_transform(document, i)?,
                document.items[i].transform,
                [dx, dy],
            )?;
            geometry::validate_matrix(matrix)?;
            candidate.items[i].transform = matrix;
            let actual = scene::bounds(&candidate, i)?
                .ok_or_else(|| invalid("Placed item lost its bounds"))?;
            let error = actual
                .iter()
                .zip(target)
                .map(|(a, b)| (a - b).abs())
                .fold(0.0_f64, f64::max);
            if actual.iter().any(|v| !v.is_finite()) || error > PLACEMENT_ERROR {
                return Err(Error::new(
                    "LAYOUT_PRECISION",
                    "Parent transform cannot place artwork within the declared geometry error",
                ));
            }
            maximum_error = maximum_error.max(error);
            moves.push((i, matrix));
            placements.push(json!({"id":document.items[i].id,"row":row,"before":bounds[k],"target":target,"actual":actual,"matrix":matrix,"geometry_error":error}));
            x += &sizes[k][0] + &gx;
        }
        y += row_height + &gy;
        start = end;
    }
    validate(&candidate)?;
    control.check()?;
    let bytes =
        serde_json::to_vec(document).map_err(|_| invalid("Unable to identify layout source"))?;
    Ok(Plan {
        moves,
        report: json!({
            "document_id":document.id,"revision":document.revision,"source_snapshot_sha256":crate::assets::sha256(&bytes),
            "algorithm":"ordered_shelves_v1","options":options,"rows":rows,"placements":placements,
            "minimum_height":number(&solution.height),"minimum_height_exact":fraction(&solution.height),
            "row_ends":solution.ends,"candidates_examined":candidates,"maximum_geometry_error":maximum_error,
            "geometry_error_limit":PLACEMENT_ERROR,"source_preserved":true,
            "objective":"minimum_total_row_height_then_fewest_rows_then_lexicographic_row_ends",
            "bounds_semantics":"unclipped_scene_geometry;excludes_strokes_effects_and_pixel_alpha;text_uses_frames",
            "dependencies":{"execution":"builtin_cpu","models":[],"gpu":false,"network":false,"external_resources_loaded":false},
            "scope":"fixed_sizes_and_order;horizontal_rows_from_area_top;unselected_artwork_is_not_an_obstacle"
        }),
    })
}

/// Read-only proposal. Atomic edits recompute from the expected document revision.
pub fn inspect(document: &Document, options: &Layout, control: &Control) -> Result<Value, Error> {
    Ok(plan(document, options, control)?.report)
}
pub(crate) fn apply(
    document: &mut Document,
    options: &Layout,
    control: &Control,
) -> Result<Value, Error> {
    let plan = plan(document, options, control)?;
    for (i, matrix) in plan.moves {
        document.items[i].transform = matrix;
    }
    Ok(plan.report)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn library_nonfinite_options_and_cancelled_work_fail_explicitly() {
        let document: Document = serde_json::from_value(json!({"schema_version":2,"id":"test","kind":"vector","width":16,"height":16,"color_space":"srgb","items":[{"id":"tile","content":{"type":"vector","geometry":{"shape":"rect","x":0,"y":0,"width":2,"height":3},"fill":[20,100,180,255]}}]})).unwrap();
        let options = Layout {
            ids: vec!["tile".into()],
            bounds: [0.0, 0.0, 8.0, 8.0],
            gap: [0.0, 0.0],
            horizontal: Alignment::Start,
            vertical: Alignment::Start,
        };
        for value in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            for k in 0..6 {
                let mut invalid = options.clone();
                if k < 4 {
                    invalid.bounds[k] = value;
                } else {
                    invalid.gap[k - 4] = value;
                }
                assert_eq!(
                    inspect(&document, &invalid, &Control::default())
                        .unwrap_err()
                        .code,
                    "INVALID_ASSISTANCE"
                );
            }
        }
        let control = Control::default();
        control.cancel();
        assert_eq!(
            inspect(&document, &options, &control).unwrap_err().code,
            "CANCELLED"
        );
    }
}
