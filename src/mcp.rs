//! Bounded MCP stdio adapter for the shared local engine, protocol 2025-11-25.
use crate::{
    Error,
    control::{Control, Options},
};
use serde::{
    Deserialize, Deserializer,
    de::{self, MapAccess, SeqAccess, Visitor},
};
use serde_json::{Map, Value, json};
use std::{
    collections::{BTreeMap, HashSet},
    fmt,
    io::{self, BufRead, Write},
    sync::{Arc, Mutex, mpsc},
    thread,
};

pub const PROTOCOL: &str = "2025-11-25";
pub const MAX_MESSAGE_BYTES: usize = crate::MAX_REQUEST_BYTES as usize + 16384;
pub const MAX_RESPONSE_BYTES: usize = 96 * 1024 * 1024;
pub const MAX_PENDING: usize = 8;
pub const MAX_REQUEST_IDS: usize = 4096;
const PAGE: usize = 8;

pub const CORE_CATALOG_BYTES: usize = 96 * 1024;
const CORE: &[&str] = &[
    "schema.lookup",
    "document.create",
    "document.inspect",
    "document.inspect.page",
    "document.query",
    "document.edit",
    "document.render",
    "session.create",
    "session.read",
    "session.apply",
    "session.receipt",
    "session.history",
    "session.diff",
    "session.publish",
    "asset.import",
    "font.import",
];

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CatalogMode {
    Full,
    Core,
}

impl CatalogMode {
    fn cursor(self) -> &'static str {
        match self {
            Self::Full => "inkbolt-tools-v1:",
            Self::Core => "inkbolt-tools-core-v1:",
        }
    }
}

// Parse once without losing duplicate-key errors when dispatch adds the command field.
struct Strict(Value);
impl<'de> Deserialize<'de> for Strict {
    fn deserialize<D: Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        struct V;
        impl<'de> Visitor<'de> for V {
            type Value = Strict;
            fn expecting(&self, f: &mut fmt::Formatter) -> fmt::Result {
                f.write_str("JSON without duplicate object keys")
            }
            fn visit_bool<E: de::Error>(self, v: bool) -> Result<Strict, E> {
                Ok(Strict(json!(v)))
            }
            fn visit_i64<E: de::Error>(self, v: i64) -> Result<Strict, E> {
                Ok(Strict(json!(v)))
            }
            fn visit_u64<E: de::Error>(self, v: u64) -> Result<Strict, E> {
                Ok(Strict(json!(v)))
            }
            fn visit_f64<E: de::Error>(self, v: f64) -> Result<Strict, E> {
                Ok(Strict(json!(v)))
            }
            fn visit_str<E: de::Error>(self, v: &str) -> Result<Strict, E> {
                Ok(Strict(json!(v)))
            }
            fn visit_unit<E: de::Error>(self) -> Result<Strict, E> {
                Ok(Strict(Value::Null))
            }
            fn visit_seq<A: SeqAccess<'de>>(self, mut seq: A) -> Result<Strict, A::Error> {
                let mut values = Vec::new();
                while let Some(Strict(v)) = seq.next_element()? {
                    values.push(v);
                }
                Ok(Strict(Value::Array(values)))
            }
            fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<Strict, A::Error> {
                let mut values = Map::new();
                while let Some((key, Strict(v))) = map.next_entry::<String, Strict>()? {
                    if values.insert(key, v).is_some() {
                        return Err(de::Error::custom("Duplicate key"));
                    }
                }
                Ok(Strict(Value::Object(values)))
            }
        }
        d.deserialize_any(V)
    }
}
pub(crate) fn strict_value(text: &str) -> Result<Value, Error> {
    serde_json::from_str::<Strict>(text)
        .map(|s| s.0)
        .map_err(|_| {
            Error::new(
                "INVALID_JSON",
                "Expected bounded JSON without duplicate keys",
            )
        })
}
fn description(command: &str) -> &'static str {
    match command {
        "document.inspect.page" => {
            "Read bounded pages of selected item fields, asset/font inventories or path anchors. Cursor binds exact document content, view and page limit. Hidden/locked items are included; resources are structural inventories. Use pinned saved references to avoid resending documents."
        }
        "schema.lookup" => {
            "Discover command arguments and shared graphics types. Use name index for available names. Large schemas return an outline; select a listed variant or definition, or use full:true for all reachable definitions. Read-only. The original schema command still returns the entire engine schema."
        }
        "layered.import" => {
            "Read a bounded local layered RGB file into editable native pixel layers. Preserves order, names, visibility, integer extents and exact byte opacity. Checks an optional source hash, uses explicit color policy and leaves the file unchanged. Unsupported masks, groups, text and effects fail explicitly; no flattened-cache substitution."
        }
        "color.convert" => {
            "Convert up to 4096 finite device RGB, grayscale, CMYK or physical D50 Lab samples through explicit profiles. Returns directional table identities, PCS values and clipped component counts. Untagged RGB needs explicit assume_srgb; other device spaces require matching profiles. Original components and profile bytes remain unchanged. No document edit or publication is performed."
        }
        "raw.retain" => {
            "Retain exact bounded sensor bytes with editable calibration/development and explicit lens, noise and detail controls. Returns a new raw-layer document, preserving the input file. Rendering recomputes from the original sensor. Expansion to ordinary pixels is explicit."
        }
        "raw.reopen" => {
            "Read a strict versioned raw sidecar and its separately supplied original sensor buffer. Checks processing revision and exact source hash; returns an editable raw-layer document. Does not restore scene styling, overwrite files or access a network."
        }
        "raw.recipe" => {
            "Export one retained raw layer's complete versioned sensor-development recipe as UTF-8 JSON with a digest. The original sensor buffer is required for reopening. Scene masks, transforms and compositing require a snapshot. No files are written."
        }
        "assist.segment" => {
            "Select a foreground object from explicit foreground/background seeds using local native RGBA8 colors and neighboring edges. Returns a binary mask, source identities and exact integer minimum-cut/max-flow certificate; optional full costs are inspectable. No model, GPU or network dependency. Read-only; assist_mask applies an editable source-preserving mask atomically. Seeds use cropped native pixel coordinates; unsupported semantics fail explicitly."
        }
        "assist.layout" => {
            "Propose an optimal ordered row layout of explicit artwork IDs inside a bounded area. Reports exact minimum shelf height, row breaks, transforms and geometry error. CPU only with no model or network dependency. Read-only; apply with assist_layout under the expected revision. Sizes and editable source are preserved; packing uses geometric bounds, excludes strokes/effects and ignores unselected obstacles."
        }
        "sequence.import" => {
            "Import an explicit ordered image list, animated PNG or GIF into editable frame views and an immutable local asset store. Source files remain unchanged. GIF retains exact palette frames and centisecond timing, with explicit untagged color policy and transparent or logical-screen background. Timing, alpha composition, disposal, poster images, color policy and limits are explicit."
        }
        "sequence.export" => {
            "Return independent PNG artifacts in exact frame order, with filenames, hashes, delay fractions and play count. Source artwork stays unchanged; no partial batch is returned on failure. Local image/font stores and render settings are explicit."
        }
        "volume.inspect" => {
            "Inspect retained extrusion, camera, lighting and projected vector faces"
        }
        "appearance.inspect" => "Inspect ordered paint passes and retained source geometry",
        "sequence.inspect" => {
            "Inspect ordered frame IDs, variant datasets, exact rational start/end times and loop count without changing artwork."
        }
        "sequence.open" => {
            "Return an editable still at an explicit frame, detaching timing and variant bindings while preserving the original sequence."
        }
        "object.import" => {
            "Retain exact local engine snapshot bytes as an editable object without changing the source. Returns an object descriptor; external image/font stores remain explicit. Optional flat link key enables explicit status and refresh."
        }
        "object.open" => {
            "Reopen a retained object's editable source and exact snapshot bytes without reading or changing an external link."
        }
        "object.status" => {
            "Inspect retained object identity and optionally check a flat link inside an explicit root. Changed, missing and invalid sources never change the retained artwork."
        }
        "sample.measure" => {
            "Inspect full-precision rendered samples and signed/HDR ranges without display projection or source mutation."
        }
        "sample.import" => {
            "Read a bounded local PNG or TIFF into a new editable raster snapshot, retaining 8/16-bit or normalized binary32 RGB/grayscale samples. Returns exact source hash and normalization diagnostics. Source files stay unchanged. Untagged inputs require explicit assume_srgb, or assume_linear_srgb for signed binary32 TIFF HDR. Profiles, associated alpha and sequences fail explicitly."
        }
        "raw.develop" => {
            "Develop a bounded explicitly calibrated Bayer sensor buffer into a new editable image. Requires sensor packing, pattern, black/white levels, camera matrix, exposure, white balance and output precision/range/resolution. Returns a pinned recipe and range diagnostics. Preserves source bytes; camera containers and automatic calibration are unsupported."
        }
        "swatch.inspect" => {
            "Inspect exact named process/spot declarations, retained tint dependencies and explicit display previews. Reports shared users and palette identity without changing source. Non-RGB previews are caller-supplied, not implicit conversions."
        }
        "geometry.measure" => {
            "Inspect rotated geometry bounds, dimensions, certified authored boundary lengths and signed contour areas in explicit physical units. Read-only; preserves source and declares geometry versus painted-area semantics."
        }
        "warp.inspect" => {
            "Inspect retained vector deformation, ordered perspective/envelope maps, sample points, perspective grids and exact expansion error certificates. Local read-only bounded planning."
        }
        "pixel_warp.inspect" => {
            "Inspect retained pixel deformation controls, posed mesh vertices, unique forward/inverse sample positions and local bounds. Local bounded read-only planning."
        }
        "repeat.inspect" => {
            "Inspect editable brick, hexagonal, radial, grid and mirrored motif layouts, exact affine placements, bounds and optional combined geometry. Read-only local planning; strict limits apply."
        }
        "interpolation.inspect" => {
            "Inspect editable fixed-count shape/color interpolation, contour correspondence, curved-spine measurements, placements, colors and optional generated geometry. Read-only local planning; strict limits apply."
        }
        "brush.inspect" => {
            "Inspect deterministic native-pixel brush spacing, dynamic size/opacity, seeded scatter, bounds and optional dab positions without editing. Use brush_stroke in document.edit/session.apply to paint, erase, mix or smudge an inline pixel layer. Pixel-integrated coverage, source-preserving atomic edits and explicit limits apply."
        }
        "image.trace" => {
            "Trace explicit RGBA8 pixels or a verified local image asset into a new editable vector document. Binary, exact-color, quantized and explicit-palette modes preserve classified cell boundaries, corners and holes. Noise thresholds, deterministic provenance, independent color-error metrics and limits are explicit. Read-only source; no file writes. Supports cooperative cancellation."
        }
        "mesh.inspect" => {
            "Inspect a bounded editable color mesh, certified geometry contraction, C1 knot joins and optional parameter samples with analytic position/color derivatives and inverse checks. Does not change a document."
        }
        "svg.import" => {
            "Import a bounded local UTF-8 SVG file or text as a new editable vector document. Supports geometry, gradients, clips, shared editable artwork masks and single-line editable text with explicit font_bindings and font_root. No installed-font lookup or substitution. Returns source hash, ID mapping and normalization losses. Preserves source files; rejects unsupported semantics and malformed XML."
        }
        "capabilities" => {
            "Inspect implemented graphics features, command names, limits and explicit unsupported semantics before planning work."
        }
        "schema" => {
            "Get the complete typed engine JSON Schema, including document, operation and resource definitions."
        }
        "implementation.status" => {
            "Get the complete 167-checkpoint implementation registry with acceptance and executable evidence; research completion is separate."
        }
        "document.create" => {
            "Create an empty editable vector or raster sRGB document. Returns a snapshot; does not save a file."
        }
        "document.validate" => {
            "Validate and normalize a supplied snapshot. Does not resolve external resource bytes or change files."
        }
        "document.inspect" => {
            "Inspect stable item IDs, hierarchy, visibility, locks, world transforms, unclipped geometry bounds and resource inventories."
        }
        "document.query" => {
            "Discover editable item IDs by content type, shape and inclusive geometry bounds; optionally inspect path anchors in local/world coordinates. Defaults to visible, unlocked items. Returned command indices address this document revision."
        }
        "channel.export" => {
            "Export a saved scalar channel as grayscale PNG or a named-ink alternate-color preview, retaining channel identity in structured metadata. Does not change the artwork."
        }
        "document.boolean" => {
            "Combine the filled geometry of explicit vector IDs with union, intersection, difference or xor. Returns a new editable path or an explicit empty result, exact polygon area, tolerance and topology diagnostics. Sources stay unchanged; styles/effects do not define the operands."
        }
        "document.measure" => {
            "Measure exact RGBA8 composite histograms, statistics and pixel samples; optionally weight by selection and alpha. Returns structured numerical evidence without changing the document."
        }
        "document.select" => {
            "Inspect an explicit list of item IDs without persistent selection state. Use returned IDs in atomic edit operations."
        }
        "document.edit" => {
            "Apply 1..64 typed operations atomically to a supplied snapshot at expected_revision. Supports physical-unit dimensions and rotated guide/grid/item snapping, reversible opaque raster backgrounds with retained sources and explicit matte/ordinary-layer conversion, retained per-font variation axes and explicit OpenType controls, Unicode script shaping, explicit pinned-font fallback and language systems, source-retaining pixel perspective/mesh/articulated controls, retained vector warp stacks and certified expansion, editable brick/hex/radial/mirrored repeat layouts and compound expansion, plus editable object interpolation with fixed counts, curved spines, unequal contours and expansion, plus editable vector brush motifs with spacing, width profiles, endpoints/corners and filled expansion, plus native-pixel clone/heal retouching and quality-gated patch/fill/move/guided edge repair with frozen explicit sources, measured boundaries and residual-checked healing, plus document/item metadata with private working fields. Returns a new snapshot and changes; leaves files unchanged."
        }
        "document.render" => {
            "Render a bounded snapshot into straight RGBA8 hex pixels. Supply asset_root and font_root when stored resources are referenced."
        }
        "document.proof" => {
            "Observe calibrated CMYK print delivery and optional independent named-ink recipe plates. Returns an sRGB PNG reference proof, exact scalar ink PNGs, measured D50 CIE76 differences, threshold mask and separate display clipping. Explicit print profile, matte, view intent and density; combined named inks require the whole canvas and an explicit CMYK fallback model. Optional ICC gamut-tag diagnostics distinguish missing tables and unclassified PCS overflow. Read-only, sources unchanged, no print job. Physical ink calibration, overprint simulation and universal reader preview parity are not inferred."
        }
        "document.prepress" => {
            "Inspect native vector CMYK and spot ink planes over unmarked paper. Retains direct CMYK fractions, named ink identities and per-paint overprint; converts RGB, gray and Lab paints through an explicit profile before ink compositing. Supports normal isolated/pass-through groups, scalar masks, geometric clips, strokes and outlined text. Returns read-only scalar PNGs and requested continuous ink samples. Extended print preparation remains in progress; unsupported blends/effects/images fail explicitly."
        }
        "document.separations" => {
            "Evaluate a retained ink_recipe over saved scalar channels. Returns exact independent named-ink PNG plates and an explicitly modelled calibrated preview. Multiple curves may share one source for duotones; optional masks multiply before one exact byte projection. Read-only; sources and editable curves stay unchanged. pdf_options.ink_recipe delivers these samples as DeviceN inks. Ordinary artwork and calibrated process imagery are separate."
        }
        "profile.gamut" => {
            "Inspect explicit D50 XYZ samples through a supplied output profile's gamut table, with exact profile identity and explicit unclassified coordinates; read-only."
        }
        "document.export" => {
            "Return PDF/PNG/APNG/JPEG/TIFF/BMP/TGA/GIF base64, working-sRGB vector SVG, or editable snapshot JSON. PDF uses native paths and outlined text by default; pdf_options.print explicitly flattens calibrated CMYK image pages with a supplied output ICC profile, required matte and sample density. pdf_options also selects ordered artboard pages and bleed, or omission exports the canvas. metadata_policy controls public descriptions, stripping, path-free resource manifests and reproducible provenance. Snapshots retain private records by default; other outputs exclude them. Saved output profiles explicitly convert and embed ICC bytes in images. JPEG/BMP transparency requires an explicit matte; TIFF declares straight or associated alpha. GIF requires exact palettes, binary alpha and centisecond timing; it exports all sequence frames. BMP/TGA/GIF reject output profiles; BMP/TGA descriptions require explicit stripping. Does not write a destination. Unsupported semantics fail explicitly."
        }
        "document.publish" => {
            "Export a snapshot or one artboard into an existing explicit output root. Creates the chosen filename atomically and rejects every existing destination. Returns a byte/hash receipt and applied metadata policy."
        }
        "document.diff" => {
            "Compare two snapshots of the same document using stable IDs, geometry, appearance fields and resources. Optional scale-1 pixel differences require equal canvas sizes."
        }
        "session.create" => {
            "Create a durable local editing session from a snapshot and resource roots. Starts session revision zero; use the same request_id for safe retries. Never overwrites another session."
        }
        "session.read" => {
            "Read the current session or a named snapshot, including document, resource roots, current revision and history depths."
        }
        "session.apply" => {
            "Commit one atomic edit, undo/redo, named snapshot action or resource-binding change. Requires expected_revision and a unique request_id; same-payload retries return the original receipt without reapplying."
        }
        "session.receipt" => {
            "Recover the original committed document and receipt by request_id after a lost response. Current head fields are separate from the historical result."
        }
        "session.history" => {
            "Page committed history receipts in revision order. Set limit 1..128 and pass next_after_revision as after_revision for the next page."
        }
        "session.verify" => {
            "Verify bounded database integrity, state/receipt hashes and history references. Does not verify external image/font availability or repair files."
        }
        "session.diff" => {
            "Compare two committed session revisions including saved resource bindings. Rendering uses immutable captured states, releasing the database read lock first."
        }
        "session.publish" => {
            "Capture the expected current revision and publish its document or artboard create-only. Later concurrent edits cannot change the captured export. Does not add an undo step."
        }
        "artboard.export" => {
            "Return independent PNG/JPEG/TIFF/BMP/TGA/SVG exports for all artboards, ordered IDs or an end-exclusive range, optionally with bleed and format-specific image options. Returns no partial batch on failure."
        }
        "asset.import" => {
            "Read an explicit local PNG, JPEG, TIFF, BMP, TGA or single-frame GIF into an immutable image store. Explicit convert_srgb supports embedded or declared RGB ICC input profiles, retaining source/profile hashes and alpha. Untagged samples require an explicit policy. Sources and existing stored bytes remain unchanged. Unsupported semantics fail explicitly."
        }
        "asset.verify" => {
            "Resolve an image descriptor and verify normalized pixel identity in the given local store."
        }
        "asset.embed" => {
            "Return an equivalent bounded embedded pixel descriptor from a verified image resource; does not change files."
        }
        "font.import" => {
            "Read a permitted local outline font and its UTF-8 license. Publish immutable byte and license copies to an explicit store; returns a pinned descriptor."
        }
        "font.verify" => {
            "Verify the pinned font bytes, selected face and retained license from the explicit font store."
        }
        "font.inspect" => {
            "Inspect a pinned local font, its variation ranges, available feature tags and selected instance metrics."
        }
        "text.inspect" => {
            "Inspect layout, glyph origins and ink bounds of one editable text frame. Optional outlines are bounded; missing fonts/glyphs fail explicitly."
        }
        "text.directions" => {
            "Resolve Unicode paragraph directions and inspect line reading order in logical scalar indices, without loading fonts."
        }
        "text.hyphenate" => {
            "Inspect discretionary break opportunities from explicit weighted rules and exceptions. Preserves original tokens and grapheme boundaries; does not lay out text or choose a language dictionary."
        }
        "story.inspect" => {
            "Inspect shared paragraph flow through ordered slots and columns, with source ranges and the retained overset tail. Original paragraph records remain unchanged."
        }
        _ => "Execute a validated Inkbolt engine command.",
    }
}
fn portable_schema(value: &mut Value) {
    match value {
        Value::Object(map) => {
            if let Some(Value::Array(types)) = map.get("type").cloned() {
                map.remove("type");
                map.insert(
                    "anyOf".into(),
                    Value::Array(types.into_iter().map(|t| json!({"type":t})).collect()),
                );
            }
            for child in map.values_mut() {
                portable_schema(child);
            }
        }
        Value::Array(values) => {
            for child in values {
                portable_schema(child);
            }
        }
        _ => {}
    }
}
pub fn catalog() -> BTreeMap<String, (String, Value)> {
    catalog_with_mode(CatalogMode::Full)
}

pub fn catalog_with_mode(mode: CatalogMode) -> BTreeMap<String, (String, Value)> {
    catalog_in_workspace(mode, false)
}

pub fn catalog_in_workspace(
    mode: CatalogMode,
    workspace: bool,
) -> BTreeMap<String, (String, Value)> {
    let mut tools = BTreeMap::new();
    for command in crate::schema::commands() {
        if mode == CatalogMode::Core && !CORE.contains(&command) {
            continue;
        }
        let mut input = crate::schema::arguments(command, mode == CatalogMode::Core).unwrap();
        if workspace {
            crate::workspace::describe(&mut input);
        }
        input["properties"]["response_format"] = json!({"type":"string","enum":["json","markdown","preview"],"default":"json","description":"JSON/Markdown preserve the full envelope in text and structuredContent. Preview uses summary text and one PNG payload location with explicit references; metadata stays in structuredContent."});
        portable_schema(&mut input);
        let name = format!("inkbolt_{}", command.replace('.', "_"));
        let mutable = matches!(
            command,
            "sequence.import"
                | "asset.import"
                | "font.import"
                | "session.create"
                | "session.apply"
                | "session.publish"
                | "document.publish"
        );
        let tool = json!({"name":name,"description":description(command),"inputSchema":input,"outputSchema":{"type":"object","properties":{"ok":{"type":"boolean"},"result":{"type":"object","additionalProperties":true},"error":{"type":"object"}},"required":["ok"],"additionalProperties":false},"annotations":{"readOnlyHint":!mutable,"destructiveHint":command=="session.apply","idempotentHint":true,"openWorldHint":false},"execution":{"taskSupport":"forbidden"}});
        tools.insert(name, (command.to_owned(), tool));
    }
    if mode == CatalogMode::Core {
        let tool = json!({
            "name":"inkbolt_run",
            "description":"Run any engine command through the same validated executor. Discover names and arguments with inkbolt_schema_lookup. Arguments omit command. Editing retains revision checks and durable retry receipts; source files and existing outputs are preserved.",
            "inputSchema":{"type":"object","additionalProperties":false,"required":["command","arguments"],"properties":{
                "command":{"type":"string","enum":crate::schema::commands().collect::<Vec<_>>()},
                "arguments":{"type":"object","additionalProperties":true,"description":"Command fields from schema.lookup, without command or response_format."},
                "response_format":{"type":"string","enum":["json","markdown","preview"],"default":"json"}
            }},
            "outputSchema":{"type":"object","properties":{"ok":{"type":"boolean"},"result":{"type":"object","additionalProperties":true},"error":{"type":"object"}},"required":["ok"],"additionalProperties":false},
            "annotations":{"readOnlyHint":false,"destructiveHint":true,"idempotentHint":false,"openWorldHint":false},
            "execution":{"taskSupport":"forbidden"}
        });
        tools.insert("inkbolt_run".into(), ("run".into(), tool));
    }
    tools
}

fn dispatch_arguments(command: &str, mut args: Map<String, Value>) -> Result<Value, Error> {
    let (command, mut args) = if command == "run" {
        let name = args
            .remove("command")
            .and_then(|v| v.as_str().map(str::to_owned));
        let arguments = args.remove("arguments");
        match (name, arguments) {
            (Some(name), Some(Value::Object(arguments)))
                if args.is_empty() && crate::schema::commands().any(|c| c == name) =>
            {
                (name, arguments)
            }
            _ => {
                return Err(Error::new(
                    "INVALID_REQUEST",
                    "Run requires a known command and an arguments object, with no extra fields",
                ));
            }
        }
    } else {
        (command.to_owned(), args)
    };
    if args.contains_key("command") {
        return Err(Error::new(
            "INVALID_REQUEST",
            "Tool selects the command; omit command from arguments",
        ));
    }
    args.insert("command".into(), json!(command));
    if serde_json::to_vec(&args).unwrap().len() > crate::MAX_REQUEST_BYTES as usize {
        return Err(Error::new(
            "REQUEST_TOO_LARGE",
            "Engine arguments exceed 16 MiB",
        ));
    }
    Ok(Value::Object(args))
}
fn protocol_error(id: Option<Value>, code: i32, message: &str) -> Value {
    let mut value = json!({"jsonrpc":"2.0","error":{"code":code,"message":message}});
    if let Some(id) = id {
        value["id"] = id;
    }
    value
}
fn send(output: &Mutex<io::Stdout>, value: &Value) -> io::Result<()> {
    let mut bytes = serde_json::to_vec(value)?;
    if bytes.len() > MAX_RESPONSE_BYTES {
        bytes = serde_json::to_vec(&protocol_error(
            value.get("id").cloned(),
            -32603,
            "MCP result exceeds 96 MiB; request fewer artboards or publish individual outputs. Inspect persistent receipts before retrying a mutation",
        ))?;
    }
    let mut out = output
        .lock()
        .map_err(|_| io::Error::other("Output lock unavailable"))?;
    out.write_all(&bytes)?;
    out.write_all(b"\n")?;
    out.flush()
}
fn valid_id(value: &Value) -> bool {
    value
        .as_str()
        .is_some_and(|s| !s.is_empty() && s.len() <= 256)
        || value
            .as_i64()
            .is_some_and(|n| n.unsigned_abs() <= 9_007_199_254_740_991)
}
fn line(input: &mut impl BufRead) -> io::Result<Option<Result<Vec<u8>, ()>>> {
    let mut bytes = Vec::new();
    let mut too_long = false;
    let mut saw = false;
    loop {
        let chunk = input.fill_buf()?;
        if chunk.is_empty() {
            return Ok(if saw {
                Some(if too_long { Err(()) } else { Ok(bytes) })
            } else {
                None
            });
        }
        saw = true;
        let end = chunk.iter().position(|b| *b == b'\n').map(|n| n + 1);
        let n = end.unwrap_or(chunk.len());
        if !too_long {
            if bytes.len() + n > MAX_MESSAGE_BYTES {
                too_long = true;
                bytes.clear();
            } else {
                bytes.extend_from_slice(&chunk[..n]);
            }
        }
        input.consume(n);
        if end.is_some() {
            return Ok(Some(if too_long { Err(()) } else { Ok(bytes) }));
        }
    }
}
struct Job {
    id: Value,
    key: String,
    request: Value,
    control: Control,
    format: ResponseFormat,
}
#[derive(Clone, Copy)]
enum ResponseFormat {
    Json,
    Markdown,
    Preview,
}
type Active = Arc<Mutex<BTreeMap<String, Control>>>;
fn tool_result(result: Result<Value, Error>, format: ResponseFormat, command: &str) -> Value {
    let failed = result.is_err();
    let envelope = match result {
        Ok(result) => json!({"ok":true,"result":result}),
        Err(error) => json!({"ok":false,"error":error}),
    };
    if matches!(format, ResponseFormat::Preview) {
        return crate::mcp_preview::present(envelope, command);
    }
    let text = if matches!(format, ResponseFormat::Markdown) {
        format!(
            "{}\n\n```json\n{}\n```",
            if failed {
                "Inkbolt could not complete the request."
            } else {
                "Inkbolt completed the request."
            },
            serde_json::to_string_pretty(&envelope).unwrap()
        )
    } else {
        envelope.to_string()
    };
    let mut content = vec![json!({"type":"text","text":text})];
    let result = &envelope["result"];
    let artifacts: Vec<&Value> =
        if let Some(entries) = result.get("artifacts").and_then(Value::as_array) {
            entries.iter().map(|v| &v["artifact"]).collect()
        } else {
            vec![result]
        };
    let mut image_bytes = 0;
    for artifact in artifacts {
        if artifact["media_type"] == "image/png"
            && artifact["encoding"] == "base64"
            && let Some(data) = artifact["data"].as_str()
        {
            if content.len() >= 5 || image_bytes + data.len() > 8 * 1024 * 1024 {
                break;
            }
            image_bytes += data.len();
            content.push(json!({"type":"image","mimeType":"image/png","data":data}));
        }
    }
    json!({"content":content,"structuredContent":envelope,"isError":failed})
}
pub fn run() -> io::Result<()> {
    run_with_mode(CatalogMode::Full)
}

pub fn run_with_mode(mode: CatalogMode) -> io::Result<()> {
    run_in_workspace(mode, None)
}

pub fn run_in_workspace(
    mode: CatalogMode,
    workspace: Option<crate::workspace::Workspace>,
) -> io::Result<()> {
    let output = Arc::new(Mutex::new(io::stdout()));
    let active: Active = Arc::new(Mutex::new(BTreeMap::new()));
    let (tx, rx) = mpsc::sync_channel::<Job>(MAX_PENDING);
    let worker_output = output.clone();
    let worker_active = active.clone();
    let worker_workspace = workspace.clone();
    let worker = thread::spawn(move || {
        for job in rx {
            let command = job.request["command"].as_str().unwrap_or("").to_owned();
            let result=std::panic::catch_unwind(std::panic::AssertUnwindSafe(||crate::request::execute(job.request,worker_workspace.as_ref(),&job.control))).unwrap_or_else(|_|Err(Error::new("INTERNAL_ERROR","Engine request failed unexpectedly; inspect any persistent request receipt before retrying")));
            // Notifications are fire-and-forget; persistent outcome remains available by receipt.
            if !job.control.is_cancelled() {
                let response = json!({"jsonrpc":"2.0","id":job.id,"result":tool_result(result,job.format,&command)});
                if send(&worker_output, &response).is_err() {
                    for c in worker_active.lock().unwrap().values() {
                        c.cancel();
                    }
                    return;
                }
            }
            worker_active.lock().unwrap().remove(&job.key);
        }
    });
    let tools = catalog_in_workspace(mode, workspace.is_some());
    let mut initialized = false;
    let mut ready = false;
    let mut seen = HashSet::new();
    let mut input = io::stdin().lock();
    let result = (|| -> io::Result<()> {
        while let Some(bytes) = line(&mut input)? {
            let bytes = match bytes {
                Ok(bytes) => bytes,
                Err(()) => {
                    send(
                        &output,
                        &protocol_error(None, -32600, "MCP message exceeds its byte limit"),
                    )?;
                    continue;
                }
            };
            let value = match serde_json::from_slice::<Strict>(&bytes) {
                Ok(Strict(value)) => value,
                Err(_) => {
                    send(
                        &output,
                        &protocol_error(
                            None,
                            -32700,
                            "Expected one UTF-8 JSON message without duplicate keys",
                        ),
                    )?;
                    continue;
                }
            };
            let Some(object) = value.as_object() else {
                send(
                    &output,
                    &protocol_error(
                        None,
                        -32600,
                        "Expected a JSON-RPC object; batches are unsupported",
                    ),
                )?;
                continue;
            };
            let id = object.get("id").cloned();
            let notification = id.is_none();
            if object.get("jsonrpc") != Some(&json!("2.0"))
                || object.get("method").and_then(Value::as_str).is_none()
                || id.as_ref().is_some_and(|id| !valid_id(id))
                || object.get("params").is_some_and(|v| !v.is_object())
            {
                if !notification
                    || !object
                        .get("method")
                        .and_then(Value::as_str)
                        .is_some_and(|m| m.starts_with("notifications/"))
                {
                    send(
                        &output,
                        &protocol_error(id.filter(valid_id), -32600, "Invalid JSON-RPC envelope"),
                    )?;
                }
                continue;
            }
            let method = value["method"].as_str().unwrap();
            let empty = Map::new();
            let params = value
                .get("params")
                .and_then(Value::as_object)
                .unwrap_or(&empty);
            if notification {
                if method == "notifications/initialized" && initialized {
                    ready = true;
                } else if method == "notifications/cancelled"
                    && let Some(id) = params.get("requestId").filter(|v| valid_id(v))
                    && let Some(c) = active.lock().unwrap().get(&id.to_string())
                {
                    c.cancel();
                }
                continue;
            }
            let id = id.unwrap();
            let key = id.to_string();
            if seen.contains(&key) {
                send(
                    &output,
                    &protocol_error(
                        Some(id),
                        -32600,
                        "Request ID was already used in this MCP connection",
                    ),
                )?;
                continue;
            }
            if seen.len() >= MAX_REQUEST_IDS {
                send(
                    &output,
                    &protocol_error(
                        Some(id),
                        -32000,
                        "MCP request-ID limit reached; reconnect and retain session request IDs for retries",
                    ),
                )?;
                continue;
            }
            seen.insert(key.clone());
            if method == "initialize" {
                if initialized {
                    send(
                        &output,
                        &protocol_error(Some(id), -32600, "Connection is already initialized"),
                    )?;
                    continue;
                }
                if !params.get("protocolVersion").is_some_and(Value::is_string)
                    || !params.get("capabilities").is_some_and(Value::is_object)
                    || !params
                        .get("clientInfo")
                        .is_some_and(|v| v["name"].is_string() && v["version"].is_string())
                {
                    send(
                        &output,
                        &protocol_error(
                            Some(id),
                            -32602,
                            "Initialization requires protocolVersion, capabilities and clientInfo name/version",
                        ),
                    )?;
                    continue;
                }
                initialized = true;
                send(
                    &output,
                    &json!({"jsonrpc":"2.0","id":id,"result":{"protocolVersion":PROTOCOL,"capabilities":{"tools":{"listChanged":false}},"serverInfo":{"name":"inkbolt","version":env!("CARGO_PKG_VERSION")},"instructions":format!("Local graphics engine. Use schema.lookup with name index to discover commands; request one command or type and select a listed variant/definition. Large schemas are outlined unless full:true. {} Preserve source files. Use durable session request IDs and expected revisions for safe edits. Export publication is create-only. Read tool errors and unsupported semantics. Stdio has no network listener; paths run with the launching user's permissions.", if mode == CatalogMode::Core { "This compact catalog defers shared types; inkbolt_run reaches every engine command with unchanged arguments and validation." } else { "Every engine command has a direct tool. A compact catalog is available with mcp --tools core." })}}),
                )?;
                continue;
            }
            if method == "ping" {
                send(&output, &json!({"jsonrpc":"2.0","id":id,"result":{}}))?;
                continue;
            }
            if !ready {
                send(
                    &output,
                    &protocol_error(
                        Some(id),
                        -32000,
                        "Initialize and send notifications/initialized before using tools",
                    ),
                )?;
                continue;
            }
            match method {
                "tools/list" => {
                    let start = match params.get("cursor") {
                        None => 0,
                        Some(Value::String(s)) => match s
                            .strip_prefix(mode.cursor())
                            .and_then(|s| s.parse::<usize>().ok())
                        {
                            Some(n) if n < tools.len() && n % PAGE == 0 => n,
                            _ => {
                                send(
                                    &output,
                                    &protocol_error(Some(id), -32602, "Invalid tool-list cursor"),
                                )?;
                                continue;
                            }
                        },
                        _ => {
                            send(
                                &output,
                                &protocol_error(Some(id), -32602, "Invalid tool-list cursor"),
                            )?;
                            continue;
                        }
                    };
                    let mut result = json!({"tools":tools.values().skip(start).take(PAGE).map(|(_,v)|v).collect::<Vec<_>>()});
                    if start + PAGE < tools.len() {
                        result["nextCursor"] = json!(format!("{}{}", mode.cursor(), start + PAGE));
                    }
                    send(&output, &json!({"jsonrpc":"2.0","id":id,"result":result}))?;
                }
                "tools/call" => {
                    let Some((command, _)) = params
                        .get("name")
                        .and_then(Value::as_str)
                        .and_then(|n| tools.get(n))
                    else {
                        send(
                            &output,
                            &protocol_error(
                                Some(id),
                                -32602,
                                "Unknown Inkbolt tool; inspect tools/list",
                            ),
                        )?;
                        continue;
                    };
                    if params.contains_key("task") {
                        send(
                            &output,
                            &protocol_error(
                                Some(id),
                                -32602,
                                "Task-augmented execution is unsupported",
                            ),
                        )?;
                        continue;
                    }
                    let mut args = match params.get("arguments") {
                        None => Map::new(),
                        Some(Value::Object(args)) => args.clone(),
                        _ => {
                            send(
                                &output,
                                &protocol_error(
                                    Some(id),
                                    -32602,
                                    "Tool arguments must be an object",
                                ),
                            )?;
                            continue;
                        }
                    };
                    let format = match args.remove("response_format") {
                        None => ResponseFormat::Json,
                        Some(Value::String(s)) if s == "json" => ResponseFormat::Json,
                        Some(Value::String(s)) if s == "markdown" => ResponseFormat::Markdown,
                        Some(Value::String(s)) if s == "preview" => ResponseFormat::Preview,
                        _ => {
                            send(
                                &output,
                                &json!({"jsonrpc":"2.0","id":id,"result":tool_result(Err(Error::new("INVALID_REQUEST","response_format must be json, markdown or preview")),ResponseFormat::Json,"")}),
                            )?;
                            continue;
                        }
                    };
                    let request = match dispatch_arguments(command, args) {
                        Ok(r) => r,
                        Err(e) => {
                            send(
                                &output,
                                &json!({"jsonrpc":"2.0","id":id,"result":tool_result(Err(e),format,"")}),
                            )?;
                            continue;
                        }
                    };
                    let control = Control::new(&Options {
                        timeout_ms: Some(60000),
                        cancel_file: None,
                    })
                    .unwrap();
                    let mut pending = active.lock().unwrap();
                    if pending.len() >= MAX_PENDING {
                        send(
                            &output,
                            &protocol_error(
                                Some(id),
                                -32000,
                                "Tool queue is full; wait for an outstanding request before retrying",
                            ),
                        )?;
                        continue;
                    }
                    pending.insert(key.clone(), control.clone());
                    drop(pending);
                    if tx
                        .try_send(Job {
                            id: id.clone(),
                            key: key.clone(),
                            request,
                            control,
                            format,
                        })
                        .is_err()
                    {
                        active.lock().unwrap().remove(&key);
                        send(
                            &output,
                            &protocol_error(Some(id), -32603, "Engine worker is unavailable"),
                        )?;
                    }
                }
                _ => send(
                    &output,
                    &protocol_error(Some(id), -32601, "Method is not supported by this server"),
                )?,
            }
        }
        Ok(())
    })();
    for control in active.lock().unwrap().values() {
        control.cancel();
    }
    drop(tx);
    let _ = worker.join();
    result
}
