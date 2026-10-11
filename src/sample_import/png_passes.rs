//! Adam7 pass rows go straight to native block buffers, without a full frame.
use super::{malformed, normalize_png};
use crate::{
    Error,
    control::Control,
    sample_store::{Candidate, Spec, scatter::Scatter},
};
use std::io::{BufRead, Seek};

pub(super) fn decode<R: BufRead + Seek>(
    reader: &mut png::Reader<R>,
    spec: Spec,
    channels: usize,
    control: &Control,
) -> Result<Candidate, Error> {
    let mut target = Scatter::new(spec, control)?;
    let stride = spec.depth.bytes() * spec.channels.count();
    let mut normalized = vec![0; spec.width as usize * stride];
    // Original coordinate schedule derived from PNG section 8.1's seven pass
    // pattern. Empty passes consume no row or filter byte.
    let passes = [
        (0, 0, 8, 8),
        (4, 0, 8, 8),
        (0, 4, 4, 8),
        (2, 0, 4, 4),
        (0, 2, 2, 4),
        (1, 0, 2, 2),
        (0, 1, 1, 2),
    ];
    for (index, (x, y, dx, dy)) in passes.into_iter().enumerate() {
        if x >= spec.width || y >= spec.height {
            continue;
        }
        let count = (spec.width - x).div_ceil(dx) as usize;
        for (line, row_y) in (y..spec.height).step_by(dy as usize).enumerate() {
            control.check()?;
            let row = reader
                .next_interlaced_row()
                .map_err(|_| malformed())?
                .ok_or_else(malformed)?;
            control.check()?;
            let expected = png::Adam7Info::new(index as u8 + 1, line as u32, spec.width);
            if !matches!(row.interlace(), png::InterlaceInfo::Adam7(info) if *info == expected) {
                return Err(malformed());
            }
            let native = &mut normalized[..count * stride];
            normalize_png(row.data(), native, spec.depth, channels)?;
            target.row(x, row_y, dx, native, control)?;
        }
    }
    control.check()?;
    if reader
        .next_interlaced_row()
        .map_err(|_| malformed())?
        .is_some()
    {
        return Err(malformed());
    }
    control.check()?;
    target.finish(control)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        hdr::Encoding,
        samples::{Channels, Depth},
    };
    use std::{
        io::{Cursor, Read, SeekFrom, Write},
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
    impl CancelRead {
        fn observe(&self) {
            if self.armed.load(Ordering::SeqCst) {
                self.reached.store(true, Ordering::SeqCst);
                self.control.cancel();
            }
        }
    }
    impl Read for CancelRead {
        fn read(&mut self, output: &mut [u8]) -> std::io::Result<usize> {
            self.observe();
            let count = output.len().min(1);
            self.bytes.read(&mut output[..count])
        }
    }
    impl BufRead for CancelRead {
        fn fill_buf(&mut self) -> std::io::Result<&[u8]> {
            self.observe();
            let bytes = self.bytes.fill_buf()?;
            Ok(&bytes[..bytes.len().min(1)])
        }
        fn consume(&mut self, count: usize) {
            self.bytes.consume(count);
        }
    }
    impl Seek for CancelRead {
        fn seek(&mut self, position: SeekFrom) -> std::io::Result<u64> {
            self.bytes.seek(position)
        }
    }

    #[test]
    fn adam7_cancellation_during_codec_input_returns_no_candidate() {
        fn chunk(target: &mut Vec<u8>, name: &[u8; 4], data: &[u8]) {
            target.extend_from_slice(&(data.len() as u32).to_be_bytes());
            target.extend_from_slice(name);
            target.extend_from_slice(data);
            let mut crc = crc32fast::Hasher::new();
            crc.update(name);
            crc.update(data);
            target.extend_from_slice(&crc.finalize().to_be_bytes());
        }
        let mut bytes = b"\x89PNG\r\n\x1a\n".to_vec();
        // A 1x3 RGBA8 original: pass 1 is y=0, pass 5 y=2, pass 7 y=1.
        chunk(
            &mut bytes,
            b"IHDR",
            &[0, 0, 0, 1, 0, 0, 0, 3, 8, 6, 0, 0, 1],
        );
        let mut zlib = flate2::write::ZlibEncoder::new(Vec::new(), flate2::Compression::default());
        zlib.write_all(&[0, 1, 2, 3, 4, 0, 9, 10, 11, 12, 0, 5, 6, 7, 8])
            .unwrap();
        chunk(&mut bytes, b"IDAT", &zlib.finish().unwrap());
        chunk(&mut bytes, b"IEND", &[]);
        let control = Control::default();
        let armed = Arc::new(AtomicBool::new(false));
        let reached = Arc::new(AtomicBool::new(false));
        let mut reader = png::Decoder::new(CancelRead {
            bytes: Cursor::new(bytes),
            armed: armed.clone(),
            reached: reached.clone(),
            control: control.clone(),
        })
        .read_info()
        .unwrap();
        armed.store(true, Ordering::SeqCst);
        let spec = Spec {
            width: 1,
            height: 3,
            depth: Depth::U8,
            channels: Channels::Rgba,
            encoding: Encoding::EncodedSrgb,
        };
        let error = decode(&mut reader, spec, 4, &control).err().unwrap();
        assert!(reached.load(Ordering::SeqCst));
        assert_eq!(error.code, "CANCELLED");
    }
}
