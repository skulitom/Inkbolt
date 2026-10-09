//! Explicit local workspace defaults and checked runtime paths, not an OS sandbox.
use crate::{Error, schema};
use serde_json::{Value, json};
use std::{
    fs,
    path::{Component, Path, PathBuf},
};

#[derive(Clone, Debug)]
pub struct Workspace {
    root: PathBuf,
}

fn invalid(message: &str) -> Error {
    Error::new("INVALID_PATH", message)
}

fn lexical(path: &Path) -> Result<(), Error> {
    if path.as_os_str().is_empty() || path.as_os_str().len() > 4096 {
        return Err(invalid("Workspace paths require 1..4096 characters"));
    }
    for component in path.components() {
        match component {
            Component::ParentDir => {
                return Err(invalid(
                    "Parent traversal is not allowed in workspace paths",
                ));
            }
            Component::Normal(name) if name.to_string_lossy().contains([':', '\0']) => {
                return Err(invalid(
                    "Workspace paths cannot contain alternate streams or NUL",
                ));
            }
            #[cfg(windows)]
            Component::Prefix(prefix)
                if !matches!(
                    prefix.kind(),
                    std::path::Prefix::Disk(_) | std::path::Prefix::VerbatimDisk(_)
                ) =>
            {
                return Err(invalid("Workspace paths require a local disk"));
            }
            _ => {}
        }
    }
    Ok(())
}

impl Workspace {
    pub fn open(root: &Path) -> Result<Self, Error> {
        lexical(root)?;
        if !root.is_absolute() {
            return Err(invalid("Workspace root must be absolute"));
        }
        let root = fs::canonicalize(root).map_err(|_| {
            Error::new(
                "IO_ERROR",
                "Workspace directory does not exist or is inaccessible",
            )
        })?;
        if !root.is_dir() {
            return Err(invalid("Workspace root must be a directory"));
        }
        Ok(Self { root })
    }

    pub fn root(&self) -> &Path {
        &self.root
    }

    /// Resolve the nearest existing ancestor, including links, before appending missing leaves.
    pub fn resolve(&self, path: &Path) -> Result<PathBuf, Error> {
        lexical(path)?;
        if path.has_root() && !path.is_absolute() {
            return Err(invalid(
                "Drive-relative and root-relative paths are not supported",
            ));
        }
        #[cfg(windows)]
        if matches!(path.components().next(), Some(Component::Prefix(_))) && !path.is_absolute() {
            return Err(invalid("Drive-relative paths are not supported"));
        }
        let joined = if path.is_absolute() {
            path.to_owned()
        } else {
            self.root.join(path)
        };
        let mut ancestor = joined.as_path();
        let mut missing = Vec::new();
        let mut resolved = loop {
            match fs::symlink_metadata(ancestor) {
                Ok(_) => {
                    break fs::canonicalize(ancestor)
                        .map_err(|_| Error::new("IO_ERROR", "Unable to resolve workspace path"))?;
                }
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                    missing.push(
                        ancestor
                            .file_name()
                            .ok_or_else(|| invalid("Workspace path has no existing ancestor"))?
                            .to_owned(),
                    );
                    ancestor = ancestor
                        .parent()
                        .ok_or_else(|| invalid("Workspace path has no existing ancestor"))?;
                }
                Err(_) => return Err(Error::new("IO_ERROR", "Unable to inspect workspace path")),
            }
        };
        if !resolved.starts_with(&self.root) {
            return Err(Error::new(
                "PATH_OUTSIDE_WORKSPACE",
                "Resolved path is outside the selected workspace",
            ));
        }
        for part in missing.into_iter().rev() {
            resolved.push(part);
        }
        Ok(resolved)
    }

    pub fn default_root(&self, field: &str, command: &str) -> Option<PathBuf> {
        let relative = match field {
            "session_root" => ".inkbolt/sessions",
            "asset_root" => ".inkbolt/assets",
            "font_root" => ".inkbolt/fonts",
            "store_root" if command == "font.import" => ".inkbolt/fonts",
            "store_root" => ".inkbolt/assets",
            "output_root" => ".",
            _ => return None,
        };
        Some(self.root.join(relative))
    }

    pub fn description(&self) -> Value {
        json!({"root":self.root, "defaults":{"session_root":".inkbolt/sessions", "asset_root":".inkbolt/assets", "font_root":".inkbolt/fonts", "image_store_root":".inkbolt/assets", "font_store_root":".inkbolt/fonts", "output_root":"."},
            "relative_paths":true, "outside_paths":"rejected_after_link_resolution", "creates_directories":"only_when_the_underlying_write_command_requires_them", "sandbox":false})
    }
}

const PATH_FIELDS: &[&str] = &[
    "file_path",
    "source_path",
    "recipe_path",
    "license_path",
    "cancel_file",
    "session_root",
    "store_root",
    "asset_root",
    "font_root",
    "output_root",
    "link_root",
];

/// Walk only fields declared by a request schema. Metadata and retained document data stay literal.
pub(crate) fn normalize(
    value: &mut Value,
    node: &Value,
    workspace: &Workspace,
    command: &str,
    depth: usize,
) -> Result<(), Error> {
    if depth > 128 {
        return Err(Error::new(
            "RESOURCE_LIMIT",
            "Workspace argument nesting exceeds limits",
        ));
    }
    if let Some(reference) = node
        .get("$ref")
        .and_then(Value::as_str)
        .and_then(|r| r.strip_prefix("#/$defs/"))
    {
        if reference == "Document" {
            return Ok(());
        }
        return normalize(
            value,
            &schema::full()["$defs"][reference],
            workspace,
            command,
            depth + 1,
        );
    }
    if let Some(choices) = node
        .get("oneOf")
        .or_else(|| node.get("anyOf"))
        .and_then(Value::as_array)
    {
        for choice in choices {
            let compatible = choice
                .get("properties")
                .and_then(Value::as_object)
                .is_none_or(|p| {
                    p.iter().all(|(name, s)| {
                        s.get("const")
                            .is_none_or(|constant| value.get(name) == Some(constant))
                    })
                });
            if compatible {
                normalize(value, choice, workspace, command, depth + 1)?;
            }
        }
    }
    if let (Some(object), Some(properties)) = (
        value.as_object_mut(),
        node.get("properties").and_then(Value::as_object),
    ) {
        for (name, definition) in properties {
            if PATH_FIELDS.contains(&name.as_str()) {
                if !object.contains_key(name)
                    && let Some(default) = workspace.default_root(name, command)
                {
                    object.insert(name.clone(), json!(default));
                }
                if let Some(Value::String(path)) = object.get(name) {
                    let resolved = workspace.resolve(Path::new(path)).map_err(|mut e| {
                        e.message = format!("{name}: {}", e.message);
                        e
                    })?;
                    object.insert(name.clone(), json!(resolved));
                }
            } else if let Some(child) = object.get_mut(name) {
                normalize(child, definition, workspace, command, depth + 1)?;
            }
        }
    }
    if let (Some(values), Some(items)) = (value.as_array_mut(), node.get("items")) {
        for child in values {
            normalize(child, items, workspace, command, depth + 1)?;
        }
    }
    Ok(())
}

pub(crate) fn describe(schema: &mut Value) {
    match schema {
        Value::Object(object) => {
            if let Some(Value::Array(required)) = object.get_mut("required") {
                required.retain(|name| {
                    !matches!(
                        name.as_str(),
                        Some("session_root" | "store_root" | "output_root")
                    )
                });
            }
            if let Some(Value::Object(properties)) = object.get_mut("properties") {
                for (field, definition) in properties {
                    if PATH_FIELDS.contains(&field.as_str())
                        && let Some(d) = definition.as_object_mut()
                    {
                        d.insert("description".into(), json!("Runtime path relative to the selected workspace, or an absolute path inside it. Omitted session, image/font store and output roots use documented workspace defaults; explicit null retains optional-root semantics."));
                    }
                }
            }
            for child in object.values_mut() {
                describe(child);
            }
        }
        Value::Array(values) => values.iter_mut().for_each(describe),
        _ => {}
    }
}
