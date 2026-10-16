//! Strict entropy syntax admission from public T.81 Annexes B, C, F and G.
//! Track only nonzero-coefficient occupancy, never sample or coefficient values.
use super::{
    framing::{Framing, Plan},
    malformed,
};
use crate::{Error, control::Control};
use std::io::{Read, Seek};

struct Huffman {
    first: [u32; 16],
    counts: [u8; 16],
    offsets: [usize; 16],
    symbols: Vec<u8>,
}
impl Huffman {
    fn new(counts: &[u8], symbols: &[u8]) -> Result<Self, Error> {
        if counts.len() != 16 || symbols.is_empty() || symbols.len() > 256 {
            return Err(malformed());
        }
        let mut result = Self {
            first: [0; 16],
            counts: counts.try_into().unwrap(),
            offsets: [0; 16],
            symbols: symbols.to_vec(),
        };
        let (mut code, mut offset) = (0u32, 0usize);
        for (index, &count) in counts.iter().enumerate() {
            result.first[index] = code;
            result.offsets[index] = offset;
            code += u32::from(count);
            // Prefixes must fit, and JPEG reserves the all-ones code for padding.
            if code >= (1 << (index + 1)) {
                return Err(malformed());
            }
            offset += usize::from(count);
            code <<= 1;
        }
        if offset != symbols.len() {
            return Err(malformed());
        }
        Ok(result)
    }
    fn symbol<R: Read + Seek>(&self, bits: &mut Bits<'_, '_, R>) -> Result<u8, Error> {
        let mut code = 0;
        for index in 0..16 {
            code = (code << 1) | u32::from(bits.take(1)?);
            if let Some(delta) = code.checked_sub(self.first[index])
                && delta < u32::from(self.counts[index])
            {
                return Ok(self.symbols[self.offsets[index] + delta as usize]);
            }
        }
        Err(malformed())
    }
}

#[derive(Default)]
struct Tables {
    dc: [Option<Huffman>; 4],
    ac: [Option<Huffman>; 4],
}
impl Tables {
    fn define(&mut self, mut bytes: &[u8]) -> Result<(), Error> {
        if bytes.is_empty() {
            return Err(malformed());
        }
        while !bytes.is_empty() {
            let header = bytes.get(..17).ok_or_else(malformed)?;
            let (class, destination) = (header[0] >> 4, usize::from(header[0] & 15));
            if class > 1 || destination > 3 {
                return Err(malformed());
            }
            let count: usize = header[1..].iter().map(|n| usize::from(*n)).sum();
            let values = bytes.get(17..17 + count).ok_or_else(malformed)?;
            let table = Huffman::new(&header[1..], values)?;
            if class == 0 {
                self.dc[destination] = Some(table);
            } else {
                self.ac[destination] = Some(table);
            }
            bytes = &bytes[17 + count..];
        }
        Ok(())
    }
}

struct Bits<'a, 'b, R> {
    reader: &'a mut Framing<'b, R>,
    byte: u8,
    remaining: u8,
}
impl<R: Read + Seek> Bits<'_, '_, R> {
    fn take(&mut self, count: u8) -> Result<u16, Error> {
        let mut result = 0u16;
        for _ in 0..count {
            if self.remaining == 0 {
                self.byte = self.reader.byte()?;
                if self.byte == 255 && self.reader.byte()? != 0 {
                    // Never manufacture padding bits when a marker arrives early.
                    return Err(malformed());
                }
                self.remaining = 8;
            }
            self.remaining -= 1;
            result = (result << 1) | u16::from((self.byte >> self.remaining) & 1);
        }
        Ok(result)
    }
    fn boundary(&mut self) -> Result<u8, Error> {
        let mask = ((1u16 << self.remaining) - 1) as u8;
        if self.byte & mask != mask {
            return Err(malformed());
        }
        self.remaining = 0;
        self.reader.marker()
    }
}

struct Component {
    id: u8,
    horizontal: usize,
    vertical: usize,
    stride: usize,
    actual_width: usize,
    actual_height: usize,
    approximation: [Option<u8>; 64],
    nonzero: Vec<u64>,
}
struct Frame {
    progressive: bool,
    across: usize,
    down: usize,
    components: Vec<Component>,
}
impl Frame {
    fn new(body: &[u8], plan: &Plan) -> Result<Self, Error> {
        if body.len() != 6 + 3 * plan.channels
            || body[0] != 8
            || u32::from(u16::from_be_bytes([body[1], body[2]])) != plan.height
            || u32::from(u16::from_be_bytes([body[3], body[4]])) != plan.width
            || usize::from(body[5]) != plan.channels
        {
            return Err(malformed());
        }
        let definitions = body[6..].as_chunks::<3>().0;
        if definitions
            .iter()
            .any(|c| !(1..=4).contains(&(c[1] >> 4)) || !(1..=4).contains(&(c[1] & 15)))
        {
            return Err(malformed());
        }
        let max_h = usize::from(
            definitions
                .iter()
                .map(|c| c[1] >> 4)
                .max()
                .ok_or_else(malformed)?,
        );
        let max_v = usize::from(
            definitions
                .iter()
                .map(|c| c[1] & 15)
                .max()
                .ok_or_else(malformed)?,
        );
        let across = (plan.width as usize).div_ceil(max_h * 8);
        let down = (plan.height as usize).div_ceil(max_v * 8);
        let components = definitions
            .iter()
            .map(|c| {
                let h = usize::from(c[1] >> 4);
                let v = usize::from(c[1] & 15);
                Component {
                    id: c[0],
                    horizontal: h,
                    vertical: v,
                    stride: across * h,
                    actual_width: (plan.width as usize * h).div_ceil(max_h * 8),
                    actual_height: (plan.height as usize * v).div_ceil(max_v * 8),
                    approximation: [None; 64],
                    // One bit per coefficient, released before the pixel decoder starts.
                    nonzero: if plan.progressive {
                        vec![0; across * h * down * v]
                    } else {
                        Vec::new()
                    },
                }
            })
            .collect();
        Ok(Self {
            progressive: plan.progressive,
            across,
            down,
            components,
        })
    }

    fn scan<R: Read + Seek>(
        &mut self,
        body: &[u8],
        tables: &Tables,
        restart: usize,
        reader: &mut Framing<'_, R>,
        control: &Control,
    ) -> Result<u8, Error> {
        let count = usize::from(*body.first().ok_or_else(malformed)?);
        if count == 0 || count > self.components.len() || body.len() != 1 + count * 2 + 3 {
            return Err(malformed());
        }
        let tail = &body[1 + count * 2..];
        let band = Band {
            first: usize::from(tail[0]),
            last: usize::from(tail[1]),
            high: tail[2] >> 4,
            low: tail[2] & 15,
            progressive: self.progressive,
        };
        if band.first > band.last || band.last > 63 || band.high > 13 || band.low > 13 {
            return Err(malformed());
        }
        if self.progressive {
            if (band.first == 0 && band.last != 0)
                || (band.first != 0 && count != 1)
                || (band.high != 0 && band.high != band.low + 1)
            {
                return Err(malformed());
            }
        } else if (band.first, band.last, band.high, band.low) != (0, 63, 0, 0) {
            return Err(malformed());
        }
        let mut selected = Vec::new();
        for pair in body[1..1 + count * 2].as_chunks::<2>().0 {
            let index = self
                .components
                .iter()
                .position(|c| c.id == pair[0])
                .ok_or_else(malformed)?;
            if selected.last().is_some_and(|&(i, _, _)| i >= index) {
                return Err(malformed());
            }
            let (dc, ac) = (usize::from(pair[1] >> 4), usize::from(pair[1] & 15));
            if dc > 3 || ac > 3 || (!self.progressive && (dc > 1 || ac > 1)) {
                return Err(malformed());
            }
            let component = &self.components[index];
            if band.first > 0 && component.approximation[0].is_none() {
                return Err(malformed());
            }
            for previous in &component.approximation[band.first..=band.last] {
                if (band.high == 0 && previous.is_some())
                    || (band.high != 0 && *previous != Some(band.high))
                {
                    return Err(malformed());
                }
            }
            if band.first == 0 && band.high == 0 && tables.dc[dc].is_none()
                || (band.last != 0 && tables.ac[ac].is_none())
            {
                return Err(malformed());
            }
            selected.push((index, dc, ac));
        }
        if count > 1
            && selected
                .iter()
                .map(|&(i, _, _)| self.components[i].horizontal * self.components[i].vertical)
                .sum::<usize>()
                > 10
        {
            return Err(malformed());
        }
        let (across, down) = if count > 1 {
            (self.across, self.down)
        } else {
            let component = &self.components[selected[0].0];
            (component.actual_width, component.actual_height)
        };
        let mut bits = Bits {
            reader,
            byte: 0,
            remaining: 0,
        };
        let mut eob = 0;
        let mut restart_index = 0;
        for mcu in 0..across * down {
            control.check()?;
            if restart != 0 && mcu != 0 && mcu % restart == 0 {
                if eob != 0 || bits.boundary()? != 0xd0 + restart_index {
                    return Err(malformed());
                }
                restart_index = (restart_index + 1) & 7;
            }
            for &(index, dc, ac) in &selected {
                let component = &mut self.components[index];
                let (h, v) = if count > 1 {
                    (component.horizontal, component.vertical)
                } else {
                    (1, 1)
                };
                for dy in 0..v {
                    for dx in 0..h {
                        let block =
                            ((mcu / across) * v + dy) * component.stride + (mcu % across) * h + dx;
                        let mut sequential = 0;
                        let occupancy = if self.progressive {
                            component.nonzero.get_mut(block).ok_or_else(malformed)?
                        } else {
                            &mut sequential
                        };
                        band.block(
                            &mut bits,
                            tables.dc[dc].as_ref(),
                            tables.ac[ac].as_ref(),
                            occupancy,
                            &mut eob,
                        )?;
                    }
                }
            }
        }
        if eob != 0 {
            return Err(malformed());
        }
        let mut marker = bits.boundary()?;
        // Tolerate one correctly numbered terminal restart at an exact boundary.
        if restart != 0 && (across * down) % restart == 0 && marker == 0xd0 + restart_index {
            marker = bits.reader.marker()?;
        }
        for (index, _, _) in selected {
            self.components[index].approximation[band.first..=band.last].fill(Some(band.low));
        }
        Ok(marker)
    }
    fn finish(&self) -> Result<(), Error> {
        if self.components.iter().any(|c| c.approximation[0].is_none()) {
            return Err(malformed());
        }
        Ok(())
    }
}

struct Band {
    first: usize,
    last: usize,
    high: u8,
    low: u8,
    progressive: bool,
}
impl Band {
    fn block<R: Read + Seek>(
        &self,
        bits: &mut Bits<'_, '_, R>,
        dc: Option<&Huffman>,
        ac: Option<&Huffman>,
        occupancy: &mut u64,
        eob: &mut u16,
    ) -> Result<(), Error> {
        if self.first == 0 {
            if self.high == 0 {
                let size = dc.ok_or_else(malformed)?.symbol(bits)?;
                if size > 11 {
                    return Err(malformed());
                }
                bits.take(size)?;
            } else {
                bits.take(1)?;
            }
            if self.last == 0 {
                return Ok(());
            }
        }
        let table = ac.ok_or_else(malformed)?;
        let mut position = self.first.max(1);
        if self.high == 0 {
            if *eob != 0 {
                *eob -= 1;
                return Ok(());
            }
            while position <= self.last {
                let symbol = table.symbol(bits)?;
                let (run, size) = (usize::from(symbol >> 4), symbol & 15);
                if size == 0 {
                    if run == 15 {
                        position += 16;
                    } else if self.progressive {
                        *eob = (1u16 << run) + bits.take(run as u8)? - 1;
                        break;
                    } else if run == 0 {
                        break;
                    } else {
                        return Err(malformed());
                    }
                } else {
                    position += run;
                    if size > 10 || position > self.last {
                        return Err(malformed());
                    }
                    bits.take(size)?;
                    *occupancy |= 1u64 << position;
                    position += 1;
                }
                if position > self.last + 1 {
                    return Err(malformed());
                }
            }
        } else {
            if *eob == 0 {
                while position <= self.last {
                    let symbol = table.symbol(bits)?;
                    let (run, size) = (symbol >> 4, symbol & 15);
                    if size > 1 {
                        return Err(malformed());
                    }
                    if size == 0 && run != 15 {
                        *eob = (1u16 << run) + bits.take(run)?;
                        break;
                    }
                    if size == 1 {
                        bits.take(1)?;
                    }
                    let mut zeros = if size == 0 { 16 } else { run };
                    while position <= self.last {
                        if *occupancy & (1u64 << position) != 0 {
                            bits.take(1)?;
                        } else if zeros == 0 {
                            break;
                        } else {
                            zeros -= 1;
                            if zeros == 0 && size == 0 {
                                position += 1;
                                break;
                            }
                        }
                        position += 1;
                    }
                    if zeros != 0 {
                        return Err(malformed());
                    }
                    if size == 1 {
                        if position > self.last {
                            return Err(malformed());
                        }
                        *occupancy |= 1u64 << position;
                        position += 1;
                    }
                }
            }
            if *eob != 0 {
                for coefficient in position..=self.last {
                    if *occupancy & (1u64 << coefficient) != 0 {
                        bits.take(1)?;
                    }
                }
                *eob -= 1;
            }
        }
        Ok(())
    }
}

pub(super) fn validate<R: Read + Seek>(
    input: &mut R,
    length: u64,
    plan: &Plan,
    control: &Control,
) -> Result<(), Error> {
    input.rewind().map_err(|_| malformed())?;
    let mut reader = Framing::new(input, length, control);
    if reader.marker()? != 0xd8 {
        return Err(malformed());
    }
    let mut tables = Tables::default();
    let mut frame = None;
    let mut restart = 0;
    let mut pending = None;
    loop {
        control.check()?;
        let marker = match pending.take() {
            Some(marker) => marker,
            None => reader.marker()?,
        };
        if marker == 0xd9 {
            if reader.position != length {
                return Err(malformed());
            }
            return frame.as_ref().ok_or_else(malformed).and_then(Frame::finish);
        }
        let body = reader.segment()?;
        match marker {
            0xc0 | 0xc2 => {
                if frame.is_some() {
                    return Err(malformed());
                }
                frame = Some(Frame::new(&body, plan)?);
            }
            0xc4 => tables.define(&body)?,
            0xdd => {
                if body.len() != 2 {
                    return Err(malformed());
                }
                restart = usize::from(u16::from_be_bytes(body.try_into().unwrap()));
            }
            0xda => {
                pending = Some(frame.as_mut().ok_or_else(malformed)?.scan(
                    &body,
                    &tables,
                    restart,
                    &mut reader,
                    control,
                )?)
            }
            0xdb | 0xe0..=0xef | 0xfe => {}
            _ => return Err(malformed()),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{self, Cursor, SeekFrom};

    struct CancelAt {
        input: Cursor<Vec<u8>>,
        at: u64,
        control: Control,
    }
    impl Read for CancelAt {
        fn read(&mut self, output: &mut [u8]) -> io::Result<usize> {
            let size = output.len().min(1);
            let n = self.input.read(&mut output[..size])?;
            if self.input.position() == self.at {
                self.control.cancel();
            }
            Ok(n)
        }
    }
    impl Seek for CancelAt {
        fn seek(&mut self, from: SeekFrom) -> io::Result<u64> {
            self.input.seek(from)
        }
    }
    #[test]
    fn cancellation_during_entropy_stops_before_another_data_unit() {
        fn segment(out: &mut Vec<u8>, marker: u8, body: &[u8]) {
            out.extend_from_slice(&[255, marker]);
            out.extend_from_slice(&((body.len() + 2) as u16).to_be_bytes());
            out.extend_from_slice(body);
        }
        // Original 17x9 neutral grayscale: six DC-zero/AC-EOB blocks.
        let mut data = vec![255, 0xd8];
        let mut quant = vec![1; 65];
        quant[0] = 0;
        segment(&mut data, 0xdb, &quant);
        let mut tables = Vec::new();
        for class in [0, 16] {
            tables.extend_from_slice(&[class, 1]);
            tables.extend_from_slice(&[0; 15]);
            tables.push(0);
        }
        segment(&mut data, 0xc4, &tables);
        segment(&mut data, 0xc0, &[8, 0, 9, 0, 17, 1, 1, 17, 0]);
        segment(&mut data, 0xda, &[1, 1, 0, 0, 63, 0]);
        let at = data.len() as u64 + 1;
        data.extend_from_slice(&[0, 15, 255, 0xd9]);
        let length = data.len() as u64;
        let plan =
            super::super::framing::inspect(Cursor::new(&data), length, 65536, &Control::default())
                .unwrap();
        validate(&mut Cursor::new(&data), length, &plan, &Control::default()).unwrap();
        let control = Control::default();
        let mut reader = CancelAt {
            input: Cursor::new(data),
            at,
            control: control.clone(),
        };
        let error = validate(&mut reader, length, &plan, &control).unwrap_err();
        assert_eq!(error.code, "CANCELLED");
        assert_eq!(reader.input.position(), at);
    }
}
