use crate::{Error, geometry, layout, model::*, scene};
use scene::index;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, HashSet};

fn isolated() -> bool {
    true
}

pub const MAX_OPERATIONS: usize = 64;
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum TransformSpace {
    #[default]
    Replace,
    World,
    Local,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct PixelRect {
    pub x: u32,
    pub y: u32,
    pub width: u32,
    pub height: u32,
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
pub enum Operation {
    ResourceProfile {
        profile: ResourceProfile,
    },
    RawSettings {
        id: String,
        settings: crate::raw::Settings,
        corrections: crate::raw::Corrections,
    },
    RawExpand {
        id: String,
    },
    AssistMask {
        id: String,
        options: crate::assistance::segment::Options,
        #[serde(default)]
        replace_existing: bool,
    },
    AssistLayout {
        options: crate::assistance::Layout,
    },
    Volume {
        id: String,
        volume: Box<crate::volumes::Spec>,
    },
    VolumeExpand {
        id: String,
    },
    AppearanceBake {
        id: String,
        asset_id: String,
        image_id: String,
        region: crate::appearance::Bake,
    },
    Appearance {
        id: String,
        appearance: Box<crate::appearance::Spec>,
    },
    AppearanceExpand {
        id: String,
    },
    ObjectReplace {
        id: String,
        object: Box<crate::objects::Object>,
        #[serde(default = "isolated")]
        keep_frame: bool,
    },
    ObjectRefresh {
        id: String,
        link_root: std::path::PathBuf,
        source_sha256: String,
    },
    ObjectDetach {
        id: String,
    },
    WorkingSpace {
        color_space: ColorSpace,
    },
    HdrGrade {
        id: String,
        grade: Option<crate::hdr::Grade>,
    },
    SampleConvert {
        id: String,
        conversion: crate::sample_convert::Conversion,
    },
    SampleProfile {
        id: String,
        action: crate::sample_profiles::Action,
    },
    SampleReplace {
        id: String,
        region: PixelRect,
        data_hex: String,
    },
    Swatch {
        id: String,
        swatch: Option<crate::swatches::Swatch>,
    },
    SwatchBake {
        ids: Vec<String>,
    },
    SwatchProfile {
        id: String,
        action: crate::swatches::device::Action,
    },
    SwatchConvert {
        id: String,
        kind: crate::swatches::ConvertKind,
        #[serde(default)]
        color: Option<crate::swatches::Process>,
    },
    Snap {
        ids: Vec<String>,
        snap: crate::snapping::Options,
    },
    Dimensions {
        id: String,
        dimensions: crate::dimensions::Resize,
    },
    Background {
        id: String,
        action: crate::backgrounds::Action,
    },
    PixelWarp {
        id: String,
        warp: Option<Box<crate::pixel_warps::Spec>>,
    },
    Warp {
        id: String,
        warp: Box<crate::warps::Spec>,
    },
    WarpExpand {
        id: String,
    },
    Repeat {
        id: String,
        repeat: Box<crate::repeats::Spec>,
    },
    RepeatExpand {
        id: String,
    },
    Interpolation {
        id: String,
        interpolation: Box<crate::interpolation::Spec>,
    },
    InterpolationExpand {
        id: String,
    },
    Repair {
        id: String,
        options: Box<crate::repair::Options>,
    },
    Retouch {
        id: String,
        options: Box<crate::retouch::Options>,
    },
    BrushStroke {
        id: String,
        stroke: Box<crate::pixel_brush::Stroke>,
    },
    MeshKnot {
        id: String,
        #[serde(default)]
        target: crate::meshes::Target,
        column: usize,
        row: usize,
        color: Option<Color>,
        offset: Option<Point>,
    },
    Metadata {
        id: Option<String>,
        value: Option<crate::metadata::Record>,
    },
    Transfer {
        transfer: Box<crate::transfer::Transfer>,
    },
    SequenceSet {
        sequence: Option<crate::sequences::Timeline>,
    },
    SequenceFrame {
        id: String,
    },
    SequenceFromLayers {
        ids: Vec<String>,
        delay: crate::sequences::Delay,
        #[serde(default)]
        plays: u32,
    },
    VariantsSet {
        definition: crate::variants::Definition,
    },
    VariantSelect {
        dataset: Option<String>,
    },
    VariantsClear {
        #[serde(default)]
        bake: bool,
    },
    Instance {
        id: String,
        instance: Box<crate::instances::Instance>,
    },
    InstanceUnlink {
        id: String,
    },
    StrokeExpand {
        id: String,
        fill_id: String,
        stroke_id: String,
    },
    VectorCanvas {
        action: crate::vector_canvas::Action,
    },
    Canvas {
        action: crate::canvas::Action,
    },
    LayerClip {
        id: String,
        clip_to: Option<String>,
    },
    WorkPath {
        id: String,
        geometry: Geometry,
        #[serde(default)]
        fill_rule: FillRule,
    },
    WorkPathCombine {
        ids: Vec<String>,
        new_id: String,
        mode: crate::booleans::Mode,
    },
    PathComponent {
        id: String,
        component: Vec<usize>,
        #[serde(default)]
        clip: bool,
        action: crate::paths::Action,
    },
    SelectionPath {
        id: String,
        #[serde(default)]
        combine: crate::selections::Combine,
        #[serde(default = "isolated")]
        antialias: bool,
    },
    ClipFromPath {
        id: String,
        path_id: String,
        #[serde(default)]
        replace_existing: bool,
    },
    Filters {
        id: String,
        filters: Vec<crate::filters::Filter>,
    },
    Adjustment {
        id: String,
        adjustment: Box<crate::adjustments::Layer>,
    },
    Path {
        id: String,
        action: crate::paths::Action,
    },
    Frame {
        id: String,
        frame: Box<crate::boards::Frame>,
    },
    GuidePut {
        id: String,
        guide: crate::boards::Guide,
    },
    GuideRemove {
        id: String,
        guide_id: String,
    },
    FontPut {
        id: String,
        font: crate::fonts::Font,
    },
    FontRemove {
        id: String,
    },
    Text {
        id: String,
        frame: Box<crate::text::Frame>,
    },
    Story {
        id: String,
        story: Option<Box<crate::text::flow::Story>>,
    },
    StoryRange {
        id: String,
        paragraph: usize,
        start: usize,
        end: usize,
        text: Option<String>,
        style: Option<crate::text::Style>,
    },
    TextRange {
        id: String,
        start: usize,
        end: usize,
        text: Option<String>,
        style: Option<crate::text::Style>,
    },
    TextOutline {
        id: String,
    },
    AssetPut {
        id: String,
        asset: crate::assets::ImageAsset,
    },
    AssetRemove {
        id: String,
    },
    Add {
        item: Box<Item>,
        index: Option<usize>,
    },
    Remove {
        id: String,
    },
    Duplicate {
        id: String,
        new_id: String,
        index: Option<usize>,
        #[serde(default)]
        descendant_ids: BTreeMap<String, String>,
    },
    Group {
        ids: Vec<String>,
        new_id: String,
        #[serde(default)]
        name: String,
        #[serde(default = "isolated")]
        isolated: bool,
        #[serde(default)]
        role: GroupRole,
        #[serde(default)]
        knockout: bool,
    },
    Ungroup {
        id: String,
    },
    Reparent {
        id: String,
        parent: Option<String>,
        index: Option<usize>,
    },
    GroupOptions {
        id: String,
        isolated: bool,
        #[serde(default)]
        knockout: Option<bool>,
    },
    SelectionSet {
        selection: Option<crate::selections::Selection>,
    },
    ChannelPut {
        id: String,
        channel: crate::channels::Channel,
        #[serde(default)]
        replace_existing: bool,
    },
    InkRecipe {
        recipe: Option<crate::ink_recipes::Recipe>,
    },
    ChannelRemove {
        id: String,
    },
    ChannelCalculate {
        id: String,
        name: String,
        #[serde(default)]
        role: crate::channels::Role,
        calculation: crate::channels::Calculation,
        #[serde(default)]
        replace_existing: bool,
    },
    ChannelLoad {
        id: String,
        #[serde(default)]
        combine: crate::selections::Combine,
    },
    SelectionSample {
        method: crate::selection_analysis::Method,
        #[serde(default)]
        combine: crate::selections::Combine,
    },
    SelectionFill {
        selected: bool,
    },
    SelectionShape {
        boundary: crate::selections::Boundary,
        #[serde(default)]
        combine: crate::selections::Combine,
        #[serde(default = "isolated")]
        antialias: bool,
        #[serde(default)]
        fill_rule: FillRule,
    },
    SelectionInvert {},
    SelectionRefine {
        mode: crate::selections::Refine,
        radius: u32,
    },
    MaskFromSelection {
        id: String,
        #[serde(default = "isolated")]
        linked: bool,
        #[serde(default)]
        replace_existing: bool,
    },
    MaskApply {
        id: String,
    },
    Mask {
        id: String,
        mask: Option<Box<crate::masks::Mask>>,
    },
    MaskLink {
        id: String,
        linked: bool,
    },
    ArtworkMask {
        id: String,
        mask: Option<Box<crate::artwork_masks::Mask>>,
    },
    ArtworkMaskLink {
        id: String,
        linked: bool,
    },
    ArtworkMaskTransform {
        id: String,
        matrix: Matrix,
        #[serde(default)]
        space: TransformSpace,
    },
    MaskTransform {
        id: String,
        matrix: Matrix,
        #[serde(default)]
        space: TransformSpace,
    },
    Clip {
        id: String,
        clip: Option<Clip>,
    },
    Align {
        ids: Vec<String>,
        axis: layout::Axis,
        anchor: layout::Anchor,
        reference: layout::Reference,
    },
    Distribute {
        ids: Vec<String>,
        axis: layout::Axis,
        mode: layout::Distribution,
        reference: layout::Reference,
    },
    Reorder {
        id: String,
        index: usize,
    },
    Properties {
        id: String,
        name: Option<String>,
        visible: Option<bool>,
        locked: Option<bool>,
        opacity: Option<f64>,
        fill_opacity: Option<f64>,
        coverage: Option<crate::coverage::Mode>,
        blend: Option<BlendMode>,
    },
    GlobalLight {
        light: crate::effects::Lighting,
    },
    OutputProfile {
        profile: Option<crate::profiles::Profile>,
    },
    EffectsScale {
        ids: Vec<String>,
        factor: f64,
    },
    Effects {
        id: String,
        effects: Vec<crate::effects::Effect>,
    },
    Transform {
        id: String,
        matrix: Matrix,
        #[serde(default)]
        space: TransformSpace,
        anchor: Option<Point>,
    },
    Vector {
        id: String,
        geometry: Geometry,
        fill: Option<Paint>,
        stroke: Option<Box<Stroke>>,
        #[serde(default)]
        fill_rule: FillRule,
    },
    PixelFill {
        id: String,
        rect: PixelRect,
        color: Color,
    },
    Fill {
        id: String,
        paint: Paint,
        #[serde(default)]
        dither: Dither,
    },
    Image {
        id: String,
        asset_id: String,
        width: f64,
        height: f64,
        crop: Option<crate::assets::Crop>,
        #[serde(default)]
        sampling: crate::assets::Sampling,
    },
    Sampling {
        id: String,
        sampling: crate::assets::Sampling,
    },
}
#[derive(Debug, Serialize)]
pub struct Change {
    pub operation_index: usize,
    pub id: String,
    pub action: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub details: Option<serde_json::Value>,
}
#[derive(Debug, Serialize)]
pub struct EditResult {
    pub document: Document,
    pub from_revision: u64,
    pub changes: Vec<Change>,
}
fn unlocked(document: &Document, i: usize) -> Result<(), Error> {
    scene::check_unlocked(document, i, true)
}
fn add(document: &mut Document, item: Item, at: Option<usize>) -> Result<(), Error> {
    if !valid_id(&item.id) || document.items.iter().any(|i| i.id == item.id) {
        return Err(invalid("New item requires a valid unused ID"));
    }
    if let Some(parent) = &item.parent {
        let p = index(document, parent)?;
        if !document.items[p].content.is_container() {
            return Err(invalid("Parent must be a group, layer, frame or artboard"));
        }
        scene::check_unlocked(document, p, false)?;
    }
    let at = scene::insertion(document, item.parent.as_deref(), at)?;
    document.items.insert(at, item);
    Ok(())
}
/// Applies to a private candidate. Any failure discards the entire batch.
/// The caller owns storage; revision checks do not provide a shared session store.
pub fn apply(
    document: &Document,
    expected_revision: u64,
    operations: &[Operation],
) -> Result<EditResult, Error> {
    apply_with_fonts(document, expected_revision, operations, None)
}
pub fn apply_with_fonts(
    document: &Document,
    expected_revision: u64,
    operations: &[Operation],
    font_root: Option<&std::path::Path>,
) -> Result<EditResult, Error> {
    apply_controlled(
        document,
        expected_revision,
        operations,
        font_root,
        &crate::control::Control::default(),
    )
}
pub fn apply_controlled(
    document: &Document,
    expected_revision: u64,
    operations: &[Operation],
    font_root: Option<&std::path::Path>,
    control: &crate::control::Control,
) -> Result<EditResult, Error> {
    apply_with_resources(
        document,
        expected_revision,
        operations,
        None,
        font_root,
        control,
    )
}
pub fn apply_with_resources(
    document: &Document,
    expected_revision: u64,
    operations: &[Operation],
    asset_root: Option<&std::path::Path>,
    font_root: Option<&std::path::Path>,
    control: &crate::control::Control,
) -> Result<EditResult, Error> {
    control.check()?;
    validate_controlled(document, control)?;
    if expected_revision != document.revision {
        return Err(Error::new(
            "REVISION_CONFLICT",
            "Expected revision does not match the supplied snapshot",
        ));
    }
    if operations.is_empty() || operations.len() > MAX_OPERATIONS {
        return Err(Error::new(
            "INVALID_OPERATION",
            "A batch must contain 1 through 64 operations",
        ));
    }
    let next = document
        .revision
        .checked_add(1)
        .ok_or_else(|| limit("Revision counter exhausted"))?;
    let mut candidate = document.clone();
    candidate.schema_version = 2;
    let mut changes = Vec::new();
    for (operation_index, operation) in operations.iter().enumerate() {
        control
            .check()
            .map_err(|e| e.at_operation(operation_index))?;
        let mut details = None;
        let (id, action) = apply_one(
            &mut candidate,
            operation,
            asset_root,
            font_root,
            &mut details,
            control,
        )
        .map_err(|e| e.at_operation(operation_index))?;
        validate_controlled(&candidate, control).map_err(|e| e.at_operation(operation_index))?;
        changes.push(Change {
            operation_index,
            id,
            action,
            details,
        });
    }
    control.check()?;
    candidate.revision = next;
    validate_controlled(&candidate, control)?;
    Ok(EditResult {
        document: candidate,
        from_revision: document.revision,
        changes,
    })
}
fn apply_one(
    document: &mut Document,
    operation: &Operation,
    asset_root: Option<&std::path::Path>,
    font_root: Option<&std::path::Path>,
    details: &mut Option<serde_json::Value>,
    control: &crate::control::Control,
) -> Result<(String, &'static str), Error> {
    match operation {
        Operation::ResourceProfile { profile } => {
            document.resource_profile = *profile;
            Ok((document.id.clone(), "resource_profile_changed"))
        }
        Operation::RawSettings {
            id,
            settings,
            corrections,
        } => {
            *details = Some(crate::raw::retained::edit(
                document,
                id,
                settings,
                corrections,
            )?);
            Ok((id.clone(), "raw_settings"))
        }
        Operation::RawExpand { id } => {
            *details = Some(crate::raw::retained::expand(document, id, control)?);
            Ok((id.clone(), "raw_expanded"))
        }
        Operation::AssistMask {
            id,
            options,
            replace_existing,
        } => {
            *details = Some(crate::assistance::segment::apply(
                document,
                id,
                options,
                *replace_existing,
                asset_root,
                control,
            )?);
            Ok((id.clone(), "assisted_mask"))
        }
        Operation::AssistLayout { options } => {
            *details = Some(crate::assistance::apply(document, options, control)?);
            Ok((document.id.clone(), "automatic_layout"))
        }
        Operation::Volume { id, volume } => {
            let i = index(document, id)?;
            scene::check_unlocked(document, i, true)?;
            if !matches!(
                document.items[i].content,
                Content::Vector { .. } | Content::Volume { .. }
            ) {
                return Err(Error::new(
                    "INVALID_VOLUME",
                    "Dimensional editing requires a vector or volume item",
                ));
            }
            document.items[i].content = Content::Volume {
                volume: volume.clone(),
            };
            Ok((id.clone(), "volume_changed"))
        }
        Operation::VolumeExpand { id } => {
            let i = index(document, id)?;
            scene::check_unlocked(document, i, true)?;
            *details = Some(crate::volumes::expand(document, i, control)?);
            Ok((id.clone(), "volume_expanded"))
        }
        Operation::Appearance { id, appearance } => {
            let i = index(document, id)?;
            scene::check_unlocked(document, i, true)?;
            if !matches!(
                document.items[i].content,
                Content::Vector { .. } | Content::Appearance { .. }
            ) {
                return Err(Error::new(
                    "INVALID_APPEARANCE",
                    "Appearance editing requires a vector or appearance item",
                ));
            }
            document.items[i].content = Content::Appearance {
                appearance: appearance.clone(),
            };
            Ok((id.clone(), "appearance_changed"))
        }
        Operation::AppearanceBake {
            id,
            asset_id,
            image_id,
            region,
        } => {
            let i = index(document, id)?;
            scene::check_unlocked(document, i, true)?;
            *details = Some(crate::appearance::bake(
                document, i, asset_id, image_id, *region, control,
            )?);
            Ok((id.clone(), "appearance_baked"))
        }
        Operation::AppearanceExpand { id } => {
            let i = index(document, id)?;
            scene::check_unlocked(document, i, true)?;
            *details = Some(crate::appearance::expand(document, i, control)?);
            Ok((id.clone(), "appearance_expanded"))
        }
        Operation::ObjectReplace {
            id,
            object,
            keep_frame,
        } => {
            *details = Some(crate::objects::replace(document, id, object, *keep_frame)?);
            Ok((id.clone(), "object_replaced"))
        }
        Operation::ObjectRefresh {
            id,
            link_root,
            source_sha256,
        } => {
            *details = Some(crate::objects::refresh(
                document,
                id,
                link_root,
                source_sha256,
            )?);
            Ok((id.clone(), "object_refreshed"))
        }
        Operation::ObjectDetach { id } => {
            *details = Some(crate::objects::detach(document, id)?);
            Ok((id.clone(), "object_detached"))
        }
        Operation::Swatch { id, swatch } => {
            *details = Some(crate::swatches::set(document, id, swatch.as_ref())?);
            Ok((id.clone(), "swatch"))
        }
        Operation::SwatchBake { ids } => {
            *details = Some(crate::swatches::bake(document, ids)?);
            Ok((document.id.clone(), "swatches_baked"))
        }
        Operation::SwatchProfile { id, action } => {
            *details = Some(crate::swatches::device::apply(
                document,
                id,
                action,
                Some(control),
            )?);
            Ok((id.clone(), "swatch_profile"))
        }
        Operation::WorkingSpace { color_space } => {
            *details = Some(crate::hdr::set_space(document, color_space.clone())?);
            Ok((document.id.clone(), "working_space"))
        }
        Operation::HdrGrade { id, grade } => {
            *details = Some(crate::hdr::set_grade(document, id, *grade)?);
            Ok((id.clone(), "hdr_grade"))
        }
        Operation::SampleConvert { id, conversion } => {
            *details = Some(crate::sample_convert::apply(document, id, conversion)?);
            Ok((id.clone(), "samples_converted"))
        }
        Operation::SampleProfile { id, action } => {
            *details = Some(crate::sample_profiles::apply(
                document, id, action, control,
            )?);
            Ok((id.clone(), "sample_profile"))
        }
        Operation::SampleReplace {
            id,
            region,
            data_hex,
        } => {
            *details = Some(crate::samples::replace(
                document, id, region, data_hex, asset_root, control,
            )?);
            Ok((id.clone(), "samples_replaced"))
        }
        Operation::SwatchConvert { id, kind, color } => {
            *details = Some(crate::swatches::convert(
                document,
                id,
                *kind,
                color.as_ref(),
            )?);
            Ok((document.id.clone(), "swatch_converted"))
        }
        Operation::Snap { ids, snap } => {
            *details = Some(crate::snapping::apply(document, ids, snap, control)?);
            Ok((document.id.clone(), "snapped"))
        }
        Operation::Dimensions { id, dimensions } => {
            *details = Some(crate::dimensions::resize(document, id, dimensions)?);
            Ok((id.clone(), "dimensions"))
        }
        Operation::Background { id, action } => {
            *details = Some(crate::backgrounds::apply(document, id, action)?);
            Ok((id.clone(), "background"))
        }
        Operation::PixelWarp { id, warp } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            crate::pixel_warps::frame(&document.items[i])?;
            document.items[i].pixel_warp = warp.clone();
            Ok((id.clone(), "pixel_warp_updated"))
        }
        Operation::Warp { id, warp } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            if !matches!(document.items[i].content, Content::Warp { .. }) {
                return Err(Error::new(
                    "INVALID_OPERATION",
                    "Warp replacement requires a warp item",
                ));
            }
            document.items[i].content = Content::Warp { warp: warp.clone() };
            Ok((id.clone(), "warp_updated"))
        }
        Operation::WarpExpand { id } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            let Content::Warp { warp } = &document.items[i].content else {
                return Err(Error::new(
                    "INVALID_OPERATION",
                    "Expansion requires a warp item",
                ));
            };
            document.items[i].content = crate::warps::content_controlled(warp, control)?;
            *details = Some(
                serde_json::json!({"source_retained_in_input":true,"expansion":"certified_polyline_geometry"}),
            );
            Ok((id.clone(), "warp_expanded"))
        }
        Operation::Repeat { id, repeat } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            if !matches!(document.items[i].content, Content::Repeat { .. }) {
                return Err(Error::new(
                    "INVALID_OPERATION",
                    "Repeat replacement requires a repeat item",
                ));
            }
            document.items[i].content = Content::Repeat {
                repeat: repeat.clone(),
            };
            Ok((id.clone(), "repeat_updated"))
        }
        Operation::RepeatExpand { id } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            let Content::Repeat { repeat } = &document.items[i].content else {
                return Err(Error::new(
                    "INVALID_OPERATION",
                    "Expansion requires a repeat item",
                ));
            };
            *details = Some(
                serde_json::json!({"copies":crate::repeats::count(&repeat.layout)?,"source_retained_in_input":true,"appearance":"combined_fill_once","expansion":"compound_vector_geometry"}),
            );
            document.items[i].content = crate::repeats::content(repeat)?;
            Ok((id.clone(), "repeat_expanded"))
        }
        Operation::Interpolation { id, interpolation } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            if !matches!(document.items[i].content, Content::Interpolation { .. }) {
                return Err(Error::new(
                    "INVALID_OPERATION",
                    "Interpolation replacement requires an interpolation item",
                ));
            }
            document.items[i].content = Content::Interpolation {
                interpolation: interpolation.clone(),
            };
            Ok((id.clone(), "interpolation_updated"))
        }
        Operation::InterpolationExpand { id } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            *details = Some(crate::interpolation::expand(document, i)?);
            Ok((id.clone(), "interpolation_expanded"))
        }
        Operation::Repair { id, options } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            *details = Some(crate::repair::apply(document, i, options, control)?);
            Ok((id.clone(), "repair"))
        }
        Operation::Retouch { id, options } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            *details = Some(crate::retouch::apply(
                document, i, options, asset_root, control,
            )?);
            Ok((id.clone(), "retouch"))
        }
        Operation::BrushStroke { id, stroke } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            *details = Some(crate::pixel_brush::apply(
                document, i, stroke, asset_root, control,
            )?);
            Ok((id.clone(), "brush_stroke"))
        }
        Operation::Transfer { transfer } => {
            *details = Some(crate::transfer::apply(
                document, transfer, asset_root, font_root, control,
            )?);
            Ok((document.id.clone(), "transferred"))
        }
        Operation::SequenceSet { sequence } => {
            *details = Some(crate::sequences::set(document, sequence.clone())?);
            Ok((document.id.clone(), "sequence_set"))
        }
        Operation::SequenceFrame { id } => {
            *details = Some(crate::sequences::select(document, id)?);
            Ok((id.clone(), "sequence_frame_selected"))
        }
        Operation::SequenceFromLayers { ids, delay, plays } => {
            *details = Some(crate::sequences::from_layers(
                document, ids, *delay, *plays,
            )?);
            Ok((document.id.clone(), "sequence_from_layers"))
        }
        Operation::VariantsSet { definition } => {
            *details = Some(crate::variants::define(document, definition.clone())?);
            Ok((document.id.clone(), "variants_defined"))
        }
        Operation::VariantSelect { dataset } => {
            *details = Some(crate::variants::select(document, dataset.clone())?);
            Ok((document.id.clone(), "variant_selected"))
        }
        Operation::VariantsClear { bake } => {
            *details = Some(crate::variants::clear(document, *bake)?);
            Ok((document.id.clone(), "variants_cleared"))
        }
        Operation::Instance { id, instance } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            if !matches!(document.items[i].content, Content::Instance { .. }) {
                return Err(Error::new(
                    "INVALID_OPERATION",
                    "Instance replacement requires an instance item",
                ));
            }
            document.items[i].content = Content::Instance {
                instance: instance.clone(),
            };
            Ok((id.clone(), "instance_updated"))
        }
        Operation::InstanceUnlink { id } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            *details = Some(crate::instances::unlink(document, i)?);
            Ok((id.clone(), "instance_unlinked"))
        }
        Operation::StrokeExpand {
            id,
            fill_id,
            stroke_id,
        } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            *details = Some(crate::strokes::expand(document, i, fill_id, stroke_id)?);
            Ok((id.clone(), "stroke_expanded"))
        }
        Operation::VectorCanvas { action } => {
            *details = Some(crate::vector_canvas::apply(document, action)?);
            Ok((document.id.clone(), "vector_canvas_edited"))
        }
        Operation::Canvas { action } => {
            *details = Some(crate::canvas::edit(document, action)?);
            Ok((document.id.clone(), "canvas_edited"))
        }
        Operation::Filters { id, filters } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            document.items[i].filters = filters.clone();
            Ok((id.clone(), "filters_updated"))
        }
        Operation::Adjustment { id, adjustment } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            if !matches!(document.items[i].content, Content::Adjustment { .. }) {
                return Err(Error::new(
                    "INVALID_OPERATION",
                    "Adjustment editing requires an adjustment layer",
                ));
            }
            document.items[i].content = Content::Adjustment {
                adjustment: adjustment.clone(),
            };
            Ok((id.clone(), "adjustment_updated"))
        }
        Operation::LayerClip { id, clip_to } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            document.items[i].clip_to = clip_to.clone();
            Ok((id.clone(), "layer_clip"))
        }
        Operation::Path { id, action } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            *details = crate::paths::edit(document, i, action).map_err(|e| e.at_item(id))?;
            Ok((id.clone(), "path_edited"))
        }
        Operation::WorkPathCombine { ids, new_id, mode } => {
            let item = crate::work_paths::combine(document, ids, new_id, *mode)?;
            add(document, item, None)?;
            *details = Some(
                serde_json::json!({"source_ids":ids,"source_changed":false,"geometry":"retained_compound_region","coordinates":"root","mode":mode}),
            );
            Ok((new_id.clone(), "work_path_combined"))
        }
        Operation::PathComponent {
            id,
            component,
            clip,
            action,
        } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            *details = crate::work_paths::edit_component(document, i, component, *clip, action)?;
            Ok((id.clone(), "path_component_edited"))
        }
        Operation::WorkPath {
            id,
            geometry,
            fill_rule,
        } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            if !matches!(document.items[i].content, Content::WorkPath { .. }) {
                return Err(Error::new(
                    "INVALID_OPERATION",
                    "Work-path replacement requires a work path",
                ));
            }
            document.items[i].content = Content::WorkPath {
                geometry: geometry.clone(),
                fill_rule: *fill_rule,
            };
            Ok((id.clone(), "work_path"))
        }
        Operation::SelectionPath {
            id,
            combine,
            antialias,
        } => {
            crate::work_paths::select(document, id, *combine, *antialias)?;
            Ok((document.id.clone(), "pixel_selection"))
        }
        Operation::ClipFromPath {
            id,
            path_id,
            replace_existing,
        } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            crate::work_paths::clip_from_path(document, i, path_id, *replace_existing)?;
            Ok((id.clone(), "clip"))
        }
        Operation::Frame { id, frame } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            if !matches!(document.items[i].content, Content::Frame { .. }) {
                return Err(Error::new(
                    "INVALID_OPERATION",
                    "Frame editing requires a frame or artboard",
                ));
            }
            document.items[i].content = Content::Frame {
                frame: frame.clone(),
            };
            Ok((id.clone(), "frame"))
        }
        Operation::GuidePut { id, guide } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            let Content::Frame { frame } = &mut document.items[i].content else {
                return Err(Error::new(
                    "INVALID_OPERATION",
                    "Guides belong to a frame or artboard",
                ));
            };
            if let Some(old) = frame.guides.iter_mut().find(|g| g.id == guide.id) {
                *old = guide.clone();
            } else {
                frame.guides.push(guide.clone());
            }
            Ok((id.clone(), "guide"))
        }
        Operation::GuideRemove { id, guide_id } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            let Content::Frame { frame } = &mut document.items[i].content else {
                return Err(Error::new(
                    "INVALID_OPERATION",
                    "Guides belong to a frame or artboard",
                ));
            };
            let n = frame
                .guides
                .iter()
                .position(|g| &g.id == guide_id)
                .ok_or_else(|| Error::new("NOT_FOUND", "Guide ID does not exist in this frame"))?;
            frame.guides.remove(n);
            Ok((id.clone(), "guide_removed"))
        }
        Operation::FontPut { id, font } => {
            if !valid_id(id) {
                return Err(invalid("Font ID must use document ID syntax"));
            }
            crate::fonts::validate(font)?;
            for (story_id, story) in &document.stories {
                if story.styles().any(|s| s.font_ids().any(|f| f == id)) {
                    crate::text::flow::check_unlocked(document, story_id)?;
                }
            }
            for i in crate::variants::resource_users(document, id, true) {
                unlocked(document, i)?;
            }
            for (i, item) in document.items.iter().enumerate() {
                if crate::instances::any_content(
                    &item.content,
                    &|c| matches!(c, Content::Text { frame } if crate::text::styles(frame).any(|s| s.font_ids().any(|f| f == id))),
                ) {
                    unlocked(document, i)?;
                }
            }
            document.fonts.insert(id.clone(), font.clone());
            Ok((id.clone(), "font"))
        }
        Operation::FontRemove { id } => {
            if document
                .stories
                .values()
                .any(|s| s.styles().any(|style| style.font_ids().any(|f| f == id)))
            {
                return Err(Error::new("FONT_IN_USE", "Font is retained by a story").at_font(id));
            }
            if !crate::variants::resource_users(document, id, true).is_empty() {
                return Err(
                    Error::new("FONT_IN_USE", "Font is retained by variant datasets").at_font(id),
                );
            }
            if document.items.iter().any(|item|crate::instances::any_content(&item.content, &|c| matches!(c,Content::Text{frame} if crate::text::styles(frame).any(|s|s.font_ids().any(|f|f==id))))){return Err(Error::new("FONT_IN_USE","Remove or relink text before removing its font").at_font(id));}
            if document.fonts.remove(id).is_none() {
                return Err(Error::new("FONT_MISSING", "Font ID does not exist").at_font(id));
            }
            Ok((id.clone(), "font_removed"))
        }
        Operation::Text { id, frame } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            if !matches!(document.items[i].content, Content::Text { .. }) {
                return Err(Error::new(
                    "INVALID_OPERATION",
                    "Text edits require a text item",
                ));
            }
            document.items[i].content = Content::Text {
                frame: frame.clone(),
            };
            Ok((id.clone(), "text"))
        }
        Operation::Story { id, story } => {
            crate::text::flow::set(document, id, story.as_deref())?;
            Ok((id.clone(), "story"))
        }
        Operation::StoryRange {
            id,
            paragraph,
            start,
            end,
            text,
            style,
        } => {
            crate::text::flow::revise(
                document,
                id,
                *paragraph,
                [*start, *end],
                text.as_deref(),
                style.as_ref(),
            )?;
            Ok((id.clone(), "story_range"))
        }
        Operation::TextRange {
            id,
            start,
            end,
            text,
            style,
        } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            let Content::Text { frame } = &mut document.items[i].content else {
                return Err(Error::new(
                    "INVALID_OPERATION",
                    "Text range edits require a text item",
                ));
            };
            crate::text::revise(frame, *start, *end, text.as_deref(), style.as_ref())?;
            Ok((id.clone(), "text_range"))
        }
        Operation::TextOutline { id } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            if document.kind != DocumentKind::Vector {
                return Err(Error::new(
                    "UNSUPPORTED",
                    "Editable outline conversion requires a vector document",
                ));
            }
            let cache = crate::fonts::resolve(document, font_root)?;
            let layout = match &document.items[i].content {
                Content::Text { frame } => crate::text::layout(frame, document, &cache)?,
                Content::StoryFrame { story_id, slot_id } => {
                    crate::text::flow::placed(document, story_id, slot_id, &cache)?
                }
                _ => {
                    return Err(Error::new(
                        "INVALID_OPERATION",
                        "Outline conversion requires text",
                    ));
                }
            };
            crate::text::outline_item(document, i, &layout)?;
            Ok((id.clone(), "text_outlined"))
        }
        Operation::AssetPut { id, asset } => {
            if !valid_id(id) {
                return Err(invalid("Asset ID must use the document ID syntax"));
            }
            crate::assets::validate(asset)?;
            for i in crate::variants::resource_users(document, id, false) {
                unlocked(document, i)?;
            }
            for (i, item) in document.items.iter().enumerate() {
                if crate::instances::any_content(
                    &item.content,
                    &|c| matches!(c,Content::Image{asset_id,..} if asset_id==id),
                ) {
                    unlocked(document, i)?;
                }
            }
            document.assets.insert(id.clone(), asset.clone());
            Ok((id.clone(), "asset_updated"))
        }
        Operation::AssetRemove { id } => {
            if !crate::variants::resource_users(document, id, false).is_empty() {
                return Err(Error::new(
                    "ASSET_IN_USE",
                    "Image asset is retained by variant datasets",
                )
                .at_asset(id));
            }
            if document.items.iter().any(|i| {
                crate::instances::any_content(
                    &i.content,
                    &|c| matches!(c,Content::Image{asset_id,..} if asset_id==id),
                )
            }) {
                return Err(Error::new(
                    "ASSET_IN_USE",
                    "Remove or relink every referencing image before removing an asset",
                ));
            }
            document
                .assets
                .remove(id)
                .ok_or_else(|| Error::new("NOT_FOUND", "Asset ID does not exist"))?;
            Ok((id.clone(), "asset_removed"))
        }
        Operation::Image {
            id,
            asset_id,
            width,
            height,
            crop,
            sampling,
        } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            if !matches!(document.items[i].content, Content::Image { .. }) {
                return Err(Error::new(
                    "INVALID_OPERATION",
                    "Image edits require a placed image item",
                ));
            }
            document.items[i].content = Content::Image {
                asset_id: asset_id.clone(),
                width: *width,
                height: *height,
                crop: *crop,
                sampling: *sampling,
            };
            Ok((id.clone(), "image"))
        }
        Operation::Sampling { id, sampling } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            match &mut document.items[i].content {
                Content::Samples { grid } => grid.sampling = *sampling,
                Content::StoredSamples { grid } => grid.sampling = *sampling,
                Content::Raw { raw } => raw.sampling = *sampling,
                Content::Image { sampling: old, .. } | Content::Raster { sampling: old, .. } => {
                    *old = *sampling
                }
                _ => {
                    return Err(Error::new(
                        "INVALID_OPERATION",
                        "Sampling edits require pixel or placed image content",
                    ));
                }
            }
            Ok((id.clone(), "sampling"))
        }
        Operation::Add { item, index } => {
            add(document, item.as_ref().clone(), *index)?;
            Ok((item.id.clone(), "added"))
        }
        Operation::Remove { id } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            let removed: HashSet<_> = scene::subtree(document, i).into_iter().collect();
            if document
                .background
                .as_ref()
                .is_some_and(|b| removed.iter().any(|&j| document.items[j].id == b.item_id))
            {
                document.background = None;
            }
            document.items = document
                .items
                .iter()
                .enumerate()
                .filter(|(j, _)| !removed.contains(j))
                .map(|(_, item)| item.clone())
                .collect();
            Ok((id.clone(), "removed"))
        }
        Operation::Duplicate {
            id,
            new_id,
            index: at,
            descendant_ids,
        } => {
            let i = index(document, id)?;
            let descendants: Vec<_> = scene::subtree(document, i)
                .into_iter()
                .filter(|&c| c != i)
                .collect();
            if descendant_ids.len() != descendants.len()
                || descendants
                    .iter()
                    .any(|&c| !descendant_ids.contains_key(&document.items[c].id))
            {
                return Err(Error::new(
                    "INVALID_OPERATION",
                    "Group duplication requires an exact old-to-new ID map for every descendant",
                ));
            }
            let mut remap = descendant_ids.clone();
            remap.insert(id.clone(), new_id.clone());
            let mut copies = Vec::new();
            for c in descendants {
                let mut copy = document.items[c].clone();
                copy.id = remap[&copy.id].clone();
                copy.parent = copy.parent.map(|p| remap[&p].clone());
                if let Some(base) = &mut copy.clip_to
                    && let Some(replacement) = remap.get(base)
                {
                    *base = replacement.clone();
                }
                if let Content::Adjustment { adjustment } = &mut copy.content
                    && let Some(base) = &mut adjustment.clip_to
                    && let Some(replacement) = remap.get(base)
                {
                    *base = replacement.clone();
                }
                copies.push(copy);
            }
            let mut copy = document.items[i].clone();
            copy.id = new_id.clone();
            add(document, copy, *at)?;
            document.items.extend(copies);
            Ok((new_id.clone(), "added"))
        }
        Operation::Group {
            ids,
            new_id,
            name,
            isolated,
            role,
            knockout,
        } => {
            let selected = scene::selection(document, ids, true)?;
            let parent = document.items[selected[0]].parent.clone();
            if selected.iter().any(|&i| document.items[i].parent != parent) {
                return Err(Error::new(
                    "INVALID_OPERATION",
                    "Grouping requires siblings under one parent",
                ));
            }
            for &i in &selected {
                unlocked(document, i)?;
            }
            let siblings = scene::children(document, parent.as_deref());
            let selected_set: HashSet<_> = selected.iter().copied().collect();
            let positions: Vec<_> = siblings
                .iter()
                .enumerate()
                .filter_map(|(p, i)| selected_set.contains(i).then_some(p))
                .collect();
            if positions.last().unwrap() - positions[0] + 1 != positions.len() {
                return Err(Error::new(
                    "INVALID_OPERATION",
                    "Group a contiguous sibling range to preserve stacking order",
                ));
            }
            let group = Item {
                hdr_grade: None,
                pixel_warp: None,
                metadata: None,
                id: new_id.clone(),
                name: name.clone(),
                visible: true,
                locked: false,
                opacity: 1.0,
                fill_opacity: 1.0,
                coverage: crate::coverage::Mode::Smooth {},
                effects: Vec::new(),
                blend: BlendMode::Normal,
                transform: identity(),
                parent,
                clip_to: None,
                clip: None,
                mask: None,
                artwork_mask: None,
                filters: Vec::new(),
                content: Content::Group {
                    isolated: *isolated,
                    role: *role,
                    knockout: *knockout,
                },
            };
            add(document, group, Some(positions[0]))?;
            for id in ids {
                let i = index(document, id)?;
                document.items[i].parent = Some(new_id.clone());
            }
            Ok((new_id.clone(), "grouped"))
        }
        Operation::Ungroup { id } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            let group = document.items[i].clone();
            let Content::Group { isolated, .. } = group.content else {
                return Err(Error::new(
                    "INVALID_OPERATION",
                    "Ungroup requires a group or layer",
                ));
            };
            let children = scene::children(document, Some(id));
            if group.content.is_knockout()
                || group.parent.as_deref().is_some_and(|id| {
                    document.items[index(document, id).unwrap()]
                        .content
                        .is_knockout()
                })
                || group.opacity != 1.0
                || group.fill_opacity != 1.0
                || !group.coverage.is_smooth()
                || !group.effects.is_empty()
                || group.clip_to.is_some()
                || !group.filters.is_empty()
                || group.blend != BlendMode::Normal
                || group.clip.as_ref().is_some_and(|c| c.enabled)
                || group.mask.as_ref().is_some_and(|m| m.enabled)
                || group.artwork_mask.as_ref().is_some_and(|m| m.enabled)
                || (isolated
                    && children
                        .iter()
                        .any(|&c| scene::backdrop_dependent(document, c)))
            {
                return Err(Error::new(
                    "UNSUPPORTED",
                    "Ungroup would change group appearance; remove the group effect or isolation dependency first",
                ));
            }
            let mut detached = Vec::new();
            for &c in &children {
                let mut child = document.items[c].clone();
                child.parent = group.parent.clone();
                child.transform = geometry::multiply(group.transform, child.transform);
                child.visible &= group.visible;
                detached.push(child);
            }
            let removed: HashSet<_> = children.into_iter().chain(std::iter::once(i)).collect();
            let at = (0..i).filter(|j| !removed.contains(j)).count();
            document.items = document
                .items
                .iter()
                .enumerate()
                .filter(|(j, _)| !removed.contains(j))
                .map(|(_, item)| item.clone())
                .collect();
            document.items.splice(at..at, detached);
            Ok((id.clone(), "ungrouped"))
        }
        Operation::Reparent {
            id,
            parent,
            index: at,
        } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            let world = scene::world_transform(document, i)?;
            let parent_world = if let Some(parent) = parent {
                let p = index(document, parent)?;
                if scene::subtree(document, i).contains(&p) {
                    return Err(Error::new(
                        "INVALID_OPERATION",
                        "Cannot reparent into the same subtree",
                    ));
                }
                if !document.items[p].content.is_container() {
                    return Err(invalid("Parent must be a group, layer, frame or artboard"));
                }
                scene::check_unlocked(document, p, false)?;
                scene::world_transform(document, p)?
            } else {
                identity()
            };
            let mut item = document.items.remove(i);
            item.parent = parent.clone();
            item.transform = geometry::relative_transform(parent_world, &[world])?;
            add(document, item, *at)?;
            Ok((id.clone(), "reparented"))
        }
        Operation::GroupOptions {
            id,
            isolated,
            knockout,
        } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            let Content::Group {
                isolated: old,
                knockout: old_knockout,
                ..
            } = &mut document.items[i].content
            else {
                return Err(Error::new(
                    "INVALID_OPERATION",
                    "Group options require a group or layer",
                ));
            };
            *old = *isolated;
            if let Some(knockout) = knockout {
                *old_knockout = *knockout;
            }
            Ok((id.clone(), "group_options"))
        }
        Operation::SelectionSet { selection } => {
            document.selection = selection.clone();
            Ok((document.id.clone(), "pixel_selection"))
        }
        Operation::InkRecipe { recipe } => {
            document.ink_recipe = recipe.clone();
            Ok((document.id.clone(), "ink_recipe"))
        }
        Operation::ChannelPut {
            id,
            channel,
            replace_existing,
        } => {
            crate::channels::put(document, id, channel.clone(), *replace_existing)?;
            Ok((id.clone(), "channel"))
        }
        Operation::ChannelRemove { id } => {
            crate::channels::get(document, id)?;
            if document.ink_recipe.as_ref().is_some_and(|r| {
                r.inks
                    .iter()
                    .any(|i| i.channel == *id || i.mask_channel.as_ref() == Some(id))
            }) {
                return Err(Error::new(
                    "CHANNEL_IN_USE",
                    "A retained ink recipe still references this channel",
                ));
            }
            document.channels.remove(id);
            Ok((id.clone(), "channel_removed"))
        }
        Operation::ChannelCalculate {
            id,
            name,
            role,
            calculation,
            replace_existing,
        } => {
            crate::channels::check_destination(document, id, *replace_existing)?;
            let plane = crate::channels::calculate(document, calculation, asset_root, font_root)?;
            let channel = crate::channels::Channel {
                name: name.clone(),
                role: role.clone(),
                plane,
            };
            crate::channels::put(document, id, channel, *replace_existing)?;
            Ok((id.clone(), "channel"))
        }
        Operation::ChannelLoad { id, combine } => {
            let values = crate::render::unhex(&crate::channels::get(document, id)?.plane.gray_hex);
            crate::selections::combine_values(document, values, *combine)?;
            Ok((document.id.clone(), "pixel_selection"))
        }
        Operation::SelectionSample { method, combine } => {
            let values =
                crate::selection_analysis::evaluate(document, method, asset_root, font_root)?;
            crate::selections::combine_values(document, values, *combine)?;
            Ok((document.id.clone(), "pixel_selection"))
        }
        Operation::SelectionFill { selected } => {
            crate::selections::fill(document, *selected)?;
            Ok((document.id.clone(), "pixel_selection"))
        }
        Operation::SelectionShape {
            boundary,
            combine,
            antialias,
            fill_rule,
        } => {
            crate::selections::shape(document, boundary, *combine, *antialias, *fill_rule)?;
            Ok((document.id.clone(), "pixel_selection"))
        }
        Operation::SelectionInvert {} => {
            crate::selections::invert(document)?;
            Ok((document.id.clone(), "pixel_selection"))
        }
        Operation::SelectionRefine { mode, radius } => {
            crate::selections::refine(document, *mode, *radius)?;
            Ok((document.id.clone(), "pixel_selection"))
        }
        Operation::MaskFromSelection {
            id,
            linked,
            replace_existing,
        } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            crate::selections::to_mask(document, i, *linked, *replace_existing)?;
            Ok((id.clone(), "mask_from_selection"))
        }
        Operation::MaskApply { id } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            if !document.items[i].filters.is_empty()
                || !document.items[i].effects.is_empty()
                || !document.items[i].coverage.is_smooth()
            {
                return Err(Error::new(
                    "UNSUPPORTED",
                    "Applying an item mask before filters, layer effects or dissolve would change evaluation order; remove those controls first",
                ));
            }
            crate::masks::apply_pixels(document, i, asset_root).map_err(|e| e.at_item(id))?;
            Ok((id.clone(), "mask_applied_at_native_pixels"))
        }
        Operation::ArtworkMask { id, mask } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            document.items[i].artwork_mask = mask.clone();
            Ok((id.clone(), "artwork_mask"))
        }
        Operation::ArtworkMaskLink { id, linked } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            let world = scene::world_transform(document, i)?;
            let mask = document.items[i]
                .artwork_mask
                .as_mut()
                .ok_or_else(|| Error::new("INVALID_OPERATION", "Item has no artwork mask"))?;
            if mask.linked != *linked {
                mask.transform = if *linked {
                    geometry::relative_transform(world, &[mask.transform])?
                } else {
                    geometry::relative_transform(identity(), &[world, mask.transform])?
                };
                mask.linked = *linked;
            }
            Ok((id.clone(), "artwork_mask_link"))
        }
        Operation::ArtworkMaskTransform { id, matrix, space } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            geometry::validate_matrix(*matrix)?;
            let world = scene::world_transform(document, i)?;
            let mask = document.items[i]
                .artwork_mask
                .as_mut()
                .ok_or_else(|| Error::new("INVALID_OPERATION", "Item has no artwork mask"))?;
            mask.transform = match space {
                TransformSpace::Replace => *matrix,
                TransformSpace::Local => {
                    geometry::relative_transform(identity(), &[mask.transform, *matrix])?
                }
                TransformSpace::World => {
                    if mask.linked {
                        geometry::relative_transform(world, &[*matrix, world, mask.transform])?
                    } else {
                        geometry::relative_transform(identity(), &[*matrix, mask.transform])?
                    }
                }
            };
            Ok((id.clone(), "artwork_mask_transform"))
        }
        Operation::Mask { id, mask } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            document.items[i].mask = mask.clone();
            Ok((id.clone(), "mask"))
        }
        Operation::MaskLink { id, linked } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            let world = scene::world_transform(document, i)?;
            let mask = document.items[i]
                .mask
                .as_mut()
                .ok_or_else(|| Error::new("INVALID_OPERATION", "Item has no opacity mask"))?;
            if mask.linked != *linked {
                mask.transform = if *linked {
                    geometry::relative_transform(world, &[mask.transform])?
                } else {
                    geometry::relative_transform(identity(), &[world, mask.transform])?
                };
                mask.linked = *linked;
            }
            Ok((id.clone(), "mask_link"))
        }
        Operation::MaskTransform { id, matrix, space } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            geometry::validate_matrix(*matrix)?;
            let world = scene::world_transform(document, i)?;
            let mask = document.items[i]
                .mask
                .as_mut()
                .ok_or_else(|| Error::new("INVALID_OPERATION", "Item has no opacity mask"))?;
            mask.transform = match space {
                TransformSpace::Replace => *matrix,
                TransformSpace::Local => {
                    geometry::relative_transform(identity(), &[mask.transform, *matrix])?
                }
                TransformSpace::World => {
                    if mask.linked {
                        geometry::relative_transform(world, &[*matrix, world, mask.transform])?
                    } else {
                        geometry::relative_transform(identity(), &[*matrix, mask.transform])?
                    }
                }
            };
            Ok((id.clone(), "mask_transform"))
        }
        Operation::Clip { id, clip } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            document.items[i].clip = clip.clone();
            Ok((id.clone(), "clip"))
        }
        Operation::Align {
            ids,
            axis,
            anchor,
            reference,
        } => {
            layout::align(document, ids, *axis, *anchor, reference)?;
            Ok((document.id.clone(), "aligned"))
        }
        Operation::Distribute {
            ids,
            axis,
            mode,
            reference,
        } => {
            layout::distribute(document, ids, *axis, *mode, reference)?;
            Ok((document.id.clone(), "distributed"))
        }
        Operation::Reorder { id, index: at } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            if *at >= scene::children(document, document.items[i].parent.as_deref()).len() {
                return Err(Error::new(
                    "INVALID_OPERATION",
                    "Stack index must identify a final item position",
                ));
            }
            let item = document.items.remove(i);
            let at = scene::insertion(document, item.parent.as_deref(), Some(*at))?;
            document.items.insert(at, item);
            Ok((id.clone(), "reordered"))
        }
        Operation::Properties {
            id,
            name,
            visible,
            locked,
            opacity,
            fill_opacity,
            coverage,
            blend,
        } => {
            let i = index(document, id)?;
            let unlock_only = *locked == Some(false)
                && name.is_none()
                && visible.is_none()
                && opacity.is_none()
                && fill_opacity.is_none()
                && coverage.is_none()
                && blend.is_none();
            if unlock_only {
                if scene::ancestors(document, i)?
                    .iter()
                    .any(|&p| document.items[p].locked)
                {
                    return Err(Error::new(
                        "LOCKED",
                        "Cannot unlock through a locked ancestor",
                    ));
                }
            } else {
                unlocked(document, i)?;
            }
            let item = &mut document.items[i];
            if let Some(value) = name {
                item.name = value.clone();
            }
            if let Some(value) = visible {
                item.visible = *value;
            }
            if let Some(value) = locked {
                item.locked = *value;
            }
            if let Some(value) = opacity {
                item.opacity = *value;
            }
            if let Some(value) = fill_opacity {
                item.fill_opacity = *value;
            }
            if let Some(value) = coverage {
                item.coverage = *value;
            }
            if let Some(value) = blend {
                item.blend = *value;
            }
            Ok((id.clone(), "properties"))
        }
        Operation::Metadata { id, value } => {
            if let Some(record) = value {
                crate::metadata::validate(record)?;
            }
            let target = if let Some(id) = id {
                let i = index(document, id)?;
                unlocked(document, i)?;
                document.items[i].metadata = value.clone();
                id.clone()
            } else {
                document.metadata = value.clone();
                document.id.clone()
            };
            Ok((target, "metadata"))
        }
        Operation::MeshKnot {
            id,
            target,
            column,
            row,
            color,
            offset,
        } => {
            crate::meshes::knot_edit(document, id, *target, *column, *row, *color, *offset)?;
            Ok((id.clone(), "mesh_knot"))
        }
        Operation::GlobalLight { light } => {
            crate::effects::set_light(document, *light)?;
            Ok((document.id.clone(), "global_light"))
        }
        Operation::OutputProfile { profile } => {
            if let Some(profile) = profile {
                crate::profiles::validate_destination(profile)?;
            }
            document.output_profile = profile.clone();
            Ok((document.id.clone(), "output_profile"))
        }
        Operation::EffectsScale { ids, factor } => {
            if !factor.is_finite() || !(0.001..=1024.0).contains(factor) {
                return Err(Error::new(
                    "INVALID_OPERATION",
                    "Effect scale factor must be in 0.001..=1024",
                ));
            }
            let selected = scene::selection(document, ids, false)?;
            for &i in &selected {
                unlocked(document, i)?;
            }
            for i in selected {
                for effect in &mut document.items[i].effects {
                    effect.scale *= factor;
                }
            }
            Ok((document.id.clone(), "effects_scaled"))
        }
        Operation::Effects { id, effects } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            document.items[i].effects = effects.clone();
            Ok((id.clone(), "effects"))
        }
        Operation::Transform {
            id,
            matrix,
            space,
            anchor,
        } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            geometry::validate_matrix(*matrix)?;
            let mut factors = if let Some([x, y]) = anchor {
                if !x.is_finite()
                    || !y.is_finite()
                    || x.abs() > MAX_COORDINATE
                    || y.abs() > MAX_COORDINATE
                {
                    return Err(invalid(
                        "Transform anchor must be finite and within coordinate limits",
                    ));
                }
                vec![
                    [1.0, 0.0, 0.0, 1.0, *x, *y],
                    *matrix,
                    [1.0, 0.0, 0.0, 1.0, -x, -y],
                ]
            } else {
                vec![*matrix]
            };
            let old = document.items[i].transform;
            document.items[i].transform = match space {
                TransformSpace::Replace => geometry::relative_transform(identity(), &factors)?,
                TransformSpace::World => {
                    let parent = scene::parent_transform(document, i)?;
                    factors.extend([parent, old]);
                    geometry::relative_transform(parent, &factors)?
                }
                TransformSpace::Local => {
                    factors.insert(0, old);
                    geometry::relative_transform(identity(), &factors)?
                }
            };
            Ok((id.clone(), "transformed"))
        }
        Operation::Vector {
            id,
            geometry,
            fill,
            stroke,
            fill_rule,
        } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            if !matches!(document.items[i].content, Content::Vector { .. }) {
                return Err(Error::new(
                    "INVALID_OPERATION",
                    "Vector edits require a vector item",
                ));
            }
            document.items[i].content = Content::Vector {
                geometry: geometry.clone(),
                fill: fill.clone(),
                stroke: stroke.clone(),
                fill_rule: *fill_rule,
            };
            Ok((id.clone(), "geometry"))
        }
        Operation::Fill { id, paint, dither } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            let Content::Fill {
                paint: old,
                dither: old_dither,
                ..
            } = &mut document.items[i].content
            else {
                return Err(Error::new(
                    "INVALID_OPERATION",
                    "Fill paint editing requires a procedural fill layer",
                ));
            };
            *old = paint.clone();
            *old_dither = *dither;
            Ok((id.clone(), "fill"))
        }
        Operation::PixelFill { id, rect, color } => {
            let i = index(document, id)?;
            unlocked(document, i)?;
            let Content::Raster {
                width,
                height,
                rgba_hex,
                ..
            } = &mut document.items[i].content
            else {
                return Err(Error::new(
                    "INVALID_OPERATION",
                    "Pixel fill requires a pixel layer",
                ));
            };
            if rect.width == 0
                || rect.height == 0
                || rect.x as u64 + rect.width as u64 > *width as u64
                || rect.y as u64 + rect.height as u64 > *height as u64
            {
                return Err(Error::new(
                    "INVALID_OPERATION",
                    "Fill rectangle must be nonempty and wholly inside the pixel layer",
                ));
            }
            let row = crate::render::hex(color).repeat(rect.width as usize);
            for y in rect.y..rect.y + rect.height {
                let start = (y as usize * *width as usize + rect.x as usize) * 8;
                rgba_hex.replace_range(start..start + row.len(), &row);
            }
            Ok((id.clone(), "pixels"))
        }
    }
}
