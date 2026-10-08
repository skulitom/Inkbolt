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
    document.background.as_ref().map(|b| json!({"item_id":b.item_id,"matte":b.matte,"active":visible_matte(document).is_some(),"canvas_bounds":[0,0,document.width,document.height],"source_alpha":"retained","opaque_appearance":"after_source_controls_before_clipped_siblings","implicit_lock":false}))
}
