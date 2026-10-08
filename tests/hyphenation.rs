use inkbolt::{
    control::Control,
    hyphenation::{Compiled, Pattern, Rules},
};

fn rules() -> Rules {
    serde_json::from_str("{}").unwrap()
}
fn pattern(n: usize) -> Pattern {
    Pattern {
        text: "a".repeat(n),
        weights: vec![1; n + 1],
        at_start: false,
        at_end: false,
    }
}
#[test]
fn compiled_rules_own_their_values_and_repeat_without_consuming_budget() {
    let control = Control::default();
    let mut source = rules();
    source.patterns.push(pattern(1));
    let compiled = Compiled::new(&source, &control).unwrap();
    source.patterns.clear();
    let words = vec!["a".repeat(256); 16];
    let first = compiled.inspect(&words, &control).unwrap();
    for _ in 0..4 {
        let later = compiled.inspect(&words, &control).unwrap();
        assert_eq!(
            serde_json::to_value(&first).unwrap(),
            serde_json::to_value(later).unwrap()
        );
    }
    assert_eq!(first.words[0].breaks, (2..=254).collect::<Vec<_>>());
    assert!(
        Compiled::new(&source, &control)
            .unwrap()
            .inspect(&words, &control)
            .unwrap()
            .words[0]
            .breaks
            .is_empty()
    );
}

#[test]
fn library_enforces_limits_independently_of_cli_transport() {
    let control = Control::default();
    let mut source = rules();
    source.patterns = vec![pattern(1); 32_769];
    assert_eq!(
        Compiled::new(&source, &control).err().unwrap().code,
        "RESOURCE_LIMIT"
    );
    source.patterns = vec![pattern(64); 4_097];
    assert_eq!(
        Compiled::new(&source, &control).err().unwrap().code,
        "RESOURCE_LIMIT"
    );
    source.patterns = vec![pattern(64); 4_096];
    let compiled = Compiled::new(&source, &control).unwrap();
    assert_eq!(
        compiled.inspect(&["a".repeat(64)], &control).unwrap().words[0].breaks,
        (2..=62).collect::<Vec<_>>()
    );
}

#[test]
fn caller_cancellation_rejects_compilation_and_reused_inspection() {
    let control = Control::default();
    let compiled = Compiled::new(&rules(), &control).unwrap();
    control.cancel();
    assert_eq!(
        Compiled::new(&rules(), &control).err().unwrap().code,
        "CANCELLED"
    );
    assert_eq!(
        compiled
            .inspect(&["abcd".into()], &control)
            .unwrap_err()
            .code,
        "CANCELLED"
    );
}
