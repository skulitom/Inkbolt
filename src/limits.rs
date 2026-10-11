//! Shared resource ceilings and bounded-evaluation settings.
//! Existing module paths re-export these constants for API compatibility.
//! Equal numbers are not automatically shared policies: independently
//! constrained memory, work, format and document domains remain distinct.
//! This consolidation does not increase any acceptance or processing limit.

macro_rules! define_limits {
    ($( $(#[$group_doc:meta])* pub mod $group:ident {
        $( $(#[$doc:meta])* pub const $name:ident: $kind:ty = $value:expr; )*
    } )*) => {
        $( $(#[$group_doc])* pub mod $group {
            $( $(#[$doc])* pub const $name: $kind = $value; )*
        } )*

        #[cfg(test)]
        fn compiled_values() -> Vec<(&'static str, serde_json::Value)> {
            vec![$($( (concat!(stringify!($group), ".", stringify!($name)),
                serde_json::json!($group::$name)), )*)*]
        }
    };
}

define_limits! {
/// Limits for `src/adjustments.rs`.
pub mod adjustments {
    /// Max operators (adjustments).
    pub const MAX_OPERATORS: usize = 16;
    /// Max document operators (adjustments).
    pub const MAX_DOCUMENT_OPERATORS: usize = 256;
    /// Max curve points (adjustments).
    pub const MAX_CURVE_POINTS: usize = 64;
}

/// Limits for `src/appearance.rs`.
pub mod appearance {
    /// Max passes (appearance).
    pub const MAX_PASSES: usize = 16;
}

/// Limits for `src/artwork_masks.rs`.
pub mod artwork_masks {
    /// Max masks (artwork masks).
    pub const MAX_MASKS: usize = 32;
    /// Max coverage pixels (artwork masks).
    pub const MAX_COVERAGE_PIXELS: u64 = 1_048_576;
    /// Max svg items (artwork masks).
    pub const MAX_SVG_ITEMS: usize = 4096;
}

/// Limits for `src/assets.rs`.
pub mod assets {
    /// Maximum temporary-file reservation attempts for an immutable image asset.
    pub const MAX_STAGE_ATTEMPTS: usize = 64;
    /// Max assets (assets).
    pub const MAX_ASSETS: usize = 64;
    /// Max asset pixels (assets).
    pub const MAX_ASSET_PIXELS: u64 = super::raster::MAX_PIXELS;
    /// Max import bytes (assets).
    pub const MAX_IMPORT_BYTES: u64 = 32 * 1024 * 1024;
}

/// Limits for `src/assistance/segment.rs`.
pub mod assistance_segment {
    /// Max pixels (assistance segment).
    pub const MAX_PIXELS: usize = 65_536;
    /// Max seeds (assistance segment).
    pub const MAX_SEEDS: usize = 32;
    /// Max work (assistance segment).
    pub const MAX_WORK: u64 = 67_108_864;
}

/// Limits for `src/assistance.rs`.
pub mod assistance {
    /// Max items (assistance).
    pub const MAX_ITEMS: usize = 64;
}

/// Limits for `src/boards.rs`.
pub mod boards {
    /// Max artboards (boards).
    pub const MAX_ARTBOARDS: usize = 32;
    /// Max guides (boards).
    pub const MAX_GUIDES: usize = 512;
    /// Max frame guides (boards).
    pub const MAX_FRAME_GUIDES: usize = 64;
    /// Max bleed (boards).
    pub const MAX_BLEED: u32 = 4096;
    /// Max batch pixels (boards).
    pub const MAX_BATCH_PIXELS: u64 = 4_194_304;
    /// Max batch bytes (boards).
    pub const MAX_BATCH_BYTES: usize = 32 * 1024 * 1024;
    /// Max batch work (boards).
    pub const MAX_BATCH_WORK: u64 = 134_217_728;
}

/// Limits for `src/booleans/topology/algebraic/roots.rs`.
pub mod booleans_topology_algebraic_roots {
    /// Max root depth (booleans topology algebraic roots).
    pub const MAX_ROOT_DEPTH: usize = 96;
    /// Max coefficient bits (booleans topology algebraic roots).
    pub const MAX_COEFFICIENT_BITS: u64 = 4096;
}

/// Limits for `src/booleans.rs`.
pub mod booleans {
    /// Max inputs (booleans).
    pub const MAX_INPUTS: usize = 16;
    /// Max edges (booleans).
    pub const MAX_EDGES: usize = 512;
    /// Max atoms (booleans).
    pub const MAX_ATOMS: usize = 4096;
    /// Max work (booleans).
    pub const MAX_WORK: usize = 2_000_000;
}

/// Limits for `src/channels.rs`.
pub mod channels {
    /// Max channels (channels).
    pub const MAX_CHANNELS: usize = 16;
    /// Max samples (channels).
    pub const MAX_SAMPLES: usize = 262_144;
}

/// Limits for `src/checks.rs`.
pub mod checks {
    /// Default number of document issues requested by an agent.
    pub const DEFAULT_ISSUES: usize = 64;
    /// Reserve for report metadata outside the collected issue records.
    pub const REPORT_ENVELOPE_BYTES: usize = 8192;
    /// Max issues (checks).
    pub const MAX_ISSUES: usize = 256;
    /// Max report bytes (checks).
    pub const MAX_REPORT_BYTES: usize = 128 * 1024;
}

/// Limits for `src/color_adjustments.rs`.
pub mod color_adjustments {
    /// Max lut 1d (color adjustments).
    pub const MAX_LUT_1D: usize = 4096;
    /// Max lut 3d side (color adjustments).
    pub const MAX_LUT_3D_SIDE: u32 = 33;
    /// Max document lut entries (color adjustments).
    pub const MAX_DOCUMENT_LUT_ENTRIES: usize = 65536;
    /// Max map stops (color adjustments).
    pub const MAX_MAP_STOPS: usize = 64;
}

/// Limits for `src/contact_sheets.rs`.
pub mod contact_sheets {
    /// Maximum thumbnail columns in a contact sheet.
    pub const MAX_COLUMNS: u32 = 8;
    /// Maximum pixels along a single thumbnail axis.
    pub const MAX_CELL_AXIS: u32 = 512;
    /// Maximum pixel gap between thumbnails.
    pub const MAX_GAP: u32 = 64;
    /// Max views (contact sheets).
    pub const MAX_VIEWS: usize = 16;
    /// Max pixels (contact sheets).
    pub const MAX_PIXELS: u64 = 4_194_304;
}

/// Limits for `src/control.rs`.
pub mod control {
    /// Maximum distinct cancellation markers inherited by a scoped request.
    pub const MAX_CANCEL_FILES: usize = 4;
    /// Max timeout ms (control).
    pub const MAX_TIMEOUT_MS: u64 = 60_000;
}

/// Limits for `src/dimensions.rs`.
pub mod dimensions {
    /// Maximum certified length subdivision depth for cubic curves and ellipses.
    pub const MAX_SUBDIVISION_DEPTH: usize = 32;
    /// Max work (dimensions).
    pub const MAX_WORK: usize = 65_536;
}

/// Limits for `src/edit.rs`.
pub mod edit {
    /// Max operations (edit).
    pub const MAX_OPERATIONS: usize = 64;
}

/// Limits for `src/effects.rs`.
pub mod effects {
    /// Maximum explicitly stored contour knots per retained layer effect.
    pub const MAX_CONTOUR_KNOTS: usize = 64;
    /// Max stack (effects).
    pub const MAX_STACK: usize = 8;
    /// Max document effects (effects).
    pub const MAX_DOCUMENT_EFFECTS: usize = 64;
    /// Max work (effects).
    pub const MAX_WORK: u64 = 67_108_864;
}

/// Limits for `src/filters.rs`.
pub mod filters {
    /// Max stack (filters).
    pub const MAX_STACK: usize = 8;
    /// Max document filters (filters).
    pub const MAX_DOCUMENT_FILTERS: usize = 64;
    /// Max work (filters).
    pub const MAX_WORK: u64 = 67_108_864;
}

/// Limits for `src/fonts.rs`.
pub mod fonts {
    /// Maximum temporary-file reservation attempts for a font or license blob.
    pub const MAX_STAGE_ATTEMPTS: usize = 64;
    /// Maximum face index admitted in a pinned font collection.
    pub const MAX_FACE_INDEX: u32 = 255;
    /// Max font bytes (fonts).
    pub const MAX_FONT_BYTES: u64 = 8 * 1024 * 1024;
    /// Max fonts (fonts).
    pub const MAX_FONTS: usize = 8;
    /// Max license bytes (fonts).
    pub const MAX_LICENSE_BYTES: u64 = 65536;
    /// Max axes (fonts).
    pub const MAX_AXES: usize = 16;
    /// Max features (fonts).
    pub const MAX_FEATURES: usize = 64;
}

/// Limits for `src/geometry/affine.rs`.
pub mod geometry_affine {
    /// Min determinant (geometry affine).
    pub const MIN_DETERMINANT: f64 = 1e-8;
    /// Max fast point error (geometry affine).
    pub const MAX_FAST_POINT_ERROR: f64 = 1e-9;
    /// Max relative factors (geometry affine).
    pub const MAX_RELATIVE_FACTORS: usize = 8;
    /// Max transform factors (geometry affine).
    pub const MAX_TRANSFORM_FACTORS: usize = MAX_RELATIVE_FACTORS + 1;
}

/// Limits for `src/geometry/point.rs`.
pub mod geometry_point {
    /// Max roundoff (geometry point).
    pub const MAX_ROUNDOFF: f64 = 1e-9;
}

/// Limits for `src/handoff.rs`.
pub mod handoff {
    /// Maximum output canvas dimension in a graphics handoff.
    pub const MAX_AXIS: u32 = 4096;
    /// Maximum handoff duration in seconds, separate from its frame-count budget.
    pub const MAX_SECONDS: u32 = 120;
    /// Max pixels (handoff).
    pub const MAX_PIXELS: u64 = 8_000_000;
    /// Max bytes (handoff).
    pub const MAX_BYTES: usize = super::publish::MAX_OUTPUT_BYTES;
}

/// Limits for scene-linear sample inspection.
pub mod hdr {
    /// Maximum requested in-canvas positions per sample measurement.
    pub const MAX_SAMPLES: usize = 256;
}

/// Limits for `src/hyphenation.rs`.
pub mod hyphenation {
    /// Max patterns (hyphenation).
    pub const MAX_PATTERNS: usize = 32_768;
    /// Max pattern chars (hyphenation).
    pub const MAX_PATTERN_CHARS: usize = 64;
    /// Max total pattern chars (hyphenation).
    pub const MAX_TOTAL_PATTERN_CHARS: usize = 262_144;
    /// Max exceptions (hyphenation).
    pub const MAX_EXCEPTIONS: usize = 4_096;
    /// Max exception chars (hyphenation).
    pub const MAX_EXCEPTION_CHARS: usize = 65_536;
    /// Max word chars (hyphenation).
    pub const MAX_WORD_CHARS: usize = 256;
    /// Max words (hyphenation).
    pub const MAX_WORDS: usize = 256;
    /// Max total word chars (hyphenation).
    pub const MAX_TOTAL_WORD_CHARS: usize = 4_096;
    /// Max work (hyphenation).
    pub const MAX_WORK: usize = 4_194_304;
}

/// Limits for `src/ink_recipes.rs`.
pub mod ink_recipes {
    /// Maximum UTF-8 bytes in a named recipe ink.
    pub const MAX_NAME_BYTES: usize = 256;
    /// Max inks (ink recipes).
    pub const MAX_INKS: usize = 8;
    /// Max knots (ink recipes).
    pub const MAX_KNOTS: usize = 64;
    /// Max work (ink recipes).
    pub const MAX_WORK: u64 = 67_108_864;
}

/// Limits for `src/inspection.rs`.
pub mod inspection {
    /// Default number of records requested in a compact inspection page.
    pub const DEFAULT_PAGE_ITEMS: usize = 32;
    /// Maximum bytes in a content-bound inspection cursor.
    pub const MAX_CURSOR_BYTES: usize = 256;
    /// Maximum requested fields, including the distinctness check.
    pub const MAX_FIELDS: usize = 10;
    /// Maximum entries in the independent inspection item-type filter.
    pub const MAX_TYPE_FILTERS: usize = 20;
    /// Max page items (inspection).
    pub const MAX_PAGE_ITEMS: usize = 128;
    /// Max page bytes (inspection).
    pub const MAX_PAGE_BYTES: usize = 32 * 1024;
    /// Record bytes (inspection).
    pub const RECORD_BYTES: usize = MAX_PAGE_BYTES - 4096;
}

/// Limits for `src/instances.rs`.
pub mod instances {
    /// Max definitions (instances).
    pub const MAX_DEFINITIONS: usize = 32;
    /// Max nesting (instances).
    pub const MAX_NESTING: usize = 8;
}

/// Limits for `src/interpolation.rs`.
pub mod interpolation {
    /// Maximum explicitly paired contours in an interpolation.
    pub const MAX_CONTOUR_PAIRS: usize = 512;
    /// Max count (interpolation).
    pub const MAX_COUNT: usize = 128;
    /// Max document spine leaves (interpolation).
    pub const MAX_DOCUMENT_SPINE_LEAVES: usize = 65536;
}

/// Limits for `src/job_process.rs`.
pub mod job_process {
    /// Default wall-clock lifetime for a worker, in milliseconds.
    pub const DEFAULT_LIFETIME_MS: u64 = 300_000;
    /// Default committed-memory ceiling for a worker, in MiB.
    pub const DEFAULT_MEMORY_MIB: u32 = 512;
    /// Minimum configurable committed-memory ceiling, in MiB.
    pub const MIN_MEMORY_MIB: u32 = 64;
    /// Max executable bytes (job process).
    pub const MAX_EXECUTABLE_BYTES: u64 = 512 * 1024 * 1024;
    /// Max lifetime ms (job process).
    pub const MAX_LIFETIME_MS: u64 = 3_600_000;
    /// Max memory mib (job process).
    pub const MAX_MEMORY_MIB: u32 = 2048;
}

/// Limits for `src/jobs/listing.rs`.
pub mod jobs_listing {
    /// Default number of records requested from retained jobs.
    pub const DEFAULT_PAGE_RECORDS: usize = 8;
    /// Max page records (jobs listing).
    pub const MAX_PAGE_RECORDS: usize = 32;
    /// Max page bytes (jobs listing).
    pub const MAX_PAGE_BYTES: usize = 32 * 1024;
    /// Max cursor bytes (jobs listing).
    pub const MAX_CURSOR_BYTES: usize = 1024;
}

/// Limits for `src/jobs/store.rs`.
pub mod jobs_store {
    /// Maximum stored process/runtime description bytes.
    pub const MAX_RUNTIME_BYTES: usize = 16 * 1024;
    /// SQLite row allowance for job input, state and record overhead.
    pub const MAX_SQL_ROW_BYTES: usize = super::jobs::MAX_INPUT_BYTES + super::jobs::MAX_STATE_BYTES + 16384;
    /// Maximum schema records read, including an extra incompatible table.
    pub const MAX_SCHEMA_RECORDS: usize = 4;
    /// Database bytes (jobs store).
    pub const DATABASE_BYTES: u64 = 512 * 1024 * 1024;
}

/// Limits for `src/jobs.rs`.
pub mod jobs {
    /// Maximum Unicode characters retained from a worker failure message.
    pub const MAX_ERROR_CHARACTERS: usize = 1024;
    /// Maximum UTF-8 bytes in a stored progress phase label.
    pub const MAX_PHASE_BYTES: usize = 64;
    /// Longest synchronous wait on a saved job, in milliseconds.
    pub const MAX_WAIT_MS: u64 = 30_000;
    /// Cooperative cancellation interval before stopping the owned runner.
    pub const CANCEL_GRACE_MS: u64 = 2_000;
    /// Maximum root path length under the existing platform string measure.
    pub const MAX_ROOT_LENGTH: usize = 4_000;
    /// Maximum explicit worker path length under the platform string measure.
    pub const MAX_WORKER_PATH_LENGTH: usize = super::paths::MAX_PATH_UNITS;
    /// Maximum nested documents visited for job resource verification.
    pub const MAX_RESOURCE_DOCUMENTS: usize = 512;
    /// Max jobs (jobs).
    pub const MAX_JOBS: usize = 128;
    /// Max active (jobs).
    pub const MAX_ACTIVE: usize = 32;
    /// Max attempts (jobs).
    pub const MAX_ATTEMPTS: u32 = 8;
    /// Max input bytes (jobs).
    pub const MAX_INPUT_BYTES: usize = 16 * 1024 * 1024;
    /// Max state bytes (jobs).
    pub const MAX_STATE_BYTES: usize = super::publications::MAX_RECEIPT_BYTES + 65536;
    /// Max store bytes (jobs).
    pub const MAX_STORE_BYTES: usize = 256 * 1024 * 1024;
}

/// Typed descriptor framing, independent of complete text-record budgets.
pub mod layered_descriptor {
    /// Maximum bytes inspected for one descriptor, including its version.
    pub const MAX_BYTES: usize = 64 * 1024;
    /// Maximum recursively nested descriptor value depth.
    pub const MAX_DEPTH: usize = 8;
    /// Maximum charged object and value nodes in one descriptor.
    pub const MAX_NODES: usize = 512;
    /// Maximum entries in one descriptor object or list.
    pub const MAX_CONTAINER: usize = 128;
    /// Maximum bytes in one descriptor class, key or enum identifier.
    pub const MAX_IDENTIFIER_BYTES: usize = 128;
    /// Maximum UTF-16 units in ordinary descriptor names and text values.
    pub const MAX_TEXT_UNITS: usize = 1024;
}

/// Shared layered text admission, resolution and diagnostic budgets.
pub mod layered_text {
    /// Complete native text record bytes, including transforms and descriptors.
    pub const MAX_RECORD_BYTES: usize = 64 * 1024;
    /// UTF-16 capacity for all admitted Unicode characters plus a terminator.
    pub const MAX_UTF16_UNITS: usize = 2 * super::text::MAX_TEXT_CHARS + 1;
    /// Maximum character or paragraph spans; shared by import and delivery.
    pub const MAX_RUNS: usize = 65;
    /// Maximum references followed in a named-style inheritance chain.
    pub const MAX_REFERENCE_DEPTH: usize = 2;
    /// Maximum borrowed property references in resolved character spans.
    pub const MAX_PROPERTY_REFERENCES: usize = 8192;
    /// Maximum printable ASCII bytes in a source or chosen font face name.
    pub const MAX_FACE_NAME_BYTES: usize = 128;
    /// Maximum ASCII bytes in an untrusted geometry-extension owner label.
    pub const MAX_SHAPE_OWNER_BYTES: usize = 128;
    /// Maximum distinct owner labels included in diagnostics.
    pub const MAX_SHAPE_OWNER_LABELS: usize = 8;
    /// Maximum source dash-pattern components accepted by diagnostics.
    pub const MAX_DASH_VALUES: usize = 32;
    /// Maximum unknown field names included in a style diagnostic.
    pub const MAX_UNMAPPED_FIELDS: usize = 16;
    /// Maximum unknown field names in compact geometry and rendering diagnostics.
    pub const MAX_BRIEF_FIELDS: usize = 8;
    /// Maximum records scanned while locating the global story payload.
    pub const MAX_TAGGED_RECORDS: usize = 512;
}

/// Limits for `src/layered/text_data.rs`.
pub mod layered_text_data {
    /// Maximum bytes in the local text-data dictionary.
    pub const MAX_BYTES: usize = 64 * 1024;
    /// Maximum bytes in an identifier or numeric token.
    pub const MAX_TOKEN_BYTES: usize = 128;
    /// Max nodes (layered text data).
    pub const MAX_NODES: usize = 4096;
    /// Max container (layered text data).
    pub const MAX_CONTAINER: usize = 512;
    /// Max depth (layered text data).
    pub const MAX_DEPTH: usize = 16;
    /// Max string bytes (layered text data).
    pub const MAX_STRING_BYTES: usize = 2 * super::layered_text::MAX_UTF16_UNITS + 2;
    /// Maximum bytes in the independent global text-data stream.
    pub const MAX_GLOBAL_BYTES: usize = 256 * 1024;
    /// Maximum charged nodes in the global stream, including its implicit root.
    pub const MAX_GLOBAL_NODES: usize = 32768;
    /// Maximum entries in one global dictionary or array.
    pub const MAX_GLOBAL_CONTAINER: usize = 4096;
    /// Maximum nesting depth in the global stream.
    pub const MAX_GLOBAL_DEPTH: usize = 32;
}

/// Limits for `src/layered/text_font_records.rs`.
pub mod layered_text_font_records {
    /// Max records (layered text font records).
    pub const MAX_RECORDS: usize = 256;
    /// Max selected (layered text font records).
    pub const MAX_SELECTED: usize = 8;
    /// Max version bytes (layered text font records).
    pub const MAX_VERSION_BYTES: usize = 512;
}

/// Limits for `src/layered/text_preset_records.rs`.
pub mod layered_text_preset_records {
    /// Maximum Unicode characters shown in each untrusted preset name preview.
    pub const PREVIEW_CHARACTERS: usize = 16;
    /// Max records (layered text preset records).
    pub const MAX_RECORDS: usize = 256;
    /// Max name bytes (layered text preset records).
    pub const MAX_NAME_BYTES: usize = 128;
    /// Max reported (layered text preset records).
    pub const MAX_REPORTED: usize = 4;
}

/// Limits for `src/layered.rs`.
pub mod layered {
    /// Text caches reserve one coordinate unit for their minimum pixel extent.
    pub const MAX_TEXT_CACHE_COORDINATE: f64 = super::model::MAX_COORDINATE - 1.0;
    /// Maximum UTF-16 units in a layer name or ordinary Unicode record.
    pub const MAX_NAME_UNITS: usize = 1024;
    /// Each editable item can contribute a layer and a folder boundary record.
    pub const MAX_SERIALIZED_RECORDS: usize = super::model::MAX_ITEMS * 2;
    /// Aggregate editable items across nested sources; independent of each document.
    pub const MAX_DECODED_ITEMS: usize = 1024;
    /// Maximum metadata entries attached to one layer.
    pub const MAX_METADATA_RECORDS: u32 = 16;
    /// Maximum ASCII bytes in an embedded-source link identifier.
    pub const MAX_LINK_ID_BYTES: usize = 128;
    /// Maximum axis in the standard layered container version.
    pub const MAX_STANDARD_DIMENSION: u32 = 30_000;
    /// Max file bytes (layered).
    pub const MAX_FILE_BYTES: usize = 32 * 1024 * 1024;
    /// Max decoded bytes (layered).
    pub const MAX_DECODED_BYTES: usize = 8 * 1024 * 1024;
    /// Max canvas pixels (layered).
    pub const MAX_CANVAS_PIXELS: usize = 1_048_576;
}

/// Limits for `src/lib.rs`.
pub mod request {
    /// Max request bytes (request).
    pub const MAX_REQUEST_BYTES: u64 = 16 * 1024 * 1024;
}

/// Limits for `src/masks.rs`.
pub mod masks {
    /// Max feather (masks).
    pub const MAX_FEATHER: u32 = 32;
    /// Max prepared pixels (masks).
    pub const MAX_PREPARED_PIXELS: u64 = 262_144;
    /// Max document pixels (masks).
    pub const MAX_DOCUMENT_PIXELS: u64 = 1_048_576;
    /// Max feather work (masks).
    pub const MAX_FEATHER_WORK: u64 = 67_108_864;
}

/// Limits for `src/mcp.rs`.
pub mod mcp {
    /// Maximum tool definitions in a full-catalog page.
    pub const PAGE: usize = 8;
    /// Maximum UTF-8 bytes in a nonempty string request identifier.
    pub const MAX_ID_BYTES: usize = 256;
    /// Max message bytes (mcp).
    pub const MAX_MESSAGE_BYTES: usize = super::request::MAX_REQUEST_BYTES as usize + 16384;
    /// Max response bytes (mcp).
    pub const MAX_RESPONSE_BYTES: usize = 96 * 1024 * 1024;
    /// Max pending (mcp).
    pub const MAX_PENDING: usize = 8;
    /// Max request ids (mcp).
    pub const MAX_REQUEST_IDS: usize = 4096;
    /// Core catalog bytes (mcp).
    pub const CORE_CATALOG_BYTES: usize = 96 * 1024;
}

/// Limits for `src/mcp_preview.rs`.
pub mod mcp_preview {
    /// Max images (mcp preview).
    pub const MAX_IMAGES: usize = 4;
    /// Max image base64 bytes (mcp preview).
    pub const MAX_IMAGE_BASE64_BYTES: usize = 8 * 1024 * 1024;
}

/// Limits for `src/measurements.rs`.
pub mod measurements {
    /// Max samples (measurements).
    pub const MAX_SAMPLES: usize = 256;
}

/// Limits for `src/meshes.rs`.
pub mod meshes {
    /// Fixed maximum iterations for contraction-bounded inverse mesh sampling.
    pub const INVERSE_STEPS: usize = 128;
    /// Maximum samples on each cell axis in the SVG texture.
    pub const MAX_SVG_SAMPLES_PER_CELL: u32 = 256;
    /// Default samples on each cell axis in the SVG texture.
    pub const DEFAULT_SVG_SAMPLES_PER_CELL: u32 = 16;
    /// Max axis (meshes).
    pub const MAX_AXIS: usize = 8;
    /// Max samples (meshes).
    pub const MAX_SAMPLES: usize = 1024;
    /// Max contraction (meshes).
    pub const MAX_CONTRACTION: f64 = 0.75;
    /// Max texture pixels (meshes).
    pub const MAX_TEXTURE_PIXELS: usize = 65536;
    /// Max svg texture pixels (meshes).
    pub const MAX_SVG_TEXTURE_PIXELS: usize = 131072;
}

/// Limits for `src/metadata.rs`.
pub mod metadata {
    /// Maximum metadata payload bytes in each emitted JPEG comment segment.
    pub const JPEG_PART_BYTES: usize = 60000;
    /// Maximum parts needed for the complete bounded metadata packet.
    pub const MAX_JPEG_PARTS: usize = MAX_PACKET_BYTES.div_ceil(JPEG_PART_BYTES);
    /// Maximum UTF-8 bytes in one descriptive metadata text value.
    pub const MAX_TEXT_BYTES: usize = 8192;
    /// Maximum tags or entries in either metadata property map.
    pub const MAX_ENTRIES: usize = 64;
    /// Maximum UTF-8 bytes in one nonempty metadata tag.
    pub const MAX_TAG_BYTES: usize = 128;
    /// Max record bytes (metadata).
    pub const MAX_RECORD_BYTES: usize = 16 * 1024;
    /// Max document bytes (metadata).
    pub const MAX_DOCUMENT_BYTES: usize = 64 * 1024;
    /// Max packet bytes (metadata).
    pub const MAX_PACKET_BYTES: usize = 256 * 1024;
}

/// Limits for `src/model.rs`.
pub mod model {
    /// Maximum ASCII bytes in a portable engine identifier.
    pub const MAX_ID_BYTES: usize = 128;
    /// Maximum UTF-8 bytes in an item or channel name.
    pub const MAX_NAME_BYTES: usize = 1024;
    /// Max dimension (model).
    pub const MAX_DIMENSION: u32 = 32768;
    /// Max items (model).
    pub const MAX_ITEMS: usize = 256;
    /// Max segments (model).
    pub const MAX_SEGMENTS: usize = 4096;
    /// Max stored pixels (model).
    pub const MAX_STORED_PIXELS: usize = 65536;
    /// Max document bytes (model).
    pub const MAX_DOCUMENT_BYTES: usize = 768 * 1024;
    /// Max large vector items (model).
    pub const MAX_LARGE_VECTOR_ITEMS: usize = 8192;
    /// Max large vector commands (model).
    pub const MAX_LARGE_VECTOR_COMMANDS: usize = 131072;
    /// Max large vector bytes (model).
    pub const MAX_LARGE_VECTOR_BYTES: usize = 8 * 1024 * 1024;
    /// Max large raster items (model).
    pub const MAX_LARGE_RASTER_ITEMS: usize = 8192;
    /// Max large raster commands (model).
    pub const MAX_LARGE_RASTER_COMMANDS: usize = 131072;
    /// Max large raster bytes (model).
    pub const MAX_LARGE_RASTER_BYTES: usize = 8 * 1024 * 1024;
    /// Max coordinate (model).
    pub const MAX_COORDINATE: f64 = 32768.0;
}

/// Limits for `src/objects.rs`.
pub mod objects {
    /// Max nesting (objects).
    pub const MAX_NESTING: usize = 4;
    /// Max rendered objects (objects).
    pub const MAX_RENDERED_OBJECTS: usize = 32;
}

/// Limits for the native pixel editor's independent source cache.
pub mod native_pixels {
    /// Maximum decoded source tiles retained by one native pixel edit reader.
    pub const CACHE_TILES: usize = 16;
}

/// Limits for full-canvas vector overview images.
pub mod previews {
    /// Smallest requested overview axis in pixels.
    pub const MIN_OVERVIEW_AXIS: u32 = 8;
    /// Largest requested overview axis in pixels before supersampling.
    pub const MAX_OVERVIEW_AXIS: u32 = 1024;
}

/// Runtime filesystem paths, measured by the platform's `OsStr::len` units.
pub mod paths {
    /// Maximum encoded path units; does not change host filesystem limits.
    pub const MAX_PATH_UNITS: usize = 4096;
}

/// Independent request-list admission budgets for document queries.
pub mod query {
    /// Maximum entries in a query's item-type filter.
    pub const MAX_TYPES: usize = 12;
    /// Maximum entries in a query's geometry-kind filter.
    pub const MAX_SHAPES: usize = 8;
}

/// Shared connection budgets for bounded local SQLite stores.
pub mod sqlite {
    /// Storage-format page size used to derive every database page budget.
    pub const PAGE_BYTES: u64 = 4096;
    /// Maximum wait for another local database writer, in milliseconds.
    pub const BUSY_TIMEOUT_MS: u64 = 250;
    /// Connection page-cache allowance expressed in KiB.
    pub const CACHE_KIB: u64 = 4096;
    /// Maximum SQL bytes on receipt and job connections; sessions have their own.
    pub const MAX_SQL_BYTES: usize = 16 * 1024;
    /// Maximum columns on receipt and job connections; sessions have their own.
    pub const MAX_COLUMNS: usize = 32;
}

/// Identifier construction during cross-document transfer.
pub mod transfer {
    /// Maximum prefix bytes, reserving space for generated object identifiers.
    pub const MAX_PREFIX_BYTES: usize = 32;
}

/// Schema-guided resolution of workspace request arguments.
pub mod workspace {
    /// Maximum recursion depth while walking request schemas and values.
    pub const MAX_ARGUMENT_DEPTH: usize = 128;
}

/// Limits for `src/paint.rs`.
pub mod paint {
    /// Max paint samples (paint).
    pub const MAX_PAINT_SAMPLES: usize = 4096;
    /// Max stops (paint).
    pub const MAX_STOPS: usize = 64;
    /// Max pattern pixels (paint).
    pub const MAX_PATTERN_PIXELS: usize = 4096;
    /// Max paint work (paint).
    pub const MAX_PAINT_WORK: u64 = 134_217_728;
}

/// Limits for `src/path_text.rs`.
pub mod path_text {
    /// Maximum path measurement subdivision depth shared with interpolation spines.
    pub const MAX_SUBDIVISION_DEPTH: usize = 24;
    /// Max commands (path text).
    pub const MAX_COMMANDS: usize = 1024;
    /// Max leaves (path text).
    pub const MAX_LEAVES: usize = 32768;
    /// Max document leaves (path text).
    pub const MAX_DOCUMENT_LEAVES: usize = 65536;
}

/// Limits for `src/pdf.rs`.
pub mod pdf {
    /// Max commands (pdf).
    pub const MAX_COMMANDS: usize = 262_144;
    /// Max objects (pdf).
    pub const MAX_OBJECTS: usize = 32_768;
    /// Max image pixels (pdf).
    pub const MAX_IMAGE_PIXELS: u64 = 4_194_304;
}

/// Limits for `src/pixel_brush.rs`.
pub mod pixel_brush {
    /// Maximum unscaled brush diameter in native pixels.
    pub const MAX_DIAMETER: u32 = 512;
    /// Max points (pixel brush).
    pub const MAX_POINTS: usize = 1024;
    /// Max dabs (pixel brush).
    pub const MAX_DABS: usize = 8192;
    /// Max work (pixel brush).
    pub const MAX_WORK: u64 = 67_108_864;
    /// Max memory bytes (pixel brush).
    pub const MAX_MEMORY_BYTES: u64 = 128 * 1024 * 1024;
    /// Max texture pixels (pixel brush).
    pub const MAX_TEXTURE_PIXELS: usize = 4096;
}

/// Limits for `src/pixel_warps.rs`.
pub mod pixel_warps {
    /// Max axis (pixel warps).
    pub const MAX_AXIS: usize = 16;
    /// Max joints (pixel warps).
    pub const MAX_JOINTS: usize = 16;
    /// Max samples (pixel warps).
    pub const MAX_SAMPLES: usize = 256;
    /// Max work (pixel warps).
    pub const MAX_WORK: u64 = 67_108_864;
    /// Min altitude (pixel warps).
    pub const MIN_ALTITUDE: f64 = 1. / 1024.;
    /// Min relative area (pixel warps).
    pub const MIN_RELATIVE_AREA: f64 = 1. / 1_048_576.;
}

/// Limits for `src/prepress/bindings.rs`.
pub mod prepress_bindings {
    /// Max bindings (prepress bindings).
    pub const MAX_BINDINGS: usize = 1024;
}

/// Limits for `src/prepress/images.rs`.
pub mod prepress_images {
    /// Max source profiles (prepress images).
    pub const MAX_SOURCE_PROFILES: usize = 16;
}

/// Limits for `src/prepress.rs`.
pub mod prepress {
    /// Maximum requested output sample positions in native ink preparation.
    pub const MAX_SAMPLES: usize = 64;
    /// Max spots (prepress).
    pub const MAX_SPOTS: usize = 28;
    /// Max buffer values (prepress).
    pub const MAX_BUFFER_VALUES: u64 = 16_777_216;
    /// Max work (prepress).
    pub const MAX_WORK: u64 = 134_217_728;
}

/// Limits for `src/primitives.rs`.
pub mod primitives {
    /// Max polygon points (primitives).
    pub const MAX_POLYGON_POINTS: usize = 1024;
    /// Max sides (primitives).
    pub const MAX_SIDES: u32 = 256;
    /// Max star points (primitives).
    pub const MAX_STAR_POINTS: u32 = 128;
}

/// Limits for `src/profiles/cmyk.rs`.
pub mod profiles_cmyk {
    /// Max profile bytes (profiles cmyk).
    pub const MAX_PROFILE_BYTES: usize = 4 * 1024 * 1024;
}

/// Limits for `src/profiles/gamut.rs`.
pub mod profiles_gamut {
    /// Max samples (profiles gamut).
    pub const MAX_SAMPLES: usize = 4096;
}

/// Limits for `src/profiles.rs`.
pub mod profiles {
    /// Maximum entries in an ICC tone-reproduction curve, shared by profile admission and continuous table reconstruction.
    pub const MAX_CURVE_ENTRIES: usize = 65536;
    /// Fixed bisection steps for continuous parametric curve inversion; changing this also requires numerical accuracy verification.
    pub const CURVE_INVERSE_STEPS: usize = 64;
    /// Maximum colors in a device or elementary ink conversion batch.
    pub const MAX_CONVERSION_SAMPLES: usize = 4096;
    /// Max profile bytes (profiles).
    pub const MAX_PROFILE_BYTES: usize = 256 * 1024;
    /// Max profile tags (profiles).
    pub const MAX_PROFILE_TAGS: usize = 128;
    /// Transform stack bytes (profiles).
    pub const TRANSFORM_STACK_BYTES: usize = 32 * 1024 * 1024;
}

/// Limits for `src/proof.rs`.
pub mod proof {
    /// Max samples (proof).
    pub const MAX_SAMPLES: usize = 64;
}

/// Limits for `src/publications/store.rs`.
pub mod publications_store {
    /// SQLite row allowance for a receipt and record overhead.
    pub const MAX_SQL_ROW_BYTES: usize = super::publications::MAX_RECEIPT_BYTES + 16384;
    /// Maximum schema records read while rejecting incompatible tables.
    pub const MAX_SCHEMA_RECORDS: usize = 3;
    /// Database bytes (publications store).
    pub const DATABASE_BYTES: u64 = 128 * 1024 * 1024;
}

/// Limits for `src/publications.rs`.
pub mod publications {
    /// Max receipt bytes (publications).
    pub const MAX_RECEIPT_BYTES: usize = 1024 * 1024;
    /// Max ledger bytes (publications).
    pub const MAX_LEDGER_BYTES: usize = 64 * 1024 * 1024;
    /// Max records (publications).
    pub const MAX_RECORDS: usize = 1024;
}

/// Limits for `src/publish.rs`.
pub mod publish {
    /// Max output bytes (publish).
    pub const MAX_OUTPUT_BYTES: usize = 32 * 1024 * 1024;
}

/// Limits for `src/raw/retained.rs`.
pub mod raw_retained {
    /// Max source bytes (raw retained).
    pub const MAX_SOURCE_BYTES: usize = 131072;
    /// Max recipe bytes (raw retained).
    pub const MAX_RECIPE_BYTES: u64 = 16384;
}

/// Limits for `src/raw.rs`.
pub mod raw {
    /// Maximum bytes of padding after a row of sensor samples.
    pub const MAX_ROW_PADDING_BYTES: usize = 4096;
    /// Max pixels (raw).
    pub const MAX_PIXELS: usize = 16384;
}

/// Limits for `src/render/coverage_cache.rs`.
pub mod render_coverage_cache {
    /// Max pixels (render coverage cache).
    pub const MAX_PIXELS: u64 = super::raster::MAX_PIXELS;
}

/// Limits for `src/render/filter_regions.rs`.
pub mod render_filter_regions {
    /// Max references (render filter regions).
    pub const MAX_REFERENCES: usize = 131_072;
}

/// Limits for `src/render/spatial.rs`.
pub mod render_spatial {
    /// Expanded item count at which tiled rendering builds a spatial index.
    pub const MIN_ITEMS: usize = 128;
    /// Edge (render spatial).
    pub const EDGE: u32 = 8;
    /// Max references (render spatial).
    pub const MAX_REFERENCES: u64 = 1_048_576;
}

/// Limits for `src/render/tiled.rs`.
pub mod render_tiled {
    /// Max pixels (render tiled).
    pub const MAX_PIXELS: u64 = super::raster::MAX_PIXELS;
    /// Edge (render tiled).
    pub const EDGE: u32 = super::raster::TILE_EDGE;
}

/// Limits for `src/render/traversal.rs`.
pub mod render_traversal {
    /// Neighborhood units (render traversal).
    pub const NEIGHBORHOOD_UNITS: u32 = 256;
}

/// Limits for `src/render.rs`.
pub mod render {
    /// Max render pixels (render).
    pub const MAX_RENDER_PIXELS: u64 = 1_048_576;
    /// Max render work (render).
    pub const MAX_RENDER_WORK: u64 = 67_108_864;
    /// Max buffer pixels (render).
    pub const MAX_BUFFER_PIXELS: u64 = 4_194_304;
}

/// Limits for `src/repair.rs`.
pub mod repair {
    /// Max work (repair).
    pub const MAX_WORK: u64 = 67_108_864;
    /// Max patches (repair).
    pub const MAX_PATCHES: usize = 4096;
}

/// Limits for `src/repeats.rs`.
pub mod repeats {
    /// Max copies (repeats).
    pub const MAX_COPIES: usize = 128;
}

/// Limits for `src/resample.rs`.
pub mod resample {
    /// Max axis taps (resample).
    pub const MAX_AXIS_TAPS: u64 = 65_536;
    /// Max work (resample).
    pub const MAX_WORK: u64 = 67_108_864;
}

/// Limits for `src/responses.rs`.
pub mod responses {
    /// Compact target bytes (responses).
    pub const COMPACT_TARGET_BYTES: usize = 8 * 1024;
}

/// Limits for `src/retouch.rs`.
pub mod retouch {
    /// Max work (retouch).
    pub const MAX_WORK: u64 = 67_108_864;
    /// Max memory bytes (retouch).
    pub const MAX_MEMORY_BYTES: u64 = 128 * 1024 * 1024;
    /// Max iterations (retouch).
    pub const MAX_ITERATIONS: u32 = 4096;
}

/// Limits for `src/sample_import.rs`.
pub mod sample_import {
    /// Scratch allocation ceiling for decoders producing inline samples.
    pub const MAX_INLINE_DECODER_BYTES: usize = 16 * 1024 * 1024;
    /// Aggregate decoded padded TIFF tile work, separate from native storage.
    pub const MAX_TIFF_PADDED_BYTES: u64 = 64 * 1024 * 1024;
    /// Max native decoded bytes (sample import).
    pub const MAX_NATIVE_DECODED_BYTES: usize = 64 * 1024 * 1024;
}

/// Limits for `src/sample_profiles.rs`.
pub mod sample_profiles {
    /// Max encoded profile bytes (sample profiles).
    pub const MAX_ENCODED_PROFILE_BYTES: usize = 512 * 1024;
}

/// Limits for `src/sample_store.rs`.
pub mod sample_store {
    /// Tile edge (sample store).
    pub const TILE_EDGE: u32 = super::raster::TILE_EDGE;
    /// Max pixels (sample store).
    pub const MAX_PIXELS: u64 = super::raster::MAX_PIXELS;
    /// Max tiles (sample store).
    pub const MAX_TILES: usize = 2048;
    /// Max region pixels (sample store).
    pub const MAX_REGION_PIXELS: u64 = 65_536;
}

/// Limits for `src/sample_tiff/tiled.rs`.
pub mod sample_tiff_tiled {
    /// Max strip bytes (sample tiff tiled).
    pub const MAX_STRIP_BYTES: usize = 16 * 1024 * 1024;
}

/// Limits for `src/scene/hierarchy.rs`.
pub mod scene_hierarchy {
    /// Max fast point error (scene hierarchy).
    pub const MAX_FAST_POINT_ERROR: f64 = 1e-9;
}

/// Limits for `src/scene.rs`.
pub mod scene {
    /// Max cached chains (scene).
    pub const MAX_CACHED_CHAINS: usize = 128;
    /// Max depth (scene).
    pub const MAX_DEPTH: usize = 16;
}

/// Limits for `src/schema.rs`.
pub mod schema {
    /// Maximum UTF-8 bytes in a schema name or focused selector.
    pub const MAX_SELECTOR_BYTES: usize = 128;
    /// Outline bytes (schema).
    pub const OUTLINE_BYTES: usize = 12 * 1024;
}

/// Limits for `src/selection_analysis.rs`.
pub mod selection_analysis {
    /// Max targets (selection analysis).
    pub const MAX_TARGETS: usize = 32;
    /// Max edge radius (selection analysis).
    pub const MAX_EDGE_RADIUS: u32 = 8;
}

/// Limits for `src/selections.rs`.
pub mod selections {
    /// Max pixels (selections).
    pub const MAX_PIXELS: u64 = 262_144;
    /// Max work (selections).
    pub const MAX_WORK: u64 = 67_108_864;
    /// Max radius (selections).
    pub const MAX_RADIUS: u32 = 32;
    /// Max polygon points (selections).
    pub const MAX_POLYGON_POINTS: usize = 1024;
    /// Coverage subrows (selections).
    pub const COVERAGE_SUBROWS: u32 = 256;
}

/// Limits for `src/sequences.rs`.
pub mod sequences {
    /// Max frames (sequences).
    pub const MAX_FRAMES: usize = 256;
    /// Max pixels (sequences).
    pub const MAX_PIXELS: u64 = super::raster::MAX_PIXELS;
}

/// Limits for `src/sessions.rs`.
pub mod sessions {
    /// Maximum receipts requested in one history page.
    pub const MAX_PAGE_RECEIPTS: usize = 128;
    /// Maximum exclusive filename reservations attempted for a new database.
    pub const MAX_RESERVATION_ATTEMPTS: usize = 64;
    /// Small test-only cache that makes interruption fixtures exercise disk writes.
    pub const FAULT_CACHE_KIB: usize = 64;
    /// Maximum serialized bytes in each undo or redo stack.
    pub const MAX_STACK_BYTES: usize = 4096;
    /// Maximum UTF-8 bytes in a retained edit-history label.
    pub const MAX_LABEL_BYTES: usize = 512;
    /// Maximum serialized provenance bytes in a continuation record.
    pub const MAX_LINEAGE_BYTES: usize = 32 * 1024;
    /// SQLite row allowance for a state and independent record overhead.
    pub const MAX_SQL_ROW_BYTES: usize = MAX_STATE_BYTES + 65536;
    /// Maximum bytes of SQL admitted by a session connection.
    pub const MAX_SQL_BYTES: usize = 32 * 1024;
    /// Maximum columns admitted by a session connection.
    pub const MAX_SQL_COLUMNS: usize = 128;
    /// Maximum SQL parameters admitted by a session connection.
    pub const MAX_SQL_VARIABLES: usize = 32;
    /// Maximum schema records read while rejecting incompatible tables.
    pub const MAX_SCHEMA_RECORDS: usize = 16;
    /// Pages copied per cancellable backup step.
    pub const BACKUP_STEP_PAGES: usize = 256;
    /// Fixed I/O buffer used while hashing or copying history backups.
    pub const BACKUP_BUFFER_BYTES: usize = 65536;
    /// Max states (sessions).
    pub const MAX_STATES: usize = 256;
    /// Max requests (sessions).
    pub const MAX_REQUESTS: usize = 2048;
    /// Max snapshots (sessions).
    pub const MAX_SNAPSHOTS: usize = 32;
    /// Max state bytes (sessions).
    pub const MAX_STATE_BYTES: usize = super::model::MAX_LARGE_VECTOR_BYTES + 16384;
    /// Max history bytes (sessions).
    pub const MAX_HISTORY_BYTES: i64 = 64 * 1024 * 1024;
    /// Max database bytes (sessions).
    pub const MAX_DATABASE_BYTES: u64 = 128 * 1024 * 1024;
    /// Max receipt bytes (sessions).
    pub const MAX_RECEIPT_BYTES: usize = 65536;
}

/// Limits for `src/simplify.rs`.
pub mod simplify {
    /// Max span (simplify).
    pub const MAX_SPAN: usize = 32;
    /// Max work (simplify).
    pub const MAX_WORK: usize = 400_000;
}

/// Limits for `src/spatial_filters.rs`.
pub mod spatial_filters {
    /// Maximum dimension of a displacement field, independent of its total-vector budget.
    pub const MAX_MAP_AXIS: u32 = 256;
    /// Max map pixels (spatial filters).
    pub const MAX_MAP_PIXELS: usize = 4096;
}

/// Limits for explicit geometry snapping.
pub mod snapping {
    /// Maximum frozen reference targets in one snap operation.
    pub const MAX_TARGETS: usize = 64;
}

/// Limits for exact quadratic parameter separation.
pub mod booleans_topology_quadratic {
    /// Maximum dyadic parameter bits while seeking a certified interior cut.
    pub const MAX_PARAMETER_BITS: usize = 4096;
}

/// Limits for `src/stored_samples.rs`.
pub mod stored_samples {
    /// Aggregate decoded source pixels may cover each native image twice.
    pub const MAX_SOURCE_DECODING_PASSES: u64 = 2;
    /// Max patches (stored samples).
    pub const MAX_PATCHES: usize = 256;
    /// Max patch pixels (stored samples).
    pub const MAX_PATCH_PIXELS: u64 = 65_536;
    /// Cache pixels (stored samples).
    pub const CACHE_PIXELS: u64 = 262_144;
    /// Cache tiles (stored samples).
    pub const CACHE_TILES: usize = (CACHE_PIXELS
        / (super::sample_store::TILE_EDGE as u64 * super::sample_store::TILE_EDGE as u64))
        as usize;
}

/// Limits for `src/strokes/brush.rs`.
pub mod strokes_brush {
    /// Max placements (strokes brush).
    pub const MAX_PLACEMENTS: usize = 8192;
}

/// Limits for `src/strokes/outline.rs`.
pub mod strokes_outline {
    /// Max outline commands (strokes outline).
    pub const MAX_OUTLINE_COMMANDS: usize = 65_536;
    /// Max points (strokes outline).
    pub const MAX_POINTS: usize = 16_384;
}

/// Limits for `src/strokes.rs`.
pub mod strokes {
    /// Outline resolution (strokes).
    pub const OUTLINE_RESOLUTION: u32 = 16;
    /// Max intervals (strokes).
    pub const MAX_INTERVALS: usize = 64;
    /// Max document work (strokes).
    pub const MAX_DOCUMENT_WORK: u64 = 32_768;
    /// Max instance work (strokes).
    pub const MAX_INSTANCE_WORK: u64 = 131_072;
    /// Max range work (strokes).
    pub const MAX_RANGE_WORK: u64 = 524_288;
    /// Max svg commands (strokes).
    pub const MAX_SVG_COMMANDS: u64 = 131_072;
    /// Max svg range commands (strokes).
    pub const MAX_SVG_RANGE_COMMANDS: u64 = 262_144;
}

/// Limits for `src/svg_import/definitions.rs`.
pub mod svg_import_definitions {
    /// Max definitions (svg import definitions).
    pub const MAX_DEFINITIONS: usize = 64;
    /// Max reference depth (svg import definitions).
    pub const MAX_REFERENCE_DEPTH: usize = 16;
}

/// Limits for `src/svg_import.rs`.
pub mod svg_import {
    /// Maximum transform functions on one SVG element.
    pub const MAX_TRANSFORMS: usize = 64;
    /// Maximum UTF-8 bytes of an SVG font family or explicit family binding.
    pub const MAX_FONT_FAMILY_BYTES: usize = 256;
    /// Max bytes (svg import).
    pub const MAX_BYTES: usize = 256 * 1024;
    /// Max nodes (svg import).
    pub const MAX_NODES: u32 = 4096;
    /// Max large bytes (svg import).
    pub const MAX_LARGE_BYTES: usize = 8 * 1024 * 1024;
    /// Max large nodes (svg import).
    pub const MAX_LARGE_NODES: u32 = 65536;
}

/// Limits for `src/swatches.rs`.
pub mod swatches {
    /// Max swatches (swatches).
    pub const MAX_SWATCHES: usize = 256;
    /// Max depth (swatches).
    pub const MAX_DEPTH: usize = 8;
}

/// Limits for `src/text/flow/hyphens.rs`.
pub mod text_flow_hyphens {
    /// Max rule sets (text flow hyphens).
    pub const MAX_RULE_SETS: usize = 16;
}

/// Limits for `src/text/flow/lists.rs`.
pub mod text_flow_lists {
    /// Max levels (text flow lists).
    pub const MAX_LEVELS: usize = 9;
    /// Max lists (text flow lists).
    pub const MAX_LISTS: usize = 64;
    /// Max counter (text flow lists).
    pub const MAX_COUNTER: u32 = 999_999;
    /// Max affix (text flow lists).
    pub const MAX_AFFIX: usize = 32;
}

/// Limits for `src/text/flow.rs`.
pub mod text_flow {
    /// Max stories (text flow).
    pub const MAX_STORIES: usize = 32;
    /// Max paragraphs (text flow).
    pub const MAX_PARAGRAPHS: usize = 256;
    /// Max slots (text flow).
    pub const MAX_SLOTS: usize = 64;
    /// Max columns (text flow).
    pub const MAX_COLUMNS: usize = 16;
}

/// Limits for `src/text.rs`.
pub mod text {
    /// Max text chars (text).
    pub const MAX_TEXT_CHARS: usize = 4096;
    /// Max text ranges (text).
    pub const MAX_TEXT_RANGES: usize = 64;
    /// Max glyphs (text).
    pub const MAX_GLYPHS: usize = 8192;
    /// Max outline commands (text).
    pub const MAX_OUTLINE_COMMANDS: usize = 131072;
    /// Max shaping work (text).
    pub const MAX_SHAPING_WORK: usize = 1_048_576;
}

/// Limits for `src/tracing.rs`.
pub mod tracing {
    /// Max pixels (tracing).
    pub const MAX_PIXELS: usize = 1_048_576;
    /// Max colors (tracing).
    pub const MAX_COLORS: usize = 64;
    /// Max edges (tracing).
    pub const MAX_EDGES: usize = 262_144;
}

/// Limits for `src/variants.rs`.
pub mod variants {
    /// Max bindings (variants).
    pub const MAX_BINDINGS: usize = 64;
    /// Max datasets (variants).
    pub const MAX_DATASETS: usize = 32;
    /// Max inheritance (variants).
    pub const MAX_INHERITANCE: usize = 8;
}

/// Limits for `src/vector_native/pdf_read.rs`.
pub mod vector_native_pdf_read {
    /// Maximum bytes scanned for a PDF keyword or numeric token.
    pub const MAX_TOKEN_BYTES: usize = 128;
    /// Maximum decoded bytes in one PDF name.
    pub const MAX_NAME_BYTES: usize = 256;
    /// Maximum literal-string parser steps, counting a closing delimiter but not the byte skipped after an escape.
    pub const MAX_STRING_STEPS: usize = 65536;
    /// Maximum non-whitespace hex digits in one PDF byte string.
    pub const MAX_HEX_DIGITS: usize = 131072;
    /// Maximum preview pages counted in the admitted PDF page tree.
    pub const MAX_PAGES: usize = 32;
    /// Max objects (vector native pdf read).
    pub const MAX_OBJECTS: usize = 4096;
    /// Max nodes (vector native pdf read).
    pub const MAX_NODES: usize = 131072;
    /// Max depth (vector native pdf read).
    pub const MAX_DEPTH: usize = 32;
}

/// Limits for `src/vector_native/tokens.rs`.
pub mod vector_native_tokens {
    /// Maximum nesting of an editable-text literal string.
    pub const MAX_STRING_DEPTH: usize = 32;
    /// Maximum decoded bytes in one editable-text literal string.
    pub const MAX_STRING_BYTES: usize = 65536;
    /// Maximum scanned bytes of a native word or name, including its leading slash.
    pub const MAX_WORD_BYTES: usize = 1024;
    /// Maximum native typed-container depth during end lookup and artboard traversal.
    pub const MAX_CONTAINER_DEPTH: usize = 32;
    /// Max tokens (vector native tokens).
    pub const MAX_TOKENS: usize = 262144;
}

/// Limits for `src/vector_native/write.rs`.
pub mod vector_native_write {
    /// Max coordinate (vector native write).
    pub const MAX_COORDINATE: f64 = 16383.0;
}

/// Limits for `src/vector_native.rs`.
pub mod vector_native {
    /// Maximum decoded bytes of the native metadata header stream.
    pub const MAX_METADATA_BYTES: usize = 65536;
    /// Maximum pending operands before an editable artwork operator.
    pub const MAX_OPERANDS: usize = 32;
    /// Max source bytes (vector native).
    pub const MAX_SOURCE_BYTES: usize = 16 * 1024 * 1024;
    /// Max decoded bytes (vector native).
    pub const MAX_DECODED_BYTES: usize = 16 * 1024 * 1024;
    /// Max blocks (vector native).
    pub const MAX_BLOCKS: usize = 256;
}

/// Limits for `src/visual_diff.rs`.
pub mod visual_diff {
    /// Max pixels (visual diff).
    pub const MAX_PIXELS: u64 = super::render::MAX_RENDER_PIXELS;
}

/// Limits for `src/volumes.rs`.
pub mod volumes {
    /// Maximum recursive face-partition depth for volume ordering.
    pub const MAX_PARTITION_DEPTH: usize = 128;
    /// Max edges (volumes).
    pub const MAX_EDGES: usize = 128;
    /// Max faces (volumes).
    pub const MAX_FACES: usize = 192;
}

/// Limits for `src/warps.rs`.
pub mod warps {
    /// Max maps (warps).
    pub const MAX_MAPS: usize = 8;
    /// Max degree (warps).
    pub const MAX_DEGREE: usize = 128;
    /// Max work (warps).
    pub const MAX_WORK: usize = 2_000_000;
    /// Max bits (warps).
    pub const MAX_BITS: u64 = 8192;
    /// Max depth (warps).
    pub const MAX_DEPTH: usize = 24;
    /// Max input edges (warps).
    pub const MAX_INPUT_EDGES: usize = 256;
    /// Max samples (warps).
    pub const MAX_SAMPLES: usize = 256;
}

/// Limits for `src/work_paths.rs`.
pub mod work_paths {
    /// Maximum operands of one compound region or explicit region combination.
    pub const MAX_OPERANDS: usize = 16;
    /// Max components (work paths).
    pub const MAX_COMPONENTS: usize = 64;
    /// Max component depth (work paths).
    pub const MAX_COMPONENT_DEPTH: usize = 8;
}

/// Shared native image storage, asset and tiled-output geometry ceilings.
pub mod raster {
    /// Pixel ceiling shared by native storage, assets, tiled output and sequences.
    pub const MAX_PIXELS: u64 = 16_777_216;
    /// Maximum native block and unindexed composition tile edge, in pixels.
    pub const TILE_EDGE: u32 = 128;
}

/// Limits for explicit delivery sampling.
pub mod render_quality {
    /// Maximum requested delivery scale, before supersampling.
    pub const MAX_SCALE: u32 = 4;
    /// Maximum factor among the fixed supersample2 and supersample4 modes.
    pub const MAX_ANTIALIAS_FACTOR: u32 = 4;
    /// Maximum evaluation scale including supersampling.
    pub const MAX_INTERNAL_SCALE: u32 = MAX_SCALE * MAX_ANTIALIAS_FACTOR;
    /// Maximum symmetric effect padding in document units.
    pub const MAX_PADDING: u32 = 256;
}
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeMap;

    #[test]
    fn generated_reference_matches_every_compiled_constant() {
        let mut documented = BTreeMap::new();
        for line in include_str!("../docs/LIMITS.md").lines() {
            if !line.starts_with("| `") {
                continue;
            }
            let fields: Vec<_> = line.split('|').map(str::trim).collect();
            let name = fields[1].trim_matches('`');
            let value: serde_json::Value = serde_json::from_str(fields[3]).unwrap();
            assert!(documented.insert(name, value).is_none());
        }
        let compiled = compiled_values();
        assert_eq!(documented.len(), compiled.len());
        for (name, value) in compiled {
            assert_eq!(documented.get(name), Some(&value), "{name}");
        }
    }
}
