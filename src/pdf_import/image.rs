use super::filters::{Codec, Filters};
use super::*;
use crate::{assets, model::Content};
use base64::Engine;
use num_rational::BigRational;
use num_traits::ToPrimitive;

#[derive(Default)]
pub(super) struct Images {
    pub assets: BTreeMap<String, assets::ImageAsset>,
    pub sources: BTreeMap<String, serde_json::Value>,
    pixels: u64,
    encoded_size: usize,
}

struct Plane<'a> {
    size: [u32; 2],
    components: usize,
    bits: usize,
    invert: [bool; 3],
    palette: Option<IndexedSamples>,
    color_key: Option<Vec<[u8; 2]>>,
    encoding: Encoding,
    filters: Filters<'a>,
}

struct IndexedSamples {
    entries: usize,
    by_code: Vec<[u8; 3]>,
}

impl IndexedSamples {
    fn new(
        pdf: &Container,
        colors: &[[u8; 3]],
        bits: usize,
        decode: Option<&Value>,
    ) -> Result<Self, Error> {
        let maximum = (1u16 << bits) - 1;
        let high = colors.len() - 1;
        let by_code = if let Some(decode) = decode {
            let Value::Array(values) = pdf.resolve(decode)? else {
                return Err(invalid("Expected indexed image Decode array"));
            };
            let [low, end] = values.as_slice() else {
                return Err(invalid("Expected two indexed image Decode endpoints"));
            };
            let exact = |v| match pdf.resolve(v)? {
                Value::Integer(i) => Ok(BigRational::from_integer((*i).into())),
                v => BigRational::from_float(number(v)?)
                    .ok_or_else(|| invalid("Invalid indexed image Decode endpoint")),
            };
            let start = exact(low)?;
            let step = (exact(end)? - &start) / BigRational::from_integer(maximum.into());
            let mut value = start;
            let mut table = Vec::with_capacity(usize::from(maximum) + 1);
            for _ in 0..=maximum {
                let index = value.round().to_integer();
                let index = if index < 0.into() {
                    0
                } else {
                    index.to_usize().unwrap_or(high).min(high)
                };
                table.push(colors[index]);
                value += &step;
            }
            table
        } else {
            (0..=maximum)
                .map(|code| colors[usize::from(code).min(high)])
                .collect()
        };
        Ok(Self {
            entries: colors.len(),
            by_code,
        })
    }
}

fn color_key(
    pdf: &Container,
    mask: &Value,
    components: usize,
    bits: usize,
) -> Result<Vec<[u8; 2]>, Error> {
    let Value::Array(values) = pdf.resolve(mask)? else {
        return Err(unsupported(
            "Explicit PDF image mask streams require stencil image support",
        ));
    };
    if values.len() != 2 * components {
        return Err(invalid("Wrong number of PDF color key endpoints"));
    }
    values
        .as_chunks::<2>()
        .0
        .iter()
        .map(|[low, high]| {
            let low = pdf.resolve(low)?.integer()?;
            let high = pdf.resolve(high)?.integer()?;
            if low > high || high >= 1 << bits {
                return Err(invalid(
                    "PDF color key range exceeds encoded sample levels or is reversed",
                ));
            }
            Ok([low as u8, high as u8])
        })
        .collect()
}

#[derive(Clone, Copy)]
enum Encoding {
    Samples { predictor: usize },
    AsciiHex,
    Jpeg { transform: bool },
}

fn hex_samples(
    bytes: &[u8],
    expected: usize,
    control: &Control,
) -> Result<(Vec<u8>, &'static str), Error> {
    let mut out = Vec::with_capacity(expected);
    let mut high = None;
    let mut ended = false;
    for chunk in bytes.chunks(16384) {
        control.check()?;
        for &byte in chunk {
            if matches!(byte, 0 | 9 | 10 | 12 | 13 | 32) {
                continue;
            }
            if ended {
                return Err(invalid("Unexpected data after ASCIIHex image end marker"));
            }
            if byte == b'>' {
                ended = true;
                if let Some(v) = high.take() {
                    out.push(v << 4);
                }
                continue;
            }
            if out.len() == expected {
                return Err(invalid("ASCIIHex image exceeds its sample count"));
            }
            let digit = match byte {
                b'0'..=b'9' => byte - b'0',
                b'a'..=b'f' => byte - b'a' + 10,
                b'A'..=b'F' => byte - b'A' + 10,
                _ => return Err(invalid("Invalid digit in ASCIIHex image")),
            };
            if let Some(v) = high.take() {
                out.push(v << 4 | digit);
            } else {
                high = Some(digit);
            }
        }
    }
    // Accept a writer's length-delimited image only at a complete byte and
    // exactly the known row extent. Odd nibble padding requires the marker.
    if high.is_some() || out.len() != expected {
        return Err(invalid("Incomplete ASCIIHex image samples"));
    }
    Ok((out, if ended { "marker" } else { "stream_length" }))
}

fn encoding(
    pdf: &Container,
    filters: Filters,
    width: u32,
    components: usize,
    bits: usize,
) -> Result<Encoding, Error> {
    let params = filters.params;
    if filters.codec == Codec::Hex {
        if let Some(params) = params {
            allowed(params, &[])?;
        }
        return Ok(Encoding::AsciiHex);
    }
    let integer = |key: &[u8], default| {
        params
            .and_then(|p| p.get(key))
            .map(|v| pdf.resolve(v)?.integer())
            .transpose()
            .map(|v| v.unwrap_or(default))
    };
    if filters.codec == Codec::Jpeg {
        if bits != 8 {
            return Err(unsupported("PDF JPEG images require 8-bit components"));
        }
        if let Some(params) = params {
            allowed(params, &[b"ColorTransform"])?;
        }
        let transform = integer(b"ColorTransform", usize::from(components == 3))?;
        if transform > 1 {
            return Err(unsupported("PDF JPEG ColorTransform must be zero or one"));
        }
        return Ok(Encoding::Jpeg {
            transform: transform == 1,
        });
    }
    if let Some(params) = params {
        if filters.codec == Codec::Raw && !filters.ascii85 {
            return Err(unsupported("PDF image prediction requires FlateDecode"));
        }
        allowed(
            params,
            &[b"Predictor", b"Colors", b"BitsPerComponent", b"Columns"],
        )?;
    }
    let predictor = integer(b"Predictor", 1)?;
    if !matches!(predictor, 1 | 2 | 10..=15) {
        return Err(unsupported("Unknown PDF image predictor"));
    }
    if predictor != 1
        && (integer(b"Colors", 1)? != components
            || integer(b"BitsPerComponent", 8)? != bits
            || integer(b"Columns", 1)? != width as usize)
    {
        return Err(unsupported(
            "PDF predictor layout differs from the image sample layout",
        ));
    }
    Ok(Encoding::Samples { predictor })
}

impl<'a> Plane<'a> {
    fn describe(
        pdf: &'a Container,
        d: &'a Dict,
        remaining: &mut usize,
        control: &Control,
    ) -> Result<Self, Error> {
        allowed(
            d,
            &[
                b"Type",
                b"Subtype",
                b"Width",
                b"Height",
                b"ColorSpace",
                b"BitsPerComponent",
                b"ImageMask",
                b"Interpolate",
                b"Decode",
                b"Mask",
                b"SMask",
                b"Length",
                b"Filter",
                b"DecodeParms",
                b"Name",
                b"Metadata",
            ],
        )?;
        if !field(d, b"Subtype")?.named(b"Image")
            || d.get(b"Type".as_slice())
                .is_some_and(|v| !v.named(b"XObject"))
        {
            return Err(unsupported("Expected a PDF image XObject"));
        }
        for key in [b"ImageMask".as_slice(), b"Interpolate"] {
            if let Some(value) = d.get(key)
                && !matches!(pdf.resolve(value)?, Value::Bool(false))
            {
                return Err(unsupported(
                    "PDF stencil masks and interpolated images require separate import semantics",
                ));
            }
        }
        let dimension = |key: &[u8]| {
            u32::try_from(pdf.resolve(field(d, key)?)?.integer()?)
                .map_err(|_| limit("PDF image dimension exceeds native limits"))
        };
        let size = [dimension(b"Width")?, dimension(b"Height")?];
        let pixels = assets::dimensions(size[0], size[1])?;
        if pixels > crate::pdf::MAX_IMAGE_PIXELS {
            return Err(limit("PDF image exceeds the page image pixel budget"));
        }
        let bits = pdf.resolve(field(d, b"BitsPerComponent")?)?.integer()?;
        if !matches!(bits, 1 | 2 | 4 | 8) {
            return Err(unsupported(
                "PDF image component depth cannot be represented exactly as RGBA8",
            ));
        }
        let space = pdf.resolve(field(d, b"ColorSpace")?)?;
        let decode = d.get(b"Decode".as_slice());
        let (components, palette) = if space.named(b"DeviceRGB") {
            (3, None)
        } else if space.named(b"DeviceGray") {
            (1, None)
        } else {
            let colors = color::palette(pdf, space, remaining, control)?;
            (1, Some(IndexedSamples::new(pdf, &colors, bits, decode)?))
        };
        let mut invert = [false; 3];
        if let Some(decode) = decode.filter(|_| palette.is_none()) {
            let Value::Array(values) = pdf.resolve(decode)? else {
                return Err(invalid("Expected PDF image Decode array"));
            };
            if values.len() != 2 * components {
                return Err(invalid("Wrong number of PDF image Decode endpoints"));
            }
            for (pair, inverted) in values.as_chunks::<2>().0.iter().zip(&mut invert) {
                *inverted = match [
                    number(pdf.resolve(&pair[0])?)?,
                    number(pdf.resolve(&pair[1])?)?,
                ] {
                    [0., 1.] => false,
                    [1., 0.] => true,
                    _ => {
                        return Err(unsupported(
                            "Editable PDF images require identity or inverted Decode ranges",
                        ));
                    }
                };
            }
        }
        let color_key = if d.contains_key(b"SMask".as_slice()) {
            None
        } else {
            d.get(b"Mask".as_slice())
                .map(|v| color_key(pdf, v, components, bits))
                .transpose()?
        };
        let filters = Filters::read(pdf, d)?;
        let encoding = encoding(pdf, filters, size[0], components, bits)?;
        Ok(Self {
            size,
            components,
            bits,
            invert,
            palette,
            color_key,
            encoding,
            filters,
        })
    }

    fn unpack(
        &self,
        pdf: &Container,
        id: Id,
        remaining: &mut usize,
        control: &Control,
        rgba: &mut [u8],
        alpha: bool,
    ) -> Result<serde_json::Value, Error> {
        let samples = self.size[0] as usize * self.components;
        let row = (samples * self.bits).div_ceil(8);
        let predictor = match self.encoding {
            Encoding::Samples { predictor } => predictor,
            Encoding::AsciiHex | Encoding::Jpeg { .. } => 1,
        };
        let png = predictor >= 10;
        let stride = row + usize::from(png);
        let expected = stride * self.size[1] as usize;
        if expected > *remaining {
            return Err(limit("PDF decoded stream budget exceeded"));
        }
        // Reserve the final sample plane before unwrapping compressed input.
        *remaining -= expected;
        let bytes = self
            .filters
            .payload(pdf.stream_bytes(id)?, expected, remaining, control)?;
        let (mut data, mut source) = match self.encoding {
            Encoding::Samples { .. } => {
                (self.filters.samples(bytes, expected, control)?, json!({}))
            }
            Encoding::AsciiHex => {
                let (samples, end) = hex_samples(&bytes, expected, control)?;
                (
                    samples,
                    json!({"filter":"ASCIIHexDecode","ascii_hex_end":end}),
                )
            }
            Encoding::Jpeg { transform } => crate::sample_import::pdf_samples(
                &bytes,
                self.size,
                self.components,
                transform,
                control,
            )?,
        };
        if data.len() != expected {
            return Err(invalid(
                "PDF image stream length disagrees with its dimensions",
            ));
        }
        if self.filters.ascii85 {
            source["filters"] = match self.filters.codec {
                Codec::Raw => json!(["ASCII85Decode"]),
                Codec::Flate => json!(["ASCII85Decode", "FlateDecode"]),
                Codec::Jpeg => json!(["ASCII85Decode", "DCTDecode"]),
                Codec::Hex => unreachable!(),
            };
        }
        let step = (self.bits * self.components).div_ceil(8);
        let maximum = ((1u16 << self.bits) - 1) as u8;
        let mut previous: &[u8] = &[];
        for (source, target) in data
            .chunks_exact_mut(stride)
            .zip(rgba.chunks_exact_mut(self.size[0] as usize * 4))
        {
            control.check()?;
            let row = if png {
                let (filter, bytes) = source.split_first_mut().expect("nonempty image scanline");
                unfilter(*filter, bytes, previous, step)?;
                bytes
            } else {
                source
            };
            let mut last = [0u8; 3];
            for (x, pixel) in target.as_chunks_mut::<4>().0.iter_mut().enumerate() {
                let mut transparent = self.color_key.is_some();
                for (channel, last) in last[..self.components].iter_mut().enumerate() {
                    let offset = (x * self.components + channel) * self.bits;
                    let mut code = (row[offset / 8] >> (8 - self.bits - offset % 8)) & maximum;
                    if predictor == 2 {
                        code = code.wrapping_add(*last) & maximum;
                        *last = code;
                    }
                    if let Some(key) = &self.color_key {
                        let [low, high] = key[channel];
                        transparent &= (low..=high).contains(&code);
                    }
                    if let Some(palette) = &self.palette {
                        pixel[..3].copy_from_slice(&palette.by_code[usize::from(code)]);
                        continue;
                    }
                    if self.invert[channel] {
                        code = maximum - code;
                    }
                    let value = code * (255 / maximum);
                    if alpha {
                        pixel[3] = value;
                    } else if self.components == 1 {
                        pixel[..3].fill(value);
                    } else {
                        pixel[channel] = value;
                    }
                }
                if transparent {
                    pixel[3] = 0;
                }
            }
            previous = row;
        }
        source["object"] = json!(id.0);
        source["generation"] = json!(id.1);
        Ok(source)
    }
}

fn unfilter(filter: u8, row: &mut [u8], previous: &[u8], step: usize) -> Result<(), Error> {
    if filter == 0 {
        return Ok(());
    }
    if filter > 4 {
        return Err(invalid("Unknown PDF PNG row filter"));
    }
    for i in 0..row.len() {
        let left = i.checked_sub(step).map_or(0, |j| row[j]);
        let up = previous.get(i).copied().unwrap_or(0);
        let value = match filter {
            1 => left,
            2 => up,
            3 => left.midpoint(up),
            _ => {
                let corner = i
                    .checked_sub(step)
                    .and_then(|j| previous.get(j))
                    .copied()
                    .unwrap_or(0);
                let estimate = i16::from(left) + i16::from(up) - i16::from(corner);
                let [a, b, c] = [left, up, corner].map(|v| estimate.abs_diff(i16::from(v)));
                if a <= b && a <= c {
                    left
                } else if b <= c {
                    up
                } else {
                    corner
                }
            }
        };
        row[i] = row[i].wrapping_add(value);
    }
    Ok(())
}

impl Images {
    pub fn placement(
        &mut self,
        pdf: &Container,
        id: Id,
        remaining: &mut usize,
        profile: ResourceProfile,
        control: &Control,
        page: usize,
    ) -> Result<(Content, [u32; 2]), Error> {
        let key = format!("image-{}-{}", id.0, id.1);
        if !self.assets.contains_key(&key) {
            if self.assets.len() >= assets::MAX_ASSETS {
                return Err(limit("PDF image asset count exceeded"));
            }
            let d = pdf.stream_dict(id)?;
            let plane = Plane::describe(pdf, d, remaining, control)?;
            let [width, height] = plane.size;
            let count = u64::from(width) * u64::from(height);
            if self.pixels + count > assets::MAX_ASSET_PIXELS {
                return Err(limit("PDF document image pixel budget exceeded"));
            }
            let mut rgba = vec![255; count as usize * 4];
            let mut source = plane.unpack(pdf, id, remaining, control, &mut rgba, false)?;
            source["components"] = json!(plane.components);
            source["bits_per_component"] = json!(plane.bits);
            if let Some(palette) = &plane.palette {
                source["palette_entries"] = json!(palette.entries);
            }
            if let Some(key) = &plane.color_key {
                source["color_key"] = json!(key);
            }
            if let Some(v) = d.get(b"SMask".as_slice()) {
                let mask_id = reference(v)?;
                let mut decode_mask = || {
                    let d = pdf.stream_dict(mask_id)?;
                    let mask = Plane::describe(pdf, d, remaining, control)?;
                    if mask.components != 1
                        || mask.palette.is_some()
                        || d.contains_key(b"Mask".as_slice())
                        || mask.size != plane.size
                        || d.contains_key(b"SMask".as_slice())
                    {
                        return Err(unsupported(
                            "PDF image soft mask requires a matching grayscale plane without another mask",
                        ));
                    }
                    mask.unpack(pdf, mask_id, remaining, control, &mut rgba, true)
                };
                source["soft_mask"] = decode_mask().map_err(|e| located(e, page, mask_id, None))?;
                if d.contains_key(b"Mask".as_slice()) {
                    source["mask_overridden_by_soft_mask"] = json!(true);
                }
            }
            let png = crate::render::encode_png(width, height, &rgba, 72.)?;
            self.encoded_size += png.len().div_ceil(3) * 4;
            if self.encoded_size > profile.bytes() {
                return Err(limit("PDF image assets exceed editable snapshot budget"));
            }
            let asset = assets::ImageAsset {
                width,
                height,
                sha256: assets::identity(width, height, &rgba),
                storage: assets::Storage::Encoded {
                    data_base64: base64::engine::general_purpose::STANDARD.encode(&png),
                    color_policy: assets::ColorPolicy::RequireSrgb,
                },
                provenance: Some(assets::Provenance {
                    source_profile_sha256: None,
                    source_sha256: assets::sha256(&png),
                    interpretation: assets::Interpretation::DeclaredSrgb,
                }),
            };
            self.assets.insert(key.clone(), asset);
            self.sources.insert(key.clone(), source);
            self.pixels += count;
        }
        let asset = &self.assets[&key];
        Ok((
            Content::Image {
                asset_id: key,
                width: f64::from(asset.width),
                height: f64::from(asset.height),
                crop: None,
                sampling: assets::Sampling::Nearest,
            },
            [asset.width, asset.height],
        ))
    }
}
