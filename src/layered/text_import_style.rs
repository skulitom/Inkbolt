//! Explicit point-text conversion. No inherited values or native defaults.
use super::{text_style::Styles, *};
use crate::{fonts, text};
use std::collections::BTreeMap;

fn missing(key: &str) -> Error {
    unsupported(&format!(
        "Editable point text needs an explicit supported {key} control"
    ))
}
fn number(values: &BTreeMap<&str, Value>, key: &str) -> Result<f64, Error> {
    values
        .get(key)
        .and_then(Value::as_f64)
        .ok_or_else(|| missing(key))
}
fn boolean(values: &BTreeMap<&str, Value>, key: &str) -> Result<bool, Error> {
    values
        .get(key)
        .and_then(Value::as_bool)
        .ok_or_else(|| missing(key))
}
pub(super) fn frame(
    source: &str,
    styles: &Styles,
    paragraphs: &super::text_paragraph::Paragraphs,
    bindings: &TextFonts,
    global: bool,
) -> Result<(text::Frame, BTreeMap<String, fonts::Font>), Error> {
    if !styles.unknown.is_empty()
        || !paragraphs.styles.unknown.is_empty()
        || paragraphs.absent_properties != 0
        || paragraphs.run_ends_without_carriage_return != 0
    {
        return Err(unsupported(
            "Unmapped or inherited character/paragraph controls cannot become editable text",
        ));
    }
    let source = source.strip_suffix('\r').ok_or_else(malformed)?;
    if source.contains(['\r', '\n']) {
        return Err(unsupported(
            "Editable native point text currently requires one line",
        ));
    }
    for p in &paragraphs.styles.runs {
        // Every admitted paragraph property is interpreted, rather than ignored
        // because this happens to be a short string.
        if p.controls.len() != 2
            || number(&p.controls, "justification_code")? != 0.0
            || boolean(&p.controls, "automatic_hyphenation")?
        {
            return Err(unsupported(
                "Editable point text requires explicit left alignment, disabled hyphenation and no other paragraph controls",
            ));
        }
    }
    let mut fonts = BTreeMap::new();
    let mut converted = Vec::new();
    let mut leading = None;
    for run in &styles.runs {
        let v = &run.controls;
        let mut consumed = std::collections::BTreeSet::new();
        for key in [
            "faux_bold",
            "faux_italic",
            "no_break",
            "local_strikethrough",
            "local_underline",
        ] {
            if let Some(value) = v.get(key) {
                if value.as_bool() != Some(false) {
                    return Err(missing(key));
                }
                consumed.insert(key);
            }
        }
        for key in ["capitalization_code", "baseline_code"] {
            if number(v, key)? != 0.0 {
                return Err(missing(key));
            }
            consumed.insert(key);
        }
        for key in ["strikethrough_code", "underline_code"] {
            if global && number(v, key)? != 0.0 {
                return Err(missing(key));
            }
            if global {
                consumed.insert(key);
            }
        }
        if boolean(v, "automatic_leading")? {
            return Err(missing("explicit leading"));
        }
        let current = number(v, "leading")?;
        if leading.is_some_and(|previous| previous != current) {
            return Err(missing("uniform leading"));
        }
        leading = Some(current);
        let name = v
            .get("font_face_name")
            .and_then(Value::as_str)
            .ok_or_else(malformed)?;
        let binding = bindings
            .bindings
            .iter()
            .find(|b| b.face_name == name)
            .ok_or_else(|| missing("pinned font"))?;
        let id = format!(
            "native-font-{}",
            bindings
                .bindings
                .iter()
                .position(|b| b.face_name == name)
                .unwrap()
                + 1
        );
        fonts.insert(id.clone(), binding.font.clone());
        let color = v
            .get("fill_color")
            .ok_or_else(|| missing("solid RGB fill"))?;
        let components = color["components"].as_array().ok_or_else(malformed)?;
        if color["type"] != 1 || components.len() != 4 || components[0].as_f64() != Some(1.0) {
            return Err(missing("opaque type-1 RGB fill"));
        }
        let mut rgba = [255; 4];
        for (out, value) in rgba.iter_mut().zip(&components[1..]) {
            let n = value
                .as_f64()
                .filter(|n| (0.0..=1.0).contains(n))
                .ok_or_else(|| missing("RGB components in 0..1"))?;
            *out = (n * 255.0).round() as u8;
        }
        let kern = if global {
            if number(v, "kerning_code")? != 1.0 {
                return Err(missing("font-metric kerning"));
            }
            true
        } else {
            boolean(v, "local_auto_kerning")?
        };
        let size = number(v, "size")?;
        let horizontal_scale = number(v, "horizontal_scale")?;
        let style = text::Style {
            font_id: id,
            fallback_fonts: Vec::new(),
            language: None,
            font_variations: BTreeMap::new(),
            features: BTreeMap::from([
                ("kern".into(), u32::from(kern)),
                ("liga".into(), u32::from(boolean(v, "ligatures")?)),
                (
                    "dlig".into(),
                    u32::from(boolean(v, "discretionary_ligatures")?),
                ),
            ]),
            size,
            fill: Paint::Solid(rgba),
            horizontal_scale,
            vertical_scale: number(v, "vertical_scale")?,
            baseline_shift: number(v, "baseline_shift")?,
            tracking: number(v, "tracking_thousandths_em")? * size * horizontal_scale / 1000.0,
        };
        consumed.extend([
            "font_face_name",
            "fill_color",
            "size",
            "horizontal_scale",
            "vertical_scale",
            "baseline_shift",
            "tracking_thousandths_em",
            "automatic_leading",
            "leading",
            "ligatures",
            "discretionary_ligatures",
            if global {
                "kerning_code"
            } else {
                "local_auto_kerning"
            },
        ]);
        if v.keys().any(|key| !consumed.contains(key)) {
            return Err(unsupported(
                "Unconverted character controls cannot be discarded",
            ));
        }
        converted.push((run.end_utf16, style));
    }
    let first = converted.first().ok_or_else(malformed)?.1.clone();
    let count = source.chars().count();
    let mut units = BTreeMap::from([(0, 0)]);
    let mut offset = 0;
    for (i, c) in source.chars().enumerate() {
        offset += c.len_utf16();
        units.insert(offset, i + 1);
    }
    let mut ranges = Vec::new();
    let mut start = 0;
    let mut previous = first.clone();
    for (end, style) in converted {
        let end = *units.get(&end.min(offset)).ok_or_else(malformed)?;
        if start == end && style != previous {
            return Err(unsupported(
                "A distinct terminal insertion style needs an editable engine representation",
            ));
        }
        previous = style.clone();
        if start < end && style != first {
            ranges.push(text::StyleRange { start, end, style });
        }
        start = end;
    }
    if start != count {
        return Err(malformed());
    }
    Ok((
        text::Frame {
            text: source.into(),
            width: 1.0,
            height: 1.0,
            style: first,
            ranges,
            align: text::Align::Left,
            direction: text::Direction::Ltr,
            bidi: text::Bidi::SingleRun,
            wrap: false,
            leading,
            overflow: text::Overflow::Visible,
            path: None,
            first_baseline: Some(text::FirstBaseline {
                metric: text::FirstBaselineMetric::Fixed,
                minimum: 0.0,
            }),
        },
        fonts,
    ))
}
