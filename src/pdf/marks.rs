//! Original physical page bounds and outside-bleed crop/registration geometry.
use super::*;
use crate::limits::pdf_marks as limits;

#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(default, deny_unknown_fields)]
pub struct Marks {
    pub crop: bool,
    pub registration: bool,
    pub gap_pt: f64,
    pub length_pt: f64,
    pub line_width_pt: f64,
    pub registration_radius_pt: f64,
}
impl Default for Marks {
    fn default() -> Self {
        Self {
            crop: true,
            registration: true,
            gap_pt: limits::DEFAULT_GAP,
            length_pt: limits::DEFAULT_LENGTH,
            line_width_pt: limits::DEFAULT_LINE_WIDTH,
            registration_radius_pt: limits::DEFAULT_REGISTRATION_RADIUS,
        }
    }
}
impl Marks {
    fn validate(self) -> Result<(), Error> {
        let bounded = |v: f64, a: f64, b: f64| v.is_finite() && (a..=b).contains(&v);
        if (!self.crop && !self.registration)
            || !bounded(self.gap_pt, limits::MIN_GAP, limits::MAX_GAP)
            || !bounded(self.length_pt, limits::MIN_LENGTH, limits::MAX_LENGTH)
            || !bounded(
                self.line_width_pt,
                limits::MIN_LINE_WIDTH,
                limits::MAX_LINE_WIDTH,
            )
            || !bounded(
                self.registration_radius_pt,
                limits::MIN_REGISTRATION_RADIUS,
                limits::MAX_REGISTRATION_RADIUS,
            )
            || self.line_width_pt * 2.0 > self.length_pt
            || (self.registration && self.line_width_pt * 2.0 > self.registration_radius_pt)
        {
            return Err(Error::new(
                "INVALID_REQUEST",
                format!(
                    "Print marks need crop or registration, gap {}..{} pt, length {}..{} pt, line width {}..{} pt and radius {}..{} pt; strokes must fit their marks",
                    limits::MIN_GAP,
                    limits::MAX_GAP,
                    limits::MIN_LENGTH,
                    limits::MAX_LENGTH,
                    limits::MIN_LINE_WIDTH,
                    limits::MAX_LINE_WIDTH,
                    limits::MIN_REGISTRATION_RADIUS,
                    limits::MAX_REGISTRATION_RADIUS
                ),
            ));
        }
        Ok(())
    }
}

pub(super) struct Layout {
    /// All rectangles and marks are stored in physical points, bottom-left.
    pub media: [f64; 4],
    pub bleed: [f64; 4],
    pub trim: [f64; 4],
    pub user_unit: f64,
    pub margin: f64,
    crop: Vec<[Point; 2]>,
    registration: Vec<Point>,
    marks: Option<Marks>,
}
impl Layout {
    pub fn new(
        size: [f64; 2],
        ppi: f64,
        bleed: boards::Insets,
        marks: Option<Marks>,
    ) -> Result<Self, Error> {
        let [w, h] = size.map(|v| v * 72.0 / ppi);
        let pad = [bleed.left, bleed.bottom, bleed.right, bleed.top].map(|v| v as f64 * 72.0 / ppi);
        let mut margin = 0.0;
        if let Some(m) = marks {
            m.validate()?;
            let required = if m.registration {
                3.0 * m.registration_radius_pt + 2.0 * m.line_width_pt
            } else {
                2.0 * m.line_width_pt
            };
            if w - pad[0] - pad[2] <= required || h - pad[1] - pad[3] <= required {
                return Err(Error::new(
                    "INVALID_REQUEST",
                    "The physical trim is too small to separate the requested print marks; reduce their size or change the physical page size",
                ));
            }
            let span = (if m.crop { m.length_pt } else { 0.0 }).max(if m.registration {
                3.0 * m.registration_radius_pt
            } else {
                0.0
            });
            margin = m.gap_pt + span + m.line_width_pt;
        }
        let media = [0.0, 0.0, w + 2.0 * margin, h + 2.0 * margin];
        let bounds = [margin, margin, margin + w, margin + h];
        let trim = [
            margin + pad[0],
            margin + pad[1],
            margin + w - pad[2],
            margin + h - pad[3],
        ];
        let user_unit = (media[2].max(media[3]) / crate::limits::pdf::MAX_PAGE_COORDINATE)
            .ceil()
            .max(1.0);
        if user_unit > f64::from(crate::limits::pdf::MAX_USER_UNIT) {
            return Err(limit("Marked PDF page exceeds physical size limits"));
        }
        let mut layout = Self {
            media,
            bleed: bounds,
            trim,
            user_unit,
            margin,
            crop: Vec::new(),
            registration: Vec::new(),
            marks,
        };
        if let Some(m) = marks {
            if m.crop {
                for y in [trim[1], trim[3]] {
                    layout.crop.push([
                        [bounds[0] - m.gap_pt - m.length_pt, y],
                        [bounds[0] - m.gap_pt, y],
                    ]);
                    layout.crop.push([
                        [bounds[2] + m.gap_pt, y],
                        [bounds[2] + m.gap_pt + m.length_pt, y],
                    ]);
                }
                for x in [trim[0], trim[2]] {
                    layout.crop.push([
                        [x, bounds[1] - m.gap_pt - m.length_pt],
                        [x, bounds[1] - m.gap_pt],
                    ]);
                    layout.crop.push([
                        [x, bounds[3] + m.gap_pt],
                        [x, bounds[3] + m.gap_pt + m.length_pt],
                    ]);
                }
            }
            if m.registration {
                let d = m.gap_pt + 1.5 * m.registration_radius_pt + 0.5 * m.line_width_pt;
                let mid = [(trim[0] + trim[2]) * 0.5, (trim[1] + trim[3]) * 0.5];
                layout.registration = vec![
                    [bounds[0] - d, mid[1]],
                    [bounds[2] + d, mid[1]],
                    [mid[0], bounds[1] - d],
                    [mid[0], bounds[3] + d],
                ];
            }
        }
        Ok(layout)
    }
    pub fn coordinates(&self, rect: [f64; 4]) -> [f64; 4] {
        rect.map(|v| v / self.user_unit)
    }
    pub fn receipt(&self) -> Value {
        json!({"units":"physical_points","coordinates":"bottom_left","margin_pt":self.margin,"settings":self.marks,"crop_segments":self.crop,"registration_centers":self.registration,"registration_arm_radius_pt":self.marks.filter(|m|m.registration).map(|m|m.registration_radius_pt*1.5),"colorant":"All","over_artwork":false})
    }
    pub fn emit(&self, writer: &mut Writer, content: &mut String) -> Result<Option<usize>, Error> {
        let Some(m) = self.marks else { return Ok(None) };
        // The special Separation name All targets every available colorant,
        // including native process and spot plates. It is never a DeviceN name.
        let tint = writer.add(
            "<< /FunctionType 2 /Domain [0 1] /C0 [0 0 0 0] /C1 [1 1 1 1] /N 1 >>".to_string(),
        )?;
        let space = writer.add(format!("[/Separation /All /DeviceCMYK {tint} 0 R]"))?;
        content.push_str(&format!(
            "q\n/Marks CS\n1 SCN\n{} w\n0 J\n0 j\n",
            number(m.line_width_pt / self.user_unit)?
        ));
        // Enter bounded PDF user coordinates before original path validation;
        // physical points may legitimately exceed scene-coordinate bounds.
        let unit = |point: Point| point.map(|v| v / self.user_unit);
        for segment in &self.crop {
            writer.path(
                content,
                &Geometry::Path {
                    commands: vec![
                        PathCommand::Move {
                            to: unit(segment[0]),
                        },
                        PathCommand::Line {
                            to: unit(segment[1]),
                        },
                    ],
                },
                identity(),
            )?;
        }
        for center in self.registration.iter().copied().map(unit) {
            let r = m.registration_radius_pt / self.user_unit;
            writer.path(
                content,
                &Geometry::Ellipse {
                    cx: center[0],
                    cy: center[1],
                    rx: r,
                    ry: r,
                },
                identity(),
            )?;
            let arm = r * 1.5;
            writer.path(
                content,
                &Geometry::Path {
                    commands: vec![
                        PathCommand::Move {
                            to: [center[0] - arm, center[1]],
                        },
                        PathCommand::Line {
                            to: [center[0] + arm, center[1]],
                        },
                        PathCommand::Move {
                            to: [center[0], center[1] - arm],
                        },
                        PathCommand::Line {
                            to: [center[0], center[1] + arm],
                        },
                    ],
                },
                identity(),
            )?;
        }
        content.push_str("S\nQ\n");
        Ok(Some(space))
    }
}
