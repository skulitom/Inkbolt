use super::*;

fn round_trip(transfer: &Transfer) -> Transfer {
    serde_json::from_slice(&serde_json::to_vec(transfer).unwrap()).unwrap()
}

#[test]
fn transport_retains_exact_native_bits_and_independent_block_layouts() {
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
                    ..spec(129, 129)
                };
                let mut expected = fixture(s);
                if depth == Depth::F32 {
                    expected[..4].copy_from_slice(&(-0.0f32).to_le_bytes());
                    let next_pixel = s.channels.count() * 4;
                    expected[next_pixel..next_pixel + 4].copy_from_slice(&1u32.to_le_bytes());
                }
                let candidate = Candidate::from_bytes(s, &expected, &control).unwrap();
                let limit = candidate.pending_bytes();
                let transfer = round_trip(&candidate.transfer(limit, &control).unwrap());
                assert_eq!(transfer.version, 1);
                for region in [
                    Region {
                        x: 0,
                        y: 0,
                        width: 128,
                        height: 128,
                    },
                    Region {
                        x: 128,
                        y: 0,
                        width: 1,
                        height: 128,
                    },
                    Region {
                        x: 0,
                        y: 128,
                        width: 128,
                        height: 1,
                    },
                    Region {
                        x: 128,
                        y: 128,
                        width: 1,
                        height: 1,
                    },
                ] {
                    let bytes = independent_blob(s, &expected, region);
                    let id = assets::sha256(&bytes);
                    let stored = transfer
                        .pending
                        .iter()
                        .find(|block| block.sha256 == id)
                        .unwrap();
                    assert_eq!(crate::render::unhex(&stored.data_hex), bytes);
                }
                let restored = transfer.prepare(limit, &control).unwrap();
                restored.verify(None, &control).unwrap();
                assert_eq!(restored.manifest(), candidate.manifest());
                assert_eq!(restored.pending_bytes(), limit);
                check_every_sample(&restored, None, &expected);
            }
        }
    }
}

#[test]
fn partial_transfer_publishes_only_changed_blocks_and_preserves_old_state() {
    let control = Control::default();
    let s = spec(257, 129);
    let original = fixture(s);
    let dir = Directory::new();
    let store = dir.store();
    let base = Candidate::from_bytes(s, &original, &control).unwrap();
    let published = base.publish(&store, &control).unwrap();
    let base = Candidate::from_manifest(published.manifest).unwrap();
    let original_files = files(&store);
    let region = Region {
        x: 127,
        y: 127,
        width: 2,
        height: 2,
    };
    let patch = vec![0; 4 * 8];
    let changed = base
        .replace(Some(&store), region, &patch, &control)
        .unwrap();
    assert_eq!(changed.pending_tiles(), 4);
    let mut expected = original.clone();
    for y in 127..129 {
        let offset = (y * 257 + 127) * 8;
        expected[offset..offset + 16].fill(0);
    }
    let transfer = round_trip(&changed.transfer(changed.pending_bytes(), &control).unwrap());
    assert_eq!(transfer.pending.len(), 4);
    let restored = transfer.prepare(changed.pending_bytes(), &control).unwrap();
    restored.verify(Some(&store), &control).unwrap();
    check_every_sample(&restored, Some(&store), &expected);
    assert_eq!(files(&store), original_files);
    let committed = restored.publish(&store, &control).unwrap();
    assert_eq!(committed.created_tiles, 4);
    let final_files = files(&store);
    for (name, bytes) in &original_files {
        assert_eq!(&final_files[name], bytes);
    }
    check_every_sample(&base, Some(&store), &original);
    let reopened = Candidate::from_manifest(committed.manifest).unwrap();
    check_every_sample(&reopened, Some(&store), &expected);
    assert_eq!(restored.publish(&store, &control).unwrap().created_tiles, 0);
}

#[test]
fn repeated_pure_edits_keep_only_current_blocks_without_lifetime_payload_growth() {
    let control = Control::default();
    let s = spec(257, 1);
    let region = Region {
        x: 0,
        y: 0,
        width: 257,
        height: 1,
    };
    let initial = fixture(s);
    let mut candidate = Candidate::from_bytes(s, &initial, &control).unwrap();
    let limit = initial.len() + 3 * 20;
    let saved = candidate.transfer(limit, &control).unwrap();
    let mut edits = 0;
    let mut edited_pixels = 0;
    for iteration in 0u16..260 {
        let mut expected = Vec::new();
        for _ in 0..257 {
            for value in [iteration, 123, 456, 65535] {
                expected.extend_from_slice(&value.to_le_bytes());
            }
        }
        candidate = candidate
            .replace(None, region, &expected, &control)
            .unwrap();
        edits += 1;
        edited_pixels += region.width as u64 * region.height as u64;
        let transfer = round_trip(&candidate.transfer(limit, &control).unwrap());
        assert_eq!(transfer.pending.len(), 2); // Two equal full blocks and one edge.
        assert_eq!(candidate.pending_bytes(), 129 * 8 + 2 * 20);
        candidate = transfer.prepare(limit, &control).unwrap();
        check_every_sample(&candidate, None, &expected);
    }
    check_every_sample(&saved.prepare(limit, &control).unwrap(), None, &initial);
    // This exercises candidate transport only; legacy document patch caps remain.
    assert!(edited_pixels > crate::stored_samples::MAX_PATCH_PIXELS);
    assert!(edits > crate::stored_samples::MAX_PATCHES);
}

#[test]
fn zero_budget_external_transfers_do_not_read_or_repair_missing_dependencies() {
    let control = Control::default();
    let s = spec(129, 1);
    let dir = Directory::new();
    let store = dir.store();
    let source = Candidate::from_bytes(s, &fixture(s), &control).unwrap();
    let external = Candidate::from_manifest(source.manifest().clone()).unwrap();
    let transfer = external.transfer(0, &control).unwrap();
    assert!(transfer.pending.is_empty());
    let prepared = round_trip(&transfer).prepare(0, &control).unwrap();
    assert!(!store.exists());
    assert_eq!(
        prepared.verify(Some(&store), &control).err().unwrap().code,
        "SAMPLE_TILE_MISSING"
    );
    assert!(!store.exists());

    source.publish(&store, &control).unwrap();
    let region = Region {
        x: 0,
        y: 0,
        width: 1,
        height: 1,
    };
    let bytes = external
        .read_region(Some(&store), region, &control)
        .unwrap();
    let unchanged = external
        .replace(Some(&store), region, &bytes, &control)
        .unwrap();
    assert_eq!(unchanged.transfer(0, &control).unwrap(), transfer);
    let original_files = files(&store);
    let changed = external
        .replace(Some(&store), region, &[0; 8], &control)
        .unwrap();
    let mut partial = changed.transfer(changed.pending_bytes(), &control).unwrap();
    // A transfer may omit a pending block, but that turns it into an explicit
    // external dependency. Preparation must not claim that it exists.
    partial.pending.clear();
    let prepared = partial.prepare(0, &control).unwrap();
    assert_eq!(
        prepared.verify(Some(&store), &control).err().unwrap().code,
        "SAMPLE_TILE_MISSING"
    );
    assert_eq!(files(&store), original_files);
}

#[test]
fn byte_budgets_and_cancellation_are_enforced_before_pending_decode() {
    let control = Control::default();
    let s = spec(129, 1);
    let candidate = Candidate::from_bytes(s, &fixture(s), &control).unwrap();
    let size = candidate.pending_bytes();
    assert_eq!(
        candidate.transfer(size - 1, &control).err().unwrap().code,
        "RESOURCE_LIMIT"
    );
    let transfer = candidate.transfer(size, &control).unwrap();
    assert_eq!(
        transfer.prepare(size - 1, &control).err().unwrap().code,
        "RESOURCE_LIMIT"
    );
    let mut corrupt = transfer.clone();
    // Digest corruption in the first block is detected only after admission of
    // every pending length. A too-small aggregate budget wins before decoding.
    let last = corrupt.pending[0].data_hex.len() - 1;
    let replacement = if &corrupt.pending[0].data_hex[last..] == "0" {
        "1"
    } else {
        "0"
    };
    corrupt.pending[0]
        .data_hex
        .replace_range(last.., replacement);
    assert_eq!(
        corrupt.prepare(size - 1, &control).err().unwrap().code,
        "RESOURCE_LIMIT"
    );
    assert_eq!(
        corrupt.prepare(size, &control).err().unwrap().code,
        "SAMPLE_TILE_CORRUPT"
    );
    let cancelled = Control::default();
    cancelled.cancel();
    assert_eq!(
        candidate.transfer(size, &cancelled).err().unwrap().code,
        "CANCELLED"
    );
    assert_eq!(
        transfer.prepare(size, &cancelled).err().unwrap().code,
        "CANCELLED"
    );
    assert_eq!(candidate.transfer(size, &control).unwrap(), transfer);
}

#[test]
fn malformed_transfers_reject_versions_order_references_framing_and_shape_aliases() {
    let control = Control::default();
    let s = spec(129, 1);
    let candidate = Candidate::from_bytes(s, &fixture(s), &control).unwrap();
    let size = candidate.pending_bytes();
    let valid = candidate.transfer(size, &control).unwrap();
    let mutations: &[fn(&mut Transfer)] = &[
        |t| t.version = 2,
        |t| t.manifest.sha256 = "0".repeat(64),
        |t| t.pending.reverse(),
        |t| t.pending.push(t.pending[0].clone()),
        |t| t.pending[1] = t.pending[0].clone(),
        |t| t.pending[0].sha256 = "0".repeat(64),
        |t| t.pending[0].data_hex.push('0'),
        |t| {
            t.pending[0].data_hex.pop();
        },
        |t| t.pending[0].data_hex.replace_range(..1, "g"),
        |t| t.pending[0].data_hex.replace_range(..1, "A"),
        |t| {
            t.manifest.tiles[1] = t.manifest.tiles[0].clone();
            t.manifest.sha256 = t.manifest.identity();
            t.pending.retain(|b| b.sha256 == t.manifest.tiles[0]);
        },
    ];
    for mutate in mutations {
        let mut bad = valid.clone();
        mutate(&mut bad);
        assert!(bad.prepare(size, &control).is_err());
    }
    let mut value = serde_json::to_value(&valid).unwrap();
    value["root"] = serde_json::json!("not-an-admitted-path");
    assert!(serde_json::from_value::<Transfer>(value).is_err());
    let mut value = serde_json::to_value(&valid).unwrap();
    value["pending"][0]["extra"] = true.into();
    assert!(serde_json::from_value::<Transfer>(value).is_err());
    assert_eq!(round_trip(&valid), valid);
}

#[test]
fn correct_hashes_cannot_admit_wrong_headers_or_invalid_native_values() {
    let control = Control::default();
    let s = Spec {
        depth: Depth::F32,
        ..spec(1, 1)
    };
    let candidate = Candidate::from_bytes(s, &fixture(s), &control).unwrap();
    let valid = candidate
        .transfer(candidate.pending_bytes(), &control)
        .unwrap();
    for (offset, bytes, error) in [
        (19, vec![1], "SAMPLE_TILE_CORRUPT"),
        (16, vec![2], "SAMPLE_TILE_CORRUPT"),
        (8, 2u32.to_le_bytes().to_vec(), "SAMPLE_TILE_CORRUPT"),
        (
            20,
            f32::NAN.to_le_bytes().to_vec(),
            "UNSUPPORTED_SAMPLE_RANGE",
        ),
        (
            20,
            2.0f32.to_le_bytes().to_vec(),
            "UNSUPPORTED_SAMPLE_RANGE",
        ),
        (
            32,
            (-1.0f32).to_le_bytes().to_vec(),
            "UNSUPPORTED_SAMPLE_RANGE",
        ),
    ] {
        let mut bad = valid.clone();
        let mut blob = crate::render::unhex(&bad.pending[0].data_hex);
        blob[offset..offset + bytes.len()].copy_from_slice(&bytes);
        let id = assets::sha256(&blob);
        bad.pending[0] = PendingBlock {
            sha256: id.clone(),
            data_hex: crate::render::hex(&blob),
        };
        bad.manifest.tiles[0] = id;
        bad.manifest.sha256 = bad.manifest.identity();
        assert_eq!(
            bad.prepare(candidate.pending_bytes(), &control)
                .err()
                .unwrap()
                .code,
            error
        );
    }
}
