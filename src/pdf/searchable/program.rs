use super::*;
use rustybuzz::ttf_parser::{Tag, name_id};
use sha2::{Digest, Sha256};
use std::borrow::Cow;
use std::fmt::Write as _;
use subsetter::GlyphRemapper;

use write_fonts::{
    FontBuilder,
    read::{
        FontData, FontRead, FontRef, TableProvider,
        ps::cff::{dict, v1::Cff},
    },
};

fn collection(data: &[u8]) -> Result<String, Error> {
    let invalid = || unsupported("Missing CID font collection information");
    let font = FontRef::new(data).map_err(|_| invalid())?;
    let raw = font
        .data_for_tag(write_fonts::types::Tag::new(b"CFF "))
        .ok_or_else(invalid)?;
    let cff = Cff::read(FontData::new(raw.as_bytes())).map_err(|_| invalid())?;
    let top = cff.top_dicts().get(0).map_err(|_| invalid())?;
    for entry in dict::entries(top, None) {
        if let dict::Entry::Ros {
            registry,
            ordering,
            supplement,
        } = entry.map_err(|_| invalid())?
        {
            let hex = |sid| {
                cff.string(sid)
                    .map(|bytes| bytes.iter().map(|b| format!("{b:02X}")).collect::<String>())
                    .ok_or_else(invalid)
            };
            return Ok(format!(
                "/CIDSystemInfo << /Registry <{}> /Ordering <{}> /Supplement {} >>",
                hex(registry)?,
                hex(ordering)?,
                supplement.to_i32()
            ));
        }
    }
    Err(invalid())
}

// The standalone subset omits OS/2. Preserve the original permissions and
// metrics before the SFNT writer computes table offsets and checksums.
fn restore_metrics(subset: &[u8], os2: &[u8]) -> Result<Vec<u8>, Error> {
    let font = FontRef::new(subset).map_err(|_| unsupported("Invalid subset font directory"))?;
    Ok(FontBuilder::new()
        .add_raw(write_fonts::types::Tag::new(b"OS/2"), os2)
        .copy_missing_tables(font)
        .build())
}

fn pdf_name(name: &str) -> String {
    let mut out = String::new();
    for b in name.bytes() {
        if (33..=126).contains(&b) && !b"#%()/<>[]{}".contains(&b) {
            out.push(b as char);
        } else {
            write!(out, "#{b:02X}").unwrap();
        }
    }
    out
}

pub(super) fn cmap(
    writer: &mut Writer,
    system: &str,
    kind: u8,
    one_byte: bool,
    rows: &[String],
) -> Result<usize, Error> {
    let op = if kind == 1 { "cidchar" } else { "bfchar" };
    let prefix = if kind == 1 {
        "InkboltEncoding"
    } else {
        "InkboltUnicode"
    };
    let name = format!("{prefix}{}", writer.objects.len() + 1);
    let range = if one_byte {
        "<00> <FF>"
    } else {
        "<0000> <FFFF>"
    };
    let mut s = format!(
        "/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n{system} def\n/CMapName /{name} def\n/CMapType {kind} def\n1 begincodespacerange\n{range}\nendcodespacerange\n"
    );
    for chunk in rows.chunks(100) {
        writeln!(s, "{} begin{op}", chunk.len()).unwrap();
        for row in chunk {
            writeln!(s, "{row}").unwrap();
        }
        writeln!(s, "end{op}").unwrap();
    }
    s.push_str("endcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n");
    let entries = if kind == 1 {
        format!("/Type /CMap /CMapName /{name} {system}")
    } else {
        String::new()
    };
    writer.stream(&entries, s.as_bytes())
}

pub(super) fn embed(
    writer: &mut Writer,
    data: &[u8],
    index: u32,
    font: PendingFont,
) -> Result<(), Error> {
    let face = Face::parse(data, index).map_err(|_| unsupported("Unreadable font program"))?;
    let mut codes = font.codes.into_iter().collect::<Vec<_>>();
    codes.sort_by_key(|(_, code)| *code);
    let subset = matches!(font.kind, Kind::SubsetCff | Kind::SubsetTrueType);
    let cff = matches!(
        font.kind,
        Kind::SubsetCff | Kind::WholeCidCff | Kind::WholeNamedCff
    );
    let mut mapper = GlyphRemapper::new();
    let bytes = if subset {
        for ((gid, _), _) in &codes {
            mapper.remap(*gid);
        }
        let os2 = face
            .raw_face()
            .table(Tag::from_bytes(b"OS/2"))
            .ok_or_else(|| unsupported("Missing font embedding permissions"))?;
        writer.control.check()?;
        let raw = subsetter::subset(data, index, &mapper)
            .map_err(|_| unsupported("Unable to subset this font program"))?;
        Cow::Owned(restore_metrics(&raw, os2)?)
    } else {
        Cow::Borrowed(data)
    };
    let mut name = face
        .names()
        .into_iter()
        .find_map(|n| {
            (n.name_id == name_id::POST_SCRIPT_NAME)
                .then(|| n.to_string())
                .flatten()
        })
        .filter(|n| !n.is_empty())
        .map(|n| pdf_name(&n))
        .unwrap_or_else(|| "InkboltFont".to_owned());
    if subset {
        // Six uppercase letters identify subsets in the PDF font name.
        let prefix: String = Sha256::digest(&bytes)[..6]
            .iter()
            .map(|byte| (b'A' + byte % 26) as char)
            .collect();
        name = format!("{prefix}+{name}");
    }
    let system = if matches!(font.kind, Kind::SubsetCff | Kind::WholeCidCff) {
        collection(&bytes)?
    } else {
        GLYPH_COLLECTION.into()
    };
    let metrics = |v: i16| f64::from(v) * 1000.0 / f64::from(face.units_per_em());
    let r = face.global_bounding_box();
    let bbox = numbers(&[r.x_min, r.y_min, r.x_max, r.y_max].map(metrics))?;
    let flags =
        4 + if face.is_monospaced() { 1 } else { 0 } + if face.is_italic() { 64 } else { 0 };
    let entries = if cff {
        "/Subtype /OpenType".into()
    } else {
        format!("/Length1 {}", bytes.len())
    };
    let file = writer.stream(&entries, &bytes)?;
    let font_file = if cff { "FontFile3" } else { "FontFile2" };
    let ascent = number(metrics(face.ascender()))?;
    let descent = number(metrics(face.descender()))?;
    let cap_height = number(metrics(face.capital_height().unwrap_or(face.ascender())))?;
    let italic_angle = number(f64::from(face.italic_angle()))?;
    let desc = writer.add(format!(
        "<< /Type /FontDescriptor /FontName /{name} /Flags {flags} /FontBBox [{bbox}] \
         /Ascent {ascent} /Descent {descent} /CapHeight {cap_height} /ItalicAngle {italic_angle} \
         /StemV 80 /{font_file} {file} 0 R >>"
    ))?;
    let one_byte = font.kind == Kind::WholeNamedCff;
    let per_font = if one_byte { 255 } else { u16::MAX as usize };
    for (chunk, id) in codes.chunks(per_font).zip(font.ids) {
        let mut unicode = vec![];
        let mut enc = vec![];
        let mut gids = vec![0, 0];
        let mut widths = BTreeMap::new();
        let mut names = vec![];
        for (i, ((gid, text), _)) in chunk.iter().enumerate() {
            writer.control.check()?;
            let code = i + 1;
            let key = if one_byte {
                format!("<{code:02X}>")
            } else {
                format!("<{code:04X}>")
            };
            unicode.push(format!("{key} <{}>", utf16(text)));
            let g = GlyphId(*gid);
            let mapped = mapper.get(*gid).unwrap_or(*gid);
            let cid = if font.kind == Kind::WholeCidCff {
                face.tables()
                    .cff
                    .and_then(|cff| cff.glyph_cid(g))
                    .ok_or_else(|| unsupported("Missing glyph CID"))? as usize
            } else if font.kind == Kind::SubsetCff {
                mapped as usize
            } else {
                code
            };
            let width = face
                .glyph_hor_advance(g)
                .ok_or_else(|| unsupported("Missing horizontal glyph metrics"))?;
            widths.insert(
                cid,
                number(f64::from(width) * 1000.0 / f64::from(face.units_per_em()))?,
            );
            if one_byte {
                let glyph_name = face
                    .tables()
                    .cff
                    .and_then(|cff| cff.glyph_name(g))
                    .ok_or_else(|| unsupported("Missing CFF glyph name"))?;
                names.push(format!("/{}", pdf_name(glyph_name)));
            } else if cff {
                enc.push(format!("{key} {cid}"));
            } else {
                gids.extend(mapped.to_be_bytes());
            }
        }
        let to_unicode = cmap(writer, &system, 2, one_byte, &unicode)?;
        if one_byte {
            let ws = widths.into_values().collect::<Vec<_>>().join(" ");
            let last = chunk.len();
            let differences = names.join(" ");
            writer.replace(id, format!(
                "<< /Type /Font /Subtype /Type1 /BaseFont /{name} /FirstChar 1 /LastChar {last} \
                 /Widths [{ws}] /Encoding << /Type /Encoding /Differences [1 {differences}] >> \
                 /FontDescriptor {desc} 0 R /ToUnicode {to_unicode} 0 R >>"
            ))?;
        } else {
            let ws = widths
                .into_iter()
                .map(|(cid, w)| format!("{cid} [{w}]"))
                .collect::<Vec<_>>()
                .join(" ");
            let (subtype, map, encoding) = if cff {
                (
                    "CIDFontType0",
                    String::new(),
                    format!("{} 0 R", cmap(writer, &system, 1, false, &enc)?),
                )
            } else {
                let map = writer.stream("", &gids)?;
                (
                    "CIDFontType2",
                    format!("/CIDToGIDMap {map} 0 R"),
                    "/Identity-H".into(),
                )
            };
            let descendant = writer.add(format!(
                "<< /Type /Font /Subtype /{subtype} /BaseFont /{name} {system} \
                 /FontDescriptor {desc} 0 R /W [{ws}] {map} >>"
            ))?;
            writer.replace(
                id,
                format!(
                    "<< /Type /Font /Subtype /Type0 /BaseFont /{name} /Encoding {encoding} \
                 /DescendantFonts [{descendant} 0 R] /ToUnicode {to_unicode} 0 R >>"
                ),
            )?;
        }
    }
    Ok(())
}
