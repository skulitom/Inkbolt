//! Recognize already opaque RGB artwork in the selected and rebased page.
use super::*;

fn rectangle(width: f64, height: f64) -> Geometry {
    Geometry::Rect {
        x: 0.,
        y: 0.,
        width,
        height,
    }
}

// Compare the actual corners. A rotated shape's bounding box, a path with
// a hole or a bow tie cannot establish that every point on the paper is inked.
fn covers(shape: &Geometry, matrix: Matrix, size: Point) -> bool {
    use PathCommand::{Close, Line, Move};
    let corners = match shape {
        Geometry::Rect {
            x,
            y,
            width,
            height,
        } => [
            [*x, *y],
            [x + width, *y],
            [x + width, y + height],
            [*x, y + height],
        ],
        Geometry::Polygon { points } => match points.as_slice() {
            [a, b, c, d] => [*a, *b, *c, *d],
            _ => return false,
        },
        Geometry::Path { commands } => match commands
            .as_slice()
            .strip_suffix(&[Close {}])
            .unwrap_or(commands)
        {
            [
                Move { to: a },
                Line { to: b },
                Line { to: c },
                Line { to: d },
            ] => [*a, *b, *c, *d],
            [
                Move { to: a },
                Line { to: b },
                Line { to: c },
                Line { to: d },
                Line { to: e },
            ] if a == e => [*a, *b, *c, *d],
            _ => return false,
        },
        _ => return false,
    };
    let [a, b, c, d] = corners.map(|p| geometry::map(matrix, p));
    let rectangular = (a[1] == b[1] && b[0] == c[0] && c[1] == d[1] && d[0] == a[0])
        || (a[0] == b[0] && b[1] == c[1] && c[0] == d[0] && d[1] == a[1]);
    rectangular && (0..2).all(|i| a[i].min(c[i]) <= 0. && a[i].max(c[i]) >= size[i])
}

fn opaque(paint: &Paint) -> bool {
    use crate::paint::Field;
    match paint {
        Paint::Solid(c) => c[3] == 255,
        Paint::Precise(c) => c.rgba[3] == 1.,
        Paint::Named(r) => r.opacity == 1. && r.overprint.is_knockout(),
        Paint::Field(Field::Linear { stops, .. } | Field::Radial { stops, .. }) => {
            stops.iter().all(|s| s.color[3] == 255)
        }
        _ => false,
    }
}

// Keep the evidence for each completed item. A knockout can reuse straight
// RGB only after a preceding item has actually established opaque coverage.
#[derive(Default)]
pub(super) struct Coverage<'a> {
    pub members: BTreeSet<&'a str>,
    pub frame_backgrounds: BTreeSet<&'a str>,
    pub document_matte: bool,
    first: Option<&'a str>,
}

impl Coverage<'_> {
    pub(super) fn receipt(&self) -> Option<Value> {
        if self.document_matte {
            Some(json!({"source":"document_matte"}))
        } else {
            self.first.map(|id| json!({"source":"item","item_id":id}))
        }
    }
}

struct Page<'a, 'b> {
    document: &'a Document,
    size: Point,
    pixels: &'b BTreeMap<String, assets::Pixels>,
    control: &'b crate::control::Control,
    coverage: Coverage<'a>,
}

impl<'a> Page<'a, '_> {
    fn collect(&mut self, parent: Option<&str>) -> Result<Option<&'a str>, Error> {
        let mut first = None;
        for i in scene::children(self.document, parent) {
            self.control.check()?;
            let item = &self.document.items[i];
            if !item.visible || !crate::backgrounds::printable(item) {
                continue;
            }
            let world = scene::world_transform(self.document, i)?;
            let image_covers = |width, height: f64| {
                let matrix = image_matrix(world, [width, height]);
                covers(&rectangle(1., 1.), matrix, self.size)
            };
            let fills_page = match &item.content {
                Content::Frame { frame } => {
                    let filled = frame.background.is_some_and(|c| c[3] == 255)
                        && covers(&frame.geometry(), world, self.size);
                    if filled {
                        self.coverage.frame_backgrounds.insert(&item.id);
                    }
                    filled
                }
                Content::Vector {
                    geometry,
                    fill: Some(p),
                    ..
                } => opaque(p) && covers(geometry, world, self.size),
                Content::Fill {
                    width,
                    height,
                    paint,
                    ..
                } => {
                    opaque(paint)
                        && covers(
                            &rectangle((*width).into(), (*height).into()),
                            world,
                            self.size,
                        )
                }
                Content::Image {
                    asset_id,
                    width,
                    height,
                    crop,
                    ..
                } if image_covers(*width, *height) => {
                    let image = &self.pixels[asset_id];
                    let crop = assets::crop(image.width, image.height, *crop)?;
                    let mut opaque = true;
                    for y in crop.y..crop.y + crop.height {
                        self.control.check()?;
                        let start = (y as usize * image.width as usize + crop.x as usize) * 4;
                        if !image.rgba[start..start + crop.width as usize * 4]
                            .as_chunks::<4>()
                            .0
                            .iter()
                            .all(|p| p[3] == 255)
                        {
                            opaque = false;
                            break;
                        }
                    }
                    opaque
                }
                Content::Raster {
                    width,
                    height,
                    rgba_hex,
                    ..
                } if image_covers((*width).into(), (*height).into()) => {
                    let mut opaque = true;
                    for row in rgba_hex.as_bytes().chunks_exact(*width as usize * 8) {
                        self.control.check()?;
                        if !row
                            .as_chunks::<8>()
                            .0
                            .iter()
                            .all(|p| p[6..].eq_ignore_ascii_case(b"ff"))
                        {
                            opaque = false;
                            break;
                        }
                    }
                    opaque
                }
                _ => false,
            };
            let child = if item.content.is_container() {
                self.collect(Some(&item.id))?
            } else {
                None
            };
            let source = if fills_page {
                Some(item.id.as_str())
            } else {
                child
            };
            if let Some(id) = source
                && item.opacity == 1.
                && item.fill_opacity == 1.
                && !item.content.is_knockout()
                && !item.mask.as_ref().is_some_and(|m| m.enabled)
                && !item.artwork_mask.as_ref().is_some_and(|m| m.enabled)
                && !item.clip.as_ref().is_some_and(|c| {
                    c.enabled
                        && !covers(
                            &c.geometry,
                            geometry::multiply(world, c.transform),
                            self.size,
                        )
                })
                && !matches!(&item.content, Content::Frame { frame } if !covers(&frame.geometry(), world, self.size))
            {
                self.coverage.members.insert(&item.id);
                first.get_or_insert(id);
            }
        }
        Ok(first)
    }
}

pub(super) fn coverage<'a>(
    document: &'a Document,
    size: Point,
    pixels: &BTreeMap<String, assets::Pixels>,
    control: &crate::control::Control,
) -> Result<Coverage<'a>, Error> {
    let mut page = Page {
        document,
        size,
        pixels,
        control,
        coverage: Coverage {
            document_matte: crate::backgrounds::visible_matte(document).is_some(),
            ..Coverage::default()
        },
    };
    page.coverage.first = page.collect(None)?;
    Ok(page.coverage)
}
