//! Original shared component definitions and deterministic local materialization.
use crate::{Error, geometry, model::*, scene};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, HashMap, HashSet};

pub const MAX_DEFINITIONS: usize = 32;
pub const MAX_NESTING: usize = 8;

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct VectorStyle {
    pub fill: Option<Paint>,
    pub stroke: Option<Box<Stroke>>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub fill_rule: Option<FillRule>,
}
#[derive(Clone, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Override {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub visible: Option<bool>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub opacity: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub fill_opacity: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub blend: Option<BlendMode>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub transform: Option<Matrix>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub content: Option<Box<Content>>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub vector_style: Option<VectorStyle>,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Instance {
    pub source: String,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub overrides: BTreeMap<String, Override>,
}
/// Resource edits must also inspect replacement content stored in overrides.
pub(crate) fn any_content(content: &Content, test: &impl Fn(&Content) -> bool) -> bool {
    test(content)
        || if let Content::Instance { instance } = content {
            instance
                .overrides
                .values()
                .any(|p| p.content.as_ref().is_some_and(|c| any_content(c, test)))
        } else {
            false
        }
}
pub(crate) fn source_owner(d: &Document, i: usize) -> Result<Option<usize>, Error> {
    Ok(std::iter::once(i)
        .chain(scene::ancestors(d, i)?)
        .find(|&j| matches!(d.items[j].content, Content::ComponentSource {})))
}
fn group() -> Content {
    Content::Group {
        isolated: true,
        role: GroupRole::Group,
        knockout: false,
    }
}
fn source(d: &Document, id: &str) -> Result<usize, Error> {
    let i = scene::index(d, id).map_err(|_| invalid("Instance component source does not exist"))?;
    if !matches!(d.items[i].content, Content::ComponentSource {}) || d.items[i].parent.is_some() {
        return Err(invalid(
            "Instance source must be a top-level component_source",
        ));
    }
    Ok(i)
}
fn patched(mut item: Item, patch: Option<&Override>) -> Result<Item, Error> {
    if let Some(p) = patch {
        if let Some(v) = &p.name {
            item.name = v.clone();
        }
        if let Some(v) = p.visible {
            item.visible = v;
        }
        if let Some(v) = p.opacity {
            item.opacity = v;
        }
        if let Some(v) = p.fill_opacity {
            item.fill_opacity = v;
        }
        if let Some(v) = p.blend {
            item.blend = v;
        }
        if let Some(v) = p.transform {
            item.transform = v;
        }
        if let Some(v) = &p.content {
            if matches!(item.content, Content::ComponentSource {})
                || matches!(**v, Content::ComponentSource {} | Content::MaskSource {})
            {
                return Err(invalid("Overrides cannot replace or create resource roots"));
            }
            if let Content::Frame { frame } = v.as_ref()
                && frame.role == crate::boards::Role::Artboard
            {
                return Err(Error::new(
                    "UNSUPPORTED",
                    "Component overrides cannot create artboard ownership",
                ));
            }
            item.content = *v.clone();
        }
        if let Some(v) = &p.vector_style {
            let Content::Vector {
                fill,
                stroke,
                fill_rule,
                ..
            } = &mut item.content
            else {
                return Err(invalid("A vector_style override requires vector content"));
            };
            *fill = v.fill.clone();
            *stroke = v.stroke.clone();
            if let Some(v) = v.fill_rule {
                *fill_rule = v;
            }
        }
    }
    Ok(item)
}
fn rebase_masks(item: &mut Item, world: Matrix) {
    for mask in item.mask.iter_mut().map(|v| v.as_mut()).chain(
        item.filters
            .iter_mut()
            .filter_map(|f| f.mask.as_deref_mut()),
    ) {
        if !mask.linked {
            mask.transform = geometry::multiply(world, mask.transform);
        }
    }
    if let Some(mask) = &mut item.artwork_mask
        && !mask.linked
    {
        mask.transform = geometry::multiply(world, mask.transform);
    }
}
struct Builder<'a> {
    original: &'a Document,
    used: HashSet<String>,
    items: Vec<Item>,
}
impl<'a> Builder<'a> {
    fn new(d: &'a Document) -> Self {
        Self {
            original: d,
            used: d.items.iter().map(|i| i.id.clone()).collect(),
            items: vec![],
        }
    }
    fn id(&mut self, instance: &str, item: &str) -> String {
        let key = serde_json::to_vec(&(instance, item)).unwrap();
        let prefix = format!("ib-instance-{}", &crate::assets::sha256(&key)[..24]);
        let mut value = prefix.clone();
        let mut n = 0;
        while !self.used.insert(value.clone()) {
            n += 1;
            value = format!("{prefix}-{n}");
        }
        value
    }
    fn emit(&mut self, item: Item, world: Matrix, stack: &[String]) -> Result<(), Error> {
        if self.items.len() == self.original.resource_profile.items() {
            return Err(limit(
                "Resolved component instances exceed the document resource-profile item budget",
            ));
        }
        let instance = if let Content::Instance { instance } = &item.content {
            Some(*instance.clone())
        } else {
            None
        };
        let id = item.id.clone();
        self.items.push(if instance.is_some() {
            Item {
                content: group(),
                ..item
            }
        } else {
            item
        });
        if let Some(instance) = instance {
            if stack.contains(&instance.source) {
                return Err(invalid("Component references contain a cycle"));
            }
            if stack.len() == MAX_NESTING {
                return Err(limit("Component references exceed 8 nested definitions"));
            }
            let mut next = stack.to_vec();
            next.push(instance.source.clone());
            let source = source(self.original, &instance.source)?;
            let members = scene::subtree(self.original, source);
            if instance
                .overrides
                .keys()
                .any(|id| !members.iter().any(|&i| &self.original.items[i].id == id))
            {
                return Err(invalid(
                    "Instance override target is not owned by its component definition",
                ));
            }
            let ids: HashMap<_, _> = members
                .iter()
                .map(|&i| {
                    let old = self.original.items[i].id.clone();
                    let new = self.id(&id, &old);
                    (old, new)
                })
                .collect();
            // Parent-first traversal computes placement once, while original
            // sibling ordering remains unchanged inside each cloned container.
            let mut worlds = HashMap::new();
            for i in members {
                let original = &self.original.items[i];
                let mut child = patched(original.clone(), instance.overrides.get(&original.id))?;
                child.id = ids[&original.id].clone();
                child.parent = Some(if i == source {
                    id.clone()
                } else {
                    ids[original.parent.as_ref().unwrap()].clone()
                });
                if let Some(base) = &mut child.clip_to
                    && let Some(mapped) = ids.get(base)
                {
                    *base = mapped.clone();
                }
                if let Content::Adjustment { adjustment } = &mut child.content
                    && let Some(base) = &mut adjustment.clip_to
                    && let Some(mapped) = ids.get(base)
                {
                    *base = mapped.clone();
                }
                if matches!(child.content, Content::ComponentSource {}) {
                    child.content = group();
                }
                rebase_masks(&mut child, world);
                let parent_world = if i == source {
                    world
                } else {
                    worlds[original.parent.as_ref().unwrap()]
                };
                let child_world = geometry::multiply(parent_world, child.transform);
                worlds.insert(original.id.clone(), child_world);
                self.emit(child, child_world, &next)?;
            }
        }
        Ok(())
    }
    fn finish(self) -> Document {
        let mut d = self.original.clone();
        d.variants = None;
        d.items = self.items;
        d
    }
}
pub(crate) fn evaluate(d: &Document) -> Result<Option<Document>, Error> {
    if !d.items.iter().any(|i| {
        matches!(
            i.content,
            Content::ComponentSource {} | Content::Instance { .. }
        )
    }) {
        return Ok(None);
    }
    let mut b = Builder::new(d);
    for (i, item) in d.items.iter().enumerate() {
        if source_owner(d, i)?.is_none() {
            b.emit(item.clone(), scene::world_transform(d, i)?, &[])?;
        }
    }
    Ok(Some(b.finish()))
}
pub(crate) fn instance_view(d: &Document, i: usize) -> Result<Document, Error> {
    let mut item = d.items[i].clone();
    item.parent = None;
    item.transform = scene::world_transform(d, i)?;
    let mut b = Builder::new(d);
    b.emit(item.clone(), item.transform, &[])?;
    Ok(b.finish())
}
pub(crate) fn validate(d: &Document, control: &crate::control::Control) -> Result<(), Error> {
    let definitions: Vec<_> = d
        .items
        .iter()
        .enumerate()
        .filter_map(|(i, v)| matches!(v.content, Content::ComponentSource {}).then_some(i))
        .collect();
    if definitions.len() > MAX_DEFINITIONS {
        return Err(limit("Document exceeds 32 component definitions"));
    }
    if definitions.is_empty()
        && !d
            .items
            .iter()
            .any(|i| matches!(i.content, Content::Instance { .. }))
    {
        return Ok(());
    }
    if d.kind != DocumentKind::Vector {
        return Err(Error::new(
            "UNSUPPORTED",
            "Component instances currently require a vector document",
        ));
    }
    for &s in &definitions {
        source(d, &d.items[s].id)?;
        for i in scene::subtree(d, s) {
            if let Content::Frame { frame } = &d.items[i].content
                && frame.role == crate::boards::Role::Artboard
            {
                return Err(Error::new(
                    "UNSUPPORTED",
                    "Component definitions support ordinary frames, not artboard ownership",
                ));
            }
        }
        // Validate unused definitions as well as placed copies. Mask resources
        // retain their own IDs and source coordinates in this isolated view.
        let mut b = Builder::new(d);
        for (i, item) in d.items.iter().enumerate() {
            if crate::artwork_masks::source_owner(d, i)?.is_some() {
                b.emit(item.clone(), scene::world_transform(d, i)?, &[])?;
            }
        }
        let virtual_item = Item {
            hdr_grade: None,
            pixel_warp: None,
            metadata: None,
            content: Content::Instance {
                instance: Box::new(Instance {
                    source: d.items[s].id.clone(),
                    overrides: BTreeMap::new(),
                }),
            },
            id: b.id("validation", &d.items[s].id),
            name: String::new(),
            visible: true,
            locked: false,
            opacity: 1.0,
            fill_opacity: 1.0,
            coverage: Default::default(),
            effects: vec![],
            blend: BlendMode::Normal,
            transform: identity(),
            parent: None,
            clip_to: None,
            clip: None,
            mask: None,
            artwork_mask: None,
            filters: vec![],
        };
        b.emit(virtual_item, identity(), &[])?;
        crate::model::validate_controlled(&b.finish(), control)?;
    }
    if let Some(expanded) = evaluate(d)? {
        crate::model::validate_controlled(&expanded, control)?;
    }
    Ok(())
}
pub(crate) fn include_sources(d: &Document, members: &mut HashSet<usize>) -> Result<(), Error> {
    fn references(instance: &Instance, depth: usize, ids: &mut Vec<String>) -> Result<(), Error> {
        if depth > MAX_NESTING {
            return Err(limit("Nested instance override data exceeds 8 levels"));
        }
        ids.push(instance.source.clone());
        for patch in instance.overrides.values() {
            if let Some(content) = &patch.content
                && let Content::Instance { instance } = content.as_ref()
            {
                references(instance, depth + 1, ids)?;
            }
        }
        Ok(())
    }
    loop {
        let old = members.len();
        for i in members.clone() {
            if let Content::Instance { instance } = &d.items[i].content {
                let mut ids = vec![];
                references(instance, 0, &mut ids)?;
                for id in ids {
                    members.extend(scene::subtree(d, source(d, &id)?));
                }
            }
            if let Some(mask) = &d.items[i].artwork_mask {
                members.extend(scene::subtree(d, scene::index(d, &mask.source)?));
            }
        }
        if old == members.len() {
            return Ok(());
        }
    }
}
pub(crate) fn check_dependents_unlocked(d: &Document, i: usize) -> Result<(), Error> {
    let Some(source) = source_owner(d, i)?.or(crate::artwork_masks::source_owner(d, i)?) else {
        return Ok(());
    };
    for (j, item) in d.items.iter().enumerate() {
        if item.locked {
            let mut members = scene::subtree(d, j).into_iter().collect();
            include_sources(d, &mut members)?;
            if members.contains(&source) {
                return Err(Error::new(
                    "LOCKED",
                    "Shared component or mask edit affects locked dependent artwork",
                ));
            }
        }
    }
    Ok(())
}
pub(crate) fn dependency_hash(d: &Document, i: usize) -> Result<Option<String>, Error> {
    if !matches!(d.items[i].content, Content::Instance { .. }) {
        return Ok(None);
    }
    let mut members = HashSet::from([i]);
    include_sources(d, &mut members)?;
    members.remove(&i);
    let mut members: Vec<_> = members.into_iter().collect();
    members.sort_unstable();
    let bytes = serde_json::to_vec(&(
        members.into_iter().map(|j| &d.items[j]).collect::<Vec<_>>(),
        &d.global_light,
        &d.assets,
        &d.fonts,
    ))
    .unwrap();
    Ok(Some(crate::assets::sha256(&bytes)))
}
pub(crate) fn unlink(d: &mut Document, i: usize) -> Result<serde_json::Value, Error> {
    let Content::Instance { instance } = &d.items[i].content else {
        return Err(Error::new(
            "INVALID_OPERATION",
            "Unlink requires a component instance",
        ));
    };
    let source = instance.source.clone();
    let mut b = Builder::new(d);
    b.emit(d.items[i].clone(), scene::world_transform(d, i)?, &[])?;
    let items = b.items;
    let created: Vec<_> = items[1..].iter().map(|i| i.id.clone()).collect();
    d.items.splice(i..=i, items);
    Ok(
        serde_json::json!({"source":source,"created_ids":created,"unlinked":true,"source_preserved":true}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn nonfinite_overrides_are_rejected_through_the_library() {
        let base: Document = serde_json::from_value(serde_json::json!({
            "schema_version":2,"id":"finite-components","revision":0,"kind":"vector","width":8,"height":8,"color_space":"srgb",
            "items":[{"id":"source","content":{"type":"component_source"}},
                {"id":"body","parent":"source","content":{"type":"vector","geometry":{"shape":"rect","x":0,"y":0,"width":4,"height":4},"fill":[0,0,0,255]}},
                {"id":"copy","content":{"type":"instance","instance":{"source":"source"}}}]
        })).unwrap();
        crate::validate(&base).unwrap();
        for value in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            for field in 0..3 {
                let mut d = base.clone();
                let Content::Instance { instance } = &mut d.items[2].content else {
                    unreachable!()
                };
                let mut patch = Override::default();
                match field {
                    0 => patch.opacity = Some(value),
                    1 => patch.fill_opacity = Some(value),
                    _ => patch.transform = Some([1.0, 0.0, 0.0, 1.0, value, 0.0]),
                }
                instance.overrides.insert("body".into(), patch);
                assert!(crate::validate(&d).is_err());
            }
        }
    }
}
