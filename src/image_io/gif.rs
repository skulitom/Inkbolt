//! Original bounded GIF block reader, LZW expansion and exact-palette writer.
use super::*;
use crate::{control::Control, sequences::Delay};
use std::collections::BTreeMap;

pub const META: &[u8] = b"Inkbolt metadata v1\n";
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Background {
    #[default]
    Transparent,
    LogicalScreen,
}
pub(crate) struct Frame {
    pub rgba: Vec<u8>,
    pub delay: Delay,
}
pub(crate) struct Animation {
    pub width: u32,
    pub height: u32,
    pub plays: u32,
    pub frames: Vec<Frame>,
    pub metadata: Option<Value>,
}
struct Reader<'a> {
    bytes: &'a [u8],
    at: usize,
}
impl<'a> Reader<'a> {
    fn take(&mut self, n: usize) -> Result<&'a [u8], Error> {
        let out = self
            .bytes
            .get(self.at..self.at.checked_add(n).ok_or_else(malformed)?)
            .ok_or_else(malformed)?;
        self.at += n;
        Ok(out)
    }
    fn byte(&mut self) -> Result<u8, Error> {
        Ok(self.take(1)?[0])
    }
    fn word(&mut self) -> Result<u16, Error> {
        Ok(u16::from_le_bytes(self.take(2)?.try_into().unwrap()))
    }
    fn blocks(&mut self) -> Result<Vec<u8>, Error> {
        let mut result = vec![];
        loop {
            let n = usize::from(self.byte()?);
            if n == 0 {
                return Ok(result);
            }
            result.extend_from_slice(self.take(n)?);
        }
    }
    fn palette(&mut self, packed: u8) -> Result<Vec<[u8; 3]>, Error> {
        if packed & 128 == 0 {
            return Ok(vec![]);
        }
        Ok(self
            .take(3 * (2usize << (packed & 7)))?
            .as_chunks::<3>()
            .0
            .to_vec())
    }
}

fn expand(data: &[u8], minimum: u8, count: usize, control: &Control) -> Result<Vec<u8>, Error> {
    if !(2..=8).contains(&minimum) {
        return Err(malformed());
    }
    let clear = 1usize << minimum;
    let end = clear + 1;
    let mut table: Vec<Vec<u8>> = vec![vec![]; 4096];
    for (i, row) in table.iter_mut().enumerate().take(clear) {
        row.push(i as u8);
    }
    let mut next = end + 1;
    let mut width = usize::from(minimum) + 1;
    let mut bit = 0usize;
    let mut previous: Option<usize> = None;
    let mut result = Vec::with_capacity(count);
    let mut initialized = false;
    let mut codes = 0usize;
    loop {
        if codes.is_multiple_of(4096) {
            control.check()?;
        }
        codes += 1;
        if bit + width > data.len() * 8 {
            return Err(malformed());
        }
        let mut code = 0;
        for i in 0..width {
            code |= usize::from((data[(bit + i) / 8] >> ((bit + i) % 8)) & 1) << i;
        }
        bit += width;
        if code == clear {
            next = end + 1;
            width = usize::from(minimum) + 1;
            previous = None;
            initialized = true;
            continue;
        }
        if !initialized {
            return Err(malformed());
        }
        if code == end {
            if result.len() != count || bit.div_ceil(8) != data.len() {
                return Err(malformed());
            }
            return Ok(result);
        }
        let value = if code < clear || code > end && code < next {
            table[code].clone()
        } else if code == next && next < 4096 {
            let mut p = table[previous.ok_or_else(malformed)?].clone();
            p.push(*p.first().ok_or_else(malformed)?);
            p
        } else {
            return Err(malformed());
        };
        if value.is_empty() || value.len() > count - result.len() {
            return Err(malformed());
        }
        result.extend_from_slice(&value);
        if let Some(p) = previous
            && next < 4096
        {
            let mut entry = table[p].clone();
            entry.push(value[0]);
            table[next] = entry;
            next += 1;
            if next == 1usize << width && width < 12 {
                width += 1;
            }
        }
        previous = Some(code);
    }
}

pub(crate) fn decode(
    bytes: &[u8],
    background: Background,
    control: &Control,
) -> Result<Animation, Error> {
    if bytes.len() > assets::MAX_IMPORT_BYTES as usize {
        return Err(limit("GIF exceeds input byte limit"));
    }
    let mut r = Reader { bytes, at: 0 };
    if !matches!(r.take(6)?, b"GIF87a" | b"GIF89a") {
        return Err(malformed());
    }
    let width = u32::from(r.word()?);
    let height = u32::from(r.word()?);
    let count = assets::dimensions(width, height)? as usize;
    let packed = r.byte()?;
    let bg = usize::from(r.byte()?);
    if r.byte()? != 0 {
        return Err(unsupported(
            "GIF requires square or unspecified pixel aspect ratio",
        ));
    }
    let global = r.palette(packed)?;
    if !global.is_empty() && bg >= global.len() {
        return Err(malformed());
    }
    let backdrop = match background {
        Background::Transparent => [0; 4],
        Background::LogicalScreen => {
            let p = global.get(bg).ok_or_else(malformed)?;
            [p[0], p[1], p[2], 255]
        }
    };
    let mut canvas = backdrop.repeat(count);
    let mut frames = vec![];
    let mut control_block: Option<(u8, u16, Option<u8>)> = None;
    let mut plays = 1;
    let mut loop_seen = false;
    let mut metadata = None;
    loop {
        control.check()?;
        match r.byte()? {
            0x3b => {
                if r.at != bytes.len() || frames.is_empty() || control_block.is_some() {
                    return Err(malformed());
                }
                return Ok(Animation {
                    width,
                    height,
                    plays,
                    frames,
                    metadata,
                });
            }
            0x21 => match r.byte()? {
                0xf9 => {
                    if control_block.is_some() || r.byte()? != 4 {
                        return Err(malformed());
                    }
                    let flags = r.byte()?;
                    let delay = r.word()?;
                    let alpha = r.byte()?;
                    if r.byte()? != 0 {
                        return Err(malformed());
                    }
                    if flags & 0xe2 != 0 || (flags >> 2) & 7 > 3 {
                        return Err(unsupported(
                            "GIF interactive timing, reserved controls and unknown disposal are unsupported",
                        ));
                    }
                    control_block =
                        Some(((flags >> 2) & 7, delay, (flags & 1 != 0).then_some(alpha)));
                }
                0xfe => {
                    let text = r.blocks()?;
                    if let Some(packet) = text.strip_prefix(META) {
                        if metadata.is_some() {
                            return Err(malformed());
                        }
                        metadata = Some(crate::metadata::read_packet(packet)?);
                    }
                }
                0xff => {
                    let n = usize::from(r.byte()?);
                    let name = r.take(n)?;
                    let data = r.blocks()?;
                    if name != b"NETSCAPE2.0" && name != b"ANIMEXTS1.0" {
                        return Err(unsupported(
                            "Unknown GIF application extension; no color/profile or animation semantics are silently ignored",
                        ));
                    }
                    if loop_seen || !frames.is_empty() || data.len() != 3 || data[0] != 1 {
                        return Err(malformed());
                    }
                    loop_seen = true;
                    let repeats = u16::from_le_bytes([data[1], data[2]]);
                    plays = if repeats == 0 {
                        0
                    } else {
                        u32::from(repeats) + 1
                    };
                }
                _ => {
                    return Err(unsupported(
                        "GIF plain text and unknown extension types require explicit support",
                    ));
                }
            },
            0x2c => {
                if frames.len() >= crate::sequences::MAX_FRAMES
                    || (frames.len() + 1) as u64 * count as u64 > crate::sequences::MAX_PIXELS
                {
                    return Err(limit("GIF exceeds frame or aggregate decoded pixel limits"));
                }
                let x = u32::from(r.word()?);
                let y = u32::from(r.word()?);
                let w = u32::from(r.word()?);
                let h = u32::from(r.word()?);
                let flags = r.byte()?;
                if w == 0 || h == 0 || x + w > width || y + h > height || flags & 0x18 != 0 {
                    return Err(malformed());
                }
                let local = r.palette(flags)?;
                let colors = if local.is_empty() { &global } else { &local };
                if colors.is_empty() {
                    return Err(malformed());
                }
                let (dispose, delay, alpha) = control_block.take().unwrap_or((0, 0, None));
                if alpha.is_some_and(|a| usize::from(a) >= colors.len()) {
                    return Err(malformed());
                }
                let minimum = r.byte()?;
                let compressed = r.blocks()?;
                let indices = expand(&compressed, minimum, w as usize * h as usize, control)?;
                let previous = (dispose == 3).then(|| canvas.clone());
                let rows: Vec<u32> = if flags & 64 == 0 {
                    (0..h).collect()
                } else {
                    [(0, 8), (4, 8), (2, 4), (1, 2)]
                        .into_iter()
                        .flat_map(|(start, step)| (start..h).step_by(step))
                        .collect()
                };
                for (row, yy) in rows.into_iter().enumerate() {
                    control.check()?;
                    for xx in 0..w as usize {
                        let index = indices[row * w as usize + xx];
                        let color = colors.get(usize::from(index)).ok_or_else(malformed)?;
                        if Some(index) == alpha {
                            continue;
                        }
                        let at = (((y + yy) * width + x) as usize + xx) * 4;
                        canvas[at..at + 4].copy_from_slice(&[color[0], color[1], color[2], 255]);
                    }
                }
                frames.push(Frame {
                    rgba: canvas.clone(),
                    delay: Delay {
                        numerator: delay,
                        denominator: 100,
                    },
                });
                if dispose == 2 {
                    for yy in y..y + h {
                        for xx in x..x + w {
                            let at = (yy * width + xx) as usize * 4;
                            canvas[at..at + 4].copy_from_slice(&backdrop);
                        }
                    }
                } else if let Some(previous) = previous {
                    canvas = previous;
                }
            }
            _ => return Err(malformed()),
        }
    }
}

fn blocks(out: &mut Vec<u8>, bytes: &[u8]) {
    for part in bytes.chunks(255) {
        out.push(part.len() as u8);
        out.extend_from_slice(part);
    }
    out.push(0);
}
// Literal-only LZW with explicit resets is deterministic and bounded. Full dictionary
// expansion above accepts externally compressed input, including deferred clears.
fn pack(indices: &[u8]) -> Vec<u8> {
    let mut out = Vec::new();
    let mut buffer = 0u32;
    let mut bits = 0;
    let mut emit = |code: u32| {
        buffer |= code << bits;
        bits += 9;
        while bits >= 8 {
            out.push(buffer as u8);
            buffer >>= 8;
            bits -= 8;
        }
    };
    for part in indices.chunks(128) {
        emit(256);
        for &v in part {
            emit(u32::from(v));
        }
    }
    emit(257);
    if bits != 0 {
        out.push(buffer as u8);
    }
    out
}
pub(crate) fn encode(
    animation: &Animation,
    metadata: Option<&str>,
    control: &Control,
) -> Result<Vec<u8>, Error> {
    let count = assets::dimensions(animation.width, animation.height)? as usize;
    if animation.frames.is_empty()
        || animation.frames.len() > crate::sequences::MAX_FRAMES
        || count as u64 * animation.frames.len() as u64 > crate::sequences::MAX_PIXELS
        || animation.plays > 65536
    {
        return Err(limit(
            "GIF exceeds frame, aggregate pixel or play-count limits",
        ));
    }
    let mut transparent = false;
    for frame in &animation.frames {
        if frame.rgba.len() != count * 4 {
            return Err(malformed());
        }
        for (i, p) in frame.rgba.as_chunks::<4>().0.iter().enumerate() {
            if i.is_multiple_of(4096) {
                control.check()?;
            }
            if p[3] != 0 && p[3] != 255 {
                return Err(Error::new(
                    "UNSUPPORTED_GIF_ALPHA",
                    "GIF requires binary alpha; choose a full-alpha format or explicitly edit/matte the source",
                ));
            }
            transparent |= p[3] == 0;
        }
    }
    let mut out = b"GIF89a".to_vec();
    out.extend_from_slice(&(animation.width as u16).to_le_bytes());
    out.extend_from_slice(&(animation.height as u16).to_le_bytes());
    out.extend_from_slice(&[0x80, 0, 0, 0, 0, 0, 0, 0, 0]);
    if animation.plays != 1 {
        out.extend_from_slice(b"\x21\xff\x0bNETSCAPE2.0\x03\x01");
        out.extend_from_slice(
            &(if animation.plays == 0 {
                0
            } else {
                animation.plays - 1
            } as u16)
                .to_le_bytes(),
        );
        out.push(0);
    }
    if let Some(packet) = metadata {
        if packet.len() > crate::metadata::MAX_PACKET_BYTES {
            return Err(limit("GIF metadata exceeds envelope limit"));
        }
        out.extend_from_slice(&[0x21, 0xfe]);
        blocks(&mut out, &[META, packet.as_bytes()].concat());
    }
    for frame in &animation.frames {
        control.check()?;
        let denominator = u32::from(if frame.delay.denominator == 0 {
            100
        } else {
            frame.delay.denominator
        });
        let ticks = u32::from(frame.delay.numerator) * 100;
        if ticks % denominator != 0 || ticks / denominator > 65535 {
            return Err(Error::new(
                "UNSUPPORTED_GIF_TIMING",
                "GIF delays must be exactly representable in 0..65535 centiseconds",
            ));
        }
        let mut colors = BTreeMap::new();
        for (i, p) in frame.rgba.as_chunks::<4>().0.iter().enumerate() {
            if i.is_multiple_of(4096) {
                control.check()?;
            }
            if p[3] != 0 {
                colors.insert([p[0], p[1], p[2]], 0u8);
                if colors.len() + usize::from(transparent) > 256 {
                    return Err(Error::new(
                        "UNSUPPORTED_GIF_PALETTE",
                        "GIF palette exceeds 256 entries including transparency; no automatic color quantization is performed",
                    ));
                }
            }
        }
        if colors.len() + usize::from(transparent) > 256 {
            return Err(Error::new(
                "UNSUPPORTED_GIF_PALETTE",
                "GIF palette exceeds 256 entries including transparency; no automatic color quantization is performed",
            ));
        }
        let entries = (colors.len() + usize::from(transparent))
            .max(2)
            .next_power_of_two();
        let mut palette = vec![0; entries * 3];
        for (i, (color, index)) in colors.iter_mut().enumerate() {
            let at = i + usize::from(transparent);
            *index = at as u8;
            palette[at * 3..at * 3 + 3].copy_from_slice(color);
        }
        let indices: Vec<u8> = frame
            .rgba
            .as_chunks::<4>()
            .0
            .iter()
            .map(|p| {
                if p[3] == 0 {
                    0
                } else {
                    colors[&[p[0], p[1], p[2]]]
                }
            })
            .collect();
        out.extend_from_slice(&[0x21, 0xf9, 4, 8 + u8::from(transparent)]);
        out.extend_from_slice(&((ticks / denominator) as u16).to_le_bytes());
        out.extend_from_slice(&[0, 0]);
        out.extend_from_slice(&[0x2c, 0, 0, 0, 0]);
        out.extend_from_slice(&(animation.width as u16).to_le_bytes());
        out.extend_from_slice(&(animation.height as u16).to_le_bytes());
        out.push(128 + (entries.trailing_zeros() as u8 - 1));
        out.extend_from_slice(&palette);
        out.push(8);
        blocks(&mut out, &pack(&indices));
        if out.len() + 1 > crate::publish::MAX_OUTPUT_BYTES {
            return Err(limit("GIF exceeds output byte limit"));
        }
    }
    out.push(0x3b);
    Ok(out)
}

pub(crate) fn still(
    bytes: &[u8],
    policy: ColorPolicy,
    declared: Option<&crate::profiles::Profile>,
) -> Result<Decoded, Error> {
    let mut animation = decode(bytes, Background::Transparent, &Control::default())?;
    if animation.frames.len() != 1 {
        return Err(unsupported(
            "Animated GIF requires sequence.import; still import never discards frames",
        ));
    }
    let frame = animation.frames.pop().unwrap();
    let mut result = super::legacy::finish(
        Pixels {
            width: animation.width,
            height: animation.height,
            rgba: frame.rgba,
        },
        "gif",
        policy,
        declared,
        vec![
            "GIF imports exact palette colors and binary alpha over a transparent initial/disposal backdrop. Still import omits single-frame delay/play count; sequence.import retains timing and allows a logical-screen background policy. Unknown application extensions fail explicitly; unrecognized comments remain only in source identity.",
        ],
    )?;
    result.metadata = animation.metadata;
    Ok(result)
}
