//! Selected global frame geometry only. Unknown frame properties do not become
//! supported layout merely because their containing record is well framed.
use super::{text_data::Node, *};

fn coordinates<const N: usize>(node: &Node) -> Result<[f64; N], Error> {
    let values = node.array()?;
    if values.len() != N {
        return Err(malformed());
    }
    let mut out = [0.0; N];
    for (target, value) in out.iter_mut().zip(values) {
        *target = value.number()?;
        if target.abs() > MAX_COORDINATE {
            return Err(limit(
                "Native text frame coordinates exceed the bounded local coordinate range",
            ));
        }
    }
    Ok(out)
}

fn rectangle(node: &Node) -> Result<[f64; 4], Error> {
    if node.array()?.len() != 32 {
        return Err(unsupported(
            "Native text frame requires a separately mapped nonrectangular path",
        ));
    }
    let values = coordinates::<32>(node)?;
    let points = values.as_chunks::<2>().0;
    let mut bounds = [
        f64::INFINITY,
        f64::INFINITY,
        f64::NEG_INFINITY,
        f64::NEG_INFINITY,
    ];
    for segment in 0..4 {
        let at = 4 * segment;
        if points[at] != points[at + 1]
            || points[at + 2] != points[at + 3]
            || points[at + 3] != points[(at + 4) % 16]
        {
            return Err(unsupported(
                "Native text frame curve or disconnected boundary requires its own layout mapping",
            ));
        }
        let p = points[at];
        bounds[0] = bounds[0].min(p[0]);
        bounds[1] = bounds[1].min(p[1]);
        bounds[2] = bounds[2].max(p[0]);
        bounds[3] = bounds[3].max(p[1]);
    }
    let [x0, y0, x1, y1] = bounds;
    if !(0.001..=MAX_COORDINATE).contains(&(x1 - x0))
        || !(0.001..=MAX_COORDINATE).contains(&(y1 - y0))
    {
        return Err(unsupported(
            "Native text rectangle needs positive bounded width and height",
        ));
    }
    let corners = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]];
    for corner in corners {
        if (0..4).filter(|&i| points[4 * i] == corner).count() != 1 {
            return Err(unsupported(
                "Native text frame is not a single axis-aligned rectangle",
            ));
        }
    }
    for segment in 0..4 {
        let a = points[4 * segment];
        let b = points[(4 * segment + 4) % 16];
        if a[0] != b[0] && a[1] != b[1] {
            return Err(unsupported(
                "Native text frame has a diagonal or crossed boundary",
            ));
        }
    }
    Ok(bounds)
}

pub(super) fn diagnose(global: &Node, story: &Node) -> Result<Value, Error> {
    let Some(layout) = story.optional("1")? else {
        return Ok(
            json!({"present":false,"reason":"global_frame_reference_not_present","layout_semantics_validated":false}),
        );
    };
    let refs = layout.field("0")?.array()?;
    if refs.is_empty() {
        return Err(malformed());
    }
    if refs.len() != 1 {
        return Err(unsupported(
            "Multiple native text frames require a linked-frame layout mapping",
        ));
    }
    let frames = global.field("0")?.field("8")?.field("0")?.array()?;
    if frames.len() > MAX_ITEMS {
        return Err(limit(&format!(
            "Global text exceeds {MAX_ITEMS} frame resources"
        )));
    }
    let index = refs[0].field("0")?.unsigned()?;
    let shape = frames.get(index).ok_or_else(malformed)?.field("0")?;
    let properties = shape.field("2")?;
    let kind = properties.optional("0")?.map(Node::unsigned).transpose()?;
    let (kind, bounds) = match kind {
        None if shape.optional("1")?.is_none() => ("point", None),
        Some(1) => ("rectangle", Some(rectangle(shape.field("1")?.field("0")?)?)),
        _ => {
            return Err(unsupported(
                "Native text frame type or geometry requires its own layout mapping",
            ));
        }
    };
    let transform = properties
        .optional("2")?
        .map(coordinates::<6>)
        .transpose()?
        .unwrap_or(identity());
    let first = properties.optional("10")?;
    let (metric, minimum) = if let Some(first) = first {
        let metric = match first.field("0")?.unsigned()? {
            0 => crate::text::FirstBaselineMetric::Fixed,
            1 => crate::text::FirstBaselineMetric::Ascent,
            2 => crate::text::FirstBaselineMetric::CapHeight,
            3 => crate::text::FirstBaselineMetric::Leading,
            4 => crate::text::FirstBaselineMetric::XHeight,
            _ => return Err(unsupported("Unknown native first-baseline metric")),
        };
        let minimum = first.field("1")?.number()?;
        if !(0.0..=MAX_COORDINATE).contains(&minimum) {
            return Err(unsupported(
                "Native first-baseline minimum is outside the engine coordinate range",
            ));
        }
        (metric, minimum)
    } else {
        (crate::text::FirstBaselineMetric::Ascent, 0.0)
    };
    // Only explicit source controls participate. Numeric validity does not
    // establish a usable grid, placement rule, default or editable conversion.
    let mut layout_controls = serde_json::Map::new();
    for (key, name, kind) in [
        ("3", "row_count", super::text_style::Kind::Integer),
        ("4", "column_count", super::text_style::Kind::Integer),
        ("7", "row_gap", super::text_style::Kind::Number),
        ("8", "column_gap", super::text_style::Kind::Number),
        ("9", "spacing", super::text_style::Kind::Number),
    ] {
        if let Some(value) = properties.optional(key)? {
            layout_controls.insert(name.to_owned(), kind.read_node(value)?);
        }
    }
    Ok(
        json!({"present":true,"source":"global_story_frame_reference","frame_index":index,
        "frame_count":frames.len(),"shape":kind,"bounds":bounds,"frame_transform":transform,
        "first_baseline":{"metric":metric,"minimum":minimum},"first_baseline_explicit":first.is_some(),
        "layout_controls":layout_controls,"layout_control_types_validated":true,"layout_controls_defaulted":false,
        "selected_reference_and_geometry_validated":true,"other_frames_validated":false,
        "remaining_frame_properties_validated":false,"local_geometry_consistency_validated":false,
        "layout_semantics_validated":false}),
    )
}
