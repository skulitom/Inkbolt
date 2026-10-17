//! Sealed block layouts share candidate, transfer and publication invariants.
use super::*;

pub(crate) mod sealed {
    pub trait Sealed {}
}

/// Built-in native layouts. External implementations cannot alter the framing,
/// allocation bounds or validation of content-addressed blocks.
pub trait Layout: sealed::Sealed + Copy + std::fmt::Debug + Eq {
    const GRID_MAGIC: &'static [u8; 8];
    const MANIFEST_SCHEMA: &'static str;
    const TRANSFER_SCHEMA: &'static str;

    fn width(self) -> u32;
    fn height(self) -> u32;
    fn stride(self) -> usize;
    fn header(self, width: u32, height: u32) -> [u8; HEADER_BYTES];
    fn validate(self) -> Result<(), Error>;
    fn validate_samples(self, bytes: &[u8]) -> Result<(), Error>;

    fn columns(self) -> u32 {
        self.width().div_ceil(TILE_EDGE)
    }
    fn tile_count(self) -> usize {
        self.columns() as usize * self.height().div_ceil(TILE_EDGE) as usize
    }
    fn tile(self, index: usize) -> Region {
        let x = index as u32 % self.columns() * TILE_EDGE;
        let y = index as u32 / self.columns() * TILE_EDGE;
        Region {
            x,
            y,
            width: TILE_EDGE.min(self.width() - x),
            height: TILE_EDGE.min(self.height() - y),
        }
    }
    fn validate_dimensions(self) -> Result<(), Error> {
        if !(1..=crate::model::MAX_DIMENSION).contains(&self.width())
            || !(1..=crate::model::MAX_DIMENSION).contains(&self.height())
            || self.width() as u64 * self.height() as u64 > MAX_PIXELS
            || self.tile_count() > MAX_TILES
        {
            return Err(crate::model::limit(
                "Native sample store dimensions, pixels or tile count exceed the bound",
            ));
        }
        Ok(())
    }
    fn byte_len(self) -> Result<usize, Error> {
        self.validate()?;
        Ok(self.width() as usize * self.height() as usize * self.stride())
    }
    fn validate_region_bytes(self, region: Region, bytes: &[u8]) -> Result<(), Error> {
        self.validate()?;
        region.validate(self)?;
        if bytes.len() != region.width as usize * region.height as usize * self.stride() {
            return Err(invalid("Replacement bytes do not match the native region"));
        }
        self.validate_samples(bytes)
    }
}

impl sealed::Sealed for Spec {}
impl Layout for Spec {
    const GRID_MAGIC: &'static [u8; 8] = b"INKGRID1";
    const MANIFEST_SCHEMA: &'static str = "Manifest";
    const TRANSFER_SCHEMA: &'static str = "Transfer";

    fn width(self) -> u32 {
        self.width
    }
    fn height(self) -> u32 {
        self.height
    }
    fn stride(self) -> usize {
        Spec::stride(&self)
    }
    fn header(self, width: u32, height: u32) -> [u8; HEADER_BYTES] {
        Spec::header(&self, width, height)
    }
    fn validate(self) -> Result<(), Error> {
        Spec::validate(&self)
    }
    fn validate_samples(self, bytes: &[u8]) -> Result<(), Error> {
        validate_image_samples(bytes, self)
    }
}
