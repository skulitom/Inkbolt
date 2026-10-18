//! Original descriptive records, privacy policy and deterministic delivery envelopes.
use crate::limits::metadata as bounds;
use crate::{Document, Error, ExportFormat, assets, model::limit};
use base64::{Engine, engine::general_purpose::STANDARD};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::{BTreeMap, HashSet};
use std::io::{Cursor, Read, Seek, SeekFrom};

pub use crate::limits::metadata::MAX_DOCUMENT_BYTES;
pub use crate::limits::metadata::MAX_PACKET_BYTES;
pub use crate::limits::metadata::MAX_RECORD_BYTES;
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
    if value.len() > bounds::MAX_TEXT_BYTES {
        return Err(limit(&format!(
            "Metadata text exceeds {} UTF-8 bytes",
            bounds::MAX_TEXT_BYTES
        )));
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
    if record.tags.len() > bounds::MAX_ENTRIES
        || record.properties.len() > bounds::MAX_ENTRIES
        || record.private.len() > bounds::MAX_ENTRIES
    {
        return Err(limit(&format!(
            "Metadata record exceeds {} tags or map entries",
            bounds::MAX_ENTRIES
        )));
    }
    let mut tags = HashSet::new();
    for tag in &record.tags {
        text(tag)?;
        if tag.trim().is_empty() || tag.len() > bounds::MAX_TAG_BYTES || !tags.insert(tag) {
            return Err(invalid(&format!(
                "Metadata tags must be nonempty, unique and at most {} bytes",
                bounds::MAX_TAG_BYTES
            )));
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
        return Err(limit(&format!(
            "Metadata record exceeds {} KiB",
            MAX_RECORD_BYTES / 1024
        )));
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
            return Err(limit(&format!(
                "Document descriptive metadata exceeds {} KiB",
                MAX_DOCUMENT_BYTES / 1024
            )));
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
    let stored: BTreeMap<_, _> = document
        .items
        .iter()
        .filter_map(|i| match &i.content {
            crate::model::Content::StoredSamples { grid } => Some((
                &i.id,
                json!({
            "base_manifest_sha256":grid.base.sha256,"recipe_sha256":grid.recipe_sha256(),
            "spec":grid.base.spec,"patch_count":grid.patches.len()}),
            )),
            _ => None,
        })
        .collect();
    if !stored.is_empty() {
        result["stored_samples"] = json!(stored);
    }
    if let Some(grid) = document.selection.as_ref().and_then(|s| s.native.as_ref()) {
        result["native_selection"] = json!({"base_manifest_sha256":grid.base.sha256,
            "spec":grid.base.spec,"nonprinting":true});
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
        return Err(limit(&format!(
            "Encoded metadata envelope exceeds {} KiB",
            MAX_PACKET_BYTES / 1024
        )));
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
        ExportFormat::Snapshot | ExportFormat::Tiff | ExportFormat::Gif | ExportFormat::Jpeg
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
        _ => unreachable!(),
    }
    if bytes.len() > crate::publish::MAX_OUTPUT_BYTES {
        return Err(limit("Image with metadata exceeds output byte limit"));
    }
    artifact["data"] = json!(STANDARD.encode(bytes));
    Ok(())
}
#[derive(Default)]
struct JpegParts {
    parts: BTreeMap<u16, Vec<u8>>,
    count: Option<u16>,
    total: usize,
}
impl JpegParts {
    fn push(&mut self, marker: u8, body: &[u8]) -> Result<(), Error> {
        if marker != 254 || !body.starts_with(JPEG_PREFIX) {
            return Ok(());
        }
        let rest = &body[JPEG_PREFIX.len()..];
        if rest.len() < 4 {
            return Err(invalid("Truncated metadata part"));
        }
        let index = u16::from_be_bytes(rest[..2].try_into().unwrap());
        let n = u16::from_be_bytes(rest[2..4].try_into().unwrap());
        self.total += rest.len() - 4;
        if self.total > MAX_PACKET_BYTES {
            return Err(limit(&format!(
                "Metadata envelope exceeds {} KiB",
                MAX_PACKET_BYTES / 1024
            )));
        }
        if n == 0
            || usize::from(n) > bounds::MAX_JPEG_PARTS
            || index == 0
            || index > n
            || self.count.is_some_and(|c| c != n)
            || self.parts.insert(index, rest[4..].to_vec()).is_some()
        {
            return Err(invalid("Inconsistent or duplicate metadata parts"));
        }
        self.count = Some(n);
        Ok(())
    }
    fn finish(self) -> Result<Option<Vec<u8>>, Error> {
        if let Some(n) = self.count {
            if self.parts.len() != usize::from(n) {
                return Err(invalid("Missing metadata part"));
            }
            Ok(Some(self.parts.into_values().flatten().collect()))
        } else {
            Ok(None)
        }
    }
}
pub fn recover(bytes: &[u8], format: &str) -> Result<Option<Value>, Error> {
    recover_reader(
        &mut Cursor::new(bytes),
        bytes.len() as u64,
        format,
        &crate::control::Control::default(),
    )
}

/// Recover bounded metadata from the same captured bytes used by the decoder.
/// PNG framing/CRC validation is the admission reader's responsibility.
pub(crate) fn recover_reader<R: Read + Seek>(
    input: &mut R,
    length: u64,
    format: &str,
    control: &crate::control::Control,
) -> Result<Option<Value>, Error> {
    control.check()?;
    let mut packet = None;
    match format {
        "jpeg" => {
            let mut at = 2u64;
            let mut parts = JpegParts::default();
            while at < length {
                control.check()?;
                input
                    .seek(SeekFrom::Start(at))
                    .map_err(|_| invalid("Truncated metadata marker"))?;
                let mut byte = [0];
                input
                    .read_exact(&mut byte)
                    .map_err(|_| invalid("Truncated metadata marker"))?;
                if byte[0] != 255 {
                    return Err(invalid("Invalid metadata marker framing"));
                }
                while byte[0] == 255 {
                    at += 1;
                    control.check()?;
                    if at >= length {
                        return Err(invalid("Truncated metadata marker"));
                    }
                    input
                        .read_exact(&mut byte)
                        .map_err(|_| invalid("Truncated metadata marker"))?;
                }
                let marker = byte[0];
                at += 1;
                if marker == 0xd9 {
                    break;
                }
                if at + 2 > length {
                    return Err(invalid("Truncated metadata size"));
                }
                let mut size = [0; 2];
                input
                    .read_exact(&mut size)
                    .map_err(|_| invalid("Truncated metadata size"))?;
                let size = u64::from(u16::from_be_bytes(size));
                if size < 2 {
                    return Err(invalid("Invalid metadata size"));
                }
                let end = at
                    .checked_add(size)
                    .filter(|end| *end <= length)
                    .ok_or_else(|| invalid("Truncated metadata payload"))?;
                // JPEG segments are independently bounded by their 16-bit length.
                if marker == 254 {
                    let mut body = vec![0; size as usize - 2];
                    input
                        .read_exact(&mut body)
                        .map_err(|_| invalid("Truncated metadata payload"))?;
                    parts.push(marker, &body)?;
                }
                at = end;
                if marker == 0xda {
                    break;
                }
            }
            packet = parts.finish()?;
        }
        "png" => {
            let mut at = 8u64;
            while at.checked_add(12).is_some_and(|end| end <= length) {
                control.check()?;
                input
                    .seek(SeekFrom::Start(at))
                    .map_err(|_| invalid("Truncated metadata chunk"))?;
                let mut header = [0; 8];
                input
                    .read_exact(&mut header)
                    .map_err(|_| invalid("Truncated metadata chunk"))?;
                let size = u64::from(u32::from_be_bytes(header[..4].try_into().unwrap()));
                let end = at
                    .checked_add(8)
                    .and_then(|v| v.checked_add(size))
                    .filter(|end| *end <= length)
                    .ok_or_else(|| invalid("Truncated metadata chunk"))?;
                let key_len = PNG_KEY.len() + 1;
                if &header[4..] == b"iTXt" && size >= key_len as u64 {
                    let mut key = vec![0; key_len];
                    input
                        .read_exact(&mut key)
                        .map_err(|_| invalid("Truncated metadata chunk"))?;
                    if key.starts_with(PNG_KEY) && key[PNG_KEY.len()] == 0 {
                        let mut fields = [0; 4];
                        if size < (key_len + fields.len()) as u64
                            || input.read_exact(&mut fields).is_err()
                            || fields != [0; 4]
                        {
                            return Err(invalid(
                                "Inkbolt metadata requires uncompressed text with empty language fields",
                            ));
                        }
                        let packet_len = size - key_len as u64 - fields.len() as u64;
                        if packet_len > MAX_PACKET_BYTES as u64 {
                            return Err(limit(&format!(
                                "Metadata envelope exceeds {} KiB",
                                MAX_PACKET_BYTES / 1024
                            )));
                        }
                        if packet.is_some() {
                            return Err(invalid("Duplicate Inkbolt metadata envelope"));
                        }
                        let mut bytes = vec![0; packet_len as usize];
                        for chunk in
                            bytes.chunks_mut(crate::limits::sample_import::INPUT_BUFFER_BYTES)
                        {
                            control.check()?;
                            input
                                .read_exact(chunk)
                                .map_err(|_| invalid("Truncated metadata chunk"))?;
                        }
                        packet = Some(bytes);
                    }
                }
                at = end + 4;
            }
        }
        "tiff" => {
            input
                .rewind()
                .map_err(|_| invalid("Invalid TIFF metadata"))?;
            let mut limits = tiff::decoder::Limits::default();
            limits.ifd_value_size = MAX_PACKET_BYTES + TEXT_PREFIX.len() + 1;
            let mut reader = tiff::decoder::Decoder::new(std::io::BufReader::with_capacity(
                crate::limits::sample_import::INPUT_BUFFER_BYTES,
                input,
            ))
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
                    packet = Some(raw.as_bytes().to_vec());
                }
            }
        }
        _ => return Ok(None),
    }
    control.check()?;
    packet.map(|packet| read_packet(&packet)).transpose()
}
pub fn read_packet(packet: &[u8]) -> Result<Value, Error> {
    if packet.len() > MAX_PACKET_BYTES {
        return Err(limit(&format!(
            "Metadata envelope exceeds {} KiB",
            MAX_PACKET_BYTES / 1024
        )));
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
        return Err(limit(&format!(
            "Metadata records exceed {} KiB",
            MAX_DOCUMENT_BYTES / 1024
        )));
    }
    Ok(
        json!({"envelope":value,"envelope_sha256":assets::sha256(packet),"trust":"untrusted_source_description_not_verified_provenance"}),
    )
}
