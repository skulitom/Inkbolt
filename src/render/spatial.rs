//! Conservative per-tile scene membership; composition retains authored order.
use super::*;
pub const EDGE: u32 = 8;
pub const MAX_REFERENCES: u64 = 1_048_576;

#[derive(Default)]
pub(super) struct Tile {
    pub children: BTreeMap<usize, Vec<usize>>,
}
pub(super) struct Plan {
    pub coverage: coverage_cache::Cache,
    pub worlds: Vec<Matrix>,
    pub parents: Vec<usize>,
    ids: BTreeMap<String, usize>,
    cells: Vec<Vec<usize>>,
    columns: u32,
    size: [u32; 2],
    pub pixels: Vec<u64>,
    pub work: u64,
    pub paint_work: u64,
    pub buffer_values: u64,
    pub clipped_layers: Vec<Vec<usize>>,
    pub clipped_adjustments: Vec<Vec<usize>>,
}
impl Plan {
    pub fn new(
        document: &Document,
        texts: &BTreeMap<String, crate::text::Layout>,
        size: [u32; 3],
        offset: u32,
        antialias: crate::render_quality::Antialias,
        control: &crate::control::Control,
    ) -> Result<Self, Error> {
        let [width, height, scale] = size;
        let n = document.items.len();
        let ids: BTreeMap<_, _> = document
            .items
            .iter()
            .enumerate()
            .map(|(i, item)| (item.id.clone(), i))
            .collect();
        let parents: Vec<_> = document
            .items
            .iter()
            .map(|item| item.parent.as_ref().map_or(n, |id| ids[id]))
            .collect();
        let worlds = (0..n)
            .map(|i| scene::world_transform(document, i))
            .collect::<Result<Vec<_>, _>>()?;
        let mut bounds = vec![None; n];
        let mut controls = vec![0u64; n];
        for (i, item) in document.items.iter().enumerate() {
            control.check()?;
            if !scene::effective_visible(document, i)? {
                continue;
            }
            let mut include = |g: &Geometry, m: Matrix| {
                controls[i] += if matches!(g, Geometry::Ellipse { .. }) {
                    97
                } else {
                    geometry::control_points(g).len() as u64
                };
                for p in geometry::control_points(g) {
                    let p = geometry::map(m, p).map(|v| v * scale as f64);
                    union(&mut bounds[i], [p[0], p[1], p[0], p[1]]);
                }
            };
            match &item.content {
                Content::Vector {
                    geometry,
                    fill,
                    stroke,
                    ..
                } => {
                    if fill.is_some() {
                        include(geometry, worlds[i]);
                    }
                    if let Some(stroke) = stroke
                        && let Some(outline) =
                            crate::strokes::generate_placed(geometry, stroke, worlds[i])?
                    {
                        include(&outline, stroke.scaling.matrix(worlds[i]));
                    }
                }
                Content::Text { .. } | Content::StoryFrame { .. } => {
                    for p in &texts[&item.id].paths {
                        include(&p.geometry, worlds[i]);
                    }
                }
                Content::Frame { frame } => {
                    if frame.background.is_some() {
                        include(&frame.geometry(), worlds[i]);
                    }
                }
                Content::Group { .. } | Content::WorkPath { .. } | Content::MaskSource {} => {}
                Content::Adjustment { .. } => {
                    bounds[i] = Some([0., 0., width as f64, height as f64])
                }
                Content::Fill { width, height, .. } => include(
                    &Geometry::Rect {
                        x: 0.,
                        y: 0.,
                        width: *width as f64,
                        height: *height as f64,
                    },
                    worlds[i],
                ),
                Content::Raster { .. }
                | Content::Samples { .. }
                | Content::StoredSamples { .. }
                | Content::Image { .. } => {
                    if let Some(warp) = crate::pixel_warps::plan(item)? {
                        include(&warp.geometry(), worlds[i]);
                    } else {
                        controls[i] += 4;
                        let b = geometry::item_bounds(&Item {
                            transform: worlds[i],
                            ..item.clone()
                        })?;
                        bounds[i] = Some(b.map(|v| v * scale as f64));
                    }
                }
                _ => {
                    return Err(Error::new(
                        "UNSUPPORTED_TILED_RENDER",
                        "Expanded content has no conservative spatial bounds",
                    )
                    .at_item(&item.id));
                }
            }
            if crate::backgrounds::matte(document, &item.id).is_some() {
                bounds[i] = Some([0., 0., width as f64, height as f64]);
            }
            if let Some(clip) = &item.clip {
                controls[i] += geometry::control_points(&clip.geometry).len() as u64;
            }
        }
        // Each descendant's own footprint contributes to every ancestor. No
        // document-storage ordering or mask/clip shrinking assumption is used.
        for i in 0..n {
            if let Some(b) = bounds[i] {
                let mut p = parents[i];
                while p != n {
                    union(&mut bounds[p], b);
                    p = parents[p];
                }
            }
        }
        let columns = width.div_ceil(EDGE);
        let mut cells = vec![Vec::new(); columns as usize * height.div_ceil(EDGE) as usize];
        let mut pixels = vec![0; n];
        let mut references = 0;
        let mut work = width as u64 * height as u64;
        let mut paint_work = 0;
        let phase = if offset.is_multiple_of(EDGE) { 1 } else { 4 };
        for (i, item) in document.items.iter().enumerate() {
            control.check()?;
            let Some(b) = bounds[i] else {
                continue;
            };
            if b.iter().any(|v| !v.is_finite()) {
                return Err(limit("Spatial render bounds are not finite"));
            }
            let [x0, y0, x1, y1] = [
                (b[0].floor() - 2.).clamp(0., width as f64) as u32,
                (b[1].floor() - 2.).clamp(0., height as f64) as u32,
                (b[2].ceil() + 2.).clamp(0., width as f64) as u32,
                (b[3].ceil() + 2.).clamp(0., height as f64) as u32,
            ];
            if x1 <= x0 || y1 <= y0 {
                continue;
            }
            let refs =
                (x1.div_ceil(EDGE) - x0 / EDGE) as u64 * (y1.div_ceil(EDGE) - y0 / EDGE) as u64;
            references += refs;
            if references > MAX_REFERENCES {
                return Err(limit("Spatial render index exceeds tile membership limit"));
            }
            pixels[i] = refs * EDGE as u64 * EDGE as u64 * phase;
            let paint = match &item.content {
                Content::Vector { fill, stroke, .. } => fill
                    .iter()
                    .chain(stroke.iter().map(|s| &s.color))
                    .map(crate::paint::work)
                    .sum(),
                Content::Fill { paint, .. } => crate::paint::work(paint),
                Content::Text { .. } | Content::StoryFrame { .. } => texts[&item.id]
                    .paths
                    .iter()
                    .map(|p| crate::paint::work(&p.fill))
                    .sum(),
                Content::Adjustment { adjustment } => adjustment.work(),
                _ => 1,
            } + if item.mask.as_ref().is_some_and(|m| m.enabled) {
                4
            } else {
                0
            };
            paint_work += pixels[i] * paint;
            let passes = texts.get(&item.id).map_or(1, |t| 1 + t.paths.len()) as u64;
            let shape = if crate::knockout::active(document) {
                24
            } else {
                0
            };
            work +=
                pixels[i] * (2 + passes + paint + shape) + refs * EDGE as u64 * controls[i] * phase;
            if work > MAX_RENDER_WORK || paint_work > crate::paint::MAX_PAINT_WORK {
                return Err(limit("Spatial render exceeds visited tile work limit"));
            }
            for y in y0 / EDGE..y1.div_ceil(EDGE) {
                for x in x0 / EDGE..x1.div_ceil(EDGE) {
                    cells[(y * columns + x) as usize].push(i);
                }
            }
        }
        let mut siblings = vec![Vec::new(); n + 1];
        for (i, &parent) in parents.iter().enumerate() {
            siblings[parent].push(i);
        }
        let mut clipped_layers = vec![Vec::new(); n];
        let mut clipped_adjustments = vec![Vec::new(); n];
        for group in siblings {
            for (pos, &i) in group.iter().enumerate() {
                if !crate::layer_clipping::drawable(&document.items[i].content) {
                    continue;
                }
                for &j in &group[pos + 1..] {
                    if crate::layer_clipping::auxiliary(&document.items[j].content) {
                        continue;
                    }
                    if document.items[j].clip_to.as_deref() != Some(&document.items[i].id) {
                        break;
                    }
                    clipped_layers[i].push(j);
                }
                for &j in &group[pos + 1..] {
                    if matches!(
                        document.items[j].content,
                        Content::WorkPath { .. } | Content::MaskSource {}
                    ) {
                        continue;
                    }
                    if !matches!(&document.items[j].content,Content::Adjustment{adjustment} if adjustment.clip_to.is_some())
                    {
                        break;
                    }
                    clipped_adjustments[i].push(j);
                }
            }
        }
        let index_values = references * 8 + cells.len() as u64 * 4 + n as u64 * 24;
        if index_values > MAX_BUFFER_PIXELS * 4 {
            return Err(limit("Spatial render index exceeds memory limit"));
        }
        let coverage = coverage_cache::Cache::new(
            document,
            texts,
            &worlds,
            size,
            antialias,
            control,
            [MAX_RENDER_WORK - work, MAX_BUFFER_PIXELS * 4 - index_values],
        )?;
        work += coverage.work;
        if work > MAX_RENDER_WORK {
            return Err(limit("Spatial coverage preparation exceeds work limit"));
        }
        let buffer_values = index_values + coverage.buffer_values;
        Ok(Self {
            coverage,
            worlds,
            parents,
            ids,
            cells,
            columns,
            size: [width, height],
            pixels,
            work,
            paint_work,
            buffer_values,
            clipped_layers,
            clipped_adjustments,
        })
    }
    pub fn parent(&self, parent: Option<&str>) -> usize {
        parent.map_or(self.parents.len(), |p| self.ids[p])
    }
    pub fn tile(&self, origin: [u32; 2], size: [u32; 2]) -> Tile {
        let mut indices = Vec::new();
        for y in origin[1] / EDGE..(origin[1] + size[1]).min(self.size[1]).div_ceil(EDGE) {
            for x in origin[0] / EDGE..(origin[0] + size[0]).min(self.size[0]).div_ceil(EDGE) {
                indices.extend_from_slice(&self.cells[(y * self.columns + x) as usize]);
            }
        }
        indices.sort_unstable();
        indices.dedup();
        let mut tile = Tile::default();
        for i in indices {
            tile.children.entry(self.parents[i]).or_default().push(i);
        }
        tile
    }
}
fn union(target: &mut Option<geometry::Bounds>, b: geometry::Bounds) {
    if let Some(a) = target {
        *a = [
            a[0].min(b[0]),
            a[1].min(b[1]),
            a[2].max(b[2]),
            a[3].max(b[3]),
        ];
    } else {
        *target = Some(b);
    }
}
