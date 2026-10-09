use crate::paint::{Field, Interpolation, Spread};
use crate::{Error, model::*, scene};
use base64::{Engine, engine::general_purpose::STANDARD};
use serde_json::{Value, json};
use std::collections::{HashMap, HashSet};
use std::fmt::Write;
use std::path::Path;

fn appearance(out: &mut String, attribute: &str, paint: &Paint, name: Option<&String>) {
    match paint {
        Paint::Solid(color) => write!(
            out,
            " {attribute}=\"{}\" {attribute}-opacity=\"{}\"",
            rgb(*color),
            color[3] as f64 / 255.0
        )
        .unwrap(),
        Paint::Precise(color) => write!(
            out,
            " {attribute}=\"rgb({}%,{}%,{}%)\" {attribute}-opacity=\"{}\"",
            color.rgba[0] * 100.0,
            color.rgba[1] * 100.0,
            color.rgba[2] * 100.0,
            color.rgba[3]
        )
        .unwrap(),
        Paint::Named(_) => unreachable!("Named colors are resolved before SVG serialization"),
        Paint::Field(_) => write!(out, " {attribute}=\"url(#{})\"", name.unwrap()).unwrap(),
    }
}
fn paint_definition(out: &mut String, name: &str, field: &Field) -> Result<(), Error> {
    let (tag, stops, spread, space) = match field {
        Field::Linear {
            start,
            end,
            stops,
            spread,
            space,
            ..
        } => {
            write!(
                out,
                "<linearGradient id=\"{name}\" x1=\"{}\" y1=\"{}\" x2=\"{}\" y2=\"{}\"",
                start[0], start[1], end[0], end[1]
            )
            .unwrap();
            ("linearGradient", stops, spread, space)
        }
        Field::Radial {
            center,
            radius,
            stops,
            spread,
            space,
            ..
        } => {
            write!(
                out,
                "<radialGradient id=\"{name}\" cx=\"{}\" cy=\"{}\" r=\"{radius}\"",
                center[0], center[1]
            )
            .unwrap();
            ("radialGradient", stops, spread, space)
        }
        _ => {
            return Err(Error::new(
                "UNSUPPORTED",
                "SVG export does not represent freeform or inline pixel-pattern paints; use PNG for appearance and a snapshot for editing",
            ));
        }
    };
    write!(out," gradientUnits=\"userSpaceOnUse\" gradientTransform=\"{}\" spreadMethod=\"{}\" color-interpolation=\"{}\">",matrix(field.transform()),match spread {Spread::Pad=>"pad",Spread::Repeat=>"repeat",Spread::Reflect=>"reflect"},match space {Interpolation::Srgb=>"sRGB",Interpolation::LinearRgb=>"linearRGB"}).unwrap();
    for stop in stops {
        write!(
            out,
            "<stop offset=\"{}\" stop-color=\"{}\" stop-opacity=\"{}\"/>",
            stop.offset,
            rgb(stop.color),
            stop.color[3] as f64 / 255.0
        )
        .unwrap();
    }
    write!(out, "</{tag}>").unwrap();
    Ok(())
}

fn mesh_definition(
    out: &mut String,
    name: &str,
    field: &Field,
    document: &Document,
    index: usize,
) -> Result<Option<Value>, Error> {
    let Field::Mesh {
        mesh,
        space,
        transform,
    } = field
    else {
        return Ok(None);
    };
    let world = scene::world_transform(document, index)?;
    let mut placements = vec![world];
    // A shared mask source can be placed far from its saved coordinates. The
    // pattern period must cover every actual use of this paint in the viewport.
    for (owner, item) in document.items.iter().enumerate() {
        if let Some(mask) = item.artwork_mask.as_ref().filter(|m| m.enabled)
            && scene::subtree(document, scene::index(document, &mask.source)?).contains(&index)
        {
            placements.push(crate::geometry::multiply(
                mask.world_transform(scene::world_transform(document, owner)?),
                world,
            ));
        }
    }
    let viewport = [
        [0.0, 0.0],
        [document.width as f64, 0.0],
        [0.0, document.height as f64],
        [document.width as f64, document.height as f64],
    ];
    let mut corners = Vec::new();
    for placement in placements {
        let inverse = crate::geometry::inverse(crate::geometry::multiply(placement, *transform))?;
        corners.extend(viewport.map(|p| crate::geometry::map(inverse, p)));
    }
    let lo = std::array::from_fn::<_, 2, _>(|c| {
        corners.iter().map(|p| p[c]).fold(mesh.origin[c], f64::min) - mesh.size[c]
    });
    let hi = std::array::from_fn::<_, 2, _>(|c| {
        corners
            .iter()
            .map(|p| p[c])
            .fold(mesh.origin[c] + mesh.size[c], f64::max)
            + mesh.size[c]
    });
    if lo
        .iter()
        .chain(hi.iter())
        .any(|v| !v.is_finite() || v.abs() > 1e9)
    {
        return Err(crate::model::limit(
            "SVG mesh paint coverage exceeds coordinate budget",
        ));
    }
    let width = hi[0] - lo[0];
    let height = hi[1] - lo[1];
    let texture = crate::meshes::texture(mesh, *space)?;
    write!(out,"<pattern id=\"{name}\" patternUnits=\"userSpaceOnUse\" patternTransform=\"{}\" x=\"{}\" y=\"{}\" width=\"{width}\" height=\"{height}\" viewBox=\"{} {} {width} {height}\" preserveAspectRatio=\"none\"><image x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" preserveAspectRatio=\"none\" image-rendering=\"pixelated\" href=\"data:image/png;base64,{}\"/></pattern>",matrix(*transform),lo[0],lo[1],lo[0],lo[1],mesh.origin[0],mesh.origin[1],mesh.size[0],mesh.size[1],STANDARD.encode(&texture.png)).unwrap();
    Ok(Some(
        json!({"paint_id":name,"dimensions":texture.size,"sha256":crate::assets::sha256(&texture.png),"premultiplied_interior_reconstruction_error_bound":texture.premultiplied_error,"bound_contract":"convex reconstruction from source centers at most one texel away; excludes footprint/geometry edges and consumer color changes","coordinate_scope":"current_canvas_viewport","editable_mesh_retained":"snapshot_only"}),
    ))
}

fn rgb(color: Color) -> String {
    format!("#{:02x}{:02x}{:02x}", color[0], color[1], color[2])
}
fn xml(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('"', "&quot;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('\'', "&apos;")
}
fn matrix(m: Matrix) -> String {
    format!(
        "matrix({} {} {} {} {} {})",
        m[0], m[1], m[2], m[3], m[4], m[5]
    )
}
fn rule(rule: FillRule) -> &'static str {
    match rule {
        FillRule::Nonzero => "nonzero",
        FillRule::EvenOdd => "evenodd",
    }
}
fn geometry(out: &mut String, shape: &Geometry) {
    if crate::primitives::parametric(shape) {
        geometry(
            out,
            &crate::primitives::expand(shape).expect("validated primitive"),
        );
        return;
    }
    match shape {
        Geometry::Rect {
            x,
            y,
            width,
            height,
        } => write!(
            out,
            "<rect x=\"{x}\" y=\"{y}\" width=\"{width}\" height=\"{height}\""
        ),
        Geometry::Ellipse { cx, cy, rx, ry } => write!(
            out,
            "<ellipse cx=\"{cx}\" cy=\"{cy}\" rx=\"{rx}\" ry=\"{ry}\""
        ),
        Geometry::Path { commands } => {
            out.push_str("<path d=\"");
            for command in commands {
                match command {
                    PathCommand::Move { to } => write!(out, "M {} {} ", to[0], to[1]),
                    PathCommand::Line { to } => write!(out, "L {} {} ", to[0], to[1]),
                    PathCommand::Cubic {
                        control1,
                        control2,
                        to,
                    } => write!(
                        out,
                        "C {} {} {} {} {} {} ",
                        control1[0], control1[1], control2[0], control2[1], to[0], to[1]
                    ),
                    PathCommand::Close {} => write!(out, "Z "),
                }
                .unwrap();
            }
            write!(out, "\"")
        }
        _ => unreachable!("Parametric geometry was expanded above"),
    }
    .unwrap();
}
struct Definitions<'a> {
    control: &'a crate::control::Control,
    clips: &'a HashMap<(usize, bool), String>,
    paints: &'a HashMap<(usize, bool), String>,
    images: &'a HashMap<usize, String>,
    frames: &'a HashMap<usize, String>,
    outlines: &'a HashMap<usize, Option<Geometry>>,
}
fn write_items(
    out: &mut String,
    document: &Document,
    parent: Option<&str>,
    definitions: &Definitions<'_>,
    prefix: &str,
) -> Result<(), Error> {
    let Definitions {
        control,
        clips,
        paints,
        images,
        frames,
        outlines,
    } = *definitions;
    for i in scene::children(document, parent) {
        control.check()?;
        let item = &document.items[i];
        if matches!(
            item.content,
            Content::WorkPath { .. } | Content::MaskSource {}
        ) {
            continue;
        }
        write!(
            out,
            "<g id=\"{}\" opacity=\"{}\" transform=\"{}\"",
            format_args!("{prefix}{}", item.id),
            item.opacity * item.fill_opacity,
            matrix(item.transform)
        )
        .unwrap();
        if !item.visible {
            out.push_str(" display=\"none\"");
        }
        if let Some(id) = clips.get(&(i, false)) {
            write!(out, " clip-path=\"url(#{id})\"").unwrap();
        }
        if let Some(id) = clips.get(&(i, true)) {
            write!(out, " mask=\"url(#{id})\"").unwrap();
        }
        if item.content.is_isolated() {
            out.push_str(" style=\"isolation:isolate\"");
        }
        write!(out, "><title>{}</title>", xml(&item.name)).unwrap();
        match &item.content {
            Content::ComponentSource {}
            | Content::Instance { .. }
            | Content::Repeat { .. }
            | Content::Warp { .. }
            | Content::Appearance { .. }
            | Content::Volume { .. }
            | Content::Interpolation { .. } => {
                unreachable!("Components are materialized before SVG serialization")
            }
            Content::WorkPath { .. } | Content::MaskSource {} => {
                unreachable!("Resource items are nonprinting")
            }
            Content::Frame { frame } => {
                write!(out, "<g clip-path=\"url(#{})\">", frames[&i]).unwrap();
                if let Some(color) = frame.background {
                    geometry(out, &frame.geometry());
                    appearance(out, "fill", &Paint::Solid(color), None);
                    out.push_str("/>");
                }
                write_items(out, document, Some(&item.id), definitions, prefix)?;
                out.push_str("</g>");
            }
            Content::Group { .. } => {
                write_items(out, document, Some(&item.id), definitions, prefix)?
            }
            Content::Vector {
                geometry: g,
                fill,
                stroke,
                fill_rule,
            } => {
                if let Some(outline) = outlines.get(&i) {
                    if let Some(fill) = fill {
                        geometry(out, g);
                        appearance(out, "fill", fill, paints.get(&(i, false)));
                        write!(out, " fill-rule=\"{}\"/>", rule(*fill_rule)).unwrap();
                    }
                    if let Some(g) = outline {
                        geometry(out, g);
                        appearance(
                            out,
                            "fill",
                            &stroke.as_ref().unwrap().color,
                            paints.get(&(i, true)),
                        );
                        out.push_str(" fill-rule=\"nonzero\"/>");
                    }
                } else {
                    geometry(out, g);
                    match fill {
                        Some(color) => appearance(out, "fill", color, paints.get(&(i, false))),
                        None => out.push_str(" fill=\"none\""),
                    };
                    write!(out, " fill-rule=\"{}\"", rule(*fill_rule)).unwrap();
                    if let Some(s) = stroke {
                        appearance(out, "stroke", &s.color, paints.get(&(i, true)));
                        if let Some(dash) = &s.dash {
                            let array = if dash.array.is_empty() {
                                "none".to_owned()
                            } else {
                                dash.array
                                    .iter()
                                    .map(f64::to_string)
                                    .collect::<Vec<_>>()
                                    .join(" ")
                            };
                            write!(
                                out,
                                " stroke-dasharray=\"{array}\" stroke-dashoffset=\"{}\"",
                                dash.offset
                            )
                            .unwrap();
                        }
                        write!(out," stroke-width=\"{}\" stroke-linecap=\"{}\" stroke-linejoin=\"{}\" stroke-miterlimit=\"{}\"",s.width,match s.cap {Cap::Butt=>"butt",Cap::Round=>"round",Cap::Square=>"square"},match s.join {Join::Miter=>"miter",Join::Round=>"round",Join::Bevel=>"bevel"},s.miter_limit).unwrap();
                    }
                    out.push_str("/>");
                }
            }
            Content::Image {
                width,
                height,
                sampling,
                ..
            } => {
                write!(out,"<image width=\"{width}\" height=\"{height}\" preserveAspectRatio=\"none\" style=\"image-rendering:{}\" href=\"data:image/png;base64,{}\"/>",match sampling {crate::assets::Sampling::Nearest=>"pixelated",crate::assets::Sampling::Bilinear=>"auto",_=>unreachable!("SVG sampling was validated")},images[&i]).unwrap();
            }
            Content::Text { .. } | Content::StoryFrame { .. } => {
                unreachable!("Text is outlined before SVG serialization")
            }
            Content::Object { .. }
            | Content::Raw { .. }
            | Content::Samples { .. }
            | Content::StoredSamples { .. }
            | Content::Adjustment { .. }
            | Content::Raster { .. }
            | Content::Fill { .. } => {
                unreachable!("vector document validation excludes pixel content")
            }
        }
        out.push_str("</g>");
    }
    Ok(())
}
pub fn export(document: &Document) -> Result<Value, Error> {
    export_with_assets(document, None)
}
pub fn export_with_assets(document: &Document, root: Option<&Path>) -> Result<Value, Error> {
    export_with_resources(document, root, None)
}
pub fn export_with_resources(
    document: &Document,
    root: Option<&Path>,
    font_root: Option<&Path>,
) -> Result<Value, Error> {
    export_controlled(
        document,
        root,
        font_root,
        &crate::control::Control::default(),
    )
}
pub fn export_controlled(
    document: &Document,
    root: Option<&Path>,
    font_root: Option<&Path>,
    control: &crate::control::Control,
) -> Result<Value, Error> {
    validate_controlled(document, control)?;
    crate::hdr::reject_page(document)?;
    crate::vector_canvas::reject_rgb_page(document)?;
    crate::swatches::vector_export(document)?;
    let source = document;
    let colors = crate::swatches::evaluate(document)?;
    let document = colors.as_ref().unwrap_or(document);
    if document.output_profile.is_some() {
        return Err(Error::new(
            "UNSUPPORTED",
            "SVG output does not implement ICC conversion or profile embedding; explicitly clear output_profile for working-sRGB SVG or use an image export",
        ));
    }
    let had_variants = document.variants.is_some();
    let expanded_instances = crate::instances::evaluate(document)?;
    let document = expanded_instances.as_ref().unwrap_or(document);
    let appearance = crate::appearance::evaluate(document)?;
    let document = appearance.as_ref().unwrap_or(document);
    let volume = crate::volumes::evaluate(document)?;
    let document = volume.as_ref().unwrap_or(document);
    let warped = crate::warps::evaluate(document)?;
    let document = warped.as_ref().unwrap_or(document);
    let repeated = crate::repeats::evaluate(document)?;
    let document = repeated.as_ref().unwrap_or(document);
    let interpolated = crate::interpolation::evaluate(document)?;
    let document = interpolated.as_ref().unwrap_or(document);
    if document.items.iter().any(|i| !i.filters.is_empty()) {
        return Err(Error::new(
            "UNSUPPORTED",
            "SVG export cannot preserve editable viewport filters; use PNG or snapshot",
        ));
    }
    if document.kind != DocumentKind::Vector {
        return Err(Error::new(
            "UNSUPPORTED",
            "SVG export currently accepts vector documents only",
        ));
    }
    if document.items.iter().any(|item| {
        item.blend != BlendMode::Normal
            || item.content.is_knockout()
            || !item.effects.is_empty()
            || !item.coverage.is_smooth()
    }) {
        return Err(Error::new(
            "UNSUPPORTED",
            "SVG export does not yet preserve non-normal blend modes, knockout groups, layer effects or dissolve",
        ));
    }
    let fonts = crate::fonts::resolve(document, font_root)?;
    let layouts = crate::text::prepare(document, &fonts)?;
    let mut outlined = document.clone();
    outlined.variants = None;
    for (id, layout) in &layouts {
        let i = scene::index(&outlined, id)?;
        crate::text::outline_item(&mut outlined, i, layout)?;
    }
    validate_controlled(&outlined, control)?;
    let document = &outlined;
    crate::meshes::svg_texture_pixels(document)?;
    let mut mesh_textures = Vec::new();
    if crate::strokes::svg_work(document)? > crate::strokes::MAX_SVG_COMMANDS {
        return Err(crate::model::limit(
            "SVG stroke outlines exceed the generated-command copy budget",
        ));
    }
    let mut image_pixels = 0u64;
    for item in &document.items {
        if item.pixel_warp.is_some() {
            return Err(Error::new(
                "UNSUPPORTED",
                "SVG does not preserve retained pixel deformation; use pixel exports and snapshots",
            )
            .at_item(&item.id));
        }
        if matches!(&item.content, Content::Image { sampling, .. } if sampling.advanced()) {
            return Err(Error::new(
                "UNSUPPORTED",
                "SVG cannot preserve the selected reconstruction kernel; use PNG and snapshots",
            )
            .at_item(&item.id));
        }
        if let Some(mask) = item.mask.as_ref().filter(|m| m.enabled) {
            let [w, h] = mask.prepared_size();
            image_pixels += w as u64 * h as u64;
        }
        if let Content::Image { asset_id, crop, .. } = &item.content {
            let source = &document.assets[asset_id];
            let c = crate::assets::crop(source.width, source.height, *crop)?;
            image_pixels += c.width as u64 * c.height as u64;
        }
    }
    if image_pixels > crate::assets::MAX_ASSET_PIXELS {
        return Err(crate::model::limit(
            "SVG embedded image copies exceed 16777216 pixels",
        ));
    }
    let version = if document.items.iter().any(|i| {
        i.artwork_mask
            .as_ref()
            .is_some_and(|m| m.enabled && !m.clip_region)
    }) {
        " version=\"2.0\""
    } else {
        ""
    };
    let canvas_bounds = crate::vector_canvas::bounds(document);
    let logical = crate::vector_canvas::logical_size(document);
    let physical = document
        .vector_canvas
        .map(|c| c.svg_dimensions(document.resolution_ppi))
        .transpose()?
        .unwrap_or([document.width.to_string(), document.height.to_string()]);
    let mut out = format!(
        "<svg{version} xmlns=\"http://www.w3.org/2000/svg\" width=\"{}\" height=\"{}\" viewBox=\"{} {} {} {}\" color-interpolation=\"sRGB\">",
        physical[0], physical[1], canvas_bounds[0], canvas_bounds[1], logical[0], logical[1]
    );
    let mut used: HashSet<_> = document.items.iter().map(|item| item.id.clone()).collect();
    let mut clips = HashMap::new();
    let mut paints = HashMap::new();
    let mut frames = HashMap::new();
    let mut outlines = HashMap::new();
    for (i, item) in document.items.iter().enumerate() {
        control.check()?;
        if let Content::Vector {
            geometry,
            stroke: Some(stroke),
            ..
        } = &item.content
            && (crate::strokes::advanced(stroke)
                || !crate::strokes::is_default_tolerance(&stroke.curve_tolerance))
        {
            outlines.insert(
                i,
                crate::strokes::generate_local(
                    geometry,
                    stroke,
                    scene::world_transform(document, i)?,
                )?,
            );
        }
    }
    let resolved = crate::assets::resolve(document, root)?;
    let mut images = HashMap::new();
    for (i, item) in document.items.iter().enumerate() {
        control.check()?;
        if let Content::Frame { frame } = &item.content {
            let mut name = format!("inkbolt-frame-{i}");
            while used.contains(&name) {
                name.push('_');
            }
            used.insert(name.clone());
            frames.insert(i, name.clone());
            write!(
                out,
                "<defs><clipPath id=\"{name}\" clipPathUnits=\"userSpaceOnUse\">"
            )
            .unwrap();
            geometry(&mut out, &frame.geometry());
            out.push_str("/></clipPath></defs>");
        }
        if let Content::Image { asset_id, crop, .. } = &item.content {
            let source = &resolved[asset_id];
            let crop = crate::assets::crop(source.width, source.height, *crop)?;
            let png =
                crate::render::encode_png(crop.width, crop.height, &source.cropped(crop), 96.0)?;
            images.insert(i, STANDARD.encode(png));
        }
        if let Content::Vector { fill, stroke, .. } = &item.content {
            for (paint, is_stroke) in fill
                .iter()
                .map(|p| (p, false))
                .chain(stroke.iter().map(|s| (&s.color, true)))
            {
                if let Paint::Field(field) = paint {
                    let mut name = format!("inkbolt-paint-{i}-{}", u8::from(is_stroke));
                    while used.contains(&name) {
                        name.push('_');
                    }
                    used.insert(name.clone());
                    paints.insert((i, is_stroke), name.clone());
                    out.push_str("<defs>");
                    if let Some(report) = mesh_definition(&mut out, &name, field, document, i)? {
                        mesh_textures.push(report);
                    } else {
                        paint_definition(&mut out, &name, field)?;
                    }
                    out.push_str("</defs>");
                }
            }
        }
        if let Some(clip) = item.clip.as_ref().filter(|c| c.enabled) {
            if matches!(&clip.geometry, Geometry::Compound { .. }) {
                return Err(Error::new(
                    "UNSUPPORTED",
                    "SVG delivery of a retained compound clip requires explicit baking; keep its editable snapshot",
                ));
            }
            let mut name = format!("inkbolt-clip-{i}");
            while used.contains(&name) {
                name.push('_');
            }
            used.insert(name.clone());
            clips.insert((i, false), name.clone());
            write!(
                out,
                "<defs><clipPath id=\"{name}\" clipPathUnits=\"userSpaceOnUse\">"
            )
            .unwrap();
            geometry(&mut out, &clip.geometry);
            write!(
                out,
                " transform=\"{}\" clip-rule=\"{}\" fill-rule=\"{}\"/></clipPath></defs>",
                matrix(clip.transform),
                rule(clip.fill_rule),
                rule(clip.fill_rule)
            )
            .unwrap();
        }
    }
    for (i, item) in document.items.iter().enumerate() {
        control.check()?;
        if let Some(mask) = item.mask.as_ref().filter(|m| m.enabled) {
            let mut name = format!("inkbolt-mask-{i}");
            while used.contains(&name) {
                name.push('_');
            }
            used.insert(name.clone());
            clips.insert((i, true), name.clone());
            mask_definition(&mut out, &name, document, i, mask)?;
        }
    }
    let mut copies = 0;
    for (i, item) in document.items.iter().enumerate() {
        control.check()?;
        let Some(mask) = item.artwork_mask.as_ref().filter(|m| m.enabled) else {
            continue;
        };
        let source = scene::index(document, &mask.source)?;
        let members = scene::subtree(document, source);
        copies += members.len();
        if copies > crate::artwork_masks::MAX_SVG_ITEMS {
            return Err(crate::model::limit(
                "SVG artwork-mask copies exceed 4096 items",
            ));
        }
        let mut name = format!("inkbolt-artmask-{i}");
        while used
            .iter()
            .any(|s| s == &name || s.starts_with(&format!("{name}-")))
        {
            name.push('_');
        }
        let prefix = format!("{name}-");
        used.insert(name.clone());
        for &m in &members {
            used.insert(format!("{prefix}{}", document.items[m].id));
        }
        clips.insert((i, true), name.clone());
        let local = if mask.linked {
            mask.transform
        } else {
            crate::geometry::multiply(
                crate::geometry::inverse(scene::world_transform(document, i)?)?,
                mask.transform,
            )
        };
        let mode = match mask.mode {
            crate::artwork_masks::Mode::Alpha => "alpha",
            crate::artwork_masks::Mode::Luminance => "luminance",
        };
        out.push_str("<defs>");
        let region = mask.region_geometry().filter(|_| mask.clip_region);
        if !mask.clip_region || region.is_some() {
            if let Some(region) = region {
                let transform = crate::geometry::multiply(local, mask.region_transform);
                let b = crate::geometry::bounds(&region, transform);
                let mut region_id = format!("{name}-region");
                while used.contains(&region_id) {
                    region_id.push('_');
                }
                used.insert(region_id.clone());
                write!(
                    out,
                    "<clipPath id=\"{region_id}\" clipPathUnits=\"userSpaceOnUse\">"
                )
                .unwrap();
                geometry(&mut out, &region);
                write!(out, " transform=\"{}\"/></clipPath>", matrix(transform)).unwrap();
                // The explicit clip defines the region, with a padded bounding
                // buffer so its antialiasing is not clipped a second time.
                write!(out,"<mask id=\"{name}\" maskUnits=\"userSpaceOnUse\" maskContentUnits=\"userSpaceOnUse\" mask-type=\"{mode}\" color-interpolation=\"sRGB\" x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\"><g clip-path=\"url(#{region_id})\">",b[0]-1.0,b[1]-1.0,b[2]-b[0]+2.0,b[3]-b[1]+2.0).unwrap();
            } else {
                write!(out, "<mask id=\"{name}\" maskUnits=\"userSpaceOnUse\" maskContentUnits=\"userSpaceOnUse\" mask-type=\"{mode}\" color-interpolation=\"sRGB\"><g>").unwrap();
            }
            let node = &document.items[source];
            write!(
                out,
                "<g transform=\"{}\" opacity=\"{}\" style=\"isolation:isolate\"",
                matrix(crate::geometry::multiply(local, node.transform)),
                node.opacity * node.fill_opacity
            )
            .unwrap();
            if !node.visible {
                out.push_str(" display=\"none\"");
            }
            if let Some(clip) = clips.get(&(source, false)) {
                write!(out, " clip-path=\"url(#{clip})\"").unwrap();
            }
            out.push('>');
            let mut placed_outlines = outlines.clone();
            let placement = mask.world_transform(scene::world_transform(document, i)?);
            for &j in &members {
                if let Content::Vector {
                    geometry,
                    stroke: Some(stroke),
                    ..
                } = &document.items[j].content
                    && stroke.scaling == crate::strokes::Scaling::Document
                {
                    let world =
                        crate::geometry::multiply(placement, scene::world_transform(document, j)?);
                    placed_outlines
                        .insert(j, crate::strokes::generate_local(geometry, stroke, world)?);
                }
            }
            write_items(
                &mut out,
                document,
                Some(&mask.source),
                &Definitions {
                    control,
                    clips: &clips,
                    paints: &paints,
                    images: &images,
                    frames: &frames,
                    outlines: &placed_outlines,
                },
                &prefix,
            )?;
            out.push_str("</g></g></mask>");
        } else {
            write!(out,"<mask id=\"{name}\" maskUnits=\"userSpaceOnUse\" maskContentUnits=\"userSpaceOnUse\" color-interpolation=\"sRGB\" x=\"0\" y=\"0\" width=\"1\" height=\"1\" mask-type=\"{mode}\"/>").unwrap();
        }
        out.push_str("</defs>");
    }
    write_items(
        &mut out,
        document,
        None,
        &Definitions {
            control,
            clips: &clips,
            paints: &paints,
            images: &images,
            frames: &frames,
            outlines: &outlines,
        },
        "",
    )?;
    out.push_str("</svg>");
    let mut losses = vec![
        "Edit locks, document revision, group/layer roles and disabled clip settings are not preserved as SVG artwork semantics; retain the snapshot for editing.",
    ];
    if expanded_instances.is_some() {
        losses.push("Component instances export as independent expanded groups. Retain snapshots for shared definitions and local overrides.");
    }
    if appearance.is_some() {
        losses.push("Appearance passes are delivered as ordinary ordered paint objects; retain the snapshot for shared source geometry, pass identities and editing controls.");
    }
    if volume.is_some() {
        losses.push("Dimensional artwork exports as projected painted faces; retain snapshots for original profiles, extrusion, camera and lighting controls.");
    }
    if warped.is_some() {
        losses.push("Warped geometry exports as certified line segments within its saved local tolerance. Retain snapshots for original geometry and editable map controls.");
    }
    if repeated.is_some() {
        losses.push("Repeat layouts export as ordinary compound geometry. Retain snapshots for editable motif and layout controls.");
    }
    if interpolated.is_some() {
        losses.push("Interpolation objects export as ordinary filled/stroked vector steps. Retain snapshots for endpoint shapes, contour correspondence, spine, orientation and reversible interpolation settings.");
    }
    if had_variants {
        losses.push("Only the selected variant is exported. Retain snapshots for dataset bindings, inherited values and captured base properties.");
    }
    if !outlines.is_empty() {
        losses.push("Width profiles, brush motifs, arrowheads, document-scaled strokes and custom stroke tolerances export as filled outline geometry. Retain snapshots for editable brush spacing/corners, stroke controls and future document-width behavior. Curve and round-arc evaluation uses the saved tolerance in the declared stroke coordinate space.");
    }
    if document.items.iter().any(|i| i.fill_opacity != 1.0) {
        losses.push("Separate content fill opacity is combined with overall opacity in SVG; retain the snapshot for independent editable controls.");
    }
    if document.items.iter().any(|i| i.mask.is_some()) {
        losses.push("Opacity masks embed processed grayscale8 PNG fields with nearest/bilinear consumer hints. Retain snapshots for original mask pixels and reversible settings. PNG export defines exact sampling and floating-point opacity.");
    }
    if document
        .items
        .iter()
        .any(|i| i.artwork_mask.is_some() || matches!(i.content, Content::MaskSource {}))
    {
        losses.push("Artwork masks export editable vector content with explicit user-space regions and alpha/sRGB-luminance interpretation. Sources are copied per enabled reference with distinct IDs. Unused sources, shared editing identity, linked state and disabled settings require the snapshot; text exports as outlines.");
    }
    if document
        .items
        .iter()
        .any(|i| matches!(i.content, Content::WorkPath { .. }))
    {
        losses.push("Nonprinting work paths are omitted from SVG artwork; retain the snapshot for editable reusable regions.");
    }
    if document.items.iter().any(|i| matches!(&i.content, Content::Vector {geometry,..} if crate::primitives::parametric(geometry)) || i.clip.as_ref().is_some_and(|c| crate::primitives::parametric(&c.geometry))) {
        losses.push("Parametric rounded rectangles, polygons and stars export as explicit paths; retain the snapshot for editable shape parameters.");
    }
    if document.selection.is_some() {
        losses.push("Pixel selection state is nonprinting and requires the editable snapshot.");
    }
    if !document.channels.is_empty() {
        losses.push("Saved alpha and named-ink channels are nonprinting and require the editable snapshot; SVG artwork does not retain channel identity or tint planes.");
    }
    if !frames.is_empty() {
        losses.push("Frames and artboards become isolated clipped groups. Guides, board roles, bleed settings and export order require the editable snapshot.");
    }
    if !layouts.is_empty() {
        losses.push("Text exports as glyph outlines; retain the snapshot and pinned fonts for editable text. SVG outline expansion uses document item and path-command limits.");
    }
    let text_paths: Vec<_> = layouts
        .iter()
        .filter_map(|(id, layout)| {
            layout
                .baseline_path
                .as_ref()
                .map(|report| json!({"item_id":id,"baseline":report}))
        })
        .collect();
    if !text_paths.is_empty() {
        losses.push("Path text retains placed glyph outlines. Editable baseline geometry, offsets, flip and overflow settings require the snapshot. Reported placement bounds describe expanded cubic baselines in item-local units; item/world transforms scale those bounds. Analytic ellipse conversion is separately disclosed.");
    }
    if !images.is_empty() {
        losses.push("Images are embedded as cropped PNG pixels. Original asset identities, provenance and uncropped pixels require the snapshot. SVG image-rendering is a consumer hint; PNG export is authoritative for exact resampling.");
    }
    if !mesh_textures.is_empty() {
        losses.push("Color meshes export as bounded sampled PNG paints within retained vector geometry. Snapshots retain editable knots, derivatives and transparency. Texture reconstruction bounds apply to the current canvas interior under the reported consumer assumptions; off-canvas repetition, geometry/footprint edges and consumer color changes require separate treatment.");
    }
    let mut artifact =
        json!({"media_type":"image/svg+xml","encoding":"utf8","data":out,"losses":losses});
    if !mesh_textures.is_empty() {
        artifact["mesh_textures"] = json!(mesh_textures);
    }
    if !text_paths.is_empty() {
        artifact["text_paths"] = json!(text_paths);
    }
    crate::swatches::annotate(source, &mut artifact)?;
    Ok(artifact)
}

fn mask_definition(
    out: &mut String,
    name: &str,
    document: &Document,
    i: usize,
    mask: &crate::masks::Mask,
) -> Result<(), Error> {
    let world = scene::world_transform(document, i)?;
    let inverse = crate::geometry::inverse(world)?;
    let prepared = crate::masks::prepare(mask, world)?;
    let mut bounds = [
        f64::INFINITY,
        f64::INFINITY,
        f64::NEG_INFINITY,
        f64::NEG_INFINITY,
    ];
    for p in [
        [0.0, 0.0],
        [document.width as f64, 0.0],
        [0.0, document.height as f64],
        [document.width as f64, document.height as f64],
    ] {
        let p = crate::geometry::map(inverse, p);
        bounds[0] = bounds[0].min(p[0]);
        bounds[1] = bounds[1].min(p[1]);
        bounds[2] = bounds[2].max(p[0]);
        bounds[3] = bounds[3].max(p[1]);
    }
    let local = if mask.linked {
        mask.transform
    } else {
        crate::geometry::multiply(inverse, mask.transform)
    };
    let byte = |v: f64| (v.clamp(0.0, 1.0) * 255.0).round() as u8;
    let pixels: Vec<_> = prepared
        .values
        .iter()
        .flat_map(|v| {
            let c = byte(*v);
            [c, c, c, 255]
        })
        .collect();
    let png = crate::render::encode_png(prepared.width, prepared.height, &pixels, 96.0)?;
    let outside = byte(prepared.outside);
    let x = bounds[0];
    let y = bounds[1];
    let w = bounds[2] - x;
    let h = bounds[3] - y;
    write!(out,"<defs><mask id=\"{name}\" maskUnits=\"userSpaceOnUse\" maskContentUnits=\"userSpaceOnUse\" mask-type=\"luminance\" color-interpolation=\"sRGB\" x=\"{x}\" y=\"{y}\" width=\"{w}\" height=\"{h}\"><rect x=\"{x}\" y=\"{y}\" width=\"{w}\" height=\"{h}\" fill=\"rgb({outside},{outside},{outside})\"/><image x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" transform=\"{}\" preserveAspectRatio=\"none\" style=\"image-rendering:{}\" href=\"data:image/png;base64,{}\"/></mask></defs>",-(prepared.pad as i64),-(prepared.pad as i64),prepared.width,prepared.height,matrix(local),match mask.sampling {crate::assets::Sampling::Nearest=>"pixelated",crate::assets::Sampling::Bilinear=>"auto",_=>unreachable!("SVG sampling was validated")},STANDARD.encode(png)).unwrap();
    Ok(())
}
