use super::*;
use crate::artwork_masks::{self, Mode};

pub(super) fn prepare(
    writer: &mut Writer,
    document: &Document,
    fonts: &crate::fonts::Cache,
) -> Result<BTreeMap<String, usize>, Error> {
    let mut states = BTreeMap::new();
    for (i, owner) in document.items.iter().enumerate() {
        let Some(mask) = owner.artwork_mask.as_ref().filter(|m| m.enabled) else {
            continue;
        };
        writer.control.check()?;
        let world = scene::world_transform(document, i)?;
        let mut instance = artwork_masks::instance(document, mask, world)?;
        // A named ink contributes its declared display coverage inside a mask,
        // even when the surrounding artwork is delivered on native plates.
        if writer.native_inks
            && !instance.swatches.is_empty()
            && let Some(resolved) =
                crate::swatches::evaluate(&instance).map_err(|e| e.at_item(&owner.id))?
        {
            instance = resolved;
        }
        validate_controlled(&instance, &writer.control).map_err(|e| e.at_item(&owner.id))?;
        let layouts = checked_layouts(&instance, fonts).map_err(|e| e.at_item(&owner.id))?;
        if !scene::effective_visible(document, i)?
            || matches!(owner.content, Content::WorkPath { .. })
        {
            continue;
        }
        let mut stream = Stream {
            scalar_artwork: true,
            default_rgb: writer.default_rgb,
            ..Stream::default()
        };
        let region = mask.region_geometry();
        if let Some(region) = region.as_ref().filter(|_| mask.clip_region) {
            clip(
                writer,
                &mut stream,
                region,
                geometry::multiply(mask.world_transform(world), mask.region_transform),
                FillRule::Nonzero,
            )?;
        }
        if !mask.clip_region || region.is_some() {
            let resources = PageResources {
                layouts,
                ..PageResources::default()
            };
            items(writer, &mut stream, &instance, None, &resources)
                .map_err(|e| e.at_item(&owner.id))?;
        }
        let dictionary = opacity::mask_dictionary(
            writer,
            stream,
            mask.mode,
            0.0,
            owner.opacity * owner.fill_opacity,
        )?;
        states.insert(owner.id.clone(), writer.add(dictionary)?);
        match mask.mode {
            Mode::Alpha => writer.artwork_alpha_masks += 1,
            Mode::Luminance => writer.artwork_luminance_masks += 1,
        }
    }
    Ok(states)
}
