//! Independent named-ink image delivery from a retained scalar recipe.
use super::*;
use crate::{control::Control, ink_recipes, profiles};

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct InkOptions {
    #[serde(default = "crate::scale")]
    pub raster_scale: u32,
}

// Original tensor interpolation using only bounded PDF calculator operators.
fn tint_function(corners: &[[u16; 3]], inks: usize) -> String {
    fn channel(
        out: &mut String,
        corners: &[[u16; 3]],
        inks: usize,
        dimension: usize,
        corner: usize,
        component: usize,
        above: usize,
    ) {
        if dimension == 0 {
            out.push_str(&format!("{} 65535 div ", corners[corner][component]));
            return;
        }
        channel(out, corners, inks, dimension - 1, corner, component, above);
        channel(
            out,
            corners,
            inks,
            dimension - 1,
            corner + (1 << (dimension - 1)),
            component,
            above + 1,
        );
        // x, y -> x + (y - x) * input[dimension - 1].
        out.push_str(&format!(
            "1 index sub {} index mul add ",
            inks - dimension + above + 2
        ));
    }
    let mut out = String::from("{ ");
    for c in 0..3 {
        channel(&mut out, corners, inks, inks, 0, c, c);
        out.push_str(
            "dup 0.0031308 le { 12.92 mul } { 1 2.4 div exp 1.055 mul 0.055 sub } ifelse ",
        );
    }
    out.push_str(&format!("{} 3 roll ", inks + 3));
    for _ in 0..inks {
        out.push_str("pop ");
    }
    out.push('}');
    out
}
pub(super) fn export(
    document: &Document,
    options: &Options,
    ink: &InkOptions,
    policy: Option<metadata::Policy>,
    control: &Control,
) -> Result<Value, Error> {
    if options.print.is_some()
        || options.color != ColorDelivery::Display
        || options.artboards.is_some()
        || options.include_bleed
    {
        return Err(Error::new(
            "INVALID_REQUEST",
            "Named scalar recipes deliver their whole canvas; print, native_inks, artboard and bleed settings cannot be combined",
        ));
    }
    if document.output_profile.is_some() {
        return Err(Error::new(
            "PROFILE_CONFLICT",
            "Named-ink recipe delivery uses its own explicit corner appearance; clear an unrelated RGB output association on a copy",
        ));
    }
    let prepared = ink_recipes::prepare(document, ink.raster_scale, control)?;
    prepared.check_mixing_work()?;
    let (profile, _) = profiles::resolve(&profiles::Profile::Builtin {
        name: profiles::Builtin::Srgb,
    })?;
    let physical = 72.0 / document.resolution_ppi;
    let logical = crate::vector_canvas::logical_size(document);
    let unit = (logical[0].max(logical[1]) * physical / 14400.0)
        .ceil()
        .max(1.0);
    if unit > 75000.0 {
        return Err(limit("Named-ink page exceeds the supported physical size"));
    }
    let width = logical[0] * physical / unit;
    let height = logical[1] * physical / unit;
    let mut writer = Writer::default();
    let catalog = writer.add(Vec::new())?;
    let tree = writer.add(Vec::new())?;
    let icc = writer.stream("/N 3 /Alternate /DeviceRGB /Range [0 1 0 1 0 1]", &profile)?;
    let n = prepared.recipe.inks.len();
    let domain = std::iter::repeat_n("0 1", n).collect::<Vec<_>>().join(" ");
    let function = writer.stream(
        &format!("/FunctionType 4 /Domain [{domain}] /Range [0 1 0 1 0 1]"),
        tint_function(&prepared.corners, n).as_bytes(),
    )?;
    let names = prepared
        .recipe
        .inks
        .iter()
        .map(|i| format!("/Inkbolt.{}", i.id))
        .collect::<Vec<_>>()
        .join(" ");
    let space = writer.add(format!(
        "[/DeviceN [{names}] [/ICCBased {icc} 0 R] {function} 0 R]"
    ))?;
    let image = writer.stream(&format!("/Type /XObject /Subtype /Image /Width {} /Height {} /ColorSpace {space} 0 R /BitsPerComponent 8 /Decode [{domain}] /Interpolate false /Intent /RelativeColorimetric",prepared.width,prepared.height),&prepared.samples)?;
    let content = writer.stream(
        "",
        format!(
            "q\n/RelativeColorimetric ri\n{} 0 0 {} 0 {} cm\n/Im Do\nQ\n",
            number(prepared.width as f64 / ink.raster_scale as f64 * physical / unit)?,
            number(prepared.height as f64 / ink.raster_scale as f64 * physical / unit)?,
            number(height - prepared.height as f64 / ink.raster_scale as f64 * physical / unit)?
        )
        .as_bytes(),
    )?;
    let page = writer.add(format!("<< /Type /Page /Parent {tree} 0 R /MediaBox [0 0 {} {}] /CropBox [0 0 {} {}] /TrimBox [0 0 {} {}] /BleedBox [0 0 {} {}] /UserUnit {} /Resources << /XObject << /Im {image} 0 R >> >> /Contents {content} 0 R >>",number(width)?,number(height)?,number(width)?,number(height)?,number(width)?,number(height)?,number(width)?,number(height)?,number(unit)?))?;
    writer.replace(
        tree,
        format!("<< /Type /Pages /Count 1 /Kids [{page} 0 R] >>"),
    )?;
    let packet = metadata::packet(
        document,
        ExportFormat::Pdf,
        ink.raster_scale,
        policy.unwrap_or_default(),
    )?
    .map(|s| {
        let mut value: Value = serde_json::from_str(&s).unwrap();
        value["delivery"]["color"] = json!("DeviceN_named_inks");
        value["delivery"]["profile"] =
            json!({"role":"alternate_srgb","icc_sha256":assets::sha256(&profile)});
        value["delivery"]["resolution_ppi"] = json!(prepared.ppi);
        String::from_utf8(metadata::canonical(&value)).unwrap()
    });
    if packet
        .as_ref()
        .is_some_and(|p| p.len() > metadata::MAX_PACKET_BYTES)
    {
        return Err(limit("Named-ink metadata exceeds its envelope limit"));
    }
    let info = packet.as_deref().map(|p| writer.stream("/Type /Metadata /Subtype /XML",format!("<rdf:RDF xmlns:rdf=\"http://www.w3.org/1999/02/22-rdf-syntax-ns#\"><rdf:Description rdf:about=\"\" xmlns:inkbolt=\"urn:inkbolt:pdf:metadata:1\"><inkbolt:packet>{}</inkbolt:packet></rdf:Description></rdf:RDF>",xml(p)).as_bytes())).transpose()?;
    writer.replace(
        catalog,
        format!(
            "<< /Type /Catalog /Pages {tree} 0 R {} >>",
            info.map(|i| format!("/Metadata {i} 0 R"))
                .unwrap_or_default()
        ),
    )?;
    control.check()?;
    let producer = writer.add("<< /Producer (Inkbolt) >>".to_string())?;
    let bytes = writer.finish(catalog, producer)?;
    let mut result = json!({"media_type":"application/pdf","encoding":"base64","data":STANDARD.encode(bytes),
        "inks":prepared.receipt(),"color_profile":{"role":"DeviceN_alternate","space":"srgb","icc_sha256":assets::sha256(&profile),"profile_embedded":true},
        "pages":[{"index":0,"artboard_id":null,"logical_size":logical,"physical_points":[logical[0]*physical,logical[1]*physical],"pixel_dimensions":[prepared.width,prepared.height],"raster_ppi":prepared.ppi,"user_unit":unit}],
        "pdf":{"version":"1.7","color_delivery":"named_ink_recipe","color":"DeviceN","image_pixels":prepared.width as u64*prepared.height as u64,"path_commands":0,"text_glyphs":0,"raster_scale":ink.raster_scale,"editable_source":"snapshot","deterministic":true,"conformance":"PDF_1.7;no_PDF_X_or_press_certification"},
        "losses":["The page contains only the explicit named-ink recipe, with independent DeviceN samples. Original source channels, editable curves, ordinary artwork and history require the retained snapshot.","Alternate appearance uses bounded calculator interpolation of the declared 16-bit linear-RGB corner model followed by sRGB encoding. Consumers may use their own ink and color management; this is not physical press certification.","This whole-canvas recipe delivery does not combine calibrated process artwork, native vector paints, transparency or overprint groups. No print job is sent."]});
    metadata::annotate(&mut result, packet.as_deref(), policy, false);
    if result.get("metadata").is_some() {
        result["metadata"]["color"] = json!("explicit_DeviceN_recipe_with_srgb_alternate");
    }
    control.check()?;
    Ok(result)
}
