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
pub mod color_adjustments;
pub mod control;
pub mod coverage;
pub mod creative_filters;
pub mod detail_filters;
pub mod diff;
pub mod dimensions;
pub mod edit;
pub mod effects;
pub mod filters;
pub mod fonts;
pub mod geometry;
pub mod hdr;
pub mod hyphenation;
pub mod image_io;
pub mod ink_recipes;
pub mod inspection;
pub mod instances;
pub mod interpolation;
mod knockout;
mod layer_clipping;
pub mod layered;
pub mod layout;
pub mod masks;
pub mod mcp;
mod mcp_preview;
pub mod measurements;
pub mod meshes;
pub mod metadata;
pub mod model;
pub mod objects;
pub mod paint;
pub mod path_text;
pub mod paths;
pub mod pdf;
pub mod pixel_brush;
pub mod pixel_warps;
pub mod prepress;
pub mod primitives;
pub mod profiles;
pub mod proof;
pub mod publish;
pub mod query;
pub mod raw;
pub mod render;
pub mod render_quality;
pub mod repair;
pub mod repeats;
pub mod request;
mod resample;
pub mod responses;
pub mod retouch;
pub mod sample_convert;
pub mod sample_import;
pub mod sample_profiles;
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
pub mod strokes;
mod svg;
pub mod svg_import;
pub mod swatches;
pub mod text;
pub mod tracing;
pub mod transfer;
pub mod variants;
pub mod vector_canvas;
pub mod volumes;
pub mod warps;
mod work_paths;
pub mod workspace;

pub use model::{ColorSpace, Document, DocumentKind, MAX_DIMENSION, validate};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::path::PathBuf;

pub const MAX_REQUEST_BYTES: u64 = 16 * 1024 * 1024;
#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum ExportFormat {
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
    96.0
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(tag = "command", deny_unknown_fields)]
pub enum Request {
    #[serde(rename = "layered.import")]
    LayeredImport {
        source_path: PathBuf,
        #[serde(default)]
        expected_sha256: Option<String>,
        id: String,
        #[serde(default)]
        color_policy: assets::ColorPolicy,
        #[serde(default)]
        control: control::Options,
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
        font_bindings: Vec<svg_import::FontBinding>,
        #[serde(default)]
        font_root: Option<PathBuf>,
    },
    #[serde(rename = "capabilities")]
    Capabilities {},
    #[serde(rename = "schema")]
    Schema {},
    #[serde(rename = "schema.lookup")]
    SchemaLookup {
        /// Command name, shared type alias, or index to discover available names.
        name: String,
        /// One tagged variant or referenced definition listed in the schema outline.
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
        #[serde(default)]
        control: control::Options,
    },
    #[serde(rename = "session.publish")]
    SessionPublish {
        session_root: PathBuf,
        session_id: String,
        expected_revision: u64,
        output: publish::Options,
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
    pub message: String,
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
}
impl Error {
    pub fn new(code: &'static str, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
            operation_index: None,
            asset_id: None,
            font_id: None,
            artboard_id: None,
            item_id: None,
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
pub fn execute(request: Request) -> Result<Value, Error> {
    execute_controlled(request, &control::Control::default())
}
pub fn execute_controlled(request: Request, context: &control::Control) -> Result<Value, Error> {
    let persistent = matches!(
        request,
        Request::SessionCreate { .. }
            | Request::SessionApply { .. }
            | Request::Publish { .. }
            | Request::SessionPublish { .. }
            | Request::SequenceImport { .. }
            | Request::AssetImport { .. }
            | Request::FontImport { .. }
    );
    if !matches!(
        request,
        Request::SessionCreate { .. } | Request::SessionApply { .. }
    ) {
        context.check()?;
    }
    let result = match request {
        Request::LayeredImport {
            source_path,
            expected_sha256,
            id,
            color_policy,
            control,
        } => layered::import(
            &source_path,
            expected_sha256.as_deref(),
            id,
            color_policy,
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
        Request::VolumeInspect { document, id } => volumes::inspect(&document, &id),
        Request::AppearanceInspect { document, id } => appearance::inspect(&document, &id),
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
        } => sample_import::import(&source_path, id, resolution_ppi, color_policy),
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
        } => svg_import::import_controlled(
            id,
            source,
            font_bindings,
            font_root,
            resource_profile,
            &context.scoped(&control)?,
        ),
        Request::MeshInspect {
            mesh,
            space,
            parameters,
        } => meshes::inspect(&mesh, space, &parameters),
        Request::Capabilities {} => {
            let mut limits = json!({"request_bytes":MAX_REQUEST_BYTES,"document_bytes":model::MAX_DOCUMENT_BYTES,"dimension_pixels":MAX_DIMENSION,"items":model::MAX_ITEMS,"hierarchy_depth":scene::MAX_DEPTH,"path_commands":model::MAX_SEGMENTS,"stored_pixels":model::MAX_STORED_PIXELS,"batch_operations":edit::MAX_OPERATIONS,"render_pixels":render::MAX_RENDER_PIXELS,"render_work":render::MAX_RENDER_WORK,"group_buffer_pixels":render::MAX_BUFFER_PIXELS,"render_scale":[1,4],"gradient_stops_per_paint":paint::MAX_STOPS,"gradient_stops_and_anchors":paint::MAX_PAINT_SAMPLES,"pattern_tile_pixels":paint::MAX_PATTERN_PIXELS,"paint_work":paint::MAX_PAINT_WORK,"image_assets":assets::MAX_ASSETS,"asset_pixels":assets::MAX_ASSET_PIXELS,"import_bytes":assets::MAX_IMPORT_BYTES,"svg_image_copy_pixels":assets::MAX_ASSET_PIXELS});
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
            limits.as_object_mut().unwrap().extend(json!({"simplification_span":simplify::MAX_SPAN,"simplification_work":simplify::MAX_WORK}).as_object().unwrap().clone());
            limits.as_object_mut().unwrap().extend(json!({"boolean_inputs":booleans::MAX_INPUTS,"boolean_source_edges":booleans::MAX_EDGES,"boolean_flattened_edges":booleans::MAX_EDGES,"boolean_atomic_edges":booleans::MAX_ATOMS,"boolean_work":booleans::MAX_WORK}).as_object().unwrap().clone());
            let supported = json!({"vector":["rect","ellipse","rounded_rect","polygon","regular_polygon","star","path_conversion","anchor_handle_edits","exact_curve_split","contour_reverse","contour_join","certified_curve_simplification","polygon_boolean_operations","line","cubic","compound_path","solid_fill","linear_gradient","radial_gradient","freeform_gradient","editable_color_mesh","inline_pattern","certified_editable_vector_warps","editable_repeat_layouts","editable_object_interpolation","editable_vector_brush_patterns","editable_dash_patterns","dash_phase","variable_width_profiles","endpoint_arrowheads","stroke_expansion","gradient_stroke","centered_stroke","object_document_stroke_scaling","affine_transform"],"raster":["retained_pixel_deformation","canvas_crop","anchored_canvas_extent","editable_scene_scale","resolution_only_edit","layer_alpha_clipping","editable_tone_adjustments","editable_color_adjustments","clipped_adjustment_chains","composite_measurements","rgba8_inline_layers","pixel_replace_fill","affine_pixel_transforms","anchored_transforms","editable_fill_layers","affine_fill_layers","solid_gradient_pattern_fills","ordered_rgb_dither"],"shared":["shared_effect_lighting","effect_scaling","effect_contours","gradient_effect_colors","knockout_groups","content_fill_opacity","editable_layer_effects","seeded_dissolve","editable_artwork_masks","shared_nonprinting_mask_sources","pass_through_group_opacity_masks","nonprinting_work_paths","path_to_selection","path_to_vector_mask","saved_alpha_channels","named_ink_channels","channel_calculations","component_isolation","color_range_selection","connected_selection","image_guided_edge_refinement","editable_viewport_filters","groups","named_layers","geometric_clips","editable_grayscale_masks","mask_density_feather_invert_disable","linked_unlinked_masks","persistent_pixel_selections","selection_set_operations","selection_morphology","selection_to_mask","native_pixel_mask_application","alignment","distribution","explicit_id_selection","type_bounds_anchor_queries","placed_images","integer_pixel_crops","explicit_asset_relink","editable_text","character_style_ranges","paragraph_wrap","text_alignment","text_tracking","text_leading","text_ink_inspection","named_artboards","nested_frames","nonprinting_guides","guide_alignment","artboard_bleed","artboard_duplication","durable_sessions","grouped_undo_redo","named_snapshots","retry_receipts","cooperative_edit_cancellation"],"blend_modes":blending::MODES,"exports":["snapshot","apng_rgba8","ordered_png_sequence","svg_vector_normal_blend","png_rgba8","jpeg_explicit_matte","tiff_rgba8"],"paint_interpolation":["srgb","linear_rgb"],"gradient_alpha":"straight","freeform":"inverse_square_anchor_weights","pattern_sampling":"nearest_repeat","svg_paints":["solid","linear","radial","sampled_mesh"],"image_sampling":["nearest","bilinear_premultiplied_srgb","area_premultiplied_srgb","bicubic_premultiplied_srgb","lanczos3_premultiplied_srgb"],"imports":["png_8bit_normalized","jpeg_8bit_gray_rgb","tiff_8bit_gray_rgb_straight_alpha","svg_editable_geometry_gradients_clips","svg_editable_single_line_text","svg_editable_artwork_masks"],"asset_store":"sha256_rgba8_create_only","color":"encoded_srgb_rgba8","stack_order":"bottom_to_top_per_parent","text":{"scripts":["unicode_grapheme_script_runs"],"directions":["ltr","rtl","auto"],"auto_direction_requires":"bidi_unicode","bidi_modes":["single_run","unicode"],"alignment":["left","center","right","start","end"],"bidi":"explicit_single_run_or_unicode16_paragraphs", "bidi_inspection":"text.directions", "bidi_line_rules":"paragraph_resolution_then_L1_L2_then_shaper_L3_L4","fallback":"explicit_ordered_pinned_fonts_whole_run_then_grapheme","fallback_fonts":7,"language":"explicit_font_language_system_or_default","coverage":"shaped_glyphs_after_canonical_composition","shaping_context":"line_local_across_style_and_font_boundaries","fonts":"pinned_monochrome_sfnt_explicit_instances","font_variations":"per_font_axis_maps","axis_controls":16,"feature_controls":64,"feature_availability":"selected_font_tag_required_when_positive","tracking_liga":"explicit_feature_overrides_default_disable","font_inspection":"font.inspect","layout":"horizontal_unhinted_font_metrics_or_rigid_path_glyphs","glyph_compositing":"individual_ordered_paths","wrap":"ascii_space_or_grapheme","svg":"outlines","outline_conversion":"vector_documents"},"artboards":{"formats":["png","jpeg","tiff","svg_vector"],"selection":["all","ids","range_zero_based_end_exclusive"],"order":"hierarchy_preorder_sibling_stack","scope":"owned_subtree_local_coordinates","bleed":"integer_per_edge","frame_clipping":"always_on","background":"optional_solid_rgba"}});
            let commands = json!([
                "color.convert",
                "layered.import",
                "assist.segment",
                "assist.layout",
                "volume.inspect",
                "appearance.inspect",
                "sequence.import",
                "sequence.export",
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
                "document.boolean",
                "channel.export",
                "document.diff",
                "document.publish",
                "session.diff",
                "session.publish",
                "capabilities",
                "schema",
                "schema.lookup",
                "implementation.status",
                "session.create",
                "session.read",
                "session.apply",
                "session.receipt",
                "session.history",
                "session.verify",
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
                "document.inspect",
                "document.inspect.page",
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
            let svg_import_contract = json!({"source_bytes":svg_import::MAX_BYTES,"xml_nodes":svg_import::MAX_NODES,"elements":["svg","g","rect","ellipse","circle","line","polygon","polyline","path","title","desc","defs","linearGradient","radialGradient","stop","clipPath","text","mask","metadata"],"path_commands":"MmLlHhVvCcSsQqTtZz","paints":["solid_srgb_rgba8","linear","centered_radial"],"gradient_units":["userSpaceOnUse","objectBoundingBox"],"gradient_templates":"local_href_with_cycle_checks","template_stop_styles":"cloned_in_derived_gradient_context","clip_geometry":"single_shape_or_compound_path","definition_limit":svg_import::MAX_DEFINITIONS,"reference_depth":svg_import::MAX_REFERENCE_DEPTH,"resources":"local_definitions_and_explicit_pinned_fonts","text":{"kind":"editable_single_line_ltr","font_bindings":fonts::MAX_FONTS,"font_selection":"first_explicit_family_weight_style_match_no_glyph_fallback","anchors":["start","middle","end"],"baseline":"alphabetic","whitespace":"legacy_xml_space_or_explicit_css_normal_pre","object_box":"full_font_cells","span_children":false},"source_preserved":true,"unsupported_policy":"error_no_partial_document","viewport":"integral_pixels_at_96ppi_with_viewBox_meet_slice_none"});
            let mut capabilities = json!({
                "name":"inkbolt","version":env!("CARGO_PKG_VERSION"),"stage":"editing_core",
                "document_schema_version":2,"readable_document_schema_versions":[1,2],
                "commands":commands,
                "document_kinds":["vector","raster"],
                "limits":limits,
                "features":{"empty_documents":true,"editing":true,"rendering":true,"atomic_snapshot_batches":true,"native_import":false,"png_import":true,"jpeg_import":true,"tiff_import":true,"content_addressed_assets":true,"editable_text":true,"pinned_local_fonts":true,"artboards":true,"nested_frames":true,"artboard_range_exports":true,"sessions":true,"persistent_undo":true,"mcp_stdio":true,"create_only_publication":true,"semantic_diffs":true},
                "supported":supported,
                "mcp":{"transport":"stdio","protocol_version":mcp::PROTOCOL,"message_bytes":mcp::MAX_MESSAGE_BYTES,"response_bytes":mcp::MAX_RESPONSE_BYTES,"pending_requests":mcp::MAX_PENDING,"request_ids_per_connection":mcp::MAX_REQUEST_IDS,"default_timeout_ms":60000},
                "layer_clipping":{"document_kind":"raster","binding":"contiguous_sibling_base_id","source_alpha":"preserves_base_alpha","base_effects":"once_after_clipped_members","source_effects":"before_alpha_preserving_blend","base_visibility":"suppresses_whole_clipping_group","pass_through_groups":"premultiplied_backdrop_difference_interpolation"},
                "masks":{"storage":"inline_gray8","outside":"clip_zero_or_unclipped_one_before_density","inversion":"source_grid_only","feather":"separable_triangular_mask_pixel_radius","sampling":["nearest","bilinear"],"linking":"item_local_or_document_coordinates","composition":"one_multiply_after_item_or_isolated_group","svg":"processed_grayscale8_png_field","selection_to_mask":true,"permanent_application":"native_pixel_layers_images_and_fills"},
                "adjustments":{"operators":["color","invert","threshold","levels","posterize","curve","exposure","brightness_contrast","shadows_highlights"],"scope":["current_backdrop","preceding_sibling_before_composite"],"alpha":"preserved","precision":"f64_then_final_rgba8","curve":"piecewise_linear_encoded_srgb","exposure":"linear_srgb","mask_and_clip":true,"clip_to":"stable_sibling_id_with_contiguous_chain"},
                "filters":{"operators":["creative","detail","spatial","box","gaussian","directional","radial","surface"],"domain":"render_viewport_after_geometry_before_item_effects","precision":"premultiplied_f64_encoded_srgb_to_requested_output_depth","radius_units":"document_pixels_scaled_by_export_scale","radial_center":"item_local","border":["transparent","clamp","reflect","wrap"],"stack_order":"first_to_last","masks":"shared_grayscale_controls","blend_modes":blending::MODES,"input_depth":8,"detail_operators":["sharpen","unsharp","median","noise"],"spatial_operators":["offset","displace","mosaic"],"noise_distribution":["uniform","gaussian"],"noise_seed":"u32_sha256_coordinate_v1","detail_alpha":"preserved","median_radius":[0,8],"sharpen_amount":[0,8],"spatial_offset":[-256,256],"mosaic_size":[1,128],"box_radius":[0,32],"gaussian_sigma":[0,16],"surface_radius":[0,16],"directional_length":[0,64],"trajectory_samples_odd":[3,129],"svg":false},
                "color_adjustments":{"operators":["hue_saturation","desaturate","channel_mixer","balance","selective","lut1d","lut3d","gradient_map"],"working_space":"straight_encoded_srgb","clipping":"after_each_operator","lookup_domain":"per_channel_clamp","lookup_order":"red_fastest_green_then_blue","lookup_3d_interpolation":"trilinear","gradient_map_interpolation":["srgb","linear_rgb"],"alpha":"preserved","profile_conversion":false},
                "measurements":{"source":"scale_one_rgba8_composite","histogram_bins":256,"weight_denominator":65025,"selection":true,"alpha_policies":["ignore","exclude_transparent","weight"]},
                "work_paths":{"document_kinds":["vector","raster"],"printing":false,"coverage":"f64_monotone_cubic_roots_256_subrows_gray8","vector_mask_coverage":"tiny_skia_f32_gray8","selection":"copied_world_geometry","vector_mask":"independent_item_local_clip_copy","source_appearance":"ignored_including_ancestor_effects","compound_operations":"document.boolean_with_existing_curve_certificate_limits","snapshot_persistence":true},
                "paths":{"indexing":"revision_scoped_command_indices","split":"de_casteljau_exact_up_to_f64_roundoff","join":["exact_coincident","explicit_bridge"],"reverse":"selected_contours_preserve_closed_seam","simplify":true,"primitive_corners":"normalized_quarter_cubics","ellipse_conversion":"four_cubic_approximation"},
                "booleans":{"command":"document.boolean","modes":["union","intersection","difference","xor"],"output":"root_coordinate_nonzero_polygon_or_null","arithmetic":"exact_rational_arrangement_then_checked_f64_vertices","curve_model":"bounded_chords_with_exact_topology_certificate","curve_coincidence":"exact_noncollinear_polynomial_affine_parameter_normalization","curve_subdivision":"invariant_within_operand_for_exact_encoded_polynomials","curve_topology":"certified_simultaneous_deformation_or_explicit_failure","curve_contacts":"verified_rational_endpoint_line_and_graph_contacts","curve_contacts_remaining":"non_rational_parameters_and_general_contacts_may_exceed_certificate_limits","analytic_ellipses":"explicit_path_conversion_required","source_mutation":false},
                "curve_simplification":{"space":["local","world"],"deviation":"exact_rational_bernstein_control_bound","topology":"monotone_swept_hulls_disjoint_except_fixed_shared_endpoints","scope":"compound_path_including_fill_closure","unproven_candidates":"retained_with_reasons","receipt":"per_reduction_exact_bound_and_parameter_map"},
                "channels":{"storage":"canvas_gray8","nonprinting":true,"roles":["alpha","spot"],"components":["red","green","blue","alpha","luma"],"calculations":["copy","add","subtract","difference","multiply","screen","minimum","maximum","average"],"spot_identity":"unique_ink_id_with_alternate_srgb_and_exact_tint_coverage","export":"gray_or_alternate_ink_preview_png_with_metadata"},
                "selection_analysis":{"source":"scale_one_rgba8_composite","distance":"maximum_absolute_component_difference","components":["rgb","rgba"],"methods":["color_range","connected","edge"],"connectivity":["four","eight"],"edge":"color_gated_triangular_integer_weights_then_levels"},
                "pixel_selection":{"coordinates":"document_grid","storage":"gray8","nonprinting":true,"combine":{"add":"maximum","subtract":"saturating_difference","intersect":"minimum"},"morphology":"square_max_min_zero_outside","feather":"separable_triangular_zero_outside","mask_application":"native_pixel_centers_then_rgba8_quantization"},
                "publication":{"output_bytes":publish::MAX_OUTPUT_BYTES,"overwrite":"never","root":"explicit_existing_local_directory","formats":["pdf","png","jpeg","tiff","svg","snapshot"]},
                "session_contract":{"storage_version":sessions::STORE_VERSION,"backend":"sqlite_rollback_full_sync","conflicts":"expected_revision","retry":"original_receipt_and_document","history":"immutable_states_no_eviction","resources":"external_explicit_roots","cancellation":"cooperative_precommit","export":"read_document_then_export_returned_snapshot"},
                "unsupported":unsupported,
            });
            capabilities["filters"].as_object_mut().unwrap().extend(json!({"creative_operators":["twist","relief","high_pass","extrema","tone_fold","edge_ink","stroke_rank","value_field","field_repair"],"creative_contract":"docs/CREATIVE_FILTERS.md","creative_alpha":"center_preserved_except_twist_and_field_repair","creative_coordinates":"item_local_twist_and_value_field;output_grid_field_repair;document_units_other_kernels"}).as_object().unwrap().clone());
            capabilities["ink_recipes"] = json!({"field":"ink_recipe","operation":"ink_recipe","inspect":"document.inspect","separations":"document.separations","source":"retained_canvas_gray8_channels","source_roles":"explicit_recipe_overrides_saved_channel_role_metadata","source_mask":"optional_independent_gray8_channel","inks":[1,ink_recipes::MAX_INKS],"curve_knots":[2,ink_recipes::MAX_KNOTS],"curve":"piecewise_linear_exact_binary64_rationals;nonmonotone_outputs_allowed","sample_projection":"curve(source/255)*mask_byte;nearest_u8_once_ties_up","scale":[1,4],"resampling":"integer_nearest_replication","plates":"scalar_gray8_PNG_no_colour_profile_or_transfer_tag","preview":["declared_linear_rgb_corners","declared_transmittance_paper_and_ink_srgb"],"corner_precision":16,"corner_order":"first_ink_fastest;zero_is_paper","preview_work":ink_recipes::MAX_WORK,"preview_interpolation":"multilinear_linear_rgb_then_srgb_encoding","pdf":"pdf_options.ink_recipe;whole_canvas_DeviceN_image;exact_ink_amounts;calculator_linear_mix_to_srgb_ICC_alternate","pdf_colorant_identity":"Inkbolt.<ink_id>","source_mutation":false,"ordinary_artwork":"excluded_from_explicit_recipe_delivery;ordinary_render_ignores_nonprinting_recipe","persistence":"snapshot_atomic_edits_sessions_undo_redo","combined_process":"pdf_options.print.named_inks;explicit_multiplicative_cmyk_alternates;whole_canvas_NChannel","unsupported":["recipe_artboard_crops_and_bleed","physical_press_calibration","implicit_ink_merging","spectral_ink_models"]});
            capabilities["sample_profiles"] = json!({"operation":"sample_profile","actions":["assign","convert"],"source":"inline_rgba8_or_normalized_sample_grid","models":["rgb"],"depths":["u8","u16","f32"],"intents":["relative_colorimetric","absolute_colorimetric","perceptual","saturation"],"view_intent":"relative_colorimetric","profile_null":"explicit_working_srgb","source_encoding":"profiled_rgb","assignment":"native_values_unchanged","conversion":"native_rgb_rewritten;alpha_exact;gray_promoted_to_rgba_when_needed","linear_compositing":"source_profile_to_linear_srgb_before_reconstruction","black_point_compensation":false,"profile_encoded_bytes_per_document":sample_profiles::MAX_ENCODED_PROFILE_BYTES,"unknown_external_input":"existing_explicit_import_policy","unsupported":["signed_hdr_profile_assignment","non_rgb_icc_source_models","implicit_profile_discard"]});
            capabilities["work_paths"]["compound_operations"] = json!(
                "retained_union_intersection_difference_xor;membership_before_coverage;independent_source_copies"
            );
            capabilities["work_paths"]["compound"] = json!({"combine":"work_path_combine","edit":"path_component","geometry":"compound","max_leaves":work_paths::MAX_COMPONENTS,"max_depth":work_paths::MAX_COMPONENT_DEPTH,"operands_per_operation":[2,16],"bounds":"union_of_operand_geometry_not_tight_filled_result","vector_mask_coverage":"shared_f64_region_scanlines_gray8","clip_pixel_limit":262144,"flattened_boolean":"separate_document.boolean_contract","unsupported":["painted_compound_vector_content","implicit_polygonal_expansion","direct_svg_pdf_active_compound_clips"]});
            capabilities["sample_profiles"]["builtin_definition_revision"] =
                json!("0.73_D50_media_white_Bradford_D65_to_D50");
            capabilities["sample_profiles"]["precision"] = json!(
                "bounded_normalized_curve_tables_then_signed_linear_matrix;nonlinear_destination_clips_before_inverse_transfer"
            );
            capabilities["vector_strokes"] = json!({"caps":["butt","round","square"],"joins":["miter","round","bevel"],"miter_limit":[1,16],"width":[0.001,1024],"dash_intervals":strokes::MAX_INTERVALS,"dash_interval":"zero_or_0.001_to_32768","dash_offset":[-32768,32768],"scaling":["object","document"],"default_scaling":"object","dash_units":"declared_stroke_space","document_scaling":"world_centerline_then_outline_in_logical_units","paint_coordinates":"item_local","mask_instances":"per_reference_world_placement","artboard_coordinates":"independent_export_viewport","odd_dash_list":"repeat_twice","empty_or_all_zero":"solid","phase_reset":"each_subpath","dash_document_work":strokes::MAX_DOCUMENT_WORK,"dash_instance_work":strokes::MAX_INSTANCE_WORK,"dash_range_work":strokes::MAX_RANGE_WORK,"curve_dashing":"original_f64_flattened_arclength","curve_tolerance":{"default":strokes::default_tolerance(),"range":[0.0000001,1],"units":"declared_stroke_space","automatic_refinement":"min_saved_and_1_over_64_divided_by_max_1_and_16_times_world_stretch_bound","outline_resolution":strokes::OUTLINE_RESOLUTION,"shared_outline":"current_placement_across_render_expansion_and_outlined_exports","stored_controls_preserved":true,"error_scope":"centerline_chord_length_and_round_sector_subdivision_not_global_offset_topology_or_raster"},"variable_width":true,"width_profile":{"knots":[2,64],"form":"normalized_contour_distance_and_width_factor","factor":[0,1024],"maximum_resulting_width":1024,"closed_endpoints":"equal_factors","dash_reset":false},"arrowheads":true,"arrow_shapes":["triangle","chevron","diamond","ellipse","bar"],"arrow_length_width":[0.001,1024],"arrow_placement":"each_contour_endpoint_original_tangent","arrow_attachment":"half_length_shaft_trim_with_butt_cut","editable_expansion":true,"expansion_operation":"stroke_expand","expansion_future_scaling":"filled_geometry_follows_object","document_scaled_definition_expansion":"unsupported_unlink_placement_first","expansion":"isolated_group_with_preserved_centerline_and_nonzero_outline","generated_document_commands":strokes::MAX_OUTLINE_COMMANDS,"generated_scan_work":render::MAX_RENDER_WORK,"svg_outline_commands":strokes::MAX_SVG_COMMANDS,"svg_range_outline_commands":strokes::MAX_SVG_RANGE_COMMANDS,"svg_advanced_controls":"filled_outlines_with_explicit_editability_loss"});
            capabilities["supported"]["exports"]
                .as_array_mut()
                .unwrap()
                .push(json!("pdf_native_paths_and_pages"));
            capabilities["supported"]["text"]["pdf"] = json!("outlines");
            capabilities["pdf"] = json!({"version":"1.7;2.0_for_managed_colour_or_calibrated_page","format":"pdf","page_selection":"pdf_options.artboards_all_ids_or_range;omitted_canvas","scale":1,"physical_units":"72_points_per_inch_from_document_resolution","boxes":["MediaBox","CropBox","BleedBox","TrimBox"],"bleed":"pdf_options.include_bleed_requires_artboards","coordinates":"bottom_left_pdf_user_units","user_unit":"ceil_largest_physical_dimension_divided_by_14400_minimum_1","maximum_user_unit":75000,"pages":boards::MAX_ARTBOARDS,"path_commands":pdf::MAX_COMMANDS,"objects":pdf::MAX_OBJECTS,"image_pixels":pdf::MAX_IMAGE_PIXELS,"output_bytes":publish::MAX_OUTPUT_BYTES,"text":"outlined_variable_and_shaped_glyphs_no_font_embedding_or_search","color":"pdf_options.color:display_DeviceRGB_or_native_inks_DeviceCMYK_blending","paints":["solid","axial_pad_srgb_constant_alpha","radial_pad_srgb_constant_alpha"],"images":"verified_crops_nearest_rgb_with_gray8_soft_mask","groups":"normal_isolated_or_pass_through_no_knockout","clips":"geometric_and_frame","strokes":"shared_generated_outlines","metadata":"selected_page_public_or_strip_packets_in_RDF_XML","output_profile":"explicit_RGB_ICCBased_page_and_isolated_groups;DefaultRGB_srgb;PDF2_BPC_OFF","unsupported":["non_normal_blends","knockout","effects","filters","dissolve","pixel_warps","layer_clipping","active_opacity_and_artwork_masks","adjustments","dither","other_gradient_semantics","non_nearest_images","editable_reimport","encapsulated_pages"],"publication":"create_only_after_complete_export"});
            capabilities["image_io"] = json!({"formats":["png","jpeg","tiff"],"jpeg":{"import":"8bit_gray_rgb_baseline_progressive","quality":[1,100],"default_quality":90,"chroma":["full","half"],"default_chroma":"full","alpha":"explicit_rgb_matte_required_when_transparent","density":"rounded_whole_ppi","lossless":false},"tiff":{"samples":"unsigned8_gray_grayalpha_rgb_rgba","alpha":"explicit_unassociated","white_is_zero":"gray_without_alpha","import_compression":["none","lzw","deflate","packbits"],"export_compression":["none","lzw","deflate"],"default_compression":"deflate","byte_orders":["little","big"],"bigtiff_import":true,"storage":["strips","tiles","chunky","planar"],"orientation":"top_left_only","pages":1,"density":"rounded_0.001_ppi","lossless":true},"jpeg_tiff_color":"explicit_input_policy_and_optional_profiled_output","profiles":true,"source_preserved":true,"output_settings_in_receipts":true});
            capabilities["pixel_warps"] = json!({"field":"item.pixel_warp","targets":["inline_raster","placed_image_crop"],"maps":["perspective","mesh","articulated"],"source":"retained_original_pixels_and_asset_identity","coordinates":"image_local_before_item_and_ancestors","mesh":"regular_source_grid_piecewise_affine","diagonal":"top_left_bottom_right","axis_intervals":[1,16],"joints":[1,16],"joint_pose":"parent_times_pivot_rotation_translation","weights":"per_vertex_normalized_sum_one_within_1e-10","inverse":"unique_simple_consistently_oriented_triangulated_disk","folds":false,"reflection":true,"minimum_altitude":0.0009765625,"minimum_relative_twice_area":9.5367431640625e-07,"sampling":["nearest","bilinear_premultiplied_srgb"],"coverage":"whole_boundary_once_no_triangle_alpha_seams","outside":"transparent_nearest_boundary_color_for_antialias","perspective_edge_color":"projective_inverse_of_nearest_destination_boundary_point","inspect":"pixel_warp.inspect","edit":"pixel_warp","clear":"warp_null","sample_limit":256,"render_work":67108864,"stored_controls":4096,"svg":"explicitly_unsupported_use_pixel_exports_and_snapshot","native_grid_edits":"clear_controls_first_for_brush_retouch_repair_mask_bake","unsupported":["folded_overlapping_meshes","singular_or_ill_conditioned_triangles","advanced_reconstruction_kernels","nonimage_content"]});
            capabilities["warps"] = json!({"content":"warp","maps":["affine","perspective","envelope"],"order":"source_then_ordered_maps_then_item_and_ancestors","nesting":"exact_homogeneous_bernstein_composition","perspective":"convex_quad_exact_projective_map","perspective_weights":[0.0009765625,1024],"envelope":"row_major_4_by_4_absolute_bicubic_controls","domain":"positive_control_hull_contained_no_extrapolation","appearance":"paint_and_stroke_after_geometry_deformation","fill":"explicit_closed_contours","open_centerlines":"fill_null","certificate":"exact_rational_homogeneous_bernstein_vs_encoded_parameter_chord","tolerance":[1e-06,1],"default_tolerance":0.01,"tolerance_units":"warp_local","source_interpretation":"ordinary_line_cubic_primitive_expansion","map_count":[1,8],"source_edges":256,"maximum_degree":128,"rational_bits":8192,"subdivision_depth":24,"arithmetic_work":2000000,"generated_commands":4096,"samples":256,"grid_intervals":[1,16],"grid":"reusable_open_path_with_segment_certificates","inspect":"warp.inspect","edit":"warp","expansion":"warp_expand_ordinary_vector","bounds":"expanded_geometry_excluding_stroke_and_clipping","svg":"ordinary_path_with_explicit_editability_loss","unsupported":["pixel_warps","arbitrary_hierarchy_envelopes","implicit_open_fill_closure","out_of_domain_hulls","inverse_or_topology_guarantees"]});
            capabilities["repeats"] = json!({"content":"repeat","layouts":["grid","brick","hex","radial"],"mirror":["none","columns","rows","both"],"copies":[1,128],"motifs":"closed_line_cubic_and_expanded_primitives","paint_coordinates":"repeat_local_global_field","coverage":"combined_fill_once","winding":"reflections_preserve_authored_winding","seams":"coincident_edges_share_coverage_no_automatic_boundary_synthesis","brick_axis":["rows","columns"],"brick_offset":[0,1],"hex_orientation":["pointy","flat"],"radial_orientation":["fixed","radial","tangent"],"closed_radial":"full_signed_turn_terminal_copy_excluded","open_radial":"signed_subturn_both_endpoints_included","transforms":["motif_relative_to_anchor","whole_layout","item_and_ancestors"],"bounds":"geometry_excluding_effects_and_clipping","inspect":"repeat.inspect","edit":"repeat","expansion":"repeat_expand_compound_vector","svg":"compound_path_with_explicit_editability_loss","generated_commands":4096,"unsupported":["open_motifs","per_copy_paint_restart","arbitrary_multicolor_hierarchy_motif"]});
            capabilities["interpolation"] = json!({"content":"interpolation","count":[2,128],"count_includes_endpoints":true,"endpoints":"vector_geometry_solid_fill_matching_stroke_controls","colors":"premultiplied_then_single_rgba8_encoding","spaces":["srgb","linear_rgb"],"correspondence":"uniform_authored_segment_fractions_exact_cubic_subdivision","unmatched_contours":"control_hull_center_collapse_or_grow","seam":"explicit_destination_segment_offset","anchors":"explicit_or_analytic_geometry_center","placement":["straight","one_contour_line_cubic_spine"],"orientation":["fixed","tangent"],"reversal":["endpoint_order","spine_traversal"],"spine_tolerance":[1e-06,0.25],"spine_leaves":32768,"document_spine_leaves":65536,"closed_spine":"both_endpoints_included_explicit_subspan_available","expansion":"interpolation_expand_isolated_group","inspect":"interpolation.inspect","bounds":"unclipped_geometry_excluding_stroke","svg":"ordinary_paths_with_explicit_editability_loss","unsupported":["arbitrary_layer_endpoints","non_solid_endpoint_paints","differing_stroke_controls","direct_open_closed_pair","undefined_spine_tangent"]});
            capabilities["vector_brushes"] = json!({"field":"stroke.brush","model":"rigid_filled_motifs_on_evaluated_centerline","motif_geometry":"closed_line_cubic_and_expanded_primitives","motif_coordinates":[-16,16],"fill_rule":"combined_nonzero_paint_once","spacing":[0.001,1024],"phase":[-32768,32768],"units":"base_stroke_width","fit":["fixed","uniform"],"profile":"whole_contour_uniform_motif_scale","corners":["bisector","incoming","outgoing"],"corner_angle":[0.1,180],"clearance":[0,1024],"corner_sites":"original_command_anchors_evaluated_adjacent_tangents","closed_distance":"cyclic","endpoints":"open_contours_only_forward_tangent","scaling":["object","document"],"expansion":"stroke_expand","svg":"filled_outlines_with_editability_loss","inspect":"document.inspect_saved_controls","distance_precision":"16_epsilon_times_point_count_times_length_plus_sum_max_abs_evaluated_coordinates","ambiguous_intervals":"unsupported_above_quarter_step","maximum_conservative_placements":strokes::MAX_BRUSH_PLACEMENTS,"work":"combined_stroke_placement_commands_and_corner_comparisons","unsupported":["warped_motifs","dash_or_arrow_combinations","nondefault_cap_join_miter"]});
            capabilities["repair"] = json!({"operation":"repair","actions":["patch","fill","move","edge_correct"],"coordinates":"native_pixel_grids","sources":"explicit_frozen_inline_pixels","patch_search":"exhaustive_integer_translation;context_rms_then_requested_distance_then_row_major","fill_search":"exhaustive_complete_valid_donor_patches;source_row_major_ties","fill_priority":"most_known_context_cells_then_target_row_major","fill_patch_radius":[1,4],"self_donors":"exclude_entire_positive_domain","move":"synthesize_source_then_copy_frozen_original_to_integer_offset","edge_correction":"guided_per_channel_weighted_median","guide_radius":[1,16],"quality":["required_context_rms","required_final_change_rms","minimum_effective_guide_support","optional_final_boundary_rms"],"quality_failure":"atomic_REPAIR_QUALITY","maximum_patches":repair::MAX_PATCHES,"work":repair::MAX_WORK,"automatic_semantic_reconstruction":false});
            capabilities["retouch"] = json!({"operation":"retouch","modes":["clone","heal"],"target_source":"explicit_inline_native_pixel_layers","sampling":["nearest","bilinear_premultiplied_srgb"],"borders":["error","transparent","clamp"],"source_transform":"target_native_to_source_native_affine","source_state":"frozen_before_operation","region":"native_integer_rectangle_with_optional_gray8","selection":"optional_world_mapped_native_centers","healing":"four_neighbor_boundary_constrained_source_correction","screening":[0,16],"residual_tolerance":[0.000000000001,0.0001],"maximum_iterations_per_channel":retouch::MAX_ITERATIONS,"work":retouch::MAX_WORK,"output":"masked_premultiplied_replacement_once_rgba8","measurements":["source_target_result_hashes","domain_bounds_components_perimeter","changed_pixels_bounds","boundary_rms","solver_residuals_iterations","clamped_pixels"],"automatic_donor_selection":false});
            capabilities["pixel_brushes"] = json!({"operation":"brush_stroke","inspect":"brush.inspect","target":"inline_native_pixel_layer","modes":["paint","erase","smudge","mixer"],"diameter":[0.25,512],"hardness":"unit_inner_radius;quadratic_radial_falloff","spacing":"0.01_to_4_times_base_diameter","point_dynamics":["size","opacity"],"flow":"per_dab","opacity":"whole_stroke_premultiplied_interpolation","scatter":"seeded_uniform_square;0_to_4_radii","texture":"native_center_sampled_repeating_gray8","selection":"optional_world_mapped_native_centers","smudge":"pre_dab_surface_bilinear_translation","mixer":"premultiplied_coverage_weighted_pickup_and_explicit_load","coverage":"analytic_circle_cell_area_and_adaptive_squared_radius_integration","coverage_numeric_tolerance":pixel_brush::COVERAGE_TOLERANCE,"points":pixel_brush::MAX_POINTS,"dabs":pixel_brush::MAX_DABS,"work":pixel_brush::MAX_WORK,"texture_pixels":pixel_brush::MAX_TEXTURE_PIXELS,"quantization":"once_per_stroke_rgba8","source_retention":"snapshot_edits_and_session_undo","hardware":false});
            capabilities["image_tracing"] = json!({"command":"image.trace","source":["rgba8_pixels","verified_image_asset"],"modes":["binary_alpha_or_encoded_luma","exact","quantized","explicit_palette"],"geometry":"exact_classified_unit_cell_boundaries","foreground_connectivity":4,"background_connectivity":8,"corners":"all_noncollinear_preserved","noise":["minimum_color_component_area","maximum_uniform_surround_transparent_hole_area"],"source_pixels":tracing::MAX_PIXELS,"result_colors":tracing::MAX_COLORS,"unit_edges":tracing::MAX_EDGES,"output_commands":model::MAX_SEGMENTS,"provenance":"normalized_options_and_input_output_grid_hashes_in_receipt_and_document_metadata","editable_output":"ordinary_nonzero_filled_paths","source_preserved":true,"cooperative_cancellation":true,"smooth_curve_fitting":false});
            capabilities["path_text"] = json!({"frame_field":"path","document_kinds":["vector","raster"],"geometry":"one_contiguous_line_cubic_or_expanded_primitive_contour","placement":"rigid_shaped_glyph_midpoint_tangent","edit":"text_and_text_range","offsets":["start_offset","normal_offset"],"flip":"reverse_traversal_without_reflection","closed":"one_finite_lap","overflow":["error","midpoint_clip","visible_endpoint_tangent_extension"],"inspection":"text.inspect_baseline_path_and_glyph_path","nominal_frame":"retained_for_alignment_not_path_clipping","distance_table":"adaptive_length_gap_and_uniform_parameter_deviation","tolerance":[0.000001,0.25],"default_tolerance":0.001,"max_commands":path_text::MAX_COMMANDS,"max_leaves":path_text::MAX_LEAVES,"max_document_leaves":path_text::MAX_DOCUMENT_LEAVES,"svg":"placed_outlines_with_text_paths_receipts","editable_interchange":"snapshot","source_fonts":"existing_explicit_pinned_font_contract","multiline":false,"native_svg_text_path_import":false});
            capabilities["meshes"] = json!({"paint":"mesh","edit":"mesh_knot","inspect":"mesh.inspect","grid":"row_major_shared_bicubic_knots","axis_range":[2,meshes::MAX_AXIS],"domain":"fixed_rectangle_with_zero_boundary_offsets","outside":"transparent","geometry":"normalized_displacement_contraction","max_contraction":meshes::MAX_CONTRACTION,"inverse_steps":meshes::INVERSE_STEPS,"continuity":"C1_in_declared_interpolation_space_up_to_f64_roundoff","color_bounds":"shared_derivative_limiter","alpha":"straight_linear","inspection_samples":meshes::MAX_SAMPLES,"svg":"sampled_png_paint_with_explicit_interior_error_bounds","svg_samples_per_cell":[1,256],"svg_default_samples_per_cell":16,"max_texture_pixels":meshes::MAX_TEXTURE_PIXELS,"max_svg_texture_pixels":meshes::MAX_SVG_TEXTURE_PIXELS,"editable_interchange":"snapshot","curved_outer_boundary":false,"folds":false});
            capabilities["metadata"] = json!({"records":"document_and_item","operation":"metadata","public_fields":["title","description","author","rights","note","tags","properties"],"private_fields":"private_map_saved_in_source_snapshots_only","export_policy":["public","strip"],"default_delivery":"public","default_snapshot":"source","record_bytes":metadata::MAX_RECORD_BYTES,"document_bytes":metadata::MAX_DOCUMENT_BYTES,"envelope_bytes":metadata::MAX_PACKET_BYTES,"formats":["snapshot","png_itxt","jpeg_numbered_comments","tiff_description","svg_namespaced_root","pdf_selected_pages_rdf_xml"],"resource_manifest":"content_and_license_hashes_without_runtime_paths","provenance":"deterministic_canonical_sanitized_snapshot_sha256","source_metadata_trust":"untrusted_description_not_authentication","orientation":"top_left_only_unsupported_input_orientation_rejected","resolution":"document_ppi_times_scale_with_format_rounding","profiles":"existing_explicit_color_contract_preserved","privacy_scope":"descriptive_records_not_artwork_text_names_or_profile_contents"});
            capabilities["color_profiles"] = json!({"working":"encoded_srgb_rgba8","output_association":"output_profile","edit":"output_profile","input_policy":"convert_srgb","explicit_input":"input_profile","builtins":["srgb","linear_srgb","display_p3"],"icc_versions":[2,4],"samples":"rgb8","connection_spaces":["xyz","lab"],"intent":"relative_colorimetric","black_point_compensation":false,"cicp_override":false,"profile_bytes":profiles::MAX_PROFILE_BYTES,"profile_tags":profiles::MAX_PROFILE_TAGS,"transform_stack_bytes":profiles::TRANSFORM_STACK_BYTES,"precision":"scalar_float_api_finite_resolution_tables_then_one_rgb8_round","alpha":"unchanged","embedding":["png","jpeg","tiff","calibrated_vector_pdf"],"jpeg_matte":"working_srgb_before_conversion","builtin_date":"2000-01-01T00:00:00","source_profile_bytes":"preserved_exactly","svg_profiled_output":false,"preview":"working_srgb"});
            capabilities["document_transfer"] = json!({"operation":"transfer","document_kinds":["vector","raster"],"source":"immutable_snapshot","selection":"subtrees_with_ancestor_context_and_transitive_references","prefix_characters":[1,32],"item_identity":"explicit_map_prefix_or_sha256_suffix","collisions":"atomic_error_never_replace","names":"duplicates_preserved","placement":"preserve_world_under_optional_destination_parent","resources":"referenced_descriptors_only_external_bytes_unchanged","verify_resources":"optional_destination_root_checks","source_variants":"selected_values_copied_definitions_omitted","global_lighting":"source_directions_pinned_locally","persistence":true});
            capabilities["variants"] = json!({"document_kinds":["vector","raster"],"operations":["variants_set","variant_select","variants_clear"],"properties":["name","visible","opacity","fill_opacity","position","transform","text","image"],"max_bindings":variants::MAX_BINDINGS,"max_datasets":variants::MAX_DATASETS,"max_inheritance":variants::MAX_INHERITANCE,"data":"typed_keyed_values","selection":"captured_base_then_inherited_property_subsets","text_ranges":true,"image_values":"explicit_pinned_asset_ids","inactive_resources":"retained_validated_and_lock_checked","unrelated_edits":"preserved","direct_controlled_edits":"explicit_error","clear_modes":["restore_base","bake_current"],"persistent":true,"exports":"selected_row_with_state_hash_and_explicit_metadata_loss"});
            capabilities["components"] = json!({"document_kinds":["vector"],"source":"top_level_nonprinting_component_source","placement":"isolated_instance","max_definitions":instances::MAX_DEFINITIONS,"max_nesting":instances::MAX_NESTING,"max_evaluated_items":model::MAX_ITEMS,"overrides":["name","visible","opacity","fill_opacity","blend","transform","content","vector_style"],"operations":["instance","instance_unlink"],"shared_edits":true,"local_overrides":true,"replacement":true,"unlink":true,"persistent":true,"dependency_locks":true,"unlinked_definition_masks":"per_instance_definition_space","svg":"expanded_independent_groups_with_editability_loss","artboards_in_definitions":false,"svg_use_import":false});
            capabilities["layer_effects"] = json!({"operators":["shadow","lit_shadow","stroke","overlay"],"global_light":true,"local_light_override":true,"effect_scale":[0.001,1024],"effective_kernel_limits_preserved":true,"contour":"piecewise_linear_2_to_64_knots_origin_zero","colors":"shared_solid_linear_radial_freeform_pattern_paints","color_coordinates":"item_local_follow_world_transform_independent_of_effect_scale","max_per_item":effects::MAX_STACK,"max_per_document":effects::MAX_DOCUMENT_EFFECTS,"max_work":effects::MAX_WORK,"domain":"viewport_after_filters_and_clipped_members","fill":"content_only_effect_source_alpha_unchanged","order":["shadows","content_and_overlays","strokes","item_masks_opacity_coverage_blend"],"units":"document_pixels_scaled_by_export_scale","stroke_radius":[0,32],"stroke_positions":["outside","inside","center"],"stroke_metric":"euclidean_integer_disk","shadow_sigma":[0,16],"shadow_offset":[-256,256],"source_mutation":false,"svg":false});
            capabilities["coverage"] = json!({"modes":["smooth","dissolve"],"seed":"u32","hash":"sha256_item_local_unit_cell_v1","threshold":"midpoint_first_little_endian_u32","domain":"after_fill_effects_masks_and_opacity","export_scale":"same_local_unit_cells","non_drawables":false});
            capabilities["blending"] = json!({"working_space":"straight_encoded_srgb","compositing":"premultiplied_f64_source_over","families":26,"nonseparable_luminance":[0.3,0.59,0.11],"comparison_tie_epsilons":8,"fill_opacity":true,"knockout":true,"knockout_shape":"intrinsic_alpha_before_fill_and_opacity","knockout_nested_groups":true,"knockout_mask_sources":false,"knockout_backdrop_adjustments":false,"knockout_max_work":render::MAX_RENDER_WORK,"dissolve":true,"svg":"normal_only"});
            capabilities["artwork_masks"] = json!({"source":"top_level_nonprinting_mask_source","content":["vector","text","isolated_group","geometric_clip","validated_component_instance"],"modes":["alpha","luminance"],"working_space":"premultiplied_encoded_srgb_f64","luminance_coefficients":[0.2125,0.7154,0.0721],"region":"optional_transformed_rectangle","linking":"item_local_or_document_coordinates","sharing":"stable_source_id_with_dependent_lock_checks","operations":["artwork_mask","artwork_mask_link","artwork_mask_transform"],"svg":"per_reference_vector_copies_with_reported_identity_loss","svg_import":true,"nested_source_masks":false,"grid_mask_coexistence":false});
            capabilities["reconstruction"] = json!({"methods":["area","bicubic","lanczos3"],"bicubic_parameter":-0.5,"lanczos_radius":3,"footprint":"inverse_pixel_source_axis_bounds","downsample":"widen_and_normalize_each_axis","area":"exact_box_cell_overlap","alpha":"premultiplied_with_final_valid_rgba_projection","border":"clamp_to_source_crop","max_axis_taps":resample::MAX_AXIS_TAPS,"max_work":resample::MAX_WORK,"svg":false,"scalar_masks":false,"displacement_maps":false});
            capabilities["canvas_operations"] = json!({"document_kinds":["raster"],"operation":"canvas","actions":["crop","extent","scale","resolution"],"sampling":["nearest","bilinear","area","bicubic","lanczos3"],"sampling_boundary_epsilon_factor":8,"extent_anchors":"nine_positions_with_floor_half_delta","content":"retained_layers_and_source_pixels","auxiliary_planes":"canvas_bound_crop_pad_or_resample","filters":"explicit_preserve_parameters_policy_required","resolution_only":true,"advanced_resamplers":true});
            capabilities["svg_import"] = svg_import_contract;
            capabilities["resource_profiles"] = json!({"field":"resource_profile","default":"standard","operation":"resource_profile","standard":{"items":model::MAX_ITEMS,"geometry_commands":model::MAX_SEGMENTS,"snapshot_bytes":model::MAX_DOCUMENT_BYTES,"svg_source_bytes":svg_import::MAX_BYTES,"svg_nodes":svg_import::MAX_NODES},"large_vector":{"items":model::MAX_LARGE_VECTOR_ITEMS,"geometry_commands":model::MAX_LARGE_VECTOR_COMMANDS,"snapshot_bytes":model::MAX_LARGE_VECTOR_BYTES,"svg_source_bytes":svg_import::MAX_LARGE_BYTES,"svg_nodes":svg_import::MAX_LARGE_NODES,"kind":"vector"},"scope":"stored_and_expanded_document_budgets;other_algorithm_and_transport_limits_remain_independent","per_path_commands":model::MAX_SEGMENTS,"checkpoint":"vector.resources.extended","checkpoint_status":"in_progress"});
            capabilities["resource_profiles"]["regional_rendering"] = json!({"profile":"large_vector","eligible":"ordinary_vector_fills_strokes_and_neutral_groups","bounds":"transformed_controls_and_generated_strokes_plus_two_evaluation_pixels","paint_coordinates":"original_item_space","work":"actual_region_scans_paints_composition_and_controls","other_scenes":"general_bounded_renderer","raises_processing_limits":false});
            capabilities["components"]["max_evaluated_items_by_profile"] =
                json!({"standard":model::MAX_ITEMS,"large_vector":model::MAX_LARGE_VECTOR_ITEMS});
            capabilities["svg_import"]["masks"] = json!({"content":["shapes","groups","gradients","geometric_clips","bound_text"],"modes":["alpha","luminance"],"units":["userSpaceOnUse","objectBoundingBox"],"sharing":"editable_source_with_import_time_coordinate_binding","legacy_region":"minus_10_percent_to_120_percent","svg2_region":"unclipped_when_all_region_attributes_absent","mode_override":"inline_mask_mode","compositing":"srgb","recursive_masks":false});
            capabilities["objects"] = json!({"commands":["object.import","object.open","object.status"],"operations":["object_replace","object_refresh","object_detach"],"parent_kind":"raster","source_kinds":["vector","raster"],"source_format":"exact_utf8_engine_snapshot","native_document_interchange":false,"link":"flat_key_explicit_root_pinned_source_hash_refresh","external_sources_unchanged":true,"implicit_link_io":false,"source_store":"inline_retained_bytes_with_sha256","max_nesting":objects::MAX_NESTING,"max_rendered_objects":objects::MAX_RENDERED_OBJECTS,"surface_scale":[1,4],"surface_precision":"f64_before_parent_reconstruction","render_budgets":"aggregate_work_and_buffer_pixels_across_evaluations","duplicate":"independent_retained_value","resources":"explicit_shared_asset_and_font_roots_pinned_within_source","missing_link":"reported_explicitly_retained_source_stays_renderable","hdr":"native_linear_parent_or_explicit_object_view","privacy":"recursive_snapshot_sanitization_detaches_links","page_delivery":"explicit_unsupported_use_image_or_snapshot"});
            capabilities["backgrounds"] = json!({"operation":"background","document_kind":"raster","actions":["promote","restore_source","to_layer"],"role":"single_bottom_printable_root","source":"retained_pixels_alpha_geometry_and_appearance","matte":"explicit_rgb8_current_canvas_after_source_controls_before_clipped_siblings","visibility":"suppresses_complete_background","implicit_lock":false,"ordinary_conversion":"isolated_layer_with_explicit_source_and_matte_ids","duplicate_and_transfer":"ordinary_retained_source_without_document_role","bounds":"source_geometry_with_separate_inspected_canvas_bounds"});
            capabilities["supported"]["raster"]
                .as_array_mut()
                .unwrap()
                .push(json!("retained_opaque_backgrounds"));
            capabilities["render_quality"] = json!({"field":"render_options","commands":["document.render","document.export","artboard.export","document.publish","session.publish"],"formats":["png","jpeg","tiff"],"antialias":["none","coverage","supersample2","supersample4"],"default_antialias":"coverage","supersample_factors":[2,4],"averaging_space":["encoded_srgb","linear_srgb"],"default_averaging":"encoded_srgb","compositing":"existing_encoded_srgb_premultiplied_f64","averaging":"completed_premultiplied_samples_before_requested_depth_projection","internal_scale_maximum":16,"padding_document_units":[0,256],"crop_to_canvas_default":true,"bounds":"symmetric_padding_then_optional_original_canvas_crop","profile_order":"average_then_rgba8_then_existing_output_conversion","effect_domain":"padded_evaluation_viewport","viewport_patterns":"noise_and_mosaic_rebase_to_evaluation_origin","limits":"all_evaluation_pixels_and_work_including_padding_and_samples","source_mutation":false,"edge_precision":"f32_coverage_then_f64_average_not_exact_area_for_arbitrary_geometry"});
            capabilities["coordinate_precision"] = json!({"storage":"IEEE754_binary64","snapshot":"exact_stored_finite_binary64_numbers","svg_literals":"roundtrip_decimal_geometry_transform_clip_and_gradient_numbers","direct_transport_absolute_error":0,"negative_coordinates":true,"fractional_coordinates":true,"geometry_control_point_absolute_limit":model::MAX_COORDINATE,"transform_component_absolute_limit":model::MAX_COORDINATE,"svg_normalization":"binary64_arithmetic_for_units_viewbox_relative_smooth_quadratic_and_transform_lists","generated_geometry":"uses_each_operation_declared_error_contract","zero_sign":"no_geometric_semantics","preview":"binary64_placement_then_output_space_binary32_quantized_coverage_not_exact_geometric_pixel_area","coverage_routes":["fills","object_and_document_strokes","image_boundaries","geometric_masks"],"ellipse_coverage":"original_32_tangent_cubic_arcs","external_svg_consumers":"their_own_precision_and_coverage_contract","scope":"within_document_and_svg_import_limits;retain_snapshot_for_source_parameters"});
            capabilities["dimensions"] = json!({"inspect":"geometry.measure","edit":"dimensions","units":["px","pt","pc","mm","cm","in"],"unit_conversion":"exact_rational_document_resolution_ppi","angle_degrees":[-360000,360000],"anchors":["min","center","max"],"bounds":"unclipped_geometry_projected_in_declared_axes;not_strokes_effects_or_glyph_ink","bounds_precision":"binary64","length":"sum_of_authored_boundaries_with_closed_contour_closing_edges","area":"signed_algebraic_contour_integral;null_for_any_open_contour;not_filled_union_area","certificate":"exact_rational_line_cubic_integrals_and_chord_polygon_or_analytic_ellipse_tangent_enclosures","length_tolerance":[0.000001,100],"area_tolerance":[0.000000001,10000],"work":dimensions::MAX_WORK,"subdivision_depth":32,"precision_failure":"NUMERIC_PRECISION","requested_logical_dimensions":[0.001,65536],"resize":"world_basis_scale_through_parent_inverse;requires_two_nonzero_source_dimensions","preserve_aspect":"exactly_one_requested_dimension","source_geometry_retained":true});
            capabilities["snapping"] = json!({"operation":"snap","targets":["point","grid","guide","item"],"target_limit":64,"reference_state":"frozen_before_operation","source_modes":["together","individual"],"rotated_bounds":true,"oblique_guides":true,"intersections_default":true,"priority":"point_grid_item_intersection_then_guide_projection;distance_then_input_order","grid_tie":"lower_index_per_axis","guide_parallel_threshold":1e-10,"units":["px","pt","pc","mm","cm","in"],"maximum_logical_distance":model::MAX_COORDINATE,"no_match":"explicit_receipt_without_item_mutation","source_geometry_retained":true});
            capabilities["swatches"] = json!({"dictionary":"document.swatches","inspect":"swatch.inspect","edit":"swatch","bake":"swatch_bake","convert":"swatch_convert_process_or_spot_retaining_components_or_explicit_replacement","definitions":["process","spot","tint"],"declaration_spaces":["srgb","gray","cmyk","lab","device"],"storage":"exact_declared_binary64;no_implicit_conversion","gray":"encoded_srgb_neutral","lab":"D50_L0..100_a_b_minus128..127","non_rgb_preview":"legacy_CMYK_Lab_require_explicit_preview;device_declarations_convert_source_profile_to_srgb","reference":{"swatch":"stable_id","tint":[0,1],"opacity":[0,1],"overprint":["knockout","preserve","preserve_nonzero"]},"precise_solid":"rgba_normalized_binary64_without_early_byte_rounding","preview_tint":"encoded_white_plus_effective_tint_times_alternate_minus_white","max_swatches":swatches::MAX_SWATCHES,"max_chain":swatches::MAX_DEPTH,"name_bytes":256,"locks":"direct_transitive_resource_and_saved_variant_dependents","deletion":"in_use_references_rejected","transfer":"independent_ID_remap_with_transitive_color_dependencies","vector_delivery":"display_srgb_gray;pdf_options.color_native_inks_preserves_spot_CMYK_Lab_and_overprint","image_delivery":"display_preview_with_explicit_losses","spot_separations":"native_PDF_Separation_resources;document_prepress_scalar_planes","overprint":"native_PDF_OP_op_OPM;display_requires_explicit_bake","separation_diagnostics":"swatch.inspect.ink_diagnostics_and_per_page_PDF_receipts;structural_not_plate_coverage","profile_driven_non_rgb_conversion":true});
            capabilities["assistance"] = json!({"inspect":"assist.layout","edit":"assist_layout","algorithm":"ordered_shelves_v1","objective":"minimum_total_row_height_then_fewest_rows_then_lexicographic_row_ends","arithmetic":"exact_rational_optimization_of_binary64_scene_bounds;binary64_placement","geometry_error_limit":assistance::PLACEMENT_ERROR,"maximum_items":assistance::MAX_ITEMS,"selection":"visible_printing_antichain;positive_bounds;unlocked_descendants_and_dependents","bounds":"unclipped_geometry;no_strokes_effects_or_alpha;text_frames","dependencies":"builtin_cpu;no_models_GPU_network_or_external_resource_loading","scope":"fixed_size_ordered_rows;explicit_area_gaps_and_alignment;unselected_artwork_ignored","unsupported":["semantic_generation","learned_models","free_reordering","automatic_resizing","painted_bounds_packing","obstacle_avoidance"]});
            capabilities["pixel_assistance"] = json!({"inspect":"assist.segment","edit":"assist_mask","algorithm":"seeded_color_cut_v1","input":"native_unfiltered_inline_RGBA8_or_u8_RGBA_gray_alpha_samples_or_verified_image_crop;encoded_srgb","objective":"minimum_integer_color_cost_plus_4_neighbor_boundary_cost;hard_class_seeds","features":"rounded_byte_premultiplied_encoded_RGB_plus_alpha","color_cost":"minimum_squared_distance_to_each_class_seed","neighbor_cost":"floor(smoothness*edge_scale/(edge_scale+squared_feature_distance))","smoothness":[0,65535],"edge_scale":[1,260100],"defaults":{"smoothness":4096,"edge_scale":4096},"ties":"smallest_foreground_set_among_minimum_cuts","certificate":"minimum_energy_equals_max_flow;optional_full_integer_costs","maximum_pixels":assistance::segment::MAX_PIXELS,"maximum_seeds_per_class":assistance::segment::MAX_SEEDS,"maximum_work":assistance::segment::MAX_WORK,"mask":"binary_native_grid;linked_display_scale;original_pixels_preserved;explicit_existing_mask_replacement","dependencies":"builtin_cpu;no_models_GPU_network;explicit_image_store_when_needed","unsupported":["semantic_recognition","alpha_matting","learned_models","remote_services","high_depth_or_HDR_input","retained_pixel_warps"]});
            capabilities["pixel_assistance"]["workflows"] = json!({"remove":{"op":"repair","action":"fill","region":"explicit_native_mask","source":"frozen_local_donors","quality":"context_and_boundary_RMS_limits"},"denoise":{"op":"repair","action":"edge_correct","guide":"explicit_self_or_local_guide","estimator":"guided_weighted_median","quality":"change_RMS_and_effective_support_limits"},"upscale":{"op":"canvas","action":"scale","sampling":"explicit_reconstruction_kernel","source":"retained_native_samples","border":"existing_clamped_sampling"},"models":[],"remote_fallback":false});
            capabilities["volumes"] = json!({
                "content":"volume","inspect":"volume.inspect","edits":["volume","volume_expand"],
                "profile":"retained_closed_geometry;simple_nonintersecting_polygonal_contours;concavity_holes_disjoint_regions",
                "fill_rules":["nonzero","even_odd"],"source_curves":"existing_certified_identity_map_chords",
                "source_tolerance":[0.000001,1],"default_source_tolerance":0.1,
                "extrusion":"front_z_zero_to_back_z_negative_depth","depth":[0,4096],
                "rotation":"degrees_about_pivot_in_X_then_Y_then_Z_order","placement":"rotation_then_pivot_plus_translation;outer_item_transform_after_projection",
                "cameras":["orthographic_positive_Z","perspective_explicit_principal_distance_near_far"],
                "perspective_distance":[1,32768],"maximum_perspective_magnification":128,
                "camera_clipping":"whole_request_rejected_when_vertices_cross_depth_range",
                "materials":["unlit_srgb8","flat_diffuse_linear_srgb_with_explicit_ambient_and_directional_lights"],
                "lights":8,"light_intensity":[0,8],"light_space":"post_rotation_3D;direction_toward_light",
                "opacity":"opaque_surface;outer_item_opacity_after_solid_compositing",
                "maximum_profile_edges":volumes::MAX_EDGES,"maximum_projected_faces":volumes::MAX_FACES,
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
                "order":"bottom_to_top","pass_controls":["fill","stroke","enabled","opacity","blend","maps","tolerance","filters","effects"],
                "pipeline":"ordered_geometry_maps_then_fill_and_stroke_then_ordered_raster_filters_then_existing_decoration_policy",
                "outer_controls":"apply_to_isolated_stack","maps":["affine","perspective","envelope"],
                "expansion":"independent_editable_vector_objects;maps_materialized;raster_filters_and_decorations_retained",
                "bake":{"space":"encoded_srgb","viewport":"explicit_document_space_origin_width_height","scale":[1,4],"pixels":model::MAX_STORED_PIXELS,"output":"embedded_immutable_RGBA8_image","placement":"inverse_world_transform","outer_controls":"retained","boundaries":"filters_reevaluated_for_declared_viewport","losses":"outside_region_cropped;paints_maps_filters_and_pass_order_frozen"},
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
                "raster_scale":[1,2,3,4],
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
                "pdf_delivery":{"option":"pdf_options.prepress","channels":"NChannel_CMYK_and_named8","profile":"exact_supplied_ICC","image_bytes":"same_as_document.prepress","spot_fallback":"explicit_multiplicative_declared","marks":["crop","registration"],"mark_units":"physical_points","mark_colorant":"All","mark_location":"outside_bleed","publication":"document.publish_or_session.publish;create_only","max_aggregate_pixels":4_194_304,"max_aggregate_work":prepress::MAX_WORK,"editable_reimport":false,"press_certification":false},
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
            capabilities["profile_gamut"] = json!({"command":"profile.gamut","read_only":true,"profile":"ICC_v2_v4_CMYK_output_XYZ_or_Lab_with_gamt_tag","tables":["lut8_Lab","lut16_Lab_XYZ","lutBToA_Lab_XYZ"],"inputs":"D50_XYZ;finite;4096_samples","intents":["relative_colorimetric","absolute_colorimetric"],"classification":"zero_in_gamut_nonzero_out;outside_PCS_encoding_unclassified","interpolation":"original_f64_tetrahedral;exact_fixed_curve_parameters;consumer_integer_paths_may_differ_at_boundaries","source_mutation":false,"print_jobs":false,"missing_table":"GAMUT_UNAVAILABLE;no_roundtrip_substitution","unsupported":["perceptual_reference_medium_mapping","eight_bit_XYZ_tables","spectral_ink_gamut"]});
            capabilities["paragraph_flow"] = json!({"resource":"document.stories","content":"story_frame","edit":["story","story_range"],"inspect":"story.inspect","slots":"ordered_source_flow_independent_of_item_placement","columns":"equal_width_explicit_gutter_and_reverse_order","paragraphs":"separate_original_rich_text_records","spacing":"additive_before_after;leading_and_logical_start_end_first_line_indents","metrics":"max_ascent_plus_max_descent_plus_max_nonnegative_gap","line_fitting":"longest_reshaped_grapheme_prefix_with_ascii_space_preference","indices":"paragraph_local_unicode_scalars","source_coverage":"line_start_end_and_consumed_end_including_skipped_break_spaces","bidi":"complete_paragraph_resolution_across_slots;line_local_shaping","overset":["error","retain"],"overset_inspection":"first_unplaced_paragraph_and_scalar_offset","clipping":"always_slot_rectangle;glyph_overhang_flagged","shared_source_edits":true,"transfer":"complete_story_slots_with_independent_story_and_font_ids","snapshot_history":true,"stories":text::flow::MAX_STORIES,"paragraphs_per_story":text::flow::MAX_PARAGRAPHS,"slots_per_story":text::flow::MAX_SLOTS,"columns_per_slot":text::flow::MAX_COLUMNS,"aggregate_characters":text::MAX_TEXT_CHARS,"visible_hyphenation":{"rules":"story_local_named_weighted_patterns_and_exceptions","rule_sets_per_story":text::flow::hyphens::MAX_RULE_SETS,"tokens":"unicode_lexical_words;original_scalars","fit":"furthest_fitting_space_or_rule_break;hyphen_shaped_with_fragment","marks":["hyphen_minus","hyphen"],"style":"preceding_source_character","emergency_break":"explicit_unmarked_grapheme_fallback;default_false","provenance":"generated_hyphen_cluster_and_original_source_interval","display_bidi":"full_virtual_paragraph_with_one_inserted_scalar;line_local_shaping","rules_budget":"aggregate_document_pattern_and_exception_limits","source_unchanged":true},"structural_lists":{"formats":["bullet","decimal","lower_alpha","upper_alpha","lower_roman","upper_roman"],"levels":text::flow::lists::MAX_LEVELS,"ids_per_story":text::flow::lists::MAX_LISTS,"max_counter":text::flow::lists::MAX_COUNTER,"roman_max":3999,"affix_characters":text::flow::lists::MAX_AFFIX,"counter_scope":"story_local_list_id;ordinary_paragraphs_and_other_lists_do_not_reset","restarts":true,"nested_counters":true,"placement":"first_line_logical_start_hanging_marker;gap_and_indent_explicit","body_source":"unchanged;marker_glyphs_have_generated_provenance","styles":"explicit_or_paragraph_base;pinned_font_resources","character_budget":"body_plus_generated_labels"},"named_paints":true});
            capabilities["hyphenation"] = json!({"command":"text.hyphenate","patterns":"explicit_text_and_scalar_gap_weights_0_to_9","matching":"maximum_over_all_matching_patterns_then_odd_priorities","anchors":["at_start","at_end"],"case":["exact","ascii_lower"],"normalization":"none","exceptions":"replace_pattern_candidates_with_explicit_internal_grapheme_boundaries","indices":"unicode_scalars","minima_units":"extended_graphemes","minima_range":[1,128],"source_preserved":true,"layout_integration":false,"language_dictionaries_bundled":false,"pattern_count":hyphenation::MAX_PATTERNS,"pattern_scalars":hyphenation::MAX_PATTERN_CHARS,"total_pattern_scalars":hyphenation::MAX_TOTAL_PATTERN_CHARS,"exceptions":hyphenation::MAX_EXCEPTIONS,"total_exception_scalars":hyphenation::MAX_EXCEPTION_CHARS,"word_scalars":hyphenation::MAX_WORD_CHARS,"words":hyphenation::MAX_WORDS,"total_word_scalars":hyphenation::MAX_TOTAL_WORD_CHARS,"work":hyphenation::MAX_WORK,"unsupported":["implicit_language_selection","soft_hyphen_input","spelling_replacements","dictionary_file_formats","line_break_placement"]});
            capabilities["hdr"] = json!({"working_space":"linear_srgb","source":"linear_srgb binary32 RGBA or gray-alpha, signed finite color and normalized alpha","encoded_sources":"decoded before linear interpolation and compositing","measure":"sample.measure","grade_operation":"hdr_grade","working_space_operation":"working_space","native_delivery":"f32 TIFF without view","display_view_required":true,"views":["clip","reinhard"],"view_space":"component-wise linear radiance, then encoded sRGB","exposure_stops":[-32,32],"channel_gain":[0,16],"blend_modes":["normal","multiply","linear_dodge","darken","lighten","difference","subtract"],"unsupported":["normalized adjustments and active filters/effects","knockout","pass-through group grading","HDR output profiles","HDR page/vector delivery","automatic HDR detection","cross-working-space transfer"],"tone_mapping_preserves_source":true});
            capabilities["raw_development"] = json!({
                "command":"raw.develop","algorithm":raw::ALGORITHM,
                "input":"explicit_headerless_Bayer_sensor_buffer","packing":["u8","u16_le","u16_be"],
                "patterns":["rggb","grbg","gbrg","bggr"],"row_padding":true,"max_row_padding_bytes":4096,
                "max_sensor_pixels":raw::MAX_PIXELS,"source_bytes":"exact_row_stride_times_height_max_32_MiB",
                "calibration":"explicit_per_site_black_white_and_row_major_camera_to_linear_srgb_matrix",
                "white_balance":["explicit_gains","measured_neutral_green_normalized"],"exposure_stops":[-32,32],
                "interpolation":"bilinear_missing_channels_available_neighbors_renormalized_at_edges",
                "outputs":["srgb8","srgb16","linear_srgb32"],"range":["explicit_clip","preserve_signed_scene_range_for_float"],
                "resolution_ppi":[1,9600],"source_unchanged":true,"source_pin":"optional_expected_sha256",
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
                "lens_borders":["clamp","transparent"],"lens_no_fold":"global_normalized_Jacobian_perturbation_bound_less_than_0.95",
                "denoise":"RGB_range_gated_uniform_local_mean_with_amount","detail":"alpha_weighted_box_unsharp_with_threshold",
                "neighborhood_radius":[1,4],"sidecar":"strict_version2_JSON_source_pinned_sensor_development_only",
                "history":"source_preserving_atomic_settings_edits_snapshots_sessions_undo_redo",
                "expansion":"explicit_raw_expand_to_native_samples","scene_resolution":"independent_from_recipe_output_preference"
            });
            capabilities["sample_precision"] = json!({"content":"samples","depths":["u8","u16","f32"],"channels":["rgba","gray_alpha"],"storage":"little_endian_straight_channel_bytes_as_hex","float_range":[0.0,1.0],"working":"normalized_f64_encoded_srgb","native_edit":"sample_replace","sampling":["nearest","bilinear","area","bicubic","lanczos3"],"tiff":{"options":["depth","channels"],"depths":["u8","u16","f32"],"channels":["rgba","gray_alpha"],"alpha":"unassociated","gray_policy":"exact_neutral_rgb_required","output_profiles":false},"display_preview":"rgba8_quantized_copy","hdr":true,"native_brush_and_mask_bake":false,"high_depth_import":true,"import":{"command":"sample.import","formats":["png","tiff"],"png_depths":["u8","u16"],"tiff_depths":["u8","u16","f32"],"source_unchanged":true,"profiles":false,"orientation_transforms":false,"associated_alpha":false,"multiple_images":false,"max_inline_pixels":65536,"max_source_bytes":33554432,"max_tiff_padded_tile_bytes":67108864},"conversion":{"operation":"sample_convert","depths":["u8","u16","f32"],"channels":["rgba","gray_alpha"],"gray_policies":["require_neutral","encoded_luma","linear_luminance"],"legacy_inline_rgba8_promotion":true,"hidden_color":"converted_without_alpha_zero_discard","profiles":false,"hdr":true},"encodings":["encoded_srgb","linear_srgb","profiled_rgb"],"linear_float_color_range":"finite_signed_binary32","linear_alpha_range":[0.0,1.0],"source_preserved":true,"geometry_coverage":"existing_f32_and_byte_coverage"});
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
                .push(json!("tiff_explicit_depth_gray_or_rgba"));
            capabilities["features"]["bmp_import"] = json!(true);
            capabilities["features"]["tga_import"] = json!(true);
            capabilities["features"]["gif_import"] = json!(true);
            capabilities["image_io"]["formats"] =
                json!(["png", "jpeg", "tiff", "bmp", "tga", "gif"]);
            capabilities["image_io"]["tiff"]["alpha"] = json!(["unassociated", "associated_rgba8"]);
            capabilities["image_io"]["tiff"]["associated_alpha_lossless"] = json!(false);
            capabilities["image_io"]["bmp"] = json!({"import":"infoheader40_rgb24_rgb32_unused_padding","export":"rgb24_bottom_up","rows":"aligned4_top_or_bottom_input","alpha":"explicit_matte_for_transparent_output","profiles":"declared_input_only","metadata":"explicit_strip_required","density":"integer_pixels_per_meter"});
            capabilities["image_io"]["tga"] = json!({"import":"raw_rle_rgb24_rgba32_gray8_grayalpha16","origins":"all_four_to_top_left","alpha":"descriptor_and_extension_0_1_2_3_4","export":"rgba32_top_left_extension_useful_alpha","profiles":"declared_input_only","metadata":"explicit_strip_required","density":false});
            capabilities["image_io"]["gif"] = json!({"import":"still_or_sequence","compression":"variable_width_lzw_2_to_8_initial_12_max_deferred_clear","export":"exact_sorted_local_palettes_literal_lzw_resets","palette_entries":256,"alpha":"binary_one_reserved_entry_in_all_frames_if_any_transparency","quantization":false,"timing":"exact_centiseconds_0_to_65535","plays":[0,65536],"background":["transparent","logical_screen"],"default_background":"transparent","disposal":["keep","background","previous"],"interlaced_input":true,"metadata":"selected_envelope_comment","profiles":"declared_still_input_only_no_embedded_profile","density":false,"animation_import":"sequence.import","still_import":"reject_multiple_frames"});
            capabilities["publication"]["formats"] = json!([
                "pdf", "png", "apng", "jpeg", "tiff", "bmp", "tga", "gif", "svg", "snapshot"
            ]);
            capabilities["supported"]["artboards"]["formats"] =
                json!(["png", "jpeg", "tiff", "bmp", "tga", "svg_vector"]);
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
            capabilities["device_color_conversion"] = json!({"command":"color.convert","spaces":["rgb","gray","cmyk","lab"],"max_samples":4096,"intents":["relative_colorimetric","absolute_colorimetric","perceptual","saturation"],"untagged":["reject","assume_srgb_for_rgb"],"lookup_inputs":[1,3,4],"lookup_interpolation":"continuous_tensor","intent_contract":"declared_directional_tables;matrix_gray_curve_fallback;absolute_media_white_scaling;v4_reference_medium_bridge;v2_direct_PCS;no_optional_BPC","profile_bytes_retained":true,"gamut":["off","if_available","required"],"gamut_coordinates":"independent_colourimetric_source_to_destination_relative_PCS","document_policy_integration":"explicit_per_paint_intent_and_source_profile;RGB_output_profile_or_explicit_print_target"});
            capabilities["managed_swatches"] = json!({"declaration":"device","edit":"swatch_profile","actions":["assign","convert"],"source_spaces":["rgb","gray","cmyk","lab"],"intent":"retained_per_definition","preview":"profiled_source_to_encoded_srgb","tint":"source_device_components_before_conversion","assignment":"retain_numbers_change_interpretation","conversion":"change_numbers_through_explicit_profile_connection","native_pdf":"exact_deduplicated_ICCBased_profiles_and_explicit_RI;D50_Lab;PDF_2_0_explicit_BPC_OFF","calibrated_pdf":"document_output_profile_in_page_and_isolated_group_blending;explicit_DefaultRGB_srgb;untagged_CMYK_rejected","native_prepress":"explicit_source_profile_to_selected_print_profile;print_intent_governs","overprint":"profiled_process_PDF_overprint_rejected;spot_overprint_retained","display_vector":"explicit_swatch_bake_required","source_retention":"snapshot_receipts_and_durable_history","document_policy":"explicit_source_encodings;per_definition_relative_default;output_profile_for_calibrated_RGB_delivery;export_intent_for_print_separation","gamut_integration":true});
            capabilities["swatches"]["declaration_spaces"] =
                json!(["srgb", "gray", "cmyk", "lab", "device"]);
            capabilities["swatches"]["profile_driven_non_rgb_conversion"] =
                json!("explicit_device_declarations");
            capabilities["vector_canvas"] = json!({"operation":"vector_canvas","actions":["set","unit","clear"],"units":["px","pt","pc","mm","cm","in"],"canonical_coordinates":"logical_pixels_binary64","unit_conversion":"exact_rational_then_one_binary64_round","origin":"finite_nonzero_supported","size_range_px":[0.000001,32768],"preview_storage":"ceiling_of_logical_size","fractional_edge":"area_coverage_except_none_point_sampling","artboards":"optional_logical_size_with_ceiling_cache","process_spaces":["rgb","cmyk"],"colour_semantics":"typed_paints_unchanged;CMYK_pages_require_native_or_profile_managed_inks","unit_changes_preserve_artwork":true,"svg":"physical_units_and_logical_viewBox","pdf":"physical_fractional_page_and_translated_evaluation_copy","source_unchanged":true});
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
                .extend([json!("layered"), json!("layered_large")]);
            capabilities["layered_interchange"] = json!({"status":"basic_interchange_verified","import":"layered.import","export_format":"layered","file_version":1,"additional_file_versions":[2],"large_export_format":"layered_large","dimensions_by_version":{"standard":30000,"large":32768},"extended_status":"partial_uncredited","mode":"rgb8","layer_order":"bottom_to_top","layer_sources":["inline_raster","encoded_srgb_rgba8_samples"],"import_compression":["raw","rle","zip","zip_prediction"],"export_compression":"rle;raw_available_in_Rust_library","preserved":["original_layer_pixels_including_hidden_RGB","integer_extents","names","visibility","byte_opacity","byte_fill_opacity","whole_layer_lock"],"source_changed":false,"canvas_pixels":layered::MAX_CANVAS_PIXELS,"stored_pixels":model::MAX_STORED_PIXELS,"file_bytes":layered::MAX_FILE_BYTES,"maximum_layers":model::MAX_ITEMS,"profile_policy":"exact_builtin_srgb;explicit_convert_srgb_for_other_profiles;explicit_assume_srgb_for_untagged","merged_preview":"white_matted_RGB_with_separate_alpha;8bit_unmatting_loss;layers_remain_original","metadata":"explicit_strip_if_descriptive_metadata_present","incoming_metadata":"strict_known_inactive_records_with_omission_receipts","descriptor_limits":{"bytes":65536,"depth":8,"values":512,"container_entries":128},"density_units":"fixed_values_always_ppi;unit_selectors_are_display_only","groups":{"modes":["normal_isolated","normal_pass_through"],"empty":true,"ancestor_levels":16,"serialized_records":512,"transforms":"absolute_integer_source_placements;imported_groups_identity","open_state":"omitted_UI_metadata","unsupported":["non_normal_group_blends","group_fill_opacity","knockout","cached_group_pixel_extents","layer_role_containers"]},"masks":{"authored_gray8":true,"independent_bounds":true,"constant_empty_planes":true,"controls":["linked","enabled","outside_black_or_white","exact_byte_density"],"sampling":"nearest_integer_translation","unsupported":["nonzero_native_feather","obsolete_invert_flag","derived_masks","combined_real_vector_masks","implicit_resampling"]},"empty_layer_names":"encoded_exactly;native_consumers_may_generate_names;receipt_lists_empty_name_source_ids","unsupported":["large_axes_above_32768","empty_pixel_layers","native_mask_feather","derived_or_combined_masks","text","embedded_objects","non_normal_blends","extra_channels","nonempty_guides","unknown_appearance_records"],"checkpoint":"raster.interchange.basic"});
            capabilities["agent_discovery"] = json!({
                "lookup":"schema.lookup", "index":"index",
                "large_schema_outline_bytes":schema::OUTLINE_BYTES,
                "full_schema":"schema", "mcp_default":"full",
                "mcp_compact_arguments":["mcp","--tools","core"],
                "mcp_compact_budget_bytes":mcp::CORE_CATALOG_BYTES,
                "mcp_dispatcher":"inkbolt_run", "execution_validation":"complete_typed_request"
            });
            capabilities["paged_inspection"] = json!({"command":"document.inspect.page","collections":["items","assets","fonts","anchors"],"maximum_records":inspection::MAX_PAGE_ITEMS,"maximum_result_bytes":inspection::MAX_PAGE_BYTES,"cursor":"document_content_and_view_and_limit_bound","order":"document_storage_for_items;id_for_resources;component_then_command_for_anchors","field_selection":true,"legacy_inspection":"unchanged","external_resources_verified":false});
            capabilities["mcp_preview"] = json!({"response_format":"preview","default":"json","image_bytes":"one_location_with_explicit_payload_ref","maximum_png_attachments":mcp_preview::MAX_IMAGES,"maximum_attached_base64_bytes":mcp_preview::MAX_IMAGE_BASE64_BYTES,"overflow":"one_inline_payload_in_structuredContent;duplicates_reference_it","text":"summary_only","supported_artifacts":["document.export","artboard.export","sequence.export","channel.export","document.proof","document.prepress","document.separations"],"other_results":"complete_structuredContent_without_textual_duplication"});
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
            Ok(capabilities)
        }
        Request::Schema {} => Ok(schema::full().clone()),
        Request::SchemaLookup { name, select, full } => {
            schema::lookup_in_workspace(&name, select.as_deref(), full, context.has_workspace())
        }
        Request::ImplementationStatus {} => Ok(implementation_status()),
        Request::Publish {
            document,
            resources,
            output,
            control,
        } => publish::publish(&document, &resources, &output, &context.scoped(&control)?),
        Request::SessionPublish {
            session_root,
            session_id,
            expected_revision,
            output,
            control,
        } => sessions::publish(
            &session_root,
            &session_id,
            expected_revision,
            &output,
            &context.scoped(&control)?,
        ),
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
        } => boards::export(
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
        Request::Inspect { document } => {
            model::validate_controlled(&document, context)?;
            let items: Vec<Value> = (0..document.items.len())
                .map(|i| inspect_item(&document, i))
                .collect::<Result<_, _>>()?;
            let assets:Vec<_>=document.assets.iter().map(|(id,a)|json!({"id":id,"width":a.width,"height":a.height,"sha256":a.sha256,"storage":match a.storage{assets::Storage::Stored=>"stored",assets::Storage::Embedded{..}=>"embedded"},"provenance":a.provenance,"used_by":document.items.iter().filter_map(|item|match &item.content{model::Content::Image{asset_id,..} if asset_id==id=>Some(&item.id),_=>None}).collect::<Vec<_>>()})).collect();
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
        Request::Query { document, query } => query::execute(&document, &query),
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
            validate(&document)?;
            let indices = scene::selection(&document, &ids, false)?;
            let items: Vec<_> = indices
                .into_iter()
                .map(|i| inspect_item(&document, i))
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
        } => Ok(json!(edit::apply_with_resources(
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

pub(crate) fn inspect_item(document: &Document, i: usize) -> Result<Value, Error> {
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
    let mut result = json!({"object":match &item.content{model::Content::Object{object}=>Some(object.summary()),_=>None},"hdr_grade":item.hdr_grade,"samples":samples::inspect(&item.content),"pixel_warp":item.pixel_warp,"metadata":item.metadata,"id":item.id,"name":item.name,"content_type":query::item_type(item),"warp":match &item.content{model::Content::Warp{warp}=>Some(warp),_=>None},"repeat":match &item.content{model::Content::Repeat{repeat}=>Some(repeat),_=>None},"interpolation":match &item.content{model::Content::Interpolation{interpolation}=>Some(interpolation),_=>None},"instance":match &item.content{model::Content::Instance{instance}=>Some(instance),_=>None},"artwork_mask_source_sha256":artwork_masks::dependency_hash(document,i)?,"component_source_sha256":instances::dependency_hash(document,i)?,"group":match &item.content{model::Content::Group{isolated,knockout,role}=>Some(json!({"isolated":isolated,"knockout":knockout,"role":role})),_=>None},"geometry":match &item.content{model::Content::Vector{geometry,..}|model::Content::WorkPath{geometry,..}=>Some(geometry),_=>None},"stroke":match &item.content{model::Content::Vector{stroke,..}=>stroke.as_ref(),_=>None},"index":i,"sibling_index":sibling_index,"parent":item.parent,"clip_to":item.clip_to,"visible":item.visible,"effective_visible":scene::effective_visible(document,i)?,"locked":item.locked,"effective_locked":scene::effective_locked(document,i)?,"opacity":item.opacity,"fill_opacity":item.fill_opacity,"coverage":item.coverage,"effects":item.effects,"blend":item.blend,"world_transform":scene::world_transform(document,i)?,"geometry_bounds":scene::bounds(document,i)?,"clip":item.clip,"mask":item.mask,"artwork_mask":item.artwork_mask,"artwork_mask_world_transform":item.artwork_mask.as_ref().map(|m|scene::world_transform(document,i).map(|w|m.world_transform(w))).transpose()?,"filters":item.filters,"mask_world_transform":item.mask.as_ref().map(|m| scene::world_transform(document,i).map(|w| m.world_transform(w))).transpose()?,"image":image,"adjustment":match &item.content{model::Content::Adjustment{adjustment}=>Some(adjustment),_=>None},"frame":match &item.content{model::Content::Frame{frame}=>Some(frame),_=>None}});
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
