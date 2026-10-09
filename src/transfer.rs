//! Original immutable subtree transfer with explicit dependency and identity maps.
use crate::{Error, geometry, model::*, scene};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet, HashSet};
use std::path::Path;

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Transfer {
    pub source: Box<Document>,
    pub ids: Vec<String>,
    pub prefix: String,
    #[serde(default)]
    pub parent: Option<String>,
    #[serde(default)]
    pub verify_resources: bool,
}

fn renamed(prefix: &str, id: &str) -> String {
    let readable = format!("{prefix}-{id}");
    if readable.len() <= 128 {
        readable
    } else {
        format!("{prefix}-{}", crate::assets::sha256(id.as_bytes()))
    }
}
fn mapping<'a>(
    prefix: &str,
    ids: impl Iterator<Item = &'a str>,
    existing: impl Iterator<Item = &'a str>,
) -> Result<BTreeMap<String, String>, Error> {
    let mut used: BTreeSet<_> = existing.map(str::to_owned).collect();
    ids.map(|id| {
        let target = renamed(prefix, id);
        if !used.insert(target.clone()) {
            return Err(Error::new(
                "ID_CONFLICT",
                "Transfer ID collides with an existing or generated ID; use a different prefix",
            ));
        }
        Ok((id.into(), target))
    })
    .collect()
}

fn resource_ids(content: &Content, images: &mut BTreeSet<String>, fonts: &mut BTreeSet<String>) {
    match content {
        Content::Image { asset_id, .. } => {
            images.insert(asset_id.clone());
        }
        Content::Text { frame } => {
            fonts.extend(
                crate::text::styles(frame)
                    .flat_map(crate::text::Style::font_ids)
                    .cloned(),
            );
        }
        Content::Instance { instance } => {
            for patch in instance.overrides.values() {
                if let Some(c) = &patch.content {
                    resource_ids(c, images, fonts);
                }
            }
        }
        _ => {}
    }
}
fn remap_content(
    content: &mut Content,
    items: &BTreeMap<String, String>,
    images: &BTreeMap<String, String>,
    fonts: &BTreeMap<String, String>,
    stories: &BTreeMap<String, String>,
) {
    match content {
        Content::StoryFrame { story_id, .. } => *story_id = stories[story_id].clone(),
        Content::Image { asset_id, .. } => *asset_id = images[asset_id].clone(),
        Content::Text { frame } => {
            for style in std::iter::once(&mut frame.style)
                .chain(frame.ranges.iter_mut().map(|r| &mut r.style))
            {
                style.font_variations = std::mem::take(&mut style.font_variations)
                    .into_iter()
                    .map(|(id, values)| (fonts[&id].clone(), values))
                    .collect();
                style.font_id = fonts[&style.font_id].clone();
                for id in &mut style.fallback_fonts {
                    *id = fonts[id].clone();
                }
            }
        }
        Content::Instance { instance } => {
            instance.source = items[&instance.source].clone();
            instance.overrides = std::mem::take(&mut instance.overrides)
                .into_iter()
                .map(|(id, mut patch)| {
                    if let Some(c) = &mut patch.content {
                        remap_content(c, items, images, fonts, stories);
                    }
                    (items[&id].clone(), patch)
                })
                .collect();
        }
        Content::Adjustment { adjustment } => {
            if let Some(base) = &mut adjustment.clip_to {
                *base = items[base].clone();
            }
        }
        _ => {}
    }
}

pub(crate) fn apply(
    destination: &mut Document,
    transfer: &Transfer,
    asset_root: Option<&Path>,
    font_root: Option<&Path>,
    control: &crate::control::Control,
) -> Result<serde_json::Value, Error> {
    let source = transfer.source.as_ref();
    validate(source)?;
    if source.color_space != destination.color_space {
        return Err(Error::new(
            "UNSUPPORTED_HDR_MODE",
            "Cross-document transfer requires matching compositing spaces; convert the source explicitly first",
        ));
    }
    if !valid_id(&transfer.prefix) || transfer.prefix.len() > 32 {
        return Err(invalid(
            "Transfer prefix requires 1..32 valid ID characters",
        ));
    }
    let parent_inverse = if let Some(parent) = &transfer.parent {
        let i = scene::index(destination, parent)?;
        if !destination.items[i].content.is_container() {
            return Err(invalid("Transfer parent must be a container"));
        }
        scene::check_unlocked(destination, i, false)?;
        geometry::inverse(scene::world_transform(destination, i)?)?
    } else {
        identity()
    };
    let selected = scene::selection(source, &transfer.ids, false)?;
    let mut owned = HashSet::new();
    for i in selected {
        owned.extend(scene::subtree(source, i));
    }
    let mut members = owned.clone();
    loop {
        let before = members.len();
        crate::instances::include_sources(source, &mut members)?;
        for i in members.clone() {
            members.extend(scene::ancestors(source, i)?);
            let item = &source.items[i];
            let adjustment_base = match &item.content {
                Content::Adjustment { adjustment } => adjustment.clip_to.as_ref(),
                _ => None,
            };
            for base in item.clip_to.iter().chain(adjustment_base) {
                members.extend(scene::subtree(source, scene::index(source, base)?));
            }
        }
        if before == members.len() {
            break;
        }
    }
    if destination.items.len() + members.len() > destination.resource_profile.items() {
        return Err(limit("Transferred hierarchy exceeds document item limit"));
    }
    let copies: Vec<_> = source
        .items
        .iter()
        .enumerate()
        .filter(|(i, _)| members.contains(i))
        .collect();
    let ids = mapping(
        &transfer.prefix,
        copies.iter().map(|(_, item)| item.id.as_str()),
        destination.items.iter().map(|item| item.id.as_str()),
    )?;
    let mut images = BTreeSet::new();
    let mut fonts = BTreeSet::new();
    for (_, item) in &copies {
        resource_ids(&item.content, &mut images, &mut fonts);
    }
    let stories: BTreeSet<_> = source
        .stories
        .keys()
        .filter(|id| {
            copies
                .iter()
                .any(|(_, i)| crate::text::flow::uses(&i.content, id))
        })
        .cloned()
        .collect();
    for id in &stories {
        fonts.extend(
            source.stories[id]
                .styles()
                .flat_map(crate::text::Style::font_ids)
                .cloned(),
        );
    }
    let story_ids = mapping(
        &transfer.prefix,
        stories.iter().map(String::as_str),
        destination.stories.keys().map(String::as_str),
    )?;
    let image_ids = mapping(
        &transfer.prefix,
        images.iter().map(String::as_str),
        destination.assets.keys().map(String::as_str),
    )?;
    let font_ids = mapping(
        &transfer.prefix,
        fonts.iter().map(String::as_str),
        destination.fonts.keys().map(String::as_str),
    )?;
    let mut swatches = BTreeSet::new();
    for (_, item) in &copies {
        swatches.extend(crate::swatches::references(source, item)?);
    }
    let swatches = crate::swatches::closure(&source.swatches, &swatches)?;
    let swatch_ids = mapping(
        &transfer.prefix,
        swatches.iter().map(String::as_str),
        destination.swatches.keys().map(String::as_str),
    )?;
    // Verify explicit destination bindings without publishing or moving any bytes.
    if transfer.verify_resources {
        for (_, item) in &copies {
            crate::objects::verify_content_resources(
                &item.content,
                asset_root,
                font_root,
                control,
            )?;
        }
        for id in &images {
            crate::assets::load(&source.assets[id], asset_root)
                .map_err(|e| e.at_asset(&image_ids[id]))?;
        }
        for id in &fonts {
            crate::fonts::load(&source.fonts[id], font_root)
                .map_err(|e| e.at_font(&font_ids[id]))?;
        }
    }
    let mut pinned_lighting = Vec::new();
    for (_, original) in &copies {
        let mut item = (*original).clone();
        item.id = ids[&original.id].clone();
        if let Some(parent) = &mut item.parent {
            *parent = ids[parent].clone();
        } else if !matches!(
            item.content,
            Content::MaskSource {} | Content::ComponentSource {}
        ) {
            item.parent = transfer.parent.clone();
            item.transform = geometry::multiply(parent_inverse, item.transform);
        }
        if let Some(base) = &mut item.clip_to {
            *base = ids[base].clone();
        }
        if let Some(mask) = &mut item.artwork_mask {
            mask.source = ids[&mask.source].clone();
        }
        for (pass_id, effect_id) in
            crate::appearance::pin_lighting(&mut item, source.global_light.azimuth)
        {
            pinned_lighting.push(
                serde_json::json!({"item_id":item.id,"pass_id":pass_id,"effect_id":effect_id}),
            );
        }
        for effect in &mut item.effects {
            if let crate::effects::Operator::LitShadow { azimuth, .. } = &mut effect.operator
                && azimuth.is_none()
            {
                *azimuth = Some(source.global_light.azimuth);
                pinned_lighting.push(serde_json::json!({"item_id":item.id,"effect_id":effect.id}));
            }
        }
        remap_content(&mut item.content, &ids, &image_ids, &font_ids, &story_ids);
        crate::swatches::remap(&mut item, &swatch_ids)?;
        destination.items.push(item);
    }
    for (old, new) in &image_ids {
        destination
            .assets
            .insert(new.clone(), source.assets[old].clone());
    }
    for (old, new) in &font_ids {
        destination
            .fonts
            .insert(new.clone(), source.fonts[old].clone());
    }
    for (old, new) in &story_ids {
        let mut story = source.stories[old].clone();
        crate::swatches::remap_story(&mut story, &swatch_ids);
        for style in story.styles_mut() {
            style.font_variations = std::mem::take(&mut style.font_variations)
                .into_iter()
                .map(|(id, values)| (font_ids[&id].clone(), values))
                .collect();
            style.font_id = font_ids[&style.font_id].clone();
            for id in &mut style.fallback_fonts {
                *id = font_ids[id].clone();
            }
        }
        destination.stories.insert(new.clone(), story);
    }
    for (old, new) in &swatch_ids {
        let mut swatch = source.swatches[old].clone();
        if let crate::swatches::Definition::Tint { base, .. } = &mut swatch.definition {
            *base = swatch_ids[base].clone();
        }
        destination.swatches.insert(new.clone(), swatch);
    }
    let added_context: Vec<_> = copies
        .iter()
        .filter(|(i, _)| !owned.contains(i))
        .map(|(_, item)| item.id.clone())
        .collect();
    let source_value =
        serde_json::to_value(source).map_err(|e| Error::new("SERIALIZATION", e.to_string()))?;
    let source_bytes = serde_json::to_vec(&source_value)
        .map_err(|e| Error::new("SERIALIZATION", e.to_string()))?;
    Ok(serde_json::json!({
        "source_document_id":source.id,"source_revision":source.revision,"source_snapshot_sha256":crate::assets::sha256(&source_bytes),
        "item_ids":ids,"asset_ids":image_ids,"font_ids":font_ids,"swatch_ids":swatch_ids,"story_ids":story_ids,"selected_ids":transfer.ids,"included_context_ids":added_context,
        "source_preserved":true,"resources_verified":transfer.verify_resources,"resource_storage":"descriptors_retained_external_bytes_unchanged",
        "pinned_lighting":pinned_lighting,"source_variant":source.variants.as_ref().and_then(|v|v.selected.as_ref()),
        "context":"Selected subtrees with ancestor containers and transitive references. Source-selected values are copied; dataset definitions, canvas, selection, channels and resolution stay with their source. Destination viewport, backdrop and parent appearance govern compositing. Root world placement and source light directions are preserved."
    }))
}
