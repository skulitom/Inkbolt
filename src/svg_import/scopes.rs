//! Resource identities in local use shadow trees, without rewriting source XML.
use super::*;
use std::collections::HashMap;
use std::ops::Range;

#[derive(Clone)]
pub(super) struct Scope {
    number: usize,
    range: Range<usize>,
}

pub(super) struct Scopes {
    ids: HashMap<String, usize>,
    pub stack: Vec<Scope>,
    next: usize,
}
impl Scopes {
    pub fn new(root: Node<'_, '_>) -> Self {
        Self {
            ids: root
                .descendants()
                .filter(Node::is_element)
                .filter_map(|node| {
                    node.attribute("id")
                        .map(|id| (id.to_owned(), node.range().start))
                })
                .collect(),
            stack: vec![],
            next: 0,
        }
    }
    pub fn push(&mut self, target: Node<'_, '_>) {
        self.next += 1;
        self.stack.push(Scope {
            number: self.next,
            range: target.range(),
        });
    }
    pub fn number(&self) -> usize {
        self.stack.last().map_or(0, |scope| scope.number)
    }
    pub fn key(&self, id: &str) -> String {
        if let Some(offset) = self.ids.get(id) {
            for scope in self.stack.iter().rev() {
                if scope.range.contains(offset) {
                    // NUL cannot occur in an XML ID. These private keys never
                    // become native IDs or receipt source IDs, so cannot collide
                    // with arbitrary user IDs or require an XML rename.
                    return format!("\0{}:{id}", scope.number);
                }
            }
        }
        id.to_owned()
    }
    pub fn reference(&self, value: &str) -> Result<Option<String>, Error> {
        Ok(definitions::reference(value)?.map(|id| self.key(id)))
    }
    pub fn styled(
        &self,
        inherited: &Style,
        properties: &BTreeMap<&str, &str>,
        template: bool,
    ) -> Result<Style, Error> {
        let mut style = if template {
            styled_template(inherited, properties)?
        } else {
            styled(inherited, properties)?
        };
        // Resolve at the declaration, not at each inheriting child. An inherited
        // URL keeps its originating tree, including across a use boundary.
        for (name, value) in [("fill", &mut style.fill), ("stroke", &mut style.stroke)] {
            if properties.get(name).is_some_and(|v| *v != "inherit")
                && let Some(key) = self.reference(value)?
            {
                *value = format!("url(#{key})");
            }
        }
        if properties.get("mask").is_some_and(|v| *v != "inherit") {
            style.mask = style.mask.map(|id| self.key(&id));
        }
        Ok(style)
    }
    pub fn annotate(&self, row: &mut Value, use_path: &[Value]) {
        if !self.stack.is_empty() {
            row["resource_scope"] = json!(self.number());
        }
        if !use_path.is_empty() {
            row["instance_path"] = json!(use_path);
        }
    }
}

pub(super) fn source_id(key: &str) -> &str {
    if key.starts_with('\0') {
        key.split_once(':').unwrap().1
    } else {
        key
    }
}
