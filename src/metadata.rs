//! Original descriptive records, privacy policy and deterministic delivery envelopes.
use crate::{Document, Error, ExportFormat, assets, model::limit};
use base64::{Engine, engine::general_purpose::STANDARD};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::{BTreeMap, HashSet};

pub const MAX_RECORD_BYTES: usize = 16 * 1024;
pub const MAX_DOCUMENT_BYTES: usize = 64 * 1024;
pub const MAX_PACKET_BYTES: usize = 256 * 1024;
pub const PNG_KEY: &[u8] = b"Inkbolt Metadata";
pub const TEXT_PREFIX: &str = "Inkbolt metadata v1\n";
pub const JPEG_PREFIX: &[u8] = b"INKBOLT-META\0";
pub const SVG_NS: &str = "urn:inkbolt:metadata:1";

#[derive(Clone, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(default, deny_unknown_fields)]
pub struct Record {
    #[serde(skip_serializing_if = "String::is_empty")]
    pub title: String,
    #[serde(skip_serializing_if = "String::is_empty")]
    pub description: String,
    #[serde(skip_serializing_if = "String::is_empty")]
    pub author: String,
    #[serde(skip_serializing_if = "String::is_empty")]
    pub rights: String,
    #[serde(skip_serializing_if = "String::is_empty")]
    pub note: String,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub tags: Vec<String>,
    #[serde(skip_serializing_if = "BTreeMap::is_empty")]
    pub properties: BTreeMap<String, String>,
    #[serde(skip_serializing_if = "BTreeMap::is_empty")]
    pub private: BTreeMap<String, String>,
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Mode {
    #[default]
    Public,
    Strip,
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(default, deny_unknown_fields)]
pub struct Policy {
    pub mode: Mode,
    pub manifest: bool,
    pub provenance: bool,
}
fn invalid(message: &str) -> Error {
    Error::new("INVALID_METADATA", message)
}
fn text(value: &str) -> Result<(), Error> {
    if value.len() > 8192 {
        return Err(limit("Metadata text exceeds 8192 UTF-8 bytes"));
    }
    if value.chars().any(|c| {
        (c.is_control() && !matches!(c, '\n' | '\r' | '\t')) || matches!(c as u32, 0xfffe | 0xffff)
    }) {
        return Err(invalid("Metadata contains unsupported control characters"));
    }
    Ok(())
}
pub fn validate(record: &Record) -> Result<usize, Error> {
    for s in [
        &record.title,
        &record.description,
        &record.author,
        &record.rights,
        &record.note,
    ] {
        text(s)?;
    }
    if record.tags.len() > 64 || record.properties.len() > 64 || record.private.len() > 64 {
        return Err(limit("Metadata record exceeds 64 tags or map entries"));
    }
    let mut tags = HashSet::new();
    for tag in &record.tags {
        text(tag)?;
        if tag.trim().is_empty() || tag.len() > 128 || !tags.insert(tag) {
            return Err(invalid(
                "Metadata tags must be nonempty, unique and at most 128 bytes",
            ));
        }
    }
    for (key, value) in record.properties.iter().chain(record.private.iter()) {
        if !crate::model::valid_id(key) {
            return Err(invalid("Metadata property keys must be portable IDs"));
        }
        text(value)?;
    }
    let size = serde_json::to_vec(record).unwrap().len();
    if size > MAX_RECORD_BYTES {
        return Err(limit("Metadata record exceeds 16 KiB"));
    }
    Ok(size)
}
pub fn validate_document(document: &Document) -> Result<(), Error> {
    let mut bytes = 0;
    for record in document
        .metadata
        .iter()
        .chain(document.items.iter().filter_map(|i| i.metadata.as_ref()))
    {
        bytes += validate(record)?;
        if bytes > MAX_DOCUMENT_BYTES {
            return Err(limit("Document descriptive metadata exceeds 64 KiB"));
        }
    }
    Ok(())
}
fn public(record: &Option<Record>, mode: Mode) -> Option<Record> {
    if mode == Mode::Strip {
        return None;
    }
    record.as_ref().and_then(|r| {
        let mut r = r.clone();
        r.private.clear();
        (r != Record::default()).then_some(r)
    })
}
pub fn sanitized(document: &Document, mode: Mode) -> Document {
    let mut copy = document.clone();
    copy.metadata = public(&document.metadata, mode);
    for item in &mut copy.items {
        item.metadata = public(&item.metadata, mode);
        if let crate::model::Content::Object { object } = &mut item.content {
            crate::objects::sanitized(object, mode);
        }
    }
    copy
}
/// Sorted JSON object keys and no filesystem or clock inputs.
pub fn canonical<T: Serialize>(value: &T) -> Vec<u8> {
    serde_json::to_vec(&serde_json::to_value(value).unwrap()).unwrap()
}
pub fn manifest(document: &Document) -> Value {
    let images: BTreeMap<_, _> = document
        .assets
        .iter()
        .map(|(id, asset)| {
            (
                id,
                json!({"sha256":asset.sha256,"width":asset.width,"height":asset.height}),
            )
        })
        .collect();
    let fonts: BTreeMap<_, _> = document.fonts.iter().map(|(id, font)| (id, json!({"sha256":font.sha256,"byte_count":font.bytes,"face_index":font.face_index,"license_sha256":font.license_sha256}))).collect();
    let objects: BTreeMap<_, _> = document.items.iter().filter_map(|i|match &i.content { crate::model::Content::Object { object } => Some((&i.id, json!({"source_sha256":object.sha256,"resources":object.document().ok().map(|d|manifest(&d))}))), _ => None }).collect();
    let mut result = json!({"images":images,"fonts":fonts,"scope":"all_resources_in_export_view","verification":"identities_only_not_file_verification"});
    if !objects.is_empty() {
        result["objects"] = json!(objects);
    }
    result
}
pub fn packet(
    document: &Document,
    format: ExportFormat,
    scale: u32,
    policy: Policy,
) -> Result<Option<String>, Error> {
    let copy = sanitized(document, policy.mode);
    let items: BTreeMap<_, _> = copy
        .items
        .iter()
        .filter_map(|i| i.metadata.as_ref().map(|m| (&i.id, m)))
        .collect();
    if copy.metadata.is_none() && items.is_empty() && !policy.manifest && !policy.provenance {
        return Ok(None);
    }
    let ppi = document.resolution_ppi * scale as f64;
    let ppi = match format {
        ExportFormat::Png | ExportFormat::Apng => (ppi / 0.0254).round() * 0.0254,
        ExportFormat::Jpeg => ppi.round(),
        ExportFormat::Tiff => (ppi * 1000.0).round() / 1000.0,
        _ => ppi,
    };
    let mut value = json!({"schema":"inkbolt.metadata.v1","document":copy.metadata,"items":items,"delivery":{"format":format,"width":document.width as u64 * scale as u64,"height":document.height as u64 * scale as u64,"resolution_ppi":ppi,"orientation":"top_left","profile":document.output_profile.as_ref().map(crate::profiles::summary).transpose()?}});
    if let Some(canvas) = document.vector_canvas {
        value["delivery"]["width"] = json!((canvas.size_px[0] * scale as f64).ceil() as u64);
        value["delivery"]["height"] = json!((canvas.size_px[1] * scale as f64).ceil() as u64);
        value["delivery"]["vector_canvas"] = canvas.receipt(document.resolution_ppi)?;
    }
    if policy.manifest {
        value["manifest"] = manifest(document);
    }
    if policy.provenance {
        value["provenance"] = json!({"engine":"inkbolt","version":env!("CARGO_PKG_VERSION"),"source_sha256":assets::sha256(&canonical(&copy)),"source_scope":"export_view_with_applied_metadata_policy","revision":document.revision,"deterministic":true});
    }
    let raw = String::from_utf8(canonical(&value)).unwrap();
    // TIFF ASCII and all other carriers share one exact JSON packet. JSON escapes
    // preserve Unicode scalars, including supplementary-plane surrogate pairs.
    let mut ascii = String::new();
    for c in raw.chars() {
        if c.is_ascii() {
            ascii.push(c);
        } else {
            for unit in c.encode_utf16(&mut [0; 2]).iter() {
                ascii.push_str(&format!("\\u{unit:04x}"));
            }
        }
    }
    if ascii.len() > MAX_PACKET_BYTES {
        return Err(limit("Encoded metadata envelope exceeds 256 KiB"));
    }
    Ok(Some(ascii))
}
pub fn annotate(
    artifact: &mut Value,
    packet: Option<&str>,
    policy: Option<Policy>,
    snapshot: bool,
) {
    if snapshot && let Some(packet) = packet {
        // A snapshot already retains its editable records. Its optional delivery
        // envelope is returned separately, without inventing snapshot fields.
        artifact["metadata_envelope"] = serde_json::from_str(packet).unwrap();
    }
    if packet.is_some() || policy.is_some() {
        artifact["metadata"] = json!({"mode":if snapshot && policy.is_none(){"source"}else if policy.unwrap_or_default().mode==Mode::Public{"public"}else{"strip"},"private_fields":if snapshot&&policy.is_none(){"retained"}else{"removed"},"envelope_sha256":packet.map(|s|assets::sha256(s.as_bytes())),"embedded":packet.is_some()&&!snapshot,"orientation":"top_left","resolution":"document_ppi_times_scale_with_format_rounding","color":"existing_declared_output_profile_policy","scope":"descriptive_records_only_not_artwork_text_names_or_profile_contents"});
    }
}
pub fn embed(artifact: &mut Value, format: ExportFormat, packet: &str) -> Result<(), Error> {
    if matches!(
        format,
        ExportFormat::Snapshot | ExportFormat::Tiff | ExportFormat::Gif
    ) {
        return Ok(());
    }
    if matches!(format, ExportFormat::Svg) {
        let svg = artifact["data"]
            .as_str()
            .ok_or_else(|| invalid("Missing SVG output"))?;
        let at = svg.find('>').ok_or_else(|| invalid("Missing SVG root"))? + 1;
        let escaped = packet
            .replace('&', "&amp;")
            .replace('<', "&lt;")
            .replace('>', "&gt;");
        artifact["data"] = json!(format!(
            "{}<metadata><inkbolt xmlns=\"{}\">{}</inkbolt></metadata>{}",
            &svg[..at],
            SVG_NS,
            escaped,
            &svg[at..]
        ));
        if artifact["data"].as_str().unwrap().len() > crate::publish::MAX_OUTPUT_BYTES {
            return Err(limit("SVG with metadata exceeds output byte limit"));
        }
        return Ok(());
    }
    let mut bytes = STANDARD
        .decode(artifact["data"].as_str().unwrap())
        .map_err(|_| invalid("Invalid image output"))?;
    match format {
        ExportFormat::Png | ExportFormat::Apng => {
            let mut payload = PNG_KEY.to_vec();
            payload.extend_from_slice(&[0; 5]);
            payload.extend_from_slice(packet.as_bytes());
            let mut chunk = (payload.len() as u32).to_be_bytes().to_vec();
            chunk.extend_from_slice(b"iTXt");
            chunk.extend_from_slice(&payload);
            chunk.extend_from_slice(&crc32fast::hash(&chunk[4..]).to_be_bytes());
            bytes.splice(bytes.len() - 12..bytes.len() - 12, chunk);
        }
        ExportFormat::Jpeg => {
            let segments = jpeg_segments(&bytes)?;
            let at = segments
                .iter()
                .find(|s| s.0 == 0xda)
                .map(|s| s.1)
                .ok_or_else(|| invalid("Missing JPEG scan"))?;
            let count = packet.len().div_ceil(60000);
            let mut comments = Vec::new();
            for (i, part) in packet.as_bytes().chunks(60000).enumerate() {
                let len = 2 + JPEG_PREFIX.len() + 4 + part.len();
                comments.extend_from_slice(&[255, 254]);
                comments.extend_from_slice(&(len as u16).to_be_bytes());
                comments.extend_from_slice(JPEG_PREFIX);
                comments.extend_from_slice(&((i + 1) as u16).to_be_bytes());
                comments.extend_from_slice(&(count as u16).to_be_bytes());
                comments.extend_from_slice(part);
            }
            bytes.splice(at..at, comments);
        }
        _ => unreachable!(),
    }
    if bytes.len() > crate::publish::MAX_OUTPUT_BYTES {
        return Err(limit("Image with metadata exceeds output byte limit"));
    }
    artifact["data"] = json!(STANDARD.encode(bytes));
    Ok(())
}
type Segment<'a> = (u8, usize, &'a [u8]);
fn jpeg_segments(bytes: &[u8]) -> Result<Vec<Segment<'_>>, Error> {
    let mut at = 2;
    let mut result = Vec::new();
    while at < bytes.len() {
        let start = at;
        if bytes[at] != 255 {
            return Err(invalid("Invalid metadata marker framing"));
        }
        while bytes.get(at) == Some(&255) {
            at += 1;
        }
        let marker = *bytes
            .get(at)
            .ok_or_else(|| invalid("Truncated metadata marker"))?;
        at += 1;
        if marker == 0xd9 {
            break;
        }
        let n = bytes
            .get(at..at + 2)
            .ok_or_else(|| invalid("Truncated metadata size"))?;
        let n = u16::from_be_bytes(n.try_into().unwrap()) as usize;
        if n < 2 {
            return Err(invalid("Invalid metadata size"));
        }
        let payload = bytes
            .get(at + 2..at + n)
            .ok_or_else(|| invalid("Truncated metadata payload"))?;
        result.push((marker, start, payload));
        at += n;
        if marker == 0xda {
            break;
        }
    }
    Ok(result)
}
pub fn recover(bytes: &[u8], format: &str) -> Result<Option<Value>, Error> {
    let mut packets = Vec::new();
    match format {
        "png" => {
            let mut at = 8;
            while at + 12 <= bytes.len() {
                let n = u32::from_be_bytes(bytes[at..at + 4].try_into().unwrap()) as usize;
                let body = bytes
                    .get(at + 8..at + 8 + n)
                    .ok_or_else(|| invalid("Truncated metadata chunk"))?;
                if &bytes[at + 4..at + 8] == b"iTXt"
                    && body.starts_with(PNG_KEY)
                    && body.get(PNG_KEY.len()) == Some(&0)
                {
                    let rest = &body[PNG_KEY.len() + 1..];
                    if !rest.starts_with(&[0; 4]) {
                        return Err(invalid(
                            "Inkbolt metadata requires uncompressed text with empty language fields",
                        ));
                    }
                    if rest.len() - 4 > MAX_PACKET_BYTES {
                        return Err(limit("Metadata envelope exceeds 256 KiB"));
                    }
                    packets.push(rest[4..].to_vec());
                }
                at += n + 12;
            }
        }
        "jpeg" => {
            let mut parts = BTreeMap::new();
            let mut count = None;
            let mut total = 0;
            for (marker, _, body) in jpeg_segments(bytes)? {
                if marker != 254 || !body.starts_with(JPEG_PREFIX) {
                    continue;
                }
                let rest = &body[JPEG_PREFIX.len()..];
                if rest.len() < 4 {
                    return Err(invalid("Truncated metadata part"));
                }
                let index = u16::from_be_bytes(rest[..2].try_into().unwrap());
                let n = u16::from_be_bytes(rest[2..4].try_into().unwrap());
                total += rest.len() - 4;
                if total > MAX_PACKET_BYTES {
                    return Err(limit("Metadata envelope exceeds 256 KiB"));
                }
                if n == 0
                    || n > 5
                    || index == 0
                    || index > n
                    || count.is_some_and(|c| c != n)
                    || parts.insert(index, rest[4..].to_vec()).is_some()
                {
                    return Err(invalid("Inconsistent or duplicate metadata parts"));
                }
                count = Some(n);
            }
            if let Some(n) = count {
                if parts.len() != n as usize {
                    return Err(invalid("Missing metadata part"));
                }
                packets.push(parts.into_values().flatten().collect());
            }
        }
        "tiff" => {
            let mut limits = tiff::decoder::Limits::default();
            limits.ifd_value_size = MAX_PACKET_BYTES + TEXT_PREFIX.len() + 1;
            let mut reader = tiff::decoder::Decoder::new(std::io::Cursor::new(bytes))
                .map_err(|_| invalid("Invalid TIFF metadata"))?
                .with_limits(limits);
            if let Some(value) = reader
                .find_tag(tiff::tags::Tag::ImageDescription)
                .map_err(|_| invalid("Invalid TIFF description"))?
            {
                let value = value
                    .into_string()
                    .map_err(|_| invalid("TIFF description must be ASCII"))?;
                if let Some(raw) = value.strip_prefix(TEXT_PREFIX) {
                    packets.push(raw.as_bytes().to_vec());
                }
            }
        }
        _ => return Ok(None),
    }
    if packets.len() > 1 {
        return Err(invalid("Duplicate Inkbolt metadata envelope"));
    }
    packets.pop().map(|packet| read_packet(&packet)).transpose()
}
pub fn read_packet(packet: &[u8]) -> Result<Value, Error> {
    if packet.len() > MAX_PACKET_BYTES {
        return Err(limit("Metadata envelope exceeds 256 KiB"));
    }
    let value: Value =
        serde_json::from_slice(packet).map_err(|_| invalid("Invalid metadata JSON"))?;
    if value["schema"] != "inkbolt.metadata.v1" || !value.is_object() {
        return Err(invalid("Unsupported metadata envelope schema"));
    }
    if value.as_object().unwrap().keys().any(|k| {
        ![
            "schema",
            "document",
            "items",
            "delivery",
            "manifest",
            "provenance",
        ]
        .contains(&k.as_str())
    }) {
        return Err(invalid("Unknown metadata envelope field"));
    }
    let items = value["items"]
        .as_object()
        .ok_or_else(|| invalid("Metadata envelope requires an object map"))?;
    if items.len() > crate::model::MAX_LARGE_VECTOR_ITEMS {
        return Err(limit("Metadata item map exceeds document limit"));
    }
    let mut size = 0;
    for (id, record) in items
        .iter()
        .map(|(id, r)| (Some(id.as_str()), r))
        .chain(std::iter::once((None, &value["document"])))
    {
        if id.is_some_and(|id| !crate::model::valid_id(id)) {
            return Err(invalid("Invalid metadata item ID"));
        }
        if record.is_null() && id.is_none() {
            continue;
        }
        let record: Record = serde_json::from_value(record.clone())
            .map_err(|_| invalid("Invalid descriptive record"))?;
        size += validate(&record)?;
        if !record.private.is_empty() {
            return Err(invalid("Delivery envelopes cannot contain private records"));
        }
    }
    if size > MAX_DOCUMENT_BYTES {
        return Err(limit("Metadata records exceed 64 KiB"));
    }
    Ok(
        json!({"envelope":value,"envelope_sha256":assets::sha256(packet),"trust":"untrusted_source_description_not_verified_provenance"}),
    )
}
