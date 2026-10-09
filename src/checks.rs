//! Actionable, bounded read-only diagnostics using the engine's own validators.
use crate::{Document, Error, control::Control, fonts, model::*, sessions::Resources, text};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

pub const MAX_ISSUES: usize = 256;
pub const MAX_REPORT_BYTES: usize = 128 * 1024;

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(default, deny_unknown_fields)]
pub struct Options {
    pub resources: bool,
    pub typography: bool,
    pub issue_limit: usize,
}
impl Default for Options {
    fn default() -> Self {
        Self {
            resources: true,
            typography: true,
            issue_limit: 64,
        }
    }
}

pub(crate) fn interrupted(error: &Error) -> bool {
    matches!(error.code, "CANCELLED" | "TIMEOUT")
}

fn recovery(code: &str) -> Value {
    let (message, commands) = match code {
        "ALPHA_POLICY_REQUIRED" => (
            "Choose an explicit RGB matte for this opaque output, or select a format that preserves transparency. The source document remains unchanged.",
            vec!["schema.lookup", "document.preflight"],
        ),
        "TEXT_OVERFLOW" | "STORY_OVERFLOW" | "STORY_FRAME_OVERFLOW" => (
            "Preserve the text and enlarge or add flow space; use layout inspection to review the result. An explicit clip/visible/retained-tail policy changes delivery semantics.",
            vec![
                "text.inspect",
                "story.inspect",
                "schema.lookup",
                "session.dry_run",
            ],
        ),
        "OUTPUT_EXISTS" => (
            "Choose a new destination filename and repeat preflight. Existing output is preserved.",
            vec!["document.preflight"],
        ),
        "FONT_ROOT_REQUIRED" | "FONT_MISSING" | "FONT_CORRUPT" | "INVALID_FONT_LICENSE" => (
            "Resolve the pinned font and retained license in the intended font store, or explicitly import and relink a reviewed replacement.",
            vec!["font.verify", "font.import", "session.dry_run"],
        ),
        "ASSET_ROOT_REQUIRED" | "ASSET_MISSING" | "ASSET_CORRUPT" | "ASSET_HASH_MISMATCH" => (
            "Resolve the exact image bytes in the intended asset store, or explicitly import and relink a reviewed replacement.",
            vec!["asset.verify", "asset.import", "session.dry_run"],
        ),
        "RESOURCE_LIMIT" => (
            "Inspect the stated limit. Reduce the requested evaluation, split delivery, or choose an implemented resource profile where applicable; source storage and rendering limits are independent.",
            vec!["capabilities", "schema.lookup", "document.preview"],
        ),
        "HDR_VIEW_REQUIRED" => (
            "Choose an explicit supported HDR display view for byte-image delivery, or use a supported native-precision output.",
            vec!["schema.lookup", "document.preflight"],
        ),
        "FONT_AXIS_RANGE" | "FONT_AXIS_UNAVAILABLE" => (
            "Inspect the pinned font's available axes and ranges, then revise the requested coordinates explicitly.",
            vec!["font.inspect", "session.dry_run"],
        ),
        "IO_ERROR" => (
            "Check the supplied local roots and source paths. Preflight does not reserve a destination or prove write permission or hard-link support.",
            vec!["schema.lookup", "document.preflight"],
        ),
        _ => (
            "Use the reported code, location and message to inspect the affected input and supported schema. Review any repair through a session dry run before applying it.",
            vec!["schema.lookup", "document.inspect.page", "session.dry_run"],
        ),
    };
    json!({"message":message,"commands":commands,"automatic_fix":false})
}

pub(crate) fn diagnostic(error: Error, severity: &str, location: Value, context: Value) -> Value {
    json!({"severity":severity,"recovery":recovery(error.code),"error":error,"location":location,"context":context})
}
fn escape(value: &str) -> String {
    value.replace('~', "~0").replace('/', "~1")
}
fn location(objects: &[String], pointer: &str) -> Value {
    json!({"retained_document_path":objects,"pointer":pointer})
}

fn validate_styles<'a>(
    styles: impl Iterator<Item = &'a text::Style>,
    d: &Document,
    cache: &fonts::Cache,
) -> Result<(), Error> {
    for style in styles {
        for (id, coordinates) in &style.font_variations {
            fonts::instance(&d.fonts[id], &cache[id], Some(coordinates))
                .map_err(|e| e.at_font(id))?;
        }
    }
    Ok(())
}

#[derive(Default, Serialize)]
struct Counts {
    documents: usize,
    images: usize,
    fonts: usize,
    text_frames: usize,
    stories: usize,
    skipped_layouts: usize,
}
struct Report<'a> {
    options: &'a Options,
    control: &'a Control,
    resources: &'a Resources,
    issues: Vec<Value>,
    issue_bytes: usize,
    stopped: bool,
    counts: Counts,
    glyphs: usize,
    commands: usize,
}
impl Report<'_> {
    fn issue(
        &mut self,
        error: Error,
        severity: &str,
        at: Value,
        context: Value,
    ) -> Result<(), Error> {
        if interrupted(&error) {
            return Err(error);
        }
        let issue = diagnostic(error, severity, at, context);
        let bytes = serde_json::to_vec(&issue).unwrap().len();
        if self.issues.len() >= self.options.issue_limit
            || self.issue_bytes + bytes > MAX_REPORT_BYTES - 8192
        {
            self.stopped = true;
        } else {
            self.issue_bytes += bytes;
            self.issues.push(issue);
        }
        Ok(())
    }
    fn charge(&mut self, layout: &text::Layout, at: Value) -> Result<(), Error> {
        self.glyphs += layout.glyphs.len();
        self.commands += layout
            .paths
            .iter()
            .map(|p| match &p.geometry {
                Geometry::Path { commands } => commands.len(),
                _ => 0,
            })
            .sum::<usize>();
        if self.glyphs > text::MAX_GLYPHS || self.commands > text::MAX_OUTLINE_COMMANDS {
            self.issue(
                Error::new(
                    "RESOURCE_LIMIT",
                    "Diagnostic layouts exceed the shared glyph or outline budget",
                ),
                "error",
                at,
                Value::Null,
            )?;
            self.stopped = true;
        }
        Ok(())
    }
    fn document(&mut self, d: &Document, objects: &[String]) -> Result<(), Error> {
        self.control.check()?;
        if self.stopped {
            return Ok(());
        }
        self.counts.documents += 1;
        if self.options.resources {
            for (id, asset) in &d.assets {
                self.control.check()?;
                if self.stopped {
                    return Ok(());
                }
                self.counts.images += 1;
                if let Err(error) = crate::assets::load(asset, self.resources.asset_root.as_deref())
                {
                    self.issue(
                        error.at_asset(id),
                        "error",
                        location(objects, &format!("/assets/{}", escape(id))),
                        json!({"expected_sha256":asset.sha256}),
                    )?;
                }
            }
        }
        let mut cache = fonts::Cache::new();
        if self.options.resources || self.options.typography {
            for (id, font) in &d.fonts {
                self.control.check()?;
                if self.stopped {
                    return Ok(());
                }
                self.counts.fonts += 1;
                match fonts::load(font,self.resources.font_root.as_deref()) {
                    Ok(bytes) => { if self.options.typography { cache.insert(id.clone(),bytes); } },
                    Err(error) => self.issue(error.at_font(id),"error",location(objects,&format!("/fonts/{}",escape(id))),json!({"expected_sha256":font.sha256,"expected_license_sha256":font.license_sha256}))?,
                }
            }
        }
        if self.options.typography {
            for (id, story) in &d.stories {
                self.control.check()?;
                if self.stopped {
                    return Ok(());
                }
                let at = location(objects, &format!("/stories/{}", escape(id)));
                if story
                    .styles()
                    .flat_map(text::Style::font_ids)
                    .any(|id| !cache.contains_key(id))
                {
                    self.counts.skipped_layouts += 1;
                    continue;
                }
                self.counts.stories += 1;
                match validate_styles(story.styles(), d, &cache)
                    .and_then(|_| text::flow::layout(story, d, &cache))
                {
                    Ok(layout) => {
                        for (slot_id, slot) in &layout.slots {
                            self.charge(slot, at.clone())?;
                            if self.stopped {
                                return Ok(());
                            }
                            if slot.overflowed {
                                self.issue(Error::new("STORY_FRAME_OVERFLOW","Story glyph ink exceeds a flow frame"),"warning",at.clone(),json!({"story_id":id,"slot_id":slot_id,"ink_bounds":slot.ink_bounds}))?;
                            }
                        }
                        if layout.overset.is_some() {
                            self.issue(Error::new("STORY_OVERFLOW","Story has unplaced text"),if story.overset==text::flow::Overset::Error {"error"}else{"warning"},at,
                                json!({"story_id":id,"overset":layout.overset,"policy":story.overset,"indices":layout.indices}))?;
                        }
                    }
                    Err(error) => self.issue(error, "error", at, json!({"story_id":id}))?,
                }
            }
            for (index, item) in d.items.iter().enumerate() {
                self.content_text(
                    &item.content,
                    d,
                    &cache,
                    objects,
                    &format!("/items/{index}/content"),
                    &item.id,
                )?;
                if self.stopped {
                    return Ok(());
                }
            }
        }
        drop(cache); // Never retain ancestor font caches while checking nested snapshots.
        for (index, item) in d.items.iter().enumerate() {
            self.content_objects(&item.content, objects, &format!("/items/{index}/content"))?;
            if self.stopped {
                break;
            }
        }
        Ok(())
    }
    fn content_text(
        &mut self,
        content: &Content,
        d: &Document,
        cache: &fonts::Cache,
        objects: &[String],
        pointer: &str,
        item_id: &str,
    ) -> Result<(), Error> {
        self.control.check()?;
        if self.stopped {
            return Ok(());
        }
        match content {
            Content::Text { frame } => {
                if text::styles(frame)
                    .flat_map(text::Style::font_ids)
                    .any(|id| !cache.contains_key(id))
                {
                    self.counts.skipped_layouts += 1;
                    return Ok(());
                }
                self.counts.text_frames += 1;
                let at = location(objects, pointer);
                let context = json!({"item_id":item_id,"frame_size":[frame.width,frame.height],"text_scalars":frame.text.chars().count(),"overflow_policy":frame.overflow});
                match validate_styles(text::styles(frame), d, cache)
                    .and_then(|_| text::layout(frame, d, cache))
                {
                    Ok(layout) => {
                        self.charge(&layout, at.clone())?;
                        if layout.overflowed {
                            self.issue(
                                Error::new(
                                    "TEXT_OVERFLOW",
                                    "Text exceeds its declared frame or baseline",
                                )
                                .at_item(item_id),
                                "warning",
                                at,
                                context,
                            )?;
                        }
                    }
                    Err(error) => self.issue(error.at_item(item_id), "error", at, context)?,
                }
            }
            Content::Instance { instance } => {
                for (id, over) in &instance.overrides {
                    if let Some(content) = &over.content {
                        self.content_text(
                            content,
                            d,
                            cache,
                            objects,
                            &format!("{pointer}/instance/overrides/{}/content", escape(id)),
                            item_id,
                        )?;
                    }
                    if self.stopped {
                        break;
                    }
                }
            }
            _ => {}
        }
        Ok(())
    }
    fn content_objects(
        &mut self,
        content: &Content,
        objects: &[String],
        pointer: &str,
    ) -> Result<(), Error> {
        self.control.check()?;
        if self.stopped {
            return Ok(());
        }
        match content {
            Content::Object { object } => {
                let nested = object.document()?;
                let mut path = objects.to_vec();
                path.push(format!("{pointer}/object/snapshot"));
                self.document(&nested, &path)?;
            }
            Content::Instance { instance } => {
                for (id, over) in &instance.overrides {
                    if let Some(content) = &over.content {
                        self.content_objects(
                            content,
                            objects,
                            &format!("{pointer}/instance/overrides/{}/content", escape(id)),
                        )?;
                    }
                    if self.stopped {
                        break;
                    }
                }
            }
            _ => {}
        }
        Ok(())
    }
}

pub fn check(
    document: &Document,
    options: &Options,
    resources: &Resources,
    control: &Control,
) -> Result<Value, Error> {
    control.check()?;
    resources.validate()?;
    control.check_resource_paths(resources)?;
    if !(1..=MAX_ISSUES).contains(&options.issue_limit) {
        return Err(Error::new("INVALID_REQUEST", "issue_limit must be 1..=256"));
    }
    let mut report = Report {
        options,
        control,
        resources,
        issues: vec![],
        issue_bytes: 0,
        stopped: false,
        counts: Default::default(),
        glyphs: 0,
        commands: 0,
    };
    let valid = match crate::model::validate_controlled(document, control) {
        Ok(()) => true,
        Err(error) => {
            report.issue(error, "error", location(&[], ""), Value::Null)?;
            false
        }
    };
    if valid {
        report.document(document, &[])?;
    }
    control.check()?;
    let complete = valid && !report.stopped && report.counts.skipped_layouts == 0;
    let errors = report
        .issues
        .iter()
        .filter(|i| i["severity"] == "error")
        .count();
    let warnings = report.issues.len() - errors;
    let status = if errors > 0 {
        "fail"
    } else if !complete {
        "incomplete"
    } else if warnings > 0 {
        "warnings"
    } else {
        "pass"
    };
    Ok(
        json!({"version":1,"document_id":valid.then_some(&document.id),"revision":document.revision,
        "document_sha256":valid.then(||crate::assets::sha256(&serde_json::to_vec(document).unwrap())),
        "status":status,"complete":complete,"valid_structure":valid,"reported_errors":errors,"reported_warnings":warnings,
        "stopped_at_limit":report.stopped,"checks":options,"checked":report.counts,"issues":report.issues,"source_changed":false,
        "semantics":"Checks retained structure, requested resource registries (including unused resources) and authored text/stories/overrides, recursively through retained snapshots. Typography reads registered fonts. Missing fonts skip dependent layouts explicitly. Hidden and definition content are included. External object links are not refreshed or read. This is not a delivery or visual-quality certificate; run document.preflight for actual export preparation."}),
    )
}

pub fn preflight(
    document: &Document,
    resources: &Resources,
    output: &crate::publish::Options,
    control: &Control,
) -> Result<Value, Error> {
    control.check()?;
    match crate::publish::preflight(document, resources, output, control) {
        Ok(receipt) => Ok(
            json!({"version":1,"ready":true,"document_sha256":crate::assets::sha256(&serde_json::to_vec(document).unwrap()),"prepared_output":receipt,"issues":[],"source_changed":false,
            "semantics":"Actual output encoded without writing or reserving files. Source/resource changes, concurrent publishers, permissions and hard-link support can still prevent later publication."}),
        ),
        Err(error) if interrupted(&error) => Err(error),
        Err(error) => Ok(json!({"version":1,"ready":false,"prepared_output":null,
            "issues":[diagnostic(error,"error",json!({"command":"document.publish"}),Value::Null)],"source_changed":false})),
    }
}
