//! Complete marker/entropy admission before allocating a decoded JPEG frame.
use super::{exif, malformed, unsupported};
use crate::{Error, control::Control, limits::sample_import as bounds, model::limit};
use std::{
    collections::BTreeSet,
    io::{BufRead, BufReader, Read, Seek},
};

pub(super) struct Plan {
    pub width: u32,
    pub height: u32,
    pub channels: usize,
    pub progressive: bool,
    pub exif: Option<exif::Metadata>,
    pub output_bytes: usize,
    pub estimated_working_bytes: u64,
    pub scans: usize,
    pub scan_work: u64,
    ids: BTreeSet<u8>,
    padded_samples: u64,
    rgb_components: bool,
}

fn frame(body: &[u8], progressive: bool, max_pixels: usize) -> Result<Plan, Error> {
    if body.len() < 6 {
        return Err(malformed());
    }
    if body[0] != 8 {
        return Err(unsupported("Native JPEG requires 8-bit samples"));
    }
    let height = u32::from(u16::from_be_bytes(body[1..3].try_into().unwrap()));
    let width = u32::from(u16::from_be_bytes(body[3..5].try_into().unwrap()));
    super::super::size(width, height, max_pixels)?;
    let channels = usize::from(body[5]);
    if !matches!(channels, 1 | 3) {
        return Err(unsupported(
            "Native JPEG requires grayscale or RGB components",
        ));
    }
    if body.len() != 6 + 3 * channels {
        return Err(malformed());
    }
    let rgb_components = channels == 3 && [body[6], body[9], body[12]] == *b"RGB";
    if channels == 3 && matches!([body[6], body[9], body[12]], [1, 34, 35] | [114, 103, 98]) {
        return Err(unsupported(
            "JPEG extended color transforms are unsupported",
        ));
    }
    let mut ids = BTreeSet::new();
    let mut sampling = Vec::new();
    for component in body[6..].as_chunks::<3>().0 {
        let (h, v) = (u64::from(component[1] >> 4), u64::from(component[1] & 15));
        if !ids.insert(component[0])
            || !(1..=4).contains(&h)
            || !(1..=4).contains(&v)
            || component[2] > 3
        {
            return Err(malformed());
        }
        sampling.push((h, v));
    }
    let max_h = sampling.iter().map(|c| c.0).max().unwrap();
    let max_v = sampling.iter().map(|c| c.1).max().unwrap();
    let across = u64::from(width).div_ceil(8 * max_h);
    let down = u64::from(height).div_ceil(8 * max_v);
    let row_samples: u64 = sampling.iter().map(|(h, v)| across * h * v * 64).sum();
    let padded_samples = row_samples * down;
    let output = u64::from(width) * u64::from(height) * channels as u64;
    // Conservative allowance for retained coefficients/planes, possible worker
    // results, two coefficient row sets, output and fixed auxiliary scratch.
    let working = padded_samples
        .checked_mul(4)
        .and_then(|n| n.checked_add(row_samples * 4))
        .and_then(|n| n.checked_add(output))
        .and_then(|n| n.checked_add(bounds::JPEG_AUXILIARY_BYTES))
        .ok_or_else(|| limit("JPEG decoder memory estimate exceeds bounds"))?;
    if output > bounds::MAX_JPEG_OUTPUT_BYTES as u64 || working > bounds::MAX_JPEG_WORKING_BYTES {
        return Err(limit("JPEG whole-frame decoder memory budget exceeded"));
    }
    Ok(Plan {
        width,
        height,
        channels,
        progressive,
        exif: None,
        output_bytes: output as usize,
        estimated_working_bytes: working,
        scans: 0,
        scan_work: 0,
        ids,
        padded_samples,
        rgb_components,
    })
}

pub(super) struct Framing<'a, R> {
    input: BufReader<R>,
    pub(super) position: u64,
    length: u64,
    control: &'a Control,
}
impl<'a, R: Read + Seek> Framing<'a, R> {
    pub(super) fn new(input: R, length: u64, control: &'a Control) -> Self {
        Self {
            input: BufReader::with_capacity(bounds::INPUT_BUFFER_BYTES, input),
            position: 0,
            length,
            control,
        }
    }
    fn read(&mut self, bytes: &mut [u8]) -> Result<(), Error> {
        self.control.check()?;
        let end = self
            .position
            .checked_add(bytes.len() as u64)
            .filter(|n| *n <= self.length)
            .ok_or_else(malformed)?;
        self.input.read_exact(bytes).map_err(|_| malformed())?;
        self.position = end;
        Ok(())
    }
    pub(super) fn byte(&mut self) -> Result<u8, Error> {
        let mut bytes = [0];
        self.read(&mut bytes)?;
        Ok(bytes[0])
    }
    pub(super) fn marker(&mut self) -> Result<u8, Error> {
        if self.byte()? != 255 {
            return Err(malformed());
        }
        let mut marker = self.byte()?;
        while marker == 255 {
            marker = self.byte()?;
        }
        Ok(marker)
    }
    pub(super) fn segment(&mut self) -> Result<Vec<u8>, Error> {
        let mut length = [0; 2];
        self.read(&mut length)?;
        let length = usize::from(u16::from_be_bytes(length));
        if length < 2 {
            return Err(malformed());
        }
        let mut body = vec![0; length - 2];
        self.read(&mut body)?;
        Ok(body)
    }
    fn entropy_marker(&mut self) -> Result<u8, Error> {
        loop {
            self.control.check()?;
            let bytes = self.input.fill_buf().map_err(|_| malformed())?;
            if bytes.is_empty() {
                return Err(malformed());
            }
            let offset = bytes.iter().position(|b| *b == 255);
            let consumed = offset.map_or(bytes.len(), |n| n + 1);
            self.position = self
                .position
                .checked_add(consumed as u64)
                .filter(|n| *n <= self.length)
                .ok_or_else(malformed)?;
            self.input.consume(consumed);
            if offset.is_none() {
                continue;
            }
            let mut marker = self.byte()?;
            while marker == 255 {
                marker = self.byte()?;
            }
            if matches!(marker, 0 | 0xd0..=0xd7) {
                continue;
            }
            return Ok(marker);
        }
    }
}

pub(super) fn inspect<R: Read + Seek>(
    input: R,
    length: u64,
    max_pixels: usize,
    control: &Control,
) -> Result<Plan, Error> {
    let mut reader = Framing {
        input: BufReader::with_capacity(bounds::INPUT_BUFFER_BYTES, input),
        position: 0,
        length,
        control,
    };
    if reader.marker()? != 0xd8 {
        return Err(malformed());
    }
    let mut plan: Option<Plan> = None;
    let mut metadata = None;
    let mut pending = None;
    let mut scanned = false;
    let mut jfif = false;
    loop {
        let marker = match pending.take() {
            Some(marker) => marker,
            None => reader.marker()?,
        };
        if marker == 0xd9 {
            let mut plan = plan.ok_or_else(malformed)?;
            if !scanned || reader.position != length {
                return Err(malformed());
            }
            if jfif && plan.rgb_components {
                return Err(unsupported(
                    "JPEG component identifiers conflict with JFIF color interpretation",
                ));
            }
            if let Some(meta) = &metadata {
                let meta: &exif::Metadata = meta;
                if meta
                    .samples
                    .is_some_and(|n| usize::from(n) != plan.channels)
                    || meta.photometric.is_some_and(|n| match plan.channels {
                        1 => n != 1,
                        _ => n != if plan.rgb_components { 2 } else { 6 },
                    })
                {
                    return Err(unsupported(
                        "JPEG EXIF component interpretation conflicts with the coded image",
                    ));
                }
            }
            plan.exif = metadata;
            return Ok(plan);
        }
        if matches!(marker, 0 | 0xd0..=0xd8) {
            return Err(malformed());
        }
        if marker == 1 {
            return Err(unsupported(
                "JPEG temporary arithmetic markers are unsupported",
            ));
        }
        let body = reader.segment()?;
        match marker {
            0xc0 | 0xc2 => {
                if plan.is_some() || scanned {
                    return Err(malformed());
                }
                plan = Some(frame(&body, marker == 0xc2, max_pixels)?);
            }
            0xda => {
                let plan = plan.as_mut().ok_or_else(malformed)?;
                let count = usize::from(*body.first().ok_or_else(malformed)?);
                if count == 0 || count > plan.channels || body.len() != 1 + count * 2 + 3 {
                    return Err(malformed());
                }
                let mut ids = BTreeSet::new();
                for component in body[1..1 + count * 2].as_chunks::<2>().0 {
                    if !plan.ids.contains(&component[0]) || !ids.insert(component[0]) {
                        return Err(malformed());
                    }
                }
                plan.scans += 1;
                plan.scan_work = plan
                    .scan_work
                    .checked_add(plan.padded_samples)
                    .ok_or_else(|| limit("JPEG scan work exceeds bounds"))?;
                if plan.scans > bounds::MAX_JPEG_SCANS
                    || plan.scan_work > bounds::MAX_JPEG_SCAN_WORK
                {
                    return Err(limit("JPEG scan count or cumulative work budget exceeded"));
                }
                scanned = true;
                pending = Some(reader.entropy_marker()?);
            }
            0xe1 if body.starts_with(b"Exif\0\0") => {
                if scanned || metadata.is_some() {
                    return Err(malformed());
                }
                metadata = Some(exif::parse(&body[6..])?);
            }
            0xe0 if body.starts_with(b"JFIF\0") => {
                if body.len() < 14
                    || body.len() != 14 + usize::from(body[12]) * usize::from(body[13]) * 3
                {
                    return Err(malformed());
                }
                jfif = true;
            }
            0xe0..=0xef => {
                return Err(unsupported(
                    "JPEG application metadata, profiles or color transforms are unsupported",
                ));
            }
            0xfe if scanned && body.starts_with(crate::metadata::JPEG_PREFIX) => {
                return Err(unsupported(
                    "Inkbolt JPEG metadata must precede the first scan",
                ));
            }
            0xc4 | 0xdb | 0xdd | 0xfe => {}
            _ => {
                return Err(unsupported(
                    "Native JPEG supports baseline and progressive Huffman-coded images",
                ));
            }
        }
    }
}
