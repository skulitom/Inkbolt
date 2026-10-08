# Inkbolt project instructions

- Build an original local vector and raster editing engine for agents, sister to Cutbolt.
- Read README.md, docs/ARCHITECTURE.md and docs/ROADMAP.md before extending behavior. Consult docs/features.json for the full implementation scope and verified status; do not infer completion from scaffolding or partial behavior.
- Use the Rust library and structured JSON CLI. MCP stdio is planned. Do not introduce a network listener, hosted API, account requirement or telemetry.
- Read docs/RESEARCH.md before application inspection. Keep product names, exact target mappings, inventories, audit scripts, binary-analysis projects, captures and reports in the external private research root recorded in local Git configuration.
- Public material uses project-owned vector/raster capability names. Run tools/check_repo.py and its --staged mode before committing. Do not disable the local content policy or commit hook.
- Never commit third-party binaries, native projects, SDK source, copied implementation, disassembly, decompiler output, or original application assets. Do not translate or paraphrase private implementation into this engine.
- Derive implementation from original design, public specifications and reviewed minimal factual requirements. Separate folders do not establish a formal clean-room process.
- Keep dependencies external, lock versions, and preserve licenses. Use original synthetic fixtures. Never overwrite source documents or media.
- Fail explicitly for unsupported semantics. Update capability reporting and documentation together; audit completion is not engine completion.
- Validate changes with cargo fmt --check, cargo clippy --locked -- -D warnings, cargo test --locked, and python tools/verify.py. Test the repository guard when changing publication rules.
- Anode is for isolated background desktop verification. Keep the viewer hidden, retain evidence privately, close only owned windows/jobs, and release the lease.
