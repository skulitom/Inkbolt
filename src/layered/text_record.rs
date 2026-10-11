//! Structural diagnostics only: native layout and font references do not yet
//! constitute a supported editable import contract.
use super::{
    binary::Reader,
    descriptor::{self, Datum},
    *,
};
use std::collections::BTreeSet;

fn object<'a>(v: &'a Value, key: &str) -> Result<&'a Value, Error> {
    let value = v.get(key).ok_or_else(malformed)?;
    if !value.is_object() {
        return Err(malformed());
    }
    Ok(value)
}
fn array<'a>(v: &'a Value, key: &str) -> Result<&'a Vec<Value>, Error> {
    v.get(key).and_then(Value::as_array).ok_or_else(malformed)
}
fn runs<'a>(engine: &'a Value, key: &str, text: &str) -> Result<&'a Vec<Value>, Error> {
    let run = object(engine, key)?;
    let values = array(run, "RunArray")?;
    let lengths = array(run, "RunLengthArray")?;
    if values.len() != lengths.len() || values.is_empty() {
        return Err(malformed());
    }
    if values.len() > 65 {
        return Err(limit("Native text exceeds 65 runs"));
    }
    let mut boundaries = BTreeSet::from([0]);
    let mut units = 0;
    for c in text.chars() {
        units += c.len_utf16();
        boundaries.insert(units);
    }
    let mut end = 0usize;
    for (value, length) in values.iter().zip(lengths) {
        let length = length
            .as_u64()
            .and_then(|n| usize::try_from(n).ok())
            .ok_or_else(malformed)?;
        end = end.checked_add(length).ok_or_else(malformed)?;
        if !value.is_object() || length == 0 || !boundaries.contains(&end) {
            return Err(malformed());
        }
    }
    if end != units {
        return Err(malformed());
    }
    Ok(values)
}
pub(super) struct Record {
    details: Value,
    source: String,
    story_index: i32,
}
pub(super) fn inspect(input: &mut Reader<'_>, control: &Control) -> Result<Record, Error> {
    if input.left() > 65536 {
        return Err(limit("Native text record exceeds 64 KiB"));
    }
    if input.short()? != 1 {
        return Err(unsupported("Unknown native text-record version"));
    }
    let mut transform = [0.0; 6];
    for n in &mut transform {
        *n = f64::from_be_bytes(input.take(8)?.try_into().unwrap());
        if !n.is_finite() {
            return Err(malformed());
        }
    }
    if input.short()? != 50 {
        return Err(unsupported("Unknown native text descriptor version"));
    }
    let mut d = descriptor::text_versioned(input, control)?;
    let text = d.field("Txt ")?.text()?;
    if text.chars().count() > crate::text::MAX_TEXT_CHARS {
        return Err(limit("Native text exceeds 4096 characters"));
    }
    let payload = match d.field("EngineData")? {
        Datum::Raw(bytes) => bytes,
        _ => return Err(malformed()),
    };
    // These descriptor fields are framed, not interpreted as engine layout.
    // Unknown fields cannot be waved through even for this narrow diagnostic.
    for key in ["textGridding", "Ornt", "AntA"] {
        if !matches!(d.field(key)?, Datum::Enum(_, _)) {
            return Err(malformed());
        }
    }
    d.field("TxMP")?.boolean()?;
    let story_index = d.field("TextIndex")?.integer()?;
    let old_text = d.optional("oldText").map(Datum::boolean).transpose()?;
    let age = match d.optional("oldTextAge") {
        Some(Datum::Enum(kind, value)) => Some(json!({"kind":kind,"value":value})),
        Some(_) => return Err(malformed()),
        None => None,
    };
    let compatibility = json!({"present":old_text.is_some() || age.is_some(),"old_text":old_text,
        "age":age,"semantics_validated":false,"trusted":false});
    for key in ["bounds", "boundingBox"] {
        if let Some(value) = d.optional(key) {
            let mut bounds = value.object()?;
            for key in ["Left", "Top ", "Rght", "Btom"] {
                if !matches!(bounds.field(key)?, Datum::Number(_) | Datum::Unit(_, _)) {
                    return Err(malformed());
                }
            }
            bounds.finish(key)?;
        }
    }
    d.finish("TxLr")?;
    if input.short()? != 1 {
        return Err(unsupported("Unknown text warp version"));
    }
    let mut warp = descriptor::versioned(input, control)?;
    for key in ["warpStyle", "warpRotate"] {
        if !matches!(warp.field(key)?, Datum::Enum(_, _)) {
            return Err(malformed());
        }
    }
    for key in ["warpValue", "warpPerspective", "warpPerspectiveOther"] {
        warp.field(key)?.number()?;
    }
    warp.finish("warp")?;
    for _ in 0..4 {
        input.signed()?;
    }
    input.zero_padding(3)?;
    let parsed = super::text_data::parse(&payload, control)?;
    let engine = object(&parsed, "EngineDict")?;
    let source = object(engine, "Editor")?
        .get("Text")
        .and_then(Value::as_str)
        .ok_or_else(malformed)?;
    if source.strip_suffix('\r') != Some(text.as_str()) {
        return Err(malformed());
    }
    let style_runs = runs(engine, "StyleRun", source)?;
    let paragraph_runs = runs(engine, "ParagraphRun", source)?;
    let fonts = array(object(&parsed, "ResourceDict")?, "FontSet")?;
    let mut referenced_fonts = BTreeSet::new();
    for run in style_runs {
        control.check()?;
        let style = object(object(run, "StyleSheet")?, "StyleSheetData")?;
        let font_index = style.get("Font").ok_or_else(|| unsupported("Native text diagnostics require explicit per-run font references; inherited styles need a layout mapping"))?;
        let index = font_index
            .as_u64()
            .and_then(|n| usize::try_from(n).ok())
            .ok_or_else(malformed)?;
        let font = fonts
            .get(index)
            .and_then(|v| v.get("Name"))
            .and_then(Value::as_str)
            .ok_or_else(malformed)?;
        if font.is_empty() || font.len() > 128 || !font.bytes().all(|b| (33..=126).contains(&b)) {
            return Err(unsupported(
                "Native font identity is not a bounded printable face name",
            ));
        }
        referenced_fonts.insert(font);
    }
    if referenced_fonts.len() > crate::fonts::MAX_FONTS {
        return Err(limit("Native text references more than eight font faces"));
    }
    // Report bounded identifiers as untrusted source data. This does not certify
    // their geometry, select an application, or make an unknown layout editable.
    let mut owners = BTreeSet::new();
    if let Some(children) = engine
        .pointer("/Rendered/Shapes/Children")
        .and_then(Value::as_array)
    {
        for child in children {
            if let Some(cookie) = child.get("Cookie").and_then(Value::as_object) {
                for key in cookie.keys() {
                    if !key.is_empty()
                        && key.len() <= 128
                        && key.bytes().all(|b| b.is_ascii_alphanumeric())
                    {
                        owners.insert(key.clone());
                    }
                }
            }
        }
    }
    let owners_truncated = owners.len() > 8;
    let owners = owners.into_iter().take(8).collect::<Vec<_>>();
    Ok(Record {
        source: source.to_owned(),
        story_index,
        details: json!({"kind":"native_text_requirements","editable_import_supported":false,
        "diagnostic_scope":"local_record_and_selected_global_story_references_and_frame_geometry_only",
        "reported_text_source":"local_record","native_story_index":story_index,
        "compatibility_markers":compatibility,
        "whole_file_validated":false,"layout_semantics_validated":false,
        "text_characters":text.chars().count(),"text_utf16_units":text.encode_utf16().count(),
        "style_runs":style_runs.len(),"paragraph_runs":paragraph_runs.len(),
        "font_face_names":referenced_fonts,"font_file_identity_declared":false,
        "shape_owner_labels":owners,"shape_owner_labels_truncated":owners_truncated,"shape_owner_labels_trusted":false,
        "transform":transform,"text_data_sha256":assets::sha256(&payload),
        "cached_pixels_used":false,"required_mapping":["explicit_content_pinned_font_bindings","global_story_and_local_style_reconciliation","editable_text_layout_reconstruction","declared_native_layout_and_rendering_differences"]}),
    })
}
pub(super) fn diagnose(
    input: &mut Reader<'_>,
    tail: &Reader<'_>,
    version: Version,
    control: &Control,
) -> Result<Value, Error> {
    let mut record = inspect(input, control)?;
    record.details["global_story"] =
        super::text_story::diagnose(tail, version, record.story_index, &record.source, control)?;
    Ok(record.details)
}
