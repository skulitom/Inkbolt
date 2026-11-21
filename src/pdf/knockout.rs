use super::*;

/// A knockout child blends against the backdrop at group entry. Within an
/// isolated group that backdrop is transparent. Normal pass-through children
/// admit the same group contribution over an arbitrary external backdrop.
pub(super) fn preflight(document: &Document, group: &Item, working_rgb: bool) -> Result<(), Error> {
    if !working_rgb {
        return Err(
            unsupported("Vector PDF knockout groups require working-RGB display delivery")
                .at_item(&group.id),
        );
    }
    check_children(document, group, true, !group.content.is_isolated())
}

fn check_children(
    document: &Document,
    parent: &Item,
    direct: bool,
    sees_backdrop: bool,
) -> Result<(), Error> {
    for index in scene::children(document, Some(&parent.id)) {
        let child = &document.items[index];
        if !child.visible
            || matches!(
                child.content,
                Content::WorkPath { .. } | Content::MaskSource {} | Content::ComponentSource { .. }
            )
        {
            continue;
        }
        // When every descendant retains its intrinsic opacity, a container's
        // completed alpha equals its child-footprint union, including masks.
        if !direct && (child.opacity != 1.0 || child.fill_opacity != 1.0) {
            return Err(unsupported("This PDF knockout member has a faded descendant with an independent footprint; use a PNG proof or retain the snapshot").at_item(&child.id));
        }
        if sees_backdrop && child.blend != BlendMode::Normal {
            return Err(unsupported("Pass-through PDF knockout groups require normal blends wherever a child sees the group entry backdrop").at_item(&child.id));
        }
        if child.content.is_container() {
            check_children(
                document,
                child,
                false,
                sees_backdrop && !child.content.is_isolated(),
            )?;
        }
    }
    Ok(())
}

pub(super) struct Group {
    prior: Stream,
    depth: usize,
}

impl Group {
    pub(super) fn new(writer: &Writer, depth: usize) -> Self {
        Self {
            prior: Stream {
                default_rgb: writer.default_rgb,
                ..Stream::default()
            },
            depth,
        }
    }

    pub(super) fn add(
        &mut self,
        writer: &mut Writer,
        form: usize,
        opacity: f64,
    ) -> Result<(), Error> {
        if opacity < 1.0 && !self.prior.content.is_empty() {
            self.depth += 1;
            if self.depth > crate::limits::pdf::MAX_KNOCKOUT_DEPTH {
                return Err(limit(
                    "PDF knockout composition exceeds the supported form nesting depth",
                ));
            }
            // For incoming footprint f and effective alpha a = p*f, earlier
            // siblings must retain (1-f). Normal source-over already contributes
            // (1-a), so apply (1-f)/(1-a) to the preceding siblings first.
            let program = format!(
                "{{ dup 1 ge {{ pop 0 }} {{ dup 1 exch sub exch {} mul 1 exch sub div }} ifelse }}",
                number(opacity)?
            );
            let transfer = writer.stream(
                "/FunctionType 4 /Domain [0 1] /Range [0 1]",
                program.as_bytes(),
            )?;
            let mask = writer.mask_state(
                format!(
                    "<< /Type /ExtGState /SMask << /S /Alpha /G {form} 0 R /TR {transfer} 0 R >> >>"
                ),
                form,
            )?;
            let prefix = writer.isolated_rgb_form(&self.prior)?;
            self.prior = Stream {
                default_rgb: writer.default_rgb,
                ..Stream::default()
            };
            self.prior.content.push_str("q\n");
            self.prior.use_resource("ExtGState", mask, "gs");
            self.prior.use_resource("XObject", prefix, "Do");
            self.prior.content.push_str("Q\n");
        }
        if opacity > 0.0 {
            self.prior.content.push_str("q\n");
            graphics_state(writer, &mut self.prior, opacity, BlendMode::Normal)?;
            self.prior.use_resource("XObject", form, "Do");
            self.prior.content.push_str("Q\n");
        }
        Ok(())
    }

    pub(super) fn finish(self, writer: &mut Writer, output: &mut Stream) -> Result<(), Error> {
        let form = writer.isolated_rgb_form(&self.prior)?;
        output.use_resource("XObject", form, "Do");
        writer.knockout_groups += 1;
        writer.page_requires_backdrop = true;
        Ok(())
    }
}
