//! Editable source reconstruction, separately opted into from font diagnostics.
use super::{binary::Reader, *};
use std::collections::{BTreeMap, BTreeSet};

pub(super) struct Prepared {
    pub frame: crate::text::Frame,
    pub transform: Matrix,
    pub fonts: BTreeMap<String, crate::fonts::Font>,
    pub receipt: Value,
    pub story: Option<(usize, usize, usize, usize)>,
}

pub(super) fn prepare(
    input: &mut Reader<'_>,
    tail: &Reader<'_>,
    version: Version,
    fonts: &TextFonts,
    source_profile: Option<&[u8]>,
    control: &Control,
) -> Result<Prepared, Error> {
    let mut record = super::text_record::inspect(input, control)?;
    record.resolve_details(tail, version, control)?;
    let binding_report = fonts.diagnose(&record.details, control)?;
    let converted = (|| {
        if !record.plain_modes {
            return Err(unsupported(
                "Editable text requires horizontal unwarped text, no grid or native antialias mode, and no legacy compatibility markers",
            ));
        }
        let mut story_reference = None;
        let global = super::text_story::payload(tail, version, control)?;
        let (source, mut styles, paragraphs) = if let Some(bytes) = global {
            let global = super::text_data::parse_global(bytes, control)?;
            let stories = global.field("1")?.field("1")?.array()?;
            let index = usize::try_from(record.story_index).map_err(|_| malformed())?;
            let story = stories.get(index).ok_or_else(malformed)?;
            let (frame_index, frame_count) = super::text_import_geometry::global(&global, story)?;
            story_reference = Some((index, stories.len(), frame_index, frame_count));
            let authoring = story.field("0")?;
            let source = authoring.field("0")?.text()?.to_owned();
            let mut boundaries = BTreeSet::from([0]);
            let mut units = 0;
            for c in source.chars() {
                units += c.len_utf16();
                boundaries.insert(units);
            }
            for (key, field) in [("6", "6"), ("5", "5")] {
                super::text_import_geometry::node_keys(authoring.field(key)?, &["0"])?;
                for run in authoring.field(key)?.field("0")?.array()? {
                    super::text_import_geometry::node_keys(run, &["0", "1"])?;
                    super::text_import_geometry::node_keys(run.field("0")?, &["0"])?;
                    super::text_import_geometry::node_keys(run.field("0")?.field("0")?, &[field])?;
                }
            }
            let style_runs = super::text_story::runs(authoring, "6", &boundaries, units)?;
            let paragraph_runs = super::text_story::runs(authoring, "5", &boundaries, units)?;
            let font_table = global.field("0")?.field("1")?;
            super::text_import_geometry::node_keys(font_table, &["0"])?;
            for font in font_table.field("0")?.array()? {
                super::text_import_geometry::node_keys(font, &["0"])?;
                super::text_import_geometry::node_keys(font.field("0")?, &["0"])?;
                super::text_import_geometry::node_keys(font.field("0")?.field("0")?, &["0"])?;
            }
            let styles = super::text_style::Styles::global(
                style_runs,
                font_table.field("0")?.array()?,
                control,
            )?;
            let paragraphs =
                super::text_paragraph::Paragraphs::global(paragraph_runs, &source, control)?;
            (source, styles, paragraphs)
        } else {
            super::text_import_geometry::local(&record.parsed)?;
            let runs = record.parsed["EngineDict"]["StyleRun"]["RunArray"]
                .as_array()
                .ok_or_else(malformed)?;
            for run in runs {
                let p = &run["StyleSheet"]["StyleSheetData"];
                if p["FillFlag"] != true
                    || p["StrokeFlag"] != false
                    || p["Kerning"].as_f64() != Some(0.0)
                {
                    return Err(unsupported(
                        "Local editable text needs explicit fill-only paint and no manual kerning",
                    ));
                }
            }
            for key in ["FillFlag", "StrokeFlag", "Kerning"] {
                record.styles.unknown.remove(key);
            }
            (record.source.clone(), record.styles, record.paragraphs)
        };
        if let Some(bytes) = source_profile {
            super::text_import_style::convert_colors(&mut styles, bytes, control)?;
        }
        let (frame, used_fonts) = super::text_import_style::frame(
            &source,
            &styles,
            &paragraphs,
            fonts,
            global.is_some(),
        )?;
        // Validate both model bounds and actual glyph coverage with pinned bytes.
        // Do not create a document that first fails when the agent asks to render.
        let document: Document = serde_json::from_value(json!({"schema_version":2,"id":"native-text-check","kind":"raster","width":1,"height":1,"color_space":"srgb","fonts":used_fonts,
            "items":[{"id":"text","transform":record.transform,"content":{"type":"text","frame":frame}}]})).map_err(|_| malformed())?;
        crate::validate(&document)?;
        let cache = used_fonts
            .iter()
            .map(|(id, font)| {
                control.check()?;
                let bytes = crate::fonts::load(font, fonts.font_root.as_deref())?;
                let face = crate::fonts::parsed(font, &bytes)?;
                if face.is_variable() {
                    return Err(unsupported(
                        "Variable native font instances need explicit axis mappings",
                    ));
                }
                Ok((id.clone(), bytes))
            })
            .collect::<Result<crate::fonts::Cache, Error>>()?;
        control.check()?;
        crate::text::layout(&frame, &document, &cache)?;
        let mut receipt = json!({"reconstruction":"engine_layout","text_source":if global.is_some(){"global_story"}else{"local_record"},
            "text_sha256":assets::sha256(frame.text.as_bytes()),"characters":frame.text.chars().count(),"shape":"point","native_baseline_matrix":record.transform,
            "nominal_frame":[1,1],"font_bindings":binding_report,"cached_pixels_used":false,"native_layout_equality":false,
            "color_quantization":"opaque RGB components rounded to eight bits","missing_values_inherited":false});
        receipt["color_interpretation"] = json!(if source_profile.is_some() {
            "converted_srgb_before_quantization"
        } else {
            "source_is_srgb"
        });
        if let Some(bytes) = source_profile {
            receipt["color_conversion"] = json!({"source_profile_sha256":assets::sha256(bytes),
                "target":"srgb","intent":"relative_colorimetric","black_point_compensation":false,
                "gamut_policy":"clip_to_srgb","clipping_count_available":false});
        }
        if let Some((index, _, frame_index, _)) = story_reference {
            receipt["story_index"] = json!(index);
            receipt["frame_index"] = json!(frame_index);
            receipt["local_text_matches"] =
                record.details["global_story"]["local_text_matches"].clone();
            receipt["global_data_sha256"] =
                record.details["global_story"]["global_data_sha256"].clone();
        }
        Ok(Prepared {
            frame,
            transform: record.transform,
            fonts: used_fonts,
            receipt,
            story: story_reference,
        })
    })();
    converted.map_err(|mut error: Error| {
        if error.details.is_none() {
            error.details = Some(Box::new(record.details));
        }
        error
    })
}

pub(super) fn complete_references<'a>(
    texts: impl Iterator<Item = &'a Prepared>,
) -> Result<bool, Error> {
    let mut stories = BTreeSet::new();
    let mut frames = BTreeSet::new();
    let mut expected = None;
    for text in texts {
        if let Some((story, count, frame, frame_count)) = text.story {
            if !stories.insert(story)
                || !frames.insert(frame)
                || expected.is_some_and(|n| n != (count, frame_count))
            {
                return Err(malformed());
            }
            expected = Some((count, frame_count));
        }
    }
    if let Some((count, frame_count)) = expected {
        if stories.len() != count || frames.len() != frame_count {
            return Err(unsupported(
                "Every global text story and frame must have exactly one editable layer reference",
            ));
        }
        Ok(true)
    } else {
        Ok(false)
    }
}
