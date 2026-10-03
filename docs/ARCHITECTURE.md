# Architecture

Inkbolt is an original engine for agent-directed graphics work. Its public document model is independent of any external application or native file format.

## Implemented foundation

The Rust library owns typed requests, document invariants and capability reporting. The CLI is a bounded JSON transport over files or stdin. Empty document snapshots carry explicit IDs, dimensions, document kind, schema version and color space. No external application is required to execute these commands.

## Planned components

1. Document graph: artboards, groups, path objects, text, raster layers and external asset identities. Separate vector geometry from pixel storage, with explicit transforms and bounds.
2. Editing: typed operations over immutable snapshots. Validate candidate state before any publication. Stable IDs and semantic diffs support agent review.
3. Vector evaluation: original geometry and bounded public-format import/export, starting with a documented shape subset. Unsupported features produce diagnostics.
4. Raster evaluation: tiles, explicit straight/premultiplied alpha, color assumptions and bounded memory. Define compositing equations and independent numerical fixtures before broadening effects.
5. Session store: expected-revision checks, request IDs, atomic batches, history and undo. Receipts distinguish already-applied requests from conflicts.
6. Execution: preview and export jobs consume immutable revisions and explicit external input/output roots. Preserve originals and publish outputs atomically.
7. Agent adapters: thin CLI and MCP stdio frontends over one contract. No network listener.

Public specifications, original mathematics and generated fixtures drive implementation. Private investigation may produce bounded factual requirements after review. It is not a source-code implementation pipeline. Binary-analysis and desktop-test tools remain external development dependencies.

No rendering backend, session database, file-format library or font stack has been selected yet. Record exact versions, licensing and tradeoffs before adding any.
