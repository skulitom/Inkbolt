//! Hash a seekable encoding without retaining its appended payload or creating files.
use super::*;
use std::{collections::BTreeMap, io::SeekFrom};

/// Only overwritten bytes survive the first pass. Entries are disjoint and
/// coalesced; merging may temporarily retain one extra journal's worth of bytes.
#[derive(Default)]
struct Patches {
    entries: BTreeMap<u64, Box<[u8]>>,
    bytes: usize,
}
impl Patches {
    fn insert(&mut self, at: u64, data: &[u8]) -> Result<(), Error> {
        if data.is_empty() {
            return Ok(());
        }
        let end = at + data.len() as u64;
        let start = self
            .entries
            .range(..=at)
            .next_back()
            .filter(|(p, v)| **p + v.len() as u64 >= at)
            .map_or(at, |(p, _)| *p);
        let mut stop = end;
        let mut replaced_bytes = 0;
        let mut replaced_entries = 0;
        for (&p, v) in self.entries.range(start..=end) {
            stop = stop.max(p + v.len() as u64);
            replaced_bytes += v.len();
            replaced_entries += 1;
        }
        let length = (stop - start) as usize;
        let bytes = self.bytes - replaced_bytes + length;
        let entries = self.entries.len() - replaced_entries + 1;
        if bytes > limits::MAX_PREFLIGHT_PATCH_BYTES || entries > limits::MAX_PREFLIGHT_PATCHES {
            return Err(limit(
                "Seekable preflight backpatch journal exceeds its memory bound",
            ));
        }
        let mut merged = vec![0; length];
        for (&p, v) in self.entries.range(start..=end) {
            let offset = (p - start) as usize;
            merged[offset..offset + v.len()].copy_from_slice(v);
        }
        merged[(at - start) as usize..(end - start) as usize].copy_from_slice(data);
        while let Some((&p, _)) = self.entries.range(start..=end).next() {
            self.entries.remove(&p);
        }
        self.entries.insert(start, merged.into_boxed_slice());
        self.bytes = bytes;
        Ok(())
    }
    fn apply(&self, at: u64, data: &mut [u8]) {
        let end = at + data.len() as u64;
        let start = self
            .entries
            .range(..=at)
            .next_back()
            .map_or(at, |(p, _)| *p);
        for (&p, v) in self.entries.range(start..end) {
            let left = p.max(at);
            let right = (p + v.len() as u64).min(end);
            if left < right {
                data[(left - at) as usize..(right - at) as usize]
                    .copy_from_slice(&v[(left - p) as usize..(right - p) as usize]);
            }
        }
    }
}

pub(crate) struct Projection<'a> {
    control: &'a Control,
    patches: Patches,
    position: u64,
    len: u64,
    maximum: u64,
    transcript: Sha256,
    expected: Option<[u8; 32]>,
    hash: Sha256,
    error: Option<Error>,
}
impl<'a> Projection<'a> {
    pub fn new(control: &'a Control) -> Self {
        Self {
            control,
            patches: Patches::default(),
            position: 0,
            len: 0,
            maximum: limits::MAX_OUTPUT_BYTES as u64,
            transcript: Sha256::new(),
            expected: None,
            hash: Sha256::new(),
            error: None,
        }
    }
    fn check(&mut self) -> io::Result<()> {
        if self.error.is_some() {
            return Err(io::Error::other("Seekable preflight already failed"));
        }
        self.control.check().map_err(|e| self.fail(e))
    }
    fn fail(&mut self, error: Error) -> io::Error {
        if self.error.is_none() {
            self.error = Some(error);
        }
        io::Error::other("Seekable preflight rejected")
    }
    fn identity(&self) -> [u8; 32] {
        let mut hash = self.transcript.clone();
        hash.update(self.position.to_le_bytes());
        hash.update(self.len.to_le_bytes());
        hash.finalize().into()
    }
    pub fn encoded(&mut self, result: Result<(), Error>) -> Result<(), Error> {
        if let Some(error) = self.error.take() {
            return Err(error);
        }
        self.control.check()?;
        result
    }
    /// Consume the first pass; renderer state must be retained by the caller.
    pub fn replay(mut self) -> Result<Self, Error> {
        if let Some(error) = self.error.take() {
            return Err(error);
        }
        self.control.check()?;
        if self.expected.is_some() {
            return Err(mismatch());
        }
        self.expected = Some(self.identity());
        self.transcript = Sha256::new();
        self.position = 0;
        self.len = 0;
        Ok(self)
    }
    pub fn finish(mut self) -> Result<Payload, Error> {
        if let Some(error) = self.error.take() {
            return Err(error);
        }
        self.control.check()?;
        if self.expected != Some(self.identity()) {
            return Err(mismatch());
        }
        Ok(Payload {
            storage: Storage::Discard,
            len: self.len as usize,
            sha256: format!("{:x}", self.hash.finalize()),
        })
    }
    /// Final bytes in an extent's first visit can already include later patches.
    fn hash_extent(&mut self, start: u64, end: u64, source: Option<&[u8]>) -> io::Result<()> {
        let mut buffer = [0; limits::IO_CHUNK_BYTES];
        let mut at = start;
        while at < end {
            self.check()?;
            let count = (end - at).min(buffer.len() as u64) as usize;
            let chunk = &mut buffer[..count];
            if let Some(source) = source {
                let offset = (at - start) as usize;
                chunk.copy_from_slice(&source[offset..offset + count]);
            } else {
                chunk.fill(0);
            }
            self.patches.apply(at, chunk);
            self.hash.update(chunk);
            at += count as u64;
        }
        Ok(())
    }
}
fn mismatch() -> Error {
    Error::new(
        "EXPORT_ERROR",
        "Seekable preflight encoding changed between passes",
    )
}
impl Write for Projection<'_> {
    fn write(&mut self, data: &[u8]) -> io::Result<usize> {
        self.check()?;
        if data.len() as u64 > self.maximum.saturating_sub(self.position) {
            return Err(self.fail(limit("Encoded output exceeds publication byte limit")));
        }
        self.transcript.update([0]);
        self.transcript.update(self.position.to_le_bytes());
        self.transcript.update((data.len() as u64).to_le_bytes());
        for chunk in data.chunks(limits::IO_CHUNK_BYTES) {
            self.check()?;
            self.transcript.update(chunk);
        }
        if data.is_empty() {
            return Ok(0);
        }
        let end = self.position + data.len() as u64;
        if self.expected.is_none() {
            let count = self
                .len
                .saturating_sub(self.position)
                .min(data.len() as u64) as usize;
            self.patches
                .insert(self.position, &data[..count])
                .map_err(|e| self.fail(e))?;
        } else {
            if self.position > self.len {
                self.hash_extent(self.len, self.position, None)?;
            }
            let start = self.position.max(self.len);
            if start < end {
                self.hash_extent(start, end, Some(&data[(start - self.position) as usize..]))?;
            }
        }
        self.position = end;
        self.len = self.len.max(end);
        Ok(data.len())
    }
    fn flush(&mut self) -> io::Result<()> {
        self.check()?;
        self.transcript.update([1]);
        Ok(())
    }
}
impl Seek for Projection<'_> {
    fn seek(&mut self, from: SeekFrom) -> io::Result<u64> {
        self.check()?;
        let (tag, argument, position) = match from {
            SeekFrom::Start(p) => (2, p, Some(p)),
            SeekFrom::Current(p) => (3, p as u64, self.position.checked_add_signed(p)),
            SeekFrom::End(p) => (4, p as u64, self.len.checked_add_signed(p)),
        };
        let Some(position) = position.filter(|p| *p <= self.maximum) else {
            return Err(self.fail(limit("Encoded output seek exceeds publication byte limit")));
        };
        self.transcript.update([tag]);
        self.transcript.update(argument.to_le_bytes());
        self.position = position;
        Ok(position)
    }
}

#[cfg(test)]
mod tests;
