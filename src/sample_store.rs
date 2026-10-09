//! Immutable native pixel blocks and pure copy-on-write candidates.
//!
//! This library primitive deliberately separates candidate construction/reads
//! from publication. A dry run can render a candidate without creating files.
//! Document/CLI integration must preserve that separation at its commit point.
use crate::{
    Error, assets,
    control::Control,
    hdr::Encoding,
    samples::{Channels, Depth},
};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    path::{Path, PathBuf},
    sync::{
        Arc,
        atomic::{AtomicU64, Ordering},
    },
};

pub const TILE_EDGE: u32 = 128;
pub const MAX_PIXELS: u64 = 16_777_216;
pub const MAX_TILES: usize = 2048;
pub const MAX_REGION_PIXELS: u64 = 65_536;
const HEADER_BYTES: usize = 20;
const MAGIC: &[u8; 8] = b"INKTILE1";
static NEXT_TEMP: AtomicU64 = AtomicU64::new(0);

#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Spec {
    pub width: u32,
    pub height: u32,
    pub depth: Depth,
    pub channels: Channels,
    pub encoding: Encoding,
}
impl Spec {
    pub fn validate(&self) -> Result<(), Error> {
        if !(1..=crate::model::MAX_DIMENSION).contains(&self.width)
            || !(1..=crate::model::MAX_DIMENSION).contains(&self.height)
            || self.width as u64 * self.height as u64 > MAX_PIXELS
            || self.tile_count() > MAX_TILES
        {
            return Err(crate::model::limit(
                "Native sample store dimensions, pixels or tile count exceed the bound",
            ));
        }
        if self.encoding == Encoding::LinearSrgb && self.depth != Depth::F32 {
            return Err(Error::new(
                "UNSUPPORTED_HDR_MODE",
                "Linear native sample blocks require binary32 depth",
            ));
        }
        Ok(())
    }
    pub fn byte_len(&self) -> Result<usize, Error> {
        self.validate()?;
        Ok(self.width as usize * self.height as usize * self.stride())
    }
    /// Validate an exact native replacement without opening a resource store.
    pub fn validate_region_bytes(&self, region: Region, bytes: &[u8]) -> Result<(), Error> {
        self.validate()?;
        region.validate(*self)?;
        if bytes.len() != region.width as usize * region.height as usize * self.stride() {
            return Err(invalid("Replacement bytes do not match the native region"));
        }
        validate_samples(bytes, *self)
    }
    fn stride(&self) -> usize {
        self.depth.bytes() * self.channels.count()
    }
    fn columns(&self) -> u32 {
        self.width.div_ceil(TILE_EDGE)
    }
    fn tile_count(&self) -> usize {
        self.columns() as usize * self.height.div_ceil(TILE_EDGE) as usize
    }
    fn tile(&self, index: usize) -> Region {
        let x = index as u32 % self.columns() * TILE_EDGE;
        let y = index as u32 / self.columns() * TILE_EDGE;
        Region {
            x,
            y,
            width: TILE_EDGE.min(self.width - x),
            height: TILE_EDGE.min(self.height - y),
        }
    }
    fn header(&self, width: u32, height: u32) -> [u8; HEADER_BYTES] {
        let mut result = [0; HEADER_BYTES];
        result[..8].copy_from_slice(MAGIC);
        result[8..12].copy_from_slice(&width.to_le_bytes());
        result[12..16].copy_from_slice(&height.to_le_bytes());
        result[16] = match self.depth {
            Depth::U8 => 1,
            Depth::U16 => 2,
            Depth::F32 => 4,
        };
        result[17] = self.channels.count() as u8;
        result[18] = match self.encoding {
            Encoding::EncodedSrgb => 0,
            Encoding::LinearSrgb => 1,
            Encoding::ProfiledRgb => 2,
        };
        result
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Region {
    pub x: u32,
    pub y: u32,
    pub width: u32,
    pub height: u32,
}
impl Region {
    fn validate(&self, spec: Spec) -> Result<(), Error> {
        if self.width == 0
            || self.height == 0
            || self.x as u64 + self.width as u64 > spec.width as u64
            || self.y as u64 + self.height as u64 > spec.height as u64
        {
            return Err(invalid(
                "Native sample region must be nonempty and within its grid",
            ));
        }
        if self.width as u64 * self.height as u64 > MAX_REGION_PIXELS {
            return Err(crate::model::limit(
                "Native sample read/replacement exceeds the region pixel bound",
            ));
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Manifest {
    pub version: u32,
    pub spec: Spec,
    /// Fixed row-major tile order. Pixel interpretation profiles remain separate
    /// document metadata and must also bind any decoded/rendered cache key.
    pub tiles: Vec<String>,
    pub sha256: String,
}
impl Manifest {
    fn identity(&self) -> String {
        let mut hash = Sha256::new();
        hash.update(b"INKGRID1");
        hash.update(self.spec.header(self.spec.width, self.spec.height));
        hash.update(TILE_EDGE.to_le_bytes());
        for tile in &self.tiles {
            hash.update(crate::render::unhex(tile));
        }
        crate::render::hex(&hash.finalize())
    }
    pub fn validate(&self) -> Result<(), Error> {
        self.spec.validate()?;
        if self.version != 1
            || self.tiles.len() != self.spec.tile_count()
            || !digest(&self.sha256)
            || self.tiles.iter().any(|value| !digest(value))
        {
            return Err(invalid(
                "Invalid native sample manifest version, tile count or canonical identity",
            ));
        }
        if self.identity() != self.sha256 {
            return Err(invalid(
                "Native sample manifest identity does not match its ordered tiles and type",
            ));
        }
        Ok(())
    }
}

/// Pending blobs are private immutable memory, shared by cheap candidate clones.
/// Only referenced blobs survive a replacement; retained older candidates remain
/// unchanged. Construction, reads and edits never create directories or files.
#[derive(Clone)]
pub struct Candidate {
    manifest: Manifest,
    pending: BTreeMap<String, Arc<[u8]>>,
}

#[derive(Debug, Serialize)]
pub struct Publication {
    pub manifest: Manifest,
    pub created_tiles: usize,
    pub existing_tiles: usize,
}

impl Candidate {
    pub fn from_manifest(manifest: Manifest) -> Result<Self, Error> {
        manifest.validate()?;
        Ok(Self {
            manifest,
            pending: BTreeMap::new(),
        })
    }
    pub fn manifest(&self) -> &Manifest {
        &self.manifest
    }
    pub fn pending_bytes(&self) -> usize {
        self.pending.values().map(|b| b.len()).sum()
    }
    pub fn pending_tiles(&self) -> usize {
        self.pending.len()
    }

    /// Input bytes are exact little-endian straight channels, never quantized.
    /// This initial constructor retains at most the validated whole native frame
    /// plus tile headers; it does not claim a streaming image decoder.
    pub fn from_bytes(spec: Spec, bytes: &[u8], control: &Control) -> Result<Self, Error> {
        control.check()?;
        if bytes.len() != spec.byte_len()? {
            return Err(invalid(
                "Native sample bytes do not match the declared grid",
            ));
        }
        let mut candidate = Self {
            manifest: Manifest {
                version: 1,
                spec,
                tiles: Vec::new(),
                sha256: String::new(),
            },
            pending: BTreeMap::new(),
        };
        for index in 0..spec.tile_count() {
            control.check()?;
            let tile = spec.tile(index);
            let mut blob = spec.header(tile.width, tile.height).to_vec();
            for y in tile.y..tile.y + tile.height {
                let offset = (y as usize * spec.width as usize + tile.x as usize) * spec.stride();
                blob.extend_from_slice(
                    &bytes[offset..offset + tile.width as usize * spec.stride()],
                );
            }
            validate_samples(&blob[HEADER_BYTES..], spec)?;
            let id = assets::sha256(&blob);
            candidate
                .pending
                .entry(id.clone())
                .or_insert_with(|| blob.into());
            candidate.manifest.tiles.push(id);
        }
        candidate.manifest.sha256 = candidate.manifest.identity();
        control.check()?;
        Ok(candidate)
    }

    fn load(&self, index: usize, root: Option<&Path>) -> Result<Arc<[u8]>, Error> {
        let id = &self.manifest.tiles[index];
        let spec = self.manifest.spec;
        let tile = spec.tile(index);
        // Only validated constructors can insert immutable pending bytes. The
        // private manifest/candidate cannot be changed through this public API.
        if let Some(bytes) = self.pending.get(id) {
            Ok(bytes.clone())
        } else {
            read_blob(root, id, spec, tile)
        }
    }

    /// Full dependency check, including tiles outside a later selected region.
    /// Does not retain all loaded bytes in memory or silently repair corruption.
    pub fn verify(&self, root: Option<&Path>, control: &Control) -> Result<(), Error> {
        control.check()?;
        check_root(root, control)?;
        self.manifest.validate()?;
        let mut seen = BTreeSet::new();
        for (index, id) in self.manifest.tiles.iter().enumerate() {
            control.check()?;
            let tile = self.manifest.spec.tile(index);
            if seen.insert((id, tile.width, tile.height)) {
                self.load(index, root)?;
            }
        }
        Ok(())
    }

    pub fn read_region(
        &self,
        root: Option<&Path>,
        region: Region,
        control: &Control,
    ) -> Result<Vec<u8>, Error> {
        control.check()?;
        check_root(root, control)?;
        self.manifest.validate()?;
        let spec = self.manifest.spec;
        region.validate(spec)?;
        let mut result = vec![0; region.width as usize * region.height as usize * spec.stride()];
        for index in intersecting(spec, region) {
            control.check()?;
            let tile = spec.tile(index);
            let bytes = self.load(index, root)?;
            let x0 = tile.x.max(region.x);
            let x1 = (tile.x + tile.width).min(region.x + region.width);
            for y in tile.y.max(region.y)..(tile.y + tile.height).min(region.y + region.height) {
                let src = ((y - tile.y) as usize * tile.width as usize + (x0 - tile.x) as usize)
                    * spec.stride()
                    + HEADER_BYTES;
                let dst = ((y - region.y) as usize * region.width as usize
                    + (x0 - region.x) as usize)
                    * spec.stride();
                let len = (x1 - x0) as usize * spec.stride();
                result[dst..dst + len].copy_from_slice(&bytes[src..src + len]);
            }
        }
        control.check()?;
        Ok(result)
    }

    /// Only intersecting tiles are read. Call verify before publication/use when
    /// all external dependencies must be proven, not just the selected region.
    pub fn replace(
        &self,
        root: Option<&Path>,
        region: Region,
        bytes: &[u8],
        control: &Control,
    ) -> Result<Self, Error> {
        control.check()?;
        check_root(root, control)?;
        self.manifest.validate()?;
        let spec = self.manifest.spec;
        spec.validate_region_bytes(region, bytes)?;
        let mut next = self.clone();
        for index in intersecting(spec, region) {
            control.check()?;
            let tile = spec.tile(index);
            let mut blob = self.load(index, root)?.to_vec();
            let x0 = tile.x.max(region.x);
            let x1 = (tile.x + tile.width).min(region.x + region.width);
            for y in tile.y.max(region.y)..(tile.y + tile.height).min(region.y + region.height) {
                let dst = ((y - tile.y) as usize * tile.width as usize + (x0 - tile.x) as usize)
                    * spec.stride()
                    + HEADER_BYTES;
                let src = ((y - region.y) as usize * region.width as usize
                    + (x0 - region.x) as usize)
                    * spec.stride();
                let len = (x1 - x0) as usize * spec.stride();
                blob[dst..dst + len].copy_from_slice(&bytes[src..src + len]);
            }
            let id = assets::sha256(&blob);
            if id != self.manifest.tiles[index] {
                next.pending
                    .entry(id.clone())
                    .or_insert_with(|| blob.into());
                next.manifest.tiles[index] = id;
            }
        }
        let used: BTreeSet<_> = next.manifest.tiles.iter().collect();
        next.pending.retain(|id, _| used.contains(id));
        next.manifest.sha256 = next.manifest.identity();
        control.check()?;
        Ok(next)
    }

    /// Publish complete immutable blocks, never a mutable document/history state.
    /// A failed/cancelled multi-block publication may retain complete cache files;
    /// retry verifies/deduplicates them. There is no historical request receipt.
    pub fn publish(&self, root: &Path, control: &Control) -> Result<Publication, Error> {
        control.check()?;
        assets::absolute(root)?;
        self.verify(Some(root), control)?;
        control.check()?;
        fs::create_dir_all(root).map_err(|_| io_error())?;
        let root = root.canonicalize().map_err(|_| io_error())?;
        let mut created = 0;
        let mut seen = BTreeSet::new();
        for (index, id) in self.manifest.tiles.iter().enumerate() {
            if !seen.insert(id) {
                continue;
            }
            control.check()?;
            if let Some(blob) = self.pending.get(id)
                && publish_blob(
                    &root,
                    id,
                    blob,
                    self.manifest.spec,
                    self.manifest.spec.tile(index),
                    control,
                )?
            {
                created += 1;
            }
        }
        // Once every unique descriptor has completed, later cancellation cannot
        // relabel this cache publication. The document commit is separate.
        Ok(Publication {
            manifest: self.manifest.clone(),
            created_tiles: created,
            existing_tiles: seen.len() - created,
        })
    }
}

fn intersecting(spec: Spec, region: Region) -> impl Iterator<Item = usize> {
    let x0 = region.x / TILE_EDGE;
    let x1 = (region.x + region.width - 1) / TILE_EDGE;
    let y0 = region.y / TILE_EDGE;
    let y1 = (region.y + region.height - 1) / TILE_EDGE;
    (y0..=y1).flat_map(move |y| (x0..=x1).map(move |x| (y * spec.columns() + x) as usize))
}
fn digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|v| v.is_ascii_digit() || (b'a'..=b'f').contains(&v))
}
fn check_root(root: Option<&Path>, control: &Control) -> Result<(), Error> {
    if let Some(root) = root {
        assets::absolute(root)?;
        control.check_path(root)?;
    }
    Ok(())
}
fn invalid(message: &str) -> Error {
    Error::new("INVALID_SAMPLE_STORE", message)
}
fn corrupt() -> Error {
    Error::new(
        "SAMPLE_TILE_CORRUPT",
        "Native sample tile bytes, type or identity do not match the manifest",
    )
}
fn io_error() -> Error {
    Error::new(
        "SAMPLE_STORE_IO",
        "Unable to access the explicit native sample store",
    )
}
fn validate_samples(bytes: &[u8], spec: Spec) -> Result<(), Error> {
    if spec.depth == Depth::F32 {
        let linear = spec.encoding == Encoding::LinearSrgb;
        for (index, data) in bytes.as_chunks::<4>().0.iter().enumerate() {
            let value = f32::from_le_bytes(*data);
            if !value.is_finite()
                || ((!linear || index % spec.channels.count() == spec.channels.count() - 1)
                    && !(0.0..=1.0).contains(&value))
            {
                return Err(Error::new(
                    "UNSUPPORTED_SAMPLE_RANGE",
                    "Native samples must be finite, with normalized encoded values and alpha; explicit linear binary32 color may be signed HDR",
                ));
            }
        }
    }
    Ok(())
}
fn validate_blob(bytes: &[u8], id: &str, spec: Spec, tile: Region) -> Result<(), Error> {
    let len = HEADER_BYTES + tile.width as usize * tile.height as usize * spec.stride();
    if bytes.len() != len
        || bytes[..HEADER_BYTES] != spec.header(tile.width, tile.height)
        || assets::sha256(bytes) != id
    {
        return Err(corrupt());
    }
    validate_samples(&bytes[HEADER_BYTES..], spec)
}
fn read_blob(root: Option<&Path>, id: &str, spec: Spec, tile: Region) -> Result<Arc<[u8]>, Error> {
    let root = root.ok_or_else(|| {
        Error::new(
            "SAMPLE_ROOT_REQUIRED",
            "Stored native samples require an explicit resource root",
        )
    })?;
    assets::absolute(root)?;
    let path = root.join(format!("{id}.native-tile"));
    let metadata = fs::symlink_metadata(&path).map_err(|e| {
        if e.kind() == std::io::ErrorKind::NotFound {
            Error::new(
                "SAMPLE_TILE_MISSING",
                "A pinned native sample tile is missing from the explicit resource root",
            )
        } else {
            io_error()
        }
    })?;
    let len = HEADER_BYTES + tile.width as usize * tile.height as usize * spec.stride();
    if metadata.file_type().is_symlink() || !metadata.is_file() || metadata.len() != len as u64 {
        return Err(corrupt());
    }
    let file = File::open(path).map_err(|_| io_error())?;
    let mut bytes = Vec::with_capacity(len);
    file.take(len as u64 + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| io_error())?;
    validate_blob(&bytes, id, spec, tile)?;
    Ok(bytes.into())
}

struct Temporary(PathBuf);
impl Drop for Temporary {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.0);
    }
}
fn publish_blob(
    root: &Path,
    id: &str,
    bytes: &[u8],
    spec: Spec,
    tile: Region,
    control: &Control,
) -> Result<bool, Error> {
    let target = root.join(format!("{id}.native-tile"));
    if fs::symlink_metadata(&target).is_ok() {
        read_blob(Some(root), id, spec, tile)?;
        return Ok(false);
    }
    let (mut file, owned) = (0..64)
        .find_map(|_| {
            let path = root.join(format!(
                ".inkbolt-native-{}-{}.tmp",
                std::process::id(),
                NEXT_TEMP.fetch_add(1, Ordering::Relaxed)
            ));
            match OpenOptions::new().create_new(true).write(true).open(&path) {
                Ok(file) => Some(Ok((file, Temporary(path)))),
                Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => None,
                Err(_) => Some(Err(io_error())),
            }
        })
        .unwrap_or_else(|| Err(io_error()))?;
    #[cfg(all(test, windows))]
    tests::checkpoint(root, "before_write");
    file.write_all(bytes)
        .and_then(|_| file.sync_all())
        .map_err(|_| io_error())?;
    drop(file);
    control.check()?;
    #[cfg(all(test, windows))]
    tests::checkpoint(root, "before_publish");
    control.check()?;
    let created = match fs::hard_link(&owned.0, &target) {
        Ok(()) => true,
        Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => {
            read_blob(Some(root), id, spec, tile)?;
            false
        }
        Err(_) => {
            return Err(Error::new(
                "SAMPLE_STORE_IO",
                "Native sample store requires create-only hard-link publication",
            ));
        }
    };
    #[cfg(all(test, windows))]
    tests::checkpoint(root, "after_publish");
    Ok(created)
}

#[cfg(test)]
mod tests;
