//! Exact retained sensor bytes, versioned sidecars and atomic source-preserving edits.
use super::*;
use crate::{assets::Sampling, scene};
pub const ALGORITHM: &str = "inkbolt-raw-linear-v2";
pub const MAX_SOURCE_BYTES: usize = 131072;
pub const MAX_RECIPE_BYTES: u64 = 16384;

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Recipe {
    pub schema_version: u32,
    pub algorithm: String,
    pub source_sha256: String,
    pub capture: Capture,
    pub settings: Settings,
    pub corrections: Corrections,
}
impl Recipe {
    pub fn validate(&self) -> Result<(), Error> {
        if self.schema_version != 2 || self.algorithm != ALGORITHM {
            return Err(Error::new(
                "UNSUPPORTED_RAW_RECIPE",
                "Unsupported raw recipe schema or processing revision",
            ));
        }
        if self.source_sha256.len() != 64
            || !self
                .source_sha256
                .bytes()
                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
        {
            return Err(invalid_raw(
                "Recipe source identity must be 64 lowercase hexadecimal characters",
            ));
        }
        self.capture.validate()?;
        self.settings.gains()?;
        self.corrections.validate(&self.capture)?;
        Ok(())
    }
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Spec {
    pub source_hex: String,
    pub recipe: Recipe,
    #[serde(default)]
    pub sampling: Sampling,
}
impl Spec {
    pub fn validate(&self) -> Result<usize, Error> {
        self.recipe.validate()?;
        if self.source_hex.len() > MAX_SOURCE_BYTES * 2 {
            return Err(limit("Retained raw source exceeds 128 KiB"));
        }
        if self.source_hex.len() != self.recipe.capture.validate()? * 2
            || !self.source_hex.bytes().all(|c| c.is_ascii_hexdigit())
        {
            return Err(invalid_raw(
                "Retained raw bytes must match the complete declared sensor buffer",
            ));
        }
        if assets::sha256(&crate::render::unhex(&self.source_hex)) != self.recipe.source_sha256 {
            return Err(Error::new(
                "SOURCE_MISMATCH",
                "Retained sensor bytes do not match their recipe identity",
            ));
        }
        Ok(self.recipe.capture.width as usize * self.recipe.capture.height as usize)
    }
    pub fn geometry(&self) -> Geometry {
        Geometry::Rect {
            x: 0.0,
            y: 0.0,
            width: self.recipe.capture.width as f64,
            height: self.recipe.capture.height as f64,
        }
    }
    pub fn grid(&self, control: &Control) -> Result<Grid, Error> {
        self.validate()?;
        let result = super::develop_corrected(
            &crate::render::unhex(&self.source_hex),
            "raw-surface".to_string(),
            &self.recipe.capture,
            &self.recipe.settings,
            &self.recipe.corrections,
            control,
        )?;
        let mut grid: Grid =
            serde_json::from_value(result["document"]["items"][0]["content"]["grid"].clone())
                .map_err(|_| invalid_raw("Unable to decode developed raw surface"))?;
        grid.sampling = self.sampling;
        Ok(grid)
    }
}
pub fn import(
    source: &Path,
    recipe: Recipe,
    id: String,
    control: &Control,
) -> Result<Value, Error> {
    control.check()?;
    recipe.validate()?;
    assets::absolute(source)?;
    let bytes = assets::read_bounded(source, MAX_SOURCE_BYTES as u64)?;
    let spec = Spec {
        source_hex: crate::render::hex(&bytes),
        recipe,
        sampling: Default::default(),
    };
    document(spec, id, bytes.len(), control)
}
#[allow(clippy::too_many_arguments)]
pub fn retain(
    source: &Path,
    expected: Option<&str>,
    id: String,
    capture: Capture,
    settings: Settings,
    corrections: Corrections,
    control: &Control,
) -> Result<Value, Error> {
    control.check()?;
    capture.validate()?;
    settings.gains()?;
    corrections.validate(&capture)?;
    assets::absolute(source)?;
    let bytes = assets::read_bounded(source, MAX_SOURCE_BYTES as u64)?;
    let hash = assets::sha256(&bytes);
    if expected.is_some_and(|v| !v.eq_ignore_ascii_case(&hash)) {
        return Err(Error::new(
            "SOURCE_MISMATCH",
            "Raw source bytes do not match the expected identity",
        ));
    }
    // Freeze a single read; never reread a mutable pathname between identity and retention.
    let spec = Spec {
        source_hex: crate::render::hex(&bytes),
        recipe: Recipe {
            schema_version: 2,
            algorithm: ALGORITHM.into(),
            source_sha256: hash.clone(),
            capture,
            settings,
            corrections,
        },
        sampling: Default::default(),
    };
    document(spec, id, bytes.len(), control)
}
fn document(
    spec: Spec,
    id: String,
    source_bytes: usize,
    control: &Control,
) -> Result<Value, Error> {
    spec.validate()?;
    let d: Document=serde_json::from_value(json!({"schema_version":2,"id":id,"kind":"raster",
        "width":spec.recipe.capture.width,"height":spec.recipe.capture.height,
        "resolution_ppi":spec.recipe.settings.resolution_ppi,
        "color_space":if matches!(spec.recipe.settings.output,Output::LinearSrgb32){"linear_srgb"}else{"srgb"},
        "items":[{"id":"raw","content":{"type":"raw","raw":spec}}]}))
        .map_err(|_|invalid_raw("Unable to construct retained raw document"))?;
    crate::validate(&d)?;
    control.check()?;
    Ok(
        json!({"source_sha256":spec.recipe.source_sha256,"document":d,"source_bytes":source_bytes,"source_changed":false,"retained":true}),
    )
}
pub fn reopen(
    source: &Path,
    sidecar: &Path,
    id: String,
    control: &Control,
) -> Result<Value, Error> {
    control.check()?;
    assets::absolute(sidecar)?;
    let bytes = assets::read_bounded(sidecar, MAX_RECIPE_BYTES)?;
    let text = std::str::from_utf8(&bytes)
        .map_err(|_| invalid_raw("Raw sidecar must contain UTF-8 JSON"))?;
    let value = crate::mcp::strict_value(text)?;
    let recipe: Recipe = serde_json::from_value(value)
        .map_err(|_| invalid_raw("Raw sidecar does not match its strict schema"))?;
    import(source, recipe, id, control)
}
pub(crate) fn recipe_data(recipe: &Recipe) -> Result<String, Error> {
    Ok(serde_json::to_string_pretty(recipe)
        .map_err(|_| invalid_raw("Unable to serialize raw recipe"))?
        + "\n")
}
pub fn recipe(d: &Document, id: &str) -> Result<Value, Error> {
    crate::validate(d)?;
    let i = scene::index(d, id)?;
    let Content::Raw { raw } = &d.items[i].content else {
        return Err(invalid_raw("Recipe export requires a retained raw layer"));
    };
    let data = recipe_data(&raw.recipe)?;
    Ok(
        json!({"media_type":"application/json","encoding":"utf8","sha256":assets::sha256(data.as_bytes()),"data":data,"recipe":raw.recipe,
        "source_changed":false,"losses":["This sidecar stores sensor development only. Layer transforms, masks, opacity, compositing, scene resolution, sampling and other document state require a snapshot. The exact original sensor buffer is required to reopen; the recipe is not a backup."]}),
    )
}
pub(crate) fn edit(
    d: &mut Document,
    id: &str,
    settings: &Settings,
    corrections: &Corrections,
) -> Result<Value, Error> {
    let i = scene::index(d, id)?;
    scene::check_unlocked(d, i, false)?;
    let Content::Raw { raw } = &mut d.items[i].content else {
        return Err(invalid_raw("Raw settings require a retained raw layer"));
    };
    let before = raw.recipe.clone();
    raw.recipe.settings = settings.clone();
    raw.recipe.corrections = corrections.clone();
    raw.validate()?;
    Ok(
        json!({"before":before,"after":raw.recipe,"source_changed":false,"scene_resolution_changed":false}),
    )
}
pub(crate) fn expand(d: &mut Document, id: &str, control: &Control) -> Result<Value, Error> {
    let i = scene::index(d, id)?;
    scene::check_unlocked(d, i, false)?;
    let Content::Raw { raw } = &d.items[i].content else {
        return Err(invalid_raw("Raw expansion requires a retained raw layer"));
    };
    let source = raw.recipe.source_sha256.clone();
    let grid = raw.grid(control)?;
    d.items[i].content = Content::Samples {
        grid: Box::new(grid),
    };
    Ok(
        json!({"source_sha256":source,"source_retained_in_input":true,"losses":["Raw settings and embedded sensor bytes become developed samples in this result. Keep the original snapshot or use undo to restore raw editability."]}),
    )
}

/// Conservative work units, retained-grid slots and maximum temporary slots.
/// The caller validates the recipe and adds these to the whole-page budgets.
pub(crate) fn preparation_costs(raw: &crate::raw::retained::Spec) -> (u64, u64, u64) {
    let capture = &raw.recipe.capture;
    let pixels = capture.width as u64 * capture.height as u64;
    let options = &raw.recipe.corrections;
    let mut per_pixel = 128;
    for (radius, amount) in options
        .denoise
        .iter()
        .map(|p| (p.radius, p.amount))
        .chain(options.detail.iter().map(|p| (p.radius, p.amount)))
    {
        if amount != 0.0 {
            per_pixel += 16 * (2 * radius as u64 + 1).pow(2);
        }
    }
    if options.lens.is_some() {
        per_pixel += 128;
    }
    let bytes = raw.source_hex.len() as u64 / 2;
    (
        pixels * per_pixel + bytes,
        pixels * 4,
        pixels * 32 + bytes.div_ceil(8),
    )
}
