//! Original editable text delivery. Font files stay external and compatibility
//! caches stay separate from text, ranges and authoring geometry.
use super::{binary::*, object_write as descriptor, *};
use crate::{fonts, text};
use std::collections::{BTreeMap, BTreeSet};

pub(super) struct Prepared {
    pub width: u32,
    pub height: u32,
    pub origin: [i32; 2],
    pub rgba: Vec<u8>,
    pub record: Vec<u8>,
    pub receipt: Value,
}
pub(super) fn policy(options: &TextDelivery) -> Result<(), Error> {
    if options.shape_owner.is_empty()
        || options.shape_owner.len() > 128
        || !options
            .shape_owner
            .bytes()
            .all(|b| b.is_ascii_alphanumeric())
    {
        return Err(unsupported(
            "Text delivery requires an explicit geometry-extension owner identifier of 1..128 ASCII letters or digits for the receiving consumer",
        ));
    }
    Ok(())
}

fn face_name(face: &rustybuzz::Face<'_>) -> Result<String, Error> {
    let names = face
        .names()
        .into_iter()
        .filter(|n| n.name_id == 6)
        .filter_map(|n| n.to_string())
        .collect::<BTreeSet<_>>();
    if names.len() != 1 {
        return Err(unsupported(
            "Native text needs one unambiguous Unicode PostScript face name in each pinned font",
        ));
    }
    let name = names.into_iter().next().unwrap();
    if name.is_empty() || name.len() > 128 || !name.bytes().all(|b| (33..=126).contains(&b)) {
        return Err(unsupported(
            "Native font face name must contain 1..128 printable nonspace ASCII bytes",
        ));
    }
    if !face.variation_axes().is_empty() {
        return Err(unsupported(
            "Variable fonts need an explicit native instance mapping",
        ));
    }
    if face.tables().glyf.is_none() {
        return Err(unsupported(
            "Native text delivery currently requires a static TrueType outline face",
        ));
    }
    Ok(name)
}

fn encode(value: &Value, out: &mut Vec<u8>, control: &Control) -> Result<(), Error> {
    control.check()?;
    match value {
        Value::Object(fields) => {
            out.extend(b"<< ");
            for (key, value) in fields {
                if key.is_empty()
                    || key.len() > 128
                    || !key.bytes().all(|b| b.is_ascii_alphanumeric())
                {
                    return Err(unsupported("Unsupported text dictionary key"));
                }
                out.push(b'/');
                out.extend(key.as_bytes());
                out.push(b' ');
                encode(value, out, control)?;
                out.push(b' ');
            }
            out.extend(b">>");
        }
        Value::Array(values) => {
            out.extend(b"[ ");
            for v in values {
                encode(v, out, control)?;
                out.push(b' ');
            }
            out.push(b']');
        }
        Value::String(s) => {
            out.extend([b'(', 254, 255]);
            for b in s.encode_utf16().flat_map(u16::to_be_bytes) {
                if b"()\\".contains(&b) {
                    out.push(b'\\');
                }
                out.push(b);
            }
            out.push(b')');
        }
        Value::Bool(b) => out.extend(if *b {
            b"true".as_slice()
        } else {
            b"false".as_slice()
        }),
        Value::Number(n) if n.is_f64() => {
            // Retain a decimal point: integral tokens have different native units.
            // Fixed notation avoids unsupported exponent syntax and round-trips
            // even very small finite binary64 values before native quantization.
            let fixed = format!("{:.340}", n.as_f64().unwrap());
            let fixed = fixed.trim_end_matches('0');
            out.extend(fixed.as_bytes());
            if fixed.ends_with('.') {
                out.push(b'0');
            }
        }
        Value::Number(n) => out.extend(n.to_string().as_bytes()),
        Value::Null => return Err(malformed()),
    }
    if out.len() > 65536 {
        return Err(limit("Native text data exceeds 64 KiB"));
    }
    Ok(())
}
fn bool_value(value: bool) -> Vec<u8> {
    vec![b'b', b'o', b'o', b'l', u8::from(value)]
}
fn rectangle(class: &str, bounds: [f64; 4]) -> Vec<u8> {
    descriptor::object(
        class,
        ["Left", "Top ", "Rght", "Btom"]
            .into_iter()
            .zip(bounds)
            .map(|(key, v)| {
                let mut data = b"UntF#Pnt".to_vec();
                data.extend(v.to_be_bytes());
                (key, data)
            })
            .collect(),
    )
}

pub(super) fn prepare(
    document: &Document,
    item: &Item,
    world: Matrix,
    cache: &fonts::Cache,
    context: &mut Encoding<'_>,
) -> Result<Prepared, Error> {
    super::write::controls(item)?;
    let options = context.options.text.as_ref().ok_or_else(|| unsupported("Editable text delivery requires explicit layered_options.text reconstruction and shape_owner"))?;
    policy(options)?;
    let Content::Text { frame } = &item.content else {
        return Err(malformed());
    };
    if frame.first_baseline.is_some() {
        return Err(unsupported("Explicit first-baseline controls require a native authoring mapping before layered delivery").at_item(&item.id));
    }
    if frame.path.is_some()
        || frame.direction != text::Direction::Ltr
        || frame.bidi != text::Bidi::SingleRun
        || frame.align != text::Align::Left
        || (frame.wrap && frame.overflow == text::Overflow::Visible)
        || (!frame.wrap && frame.overflow == text::Overflow::Clip)
    {
        return Err(unsupported("Native text currently needs left-aligned horizontal LTR frames without paths; point text cannot carry clipping and paragraph text cannot carry visible overflow").at_item(&item.id));
    }
    let styles = text::styles(frame).collect::<Vec<_>>();
    let mut native_fonts = Vec::new();
    let mut font_indexes = BTreeMap::new();
    let mut font_receipts = Vec::new();
    for style in &styles {
        if !style.fallback_fonts.is_empty()
            || style.language.is_some()
            || !style.font_variations.is_empty()
            || style
                .features
                .iter()
                .any(|(k, v)| !["kern", "liga", "dlig"].contains(&k.as_str()) || *v > 1)
        {
            return Err(unsupported("Native text needs explicit single-face styles without language, fallback, variation or unmapped feature controls").at_item(&item.id));
        }
        if font_indexes.contains_key(&style.font_id) {
            continue;
        }
        let font = &document.fonts[&style.font_id];
        let face = fonts::parsed(font, &cache[&style.font_id])?;
        let name = face_name(&face).map_err(|e| e.at_font(&style.font_id))?;
        if let Some(prior) = context
            .budget
            .native_fonts
            .insert(name.clone(), (font.sha256.clone(), font.face_index))
            && prior != (font.sha256.clone(), font.face_index)
        {
            return Err(unsupported(
                "Distinct pinned font files with the same native face name cannot be distinguished",
            ));
        }
        if context.budget.native_fonts.len() > fonts::MAX_FONTS {
            return Err(limit(
                "Native text delivery references more than eight font faces across nested sources",
            ));
        }
        font_indexes.insert(style.font_id.clone(), native_fonts.len());
        native_fonts.push(json!({"Name":name,"Script":0,"FontType":1,"Synthetic":0}));
        font_receipts.push(json!({"font_id":style.font_id,"face_name":name,"font":font,"embedded":false,"recipient_file_identity_pinned":false}));
    }
    let layout = text::layout(frame, document, cache)?;
    let tracking = styles
        .iter()
        .map(|style| (style.tracking * 1000.0 / style.size).round() as i64)
        .collect::<Vec<_>>();
    let tracking_quantization = styles.iter().zip(&tracking).enumerate()
        .filter(|(_, (style,units))| style.tracking * 1000.0 / style.size != **units as f64)
        .map(|(index,(style,units))| json!({"style_index":index,"source_pixels":style.tracking,"native_thousandths_em":units,"delivered_pixels":*units as f64*style.size/1000.0}))
        .collect::<Vec<_>>();
    let native_styles = styles.iter().zip(&tracking).map(|(style,tracking)| {
        let Paint::Solid(color) = style.fill else { return Err(unsupported("Native text currently needs solid RGB character fills")); };
        if color[3]!=255 { return Err(unsupported("Native character alpha requires a verified paint mapping; use layer opacity for this delivery subset")); }
        let face = fonts::parsed(&document.fonts[&style.font_id], &cache[&style.font_id])?;
        let natural = (face.ascender() as f64-face.descender() as f64+face.line_gap() as f64)*style.size/face.units_per_em() as f64;
        let leading = frame.leading.unwrap_or(natural.max(0.001));
        let liga = style.features.get("liga").copied().unwrap_or(u32::from(style.tracking==0.0))!=0;
        Ok(json!({"Font":font_indexes[&style.font_id],"FontSize":style.size,
            "FillColor":{"Type":1,"Values":[1.0,color[0] as f64/255.0,color[1] as f64/255.0,color[2] as f64/255.0]},
            "FillFlag":true,"StrokeFlag":false,"AutoLeading":false,"Leading":leading,
            "Tracking":tracking,"HorizontalScale":1.0,"VerticalScale":1.0,
            "BaselineShift":0.0,"FontCaps":0,"FontBaseline":0,
            "AutoKerning":style.features.get("kern").copied().unwrap_or(1)!=0,"Kerning":0,
            "Ligatures":liga,"DLigatures":style.features.get("dlig").copied().unwrap_or(0)!=0}))
    }).collect::<Result<Vec<_>,Error>>()?;
    let chars = frame.text.chars().collect::<Vec<_>>();
    let mut segments = Vec::<(usize, usize)>::new();
    let mut prior = 0;
    for (index, r) in frame.ranges.iter().enumerate() {
        if r.start > prior {
            segments.push((r.start - prior, 0));
        }
        segments.push((r.end - r.start, index + 1));
        prior = r.end;
    }
    if prior < chars.len() {
        segments.push((chars.len() - prior, 0));
    }
    let mut runs = Vec::new();
    let mut lengths = Vec::new();
    let mut offset = 0;
    for (count, style) in segments {
        let units = chars[offset..offset + count]
            .iter()
            .map(|c| c.len_utf16())
            .sum::<usize>();
        runs.push(json!({"StyleSheet":{"StyleSheetData":native_styles[style]}}));
        lengths.push(units);
        offset += count;
    }
    if lengths.is_empty() {
        runs.push(json!({"StyleSheet":{"StyleSheetData":native_styles[0]}}));
        lengths.push(1);
    } else {
        *lengths.last_mut().unwrap() += 1;
    }
    if runs.len() > 65 {
        return Err(limit("Native character-style run table exceeds 65 entries"));
    }
    let text = format!("{}\r", frame.text.replace('\n', "\r"));
    let paragraph_lengths = text
        .split_inclusive('\r')
        .map(|s| s.encode_utf16().count())
        .collect::<Vec<_>>();
    if paragraph_lengths.len() > 65 {
        return Err(limit("Native text exceeds 65 paragraphs"));
    }
    let paragraph = json!({"ParagraphSheet":{"DefaultStyleSheet":0,"Properties":{"Justification":0,"AutoHyphenate":false}}});
    let shape_type = u32::from(frame.wrap);
    let mut cookie = json!({"ShapeType":shape_type,"Base":{"ShapeType":shape_type,"TransformPoint0":[1.0,0.0],"TransformPoint1":[0.0,1.0],"TransformPoint2":[0.0,0.0]}});
    cookie[if frame.wrap { "BoxBounds" } else { "PointBase" }] = if frame.wrap {
        json!([0.0, 0.0, frame.width, frame.height])
    } else {
        json!([0.0, 0.0])
    };
    let data = json!({"EngineDict":{"Editor":{"Text":text},"ParagraphRun":{"DefaultRunData":{"ParagraphSheet":{"DefaultStyleSheet":0,"Properties":{}}},"RunArray":vec![paragraph;paragraph_lengths.len()],"RunLengthArray":paragraph_lengths},
        "StyleRun":{"DefaultRunData":{"StyleSheet":{"StyleSheetData":{}}},"RunArray":runs,"RunLengthArray":lengths},"AntiAlias":0,"UseFractionalGlyphWidths":true,
        "Rendered":{"Version":1,"Shapes":{"WritingDirection":0,"Children":[{"ShapeType":shape_type,"Procession":0,"Lines":{"WritingDirection":0,"Children":[]},"Cookie":{options.shape_owner.clone():cookie}}]}}},
        "ResourceDict":{"TheNormalStyleSheet":0,"TheNormalParagraphSheet":0,"FontSet":native_fonts,"StyleSheetSet":[{"Name":"Original","StyleSheetData":native_styles[0]}],"ParagraphSheetSet":[{"Name":"Original","DefaultStyleSheet":0,"Properties":{"Justification":0,"AutoHyphenate":false}}]}});
    let mut payload = Vec::new();
    encode(&data, &mut payload, context.control)?;
    super::text_data::parse(&payload, context.control)?;
    let baseline = if frame.wrap {
        0.0
    } else {
        layout.lines[0].baseline
    };
    let matrix = crate::geometry::relative_transform(
        identity(),
        &[world, [1.0, 0.0, 0.0, 1.0, 0.0, baseline]],
    )?;
    let mut record = Vec::new();
    short(&mut record, 1);
    for n in matrix {
        record.extend(n.to_be_bytes());
    }
    short(&mut record, 50);
    word(&mut record, 16);
    let mut raw = b"tdta".to_vec();
    section(&mut raw, &payload);
    let bounds = [0.0, -baseline, frame.width, frame.height - baseline];
    record.extend(descriptor::descriptor(
        "TxLr",
        vec![
            ("Txt ", descriptor::text(&frame.text.replace('\n', "\r"))),
            ("EngineData", raw),
            (
                "textGridding",
                descriptor::enumeration("textGridding", "None"),
            ),
            ("Ornt", descriptor::enumeration("Ornt", "Hrzn")),
            ("AntA", descriptor::enumeration("Annt", "Anno")),
            ("TxMP", bool_value(false)),
            ("TextIndex", descriptor::integer(0)),
            ("bounds", rectangle("bounds", bounds)),
            ("boundingBox", rectangle("boundingBox", bounds)),
        ],
    ));
    short(&mut record, 1);
    word(&mut record, 16);
    record.extend(descriptor::descriptor(
        "warp",
        vec![
            (
                "warpStyle",
                descriptor::enumeration("warpStyle", "warpNone"),
            ),
            ("warpValue", descriptor::number(0.0)),
            ("warpPerspective", descriptor::number(0.0)),
            ("warpPerspectiveOther", descriptor::number(0.0)),
            ("warpRotate", descriptor::enumeration("Ornt", "Hrzn")),
        ],
    ));
    record.extend([0; 16]);
    super::text_record::inspect(&mut Reader::new(&record), context.control)?;
    let local = layout.ink_bounds.unwrap_or([0.0, 0.0, 1.0, 1.0]);
    let mapped = crate::geometry::bounds(
        &Geometry::Rect {
            x: local[0],
            y: local[1],
            width: (local[2] - local[0]).max(0.001),
            height: (local[3] - local[1]).max(0.001),
        },
        world,
    );
    if mapped
        .iter()
        .any(|v| !v.is_finite() || !(-32767.0..=32767.0).contains(v))
    {
        return Err(limit("Native text cache exceeds bounded layer coordinates"));
    }
    let left = mapped[0].floor() as i32;
    let top = mapped[1].floor() as i32;
    let width = ((mapped[2].ceil() as i32 - left) as u32).max(1);
    let height = ((mapped[3].ceil() as i32 - top) as u32).max(1);
    size(width, height, MAX_STORED_PIXELS, Version::Large)?;
    if context.budget.pixels + width as usize * height as usize > MAX_DECODED_BYTES / 4 {
        return Err(limit("Native text cache exceeds decoded sample budget"));
    }
    let translated = crate::geometry::relative_transform(
        [1.0, 0.0, 0.0, 1.0, left as f64, top as f64],
        &[world],
    )?;
    let cache_document:Document=serde_json::from_value(json!({"schema_version":2,"id":"text-cache","kind":"raster","width":width,"height":height,"color_space":"srgb","fonts":document.fonts,
        "items":[{"id":"source","transform":translated,"content":item.content}]})).map_err(|_|malformed())?;
    let raster = crate::render::rasterize_controlled(
        &cache_document,
        1,
        None,
        context.font_root,
        None,
        context.control,
    )?;
    Ok(Prepared {
        width,
        height,
        origin: [left, top],
        rgba: raster.rgba,
        record,
        receipt: json!({"item_id":item.id,"text_sha256":assets::sha256(frame.text.as_bytes()),"characters":chars.len(),"utf16_units":frame.text.encode_utf16().count(),"shape":if frame.wrap{"paragraph"}else{"point"},"shape_owner":options.shape_owner,
        "source_frame":[frame.width,frame.height],"native_matrix":matrix,"source_fonts":font_receipts,"tracking_quantization":tracking_quantization,"cached_pixels_are_source":false,"native_layout_equality":false,"automatic_leading":"resolved_to_explicit_per_style_values","font_binary_embedding":false}),
    })
}
