//! Original local layered RGB interchange; no embedded engine snapshot.
mod binary;
mod descriptor;
mod mask;
mod metadata;
mod object_write;
mod objects;
mod read;
mod write;
use crate::{Document, Error, assets, control::Control, model::*};
use base64::{Engine, engine::general_purpose::STANDARD};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::path::Path;
pub const MAX_FILE_BYTES: usize = 32 * 1024 * 1024;
pub const MAX_DECODED_BYTES: usize = 8 * 1024 * 1024;
pub const MAX_CANVAS_PIXELS: usize = 1_048_576;

/// Explicit conversion of native embedded placements to retained engine objects.
/// Reconstruction and source sharing can differ from the originating consumer.
#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct EmbeddedObjects {
    pub sampling: assets::Sampling,
    pub sharing: ObjectSharing,
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum ObjectSharing {
    IndependentCopies,
}

/// Explicit acceptance of reconstruction differences in the receiving consumer.
#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum ObjectDelivery {
    NativeReconstruction,
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ExportOptions {
    pub embedded_objects: Option<ObjectDelivery>,
}

#[derive(Default)]
struct DecodeBudget {
    pixels: usize,
    items: usize,
    snapshot_bytes: usize,
}

#[derive(Default)]
struct EncodeBudget {
    pixels: usize,
    items: usize,
    source_bytes: usize,
}
struct Encoding<'a> {
    options: &'a ExportOptions,
    control: &'a Control,
    budget: &'a mut EncodeBudget,
    depth: usize,
    scope: String,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Version {
    #[default]
    Standard,
    Large,
}
impl Version {
    pub fn number(self) -> u16 {
        match self {
            Self::Standard => 1,
            Self::Large => 2,
        }
    }
    pub fn maximum_dimension(self) -> u32 {
        match self {
            Self::Standard => 30000,
            Self::Large => MAX_DIMENSION,
        }
    }
    fn read(number: u16) -> Result<Self, Error> {
        match number {
            1 => Ok(Self::Standard),
            2 => Ok(Self::Large),
            _ => Err(unsupported("Unknown layered file version")),
        }
    }
}

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Compression {
    Raw,
    #[default]
    Rle,
}
fn malformed() -> Error {
    Error::new(
        "INVALID_LAYERED_FILE",
        "Layered document has invalid framing, channel data or contradictory records",
    )
}
fn unsupported(message: &str) -> Error {
    Error::new("UNSUPPORTED_LAYERED_SEMANTICS", message)
}
fn size(width: u32, height: u32, max: usize, version: Version) -> Result<usize, Error> {
    if width == 0
        || height == 0
        || width > version.maximum_dimension()
        || height > version.maximum_dimension()
    {
        return Err(unsupported(&format!(
            "Layered dimensions must be positive and at most {} for this version within current engine limits",
            version.maximum_dimension()
        )));
    }
    let n = width as usize * height as usize;
    if n > max {
        return Err(limit(
            "Layered pixel count exceeds its bounded canvas or retained-source limit",
        ));
    }
    Ok(n)
}
pub fn import(
    source: &Path,
    expected_sha256: Option<&str>,
    id: String,
    color_policy: assets::ColorPolicy,
    control: &Control,
) -> Result<Value, Error> {
    import_with_objects(source, expected_sha256, id, color_policy, None, control)
}
pub fn import_with_objects(
    source: &Path,
    expected_sha256: Option<&str>,
    id: String,
    color_policy: assets::ColorPolicy,
    embedded_objects: Option<EmbeddedObjects>,
    control: &Control,
) -> Result<Value, Error> {
    control.check()?;
    assets::absolute(source)?;
    let bytes = assets::read_bounded(source, MAX_FILE_BYTES as u64)?;
    let hash = assets::sha256(&bytes);
    if expected_sha256.is_some_and(|v| v != hash) {
        return Err(Error::new(
            "SOURCE_MISMATCH",
            "Layered source bytes do not match the declared SHA-256",
        ));
    }
    let mut result = decode_with_objects(&bytes, id, color_policy, embedded_objects, control)?;
    result["source_sha256"] = json!(hash);
    result["source_bytes"] = json!(bytes.len());
    result["source_changed"] = json!(false);
    Ok(result)
}
pub fn decode(
    bytes: &[u8],
    id: String,
    color_policy: assets::ColorPolicy,
    control: &Control,
) -> Result<Value, Error> {
    decode_with_objects(bytes, id, color_policy, None, control)
}
pub fn decode_with_objects(
    bytes: &[u8],
    id: String,
    color_policy: assets::ColorPolicy,
    embedded_objects: Option<EmbeddedObjects>,
    control: &Control,
) -> Result<Value, Error> {
    if bytes.len() > MAX_FILE_BYTES {
        return Err(limit("Layered input exceeds 32 MiB"));
    }
    control.check()?;
    read::document(
        bytes,
        id,
        color_policy,
        embedded_objects,
        control,
        0,
        &mut DecodeBudget::default(),
    )
}
pub fn export(
    document: &Document,
    compression: Compression,
    control: &Control,
) -> Result<Value, Error> {
    export_versioned(document, compression, Version::Standard, control)
}

pub fn export_versioned(
    document: &Document,
    compression: Compression,
    version: Version,
    control: &Control,
) -> Result<Value, Error> {
    export_with_options(
        document,
        compression,
        version,
        &ExportOptions::default(),
        control,
    )
}

pub fn export_with_options(
    document: &Document,
    compression: Compression,
    version: Version,
    options: &ExportOptions,
    control: &Control,
) -> Result<Value, Error> {
    write::document(
        document,
        compression,
        version,
        &mut Encoding {
            options,
            control,
            budget: &mut EncodeBudget::default(),
            depth: 0,
            scope: "root".into(),
        },
    )
}
