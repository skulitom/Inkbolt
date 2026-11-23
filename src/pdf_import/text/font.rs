use super::super::*;
use super::cmap;
use rustybuzz::ttf_parser::{Face, GlyphId, PlatformId};

enum Encoding {
    SymbolMac,
    Named(BTreeMap<u16, String>),
    SimpleGlyphs(BTreeMap<u16, u16>),
    Identity,
    CidToGlyph(Vec<u8>),
    CffCid {
        codes: Option<BTreeMap<u16, u16>>,
        glyphs: BTreeMap<u16, u16>,
        system: cmap::SystemInfo,
    },
}

pub(super) struct Font {
    pub bytes: Vec<u8>,
    pub stream: Id,
    pub digest: String,
    pub unicode: cmap::CharacterMap,
    encoding: Encoding,
    widths: BTreeMap<u16, f64>,
    default_width: Option<f64>,
}

fn stream(
    pdf: &Container,
    id: Id,
    remaining: &mut usize,
    control: &Control,
) -> Result<Vec<u8>, Error> {
    let bytes = filters::stream(pdf, id, *remaining, remaining, control)?;
    *remaining -= bytes.len();
    Ok(bytes)
}
fn cid(value: &Value) -> Result<u16, Error> {
    u16::try_from(value.integer()?).map_err(|_| invalid("Invalid PDF character identifier"))
}

fn named_codes(pdf: &Container, value: &Value) -> Result<Encoding, Error> {
    let enc = pdf.resolve(value)?.dict()?;
    allowed(enc, &[b"Type", b"Differences"])?;
    if enc
        .get(b"Type".as_slice())
        .is_some_and(|v| !v.named(b"Encoding"))
    {
        return Err(invalid("Invalid simple font encoding type"));
    }
    let Value::Array(list) = pdf.resolve(field(enc, b"Differences")?)? else {
        return Err(invalid("Expected explicit PDF glyph names"));
    };
    let mut map = BTreeMap::new();
    let mut next = None;
    for entry in list {
        match entry {
            Value::Integer(_) => {
                next = Some(
                    u8::try_from(entry.integer()?)
                        .map_err(|_| invalid("Simple font code exceeds one byte"))?,
                )
            }
            Value::Name(name) => {
                let code = next.ok_or_else(|| invalid("Missing simple font character code"))?;
                let name = std::str::from_utf8(name)
                    .map_err(|_| unsupported("Unsupported CFF glyph name"))?;
                if map.insert(u16::from(code), name.to_owned()).is_some() {
                    return Err(invalid("Duplicate PDF simple font character code"));
                }
                next = code.checked_add(1);
            }
            _ => return Err(invalid("Invalid simple font encoding difference")),
        }
    }
    Ok(Encoding::Named(map))
}

fn cff_cid_encoding(
    pdf: &Container,
    encoding: &Value,
    descendant: &Dict,
    remaining: &mut usize,
    control: &Control,
) -> Result<Encoding, Error> {
    if descendant.contains_key(b"CIDToGIDMap".as_slice()) {
        return Err(unsupported(
            "Unexpected glyph map for a compact outline font",
        ));
    }
    let system = cmap::SystemInfo::read(pdf.resolve(field(descendant, b"CIDSystemInfo")?)?)?;
    let codes = if encoding.named(b"Identity-H") {
        None
    } else {
        let id = reference(encoding)?;
        let fields = pdf.stream_dict(id)?;
        allowed(
            fields,
            &[
                b"Type",
                b"CMapName",
                b"CIDSystemInfo",
                b"WMode",
                b"Length",
                b"Filter",
                b"DecodeParms",
            ],
        )?;
        if !field(fields, b"Type")?.named(b"CMap")
            || fields
                .get(b"WMode".as_slice())
                .is_some_and(|v| v.integer().ok() != Some(0))
        {
            return Err(unsupported("Expected a horizontal PDF encoding map"));
        }
        let bytes = stream(pdf, id, remaining, control)?;
        let map = cmap::read(&bytes, true, remaining, control)?;
        if map.width != 2
            || map.system.as_ref() != Some(&system)
            || cmap::SystemInfo::read(pdf.resolve(field(fields, b"CIDSystemInfo")?)?)? != system
            || !map.name.as_ref().is_some_and(|n| {
                fields
                    .get(b"CMapName".as_slice())
                    .is_some_and(|v| v.named(n))
            })
        {
            return Err(invalid(
                "Encoding map and descendant character collections disagree",
            ));
        }
        Some(map.cids)
    };
    Ok(Encoding::CffCid {
        codes,
        glyphs: BTreeMap::new(),
        system,
    })
}

fn cid_glyphs(
    face: &Face,
    system: &cmap::SystemInfo,
    remaining: &mut usize,
) -> Result<BTreeMap<u16, u16>, Error> {
    use write_fonts::read::{
        FontData, FontRead,
        ps::cff::{charset::Charset, dict, v1::Cff},
    };
    let bad = || invalid("Invalid embedded compact font character collection");
    let raw = face
        .raw_face()
        .table(rustybuzz::ttf_parser::Tag::from_bytes(b"CFF "))
        .ok_or_else(bad)?;
    let data = FontData::new(raw);
    let cff = Cff::read(data).map_err(|_| bad())?;
    let top = cff.top_dicts().get(0).map_err(|_| bad())?;
    let mut offset = None;
    let mut collection = false;
    for entry in dict::entries(top, None) {
        match entry.map_err(|_| bad())? {
            dict::Entry::Charset(start) if start >= 3 && offset.is_none() => offset = Some(start),
            dict::Entry::Ros {
                registry,
                ordering,
                supplement,
            } if !collection
                && cff.string(registry) == Some(&system.registry)
                && cff.string(ordering) == Some(&system.ordering)
                && usize::try_from(supplement.to_i32()).ok() == Some(system.supplement) =>
            {
                collection = true
            }
            dict::Entry::Ros { .. } | dict::Entry::Charset(_) => return Err(bad()),
            _ => (),
        }
    }
    if !collection {
        return Err(bad());
    }
    let count = face.number_of_glyphs();
    *remaining = remaining
        .checked_sub(usize::from(count) * 4)
        .ok_or_else(|| limit("Embedded character set exceeds decode budget"))?;
    let charset =
        Charset::new(data, offset.ok_or_else(bad)?, u32::from(count)).map_err(|_| bad())?;
    let mut glyphs = BTreeMap::new();
    for (gid, cid) in charset.iter().take(usize::from(count)) {
        let gid = u16::try_from(gid.to_u32()).map_err(|_| bad())?;
        if glyphs.insert(cid.to_u16(), gid).is_some() {
            return Err(bad());
        }
    }
    if glyphs.len() != usize::from(count) || glyphs.get(&0) != Some(&0) {
        return Err(bad());
    }
    Ok(glyphs)
}

/// Resolve Differences once. A page can show the same byte thousands of times.
fn named_glyphs(face: &Face, names: &BTreeMap<u16, String>) -> Result<BTreeMap<u16, u16>, Error> {
    use write_fonts::read::{FontData, FontRead, ps::cff::v1::Cff};
    let bad = || unsupported("Expected one name-keyed compact font with an explicit charset");
    let raw = face
        .raw_face()
        .table(rustybuzz::ttf_parser::Tag::from_bytes(b"CFF "))
        .ok_or_else(bad)?;
    let cff = Cff::read(FontData::new(raw)).map_err(|_| bad())?;
    let charset = cff.charset(0).map_err(|_| bad())?.ok_or_else(bad)?;
    let wanted = names
        .values()
        .map(String::as_bytes)
        .collect::<BTreeSet<_>>();
    let mut by_name = BTreeMap::new();
    for (gid, sid) in charset.iter().take(usize::from(face.number_of_glyphs())) {
        let name = cff.string(sid).ok_or_else(bad)?;
        if wanted.contains(name) && by_name.insert(name, gid.to_u32() as u16).is_some() {
            return Err(invalid(
                "Repeated referenced glyph name in embedded compact font",
            ));
        }
    }
    Ok(names
        .iter()
        .filter_map(|(code, name)| Some((*code, *by_name.get(name.as_bytes())?)))
        .collect())
}
fn cid_widths(
    pdf: &Container,
    value: Option<&Value>,
    remaining: &mut usize,
) -> Result<BTreeMap<u16, f64>, Error> {
    let mut widths = BTreeMap::new();
    let Some(value) = value else {
        return Ok(widths);
    };
    let Value::Array(list) = pdf.resolve(value)? else {
        return Err(invalid("Expected a CID width array"));
    };
    let mut items = list.iter();
    while let Some(first) = items.next() {
        let first = cid(pdf.resolve(first)?)?;
        let next = items
            .next()
            .ok_or_else(|| invalid("Incomplete CID widths"))?;
        let mut insert = |code, width| {
            *remaining = remaining
                .checked_sub(std::mem::size_of::<(u16, f64)>())
                .ok_or_else(|| limit("Expanded CID widths exceed decode budget"))?;
            if widths.insert(code, width).is_some() {
                Err(invalid("Overlapping PDF CID widths"))
            } else {
                Ok(())
            }
        };
        match pdf.resolve(next)? {
            Value::Array(values) => {
                for (i, w) in values.iter().enumerate() {
                    let code = usize::from(first)
                        .checked_add(i)
                        .and_then(|v| u16::try_from(v).ok())
                        .ok_or_else(|| invalid("CID width index overflow"))?;
                    insert(code, number(pdf.resolve(w)?)?)?;
                }
            }
            last => {
                let last = cid(last)?;
                let w = number(
                    pdf.resolve(
                        items
                            .next()
                            .ok_or_else(|| invalid("Missing CID range width"))?,
                    )?,
                )?;
                if last < first {
                    return Err(invalid("Reversed CID width range"));
                }
                for i in first..=last {
                    insert(i, w)?;
                }
            }
        }
    }
    Ok(widths)
}

impl Font {
    pub fn read(
        pdf: &Container,
        id: Id,
        remaining: &mut usize,
        control: &Control,
    ) -> Result<Self, Error> {
        let reference_to_font = Value::Ref(id);
        let font = pdf.resolve(&reference_to_font)?;
        let dict = font.dict()?;
        let sub = field(dict, b"Subtype")?;
        if !field(dict, b"Type")?.named(b"Font") {
            return Err(invalid("Expected a PDF font resource"));
        }
        let (owner, mut encoding, widths, default_width, code_width) = if sub.named(b"TrueType")
            || sub.named(b"Type1")
        {
            if !dict.contains_key(b"ToUnicode".as_slice())
                || !dict.contains_key(b"FontDescriptor".as_slice())
            {
                return Err(unsupported(
                    "Editable PDF text requires an embedded font and explicit Unicode map",
                ));
            }
            allowed(
                dict,
                &[
                    b"Type",
                    b"Subtype",
                    b"Name",
                    b"BaseFont",
                    b"FirstChar",
                    b"LastChar",
                    b"Widths",
                    b"FontDescriptor",
                    b"ToUnicode",
                    b"Encoding",
                ],
            )?;
            let first = field(dict, b"FirstChar")?.integer()?;
            let last = field(dict, b"LastChar")?.integer()?;
            let Value::Array(list) = pdf.resolve(field(dict, b"Widths")?)? else {
                return Err(invalid("Expected simple font widths"));
            };
            if first > last || last > 255 || list.len() != last - first + 1 {
                return Err(invalid("Invalid simple font width range"));
            }
            let mut widths = BTreeMap::new();
            for (i, w) in list.iter().enumerate() {
                widths.insert((first + i) as u16, number(pdf.resolve(w)?)?);
            }
            let encoding = if sub.named(b"Type1") {
                named_codes(pdf, field(dict, b"Encoding")?)?
            } else if !dict.contains_key(b"Encoding".as_slice()) {
                Encoding::SymbolMac
            } else {
                return Err(unsupported("Unsupported simple TrueType font encoding"));
            };
            (dict, encoding, widths, None, 1)
        } else if sub.named(b"Type0") {
            allowed(
                dict,
                &[
                    b"Type",
                    b"Subtype",
                    b"Name",
                    b"BaseFont",
                    b"Encoding",
                    b"DescendantFonts",
                    b"ToUnicode",
                ],
            )?;
            let Value::Array(descendants) = pdf.resolve(field(dict, b"DescendantFonts")?)? else {
                return Err(invalid("Expected CID descendant list"));
            };
            let [descendant] = descendants.as_slice() else {
                return Err(invalid("Expected one CID descendant"));
            };
            let d = pdf.resolve(descendant)?.dict()?;
            if !field(d, b"Type")?.named(b"Font") {
                return Err(invalid("Expected a descendant font"));
            }
            allowed(
                d,
                &[
                    b"Type",
                    b"Subtype",
                    b"BaseFont",
                    b"CIDSystemInfo",
                    b"FontDescriptor",
                    b"DW",
                    b"W",
                    b"CIDToGIDMap",
                ],
            )?;
            let encoding = if field(d, b"Subtype")?.named(b"CIDFontType0") {
                cff_cid_encoding(pdf, field(dict, b"Encoding")?, d, remaining, control)?
            } else if field(d, b"Subtype")?.named(b"CIDFontType2")
                && field(dict, b"Encoding")?.named(b"Identity-H")
            {
                match d.get(b"CIDToGIDMap".as_slice()) {
                    None => Encoding::Identity,
                    Some(value) if value.named(b"Identity") => Encoding::Identity,
                    Some(value) => {
                        let id = reference(value)?;
                        allowed(
                            pdf.stream_dict(id)?,
                            &[b"Length", b"Filter", b"DecodeParms"],
                        )?;
                        let map = stream(pdf, id, remaining, control)?;
                        if map.len() % 2 != 0 || map.len() > 2 * (usize::from(u16::MAX) + 1) {
                            return Err(invalid("Invalid CID to glyph map length"));
                        }
                        Encoding::CidToGlyph(map)
                    }
                }
            } else {
                return Err(unsupported("Unsupported horizontal CID encoding"));
            };
            (
                d,
                encoding,
                cid_widths(pdf, d.get(b"W".as_slice()), remaining)?,
                Some(
                    d.get(b"DW".as_slice())
                        .map(|v| number(pdf.resolve(v)?))
                        .transpose()?
                        .unwrap_or(1000.),
                ),
                2,
            )
        } else {
            return Err(unsupported(
                "Editable PDF labels require a supported static outline font",
            ));
        };
        let descriptor = pdf.resolve(field(owner, b"FontDescriptor")?)?.dict()?;
        if !field(descriptor, b"Type")?.named(b"FontDescriptor") {
            return Err(invalid("Expected PDF font descriptor"));
        }
        let cff = matches!(encoding, Encoding::Named(_) | Encoding::CffCid { .. });
        if [b"FontFile".as_slice(), b"FontFile2", b"FontFile3"]
            .into_iter()
            .filter(|&key| descriptor.contains_key(key))
            .count()
            != 1
        {
            return Err(unsupported("Expected one embedded static font program"));
        }
        let id = reference(field(
            descriptor,
            if cff { b"FontFile3" } else { b"FontFile2" },
        )?)?;
        let fields = pdf.stream_dict(id)?;
        if cff {
            allowed(fields, &[b"Length", b"Subtype", b"Filter", b"DecodeParms"])?;
            if !field(fields, b"Subtype")?.named(b"OpenType") {
                return Err(unsupported("Expected an OpenType compact font program"));
            }
        } else {
            allowed(fields, &[b"Length", b"Length1", b"Filter", b"DecodeParms"])?;
        }
        let bytes = filters::stream(
            pdf,
            id,
            crate::fonts::MAX_FONT_BYTES as usize,
            remaining,
            control,
        )?;
        *remaining -= bytes.len();
        if let Some(n) = fields.get(b"Length1".as_slice())
            && pdf.resolve(n)?.integer()? != bytes.len()
        {
            return Err(invalid(
                "Embedded TrueType length disagrees with the descriptor",
            ));
        }
        let face = Face::parse(&bytes, 0).map_err(|_| invalid("Invalid embedded font"))?;
        crate::fonts::require_outline_face(&face)?;
        if face.tables().glyf.is_some() == cff
            || face.tables().cff.is_some() != cff
            || face.is_variable()
            || face.tables().cff2.is_some()
            || bytes.starts_with(b"ttcf")
        {
            return Err(unsupported(
                "PDF label requires a matching static outline program",
            ));
        }
        match &mut encoding {
            Encoding::CffCid { glyphs, system, .. } => {
                *glyphs = cid_glyphs(&face, system, remaining)?
            }
            Encoding::Named(names) => {
                encoding = Encoding::SimpleGlyphs(named_glyphs(&face, names)?)
            }
            _ => (),
        }
        if matches!(encoding, Encoding::SymbolMac) {
            let flags = field(descriptor, b"Flags")?.integer()?;
            let tables = face
                .tables()
                .cmap
                .ok_or_else(|| unsupported("Simple embedded TrueType font has no character map"))?
                .subtables;
            if flags & 4 == 0
                || flags & 32 != 0
                || tables
                    .into_iter()
                    .any(|t| t.platform_id == PlatformId::Windows && t.encoding_id == 0)
                || tables
                    .into_iter()
                    .filter(|t| t.platform_id == PlatformId::Macintosh && t.encoding_id == 0)
                    .count()
                    != 1
            {
                return Err(unsupported(
                    "Simple symbolic PDF font requires one Macintosh byte encoding",
                ));
            }
        }
        let to_unicode = reference(field(dict, b"ToUnicode")?)?;
        allowed(
            pdf.stream_dict(to_unicode)?,
            &[b"Length", b"Filter", b"DecodeParms"],
        )?;
        let unicode = cmap::read(
            &stream(pdf, to_unicode, remaining, control)?,
            false,
            remaining,
            control,
        )?;
        if unicode.width != code_width {
            return Err(invalid("ToUnicode width disagrees with font encoding"));
        }
        Ok(Self {
            digest: crate::assets::sha256(&bytes),
            bytes,
            stream: id,
            unicode,
            encoding,
            widths,
            default_width,
        })
    }
    pub fn width(&self, code: u16) -> Result<f64, Error> {
        let code = self.character_id(code)?;
        self.widths
            .get(&code)
            .copied()
            .or(self.default_width)
            .ok_or_else(|| unsupported("Missing width for painted PDF character"))
    }
    fn character_id(&self, code: u16) -> Result<u16, Error> {
        match &self.encoding {
            Encoding::CffCid {
                codes: Some(codes), ..
            } => codes
                .get(&code)
                .copied()
                .ok_or_else(|| unsupported("Painted code is absent from the encoding map")),
            _ => Ok(code),
        }
    }
    pub fn glyph(&self, face: &Face, code: u16) -> Result<GlyphId, Error> {
        let gid = match &self.encoding {
            Encoding::SymbolMac => face
                .tables()
                .cmap
                .and_then(|t| {
                    t.subtables
                        .into_iter()
                        .find(|t| t.platform_id == PlatformId::Macintosh && t.encoding_id == 0)
                })
                .and_then(|t| t.glyph_index(u32::from(code)))
                .map(|g| g.0),
            Encoding::Identity => Some(code),
            Encoding::SimpleGlyphs(glyphs) => glyphs.get(&code).copied(),
            Encoding::Named(_) => return Err(invalid("Unresolved compact font encoding")),
            Encoding::CffCid { glyphs, .. } => glyphs.get(&self.character_id(code)?).copied(),
            Encoding::CidToGlyph(map) => map
                .get(usize::from(code) * 2..usize::from(code) * 2 + 2)
                .map(|b| u16::from_be_bytes([b[0], b[1]])),
        };
        gid.filter(|&g| g != 0 && g < face.number_of_glyphs())
            .map(GlyphId)
            .ok_or_else(|| unsupported("Painted PDF code has no identifiable embedded glyph"))
    }
}
