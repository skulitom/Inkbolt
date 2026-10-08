//! Flatten native vector ink composition into calibrated, independent PDF plates.
use super::*;
use crate::{control::Control, prepress as native, profiles, render_quality::Antialias};

#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum SpotFallback {
    MultiplicativeDeclared,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct PrepressOptions {
    pub profile: profiles::cmyk::Source,
    #[serde(default)]
    pub intent: profiles::Intent,
    #[serde(default = "crate::scale")]
    pub raster_scale: u32,
    #[serde(default)]
    pub antialias: Antialias,
    pub spot_fallback: Option<SpotFallback>,
    pub marks: Option<super::Marks>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub ink_bindings: Vec<native::InkBinding>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub adjustment_policy: Option<native::AdjustmentPolicy>,
}

pub(super) fn export(
    document: &Document,
    resources: &Resources,
    options: &Options,
    settings: &PrepressOptions,
    policy: Option<metadata::Policy>,
    control: &Control,
) -> Result<Value, Error> {
    control.check()?;
    if options.color != ColorDelivery::Display
        || (options.include_bleed && options.artboards.is_none())
    {
        return Err(Error::new(
            "INVALID_REQUEST",
            "Native flattened prepress is a separate color mode; bleed needs an artboard selection",
        ));
    }
    let routes = native::bindings::Resolved::new(document, &settings.ink_bindings, control)?;
    let expanded = crate::instances::evaluate(document)?;
    let document = expanded.as_ref().unwrap_or(document);
    let pages: Vec<Option<usize>> = options
        .artboards
        .as_ref()
        .map(|s| boards::select(document, s))
        .transpose()?
        .map(|v| v.into_iter().map(Some).collect())
        .unwrap_or_else(|| vec![None]);
    let mut writer = Writer::default();
    let catalog = writer.add(Vec::new())?;
    let tree = writer.add(Vec::new())?;
    // Pin file input once, so every selected page uses exactly the same bytes.
    let profile = profiles::cmyk::read_source(&settings.profile)?;
    let source = profiles::cmyk::Source::Icc {
        data: STANDARD.encode(&profile),
    };
    let icc = writer.stream(
        "/N 4 /Alternate /DeviceCMYK /Range [0 1 0 1 0 1 0 1]",
        &profile,
    )?;
    let mut references = Vec::new();
    let mut receipts = Vec::new();
    let mut envelopes = Vec::new();
    let mut color_receipt = Value::Null;
    let mut work = 0u64;
    for selected in pages {
        control.check()?;
        let scoped = selected
            .map(|i| boards::standalone(document, &document.items[i].id, options.include_bleed))
            .transpose()?;
        let page = scoped.as_ref().unwrap_or(document);
        let prepared = native::prepare_resolved(
            page,
            &native::Options {
                profile: source.clone(),
                intent: settings.intent,
                raster_scale: settings.raster_scale,
                antialias: settings.antialias,
                artboard_id: None,
                include_bleed: false,
                samples: Vec::new(),
                ink_bindings: settings.ink_bindings.clone(),
                adjustment_policy: settings.adjustment_policy,
            },
            resources,
            control,
            &routes,
        )?;
        writer.pixels += prepared.dimensions[0] as u64 * prepared.dimensions[1] as u64;
        work += prepared.work;
        if writer.pixels > MAX_IMAGE_PIXELS || work > native::MAX_WORK {
            return Err(limit(
                "Native flattened pages exceed the aggregate pixel or channel-aware work budget",
            ));
        }
        if !prepared.spots.is_empty() && settings.spot_fallback.is_none() {
            return Err(Error::new(
                "INVALID_REQUEST",
                "Native spots require explicit spot_fallback:multiplicative_declared for the PDF alternate appearance",
            ));
        }
        let alternates = prepared.alternates()?;
        let space = super::combined::channel_space(&mut writer, icc, &alternates)?;
        let image=writer.stream(&format!("/Type /XObject /Subtype /Image /Width {} /Height {} /ColorSpace {space} 0 R /BitsPerComponent 8 /Interpolate false /Intent /RelativeColorimetric",prepared.dimensions[0],prepared.dimensions[1]),&prepared.samples)?;
        let bleed = if options.include_bleed {
            selected
                .map(|i| {
                    let Content::Frame { frame } = &document.items[i].content else {
                        unreachable!()
                    };
                    frame.bleed
                })
                .unwrap_or_default()
        } else {
            boards::Insets::default()
        };
        let layout = super::marks::Layout::new(
            prepared.logical_size,
            prepared.resolution_ppi,
            bleed,
            settings.marks,
        )?;
        let media = layout.coordinates(layout.media);
        let trim = layout.coordinates(layout.trim);
        let bounds = layout.coordinates(layout.bleed);
        let pixel_physical =
            72.0 / (prepared.resolution_ppi * prepared.raster_scale as f64 * layout.user_unit);
        let image_size = prepared.dimensions.map(|v| v as f64 * pixel_physical);
        let mut content = String::from("q\n/RelativeColorimetric ri\n");
        if prepared
            .dimensions
            .map(|v| v as f64 / prepared.raster_scale as f64)
            != prepared.logical_size
        {
            content.push_str(&format!(
                "{} {} {} {} re W n\n",
                number(bounds[0])?,
                number(bounds[1])?,
                number(bounds[2] - bounds[0])?,
                number(bounds[3] - bounds[1])?
            ));
        }
        content.push_str(&format!(
            "{} 0 0 {} {} {} cm\n/Im Do\nQ\n",
            number(image_size[0])?,
            number(image_size[1])?,
            number(bounds[0])?,
            number(bounds[3] - image_size[1])?
        ));
        let marks = layout.emit(&mut writer, &mut content)?;
        let content = writer.stream("", content.as_bytes())?;
        let mark_resource = marks
            .map(|id| format!("/ColorSpace << /Marks {id} 0 R >>"))
            .unwrap_or_default();
        let id=writer.add(format!("<< /Type /Page /Parent {tree} 0 R /MediaBox [{}] /CropBox [{}] /BleedBox [{}] /TrimBox [{}] /UserUnit {} /Resources << /XObject << /Im {image} 0 R >> {mark_resource} >> /Contents {content} 0 R >>",numbers(&media)?,numbers(&media)?,numbers(&bounds)?,numbers(&trim)?,number(layout.user_unit)?))?;
        references.push(format!("{id} 0 R"));
        color_receipt = prepared.profile_receipt(true);
        let artboard_id = selected.map(|i| &document.items[i].id);
        let fallback = json!({"model":settings.spot_fallback,"alternate_cmyk":alternates.iter().map(|(id,v)|(id.clone(),json!(v))).collect::<BTreeMap<_,_>>(),"physical_ink_certification":false});
        let receipt = json!({"index":receipts.len(),"artboard_id":artboard_id,"logical_size":prepared.logical_size,"physical_points":[layout.media[2],layout.media[3]],"artwork_physical_points":[layout.bleed[2]-layout.bleed[0],layout.bleed[3]-layout.bleed[1]],"resolution_ppi":prepared.resolution_ppi,"raster_ppi":prepared.resolution_ppi*prepared.raster_scale as f64,"pixel_dimensions":prepared.dimensions,"media_box":media,"bleed_box":bounds,"trim_box":trim,"user_unit":layout.user_unit,"coordinates":"pdf_bottom_left_in_user_units","render_settings":prepared.sampling_receipt(),"inks":prepared.ink_receipt(),"image_sources":prepared.image_sources,"coverage_sources":prepared.coverage_sources,"blending":crate::prepress::blending_receipt(),"spot_fallback":fallback,"marks":layout.receipt()});
        let packet = metadata::packet(
            page,
            ExportFormat::Pdf,
            settings.raster_scale,
            policy.unwrap_or_default(),
        )?
        .map(|s| {
            let mut value: Value = serde_json::from_str(&s).unwrap();
            value["delivery"]["profile"] = color_receipt.clone();
            value["delivery"]["native_prepress"] = receipt.clone();
            String::from_utf8(metadata::canonical(&value)).unwrap()
        });
        if packet
            .as_ref()
            .is_some_and(|p| p.len() > metadata::MAX_PACKET_BYTES)
        {
            return Err(limit(
                "Native prepress metadata exceeds its envelope budget",
            ));
        }
        envelopes.push(json!({"artboard_id":artboard_id,"packet":packet.map(|s|serde_json::from_str::<Value>(&s).unwrap())}));
        receipts.push(receipt);
    }
    let packet = if envelopes.iter().any(|p| !p["packet"].is_null()) {
        Some(
            String::from_utf8(metadata::canonical(
                &json!({"schema":"inkbolt.pdf.metadata.v1","pages":envelopes}),
            ))
            .unwrap(),
        )
    } else {
        None
    };
    let meta = if let Some(packet) = &packet {
        let xmp = format!(
            "<rdf:RDF xmlns:rdf=\"http://www.w3.org/1999/02/22-rdf-syntax-ns#\"><rdf:Description rdf:about=\"\" xmlns:inkbolt=\"urn:inkbolt:pdf:metadata:1\"><inkbolt:packet>{}</inkbolt:packet></rdf:Description></rdf:RDF>",
            xml(packet)
        );
        let id = writer.stream("/Type /Metadata /Subtype /XML", xmp.as_bytes())?;
        format!("/Metadata {id} 0 R")
    } else {
        String::new()
    };
    writer.replace(
        tree,
        format!(
            "<< /Type /Pages /Count {} /Kids [{}] >>",
            references.len(),
            references.join(" ")
        ),
    )?;
    writer.replace(
        catalog,
        format!("<< /Type /Catalog /Pages {tree} 0 R {meta} >>"),
    )?;
    let info = writer.add("<< /Producer (Inkbolt) >>".to_string())?;
    let pixels = writer.pixels;
    let commands = writer.commands;
    let bytes = writer.finish(catalog, info)?;
    control.check()?;
    let mut result = json!({"media_type":"application/pdf","encoding":"base64","data":STANDARD.encode(&bytes),"pages":receipts,"color_profile":color_receipt,"pdf":{"version":"1.7","include_bleed":options.include_bleed,"artboards":options.artboards,"path_commands":commands,"image_pixels":pixels,"text_glyphs":0,"color":"NChannel_CMYK_and_named8","color_delivery":"native_flattened_prepress","raster_scale":settings.raster_scale,"editable_source":"snapshot","deterministic":true,"conformance":"PDF_1.7;no_PDF_X_or_press_certification"},"losses":["Artwork, glyphs, transparency and overprint are flattened into independent native ink amounts at the declared sample density. Keep the original snapshot and resources for editing; no editable reimport is claimed.","Native CMYK operands bypass color conversion. Other process paints convert before ink composition through the supplied profile. Geometry coverage, finite color-table precision and one byte projection bound the delivered samples.","Spot identity and ink amounts are retained. The explicitly selected multiplicative declared-color fallback describes alternate display appearance only; it is not a spectral or physical press model, and PDF consumers may apply different display policies.","Marks use the All separation outside the bleed area. Plate inspection covers artwork only; PDF media includes the marks. Matching native colorants are required to retain ink numbers on output. No print job is sent."]});
    if !settings.ink_bindings.is_empty() {
        result["losses"][2] = json!(
            "Explicit ink_bindings interpret retained source spots as declared destination inks before composition. Unbound identities remain separate; original source declarations and applied mappings are retained in receipts. The chosen destination alternate describes display appearance only, not a spectral or physical press model."
        );
    }
    if settings.adjustment_policy.is_some() {
        result["losses"][1] = json!(
            "Native CMYK paint operands bypass conversion until an explicit adjustment changes their process colour. The selected adjustment policy observes process inks through the output profile, applies the original RGB operators and converts changed values back; alpha and named ink amounts remain unchanged. Other process paints convert before ink composition. Geometry coverage, finite colour-table precision and one byte projection bound delivered samples."
        );
    }
    result["losses"].as_array_mut().unwrap().push(json!(
        "An explicitly viewed retained HDR source is composited in full precision, projected through its declared view and reconstructed as encoded RGB before process conversion. Native ink identities do not cross that display boundary. Retained nonprinting recipes and RGB output associations do not change working source artwork. Source snapshots remain unchanged."
    ));
    metadata::annotate(&mut result, packet.as_deref(), policy, false);
    Ok(result)
}
