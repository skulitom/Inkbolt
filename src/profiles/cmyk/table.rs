//! Original continuous bounded ICC lookup evaluation, from ICC.1 section 10.
use super::super::curves::{Curve, Reader};
use super::*;

const IDENTITY: [f64; 12] = [1., 0., 0., 0., 1., 0., 0., 0., 1., 0., 0., 0.];
enum Stage {
    Curves(Vec<Curve>),
    Matrix([f64; 12]),
    Clut {
        grid: Vec<usize>,
        outputs: usize,
        values: Vec<f64>,
    },
}
pub(crate) struct Table {
    stages: Vec<Stage>,
    pub legacy_lab: bool,
    pub lab: bool,
    outputs: usize,
    inputs: usize,
    pub signature: [u8; 4],
}
impl Table {
    pub fn new(bytes: &[u8], forward: bool) -> Result<Option<Self>, Error> {
        Self::with_intent(bytes, forward, Intent::RelativeColorimetric)
    }
    pub fn with_intent(bytes: &[u8], forward: bool, intent: Intent) -> Result<Option<Self>, Error> {
        let mut selected = None;
        let mut signature = [0; 4];
        let suffixes: &[u8] = match intent {
            Intent::RelativeColorimetric | Intent::AbsoluteColorimetric => b"10",
            Intent::Perceptual => b"0",
            Intent::Saturation => b"20",
        };
        // These callers have already validated the complete profile framing.
        for &suffix in suffixes {
            let name = [
                if forward { b'A' } else { b'B' },
                b'2',
                if forward { b'B' } else { b'A' },
                suffix,
            ];
            for at in (132..132 + word(bytes, 128)? * 12).step_by(12) {
                if bytes[at..at + 4] == name {
                    let offset = word(bytes, at + 4)?;
                    selected = Some(&bytes[offset..offset + word(bytes, at + 8)?]);
                    signature = name;
                    break;
                }
            }
            if selected.is_some() {
                break;
            }
        }
        let Some(tag) = selected else {
            return Ok(None);
        };
        let channels = match &bytes[16..20] {
            b"RGB " => 3,
            b"CMYK" => 4,
            b"GRAY" => 1,
            _ => return Err(invalid()),
        };
        let inputs = if forward { channels } else { 3 };
        let outputs = if forward { 3 } else { channels };
        let lab = &bytes[20..24] == b"Lab ";
        let mut reader = Reader {
            data: tag,
            ranges: Vec::new(),
        };
        if reader.bytes(4, 4)? != [0; 4] || reader.bytes(8, 2)? != [inputs as u8, outputs as u8] {
            return Err(invalid());
        }
        let mut stages = Vec::new();
        let classic = matches!(reader.bytes(0, 4)?, b"mft1" | b"mft2");
        if classic {
            let eight = &tag[..4] == b"mft1";
            if eight && !lab {
                return Err(Error::new(
                    "UNSUPPORTED",
                    "Native preparation rejects ambiguous eight-bit XYZ connection tables",
                ));
            }
            if reader.bytes(11, 1)? != [0] {
                return Err(invalid());
            }
            let mut matrix = IDENTITY;
            for (i, v) in matrix[..9].iter_mut().enumerate() {
                *v = reader.fixed(12 + i * 4)?;
            }
            if (forward || lab) && matrix != IDENTITY {
                return Err(invalid());
            }
            if !forward && !lab {
                stages.push(Stage::Matrix(matrix));
            }
            let grid = vec![reader.bytes(10, 1)?[0] as usize; inputs];
            if grid[0] < 2 {
                return Err(invalid());
            }
            let (start, ni, no, precision) = if eight {
                (48, 256, 256, 1)
            } else {
                (52, reader.short(48)?, reader.short(50)?, 2)
            };
            if !(2..=4096).contains(&ni) || !(2..=4096).contains(&no) {
                return Err(invalid());
            }
            let input = (0..inputs)
                .map(|c| {
                    reader
                        .values(start + c * ni * precision, ni, precision)
                        .map(Curve::Table)
                })
                .collect::<Result<_, _>>()?;
            stages.push(Stage::Curves(input));
            let clut = start + inputs * ni * precision;
            let count = grid.iter().product::<usize>() * outputs;
            stages.push(Stage::Clut {
                grid,
                outputs,
                values: reader.values(clut, count, precision)?,
            });
            let at = clut + count * precision;
            let output = (0..outputs)
                .map(|c| {
                    reader
                        .values(at + c * no * precision, no, precision)
                        .map(Curve::Table)
                })
                .collect::<Result<_, _>>()?;
            stages.push(Stage::Curves(output));
            let end = at + outputs * no * precision;
            if end > tag.len()
                || tag.len() - end > 3
                || reader.bytes(end, tag.len() - end)?.iter().any(|&v| v != 0)
            {
                return Err(invalid());
            }
        } else {
            if bytes[8] != 4
                || reader.bytes(0, 4)? != if forward { b"mAB " } else { b"mBA " }
                || reader.bytes(10, 2)? != [0; 2]
            {
                return Err(invalid());
            }
            let offsets = (12..32)
                .step_by(4)
                .map(|at| reader.word(at))
                .collect::<Result<Vec<_>, _>>()?;
            if offsets[0] == 0
                || (offsets[1] == 0) != (offsets[2] == 0)
                || (offsets[3] == 0) != (offsets[4] == 0)
                || (offsets[3] == 0 && inputs != outputs)
            {
                return Err(invalid());
            }
            let b = Stage::Curves(reader.curves(offsets[0], if forward { outputs } else { 3 })?);
            let matrix = if offsets[1] != 0 {
                let mut matrix = IDENTITY;
                for (i, v) in matrix.iter_mut().enumerate() {
                    *v = reader.fixed(offsets[1] + i * 4)?;
                }
                reader.record(offsets[1], offsets[1] + 48)?;
                Some(Stage::Matrix(matrix))
            } else {
                None
            };
            let middle = if offsets[2] != 0 {
                Some(Stage::Curves(reader.curves(offsets[2], 3)?))
            } else {
                None
            };
            let clut = if offsets[3] != 0 {
                let at = offsets[3];
                let header = reader.bytes(at, 20)?;
                let grid: Vec<usize> = header[..inputs].iter().map(|v| *v as usize).collect();
                let precision = header[16] as usize;
                if grid.iter().any(|&n| n < 2)
                    || header[inputs..16]
                        .iter()
                        .chain(&header[17..20])
                        .any(|&v| v != 0)
                    || ![1, 2].contains(&precision)
                {
                    return Err(invalid());
                }
                let count = grid.iter().product::<usize>() * outputs;
                let values = reader.values(at + 20, count, precision)?;
                reader.record(at, at + 20 + count * precision)?;
                Some(Stage::Clut {
                    grid,
                    outputs,
                    values,
                })
            } else {
                None
            };
            let a = if offsets[4] != 0 {
                Some(Stage::Curves(reader.curves(
                    offsets[4],
                    if forward { inputs } else { outputs },
                )?))
            } else {
                None
            };
            if forward {
                stages.extend(a);
                stages.extend(clut);
                stages.extend(middle);
                stages.extend(matrix);
                stages.push(b);
            } else {
                stages.push(b);
                stages.extend(matrix);
                stages.extend(middle);
                stages.extend(clut);
                stages.extend(a);
            }
        }
        Ok(Some(Self {
            stages,
            outputs,
            inputs,
            signature,
            lab,
            legacy_lab: lab && &tag[..4] == b"mft2",
        }))
    }
    pub fn evaluate<const N: usize>(&self, input: [f64; N]) -> Result<[f64; 4], Error> {
        if N != self.inputs || input.iter().any(|v| !v.is_finite()) {
            return Err(invalid());
        }
        let mut value = [0.0; 4];
        value[..N].copy_from_slice(&input);
        for stage in &self.stages {
            match stage {
                Stage::Curves(curves) => {
                    for (v, curve) in value.iter_mut().zip(curves) {
                        *v = curve.value(*v)?;
                    }
                }
                Stage::Matrix(m) => {
                    let old = value;
                    for r in 0..3 {
                        value[r] = (m[r * 3] * old[0]
                            + m[r * 3 + 1] * old[1]
                            + m[r * 3 + 2] * old[2]
                            + m[9 + r])
                            .clamp(0.0, 1.0);
                    }
                }
                Stage::Clut {
                    grid,
                    outputs,
                    values,
                } => {
                    let mut low = [0usize; 4];
                    let mut t = [0.0; 4];
                    for i in 0..grid.len() {
                        let pos = value[i].clamp(0.0, 1.0) * (grid[i] - 1) as f64;
                        low[i] = (pos.floor() as usize).min(grid[i] - 2);
                        t[i] = pos - low[i] as f64;
                    }
                    value = [0.0; 4];
                    // Tensor interpolation preserves fractional lookup coordinates;
                    // no quantized intermediate sample or weight is introduced.
                    for corner in 0..(1 << grid.len()) {
                        let weight = (0..grid.len())
                            .map(|i| {
                                if (corner >> i) & 1 == 1 {
                                    t[i]
                                } else {
                                    1.0 - t[i]
                                }
                            })
                            .product::<f64>();
                        let at = (0..grid.len())
                            .fold(0, |at, i| at * grid[i] + low[i] + ((corner >> i) & 1))
                            * outputs;
                        for c in 0..*outputs {
                            value[c] += values[at + c] * weight;
                        }
                    }
                }
            }
        }
        if value[..self.outputs].iter().any(|v| !v.is_finite()) {
            return Err(invalid());
        }
        Ok(value.map(|v| v.clamp(0.0, 1.0)))
    }
}
