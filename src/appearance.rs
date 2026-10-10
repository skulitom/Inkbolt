//! Retained ordered paint passes over one original vector source.
use crate::{Error, geometry, model::*, scene};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::HashSet;

pub const MAX_PASSES: usize = 16;
fn one() -> f64 {
    1.0
}
fn yes() -> bool {
    true
}
fn tolerance() -> f64 {
    0.01
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Pass {
    pub id: String,
    pub fill: Option<Paint>,
    pub stroke: Option<Box<Stroke>>,
    #[serde(default = "yes")]
    pub enabled: bool,
    #[serde(default = "one")]
    pub opacity: f64,
    #[serde(default)]
    pub blend: BlendMode,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub maps: Vec<crate::warps::Map>,
    #[serde(default = "tolerance")]
    pub tolerance: f64,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub filters: Vec<crate::filters::Filter>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub effects: Vec<crate::effects::Effect>,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Spec {
    pub geometry: Geometry,
    #[serde(default)]
    pub fill_rule: FillRule,
    pub passes: Vec<Pass>,
}
fn invalid(message: &str) -> Error {
    Error::new("INVALID_APPEARANCE", message)
}
fn warp(s: &Spec, p: &Pass) -> crate::warps::Spec {
    crate::warps::Spec {
        geometry: s.geometry.clone(),
        fill: p.fill.clone(),
        stroke: p.stroke.clone(),
        fill_rule: s.fill_rule,
        maps: p.maps.clone(),
        tolerance: p.tolerance,
    }
}
pub(crate) fn stored(s: &Spec) -> Result<usize, Error> {
    if s.passes.is_empty() || s.passes.len() > MAX_PASSES {
        return Err(limit("Appearance requires 1..16 ordered paint passes"));
    }
    let mut ids = HashSet::new();
    let mut commands = geometry::validate_geometry(&s.geometry)?;
    for p in &s.passes {
        if !valid_id(&p.id) || !ids.insert(&p.id) {
            return Err(invalid("Appearance pass IDs must be portable and unique"));
        }
        if p.fill.is_none() && p.stroke.is_none() {
            return Err(invalid("Each appearance pass requires a fill or stroke"));
        }
        if !p.tolerance.is_finite() || !(0.000001..=1.0).contains(&p.tolerance) {
            return Err(invalid(
                "Appearance vector tolerance must be in 0.000001..=1",
            ));
        }
        if p.filters
            .iter()
            .filter_map(|f| f.mask.as_ref())
            .any(|m| !m.linked)
        {
            return Err(Error::new(
                "UNSUPPORTED",
                "Appearance pass filter masks require local linking",
            ));
        }
        if !p.maps.is_empty() {
            commands += crate::warps::stored(&warp(s, p))?;
        } else if let Some(stroke) = &p.stroke {
            commands += crate::strokes::brush_segments(stroke)?;
        }
    }
    Ok(commands)
}
fn content(s: &Spec, p: &Pass) -> Content {
    if p.maps.is_empty() {
        Content::Vector {
            geometry: s.geometry.clone(),
            fill: p.fill.clone(),
            stroke: p.stroke.clone(),
            fill_rule: s.fill_rule,
        }
    } else {
        Content::Warp {
            warp: Box::new(warp(s, p)),
        }
    }
}
fn generated(item: &Item, used: &mut HashSet<String>) -> Result<Vec<Item>, Error> {
    let Content::Appearance { appearance: spec } = &item.content else {
        return Err(invalid("An appearance item is required"));
    };
    stored(spec)?;
    let mut out = vec![Item {
        content: Content::Group {
            isolated: true,
            role: GroupRole::Group,
            knockout: false,
        },
        ..item.clone()
    }];
    for p in &spec.passes {
        let prefix = format!(
            "ib-appearance-{}",
            &crate::assets::sha256(&serde_json::to_vec(&(&item.id, &p.id)).unwrap())[..24]
        );
        let mut id = prefix.clone();
        let mut suffix = 0;
        while !used.insert(id.clone()) {
            suffix += 1;
            id = format!("{prefix}-{suffix}");
        }
        out.push(Item {
            id,
            name: p.id.clone(),
            parent: Some(item.id.clone()),
            visible: p.enabled,
            locked: false,
            opacity: p.opacity,
            blend: p.blend,
            fill_opacity: 1.0,
            coverage: Default::default(),
            transform: identity(),
            clip_to: None,
            clip: None,
            mask: None,
            artwork_mask: None,
            hdr_grade: None,
            pixel_warp: None,
            metadata: None,
            effects: p.effects.clone(),
            filters: p.filters.clone(),
            content: content(spec, p),
        });
    }
    Ok(out)
}
pub(crate) fn evaluate(d: &Document) -> Result<Option<Document>, Error> {
    if !d
        .items
        .iter()
        .any(|i| matches!(i.content, Content::Appearance { .. }))
    {
        return Ok(None);
    }
    let mut used = d.items.iter().map(|i| i.id.clone()).collect();
    let mut items = Vec::new();
    for item in &d.items {
        if matches!(item.content, Content::Appearance { .. }) {
            items.extend(generated(item, &mut used)?);
        } else {
            items.push(item.clone());
        }
        if items.len() > d.resource_profile.items() {
            return Err(limit(
                "Evaluated appearance exceeds the document resource-profile item budget",
            ));
        }
    }
    let mut copy = d.clone();
    copy.items = items;
    copy.variants = None;
    Ok(Some(copy))
}
pub(crate) fn validate(d: &Document, control: &crate::control::Control) -> Result<(), Error> {
    if let Some(copy) = evaluate(d)? {
        crate::model::validate_controlled(&copy, control)?;
    }
    Ok(())
}
pub(crate) fn bounds(spec: &Spec, matrix: Matrix) -> Result<geometry::Bounds, Error> {
    bounds_controlled(spec, matrix, &crate::control::Control::default())
}
fn bounds_controlled(
    spec: &Spec,
    matrix: Matrix,
    control: &crate::control::Control,
) -> Result<geometry::Bounds, Error> {
    control.check()?;
    stored(spec)?;
    spec.passes
        .iter()
        .map(|p| {
            let g = if p.maps.is_empty() {
                spec.geometry.clone()
            } else {
                crate::warps::plan_controlled(&warp(spec, p), control)?.geometry
            };
            Ok(geometry::bounds(&g, matrix))
        })
        .collect::<Result<Vec<_>, Error>>()?
        .into_iter()
        .reduce(scene::union)
        .ok_or_else(|| invalid("No appearance bounds"))
}
pub(crate) fn expand(
    d: &mut Document,
    index: usize,
    control: &crate::control::Control,
) -> Result<Value, Error> {
    let mut used = d.items.iter().map(|i| i.id.clone()).collect();
    let mut items = generated(&d.items[index], &mut used)?;
    for item in &mut items {
        if let Content::Warp { warp } = &item.content {
            item.content = crate::warps::content_controlled(warp, control)?;
        }
    }
    let ids: Vec<_> = items.iter().skip(1).map(|i| i.id.clone()).collect();
    d.items.splice(index..=index, items);
    Ok(
        json!({"created":ids,"source_retained_in_input":true,"losses":["Paint passes become independent editable objects; shared geometry and live vector maps are expanded. Ordered raster filters and decorations remain editable."]}),
    )
}
pub fn inspect(d: &Document, id: &str) -> Result<Value, Error> {
    inspect_controlled(d, id, &crate::control::Control::default())
}
pub fn inspect_controlled(
    d: &Document,
    id: &str,
    control: &crate::control::Control,
) -> Result<Value, Error> {
    crate::model::validate_controlled(d, control)?;
    let i = scene::index(d, id)?;
    let Content::Appearance { appearance: spec } = &d.items[i].content else {
        return Err(invalid("Appearance inspection requires an appearance item"));
    };
    Ok(
        json!({"id":id,"source":spec.geometry,"fill_rule":spec.fill_rule,"passes":spec.passes,"order":"bottom_to_top","pipeline":"ordered_geometry_maps_then_fill_and_stroke_then_ordered_raster_filters_then_decorations;outer_item_controls_apply_to_isolated_stack","bounds":bounds_controlled(spec,scene::world_transform(d,i)?,control)?,"bounds_semantics":"geometry_including_disabled_passes;excludes_strokes_and_raster_effects","source_preserved":true}),
    )
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Bake {
    pub origin: Point,
    pub width: u32,
    pub height: u32,
    pub scale: u32,
}
pub(crate) fn bake(
    d: &mut Document,
    index: usize,
    asset_id: &str,
    image_id: &str,
    region: Bake,
    control: &crate::control::Control,
) -> Result<Value, Error> {
    let Content::Appearance { appearance: spec } = &d.items[index].content else {
        return Err(invalid("Baking requires an appearance item"));
    };
    if !valid_id(asset_id)
        || !valid_id(image_id)
        || d.assets.contains_key(asset_id)
        || d.items.iter().any(|i| i.id == image_id)
    {
        return Err(invalid(
            "Baked asset and image IDs must be new portable IDs",
        ));
    }
    if d.color_space != ColorSpace::Srgb {
        return Err(Error::new(
            "UNSUPPORTED",
            "Appearance baking currently requires encoded-sRGB working space",
        ));
    }
    if !(1..=4).contains(&region.scale)
        || region.width == 0
        || region.height == 0
        || region.width > MAX_DIMENSION
        || region.height > MAX_DIMENSION
        || region.width as u64 * region.height as u64 * (region.scale as u64).pow(2)
            > MAX_STORED_PIXELS as u64
    {
        return Err(limit(
            "Appearance baking requires scale 1..4 and at most 65536 embedded pixels",
        ));
    }
    geometry::validate_geometry(&Geometry::Rect {
        x: region.origin[0],
        y: region.origin[1],
        width: region.width as f64,
        height: region.height as f64,
    })?;
    let world = scene::world_transform(d, index)?;
    let window = [1.0, 0.0, 0.0, 1.0, -region.origin[0], -region.origin[1]];
    let capture = geometry::multiply(window, world);
    let placement = geometry::relative_transform(
        world,
        &[[1.0, 0.0, 0.0, 1.0, region.origin[0], region.origin[1]]],
    )?;
    let mut source = d.clone();
    source.vector_canvas = None;
    source.width = region.width;
    source.height = region.height;
    source.variants = None;
    source.background = None;
    source.selection = None;
    source.channels.clear();
    source.stories.clear();
    source.fonts.clear();
    source.assets.clear();
    source.output_profile = None;
    source.items=vec![serde_json::from_value(json!({"id":"bake-source","transform":capture,"content":{"type":"appearance","appearance":spec}})).map_err(|_|invalid("Unable to construct appearance source"))?];
    control.check()?;
    let rendered = crate::render::rasterize(&source, region.scale)?;
    control.check()?;
    let digest = crate::assets::identity(rendered.width, rendered.height, &rendered.rgba);
    let asset = crate::assets::ImageAsset {
        width: rendered.width,
        height: rendered.height,
        sha256: digest.clone(),
        storage: crate::assets::Storage::Embedded {
            rgba_hex: crate::render::hex(&rendered.rgba),
        },
        provenance: None,
    };
    let child:Item=serde_json::from_value(json!({"id":image_id,"name":"Baked appearance","parent":d.items[index].id,"transform":placement,"content":{"type":"image","asset_id":asset_id,"width":region.width,"height":region.height,"sampling":"nearest"}})).map_err(|_|invalid("Unable to construct baked placement"))?;
    d.assets.insert(asset_id.into(), asset);
    d.items[index].content = Content::Group {
        isolated: true,
        role: GroupRole::Group,
        knockout: false,
    };
    d.items.insert(index + 1, child);
    Ok(
        json!({"asset_id":asset_id,"image_id":image_id,"sha256":digest,"bounds":region,"source_retained_in_input":true,"losses":["The explicit document-space evaluation viewport is baked to RGBA8 at the declared scale; content outside it is cropped. Paint identities, pass order and live geometry/raster effects become pixels. Viewport-filter boundaries are reevaluated for this region; use the full document canvas to preserve its boundary behavior. Outer item controls remain editable. Keep the original snapshot or undo history."]}),
    )
}
pub(crate) fn has_effects(item: &Item) -> bool {
    matches!(&item.content,Content::Appearance{appearance} if appearance.passes.iter().any(|p|!p.filters.is_empty()||!p.effects.is_empty()))
}
pub(crate) fn pin_lighting(item: &mut Item, azimuth: f64) -> Vec<(String, String)> {
    let mut pinned = vec![];
    if let Content::Appearance { appearance } = &mut item.content {
        for p in &mut appearance.passes {
            for e in &mut p.effects {
                if let crate::effects::Operator::LitShadow { azimuth: a, .. } = &mut e.operator
                    && a.is_none()
                {
                    *a = Some(azimuth);
                    pinned.push((p.id.clone(), e.id.clone()));
                }
            }
        }
    }
    pinned
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn nonfinite_library_passes_and_maps_fail_explicitly() {
        let original:Document=serde_json::from_value(json!({"schema_version":2,"id":"finite","kind":"vector","width":16,"height":16,"color_space":"srgb","items":[{"id":"p","content":{"type":"appearance","appearance":{"geometry":{"shape":"rect","x":1,"y":1,"width":4,"height":4},"passes":[{"id":"fill","fill":[0,0,0,255]}]}}}]})).unwrap();
        for n in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            let mut d = original.clone();
            let Content::Appearance { appearance } = &mut d.items[0].content else {
                unreachable!()
            };
            appearance.passes[0].opacity = n;
            assert!(crate::validate(&d).is_err());
            let mut d = original.clone();
            let Content::Appearance { appearance } = &mut d.items[0].content else {
                unreachable!()
            };
            appearance.passes[0].maps = vec![crate::warps::Map::Affine {
                matrix: [1.0, 0.0, 0.0, 1.0, n, 0.0],
            }];
            assert!(crate::validate(&d).is_err());
        }
    }
}
