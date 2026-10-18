//! Exact union of dilated coarse transitions, without a full native label plane.
use super::*;
use std::collections::BTreeMap;

#[derive(Debug)]
pub(super) struct Run {
    pub x: u32,
    pub end: u32,
    pub offset: usize,
}

pub(super) struct Band {
    pub rows: Vec<Vec<Run>>,
    pub coordinates: Vec<[u32; 2]>,
}

impl Band {
    pub fn index(&self, x: u32, y: u32) -> Option<usize> {
        let row = self.rows.get(y as usize)?;
        let at = row.partition_point(|run| run.x <= x).checked_sub(1)?;
        let run = &row[at];
        (x < run.end).then_some(run.offset + (x - run.x) as usize)
    }

    pub fn new(
        grid: &Grid,
        labels: &[bool],
        radius: u32,
        work: &mut Work<'_>,
    ) -> Result<Self, Error> {
        // Each rectangle contributes one add and one remove event. Sorting the
        // original intervals gives deterministic union runs, including overlaps.
        let mut events = BTreeMap::<u32, Vec<((u32, u32), i32)>>::new();
        let mut rectangle = |x0: u32, y0: u32, x1: u32, y1: u32| {
            events.entry(y0).or_default().push(((x0, x1), 1));
            events.entry(y1).or_default().push(((x0, x1), -1));
        };
        for cy in 0..grid.rows {
            for cx in 0..grid.columns {
                work.add(2)?;
                let i = grid.index(cx, cy);
                let (x0, y0, x1, y1) = grid.cell(cx, cy);
                if cx + 1 < grid.columns && labels[i] != labels[i + 1] {
                    rectangle(
                        x1.saturating_sub(radius),
                        y0.saturating_sub(radius - 1),
                        (x1 + radius).min(grid.width),
                        (y1 + radius - 1).min(grid.height),
                    );
                }
                if cy + 1 < grid.rows && labels[i] != labels[i + grid.columns as usize] {
                    rectangle(
                        x0.saturating_sub(radius - 1),
                        y1.saturating_sub(radius),
                        (x1 + radius - 1).min(grid.width),
                        (y1 + radius).min(grid.height),
                    );
                }
            }
        }
        let mut active = BTreeMap::<(u32, u32), i32>::new();
        let mut rows = Vec::with_capacity(grid.height as usize);
        let mut coordinates = Vec::new();
        for y in 0..grid.height {
            if let Some(changes) = events.remove(&y) {
                for (interval, delta) in changes {
                    work.add(1)?;
                    let count = active.entry(interval).or_default();
                    *count += delta;
                    if *count == 0 {
                        active.remove(&interval);
                    }
                }
            }
            let mut merged: Vec<(u32, u32)> = Vec::new();
            for &(start, end) in active.keys() {
                work.add(1)?;
                if let Some(last) = merged.last_mut()
                    && start <= last.1
                {
                    last.1 = last.1.max(end);
                } else {
                    merged.push((start, end));
                }
            }
            let mut row = Vec::with_capacity(merged.len());
            for (x, end) in merged {
                if coordinates.len() + (end - x) as usize > limits::MAX_REFINE_PIXELS {
                    return Err(crate::model::limit(
                        "Proxy selection boundary exceeds native refinement node limit; use a smaller region or radius",
                    ));
                }
                work.add((end - x) as u64)?;
                row.push(Run {
                    x,
                    end,
                    offset: coordinates.len(),
                });
                coordinates.extend((x..end).map(|x| [x, y]));
            }
            rows.push(row);
        }
        Ok(Self { rows, coordinates })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn union_matches_independent_native_transition_dilation() {
        let control = Control::default();
        for (width, height, step) in [(7, 5, 3), (4, 3, 2), (3, 2, 1)] {
            let grid = Grid::new(width, height, step).unwrap();
            for bits in 0..1usize << (grid.columns * grid.rows) {
                let labels: Vec<_> = (0..grid.len()).map(|i| bits & (1 << i) != 0).collect();
                for radius in 1..=3 {
                    let mut work = Work {
                        count: 0,
                        preparation: Default::default(),
                        control: &control,
                    };
                    let band = Band::new(&grid, &labels, radius, &mut work).unwrap();
                    let mut endpoints = Vec::new();
                    for y in 0..height {
                        for x in 0..width {
                            for (xx, yy) in [(x + 1, y), (x, y + 1)] {
                                if xx < width
                                    && yy < height
                                    && grid.label(&labels, x, y) != grid.label(&labels, xx, yy)
                                {
                                    endpoints.extend([[x, y], [xx, yy]]);
                                }
                            }
                        }
                    }
                    let expected: Vec<_> = (0..height)
                        .flat_map(|y| (0..width).map(move |x| [x, y]))
                        .filter(|&[x, y]| {
                            endpoints
                                .iter()
                                .any(|&[xx, yy]| x.abs_diff(xx).max(y.abs_diff(yy)) < radius)
                        })
                        .collect();
                    assert_eq!(band.coordinates, expected);
                    for y in 0..height {
                        for x in 0..width {
                            assert_eq!(
                                band.index(x, y),
                                expected.iter().position(|p| *p == [x, y])
                            );
                        }
                    }
                }
            }
        }
    }
}
