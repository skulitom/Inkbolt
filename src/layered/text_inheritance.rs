//! Source-defined style references and overrides; no built-in native defaults.
use super::{text_data::Node, *};
use crate::limits::layered_text as bounds;
use std::collections::{BTreeMap, BTreeSet};

type Fields<'a> = BTreeMap<&'a str, &'a Node>;
pub(super) struct Run<'a> {
    pub length: usize,
    pub fields: Option<Fields<'a>>,
}
pub(super) struct Resolved<'a> {
    pub characters: Vec<Run<'a>>,
    pub paragraphs: Vec<Run<'a>>,
    pub report: Value,
}
struct Sheet<'a> {
    root: Option<&'a Node>,
    fields: Option<Fields<'a>>,
}
fn fields(node: &Node) -> Result<Fields<'_>, Error> {
    let Node::Dictionary(values) = node else {
        return Err(malformed());
    };
    Ok(values.iter().map(|(k, v)| (k.as_str(), v)).collect())
}
struct Family<'a> {
    table: Option<&'a Node>,
    declared_root: Option<&'a Node>,
    property: &'static str,
    parent: &'static str,
    used: BTreeSet<usize>,
    roots: BTreeSet<usize>,
    control: &'a Control,
}
impl<'a> Family<'a> {
    fn sheet(&mut self, node: &'a Node, path: &mut Vec<usize>) -> Result<Sheet<'a>, Error> {
        self.control.check()?;
        if matches!(node, Node::Scalar(_)) {
            let index = node.unsigned()?;
            if path.contains(&index) {
                return Err(malformed());
            }
            if path.len() >= bounds::MAX_REFERENCE_DEPTH {
                return Err(unsupported(
                    "Deeper named text style inheritance is not mapped",
                ));
            }
            let table = self.table.ok_or_else(malformed)?.field("0")?.array()?;
            let entry = table.get(index).ok_or_else(malformed)?;
            super::text_import_geometry::node_keys(entry, &["0"])?;
            let sheet = entry.field("0")?;
            path.push(index);
            self.used.insert(index);
            let out = self.sheet(sheet, path)?;
            path.pop();
            return Ok(out);
        }
        super::text_import_geometry::node_keys(node, &["0", self.parent, self.property])?;
        if let Some(name) = node.optional("0")? {
            name.text()?;
        }
        let own = node.optional(self.property)?;
        let properties = own.map(fields).transpose()?;
        if let Some(parent) = node.optional(self.parent)? {
            // A parent is always an explicit table reference, never an inline
            // fallback or a name guessed from a cache.
            parent.unsigned()?;
            let mut inherited = self.sheet(parent, path)?;
            if let Some(properties) = properties {
                inherited
                    .fields
                    .get_or_insert_with(BTreeMap::new)
                    .extend(properties);
            }
            return Ok(inherited);
        }
        if let Some(&index) = path.last() {
            let declared = self.declared_root.ok_or_else(|| {
                unsupported("Named text styles need their source-declared root properties")
            })?;
            fields(declared)?;
            if own != Some(declared) {
                return Err(unsupported(
                    "Named text style root differs from its source declaration",
                ));
            }
            self.roots.insert(index);
            Ok(Sheet {
                root: Some(declared),
                fields: None,
            })
        } else {
            Ok(Sheet {
                root: None,
                fields: properties,
            })
        }
    }
}
impl<'a> Sheet<'a> {
    fn effective(&self) -> Result<Option<Fields<'a>>, Error> {
        let mut out = self.root.map(fields).transpose()?;
        if let Some(properties) = &self.fields {
            out.get_or_insert_with(BTreeMap::new)
                .extend(properties.iter().map(|(k, v)| (*k, *v)));
        }
        Ok(out)
    }
}

pub(super) fn resolve<'a>(
    global: &'a Node,
    characters: &'a [Node],
    paragraphs: &'a [Node],
    control: &'a Control,
) -> Result<Resolved<'a>, Error> {
    let resources = global.field("0")?;
    let authoring = global.field("1")?;
    let mut character = Family {
        table: resources.optional("5")?,
        declared_root: authoring.optional("2")?,
        property: "6",
        parent: "5",
        used: BTreeSet::new(),
        roots: BTreeSet::new(),
        control,
    };
    let mut paragraph = Family {
        table: resources.optional("6")?,
        declared_root: authoring.optional("3")?,
        property: "5",
        parent: "6",
        used: BTreeSet::new(),
        roots: BTreeSet::new(),
        control,
    };
    let mut para_sheets = Vec::new();
    for run in paragraphs {
        super::text_import_geometry::node_keys(run, &["0", "1"])?;
        let wrapper = run.field("0")?;
        super::text_import_geometry::node_keys(wrapper, &["0"])?;
        para_sheets.push(if let Some(sheet) = wrapper.optional("0")? {
            paragraph.sheet(sheet, &mut Vec::new())?
        } else {
            Sheet {
                root: None,
                fields: None,
            }
        });
    }
    let para_fields = para_sheets
        .iter()
        .map(Sheet::effective)
        .collect::<Result<Vec<_>, _>>()?;
    let mut char_sheets = Vec::new();
    for run in characters {
        super::text_import_geometry::node_keys(run, &["0", "1"])?;
        super::text_import_geometry::node_keys(run.field("0")?, &["0"])?;
        char_sheets.push(character.sheet(run.field("0")?.field("0")?, &mut Vec::new())?);
    }
    let mut output = Vec::new();
    let mut property_count: usize = para_fields.iter().flatten().map(BTreeMap::len).sum();
    let (mut c, mut p, mut at) = (0, 0, 0);
    let (mut c_end, mut p_end) = (0, 0);
    while c < characters.len() && p < paragraphs.len() {
        control.check()?;
        if c_end == at {
            c_end += characters[c].field("1")?.unsigned()?;
        }
        if p_end == at {
            p_end += paragraphs[p].field("1")?.unsigned()?;
        }
        let sheet = &char_sheets[c];
        let mut merged = sheet.root.map(fields).transpose()?.unwrap_or_default();
        if let Some(value) = para_fields[p].as_ref().and_then(|f| f.get("32")) {
            merged.extend(fields(value)?);
        }
        if let Some(properties) = &sheet.fields {
            merged.extend(properties.iter().map(|(k, v)| (*k, *v)));
        }
        property_count += merged.len();
        if property_count > bounds::MAX_PROPERTY_REFERENCES {
            return Err(limit(&format!(
                "Resolved text exceeds {} property references",
                bounds::MAX_PROPERTY_REFERENCES
            )));
        }
        let end = c_end.min(p_end);
        if end <= at {
            return Err(malformed());
        }
        output.push(Run {
            length: end - at,
            fields: Some(merged),
        });
        if output.len() > bounds::MAX_RUNS {
            return Err(limit(&format!(
                "Resolved text exceeds {} character spans",
                bounds::MAX_RUNS
            )));
        }
        at = end;
        c += usize::from(c_end == end);
        p += usize::from(p_end == end);
    }
    if c != characters.len() || p != paragraphs.len() {
        return Err(malformed());
    }
    let had_paragraph_characters = para_fields
        .iter()
        .any(|v| v.as_ref().is_some_and(|v| v.contains_key("32")));
    let report = json!({"source_defined_inheritance":!character.used.is_empty()||!paragraph.used.is_empty(),
        "character_style_indices":character.used,"paragraph_style_indices":paragraph.used,
        "character_root_indices":character.roots,"paragraph_root_indices":paragraph.roots,
        "paragraph_character_attributes":had_paragraph_characters,"resolved_character_runs":output.len(),
        "selected_style_references_validated":true,"source_defaults_invented":false,
        "precedence":"source_root_then_paragraph_character_attributes_then_character_style_then_local_overrides",
        "named_style_links_retained":false});
    let paragraphs = paragraphs
        .iter()
        .zip(para_fields)
        .map(|(run, mut properties)| {
            if let Some(properties) = &mut properties {
                properties.remove("32");
            }
            Ok(Run {
                length: run.field("1")?.unsigned()?,
                fields: properties,
            })
        })
        .collect::<Result<_, Error>>()?;
    Ok(Resolved {
        characters: output,
        paragraphs,
        report,
    })
}
