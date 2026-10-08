//! Nonprinting scalar planes with explicit selection, component and named-ink semantics.
use crate::{Error, model::*, render, selections};
use base64::{Engine, engine::general_purpose::STANDARD};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{collections::HashSet, path::Path};
pub const MAX_CHANNELS: usize = 16;
pub const MAX_SAMPLES: usize = 262_144;

#[derive(Clone, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Role {
    #[default]
    Alpha,
    Spot {
        ink_id: String,
        alternate_srgb: [u8; 3],
    },
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Channel {
    pub name: String,
    #[serde(default)]
    pub role: Role,
    pub plane: selections::Selection,
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Component {
    Red,
    Green,
    Blue,
    Alpha,
    Luma,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Source {
    Selection {},
    Channel { id: String },
    Component { component: Component },
    Constant { value: u8 },
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Mode {
    Add,
    Subtract,
    Difference,
    Multiply,
    Screen,
    Minimum,
    Maximum,
    Average,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Calculation {
    Copy {
        source: Source,
        #[serde(default)]
        invert: bool,
    },
    Combine {
        left: Source,
        right: Source,
        mode: Mode,
        #[serde(default)]
        invert_left: bool,
        #[serde(default)]
        invert_right: bool,
    },
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Display {
    #[default]
    Gray,
    Ink,
}

pub fn validate(document: &Document) -> Result<(), Error> {
    if document.channels.len() > MAX_CHANNELS {
        return Err(limit("Document exceeds 16 saved channels"));
    }
    let mut count = 0;
    let mut inks = HashSet::new();
    for (id, channel) in &document.channels {
        if !valid_id(id)
            || channel.name.len() > 1024
            || channel
                .name
                .chars()
                .any(|c| c.is_control() || matches!(c, '\u{fffe}' | '\u{ffff}'))
        {
            return Err(invalid("Channel ID or name is invalid"));
        }
        selections::validate(&channel.plane, document.width, document.height)?;
        count += channel.plane.width as usize * channel.plane.height as usize;
        if let Role::Spot { ink_id, .. } = &channel.role
            && (!valid_id(ink_id) || !inks.insert(ink_id))
        {
            return Err(invalid(
                "Spot ink IDs must be valid and unique in a document",
            ));
        }
    }
    if count > MAX_SAMPLES {
        return Err(limit("Saved channels exceed 262144 scalar samples"));
    }
    Ok(())
}
pub fn get<'a>(document: &'a Document, id: &str) -> Result<&'a Channel, Error> {
    document
        .channels
        .get(id)
        .ok_or_else(|| Error::new("NOT_FOUND", "Saved channel ID does not exist"))
}
pub(crate) fn check_destination(
    document: &Document,
    id: &str,
    replace_existing: bool,
) -> Result<(), Error> {
    if !valid_id(id) {
        return Err(invalid("Channel ID is invalid"));
    }
    if document.channels.contains_key(id) && !replace_existing {
        return Err(Error::new(
            "INVALID_OPERATION",
            "Channel already exists; explicitly set replace_existing to replace its plane and role",
        ));
    }
    Ok(())
}
pub(crate) fn put(
    document: &mut Document,
    id: &str,
    channel: Channel,
    replace_existing: bool,
) -> Result<(), Error> {
    check_destination(document, id, replace_existing)?;
    document.channels.insert(id.to_owned(), channel);
    Ok(())
}
fn resolve(
    document: &Document,
    source: &Source,
    image: &mut Option<Vec<u8>>,
    asset_root: Option<&Path>,
    font_root: Option<&Path>,
) -> Result<Vec<u8>, Error> {
    Ok(match source {
        Source::Selection {} => render::unhex(
            &document
                .selection
                .as_ref()
                .ok_or_else(|| {
                    Error::new(
                        "INVALID_OPERATION",
                        "Channel calculation requires an active selection",
                    )
                })?
                .gray_hex,
        ),
        Source::Channel { id } => render::unhex(&get(document, id)?.plane.gray_hex),
        Source::Constant { value } => {
            vec![*value; document.width as usize * document.height as usize]
        }
        Source::Component { component } => {
            if image.is_none() {
                *image = Some(
                    render::rasterize_with_resources(document, 1, asset_root, font_root)?.rgba,
                );
            }
            image
                .as_ref()
                .unwrap()
                .as_chunks::<4>()
                .0
                .iter()
                .map(|p| match component {
                    Component::Red => p[0],
                    Component::Green => p[1],
                    Component::Blue => p[2],
                    Component::Alpha => p[3],
                    Component::Luma => {
                        ((2126 * p[0] as u32 + 7152 * p[1] as u32 + 722 * p[2] as u32 + 5000)
                            / 10000) as u8
                    }
                })
                .collect()
        }
    })
}
pub fn calculate(
    document: &Document,
    calculation: &Calculation,
    asset_root: Option<&Path>,
    font_root: Option<&Path>,
) -> Result<selections::Selection, Error> {
    selections::check_size(document.width, document.height)?;
    let mut image = None;
    let values = match calculation {
        Calculation::Copy { source, invert } => {
            let mut v = resolve(document, source, &mut image, asset_root, font_root)?;
            if *invert {
                for c in &mut v {
                    *c = 255 - *c;
                }
            }
            v
        }
        Calculation::Combine {
            left,
            right,
            mode,
            invert_left,
            invert_right,
        } => {
            let a = resolve(document, left, &mut image, asset_root, font_root)?;
            let b = resolve(document, right, &mut image, asset_root, font_root)?;
            a.into_iter()
                .zip(b)
                .map(|(a, b)| {
                    let a = if *invert_left { 255 - a } else { a } as u32;
                    let b = if *invert_right { 255 - b } else { b } as u32;
                    (match mode {
                        Mode::Add => (a + b).min(255),
                        Mode::Subtract => a.saturating_sub(b),
                        Mode::Difference => a.abs_diff(b),
                        Mode::Multiply => (a * b + 127) / 255,
                        Mode::Screen => 255 - ((255 - a) * (255 - b) + 127) / 255,
                        Mode::Minimum => a.min(b),
                        Mode::Maximum => a.max(b),
                        Mode::Average => (a + b).div_ceil(2),
                    }) as u8
                })
                .collect()
        }
    };
    Ok(selections::Selection {
        width: document.width,
        height: document.height,
        gray_hex: render::hex(&values),
    })
}
pub fn inspect(document: &Document) -> Value {
    Value::Array(document.channels.iter().map(|(id,c)|json!({"id":id,"name":c.name,"role":c.role,"coverage":selections::inspect(Some(&c.plane)),"nonprinting":true})).collect())
}
pub fn export(document: &Document, id: &str, display: Display) -> Result<Value, Error> {
    crate::validate(document)?;
    let channel = get(document, id)?;
    let color = if matches!(display, Display::Ink) {
        match channel.role {
            Role::Spot { alternate_srgb, .. } => Some(alternate_srgb),
            Role::Alpha => {
                return Err(Error::new(
                    "INVALID_REQUEST",
                    "Ink display requires a spot channel",
                ));
            }
        }
    } else {
        None
    };
    let pixels: Vec<u8> = render::unhex(&channel.plane.gray_hex)
        .iter()
        .flat_map(|&v| match color {
            Some(rgb) if v != 0 => [rgb[0], rgb[1], rgb[2], v],
            Some(_) => [0; 4],
            None => [v, v, v, 255],
        })
        .collect();
    let bytes = render::encode_png(
        document.width,
        document.height,
        &pixels,
        document.resolution_ppi,
    )?;
    Ok(
        json!({"document_id":document.id,"revision":document.revision,"channel_id":id,"name":channel.name,"role":channel.role,"display":display,"media_type":"image/png","encoding":"base64","width":document.width,"height":document.height,"data":STANDARD.encode(bytes),"coverage_sha256":crate::assets::sha256(&render::unhex(&channel.plane.gray_hex)),"fidelity":"PNG is a scalar grayscale view or alternate-sRGB ink preview; named ink identity is retained in this result and the editable snapshot, not inside PNG. This is not a color-managed separation."}),
    )
}
