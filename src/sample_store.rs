//! Immutable native pixel blocks and pure copy-on-write candidates.
//!
//! This library primitive deliberately separates candidate construction/reads
//! from publication. A dry run never publishes resource or session files;
//! internal whole-image edits can own bounded, delete-on-close private extents.
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

pub use crate::limits::sample_store::MAX_PIXELS;
pub use crate::limits::sample_store::MAX_REGION_PIXELS;
pub use crate::limits::sample_store::MAX_TILES;
pub use crate::limits::sample_store::TILE_EDGE;
pub(crate) const HEADER_BYTES: usize = crate::limits::sample_store::HEADER_BYTES;
const MAGIC: &[u8; 8] = b"INKTILE1";
static NEXT_TEMP: AtomicU64 = AtomicU64::new(0);
pub(crate) mod admission;
pub(crate) mod layout;
pub use layout::Layout;
pub(crate) mod private;
pub(crate) mod publication;
use private::PendingData;
#[cfg(test)]
mod scatter;
mod transfer;
pub use transfer::{BlockTransfer, PendingBlock};
pub type Manifest = BlockManifest<Spec>;
pub type Candidate = BlockCandidate<Spec>;
pub type Publication = BlockPublication<Spec>;
pub type Transfer = BlockTransfer<Spec>;

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
        self.validate_dimensions()?;
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
        self.validate_samples(bytes)
    }
    pub(crate) fn stride(&self) -> usize {
        self.depth.bytes() * self.channels.count()
    }
    fn columns(&self) -> u32 {
        self.width.div_ceil(TILE_EDGE)
    }
    pub(crate) fn tile_count(&self) -> usize {
        self.columns() as usize * self.height.div_ceil(TILE_EDGE) as usize
    }
    pub(crate) fn tile(&self, index: usize) -> Region {
        let x = index as u32 % self.columns() * TILE_EDGE;
        let y = index as u32 / self.columns() * TILE_EDGE;
        Region {
            x,
            y,
            width: TILE_EDGE.min(self.width - x),
            height: TILE_EDGE.min(self.height - y),
        }
    }
    pub(crate) fn header(&self, width: u32, height: u32) -> [u8; HEADER_BYTES] {
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
    fn validate(&self, spec: impl Layout) -> Result<(), Error> {
        if self.width == 0
            || self.height == 0
            || self.x as u64 + self.width as u64 > spec.width() as u64
            || self.y as u64 + self.height as u64 > spec.height() as u64
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

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct BlockManifest<S> {
    pub version: u32,
    pub spec: S,
    /// Fixed row-major tile order. Pixel interpretation profiles remain separate
    /// document metadata and must also bind any decoded/rendered cache key.
    pub tiles: Vec<String>,
    pub sha256: String,
}
impl<S: Layout + JsonSchema> JsonSchema for BlockManifest<S> {
    fn schema_name() -> std::borrow::Cow<'static, str> {
        S::MANIFEST_SCHEMA.into()
    }
    fn json_schema(generator: &mut schemars::SchemaGenerator) -> schemars::Schema {
        #[derive(JsonSchema)]
        #[serde(deny_unknown_fields)]
        #[allow(dead_code)]
        struct Definition<S> {
            version: u32,
            spec: S,
            /// Fixed row-major tile order. Pixel interpretation profiles remain separate
            /// document metadata and must also bind any decoded/rendered cache key.
            tiles: Vec<String>,
            sha256: String,
        }
        Definition::<S>::json_schema(generator)
    }
}

impl<S: Layout> BlockManifest<S> {
    pub(crate) fn identity(&self) -> String {
        let mut hash = Sha256::new();
        hash.update(S::GRID_MAGIC);
        hash.update(self.spec.header(self.spec.width(), self.spec.height()));
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

/// Pending blobs are immutable memory or internal owned extents, shared by clones.
/// Only referenced blobs survive a replacement; retained older candidates remain
/// unchanged. Public constructors, reads and replacements never create files.
#[derive(Clone, Debug)]
pub struct BlockCandidate<S> {
    manifest: BlockManifest<S>,
    pending: BTreeMap<String, PendingData>,
}
impl<S: PartialEq> PartialEq for BlockCandidate<S> {
    fn eq(&self, other: &Self) -> bool {
        self.manifest == other.manifest && self.pending.keys().eq(other.pending.keys())
    }
}
impl<S: Eq> Eq for BlockCandidate<S> {}

#[derive(Debug, Serialize)]
pub struct BlockPublication<S> {
    pub manifest: BlockManifest<S>,
    pub created_tiles: usize,
    pub existing_tiles: usize,
}

impl<S: Layout> BlockCandidate<S> {
    pub fn from_manifest(manifest: BlockManifest<S>) -> Result<Self, Error> {
        manifest.validate()?;
        Ok(Self {
            manifest,
            pending: BTreeMap::new(),
        })
    }
    pub fn manifest(&self) -> &BlockManifest<S> {
        &self.manifest
    }
    pub fn pending_bytes(&self) -> usize {
        self.pending.values().map(|b| b.len()).sum()
    }
    pub(crate) fn resident_bytes(&self) -> usize {
        self.pending.values().map(PendingData::resident_bytes).sum()
    }
    pub(crate) fn private_extents(&self) -> impl Iterator<Item = (usize, u64)> + '_ {
        self.pending.values().filter_map(PendingData::extent)
    }
    pub(crate) fn private_bytes(&self) -> u64 {
        self.private_extents()
            .collect::<BTreeMap<_, _>>()
            .values()
            .sum()
    }
    pub fn pending_tiles(&self) -> usize {
        self.pending.len()
    }

    /// Input bytes are exact little-endian straight channels, never quantized.
    /// This initial constructor retains at most the validated whole native frame
    /// plus tile headers; it does not claim a streaming image decoder.
    pub fn from_bytes(spec: S, bytes: &[u8], control: &Control) -> Result<Self, Error> {
        control.check()?;
        if bytes.len() != spec.byte_len()? {
            return Err(invalid(
                "Native sample bytes do not match the declared grid",
            ));
        }
        let mut candidate = Self {
            manifest: BlockManifest {
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
                let offset = (y as usize * spec.width() as usize + tile.x as usize) * spec.stride();
                blob.extend_from_slice(
                    &bytes[offset..offset + tile.width as usize * spec.stride()],
                );
            }
            spec.validate_samples(&blob[HEADER_BYTES..])?;
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

    /// Read exact native rows directly into the immutable block candidate.
    /// The producer fills one reusable row in ascending order. Only one tile
    /// band is unfinished at once; completed unique blocks remain in memory
    /// until explicit publication. Failure/cancellation writes no files.
    pub fn from_rows(
        spec: S,
        control: &Control,
        mut read_row: impl FnMut(u32, &mut [u8]) -> Result<(), Error>,
    ) -> Result<Self, Error> {
        control.check()?;
        spec.validate()?;
        let mut candidate = Self {
            manifest: BlockManifest {
                version: 1,
                spec,
                tiles: Vec::with_capacity(spec.tile_count()),
                sha256: String::new(),
            },
            pending: BTreeMap::new(),
        };
        let mut row = vec![0; spec.width() as usize * spec.stride()];
        let columns = spec.columns() as usize;
        for first in (0..spec.tile_count()).step_by(columns) {
            control.check()?;
            let regions: Vec<_> = (first..first + columns).map(|i| spec.tile(i)).collect();
            let mut band: Vec<_> = regions
                .iter()
                .map(|r| {
                    let mut blob = Vec::with_capacity(
                        HEADER_BYTES + r.width as usize * r.height as usize * spec.stride(),
                    );
                    blob.extend_from_slice(&spec.header(r.width, r.height));
                    blob
                })
                .collect();
            for y in regions[0].y..regions[0].y + regions[0].height {
                control.check()?;
                read_row(y, &mut row)?;
                control.check()?;
                spec.validate_samples(&row)?;
                for (region, blob) in regions.iter().zip(&mut band) {
                    let start = region.x as usize * spec.stride();
                    let end = start + region.width as usize * spec.stride();
                    blob.extend_from_slice(&row[start..end]);
                }
            }
            for blob in band {
                control.check()?;
                let id = assets::sha256(&blob);
                candidate
                    .pending
                    .entry(id.clone())
                    .or_insert_with(|| blob.into());
                candidate.manifest.tiles.push(id);
            }
        }
        candidate.manifest.sha256 = candidate.manifest.identity();
        control.check()?;
        Ok(candidate)
    }

    fn load(
        &self,
        index: usize,
        root: Option<&Path>,
        control: &Control,
    ) -> Result<Arc<[u8]>, Error> {
        let id = &self.manifest.tiles[index];
        let spec = self.manifest.spec;
        let tile = spec.tile(index);
        // Only validated constructors can insert immutable pending bytes. The
        // private manifest/candidate cannot be changed through this public API.
        if let Some(bytes) = self.pending.get(id) {
            bytes.load(id, spec, tile, control)
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
                self.load(index, root, control)?;
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
        // Candidate construction validated this immutable manifest. Rehashing
        // every reference on each window would make tiled reads quadratic;
        // loaded external blocks still receive full content verification.
        let spec = self.manifest.spec;
        region.validate(spec)?;
        let mut result = vec![0; region.width as usize * region.height as usize * spec.stride()];
        for index in intersecting(spec, region) {
            control.check()?;
            let tile = spec.tile(index);
            let bytes = self.load(index, root, control)?;
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
        // Candidate construction validated this immutable manifest. Rehashing
        // every reference on each window would make tiled reads quadratic;
        // loaded external blocks still receive full content verification.
        let spec = self.manifest.spec;
        spec.validate_region_bytes(region, bytes)?;
        let mut next = self.clone();
        for index in intersecting(spec, region) {
            control.check()?;
            let tile = spec.tile(index);
            let mut blob = self.load(index, root, control)?.to_vec();
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
    pub fn publish(&self, root: &Path, control: &Control) -> Result<BlockPublication<S>, Error> {
        publication::publish(&self.manifest, &mut &self.pending, root, control)
    }
}

fn intersecting(spec: impl Layout, region: Region) -> impl Iterator<Item = usize> {
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
fn validate_image_samples(bytes: &[u8], spec: Spec) -> Result<(), Error> {
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
fn validate_blob(bytes: &[u8], id: &str, spec: impl Layout, tile: Region) -> Result<(), Error> {
    let len = HEADER_BYTES + tile.width as usize * tile.height as usize * spec.stride();
    if bytes.len() != len
        || bytes[..HEADER_BYTES] != spec.header(tile.width, tile.height)
        || assets::sha256(bytes) != id
    {
        return Err(corrupt());
    }
    spec.validate_samples(&bytes[HEADER_BYTES..])
}
fn read_blob(
    root: Option<&Path>,
    id: &str,
    spec: impl Layout,
    tile: Region,
) -> Result<Arc<[u8]>, Error> {
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

struct Temporary {
    path: PathBuf,
    armed: bool,
}
impl Drop for Temporary {
    fn drop(&mut self) {
        if self.armed {
            let _ = fs::remove_file(&self.path);
        }
    }
}
fn publish_blob(
    root: &Path,
    id: &str,
    bytes: &[u8],
    spec: impl Layout,
    tile: Region,
    control: &Control,
) -> Result<bool, Error> {
    let target = root.join(format!("{id}.native-tile"));
    if fs::symlink_metadata(&target).is_ok() {
        read_blob(Some(root), id, spec, tile)?;
        return Ok(false);
    }
    let (mut file, mut owned) = (0..crate::limits::sample_store::MAX_STAGE_ATTEMPTS)
        .find_map(|_| {
            let path = root.join(format!(
                ".inkbolt-native-{}-{}.tmp",
                std::process::id(),
                NEXT_TEMP.fetch_add(1, Ordering::Relaxed)
            ));
            match OpenOptions::new().create_new(true).write(true).open(&path) {
                Ok(file) => Some(Ok((file, Temporary { path, armed: true }))),
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
    let created = match fs::hard_link(&owned.path, &target) {
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
    // Admission reserves one possible temporary alias, not one per new block.
    // Stop on failed cleanup before another block can consume that reservation.
    fs::remove_file(&owned.path).map_err(|_| io_error())?;
    owned.armed = false;
    Ok(created)
}

#[cfg(test)]
mod tests;
