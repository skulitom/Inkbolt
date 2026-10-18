use super::*;
use crate::sample_store::tests::{Directory, check_every_sample, files, fixture, spec};

fn build(s: Spec, bytes: &[u8], budget: &Budget, directory: &Path, control: &Control) -> Candidate {
    from_rows(s, None, budget, directory, control, |y, row| {
        let start = y as usize * row.len();
        row.copy_from_slice(&bytes[start..start + row.len()]);
        Ok(())
    })
    .unwrap()
}

#[test]
fn private_layouts_edges_and_transfer_match_exact_memory_candidates() {
    let directory = Directory::new();
    let control = Control::default();
    for depth in [Depth::U8, Depth::U16, Depth::F32] {
        for channels in [Channels::Rgba, Channels::GrayAlpha] {
            for encoding in [
                Encoding::EncodedSrgb,
                Encoding::ProfiledRgb,
                Encoding::LinearSrgb,
            ] {
                if encoding == Encoding::LinearSrgb && depth != Depth::F32 {
                    continue;
                }
                let s = Spec {
                    depth,
                    channels,
                    encoding,
                    ..spec(133, 131)
                };
                let expected = fixture(s);
                let memory = Candidate::from_bytes(s, &expected, &control).unwrap();
                let candidate = build(s, &expected, &Budget::default(), &directory.0, &control);
                assert_eq!(candidate, memory);
                assert_eq!(candidate.resident_bytes(), 0);
                assert_eq!(candidate.private_bytes(), candidate.pending_bytes() as u64);
                assert_eq!(memory.private_bytes(), 0);
                check_every_sample(&candidate, None, &expected);
                let transfer = candidate.transfer(usize::MAX, &control).unwrap();
                assert_eq!(transfer, memory.transfer(usize::MAX, &control).unwrap());
                let reopened = transfer.prepare(usize::MAX, &control).unwrap();
                check_every_sample(&reopened, None, &expected);
                drop(candidate);
                assert!(files(&directory.0).is_empty());
            }
        }
    }
}

#[test]
fn full_mapping_reuses_published_and_private_blocks_and_local_replacement_is_independent() {
    let directory = Directory::new();
    let control = Control::default();
    let s = spec(259, 131);
    let expected = fixture(s);
    let original = build(s, &expected, &Budget::default(), &directory.0, &control);
    let map = |source: &Candidate, root: Option<&Path>, change: bool| {
        let mut rows = Rows::new(source.clone(), root);
        source
            .map_private_rows(&control, |y, row| {
                rows.read(y, row, &control)?;
                if change && y == 130 {
                    row[0] ^= 1;
                }
                Ok(())
            })
            .unwrap()
    };
    let same = map(&original, None, false);
    assert_eq!(same, original);
    assert_eq!(
        same.private_extents().next(),
        original.private_extents().next()
    );
    original.publish(&directory.store(), &control).unwrap();
    let published = Candidate::from_manifest(original.manifest().clone()).unwrap();
    let unchanged = map(&published, Some(&directory.store()), false);
    assert_eq!(unchanged.pending_tiles(), 0);
    assert_eq!(unchanged.private_bytes(), 0);
    let before = files(&directory.store());
    let changed = map(&published, Some(&directory.store()), true);
    assert_eq!(changed.pending_tiles(), 1);
    assert_eq!(files(&directory.store()), before);
    let mut changed_bytes = expected.clone();
    changed_bytes[130 * s.width as usize * s.stride()] ^= 1;
    check_every_sample(&changed, Some(&directory.store()), &changed_bytes);
    let mixed = changed
        .replace(
            Some(&directory.store()),
            Region {
                x: 0,
                y: 0,
                width: 1,
                height: 1,
            },
            &[1, 0, 2, 0, 3, 0, 255, 255],
            &control,
        )
        .unwrap();
    assert!(mixed.resident_bytes() > 0);
    assert_eq!(mixed.private_bytes(), changed.private_bytes());
    check_every_sample(&original, None, &expected);
    check_every_sample(&changed, Some(&directory.store()), &changed_bytes);
    changed_bytes[..8].copy_from_slice(&[1, 0, 2, 0, 3, 0, 255, 255]);
    mixed.publish(&directory.store(), &control).unwrap();
    let reopened = Candidate::from_manifest(mixed.manifest().clone()).unwrap();
    check_every_sample(&reopened, Some(&directory.store()), &changed_bytes);
}

#[test]
fn reservations_survive_clones_and_failed_construction_releases_only_owned_files() {
    let directory = Directory::new();
    let sentinel = directory.0.join("unrelated.tmp");
    fs::write(&sentinel, b"keep").unwrap();
    let control = Control::default();
    let s = spec(3, 2);
    let expected = fixture(s);
    let budget = Budget(crate::sample_import::source::Budget::new(
        (expected.len() + HEADER_BYTES) as u64,
    ));
    let candidate = build(s, &expected, &budget, &directory.0, &control);
    let clone = candidate.clone();
    drop(candidate);
    let attempt = || {
        from_rows(s, None, &budget, &directory.0, &control, |_, row| {
            row.fill(0);
            Ok(())
        })
    };
    assert_eq!(attempt().unwrap_err().code, "RESOURCE_LIMIT");
    check_every_sample(&clone, None, &expected);
    drop(clone);
    drop(attempt().unwrap());
    assert_eq!(
        files(&directory.0),
        BTreeMap::from([("unrelated.tmp".into(), b"keep".to_vec())])
    );

    let tall = spec(3, 130);
    let budget = Budget(crate::sample_import::source::Budget::new(
        (tall.byte_len().unwrap() + 2 * HEADER_BYTES) as u64,
    ));
    for cancel in [false, true] {
        let control = Control::default();
        let error = from_rows(tall, None, &budget, &directory.0, &control, |y, row| {
            row.fill(0);
            if y == 129 {
                if cancel {
                    control.cancel();
                } else {
                    return Err(Error::new("ROW_FAILED", "synthetic late failure"));
                }
            }
            Ok(())
        })
        .unwrap_err();
        assert_eq!(error.code, if cancel { "CANCELLED" } else { "ROW_FAILED" });
        assert_eq!(fs::read(&sentinel).unwrap(), b"keep");
        assert_eq!(files(&directory.0).len(), 1);
        drop(build(
            tall,
            &fixture(tall),
            &budget,
            &directory.0,
            &Control::default(),
        ));
    }
}

#[test]
fn private_corruption_refuses_read_transfer_and_publication_but_transport_bound_is_checked_first() {
    let directory = Directory::new();
    let control = Control::default();
    let s = spec(3, 2);
    let candidate = build(s, &fixture(s), &Budget::default(), &directory.0, &control);
    let PendingData::File { extent, offset, .. } = candidate.pending.values().next().unwrap()
    else {
        panic!("expected private file")
    };
    extent
        .file
        .lock()
        .unwrap()
        .write_at(offset + HEADER_BYTES as u64, &[255], &control)
        .unwrap();
    assert_eq!(
        candidate.verify(None, &control).unwrap_err().code,
        "SAMPLE_TILE_CORRUPT"
    );
    assert_eq!(
        candidate
            .read_region(None, s.tile(0), &control)
            .unwrap_err()
            .code,
        "SAMPLE_TILE_CORRUPT"
    );
    assert_eq!(
        candidate.transfer(0, &control).unwrap_err().code,
        "RESOURCE_LIMIT"
    );
    assert_eq!(
        candidate.transfer(usize::MAX, &control).unwrap_err().code,
        "SAMPLE_TILE_CORRUPT"
    );
    assert_eq!(
        candidate
            .publish(&directory.store(), &control)
            .unwrap_err()
            .code,
        "SAMPLE_TILE_CORRUPT"
    );
    assert!(files(&directory.store()).is_empty());
}

#[test]
fn row_bands_replay_exact_short_edges_and_check_cached_cancellation() {
    let directory = Directory::new();
    let control = Control::default();
    let s = spec(259, 131);
    let expected = fixture(s);
    let candidate = build(s, &expected, &Budget::default(), &directory.0, &control);
    let mut rows = Rows::new(candidate, None);
    let mut row = vec![0; s.width as usize * s.stride()];
    for y in (0..s.height).chain((0..s.height).rev()) {
        rows.read(y, &mut row, &control).unwrap();
        let start = y as usize * row.len();
        assert_eq!(row, expected[start..start + row.len()]);
    }
    control.cancel();
    assert_eq!(
        rows.read(0, &mut row, &control).unwrap_err().code,
        "CANCELLED"
    );
}
