use super::*;
use std::rc::Rc;

#[derive(Clone)]
pub(super) enum FillSpace {
    Gray,
    Rgb,
    Indexed(Rc<[[u8; 3]]>),
}

impl FillSpace {
    pub fn select(
        pdf: &Container,
        resources: &Dict,
        name: &[u8],
        remaining: &mut usize,
        control: &Control,
    ) -> Result<Self, Error> {
        match name {
            b"DeviceGray" => return Ok(Self::Gray),
            b"DeviceRGB" => return Ok(Self::Rgb),
            b"DeviceCMYK" | b"Pattern" => {
                return Err(unsupported("Unsupported PDF fill color space"));
            }
            _ => {}
        }
        let value = pdf.resolve(drawing::resource(pdf, resources, b"ColorSpace", name)?)?;
        if value.named(b"DeviceGray") {
            return Ok(Self::Gray);
        }
        if value.named(b"DeviceRGB") {
            return Ok(Self::Rgb);
        }
        Ok(Self::Indexed(palette(pdf, value, remaining, control)?))
    }

    pub fn initial(&self) -> [f64; 3] {
        match self {
            Self::Indexed(table) => table[0].map(|v| f64::from(v) / 255.),
            _ => [0.; 3],
        }
    }
}

pub(super) fn palette(
    pdf: &Container,
    value: &Value,
    remaining: &mut usize,
    control: &Control,
) -> Result<Rc<[[u8; 3]]>, Error> {
    let Value::Array(parts) = value else {
        return Err(unsupported("Unsupported PDF color space"));
    };
    let [family, base, high, lookup] = parts.as_slice() else {
        return Err(unsupported("Expected an Indexed PDF color space"));
    };
    if !pdf.resolve(family)?.named(b"Indexed") {
        return Err(unsupported("Unsupported PDF color space"));
    }
    let base = pdf.resolve(base)?;
    let components = if base.named(b"DeviceRGB") {
        3
    } else if base.named(b"DeviceGray") {
        1
    } else {
        return Err(unsupported(
            "Indexed PDF colors require a DeviceRGB or DeviceGray base",
        ));
    };
    let high = pdf.resolve(high)?.integer()?;
    if high > 255 {
        return Err(invalid("PDF palette index exceeds 255"));
    }
    let expected = (high + 1) * components;
    if expected > *remaining {
        return Err(limit("PDF palette exceeds decoded byte budget"));
    }
    let stream;
    let bytes = if matches!(lookup, Value::Ref(id) if pdf.stream_dict(*id).is_ok()) {
        stream = filters::stream(pdf, reference(lookup)?, expected, remaining, control)?;
        stream.as_slice()
    } else if let Value::Bytes(bytes) = pdf.resolve(lookup)? {
        bytes.as_slice()
    } else {
        return Err(invalid("Expected a PDF palette string or stream"));
    };
    if bytes.len() != expected {
        return Err(invalid("PDF palette length differs from its declared size"));
    }
    *remaining -= expected;
    Ok(bytes
        .chunks_exact(components)
        .map(|c| {
            if components == 1 {
                [c[0]; 3]
            } else {
                [c[0], c[1], c[2]]
            }
        })
        .collect())
}
