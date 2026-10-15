//! Original image admission: bounded immutable bytes, never an implicit store write.
use super::*;
use base64::Engine;
use serde::Serialize;
use std::{collections::HashMap, path::Path};

pub(super) const ATTRIBUTES: &[&str] =
    &["href", "x", "y", "width", "height", "preserveAspectRatio"];
fn default_policy() -> crate::assets::ColorPolicy {
    crate::assets::ColorPolicy::AssumeSrgb
}
fn default_sampling() -> crate::assets::Sampling {
    crate::assets::Sampling::Bilinear
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ImageOptions {
    #[serde(default)]
    pub source_root: Option<PathBuf>,
    #[serde(default = "default_policy")]
    pub color_policy: crate::assets::ColorPolicy,
    #[serde(default = "default_sampling")]
    pub sampling: crate::assets::Sampling,
}
impl Default for ImageOptions {
    fn default() -> Self {
        Self {
            source_root: None,
            color_policy: default_policy(),
            sampling: default_sampling(),
        }
    }
}
#[derive(Clone)]
struct Record {
    id: String,
    size: [f64; 2],
}
pub(super) struct Images {
    options: ImageOptions,
    hrefs: HashMap<String, Record>,
    sources: HashMap<String, Record>,
    bytes: usize,
    pixels: u64,
}

fn href<'a>(node: Node<'a, '_>) -> Result<&'a str, Error> {
    let current = node.attribute("href");
    let legacy = node.attribute(("http://www.w3.org/1999/xlink", "href"));
    if current.is_some() && legacy.is_some() && current != legacy {
        return Err(invalid("Conflicting image href and xlink:href"));
    }
    current
        .or(legacy)
        .filter(|v| !v.is_empty())
        .ok_or_else(|| invalid("SVG image requires href"))
}
fn unescape(value: &str) -> Result<Vec<u8>, Error> {
    let input = value.as_bytes();
    let mut out = Vec::with_capacity(input.len());
    let mut index = 0;
    while index < input.len() {
        if input[index] == b'%' {
            let pair = input
                .get(index + 1..index + 3)
                .ok_or_else(|| invalid("Incomplete image URI escape"))?;
            let digit = |b: u8| {
                (b as char)
                    .to_digit(16)
                    .ok_or_else(|| invalid("Invalid image URI escape"))
            };
            out.push((digit(pair[0])? * 16 + digit(pair[1])?) as u8);
            index += 3;
        } else {
            out.push(input[index]);
            index += 1;
        }
    }
    Ok(out)
}
fn local_name(value: &str) -> Result<String, Error> {
    let decoded =
        String::from_utf8(unescape(value)?).map_err(|_| invalid("Image path must be UTF-8"))?;
    if decoded.is_empty()
        || decoded
            .chars()
            .any(|c| c.is_control() || matches!(c, ':' | '\\' | '?' | '#'))
        || decoded
            .split('/')
            .any(|part| part.is_empty() || part == "." || part == "..")
    {
        return Err(unsupported(
            "SVG image requires a relative local path without escapes, query or fragment",
        ));
    }
    Ok(decoded)
}
fn data_parts(value: &str) -> Result<(&str, bool, &str), Error> {
    let (header, data) = value
        .strip_prefix("data:")
        .unwrap()
        .split_once(',')
        .ok_or_else(|| invalid("Image data URI requires a comma"))?;
    let (media, base64) = header
        .strip_suffix(";base64")
        .map(|v| (v, true))
        .unwrap_or((header, false));
    if !matches!(media, "image/png" | "image/jpeg") {
        return Err(unsupported("SVG images currently require PNG or JPEG data"));
    }
    Ok((media, base64, data))
}
fn coordinate(node: Node<'_, '_>, name: &str, basis: f64) -> Result<Option<f64>, Error> {
    node.attribute(name)
        .filter(|v| !matches!(name, "width" | "height") || v.trim() != "auto")
        .map(|v| {
            let resolved = definitions::Coordinate::parse(v)?.value(basis);
            if !resolved.is_finite() {
                return Err(invalid("Nonfinite SVG image coordinate"));
            }
            Ok(resolved)
        })
        .transpose()
}
pub(super) fn validate(node: Node<'_, '_>) -> Result<(), Error> {
    let value = href(node)?;
    if value.starts_with("data:") {
        data_parts(value)?;
    } else {
        local_name(value)?;
    }
    for name in ["x", "y", "width", "height"] {
        if let Some(value) = coordinate(node, name, 1.0)?
            && (!value.is_finite() || (matches!(name, "width" | "height") && value < 0.0))
        {
            return Err(invalid("Invalid SVG image position or dimensions"));
        }
    }
    viewports::mapping_from(node, [1.0, 1.0], Some([0.0, 0.0, 1.0, 1.0]))?;
    Ok(())
}
fn read_local(root: Option<&Path>, name: &str, cap: usize) -> Result<Vec<u8>, Error> {
    let root = root.ok_or_else(|| {
        Error::new(
            "SVG_IMAGE_ROOT_REQUIRED",
            "Local SVG images require images.source_root",
        )
    })?;
    crate::assets::absolute(root)?;
    let root = root
        .canonicalize()
        .map_err(|_| invalid("SVG image root is unavailable"))?;
    if !root.is_dir() {
        return Err(invalid("SVG image root must be a directory"));
    }
    let path = root
        .join(name)
        .canonicalize()
        .map_err(|_| invalid("Local SVG image is unavailable"))?;
    if !path.starts_with(&root) || !path.is_file() {
        return Err(unsupported(
            "SVG image must resolve to a regular file inside its explicit root",
        ));
    }
    crate::assets::read_bounded(&path, cap as u64)
}
impl Images {
    pub fn new(options: ImageOptions) -> Self {
        Self {
            options,
            hrefs: HashMap::new(),
            sources: HashMap::new(),
            bytes: 0,
            pixels: 0,
        }
    }
    pub fn validate_template(
        &mut self,
        node: Node<'_, '_>,
        document: &mut Document,
        losses: &mut Vec<String>,
    ) -> Result<(), Error> {
        self.load(node, document, losses).map(|_| ())
    }
    fn load(
        &mut self,
        node: Node<'_, '_>,
        document: &mut Document,
        losses: &mut Vec<String>,
    ) -> Result<Record, Error> {
        validate(node)?;
        let href = href(node)?;
        if let Some(record) = self.hrefs.get(href) {
            return Ok(record.clone());
        }
        let cap = (document.resource_profile.bytes() * 3 / 4)
            .min(crate::assets::MAX_IMPORT_BYTES as usize);
        let (bytes, media) = if href.starts_with("data:") {
            let (media, base64, data) = data_parts(href)?;
            let data = unescape(data)?;
            let bytes = if base64 {
                base64::engine::general_purpose::STANDARD
                    .decode(data)
                    .map_err(|_| invalid("Invalid image base64"))?
            } else {
                data
            };
            (bytes, Some(media))
        } else {
            (
                read_local(self.options.source_root.as_deref(), &local_name(href)?, cap)?,
                None,
            )
        };
        if bytes.len() > cap {
            return Err(Error::new(
                "RESOURCE_LIMIT",
                "Encoded SVG image cannot fit the snapshot byte limit",
            ));
        }
        let actual = if bytes.starts_with(b"\x89PNG\r\n\x1a\n") {
            "image/png"
        } else if bytes.starts_with(&[255, 216]) {
            "image/jpeg"
        } else {
            return Err(unsupported(
                "SVG images currently require PNG or JPEG bytes",
            ));
        };
        if media.is_some_and(|media| media != actual) {
            return Err(invalid("Image MIME type does not match its bytes"));
        }
        let hash = crate::assets::sha256(&bytes);
        if let Some(record) = self.sources.get(&hash) {
            self.hrefs.insert(href.to_owned(), record.clone());
            return Ok(record.clone());
        }
        let encoded_size = bytes.len().div_ceil(3) * 4;
        if self.bytes + encoded_size > document.resource_profile.bytes()
            || document.assets.len() >= crate::assets::MAX_ASSETS
        {
            return Err(Error::new(
                "RESOURCE_LIMIT",
                "SVG image resources exceed the document budget",
            ));
        }
        let imported = crate::assets::encoded(&bytes, self.options.color_policy)?;
        let count = imported.asset.width as u64 * imported.asset.height as u64;
        if self.pixels + count > crate::assets::MAX_ASSET_PIXELS {
            return Err(Error::new(
                "RESOURCE_LIMIT",
                "SVG images exceed the decoded-pixel budget",
            ));
        }
        let record = Record {
            id: format!("svg-image-{}", document.assets.len()),
            size: [imported.asset.width as f64, imported.asset.height as f64],
        };
        document.assets.insert(record.id.clone(), imported.asset);
        self.bytes += encoded_size;
        self.pixels += count;
        self.sources.insert(hash, record.clone());
        self.hrefs.insert(href.to_owned(), record.clone());
        losses.push("Image metadata and source density are retained in the encoded source, not installed into document metadata or placement. JPEG source compression is irreversible; normalized interpretation is RGBA8.".into());
        if let Some(conversion) = imported.color_conversion {
            losses.push(format!("Image color conversion uses relative colorimetric intent without black-point compensation: {}.", conversion["loss"].as_str().unwrap()));
        }
        losses.push(format!("SVG images retain immutable encoded sources and content-pinned RGBA8 interpretation ({:?}). Source links and sizing expressions become fixed editable placement.", self.options.color_policy));
        Ok(record)
    }
}

impl Importer<'_> {
    pub(super) fn expand_image(
        &mut self,
        node: Node<'_, '_>,
        parent: Option<String>,
        inherited: &Style,
    ) -> Result<(), Error> {
        if self.in_mask {
            return Err(unsupported(
                "Image artwork inside SVG mask sources is not yet supported",
            ));
        }
        for child in node.children().filter(Node::is_element) {
            if !["title", "desc", "style"].contains(&child.tag_name().name()) {
                return Err(unsupported("SVG image artwork children are not supported"));
            }
        }
        self.control.check()?;
        let record = self
            .images
            .load(node, &mut self.document, &mut self.losses)?;
        let width = coordinate(node, "width", self.viewport[0])?;
        let height = coordinate(node, "height", self.viewport[1])?;
        let size = match (width, height) {
            (Some(w), Some(h)) => [w, h],
            (Some(w), None) => [w, w * record.size[1] / record.size[0]],
            (None, Some(h)) => [h * record.size[0] / record.size[1], h],
            (None, None) => record.size,
        };
        let x = coordinate(node, "x", self.viewport[0])?.unwrap_or(0.0);
        let y = coordinate(node, "y", self.viewport[1])?.unwrap_or(0.0);
        let index = self.document.items.len();
        self.visit(node, parent, inherited, Some(identity()))?;
        let sampling = self.bindings[index]
            .style
            .image_sampling
            .unwrap_or(self.images.options.sampling);
        self.losses.push(format!("SVG image sampling becomes {sampling:?}. The pixelated hint selects nearest sampling, including noninteger scales; browser-specific reconstruction is not retained."));
        let id = self.document.items[index].id.clone();
        let props = properties(node, ATTRIBUTES, self.styles)?;
        self.bindings[index].object_bounds = Some([x, y, x + size[0], y + size[1]]);
        let row = self.mappings.last_mut().unwrap();
        row["asset_id"] = json!(record.id);
        row["image_size"] = json!(size);
        if size.contains(&0.0) {
            let binding = &mut self.bindings[index];
            self.template_refs
                .record(&binding.style, binding.clip.as_deref())?;
            binding.clip = None;
            binding.style.mask = None;
            binding.displayed = false;
            self.document.items[index].visible = false;
            row["empty_image"] = json!(true);
            let child = self.viewport_group(id, [1.0, 0.0, 0.0, 1.0, x, y], None, false)?;
            self.document.items[child].content = Content::Image {
                asset_id: record.id,
                width: record.size[0],
                height: record.size[1],
                crop: None,
                sampling,
            };
            self.mappings.last_mut().unwrap()["image_item_id"] =
                json!(self.document.items[child].id);
            self.losses.push("Zero-size images retain a hidden intrinsic-sized image under a nonpainting group; source sizing expressions are not retained.".into());
            return Ok(());
        }
        let clip = (props.get("overflow") != Some(&"visible")).then(|| Clip {
            geometry: Geometry::Rect {
                x,
                y,
                width: size[0],
                height: size[1],
            },
            transform: identity(),
            fill_rule: FillRule::Nonzero,
            enabled: true,
        });
        let wrapper = self.viewport_group(id, identity(), clip, true)?;
        let mut transform =
            viewports::mapping_from(node, size, Some([0.0, 0.0, record.size[0], record.size[1]]))?;
        transform[4] += x;
        transform[5] += y;
        let child = self.viewport_group(
            self.document.items[wrapper].id.clone(),
            transform,
            None,
            self.bindings[index].style.visible,
        )?;
        self.document.items[child].content = Content::Image {
            asset_id: record.id,
            width: record.size[0],
            height: record.size[1],
            crop: None,
            sampling,
        };
        let row = self
            .mappings
            .iter_mut()
            .find(|r| r["item_id"] == self.document.items[index].id)
            .unwrap();
        row["image_item_id"] = json!(self.document.items[child].id);
        row["viewport_item_id"] = json!(self.document.items[wrapper].id);
        Ok(())
    }
}
