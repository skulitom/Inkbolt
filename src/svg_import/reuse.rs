//! Local source-node references. Expansion never rewrites XML or source IDs.
use super::*;
use roxmltree::NodeId;
use std::collections::HashMap;

pub(super) const ATTRIBUTES: &[&str] = &["href", "x", "y", "width", "height"];

pub(super) fn located(mut error: Error, node: Node<'_, '_>) -> Error {
    let position = node.document().text_pos_at(node.range().start);
    let details = error.details.get_or_insert_with(|| Box::new(json!({})));
    if details.get("byte_offset").is_none() {
        details["byte_offset"] = json!(node.range().start);
        details["line"] = json!(position.row);
        details["column"] = json!(position.col);
        details["element"] = json!(node.tag_name().name());
    }
    error
}

#[derive(Default)]
pub(super) struct References {
    targets: HashMap<NodeId, NodeId>,
}
impl References {
    pub fn collect(root: Node<'_, '_>, control: &crate::control::Control) -> Result<Self, Error> {
        let uses: Vec<_> = root
            .descendants()
            .filter(|n| n.has_tag_name("use"))
            .collect();
        if uses.is_empty() {
            return Ok(Self::default());
        }
        let nodes: Vec<_> = root.descendants().filter(Node::is_element).collect();
        let mut scoped = HashSet::new();
        for node in nodes.iter().rev() {
            control.check()?;
            if node.has_tag_name("metadata")
                || node.children().any(|child| scoped.contains(&child.id()))
            {
                scoped.insert(node.id());
            }
        }
        let ids: HashMap<_, _> = root
            .descendants()
            .filter(Node::is_element)
            .filter_map(|node| node.attribute("id").map(|id| (id, node)))
            .collect();
        let mut result = Self::default();
        for node in uses {
            control.check()?;
            let target = (|| {
                let href = node.attribute("href");
                let legacy = node.attribute(("http://www.w3.org/1999/xlink", "href"));
                if href.is_some() && legacy.is_some() && href != legacy {
                    return Err(invalid("Conflicting use href and xlink:href"));
                }
                let id = href
                    .or(legacy)
                    .and_then(|v| v.strip_prefix('#'))
                    .filter(|id| {
                        !id.is_empty()
                            && !id
                                .chars()
                                .any(|c| c.is_whitespace() || matches!(c, '%' | '#'))
                    })
                    .ok_or_else(|| {
                        unsupported("SVG use requires one literal local fragment reference")
                    })?;
                let target = ids
                    .get(id)
                    .copied()
                    .ok_or_else(|| invalid("Missing SVG use target"))?;
                let tag = target.tag_name().name();
                if !["g", "text", "use", "symbol", "svg"].contains(&tag) && shape_attributes(tag).is_err()
                {
                    return Err(unsupported(
                        "SVG use currently references shapes, groups, text, SVG viewports, symbols or another use",
                    ));
                }
                if scoped.contains(&target.id()) {
                    return Err(unsupported(
                        "SVG use targets containing metadata are not supported",
                    ));
                }
                Ok(target.id())
            })()
            .map_err(|error| located(error, node))?;
            result.targets.insert(node.id(), target);
        }
        // Child edges and use-reference edges share one memoized graph. This
        // visits each source node once instead of expanding a potentially huge DAG.
        result.depth(root, 0, &mut HashSet::new(), &mut HashMap::new(), control)?;
        Ok(result)
    }
    fn depth(
        &self,
        node: Node<'_, '_>,
        hops: usize,
        active: &mut HashSet<NodeId>,
        memo: &mut HashMap<NodeId, usize>,
        control: &crate::control::Control,
    ) -> Result<usize, Error> {
        control.check()?;
        if hops > MAX_REFERENCE_DEPTH {
            return Err(located(
                Error::new("RESOURCE_LIMIT", "SVG reuse reference depth exceeded"),
                node,
            ));
        }
        if let Some(&depth) = memo.get(&node.id()) {
            if hops + depth > MAX_REFERENCE_DEPTH {
                return Err(located(
                    Error::new("RESOURCE_LIMIT", "SVG reuse reference depth exceeded"),
                    node,
                ));
            }
            return Ok(depth);
        }
        if !active.insert(node.id()) {
            return Err(located(invalid("Circular SVG use reference"), node));
        }
        let mut depth = 0;
        if let Some(target) = self.target(node) {
            depth = 1 + self
                .depth(target, hops + 1, active, memo, control)
                .map_err(|error| located(error, node))?;
        }
        for child in node.children().filter(Node::is_element) {
            depth = depth.max(self.depth(child, hops, active, memo, control)?);
        }
        active.remove(&node.id());
        memo.insert(node.id(), depth);
        Ok(depth)
    }
    pub fn target<'a, 'input>(&self, node: Node<'a, 'input>) -> Option<Node<'a, 'input>> {
        self.targets
            .get(&node.id())
            .and_then(|id| node.document().get_node(*id))
    }
}

pub(super) fn translation(node: Node<'_, '_>, viewport: [f64; 2]) -> Result<Matrix, Error> {
    for name in ["width", "height"] {
        if let Some(value) = node.attribute(name).filter(|v| v.trim() != "auto") {
            let value = definitions::Coordinate::parse(value)?.value(1.0);
            if !value.is_finite() || value < 0.0 {
                return Err(located(
                    invalid("SVG use dimensions cannot be negative"),
                    node,
                ));
            }
        }
    }
    let mut transform = identity();
    for (axis, name) in ["x", "y"].into_iter().enumerate() {
        transform[4 + axis] = node
            .attribute(name)
            .map(definitions::Coordinate::parse)
            .transpose()?
            .unwrap_or(definitions::Coordinate::User(0.0))
            .value(viewport[axis]);
    }
    geometry::validate_matrix(transform)?;
    Ok(transform)
}

impl Importer<'_> {
    pub(super) fn collect_definition(
        &mut self,
        node: Node<'_, '_>,
        inherited: &Style,
    ) -> Result<(), Error> {
        self.control.check()?;
        let tag = node.tag_name().name();
        if ["linearGradient", "radialGradient", "clipPath", "mask"].contains(&tag) {
            let key = self.scopes.key(required(node, "id")?);
            return if self.collected_resources.insert(key) {
                self.definitions
                    .collect(node, inherited, self.styles, &self.scopes, &self.use_path)
            } else {
                Ok(())
            };
        }
        if tag != "defs" {
            return self
                .validate_template(node, inherited)
                .map_err(|e| located(e, node));
        }
        let props = properties(node, &[], self.styles)?;
        if node.has_attribute("transform")
            || props.contains_key("clip-path")
            || props.get("mask").is_some_and(|v| *v != "none")
        {
            return Err(unsupported(
                "Transforms/effects on defs containers are not supported",
            ));
        }
        let style = self.scopes.styled(inherited, &props, true)?;
        for child in template_children(node)? {
            self.collect_definition(child, &style)?;
        }
        Ok(())
    }

    pub(super) fn validate_template(
        &mut self,
        node: Node<'_, '_>,
        inherited: &Style,
    ) -> Result<(), Error> {
        self.control.check()?;
        let tag = node.tag_name().name();
        let extra = match tag {
            "g" => &[][..],
            "use" => ATTRIBUTES,
            "symbol" => viewports::SYMBOL_ATTRIBUTES,
            "svg" => viewports::NESTED_ATTRIBUTES,
            "text" => &["x", "y", "dx", "dy"],
            _ => shape_attributes(tag)?,
        };
        let props = properties(node, extra, self.styles)?;
        let style = self.scopes.styled(inherited, &props, true)?;
        if let Some(transform) = node.attribute("transform") {
            geometry::validate_matrix(numbers::transform(transform)?)?;
        }
        let clip = props
            .get("clip-path")
            .map(|value| self.scopes.reference(value))
            .transpose()?
            .flatten();
        // Keep only distinct references, not one full inherited style (including
        // potentially long font-family strings) for every nonpainting template.
        self.template_refs.record(&style, clip.as_deref())?;
        match tag {
            "g" | "symbol" | "svg" => {
                if tag != "g" {
                    viewports::validate(node)?;
                }
                for child in template_children(node)? {
                    self.collect_definition(child, &style)?;
                }
            }
            "use" => {
                translation(node, self.viewport)?;
                if !template_children(node)?.is_empty() {
                    return Err(unsupported(
                        "SVG use accepts only plain descriptions and style children",
                    ));
                }
            }
            "text" => {
                // Fonts and metrics bind when painted, after use inheritance.
                // A template may receive its only bound family from its host.
                labels::template_source(node)?;
            }
            _ => {
                geometry::validate_geometry(&shape(node, &mut Vec::new())?)?;
                if !template_children(node)?.is_empty() {
                    return Err(unsupported(
                        "Shape templates cannot contain artwork children",
                    ));
                }
            }
        }
        Ok(())
    }

    pub(super) fn expand_use(
        &mut self,
        node: Node<'_, '_>,
        parent: String,
        inherited: &Style,
    ) -> Result<(), Error> {
        let target = self
            .references
            .target(node)
            .ok_or_else(|| invalid("SVG use target was not indexed"))?;
        let host = parent.clone();
        self.use_path.push(json!({"source_id":node.attribute("id"), "byte_offset":node.range().start, "item_id":parent}));
        self.scopes.push(target);
        let viewport = target.has_tag_name("symbol") || target.has_tag_name("svg");
        let result = if viewport {
            self.expand_viewport(target, Some(node), parent, inherited)
        } else {
            self.visit(target, Some(parent), inherited, None)
        };
        self.scopes.stack.pop();
        self.use_path.pop();
        if result.is_ok() {
            self.occurrences.push(sharing::Occurrence {
                host,
                target: target.range().start,
                viewport,
                original: false,
            });
        }
        result.map_err(|error| {
            let mut error = located(error, target);
            error.details.as_mut().unwrap()["use_byte_offset"] = json!(node.range().start);
            error
        })
    }
}

fn template_children<'a, 'input>(node: Node<'a, 'input>) -> Result<Vec<Node<'a, 'input>>, Error> {
    let mut result = Vec::new();
    let mut title = false;
    for child in node.children() {
        if child.is_text() && !child.text().unwrap_or("").trim().is_empty() {
            return Err(unsupported(
                "SVG templates require artwork elements, not raw text",
            ));
        }
        if !child.is_element() || child.has_tag_name("style") {
            continue;
        }
        if ["title", "desc"].contains(&child.tag_name().name()) {
            if child.attributes().len() != 0 || child.children().any(|n| n.is_element()) {
                return Err(unsupported("Template descriptions require plain text"));
            }
            if child.has_tag_name("title") {
                if title {
                    return Err(unsupported("At most one title per element is supported"));
                }
                title = true;
            }
        } else {
            result.push(child);
        }
    }
    Ok(result)
}
