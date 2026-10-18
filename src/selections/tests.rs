use super::*;
use crate::{scalar_store, stored_scalars::Grid};

fn document(width: u32, height: u32) -> Document {
    serde_json::from_value(
        json!({"schema_version":2,"id":"selection-library","kind":"raster",
        "width":width,"height":height,"color_space":"srgb"}),
    )
    .unwrap()
}
fn selection(width: u32, height: u32, bytes: &[u8]) -> Selection {
    let candidate = scalar_store::Candidate::from_bytes(
        scalar_store::Spec { width, height },
        bytes,
        &Control::default(),
    )
    .unwrap();
    Selection {
        width,
        height,
        gray_hex: String::new(),
        native: Some(Grid::from_candidate(candidate)),
    }
}

#[test]
fn private_feather_matches_integer_outer_product_and_preserves_original_candidate() {
    let (w, h) = (133u32, 131u32);
    let source: Vec<u8> = (0..w * h)
        .map(|i| ((i % w * 71 + i / w * 13) % 256) as u8)
        .collect();
    let mut d = document(w, h);
    d.selection = Some(selection(w, h, &source));
    let original = d.clone();
    refine_with_resources(&mut d, Refine::Feather, 1, None, &Control::default()).unwrap();
    let got = dense(d.selection.as_ref().unwrap(), None, &Control::default()).unwrap();
    for y in 0..h as i64 {
        for x in 0..w as i64 {
            let mut sum = 0u32;
            for dy in -1i64..=1 {
                for dx in -1i64..=1 {
                    let (xx, yy) = (x + dx, y + dy);
                    if xx >= 0 && yy >= 0 && xx < w as i64 && yy < h as i64 {
                        sum += source[(yy * w as i64 + xx) as usize] as u32
                            * (2 - dx.unsigned_abs() as u32)
                            * (2 - dy.unsigned_abs() as u32);
                    }
                }
            }
            assert_eq!(got[(y * w as i64 + x) as usize], ((sum + 8) / 16) as u8);
        }
    }
    assert_eq!(
        dense(
            original.selection.as_ref().unwrap(),
            None,
            &Control::default()
        )
        .unwrap(),
        source
    );
    let grid = d.selection.as_ref().unwrap().native.as_ref().unwrap();
    let candidate = grid.prepare(None, &Control::default()).unwrap();
    assert_eq!(candidate.resident_bytes(), 0);
    assert!(candidate.private_bytes() > 0);
    let copy = d.clone();
    drop(d);
    assert_eq!(
        dense(copy.selection.as_ref().unwrap(), None, &Control::default()).unwrap(),
        got
    );
    let durable = crate::stored_samples::durable_document(&copy);
    assert!(
        durable
            .selection
            .as_ref()
            .unwrap()
            .native
            .as_ref()
            .unwrap()
            .staged
            .is_none()
    );
    assert!(crate::stored_samples::has_staged(&copy));
    assert!(!crate::stored_samples::has_staged(&durable));
}

#[test]
fn cancelled_private_authoring_preserves_the_complete_source() {
    let mut d = document(513, 513);
    fill(&mut d, true).unwrap();
    let before = crate::metadata::canonical(crate::stored_samples::durable_document(&d).as_ref());
    let control = Control::default();
    control.cancel();
    assert_eq!(
        invert_with_resources(&mut d, None, &control)
            .unwrap_err()
            .code,
        "CANCELLED"
    );
    assert_eq!(
        before,
        crate::metadata::canonical(crate::stored_samples::durable_document(&d).as_ref())
    );
    assert_eq!(
        inspect_with_resources(d.selection.as_ref(), None, &Control::default()).unwrap()["fully_selected_pixels"],
        513 * 513
    );
    let old = d
        .selection
        .as_ref()
        .unwrap()
        .native
        .as_ref()
        .unwrap()
        .prepare(None, &Control::default())
        .unwrap();
    fill(&mut d, true).unwrap();
    let new = d
        .selection
        .as_ref()
        .unwrap()
        .native
        .as_ref()
        .unwrap()
        .prepare(None, &Control::default())
        .unwrap();
    assert_eq!(new.manifest(), old.manifest());
    assert_eq!(
        new.private_extents().collect::<Vec<_>>(),
        old.private_extents().collect::<Vec<_>>()
    );
}
