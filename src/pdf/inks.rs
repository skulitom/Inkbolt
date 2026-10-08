//! Original native named-ink PDF operands and resource emission.
use super::*;
use crate::swatches::{Overprint, Process, Reference};

pub(super) fn device_space(
    writer: &mut Writer,
    encoding: &crate::profiles::device::Endpoint,
) -> Result<String, Error> {
    use crate::profiles::device::Space;
    writer.explicit_black_point = true;
    if encoding.space == Space::Lab {
        return Ok("[/Lab << /WhitePoint [0.9642 1 0.8249] /Range [-128 127 -128 127] >>]".into());
    }
    let bytes = encoding.bytes()?;
    let hash = crate::assets::sha256(&bytes);
    let profile = if let Some(&id) = writer.device_profiles.get(&hash) {
        id
    } else {
        let (n, alternate) = match encoding.space {
            Space::Rgb => (3, "DeviceRGB"),
            Space::Gray => (1, "DeviceGray"),
            Space::Cmyk => (4, "DeviceCMYK"),
            Space::Lab => unreachable!(),
        };
        let id = writer.stream(&format!("/N {n} /Alternate /{alternate}"), &bytes)?;
        writer.device_profiles.insert(hash, id);
        id
    };
    Ok(format!("[/ICCBased {profile} 0 R]"))
}
fn alternate(writer: &mut Writer, color: &Process) -> Result<(String, Vec<f64>, Vec<f64>), Error> {
    Ok(match color {
        Process::Device {
            encoding,
            components,
            ..
        } => {
            let space = device_space(writer, encoding)?;
            (space, encoding.white(), components.clone())
        }
        Process::Srgb { components } => ("/DeviceRGB".into(), vec![1.0; 3], components.to_vec()),
        // The declared gray is encoded-sRGB neutral, not an unspecified gray TRC.
        Process::Gray { component } => ("/DeviceRGB".into(), vec![1.0; 3], vec![*component; 3]),
        Process::Cmyk { components, .. } => {
            ("/DeviceCMYK".into(), vec![0.0; 4], components.to_vec())
        }
        Process::Lab { components, .. } => (
            "[/Lab << /WhitePoint [0.9642 1 0.8249] /Range [-128 127 -128 127] >>]".into(),
            vec![100.0, 0.0, 0.0],
            components.to_vec(),
        ),
    })
}

pub(super) fn paint(
    writer: &mut Writer,
    stream: &mut Stream,
    reference: &Reference,
) -> Result<(), Error> {
    if !writer.native_inks {
        return Err(Error::new(
            "SWATCH_CONTEXT_REQUIRED",
            "Named ink operands require native-ink PDF mode",
        ));
    }
    let p = crate::swatches::native(&writer.swatches, reference)?;
    if writer.blend_space.is_some() && matches!(p.color, Process::Cmyk { .. }) {
        return Err(Error::new(
            "UNTAGGED_COLOR",
            "Calibrated RGB page delivery requires an explicit source profile for CMYK paint or spot alternates; assign the printing condition or use native process delivery",
        ));
    }
    if !p.overprint.is_knockout() && p.spot_id.is_none() && !matches!(p.color, Process::Cmyk { .. })
    {
        return Err(unsupported(
            "Process overprint requires explicit CMYK components; no implicit RGB/gray/Lab separation conversion is performed",
        ));
    }
    let overprint = !p.overprint.is_knockout();
    let mode = usize::from(p.overprint == Overprint::PreserveNonzero);
    let intent = match &p.color {
        Process::Device { intent, .. } => match intent {
            crate::profiles::Intent::RelativeColorimetric => " /RI /RelativeColorimetric",
            crate::profiles::Intent::AbsoluteColorimetric => " /RI /AbsoluteColorimetric",
            crate::profiles::Intent::Perceptual => " /RI /Perceptual",
            crate::profiles::Intent::Saturation => " /RI /Saturation",
        },
        _ => "",
    };
    let black_point = if matches!(p.color, Process::Device { .. }) {
        " /UseBlackPtComp /OFF"
    } else {
        ""
    };
    let gs = writer.add(format!("<< /Type /ExtGState /ca {} /CA {} /BM /Normal /SMask /None /OP {overprint} /op {overprint} /OPM {mode}{intent}{black_point} >>", number(p.opacity)?, number(p.opacity)?))?;
    stream.use_resource("ExtGState", gs, "gs");
    let (space, white, components) = alternate(writer, &p.color)?;
    if let Some(id) = &p.spot_id {
        let resource = if let Some(&resource) = writer.ink_spaces.get(id) {
            resource
        } else {
            // IDs contain only portable ASCII characters. The owned prefix also
            // prevents reserved colorant names such as All, None and Cyan.
            let function = writer.add(format!(
                "<< /FunctionType 2 /Domain [0 1] /C0 [{}] /C1 [{}] /N 1 >>",
                numbers(&white)?,
                numbers(&components)?
            ))?;
            let resource = writer.add(format!(
                "[/Separation /Inkbolt.{id} {space} {function} 0 R]"
            ))?;
            writer.ink_spaces.insert(id.clone(), resource);
            resource
        };
        stream.use_resource("ColorSpace", resource, "cs");
        stream
            .content
            .push_str(&format!("{} scn\n", number(p.tint)?));
    } else {
        let values = if p.tint == 1.0 {
            components
        } else if p.tint == 0.0 {
            white
        } else {
            white
                .iter()
                .zip(&components)
                .map(|(w, c)| w + p.tint * (c - w))
                .collect::<Vec<_>>()
        };
        match p.color {
            Process::Srgb { .. } | Process::Gray { .. } => stream
                .content
                .push_str(&format!("{} rg\n", numbers(&values)?)),
            Process::Cmyk { .. } => stream
                .content
                .push_str(&format!("{} k\n", numbers(&values)?)),
            Process::Lab { .. } | Process::Device { .. } => {
                let resource = writer.add(space)?;
                stream.use_resource("ColorSpace", resource, "cs");
                stream
                    .content
                    .push_str(&format!("{} scn\n", numbers(&values)?));
            }
        }
    }
    Ok(())
}
