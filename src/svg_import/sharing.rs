//! Preserve compatible resolved SVG occurrences as editable native components.
use super::*;
use crate::instances::{Instance, Override, VectorStyle};
use std::collections::HashMap;

pub(super) struct Occurrence {
    pub host: String,
    pub target: usize,
    pub viewport: bool,
    pub original: bool,
}

fn group() -> Content {
    Content::Group {
        isolated: true,
        role: GroupRole::Group,
        knockout: false,
    }
}
fn neutral(id: String, content: Content) -> Item {
    Item {
        id,
        content,
        name: String::new(),
        parent: None,
        transform: identity(),
        visible: true,
        locked: false,
        opacity: 1.0,
        fill_opacity: 1.0,
        coverage: Default::default(),
        blend: BlendMode::Normal,
        hdr_grade: None,
        pixel_warp: None,
        metadata: None,
        effects: vec![],
        clip_to: None,
        clip: None,
        mask: None,
        artwork_mask: None,
        filters: vec![],
    }
}
fn resolved<'a>(aliases: &'a HashMap<String, String>, mut id: &'a str) -> &'a str {
    while let Some(next) = aliases.get(id) {
        id = next;
    }
    id
}
fn remap(value: &mut Value, fields: &[&str], aliases: &HashMap<String, String>) {
    for field in fields {
        if let Some(id) = value[*field].as_str() {
            let new = resolved(aliases, id).to_owned();
            value[*field] = json!(new);
        }
    }
}

/// Only native overrides that keep source geometry live are admitted. Other
/// context differences form another definition instead of freezing whole shapes.
fn overrides(base: &[Item], candidate: &[Item]) -> Option<BTreeMap<String, Override>> {
    if base.len() != candidate.len() {
        return None;
    }
    let ids: HashMap<_, _> = candidate
        .iter()
        .zip(base)
        .map(|(c, b)| (c.id.as_str(), b.id.as_str()))
        .collect();
    let mut result = BTreeMap::new();
    for (index, (b, c)) in base.iter().zip(candidate).enumerate() {
        let mut compared = c.clone();
        compared.id = b.id.clone();
        compared.parent = if index == 0 {
            None
        } else {
            Some(ids.get(c.parent.as_deref()?)?.to_string())
        };
        let mut expected = b.clone();
        if index == 0 {
            expected.parent = None;
            expected.content = group();
        }
        let mut patch = Override::default();
        macro_rules! property {
            ($field:ident) => {
                if c.$field != b.$field {
                    patch.$field = Some(c.$field.clone());
                    compared.$field = b.$field.clone();
                }
            };
        }
        property!(name);
        property!(visible);
        property!(opacity);
        property!(fill_opacity);
        property!(blend);
        property!(transform);
        if compared.content != expected.content {
            match (&expected.content, &compared.content) {
                (
                    Content::Vector { geometry: a, .. },
                    Content::Vector {
                        geometry: z,
                        fill,
                        stroke,
                        fill_rule,
                    },
                ) if a == z => {
                    patch.vector_style = Some(VectorStyle {
                        fill: fill.clone(),
                        stroke: stroke.clone(),
                        fill_rule: Some(*fill_rule),
                    });
                    compared.content = expected.content.clone();
                }
                (Content::Instance { instance: a }, Content::Instance { instance: z })
                    if a.source == z.source =>
                {
                    patch.content = Some(Box::new(compared.content.clone()));
                    compared.content = expected.content.clone();
                }
                _ => return None,
            }
        }
        if compared != expected {
            return None;
        }
        if patch != Override::default() {
            result.insert(b.id.clone(), patch);
        }
    }
    Some(result)
}

struct Candidate {
    instance: String,
    items: Vec<Item>,
    stored: HashSet<String>,
}
impl Candidate {
    fn collect(
        d: &Document,
        occurrence: &Occurrence,
        number: usize,
    ) -> Result<Option<Self>, Error> {
        let child = |parent: &str| {
            d.items
                .iter()
                .find(|item| item.parent.as_deref() == Some(parent))
        };
        let instance = if occurrence.viewport {
            let Some(viewport) = child(&occurrence.host) else {
                return Ok(None);
            };
            viewport.id.clone()
        } else {
            occurrence.host.clone()
        };
        let Some(root) = child(&instance) else {
            return Ok(None);
        };
        let index = crate::scene::index(d, &root.id)?;
        let mut items: Vec<_> = crate::scene::subtree(d, index)
            .into_iter()
            .map(|i| d.items[i].clone())
            .collect();
        let stored = items.iter().map(|i| i.id.clone()).collect();
        if matches!(root.content, Content::Group { .. }) {
            items[0].parent = None;
        } else {
            let id = format!("svg-component-{number}");
            items[0].parent = Some(id.clone());
            items.insert(0, neutral(id, group()));
        }
        Ok(Some(Self {
            instance,
            items,
            stored,
        }))
    }
}

impl Importer<'_> {
    pub(super) fn share_components(&mut self, enabled: bool) -> Result<Vec<Value>, Error> {
        if self.occurrences.is_empty() {
            return Ok(vec![]);
        }
        let expanded = |reason: &str| {
            self.occurrences.iter().map(|o| json!({
            "host_item_id":o.host,"byte_offset":o.target,"mode":"expanded","reason":reason
        })).collect::<Vec<_>>()
        };
        if !enabled {
            self.losses.push("SVG reference sharing is expanded into independent editable groups for this destination; the reuse receipt records the reason.".into());
            return Ok(expanded("destination_requires_groups"));
        }
        // Conversion follows paint/clip/mask binding and whole expanded-input
        // validation. It cannot erase a source validation failure or evade limits.
        let mut document = self.document.clone();
        let mut aliases = HashMap::new();
        let mut sources = BTreeMap::<usize, Vec<String>>::new();
        let mut placements = HashMap::<String, (String, String)>::new();
        let mut receipts = vec![];
        let mut definitions = 0;
        let mut variants = false;
        let mut occurrences: Vec<_> = self
            .occurrences
            .iter()
            .map(|o| Occurrence {
                host: o.host.clone(),
                target: o.target,
                viewport: o.viewport,
                original: false,
            })
            .collect();
        // Referenced nodes also occur directly or inside other copied subtrees.
        // Give every such occurrence a placement, so overlapping source targets
        // retain their shared child geometry instead of creating unrelated copies.
        let targets: HashSet<_> = occurrences.iter().map(|o| o.target).collect();
        let mut direct_roots = HashSet::new();
        for (number, occurrence) in occurrences.iter().enumerate() {
            self.control.check()?;
            if let Some(candidate) = Candidate::collect(&document, occurrence, number)? {
                // A shape candidate has a synthetic root, so use its stored child.
                let root = candidate
                    .items
                    .iter()
                    .find(|item| candidate.stored.contains(&item.id))
                    .unwrap();
                direct_roots.insert(root.id.clone());
            }
        }
        for row in &self.mappings {
            self.control.check()?;
            let Some(offset) = row["byte_offset"].as_u64() else {
                continue;
            };
            if !targets.contains(&(offset as usize)) || row["empty_viewport"] == true {
                continue;
            }
            let Some(id) = row["item_id"].as_str() else {
                continue;
            };
            if direct_roots.contains(id) {
                continue;
            }
            let index = crate::scene::index(&document, id)?;
            let host = format!("svg-source-placement-{id}");
            let mut item = neutral(host.clone(), group());
            item.parent = document.items[index].parent.clone();
            document.items[index].parent = Some(host.clone());
            document.items.insert(index, item);
            occurrences.push(Occurrence {
                host,
                target: offset as usize,
                viewport: false,
                original: row.get("instance_path").is_none(),
            });
        }
        let prepared: Result<_, Error> = (|| {
            let mut depths = HashMap::new();
            for occurrence in &occurrences {
                self.control.check()?;
                let index = crate::scene::index(&document, &occurrence.host)?;
                depths.insert(
                    occurrence.host.clone(),
                    crate::scene::ancestors(&document, index)?.len(),
                );
            }
            let paths = self
                .mappings
                .iter()
                .map(|row| {
                    self.control.check()?;
                    let index = crate::scene::index(&document, row["item_id"].as_str().unwrap())?;
                    let mut ancestors = crate::scene::ancestors(&document, index)?;
                    ancestors.reverse();
                    ancestors.push(index);
                    Ok(ancestors
                        .into_iter()
                        .map(|i| document.items[i].id.clone())
                        .filter(|id| depths.contains_key(id))
                        .collect::<Vec<_>>())
                })
                .collect::<Result<Vec<_>, Error>>()?;
            Ok((depths, paths))
        })();
        let (depths, paths) = match prepared {
            Ok(value) => value,
            Err(error) if error.code == "RESOURCE_LIMIT" => {
                self.losses.push("SVG references remain independent editable groups because component placement wrappers would exceed the hierarchy budget.".into());
                return Ok(expanded("component_resource_budget"));
            }
            Err(error) => return Err(error),
        };
        occurrences.sort_by_key(|o| std::cmp::Reverse(depths[&o.host]));
        for (number, occurrence) in occurrences.iter().enumerate() {
            self.control.check()?;
            let Some(candidate) = Candidate::collect(&document, occurrence, number)? else {
                receipts.push(
                    json!({"host_item_id":occurrence.host,"byte_offset":occurrence.target,
                    "mode":"expanded","reason":"empty_viewport_or_content"}),
                );
                continue;
            };
            let mut matched = None;
            for source in sources.get(&occurrence.target).into_iter().flatten() {
                let index = crate::scene::index(&document, source)?;
                let members: Vec<_> = crate::scene::subtree(&document, index)
                    .into_iter()
                    .map(|i| document.items[i].clone())
                    .collect();
                if let Some(patches) = overrides(&members, &candidate.items) {
                    matched = Some((source.clone(), patches, members));
                    break;
                }
            }
            let (source, patches) = if let Some((source, patches, members)) = matched {
                for (old, new) in candidate.items.iter().zip(&members) {
                    if old.id != new.id {
                        aliases.insert(old.id.clone(), new.id.clone());
                    }
                }
                document
                    .items
                    .retain(|item| !candidate.stored.contains(&item.id));
                (source, patches)
            } else {
                if definitions == crate::instances::MAX_DEFINITIONS {
                    receipts.push(
                        json!({"host_item_id":occurrence.host,"byte_offset":occurrence.target,
                        "mode":"expanded","reason":"component_definition_limit"}),
                    );
                    continue;
                }
                variants |= sources
                    .get(&occurrence.target)
                    .is_some_and(|v| !v.is_empty());
                definitions += 1;
                let mut items = candidate.items;
                items[0].content = Content::ComponentSource {};
                let source = items[0].id.clone();
                document
                    .items
                    .retain(|item| !candidate.stored.contains(&item.id));
                document.items.extend(items);
                sources
                    .entry(occurrence.target)
                    .or_default()
                    .push(source.clone());
                (source, BTreeMap::new())
            };
            let index = crate::scene::index(&document, &candidate.instance)?;
            document.items[index].content = Content::Instance {
                instance: Box::new(Instance {
                    source: source.clone(),
                    overrides: patches,
                }),
            };
            placements.insert(
                occurrence.host.clone(),
                (candidate.instance.clone(), source.clone()),
            );
            receipts.push(json!({"host_item_id":occurrence.host,"instance_item_id":candidate.instance,
                "component_source_id":source,"byte_offset":occurrence.target,"mode":"component","original":occurrence.original}));
        }
        if let Err(error) = validate_controlled(&document, &self.control) {
            if error.code != "RESOURCE_LIMIT" {
                return Err(error);
            }
            self.losses.push(format!("SVG reference sharing remains expanded because the native component representation exceeds a resource budget: {}", error.message));
            return Ok(expanded("component_resource_budget"));
        }
        for (row, path) in self.mappings.iter_mut().zip(paths) {
            self.control.check()?;
            // Paths retain all enclosing placements even when an inner stored
            // item moves into a shared source. They never name virtual render IDs.
            let own_placement = row["item_id"]
                .as_str()
                .and_then(|id| placements.get(id))
                .cloned();
            let mut occurrence = None;
            if let Some(path) = row.get_mut("instance_path").and_then(Value::as_array_mut) {
                for entry in path {
                    if let Some((instance, source)) =
                        entry["item_id"].as_str().and_then(|id| placements.get(id))
                    {
                        entry["instance_item_id"] = json!(instance);
                        entry["component_source_id"] = json!(source);
                        occurrence = Some((instance.clone(), source.clone()));
                    }
                    remap(
                        entry,
                        &["item_id", "instance_item_id", "component_source_id"],
                        &aliases,
                    );
                }
            }
            if let Some((instance, source)) = own_placement.or(occurrence) {
                row["instance_item_id"] = json!(instance);
                row["component_source_id"] = json!(source);
            }
            let component_path: Vec<_> = path.iter().filter_map(|id| placements.get(id)).map(|(instance, source)| {
                json!({"instance_item_id":resolved(&aliases,instance),"component_source_id":resolved(&aliases,source)})
            }).collect();
            if let Some(last) = component_path.last() {
                row["instance_item_id"] = last["instance_item_id"].clone();
                row["component_source_id"] = last["component_source_id"].clone();
                row["component_path"] = json!(component_path);
            }
            remap(
                row,
                &[
                    "item_id",
                    "viewport_item_id",
                    "image_item_id",
                    "resource_item_id",
                    "instance_item_id",
                    "component_source_id",
                ],
                &aliases,
            );
        }
        // Resource receipts retain the source tree context even when sharing
        // removes a copied host from the stored document.
        for row in &mut self.definitions.records {
            self.control.check()?;
            if let Some(path) = row.get_mut("instance_path").and_then(Value::as_array_mut) {
                for entry in path {
                    if let Some((instance, source)) =
                        entry["item_id"].as_str().and_then(|id| placements.get(id))
                    {
                        entry["instance_item_id"] = json!(instance);
                        entry["component_source_id"] = json!(source);
                    }
                    remap(
                        entry,
                        &["item_id", "instance_item_id", "component_source_id"],
                        &aliases,
                    );
                }
            }
            remap(row, &["item_id"], &aliases);
        }
        for row in &mut receipts {
            remap(
                row,
                &["host_item_id", "instance_item_id", "component_source_id"],
                &aliases,
            );
        }
        if variants {
            self.losses.push("SVG reuse contexts that cannot be represented by native geometry-preserving overrides become separate component variants; edits do not propagate between these variants.".into());
        }
        if receipts.iter().any(|r| r["mode"] == "expanded") {
            self.losses.push("Some SVG references remain independent editable groups; reuse receipts identify empty content or native component limits. Keep the original SVG for those source relationships.".into());
        }
        if definitions != 0 {
            self.losses.push("Compatible SVG references become native components with resolved placement overrides. Edit mapped source items for shared changes or instance overrides for local changes; CSS inheritance is not live editing state. SVG export expands components and reports sharing loss.".into());
        }
        self.document = document;
        Ok(receipts)
    }
}
