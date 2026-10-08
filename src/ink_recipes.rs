//! Retained named-ink recipes over independent saved scalar sources.
use crate::{Document, Error, assets, control::Control, model::limit, profiles, render};
use base64::{Engine, engine::general_purpose::STANDARD};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::HashSet;

pub const MAX_INKS: usize = 8;
pub const MAX_KNOTS: usize = 64;
pub const MAX_WORK: u64 = 67_108_864;

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Ink {
    pub id: String,
    pub name: String,
    pub channel: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub mask_channel: Option<String>,
    pub alternate_srgb: [u8; 3],
    pub curve: Vec<[f64; 2]>,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Preview {
    Transmittance { paper_srgb: [u8; 3] },
    Corners { linear_rgb: Vec<[f64; 3]> },
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Recipe {
    pub inks: Vec<Ink>,
    pub preview: Preview,
}
/// Explicit supplied process-colour approximation for printing named inks with
/// calibrated process artwork. This is separate from the recipe-only preview.
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(tag = "model", rename_all = "snake_case", deny_unknown_fields)]
pub enum ProcessMix {
    MultiplicativeCmyk {
        alternate_cmyk: std::collections::BTreeMap<String, [f64; 4]>,
    },
}
impl ProcessMix {
    pub(crate) fn validate(&self, document: &Document) -> Result<Vec<[f64; 4]>, Error> {
        let recipe = document.ink_recipe.as_ref().ok_or_else(|| {
            Error::new(
                "INVALID_REQUEST",
                "Combined printing requires a retained ink_recipe",
            )
        })?;
        let Self::MultiplicativeCmyk { alternate_cmyk } = self;
        if alternate_cmyk.len() != recipe.inks.len()
            || recipe
                .inks
                .iter()
                .any(|i| !alternate_cmyk.contains_key(&i.id))
            || alternate_cmyk
                .values()
                .flatten()
                .any(|v| !v.is_finite() || !(0.0..=1.0).contains(v))
        {
            return Err(Error::new(
                "INVALID_REQUEST",
                "Combined printing needs exactly one normalized CMYK alternate for each recipe ink ID",
            ));
        }
        Ok(recipe.inks.iter().map(|i| alternate_cmyk[&i.id]).collect())
    }
}
pub struct Combined<'a> {
    pub named: Prepared<'a>,
    pub alternates: Vec<[f64; 4]>,
    pub samples: Vec<u8>,
    pub fallback: Vec<f64>,
    process_hash: String,
}
impl Combined<'_> {
    pub fn receipt(&self) -> Value {
        json!({"kind":"cmyk_and_named","named":self.named.receipt(),"process_sha256":self.process_hash,"interleaved_sha256":assets::sha256(&self.samples),"sample_encoding":"CMYK8_then_named8_in_recipe_order;0_none_255_full","fallback_model":"multiplicative_cmyk;1-(1-process)*product(1-tint*alternate)","alternate_cmyk":self.named.recipe.inks.iter().zip(&self.alternates).map(|(i,a)|(&i.id,a)).collect::<std::collections::BTreeMap<_,_>>(),"fallback_precision":"continuous_normalized_f64_no_extra_byte_projection","ordinary_recipe_preview":"replaced_only_for_this_explicit_combined_delivery"})
    }
}
pub fn combine<'a>(
    document: &'a Document,
    scale: u32,
    process: &[u8],
    mix: &ProcessMix,
    control: &Control,
) -> Result<Combined<'a>, Error> {
    let alternates = mix.validate(document)?;
    let named = prepare(document, scale, control)?;
    let n = named.recipe.inks.len();
    if process.len() != named.width as usize * named.height as usize * 4 {
        return Err(Error::new(
            "INVALID_REQUEST",
            "Process and named plate dimensions must agree",
        ));
    }
    let mut samples = Vec::with_capacity(process.len() + named.samples.len());
    let mut fallback = Vec::with_capacity(process.len());
    for (index, (p, q)) in process
        .as_chunks::<4>()
        .0
        .iter()
        .zip(named.samples.chunks_exact(n))
        .enumerate()
    {
        if index.is_multiple_of(4096) {
            control.check()?;
        }
        samples.extend_from_slice(p);
        samples.extend_from_slice(q);
        for c in 0..4 {
            let absence = q
                .iter()
                .zip(&alternates)
                .fold(1.0 - p[c] as f64 / 255.0, |v, (&t, a)| {
                    v * (1.0 - t as f64 / 255.0 * a[c])
                });
            fallback.push(1.0 - absence);
        }
    }
    control.check()?;
    Ok(Combined {
        named,
        alternates,
        samples,
        fallback,
        process_hash: assets::sha256(process),
    })
}
impl Recipe {
    pub fn validate(&self, document: &Document) -> Result<(), Error> {
        if self.inks.is_empty() || self.inks.len() > MAX_INKS {
            return Err(limit("An ink recipe requires 1..=8 independent named inks"));
        }
        let mut ids = HashSet::new();
        for ink in &self.inks {
            if !crate::model::valid_id(&ink.id)
                || !ids.insert(&ink.id)
                || ink.name.is_empty()
                || ink.name.len() > 256
                || ink
                    .name
                    .chars()
                    .any(|c| c.is_control() || matches!(c, '\u{fffe}' | '\u{ffff}'))
            {
                return Err(Error::new(
                    "INVALID_DOCUMENT",
                    "Recipe ink IDs must be unique and portable; names must contain 1..256 valid UTF-8 bytes",
                ));
            }
            crate::channels::get(document, &ink.channel)?;
            if let Some(id) = &ink.mask_channel {
                crate::channels::get(document, id)?;
            }
            if !(2..=MAX_KNOTS).contains(&ink.curve.len())
                || ink.curve[0][0] != 0.0
                || ink.curve.last().unwrap()[0] != 1.0
                || ink.curve.windows(2).any(|p| p[0][0] >= p[1][0])
                || ink
                    .curve
                    .iter()
                    .flatten()
                    .any(|v| !v.is_finite() || !(0.0..=1.0).contains(v))
            {
                return Err(Error::new(
                    "INVALID_DOCUMENT",
                    "Ink curves need 2..64 finite normalized knots with increasing inputs and endpoints 0 and 1",
                ));
            }
        }
        if let Preview::Corners { linear_rgb } = &self.preview
            && (linear_rgb.len() != 1 << self.inks.len()
                || linear_rgb
                    .iter()
                    .flatten()
                    .any(|v| !v.is_finite() || !(0.0..=1.0).contains(v)))
        {
            return Err(Error::new(
                "INVALID_DOCUMENT",
                "Ink preview needs 2^ink_count normalized linear-RGB corners",
            ));
        }
        Ok(())
    }
    pub(crate) fn corners(&self) -> Vec<[u16; 3]> {
        let decode = |v: u8| {
            let x = v as f64 / 255.0;
            if x <= 0.04045 {
                x / 12.92
            } else {
                ((x + 0.055) / 1.055).powf(2.4)
            }
        };
        (0..1usize << self.inks.len())
            .map(|bits| {
                let value = match &self.preview {
                    Preview::Corners { linear_rgb } => linear_rgb[bits],
                    Preview::Transmittance { paper_srgb } => std::array::from_fn(|c| {
                        self.inks
                            .iter()
                            .enumerate()
                            .filter(|(i, _)| bits & (1 << i) != 0)
                            .fold(decode(paper_srgb[c]), |v, (_, ink)| {
                                v * decode(ink.alternate_srgb[c])
                            })
                    }),
                };
                value.map(|v| (v * 65535.0).round() as u16)
            })
            .collect()
    }
}
pub fn validate(document: &Document) -> Result<(), Error> {
    if let Some(recipe) = &document.ink_recipe {
        recipe.validate(document)?;
    }
    Ok(())
}
pub fn inspect(document: &Document) -> Value {
    document.ink_recipe.as_ref().map(|r| json!({"recipe":r,"source_channels":r.inks.iter().map(|i| &i.channel).collect::<Vec<_>>(),"nonprinting_until_explicit_delivery":true,"source_hashes":r.inks.iter().map(|i| (&i.id,assets::sha256(&render::unhex(&document.channels[&i.channel].plane.gray_hex)))).collect::<std::collections::BTreeMap<_,_>>(),"mask_source_hashes":r.inks.iter().filter_map(|i| i.mask_channel.as_ref().map(|id| (&i.id,assets::sha256(&render::unhex(&document.channels[id].plane.gray_hex))))).collect::<std::collections::BTreeMap<_,_>>()})).unwrap_or(Value::Null)
}
fn table(ink: &Ink) -> Vec<num_rational::BigRational> {
    use num_rational::BigRational as Rat;
    let knots: Vec<_> = ink
        .curve
        .iter()
        .map(|p| {
            (
                Rat::from_float(p[0]).unwrap(),
                Rat::from_float(p[1]).unwrap(),
            )
        })
        .collect();
    let mut at = 1;
    (0u32..256)
        .map(|value| {
            let x = Rat::new(value.into(), 255.into());
            while at + 1 < knots.len() && knots[at].0 < x {
                at += 1;
            }
            let (a, b) = (&knots[at - 1], &knots[at]);
            let t = (x - &a.0) / (&b.0 - &a.0);
            &a.1 + t * (&b.1 - &a.1)
        })
        .collect()
}
pub struct Prepared<'a> {
    pub recipe: &'a Recipe,
    pub width: u32,
    pub height: u32,
    pub ppi: f64,
    pub samples: Vec<u8>,
    pub corners: Vec<[u16; 3]>,
    source_hashes: Vec<(String, Option<String>)>,
}
impl Prepared<'_> {
    pub(crate) fn check_mixing_work(&self) -> Result<(), Error> {
        let n = self.recipe.inks.len();
        if self.width as u64 * self.height as u64 * (n as u64 + 1) * (1 << n) > MAX_WORK {
            return Err(limit(
                "Ink preview exceeds the bounded corner-mixing work budget",
            ));
        }
        Ok(())
    }
    pub fn preview(&self, control: &Control) -> Result<Vec<u8>, Error> {
        self.check_mixing_work()?;
        let n = self.recipe.inks.len();
        let mut rgba = Vec::with_capacity(self.width as usize * self.height as usize * 4);
        for (index, p) in self.samples.chunks_exact(n).enumerate() {
            if index.is_multiple_of(4096) {
                control.check()?;
            }
            let mut weights = [0.0; 1 << MAX_INKS];
            weights[0] = 1.0;
            for (i, &sample) in p.iter().enumerate() {
                let q = sample as f64 / 255.0;
                for j in 0..1 << i {
                    weights[j + (1 << i)] = weights[j] * q;
                    weights[j] *= 1.0 - q;
                }
            }
            for c in 0..3 {
                let linear = self
                    .corners
                    .iter()
                    .zip(weights)
                    .map(|(p, w)| p[c] as f64 / 65535.0 * w)
                    .sum::<f64>()
                    .clamp(0.0, 1.0);
                let encoded = if linear <= 0.0031308 {
                    linear * 12.92
                } else {
                    1.055 * linear.powf(1.0 / 2.4) - 0.055
                };
                rgba.push((encoded * 255.0).round() as u8);
            }
            rgba.push(255);
        }
        control.check()?;
        Ok(rgba)
    }
    pub fn receipt(&self) -> Value {
        json!({"width":self.width,"height":self.height,"resolution_ppi":self.ppi,"channels":self.recipe.inks.iter().zip(&self.source_hashes).map(|(i,(source,mask))|json!({"id":i.id,"name":i.name,"source_channel":i.channel,"source_sha256":source,"mask_channel":i.mask_channel,"mask_sha256":mask,"pdf_colorant":format!("Inkbolt.{}",i.id),"curve":i.curve,"alternate_srgb":i.alternate_srgb})).collect::<Vec<_>>(),"interleaved_sha256":assets::sha256(&self.samples),"sample_encoding":"ink_amount_u8;0_none_255_full;recipe_order","preview_model":self.recipe.preview,"preview_corners_linear_rgb16":self.corners,"corner_order":"ink_0_is_least_significant_bit;zero_is_paper","source_retained":true})
    }
}
pub fn prepare<'a>(
    document: &'a Document,
    scale: u32,
    control: &Control,
) -> Result<Prepared<'a>, Error> {
    control.check()?;
    crate::validate(document)?;
    let recipe = document.ink_recipe.as_ref().ok_or_else(|| {
        Error::new(
            "INVALID_REQUEST",
            "Explicit named-ink delivery requires a retained ink_recipe",
        )
    })?;
    if !(1..=4).contains(&scale) {
        return Err(Error::new(
            "INVALID_REQUEST",
            "Ink separation scale must be in 1..=4",
        ));
    }
    let [width, height] =
        crate::vector_canvas::logical_size(document).map(|v| (v * scale as f64).ceil() as u32);
    if width as u64 * height as u64 > render::MAX_RENDER_PIXELS {
        return Err(limit("Ink separations exceed the output pixel budget"));
    }
    let source: Vec<_> = recipe
        .inks
        .iter()
        .map(|i| render::unhex(&document.channels[&i.channel].plane.gray_hex))
        .collect();
    let tables: Vec<_> = recipe.inks.iter().map(table).collect();
    let masks: Vec<_> = recipe
        .inks
        .iter()
        .map(|ink| {
            ink.mask_channel
                .as_ref()
                .map(|id| render::unhex(&document.channels[id].plane.gray_hex))
        })
        .collect();
    let mut cache = vec![vec![u16::MAX; 65536]; recipe.inks.len()];
    let mut samples = Vec::with_capacity(width as usize * height as usize * recipe.inks.len());
    for y in 0..height {
        control.check()?;
        for x in 0..width {
            let at = (y / scale) as usize * document.width as usize + (x / scale) as usize;
            for (i, plane) in source.iter().enumerate() {
                use num_traits::ToPrimitive;
                let value = plane[at] as usize;
                let mask = masks[i].as_ref().map_or(255, |p| p[at]);
                let slot = value * 256 + mask as usize;
                if cache[i][slot] == u16::MAX {
                    // Curve and optional mask are multiplied as exact rationals;
                    // project once, with ties rounded upward, to the delivery byte.
                    let q = &tables[i][value];
                    cache[i][slot] = ((q.numer() * (mask as u16 * 2) + q.denom())
                        / (q.denom() * 2u16))
                        .to_u16()
                        .unwrap();
                }
                samples.push(cache[i][slot] as u8);
            }
        }
    }
    Ok(Prepared {
        recipe,
        width,
        height,
        ppi: document.resolution_ppi * scale as f64,
        samples,
        corners: recipe.corners(),
        source_hashes: source
            .iter()
            .zip(&masks)
            .map(|(source, mask)| {
                (
                    assets::sha256(source),
                    mask.as_ref().map(|m| assets::sha256(m)),
                )
            })
            .collect(),
    })
}
pub fn export(document: &Document, scale: u32, control: &Control) -> Result<Value, Error> {
    let prepared = prepare(document, scale, control)?;
    let mut plates = Vec::new();
    for (i, ink) in prepared.recipe.inks.iter().enumerate() {
        control.check()?;
        let values: Vec<_> = prepared
            .samples
            .chunks_exact(prepared.recipe.inks.len())
            .map(|p| p[i])
            .collect();
        let bytes =
            crate::proof::scalar_png(prepared.width, prepared.height, &values, prepared.ppi)?;
        plates.push(json!({"id":ink.id,"name":ink.name,"media_type":"image/png","encoding":"base64","data":STANDARD.encode(&bytes),"sha256":assets::sha256(&bytes),"sample_sha256":assets::sha256(&values),"minimum":values.iter().min().unwrap(),"maximum":values.iter().max().unwrap(),"mean_fraction":values.iter().map(|&v|v as u64).sum::<u64>() as f64/(255.0*values.len() as f64)}));
    }
    let rgb = prepared.preview(control)?;
    let (profile, _) = profiles::resolve(&profiles::Profile::Builtin {
        name: profiles::Builtin::Srgb,
    })?;
    let bytes = render::encode_png_with_profile(
        prepared.width,
        prepared.height,
        &rgb,
        prepared.ppi,
        Some(&profile),
    )?;
    let result = json!({"inks":prepared.receipt(),"plates":plates,"preview":{"media_type":"image/png","encoding":"base64","data":STANDARD.encode(&bytes),"sha256":assets::sha256(&bytes),"sample_sha256":assets::sha256(&rgb),"icc_sha256":assets::sha256(&profile)},"losses":["The recipe maps original saved scalar bytes through explicit curves and rounds once to unsigned ink amounts. Sources and editable curves remain unchanged.","The displayed mixture uses the declared linear-RGB corner model, quantized once to 16-bit corners. This is a supplied appearance model, not physical press certification.","Ordinary artwork, unrelated saved channels and image transparency do not enter this explicit plate delivery. Retain the complete snapshot; use calibrated CMYK proof/export for process artwork."]});
    if serde_json::to_vec(&result)
        .map_err(|_| Error::new("EXPORT_ERROR", "Unable to encode ink result"))?
        .len()
        > crate::publish::MAX_OUTPUT_BYTES
    {
        return Err(limit("Named-ink artifacts exceed the bounded output size"));
    }
    control.check()?;
    Ok(result)
}
