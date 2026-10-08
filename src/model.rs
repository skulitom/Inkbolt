use crate::assets::{self, Crop, ImageAsset, Sampling};
pub use crate::paint::{Dither, Paint};
use crate::{Error, geometry, scene};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, HashSet};

pub const MAX_DIMENSION: u32 = 32768;
pub const MAX_ITEMS: usize = 256;
pub const MAX_SEGMENTS: usize = 4096;
pub const MAX_STORED_PIXELS: usize = 65536;
pub const MAX_DOCUMENT_BYTES: usize = 768 * 1024;
pub const MAX_LARGE_VECTOR_ITEMS: usize = 8192;
pub const MAX_LARGE_VECTOR_COMMANDS: usize = 131072;
pub const MAX_LARGE_VECTOR_BYTES: usize = 8 * 1024 * 1024;
pub const MAX_COORDINATE: f64 = 32768.0;
pub type Color = [u8; 4];
pub type Point = [f64; 2];
pub type Matrix = [f64; 6];
pub fn identity() -> Matrix {
    [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
}
fn yes() -> bool {
    true
}
fn one() -> f64 {
    1.0
}
fn is_one(value: &f64) -> bool {
    *value == 1.0
}
fn resolution() -> f64 {
    96.0
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum DocumentKind {
    Vector,
    Raster,
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ColorSpace {
    Srgb,
    LinearSrgb,
}

/// Persisted opt-in storage budgets. Algorithm-specific work limits are independent.
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ResourceProfile {
    #[default]
    Standard,
    LargeVector,
}
impl ResourceProfile {
    pub fn is_standard(&self) -> bool {
        *self == Self::Standard
    }
    pub fn items(self) -> usize {
        match self {
            Self::Standard => MAX_ITEMS,
            Self::LargeVector => MAX_LARGE_VECTOR_ITEMS,
        }
    }
    pub fn commands(self) -> usize {
        match self {
            Self::Standard => MAX_SEGMENTS,
            Self::LargeVector => MAX_LARGE_VECTOR_COMMANDS,
        }
    }
    pub fn bytes(self) -> usize {
        match self {
            Self::Standard => MAX_DOCUMENT_BYTES,
            Self::LargeVector => MAX_LARGE_VECTOR_BYTES,
        }
    }
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Document {
    #[serde(default, skip_serializing_if = "ResourceProfile::is_standard")]
    pub resource_profile: ResourceProfile,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub vector_canvas: Option<crate::vector_canvas::Canvas>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub ink_recipe: Option<crate::ink_recipes::Recipe>,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub stories: BTreeMap<String, crate::text::flow::Story>,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub swatches: BTreeMap<String, crate::swatches::Swatch>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub background: Option<crate::backgrounds::Background>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub metadata: Option<crate::metadata::Record>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub output_profile: Option<crate::profiles::Profile>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub variants: Option<crate::variants::State>,
    pub schema_version: u32,
    pub id: String,
    pub kind: DocumentKind,
    pub width: u32,
    pub height: u32,
    pub color_space: ColorSpace,
    #[serde(default)]
    pub revision: u64,
    #[serde(default = "resolution")]
    pub resolution_ppi: f64,
    #[serde(default, skip_serializing_if = "crate::effects::Lighting::is_default")]
    pub global_light: crate::effects::Lighting,
    #[serde(default)]
    pub items: Vec<Item>,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub assets: BTreeMap<String, ImageAsset>,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub fonts: BTreeMap<String, crate::fonts::Font>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub selection: Option<crate::selections::Selection>,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub channels: BTreeMap<String, crate::channels::Channel>,
}

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum BlendMode {
    #[default]
    Normal,
    Multiply,
    Screen,
    Darken,
    Lighten,
    ColorBurn,
    ColorDodge,
    Overlay,
    HardLight,
    SoftLight,
    Difference,
    Exclusion,
    Hue,
    Saturation,
    Color,
    Luminosity,
    LinearBurn,
    LinearDodge,
    VividLight,
    LinearLight,
    PinLight,
    HardMix,
    Subtract,
    Divide,
    DarkerColor,
    LighterColor,
}

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum FillRule {
    #[default]
    Nonzero,
    EvenOdd,
}

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Cap {
    #[default]
    Butt,
    Round,
    Square,
}

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Join {
    #[default]
    Miter,
    Round,
    Bevel,
}

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum GroupRole {
    #[default]
    Group,
    Layer,
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Clip {
    pub geometry: Geometry,
    #[serde(default)]
    pub fill_rule: FillRule,
    #[serde(default = "identity")]
    pub transform: Matrix,
    #[serde(default = "yes")]
    pub enabled: bool,
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Stroke {
    #[serde(default, skip_serializing_if = "crate::strokes::Scaling::is_object")]
    pub scaling: crate::strokes::Scaling,
    pub color: Paint,
    pub width: f64,
    #[serde(default)]
    pub cap: Cap,
    #[serde(default)]
    pub join: Join,
    #[serde(default = "miter")]
    pub miter_limit: f64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub dash: Option<crate::strokes::Dash>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub brush: Option<crate::strokes::Brush>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub width_profile: Vec<Point>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub start_arrow: Option<crate::strokes::Arrow>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub end_arrow: Option<crate::strokes::Arrow>,
    #[serde(
        default = "crate::strokes::default_tolerance",
        skip_serializing_if = "crate::strokes::is_default_tolerance"
    )]
    pub curve_tolerance: f64,
}
fn miter() -> f64 {
    4.0
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(tag = "verb", rename_all = "snake_case", deny_unknown_fields)]
pub enum PathCommand {
    Move {
        to: Point,
    },
    Line {
        to: Point,
    },
    Cubic {
        control1: Point,
        control2: Point,
        to: Point,
    },
    Close {},
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(tag = "shape", rename_all = "snake_case", deny_unknown_fields)]
pub enum Geometry {
    Compound {
        mode: crate::booleans::Mode,
        operands: Vec<crate::work_paths::Operand>,
    },
    RoundedRect {
        x: f64,
        y: f64,
        width: f64,
        height: f64,
        radii: [f64; 4],
    },
    Polygon {
        points: Vec<Point>,
    },
    RegularPolygon {
        cx: f64,
        cy: f64,
        radius: f64,
        sides: u32,
        #[serde(default)]
        rotation: f64,
    },
    Star {
        cx: f64,
        cy: f64,
        outer_radius: f64,
        inner_radius: f64,
        points: u32,
        #[serde(default)]
        rotation: f64,
    },
    Rect {
        x: f64,
        y: f64,
        width: f64,
        height: f64,
    },
    Ellipse {
        cx: f64,
        cy: f64,
        rx: f64,
        ry: f64,
    },
    Path {
        commands: Vec<PathCommand>,
    },
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Content {
    Raw {
        raw: Box<crate::raw::retained::Spec>,
    },
    Volume {
        volume: Box<crate::volumes::Spec>,
    },
    Appearance {
        appearance: Box<crate::appearance::Spec>,
    },
    StoryFrame {
        story_id: String,
        slot_id: String,
    },
    Object {
        object: Box<crate::objects::Object>,
    },
    Samples {
        grid: Box<crate::samples::Grid>,
    },
    Warp {
        warp: Box<crate::warps::Spec>,
    },
    Repeat {
        repeat: Box<crate::repeats::Spec>,
    },
    Interpolation {
        interpolation: Box<crate::interpolation::Spec>,
    },
    ComponentSource {},
    Instance {
        instance: Box<crate::instances::Instance>,
    },
    WorkPath {
        geometry: Geometry,
        #[serde(default)]
        fill_rule: FillRule,
    },
    Adjustment {
        adjustment: Box<crate::adjustments::Layer>,
    },
    Frame {
        frame: Box<crate::boards::Frame>,
    },
    Text {
        frame: Box<crate::text::Frame>,
    },
    MaskSource {},
    Group {
        #[serde(default = "yes")]
        isolated: bool,
        #[serde(default)]
        role: GroupRole,
        #[serde(default, skip_serializing_if = "is_false")]
        knockout: bool,
    },
    Vector {
        geometry: Geometry,
        fill: Option<Paint>,
        stroke: Option<Box<Stroke>>,
        #[serde(default)]
        fill_rule: FillRule,
    },
    Raster {
        width: u32,
        height: u32,
        rgba_hex: String,
        #[serde(default)]
        sampling: Sampling,
    },
    Fill {
        width: u32,
        height: u32,
        paint: Paint,
        #[serde(default)]
        dither: Dither,
    },
    Image {
        asset_id: String,
        width: f64,
        height: f64,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        crop: Option<Crop>,
        #[serde(default)]
        sampling: Sampling,
    },
}

fn is_false(value: &bool) -> bool {
    !value
}

impl Content {
    pub fn is_knockout(&self) -> bool {
        matches!(self, Self::Group { knockout: true, .. })
    }
    pub fn is_container(&self) -> bool {
        matches!(
            self,
            Self::Group { .. }
                | Self::Frame { .. }
                | Self::MaskSource {}
                | Self::ComponentSource {}
        )
    }
    pub fn is_isolated(&self) -> bool {
        matches!(
            self,
            Self::Group { isolated: true, .. }
                | Self::Frame { .. }
                | Self::ComponentSource {}
                | Self::Instance { .. }
                | Self::Interpolation { .. }
                | Self::Object { .. }
        )
    }
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Item {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub hdr_grade: Option<crate::hdr::Grade>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub pixel_warp: Option<Box<crate::pixel_warps::Spec>>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub metadata: Option<crate::metadata::Record>,
    pub id: String,
    #[serde(default)]
    pub name: String,
    #[serde(default = "yes")]
    pub visible: bool,
    #[serde(default)]
    pub locked: bool,
    #[serde(default = "one")]
    pub opacity: f64,
    #[serde(default = "one", skip_serializing_if = "is_one")]
    pub fill_opacity: f64,
    #[serde(default, skip_serializing_if = "crate::coverage::Mode::is_smooth")]
    pub coverage: crate::coverage::Mode,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub effects: Vec<crate::effects::Effect>,
    #[serde(default)]
    pub blend: BlendMode,
    #[serde(default = "identity")]
    pub transform: Matrix,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub parent: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub clip_to: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub clip: Option<Clip>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub mask: Option<Box<crate::masks::Mask>>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub artwork_mask: Option<Box<crate::artwork_masks::Mask>>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub filters: Vec<crate::filters::Filter>,
    pub content: Content,
}

pub fn valid_id(id: &str) -> bool {
    !id.is_empty()
        && id.len() <= 128
        && id
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || b"._-".contains(&c))
}
pub(crate) fn invalid(message: &str) -> Error {
    Error::new("INVALID_DOCUMENT", message)
}
pub(crate) fn limit(message: &str) -> Error {
    Error::new("RESOURCE_LIMIT", message)
}

pub fn validate(document: &Document) -> Result<(), Error> {
    validate_controlled(document, &crate::control::Control::default())
}

pub fn validate_controlled(
    document: &Document,
    control: &crate::control::Control,
) -> Result<(), Error> {
    control.check()?;
    let budget = document.resource_profile;
    if !budget.is_standard() && document.kind != DocumentKind::Vector {
        return Err(invalid(
            "The large_vector resource profile requires a vector document",
        ));
    }
    if ![1, 2].contains(&document.schema_version) {
        return Err(invalid("Unsupported document schema version"));
    }
    if document.schema_version == 1
        && (!budget.is_standard()
            || !document.stories.is_empty()
            || !document.swatches.is_empty()
            || document.background.is_some()
            || document.metadata.is_some()
            || document.output_profile.is_some()
            || document.variants.is_some()
            || !document.items.is_empty()
            || !document.assets.is_empty()
            || !document.fonts.is_empty()
            || document.selection.is_some()
            || !document.channels.is_empty()
            || document.ink_recipe.is_some()
            || document.revision != 0
            || document.resolution_ppi != 96.0
            || document.vector_canvas.is_some())
    {
        return Err(invalid(
            "Legacy snapshots must be empty at revision zero and 96 ppi",
        ));
    }
    if !valid_id(&document.id) {
        return Err(invalid(
            "ID must contain 1-128 ASCII letters, digits, dots, hyphens or underscores",
        ));
    }
    if !(1..=MAX_DIMENSION).contains(&document.width)
        || !(1..=MAX_DIMENSION).contains(&document.height)
    {
        return Err(invalid("Width and height must each be in 1..=32768 pixels"));
    }
    if !document.resolution_ppi.is_finite() || !(1.0..=9600.0).contains(&document.resolution_ppi) {
        return Err(invalid("Resolution must be finite and in 1..=9600 ppi"));
    }
    if document.items.len() > budget.items() {
        return Err(limit(&format!(
            "Document exceeds {} items for its resource profile",
            budget.items()
        )));
    }
    if let Some(profile) = &document.output_profile {
        crate::profiles::validate_destination(profile)?;
    }
    crate::vector_canvas::validate(document)?;
    crate::hdr::validate_document(document)?;
    crate::metadata::validate_document(document)?;
    let profile_bytes: usize = document
        .items
        .iter()
        .filter_map(|item| {
            if let Content::Samples { grid } = &item.content
                && let Some(crate::profiles::Profile::Icc { data }) = &grid.profile
            {
                return Some(data.len());
            }
            None
        })
        .sum();
    if profile_bytes > crate::sample_profiles::MAX_ENCODED_PROFILE_BYTES {
        return Err(limit(
            "Retained sample profiles exceed aggregate encoded storage limit",
        ));
    }
    crate::swatches::validate(document)?;
    if let Some(selection) = &document.selection {
        crate::selections::validate(selection, document.width, document.height)?;
    }
    crate::channels::validate(document)?;
    crate::ink_recipes::validate(document)?;
    let mut ids = HashSet::new();
    for item in &document.items {
        if !valid_id(&item.id) || !ids.insert(&item.id) {
            return Err(invalid("Item IDs must be valid and unique"));
        }
    }
    let mut segments = 0;
    let mut dash_work = 0;
    let mut outline_commands = 0;
    let mut pixels = 0usize;
    if document.assets.len() > assets::MAX_ASSETS {
        return Err(limit("Document exceeds 64 image assets"));
    }
    let mut asset_pixels = 0u64;
    for (id, asset) in &document.assets {
        if !valid_id(id) {
            return Err(invalid("Asset IDs must use the document ID syntax"));
        }
        pixels += assets::validate(asset)?;
        asset_pixels += asset.width as u64 * asset.height as u64;
        if asset_pixels > assets::MAX_ASSET_PIXELS {
            return Err(limit("Document assets exceed 16777216 decoded pixels"));
        }
    }
    if pixels > MAX_STORED_PIXELS {
        return Err(limit("Embedded assets exceed inline pixel limit"));
    }
    if document.fonts.len() > crate::fonts::MAX_FONTS {
        return Err(limit("Document exceeds 8 pinned fonts"));
    }
    for (id, font) in &document.fonts {
        if !valid_id(id) {
            return Err(invalid("Font ID must use document ID syntax"));
        }
        crate::fonts::validate(font)?;
    }
    let mut characters = 0usize;
    let mut guides = 0;
    let mut boards = 0;
    let mut paint_samples = 0usize;
    if document.stories.len() > crate::text::flow::MAX_STORIES {
        return Err(limit("Document exceeds story count limit"));
    }
    crate::text::flow::hyphens::validate_resources(document.stories.values())?;
    for (id, story) in &document.stories {
        if !valid_id(id) {
            return Err(invalid("Story IDs must use document ID syntax"));
        }
        let (a, b, c) = crate::text::flow::validate(story, document)?;
        characters += a;
        pixels += b;
        paint_samples += c;
    }
    if characters > crate::text::MAX_TEXT_CHARS
        || pixels > MAX_STORED_PIXELS
        || paint_samples > crate::paint::MAX_PAINT_SAMPLES
    {
        return Err(limit(
            "Story resources exceed aggregate text or paint limits",
        ));
    }
    if document
        .items
        .iter()
        .map(|i| i.filters.len())
        .sum::<usize>()
        > crate::filters::MAX_DOCUMENT_FILTERS
    {
        return Err(limit("Document exceeds 64 filters"));
    }
    for (i, item) in document.items.iter().enumerate() {
        if i % 32 == 0 {
            control.check()?;
        }
        if item.name.len() > 1024
            || item
                .name
                .chars()
                .any(|c| c.is_control() || matches!(c, '\u{fffe}' | '\u{ffff}'))
        {
            return Err(invalid(
                "Item names must be at most 1024 bytes and contain no control or invalid XML characters",
            ));
        }
        if !item.opacity.is_finite() || !(0.0..=1.0).contains(&item.opacity) {
            return Err(invalid("Opacity must be in 0..=1"));
        }
        geometry::validate_matrix(item.transform)?;
        let world = scene::world_transform(document, i)?;
        geometry::validate_matrix(world)?;
        segments += crate::pixel_warps::validate(item, world).map_err(|e| e.at_item(&item.id))?;
        pixels += crate::filters::validate(item, world).map_err(|e| e.at_item(&item.id))?;
        for effect in &item.effects {
            let (stored, samples) =
                crate::paint::validate(&effect.color).map_err(|e| e.at_item(&item.id))?;
            pixels += stored;
            paint_samples += samples;
            crate::paint::validate_world(&effect.color, world).map_err(|e| e.at_item(&item.id))?;
        }
        if let Some(clip) = &item.clip {
            crate::work_paths::compound_rule(&clip.geometry, clip.fill_rule)?;
            segments += geometry::validate_geometry(&clip.geometry)?;
            geometry::validate_matrix(clip.transform)?;
            let clip_world = geometry::multiply(world, clip.transform);
            geometry::validate_matrix(clip_world)?;
            validate_world_geometry(&clip.geometry, clip_world)?;
        }
        if let Some(mask) = &item.mask {
            pixels += mask.validate(world).map_err(|e| e.at_item(&item.id))?;
        }
        match &item.content {
            Content::ComponentSource {} | Content::Instance { .. } => {}
            Content::Volume { volume } => {
                if document.kind != DocumentKind::Vector
                    && crate::artwork_masks::source_owner(document, i)?.is_none()
                {
                    return Err(invalid(
                        "Dimensional artwork requires a vector document or mask source",
                    ));
                }
                segments += crate::volumes::stored(volume)?;
            }
            Content::Appearance { appearance } => {
                if document.kind != DocumentKind::Vector
                    && crate::artwork_masks::source_owner(document, i)?.is_none()
                {
                    return Err(invalid(
                        "Appearance stacks require a vector document or mask source",
                    ));
                }
                segments += crate::appearance::stored(appearance)?;
            }
            Content::Warp { warp } => {
                if document.kind != DocumentKind::Vector
                    && crate::artwork_masks::source_owner(document, i)?.is_none()
                {
                    return Err(invalid(
                        "Vector warps require a vector document or mask source",
                    ));
                }
                segments += crate::warps::stored(warp)?;
            }
            Content::Repeat { repeat } => {
                if document.kind != DocumentKind::Vector
                    && crate::artwork_masks::source_owner(document, i)?.is_none()
                {
                    return Err(invalid("Repeats require a vector document or mask source"));
                }
                segments += crate::repeats::stored(repeat)?;
            }
            Content::Interpolation { interpolation } => {
                if document.kind != DocumentKind::Vector
                    && crate::artwork_masks::source_owner(document, i)?.is_none()
                {
                    return Err(invalid(
                        "Interpolation requires a vector document or mask source",
                    ));
                }
                segments += crate::interpolation::stored(interpolation)?;
                if segments > budget.commands() {
                    return Err(limit(
                        "Document exceeds its resource-profile geometry command budget",
                    ));
                }
            }
            Content::MaskSource {} => {}
            Content::WorkPath {
                geometry,
                fill_rule,
            } => {
                crate::work_paths::compound_rule(geometry, *fill_rule)?;
                if item.opacity != 1.0
                    || item.blend != BlendMode::Normal
                    || item.clip.is_some()
                    || item.mask.is_some()
                    || item.artwork_mask.is_some()
                    || !item.filters.is_empty()
                {
                    return Err(Error::new("UNSUPPORTED", "Nonprinting work paths require opacity 1, normal blending and no clip, mask or filters").at_item(&item.id));
                }
                segments += geometry::validate_geometry(geometry)?;
                validate_world_geometry(geometry, world)?;
            }
            Content::Adjustment { adjustment } => {
                if document.kind != DocumentKind::Raster {
                    return Err(invalid("Adjustment layers require a raster document"));
                }
                adjustment.validate().map_err(|e| e.at_item(&item.id))?;
            }
            Content::Frame { frame } => {
                if frame.logical_size.is_some() && document.kind != DocumentKind::Vector {
                    return Err(invalid(
                        "Fractional logical frames require a vector document",
                    ));
                }
                crate::boards::validate(frame)?;
                guides += frame.guides.len();
                boards += usize::from(frame.role == crate::boards::Role::Artboard);
                if guides > crate::boards::MAX_GUIDES || boards > crate::boards::MAX_ARTBOARDS {
                    return Err(limit("Document exceeds guide or artboard count limit"));
                }
                validate_world_geometry(&frame.geometry(), world)?;
            }
            Content::Text { frame } => {
                let (chars, stored, samples) = crate::text::validate(frame, document, world)?;
                characters += chars;
                pixels += stored;
                paint_samples += samples;
                if let Some(path) = &frame.path {
                    segments += crate::path_text::validate(path)?;
                    validate_world_geometry(&path.geometry, world)?;
                }
                if characters > crate::text::MAX_TEXT_CHARS {
                    return Err(limit("Document exceeds text character limit"));
                }
                validate_world_geometry(&crate::text::frame_geometry(frame), world)?;
            }
            Content::StoryFrame { story_id, slot_id } => {
                let story = crate::text::flow::story(document, story_id)?;
                let slot = story.slot(slot_id)?;
                validate_world_geometry(&slot.geometry(), world)?;
                for s in story.styles() {
                    crate::paint::validate_world(&s.fill, world)?;
                }
            }
            Content::Group { isolated, .. } => {
                if !isolated && item.blend != BlendMode::Normal {
                    return Err(Error::new(
                        "UNSUPPORTED",
                        "Pass-through groups require normal group blending; child blend modes still use the surrounding backdrop",
                    ));
                }
            }
            Content::Vector {
                geometry,
                fill,
                stroke,
                ..
            } => {
                if matches!(geometry, Geometry::Compound { .. }) {
                    return Err(Error::new(
                        "UNSUPPORTED",
                        "Compound regions are retained work paths or vector clips; painted compound artwork requires explicit expansion",
                    ));
                }
                if document.kind != DocumentKind::Vector
                    && crate::artwork_masks::source_owner(document, i)?.is_none()
                {
                    return Err(invalid(
                        "Vector content requires a vector document or mask source",
                    ));
                }
                segments += geometry::validate_geometry(geometry)?;
                if segments > budget.commands() {
                    return Err(limit(
                        "Document exceeds its resource-profile geometry command budget",
                    ));
                }
                if let Some(stroke) = stroke
                    && (!stroke.width.is_finite()
                        || !(0.001..=1024.0).contains(&stroke.width)
                        || !stroke.miter_limit.is_finite()
                        || !(1.0..=16.0).contains(&stroke.miter_limit))
                {
                    return Err(invalid(
                        "Stroke width must be in 0.001..=1024 and miter limit in 1..=16",
                    ));
                }
                if let Some(stroke) = stroke {
                    segments += crate::strokes::brush_segments(stroke)?;
                    if segments > budget.commands() {
                        return Err(limit(
                            "Document exceeds its resource-profile geometry command budget",
                        ));
                    }
                    dash_work += crate::strokes::work_placed(geometry, stroke, world)?;
                    crate::strokes::check_work(dash_work, crate::strokes::MAX_DOCUMENT_WORK)?;
                    if let Some(outline) = crate::strokes::generate_placed(geometry, stroke, world)?
                    {
                        validate_world_geometry(&outline, stroke.scaling.matrix(world))?;
                        let Geometry::Path { commands } = outline else {
                            unreachable!()
                        };
                        outline_commands += commands.len();
                        if outline_commands > crate::strokes::MAX_OUTLINE_COMMANDS {
                            return Err(limit(
                                "Document exceeds generated stroke-outline command limit",
                            ));
                        }
                    }
                }
                validate_world_geometry(geometry, world)?;
                for paint in fill.iter().chain(stroke.iter().map(|s| &s.color)) {
                    let (stored, samples) = crate::paint::validate(paint)?;
                    crate::paint::validate_world(paint, world)?;
                    pixels += stored;
                    paint_samples += samples;
                }
            }
            Content::Fill {
                width,
                height,
                paint,
                ..
            } => {
                if document.kind != DocumentKind::Raster {
                    return Err(invalid("Procedural fill layers require a raster document"));
                }
                if !(1..=MAX_DIMENSION).contains(width) || !(1..=MAX_DIMENSION).contains(height) {
                    return Err(invalid("Fill layer dimensions must be in 1..=32768"));
                }
                validate_world_geometry(
                    &Geometry::Rect {
                        x: 0.0,
                        y: 0.0,
                        width: *width as f64,
                        height: *height as f64,
                    },
                    world,
                )?;
                let (stored, samples) = crate::paint::validate(paint)?;
                crate::paint::validate_world(paint, world)?;
                pixels += stored;
                paint_samples += samples;
            }
            Content::Object { object } => {
                crate::objects::validate_placement(object, document, world)?
            }
            Content::Samples { grid } => {
                if document.kind != DocumentKind::Raster {
                    return Err(invalid("Sample grids require a raster document"));
                }
                pixels += grid.validate()?;
                if pixels > MAX_STORED_PIXELS {
                    return Err(limit("Inline pixel storage exceeds 65536 pixels"));
                }
                validate_world_geometry(&grid.geometry(), world)?;
            }
            Content::Raw { raw } => {
                if document.kind != DocumentKind::Raster {
                    return Err(invalid("Raw layers require a raster document"));
                }
                pixels += raw.validate()?;
                if pixels > MAX_STORED_PIXELS {
                    return Err(limit("Inline pixel storage exceeds 65536 pixels"));
                }
                validate_world_geometry(&raw.geometry(), world)?;
            }
            Content::Raster {
                width,
                height,
                rgba_hex,
                ..
            } => {
                if document.kind != DocumentKind::Raster {
                    return Err(invalid("Pixel content requires a raster document"));
                }
                if *width == 0 || *height == 0 || *width > MAX_DIMENSION || *height > MAX_DIMENSION
                {
                    return Err(invalid("Pixel layer dimensions must be in 1..=32768"));
                }
                pixels += *width as usize * *height as usize;
                if pixels > MAX_STORED_PIXELS {
                    return Err(limit("Inline pixel storage exceeds 65536 pixels"));
                }
                if rgba_hex.len() != *width as usize * *height as usize * 8
                    || !rgba_hex.bytes().all(|c| c.is_ascii_hexdigit())
                {
                    return Err(invalid(
                        "Pixel data must contain exactly width*height straight RGBA8 hex values",
                    ));
                }
                validate_world_geometry(
                    &Geometry::Rect {
                        x: 0.0,
                        y: 0.0,
                        width: *width as f64,
                        height: *height as f64,
                    },
                    world,
                )?;
            }
            Content::Image {
                asset_id,
                width,
                height,
                crop,
                ..
            } => {
                let asset = document
                    .assets
                    .get(asset_id)
                    .ok_or_else(|| invalid("Image refers to an undefined asset"))?;
                for value in [width, height] {
                    if !value.is_finite() || !(0.001..=MAX_COORDINATE).contains(value) {
                        return Err(invalid("Placed image dimensions must be in 0.001..=32768"));
                    }
                }
                assets::crop(asset.width, asset.height, *crop)?;
                validate_world_geometry(
                    &Geometry::Rect {
                        x: 0.0,
                        y: 0.0,
                        width: *width,
                        height: *height,
                    },
                    world,
                )?;
            }
        }
        if segments > budget.commands() {
            return Err(limit(
                "Document exceeds its resource-profile geometry command budget",
            ));
        }
        if pixels > MAX_STORED_PIXELS {
            return Err(limit("Inline pixel storage exceeds 65536 pixels"));
        }
        if paint_samples > crate::paint::MAX_PAINT_SAMPLES {
            return Err(limit("Document exceeds 4096 gradient stops and anchors"));
        }
    }
    crate::backgrounds::validate(document)?;
    crate::masks::validate_budget(document)?;
    crate::artwork_masks::validate(document)?;
    crate::adjustments::validate_document(document)?;
    crate::layer_clipping::validate(document)?;
    crate::effects::validate(document)?;
    crate::knockout::validate(document)?;
    crate::instances::validate(document)?;
    crate::appearance::validate(document)?;
    crate::volumes::validate(document)?;
    crate::warps::validate(document)?;
    crate::repeats::validate(document)?;
    crate::interpolation::validate(document)?;
    crate::variants::validate(document)?;
    if serde_json::to_vec(document)
        .map_err(|_| invalid("Document cannot be serialized"))?
        .len()
        > budget.bytes()
    {
        return Err(limit("Snapshot exceeds its resource-profile byte budget"));
    }
    control.check()?;
    Ok(())
}

pub(crate) fn validate_world_geometry(geometry: &Geometry, world: Matrix) -> Result<(), Error> {
    if let Geometry::Compound { operands, .. } = geometry {
        for operand in operands {
            let matrix = crate::geometry::multiply(world, operand.transform);
            crate::geometry::validate_matrix(matrix)?;
            validate_world_geometry(&operand.geometry, matrix)?;
        }
        return Ok(());
    }
    // Bound control points too; curve extrema alone do not bound backend work.
    for point in geometry::control_points(geometry) {
        if geometry::map(world, point)
            .iter()
            .any(|v| !v.is_finite() || v.abs() > MAX_COORDINATE * 2.0)
        {
            return Err(limit("Transformed geometry exceeds coordinate limits"));
        }
    }
    Ok(())
}
