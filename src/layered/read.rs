use super::{binary::*, *};
use std::collections::BTreeSet;

#[derive(Clone, Copy, PartialEq, Eq)]
enum Kind {
    Pixel,
    Group { isolated: bool },
    Boundary,
}
struct Layer {
    bounds: [i32; 4],
    channels: Vec<(i16, usize)>,
    name: String,
    opacity: u8,
    fill: u8,
    visible: bool,
    id: Option<u32>,
    locked: bool,
    kind: Kind,
    mask: Option<super::mask::Record>,
}
impl Layer {
    fn identity(&self, index: usize) -> String {
        self.id.map_or_else(
            || format!("record-{}", index + 1),
            |id| format!("layer-{id}"),
        )
    }
}
fn record(
    input: &mut Reader<'_>,
    ignored: &mut BTreeSet<String>,
    control: &Control,
    version: Version,
) -> Result<Layer, Error> {
    let bounds = [
        input.signed()?,
        input.signed()?,
        input.signed()?,
        input.signed()?,
    ];
    let width = bounds[3] as i64 - bounds[1] as i64;
    let height = bounds[2] as i64 - bounds[0] as i64;
    if width < 0 || height < 0 || bounds.iter().any(|v| v.unsigned_abs() > 32768) {
        return Err(unsupported(
            "Layered pixel records require positive bounded extents",
        ));
    }
    let count = input.short()?;
    if count > 5 {
        return Err(unsupported(
            "Layered import requires RGB with optional transparency and one authored scalar mask",
        ));
    }
    let channels = (0..count)
        .map(|_| Ok((input.short()? as i16, input.length(version)?)))
        .collect::<Result<Vec<_>, Error>>()?;
    let keys: BTreeSet<_> = channels.iter().map(|c| c.0).collect();
    if keys.len() != count as usize || keys.iter().any(|k| ![-2, -1, 0, 1, 2].contains(k)) {
        return Err(unsupported("Unsupported or duplicate layer channels"));
    }
    if input.take(4)? != b"8BIM" {
        return Err(malformed());
    }
    let blend = input.take(4)?;
    if blend != b"norm" && blend != b"pass" {
        return Err(unsupported(
            "Layered import currently preserves normal pixel-layer compositing",
        ));
    }
    let opacity = input.byte()?;
    if input.byte()? != 0 {
        return Err(unsupported(
            "Clipping stacks require extended layered interchange",
        ));
    }
    let flags = input.byte()?;
    if flags & !31 != 0 {
        return Err(unsupported(
            "Layer flags describe unsupported nonpixel appearance",
        ));
    }
    if input.byte()? != 0 {
        return Err(malformed());
    }
    let mut extra = input.section()?;
    let mask = super::mask::Record::read(extra.section()?, version)?;
    if mask.is_some() != keys.contains(&-2) {
        return Err(malformed());
    }
    let mut ranges = extra.section()?;
    while ranges.left() != 0 {
        if ranges.take(8)? != [0, 0, 255, 255, 0, 0, 255, 255] {
            return Err(unsupported("Conditional blend ranges cannot be discarded"));
        }
    }
    let n = extra.byte()? as usize;
    let fallback_name = extra.take(n)?.to_vec();
    extra.take((4 - (n + 1) % 4) % 4)?;
    let mut layer = Layer {
        bounds,
        channels,
        name: String::new(),
        opacity,
        fill: 255,
        visible: flags & 2 == 0,
        id: None,
        locked: false,
        kind: Kind::Pixel,
        mask,
    };
    let mut unicode_name = None;
    let mut keys = BTreeSet::new();
    while extra.left() > 0 {
        if extra.left() < 12 {
            extra.zero_padding(3)?;
            break;
        }
        let signature = extra.take(4)?;
        if signature != b"8BIM" && !(version == Version::Large && signature == b"8B64") {
            return Err(malformed());
        }
        let key: [u8; 4] = extra.take(4)?.try_into().unwrap();
        binary::tag_signature(signature, &key, version)?;
        if !keys.insert(key) {
            return Err(malformed());
        }
        let mut data = extra.tagged_section(&key, version)?;
        let count = data.left();
        match &key {
            b"luni" => {
                unicode_name = Some(data.unicode()?);
                data.zero_padding(3)?;
            }
            b"lyid" => {
                layer.id = Some(data.word()?);
                data.end()?;
            }
            b"lyvr" => {
                let minimum = data.word()?;
                data.end()?;
                if ![70, 80, 110].contains(&minimum) {
                    return Err(unsupported("Unknown minimum layer-reader version"));
                }
                ignored.insert(format!("lyvr:minimum_reader_{minimum}"));
            }
            b"lsct" => {
                if ![4, 12, 16].contains(&count) {
                    return Err(malformed());
                }
                let kind = data.word()?;
                let mode = if data.left() >= 8 {
                    if data.take(4)? != b"8BIM" {
                        return Err(malformed());
                    }
                    data.take(4)?
                } else {
                    blend
                };
                if data.left() == 4 && data.word()? != 0 {
                    return Err(unsupported(
                        "Timeline and scene folders require their own editable mapping",
                    ));
                }
                data.end()?;
                layer.kind = match kind {
                    0 if mode == b"norm" => Kind::Pixel,
                    1 | 2 if mode == b"norm" || mode == b"pass" => {
                        if blend == b"pass" && mode != b"pass" {
                            return Err(malformed());
                        }
                        ignored.insert("lsct:folder_open_state".into());
                        Kind::Group {
                            isolated: mode == b"norm",
                        }
                    }
                    3 if mode == b"norm" => Kind::Boundary,
                    _ => return Err(unsupported("Unknown folder type or group blend mode")),
                };
            }
            b"iOpa" => {
                layer.fill = data.byte()?;
                data.zero_padding(3)?;
            }
            b"lmgm" => {
                let value = data.byte()?;
                data.zero_padding(3)?;
                if value > 1 || layer.mask.is_none() {
                    return Err(unsupported("Unknown mask/effect ordering or missing mask"));
                }
                // Effects and non-normal blends fail separately; both orders agree here.
                ignored.insert(format!(
                    "lmgm:effect_order_{value}_inactive_without_effects"
                ));
            }
            b"lspf" => {
                let locks = data.word()?;
                data.end()?;
                if ![0, 7].contains(&locks) {
                    return Err(unsupported(
                        "Partial layer locks have no whole-item lock equivalent",
                    ));
                }
                layer.locked = locks == 7;
            }
            b"clbl" | b"infx" | b"knko" | b"tsly" => {
                let value = data.byte()?;
                data.zero_padding(3)?;
                let expected = match &key {
                    b"clbl" | b"tsly" => 1,
                    _ => 0,
                };
                if value != expected {
                    return Err(unsupported(
                        "Nondefault layer compositing flags require extended interchange",
                    ));
                }
            }
            b"lclr" | b"fxrp" | b"lnsr" => {
                ignored.insert(String::from_utf8_lossy(&key).into_owned());
            }
            b"shmd" => {
                super::metadata::layer(&mut data, control)?;
                ignored.insert("shmd:layer_timestamp".into());
            }
            _ => {
                return Err(unsupported(&format!(
                    "Layer information {} has no supported editable mapping",
                    String::from_utf8_lossy(&key)
                )));
            }
        }
        if count % 2 != 0 {
            extra.take(1)?;
        }
    }
    layer.name = if let Some(name) = unicode_name {
        name
    } else {
        if !fallback_name.is_ascii() {
            return Err(unsupported(
                "Non-ASCII legacy layer names require a Unicode name record",
            ));
        }
        String::from_utf8(fallback_name).map_err(|_| malformed())?
    };
    if flags & 1 != 0 && !layer.locked {
        return Err(unsupported(
            "Transparency-only locking has no whole-item lock equivalent",
        ));
    }
    let count = count - u16::from(layer.mask.is_some());
    if layer.kind == Kind::Boundary && layer.mask.is_some() {
        return Err(unsupported(
            "Folder boundary records cannot own authored masks",
        ));
    }
    if layer.kind == Kind::Pixel {
        if !(3..=4).contains(&count)
            || ![0, 1, 2]
                .iter()
                .all(|k| layer.channels.iter().any(|c| c.0 == *k))
        {
            return Err(unsupported(
                "Pixel records require RGB with optional transparency",
            ));
        }
        if blend != b"norm" || flags & 16 != 0 {
            return Err(unsupported(
                "Pixel records require ordinary normal compositing",
            ));
        }
        size(width as u32, height as u32, MAX_STORED_PIXELS, version)?;
    } else {
        if count != 0
            && (!(3..=4).contains(&count)
                || ![0, 1, 2]
                    .iter()
                    .all(|k| layer.channels.iter().any(|c| c.0 == *k)))
        {
            return Err(unsupported(
                "Folder cache channels must be empty RGB with optional transparency",
            ));
        }
        if bounds != [0; 4] {
            return Err(unsupported(
                "Folder records with cached pixel extents require an explicit cache mapping",
            ));
        }
        if layer.fill != 255 {
            return Err(unsupported(
                "Folder fill opacity requires independent native compositing verification",
            ));
        }
    }
    Ok(layer)
}

fn hierarchy(records: &[Layer]) -> Result<Vec<Option<String>>, Error> {
    let mut parents = vec![None; records.len()];
    let mut stack: Vec<usize> = Vec::new();
    for (index, record) in records.iter().enumerate().rev() {
        if record.kind == Kind::Boundary {
            stack.pop().ok_or_else(malformed)?;
            continue;
        }
        if stack.len() > crate::scene::MAX_DEPTH {
            return Err(limit("Layered hierarchy exceeds 16 ancestor levels"));
        }
        parents[index] = stack.last().map(|&parent| records[parent].identity(parent));
        if matches!(record.kind, Kind::Group { .. }) {
            stack.push(index);
        }
    }
    if !stack.is_empty() {
        return Err(malformed());
    }
    Ok(parents)
}

pub(super) fn document(
    bytes: &[u8],
    id: String,
    policy: assets::ColorPolicy,
    control: &Control,
) -> Result<Value, Error> {
    let mut input = Reader::new(bytes);
    if input.take(4)? != b"8BPS" {
        return Err(malformed());
    }
    let version = Version::read(input.short()?)?;
    if input.take(6)? != [0; 6] {
        return Err(malformed());
    }
    let channels = input.short()?;
    let height = input.word()?;
    let width = input.word()?;
    let canvas = size(width, height, MAX_CANVAS_PIXELS, version)?;
    if input.short()? != 8 || input.short()? != 3 || !(3..=4).contains(&channels) {
        return Err(unsupported(
            "Layered import requires 8-bit RGB with optional merged transparency",
        ));
    }
    if input.section()?.left() != 0 {
        return Err(unsupported(
            "Unexpected indexed or duotone colour data in RGB document",
        ));
    }
    let mut resources = input.section()?;
    let mut resource_ids = BTreeSet::new();
    let mut ignored = BTreeSet::new();
    let mut profile = None;
    let mut resolution = 96.0;
    let mut density_declared = false;
    while resources.left() > 0 {
        control.check()?;
        if resources.take(4)? != b"8BIM" {
            return Err(malformed());
        }
        let key = resources.short()?;
        if !resource_ids.insert(key) {
            return Err(malformed());
        }
        let n = resources.byte()? as usize;
        resources.take(n)?;
        if !(n + 1).is_multiple_of(2) {
            resources.take(1)?;
        }
        let mut data = resources.section()?;
        let count = data.left();
        match key {
            1039 => {
                crate::profiles::parse(data.data)?;
                profile = Some(data.data.to_vec());
            }
            1005 => {
                let x = data.word()? as f64 / 65536.0;
                let xu = data.short()?;
                data.short()?;
                let y = data.word()? as f64 / 65536.0;
                let yu = data.short()?;
                data.short()?;
                data.end()?;
                // The fixed-point values are always ppi; selectors only change display units.
                if ![1, 2].contains(&xu) || ![1, 2].contains(&yu) {
                    return Err(malformed());
                }
                if x != y {
                    return Err(unsupported(
                        "Anisotropic pixel density requires an explicit mapping",
                    ));
                }
                resolution = x;
                density_declared = true;
            }
            1057 => {
                if data.word()? != 1 {
                    return Err(unsupported("Unknown merged-cache version record"));
                }
                if data.byte()? > 1 {
                    return Err(malformed());
                }
                data.unicode()?;
                data.unicode()?;
                data.word()?;
                data.end()?;
            }
            1006 | 1045 | 1053 | 1077 => {
                super::metadata::alpha(key, &mut data, channels)?;
                ignored.insert(format!("resource:{key}"));
            }
            10000 => {
                if data.short()? != 1 || data.byte()? > 1 || data.byte()? != 0 {
                    return Err(malformed());
                }
                data.word()?;
                data.short()?;
                data.end()?;
                ignored.insert("resource:10000".into());
            }
            1032 | 1092 => {
                let expected_version = if key == 1032 { 1 } else { 2 };
                if data.word()? != expected_version || data.word()? == 0 || data.word()? == 0 {
                    return Err(unsupported(
                        "Unknown guide-grid resource version or spacing",
                    ));
                }
                if data.word()? != 0 {
                    return Err(unsupported(
                        "Guide geometry requires extended layered interchange",
                    ));
                }
                data.end()?;
                ignored.insert(format!("resource:{key}:empty_guides"));
            }
            1097 => {
                if data.word()? != 0 {
                    return Err(unsupported(
                        "Guide identity associations require extended layered interchange",
                    ));
                }
                data.end()?;
                ignored.insert("resource:1097:empty_guide_identities".into());
            }
            // These records carry descriptive/UI/preview state, never editable paint.
            1008 | 1010 | 1011 | 1024 | 1026 | 1028 | 1033 | 1035 | 1036 | 1037 | 1044 | 1049
            | 1054 | 1058 | 1059 | 1060 | 1061 | 1062 | 1064 | 1069 | 1072 | 1082 | 1083 | 1084
            | 1085 | 1086 | 1087 | 1013 | 1016 | 1050 => {
                ignored.insert(format!("resource:{key}"));
            }
            _ => {
                return Err(unsupported(&format!(
                    "Image resource {key} has no supported editable mapping"
                )));
            }
        }
        if count % 2 != 0 {
            resources.take(1)?;
        }
    }
    let working = crate::profiles::resolve(&crate::profiles::Profile::Builtin {
        name: crate::profiles::Builtin::Srgb,
    })?
    .0;
    let convert = match &profile {
        Some(p) if p == &working => false,
        Some(_) if policy == assets::ColorPolicy::ConvertSrgb => true,
        Some(_) => {
            return Err(Error::new(
                "COLOR_POLICY_REQUIRED",
                "A different embedded RGB profile requires explicit convert_srgb; source interpretation cannot be replaced by an assumption",
            ));
        }
        None if policy == assets::ColorPolicy::AssumeSrgb => false,
        None => {
            return Err(Error::new(
                "COLOR_POLICY_REQUIRED",
                "Untagged layered RGB requires explicit assume_srgb",
            ));
        }
    };
    let mut section = input.framed_section(version)?;
    if section.left() == 0 {
        return Err(unsupported("Flattened input has no editable layer records"));
    }
    let mut layers = section.framed_section(version)?;
    if !layers.data.len().is_multiple_of(2) {
        return Err(malformed());
    }
    let count = layers.short()? as i16;
    if count == 0 || count == i16::MIN || count.unsigned_abs() as usize > MAX_ITEMS * 2 {
        return Err(limit(
            "Layered input exceeds 512 serialized layer and boundary records",
        ));
    }
    if (channels == 4) != (count < 0) {
        return Err(unsupported(
            "Additional merged alpha channels are distinct from document transparency",
        ));
    }
    let mut records = Vec::new();
    let mut total = 0;
    let mut ids = BTreeSet::new();
    for _ in 0..count.unsigned_abs() {
        control.check()?;
        let r = record(&mut layers, &mut ignored, control, version)
            .map_err(|e| context(e, "Layer record"))?;
        if r.kind != Kind::Boundary && r.id.is_some_and(|id| !ids.insert(id)) {
            return Err(malformed());
        }
        total += (r.bounds[3] - r.bounds[1]) as usize * (r.bounds[2] - r.bounds[0]) as usize;
        total += r.mask.as_ref().map_or(0, super::mask::Record::pixels);
        if total > MAX_STORED_PIXELS {
            return Err(limit("Retained layer and mask pixels exceed 65536"));
        }
        records.push(r);
    }
    let parents = hierarchy(&records)?;
    let editable = records.iter().filter(|r| r.kind != Kind::Boundary).count();
    if editable > MAX_ITEMS {
        return Err(limit("Layered input exceeds 256 editable items"));
    }
    let mut items = Vec::new();
    for (index, r) in records.iter().enumerate() {
        control.check()?;
        let w = (r.bounds[3] - r.bounds[1]) as usize;
        let h = (r.bounds[2] - r.bounds[0]) as usize;
        let mut rgba = vec![255; w * h * 4];
        let mut mask = None;
        for &(channel, count) in &r.channels {
            if channel == -2 {
                let record = r.mask.as_ref().ok_or_else(malformed)?;
                let values = binary::decode(
                    layers.take(count)?,
                    record.width,
                    record.height,
                    version,
                    control,
                )
                .map_err(|e| context(e, "Mask samples"))?;
                mask = Some(record.document_mask(&values, [r.bounds[1], r.bounds[0]]));
                continue;
            }
            let values = binary::decode(layers.take(count)?, w, h, version, control)
                .map_err(|e| context(e, "Layer samples"))?;
            let c = if channel == -1 { 3 } else { channel as usize };
            for (p, v) in rgba.as_chunks_mut::<4>().0.iter_mut().zip(values) {
                p[c] = v;
            }
        }
        if r.kind == Kind::Boundary {
            continue;
        }
        if convert && r.kind == Kind::Pixel {
            let mut values = rgba.iter().map(|v| *v as f64 / 255.0).collect::<Vec<_>>();
            crate::profiles::convert_f64(
                &mut values,
                &crate::profiles::Profile::Icc {
                    data: STANDARD.encode(profile.as_ref().unwrap()),
                },
                &crate::profiles::Profile::Builtin {
                    name: crate::profiles::Builtin::Srgb,
                },
                crate::profiles::Intent::RelativeColorimetric,
                true,
                Some(control),
            )?;
            for (out, value) in rgba.iter_mut().zip(values) {
                *out = (value * 255.0).round() as u8;
            }
        }
        let content = match r.kind {
            Kind::Pixel => {
                json!({"type":"raster","width":w,"height":h,"rgba_hex":crate::render::hex(&rgba)})
            }
            Kind::Group { isolated } => json!({"type":"group","isolated":isolated}),
            Kind::Boundary => unreachable!(),
        };
        let item:Item=serde_json::from_value(json!({"id":r.identity(index),"parent":parents[index],"name":r.name,"visible":r.visible,"locked":r.locked,"opacity":r.opacity as f64/255.0,"fill_opacity":r.fill as f64/255.0,"transform":[1,0,0,1,r.bounds[1],r.bounds[0]],"mask":mask,"content":content})).map_err(|_|malformed())?;
        items.push(item);
    }
    layers
        .zero_padding(3)
        .map_err(|e| context(e, "Layer section padding"))?;
    let mut overlay = section.section()?;
    if overlay.left() != 0 {
        overlay.take(10)?;
        if overlay.short()? > 100 || overlay.byte()? != 128 {
            return Err(unsupported(
                "Legacy global mask coverage requires an explicit mapping",
            ));
        }
        overlay.zero_padding(3)?;
        ignored.insert("global_mask:per_layer_display_overlay".into());
    }
    super::metadata::global(&mut section, &mut ignored, control, version)?;
    let merged = binary::decode(
        input.take(input.left())?,
        width as usize,
        height as usize * channels as usize,
        version,
        control,
    )
    .map_err(|e| context(e, "Merged samples"))?;
    if merged.len() != canvas * channels as usize {
        return Err(malformed());
    }
    let document:Document=serde_json::from_value(json!({"schema_version":2,"id":id,"kind":"raster","width":width,"height":height,"resolution_ppi":resolution,"color_space":"srgb","items":items})).map_err(|_|malformed())?;
    crate::validate(&document)?;
    control.check()?;
    Ok(
        json!({"document":document,"format":if version==Version::Large{"layered_rgb_v2"}else{"layered_rgb_v1"},"file_version":version.number(),"layers":editable,"serialized_records":records.len(),"masked_items":records.iter().filter(|r|r.mask.is_some()).count(),"groups":records.iter().filter(|r|matches!(r.kind,Kind::Group{..})).count(),"source_profile_sha256":profile.as_ref().map(|v|assets::sha256(v)),"interpretation":if convert{"converted_srgb_per_layer"}else if profile.is_some(){"declared_working_srgb"}else{"assumed_srgb"},"merged_cache":{"sample_sha256":assets::sha256(&merged),"used_for_editable_reconstruction":false},"resolution_declared":density_declared,"omitted_nonappearance_records":ignored,"losses":["Creates new layer identities from numeric file IDs; preserves native pixel extents, sibling order, folder hierarchy, Unicode names, visibility, opacity and supported full locks. Folder expansion state is listed as omitted UI metadata. No file is overwritten.","The merged cache is decoded and validated but editable appearance is recomputed from layers. Descriptive/UI/thumbnail records listed in the receipt are not imported as trusted document metadata.","Explicit conversion to working sRGB changes layer RGB before compositing, preserves alpha and can change profile-space blending. It is not a promise of cross-consumer composite equality."]}),
    )
}

fn context(mut error: Error, location: &str) -> Error {
    error.message = format!("{location}: {}", error.message);
    error
}
