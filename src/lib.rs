pub mod adjustments;
pub mod appearance;
pub mod artwork_masks;
pub mod assets;
pub mod assistance;
pub mod backgrounds;
pub mod blending;
pub mod boards;
pub mod booleans;
pub mod canvas;
pub mod channels;
pub mod checks;
pub mod color_adjustments;
pub mod contact_sheets;
pub mod control;
pub mod coverage;
pub mod creative_filters;
pub mod detail_filters;
pub mod diff;
pub mod dimensions;
pub mod edit;
pub mod effects;
pub mod filters;
mod finite;
pub mod fonts;
pub mod geometry;
pub mod handoff;
pub mod hdr;
pub mod hyphenation;
pub mod image_io;
pub mod ink_recipes;
pub mod inspection;
pub mod instances;
pub mod interpolation;
pub mod job_process;
pub mod jobs;
mod knockout;
mod layer_clipping;
pub mod layered;
pub mod layout;
pub mod limits;
pub mod masks;
pub mod mcp;
mod mcp_preview;
pub mod measurements;
pub mod meshes;
pub mod metadata;
pub mod model;
mod native_pixels;
pub mod objects;
pub mod paint;
pub mod path_text;
pub mod paths;
pub mod pdf;
pub mod pixel_brush;
pub mod pixel_warps;
pub mod prepress;
pub mod presets;
pub mod previews;
pub mod primitives;
pub mod profiles;
pub mod proof;
pub mod publications;
pub mod publish;
pub mod query;
pub mod raw;
pub mod render;
pub mod render_quality;
pub mod repair;
pub mod repeats;
pub mod request;
mod resample;
#[cfg(all(test, windows))]
mod resource_recovery_tests;
pub mod responses;
pub mod retouch;
pub mod sample_convert;
pub mod sample_import;
pub mod sample_profiles;
pub mod sample_store;
mod sample_tiff;
pub mod samples;
pub mod scene;
pub mod schema;
pub mod selection_analysis;
pub mod selections;
pub mod sequences;
pub mod sessions;
pub mod simplify;
pub mod snapping;
pub mod spatial_filters;
pub mod stored_samples;
pub mod strokes;
mod svg;
pub mod svg_import;
pub mod swatches;
pub mod text;
pub mod tracing;
pub mod transfer;
pub mod variants;
pub mod vector_canvas;
pub mod vector_native;
pub mod visual_diff;
pub mod volumes;
pub mod warps;
mod work_paths;
pub mod workspace;

pub use model::{ColorSpace, Document, DocumentKind, MAX_DIMENSION, validate};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::path::PathBuf;

pub use crate::limits::request::MAX_REQUEST_BYTES;
#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum ExportFormat {
    NativeVector,
    Layered,
    LayeredLarge,
    Gif,
    Bmp,
    Tga,
    Pdf,
    Apng,
    Snapshot,
    Svg,
    Png,
    Jpeg,
    Tiff,
}
fn scale() -> u32 {
    1
}
fn resolution() -> f64 {
    f64::from(limits::model::DEFAULT_RESOLUTION_PPI)
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(tag = "command", deny_unknown_fields)]
pub enum Request {
    #[serde(rename = "preset.list")]
    PresetList {},
    #[serde(rename = "preset.create")]
    PresetCreate {
        id: String,
        version: u32,
        preset: presets::Spec,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "handoff.export")]
    HandoffExport {
        document: Document,
        #[serde(default)]
        resources: sessions::Resources,
        options: handoff::Options,
        #[serde(default)]
        previous: Option<handoff::Pinned>,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "handoff.inspect")]
    HandoffInspect {
        handoff: handoff::Pinned,
        #[serde(default)]
        input_root: Option<PathBuf>,
        #[serde(default)]
        include_schedule: bool,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "layered.import")]
    LayeredImport {
        source_path: PathBuf,
        #[serde(default)]
        expected_sha256: Option<String>,
        id: String,
        #[serde(default)]
        color_policy: assets::ColorPolicy,
        #[serde(default)]
        embedded_objects: Option<layered::EmbeddedObjects>,
        #[serde(default)]
        control: control::Options,
        #[serde(default)]
        text_fonts: Option<layered::TextFonts>,
    },
    #[serde(rename = "assist.segment")]
    AssistSegment {
        document: Document,
        id: String,
        options: assistance::segment::Options,
        asset_root: Option<PathBuf>,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "assist.layout")]
    AssistLayout {
        document: Document,
        options: assistance::Layout,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "volume.inspect")]
    VolumeInspect { document: Document, id: String },
    #[serde(rename = "appearance.inspect")]
    AppearanceInspect { document: Document, id: String },
    #[serde(rename = "sequence.import")]
    SequenceImport {
        source: sequences::Source,
        store_root: PathBuf,
        id: String,
        #[serde(default)]
        color_policy: assets::ColorPolicy,
        #[serde(default = "resolution")]
        resolution_ppi: f64,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "sequence.export")]
    SequenceExport {
        document: Document,
        #[serde(default)]
        resources: sessions::Resources,
        #[serde(default = "scale")]
        scale: u32,
        #[serde(default)]
        render_options: Option<render_quality::Options>,
        #[serde(default)]
        metadata_policy: Option<metadata::Policy>,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "sequence.inspect")]
    SequenceInspect { document: Document },
    #[serde(rename = "sequence.open")]
    SequenceOpen { document: Document, id: String },
    #[serde(rename = "object.import")]
    ObjectImport {
        #[serde(default)]
        source_path: Option<PathBuf>,
        #[serde(default)]
        snapshot: Option<String>,
        #[serde(default)]
        link_key: Option<String>,
    },
    #[serde(rename = "object.open")]
    ObjectOpen { document: Document, id: String },
    #[serde(rename = "object.status")]
    ObjectStatus {
        document: Document,
        id: String,
        #[serde(default)]
        link_root: Option<PathBuf>,
    },
    #[serde(rename = "sample.measure")]
    SampleMeasure {
        document: Document,
        #[serde(default)]
        points: Vec<[u32; 2]>,
        #[serde(default)]
        asset_root: Option<PathBuf>,
        #[serde(default)]
        font_root: Option<PathBuf>,
    },
    #[serde(rename = "sample.import")]
    SampleImport {
        source_path: PathBuf,
        id: String,
        #[serde(default = "resolution")]
        resolution_ppi: f64,
        #[serde(default)]
        color_policy: sample_import::Policy,
        #[serde(default)]
        storage: Option<sample_import::NativeStore>,
    },
    #[serde(rename = "raw.develop")]
    RawDevelop {
        source_path: PathBuf,
        #[serde(default)]
        expected_sha256: Option<String>,
        id: String,
        capture: raw::Capture,
        settings: raw::Settings,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "raw.retain")]
    RawRetain {
        source_path: PathBuf,
        #[serde(default)]
        expected_sha256: Option<String>,
        id: String,
        capture: raw::Capture,
        settings: raw::Settings,
        #[serde(default)]
        corrections: raw::Corrections,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "raw.reopen")]
    RawReopen {
        source_path: PathBuf,
        recipe_path: PathBuf,
        id: String,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "raw.recipe")]
    RawRecipe { document: Document, id: String },
    #[serde(rename = "swatch.inspect")]
    SwatchInspect { document: Document },
    #[serde(rename = "geometry.measure")]
    GeometryMeasure {
        document: Document,
        options: dimensions::Options,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "pixel_warp.inspect")]
    PixelWarpInspect {
        warp: pixel_warps::Spec,
        width: f64,
        height: f64,
        #[serde(default)]
        samples: Vec<model::Point>,
        #[serde(default)]
        inverse_samples: Vec<model::Point>,
        #[serde(default)]
        include_mesh: bool,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "warp.inspect")]
    WarpInspect {
        warp: warps::Spec,
        #[serde(default)]
        samples: Vec<model::Point>,
        grid: Option<warps::Grid>,
        #[serde(default)]
        include_geometry: bool,
        #[serde(default)]
        include_segments: bool,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "repeat.inspect")]
    RepeatInspect {
        repeat: repeats::Spec,
        #[serde(default)]
        include_geometry: bool,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "interpolation.inspect")]
    InterpolationInspect {
        interpolation: interpolation::Spec,
        #[serde(default)]
        include_geometry: bool,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "brush.inspect")]
    BrushInspect {
        stroke: pixel_brush::Stroke,
        #[serde(default)]
        include_dabs: bool,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "image.trace")]
    ImageTrace {
        id: String,
        source: tracing::Source,
        options: tracing::Options,
        asset_root: Option<PathBuf>,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "mesh.inspect")]
    MeshInspect {
        mesh: meshes::Mesh,
        #[serde(default)]
        space: paint::Interpolation,
        #[serde(default)]
        parameters: Vec<model::Point>,
    },
    #[serde(rename = "svg.import")]
    SvgImport {
        #[serde(default)]
        resource_profile: model::ResourceProfile,
        #[serde(default)]
        control: control::Options,
        id: String,
        source: svg_import::Source,
        #[serde(default)]
        images: svg_import::ImageOptions,
        #[serde(default)]
        unsupported: svg_import::UnsupportedPolicy,
        #[serde(default)]
        font_bindings: Vec<svg_import::FontBinding>,
        #[serde(default)]
        font_root: Option<PathBuf>,
    },
    #[serde(rename = "vector.import")]
    VectorImport {
        id: String,
        source_path: PathBuf,
        color_policy: vector_native::ColorPolicy,
        #[serde(default)]
        resource_profile: model::ResourceProfile,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "capabilities")]
    Capabilities {},
    #[serde(rename = "schema")]
    Schema {},
    #[serde(rename = "schema.lookup")]
    SchemaLookup {
        /// Command name, shared type alias, or index to discover available names.
        name: String,
        /// A listed variant/definition, or nested components separated by /; use an outline variant's select value.
        select: Option<String>,
        /// Return the complete schema even when it exceeds the outline budget.
        #[serde(default)]
        full: bool,
    },
    #[serde(rename = "implementation.status")]
    ImplementationStatus {},
    #[serde(rename = "document.publish")]
    Publish {
        document: Document,
        #[serde(default)]
        resources: sessions::Resources,
        output: publish::Options,
        /// Optional durable prepared receipt for idempotent publication and recovery.
        #[serde(default)]
        receipt: Option<publications::ReceiptTarget>,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "session.publish")]
    SessionPublish {
        session_root: PathBuf,
        session_id: String,
        expected_revision: u64,
        output: publish::Options,
        /// Optional durable receipt; retries do not recapture an advanced session.
        #[serde(default)]
        receipt: Option<publications::ReceiptTarget>,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "publication.receipt")]
    PublicationReceipt {
        receipt_root: PathBuf,
        request_id: String,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "publication.recover")]
    PublicationRecover {
        receipt_root: PathBuf,
        request_id: String,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "job.start")]
    JobStart {
        job_root: PathBuf,
        request_id: String,
        document: Document,
        #[serde(default)]
        resources: sessions::Resources,
        output: publish::Options,
        #[serde(default)]
        options: jobs::Options,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "job.status")]
    JobStatus {
        job_root: PathBuf,
        request_id: String,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "job.list")]
    JobList {
        job_root: PathBuf,
        #[serde(default)]
        options: jobs::ListOptions,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "job.result")]
    JobResult {
        job_root: PathBuf,
        request_id: String,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "job.wait")]
    JobWait {
        job_root: PathBuf,
        request_id: String,
        #[serde(default)]
        wait_ms: u64,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "job.cancel")]
    JobCancel {
        job_root: PathBuf,
        request_id: String,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "job.resume")]
    JobResume {
        job_root: PathBuf,
        request_id: String,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "document.diff")]
    Diff {
        before: Box<Document>,
        after: Box<Document>,
        #[serde(default)]
        before_resources: sessions::Resources,
        #[serde(default)]
        after_resources: sessions::Resources,
        #[serde(default)]
        compare_pixels: bool,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "document.diff.preview")]
    DiffPreview {
        before: Box<Document>,
        after: Box<Document>,
        #[serde(default)]
        before_resources: sessions::Resources,
        #[serde(default)]
        after_resources: sessions::Resources,
        #[serde(default)]
        options: visual_diff::Options,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "session.diff.preview")]
    SessionDiffPreview {
        session_root: PathBuf,
        session_id: String,
        from_revision: u64,
        to_revision: u64,
        #[serde(default)]
        options: visual_diff::Options,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "session.diff")]
    SessionDiff {
        session_root: PathBuf,
        session_id: String,
        from_revision: u64,
        to_revision: u64,
        #[serde(default)]
        compare_pixels: bool,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "session.create")]
    SessionCreate {
        session_root: PathBuf,
        session_id: String,
        request_id: String,
        document: Document,
        #[serde(default)]
        resources: sessions::Resources,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "session.read")]
    SessionRead {
        session_root: PathBuf,
        session_id: String,
        snapshot: Option<String>,
    },
    #[serde(rename = "session.apply")]
    SessionApply {
        session_root: PathBuf,
        session_id: String,
        request_id: String,
        expected_revision: u64,
        action: sessions::Action,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "session.dry_run")]
    SessionDryRun {
        session_root: PathBuf,
        session_id: String,
        request_id: String,
        expected_revision: u64,
        action: sessions::Action,
        #[serde(default)]
        options: sessions::DryRunOptions,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "session.apply_proposal")]
    SessionApplyProposal {
        session_root: PathBuf,
        proposal: sessions::Proposal,
        action: sessions::Action,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "session.receipt")]
    SessionReceipt {
        session_root: PathBuf,
        session_id: String,
        request_id: String,
    },
    #[serde(rename = "session.history")]
    SessionHistory {
        session_root: PathBuf,
        session_id: String,
        after_revision: Option<u64>,
        limit: usize,
    },
    #[serde(rename = "session.verify")]
    SessionVerify {
        session_root: PathBuf,
        session_id: String,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "session.backup")]
    SessionBackup {
        session_root: PathBuf,
        session_id: String,
        expected_revision: u64,
        output: sessions::backup::Output,
        #[serde(default)]
        receipt: Option<publications::ReceiptTarget>,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "session.recover")]
    SessionRecover {
        session_root: PathBuf,
        session_id: String,
        source: sessions::backup::Source,
        #[serde(default)]
        receipt: Option<publications::ReceiptTarget>,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "session.migrate")]
    SessionMigrate {
        session_id: String,
        source: sessions::backup::Source,
        target_version: i64,
        output: sessions::backup::Output,
        #[serde(default)]
        receipt: Option<publications::ReceiptTarget>,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "session.continue")]
    SessionContinue {
        session_root: PathBuf,
        session_id: String,
        request_id: String,
        parent: sessions::lineage::Parent,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "artboard.export")]
    ArtboardExport {
        #[serde(default)]
        render_options: Option<render_quality::Options>,
        metadata_policy: Option<metadata::Policy>,
        document: Document,
        #[serde(default)]
        image_options: Option<image_io::Options>,
        #[serde(default)]
        selection: boards::Selection,
        format: boards::Format,
        #[serde(default = "scale")]
        scale: u32,
        #[serde(default)]
        include_bleed: bool,
        asset_root: Option<PathBuf>,
        font_root: Option<PathBuf>,
    },
    #[serde(rename = "font.import")]
    FontImport {
        source_path: PathBuf,
        license_path: PathBuf,
        store_root: PathBuf,
        #[serde(default)]
        face_index: u32,
    },
    #[serde(rename = "font.verify")]
    FontVerify {
        font: fonts::Font,
        font_root: Option<PathBuf>,
    },
    #[serde(rename = "font.inspect")]
    FontInspect {
        font: fonts::Font,
        font_root: Option<PathBuf>,
        #[serde(default)]
        variations: fonts::Coordinates,
    },
    #[serde(rename = "text.inspect")]
    TextInspect {
        document: Document,
        id: String,
        font_root: Option<PathBuf>,
        #[serde(default)]
        include_outlines: bool,
    },
    #[serde(rename = "text.directions")]
    TextDirections {
        text: String,
        direction: text::Direction,
        #[serde(default)]
        lines: Vec<text::bidi::Range>,
    },
    #[serde(rename = "text.hyphenate")]
    TextHyphenate {
        rules: hyphenation::Rules,
        words: Vec<String>,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "story.inspect")]
    StoryInspect {
        document: Document,
        id: String,
        font_root: Option<PathBuf>,
        #[serde(default)]
        include_outlines: bool,
    },
    #[serde(rename = "asset.import")]
    AssetImport {
        source_path: PathBuf,
        store_root: PathBuf,
        #[serde(default)]
        color_policy: assets::ColorPolicy,
        input_profile: Option<profiles::Profile>,
    },
    #[serde(rename = "asset.verify")]
    AssetVerify {
        asset: assets::ImageAsset,
        asset_root: Option<PathBuf>,
    },
    #[serde(rename = "asset.embed")]
    AssetEmbed {
        asset: assets::ImageAsset,
        asset_root: Option<PathBuf>,
    },
    #[serde(rename = "document.create")]
    Create {
        #[serde(default)]
        resource_profile: model::ResourceProfile,
        id: String,
        kind: DocumentKind,
        width: u32,
        height: u32,
        #[serde(default = "resolution")]
        resolution_ppi: f64,
    },
    #[serde(rename = "document.validate")]
    Validate { document: Document },
    #[serde(rename = "document.check")]
    Check {
        document: Document,
        #[serde(default)]
        options: checks::Options,
        #[serde(default)]
        resources: sessions::Resources,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "document.preflight")]
    Preflight {
        document: Document,
        output: publish::Options,
        #[serde(default)]
        resources: sessions::Resources,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "document.inspect")]
    Inspect { document: Document },
    #[serde(rename = "document.inspect.page")]
    InspectPage {
        document: Document,
        #[serde(default)]
        options: inspection::Options,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "document.preview")]
    Preview {
        document: Document,
        #[serde(default)]
        options: previews::Options,
        asset_root: Option<PathBuf>,
        font_root: Option<PathBuf>,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "document.contact_sheet")]
    ContactSheet {
        document: Document,
        #[serde(default)]
        options: contact_sheets::Options,
        asset_root: Option<PathBuf>,
        font_root: Option<PathBuf>,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "document.query")]
    Query {
        document: Document,
        query: query::Query,
    },
    #[serde(rename = "document.measure")]
    Measure {
        document: Document,
        #[serde(default)]
        options: measurements::Options,
        asset_root: Option<PathBuf>,
        font_root: Option<PathBuf>,
    },
    #[serde(rename = "channel.export")]
    ChannelExport {
        document: Document,
        id: String,
        #[serde(default)]
        display: channels::Display,
    },
    #[serde(rename = "document.boolean")]
    Boolean {
        document: Document,
        ids: Vec<String>,
        mode: booleans::Mode,
        #[serde(default = "booleans::default_tolerance")]
        curve_tolerance: f64,
    },
    #[serde(rename = "document.select")]
    Select {
        document: Document,
        ids: Vec<String>,
    },
    #[serde(rename = "document.edit")]
    Edit {
        document: Document,
        expected_revision: u64,
        operations: Vec<edit::Operation>,
        asset_root: Option<PathBuf>,
        font_root: Option<PathBuf>,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "document.render")]
    Render {
        #[serde(default)]
        control: control::Options,
        #[serde(default)]
        render_options: Option<render_quality::Options>,
        document: Document,
        #[serde(default = "scale")]
        scale: u32,
        asset_root: Option<PathBuf>,
        font_root: Option<PathBuf>,
    },
    #[serde(rename = "document.proof")]
    Proof {
        document: Document,
        options: proof::Options,
        asset_root: Option<PathBuf>,
        font_root: Option<PathBuf>,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "document.prepress")]
    Prepress {
        document: Document,
        options: prepress::Options,
        asset_root: Option<PathBuf>,
        font_root: Option<PathBuf>,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "document.separations")]
    Separations {
        document: Document,
        #[serde(default = "scale")]
        scale: u32,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "color.convert")]
    ColorConvert {
        source: profiles::device::Endpoint,
        destination: profiles::device::Endpoint,
        values: Vec<Vec<f64>>,
        #[serde(default)]
        intent: profiles::Intent,
        #[serde(default)]
        gamut: Option<profiles::gamut::Mode>,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "profile.gamut")]
    ProfileGamut {
        profile: profiles::cmyk::Source,
        xyz_d50: Vec<[f64; 3]>,
        #[serde(default)]
        intent: profiles::Intent,
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "document.export")]
    Export {
        #[serde(default)]
        control: control::Options,
        #[serde(default)]
        render_options: Option<render_quality::Options>,
        metadata_policy: Option<metadata::Policy>,
        document: Document,
        #[serde(default)]
        image_options: Option<image_io::Options>,
        #[serde(default)]
        pdf_options: Option<pdf::Options>,
        #[serde(default)]
        layered_options: Option<layered::ExportOptions>,
        format: ExportFormat,
        #[serde(default = "scale")]
        scale: u32,
        asset_root: Option<PathBuf>,
        font_root: Option<PathBuf>,
    },
}

#[derive(Debug, Serialize)]
pub struct Error {
    pub code: &'static str,
    pub message: Box<str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub operation_index: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub asset_id: Option<Box<str>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub font_id: Option<Box<str>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub artboard_id: Option<Box<str>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub item_id: Option<Box<str>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub details: Option<Box<Value>>,
}
impl Error {
    pub fn new(code: &'static str, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into().into_boxed_str(),
            operation_index: None,
            asset_id: None,
            font_id: None,
            artboard_id: None,
            item_id: None,
            details: None,
        }
    }
    pub fn at_operation(mut self, index: usize) -> Self {
        self.operation_index = Some(index);
        self
    }
    pub fn at_item(mut self, id: &str) -> Self {
        self.item_id = Some(id.into());
        self
    }
    pub fn at_artboard(mut self, id: &str) -> Self {
        self.artboard_id = Some(id.into());
        self
    }
    pub fn at_font(mut self, id: &str) -> Self {
        self.font_id = Some(id.into());
        self
    }
    pub fn at_asset(mut self, id: &str) -> Self {
        self.asset_id = Some(id.into());
        self
    }
}
pub fn implementation_status() -> Value {
    serde_json::from_str(include_str!("../docs/features.json"))
        .expect("checked implementation registry")
}
// Keep capability-report construction off ordinary execution stacks. Its
// many JSON temporaries otherwise inflate every command frame in debug builds.
#[inline(never)]
fn capability_report() -> Value {
    let mut limits = json!({"request_bytes":MAX_REQUEST_BYTES,"document_bytes":model::MAX_DOCUMENT_BYTES,"dimension_pixels":MAX_DIMENSION,"items":model::MAX_ITEMS,"hierarchy_depth":scene::MAX_DEPTH,"path_commands":model::MAX_SEGMENTS,"stored_pixels":model::MAX_STORED_PIXELS,"batch_operations":edit::MAX_OPERATIONS,"render_pixels":render::MAX_RENDER_PIXELS,"render_work":render::MAX_RENDER_WORK,"group_buffer_pixels":render::MAX_BUFFER_PIXELS,"render_scale":[1,limits::render_quality::MAX_SCALE],"gradient_stops_per_paint":paint::MAX_STOPS,"gradient_stops_and_anchors":paint::MAX_PAINT_SAMPLES,"pattern_tile_pixels":paint::MAX_PATTERN_PIXELS,"paint_work":paint::MAX_PAINT_WORK,"image_assets":assets::MAX_ASSETS,"asset_pixels":assets::MAX_ASSET_PIXELS,"import_bytes":assets::MAX_IMPORT_BYTES,"svg_image_copy_pixels":assets::MAX_ASSET_PIXELS});
    let more = json!({"fonts":fonts::MAX_FONTS,"font_bytes":fonts::MAX_FONT_BYTES,"font_license_bytes":fonts::MAX_LICENSE_BYTES,"text_characters":text::MAX_TEXT_CHARS,"text_ranges_per_frame":text::MAX_TEXT_RANGES,"text_glyphs":text::MAX_GLYPHS,"text_outline_commands":text::MAX_OUTLINE_COMMANDS,"artboards":boards::MAX_ARTBOARDS,"guides":boards::MAX_GUIDES,"guides_per_frame":boards::MAX_FRAME_GUIDES,"bleed_per_edge":boards::MAX_BLEED,"artboard_batch_pixels":boards::MAX_BATCH_PIXELS,"artboard_batch_encoded_bytes":boards::MAX_BATCH_BYTES,"artboard_batch_work":boards::MAX_BATCH_WORK});
    limits
        .as_object_mut()
        .unwrap()
        .extend(more.as_object().unwrap().clone());
    limits.as_object_mut().unwrap().extend(json!({"session_states":sessions::MAX_STATES,"session_requests":sessions::MAX_REQUESTS,"session_snapshots":sessions::MAX_SNAPSHOTS,"session_state_bytes":sessions::MAX_STATE_BYTES,"session_history_bytes":sessions::MAX_HISTORY_BYTES,"session_database_bytes":sessions::MAX_DATABASE_BYTES,"session_receipt_bytes":sessions::MAX_RECEIPT_BYTES,"control_timeout_ms":control::MAX_TIMEOUT_MS}).as_object().unwrap().clone());
    limits.as_object_mut().unwrap().extend(json!({"mask_feather_radius":masks::MAX_FEATHER,"mask_prepared_pixels":masks::MAX_PREPARED_PIXELS,"mask_document_prepared_pixels":masks::MAX_DOCUMENT_PIXELS,"mask_feather_work":masks::MAX_FEATHER_WORK}).as_object().unwrap().clone());
    limits.as_object_mut().unwrap().extend(json!({"artwork_mask_references":artwork_masks::MAX_MASKS,"artwork_mask_coverage_pixels":artwork_masks::MAX_COVERAGE_PIXELS,"artwork_mask_svg_copies":artwork_masks::MAX_SVG_ITEMS}).as_object().unwrap().clone());
    limits.as_object_mut().unwrap().extend(json!({"selection_pixels":selections::MAX_PIXELS,"selection_work":selections::MAX_WORK,"selection_radius":selections::MAX_RADIUS,"selection_polygon_points":selections::MAX_POLYGON_POINTS,"selection_coverage_subrows":selections::COVERAGE_SUBROWS}).as_object().unwrap().clone());
    limits.as_object_mut().unwrap().extend(json!({"polygon_points":primitives::MAX_POLYGON_POINTS,"regular_polygon_sides":primitives::MAX_SIDES,"star_points":primitives::MAX_STAR_POINTS}).as_object().unwrap().clone());
    limits.as_object_mut().unwrap().extend(json!({"adjustment_operators_per_layer":adjustments::MAX_OPERATORS,"adjustment_operators":adjustments::MAX_DOCUMENT_OPERATORS,"tone_curve_points":adjustments::MAX_CURVE_POINTS,"measurement_samples":measurements::MAX_SAMPLES}).as_object().unwrap().clone());
    limits.as_object_mut().unwrap().extend(json!({"color_lut_1d_entries":color_adjustments::MAX_LUT_1D,"color_lut_3d_side":color_adjustments::MAX_LUT_3D_SIDE,"color_lut_entries":color_adjustments::MAX_DOCUMENT_LUT_ENTRIES,"color_map_stops":color_adjustments::MAX_MAP_STOPS}).as_object().unwrap().clone());
    limits.as_object_mut().unwrap().extend(json!({"filters_per_item":filters::MAX_STACK,"filters_per_document":filters::MAX_DOCUMENT_FILTERS,"filter_work":filters::MAX_WORK,"displacement_map_pixels":spatial_filters::MAX_MAP_PIXELS}).as_object().unwrap().clone());
    limits.as_object_mut().unwrap().extend(json!({"saved_channels":channels::MAX_CHANNELS,"channel_samples":channels::MAX_SAMPLES,"selection_targets":selection_analysis::MAX_TARGETS,"selection_edge_radius":selection_analysis::MAX_EDGE_RADIUS}).as_object().unwrap().clone());
    limits.as_object_mut().unwrap().extend(
        json!({"simplification_span":simplify::MAX_SPAN,"simplification_work":simplify::MAX_WORK})
            .as_object()
            .unwrap()
            .clone(),
    );
    limits.as_object_mut().unwrap().extend(json!({"boolean_inputs":booleans::MAX_INPUTS,"boolean_source_edges":booleans::MAX_EDGES,"boolean_flattened_edges":booleans::MAX_EDGES,"boolean_atomic_edges":booleans::MAX_ATOMS,"boolean_work":booleans::MAX_WORK}).as_object().unwrap().clone());
    let supported = json!({"vector":["rect","ellipse","rounded_rect","polygon","regular_polygon","star","path_conversion","anchor_handle_edits","exact_curve_split","contour_reverse","contour_join","certified_curve_simplification","polygon_boolean_operations","line","cubic","compound_path","solid_fill","linear_gradient","radial_gradient","freeform_gradient","editable_color_mesh","inline_pattern","certified_editable_vector_warps","editable_repeat_layouts","editable_object_interpolation","editable_vector_brush_patterns","editable_dash_patterns","dash_phase","variable_width_profiles","endpoint_arrowheads","stroke_expansion","gradient_stroke","centered_stroke","object_document_stroke_scaling","affine_transform"],"raster":["retained_pixel_deformation","canvas_crop","anchored_canvas_extent","editable_scene_scale","resolution_only_edit","layer_alpha_clipping","editable_tone_adjustments","editable_color_adjustments","clipped_adjustment_chains","composite_measurements","rgba8_inline_layers","pixel_replace_fill","affine_pixel_transforms","anchored_transforms","editable_fill_layers","affine_fill_layers","solid_gradient_pattern_fills","ordered_rgb_dither"],"shared":["shared_effect_lighting","effect_scaling","effect_contours","gradient_effect_colors","knockout_groups","content_fill_opacity","editable_layer_effects","seeded_dissolve","editable_artwork_masks","shared_nonprinting_mask_sources","pass_through_group_opacity_masks","nonprinting_work_paths","path_to_selection","path_to_vector_mask","saved_alpha_channels","named_ink_channels","channel_calculations","component_isolation","color_range_selection","connected_selection","image_guided_edge_refinement","editable_viewport_filters","groups","named_layers","geometric_clips","editable_grayscale_masks","mask_density_feather_invert_disable","linked_unlinked_masks","persistent_pixel_selections","selection_set_operations","selection_morphology","selection_to_mask","native_pixel_mask_application","alignment","distribution","explicit_id_selection","type_bounds_anchor_queries","placed_images","integer_pixel_crops","explicit_asset_relink","editable_text","character_style_ranges","paragraph_wrap","text_alignment","text_tracking","text_leading","text_ink_inspection","named_artboards","nested_frames","nonprinting_guides","guide_alignment","artboard_bleed","artboard_duplication","durable_sessions","grouped_undo_redo","named_snapshots","retry_receipts","cooperative_edit_cancellation"],"blend_modes":blending::MODES,"exports":["snapshot","apng_rgba8","ordered_png_sequence","svg_vector_normal_blend","png_rgba8","jpeg_explicit_matte","tiff_rgba8"],"paint_interpolation":["srgb","linear_rgb"],"gradient_alpha":"straight","freeform":"inverse_square_anchor_weights","pattern_sampling":"nearest_repeat","svg_paints":["solid","linear","radial","sampled_mesh"],"image_sampling":["nearest","bilinear_premultiplied_srgb","area_premultiplied_srgb","bicubic_premultiplied_srgb","lanczos3_premultiplied_srgb"],"imports":["png_8bit_normalized","jpeg_8bit_gray_rgb","tiff_8bit_gray_rgb_straight_alpha","svg_editable_geometry_gradients_clips","svg_editable_single_line_text","svg_editable_artwork_masks"],"asset_store":"sha256_rgba8_create_only","color":"encoded_srgb_rgba8","stack_order":"bottom_to_top_per_parent","text":{"scripts":["unicode_grapheme_script_runs"],"directions":["ltr","rtl","auto"],"auto_direction_requires":"bidi_unicode","bidi_modes":["single_run","unicode"],"alignment":["left","center","right","start","end"],"bidi":"explicit_single_run_or_unicode16_paragraphs", "bidi_inspection":"text.directions", "bidi_line_rules":"paragraph_resolution_then_L1_L2_then_shaper_L3_L4","fallback":"explicit_ordered_pinned_fonts_whole_run_then_grapheme","fallback_fonts":fonts::MAX_FALLBACK_FONTS,"language":"explicit_font_language_system_or_default","coverage":"shaped_glyphs_after_canonical_composition","shaping_context":"line_local_across_style_and_font_boundaries","fonts":"pinned_monochrome_sfnt_explicit_instances","font_variations":"per_font_axis_maps","axis_controls":fonts::MAX_AXES,"feature_controls":fonts::MAX_FEATURES,"feature_availability":"selected_font_tag_required_when_positive","tracking_liga":"explicit_feature_overrides_default_disable","font_inspection":"font.inspect","layout":"horizontal_unhinted_font_metrics_or_rigid_path_glyphs","glyph_compositing":"individual_ordered_paths","wrap":"ascii_space_or_grapheme","svg":"outlines","outline_conversion":"vector_documents"},"artboards":{"formats":["png","jpeg","tiff","svg_vector"],"selection":["all","ids","range_zero_based_end_exclusive"],"order":"hierarchy_preorder_sibling_stack","scope":"owned_subtree_local_coordinates","bleed":"integer_per_edge","frame_clipping":"always_on","background":"optional_solid_rgba"}});
    let commands = json!([
        "preset.list",
        "preset.create",
        "color.convert",
        "layered.import",
        "assist.segment",
        "assist.layout",
        "volume.inspect",
        "appearance.inspect",
        "sequence.import",
        "sequence.export",
        "handoff.export",
        "handoff.inspect",
        "sequence.inspect",
        "sequence.open",
        "swatch.inspect",
        "brush.inspect",
        "warp.inspect",
        "pixel_warp.inspect",
        "repeat.inspect",
        "interpolation.inspect",
        "image.trace",
        "mesh.inspect",
        "svg.import",
        "vector.import",
        "document.boolean",
        "channel.export",
        "document.diff",
        "document.diff.preview",
        "session.diff.preview",
        "document.publish",
        "publication.receipt",
        "job.start",
        "job.status",
        "job.list",
        "job.result",
        "job.wait",
        "job.cancel",
        "job.resume",
        "publication.recover",
        "session.diff",
        "session.publish",
        "capabilities",
        "schema",
        "schema.lookup",
        "implementation.status",
        "session.create",
        "session.read",
        "session.apply",
        "session.dry_run",
        "session.apply_proposal",
        "session.receipt",
        "session.history",
        "session.verify",
        "session.backup",
        "session.migrate",
        "session.continue",
        "session.recover",
        "artboard.export",
        "font.import",
        "font.verify",
        "font.inspect",
        "text.inspect",
        "text.directions",
        "text.hyphenate",
        "story.inspect",
        "object.import",
        "object.open",
        "object.status",
        "sample.import",
        "raw.develop",
        "raw.retain",
        "raw.reopen",
        "raw.recipe",
        "sample.measure",
        "asset.import",
        "asset.verify",
        "asset.embed",
        "document.create",
        "document.validate",
        "document.check",
        "document.preflight",
        "document.inspect",
        "document.inspect.page",
        "document.preview",
        "document.contact_sheet",
        "document.query",
        "document.measure",
        "document.select",
        "document.edit",
        "document.render",
        "document.proof",
        "document.prepress",
        "document.separations",
        "profile.gamut",
        "geometry.measure",
        "document.export"
    ]);
    let unsupported = json!([
        "vertical_script_layout",
        "color_fonts",
        "threaded_text",
        "columns",
        "automatic_hyphenation",
        "vertical_and_multicontour_path_text",
        "high_depth_filters",
        "non_rgb_pixel_working_profiles_use_explicit_device_paints_or_print_delivery",
        "image_non_rgb_profiles_and_hdr",
        "image_16bit",
        "animated_png",
        "image_exif",
        "ewa_and_arbitrary_reconstruction_kernels",
        "mask_application_to_text_and_containers",
        "pass_through_group_filters",
        "pass_through_non_normal_group_blend",
        "svg_freeform_and_inline_pattern_paints",
        "mesh_curved_outer_boundary_and_noncontractive_geometry",
        "svg_editable_mesh_import"
    ]);
    let mut svg_import_contract = json!({"source_bytes":svg_import::MAX_BYTES,"xml_nodes":svg_import::MAX_NODES,"elements":["svg","g","rect","ellipse","circle","line","polygon","polyline","path","title","desc","style","defs","linearGradient","radialGradient","stop","clipPath","text","mask","metadata"],"path_commands":"MmLlHhVvCcSsQqTtAaZz","paints":["solid_srgb_rgba8","linear","centered_radial"],"gradient_units":["userSpaceOnUse","objectBoundingBox"],"gradient_templates":"local_href_with_cycle_checks","template_stop_styles":"cloned_in_derived_gradient_context","clip_geometry":"single_shape_or_compound_path","definition_limit":svg_import::MAX_DEFINITIONS,"reference_depth":svg_import::MAX_REFERENCE_DEPTH,"resources":"local_definitions_and_explicit_pinned_fonts","text":{"kind":"editable_single_line_ltr","font_bindings":fonts::MAX_FONTS,"font_selection":"first_explicit_family_weight_style_match_no_glyph_fallback","anchors":["start","middle","end"],"baseline":"alphabetic","whitespace":"legacy_xml_space_or_explicit_css_normal_pre","object_box":"full_font_cells","span_children":false},"source_preserved":true,"unsupported_policy":"error_no_partial_document","viewport":"integral_pixels_at_96ppi_with_viewBox_meet_slice_none"});
    svg_import_contract["arcs"] = json!({"method":"adaptive_tangent_cubics_at_most_quarter_turns","max_radial_error_local":limits::svg_import::ARC_RADIAL_TOLERANCE,"max_normalized_radius":model::MAX_COORDINATE,"coordinate_space":"source_element_local_before_transforms","binary64_roundoff_included":false,"receipt":"approximations"});
    svg_import_contract["rounded_rectangles"] = json!(true);
    svg_import_contract["unsupported"] = json!({"field":"unsupported","default":"error",
        "options":["error","omit_and_report"],"receipt":"omissions",
        "scope":"located_unsupported_element_subtrees_and_known_omitted_dependencies",
        "source_locations":"original_utf8_byte_ranges_and_one_based_line_column",
        "root_omission":false,"invalid_xml_duplicate_ids_and_resource_failures":"error",
        "late_paint_and_mask_locations":true,
        "max_attempts":limits::svg_import::MAX_OMISSION_ATTEMPTS,
        "max_source_processing_bytes":limits::svg_import::MAX_OMISSION_SOURCE_BYTES});
    svg_import_contract["text"]["span_children"] = json!(true);
    svg_import_contract["text"]["kind"] =
        json!("editable_horizontal_ltr_ranges_and_character_positions");
    svg_import_contract["text"]["coordinates"] = json!(
        "x_y_dx_dy_scalar_or_bounded_lists;ancestor_entries_overridden_per_addressable_character"
    );
    svg_import_contract["text"]["spans"] = json!({"element":"tspan","scope":"descendants_of_text_or_tspan","styles":"inherited_font_fill_anchor_whitespace_visibility_and_embedded_cascade","positioning":"native_character_positions;absolute_chunks_and_cumulative_relative_shifts","mapping":"item_id_and_Unicode_scalar_text_range_at_imported_revision","object_box":"entire_text_font_cells_for_all_range_paints","dom_boundaries":"separate_initial_style_ranges;later_range_edits_normalize_ranges","unsupported":["span_transform","span_opacity_except_one","span_clip","span_mask","span_isolation","different_styles_or_absolute_positions_inside_grapheme","rotation","textLength","textPath"]});
    svg_import_contract["elements"]
        .as_array_mut()
        .unwrap()
        .extend([
            json!("use"),
            json!("symbol"),
            json!("image"),
            json!("tspan"),
        ]);
    svg_import_contract["resources"] =
        json!("local_definitions_explicit_pinned_fonts_and_embedded_image_sources");
    svg_import_contract["images"] = json!({"formats":["png","jpeg"],
        "sources":["data_uri_base64_or_percent_bytes","relative_file_under_explicit_images.source_root"],
        "remote_urls":false,"implicit_source_root":false,"file_writes":false,
        "storage":"encoded_source_base64_with_source_and_normalized_pixel_hashes",
        "default_color_policy":"assume_srgb","color_policies":["require_srgb","assume_srgb","convert_srgb"],
        "default_sampling":"bilinear","sampling":"existing_native_image_sampling",
        "image_rendering":{"auto":"images.sampling","pixelated":"nearest_with_declared_noninteger_scale_loss","inherited":true},
        "dimensions":"absolute_percentage_auto;intrinsic_pixels_when_omitted;missing_axis_uses_intrinsic_ratio",
        "aspect":"meet_slice_none_all_nine_alignments","overflow":["hidden","visible"],"default_overflow":"hidden",
        "object_box":"positioning_rectangle_including_letterboxing","zero_size":"nonpainting_group_with_hidden_intrinsic_image",
        "reuse":"shared_assets_and_compatible_native_components",
        "limits":"existing_source_snapshot_asset_count_and_aggregate_decoded_pixel_budgets",
        "mapping":["asset_id","image_item_id","viewport_item_id","image_size","empty_image"],
        "unsupported":["image_artwork_inside_mask_sources","svg_image_sources","animations","css_geometry_and_object_fit"]});
    svg_import_contract["reuse"] = json!({"references":"literal_local_href_or_xlink_href",
        "targets":["shapes","g","text","image","use","symbol","svg"],"output":"compatible_native_components;declared_context_variants_and_group_fallback",
        "styles":"source_declarations_with_placement_inheritance",
        "position":"transform_then_xy_translation_with_current_viewport_percentages",
        "nonviewport_dimensions":"validated_but_do_not_scale_shapes",
        "mapping":"original_locations;instance_path;component_path;reuse_receipts",
        "limits":"existing_reference_depth_expanded_items_and_hierarchy",
        "cycles":false,"external_references":false,"symbol":true,
        "cloned_resource_scopes":true,"component_sharing":true,
        "resource_references":"nearest_cloned_tree_then_enclosing_trees_then_original;inherited_URLs_keep_declaration_scope",
        "resource_contexts":"separate_gradient_clip_and_mask_definitions_per_use;existing_definition_limit_includes_clones",
        "resource_mapping":"original_source_id_and_offset;resource_scope;instance_path;mask_source_item_id",
        "component_overrides":["name","visible","opacity","fill_opacity","blend","transform","vector_style","nested_same_source_instance"],
        "component_variants":"other_resolved_context_differences_remain_separate_and_reported",
        "component_fallback":"expanded_groups_for_native_limits_or_raster_destinations",
        "shared_originals":"visible_originals_and_overlapping_reference_targets"});
    svg_import_contract["symbol_viewports"] = json!({
        "dimensions":"use_overrides_symbol_then_enclosing_user_viewport;absolute_percentage_auto",
        "viewBox":"positive_dimensions;meet_slice_none",
        "anchors":"refX_refY_numeric_percentage_and_axis_keywords;omission_distinct_from_zero",
        "overflow":["hidden","visible"],"overflow_scope":"symbol_and_nested_svg",
        "coordinates":"separate_viewport_clip_and_content_transform",
        "mapping":["viewport_item_id","viewport_size","instance_path"],
        "zero_size":"nonpainting_empty_group_with_declared_content_loss",
        "nested_svg":true});
    svg_import_contract["nested_viewports"] = json!({
        "dimensions":"explicit_use_override_then_svg_then_enclosing_user_viewport;absolute_percentage_auto",
        "position":"xy_absolute_or_percentage_of_enclosing_user_viewport;transform_outside_translation",
        "viewBox":"positive_dimensions;meet_slice_none;all_nine_alignments",
        "overflow":["hidden","visible"],"default_overflow":"hidden",
        "coordinates":"outer_viewport_clip;inner_viewBox_mapping_and_effects;nearest_viewport_percentages",
        "preserveAspectRatio_without_viewBox":"syntax_checked_no_geometric_effect",
        "version":"omitted_inherits_root;explicit_1.0_1.1_or_2.0_cannot_switch_root_text_mask_compatibility",
        "zero_size":"nonpainting_empty_group_with_declared_content_loss;descendants_still_validated",
        "mapping":["viewport_item_id","viewport_size","empty_viewport"],
        "limits":"existing_items_hierarchy_and_reference_budgets_include_generated_groups"});
    svg_import_contract["css"] = json!({"embedded_style":true,"inline_style":true,
        "selectors":["type","universal","class","id","compound","list"],
        "cascade":"presentation_attributes_then_specificity_source_order_then_inline",
        "important":false,"external_stylesheets":false,"at_rules":false,"escapes":false,
        "unknown_or_invalid_declarations":"error_even_if_unmatched_or_overridden",
        "source_location":"element_byte_offset_line_column_and_css_offset_when_available",
        "rules":limits::svg_import::MAX_CSS_RULES,"selectors_per_rule":limits::svg_import::MAX_CSS_RULES,
        "selector_components":limits::svg_import::MAX_CSS_SELECTOR_COMPONENTS,
        "declarations":limits::svg_import::MAX_CSS_DECLARATIONS,"match_work":limits::svg_import::MAX_CSS_MATCH_WORK});
    svg_import_contract["insertion"] = json!({"operation":"add_svg",
        "sources":["svg_fragment","svg_document"],"source_bytes":MAX_REQUEST_BYTES,
        "prefix_bytes":limits::transfer::MAX_PREFIX_BYTES,"placement":"parent_local",
        "fonts":"existing_destination_bindings","images":"same_images_options_and_atomic_encoded_asset_transfer","compositing":"destination_working_space",
        "full_document_viewport":"retained_as_outer_clip","fragment_viewport":"destination_logical_size_without_extra_clip",
        "ids":"deterministic_collision_checked_prefix","unsupported_policy":"error_atomic_batch"});
    svg_import_contract["insertion"]["unsupported"] = svg_import_contract["unsupported"].clone();
    let mut capabilities = json!({
        "name":"inkbolt","version":env!("CARGO_PKG_VERSION"),"stage":"editing_core",
        "document_schema_version":2,"readable_document_schema_versions":[1,2],
        "commands":commands,
        "document_kinds":["vector","raster"],
        "limits":limits,
        "features":{"empty_documents":true,"editing":true,"rendering":true,"atomic_snapshot_batches":true,"native_import":false,"png_import":true,"jpeg_import":true,"tiff_import":true,"content_addressed_assets":true,"editable_text":true,"pinned_local_fonts":true,"artboards":true,"nested_frames":true,"artboard_range_exports":true,"sessions":true,"persistent_undo":true,"mcp_stdio":true,"create_only_publication":true,"semantic_diffs":true},
        "supported":supported,
        "mcp":{"transport":"stdio","protocol_version":mcp::PROTOCOL,"message_bytes":mcp::MAX_MESSAGE_BYTES,"response_bytes":mcp::MAX_RESPONSE_BYTES,"pending_requests":mcp::MAX_PENDING,"request_ids_per_connection":mcp::MAX_REQUEST_IDS,"default_timeout_ms":control::MAX_TIMEOUT_MS},
        "layer_clipping":{"document_kind":"raster","binding":"contiguous_sibling_base_id","source_alpha":"preserves_base_alpha","base_effects":"once_after_clipped_members","source_effects":"before_alpha_preserving_blend","base_visibility":"suppresses_whole_clipping_group","pass_through_groups":"premultiplied_backdrop_difference_interpolation"},
        "masks":{"storage":"inline_gray8","outside":"clip_zero_or_unclipped_one_before_density","inversion":"source_grid_only","feather":"separable_triangular_mask_pixel_radius","sampling":["nearest","bilinear"],"linking":"item_local_or_document_coordinates","composition":"one_multiply_after_item_or_isolated_group","svg":"processed_grayscale8_png_field","selection_to_mask":true,"permanent_application":"native_pixel_layers_images_and_fills"},
        "adjustments":{"operators":["color","invert","threshold","levels","posterize","curve","exposure","brightness_contrast","shadows_highlights"],"scope":["current_backdrop","preceding_sibling_before_composite"],"alpha":"preserved","precision":"f64_then_final_rgba8","curve":"piecewise_linear_encoded_srgb","exposure":"linear_srgb","mask_and_clip":true,"clip_to":"stable_sibling_id_with_contiguous_chain"},
        "filters":{"operators":["creative","detail","spatial","box","gaussian","directional","radial","surface"],"domain":"render_viewport_after_geometry_before_item_effects","precision":"premultiplied_f64_encoded_srgb_to_requested_output_depth","radius_units":"document_pixels_scaled_by_export_scale","radial_center":"item_local","border":["transparent","clamp","reflect","wrap"],"stack_order":"first_to_last","masks":"shared_grayscale_controls","blend_modes":blending::MODES,"input_depth":8,"detail_operators":["sharpen","unsharp","median","noise"],"spatial_operators":["offset","displace","mosaic"],"noise_distribution":["uniform","gaussian"],"noise_seed":"u32_sha256_coordinate_v1","detail_alpha":"preserved","median_radius":[0,limits::detail_filters::MAX_MEDIAN_RADIUS],"sharpen_amount":[0,limits::detail_filters::MAX_SHARPEN_AMOUNT],"spatial_offset":[-i64::from(limits::spatial_filters::MAX_OFFSET),limits::spatial_filters::MAX_OFFSET],"mosaic_size":[1,limits::spatial_filters::MAX_MOSAIC_SIZE],"box_radius":[0,limits::filters::MAX_BOX_RADIUS],"gaussian_sigma":[0,limits::filters::MAX_GAUSSIAN_SIGMA],"surface_radius":[0,limits::filters::MAX_SURFACE_RADIUS],"directional_length":[0,limits::filters::MAX_DIRECTIONAL_LENGTH],"trajectory_samples_odd":[limits::filters::MIN_TRAJECTORY_SAMPLES,limits::filters::MAX_TRAJECTORY_SAMPLES],"svg":false},
        "color_adjustments":{"operators":["hue_saturation","desaturate","channel_mixer","balance","selective","lut1d","lut3d","gradient_map"],"working_space":"straight_encoded_srgb","clipping":"after_each_operator","lookup_domain":"per_channel_clamp","lookup_order":"red_fastest_green_then_blue","lookup_3d_interpolation":"trilinear","gradient_map_interpolation":["srgb","linear_rgb"],"alpha":"preserved","profile_conversion":false},
        "measurements":{"source":"scale_one_rgba8_composite","histogram_bins":256,"weight_denominator":65025,"selection":true,"alpha_policies":["ignore","exclude_transparent","weight"]},
        "work_paths":{"document_kinds":["vector","raster"],"printing":false,"coverage":"f64_monotone_cubic_roots_256_subrows_gray8","vector_mask_coverage":"tiny_skia_f32_gray8","selection":"copied_world_geometry","vector_mask":"independent_item_local_clip_copy","source_appearance":"ignored_including_ancestor_effects","compound_operations":"document.boolean_with_existing_curve_certificate_limits","snapshot_persistence":true},
        "paths":{"indexing":"revision_scoped_command_indices","split":"de_casteljau_exact_up_to_f64_roundoff","join":["exact_coincident","explicit_bridge"],"reverse":"selected_contours_preserve_closed_seam","simplify":true,"primitive_corners":"normalized_quarter_cubics","ellipse_conversion":"four_cubic_approximation"},
        "booleans":{"command":"document.boolean","modes":["union","intersection","difference","xor"],"output":"root_coordinate_nonzero_polygon_or_null","arithmetic":"exact_rational_arrangement_then_checked_f64_vertices","curve_model":"bounded_chords_with_exact_topology_certificate","curve_tolerance":[0,limits::booleans::MAX_CURVE_TOLERANCE],"default_curve_tolerance":limits::booleans::DEFAULT_CURVE_TOLERANCE,"curve_coincidence":"exact_noncollinear_polynomial_affine_parameter_normalization","curve_subdivision":"invariant_within_operand_for_exact_encoded_polynomials","curve_topology":"certified_simultaneous_deformation_or_explicit_failure","curve_contacts":"verified_rational_resultants_and_quadratic_parameter_nodes_with_rational_junctions","curve_contact_root_search_depth":limits::booleans_topology_algebraic_roots::MAX_ROOT_DEPTH,"curve_contact_polynomial_coefficient_bits":limits::booleans_topology_algebraic_roots::MAX_COEFFICIENT_BITS,"curve_quadratic_predicates":"exact_signs_across_two_real_quadratic_fields","curve_contacts_remaining":"non_rational_fixed_world_junctions_and_uncertified_deformations_remain_explicit_failures","analytic_ellipses":"explicit_path_conversion_required","source_mutation":false},
        "curve_simplification":{"space":["local","world"],"deviation":"exact_rational_bernstein_control_bound","topology":"monotone_swept_hulls_disjoint_except_fixed_shared_endpoints","scope":"compound_path_including_fill_closure","unproven_candidates":"retained_with_reasons","receipt":"per_reduction_exact_bound_and_parameter_map"},
        "channels":{"storage":"canvas_gray8","nonprinting":true,"roles":["alpha","spot"],"components":["red","green","blue","alpha","luma"],"calculations":["copy","add","subtract","difference","multiply","screen","minimum","maximum","average"],"spot_identity":"unique_ink_id_with_alternate_srgb_and_exact_tint_coverage","export":"gray_or_alternate_ink_preview_png_with_metadata"},
        "selection_analysis":{"source":"scale_one_rgba8_composite","distance":"maximum_absolute_component_difference","components":["rgb","rgba"],"methods":["color_range","connected","edge"],"connectivity":["four","eight"],"edge":"color_gated_triangular_integer_weights_then_levels"},
        "pixel_selection":{"coordinates":"document_grid","storage":"gray8","nonprinting":true,"combine":{"add":"maximum","subtract":"saturating_difference","intersect":"minimum"},"morphology":"square_max_min_zero_outside","feather":"separable_triangular_zero_outside","mask_application":"native_pixel_centers_then_rgba8_quantization"},
        "publication":{"output_bytes":publish::MAX_OUTPUT_BYTES,"overwrite":"never","root":"explicit_existing_local_directory","formats":["pdf","png","jpeg","tiff","svg","snapshot"]},
        "session_contract":{"storage_version":sessions::STORE_VERSION,"supported_storage_versions":sessions::SUPPORTED_STORE_VERSIONS,"backend":"sqlite_rollback_full_sync","parent_directory_aliases":true,"database_symlinks":false,"conflicts":"expected_revision","retry":"original_receipt_and_document","history":"immutable_states_no_eviction","resources":"external_explicit_roots","cancellation":"cooperative_precommit","export":"read_document_then_export_returned_snapshot"},
        "unsupported":unsupported,
    });
    capabilities["filters"].as_object_mut().unwrap().extend(json!({
        "trajectory_samples_default": limits::filters::DEFAULT_TRAJECTORY_SAMPLES,
        "directional_angle_degrees": [-i64::from(limits::filters::MAX_ANGLE_DEGREES), limits::filters::MAX_ANGLE_DEGREES],
        "radial_angle_degrees": [-i64::from(limits::filters::MAX_RADIAL_ANGLE), limits::filters::MAX_RADIAL_ANGLE],
        "displacement_map_dimension": [1, limits::spatial_filters::MAX_MAP_AXIS]
    }).as_object().unwrap().clone());
    capabilities["filters"]["creative_limits"] = json!({
        "angle_degrees": [-i64::from(limits::filters::MAX_ANGLE_DEGREES), limits::filters::MAX_ANGLE_DEGREES],
        "twist_radius": [limits::creative_filters::MIN_TWIST_RADIUS, model::MAX_COORDINATE],
        "relief_distance": [0, limits::creative_filters::MAX_RELIEF_DISTANCE],
        "relief_strength": [0, limits::creative_filters::MAX_RELIEF_STRENGTH],
        "high_pass_sigma": [0, limits::filters::MAX_GAUSSIAN_SIGMA],
        "extrema_radius": [0, limits::creative_filters::MAX_EXTREMA_RADIUS],
        "stroke_rank_radius": [0, limits::creative_filters::MAX_STROKE_RADIUS],
        "edge_ink_strength": [0, limits::creative_filters::MAX_EDGE_STRENGTH],
        "value_cell_size": [1, limits::creative_filters::MAX_CELL_SIZE],
        "value_octaves": [1, limits::creative_filters::MAX_OCTAVES]
    });
    capabilities["filters"].as_object_mut().unwrap().extend(json!({"creative_operators":["twist","relief","high_pass","extrema","tone_fold","edge_ink","stroke_rank","value_field","field_repair"],"creative_contract":"docs/CREATIVE_FILTERS.md","creative_alpha":"center_preserved_except_twist_and_field_repair","creative_coordinates":"item_local_twist_and_value_field;output_grid_field_repair;document_units_other_kernels"}).as_object().unwrap().clone());
    capabilities["ink_recipes"] = json!({"field":"ink_recipe","operation":"ink_recipe","inspect":"document.inspect","separations":"document.separations","source":"retained_canvas_gray8_channels","source_roles":"explicit_recipe_overrides_saved_channel_role_metadata","source_mask":"optional_independent_gray8_channel","inks":[1,ink_recipes::MAX_INKS],"curve_knots":[2,ink_recipes::MAX_KNOTS],"curve":"piecewise_linear_exact_binary64_rationals;nonmonotone_outputs_allowed","sample_projection":"curve(source/255)*mask_byte;nearest_u8_once_ties_up","scale":[1,limits::render_quality::MAX_SCALE],"resampling":"integer_nearest_replication","plates":"scalar_gray8_PNG_no_colour_profile_or_transfer_tag","preview":["declared_linear_rgb_corners","declared_transmittance_paper_and_ink_srgb"],"corner_precision":16,"corner_order":"first_ink_fastest;zero_is_paper","preview_work":ink_recipes::MAX_WORK,"preview_interpolation":"multilinear_linear_rgb_then_srgb_encoding","pdf":"pdf_options.ink_recipe;whole_canvas_DeviceN_image;exact_ink_amounts;calculator_linear_mix_to_srgb_ICC_alternate","pdf_colorant_identity":"Inkbolt.<ink_id>","source_mutation":false,"ordinary_artwork":"excluded_from_explicit_recipe_delivery;ordinary_render_ignores_nonprinting_recipe","persistence":"snapshot_atomic_edits_sessions_undo_redo","combined_process":"pdf_options.print.named_inks;explicit_multiplicative_cmyk_alternates;whole_canvas_NChannel","unsupported":["recipe_artboard_crops_and_bleed","physical_press_calibration","implicit_ink_merging","spectral_ink_models"]});
    capabilities["sample_profiles"] = json!({"operation":"sample_profile","actions":["assign","convert"],"source":"inline_rgba8_or_normalized_sample_grid","models":["rgb"],"depths":["u8","u16","f32"],"intents":["relative_colorimetric","absolute_colorimetric","perceptual","saturation"],"view_intent":"relative_colorimetric","profile_null":"explicit_working_srgb","source_encoding":"profiled_rgb","assignment":"native_values_unchanged","conversion":"native_rgb_rewritten;alpha_exact;gray_promoted_to_rgba_when_needed","linear_compositing":"source_profile_to_linear_srgb_before_reconstruction","black_point_compensation":false,"profile_encoded_bytes_per_document":sample_profiles::MAX_ENCODED_PROFILE_BYTES,"unknown_external_input":"existing_explicit_import_policy","unsupported":["signed_hdr_profile_assignment","non_rgb_icc_source_models","implicit_profile_discard"]});
    capabilities["work_paths"]["compound_operations"] = json!(
        "retained_union_intersection_difference_xor;membership_before_coverage;independent_source_copies"
    );
    capabilities["work_paths"]["compound"] = json!({"combine":"work_path_combine","edit":"path_component","geometry":"compound","max_leaves":work_paths::MAX_COMPONENTS,"max_depth":work_paths::MAX_COMPONENT_DEPTH,"operands_per_operation":[2,limits::work_paths::MAX_OPERANDS],"bounds":"union_of_operand_geometry_not_tight_filled_result","vector_mask_coverage":"shared_f64_region_scanlines_gray8","clip_pixel_limit":selections::MAX_PIXELS,"flattened_boolean":"separate_document.boolean_contract","unsupported":["painted_compound_vector_content","implicit_polygonal_expansion","direct_svg_pdf_active_compound_clips"]});
    capabilities["sample_profiles"]["builtin_definition_revision"] =
        json!("0.73_D50_media_white_Bradford_D65_to_D50");
    capabilities["sample_profiles"]["precision"] = json!(
        "bounded_normalized_curve_tables_then_signed_linear_matrix;nonlinear_destination_clips_before_inverse_transfer"
    );
    capabilities["vector_strokes"] = json!({"caps":["butt","round","square"],"joins":["miter","round","bevel"],"miter_limit":[limits::strokes::MIN_MITER_LIMIT,limits::strokes::MAX_MITER_LIMIT],"width":[limits::strokes::MIN_WIDTH,limits::strokes::MAX_WIDTH],"dash_intervals":strokes::MAX_INTERVALS,"dash_interval":format!("zero_or_{}_to_{}",limits::strokes::MIN_DASH_LENGTH,model::MAX_COORDINATE),"dash_offset":[-(model::MAX_COORDINATE as i64),model::MAX_COORDINATE as i64],"scaling":["object","document"],"default_scaling":"object","dash_units":"declared_stroke_space","document_scaling":"world_centerline_then_outline_in_logical_units","paint_coordinates":"item_local","mask_instances":"per_reference_world_placement","artboard_coordinates":"independent_export_viewport","odd_dash_list":"repeat_twice","empty_or_all_zero":"solid","phase_reset":"each_subpath","dash_document_work":strokes::MAX_DOCUMENT_WORK,"dash_instance_work":strokes::MAX_INSTANCE_WORK,"dash_range_work":strokes::MAX_RANGE_WORK,"curve_dashing":"original_f64_flattened_arclength","curve_tolerance":{"default":strokes::default_tolerance(),"range":[limits::strokes::MIN_CURVE_TOLERANCE,limits::strokes::MAX_CURVE_TOLERANCE],"units":"declared_stroke_space","automatic_refinement":format!("min_saved_and_1_over_{}_divided_by_max_1_and_{}_times_world_stretch_bound",1.0 / limits::strokes::DEFAULT_CURVE_TOLERANCE,strokes::OUTLINE_RESOLUTION),"outline_resolution":strokes::OUTLINE_RESOLUTION,"shared_outline":"current_placement_across_render_expansion_and_outlined_exports","stored_controls_preserved":true,"error_scope":"centerline_chord_length_and_round_sector_subdivision_not_global_offset_topology_or_raster"},"variable_width":true,"width_profile":{"knots":[2,limits::strokes::MAX_PROFILE_KNOTS],"form":"normalized_contour_distance_and_width_factor","factor":[0,limits::strokes::MAX_PROFILE_FACTOR],"maximum_resulting_width":limits::strokes::MAX_WIDTH,"closed_endpoints":"equal_factors","dash_reset":false},"arrowheads":true,"arrow_shapes":["triangle","chevron","diamond","ellipse","bar"],"arrow_length_width":[limits::strokes::MIN_ARROW_EXTENT,limits::strokes::MAX_ARROW_EXTENT],"arrow_placement":"each_contour_endpoint_original_tangent","arrow_attachment":"half_length_shaft_trim_with_butt_cut","editable_expansion":true,"expansion_operation":"stroke_expand","expansion_future_scaling":"filled_geometry_follows_object","document_scaled_definition_expansion":"unsupported_unlink_placement_first","expansion":"isolated_group_with_preserved_centerline_and_nonzero_outline","generated_document_commands":strokes::MAX_OUTLINE_COMMANDS,"generated_scan_work":render::MAX_RENDER_WORK,"svg_outline_commands":strokes::MAX_SVG_COMMANDS,"svg_range_outline_commands":strokes::MAX_SVG_RANGE_COMMANDS,"svg_advanced_controls":"filled_outlines_with_explicit_editability_loss"});
    capabilities["supported"]["exports"]
        .as_array_mut()
        .unwrap()
        .push(json!("pdf_native_paths_and_pages"));
    capabilities["supported"]["text"]["pdf"] = json!("outlines");
    capabilities["pdf"] = json!({"version":"1.7;2.0_for_managed_colour_or_calibrated_page","format":"pdf","page_selection":"pdf_options.artboards_all_ids_or_range;omitted_canvas","scale":1,"physical_units":"72_points_per_inch_from_document_resolution","boxes":["MediaBox","CropBox","BleedBox","TrimBox"],"bleed":"pdf_options.include_bleed_requires_artboards","coordinates":"bottom_left_pdf_user_units","user_unit":format!("ceil_largest_physical_dimension_divided_by_{}_minimum_1", limits::pdf::MAX_PAGE_COORDINATE),"maximum_user_unit":limits::pdf::MAX_USER_UNIT,"maximum_page_coordinate":limits::pdf::MAX_PAGE_COORDINATE,"pages":boards::MAX_ARTBOARDS,"path_commands":pdf::MAX_COMMANDS,"objects":pdf::MAX_OBJECTS,"image_pixels":pdf::MAX_IMAGE_PIXELS,"output_bytes":publish::MAX_OUTPUT_BYTES,"text":"outlined_variable_and_shaped_glyphs_no_font_embedding_or_search","color":"pdf_options.color:display_DeviceRGB_or_native_inks_DeviceCMYK_blending","paints":["solid","axial_pad_srgb_constant_alpha","radial_pad_srgb_constant_alpha"],"images":"verified_crops_nearest_rgb_with_gray8_soft_mask","groups":"normal_isolated_or_pass_through_no_knockout","clips":"geometric_and_frame","strokes":"shared_generated_outlines","metadata":"selected_page_public_or_strip_packets_in_RDF_XML","output_profile":"explicit_RGB_ICCBased_page_and_isolated_groups;DefaultRGB_srgb;PDF2_BPC_OFF","unsupported":["non_normal_blends","knockout","effects","filters","dissolve","pixel_warps","layer_clipping","active_opacity_and_artwork_masks","adjustments","dither","other_gradient_semantics","non_nearest_images","editable_reimport","encapsulated_pages"],"publication":"create_only_after_complete_export"});
    capabilities["image_io"] = json!({"formats":["png","jpeg","tiff"],"jpeg":{"import":"8bit_gray_rgb_baseline_progressive","quality":[limits::image_io::MIN_JPEG_QUALITY,limits::image_io::MAX_JPEG_QUALITY],"default_quality":limits::image_io::DEFAULT_JPEG_QUALITY,"chroma":["full","half"],"default_chroma":"full","alpha":"explicit_rgb_matte_required_when_transparent","density":"rounded_whole_ppi","lossless":false},"tiff":{"samples":"unsigned8_gray_grayalpha_rgb_rgba","alpha":"explicit_unassociated","white_is_zero":"gray_without_alpha","import_compression":["none","lzw","deflate","packbits"],"export_compression":["none","lzw","deflate"],"default_compression":"deflate","byte_orders":["little","big"],"bigtiff_import":true,"storage":["strips","tiles","chunky","planar"],"orientation":"top_left_only","pages":1,"density":"rounded_0.001_ppi","lossless":true},"jpeg_tiff_color":"explicit_input_policy_and_optional_profiled_output","profiles":true,"source_preserved":true,"output_settings_in_receipts":true});
    capabilities["pixel_warps"] = json!({"field":"item.pixel_warp","targets":["inline_raster","placed_image_crop"],"maps":["perspective","mesh","articulated"],"source":"retained_original_pixels_and_asset_identity","coordinates":"image_local_before_item_and_ancestors","mesh":"regular_source_grid_piecewise_affine","diagonal":"top_left_bottom_right","axis_intervals":[1,pixel_warps::MAX_AXIS],"joints":[1,pixel_warps::MAX_JOINTS],"joint_pose":"parent_times_pivot_rotation_translation","weights":format!("per_vertex_normalized_sum_one_within_{:e}", limits::pixel_warps::WEIGHT_SUM_TOLERANCE),"inverse":"unique_simple_consistently_oriented_triangulated_disk","folds":false,"reflection":true,"minimum_altitude":limits::pixel_warps::MIN_ALTITUDE,"minimum_relative_twice_area":limits::pixel_warps::MIN_RELATIVE_AREA,"sampling":["nearest","bilinear_premultiplied_srgb"],"coverage":"whole_boundary_once_no_triangle_alpha_seams","outside":"transparent_nearest_boundary_color_for_antialias","perspective_edge_color":"projective_inverse_of_nearest_destination_boundary_point","inspect":"pixel_warp.inspect","edit":"pixel_warp","clear":"warp_null","sample_limit":pixel_warps::MAX_SAMPLES,"render_work":pixel_warps::MAX_WORK,"stored_controls":model::MAX_SEGMENTS,"svg":"explicitly_unsupported_use_pixel_exports_and_snapshot","native_grid_edits":"clear_controls_first_for_brush_retouch_repair_mask_bake","unsupported":["folded_overlapping_meshes","singular_or_ill_conditioned_triangles","advanced_reconstruction_kernels","nonimage_content"]});
    capabilities["warps"] = json!({"content":"warp","maps":["affine","perspective","envelope"],"order":"source_then_ordered_maps_then_item_and_ancestors","nesting":"exact_homogeneous_bernstein_composition","perspective":"convex_quad_exact_projective_map","perspective_weights":[1.0 / limits::warps::MAX_PERSPECTIVE_WEIGHT as f64,limits::warps::MAX_PERSPECTIVE_WEIGHT],"envelope":"row_major_4_by_4_absolute_bicubic_controls","domain":"positive_control_hull_contained_no_extrapolation","appearance":"paint_and_stroke_after_geometry_deformation","fill":"explicit_closed_contours","open_centerlines":"fill_null","certificate":"exact_rational_homogeneous_bernstein_vs_encoded_parameter_chord","tolerance":[limits::warps::MIN_TOLERANCE,limits::warps::MAX_TOLERANCE],"default_tolerance":limits::warps::DEFAULT_TOLERANCE,"tolerance_units":"warp_local","source_interpretation":"ordinary_line_cubic_primitive_expansion","map_count":[1,warps::MAX_MAPS],"source_edges":warps::MAX_INPUT_EDGES,"maximum_degree":warps::MAX_DEGREE,"rational_bits":warps::MAX_BITS,"subdivision_depth":warps::MAX_DEPTH,"arithmetic_work":warps::MAX_WORK,"generated_commands":model::MAX_SEGMENTS,"samples":warps::MAX_SAMPLES,"grid_intervals":[1,limits::warps::MAX_GRID_AXIS],"grid":"reusable_open_path_with_segment_certificates","inspect":"warp.inspect","edit":"warp","expansion":"warp_expand_ordinary_vector","bounds":"expanded_geometry_excluding_stroke_and_clipping","svg":"ordinary_path_with_explicit_editability_loss","unsupported":["pixel_warps","arbitrary_hierarchy_envelopes","implicit_open_fill_closure","out_of_domain_hulls","inverse_or_topology_guarantees"]});
    capabilities["repeats"] = json!({"content":"repeat","layouts":["grid","brick","hex","radial"],"mirror":["none","columns","rows","both"],"copies":[1,repeats::MAX_COPIES],"motifs":"closed_line_cubic_and_expanded_primitives","paint_coordinates":"repeat_local_global_field","coverage":"combined_fill_once","winding":"reflections_preserve_authored_winding","seams":"coincident_edges_share_coverage_no_automatic_boundary_synthesis","brick_axis":["rows","columns"],"brick_offset":[0,1],"hex_orientation":["pointy","flat"],"radial_orientation":["fixed","radial","tangent"],"closed_radial":"full_signed_turn_terminal_copy_excluded","open_radial":"signed_subturn_both_endpoints_included","transforms":["motif_relative_to_anchor","whole_layout","item_and_ancestors"],"bounds":"geometry_excluding_effects_and_clipping","inspect":"repeat.inspect","edit":"repeat","expansion":"repeat_expand_compound_vector","svg":"compound_path_with_explicit_editability_loss","generated_commands":model::MAX_SEGMENTS,"unsupported":["open_motifs","per_copy_paint_restart","arbitrary_multicolor_hierarchy_motif"]});
    capabilities["interpolation"] = json!({"content":"interpolation","count":[2,interpolation::MAX_COUNT],"count_includes_endpoints":true,"endpoints":"vector_geometry_solid_fill_matching_stroke_controls","colors":"premultiplied_then_single_rgba8_encoding","spaces":["srgb","linear_rgb"],"correspondence":"uniform_authored_segment_fractions_exact_cubic_subdivision","unmatched_contours":"control_hull_center_collapse_or_grow","seam":"explicit_destination_segment_offset","anchors":"explicit_or_analytic_geometry_center","placement":["straight","one_contour_line_cubic_spine"],"orientation":["fixed","tangent"],"reversal":["endpoint_order","spine_traversal"],"spine_tolerance":[limits::path_text::MIN_TOLERANCE,limits::path_text::MAX_TOLERANCE],"spine_leaves":path_text::MAX_LEAVES,"document_spine_leaves":interpolation::MAX_DOCUMENT_SPINE_LEAVES,"closed_spine":"both_endpoints_included_explicit_subspan_available","expansion":"interpolation_expand_isolated_group","inspect":"interpolation.inspect","bounds":"unclipped_geometry_excluding_stroke","svg":"ordinary_paths_with_explicit_editability_loss","unsupported":["arbitrary_layer_endpoints","non_solid_endpoint_paints","differing_stroke_controls","direct_open_closed_pair","undefined_spine_tangent"]});
    capabilities["vector_brushes"] = json!({"field":"stroke.brush","model":"rigid_filled_motifs_on_evaluated_centerline","motif_geometry":"closed_line_cubic_and_expanded_primitives","motif_coordinates":[-(limits::strokes_brush::MAX_MOTIF_COORDINATE as i64),limits::strokes_brush::MAX_MOTIF_COORDINATE as i64],"fill_rule":"combined_nonzero_paint_once","spacing":[limits::strokes_brush::MIN_SPACING,limits::strokes_brush::MAX_SPACING],"phase":[-(model::MAX_COORDINATE as i64),model::MAX_COORDINATE as i64],"units":"base_stroke_width","fit":["fixed","uniform"],"profile":"whole_contour_uniform_motif_scale","corners":["bisector","incoming","outgoing"],"corner_angle":[limits::strokes_brush::MIN_CORNER_ANGLE,limits::strokes_brush::MAX_CORNER_ANGLE],"clearance":[0,limits::strokes_brush::MAX_CLEARANCE],"corner_sites":"original_command_anchors_evaluated_adjacent_tangents","closed_distance":"cyclic","endpoints":"open_contours_only_forward_tangent","scaling":["object","document"],"expansion":"stroke_expand","svg":"filled_outlines_with_editability_loss","inspect":"document.inspect_saved_controls","distance_precision":format!("{}_epsilon_times_point_count_times_length_plus_sum_max_abs_evaluated_coordinates", limits::strokes_brush::ROUNDING_EPSILONS),"ambiguous_intervals":"unsupported_above_quarter_step","maximum_conservative_placements":strokes::MAX_BRUSH_PLACEMENTS,"work":"combined_stroke_placement_commands_and_corner_comparisons","unsupported":["warped_motifs","dash_or_arrow_combinations","nondefault_cap_join_miter"]});
    capabilities["repair"] = json!({"operation":"repair","actions":["patch","fill","move","edge_correct"],"coordinates":"native_pixel_grids","sources":"explicit_frozen_inline_pixels","patch_search":"exhaustive_integer_translation;context_rms_then_requested_distance_then_row_major","fill_search":"exhaustive_complete_valid_donor_patches;source_row_major_ties","fill_priority":"most_known_context_cells_then_target_row_major","fill_patch_radius":[1,limits::repair::MAX_FILL_PATCH_RADIUS],"self_donors":"exclude_entire_positive_domain","move":"synthesize_source_then_copy_frozen_original_to_integer_offset","edge_correction":"guided_per_channel_weighted_median","guide_radius":[1,limits::repair::MAX_GUIDE_RADIUS],"quality":["required_context_rms","required_final_change_rms","minimum_effective_guide_support","optional_final_boundary_rms"],"quality_failure":"atomic_REPAIR_QUALITY","maximum_patches":repair::MAX_PATCHES,"work":repair::MAX_WORK,"automatic_semantic_reconstruction":false});
    capabilities["repair"].as_object_mut().unwrap().extend(
        json!({
            "patch_search_radius": [0, limits::repair::MAX_SEARCH_RADIUS],
            "patch_context_radius": [1, limits::repair::MAX_CONTEXT_RADIUS],
            "patch_source_origin": [0, model::MAX_COORDINATE],
            "synthesized_weight": [limits::repair::MIN_SYNTHESIZED_WEIGHT, 1],
            "default_synthesized_weight": limits::repair::DEFAULT_SYNTHESIZED_WEIGHT,
            "guide_range_sigma": [limits::repair::MIN_RANGE_SIGMA, 1],
            "guide_minimum_effective_samples": [1, limits::repair::MAX_EFFECTIVE_SAMPLES]
        })
        .as_object()
        .unwrap()
        .clone(),
    );
    capabilities["retouch"] = json!({"operation":"retouch","modes":["clone","heal"],"target_source":["raster","samples","stored_samples"],"encodings":["encoded_srgb"],"depths":["u8","u16","f32"],"channels":["rgba","gray_alpha"],"maximum_region_pixels":sample_store::MAX_REGION_PIXELS,"maximum_processing_memory_bytes":retouch::MAX_MEMORY_BYTES,"stored_edits":"versioned_legacy_patches_or_block_manifests;pure_preparation;explicit_block_commit;full_dependency_verification","sampling":["nearest","bilinear_premultiplied_srgb"],"borders":["error","transparent","clamp"],"source_transform":"target_native_to_source_native_affine","source_state":"frozen_before_operation","region":"native_integer_rectangle_with_optional_gray8","selection":"optional_world_mapped_native_centers","healing":"four_neighbor_boundary_constrained_source_correction","screening":[0,limits::retouch::MAX_SCREENING],"residual_tolerance":[limits::retouch::MIN_RESIDUAL_TOLERANCE,limits::retouch::MAX_RESIDUAL_TOLERANCE],"maximum_iterations_per_channel":retouch::MAX_ITERATIONS,"work":retouch::MAX_WORK,"output":"masked_premultiplied_replacement_once_at_target_native_depth","gray_policy":"reject_chromatic_results_without_implicit_conversion","measurements":["source_target_result_hashes","domain_bounds_components_perimeter","changed_pixels_bounds","boundary_rms","solver_residuals_iterations","clamped_pixels"],"automatic_donor_selection":false});
    capabilities["retouch"].as_object_mut().unwrap().extend(
        json!({
            "default_residual_tolerance": limits::retouch::DEFAULT_RESIDUAL_TOLERANCE,
            "default_iterations_per_channel": limits::retouch::DEFAULT_ITERATIONS
        })
        .as_object()
        .unwrap()
        .clone(),
    );
    capabilities["pixel_brushes"] = json!({"operation":"brush_stroke","inspect":"brush.inspect","target":["raster","samples","stored_samples"],"encodings":["encoded_srgb"],"depths":["u8","u16","f32"],"channels":["rgba","gray_alpha"],"maximum_window_pixels":sample_store::MAX_REGION_PIXELS,"maximum_processing_memory_bytes":pixel_brush::MAX_MEMORY_BYTES,"stored_edits":"versioned_legacy_patches_or_block_manifests;pure_preparation;explicit_block_commit;full_dependency_verification","gray_policy":"reject_chromatic_results_without_implicit_conversion","modes":["paint","erase","smudge","mixer"],"diameter":[limits::pixel_brush::MIN_DIAMETER,limits::pixel_brush::MAX_DIAMETER],"hardness":"unit_inner_radius;quadratic_radial_falloff","spacing":format!("{}_to_{}_times_base_diameter",limits::pixel_brush::MIN_SPACING,limits::pixel_brush::MAX_SPACING),"point_dynamics":["size","opacity"],"flow":"per_dab","opacity":"whole_stroke_premultiplied_interpolation","scatter":format!("seeded_uniform_square;0_to_{}_radii",limits::pixel_brush::MAX_SCATTER),"texture":"native_center_sampled_repeating_gray8","selection":"optional_world_mapped_native_centers","smudge":"pre_dab_surface_bilinear_translation","mixer":"premultiplied_coverage_weighted_pickup_and_explicit_load","coverage":"analytic_circle_cell_area_and_adaptive_squared_radius_integration","coverage_numeric_tolerance":pixel_brush::COVERAGE_TOLERANCE,"points":pixel_brush::MAX_POINTS,"dabs":pixel_brush::MAX_DABS,"work":pixel_brush::MAX_WORK,"texture_pixels":pixel_brush::MAX_TEXTURE_PIXELS,"quantization":"once_per_stroke_at_target_native_depth","source_retention":"snapshot_edits_and_session_undo","hardware":false});
    capabilities["pixel_brushes"].as_object_mut().unwrap().extend(json!({
        "spacing_range": [limits::pixel_brush::MIN_SPACING, limits::pixel_brush::MAX_SPACING],
        "default_spacing": limits::pixel_brush::DEFAULT_SPACING,
        "scatter_range": [0, limits::pixel_brush::MAX_SCATTER],
        "texture_scale": [limits::pixel_brush::MIN_TEXTURE_SCALE, limits::pixel_brush::MAX_TEXTURE_SCALE],
        "coverage_max_depth": limits::pixel_brush::MAX_COVERAGE_DEPTH
    }).as_object().unwrap().clone());
    capabilities["image_tracing"] = json!({"command":"image.trace","source":["rgba8_pixels","verified_image_asset"],"modes":["binary_alpha_or_encoded_luma","exact","quantized","explicit_palette"],"geometry":"exact_classified_unit_cell_boundaries","foreground_connectivity":4,"background_connectivity":8,"corners":"all_noncollinear_preserved","noise":["minimum_color_component_area","maximum_uniform_surround_transparent_hole_area"],"source_pixels":tracing::MAX_PIXELS,"result_colors":tracing::MAX_COLORS,"unit_edges":tracing::MAX_EDGES,"output_commands":model::MAX_SEGMENTS,"provenance":"normalized_options_and_input_output_grid_hashes_in_receipt_and_document_metadata","editable_output":"ordinary_nonzero_filled_paths","source_preserved":true,"cooperative_cancellation":true,"smooth_curve_fitting":false});
    capabilities["path_text"] = json!({"frame_field":"path","document_kinds":["vector","raster"],"geometry":"one_contiguous_line_cubic_or_expanded_primitive_contour","placement":"rigid_shaped_glyph_midpoint_tangent","edit":"text_and_text_range","offsets":["start_offset","normal_offset"],"flip":"reverse_traversal_without_reflection","closed":"one_finite_lap","overflow":["error","midpoint_clip","visible_endpoint_tangent_extension"],"inspection":"text.inspect_baseline_path_and_glyph_path","nominal_frame":"retained_for_alignment_not_path_clipping","distance_table":"adaptive_length_gap_and_uniform_parameter_deviation","tolerance":[limits::path_text::MIN_TOLERANCE,limits::path_text::MAX_TOLERANCE],"default_tolerance":limits::path_text::DEFAULT_TOLERANCE,"max_commands":path_text::MAX_COMMANDS,"max_leaves":path_text::MAX_LEAVES,"max_document_leaves":path_text::MAX_DOCUMENT_LEAVES,"svg":"placed_outlines_with_text_paths_receipts","editable_interchange":"snapshot","source_fonts":"existing_explicit_pinned_font_contract","multiline":false,"native_svg_text_path_import":false});
    capabilities["meshes"] = json!({"paint":"mesh","edit":"mesh_knot","inspect":"mesh.inspect","grid":"row_major_shared_bicubic_knots","axis_range":[2,meshes::MAX_AXIS],"domain":"fixed_rectangle_with_zero_boundary_offsets","outside":"transparent","geometry":"normalized_displacement_contraction","max_contraction":meshes::MAX_CONTRACTION,"inverse_steps":meshes::INVERSE_STEPS,"continuity":"C1_in_declared_interpolation_space_up_to_f64_roundoff","color_bounds":"shared_derivative_limiter","alpha":"straight_linear","inspection_samples":meshes::MAX_SAMPLES,"svg":"sampled_png_paint_with_explicit_interior_error_bounds","svg_samples_per_cell":[1,limits::meshes::MAX_SVG_SAMPLES_PER_CELL],"svg_default_samples_per_cell":limits::meshes::DEFAULT_SVG_SAMPLES_PER_CELL,"max_texture_pixels":meshes::MAX_TEXTURE_PIXELS,"max_svg_texture_pixels":meshes::MAX_SVG_TEXTURE_PIXELS,"editable_interchange":"snapshot","curved_outer_boundary":false,"folds":false});
    capabilities["metadata"] = json!({"records":"document_and_item","operation":"metadata","public_fields":["title","description","author","rights","note","tags","properties"],"private_fields":"private_map_saved_in_source_snapshots_only","export_policy":["public","strip"],"default_delivery":"public","default_snapshot":"source","record_bytes":metadata::MAX_RECORD_BYTES,"document_bytes":metadata::MAX_DOCUMENT_BYTES,"envelope_bytes":metadata::MAX_PACKET_BYTES,"formats":["snapshot","png_itxt","jpeg_numbered_comments","tiff_description","svg_namespaced_root","pdf_selected_pages_rdf_xml"],"resource_manifest":"content_and_license_hashes_without_runtime_paths","provenance":"deterministic_canonical_sanitized_snapshot_sha256","source_metadata_trust":"untrusted_description_not_authentication","orientation":"top_left_only_unsupported_input_orientation_rejected","resolution":"document_ppi_times_scale_with_format_rounding","profiles":"existing_explicit_color_contract_preserved","privacy_scope":"descriptive_records_not_artwork_text_names_or_profile_contents"});
    capabilities["color_profiles"] = json!({"working":"encoded_srgb_rgba8","output_association":"output_profile","edit":"output_profile","input_policy":"convert_srgb","explicit_input":"input_profile","builtins":["srgb","linear_srgb","display_p3"],"icc_versions":[2,4],"samples":"rgb8","connection_spaces":["xyz","lab"],"intent":"relative_colorimetric","black_point_compensation":false,"cicp_override":false,"profile_bytes":profiles::MAX_PROFILE_BYTES,"profile_tags":profiles::MAX_PROFILE_TAGS,"transform_stack_bytes":profiles::TRANSFORM_STACK_BYTES,"precision":"scalar_float_api_finite_resolution_tables_then_one_rgb8_round","alpha":"unchanged","embedding":["png","jpeg","tiff","calibrated_vector_pdf"],"jpeg_matte":"working_srgb_before_conversion","builtin_date":"2000-01-01T00:00:00","source_profile_bytes":"preserved_exactly","svg_profiled_output":false,"preview":"working_srgb"});
    capabilities["document_transfer"] = json!({"operation":"transfer","document_kinds":["vector","raster"],"source":"immutable_snapshot","selection":"subtrees_with_ancestor_context_and_transitive_references","prefix_characters":[1,limits::transfer::MAX_PREFIX_BYTES],"item_id_bytes":limits::model::MAX_ID_BYTES,"item_identity":"explicit_map_prefix_or_sha256_suffix","collisions":"atomic_error_never_replace","names":"duplicates_preserved","placement":"preserve_world_under_optional_destination_parent","resources":"referenced_descriptors_only_external_bytes_unchanged","verify_resources":"optional_destination_root_checks","source_variants":"selected_values_copied_definitions_omitted","global_lighting":"source_directions_pinned_locally","persistence":true});
    capabilities["variants"] = json!({"document_kinds":["vector","raster"],"operations":["variants_set","variant_select","variants_clear"],"properties":["name","visible","opacity","fill_opacity","position","transform","text","image"],"max_bindings":variants::MAX_BINDINGS,"max_datasets":variants::MAX_DATASETS,"max_inheritance":variants::MAX_INHERITANCE,"data":"typed_keyed_values","selection":"captured_base_then_inherited_property_subsets","text_ranges":true,"image_values":"explicit_pinned_asset_ids","inactive_resources":"retained_validated_and_lock_checked","unrelated_edits":"preserved","direct_controlled_edits":"explicit_error","clear_modes":["restore_base","bake_current"],"persistent":true,"exports":"selected_row_with_state_hash_and_explicit_metadata_loss"});
    capabilities["components"] = json!({"document_kinds":["vector"],"source":"top_level_nonprinting_component_source","placement":"isolated_instance","max_definitions":instances::MAX_DEFINITIONS,"max_nesting":instances::MAX_NESTING,"max_evaluated_items":model::MAX_ITEMS,"overrides":["name","visible","opacity","fill_opacity","blend","transform","content","vector_style"],"operations":["instance","instance_unlink"],"shared_edits":true,"local_overrides":true,"replacement":true,"unlink":true,"persistent":true,"dependency_locks":true,"unlinked_definition_masks":"per_instance_definition_space","svg":"expanded_independent_groups_with_editability_loss","artboards_in_definitions":false,"svg_use_import":false});
    capabilities["layer_effects"] = json!({"operators":["shadow","lit_shadow","stroke","overlay"],"global_light":true,"local_light_override":true,"effect_scale":[limits::effects::MIN_SCALE,limits::effects::MAX_SCALE],"effective_kernel_limits_preserved":true,"contour":format!("piecewise_linear_2_to_{}_knots_origin_zero",limits::effects::MAX_CONTOUR_KNOTS),"colors":"shared_solid_linear_radial_freeform_pattern_paints","color_coordinates":"item_local_follow_world_transform_independent_of_effect_scale","max_per_item":effects::MAX_STACK,"max_per_document":effects::MAX_DOCUMENT_EFFECTS,"max_work":effects::MAX_WORK,"domain":"viewport_after_filters_and_clipped_members","fill":"content_only_effect_source_alpha_unchanged","order":["shadows","content_and_overlays","strokes","item_masks_opacity_coverage_blend"],"units":"document_pixels_scaled_by_export_scale","stroke_radius":[0,limits::effects::MAX_STROKE_RADIUS],"stroke_positions":["outside","inside","center"],"stroke_metric":"euclidean_integer_disk","shadow_sigma":[0,limits::effects::MAX_SHADOW_SIGMA],"shadow_offset":[-i64::from(limits::effects::MAX_SHADOW_OFFSET),limits::effects::MAX_SHADOW_OFFSET],"source_mutation":false,"svg":false});
    capabilities["layer_effects"].as_object_mut().unwrap().extend(json!({
        "light_azimuth": [-i64::from(limits::effects::MAX_LIGHT_AZIMUTH), limits::effects::MAX_LIGHT_AZIMUTH],
        "default_light_azimuth": limits::effects::DEFAULT_LIGHT_AZIMUTH,
        "shadow_distance": [0, limits::effects::MAX_SHADOW_OFFSET],
        "contour_knots": [2, limits::effects::MAX_CONTOUR_KNOTS]
    }).as_object().unwrap().clone());
    capabilities["coverage"] = json!({"modes":["smooth","dissolve"],"seed":"u32","hash":"sha256_item_local_unit_cell_v1","threshold":"midpoint_first_little_endian_u32","domain":"after_fill_effects_masks_and_opacity","export_scale":"same_local_unit_cells","non_drawables":false});
    capabilities["blending"] = json!({"working_space":"straight_encoded_srgb","compositing":"premultiplied_f64_source_over","families":26,"nonseparable_luminance":[0.3,0.59,0.11],"comparison_tie_epsilons":limits::blending::COMPARISON_TIE_EPSILONS,"fill_opacity":true,"knockout":true,"knockout_shape":"intrinsic_alpha_before_fill_and_opacity","knockout_nested_groups":true,"knockout_mask_sources":false,"knockout_backdrop_adjustments":false,"knockout_max_work":render::MAX_RENDER_WORK,"dissolve":true,"svg":"normal_only"});
    capabilities["artwork_masks"] = json!({"source":"top_level_nonprinting_mask_source","content":["vector","text","isolated_group","geometric_clip","validated_component_instance"],"modes":["alpha","luminance"],"working_space":"premultiplied_encoded_srgb_f64","luminance_coefficients":[0.2125,0.7154,0.0721],"region":"optional_transformed_rectangle","linking":"item_local_or_document_coordinates","sharing":"stable_source_id_with_dependent_lock_checks","operations":["artwork_mask","artwork_mask_link","artwork_mask_transform"],"svg":"per_reference_vector_copies_with_reported_identity_loss","svg_import":true,"nested_source_masks":false,"grid_mask_coexistence":false});
    capabilities["reconstruction"] = json!({"methods":["area","bicubic","lanczos3"],"bicubic_parameter":-0.5,"lanczos_radius":3,"footprint":"inverse_pixel_source_axis_bounds","downsample":"widen_and_normalize_each_axis","area":"exact_box_cell_overlap","alpha":"premultiplied_with_final_valid_rgba_projection","border":"clamp_to_source_crop","max_axis_taps":resample::MAX_AXIS_TAPS,"max_work":resample::MAX_WORK,"svg":false,"scalar_masks":false,"displacement_maps":false});
    capabilities["canvas_operations"] = json!({"document_kinds":["raster"],"operation":"canvas","actions":["crop","extent","scale","resolution"],"sampling":["nearest","bilinear","area","bicubic","lanczos3"],"sampling_boundary_epsilon_factor":limits::assets::PIXEL_BOUNDARY_EPSILONS,"extent_anchors":"nine_positions_with_floor_half_delta","content":"retained_layers_and_source_pixels","auxiliary_planes":"canvas_bound_crop_pad_or_resample","filters":"explicit_preserve_parameters_policy_required","resolution_only":true,"advanced_resamplers":true});
    capabilities["svg_import"] = svg_import_contract;
    capabilities["encoded_image_assets"] = json!({"storage_type":"encoded","formats":["png","jpeg"],
        "source":"immutable_base64_in_snapshot","verification":"source_hash_then_decode_and_compare_dimensions_pixel_hash_and_provenance",
        "color_policy":"retained_in_storage","external_store_required":false,
        "source_byte_limit":assets::MAX_IMPORT_BYTES,"aggregate_pixel_limit":assets::MAX_ASSET_PIXELS,
        "snapshot_bytes":"resource_profile_limit_including_base64","raw_inline_pixel_limit_unchanged":true});
    capabilities["native_vector_import"] = json!({
        "command":"vector.import","source":"local_regular_file;read_only",
        "container":"editable_text_14_creator_30;or_classic_xref_PDF_with_one_reachable_editable_stream_container_12_roundtrip_24_creator_30",
        "source_bytes":vector_native::MAX_SOURCE_BYTES,"decoded_bytes":vector_native::MAX_DECODED_BYTES,
        "blocks":vector_native::MAX_BLOCKS,"compression":["none","single_zstandard_frame_checked_checksum_and_size"],
        "editable":["flat_named_layers","closed_line_and_cubic_RGB_paths","visibility","locks","opacity","shared_scene_artboards"],
        "color_policy":"required_encoded_srgb;source_profiles_not_imported",
        "coordinates":"native_points_at_72ppi;one_shared_y_flip_and_artboard_union_origin",
        "unsupported":["nested_layers","groups","open_or_stroked_or_compound_paths","gradients","text","images","links","effects","clipping","nondefault_blend_or_winding","fractional_RGB_components","nonzero_bleed","non_ASCII_labels","scaled_canvases","xref_streams","incremental_or_encrypted_PDF","unknown_artwork_operators_or_object_properties"],
        "preview_pages":"never_used_as_editable_artwork","native_delivery":"native_vector_subset",
        "checkpoint_status":"basic_verified;extended_in_progress"
    });
    capabilities["native_vector_delivery"] = json!({"format":"native_vector","transport":"editable_text","editable":["flat_named_layers","closed_line_and_cubic_RGB_paths","visibility","locks","opacity","shared_scene_artboards"],"geometry_conversion":["rectangles_to_paths","polygons_to_paths","affine_transforms_baked_into_controls"],"units":"points_at_72_per_inch","color":"encoded_RGB_without_profile","names":"nonempty_printable_ASCII;ambiguous_native_identity_spellings_rejected","layers":"nonempty_flat_root_layers;isolated_normal_full_opacity","paths":"one_closed_nonzero_contour;opaque_solid_RGB_fill;no_stroke","artboards":"scene_scope;zero_bleed;no_guides_or_background","resources":"none","unsupported":["empty_layers","root_paths","nested_containers","text","images","links","gradients","effects","masks","clipping","nonnormal_blends","fill_opacity","profiles","inks","selection_channels_variants"],"metadata":"explicit_strip_if_descriptive_metadata_present","normal_canvas_coordinate_limit":limits::vector_native_write::MAX_COORDINATE as u32,"output_bytes":vector_native::MAX_DECODED_BYTES,"implicit_canvas_artboard":true,"snapshot_payload":false,"executable_prolog":false,"checkpoint_status":"basic_verified;extended_in_progress"});
    capabilities["resource_profiles"] = json!({"field":"resource_profile","default":"standard","operation":"resource_profile","standard":{"items":model::MAX_ITEMS,"geometry_commands":model::MAX_SEGMENTS,"snapshot_bytes":model::MAX_DOCUMENT_BYTES,"svg_source_bytes":svg_import::MAX_BYTES,"svg_nodes":svg_import::MAX_NODES},"large_vector":{"items":model::MAX_LARGE_VECTOR_ITEMS,"geometry_commands":model::MAX_LARGE_VECTOR_COMMANDS,"snapshot_bytes":model::MAX_LARGE_VECTOR_BYTES,"svg_source_bytes":svg_import::MAX_LARGE_BYTES,"svg_nodes":svg_import::MAX_LARGE_NODES,"kind":"vector"},"scope":"stored_and_expanded_document_budgets;other_algorithm_and_transport_limits_remain_independent","per_path_commands":model::MAX_SEGMENTS,"checkpoint":"vector.resources.extended","checkpoint_status":"in_progress"});
    capabilities["resource_profiles"]["regional_rendering"] = json!({"profile":"large_vector","eligible":"ordinary_vector_fills_strokes_and_neutral_groups","bounds":"transformed_controls_and_generated_strokes_plus_two_evaluation_pixels","paint_coordinates":"original_item_space","work":"actual_region_scans_paints_composition_and_controls","other_scenes":"general_bounded_renderer","raises_processing_limits":false});
    capabilities["resource_profiles"]["large_raster"] = json!({"items":model::MAX_LARGE_RASTER_ITEMS,"geometry_commands":model::MAX_LARGE_RASTER_COMMANDS,"snapshot_bytes":model::MAX_LARGE_RASTER_BYTES,"kind":"raster","overlays":"ordinary_vector_geometry_with_fills_and_strokes","native_storage":"existing_immutable_blocks_and_pure_patches","rendering":"existing_whole_limits;opt_in_tiled_evaluation;conservative_spatial_membership;neighboring_source_reuse","raises_processing_limits":false});
    capabilities["components"]["max_evaluated_items_by_profile"] = json!({"standard":model::MAX_ITEMS,"large_vector":model::MAX_LARGE_VECTOR_ITEMS,"large_raster":model::MAX_LARGE_RASTER_ITEMS});
    capabilities["svg_import"]["masks"] = json!({"content":["shapes","groups","gradients","geometric_clips","bound_text"],"modes":["alpha","luminance"],"units":["userSpaceOnUse","objectBoundingBox"],"sharing":"editable_source_with_import_time_coordinate_binding","legacy_region":"minus_10_percent_to_120_percent","svg2_region":"unclipped_when_all_region_attributes_absent","mode_override":"css_mask_mode","compositing":"srgb","recursive_masks":false});
    capabilities["svg_import"]["masks"]["viewport_binding"] =
        json!("one_source_per_referencing_user_viewport;cross_viewport_sharing_loss_reported");
    capabilities["objects"] = json!({"commands":["object.import","object.open","object.status"],"operations":["object_replace","object_refresh","object_detach"],"parent_kind":"raster","source_kinds":["vector","raster"],"source_format":"exact_utf8_engine_snapshot","native_document_interchange":false,"link":"flat_key_explicit_root_pinned_source_hash_refresh","external_sources_unchanged":true,"implicit_link_io":false,"source_store":"inline_retained_bytes_with_sha256","max_nesting":objects::MAX_NESTING,"max_rendered_objects":objects::MAX_RENDERED_OBJECTS,"surface_scale":[1,limits::render_quality::MAX_SCALE],"surface_precision":"f64_before_parent_reconstruction","render_budgets":"aggregate_work_and_buffer_pixels_across_evaluations","duplicate":"independent_retained_value","resources":"explicit_shared_asset_and_font_roots_pinned_within_source","missing_link":"reported_explicitly_retained_source_stays_renderable","hdr":"native_linear_parent_or_explicit_object_view","privacy":"recursive_snapshot_sanitization_detaches_links","page_delivery":"explicit_unsupported_use_image_or_snapshot"});
    capabilities["backgrounds"] = json!({"operation":"background","document_kind":"raster","actions":["promote","restore_source","to_layer"],"role":"single_bottom_printable_root","source":"retained_pixels_alpha_geometry_and_appearance","matte":"explicit_rgb8_current_canvas_after_source_controls_before_clipped_siblings","visibility":"suppresses_complete_background","implicit_lock":false,"ordinary_conversion":"isolated_layer_with_explicit_source_and_matte_ids","duplicate_and_transfer":"ordinary_retained_source_without_document_role","bounds":"source_geometry_with_separate_inspected_canvas_bounds"});
    capabilities["supported"]["raster"]
        .as_array_mut()
        .unwrap()
        .push(json!("retained_opaque_backgrounds"));
    capabilities["render_quality"] = json!({"field":"render_options","commands":["document.render","document.export","artboard.export","document.publish","session.publish"],"formats":["png","jpeg","tiff"],"antialias":["none","coverage","supersample2","supersample4"],"default_antialias":"coverage","supersample_factors":[2,4],"averaging_space":["encoded_srgb","linear_srgb"],"default_averaging":"encoded_srgb","compositing":"existing_encoded_srgb_premultiplied_f64","averaging":"completed_premultiplied_samples_before_requested_depth_projection","internal_scale_maximum":limits::render_quality::MAX_INTERNAL_SCALE,"padding_document_units":[0,limits::render_quality::MAX_PADDING],"crop_to_canvas_default":true,"bounds":"symmetric_padding_then_optional_original_canvas_crop","profile_order":"average_then_rgba8_then_existing_output_conversion","effect_domain":"padded_evaluation_viewport","viewport_patterns":"noise_and_mosaic_rebase_to_evaluation_origin","limits":"all_evaluation_pixels_and_work_including_padding_and_samples","source_mutation":false,"edge_precision":"f32_coverage_then_f64_average_not_exact_area_for_arbitrary_geometry"});
    capabilities["coordinate_precision"] = json!({"storage":"IEEE754_binary64","snapshot":"exact_stored_finite_binary64_numbers","svg_literals":"roundtrip_decimal_geometry_transform_clip_and_gradient_numbers","direct_transport_absolute_error":0,"negative_coordinates":true,"fractional_coordinates":true,"geometry_control_point_absolute_limit":model::MAX_COORDINATE,"transform_component_absolute_limit":model::MAX_COORDINATE,"svg_normalization":"binary64_arithmetic_for_units_viewbox_relative_smooth_quadratic_and_transform_lists","generated_geometry":"uses_each_operation_declared_error_contract","zero_sign":"no_geometric_semantics","preview":"binary64_placement_then_output_space_binary32_quantized_coverage_not_exact_geometric_pixel_area","coverage_routes":["fills","object_and_document_strokes","image_boundaries","geometric_masks"],"ellipse_coverage":"original_32_tangent_cubic_arcs","external_svg_consumers":"their_own_precision_and_coverage_contract","scope":"within_document_and_svg_import_limits;retain_snapshot_for_source_parameters"});
    capabilities["coordinate_precision"]["point_arithmetic"] = json!({
        "expression":"a*x+b*y+translation_for_each_axis",
        "ordinary_or_compensated_absolute_error":geometry::MAX_POINT_ROUNDOFF,
        "alternative":"certified_nearest_binary64;exact_rational_fallback_for_ambiguous_rounding_or_intermediate_overflow",
        "error_scope":"application_of_the_supplied_finite_binary64_matrix_to_the_supplied_point;matrix_construction_normalization_and_coverage_quantization_are_separate",
        "source_controls_changed":false,
        "admission_limits_changed":false
    });
    capabilities["coordinate_precision"]["hierarchy"] = json!({
        "fast_composition_point_error":scene::MAX_FAST_POINT_ERROR,
        "error_scope":format!("composition_only;exact_application_to_controls_bounded_by_{};final_point_arithmetic_and_coverage_are_separate", model::MAX_COORDINATE),
        "fallback":"exact_rational_product_of_stored_binary64_matrices;certified_nearest_final_coefficients",
        "maximum_ancestors":scene::MAX_DEPTH,
        "shared_chain_cache_entries":scene::MAX_CACHED_CHAINS,
        "cache_scope":"one_immutable_validation_render_or_inspection;no_cross_revision_reuse",
        "stored_controls_changed":false
    });
    capabilities["coordinate_precision"]["affine_inverse"] = json!({
        "minimum_absolute_determinant":geometry::MIN_DETERMINANT,
        "determinant_test":"exact_stored_binary64_arithmetic_against_binary64_minimum;certified_fast_interval_or_exact_rational_fallback",
        "renderer_nonsingular_check":true,
        "fast_coefficient_point_error":geometry::MAX_FAST_INVERSE_POINT_ERROR,
        "point_coordinate_absolute_limit":limits::geometry_affine::MAX_POINT_COORDINATE,
        "fallback":"exact_rational_determinant_and_inverse;certified_nearest_binary64_coefficients",
        "error_scope":"coefficient_error_only;final_point_arithmetic_inverse_composition_and_sampling_are_separate",
        "stored_controls_changed":false
    });
    capabilities["coordinate_precision"]["relative_edits"] = json!({
        "operations":["reparent","transform","mask_link","mask_transform","artwork_mask_link","artwork_mask_transform"],
        "expression":"inverse_parent_times_complete_ordered_factors;anchors_included_before_rounding",
        "maximum_factors":geometry::MAX_RELATIVE_FACTORS,
        "fast_coefficient_point_error":geometry::MAX_FAST_INVERSE_POINT_ERROR,
        "point_coordinate_absolute_limit":limits::geometry_affine::MAX_POINT_COORDINATE,
        "fallback":"exact_rational_complete_expression;certified_nearest_binary64_final_coefficients",
        "error_scope":"coefficient_error_only;world_recomposition_point_arithmetic_and_sampling_are_separate",
        "source_geometry_changed":false
    });
    capabilities["coordinate_precision"]["coordinate_conversions"] = json!({
        "maximum_expression_factors":geometry::MAX_TRANSFORM_FACTORS,
        "factor_types":["forward","inverse"],
        "fast_coefficient_point_error":geometry::MAX_FAST_INVERSE_POINT_ERROR,
        "point_coordinate_absolute_limit":limits::geometry_affine::MAX_POINT_COORDINATE,
        "fallback":"exact_rational_ordered_expression;certified_nearest_binary64_final_coefficients",
        "scope":["transfers","copied_clips","selection_mask_placement","applied_mask_clip_placement","appearance_bake_placement","world_path_edits","alignment_distribution_layout_snap_moves","dimension_edits","artboard_mask_placement","focused_preview_mapping","svg_mask_and_clip_coordinate_conversion"],
        "error_scope":"input_expression_coefficients;world_recomposition_point_arithmetic_raster_sampling_and_input_normalization_are_separate",
        "source_geometry_changed_by_coordinate_conversion":false
    });
    capabilities["dimensions"] = json!({"inspect":"geometry.measure","edit":"dimensions","units":["px","pt","pc","mm","cm","in"],"unit_conversion":"exact_rational_document_resolution_ppi","angle_degrees":[-i64::from(limits::dimensions::MAX_ANGLE_DEGREES),limits::dimensions::MAX_ANGLE_DEGREES],"anchors":["min","center","max"],"bounds":"unclipped_geometry_projected_in_declared_axes;not_strokes_effects_or_glyph_ink","bounds_precision":"binary64","length":"sum_of_authored_boundaries_with_closed_contour_closing_edges","area":"signed_algebraic_contour_integral;null_for_any_open_contour;not_filled_union_area","certificate":"exact_rational_line_cubic_integrals_and_chord_polygon_or_analytic_ellipse_tangent_enclosures","length_tolerance":[limits::dimensions::MIN_LENGTH_TOLERANCE,limits::dimensions::MAX_LENGTH_TOLERANCE],"area_tolerance":[limits::dimensions::MIN_AREA_TOLERANCE,limits::dimensions::MAX_AREA_TOLERANCE],"work":dimensions::MAX_WORK,"subdivision_depth":limits::dimensions::MAX_SUBDIVISION_DEPTH,"precision_failure":"NUMERIC_PRECISION","requested_logical_dimensions":[limits::dimensions::MIN_LOGICAL_DIMENSION,limits::dimensions::MAX_LOGICAL_DIMENSION as u32],"resize":"world_basis_scale_through_parent_inverse;requires_two_nonzero_source_dimensions","preserve_aspect":"exactly_one_requested_dimension","source_geometry_retained":true});
    capabilities["dimensions"].as_object_mut().unwrap().extend(
        json!({
            "default_length_tolerance": limits::dimensions::DEFAULT_LENGTH_TOLERANCE,
            "default_area_tolerance": limits::dimensions::DEFAULT_AREA_TOLERANCE
        })
        .as_object()
        .unwrap()
        .clone(),
    );
    capabilities["snapping"] = json!({"operation":"snap","targets":["point","grid","guide","item"],"target_limit":limits::snapping::MAX_TARGETS,"reference_state":"frozen_before_operation","source_modes":["together","individual"],"rotated_bounds":true,"oblique_guides":true,"intersections_default":true,"priority":"point_grid_item_intersection_then_guide_projection;distance_then_input_order","grid_tie":"lower_index_per_axis","guide_parallel_threshold":limits::snapping::PARALLEL_THRESHOLD,"units":["px","pt","pc","mm","cm","in"],"maximum_logical_distance":model::MAX_COORDINATE,"no_match":"explicit_receipt_without_item_mutation","source_geometry_retained":true});
    capabilities["swatches"] = json!({"dictionary":"document.swatches","inspect":"swatch.inspect","edit":"swatch","bake":"swatch_bake","convert":"swatch_convert_process_or_spot_retaining_components_or_explicit_replacement","definitions":["process","spot","tint"],"declaration_spaces":["srgb","gray","cmyk","lab","device"],"storage":"exact_declared_binary64;no_implicit_conversion","gray":"encoded_srgb_neutral","lab":"D50_L0..100_a_b_minus128..127","non_rgb_preview":"legacy_CMYK_Lab_require_explicit_preview;device_declarations_convert_source_profile_to_srgb","reference":{"swatch":"stable_id","tint":[0,1],"opacity":[0,1],"overprint":["knockout","preserve","preserve_nonzero"]},"precise_solid":"rgba_normalized_binary64_without_early_byte_rounding","preview_tint":"encoded_white_plus_effective_tint_times_alternate_minus_white","max_swatches":swatches::MAX_SWATCHES,"max_chain":swatches::MAX_DEPTH,"name_bytes":limits::swatches::MAX_NAME_BYTES,"locks":"direct_transitive_resource_and_saved_variant_dependents","deletion":"in_use_references_rejected","transfer":"independent_ID_remap_with_transitive_color_dependencies","vector_delivery":"display_srgb_gray;pdf_options.color_native_inks_preserves_spot_CMYK_Lab_and_overprint","image_delivery":"display_preview_with_explicit_losses","spot_separations":"native_PDF_Separation_resources;document_prepress_scalar_planes","overprint":"native_PDF_OP_op_OPM;display_requires_explicit_bake","separation_diagnostics":"swatch.inspect.ink_diagnostics_and_per_page_PDF_receipts;structural_not_plate_coverage","profile_driven_non_rgb_conversion":true});
    capabilities["assistance"] = json!({"inspect":"assist.layout","edit":"assist_layout","algorithm":"ordered_shelves_v1","objective":"minimum_total_row_height_then_fewest_rows_then_lexicographic_row_ends","arithmetic":"exact_rational_optimization_of_binary64_scene_bounds;binary64_placement","geometry_error_limit":assistance::PLACEMENT_ERROR,"maximum_items":assistance::MAX_ITEMS,"selection":"visible_printing_antichain;positive_bounds;unlocked_descendants_and_dependents","bounds":"unclipped_geometry;no_strokes_effects_or_alpha;text_frames","dependencies":"builtin_cpu;no_models_GPU_network_or_external_resource_loading","scope":"fixed_size_ordered_rows;explicit_area_gaps_and_alignment;unselected_artwork_ignored","unsupported":["semantic_generation","learned_models","free_reordering","automatic_resizing","painted_bounds_packing","obstacle_avoidance"]});
    capabilities["pixel_assistance"] = json!({"inspect":"assist.segment","edit":"assist_mask","algorithm":"seeded_color_cut_v1","input":"native_unfiltered_inline_RGBA8_or_u8_RGBA_gray_alpha_samples_or_verified_image_crop;encoded_srgb","objective":"minimum_integer_color_cost_plus_4_neighbor_boundary_cost;hard_class_seeds","features":"rounded_byte_premultiplied_encoded_RGB_plus_alpha","color_cost":"minimum_squared_distance_to_each_class_seed","neighbor_cost":"floor(smoothness*edge_scale/(edge_scale+squared_feature_distance))","smoothness":[0,limits::assistance_segment::MAX_SMOOTHNESS],"edge_scale":[1,limits::assistance_segment::MAX_EDGE_SCALE],"defaults":{"smoothness":limits::assistance_segment::DEFAULT_WEIGHT,"edge_scale":limits::assistance_segment::DEFAULT_WEIGHT},"ties":"smallest_foreground_set_among_minimum_cuts","certificate":"minimum_energy_equals_max_flow;optional_full_integer_costs","maximum_pixels":assistance::segment::MAX_PIXELS,"maximum_seeds_per_class":assistance::segment::MAX_SEEDS,"maximum_work":assistance::segment::MAX_WORK,"mask":"binary_native_grid;linked_display_scale;original_pixels_preserved;explicit_existing_mask_replacement","dependencies":"builtin_cpu;no_models_GPU_network;explicit_image_store_when_needed","unsupported":["semantic_recognition","alpha_matting","learned_models","remote_services","high_depth_or_HDR_input","retained_pixel_warps"]});
    capabilities["pixel_assistance"]["workflows"] = json!({"remove":{"op":"repair","action":"fill","region":"explicit_native_mask","source":"frozen_local_donors","quality":"context_and_boundary_RMS_limits"},"denoise":{"op":"repair","action":"edge_correct","guide":"explicit_self_or_local_guide","estimator":"guided_weighted_median","quality":"change_RMS_and_effective_support_limits"},"upscale":{"op":"canvas","action":"scale","sampling":"explicit_reconstruction_kernel","source":"retained_native_samples","border":"existing_clamped_sampling"},"models":[],"remote_fallback":false});
    capabilities["volumes"] = json!({
        "content":"volume","inspect":"volume.inspect","edits":["volume","volume_expand"],
        "profile":"retained_closed_geometry;simple_nonintersecting_polygonal_contours;concavity_holes_disjoint_regions",
        "fill_rules":["nonzero","even_odd"],"source_curves":"existing_certified_identity_map_chords",
        "source_tolerance":[limits::warps::MIN_TOLERANCE,limits::warps::MAX_TOLERANCE],"default_source_tolerance":limits::volumes::DEFAULT_SOURCE_TOLERANCE,
        "extrusion":"front_z_zero_to_back_z_negative_depth","depth":[0,limits::volumes::MAX_DEPTH],
        "rotation":"degrees_about_pivot_in_X_then_Y_then_Z_order","placement":"rotation_then_pivot_plus_translation;outer_item_transform_after_projection",
        "cameras":["orthographic_positive_Z","perspective_explicit_principal_distance_near_far"],
        "perspective_distance":[limits::volumes::MIN_CAMERA_DISTANCE,limits::volumes::MAX_CAMERA_DISTANCE],"maximum_perspective_magnification":limits::volumes::MAX_MAGNIFICATION,
        "camera_clipping":"whole_request_rejected_when_vertices_cross_depth_range",
        "materials":["unlit_srgb8","flat_diffuse_linear_srgb_with_explicit_ambient_and_directional_lights"],
        "lights":limits::volumes::MAX_LIGHTS,"light_intensity":[0,limits::volumes::MAX_LIGHT_INTENSITY],"light_space":"post_rotation_3D;direction_toward_light",
        "opacity":"opaque_surface;outer_item_opacity_after_solid_compositing",
        "maximum_profile_edges":volumes::MAX_EDGES,"maximum_projected_faces":volumes::MAX_FACES,
        "early_profile_limit":"exact_nonredundant_interior_vertex_lower_bound;collinear_subdivision_does_not_spend_edges",
        "preparation_cancellation":"caller_control_during_certified_subdivision_exact_profile_topology_and_face_partition",
        "visibility":"back_face_culling_and_bounded_BSP_partition_far_to_near",
        "numeric":"binary64_rigid_projection_and_plane_splits;shared_renderer_edge_quantization",
        "expansion":"independent_ordered_vector_faces;original_source_in_snapshot_or_history",
        "dependencies":"CPU_only_builtin_geometry_and_materials;no_models_GPU_assets_or_network",
        "offline_verification":"Windows_AppContainer_zero_capabilities;network_probe_denied;repeated_outputs_match_normal_execution",
        "unsupported":["intersecting_or_touching_profiles","bevels","revolution","textures","cast_shadows","inter_volume_3D_occlusion","implicit_camera_clipping"]
    });
    capabilities["appearance"] = json!({
        "content":"appearance","inspect":"appearance.inspect",
        "edits":["appearance","appearance_expand","appearance_bake"],
        "source":"one_retained_geometry_and_fill_rule","passes":[1,appearance::MAX_PASSES],
        "vector_tolerance":[limits::warps::MIN_TOLERANCE,limits::warps::MAX_TOLERANCE],
        "default_vector_tolerance":limits::warps::DEFAULT_TOLERANCE,
        "order":"bottom_to_top","pass_controls":["fill","stroke","enabled","opacity","blend","maps","tolerance","filters","effects"],
        "pipeline":"ordered_geometry_maps_then_fill_and_stroke_then_ordered_raster_filters_then_existing_decoration_policy",
        "outer_controls":"apply_to_isolated_stack","maps":["affine","perspective","envelope"],
        "expansion":"independent_editable_vector_objects;maps_materialized;raster_filters_and_decorations_retained",
        "bake":{"space":"encoded_srgb","viewport":"explicit_document_space_origin_width_height","scale":[1,limits::render_quality::MAX_SCALE],"pixels":model::MAX_STORED_PIXELS,"output":"embedded_immutable_RGBA8_image","placement":"inverse_world_transform","outer_controls":"retained","boundaries":"filters_reevaluated_for_declared_viewport","losses":"outside_region_cropped;paints_maps_filters_and_pass_order_frozen"},
        "budgets":"shared_evaluated_document_items_geometry_paints_masks_filters_and_effects",
        "bounds":"union_of_mapped_geometry_including_disabled_passes;excludes_strokes_and_raster_effects",
        "history":"atomic_edits_snapshots_undo_redo_and_retry_receipts",
        "delivery":"existing_SVG_PDF_supported_paints_and_blends;live_raster_effects_require_explicit_baking",
        "unsupported":["unlinked_per_pass_filter_masks","arbitrary_interleaving_of_pipeline_stages","recursive_appearance_passes","non_srgb_baking"]
    });
    capabilities["supported"]["vector"]
        .as_array_mut()
        .unwrap()
        .push(json!("retained_multiple_fill_stroke_appearance"));
    capabilities["presets"] = presets::catalog();
    capabilities["handoff"] = json!({
        "commands":["handoff.export","handoff.inspect"],"schema_version":handoff::VERSION,
        "selection":["still_with_explicit_sequence_frame","complete_ordered_sequence"],
        "source":"exact_editable_snapshot_with_external_resource_bindings;history_not_bundled",
        "identity":"SHA256_of_compact_typed_manifest_and_every_source_frame_scene_file;content_named_flat_paths",
        "revision_update":"explicit_pinned_previous_manifest;same_link_and_document;strictly_newer_source_revision",
        "timing":["strict","sample_start"],"ending":["hold_last","loop","transparent"],
        "alpha":["transparent","explicit_opaque_matte"],"color":"encoded_sRGB_straight_RGBA8_PNG;no_output_ICC",
        "files":"export_returns_base64_without_writes;inspect_input_root_checks_all_complete_files",
        "limits":{"frames":sequences::MAX_FRAMES,"aggregate_pixels":sequences::MAX_PIXELS,
            "canvas_pixels":handoff::MAX_PIXELS,"axis":limits::handoff::MAX_AXIS,"seconds":limits::handoff::MAX_SECONDS,"bytes":handoff::MAX_BYTES},
        "losses":handoff::LOSSES,"automatic_relink":false,"model_trials":false
    });
    capabilities["sequences"] = json!({
        "commands":["sequence.import","sequence.inspect","sequence.open","sequence.export"],
        "storage":"document.variants.sequence","edits":["sequence_set","sequence_frame","sequence_from_layers"],
        "imports":["explicit_ordered_png_jpeg_tiff_files","apng_rgba8_palette_gray_rgb_expansion"],
        "exports":["ordered_png_artifacts_with_timing_receipt","apng_full_canvas_rgba8"],
        "apng_compositing":{"default":"linear_srgb","options":["linear_srgb","encoded_srgb"],"alpha":"straight_over;nearest_byte_after_each_frame","disposal":["none","background","previous"],"interlace":"Adam7","separate_default_image":"hidden_poster_retained_not_reexported"},
        "timing":"exact_u16_fraction;zero_denominator_100;zero_numerator_consumer_fastest","plays":"u32;zero_infinite",
        "max_frames":sequences::MAX_FRAMES,"max_distinct_import_states":variants::MAX_DATASETS,
        "max_total_output_or_import_pixels":sequences::MAX_PIXELS,"max_evaluated_scene_work":render::MAX_RENDER_WORK,
        "max_output_bytes":publish::MAX_OUTPUT_BYTES,"cancellation":"between_frames_and_during_encoding_or_publication",
        "still_handoff":"sequence.open_then_PNG_publication;explicit_consumer_hold_and_matte;editable_source_retained",
        "apng_profile_conversion":false,"apng_output_profile":false,"high_depth_animation":false,"audio":false,"live_playback":false,
        "source_preserved":true
    });
    capabilities["vector_prepress"] = json!({
        "delivery": "pdf_options.color_native_inks_with_artboard_selection",
        "trim": "artboard_width_height_in_document_logical_units",
        "bleed": "explicit_per_edge_insets_reveal_owned_artwork",
        "physical_size": "resolution_ppi_and_PDF_UserUnit",
        "spots": "distinct_base_ids_shared_Separation_resources",
        "overprint": ["knockout", "preserve", "preserve_nonzero"],
        "inventory": "selected_page_structural_diagnostics_not_plate_coverage",
        "print_jobs": false,
        "calibrated_page":"document_RGB_output_profile;managed_source_profiles;explicit_PDF2_BPC_OFF",
        "prepared_plates":"pdf_options.prepress;flattened_process_and_spot_planes_with_marks",
        "unsupported": ["editable_PDF_reimport", "embedded_text_fonts"]
    });
    capabilities["print_cmyk"] = json!({
        "delivery":"pdf_options.print;flattened_ICCBased_CMYK8_images",
        "required":["profile","matte"],
        "profile":"ICC_v2_v4_CMYK_output_XYZ_or_Lab;A2B0_and_B2A0_required;exact_bytes_embedded",
        "max_profile_bytes":profiles::cmyk::MAX_PROFILE_BYTES,
        "profile_sources":["inline_icc_within_transport_limit","absolute_file_with_required_sha256"],
        "intent":["relative_colorimetric","absolute_colorimetric","perceptual","saturation"],
        "matte":"encoded_srgb_byte_triplet_composited_before_conversion",
        "raster_scale":(1..=limits::render_quality::MAX_SCALE).collect::<Vec<_>>(),
        "raster_ppi":"document_resolution_ppi_times_raster_scale",
        "physical_size":"independent_of_raster_scale;72_points_per_inch",
        "render_options":"shared_renderer;crop_to_canvas_true;explicit_HDR_view",
        "page_selection":"pdf_options.artboards_and_include_bleed",
        "limits":"shared_render_page_profile_and_output_limits",
        "black_point_compensation":false,"endpoint_fixups":false,"print_jobs":false,
        "conflicts":["document_output_profile","native_inks"],
        "unsupported":["float_PCS_override_tables","PDF_X_certification"],
        "source_preserved":true
    });
    capabilities["native_prepress"] = json!({
        "command":"document.prepress","stage":"in_progress","read_only":true,
        "source":"encoded_vector_and_raster_artwork;explicit_CMYK_output_profile",
        "images":{"content":["placed_RGBA8","inline_RGBA8","normalized_RGB_or_gray_u8_u16_f32_samples","retained_raw_srgb8_srgb16"],"source_profiles":"retained_RGB_matrix_TRC_or_XYZ_Lab_tables;direct_to_CMYK","reconstruction":"associated_retained_source_RGB_before_separation","sampling":["nearest","bilinear","area","bicubic","lanczos3"],"spot_behavior":"knockout_at_source_alpha","receipts":"image_sources_with_source_hashes","max_source_profiles":prepress::MAX_SOURCE_PROFILES},
        "paper":"opaque_zero_ink","native_cmyk":"exact_operands_before_compositing",
        "converted_paints":["srgb","gray","lab","profiled_rgb_gray_cmyk_and_D50_lab"],"conversion_order":"before_ink_alpha_compositing",
        "intents":["relative_colorimetric","absolute_colorimetric","perceptual","saturation"],
        "spots":"sorted_base_swatch_identity;duplicate_labels_remain_distinct",
        "overprint":["knockout","preserve","preserve_nonzero"],
        "groups":["isolated_all_blend_modes","normal_pass_through_with_blended_children","isolated_and_pass_through_knockout"],
        "blending":prepress::blending_receipt(),
        "coverage":["scalar_masks","shared_alpha_artwork_masks","shared_encoded_sRGB_luminance_artwork_masks","raster_layer_alpha_clipping","geometric_clips","outlined_strokes","outlined_text","seeded_local_cell_dissolve"],
        "coverage_composition":prepress::coverage_receipt(),
        "coverage_sources":{"receipt":"coverage_sources;shared_with_PDF_pages","mask_hashes":["source_sha256:source_items_and_fonts","evaluated_source_sha256:placed_palette_resolved_items"],"max_mask_samples":artwork_masks::MAX_COVERAGE_PIXELS,"layer_clipping":"intrinsic_base_alpha_preserved;base_controls_once_after_stack;opaque_background_controls_before_stack","overprint":"independent_per_ink_backdrop_retention","mask_color":"existing_encoded_sRGB_scalar_contract;named_preview_required;overprint_unsupported_inside_mask"},
        "plates":"scalar_gray8_PNG;single_nearest_byte_projection;0_no_ink_255_full_ink",
        "arithmetic":"binary64_ink_amounts_and_original_ICC_curve_matrix_trilinear_evaluation",
        "PCS_range":"Lab_clamped_to_normalized_table_domain;XYZ_outside_encoding_rejected",
        "max_spots":prepress::MAX_SPOTS,"max_buffer_values":prepress::MAX_BUFFER_VALUES,"max_work":prepress::MAX_WORK,
        "print_jobs":false,"source_mutation":false,"file_publication":false,
        "pdf_delivery":{"option":"pdf_options.prepress","channels":"NChannel_CMYK_and_named8","profile":"exact_supplied_ICC","image_bytes":"same_as_document.prepress","spot_fallback":"explicit_multiplicative_declared","marks":["crop","registration"],"mark_units":"physical_points","mark_colorant":"All","mark_location":"outside_bleed","publication":"document.publish_or_session.publish;create_only","max_aggregate_pixels":pdf::MAX_IMAGE_PIXELS,"max_aggregate_work":prepress::MAX_WORK,"editable_reimport":false,"press_certification":false},
        "remaining":[],
        "checkpoint_verification":"implementation.status",
        "unsupported":["adjustments_without_explicit_policy","float_PCS_override_tables","root_HDR_without_explicit_retained_view","root_independent_channel_recipes","root_RGB_output_profiles"]
    });
    capabilities["native_prepress"]["effects"] = prepress::effects_receipt();
    capabilities["native_prepress"]["pixel_warps"] = prepress::pixel_warps_receipt();
    capabilities["native_prepress"]["raw_sources"] = prepress::raw_receipt();
    capabilities["native_prepress"]["object_sources"] = prepress::objects_receipt();
    capabilities["native_prepress"]["ink_bindings"] = prepress::bindings::receipt();
    capabilities["native_prepress"]["adjustments"] = prepress::adjustments_receipt();
    capabilities["native_prepress"]["filters"] = prepress::filters_receipt();
    capabilities["print_proof"] = json!({
        "command":"document.proof","read_only":true,"source":"same_flattened_matted_CMYK8_as_PDF_print",
        "view_intents":["relative_colorimetric","absolute_colorimetric"],
        "profile_interpolation":"pinned_color_engine;four_dimensional_multilinear;consumer_algorithms_may_differ",
        "display":"sRGB_RGBA8_with_exact_embedded_working_profile;opaque",
        "plates":"four_grayscale8_PNGs;0_no_ink_255_full_ink;no_color_profile",
        "difference":"D50_CIE76_before_display_clipping;explicit_threshold;not_exact_gamut_membership",
        "display_clipping":"linear_sRGB_component_and_pixel_counts_before_clamp",
        "samples":proof::MAX_SAMPLES,"output_bytes":publish::MAX_OUTPUT_BYTES,
        "source_mutation":false,"print_jobs":false,"file_publication":false,
        "combined_named":"print.named_inks;exact_independent_scalar_planes;continuous_multiplicative_CMYK_fallback;16bit_backend_weight_bins",
        "gamut":"ICC_gamt_if_available;required_and_off_modes;source_process_PCS_only",
        "separation_intents":["relative_colorimetric","absolute_colorimetric","perceptual","saturation"],"gamut_intent":"absolute_if_separation_absolute;otherwise_relative_colourimetric","unsupported":["overprint_simulation","perceptual_saturation_physical_view","arbitrary_display_profile","physical_ink_certification","exact_gamut_volume"]
    });
    capabilities["profile_gamut"] = json!({"command":"profile.gamut","read_only":true,"profile":"ICC_v2_v4_CMYK_output_XYZ_or_Lab_with_gamt_tag","tables":["lut8_Lab","lut16_Lab_XYZ","lutBToA_Lab_XYZ"],"inputs":format!("D50_XYZ;finite;{}_samples", limits::profiles_gamut::MAX_SAMPLES),"intents":["relative_colorimetric","absolute_colorimetric"],"classification":"zero_in_gamut_nonzero_out;outside_PCS_encoding_unclassified","interpolation":"original_f64_tetrahedral;exact_fixed_curve_parameters;consumer_integer_paths_may_differ_at_boundaries","source_mutation":false,"print_jobs":false,"missing_table":"GAMUT_UNAVAILABLE;no_roundtrip_substitution","unsupported":["perceptual_reference_medium_mapping","eight_bit_XYZ_tables","spectral_ink_gamut"]});
    capabilities["paragraph_flow"] = json!({"resource":"document.stories","content":"story_frame","edit":["story","story_range"],"inspect":"story.inspect","slots":"ordered_source_flow_independent_of_item_placement","columns":"equal_width_explicit_gutter_and_reverse_order","paragraphs":"separate_original_rich_text_records","spacing":"additive_before_after;leading_and_logical_start_end_first_line_indents","metrics":"max_ascent_plus_max_descent_plus_max_nonnegative_gap","line_fitting":"longest_reshaped_grapheme_prefix_with_ascii_space_preference","indices":"paragraph_local_unicode_scalars","source_coverage":"line_start_end_and_consumed_end_including_skipped_break_spaces","bidi":"complete_paragraph_resolution_across_slots;line_local_shaping","overset":["error","retain"],"overset_inspection":"first_unplaced_paragraph_and_scalar_offset","clipping":"always_slot_rectangle;glyph_overhang_flagged","shared_source_edits":true,"transfer":"complete_story_slots_with_independent_story_and_font_ids","snapshot_history":true,"stories":text::flow::MAX_STORIES,"paragraphs_per_story":text::flow::MAX_PARAGRAPHS,"slots_per_story":text::flow::MAX_SLOTS,"columns_per_slot":text::flow::MAX_COLUMNS,"aggregate_characters":text::MAX_TEXT_CHARS,"visible_hyphenation":{"rules":"story_local_named_weighted_patterns_and_exceptions","rule_sets_per_story":text::flow::hyphens::MAX_RULE_SETS,"tokens":"unicode_lexical_words;original_scalars","fit":"furthest_fitting_space_or_rule_break;hyphen_shaped_with_fragment","marks":["hyphen_minus","hyphen"],"style":"preceding_source_character","emergency_break":"explicit_unmarked_grapheme_fallback;default_false","provenance":"generated_hyphen_cluster_and_original_source_interval","display_bidi":"full_virtual_paragraph_with_one_inserted_scalar;line_local_shaping","rules_budget":"aggregate_document_pattern_and_exception_limits","source_unchanged":true},"structural_lists":{"formats":["bullet","decimal","lower_alpha","upper_alpha","lower_roman","upper_roman"],"levels":text::flow::lists::MAX_LEVELS,"ids_per_story":text::flow::lists::MAX_LISTS,"max_counter":text::flow::lists::MAX_COUNTER,"roman_max":text::flow::lists::MAX_ROMAN_COUNTER,"affix_characters":text::flow::lists::MAX_AFFIX,"counter_scope":"story_local_list_id;ordinary_paragraphs_and_other_lists_do_not_reset","restarts":true,"nested_counters":true,"placement":"first_line_logical_start_hanging_marker;gap_and_indent_explicit","body_source":"unchanged;marker_glyphs_have_generated_provenance","styles":"explicit_or_paragraph_base;pinned_font_resources","character_budget":"body_plus_generated_labels"},"named_paints":true});
    capabilities["hyphenation"] = json!({"command":"text.hyphenate","patterns":"explicit_text_and_scalar_gap_weights_0_to_9","matching":"maximum_over_all_matching_patterns_then_odd_priorities","anchors":["at_start","at_end"],"case":["exact","ascii_lower"],"normalization":"none","exceptions":"replace_pattern_candidates_with_explicit_internal_grapheme_boundaries","indices":"unicode_scalars","minima_units":"extended_graphemes","minima_range":[1,limits::hyphenation::MAX_MINIMUM_GRAPHEMES],"source_preserved":true,"layout_integration":false,"language_dictionaries_bundled":false,"pattern_count":hyphenation::MAX_PATTERNS,"pattern_scalars":hyphenation::MAX_PATTERN_CHARS,"total_pattern_scalars":hyphenation::MAX_TOTAL_PATTERN_CHARS,"exceptions":hyphenation::MAX_EXCEPTIONS,"total_exception_scalars":hyphenation::MAX_EXCEPTION_CHARS,"word_scalars":hyphenation::MAX_WORD_CHARS,"words":hyphenation::MAX_WORDS,"total_word_scalars":hyphenation::MAX_TOTAL_WORD_CHARS,"work":hyphenation::MAX_WORK,"unsupported":["implicit_language_selection","soft_hyphen_input","spelling_replacements","dictionary_file_formats","line_break_placement"]});
    capabilities["hdr"] = json!({"working_space":"linear_srgb","source":"linear_srgb binary32 RGBA or gray-alpha, signed finite color and normalized alpha","encoded_sources":"decoded before linear interpolation and compositing","measure":"sample.measure","grade_operation":"hdr_grade","working_space_operation":"working_space","native_delivery":"f32 TIFF without view","display_view_required":true,"views":["clip","reinhard"],"view_space":"component-wise linear radiance, then encoded sRGB","exposure_stops":[-i64::from(limits::hdr::MAX_EXPOSURE_STOPS),limits::hdr::MAX_EXPOSURE_STOPS],"channel_gain":[0,limits::hdr::MAX_CHANNEL_GAIN],"blend_modes":["normal","multiply","linear_dodge","darken","lighten","difference","subtract"],"unsupported":["normalized adjustments and active filters/effects","knockout","pass-through group grading","HDR output profiles","HDR page/vector delivery","automatic HDR detection","cross-working-space transfer"],"tone_mapping_preserves_source":true});
    capabilities["raw_development"] = json!({
        "command":"raw.develop","algorithm":raw::ALGORITHM,
        "input":"explicit_headerless_Bayer_sensor_buffer","packing":["u8","u16_le","u16_be"],
        "patterns":["rggb","grbg","gbrg","bggr"],"row_padding":true,"max_row_padding_bytes":limits::raw::MAX_ROW_PADDING_BYTES,
        "max_sensor_pixels":raw::MAX_PIXELS,"source_bytes":format!("exact_row_stride_times_height_max_{}_MiB", assets::MAX_IMPORT_BYTES as f64 / (1024.0 * 1024.0)),
        "calibration":"explicit_per_site_black_white_and_row_major_camera_to_linear_srgb_matrix",
        "white_balance":["explicit_gains","measured_neutral_green_normalized"],"exposure_stops":[-i64::from(limits::raw::MAX_EXPOSURE_STOPS),limits::raw::MAX_EXPOSURE_STOPS],
        "interpolation":"bilinear_missing_channels_available_neighbors_renormalized_at_edges",
        "outputs":["srgb8","srgb16","linear_srgb32"],"range":["explicit_clip","preserve_signed_scene_range_for_float"],
        "resolution_ppi":[limits::model::MIN_RESOLUTION_PPI,limits::model::MAX_RESOLUTION_PPI],"source_unchanged":true,"source_pin":"optional_expected_sha256",
        "recipe":"versioned_algorithm_source_hash_capture_and_settings","diagnostics":"sensor_and_output_ranges_clipping_counts",
        "camera_containers":false,"automatic_calibration":false,"lens_correction":true,"noise_detail_controls":true,"corrections_command":"raw.retain",
        "source_retention":"external_original_bytes_not_embedded_in_developed_document"
    });
    capabilities["raw_development"]["retained"] = json!({
        "commands":["raw.retain","raw.reopen","raw.recipe"],"content":"raw","operations":["raw_settings","raw_expand"],
        "algorithm":raw::retained::ALGORITHM,"source":"exact_embedded_sensor_bytes_including_padding",
        "max_source_bytes":raw::retained::MAX_SOURCE_BYTES,"max_recipe_bytes":raw::retained::MAX_RECIPE_BYTES,
        "correction_order":["linear_development","denoise","lens","detail","explicit_output_projection"],
        "lens":"explicit_radial3_tangential2_pull_map_bilinear_linear_light",
        "lens_borders":["clamp","transparent"],"lens_no_fold":format!("global_normalized_Jacobian_perturbation_bound_less_than_{}", limits::raw_corrections::MAX_JACOBIAN_PERTURBATION),
        "denoise":"RGB_range_gated_uniform_local_mean_with_amount","detail":"alpha_weighted_box_unsharp_with_threshold",
        "neighborhood_radius":[1,limits::raw_corrections::MAX_RADIUS],"sidecar":"strict_version2_JSON_source_pinned_sensor_development_only",
        "history":"source_preserving_atomic_settings_edits_snapshots_sessions_undo_redo",
        "expansion":"explicit_raw_expand_to_native_samples","scene_resolution":"independent_from_recipe_output_preference"
    });
    capabilities["sample_precision"] = json!({"content":"samples","depths":["u8","u16","f32"],"channels":["rgba","gray_alpha"],"storage":"little_endian_straight_channel_bytes_as_hex","float_range":[0.0,1.0],"working":"normalized_f64_encoded_srgb","native_edit":"sample_replace","sampling":["nearest","bilinear","area","bicubic","lanczos3"],"tiff":{"options":["depth","channels"],"depths":["u8","u16","f32"],"channels":["rgba","gray_alpha"],"alpha":"unassociated","gray_policy":"exact_neutral_rgb_required","output_profiles":false},"display_preview":"rgba8_quantized_copy","hdr":true,"native_brush_and_mask_bake":false,"native_brush":true,"native_retouch":true,"native_mask_bake":false,"high_depth_import":true,"import":{"command":"sample.import","formats":["png","tiff"],"png_depths":["u8","u16"],"tiff_depths":["u8","u16","f32"],"source_unchanged":true,"profiles":false,"orientation_transforms":false,"associated_alpha":false,"multiple_images":false,"max_inline_pixels":model::MAX_STORED_PIXELS,"max_source_bytes":assets::MAX_IMPORT_BYTES,"max_tiff_padded_tile_bytes":limits::sample_import::MAX_TIFF_PADDED_BYTES},"conversion":{"operation":"sample_convert","depths":["u8","u16","f32"],"channels":["rgba","gray_alpha"],"gray_policies":["require_neutral","encoded_luma","linear_luminance"],"legacy_inline_rgba8_promotion":true,"hidden_color":"converted_without_alpha_zero_discard","profiles":false,"hdr":true},"encodings":["encoded_srgb","linear_srgb","profiled_rgb"],"linear_float_color_range":"finite_signed_binary32","linear_alpha_range":[0.0,1.0],"source_preserved":true,"geometry_coverage":"existing_f32_and_byte_coverage"});
    capabilities["supported"]["raster"]
        .as_array_mut()
        .unwrap()
        .extend([
            json!("retained_typed_sample_grids"),
            json!("native_sample_replace"),
        ]);
    capabilities["supported"]["exports"]
        .as_array_mut()
        .unwrap()
        .extend([
            json!("tiff_explicit_depth_gray_or_rgba"),
            json!("native_vector_editable_subset"),
        ]);
    capabilities["features"]["bmp_import"] = json!(true);
    capabilities["features"]["tga_import"] = json!(true);
    capabilities["features"]["gif_import"] = json!(true);
    capabilities["image_io"]["formats"] = json!(["png", "jpeg", "tiff", "bmp", "tga", "gif"]);
    capabilities["image_io"]["tiff"]["alpha"] = json!(["unassociated", "associated_rgba8"]);
    capabilities["image_io"]["tiff"]["associated_alpha_lossless"] = json!(false);
    capabilities["image_io"]["bmp"] = json!({"import":"infoheader40_rgb24_rgb32_unused_padding","export":"rgb24_bottom_up","rows":"aligned4_top_or_bottom_input","alpha":"explicit_matte_for_transparent_output","profiles":"declared_input_only","metadata":"explicit_strip_required","density":"integer_pixels_per_meter"});
    capabilities["image_io"]["tga"] = json!({"import":"raw_rle_rgb24_rgba32_gray8_grayalpha16","origins":"all_four_to_top_left","alpha":"descriptor_and_extension_0_1_2_3_4","export":"rgba32_top_left_extension_useful_alpha","profiles":"declared_input_only","metadata":"explicit_strip_required","density":false});
    capabilities["image_io"]["gif"] = json!({"import":"still_or_sequence","compression":"variable_width_lzw_2_to_8_initial_12_max_deferred_clear","export":"exact_sorted_local_palettes_literal_lzw_resets","palette_entries":limits::image_io_gif::MAX_PALETTE_ENTRIES,"maximum_delay_centiseconds":limits::image_io_gif::MAX_DELAY_TICKS,"alpha":"binary_one_reserved_entry_in_all_frames_if_any_transparency","quantization":false,"timing":format!("exact_centiseconds_0_to_{}", limits::image_io_gif::MAX_DELAY_TICKS),"plays":[0,limits::image_io_gif::MAX_PLAYS],"background":["transparent","logical_screen"],"default_background":"transparent","disposal":["keep","background","previous"],"interlaced_input":true,"metadata":"selected_envelope_comment","profiles":"declared_still_input_only_no_embedded_profile","density":false,"animation_import":"sequence.import","still_import":"reject_multiple_frames"});
    capabilities["publication"]["formats"] = json!([
        "pdf", "png", "apng", "jpeg", "tiff", "bmp", "tga", "gif", "svg", "snapshot"
    ]);
    capabilities["supported"]["artboards"]["formats"] =
        json!(["png", "jpeg", "tiff", "bmp", "tga", "svg_vector"]);
    capabilities["supported"]["artboards"]["scope"] = json!({
        "field":"frame.scope", "default":"subtree", "choices":["subtree","scene"],
        "subtree":"owned_children_in_local_coordinates;ancestor_context_excluded",
        "scene":"shared_vector_layer_tree_in_translated_viewport;no_artwork_duplication",
        "scene_requirements":"root_artboard_without_children_background_or_appearance_modifiers;translation_only",
        "scene_editing":"move_resize_duplicate_or_remove_viewport_without_changing_artwork",
        "scene_resources":"complete_scene_per_selected_view;existing_batch_limits",
        "scene_filters":"evaluate_in_each_output_viewport",
        "persistence":"optional_scope_omitted_for_legacy_subtree_snapshots"
    });
    capabilities["render_quality"]["formats"] =
        json!(["png", "apng", "jpeg", "tiff", "bmp", "tga", "gif"]);
    capabilities["metadata"]["formats"]
        .as_array_mut()
        .unwrap()
        .push(json!("gif_comment"));
    capabilities["metadata"]["orientation"] = json!(
        "top_left_output_bmp_and_tga_origins_normalized_other_unsupported_input_orientation_rejected"
    );
    capabilities["sequences"]["additional_formats"] = json!({"gif":"exact_palette_binary_alpha_centisecond_timing","ordered_images":["bmp","tga","gif_single_frame"]});
    capabilities["sequences"]["imports"]
        .as_array_mut()
        .unwrap()
        .extend([
            json!("gif_palette_binary_alpha_centisecond_timing"),
            json!("explicit_ordered_bmp_tga_gif_stills"),
        ]);
    capabilities["sequences"]["exports"]
        .as_array_mut()
        .unwrap()
        .push(json!("gif_full_canvas_exact_palette_binary_alpha"));
    capabilities["supported"]["exports"]
        .as_array_mut()
        .unwrap()
        .extend([
            json!("bmp_rgb24_explicit_matte"),
            json!("tga_rgba32_useful_alpha"),
            json!("gif_exact_palette_still_or_sequence"),
        ]);
    capabilities["device_color_conversion"] = json!({"command":"color.convert","spaces":["rgb","gray","cmyk","lab"],"max_samples":limits::profiles::MAX_CONVERSION_SAMPLES,"intents":["relative_colorimetric","absolute_colorimetric","perceptual","saturation"],"untagged":["reject","assume_srgb_for_rgb"],"lookup_inputs":[1,3,4],"lookup_interpolation":"continuous_tensor","intent_contract":"declared_directional_tables;matrix_gray_curve_fallback;absolute_media_white_scaling;v4_reference_medium_bridge;v2_direct_PCS;no_optional_BPC","profile_bytes_retained":true,"gamut":["off","if_available","required"],"gamut_coordinates":"independent_colourimetric_source_to_destination_relative_PCS","document_policy_integration":"explicit_per_paint_intent_and_source_profile;RGB_output_profile_or_explicit_print_target"});
    capabilities["managed_swatches"] = json!({"declaration":"device","edit":"swatch_profile","actions":["assign","convert"],"source_spaces":["rgb","gray","cmyk","lab"],"intent":"retained_per_definition","preview":"profiled_source_to_encoded_srgb","tint":"source_device_components_before_conversion","assignment":"retain_numbers_change_interpretation","conversion":"change_numbers_through_explicit_profile_connection","native_pdf":"exact_deduplicated_ICCBased_profiles_and_explicit_RI;D50_Lab;PDF_2_0_explicit_BPC_OFF","calibrated_pdf":"document_output_profile_in_page_and_isolated_group_blending;explicit_DefaultRGB_srgb;untagged_CMYK_rejected","native_prepress":"explicit_source_profile_to_selected_print_profile;print_intent_governs","overprint":"profiled_process_PDF_overprint_rejected;spot_overprint_retained","display_vector":"explicit_swatch_bake_required","source_retention":"snapshot_receipts_and_durable_history","document_policy":"explicit_source_encodings;per_definition_relative_default;output_profile_for_calibrated_RGB_delivery;export_intent_for_print_separation","gamut_integration":true});
    capabilities["swatches"]["declaration_spaces"] =
        json!(["srgb", "gray", "cmyk", "lab", "device"]);
    capabilities["swatches"]["profile_driven_non_rgb_conversion"] =
        json!("explicit_device_declarations");
    capabilities["vector_canvas"] = json!({"operation":"vector_canvas","actions":["set","unit","clear"],"units":["px","pt","pc","mm","cm","in"],"canonical_coordinates":"logical_pixels_binary64","unit_conversion":"exact_rational_then_one_binary64_round","origin":"finite_nonzero_supported","size_range_px":[limits::vector_canvas::MIN_LOGICAL_SIZE,model::MAX_DIMENSION],"preview_storage":"ceiling_of_logical_size","fractional_edge":"area_coverage_except_none_point_sampling","artboards":"optional_logical_size_with_ceiling_cache","process_spaces":["rgb","cmyk"],"colour_semantics":"typed_paints_unchanged;CMYK_pages_require_native_or_profile_managed_inks","unit_changes_preserve_artwork":true,"svg":"physical_units_and_logical_viewBox","pdf":"physical_fractional_page_and_translated_evaluation_copy","source_unchanged":true});
    capabilities["features"]["native_import"] = json!(true);
    capabilities["supported"]["imports"]
        .as_array_mut()
        .unwrap()
        .extend([
            json!("layered_rgb8_pixel_subset"),
            json!("layered_large_rgb8_pixel_subset"),
        ]);
    capabilities["supported"]["exports"]
        .as_array_mut()
        .unwrap()
        .extend([
            json!("layered_rgb8_pixel_subset"),
            json!("layered_large_rgb8_pixel_subset"),
        ]);
    capabilities["publication"]["formats"]
        .as_array_mut()
        .unwrap()
        .extend([
            json!("layered"),
            json!("layered_large"),
            json!("native_vector"),
        ]);
    capabilities["layered_interchange"] = json!({"status":"basic_interchange_verified","import":"layered.import","export_format":"layered","file_version":1,"additional_file_versions":[2],"large_export_format":"layered_large","dimensions_by_version":{"standard":limits::layered::MAX_STANDARD_DIMENSION,"large":model::MAX_DIMENSION},"extended_status":"partial_uncredited","mode":"rgb8","layer_order":"bottom_to_top","layer_sources":["inline_raster","encoded_srgb_rgba8_samples"],"import_compression":["raw","rle","zip","zip_prediction"],"export_compression":"rle;raw_available_in_Rust_library","preserved":["original_layer_pixels_including_hidden_RGB","integer_extents","names","visibility","byte_opacity","byte_fill_opacity","whole_layer_lock"],"source_changed":false,"canvas_pixels":layered::MAX_CANVAS_PIXELS,"stored_pixels":model::MAX_STORED_PIXELS,"file_bytes":layered::MAX_FILE_BYTES,"maximum_layers":model::MAX_ITEMS,"profile_policy":"exact_builtin_srgb;explicit_convert_srgb_for_other_profiles;explicit_assume_srgb_for_untagged","merged_preview":"white_matted_RGB_with_separate_alpha;8bit_unmatting_loss;layers_remain_original","metadata":"explicit_strip_if_descriptive_metadata_present","incoming_metadata":"strict_known_inactive_records_with_omission_receipts","descriptor_limits":{"bytes":limits::layered_descriptor::MAX_BYTES,"depth":limits::layered_descriptor::MAX_DEPTH,"values":limits::layered_descriptor::MAX_NODES,"container_entries":limits::layered_descriptor::MAX_CONTAINER},"density_units":"fixed_values_always_ppi;unit_selectors_are_display_only","groups":{"modes":["normal_isolated","normal_pass_through"],"empty":true,"ancestor_levels":limits::scene::MAX_DEPTH,"serialized_records":limits::layered::MAX_SERIALIZED_RECORDS,"transforms":"absolute_integer_source_placements;imported_groups_identity","open_state":"omitted_UI_metadata","unsupported":["non_normal_group_blends","group_fill_opacity","knockout","cached_group_pixel_extents","layer_role_containers"]},"masks":{"authored_gray8":true,"independent_bounds":true,"constant_empty_planes":true,"controls":["linked","enabled","outside_black_or_white","exact_byte_density"],"sampling":"nearest_integer_translation","unsupported":["nonzero_native_feather","obsolete_invert_flag","derived_masks","combined_real_vector_masks","implicit_resampling"]},"empty_layer_names":"encoded_exactly;native_consumers_may_generate_names;receipt_lists_empty_name_source_ids","unsupported":["large_axes_above_32768","empty_pixel_layers","native_mask_feather","derived_or_combined_masks","unmapped_incoming_text_layout","unsupported_embedded_source_semantics","non_normal_blends","extra_channels","nonempty_guides","unknown_appearance_records"],"checkpoint":"raster.interchange.basic"});
    capabilities["layered_interchange"]["empty_external_link_tables"] = json!({"import":true,"framing":"version_specific_32_or_64_bit_length","receipt":"omitted_nonappearance_records","nonempty_references":"unsupported"});
    capabilities["layered_interchange"]["embedded_objects"] = json!({
        "import":"explicit_policy_required","export":"explicit_policy_required",
        "export_policy":{"layered_options":{"embedded_objects":"native_reconstruction"}},
        "export_source":"independent_native_rgb8_large_container_per_placement;affine_corners;original_source_unchanged",
        "export_reconstruction":"native_consumer_controls_sampling_and_coverage;source_sampling_and_surface_scale_are_receipt_only",
        "export_source_record_version":7,
        "policy":{"sampling":["nearest","bilinear","area","bicubic","lanczos3"],"sharing":["independent_copies"]},
        "source":"retained_normalized_editable_rgb8_layered_document","native_source_bytes":"remain_in_original_input;sha256_in_receipt",
        "placement":"validated_affine_corners_and_source_size_density","cached_pixels":"validated_and_hashed;never_used_as_editable_source",
        "native_composite_equality":false,"profile_policy":"applies_to_every_nested_document",
        "source_record_versions":[1,2,3,4,5,6,7,8],"empty_external_link_list":"omitted_with_receipt;nonempty_unsupported",
        "limits":{"nesting":objects::MAX_NESTING,"decoded_items":limits::layered::MAX_DECODED_ITEMS,"decoded_sample_bytes":layered::MAX_DECODED_BYTES,
            "source_snapshot_bytes":model::MAX_DOCUMENT_BYTES,"aggregate_snapshot_allocation_bytes":layered::MAX_DECODED_BYTES},
        "unsupported":["external_links","aliases","selected_layer_comps","animation","active_warps","perspective","non_layered_sources","unknown_descriptor_fields"]
    });
    capabilities["layered_interchange"]["text_diagnostics"] = json!({
        "status":"structural_diagnostics;explicit_bounded_point_import_available",
        "error_details":"native_text_requirements;first_local_record_and_its_selected_global_story;not_a_complete_import",
        "checks":["descriptor_framing","bounded_text_data_syntax","matching_local_text_sources","utf16_run_boundaries","explicit_run_font_references","global_tag_framing","explicit_global_story_index","selected_global_story_run_references","local_global_text_comparison","selected_global_frame_reference","point_or_rectangular_frame_geometry","separate_frame_transform","first_baseline_control","explicit_frame_layout_control_types","known_character_control_types","local_global_character_control_comparison","known_paragraph_control_types","local_global_paragraph_control_comparison"],
        "limits":{"record_bytes":limits::layered_text::MAX_RECORD_BYTES,"data_values":limits::layered_text_data::MAX_NODES,"data_depth":limits::layered_text_data::MAX_DEPTH,"container_entries":limits::layered_text_data::MAX_CONTAINER,"string_bytes":limits::layered_text_data::MAX_STRING_BYTES,"runs":limits::layered_text::MAX_RUNS,"referenced_fonts":limits::fonts::MAX_FONTS},
        "layout_semantics_validated":false,"whole_file_validated":false,"cached_pixel_fallback":false,
        "global_story":{"versions":[14],"text_source":"global_story_when_present;local_record_otherwise","style_semantics_validated":false,"other_stories_validated":false,"other_layer_references_validated":false,
            "limits":{"data_bytes":limits::layered_text_data::MAX_GLOBAL_BYTES,"data_values":limits::layered_text_data::MAX_GLOBAL_NODES,"data_depth":limits::layered_text_data::MAX_GLOBAL_DEPTH,"container_entries":limits::layered_text_data::MAX_GLOBAL_CONTAINER,"tagged_records":limits::layered_text::MAX_TAGGED_RECORDS,"stories":limits::model::MAX_ITEMS,"characters":limits::text::MAX_TEXT_CHARS,"runs":limits::layered_text::MAX_RUNS,"referenced_fonts":limits::fonts::MAX_FONTS},
            "frame":{"source":"independent_global_frame_reference","shapes":["point","rectangle"],"frame_resources":limits::model::MAX_ITEMS,"selected_frames":1,"coordinate_bound":limits::model::MAX_COORDINATE,"first_baseline_metrics":["fixed","ascent","cap_height","leading","x_height"],"layout_controls":{"integer_counts":["row_count","column_count"],"finite_source_distances":["row_gap","column_gap","spacing"],"missing_values_defaulted":false,"layout_ranges_validated":false},"remaining_properties_validated":false,"local_geometry_consistency_validated":false,"other_frames_validated":false,"layout_semantics_validated":false}},
        "font_bindings":{"argument":"text_fonts","maximum_faces":fonts::MAX_FONTS,"names":"exact_case_sensitive_unique_unicode_postscript_face_name","resources":"content_pinned_font_and_retained_license;referenced_only","source":"selected_global_story_or_local_record_if_absent","digest":"compact_sorted_key_json_of_referenced_face_name_to_font_descriptor_map","scope":"first_native_text_record_only;not_complete_import","source_font_files_identified":false,"system_font_lookup":false},
        "character_controls":{"scope":"explicit_observed_controls_only;unknown_fields_uninterpreted","comparison":"matching_text_utf16_spans;independent_run_partitions;resolved_face_names","missing_controls":"reported_without_defaults","run_fingerprints":"known_controls_and_boundaries_only;not_complete_style_identity","paint":"type_1_four_finite_source_components;typed_named_class;unknown_classes_modes_and_nested_fields_reported;no_color_conversion","legacy_controls":"global_kerning_decoration_digit_set_and_joining_codes_separate_from_local_flags;no_conversion","additional_controls":"language_baseline_direction_character_alignment_spacing_compression_alternate_forms_diacritics_stylistic_sets;raw_source_values","annotation_and_paint_controls":"rotation_underline_offset_legacy_features_annotations_inline_offsets_character_spacing_fill_stroke_order_overprint_width_miter_dash_visibility_direction_mark_position;diagnostics_only","source_dash_values":limits::layered_text::MAX_DASH_VALUES,"annotation_scale_record":"typed_numeric_value;unknown_nested_fields_reported","unmapped_fields_reported":limits::layered_text::MAX_UNMAPPED_FIELDS,"complete_style_semantics_validated":false},
        "paragraph_controls":{"scope":"observed_controls_with_explicit_source_style_resolution;no_invented_defaults","comparison":"matching_text_utf16_spans;independent_run_partitions;source_numeric_values","triples":"exactly_three_finite_numbers;no_justification_conversion","legacy_hyphen_limit":"global_limit_and_local_code_reported_separately;conversion_unvalidated","additional_controls":"leading_direction_paragraph_direction_line_breaking_order_list_tier_joining_width;raw_source_codes","hanging_punctuation":"global_code_and_local_boolean_separate;no_conversion","missing_property_containers":"counted_without_defaulting","paragraph_boundaries":"carriage_return_run_end_counts_only;semantics_unvalidated","layout_controls":"hyphenation_zone_preference_single_word_justification_inline_grouping_line_keeping_repeated_characters_tab_width_justification_method_drop_cap_multiplier_composer_code;diagnostics_only","preset_references":"line_breaking_spacing_list;unsigned_index_or_typed_nil;direct_source_slots_and_names;absent_distinct;definitions_unvalidated;no_defaulting","legacy_preset_codes":"local_line_breaking_and_spacing_codes;separate_from_global_references;conversion_unvalidated","preset_table_records":limits::layered_text_preset_records::MAX_RECORDS,"preset_name_utf8_bytes":limits::layered_text_preset_records::MAX_NAME_BYTES,"reported_preset_records":limits::layered_text_preset_records::MAX_REPORTED,"preset_name_preview_characters":limits::layered_text_preset_records::PREVIEW_CHARACTERS,"list_controls":"item_suppression_and_number_restart;diagnostics_only","unmapped_fields_reported":limits::layered_text::MAX_UNMAPPED_FIELDS,"complete_style_semantics_validated":false},
        "shape_owner_labels":"at_most_eight_bounded_untrusted_identifiers;not_geometry_validation",
        "compatibility_markers":"optional_boolean_and_bounded_enum_source_data;untrusted;semantics_not_validated",
        "editable_text_import":true,"editable_text_import_scope":"explicit_point_subset;see_text_import","editable_text_export":true
    });
    capabilities["layered_interchange"]["text_import"] = json!({
        "status":"explicit_bounded_engine_layout_reconstruction;original_extended_checkpoint_open",
        "option":"text_fonts.reconstruction","reconstruction":"engine_layout",
        "sources":["explicit_local_authoring_without_global_table","explicit_selected_global_authoring"],
        "frames":"single_line_horizontal_left_aligned_point;fixed_zero_baseline;visible_unwrapped_nominal_1x1_frame",
        "fonts":"required_content_pinned_static_outline_fonts_and_retained_licenses;exact_face_names;no_installed_lookup",
        "styles":["utf16_ranges","opaque_solid_rgb_quantized_to_eight_bits","size","tracking","uniform_explicit_leading","character_scales","baseline_shift","kern_liga_dlig"],
        "references":"every_global_story_and_frame_exactly_once;no_stale_local_fallback",
        "language_tags":["en-US","en-GB","fr","tr"],"language_policy":"explicit_source_codes_only;absent_unspecified;other_codes_fail",
        "profile_conversion":"explicit_convert_srgb;authored_components_before_rgb8_quantization;source_profile_per_nested_document",
        "rendering":{"option":"text_fonts.rendering","choice":"engine","known_source_modes":["none","crisp","strong","smooth","sharp"],"controls":"descriptor_local_and_explicit_selected_global_values_must_agree;missing_global_values_not_inferred","differences":"engine_edge_smoothing_and_fractional_spacing;source_controls_in_receipt","native_rendering_equivalence":false},
        "inheritance":{"source":"explicit_global_character_and_paragraph_references","root":"must_equal_source_declaration","precedence":"root_then_paragraph_character_attributes_then_character_style_then_local_overrides","max_reference_depth":limits::layered_text::MAX_REFERENCE_DEPTH,"max_resolved_character_runs":limits::layered_text::MAX_RUNS,"max_property_references":limits::layered_text::MAX_PROPERTY_REFERENCES,"named_style_links":"resolved_to_independent_editable_ranges","local_cache":"may_be_sparse;never_authoritative","unsupported":["deeper_chains","unmapped_auxiliary_tables","local_only_inheritance","missing_or_conflicting_roots"]},
        "source_fonts":{"scope":"global_font_resource_provenance","table_records":limits::layered_text_font_records::MAX_RECORDS,"selected_records":limits::layered_text_font_records::MAX_SELECTED,"version_utf8_bytes":limits::layered_text_font_records::MAX_VERSION_BYTES,"technology_codes":[0,1],"version":"optional_source_text;not_font_file_identity;chosen_version_not_implicitly_matched","validation":"selected_records_in_diagnostics;entire_table_for_editable_import","retention":"import_receipt_only;chosen_font_controls_delivery","unknown_semantics":"explicit_rejection"},
        "caches":"decoded_and_hashed;never_source","native_layout_equality":false,
        "unsupported":["unmapped_controls_or_inheritance","general_native_saved_global_tables","paragraph_or_multiline_text","linked_frames","other_features","manual_or_optical_global_kerning","warps","separate_frame_transforms","legacy_markers","unknown_or_conflicting_rendering_controls","variable_fonts","missing_glyphs_or_requested_features"],
        "contract":"docs/LAYERED_TEXT_IMPORT.md"
    });
    capabilities["limits"]["resolution_ppi"] = json!([
        limits::model::MIN_RESOLUTION_PPI,
        limits::model::MAX_RESOLUTION_PPI
    ]);
    capabilities["limits"]["default_resolution_ppi"] = json!(limits::model::DEFAULT_RESOLUTION_PPI);
    capabilities["reconstruction"]["max_index_coordinate"] =
        json!(limits::resample::MAX_INDEX_COORDINATE);
    capabilities["raw_development"]["calibration_limits"] = json!({
        "camera_coefficient":[-i64::from(limits::raw::MAX_CAMERA_COEFFICIENT),limits::raw::MAX_CAMERA_COEFFICIENT],
        "minimum_absolute_determinant":limits::raw::MIN_CAMERA_DETERMINANT,
        "white_balance_component":[0,limits::raw::MAX_WHITE_BALANCE_COMPONENT],
        "component_minimum_exclusive":true,
        "effective_white_balance_gain":[1.0/f64::from(limits::raw::MAX_WHITE_BALANCE_GAIN),limits::raw::MAX_WHITE_BALANCE_GAIN],
        "max_source_bytes":assets::MAX_IMPORT_BYTES
    });
    capabilities["raw_development"]["retained"]["correction_limits"] = json!({
        "threshold":[0,limits::raw_corrections::MAX_THRESHOLD],
        "denoise_amount":[0,1],"detail_amount":[0,limits::raw_corrections::MAX_DETAIL_AMOUNT],
        "focal_length":[limits::raw_corrections::MIN_FOCAL_LENGTH,limits::raw_corrections::MAX_FOCAL_LENGTH],
        "radial_coefficient":[-limits::raw_corrections::MAX_RADIAL_COEFFICIENT,limits::raw_corrections::MAX_RADIAL_COEFFICIENT],
        "tangential_coefficient":[-limits::raw_corrections::MAX_TANGENTIAL_COEFFICIENT,limits::raw_corrections::MAX_TANGENTIAL_COEFFICIENT],
        "jacobian_perturbation_maximum_exclusive":limits::raw_corrections::MAX_JACOBIAN_PERTURBATION
    });
    capabilities["geometry_limits"] = json!({
        "minimum_rectangle_extent":limits::geometry::MIN_RECTANGLE_EXTENT,
        "minimum_ellipse_radius":limits::geometry::MIN_ELLIPSE_RADIUS,
        "cubic_linear_threshold":limits::geometry::CUBIC_LINEAR_THRESHOLD,
        "threshold_scope":"legacy_binary64_derivative_coefficient_branch_for_geometric_bounds;not_an_error_certificate"
    });
    capabilities["snapping"]["grid_spacing"] =
        json!([limits::snapping::MIN_GRID_SPACING, model::MAX_COORDINATE]);
    capabilities["snapping"]["minimum_guide_length"] = json!(limits::snapping::MIN_GUIDE_LENGTH);
    capabilities["volumes"]["rotation_degrees"] = json!([
        -i64::from(limits::volumes::MAX_ROTATION),
        limits::volumes::MAX_ROTATION
    ]);
    capabilities["volumes"]["normalization_norm"] = json!([
        limits::volumes::MIN_DIRECTION_NORM,
        limits::volumes::MAX_DIRECTION_NORM
    ]);
    capabilities["volumes"]["minimum_camera_near"] = json!(limits::volumes::MIN_CAMERA_NEAR);
    capabilities["volumes"]["maximum_camera_far"] = json!(limits::volumes::MAX_CAMERA_FAR);
    capabilities["text_limits"] = json!({
        "frame_extent":[limits::text::MIN_FRAME_EXTENT,model::MAX_COORDINATE],
        "leading":[limits::text::MIN_LEADING,limits::text::MAX_LEADING],
        "font_size":[limits::text::MIN_FONT_SIZE,limits::text::MAX_FONT_SIZE],
        "tracking":[-i64::from(limits::text::MAX_TRACKING),limits::text::MAX_TRACKING],
        "language_bytes":limits::text::MAX_LANGUAGE_BYTES,
        "layout_overflow_tolerance":limits::text::LAYOUT_OVERFLOW_TOLERANCE,
        "layout_tolerance_scope":"fit_and_ink_overflow_comparisons;not_glyph_position_accuracy"
    });
    capabilities["paragraph_flow"]["layout_limits"] = json!({
        "slot_extent":[limits::text::MIN_FRAME_EXTENT,model::MAX_COORDINATE],
        "minimum_column_extent":limits::text::MIN_FRAME_EXTENT,
        "gutter":[0,model::MAX_COORDINATE],
        "spacing_and_indents":[0,model::MAX_COORDINATE],
        "first_indent":[-model::MAX_COORDINATE,model::MAX_COORDINATE],
        "list_gap":[0,model::MAX_COORDINATE],
        "layout_overflow_tolerance":limits::text::LAYOUT_OVERFLOW_TOLERANCE
    });
    capabilities["text_character_geometry"] = json!({"style_controls":["horizontal_scale","vertical_scale","baseline_shift"],"scale_range":[limits::text::MIN_CHARACTER_SCALE,limits::text::MAX_CHARACTER_SCALE],"scale_default":1,"baseline_shift_range":[-(model::MAX_COORDINATE as i64),model::MAX_COORDINATE as i64],"baseline_shift_default":0,"baseline_shift":"positive_moves_up_in_local_glyph_coordinates;does_not_change_line_spacing","tracking":"local_pixels_added_after_horizontal_glyph_scaling","metrics":"vertical_scale_applies_to_font_metrics_and_first_baseline_heights","contexts":["ordinary_frames","paths","linked_stories","generated_list_markers","generated_hyphens"],"retained":true,"native_delivery":"explicit_scales_and_shift;tracking_compensated_for_native_horizontal_scale;recipient_layout_not_identical"});
    capabilities["text_first_baseline"] = json!({"option":"text.frame.first_baseline","metrics":["ascent","cap_height","x_height","leading","fixed"],"minimum":format!("finite_0_to_{}_local_pixels", model::MAX_COORDINATE),"default":"existing_font_ascent_placement","font_metrics":"contributing_first_line_instances_and_base_style;cap_and_x_height_require_positive_font_metrics;no_fallback_guess","placement":"uniform_translation_of_all_lines;frame_origin_and_clip_unchanged","retained":true,"native_layered_delivery":"fixed_zero_unwrapped_points_only","unsupported":["path_text","character_positioning","linked_story_controls","other_native_first_baseline_controls"]});
    capabilities["text_positioning"] = json!({"option":"text.frame.positioning","indices":"Unicode_scalars;absolute_positions_at_grapheme_boundaries","max_positions":text::MAX_TEXT_CHARS,"coordinate_bound":model::MAX_COORDINATE,"origin":"local_alphabetic_baseline;default_zero","absolute":["x","y"],"relative":["dx","dy"],"anchors":["start","middle","end"],"chunks":"absolute_position_starts_independent_shaping_and_anchor_chunk","relative_inside_cluster":"accumulated_for_next_cluster","continuation":"unanchored_pen","edit":"start_entry_follows_first_replacement;removed_entries_discarded;later_indices_shift","native_layered_delivery":"unsupported","unsupported":["wrapped_text","paragraph_breaks","path_text","bidi_layout","non_left_frame_alignment","paragraph_leading","first_baseline"]});
    capabilities["layered_interchange"]["text_delivery"] = json!({
        "status":"explicit_native_layout_reconstruction;bounded_subset",
        "option":"layered_options.text",
        "reconstruction":"native_layout",
        "shape_owner":format!("required_consumer_geometry_identifier;1_to_{}_ASCII_letters_or_digits;unrecognized_labels_may_fail_geometry", limits::layered_text::MAX_SHAPE_OWNER_BYTES),
        "frames":["horizontal_left_aligned_ltr_point","horizontal_left_aligned_ltr_paragraph"],
        "fonts":"explicit_pinned_local_font_root;unique_Unicode_PostScript_name;static_TrueType_outline_faces;no_embedding_or_installed_font_lookup",
        "styles":["utf16_character_ranges","size","solid_opaque_rgb","tracking","explicit_leading","horizontal_scale","vertical_scale","baseline_shift","kern_liga_dlig_boolean_controls"],
        "placement":"affine_world_matrix;point_origin_includes_source_first_baseline;paragraph_box_local",
        "tracking":format!("compensated_for_horizontal_scale;magnitude_at_most_{}_integer_thousandths_em;nearest_ties_away_from_zero;changed_values_in_receipt", i32::MAX),
        "caches":"separate_engine_rendered_pixels;never_editable_source",
        "native_layout_equality":false,"recipient_font_file_identity_pinned":false,"editable_import":true,"editable_import_scope":"explicit_point_subset",
        "limits":{"characters":text::MAX_TEXT_CHARS,"runs":limits::layered_text::MAX_RUNS,"paragraphs":limits::layered_text::MAX_RUNS,"font_faces_across_nested_sources":fonts::MAX_FONTS,"text_record_bytes":limits::layered_text::MAX_RECORD_BYTES},
        "unsupported":["font_fallback","variable_fonts","non_TrueType_outlines","unmapped_language_tags","text_paths","character_positioning","unicode_bidi","non_left_alignment","character_alpha_or_non_solid_paint","other_features","point_clipping","paragraph_visible_overflow","explicit_first_baseline_controls_except_fixed_zero_points"],
        "language_tags":["en-US","en-GB","fr","tr"],"language_policy":"exact_tags_only;no_region_or_default_inference"
    });
    capabilities["native_sample_store_library"] = json!({
        "status":"integrated_native_import_local_patch_edits_and_bounded_view_rendering;scale_gate_open",
        "module":"sample_store", "manifest_version":1,
        "tile_edge":sample_store::TILE_EDGE, "max_pixels":sample_store::MAX_PIXELS,
        "max_tiles":sample_store::MAX_TILES, "max_region_pixels":sample_store::MAX_REGION_PIXELS,
        "depths":["u8","u16","f32"], "channels":["rgba","gray_alpha"],
        "candidate_edits":"pure_copy_on_write;unchanged_blocks_shared",
        "candidate_transfer":{"version":1,"scope":"rust_library_and_explicit_block_mode_review_documents","pending":"sorted_unique_exact_typed_blocks_as_lowercase_hex","budget":"caller_required_unique_decoded_block_bytes_including_headers;separate_parse_and_live_memory_limits_required","preparation":"pure;external_dependencies_require_explicit_verification"},
        "publication":"explicit_create_only_verified_immutable_blocks;complete_orphans_retained",
        "interpretation":"native_type_and_encoding_bound;ICC_profile_is_separate_document_metadata",
        "cli_storage_limits_changed":true, "streaming_import":true,
        "streaming_import_formats":["noninterlaced_png_to_native_blocks","adam7_png_passes_to_native_blocks","tiff_chunk_bands_to_native_blocks"],
        "buffered_import_formats":[],
        "import_memory":"encoded_source_and_pending_blocks_retained;rows_or_passes_or_chunk_bands_avoid_separate_complete_decoded_and_normalized_frames;Adam7_retains_all_unfinished_blocks_and_one_coverage_bit_per_pixel;TIFF_chunk_band_size_is_source_defined",
        "png_import_checksums":"chunk_CRC_and_zlib_Adler32_required_before_publication",
        "document_history_integration":true, "render_integration":true,
        "content":"stored_samples", "resource_binding":"asset_root",
        "import":{"command":"sample.import","opt_in":"storage.store_root","workspace_opt_in":"storage:{}","max_decoded_bytes":sample_import::MAX_NATIVE_DECODED_BYTES},
        "retained_edits":{"operation":"sample_replace","operations":["sample_replace","retouch","brush_stroke"],"max_patches":stored_samples::MAX_PATCHES,"max_aggregate_patch_pixels":stored_samples::MAX_PATCH_PIXELS,"writes_files":false,"snapshot":"immutable_base_manifest_plus_exact_native_patch_bytes"},
        "block_edits":{"storage_version":2,"migration_operation":"sample_storage_migrate","default_import_storage_version":1,"operations":["sample_replace","retouch","brush_stroke"],"maximum_pending_document_bytes":stored_samples::MAX_PENDING_BYTES,"lifetime_patch_limit":false,"pure_library_preparation":true,"commit":"CLI_and_MCP_document_edit_and_session_commit_publish_immutable_blocks_before_durable_state","review":"staged_blocks_in_memory;included_document_has_bounded_explicit_transfer","history":"current_manifest_only;old_states_and_receipts_preserved","full_storage_milestone_verified":false},
        "render_cache":{"scope":"one_prepared_source","max_decoded_pixels":limits::stored_samples::CACHE_PIXELS,"maximum_source_decoding_passes":limits::stored_samples::MAX_SOURCE_DECODING_PASSES},
        "output_limits_changed":true, "large_output_opt_in":"render_options.evaluation:tiled",
        "unsupported":["stored_sample_convert","stored_sample_profile_edits","native_automatic_repair_and_mask_bake","native_ink_separations","layered_pixel_export","structural_SVG_PDF_export"],
        "full_dependency_verification":["sample_replace","retouch","brush_stroke","visible_render_sources","document.check_resources","verified_transfer","job_admission_and_execution"]
    });
    capabilities["sample_precision"]["contents"] = json!(["samples", "stored_samples"]);
    capabilities["sample_precision"]["import"]["native_storage"] = json!({
        "opt_in":"storage.store_root", "max_source_pixels":sample_store::MAX_PIXELS,
        "max_native_bytes":sample_import::MAX_NATIVE_DECODED_BYTES,
        "output_limits_changed":true, "large_output_opt_in":"render_options.evaluation:tiled", "contract":"native_sample_store_library"
    });
    capabilities["render_quality"]["evaluation"] = json!({
        "default":"whole", "modes":["whole","tiled"],
        "whole_evaluation_pixels":render::MAX_RENDER_PIXELS,
        "tiled_evaluation_pixels":render::tiled::MAX_PIXELS,
        "tile_edge":render::tiled::EDGE,
        "tile_edge_semantics":format!("maximum_evaluation_edge;{}_for_at_least_{}_expanded_items", limits::render_spatial::EDGE, limits::render_spatial::MIN_ITEMS),
        "spatial_index":{"minimum_items":limits::render_spatial::MIN_ITEMS,"edge":limits::render_spatial::EDGE,"maximum_memberships":limits::render_spatial::MAX_REFERENCES,
            "bounds":"conservative_transformed_controls;ancestor_union;authored_order_and_clipping_bindings",
            "coverage_cache_pixels":limits::render_coverage_cache::MAX_PIXELS,"lifetime":"one_prepared_render;rebuild_for_every_revision",
            "work":"visited_tiles_and_preparation;existing_total_work_and_memory_limits"},
        "scene_preparation":"once_per_render;no_persistent_cache",
        "source_cache":"bounded_native_tiles;inline_native_decoded_once;byte_asset_taps_converted_on_demand",
        "traversal":{"neighborhood_document_units":render::traversal::NEIGHBORHOOD_UNITS,
            "order":"top_to_bottom_bands;neighboring_small_tiles;fixed_source_cache_and_decode_budget",
            "native_strip_rows":format!("bounded_by_{}MiB;independent_of_composition_tile_edge", limits::sample_tiff_tiled::MAX_STRIP_BYTES / (1024 * 1024))},
        "native_tiff":"bounded_native_strips;none_lzw_deflate;one_final_depth_projection",
        "native_strip_bytes":limits::sample_tiff_tiled::MAX_STRIP_BYTES,
        "encoded_output_bytes":publish::MAX_OUTPUT_BYTES,
        "rgba8_delivery":"complete_final_byte_image_retained;no_complete_f64_surface",
        "tiled_filters":{"operators":["box","gaussian","directional","radial","surface","creative.twist","detail.sharpen","detail.unsharp","detail.median","detail.noise","spatial.offset","spatial.displace","spatial.mosaic","creative.relief","creative.high_pass","creative.extrema","creative.tone_fold","creative.edge_ink","creative.stroke_rank","creative.value_field","creative.field_repair"],"borders":["transparent","clamp","reflect"],"support":"local_halos_or_bounded_nonlocal_source_paths;ordered_stacks_parents_clipped_siblings;real_viewport_borders","mapping_limits":{"path_references":limits::render_filter_regions::MAX_REFERENCES,"radial_samples":limits::render_filter_regions::MAX_REFERENCES},"storage":"actual_peak_source_region_plus_retained_mapping;short_codec_bands_rechecked","coordinates":"global_noise_cells_mosaic_grid_row_parity_and_field_lookup","masks":"global_linked_or_unlinked_coordinates","work":"actual_expanded_tile_visits_including_short_native_codec_bands;full_normal_unmasked_replacement_avoids_blend_conversions","rank_scratch":"bounded_three_channel_neighborhoods_in_render_memory_budget","unsupported":["wrap"],"unsupported_controls_reject_when_disabled":true},
        "tiled_effects":{"operators":["shadow","lit_shadow","stroke","overlay"],"support":"maximum_immutable_alpha_effect_support_plus_sequential_filter_and_ancestor_support","paints":"global_original_item_space","controls":["fill_opacity","overall_opacity","scale","contour","lighting","disabled_effects"],"integer_unblurred_shadow":"borrowed_alpha_single_tap;reduced_work_charge","work_limits_raised":false},
        "unsupported_tiled":["other_filter_operators","wrapped_filter_borders","artwork_masks","raw","retained_object_surfaces"],
        "other_limits":"existing_total_work_source_cache_and_format_batch_limits_apply",
        "native_full_surface_library_api":"whole_evaluation_only",
        "progress":"render_tiles;cooperative_cancellation_between_tiles"
    });
    capabilities["agent_discovery"] = json!({
        "cli_help_arguments":["--help","-h"],
        "lookup":"schema.lookup", "index":"index",
        "large_schema_outline_bytes":schema::OUTLINE_BYTES,
        "schema_selector_separator":"/",
        "schema_selector_max_bytes":limits::schema::MAX_SELECTOR_BYTES,
        "schema_variant_selector_field":"select",
        "schema_error_queries":["details.schema_lookup","details.suggested_lookup"],
        "full_schema":"schema", "mcp_default":"full",
        "mcp_compact_arguments":["mcp","--tools","core"],
        "mcp_compact_budget_bytes":mcp::CORE_CATALOG_BYTES,
        "mcp_compact_first_tools":mcp::CORE_ENTRY_POINTS,
        "mcp_dispatcher":"inkbolt_run", "execution_validation":"complete_typed_request"
    });
    capabilities["request_diagnostics"] = json!({"code":"INVALID_REQUEST","scope":"typed_JSON_request_rejection","missing_fields":"schema_confirmed_names;not_JSON_instance_paths","schema_lookup":"details.schema_lookup","expected":"optional_compact_schema_fields_when_unambiguous","maximum_error_bytes":limits::request::MAX_DIAGNOSTIC_BYTES,"request_values_echoed":false,"execution_validation":"unchanged;hints_generated_only_after_rejection"});
    capabilities["session_contract"]["svg_retry_fingerprints"] = json!({"accepted":["current","before_unsupported_policy","before_image_options"],"introduced_fields_must_equal_defaults":true,"stored_rows_rewritten":false});
    capabilities["session_proposals"] = json!({"dry_run":"session.dry_run","apply":"session.apply_proposal","version":1,"actions":"all_session_actions","database_dry_run_access":"read_only","history_changed_by_dry_run":false,"bound_inputs":["session_id","request_id","expected_revision","request_fingerprint","base_state_sha256","result_state_sha256"],"comparison":"structural_with_optional_pixels","preview":"optional_full_canvas_PNG_at_scale_one","persistent_proposal_store":false,"proposal_is_authorization":false,"history_storage_and_receipt_limits":"shared_with_real_apply;filesystem_commit_can_still_fail"});
    capabilities["paged_inspection"] = json!({"command":"document.inspect.page","collections":["items","assets","fonts","anchors"],"maximum_records":inspection::MAX_PAGE_ITEMS,"maximum_result_bytes":inspection::MAX_PAGE_BYTES,"cursor":"document_content_and_view_and_limit_bound","order":"document_storage_for_items;id_for_resources;component_then_command_for_anchors","field_selection":true,"legacy_inspection":"unchanged","external_resources_verified":false});
    capabilities["document_checks"] = json!({"command":"document.check","report_version":1,"checks":["structure","pinned_resource_registries","authored_text_and_story_layout","retained_nested_snapshots","instance_replacement_content"],"maximum_issues":checks::MAX_ISSUES,"maximum_report_bytes":checks::MAX_REPORT_BYTES,"default_issues":limits::checks::DEFAULT_ISSUES,"font_axes":"validated_even_for_empty_text","incomplete":"explicit_for_skipped_layouts_or_stopped_work","errors":"located_original_codes_and_repair_guidance","external_object_links":"not_read_or_refreshed","delivery_certificate":false,"source_changed":false});
    capabilities["resource_import_recovery"] = json!({"commands":["asset.import","font.import","sequence.import"],"publication":"complete_flushed_content_addressed_blobs;create_only;existing_content_verified","source_preserved":true,"historical_request_receipt":false,"retry":"reread_unchanged_sources_and_settings;deduplicate_complete_blobs;creation_counts_describe_this_invocation","font_pair":"license_published_before_font;complete_license_can_remain_on_failure","sequence":"partial_complete_cache_entries_can_remain;only_complete_document_returned","cancellation":{"image_and_font":"shared_context_checked_before_entry;bounded_in_flight_operation_finishes","sequence":"between_frames_and_cache_entries;committed_cache_retained;final_publication_wins_late_cancel"},"orphans":"retained_after_process_death;no_directory_sweep","evidence_scope":"trusted_local_Windows_process_interruption"});
    capabilities["session_backups"] = json!({"commands":["session.backup","session.recover","session.migrate"],"storage_version":sessions::STORE_VERSION,"supported_storage_versions":sessions::SUPPORTED_STORE_VERSIONS,"maximum_database_bytes":sessions::MAX_DATABASE_BYTES,"capture":format!("expected_head_read_transaction;bounded_{}_page_steps;writers_may_receive_SESSION_BUSY", limits::sessions::BACKUP_STEP_PAGES),"verification":"whole_history_checksums_and_links;exact_head_and_history_identity;validated_copy_before_publication","publication":"create_only_hard_link;no_existing_destination_or_sidecars;late_cancellation_keeps_success","restore_identity":"exact_byte_length_and_sha256;original_session_id_preserved","retains":["immutable_states","undo_redo","named_snapshots","resource_bindings","retry_receipts"],"resources_copied":false,"external_resources_verified":false,"implicit_migration":false,"durable_publication_ledger":true,"receipt_optional":true,"hot_journal":"read_only_backup_requires_ordinary_session_recovery_first","orphans":"retained_after_crash;only_owned_live_temporary_files_cleaned"});
    capabilities["session_continuation"] = json!({"command":"session.continue","parent":"exact_revision_in_hash_pinned_whole_history_backup","new_identity":true,"new_revision":0,"old_history":"preserved_in_parent_backup;not_copied_or_evicted","new_undo_redo_and_snapshots":"empty","resources":"original_bindings_retained;explicit_rebinding;no_external_resource_reads","lineage":"version_1_checksums_and_initial_receipt_link;returned_by_read_receipt_verify_and_compact_results","retry":"same_request_id_and_parent_identity;committed_receipt_survives_missing_parent","automatic_parent_traversal":false,"authentication":false});
    capabilities["durable_publication"] = json!({"commands":["document.publish","session.publish","session.backup","session.recover","session.migrate"],"optional_argument":"receipt:{receipt_root,request_id}","inspection":"publication.receipt","recovery":"publication.recover","backend":if cfg!(windows) {"Windows_local_file_identity_and_SQLite_rollback_FULL"} else if cfg!(unix) {"Unix_device_inode_and_SQLite_rollback_FULL"} else {"unsupported"},"supported_here":cfg!(any(windows, unix)),"states":["prepared","complete"],"recovery_proof":if cfg!(unix) {"retained_staging_link;exact_bytes_sha256;device_and_inode_identity;identical_unrelated_bytes_rejected"} else {"retained_staging_link;exact_bytes_sha256;volume_and_128bit_file_identity;identical_unrelated_bytes_rejected"},"request_identity":"normalized_typed_inputs_without_control","completed_retry":"original_receipt_without_reopening_sources_or_output","prepared_recovery":"publish_validated_staging_bytes;no_rerender","postpublication_store_failure":"successful_created_output_with_completion_pending_and_recovery_required","maximum_receipts":publications::MAX_RECORDS,"maximum_receipt_bytes":publications::MAX_RECEIPT_BYTES,"maximum_ledger_payload_bytes":publications::MAX_LEDGER_BYTES,"maximum_output_bytes":publish::MAX_OUTPUT_BYTES,"maximum_history_bytes":sessions::MAX_DATABASE_BYTES,"payload_versions":{"output":1,"history":2},"published_restoration":"historical_creation_proved_by_retained_and_destination_file_identity;new_edits_preserved;current_integrity_requires_session.verify","cleanup":"identified_owned_staging_after_completed_record;crash_or_uncertain_commit_evidence_retained","implicit_job_queue":false,"power_loss_guarantee":false});
    capabilities["session_migration"] = json!({"command":"session.migrate","supported":[{"from":1,"to":2}],"publication":"new_backup_only;no_in_place_or_implicit_upgrade","adds":"empty_checked_lineage_table","preserves":"all_original_rows_and_logical_history_sha256","restore":"session.recover_with_returned_backup_identity","downgrade":false});
    capabilities["jobs"] = jobs::capabilities();
    capabilities["job_process"] = json!({"interface":"Rust_library_worker_containment;used_by_durable_jobs","supported_here":cfg!(windows),"backend":"Windows_owned_job_object","cooperating_child_start_gate":true,"hidden":true,"active_processes":1,"default_lifetime_ms":job_process::Limits::default().lifetime_ms,"maximum_lifetime_ms":job_process::MAX_LIFETIME_MS,"default_committed_memory_mib":job_process::Limits::default().memory_mib,"maximum_committed_memory_mib":job_process::MAX_MEMORY_MIB,"deadline":"watchdog_independent_of_caller_polling","owner_process_death":"kill_on_job_close;before_assignment_startup_pipe_EOF","executable_identity":"exact_bytes_sha256;held_against_write_and_delete","process_identity":"PID_and_creation_time;unknown_access_never_assumed_dead","peak_memory":"OS_peak_committed_bytes;not_resident_set","elapsed":"launch_to_first_observed_exit;not_a_controlled_runtime_benchmark","durable_queue":false,"publication_reconciliation":false,"security_sandbox":false});
    capabilities["export_preflight"] = json!({"command":"document.preflight","preparation":"same_encoder_and_destination_checks_as_document.publish","success":"created_false_receipt_with_exact_bytes_sha256_and_actual_losses","failure":"ready_false_with_original_error_and_repair_guidance","cancellation":"normal_error_no_partial_report","writes_files":false,"reserves_output":false,"predicts_filesystem_write_success":false,"durable_receipt_ledger":false});
    capabilities["focused_previews"] = json!({"command":"document.preview","focus":["canvas","region","items","artboard"],"image":"PNG_with_existing_output_profile_and_loss_contract","region_and_items":"full_composition_crop;full_evaluation_limits_apply","item_bounds":"unclipped_geometry_without_strokes_or_effects;explicit_margin","artboard":"selected_subtree_or_shared_scene;existing_artboard_export_contract","coordinates":"explicit_document_world_to_pixel_and_inverse;pixel_edges_and_centers","quantization":"outward_to_original_render_grid_then_clip","source_identity":"canonical_document_sha256_and_revision","source_changed":false});
    capabilities["focused_previews"]["vector_overview"] = json!({"option":"max_size","axes":[limits::previews::MIN_OVERVIEW_AXIS,limits::previews::MAX_OVERVIEW_AXIS],"focus":"canvas","scale":1,"evaluation":"whole","padding":0,"crop_to_canvas":true,"enlargement":false,"full_resolution_buffer":false,"coordinate_mapping":true,"admitted":["vector_fills","object_scaled_strokes","groups","frames","geometric_clips","scalar_masks","text","placed_and_retained_pixels"],"unsupported":["document_scaled_strokes","effects","filters","artwork_masks","pixel_warps","HDR_grades","backgrounds","native_ink_recipes","other_retained_generators","raster_documents"],"limits":"ordinary_geometry_matrix_pixel_work_and_memory_limits;supersampling_counts","contact_sheets":true});
    capabilities["visual_comparison"] = json!({"commands":["document.diff.preview","session.diff.preview"],"artifacts":["before","after","mask"],"color":"common_srgb_rgba8_view;original_output_profiles_recorded_but_not_applied","alignment":"world_grid_or_standalone_artboard_local;union_extents;transparent_missing_pixels;no_registration_or_resampling","fractional_grid_phase":"reject_unless_integer_at_requested_scale;1e-9_pixel_roundoff_tolerance","focus":["canvas","region","union_of_items_in_both_revisions","artboard"],"metrics":"exact_and_strictly_above_threshold_channel_deltas;end_exclusive_bounds;per_side_world_corners","maximum_output_pixels":visual_diff::MAX_PIXELS,"source_render_limits":"unchanged_full_render_limits","structural":"included_by_default;optional_omission_is_explicit_null","source_changed":false});
    capabilities["contact_sheets"] = json!({"command":"document.contact_sheet","maximum_views":contact_sheets::MAX_VIEWS,"maximum_aggregate_evaluation_pixels":contact_sheets::MAX_PIXELS,"maximum_sheet_pixels":contact_sheets::MAX_PIXELS,"maximum_cell_axis":limits::contact_sheets::MAX_CELL_AXIS,"columns":[1,limits::contact_sheets::MAX_COLUMNS],"gap":[0,limits::contact_sheets::MAX_GAP],"thumbnail_sampling":"nearest_center;no_enlargement;thin_details_can_disappear","coordinates":"per_view_world_to_sheet_and_inverse","color":"one_document_output_profile;transparent_gaps;96ppi_sheet","source_changed":false});
    capabilities["mcp_responses"] = json!({"formats":["json","markdown","structured","preview"],"default":"json","png_payloads":"one_location_with_explicit_payload_ref","json_markdown_text":"metadata_envelope;overflow_PNGs_reference_structuredContent","structured_preview_text":"summary_only","engine_results":"unchanged_after_payload_reconstruction"});
    capabilities["mcp_preview"] = json!({"response_format":"preview","default":"json","image_bytes":"one_location_with_explicit_payload_ref","maximum_png_attachments":mcp_preview::MAX_IMAGES,"maximum_attached_base64_bytes":mcp_preview::MAX_IMAGE_BASE64_BYTES,"overflow":"one_inline_payload_in_structuredContent;duplicates_reference_it","text":"summary_only","supported_artifacts":["document.export","document.preview","document.contact_sheet","document.diff.preview","session.diff.preview","artboard.export","sequence.export","channel.export","document.proof","document.prepress","document.separations","session.dry_run"],"other_results":"complete_structuredContent_without_textual_duplication"});
    capabilities["agent_inputs"] = json!({
        "workspace_flag":"--workspace ABSOLUTE_DIRECTORY",
        "workspace_position":"before_request_file_or_mcp",
        "saved_document":{"fields":["session_id","revision","session_root"],"revision":"required_immutable_committed_revision","session_root":"required_without_workspace","placement":"top_level_document_before_after_arguments","resources":"inherit_saved_bindings_including_null_unless_explicitly_overridden","nested_transfer_source":false},
        "document_file":{"fields":["file_path","sha256"],"sha256":"required_lowercase_hex_of_exact_bytes","source":"one_inline_snapshot_JSON","file_bytes":MAX_REQUEST_BYTES,"resources":"explicit_or_workspace_defaults","recursive_references":false,"create_only_output":"document.publish_or_session.publish_with_format_snapshot"},
        "json_library_api":"request::execute",
        "typed_library_api":"execute_and_execute_controlled_keep_inline_snapshots",
        "request_bytes":MAX_REQUEST_BYTES,"expanded_request_bytes":MAX_REQUEST_BYTES,
        "workspace_is_os_sandbox":false
    });
    capabilities["agent_outputs"] = json!({"response_mode_default":"full","compact_commands":responses::COMMANDS,"compact_target_bytes":responses::COMPACT_TARGET_BYTES,"compact_target_scope":"ordinary_result_JSON;long_explicit_paths_can_exceed_target","compact_omissions":["document","receipt.changes","snapshots"],"compact_recovery":"pinned_document_ref_and_receipt_ref;request_response_mode_full","presentation_in_retry_fingerprint":false,"inline_snapshot_results":"full_only"});
    capabilities["geometry_limits"]["primitives"] = json!({"minimum_extent":limits::primitives::MIN_EXTENT,"rotation_degrees":[-i64::from(limits::primitives::MAX_ROTATION_DEGREES),limits::primitives::MAX_ROTATION_DEGREES]});
    capabilities["native_prepress"]["color_conversion_batch_samples"] =
        json!(limits::profiles::MAX_CONVERSION_SAMPLES);
    capabilities["native_prepress"]["color_buffer_values"] =
        json!(limits::prepress::COLOR_BUFFER_VALUES);
    capabilities["session_backups"]["lock_wait_ms"] = json!(limits::sqlite::BUSY_TIMEOUT_MS);
    capabilities["session_backups"]["retry_interval_ms"] =
        json!(limits::sessions::BACKUP_RETRY_INTERVAL_MS);
    capabilities["jobs"]["launch_lock_timeout_ms"] = json!(limits::jobs::LAUNCH_LOCK_TIMEOUT_MS);
    capabilities["jobs"]["launch_retry_interval_ms"] =
        json!(limits::jobs::LAUNCH_RETRY_INTERVAL_MS);
    capabilities["jobs"]["monitor_interval_ms"] = json!(limits::jobs::MONITOR_INTERVAL_MS);
    capabilities["jobs"]["state_poll_interval_ms"] = json!(limits::jobs::STATE_POLL_INTERVAL_MS);
    capabilities["job_process"]["maximum_wait_slice_ms"] =
        json!(limits::job_process::MAX_WAIT_SLICE_MS);
    capabilities["numerical_limits"] = json!({"boards_guide_alignment_tolerance":limits::boards::GUIDE_ALIGNMENT_TOLERANCE,"layered_affine_closure_tolerance":limits::layered::AFFINE_CLOSURE_TOLERANCE,"meshes_control_inset_epsilons":limits::meshes::CONTROL_INSET_EPSILONS,"meshes_inverse_tolerance":limits::meshes::INVERSE_TOLERANCE,"meshes_svg_error_margin":limits::meshes::SVG_ERROR_MARGIN,"path_text_rounding_epsilons":limits::path_text::ROUNDING_EPSILONS,"pixel_brush_endpoint_epsilons":limits::pixel_brush::ENDPOINT_EPSILONS,"pixel_warps_orientation_epsilons":limits::pixel_warps::ORIENTATION_EPSILONS,"pixel_warps_weight_sum_tolerance":limits::pixel_warps::WEIGHT_SUM_TOLERANCE,"profiles_min_matrix_determinant":limits::profiles::MIN_MATRIX_DETERMINANT,"render_filter_regions_absolute_margin":limits::render_filter_regions::ABSOLUTE_MARGIN,"render_filter_regions_rounding_epsilons":limits::render_filter_regions::ROUNDING_EPSILONS,"strokes_brush_min_bisector_length":limits::strokes_brush::MIN_BISECTOR_LENGTH,"strokes_brush_rounding_epsilons":limits::strokes_brush::ROUNDING_EPSILONS,"strokes_outline_rounding_epsilons":limits::strokes_outline::ROUNDING_EPSILONS,"vector_native_integer_tolerance":limits::vector_native::INTEGER_TOLERANCE,"visual_diff_grid_phase_tolerance":limits::visual_diff::GRID_PHASE_TOLERANCE,"volumes_partition_epsilons":limits::volumes::PARTITION_EPSILONS,"render_coverage_path_ellipse_arcs":limits::render_coverage_path::ELLIPSE_ARCS,"work_paths_coverage_max_root_steps":limits::work_paths_coverage::MAX_ROOT_STEPS,"work_paths_coverage_cubic_crossing_work":limits::work_paths_coverage::CUBIC_CROSSING_WORK,"dimensions_pi_atan_terms":limits::dimensions::PI_ATAN_TERMS,"geometry_point_fast_term_bound":limits::geometry_point::FAST_TERM_BOUND});
    capabilities["numerical_limits"]["booleans_quadratic_min_root_enclosure_bits"] =
        json!(limits::booleans_topology_quadratic::MIN_ROOT_ENCLOSURE_BITS);
    capabilities["numerical_limits"]["booleans_quadratic_root_bits_per_depth"] =
        json!(limits::booleans_topology_quadratic::ROOT_BITS_PER_DEPTH);
    capabilities["numerical_limits"]["booleans_quadratic_root_guard_bits"] =
        json!(limits::booleans_topology_quadratic::ROOT_GUARD_BITS);
    capabilities["numerical_limits"]["booleans_quadratic_initial_parameter_bits"] =
        json!(limits::booleans_topology_quadratic::INITIAL_PARAMETER_BITS);
    capabilities["numerical_limits"]["booleans_quadratic_parameter_growth_factor"] =
        json!(limits::booleans_topology_quadratic::PARAMETER_GROWTH_FACTOR);
    capabilities["image_io"]["gif"]["literal_run"] = json!(limits::image_io_gif::LITERAL_RUN);
    capabilities["pixel_warps"]["maximum_absolute_joint_angle_degrees"] =
        json!(limits::pixel_warps::MAX_JOINT_ANGLE_DEGREES);
    capabilities["repeats"]["maximum_absolute_radial_angle_degrees"] =
        json!(limits::repeats::MAX_RADIAL_ANGLE_DEGREES);
    capabilities["layered_interchange"]["maximum_import_channels_per_layer"] =
        json!(limits::layered::MAX_IMPORT_LAYER_CHANNELS);
    capabilities["objects"]["minimum_extent"] = json!(limits::objects::MIN_EXTENT);
    capabilities["geometry_limits"]["minimum_placed_image_extent"] =
        json!(limits::model::MIN_PLACED_IMAGE_EXTENT);
    capabilities["paint_limits"] = json!({"minimum_linear_span":limits::paint::MIN_LINEAR_SPAN,"minimum_radial_radius":limits::paint::MIN_RADIAL_RADIUS,"maximum_radial_radius":model::MAX_COORDINATE,"minimum_anchor_separation":limits::paint::MIN_ANCHOR_SEPARATION});
    capabilities["pixel_warps"]["minimum_frame_extent"] =
        json!(limits::pixel_warps::MIN_FRAME_EXTENT);
    capabilities["path_text"]["minimum_baseline_length"] =
        json!(limits::path_text::MIN_BASELINE_LENGTH);
    capabilities["pdf"]["mark_limits"] = json!({"gap_pt":[limits::pdf_marks::MIN_GAP,limits::pdf_marks::MAX_GAP],"length_pt":[limits::pdf_marks::MIN_LENGTH,limits::pdf_marks::MAX_LENGTH],"line_width_pt":[limits::pdf_marks::MIN_LINE_WIDTH,limits::pdf_marks::MAX_LINE_WIDTH],"registration_radius_pt":[limits::pdf_marks::MIN_REGISTRATION_RADIUS,limits::pdf_marks::MAX_REGISTRATION_RADIUS],"defaults":{"gap_pt":limits::pdf_marks::DEFAULT_GAP,"length_pt":limits::pdf_marks::DEFAULT_LENGTH,"line_width_pt":limits::pdf_marks::DEFAULT_LINE_WIDTH,"registration_radius_pt":limits::pdf_marks::DEFAULT_REGISTRATION_RADIUS}});
    capabilities["print_proof"]["delta_e76_threshold"] =
        json!([0, limits::proof::MAX_DELTA_E76_THRESHOLD]);
    capabilities["color_profiles"]["lut_curve_entries"] =
        json!([2, limits::profiles::MAX_LUT_CURVE_ENTRIES]);
    capabilities["meshes"]["maximum_svg_coverage_coordinate"] =
        json!(limits::svg::MAX_MESH_COVERAGE_COORDINATE);
    capabilities["svg_import"]["validation_limits"] = json!({"canvas_extent":[limits::vector_canvas::MIN_LOGICAL_SIZE,model::MAX_DIMENSION],"stroke_width":[0,limits::strokes::MAX_WIDTH],"miter_limit":[limits::strokes::MIN_MITER_LIMIT,limits::strokes::MAX_MITER_LIMIT],"font_size":[limits::text::MIN_FONT_SIZE,limits::text::MAX_FONT_SIZE]});
    capabilities
}
pub fn execute(request: Request) -> Result<Value, Error> {
    execute_controlled(request, &control::Control::default())
}
pub fn execute_controlled(request: Request, context: &control::Control) -> Result<Value, Error> {
    let persistent = matches!(
        request,
        Request::SessionCreate { .. }
            | Request::SessionContinue { .. }
            | Request::SessionBackup { .. }
            | Request::SessionRecover { .. }
            | Request::SessionMigrate { .. }
            | Request::PublicationRecover { .. }
            | Request::JobStart { .. }
            | Request::JobCancel { .. }
            | Request::JobResume { .. }
            | Request::SessionApply { .. }
            | Request::SessionApplyProposal { .. }
            | Request::Publish { .. }
            | Request::SessionPublish { .. }
            | Request::SequenceImport { .. }
            | Request::AssetImport { .. }
            | Request::FontImport { .. }
    );
    if !matches!(
        request,
        Request::SessionCreate { .. }
            | Request::SessionContinue { .. }
            | Request::SessionBackup { .. }
            | Request::SessionRecover { .. }
            | Request::SessionMigrate { .. }
            | Request::Publish { .. }
            | Request::SessionPublish { .. }
            | Request::PublicationRecover { .. }
            | Request::JobStart { .. }
            | Request::JobCancel { .. }
            | Request::JobResume { .. }
            | Request::SessionApply { .. }
            | Request::SessionApplyProposal { .. }
    ) {
        context.check()?;
    }
    let result = match request {
        Request::LayeredImport {
            source_path,
            expected_sha256,
            id,
            color_policy,
            embedded_objects,
            control,
            text_fonts,
        } => layered::import_with_text_fonts(
            &source_path,
            expected_sha256.as_deref(),
            id,
            color_policy,
            embedded_objects,
            text_fonts.as_ref(),
            &context.scoped(&control)?,
        ),
        Request::PresetList {} => Ok(presets::catalog()),
        Request::PresetCreate {
            id,
            version,
            preset,
            control,
        } => presets::create(id, version, preset, &context.scoped(&control)?),
        Request::HandoffExport {
            document,
            resources,
            options,
            previous,
            control,
        } => handoff::export(
            &document,
            &resources,
            &options,
            previous.as_ref(),
            &context.scoped(&control)?,
        ),
        Request::HandoffInspect {
            handoff,
            input_root,
            include_schedule,
            control,
        } => handoff::inspect(
            &handoff,
            input_root.as_deref(),
            include_schedule,
            &context.scoped(&control)?,
        ),
        Request::SequenceImport {
            source,
            store_root,
            id,
            color_policy,
            resolution_ppi,
            control,
        } => sequences::import(
            &source,
            &store_root,
            id,
            color_policy,
            resolution_ppi,
            &context.scoped(&control)?,
        ),
        Request::SequenceExport {
            document,
            resources,
            scale,
            render_options,
            metadata_policy,
            control,
        } => sequences::export_frames(
            &document,
            &resources,
            scale,
            render_options.as_ref(),
            metadata_policy,
            &context.scoped(&control)?,
        ),
        Request::AssistLayout {
            document,
            options,
            control,
        } => assistance::inspect(&document, &options, &context.scoped(&control)?),
        Request::AssistSegment {
            document,
            id,
            options,
            asset_root,
            control,
        } => assistance::segment::inspect(
            &document,
            &id,
            &options,
            asset_root.as_deref(),
            &context.scoped(&control)?,
        ),
        Request::VolumeInspect { document, id } => {
            volumes::inspect_controlled(&document, &id, context)
        }
        Request::AppearanceInspect { document, id } => {
            appearance::inspect_controlled(&document, &id, context)
        }
        Request::SequenceInspect { document } => sequences::inspect(&document),
        Request::SequenceOpen { document, id } => sequences::open(&document, &id),
        Request::ObjectImport {
            source_path,
            snapshot,
            link_key,
        } => objects::import(
            source_path.as_deref(),
            snapshot.as_deref(),
            link_key.as_deref(),
        ),
        Request::ObjectOpen { document, id } => objects::open(&document, &id),
        Request::ObjectStatus {
            document,
            id,
            link_root,
        } => objects::status(&document, &id, link_root.as_deref()),
        Request::SampleMeasure {
            document,
            points,
            asset_root,
            font_root,
        } => hdr::measure(
            &document,
            &points,
            asset_root.as_deref(),
            font_root.as_deref(),
        ),
        Request::SampleImport {
            source_path,
            id,
            resolution_ppi,
            color_policy,
            storage,
        } => sample_import::import_with_storage(
            &source_path,
            id,
            resolution_ppi,
            color_policy,
            storage.as_ref(),
            context,
        ),
        Request::RawDevelop {
            source_path,
            expected_sha256,
            id,
            capture,
            settings,
            control,
        } => raw::import(
            &source_path,
            expected_sha256.as_deref(),
            id,
            &capture,
            &settings,
            &context.scoped(&control)?,
        ),
        Request::RawRetain {
            source_path,
            expected_sha256,
            id,
            capture,
            settings,
            corrections,
            control,
        } => raw::retained::retain(
            &source_path,
            expected_sha256.as_deref(),
            id,
            capture,
            settings,
            corrections,
            &context.scoped(&control)?,
        ),
        Request::RawReopen {
            source_path,
            recipe_path,
            id,
            control,
        } => raw::retained::reopen(&source_path, &recipe_path, id, &context.scoped(&control)?),
        Request::RawRecipe { document, id } => raw::retained::recipe(&document, &id),
        Request::SwatchInspect { document } => swatches::inspect(&document),
        Request::GeometryMeasure {
            document,
            options,
            control,
        } => dimensions::inspect(&document, &options, &context.scoped(&control)?),
        Request::PixelWarpInspect {
            warp,
            width,
            height,
            samples,
            inverse_samples,
            include_mesh,
            control,
        } => pixel_warps::inspect(
            &warp,
            [width, height],
            &samples,
            &inverse_samples,
            include_mesh,
            &context.scoped(&control)?,
        ),
        Request::WarpInspect {
            warp,
            samples,
            grid,
            include_geometry,
            include_segments,
            control,
        } => warps::inspect(
            &warp,
            &samples,
            grid.as_ref(),
            include_geometry,
            include_segments,
            &context.scoped(&control)?,
        ),
        Request::RepeatInspect {
            repeat,
            include_geometry,
            control,
        } => repeats::inspect(&repeat, include_geometry, &context.scoped(&control)?),
        Request::InterpolationInspect {
            interpolation,
            include_geometry,
            control,
        } => interpolation::inspect(&interpolation, include_geometry, &context.scoped(&control)?),
        Request::BrushInspect {
            stroke,
            include_dabs,
            control,
        } => pixel_brush::inspect(&stroke, include_dabs, &context.scoped(&control)?),
        Request::ImageTrace {
            id,
            source,
            options,
            asset_root,
            control,
        } => tracing::trace(
            id,
            &source,
            &options,
            asset_root.as_deref(),
            &context.scoped(&control)?,
        ),
        Request::SvgImport {
            resource_profile,
            control,
            id,
            source,
            font_bindings,
            font_root,
            images,
            unsupported,
        } => svg_import::import_with_options_controlled(
            id,
            source,
            font_bindings,
            font_root,
            resource_profile,
            svg_import::Options {
                images,
                unsupported,
            },
            &context.scoped(&control)?,
        ),
        Request::VectorImport {
            id,
            source_path,
            color_policy,
            resource_profile,
            control,
        } => vector_native::import(
            id,
            &source_path,
            color_policy,
            resource_profile,
            &context.scoped(&control)?,
        ),
        Request::MeshInspect {
            mesh,
            space,
            parameters,
        } => meshes::inspect(&mesh, space, &parameters),
        Request::Capabilities {} => Ok(capability_report()),
        Request::Schema {} => Ok(schema::full().clone()),
        Request::SchemaLookup { name, select, full } => {
            schema::lookup_in_workspace(&name, select.as_deref(), full, context.has_workspace())
        }
        Request::ImplementationStatus {} => Ok(implementation_status()),
        Request::Publish {
            document,
            resources,
            output,
            receipt,
            control,
        } => match receipt {
            Some(target) => publications::document(
                &document,
                &resources,
                &output,
                &target,
                &context.scoped(&control)?,
            ),
            None => publish::publish(&document, &resources, &output, &context.scoped(&control)?),
        },
        Request::SessionPublish {
            session_root,
            session_id,
            expected_revision,
            output,
            receipt,
            control,
        } => match receipt {
            Some(target) => publications::session(
                &session_root,
                &session_id,
                expected_revision,
                &output,
                &target,
                &context.scoped(&control)?,
            ),
            None => sessions::publish(
                &session_root,
                &session_id,
                expected_revision,
                &output,
                &context.scoped(&control)?,
            ),
        },
        Request::PublicationReceipt {
            receipt_root,
            request_id,
            control,
        } => publications::receipt(
            &publications::ReceiptTarget {
                receipt_root,
                request_id,
            },
            &context.scoped(&control)?,
        ),
        Request::PublicationRecover {
            receipt_root,
            request_id,
            control,
        } => publications::recover(
            &publications::ReceiptTarget {
                receipt_root,
                request_id,
            },
            &context.scoped(&control)?,
        ),
        Request::JobStart {
            job_root,
            request_id,
            document,
            resources,
            output,
            options,
            control,
        } => jobs::start(
            &job_root,
            &request_id,
            &document,
            &resources,
            &output,
            &options,
            &context.scoped(&control)?,
        ),
        Request::JobStatus {
            job_root,
            request_id,
            control,
        } => jobs::status(&job_root, &request_id, &context.scoped(&control)?),
        Request::JobList {
            job_root,
            options,
            control,
        } => jobs::list(&job_root, &options, &context.scoped(&control)?),
        Request::JobResult {
            job_root,
            request_id,
            control,
        } => jobs::result(&job_root, &request_id, &context.scoped(&control)?),
        Request::JobWait {
            job_root,
            request_id,
            wait_ms,
            control,
        } => jobs::wait(&job_root, &request_id, wait_ms, &context.scoped(&control)?),
        Request::JobCancel {
            job_root,
            request_id,
            control,
        } => jobs::cancel(&job_root, &request_id, &context.scoped(&control)?),
        Request::JobResume {
            job_root,
            request_id,
            control,
        } => jobs::resume(&job_root, &request_id, &context.scoped(&control)?),
        Request::Diff {
            before,
            after,
            before_resources,
            after_resources,
            compare_pixels,
            control,
        } => diff::compare(
            &before,
            &after,
            &before_resources,
            &after_resources,
            compare_pixels,
            &context.scoped(&control)?,
        ),
        Request::DiffPreview {
            before,
            after,
            before_resources,
            after_resources,
            options,
            control,
        } => visual_diff::compare(
            &before,
            &after,
            &before_resources,
            &after_resources,
            &options,
            &context.scoped(&control)?,
        ),
        Request::SessionDiffPreview {
            session_root,
            session_id,
            from_revision,
            to_revision,
            options,
            control,
        } => sessions::compare_preview(
            &session_root,
            &session_id,
            from_revision,
            to_revision,
            &options,
            &context.scoped(&control)?,
        ),
        Request::SessionDiff {
            session_root,
            session_id,
            from_revision,
            to_revision,
            compare_pixels,
            control,
        } => sessions::compare(
            &session_root,
            &session_id,
            from_revision,
            to_revision,
            compare_pixels,
            &context.scoped(&control)?,
        ),
        Request::SessionCreate {
            session_root,
            session_id,
            request_id,
            document,
            resources,
            control,
        } => sessions::create(
            &session_root,
            &session_id,
            &request_id,
            &document,
            &resources,
            &context.scoped(&control)?,
        ),
        Request::SessionDryRun {
            session_root,
            session_id,
            request_id,
            expected_revision,
            action,
            options,
            control,
        } => sessions::dry_run(
            &session_root,
            &session_id,
            &request_id,
            expected_revision,
            &action,
            &options,
            &context.scoped(&control)?,
        ),
        Request::SessionApplyProposal {
            session_root,
            proposal,
            action,
            control,
        } => sessions::apply_proposal(
            &session_root,
            &proposal,
            &action,
            &context.scoped(&control)?,
        ),
        Request::SessionRead {
            session_root,
            session_id,
            snapshot,
        } => sessions::read(&session_root, &session_id, snapshot.as_deref()),
        Request::SessionApply {
            session_root,
            session_id,
            request_id,
            expected_revision,
            action,
            control,
        } => sessions::mutate(
            &session_root,
            &session_id,
            &request_id,
            expected_revision,
            &action,
            &context.scoped(&control)?,
        ),
        Request::SessionReceipt {
            session_root,
            session_id,
            request_id,
        } => sessions::receipt(&session_root, &session_id, &request_id),
        Request::SessionHistory {
            session_root,
            session_id,
            after_revision,
            limit,
        } => sessions::history(&session_root, &session_id, after_revision, limit),
        Request::SessionVerify {
            session_root,
            session_id,
            control,
        } => sessions::verify(&session_root, &session_id, &context.scoped(&control)?),
        Request::SessionBackup {
            session_root,
            session_id,
            expected_revision,
            output,
            receipt,
            control,
        } => {
            let control = context.scoped(&control)?;
            match receipt {
                Some(target) => publications::history::backup(
                    &session_root,
                    &session_id,
                    expected_revision,
                    &output,
                    &target,
                    &control,
                ),
                None => sessions::backup::create(
                    &session_root,
                    &session_id,
                    expected_revision,
                    &output,
                    &control,
                ),
            }
        }
        Request::SessionRecover {
            session_root,
            session_id,
            source,
            receipt,
            control,
        } => {
            let control = context.scoped(&control)?;
            match receipt {
                Some(target) => publications::history::restore(
                    &session_root,
                    &session_id,
                    &source,
                    &target,
                    &control,
                ),
                None => sessions::backup::recover(&session_root, &session_id, &source, &control),
            }
        }
        Request::SessionMigrate {
            session_id,
            source,
            target_version,
            output,
            receipt,
            control,
        } => {
            let control = context.scoped(&control)?;
            match receipt {
                Some(target) => publications::history::migrate(
                    &session_id,
                    &source,
                    target_version,
                    &output,
                    &target,
                    &control,
                ),
                None => sessions::lineage::migrate(
                    &session_id,
                    &source,
                    target_version,
                    &output,
                    &control,
                ),
            }
        }
        Request::SessionContinue {
            session_root,
            session_id,
            request_id,
            parent,
            control,
        } => sessions::lineage::continue_from(
            &session_root,
            &session_id,
            &request_id,
            &parent,
            &context.scoped(&control)?,
        ),
        Request::ArtboardExport {
            render_options,
            metadata_policy,
            document,
            image_options,
            selection,
            format,
            scale,
            include_bleed,
            asset_root,
            font_root,
        } => boards::export_controlled(
            &document,
            &selection,
            boards::ExportOptions {
                render_options: render_options.as_ref(),
                metadata_policy,
                image_options: image_options.as_ref(),
                format,
                scale,
                include_bleed,
                asset_root: asset_root.as_deref(),
                font_root: font_root.as_deref(),
            },
            context,
        ),
        Request::FontImport {
            source_path,
            license_path,
            store_root,
            face_index,
        } => Ok(json!(fonts::import(
            &source_path,
            &license_path,
            &store_root,
            face_index
        )?)),
        Request::FontVerify { font, font_root } => {
            fonts::load(&font, font_root.as_deref())?;
            Ok(json!({"valid":true,"font":font}))
        }
        Request::FontInspect {
            font,
            font_root,
            variations,
        } => fonts::inspect(&font, font_root.as_deref(), &variations),
        Request::TextDirections {
            text,
            direction,
            lines,
        } => Ok(json!(text::bidi::inspect(&text, direction, &lines)?)),
        Request::TextHyphenate {
            rules,
            words,
            control,
        } => {
            let control = context.scoped(&control)?;
            Ok(json!(
                hyphenation::Compiled::new(&rules, &control)?.inspect(&words, &control)?
            ))
        }
        Request::StoryInspect {
            document,
            id,
            font_root,
            include_outlines,
        } => {
            validate(&document)?;
            let source = text::flow::story(&document, &id)?;
            let cache = fonts::resolve_story(&document, font_root.as_deref(), Some(&id))?;
            let report = text::flow::layout(source, &document, &cache)?;
            let mut value = json!(report);
            if !include_outlines {
                for slot in value["slots"].as_object_mut().unwrap().values_mut() {
                    slot.as_object_mut().unwrap().remove("paths");
                }
            }
            Ok(
                json!({"document_id":document.id,"revision":document.revision,"id":id,"story":source,"layout":value,"source_preserved":true}),
            )
        }
        Request::TextInspect {
            document,
            id,
            font_root,
            include_outlines,
        } => {
            validate(&document)?;
            let i = scene::index(&document, &id)?;
            if let model::Content::StoryFrame { story_id, slot_id } = &document.items[i].content {
                let cache = fonts::resolve(&document, font_root.as_deref())?;
                let report =
                    text::flow::layout(text::flow::story(&document, story_id)?, &document, &cache)?;
                let mut layout = json!(report.slots[slot_id]);
                if !include_outlines {
                    layout.as_object_mut().unwrap().remove("paths");
                }
                return Ok(
                    json!({"id":id,"story_id":story_id,"slot_id":slot_id,"layout":layout,"lines":report.lines.iter().filter(|l|&l.slot_id==slot_id).collect::<Vec<_>>(),"overset":report.overset,"geometry_bounds":scene::bounds(&document,i)?,"indices":report.indices}),
                );
            }
            let model::Content::Text { frame } = &document.items[i].content else {
                return Err(Error::new("INVALID_OPERATION", "Selected item is not text"));
            };
            let cache = fonts::resolve(&document, font_root.as_deref())?;
            let layout = text::layout(frame, &document, &cache)?;
            let world = scene::world_transform(&document, i)?;
            let mut world_ink = None;
            for p in &layout.paths {
                model::validate_world_geometry(&p.geometry, world)?;
                let b = geometry::bounds(&p.geometry, world);
                world_ink = Some(world_ink.map_or(b, |v| scene::union(v, b)));
            }
            let mut value = json!(layout);
            if !include_outlines {
                value.as_object_mut().unwrap().remove("paths");
            }
            Ok(
                json!({"id":id,"frame":frame,"layout":value,"world_ink_bounds":world_ink,"geometry_bounds":scene::bounds(&document,i)?,"indices":"unicode_scalars","edit_boundaries":"graphemes","glyph_clusters":"logical_scalar_intervals","bounds_semantics":"Ink bounds exclude geometric clipping and visibility; path midpoint culling is applied. Frame bounds drive alignment."}),
            )
        }
        Request::AssetImport {
            source_path,
            store_root,
            color_policy,
            input_profile,
        } => Ok(json!(assets::import_with_profile(
            &source_path,
            &store_root,
            color_policy,
            input_profile.as_ref()
        )?)),
        Request::AssetVerify { asset, asset_root } => {
            assets::load(&asset, asset_root.as_deref())?;
            Ok(
                json!({"valid":true,"sha256":asset.sha256,"width":asset.width,"height":asset.height}),
            )
        }
        Request::AssetEmbed { asset, asset_root } => {
            Ok(json!(assets::embed(&asset, asset_root.as_deref())?))
        }
        Request::Create {
            resource_profile,
            id,
            kind,
            width,
            height,
            resolution_ppi,
        } => {
            let document = Document {
                resource_profile,
                vector_canvas: None,
                stories: std::collections::BTreeMap::new(),
                swatches: Default::default(),
                background: None,
                metadata: None,
                output_profile: None,
                variants: None,
                schema_version: 2,
                id,
                kind,
                width,
                height,
                color_space: ColorSpace::Srgb,
                revision: 0,
                resolution_ppi,
                global_light: effects::Lighting::default(),
                items: vec![],
                assets: Default::default(),
                fonts: Default::default(),
                selection: None,
                channels: Default::default(),
                ink_recipe: None,
            };
            validate(&document)?;
            Ok(json!(document))
        }
        Request::Validate { document } => {
            model::validate_controlled(&document, context)?;
            Ok(json!(document))
        }
        Request::Check {
            document,
            options,
            resources,
            control,
        } => checks::check(&document, &options, &resources, &context.scoped(&control)?),
        Request::Preflight {
            document,
            output,
            resources,
            control,
        } => checks::preflight(&document, &resources, &output, &context.scoped(&control)?),
        Request::Inspect { document } => {
            model::validate_controlled(&document, context)?;
            let mut geometry = scene::GeometryCache::new(&document, context)?;
            let items: Vec<Value> = (0..document.items.len())
                .map(|i| inspect_item(&document, i, &mut geometry))
                .collect::<Result<_, _>>()?;
            let assets:Vec<_>=document.assets.iter().map(|(id,a)|json!({"id":id,"width":a.width,"height":a.height,"sha256":a.sha256,"storage":match a.storage{assets::Storage::Stored=>"stored",assets::Storage::Embedded{..}=>"embedded",assets::Storage::Encoded{..}=>"encoded"},"provenance":a.provenance,"used_by":document.items.iter().filter_map(|item|match &item.content{model::Content::Image{asset_id,..} if asset_id==id=>Some(&item.id),_=>None}).collect::<Vec<_>>()})).collect();
            let fonts:Vec<_>=document.fonts.iter().map(|(id,font)|json!({"id":id,"font":font,"used_by":document.items.iter().filter(|item|instances::any_content(&item.content,&|c|match c {model::Content::Text {frame}=>text::styles(frame).any(|s|s.font_ids().any(|f|f==id)),model::Content::StoryFrame {story_id,..}=>document.stories.get(story_id).is_some_and(|story|story.styles().any(|s|s.font_ids().any(|f|f==id))),_=>false})).map(|item|&item.id).collect::<Vec<_>>()})).collect();
            Ok(
                json!({"stories":document.stories,"swatches":swatches::inspect(&document)?,"background":backgrounds::inspect(&document),"metadata":document.metadata,"resource_manifest":metadata::manifest(&document),"id":document.id,"revision":document.revision,"kind":document.kind,"width":document.width,"height":document.height,"canvas_bounds":if document.vector_canvas.is_some(){json!(vector_canvas::bounds(&document))}else{json!([0,0,document.width,document.height])},"vector_canvas":document.vector_canvas.map(|c|c.receipt(document.resolution_ppi)).transpose()?,"output_profile":document.output_profile.as_ref().map(profiles::summary).transpose()?,"global_light":document.global_light,"resolution_ppi":document.resolution_ppi,"variants":document.variants,"selection":selections::inspect(document.selection.as_ref()),"channels":channels::inspect(&document),"ink_recipe":ink_recipes::inspect(&document),"items":items,"assets":assets,"fonts":fonts,"artboards":boards::inspect(&document)?,"resource_profile":document.resource_profile,"bounds_semantics":"Unclipped geometry only; excludes strokes, visibility and opacity. Text uses its frame here; text.inspect reports glyph ink. Resource inventories are structural; use asset.verify/font.verify to check stored bytes."}),
            )
        }
        Request::InspectPage {
            document,
            options,
            control,
        } => inspection::page(&document, &options, &context.scoped(&control)?),
        Request::Preview {
            document,
            options,
            asset_root,
            font_root,
            control,
        } => previews::preview(
            &document,
            &options,
            asset_root.as_deref(),
            font_root.as_deref(),
            &context.scoped(&control)?,
        ),
        Request::ContactSheet {
            document,
            options,
            asset_root,
            font_root,
            control,
        } => contact_sheets::sheet(
            &document,
            &options,
            asset_root.as_deref(),
            font_root.as_deref(),
            &context.scoped(&control)?,
        ),
        Request::Query { document, query } => query::execute(&document, &query, context),
        Request::Measure {
            document,
            options,
            asset_root,
            font_root,
        } => measurements::measure(
            &document,
            &options,
            asset_root.as_deref(),
            font_root.as_deref(),
        ),
        Request::ChannelExport {
            document,
            id,
            display,
        } => channels::export(&document, &id, display),
        Request::Boolean {
            document,
            ids,
            mode,
            curve_tolerance,
        } => booleans::compute(&document, &ids, mode, curve_tolerance),
        Request::Select { document, ids } => {
            model::validate_controlled(&document, context)?;
            let indices = scene::selection(&document, &ids, false)?;
            let mut geometry = scene::GeometryCache::new(&document, context)?;
            let items: Vec<_> = indices
                .into_iter()
                .map(|i| inspect_item(&document, i, &mut geometry))
                .collect::<Result<_, _>>()?;
            Ok(
                json!({"document_id":document.id,"revision":document.revision,"ids":ids,"items":items,"selection_state":"explicit_ids_only"}),
            )
        }
        Request::Edit {
            document,
            expected_revision,
            operations,
            asset_root,
            font_root,
            control,
        } => Ok(json!(edit::commit_with_resources(
            &document,
            expected_revision,
            &operations,
            asset_root.as_deref(),
            font_root.as_deref(),
            &context.scoped(&control)?
        )?)),
        Request::Render {
            control,
            render_options,
            document,
            scale,
            asset_root,
            font_root,
        } => render::preview_controlled(
            &document,
            scale,
            asset_root.as_deref(),
            font_root.as_deref(),
            render_options.as_ref(),
            &context.scoped(&control)?,
        ),
        Request::Export {
            control,
            render_options,
            metadata_policy,
            document,
            image_options,
            pdf_options,
            layered_options,
            format,
            scale,
            asset_root,
            font_root,
        } => publish::export_with_render_options(
            &document,
            format,
            scale,
            &sessions::Resources {
                asset_root,
                font_root,
            },
            publish::FormatOptions {
                control: Some(&context.scoped(&control)?),
                image_options: image_options.as_ref(),
                metadata_policy,
                pdf_options: pdf_options.as_ref(),
                layered_options: layered_options.as_ref(),
                render_options: render_options.as_ref(),
            },
        ),
        Request::ColorConvert {
            source,
            destination,
            values,
            intent,
            gamut,
            control,
        } => profiles::device::convert_with_gamut(
            &source,
            &destination,
            intent,
            &values,
            gamut,
            Some(&context.scoped(&control)?),
        ),
        Request::ProfileGamut {
            profile,
            xyz_d50,
            intent,
            control,
        } => profiles::gamut::inspect(&profile, &xyz_d50, intent, &context.scoped(&control)?),
        Request::Separations {
            document,
            scale,
            control,
        } => ink_recipes::export(&document, scale, &context.scoped(&control)?),
        Request::Proof {
            document,
            options,
            asset_root,
            font_root,
            control,
        } => proof::inspect(
            &document,
            &options,
            &sessions::Resources {
                asset_root,
                font_root,
            },
            &context.scoped(&control)?,
        ),
        Request::Prepress {
            document,
            options,
            asset_root,
            font_root,
            control,
        } => prepress::inspect(
            &document,
            &options,
            &sessions::Resources {
                asset_root,
                font_root,
            },
            &context.scoped(&control)?,
        ),
    };
    if !persistent {
        context.check()?;
    }
    result
}

pub(crate) fn inspect_item(
    document: &Document,
    i: usize,
    geometry: &mut scene::GeometryCache,
) -> Result<Value, Error> {
    let world = geometry.world(i);
    let bounds = geometry.bounds(i)?;
    let item = &document.items[i];
    let sibling_index = scene::children(document, item.parent.as_deref())
        .iter()
        .position(|&j| i == j)
        .unwrap();
    let image = match &item.content {
        model::Content::Image {
            asset_id,
            width,
            height,
            crop,
            sampling,
        } => Some(
            json!({"asset_id":asset_id,"width":width,"height":height,"crop":crop,"sampling":sampling}),
        ),
        _ => None,
    };
    let mut result = json!({"object":match &item.content{model::Content::Object{object}=>Some(object.summary()),_=>None},"hdr_grade":item.hdr_grade,"samples":samples::inspect(&item.content),"pixel_warp":item.pixel_warp,"metadata":item.metadata,"id":item.id,"name":item.name,"content_type":query::item_type(item),"warp":match &item.content{model::Content::Warp{warp}=>Some(warp),_=>None},"repeat":match &item.content{model::Content::Repeat{repeat}=>Some(repeat),_=>None},"interpolation":match &item.content{model::Content::Interpolation{interpolation}=>Some(interpolation),_=>None},"instance":match &item.content{model::Content::Instance{instance}=>Some(instance),_=>None},"artwork_mask_source_sha256":artwork_masks::dependency_hash(document,i)?,"component_source_sha256":instances::dependency_hash(document,i)?,"group":match &item.content{model::Content::Group{isolated,knockout,role}=>Some(json!({"isolated":isolated,"knockout":knockout,"role":role})),_=>None},"geometry":match &item.content{model::Content::Vector{geometry,..}|model::Content::WorkPath{geometry,..}=>Some(geometry),_=>None},"stroke":match &item.content{model::Content::Vector{stroke,..}=>stroke.as_ref(),_=>None},"index":i,"sibling_index":sibling_index,"parent":item.parent,"clip_to":item.clip_to,"visible":item.visible,"effective_visible":scene::effective_visible(document,i)?,"locked":item.locked,"effective_locked":scene::effective_locked(document,i)?,"opacity":item.opacity,"fill_opacity":item.fill_opacity,"coverage":item.coverage,"effects":item.effects,"blend":item.blend,"world_transform":world,"geometry_bounds":bounds,"clip":item.clip,"mask":item.mask,"artwork_mask":item.artwork_mask,"artwork_mask_world_transform":item.artwork_mask.as_ref().map(|m|m.world_transform(world)),"filters":item.filters,"mask_world_transform":item.mask.as_ref().map(|m|m.world_transform(world)),"image":image,"adjustment":match &item.content{model::Content::Adjustment{adjustment}=>Some(adjustment),_=>None},"frame":match &item.content{model::Content::Frame{frame}=>Some(frame),_=>None}});
    if matches!(
        &item.content,
        model::Content::WorkPath {
            geometry: model::Geometry::Compound { .. },
            ..
        }
    ) {
        result["geometry_bounds_semantics"] =
            json!("conservative_union_of_operand_geometry_not_tight_filled_result");
    }
    Ok(result)
}
