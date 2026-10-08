//! Editable, nonprinting artwork sources reused as alpha or luminance masks.
use crate::{Error, geometry, model::*, scene};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use std::collections::HashSet;

pub const MAX_MASKS: usize = 32;
pub const MAX_COVERAGE_PIXELS: u64 = 1_048_576;
pub const MAX_SVG_ITEMS: usize = 4096;
fn yes() -> bool {
    true
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Mode {
    #[default]
    Alpha,
    Luminance,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Mask {
    pub source: String,
    /// x, y, width, height in region coordinates. Zero extent hides everything.
    pub region: [f64; 4],
    #[serde(default = "yes")]
    pub clip_region: bool,
    #[serde(default)]
    pub mode: Mode,
    #[serde(default = "identity")]
    pub transform: Matrix,
    #[serde(default = "identity")]
    pub region_transform: Matrix,
    #[serde(default = "yes")]
    pub linked: bool,
    #[serde(default = "yes")]
    pub enabled: bool,
}
impl Mask {
    pub fn world_transform(&self, owner: Matrix) -> Matrix {
        if self.linked {
            geometry::multiply(owner, self.transform)
        } else {
            self.transform
        }
    }
    pub fn region_geometry(&self) -> Option<Geometry> {
        let [x, y, width, height] = self.region;
        (width > 0.0 && height > 0.0).then_some(Geometry::Rect {
            x,
            y,
            width,
            height,
        })
    }
    pub fn scalar(&self, premultiplied: &[f64; 4]) -> f64 {
        match self.mode {
            Mode::Alpha => premultiplied[3],
            // Linear combination commutes with premultiplication. Encoded sRGB.
            Mode::Luminance => {
                premultiplied[0] * 0.2125 + premultiplied[1] * 0.7154 + premultiplied[2] * 0.0721
            }
        }
        .clamp(0.0, 1.0)
    }
}
pub(crate) fn source_owner(document: &Document, index: usize) -> Result<Option<usize>, Error> {
    Ok(std::iter::once(index)
        .chain(scene::ancestors(document, index)?)
        .find(|&i| matches!(document.items[i].content, Content::MaskSource {})))
}
pub(crate) fn validate(document: &Document) -> Result<(), Error> {
    if document
        .items
        .iter()
        .filter(|i| i.artwork_mask.is_some())
        .count()
        > MAX_MASKS
    {
        return Err(limit("Document exceeds 32 artwork-mask references"));
    }
    for (i, item) in document.items.iter().enumerate() {
        if let Some(source) = source_owner(document, i)? {
            if document.items[source].parent.is_some() {
                return Err(invalid("Mask sources must be top-level resources"));
            }
            if !matches!(
                item.content,
                Content::MaskSource {}
                    | Content::Instance { .. }
                    | Content::Appearance { .. }
                    | Content::Volume { .. }
                    | Content::Interpolation { .. }
                    | Content::Repeat { .. }
                    | Content::Warp { .. }
                    | Content::Vector { .. }
                    | Content::Text { .. }
                    | Content::StoryFrame { .. }
                    | Content::Group { isolated: true, .. }
            ) || item.content.is_knockout()
                || item.artwork_mask.is_some()
                || item.mask.is_some()
                || item.clip_to.is_some()
                || !item.filters.is_empty()
                || item.blend != BlendMode::Normal
            {
                return Err(Error::new("UNSUPPORTED", "Mask sources support vector shapes, text, isolated groups and geometric clips; nested opacity masks, pixel content, filters, knockout and non-normal blending are not yet supported").at_item(&item.id));
            }
        }
        if let Some(mask) = &item.artwork_mask {
            if item.mask.is_some() {
                return Err(Error::new(
                    "UNSUPPORTED",
                    "An item cannot currently combine grid and artwork opacity masks",
                )
                .at_item(&item.id));
            }
            if !valid_id(&mask.source)
                || scene::index(document, &mask.source).is_err()
                || !matches!(
                    document.items[scene::index(document, &mask.source)?].content,
                    Content::MaskSource {}
                )
            {
                return Err(
                    invalid("Artwork mask requires an existing mask_source ID").at_item(&item.id)
                );
            }
            let [x, y, w, h] = mask.region;
            if mask
                .region
                .iter()
                .any(|v| !v.is_finite() || v.abs() > MAX_COORDINATE)
                || w < 0.0
                || h < 0.0
            {
                return Err(invalid(
                    "Artwork-mask region requires finite x/y and nonnegative extents within coordinate limits",
                ));
            }
            geometry::validate_matrix(mask.transform)?;
            geometry::validate_matrix(mask.region_transform)?;
            let world = mask.world_transform(scene::world_transform(document, i)?);
            geometry::validate_matrix(world)?;
            let region_world = geometry::multiply(world, mask.region_transform);
            geometry::validate_matrix(region_world)?;
            if let Some(region) = mask.region_geometry() {
                validate_world_geometry(&region, region_world)?;
            } else {
                let point = geometry::map(region_world, [x, y]);
                if point
                    .iter()
                    .any(|v| !v.is_finite() || v.abs() > MAX_COORDINATE)
                {
                    return Err(invalid(
                        "Empty artwork-mask region origin exceeds world bounds",
                    ));
                }
            }
        }
    }
    Ok(())
}
pub(crate) fn check_dependents_unlocked(document: &Document, index: usize) -> Result<(), Error> {
    if let Some(source) = source_owner(document, index)? {
        let id = &document.items[source].id;
        for (i, item) in document.items.iter().enumerate() {
            if item.artwork_mask.as_ref().is_some_and(|m| &m.source == id)
                && (scene::effective_locked(document, i)?
                    || scene::subtree(document, i)
                        .iter()
                        .any(|&j| document.items[j].locked))
            {
                return Err(Error::new(
                    "LOCKED",
                    "Mask artwork affects a locked referencing item or descendant",
                ));
            }
        }
    }
    Ok(())
}
/// Materialize only a referenced source, preserving stable IDs and local edits.
pub(crate) fn instance(
    document: &Document,
    mask: &Mask,
    owner_world: Matrix,
) -> Result<Document, Error> {
    let source = scene::index(document, &mask.source)?;
    let members: HashSet<_> = scene::subtree(document, source).into_iter().collect();
    let mut instance = document.clone();
    instance.background = None;
    instance.variants = None;
    instance.kind = DocumentKind::Vector;
    instance.vector_canvas = None;
    // Mask artwork always uses the declared encoded scalar contract, including
    // when its owner composites signed linear samples.
    instance.color_space = ColorSpace::Srgb;
    instance.selection = None;
    instance.channels.clear();
    instance.assets.clear();
    instance.items = document
        .items
        .iter()
        .enumerate()
        .filter(|(i, _)| members.contains(i))
        .map(|(_, i)| i.clone())
        .collect();
    let index = scene::index(&instance, &mask.source)?;
    instance.items[index].content = Content::Group {
        isolated: true,
        role: GroupRole::Group,
        knockout: false,
    };
    instance.items[index].transform = geometry::multiply(
        mask.world_transform(owner_world),
        instance.items[index].transform,
    );
    Ok(instance)
}
/// Fingerprint transitive source artwork, including component and font dependencies.
pub(crate) fn dependency_hash(document: &Document, index: usize) -> Result<Option<String>, Error> {
    let Some(mask) = &document.items[index].artwork_mask else {
        return Ok(None);
    };
    let source = scene::index(document, &mask.source)?;
    let mut members: HashSet<_> = scene::subtree(document, source).into_iter().collect();
    crate::instances::include_sources(document, &mut members)?;
    let mut members: Vec<_> = members.into_iter().collect();
    members.sort_unstable();
    let bytes = serde_json::to_vec(&(
        members
            .into_iter()
            .map(|i| &document.items[i])
            .collect::<Vec<_>>(),
        &document.fonts,
    ))
    .unwrap();
    Ok(Some(crate::assets::sha256(&bytes)))
}

/// Board extraction retains shared nonprinting definitions needed by owned items.
pub(crate) fn include_sources(
    document: &Document,
    members: &mut HashSet<usize>,
) -> Result<(), Error> {
    crate::instances::include_sources(document, members)?;
    let roots = members
        .iter()
        .filter_map(|&i| {
            document.items[i]
                .artwork_mask
                .as_ref()
                .map(|m| m.source.as_str())
        })
        .collect::<Vec<_>>();
    for id in roots {
        members.extend(scene::subtree(document, scene::index(document, id)?));
    }
    Ok(())
}
