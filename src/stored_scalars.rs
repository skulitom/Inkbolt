//! Resource-aware scalar descriptors and bounded exact-byte readers.
use crate::{
    Error,
    control::Control,
    sample_store::Region,
    scalar_store::{Candidate, Manifest, Transfer},
};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use std::{
    cell::RefCell,
    collections::BTreeMap,
    path::{Path, PathBuf},
};

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Staged(Candidate);
impl Serialize for Staged {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        self.0
            .transfer(
                crate::stored_samples::MAX_PENDING_BYTES,
                &Control::default(),
            )
            .map_err(|e| serde::ser::Error::custom(e.message))?
            .serialize(serializer)
    }
}
impl<'de> Deserialize<'de> for Staged {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        Transfer::deserialize(deserializer)?
            .prepare(
                crate::stored_samples::MAX_PENDING_BYTES,
                &Control::default(),
            )
            .map(Self)
            .map_err(|e| serde::de::Error::custom(e.message))
    }
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
#[schemars(rename = "StoredScalarGrid")]
pub struct Grid {
    pub base: Manifest,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    #[schemars(with = "Option<crate::scalar_store::Transfer>")]
    pub staged: Option<Staged>,
}
impl Grid {
    pub fn from_candidate(candidate: Candidate) -> Self {
        let base = candidate.manifest().clone();
        Self {
            base,
            staged: (candidate.pending_tiles() != 0).then_some(Staged(candidate)),
        }
    }
    pub fn validate(&self) -> Result<(), Error> {
        self.base.validate()?;
        if let Some(staged) = &self.staged {
            if staged.0.manifest() != &self.base || staged.0.pending_tiles() == 0 {
                return Err(Error::new(
                    "INVALID_STORED_SCALAR",
                    "Pending scalar blocks must match the current manifest",
                ));
            }
            if staged.0.resident_bytes() > crate::stored_samples::MAX_PENDING_BYTES
                || staged.0.private_bytes() > crate::limits::stored_samples::MAX_PRIVATE_EDIT_BYTES
            {
                return Err(crate::model::limit(
                    "Pending scalar blocks exceed the native byte budget",
                ));
            }
        }
        Ok(())
    }
    pub fn pending_bytes(&self) -> usize {
        self.staged.as_ref().map_or(0, |s| s.0.pending_bytes())
    }
    pub(crate) fn candidate(&self) -> Option<&Candidate> {
        self.staged.as_ref().map(|s| &s.0)
    }
    pub(crate) fn transport_bytes(&self) -> usize {
        self.staged.as_ref().map_or(0, |s| {
            s.0.pending_bytes() * 2
                + serde_json::to_vec(&self.base)
                    .expect("scalar manifest serialization")
                    .len()
                + s.0.pending_tiles() * 128
                + 256
        })
    }
    pub(crate) fn cache_bytes(&self) -> u64 {
        let spec = self.base.spec;
        let edge = crate::scalar_store::TILE_EDGE as u64;
        (spec.width as u64 * spec.height as u64).min(
            spec.width.div_ceil(edge as u32) as u64
                * edge
                * edge
                * crate::limits::masks::NATIVE_SOURCE_CACHE_ROWS,
        )
    }
    pub fn prepare(&self, root: Option<&Path>, control: &Control) -> Result<Candidate, Error> {
        self.validate()?;
        let candidate = match &self.staged {
            Some(staged) => staged.0.clone(),
            None => Candidate::from_manifest(self.base.clone())?,
        };
        candidate.verify(root, control)?;
        Ok(candidate)
    }
}

struct Tile {
    used: u64,
    width: u32,
    bytes: Vec<u8>,
}
#[derive(Default)]
struct Cache {
    tiles: BTreeMap<usize, Tile>,
    clock: u64,
    decoded_pixels: u64,
}

/// One prepared source: verifies all dependencies, then retains a bounded cache.
/// Every later cache miss still verifies current file bytes against the manifest.
pub struct Reader {
    candidate: Candidate,
    root: Option<PathBuf>,
    control: Control,
    cache: RefCell<Cache>,
}
impl Reader {
    pub fn new(grid: &Grid, root: Option<&Path>, control: &Control) -> Result<Self, Error> {
        Ok(Self {
            candidate: grid.prepare(root, control)?,
            root: root.map(Path::to_owned),
            control: control.clone(),
            cache: RefCell::new(Cache::default()),
        })
    }
    pub fn pixel(&self, x: u32, y: u32) -> Result<u8, Error> {
        let spec = self.candidate.manifest().spec;
        if x >= spec.width || y >= spec.height {
            return Err(Error::new(
                "INVALID_STORED_SCALAR",
                "Scalar coordinates must be inside the native grid",
            ));
        }
        let edge = crate::scalar_store::TILE_EDGE;
        let index = (y / edge * spec.width.div_ceil(edge) + x / edge) as usize;
        let mut cache = self.cache.borrow_mut();
        cache.clock += 1;
        let tick = cache.clock;
        if tick.is_multiple_of(crate::limits::control::PIXEL_CHECK_INTERVAL as u64) {
            self.control.check()?;
        }
        if !cache.tiles.contains_key(&index) {
            self.control.check()?;
            let region = Region {
                x: x / edge * edge,
                y: y / edge * edge,
                width: edge.min(spec.width - x / edge * edge),
                height: edge.min(spec.height - y / edge * edge),
            };
            let pixels = region.width as u64 * region.height as u64;
            let maximum = spec.width as u64
                * spec.height as u64
                * crate::limits::stored_samples::MAX_SOURCE_DECODING_PASSES;
            if cache.decoded_pixels + pixels > maximum {
                return Err(crate::model::limit(
                    "Stored scalar sampling exceeds its bounded tile decoding work",
                ));
            }
            let capacity = spec.width.div_ceil(edge) as usize
                * crate::limits::masks::NATIVE_SOURCE_CACHE_ROWS as usize;
            if cache.tiles.len() >= capacity {
                let oldest = *cache.tiles.iter().min_by_key(|(_, t)| t.used).unwrap().0;
                cache.tiles.remove(&oldest);
            }
            let bytes = self
                .candidate
                .read_region(self.root.as_deref(), region, &self.control)?;
            cache.decoded_pixels += pixels;
            cache.tiles.insert(
                index,
                Tile {
                    used: tick,
                    width: region.width,
                    bytes,
                },
            );
        }
        let tile = cache.tiles.get_mut(&index).unwrap();
        tile.used = tick;
        Ok(tile.bytes[((y % edge) * tile.width + x % edge) as usize])
    }
}
