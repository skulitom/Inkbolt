//! Vector transparency for a pass-through knockout group whose children need
//! the actual scene at group entry. All forms share document coordinates.
use super::*;

fn printable(item: &Item) -> bool {
    item.visible
        && !matches!(
            item.content,
            Content::WorkPath { .. } | Content::MaskSource {} | Content::ComponentSource { .. }
        )
}

pub(super) fn needed(document: &Document) -> Result<bool, Error> {
    if !document
        .items
        .iter()
        .any(|i| i.content.is_knockout() && !i.content.is_isolated())
    {
        return Ok(false);
    }
    for (i, item) in document.items.iter().enumerate() {
        if item.blend != BlendMode::Normal
            && printable(item)
            && scene::effective_visible(document, i)?
            && scene::ancestors(document, i)?
                .iter()
                .map(|&p| &document.items[p])
                .take_while(|p| !p.content.is_isolated())
                .any(|p| p.content.is_knockout())
        {
            return Ok(true);
        }
    }
    Ok(false)
}

fn stream(writer: &Writer) -> Stream {
    Stream {
        default_rgb: writer.default_rgb,
        ..Stream::default()
    }
}

fn placed(writer: &Writer, form: usize) -> Stream {
    let mut out = stream(writer);
    out.use_resource("XObject", form, "Do");
    out
}

struct Member {
    id: String,
    paint: Artwork,
    // Intrinsic alpha, with the clip and mask, before this or any descendant's owner opacity.
    shape: Option<usize>,
    opacity: f64,
    blend: BlendMode,
}

enum Artwork {
    Isolated(usize),
    Through {
        children: Vec<Member>,
        knockout: bool,
        boundary: Option<usize>,
    },
}

fn prepare(
    writer: &mut Writer,
    doc: &Document,
    parent: Option<&str>,
    res: &PageResources,
    need_shape: bool,
) -> Result<Vec<Member>, Error> {
    let mut out = Vec::new();
    for i in scene::children(doc, parent) {
        let item = &doc.items[i];
        if printable(item) {
            writer.control.check()?;
            out.push(member(writer, doc, i, res, need_shape).map_err(|e| e.at_item(&item.id))?);
        }
    }
    Ok(out)
}

fn member(
    writer: &mut Writer,
    doc: &Document,
    i: usize,
    res: &PageResources,
    need_shape: bool,
) -> Result<Member, Error> {
    let item = &doc.items[i];
    let world = scene::world_transform(doc, i)?;
    let mut mask = res.artwork_masks.get(&item.id).map(|s| s.shape);
    let mut scalar = 1.;
    if let Some(prepared) = res.masks.items.get(&item.id) {
        writer.grid_masks += 1;
        mask = opacity::grid_state(
            writer,
            item.mask.as_ref().expect("prepared mask"),
            prepared,
            world,
            1.,
            false,
        )?
        .map(|s| s.shape);
        if mask.is_none() {
            scalar = prepared.outside;
        }
    }
    let mut clipping = stream(writer);
    let commands_before = writer.commands;
    item_clip(writer, &mut clipping, item, world)?;
    let clip_commands = writer.commands - commands_before;
    let mut clip_emitted = false;
    let mut body = stream(writer);
    item_paint(writer, &mut body, item, world, res)?;
    let mut wrap = |w: &mut Writer, f: usize| -> Result<usize, Error> {
        let f = if clipping.content.is_empty() {
            f
        } else {
            if clip_emitted {
                w.commands += clip_commands;
                if w.commands > MAX_COMMANDS {
                    return Err(limit("PDF knockout clips exceed the generated-path budget"));
                }
            }
            clip_emitted = true;
            let mut clipped = clipping.clone();
            clipped.use_resource("XObject", f, "Do");
            w.isolated_rgb_form(&clipped)?
        };
        knockout::masked_form(w, f, scalar, mask)
    };
    let (paint, shape) = if !item.content.is_container() {
        let form = writer.isolated_rgb_form(&body)?;
        let form = wrap(writer, form)?;
        (Artwork::Isolated(form), need_shape.then_some(form))
    } else {
        let knockout = item.content.is_knockout();
        let children = prepare(writer, doc, Some(&item.id), res, need_shape || knockout)?;
        // Share the frame background with its color and coverage forms.
        if !body.content.is_empty() {
            let background = writer.isolated_rgb_form(&body)?;
            body = placed(writer, background);
        }
        let shape = if need_shape {
            let mut coverage = body.clone();
            for child in &children {
                coverage.use_resource("XObject", child.footprint(), "Do");
            }
            let form = writer.isolated_rgb_form(&coverage)?;
            Some(wrap(writer, form)?)
        } else {
            None
        };
        let paint = if item.content.is_isolated() {
            if knockout {
                let mut group = knockout::Group::new(writer, scene::ancestors(doc, i)?.len());
                for child in &children {
                    // Each direct child sees transparent at entry to an isolated knockout.
                    let form = match child.paint {
                        Artwork::Isolated(f) => f,
                        Artwork::Through { .. } => {
                            let mut single = stream(writer);
                            child.draw_through(writer, &mut single, 1.)?;
                            writer.isolated_rgb_form(&single)?
                        }
                    };
                    group.add(
                        writer,
                        form,
                        (child.footprint() != form).then_some(child.footprint()),
                        child.opacity,
                    )?;
                }
                group.finish(writer, &mut body)?;
            } else {
                draw_all(writer, &mut body, &children)?;
            }
            let form = writer.isolated_rgb_form(&body)?;
            Artwork::Isolated(wrap(writer, form)?)
        } else {
            let boundary = if clipping.content.is_empty() && mask.is_none() && scalar == 1. {
                None
            } else {
                let mut full = stream(writer);
                full.content = format!("1 g {} re f\n", writer.page_bbox);
                let white = writer.isolated_rgb_form(&full)?;
                Some(wrap(writer, white)?)
            };
            Artwork::Through {
                children,
                knockout,
                boundary,
            }
        };
        (paint, shape)
    };
    Ok(Member {
        id: item.id.clone(),
        paint,
        shape,
        opacity: item.opacity * item.fill_opacity,
        blend: item.blend,
    })
}

fn draw_all(writer: &mut Writer, out: &mut Stream, children: &[Member]) -> Result<(), Error> {
    for child in children {
        child.draw(writer, out).map_err(|e| e.at_item(&child.id))?;
    }
    Ok(())
}

impl Member {
    fn footprint(&self) -> usize {
        self.shape.expect("prepared knockout footprint")
    }

    fn draw(&self, writer: &mut Writer, out: &mut Stream) -> Result<(), Error> {
        if self.opacity == 0. {
            return Ok(());
        }
        match self.paint {
            Artwork::Isolated(form) => self.draw_form(writer, out, form, self.opacity),
            Artwork::Through { .. } => self.draw_through(writer, out, self.opacity),
        }
    }

    fn draw_form(
        &self,
        writer: &mut Writer,
        out: &mut Stream,
        form: usize,
        opacity: f64,
    ) -> Result<(), Error> {
        out.content.push_str("q\n");
        graphics_state(writer, out, opacity, self.blend)?;
        out.use_resource("XObject", form, "Do");
        out.content.push_str("Q\n");
        Ok(())
    }

    fn draw_through(
        &self,
        writer: &mut Writer,
        out: &mut Stream,
        opacity: f64,
    ) -> Result<(), Error> {
        let Artwork::Through {
            children,
            knockout,
            boundary,
        } = &self.paint
        else {
            unreachable!()
        };
        if children.is_empty() {
            return Ok(());
        }
        if !knockout && opacity == 1. && boundary.is_none() {
            return draw_all(writer, out, children);
        }
        let entry = writer.isolated_rgb_form(out)?;
        let completed = self.on_entry(writer, entry, opacity)?.form(writer)?;
        *out = placed(writer, completed);
        Ok(())
    }

    fn on_entry(
        &self,
        writer: &mut Writer,
        entry: usize,
        opacity: f64,
    ) -> Result<Composite, Error> {
        if opacity == 0. {
            return Ok(Composite::Form(entry));
        }
        let (children, knockout, boundary) = match &self.paint {
            Artwork::Isolated(form) => {
                let mut alone = placed(writer, entry);
                self.draw_form(writer, &mut alone, *form, opacity)?;
                return Ok(Composite::Form(writer.isolated_rgb_form(&alone)?));
            }
            Artwork::Through {
                children,
                knockout,
                boundary,
            } => (children, knockout, boundary),
        };
        if children.is_empty() {
            return Ok(Composite::Form(entry));
        }
        let candidate = if *knockout {
            writer.knockout_groups += 1;
            writer.backdrop_groups += 1;
            writer.page_requires_backdrop = true;
            composite(writer, entry, children)?
        } else {
            let mut all = placed(writer, entry);
            draw_all(writer, &mut all, children)?;
            Composite::Form(writer.isolated_rgb_form(&all)?)
        };
        if opacity == 1. && boundary.is_none() {
            Ok(candidate)
        } else {
            // Interpolate the completed candidate with its unchanged entry once,
            // including when both are translucent. Source-over alone doubles the entry.
            let field = match boundary {
                Some(id) => *id,
                None => {
                    let mut full = stream(writer);
                    full.content = format!("1 g {} re f\n", writer.page_bbox);
                    writer.isolated_rgb_form(&full)?
                }
            };
            let weight = knockout::masked_form(writer, field, opacity, None)?;
            let state = alpha_mask(writer, weight, false)?;
            let before = opaque(writer, entry)?;
            let after = candidate.fields(writer)?;
            Ok(Composite::Fields(before.interpolate(writer, after, state)?))
        }
    }
}

pub(super) fn render(
    writer: &mut Writer,
    out: &mut Stream,
    doc: &Document,
    res: &PageResources,
) -> Result<(), Error> {
    let children = prepare(writer, doc, None, res, false)?;
    draw_all(writer, out, &children)
}

fn alpha_mask(writer: &mut Writer, form: usize, inverse: bool) -> Result<usize, Error> {
    let transfer = if inverse {
        " /TR << /FunctionType 2 /Domain [0 1] /C0 [1] /C1 [0] /N 1 >>"
    } else {
        ""
    };
    writer.mask_state(
        format!("<< /Type /ExtGState /SMask << /S /Alpha /G {form} 0 R{transfer} >> >>"),
        form,
    )
}

// All arithmetic takes place on opaque premultiplied fields. Private PDF
// operators used to calculate them do not describe authored blend modes.
#[derive(Clone, Copy)]
struct Fields {
    rgb: usize,
    alpha: usize,
}

fn opaque(writer: &mut Writer, form: usize) -> Result<Fields, Error> {
    let mask = alpha_mask(writer, form, false)?;
    let mut rgb = stream(writer);
    rgb.content = format!("0 0 0 rg {} re f\n", writer.page_bbox);
    rgb.use_resource("XObject", form, "Do");
    let mut gray = Stream {
        content: format!("0 g {} re f\n", writer.page_bbox),
        ..Stream::default()
    };
    gray.use_resource("ExtGState", mask, "gs");
    gray.content
        .push_str(&format!("1 g {} re f\n", writer.page_bbox));
    Ok(Fields {
        rgb: writer.isolated_rgb_form(&rgb)?,
        alpha: opacity::gray_form(writer, &gray)?,
    })
}

impl Fields {
    fn interpolate(self, writer: &mut Writer, after: Self, weight: usize) -> Result<Self, Error> {
        // Ordinary masked source-over interpolates two *opaque* associated
        // fields. Do this independently for RGB and alpha, then restore RGBA.
        let mix = |w: &mut Writer, before, after, gray| {
            let mut output = placed(w, before);
            output.use_resource("ExtGState", weight, "gs");
            output.use_resource("XObject", after, "Do");
            if gray {
                opacity::gray_form(w, &output)
            } else {
                w.isolated_rgb_form(&output)
            }
        };
        Ok(Self {
            rgb: mix(writer, self.rgb, after.rgb, false)?,
            alpha: mix(writer, self.alpha, after.alpha, true)?,
        })
    }

    fn arithmetic(
        self,
        writer: &mut Writer,
        right: Fields,
        diff: usize,
        add: bool,
        survival: usize,
    ) -> Result<Fields, Error> {
        let mut combine = |left, right, gray| {
            let mut out = stream(writer);
            let white = if gray { "1 g" } else { "1 1 1 rg" };
            let black = if gray { "0 g" } else { "0 0 0 rg" };
            let page = format!("{} re f\n", writer.page_bbox);
            // For additions a+b<=1, so 1-abs(1-a-b) gives the sum.
            // With a mask the left operand is scaled against the opaque base.
            if add {
                out.content.push_str(&format!("{white} {page}"));
                out.use_resource("ExtGState", diff, "gs");
            } else {
                out.content.push_str(&format!("{black} {page}"));
            }
            out.content.push_str("q\n");
            out.use_resource("ExtGState", survival, "gs");
            out.use_resource("XObject", left, "Do");
            out.content.push_str("Q\n");
            if !add {
                out.use_resource("ExtGState", diff, "gs");
            }
            out.use_resource("XObject", right, "Do");
            if add {
                out.content.push_str(&format!("{white} {page}"));
            }
            if gray {
                opacity::gray_form(writer, &out)
            } else {
                writer.isolated_rgb_form(&out)
            }
        };
        Ok(Fields {
            rgb: combine(self.rgb, right.rgb, false)?,
            alpha: combine(self.alpha, right.alpha, true)?,
        })
    }

    fn restore(self, writer: &mut Writer) -> Result<usize, Error> {
        writer.uses_backdrop_division = true;
        // Use neutral RGB for division, derived directly from the scalar soft
        // mask. Converting a DeviceGray color to an ICC RGB space changes its value.
        let alpha = writer.mask_state(
            format!(
                "<< /Type /ExtGState /SMask << /S /Luminosity /G {} 0 R /BC [0] >> >>",
                self.alpha
            ),
            self.alpha,
        )?;
        let mut inv = stream(writer);
        inv.content = format!("1 1 1 rg {} re f\n", writer.page_bbox);
        inv.use_resource("ExtGState", alpha, "gs");
        inv.content
            .push_str(&format!("0 0 0 rg {} re f\n", writer.page_bbox));
        let inverse = writer.isolated_rgb_form(&inv)?;
        let dodge = writer.add("<< /Type /ExtGState /BM /ColorDodge >>")?;
        let mut straight = placed(writer, self.rgb);
        straight.use_resource("ExtGState", dodge, "gs");
        straight.use_resource("XObject", inverse, "Do");
        let straight = writer.isolated_rgb_form(&straight)?;
        knockout::masked_form(writer, straight, 1., Some(alpha))
    }
}

// Defer unassociation until real PDF paint needs RGBA. A parent knockout
// or an owner fade can consume the associated fields of a child directly.
enum Composite {
    Form(usize),
    Fields(Fields),
}

impl Composite {
    fn fields(self, writer: &mut Writer) -> Result<Fields, Error> {
        match self {
            Self::Form(f) => opaque(writer, f),
            Self::Fields(fields) => Ok(fields),
        }
    }
    fn form(self, writer: &mut Writer) -> Result<usize, Error> {
        match self {
            Self::Form(f) => Ok(f),
            Self::Fields(fields) => fields.restore(writer),
        }
    }
}

struct Range {
    fields: Fields,
    shape: usize,
}

fn composite(writer: &mut Writer, entry: usize, children: &[Member]) -> Result<Composite, Error> {
    let first = children[0].on_entry(writer, entry, children[0].opacity)?;
    if children.len() == 1 {
        return Ok(first);
    }
    let diff = writer.add("<< /Type /ExtGState /BM /Difference >>")?;
    let background = opaque(writer, entry)?;
    let mut ranges = vec![Range {
        fields: first.fields(writer)?,
        shape: children[0].footprint(),
    }];
    for child in &children[1..] {
        let current = child
            .on_entry(writer, entry, child.opacity)?
            .fields(writer)?;
        let survival = alpha_mask(writer, child.footprint(), true)?;
        // C >= (1-F)B in every associated channel, even for darkening modes.
        let fields = background.arithmetic(writer, current, diff, false, survival)?;
        ranges.push(Range {
            fields,
            shape: child.footprint(),
        });
    }
    // Combining contiguous ranges preserves order with logarithmic form depth.
    while ranges.len() > 1 {
        let mut next = Vec::with_capacity(ranges.len().div_ceil(2));
        let mut pairs = ranges.into_iter();
        while let Some(left) = pairs.next() {
            if let Some(right) = pairs.next() {
                let survival = alpha_mask(writer, right.shape, true)?;
                let fields = left
                    .fields
                    .arithmetic(writer, right.fields, diff, true, survival)?;
                let mut shape = placed(writer, left.shape);
                shape.use_resource("XObject", right.shape, "Do");
                next.push(Range {
                    fields,
                    shape: writer.isolated_rgb_form(&shape)?,
                });
            } else {
                next.push(left);
            }
        }
        ranges = next;
    }
    Ok(Composite::Fields(ranges.pop().unwrap().fields))
}
