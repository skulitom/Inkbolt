//! Pure block-mode documents and their explicit publication boundary.
use super::*;
use crate::{
    model::{Content, Document},
    sample_store::Transfer,
};
use std::borrow::Cow;

/// Shared immutable private blocks. JSON transport is validated on admission;
/// ordinary document clones share buffers instead of copying hexadecimal data.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Staged(pub(super) Candidate);

impl Serialize for Staged {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        self.0
            .transfer(MAX_PENDING_BYTES, &Control::default())
            .map_err(|e| serde::ser::Error::custom(e.message))?
            .serialize(serializer)
    }
}
impl<'de> Deserialize<'de> for Staged {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        let transfer = Transfer::deserialize(deserializer)?;
        transfer
            .prepare(MAX_PENDING_BYTES, &Control::default())
            .map(Self)
            .map_err(|e| serde::de::Error::custom(e.message))
    }
}

pub(crate) fn check_pending_budget(document: &Document) -> Result<(), Error> {
    let total: usize = document
        .items
        .iter()
        .filter_map(|item| match &item.content {
            Content::StoredSamples { grid } => grid.staged.as_ref().map(|s| s.0.pending_bytes()),
            _ => None,
        })
        .chain(crate::masks::grids(document).map(|(_, grid)| grid.pending_bytes()))
        .try_fold(0usize, |total, bytes| total.checked_add(bytes))
        .ok_or_else(|| crate::model::limit("Prepared native block byte count overflowed"))?;
    if total > MAX_PENDING_BYTES {
        return Err(crate::model::limit(
            "Prepared document exceeds its aggregate native block byte budget",
        ));
    }
    Ok(())
}

/// The exact state to commit after publication. Pure callers must retain the
/// original document until its private blocks have been published successfully.
pub fn durable_document(document: &Document) -> Cow<'_, Document> {
    if !has_staged(document) {
        return Cow::Borrowed(document);
    }
    let mut result = document.clone();
    clear_staged(&mut result);
    Cow::Owned(result)
}

pub(crate) fn has_staged(document: &Document) -> bool {
    document.items.iter().any(|item| {
        matches!(&item.content,
        Content::StoredSamples { grid } if grid.staged.is_some())
    }) || crate::masks::grids(document).any(|(_, grid)| grid.staged.is_some())
}

pub(crate) fn clear_staged(document: &mut Document) {
    for item in &mut document.items {
        if let Content::StoredSamples { grid } = &mut item.content {
            grid.staged = None;
        }
        for mask in item
            .mask
            .iter_mut()
            .chain(item.filters.iter_mut().filter_map(|f| f.mask.as_mut()))
        {
            if let Some(grid) = &mut mask.native {
                grid.staged = None;
            }
        }
    }
}

/// Validate all pending layer dependencies before any writes, then publish only
/// complete immutable blocks. Never changes document/history state. Failure may
/// leave complete unreferenced cache blocks under the native store contract.
pub fn publish_document(
    document: &Document,
    root: Option<&Path>,
    control: &Control,
) -> Result<(), Error> {
    control.check()?;
    check_pending_budget(document)?;
    let mut pending = Vec::new();
    let mut scalar_pending = Vec::new();
    for (_, grid) in crate::masks::grids(document) {
        let candidate = grid.prepare(root, control)?;
        if grid.staged.is_some() {
            scalar_pending.push(candidate);
        }
    }
    for item in &document.items {
        if let Content::StoredSamples { grid } = &item.content
            && grid.staged.is_some()
        {
            pending.push(grid.prepare(root, control)?);
        }
    }
    if !pending.is_empty() || !scalar_pending.is_empty() {
        let root = root.ok_or_else(|| {
            Error::new(
                "SAMPLE_ROOT_REQUIRED",
                "Publishing native edits requires an explicit resource root",
            )
        })?;
        for candidate in pending {
            candidate.publish(root, control)?;
        }
        for candidate in scalar_pending {
            candidate.publish(root, control)?;
        }
    }
    Ok(())
}

/// Reject an oversized requested review document before allocating its hex
/// transport. The upper bound includes the repeated manifest and block framing.
pub(crate) fn check_review_document(document: &Document) -> Result<(), Error> {
    let mut bytes = serde_json::to_vec(durable_document(document).as_ref())
        .map_err(|_| invalid("Document cannot be serialized"))?
        .len();
    for item in &document.items {
        if let Content::StoredSamples { grid } = &item.content
            && let Some(staged) = &grid.staged
        {
            bytes += staged.0.pending_bytes() * 2
                + serde_json::to_vec(&grid.base)
                    .expect("manifest serialization")
                    .len()
                + staged.0.pending_tiles() * 128
                + 256;
        }
    }
    bytes += crate::masks::grids(document)
        .map(|(_, grid)| grid.transport_bytes())
        .sum::<usize>();
    if bytes as u64 > crate::MAX_REQUEST_BYTES {
        return Err(crate::model::limit(
            "Prepared native document exceeds the round-trip transport budget; commit before snapshot export or omit include_document during review",
        ));
    }
    Ok(())
}

pub(crate) fn migrate(
    document: &mut Document,
    id: &str,
    root: Option<&Path>,
    control: &Control,
) -> Result<serde_json::Value, Error> {
    let index = crate::scene::index(document, id)?;
    crate::scene::check_unlocked(document, index, false)?;
    let Content::StoredSamples { grid } = &mut document.items[index].content else {
        return Err(Error::new(
            "INVALID_OPERATION",
            "Native storage migration requires a stored sample layer",
        ));
    };
    if grid.storage_version != 1 {
        return Err(Error::new(
            "MIGRATION_NOT_NEEDED",
            "Native layer already uses block storage version 2",
        ));
    }
    let candidate = grid.prepare(root, control)?;
    let identity = candidate.manifest().sha256.clone();
    grid.storage_version = 2;
    grid.patches.clear();
    grid.set_candidate(candidate)?;
    grid.validate()?;
    Ok(
        serde_json::json!({"id":id,"from_storage_version":1,"storage_version":2,
        "native_sha256":identity,"conversion":false,"samples_preserved":true,
        "preparation_writes_files":false,"block_publication":"before_document_commit"}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn aggregate_pending_budget_and_review_transport_are_independent_of_snapshot_size() {
        let spec = crate::sample_store::Spec {
            width: 128,
            height: 128,
            depth: crate::samples::Depth::F32,
            channels: crate::samples::Channels::Rgba,
            encoding: Default::default(),
        };
        let candidate =
            Candidate::from_bytes(spec, &vec![0; 128 * 128 * 16], &Control::default()).unwrap();
        let bytes_per_layer = candidate.pending_bytes();
        let mut item: crate::model::Item = serde_json::from_value(serde_json::json!({
            "id":"pixels","content":{"type":"stored_samples","grid":{"base":candidate.manifest()}}
        }))
        .unwrap();
        let Content::StoredSamples { grid } = &mut item.content else {
            unreachable!()
        };
        grid.storage_version = 2;
        grid.set_candidate(candidate).unwrap();
        let mut document: Document = serde_json::from_value(serde_json::json!({
            "schema_version":2,"id":"budget","kind":"raster","width":128,"height":128,"color_space":"srgb"
        })).unwrap();
        let admitted = MAX_PENDING_BYTES / bytes_per_layer;
        for index in 0..admitted {
            let mut copy = item.clone();
            copy.id = format!("pixels-{index}");
            document.items.push(copy);
        }
        crate::model::validate(&document).unwrap();
        assert!(
            serde_json::to_vec(durable_document(&document).as_ref())
                .unwrap()
                .len()
                < crate::model::MAX_DOCUMENT_BYTES
        );
        assert_eq!(
            check_review_document(&document).unwrap_err().code,
            "RESOURCE_LIMIT"
        );
        let mut copy = item.clone();
        copy.id = "overflow".into();
        document.items.push(copy);
        let error = crate::model::validate(&document).unwrap_err();
        assert_eq!(error.code, "RESOURCE_LIMIT");
        assert!(error.message.contains("aggregate native block"));
        // Shared buffers keep this budget fixture small in actual test memory.
        document.items.truncate(31);
        check_review_document(&document).unwrap();
        assert!(serde_json::to_vec(&document).unwrap().len() as u64 <= crate::MAX_REQUEST_BYTES);
        document.items.push(item);
        assert_eq!(
            check_review_document(&document).unwrap_err().code,
            "RESOURCE_LIMIT"
        );
        assert_eq!(
            crate::publish::export(
                &document,
                crate::ExportFormat::Snapshot,
                1,
                &crate::sessions::Resources::default()
            )
            .unwrap_err()
            .code,
            "RESOURCE_LIMIT"
        );
    }
}
