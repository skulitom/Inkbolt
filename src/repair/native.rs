//! Bounded typed views for the shared repair algorithms. Global coordinates and
//! sorted cell addresses keep disjoint move destinations local and deterministic.
use super::*;
use crate::sample_store::{Region, Spec, TILE_EDGE};
use std::collections::BTreeMap;

fn checked_region(r: &retouch::Region, spec: Spec) -> Result<Region, Error> {
    if r.width == 0
        || r.height == 0
        || r.x as u64 + r.width as u64 > spec.width as u64
        || r.y as u64 + r.height as u64 > spec.height as u64
    {
        return Err(invalid(
            "Repair region must be nonempty and inside its native grid",
        ));
    }
    Ok(Region {
        x: r.x,
        y: r.y,
        width: r.width,
        height: r.height,
    })
}

fn clip(b: [i64; 4], spec: Spec) -> Region {
    let x = b[0].clamp(0, spec.width as i64) as u32;
    let y = b[1].clamp(0, spec.height as i64) as u32;
    let x1 = b[2].clamp(x as i64, spec.width as i64) as u32;
    let y1 = b[3].clamp(y as i64, spec.height as i64) as u32;
    Region {
        x,
        y,
        width: x1 - x,
        height: y1 - y,
    }
}

fn expanded(r: Region, radius: u32, offset: [i32; 2], spec: Spec) -> Region {
    let x = r.x as i64 + offset[0] as i64;
    let y = r.y as i64 + offset[1] as i64;
    let halo = radius as i64;
    clip(
        [
            x - halo,
            y - halo,
            x + r.width as i64 + halo,
            y + r.height as i64 + halo,
        ],
        spec,
    )
}

pub(super) fn inputs<'a>(
    document: &Document,
    index: usize,
    o: &Options,
    root: Option<&'a Path>,
    work: &mut Work<'_>,
) -> Result<Option<(Grid<'a>, Grid<'a>)>, Error> {
    let id = match &o.action {
        Action::Patch { source_id, .. } => source_id,
        Action::Fill { fill } | Action::Move { fill, .. } => &fill.source_id,
        Action::EdgeCorrect { guide_id, .. } => guide_id,
    };
    let source_index = scene::index(document, id)?;
    let target_content = &document.items[index].content;
    let source_content = &document.items[source_index].content;
    let native = |c: &Content| matches!(c, Content::Samples { .. } | Content::StoredSamples { .. });
    if !native(target_content) && !native(source_content) {
        return Ok(None);
    }
    crate::pixel_warps::reject_native(&document.items[index])?;
    crate::pixel_warps::reject_native(&document.items[source_index])?;
    let spec = typed::spec(target_content)?;
    let source_spec = typed::spec(source_content)?;
    let region = checked_region(&o.region, spec)?;
    if region.width as u64 * region.height as u64 > crate::sample_store::MAX_REGION_PIXELS {
        return Err(limit("Repair exceeds the native local edit region limit"));
    }
    let mut target_regions = Vec::new();
    let source_regions = match &o.action {
        Action::Patch {
            source_origin,
            search_radius,
            context_radius,
            max_context_rms,
            ..
        } => {
            if *search_radius > bounds::MAX_SEARCH_RADIUS
                || !(1..=bounds::MAX_CONTEXT_RADIUS).contains(context_radius)
                || !unit(*max_context_rms)
                || source_origin.iter().any(|&v| f64::from(v) > MAX_COORDINATE)
            {
                return Err(invalid(
                    "Patch requires bounded radii, source origin and context RMS",
                ));
            }
            target_regions.push(expanded(region, *context_radius, [0, 0], spec));
            let halo = (*search_radius + *context_radius) as i64;
            let [x, y] = source_origin.map(i64::from);
            vec![clip(
                [
                    x - halo,
                    y - halo,
                    x + region.width as i64 + halo,
                    y + region.height as i64 + halo,
                ],
                source_spec,
            )]
        }
        Action::Fill { fill } | Action::Move { fill, .. } => {
            validate_fill(fill)?;
            target_regions.push(expanded(region, fill.patch_radius, [0, 0], spec));
            if let Action::Move { offset, .. } = &o.action {
                // Destination only needs its boundary. Do not allocate the gap
                // between distant source and destination rectangles.
                target_regions.push(expanded(region, 1, *offset, spec));
            }
            vec![match &fill.donor_region {
                Some(r) => checked_region(r, source_spec)?,
                None => Region {
                    x: 0,
                    y: 0,
                    width: source_spec.width,
                    height: source_spec.height,
                },
            }]
        }
        Action::EdgeCorrect {
            radius,
            range_sigma,
            max_change_rms,
            minimum_effective_samples,
            ..
        } => {
            if !(1..=bounds::MAX_GUIDE_RADIUS).contains(radius)
                || !range_sigma.is_finite()
                || !(bounds::MIN_RANGE_SIGMA..=1.0).contains(range_sigma)
                || !unit(*max_change_rms)
                || !minimum_effective_samples.is_finite()
                || !(1.0..=f64::from(bounds::MAX_EFFECTIVE_SAMPLES))
                    .contains(minimum_effective_samples)
            {
                return Err(invalid(
                    "Edge correction requires bounded radius, range sigma, change RMS and effective support",
                ));
            }
            if spec.width != source_spec.width || spec.height != source_spec.height {
                return Err(invalid(
                    "Guide and target native grids must have the same dimensions",
                ));
            }
            target_regions.push(expanded(region, *radius, [0, 0], spec));
            target_regions.clone()
        }
    };
    let cells = target_regions
        .iter()
        .chain(&source_regions)
        .map(|r| r.width as u64 * r.height as u64)
        .sum::<u64>();
    let replacement = target_regions
        .iter()
        .filter(|r| r.width > 0 && r.height > 0)
        .map(|r| typed::replacement_memory(target_content, *r))
        .sum::<u64>();
    let memory = cells * bounds::WORKING_BYTES_PER_PIXEL
        + bounds::FIXED_WORKING_BYTES
        + crate::selections::selection_memory(document, o.use_selection)
        + typed::memory(target_content)
        + replacement
        + if source_index != index {
            typed::memory(source_content)
        } else {
            0
        };
    if memory > bounds::MAX_MEMORY_BYTES {
        return Err(limit(
            "Repair windows, donor search and replacement blocks exceed the processing memory bound; narrow the region or provide a smaller explicit donor_region",
        ));
    }
    let target_reader =
        typed::Pixels::new(target_content, root, "UNSUPPORTED_REPAIR_ENCODING", work)?;
    let source_reader = if source_index == index {
        target_reader.clone()
    } else {
        typed::Pixels::new(source_content, root, "UNSUPPORTED_REPAIR_ENCODING", work)?
    };
    let target = read(target_reader, positions(&target_regions, spec, work)?, work)?;
    let source = read(
        source_reader,
        positions(&source_regions, source_spec, work)?,
        work,
    )?;
    Ok(Some((target, source)))
}

fn positions(regions: &[Region], spec: Spec, work: &mut Work<'_>) -> Result<Vec<usize>, Error> {
    let mut cells = Vec::new();
    for r in regions {
        for y in r.y..r.y + r.height {
            work.control.check()?;
            cells.extend(
                (r.x..r.x + r.width).map(|x| y as usize * spec.width as usize + x as usize),
            );
        }
    }
    cells.sort_unstable();
    cells.dedup();
    Ok(cells)
}

fn read<'a>(
    mut reader: typed::Pixels<'a>,
    cells: Vec<usize>,
    work: &mut Work<'_>,
) -> Result<Grid<'a>, Error> {
    work.add(cells.len())?;
    let w = reader.spec.width as usize;
    let stride = reader.stride();
    let mut bytes = Vec::with_capacity(cells.len() * stride);
    let mut pixels = Vec::with_capacity(cells.len());
    for (position, &i) in cells.iter().enumerate() {
        if position % crate::limits::retouch::SAMPLE_CHECK_INTERVAL == 0 {
            work.control.check()?;
        }
        let raw = reader.raw(i % w, i / w, work)?;
        bytes.extend_from_slice(&raw[..stride]);
        pixels.push(typed::premultiplied(&raw, reader.spec));
    }
    Ok(Grid {
        w,
        h: reader.spec.height as usize,
        bytes,
        pixels,
        locations: Some(cells),
        identity: reader.identity.clone(),
        reader: Some(reader),
    })
}

pub(super) fn reload<'a>(
    content: &Content,
    before: &Grid,
    root: Option<&'a Path>,
    work: &mut Work<'_>,
) -> Result<Grid<'a>, Error> {
    let reader = typed::Pixels::new(content, root, "UNSUPPORTED_REPAIR_ENCODING", work)?;
    read(reader, before.locations.as_ref().unwrap().clone(), work)
}

pub(super) fn write(
    document: &mut Document,
    index: usize,
    target: &Grid,
    bytes: &[u8],
    changed: &[usize],
    work: &mut Work<'_>,
) -> Result<String, Error> {
    if changed.is_empty() {
        return Ok(target.hash());
    }
    let mut reader = target.reader.as_ref().unwrap().clone();
    let stride = reader.stride();
    let edge = TILE_EDGE as usize;
    let mut blocks = BTreeMap::<(usize, usize), [usize; 4]>::new();
    for &i in changed {
        let [x, y] = target.xy(i);
        let b = blocks
            .entry((y / edge, x / edge))
            .or_insert([x, y, x + 1, y + 1]);
        *b = [b[0].min(x), b[1].min(y), b[2].max(x + 1), b[3].max(y + 1)];
    }
    let mut replacements = Vec::new();
    for b in blocks.values() {
        let region = Region {
            x: b[0] as u32,
            y: b[1] as u32,
            width: (b[2] - b[0]) as u32,
            height: (b[3] - b[1]) as u32,
        };
        work.add(region.width as usize * region.height as usize)?;
        let mut data = Vec::with_capacity(region.width as usize * region.height as usize * stride);
        for y in b[1]..b[3] {
            work.control.check()?;
            for x in b[0]..b[2] {
                if let Some(i) = target.at(x as i64, y as i64) {
                    data.extend_from_slice(&bytes[i * stride..(i + 1) * stride]);
                } else {
                    // Disjoint windows in one block may enclose unvisited cells.
                    data.extend_from_slice(&reader.raw(x, y, work)?[..stride]);
                }
            }
        }
        replacements.push((region, data));
    }
    let borrowed: Vec<_> = replacements
        .iter()
        .map(|(r, v)| (*r, v.as_slice()))
        .collect();
    let (content, identity) =
        reader.replace_regions(&document.items[index].content, &borrowed, work)?;
    document.items[index].content = content;
    Ok(identity)
}
