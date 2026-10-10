//! Original bounded mapping of placed records to retained editable sources.
use super::{
    binary::Reader,
    descriptor::{self, Datum, Descriptor},
    *,
};
use std::collections::BTreeMap;

#[derive(Debug)]
pub(super) struct Placement {
    pub source: String,
    pub identity: String,
    pub points: [f64; 8],
    pub size: [f64; 2],
    pub resolution: f64,
}
pub(super) struct Source<'a> {
    pub bytes: &'a [u8],
    pub filename: String,
    pub version: u32,
}
fn require(value: bool) -> Result<(), Error> {
    if value {
        Ok(())
    } else {
        Err(unsupported(
            "Embedded object fields require a supported still, affine, unwarped layered source",
        ))
    }
}
fn number(r: &mut Reader<'_>) -> Result<f64, Error> {
    let n = f64::from_be_bytes(r.take(8)?.try_into().unwrap());
    if n.is_finite() {
        Ok(n)
    } else {
        Err(malformed())
    }
}
fn identifier(value: String) -> Result<String, Error> {
    if value.is_empty()
        || value.len() > 128
        || !value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"-_.:".contains(&b))
    {
        return Err(malformed());
    }
    Ok(value)
}
fn string(r: &mut Reader<'_>) -> Result<String, Error> {
    let v = r.unicode()?;
    let v = v.strip_suffix('\0').unwrap_or(&v);
    if v.contains('\0') {
        return Err(malformed());
    }
    Ok(v.to_owned())
}
fn pascal_id(r: &mut Reader<'_>) -> Result<String, Error> {
    let n = r.byte()? as usize;
    identifier(String::from_utf8(r.take(n)?.to_vec()).map_err(|_| malformed())?)
}
fn unselected(mut d: Descriptor) -> Result<(), Error> {
    require(d.field("compID")?.integer()? == -1 && d.field("originalCompID")?.integer()? == -1)?;
    d.finish("null")
}
fn still(mut d: Descriptor) -> Result<(), Error> {
    require(d.field("numerator")?.integer()? == 0 && d.field("denominator")?.integer()? > 0)?;
    d.finish("null")
}
fn unwarped(mut d: Descriptor) -> Result<(), Error> {
    require(matches!(d.field("warpStyle")?, Datum::Enum(k,v) if k=="warpStyle" && v=="warpNone"))?;
    for key in ["warpValue", "warpPerspective", "warpPerspectiveOther"] {
        require(d.field(key)?.number()? == 0.0)?;
    }
    require(matches!(d.field("warpRotate")?, Datum::Enum(k,v) if k=="Ornt" && v=="Hrzn"))?;
    let mut bounds = d.field("bounds")?.object()?;
    let b = [
        bounds.field("Top ")?.number()?,
        bounds.field("Left")?.number()?,
        bounds.field("Btom")?.number()?,
        bounds.field("Rght")?.number()?,
    ];
    require(b[0] <= b[2] && b[1] <= b[3] && b.iter().all(|v| v.abs() <= MAX_COORDINATE * 2.0))?;
    bounds.finish("classFloatRect")?;
    require(d.field("uOrder")?.integer()? == 4 && d.field("vOrder")?.integer()? == 4)?;
    d.finish("warp")
}
fn points(value: Datum) -> Result<[f64; 8], Error> {
    let values = value
        .list()?
        .into_iter()
        .map(Datum::number)
        .collect::<Result<Vec<_>, _>>()?;
    let values: [f64; 8] = values.try_into().map_err(|_| malformed())?;
    require(values.iter().all(|v| v.abs() <= MAX_COORDINATE * 2.0))?;
    Ok(values)
}
pub(super) fn placement(r: &mut Reader<'_>, control: &Control) -> Result<Placement, Error> {
    require(r.take(4)? == b"soLD" && matches!(r.word()?, 4 | 5))?;
    let mut d = descriptor::versioned(r, control)?;
    let source = identifier(d.field("Idnt")?.text()?)?;
    let identity = identifier(d.field("placed")?.text()?)?;
    for (key, value) in [
        ("PgNm", 1),
        ("totalPages", 1),
        ("Crop", 1),
        ("frameCount", 1),
        ("Annt", 16),
        ("Type", 2),
        ("comp", -1),
    ] {
        require(d.field(key)?.integer()? == value)?;
    }
    still(d.field("frameStep")?.object()?)?;
    still(d.field("duration")?.object()?)?;
    let points = points(d.field("Trnf")?)?;
    require(points == self::points(d.field("nonAffineTransform")?)?)?;
    unwarped(d.field("warp")?.object()?)?;
    let mut size = d.field("Sz  ")?.object()?;
    let dimensions = [size.field("Wdth")?.number()?, size.field("Hght")?.number()?];
    size.finish("Pnt ")?;
    require(
        dimensions
            .iter()
            .all(|v| (1.0..=MAX_DIMENSION as f64).contains(v) && v.fract() == 0.0),
    )?;
    let resolution = match d.field("Rslt")? {
        Datum::Unit(unit, n) if unit == "#Rsl" && n > 0.0 => n,
        _ => return Err(malformed()),
    };
    unselected(d.field("compInfo")?.object()?)?;
    if let Some(color) = d.optional("ClMg") {
        let mut color = color.object()?;
        require(
            matches!(color.field("placedLayerOCIOConversion")?,Datum::Enum(k,v) if k=="placedLayerOCIOConversion" && v=="placedLayerOCIOConvertEmbedded"),
        )?;
        color.finish("ClMg")?;
    }
    d.finish("null")?;
    r.zero_padding(3)?;
    Ok(Placement {
        source,
        identity,
        points,
        size: dimensions,
        resolution,
    })
}
pub(super) fn legacy(r: &mut Reader<'_>, control: &Control) -> Result<(String, [f64; 8]), Error> {
    require(r.take(4)? == b"plcL" && r.word()? == 3)?;
    let id = pascal_id(r)?;
    for value in [1, 1, 16, 2] {
        require(r.word()? == value)?;
    }
    let mut points = [0.0; 8];
    for v in &mut points {
        *v = number(r)?;
    }
    require(r.word()? == 0)?;
    unwarped(descriptor::versioned(r, control)?)?;
    r.zero_padding(3)?;
    Ok((id, points))
}
pub(super) fn sources<'a>(
    r: &mut Reader<'a>,
    control: &Control,
) -> Result<BTreeMap<String, Source<'a>>, Error> {
    let mut sources = BTreeMap::new();
    while r.left() != 0 {
        control.check()?;
        if sources.len() >= MAX_ITEMS {
            return Err(limit("Embedded source table exceeds 256 records"));
        }
        let mut entry = r.framed_section(Version::Large)?;
        require(entry.take(4)? == b"liFD")?;
        let version = entry.word()?;
        require((1..=8).contains(&version))?;
        let id = pascal_id(&mut entry)?;
        let filename = string(&mut entry)?;
        require(matches!(entry.take(4)?, b"8BPS" | b"8BPB"))?;
        entry.take(4)?; // Creator identity has no execution or appearance semantics.
        let length = entry.length(Version::Large)?;
        match entry.byte()? {
            0 => {}
            1 => {
                let mut d = descriptor::prefix(&mut entry, control)?;
                unselected(d.field("compInfo")?.object()?)?;
                d.finish("null")?;
            }
            _ => return Err(malformed()),
        }
        let bytes = entry.take(length)?;
        if version >= 5 {
            string(&mut entry)?;
        }
        if version >= 6 {
            require(number(&mut entry)? == 0.0)?;
        }
        if version >= 7 {
            require(entry.byte()? == 0)?;
        }
        if version >= 8 {
            let mut d = descriptor::versioned(&mut entry, control)?;
            identifier(d.field("contentID")?.text()?)?;
            d.finish("null")?;
        }
        if entry.left() != 0 && entry.left() != (4 - entry.at % 4) % 4 {
            return Err(malformed());
        }
        entry.zero_padding(3)?;
        if sources
            .insert(
                id,
                Source {
                    bytes,
                    filename,
                    version,
                },
            )
            .is_some()
        {
            return Err(malformed());
        }
    }
    Ok(sources)
}

impl Placement {
    pub fn matrix(&self) -> Result<Matrix, Error> {
        let p = self.points;
        let [w, h] = self.size;
        let m = [
            (p[2] - p[0]) / w,
            (p[3] - p[1]) / w,
            (p[6] - p[0]) / h,
            (p[7] - p[1]) / h,
            p[0],
            p[1],
        ];
        crate::geometry::validate_matrix(m)?;
        let opposite = crate::geometry::map(m, [w, h]);
        require((opposite[0] - p[4]).abs() <= 1e-9 && (opposite[1] - p[5]).abs() <= 1e-9)?;
        Ok(m)
    }
}
