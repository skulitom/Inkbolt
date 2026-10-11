//! Observed character controls only. Equal local caches do not establish complete
//! style semantics, font identity, paragraph layout or editability.
use super::{text_data::Node, *};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Copy)]
pub(super) enum Kind {
    Boolean,
    Number,
    Integer,
    NumberTriple,
}
impl Kind {
    pub fn read(self, value: &Value) -> Result<Value, Error> {
        Ok(match self {
            Self::Boolean => json!(value.as_bool().ok_or_else(malformed)?),
            Self::Number => json!(
                value
                    .as_f64()
                    .filter(|n| n.is_finite())
                    .ok_or_else(malformed)?
            ),
            Self::Integer => json!(value.as_i64().ok_or_else(malformed)?),
            Self::NumberTriple => {
                let values = value.as_array().ok_or_else(malformed)?;
                if values.len() != 3 {
                    return Err(malformed());
                }
                Value::Array(
                    values
                        .iter()
                        .map(|v| Self::Number.read(v))
                        .collect::<Result<_, _>>()?,
                )
            }
        })
    }
    pub fn read_node(self, node: &Node) -> Result<Value, Error> {
        if let Self::NumberTriple = self {
            let values = node.array()?;
            if values.len() != 3 {
                return Err(malformed());
            }
            return Ok(Value::Array(
                values
                    .iter()
                    .map(|v| Ok(json!(v.number()?)))
                    .collect::<Result<_, Error>>()?,
            ));
        }
        let Node::Scalar(v) = node else {
            return Err(malformed());
        };
        self.read(v)
    }
}

// This is an explicit mapping of individually observed controls, not a table of
// native defaults. Missing entries remain missing. Feature names do not imply
// a mapping to shaping tags or support by the selected font.
const CONTROLS: &[(Option<&str>, Option<&str>, &str, Kind)] = &[
    (Some("1"), Some("FontSize"), "size", Kind::Number),
    (Some("2"), Some("FauxBold"), "faux_bold", Kind::Boolean),
    (Some("3"), Some("FauxItalic"), "faux_italic", Kind::Boolean),
    (
        Some("4"),
        Some("AutoLeading"),
        "automatic_leading",
        Kind::Boolean,
    ),
    (Some("5"), Some("Leading"), "leading", Kind::Number),
    (
        Some("6"),
        Some("HorizontalScale"),
        "horizontal_scale",
        Kind::Number,
    ),
    (
        Some("7"),
        Some("VerticalScale"),
        "vertical_scale",
        Kind::Number,
    ),
    (
        Some("8"),
        Some("Tracking"),
        "tracking_thousandths_em",
        Kind::Integer,
    ),
    (
        Some("9"),
        Some("BaselineShift"),
        "baseline_shift",
        Kind::Number,
    ),
    (
        Some("12"),
        Some("FontCaps"),
        "capitalization_code",
        Kind::Integer,
    ),
    (
        Some("13"),
        Some("FontBaseline"),
        "baseline_code",
        Kind::Integer,
    ),
    // These legacy booleans/codes do not encode all global modes.
    (Some("11"), None, "kerning_code", Kind::Integer),
    (
        None,
        Some("AutoKerning"),
        "local_auto_kerning",
        Kind::Boolean,
    ),
    (Some("15"), None, "strikethrough_code", Kind::Integer),
    (
        None,
        Some("Strikethrough"),
        "local_strikethrough",
        Kind::Boolean,
    ),
    (Some("16"), None, "underline_code", Kind::Integer),
    (None, Some("Underline"), "local_underline", Kind::Boolean),
    (
        None,
        Some("YUnderline"),
        "local_underline_position",
        Kind::Integer,
    ),
    (Some("18"), Some("Ligatures"), "ligatures", Kind::Boolean),
    (
        Some("19"),
        Some("DLigatures"),
        "discretionary_ligatures",
        Kind::Boolean,
    ),
    (Some("20"), None, "contextual_ligatures", Kind::Boolean),
    (Some("23"), None, "fractions", Kind::Boolean),
    (Some("24"), None, "ordinals", Kind::Boolean),
    (Some("25"), None, "swash", Kind::Boolean),
    (Some("26"), None, "titling", Kind::Boolean),
    (Some("27"), None, "connection_forms", Kind::Boolean),
    (Some("28"), None, "stylistic_alternates", Kind::Boolean),
    (Some("29"), None, "ornaments", Kind::Boolean),
    (Some("75"), None, "justification_alternates", Kind::Boolean),
    (Some("31"), None, "proportional_metrics", Kind::Boolean),
    (Some("32"), None, "kana", Kind::Boolean),
    (Some("33"), None, "italics", Kind::Boolean),
    (Some("52"), Some("NoBreak"), "no_break", Kind::Boolean),
    (Some("14"), None, "opentype_baseline_code", Kind::Integer),
    (Some("30"), None, "figure_style_code", Kind::Integer),
    (
        Some("35"),
        Some("BaselineDirection"),
        "baseline_direction_code",
        Kind::Integer,
    ),
    (
        Some("36"),
        Some("Tsume"),
        "spacing_compression",
        Kind::Number,
    ),
    (
        Some("37"),
        Some("StyleRunAlignment"),
        "character_alignment_code",
        Kind::Integer,
    ),
    (Some("38"), Some("Language"), "language_code", Kind::Integer),
    (Some("39"), None, "alternate_form_code", Kind::Integer),
    (Some("68"), None, "joining_elongation_code", Kind::Integer),
    (
        None,
        Some("Kashida"),
        "local_joining_elongation_code",
        Kind::Integer,
    ),
    (Some("70"), None, "digit_set_code", Kind::Integer),
    (
        None,
        Some("HindiNumbers"),
        "local_alternate_digits",
        Kind::Boolean,
    ),
    (
        Some("72"),
        None,
        "diacritic_horizontal_offset",
        Kind::Number,
    ),
    (Some("73"), None, "diacritic_vertical_offset", Kind::Number),
    (Some("85"), None, "stylistic_set_selection", Kind::Integer),
    (Some("87"), None, "mark_baseline_distance", Kind::Number),
];

fn face_name(name: &str) -> Result<Value, Error> {
    if name.is_empty() || name.len() > 128 || !name.bytes().all(|b| (33..=126).contains(&b)) {
        return Err(unsupported(
            "Native font identity is not a bounded printable face name",
        ));
    }
    Ok(json!(name))
}

#[derive(Serialize)]
pub(super) struct Run {
    pub end_utf16: usize,
    pub controls: BTreeMap<&'static str, Value>,
}
pub(super) struct Styles {
    pub runs: Vec<Run>,
    pub unknown: BTreeSet<String>,
}
impl Styles {
    pub fn local(engine: &Value, fonts: &[Value], control: &Control) -> Result<Self, Error> {
        let run = &engine["StyleRun"];
        let lengths = run["RunLengthArray"].as_array().ok_or_else(malformed)?;
        let mut out = Self {
            runs: Vec::new(),
            unknown: BTreeSet::new(),
        };
        let mut end = 0;
        for (r, length) in run["RunArray"]
            .as_array()
            .ok_or_else(malformed)?
            .iter()
            .zip(lengths)
        {
            control.check()?;
            // Complete positive run coverage has already been validated.
            end += length.as_u64().ok_or_else(malformed)? as usize;
            let properties = r
                .pointer("/StyleSheet/StyleSheetData")
                .and_then(Value::as_object)
                .ok_or_else(malformed)?;
            let mut controls = BTreeMap::new();
            if let Some(index) = properties.get("Font") {
                let index = index
                    .as_u64()
                    .and_then(|n| usize::try_from(n).ok())
                    .ok_or_else(malformed)?;
                let name = fonts
                    .get(index)
                    .and_then(|v| v.get("Name"))
                    .and_then(Value::as_str)
                    .ok_or_else(malformed)?;
                controls.insert("font_face_name", face_name(name)?);
            }
            for &(_, local, name, kind) in CONTROLS {
                if let Some(v) = local.and_then(|key| properties.get(key)) {
                    controls.insert(name, kind.read(v)?);
                }
            }
            for &(_, local, name) in super::text_paint::FIELDS {
                if let Some(value) = properties.get(local)
                    && let Some(value) = super::text_paint::local(value, local, &mut out.unknown)?
                {
                    controls.insert(name, value);
                }
            }
            out.unknown.extend(
                properties
                    .keys()
                    .filter(|k| {
                        k.as_str() != "Font"
                            && !super::text_paint::FIELDS
                                .iter()
                                .any(|(_, local, _)| *local == k.as_str())
                            && !CONTROLS
                                .iter()
                                .any(|(_, local, _, _)| *local == Some(k.as_str()))
                    })
                    .cloned(),
            );
            out.runs.push(Run {
                end_utf16: end,
                controls,
            });
        }
        Ok(out)
    }

    pub fn global(
        runs: &[super::text_inheritance::Run<'_>],
        fonts: &[Node],
        control: &Control,
    ) -> Result<Self, Error> {
        let mut out = Self {
            runs: Vec::new(),
            unknown: BTreeSet::new(),
        };
        let mut end = 0;
        for run in runs {
            control.check()?;
            end += run.length;
            let style = run.fields.as_ref().ok_or_else(malformed)?;
            let index = style.get("0").ok_or_else(malformed)?.unsigned()?;
            let name = fonts
                .get(index)
                .ok_or_else(malformed)?
                .field("0")?
                .field("0")?
                .field("0")?
                .text()?;
            let mut controls = BTreeMap::from([("font_face_name", face_name(name)?)]);
            for &(key, _, name, kind) in CONTROLS {
                if let Some(key) = key
                    && let Some(v) = style.get(key)
                {
                    controls.insert(name, kind.read_node(v)?);
                }
            }
            for &(global, _, name) in super::text_paint::FIELDS {
                if let Some(value) = style.get(global)
                    && let Some(value) = super::text_paint::global(value, global, &mut out.unknown)?
                {
                    controls.insert(name, value);
                }
            }
            out.unknown.extend(
                style
                    .keys()
                    .filter(|k| {
                        **k != "0"
                            && !super::text_paint::FIELDS
                                .iter()
                                .any(|(global, _, _)| *global == **k)
                            && !CONTROLS.iter().any(|(key, _, _, _)| *key == Some(**k))
                    })
                    .map(|k| (*k).to_owned()),
            );
            out.runs.push(Run {
                end_utf16: end,
                controls,
            });
        }
        Ok(out)
    }

    pub fn missing_fonts(&self) -> usize {
        self.runs
            .iter()
            .filter(|r| !r.controls.contains_key("font_face_name"))
            .count()
    }

    pub fn faces(&self) -> Result<BTreeSet<&str>, Error> {
        let faces = self
            .runs
            .iter()
            .filter_map(|r| r.controls.get("font_face_name").and_then(Value::as_str))
            .collect::<BTreeSet<_>>();
        if faces.len() > crate::fonts::MAX_FONTS {
            return Err(limit(
                "Native text story references more than eight font faces",
            ));
        }
        Ok(faces)
    }

    fn summary(&self) -> Result<Value, Error> {
        let bytes = serde_json::to_vec(&self.runs).map_err(|_| malformed())?;
        let observed = self
            .runs
            .iter()
            .flat_map(|r| r.controls.keys())
            .collect::<BTreeSet<_>>();
        let enabled = self
            .runs
            .iter()
            .flat_map(|r| r.controls.iter())
            .filter_map(|(k, v)| (v.as_bool() == Some(true)).then_some(k))
            .collect::<BTreeSet<_>>();
        Ok(
            json!({"run_controls_sha256":assets::sha256(&bytes),"observed_controls":observed,
            "enabled_boolean_controls":enabled,"unmapped_fields":self.unknown.iter().take(16).collect::<Vec<_>>(),
            "unmapped_field_count":self.unknown.len(),"unmapped_fields_truncated":self.unknown.len()>16}),
        )
    }

    pub fn compare(
        &self,
        local: &Self,
        text_matches: bool,
        control: &Control,
    ) -> Result<Value, Error> {
        let comparison = if text_matches {
            let mut compared = BTreeSet::new();
            let mut different = BTreeSet::new();
            let mut missing_local = BTreeSet::new();
            let mut missing_global = BTreeSet::new();
            let (mut g, mut l, mut spans, mut differing_spans) = (0, 0, 0, 0);
            while g < self.runs.len() && l < local.runs.len() {
                control.check()?;
                let global = &self.runs[g];
                let local = &local.runs[l];
                let mut differs = false;
                for (key, value) in &global.controls {
                    if let Some(other) = local.controls.get(key) {
                        compared.insert(key);
                        if value != other {
                            different.insert(key);
                            differs = true;
                        }
                    } else {
                        missing_local.insert(key);
                    }
                }
                for key in local.controls.keys() {
                    if !global.controls.contains_key(key) {
                        missing_global.insert(key);
                    }
                }
                spans += 1;
                differing_spans += usize::from(differs);
                let end = global.end_utf16.min(local.end_utf16);
                g += usize::from(global.end_utf16 == end);
                l += usize::from(local.end_utf16 == end);
            }
            json!({"performed":true,"utf16_spans":spans,"compared_controls":compared,
                "all_compared_values_match":different.is_empty(),"differing_spans":differing_spans,"different_controls":different,
                "missing_local_controls":missing_local,"missing_global_controls":missing_global,
                "all_observed_controls_present_on_both_sides":missing_local.is_empty()&&missing_global.is_empty()})
        } else {
            json!({"performed":false,"reason":"source_text_differs"})
        };
        Ok(
            json!({"known_control_types_validated":true,"global":self.summary()?,"local":local.summary()?,
            "comparison":comparison,"complete_style_semantics_validated":false,"font_file_identity_validated":false,
            "missing_values_defaulted":false,"unknown_fields_interpreted":false,"rendering_equivalence_validated":false}),
        )
    }
}
