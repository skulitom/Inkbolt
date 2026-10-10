//! Bounded global story/reference framing. This is preparation for editable
//! reconstruction; unknown style and layout fields are never accepted as paint.
use super::{binary::Reader, text_data::Node, *};
use std::collections::BTreeSet;

fn payload<'a>(
    tail: &Reader<'a>,
    version: Version,
    control: &Control,
) -> Result<Option<&'a [u8]>, Error> {
    let mut input = Reader::new(&tail.data[tail.at..]);
    input.section()?; // Frame, but do not interpret, the global mask record.
    let mut keys = BTreeSet::new();
    let mut found = None;
    while input.left() != 0 {
        control.check()?;
        if input.left() < 12 {
            input.zero_padding(3)?;
            break;
        }
        if keys.len() >= 512 {
            return Err(limit("Global text lookup exceeds 512 tagged records"));
        }
        let signature = input.take(4)?;
        let key: [u8; 4] = input.take(4)?.try_into().unwrap();
        super::binary::tag_signature(signature, &key, version)?;
        if !keys.insert(key) {
            return Err(malformed());
        }
        let data = input.tagged_section(&key, version)?;
        if key == *b"Txt2" {
            found = Some(data.data);
        }
        if input
            .take((4 - data.left() % 4) % 4)?
            .iter()
            .any(|&b| b != 0)
        {
            return Err(malformed());
        }
    }
    Ok(found)
}

fn runs<'a>(
    authoring: &'a Node,
    key: &str,
    boundaries: &BTreeSet<usize>,
    units: usize,
) -> Result<&'a [Node], Error> {
    let runs = authoring.field(key)?.field("0")?.array()?;
    if runs.len() > 65 {
        return Err(limit("Global text story exceeds 65 runs"));
    }
    if runs.is_empty() {
        return Err(malformed());
    }
    let mut end = 0usize;
    for run in runs {
        let length = run.field("1")?.unsigned()?;
        end = end.checked_add(length).ok_or_else(malformed)?;
        if length == 0
            || !boundaries.contains(&end)
            || !matches!(run.field("0")?, Node::Dictionary(_))
        {
            return Err(malformed());
        }
    }
    if end != units {
        return Err(malformed());
    }
    Ok(runs)
}

pub(super) fn diagnose(
    tail: &Reader<'_>,
    version: Version,
    index: i32,
    local: &str,
    control: &Control,
) -> Result<Value, Error> {
    let Some(bytes) = payload(tail, version, control)? else {
        return Ok(
            json!({"present":false,"text_source":"local_record","global_tag_framing_validated":true,
            "layout_semantics_validated":false,"other_layer_references_validated":false}),
        );
    };
    let global = super::text_data::parse_global(bytes, control)?;
    if global.field("98")?.field("0")?.unsigned()? != 14 {
        return Err(unsupported("Unknown global text-data version"));
    }
    let stories = global.field("1")?.field("1")?.array()?;
    if stories.len() > MAX_ITEMS {
        return Err(limit("Global text exceeds 256 stories"));
    }
    let index = usize::try_from(index).map_err(|_| malformed())?;
    let authoring = stories.get(index).ok_or_else(malformed)?.field("0")?;
    let source = authoring.field("0")?.text()?;
    let text = source.strip_suffix('\r').ok_or_else(malformed)?;
    if text.chars().count() > crate::text::MAX_TEXT_CHARS {
        return Err(limit("Global text story exceeds 4096 characters"));
    }
    let mut boundaries = BTreeSet::from([0]);
    let mut units = 0;
    for c in source.chars() {
        units += c.len_utf16();
        boundaries.insert(units);
    }
    let style_runs = runs(authoring, "6", &boundaries, units)?;
    let paragraph_runs = runs(authoring, "5", &boundaries, units)?;
    let fonts = global.field("0")?.field("1")?.field("0")?.array()?;
    let mut faces = BTreeSet::new();
    for run in style_runs {
        control.check()?;
        let font = run
            .field("0")?
            .field("0")?
            .field("6")?
            .field("0")?
            .unsigned()?;
        let name = fonts
            .get(font)
            .ok_or_else(malformed)?
            .field("0")?
            .field("0")?
            .field("0")?
            .text()?;
        if name.is_empty() || name.len() > 128 || !name.bytes().all(|b| (33..=126).contains(&b)) {
            return Err(unsupported(
                "Global font identity is not a bounded printable face name",
            ));
        }
        faces.insert(name);
    }
    if faces.len() > crate::fonts::MAX_FONTS {
        return Err(limit(
            "Global text story references more than eight font faces",
        ));
    }
    Ok(
        json!({"present":true,"version":14,"text_source":"global_story","story_index":index,"story_count":stories.len(),
        "text_characters":text.chars().count(),"text_utf16_units":units-1,"text_sha256":assets::sha256(text.as_bytes()),
        "local_text_matches":source==local,"font_face_names":faces,"font_file_identity_declared":false,
        "style_runs":style_runs.len(),"paragraph_runs":paragraph_runs.len(),"global_data_sha256":assets::sha256(bytes),
        "global_tag_framing_validated":true,"selected_story_run_references_validated":true,
        "other_stories_validated":false,"other_layer_references_validated":false,"layout_semantics_validated":false,
        "style_semantics_validated":false,"local_style_consistency_validated":false}),
    )
}
