//! Read-only, explicit item and anchor discovery for revision-scoped edits.
use crate::{Error, geometry::Bounds, model::*, scene};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
fn yes() -> bool {
    true
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum ItemType {
    Raw,
    Volume,
    Appearance,
    Object,
    Warp,
    Repeat,
    Interpolation,
    ComponentSource,
    Instance,
    WorkPath,
    MaskSource,
    Adjustment,
    Vector,
    Samples,
    Raster,
    Image,
    Fill,
    Text,
    Group,
    Frame,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Shape {
    Compound,
    Rect,
    Ellipse,
    Path,
    RoundedRect,
    Polygon,
    RegularPolygon,
    Star,
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Relation {
    #[default]
    Intersects,
    Contains,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Region {
    pub bounds: Bounds,
    #[serde(default)]
    pub relation: Relation,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Query {
    #[serde(default)]
    pub types: Vec<ItemType>,
    #[serde(default)]
    pub shapes: Vec<Shape>,
    pub region: Option<Region>,
    #[serde(default = "yes")]
    pub visible_only: bool,
    #[serde(default)]
    pub include_locked: bool,
    #[serde(default)]
    pub include_anchors: bool,
    pub anchor_bounds: Option<Bounds>,
}
pub fn item_type(item: &Item) -> ItemType {
    match item.content {
        Content::Raw { .. } => ItemType::Raw,
        Content::Volume { .. } => ItemType::Volume,
        Content::Appearance { .. } => ItemType::Appearance,
        Content::Object { .. } => ItemType::Object,
        Content::Warp { .. } => ItemType::Warp,
        Content::Repeat { .. } => ItemType::Repeat,
        Content::Interpolation { .. } => ItemType::Interpolation,
        Content::ComponentSource {} => ItemType::ComponentSource,
        Content::Instance { .. } => ItemType::Instance,
        Content::MaskSource {} => ItemType::MaskSource,
        Content::WorkPath { .. } => ItemType::WorkPath,
        Content::Adjustment { .. } => ItemType::Adjustment,
        Content::Vector { .. } => ItemType::Vector,
        Content::Samples { .. } | Content::StoredSamples { .. } => ItemType::Samples,
        Content::Raster { .. } => ItemType::Raster,
        Content::Image { .. } => ItemType::Image,
        Content::Fill { .. } => ItemType::Fill,
        Content::Text { .. } | Content::StoryFrame { .. } => ItemType::Text,
        Content::Group { .. } => ItemType::Group,
        Content::Frame { .. } => ItemType::Frame,
    }
}
pub fn shape(g: &Geometry) -> Shape {
    match g {
        Geometry::Compound { .. } => Shape::Compound,
        Geometry::Rect { .. } => Shape::Rect,
        Geometry::Ellipse { .. } => Shape::Ellipse,
        Geometry::Path { .. } => Shape::Path,
        Geometry::RoundedRect { .. } => Shape::RoundedRect,
        Geometry::Polygon { .. } => Shape::Polygon,
        Geometry::RegularPolygon { .. } => Shape::RegularPolygon,
        Geometry::Star { .. } => Shape::Star,
    }
}
fn valid_bounds(b: Bounds) -> Result<(), Error> {
    if b.iter()
        .any(|v| !v.is_finite() || v.abs() > MAX_COORDINATE * 2.0)
        || b[0] > b[2]
        || b[1] > b[3]
    {
        return Err(Error::new(
            "INVALID_REQUEST",
            "Query bounds must be ordered, finite and within world coordinates",
        ));
    }
    Ok(())
}
pub(crate) fn execute(document: &Document, query: &Query) -> Result<Value, Error> {
    validate(document)?;
    if let Some(region) = &query.region {
        valid_bounds(region.bounds)?;
    }
    if let Some(b) = query.anchor_bounds {
        valid_bounds(b)?;
    }
    if query.types.len() > 12 || query.shapes.len() > 8 {
        return Err(Error::new(
            "INVALID_REQUEST",
            "Query type/shape filters exceed available kinds",
        ));
    }
    let mut items = Vec::new();
    let mut ids = Vec::new();
    for (i, item) in document.items.iter().enumerate() {
        let edit_blocked_by_locks = match scene::check_unlocked(document, i, true) {
            Ok(()) => false,
            Err(error) if error.code == "LOCKED" => true,
            Err(error) => return Err(error),
        };
        if (!query.types.is_empty() && !query.types.contains(&item_type(item)))
            || (query.visible_only && !scene::effective_visible(document, i)?)
            || (!query.include_locked && edit_blocked_by_locks)
        {
            continue;
        }
        if !query.shapes.is_empty() {
            let (Content::Vector { geometry, .. } | Content::WorkPath { geometry, .. }) =
                &item.content
            else {
                continue;
            };
            if !query.shapes.contains(&shape(geometry)) {
                continue;
            }
        }
        if let Some(region) = &query.region {
            let Some(b) = scene::bounds(document, i)? else {
                continue;
            };
            let r = region.bounds;
            let found = match region.relation {
                Relation::Intersects => {
                    b[0] <= r[2] && b[2] >= r[0] && b[1] <= r[3] && b[3] >= r[1]
                }
                Relation::Contains => b[0] >= r[0] && b[1] >= r[1] && b[2] <= r[2] && b[3] <= r[3],
            };
            if !found {
                continue;
            }
        }
        let mut inspected = crate::inspect_item(document, i)?;
        inspected["edit_blocked_by_locks"] = json!(edit_blocked_by_locks);
        if query.include_anchors || query.anchor_bounds.is_some() {
            let anchors = crate::paths::anchors(document, i)?
                .into_iter()
                .filter(|a| {
                    query.anchor_bounds.is_none_or(|b| {
                        let p = &a["world"];
                        let x = p[0].as_f64().unwrap();
                        let y = p[1].as_f64().unwrap();
                        x >= b[0] && x <= b[2] && y >= b[1] && y <= b[3]
                    })
                })
                .collect::<Vec<_>>();
            if query.anchor_bounds.is_some() && anchors.is_empty() {
                continue;
            }
            inspected["anchors"] = json!(anchors);
        }
        ids.push(item.id.clone());
        items.push(inspected);
    }
    Ok(
        json!({"document_id":document.id,"revision":document.revision,"ids":ids,"items":items,"order":"document_storage","semantics":"Read-only discovery. Region compares inclusive unclipped world geometry bounds, excluding strokes and mask effects; it is not a filled-area hit test. Anchor indices address path commands at this revision; topology edits can renumber them. Hidden items and items blocked by own, ancestor or affected descendant locks are excluded by default."}),
    )
}
