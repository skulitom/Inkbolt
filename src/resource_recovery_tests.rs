//! Real-process checks of the documented immutable-cache publication boundary.
use crate::{Error, assets, control::Control};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    fs,
    os::windows::process::CommandExt,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::atomic::{AtomicU64, Ordering},
    time::{Duration, Instant},
};

static NEXT: AtomicU64 = AtomicU64::new(0);
static HITS: AtomicU64 = AtomicU64::new(0);
pub(crate) fn checkpoint(store: &Path, point: &str) {
    if std::env::var("INKBOLT_RESOURCE_FAULT").ok().as_deref() != Some(point) {
        return;
    }
    let root = PathBuf::from(std::env::var_os("INKBOLT_RESOURCE_TEST_ROOT").unwrap());
    if store != root.join("store") {
        return;
    }
    let occurrence: u64 = std::env::var("INKBOLT_RESOURCE_OCCURRENCE")
        .unwrap()
        .parse()
        .unwrap();
    if HITS.fetch_add(1, Ordering::Relaxed) + 1 != occurrence {
        return;
    }
    let worker = std::env::var("INKBOLT_RESOURCE_WORKER").unwrap();
    fs::write(root.join(format!("ready-{worker}")), b"ready").unwrap();
    while !root.join(format!("release-{worker}")).exists() {
        std::thread::sleep(Duration::from_millis(5));
    }
}

struct Owned {
    root: PathBuf,
    children: Vec<Child>,
    sources: BTreeMap<String, Vec<u8>>,
}
impl Owned {
    fn new(kind: &str) -> Self {
        let root = std::env::temp_dir().canonicalize().unwrap().join(format!(
            "inkbolt-resource-recovery-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&root).unwrap();
        let request = fixture(&root, kind);
        fs::write(
            root.join("request.json"),
            serde_json::to_vec(&request).unwrap(),
        )
        .unwrap();
        let sources = fs::read_dir(&root)
            .unwrap()
            .map(|entry| {
                let path = entry.unwrap().path();
                (
                    path.file_name().unwrap().to_string_lossy().into_owned(),
                    fs::read(path).unwrap(),
                )
            })
            .collect();
        Self {
            root,
            children: Vec::new(),
            sources,
        }
    }
    fn start(&mut self, point: &str, occurrence: u64) -> usize {
        let worker = self.children.len();
        let child = Command::new(std::env::current_exe().unwrap())
            .args([
                "--exact",
                "resource_recovery_tests::resource_worker",
                "--nocapture",
            ])
            .env("INKBOLT_RESOURCE_FAULT", point)
            .env("INKBOLT_RESOURCE_TEST_ROOT", &self.root)
            .env("INKBOLT_RESOURCE_OCCURRENCE", occurrence.to_string())
            .env("INKBOLT_RESOURCE_WORKER", worker.to_string())
            .creation_flags(0x0800_0000)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .unwrap();
        self.children.push(child);
        let started = Instant::now();
        while !self.root.join(format!("ready-{worker}")).exists() {
            assert!(
                self.children[worker].try_wait().unwrap().is_none(),
                "Worker exited before {point}"
            );
            assert!(
                started.elapsed() < Duration::from_secs(20),
                "Worker never reached {point}"
            );
            std::thread::sleep(Duration::from_millis(5));
        }
        worker
    }
    fn release(&self, worker: usize) {
        fs::write(self.root.join(format!("release-{worker}")), b"release").unwrap();
    }
    fn finish(&mut self, worker: usize) -> Value {
        self.release(worker);
        let started = Instant::now();
        loop {
            if let Some(status) = self.children[worker].try_wait().unwrap() {
                assert!(status.success());
                break;
            }
            assert!(started.elapsed() < Duration::from_secs(20));
            std::thread::sleep(Duration::from_millis(5));
        }
        serde_json::from_slice(&fs::read(self.root.join(format!("result-{worker}.json"))).unwrap())
            .unwrap()
    }
    fn kill(&mut self, worker: usize) {
        self.children[worker].kill().unwrap();
        self.children[worker].wait().unwrap();
    }
    fn source_bytes_unchanged(&self) {
        for (name, bytes) in &self.sources {
            assert_eq!(&fs::read(self.root.join(name)).unwrap(), bytes);
        }
    }
    fn files(&self, temporaries: bool) -> BTreeMap<String, Vec<u8>> {
        fs::read_dir(self.root.join("store"))
            .unwrap()
            .filter_map(|entry| {
                let path = entry.unwrap().path();
                let name = path.file_name().unwrap().to_string_lossy().into_owned();
                (name.ends_with(".tmp") == temporaries).then(|| (name, fs::read(path).unwrap()))
            })
            .collect()
    }
    fn invoke(&self) -> Value {
        invoke(&self.root, &Control::default()).unwrap()
    }
}
impl Drop for Owned {
    fn drop(&mut self) {
        for child in &mut self.children {
            let _ = child.kill();
            let _ = child.wait();
        }
        let root = self.root.canonicalize().unwrap();
        assert_eq!(
            root.parent(),
            Some(std::env::temp_dir().canonicalize().unwrap().as_path())
        );
        assert!(
            root.file_name()
                .unwrap()
                .to_string_lossy()
                .starts_with("inkbolt-resource-recovery-")
        );
        fs::remove_dir_all(root).unwrap();
    }
}
fn invoke(root: &Path, control: &Control) -> Result<Value, Error> {
    crate::execute_controlled(
        serde_json::from_slice(&fs::read(root.join("request.json")).unwrap()).unwrap(),
        control,
    )
}
#[test]
fn resource_worker() {
    let Some(root) = std::env::var_os("INKBOLT_RESOURCE_TEST_ROOT") else {
        return;
    };
    let root = PathBuf::from(root);
    let control = Control::new(&crate::control::Options {
        timeout_ms: None,
        cancel_file: Some(root.join("cancel")),
    })
    .unwrap();
    let response = match invoke(&root, &control) {
        Ok(result) => json!({"ok":true,"result":result}),
        Err(error) => json!({"ok":false,"error":error.code}),
    };
    let worker = std::env::var("INKBOLT_RESOURCE_WORKER").unwrap();
    fs::write(
        root.join(format!("result-{worker}.json")),
        serde_json::to_vec(&response).unwrap(),
    )
    .unwrap();
}

fn pixels(index: usize) -> Vec<u8> {
    [
        vec![20, 60, 110, 255],
        vec![180, 40, 70, 128],
        vec![0, 0, 0, 0],
    ][index]
        .repeat(4)
}
fn encoded_png(frames: usize, index: usize) -> Vec<u8> {
    let mut output = Vec::new();
    {
        let mut encoder = png::Encoder::new(&mut output, 2, 2);
        encoder.set_color(png::ColorType::Rgba);
        encoder.set_depth(png::BitDepth::Eight);
        encoder.set_source_srgb(png::SrgbRenderingIntent::RelativeColorimetric);
        if frames > 1 {
            encoder.set_animated(frames as u32, 2).unwrap();
        }
        let mut writer = encoder.write_header().unwrap();
        for frame in 0..frames {
            if frames > 1 {
                writer.set_frame_delay(1, 12).unwrap();
            }
            writer
                .write_image_data(&pixels(if frames > 1 { frame } else { index }))
                .unwrap();
        }
        writer.finish().unwrap();
    }
    output
}
fn fixture(root: &Path, kind: &str) -> Value {
    let store = root.join("store");
    match kind {
        "font" => {
            fs::write(root.join("original.font"), original_font()).unwrap();
            fs::write(
                root.join("original.license"),
                b"Original synthetic recovery fixture; permission to use and retain.",
            )
            .unwrap();
            json!({"command":"font.import","source_path":root.join("original.font"),"license_path":root.join("original.license"),"store_root":store})
        }
        "image" => {
            fs::write(root.join("original.png"), encoded_png(1, 0)).unwrap();
            json!({"command":"asset.import","source_path":root.join("original.png"),"store_root":store})
        }
        "images" => {
            let frames: Vec<_> = (0..3)
                .map(|index| {
                    let path = root.join(format!("original-{index}.png"));
                    fs::write(&path, encoded_png(1, index)).unwrap();
                    json!({"source_path":path,"delay":{"numerator":1,"denominator":12}})
                })
                .collect();
            json!({"command":"sequence.import","id":"sequence","store_root":store,"source":{"type":"images","plays":2,"frames":frames}})
        }
        "apng" => {
            fs::write(root.join("original.png"), encoded_png(3, 0)).unwrap();
            json!({"command":"sequence.import","id":"sequence","store_root":store,"source":{"type":"apng","source_path":root.join("original.png")}})
        }
        _ => panic!("Unknown original fixture"),
    }
}
fn image_blobs() -> BTreeMap<String, Vec<u8>> {
    (0..3)
        .map(|index| {
            let mut bytes = b"INKRGBA1".to_vec();
            bytes.extend(2u32.to_le_bytes());
            bytes.extend(2u32.to_le_bytes());
            bytes.extend(pixels(index));
            (format!("{}.rgba8", assets::sha256(&bytes)), bytes)
        })
        .collect()
}
fn assert_complete_images(owned: &Owned, count: usize) {
    let expected = image_blobs();
    let files = owned.files(false);
    assert_eq!(files.len(), count);
    for (name, bytes) in files {
        assert_eq!(expected[&name], bytes);
    }
}

#[test]
fn image_process_death_never_exposes_partial_content_and_retry_retains_orphans() {
    for point in [
        "image_before_write",
        "image_before_publish",
        "image_after_publish",
    ] {
        let mut owned = Owned::new("image");
        let worker = owned.start(point, 1);
        owned.kill(worker);
        assert_complete_images(&owned, usize::from(point == "image_after_publish"));
        let orphans = owned.files(true);
        assert_eq!(orphans.len(), 1);
        let result = owned.invoke();
        assert_eq!(result["created"], point != "image_after_publish");
        assert_complete_images(&owned, 1);
        assert_eq!(owned.files(true), orphans);
        let replay = owned.invoke();
        assert_eq!(replay["created"], false);
        assert_eq!(replay["asset"], result["asset"]);
        owned.source_bytes_unchanged();
    }
}

#[test]
fn font_pair_process_death_preserves_license_and_completes_only_missing_blobs() {
    for suffix in ["license", "font"] {
        for phase in ["before_write", "before_publish", "after_publish"] {
            let mut owned = Owned::new("font");
            let worker = owned.start(&format!("{suffix}_{phase}"), 1);
            owned.kill(worker);
            let before = owned.files(false);
            let expected = usize::from(suffix == "font") + usize::from(phase == "after_publish");
            assert_eq!(before.len(), expected);
            let orphans = owned.files(true);
            assert_eq!(orphans.len(), 1);
            let result = owned.invoke();
            let all = owned.files(false);
            assert_eq!(all.len(), 2);
            assert_eq!(
                all[&format!("{}.font", result["sha256"].as_str().unwrap())],
                owned.sources["original.font"]
            );
            assert_eq!(
                all[&format!("{}.license", result["license_sha256"].as_str().unwrap())],
                owned.sources["original.license"]
            );
            for (name, bytes) in before {
                assert_eq!(all[&name], bytes);
            }
            assert_eq!(owned.files(true), orphans);
            assert_eq!(owned.invoke(), result);
            owned.source_bytes_unchanged();
        }
    }
}

#[test]
fn sequence_process_death_retains_only_complete_cache_entries_then_reconstructs_the_document() {
    for kind in ["images", "apng"] {
        for occurrence in 1..=3 {
            for point in [
                "image_before_write",
                "image_before_publish",
                "image_after_publish",
            ] {
                let mut owned = Owned::new(kind);
                let worker = owned.start(point, occurrence);
                owned.kill(worker);
                assert!(!owned.root.join(format!("result-{worker}.json")).exists());
                let completed = occurrence as usize - usize::from(point != "image_after_publish");
                assert_complete_images(&owned, completed);
                let before = owned.files(false);
                let orphans = owned.files(true);
                let result = owned.invoke();
                assert_complete_images(&owned, 3);
                let replay = owned.invoke();
                assert_eq!(replay["document"], result["document"]);
                assert_eq!(
                    result["document"]["variants"]["sequence"]["frames"]
                        .as_array()
                        .unwrap()
                        .len(),
                    3
                );
                assert_eq!(result["document"]["variants"]["sequence"]["plays"], 2);
                for (name, bytes) in before {
                    assert_eq!(owned.files(false)[&name], bytes);
                }
                assert_eq!(owned.files(true), orphans);
                owned.source_bytes_unchanged();
            }
        }
    }
}

#[test]
fn sequence_cancellation_retains_committed_cache_but_only_returns_complete_documents() {
    for kind in ["images", "apng"] {
        for occurrence in [1, 3] {
            let mut owned = Owned::new(kind);
            let worker = owned.start("image_after_publish", occurrence);
            fs::write(owned.root.join("cancel"), b"stop").unwrap();
            let result = owned.finish(worker);
            assert_eq!(result["ok"], occurrence == 3);
            if occurrence == 1 {
                assert_eq!(result["error"], "CANCELLED");
            }
            assert_complete_images(&owned, occurrence as usize);
            assert!(owned.files(true).is_empty());
            let recovered = owned.invoke();
            assert_complete_images(&owned, 3);
            assert_eq!(
                recovered["document"]["assets"].as_object().unwrap().len(),
                3
            );
            owned.source_bytes_unchanged();
        }
    }
}

#[test]
fn bounded_image_and_font_import_complete_after_late_context_cancellation() {
    for (kind, point) in [
        ("image", "image_before_publish"),
        ("font", "license_after_publish"),
    ] {
        let mut owned = Owned::new(kind);
        let worker = owned.start(point, 1);
        fs::write(owned.root.join("cancel"), b"stop").unwrap();
        let response = owned.finish(worker);
        assert_eq!(response["ok"], true);
        assert_eq!(owned.files(false).len(), if kind == "font" { 2 } else { 1 });
        let cancelled = Control::new(&crate::control::Options {
            timeout_ms: None,
            cancel_file: Some(owned.root.join("cancel")),
        })
        .unwrap();
        assert_eq!(
            invoke(&owned.root, &cancelled).unwrap_err().code,
            "CANCELLED"
        );
        assert!(owned.files(true).is_empty());
        owned.source_bytes_unchanged();
    }
}

#[test]
fn competing_resource_publishers_deduplicate_and_never_replace_corrupt_blobs() {
    for (kind, point, count) in [
        ("image", "image_before_publish", 1),
        ("font", "license_before_publish", 2),
    ] {
        let mut owned = Owned::new(kind);
        let first = owned.start(point, 1);
        let second = owned.start(point, 1);
        owned.release(first);
        owned.release(second);
        let one = owned.finish(first);
        let two = owned.finish(second);
        assert_eq!(one["ok"], true);
        assert_eq!(two["ok"], true);
        assert_eq!(owned.files(false).len(), count);
        assert!(owned.files(true).is_empty());
        if kind == "image" {
            assert_eq!(
                [
                    one["result"]["created"].as_bool().unwrap(),
                    two["result"]["created"].as_bool().unwrap()
                ]
                .iter()
                .filter(|v| **v)
                .count(),
                1
            );
        } else {
            assert_eq!(one["result"], two["result"]);
        }
        let names: Vec<_> = owned.files(false).keys().cloned().collect();
        for name in names {
            let path = owned.root.join("store").join(&name);
            let original = fs::read(&path).unwrap();
            fs::write(&path, b"unrelated original content").unwrap();
            let before = owned.files(false);
            assert_eq!(
                invoke(&owned.root, &Control::default()).unwrap_err().code,
                if kind == "image" {
                    "ASSET_CORRUPT"
                } else {
                    "FONT_CORRUPT"
                }
            );
            assert_eq!(owned.files(false), before);
            assert!(owned.files(true).is_empty());
            fs::write(path, original).unwrap();
        }
        owned.source_bytes_unchanged();
    }
}

// Original minimal two-glyph SFNT. One rectangle, integer metrics and a retained
// synthetic license are enough to exercise the actual public font-import path.
fn original_font() -> Vec<u8> {
    fn u16_at(bytes: &mut [u8], offset: usize, value: u16) {
        bytes[offset..offset + 2].copy_from_slice(&value.to_be_bytes());
    }
    fn u32_at(bytes: &mut [u8], offset: usize, value: u32) {
        bytes[offset..offset + 4].copy_from_slice(&value.to_be_bytes());
    }
    fn checksum(bytes: &[u8]) -> u32 {
        bytes.chunks(4).fold(0u32, |sum, chunk| {
            let mut word = [0u8; 4];
            word[..chunk.len()].copy_from_slice(chunk);
            sum.wrapping_add(u32::from_be_bytes(word))
        })
    }
    let mut head = vec![0; 54];
    u32_at(&mut head, 0, 0x10000);
    u32_at(&mut head, 12, 0x5f0f3cf5);
    u16_at(&mut head, 18, 1000);
    let mut hhea = vec![0; 36];
    u32_at(&mut hhea, 0, 0x10000);
    u16_at(&mut hhea, 34, 2);
    let mut maxp = vec![0; 32];
    u32_at(&mut maxp, 0, 0x10000);
    u16_at(&mut maxp, 4, 2);
    u16_at(&mut maxp, 6, 4);
    u16_at(&mut maxp, 8, 1);
    let hmtx: Vec<u8> = [600u16, 0, 600, 0]
        .into_iter()
        .flat_map(u16::to_be_bytes)
        .collect();
    let mut glyf: Vec<u8> = [1i16, 0, 0, 500, 700, 3, 0]
        .into_iter()
        .flat_map(i16::to_be_bytes)
        .collect();
    glyf.extend([1, 1, 1, 1]);
    glyf.extend(
        [0i16, 500, 0, -500, 0, 0, 700, 0]
            .into_iter()
            .flat_map(i16::to_be_bytes),
    );
    glyf.resize(36, 0);
    let loca: Vec<u8> = [0u16, 0, 18]
        .into_iter()
        .flat_map(u16::to_be_bytes)
        .collect();
    let mut cmap = vec![0; 40];
    u16_at(&mut cmap, 2, 1);
    u16_at(&mut cmap, 4, 3);
    u16_at(&mut cmap, 6, 10);
    u32_at(&mut cmap, 8, 12);
    u16_at(&mut cmap, 12, 12);
    u32_at(&mut cmap, 16, 28);
    u32_at(&mut cmap, 24, 1);
    u32_at(&mut cmap, 28, 65);
    u32_at(&mut cmap, 32, 65);
    u32_at(&mut cmap, 36, 1);
    let tables = BTreeMap::from([
        (*b"head", head),
        (*b"hhea", hhea),
        (*b"maxp", maxp),
        (*b"hmtx", hmtx),
        (*b"glyf", glyf),
        (*b"loca", loca),
        (*b"cmap", cmap),
    ]);
    let mut output = vec![0; 12 + 16 * tables.len()];
    u32_at(&mut output, 0, 0x10000);
    u16_at(&mut output, 4, tables.len() as u16);
    u16_at(&mut output, 6, 64);
    u16_at(&mut output, 8, 2);
    u16_at(&mut output, 10, 48);
    let mut head_offset = 0;
    for (index, (tag, bytes)) in tables.into_iter().enumerate() {
        let offset = output.len();
        let entry = 12 + 16 * index;
        output[entry..entry + 4].copy_from_slice(&tag);
        u32_at(&mut output, entry + 4, checksum(&bytes));
        u32_at(&mut output, entry + 8, offset as u32);
        u32_at(&mut output, entry + 12, bytes.len() as u32);
        if &tag == b"head" {
            head_offset = offset;
        }
        output.extend(bytes);
        output.resize(output.len().next_multiple_of(4), 0);
    }
    let adjustment = 0xb1b0afbau32.wrapping_sub(checksum(&output));
    u32_at(&mut output, head_offset + 8, adjustment);
    output
}
