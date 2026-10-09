use inkbolt::{Error, MAX_REQUEST_BYTES, control::Control, workspace::Workspace};
use serde_json::{Value, json};
use std::{
    ffi::OsString,
    io::{Read, Write},
    path::Path,
};

fn read_request(reader: impl Read) -> Result<Value, Error> {
    let mut bytes = Vec::new();
    reader
        .take(MAX_REQUEST_BYTES + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| Error::new("IO_ERROR", "Unable to read request"))?;
    inkbolt::request::decode(&bytes)
}

fn run(args: &[OsString], workspace: Option<&Workspace>) -> Result<Value, Error> {
    let request = match args {
        [] => read_request(std::io::stdin().lock())?,
        [arg] if arg == "capabilities" || arg == "schema" || arg == "implementation.status" => {
            json!({"command":arg.to_str().unwrap()})
        }
        [path] => {
            let path = match workspace {
                Some(w) => w.resolve(Path::new(path))?,
                None => path.into(),
            };
            let file = std::fs::File::open(path)
                .map_err(|_| Error::new("IO_ERROR", "Unable to open request file"))?;
            read_request(file)?
        }
        _ => {
            return Err(Error::new(
                "INVALID_REQUEST",
                "Use optional --workspace DIR followed by stdin, one request file, capabilities, schema, implementation.status, or mcp --tools core|full",
            ));
        }
    };
    inkbolt::request::execute(request, workspace, &Control::default())
}

fn start() -> Result<Option<Value>, Error> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    let (workspace, args) = match args.as_slice() {
        [flag, root, rest @ ..] if flag == "--workspace" => {
            (Some(Workspace::open(Path::new(root))?), rest)
        }
        [flag] if flag == "--workspace" => {
            return Err(Error::new(
                "INVALID_REQUEST",
                "--workspace requires an existing absolute directory",
            ));
        }
        rest => (None, rest),
    };
    let mode = match args {
        [arg] if arg == "mcp" => Some(inkbolt::mcp::CatalogMode::Full),
        [arg, flag, mode] if arg == "mcp" && flag == "--tools" && mode == "full" => {
            Some(inkbolt::mcp::CatalogMode::Full)
        }
        [arg, flag, mode] if arg == "mcp" && flag == "--tools" && mode == "core" => {
            Some(inkbolt::mcp::CatalogMode::Core)
        }
        _ => None,
    };
    if let Some(mode) = mode {
        // Do not emit a CLI envelope after a protocol I/O failure.
        if inkbolt::mcp::run_in_workspace(mode, workspace).is_err() {
            std::process::exit(1);
        }
        return Ok(None);
    }
    run(args, workspace.as_ref()).map(Some)
}

fn main() {
    let (envelope, code) = match start() {
        Ok(None) => return,
        Ok(Some(result)) => (json!({"ok": true, "result": result}), 0),
        Err(error) => (json!({"ok": false, "error": error}), 1),
    };
    let mut output = std::io::stdout().lock();
    if writeln!(output, "{envelope}").is_err() {
        std::process::exit(1);
    }
    std::process::exit(code);
}
