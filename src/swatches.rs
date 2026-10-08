//! Original named color declarations, retained tints and explicit display previews.
use crate::{
    Error,
    model::*,
    paint::{Paint, Precise},
    scene,
};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};
pub mod device;

pub const MAX_SWATCHES: usize = 256;
pub const MAX_DEPTH: usize = 8;
fn one() -> f64 {
    1.0
}
fn invalid(message: &str) -> Error {
    Error::new("INVALID_SWATCH", message)
}
fn unit(v: f64) -> bool {
    v.is_finite() && (0.0..=1.0).contains(&v)
}
fn name(v: &str) -> bool {
    !v.is_empty()
        && v.len() <= 256
        && !v
            .chars()
            .any(|c| c.is_control() || matches!(c, '\u{fffe}' | '\u{ffff}'))
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(tag = "space", rename_all = "snake_case", deny_unknown_fields)]
pub enum Process {
    Device {
        encoding: crate::profiles::device::Endpoint,
        components: Vec<f64>,
        #[serde(default)]
        intent: crate::profiles::Intent,
    },
    Srgb {
        components: [f64; 3],
    },
    Gray {
        component: f64,
    },
    Cmyk {
        components: [f64; 4],
        #[serde(default, skip_serializing_if = "Option::is_none")]
        preview_srgb: Option<[f64; 3]>,
    },
    Lab {
        components: [f64; 3],
        #[serde(default, skip_serializing_if = "Option::is_none")]
        preview_srgb: Option<[f64; 3]>,
    },
}
impl Process {
    fn validate(&self) -> Result<(), Error> {
        let valid = match self {
            Self::Device {
                encoding,
                components,
                intent,
            } => {
                crate::profiles::device::validate_value(encoding, *intent, components)?;
                true
            }
            Self::Srgb { components } => components.iter().all(|v| unit(*v)),
            Self::Gray { component } => unit(*component),
            Self::Cmyk { components, .. } => components.iter().all(|v| unit(*v)),
            Self::Lab {
                components: [l, a, b],
                ..
            } => {
                l.is_finite()
                    && (0.0..=100.0).contains(l)
                    && [a, b]
                        .iter()
                        .all(|v| v.is_finite() && (-128.0..=127.0).contains(*v))
            }
        };
        if !valid || self.preview().is_some_and(|p| p.iter().any(|v| !unit(*v))) {
            return Err(invalid(
                "Color components or explicit preview are outside their declared finite ranges",
            ));
        }
        Ok(())
    }
    fn preview(&self) -> Option<[f64; 3]> {
        match self {
            Self::Device { .. } => None,
            Self::Srgb { components } => Some(*components),
            Self::Gray { component } => Some([*component; 3]),
            Self::Cmyk { preview_srgb, .. } | Self::Lab { preview_srgb, .. } => *preview_srgb,
        }
    }
    fn needs_conversion(&self) -> bool {
        matches!(
            self,
            Self::Cmyk { .. } | Self::Lab { .. } | Self::Device { .. }
        )
    }
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Definition {
    Process { color: Process },
    Spot { alternate: Process },
    Tint { base: String, tint: f64 },
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Swatch {
    pub name: String,
    pub definition: Definition,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Reference {
    pub swatch: String,
    #[serde(default = "one")]
    pub tint: f64,
    #[serde(default = "one")]
    pub opacity: f64,
    #[serde(default, skip_serializing_if = "Overprint::is_knockout")]
    pub overprint: Overprint,
}
/// Controls which existing ink components a named paint replaces in native delivery.
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Overprint {
    #[default]
    Knockout,
    Preserve,
    PreserveNonzero,
}
impl Overprint {
    pub fn is_knockout(&self) -> bool {
        *self == Self::Knockout
    }
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ConvertKind {
    Process,
    Spot,
}

#[derive(Clone, Debug, Serialize)]
pub(crate) struct NativePaint {
    pub base_id: String,
    pub spot_id: Option<String>,
    pub color: Process,
    pub tint: f64,
    pub opacity: f64,
    pub overprint: Overprint,
}
pub(crate) fn native(
    table: &BTreeMap<String, Swatch>,
    reference: &Reference,
) -> Result<NativePaint, Error> {
    reference.validate()?;
    let resolved = resolve(table, &reference.swatch)?;
    let color = match &table[&resolved.base_id].definition {
        Definition::Process { color } | Definition::Spot { alternate: color } => color.clone(),
        Definition::Tint { .. } => unreachable!(),
    };
    Ok(NativePaint {
        base_id: resolved.base_id,
        spot_id: resolved.spot_id,
        color,
        tint: resolved.tint * reference.tint,
        opacity: reference.opacity,
        overprint: reference.overprint,
    })
}
impl Reference {
    pub(crate) fn validate(&self) -> Result<(), Error> {
        if !valid_id(&self.swatch) || !unit(self.tint) || !unit(self.opacity) {
            return Err(invalid(
                "Named paint requires a valid swatch ID and finite tint/opacity in 0..=1",
            ));
        }
        Ok(())
    }
}
#[derive(Serialize)]
pub(crate) struct Resolved {
    base_id: String,
    spot_id: Option<String>,
    tint: f64,
    preview_srgb: Option<[f64; 3]>,
    requires_color_conversion: bool,
    dependencies: BTreeSet<String>,
}
fn resolve(table: &BTreeMap<String, Swatch>, id: &str) -> Result<Resolved, Error> {
    let mut next = id;
    let mut dependencies = BTreeSet::new();
    let mut tint = 1.0;
    loop {
        if !dependencies.insert(next.to_string()) {
            return Err(invalid("Tint definitions contain a cycle"));
        }
        if dependencies.len() > MAX_DEPTH {
            return Err(limit("Swatch reference chain exceeds eight definitions"));
        }
        let swatch = table.get(next).ok_or_else(|| {
            Error::new("SWATCH_NOT_FOUND", format!("Swatch {next} does not exist"))
        })?;
        if !valid_id(next) || !name(&swatch.name) {
            return Err(invalid(
                "Swatch requires a valid ID and a nonempty printable name of at most 256 bytes",
            ));
        }
        let (color, spot) = match &swatch.definition {
            Definition::Tint { base, tint: amount } => {
                if !valid_id(base) || !unit(*amount) {
                    return Err(invalid(
                        "Tint requires a valid base ID and a finite value in 0..=1",
                    ));
                }
                tint *= amount;
                next = base;
                continue;
            }
            Definition::Process { color } => (color, false),
            Definition::Spot { alternate } => (alternate, true),
        };
        color.validate()?;
        return Ok(Resolved {
            base_id: next.into(),
            spot_id: spot.then(|| next.into()),
            tint,
            preview_srgb: color.preview(),
            requires_color_conversion: color.needs_conversion(),
            dependencies,
        });
    }
}
fn resolved_paint(
    table: &BTreeMap<String, Swatch>,
    reference: &Reference,
) -> Result<Precise, Error> {
    reference.validate()?;
    let r = resolve(table, &reference.swatch)?;
    let t = r.tint * reference.tint;
    let color = match &table[&r.base_id].definition {
        Definition::Process { color } | Definition::Spot { alternate: color } => color,
        Definition::Tint { .. } => unreachable!(),
    };
    if let Process::Device {
        encoding,
        components,
        intent,
    } = color
    {
        let values = device::tinted(encoding, components, t);
        let sample =
            crate::profiles::device::Connection::new(encoding, &device::display(), *intent)?
                .sample(&values)?;
        return Ok(Precise {
            rgba: [
                sample.values[0],
                sample.values[1],
                sample.values[2],
                reference.opacity,
            ],
        });
    }
    let rgb = r.preview_srgb.ok_or_else(|| Error::new("SWATCH_PREVIEW_REQUIRED", "Non-RGB declarations require an explicit preview_srgb; no implicit profile conversion is performed"))?;
    Ok(Precise {
        rgba: [
            1.0 + t * (rgb[0] - 1.0),
            1.0 + t * (rgb[1] - 1.0),
            1.0 + t * (rgb[2] - 1.0),
            reference.opacity,
        ],
    })
}

type Visitor<'a> = dyn FnMut(&mut Paint) -> Result<(), Error> + 'a;
fn stroke(stroke: &mut Option<Box<Stroke>>, visit: &mut Visitor<'_>) -> Result<(), Error> {
    if let Some(s) = stroke {
        visit(&mut s.color)?;
    }
    Ok(())
}
fn text(frame: &mut crate::text::Frame, visit: &mut Visitor<'_>) -> Result<(), Error> {
    visit(&mut frame.style.fill)?;
    for r in &mut frame.ranges {
        visit(&mut r.style.fill)?;
    }
    Ok(())
}
fn content(c: &mut Content, visit: &mut Visitor<'_>, depth: usize) -> Result<(), Error> {
    if depth > crate::instances::MAX_NESTING {
        return Err(limit(
            "Named-paint override traversal exceeds component nesting limit",
        ));
    }
    match c {
        Content::Vector {
            fill, stroke: s, ..
        } => {
            if let Some(p) = fill {
                visit(p)?;
            }
            stroke(s, visit)?;
        }
        Content::Fill { paint, .. } => visit(paint)?,
        Content::Text { frame } => text(frame, visit)?,
        Content::Warp { warp } => {
            if let Some(p) = &mut warp.fill {
                visit(p)?;
            }
            stroke(&mut warp.stroke, visit)?;
        }
        Content::Appearance { appearance } => {
            for p in &mut appearance.passes {
                if let Some(fill) = &mut p.fill {
                    visit(fill)?;
                }
                stroke(&mut p.stroke, visit)?;
                for effect in &mut p.effects {
                    visit(&mut effect.color)?;
                }
            }
        }
        Content::Repeat { repeat } => visit(&mut repeat.fill)?,
        Content::Interpolation { interpolation } => {
            stroke(&mut interpolation.from.stroke, visit)?;
            stroke(&mut interpolation.to.stroke, visit)?;
        }
        Content::Instance { instance } => {
            for patch in instance.overrides.values_mut() {
                if let Some(c) = &mut patch.content {
                    content(c, visit, depth + 1)?;
                }
                if let Some(s) = &mut patch.vector_style {
                    if let Some(p) = &mut s.fill {
                        visit(p)?;
                    }
                    stroke(&mut s.stroke, visit)?;
                }
            }
        }
        _ => {}
    }
    Ok(())
}
pub(crate) fn walk(item: &mut Item, visit: &mut Visitor<'_>) -> Result<(), Error> {
    content(&mut item.content, visit, 0)?;
    for effect in &mut item.effects {
        visit(&mut effect.color)?;
    }
    Ok(())
}
fn story_ids(d: &Document, item: &Item) -> BTreeSet<String> {
    d.stories
        .keys()
        .filter(|id| crate::text::flow::uses(&item.content, id))
        .cloned()
        .collect()
}
fn walk_bound(d: &Document, item: &Item, visit: &mut Visitor<'_>) -> Result<(), Error> {
    walk(&mut item.clone(), visit)?;
    for id in story_ids(d, item) {
        for style in d.stories[&id].styles() {
            visit(&mut style.fill.clone())?;
        }
    }
    Ok(())
}
pub(crate) fn remap_story(story: &mut crate::text::flow::Story, ids: &BTreeMap<String, String>) {
    for style in story.styles_mut() {
        if let Paint::Named(r) = &mut style.fill {
            r.swatch = ids[&r.swatch].clone();
        }
    }
}
fn variants(
    d: &Document,
    visit: &mut dyn FnMut(&str, &mut Paint) -> Result<(), Error>,
) -> Result<(), Error> {
    if let Some(v) = &d.variants {
        for (i, b) in v.definition.bindings.iter().enumerate() {
            let values = v.base.get(i).into_iter().chain(
                v.definition
                    .datasets
                    .values()
                    .filter_map(|row| row.values.get(&b.key)),
            );
            for value in values {
                if let crate::variants::Value::Text(t) = value {
                    for r in &t.ranges {
                        visit(&b.item_id, &mut r.style.fill.clone())?;
                    }
                }
            }
        }
    }
    Ok(())
}
pub fn validate(d: &Document) -> Result<(), Error> {
    if d.swatches.len() > MAX_SWATCHES {
        return Err(limit("Document exceeds 256 named swatches"));
    }
    for id in d.swatches.keys() {
        resolve(&d.swatches, id)?;
    }
    let mut check = |p: &mut Paint| {
        if let Paint::Named(reference) = p {
            reference.validate()?;
            resolve(&d.swatches, &reference.swatch)?;
        }
        Ok(())
    };
    for item in &d.items {
        walk(&mut item.clone(), &mut check).map_err(|e| e.at_item(&item.id))?;
    }
    for story in d.stories.values() {
        for style in story.styles() {
            check(&mut style.fill.clone())?;
        }
    }
    variants(d, &mut |id, p| check(p).map_err(|e| e.at_item(id)))
}
pub(crate) fn references(d: &Document, item: &Item) -> Result<BTreeSet<String>, Error> {
    let mut ids = BTreeSet::new();
    walk_bound(d, item, &mut |p| {
        if let Paint::Named(r) = p {
            ids.insert(r.swatch.clone());
        }
        Ok(())
    })?;
    Ok(ids)
}
pub(crate) fn closure(
    table: &BTreeMap<String, Swatch>,
    roots: &BTreeSet<String>,
) -> Result<BTreeSet<String>, Error> {
    let mut result = BTreeSet::new();
    for id in roots {
        result.extend(resolve(table, id)?.dependencies);
    }
    Ok(result)
}
pub(crate) fn remap(item: &mut Item, ids: &BTreeMap<String, String>) -> Result<(), Error> {
    walk(item, &mut |p| {
        if let Paint::Named(r) = p {
            r.swatch = ids[&r.swatch].clone();
        }
        Ok(())
    })
}
pub(crate) fn evaluate(d: &Document) -> Result<Option<Document>, Error> {
    let mut changed = false;
    let mut out = d.clone();
    for item in &mut out.items {
        walk(item, &mut |p| {
            if let Paint::Named(r) = p {
                if !r.overprint.is_knockout() {
                    return Err(Error::new(
                        "OVERPRINT_PREVIEW_UNSUPPORTED",
                        "Display rendering does not simulate ink overprint; use native-ink PDF delivery or explicitly bake a display copy",
                    ));
                }
                *p = Paint::Precise(resolved_paint(&d.swatches, r)?);
                changed = true;
            }
            Ok(())
        })?;
    }
    let stories: BTreeSet<_> = d.items.iter().flat_map(|i| story_ids(d, i)).collect();
    for id in stories {
        for style in out.stories.get_mut(&id).unwrap().styles_mut() {
            if let Paint::Named(r) = &style.fill {
                if !r.overprint.is_knockout() {
                    return Err(Error::new(
                        "OVERPRINT_PREVIEW_UNSUPPORTED",
                        "Display rendering does not simulate story ink overprint; use native-ink PDF or explicitly bake a display copy",
                    ));
                }
                style.fill = Paint::Precise(resolved_paint(&d.swatches, r)?);
                changed = true;
            }
        }
    }
    Ok(changed.then_some(out))
}
fn used(d: &Document) -> Result<BTreeSet<String>, Error> {
    let mut result = BTreeSet::new();
    for item in &d.items {
        result.extend(references(d, item)?);
    }
    closure(&d.swatches, &result)
}
pub(crate) fn vector_export(d: &Document) -> Result<(), Error> {
    for item in &d.items {
        walk_bound(d, item, &mut |paint| {
            if matches!(paint, Paint::Named(r) if !r.overprint.is_knockout()) {
                return Err(Error::new(
                    "UNSUPPORTED",
                    "Display vector delivery cannot preserve overprint; use native-ink PDF or explicitly bake a display copy",
                ));
            }
            Ok(())
        })?;
    }
    for id in used(d)? {
        let r = resolve(&d.swatches, &id)?;
        if r.spot_id.is_some() || r.requires_color_conversion {
            return Err(Error::new(
                "UNSUPPORTED",
                "Vector delivery does not yet preserve spot/non-RGB swatch semantics; explicitly bake display previews on a document copy or retain the snapshot",
            ));
        }
    }
    Ok(())
}
pub(crate) fn annotate(d: &Document, artifact: &mut Value) -> Result<(), Error> {
    if artifact.get("swatches").is_some() {
        return Ok(());
    }
    let ids = used(d)?;
    if !ids.is_empty() {
        artifact["swatches"] = json!({"used_ids":ids,"color":"encoded_srgb_display_preview","tint":"legacy_display_white_interpolation;device_components_before_profile_conversion","native_ink_preservation":false,"editable_source":"snapshot"});
        let losses = artifact
            .as_object_mut()
            .unwrap()
            .entry("losses")
            .or_insert_with(|| json!([]))
            .as_array_mut()
            .unwrap();
        losses.push(json!("Named colors and spot tints are delivered as display previews; the snapshot retains exact declarations and references. Device declarations use their explicit profiles; other non-RGB declarations require supplied previews. This is not ink separation or print proof."));
    }
    Ok(())
}
pub fn inspect(d: &Document) -> Result<Value, Error> {
    crate::validate(d)?;
    let mut entries = Vec::new();
    for (id, swatch) in &d.swatches {
        let resolved = resolve(&d.swatches, id)?;
        let mut users = Vec::new();
        let mut variant_users = BTreeSet::new();
        variants(d, &mut |owner, p| {
            if let Paint::Named(r) = p
                && resolve(&d.swatches, &r.swatch)?.dependencies.contains(id)
            {
                variant_users.insert(owner.to_string());
            }
            Ok(())
        })?;
        for item in &d.items {
            if closure(&d.swatches, &references(d, item)?)?.contains(id) {
                users.push(item.id.clone());
            }
        }
        let rgba = resolved_paint(
            &d.swatches,
            &Reference {
                swatch: id.clone(),
                tint: 1.0,
                opacity: 1.0,
                overprint: Overprint::Knockout,
            },
        )
        .ok()
        .map(|c| c.rgba);
        let stories: Vec<_> = d.stories.iter().filter_map(|(key,story)|story.styles().any(|s| matches!(&s.fill,Paint::Named(r) if resolve(&d.swatches,&r.swatch).is_ok_and(|v|v.dependencies.contains(id)))).then_some(key)).collect();
        entries.push(json!({"id":id,"swatch":swatch,"resolved":resolved,"preview_rgba":rgba,"used_by":users,"variant_users":variant_users,"story_users":stories}));
    }
    Ok(
        json!({"document_id":d.id,"revision":d.revision,"swatches":entries,"ink_diagnostics":ink_diagnostics(d)?,"palette_sha256":crate::assets::sha256(&crate::metadata::canonical(&d.swatches)),"declarations":"stored_binary64_without_rgb_conversion","preview":"encoded_srgb;device_uses_declared_profile_and_intent;legacy_non_rgb_requires_explicit_preview;not_print_proof","source_changed":false}),
    )
}
pub(crate) fn set(d: &mut Document, id: &str, swatch: Option<&Swatch>) -> Result<Value, Error> {
    if !valid_id(id) {
        return Err(invalid("Swatch ID is invalid"));
    }
    if swatch.is_none() && !d.swatches.contains_key(id) {
        return Err(Error::new("SWATCH_NOT_FOUND", "Swatch does not exist"));
    }
    let mut users = BTreeSet::new();
    for (i, item) in d.items.iter().enumerate() {
        if closure(&d.swatches, &references(d, item)?)?.contains(id) {
            scene::check_unlocked(d, i, false)?;
            users.insert(item.id.clone());
        }
    }
    variants(d, &mut |owner, p| {
        if let Paint::Named(r) = p
            && resolve(&d.swatches, &r.swatch)?.dependencies.contains(id)
        {
            scene::check_unlocked(d, scene::index(d, owner)?, false)?;
            users.insert(owner.to_string());
        }
        Ok(())
    })?;
    let story_users: Vec<_> = d.stories.iter().filter_map(|(key,story)|story.styles().any(|s| matches!(&s.fill,Paint::Named(r) if resolve(&d.swatches,&r.swatch).is_ok_and(|v|v.dependencies.contains(id)))).then_some(key.clone())).collect();
    if swatch.is_none()
        && (!users.is_empty()
            || !story_users.is_empty()
            || d.swatches.iter().any(|(key, s)| {
                key != id && matches!(&s.definition,Definition::Tint { base, .. } if base==id)
            }))
    {
        return Err(Error::new(
            "SWATCH_IN_USE",
            "Remove paint and tint references before deleting a swatch",
        ));
    }
    let before = d.swatches.get(id).cloned();
    if let Some(s) = swatch {
        d.swatches.insert(id.into(), s.clone());
    } else {
        d.swatches.remove(id);
    }
    validate(d)?;
    Ok(
        json!({"id":id,"before":before,"after":swatch,"affected_items":users,"affected_stories":story_users,"source_values_retained":true}),
    )
}
pub(crate) fn bake(d: &mut Document, ids: &[String]) -> Result<Value, Error> {
    let selected = scene::selection(d, ids, true)?;
    let mut members = BTreeSet::new();
    for i in selected {
        scene::check_unlocked(d, i, true)?;
        members.extend(scene::subtree(d, i));
    }
    let mut records = Vec::new();
    let mut story_copies = BTreeMap::new();
    let stories: BTreeSet<_> = members
        .iter()
        .flat_map(|i| story_ids(d, &d.items[*i]))
        .collect();
    let mut story_records = Vec::new();
    for id in stories {
        let mut source = d.stories[&id].clone();
        let mut count = 0;
        for style in source.styles_mut() {
            if let Paint::Named(r) = &style.fill {
                style.fill = Paint::Precise(resolved_paint(&d.swatches, r)?);
                count += 1;
            }
        }
        if count == 0 {
            continue;
        }
        let shared =
            d.items.iter().enumerate().any(|(i, item)| {
                !members.contains(&i) && crate::text::flow::uses(&item.content, &id)
            });
        let destination = if shared {
            (1..)
                .map(|n| format!("display-story-{n}"))
                .find(|id| !d.stories.contains_key(id))
                .unwrap()
        } else {
            id.clone()
        };
        d.stories.insert(destination.clone(), source);
        story_copies.insert(id.clone(), destination.clone());
        story_records.push(
            json!({"source":id,"destination":destination,"paints":count,"independent_copy":shared}),
        );
    }
    for i in members {
        rebind_stories(&mut d.items[i].content, &story_copies);
        let mut count = 0;
        walk(&mut d.items[i], &mut |p| {
            if let Paint::Named(r) = p {
                *p = Paint::Precise(resolved_paint(&d.swatches, r)?);
                count += 1;
            }
            Ok(())
        })?;
        if count > 0 {
            records.push(json!({"id":d.items[i].id,"paints":count}));
        }
    }
    Ok(
        json!({"items":records,"stories":story_records,"palette_retained":true,"loss":"Selected current paints lose global color/spot/tint references and overprint instructions and become precise display sRGB. This does not simulate overprinted inks. Selected story bindings copy their source when other bindings must stay live; otherwise the selected source is baked in place. Variant datasets and unrelated resource definitions remain live."}),
    )
}
fn rebind_stories(content: &mut Content, ids: &BTreeMap<String, String>) {
    match content {
        Content::StoryFrame { story_id, .. } => {
            if let Some(id) = ids.get(story_id) {
                *story_id = id.clone();
            }
        }
        Content::Instance { instance } => {
            for patch in instance.overrides.values_mut() {
                if let Some(c) = &mut patch.content {
                    rebind_stories(c, ids);
                }
            }
        }
        _ => {}
    }
}

pub(crate) fn convert(
    d: &mut Document,
    id: &str,
    kind: ConvertKind,
    replacement: Option<&Process>,
) -> Result<Value, Error> {
    let before = d
        .swatches
        .get(id)
        .ok_or_else(|| Error::new("SWATCH_NOT_FOUND", "Swatch does not exist"))?
        .clone();
    let original = match &before.definition {
        Definition::Process { color } | Definition::Spot { alternate: color } => color,
        Definition::Tint { .. } => {
            return Err(invalid(
                "Convert the base definition of a tint; tint aliases remain attached to it",
            ));
        }
    };
    let color = replacement.unwrap_or(original).clone();
    color.validate()?;
    let after = Swatch {
        name: before.name.clone(),
        definition: match kind {
            ConvertKind::Process => Definition::Process { color },
            ConvertKind::Spot => Definition::Spot { alternate: color },
        },
    };
    let mut receipt = set(d, id, Some(&after))?;
    receipt["conversion"] = json!({"kind":kind,"component_policy":if replacement.is_some(){"caller_supplied_declaration"}else{"retain_exact_components"},"profile_conversion":false,"references_retained":true,"overprint_retained":true,"separation_change":"Changing spot/process classification changes the affected ink channels; overprinted appearance may change. Explicit native export diagnostics apply."});
    Ok(receipt)
}

/// Structural inventory, not plate coverage or a proof of exportability.
pub(crate) fn ink_diagnostics(d: &Document) -> Result<Value, Error> {
    let mut paints = Vec::new();
    let mut spots = BTreeMap::new();
    let mut process_spaces = BTreeSet::new();
    let mut overprint_items = BTreeSet::new();
    let mut display_paints = 0;
    for item in &d.items {
        let mut ordinal = 0;
        walk_bound(d, item, &mut |paint| {
            if let Paint::Named(reference) = paint {
                let p = native(&d.swatches, reference)?;
                let space = match p.color {
                    Process::Device { .. } => "profiled_device",
                    Process::Srgb { .. } => "srgb",
                    Process::Gray { .. } => "gray",
                    Process::Cmyk { .. } => "cmyk",
                    Process::Lab { .. } => "lab",
                };
                if let Some(id) = &p.spot_id {
                    spots.insert(id.clone(), json!({"id":id,"name":d.swatches[id].name,"pdf_name":format!("Inkbolt.{id}"),"alternate":p.color}));
                } else {
                    process_spaces.insert(space);
                }
                let supported_overprint = p.overprint.is_knockout()
                    || p.spot_id.is_some()
                    || matches!(p.color, Process::Cmyk { .. });
                if !p.overprint.is_knockout() {
                    overprint_items.insert(item.id.clone());
                }
                paints.push(json!({"item_id":item.id,"paint_ordinal":ordinal,"reference":reference,"resolved":p,"native_overprint_supported":supported_overprint}));
            } else {
                display_paints += 1;
            }
            ordinal += 1;
            Ok(())
        })?;
    }
    Ok(
        json!({"scope":"structural_named_paints_including_hidden_resources;not_plate_coverage_or_export_preflight","spots":spots.values().collect::<Vec<_>>(),"process_spaces":process_spaces,"overprint_items":overprint_items,"paints":paints,"other_display_paints":display_paints,"rgb_lab_process_separation":"requires_consumer_color_conversion;no_profile_proof","ink_identity":"Inkbolt.<base_swatch_id>;labels_do_not_merge_inks","saved_variants":"inventory_uses_current_item_paints;swatch_entries_report_saved_variant_dependents"}),
    )
}
pub(crate) fn dependency_hash(d: &Document, i: usize) -> Result<Option<String>, Error> {
    let mut visited = BTreeSet::new();
    let mut pending = vec![i];
    let mut ids = BTreeSet::new();
    while let Some(i) = pending.pop() {
        if !visited.insert(i) {
            continue;
        }
        let item = &d.items[i];
        ids.extend(references(d, item)?);
        pending.extend(scene::children(d, Some(&item.id)));
        if let Content::Instance { instance } = &item.content {
            pending.push(scene::index(d, &instance.source)?);
        }
        if let Some(mask) = &item.artwork_mask {
            pending.push(scene::index(d, &mask.source)?);
        }
    }
    let definitions: BTreeMap<_, _> = closure(&d.swatches, &ids)?
        .into_iter()
        .map(|id| {
            let v = d.swatches[&id].clone();
            (id, v)
        })
        .collect();
    Ok((!definitions.is_empty())
        .then(|| crate::assets::sha256(&crate::metadata::canonical(&definitions))))
}
