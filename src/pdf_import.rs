//! Editable page graphics from a bounded classic-xref PDF.
mod color;
mod drawing;
mod image;
mod program;

use crate::{
    Document, Error,
    control::Control,
    limits::vector_native_pdf_read as bounds,
    model::ResourceProfile,
    vector_native::{
        self,
        pdf_read::{Container, Id, Value, field},
    },
};
use serde_json::json;
use std::{
    collections::{BTreeMap, BTreeSet},
    path::Path,
};

type Dict = BTreeMap<Vec<u8>, Value>;

fn invalid(message: &str) -> Error {
    Error::new("INVALID_PDF", message)
}
fn unsupported(message: &str) -> Error {
    Error::new("UNSUPPORTED", message)
}
fn limit(message: &str) -> Error {
    Error::new("RESOURCE_LIMIT", message)
}

fn reference(value: &Value) -> Result<Id, Error> {
    match value {
        Value::Ref(id) => Ok(*id),
        _ => Err(invalid("Expected an indirect PDF object")),
    }
}

fn allowed(dict: &Dict, names: &[&[u8]]) -> Result<(), Error> {
    if let Some(key) = dict.keys().find(|k| !names.contains(&k.as_slice())) {
        return Err(unsupported(&format!(
            "Unsupported PDF field /{}",
            String::from_utf8_lossy(key)
        )));
    }
    Ok(())
}

fn number(value: &Value) -> Result<f64, Error> {
    match value {
        Value::Integer(v) => Ok(*v as f64),
        Value::Real(v) => Ok(*v),
        _ => Err(invalid("Expected a finite PDF number")),
    }
}
fn numbers<const N: usize>(pdf: &Container, value: &Value) -> Result<[f64; N], Error> {
    let Value::Array(values) = pdf.resolve(value)? else {
        return Err(invalid("Expected a PDF array"));
    };
    if values.len() != N {
        return Err(invalid("Unexpected PDF array length"));
    }
    let mut result = [0.; N];
    for (v, out) in values.iter().zip(&mut result) {
        *out = number(pdf.resolve(v)?)?;
    }
    Ok(result)
}
fn rect(pdf: &Container, value: &Value) -> Result<[f64; 4], Error> {
    let b = numbers(pdf, value)?;
    if b[0] >= b[2] || b[1] >= b[3] {
        return Err(unsupported(
            "PDF rectangle requires positive ordered extents",
        ));
    }
    Ok(b)
}

fn located(mut e: Error, page: usize, id: Id, offset: Option<usize>) -> Error {
    if e.details.is_none() {
        e.details = Some(Box::new(
            json!({"page_index":page,"object":id.0,"generation":id.1,"decoded_byte_offset":offset}),
        ));
    }
    e
}

struct PageTree<'a> {
    seen: BTreeSet<Id>,
    pages: Vec<(Id, Vec<&'a Dict>)>,
}
impl<'a> PageTree<'a> {
    fn walk(
        &mut self,
        pdf: &'a Container,
        node: &'a Value,
        parent: Option<Id>,
        ancestors: &mut Vec<&'a Dict>,
    ) -> Result<(), Error> {
        let id = reference(node)?;
        if ancestors.len() >= bounds::MAX_DEPTH {
            return Err(limit("PDF page tree depth exceeded"));
        }
        if !self.seen.insert(id) {
            return Err(invalid("Repeated PDF page tree object"));
        }
        let dict = pdf.resolve(node)?.dict()?;
        if dict.get(b"Parent".as_slice()).map(reference).transpose()? != parent {
            return Err(invalid("Invalid PDF page parent"));
        }
        ancestors.push(dict);
        let kind = field(dict, b"Type")?;
        if kind.named(b"Page") {
            if self.pages.len() >= bounds::MAX_PAGES {
                return Err(limit("PDF page limit exceeded"));
            }
            self.pages.push((id, ancestors.clone()));
        } else if kind.named(b"Pages") {
            let Value::Array(kids) = pdf.resolve(field(dict, b"Kids")?)? else {
                return Err(invalid("Expected PDF page children"));
            };
            let before = self.pages.len();
            for child in kids {
                self.walk(pdf, child, Some(id), ancestors)?;
            }
            if pdf.resolve(field(dict, b"Count")?)?.integer()? != self.pages.len() - before {
                return Err(invalid("PDF page count disagrees with page tree"));
            }
        } else {
            return Err(invalid("Expected a PDF page tree node"));
        }
        ancestors.pop();
        Ok(())
    }
}

pub fn import(
    id: String,
    source_path: &Path,
    page_index: usize,
    _color_policy: vector_native::ColorPolicy,
    profile: ResourceProfile,
    control: &Control,
) -> Result<serde_json::Value, Error> {
    control.check()?;
    control.check_path(source_path)?;
    if !crate::model::valid_id(&id) || profile == ResourceProfile::LargeRaster {
        return Err(Error::new(
            "INVALID_REQUEST",
            "PDF import requires a valid document ID and a vector profile",
        ));
    }
    if !std::fs::metadata(source_path).is_ok_and(|m| m.is_file()) {
        return Err(Error::new(
            "IO_ERROR",
            "PDF source must be a readable regular file",
        ));
    }
    let bytes = crate::assets::read_bounded(source_path, vector_native::MAX_SOURCE_BYTES as u64)?;
    let pdf = Container::read_for_page_import(&bytes, control)?;
    let catalog = pdf.catalog()?;
    allowed(
        catalog,
        &[
            b"Type",
            b"Pages",
            b"Version",
            b"Metadata",
            b"Lang",
            b"PageMode",
            b"PageLayout",
            b"ViewerPreferences",
        ],
    )?;
    let mut tree = PageTree {
        seen: BTreeSet::new(),
        pages: Vec::new(),
    };
    tree.walk(&pdf, field(catalog, b"Pages")?, None, &mut Vec::new())?;
    let (page_id, lineage) = tree.pages.get(page_index).ok_or_else(|| {
        Error::new(
            "INVALID_REQUEST",
            format!(
                "Page index {page_index} is outside the {}-page PDF",
                tree.pages.len()
            ),
        )
    })?;
    let mut result = read_page(&pdf, lineage, id, page_index, profile, control)
        .map_err(|e| located(e, page_index, *page_id, None))?;
    result["source"] = json!({"sha256":crate::assets::sha256(&bytes),"bytes":bytes.len(),"page_index":page_index,"pages":tree.pages.len(),"modified":false});
    if let Some(generation) = pdf.nonstandard_free_head_generation {
        result["source"]["free_head_generation"] = json!(generation);
    }
    control.check()?;
    Ok(result)
}

fn read_page(
    pdf: &Container,
    lineage: &[&Dict],
    id: String,
    page_index: usize,
    profile: ResourceProfile,
    control: &Control,
) -> Result<serde_json::Value, Error> {
    let (&page, parents) = lineage.split_last().unwrap();
    for dict in parents {
        allowed(
            dict,
            &[
                b"Type",
                b"Kids",
                b"Count",
                b"Parent",
                b"MediaBox",
                b"CropBox",
                b"Rotate",
                b"Resources",
            ],
        )?;
    }
    allowed(
        page,
        &[
            b"Type",
            b"Parent",
            b"MediaBox",
            b"CropBox",
            b"BleedBox",
            b"TrimBox",
            b"ArtBox",
            b"Rotate",
            b"Resources",
            b"Contents",
            b"Group",
            b"UserUnit",
            b"Metadata",
        ],
    )?;
    let inherit = |key: &[u8]| lineage.iter().rev().find_map(|d| d.get(key));
    let media = rect(
        pdf,
        inherit(b"MediaBox").ok_or_else(|| invalid("PDF page needs a media box"))?,
    )?;
    let crop = inherit(b"CropBox")
        .map(|v| rect(pdf, v))
        .transpose()?
        .unwrap_or(media);
    let view = [
        crop[0].max(media[0]),
        crop[1].max(media[1]),
        crop[2].min(media[2]),
        crop[3].min(media[3]),
    ];
    let unit = page
        .get(b"UserUnit".as_slice())
        .map(|v| number(pdf.resolve(v)?))
        .transpose()?
        .unwrap_or(1.);
    if !(unit > 0. && unit <= crate::limits::pdf::MAX_USER_UNIT as f64)
        || view[0] >= view[2]
        || view[1] >= view[3]
    {
        return Err(invalid("Invalid PDF page units or crop intersection"));
    }
    let rotate = match inherit(b"Rotate").map(|v| pdf.resolve(v)).transpose()? {
        None => 0,
        Some(Value::Integer(v)) if v % 90 == 0 => v.rem_euclid(360),
        _ => {
            return Err(invalid(
                "Page rotation must be an integer multiple of 90 degrees",
            ));
        }
    };
    let [l, b, r, t] = view.map(|p| p * unit);
    let matrix = match rotate {
        0 => [unit, 0., 0., -unit, -l, t],
        90 => [0., unit, unit, 0., -b, -l],
        180 => [-unit, 0., 0., unit, r, -b],
        _ => [0., -unit, -unit, 0., t, r],
    };
    let size = if rotate % 180 == 0 {
        [r - l, t - b]
    } else {
        [t - b, r - l]
    };
    let canvas = crate::vector_canvas::Canvas {
        origin_px: [0.; 2],
        size_px: size,
        unit: crate::dimensions::Unit::Pt,
        process_space: Default::default(),
    };
    let [width, height] = canvas.dimensions()?;
    if let Some(v) = page.get(b"Group".as_slice()) {
        drawing::group(pdf, v)?;
    }
    let empty = Dict::new();
    let resources = inherit(b"Resources")
        .map(|v| pdf.resolve(v)?.dict())
        .transpose()?
        .unwrap_or(&empty);
    let mut drawing = drawing::Drawing::new(pdf, page_index, size, profile, control);
    drawing.page(page.get(b"Contents".as_slice()), resources, matrix)?;
    let mut document: Document = serde_json::from_value(
        json!({"schema_version":2,"id":id,"kind":"vector","color_space":"srgb","resolution_ppi":72,
        "width":width,"height":height,"vector_canvas":canvas,"resource_profile":profile}),
    )
    .map_err(|e| invalid(&e.to_string()))?;
    document.items = drawing.items;
    document.assets = drawing.images.assets;
    crate::model::validate_controlled(&document, control)?;
    if serde_json::to_vec(&document)
        .map_err(|e| invalid(&e.to_string()))?
        .len()
        > profile.bytes()
    {
        return Err(limit("Recovered PDF exceeds editable snapshot budget"));
    }
    let mut boxes = json!({"media":media,"crop":crop});
    for (key, label) in [
        (b"TrimBox".as_slice(), "trim"),
        (b"BleedBox", "bleed"),
        (b"ArtBox", "art"),
    ] {
        if let Some(v) = page.get(key) {
            boxes[label] = json!(rect(pdf, v)?);
        }
    }
    let mut losses = vec![
        "Painted geometry is recovered as editable paths with new item IDs. Original shape types, names, stroke construction and authoring history cannot be inferred.",
        "Selected page artwork is placed in physical points. Page boxes are returned as source coordinates. Metadata and other pages stay in the source file.",
    ];
    if drawing.used_indexed_fill {
        losses.push("Indexed PDF fills retain the selected colors. The original palette and its indices remain in the source PDF.");
    }
    if !drawing.images.sources.is_empty() {
        losses.push("Image samples and soft-mask alpha are normalized into straight RGBA8 PNG assets. Original image streams, packing and compression remain in the source PDF.");
    }
    if drawing
        .images
        .sources
        .values()
        .any(|s| s.get("palette_entries").is_some() || s.get("color_key").is_some())
    {
        losses.push("Image palettes and color keys are expanded into straight RGBA8 samples. Their original tables, indices and mask ranges remain in the source PDF.");
    }
    let mut result = json!({"document":document,"mapping":drawing.mapping,"page":{"boxes":boxes,"user_unit":unit,"rotation":rotate,"source_to_document":matrix},
        "color_policy":"caller_declared_encoded_srgb","losses":losses});
    if !drawing.images.sources.is_empty() {
        result["image_sources"] = json!(drawing.images.sources);
    }
    Ok(result)
}
