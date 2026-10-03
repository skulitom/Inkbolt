use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

pub const MAX_REQUEST_BYTES: u64 = 1024 * 1024;
pub const MAX_DIMENSION: u32 = 32768;

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum DocumentKind {
    Vector,
    Raster,
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ColorSpace {
    Srgb,
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Document {
    pub schema_version: u32,
    pub id: String,
    pub kind: DocumentKind,
    pub width: u32,
    pub height: u32,
    pub color_space: ColorSpace,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(tag = "command", deny_unknown_fields)]
pub enum Request {
    #[serde(rename = "capabilities")]
    Capabilities {},
    #[serde(rename = "schema")]
    Schema {},
    #[serde(rename = "document.create")]
    Create {
        id: String,
        kind: DocumentKind,
        width: u32,
        height: u32,
    },
    #[serde(rename = "document.validate")]
    Validate { document: Document },
}

#[derive(Debug, Serialize)]
pub struct Error {
    pub code: &'static str,
    pub message: String,
}

impl Error {
    pub fn new(code: &'static str, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
        }
    }
}

pub fn validate(document: &Document) -> Result<(), Error> {
    if document.schema_version != 1 {
        return Err(Error::new(
            "INVALID_DOCUMENT",
            "Unsupported document schema version",
        ));
    }
    if document.id.is_empty()
        || document.id.len() > 128
        || !document
            .id
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || b"._-".contains(&c))
    {
        return Err(Error::new(
            "INVALID_DOCUMENT",
            "ID must contain 1-128 ASCII letters, digits, dots, hyphens or underscores",
        ));
    }
    if !(1..=MAX_DIMENSION).contains(&document.width)
        || !(1..=MAX_DIMENSION).contains(&document.height)
    {
        return Err(Error::new(
            "INVALID_DOCUMENT",
            "Width and height must each be in 1..=32768 pixels",
        ));
    }
    Ok(())
}

pub fn execute(request: Request) -> Result<Value, Error> {
    match request {
        Request::Capabilities {} => Ok(json!({
            "name": "inkbolt", "version": env!("CARGO_PKG_VERSION"),
            "stage": "foundation", "document_schema_version": 1,
            "commands": ["capabilities", "schema", "document.create", "document.validate"],
            "document_kinds": ["vector", "raster"],
            "limits": {"request_bytes": MAX_REQUEST_BYTES, "dimension_pixels": MAX_DIMENSION},
            "features": {"empty_documents": true, "editing": false, "rendering": false,
                "native_import": false, "sessions": false, "mcp_stdio": false}
        })),
        Request::Schema {} => Ok(json!(schemars::schema_for!(Request))),
        Request::Create {
            id,
            kind,
            width,
            height,
        } => {
            let document = Document {
                schema_version: 1,
                id,
                kind,
                width,
                height,
                color_space: ColorSpace::Srgb,
            };
            validate(&document)?;
            Ok(json!(document))
        }
        Request::Validate { document } => {
            validate(&document)?;
            Ok(json!(document))
        }
    }
}
