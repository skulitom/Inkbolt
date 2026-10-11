//! Explicit chosen font identities. A face name does not identify the source file.
use super::*;
use crate::fonts;
use std::{collections::BTreeMap, path::PathBuf};

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct TextFontBinding {
    pub face_name: String,
    pub font: fonts::Font,
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct TextFonts {
    pub bindings: Vec<TextFontBinding>,
    #[serde(default)]
    pub font_root: Option<PathBuf>,
    /// Explicitly choose editable engine layout for the admitted text subset.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reconstruction: Option<TextImportReconstruction>,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum TextImportReconstruction {
    EngineLayout,
}

fn valid_name(name: &str) -> bool {
    !name.is_empty() && name.len() <= 128 && name.bytes().all(|b| (33..=126).contains(&b))
}

pub(super) fn face_name(face: &rustybuzz::Face<'_>) -> Result<String, Error> {
    let names = face
        .names()
        .into_iter()
        .filter(|n| n.name_id == 6)
        .filter_map(|n| n.to_string())
        .collect::<std::collections::BTreeSet<_>>();
    if names.len() != 1 {
        return Err(unsupported(
            "Native text needs one unambiguous Unicode PostScript face name in each pinned font",
        ));
    }
    let name = names.into_iter().next().unwrap();
    if !valid_name(&name) {
        return Err(unsupported(
            "Native font face name must contain 1..128 printable nonspace ASCII bytes",
        ));
    }
    Ok(name)
}

impl TextFonts {
    pub(super) fn validate(&self) -> Result<(), Error> {
        if self.bindings.is_empty() || self.bindings.len() > fonts::MAX_FONTS {
            return Err(limit(
                "Native text bindings require one to eight explicit font faces",
            ));
        }
        let mut names = std::collections::BTreeSet::new();
        for binding in &self.bindings {
            if !valid_name(&binding.face_name) || !names.insert(&binding.face_name) {
                return Err(Error::new(
                    "INVALID_REQUEST",
                    "Native font bindings require unique bounded printable face names",
                ));
            }
            fonts::validate(&binding.font)?;
        }
        Ok(())
    }

    pub(super) fn diagnose(&self, details: &Value, control: &Control) -> Result<Value, Error> {
        let global = details["global_story"]["present"].as_bool() == Some(true);
        let source = if global {
            &details["global_story"]
        } else {
            details
        };
        let required = source["font_face_names"].as_array().ok_or_else(malformed)?;
        let provided = self
            .bindings
            .iter()
            .map(|b| (b.face_name.as_str(), &b.font))
            .collect::<BTreeMap<_, _>>();
        let mut used = BTreeMap::new();
        let mut missing = Vec::new();
        for name in required {
            let name = name.as_str().ok_or_else(malformed)?;
            if let Some(font) = provided.get(name) {
                used.insert(name, *font);
            } else {
                missing.push(name);
            }
        }
        if !missing.is_empty() {
            let mut error = Error::new(
                "FONT_BINDING_REQUIRED",
                "Supply an explicit pinned font binding for every referenced face in the selected native text source",
            );
            error.details = Some(Box::new(
                json!({"kind":"native_text_font_bindings","text_source":if global {"global_story"} else {"local_record"},"missing_face_names":missing,"source_font_files_identified":false}),
            ));
            return Err(error);
        }
        for (name, font) in &used {
            control.check()?;
            let checked = (|| {
                let bytes = fonts::load(font, self.font_root.as_deref())?;
                control.check()?;
                let selected = face_name(&fonts::parsed(font, &bytes)?)?;
                if selected != *name {
                    return Err(Error::new(
                        "FONT_FACE_MISMATCH",
                        "The selected pinned face does not have the native binding's exact face name",
                    ));
                }
                Ok(())
            })();
            checked.map_err(|mut error: Error| {
                error.details = Some(Box::new(json!({"kind":"native_text_font_bindings","face_name":name,"source_font_files_identified":false})));
                error
            })?;
        }
        control.check()?;
        let identity = serde_json::to_vec(&json!(used)).map_err(|_| malformed())?;
        Ok(
            json!({"text_source":if global {"global_story"} else {"local_record"},
            "checked_faces":used.len(),"unused_bindings":provided.len()-used.len(),
            "chosen_bindings_sha256":assets::sha256(&identity),"chosen_resources_validated":true,
            "source_font_files_identified":false}),
        )
    }
}
