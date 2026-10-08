//! Explicit interpretation of retained source spots as declared destination inks.
use super::*;

pub const MAX_BINDINGS: usize = 1024;

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct InkBinding {
    pub object_path: Vec<String>,
    pub source_spot: String,
    pub target_spot: String,
}

pub(super) type Key = (Vec<String>, String);
struct Entry {
    target: Spot,
    receipt: Value,
}
#[derive(Default)]
pub(crate) struct Resolved {
    entries: BTreeMap<Key, Entry>,
}
fn invalid(message: &str) -> Error {
    Error::new("INVALID_INK_BINDING", message)
}
fn spot(document: &Document, id: &str) -> Result<Spot, Error> {
    let entry = document
        .swatches
        .get(id)
        .ok_or_else(|| invalid("Ink binding references a missing spot declaration"))?;
    let swatches::Definition::Spot { alternate } = &entry.definition else {
        return Err(invalid(
            "Ink bindings require direct source and destination spot declarations",
        ));
    };
    Ok(Spot {
        id: id.into(),
        name: entry.name.clone(),
        alternate: alternate.clone(),
        binding: None,
    })
}
impl Resolved {
    pub(crate) fn new(
        document: &Document,
        bindings: &[InkBinding],
        control: &Control,
    ) -> Result<Self, Error> {
        control.check()?;
        if bindings.len() > MAX_BINDINGS {
            return Err(limit(
                "Native print preparation supports at most 1024 ink bindings",
            ));
        }
        let mut result = Self::default();
        if bindings.is_empty() {
            return Ok(result);
        }
        crate::validate(document)?;
        let mut sources: BTreeMap<Vec<String>, Document> = BTreeMap::new();
        for binding in bindings {
            control.check()?;
            if binding.object_path.is_empty()
                || binding.object_path.len() > crate::objects::MAX_NESTING
                || binding.object_path.iter().any(|id| !valid_id(id))
                || !valid_id(&binding.source_spot)
                || !valid_id(&binding.target_spot)
            {
                return Err(invalid(
                    "Ink bindings require one to four object IDs and valid spot IDs",
                ));
            }
            let key = (binding.object_path.clone(), binding.source_spot.clone());
            if result.entries.contains_key(&key) {
                return Err(invalid(
                    "An object source spot may have only one ink binding",
                ));
            }
            let target = spot(document, &binding.target_spot)?;
            let mut path = Vec::new();
            for id in &binding.object_path {
                control.check()?;
                let mut next = path.clone();
                next.push(id.clone());
                if !sources.contains_key(&next) {
                    let parent = if path.is_empty() {
                        document
                    } else {
                        &sources[&path]
                    };
                    let item = parent
                        .items
                        .iter()
                        .find(|i| &i.id == id)
                        .ok_or_else(|| invalid("Ink binding object path does not exist"))?;
                    let Content::Object { object } = &item.content else {
                        return Err(invalid(
                            "Every ink binding path element must be a retained object",
                        ));
                    };
                    sources.insert(next.clone(), object.document()?);
                }
                path = next;
            }
            let source = spot(&sources[&path], &binding.source_spot)?;
            let receipt = json!({"object_path":binding.object_path,"source_spot":binding.source_spot,"source_name":source.name,"source_alternate":source.alternate,"target_spot":binding.target_spot,"target_name":target.name,"target_alternate":target.alternate,"interpretation":"source_tints_address_declared_destination_ink_before_composition","source_changed":false});
            result.entries.insert(key, Entry { target, receipt });
        }
        Ok(result)
    }
    pub(crate) fn reject_projected(&self, path: &[String]) -> Result<(), Error> {
        if self.entries.keys().any(|(p, _)| p.starts_with(path)) {
            return Err(invalid(
                "Ink bindings cannot cross an explicit RGB view projection",
            ));
        }
        Ok(())
    }
    pub(super) fn get(&self, path: &[String], id: &str) -> Option<Spot> {
        self.entries.get(&(path.to_vec(), id.into())).map(|entry| {
            let mut spot = entry.target.clone();
            spot.binding = Some(spot.id.clone());
            spot.id = bound_id(&spot.id, path.is_empty());
            spot
        })
    }
    pub(super) fn receipts(&self, used: &BTreeSet<Key>) -> Vec<Value> {
        self.entries
            .iter()
            .map(|(key, entry)| {
                let mut receipt = entry.receipt.clone();
                receipt["applied"] = json!(used.contains(key));
                receipt
            })
            .collect()
    }
}

fn bound_id(target: &str, root: bool) -> String {
    // '@' cannot occur in an authored ID or an unbound placement path. It is
    // an internal key only; root plates and receipts use the declared target.
    if root {
        target.into()
    } else {
        format!("@{target}")
    }
}
pub(super) fn placed_id(item: &str, spot: &Spot, root: bool) -> String {
    spot.binding.as_ref().map_or_else(
        || objects::identity(item, &spot.id),
        |target| bound_id(target, root),
    )
}
pub(super) fn mapping(item: &str, spot: &Spot) -> Value {
    if let Some(target) = &spot.binding {
        json!({"source_id":null,"target_spot":target,"id":target,"name":spot.name})
    } else {
        json!({"source_id":spot.id,"id":objects::identity(item,&spot.id),"name":spot.name})
    }
}
pub(crate) fn receipt() -> Value {
    json!({"option":"ink_bindings","fields":["object_path","source_spot","target_spot"],"targets":"direct_root_spot_declarations","source":"direct_spot_in_explicit_retained_object_path","order":"resolve_aliases_before_source_composition_and_channel_budgets","fallback":"explicit_destination_name_and_alternate","noise":"destination_identity_for_bound_inks;unbound_identity_unchanged","unapplied":"valid_hidden_unused_or_unselected_sources_report_applied_false","duplicates":"error","max_bindings":MAX_BINDINGS,"implicit_merging":false,"source_changed":false})
}
