//! Private pixel preparation; public pure candidates keep their memory contract.
use super::{
    malformed,
    source::{Budget, Scratch},
};
use crate::{
    Error, assets,
    control::Control,
    model::limit,
    sample_store::{
        Manifest, Publication, Region, Spec,
        publication::{self, Pending},
    },
    samples::Depth,
};
use std::{path::Path, sync::Arc};

pub(super) struct Builder {
    data: Data,
    covered: Option<Vec<u8>>,
    written: usize,
}

struct Data {
    spec: Spec,
    scratch: Scratch,
}

pub(super) struct Prepared {
    manifest: Manifest,
    data: Data,
}
impl Prepared {
    pub fn manifest(&self) -> &Manifest {
        &self.manifest
    }
    pub fn publish(mut self, root: &Path, control: &Control) -> Result<Publication, Error> {
        publication::publish(&self.manifest, &mut self.data, root, control)
    }
}

impl Pending for Data {
    fn contains(&self, _: &str) -> bool {
        true
    }
    fn load(
        &mut self,
        _: &str,
        spec: Spec,
        tile: Region,
        control: &Control,
    ) -> Result<Arc<[u8]>, Error> {
        if spec != self.spec {
            return Err(malformed());
        }
        let header = spec.header(tile.width, tile.height);
        let row_bytes = tile.width as usize * spec.stride();
        let mut blob = vec![0; header.len() + row_bytes * tile.height as usize];
        blob[..header.len()].copy_from_slice(&header);
        for (row, target) in blob[header.len()..].chunks_exact_mut(row_bytes).enumerate() {
            let offset = ((tile.y as u64 + row as u64) * spec.width as u64 + tile.x as u64)
                * spec.stride() as u64;
            self.scratch.read_at(offset, target, control)?;
        }
        spec.validate_region_bytes(tile, &blob[header.len()..])?;
        Ok(blob.into())
    }
}

impl Builder {
    pub fn new(
        spec: Spec,
        budget: &Budget,
        scattered: bool,
        control: &Control,
    ) -> Result<Self, Error> {
        Self::in_directory(spec, budget, scattered, &std::env::temp_dir(), control)
    }

    fn in_directory(
        spec: Spec,
        budget: &Budget,
        scattered: bool,
        directory: &Path,
        control: &Control,
    ) -> Result<Self, Error> {
        control.check()?;
        let bytes = spec.byte_len()?;
        if bytes > super::MAX_NATIVE_DECODED_BYTES {
            return Err(limit(
                "Native import exceeds its private pixel extent limit",
            ));
        }
        let mut scratch = Scratch::create(directory, budget.clone(), control)?;
        scratch.allocate(bytes as u64, control)?;
        Ok(Self {
            data: Data { spec, scratch },
            covered: scattered
                .then(|| vec![0; (spec.width as usize * spec.height as usize).div_ceil(8)]),
            written: 0,
        })
    }

    pub fn from_rows(
        spec: Spec,
        budget: &Budget,
        control: &Control,
        mut read_row: impl FnMut(u32, &mut [u8]) -> Result<(), Error>,
    ) -> Result<Prepared, Error> {
        let mut target = Self::new(spec, budget, false, control)?;
        let mut row = vec![0; spec.width as usize * spec.stride()];
        for y in 0..spec.height {
            control.check()?;
            read_row(y, &mut row)?;
            control.check()?;
            spec.validate_region_bytes(
                Region {
                    x: 0,
                    y,
                    width: spec.width,
                    height: 1,
                },
                &row,
            )?;
            target
                .data
                .scratch
                .write_at(y as u64 * row.len() as u64, &row, control)?;
        }
        target.finish(control)
    }

    /// Adam7 rows are disjoint samples; reassemble one native row at a time.
    pub fn row(
        &mut self,
        x: u32,
        y: u32,
        step: u32,
        bytes: &[u8],
        control: &Control,
    ) -> Result<(), Error> {
        control.check()?;
        let spec = self.data.spec;
        let stride = spec.stride();
        let count = bytes.len() / stride;
        if bytes.is_empty()
            || !bytes.len().is_multiple_of(stride)
            || step == 0
            || x >= spec.width
            || y >= spec.height
            || count > 1 + ((spec.width - 1 - x) / step) as usize
        {
            return Err(malformed());
        }
        spec.validate_region_bytes(
            Region {
                x: 0,
                y,
                width: count as u32,
                height: 1,
            },
            bytes,
        )?;
        let covered = self.covered.as_mut().ok_or_else(malformed)?;
        for i in 0..count {
            let pixel = y as usize * spec.width as usize + x as usize + i * step as usize;
            if covered[pixel / 8] & (1 << (pixel % 8)) != 0 {
                return Err(malformed());
            }
        }
        let mut row = vec![0; spec.width as usize * stride];
        let offset = y as u64 * row.len() as u64;
        self.data.scratch.read_at(offset, &mut row, control)?;
        for (i, sample) in bytes.chunks_exact(stride).enumerate() {
            let col = x as usize + i * step as usize;
            row[col * stride..(col + 1) * stride].copy_from_slice(sample);
        }
        self.data.scratch.write_at(offset, &row, control)?;
        for i in 0..count {
            let pixel = y as usize * spec.width as usize + x as usize + i * step as usize;
            covered[pixel / 8] |= 1 << (pixel % 8);
        }
        self.written += count;
        control.check()
    }

    /// TIFF planes/chunks follow a validated complete schedule. This operation
    /// preserves other components while assembling one row segment in memory.
    pub fn components(
        &mut self,
        region: Region,
        first: usize,
        channels: usize,
        native: &[u8],
        opaque_alpha: bool,
        control: &Control,
    ) -> Result<(), Error> {
        control.check()?;
        let spec = self.data.spec;
        let n = spec.channels.count();
        let unit = spec.depth.bytes();
        if region.height != 1
            || region.width == 0
            || region.x as u64 + region.width as u64 > spec.width as u64
            || region.y >= spec.height
            || channels == 0
            || first + channels > n
            || native.len() != region.width as usize * channels * unit
        {
            return Err(malformed());
        }
        let offset = (region.y as u64 * spec.width as u64 + region.x as u64) * spec.stride() as u64;
        if first == 0 && channels == n {
            return self.data.scratch.write_at(offset, native, control);
        }
        let mut row = vec![0; region.width as usize * spec.stride()];
        self.data.scratch.read_at(offset, &mut row, control)?;
        for (pixel, source) in row
            .chunks_exact_mut(spec.stride())
            .zip(native.chunks_exact(channels * unit))
        {
            pixel[first * unit..(first + channels) * unit].copy_from_slice(source);
            if opaque_alpha {
                let alpha = &mut pixel[(n - 1) * unit..];
                match spec.depth {
                    Depth::U8 => alpha.fill(255),
                    Depth::U16 => alpha.copy_from_slice(&u16::MAX.to_le_bytes()),
                    Depth::F32 => alpha.copy_from_slice(&1.0_f32.to_le_bytes()),
                }
            }
        }
        self.data.scratch.write_at(offset, &row, control)
    }

    pub fn finish(mut self, control: &Control) -> Result<Prepared, Error> {
        control.check()?;
        let spec = self.data.spec;
        if self.covered.is_some() && self.written != spec.width as usize * spec.height as usize {
            return Err(malformed());
        }
        drop(self.covered.take());
        let mut manifest = Manifest {
            version: 1,
            spec,
            tiles: Vec::with_capacity(spec.tile_count()),
            sha256: String::new(),
        };
        for index in 0..spec.tile_count() {
            let blob = self.data.load("", spec, spec.tile(index), control)?;
            manifest.tiles.push(assets::sha256(&blob));
        }
        manifest.sha256 = manifest.identity();
        manifest.validate()?;
        control.check()?;
        Ok(Prepared {
            manifest,
            data: self.data,
        })
    }
}

#[cfg(test)]
mod tests;
