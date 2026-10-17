//! Pure assembly of disjoint native scanlines into their final block buffers.
use super::*;

pub(crate) struct Scatter {
    spec: Spec,
    blocks: Vec<Vec<u8>>,
    covered: Vec<u8>,
    written: usize,
}

impl Scatter {
    pub(crate) fn new(spec: Spec, control: &Control) -> Result<Self, Error> {
        control.check()?;
        spec.validate()?;
        let mut blocks = Vec::with_capacity(spec.tile_count());
        for index in 0..spec.tile_count() {
            control.check()?;
            let region = spec.tile(index);
            let mut block =
                vec![
                    0;
                    HEADER_BYTES + region.width as usize * region.height as usize * spec.stride()
                ];
            block[..HEADER_BYTES].copy_from_slice(&spec.header(region.width, region.height));
            blocks.push(block);
        }
        let pixels = spec.width as usize * spec.height as usize;
        Ok(Self {
            spec,
            blocks,
            covered: vec![0; pixels.div_ceil(8)],
            written: 0,
        })
    }

    /// Every supplied pixel must be new, in bounds and a complete native sample.
    /// The coverage bitmap costs one bit per source pixel (at most 2 MiB).
    pub(crate) fn row(
        &mut self,
        x: u32,
        y: u32,
        step: u32,
        bytes: &[u8],
        control: &Control,
    ) -> Result<(), Error> {
        control.check()?;
        let spec = self.spec;
        let stride = spec.stride();
        let count = bytes.len() / stride;
        if bytes.is_empty()
            || !bytes.len().is_multiple_of(stride)
            || step == 0
            || x >= spec.width
            || y >= spec.height
            || count > 1 + ((spec.width - 1 - x) / step) as usize
        {
            return Err(invalid(
                "Scattered native row exceeds its grid or sample bounds",
            ));
        }
        spec.validate_samples(bytes)?;
        // Check the entire row before changing either storage or its coverage.
        for i in 0..count {
            let pixel = y as usize * spec.width as usize + x as usize + i * step as usize;
            if self.covered[pixel / 8] & (1 << (pixel % 8)) != 0 {
                return Err(invalid("Scattered native rows overlap"));
            }
        }
        for (i, sample) in bytes.chunks_exact(stride).enumerate() {
            let col = x + i as u32 * step;
            let pixel = y as usize * spec.width as usize + col as usize;
            let index = (y / TILE_EDGE * spec.columns() + col / TILE_EDGE) as usize;
            let region = spec.tile(index);
            let offset = HEADER_BYTES
                + ((y - region.y) as usize * region.width as usize + (col - region.x) as usize)
                    * stride;
            self.blocks[index][offset..offset + stride].copy_from_slice(sample);
            self.covered[pixel / 8] |= 1 << (pixel % 8);
        }
        self.written += count;
        control.check()
    }

    pub(crate) fn finish(self, control: &Control) -> Result<Candidate, Error> {
        control.check()?;
        if self.written != self.spec.width as usize * self.spec.height as usize {
            return Err(invalid(
                "Scattered native rows do not cover the complete grid",
            ));
        }
        let mut candidate = Candidate {
            manifest: Manifest {
                version: 1,
                spec: self.spec,
                tiles: Vec::with_capacity(self.blocks.len()),
                sha256: String::new(),
            },
            pending: BTreeMap::new(),
        };
        // Consume each mutable buffer before moving to the next one. There is
        // never a second full frame while blocks become immutable/deduplicated.
        for block in self.blocks {
            control.check()?;
            let id = assets::sha256(&block);
            candidate
                .pending
                .entry(id.clone())
                .or_insert_with(|| block.into());
            candidate.manifest.tiles.push(id);
        }
        candidate.manifest.sha256 = candidate.manifest.identity();
        control.check()?;
        Ok(candidate)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn spec() -> Spec {
        Spec {
            width: 131,
            height: 129,
            depth: Depth::U8,
            channels: Channels::GrayAlpha,
            encoding: Encoding::EncodedSrgb,
        }
    }

    #[test]
    fn arbitrary_disjoint_rows_preserve_short_edges_and_exact_manifest() {
        let control = Control::default();
        let spec = spec();
        let bytes: Vec<_> = (0..spec.width * spec.height)
            .flat_map(|i| [(i % 251) as u8, (i % 239) as u8])
            .collect();
        let mut scattered = Scatter::new(spec, &control).unwrap();
        for y in (0..spec.height).rev() {
            for start in (0..3).rev() {
                let row: Vec<_> = (start..spec.width)
                    .step_by(3)
                    .flat_map(|x| {
                        let i = (y * spec.width + x) as usize * 2;
                        bytes[i..i + 2].iter().copied()
                    })
                    .collect();
                scattered.row(start, y, 3, &row, &control).unwrap();
            }
        }
        let candidate = scattered.finish(&control).unwrap();
        let reference = Candidate::from_bytes(spec, &bytes, &control).unwrap();
        assert_eq!(candidate.manifest(), reference.manifest());
        assert_eq!(
            candidate
                .read_region(
                    None,
                    Region {
                        x: 0,
                        y: 0,
                        width: spec.width,
                        height: spec.height
                    },
                    &control
                )
                .unwrap(),
            bytes
        );
    }

    #[test]
    fn overlaps_missing_pixels_and_invalid_samples_cannot_become_candidates() {
        let control = Control::default();
        let mut scattered = Scatter::new(spec(), &control).unwrap();
        scattered.row(2, 0, 1, &[12, 255], &control).unwrap();
        // The fresh first pixel of a partially overlapping row stays unwritten.
        assert!(scattered.row(1, 0, 1, &[1, 2, 3, 4], &control).is_err());
        scattered.row(1, 0, 1, &[1, 2], &control).unwrap();
        for (x, y, step, data) in [
            (0, 0, 0, &[0, 0][..]),
            (130, 0, 1, &[0, 0, 0, 0][..]),
            (0, 129, 1, &[0, 0][..]),
            (0, 0, 1, &[0][..]),
            (0, 0, 1, &[][..]),
        ] {
            assert!(scattered.row(x, y, step, data, &control).is_err());
        }
        assert!(scattered.finish(&control).is_err());
        let mut float = Scatter::new(
            Spec {
                width: 1,
                height: 1,
                depth: Depth::F32,
                ..spec()
            },
            &control,
        )
        .unwrap();
        let values = [f32::NAN.to_le_bytes(), 1.0_f32.to_le_bytes()].concat();
        assert!(float.row(0, 0, 1, &values, &control).is_err());
        assert!(float.finish(&control).is_err());
    }

    #[test]
    fn cancellation_prevents_writes_and_candidate_completion() {
        let control = Control::default();
        let mut scattered = Scatter::new(spec(), &control).unwrap();
        control.cancel();
        assert_eq!(
            scattered.row(0, 0, 1, &[0, 0], &control).unwrap_err().code,
            "CANCELLED"
        );
        assert_eq!(scattered.finish(&control).err().unwrap().code, "CANCELLED");
        assert_eq!(
            Scatter::new(spec(), &control).err().unwrap().code,
            "CANCELLED"
        );
    }
}
