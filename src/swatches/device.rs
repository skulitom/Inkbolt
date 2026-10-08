//! Retained profile declarations and explicit assignment/conversion of named colours.
use super::*;
use crate::profiles::{
    Builtin, Intent, Profile,
    device::{Endpoint, Space, Untagged},
};

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Action {
    Assign {
        encoding: Endpoint,
        #[serde(default)]
        intent: Intent,
    },
    Convert {
        destination: Endpoint,
        #[serde(default)]
        intent: Intent,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        gamut: Option<crate::profiles::gamut::Mode>,
    },
}
pub(crate) fn display() -> Endpoint {
    Endpoint {
        space: Space::Rgb,
        profile: Some(Profile::Builtin {
            name: Builtin::Srgb,
        }),
        untagged: Untagged::Reject,
    }
}
pub(crate) fn tinted(encoding: &Endpoint, components: &[f64], tint: f64) -> Vec<f64> {
    if tint == 1.0 {
        return components.to_vec();
    }
    if tint == 0.0 {
        return encoding.white();
    }
    encoding
        .white()
        .iter()
        .zip(components)
        .map(|(white, value)| white + tint * (value - white))
        .collect()
}
fn source(color: &Process) -> (Endpoint, Vec<f64>) {
    match color {
        Process::Device {
            encoding,
            components,
            ..
        } => (encoding.clone(), components.clone()),
        Process::Srgb { components } => (display(), components.to_vec()),
        Process::Gray { component } => (display(), vec![*component; 3]),
        Process::Cmyk { components, .. } => (
            Endpoint {
                space: Space::Cmyk,
                profile: None,
                untagged: Untagged::Reject,
            },
            components.to_vec(),
        ),
        Process::Lab { components, .. } => (
            Endpoint {
                space: Space::Lab,
                profile: None,
                untagged: Untagged::Reject,
            },
            components.to_vec(),
        ),
    }
}
pub(crate) fn apply(
    d: &mut Document,
    id: &str,
    action: &Action,
    control: Option<&crate::control::Control>,
) -> Result<Value, Error> {
    if let Some(c) = control {
        c.check()?;
    }
    let before = d
        .swatches
        .get(id)
        .ok_or_else(|| Error::new("SWATCH_NOT_FOUND", "Swatch does not exist"))?
        .clone();
    let original = match &before.definition {
        Definition::Process { color } | Definition::Spot { alternate: color } => color,
        Definition::Tint { .. } => {
            return Err(invalid(
                "Assign or convert the base definition; tint aliases retain their references",
            ));
        }
    };
    let (source, mut components) = source(original);
    let mut conversion = None;
    let (encoding, intent) = match action {
        Action::Assign { encoding, intent } => {
            // Legacy gray is a single authored number even though its old preview is encoded RGB.
            if let Process::Gray { component } = original {
                components = vec![*component];
            }
            (encoding.clone(), *intent)
        }
        Action::Convert {
            destination,
            intent,
            gamut,
        } => {
            let converted = crate::profiles::device::convert_with_gamut(
                &source,
                destination,
                *intent,
                &[components],
                *gamut,
                control,
            )?;
            components = serde_json::from_value(converted["samples"][0]["values"].clone())
                .map_err(|_| invalid("Invalid conversion result"))?;
            conversion = Some(converted);
            (destination.clone(), *intent)
        }
    };
    let color = Process::Device {
        encoding,
        components,
        intent,
    };
    color.validate()?;
    let after = Swatch {
        name: before.name.clone(),
        definition: match before.definition {
            Definition::Process { .. } => Definition::Process { color },
            Definition::Spot { .. } => Definition::Spot { alternate: color },
            Definition::Tint { .. } => unreachable!(),
        },
    };
    let mut receipt = super::set(d, id, Some(&after))?;
    receipt["profile_action"] = json!({"action":action,"conversion":conversion,"components_unchanged":matches!(action,Action::Assign { .. }),"references_retained":true,"tint_policy":"interpolate_source_device_components_before_profile_conversion","original_declaration":before,"undo":"retained_before_receipt_and_session_history"});
    Ok(receipt)
}
