use super::*;

fn document() -> Document {
    let spec = crate::sample_store::Spec {
        width: 3,
        height: 3,
        depth: crate::samples::Depth::U16,
        channels: crate::samples::Channels::Rgba,
        encoding: Default::default(),
    };
    let bytes: Vec<u8> = (0..9u16)
        .flat_map(|i| [1001 + i * 71, 23003 + i * 53, 35007, 65535])
        .flat_map(u16::to_le_bytes)
        .collect();
    let candidate =
        crate::sample_store::Candidate::from_bytes(spec, &bytes, &Control::default()).unwrap();
    serde_json::from_value(json!({"schema_version":2,"id":"shared-patch","kind":"raster",
        "width":3,"height":3,"color_space":"srgb","items":[{"id":"pixels","content":{
            "type":"stored_samples","grid":{"storage_version":2,"base":candidate.manifest(),
                "staged":candidate.transfer(crate::stored_samples::MAX_PENDING_BYTES,&Control::default()).unwrap()}
        }}]})).unwrap()
}
fn options() -> Options {
    serde_json::from_value(
        json!({"source_id":"pixels","source_transform":[1,0,0,1,-1,0],
        "region":{"x":1,"y":1,"width":1,"height":1},"mode":{"type":"clone"},"sampling":"nearest"}),
    )
    .unwrap()
}

#[test]
fn borrowed_readers_cannot_reset_work_memory_or_cancellation() {
    for (previous, retained, cancelled, expected) in [
        (MAX_WORK, 0, false, "RESOURCE_LIMIT"),
        (0, MAX_MEMORY_BYTES, false, "RESOURCE_LIMIT"),
        (0, 0, true, "CANCELLED"),
    ] {
        let mut d = document();
        let original = d.clone();
        let control = Control::default();
        let mut work = Work {
            count: 0,
            preparation: Default::default(),
            control: &control,
        };
        let mut target =
            pixels::Pixels::new(&d.items[0].content, None, "UNSUPPORTED", &mut work).unwrap();
        let mut source = target.clone();
        if cancelled {
            control.cancel();
        }
        let error = apply_with_inputs(
            &mut d,
            0,
            &options(),
            None,
            &control,
            Some(Prepared {
                target: &mut target,
                source: &mut source,
                selection: None,
                local_work_before: previous,
                retained_memory: retained,
            }),
        )
        .err()
        .unwrap();
        assert_eq!(error.code, expected);
        assert_eq!(d, original);
    }
}

#[test]
fn constructed_result_retains_original_and_needs_no_second_preparation() {
    let mut d = document();
    let original = d.clone();
    let control = Control::default();
    let mut work = Work {
        count: 0,
        preparation: Default::default(),
        control: &control,
    };
    let mut target =
        pixels::Pixels::new(&d.items[0].content, None, "UNSUPPORTED", &mut work).unwrap();
    let mut source = target.clone();
    let wanted = source.raw(0, 1, &mut work).unwrap();
    let before = target.raw(1, 1, &mut work).unwrap();
    let prepared = work.preparation.work;
    let (receipt, mut output) = apply_with_inputs(
        &mut d,
        0,
        &options(),
        None,
        &control,
        Some(Prepared {
            target: &mut target,
            source: &mut source,
            selection: None,
            local_work_before: 0,
            retained_memory: 0,
        }),
    )
    .unwrap();
    assert_eq!(receipt["source_preparation_work"], 0);
    assert_eq!(output.raw(1, 1, &mut work).unwrap(), wanted);
    assert_eq!(target.raw(1, 1, &mut work).unwrap(), before);
    assert_eq!(work.preparation.work, prepared);
    assert_ne!(d, original);
    let Content::StoredSamples { grid } = &d.items[0].content else {
        panic!()
    };
    assert_eq!(grid.base.sha256, output.identity);
    let mut old =
        pixels::Pixels::new(&original.items[0].content, None, "UNSUPPORTED", &mut work).unwrap();
    assert_eq!(old.raw(1, 1, &mut work).unwrap(), before);
}
