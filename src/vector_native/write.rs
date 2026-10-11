//! Original resource-free editable data. No preview, executable prolog or snapshot payload.
use super::limit;
use super::*;
use crate::{
    boards::{Insets, Role, Scope},
    geometry,
    model::*,
};
use serde_json::{Value, json};
use std::fmt::Write;

pub use crate::limits::vector_native_write::MAX_COORDINATE;

fn text(value: &str) -> Result<String, Error> {
    if value.is_empty() || !value.bytes().all(|b| (32..=126).contains(&b)) {
        return Err(unsupported(
            "Native delivery requires nonempty printable ASCII names",
        ));
    }
    let mut result = String::from("(");
    for c in value.chars() {
        if matches!(c, '(' | ')' | '\\') {
            result.push('\\');
        }
        result.push(c);
    }
    result.push(')');
    Ok(result)
}
fn appearance(item: &Item) -> Result<(), Error> {
    if item.metadata.is_some()
        || item.blend != BlendMode::Normal
        || item.fill_opacity != 1.0
        || !item.coverage.is_smooth()
        || !item.effects.is_empty()
        || !item.filters.is_empty()
        || item.hdr_grade.is_some()
        || item.pixel_warp.is_some()
        || item.clip_to.is_some()
        || item.clip.is_some()
        || item.mask.is_some()
        || item.artwork_mask.is_some()
    {
        return Err(unsupported("Native delivery has unmapped item appearance"));
    }
    text(&item.name)?;
    Ok(())
}
fn point(matrix: Matrix, p: Point) -> Result<Point, Error> {
    let result = geometry::map(matrix, p);
    if result
        .iter()
        .any(|v| !v.is_finite() || v.abs() > MAX_COORDINATE)
    {
        return Err(limit(
            "Native delivery point exceeds the normal-canvas budget",
        ));
    }
    Ok(result)
}
fn identity(document: &Document, id: &str) -> String {
    let digest =
        crate::assets::sha256(format!("inkbolt.native.board.v1\0{}\0{id}", document.id).as_bytes());
    // Project-owned deterministic UUID, version 8 and RFC variant. No source identity is asserted.
    format!(
        "{}-{}-8{}-a{}-{}",
        &digest[..8],
        &digest[8..12],
        &digest[13..16],
        &digest[17..20],
        &digest[20..32]
    )
}
struct Board<'a> {
    id: &'a str,
    name: &'a str,
    bounds: [f64; 4],
    locked: bool,
}
fn board(data: &mut String, document: &Document, board: &Board<'_>) -> Result<(), Error> {
    let [left, top, right, bottom] = board.bounds;
    if right <= left
        || top <= bottom
        || right - left > MAX_COORDINATE
        || top - bottom > MAX_COORDINATE
    {
        return Err(limit("Native delivery artboard size exceeds its budget"));
    }
    writeln!(data,"%_/Dictionary :\n%_1 /Real (PAR) , {} /UnicodeString (Name) ,\n%_{left} {top} /RealPointRelToROrigin (PositionPoint1) ,\n%_{right} {bottom} /RealPointRelToROrigin (PositionPoint2) ,\n%_0 0 /RealPoint (RulerOrigin) , 0 /Bool (IsArtboardDefaultName) ,\n%_0 /Int (DisplayMark) , {} /Bool (IsArtboardLocked) ,\n%_0 /Bool (IsArtboardSelected) , ({}) /String (ArtboardUUID) ,\n%_/FillStyle : 0 1 0 0 0 Xy 0 J 0 j 1 w 10 M []0 d 0 XR 0 0 Xd /Def ; (EachArtboardColor) ,\n%_; ,",text(board.name)?,u8::from(board.locked),identity(document,board.id)).unwrap();
    Ok(())
}
fn path(data: &mut String, item: &Item, matrix: Matrix) -> Result<(), Error> {
    let Content::Vector {
        geometry,
        fill: Some(Paint::Solid(color)),
        stroke: None,
        fill_rule: FillRule::Nonzero,
    } = &item.content
    else {
        return Err(unsupported(
            "Native delivery requires nonzero solid-filled unstroked paths",
        ));
    };
    if color[3] != 255 {
        return Err(unsupported(
            "Native delivery requires opaque fill colors; use item opacity",
        ));
    }
    // Exact rectangle/polygon expansion retains geometry. Curved primitives have distinct
    // approximation contracts and are not silently converted here.
    if !matches!(
        geometry,
        Geometry::Path { .. } | Geometry::Rect { .. } | Geometry::Polygon { .. }
    ) {
        return Err(unsupported(
            "Native delivery admits paths, rectangles and polygons",
        ));
    }
    let Geometry::Path { commands } = crate::primitives::expand(geometry)? else {
        unreachable!()
    };
    if !matches!(commands.first(), Some(PathCommand::Move { .. }))
        || !matches!(commands.last(), Some(PathCommand::Close {}))
        || commands[1..commands.len() - 1]
            .iter()
            .any(|c| matches!(c, PathCommand::Move { .. } | PathCommand::Close {}))
    {
        return Err(unsupported(
            "Native delivery requires one explicitly closed contour per path",
        ));
    }
    writeln!(
        data,
        "{} A {} Xw\n0 O 0 {} 0 0 0 Xy\n0 0 0 0 {} {} {} Xa\n0 J 0 j 1 w 10 M []0 d 0 XR",
        u8::from(item.locked),
        u8::from(!item.visible),
        item.opacity,
        color[0] as f64 / 255.0,
        color[1] as f64 / 255.0,
        color[2] as f64 / 255.0
    )
    .unwrap();
    let mut start = [0.0; 2];
    for command in commands {
        match command {
            PathCommand::Move { to } => {
                start = point(matrix, to)?;
                writeln!(data, "{} {} m", start[0], start[1]).unwrap();
            }
            PathCommand::Line { to } => {
                let p = point(matrix, to)?;
                writeln!(data, "{} {} L", p[0], p[1]).unwrap();
            }
            PathCommand::Cubic {
                control1,
                control2,
                to,
            } => {
                let a = point(matrix, control1)?;
                let b = point(matrix, control2)?;
                let p = point(matrix, to)?;
                writeln!(
                    data,
                    "{} {} {} {} {} {} C",
                    a[0], a[1], b[0], b[1], p[0], p[1]
                )
                .unwrap();
            }
            PathCommand::Close {} => {
                writeln!(data, "{} {} L", start[0], start[1]).unwrap();
            }
        }
    }
    writeln!(
        data,
        "f\n%_/ArtDictionary : /XMLUID : ({}) ; (AI10_ArtUID) , ;\n4 As",
        names::encode(&item.name)?
    )
    .unwrap();
    Ok(())
}
pub fn export(document: &Document, control: &Control) -> Result<Value, Error> {
    crate::model::validate_controlled(document, control)?;
    if document.metadata.is_some()
        || document.kind != DocumentKind::Vector
        || document.color_space != ColorSpace::Srgb
        || document
            .vector_canvas
            .is_some_and(|c| c.process_space != crate::vector_canvas::ProcessSpace::Rgb)
        || document.background.is_some()
        || document.output_profile.is_some()
        || document.ink_recipe.is_some()
        || !document.stories.is_empty()
        || !document.assets.is_empty()
        || !document.fonts.is_empty()
        || !document.swatches.is_empty()
        || document.selection.is_some()
        || !document.channels.is_empty()
        || document.variants.is_some()
    {
        return Err(unsupported(
            "Native delivery requires a resource-free RGB vector document without auxiliary state",
        ));
    }
    let scale = 72.0 / document.resolution_ppi;
    let mapping = [scale, 0.0, 0.0, -scale, 0.0, 0.0];
    let worlds = crate::scene::world_transforms(document, control)?;
    let mut boards = Vec::new();
    let mut layers = Vec::new();
    let mut paths = 0;
    for (i, item) in document.items.iter().enumerate() {
        control.check()?;
        appearance(item)?;
        match &item.content {
            Content::Frame { frame }
                if frame.scope == Scope::Scene && frame.role == Role::Artboard =>
            {
                if frame.bleed != Insets::default()
                    || !frame.guides.is_empty()
                    || frame.background.is_some()
                {
                    return Err(unsupported(
                        "Native artboards require zero bleed and no guides or background",
                    ));
                }
                let matrix = geometry::multiply(mapping, worlds[i]);
                let a = point(matrix, [0.0; 2])?;
                let b = point(matrix, frame.size())?;
                boards.push(Board {
                    id: &item.id,
                    name: &item.name,
                    bounds: [a[0], a[1], b[0], b[1]],
                    locked: item.locked,
                });
            }
            Content::Group {
                role: GroupRole::Layer,
                isolated: true,
                knockout: false,
            } if item.parent.is_none() && item.opacity == 1.0 => {
                layers.push(i);
            }
            Content::Vector { .. } => {
                let parent = item
                    .parent
                    .as_deref()
                    .ok_or_else(|| unsupported("Native paths require an explicit flat layer"))?;
                let p = &document.items[crate::scene::index(document, parent)?];
                if !matches!(
                    p.content,
                    Content::Group {
                        role: GroupRole::Layer,
                        ..
                    }
                ) || p.parent.is_some()
                {
                    return Err(unsupported("Native paths require an explicit flat layer"));
                }
                paths += 1;
            }
            _ => {
                return Err(unsupported(
                    "Native delivery has unmapped content or layer structure",
                ));
            }
        }
    }
    let implicit_board = boards.is_empty();
    if implicit_board {
        let (origin, size) = document
            .vector_canvas
            .map(|c| (c.origin_px, c.size_px))
            .unwrap_or(([0.0; 2], [document.width as f64, document.height as f64]));
        let a = point(mapping, origin)?;
        let b = point(mapping, [origin[0] + size[0], origin[1] + size[1]])?;
        boards.push(Board {
            id: "canvas",
            name: "Canvas",
            bounds: [a[0], a[1], b[0], b[1]],
            locked: false,
        });
    }
    if layers.is_empty() {
        return Err(unsupported(
            "Native delivery requires at least one explicit layer",
        ));
    }
    let left = boards
        .iter()
        .map(|b| b.bounds[0])
        .fold(f64::INFINITY, f64::min);
    let top = boards
        .iter()
        .map(|b| b.bounds[1])
        .fold(f64::NEG_INFINITY, f64::max);
    let right = boards
        .iter()
        .map(|b| b.bounds[2])
        .fold(f64::NEG_INFINITY, f64::max);
    let bottom = boards
        .iter()
        .map(|b| b.bounds[3])
        .fold(f64::INFINITY, f64::min);
    if right - left > MAX_COORDINATE || top - bottom > MAX_COORDINATE {
        return Err(limit("Native artboard union exceeds normal-canvas budget"));
    }
    let mut data = format!(
        "%!PS-Inkbolt-1.0\n%%Creator: Inkbolt\n%%AI8_CreatorVersion: 30.0.0\n%AI5_FileFormat 14.0\n%%BoundingBox: {} {} {} {}\n%%HiResBoundingBox: {left} {bottom} {right} {top}\n%AI5_ArtSize: {} {}\n%AI9_ColorModel: 1\n%AI24_LargeCanvasScale: 1\n%AI5_NumLayers: {}\n%%EndComments\n%%BeginProlog\n%%EndProlog\n%%BeginSetup\n%AI9_BeginDocumentData\n%_/Document : /Dictionary :\n%_/Array :\n",
        left.floor(),
        bottom.floor(),
        right.ceil(),
        top.ceil(),
        right - left,
        top - bottom,
        layers.len()
    );
    for value in &boards {
        board(&mut data, document, value)?;
    }
    data.push_str("%_; (ArtboardArray) ,\n%_0 /Int (CropAreaActive) ,\n");
    for side in ["Top", "Right", "Bottom", "Left"] {
        writeln!(data, "%_0 /Real (Bleed{side}Value) ,").unwrap();
    }
    data.push_str(
        "%_; /Recorded , /Dictionary : ; /NotRecorded , ;\n%AI9_EndDocumentData\n%%EndSetup\n",
    );
    for &index in &layers {
        control.check()?;
        let layer = &document.items[index];
        let children = crate::scene::children(document, Some(&layer.id));
        if children.is_empty() {
            return Err(unsupported(
                "Native editable-text delivery cannot preserve empty layers",
            ));
        }
        let flag = u8::from(layer.visible);
        writeln!(
            data,
            "%AI5_BeginLayer\n{flag} 1 {} 1 0 0 {flag} 0 40 80 120 0 50 0 Lb\n{} Ln\n0 AE",
            u8::from(!layer.locked),
            text(&layer.name)?
        )
        .unwrap();
        for i in children {
            control.check()?;
            path(
                &mut data,
                &document.items[i],
                geometry::multiply(mapping, worlds[i]),
            )?;
            if data.len() > MAX_DECODED_BYTES {
                return Err(limit("Native delivery exceeds 16 MiB"));
            }
        }
        data.push_str("LB\n%AI5_EndLayer--\n");
    }
    data.push_str("%%PageTrailer\ngsave annotatepage grestore showpage\n%%Trailer\n%%EOF\n");
    if data.len() > MAX_DECODED_BYTES {
        return Err(limit("Native delivery exceeds 16 MiB"));
    }
    // Admit only bytes that the bounded reader can represent too; do not claim this
    // self-check substitutes for independent consumer verification.
    artwork::read(
        data.as_bytes(),
        document.id.clone(),
        document.resource_profile,
        control,
    )?;
    let sha256 = crate::assets::sha256(data.as_bytes());
    Ok(
        json!({"media_type":"application/vnd.inkbolt.native-vector","encoding":"utf8","data":data,
        "native_vector":{"transport":"editable_text","creator_version":30,"file_format":14,"sha256":sha256,
            "document_to_native":mapping,"units":"points","source_resolution_ppi":document.resolution_ppi,"implicit_canvas_artboard":implicit_board,
            "counts":{"artboards":boards.len(),"layers":layers.len(),"paths":paths},"source_modified":false},
        "losses":["Layer and item transforms are baked into point controls; rectangles and polygons become editable closed paths. Retain the snapshot for source parameters and IDs.",
            "Delivery contains encoded RGB numbers without a color profile. External color management, antialiasing and opacity quantization can differ.",
            "The native artboard union determines the reopened canvas at 72 pixels per inch; the original document viewport and resolution stay in the source snapshot."]}),
    )
}
