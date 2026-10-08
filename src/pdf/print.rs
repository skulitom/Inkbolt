//! Flattened, calibrated CMYK image pages. Editing sources remain independent.
use super::*;
use crate::{control::Control, profiles, render_quality};

fn one() -> u32 {
    1
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct PrintOptions {
    pub profile: profiles::cmyk::Source,
    pub matte: [u8; 3],
    #[serde(default)]
    pub intent: profiles::Intent,
    #[serde(default = "one")]
    pub raster_scale: u32,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub render_options: Option<render_quality::Options>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub named_inks: Option<crate::ink_recipes::ProcessMix>,
}
impl PrintOptions {
    pub(crate) fn validate(&self, document: &Document) -> Result<(), Error> {
        if let Some(mix) = &self.named_inks {
            mix.validate(document)?;
        }
        if document.output_profile.is_some() {
            return Err(Error::new(
                "PROFILE_CONFLICT",
                "Clear the document RGB output association before selecting a CMYK print profile",
            ));
        }
        if !(1..=4).contains(&self.raster_scale)
            || self.render_options.is_some_and(|o| !o.crop_to_canvas)
        {
            return Err(Error::new(
                "INVALID_REQUEST",
                "CMYK pages require raster_scale 1..=4 and crop_to_canvas:true",
            ));
        }
        Ok(())
    }
}

pub(super) fn export(
    document: &Document,
    resources: &Resources,
    options: &Options,
    print: &PrintOptions,
    policy: Option<metadata::Policy>,
    control: Option<&Control>,
) -> Result<Value, Error> {
    if let Some(c) = control {
        c.check()?;
    }
    if options.color != ColorDelivery::Display {
        return Err(Error::new(
            "INVALID_REQUEST",
            "Flattened CMYK print delivery cannot be combined with native_inks",
        ));
    }
    print.validate(document)?;
    if print.named_inks.is_some() && (options.artboards.is_some() || options.include_bleed) {
        return Err(Error::new(
            "INVALID_REQUEST",
            "Combined process and named plates require the whole canvas; crop an explicit source copy first",
        ));
    }
    if options.include_bleed && options.artboards.is_none() {
        return Err(Error::new(
            "INVALID_REQUEST",
            "PDF bleed requires an artboard selection",
        ));
    }
    let converter = profiles::cmyk::Converter::new(&print.profile, print.intent)?;
    let pages: Vec<Option<usize>> = options
        .artboards
        .as_ref()
        .map(|s| boards::select(document, s))
        .transpose()?
        .map(|s| s.into_iter().map(Some).collect())
        .unwrap_or_else(|| vec![None]);
    let mut writer = Writer::default();
    let catalog = writer.add(Vec::new())?;
    let tree = writer.add(Vec::new())?;
    let icc = writer.stream(
        "/N 4 /Alternate /DeviceCMYK /Range [0 1 0 1 0 1 0 1]",
        &converter.bytes,
    )?;
    let mut references = Vec::new();
    let mut receipts = Vec::new();
    let mut envelopes = Vec::new();
    let mut combined_receipt = None;
    for selection in pages {
        if let Some(c) = control {
            c.check()?;
        }
        let scoped = selection
            .map(|i| boards::standalone(document, &document.items[i].id, options.include_bleed))
            .transpose()?;
        let page = scoped.as_ref().unwrap_or(document);
        let plan = render_quality::Plan::for_document(
            page,
            print.raster_scale,
            print.render_options.as_ref(),
        )?;
        writer.pixels += plan.output[0] as u64 * plan.output[1] as u64;
        if writer.pixels > MAX_IMAGE_PIXELS {
            return Err(limit(
                "PDF print pages exceed the aggregate image pixel budget",
            ));
        }
        let logical = crate::vector_canvas::logical_size(page);
        let physical = 72.0 / page.resolution_ppi;
        let user_unit = (logical[0].max(logical[1]) * physical / 14400.0)
            .ceil()
            .max(1.0);
        if user_unit > 75000.0 {
            return Err(limit("PDF page exceeds the supported physical size"));
        }
        let factor = physical / user_unit;
        let width = logical[0] * factor;
        let height = logical[1] * factor;
        let raster = crate::render::rasterize_with_options(
            page,
            print.raster_scale,
            resources.asset_root.as_deref(),
            resources.font_root.as_deref(),
            print.render_options.as_ref(),
        )?;
        let pixels = converter.convert(&raster.rgba, print.matte, control)?;
        let combined = print
            .named_inks
            .as_ref()
            .map(|mix| {
                crate::ink_recipes::combine(
                    page,
                    print.raster_scale,
                    &pixels,
                    mix,
                    control.unwrap_or(&Control::default()),
                )
            })
            .transpose()?;
        let space = if let Some(inks) = &combined {
            combined_receipt = Some(inks.receipt());
            format!("{} 0 R", super::combined::space(&mut writer, icc, inks)?)
        } else {
            format!("[/ICCBased {icc} 0 R]")
        };
        let image = writer.stream(&format!("/Type /XObject /Subtype /Image /Width {} /Height {} /ColorSpace {space} /BitsPerComponent 8 /Interpolate false /Intent /RelativeColorimetric", raster.width, raster.height), combined.as_ref().map_or(pixels.as_slice(), |v| v.samples.as_slice()))?;
        let image_width = raster.width as f64 / print.raster_scale as f64 * factor;
        let image_height = raster.height as f64 / print.raster_scale as f64 * factor;
        let content = format!(
            "q\n/RelativeColorimetric ri\n{} 0 0 {} 0 {} cm\n/Im Do\nQ\n",
            number(image_width)?,
            number(image_height)?,
            number(height - image_height)?
        );
        let content = writer.stream("", content.as_bytes())?;
        let bleed = if options.include_bleed {
            selection
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
        let media = [0.0, 0.0, width, height];
        let trim = [
            bleed.left as f64 * factor,
            bleed.bottom as f64 * factor,
            width - bleed.right as f64 * factor,
            height - bleed.top as f64 * factor,
        ];
        let id = writer.add(format!("<< /Type /Page /Parent {tree} 0 R /MediaBox [{}] /CropBox [{}] /BleedBox [{}] /TrimBox [{}] /UserUnit {} /Resources << /XObject << /Im {image} 0 R >> >> /Contents {content} 0 R >>", numbers(&media)?, numbers(&media)?, numbers(&media)?, numbers(&trim)?, number(user_unit)?))?;
        references.push(format!("{id} 0 R"));
        let artboard_id = selection.map(|i| &document.items[i].id);
        receipts.push(json!({"index":receipts.len(),"artboard_id":artboard_id,"logical_size":logical,"physical_points":[logical[0]*physical,logical[1]*physical],"resolution_ppi":page.resolution_ppi,"raster_ppi":page.resolution_ppi*print.raster_scale as f64,"pixel_dimensions":[raster.width,raster.height],"media_box":media,"trim_box":trim,"user_unit":user_unit,"coordinates":"pdf_bottom_left_in_user_units","render_settings":plan.receipt(),"cmyk_sha256":assets::sha256(&pixels)}));
        let packet = metadata::packet(
            page,
            ExportFormat::Pdf,
            print.raster_scale,
            policy.unwrap_or_default(),
        )?
        .map(|s| {
            let mut value: Value = serde_json::from_str(&s).unwrap();
            value["delivery"]["profile"] = converter.receipt();
            if let Some(inks) = &combined {
                value["delivery"]["named_inks"] = inks.receipt();
            }
            value["delivery"]["physical_points"] =
                json!([logical[0] * physical, logical[1] * physical]);
            String::from_utf8(metadata::canonical(&value)).unwrap()
        });
        if packet
            .as_ref()
            .is_some_and(|s| s.len() > metadata::MAX_PACKET_BYTES)
        {
            return Err(limit(
                "CMYK page metadata exceeds the bounded envelope size",
            ));
        }
        envelopes.push(json!({"artboard_id":artboard_id,"packet":packet.map(|s|serde_json::from_str::<Value>(&s).unwrap())}));
    }
    let packet = if envelopes.iter().any(|v| !v["packet"].is_null()) {
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
    let bytes = writer.finish(catalog, info)?;
    if let Some(c) = control {
        c.check()?;
    }
    let mut result = json!({"media_type":"application/pdf","encoding":"base64","data":STANDARD.encode(bytes),"pages":receipts,"color_profile":converter.receipt(),"pdf":{"version":"1.7","include_bleed":options.include_bleed,"artboards":options.artboards,"path_commands":0,"image_pixels":pixels,"text_glyphs":0,"color":"ICCBased_CMYK8","color_delivery":"flattened_print","matte":print.matte,"raster_scale":print.raster_scale,"editable_source":"snapshot","deterministic":true,"conformance":"PDF_1.7;no_PDF_X_or_press_certification"},"losses":["The selected pages are flattened to display RGB8 at the declared raster density, then composited on the explicit encoded-sRGB matte before CMYK conversion. Source layers, text, native precision and transparency require the retained snapshot.","CMYK separation follows the supplied profile and selected intent without black-point compensation or endpoint fixups. Finite lookup precision and byte quantization are irreversible; this is not a gamut proof or a calibrated press certification.","Named ink display previews become process CMYK. Spot channels and overprint are not simulated; unsupported overprint fails unless the caller explicitly bakes display artwork first.","PDF consumers may reconvert calibrated colors for a different output device; use the matching printing condition to preserve CMYK numbers. No print job is sent, and PDF reimport is not implemented."]});
    metadata::annotate(&mut result, packet.as_deref(), policy, false);
    if let Some(inks) = combined_receipt {
        result["inks"] = inks;
        result["pdf"]["color"] = json!("NChannel_CMYK_and_named8");
        result["pdf"]["color_delivery"] = json!("combined_process_and_named");
        result["losses"][2] = json!(
            "Ordinary named-paint alternates enter the calibrated process artwork. The explicit saved recipe independently supplies additional named plates. Its supplied multiplicative CMYK fallback models display appearance only; it does not certify physical ink interaction or preserve vector overprint groups."
        );
    }
    if result.get("metadata").is_some() {
        result["metadata"]["color"] = json!("explicit_CMYK_print_profile");
        result["metadata"]["resolution"] = json!("per_page_document_ppi_times_print_raster_scale");
    }
    Ok(result)
}
