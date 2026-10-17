//! Exact coverage bytes in immutable native blocks, independent of color.
use crate::{Error, sample_store, sample_store::Layout};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

pub use sample_store::{MAX_PIXELS, MAX_REGION_PIXELS, MAX_TILES, Region, TILE_EDGE};
pub type Candidate = sample_store::BlockCandidate<Spec>;
pub type Manifest = sample_store::BlockManifest<Spec>;
pub type Publication = sample_store::BlockPublication<Spec>;
pub type Transfer = sample_store::BlockTransfer<Spec>;

#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
#[schemars(rename = "ScalarSpec")]
pub struct Spec {
    pub width: u32,
    pub height: u32,
}
impl Spec {
    pub fn validate(&self) -> Result<(), Error> {
        self.validate_dimensions()
    }
    pub fn byte_len(&self) -> Result<usize, Error> {
        Layout::byte_len(*self)
    }
    pub fn validate_region_bytes(&self, region: Region, bytes: &[u8]) -> Result<(), Error> {
        Layout::validate_region_bytes(*self, region, bytes)
    }
}

impl sample_store::layout::sealed::Sealed for Spec {}
impl Layout for Spec {
    const GRID_MAGIC: &'static [u8; 8] = b"INKSCGR1";
    const MANIFEST_SCHEMA: &'static str = "ScalarManifest";
    const TRANSFER_SCHEMA: &'static str = "ScalarTransfer";

    fn width(self) -> u32 {
        self.width
    }
    fn height(self) -> u32 {
        self.height
    }
    fn stride(self) -> usize {
        1
    }
    fn header(self, width: u32, height: u32) -> [u8; 20] {
        let mut result = [0; 20];
        result[..8].copy_from_slice(b"INKSCAL1");
        result[8..12].copy_from_slice(&width.to_le_bytes());
        result[12..16].copy_from_slice(&height.to_le_bytes());
        result[16] = 1;
        result[17] = 1;
        result
    }
    fn validate(self) -> Result<(), Error> {
        self.validate_dimensions()
    }
    fn validate_samples(self, _: &[u8]) -> Result<(), Error> {
        Ok(())
    }
}

#[cfg(test)]
mod tests;
