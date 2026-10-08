use super::{binary::*, *};
fn native_byte(value: f64) -> Result<u8, Error> {
    let byte = (value * 255.0).round() as u8;
    if byte as f64 / 255.0 != value {
        return Err(unsupported(
            "Layered opacity must be an exact byte fraction; quantize explicitly on a source copy",
        ));
    }
    Ok(byte)
}
fn original(item: &Item, world: Matrix) -> Result<(u32, u32, Vec<u8>), Error> {
    if item.blend != BlendMode::Normal
        || item.clip_to.is_some()
        || item.clip.is_some()
        || item.artwork_mask.is_some()
        || !item.effects.is_empty()
        || !item.filters.is_empty()
        || item.hdr_grade.is_some()
        || item.pixel_warp.is_some()
        || !item.coverage.is_smooth()
    {
        return Err(unsupported("Layered delivery needs normal pixel layers or normal/pass-through folders without effects, filters or clipping; no implicit flattening is performed").at_item(&item.id));
    }
    let [a, b, c, d, x, y] = world;
    if [a, b, c, d] != [1.0, 0.0, 0.0, 1.0] || x.fract() != 0.0 || y.fract() != 0.0 {
        return Err(unsupported(
            "Layered native pixels require an integer translation without resampling",
        )
        .at_item(&item.id));
    }
    if item.name.encode_utf16().count() > 1024 {
        return Err(limit("Layer name exceeds 1024 UTF-16 units"));
    }
    match &item.content {
        Content::Group { knockout:false,role:GroupRole::Group,.. } if item.fill_opacity == 1.0 => Ok((0,0,Vec::new())),
        Content::Raster{width,height,rgba_hex,sampling} if *sampling==assets::Sampling::Nearest => Ok((*width,*height,crate::render::unhex(rgba_hex))),
        Content::Samples{grid} if grid.depth==crate::samples::Depth::U8 && grid.channels==crate::samples::Channels::Rgba && grid.encoding==crate::hdr::Encoding::EncodedSrgb && grid.sampling==assets::Sampling::Nearest && grid.profile.is_none() => Ok((grid.width,grid.height,crate::render::unhex(&grid.data_hex))),
        _=>Err(unsupported("Layered basic delivery requires original RGBA8 pixel layers; use explicit engine expansion for other sources").at_item(&item.id)),
    }
}

fn order(document: &Document, parent: Option<&str>, records: &mut Vec<(usize, bool)>) {
    for index in crate::scene::children(document, parent) {
        let item = &document.items[index];
        if matches!(item.content, Content::Group { .. }) {
            records.push((index, true));
            order(document, Some(&item.id), records);
        }
        records.push((index, false));
    }
}
pub(super) fn document(
    document: &Document,
    compression: Compression,
    version: Version,
    control: &Control,
) -> Result<Value, Error> {
    control.check()?;
    crate::validate(document)?;
    if document.kind != DocumentKind::Raster
        || document.color_space != ColorSpace::Srgb
        || document.background.is_some()
        || document.output_profile.is_some()
        || document.vector_canvas.is_some()
        || document.ink_recipe.is_some()
        || !document.stories.is_empty()
        || !document.assets.is_empty()
        || !document.fonts.is_empty()
        || !document.swatches.is_empty()
        || document.selection.is_some()
        || !document.channels.is_empty()
    {
        return Err(unsupported(
            "Layered basic delivery preserves working-sRGB pixel layers; other document resources and output interpretations require explicit interchange mapping",
        ));
    }
    size(document.width, document.height, MAX_CANVAS_PIXELS, version)?;
    if document.items.is_empty() {
        return Err(unsupported(
            "Layered delivery requires at least one editable pixel layer",
        ));
    }
    let mut records = Vec::new();
    let mut channel_data = Vec::new();
    let mut receipts = Vec::new();
    let mut ordered = Vec::new();
    order(document, None, &mut ordered);
    short(&mut records, (-(ordered.len() as i16)) as u16);
    for &(index, boundary) in &ordered {
        let item = &document.items[index];
        control.check()?;
        let world = crate::scene::world_transform(document, index)?;
        let (w, h, rgba) = original(item, world)?;
        let group = matches!(item.content, Content::Group { .. });
        if !group {
            size(w, h, MAX_STORED_PIXELS, version)?;
        }
        let left = if group { 0 } else { world[4] as i32 };
        let top = if group { 0 } else { world[5] as i32 };
        let bounds = [top, left, top + h as i32, left + w as i32];
        if bounds
            .iter()
            .any(|&value| !(-32768..=32768).contains(&value))
        {
            return Err(limit(
                "Layered pixel bounds exceed the supported coordinate range",
            ));
        }
        for value in bounds {
            records.extend(value.to_be_bytes());
        }
        let mask = if boundary {
            None
        } else {
            item.mask
                .as_ref()
                .map(|mask| super::mask::encode_mask(mask, world, version, compression))
                .transpose()?
        };
        short(&mut records, 4 + u16::from(mask.is_some()));
        for channel in [-1_i16, 0, 1, 2] {
            let c = if channel == -1 { 3 } else { channel as usize };
            let plane = rgba
                .as_chunks::<4>()
                .0
                .iter()
                .map(|p| p[c])
                .collect::<Vec<_>>();
            let bytes = if group {
                vec![0, 0]
            } else {
                encode(&plane, w as usize, compression, version)
            };
            short(&mut records, channel as u16);
            length(&mut records, bytes.len(), version);
            channel_data.extend(bytes);
        }
        if let Some(mask) = &mask {
            short(&mut records, (-2_i16) as u16);
            length(&mut records, mask.channel.len(), version);
            channel_data.extend_from_slice(&mask.channel);
        }
        records.extend(b"8BIMnorm");
        records.extend([
            if boundary {
                255
            } else {
                native_byte(item.opacity)?
            },
            0,
            8 | if boundary || item.visible { 0 } else { 2 },
            0,
        ]);
        let mut extra = Vec::new();
        section(
            &mut extra,
            mask.as_ref().map_or(&[], |mask| mask.metadata.as_slice()),
        );
        word(&mut extra, 0);
        let full_name = if boundary { "<group end>" } else { &item.name };
        let name = full_name
            .chars()
            .take(255)
            .map(|c| if c.is_ascii() { c as u8 } else { b'?' })
            .collect::<Vec<_>>();
        let name_length = name.len() + 1;
        extra.push(name.len() as u8);
        extra.extend(name);
        extra.extend(std::iter::repeat_n(0, (4 - name_length % 4) % 4));
        tagged(&mut extra, b"luni", &unicode(full_name));
        let file_id = index + 1 + if boundary { document.items.len() } else { 0 };
        tagged(&mut extra, b"lyid", &(file_id as u32).to_be_bytes());
        tagged(
            &mut extra,
            b"lspf",
            &(if !boundary && item.locked { 7u32 } else { 0u32 }).to_be_bytes(),
        );
        tagged(
            &mut extra,
            b"iOpa",
            &[native_byte(item.fill_opacity)?, 0, 0, 0],
        );
        if let Content::Group { isolated, .. } = item.content {
            let mut divider = Vec::new();
            word(&mut divider, if boundary { 3 } else { 1 });
            if !boundary {
                divider.extend(b"8BIM");
                divider.extend(if isolated { b"norm" } else { b"pass" });
            }
            tagged(&mut extra, b"lsct", &divider);
        }
        section(&mut records, &extra);
        if !boundary {
            receipts.push(json!({"source_id":item.id,"file_id":file_id,"parent_source_id":item.parent,"kind":if group{"group"}else{"pixel"},"bounds":[top,left,top+h as i32,left+w as i32],"rgba_sha256":if group{None}else{Some(assets::sha256(&rgba))},"mask":mask.map(|mask|mask.receipt)}));
        }
    }
    records.extend(channel_data);
    if !records.len().is_multiple_of(2) {
        records.push(0);
    }
    let mut layers = Vec::new();
    framed_section(&mut layers, &records, version);
    word(&mut layers, 0);
    let profile = crate::profiles::resolve(&crate::profiles::Profile::Builtin {
        name: crate::profiles::Builtin::Srgb,
    })?
    .0;
    let mut resources = Vec::new();
    resource(&mut resources, 1039, &profile);
    let density = (document.resolution_ppi * 65536.0).round() as u32;
    let mut resolution = Vec::new();
    for _ in 0..2 {
        word(&mut resolution, density);
        short(&mut resolution, 1);
        short(&mut resolution, 1);
    }
    resource(&mut resources, 1005, &resolution);
    let mut cache_version = Vec::new();
    word(&mut cache_version, 1);
    cache_version.push(1);
    cache_version.extend(unicode("Inkbolt"));
    cache_version.extend(unicode("Inkbolt"));
    word(&mut cache_version, 1);
    resource(&mut resources, 1057, &cache_version);
    let mut bytes = b"8BPS".to_vec();
    short(&mut bytes, version.number());
    bytes.extend([0; 6]);
    short(&mut bytes, 4);
    word(&mut bytes, document.height);
    word(&mut bytes, document.width);
    short(&mut bytes, 8);
    short(&mut bytes, 3);
    word(&mut bytes, 0);
    section(&mut bytes, &resources);
    framed_section(&mut bytes, &layers, version);
    control.check()?;
    let raster = crate::render::rasterize(document, 1)?;
    let mut composite = Vec::with_capacity(raster.rgba.len());
    for c in 0..4 {
        composite.extend(raster.rgba.as_chunks::<4>().0.iter().map(|p| {
            if c == 3 {
                p[3]
            } else {
                let alpha = p[3] as u32;
                ((p[c] as u32 * alpha + 255 * (255 - alpha) + 127) / 255) as u8
            }
        }));
    }
    bytes.extend(encode(
        &composite,
        document.width as usize,
        compression,
        version,
    ));
    control.check()?;
    if bytes.len() > MAX_FILE_BYTES {
        return Err(limit("Layered export exceeds 32 MiB"));
    }
    Ok(
        json!({"media_type":"application/octet-stream","encoding":"base64","data":STANDARD.encode(&bytes),"layered":{"version":version.number(),"mode":"rgb8","compression":compression,"layers":receipts,"empty_name_source_ids":document.items.iter().filter(|i|i.name.is_empty()).map(|i|&i.id).collect::<Vec<_>>(),"serialized_records":ordered.len(),"order":"bottom_to_top","source_composite_rgba_sha256":assets::sha256(&raster.rgba),"merged_planes_sha256":assets::sha256(&composite),"merged_color":"white_matted_rgb_plus_straight_alpha","profile_sha256":assets::sha256(&profile),"resolution_ppi":density as f64/65536.0,"source_changed":false},"losses":["Native pixel bytes, extents, names, visibility, exact byte opacity and normal/pass-through folder hierarchy are retained. Folder transforms are resolved to absolute pixel placements; imported folder transforms are identity, and source documents are unchanged. File layer IDs are independently generated; source IDs appear only in the delivery receipt. Empty names are encoded exactly, but native consumers may generate names for them; empty_name_source_ids identifies those items. Name items explicitly for stable external names.","The merged cache stores RGB composited against white plus a separate alpha plane. Unmatting this 8-bit cache can lose straight RGB precision at low alpha. Editable source pixels remain separate; consumer compositing and rounding can differ.","Physical density rounds to unsigned 16.16 pixels per inch. Engine history, variants and private metadata are not embedded as an editable engine snapshot."]}),
    )
}
