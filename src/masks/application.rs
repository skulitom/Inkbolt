//! Whole native image alpha application without color conversion or full frames.
use super::*;
use crate::{control::Control, sample_store::Spec, samples::Depth};

fn row(
    bytes: &mut [u8],
    y: u32,
    spec: Spec,
    mask: &Prepared,
    world: Matrix,
    control: &Control,
) -> Result<(), Error> {
    let unit = spec.depth.bytes();
    let channels = spec.channels.count();
    for (x, pixel) in bytes.chunks_exact_mut(unit * channels).enumerate() {
        if x.is_multiple_of(crate::limits::control::PIXEL_CHECK_INTERVAL) {
            control.check()?;
        }
        let coverage = mask
            .sample(geometry::map(world, [x as f64 + 0.5, y as f64 + 0.5]))?
            .clamp(0.0, 1.0);
        if coverage == 1.0 {
            continue;
        }
        let alpha = &mut pixel[(channels - 1) * unit..];
        match spec.depth {
            Depth::U8 => alpha[0] = (alpha[0] as f64 * coverage).round() as u8,
            Depth::U16 => {
                let value = u16::from_le_bytes(alpha.try_into().unwrap());
                alpha.copy_from_slice(&((value as f64 * coverage).round() as u16).to_le_bytes());
            }
            Depth::F32 => {
                let value = f32::from_le_bytes(alpha.try_into().unwrap());
                alpha.copy_from_slice(&((value as f64 * coverage) as f32).to_le_bytes());
            }
        }
    }
    Ok(())
}

pub(super) fn apply(
    content: &Content,
    mask: &Prepared,
    world: Matrix,
    root: Option<&Path>,
    control: &Control,
) -> Result<Option<Content>, Error> {
    match content {
        Content::StoredSamples { grid } => {
            if grid.storage_version != 2 {
                return Err(Error::new(
                    "MIGRATION_REQUIRED",
                    "Explicitly migrate the native layer to block storage version 2 before whole-image mask application",
                ));
            }
            let source = grid.prepare(root, control)?;
            let spec = source.manifest().spec;
            let mut rows = crate::sample_store::private::Rows::new(source.clone(), root);
            let result = source.map_private_rows(control, |y, bytes| {
                rows.read(y, bytes, control)?;
                row(bytes, y, spec, mask, world, control)
            })?;
            let mut next = grid.clone();
            next.set_candidate(result)?;
            next.validate()?;
            Ok(Some(Content::StoredSamples { grid: next }))
        }
        Content::Samples { grid } => {
            grid.validate()?;
            let spec = Spec {
                width: grid.width,
                height: grid.height,
                depth: grid.depth,
                channels: grid.channels,
                encoding: grid.encoding,
            };
            let mut bytes = crate::render::unhex(&grid.data_hex);
            for (y, bytes) in bytes
                .chunks_exact_mut(spec.width as usize * spec.stride())
                .enumerate()
            {
                row(bytes, y as u32, spec, mask, world, control)?;
            }
            let mut next = grid.clone();
            next.data_hex = crate::render::hex(&bytes);
            Ok(Some(Content::Samples { grid: next }))
        }
        _ => Ok(None),
    }
}
