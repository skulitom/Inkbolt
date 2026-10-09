//! Stable-ID document comparisons, with optional independently inspectable pixel deltas.
use crate::{
    Document, Error,
    control::Control,
    model::{Content, Item},
    sessions::Resources,
};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};

fn hash<T: serde::Serialize>(value: &T) -> String {
    crate::assets::sha256(&serde_json::to_vec(value).expect("validated model serializes"))
}
fn summary(document: &Document, index: usize) -> Result<Value, Error> {
    let item = &document.items[index];
    Ok(
        json!({"sha256":hash(item),"parent":item.parent,"sibling_index":crate::scene::children(document,item.parent.as_deref()).iter().position(|i|*i==index).unwrap(),"world_transform":crate::scene::world_transform(document,index)?,"mask_world_transform":item.mask.as_ref().map(|m| crate::scene::world_transform(document,index).map(|w| m.world_transform(w))).transpose()?,"artwork_mask_world_transform":item.artwork_mask.as_ref().map(|m| crate::scene::world_transform(document,index).map(|w|m.world_transform(w))).transpose()?,"artwork_mask_source_sha256":crate::artwork_masks::dependency_hash(document,index)?,"component_source_sha256":crate::instances::dependency_hash(document,index)?,"story_source_sha256":crate::text::flow::dependency_hash(document,index)?,"swatch_source_sha256":crate::swatches::dependency_hash(document,index)?,"geometry_bounds":crate::scene::bounds(document,index)?,"effective_visible":crate::scene::effective_visible(document,index)?,"effective_locked":crate::scene::effective_locked(document,index)?}),
    )
}
fn fields(a: &Item, b: &Item) -> Vec<String> {
    let a = serde_json::to_value(a).unwrap();
    let b = serde_json::to_value(b).unwrap();
    let mut result = Vec::new();
    for key in [
        "hdr_grade",
        "metadata",
        "name",
        "visible",
        "locked",
        "opacity",
        "fill_opacity",
        "coverage",
        "effects",
        "blend",
        "transform",
        "parent",
        "clip_to",
        "clip",
        "mask",
        "artwork_mask",
        "filters",
    ] {
        if a[key] != b[key] {
            result.push(key.to_owned());
        }
    }
    if a["content"]["type"] != b["content"]["type"] {
        result.push("content".to_owned());
    } else {
        let keys: BTreeSet<_> = a["content"]
            .as_object()
            .unwrap()
            .keys()
            .chain(b["content"].as_object().unwrap().keys())
            .collect();
        for key in keys {
            if a["content"][key] != b["content"][key] {
                result.push(format!("content.{key}"));
            }
        }
    }
    result
}
fn pixel_delta(a: &[u8], b: &[u8], width: u32, height: u32) -> Value {
    let mut count = 0;
    let mut bounds = [width, height, 0, 0];
    let mut max_delta = 0;
    for (n, (old, new)) in a
        .as_chunks::<4>()
        .0
        .iter()
        .zip(b.as_chunks::<4>().0)
        .enumerate()
    {
        if old == new {
            continue;
        }
        count += 1;
        let x = n as u32 % width;
        let y = n as u32 / width;
        bounds = [
            bounds[0].min(x),
            bounds[1].min(y),
            bounds[2].max(x + 1),
            bounds[3].max(y + 1),
        ];
        for (x, y) in old.iter().zip(new) {
            max_delta = max_delta.max(x.abs_diff(*y));
        }
    }
    json!({"changed_pixels":count,"bounds":if count>0{Some(bounds)}else{None},"maximum_channel_delta":max_delta})
}
fn raster_delta(a: &Item, b: &Item) -> Option<Value> {
    if let (
        Content::Raster {
            width: aw,
            height: ah,
            rgba_hex: a,
            ..
        },
        Content::Raster {
            width: bw,
            height: bh,
            rgba_hex: b,
            ..
        },
    ) = (&a.content, &b.content)
    {
        if (aw, ah) == (bw, bh) {
            Some(pixel_delta(
                &crate::render::unhex(a),
                &crate::render::unhex(b),
                *aw,
                *ah,
            ))
        } else {
            Some(json!({"resized":true,"before_dimensions":[aw,ah],"after_dimensions":[bw,bh]}))
        }
    } else {
        None
    }
}
pub fn compare(
    before: &Document,
    after: &Document,
    before_resources: &Resources,
    after_resources: &Resources,
    compare_pixels: bool,
    control: &Control,
) -> Result<Value, Error> {
    control.check()?;
    before_resources.validate()?;
    after_resources.validate()?;
    if compare_pixels {
        control.check_resource_paths(before_resources)?;
        control.check_resource_paths(after_resources)?;
    }
    crate::model::validate_controlled(before, control)?;
    crate::model::validate_controlled(after, control)?;
    if before.id != after.id || before.kind != after.kind {
        return Err(Error::new(
            "INVALID_REQUEST",
            "Document diff requires the same document ID and kind",
        ));
    }
    let old: BTreeMap<_, _> = before
        .items
        .iter()
        .enumerate()
        .map(|(i, v)| (v.id.as_str(), i))
        .collect();
    let new: BTreeMap<_, _> = after
        .items
        .iter()
        .enumerate()
        .map(|(i, v)| (v.id.as_str(), i))
        .collect();
    let ids: BTreeSet<_> = old.keys().chain(new.keys()).copied().collect();
    let mut items = Vec::new();
    for id in ids {
        control.check()?;
        let a = old.get(id).copied();
        let b = new.get(id).copied();
        let av = a.map(|i| summary(before, i)).transpose()?;
        let bv = b.map(|i| summary(after, i)).transpose()?;
        let (kind, changed, pixels) = match (a, b) {
            (None, Some(_)) => ("added", Vec::new(), None),
            (Some(_), None) => ("removed", Vec::new(), None),
            (Some(a), Some(b)) => {
                if before.items[a] == after.items[b] && av == bv {
                    continue;
                }
                let mut changed = fields(&before.items[a], &after.items[b]);
                for key in [
                    "sibling_index",
                    "world_transform",
                    "mask_world_transform",
                    "artwork_mask_world_transform",
                    "artwork_mask_source_sha256",
                    "component_source_sha256",
                    "swatch_source_sha256",
                    "story_source_sha256",
                    "geometry_bounds",
                    "effective_visible",
                    "effective_locked",
                ] {
                    if av.as_ref().unwrap()[key] != bv.as_ref().unwrap()[key] {
                        changed.push(format!("derived.{key}"));
                    }
                }
                (
                    "changed",
                    changed,
                    raster_delta(&before.items[a], &after.items[b]),
                )
            }
            _ => unreachable!(),
        };
        items.push(json!({"id":id,"change":kind,"fields":changed,"before":av,"after":bv,"stored_pixels":pixels}));
    }
    let mut metadata = Vec::new();
    let a = serde_json::to_value(before).unwrap();
    let b = serde_json::to_value(after).unwrap();
    for key in [
        "background",
        "schema_version",
        "vector_canvas",
        "width",
        "height",
        "resolution_ppi",
        "resource_profile",
        "global_light",
        "color_space",
        "metadata",
        "output_profile",
        "variants",
    ] {
        if a[key] != b[key] {
            metadata.push(json!({"field":key,"before":a[key],"after":b[key]}));
        }
    }
    if before.selection != after.selection {
        metadata.push(json!({"field":"selection","before":crate::selections::inspect(before.selection.as_ref()),"after":crate::selections::inspect(after.selection.as_ref())}));
    }
    if before.channels != after.channels {
        metadata.push(json!({"field":"channels","before":crate::channels::inspect(before),"after":crate::channels::inspect(after)}));
    }
    if before.ink_recipe != after.ink_recipe {
        metadata.push(
            json!({"field":"ink_recipe","before":before.ink_recipe,"after":after.ink_recipe}),
        );
    }
    let mut resources = Vec::new();
    for kind in ["assets", "fonts", "swatches", "stories"] {
        let empty = serde_json::Map::new();
        let a = a[kind].as_object().unwrap_or(&empty);
        let b = b[kind].as_object().unwrap_or(&empty);
        let ids: BTreeSet<_> = a.keys().chain(b.keys()).collect();
        for id in ids {
            if a.get(id) != b.get(id) {
                resources.push(json!({"kind":kind,"id":id,"before_sha256":a.get(id).map(hash),"after_sha256":b.get(id).map(hash)}));
            }
        }
    }
    let bindings_changed = before_resources != after_resources;
    let pixels = if compare_pixels {
        if (before.width, before.height) != (after.width, after.height) {
            return Err(Error::new(
                "UNSUPPORTED",
                "Rendered pixel comparison requires equal canvas dimensions; structural diff remains available",
            ));
        }
        let a = crate::render::rasterize_controlled(
            before,
            1,
            before_resources.asset_root.as_deref(),
            before_resources.font_root.as_deref(),
            None,
            control,
        )?;
        control.check()?;
        let b = crate::render::rasterize_controlled(
            after,
            1,
            after_resources.asset_root.as_deref(),
            after_resources.font_root.as_deref(),
            None,
            control,
        )?;
        control.check()?;
        Some(pixel_delta(&a.rgba, &b.rgba, a.width, a.height))
    } else {
        None
    };
    control.check()?;
    Ok(
        json!({"document_id":before.id,"from_revision":before.revision,"to_revision":after.revision,"before_sha256":hash(before),"after_sha256":hash(after),"changed":!metadata.is_empty()||!items.is_empty()||!resources.is_empty()||bindings_changed,"metadata":metadata,"items":items,"resources":resources,"resource_bindings_changed":bindings_changed,"rendered_pixels":pixels,"semantics":"Revision alone is not a content change. Bounds are unclipped geometry; pixel bounds are end-exclusive at scale 1. Rendered pixels compare working-sRGB RGBA8 array positions before output-profile conversion; origins are not world-aligned. Use document.diff.preview for explicit world-grid alignment and images. Derived changes include ancestor effects. This is a comparison, not an executable patch."}),
    )
}
