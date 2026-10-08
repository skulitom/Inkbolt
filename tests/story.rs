use inkbolt::{Document, model::Content, validate};
use serde_json::json;

fn document() -> Document {
    serde_json::from_value(json!({
        "schema_version":2,"id":"story-contract","kind":"vector","width":32,"height":32,"color_space":"srgb",
        "fonts":{"original":{"sha256":"a".repeat(64),"license_sha256":"b".repeat(64),"face_index":0,"bytes":100}},
        "stories":{"source":{"paragraphs":[{"text":"AAAA","style":{"font_id":"original","size":10,"fill":[0,0,0,255]}}],"slots":[{"id":"frame","width":24,"height":10}]}},
        "items":[{"id":"placed","content":{"type":"story_frame","story_id":"source","slot_id":"frame"}}]
    })).unwrap()
}
#[test]
fn story_characters_count_once_but_every_retained_source_counts() {
    let mut d = document();
    d.stories.get_mut("source").unwrap().paragraphs[0].text = "A".repeat(4096);
    for i in 0..4 {
        let mut item = d.items[0].clone();
        item.id = format!("copy-{i}");
        d.items.push(item);
    }
    validate(&d).unwrap();
    let mut extra = d.stories["source"].clone();
    extra.paragraphs[0].text = "A".into();
    d.stories.insert("unplaced".into(), extra);
    assert_eq!(validate(&d).unwrap_err().code, "RESOURCE_LIMIT");
}
#[test]
fn direct_library_nonfinite_values_and_missing_slot_references_fail() {
    for value in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
        for field in 0..4 {
            let mut d = document();
            let story = d.stories.get_mut("source").unwrap();
            match field {
                0 => story.slots[0].width = value,
                1 => story.slots[0].gutter = value,
                2 => story.paragraphs[0].before = value,
                _ => story.paragraphs[0].first_indent = value,
            }
            assert_eq!(validate(&d).unwrap_err().code, "INVALID_STORY");
        }
    }
    let mut d = document();
    if let Content::StoryFrame { slot_id, .. } = &mut d.items[0].content {
        *slot_id = "missing".into();
    }
    assert_eq!(validate(&d).unwrap_err().code, "INVALID_STORY");
}
#[test]
fn list_marker_library_validation_checks_nonfinite_gap_and_style() {
    use inkbolt::text::flow::lists::{List, Marker};
    for gap in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
        let mut d = document();
        d.stories.get_mut("source").unwrap().paragraphs[0].list = Some(List {
            id: "steps".into(),
            level: 0,
            marker: Marker::Bullet { text: "A".into() },
            restart: None,
            gap,
            style: None,
        });
        assert_eq!(validate(&d).unwrap_err().code, "INVALID_LIST");
    }
    let mut d = document();
    let p = &mut d.stories.get_mut("source").unwrap().paragraphs[0];
    let mut style = p.style.clone();
    style.size = f64::NAN;
    p.list = Some(List {
        id: "steps".into(),
        level: 0,
        marker: Marker::Bullet { text: "A".into() },
        restart: None,
        gap: 0.0,
        style: Some(style),
    });
    assert_eq!(validate(&d).unwrap_err().code, "INVALID_DOCUMENT");
}
#[test]
fn retained_hyphenation_rules_share_a_document_storage_budget() {
    use inkbolt::hyphenation::{Pattern, Rules};
    let rules: Rules = serde_json::from_value(json!({"patterns":[]})).unwrap();
    let mut d = document();
    let mut rule = rules;
    rule.patterns = vec![
        Pattern {
            text: "A".repeat(64),
            weights: vec![1; 65],
            at_start: false,
            at_end: false
        };
        2048
    ];
    d.stories
        .get_mut("source")
        .unwrap()
        .hyphenation_rules
        .insert("words".into(), rule);
    let mut extra = d.stories["source"].clone();
    extra.paragraphs[0].text.clear();
    validate(&d).unwrap();
    d.stories.insert("second".into(), extra.clone());
    assert!(
        validate(&d)
            .unwrap_err()
            .message
            .contains("Snapshot exceeds")
    );
    d.stories.insert("third".into(), extra);
    let error = validate(&d).unwrap_err();
    assert_eq!(error.code, "RESOURCE_LIMIT");
    assert!(
        error
            .message
            .contains("aggregate hyphenation rule characters")
    );
}
