//! Original editable-vector container and source interpretation.
mod artwork;
mod boards;
mod pdf_read;
mod tokens;
use crate::{Error, control::Control};
use std::io::Read;
pub const MAX_SOURCE_BYTES: usize = 16 * 1024 * 1024;
pub const MAX_DECODED_BYTES: usize = 16 * 1024 * 1024;
pub const MAX_BLOCKS: usize = 256;
#[derive(Debug, serde::Deserialize, schemars::JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum ColorPolicy {
    EncodedSrgb,
}
pub fn import(
    id: String,
    source_path: &std::path::Path,
    _color_policy: ColorPolicy,
    profile: crate::model::ResourceProfile,
    control: &Control,
) -> Result<serde_json::Value, Error> {
    control.check()?;
    control.check_path(source_path)?;
    if profile == crate::model::ResourceProfile::LargeRaster {
        return Err(Error::new(
            "INVALID_REQUEST",
            "Native vector import requires a vector resource profile",
        ));
    }
    let file = std::fs::File::open(source_path)
        .map_err(|e| Error::new("VECTOR_IO", format!("Cannot open vector source: {e}")))?;
    if !file
        .metadata()
        .map_err(|e| Error::new("VECTOR_IO", e.to_string()))?
        .is_file()
    {
        return Err(Error::new(
            "VECTOR_IO",
            "Vector source must be a regular file",
        ));
    }
    let mut bytes = Vec::new();
    file.take(MAX_SOURCE_BYTES as u64 + 1)
        .read_to_end(&mut bytes)
        .map_err(|e| Error::new("VECTOR_IO", e.to_string()))?;
    let decoded = decode(&bytes, control)?;
    let mut result = artwork::read(&decoded.data, id, profile, control)?;
    result["source"] = serde_json::json!({"sha256":crate::assets::sha256(&bytes),"bytes":bytes.len(),"decoded_sha256":crate::assets::sha256(&decoded.data),"decoded_bytes":decoded.data.len(),"preview_pages":decoded.pages,"blocks":decoded.blocks,"container_version":12,"roundtrip_version":24,"creator_version":decoded.creator_version,"compression":if decoded.compressed{"zstandard"}else{"none"},"modified":false});
    result["color_policy"] = serde_json::json!("caller_declared_encoded_srgb");
    result["losses"] = serde_json::json!([
        "RGB numbers use the caller's explicit encoded-sRGB interpretation; source color profiles and application color-management settings are not imported.",
        "Unused setup resources, editor display settings and export preferences remain in the unchanged source file; no preview artwork is used.",
        "Native appearance is rendered by the engine; matching geometry does not establish identical external antialiasing or compositing quantization.",
        "Native file delivery and complete native interoperability remain unimplemented. Retain the source file and editable snapshot."
    ]);
    control.check()?;
    Ok(result)
}
pub(crate) fn invalid(message: &str) -> Error {
    Error::new("INVALID_VECTOR_SOURCE", message)
}
pub(crate) fn unsupported(message: &str) -> Error {
    Error::new("UNSUPPORTED", message)
}
pub(crate) fn limit(message: &str) -> Error {
    Error::new("RESOURCE_LIMIT", message)
}

pub struct Decoded {
    pub data: Vec<u8>,
    pub pages: usize,
    pub blocks: usize,
    pub creator_version: usize,
    pub compressed: bool,
}
/// Validate framing before interpreting editable artwork. Preview streams are never interpreted.
pub fn decode(bytes: &[u8], control: &Control) -> Result<Decoded, Error> {
    if bytes.len() > MAX_SOURCE_BYTES {
        return Err(limit("Native vector source exceeds 16 MiB"));
    }
    let pdf = pdf_read::Container::read(bytes, control)?;
    let (container, pages) = pdf.editable()?;
    let number = |key: &[u8]| pdf.resolve(pdf_read::field(container, key)?)?.integer();
    if number(b"ContainerVersion")? != 12 || number(b"RoundtripVersion")? != 24 {
        return Err(unsupported("Unsupported editable-vector container version"));
    }
    let creator_version = number(b"CreatorVersion")?;
    if creator_version != 30 {
        return Err(unsupported("Native creator version has not been verified"));
    }
    let blocks = number(b"NumBlock")?;
    if !(1..=MAX_BLOCKS).contains(&blocks) {
        return Err(limit("Native vector block count exceeds budget"));
    }
    let compressed = match container.get(b"RoundtripStreamType".as_slice()) {
        Some(v) if pdf.resolve(v)?.integer()? == 2 => true,
        None => false,
        _ => return Err(unsupported("Unsupported native vector compression kind")),
    };
    let mut known: std::collections::BTreeSet<Vec<u8>> = [
        b"ContainerVersion".as_slice(),
        b"RoundtripVersion",
        b"CreatorVersion",
        b"NumBlock",
        b"AIMetaData",
        b"RoundtripStreamType",
    ]
    .iter()
    .map(|v| v.to_vec())
    .collect();
    let mut encoded = Vec::new();
    for n in 1..=blocks {
        control.check()?;
        let key = format!("AIPrivateData{n}").into_bytes();
        let part = pdf.stream(
            pdf_read::field(container, &key)?,
            MAX_SOURCE_BYTES - encoded.len(),
            control,
        )?;
        encoded.extend(part);
        known.insert(key);
    }
    if container.keys().any(|key| !known.contains(key)) {
        return Err(unsupported("Unknown editable-vector container field"));
    }
    let metadata = pdf.stream(pdf_read::field(container, b"AIMetaData")?, 65536, control)?;
    let data = if compressed {
        let source = encoded
            .strip_prefix(b"%AI24_ZStandard_Data")
            .ok_or_else(|| invalid("Invalid native compression prefix"))?;
        if !source.starts_with(&[0x28, 0xb5, 0x2f, 0xfd]) || source.len() < 5 {
            return Err(invalid("Expected one native compression frame"));
        }
        let mut decoder = ruzstd::decoding::StreamingDecoder::new_with_max_window_size(
            source,
            MAX_DECODED_BYTES as u64,
        )
        .map_err(|_| invalid("Invalid native compression frame"))?;
        let declared_size = (source[4] & 0xe0 != 0).then(|| decoder.decoder.content_size());
        if declared_size.is_some_and(|n| n > MAX_DECODED_BYTES as u64) {
            return Err(limit("Declared native frame size exceeds 16 MiB"));
        }
        let mut data = Vec::new();
        let mut buffer = [0u8; 16384];
        loop {
            control.check()?;
            let n = decoder
                .read(&mut buffer)
                .map_err(|_| invalid("Invalid compressed native data"))?;
            if n == 0 {
                break;
            }
            if data.len() + n > MAX_DECODED_BYTES {
                return Err(limit("Decoded native vector exceeds 16 MiB"));
            }
            data.extend_from_slice(&buffer[..n]);
        }
        if !decoder.decoder.is_finished() || declared_size.is_some_and(|n| n != data.len() as u64) {
            return Err(invalid("Native compression size or completion mismatch"));
        }
        if let Some(checksum) = decoder.decoder.get_checksum_from_data()
            && Some(checksum) != decoder.decoder.get_calculated_checksum()
        {
            return Err(invalid("Native compression checksum mismatch"));
        }
        if !decoder.into_inner().is_empty() {
            return Err(invalid("Trailing native compression frames or bytes"));
        }
        data
    } else {
        encoded
    };
    if !data.starts_with(b"%!PS-") || metadata.is_empty() || !data.starts_with(&metadata) {
        return Err(invalid(
            "Native editable stream and metadata header disagree",
        ));
    }
    control.check()?;
    Ok(Decoded {
        data,
        pages,
        blocks,
        creator_version,
        compressed,
    })
}
