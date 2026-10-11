//! Explicit source controls and a separately chosen rendering conversion.
use super::{text_data::Node, *};

fn mode(code: u64) -> Option<&'static str> {
    match code {
        0 => Some("none"),
        1 => Some("crisp"),
        2 => Some("strong"),
        3 => Some("smooth"),
        4 => Some("sharp"),
        _ => None,
    }
}
fn descriptor_mode(kind: &str, value: &str) -> Option<&'static str> {
    if kind != "Annt" {
        return None;
    }
    match value {
        "Anno" => mode(0),
        "AnCr" => mode(1),
        "AnSt" => mode(2),
        "AnSm" => mode(3),
        "antiAliasSharp" => mode(4),
        _ => None,
    }
}
fn integer(value: &Value) -> Result<u64, Error> {
    value.as_u64().ok_or_else(malformed)
}
fn boolean(value: &Value) -> Result<bool, Error> {
    value.as_bool().ok_or_else(malformed)
}
fn scalar(value: &Node) -> Result<&Value, Error> {
    match value {
        Node::Scalar(value) => Ok(value),
        _ => Err(malformed()),
    }
}
#[derive(Default)]
pub(super) struct Global {
    present: bool,
    code: Option<u64>,
    fractional: Option<bool>,
    unknown: Vec<String>,
}
impl Global {
    pub fn read(authoring: &Node) -> Result<Self, Error> {
        let Some(value) = authoring.optional("10")? else {
            return Ok(Self::default());
        };
        let Node::Dictionary(fields) = value else {
            return Err(malformed());
        };
        Ok(Self {
            present: true,
            code: fields.get("0").map(|v| integer(scalar(v)?)).transpose()?,
            fractional: fields.get("2").map(|v| boolean(scalar(v)?)).transpose()?,
            unknown: fields
                .keys()
                .filter(|k| !["0", "2"].contains(&k.as_str()))
                .cloned()
                .collect(),
        })
    }
    pub fn report(&self) -> Value {
        json!({"present":self.present,"antialias_code":self.code,"antialias_mode":self.code.and_then(mode),
            "fractional_widths":self.fractional,"unknown_fields":self.unknown.iter().take(8).collect::<Vec<_>>(),
            "unknown_field_count":self.unknown.len(),"missing_values_inferred":false})
    }
}

pub(super) struct Local {
    kind: String,
    value: String,
    code: Option<u64>,
    fractional: Option<bool>,
}
impl Local {
    pub fn read(kind: String, value: String, engine: &Value) -> Result<Self, Error> {
        Ok(Self {
            kind,
            value,
            code: engine.get("AntiAlias").map(integer).transpose()?,
            fractional: engine
                .get("UseFractionalGlyphWidths")
                .map(boolean)
                .transpose()?,
        })
    }
    pub fn report(&self) -> Value {
        let descriptor = descriptor_mode(&self.kind, &self.value);
        let local = self.code.and_then(mode);
        json!({"descriptor":{"kind":self.kind,"value":self.value,"antialias_mode":descriptor},
            "local":{"antialias_code":self.code,"antialias_mode":local,"fractional_widths":self.fractional},
            "known_antialias_values_agree":descriptor.zip(local).map(|(a,b)|a==b),
            "missing_values_inferred":false,"native_rendering_equivalence":false})
    }
    pub fn reconstruct(
        &self,
        global: &Global,
        choice: Option<TextImportRendering>,
    ) -> Result<Value, Error> {
        let descriptor = descriptor_mode(&self.kind, &self.value).ok_or_else(|| {
            unsupported("Unknown descriptor antialias mode has no rendering mapping")
        })?;
        let local = self.code.and_then(mode).ok_or_else(|| {
            unsupported("Editable text needs an explicit known local antialias mode")
        })?;
        let fractional = self.fractional.ok_or_else(|| {
            unsupported("Editable text needs an explicit local fractional-width control")
        })?;
        if descriptor != local
            || global
                .code
                .is_some_and(|code| mode(code) != Some(descriptor))
            || global.fractional.is_some_and(|value| value != fractional)
        {
            return Err(unsupported(
                "Conflicting or unknown source text rendering controls require reconciliation",
            ));
        }
        if !global.unknown.is_empty() {
            return Err(unsupported(
                "Unknown global text rendering controls cannot be discarded",
            ));
        }
        if choice.is_none() && (descriptor != "none" || !fractional) {
            return Err(unsupported(
                "Known native text rendering requires explicit text_fonts.rendering:engine; edge smoothing and fractional spacing will be reconstructed",
            ));
        }
        Ok(
            json!({"choice":if choice.is_some(){"engine"}else{"existing_point_reconstruction"},
            "source":self.report(),"global_source":global.report(),
            "output":{"edge_smoothing":"engine","fractional_widths":true},
            "differences":{"native_edge_smoothing_reconstructed":true,"fractional_spacing_reconstructed":!fractional},
            "native_rendering_equivalence":false}),
        )
    }
}
