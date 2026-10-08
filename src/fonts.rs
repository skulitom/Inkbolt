//! Explicit pinned local font resources and their retained license text.
use crate::{
    Error, assets,
    model::{invalid, limit},
};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use std::{
    collections::BTreeMap,
    fs::{self, OpenOptions},
    io::Write,
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
};
pub const MAX_FONT_BYTES: u64 = 8 * 1024 * 1024;
pub const MAX_FONTS: usize = 8;
pub const MAX_LICENSE_BYTES: u64 = 65536;
pub const MAX_AXES: usize = 16;
pub const MAX_FEATURES: usize = 64;
pub type Coordinates = BTreeMap<String, f64>;
static TEMP: AtomicU64 = AtomicU64::new(0);

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Font {
    pub sha256: String,
    pub license_sha256: String,
    pub face_index: u32,
    pub bytes: u64,
}
pub type Cache = BTreeMap<String, Vec<u8>>;
pub fn valid_hash(s: &str) -> bool {
    s.len() == 64
        && s.bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}
pub fn validate(font: &Font) -> Result<(), Error> {
    if !valid_hash(&font.sha256) || !valid_hash(&font.license_sha256) {
        return Err(invalid(
            "Font and license identities must be lowercase SHA-256 hex",
        ));
    }
    if !(1..=MAX_FONT_BYTES).contains(&font.bytes) || font.face_index > 255 {
        return Err(limit("Font descriptor exceeds byte or face-index limits"));
    }
    Ok(())
}
fn face(bytes: &[u8], index: u32) -> Result<rustybuzz::Face<'_>, Error> {
    let face = rustybuzz::Face::from_slice(bytes, index).ok_or_else(|| {
        Error::new(
            "INVALID_FONT",
            "Font does not contain a readable requested SFNT face",
        )
    })?;
    for tag in [b"COLR", b"CBDT", b"sbix", b"SVG "] {
        if face
            .raw_face()
            .table(rustybuzz::ttf_parser::Tag::from_bytes(tag))
            .is_some()
        {
            return Err(Error::new(
                "UNSUPPORTED",
                "Color, SVG and bitmap font artwork is unsupported; select a monochrome outline font",
            ));
        }
    }
    let tables = face.tables();
    if tables.glyf.is_none() && tables.cff.is_none() && tables.cff2.is_none() {
        return Err(Error::new(
            "UNSUPPORTED",
            "Text requires scalable outline glyphs",
        ));
    }
    Ok(face)
}
struct Temporary(PathBuf);
impl Drop for Temporary {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.0);
    }
}
fn publish(root: &Path, digest: &str, suffix: &str, bytes: &[u8]) -> Result<bool, Error> {
    fs::create_dir_all(root)
        .map_err(|_| Error::new("IO_ERROR", "Unable to create explicit font root"))?;
    let target = root.join(format!("{digest}.{suffix}"));
    if target
        .try_exists()
        .map_err(|_| Error::new("IO_ERROR", "Unable to inspect font store"))?
    {
        load_blob(root, digest, suffix, bytes.len() as u64)?;
        return Ok(false);
    }
    for _ in 0..64 {
        let p = root.join(format!(
            ".inkbolt-font-{}-{}.tmp",
            std::process::id(),
            TEMP.fetch_add(1, Ordering::Relaxed)
        ));
        let mut f = match OpenOptions::new().create_new(true).write(true).open(&p) {
            Ok(f) => f,
            Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(_) => {
                return Err(Error::new(
                    "IO_ERROR",
                    "Unable to reserve temporary font resource",
                ));
            }
        };
        let temp = Temporary(p);
        f.write_all(bytes)
            .and_then(|_| f.sync_all())
            .map_err(|_| Error::new("IO_ERROR", "Unable to write immutable font resource"))?;
        drop(f);
        return match fs::hard_link(&temp.0, &target) {
            Ok(()) => Ok(true),
            Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => {
                load_blob(root, digest, suffix, bytes.len() as u64)?;
                Ok(false)
            }
            Err(_) => Err(Error::new(
                "FONT_STORE_ERROR",
                "Font root must support create-only hard-link publication",
            )),
        };
    }
    Err(Error::new(
        "FONT_STORE_ERROR",
        "Font store temporary-name retry limit exceeded",
    ))
}
fn load_blob(root: &Path, digest: &str, suffix: &str, max: u64) -> Result<Vec<u8>, Error> {
    let p = root.join(format!("{digest}.{suffix}"));
    let m = fs::symlink_metadata(&p).map_err(|e| {
        if e.kind() == std::io::ErrorKind::NotFound {
            Error::new("FONT_MISSING", "Pinned font or retained license is missing")
        } else {
            Error::new("IO_ERROR", "Unable to inspect font resource")
        }
    })?;
    if !m.is_file() || m.file_type().is_symlink() {
        return Err(Error::new(
            "FONT_CORRUPT",
            "Font resource must be a regular non-symlink file",
        ));
    }
    let bytes = assets::read_bounded(&p, max)?;
    if assets::sha256(&bytes) != digest {
        return Err(Error::new(
            "FONT_CORRUPT",
            "Font resource does not match its pinned identity",
        ));
    }
    Ok(bytes)
}
pub fn import(source: &Path, license: &Path, root: &Path, index: u32) -> Result<Font, Error> {
    assets::absolute(source)?;
    assets::absolute(license)?;
    assets::absolute(root)?;
    let bytes = assets::read_bounded(source, MAX_FONT_BYTES)?;
    face(&bytes, index)?;
    let license = assets::read_bounded(license, MAX_LICENSE_BYTES)?;
    if std::str::from_utf8(&license).map_or(true, |s| s.trim().is_empty()) {
        return Err(Error::new(
            "INVALID_FONT_LICENSE",
            "Retained license must be nonempty UTF-8 text",
        ));
    }
    let font = Font {
        sha256: assets::sha256(&bytes),
        license_sha256: assets::sha256(&license),
        face_index: index,
        bytes: bytes.len() as u64,
    };
    validate(&font)?;
    publish(root, &font.license_sha256, "license", &license)?;
    publish(root, &font.sha256, "font", &bytes)?;
    Ok(font)
}
pub fn load(font: &Font, root: Option<&Path>) -> Result<Vec<u8>, Error> {
    validate(font)?;
    let root = root.ok_or_else(|| {
        Error::new(
            "FONT_ROOT_REQUIRED",
            "Text requires an explicit local font root",
        )
    })?;
    assets::absolute(root)?;
    let bytes = load_blob(root, &font.sha256, "font", font.bytes)?;
    if bytes.len() as u64 != font.bytes {
        return Err(Error::new(
            "FONT_CORRUPT",
            "Font length does not match its descriptor",
        ));
    }
    let license = load_blob(root, &font.license_sha256, "license", MAX_LICENSE_BYTES)?;
    if std::str::from_utf8(&license).map_or(true, |s| s.trim().is_empty()) {
        return Err(Error::new(
            "INVALID_FONT_LICENSE",
            "Retained license must be nonempty UTF-8 text",
        ));
    }
    face(&bytes, font.face_index)?;
    Ok(bytes)
}
pub fn resolve(document: &crate::Document, root: Option<&Path>) -> Result<Cache, Error> {
    resolve_story(document, root, None)
}
pub(crate) fn resolve_story(
    document: &crate::Document,
    root: Option<&Path>,
    extra: Option<&str>,
) -> Result<Cache, Error> {
    let mut cache = Cache::new();
    let styles: Vec<_> = document
        .items
        .iter()
        .filter_map(|item| match &item.content {
            crate::model::Content::Text { frame } => Some(frame.as_ref()),
            _ => None,
        })
        .flat_map(crate::text::styles)
        .chain(
            document
                .stories
                .iter()
                .filter(|(id, _)| {
                    extra == Some(id.as_str())
                        || document
                            .items
                            .iter()
                            .any(|item| crate::text::flow::uses(&item.content, id))
                })
                .flat_map(|(_, s)| s.styles()),
        )
        .collect();
    for style in &styles {
        for id in style.font_ids() {
            if !cache.contains_key(id) {
                let descriptor = document
                    .fonts
                    .get(id)
                    .ok_or_else(|| invalid("Text refers to an undefined font"))?;
                cache.insert(
                    id.clone(),
                    load(descriptor, root).map_err(|e| e.at_font(id))?,
                );
            }
        }
    }
    for style in styles {
        for (id, values) in &style.font_variations {
            instance(&document.fonts[id], &cache[id], Some(values)).map_err(|e| e.at_font(id))?;
        }
    }
    Ok(cache)
}
pub fn parsed<'a>(font: &Font, bytes: &'a [u8]) -> Result<rustybuzz::Face<'a>, Error> {
    face(bytes, font.face_index)
}

pub fn tag(value: &str) -> Result<rustybuzz::ttf_parser::Tag, Error> {
    let bytes: [u8; 4] = value
        .as_bytes()
        .try_into()
        .map_err(|_| invalid("Font axis and feature tags require four printable ASCII bytes"))?;
    if !bytes.iter().all(|b| (0x20..=0x7e).contains(b)) {
        return Err(invalid(
            "Font axis and feature tags require four printable ASCII bytes",
        ));
    }
    Ok(rustybuzz::ttf_parser::Tag::from_bytes(&bytes))
}

pub fn validate_coordinates(values: &Coordinates) -> Result<(), Error> {
    if values.len() > MAX_AXES {
        return Err(limit("Font instance exceeds 16 axis controls"));
    }
    for (key, value) in values {
        tag(key)?;
        if !value.is_finite() {
            return Err(invalid("Font axis coordinates must be finite"));
        }
    }
    Ok(())
}

pub fn instance<'a>(
    font: &Font,
    bytes: &'a [u8],
    values: Option<&Coordinates>,
) -> Result<rustybuzz::Face<'a>, Error> {
    let mut face = parsed(font, bytes)?;
    if let Some(values) = values {
        validate_coordinates(values)?;
        if !values.is_empty() {
            let tables = face.tables();
            for (tag, parsed) in [
                (b"avar", tables.avar.is_some()),
                (b"gvar", tables.gvar.is_some()),
                (b"HVAR", tables.hvar.is_some()),
                (b"MVAR", tables.mvar.is_some()),
            ] {
                if face
                    .raw_face()
                    .table(rustybuzz::ttf_parser::Tag::from_bytes(tag))
                    .is_some()
                    && !parsed
                {
                    return Err(Error::new(
                        "UNSUPPORTED",
                        "Font contains an unreadable or unsupported variation table",
                    ));
                }
            }
        }
        if !values.is_empty() && face.variation_axes().len() as usize > MAX_AXES {
            return Err(limit("Controlled variable fonts may have at most 16 axes"));
        }
        for (key, value) in values {
            let tag = tag(key)?;
            let axis = face
                .variation_axes()
                .into_iter()
                .find(|a| a.tag == tag)
                .ok_or_else(|| {
                    Error::new(
                        "FONT_AXIS_UNAVAILABLE",
                        format!("Font has no {key} variation axis"),
                    )
                })?;
            if *value < axis.min_value as f64 || *value > axis.max_value as f64 {
                return Err(Error::new(
                    "FONT_AXIS_RANGE",
                    format!(
                        "Axis {key} must be in {}..={}",
                        axis.min_value, axis.max_value
                    ),
                ));
            }
            face.set_variation(tag, *value as f32).ok_or_else(|| {
                Error::new("UNSUPPORTED", "Font instance coordinates cannot be applied")
            })?;
        }
    }
    Ok(face)
}

pub fn feature_tags(face: &rustybuzz::Face<'_>) -> std::collections::BTreeSet<String> {
    let mut result = std::collections::BTreeSet::new();
    for table in face.tables().gsub.iter().chain(face.tables().gpos.iter()) {
        result.extend(table.features.into_iter().map(|f| f.tag.to_string()));
    }
    if face.tables().kern.is_some() {
        result.insert("kern".into());
    }
    result
}

pub fn has_feature(face: &rustybuzz::Face<'_>, key: &str) -> Result<bool, Error> {
    let tag = tag(key)?;
    Ok((key == "kern" && face.tables().kern.is_some())
        || face
            .tables()
            .gsub
            .iter()
            .chain(face.tables().gpos.iter())
            .any(|table| table.features.find(tag).is_some()))
}

pub fn inspect(
    font: &Font,
    root: Option<&Path>,
    values: &Coordinates,
) -> Result<serde_json::Value, Error> {
    let bytes = load(font, root)?;
    let face = instance(font, &bytes, Some(values))?;
    let axes: Vec<_> = face.variation_axes().into_iter().enumerate().map(|(i,a)| {
        let tag = a.tag.to_string();
        serde_json::json!({"tag":tag,"minimum":a.min_value,"default":a.def_value,"maximum":a.max_value,
            "requested":values.get(&tag),"effective_user_coordinate":values.get(&tag).map_or(a.def_value,|v|*v as f32),
            "normalized_coordinate":face.variation_coordinates().get(i).map(|v|v.get() as f64/16384.0),
            "name_id":a.name_id})
    }).collect();
    Ok(
        serde_json::json!({"font":font,"units_per_em":face.units_per_em(),"glyph_count":face.number_of_glyphs(),
        "axes":axes,"feature_tags":feature_tags(&face),"ascender":face.ascender(),"descender":face.descender(),
        "line_gap":face.line_gap(),"coordinate_precision":"f32_user_to_font_normalized_f2dot14",
        "feature_scope":"font_tags;applicability_depends_on_script_language_and_glyph_sequence"}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn nonfinite_axis_coordinates_are_rejected_before_font_access() {
        for value in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            assert!(validate_coordinates(&BTreeMap::from([("wght".into(), value)])).is_err());
        }
        assert!(validate_coordinates(&BTreeMap::from([("weight".into(), 400.0)])).is_err());
    }
}
