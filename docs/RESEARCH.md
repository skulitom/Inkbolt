# Research and publication boundaries

Application-specific investigation is private local development work. Keep its exact target names, installation paths, versions, hashes, evidence, scripts, audit plans and results outside this repository. The current root can be found with `git config --local --get inkbolt.researchRoot`.

Commit original project code, contracts, documentation and synthetic fixture generators. Do not commit application binaries, installers, plugins, native projects, copied documentation or SDK source, presets, fonts, screenshots, dumps, disassembly, decompiler output or analysis databases. Preserve provenance and required license attribution externally and in distributed dependencies where required.

Use the following order for each bounded investigation:

1. Define an interoperability question and measurable stop condition.
2. Check public specifications and supported interfaces.
3. Use original synthetic inputs to observe behavior on an exact build. Record settings, source hashes, outputs, failures and confidence privately.
4. Use binary inspection only for a remaining necessary question with an established access basis. Limit modules, analysis and time; keep input installations unchanged.
5. Review minimal factual requirements before admitting them to the original implementation. Never port, translate or paraphrase decompiled code, private tables, shaders or control flow.

Separate directories do not establish a formal clean-room process. An implementer exposed to proprietary implementation is not independent of that exposure. No such process is claimed here.

Ghidra projects, caches and logs belong in the private root. Run metadata/loader probes on an original executable before using the workflow on any external target. Keep general extraction and decompilation disabled by default. Anode provides background desktop verification; it shares the user's account and filesystem, so it is not a security sandbox. Keep the viewer hidden and retain captures privately.

`tools/check_repo.py` scans commit candidates; `--staged` reads indexed bytes, including forced additions. A missing Git-private policy fails closed. `tools/setup_private.py` installs the checkout-local hook and policy. These do not transfer to clones and can be bypassed deliberately. Review the full history before distribution. Hiding a folder does not encrypt or restrict its contents.
