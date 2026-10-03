# Inkbolt

A local vector and raster editing engine for agents. Sister to Cutbolt: Cutbolt handles time; Inkbolt will handle paths, pixels and layered documents.

**Status: initial foundation, 3 October 2026.** The Rust library and JSON CLI can create and validate empty vector or raster document snapshots, describe supported capabilities, and export the request schema. Editing, rendering, file interoperability, saved sessions and MCP stdio are planned, not implemented.

Inkbolt runs locally without a hosted API, network listener, account or telemetry. Requests and responses are structured JSON, with strict fields and explicit errors. Document creation is in memory; the caller owns persistence.

## Run

Requires Rust/Cargo and Python 3.11+ for development checks. Dependencies are pinned in Cargo.lock and fetched to the normal external package cache.

```powershell
cargo build --locked
.\target\debug\inkbolt.exe capabilities
.\target\debug\inkbolt.exe examples/create-vector.json
.\target\debug\inkbolt.exe examples/create-raster.json
.\target\debug\inkbolt.exe schema
python tools/verify.py
```

Send one request on stdin, or pass one request file. Success is `{"ok":true,"result":...}` with exit code 0. Failure is `{"ok":false,"error":{"code":"...","message":"..."}}` with exit code 1. No commands currently write documents or media. See [the agent interface](docs/AGENT_INTERFACE.md).

## Direction

- Vector: paths, fills, strokes, groups, transforms, typography and artboards.
- Raster: tiled pixels, layers, masks, selections, compositing and adjustments.
- Shared: stable object IDs, explicit color semantics, transactional sessions, previews, undo and repeatable exports.
- Agent workflow: inspect, plan, apply, review, recover; expose the same contracts through CLI, library and eventually MCP stdio.

See [architecture](docs/ARCHITECTURE.md), [roadmap](docs/ROADMAP.md), [dependencies](docs/DEPENDENCIES.md), and [research boundaries](docs/RESEARCH.md).

## Private research and publication

The original source, contracts and synthetic fixtures belong here. Application-specific research, target identities and audit evidence belong in an external private directory. Audit tools are development tools, not runtime dependencies.

This checkout has a Git-private content policy and local pre-commit check. They are not transferred by cloning. To prepare another checkout, supply its private policy file and an external research directory:

```powershell
python tools/setup_private.py --research-root C:\DEV\Inkbolt-Research-Private --policy C:\DEV\Inkbolt-Research-Private\content-policy.json
python tools/check_repo.py
python tools/check_repo.py --staged
```

The check fails when policy is missing and inspects actual staged bytes, including forced additions. Ignore rules and hooks reduce accidental publication; they do not prove provenance or replace full history review. A hidden folder is a visibility convenience, not access control.

Original Inkbolt code is [MIT licensed](LICENSE). The repository material checker is adapted from Cutbolt under the same license; its notice is retained.
