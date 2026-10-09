//! Create-only output publication; rendering finishes before any destination appears.
use crate::{Document, Error, ExportFormat, assets, control::Control, sessions::Resources};
use base64::{Engine, engine::general_purpose::STANDARD};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    fs::{self, OpenOptions},
    io::Write,
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
};

pub const MAX_OUTPUT_BYTES: usize = 32 * 1024 * 1024;
static TEMP: AtomicU64 = AtomicU64::new(0);
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Options {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub render_options: Option<crate::render_quality::Options>,
    pub metadata_policy: Option<crate::metadata::Policy>,
    #[serde(default)]
    pub image_options: Option<crate::image_io::Options>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub pdf_options: Option<crate::pdf::Options>,
    pub output_root: PathBuf,
    pub file_name: String,
    pub format: ExportFormat,
    #[serde(default = "crate::scale")]
    pub scale: u32,
    pub artboard_id: Option<String>,
    #[serde(default)]
    pub include_bleed: bool,
}
pub(crate) fn destination(options: &Options) -> Result<PathBuf, Error> {
    assets::absolute(&options.output_root)?;
    let name = &options.file_name;
    let stem = name.split('.').next().unwrap_or("").to_ascii_uppercase();
    let reserved = matches!(stem.as_str(), "CON" | "PRN" | "AUX" | "NUL")
        || (stem.len() == 4
            && (stem.starts_with("COM") || stem.starts_with("LPT"))
            && matches!(stem.as_bytes()[3], b'1'..=b'9'));
    if !crate::model::valid_id(name)
        || name.ends_with('.')
        || reserved
        || name.starts_with(".inkbolt-output-")
        || name.starts_with(".inkbolt-publication-")
    {
        return Err(Error::new(
            "INVALID_REQUEST",
            "Output file_name must be a portable single filename, without reserved names or a trailing dot",
        ));
    }
    let extensions: &[&str] = match options.format {
        ExportFormat::Layered => &[".psd"],
        ExportFormat::LayeredLarge => &[".psb"],
        ExportFormat::Gif => &[".gif"],
        ExportFormat::Bmp => &[".bmp"],
        ExportFormat::Tga => &[".tga"],
        ExportFormat::Pdf => &[".pdf"],
        ExportFormat::Apng => &[".png", ".apng"],
        ExportFormat::Png => &[".png"],
        ExportFormat::Jpeg => &[".jpg", ".jpeg"],
        ExportFormat::Tiff => &[".tif", ".tiff"],
        ExportFormat::Svg => &[".svg"],
        ExportFormat::Snapshot => &[".json"],
    };
    if !extensions
        .iter()
        .any(|ext| name.to_ascii_lowercase().ends_with(ext))
    {
        return Err(Error::new(
            "INVALID_REQUEST",
            "Output filename extension must match the export format",
        ));
    }
    let target = options.output_root.join(name);
    if target.as_os_str().len() > 4096 {
        return Err(crate::model::limit("Output path exceeds its length limit"));
    }
    Ok(target)
}
pub(crate) fn exists(target: &Path) -> Result<(), Error> {
    match fs::symlink_metadata(target) {
        Ok(_) => Err(Error::new(
            "OUTPUT_EXISTS",
            "Destination already exists; choose a new filename. Existing files are never overwritten",
        )),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(_) => Err(Error::new(
            "IO_ERROR",
            "Unable to inspect output destination",
        )),
    }
}
struct Temporary(PathBuf);
impl Drop for Temporary {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.0);
    }
}

pub fn export(
    document: &Document,
    format: ExportFormat,
    scale: u32,
    resources: &Resources,
) -> Result<Value, Error> {
    export_with_options(document, format, scale, resources, None)
}
pub fn export_with_options(
    document: &Document,
    format: ExportFormat,
    scale: u32,
    resources: &Resources,
    image_options: Option<&crate::image_io::Options>,
) -> Result<Value, Error> {
    export_with_metadata(document, format, scale, resources, image_options, None)
}
pub fn export_with_metadata(
    document: &Document,
    format: ExportFormat,
    scale: u32,
    resources: &Resources,
    image_options: Option<&crate::image_io::Options>,
    metadata_policy: Option<crate::metadata::Policy>,
) -> Result<Value, Error> {
    export_with_format_options(
        document,
        format,
        scale,
        resources,
        image_options,
        metadata_policy,
        None,
    )
}
#[derive(Default)]
pub struct FormatOptions<'a> {
    pub control: Option<&'a Control>,
    pub image_options: Option<&'a crate::image_io::Options>,
    pub pdf_options: Option<&'a crate::pdf::Options>,
    pub render_options: Option<&'a crate::render_quality::Options>,
    pub metadata_policy: Option<crate::metadata::Policy>,
}
pub fn export_with_format_options(
    document: &Document,
    format: ExportFormat,
    scale: u32,
    resources: &Resources,
    image_options: Option<&crate::image_io::Options>,
    metadata_policy: Option<crate::metadata::Policy>,
    pdf_options: Option<&crate::pdf::Options>,
) -> Result<Value, Error> {
    export_with_render_options(
        document,
        format,
        scale,
        resources,
        FormatOptions {
            control: None,
            image_options,
            metadata_policy,
            pdf_options,
            render_options: None,
        },
    )
}
pub fn export_with_render_options(
    document: &Document,
    format: ExportFormat,
    scale: u32,
    resources: &Resources,
    options: FormatOptions<'_>,
) -> Result<Value, Error> {
    let FormatOptions {
        control,
        image_options,
        metadata_policy,
        pdf_options,
        render_options,
    } = options;
    crate::render_quality::validate_format(format, render_options)?;
    crate::model::validate_controlled(document, control.unwrap_or(&Control::default()))?;
    crate::image_io::validate_options(format, image_options)?;
    if matches!(format, ExportFormat::Pdf) {
        if scale != 1 {
            return Err(Error::new(
                "UNSUPPORTED",
                "PDF uses physical page units; scale must be 1",
            ));
        }
        let mut artifact = crate::pdf::export_controlled(
            document,
            resources,
            pdf_options.unwrap_or(&crate::pdf::Options::default()),
            metadata_policy,
            control,
        )?;
        crate::variants::annotate_export(document.variants.as_ref(), &mut artifact, false);
        return Ok(artifact);
    }
    if pdf_options.is_some() {
        return Err(Error::new(
            "INVALID_REQUEST",
            "pdf_options requires PDF format",
        ));
    }
    let snapshot = matches!(format, ExportFormat::Snapshot);
    let mut packet =
        crate::metadata::packet(document, format, scale, metadata_policy.unwrap_or_default())?;
    let render_plan = render_options
        .map(|o| crate::render_quality::Plan::for_document(document, scale, Some(o)))
        .transpose()?;
    if let (Some(packet), Some(plan)) = (&mut packet, &render_plan) {
        let mut value: Value = serde_json::from_str(packet)
            .map_err(|_| Error::new("EXPORT_ERROR", "Invalid metadata envelope"))?;
        value["delivery"]["width"] = json!(plan.output[0]);
        value["delivery"]["height"] = json!(plan.output[1]);
        value["delivery"]["render_settings"] = plan.receipt();
        *packet = value.to_string();
    }
    let sanitized = if snapshot {
        metadata_policy.map(|p| crate::metadata::sanitized(document, p.mode))
    } else {
        None
    };
    let document = sanitized.as_ref().unwrap_or(document);
    crate::image_io::validate_options(format, image_options)?;
    let mut artifact = match format {
        ExportFormat::Layered | ExportFormat::LayeredLarge => {
            if scale != 1 || packet.is_some() {
                return Err(Error::new(
                    "UNSUPPORTED_LAYERED_SEMANTICS",
                    "Layered delivery requires scale 1 and explicit stripped descriptive metadata",
                ));
            }
            crate::layered::export_versioned(
                document,
                crate::layered::Compression::Rle,
                if matches!(format, ExportFormat::LayeredLarge) {
                    crate::layered::Version::Large
                } else {
                    crate::layered::Version::Standard
                },
                control.unwrap_or(&Control::default()),
            )
        }
        ExportFormat::Pdf => unreachable!("PDF was handled above"),
        ExportFormat::Gif => crate::sequences::export_gif(
            document,
            resources,
            scale,
            render_options,
            packet.as_deref(),
            control.unwrap_or(&Control::default()),
        ),
        ExportFormat::Apng => crate::sequences::export(
            document,
            resources,
            scale,
            render_options,
            control.unwrap_or(&Control::default()),
        ),
        ExportFormat::Jpeg | ExportFormat::Tiff | ExportFormat::Bmp | ExportFormat::Tga => {
            crate::image_io::export_with_metadata(
                document,
                format,
                scale,
                resources,
                image_options,
                packet.as_deref(),
                (render_options, control.unwrap_or(&Control::default())),
            )
        }
        ExportFormat::Png => crate::render::png_controlled(
            document,
            scale,
            resources.asset_root.as_deref(),
            resources.font_root.as_deref(),
            render_options,
            control.unwrap_or(&Control::default()),
        ),
        ExportFormat::Svg => {
            if scale != 1 {
                return Err(Error::new(
                    "UNSUPPORTED",
                    "SVG export uses document units; scale must be 1",
                ));
            }
            crate::svg::export_controlled(
                document,
                resources.asset_root.as_deref(),
                resources.font_root.as_deref(),
                control.unwrap_or(&Control::default()),
            )
        }
        ExportFormat::Snapshot => {
            crate::model::validate_controlled(document, control.unwrap_or(&Control::default()))?;
            if scale != 1 {
                return Err(Error::new(
                    "UNSUPPORTED",
                    "Snapshot export does not rescale content",
                ));
            }
            Ok(
                json!({"media_type":"application/vnd.inkbolt.document+json","encoding":"utf8","data":serde_json::to_string(document).map_err(|_|Error::new("EXPORT_ERROR","Unable to encode snapshot"))?}),
            )
        }
    }?;
    if !snapshot {
        crate::swatches::annotate(document, &mut artifact)?;
    }
    if let Some(plan) = render_plan {
        artifact["render_settings"] = plan.receipt();
    }
    if let Some(packet) = &packet {
        crate::metadata::embed(&mut artifact, format, packet)?;
    }
    crate::metadata::annotate(&mut artifact, packet.as_deref(), metadata_policy, snapshot);
    crate::variants::annotate_export(
        document.variants.as_ref(),
        &mut artifact,
        matches!(format, ExportFormat::Snapshot),
    );
    if let Some(control) = control {
        control.check()?;
    }
    Ok(artifact)
}
pub(crate) struct PreparedOutput {
    pub target: PathBuf,
    pub bytes: Vec<u8>,
    pub receipt: Value,
}
pub(crate) fn prepare_publication(
    document: &Document,
    resources: &Resources,
    options: &Options,
    control: &Control,
) -> Result<PreparedOutput, Error> {
    resources.validate()?;
    control.check_resource_paths(resources)?;
    let target = destination(options)?;
    exists(&target)?;
    control.check()?;
    crate::model::validate_controlled(document, control)?;
    let single_pdf = matches!(options.format, ExportFormat::Pdf) && options.artboard_id.is_some();
    let pdf_options = if single_pdf {
        if options.pdf_options.is_some() {
            return Err(Error::new(
                "INVALID_REQUEST",
                "Choose artboard_id or pdf_options, not both",
            ));
        }
        Some(crate::pdf::Options {
            artboards: Some(crate::boards::Selection::Ids {
                ids: vec![options.artboard_id.clone().unwrap()],
            }),
            include_bleed: options.include_bleed,
            color: crate::pdf::ColorDelivery::Display,
            print: None,
            ink_recipe: None,
            prepress: None,
        })
    } else {
        options.pdf_options.clone()
    };
    let board = if single_pdf {
        None
    } else if let Some(id) = &options.artboard_id {
        if matches!(options.format, ExportFormat::Snapshot | ExportFormat::Apng) {
            return Err(Error::new(
                "UNSUPPORTED",
                "Artboard publication requires a still image or SVG; publish the complete snapshot or sequence separately",
            ));
        }
        Some(crate::boards::standalone(
            document,
            id,
            options.include_bleed,
        )?)
    } else {
        if options.include_bleed {
            return Err(Error::new(
                "INVALID_REQUEST",
                "include_bleed requires artboard_id",
            ));
        }
        None
    };
    let mut artifact = export_with_render_options(
        board.as_ref().unwrap_or(document),
        options.format,
        options.scale,
        resources,
        FormatOptions {
            control: Some(control),
            image_options: options.image_options.as_ref(),
            metadata_policy: options.metadata_policy,
            pdf_options: pdf_options.as_ref(),
            render_options: options.render_options.as_ref(),
        },
    )?;
    crate::variants::annotate_export(
        document.variants.as_ref(),
        &mut artifact,
        matches!(options.format, ExportFormat::Snapshot),
    );
    control.check()?;
    let data = artifact["data"]
        .as_str()
        .ok_or_else(|| Error::new("EXPORT_ERROR", "Export omitted encoded data"))?;
    if data.len() > MAX_OUTPUT_BYTES * 4 / 3 + 4 {
        return Err(crate::model::limit("Export exceeds publication byte limit"));
    }
    let bytes = if artifact["encoding"] == "base64" {
        STANDARD
            .decode(data)
            .map_err(|_| Error::new("EXPORT_ERROR", "Export returned invalid encoding"))?
    } else {
        data.as_bytes().to_vec()
    };
    if bytes.len() > MAX_OUTPUT_BYTES {
        return Err(crate::model::limit("Export exceeds publication byte limit"));
    }
    let checksum = assets::sha256(&bytes);
    // The root must already exist. Never create a directory in place of a source path.
    if !options.output_root.is_dir() {
        return Err(Error::new(
            "IO_ERROR",
            "Output root must be an existing local directory",
        ));
    }
    let mut receipt = json!({"created":false,"path":target,"document_id":document.id,"revision":document.revision,"artboard_id":options.artboard_id,"include_bleed":pdf_options.as_ref().map_or(options.include_bleed, |p| p.include_bleed),"format":options.format,"scale":options.scale,"media_type":artifact["media_type"],"bytes":bytes.len(),"sha256":checksum,"losses":artifact.get("losses").cloned().unwrap_or(json!([]))});
    if let Some(settings) = artifact.get("settings") {
        receipt["settings"] = settings.clone();
    }
    for field in [
        "sequence",
        "sample_precision",
        "swatches",
        "render_settings",
        "metadata",
        "metadata_envelope",
        "mesh_textures",
        "text_paths",
        "pages",
        "pdf",
        "inks",
    ] {
        if let Some(value) = artifact.get(field) {
            receipt[field] = value.clone();
        }
    }
    if let Some(profile) = artifact.get("color_profile") {
        receipt["color_profile"] = profile.clone();
    }
    crate::variants::annotate_export(
        document.variants.as_ref(),
        &mut receipt,
        matches!(options.format, ExportFormat::Snapshot),
    );
    Ok(PreparedOutput {
        target,
        bytes,
        receipt,
    })
}

/// Prepare exact output and inspect its destination without writing or reserving it.
pub fn preflight(
    document: &Document,
    resources: &Resources,
    options: &Options,
    control: &Control,
) -> Result<Value, Error> {
    let prepared = prepare_publication(document, resources, options, control)?;
    control.check()?;
    Ok(prepared.receipt)
}

pub fn publish(
    document: &Document,
    resources: &Resources,
    options: &Options,
    control: &Control,
) -> Result<Value, Error> {
    let PreparedOutput {
        target,
        bytes,
        mut receipt,
    } = prepare_publication(document, resources, options, control)?;
    let mut reserved = None;
    for _ in 0..64 {
        let path = options.output_root.join(format!(
            ".inkbolt-output-{}-{}.tmp",
            std::process::id(),
            TEMP.fetch_add(1, Ordering::Relaxed)
        ));
        match OpenOptions::new().write(true).create_new(true).open(&path) {
            Ok(file) => {
                reserved = Some((Temporary(path), file));
                break;
            }
            Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(_) => {
                return Err(Error::new(
                    "IO_ERROR",
                    "Unable to reserve output temporary file",
                ));
            }
        }
    }
    let (temp, mut file) = reserved
        .ok_or_else(|| Error::new("IO_ERROR", "Output temporary-name retry limit exceeded"))?;
    for chunk in bytes.chunks(65536) {
        control.check()?;
        file.write_all(chunk)
            .map_err(|_| Error::new("IO_ERROR", "Unable to write export temporary file"))?;
    }
    file.sync_all()
        .map_err(|_| Error::new("IO_ERROR", "Unable to flush export temporary file"))?;
    drop(file);
    #[cfg(test)]
    fault_point("before_publish");
    control.check()?;
    match fs::hard_link(&temp.0, &target) {
        Ok(()) => {}
        Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => {
            return Err(Error::new(
                "OUTPUT_EXISTS",
                "Destination already exists; choose a new filename. Existing files are never overwritten",
            ));
        }
        Err(_) => {
            exists(&target)?;
            return Err(Error::new(
                "IO_ERROR",
                "Output root must support create-only hard-link publication",
            ));
        }
    }
    #[cfg(test)]
    fault_point("after_publish");
    // Publication is the commit point; late cancellation cannot undo a completed export.
    receipt["created"] = json!(true);
    Ok(receipt)
}

#[cfg(test)]
fn fault_point(stage: &str) {
    if std::env::var("INKBOLT_PUBLISH_TEST_STAGE").ok().as_deref() != Some(stage) {
        return;
    }
    if let Some(root) = std::env::var_os("INKBOLT_PUBLISH_TEST_ROOT") {
        let root = PathBuf::from(root);
        fs::write(root.join("ready"), b"ready").unwrap();
        while !root.join("release").exists() {
            std::thread::sleep(std::time::Duration::from_millis(5));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        process::{Child, Command, Stdio},
        time::{Duration, Instant},
    };
    struct Owned {
        root: PathBuf,
        child: Option<Child>,
    }
    impl Drop for Owned {
        fn drop(&mut self) {
            if let Some(child) = &mut self.child {
                let _ = child.kill();
                let _ = child.wait();
            }
            let base = std::env::temp_dir().canonicalize().unwrap();
            let target = self.root.canonicalize().unwrap();
            assert_eq!(target.parent(), Some(base.as_path()));
            assert!(
                target
                    .file_name()
                    .unwrap()
                    .to_string_lossy()
                    .starts_with("inkbolt-publish-test-")
            );
            fs::remove_dir_all(target).unwrap();
        }
    }
    fn document() -> Document {
        serde_json::from_value(json!({"schema_version":2,"id":"original","kind":"raster","width":2,"height":2,"color_space":"srgb"})).unwrap()
    }
    fn options(root: &Path) -> Options {
        Options {
            render_options: None,
            pdf_options: None,
            metadata_policy: None,
            output_root: root.to_owned(),
            file_name: "result.png".into(),
            format: ExportFormat::Png,
            image_options: None,
            scale: 1,
            artboard_id: None,
            include_bleed: false,
        }
    }
    fn start(stage: &str, mode: &str) -> Owned {
        let root = std::env::temp_dir().canonicalize().unwrap().join(format!(
            "inkbolt-publish-test-{}-{}",
            std::process::id(),
            TEMP.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&root).unwrap();
        let mut owned = Owned { root, child: None };
        owned.child = Some(
            Command::new(std::env::current_exe().unwrap())
                .args([
                    "--exact",
                    "publish::tests::publication_worker",
                    "--nocapture",
                ])
                .env("INKBOLT_PUBLISH_TEST_ROOT", &owned.root)
                .env("INKBOLT_PUBLISH_TEST_STAGE", stage)
                .env("INKBOLT_PUBLISH_TEST_MODE", mode)
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn()
                .unwrap(),
        );
        let start = Instant::now();
        while !owned.root.join("ready").exists() {
            assert!(owned.child.as_mut().unwrap().try_wait().unwrap().is_none());
            assert!(start.elapsed() < Duration::from_secs(20));
            std::thread::sleep(Duration::from_millis(5));
        }
        owned
    }
    fn finish(owned: &mut Owned) {
        fs::write(owned.root.join("release"), b"release").unwrap();
        let start = Instant::now();
        loop {
            if let Some(status) = owned.child.as_mut().unwrap().try_wait().unwrap() {
                assert!(status.success());
                break;
            }
            assert!(start.elapsed() < Duration::from_secs(20));
            std::thread::sleep(Duration::from_millis(5));
        }
    }
    #[test]
    fn publication_worker() {
        let Some(root) = std::env::var_os("INKBOLT_PUBLISH_TEST_ROOT") else {
            return;
        };
        let root = PathBuf::from(root);
        let mode = std::env::var("INKBOLT_PUBLISH_TEST_MODE").unwrap();
        let control = Control::new(&crate::control::Options {
            timeout_ms: (mode == "timeout").then_some(500),
            cancel_file: Some(root.join("cancel")),
        })
        .unwrap();
        let result = publish(
            &document(),
            &Resources::default(),
            &options(&root),
            &control,
        );
        if mode == "cancel" {
            assert_eq!(result.unwrap_err().code, "CANCELLED");
        } else if mode == "timeout" {
            assert_eq!(result.unwrap_err().code, "TIMEOUT");
        } else {
            result.unwrap();
        }
    }
    #[test]
    fn cancel_or_timeout_after_flush_removes_temporary_and_publishes_nothing() {
        for mode in ["cancel", "timeout"] {
            let mut owned = start("before_publish", mode);
            assert!(!owned.root.join("result.png").exists());
            if mode == "cancel" {
                fs::write(owned.root.join("cancel"), b"cancel").unwrap();
            } else {
                std::thread::sleep(Duration::from_millis(550));
            }
            finish(&mut owned);
            assert!(!owned.root.join("result.png").exists());
            assert!(!fs::read_dir(&owned.root).unwrap().any(|e| {
                e.unwrap()
                    .file_name()
                    .to_string_lossy()
                    .starts_with(".inkbolt-output-")
            }));
        }
    }
    #[test]
    fn killed_prepublication_writer_leaves_no_destination_and_retry_preserves_orphan() {
        let mut owned = start("before_publish", "kill");
        owned.child.as_mut().unwrap().kill().unwrap();
        owned.child.as_mut().unwrap().wait().unwrap();
        assert!(!owned.root.join("result.png").exists());
        let orphan = fs::read_dir(&owned.root)
            .unwrap()
            .map(|e| e.unwrap().path())
            .find(|p| {
                p.file_name()
                    .unwrap()
                    .to_string_lossy()
                    .starts_with(".inkbolt-output-")
            })
            .unwrap();
        let bytes = fs::read(&orphan).unwrap();
        let receipt = publish(
            &document(),
            &Resources::default(),
            &options(&owned.root),
            &Control::default(),
        )
        .unwrap();
        assert_eq!(receipt["sha256"], assets::sha256(&bytes));
        assert_eq!(fs::read(&orphan).unwrap(), bytes);
        assert_eq!(fs::read(owned.root.join("result.png")).unwrap(), bytes);
    }
    #[test]
    fn late_cancellation_keeps_committed_output_and_success_receipt() {
        let mut owned = start("after_publish", "success");
        let before = fs::read(owned.root.join("result.png")).unwrap();
        fs::write(owned.root.join("cancel"), b"cancel").unwrap();
        finish(&mut owned);
        assert_eq!(fs::read(owned.root.join("result.png")).unwrap(), before);
    }
}
