//! Read-only print observation, scalar process plates and measured color loss.
use crate::{
    Document, Error, assets, boards, control::Control, model::limit, profiles, render,
    sessions::Resources,
};
use base64::{Engine, engine::general_purpose::STANDARD};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

pub const MAX_SAMPLES: usize = 64;
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Options {
    pub print: crate::pdf::PrintOptions,
    #[serde(default)]
    pub view_intent: profiles::Intent,
    pub delta_e76_threshold: f64,
    #[serde(default)]
    pub samples: Vec<[u32; 2]>,
    pub artboard_id: Option<String>,
    #[serde(default)]
    pub include_bleed: bool,
    #[serde(default)]
    pub gamut: profiles::gamut::Mode,
}
pub(crate) fn scalar_png(
    width: u32,
    height: u32,
    values: &[u8],
    ppi: f64,
) -> Result<Vec<u8>, Error> {
    let mut bytes = Vec::new();
    {
        let mut encoder = png::Encoder::new(&mut bytes, width, height);
        encoder.set_color(png::ColorType::Grayscale);
        encoder.set_depth(png::BitDepth::Eight);
        let ppm = (ppi / 0.0254).round() as u32;
        encoder.set_pixel_dims(Some(png::PixelDimensions {
            xppu: ppm,
            yppu: ppm,
            unit: png::Unit::Meter,
        }));
        let mut writer = encoder
            .write_header()
            .map_err(|_| Error::new("EXPORT_ERROR", "Unable to encode proof plane"))?;
        writer
            .write_image_data(values)
            .map_err(|_| Error::new("EXPORT_ERROR", "Unable to encode proof samples"))?;
    }
    Ok(bytes)
}
fn artifact(bytes: Vec<u8>, samples: &[u8]) -> Value {
    json!({"media_type":"image/png","encoding":"base64","sha256":assets::sha256(&bytes),"data":STANDARD.encode(&bytes),"sample_sha256":assets::sha256(samples)})
}
pub fn inspect(
    document: &Document,
    options: &Options,
    resources: &Resources,
    control: &Control,
) -> Result<Value, Error> {
    control.check()?;
    crate::validate(document)?;
    options.print.validate(document)?;
    if options.print.named_inks.is_some()
        && (options.artboard_id.is_some() || options.include_bleed)
    {
        return Err(Error::new(
            "INVALID_REQUEST",
            "Combined process and named proof requires the whole canvas",
        ));
    }
    if !options.delta_e76_threshold.is_finite()
        || !(0.0..=1000.0).contains(&options.delta_e76_threshold)
        || options.samples.len() > MAX_SAMPLES
        || (options.include_bleed && options.artboard_id.is_none())
    {
        return Err(Error::new(
            "INVALID_REQUEST",
            "Proof needs a finite delta_e76_threshold in 0..=1000, at most 64 samples, and an artboard for bleed",
        ));
    }
    let scoped = options
        .artboard_id
        .as_ref()
        .map(|id| boards::standalone(document, id, options.include_bleed))
        .transpose()?;
    let page = scoped.as_ref().unwrap_or(document);
    let plan = crate::render_quality::Plan::for_document(
        page,
        options.print.raster_scale,
        options.print.render_options.as_ref(),
    )?;
    if options
        .samples
        .iter()
        .any(|p| p[0] >= plan.output[0] || p[1] >= plan.output[1])
    {
        return Err(Error::new(
            "INVALID_REQUEST",
            "Proof sample coordinates must address output pixels",
        ));
    }
    control.check()?;
    let converter = profiles::cmyk::Converter::new(&options.print.profile, options.print.intent)?;
    let gamut = if matches!(options.gamut, profiles::gamut::Mode::Off) {
        None
    } else {
        profiles::gamut::Gamut::new(
            &converter.bytes,
            if options.print.intent == profiles::Intent::AbsoluteColorimetric {
                profiles::Intent::AbsoluteColorimetric
            } else {
                profiles::Intent::RelativeColorimetric
            },
        )?
    };
    if matches!(options.gamut, profiles::gamut::Mode::Required) && gamut.is_none() {
        return Err(Error::new(
            "GAMUT_UNAVAILABLE",
            "The supplied profile has no gamut table",
        ));
    }
    let observer = profiles::proof::Observer::new(&converter.bytes, options.view_intent)?;
    control.check()?;
    let raster = render::rasterize_with_options(
        page,
        options.print.raster_scale,
        resources.asset_root.as_deref(),
        resources.font_root.as_deref(),
        options.print.render_options.as_ref(),
    )?;
    let ink = converter.convert(&raster.rgba, options.print.matte, Some(control))?;
    let combined = options
        .print
        .named_inks
        .as_ref()
        .map(|mix| {
            crate::ink_recipes::combine(page, options.print.raster_scale, &ink, mix, control)
        })
        .transpose()?;
    let count = ink.len() / 4;
    let mut preview = Vec::with_capacity(ink.len());
    let mut difference = Vec::with_capacity(count);
    let mut samples = vec![Value::Null; options.samples.len()];
    let mut sum = 0.0;
    let mut maximum = 0.0_f64;
    let mut exceeds = 0u64;
    let mut clipped_pixels = 0u64;
    let mut clipped_channels = [0u64; 3];
    let mut gamut_error = None;
    let mut gamut_outside = Vec::new();
    let mut gamut_unknown = Vec::new();
    let mut gamut_maximum = 0.0_f64;
    let observe = |i: usize, sample: profiles::proof::Sample| {
        let classification = gamut
            .as_ref()
            .and_then(|g| match g.classify(sample.source_xyz) {
                Ok(v) => {
                    gamut_outside.push(if v.value.is_some_and(|x| x != 0.0) {
                        255
                    } else {
                        0
                    });
                    gamut_unknown.push(if v.value.is_none() { 255 } else { 0 });
                    if let Some(x) = v.value {
                        gamut_maximum = gamut_maximum.max(x);
                    }
                    Some(v)
                }
                Err(error) => {
                    gamut_error = Some(error);
                    None
                }
            });
        preview.extend_from_slice(&sample.display_rgb);
        preview.push(255);
        sum += sample.delta_e76;
        maximum = maximum.max(sample.delta_e76);
        let flagged = sample.delta_e76 > options.delta_e76_threshold;
        exceeds += u64::from(flagged);
        difference.push(if flagged { 255 } else { 0 });
        let mut clipped = false;
        for (channel, value) in sample.linear_rgb.iter().enumerate() {
            if !(0.0..=1.0).contains(value) {
                clipped_channels[channel] += 1;
                clipped = true;
            }
        }
        clipped_pixels += u64::from(clipped);
        for (slot, p) in options.samples.iter().enumerate() {
            if i == p[1] as usize * raster.width as usize + p[0] as usize {
                samples[slot] = json!({"pixel":p,"cmyk8":&ink[i*4..i*4+4],"source_xyz_d50":sample.source_xyz,
                    "proof_xyz_d50":sample.proof_xyz,"source_lab_d50":sample.source_lab,"proof_lab_d50":sample.proof_lab,
                    "delta_e76":sample.delta_e76,"linear_srgb":sample.linear_rgb,"preview_rgb8":sample.display_rgb});
                if let Some(inks) = &combined {
                    let n = inks.named.recipe.inks.len();
                    samples[slot]["named8"] = json!(&inks.named.samples[i * n..(i + 1) * n]);
                    samples[slot]["fallback_cmyk"] = json!(&inks.fallback[i * 4..i * 4 + 4]);
                }
                if let Some(value) = &classification {
                    samples[slot]["gamut"] = value.receipt();
                }
            }
        }
    };
    if let Some(inks) = &combined {
        observer.observe_continuous(
            &raster.rgba,
            &inks.fallback,
            options.print.matte,
            control,
            observe,
        )?;
    } else {
        observer.observe(&raster.rgba, &ink, options.print.matte, control, observe)?;
    }
    if let Some(error) = gamut_error {
        return Err(error);
    }
    let ppi = page.resolution_ppi * options.print.raster_scale as f64;
    let preview_artifact = artifact(
        render::encode_png_with_profile(
            raster.width,
            raster.height,
            &preview,
            ppi,
            Some(&observer.display_profile),
        )?,
        &preview,
    );
    let difference_artifact = artifact(
        scalar_png(raster.width, raster.height, &difference, ppi)?,
        &difference,
    );
    let mut plates = serde_json::Map::new();
    for (channel, name) in ["cyan", "magenta", "yellow", "black"].iter().enumerate() {
        control.check()?;
        let values: Vec<_> = ink.as_chunks::<4>().0.iter().map(|p| p[channel]).collect();
        let mut plane = artifact(
            scalar_png(raster.width, raster.height, &values, ppi)?,
            &values,
        );
        plane["minimum"] = json!(values.iter().min().unwrap());
        plane["maximum"] = json!(values.iter().max().unwrap());
        plane["mean_fraction"] =
            json!(values.iter().map(|&v| v as u64).sum::<u64>() as f64 / (255.0 * count as f64));
        plates.insert((*name).into(), plane);
    }
    let total_ink: Vec<u16> = ink
        .as_chunks::<4>()
        .0
        .iter()
        .map(|p| p.iter().map(|&v| v as u16).sum())
        .collect();
    let mut profile = converter.receipt();
    profile["profile_embedded"] = json!(false);
    let mut result = json!({"width":raster.width,"height":raster.height,"resolution_ppi":ppi,
        "matte":options.print.matte,"raster_scale":options.print.raster_scale,
        "artboard_id":options.artboard_id,"include_bleed":options.include_bleed,"render_settings":plan.receipt(),
        "print_profile":profile,"cmyk_sha256":assets::sha256(&ink),"view_intent":options.view_intent,
        "preview":preview_artifact,"preview_profile_sha256":assets::sha256(&observer.display_profile),
        "plates":plates,"plate_encoding":"scalar_ink_amount_0_none_255_full;not_color_or_print_negative",
        "total_ink":{"maximum_fraction":*total_ink.iter().max().unwrap() as f64/255.0,
            "mean_fraction":total_ink.iter().map(|&v| v as u64).sum::<u64>() as f64/(255.0*count as f64)},
        "difference":{"metric":"CIE76_D50_PCS_before_display_clipping","threshold":options.delta_e76_threshold,
            "comparison":"strictly_greater","maximum":maximum,"mean":sum/count as f64,
            "pixels_above_threshold":exceeds,"mask":difference_artifact},
        "display_clipping":{"space":"linear_srgb_before_clamp","pixels":clipped_pixels,"channels":clipped_channels},
        "samples":samples,"source_revision":document.revision,
        "losses":["The proof observes flattened, explicitly matted CMYK8 delivery. Editable source artwork and profiles are unchanged; no print job or file is written.",
            "D50 CIE76 round-trip differences include profile mapping, finite table precision and CMYK8 quantization. Threshold flags are diagnostics, not exact gamut membership or a printing tolerance certification.",
            "The view uses colorimetric profile tables, with optional explicit media-white scaling and no black-point compensation. RGB preview clipping is reported separately from pre-display color differences.",
            "Scalar plates describe process ink amounts only. Spot inks, duotones and overprint simulation remain unsupported; named display alternates become process colors under the existing print contract."]});
    result["gamut"] = if let Some(gamut) = &gamut {
        control.check()?;
        let mut receipt = gamut.receipt();
        receipt["diagnostic_intent"] = json!(if options.print.intent
            == profiles::Intent::AbsoluteColorimetric
        {
            options.print.intent
        } else {
            profiles::Intent::RelativeColorimetric
        });
        receipt["source_scope"] =
            json!("matted_process_source_before_separation;named_ink_physical_gamut_not_inferred");
        receipt["out_of_gamut_pixels"] = json!(gamut_outside.iter().filter(|&&v| v != 0).count());
        receipt["unclassified_pixels"] = json!(gamut_unknown.iter().filter(|&&v| v != 0).count());
        receipt["maximum_value"] = json!(gamut_maximum);
        receipt["mask"] = artifact(
            scalar_png(raster.width, raster.height, &gamut_outside, ppi)?,
            &gamut_outside,
        );
        receipt["unclassified_mask"] = artifact(
            scalar_png(raster.width, raster.height, &gamut_unknown, ppi)?,
            &gamut_unknown,
        );
        receipt
    } else if matches!(options.gamut, profiles::gamut::Mode::Off) {
        json!({"status":"disabled"})
    } else {
        json!({"status":"unavailable","reason":"profile_has_no_gamt_tag","membership_inferred":false})
    };
    if let Some(inks) = &combined {
        let mut named = Vec::new();
        let n = inks.named.recipe.inks.len();
        for (i, definition) in inks.named.recipe.inks.iter().enumerate() {
            control.check()?;
            let values: Vec<_> = inks.named.samples.chunks_exact(n).map(|p| p[i]).collect();
            let mut plane = artifact(
                scalar_png(raster.width, raster.height, &values, ppi)?,
                &values,
            );
            plane["id"] = json!(definition.id);
            plane["name"] = json!(definition.name);
            plane["minimum"] = json!(values.iter().min().unwrap());
            plane["maximum"] = json!(values.iter().max().unwrap());
            plane["mean_fraction"] = json!(
                values.iter().map(|&v| v as u64).sum::<u64>() as f64 / (255.0 * count as f64)
            );
            named.push(plane);
        }
        let totals: Vec<u16> = inks
            .samples
            .chunks_exact(4 + n)
            .map(|p| p.iter().map(|&v| v as u16).sum())
            .collect();
        result["total_ink_including_named"] = json!({"maximum_fraction":*totals.iter().max().unwrap() as f64/255.0,"mean_fraction":totals.iter().map(|&v|v as u64).sum::<u64>() as f64/(255.0*count as f64)});
        result["named_plates"] = json!(named);
        result["inks"] = inks.receipt();
        result["losses"][3] = json!(
            "Process and named scalar planes retain the exact independent delivered bytes. Combined preview observes the explicitly supplied multiplicative CMYK fallback through the process profile, without another byte projection. This approximation does not certify physical ink interaction; the ordinary recipe corner preview is not used in this mode."
        );
    }
    if serde_json::to_vec(&result)
        .map_err(|_| Error::new("EXPORT_ERROR", "Unable to encode proof receipt"))?
        .len()
        > crate::publish::MAX_OUTPUT_BYTES
    {
        return Err(limit("Proof artifacts exceed the bounded output size"));
    }
    control.check()?;
    Ok(result)
}
