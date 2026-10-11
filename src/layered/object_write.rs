//! Original placed-source encoding and separately rendered compatibility caches.
use super::{binary::*, *};

pub(super) struct Prepared {
    pub width: u32,
    pub height: u32,
    pub origin: [i32; 2],
    pub rgba: Vec<u8>,
    pub placement: Vec<u8>,
    pub source: Vec<u8>,
    pub receipt: Value,
}

fn key(out: &mut Vec<u8>, value: &str) {
    word(
        out,
        if value.len() == 4 {
            0
        } else {
            value.len() as u32
        },
    );
    out.extend(value.as_bytes());
}
pub(super) fn descriptor(class: &str, fields: Vec<(&str, Vec<u8>)>) -> Vec<u8> {
    let mut out = unicode("");
    key(&mut out, class);
    word(&mut out, fields.len() as u32);
    for (name, value) in fields {
        key(&mut out, name);
        out.extend(value);
    }
    out
}
pub(super) fn object(class: &str, fields: Vec<(&str, Vec<u8>)>) -> Vec<u8> {
    let mut out = b"Objc".to_vec();
    out.extend(descriptor(class, fields));
    out
}
pub(super) fn number(value: f64) -> Vec<u8> {
    let mut out = b"doub".to_vec();
    out.extend(value.to_be_bytes());
    out
}
pub(super) fn integer(value: i32) -> Vec<u8> {
    let mut out = b"long".to_vec();
    out.extend(value.to_be_bytes());
    out
}
pub(super) fn text(value: &str) -> Vec<u8> {
    let mut out = b"TEXT".to_vec();
    out.extend(unicode(&format!("{value}\0")));
    out
}
pub(super) fn enumeration(class: &str, value: &str) -> Vec<u8> {
    let mut out = b"enum".to_vec();
    key(&mut out, class);
    key(&mut out, value);
    out
}
fn points(values: &[f64; 8]) -> Vec<u8> {
    let mut out = b"VlLs".to_vec();
    word(&mut out, 8);
    for v in values {
        out.extend(number(*v));
    }
    out
}
fn identity(scope: &str, role: &str, source: &str) -> String {
    let digest = assets::sha256(format!("Inkbolt layered {role} {scope} {source}").as_bytes());
    format!(
        "{}-{}-{}-{}-{}",
        &digest[..8],
        &digest[8..12],
        &digest[12..16],
        &digest[16..20],
        &digest[20..32]
    )
}
fn placement(
    source: &str,
    placed: &str,
    corners: &[f64; 8],
    width: u32,
    height: u32,
    resolution: f64,
) -> Vec<u8> {
    let bounds = object(
        "classFloatRect",
        vec![
            ("Top ", number(0.0)),
            ("Left", number(0.0)),
            ("Btom", number(height as f64)),
            ("Rght", number(width as f64)),
        ],
    );
    let warp = object(
        "warp",
        vec![
            ("warpStyle", enumeration("warpStyle", "warpNone")),
            ("warpValue", number(0.0)),
            ("warpPerspective", number(0.0)),
            ("warpPerspectiveOther", number(0.0)),
            ("warpRotate", enumeration("Ornt", "Hrzn")),
            ("bounds", bounds),
            ("uOrder", integer(4)),
            ("vOrder", integer(4)),
        ],
    );
    let still = || {
        object(
            "null",
            vec![("numerator", integer(0)), ("denominator", integer(24))],
        )
    };
    let mut density = b"UntF#Rsl".to_vec();
    density.extend(resolution.to_be_bytes());
    let mut out = b"soLD".to_vec();
    word(&mut out, 4);
    word(&mut out, 16);
    out.extend(descriptor(
        "null",
        vec![
            ("Idnt", text(source)),
            ("placed", text(placed)),
            ("PgNm", integer(1)),
            ("totalPages", integer(1)),
            ("Crop", integer(1)),
            ("frameCount", integer(1)),
            ("Annt", integer(16)),
            ("Type", integer(2)),
            ("comp", integer(-1)),
            ("frameStep", still()),
            ("duration", still()),
            ("Trnf", points(corners)),
            ("nonAffineTransform", points(corners)),
            ("warp", warp),
            (
                "Sz  ",
                object(
                    "Pnt ",
                    vec![
                        ("Wdth", number(width as f64)),
                        ("Hght", number(height as f64)),
                    ],
                ),
            ),
            ("Rslt", density),
            (
                "compInfo",
                object(
                    "null",
                    vec![("compID", integer(-1)), ("originalCompID", integer(-1))],
                ),
            ),
        ],
    ));
    out
}
pub(super) fn prepare(
    item: &Item,
    world: Matrix,
    index: usize,
    compression: Compression,
    context: &mut Encoding<'_>,
) -> Result<Prepared, Error> {
    super::write::controls(item)?;
    let Content::Object { object } = &item.content else {
        unreachable!()
    };
    if object.link.is_some() || object.view.is_some() {
        return Err(unsupported("Native embedded delivery requires an independent working-sRGB source without external link or HDR view").at_item(&item.id));
    }
    let source_document = object.document()?;
    if source_document.metadata.is_some()
        || source_document.items.iter().any(|i| i.metadata.is_some())
    {
        return Err(unsupported("Strip descriptive metadata explicitly from a copy of the embedded source before native delivery").at_item(&item.id));
    }
    let scope = format!("{}-{index}", context.scope);
    let source_id = identity(&scope, "source", &object.sha256);
    let placed_id = identity(&scope, "placement", &object.sha256);
    let encoded = super::write::document(
        &source_document,
        compression,
        Version::Large,
        &mut Encoding {
            options: context.options,
            control: context.control,
            budget: context.budget,
            depth: context.depth + 1,
            scope,
            font_root: context.font_root,
        },
    )?;
    let bytes = STANDARD
        .decode(encoded["data"].as_str().ok_or_else(malformed)?)
        .map_err(|_| malformed())?;
    context.budget.source_bytes += bytes.len();
    if context.budget.source_bytes > MAX_FILE_BYTES {
        return Err(limit(&format!(
            "Embedded delivery source payloads exceed {} MiB",
            MAX_FILE_BYTES as f64 / 1_048_576.0
        )));
    }
    let mut corners = [0.0; 8];
    for (i, point) in [
        [0.0, 0.0],
        [object.width, 0.0],
        [object.width, object.height],
        [0.0, object.height],
    ]
    .into_iter()
    .enumerate()
    {
        let mapped = crate::geometry::relative_transform(
            [1.0, 0.0, 0.0, 1.0, 0.0, 0.0],
            &[world, [1.0, 0.0, 0.0, 1.0, point[0], point[1]]],
        )?;
        corners[i * 2] = mapped[4];
        corners[i * 2 + 1] = mapped[5];
    }
    if corners
        .iter()
        .any(|v| !(-crate::model::MAX_COORDINATE..=crate::model::MAX_COORDINATE).contains(v))
    {
        return Err(limit(
            "Embedded native placement corners exceed coordinate limits",
        ));
    }
    let density = encoded["layered"]["resolution_ppi"]
        .as_f64()
        .ok_or_else(malformed)?;
    let descriptor = placement(
        &source_id,
        &placed_id,
        &corners,
        source_document.width,
        source_document.height,
        density,
    );
    // Check the public representation before writing caches or source-table bytes.
    let restored = super::objects::placement(&mut Reader::new(&descriptor), context.control)?;
    restored.matrix()?;
    let left = corners
        .iter()
        .step_by(2)
        .copied()
        .fold(f64::INFINITY, f64::min)
        .floor() as i32;
    let top = corners
        .iter()
        .skip(1)
        .step_by(2)
        .copied()
        .fold(f64::INFINITY, f64::min)
        .floor() as i32;
    let right = corners
        .iter()
        .step_by(2)
        .copied()
        .fold(f64::NEG_INFINITY, f64::max)
        .ceil() as i32;
    let bottom = corners
        .iter()
        .skip(1)
        .step_by(2)
        .copied()
        .fold(f64::NEG_INFINITY, f64::max)
        .ceil() as i32;
    let width = (right - left) as u32;
    let height = (bottom - top) as u32;
    size(width, height, MAX_STORED_PIXELS, Version::Large)?;
    if context.budget.pixels + width as usize * height as usize > MAX_DECODED_BYTES / 4 {
        return Err(limit(
            "Embedded cache exceeds the aggregate decoded sample budget",
        ));
    }
    let translated = crate::geometry::relative_transform(
        [1.0, 0.0, 0.0, 1.0, left as f64, top as f64],
        &[world],
    )?;
    let cache_document:Document=serde_json::from_value(json!({"schema_version":2,"id":"placed-cache","kind":"raster",
        "width":width,"height":height,"color_space":"srgb","items":[{"id":"source","transform":translated,"content":item.content}]})).map_err(|_|malformed())?;
    let raster = crate::render::rasterize_controlled(
        &cache_document,
        1,
        None,
        context.font_root,
        None,
        context.control,
    )?;
    let mut entry = b"liFD".to_vec();
    word(&mut entry, 7);
    entry.push(source_id.len() as u8);
    entry.extend(source_id.as_bytes());
    entry.extend(unicode(&format!("source-{index}.psb\0")));
    entry.extend(b"8BPBIBLT");
    length(&mut entry, bytes.len(), Version::Large);
    entry.push(0);
    entry.extend_from_slice(&bytes);
    entry.extend(unicode(""));
    entry.extend(0.0f64.to_be_bytes());
    entry.push(0);
    entry.extend(std::iter::repeat_n(0, (4 - entry.len() % 4) % 4));
    let mut table = Vec::new();
    framed_section(&mut table, &entry, Version::Large);
    Ok(Prepared {
        width,
        height,
        origin: [left, top],
        rgba: raster.rgba,
        placement: descriptor,
        source: table,
        receipt: json!({"item_id":item.id,"source_id":source_id,"placed_id":placed_id,"source_snapshot_sha256":object.sha256,
            "native_source_sha256":assets::sha256(&bytes),"native_source_bytes":bytes.len(),"native_source_version":2,"source_table_version":7,
            "source_size":[source_document.width,source_document.height],"source_resolution_ppi":density,"corners":corners,
            "source_sampling":object.sampling,"source_surface_scale":object.surface_scale,"delivery_policy":"native_reconstruction",
            "sharing":"independent_sources","source_changed":false,"nested_delivery":encoded["layered"],"source_losses":encoded["losses"]}),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn embedded_delivery_library_raw_and_rle_retain_sources() {
        let source = json!({"schema_version":2,"id":"original","kind":"raster","width":2,"height":1,"color_space":"srgb",
            "items":[{"id":"pixels","content":{"type":"raster","width":2,"height":1,"rgba_hex":"c0204000145078ff"}}]}).to_string();
        let object = crate::objects::import(None, Some(&source), None).unwrap();
        let d: Document = serde_json::from_value(json!({"schema_version":2,"id":"outer","kind":"raster","width":4,"height":2,"color_space":"srgb",
            "items":[{"id":"placed","content":{"type":"object","object":object["object"]}}]})).unwrap();
        for version in [Version::Standard, Version::Large] {
            for compression in [Compression::Raw, Compression::Rle] {
                let encoded = export_with_options(
                    &d,
                    compression,
                    version,
                    &ExportOptions {
                        embedded_objects: Some(ObjectDelivery::NativeReconstruction),
                        text: None,
                    },
                    &Control::default(),
                )
                .unwrap();
                let bytes = STANDARD.decode(encoded["data"].as_str().unwrap()).unwrap();
                let reopened = decode_with_objects(
                    &bytes,
                    "reopened".into(),
                    assets::ColorPolicy::RequireSrgb,
                    Some(EmbeddedObjects {
                        sampling: assets::Sampling::Nearest,
                        sharing: ObjectSharing::IndependentCopies,
                    }),
                    &Control::default(),
                )
                .unwrap();
                let snapshot = reopened["document"]["items"][0]["content"]["object"]["snapshot"]
                    .as_str()
                    .unwrap();
                let inner: Value = serde_json::from_str(snapshot).unwrap();
                assert_eq!(inner["items"][0]["content"]["rgba_hex"], "c0204000145078ff");
                assert_eq!(
                    encoded["layered"]["embedded_objects"][0]["source_snapshot_sha256"],
                    assets::sha256(source.as_bytes())
                );
            }
        }
    }
}
