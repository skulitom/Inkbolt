use super::{MAX_IMAGE_PIXELS, Stream, Writer, number, numbers};
use crate::{
    Error,
    assets::Sampling,
    geometry, masks,
    model::{Matrix, limit},
};

/// Both fields reference one prepared grayscale form. A knockout subtree
/// needs its unweighted mask as well as the ordinary, owner-weighted state.
#[derive(Clone, Copy, Debug)]
pub(super) struct States {
    pub paint: usize,
    pub shape: usize,
}

pub(super) struct Field {
    entries: String,
    form: usize,
}

pub(super) fn gray_form(writer: &mut Writer, stream: &Stream) -> Result<usize, Error> {
    let dictionary = format!(
        "/Type /XObject /Subtype /Form /BBox [{}] /Group << /S /Transparency /CS /DeviceGray /I true >> /Resources {}",
        writer.page_bbox,
        stream.dictionary(None)
    );
    writer.form(&dictionary, stream)
}

pub(super) fn field(
    writer: &mut Writer,
    stream: Stream,
    mode: crate::artwork_masks::Mode,
    outside: f64,
) -> Result<Field, Error> {
    let form = gray_form(writer, &stream)?;
    use crate::artwork_masks::Mode;
    let entries = match mode {
        Mode::Alpha => format!("/S /Alpha /G {form} 0 R"),
        Mode::Luminance => format!("/S /Luminosity /G {form} 0 R /BC [{}]", number(outside)?),
    };
    Ok(Field { entries, form })
}

impl Field {
    // Apply owner opacity to the completed field. Setting /ca on the same
    // group invocation can apply opacity twice in readers, and wrapping a
    // pass-through group can change the backdrop seen by its children.
    pub(super) fn state(&self, writer: &mut Writer, owner_opacity: f64) -> Result<usize, Error> {
        let transfer = if owner_opacity == 1.0 {
            String::new()
        } else {
            format!(
                " /TR << /FunctionType 2 /Domain [0 1] /C0 [0] /C1 [{}] /N 1 >>",
                number(owner_opacity)?
            )
        };
        writer.mask_state(
            format!(
                "<< /Type /ExtGState /SMask << {}{transfer} >> >>",
                self.entries
            ),
            self.form,
        )
    }

    pub(super) fn states(
        &self,
        writer: &mut Writer,
        opacity: f64,
        need_shape: bool,
    ) -> Result<States, Error> {
        let paint = self.state(writer, opacity)?;
        let shape = if need_shape && opacity != 1.0 {
            self.state(writer, 1.0)?
        } else {
            paint
        };
        Ok(States { paint, shape })
    }
}

/// Returns no state when the entire field equals its constant exterior.
pub(super) fn grid_state(
    writer: &mut Writer,
    mask: &masks::Mask,
    prepared: &masks::Prepared,
    world: Matrix,
    owner_opacity: f64,
    need_shape: bool,
) -> Result<Option<States>, Error> {
    if mask.constant || mask.density == 0.0 {
        return Ok(None);
    }
    let (w, h, pad) = (prepared.width, prepared.height, f64::from(prepared.pad));
    let samples = u64::from(w) * u64::from(h);
    if writer.pixels + writer.grid_mask_samples + samples > MAX_IMAGE_PIXELS {
        return Err(limit(
            "PDF image copies and opacity grids exceed the shared sample budget",
        ));
    }
    // Visit native tiles once while writing PDF's first-dimension-fastest sample order.
    let mut data = vec![0; 2 * samples as usize];
    let mut uniform = true;
    let edge = crate::scalar_store::TILE_EDGE;
    for top in (0..h).step_by(edge as usize) {
        for left in (0..w).step_by(edge as usize) {
            for y in top..h.min(top + edge) {
                writer.control.check()?;
                for x in left..w.min(left + edge) {
                    let v = prepared.at(i64::from(x), i64::from(y))?;
                    uniform &= v == prepared.outside;
                    let offset = 2 * (y * w + x) as usize;
                    let sample = (v * f64::from(u16::MAX)).round() as u16;
                    data[offset..offset + 2].copy_from_slice(&sample.to_be_bytes());
                }
            }
        }
    }
    writer.grid_mask_samples += samples;
    if uniform {
        return Ok(None);
    }
    let mut stream = Stream {
        default_rgb: writer.default_rgb,
        content: format!(
            "{} g {} re f\n",
            number(prepared.outside)?,
            writer.page_bbox
        ),
        ..Stream::default()
    };
    let placement = mask.world_transform(world);
    match mask.sampling {
        Sampling::Nearest => {
            let id = writer.stream(&format!("/Type /XObject /Subtype /Image /Width {w} /Height {h} /ColorSpace /DeviceGray /BitsPerComponent 16 /Interpolate false"), &data)?;
            // The first PDF image row is at the top of its unit square.
            let matrix = geometry::multiply(
                placement,
                [
                    f64::from(w),
                    0.0,
                    0.0,
                    -f64::from(h),
                    -pad,
                    f64::from(h) - pad,
                ],
            );
            stream
                .content
                .push_str(&format!("{} cm\n", numbers(&matrix)?));
            stream.use_resource("XObject", id, "Do");
        }
        Sampling::Bilinear => {
            stream
                .content
                .push_str(&format!("{} cm\n", numbers(&placement)?));
            bilinear_grid(writer, &mut stream, &data, [w, h], pad)?;
        }
        _ => unreachable!("validated scalar mask sampling"),
    }
    field(
        writer,
        stream,
        crate::artwork_masks::Mode::Luminance,
        prepared.outside,
    )?
    .states(writer, owner_opacity, need_shape)
    .map(Some)
}

fn bilinear_grid(
    writer: &mut Writer,
    stream: &mut Stream,
    data: &[u8],
    [w, h]: [u32; 2],
    pad: f64,
) -> Result<(), Error> {
    // Some readers tessellate a whole function shading at a fixed resolution.
    // Overlap one interpolation cell so antialiased edges on rotated or sheared
    // patches paint the same opaque gray field on both sides of the join.
    const INTERVALS: u32 = 16;
    // Preparation supplies at least one exterior knot at either end.
    let patch_starts = |knots: u32| (0..knots - 2).step_by((INTERVALS - 1) as usize);
    let coordinate = |v: u32| f64::from(v) + 0.5 - pad;
    let mut patch = Vec::new();
    for top in patch_starts(h) {
        let bottom = (top + INTERVALS).min(h - 1);
        for left in patch_starts(w) {
            writer.control.check()?;
            let right = (left + INTERVALS).min(w - 1);
            let width = right - left + 1;
            let height = bottom - top + 1;
            patch.clear();
            for y in top..=bottom {
                let start = 2 * (y * w + left) as usize;
                patch.extend_from_slice(&data[start..start + 2 * width as usize]);
            }
            let domain = numbers(&[
                coordinate(left),
                coordinate(right),
                coordinate(top),
                coordinate(bottom),
            ])?;
            // The function domain bounds its inputs. The optional shading box
            // also bounds device painting, avoiding a page scan per patch.
            let bbox = numbers(&[
                coordinate(left),
                coordinate(top),
                coordinate(right),
                coordinate(bottom),
            ])?;
            let function = writer.stream(&format!("/FunctionType 0 /Domain [{domain}] /Range [0 1] /Size [{width} {height}] /BitsPerSample 16 /Order 1"), &patch)?;
            let shading = writer.add(format!("<< /ShadingType 1 /ColorSpace /DeviceGray /Domain [{domain}] /BBox [{bbox}] /Function {function} 0 R >>"))?;
            stream.use_resource("Shading", shading, "sh");
        }
    }
    Ok(())
}
