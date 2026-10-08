//! Explicit continuous PCS connection for original native ink preparation.
use super::*;

pub(crate) struct PaintConverter {
    pub process: ProcessProfile,
    rgb: SourceConverter,
    destination: std::sync::Arc<super::table::Table>,
}
pub(crate) struct ProcessProfile {
    pub bytes: Vec<u8>,
    pub intent: Intent,
}
pub(crate) enum SourceConverter {
    Colorimetric(Box<ColorimetricSource>),
    Managed(Box<super::super::device::Connection>),
}
pub(crate) struct ColorimetricSource {
    matrix: Option<MatrixSource>,
    source_table: Option<super::table::Table>,
    destination: std::sync::Arc<super::table::Table>,
    scale: [f64; 3],
}
struct MatrixSource {
    curves: [super::super::curves::Curve; 3],
    columns: [[f64; 3]; 3],
}
impl MatrixSource {
    fn new(bytes: &[u8], source: &ColorProfile) -> Result<Self, Error> {
        use super::super::curves::Reader;
        let mut curves = Vec::new();
        for signature in [b"rTRC", b"gTRC", b"bTRC"] {
            let at = (132..132 + word(bytes, 128)? * 12)
                .step_by(12)
                .find(|&at| &bytes[at..at + 4] == signature)
                .ok_or_else(invalid)?;
            let offset = word(bytes, at + 4)?;
            let end = offset + word(bytes, at + 8)?;
            let mut reader = Reader {
                data: &bytes[..end],
                ranges: Vec::new(),
            };
            curves.push(reader.curves(offset, 1)?.remove(0));
        }
        let curves = curves.try_into().ok().unwrap();
        let columns = [
            source.red_colorant,
            source.green_colorant,
            source.blue_colorant,
        ]
        .map(|v| [v.x, v.y, v.z]);
        Ok(Self { curves, columns })
    }
    fn convert(&self, values: &[f64], output: &mut [f64]) -> Result<(), Error> {
        for (pixel, xyz) in values
            .as_chunks::<3>()
            .0
            .iter()
            .zip(output.as_chunks_mut::<3>().0)
        {
            let mut linear = [0.0; 3];
            for c in 0..3 {
                linear[c] = self.curves[c].value(pixel[c])?;
            }
            for (row, v) in xyz.iter_mut().enumerate() {
                *v = (0..3)
                    .map(|c| self.columns[c][row] * linear[c])
                    .sum::<f64>()
                    * 0.5;
            }
        }
        Ok(())
    }
}
fn input(values: &[f64]) -> Result<(), Error> {
    if !values.len().is_multiple_of(3) || values.iter().any(|v| !v.is_finite()) {
        return Err(Error::new(
            "INVALID_REQUEST",
            "Ink conversion needs finite color triples",
        ));
    }
    if values.len() / 3 > 4096 {
        return Err(limit(
            "Elementary ink color conversion exceeds its batch bound",
        ));
    }
    Ok(())
}
impl ColorimetricSource {
    fn new(
        source_bytes: &[u8],
        source: &ColorProfile,
        destination_profile: &ColorProfile,
        destination: std::sync::Arc<super::table::Table>,
        intent: Intent,
    ) -> Result<Self, Error> {
        for at in (132..132 + word(source_bytes, 128)? * 12).step_by(12) {
            if &source_bytes[at..at + 3] == b"D2B" {
                return Err(Error::new(
                    "UNSUPPORTED",
                    "Native preparation does not evaluate float PCS override tables",
                ));
            }
        }
        let scale = if intent == Intent::AbsoluteColorimetric {
            absolute_scale(source, destination_profile)?
        } else {
            [1.0; 3]
        };
        let source_table = super::table::Table::new(source_bytes, true)?;
        let matrix = if source_table.is_none() {
            if source.lut_a_to_b_saturation.is_some() {
                return Err(Error::new(
                    "UNSUPPORTED_PROFILE_INTENT",
                    "Source profile lacks a colorimetric or default table",
                ));
            }
            if source.pcs != DataColorSpace::Xyz {
                return Err(invalid());
            }
            Some(MatrixSource::new(source_bytes, source)?)
        } else {
            None
        };
        Ok(Self {
            matrix,
            source_table,
            destination,
            scale,
        })
    }
    pub fn convert(&self, values: &[f64]) -> Result<Vec<f64>, Error> {
        input(values)?;
        let mut xyz = vec![0.0; values.len()];
        if let Some(matrix) = &self.matrix {
            matrix.convert(values, &mut xyz)?;
        } else {
            let table = self.source_table.as_ref().unwrap();
            for (pixel, out) in values
                .as_chunks::<3>()
                .0
                .iter()
                .zip(xyz.as_chunks_mut::<3>().0)
            {
                let q = table.evaluate(*pixel)?;
                *out = if table.lab {
                    let scale = if table.legacy_lab {
                        65535.0 / 65280.0
                    } else {
                        1.0
                    };
                    let q = q.map(|v| (v * scale).clamp(0.0, 1.0));
                    super::super::proof::from_lab([
                        q[0] * 100.0,
                        q[1] * 255.0 - 128.0,
                        q[2] * 255.0 - 128.0,
                    ])
                    .map(|v| v * 0.5)
                } else {
                    std::array::from_fn(|c| q[c] * 65535.0 / 65536.0)
                };
            }
        }
        self.separate_xyz(&xyz)
    }
    fn separate_xyz(&self, values: &[f64]) -> Result<Vec<f64>, Error> {
        input(values)?;
        let mut encoded = values.to_vec();
        for pixel in encoded.as_chunks_mut::<3>().0 {
            for (v, scale) in pixel.iter_mut().zip(self.scale) {
                *v *= scale;
            }
            if self.destination.lab {
                let scale = if self.destination.legacy_lab {
                    65280.0 / 65535.0
                } else {
                    1.0
                };
                let lab = super::super::proof::lab(pixel.map(|v| v * 2.0));
                let q = [
                    lab[0] / 100.0,
                    (lab[1] + 128.0) / 255.0,
                    (lab[2] + 128.0) / 255.0,
                ];
                *pixel = q.map(|v| (v * scale).clamp(0.0, 1.0));
            } else {
                *pixel = pixel.map(|v| v * 65536.0 / 65535.0);
            }
        }
        if encoded
            .iter()
            .any(|v| !v.is_finite() || !(0.0..=1.0).contains(v))
        {
            return Err(Error::new(
                "UNSUPPORTED_PROFILE_RANGE",
                "Native source connection exceeds the bounded PCSXYZ encoding range",
            ));
        }
        let mut output = Vec::with_capacity(values.len() / 3 * 4);
        for pixel in encoded.as_chunks::<3>().0 {
            output.extend(self.destination.evaluate(*pixel)?);
        }
        if output
            .iter()
            .any(|v| !v.is_finite() || !(0.0..=1.0).contains(v))
        {
            return Err(Error::new(
                "COLOR_CONVERSION",
                "Elementary paint conversion produced invalid ink fractions",
            ));
        }
        Ok(output)
    }
}
impl SourceConverter {
    fn new(
        source_bytes: &[u8],
        source: &ColorProfile,
        destination_bytes: &[u8],
        destination_profile: &ColorProfile,
        destination: std::sync::Arc<super::table::Table>,
        intent: Intent,
    ) -> Result<Self, Error> {
        if matches!(intent, Intent::Perceptual | Intent::Saturation) {
            use super::super::device::{Connection, Endpoint, Space, Untagged};
            let connection = Connection::new(
                &Endpoint {
                    space: Space::Rgb,
                    profile: Some(Profile::Icc {
                        data: STANDARD.encode(source_bytes),
                    }),
                    untagged: Untagged::Reject,
                },
                &Endpoint {
                    space: Space::Cmyk,
                    profile: Some(Profile::Icc {
                        data: STANDARD.encode(destination_bytes),
                    }),
                    untagged: Untagged::Reject,
                },
                intent,
            )?;
            Ok(Self::Managed(Box::new(connection)))
        } else {
            Ok(Self::Colorimetric(Box::new(ColorimetricSource::new(
                source_bytes,
                source,
                destination_profile,
                destination,
                intent,
            )?)))
        }
    }
    pub fn convert(&self, values: &[f64]) -> Result<Vec<f64>, Error> {
        match self {
            Self::Colorimetric(source) => source.convert(values),
            Self::Managed(connection) => {
                input(values)?;
                let mut output = Vec::with_capacity(values.len() / 3 * 4);
                for point in values.as_chunks::<3>().0 {
                    output.extend(connection.sample(point)?.values);
                }
                Ok(output)
            }
        }
    }
}
impl PaintConverter {
    pub fn new(source: &Source, intent: Intent) -> Result<Self, Error> {
        let bytes = read_source(source)?;
        let destination = parse_space(&bytes, true)?;
        if destination.lut_a_to_b_perceptual.is_none()
            || destination.lut_b_to_a_perceptual.is_none()
        {
            return Err(Error::new(
                "UNSUPPORTED",
                "CMYK image delivery requires both A2B0 and B2A0 profile tables",
            ));
        }
        let table = std::sync::Arc::new(
            super::table::Table::with_intent(&bytes, false, intent)?.ok_or_else(invalid)?,
        );
        let (source_bytes, source) = resolve(&Profile::Builtin {
            name: Builtin::Srgb,
        })?;
        let rgb = SourceConverter::new(
            &source_bytes,
            &source,
            &bytes,
            &destination,
            table.clone(),
            intent,
        )?;
        Ok(Self {
            process: ProcessProfile { bytes, intent },
            rgb,
            destination: table,
        })
    }
    pub fn source(&self, profile: &Profile) -> Result<SourceConverter, Error> {
        let (bytes, source) = resolve(profile)?;
        SourceConverter::new(
            &bytes,
            &source,
            &self.process.bytes,
            &parse_space(&self.process.bytes, true)?,
            self.destination.clone(),
            self.process.intent,
        )
    }
    pub fn rgb(&self, values: &[f64]) -> Result<Vec<f64>, Error> {
        self.rgb.convert(values)
    }
    pub fn lab(&self, values: [f64; 3]) -> Result<[f64; 4], Error> {
        if matches!(self.rgb, SourceConverter::Managed(_)) {
            use super::super::device::{Connection, Endpoint, Space, Untagged};
            let connection = Connection::new(
                &Endpoint {
                    space: Space::Lab,
                    profile: None,
                    untagged: Untagged::Reject,
                },
                &Endpoint {
                    space: Space::Cmyk,
                    profile: Some(Profile::Icc {
                        data: STANDARD.encode(&self.process.bytes),
                    }),
                    untagged: Untagged::Reject,
                },
                self.process.intent,
            )?;
            return Ok(connection.sample(&values)?.values.try_into().unwrap());
        }
        let xyz = super::super::proof::from_lab(values).map(|v| v * 0.5);
        let SourceConverter::Colorimetric(source) = &self.rgb else {
            unreachable!()
        };
        Ok(source.separate_xyz(&xyz)?.try_into().unwrap())
    }
}
