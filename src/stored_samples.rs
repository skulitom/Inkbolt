//! Retained native patches over immutable external sample blocks.
//!
//! The descriptor is a complete snapshot resource recipe: pure edits never
//! return references to unpublished blocks. Profiles and sampling remain part
//! of the source interpretation, independently of the exact native block bits.
use crate::{
    Error,
    assets::Sampling,
    control::Control,
    hdr::Encoding,
    profiles::Profile,
    sample_store::{Candidate, Manifest, Region},
};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use std::path::Path;
use std::{cell::RefCell, collections::BTreeMap, path::PathBuf};

pub const MAX_PATCHES: usize = 256;
pub const MAX_PATCH_PIXELS: u64 = 65_536;

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Patch {
    pub region: Region,
    /// Exact straight little-endian native channel bytes, in row-major order.
    pub data_hex: String,
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Grid {
    pub base: Manifest,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub patches: Vec<Patch>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub profile: Option<Profile>,
    #[serde(default)]
    pub sampling: Sampling,
}

impl Grid {
    pub(crate) fn recipe_sha256(&self) -> String {
        crate::assets::sha256(&serde_json::to_vec(self).expect("native grid serialization"))
    }
    /// Upper bounds for verification, decoded-cache churn, retained candidate
    /// blocks and temporary native/color buffers, before any resource reads.
    pub(crate) fn preparation_costs(&self) -> (u64, u64) {
        let spec = self.base.spec;
        let pixels = spec.width as u64 * spec.height as u64;
        let mut patch_tiles = std::collections::BTreeSet::new();
        let edge = crate::sample_store::TILE_EDGE;
        let mut patch_work = 0;
        for patch in &self.patches {
            let r = patch.region;
            for y in r.y / edge..(r.y + r.height).div_ceil(edge) {
                for x in r.x / edge..(r.x + r.width).div_ceil(edge) {
                    let count = (spec.width - x * edge).min(edge) as u64
                        * (spec.height - y * edge).min(edge) as u64;
                    patch_work += count;
                    patch_tiles.insert((x, y, count));
                }
            }
        }
        let pending_bytes = patch_tiles
            .iter()
            .map(|(_, _, count)| {
                count * spec.depth.bytes() as u64 * spec.channels.count() as u64 + 20
            })
            .sum::<u64>();
        let scratch_pixels = pixels.min((edge * edge) as u64);
        (
            pixels * 3 + patch_work,
            pixels.min(CACHE_PIXELS) * 4 + scratch_pixels * 12 + pending_bytes.div_ceil(8),
        )
    }
    pub fn validate(&self) -> Result<(), Error> {
        self.base.validate()?;
        if self.profile.is_some() != (self.base.spec.encoding == Encoding::ProfiledRgb) {
            return Err(invalid(
                "Profiled native samples require exactly one RGB source profile",
            ));
        }
        if let Some(profile) = &self.profile {
            crate::profiles::resolve(profile)?;
        }
        if self.patches.len() > MAX_PATCHES {
            return Err(crate::model::limit(
                "Stored native samples exceed the retained patch count",
            ));
        }
        let mut pixels = 0u64;
        let mut tile_work = 0u64;
        for patch in &self.patches {
            let r = patch.region;
            pixels += r.width as u64 * r.height as u64;
            if pixels > MAX_PATCH_PIXELS {
                return Err(crate::model::limit(
                    "Stored native samples exceed the retained patch pixel budget",
                ));
            }
            self.patch_bytes(patch)?;
            let edge = crate::sample_store::TILE_EDGE as u64;
            let columns = (r.x as u64 + r.width as u64).div_ceil(edge) - r.x as u64 / edge;
            let rows = (r.y as u64 + r.height as u64).div_ceil(edge) - r.y as u64 / edge;
            tile_work += columns * rows * edge * edge;
            if tile_work > crate::sample_store::MAX_PIXELS {
                return Err(crate::model::limit(
                    "Stored native patch preparation exceeds its tile work budget",
                ));
            }
        }
        Ok(())
    }

    fn patch_bytes(&self, patch: &Patch) -> Result<Vec<u8>, Error> {
        let spec = self.base.spec;
        let count = patch.region.width as u64 * patch.region.height as u64;
        if count > MAX_PATCH_PIXELS
            || patch.data_hex.len() as u64
                != count * spec.depth.bytes() as u64 * spec.channels.count() as u64 * 2
            || !patch.data_hex.bytes().all(|b| b.is_ascii_hexdigit())
        {
            return Err(invalid(
                "Native patch bytes must exactly match its bounded region and sample type",
            ));
        }
        let bytes = crate::render::unhex(&patch.data_hex);
        spec.validate_region_bytes(patch.region, &bytes)?;
        Ok(bytes)
    }

    /// Prepare a private candidate; inherited resources are never modified.
    /// Full verification still checks base blocks hidden by later patches.
    pub fn prepare(&self, root: Option<&Path>, control: &Control) -> Result<Candidate, Error> {
        control.check()?;
        self.validate()?;
        let mut candidate = Candidate::from_manifest(self.base.clone())?;
        candidate.verify(root, control)?;
        for patch in &self.patches {
            control.check()?;
            candidate =
                candidate.replace(root, patch.region, &self.patch_bytes(patch)?, control)?;
        }
        Ok(candidate)
    }

    /// A changed snapshot embeds its exact delta, not a dangling new file name.
    pub fn replace(
        &self,
        root: Option<&Path>,
        patch: Patch,
        control: &Control,
    ) -> Result<(Self, String, String), Error> {
        let bytes = self.patch_bytes(&patch)?;
        let before = self.prepare(root, control)?;
        let after = before.replace(root, patch.region, &bytes, control)?;
        let mut next = self.clone();
        if before.manifest().sha256 != after.manifest().sha256 {
            next.patches.push(patch);
            next.validate()?;
        }
        control.check()?;
        Ok((
            next,
            before.manifest().sha256.clone(),
            after.manifest().sha256.clone(),
        ))
    }

    pub fn geometry(&self) -> crate::model::Geometry {
        crate::model::Geometry::Rect {
            x: 0.0,
            y: 0.0,
            width: self.base.spec.width as f64,
            height: self.base.spec.height as f64,
        }
    }
}

fn invalid(message: &str) -> Error {
    Error::new("INVALID_STORED_SAMPLES", message)
}

const CACHE_PIXELS: u64 = 262_144;
const CACHE_TILES: usize = (CACHE_PIXELS
    / (crate::sample_store::TILE_EDGE as u64 * crate::sample_store::TILE_EDGE as u64))
    as usize;

struct CachedTile {
    used: u64,
    decoded: crate::samples::Decoded,
}
#[derive(Default)]
struct Cache {
    tiles: BTreeMap<usize, CachedTile>,
    clock: u64,
    decoded_pixels: u64,
}

pub(crate) struct Reader {
    candidate: Candidate,
    root: Option<PathBuf>,
    profile: Option<Profile>,
    linear: bool,
    control: Control,
    cache: RefCell<Cache>,
}
impl Reader {
    pub(crate) fn new(
        grid: &Grid,
        root: Option<&Path>,
        linear: bool,
        control: &Control,
    ) -> Result<Self, Error> {
        Ok(Self {
            candidate: grid.prepare(root, control)?,
            root: root.map(Path::to_owned),
            profile: grid.profile.clone(),
            linear,
            control: control.clone(),
            cache: RefCell::new(Cache::default()),
        })
    }
    fn pixel(&self, x: u32, y: u32) -> Result<[f64; 4], Error> {
        let spec = self.candidate.manifest().spec;
        let edge = crate::sample_store::TILE_EDGE;
        let index = (y / edge * spec.width.div_ceil(edge) + x / edge) as usize;
        let mut cache = self.cache.borrow_mut();
        cache.clock += 1;
        let tick = cache.clock;
        if !cache.tiles.contains_key(&index) {
            self.control.check()?;
            let region = Region {
                x: x / edge * edge,
                y: y / edge * edge,
                width: edge.min(spec.width - x / edge * edge),
                height: edge.min(spec.height - y / edge * edge),
            };
            let pixels = region.width as u64 * region.height as u64;
            if cache.decoded_pixels + pixels > spec.width as u64 * spec.height as u64 * 2 {
                return Err(crate::model::limit(
                    "Stored native sampling exceeds its bounded tile decoding work",
                ));
            }
            if cache.tiles.len() >= CACHE_TILES {
                let oldest = *cache
                    .tiles
                    .iter()
                    .min_by_key(|(_, value)| value.used)
                    .unwrap()
                    .0;
                cache.tiles.remove(&oldest);
            }
            let native = self
                .candidate
                .read_region(self.root.as_deref(), region, &self.control)?;
            let decoded = crate::samples::decode_native(
                region.width,
                &native,
                spec.depth,
                spec.channels,
                spec.encoding,
                self.profile.as_ref(),
                self.linear,
            )?;
            cache.decoded_pixels += pixels;
            cache.tiles.insert(
                index,
                CachedTile {
                    used: tick,
                    decoded,
                },
            );
        }
        let tile = cache.tiles.get_mut(&index).unwrap();
        tile.used = tick;
        Ok(tile
            .decoded
            .premultiplied_at((x % edge) as usize, (y % edge) as usize))
    }
}
impl crate::samples::Source for Reader {
    fn sample_planned(
        &self,
        crop: crate::assets::Crop,
        point: crate::model::Point,
        plan: &crate::resample::Plan,
    ) -> Result<[f64; 4], Error> {
        let failure = RefCell::new(None);
        let value = crate::resample::straight_range(point, plan, self.linear, |x, y| {
            if failure.borrow().is_some() {
                return [0.0; 4];
            }
            let x = x.clamp(crop.x as i64, (crop.x + crop.width - 1) as i64) as u32;
            let y = y.clamp(crop.y as i64, (crop.y + crop.height - 1) as i64) as u32;
            match self.pixel(x, y) {
                Ok(value) => value,
                Err(error) => {
                    *failure.borrow_mut() = Some(error);
                    [0.0; 4]
                }
            }
        });
        if let Some(error) = failure.into_inner() {
            Err(error)
        } else {
            value
        }
    }
}
