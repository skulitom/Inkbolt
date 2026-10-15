//! SVG viewport mapping kept separate from native canvas admission.
use super::*;

pub(super) const SYMBOL_ATTRIBUTES: &[&str] = &[
    "x",
    "y",
    "width",
    "height",
    "viewBox",
    "preserveAspectRatio",
    "refX",
    "refY",
];

pub(super) const NESTED_ATTRIBUTES: &[&str] = &[
    "x",
    "y",
    "width",
    "height",
    "viewBox",
    "preserveAspectRatio",
    "version",
];

fn view_box(node: Node<'_, '_>) -> Result<Option<[f64; 4]>, Error> {
    node.attribute("viewBox")
        .map(|value| {
            let values = numbers::list(value)?;
            if values.len() != 4 || values[2] <= 0.0 || values[3] <= 0.0 {
                return Err(invalid(
                    "viewBox requires x y positive-width positive-height",
                ));
            }
            Ok([values[0], values[1], values[2], values[3]])
        })
        .transpose()
}

pub(super) fn mapping(node: Node<'_, '_>, [width, height]: [f64; 2]) -> Result<Matrix, Error> {
    mapping_from(node, [width, height], view_box(node)?)
}
pub(super) fn mapping_from(
    node: Node<'_, '_>,
    [width, height]: [f64; 2],
    view: Option<[f64; 4]>,
) -> Result<Matrix, Error> {
    let tokens: Vec<_> = node
        .attribute("preserveAspectRatio")
        .unwrap_or("xMidYMid meet")
        .split_whitespace()
        .collect();
    if !(1..=2).contains(&tokens.len())
        || ![
            "none", "xMinYMin", "xMidYMin", "xMaxYMin", "xMinYMid", "xMidYMid", "xMaxYMid",
            "xMinYMax", "xMidYMax", "xMaxYMax",
        ]
        .contains(&tokens[0])
    {
        return Err(unsupported("Unsupported preserveAspectRatio syntax"));
    }
    let slice = match tokens.get(1).copied().unwrap_or("meet") {
        "meet" => false,
        "slice" => true,
        _ => return Err(invalid("Expected meet or slice")),
    };
    // The attribute is syntactically checked even when it has no geometric
    // effect. With no viewBox, the viewport retains one-to-one user units.
    let Some(view) = view else {
        return Ok(identity());
    };
    let (mut sx, mut sy) = (width / view[2], height / view[3]);
    let (mut dx, mut dy) = (0.0, 0.0);
    if tokens[0] != "none" {
        let scale = if slice { sx.max(sy) } else { sx.min(sy) };
        (sx, sy) = (scale, scale);
        let factor = |value| match value {
            "Min" => 0.0,
            "Mid" => 0.5,
            _ => 1.0,
        };
        dx = (width - view[2] * scale) * factor(&tokens[0][1..4]);
        dy = (height - view[3] * scale) * factor(&tokens[0][5..8]);
    }
    Ok([sx, 0.0, 0.0, sy, dx - view[0] * sx, dy - view[1] * sy])
}

fn coordinate(value: &str, basis: f64) -> Result<f64, Error> {
    let value = definitions::Coordinate::parse(value)?.value(basis);
    if !value.is_finite() {
        return Err(invalid("Nonfinite SVG viewport coordinate"));
    }
    Ok(value)
}
fn reference(value: &str, axis: usize, basis: f64) -> Result<f64, Error> {
    Ok(match (value.trim(), axis) {
        ("left", 0) | ("top", 1) => 0.0,
        ("center", _) => basis * 0.5,
        ("right", 0) | ("bottom", 1) => basis,
        _ => coordinate(value, basis)?,
    })
}
pub(super) fn validate(node: Node<'_, '_>) -> Result<(), Error> {
    mapping(node, [1.0, 1.0])?;
    for name in ["width", "height"] {
        if let Some(value) = node.attribute(name).filter(|v| v.trim() != "auto")
            && coordinate(value, 1.0)? < 0.0
        {
            return Err(invalid("SVG viewport dimensions cannot be negative"));
        }
    }
    for (axis, (position, anchor)) in [("x", "refX"), ("y", "refY")].into_iter().enumerate() {
        if let Some(value) = node.attribute(position) {
            coordinate(value, 1.0)?;
        }
        if node.has_tag_name("symbol")
            && let Some(value) = node.attribute(anchor)
        {
            reference(value, axis, 1.0)?;
        }
    }
    Ok(())
}

struct Viewport {
    size: [f64; 2],
    user_viewport: [f64; 2],
    placement: Matrix,
    content: Matrix,
}
impl Viewport {
    fn resolve(
        node: Node<'_, '_>,
        host: Option<Node<'_, '_>>,
        parent_viewport: [f64; 2],
    ) -> Result<Self, Error> {
        validate(node)?;
        let mut size = [0.0; 2];
        for (axis, name) in ["width", "height"].into_iter().enumerate() {
            let value = host
                .and_then(|host| host.attribute(name))
                .filter(|v| v.trim() != "auto")
                .or_else(|| node.attribute(name).filter(|v| v.trim() != "auto"));
            size[axis] = value
                .map(|v| coordinate(v, parent_viewport[axis]))
                .transpose()?
                .unwrap_or(parent_viewport[axis]);
            if size[axis] < 0.0 {
                return Err(invalid("SVG viewport dimensions cannot be negative"));
            }
        }
        let user_viewport = view_box(node)?.map(|v| [v[2], v[3]]).unwrap_or(size);
        let empty = size.contains(&0.0);
        let content = if empty {
            identity()
        } else {
            mapping(node, size)?
        };
        let mut position = identity();
        for (axis, (name, anchor)) in [("x", "refX"), ("y", "refY")].into_iter().enumerate() {
            position[4 + axis] = node
                .attribute(name)
                .map(|v| coordinate(v, parent_viewport[axis]))
                .transpose()?
                .unwrap_or(0.0);
            if !empty
                && node.has_tag_name("symbol")
                && let Some(value) = node.attribute(anchor)
            {
                // An omitted anchor leaves the viewport edge in place. Explicit
                // zero anchors the mapped user-space origin, which can differ.
                let value = reference(value, axis, user_viewport[axis])?;
                position[4 + axis] -= content[axis * 3] * value + content[4 + axis];
            }
        }
        let transform = node
            .attribute("transform")
            .map(numbers::transform)
            .transpose()?
            .unwrap_or(identity());
        let placement = geometry::multiply(transform, position);
        geometry::validate_matrix(placement)?;
        if !empty {
            geometry::validate_matrix(content)?;
        }
        Ok(Self {
            size,
            user_viewport,
            placement,
            content,
        })
    }
}

impl Importer<'_> {
    pub(super) fn viewport_group(
        &mut self,
        parent: String,
        transform: Matrix,
        clip: Option<Clip>,
        visible: bool,
    ) -> Result<usize, Error> {
        self.control.check()?;
        let index = self.document.items.len();
        if index >= self.document.resource_profile.items() {
            return Err(Error::new(
                "RESOURCE_LIMIT",
                "SVG viewport exceeds item limit",
            ));
        }
        let parent_index = crate::scene::index(&self.document, &parent)?;
        if crate::scene::ancestors(&self.document, parent_index)?.len() >= crate::scene::MAX_DEPTH {
            return Err(Error::new(
                "RESOURCE_LIMIT",
                "SVG viewport exceeds hierarchy limit",
            ));
        }
        self.document.items.push(Item {
            id: format!("svg-{index}"),
            name: String::new(),
            content: Content::Group {
                isolated: true,
                role: GroupRole::Group,
                knockout: false,
            },
            parent: Some(parent),
            transform,
            visible,
            locked: false,
            opacity: 1.0,
            fill_opacity: 1.0,
            coverage: crate::coverage::Mode::Smooth {},
            blend: BlendMode::Normal,
            hdr_grade: None,
            pixel_warp: None,
            metadata: None,
            effects: vec![],
            clip_to: None,
            clip,
            mask: None,
            artwork_mask: None,
            filters: vec![],
        });
        self.bindings.push(definitions::Binding {
            index,
            style: Style::default(),
            clip: None,
            displayed: visible,
            object_bounds: None,
            text_placement: identity(),
            text_ranges: vec![],
            viewport: self.viewport,
        });
        Ok(index)
    }
    pub(super) fn expand_viewport(
        &mut self,
        node: Node<'_, '_>,
        host: Option<Node<'_, '_>>,
        parent: String,
        inherited: &Style,
    ) -> Result<(), Error> {
        let layout = Viewport::resolve(node, host, self.viewport)?;
        let attributes = if node.has_tag_name("symbol") {
            SYMBOL_ATTRIBUTES
        } else {
            NESTED_ATTRIBUTES
        };
        let props = properties(node, attributes, self.styles)?;
        let empty = layout.size.contains(&0.0);
        let clipped = props.get("overflow") != Some(&"visible");
        let clip = (!empty && clipped).then(|| Clip {
            geometry: Geometry::Rect {
                x: 0.0,
                y: 0.0,
                width: layout.size[0],
                height: layout.size[1],
            },
            transform: identity(),
            fill_rule: FillRule::Nonzero,
            enabled: true,
        });
        let wrapper = self.viewport_group(parent.clone(), layout.placement, clip, !empty)?;
        let wrapper_id = self.document.items[wrapper].id.clone();
        if empty {
            // A zero-size viewport has no rendered contents. Keep its occurrence
            // and dimensions without introducing a singular native transform.
            self.validate_template(node, inherited)?;
            if host.is_some() {
                let host_index = crate::scene::index(&self.document, &parent)?;
                let binding = &mut self.bindings[host_index];
                self.template_refs
                    .record(&binding.style, binding.clip.as_deref())?;
                binding.clip = None;
                binding.style.mask = None;
                binding.displayed = false;
                self.document.items[host_index].visible = false;
            }
            self.document.items[wrapper].name = node.attribute("id").unwrap_or("").to_owned();
            self.mappings.push(
                json!({"item_id":wrapper_id,"source_id":node.attribute("id"),
                "element":node.tag_name().name(),"byte_offset":node.range().start,
                "viewport_size":layout.size,"empty_viewport":true}),
            );
            self.scopes
                .annotate(self.mappings.last_mut().unwrap(), &self.use_path);
            self.losses.push(format!("Zero-size {} viewports become nonpainting empty groups; retain the SVG for their unexpanded contents.", if node.has_tag_name("symbol") { "symbol" } else { "SVG" }));
            return Ok(());
        }
        let previous = self.viewport;
        self.viewport = layout.user_viewport;
        let first = self.document.items.len();
        let result = self.visit(
            node,
            Some(wrapper_id.clone()),
            inherited,
            Some(layout.content),
        );
        self.viewport = previous;
        result?;
        let id = &self.document.items[first].id;
        let row = self
            .mappings
            .iter_mut()
            .find(|row| row["item_id"] == id.as_str())
            .unwrap();
        row["viewport_item_id"] = json!(wrapper_id);
        row["viewport_size"] = json!(layout.size);
        Ok(())
    }
}
