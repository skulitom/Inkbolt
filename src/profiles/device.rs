//! Original bounded device/PCS connections, using declared profile tables.
use super::{
    cmyk::table::Table,
    curves::{Curve, Reader},
    *,
};

#[derive(Clone, Copy, Debug, PartialEq, Eq, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Space {
    Rgb,
    Gray,
    Cmyk,
    Lab,
}
impl Space {
    fn channels(self) -> usize {
        match self {
            Self::Gray => 1,
            Self::Cmyk => 4,
            _ => 3,
        }
    }
    fn device(self) -> Result<DataColorSpace, Error> {
        match self {
            Self::Rgb => Ok(DataColorSpace::Rgb),
            Self::Gray => Ok(DataColorSpace::Gray),
            Self::Cmyk => Ok(DataColorSpace::Cmyk),
            Self::Lab => Err(unsupported()),
        }
    }
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Untagged {
    #[default]
    Reject,
    AssumeSrgb,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Endpoint {
    pub space: Space,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub profile: Option<Profile>,
    #[serde(default)]
    pub untagged: Untagged,
}
impl Endpoint {
    pub(crate) fn bytes(&self) -> Result<Vec<u8>, Error> {
        let profile = self.profile.clone().or_else(|| (self.space == Space::Rgb && matches!(self.untagged, Untagged::AssumeSrgb)).then_some(Profile::Builtin { name: Builtin::Srgb })).ok_or_else(|| Error::new("UNTAGGED_COLOR", "Device colors require an explicit matching profile; untagged RGB may explicitly assume_srgb"))?;
        match &profile {
            Profile::Builtin { .. } => resolve(&profile).map(|v| v.0),
            Profile::Icc { data } => {
                let max = if self.space == Space::Cmyk {
                    cmyk::MAX_PROFILE_BYTES
                } else {
                    MAX_PROFILE_BYTES
                };
                if data.len() > max.div_ceil(3) * 4 {
                    return Err(limit("Encoded device profile exceeds its byte limit"));
                }
                STANDARD.decode(data).map_err(|_| invalid())
            }
        }
    }
    pub(crate) fn white(&self) -> Vec<f64> {
        match self.space {
            Space::Rgb => vec![1.0; 3],
            Space::Gray => vec![1.0],
            Space::Cmyk => vec![0.0; 4],
            Space::Lab => vec![100.0, 0.0, 0.0],
        }
    }
}
enum Model {
    Lab,
    Table(Table),
    Matrix {
        curves: [Curve; 3],
        columns: [[f64; 3]; 3],
        inverse: Option<[[f64; 3]; 3]>,
    },
    Gray {
        curve: Curve,
        lab: bool,
    },
}
pub(crate) struct Prepared {
    space: Space,
    model: Model,
    white: [f64; 3],
    receipt: Value,
    version: Option<u8>,
    reference_medium: bool,
}
const WHITE: [f64; 3] = [0.9642, 1.0, 0.8249];
#[derive(Clone, Copy)]
enum Pcs {
    Xyz([f64; 3]),
    Lab([f64; 3]),
}
impl Pcs {
    fn xyz(self) -> [f64; 3] {
        match self {
            Self::Xyz(v) => v,
            Self::Lab(v) => proof::from_lab(v),
        }
    }
    fn lab(self) -> [f64; 3] {
        match self {
            Self::Lab(v) => v,
            Self::Xyz(v) => proof::lab(v),
        }
    }
}
fn curve(bytes: &[u8], signature: &[u8; 4]) -> Result<Curve, Error> {
    let at = (132..132 + word(bytes, 128)? * 12)
        .step_by(12)
        .find(|&at| &bytes[at..at + 4] == signature)
        .ok_or_else(invalid)?;
    let start = word(bytes, at + 4)?;
    let end = start + word(bytes, at + 8)?;
    Reader {
        data: &bytes[..end],
        ranges: Vec::new(),
    }
    .curves(start, 1)
    .map(|mut v| v.remove(0))
}
fn invert(columns: [[f64; 3]; 3]) -> Result<[[f64; 3]; 3], Error> {
    let [a, b, c] = columns;
    let cross = |p: [f64; 3], q: [f64; 3]| {
        [
            p[1] * q[2] - p[2] * q[1],
            p[2] * q[0] - p[0] * q[2],
            p[0] * q[1] - p[1] * q[0],
        ]
    };
    let rows = [cross(b, c), cross(c, a), cross(a, b)];
    let det = (0..3).map(|i| a[i] * rows[0][i]).sum::<f64>();
    if !det.is_finite() || det.abs() < 1e-12 {
        return Err(Error::new(
            "UNSUPPORTED_PROFILE_MATRIX",
            "Destination matrix is singular or ill-conditioned",
        ));
    }
    Ok(rows.map(|r| r.map(|v| v / det)))
}
impl Prepared {
    pub(crate) fn new(endpoint: &Endpoint, intent: Intent, forward: bool) -> Result<Self, Error> {
        if endpoint.space == Space::Lab {
            if endpoint.profile.is_some() {
                return Err(Error::new(
                    "PROFILE_CONFLICT",
                    "Lab is an explicit D50 colorimetric space; do not attach an unrelated device profile",
                ));
            }
            return Ok(Self {
                space: Space::Lab,
                model: Model::Lab,
                white: WHITE,
                receipt: json!({"space":"lab","interpretation":"D50_colorimetric","profile_sha256":null}),
                version: None,
                reference_medium: false,
            });
        }
        let assumed = endpoint.profile.is_none();
        let bytes = endpoint.bytes()?;
        let parsed = parse_model(&bytes, endpoint.space.device()?, false)?;
        for at in (132..132 + word(&bytes, 128)? * 12).step_by(12) {
            if matches!(&bytes[at..at + 3], b"D2B" | b"B2D") {
                return Err(Error::new(
                    "UNSUPPORTED",
                    "Device connections do not silently ignore floating PCS override tables",
                ));
            }
        }
        let white = parsed.media_white_point.ok_or_else(invalid)?;
        let white = [white.x, white.y, white.z];
        if white.iter().any(|v| !v.is_finite() || *v <= 0.0) {
            return Err(invalid());
        }
        let mut selected = None;
        let model = if let Some(table) = Table::with_intent(&bytes, forward, intent)? {
            selected = Some(String::from_utf8_lossy(&table.signature).into_owned());
            Model::Table(table)
        } else {
            let prefix = if forward { b"A2B" } else { b"B2A" };
            if (132..132 + word(&bytes, 128)? * 12)
                .step_by(12)
                .any(|at| &bytes[at..at + 3] == prefix)
            {
                return Err(Error::new(
                    "UNSUPPORTED_PROFILE_INTENT",
                    "Profile lacks the requested directional intent table and default fallback",
                ));
            }
            match endpoint.space {
                Space::Rgb => {
                    if parsed.pcs != DataColorSpace::Xyz {
                        return Err(invalid());
                    }
                    let curves = [
                        curve(&bytes, b"rTRC")?,
                        curve(&bytes, b"gTRC")?,
                        curve(&bytes, b"bTRC")?,
                    ];
                    if !forward {
                        for c in &curves {
                            c.validate_inverse()?;
                        }
                    }
                    let columns = [
                        parsed.red_colorant,
                        parsed.green_colorant,
                        parsed.blue_colorant,
                    ]
                    .map(|v| [v.x, v.y, v.z]);
                    let inverse = if forward {
                        None
                    } else {
                        Some(invert(columns)?)
                    };
                    Model::Matrix {
                        curves,
                        columns,
                        inverse,
                    }
                }
                Space::Gray => {
                    let curve = curve(&bytes, b"kTRC")?;
                    if !forward {
                        curve.validate_inverse()?;
                    }
                    Model::Gray {
                        curve,
                        lab: parsed.pcs == DataColorSpace::Lab,
                    }
                }
                _ => {
                    return Err(Error::new(
                        "UNSUPPORTED_PROFILE_INTENT",
                        "Device profile requires a supported directional table",
                    ));
                }
            }
        };
        let reference_medium = bytes[8] == 4
            && matches!(intent, Intent::Perceptual | Intent::Saturation)
            && matches!(model, Model::Table(_));
        let receipt = json!({"space":endpoint.space,"profile_sha256":assets::sha256(&bytes),"profile_bytes":bytes.len(),"profile_version":bytes[8],"selected_table":selected,"model":match &model {Model::Table(_)=>"continuous_tensor_lookup",Model::Matrix{..}=>"matrix_trc",Model::Gray{..}=>"gray_trc",Model::Lab=>"D50_Lab"},"pcs_domain":if reference_medium {"v4_reference_medium"}else{"colourimetric_or_legacy"},"untagged_assumption":if assumed {Some("srgb")}else{None},"source_bytes_unchanged":true});
        Ok(Self {
            space: endpoint.space,
            model,
            white,
            receipt,
            version: Some(bytes[8]),
            reference_medium,
        })
    }
    fn to_pcs(&self, values: &[f64]) -> Result<Pcs, Error> {
        if values.len() != self.space.channels() || values.iter().any(|v| !v.is_finite()) {
            return Err(Error::new(
                "INVALID_COLOR",
                "Color components must be finite and match the declared space",
            ));
        }
        if self.space == Space::Lab {
            if !(0.0..=100.0).contains(&values[0])
                || values[1..].iter().any(|v| !(-128.0..=127.0).contains(v))
            {
                return Err(Error::new(
                    "INVALID_COLOR",
                    "Lab values exceed the declared physical component ranges",
                ));
            }
        } else if values.iter().any(|v| !(0.0..=1.0).contains(v)) {
            return Err(Error::new(
                "INVALID_COLOR",
                "Device values must be normalized to 0..1",
            ));
        }
        match &self.model {
            Model::Lab => Ok(Pcs::Lab(values.try_into().unwrap())),
            Model::Gray { curve, lab } => {
                let y = curve.value(values[0])?;
                Ok(if *lab {
                    Pcs::Lab([y * 100.0, 0.0, 0.0])
                } else {
                    Pcs::Xyz(WHITE.map(|v| v * y))
                })
            }
            Model::Matrix {
                curves, columns, ..
            } => {
                let v = [
                    curves[0].value(values[0])?,
                    curves[1].value(values[1])?,
                    curves[2].value(values[2])?,
                ];
                Ok(Pcs::Xyz(std::array::from_fn(|r| {
                    (0..3).map(|c| columns[c][r] * v[c]).sum()
                })))
            }
            Model::Table(table) => {
                let q = match self.space {
                    Space::Rgb => table.evaluate::<3>(values.try_into().unwrap())?,
                    Space::Gray => table.evaluate::<1>(values.try_into().unwrap())?,
                    Space::Cmyk => table.evaluate::<4>(values.try_into().unwrap())?,
                    _ => unreachable!(),
                };
                Ok(if table.lab {
                    let s = if table.legacy_lab {
                        65535.0 / 65280.0
                    } else {
                        1.0
                    };
                    Pcs::Lab([
                        q[0] * s * 100.0,
                        q[1] * s * 255.0 - 128.0,
                        q[2] * s * 255.0 - 128.0,
                    ])
                } else {
                    Pcs::Xyz(std::array::from_fn(|i| q[i] * 65535.0 / 32768.0))
                })
            }
        }
    }
    fn encode_pcs(&self, pcs: Pcs) -> Result<(Vec<f64>, usize), Error> {
        let xyz = pcs.xyz();
        if xyz.iter().any(|v| !v.is_finite()) {
            return Err(invalid());
        }
        match &self.model {
            Model::Lab => Ok((pcs.lab().to_vec(), 0)),
            Model::Gray { curve, lab } => {
                let v = if *lab { pcs.lab()[0] / 100.0 } else { xyz[1] };
                Ok((
                    vec![curve.inverse(v)?],
                    usize::from(curve.clips_inverse(v)?),
                ))
            }
            Model::Matrix {
                curves, inverse, ..
            } => {
                let rows = inverse.as_ref().unwrap();
                let mut clipped = 0;
                let mut output = Vec::new();
                for i in 0..3 {
                    let v = (0..3).map(|c| rows[i][c] * xyz[c]).sum::<f64>();
                    clipped += usize::from(curves[i].clips_inverse(v)?);
                    output.push(curves[i].inverse(v)?);
                }
                Ok((output, clipped))
            }
            Model::Table(table) => {
                let q = if table.lab {
                    let lab = pcs.lab();
                    let s = if table.legacy_lab {
                        65280.0 / 65535.0
                    } else {
                        1.0
                    };
                    [
                        lab[0] / 100.0,
                        (lab[1] + 128.0) / 255.0,
                        (lab[2] + 128.0) / 255.0,
                    ]
                    .map(|v| v * s)
                } else {
                    xyz.map(|v| v * 32768.0 / 65535.0)
                };
                let clipped = q.iter().filter(|v| !(0.0..=1.0).contains(*v)).count();
                let output = table.evaluate(q.map(|v| v.clamp(0.0, 1.0)))?;
                Ok((output[..self.space.channels()].to_vec(), clipped))
            }
        }
    }
}
pub(crate) fn validate_value(
    endpoint: &Endpoint,
    intent: Intent,
    values: &[f64],
) -> Result<(), Error> {
    Prepared::new(endpoint, intent, true)?
        .to_pcs(values)
        .map(|_| ())
}
pub(crate) struct Connection {
    source: Prepared,
    destination: Prepared,
    scale: [f64; 3],
    offset: [f64; 3],
    adjustment: &'static str,
}
#[derive(Serialize)]
pub(crate) struct Sample {
    pub source: Vec<f64>,
    pub source_pcs_xyz: [f64; 3],
    pub destination_pcs_xyz: [f64; 3],
    pub values: Vec<f64>,
    pub clipped_components: usize,
}
impl Connection {
    pub(crate) fn new(
        source: &Endpoint,
        destination: &Endpoint,
        intent: Intent,
    ) -> Result<Self, Error> {
        let source = Prepared::new(source, intent, true)?;
        let destination = Prepared::new(destination, intent, false)?;
        let mut scale = [1.0; 3];
        let mut offset = [0.0; 3];
        let mut adjustment = "identity";
        if intent == Intent::AbsoluteColorimetric {
            scale = std::array::from_fn(|i| source.white[i] / destination.white[i]);
            adjustment = "absolute_media_white";
        } else if matches!(intent, Intent::Perceptual | Intent::Saturation) {
            if source.version == Some(2) || destination.version == Some(2) {
                // A v2 connection has no standardized reference-medium black.
                // Keep its existing PCS convention explicit instead of inferring one.
                adjustment = "legacy_v2_direct_PCS_no_black_rescaling";
            } else if source.reference_medium != destination.reference_medium {
                // ICC.1 6.3.4.3: affine PCS XYZ adjustment preserving adopted white.
                const BLACK: [f64; 3] = [0.003357, 0.003479, 0.002869];
                if destination.reference_medium {
                    scale = std::array::from_fn(|i| 1.0 - BLACK[i] / WHITE[i]);
                    offset = BLACK;
                    adjustment = "colourimetric_to_v4_reference_medium";
                } else {
                    scale = std::array::from_fn(|i| 1.0 / (1.0 - BLACK[i] / WHITE[i]));
                    offset = std::array::from_fn(|i| -BLACK[i] * scale[i]);
                    adjustment = "v4_reference_medium_to_colourimetric";
                }
            }
        }
        Ok(Self {
            source,
            destination,
            scale,
            offset,
            adjustment,
        })
    }
    pub(crate) fn sample(&self, row: &[f64]) -> Result<Sample, Error> {
        let pcs = self.source.to_pcs(row)?;
        let xyz = pcs.xyz();
        let connected = if self.scale == [1.0; 3] && self.offset == [0.0; 3] {
            pcs
        } else {
            Pcs::Xyz(std::array::from_fn(|i| {
                xyz[i] * self.scale[i] + self.offset[i]
            }))
        };
        let (values, clipped_components) = self.destination.encode_pcs(connected)?;
        Ok(Sample {
            source: row.to_vec(),
            source_pcs_xyz: xyz,
            destination_pcs_xyz: connected.xyz(),
            values,
            clipped_components,
        })
    }
}
pub fn convert(
    source: &Endpoint,
    destination: &Endpoint,
    intent: Intent,
    values: &[Vec<f64>],
    control: Option<&crate::control::Control>,
) -> Result<Value, Error> {
    convert_with_gamut(source, destination, intent, values, None, control)
}
pub fn convert_with_gamut(
    source: &Endpoint,
    destination: &Endpoint,
    intent: Intent,
    values: &[Vec<f64>],
    gamut_mode: Option<gamut::Mode>,
    control: Option<&crate::control::Control>,
) -> Result<Value, Error> {
    if values.len() > 4096 {
        return Err(limit("Device conversion exceeds 4096 color samples"));
    }
    if let Some(c) = control {
        c.check()?;
    }
    let connection = Connection::new(source, destination, intent)?;
    let diagnostic_intent = if intent == Intent::AbsoluteColorimetric {
        intent
    } else {
        Intent::RelativeColorimetric
    };
    let diagnostic = match gamut_mode {
        None | Some(gamut::Mode::Off) => None,
        Some(mode) => {
            let table = if destination.space == Space::Lab {
                None
            } else {
                gamut::Gamut::profile_relative(&destination.bytes()?, destination.space.device()?)?
            };
            if table.is_none() && matches!(mode, gamut::Mode::Required) {
                return Err(Error::new(
                    "GAMUT_UNAVAILABLE",
                    "Destination has no supplied gamut table; clipping and round-trip drift do not prove gamut membership",
                ));
            }
            table
                .map(|table| {
                    Connection::new(source, destination, diagnostic_intent)
                        .map(|transform| (table, transform))
                })
                .transpose()?
        }
    };
    let mut samples = Vec::new();
    for row in values {
        if let Some(c) = control {
            c.check()?;
        }
        let mut sample = json!(connection.sample(row)?);
        if let Some((table, transform)) = &diagnostic {
            let colourimetric = transform.sample(row)?;
            let xyz = colourimetric.destination_pcs_xyz;
            sample["gamut"] = table.classify(xyz)?.receipt();
            sample["gamut"]["destination_relative_pcs_xyz"] = json!(xyz);
        }
        samples.push(sample);
    }
    let mut result = json!({"source":connection.source.receipt,"destination":connection.destination.receipt,"intent":intent,"connection":"explicit_directional_profile_tables;declared_PCS_domain_connection;no_optional_black_point_compensation","pcs_adjustment":{"model":connection.adjustment,"scale":connection.scale,"offset":connection.offset},"samples":samples,"source_changed":false});
    if let Some(mode) = gamut_mode {
        result["gamut"] = if let Some((table, transform)) = diagnostic {
            json!({"status":"available","profile":table.receipt(),"intent":diagnostic_intent,"source":transform.source.receipt,"destination":transform.destination.receipt,"connection":"source_colourimetric_PCS_to_destination_relative_PCS;media_white_scaling_once","claim":"supplied_profile_classification;not_clipping_or_roundtrip_drift"})
        } else {
            json!({"status":if matches!(mode,gamut::Mode::Off) {"off"} else {"unavailable"},"claim":"no_gamut_membership_claim"})
        };
    }
    Ok(result)
}
