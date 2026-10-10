//! Chunk-band TIFF decoding into the pure native block candidate.
use super::{malformed, tiff_error};
use crate::{
    Error,
    control::Control,
    model::limit,
    sample_store::{Candidate, Spec},
    samples::Depth,
};
use std::io::{Read, Seek};
use tiff::decoder::{ChunkType, Decoder, DecodingResult};

pub(super) fn decode<R: Read + Seek>(
    decoder: &mut Decoder<R>,
    spec: Spec,
    channels: usize,
    planar: bool,
    control: &Control,
) -> Result<Candidate, Error> {
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
        if padded > super::MAX_NATIVE_DECODED_BYTES as u64 {
            return Err(limit("Sample TIFF padded tile work exceeds 64 MiB"));
        }
    }
    let stride = usize::try_from(stride)
        .map_err(|_| limit("Sample TIFF chunk stride exceeds platform bounds"))?;
    let unit = spec.depth.bytes();
    let output_channels = spec.channels.count();
    let mut band = Vec::new();
    Candidate::from_rows(spec, control, |y, output| {
        if y % height == 0 {
            // Drop the previous band before allocating the next. Chunk height is
            // source-defined: a single full-height strip can still be large.
            band.clear();
            for plane in 0..planes {
                for column in 0..across {
                    control.check()?;
                    let index = plane * per_plane + (y / height) as usize * across + column;
                    let mut chunk = DecodingResult::U8(Vec::new());
                    // Keep padded row stride for the locked codec's LZW edge
                    // behavior; copy only actual image samples below.
                    decoder
                        .read_chunk_to_buffer(&mut chunk, index as u32, stride)
                        .map_err(tiff_error)?;
                    control.check()?;
                    band.push(chunk);
                }
            }
        }
        if channels != output_channels {
            for pixel in output.chunks_exact_mut(output_channels * unit) {
                let alpha = &mut pixel[channels * unit..];
                match spec.depth {
                    Depth::U8 => alpha.fill(255),
                    Depth::U16 => alpha.copy_from_slice(&u16::MAX.to_le_bytes()),
                    Depth::F32 => alpha.copy_from_slice(&1.0_f32.to_le_bytes()),
                }
            }
        }
        let row_start = (y % height) as usize * stride;
        for (index, chunk) in band.iter_mut().enumerate() {
            let plane = index / across;
            let x = index % across * width as usize;
            let actual_width = (spec.width as usize - x).min(width as usize);
            let used = actual_width * chunk_channels * unit;
            let mut buffer = chunk.as_buffer(0);
            let row = buffer
                .as_bytes_mut()
                .get(row_start..row_start + used)
                .ok_or_else(malformed)?;
            for (offset, pixel) in row.chunks_exact(chunk_channels * unit).enumerate() {
                let start = ((x + offset) * output_channels + plane) * unit;
                let target = &mut output[start..start + chunk_channels * unit];
                for (value, destination) in
                    pixel.chunks_exact(unit).zip(target.chunks_exact_mut(unit))
                {
                    match spec.depth {
                        Depth::U8 => destination[0] = value[0],
                        Depth::U16 => destination.copy_from_slice(
                            &u16::from_ne_bytes(value.try_into().unwrap()).to_le_bytes(),
                        ),
                        Depth::F32 => destination.copy_from_slice(
                            &u32::from_ne_bytes(value.try_into().unwrap()).to_le_bytes(),
                        ),
                    }
                }
            }
        }
        Ok(())
    })
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
        let error = decode(&mut decoder, spec, 4, false, &control)
            .err()
            .unwrap();
        assert!(reached.load(Ordering::SeqCst));
        assert_eq!(error.code, "CANCELLED");
    }
}
