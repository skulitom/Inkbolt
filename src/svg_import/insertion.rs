//! SVG authoring through the same atomic edit path as ordinary object edits.
use super::*;
use serde::Serialize;
use std::collections::BTreeSet;
use std::path::Path;

fn normal_weight() -> u16 {
    400
}

/// A CSS family selector bound to an existing, content-pinned document font.
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct InsertFontBinding {
    pub family: String,
    pub font_id: String,
    #[serde(default = "normal_weight")]
    pub weight: u16,
    #[serde(default)]
    pub style: FaceStyle,
}

fn prefix(
    document: &Document,
    source: &Document,
    requested: Option<&str>,
) -> Result<String, Error> {
    if let Some(prefix) = requested {
        if !valid_id(prefix) || prefix.len() > crate::limits::transfer::MAX_PREFIX_BYTES {
            return Err(Error::new(
                "INVALID_REQUEST",
                "SVG insertion prefix must be a valid bounded item-ID prefix",
            ));
        }
        return Ok(prefix.to_owned());
    }
    let used: BTreeSet<_> = document.items.iter().map(|item| item.id.as_str()).collect();
    // Each failed candidate consumes at least one distinct existing item ID.
    // Source IDs are the importer's short deterministic IDs, not raw XML IDs.
    for index in 1..=document.items.len() + 1 {
        let prefix = format!("svg-{index}");
        if source
            .items
            .iter()
            .all(|item| !used.contains(format!("{prefix}-{}", item.id).as_str()))
        {
            return Ok(prefix);
        }
    }
    Err(invalid("Unable to reserve SVG insertion IDs"))
}

/// Called only on the editor's private candidate. Any later failure discards it.
pub(crate) fn insert(
    document: &mut Document,
    svg: &str,
    parent: Option<&str>,
    requested_prefix: Option<&str>,
    font_bindings: &[InsertFontBinding],
    font_root: Option<&Path>,
    control: &crate::control::Control,
) -> Result<Value, Error> {
    control.check()?;
    if svg.len() > crate::MAX_REQUEST_BYTES as usize {
        return Err(Error::new(
            "RESOURCE_LIMIT",
            "Inserted SVG exceeds the request byte ceiling",
        ));
    }
    if font_bindings.len() > crate::fonts::MAX_FONTS {
        return Err(Error::new(
            "RESOURCE_LIMIT",
            "SVG font binding limit exceeded",
        ));
    }
    if let Some(parent) = parent {
        let index = crate::scene::index(document, parent)?;
        if !document.items[index].content.is_container() {
            return Err(Error::new(
                "INVALID_REQUEST",
                "SVG insertion parent must be a container",
            ));
        }
        crate::scene::check_unlocked(document, index, false)?;
    }
    let bindings = font_bindings
        .iter()
        .map(|binding| {
            let font = document.fonts.get(&binding.font_id).ok_or_else(|| {
                Error::new(
                    "SVG_FONT_NOT_BOUND",
                    "SVG insertion font ID is absent from the destination",
                )
                .at_font(&binding.font_id)
            })?;
            Ok(FontBinding {
                family: binding.family.clone(),
                font_id: binding.font_id.clone(),
                font: font.clone(),
                weight: binding.weight,
                style: binding.style,
            })
        })
        .collect::<Result<Vec<_>, Error>>()?;

    let profile = if document.resource_profile.is_standard() {
        ResourceProfile::Standard
    } else {
        ResourceProfile::LargeVector
    };
    let max_nodes = if profile.is_standard() {
        MAX_NODES
    } else {
        MAX_LARGE_NODES
    };
    // Parse only within the existing node/DTD bounds. A fragment with several
    // roots fails this probe, then goes through the ordinary wrapped importer.
    let full_svg = roxmltree::Document::parse_with_options(
        svg,
        roxmltree::ParsingOptions {
            allow_dtd: false,
            nodes_limit: max_nodes,
            entity_resolver: None,
        },
    )
    .is_ok_and(|xml| xml.root_element().tag_name().name() == "svg");
    let [width, height] = crate::vector_canvas::logical_size(document);
    let (text, offset) = if full_svg {
        (svg.to_owned(), 0)
    } else {
        let opening = format!("<svg xmlns=\"{NS}\" width=\"{width}\" height=\"{height}\">");
        let offset = opening.len();
        (format!("{opening}{svg}</svg>"), offset)
    };
    let byte_budget =
        crate::MAX_REQUEST_BYTES as usize + offset + if full_svg { 0 } else { "</svg>".len() };
    let mut imported = import_with_budget(
        "svg-insertion".into(),
        Source::Text { text },
        bindings,
        font_root.map(Path::to_owned),
        profile,
        control,
        Some(byte_budget),
    )?;
    let mut source: Document = serde_json::from_value(imported["document"].take())
        .map_err(|e| Error::new("SERIALIZATION", e.to_string()))?;
    // The import remains a valid sRGB vector document. Insertion carries its
    // encoded paints into the destination, whose ordinary edit validation and
    // compositing rules apply (including supported raster HDR destinations).
    if source.metadata.is_some() {
        imported["losses"].as_array_mut().unwrap().push(json!(
            "Insertion retains imported item metadata but excludes source document metadata; destination document metadata is unchanged."
        ));
    }
    let root = if full_svg {
        // Standalone SVG import clips at its canvas. Retain that viewport in
        // an outer group so the original root's own clip remains independent.
        let [width, height] = crate::vector_canvas::logical_size(&source);
        let wrapper: Item = serde_json::from_value(json!({"id":"svg-viewport",
            "content":{"type":"group"},"clip":{"geometry":{"shape":"rect",
            "x":0.0,"y":0.0,"width":width,"height":height}}}))
        .map_err(|e| Error::new("SERIALIZATION", e.to_string()))?;
        source.items[0].parent = Some(wrapper.id.clone());
        let id = wrapper.id.clone();
        source.items.insert(0, wrapper);
        id
    } else {
        "svg-0".to_owned()
    };
    let prefix = prefix(document, &source, requested_prefix)?;
    let roots = source
        .items
        .iter()
        .filter(|item| item.parent.is_none())
        .map(|item| item.id.clone())
        .collect();
    let transferred = crate::transfer::insert_svg(
        document,
        &crate::transfer::Transfer {
            source: Box::new(source),
            ids: roots,
            prefix: prefix.clone(),
            parent: parent.map(str::to_owned),
            verify_resources: false,
        },
        font_root,
        control,
    )?;
    let ids = &transferred["item_ids"];
    for section in ["mapping", "definitions", "approximations"] {
        if let Some(rows) = imported[section].as_array_mut() {
            for row in rows {
                if let Some(id) = row["item_id"].as_str() {
                    row["item_id"] = ids[id].clone();
                }
                if let Some(position) = row["byte_offset"].as_u64() {
                    row["byte_offset"] = json!(position.checked_sub(offset as u64));
                    if position < offset as u64 {
                        row["synthetic"] = json!(true);
                    }
                }
            }
        }
    }
    Ok(json!({"root_id":ids[&root],"prefix":prefix,"item_ids":ids,
        "font_ids":transferred["font_ids"],"mapping":imported["mapping"],
        "definitions":imported["definitions"],"approximations":imported["approximations"],
        "losses":imported["losses"],"placement":"parent_local",
        "source":{"sha256":crate::assets::sha256(svg.as_bytes()),"bytes":svg.len(),
            "kind":if full_svg { "svg_document" } else { "svg_fragment" }},
        "viewport_clipped":full_svg,"fonts":"existing_destination_bindings",
        "compositing":"destination_working_space"}))
}
