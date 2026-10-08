//! Original logical vector viewports; pixel storage is a derived bounded preview grid.
use crate::{Error, dimensions::Unit, geometry, model::*};
use num_rational::BigRational;
use num_traits::ToPrimitive;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum ProcessSpace {
    #[default]
    Rgb,
    Cmyk,
}
#[derive(Clone, Copy, Debug, PartialEq, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Canvas {
    pub origin_px: Point,
    pub size_px: Point,
    #[serde(default)]
    pub unit: Unit,
    #[serde(default)]
    pub process_space: ProcessSpace,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Action {
    Set {
        origin: Point,
        size: Point,
        #[serde(default)]
        unit: Unit,
        #[serde(default)]
        process_space: ProcessSpace,
    },
    Unit {
        unit: Unit,
    },
    Clear {},
}
fn invalid(message: &str) -> Error {
    Error::new("INVALID_CANVAS", message)
}
fn convert(value: f64, unit: Unit, ppi: f64, to_pixels: bool) -> Result<f64, Error> {
    let value =
        BigRational::from_float(value).ok_or_else(|| invalid("Canvas values must be finite"))?;
    let factor = unit.exact(ppi);
    let value = if to_pixels {
        value * factor
    } else {
        value / factor
    };
    value
        .to_f64()
        .filter(|v| v.is_finite())
        .ok_or_else(|| invalid("Canvas conversion exceeds finite precision"))
}
impl Canvas {
    pub fn svg_dimensions(self, ppi: f64) -> Result<[String; 2], Error> {
        let suffix = match self.unit {
            Unit::Px => "px",
            Unit::Pt => "pt",
            Unit::Pc => "pc",
            Unit::Mm => "mm",
            Unit::Cm => "cm",
            Unit::In => "in",
        };
        // SVG CSS pixels have a fixed physical scale. Document logical pixels
        // instead use the document's saved resolution.
        let value = |v| -> Result<String, Error> {
            Ok(format!(
                "{}{suffix}",
                if matches!(self.unit, Unit::Px) {
                    v * 96.0 / ppi
                } else {
                    convert(v, self.unit, ppi, false)?
                }
            ))
        };
        Ok([value(self.size_px[0])?, value(self.size_px[1])?])
    }
    pub fn dimensions(self) -> Result<[u32; 2], Error> {
        if self
            .origin_px
            .iter()
            .chain(&self.size_px)
            .any(|v| !v.is_finite())
            || self
                .size_px
                .iter()
                .any(|v| *v < 0.000001 || *v > MAX_DIMENSION as f64)
            || (0..2).any(|i| {
                self.origin_px[i].abs() > MAX_COORDINATE
                    || (self.origin_px[i] + self.size_px[i]).abs() > MAX_COORDINATE
            })
        {
            return Err(invalid(
                "Canvas origin and far edges must stay within coordinate limits; sizes must be between 0.000001 and 32768 logical pixels",
            ));
        }
        Ok(self.size_px.map(|v| v.ceil() as u32))
    }
    pub fn receipt(self, ppi: f64) -> Result<Value, Error> {
        Ok(
            json!({"origin_px":self.origin_px,"size_px":self.size_px,"unit":self.unit,"origin_in_unit":[convert(self.origin_px[0],self.unit,ppi,false)?,convert(self.origin_px[1],self.unit,ppi,false)?],"size_in_unit":[convert(self.size_px[0],self.unit,ppi,false)?,convert(self.size_px[1],self.unit,ppi,false)?],"process_space":self.process_space,"preview_storage":self.dimensions()?,"coordinates":"artwork_stays_in_logical_pixels;unit_is_a_display_preference","colour":"typed_paint_declarations_unchanged;CMYK_page_delivery_requires_explicit_native_or_profiled_inks","source_changed":false}),
        )
    }
}
pub fn validate(document: &Document) -> Result<(), Error> {
    if let Some(canvas) = document.vector_canvas {
        if document.kind != DocumentKind::Vector || document.color_space != ColorSpace::Srgb {
            return Err(invalid(
                "A logical vector canvas requires an encoded vector document",
            ));
        }
        if canvas.dimensions()? != [document.width, document.height] {
            return Err(invalid(
                "Pixel storage dimensions must equal the ceiling of the logical canvas size",
            ));
        }
    }
    Ok(())
}
pub fn apply(document: &mut Document, action: &Action) -> Result<Value, Error> {
    if document.kind != DocumentKind::Vector {
        return Err(invalid("Vector canvas edits require a vector document"));
    }
    let before = document.vector_canvas;
    match action {
        Action::Set {
            origin,
            size,
            unit,
            process_space,
        } => {
            let canvas = Canvas {
                origin_px: [
                    convert(origin[0], *unit, document.resolution_ppi, true)?,
                    convert(origin[1], *unit, document.resolution_ppi, true)?,
                ],
                size_px: [
                    convert(size[0], *unit, document.resolution_ppi, true)?,
                    convert(size[1], *unit, document.resolution_ppi, true)?,
                ],
                unit: *unit,
                process_space: *process_space,
            };
            [document.width, document.height] = canvas.dimensions()?;
            document.vector_canvas = Some(canvas);
        }
        Action::Unit { unit } => {
            let canvas = document.vector_canvas.get_or_insert(Canvas {
                origin_px: [0.0; 2],
                size_px: [document.width as f64, document.height as f64],
                unit: *unit,
                process_space: ProcessSpace::Rgb,
            });
            canvas.unit = *unit;
        }
        Action::Clear {} => {
            document.vector_canvas = None;
        }
    }
    validate(document)?;
    Ok(
        json!({"before":before,"after":document.vector_canvas,"artwork_changed":false,"paint_declarations_changed":false,"unit_change_rescales_artwork":false}),
    )
}
pub(crate) fn logical_size(document: &Document) -> Point {
    document
        .vector_canvas
        .map_or([document.width as f64, document.height as f64], |c| {
            c.size_px
        })
}
pub(crate) fn bounds(document: &Document) -> [f64; 4] {
    let origin = document.vector_canvas.map_or([0.0; 2], |c| c.origin_px);
    let size = logical_size(document);
    [
        origin[0],
        origin[1],
        origin[0] + size[0],
        origin[1] + size[1],
    ]
}
pub(crate) fn reject_rgb_page(document: &Document) -> Result<(), Error> {
    if document
        .vector_canvas
        .is_some_and(|c| c.process_space == ProcessSpace::Cmyk)
    {
        return Err(Error::new(
            "COLOR_POLICY_REQUIRED",
            "A CMYK canvas requires explicit native ink or profile-managed page delivery; an RGB page cannot silently replace its process interpretation",
        ));
    }
    Ok(())
}
/// A temporary evaluation copy only. Shared definitions keep their own coordinates.
pub(crate) fn translated(document: &Document, offset: Point) -> Result<Document, Error> {
    let mut out = document.clone();
    out.vector_canvas = None;
    out.variants = None;
    let shift = [1.0, 0.0, 0.0, 1.0, offset[0], offset[1]];
    for (i, item) in out.items.iter_mut().enumerate() {
        if crate::instances::source_owner(document, i)?.is_some()
            || crate::artwork_masks::source_owner(document, i)?.is_some()
        {
            continue;
        }
        if item.parent.is_none() {
            item.transform = geometry::multiply(shift, item.transform);
        }
        for mask in item
            .mask
            .iter_mut()
            .chain(item.filters.iter_mut().filter_map(|f| f.mask.as_mut()))
        {
            if !mask.linked {
                mask.transform = geometry::multiply(shift, mask.transform);
            }
        }
        if let Some(mask) = item.artwork_mask.as_mut().filter(|m| !m.linked) {
            mask.transform = geometry::multiply(shift, mask.transform);
        }
    }
    Ok(out)
}
