//! Reversible opaque raster backgrounds over retained editable source layers.
use crate::{Error, model::*, scene};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Background {
    pub item_id: String,
    pub matte: [u8; 3],
    /// Fixed opaque pixel source, in canvas coordinates [x, y, width, height].
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub fixed_pixel_bounds: Option<[i32; 4]>,
    /// A fixed pixel surface retains the file's fill byte without fading paint.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub inactive_fill_byte: Option<u8>,
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Action {
    Promote {
        matte: [u8; 3],
    },
    /// Recover the retained source, including its original alpha and appearance controls.
    RestoreSource {},
    /// Keep the opaque appearance as an ordinary editable layer with two children.
    ToLayer {
        source_id: String,
        matte_id: String,
    },
}

pub(crate) fn printable(item: &Item) -> bool {
    !matches!(
        item.content,
        Content::WorkPath { .. } | Content::MaskSource {} | Content::ComponentSource { .. }
    )
}
fn eligible(item: &Item) -> bool {
    matches!(
        item.content,
        Content::Object { .. }
            | Content::Samples { .. }
            | Content::StoredSamples { .. }
            | Content::Raw { .. }
            | Content::Raster { .. }
            | Content::Image { .. }
            | Content::Fill { .. }
            | Content::Text { .. }
            | Content::StoryFrame { .. }
            | Content::Group { isolated: true, .. }
            | Content::Frame { .. }
    )
}
pub(crate) fn matte(document: &Document, id: &str) -> Option<[u8; 3]> {
    document
        .background
        .as_ref()
        .filter(|b| b.item_id == id)
        .map(|b| b.matte)
}
pub(crate) fn visible_matte(document: &Document) -> Option<[u8; 3]> {
    let background = document.background.as_ref()?;
    let item = &document.items[scene::index(document, &background.item_id).ok()?];
    item.visible.then_some(background.matte)
}

fn protected(item: &Item) -> Error {
    Error::new("BACKGROUND_PROTECTED", "The fixed background keeps its position, opaque RGB pixels and normal appearance. Restore it to an ordinary layer before changing these properties.").at_item(&item.id)
}

fn opaque_hex(rgba: &str) -> bool {
    rgba.as_bytes()
        .as_chunks::<8>()
        .0
        .iter()
        .all(|pixel| pixel[6..8].eq_ignore_ascii_case(b"ff"))
}

pub(crate) fn fixed_pixels(document: &Document) -> Option<&str> {
    document
        .background
        .as_ref()
        .filter(|b| b.fixed_pixel_bounds.is_some())
        .map(|b| b.item_id.as_str())
}

pub(crate) fn fixed_grid(document: &Document) -> Option<(&str, &crate::stored_samples::Grid)> {
    let id = fixed_pixels(document)?;
    let item = document.items.iter().find(|item| item.id == id)?;
    match &item.content {
        Content::StoredSamples { grid } => Some((id, grid)),
        _ => None,
    }
}

pub(crate) fn verify_opaque_blocks(
    id: &str,
    source: &crate::sample_store::Candidate,
    root: Option<&std::path::Path>,
    control: &crate::control::Control,
) -> Result<(), Error> {
    let manifest = source.manifest();
    let mut seen = std::collections::BTreeSet::new();
    for (index, digest) in manifest.tiles.iter().enumerate() {
        control.check()?;
        if seen.insert(digest) {
            let tile = source.read_region(root, manifest.spec.tile(index), control)?;
            if tile.as_chunks::<4>().0.iter().any(|p| p[3] != 255) {
                return Err(Error::new("BACKGROUND_PROTECTED","Fixed background pixels must stay opaque. Restore the source to an ordinary layer to edit alpha.").at_item(id));
            }
        }
    }
    Ok(())
}

fn validate_fixed(item: &Item, bounds: [i32; 4]) -> Result<(), Error> {
    use crate::assets::Sampling;
    use crate::samples::{Channels, Depth};
    let (width, height) = match &item.content {
        Content::Raster {
            width,
            height,
            rgba_hex,
            sampling: Sampling::Nearest,
        } if opaque_hex(rgba_hex) => (*width, *height),
        Content::Samples { grid }
            if grid.depth == Depth::U8
                && grid.channels == Channels::Rgba
                && grid.encoding == crate::hdr::Encoding::EncodedSrgb
                && grid.sampling == Sampling::Nearest
                && opaque_hex(&grid.data_hex) =>
        {
            (grid.width, grid.height)
        }
        Content::StoredSamples { grid }
            if grid.storage_version == 2
                && grid.base.spec.depth == Depth::U8
                && grid.base.spec.channels == Channels::Rgba
                && grid.base.spec.encoding == crate::hdr::Encoding::EncodedSrgb
                && grid.sampling == Sampling::Nearest =>
        {
            (grid.base.spec.width, grid.base.spec.height)
        }
        _ => return Err(protected(item)),
    };
    let [x, y, w, h] = bounds;
    if [w, h] != [width as i32, height as i32]
        || item.transform != [1., 0., 0., 1., f64::from(x), f64::from(y)]
        || item.opacity != 1.
        || item.fill_opacity != 1.
        || item.blend != BlendMode::Normal
        || item.mask.is_some()
        || item.clip.is_some()
        || item.artwork_mask.is_some()
        || !item.filters.is_empty()
        || !item.effects.is_empty()
        || item.hdr_grade.is_some()
        || item.pixel_warp.is_some()
        || !item.coverage.is_smooth()
        || !item.knockout_target.is_none()
    {
        return Err(protected(item));
    }
    Ok(())
}
pub(crate) fn validate(document: &Document) -> Result<(), Error> {
    let Some(background) = &document.background else {
        return Ok(());
    };
    if document.kind != DocumentKind::Raster {
        return Err(invalid("Background layers require a raster document"));
    }
    let i = scene::index(document, &background.item_id)
        .map_err(|_| invalid("Background item_id must refer to an existing layer"))?;
    let item = &document.items[i];
    if !eligible(item) || item.parent.is_some() || item.clip_to.is_some() {
        return Err(
            invalid("Background must be an unclipped root drawable or isolated container")
                .at_item(&item.id),
        );
    }
    let first = scene::children(document, None)
        .into_iter()
        .find(|&j| printable(&document.items[j]));
    if first != Some(i) {
        return Err(invalid("Background must remain the bottom printable root; restore or convert it before moving it above another layer").at_item(&item.id));
    }
    if let Some(bounds) = background.fixed_pixel_bounds {
        validate_fixed(item, bounds)?;
    } else if background.inactive_fill_byte.is_some() {
        return Err(
            invalid("An inactive fill byte belongs to a fixed pixel background").at_item(&item.id),
        );
    }
    Ok(())
}

pub(crate) fn apply(document: &mut Document, id: &str, action: &Action) -> Result<Value, Error> {
    if document.kind != DocumentKind::Raster {
        return Err(Error::new(
            "INVALID_OPERATION",
            "Background conversion requires a raster document",
        ));
    }
    let i = scene::index(document, id)?;
    scene::check_unlocked(document, i, true)?;
    let previous = document.background.clone();
    match action {
        Action::Promote { matte } => {
            if let Some(old) = &previous {
                scene::check_unlocked(document, scene::index(document, &old.item_id)?, true)?;
            }
            let item = &document.items[i];
            if !eligible(item) || item.parent.is_some() || item.clip_to.is_some() {
                return Err(Error::new("INVALID_OPERATION", "Promote an unclipped root drawable or isolated container; explicitly reparent or unlink clipping first").at_item(id));
            }
            let item = document.items.remove(i);
            document.items.insert(0, item);
            document.background = Some(Background {
                item_id: id.into(),
                matte: *matte,
                fixed_pixel_bounds: None,
                inactive_fill_byte: None,
            });
            Ok(
                json!({"previous":previous,"background":document.background,"source_retained":true,"placement":"bottom_printable_root","matte_coordinates":"current_canvas","alpha":"opaque_after_source_appearance_before_clipped_siblings"}),
            )
        }
        Action::RestoreSource {} => {
            if previous.as_ref().is_none_or(|b| b.item_id != id) {
                return Err(Error::new(
                    "INVALID_OPERATION",
                    "Requested layer is not the background",
                ));
            }
            document.background = None;
            Ok(
                json!({"previous":previous,"background":null,"source_retained":true,"restored":"original_source_alpha_and_controls","placement":"unchanged"}),
            )
        }
        Action::ToLayer {
            source_id,
            matte_id,
        } => {
            let Some(background) = previous.as_ref().filter(|b| b.item_id == id) else {
                return Err(Error::new(
                    "INVALID_OPERATION",
                    "Requested layer is not the background",
                ));
            };
            if source_id == matte_id
                || [source_id, matte_id]
                    .iter()
                    .any(|id| !valid_id(id) || document.items.iter().any(|item| item.id == **id))
            {
                return Err(Error::new(
                    "ID_CONFLICT",
                    "Source and matte children require distinct valid unused IDs",
                ));
            }
            let mut source = document.items[i].clone();
            source.id = source_id.clone();
            source.parent = Some(id.into());
            source.visible = true;
            // The original root identity remains the ordinary layer, so external
            // clipping references stay stable. Retained descendants follow source.
            for item in &mut document.items {
                if item.parent.as_deref() == Some(id) {
                    item.parent = Some(source_id.clone());
                }
            }
            let root = &mut document.items[i];
            root.transform = identity();
            root.opacity = 1.0;
            root.fill_opacity = 1.0;
            root.blend = BlendMode::Normal;
            root.coverage = crate::coverage::Mode::Smooth {};
            root.pixel_warp = None;
            root.clip = None;
            root.mask = None;
            root.artwork_mask = None;
            root.filters.clear();
            root.effects.clear();
            root.content = Content::Group {
                isolated: true,
                role: GroupRole::Layer,
                knockout: false,
            };
            let mut matte = root.clone();
            matte.id = matte_id.clone();
            matte.name = "Background matte".into();
            matte.metadata = None;
            matte.visible = true;
            matte.parent = Some(id.into());
            let [r, g, b] = background.matte;
            matte.content = Content::Fill {
                width: document.width,
                height: document.height,
                paint: Paint::Solid([r, g, b, 255]),
                dither: crate::paint::Dither::None,
            };
            document.items.splice(i + 1..i + 1, [matte, source]);
            document.background = None;
            Ok(
                json!({"previous":previous,"background":null,"source_retained":true,"source_id":source_id,"matte_id":matte_id,"appearance":"ordinary_isolated_layer_with_editable_source_and_canvas_sized_matte","matte_coordinates":"captured_canvas_at_conversion"}),
            )
        }
    }
}

pub fn inspect(document: &Document) -> Option<Value> {
    document.background.as_ref().map(|b| {
        let mut result = json!({"item_id":b.item_id,"matte":b.matte,"active":visible_matte(document).is_some(),"canvas_bounds":[0,0,document.width,document.height],"source_alpha":"retained","opaque_appearance":"after_source_controls_before_clipped_siblings","implicit_lock":false});
        if let Some(bounds) = b.fixed_pixel_bounds {
            result["fixed_pixel_bounds"] = json!(bounds);
            result["inactive_fill_byte"] = json!(b.inactive_fill_byte.unwrap_or(255));
            result["source_alpha"] = json!("opaque");
            result["protected"] = json!(["pixel_position","pixel_extent","transparency","appearance"]);
        }
        result
    })
}
