use super::*;

#[derive(Clone)]
enum Action {
    Seek(SeekFrom),
    Write(Vec<u8>),
    Flush,
}
fn execute(output: &mut (impl Write + Seek), actions: &[Action]) -> io::Result<()> {
    for action in actions {
        match action {
            Action::Seek(at) => {
                output.seek(*at)?;
            }
            Action::Write(data) => {
                if data.is_empty() {
                    assert_eq!(output.write(data)?, 0);
                } else {
                    output.write_all(data)?;
                }
            }
            Action::Flush => output.flush()?,
        }
    }
    Ok(())
}
fn agree(actions: &[Action]) {
    let control = Control::default();
    let mut expected = Cursor::new(Vec::new());
    // Cursor grows on empty writes past EOF; Inkbolt's sink contract follows
    // files instead: an empty write never materializes a hole.
    let nonempty: Vec<_> = actions
        .iter()
        .filter(|a| !matches!(a, Action::Write(v) if v.is_empty()))
        .cloned()
        .collect();
    execute(&mut expected, &nonempty).unwrap();
    let mut first = Projection::new(&control);
    execute(&mut first, actions).unwrap();
    let mut second = first.replay().unwrap();
    execute(&mut second, actions).unwrap();
    let mut payload = second.finish().unwrap();
    assert_eq!(payload.len(), expected.get_ref().len());
    assert_eq!(payload.sha256(), assets::sha256(expected.get_ref()));
    assert!(matches!(payload.storage, Storage::Discard));
    assert!(payload.copy_to(&mut Vec::new(), &control, |_| {}).is_err());
}

#[test]
fn holes_overlaps_frontier_crossing_and_chunk_boundaries_match_real_seekable_bytes() {
    let mut actions = vec![
        Action::Write(b"header".to_vec()),
        Action::Seek(SeekFrom::Start(12)),
        Action::Write(b"pixels".to_vec()),
        Action::Seek(SeekFrom::Start(4)),
        Action::Write(b"replaced hole and tail".to_vec()),
        Action::Seek(SeekFrom::Start(2)),
        Action::Write(b"FINAL".to_vec()),
        Action::Seek(SeekFrom::End(65536)),
        Action::Write(vec![13; 65538]),
        Action::Seek(SeekFrom::Start(65530)),
        Action::Write(vec![31; 24]),
        Action::Seek(SeekFrom::End(-3)),
        Action::Write(b"END".to_vec()),
        Action::Flush,
    ];
    agree(&actions);
    actions.push(Action::Seek(SeekFrom::Start(
        limits::MAX_OUTPUT_BYTES as u64,
    )));
    actions.push(Action::Write(vec![]));
    agree(&actions);
    agree(&[]);
}

#[test]
fn deterministic_random_overwrites_match_cursor_without_retaining_the_extent() {
    for seed in 0..48u64 {
        let mut state = seed + 1;
        let mut next = || {
            state = state.wrapping_mul(6364136223846793005).wrapping_add(1);
            state >> 32
        };
        let mut actions = vec![];
        for _ in 0..90 {
            actions.push(Action::Seek(SeekFrom::Start(next() % 180_000)));
            let len = (next() % 800) as usize;
            actions.push(Action::Write((0..len).map(|_| next() as u8).collect()));
        }
        agree(&actions);
    }
    let control = Control::default();
    let mut first = Projection::new(&control);
    for _ in 0..128 {
        first.write_all(&[9; 65536]).unwrap();
    }
    first.seek(SeekFrom::Start(4)).unwrap();
    first.write_all(&[1, 2, 3, 4]).unwrap();
    assert_eq!(first.len, 8 * 1024 * 1024);
    assert_eq!(first.patches.bytes, 4);
    assert_eq!(first.patches.entries.len(), 1);
}

#[test]
fn changed_bytes_even_when_later_overwritten_or_changed_seek_transcript_are_rejected() {
    let actions = vec![
        Action::Write(b"first".to_vec()),
        Action::Seek(SeekFrom::Start(0)),
        Action::Write(b"FINAL".to_vec()),
        Action::Flush,
    ];
    for variant in 0..5 {
        let control = Control::default();
        let mut first = Projection::new(&control);
        execute(&mut first, &actions).unwrap();
        let mut replay = actions.clone();
        match variant {
            0 => replay[0] = Action::Write(b"other".to_vec()),
            1 => replay[1] = Action::Seek(SeekFrom::Current(-5)),
            2 => replay.push(Action::Seek(SeekFrom::Start(0))),
            3 => replay.push(Action::Write(vec![0])),
            _ => {
                replay.pop();
            }
        }
        let mut second = first.replay().unwrap();
        execute(&mut second, &replay).unwrap();
        assert_eq!(second.finish().err().unwrap().code, "EXPORT_ERROR");
    }
}

#[test]
fn journal_bounds_fail_before_inserting_and_old_overwrites_do_not_accumulate() {
    let mut patches = Patches::default();
    patches
        .insert(0, &vec![1; limits::MAX_PREFLIGHT_PATCH_BYTES])
        .unwrap();
    for _ in 0..10 {
        patches.insert(2, &[3; 100]).unwrap();
    }
    assert_eq!(patches.bytes, limits::MAX_PREFLIGHT_PATCH_BYTES);
    assert_eq!(patches.entries.len(), 1);
    assert!(
        patches
            .insert(limits::MAX_PREFLIGHT_PATCH_BYTES as u64, &[1])
            .is_err()
    );
    assert_eq!(patches.bytes, limits::MAX_PREFLIGHT_PATCH_BYTES);
    let mut patches = Patches::default();
    for i in 0..limits::MAX_PREFLIGHT_PATCHES {
        patches.insert(i as u64 * 2, &[1]).unwrap();
    }
    assert!(
        patches
            .insert(limits::MAX_PREFLIGHT_PATCHES as u64 * 2, &[1])
            .is_err()
    );
    assert_eq!(patches.entries.len(), limits::MAX_PREFLIGHT_PATCHES);
    patches.insert(0, &[2; 8]).unwrap();
    assert!(patches.entries.len() < limits::MAX_PREFLIGHT_PATCHES);
}

#[test]
fn invalid_seeks_extent_overflow_and_journal_exhaustion_poison_the_sink() {
    for from in [
        SeekFrom::Current(-1),
        SeekFrom::End(i64::MAX),
        SeekFrom::Start(u64::MAX),
    ] {
        let control = Control::default();
        let mut first = Projection::new(&control);
        assert!(first.seek(from).is_err());
        assert!(first.write_all(&[0]).is_err());
        assert_eq!(first.replay().err().unwrap().code, "RESOURCE_LIMIT");
    }
    let control = Control::default();
    let mut first = Projection::new(&control);
    first.maximum = 8;
    first.write_all(&[1; 8]).unwrap();
    assert!(first.write_all(&[1]).is_err());
    assert_eq!(first.replay().err().unwrap().code, "RESOURCE_LIMIT");
    let mut first = Projection::new(&control);
    let bytes = vec![1; limits::MAX_PREFLIGHT_PATCH_BYTES + 1];
    first.write_all(&bytes).unwrap();
    first.rewind().unwrap();
    assert!(first.write_all(&bytes).is_err());
    assert_eq!(first.replay().err().unwrap().code, "RESOURCE_LIMIT");
}

#[test]
fn cancellation_before_replay_during_holes_and_before_completion_never_succeeds() {
    for phase in 0..3 {
        let control = Control::default();
        let mut first = Projection::new(&control);
        first.seek(SeekFrom::Start(65536)).unwrap();
        first.write_all(b"end").unwrap();
        if phase == 0 {
            control.cancel();
            assert_eq!(first.replay().err().unwrap().code, "CANCELLED");
        } else {
            let mut second = first.replay().unwrap();
            second.seek(SeekFrom::Start(65536)).unwrap();
            if phase == 1 {
                control.cancel();
            }
            let write = second.write_all(b"end");
            if phase == 1 {
                assert!(write.is_err());
            } else {
                write.unwrap();
                control.cancel();
            }
            assert_eq!(second.finish().err().unwrap().code, "CANCELLED");
        }
    }
}

#[test]
fn locked_tiff_codec_routes_only_retain_the_final_directory_pointer() {
    use serde_json::json;
    let document = serde_json::from_value(json!({"schema_version":2,"id":"seek-layout",
        "kind":"raster","width":17,"height":271,"color_space":"srgb"}))
    .unwrap();
    let control = Control::default();
    let resources = crate::sessions::Resources::default();
    for depth in [None, Some("u8"), Some("u16"), Some("f32")] {
        for compression in ["none", "lzw", "deflate"] {
            for evaluation in ["whole", "tiled"] {
                let mut options = json!({"compression":compression});
                if let Some(depth) = depth {
                    options["depth"] = json!(depth);
                }
                let options = serde_json::from_value(options).unwrap();
                let render = serde_json::from_value(json!({"evaluation":evaluation})).unwrap();
                let mut memory = Cursor::new(Vec::new());
                crate::image_io::tiff_to_writer(
                    &document,
                    1,
                    &resources,
                    Some(&options),
                    Some("original"),
                    (Some(&render), &control),
                    &mut memory,
                )
                .unwrap();
                let mut first = Projection::new(&control);
                crate::image_io::tiff_to_writer(
                    &document,
                    1,
                    &resources,
                    Some(&options),
                    Some("original"),
                    (Some(&render), &control),
                    &mut first,
                )
                .unwrap();
                assert_eq!(first.patches.bytes, 4);
                assert_eq!(first.patches.entries.len(), 1);
                assert!(first.patches.entries.contains_key(&4));
                let mut second = first.replay().unwrap();
                crate::image_io::tiff_to_writer(
                    &document,
                    1,
                    &resources,
                    Some(&options),
                    Some("original"),
                    (Some(&render), &control),
                    &mut second,
                )
                .unwrap();
                let payload = second.finish().unwrap();
                assert_eq!(payload.sha256(), assets::sha256(memory.get_ref()));
                assert_eq!(payload.len(), memory.get_ref().len());
            }
        }
    }
}
