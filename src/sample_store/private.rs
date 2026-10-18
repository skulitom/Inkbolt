//! Owned immutable native edit extents; public memory constructors stay pure.
use super::*;
use crate::sample_import::source::Scratch;
use std::sync::Mutex;

#[cfg(test)]
#[path = "private_tests.rs"]
mod tests;

#[derive(Clone)]
pub(crate) struct Budget(crate::sample_import::source::Budget);
impl Default for Budget {
    fn default() -> Self {
        Self(crate::sample_import::source::Budget::new(
            crate::limits::stored_samples::MAX_PRIVATE_EDIT_BYTES,
        ))
    }
}

pub(super) struct Extent {
    file: Mutex<Scratch>,
    bytes: u64,
}
impl std::fmt::Debug for Extent {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("PrivateNativeExtent")
            .field("bytes", &self.bytes)
            .finish_non_exhaustive()
    }
}

#[derive(Clone, Debug)]
pub(super) enum PendingData {
    Memory(Arc<[u8]>),
    File {
        extent: Arc<Extent>,
        offset: u64,
        length: usize,
    },
}
impl From<Vec<u8>> for PendingData {
    fn from(bytes: Vec<u8>) -> Self {
        Self::Memory(bytes.into())
    }
}
impl PendingData {
    pub(super) fn len(&self) -> usize {
        match self {
            Self::Memory(bytes) => bytes.len(),
            Self::File { length, .. } => *length,
        }
    }
    pub(super) fn resident_bytes(&self) -> usize {
        match self {
            Self::Memory(bytes) => bytes.len(),
            Self::File { .. } => 0,
        }
    }
    pub(super) fn extent(&self) -> Option<(usize, u64)> {
        match self {
            Self::Memory(_) => None,
            Self::File { extent, .. } => Some((Arc::as_ptr(extent) as usize, extent.bytes)),
        }
    }
    pub(super) fn load(
        &self,
        id: &str,
        spec: impl Layout,
        tile: Region,
        control: &Control,
    ) -> Result<Arc<[u8]>, Error> {
        match self {
            Self::Memory(bytes) => Ok(bytes.clone()),
            Self::File {
                extent,
                offset,
                length,
            } => {
                control.check()?;
                if *length
                    != HEADER_BYTES + tile.width as usize * tile.height as usize * spec.stride()
                {
                    return Err(corrupt());
                }
                let mut bytes = vec![0; *length];
                extent
                    .file
                    .lock()
                    .map_err(|_| io_error())?
                    .read_at(*offset, &mut bytes, control)?;
                validate_blob(&bytes, id, spec, tile)?;
                Ok(bytes.into())
            }
        }
    }
}

impl<S: Layout> BlockCandidate<S> {
    pub(crate) fn map_private_rows(
        &self,
        control: &Control,
        read_row: impl FnMut(u32, &mut [u8]) -> Result<(), Error>,
    ) -> Result<Self, Error> {
        from_rows(
            self.manifest.spec,
            Some(self),
            control.native_staging(),
            &std::env::temp_dir(),
            control,
            read_row,
        )
    }
}

fn from_rows<S: Layout>(
    spec: S,
    prior: Option<&BlockCandidate<S>>,
    budget: &Budget,
    directory: &Path,
    control: &Control,
    mut read_row: impl FnMut(u32, &mut [u8]) -> Result<(), Error>,
) -> Result<BlockCandidate<S>, Error> {
    control.check()?;
    if spec.byte_len()? > crate::sample_import::MAX_NATIVE_DECODED_BYTES {
        return Err(crate::model::limit(
            "Native edit exceeds the private payload extent bound",
        ));
    }
    let mut scratch = Scratch::create(directory, budget.0.clone(), control)?;
    let mut offsets = BTreeMap::new();
    let inherited: BTreeSet<_> = prior
        .into_iter()
        .flat_map(|source| &source.manifest.tiles)
        .collect();
    let mut pending = BTreeMap::new();
    let mut length = 0u64;
    let mut manifest = BlockManifest {
        version: 1,
        spec,
        tiles: Vec::with_capacity(spec.tile_count()),
        sha256: String::new(),
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
                blob.extend_from_slice(&row[start..start + region.width as usize * spec.stride()]);
            }
        }
        for blob in band {
            control.check()?;
            let id = assets::sha256(&blob);
            if inherited.contains(&id) {
                if let Some(bytes) = prior.and_then(|source| source.pending.get(&id)) {
                    pending.insert(id.clone(), bytes.clone());
                }
            } else if let std::collections::btree_map::Entry::Vacant(entry) =
                offsets.entry(id.clone())
            {
                scratch.append(&blob, control)?;
                entry.insert((length, blob.len()));
                length += blob.len() as u64;
            }
            manifest.tiles.push(id);
        }
    }
    manifest.sha256 = manifest.identity();
    manifest.validate()?;
    control.check()?;
    let extent = Arc::new(Extent {
        file: Mutex::new(scratch),
        bytes: length,
    });
    pending.extend(offsets.into_iter().map(|(id, (offset, length))| {
        (
            id,
            PendingData::File {
                extent: extent.clone(),
                offset,
                length,
            },
        )
    }));
    Ok(BlockCandidate { manifest, pending })
}

/// Full dependency verification belongs to the caller; this one-band reader
/// verifies every loaded tile again and never reloads a tile for each row.
pub(crate) struct Rows<S> {
    candidate: BlockCandidate<S>,
    root: Option<PathBuf>,
    top: Option<u32>,
    band: Vec<Vec<u8>>,
}
impl<S: Layout> Rows<S> {
    pub(crate) fn new(candidate: BlockCandidate<S>, root: Option<&Path>) -> Self {
        Self {
            candidate,
            root: root.map(Path::to_owned),
            top: None,
            band: Vec::new(),
        }
    }
    pub(crate) fn read(&mut self, y: u32, row: &mut [u8], control: &Control) -> Result<(), Error> {
        control.check()?;
        let spec = self.candidate.manifest.spec;
        if y >= spec.height() || row.len() != spec.width() as usize * spec.stride() {
            return Err(invalid("Native row does not match the source grid"));
        }
        let top = y / TILE_EDGE * TILE_EDGE;
        if self.top != Some(top) {
            self.band.clear();
            self.top = None;
            for x in (0..spec.width()).step_by(TILE_EDGE as usize) {
                self.band.push(self.candidate.read_region(
                    self.root.as_deref(),
                    Region {
                        x,
                        y: top,
                        width: TILE_EDGE.min(spec.width() - x),
                        height: TILE_EDGE.min(spec.height() - top),
                    },
                    control,
                )?);
            }
            self.top = Some(top);
        }
        for (column, bytes) in self.band.iter().enumerate() {
            let x = column * TILE_EDGE as usize;
            let width = (spec.width() as usize - x).min(TILE_EDGE as usize);
            let start = (y - top) as usize * width * spec.stride();
            row[x * spec.stride()..(x + width) * spec.stride()]
                .copy_from_slice(&bytes[start..start + width * spec.stride()]);
        }
        Ok(())
    }
}
