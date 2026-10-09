//! Versioned, pure starting documents and explicit delivery settings.
use crate::{Error, ExportFormat, boards, control::Control, model::*, pdf, render_quality};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

pub const VERSION: u32 = 1;

#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema)]
#[schemars(rename = "PresetScreenSize")]
#[serde(rename_all = "snake_case")]
pub enum ScreenSize {
    Icon256,
    PresentationHd,
    PresentationQhd,
    SocialSquare,
    SocialPortrait,
    SocialStory,
}
impl ScreenSize {
    pub const ALL: [Self; 6] = [
        Self::Icon256,
        Self::PresentationHd,
        Self::PresentationQhd,
        Self::SocialSquare,
        Self::SocialPortrait,
        Self::SocialStory,
    ];
    pub fn dimensions(self) -> [u32; 2] {
        match self {
            Self::Icon256 => [256, 256],
            Self::PresentationHd => [1920, 1080],
            Self::PresentationQhd => [2560, 1440],
            Self::SocialSquare => [1080, 1080],
            Self::SocialPortrait => [1080, 1350],
            Self::SocialStory => [1080, 1920],
        }
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema)]
#[schemars(rename = "PresetBackground")]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Background {
    Transparent {},
    Solid { color: [u8; 3] },
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema)]
#[schemars(rename = "PresetPaper")]
#[serde(rename_all = "snake_case")]
pub enum Paper {
    A4,
    A5,
    Letter,
}
impl Paper {
    pub const ALL: [Self; 3] = [Self::A4, Self::A5, Self::Letter];
    fn size(self) -> ([f64; 2], crate::dimensions::Unit) {
        match self {
            Self::A4 => ([210.0, 297.0], crate::dimensions::Unit::Mm),
            Self::A5 => ([148.0, 210.0], crate::dimensions::Unit::Mm),
            Self::Letter => ([8.5, 11.0], crate::dimensions::Unit::In),
        }
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema)]
#[schemars(rename = "PresetOrientation")]
#[serde(rename_all = "snake_case")]
pub enum Orientation {
    Portrait,
    Landscape,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema)]
#[schemars(rename = "PresetPrintColor")]
#[serde(rename_all = "snake_case")]
pub enum PrintColor {
    DisplayRgb,
    NativeInks,
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[schemars(rename = "PresetSpec")]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Spec {
    Screen {
        size: ScreenSize,
        kind: DocumentKind,
        background: Background,
        #[serde(default)]
        resource_profile: ResourceProfile,
    },
    PrintPage {
        paper: Paper,
        orientation: Orientation,
        /// One of 72, 96, 150 or 300. Physical trim size is independent of sampling density.
        resolution_ppi: u32,
        color: PrintColor,
        /// Exact logical pixels at the selected resolution, never rounded millimetres.
        #[serde(default)]
        bleed_px: boards::Insets,
        #[serde(default)]
        resource_profile: ResourceProfile,
    },
}

/// Add only output_root and file_name to use with document/session.publish or preflight.
#[derive(Clone, Debug, Serialize)]
pub struct Delivery {
    pub format: ExportFormat,
    pub scale: u32,
    pub artboard_id: Option<String>,
    pub include_bleed: bool,
    pub metadata_policy: crate::metadata::Policy,
    pub render_options: Option<render_quality::Options>,
    pub pdf_options: Option<pdf::Options>,
}

pub fn catalog() -> Value {
    json!({"version":VERSION,"commands":["preset.list","preset.create"],
        "schema":"schema.lookup preset.create",
        "screen":ScreenSize::ALL.map(|size|json!({"size":size,"pixels":size.dimensions()})),
        "print":Paper::ALL.map(|paper|{let(size,unit)=paper.size();json!({"paper":paper,"portrait_size":size,"unit":unit})}),
        "print_resolutions_ppi":[72,96,150,300],"print_orientations":["portrait","landscape"],
        "screen_color":"sRGB RGBA8 PNG; explicit transparent or solid artboard background",
        "print_color":["display_rgb","native_inks"],"print_output_profile":"none selected; configure a supplied profile explicitly for calibrated delivery",
        "bleed":"integer logical pixels per edge; physical size is reported without rounding",
        "metadata":"strip for delivery; editable source remains intact",
        "writes_files":false,"mutates_existing_documents":false,
        "limits":"Ordinary document, rendering and export limits still apply; preflight the edited document.",
        "versioning":"Version 1 dimensions and defaults are fixed. Unknown versions fail; retain the returned specification and delivery settings."})
}

pub fn create(id: String, version: u32, spec: Spec, control: &Control) -> Result<Value, Error> {
    control.check()?;
    if version != VERSION {
        return Err(Error::new(
            "UNSUPPORTED",
            "Unsupported preset version; use preset.list",
        ));
    }
    let (kind, resource_profile) = match &spec {
        Spec::Screen {
            kind,
            resource_profile,
            ..
        } => (kind.clone(), *resource_profile),
        Spec::PrintPage {
            resource_profile, ..
        } => (DocumentKind::Vector, *resource_profile),
    };
    let mut document = Document {
        schema_version: 2,
        id,
        kind,
        resource_profile,
        width: 1,
        height: 1,
        color_space: ColorSpace::Srgb,
        revision: 0,
        resolution_ppi: 96.0,
        vector_canvas: None,
        stories: Default::default(),
        swatches: Default::default(),
        background: None,
        metadata: None,
        output_profile: None,
        variants: None,
        global_light: Default::default(),
        items: vec![],
        assets: Default::default(),
        fonts: Default::default(),
        selection: None,
        channels: Default::default(),
        ink_recipe: None,
    };
    let mut delivery = Delivery {
        format: ExportFormat::Png,
        scale: 1,
        artboard_id: Some("canvas".into()),
        include_bleed: false,
        metadata_policy: crate::metadata::Policy {
            mode: crate::metadata::Mode::Strip,
            ..Default::default()
        },
        render_options: Some(render_quality::Options {
            evaluation: render_quality::Evaluation::Tiled,
            ..Default::default()
        }),
        pdf_options: None,
    };
    let (parent_id, bleed, background, preview, physical) = match &spec {
        Spec::Screen {
            size, background, ..
        } => {
            [document.width, document.height] = size.dimensions();
            let background = match background {
                Background::Transparent {} => None,
                Background::Solid { color } => Some([color[0], color[1], color[2], 255]),
            };
            (
                "canvas",
                boards::Insets::default(),
                background,
                true,
                Value::Null,
            )
        }
        Spec::PrintPage {
            paper,
            orientation,
            resolution_ppi,
            color,
            bleed_px,
            ..
        } => {
            if ![72, 96, 150, 300].contains(resolution_ppi) {
                return Err(Error::new(
                    "INVALID_REQUEST",
                    "Preset resolution_ppi must be 72, 96, 150 or 300",
                ));
            }
            document.resolution_ppi = *resolution_ppi as f64;
            let (mut size, unit) = paper.size();
            if matches!(orientation, Orientation::Landscape) {
                size.swap(0, 1);
            }
            let native = matches!(color, PrintColor::NativeInks);
            crate::vector_canvas::apply(
                &mut document,
                &crate::vector_canvas::Action::Set {
                    origin: [0.0; 2],
                    size,
                    unit,
                    process_space: if native {
                        crate::vector_canvas::ProcessSpace::Cmyk
                    } else {
                        crate::vector_canvas::ProcessSpace::Rgb
                    },
                },
            )?;
            delivery.format = ExportFormat::Pdf;
            delivery.artboard_id = None;
            delivery.render_options = None;
            delivery.pdf_options = Some(pdf::Options {
                artboards: Some(boards::Selection::Ids {
                    ids: vec!["page".into()],
                }),
                include_bleed: *bleed_px != boards::Insets::default(),
                color: if native {
                    pdf::ColorDelivery::NativeInks
                } else {
                    pdf::ColorDelivery::Display
                },
                ..Default::default()
            });
            let inches_per_pixel = 1.0 / document.resolution_ppi;
            let physical = json!({"trim_size":size,"unit":unit,"bleed_order":["top","right","bottom","left"],
                "bleed_inches":([bleed_px.top,bleed_px.right,bleed_px.bottom,bleed_px.left].map(|v|v as f64*inches_per_pixel)),
                "output_profile":null,"calibrated":false});
            ("page", *bleed_px, None, !native, physical)
        }
    };
    let frame = boards::Frame {
        role: boards::Role::Artboard,
        width: document.width,
        height: document.height,
        logical_size: document.vector_canvas.map(|c| c.size_px),
        bleed,
        guides: vec![],
        background,
    };
    // Deserialize the fixed item shell through the same default contract as authored items.
    document.items.push(
        serde_json::from_value(json!({"id":parent_id,"name":parent_id,
        "content":{"type":"frame","frame":frame}}))
        .map_err(|_| Error::new("INVALID_REQUEST", "Unable to create preset artboard"))?,
    );
    crate::model::validate_controlled(&document, control)?;
    let settings = json!({"version":VERSION,"preset":spec});
    let specification_sha256 = crate::assets::sha256(
        &serde_json::to_vec(&settings)
            .map_err(|_| Error::new("INVALID_REQUEST", "Unable to encode preset specification"))?,
    );
    let document_sha256 = crate::assets::sha256(
        &serde_json::to_vec(&document)
            .map_err(|_| Error::new("INVALID_DOCUMENT", "Unable to encode preset document"))?,
    );
    let preview = preview.then(|| crate::previews::Options {
        focus: crate::previews::Focus::Artboard {
            id: parent_id.into(),
            include_bleed: false,
        },
        render_options: render_quality::Options {
            evaluation: render_quality::Evaluation::Tiled,
            ..Default::default()
        },
        ..Default::default()
    });
    control.check()?;
    Ok(
        json!({"specification":settings,"specification_sha256":specification_sha256,
        "document":document,"document_sha256":document_sha256,"content_parent_id":parent_id,
        "delivery":delivery,"preview":preview,"physical":physical,
        "preview_note":if preview.is_some(){"Trim preview; delivery can include explicitly requested bleed."}else{"Native ink pages require document.prepress with an explicit supplied profile for a calibrated preview."},
        "writes_files":false,"preflight_required":true}),
    )
}
