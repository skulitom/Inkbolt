//! Original SVG mask-source collection and independent content/region coordinates.
use super::*;
use crate::artwork_masks::{Mask, Mode};
use definitions::{Binding, Coordinate, bbox_matrix, bbox_unit, local_bounds};

pub(super) fn mode(value: &str, allow_source: bool) -> Result<Option<Mode>, Error> {
    match value {
        "alpha" => Ok(Some(Mode::Alpha)),
        "luminance" => Ok(Some(Mode::Luminance)),
        "match-source" if allow_source => Ok(None),
        _ => Err(unsupported("Unsupported mask interpretation")),
    }
}

#[derive(Clone)]
pub(super) struct Template {
    offset: usize,
    style: Style,
    clip: Option<String>,
    region_box: bool,
    content_box: bool,
    region: [Coordinate; 4],
    explicit_region: bool,
    source: Option<String>,
}
impl Template {
    pub fn parse(node: Node<'_, '_>, inherited: &Style) -> Result<Self, Error> {
        let p = properties(
            node,
            &["maskUnits", "maskContentUnits", "x", "y", "width", "height"],
        )?;
        let style = styled(inherited, &p)?;
        if node.has_attribute("transform") || style.mask.is_some() {
            return Err(unsupported(
                "Transforms or recursive mask effects on mask definitions are not yet supported",
            ));
        }
        if style.space != crate::paint::Interpolation::Srgb {
            return Err(unsupported(
                "Mask source compositing and luminance currently require sRGB",
            ));
        }
        let region_box = bbox_unit(node.attribute("maskUnits").unwrap_or("objectBoundingBox"))?;
        let content_box = bbox_unit(
            node.attribute("maskContentUnits")
                .unwrap_or("userSpaceOnUse"),
        )?;
        let mut region = [Coordinate::User(0.0); 4];
        for (i, (key, default)) in [
            ("x", "-10%"),
            ("y", "-10%"),
            ("width", "120%"),
            ("height", "120%"),
        ]
        .into_iter()
        .enumerate()
        {
            let value = node.attribute(key).unwrap_or(default).trim();
            region[i] = if region_box && !value.ends_with('%') {
                Coordinate::User(number(value).map_err(|_| {
                    unsupported("Object-box mask regions require unitless numbers or percentages")
                })?)
            } else {
                Coordinate::parse(value)?
            };
        }
        Ok(Self {
            offset: node.range().start,
            style,
            clip: p
                .get("clip-path")
                .map(|v| definitions::reference(v))
                .transpose()?
                .flatten()
                .map(str::to_owned),
            region_box,
            content_box,
            region,
            explicit_region: ["x", "y", "width", "height"]
                .iter()
                .any(|k| node.has_attribute(*k)),
            source: None,
        })
    }
}

impl Importer {
    pub(super) fn prepare_masks(&mut self, root: Node<'_, '_>) -> Result<(), Error> {
        let viewport = self.viewport;
        // Definitions discovered inside a source join this bounded queue. They
        // are resources, not nested scene children or an execution dependency.
        while let Some((name, template)) = self
            .definitions
            .masks
            .iter()
            .filter(|(_, t)| t.source.is_none())
            .min_by_key(|(_, t)| t.offset)
            .map(|(id, t)| (id.clone(), t.clone()))
        {
            let node = root
                .descendants()
                .find(|n| n.is_element() && n.range().start == template.offset)
                .ok_or_else(|| invalid("Mask definition source is unavailable"))?;
            if !self.modern_masks && template.region[2..].iter().any(|v| v.value(1.0) < 0.0) {
                return Err(invalid("SVG 1.x mask region dimensions cannot be negative"));
            }
            let index = self.document.items.len();
            if index >= self.document.resource_profile.items() {
                return Err(Error::new(
                    "RESOURCE_LIMIT",
                    "SVG mask source exceeds item limit",
                ));
            }
            let id = format!("svg-{index}");
            self.definitions.masks.get_mut(&name).unwrap().source = Some(id.clone());
            // Content units add a transform; they do not establish a viewport.
            // Percentages in content retain the root user-viewport basis.
            self.viewport = viewport;
            self.in_mask = true;
            let mut title = None;
            for child in node.children() {
                if child.is_text() && !child.text().unwrap_or("").trim().is_empty() {
                    return Err(unsupported(
                        "Mask containers require artwork elements, not raw text",
                    ));
                }
                if child.is_element() && ["title", "desc"].contains(&child.tag_name().name()) {
                    if child.attributes().len() != 0 || child.children().any(|c| c.is_element()) {
                        return Err(unsupported("Mask descriptions require plain text"));
                    }
                    if child.tag_name().name() == "title" {
                        if title.is_some() {
                            return Err(unsupported("At most one title per mask is supported"));
                        }
                        title = Some(
                            child
                                .children()
                                .filter_map(|c| c.text())
                                .collect::<String>(),
                        );
                    } else {
                        self.losses.push(
                            "Description text is not retained in the editable document.".into(),
                        );
                    }
                }
            }
            self.document.items.push(Item {
                hdr_grade: None,
                pixel_warp: None,
                metadata: None,
                id: id.clone(),
                name: title.unwrap_or_else(|| name.clone()),
                content: Content::MaskSource {},
                parent: None,
                transform: identity(),
                // SVG mask opacity/display do not apply. Visibility still
                // inherits to painted children, where it can be overridden.
                visible: true,
                locked: false,
                opacity: 1.0,
                fill_opacity: 1.0,
                coverage: crate::coverage::Mode::Smooth {},
                effects: Vec::new(),
                blend: BlendMode::Normal,
                clip_to: None,
                clip: None,
                mask: None,
                artwork_mask: None,
                filters: vec![],
            });
            self.bindings.push(Binding {
                index,
                style: template.style.clone(),
                clip: template.clip.clone(),
                displayed: true,
                text_bounds: None,
                text_placement: identity(),
                viewport: self.viewport,
            });
            self.mappings.push(json!({"item_id":id,"source_id":name,"element":"mask","byte_offset":template.offset}));
            if let Some(record) = self
                .definitions
                .records
                .iter_mut()
                .find(|r| r["source_id"] == name)
            {
                record["item_id"] = json!(id);
            }
            for child in node
                .children()
                .filter(|c| c.is_element() && !["title", "desc"].contains(&c.tag_name().name()))
            {
                self.visit(child, Some(id.clone()), &template.style, None)?;
            }
            self.viewport = viewport;
            self.in_mask = false;
        }
        Ok(())
    }
}

pub(super) fn apply(
    document: &mut Document,
    bindings: &[Binding],
    masks: &BTreeMap<String, Template>,
    modern: bool,
) -> Result<(), Error> {
    for b in bindings {
        let Some(id) = &b.style.mask else {
            continue;
        };
        let template = masks
            .get(id)
            .ok_or_else(|| invalid(format!("Missing or wrong-type mask reference: {id}")))?;
        let clip_region = !modern || template.explicit_region;
        let bounds = local_bounds(document, b.index, identity(), bindings);
        let user = geometry::inverse(b.text_placement)?;
        let bbox = if template.content_box || (clip_region && template.region_box) {
            bbox_matrix(bounds)?
        } else {
            identity()
        };
        let content = if template.content_box { bbox } else { user };
        let region_to_owner = if template.region_box { bbox } else { user };
        let basis = if template.region_box {
            [1.0, 1.0]
        } else {
            b.viewport
        };
        let mut region = std::array::from_fn(|i| template.region[i].value(basis[i % 2]));
        // CSS Masking disables a nonpositive region; SVG 1.x negatives were
        // rejected even on unused definitions during collection.
        region[2] = region[2].max(0.0);
        region[3] = region[3].max(0.0);
        document.items[b.index].artwork_mask = Some(Box::new(Mask {
            source: template.source.clone().unwrap(),
            region,
            clip_region,
            mode: b.style.mask_mode.unwrap_or(template.style.mask_type),
            transform: content,
            region_transform: geometry::relative_transform(content, &[region_to_owner])?,
            linked: true,
            enabled: true,
        }));
    }
    Ok(())
}
