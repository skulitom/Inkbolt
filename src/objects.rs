//! Retained editable snapshots with explicit, optimistic local link refresh.
use crate::{Error, assets, model::*, scene};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{cell::Cell, fs::File, io::Read, path::Path};

pub const MAX_NESTING: usize = 4;
pub const MAX_RENDERED_OBJECTS: usize = 32;
thread_local! { static PARSE_DEPTH: Cell<usize> = const { Cell::new(0) }; }
struct ParseGuard;
impl Drop for ParseGuard {
    fn drop(&mut self) {
        PARSE_DEPTH.set(PARSE_DEPTH.get() - 1);
    }
}
fn one() -> u32 {
    1
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Link {
    pub key: String,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Object {
    pub snapshot: String,
    pub sha256: String,
    pub width: f64,
    pub height: f64,
    #[serde(default)]
    pub sampling: assets::Sampling,
    #[serde(default = "one")]
    pub surface_scale: u32,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub view: Option<crate::hdr::View>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub link: Option<Link>,
}
fn invalid(message: &str) -> Error {
    Error::new("INVALID_OBJECT", message)
}
fn key(value: &str) -> Result<(), Error> {
    let stem = value.split('.').next().unwrap_or("").to_ascii_uppercase();
    if !valid_id(value)
        || !value.as_bytes()[0].is_ascii_alphanumeric()
        || value.ends_with('.')
        || ["CON", "PRN", "AUX", "NUL"].contains(&stem.as_str())
        || (stem.len() == 4
            && (stem.starts_with("COM") || stem.starts_with("LPT"))
            && matches!(stem.as_bytes()[3], b'1'..=b'9'))
    {
        return Err(invalid(
            "Object link keys require a portable, flat ASCII filename",
        ));
    }
    Ok(())
}
fn parse(snapshot: &str) -> Result<Document, Error> {
    if snapshot.len() > MAX_DOCUMENT_BYTES {
        return Err(limit("Retained object snapshot exceeds 768 KiB"));
    }
    if PARSE_DEPTH.get() >= MAX_NESTING {
        return Err(limit("Retained object nesting exceeds four levels"));
    }
    PARSE_DEPTH.set(PARSE_DEPTH.get() + 1);
    let _guard = ParseGuard;
    let d: Document = serde_json::from_value(crate::mcp::strict_value(snapshot)?)
        .map_err(|_| invalid("Object source must be an editable engine snapshot"))?;
    validate(&d)?;
    Ok(d)
}
impl Object {
    pub fn document(&self) -> Result<Document, Error> {
        if assets::sha256(self.snapshot.as_bytes()) != self.sha256 {
            return Err(Error::new(
                "OBJECT_HASH_MISMATCH",
                "Retained object source bytes do not match their identity",
            ));
        }
        if let Some(link) = &self.link {
            key(&link.key)?;
        }
        if [self.width, self.height]
            .iter()
            .any(|v| !v.is_finite() || !(0.001..=MAX_COORDINATE).contains(v))
            || !(1..=4).contains(&self.surface_scale)
        {
            return Err(invalid(
                "Object dimensions require 0.001..=32768; surface scale requires 1..=4",
            ));
        }
        if let Some(view) = self.view {
            view.validate()?;
        }
        let d = parse(&self.snapshot)?;
        if self.view.is_some() && !crate::hdr::linear(&d) {
            return Err(invalid("Object display views require a linear HDR source"));
        }
        Ok(d)
    }
    pub fn geometry(&self) -> Geometry {
        Geometry::Rect {
            x: 0.0,
            y: 0.0,
            width: self.width,
            height: self.height,
        }
    }
    pub fn summary(&self) -> Value {
        json!({"sha256":self.sha256,"source_bytes":self.snapshot.len(),"width":self.width,"height":self.height,"sampling":self.sampling,"surface_scale":self.surface_scale,"view":self.view,"link":self.link,"source":"retained_editable_snapshot","render":"retained_source_never_implicit_external_refresh"})
    }
}
pub(crate) fn validate_placement(
    object: &Object,
    parent: &Document,
    world: Matrix,
) -> Result<(), Error> {
    let d = object.document()?;
    if parent.kind != DocumentKind::Raster {
        return Err(invalid(
            "Retained objects currently require a raster parent document",
        ));
    }
    if crate::hdr::linear(&d) && !crate::hdr::linear(parent) && object.view.is_none() {
        return Err(Error::new(
            "HDR_VIEW_REQUIRED",
            "A linear object in an encoded parent requires an explicit object view",
        ));
    }
    validate_world_geometry(&object.geometry(), world)
}
fn read(path: &Path) -> Result<String, Error> {
    let file = File::open(path)
        .map_err(|_| Error::new("OBJECT_SOURCE_MISSING", "Object source cannot be opened"))?;
    let metadata = file
        .metadata()
        .map_err(|_| invalid("Object source metadata is unavailable"))?;
    if !metadata.is_file() {
        return Err(invalid("Object sources must be regular files"));
    }
    if metadata.len() > MAX_DOCUMENT_BYTES as u64 {
        return Err(limit("Object source exceeds 768 KiB"));
    }
    let mut bytes = Vec::new();
    file.take(MAX_DOCUMENT_BYTES as u64 + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| invalid("Object source could not be read"))?;
    if bytes.len() > MAX_DOCUMENT_BYTES {
        return Err(limit("Object source exceeds 768 KiB"));
    }
    String::from_utf8(bytes).map_err(|_| invalid("Object snapshot must be UTF-8"))
}
fn linked(root: &Path, name: &str) -> Result<String, Error> {
    key(name)?;
    let root = root
        .canonicalize()
        .map_err(|_| Error::new("OBJECT_SOURCE_MISSING", "Object link root is unavailable"))?;
    if !root.is_dir() {
        return Err(invalid("Object link root must be a directory"));
    }
    let path = root.join(name).canonicalize().map_err(|_| {
        Error::new(
            "OBJECT_SOURCE_MISSING",
            "Object link is missing or unavailable",
        )
    })?;
    if path.parent() != Some(root.as_path()) {
        return Err(Error::new(
            "OBJECT_LINK_ESCAPE",
            "Object links must resolve directly inside the explicit root",
        ));
    }
    read(&path)
}
pub fn import(
    source_path: Option<&Path>,
    snapshot: Option<&str>,
    link_key: Option<&str>,
) -> Result<Value, Error> {
    let snapshot = match (source_path, snapshot) {
        (Some(path), None) => read(path)?,
        (None, Some(s)) if link_key.is_none() => s.to_owned(),
        _ => {
            return Err(invalid(
                "Provide exactly one source_path or snapshot; links require a file source",
            ));
        }
    };
    let d = parse(&snapshot)?;
    let object = Object {
        sha256: assets::sha256(snapshot.as_bytes()),
        snapshot,
        width: d.width as f64,
        height: d.height as f64,
        sampling: assets::Sampling::Nearest,
        surface_scale: 1,
        view: None,
        link: link_key.map(|key| Link { key: key.into() }),
    };
    object.document()?;
    Ok(
        json!({"object":object,"source_changed":false,"source_kind":d.kind,"resources":crate::metadata::manifest(&d),"losses":["Retains exact UTF-8 engine snapshot bytes. Referenced image/font stores remain external and explicitly resolved. Native third-party document parsing is separate interchange work. Rendering evaluates a bounded offscreen surface at explicit surface_scale, then reconstructs it in the parent; sources stay editable. Links are checked or refreshed only on explicit request."]}),
    )
}
fn get<'a>(d: &'a Document, id: &str) -> Result<&'a Object, Error> {
    match &d.items[scene::index(d, id)?].content {
        Content::Object { object } => Ok(object),
        _ => Err(invalid("Operation requires a retained object item")),
    }
}
pub fn open(d: &Document, id: &str) -> Result<Value, Error> {
    validate(d)?;
    let object = get(d, id)?;
    Ok(
        json!({"id":id,"snapshot":object.snapshot,"sha256":object.sha256,"document":object.document()?,"source_changed":false,"link_read":false}),
    )
}
pub fn status(d: &Document, id: &str, root: Option<&Path>) -> Result<Value, Error> {
    validate(d)?;
    let object = get(d, id)?;
    let mut result = object.summary();
    result["id"] = json!(id);
    result["retained_source_available"] = json!(true);
    result["source_changed"] = json!(false);
    result["status"] = json!(if object.link.is_some() {
        "unchecked"
    } else {
        "embedded"
    });
    if let (Some(link), Some(root)) = (&object.link, root) {
        match linked(root, &link.key) {
            Ok(bytes) => {
                let hash = assets::sha256(bytes.as_bytes());
                result["status"] = json!(if hash == object.sha256 {
                    "current"
                } else {
                    "changed"
                });
                result["current_sha256"] = json!(hash);
                if let Err(error) = parse(&bytes) {
                    result["status"] = json!("invalid");
                    result["error"] = json!(error);
                }
            }
            Err(error) => {
                result["status"] = json!(if error.code == "OBJECT_SOURCE_MISSING" {
                    "missing"
                } else {
                    "unavailable"
                });
                result["error"] = json!(error);
            }
        }
    }
    Ok(result)
}
pub(crate) fn replace(
    d: &mut Document,
    id: &str,
    replacement: &Object,
    keep_frame: bool,
) -> Result<Value, Error> {
    let i = scene::index(d, id)?;
    scene::check_unlocked(d, i, false)?;
    let before = get(d, id)?;
    let old = before.sha256.clone();
    let mut next = replacement.clone();
    if keep_frame {
        next.width = before.width;
        next.height = before.height;
    }
    next.document()?;
    d.items[i].content = Content::Object {
        object: Box::new(next),
    };
    Ok(
        json!({"id":id,"before_sha256":old,"after_sha256":replacement.sha256,"keep_frame":keep_frame,"external_sources_changed":false,"other_placements_changed":false}),
    )
}
pub(crate) fn refresh(
    d: &mut Document,
    id: &str,
    root: &Path,
    expected: &str,
) -> Result<Value, Error> {
    scene::check_unlocked(d, scene::index(d, id)?, false)?;
    let mut next = get(d, id)?.clone();
    let link = next
        .link
        .as_ref()
        .ok_or_else(|| invalid("Refresh requires a linked object"))?;
    let bytes = linked(root, &link.key)?;
    let hash = assets::sha256(bytes.as_bytes());
    if hash != expected {
        return Err(Error::new(
            "OBJECT_SOURCE_CONFLICT",
            "Link bytes differ from the explicitly expected source hash",
        ));
    }
    next.snapshot = bytes;
    next.sha256 = hash;
    replace(d, id, &next, true)
}
pub(crate) fn detach(d: &mut Document, id: &str) -> Result<Value, Error> {
    let mut next = get(d, id)?.clone();
    next.link = None;
    replace(d, id, &next, true)
}

#[derive(Default)]
struct Budget {
    depth: usize,
    enabled: bool,
    objects: usize,
    work: u64,
    buffers: u64,
}
thread_local! { static BUDGET: std::cell::RefCell<Budget> = std::cell::RefCell::new(Budget::default()); }
pub(crate) struct RenderGuard;
impl RenderGuard {
    pub(crate) fn enter(d: &Document) -> Result<Self, Error> {
        BUDGET.with_borrow_mut(|b| {
            if b.depth == 0 {
                b.enabled = d
                    .items
                    .iter()
                    .any(|i| matches!(i.content, Content::Object { .. }));
                b.objects = 0;
                b.work = 0;
                b.buffers = 0;
            }
            if b.depth > 0 {
                b.objects += 1;
            }
            if b.depth > MAX_NESTING || b.objects > MAX_RENDERED_OBJECTS {
                return Err(limit(
                    "Retained object render nesting or evaluation count exceeded",
                ));
            }
            b.depth += 1;
            Ok(Self)
        })
    }
}
impl Drop for RenderGuard {
    fn drop(&mut self) {
        BUDGET.with_borrow_mut(|b| b.depth -= 1);
    }
}
pub(crate) fn charge(work: u64) -> Result<(), Error> {
    BUDGET.with_borrow_mut(|b| {
        if b.enabled {
            b.work = b.work.saturating_add(work);
            if b.work > crate::render::MAX_RENDER_WORK {
                return Err(limit(
                    "Aggregate retained object evaluation exceeds render work limit",
                ));
            }
        }
        Ok(())
    })
}
pub(crate) fn charge_buffers(pixels: u64) -> Result<(), Error> {
    BUDGET.with_borrow_mut(|b| {
        if b.enabled {
            b.buffers = b.buffers.saturating_add(pixels);
            if b.buffers > crate::render::MAX_BUFFER_PIXELS {
                return Err(limit(
                    "Aggregate retained object buffers exceed the pixel budget",
                ));
            }
        }
        Ok(())
    })
}
pub(crate) fn verify_resources(
    object: &Object,
    asset_root: Option<&Path>,
    font_root: Option<&Path>,
    control: &crate::control::Control,
) -> Result<(), Error> {
    let d = object.document()?;
    for asset in d.assets.values() {
        assets::load(asset, asset_root)?;
    }
    for font in d.fonts.values() {
        crate::fonts::load(font, font_root)?;
    }
    for item in &d.items {
        verify_content_resources(&item.content, asset_root, font_root, control)?;
    }
    Ok(())
}
pub(crate) fn verify_content_resources(
    content: &Content,
    asset_root: Option<&Path>,
    font_root: Option<&Path>,
    control: &crate::control::Control,
) -> Result<(), Error> {
    control.check()?;
    match content {
        Content::Object { object } => verify_resources(object, asset_root, font_root, control)?,
        Content::StoredSamples { grid } => {
            grid.prepare(asset_root, control)?;
        }
        Content::Instance { instance } => {
            for over in instance.overrides.values() {
                if let Some(content) = &over.content {
                    verify_content_resources(content, asset_root, font_root, control)?;
                }
            }
        }
        _ => {}
    }
    Ok(())
}
pub(crate) fn sanitized(object: &mut Object, mode: crate::metadata::Mode) {
    // Publication validates the source before applying its explicit privacy policy.
    if let Ok(d) = object.document() {
        object.snapshot = serde_json::to_string(&crate::metadata::sanitized(&d, mode))
            .expect("validated snapshot serialization");
        object.sha256 = assets::sha256(object.snapshot.as_bytes());
        object.link = None;
    }
}
