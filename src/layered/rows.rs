//! Bounded channel decoding: encoded input is borrowed, only one decoded row is retained.
use super::{Version, binary::Reader, malformed, unsupported};
use crate::{Error, control::Control};
use sha2::{Digest, Sha256};

pub(super) struct Rows<'a> {
    input: Reader<'a>,
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
        bytes: &'a [u8],
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
        let mut input = Reader::new(bytes);
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
                &self.input.data[self.input.at..],
                output,
                flate2::FlushDecompress::None,
            )
            .map_err(|_| malformed())?;
        let consumed = (decoder.total_in() - before_in) as usize;
        let produced = (decoder.total_out() - before_out) as usize;
        self.input.take(consumed)?;
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
            0 => output.copy_from_slice(self.input.take(self.width)?),
            1 => {
                let mut row = Reader::new(self.input.take(self.sizes[self.at])?);
                let mut at = 0;
                while row.left() != 0 {
                    control.check()?;
                    let code = row.byte()?;
                    let count = match code {
                        0..=127 => code as usize + 1,
                        129..=255 => 257 - code as usize,
                        _ => 0,
                    };
                    let target = output.get_mut(at..at + count).ok_or_else(malformed)?;
                    if code <= 127 {
                        target.copy_from_slice(row.take(count)?);
                    } else if code != 128 {
                        target.fill(row.byte()?);
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
        let padding = self.input.left();
        if embedded {
            self.input.zero_padding(1024 * 1024)?;
        } else {
            self.input.end()?;
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
}
