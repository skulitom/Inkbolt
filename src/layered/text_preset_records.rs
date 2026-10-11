//! Selected source slot/name metadata, never preset definitions or defaults.
use super::{text_data::Node, *};
use std::collections::BTreeMap;

pub(super) const MAX_RECORDS: usize = 256;
pub(super) const MAX_NAME_BYTES: usize = 128;
const MAX_REPORTED: usize = 4;
const PREVIEW_CHARACTERS: usize = 16;

#[derive(Default)]
pub(super) struct Records(BTreeMap<(&'static str, usize), String>);

impl Records {
    pub fn read(
        &mut self,
        global: &Node,
        table: &str,
        control: &'static str,
        value: &Node,
    ) -> Result<Value, Error> {
        if matches!(value, Node::Name(name) if name == "nil") {
            return Ok(Value::Null);
        }
        let index = value.unsigned()?;
        let entries = global.field("0")?.field(table)?.field("0")?.array()?;
        if entries.len() > MAX_RECORDS {
            return Err(limit("Paragraph preset table exceeds 256 records"));
        }
        // The reference addresses record slots directly. Auxiliary ordering
        // arrays neither remap this index nor supply missing records.
        let name = entries
            .get(index)
            .ok_or_else(malformed)?
            .field("0")?
            .field("0")?
            .text()?;
        if name.len() > MAX_NAME_BYTES {
            return Err(limit("Paragraph preset name exceeds 128 UTF-8 bytes"));
        }
        self.0.insert((control, index), name.to_owned());
        Ok(json!({"index":index,"name":name}))
    }

    pub fn report(&self) -> Value {
        let selected = self
            .0
            .iter()
            .take(MAX_REPORTED)
            .map(|((control, index), name)| {
                let preview: String = name.chars().take(PREVIEW_CHARACTERS).collect();
                json!({"control":control,"index":index,"name_preview":preview,
                    "name_truncated":preview.len()!=name.len(),"name_utf8_bytes":name.len(),
                    "name_sha256":assets::sha256(name.as_bytes())})
            })
            .collect::<Vec<_>>();
        json!({"selected":selected,"selected_count":self.0.len(),
            "truncated":self.0.len()>MAX_REPORTED,"names_untrusted":true,
            "definition_semantics_validated":false,"other_records_validated":false})
    }
}
