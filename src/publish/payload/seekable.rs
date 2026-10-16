//! Codec backpatches stay private until the final extent and bytes are verified.
use super::*;
use std::io::SeekFrom;

enum Target {
    Memory(Cursor<Vec<u8>>),
    Private(File),
}

pub(crate) struct SeekSink<'a> {
    target: Target,
    position: u64,
    len: u64,
    maximum: u64,
    control: &'a Control,
    error: Option<Error>,
}
impl<'a> SeekSink<'a> {
    fn new(target: Target, control: &'a Control) -> Self {
        Self {
            target,
            position: 0,
            len: 0,
            maximum: limits::MAX_OUTPUT_BYTES as u64,
            control,
            error: None,
        }
    }
    pub fn memory(control: &'a Control) -> Self {
        Self::new(Target::Memory(Cursor::new(Vec::new())), control)
    }
    pub fn publication(retain: bool, control: &'a Control) -> Result<Self, Error> {
        if retain {
            let mut sink = Self::new(Target::Private(private_file(control)?), control);
            sink.maximum = limits::MAX_FILE_IMAGE_BYTES as u64;
            Ok(sink)
        } else {
            Ok(Self::memory(control))
        }
    }
    fn fail(&mut self, error: Error) -> io::Error {
        if self.error.is_none() {
            self.error = Some(error);
        }
        io::Error::other("Seekable encoded output rejected")
    }
    fn check(&mut self) -> io::Result<()> {
        if self.error.is_some() {
            return Err(io::Error::other("Seekable encoded output already failed"));
        }
        self.control.check().map_err(|error| self.fail(error))
    }
    pub fn finish(mut self) -> Result<Payload, Error> {
        if let Some(error) = self.error {
            return Err(error);
        }
        self.control.check()?;
        let mut hash = Sha256::new();
        match &mut self.target {
            Target::Memory(cursor) => {
                if cursor.get_ref().len() as u64 != self.len {
                    return Err(io_error());
                }
                for chunk in cursor.get_ref().chunks(limits::IO_CHUNK_BYTES) {
                    self.control.check()?;
                    hash.update(chunk);
                }
            }
            Target::Private(file) => {
                file.rewind().map_err(|_| io_error())?;
                let mut buffer = vec![0; limits::IO_CHUNK_BYTES];
                let mut read = 0u64;
                loop {
                    self.control.check()?;
                    let count = file.read(&mut buffer).map_err(|_| io_error())?;
                    if count == 0 {
                        break;
                    }
                    read += count as u64;
                    if read > self.len {
                        return Err(io_error());
                    }
                    hash.update(&buffer[..count]);
                }
                if read != self.len {
                    return Err(io_error());
                }
            }
        }
        self.control.check()?;
        Ok(Payload {
            storage: match self.target {
                Target::Memory(cursor) => Storage::Memory(cursor.into_inner()),
                Target::Private(file) => Storage::Private(file),
            },
            len: self.len as usize,
            sha256: format!("{:x}", hash.finalize()),
        })
    }
}
impl Write for SeekSink<'_> {
    fn write(&mut self, data: &[u8]) -> io::Result<usize> {
        self.check()?;
        if data.len() as u64 > self.maximum.saturating_sub(self.position) {
            return Err(self.fail(limit("Encoded output exceeds publication byte limit")));
        }
        // A zero-byte write must not allocate a hole or increase the extent.
        if data.is_empty() {
            return Ok(0);
        }
        let count = match &mut self.target {
            Target::Memory(cursor) => cursor.write(data),
            Target::Private(file) => file.write(data),
        }
        .map_err(|_| self.fail(io_error()))?;
        self.position += count as u64;
        self.len = self.len.max(self.position);
        Ok(count)
    }
    fn flush(&mut self) -> io::Result<()> {
        self.check()?;
        match &mut self.target {
            Target::Memory(cursor) => cursor.flush(),
            Target::Private(file) => file.flush(),
        }
        .map_err(|_| self.fail(io_error()))
    }
}
impl Seek for SeekSink<'_> {
    fn seek(&mut self, at: SeekFrom) -> io::Result<u64> {
        self.check()?;
        let position = match at {
            SeekFrom::Start(position) => Some(position),
            SeekFrom::Current(offset) => self.position.checked_add_signed(offset),
            SeekFrom::End(offset) => self.len.checked_add_signed(offset),
        };
        let Some(position) = position.filter(|&value| value <= self.maximum) else {
            return Err(self.fail(limit("Encoded output seek exceeds publication byte limit")));
        };
        let actual = match &mut self.target {
            Target::Memory(cursor) => cursor.seek(SeekFrom::Start(position)),
            Target::Private(file) => file.seek(SeekFrom::Start(position)),
        }
        .map_err(|_| self.fail(io_error()))?;
        if actual != position {
            return Err(self.fail(io_error()));
        }
        self.position = position;
        Ok(position)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn file_extent_has_a_separate_bound_and_failed_seek_keeps_payload_private() {
        let control = Control::default();
        let position = limits::MAX_OUTPUT_BYTES as u64 + 1;
        let mut inline = SeekSink::memory(&control);
        assert!(inline.seek(SeekFrom::Start(position)).is_err());
        assert_eq!(inline.finish().err().unwrap().code, "RESOURCE_LIMIT");
        let mut file = SeekSink::publication(true, &control).unwrap();
        file.seek(SeekFrom::Start(limits::MAX_FILE_IMAGE_BYTES as u64 - 1))
            .unwrap();
        file.write_all(b"x").unwrap();
        assert_eq!(file.len, limits::MAX_FILE_IMAGE_BYTES as u64);
        assert!(file.write_all(b"y").is_err());
        assert_eq!(file.finish().err().unwrap().code, "RESOURCE_LIMIT");
    }
    #[test]
    fn backpatch_holes_and_empty_writes_keep_final_extent_and_exact_hash() {
        let control = Control::default();
        for mut sink in [
            SeekSink::memory(&control),
            SeekSink::publication(true, &control).unwrap(),
        ] {
            sink.maximum = 32;
            sink.write_all(b"header").unwrap();
            sink.seek(SeekFrom::Start(12)).unwrap();
            sink.write_all(b"pixels").unwrap();
            sink.seek(SeekFrom::Start(0)).unwrap();
            sink.write_all(b"FINAL!").unwrap();
            sink.seek(SeekFrom::End(-1)).unwrap();
            sink.write_all(b"S").unwrap();
            sink.seek(SeekFrom::Start(32)).unwrap();
            sink.write_all(b"").unwrap();
            assert_eq!(sink.len, 18);
            let expected = b"FINAL!\0\0\0\0\0\0pixelS";
            let mut payload = sink.finish().unwrap();
            assert_eq!(payload.len(), expected.len());
            assert_eq!(payload.sha256(), assets::sha256(expected));
            let mut output = Vec::new();
            payload.copy_to(&mut output, &control, |_| {}).unwrap();
            assert_eq!(output, expected);
        }
    }
    #[test]
    fn invalid_seeks_and_extending_writes_poison_without_allocating() {
        let control = Control::default();
        for at in [
            SeekFrom::Start(u64::MAX),
            SeekFrom::Current(-1),
            SeekFrom::End(i64::MAX),
        ] {
            let mut sink = SeekSink::memory(&control);
            assert!(sink.seek(at).is_err());
            assert!(sink.write_all(b"x").is_err());
            assert_eq!(sink.finish().err().unwrap().code, "RESOURCE_LIMIT");
        }
        let mut sink = SeekSink::memory(&control);
        sink.maximum = 8;
        sink.write_all(b"12345678").unwrap();
        sink.rewind().unwrap();
        sink.write_all(b"AB").unwrap();
        sink.seek(SeekFrom::End(0)).unwrap();
        assert!(sink.write_all(b"9").is_err());
        assert_eq!(sink.len, 8);
        assert_eq!(sink.finish().err().unwrap().code, "RESOURCE_LIMIT");
    }
    #[test]
    fn cancelled_backpatch_cannot_return_a_successful_payload() {
        let control = Control::default();
        let mut sink = SeekSink::memory(&control);
        sink.write_all(b"pending").unwrap();
        control.cancel();
        assert!(sink.rewind().is_err());
        assert!(sink.flush().is_err());
        assert_eq!(sink.finish().err().unwrap().code, "CANCELLED");
    }
    #[test]
    fn final_readback_rejects_changed_extent_and_cancelled_payload() {
        let control = Control::default();
        let mut sink = SeekSink::publication(true, &control).unwrap();
        sink.write_all(b"finished").unwrap();
        if let Target::Private(file) = &mut sink.target {
            file.set_len(3).unwrap();
        }
        assert_eq!(sink.finish().err().unwrap().code, "IO_ERROR");
        for private in [false, true] {
            let control = Control::default();
            let mut sink = SeekSink::publication(private, &control).unwrap();
            sink.write_all(b"finished").unwrap();
            control.cancel();
            assert_eq!(sink.finish().err().unwrap().code, "CANCELLED");
        }
    }
}
