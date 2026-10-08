//! Explicit omission of bounded descriptive records; appearance-bearing variants fail.
use super::{
    binary::Reader,
    descriptor::{self, Datum, Descriptor},
    *,
};
use std::collections::BTreeSet;

fn require(ok: bool) -> Result<(), Error> {
    if ok {
        Ok(())
    } else {
        Err(unsupported(
            "Active or unknown metadata semantics require an editable mapping",
        ))
    }
}
pub(super) fn layer(input: &mut Reader<'_>, control: &Control) -> Result<(), Error> {
    let count = input.word()?;
    if count > 16 {
        return Err(limit("Layer metadata exceeds 16 records"));
    }
    let mut keys = BTreeSet::new();
    for _ in 0..count {
        control.check()?;
        if input.take(4)? != b"8BIM" {
            return Err(malformed());
        }
        let key = input.take(4)?;
        if !keys.insert(key) {
            return Err(malformed());
        }
        require(key == b"cust")?;
        if input.byte()? > 1 || input.take(3)? != [0; 3] {
            return Err(malformed());
        }
        let mut payload = input.section()?;
        let mut d = descriptor::versioned(&mut payload, control)?;
        require(matches!(d.field("layerTime")?, Datum::Number(n) if n >= 0.0))?;
        d.finish("metadata")?;
        payload.zero_padding(3)?;
    }
    input.end()
}
fn version(mut d: Descriptor) -> Result<(), Error> {
    for key in ["major", "minor", "fix"] {
        require(d.field(key)?.integer()? >= 0)?;
    }
    d.finish("null")
}
fn backend(mut d: Descriptor) -> Result<(), Error> {
    for key in ["Vrsn", "psVersion"] {
        version(d.field(key)?.object()?)?;
    }
    for key in ["description", "reason"] {
        d.field(key)?.text()?;
    }
    for (key, kind, value) in [
        ("Engn", "Engn", "compCoreGPU"),
        ("enableCompCoreGPU", "enable", "feature"),
        ("enableCompCoreThreads", "enable", "feature"),
        ("compCoreGPUSupport", "reason", "supported"),
    ] {
        require(matches!(d.field(key)?, Datum::Enum(k, v) if k == kind && v == value))?;
    }
    d.finish("null")
}
fn global_record(key: &[u8; 4], data: &mut Reader<'_>, control: &Control) -> Result<(), Error> {
    match key {
        b"Patt" => {
            require(data.left() == 0)?;
        }
        b"CAI " => {
            require(data.word()? == 3)?;
            let mut d = descriptor::versioned(data, control)?;
            require(!d.field("enab")?.boolean()?)?;
            require(d.field("generationalGuid")?.text()?.is_empty())?;
            d.finish("null")?;
            // Disabled provenance record with empty auxiliary payloads.
            require(data.word()? == 0 && data.word()? == 0)?;
        }
        b"OCIO" => {
            let mut d = descriptor::versioned(data, control)?;
            require(d.field("Knd ")?.text()? == "icc")?;
            let mut view = d.field("ocio_display_view")?.object()?;
            require(view.field("display")?.text()?.is_empty())?;
            require(view.field("view")?.text()?.is_empty())?;
            view.finish("viewColorManagementInfo")?;
            d.finish("documentColorManagementInfo")?;
        }
        b"GenI" => {
            let mut d = descriptor::versioned(data, control)?;
            require(d.field("isUsingGenTech")?.integer()? == 0)?;
            require(matches!(d.field("externalModelList")?, Datum::List(v) if v.is_empty()))?;
            d.finish("genTechInfo")?;
        }
        b"cinf" => backend(descriptor::versioned(data, control)?)?,
        b"FMsk" => {
            // Overlay colour/opacity only; actual global and layer masks are rejected elsewhere.
            require(data.short()? == 0)?;
            for _ in 0..4 {
                data.short()?;
            }
            require(data.short()? <= 100)?;
        }
        _ => {
            return Err(unsupported(&format!(
                "Global information {} has no supported editable mapping",
                String::from_utf8_lossy(key)
            )));
        }
    }
    data.end()
}
pub(super) fn global(
    input: &mut Reader<'_>,
    ignored: &mut BTreeSet<String>,
    control: &Control,
    version: Version,
) -> Result<(), Error> {
    let mut keys = BTreeSet::new();
    while input.left() != 0 {
        control.check()?;
        if input.left() < 12 {
            return input.zero_padding(3);
        }
        let signature = input.take(4)?;
        if signature != b"8BIM" && !(version == Version::Large && signature == b"8B64") {
            return Err(malformed());
        }
        let key: [u8; 4] = input.take(4)?.try_into().unwrap();
        super::binary::tag_signature(signature, &key, version)?;
        if !keys.insert(key) {
            return Err(malformed());
        }
        let mut data = input.tagged_section(&key, version)?;
        let count = data.left();
        global_record(&key, &mut data, control).map_err(|mut error| {
            error.message = format!(
                "Global {}: {}",
                String::from_utf8_lossy(&key),
                error.message
            );
            error
        })?;
        if input.take((4 - count % 4) % 4)?.iter().any(|&b| b != 0) {
            return Err(malformed());
        }
        ignored.insert(format!("global:{}", String::from_utf8_lossy(&key)));
    }
    Ok(())
}

pub(super) fn alpha(key: u16, data: &mut Reader<'_>, channels: u16) -> Result<(), Error> {
    let expected = usize::from(channels == 4);
    match key {
        1006 => {
            for _ in 0..expected {
                let n = data.byte()? as usize;
                data.take(n)?;
            }
        }
        1045 => {
            for _ in 0..expected {
                data.unicode()?;
            }
        }
        1053 => {
            for _ in 0..expected {
                require(data.word()? == 0)?;
            }
        }
        1077 => {
            require(data.word()? == 1)?;
            for _ in 0..expected {
                require(data.short()? == 0)?;
                for _ in 0..4 {
                    data.short()?;
                }
                require(data.short()? <= 100)?;
                require(data.byte()? == 1)?;
            }
        }
        _ => unreachable!(),
    }
    data.end().map_err(|_| {
        unsupported("Additional alpha metadata cannot be mapped to merged transparency")
    })
}
