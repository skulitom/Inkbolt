//! Reject unconverted layout controls before creating an editable point frame.
use super::{text_data::Node, *};

fn coordinates(v: &Value, expected: [f64; 2]) -> bool {
    v.as_array()
        .is_some_and(|v| v.len() == 2 && v.iter().zip(expected).all(|(v, n)| v.as_f64() == Some(n)))
}

pub(super) fn keys(v: &Value, allowed: &[&str]) -> Result<(), Error> {
    let fields = v.as_object().ok_or_else(malformed)?;
    if fields.keys().any(|k| !allowed.contains(&k.as_str())) {
        return Err(unsupported(
            "Native text contains an unmapped layout or inheritance field",
        ));
    }
    Ok(())
}
pub(super) fn node_keys(v: &Node, allowed: &[&str]) -> Result<(), Error> {
    node_keys_at(v, allowed, "global text container")
}
fn node_keys_at(v: &Node, allowed: &[&str], location: &str) -> Result<(), Error> {
    let Node::Dictionary(fields) = v else {
        return Err(malformed());
    };
    let unknown = fields
        .keys()
        .filter(|k| !allowed.contains(&k.as_str()))
        .collect::<Vec<_>>();
    if !unknown.is_empty() {
        return Err(unsupported(&format!(
            "Unmapped authoring or geometry fields in {location}: {} ({} total)",
            serde_json::to_string(
                &unknown
                    .iter()
                    .take(crate::limits::layered_text::MAX_BRIEF_FIELDS)
                    .collect::<Vec<_>>()
            )
            .unwrap(),
            unknown.len()
        )));
    }
    Ok(())
}
pub(super) fn local(parsed: &Value) -> Result<(), Error> {
    keys(parsed, &["EngineDict", "ResourceDict"])?;
    let e = &parsed["EngineDict"];
    keys(
        e,
        &[
            "Editor",
            "StyleRun",
            "ParagraphRun",
            "Rendered",
            "AntiAlias",
            "UseFractionalGlyphWidths",
        ],
    )?;
    keys(&e["Editor"], &["Text"])?;
    // Rendering controls are separately reconciled and explicitly converted.
    for (table, sheet, data) in [
        ("StyleRun", "StyleSheet", "StyleSheetData"),
        ("ParagraphRun", "ParagraphSheet", "Properties"),
    ] {
        let r = &e[table];
        keys(r, &["RunArray", "RunLengthArray", "DefaultRunData"])?;
        if let Some(default) = r.get("DefaultRunData") {
            keys(default, &[sheet])?;
            keys(&default[sheet], &[data, "DefaultStyleSheet"])?;
            keys(&default[sheet][data], &[])?;
            if default[sheet]
                .get("DefaultStyleSheet")
                .is_some_and(|v| v != 0)
            {
                return Err(unsupported("Inherited paragraph styles are unsupported"));
            }
        }
        for run in r["RunArray"].as_array().ok_or_else(malformed)? {
            keys(run, &[sheet])?;
            keys(&run[sheet], &[data, "DefaultStyleSheet"])?;
            if run[sheet].get("DefaultStyleSheet").is_some_and(|v| v != 0) {
                return Err(unsupported("Inherited paragraph styles are unsupported"));
            }
        }
    }
    let rendered = &e["Rendered"];
    keys(rendered, &["Version", "Shapes"])?;
    if rendered["Version"] != 1 {
        return Err(unsupported("Unknown local text geometry version"));
    }
    let shapes = &rendered["Shapes"];
    keys(shapes, &["WritingDirection", "Children"])?;
    let children = shapes["Children"].as_array().ok_or_else(malformed)?;
    if shapes["WritingDirection"] != 0 || children.len() != 1 {
        return Err(unsupported("Point text needs one horizontal frame"));
    }
    let child = &children[0];
    keys(child, &["ShapeType", "Procession", "Lines", "Cookie"])?;
    if child["ShapeType"] != 0 || child["Procession"] != 0 {
        return Err(unsupported(
            "Only unthreaded horizontal point text is reconstructed",
        ));
    }
    keys(&child["Lines"], &["WritingDirection", "Children"])?;
    if child["Lines"]["WritingDirection"] != 0 || child["Lines"]["Children"] != json!([]) {
        return Err(unsupported(
            "Unmapped local line-layout records cannot be reconstructed",
        ));
    }
    let cookies = child["Cookie"].as_object().ok_or_else(malformed)?;
    if cookies.len() != 1 {
        return Err(unsupported(
            "Point text requires one explicit geometry owner",
        ));
    }
    let cookie = cookies.values().next().unwrap();
    keys(cookie, &["ShapeType", "PointBase", "Base"])?;
    if cookie["ShapeType"] != 0 || !coordinates(&cookie["PointBase"], [0.0, 0.0]) {
        return Err(unsupported("Unmapped point-text origin"));
    }
    let base = &cookie["Base"];
    keys(
        base,
        &[
            "ShapeType",
            "TransformPoint0",
            "TransformPoint1",
            "TransformPoint2",
        ],
    )?;
    if base["ShapeType"] != 0
        || !coordinates(&base["TransformPoint0"], [1.0, 0.0])
        || !coordinates(&base["TransformPoint1"], [0.0, 1.0])
        || !coordinates(&base["TransformPoint2"], [0.0, 0.0])
    {
        return Err(unsupported(
            "Separate local text transforms require a verified composition mapping",
        ));
    }
    let r = &parsed["ResourceDict"];
    keys(
        r,
        &[
            "FontSet",
            "TheNormalStyleSheet",
            "TheNormalParagraphSheet",
            "StyleSheetSet",
            "ParagraphSheetSet",
        ],
    )?;
    for key in ["TheNormalStyleSheet", "TheNormalParagraphSheet"] {
        if r.get(key).is_some_and(|v| v != 0) {
            return Err(unsupported(
                "Inherited text resource styles are unsupported",
            ));
        }
    }
    for font in r["FontSet"].as_array().ok_or_else(malformed)? {
        keys(font, &["Name", "Script", "FontType", "Synthetic"])?;
        if ["Script", "Synthetic"]
            .iter()
            .any(|key| font.get(key).is_some_and(|v| v != 0))
            || font.get("FontType").is_some_and(|v| v != 1)
        {
            return Err(unsupported(
                "Unmapped native font script, kind or synthetic style",
            ));
        }
    }
    // A supplied normal resource may repeat the first explicit run. It cannot
    // introduce hidden inherited controls that the editable model would lose.
    for (table, run, sheet, field) in [
        ("StyleSheetSet", "StyleRun", "StyleSheet", "StyleSheetData"),
        (
            "ParagraphSheetSet",
            "ParagraphRun",
            "ParagraphSheet",
            "Properties",
        ),
    ] {
        if let Some(entries) = r.get(table) {
            let entries = entries.as_array().ok_or_else(malformed)?;
            if entries.len() != 1 {
                return Err(unsupported(
                    "Native inherited style tables require a separate mapping",
                ));
            }
            keys(&entries[0], &["Name", "DefaultStyleSheet", field])?;
            if entries[0][field] != e[run]["RunArray"][0][sheet][field]
                || entries[0].get("DefaultStyleSheet").is_some_and(|v| v != 0)
            {
                return Err(unsupported(
                    "A native default resource differs from its explicit first style run",
                ));
            }
        }
    }
    Ok(())
}

pub(super) fn global(global: &Node, story: &Node) -> Result<(usize, usize), Error> {
    node_keys_at(global, &["98", "0", "1"], "global root /")?;
    node_keys_at(global.field("98")?, &["0"], "global version /98")?;
    node_keys_at(global.field("1")?, &["1", "2", "3"], "global authoring /1")?;
    let resources = global.field("0")?;
    node_keys_at(resources, &["1", "5", "6", "8"], "global resources /0")?;
    for key in ["5", "6"] {
        if let Some(table) = resources.optional(key)? {
            // Auxiliary table arrays have not been admitted as editable data.
            node_keys_at(table, &["0"], "named text style table")?;
        }
    }
    node_keys(story, &["0", "1"])?;
    node_keys_at(
        story.field("0")?,
        &["0", "5", "6", "10"],
        "selected story authoring",
    )?;
    let layout = story.field("1")?;
    node_keys_at(layout, &["0"], "selected story layout")?;
    let refs = layout.field("0")?.array()?;
    if refs.len() != 1 {
        return Err(unsupported(
            "Editable point text requires one frame per story",
        ));
    }
    node_keys(&refs[0], &["0"])?;
    let index = refs[0].field("0")?.unsigned()?;
    let table = resources.field("8")?;
    node_keys(table, &["0"])?;
    let frames = table.field("0")?.array()?;
    let frame = frames.get(index).ok_or_else(malformed)?;
    node_keys(frame, &["0"])?;
    let shape = frame.field("0")?;
    node_keys(shape, &["2"])?;
    // Empty point geometry is meaningful: the record matrix locates its baseline.
    // Explicit separate transforms, rectangles and first-baseline overrides need
    // their own import mappings, even when structurally valid diagnostics exist.
    node_keys(shape.field("2")?, &[])?;
    Ok((index, frames.len()))
}
