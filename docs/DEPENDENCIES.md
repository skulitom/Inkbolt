# Dependencies and provenance

Original engine code is MIT licensed. The material checker is adapted from original Cutbolt tooling; LICENSE retains its notice. No engine code or audit output from external applications is incorporated.

Cargo.lock records exact versions and checksums. Packages remain in Cargo's external cache; do not vendor them. Direct dependencies:

| Package | Purpose | License |
| --- | --- | --- |
| serde | Typed JSON contracts | MIT OR Apache-2.0 |
| serde_json | JSON transport | MIT OR Apache-2.0 |
| schemars | Request JSON Schema | MIT |

Rust/Cargo, Python 3.11+ and Git are development tools. Python checks use only the standard library. Ghidra, Java and Anode are optional external research tools; exact local installations and verification receipts belong in the private research root. They are not runtime dependencies.

Review the resolved graph and any distribution notices before a release. No native document importer, renderer, pixel library or font dependency has been selected.
