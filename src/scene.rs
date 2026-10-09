//! Flat storage with explicit parent references; ordering is local to each parent.
use crate::{
    Error,
    geometry::{self, Bounds},
    model::*,
};
use std::collections::HashSet;

pub const MAX_DEPTH: usize = 16;
pub fn index(document: &Document, id: &str) -> Result<usize, Error> {
    document
        .items
        .iter()
        .position(|item| item.id == id)
        .ok_or_else(|| Error::new("NOT_FOUND", "No item has the requested ID"))
}
pub fn children(document: &Document, parent: Option<&str>) -> Vec<usize> {
    document
        .items
        .iter()
        .enumerate()
        .filter_map(|(i, item)| (item.parent.as_deref() == parent).then_some(i))
        .collect()
}
pub fn ancestors(document: &Document, i: usize) -> Result<Vec<usize>, Error> {
    let mut result = Vec::new();
    let mut seen = HashSet::from([i]);
    let mut next = document.items[i].parent.as_deref();
    while let Some(id) = next {
        let p = index(document, id).map_err(|_| invalid("Parent ID does not exist"))?;
        if !document.items[p].content.is_container() {
            return Err(invalid("Parent must be a group, layer, frame or artboard"));
        }
        if !seen.insert(p) {
            return Err(invalid("Hierarchy contains a cycle"));
        }
        result.push(p);
        if result.len() > MAX_DEPTH {
            return Err(limit("Hierarchy exceeds 16 ancestor levels"));
        }
        next = document.items[p].parent.as_deref();
    }
    Ok(result)
}
pub fn world_transform(document: &Document, i: usize) -> Result<Matrix, Error> {
    let mut world = document.items[i].transform;
    for p in ancestors(document, i)? {
        world = geometry::multiply(document.items[p].transform, world);
    }
    Ok(world)
}
pub fn parent_transform(document: &Document, i: usize) -> Result<Matrix, Error> {
    match &document.items[i].parent {
        Some(id) => world_transform(document, index(document, id)?),
        None => Ok(identity()),
    }
}
pub fn effective_locked(document: &Document, i: usize) -> Result<bool, Error> {
    Ok(document.items[i].locked
        || ancestors(document, i)?
            .iter()
            .any(|&p| document.items[p].locked))
}
pub fn effective_visible(document: &Document, i: usize) -> Result<bool, Error> {
    let mut pending = vec![i];
    let mut seen = HashSet::new();
    while let Some(j) = pending.pop() {
        if !seen.insert(j) {
            continue;
        }
        let item = &document.items[j];
        if !item.visible
            || matches!(
                item.content,
                Content::MaskSource {} | Content::ComponentSource {}
            )
        {
            return Ok(false);
        }
        pending.extend(ancestors(document, j)?);
        let base = item.clip_to.as_ref().or(match &item.content {
            Content::Adjustment { adjustment } => adjustment.clip_to.as_ref(),
            _ => None,
        });
        if let Some(base) = base {
            pending.push(index(document, base)?);
        }
    }
    Ok(true)
}
pub fn subtree(document: &Document, i: usize) -> Vec<usize> {
    let mut result = vec![i];
    for c in children(document, Some(&document.items[i].id)) {
        result.extend(subtree(document, c));
    }
    result
}
pub fn check_unlocked(document: &Document, i: usize, descendants: bool) -> Result<(), Error> {
    if effective_locked(document, i)?
        || (descendants
            && subtree(document, i)
                .iter()
                .any(|&c| document.items[c].locked))
    {
        return Err(Error::new(
            "LOCKED",
            "Item, ancestor or affected descendant is locked",
        ));
    }
    crate::artwork_masks::check_dependents_unlocked(document, i)?;
    crate::instances::check_dependents_unlocked(document, i)
}
pub fn union(a: Bounds, b: Bounds) -> Bounds {
    [
        a[0].min(b[0]),
        a[1].min(b[1]),
        a[2].max(b[2]),
        a[3].max(b[3]),
    ]
}
pub fn bounds(document: &Document, i: usize) -> Result<Option<Bounds>, Error> {
    let m = world_transform(document, i)?;
    if let Some(p) = crate::pixel_warps::plan(&document.items[i])? {
        return Ok(Some(geometry::bounds(&p.geometry(), m)));
    }
    match &document.items[i].content {
        Content::Appearance { appearance } => crate::appearance::bounds(appearance, m).map(Some),
        Content::StoryFrame { story_id, slot_id } => Ok(Some(geometry::bounds(
            &crate::text::flow::story(document, story_id)?
                .slot(slot_id)?
                .geometry(),
            m,
        ))),
        Content::Volume { volume } => crate::volumes::bounds(volume, m).map(Some),
        Content::Warp { warp } => Ok(Some(geometry::bounds(
            &crate::warps::plan(warp)?.geometry,
            m,
        ))),
        Content::Repeat { repeat } => Ok(Some(geometry::bounds(
            &crate::repeats::geometry(repeat)?,
            m,
        ))),
        Content::ComponentSource {} => Ok(None),
        Content::Interpolation { interpolation } => {
            crate::interpolation::bounds(interpolation, m).map(Some)
        }
        Content::Instance { .. } => {
            let view = crate::instances::instance_view(document, i)?;
            bounds(&view, 0)
        }
        Content::Adjustment { .. } | Content::MaskSource {} => Ok(None),
        Content::Frame { frame } => Ok(Some(geometry::bounds(&frame.geometry(), m))),
        Content::Vector { geometry, .. } | Content::WorkPath { geometry, .. } => {
            Ok(Some(geometry::bounds(geometry, m)))
        }
        Content::Text { frame } => Ok(Some(geometry::bounds(
            &crate::text::frame_geometry(frame),
            m,
        ))),
        Content::Image { width, height, .. } => Ok(Some(geometry::bounds(
            &Geometry::Rect {
                x: 0.0,
                y: 0.0,
                width: *width,
                height: *height,
            },
            m,
        ))),
        Content::Object { object } => Ok(Some(geometry::bounds(&object.geometry(), m))),
        Content::Samples { grid } => Ok(Some(geometry::bounds(&grid.geometry(), m))),
        Content::StoredSamples { grid } => Ok(Some(geometry::bounds(&grid.geometry(), m))),
        Content::Raw { raw } => Ok(Some(geometry::bounds(&raw.geometry(), m))),
        Content::Raster { width, height, .. } | Content::Fill { width, height, .. } => {
            Ok(Some(geometry::bounds(
                &Geometry::Rect {
                    x: 0.0,
                    y: 0.0,
                    width: *width as f64,
                    height: *height as f64,
                },
                m,
            )))
        }
        Content::Group { .. } => {
            let mut out = None;
            for c in children(document, Some(&document.items[i].id)) {
                if let Some(b) = bounds(document, c)? {
                    out = Some(out.map_or(b, |a| union(a, b)));
                }
            }
            Ok(out)
        }
    }
}
pub fn selection(document: &Document, ids: &[String], disjoint: bool) -> Result<Vec<usize>, Error> {
    if ids.is_empty() || ids.len() > document.resource_profile.items() {
        return Err(Error::new(
            "INVALID_OPERATION",
            "Selection requires nonempty unique IDs within the document resource profile",
        ));
    }
    let mut selected = HashSet::new();
    let mut indices = Vec::new();
    for id in ids {
        let i = index(document, id)?;
        if !selected.insert(i) {
            return Err(Error::new(
                "INVALID_OPERATION",
                "Selection IDs must be unique",
            ));
        }
        indices.push(i);
    }
    if disjoint {
        for &i in &indices {
            if ancestors(document, i)?.iter().any(|p| selected.contains(p)) {
                return Err(Error::new(
                    "INVALID_OPERATION",
                    "Select a group or its descendants, not both",
                ));
            }
        }
    }
    Ok(indices)
}
pub(crate) fn insertion(
    document: &Document,
    parent: Option<&str>,
    at: Option<usize>,
) -> Result<usize, Error> {
    let siblings = children(document, parent);
    let at = at.unwrap_or(siblings.len());
    if at > siblings.len() {
        return Err(Error::new(
            "INVALID_OPERATION",
            "Insertion index exceeds sibling count",
        ));
    }
    Ok(if at < siblings.len() {
        siblings[at]
    } else {
        siblings.last().map_or(document.items.len(), |i| i + 1)
    })
}
pub(crate) fn backdrop_dependent(document: &Document, i: usize) -> bool {
    let item = &document.items[i];
    item.blend != BlendMode::Normal
        || matches!(
            item.content,
            Content::Group {
                isolated: false,
                knockout: true,
                ..
            }
        )
        || matches!(&item.content, Content::Adjustment { adjustment } if adjustment.clip_to.is_none())
        || (matches!(
            item.content,
            Content::Group {
                isolated: false,
                ..
            }
        ) && children(document, Some(&item.id))
            .iter()
            .any(|&c| backdrop_dependent(document, c)))
}
