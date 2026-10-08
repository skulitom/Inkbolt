use inkbolt::{Error, MAX_REQUEST_BYTES, Request, execute};
use serde_json::{Value, json};
use std::io::{Read, Write};

fn read_request(reader: impl Read) -> Result<Request, Error> {
    let mut bytes = Vec::new();
    reader
        .take(MAX_REQUEST_BYTES + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| Error::new("IO_ERROR", "Unable to read request"))?;
    if bytes.len() as u64 > MAX_REQUEST_BYTES {
        return Err(Error::new("REQUEST_TOO_LARGE", "Request exceeds 16 MiB"));
    }
    // Do not echo request fragments or local paths into errors.
    serde_json::from_slice(&bytes).map_err(|_| {
        Error::new(
            "INVALID_REQUEST",
            "Expected one request matching the command schema",
        )
    })
}

fn run() -> Result<Value, Error> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    let request = match args.as_slice() {
        [] => read_request(std::io::stdin().lock())?,
        [arg] if arg == "capabilities" => Request::Capabilities {},
        [arg] if arg == "schema" => Request::Schema {},
        [arg] if arg == "implementation.status" => Request::ImplementationStatus {},
        [path] => {
            let file = std::fs::File::open(path)
                .map_err(|_| Error::new("IO_ERROR", "Unable to open request file"))?;
            read_request(file)?
        }
        _ => {
            return Err(Error::new(
                "INVALID_REQUEST",
                "Use stdin, one request file, capabilities, schema, or implementation.status",
            ));
        }
    };
    execute(request)
}

fn main() {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    if args.len() == 1 && args[0] == "mcp" {
        if inkbolt::mcp::run().is_err() {
            std::process::exit(1);
        }
        return;
    }

    let (envelope, code) = match run() {
        Ok(result) => (json!({"ok": true, "result": result}), 0),
        Err(error) => (json!({"ok": false, "error": error}), 1),
    };
    let mut output = std::io::stdout().lock();
    if writeln!(output, "{envelope}").is_err() {
        std::process::exit(1);
    }
    std::process::exit(code);
}
