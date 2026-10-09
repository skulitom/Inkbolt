//! Frozen typed sources and bounded raw block access for local native edits.
use crate::sample_store::{Candidate, Region, Spec, TILE_EDGE};
use crate::samples::{Channels, Depth};
use crate::{Error, assets, control::Control, model::Content, render};
use std::{collections::BTreeMap, path::Path};

pub(crate) trait Budget {
    fn charge(&mut self, pixels: usize) -> Result<(), Error>;
    fn control(&self) -> &Control;
}

pub(crate) fn replacement_memory(content: &Content, region: Region) -> u64 {
    let Content::StoredSamples { grid } = content else {
        return 0;
    };
    let columns = (region.x + region.width).div_ceil(TILE_EDGE) - region.x / TILE_EDGE;
    let rows = (region.y + region.height).div_ceil(TILE_EDGE) - region.y / TILE_EDGE;
    columns as u64
        * rows as u64
        * TILE_EDGE as u64
        * TILE_EDGE as u64
        * grid.base.spec.depth.bytes() as u64
        * grid.base.spec.channels.count() as u64
}

pub(crate) fn memory(content: &Content) -> u64 {
    match content {
        Content::StoredSamples { grid } => grid.preparation_costs().1 * 8,
        Content::Samples { grid } => {
            grid.width as u64
                * grid.height as u64
                * grid.depth.bytes() as u64
                * grid.channels.count() as u64
                * 4
        }
        Content::Raster { width, height, .. } => *width as u64 * *height as u64 * 16,
        _ => 0,
    }
}

pub(crate) fn spec(content: &Content) -> Result<Spec, Error> {
    match content {
        Content::Raster { width, height, .. } => Ok(Spec {
            width: *width,
            height: *height,
            depth: Depth::U8,
            channels: Channels::Rgba,
            encoding: Default::default(),
        }),
        Content::Samples { grid } => Ok(Spec {
            width: grid.width,
            height: grid.height,
            depth: grid.depth,
            channels: grid.channels,
            encoding: grid.encoding,
        }),
        Content::StoredSamples { grid } => Ok(grid.base.spec),
        _ => Err(Error::new(
            "INVALID_OPERATION",
            "Pixel edits require raster, samples or stored_samples layers",
        )),
    }
}

#[derive(Clone)]
enum Data {
    Inline(Vec<u8>),
    Stored(Candidate),
}

#[derive(Clone)]
pub(crate) struct Pixels<'a> {
    pub spec: Spec,
    pub identity: String,
    pub identity_kind: &'static str,
    data: Data,
    root: Option<&'a Path>,
    cache: BTreeMap<usize, (u64, Vec<u8>)>,
    clock: u64,
}

impl<'a> Pixels<'a> {
    pub fn new(
        content: &Content,
        root: Option<&'a Path>,
        encoding_error: &'static str,
        work: &mut impl Budget,
    ) -> Result<Self, Error> {
        let spec = spec(content)?;
        let (data, legacy) = match content {
            Content::Raster { rgba_hex, .. } => (Some(render::unhex(rgba_hex)), true),
            Content::Samples { grid } => (Some(render::unhex(&grid.data_hex)), false),
            Content::StoredSamples { .. } => (None, false),
            _ => unreachable!(),
        };
        if spec.encoding != crate::hdr::Encoding::EncodedSrgb {
            return Err(Error::new(
                encoding_error,
                "Normalized pixel editing requires explicit encoded sRGB samples; profiled and linear sources need an explicit conversion first",
            ));
        }
        let (data, identity) = if let Some(bytes) = data {
            work.charge(spec.width as usize * spec.height as usize)?;
            let identity = if legacy {
                assets::identity(spec.width, spec.height, &bytes)
            } else {
                Candidate::from_bytes(spec, &bytes, work.control())?
                    .manifest()
                    .sha256
                    .clone()
            };
            (Data::Inline(bytes), identity)
        } else {
            let Content::StoredSamples { grid } = content else {
                unreachable!()
            };
            work.charge(grid.preparation_costs().0 as usize)?;
            let candidate = grid.prepare(root, work.control())?;
            let identity = candidate.manifest().sha256.clone();
            (Data::Stored(candidate), identity)
        };
        Ok(Self {
            spec,
            identity,
            identity_kind: if legacy {
                "rgba8_image"
            } else {
                "native_tile_manifest"
            },
            data,
            root,
            cache: BTreeMap::new(),
            clock: 0,
        })
    }

    pub fn stride(&self) -> usize {
        self.spec.depth.bytes() * self.spec.channels.count()
    }

    pub fn raw(&mut self, x: usize, y: usize, work: &mut impl Budget) -> Result<[u8; 16], Error> {
        let stride = self.stride();
        let mut result = [0; 16];
        let bytes = match &self.data {
            Data::Inline(bytes) => {
                let at = (y * self.spec.width as usize + x) * stride;
                &bytes[at..at + stride]
            }
            Data::Stored(candidate) => {
                let edge = TILE_EDGE as usize;
                let columns = self.spec.width.div_ceil(TILE_EDGE) as usize;
                let index = y / edge * columns + x / edge;
                let x0 = x / edge * edge;
                let y0 = y / edge * edge;
                let width = (self.spec.width as usize - x0).min(edge);
                let height = (self.spec.height as usize - y0).min(edge);
                self.clock += 1;
                if !self.cache.contains_key(&index) {
                    work.charge(width * height)?;
                    if self.cache.len() == 16 {
                        let oldest = *self
                            .cache
                            .iter()
                            .min_by_key(|(_, (used, _))| used)
                            .unwrap()
                            .0;
                        self.cache.remove(&oldest);
                    }
                    let bytes = candidate.read_region(
                        self.root,
                        Region {
                            x: x0 as u32,
                            y: y0 as u32,
                            width: width as u32,
                            height: height as u32,
                        },
                        work.control(),
                    )?;
                    self.cache.insert(index, (self.clock, bytes));
                }
                let (used, bytes) = self.cache.get_mut(&index).unwrap();
                *used = self.clock;
                let at = ((y - y0) * width + x - x0) * stride;
                &bytes[at..at + stride]
            }
        };
        result[..stride].copy_from_slice(bytes);
        Ok(result)
    }

    pub fn sample(
        &mut self,
        x: usize,
        y: usize,
        work: &mut impl Budget,
    ) -> Result<[f64; 4], Error> {
        let raw = self.raw(x, y, work)?;
        Ok(premultiplied(&raw, self.spec))
    }

    /// Return a complete pure snapshot recipe, never unpublished block names.
    pub fn replace(
        &self,
        content: &Content,
        region: Region,
        bytes: &[u8],
        work: &mut impl Budget,
    ) -> Result<(Content, String), Error> {
        let mut content = content.clone();
        let identity = match &self.data {
            Data::Inline(original) => {
                let stride = self.stride();
                let mut output = original.clone();
                for y in 0..region.height as usize {
                    work.control().check()?;
                    let at = ((region.y as usize + y) * self.spec.width as usize
                        + region.x as usize)
                        * stride;
                    let start = y * region.width as usize * stride;
                    let len = region.width as usize * stride;
                    output[at..at + len].copy_from_slice(&bytes[start..start + len]);
                }
                match &mut content {
                    Content::Raster { rgba_hex, .. } => {
                        *rgba_hex = render::hex(&output);
                        assets::identity(self.spec.width, self.spec.height, &output)
                    }
                    Content::Samples { grid } => {
                        grid.data_hex = render::hex(&output);
                        Candidate::from_bytes(self.spec, &output, work.control())?
                            .manifest()
                            .sha256
                            .clone()
                    }
                    _ => unreachable!(),
                }
            }
            Data::Stored(before) => {
                let Content::StoredSamples { grid } = &mut content else {
                    unreachable!()
                };
                // Replacement visits complete intersecting blocks, even when
                // their source pixels were already read through the local cache.
                let columns = (region.x + region.width).div_ceil(TILE_EDGE) - region.x / TILE_EDGE;
                let rows = (region.y + region.height).div_ceil(TILE_EDGE) - region.y / TILE_EDGE;
                work.charge((columns * rows * TILE_EDGE * TILE_EDGE) as usize)?;
                let after = before.replace(self.root, region, bytes, work.control())?;
                if before.manifest().sha256 != after.manifest().sha256 {
                    grid.patches.push(crate::stored_samples::Patch {
                        region,
                        data_hex: render::hex(bytes),
                    });
                    grid.validate()?;
                }
                after.manifest().sha256.clone()
            }
        };
        Ok((content, identity))
    }
}

pub(crate) fn premultiplied(raw: &[u8], spec: Spec) -> [f64; 4] {
    let mut values = [0.0; 4];
    for (v, bytes) in values.iter_mut().zip(raw.chunks_exact(spec.depth.bytes())) {
        *v = match spec.depth {
            Depth::U8 => bytes[0] as f64 / 255.0,
            Depth::U16 => u16::from_le_bytes(bytes.try_into().unwrap()) as f64 / 65535.0,
            Depth::F32 => f32::from_le_bytes(bytes.try_into().unwrap()) as f64,
        };
    }
    let [r, g, b, a] = match spec.channels {
        Channels::Rgba => values,
        Channels::GrayAlpha => [values[0], values[0], values[0], values[1]],
    };
    [r * a, g * a, b * a, a]
}

pub(crate) fn encode(value: [f64; 4], spec: Spec) -> Result<[u8; 16], Error> {
    let alpha = spec.depth.quantize(value[3].clamp(0.0, 1.0));
    let rgba = if alpha == 0.0 {
        [0.0; 4]
    } else {
        [
            value[0] / value[3],
            value[1] / value[3],
            value[2] / value[3],
            value[3],
        ]
    };
    let mut values = rgba;
    if spec.channels == Channels::GrayAlpha {
        if rgba[0] != rgba[1] || rgba[1] != rgba[2] {
            return Err(Error::new(
                "GRAYSCALE_CONVERSION_REQUIRED",
                "A chromatic pixel edit cannot be stored as gray_alpha; convert the target explicitly first",
            ));
        }
        values = [rgba[0], rgba[3], 0.0, 0.0];
    }
    let mut result = [0; 16];
    for (bytes, value) in result.chunks_exact_mut(spec.depth.bytes()).zip(values) {
        let value = value.clamp(0.0, 1.0);
        match spec.depth {
            Depth::U8 => bytes[0] = (value * 255.0).round() as u8,
            Depth::U16 => bytes.copy_from_slice(&((value * 65535.0).round() as u16).to_le_bytes()),
            Depth::F32 => bytes.copy_from_slice(&(value as f32).to_le_bytes()),
        }
    }
    Ok(result)
}
