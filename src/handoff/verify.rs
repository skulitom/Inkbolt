use super::*;
use std::{
    fs,
    io::{Cursor, Read},
};

pub(super) fn inventory(m: &Manifest) -> Result<BTreeMap<String, &File>, Error> {
    let mut files = BTreeMap::new();
    for (file, prefix, extension) in std::iter::once((&m.source.snapshot, "source", "json"))
        .chain(std::iter::once((&m.scene, "scene", "json")))
        .chain(m.frames.iter().map(|f| (&f.image, "frame", "png")))
    {
        if !hash_valid(&file.sha256)
            || file.bytes == 0
            || file.bytes > MAX_BYTES as u64
            || file.path != format!("{prefix}-{}.{extension}", file.sha256)
        {
            return Err(invalid(
                "File identity must have a content-derived flat filename, SHA-256 and bounded nonzero byte count",
            ));
        }
        if let Some(previous) = files.insert(file.path.clone(), file)
            && previous != file
        {
            return Err(invalid("Repeated filename has conflicting identities"));
        }
    }
    if files.values().map(|f| f.bytes).sum::<u64>() + bytes(m)?.len() as u64 > MAX_BYTES as u64 {
        return Err(model::limit(
            "Handoff files exceed the aggregate byte limit",
        ));
    }
    let mut ids = std::collections::HashSet::new();
    for frame in &m.frames {
        if frame
            .id
            .as_ref()
            .is_some_and(|id| !model::valid_id(id) || !ids.insert(id))
            || frame
                .dataset
                .as_ref()
                .is_some_and(|id| !model::valid_id(id))
        {
            return Err(invalid(
                "Source frame IDs must be valid and unique, and datasets must be valid IDs",
            ));
        }
        match &m.options.selection {
            Selection::Sequence => {
                let delay = frame
                    .source_delay
                    .ok_or_else(|| invalid("Sequence frames require original delays"))?;
                let expected = Time {
                    num: delay.numerator.into(),
                    den: if delay.denominator == 0 {
                        100
                    } else {
                        delay.denominator.into()
                    },
                };
                if frame.id.is_none()
                    || frame.dataset.is_none()
                    || delay.numerator == 0
                    || frame.hold != expected
                    || m.source.sequence_plays.is_none()
                {
                    return Err(invalid(
                        "Sequence frame identity or exact source delay is inconsistent",
                    ));
                }
            }
            Selection::Still { frame_id } => {
                if &frame.id != frame_id
                    || frame.dataset.is_some() != frame_id.is_some()
                    || frame.source_delay.is_some() != frame_id.is_some()
                    || m.source.sequence_plays.is_some() != frame_id.is_some()
                {
                    return Err(invalid(
                        "Still selection must match its declared source frame",
                    ));
                }
            }
        }
    }
    Ok(files)
}

fn read(root: &Path, file: &File, control: &Control) -> Result<Vec<u8>, Error> {
    control.check()?;
    let path = root.join(&file.path);
    let mut options = fs::OpenOptions::new();
    options.read(true);
    #[cfg(windows)]
    {
        use std::os::windows::fs::OpenOptionsExt;
        options.custom_flags(0x00200000); // Read the named file, never a reparse target.
    }
    let mut handle = options.open(&path).map_err(|_| {
        Error::new(
            "IO_ERROR",
            format!("Unable to open handoff file {}", file.path),
        )
    })?;
    let metadata = handle
        .metadata()
        .map_err(|_| invalid("Unable to inspect handoff file"))?;
    #[cfg(windows)]
    let reparse = {
        use std::os::windows::fs::MetadataExt;
        metadata.file_attributes() & 0x400 != 0
    };
    #[cfg(not(windows))]
    let reparse = fs::symlink_metadata(&path)
        .map_err(|_| invalid("Unable to inspect handoff path"))?
        .file_type()
        .is_symlink();
    if reparse
        || !metadata.is_file()
        || metadata.len() != file.bytes
        || fs::canonicalize(&path)
            .map_err(|_| invalid("Unable to resolve handoff file"))?
            .parent()
            != Some(root)
    {
        return Err(Error::new(
            "SOURCE_MISMATCH",
            format!(
                "Handoff file type, location or length differs: {}",
                file.path
            ),
        ));
    }
    let mut data = Vec::new();
    let mut block = [0; 65536];
    loop {
        control.check()?;
        let count = handle
            .read(&mut block)
            .map_err(|_| invalid("Unable to read handoff file"))?;
        if count == 0 {
            break;
        }
        if data.len() + count > file.bytes as usize {
            return Err(Error::new(
                "SOURCE_MISMATCH",
                "Handoff file grew during verification",
            ));
        }
        data.extend_from_slice(&block[..count]);
    }
    if data.len() as u64 != file.bytes || assets::sha256(&data) != file.sha256 {
        return Err(Error::new(
            "SOURCE_MISMATCH",
            format!("Handoff file bytes differ: {}", file.path),
        ));
    }
    control.check()?;
    Ok(data)
}

fn png(data: &[u8], m: &Manifest) -> Result<(), Error> {
    let decoder = png::Decoder::new_with_limits(
        Cursor::new(data),
        png::Limits {
            bytes: 64 * 1024 * 1024,
        },
    );
    let mut reader = decoder
        .read_info()
        .map_err(|_| invalid("Invalid handoff PNG header"))?;
    let info = reader.info();
    if info.width != m.width
        || info.height != m.height
        || info.bit_depth != png::BitDepth::Eight
        || info.color_type != png::ColorType::Rgba
        || info.icc_profile.is_some()
        || info.animation_control.is_some()
        || info.srgb.is_none()
    {
        return Err(invalid(
            "Handoff frames require the declared size and static sRGB straight RGBA8 PNG",
        ));
    }
    let length = reader
        .output_buffer_size()
        .filter(|&n| n as u64 <= MAX_PIXELS * 4)
        .ok_or_else(|| model::limit("Decoded handoff PNG exceeds its pixel limit"))?;
    let mut pixels = vec![0; length];
    reader
        .next_frame(&mut pixels)
        .map_err(|_| invalid("Invalid handoff PNG pixels"))?;
    reader
        .finish()
        .map_err(|_| invalid("Invalid handoff PNG ending"))?;
    Ok(())
}

pub(super) fn files(pin: &Pinned, input_root: &Path, control: &Control) -> Result<(), Error> {
    assets::absolute(input_root)?;
    let root = fs::canonicalize(input_root)
        .map_err(|_| Error::new("IO_ERROR", "Handoff input_root does not exist"))?;
    if !root.is_dir() {
        return Err(invalid("Handoff input_root must be a directory"));
    }
    let m = &pin.manifest;
    // The manifest file is part of a complete delivery, not just a caller-supplied object.
    let manifest_bytes = bytes(m)?;
    let manifest_file = identity("handoff", "json", &manifest_bytes);
    if read(&root, &manifest_file, control)? != manifest_bytes {
        return Err(invalid("Manifest file differs from pinned object"));
    }
    for file in inventory(m)?.values() {
        let data = read(&root, file, control)?;
        if **file == m.source.snapshot {
            let value = crate::request::decode(&data)?;
            let document: Document = serde_json::from_value(value)
                .map_err(|_| invalid("Handoff source is not an editable document snapshot"))?;
            model::validate_controlled(&document, control)?;
            if document.id != m.source.document_id
                || document.revision != m.source.revision
                || document
                    .variants
                    .as_ref()
                    .and_then(|v| v.sequence.as_ref())
                    .map(|s| s.plays)
                    != m.source.sequence_plays
            {
                return Err(invalid(
                    "Source snapshot does not match manifest identity or play count",
                ));
            }
            let expected = clock::source_frames(&document, &m.options)?;
            let actual = m
                .frames
                .iter()
                .map(|f| (f.id.clone(), f.dataset.clone(), f.source_delay, f.hold))
                .collect::<Vec<_>>();
            let plan = crate::render_quality::Plan::for_document(
                &document,
                m.options.scale,
                m.options.render_options.as_ref(),
            )?;
            if expected != actual
                || plan.output != [m.width, m.height]
                || document.output_profile.is_some()
            {
                return Err(invalid(
                    "Source snapshot does not match declared selection, timing, dimensions or color policy",
                ));
            }
        } else if **file == m.scene {
            if data != bytes(&scene(m))? {
                return Err(invalid("Scene file differs from the declared recipe"));
            }
        } else {
            png(&data, m)?;
        }
        control.check()?;
    }
    Ok(())
}
