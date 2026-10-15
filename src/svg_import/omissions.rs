//! Explicit source-subtree omission, using fresh strict imports and original locations.
use super::*;
use crate::limits::svg_import::{MAX_OMISSION_ATTEMPTS, MAX_OMISSION_SOURCE_BYTES};
use std::ops::Range;

/// Validate the complete original XML before any subtree can be discarded.
pub(super) fn parse<'a>(
    text: &'a str,
    max_nodes: u32,
    control: &crate::control::Control,
) -> Result<roxmltree::Document<'a>, Error> {
    control.check()?;
    if text.contains("<!DOCTYPE") {
        return Err(unsupported("DTD declarations are not supported"));
    }
    check_depth(text, control)?;
    let xml = roxmltree::Document::parse_with_options(
        text,
        roxmltree::ParsingOptions {
            allow_dtd: false,
            nodes_limit: max_nodes,
            entity_resolver: None,
        },
    )
    .map_err(|e| invalid(format!("XML parse failed: {e}")))?;
    let mut ids = HashSet::new();
    for node in xml.descendants() {
        control.check()?;
        if node.is_pi() {
            return Err(unsupported(
                "Processing instructions and external stylesheets are not supported",
            ));
        }
        if !node.is_element() {
            continue;
        }
        if node.ancestors().take(crate::scene::MAX_DEPTH + 4).count() > crate::scene::MAX_DEPTH + 2
        {
            return Err(Error::new(
                "RESOURCE_LIMIT",
                "SVG nesting exceeds the document limit",
            ));
        }
        if let Some(id) = node.attribute("id")
            && (id.is_empty() || !ids.insert(id))
        {
            return Err(invalid("Empty or duplicate SVG source ID"));
        }
    }
    Ok(xml)
}

// Bound nesting before entering the XML parser. This only counts lexical tag
// boundaries; the parser remains authoritative for names, attributes and XML
// validity. Quoted attributes, comments, CDATA and processing instructions do
// not introduce element depth. DTDs were refused before this scan.
fn check_depth(text: &str, control: &crate::control::Control) -> Result<(), Error> {
    let bytes = text.as_bytes();
    let mut cursor = 0;
    let mut depth = 0usize;
    while let Some(relative) = text[cursor..].find('<') {
        control.check()?;
        let start = cursor + relative;
        let tail = &text[start..];
        let special = if tail.starts_with("<!--") {
            Some((4, "-->"))
        } else if tail.starts_with("<![CDATA[") {
            Some((9, "]]>"))
        } else if tail.starts_with("<?") {
            Some((2, "?>"))
        } else {
            None
        };
        if let Some((prefix, end)) = special {
            let length = tail[prefix..]
                .find(end)
                .ok_or_else(|| invalid("Unclosed XML markup"))?;
            cursor = start + prefix + length + end.len();
            continue;
        }
        let mut quote = None;
        let mut end = start + 1;
        while end < bytes.len() {
            let byte = bytes[end];
            if let Some(current) = quote {
                if byte == current {
                    quote = None;
                }
            } else if matches!(byte, b'\'' | b'"') {
                quote = Some(byte);
            } else if byte == b'>' {
                break;
            }
            end += 1;
        }
        if end == bytes.len() {
            return Err(invalid("Unclosed XML tag"));
        }
        if tail.starts_with("</") {
            depth = depth.saturating_sub(1);
        } else if !tail.starts_with("<!") {
            if depth + 1 > crate::scene::MAX_DEPTH + 1 {
                return Err(Error::new(
                    "RESOURCE_LIMIT",
                    "SVG nesting exceeds the document limit",
                ));
            }
            if bytes[end - 1] != b'/' {
                depth += 1;
            }
        }
        cursor = end + 1;
    }
    Ok(())
}

pub(super) fn dependency(id: &str) -> Error {
    let mut error = unsupported(format!("Reference depends on omitted SVG source ID {id}"));
    error.details = Some(Box::new(json!({"omitted_reference":id})));
    error
}

pub(super) fn check_references(
    node: Node<'_, '_>,
    props: &BTreeMap<&str, &str>,
    extra: &[&str],
    omitted_ids: &HashSet<String>,
) -> Result<(), Error> {
    if omitted_ids.is_empty() {
        return Ok(());
    }
    for name in ["fill", "stroke", "clip-path", "mask"] {
        if let Some(value) = props.get(name)
            && let Some(id) = definitions::reference(value)?
            && omitted_ids.contains(id)
        {
            return Err(reuse::located(dependency(id), node));
        }
    }
    if extra.contains(&"href") {
        let href = node.attribute("href");
        let legacy = node.attribute(("http://www.w3.org/1999/xlink", "href"));
        if href.is_some() && legacy.is_some() && href != legacy {
            return Err(reuse::located(
                invalid("Conflicting href and xlink:href"),
                node,
            ));
        }
        if let Some(id) = href.or(legacy).and_then(|value| value.strip_prefix('#'))
            && omitted_ids.contains(id)
        {
            return Err(reuse::located(dependency(id), node));
        }
    }
    Ok(())
}

struct Filtered<'a> {
    original: &'a str,
    removed: Vec<Range<usize>>,
}
impl Filtered<'_> {
    fn text(&self) -> String {
        let mut result = String::with_capacity(self.original.len());
        let mut start = 0;
        for range in &self.removed {
            result.push_str(&self.original[start..range.start]);
            start = range.end;
        }
        result.push_str(&self.original[start..]);
        result
    }
    fn original_offset(&self, mut offset: usize) -> usize {
        for range in &self.removed {
            if range.start > offset {
                break;
            }
            offset += range.len();
        }
        offset
    }
    fn remove(&mut self, range: Range<usize>) {
        self.removed
            .retain(|old| !(range.start <= old.start && old.end <= range.end));
        self.removed.push(range);
        self.removed.sort_by_key(|range| range.start);
    }
    // Only receipt/error objects enter this function, never editable metadata.
    fn remap(&self, value: &mut Value, xml: &roxmltree::Document<'_>) {
        match value {
            Value::Array(values) => {
                for value in values {
                    self.remap(value, xml);
                }
            }
            Value::Object(fields) => {
                for (name, value) in fields.iter_mut() {
                    if ["byte_offset", "use_byte_offset"].contains(&name.as_str()) {
                        if let Some(offset) = value.as_u64() {
                            *value = json!(self.original_offset(offset as usize));
                        }
                    } else {
                        self.remap(value, xml);
                    }
                }
                if (fields.contains_key("line") || fields.contains_key("column"))
                    && let Some(offset) = fields.get("byte_offset").and_then(Value::as_u64)
                {
                    let position = xml.text_pos_at(offset as usize);
                    fields.insert("line".into(), json!(position.row));
                    fields.insert("column".into(), json!(position.col));
                }
            }
            _ => {}
        }
    }
}

pub(super) fn import(
    text: &str,
    max_nodes: u32,
    control: &crate::control::Control,
    mut attempt: impl FnMut(&str, &HashSet<String>) -> Result<Value, Error>,
) -> Result<Value, Error> {
    let xml = parse(text, max_nodes, control)?;
    let nodes: BTreeMap<_, _> = xml
        .descendants()
        .filter(Node::is_element)
        .map(|node| (node.range().start, node))
        .collect();
    let mut filtered = Filtered {
        original: text,
        removed: Vec::new(),
    };
    let mut omitted_ids = HashSet::new();
    let mut reports = Vec::new();
    let mut work = 0usize;
    for _ in 0..MAX_OMISSION_ATTEMPTS {
        control.check()?;
        let source = filtered.text();
        work = work.saturating_add(source.len());
        if work > MAX_OMISSION_SOURCE_BYTES {
            return Err(Error::new(
                "RESOURCE_LIMIT",
                "SVG omission source-processing budget exceeded",
            ));
        }
        match attempt(&source, &omitted_ids) {
            Ok(mut result) => {
                for section in ["mapping", "definitions", "approximations", "reuse"] {
                    filtered.remap(&mut result[section], &xml);
                }
                reports.sort_by_key(|row: &Value| row["byte_offset"].as_u64());
                result["source"]["sha256"] = json!(crate::assets::sha256(text.as_bytes()));
                result["source"]["bytes"] = json!(text.len());
                result["unsupported"] = json!("omit_and_report");
                result["omissions"] = json!(reports);
                if !reports.is_empty() {
                    result["losses"].as_array_mut().unwrap().push(json!(
                        "Unsupported source subtrees and their reported dependents were omitted by explicit request. Removed styles and text may change remaining appearance and layout; retain the original source."
                    ));
                }
                return Ok(result);
            }
            Err(mut error) => {
                if let Some(details) = error.details.as_mut() {
                    filtered.remap(details, &xml);
                }
                let owner = error
                    .details
                    .as_ref()
                    .and_then(|details| {
                        details
                            .get("use_byte_offset")
                            .or_else(|| details.get("byte_offset"))
                            .and_then(Value::as_u64)
                    })
                    .and_then(|offset| nodes.get(&(offset as usize)))
                    .copied();
                let Some(node) = owner.filter(|node| *node != xml.root_element()) else {
                    return Err(error);
                };
                if error.code != "SVG_UNSUPPORTED" {
                    return Err(error);
                }
                let position = xml.text_pos_at(node.range().start);
                let covered: Vec<_> = reports
                    .iter()
                    .filter(|row: &&Value| {
                        let start = row["byte_offset"].as_u64().unwrap() as usize;
                        node.range().contains(&start)
                    })
                    .cloned()
                    .collect();
                reports.retain(|row| {
                    !node
                        .range()
                        .contains(&(row["byte_offset"].as_u64().unwrap() as usize))
                });
                reports.push(json!({"source_id":node.attribute("id"),
                    "element":node.tag_name().name(), "byte_offset":node.range().start,
                    "byte_end":node.range().end, "line":position.row, "column":position.col,
                    "descendant_elements":node.descendants().filter(Node::is_element).count()-1,
                    "code":error.code, "reason":error.message, "cause":error.details,
                    "covered_omissions":covered,
                    "scope":"source_element_and_descendants"}));
                for descendant in node.descendants().filter(Node::is_element) {
                    control.check()?;
                    if let Some(id) = descendant.attribute("id") {
                        omitted_ids.insert(id.to_owned());
                    }
                }
                filtered.remove(node.range());
            }
        }
    }
    Err(Error::new(
        "RESOURCE_LIMIT",
        "SVG omission attempt limit exceeded",
    ))
}
