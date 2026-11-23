//! Stream filters used by public page content, palettes and image planes.
use super::*;
use std::borrow::Cow;

#[derive(Clone, Copy, PartialEq)]
pub(super) enum Codec {
    Raw,
    Flate,
    Jpeg,
    Hex,
}

#[derive(Clone, Copy)]
pub(super) struct Filters<'a> {
    pub ascii85: bool,
    pub codec: Codec,
    pub params: Option<&'a Dict>,
}

fn parameters<'a>(pdf: &'a Container, v: &'a Value) -> Result<Option<&'a Dict>, Error> {
    match pdf.resolve(v)? {
        Value::Null => Ok(None),
        v => Ok(Some(v.dict()?)),
    }
}

impl<'a> Filters<'a> {
    pub fn read(pdf: &'a Container, dict: &'a Dict) -> Result<Self, Error> {
        let value = dict
            .get(b"Filter".as_slice())
            .map(|v| pdf.resolve(v))
            .transpose()?;
        let filters = match value {
            Some(Value::Array(entries)) => entries.as_slice(),
            Some(v) => std::slice::from_ref(v),
            None => &[],
        };
        let first = filters.first().map(|v| pdf.resolve(v)).transpose()?;
        let ascii85 = first.is_some_and(|v| v.named(b"ASCII85Decode"));
        let inner = match filters {
            [] if value.is_none() => None,
            [_] if ascii85 => None,
            [_] => first,
            [_, second] if ascii85 => Some(pdf.resolve(second)?),
            _ => return Err(unsupported("Unsupported PDF stream filter chain")),
        };
        let codec = match inner {
            None => Codec::Raw,
            Some(v) if v.named(b"FlateDecode") => Codec::Flate,
            Some(v) if v.named(b"DCTDecode") => Codec::Jpeg,
            Some(v) if !ascii85 && v.named(b"ASCIIHexDecode") => Codec::Hex,
            _ => return Err(unsupported("Unsupported PDF stream filter")),
        };
        let params = match dict
            .get(b"DecodeParms".as_slice())
            .map(|v| pdf.resolve(v))
            .transpose()?
        {
            None | Some(Value::Null) => None,
            Some(Value::Array(entries)) if value.is_none() && entries.len() == 1 => {
                // The image reader already accepts a single null parameter on raw samples.
                parameters(pdf, &entries[0])?
            }
            Some(Value::Array(entries)) if entries.len() == filters.len() => {
                if let [outer, _] = entries.as_slice()
                    && let Some(dict) = parameters(pdf, outer)?
                {
                    allowed(dict, &[])?;
                }
                entries
                    .last()
                    .map(|v| parameters(pdf, v))
                    .transpose()?
                    .flatten()
            }
            Some(Value::Dict(params)) if filters.len() <= 1 => Some(params),
            _ => return Err(invalid("PDF decode parameters must match the filter chain")),
        };
        if ascii85
            && codec == Codec::Raw
            && let Some(params) = params
        {
            allowed(params, &[])?;
        }
        Ok(Self {
            ascii85,
            codec,
            params,
        })
    }

    pub fn payload<'b>(
        &self,
        raw: &'b [u8],
        maximum: usize,
        remaining: &mut usize,
        control: &Control,
    ) -> Result<Cow<'b, [u8]>, Error> {
        if !self.ascii85 {
            return Ok(Cow::Borrowed(raw));
        }
        let intermediate = self.codec != Codec::Raw;
        let cap = if intermediate { *remaining } else { maximum };
        let bytes = ascii85(raw, cap, control)?;
        if intermediate {
            *remaining -= bytes.len();
        }
        Ok(Cow::Owned(bytes))
    }

    pub fn samples(
        &self,
        bytes: Cow<'_, [u8]>,
        maximum: usize,
        control: &Control,
    ) -> Result<Vec<u8>, Error> {
        match self.codec {
            Codec::Raw if bytes.len() <= maximum => Ok(bytes.into_owned()),
            Codec::Raw => Err(limit("PDF decoded stream budget exceeded")),
            Codec::Flate => vector_native::pdf_read::inflate_bytes(&bytes, maximum, control),
            _ => Err(unsupported(
                "Unsupported filter for PDF graphics or palette stream",
            )),
        }
    }
}

pub(super) fn stream(
    pdf: &Container,
    id: Id,
    maximum: usize,
    remaining: &mut usize,
    control: &Control,
) -> Result<Vec<u8>, Error> {
    let filters = Filters::read(pdf, pdf.stream_dict(id)?)?;
    if let Some(params) = filters.params {
        allowed(params, &[])?;
    }
    let bytes = filters.payload(
        pdf.stream_bytes(id)?,
        maximum.min(*remaining),
        remaining,
        control,
    )?;
    filters.samples(bytes, maximum.min(*remaining), control)
}

fn ascii85(raw: &[u8], maximum: usize, control: &Control) -> Result<Vec<u8>, Error> {
    let mut bytes = Vec::new();
    let mut digits = [0u8; 5];
    let mut count = 0;
    let mut ended = false;
    let mut input = raw.iter().copied().enumerate();
    while let Some((offset, c)) = input.next() {
        if offset % 16384 == 0 {
            control.check()?;
        }
        if matches!(c, 0 | 9 | 10 | 12 | 13 | 32) {
            continue;
        }
        if ended {
            return Err(invalid("Data after ASCII85 end marker"));
        }
        let length = match c {
            b'!'..=b'u' => {
                digits[count] = c - b'!';
                count += 1;
                if count < 5 {
                    continue;
                }
                4
            }
            b'z' if count == 0 => {
                digits.fill(0);
                4
            }
            b'~' if input.next().is_some_and(|(_, next)| next == b'>') => {
                ended = true;
                if count == 0 {
                    continue;
                }
                if count == 1 {
                    return Err(invalid("Incomplete final ASCII85 group"));
                }
                digits[count..].fill(84);
                count - 1
            }
            _ => return Err(invalid("Invalid ASCII85 digit or end marker")),
        };
        if length > maximum - bytes.len() {
            return Err(limit("PDF ASCII85 decoded stream budget exceeded"));
        }
        let word = digits.iter().fold(0u64, |v, &d| v * 85 + u64::from(d));
        let word = u32::try_from(word).map_err(|_| invalid("ASCII85 group exceeds four bytes"))?;
        bytes.extend_from_slice(&word.to_be_bytes()[..length]);
        count = 0;
    }
    if !ended {
        return Err(invalid("Missing ASCII85 end marker"));
    }
    Ok(bytes)
}
