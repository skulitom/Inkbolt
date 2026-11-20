//! Read-only installation diagnostics for the JSON CLI.
use inkbolt::{Error, control::Control, workspace::Workspace};
use serde_json::{Map, Value, json};
use std::{fs, io, path::Path};

#[cfg(any(windows, target_os = "linux", target_os = "macos"))]
fn allowed(result: io::Result<()>) -> Option<bool> {
    match result {
        Ok(()) => Some(true),
        Err(e)
            if matches!(
                e.kind(),
                io::ErrorKind::PermissionDenied | io::ErrorKind::ReadOnlyFilesystem
            ) =>
        {
            Some(false)
        }
        Err(_) => None,
    }
}

// Check permissions on the named directory with the current process credentials.
// A missing store is reported separately from its nearest existing parent.
#[cfg(windows)]
fn permissions(path: &Path) -> Value {
    use std::os::windows::fs::OpenOptionsExt;
    const FILE_LIST_DIRECTORY: u32 = 1;
    const FILE_ADD_FILE: u32 = 2;
    const FILE_ADD_SUBDIRECTORY: u32 = 4;
    const FILE_FLAG_BACKUP_SEMANTICS: u32 = 0x02000000;
    let check = |rights| {
        allowed(
            fs::OpenOptions::new()
                .access_mode(rights)
                .custom_flags(FILE_FLAG_BACKUP_SEMANTICS)
                .open(path)
                .map(drop),
        )
    };
    json!({"list":check(FILE_LIST_DIRECTORY),"create_file":check(FILE_ADD_FILE),
           "create_directory":check(FILE_ADD_SUBDIRECTORY)})
}

#[cfg(any(target_os = "linux", target_os = "macos"))]
fn permissions(path: &Path) -> Value {
    use std::{ffi::CString, os::unix::ffi::OsStrExt};
    let Ok(path) = CString::new(path.as_os_str().as_bytes()) else {
        return Value::Null;
    };
    let check = |mode| {
        // The absolute, NUL-terminated path outlives this synchronous OS query.
        if unsafe { libc::faccessat(libc::AT_FDCWD, path.as_ptr(), mode, libc::AT_EACCESS) } == 0 {
            Some(true)
        } else {
            allowed(Err(io::Error::last_os_error()))
        }
    };
    let create = check(libc::W_OK | libc::X_OK);
    json!({"list":check(libc::R_OK),"create_file":create,"create_directory":create})
}

#[cfg(not(any(windows, target_os = "linux", target_os = "macos")))]
fn permissions(_: &Path) -> Value {
    Value::Null
}

fn inspect(workspace: &Workspace, relative: &Path) -> Value {
    let path = match workspace.resolve(relative) {
        Ok(path) => path,
        Err(e) => return json!({"state":"unavailable","error":e}),
    };
    for parent in path
        .ancestors()
        .take_while(|p| p.starts_with(workspace.root()))
    {
        match fs::metadata(parent) {
            Ok(metadata) if metadata.is_dir() => {
                return json!({
                    "state":if parent == path {"directory"} else {"missing"},
                    "checked_directory":parent, "permissions":permissions(parent)
                });
            }
            Ok(_) => return json!({"state":"not_directory","path":parent}),
            Err(e) if e.kind() == io::ErrorKind::NotFound => continue,
            Err(e) => return json!({"state":"unavailable","reason":e.kind().to_string()}),
        }
    }
    json!({"state":"unavailable","reason":"No accessible ancestor"})
}

pub(super) fn report(workspace: Option<&Workspace>) -> Result<Value, Error> {
    let caps = inkbolt::request::execute(
        json!({"command":"capabilities"}),
        workspace,
        &Control::default(),
    )?;
    let defaults = inkbolt::workspace::default_paths();
    let selected = workspace.map(|w| {
        let mut roots = Map::new();
        for (role, relative) in defaults
            .as_object()
            .expect("workspace defaults are an object")
        {
            let path = Path::new(relative.as_str().expect("workspace defaults are paths"));
            roots.insert(role.clone(), inspect(w, path));
        }
        json!({"root":w.root(),"roots":roots})
    });
    Ok(
        json!({"name":caps["name"],"version":caps["version"],"platform":caps["platform"],
              "workspace_defaults":defaults,"workspace":selected}),
    )
}
