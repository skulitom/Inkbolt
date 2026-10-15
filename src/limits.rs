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
    /// Per-pixel work charge for one curve adjustment.
    pub const CURVE_WORK: u64 = 8;
    /// Per-pixel work charge for a simple adjustment operator.
    pub const SIMPLE_OPERATOR_WORK: u64 = 4;
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
    /// Machine-epsilon allowance for nearest-pixel boundary stabilization.
    pub const PIXEL_BOUNDARY_EPSILONS: u32 = 8;
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
    /// Work units between cooperative cancellation checks in the selection solver.
    pub const CONTROL_WORK_INTERVAL: u64 = 2048;
    /// Maximum integer smoothness coefficient in the selection energy.
    pub const MAX_SMOOTHNESS: u32 = 65535;
    /// Maximum squared distance across the four encoded-byte features.
    pub const MAX_EDGE_SCALE: u32 = 4 * 255 * 255;
    /// Shared default smoothness and edge scale, retained by the options schema.
    pub const DEFAULT_WEIGHT: u32 = 4096;
    /// Max pixels (assistance segment).
    pub const MAX_PIXELS: usize = 65_536;
    /// Max seeds (assistance segment).
    pub const MAX_SEEDS: usize = 32;
    /// Max work (assistance segment).
    pub const MAX_WORK: u64 = 67_108_864;
}

/// Limits for `src/assistance.rs`.
pub mod assistance {
    /// Maximum checked absolute geometry error after layout placement.
    pub const PLACEMENT_ERROR: f64 = 1e-7;
    /// Max items (assistance).
    pub const MAX_ITEMS: usize = 64;
}

/// Limits for `src/boards.rs`.
pub mod boards {
    /// Maximum absolute world-axis deviation of an aligned guide.
    pub const GUIDE_ALIGNMENT_TOLERANCE: f64 = 1e-8;
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
    /// Maximum degree admitted to bounded contact root discovery.
    pub const MAX_POLYNOMIAL_DEGREE: usize = 18;
    /// Max root depth (booleans topology algebraic roots).
    pub const MAX_ROOT_DEPTH: usize = 96;
    /// Max coefficient bits (booleans topology algebraic roots).
    pub const MAX_COEFFICIENT_BITS: u64 = 4096;
}

/// Limits for `src/booleans.rs`.
pub mod booleans {
    /// Work charge per incident neighbor when certifying junction ray order.
    pub const JUNCTION_NEIGHBOR_WORK: usize = 8;
    /// Work charge for canonicalizing one source cubic.
    pub const CANONICAL_CUBIC_WORK: usize = 128;
    /// Maximum requested curve-flattening deviation in root document units.
    pub const MAX_CURVE_TOLERANCE: u32 = 64;
    /// Default requested curve-flattening deviation; topology certification remains mandatory.
    pub const DEFAULT_CURVE_TOLERANCE: f64 = 0.125;
    /// Maximum geometric subdivision depth shared by topology refinement and exact contact synchronization.
    pub const MAX_TOPOLOGY_DEPTH: usize = 20;
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
    /// Per-pixel base work for color adjustments, including gradient maps and selective corrections.
    pub const BASE_WORK: u64 = 16;
    /// Additional per-pixel work for each selective color correction.
    pub const SELECTIVE_CORRECTION_WORK: u64 = 4;
    /// Per-pixel work charge for a three-dimensional color lookup.
    pub const LUT_3D_WORK: u64 = 32;
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

/// Numerical policy for `blending`.
pub mod blending {
    /// Shared relative comparison tie allowance for display and native ink blends.
    pub const COMPARISON_TIE_EPSILONS: u32 = 8;
}

/// Numerical policy for `render_coverage_path`.
pub mod render_coverage_path {
    /// Number of tangent-matched cubic arcs used for output-space ellipse coverage.
    pub const ELLIPSE_ARCS: u32 = 32;
}

/// Numerical policy for `work_paths_coverage`.
pub mod work_paths_coverage {
    /// Crossing work charge includes every bisection step and the final cubic evaluation.
    pub const CUBIC_CROSSING_WORK: u64 = MAX_ROOT_STEPS as u64 + 1;
    /// Maximum bisection steps for one monotone cubic scanline crossing.
    pub const MAX_ROOT_STEPS: usize = 56;
}

/// Exact geometry work policies for `booleans_topology`.
pub mod booleans_topology {
    /// Work charge for projecting two cubic control hulls onto one separating axis.
    pub const SEPARATING_AXIS_WORK: usize = 8;
    /// Work charge per candidate direction in paired-coordinate certification.
    pub const PAIRED_COORDINATE_WORK: usize = 24;
    /// Work charge per direction for a point outside a cubic control hull.
    pub const OUTSIDE_HULL_WORK: usize = 5;
    /// Work charge for the derivative cross products in a transverse certificate.
    pub const TRANSVERSE_WORK: usize = 9;
    /// Work charge per curved arc when checking chord error and monotonicity.
    pub const REFINEMENT_ARC_WORK: usize = 24;
}

/// Exact geometry work policies for `booleans_topology_algebraic`.
pub mod booleans_topology_algebraic {
    /// Setup work charge for bounded rational contact roots.
    pub const RATIONAL_ROOTS_WORK: usize = 32;
    /// Work charge per direction when matching quadratic coordinates.
    pub const QUADRATIC_DIRECTION_WORK: usize = 32;
    /// Setup work charge per curved arc for algebraic contact preparation.
    pub const CONTACT_ARC_WORK: usize = 32;
    /// Work charge per rational arc pair during contact preparation and synchronization.
    pub const ARC_PAIR_WORK: usize = 8;
    /// Work charge for synchronizing endpoints along a shared linear coordinate.
    pub const LINEAR_SYNC_WORK: usize = 64;
    /// Work charge for synchronizing endpoints along a shared quadratic coordinate.
    pub const QUADRATIC_SYNC_WORK: usize = 64;
}

/// Exact geometry work policies for `booleans_quadratic_contacts`.
pub mod booleans_quadratic_contacts {
    /// Work charge per coefficient for monic normalization in a quadratic field.
    pub const MONIC_COEFFICIENT_WORK: usize = 16;
    /// Work charge per divisor coefficient during quadratic polynomial remainder reduction.
    pub const REMAINDER_COEFFICIENT_WORK: usize = 32;
    /// Work charge per candidate quadratic tangency root.
    pub const TANGENCY_ROOT_WORK: usize = 256;
}

/// Exact geometry work policies for `booleans_quadratic_predicates`.
pub mod booleans_quadratic_predicates {
    /// Work charge per separating axis for quadratic-field control hulls.
    pub const SEPARATING_AXIS_WORK: usize = 32;
    /// Work charge per paired-coordinate direction across quadratic fields.
    pub const PAIRED_COORDINATE_WORK: usize = 48;
    /// Work charge per direction for a rational point outside a quadratic hull.
    pub const OUTSIDE_HULL_WORK: usize = 24;
    /// Work charge for transverse derivative signs across quadratic fields.
    pub const TRANSVERSE_WORK: usize = 72;
    /// Setup work charge for a pair of algebraic arc views.
    pub const PAIR_SETUP_WORK: usize = 64;
}

/// Limits for `src/control.rs`.
pub mod control {
    /// Pixels between cooperative cancellation checks in raster and ink evaluation loops.
    pub const PIXEL_CHECK_INTERVAL: usize = 4096;
    /// Items or scheduled frames between cooperative cancellation checks.
    pub const ITEM_CHECK_INTERVAL: usize = 32;
    /// Maximum distinct cancellation markers inherited by a scoped request.
    pub const MAX_CANCEL_FILES: usize = 4;
    /// Max timeout ms (control).
    pub const MAX_TIMEOUT_MS: u64 = 60_000;
}

/// Limits for `src/dimensions.rs`.
pub mod dimensions {
    /// Even positive truncation count for bounded Machin arctangent intervals; remainder uses the next term.
    pub const PI_ATAN_TERMS: u32 = 32;
    /// Certified subdivision steps between cancellation checks.
    pub const MEASUREMENT_CHECK_INTERVAL: usize = 32;
    /// Maximum absolute measurement/resize projection angle in degrees.
    pub const MAX_ANGLE_DEGREES: u32 = 360_000;
    /// Minimum caller-selected certified boundary-length tolerance.
    pub const MIN_LENGTH_TOLERANCE: f64 = 0.000001;
    /// Maximum caller-selected certified boundary-length tolerance.
    pub const MAX_LENGTH_TOLERANCE: u32 = 100;
    /// Default certified boundary-length tolerance.
    pub const DEFAULT_LENGTH_TOLERANCE: f64 = 0.0001;
    /// Minimum caller-selected signed-area tolerance.
    pub const MIN_AREA_TOLERANCE: f64 = 0.000000001;
    /// Maximum caller-selected signed-area tolerance.
    pub const MAX_AREA_TOLERANCE: u32 = 10_000;
    /// Default signed-area tolerance.
    pub const DEFAULT_AREA_TOLERANCE: f64 = 0.000001;
    /// Minimum requested nondegenerate dimension after physical-unit conversion.
    pub const MIN_LOGICAL_DIMENSION: f64 = 0.001;
    /// Largest possible span between the negative and positive geometry bounds.
    pub const MAX_LOGICAL_DIMENSION: f64 = 2.0 * super::model::MAX_COORDINATE;
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
    /// Per-pixel shadow work for one exact integer tap with borrowed alpha.
    pub const DIRECT_SHADOW_WORK: u64 = 16;
    /// Per-pixel shadow work beyond the two-pass Gaussian kernel.
    pub const SOFT_SHADOW_OVERHEAD: u64 = 24;
    /// Per-pixel stroke-effect work beyond its neighborhood samples.
    pub const STROKE_OVERHEAD: u64 = 16;
    /// Per-pixel overlay-effect work.
    pub const OVERLAY_WORK: u64 = 12;
    /// Additional per-pixel preparation work for nonsolid effect paints.
    pub const PAINT_SETUP_WORK: u64 = 8;
    /// Minimum retained layer-effect kernel scale.
    pub const MIN_SCALE: f64 = 0.001;
    /// Maximum retained layer-effect kernel scale; effective kernel bounds also apply.
    pub const MAX_SCALE: u32 = 1024;
    /// Maximum shadow sigma, applied independently before and after effect scaling.
    pub const MAX_SHADOW_SIGMA: u32 = 16;
    /// Maximum shadow offset component or lit-shadow distance, before and after scaling.
    pub const MAX_SHADOW_OFFSET: u32 = 256;
    /// Maximum disk-stroke radius, before and after effect scaling.
    pub const MAX_STROKE_RADIUS: u32 = 32;
    /// Maximum absolute global or local lighting azimuth in degrees.
    pub const MAX_LIGHT_AZIMUTH: u32 = 360;
    /// Default document lighting azimuth in degrees.
    pub const DEFAULT_LIGHT_AZIMUTH: u32 = 225;
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
    /// Per-pixel filter composition overhead before any direct-replacement credit.
    pub const BASE_WORK: u64 = 8;
    /// Per-pixel work saved when a filter directly replaces its input.
    pub const DIRECT_REPLACEMENT_CREDIT: u64 = 4;
    /// Additional per-pixel charge for filter-mask sampling.
    pub const MASK_SAMPLE_WORK: u64 = 4;
    /// Work charge per bilinear directional or radial trajectory sample.
    pub const TRAJECTORY_SAMPLE_WORK: u64 = 4;
    /// Work charge per surface-filter neighborhood sample.
    pub const SURFACE_NEIGHBOR_WORK: u64 = 8;
    /// Maximum document-space box-kernel radius.
    pub const MAX_BOX_RADIUS: u32 = 32;
    /// Maximum sigma for the shared Gaussian blur, unsharp and high-pass kernel.
    pub const MAX_GAUSSIAN_SIGMA: u32 = 16;
    /// Maximum document-space directional trajectory length.
    pub const MAX_DIRECTIONAL_LENGTH: u32 = 64;
    /// Maximum absolute freely rotating directional or creative angle in degrees.
    pub const MAX_ANGLE_DEGREES: u32 = 360_000;
    /// Maximum absolute radial trajectory angle in degrees.
    pub const MAX_RADIAL_ANGLE: u32 = 180;
    /// Minimum trajectory samples, with a separate odd-count requirement.
    pub const MIN_TRAJECTORY_SAMPLES: u32 = 3;
    /// Maximum trajectory samples, with a separate odd-count requirement.
    pub const MAX_TRAJECTORY_SAMPLES: u32 = 129;
    /// Default directional and radial trajectory sample count.
    pub const DEFAULT_TRAJECTORY_SAMPLES: u32 = 33;
    /// Maximum document-space surface-filter radius.
    pub const MAX_SURFACE_RADIUS: u32 = 16;
    /// Max stack (filters).
    pub const MAX_STACK: usize = 8;
    /// Max document filters (filters).
    pub const MAX_DOCUMENT_FILTERS: usize = 64;
    /// Max work (filters).
    pub const MAX_WORK: u64 = 67_108_864;
}

/// Admission limits for detail-filter kernels.
pub mod detail_filters {
    /// Per-pixel work for the fixed sharpen stencil.
    pub const SHARPEN_WORK: u64 = 16;
    /// Per-pixel unsharp combination work beyond Gaussian evaluation.
    pub const UNSHARP_COMBINE_WORK: u64 = 8;
    /// Work charge per median neighborhood sample.
    pub const MEDIAN_NEIGHBOR_WORK: u64 = 8;
    /// Per-pixel work charge for deterministic noise generation.
    pub const NOISE_WORK: u64 = 64;
    /// Maximum strength for the shared sharpen and unsharp calculation.
    pub const MAX_SHARPEN_AMOUNT: u32 = 8;
    /// Maximum square median-neighborhood radius.
    pub const MAX_MEDIAN_RADIUS: u32 = 8;
}

/// Admission limits for creative-filter kernels.
pub mod creative_filters {
    /// Per-pixel twist evaluation and reconstruction work.
    pub const TWIST_WORK: u64 = 48;
    /// Per-pixel relief evaluation work.
    pub const RELIEF_WORK: u64 = 32;
    /// Per-pixel high-pass combination work beyond Gaussian evaluation.
    pub const HIGH_PASS_COMBINE_WORK: u64 = 8;
    /// Work charge per extrema neighborhood sample.
    pub const EXTREMA_NEIGHBOR_WORK: u64 = 8;
    /// Per-pixel tone-fold work.
    pub const TONE_FOLD_WORK: u64 = 4;
    /// Per-pixel edge-ink work.
    pub const EDGE_INK_WORK: u64 = 96;
    /// Work charge per line-neighborhood sample in stroke-rank evaluation.
    pub const STROKE_RANK_SAMPLE_WORK: u64 = 32;
    /// Per-pixel work charge per procedural value-field octave.
    pub const VALUE_FIELD_OCTAVE_WORK: u64 = 256;
    /// Per-pixel field-repair work.
    pub const FIELD_REPAIR_WORK: u64 = 8;
    /// Minimum nondegenerate local twist radius.
    pub const MIN_TWIST_RADIUS: f64 = 0.0001;
    /// Maximum opposing relief sample displacement in document units.
    pub const MAX_RELIEF_DISTANCE: u32 = 32;
    /// Maximum relief contrast strength.
    pub const MAX_RELIEF_STRENGTH: u32 = 8;
    /// Maximum square extrema-neighborhood radius.
    pub const MAX_EXTREMA_RADIUS: u32 = 8;
    /// Maximum line-neighborhood radius for stroke-rank sampling.
    pub const MAX_STROKE_RADIUS: u32 = 8;
    /// Maximum edge-ink strength, independent of relief contrast.
    pub const MAX_EDGE_STRENGTH: u32 = 8;
    /// Maximum item-local value-field cell size.
    pub const MAX_CELL_SIZE: u32 = 4096;
    /// Maximum value-field octave count.
    pub const MAX_OCTAVES: u32 = 4;
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
    /// Maximum fallback entries after reserving one primary font binding.
    pub const MAX_FALLBACK_FONTS: usize = MAX_FONTS - 1;
    /// Max license bytes (fonts).
    pub const MAX_LICENSE_BYTES: u64 = 65536;
    /// Max axes (fonts).
    pub const MAX_AXES: usize = 16;
    /// Max features (fonts).
    pub const MAX_FEATURES: usize = 64;
}

/// Limits for primitive admission and legacy binary64 bounds in `src/geometry.rs`.
pub mod geometry {
    /// Minimum rectangle width and height in local units.
    pub const MIN_RECTANGLE_EXTENT: f64 = 0.001;
    /// Minimum ellipse radius, independent of rectangle admission.
    pub const MIN_ELLIPSE_RADIUS: f64 = 0.001;
    /// Absolute derivative coefficient threshold for the existing cubic-bounds linear branch.
    pub const CUBIC_LINEAR_THRESHOLD: f64 = 1e-12;
}

/// Limits for `src/geometry/affine.rs`.
pub mod geometry_affine {
    /// Coordinate domain for the certified coefficient-error bound; twice the control limit.
    pub const MAX_POINT_COORDINATE: f64 = 2.0 * super::model::MAX_COORDINATE;
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
    /// Sum-of-magnitudes fast-path bound proved against point roundoff; changing it requires a new forward-error proof.
    pub const FAST_TERM_BOUND: f64 = 1_048_576.0;
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
    /// Absolute exposure bound for both HDR grading and display views.
    pub const MAX_EXPOSURE_STOPS: u32 = 32;
    /// Maximum nonnegative linear HDR channel multiplier.
    pub const MAX_CHANNEL_GAIN: u32 = 16;
    /// Maximum requested in-canvas positions per sample measurement.
    pub const MAX_SAMPLES: usize = 256;
}

/// Limits for `src/hyphenation.rs`.
pub mod hyphenation {
    /// Maximum caller-selected minimum grapheme count on either side of a break.
    pub const MAX_MINIMUM_GRAPHEMES: usize = 128;
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

/// JPEG codec admission and defaults in `src/image_io.rs`.
pub mod image_io {
    /// Minimum admitted JPEG encoder quality.
    pub const MIN_JPEG_QUALITY: u8 = 1;
    /// Maximum admitted JPEG encoder quality.
    pub const MAX_JPEG_QUALITY: u8 = 100;
    /// JPEG quality when the caller omits the option.
    pub const DEFAULT_JPEG_QUALITY: u8 = 90;
}

/// Fixed-width GIF output bounds in `src/image_io/gif.rs`.
pub mod image_io_gif {
    /// Literal-only encoder run before a dictionary reset; must stay in 1..=254 for fixed nine-bit codes.
    pub const LITERAL_RUN: usize = 128;
    /// Decoder codes or delivery pixels between cancellation checks; independent of the fixed LZW dictionary size.
    pub const CONTROL_INTERVAL: usize = 4096;
    /// Palette cardinality including any reserved transparent entry.
    pub const MAX_PALETTE_ENTRIES: usize = 256;
    /// Largest positive play count encoded as repetitions after the first play.
    pub const MAX_PLAYS: u32 = 65536;
    /// Largest delay representable in the centisecond timing field.
    pub const MAX_DELAY_TICKS: u32 = 65535;
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
    /// Maximum delay between owned-process completion probes.
    pub const PROCESS_POLL_INTERVAL_MS: u64 = 5;
    /// Maximum duration of one process wait slice.
    pub const MAX_WAIT_SLICE_MS: u64 = 1000;
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
    /// Maximum encoded scope or member inventory bytes used to bind a listing cursor.
    pub const MAX_FINGERPRINT_BYTES: usize = 32768;
    /// Additional JSON envelope reserve before admitting each job listing row.
    pub const RECORD_ENVELOPE_RESERVE: usize = 32;
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
    /// Maximum temporary-name reservation attempts for a new job database.
    pub const MAX_STAGE_ATTEMPTS: usize = 64;
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
    /// Polling interval for synchronous saved-job waits.
    pub const STATE_POLL_INTERVAL_MS: u64 = 50;
    /// Worker process/progress/cancellation polling interval.
    pub const MONITOR_INTERVAL_MS: u64 = 100;
    /// Delay between queue launch-lease attempts.
    pub const LAUNCH_RETRY_INTERVAL_MS: u64 = 10;
    /// Maximum wait for the queue launch lease, independent of cancellation grace.
    pub const LAUNCH_LOCK_TIMEOUT_MS: u64 = 2000;
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
    /// Imported RGB layer channels, including optional transparency and one authored scalar mask.
    pub const MAX_IMPORT_LAYER_CHANNELS: usize = 3 + 1 + 1;
    /// Maximum retained placement corner residual for admitted affine source geometry.
    pub const AFFINE_CLOSURE_TOLERANCE: f64 = 1e-9;
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
    /// Additional roundoff allowance in the SVG mesh reconstruction error bound.
    pub const SVG_ERROR_MARGIN: f64 = 1e-10;
    /// Contraction-scaled termination target for mesh inverse iteration.
    pub const INVERSE_TOLERANCE: f64 = 1e-13;
    /// Inward machine-epsilon margin for bounded color controls.
    pub const CONTROL_INSET_EPSILONS: u32 = 16;
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
    /// Minimum placed-image width or height in document units.
    pub const MIN_PLACED_IMAGE_EXTENT: f64 = 0.001;
    /// Minimum document resolution in pixels per inch, shared by every authoring route.
    pub const MIN_RESOLUTION_PPI: u32 = 1;
    /// Maximum document resolution in pixels per inch.
    pub const MAX_RESOLUTION_PPI: u32 = 9600;
    /// Default resolution for current documents; legacy snapshot rules stay versioned.
    pub const DEFAULT_RESOLUTION_PPI: u32 = 96;
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
    /// Minimum retained-object placement width or height in document units.
    pub const MIN_EXTENT: f64 = 0.001;
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
    /// Per-pixel mesh-paint work when no inverse deformation is required.
    pub const REGULAR_MESH_WORK: u64 = 16;
    /// Minimum separation of linear-gradient endpoints.
    pub const MIN_LINEAR_SPAN: f64 = 0.001;
    /// Minimum radial-gradient radius.
    pub const MIN_RADIAL_RADIUS: f64 = 0.001;
    /// Minimum pairwise freeform-gradient anchor separation.
    pub const MIN_ANCHOR_SEPARATION: f64 = 0.001;
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
    /// Per-leaf accumulation/subdivision allowance in measured baseline bounds.
    pub const ROUNDING_EPSILONS: u32 = 256;
    /// Minimum certified lower bound on text baseline length.
    pub const MIN_BASELINE_LENGTH: f64 = 0.001;
    /// Minimum caller-selected distance-table tolerance shared by text paths and interpolation spines.
    pub const MIN_TOLERANCE: f64 = 0.000001;
    /// Maximum caller-selected distance-table tolerance shared by text paths and interpolation spines.
    pub const MAX_TOLERANCE: f64 = 0.25;
    /// Default distance-table tolerance for text paths and interpolation spines.
    pub const DEFAULT_TOLERANCE: f64 = 0.001;
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
    /// Existing page-coordinate span used to select a per-page UserUnit.
    pub const MAX_PAGE_COORDINATE: f64 = 14400.0;
    /// Existing upper bound on the per-page UserUnit multiplier.
    pub const MAX_USER_UNIT: u32 = 75000;
    /// Max commands (pdf).
    pub const MAX_COMMANDS: usize = 262_144;
    /// Max objects (pdf).
    pub const MAX_OBJECTS: usize = 32_768;
    /// Max image pixels (pdf).
    pub const MAX_IMAGE_PIXELS: u64 = 4_194_304;
}

/// Existing print-mark admission and omitted-option defaults.
pub mod pdf_marks {
    /// Min gap in physical points.
    pub const MIN_GAP: f64 = 0.1;
    /// Max gap in physical points.
    pub const MAX_GAP: f64 = 72.0;
    /// Default gap in physical points.
    pub const DEFAULT_GAP: f64 = 3.0;
    /// Min length in physical points.
    pub const MIN_LENGTH: f64 = 1.0;
    /// Max length in physical points.
    pub const MAX_LENGTH: f64 = 144.0;
    /// Default length in physical points.
    pub const DEFAULT_LENGTH: f64 = 6.0;
    /// Min line width in physical points.
    pub const MIN_LINE_WIDTH: f64 = 0.05;
    /// Max line width in physical points.
    pub const MAX_LINE_WIDTH: f64 = 4.0;
    /// Default line width in physical points.
    pub const DEFAULT_LINE_WIDTH: f64 = 0.25;
    /// Min registration radius in physical points.
    pub const MIN_REGISTRATION_RADIUS: f64 = 0.5;
    /// Max registration radius in physical points.
    pub const MAX_REGISTRATION_RADIUS: f64 = 36.0;
    /// Default registration radius in physical points.
    pub const DEFAULT_REGISTRATION_RADIUS: f64 = 3.0;
}

/// Limits for `src/pixel_brush.rs`.
pub mod pixel_brush {
    /// Relative roundoff allowance for a duplicate terminal dab.
    pub const ENDPOINT_EPSILONS: u32 = 16;
    /// Accumulated brush work units between cancellation checks.
    pub const WORK_CHECK_INTERVAL: u64 = 1024;
    /// Brush placements between cancellation checks.
    pub const DAB_CHECK_INTERVAL: usize = 64;
    /// Minimum unscaled brush diameter in native pixels.
    pub const MIN_DIAMETER: f64 = 0.25;
    /// Minimum distance between regular dabs as a fraction of base diameter.
    pub const MIN_SPACING: f64 = 0.01;
    /// Maximum distance between regular dabs as a multiple of base diameter.
    pub const MAX_SPACING: u32 = 4;
    /// Default distance between regular dabs as a fraction of base diameter.
    pub const DEFAULT_SPACING: f64 = 0.25;
    /// Maximum scatter displacement as a multiple of tip radius.
    pub const MAX_SCATTER: u32 = 4;
    /// Minimum texture scale on each native-grid axis.
    pub const MIN_TEXTURE_SCALE: f64 = 0.001;
    /// Maximum texture scale on each native-grid axis.
    pub const MAX_TEXTURE_SCALE: u32 = 1024;
    /// Absolute coverage integration tolerance allocated across squared-radius spans.
    pub const COVERAGE_TOLERANCE: f64 = 0.0000001;
    /// Maximum recursive bisections per adaptive coverage integral.
    pub const MAX_COVERAGE_DEPTH: u32 = 20;
    /// Conservative live preparation/output bytes charged per working-window pixel.
    pub const WORKING_BYTES_PER_PIXEL: u64 = 256;
    /// Fixed preparation allowance in addition to window, cache and replacement bytes.
    pub const FIXED_WORKING_BYTES: u64 = 8 * 1024 * 1024;
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
    /// Maximum absolute authored articulated-joint rotation in degrees.
    pub const MAX_JOINT_ANGLE_DEGREES: u32 = 360;
    /// Conservative live scalar allowance per deformation-grid vertex, including vector growth.
    pub const VERTEX_BUFFER_VALUES: usize = 32;
    /// Conservative live scalar allowance per deformation-grid cell.
    pub const CELL_BUFFER_VALUES: usize = 16;
    /// Conservative live scalar allowance per articulated joint.
    pub const JOINT_BUFFER_VALUES: usize = 16;
    /// Fixed live scalar allowance for projective coefficients and plan construction.
    pub const FIXED_BUFFER_VALUES: usize = 128;
    /// Maximum absolute departure of articulated weights from unity.
    pub const WEIGHT_SUM_TOLERANCE: f64 = 1e-10;
    /// Filtered orientation uncertainty before exact rational fallback.
    pub const ORIENTATION_EPSILONS: u32 = 16;
    /// Minimum warp-frame width or height before deformation.
    pub const MIN_FRAME_EXTENT: f64 = 0.001;
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
    /// Per-pixel profile-conversion overhead for native adjustments.
    pub const ADJUSTMENT_CONVERSION_WORK: u64 = 256;
    /// Per-source-pixel work for a declared display projection before native composition.
    pub const PROJECTED_SOURCE_WORK: u64 = 16;
    /// Per-channel native object placement work beyond the reconstruction kernel.
    pub const OBJECT_RECONSTRUCTION_WORK: u64 = 16;
    /// Per-pixel native image work in addition to the destination ink channels.
    pub const IMAGE_PIXEL_OVERHEAD: u64 = 16;
    /// Per-channel work for native blend and effect composition.
    pub const BLEND_CHANNEL_WORK: usize = 8;
    /// Per-pixel overhead for native blend and effect composition.
    pub const BLEND_PIXEL_OVERHEAD: usize = 32;
    /// Per-channel work for normal native composition.
    pub const NORMAL_CHANNEL_WORK: usize = 2;
    /// Per-pixel overhead for normal native composition.
    pub const NORMAL_PIXEL_OVERHEAD: usize = 1;
    /// Additional per-channel work when native shape coverage is tracked.
    pub const SHAPE_CHANNEL_WORK: usize = 4;
    /// Additional per-pixel work when native shape coverage is tracked.
    pub const SHAPE_PIXEL_OVERHEAD: usize = 8;
    /// Per-pixel native dissolve work for one coverage field.
    pub const DISSOLVE_WORK: u64 = 128;
    /// Native dissolve charges both color and shape coverage fields when shape is tracked.
    pub const SHAPE_DISSOLVE_WORK: u64 = 2 * DISSOLVE_WORK;
    /// Per-pixel native filter composition overhead beyond per-channel blend work.
    pub const FILTER_PIXEL_OVERHEAD: u64 = 40;
    /// Conservative live scalar allowance for color conversion scratch arrays; follows the shared batch size.
    pub const COLOR_BUFFER_VALUES: u64 = super::profiles::MAX_CONVERSION_SAMPLES as u64 * 16;
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
    /// Minimum parametric radius or rounded-rectangle dimension.
    pub const MIN_EXTENT: f64 = 0.001;
    /// Maximum absolute saved rotation for regular polygons and stars.
    pub const MAX_ROTATION_DEGREES: u32 = 360000;
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
    /// Gamut samples between cancellation checks.
    pub const SAMPLE_CHECK_INTERVAL: usize = 256;
    /// Max samples (profiles gamut).
    pub const MAX_SAMPLES: usize = 4096;
}

/// Limits for `src/profiles.rs`.
pub mod profiles {
    /// Minimum absolute destination-profile matrix determinant, independent of raw-camera admission.
    pub const MIN_MATRIX_DETERMINANT: f64 = 1e-12;
    /// Maximum input/output entries in admitted LUT8/LUT16 curve tables; independent of standalone tone curves.
    pub const MAX_LUT_CURVE_ENTRIES: usize = 4096;
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
    /// Maximum caller-selected color-loss classification threshold.
    pub const MAX_DELTA_E76_THRESHOLD: u32 = 1000;
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
    /// Maximum temporary-name attempts for staged output and history receipt publication.
    pub const MAX_STAGE_ATTEMPTS: usize = 64;
    /// Max receipt bytes (publications).
    pub const MAX_RECEIPT_BYTES: usize = 1024 * 1024;
    /// Max ledger bytes (publications).
    pub const MAX_LEDGER_BYTES: usize = 64 * 1024 * 1024;
    /// Max records (publications).
    pub const MAX_RECORDS: usize = 1024;
}

/// Limits for `src/publish.rs`.
pub mod publish {
    /// Maximum temporary-file reservation attempts for direct output publication.
    pub const MAX_STAGE_ATTEMPTS: usize = 64;
    /// Maximum bytes per checked staging write or receipt-verification read; cancellation is checked between chunks.
    pub const IO_CHUNK_BYTES: usize = 65536;
    /// Max output bytes (publish).
    pub const MAX_OUTPUT_BYTES: usize = 32 * 1024 * 1024;
}

/// Limits for `src/raw/corrections.rs`.
pub mod raw_corrections {
    /// Maximum denoise/detail neighborhood radius in sensor pixels.
    pub const MAX_RADIUS: u32 = 4;
    /// Maximum linear-light range/detail threshold.
    pub const MAX_THRESHOLD: u32 = 16;
    /// Maximum detail enhancement multiplier; denoise amount stays normalized.
    pub const MAX_DETAIL_AMOUNT: u32 = 4;
    /// Minimum calibrated focal length in sensor pixels.
    pub const MIN_FOCAL_LENGTH: u32 = 1;
    /// Maximum calibrated focal length, independent of sensor dimensions.
    pub const MAX_FOCAL_LENGTH: u32 = 32768;
    /// Absolute admitted radial lens coefficient.
    pub const MAX_RADIAL_COEFFICIENT: f64 = 1.0;
    /// Absolute admitted tangential lens coefficient.
    pub const MAX_TANGENTIAL_COEFFICIENT: f64 = 0.25;
    /// Exclusive global Jacobian-perturbation admission bound for no-fold certification.
    pub const MAX_JACOBIAN_PERTURBATION: f64 = 0.95;
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
    /// Absolute camera-to-linear-RGB matrix coefficient bound.
    pub const MAX_CAMERA_COEFFICIENT: u32 = 16;
    /// Smallest admitted absolute camera calibration determinant.
    pub const MIN_CAMERA_DETERMINANT: f64 = 1e-12;
    /// Absolute sensor-development exposure bound, independent of HDR grading.
    pub const MAX_EXPOSURE_STOPS: u32 = 32;
    /// Maximum positive input white-balance component before neutral normalization.
    pub const MAX_WHITE_BALANCE_COMPONENT: u32 = 64;
    /// Maximum effective gain; its reciprocal is the minimum effective gain.
    pub const MAX_WHITE_BALANCE_GAIN: u32 = 64;
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
    /// Dependency-region mapping work per radial trajectory sample.
    pub const RADIAL_SAMPLE_WORK: u64 = 32;
    /// Dependency-region mapping work for a twist step.
    pub const TWIST_WORK: u64 = 128;
    /// Relative accumulation allowance in filter dependency bounds.
    pub const ROUNDING_EPSILONS: u32 = 64;
    /// Absolute floor on conservative filter dependency coordinate margins.
    pub const ABSOLUTE_MARGIN: f64 = 1e-9;
    /// Max references (render filter regions).
    pub const MAX_REFERENCES: usize = 131_072;
}

/// Limits for `src/render/spatial.rs`.
pub mod render_spatial {
    /// Conservative eight-byte scalar allowance per spatial-index reference.
    pub const REFERENCE_VALUES: u64 = 8;
    /// Conservative eight-byte scalar allowance per spatial-index cell.
    pub const CELL_VALUES: u64 = 4;
    /// Conservative eight-byte scalar allowance per spatial-index item.
    pub const ITEM_VALUES: u64 = 24;
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
    /// Per-pixel item setup shared by sparse, indexed and tiled composition.
    pub const ITEM_SETUP_WORK: u64 = 2;
    /// Per-output-pixel item-mask sampling work shared by render planners.
    pub const MASK_SAMPLE_WORK: u64 = 4;
    /// Per-pixel item work for color and shape knockout composition across planners.
    pub const KNOCKOUT_ITEM_WORK: u64 = 24;
    /// Max render pixels (render).
    pub const MAX_RENDER_PIXELS: u64 = 1_048_576;
    /// Max render work (render).
    pub const MAX_RENDER_WORK: u64 = 67_108_864;
    /// Max buffer pixels (render).
    pub const MAX_BUFFER_PIXELS: u64 = 4_194_304;
}

/// Limits for `src/repair.rs`.
pub mod repair {
    /// Maximum exemplar-fill patch radius, independent of patch placement context.
    pub const MAX_FILL_PATCH_RADIUS: u32 = 4;
    /// Minimum confidence weight for newly synthesized context samples.
    pub const MIN_SYNTHESIZED_WEIGHT: f64 = 0.01;
    /// Default confidence weight for newly synthesized context samples.
    pub const DEFAULT_SYNTHESIZED_WEIGHT: f64 = 0.5;
    /// Maximum integer displacement searched around a requested patch origin.
    pub const MAX_SEARCH_RADIUS: u32 = 32;
    /// Maximum radius used to gather surrounding patch-placement context.
    pub const MAX_CONTEXT_RADIUS: u32 = 4;
    /// Maximum guided-correction neighborhood radius.
    pub const MAX_GUIDE_RADIUS: u32 = 16;
    /// Minimum normalized range sigma for guided-correction weights.
    pub const MIN_RANGE_SIGMA: f64 = 0.0001;
    /// Theoretical support ceiling: cardinality of the largest square guide window.
    pub const MAX_EFFECTIVE_SAMPLES: u32 = (2 * MAX_GUIDE_RADIUS + 1) * (2 * MAX_GUIDE_RADIUS + 1);
    /// Max work (repair).
    pub const MAX_WORK: u64 = 67_108_864;
    /// Max patches (repair).
    pub const MAX_PATCHES: usize = 4096;
}

/// Limits for `src/repeats.rs`.
pub mod repeats {
    /// Maximum absolute authored radial start angle and sweep; full-turn closure is a separate geometric rule.
    pub const MAX_RADIAL_ANGLE_DEGREES: u32 = 360;
    /// Minimum hexagonal/radial layout radius in repeat-local units.
    pub const MIN_RADIUS: f64 = 0.001;
    /// Minimum absolute grid/brick step on each axis in repeat-local units.
    pub const MIN_STEP: f64 = 0.001;
    /// Max copies (repeats).
    pub const MAX_COPIES: usize = 128;
}

/// Limits for `src/resample.rs`.
pub mod resample {
    /// Per-axis-tap reconstruction preparation work in addition to the two-dimensional sample product.
    pub const AXIS_TAP_WORK: u64 = 4;
    /// Absolute source coordinate supported by advanced-kernel stable index arithmetic.
    pub const MAX_INDEX_COORDINATE: f64 = 1e12;
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
    /// Source sample positions between cancellation checks.
    pub const SAMPLE_CHECK_INTERVAL: usize = 1024;
    /// Maximum screening strength of the boundary-constrained healing system.
    pub const MAX_SCREENING: u32 = 16;
    /// Minimum requested true residual tolerance for healing.
    pub const MIN_RESIDUAL_TOLERANCE: f64 = 1e-12;
    /// Maximum requested true residual tolerance for healing.
    pub const MAX_RESIDUAL_TOLERANCE: f64 = 1e-4;
    /// Default requested true residual tolerance for healing.
    pub const DEFAULT_RESIDUAL_TOLERANCE: f64 = 1e-9;
    /// Default per-channel healing iteration allowance.
    pub const DEFAULT_ITERATIONS: u32 = 2048;
    /// Conservative bytes charged separately per window and region pixel.
    pub const WORKING_BYTES_PER_PIXEL: u64 = 256;
    /// Fixed solver/preparation allowance in addition to windows and native resources.
    pub const FIXED_WORKING_BYTES: u64 = 8 * 1024 * 1024;
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
    /// Maximum create-only temporary-file reservation attempts for one native tile.
    pub const MAX_STAGE_ATTEMPTS: usize = 64;
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
    /// Delay between backup retries within the shared SQLite lock-wait budget.
    pub const BACKUP_RETRY_INTERVAL_MS: u64 = 5;
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
    /// Work charge per source point in simplification hull preparation.
    pub const HULL_POINT_WORK: usize = 8;
    /// Work charge per source cubic for a candidate replacement error certificate.
    pub const CERTIFICATE_CURVE_WORK: usize = 64;
    /// Work charge per source cubic for simplification monotonicity admission.
    pub const MONOTONICITY_CURVE_WORK: usize = 16;
    /// Max span (simplify).
    pub const MAX_SPAN: usize = 32;
    /// Max work (simplify).
    pub const MAX_WORK: usize = 400_000;
}

/// Limits for `src/spatial_filters.rs`.
pub mod spatial_filters {
    /// Per-pixel mosaic evaluation work.
    pub const MOSAIC_WORK: u64 = 4;
    /// Per-pixel offset reconstruction work.
    pub const OFFSET_WORK: u64 = 4;
    /// Per-pixel displacement-field evaluation and reconstruction work.
    pub const DISPLACE_WORK: u64 = 16;
    /// Maximum absolute document-space offset or displacement amplitude.
    pub const MAX_OFFSET: u32 = 256;
    /// Maximum mosaic block size in document units.
    pub const MAX_MOSAIC_SIZE: u32 = 128;
    /// Maximum dimension of a displacement field, independent of its total-vector budget.
    pub const MAX_MAP_AXIS: u32 = 256;
    /// Max map pixels (spatial filters).
    pub const MAX_MAP_PIXELS: usize = 4096;
}

/// Limits for explicit geometry snapping.
pub mod snapping {
    /// Minimum transformed guide-segment length in document units.
    pub const MIN_GUIDE_LENGTH: f64 = 1e-10;
    /// Pairs at or below this absolute normalized direction cross product are parallel.
    pub const PARALLEL_THRESHOLD: f64 = 1e-10;
    /// Minimum grid spacing in logical document pixels.
    pub const MIN_GRID_SPACING: f64 = 0.001;
    /// Maximum frozen reference targets in one snap operation.
    pub const MAX_TARGETS: usize = 64;
}

/// Limits for exact quadratic parameter separation.
pub mod booleans_topology_quadratic {
    /// Minimum certified quadratic-root enclosure precision, shared with contact receipts.
    pub const MIN_ROOT_ENCLOSURE_BITS: usize = 128;
    /// Additional quadratic-root enclosure bits per geometric subdivision level.
    pub const ROOT_BITS_PER_DEPTH: usize = 16;
    /// Additional root enclosure bits beyond the current dyadic parameter search.
    pub const ROOT_GUARD_BITS: usize = 32;
    /// Initial dyadic parameter precision before bounded refinement.
    pub const INITIAL_PARAMETER_BITS: usize = 4;
    /// Dyadic parameter precision growth factor, capped by MAX_PARAMETER_BITS.
    pub const PARAMETER_GROWTH_FACTOR: usize = 2;
    /// Work charge per attempted quadratic span split, in addition to parameter bytes.
    pub const SPLIT_SETUP_WORK: usize = 128;
    /// Work charge per rational cubic when locating quadratic node parameters.
    pub const NODE_ARC_WORK: usize = 128;
    /// Setup work charge per arc when finding preimages of a quadratic node.
    pub const NODE_PREIMAGE_WORK: usize = 8;
    /// Work charge per reconstructed span between quadratic contact cuts.
    pub const CONTACT_SPAN_WORK: usize = 128;
    /// Maximum numerator or denominator bits in one quadratic contact coefficient; independent of dyadic cut search.
    pub const MAX_COEFFICIENT_BITS: u64 = 4096;
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
    /// Conservative centerline distance and coordinate roundoff allowance.
    pub const ROUNDING_EPSILONS: u32 = 16;
    /// Minimum bisector magnitude before using the outgoing tangent.
    pub const MIN_BISECTOR_LENGTH: f64 = 1e-12;
    /// Minimum repeat spacing in base stroke widths.
    pub const MIN_SPACING: f64 = 0.001;
    /// Maximum repeat spacing in base stroke widths; independent of stroke width and arrow dimensions.
    pub const MAX_SPACING: u32 = 1024;
    /// Maximum endpoint/corner clearance in base stroke widths.
    pub const MAX_CLEARANCE: u32 = 1024;
    /// Maximum absolute expanded motif control coordinate in normalized motif units.
    pub const MAX_MOTIF_COORDINATE: u32 = 16;
    /// Minimum corner classification angle in degrees.
    pub const MIN_CORNER_ANGLE: f64 = 0.1;
    /// Maximum corner classification angle in degrees.
    pub const MAX_CORNER_ANGLE: u32 = 180;
    /// Default corner classification angle in degrees.
    pub const DEFAULT_CORNER_ANGLE: u32 = 30;
    /// Max placements (strokes brush).
    pub const MAX_PLACEMENTS: usize = 8192;
}

/// Limits for `src/strokes/outline.rs`.
pub mod strokes_outline {
    /// Coordinate/radius roundoff allowance when joining outline nodes.
    pub const ROUNDING_EPSILONS: u32 = 8;
    /// Maximum cubic subdivision depth while preparing stroke centerlines.
    pub const MAX_SUBDIVISION_DEPTH: usize = 24;
    /// Max outline commands (strokes outline).
    pub const MAX_OUTLINE_COMMANDS: usize = 65_536;
    /// Max points (strokes outline).
    pub const MAX_POINTS: usize = 16_384;
}

/// Limits for `src/strokes.rs`.
pub mod strokes {
    /// Minimum stored stroke width in the declared stroke space.
    pub const MIN_WIDTH: f64 = 0.001;
    /// Maximum stored or profile-expanded stroke width in the declared stroke space.
    pub const MAX_WIDTH: u32 = 1024;
    /// Minimum miter extension ratio.
    pub const MIN_MITER_LIMIT: u32 = 1;
    /// Maximum miter extension ratio.
    pub const MAX_MITER_LIMIT: u32 = 16;
    /// Default miter extension ratio shared by document authoring and brush compatibility.
    pub const DEFAULT_MITER_LIMIT: u32 = 4;
    /// Minimum caller-stored curve tolerance; internal placement refinement may be tighter.
    pub const MIN_CURVE_TOLERANCE: f64 = 0.0000001;
    /// Maximum caller-stored curve tolerance in the declared stroke space.
    pub const MAX_CURVE_TOLERANCE: u32 = 1;
    /// Default stored tolerance and numerator of placement-aware outline refinement.
    pub const DEFAULT_CURVE_TOLERANCE: f64 = 1.0 / 64.0;
    /// Maximum knots in one stored width profile.
    pub const MAX_PROFILE_KNOTS: usize = 64;
    /// Maximum width multiplier at a profile knot; resulting width has a separate bound.
    pub const MAX_PROFILE_FACTOR: u32 = 1024;
    /// Minimum arrow length or width in the declared stroke space.
    pub const MIN_ARROW_EXTENT: f64 = 0.001;
    /// Maximum arrow length or width; independent of shaft width and brush spacing.
    pub const MAX_ARROW_EXTENT: u32 = 1024;
    /// Minimum nonzero dash interval in the declared stroke space.
    pub const MIN_DASH_LENGTH: f64 = 0.001;
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

/// Bounds on derived SVG delivery geometry.
pub mod svg {
    /// Maximum absolute coordinate of a derived mesh-paint coverage rectangle.
    pub const MAX_MESH_COVERAGE_COORDINATE: f64 = 1e9;
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
    /// Maximum private import attempts for explicit unsupported-content omission.
    pub const MAX_OMISSION_ATTEMPTS: usize = 256;
    /// Sum of filtered source bytes across omission attempts (independent of XML/node limits).
    pub const MAX_OMISSION_SOURCE_BYTES: usize = 128 * 1024 * 1024;
    /// Embedded CSS rules across all style elements in one SVG source.
    pub const MAX_CSS_RULES: usize = 4096;
    /// Type, universal, class and ID components in one compound selector.
    pub const MAX_CSS_SELECTOR_COMPONENTS: usize = 64;
    /// CSS declarations across embedded rules and inline styles.
    pub const MAX_CSS_DECLARATIONS: usize = 65536;
    /// Selector component/name work and declaration applications per import.
    pub const MAX_CSS_MATCH_WORK: usize = 4 * 1024 * 1024;
    /// Maximum tangent-cubic radial error in source-element local units, excluding binary64 roundoff.
    pub const ARC_RADIAL_TOLERANCE: f64 = 0.001;
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
    /// Maximum UTF-8 bytes in a nonempty printable swatch label.
    pub const MAX_NAME_BYTES: usize = 256;
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
    /// Largest supported subtractive Roman numeral, without overbar notation.
    pub const MAX_ROMAN_COUNTER: u32 = 3999;
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
    /// Minimum ordinary frame and remaining flow-column extent in local pixels.
    pub const MIN_FRAME_EXTENT: f64 = 0.001;
    /// Minimum explicit or natural leading in local pixels.
    pub const MIN_LEADING: f64 = 0.001;
    /// Maximum explicit leading in local pixels.
    pub const MAX_LEADING: u32 = 4096;
    /// Smallest admitted font size in local pixels.
    pub const MIN_FONT_SIZE: f64 = 0.01;
    /// Largest admitted font size, independent of tracking.
    pub const MAX_FONT_SIZE: u32 = 1024;
    /// Absolute tracking bound in local pixels, independent of font size.
    pub const MAX_TRACKING: u32 = 1024;
    /// Minimum horizontal/vertical character scale.
    pub const MIN_CHARACTER_SCALE: f64 = 0.01;
    /// Maximum horizontal/vertical character scale.
    pub const MAX_CHARACTER_SCALE: f64 = 10.0;
    /// Maximum language-tag bytes; subtag syntax is checked separately.
    pub const MAX_LANGUAGE_BYTES: usize = 64;
    /// Layout fit/ink-overflow comparison tolerance, not a glyph-position accuracy guarantee.
    pub const LAYOUT_OVERFLOW_TOLERANCE: f64 = 1e-9;
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
    /// Classification or boundary traversal steps between cancellation checks.
    pub const CONTROL_INTERVAL: usize = 4096;
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
    /// Maximum absolute residual when admitting an integer-valued native field.
    pub const INTEGER_TOLERANCE: f64 = 1e-8;
    /// Parsed bytes or syntax nodes between cancellation checks.
    pub const PARSE_CHECK_INTERVAL: usize = 256;
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

/// Limits for logical vector viewport admission.
pub mod vector_canvas {
    /// Minimum positive logical canvas size per axis; storage uses its ceiling.
    pub const MIN_LOGICAL_SIZE: f64 = 0.000001;
}

/// Limits for `src/visual_diff.rs`.
pub mod visual_diff {
    /// Maximum absolute output-pixel grid phase residual; no resampling.
    pub const GRID_PHASE_TOLERANCE: f64 = 1e-9;
    /// Max pixels (visual diff).
    pub const MAX_PIXELS: u64 = super::render::MAX_RENDER_PIXELS;
}

/// Limits for `src/volumes.rs`.
pub mod volumes {
    /// Relative plane-partition roundoff allowance for projected volume faces.
    pub const PARTITION_EPSILONS: u32 = 2048;
    /// Default source chord tolerance; admissible bounds come from the shared warp evaluator.
    pub const DEFAULT_SOURCE_TOLERANCE: f64 = 0.1;
    /// Maximum retained extrusion depth in local units.
    pub const MAX_DEPTH: u32 = 4096;
    /// Maximum absolute rigid rotation angle in degrees.
    pub const MAX_ROTATION: u32 = 360000;
    /// Minimum norm accepted by direction and derived-normal normalization.
    pub const MIN_DIRECTION_NORM: f64 = 1e-8;
    /// Maximum norm accepted by direction and derived-normal normalization.
    pub const MAX_DIRECTION_NORM: u32 = 65536;
    /// Minimum perspective camera distance in local units.
    pub const MIN_CAMERA_DISTANCE: u32 = 1;
    /// Maximum perspective camera distance, independent of scene-coordinate limits.
    pub const MAX_CAMERA_DISTANCE: u32 = 32768;
    /// Minimum positive near-plane distance.
    pub const MIN_CAMERA_NEAR: f64 = 0.01;
    /// Maximum far-plane distance, independent of direction normalization.
    pub const MAX_CAMERA_FAR: u32 = 65536;
    /// Maximum distance/near-plane ratio accepted for perspective projection.
    pub const MAX_MAGNIFICATION: u32 = 128;
    /// Maximum directional lights in a diffuse material.
    pub const MAX_LIGHTS: usize = 8;
    /// Maximum nonnegative linear-light intensity per light.
    pub const MAX_LIGHT_INTENSITY: u32 = 8;
    /// Maximum recursive face-partition depth for volume ordering.
    pub const MAX_PARTITION_DEPTH: usize = 128;
    /// Max edges (volumes).
    pub const MAX_EDGES: usize = 128;
    /// Max faces (volumes).
    pub const MAX_FACES: usize = 192;
}

/// Limits for `src/warps.rs`.
pub mod warps {
    /// Work charge per homogeneous control when preparing a unit-domain warp.
    pub const UNIT_CONTROL_WORK: usize = 8;
    /// Work charge per control pair in homogeneous subdivision.
    pub const SPLIT_PAIR_WORK: usize = 3;
    /// Work charge per homogeneous control for the exact chord certificate.
    pub const CERTIFICATE_CONTROL_WORK: usize = 20;
    /// Charged exact-arithmetic work units between cancellation checks.
    pub const EXACT_WORK_CHECK_INTERVAL: usize = 1024;
    /// Minimum positive domain width/height for perspective, envelope and inspected grids.
    pub const MIN_DOMAIN_EXTENT: f64 = 0.001;
    /// Minimum requested certified chord deviation in warp-local units.
    pub const MIN_TOLERANCE: f64 = 0.000001;
    /// Maximum requested certified chord deviation in warp-local units.
    pub const MAX_TOLERANCE: u32 = 1;
    /// Default requested certified chord deviation in warp-local units.
    pub const DEFAULT_TOLERANCE: f64 = 0.01;
    /// Maximum projective corner weight; the minimum is its exact reciprocal.
    pub const MAX_PERSPECTIVE_WEIGHT: usize = 1024;
    /// Maximum intervals on each axis of an inspected deformation grid.
    pub const MAX_GRID_AXIS: usize = 16;
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
