//! Shared verified publication for pure memory candidates and private imports.
use super::*;

pub(crate) trait Pending<S = Spec> {
    fn contains(&self, id: &str) -> bool;
    fn load(
        &mut self,
        id: &str,
        spec: S,
        tile: Region,
        control: &Control,
    ) -> Result<Arc<[u8]>, Error>;
}

impl<S: Layout> Pending<S> for &BTreeMap<String, PendingData> {
    fn contains(&self, id: &str) -> bool {
        self.contains_key(id)
    }
    fn load(
        &mut self,
        id: &str,
        spec: S,
        tile: Region,
        control: &Control,
    ) -> Result<Arc<[u8]>, Error> {
        self.get(id)
            .ok_or_else(corrupt)?
            .load(id, spec, tile, control)
    }
}

pub(crate) fn publish<S: Layout>(
    manifest: &BlockManifest<S>,
    pending: &mut impl Pending<S>,
    root: &Path,
    control: &Control,
) -> Result<BlockPublication<S>, Error> {
    control.check()?;
    assets::absolute(root)?;
    check_root(Some(root), control)?;
    manifest.validate()?;
    let mut verified = BTreeSet::new();
    for (index, id) in manifest.tiles.iter().enumerate() {
        control.check()?;
        let tile = manifest.spec.tile(index);
        if verified.insert((id, tile.width, tile.height)) {
            if pending.contains(id) {
                let bytes = pending.load(id, manifest.spec, tile, control)?;
                validate_blob(&bytes, id, manifest.spec, tile)?;
            } else {
                read_blob(Some(root), id, manifest.spec, tile)?;
            }
        }
    }
    control.check()?;
    let existing = manifest.tiles.iter().collect::<BTreeSet<_>>().len();
    if unpublished(manifest, pending, root, control)?.is_empty() {
        return Ok(BlockPublication {
            manifest: manifest.clone(),
            created_tiles: 0,
            existing_tiles: existing,
        });
    }
    #[cfg(all(test, windows))]
    tests::checkpoint(root, "before_admission");
    fs::create_dir_all(root).map_err(|_| io_error())?;
    let root = root.canonicalize().map_err(|_| io_error())?;
    let admission = admission::Admission::acquire(&root, control)?;
    let missing = unpublished(manifest, pending, &root, control)?;
    admission.check(&root, &missing, admission::budget(), control)?;
    let mut created = 0;
    let mut seen = BTreeSet::new();
    for (index, id) in manifest.tiles.iter().enumerate() {
        if !seen.insert(id) {
            continue;
        }
        control.check()?;
        if pending.contains(id) {
            let tile = manifest.spec.tile(index);
            let blob = pending.load(id, manifest.spec, tile, control)?;
            // Recheck the loaded private bytes before they can become persistent.
            validate_blob(&blob, id, manifest.spec, tile)?;
            if publish_blob(&root, id, &blob, manifest.spec, tile, control)? {
                created += 1;
            }
        }
        #[cfg(test)]
        crate::sessions::fault_point("native_block_published");
    }
    Ok(BlockPublication {
        manifest: manifest.clone(),
        created_tiles: created,
        existing_tiles: seen.len() - created,
    })
}

fn unpublished<S: Layout>(
    manifest: &BlockManifest<S>,
    pending: &impl Pending<S>,
    root: &Path,
    control: &Control,
) -> Result<Vec<usize>, Error> {
    let mut seen = BTreeSet::new();
    let mut missing = Vec::new();
    for (index, id) in manifest.tiles.iter().enumerate() {
        if !seen.insert(id) {
            continue;
        }
        control.check()?;
        if pending.contains(id) {
            let tile = manifest.spec.tile(index);
            match fs::symlink_metadata(root.join(format!("{id}.native-tile"))) {
                Ok(_) => {
                    read_blob(Some(root), id, manifest.spec, tile)?;
                }
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => missing.push(
                    HEADER_BYTES
                        + tile.width as usize * tile.height as usize * manifest.spec.stride(),
                ),
                Err(_) => return Err(io_error()),
            }
        }
    }
    Ok(missing)
}
