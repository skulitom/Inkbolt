//! Bounded transport of a pure candidate, separate from durable publication.
use super::*;

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct PendingBlock {
    pub sha256: String,
    /// Lowercase hexadecimal canonical file bytes, including the typed header.
    pub data_hex: String,
}

/// Pending blocks are unique and strictly sorted by identity. Other manifest
/// references remain external dependencies; preparation never opens a store.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct BlockTransfer<S> {
    pub version: u32,
    pub manifest: BlockManifest<S>,
    pub pending: Vec<PendingBlock>,
}

impl<S: Layout + JsonSchema> JsonSchema for BlockTransfer<S> {
    fn schema_name() -> std::borrow::Cow<'static, str> {
        S::TRANSFER_SCHEMA.into()
    }
    fn json_schema(generator: &mut schemars::SchemaGenerator) -> schemars::Schema {
        /// Pending blocks are unique and strictly sorted by identity. Other manifest
        /// references remain external dependencies; preparation never opens a store.
        #[derive(JsonSchema)]
        #[serde(deny_unknown_fields)]
        #[allow(dead_code)]
        struct Definition<S: Layout> {
            version: u32,
            manifest: BlockManifest<S>,
            pending: Vec<PendingBlock>,
        }
        Definition::<S>::json_schema(generator)
    }
}

impl<S: Layout> BlockCandidate<S> {
    /// Encode private pending blocks without publishing them. The explicit
    /// budget counts decoded block bytes including headers, not JSON bytes.
    /// Callers must also bound serialization and total live memory (hex is 2x).
    pub fn transfer(
        &self,
        max_pending_bytes: usize,
        control: &Control,
    ) -> Result<BlockTransfer<S>, Error> {
        control.check()?;
        if self.pending_bytes() > max_pending_bytes {
            return Err(budget());
        }
        let mut pending = Vec::with_capacity(self.pending.len());
        let references: BTreeMap<_, _> = self
            .manifest
            .tiles
            .iter()
            .enumerate()
            .map(|(index, id)| (id, self.manifest.spec.tile(index)))
            .collect();
        for (sha256, bytes) in &self.pending {
            control.check()?;
            pending.push(PendingBlock {
                sha256: sha256.clone(),
                data_hex: crate::render::hex(&bytes.load(
                    sha256,
                    self.manifest.spec,
                    references[sha256],
                    control,
                )?),
            });
        }
        control.check()?;
        Ok(BlockTransfer {
            version: 1,
            manifest: self.manifest.clone(),
            pending,
        })
    }
}

impl<S: Layout> BlockTransfer<S> {
    /// Check all framing and the explicit decoded-byte budget before decoding.
    /// This proves pending bytes only. Use Candidate::verify with the explicit
    /// root to certify inherited dependencies before publication or admission.
    pub fn prepare(
        &self,
        max_pending_bytes: usize,
        control: &Control,
    ) -> Result<BlockCandidate<S>, Error> {
        control.check()?;
        if self.version != 1 {
            return Err(invalid("Unsupported native candidate transfer version"));
        }
        self.manifest.validate()?;
        let spec = self.manifest.spec;
        let mut references: BTreeMap<&str, Region> = BTreeMap::new();
        for (index, id) in self.manifest.tiles.iter().enumerate() {
            control.check()?;
            let tile = spec.tile(index);
            if let Some(previous) = references.insert(id, tile)
                && (previous.width != tile.width || previous.height != tile.height)
            {
                return Err(invalid(
                    "A native block identity cannot describe different edge dimensions",
                ));
            }
        }
        if self.pending.len() > references.len() {
            return Err(invalid("Too many pending native blocks for the manifest"));
        }
        let mut previous = None;
        let mut total = 0usize;
        for block in &self.pending {
            control.check()?;
            if previous.is_some_and(|id| id >= block.sha256.as_str()) {
                return Err(invalid(
                    "Pending native blocks must have unique, sorted identities",
                ));
            }
            previous = Some(block.sha256.as_str());
            let tile = references
                .get(block.sha256.as_str())
                .ok_or_else(|| invalid("Pending native block is not referenced by the manifest"))?;
            let length = HEADER_BYTES + tile.width as usize * tile.height as usize * spec.stride();
            if block.data_hex.len() != length * 2
                || !block
                    .data_hex
                    .bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
            {
                return Err(invalid(
                    "Pending native bytes must be exact lowercase hexadecimal typed blocks",
                ));
            }
            total = total.checked_add(length).ok_or_else(budget)?;
            if total > max_pending_bytes {
                return Err(budget());
            }
        }
        let mut pending = BTreeMap::new();
        for block in &self.pending {
            control.check()?;
            let bytes = crate::render::unhex(&block.data_hex);
            validate_blob(
                &bytes,
                &block.sha256,
                spec,
                references[block.sha256.as_str()],
            )?;
            pending.insert(block.sha256.clone(), bytes.into());
        }
        control.check()?;
        Ok(BlockCandidate {
            manifest: self.manifest.clone(),
            pending,
        })
    }
}

fn budget() -> Error {
    crate::model::limit("Native candidate transfer exceeds its explicit pending-block byte budget")
}
