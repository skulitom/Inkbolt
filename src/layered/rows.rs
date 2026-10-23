//! Bounded channel decoding from borrowed bytes or an immutable private file range.
use super::{Version, input::Plane, malformed, unsupported};
use crate::{Error, control::Control};
use sha2::{Digest, Sha256};
use std::io::{BufRead, Read};

struct Encoded<'a> {
    reader: Box<dyn BufRead + 'a>,
    at: usize,
    length: usize,
}
impl Encoded<'_> {
    fn read(&mut self, output: &mut [u8]) -> Result<(), Error> {
        let end = self
            .at
            .checked_add(output.len())
            .filter(|end| *end <= self.length)
            .ok_or_else(malformed)?;
        self.reader.read_exact(output).map_err(|_| malformed())?;
        self.at = end;
        Ok(())
    }
    fn byte(&mut self) -> Result<u8, Error> {
        let mut b = [0];
        self.read(&mut b)?;
        Ok(b[0])
    }
    fn short(&mut self) -> Result<u16, Error> {
        let mut b = [0; 2];
        self.read(&mut b)?;
        Ok(u16::from_be_bytes(b))
    }
    fn word(&mut self) -> Result<u32, Error> {
        let mut b = [0; 4];
        self.read(&mut b)?;
        Ok(u32::from_be_bytes(b))
    }
}

pub(super) struct Rows<'a> {
    input: Encoded<'a>,
    compression: u16,
    width: usize,
    rows: usize,
    at: usize,
    sizes: Vec<usize>,
    decoder: Option<flate2::Decompress>,
    ended: bool,
}

impl<'a> Rows<'a> {
    pub fn new(
        plane: Plane<'a>,
        width: usize,
        rows: usize,
        version: Version,
    ) -> Result<Self, Error> {
        if width > crate::model::MAX_DIMENSION as usize
            || rows > crate::model::MAX_DIMENSION as usize * 4
            || width
                .checked_mul(rows)
                .is_none_or(|n| n > crate::limits::layered::MAX_NATIVE_DECODED_BYTES)
        {
            return Err(crate::model::limit(
                "Layered channel exceeds bounded row decode work",
            ));
        }
        let (reader, length) = plane.reader();
        let mut input = Encoded {
            reader,
            length,
            at: 0,
        };
        let compression = input.short()?;
        if compression > 3 {
            return Err(unsupported("Unknown layered channel compression"));
        }
        let sizes = if compression == 1 {
            (0..rows)
                .map(|_| {
                    if version == Version::Large {
                        input.word().map(|n| n as usize)
                    } else {
                        input.short().map(usize::from)
                    }
                })
                .collect::<Result<Vec<_>, _>>()?
        } else {
            Vec::new()
        };
        Ok(Self {
            input,
            compression,
            width,
            rows,
            at: 0,
            sizes,
            decoder: (compression >= 2).then(|| flate2::Decompress::new(true)),
            ended: false,
        })
    }

    fn inflate(&mut self, output: &mut [u8]) -> Result<(usize, usize), Error> {
        let decoder = self.decoder.as_mut().ok_or_else(malformed)?;
        let before_in = decoder.total_in();
        let before_out = decoder.total_out();
        let status = decoder
            .decompress(
                self.input.reader.fill_buf().map_err(|_| malformed())?,
                output,
                flate2::FlushDecompress::None,
            )
            .map_err(|_| malformed())?;
        let consumed = (decoder.total_in() - before_in) as usize;
        let produced = (decoder.total_out() - before_out) as usize;
        self.input.reader.consume(consumed);
        self.input.at += consumed;
        self.ended = status == flate2::Status::StreamEnd;
        if consumed == 0 && produced == 0 && !self.ended {
            return Err(malformed());
        }
        Ok((consumed, produced))
    }

    pub fn row(&mut self, output: &mut [u8], control: &Control) -> Result<(), Error> {
        control.check()?;
        if output.len() != self.width || self.at >= self.rows {
            return Err(malformed());
        }
        match self.compression {
            0 => self.input.read(output)?,
            1 => {
                let end = self
                    .input
                    .at
                    .checked_add(self.sizes[self.at])
                    .filter(|end| *end <= self.input.length)
                    .ok_or_else(malformed)?;
                let mut at = 0;
                while self.input.at < end {
                    control.check()?;
                    let code = self.input.byte()?;
                    let count = match code {
                        0..=127 => code as usize + 1,
                        129..=255 => 257 - code as usize,
                        _ => 0,
                    };
                    let target = output.get_mut(at..at + count).ok_or_else(malformed)?;
                    if code <= 127 {
                        if count > end - self.input.at {
                            return Err(malformed());
                        }
                        self.input.read(target)?;
                    } else if code != 128 {
                        if self.input.at == end {
                            return Err(malformed());
                        }
                        target.fill(self.input.byte()?);
                    }
                    at += count;
                }
                if at != self.width {
                    return Err(malformed());
                }
            }
            2 | 3 => {
                let mut at = 0;
                while at < output.len() {
                    control.check()?;
                    if self.ended {
                        return Err(malformed());
                    }
                    at += self.inflate(&mut output[at..])?.1;
                }
                if self.compression == 3 {
                    for i in 1..output.len() {
                        output[i] = output[i].wrapping_add(output[i - 1]);
                    }
                }
            }
            _ => unreachable!(),
        }
        self.at += 1;
        Ok(())
    }

    pub fn finish(mut self, embedded: bool, control: &Control) -> Result<usize, Error> {
        if self.at != self.rows {
            return Err(malformed());
        }
        if self.decoder.is_some() {
            while !self.ended {
                control.check()?;
                if self.inflate(&mut [0])?.1 != 0 {
                    return Err(malformed());
                }
            }
        }
        let padding = self.input.length - self.input.at;
        if padding > if embedded { 1024 * 1024 } else { 0 } {
            return Err(malformed());
        }
        let mut buffer = vec![0; padding.min(crate::limits::sample_import::INPUT_BUFFER_BYTES)];
        while self.input.at < self.input.length {
            control.check()?;
            let size = buffer.len().min(self.input.length - self.input.at);
            self.input.read(&mut buffer[..size])?;
            if buffer[..size].iter().any(|b| *b != 0) {
                return Err(malformed());
            }
        }
        control.check()?;
        Ok(padding)
    }

    pub fn digest(mut self, embedded: bool, control: &Control) -> Result<(String, usize), Error> {
        let mut row = vec![0; self.width];
        let mut hash = Sha256::new();
        for _ in 0..self.rows {
            self.row(&mut row, control)?;
            hash.update(&row);
        }
        Ok((
            crate::render::hex(&hash.finalize()),
            self.finish(embedded, control)?,
        ))
    }

    pub fn collect(mut self, control: &Control) -> Result<Vec<u8>, Error> {
        let count = self
            .width
            .checked_mul(self.rows)
            .filter(|n| *n <= super::MAX_DECODED_BYTES)
            .ok_or_else(|| crate::model::limit("Inline layered samples exceed their byte bound"))?;
        let mut result = vec![0; count];
        for y in 0..self.rows {
            self.row(&mut result[y * self.width..(y + 1) * self.width], control)?;
        }
        self.finish(false, control)?;
        Ok(result)
    }
}
