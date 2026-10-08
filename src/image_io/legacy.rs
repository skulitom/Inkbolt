//! Original bounded BMP and TGA framing and pixel transport.
use super::*;

fn word(bytes: &[u8], at: usize) -> Result<u16, Error> {
    Ok(u16::from_le_bytes(
        bytes
            .get(at..at + 2)
            .ok_or_else(malformed)?
            .try_into()
            .unwrap(),
    ))
}
fn long(bytes: &[u8], at: usize) -> Result<u32, Error> {
    Ok(u32::from_le_bytes(
        bytes
            .get(at..at + 4)
            .ok_or_else(malformed)?
            .try_into()
            .unwrap(),
    ))
}
pub(super) fn finish(
    mut pixels: Pixels,
    format: &'static str,
    policy: ColorPolicy,
    declared: Option<&crate::profiles::Profile>,
    losses: Vec<&'static str>,
) -> Result<Decoded, Error> {
    let interpretation = if declared.is_some() {
        Interpretation::ConvertedSrgb
    } else {
        assume(policy)?
    };
    let source_profile_sha256 = crate::profiles::import(&mut pixels.rgba, None, declared, policy)?;
    Ok(Decoded {
        metadata: None,
        source_profile_sha256,
        pixels,
        interpretation,
        format,
        losses,
    })
}

pub(super) fn bmp(
    bytes: &[u8],
    policy: ColorPolicy,
    declared: Option<&crate::profiles::Profile>,
) -> Result<Decoded, Error> {
    if bytes.len() < 54
        || !bytes.starts_with(b"BM")
        || long(bytes, 2)? as usize != bytes.len()
        || long(bytes, 6)? != 0
        || word(bytes, 26)? != 1
    {
        return Err(malformed());
    }
    if long(bytes, 14)? != 40
        || long(bytes, 30)? != 0
        || ![24, 32].contains(&word(bytes, 28)?)
        || long(bytes, 46)? != 0
        || long(bytes, 50)? != 0
    {
        return Err(unsupported(
            "BMP import requires a 40-byte header with uncompressed 24-bit RGB or 32-bit RGB plus unused padding; palette, bitfields and profile headers are unsupported",
        ));
    }
    let width = long(bytes, 18)? as i32;
    let signed_height = long(bytes, 22)? as i32;
    if width <= 0 || signed_height == i32::MIN {
        return Err(malformed());
    }
    let height = signed_height.unsigned_abs();
    let count = assets::dimensions(width as u32, height)? as usize;
    let components = usize::from(word(bytes, 28)? / 8);
    let stride = (width as usize * components).div_ceil(4) * 4;
    let offset = long(bytes, 10)? as usize;
    let size = stride * height as usize;
    if offset != 54 || offset + size != bytes.len() || ![0, size as u32].contains(&long(bytes, 34)?)
    {
        return Err(malformed());
    }
    let mut rgba = vec![0; count * 4];
    for y in 0..height as usize {
        let row = if signed_height > 0 {
            height as usize - 1 - y
        } else {
            y
        };
        for x in 0..width as usize {
            let at = offset + row * stride + x * components;
            let to = (y * width as usize + x) * 4;
            rgba[to..to + 4].copy_from_slice(&[bytes[at + 2], bytes[at + 1], bytes[at], 255]);
        }
    }
    finish(
        Pixels {
            width: width as u32,
            height,
            rgba,
        },
        "bmp",
        policy,
        declared,
        vec![
            "BMP BI_RGB transports RGB without alpha. The fourth byte in 32-bit input is unused padding, not transparency. Source density and descriptions do not change placement; original source identity is retained.",
        ],
    )
}

pub(super) fn is_tga(bytes: &[u8]) -> bool {
    bytes.ends_with(b"TRUEVISION-XFILE.\0")
        || bytes.len() >= 18 && bytes[1] == 0 && [2, 3, 10, 11].contains(&bytes[2])
}

pub(super) fn tga(
    bytes: &[u8],
    policy: ColorPolicy,
    declared: Option<&crate::profiles::Profile>,
) -> Result<Decoded, Error> {
    if bytes.len() < 18 {
        return Err(malformed());
    }
    if bytes[1] != 0
        || bytes[3..8] != [0; 5]
        || ![2, 3, 10, 11].contains(&bytes[2])
        || bytes[17] & 0xc0 != 0
    {
        return Err(unsupported(
            "TGA requires noninterleaved truecolor or grayscale pixels without a color map",
        ));
    }
    let gray = bytes[2] == 3 || bytes[2] == 11;
    let compressed = bytes[2] >= 10;
    let components = match (gray, bytes[16]) {
        (false, 24) => 3,
        (false, 32) => 4,
        (true, 8) => 1,
        (true, 16) => 2,
        _ => {
            return Err(unsupported(
                "TGA requires RGB24, RGBA32, gray8 or gray-alpha16",
            ));
        }
    };
    let bits = bytes[17] & 15;
    if ![0, 8].contains(&bits) || bits == 8 && ![2, 4].contains(&components) {
        return Err(unsupported(
            "TGA alpha requires zero or eight explicitly declared attribute bits",
        ));
    }
    let width = u32::from(word(bytes, 12)?);
    let height = u32::from(word(bytes, 14)?);
    let count = assets::dimensions(width, height)? as usize;
    let mut end = bytes.len();
    let mut alpha_type = if bits == 8 { 3 } else { 0 };
    if bytes.ends_with(b"TRUEVISION-XFILE.\0") {
        if end < 44 {
            return Err(malformed());
        }
        end -= 26;
        let extension = long(bytes, end)? as usize;
        if long(bytes, end + 4)? != 0 {
            return Err(unsupported(
                "TGA developer records require a separately supported metadata dialect",
            ));
        }
        if extension != 0 {
            if extension < 18 + usize::from(bytes[0])
                || extension + 495 != end
                || word(bytes, extension)? != 495
            {
                return Err(malformed());
            }
            // Reject color transforms and auxiliary tables rather than ignore their semantics.
            if bytes[extension + 470..extension + 494]
                .iter()
                .any(|v| *v != 0)
            {
                return Err(unsupported(
                    "TGA aspect, gamma, color tables, thumbnails and scanline tables require explicit support",
                ));
            }
            alpha_type = bytes[extension + 494];
            if alpha_type > 4 || alpha_type >= 2 && bits != 8 {
                return Err(unsupported(
                    "TGA extension alpha semantics conflict with its image descriptor",
                ));
            }
            end = extension;
        }
    }
    let mut at = 18 + usize::from(bytes[0]);
    if at > end {
        return Err(malformed());
    }
    let mut rgba = vec![0; count * 4];
    let mut written = 0;
    while written < count {
        let packet = if compressed {
            let v = *bytes.get(at).filter(|_| at < end).ok_or_else(malformed)?;
            at += 1;
            v
        } else {
            0
        };
        let n = if compressed {
            usize::from(packet & 127) + 1
        } else {
            count
        };
        let repeated = compressed && packet & 128 != 0;
        let consumed = if repeated { components } else { n * components };
        if n > count - written || at + consumed > end {
            return Err(malformed());
        }
        for i in 0..n {
            let p = at + if repeated { 0 } else { i * components };
            let mut pixel = if gray {
                [
                    bytes[p],
                    bytes[p],
                    bytes[p],
                    if components == 2 && alpha_type >= 2 {
                        bytes[p + 1]
                    } else {
                        255
                    },
                ]
            } else {
                [
                    bytes[p + 2],
                    bytes[p + 1],
                    bytes[p],
                    if components == 4 && alpha_type >= 2 {
                        bytes[p + 3]
                    } else {
                        255
                    },
                ]
            };
            if alpha_type == 4 {
                unassociate(&mut pixel)?;
            }
            let file_x = (written + i) % width as usize;
            let file_y = (written + i) / width as usize;
            let x = if bytes[17] & 16 != 0 {
                width as usize - 1 - file_x
            } else {
                file_x
            };
            let y = if bytes[17] & 32 == 0 {
                height as usize - 1 - file_y
            } else {
                file_y
            };
            let dest = (y * width as usize + x) * 4;
            rgba[dest..dest + 4].copy_from_slice(&pixel);
        }
        written += n;
        at += consumed;
    }
    if at != end {
        return Err(malformed());
    }
    finish(
        Pixels {
            width,
            height,
            rgba,
        },
        "tga",
        policy,
        declared,
        vec![
            "TGA pixel origins normalize to top-left; canvas placement remains explicit. Declared useful or retained alpha is preserved; undeclared or ignored attribute bytes are opaque. Premultiplied samples are unassociated with integer rounding. Descriptions and source coordinates are retained only through source identity.",
        ],
    )
}

pub(super) fn unassociate(pixel: &mut [u8; 4]) -> Result<(), Error> {
    let alpha = u32::from(pixel[3]);
    for value in &mut pixel[..3] {
        if u32::from(*value) > alpha {
            return Err(malformed());
        }
        *value = (u32::from(*value) * 255 + alpha / 2)
            .checked_div(alpha)
            .unwrap_or(0) as u8;
    }
    Ok(())
}

pub(super) fn encode(
    p: &crate::render::Rasterized,
    format: ExportFormat,
    ppi: f64,
) -> Result<Vec<u8>, Error> {
    assets::dimensions(p.width, p.height)?;
    if p.rgba.len() != p.width as usize * p.height as usize * 4 {
        return Err(malformed());
    }
    let bmp = matches!(format, ExportFormat::Bmp);
    let stride = if bmp {
        (p.width as usize * 3).div_ceil(4) * 4
    } else {
        p.width as usize * 4
    };
    let size = stride * p.height as usize;
    let total = size + if bmp { 54 } else { 18 + 495 + 26 };
    if total > crate::publish::MAX_OUTPUT_BYTES {
        return Err(limit("Encoded image exceeds output byte limit"));
    }
    let mut out = vec![0; total];
    if bmp {
        out[..2].copy_from_slice(b"BM");
        out[2..6].copy_from_slice(&(total as u32).to_le_bytes());
        out[10..14].copy_from_slice(&54u32.to_le_bytes());
        out[14..18].copy_from_slice(&40u32.to_le_bytes());
        out[18..22].copy_from_slice(&p.width.to_le_bytes());
        out[22..26].copy_from_slice(&(p.height as i32).to_le_bytes());
        out[26..28].copy_from_slice(&1u16.to_le_bytes());
        out[28..30].copy_from_slice(&24u16.to_le_bytes());
        out[34..38].copy_from_slice(&(size as u32).to_le_bytes());
        let density = (ppi / 0.0254).round() as i32;
        out[38..42].copy_from_slice(&density.to_le_bytes());
        out[42..46].copy_from_slice(&density.to_le_bytes());
    } else {
        out[2] = 2;
        out[12..14].copy_from_slice(&(p.width as u16).to_le_bytes());
        out[14..16].copy_from_slice(&(p.height as u16).to_le_bytes());
        out[16] = 32;
        out[17] = 40;
        let extension = 18 + size;
        out[extension..extension + 2].copy_from_slice(&495u16.to_le_bytes());
        out[extension + 494] = 3;
        out[total - 26..total - 22].copy_from_slice(&(extension as u32).to_le_bytes());
        out[total - 18..].copy_from_slice(b"TRUEVISION-XFILE.\0");
    }
    for y in 0..p.height as usize {
        let row = if bmp { p.height as usize - 1 - y } else { y };
        for x in 0..p.width as usize {
            let pixel = &p.rgba[(y * p.width as usize + x) * 4..][..4];
            if bmp && pixel[3] != 255 {
                return Err(Error::new(
                    "ALPHA_POLICY_REQUIRED",
                    "BMP24 requires opaque pixels or an explicit RGB matte",
                ));
            }
            let at = if bmp {
                54 + row * stride + x * 3
            } else {
                18 + row * stride + x * 4
            };
            out[at..at + 3].copy_from_slice(&[pixel[2], pixel[1], pixel[0]]);
            if !bmp {
                out[at + 3] = pixel[3];
            }
        }
    }
    Ok(out)
}
