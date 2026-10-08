//! Original bounded evaluation of ICC gamut tables, independent of round trips.
use super::*;

pub const MAX_SAMPLES: usize = 4096;
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Mode {
    #[default]
    IfAvailable,
    Required,
    Off,
}
use super::curves::{Curve, Reader};

const IDENTITY: [f64; 12] = [1., 0., 0., 0., 1., 0., 0., 0., 1., 0., 0., 0.];
pub struct Gamut {
    input: Vec<Curve>,
    middle: Vec<Curve>,
    output: Curve,
    matrix: [f64; 12],
    matrix_first: bool,
    grid: [usize; 3],
    values: Vec<f64>,
    lab: bool,
    legacy_lab: bool,
    scale: [f64; 3],
    tag_type: String,
    profile_hash: String,
    tag_hash: String,
}
pub struct Classification {
    pub encoded_pcs: [f64; 3],
    pub value: Option<f64>,
}
impl Classification {
    pub fn receipt(&self) -> Value {
        json!({"encoded_pcs":self.encoded_pcs,"gamut_value":self.value,"classification":match self.value {None=>"outside_pcs_encoding",Some(0.0)=>"in_gamut",Some(_)=>"out_of_gamut"}})
    }
}
impl Gamut {
    pub fn new(bytes: &[u8], intent: Intent) -> Result<Option<Self>, Error> {
        Self::from_profile(bytes, intent, parse_space(bytes, true)?)
    }
    pub(crate) fn profile_relative(
        bytes: &[u8],
        space: DataColorSpace,
    ) -> Result<Option<Self>, Error> {
        Self::from_profile(
            bytes,
            Intent::RelativeColorimetric,
            parse_model(bytes, space, false)?,
        )
    }
    fn from_profile(
        bytes: &[u8],
        intent: Intent,
        profile: ColorProfile,
    ) -> Result<Option<Self>, Error> {
        if !matches!(
            intent,
            Intent::RelativeColorimetric | Intent::AbsoluteColorimetric
        ) {
            return Err(Error::new(
                "UNSUPPORTED_PROFILE_INTENT",
                "Gamut coordinates require a colorimetric interpretation",
            ));
        }
        let count = word(bytes, 128)?;
        let Some(entry) = (132..132 + count * 12)
            .step_by(12)
            .find(|&at| bytes[at..at + 4] == *b"gamt")
        else {
            return Ok(None);
        };
        let at = word(bytes, entry + 4)?;
        let size = word(bytes, entry + 8)?;
        let tag = &bytes[at..at + size];
        let mut reader = Reader {
            data: tag,
            ranges: Vec::new(),
        };
        if reader.bytes(4, 4)? != [0; 4] || reader.bytes(8, 2)? != [3, 1] {
            return Err(invalid());
        }
        let lab = profile.pcs == DataColorSpace::Lab;
        let modern = reader.bytes(0, 4)? == b"mBA ";
        let mut matrix = IDENTITY;
        let (input, middle, output, grid, values, legacy_lab) = match reader.bytes(0, 4)? {
            b"mft1" | b"mft2" => {
                let eight = tag[..4] == *b"mft1";
                if !lab && eight {
                    return Err(Error::new(
                        "UNSUPPORTED",
                        "Gamut rejects ambiguous eight-bit XYZ connection tables",
                    ));
                }
                if reader.bytes(11, 1)? != [0] {
                    return Err(invalid());
                }
                for (i, v) in matrix[..9].iter_mut().enumerate() {
                    *v = reader.fixed(12 + i * 4)?;
                }
                if lab && matrix != IDENTITY {
                    return Err(invalid());
                }
                let grid = [reader.bytes(10, 1)?[0] as usize; 3];
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
                let input = (0..3)
                    .map(|c| {
                        reader
                            .values(start + c * ni * precision, ni, precision)
                            .map(Curve::Table)
                    })
                    .collect::<Result<_, _>>()?;
                let clut = start + 3 * ni * precision;
                let cells = grid.iter().product::<usize>();
                let values = reader.values(clut, cells, precision)?;
                let output = clut + cells * precision;
                let curve = Curve::Table(reader.values(output, no, precision)?);
                let end = output + no * precision;
                if tag.len() - end > 3
                    || reader.bytes(end, tag.len() - end)?.iter().any(|&v| v != 0)
                {
                    return Err(invalid());
                }
                (input, Vec::new(), curve, grid, values, lab && !eight)
            }
            b"mBA " => {
                if bytes[8] != 4 || reader.bytes(10, 2)? != [0; 2] {
                    return Err(invalid());
                }
                let offsets: Vec<_> = (12..32)
                    .step_by(4)
                    .map(|i| reader.word(i))
                    .collect::<Result<_, _>>()?;
                if offsets[0] == 0
                    || offsets[3] == 0
                    || offsets[4] == 0
                    || (offsets[1] == 0) != (offsets[2] == 0)
                {
                    return Err(invalid());
                }
                let input = reader.curves(offsets[0], 3)?;
                let middle = if offsets[1] != 0 {
                    for (i, v) in matrix.iter_mut().enumerate() {
                        *v = reader.fixed(offsets[1] + i * 4)?;
                    }
                    reader.record(offsets[1], offsets[1] + 48)?;
                    reader.curves(offsets[2], 3)?
                } else {
                    Vec::new()
                };
                let clut = offsets[3];
                let header = reader.bytes(clut, 20)?;
                let grid = [header[0] as usize, header[1] as usize, header[2] as usize];
                let precision = header[16] as usize;
                if grid.iter().any(|&n| n < 2)
                    || header[3..16].iter().chain(&header[17..20]).any(|&v| v != 0)
                    || ![1, 2].contains(&precision)
                {
                    return Err(invalid());
                }
                let cells = grid.iter().product::<usize>();
                let values = reader.values(clut + 20, cells, precision)?;
                reader.record(clut, clut + 20 + cells * precision)?;
                let output = reader.curves(offsets[4], 1)?.remove(0);
                (input, middle, output, grid, values, false)
            }
            _ => {
                return Err(Error::new(
                    "UNSUPPORTED",
                    "Gamut requires an ICC lut8, lut16 or lutBToA table",
                ));
            }
        };
        let scale = if intent == Intent::AbsoluteColorimetric {
            absolute_scale(&working()?, &profile)?
        } else {
            [1.; 3]
        };
        Ok(Some(Self {
            input,
            middle,
            output,
            matrix,
            matrix_first: !modern,
            grid,
            values,
            lab,
            legacy_lab,
            scale,
            tag_type: String::from_utf8_lossy(&tag[..4]).trim().to_string(),
            profile_hash: assets::sha256(bytes),
            tag_hash: assets::sha256(tag),
        }))
    }
    pub fn receipt(&self) -> Value {
        json!({"status":"available","method":"ICC_gamt_tag;zero_in_gamut_nonzero_out","profile_sha256":self.profile_hash,"tag_sha256":self.tag_hash,"tag_type":self.tag_type,"pcs":if self.lab {"Lab"} else {"XYZ"},"legacy_lab_encoding":self.legacy_lab,"source_to_profile_relative_scale":self.scale,"clut_interpolation":"tetrahedral_f64;descending_fraction_stable_axis_order","grid":self.grid,"encoding_overflow":"unclassified_without_clamping_source_PCS","claim":"supplied_profile_classification_not_independent_press_certification"})
    }
    fn matrix(&self, q: [f64; 3]) -> [f64; 3] {
        std::array::from_fn(|c| {
            (self.matrix[c * 3] * q[0]
                + self.matrix[c * 3 + 1] * q[1]
                + self.matrix[c * 3 + 2] * q[2]
                + self.matrix[9 + c])
                .clamp(0.0, 1.0)
        })
    }
    pub fn classify(&self, xyz: [f64; 3]) -> Result<Classification, Error> {
        if xyz.iter().any(|v| !v.is_finite()) {
            return Err(Error::new(
                "INVALID_REQUEST",
                "Gamut samples require finite D50 XYZ coordinates",
            ));
        }
        let xyz = std::array::from_fn(|i| xyz[i] * self.scale[i]);
        let encoded = if self.lab {
            let q = super::proof::lab(xyz);
            let factor = if self.legacy_lab {
                65280.0 / 65535.0
            } else {
                1.0
            };
            [
                q[0] / 100.0 * factor,
                (q[1] + 128.0) / 255.0 * factor,
                (q[2] + 128.0) / 255.0 * factor,
            ]
        } else {
            xyz.map(|v| v * 32768.0 / 65535.0)
        };
        if encoded.iter().any(|v| !v.is_finite()) {
            return Err(Error::new(
                "INVALID_REQUEST",
                "Gamut sample exceeds finite PCS encoding",
            ));
        }
        if encoded.iter().any(|v| !(0.0..=1.0).contains(v)) {
            return Ok(Classification {
                encoded_pcs: encoded,
                value: None,
            });
        }
        let mut q = if self.matrix_first {
            self.matrix(encoded)
        } else {
            encoded
        };
        for (v, curve) in q.iter_mut().zip(&self.input) {
            *v = curve.value(*v)?;
        }
        if !self.matrix_first {
            q = self.matrix(q);
        }
        for (v, curve) in q.iter_mut().zip(&self.middle) {
            *v = curve.value(*v)?;
        }
        let positions: [f64; 3] = std::array::from_fn(|i| q[i] * (self.grid[i] - 1) as f64);
        let low: [usize; 3] =
            std::array::from_fn(|i| (positions[i].floor() as usize).min(self.grid[i] - 2));
        let fractions: [f64; 3] = std::array::from_fn(|i| positions[i] - low[i] as f64);
        let mut order = [0, 1, 2];
        order.sort_by(|&a, &b| fractions[b].total_cmp(&fractions[a]).then(a.cmp(&b)));
        let at = |p: [usize; 3]| self.values[(p[0] * self.grid[1] + p[1]) * self.grid[2] + p[2]];
        let [a, b, c] = order;
        let mut point = low;
        let mut value = (1.0 - fractions[a]) * at(point);
        point[a] += 1;
        value += (fractions[a] - fractions[b]) * at(point);
        point[b] += 1;
        value += (fractions[b] - fractions[c]) * at(point);
        point[c] += 1;
        value += fractions[c] * at(point);
        Ok(Classification {
            encoded_pcs: encoded,
            value: Some(self.output.value(value)?),
        })
    }
}
pub fn inspect(
    profile: &cmyk::Source,
    xyz: &[[f64; 3]],
    intent: Intent,
    control: &crate::control::Control,
) -> Result<Value, Error> {
    control.check()?;
    if xyz.len() > MAX_SAMPLES {
        return Err(limit("Gamut inspection exceeds 4096 samples"));
    }
    let bytes = cmyk::read_source(profile)?;
    let gamut = Gamut::new(&bytes, intent)?.ok_or_else(|| {
        Error::new(
            "GAMUT_UNAVAILABLE",
            "The supplied profile has no gamut table",
        )
    })?;
    let mut samples = Vec::with_capacity(xyz.len());
    for (i, p) in xyz.iter().enumerate() {
        if i.is_multiple_of(256) {
            control.check()?;
        }
        let mut value = gamut.classify(*p)?.receipt();
        value["xyz_d50"] = json!(p);
        samples.push(value);
    }
    control.check()?;
    Ok(json!({"profile":gamut.receipt(),"intent":intent,"samples":samples,"source_unchanged":true}))
}
