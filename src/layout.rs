use crate::{Error, geometry, model::*, scene};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Axis {
    X,
    Y,
}
impl Axis {
    pub(crate) fn index(self) -> usize {
        match self {
            Self::X => 0,
            Self::Y => 1,
        }
    }
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Anchor {
    Min,
    Center,
    Max,
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Distribution {
    Gaps,
    Centers,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Reference {
    Guide { frame_id: String, id: String },
    Canvas {},
    Selection {},
    Item { id: String },
    Bounds { bounds: geometry::Bounds },
}
fn selection_bounds(
    document: &Document,
    selected: &[usize],
) -> Result<Vec<geometry::Bounds>, Error> {
    selected
        .iter()
        .map(|&i| {
            scene::check_unlocked(document, i, true)?;
            scene::bounds(document, i)?.ok_or_else(|| {
                Error::new("INVALID_OPERATION", "Empty groups have no alignment bounds")
            })
        })
        .collect()
}
fn reference_bounds(
    document: &Document,
    reference: &Reference,
    selected: &[geometry::Bounds],
    axis: Axis,
) -> Result<geometry::Bounds, Error> {
    let b = match reference {
        Reference::Guide { frame_id, id } => {
            crate::boards::guide_bounds(document, frame_id, id, axis)?
        }
        Reference::Canvas {} => crate::vector_canvas::bounds(document),
        Reference::Selection {} => selected
            .iter()
            .copied()
            .reduce(scene::union)
            .ok_or_else(|| Error::new("INVALID_OPERATION", "Empty selection"))?,
        Reference::Item { id } => scene::bounds(document, scene::index(document, id)?)?
            .ok_or_else(|| {
                Error::new("INVALID_OPERATION", "Reference item has no geometry bounds")
            })?,
        Reference::Bounds { bounds } => *bounds,
    };
    if b.iter()
        .any(|v| !v.is_finite() || v.abs() > MAX_COORDINATE * 2.0)
        || b[0] > b[2]
        || b[1] > b[3]
    {
        return Err(Error::new(
            "INVALID_OPERATION",
            "Reference bounds must be finite and ordered within coordinate limits",
        ));
    }
    Ok(b)
}

fn fixed_guide(
    document: &Document,
    reference: &Reference,
    selected: &[usize],
) -> Result<(), Error> {
    if let Reference::Guide { frame_id, .. } = reference {
        let i = scene::index(document, frame_id)?;
        if selected.contains(&i)
            || scene::ancestors(document, i)?
                .iter()
                .any(|p| selected.contains(p))
        {
            return Err(Error::new(
                "INVALID_OPERATION",
                "Cannot move a guide's frame or ancestor while aligning to that guide",
            ));
        }
    }
    Ok(())
}
fn move_world(document: &mut Document, i: usize, axis: usize, delta: f64) -> Result<(), Error> {
    let inverse = geometry::inverse(scene::parent_transform(document, i)?)?;
    let direction = if axis == 0 {
        [delta, 0.0]
    } else {
        [0.0, delta]
    };
    document.items[i].transform[4] += inverse[0] * direction[0] + inverse[2] * direction[1];
    document.items[i].transform[5] += inverse[1] * direction[0] + inverse[3] * direction[1];
    Ok(())
}
pub fn align(
    document: &mut Document,
    ids: &[String],
    axis: Axis,
    anchor: Anchor,
    reference: &Reference,
) -> Result<(), Error> {
    let selected = scene::selection(document, ids, true)?;
    fixed_guide(document, reference, &selected)?;
    let bounds = selection_bounds(document, &selected)?;
    let reference = reference_bounds(document, reference, &bounds, axis)?;
    let axis = axis.index();
    let coordinate = |b: geometry::Bounds| match anchor {
        Anchor::Min => b[axis],
        Anchor::Center => (b[axis] + b[axis + 2]) * 0.5,
        Anchor::Max => b[axis + 2],
    };
    let target = coordinate(reference);
    for (&i, b) in selected.iter().zip(bounds) {
        move_world(document, i, axis, target - coordinate(b))?;
    }
    Ok(())
}
pub fn distribute(
    document: &mut Document,
    ids: &[String],
    axis: Axis,
    mode: Distribution,
    reference: &Reference,
) -> Result<(), Error> {
    let selected = scene::selection(document, ids, true)?;
    if selected.len() < 3 {
        return Err(Error::new(
            "INVALID_OPERATION",
            "Distribution requires at least three objects",
        ));
    }
    fixed_guide(document, reference, &selected)?;
    let bounds = selection_bounds(document, &selected)?;
    let reference = reference_bounds(document, reference, &bounds, axis)?;
    let axis = axis.index();
    let mut ordered: Vec<_> = selected.into_iter().zip(bounds).collect();
    let key = |b: &geometry::Bounds| match mode {
        Distribution::Gaps => b[axis],
        Distribution::Centers => (b[axis] + b[axis + 2]) * 0.5,
    };
    ordered.sort_by(|(ia, a), (ib, b)| {
        key(a)
            .total_cmp(&key(b))
            .then_with(|| document.items[*ia].id.cmp(&document.items[*ib].id))
    });
    let n = ordered.len();
    let mut position = reference[axis];
    let sum: f64 = ordered.iter().map(|(_, b)| b[axis + 2] - b[axis]).sum();
    let gap = (reference[axis + 2] - reference[axis] - sum) / (n - 1) as f64;
    // Centers retain the outer object extents at the reference edges.
    let first_half = (ordered[0].1[axis + 2] - ordered[0].1[axis]) * 0.5;
    let last_half = (ordered[n - 1].1[axis + 2] - ordered[n - 1].1[axis]) * 0.5;
    let center_start = reference[axis] + first_half;
    let center_step = (reference[axis + 2] - last_half - center_start) / (n - 1) as f64;
    for (j, (i, b)) in ordered.into_iter().enumerate() {
        let target = match mode {
            Distribution::Gaps => position,
            Distribution::Centers => {
                center_start + j as f64 * center_step - (b[axis + 2] - b[axis]) * 0.5
            }
        };
        move_world(document, i, axis, target - b[axis])?;
        position += b[axis + 2] - b[axis] + gap;
    }
    Ok(())
}
