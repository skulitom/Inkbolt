//! Authored scalar planes retain their own bounds and controls.
use super::{binary::*, *};

pub(super) struct Record {
    pub bounds: [i32; 4],
    pub width: usize,
    pub height: usize,
    outside: u8,
    linked: bool,
    enabled: bool,
    density: u8,
}
impl Record {
    pub fn read(mut input: Reader<'_>, version: Version) -> Result<Option<Self>, Error> {
        if input.left() == 0 {
            return Ok(None);
        }
        let length = input.left();
        if length < 20 || !length.is_multiple_of(2) {
            return Err(malformed());
        }
        let bounds = [
            input.signed()?,
            input.signed()?,
            input.signed()?,
            input.signed()?,
        ];
        let width = bounds[3] as i64 - bounds[1] as i64;
        let height = bounds[2] as i64 - bounds[0] as i64;
        if width < 0 || height < 0 || bounds.iter().any(|v| v.unsigned_abs() > 32768) {
            return Err(unsupported(
                "Mask bounds exceed the supported coordinate range",
            ));
        }
        if width != 0 || height != 0 {
            size(width as u32, height as u32, MAX_STORED_PIXELS, version)?;
        }
        let outside = input.byte()?;
        if outside != 0 && outside != 255 {
            return Err(unsupported("Mask outside value must be black or white"));
        }
        let flags = input.byte()?;
        if flags & !19 != 0 {
            return Err(unsupported(
                "Inverted, derived or unknown mask flags require an explicit mapping",
            ));
        }
        let mut density = 255;
        if flags & 16 != 0 {
            let parameters = input.byte()?;
            if parameters & !3 != 0 {
                return Err(unsupported(
                    "Vector-mask or unknown mask parameters require an explicit mapping",
                ));
            }
            if parameters & 1 != 0 {
                density = input.byte()?;
            }
            if parameters & 2 != 0 {
                let feather = f64::from_be_bytes(input.take(8)?.try_into().unwrap());
                if !feather.is_finite() || feather < 0.0 {
                    return Err(malformed());
                }
                if feather != 0.0 {
                    return Err(unsupported(
                        "Native mask feather is distinct from the engine triangular kernel and cannot be approximated implicitly",
                    ));
                }
            }
        }
        if input.left() >= 18 {
            return Err(unsupported(
                "Combined real and authored mask records require separate retained sources",
            ));
        }
        input.zero_padding(2)?;
        Ok(Some(Self {
            bounds,
            width: width as usize,
            height: height as usize,
            outside,
            linked: flags & 1 == 0,
            enabled: flags & 2 == 0,
            density,
        }))
    }
    pub fn pixels(&self) -> usize {
        self.width * self.height
    }
    pub fn document_mask(&self, bytes: &[u8], origin: [i32; 2]) -> Value {
        let x = self.bounds[1] as f64 - if self.linked { origin[0] as f64 } else { 0.0 };
        let y = self.bounds[0] as f64 - if self.linked { origin[1] as f64 } else { 0.0 };
        json!({"constant":self.width==0&&self.height==0,"width":self.width,"height":self.height,"gray_hex":crate::render::hex(bytes),"transform":[1,0,0,1,x,y],"linked":self.linked,"enabled":self.enabled,"clip":self.outside==0,"invert":false,"density":self.density as f64/255.0,"feather":0,"sampling":"nearest"})
    }
}

pub(super) struct Encoded {
    pub metadata: Vec<u8>,
    pub channel: Vec<u8>,
    pub receipt: Value,
}
pub(super) fn encode_mask(
    mask: &crate::masks::Mask,
    world: Matrix,
    version: Version,
    compression: Compression,
) -> Result<Encoded, Error> {
    if mask.invert || mask.feather != 0 || mask.sampling != assets::Sampling::Nearest {
        return Err(unsupported(
            "Layered masks require authored nearest gray8 samples without implicit inversion or feather conversion",
        ));
    }
    let [a, b, c, d, x, y] = mask.world_transform(world);
    if !(-32768.0..=32768.0).contains(&x) || !(-32768.0..=32768.0).contains(&y) {
        return Err(limit("Native mask placement exceeds the coordinate range"));
    }
    if [a, b, c, d] != [1.0, 0.0, 0.0, 1.0] || x.fract() != 0.0 || y.fract() != 0.0 {
        return Err(unsupported(
            "Native mask samples require integer translation without resampling",
        ));
    }
    if !mask.constant {
        size(mask.width, mask.height, MAX_STORED_PIXELS, version)?;
    }
    let bounds = [
        y as i64,
        x as i64,
        y as i64 + mask.height as i64,
        x as i64 + mask.width as i64,
    ];
    if bounds.iter().any(|v| !(-32768..=32768).contains(v)) {
        return Err(limit("Native mask bounds exceed the coordinate range"));
    }
    let density = (mask.density * 255.0).round() as u8;
    if density as f64 / 255.0 != mask.density {
        return Err(unsupported(
            "Native mask density must be an exact byte fraction",
        ));
    }
    let outside = if mask.clip { 0 } else { 255 };
    let mut metadata = Vec::new();
    for v in bounds {
        metadata.extend((v as i32).to_be_bytes());
    }
    metadata.push(outside);
    metadata.push(
        u8::from(!mask.linked)
            | if mask.enabled { 0 } else { 2 }
            | if density == 255 { 0 } else { 16 },
    );
    if density != 255 {
        metadata.extend([1, density]);
    } else {
        metadata.extend([0, 0]);
    }
    let samples = crate::render::unhex(&mask.gray_hex);
    let channel = if mask.constant {
        vec![0, 0]
    } else {
        encode(&samples, mask.width as usize, compression, version)
    };
    Ok(Encoded {
        metadata,
        channel,
        receipt: json!({"bounds":bounds,"constant":mask.constant,"gray_sha256":assets::sha256(&samples),"linked":mask.linked,"enabled":mask.enabled,"outside":outside,"density":density}),
    })
}
