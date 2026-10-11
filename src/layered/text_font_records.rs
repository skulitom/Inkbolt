//! Source font provenance is not a font-file identity or a lookup instruction.
use super::{text_data::Node, text_inheritance::Run, *};
use std::collections::BTreeSet;

pub(super) const MAX_RECORDS: usize = 256;
pub(super) const MAX_SELECTED: usize = 8;
pub(super) const MAX_VERSION_BYTES: usize = 512;

fn known(node: &Node, keys: &[&str]) -> Result<bool, Error> {
    let Node::Dictionary(values) = node else {
        return Err(malformed());
    };
    Ok(values.keys().all(|key| keys.contains(&key.as_str())))
}

fn record(node: &Node, index: usize) -> Result<(Value, bool), Error> {
    let font = node.field("0")?;
    let properties = font.field("0")?;
    let class = font
        .optional("99")?
        .map(|value| match value {
            Node::Name(name) => Ok(name == "CoolTypeFont"),
            _ => Err(malformed()),
        })
        .transpose()?;
    let face_name = super::text_style::face_name(properties.field("0")?.text()?)?;
    let technology = properties.optional("2")?.map(Node::unsigned).transpose()?;
    let version = properties.optional("5")?.map(Node::text).transpose()?;
    if let Some(version) = version {
        if version.is_empty() {
            return Err(malformed());
        }
        if version.len() > MAX_VERSION_BYTES {
            return Err(limit("Source font version exceeds 512 UTF-8 bytes"));
        }
    }
    let supported = known(node, &["0"])?
        && known(font, &["0", "99"])?
        && known(properties, &["0", "2", "5"])?
        && class != Some(false)
        && technology.is_none_or(|code| code <= 1);
    Ok((
        json!({"index":index,"face_name":face_name,"class_declared":class.is_some(),
            "technology_code":technology,"version":version,"metadata_supported":supported}),
        supported,
    ))
}

pub(super) fn read(
    table: &Node,
    runs: &[Run<'_>],
    strict: bool,
    control: &Control,
) -> Result<Value, Error> {
    let fonts = table.field("0")?.array()?;
    if fonts.len() > MAX_RECORDS {
        return Err(limit("Global text exceeds 256 source font records"));
    }
    let mut selected = BTreeSet::new();
    for run in runs {
        control.check()?;
        let properties = run.fields.as_ref().ok_or_else(malformed)?;
        selected.insert(properties.get("0").ok_or_else(malformed)?.unsigned()?);
    }
    if selected.len() > MAX_SELECTED {
        return Err(limit("Selected text exceeds eight source font records"));
    }
    let mut supported = known(table, &["0"])?;
    let mut records = Vec::new();
    for index in &selected {
        control.check()?;
        let (value, valid) = record(fonts.get(*index).ok_or_else(malformed)?, *index)?;
        supported &= valid;
        records.push(value);
    }
    if strict {
        // Editable admission checks unused declarations too; diagnostics only
        // describe records referenced by this selected story.
        for (index, font) in fonts.iter().enumerate() {
            control.check()?;
            if !selected.contains(&index) {
                supported &= record(font, index)?.1;
            }
        }
        if !supported {
            return Err(unsupported(
                "Unmapped source font class, technology or properties",
            ));
        }
    }
    Ok(
        json!({"font_table_records":fonts.len(),"selected_records":records,
        "selected_metadata_supported":supported,"all_table_records_validated":strict,
        "source_font_file_identity_declared":false,"chosen_font_version_checked":false,
        "system_font_lookup":false,"technology_interpreted_as_outline_format":false}),
    )
}
