//! Shared JSON preparation for CLI and stdio. The typed snapshot API remains available.
use crate::{
    Error, Request,
    control::{Control, Options},
    schema,
    sessions::{self, Resources},
    workspace::{self, Workspace},
};
use schemars::JsonSchema;
use serde::Deserialize;
use serde_json::{Value, json};
use std::path::PathBuf;

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct SavedDocument {
    pub session_id: String,
    /// Exact immutable session revision; no implicit moving head.
    pub revision: u64,
    /// Required outside a workspace; otherwise defaults to its session store.
    pub session_root: Option<PathBuf>,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct DocumentFile {
    /// A published snapshot JSON file; workspace-relative or otherwise absolute.
    pub file_path: PathBuf,
    /// SHA-256 of the exact file bytes, from a publication receipt or independent hash.
    pub sha256: String,
}

pub fn file_schema() -> Value {
    let mut schema = json!(schemars::schema_for!(DocumentFile));
    schema["properties"]["sha256"]["pattern"] = json!("^[0-9a-f]{64}$");
    schema
}

fn load_file(
    reference: DocumentFile,
    workspace: Option<&Workspace>,
    control: &Control,
    replayable: bool,
) -> Result<Value, Error> {
    if reference.sha256.len() != 64
        || !reference
            .sha256
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
    {
        return Err(invalid(
            "Document file sha256 must contain 64 lowercase hexadecimal characters",
        ));
    }
    let path = match workspace {
        Some(workspace) => workspace.resolve(&reference.file_path)?,
        None => {
            crate::assets::absolute(&reference.file_path)?;
            reference.file_path
        }
    };
    if path.as_os_str().len() > 4096 {
        return Err(Error::new(
            "RESOURCE_LIMIT",
            "Document file path exceeds 4096 characters",
        ));
    }
    let bytes =
        crate::assets::read_bounded(&path, crate::MAX_REQUEST_BYTES).map_err(|mut error| {
            if error.code == "RESOURCE_LIMIT" {
                error.message = "Document file exceeds 16 MiB".into();
            }
            error
        })?;
    // Do not restart deadlines or reread the file after checking its content identity.
    if !replayable {
        control.check()?;
    }
    if crate::assets::sha256(&bytes) != reference.sha256 {
        return Err(Error::new(
            "SOURCE_MISMATCH",
            "Document file bytes differ from the pinned sha256; inspect the source and use its intended revision",
        ));
    }
    let document = decode(&bytes).map_err(|_| {
        Error::new(
            "INVALID_DOCUMENT_FILE",
            "Document file must contain one JSON snapshot without duplicate keys",
        )
    })?;
    // References and response envelopes are never followed recursively from a file.
    serde_json::from_value::<crate::Document>(document.clone()).map_err(|_| Error::new("INVALID_DOCUMENT_FILE", "Document file must contain an inline document snapshot, not a reference or response envelope"))?;
    Ok(document)
}

pub fn reference_schema() -> Value {
    let mut schema = json!(schemars::schema_for!(SavedDocument));
    schema["properties"]["session_root"]["type"] = json!("string");
    schema["required"]
        .as_array_mut()
        .unwrap()
        .push(json!("session_root"));
    schema
}

fn invalid(message: &str) -> Error {
    Error::new("INVALID_REQUEST", message)
}

pub(crate) fn describe_arguments(schema: &mut Value) {
    if let Some(properties) = schema.get_mut("properties").and_then(Value::as_object_mut) {
        for property in properties.values_mut() {
            if property.get("$ref").and_then(Value::as_str) == Some("#/$defs/Document") {
                *property = json!({"anyOf":[property.clone(),reference_schema(),file_schema()],"description":"Inline snapshot, exact saved session revision, or snapshot file pinned by SHA-256. Saved session resource bindings are inherited unless overridden; files use explicit or workspace roots."});
            }
        }
    }
}

fn merge_resources(value: &mut Value, resources: &Resources) {
    if let Some(object) = value.as_object_mut() {
        for (name, root) in [
            ("asset_root", &resources.asset_root),
            ("font_root", &resources.font_root),
        ] {
            if !object.contains_key(name) {
                object.insert(name.into(), json!(root));
            }
        }
    }
}

fn bind(value: &mut Value, argument_schema: &Value, field: &str, resources: &Resources) {
    let nested = match field {
        "before" => Some("before_resources"),
        "after" => Some("after_resources"),
        "document" if argument_schema["properties"].get("resources").is_some() => Some("resources"),
        _ => None,
    };
    if let Some(name) = nested {
        let object = value.as_object_mut().unwrap();
        merge_resources(object.entry(name).or_insert_with(|| json!({})), resources);
    } else if field == "document" {
        for (name, root) in [
            ("asset_root", &resources.asset_root),
            ("font_root", &resources.font_root),
        ] {
            if argument_schema["properties"].get(name).is_some() && value.get(name).is_none() {
                value[name] = json!(root);
            }
        }
    }
}

pub fn execute(
    mut value: Value,
    workspace: Option<&Workspace>,
    context: &Control,
) -> Result<Value, Error> {
    if serde_json::to_vec(&value).unwrap().len() > crate::MAX_REQUEST_BYTES as usize {
        return Err(Error::new(
            "REQUEST_TOO_LARGE",
            "Engine arguments exceed 16 MiB",
        ));
    }
    let response_mode = crate::responses::take(&mut value)?;
    // Inline requests without a workspace need no generated schema or path preparation.
    let has_reference = value.as_object().is_some_and(|object| {
        object
            .values()
            .any(|field| field.get("session_id").is_some() || field.get("file_path").is_some())
    });
    if workspace.is_none() && !has_reference {
        let request = serde_json::from_value(value).map_err(|_| {
            invalid("Arguments must match the command schema; inspect schema.lookup")
        })?;
        return crate::responses::execute(request, context, response_mode);
    }
    let command = value
        .get("command")
        .and_then(Value::as_str)
        .ok_or_else(|| invalid("A command name is required"))?
        .to_owned();
    let argument_schema =
        schema::request_variant(&command).ok_or_else(|| invalid("Unknown command"))?;
    let mut context = context.in_workspace(workspace);
    if let Some(definition) = argument_schema["properties"].get("control") {
        if let Some(w) = workspace
            && let Some(options) = value.get_mut("control")
        {
            workspace::normalize(options, definition, w, &command, 0)?;
        }
        let options: Options =
            serde_json::from_value(value.get("control").cloned().unwrap_or_else(|| json!({})))
                .map_err(|_| invalid("Control must match the command schema"))?;
        context = context.scoped(&options)?;
    }
    let replayable = matches!(
        command.as_str(),
        "session.create" | "session.continue" | "session.apply" | "session.apply_proposal"
    );
    if !replayable {
        context.check()?;
    }
    // Inherit saved bindings before filling missing workspace defaults.
    let document_fields: Vec<_> = argument_schema["properties"]
        .as_object()
        .unwrap()
        .iter()
        .filter(|(_, node)| node.get("$ref").and_then(Value::as_str) == Some("#/$defs/Document"))
        .map(|(name, _)| name.clone())
        .collect();
    for field in document_fields {
        if value
            .get(&field)
            .is_some_and(|d| d.get("file_path").is_some())
        {
            let reference: DocumentFile =
                serde_json::from_value(value[&field].clone()).map_err(|_| {
                    invalid("Document file requires file_path and sha256, without extra fields")
                })?;
            value[&field] = load_file(reference, workspace, &context, replayable)?;
            continue;
        }
        if !value
            .get(&field)
            .is_some_and(|d| d.get("session_id").is_some())
        {
            continue;
        }
        if value[&field]
            .get("session_root")
            .is_some_and(Value::is_null)
        {
            return Err(invalid(
                "Saved document session_root must be a path when provided",
            ));
        }
        let reference: SavedDocument = serde_json::from_value(value[&field].clone()).map_err(|_| invalid("Saved document requires session_id, revision and an optional session_root, without extra fields"))?;
        let root = match (&reference.session_root, workspace) {
            (Some(root), Some(w)) => w.resolve(root)?,
            (Some(root), None) => root.clone(),
            (None, Some(w)) => w.resolve(&w.default_root("session_root", &command).unwrap())?,
            (None, None) => {
                return Err(invalid(
                    "Saved document session_root is required without a workspace",
                ));
            }
        };
        let state = sessions::capture(&root, &reference.session_id, reference.revision)?;
        if !replayable {
            context.check()?;
        }
        value[&field] = json!(state.document);
        bind(&mut value, argument_schema, &field, &state.resources);
    }
    if let Some(w) = workspace {
        // Missing resource containers also receive defaults; explicit null is left for type validation.
        for field in ["resources", "before_resources", "after_resources"] {
            if argument_schema["properties"].get(field).is_some() && value.get(field).is_none() {
                value[field] = json!({});
            }
        }
        workspace::normalize(&mut value, argument_schema, w, &command, 0)?;
    }
    if serde_json::to_vec(&value).unwrap().len() > crate::MAX_REQUEST_BYTES as usize {
        return Err(Error::new(
            "REQUEST_TOO_LARGE",
            "Expanded engine arguments exceed 16 MiB",
        ));
    }
    let request: Request = serde_json::from_value(value)
        .map_err(|_| invalid("Arguments must match the command schema; inspect schema.lookup"))?;
    let mut result = crate::responses::execute(request, &context, response_mode)?;
    if let Some(w) = workspace
        && command == "capabilities"
    {
        result["workspace"] = w.description();
    }
    Ok(result)
}

/// Decode exactly one request with duplicate-key protection shared with MCP.
pub fn decode(bytes: &[u8]) -> Result<Value, Error> {
    if bytes.len() > crate::MAX_REQUEST_BYTES as usize {
        return Err(Error::new("REQUEST_TOO_LARGE", "Request exceeds 16 MiB"));
    }
    std::str::from_utf8(bytes)
        .ok()
        .and_then(|text| crate::mcp::strict_value(text).ok())
        .ok_or_else(|| invalid("Expected one request matching the command schema"))
}
