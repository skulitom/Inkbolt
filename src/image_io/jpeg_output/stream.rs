//! Preserve metadata's historical before-SOS placement without buffering the JPEG.
use super::{Control, Error, RefCell, Write, error};
use std::io;

pub(super) struct Stream<'a, W> {
    output: W,
    metadata: Option<&'a str>,
    control: &'a Control,
    failure: &'a RefCell<Option<Error>>,
    header: [u8; 4],
    used: usize,
    remaining: usize,
    started: bool,
    scanned: bool,
    tail: [u8; 2],
    poisoned: bool,
    unchecked_bytes: usize,
}
impl<'a, W: Write> Stream<'a, W> {
    pub(super) fn new(
        output: W,
        metadata: Option<&'a str>,
        control: &'a Control,
        failure: &'a RefCell<Option<Error>>,
    ) -> Result<Self, Error> {
        // The shared metadata builder already bounds the packet. Render receipts
        // are appended afterward; preserve their historical admission here.
        if metadata.is_some_and(|p| p.len() > crate::publish::MAX_OUTPUT_BYTES) {
            return Err(crate::model::limit("JPEG metadata exceeds output budget"));
        }
        Ok(Self {
            output,
            metadata,
            control,
            failure,
            header: [0; 4],
            used: 0,
            remaining: 0,
            started: false,
            scanned: false,
            tail: [0; 2],
            poisoned: false,
            unchecked_bytes: crate::limits::jpeg_output::STREAM_BUFFER_BYTES,
        })
    }
    fn check(&mut self) -> io::Result<()> {
        if self.poisoned || self.failure.borrow().is_some() {
            return Err(io::Error::other("JPEG output failed"));
        }
        if let Err(error) = self.control.check() {
            *self.failure.borrow_mut() = Some(error);
            return Err(io::Error::other("JPEG output cancelled"));
        }
        Ok(())
    }
    fn comments(&mut self) -> io::Result<()> {
        if let Some(packet) = self.metadata {
            let parts = packet
                .len()
                .div_ceil(crate::limits::metadata::JPEG_PART_BYTES);
            for (index, part) in packet
                .as_bytes()
                .chunks(crate::limits::metadata::JPEG_PART_BYTES)
                .enumerate()
            {
                self.check()?;
                let len = 2 + crate::metadata::JPEG_PREFIX.len() + 4 + part.len();
                self.output.write_all(&[255, 254])?;
                self.output.write_all(&(len as u16).to_be_bytes())?;
                self.output.write_all(crate::metadata::JPEG_PREFIX)?;
                self.output.write_all(&((index + 1) as u16).to_be_bytes())?;
                self.output.write_all(&(parts as u16).to_be_bytes())?;
                self.output.write_all(part)?;
            }
        }
        Ok(())
    }
    fn accept(&mut self, mut data: &[u8]) -> io::Result<()> {
        // A row failure must stop even the next tiny entropy write. Filesystem
        // cancellation probes are bounded by rows and encoded chunks instead
        // of being repeated for each byte or bit-buffer emitted by the codec.
        if self.poisoned || self.failure.borrow().is_some() {
            return Err(io::Error::other("JPEG output failed"));
        }
        self.unchecked_bytes = self.unchecked_bytes.saturating_add(data.len());
        if self.unchecked_bytes >= crate::limits::jpeg_output::STREAM_BUFFER_BYTES {
            self.check()?;
            self.unchecked_bytes = data.len();
        }
        while !data.is_empty() {
            if self.remaining > 0 {
                let count = self.remaining.min(data.len());
                self.output.write_all(&data[..count])?;
                data = &data[count..];
                self.remaining -= count;
                continue;
            }
            if self.scanned {
                return self.output.write_all(data);
            }
            self.header[self.used] = data[0];
            self.used += 1;
            data = &data[1..];
            if self.used == 1 && self.header[0] != 255 {
                return Err(io::Error::other("Invalid JPEG header"));
            }
            if self.used == 2 {
                let marker = self.header[1];
                if !self.started {
                    if marker != 216 {
                        return Err(io::Error::other("Missing JPEG start"));
                    }
                    self.output.write_all(&self.header[..2])?;
                    self.started = true;
                    self.used = 0;
                    continue;
                }
                if matches!(marker, 0 | 1 | 208..=217 | 255) {
                    return Err(io::Error::other("Invalid JPEG segment"));
                }
            }
            if self.used == 4 {
                let length = u16::from_be_bytes([self.header[2], self.header[3]]) as usize;
                if length < 2 {
                    return Err(io::Error::other("Invalid JPEG segment length"));
                }
                if self.header[1] == 218 {
                    self.comments()?;
                    self.scanned = true;
                }
                self.output.write_all(&self.header)?;
                self.remaining = length - 2;
                self.used = 0;
            }
        }
        Ok(())
    }
    pub(super) fn finish(&mut self) -> Result<(), Error> {
        self.check().map_err(|_| error())?;
        if !self.scanned || self.remaining != 0 || self.used != 0 || self.tail != [255, 217] {
            return Err(error());
        }
        Ok(())
    }
}
impl<W: Write> Write for Stream<'_, W> {
    fn write(&mut self, data: &[u8]) -> io::Result<usize> {
        if let Err(error) = self.accept(data) {
            self.poisoned = true;
            return Err(error);
        }
        for byte in data.iter().rev().take(2).rev() {
            self.tail = [self.tail[1], *byte];
        }
        Ok(data.len())
    }
    fn flush(&mut self) -> io::Result<()> {
        self.check()?;
        if let Err(error) = self.output.flush() {
            self.poisoned = true;
            return Err(error);
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn split_headers_keep_exact_metadata_order_and_parts_without_buffering_segments() {
        let packet = "x".repeat(60001);
        let input = [
            255, 216, 255, 224, 0, 7, 1, 2, 255, 218, 4, 255, 218, 0, 2, 19, 255, 0, 23, 255, 217,
        ];
        let mut expected = input[..11].to_vec();
        for (index, part) in packet.as_bytes().chunks(60000).enumerate() {
            expected.extend([255, 254]);
            expected.extend(((19 + part.len()) as u16).to_be_bytes());
            expected.extend(b"INKBOLT-META\0");
            expected.extend(((index + 1) as u16).to_be_bytes());
            expected.extend(2u16.to_be_bytes());
            expected.extend(part);
        }
        expected.extend(&input[11..]);
        for chunk in 1..=input.len() {
            let control = Control::default();
            let failure = RefCell::new(None);
            let mut output = Vec::new();
            let mut stream = Stream::new(&mut output, Some(&packet), &control, &failure).unwrap();
            for part in input.chunks(chunk) {
                stream.write_all(part).unwrap();
            }
            stream.finish().unwrap();
            assert_eq!(output.len(), expected.len());
            assert_eq!(output.iter().zip(&expected).position(|(a, b)| a != b), None);
        }
    }
    #[test]
    fn missing_scan_truncated_segment_or_missing_end_cannot_finish() {
        for input in [
            &[255, 216][..],
            &[255, 216, 255, 224, 0, 1],
            &[255, 216, 255, 224, 0, 5, 9],
            &[255, 216, 255, 218, 0, 2, 1, 2],
            &[255, 216, 255, 217],
        ] {
            let control = Control::default();
            let failure = RefCell::new(None);
            let mut output = Vec::new();
            let mut stream = Stream::new(&mut output, None, &control, &failure).unwrap();
            let write = stream.write_all(input);
            assert!(write.is_err() || stream.finish().is_err());
        }
    }
    #[test]
    fn cancellation_between_small_writes_is_checked_at_chunk_boundary_and_finish() {
        for finish in [false, true] {
            let control = Control::default();
            let failure = RefCell::new(None);
            let mut output = Vec::new();
            let mut stream = Stream::new(&mut output, None, &control, &failure).unwrap();
            stream
                .write_all(&[255, 216, 255, 218, 0, 2, 19, 255, 217])
                .unwrap();
            if !finish {
                // This large write itself crosses the first check boundary.
                // Its bytes must count toward the following check as well.
                stream
                    .write_all(&vec![
                        0;
                        crate::limits::jpeg_output::STREAM_BUFFER_BYTES - 9
                    ])
                    .unwrap();
            }
            control.cancel();
            if finish {
                assert!(stream.finish().is_err());
            } else {
                assert!(stream.write_all(&[0; 16]).is_err());
            }
            assert_eq!(failure.borrow().as_ref().unwrap().code, "CANCELLED");
            assert_eq!(
                output.len(),
                if finish {
                    9
                } else {
                    crate::limits::jpeg_output::STREAM_BUFFER_BYTES
                }
            );
        }
    }
}
