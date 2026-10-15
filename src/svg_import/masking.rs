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
    scopes: Vec<scopes::Scope>,
    use_path: Vec<Value>,
    style: Style,
    clip: Option<String>,
    region_box: bool,
    content_box: bool,
    region: [Coordinate; 4],
    explicit_region: bool,
    sources: BTreeMap<[u64; 2], String>,
}
fn viewport_key(viewport: [f64; 2]) -> [u64; 2] {
    viewport.map(f64::to_bits)
}
impl Template {
    fn pending_viewport(
        &self,
        name: &str,
        root: [f64; 2],
        bindings: &[Binding],
    ) -> Option<[f64; 2]> {
        if !self.sources.contains_key(&viewport_key(root)) {
            return Some(root);
        }
        bindings
            .iter()
            .filter(|binding| binding.style.mask.as_deref() == Some(name))
            .map(|binding| binding.viewport)
            .find(|viewport| !self.sources.contains_key(&viewport_key(*viewport)))
    }
    pub fn parse(
        node: Node<'_, '_>,
        inherited: &Style,
        styles: &styles::Sheet,
        scopes: &scopes::Scopes,
        use_path: &[Value],
    ) -> Result<Self, Error> {
        let p = properties(
            node,
            &["maskUnits", "maskContentUnits", "x", "y", "width", "height"],
            styles,
        )?;
        let style = scopes.styled(inherited, &p, false)?;
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
                match number(value) {
                    Ok(number) => Coordinate::User(number),
                    Err(_) => {
                        // Preserve invalid literal failures; only valid lengths
                        // in unsupported units are eligible for omission.
                        length(value)?;
                        return Err(unsupported(
                            "Object-box mask regions require unitless numbers or percentages",
                        ));
                    }
                }
            } else {
                Coordinate::parse(value)?
            };
        }
        Ok(Self {
            offset: node.range().start,
            scopes: scopes.stack.clone(),
            use_path: use_path.to_vec(),
            style,
            clip: p
                .get("clip-path")
                .map(|v| scopes.reference(v))
                .transpose()?
                .flatten(),
            region_box,
            content_box,
            region,
            explicit_region: ["x", "y", "width", "height"]
                .iter()
                .any(|k| node.has_attribute(*k)),
            sources: BTreeMap::new(),
        })
    }
}

impl Importer<'_> {
    pub(super) fn prepare_masks(&mut self, root: Node<'_, '_>) -> Result<(), Error> {
        let viewport = self.viewport;
        // Definitions discovered inside a source join this bounded queue. They
        // are resources, not nested scene children or an execution dependency.
        while let Some((name, template, source_viewport)) = self
            .definitions
            .masks
            .iter()
            .filter_map(|(id, t)| {
                t.pending_viewport(id, viewport, &self.bindings)
                    .map(|v| (id, t, v))
            })
            .min_by_key(|(_, t, _)| t.offset)
            .map(|(id, t, v)| (id.clone(), t.clone(), v))
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
            self.definitions
                .masks
                .get_mut(&name)
                .unwrap()
                .sources
                .insert(viewport_key(source_viewport), id.clone());
            // Content units add a transform; they do not establish a viewport.
            // Percentages retain the referencing user viewport. Different
            // viewport contexts receive separate editable source variants.
            self.viewport = source_viewport;
            self.in_mask = true;
            self.scopes.stack = template.scopes.clone();
            self.use_path = template.use_path.clone();
            let source_id = scopes::source_id(&name);
            let mut title = None;
            for child in node.children() {
                if child.is_text() && !child.text().unwrap_or("").trim().is_empty() {
                    return Err(reuse::Location::new(node, &self.use_path).locate(
                        unsupported("Mask containers require artwork elements, not raw text"),
                        node.document(),
                    ));
                }
                if child.is_element() && ["title", "desc"].contains(&child.tag_name().name()) {
                    if child.attributes().len() != 0 || child.children().any(|c| c.is_element()) {
                        return Err(reuse::Location::new(child, &self.use_path).locate(
                            unsupported("Mask descriptions require plain text"),
                            node.document(),
                        ));
                    }
                    if child.tag_name().name() == "title" {
                        if title.is_some() {
                            return Err(reuse::Location::new(child, &self.use_path).locate(
                                unsupported("At most one title per mask is supported"),
                                node.document(),
                            ));
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
                name: title.unwrap_or_else(|| source_id.to_owned()),
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
                location: Some(reuse::Location::new(node, &self.use_path)),
                index,
                style: template.style.clone(),
                clip: template.clip.clone(),
                displayed: true,
                object_bounds: None,
                text_placement: identity(),
                text_ranges: vec![],
                viewport: self.viewport,
            });
            let mapping_start = self.mappings.len();
            let mut mapping = json!({"item_id":id,"source_id":source_id,"element":"mask","byte_offset":template.offset});
            self.scopes.annotate(&mut mapping, &self.use_path);
            self.mappings.push(mapping.clone());
            if let Some(record) = self.definitions.records.iter_mut().find(|r| {
                r["source_id"] == source_id
                    && r["resource_scope"] == mapping["resource_scope"]
                    && r["item_id"].is_null()
            }) {
                record["item_id"] = json!(id);
            } else {
                mapping["viewport"] = json!(source_viewport);
                self.definitions.records.push(mapping);
            }
            for child in node
                .children()
                .filter(|c| c.is_element() && !["title", "desc"].contains(&c.tag_name().name()))
            {
                self.visit(child, Some(id.clone()), &template.style, None)?;
            }
            if source_viewport != viewport {
                self.losses.push("Masks used from different user viewports become independent editable sources, one per viewport. Shared edits do not cross these viewport-specific copies.".into());
                for row in &mut self.mappings[mapping_start..] {
                    row["resource_item_id"] = json!(id);
                    row["resource_viewport"] = json!(source_viewport);
                }
            }
            self.viewport = viewport;
            self.in_mask = false;
            self.scopes.stack.clear();
            self.use_path.clear();
        }
        Ok(())
    }
}

pub(super) fn apply(
    document: &mut Document,
    bindings: &[Binding],
    masks: &BTreeMap<String, Template>,
    modern: bool,
    xml: &roxmltree::Document<'_>,
) -> Result<(), Error> {
    for b in bindings {
        let Some(id) = &b.style.mask else {
            continue;
        };
        let result = (|| {
            let template = masks.get(id).ok_or_else(|| {
                invalid(format!(
                    "Missing or wrong-type mask reference: {}",
                    scopes::source_id(id)
                ))
            })?;
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
                source: template
                    .sources
                    .get(&viewport_key(b.viewport))
                    .cloned()
                    .ok_or_else(|| invalid("Mask viewport context was not prepared"))?,
                region,
                clip_region,
                mode: b.style.mask_mode.unwrap_or(template.style.mask_type),
                transform: content,
                region_transform: geometry::relative_transform(content, &[region_to_owner])?,
                linked: true,
                enabled: true,
            }));
            Ok(())
        })();
        result.map_err(|error| b.locate(error, xml))?;
    }
    Ok(())
}
