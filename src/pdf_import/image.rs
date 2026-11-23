use super::*;
use crate::{assets, model::Content};
use base64::Engine;

#[derive(Default)]
pub(super) struct Images {
    pub assets: BTreeMap<String, assets::ImageAsset>,
    pub sources: BTreeMap<String, serde_json::Value>,
    pixels: u64,
    encoded_size: usize,
}

struct Plane {
    size: [u32; 2],
    components: usize,
    bits: usize,
    invert: [bool; 3],
    predictor: usize,
}

impl Plane {
    fn describe(pdf: &Container, d: &Dict) -> Result<Self, Error> {
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
        let space = pdf.resolve(field(d, b"ColorSpace")?)?;
        let components = if space.named(b"DeviceRGB") {
            3
        } else if space.named(b"DeviceGray") {
            1
        } else {
            return Err(unsupported(
                "Editable PDF images require DeviceRGB or DeviceGray",
            ));
        };
        let bits = pdf.resolve(field(d, b"BitsPerComponent")?)?.integer()?;
        if !matches!(bits, 1 | 2 | 4 | 8) {
            return Err(unsupported(
                "PDF image component depth cannot be represented exactly as RGBA8",
            ));
        }
        let mut invert = [false; 3];
        if let Some(decode) = d.get(b"Decode".as_slice()) {
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
        let mut predictor = 1;
        if let Some(params) = d.get(b"DecodeParms".as_slice()) {
            let params = pdf.single_filter_entry(params)?;
            if !matches!(params, Value::Null) {
                if !pdf
                    .single_filter_entry(field(d, b"Filter")?)?
                    .named(b"FlateDecode")
                {
                    return Err(unsupported("PDF image prediction requires FlateDecode"));
                }
                let params = params.dict()?;
                allowed(
                    params,
                    &[b"Predictor", b"Colors", b"BitsPerComponent", b"Columns"],
                )?;
                let integer = |key: &[u8], default| {
                    params
                        .get(key)
                        .map(|v| pdf.resolve(v)?.integer())
                        .transpose()
                        .map(|v| v.unwrap_or(default))
                };
                predictor = integer(b"Predictor", 1)?;
                if !matches!(predictor, 1 | 2 | 10..=15) {
                    return Err(unsupported("Unknown PDF image predictor"));
                }
                if predictor != 1
                    && (integer(b"Colors", 1)? != components
                        || integer(b"BitsPerComponent", 8)? != bits
                        || integer(b"Columns", 1)? != size[0] as usize)
                {
                    return Err(unsupported(
                        "PDF predictor layout differs from the image sample layout",
                    ));
                }
            }
        }
        Ok(Self {
            size,
            components,
            bits,
            invert,
            predictor,
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
    ) -> Result<(), Error> {
        let samples = self.size[0] as usize * self.components;
        let row = (samples * self.bits).div_ceil(8);
        let png = self.predictor >= 10;
        let stride = row + usize::from(png);
        let expected = stride * self.size[1] as usize;
        if expected > *remaining {
            return Err(limit("PDF decoded stream budget exceeded"));
        }
        let mut data = pdf.inflated_stream(&Value::Ref(id), expected, control)?;
        if data.len() != expected {
            return Err(invalid(
                "PDF image stream length disagrees with its dimensions",
            ));
        }
        *remaining -= expected;
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
                for (channel, last) in last[..self.components].iter_mut().enumerate() {
                    let offset = (x * self.components + channel) * self.bits;
                    let mut code = (row[offset / 8] >> (8 - self.bits - offset % 8)) & maximum;
                    if self.predictor == 2 {
                        code = code.wrapping_add(*last) & maximum;
                        *last = code;
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
            }
            previous = row;
        }
        Ok(())
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
            let plane = Plane::describe(pdf, d)?;
            let [width, height] = plane.size;
            let count = u64::from(width) * u64::from(height);
            if self.pixels + count > assets::MAX_ASSET_PIXELS {
                return Err(limit("PDF document image pixel budget exceeded"));
            }
            let mut rgba = vec![255; count as usize * 4];
            plane.unpack(pdf, id, remaining, control, &mut rgba, false)?;
            let mut source = json!({"object":id.0,"generation":id.1,"components":plane.components,"bits_per_component":plane.bits});
            if let Some(v) = d.get(b"SMask".as_slice()) {
                let mask_id = reference(v)?;
                let mut decode_mask = || {
                    let d = pdf.stream_dict(mask_id)?;
                    let mask = Plane::describe(pdf, d)?;
                    if mask.components != 1
                        || mask.size != plane.size
                        || d.contains_key(b"SMask".as_slice())
                    {
                        return Err(unsupported(
                            "PDF image soft mask requires a matching grayscale plane without another mask",
                        ));
                    }
                    mask.unpack(pdf, mask_id, remaining, control, &mut rgba, true)
                };
                decode_mask().map_err(|e| located(e, page, mask_id, None))?;
                source["soft_mask"] = json!({"object":mask_id.0,"generation":mask_id.1});
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
