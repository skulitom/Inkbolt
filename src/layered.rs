//! Original local layered RGB interchange; no embedded engine snapshot.
mod binary;
mod descriptor;
mod mask;
mod metadata;
mod native;
mod object_write;
mod objects;
mod read;
mod rows;
mod text_data;
mod text_font_records;
mod text_fonts;
mod text_frame;
mod text_import;
mod text_import_geometry;
mod text_import_style;
mod text_inheritance;
mod text_language;
mod text_paint;
mod text_paragraph;
mod text_preset_records;
mod text_record;
mod text_rendering;
mod text_story;
mod text_style;
mod text_write;
mod write;
pub use crate::limits::layered::MAX_CANVAS_PIXELS;
pub use crate::limits::layered::MAX_DECODED_BYTES;
pub use crate::limits::layered::MAX_FILE_BYTES;
use crate::{Document, Error, assets, control::Control, model::*};
use base64::{Engine, engine::general_purpose::STANDARD};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::path::Path;
pub use text_fonts::{TextFontBinding, TextFonts, TextImportReconstruction, TextImportRendering};

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
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct TextDelivery {
    pub reconstruction: TextReconstruction,
    /// Consumer's geometry-extension identifier, supplied explicitly as data.
    pub shape_owner: String,
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum TextReconstruction {
    NativeLayout,
}
#[derive(Clone, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ExportOptions {
    pub embedded_objects: Option<ObjectDelivery>,
    pub text: Option<TextDelivery>,
}

#[derive(Default)]
struct DecodeBudget {
    pixels: usize,
    retained_pixels: usize,
    items: usize,
    snapshot_bytes: usize,
    native: Option<native::Import>,
}

/// Explicit native storage and canvas admission. Legacy import functions retain inline limits.
#[derive(Clone, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ImportOptions {
    pub embedded_objects: Option<EmbeddedObjects>,
    pub text_fonts: Option<TextFonts>,
    pub storage: Option<crate::sample_import::NativeStore>,
    #[serde(default)]
    pub resource_profile: ResourceProfile,
}

#[derive(Default)]
struct EncodeBudget {
    pixels: usize,
    items: usize,
    source_bytes: usize,
    native_fonts: std::collections::BTreeMap<String, (String, u32)>,
}
struct Encoding<'a> {
    options: &'a ExportOptions,
    control: &'a Control,
    budget: &'a mut EncodeBudget,
    depth: usize,
    scope: String,
    font_root: Option<&'a Path>,
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
            Self::Standard => crate::limits::layered::MAX_STANDARD_DIMENSION,
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
    import_with_text_fonts(
        source,
        expected_sha256,
        id,
        color_policy,
        embedded_objects,
        None,
        control,
    )
}
pub fn import_with_text_fonts(
    source: &Path,
    expected_sha256: Option<&str>,
    id: String,
    color_policy: assets::ColorPolicy,
    embedded_objects: Option<EmbeddedObjects>,
    text_fonts: Option<&TextFonts>,
    control: &Control,
) -> Result<Value, Error> {
    import_with_options(
        source,
        expected_sha256,
        id,
        color_policy,
        &ImportOptions {
            embedded_objects,
            text_fonts: text_fonts.cloned(),
            ..Default::default()
        },
        control,
    )
}
pub fn import_with_options(
    source: &Path,
    expected_sha256: Option<&str>,
    id: String,
    color_policy: assets::ColorPolicy,
    options: &ImportOptions,
    control: &Control,
) -> Result<Value, Error> {
    control.check()?;
    let text_fonts = options.text_fonts.as_ref();
    let mut budget = DecodeBudget {
        native: native::Import::new(options, control)?,
        ..Default::default()
    };
    if let Some(fonts) = text_fonts {
        fonts.validate()?;
    }
    assets::absolute(source)?;
    let bytes = assets::read_bounded(source, MAX_FILE_BYTES as u64)?;
    let hash = assets::sha256(&bytes);
    if expected_sha256.is_some_and(|v| v != hash) {
        return Err(Error::new(
            "SOURCE_MISMATCH",
            "Layered source bytes do not match the declared SHA-256",
        ));
    }
    let mut result = read::document(
        &bytes,
        id,
        color_policy,
        read::Options {
            embedded_objects: options.embedded_objects,
            text_fonts,
            native: options.storage.is_some(),
            resource_profile: options.resource_profile,
        },
        control,
        0,
        &mut budget,
    )
    .map_err(|mut error| {
        if let Some(fonts) = text_fonts
            && let Some(details) = &mut error.details
            && details["kind"] == "native_text_requirements"
        {
            match fonts.diagnose(details, control) {
                Ok(report) => details["font_bindings"] = report,
                Err(binding_error) => return binding_error,
            }
        }
        error
    })?;
    result["source_sha256"] = json!(hash);
    result["source_bytes"] = json!(bytes.len());
    result["source_changed"] = json!(false);
    if let Some(native) = budget.native {
        result["storage"] = native.publish(options.storage.as_ref().unwrap(), control)?;
    }
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
        return Err(limit(&format!(
            "Layered input exceeds {} MiB",
            MAX_FILE_BYTES / (1024 * 1024)
        )));
    }
    control.check()?;
    read::document(
        bytes,
        id,
        color_policy,
        read::Options {
            embedded_objects,
            text_fonts: None,
            native: false,
            resource_profile: ResourceProfile::Standard,
        },
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
    export_with_fonts(document, compression, version, options, None, control)
}
pub fn export_with_fonts(
    document: &Document,
    compression: Compression,
    version: Version,
    options: &ExportOptions,
    font_root: Option<&Path>,
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
            font_root,
        },
    )
}
