//! One TIFF chunk at a time, assembled into private native pixel staging.
use super::{malformed, tiff_error};
use crate::{
    Error,
    control::Control,
    model::limit,
    sample_store::{Region, Spec},
    samples::Depth,
};
use std::io::{Read, Seek};
use tiff::decoder::{ChunkType, Decoder, DecodingResult};

pub(super) fn decode<R: Read + Seek>(
    decoder: &mut Decoder<R>,
    spec: Spec,
    channels: usize,
    planar: bool,
    budget: &super::source::Budget,
    control: &Control,
) -> Result<super::pixels::Prepared, Error> {
    spec.validate()?;
    let tiled = decoder.get_chunk_type() == ChunkType::Tile;
    let (width, height) = decoder.chunk_dimensions();
    if width == 0 || height == 0 || (!tiled && width != spec.width) {
        return Err(malformed());
    }
    let across = spec.width.div_ceil(width) as usize;
    let per_plane = across * spec.height.div_ceil(height) as usize;
    let planes = if planar { channels } else { 1 };
    let chunk_channels = if planar { 1 } else { channels };
    let chunks = per_plane * planes;
    let actual = if tiled {
        decoder.tile_count()
    } else {
        decoder.strip_count()
    }
    .map_err(tiff_error)? as usize;
    if actual != chunks {
        return Err(malformed());
    }
    let stride = width as u64 * chunk_channels as u64 * spec.depth.bytes() as u64;
    if tiled {
        let padded = stride
            .checked_mul(height as u64)
            .and_then(|bytes| bytes.checked_mul(chunks as u64))
            .ok_or_else(|| limit("Sample TIFF padded tile work exceeds limit"))?;
        if padded > crate::limits::sample_import::MAX_NATIVE_TIFF_PADDED_BYTES {
            return Err(limit(&format!(
                "Sample TIFF padded tile work exceeds {} MiB",
                crate::limits::sample_import::MAX_NATIVE_TIFF_PADDED_BYTES / (1024 * 1024)
            )));
        }
    }
    let stride = usize::try_from(stride)
        .map_err(|_| limit("Sample TIFF chunk stride exceeds platform bounds"))?;
    let unit = spec.depth.bytes();
    let output_channels = spec.channels.count();
    let mut target = super::pixels::Builder::new(spec, budget, false, control)?;
    for index in 0..chunks {
        control.check()?;
        let plane = index / per_plane;
        let region = index % per_plane;
        let x = region % across * width as usize;
        let y = region / across * height as usize;
        let actual_width = (spec.width as usize - x).min(width as usize);
        let actual_height = (spec.height as usize - y).min(height as usize);
        // A source chunk may span the whole image, but completed chunks and
        // other planes never remain resident. The decoder's allocation budget
        // and padded-work admission above retain their existing limits.
        let mut chunk = DecodingResult::U8(Vec::new());
        // Preserve padded row stride for the locked codec's LZW edge behavior.
        decoder
            .read_chunk_to_buffer(&mut chunk, index as u32, stride)
            .map_err(tiff_error)?;
        control.check()?;
        let mut buffer = chunk.as_buffer(0);
        for row_index in 0..actual_height {
            control.check()?;
            let row_start = row_index * stride;
            let used = actual_width * chunk_channels * unit;
            let row = buffer
                .as_bytes_mut()
                .get(row_start..row_start + used)
                .ok_or_else(malformed)?;
            let mut native = Vec::with_capacity(used);
            for value in row.chunks_exact(unit) {
                match spec.depth {
                    Depth::U8 => native.push(value[0]),
                    Depth::U16 => native.extend_from_slice(
                        &u16::from_ne_bytes(value.try_into().unwrap()).to_le_bytes(),
                    ),
                    Depth::F32 => native.extend_from_slice(
                        &u32::from_ne_bytes(value.try_into().unwrap()).to_le_bytes(),
                    ),
                }
            }
            target.components(
                Region {
                    x: x as u32,
                    y: (y + row_index) as u32,
                    width: actual_width as u32,
                    height: 1,
                },
                if planar { plane } else { 0 },
                chunk_channels,
                &native,
                channels != output_channels,
                control,
            )?;
        }
    }
    target.finish(control)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{hdr::Encoding, samples::Channels};
    use std::{
        io::{Cursor, SeekFrom},
        sync::{
            Arc,
            atomic::{AtomicBool, Ordering},
        },
    };

    struct CancelRead {
        bytes: Cursor<Vec<u8>>,
        armed: Arc<AtomicBool>,
        reached: Arc<AtomicBool>,
        control: Control,
    }
    impl Read for CancelRead {
        fn read(&mut self, output: &mut [u8]) -> std::io::Result<usize> {
            let count = self.bytes.read(output)?;
            if count > 0 && self.armed.load(Ordering::SeqCst) {
                self.reached.store(true, Ordering::SeqCst);
                self.control.cancel();
            }
            Ok(count)
        }
    }
    impl Seek for CancelRead {
        fn seek(&mut self, position: SeekFrom) -> std::io::Result<u64> {
            self.bytes.seek(position)
        }
    }

    #[test]
    fn tiff_bands_observe_cancellation_after_codec_reads_without_returning_candidate() {
        let mut encoded = Cursor::new(Vec::new());
        {
            let mut encoder = tiff::encoder::TiffEncoder::new(&mut encoded).unwrap();
            let mut image = encoder
                .new_image::<tiff::encoder::colortype::RGBA8>(2, 3)
                .unwrap();
            image.rows_per_strip(1).unwrap();
            image.write_data(&[23; 24]).unwrap();
        }
        encoded.set_position(0);
        let control = Control::default();
        let armed = Arc::new(AtomicBool::new(false));
        let reached = Arc::new(AtomicBool::new(false));
        let mut decoder = Decoder::new(CancelRead {
            bytes: encoded,
            armed: armed.clone(),
            reached: reached.clone(),
            control: control.clone(),
        })
        .unwrap();
        armed.store(true, Ordering::SeqCst);
        let spec = Spec {
            width: 2,
            height: 3,
            depth: Depth::U8,
            channels: Channels::Rgba,
            encoding: Encoding::EncodedSrgb,
        };
        let budget = super::super::source::Budget::new(
            crate::limits::sample_import::MAX_PRIVATE_STAGING_BYTES,
        );
        let error = decode(&mut decoder, spec, 4, false, &budget, &control)
            .err()
            .unwrap();
        assert!(reached.load(Ordering::SeqCst));
        assert_eq!(error.code, "CANCELLED");
    }
}
