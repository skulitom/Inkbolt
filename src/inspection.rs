//! Content-bound pages of selected inspection records, without exporting snapshots.
use crate::{Error, assets, control::Control, geometry, model::*, query, scene};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::BTreeSet;

pub const MAX_PAGE_ITEMS: usize = 128;
pub const MAX_PAGE_BYTES: usize = 32 * 1024;
const RECORD_BYTES: usize = MAX_PAGE_BYTES - 4096;
type Records<'a> = Box<dyn Iterator<Item = Result<Value, Error>> + 'a>;
fn page_size() -> usize {
    32
}

#[derive(
    Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Deserialize, Serialize, JsonSchema,
)]
#[serde(rename_all = "snake_case")]
pub enum Field {
    Name,
    ContentType,
    Hierarchy,
    Visibility,
    Locks,
    Transform,
    Bounds,
    Geometry,
    Style,
    Metadata,
}
fn default_fields() -> Vec<Field> {
    vec![
        Field::Name,
        Field::ContentType,
        Field::Hierarchy,
        Field::Visibility,
        Field::Locks,
        Field::Bounds,
    ]
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(tag = "collection", rename_all = "snake_case", deny_unknown_fields)]
pub enum View {
    Items {
        #[serde(default)]
        ids: Vec<String>,
        #[serde(default = "default_fields")]
        fields: Vec<Field>,
        #[serde(default)]
        types: Vec<query::ItemType>,
    },
    Assets {
        #[serde(default)]
        ids: Vec<String>,
    },
    Fonts {
        #[serde(default)]
        ids: Vec<String>,
    },
    Anchors {
        id: String,
    },
}
impl Default for View {
    fn default() -> Self {
        Self::Items {
            ids: vec![],
            fields: default_fields(),
            types: vec![],
        }
    }
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(default, deny_unknown_fields)]
pub struct Options {
    pub view: View,
    pub limit: usize,
    pub cursor: Option<String>,
}
impl Default for Options {
    fn default() -> Self {
        Self {
            view: View::default(),
            limit: page_size(),
            cursor: None,
        }
    }
}

fn invalid(message: &str) -> Error {
    Error::new("INVALID_REQUEST", message)
}
fn selected(ids: &[String], available: &BTreeSet<&str>) -> Result<BTreeSet<String>, Error> {
    if ids.len() > MAX_LARGE_VECTOR_ITEMS {
        return Err(invalid(
            "Inspection ID selection exceeds the large-document item limit",
        ));
    }
    let chosen: BTreeSet<_> = ids.iter().cloned().collect();
    if chosen.len() != ids.len() {
        return Err(invalid("Inspection IDs must be distinct"));
    }
    for id in &chosen {
        if !available.contains(id.as_str()) {
            return Err(Error::new(
                "INSPECTION_ID_NOT_FOUND",
                format!("Selected inspection ID {id:?} is absent from this collection"),
            ));
        }
    }
    Ok(chosen)
}

fn item_record(d: &Document, i: usize, fields: &[Field]) -> Result<Value, Error> {
    let item = &d.items[i];
    let mut row = json!({"id":item.id,"index":i});
    for field in fields {
        match field {
            Field::Name => row["name"] = json!(item.name),
            Field::ContentType => row["content_type"] = json!(query::item_type(item)),
            Field::Hierarchy => {
                row["parent"] = json!(item.parent);
                row["clip_to"] = json!(item.clip_to);
                row["sibling_index"] = json!(
                    scene::children(d, item.parent.as_deref())
                        .iter()
                        .position(|&j| i == j)
                        .unwrap()
                );
            }
            Field::Visibility => {
                row["visible"] = json!(item.visible);
                row["effective_visible"] = json!(scene::effective_visible(d, i)?);
            }
            Field::Locks => {
                row["locked"] = json!(item.locked);
                row["effective_locked"] = json!(scene::effective_locked(d, i)?);
                row["edit_blocked_by_locks"] = json!(match scene::check_unlocked(d, i, true) {
                    Ok(()) => false,
                    Err(e) if e.code == "LOCKED" => true,
                    Err(e) => return Err(e),
                });
            }
            Field::Transform => row["world_transform"] = json!(scene::world_transform(d, i)?),
            Field::Bounds => {
                row["geometry_bounds"] = json!(scene::bounds(d, i)?);
                if matches!(
                    &item.content,
                    Content::WorkPath {
                        geometry: Geometry::Compound { .. },
                        ..
                    }
                ) {
                    row["geometry_bounds_semantics"] =
                        json!("conservative_union_of_operand_geometry_not_tight_filled_result");
                }
            }
            Field::Geometry => {
                row["geometry"] = match &item.content {
                    Content::Vector { geometry, .. } | Content::WorkPath { geometry, .. } => {
                        json!(geometry)
                    }
                    _ => Value::Null,
                }
            }
            Field::Style => {
                row["opacity"] = json!(item.opacity);
                row["fill_opacity"] = json!(item.fill_opacity);
                row["coverage"] = json!(item.coverage);
                row["blend"] = json!(item.blend);
                row["effects"] = json!(item.effects);
                row["filters"] = json!(item.filters);
                row["stroke"] = match &item.content {
                    Content::Vector { stroke, .. } => json!(stroke),
                    _ => Value::Null,
                };
                row["fill"] = match &item.content {
                    Content::Vector { fill, .. } => json!(fill),
                    Content::Fill { paint, .. } => json!(paint),
                    _ => Value::Null,
                };
            }
            Field::Metadata => row["metadata"] = json!(item.metadata),
        }
    }
    Ok(row)
}

struct PathPart<'a> {
    commands: &'a [PathCommand],
    world: Matrix,
    component: Option<Vec<usize>>,
}
fn parts<'a>(
    g: &'a Geometry,
    world: Matrix,
    address: &mut Vec<usize>,
    compound: bool,
    out: &mut Vec<PathPart<'a>>,
) {
    match g {
        Geometry::Path { commands } => out.push(PathPart {
            commands,
            world,
            component: compound.then(|| address.clone()),
        }),
        Geometry::Compound { operands, .. } if compound => {
            for (i, operand) in operands.iter().enumerate() {
                address.push(i);
                parts(
                    &operand.geometry,
                    geometry::multiply(world, operand.transform),
                    address,
                    true,
                    out,
                );
                address.pop();
            }
        }
        _ => {}
    }
}

pub fn page(d: &Document, options: &Options, control: &Control) -> Result<Value, Error> {
    if !(1..=MAX_PAGE_ITEMS).contains(&options.limit) {
        return Err(invalid("Inspection page limit must be in 1..=128"));
    }
    if options.cursor.as_ref().is_some_and(|c| c.len() > 256) {
        return Err(Error::new(
            "INVALID_CURSOR",
            "Inspection cursor exceeds its byte limit",
        ));
    }
    crate::model::validate_controlled(d, control)?;
    let source_sha256 = assets::sha256(
        &serde_json::to_vec(d)
            .map_err(|_| invalid("Unable to serialize the inspected document"))?,
    );
    let selection_sha256 =
        assets::sha256(&serde_json::to_vec(&(&options.view, options.limit)).unwrap());
    let prefix = format!("inspect-v1:{source_sha256}:{selection_sha256}:");
    let start = match &options.cursor {
        None => 0,
        Some(cursor) => {
            let offset = cursor.strip_prefix(&prefix).ok_or_else(|| Error::new("STALE_CURSOR", "Inspection document, selection, fields or page limit changed; restart without a cursor"))?;
            let parsed = offset
                .parse::<usize>()
                .map_err(|_| Error::new("INVALID_CURSOR", "Invalid inspection cursor offset"))?;
            if parsed == 0 || parsed.to_string() != offset {
                return Err(Error::new(
                    "INVALID_CURSOR",
                    "Invalid inspection cursor offset",
                ));
            }
            parsed
        }
    };
    // Only IDs/indices and borrowed path slices are collected before paging. Bounds,
    // path records and other fields are evaluated for this page and at most one
    // lookahead record when the byte budget ends a page early.
    let (collection, order, total, rows): (&str, &str, usize, Records<'_>) = match &options.view {
        View::Items { ids, fields, types } => {
            if fields.len() > 10 || fields.iter().collect::<BTreeSet<_>>().len() != fields.len() {
                return Err(invalid(
                    "Inspection fields must be distinct supported field names",
                ));
            }
            if types.len() > 20 {
                return Err(invalid(
                    "Inspection type filter exceeds available item kinds",
                ));
            }
            let chosen = selected(ids, &d.items.iter().map(|i| i.id.as_str()).collect())?;
            let indices: Vec<_> = d
                .items
                .iter()
                .enumerate()
                .filter(|(_, i)| {
                    (chosen.is_empty() || chosen.contains(&i.id))
                        && (types.is_empty() || types.contains(&query::item_type(i)))
                })
                .map(|(i, _)| i)
                .collect();
            let total = indices.len();
            (
                "items",
                "document_storage",
                total,
                Box::new(
                    indices
                        .into_iter()
                        .skip(start)
                        .map(|i| item_record(d, i, fields)),
                ),
            )
        }
        View::Assets { ids } => {
            let chosen = selected(ids, &d.assets.keys().map(String::as_str).collect())?;
            let entries: Vec<_> = d
                .assets
                .iter()
                .filter(|(id, _)| chosen.is_empty() || chosen.contains(*id))
                .collect();
            let total = entries.len();
            ("assets","id",total,Box::new(entries.into_iter().skip(start).map(|(id,a)|Ok(json!({"id":id,"width":a.width,"height":a.height,"sha256":a.sha256,"storage":match a.storage {assets::Storage::Stored=>"stored",assets::Storage::Embedded{..}=>"embedded"},"provenance":a.provenance})))))
        }
        View::Fonts { ids } => {
            let chosen = selected(ids, &d.fonts.keys().map(String::as_str).collect())?;
            let entries: Vec<_> = d
                .fonts
                .iter()
                .filter(|(id, _)| chosen.is_empty() || chosen.contains(*id))
                .collect();
            let total = entries.len();
            (
                "fonts",
                "id",
                total,
                Box::new(
                    entries
                        .into_iter()
                        .skip(start)
                        .map(|(id, font)| Ok(json!({"id":id,"font":font}))),
                ),
            )
        }
        View::Anchors { id } => {
            let i = scene::index(d, id)?;
            let mut paths = vec![];
            match &d.items[i].content {
                Content::Vector { geometry, .. } | Content::WorkPath { geometry, .. } => parts(
                    geometry,
                    scene::world_transform(d, i)?,
                    &mut vec![],
                    matches!(d.items[i].content, Content::WorkPath { .. })
                        && matches!(geometry, Geometry::Compound { .. }),
                    &mut paths,
                ),
                _ => {}
            }
            let total = paths
                .iter()
                .map(|p| {
                    p.commands
                        .iter()
                        .filter(|c| !matches!(c, PathCommand::Close {}))
                        .count()
                })
                .sum();
            let mut skip = start;
            let mut remaining = Vec::new();
            for part in paths {
                let count = part
                    .commands
                    .iter()
                    .filter(|c| !matches!(c, PathCommand::Close {}))
                    .count();
                if skip >= count {
                    skip -= count;
                } else {
                    remaining.push((part, skip));
                    skip = 0;
                }
            }
            (
                "anchors",
                "component_then_command",
                total,
                Box::new(remaining.into_iter().flat_map(|(part, skip)| {
                    crate::paths::geometry_anchors_from(part.commands, part.world, skip).map(
                        move |mut anchor| {
                            if let Some(component) = &part.component {
                                anchor["component"] = json!(component);
                            }
                            Ok(anchor)
                        },
                    )
                })),
            )
        }
    };
    if start > total || (options.cursor.is_some() && start == total) {
        return Err(Error::new(
            "INVALID_CURSOR",
            "Inspection cursor is outside this collection",
        ));
    }
    let mut records = vec![];
    let mut bytes = 0;
    for row in rows.take(options.limit) {
        control.check()?;
        let row = row?;
        let size = serde_json::to_vec(&row).unwrap().len() + 1;
        if size > RECORD_BYTES {
            return Err(Error::new(
                "INSPECTION_RECORD_TOO_LARGE",
                "One record exceeds the 28 KiB inspection allowance; omit geometry/metadata/style or use the anchors collection for path controls",
            ));
        }
        if bytes + size > RECORD_BYTES {
            break;
        }
        bytes += size;
        records.push(row);
    }
    let next = start + records.len();
    control.check()?;
    let result = json!({"document_id":d.id,"revision":d.revision,"document_sha256":source_sha256,"collection":collection,"order":order,"offset":start,"total":total,"limit":options.limit,"returned":records.len(),"records":records,"next_cursor":(next<total).then(||format!("{prefix}{next}")),"semantics":"Read-only structural inspection. Hidden and locked items are included. Bounds are unclipped world geometry, excluding strokes/effects; text uses its frame. Resource inventories do not verify external bytes. Anchor indices and compound addresses belong to this exact document; topology edits can renumber them."});
    if serde_json::to_vec(&result).unwrap().len() > MAX_PAGE_BYTES {
        return Err(Error::new(
            "RESOURCE_LIMIT",
            "Inspection page metadata exceeds 32 KiB",
        ));
    }
    Ok(result)
}
