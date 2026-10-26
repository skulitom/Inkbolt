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
        [arg] if arg == "--help" || arg == "-h" => {
            return Ok(json!({
                "usage":[
                    "inkbolt [--workspace ABSOLUTE_DIRECTORY] < request.json",
                    "inkbolt [--workspace ABSOLUTE_DIRECTORY] request.json",
                    "inkbolt [--workspace ABSOLUTE_DIRECTORY] capabilities|schema|implementation.status",
                    "inkbolt [--workspace ABSOLUTE_DIRECTORY] mcp [--tools essentials|core|full]",
                    "inkbolt [--workspace ABSOLUTE_DIRECTORY] --help|-h"
                ],
                "requests":"One JSON request on stdin or in one UTF-8 request file. No arguments reads stdin.",
                "workspace":"Optional existing absolute directory; selects default stores and resolves request paths within it.",
                "responses":{"success":"One JSON line with ok:true and result; exit code 0.",
                    "failure":"One JSON line with ok:false and error containing code and message; exit code 1.",
                    "mcp":"MCP stdio protocol instead of CLI envelopes; use --tools essentials for the smallest catalog, core for more direct tools."},
                "discovery":"Use schema.lookup for command arguments or one operation. Full schema and capabilities are larger responses.",
                "examples":[
                    {"command":"schema.lookup","name":"index"},
                    {"command":"schema.lookup","name":"document.create"},
                    {"command":"schema.lookup","name":"operation","select":"reorder"},
                    {"command":"document.create","id":"example","kind":"vector","width":32,"height":32}
                ]
            }));
        }
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
                "Use --help for CLI usage, JSON examples and focused schema discovery",
            ));
        }
    };
    inkbolt::request::execute(request, workspace, &Control::default())
}

fn start() -> Result<Option<Value>, Error> {
    inkbolt::jobs::configure_cli_executable(
        std::env::current_exe().map_err(|_| {
            Error::new("IO_ERROR", "Unable to locate the current engine executable")
        })?,
    );
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    match args.as_slice() {
        [flag, root, generation] if flag == "--job-worker" => {
            let generation = generation
                .to_str()
                .and_then(|s| s.parse().ok())
                .ok_or_else(|| Error::new("INVALID_REQUEST", "Invalid worker generation"))?;
            inkbolt::job_process::await_start(std::io::stdin().lock())?;
            inkbolt::jobs::run_worker(Path::new(root), generation)?;
            return Ok(None);
        }
        [flag, root, id, attempt] if flag == "--job-run" => {
            let id = id
                .to_str()
                .ok_or_else(|| Error::new("INVALID_REQUEST", "Invalid job ID"))?;
            let attempt = attempt
                .to_str()
                .and_then(|s| s.parse().ok())
                .ok_or_else(|| Error::new("INVALID_REQUEST", "Invalid attempt number"))?;
            inkbolt::job_process::await_start(std::io::stdin().lock())?;
            inkbolt::jobs::run_attempt(Path::new(root), id, attempt)?;
            return Ok(None);
        }
        _ => {}
    }
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
        [arg, flag, mode] if arg == "mcp" && flag == "--tools" && mode == "essentials" => {
            Some(inkbolt::mcp::CatalogMode::Essentials)
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
