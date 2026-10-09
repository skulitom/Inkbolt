//! Versioned, content-bound local graphics deliveries and explicit revision links.
use crate::{Document, Error, assets, control::Control, model, sessions::Resources};
use base64::{Engine, engine::general_purpose::STANDARD};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::BTreeMap;
use std::path::Path;

mod clock;
mod verify;

pub const VERSION: u32 = 1;
pub const MAX_PIXELS: u64 = 8_000_000;
pub const MAX_BYTES: usize = crate::publish::MAX_OUTPUT_BYTES;
pub const LOSSES: &[&str] = &[
    "Delivery frames are flattened straight RGBA8 encoded sRGB. Editable artwork remains in the exact source snapshot; its external resource stores are not bundled.",
    "Destination duration, frame rate, sampling and ending are explicit. Source play count is recorded but is not an instruction to the destination.",
    "Transparent scene output uses Cutbolt's separate 8-bit color/matte passes and straight-alpha quantization. Matte output composites in encoded sRGB and discards output alpha.",
    "A revision creates a new pinned delivery. Existing Cutbolt scenes, compiled assets and saved timeline revisions are never updated automatically.",
];

#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
#[schemars(rename = "HandoffTime")]
pub struct Time {
    pub num: u32,
    pub den: u32,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
#[schemars(rename = "HandoffSelection")]
pub enum Selection {
    Still { frame_id: Option<String> },
    Sequence,
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
#[schemars(rename = "HandoffTiming")]
pub enum Timing {
    Strict,
    SampleStart,
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
#[schemars(rename = "HandoffEnding")]
pub enum Ending {
    HoldLast,
    Loop,
    Transparent,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
#[schemars(rename = "HandoffAlpha")]
pub enum Alpha {
    Transparent,
    Matte { background: [u8; 3] },
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
#[schemars(rename = "HandoffOptions")]
pub struct Options {
    /// Stable graphic identity, retained across explicit revision updates.
    pub link_key: String,
    pub selection: Selection,
    pub duration: Time,
    pub frame_rate: Time,
    pub timing: Timing,
    pub end: Ending,
    pub alpha: Alpha,
    #[serde(default = "crate::scale")]
    pub scale: u32,
    #[serde(default)]
    pub render_options: Option<crate::render_quality::Options>,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
#[schemars(rename = "HandoffFile")]
pub struct File {
    pub path: String,
    pub sha256: String,
    pub bytes: u64,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
#[schemars(rename = "HandoffSource")]
pub struct Source {
    pub document_id: String,
    pub revision: u64,
    pub snapshot: File,
    pub sequence_plays: Option<u32>,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
#[schemars(rename = "HandoffFrame")]
pub struct Frame {
    pub id: Option<String>,
    pub dataset: Option<String>,
    pub source_delay: Option<crate::sequences::Delay>,
    pub hold: Time,
    pub image: File,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
#[schemars(rename = "HandoffPrevious")]
pub struct Previous {
    pub sha256: String,
    pub source_revision: u64,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
#[schemars(rename = "HandoffManifest")]
pub struct Manifest {
    pub schema_version: u32,
    pub options: Options,
    pub source: Source,
    pub width: u32,
    pub height: u32,
    pub frames: Vec<Frame>,
    pub scene: File,
    pub previous: Option<Previous>,
    pub losses: Vec<String>,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
#[schemars(rename = "HandoffPinned")]
pub struct Pinned {
    /// Hash of compact typed manifest bytes returned by handoff.export.
    pub sha256: String,
    pub manifest: Manifest,
}
fn invalid(message: &str) -> Error {
    Error::new("INVALID_HANDOFF", message)
}
fn bytes<T: Serialize>(value: &T) -> Result<Vec<u8>, Error> {
    serde_json::to_vec(value).map_err(|_| invalid("Unable to serialize handoff content"))
}
fn hash_valid(hash: &str) -> bool {
    hash.len() == 64
        && hash
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
fn identity(prefix: &str, extension: &str, data: &[u8]) -> File {
    let sha256 = assets::sha256(data);
    File {
        path: format!("{prefix}-{sha256}.{extension}"),
        sha256,
        bytes: data.len() as u64,
    }
}
fn add(files: &mut BTreeMap<String, Vec<u8>>, file: &File, data: Vec<u8>) -> Result<(), Error> {
    if let Some(old) = files.get(&file.path) {
        if old != &data {
            return Err(invalid("Conflicting delivery file identity"));
        }
    } else {
        files.insert(file.path.clone(), data);
    }
    if files.values().map(Vec::len).sum::<usize>() > MAX_BYTES {
        return Err(model::limit(
            "Handoff files exceed the 32 MiB aggregate byte budget",
        ));
    }
    Ok(())
}
pub(super) fn scene(manifest: &Manifest) -> Value {
    let (transparent, background) = match manifest.options.alpha {
        Alpha::Transparent => (true, [0, 0, 0]),
        Alpha::Matte { background } => (false, background),
    };
    json!({"schema_version":1,"id":manifest.options.link_key,"width":manifest.width,
        "height":manifest.height,"output_scale":1,"duration":manifest.options.duration,
        "frame_rate":manifest.options.frame_rate,"background":background,"transparent":transparent,
        "color":"srgb_straight_encoded","audio":null,"layers":[{
            "id":"graphic","canvas":[manifest.width,manifest.height],"start":{"num":0,"den":1},
            "duration":manifest.options.duration,"frames":manifest.frames.iter().map(|frame| json!({
                "image":frame.image,"hold":frame.hold,"offset":[0,0],"anchor":[0,0]})).collect::<Vec<_>>(),
            "timing":manifest.options.timing,"end":manifest.options.end,"alpha_mode":"straight",
            "transform":{"crop":[0,0,manifest.width,manifest.height],"quarter_turns":0,"scale":1,
                         "position":[0,0],"opacity":255}}]})
}

/// Pure export: all files are returned only after every frame and identity succeeds.
pub fn export(
    document: &Document,
    resources: &Resources,
    options: &Options,
    previous: Option<&Pinned>,
    control: &Control,
) -> Result<Value, Error> {
    control.check()?;
    model::validate_controlled(document, control)?;
    clock::options(options)?;
    if document.output_profile.is_some() {
        return Err(Error::new(
            "UNSUPPORTED",
            "Handoff requires encoded sRGB PNG without an output ICC profile; clear the association explicitly on a delivery copy",
        ));
    }
    let previous = previous.map(|pin| {
        validate(pin, control)?;
        if pin.manifest.options.link_key != options.link_key || pin.manifest.source.document_id != document.id
            || document.revision <= pin.manifest.source.revision {
            return Err(Error::new("HANDOFF_CONFLICT", "Revision update requires the same link_key and document ID and a strictly newer source revision"));
        }
        Ok(Previous { sha256: pin.sha256.clone(), source_revision: pin.manifest.source.revision })
    }).transpose()?;
    let plan = crate::render_quality::Plan::for_document(
        document,
        options.scale,
        options.render_options.as_ref(),
    )?;
    let [width, height] = plan.output;
    if width > 4096 || height > 4096 || width as u64 * height as u64 > MAX_PIXELS {
        return Err(model::limit(
            "Handoff canvas exceeds 4096 per axis or eight million pixels",
        ));
    }
    let specs = clock::source_frames(document, options)?;
    clock::schedule(
        options,
        &specs.iter().map(|f| f.3).collect::<Vec<_>>(),
        control,
    )?;
    let evaluated = plan.evaluation[0] as u64
        * plan.evaluation[1] as u64
        * (plan.internal_scale as u64).pow(2)
        * specs.len() as u64;
    if width as u64 * height as u64 * specs.len() as u64 > crate::sequences::MAX_PIXELS
        || evaluated.saturating_mul(document.items.len().max(1) as u64)
            > crate::render::MAX_RENDER_WORK
    {
        return Err(model::limit(
            "Handoff exceeds aggregate frame pixels or scene work",
        ));
    }
    let mut files = BTreeMap::new();
    let source_bytes = bytes(document)?;
    let snapshot = identity("source", "json", &source_bytes);
    add(&mut files, &snapshot, source_bytes)?;
    let mut frames = Vec::new();
    for (id, dataset, source_delay, hold) in specs {
        control.check()?;
        let mut view = match &dataset {
            Some(dataset) => crate::variants::view(document, dataset)?,
            None => document.clone(),
        };
        view.variants = None;
        let artifact = crate::publish::export_with_render_options(
            &view,
            crate::ExportFormat::Png,
            options.scale,
            resources,
            crate::publish::FormatOptions {
                control: Some(control),
                render_options: options.render_options.as_ref(),
                metadata_policy: Some(crate::metadata::Policy {
                    mode: crate::metadata::Mode::Strip,
                    ..Default::default()
                }),
                ..Default::default()
            },
        )?;
        let raw = STANDARD
            .decode(
                artifact["data"]
                    .as_str()
                    .ok_or_else(|| invalid("Missing PNG payload"))?,
            )
            .map_err(|_| invalid("Invalid PNG payload"))?;
        let image = identity("frame", "png", &raw);
        add(&mut files, &image, raw)?;
        frames.push(Frame {
            id,
            dataset,
            source_delay,
            hold,
            image,
        });
    }
    let mut manifest = Manifest {
        schema_version: VERSION,
        options: options.clone(),
        source: Source {
            document_id: document.id.clone(),
            revision: document.revision,
            snapshot,
            sequence_plays: document
                .variants
                .as_ref()
                .and_then(|v| v.sequence.as_ref())
                .map(|s| s.plays),
        },
        width,
        height,
        frames,
        scene: identity("scene", "json", &[]),
        previous,
        losses: LOSSES.iter().map(|s| s.to_string()).collect(),
    };
    let scene_bytes = bytes(&scene(&manifest))?;
    manifest.scene = identity("scene", "json", &scene_bytes);
    add(&mut files, &manifest.scene, scene_bytes)?;
    let manifest_bytes = bytes(&manifest)?;
    let manifest_file = identity("handoff", "json", &manifest_bytes);
    let pin = Pinned {
        sha256: manifest_file.sha256.clone(),
        manifest,
    };
    validate(&pin, control)?;
    add(&mut files, &manifest_file, manifest_bytes)?;
    control.check()?;
    Ok(
        json!({"handoff":pin,"manifest_file":manifest_file,"files":files.into_iter().map(|(path,data)|json!({
        "path":path,"sha256":assets::sha256(&data),"bytes":data.len(),"encoding":"base64","data":STANDARD.encode(data)})).collect::<Vec<_>>(),
        "source_preserved":true,"writes_files":false,"publication":"Write each returned file create-only; consume only after handoff.inspect verifies the pinned manifest and all files. Never replace an existing linked revision."}),
    )
}

fn validate(pin: &Pinned, control: &Control) -> Result<Vec<Option<usize>>, Error> {
    control.check()?;
    let m = &pin.manifest;
    if m.schema_version != VERSION {
        return Err(Error::new(
            "UNSUPPORTED_HANDOFF_VERSION",
            "Only handoff schema_version 1 is supported",
        ));
    }
    if !hash_valid(&pin.sha256) || assets::sha256(&bytes(m)?) != pin.sha256 {
        return Err(Error::new(
            "SOURCE_MISMATCH",
            "Handoff manifest differs from its pinned SHA-256",
        ));
    }
    if !model::valid_id(&m.source.document_id)
        || m.width == 0
        || m.height == 0
        || m.width > 4096
        || m.height > 4096
        || m.width as u64 * m.height as u64 > MAX_PIXELS
        || m.frames.is_empty()
        || m.frames.len() > crate::sequences::MAX_FRAMES
        || m.width as u64 * m.height as u64 * m.frames.len() as u64 > crate::sequences::MAX_PIXELS
    {
        return Err(invalid(
            "Handoff identity, canvas or frame count is outside its bounds",
        ));
    }
    if m.losses != LOSSES.iter().map(|s| s.to_string()).collect::<Vec<_>>() {
        return Err(invalid(
            "Version 1 handoff loss declarations must be retained",
        ));
    }
    if let Some(previous) = &m.previous
        && (!hash_valid(&previous.sha256) || previous.source_revision >= m.source.revision)
    {
        return Err(invalid("Invalid predecessor identity or revision"));
    }
    verify::inventory(m)?;
    if identity("scene", "json", &bytes(&scene(m))?) != m.scene {
        return Err(invalid(
            "Scene identity does not match the declared frames and policies",
        ));
    }
    clock::schedule(
        &m.options,
        &m.frames.iter().map(|f| f.hold).collect::<Vec<_>>(),
        control,
    )
}

pub fn inspect(
    pin: &Pinned,
    input_root: Option<&Path>,
    include_schedule: bool,
    control: &Control,
) -> Result<Value, Error> {
    let selected = validate(pin, control)?;
    if let Some(root) = input_root {
        verify::files(pin, root, control)?;
    }
    let mut result = json!({"schema_version":VERSION,"sha256":pin.sha256,"link_key":pin.manifest.options.link_key,
        "source":pin.manifest.source,"previous":pin.manifest.previous,"manifest_verified":true,
        "files_verified":input_root.is_some(),"frame_files":pin.manifest.frames.len(),"output_frames":selected.len(),
        "selection_sha256":assets::sha256(&bytes(&selected)?),"scene":pin.manifest.scene,"losses":pin.manifest.losses,
        "read_only":true,"scope":"Identity and declared delivery contract. This is not a re-render or proof of authenticity; retain the trusted manifest pin. Source stores remain external."});
    if include_schedule {
        result["selected_frames"] = json!(selected);
    }
    control.check()?;
    Ok(result)
}
