//! Original ICC curve equations and continuous table reconstruction.
use super::{invalid, limit};
use crate::Error;

pub(super) enum Curve {
    Identity,
    Table(Vec<f64>),
    Parametric(Vec<f64>),
}
impl Curve {
    pub(super) fn validate_inverse(&self) -> Result<(), Error> {
        let valid = match self {
            Self::Identity => true,
            Self::Table(v) => {
                v.windows(2).all(|p| p[0] <= p[1]) || v.windows(2).all(|p| p[0] >= p[1])
            }
            Self::Parametric(p) => match p.as_slice() {
                [_] => true,
                [_, a, _] | [_, a, _, _] => *a > 0.0,
                [g, a, b, c, d] => {
                    *a > 0.0
                        && *c >= 0.0
                        && (*a * d.max(0.0) + b) >= 0.0
                        && (*a * d + b).powf(*g) >= c * d
                }
                [g, a, b, c, d, e, f] => {
                    *a > 0.0
                        && *c >= 0.0
                        && (*a * d.max(0.0) + b) >= 0.0
                        && (*a * d + b).powf(*g) + e >= c * d + f
                }
                _ => false,
            },
        };
        if !valid || self.value(0.0)? == self.value(1.0)? {
            return Err(Error::new(
                "UNSUPPORTED_PROFILE_CURVE",
                "Destination curves must be nonconstant and monotone over their device domain",
            ));
        }
        Ok(())
    }
    /// ICC.1 Annex F: interior plateaus choose their high endpoint; terminal
    /// plateaus choose their low endpoint. A discontinuity chooses nearest y.
    pub(super) fn inverse(&self, y: f64) -> Result<f64, Error> {
        let first = self.value(0.0)?;
        let last = self.value(1.0)?;
        let sign = if last > first { 1.0 } else { -1.0 };
        let y = (y * sign).clamp(first * sign, last * sign);
        let terminal = y == last * sign;
        if let Self::Table(values) = self {
            let lo = values.partition_point(|v| v * sign < y);
            let hi = values.partition_point(|v| v * sign <= y);
            let scale = (values.len() - 1) as f64;
            if lo < hi {
                return Ok(if terminal { lo } else { hi - 1 } as f64 / scale);
            }
            let a = values[lo - 1] * sign;
            let b = values[lo] * sign;
            return Ok(((lo - 1) as f64 + (y - a) / (b - a)) / scale);
        }
        let (mut lo, mut hi) = (0.0, 1.0);
        for _ in 0..64 {
            let mid = (lo + hi) * 0.5;
            let q = self.value(mid)? * sign;
            if q < y || (!terminal && q == y) {
                lo = mid;
            } else {
                hi = mid;
            }
        }
        let a = (self.value(lo)? * sign - y).abs();
        let b = (self.value(hi)? * sign - y).abs();
        Ok(if a < b || (a == b && !terminal) {
            lo
        } else {
            hi
        })
    }
    pub(super) fn clips_inverse(&self, y: f64) -> Result<bool, Error> {
        let a = self.value(0.0)?;
        let b = self.value(1.0)?;
        Ok(!(a.min(b)..=a.max(b)).contains(&y))
    }
    pub(super) fn value(&self, x: f64) -> Result<f64, Error> {
        let x = x.clamp(0.0, 1.0);
        let y = match self {
            Self::Identity => x,
            Self::Table(v) => linear(v, x),
            Self::Parametric(p) => match p.as_slice() {
                [g] => x.powf(*g),
                [g, a, b] => {
                    if x >= -b / a {
                        (a * x + b).powf(*g)
                    } else {
                        0.0
                    }
                }
                [g, a, b, c] => {
                    if x >= -b / a {
                        (a * x + b).powf(*g) + c
                    } else {
                        *c
                    }
                }
                [g, a, b, c, d] => {
                    if x >= *d {
                        (a * x + b).powf(*g)
                    } else {
                        c * x
                    }
                }
                [g, a, b, c, d, e, f] => {
                    if x >= *d {
                        (a * x + b).powf(*g) + e
                    } else {
                        c * x + f
                    }
                }
                _ => unreachable!(),
            },
        };
        if !y.is_finite() {
            return Err(Error::new(
                "INVALID_PROFILE",
                "ICC curve has an undefined value in its evaluated domain",
            ));
        }
        Ok(y.clamp(0.0, 1.0))
    }
}
fn linear(values: &[f64], x: f64) -> f64 {
    let q = x.clamp(0.0, 1.0) * (values.len() - 1) as f64;
    let low = (q.floor() as usize).min(values.len() - 2);
    if values[low] == values[low + 1] {
        return values[low];
    }
    let t = q - low as f64;
    (1.0 - t) * values[low] + t * values[low + 1]
}

pub(super) struct Reader<'a> {
    pub(super) data: &'a [u8],
    pub(super) ranges: Vec<(usize, usize)>,
}
impl Reader<'_> {
    pub(super) fn bytes(&self, at: usize, length: usize) -> Result<&[u8], Error> {
        self.data
            .get(at..at.checked_add(length).ok_or_else(invalid)?)
            .ok_or_else(invalid)
    }
    pub(super) fn word(&self, at: usize) -> Result<usize, Error> {
        Ok(u32::from_be_bytes(self.bytes(at, 4)?.try_into().unwrap()) as usize)
    }
    pub(super) fn short(&self, at: usize) -> Result<usize, Error> {
        Ok(u16::from_be_bytes(self.bytes(at, 2)?.try_into().unwrap()) as usize)
    }
    pub(super) fn fixed(&self, at: usize) -> Result<f64, Error> {
        Ok(i32::from_be_bytes(self.bytes(at, 4)?.try_into().unwrap()) as f64 / 65536.0)
    }
    pub(super) fn record(&mut self, start: usize, end: usize) -> Result<(), Error> {
        if start < 32
            || !start.is_multiple_of(4)
            || end < start
            || end > self.data.len()
            || self
                .ranges
                .iter()
                .any(|&(a, b)| start < b && a < end && (start, end) != (a, b))
        {
            return Err(invalid());
        }
        self.ranges.push((start, end));
        Ok(())
    }
    pub(super) fn values(
        &self,
        at: usize,
        count: usize,
        precision: usize,
    ) -> Result<Vec<f64>, Error> {
        let bytes = self.bytes(at, count.checked_mul(precision).ok_or_else(invalid)?)?;
        match precision {
            1 => Ok(bytes.iter().map(|&x| x as f64 / 255.0).collect()),
            2 => Ok(bytes
                .as_chunks::<2>()
                .0
                .iter()
                .map(|&x| u16::from_be_bytes(x) as f64 / 65535.0)
                .collect()),
            _ => Err(invalid()),
        }
    }
    pub(super) fn curves(&mut self, mut at: usize, count: usize) -> Result<Vec<Curve>, Error> {
        let mut curves = Vec::new();
        for _ in 0..count {
            let start = at;
            let signature = self.bytes(at, 4)?;
            if self.bytes(at + 4, 4)? != [0; 4] {
                return Err(invalid());
            }
            let (curve, end) = match signature {
                b"curv" => {
                    let n = self.word(at + 8)?;
                    if n > 65536 {
                        return Err(limit("ICC curve exceeds 65536 entries"));
                    }
                    let v = match n {
                        0 => Curve::Identity,
                        1 => {
                            let g = self.short(at + 12)? as f64 / 256.0;
                            if g <= 0.0 {
                                return Err(invalid());
                            }
                            Curve::Parametric(vec![g])
                        }
                        _ => Curve::Table(self.values(at + 12, n, 2)?),
                    };
                    (v, at + 12 + n * 2)
                }
                b"para" => {
                    if self.short(at + 10)? != 0 {
                        return Err(invalid());
                    }
                    let n = *[1, 3, 4, 5, 7]
                        .get(self.short(at + 8)?)
                        .ok_or_else(invalid)?;
                    let values: Vec<_> = (0..n)
                        .map(|i| self.fixed(at + 12 + i * 4))
                        .collect::<Result<_, _>>()?;
                    if values[0] <= 0.0 || (n > 1 && values[1] == 0.0) {
                        return Err(invalid());
                    }
                    (Curve::Parametric(values), at + 12 + n * 4)
                }
                _ => return Err(invalid()),
            };
            at = end.div_ceil(4) * 4;
            if end != self.data.len() && self.bytes(end, at - end)?.iter().any(|&v| v != 0) {
                return Err(invalid());
            }
            self.record(start, end)?;
            curves.push(curve);
        }
        Ok(curves)
    }
}
