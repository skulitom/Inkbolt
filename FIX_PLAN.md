# Inkbolt fix plan: from verified engine to the agent tool people pick

Prepared 11 October 2026 for an implementing agent. The initial review used
commit `16e1cf1` plus the then-uncommitted rendering work; see "Current
implementation baseline" for its landed status. File and line references were
collected on that date. Re-locate them by symbol name before editing; do not trust
line numbers blindly.

**Adopted 11 October 2026.** The owner adopted this plan for the active
agent-readiness goal and explicitly approved all recommended defaults D1-D7.
**This is the primary development plan and takes priority over every earlier
plan**, as the owner reaffirmed on 11 October 2026. Its scope, decisions,
priorities and workstream order govern implementation. Older roadmaps and
readiness plans are supporting context; resolve planning conflicts in favor of
this plan. The original A1-A7 gates,
matched sister-project comparisons, B01-B20 outcomes and unchanged 167-checkpoint
criteria remain required; this plan extends their execution, not their credit.
See [the readiness plan](docs/AGENT_READINESS.md). W9 remains deferred and outside
the active implementation scope. Routine checks retain the 180-second budget.
Verified changes are committed and pushed directly to `main` under the owner's
standing authorization.

## Current status and next actions

| Workstream | Current status | Next action |
| --- | --- | --- |
| W0 | Complete and closed | Change limits only with a capability or safety change that needs them; no further consolidation campaign |
| W1 | Full hosted Windows/Linux/macOS matrix passed at `a1a0339`, including the evaluation path-alias correction. Later session-store judge and Windows job-fixture changes have focused checks | Retain current-revision hosted acceptance when available; Unix jobs remain open |
| W2 | All twenty tasks have external lifecycles/capture import and matched reporting. [Five-pair evidence covers B01-B03](docs/BENCHMARK_RESULTS.md), with separate smaller-model pilots. B03 matches baseline artifact success at 5.37x median token use; B01 baseline source-admission failures had correct delivered pixels. B05's session-store assumption is corrected with Windows/WSL checks. B17-B19 have no baseline | Run B04/B05, then complete five-repetition evidence for the other fifteen tasks. Audit further judge store assumptions before trials and review B01's font-delivery contract before reliability claims. Retain failures; B19/B20 require Windows and B10 Linux memory evidence remains required |
| W5.1 | Complete: single-copy PNG delivery, structured responses and measured traffic reductions; fresh Windows/Linux acceptance passed | Keep the transport contract; use W2 evidence to prioritize W5.2+ |
| W3a.1-2 | Arcs and rounded rectangles complete with fresh Windows/Linux acceptance | Other W3a items remain open; prioritize them using W2 evidence |
| W3b | Atomic SVG insertion complete within its declared contract; fresh Windows/Linux full acceptance passed at `e9c493e` | Measure B01/B02 usability through W2 |
| W3c / W4 / W5.2+ / W6 | Open; substantial work. W5.2 first-page entry points and CLI-help/sibling-index guidance have focused Windows/Linux checks; remeasurement preserved success and lowered observed token use, but baseline remains cheaper | Broaden W2 coverage before further B02-specific tuning or substantial interface/scale work; insertion-index and schema discovery friction remain recorded. Full milestone acceptance remains open |
| W7 / W8 | Distribution and published usability evidence remain open; README checkpoint headline moved | Ship only verified platform tiers; publish comparable results after trials |
| W9 | Deferred, outside active scope | No learned-model plugin work |

Keep this table current in place. Detailed milestone evidence belongs in
[development status](docs/DEVELOPMENT_STATUS.md) and the relevant contract;
per-commit history belongs in Git, not appended status paragraphs in this plan.

The initial review identified six gaps. The table above records subsequent
progress; the following list describes that original baseline:

1. **No recorded model evidence and no baseline.** Model-driven trials are informal;
   nothing compares an agent using Inkbolt against an agent that is not using it.
2. **The agent interface is heavy.** It is large and duplicates payloads.
3. **Scale limits sit below everyday professional work.**
4. **Everyday real-world inputs are refused.** This covers SVG arcs, circles in
   booleans, JPEG native import and layered files over 1 MP.
5. **It does not ship.** It is Windows-only, has no CI and no releases, and the
   install is build-from-source.
6. **The open interchange checkpoints get little practical traction.** Recent work
   adds refusal diagnostics rather than admitting more of each format.

---

## 0. Ground rules (read first)

- Read `AGENTS.md`, `README.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`,
  `docs/AGENT_READINESS.md`, `docs/DEVELOPMENT_LOOP.md` and `docs/RESEARCH.md`
  before changing behavior. This is the primary plan and takes priority over
  earlier plans in those documents. Preserve applicable project safeguards and
  the acceptance requirements explicitly retained below.
- **Research boundary.** Use project-owned capability names ("native vector",
  "native layered", "page exchange"). Never put third-party product names,
  private research, copied implementation or third-party assets in the repo.
  Native-format work must start from public specifications and from minimal
  factual requirements the owner has reviewed. Do not open the private research
  root yourself.
- **Acceptance criteria are fixed.** Never weaken an acceptance criterion in
  `docs/features.json` and never award a checkpoint without independent evidence.
  Partial work gets no credit. After registry edits, run `python tools/update_report.py`.
- **Unsupported semantics still fail explicitly.** Any new approximation must be
  declared in the response (method, bound, losses), never silent.
- **Capabilities and docs change together with behavior.** Every changed limit or
  feature updates `capabilities` (mostly `src/lib.rs` ~1000-1700) and the
  relevant `docs/*.md`.
- **Verification loop.** While implementing, use `python tools/verify.py` (quick,
  180 s budget), `--only`, `--rust` and `--last-failed`. Before any milestone or
  feature claim, run `python tools/verify.py --thorough`. Before every commit,
  run `python tools/check_repo.py` and `--staged`. Never disable the guard or the hook.
  Quick scheduling uses saved durations to start long checks early and leave
  known overruns pending before launch, preserving time for checks that fit.
  Failed/pending results never become passes; focused feedback and fresh thorough
  milestone acceptance retain their separate scopes.
- **Dependencies.** Lock exact versions in `Cargo.toml`/`Cargo.lock` and record
  each one in `docs/DEPENDENCIES.md` and `THIRD_PARTY_NOTICES.md`.
- **Fixtures are original and synthetic.** Never commit downloaded icon sets,
  photos, fonts or documents.
- **Publication authority.** Commits and pushes to `main` are already authorized.
  D2 authorizes preparing the separate public CI guard while preserving the local
  private guard and commit hook. Present concrete changes for any remaining
  approval required before tags, GitHub releases, registry listings, package
  publication, newly enabled CI, or other publication-rule changes. Do not handle
  API keys or credentials. Model trials read them from the environment, which the
  owner sets up.

## 1. Accepted owner decisions

On 11 October 2026 the owner answered **"Adopt the recommended defaults"** for
all seven decisions below. The recommended-default column is therefore the
accepted choice. Implementation and independent evidence are still required;
selecting a target or platform tier does not establish support.

| ID | Decision | Recommended default | Blocks |
| --- | --- | --- | --- |
| D1 | Default precision for `document.boolean`: keep exact-only, or add `precision:"auto"` (exact first, then a declared tolerance fallback) as the default | `auto` is the default; existing exact tests pin `precision:"exact"` | W3c |
| D2 | Public/CI mode for `tools/check_repo.py`, which currently fails closed without the private policy | Add `--public` structural mode for CI only; the local hook and private policy stay mandatory | W1.6, W7 |
| D3 | SVG import policy for unsupported elements: whole-import failure only, or opt-in `unsupported:"omit_and_report"` with located losses | Add the opt-in; keep failure as the default | W3a |
| D4 | Optional local learned-model plugin for semantic selection (user-installed, network-denied, pinned weights hash) | Defer; not in this plan's default scope | W9 |
| D5 | Platform promise for Linux/macOS: build + core engine + CLI/MCP only, or also durable jobs/receipts parity | Tier 1 = build/core/CLI/MCP/receipts; jobs follow in tier 2 | W1 |
| D6 | Distribution channels: GitHub release binaries, `cargo install --git`, crates.io, npm/pip launch shims, MCP registry listing | GitHub releases + `cargo install --git` first | W7 |
| D7 | Scale targets for W4 (pixels, depth, memory ceiling) | 8192x8192 (67,108,864 px) RGBA8/RGBA16; at most 512 MiB peak commit for a 50 MP 16-bit edit/export workflow | W4 |

---

## 2. Priorities and order

| Order | Work | Delivery unit / dependency |
| --- | --- | --- |
| Closed | W0 | Complete; no additional cleanup gate for later work |
| 1 | W1 CI and platform verification | Activation approved; hosted evidence remains; do not hold independent harness work behind it |
| 2 | W2 harness | Several milestones across 20 adapters; no model credentials needed for fixtures, prompts, judges, fake drivers or baseline plumbing |
| 3 | W5.1 payloads, W3a.1-2 arcs/rounded rectangles, W3b SVG insertion | Separate bounded behavior changes with focused tests; can proceed while real trials await the owner's environment |
| 4 | W2 real model and baseline trials | Owner-provided execution environment or transcript/workspace imports; matched settings and retained failures |
| 5 | W3a remaining coverage, W3c, W4, W5.2+ and W6 | Reorder using the decision rule under W2 before committing to a substantial stream |
| 6 | W7 distribution | W1 evidence and approved D6 channels; publication approval still applies |
| Now / later | W8 positioning | Move the checkpoint headline now; gallery, install promises and comparative claims follow verified delivery and trials |
| Deferred | W9 | Outside active scope under D4 |

The original S/M/L estimates were too optimistic and are not schedule promises.
W4 and each W6 format stream need multiweek planning allowances, split into
reviewable storage/migration, admission, fidelity and acceptance milestones.
W2 is also a multi-milestone refactor, not merely waiting for the owner to run a
model. Re-estimate each increment after its design and oracle are concrete;
small interface/SVG increments are not guaranteed one-day changes.

Commit in small logical units with tests, capability reporting and documentation.
Keep routine feedback within 180 seconds. Reserve fresh full acceptance for
behavior/platform milestones; planning, wording and workflow scheduling changes
use focused verification plus the existing unchanged-engine evidence.

---

## W0. Limits single source of truth (complete)

Closed. The [original requirements and verified evidence](docs/DEVELOPMENT_STATUS.md)
remain available for traceability. Further limit work must accompany an actual
capability or safety requirement, not reopen a consolidation campaign.

---

## W1. Cross-platform build and CI (P0, M) [D2, D5]

See the status table, [platform support](docs/PLATFORMS.md) and
[milestone evidence](docs/DEVELOPMENT_STATUS.md) for verified coverage.
Linux tier 1 does not establish macOS, Unix jobs or full W1 completion.
The owner approved the reviewed three-platform CI workflow, its narrow path
allowance and Cargo cache on 11 October 2026. Task 6's activation approval is
satisfied; the full hosted matrix passed at `5dfb699` as recorded in the status table.

**Tasks**

1. **Unix file identity.** Implement `file_identity` for Unix with `st_dev` +
   `st_ino` from `std::os::unix::fs::MetadataExt`. Match the Windows semantics
   (stable identity of the published file across hard links and renames).
   Document any difference in `docs/PUBLICATION_RECEIPTS.md`.
2. **Compile-clean stubs (tier 1).** Gate or restructure the dead items so that
   `cargo clippy --all-targets -- -D warnings` passes on Linux and macOS. Keep
   `UNSUPPORTED_PLATFORM` for jobs, with `capabilities.jobs.supported_here`
   truthful.
3. **Unix job backend (tier 2, D5).** This needs:
   - a process group/session per job and `setrlimit(RLIMIT_AS)` on Linux (or a
     documented weaker limit on macOS);
   - a creation-time identity (Linux `/proc/<pid>/stat` start time, macOS
     `proc_pidinfo`);
   - a peak memory measure (`wait4`/`getrusage`);
   - a `FileLease` without `share_mode`;
   - a worker launch without `CommandExt`.

   Any new crate (for example `libc`) must be locked and documented. Rerun the
   [recovery contracts](docs/RECOVERY_CONTRACTS.md) audit on each platform you
   claim.
4. **Python portability.**
   - Guard the module-level `msvcrt`/`WinDLL` imports.
   - Add one helper that skips tests based on the engine's `capabilities`
     (`supported_here`), not `os.name`, so skips track engine truth.
   - Apply it to `test_jobs.py`, `test_publication_receipts.py`,
     `test_history_receipts.py`, `test_session_backups.py`, and the
     job/receipt cases in `test_session_lineage`, `test_recovery_workflow`,
     `test_mcp` and `test_agent_workspace`.
   - Make the measurement tools report `ineligible` instead of crashing.
5. **Toolchain.** Add `rust-version` (verify the true minimum; file locking needs
   1.89) and a `rust-toolchain.toml` pinned to the verified toolchain.
6. **CI (needs D2 and owner approval before it runs on push).**
   - Add `.github/workflows/ci.yml` with a Windows/Linux/macOS matrix:
     `cargo fmt --check`, `cargo build --locked`,
     `cargo clippy --all-targets --locked -- -D warnings`, `cargo test --locked`,
     and the Python suite through `verify.py`.
   - For the guard, add a `check_repo.py --public` mode. It runs the public
     structural checks (suffix allowlist, size, UTF-8/NUL, private directory
     names, gitignored files) and reports `private_policy:"not_evaluated"`.
   - That mode must never satisfy the local hook. Extend `tests/test_repo_guard.py`
     to prove the hook and default mode still fail closed.
7. **Cross-platform docs.** Add bash and PowerShell commands to the README, and
   per-OS MCP config examples
   (`examples/mcp-config.windows.json`, `.unix.json`) that use `--tools core`.

**Acceptance.** `--thorough` still passes on Windows. The CI matrix passes on all
three OSes, with unsupported features skipped explicitly according to
`capabilities`. `docs/AGENT_READINESS.md` names exactly which platform tier is
claimed, with evidence.

---

## W2. Model-driven trials and a no-engine baseline (P0, multiple milestones)

**Problem.** The product claims to be "for agents". The owner has tried it
informally with an external model client, but there are no retained trials
in the benchmark format, and nothing compares it against an agent working without
Inkbolt. The scripted adapters prove contracts, not usability.

Current code:

- `tools/benchmark_tasks.py` defines `TASKS` and `CHECKS` (B01-B20).
- `tools/benchmark_adapters.py` maps each task to one function that **mixes
  solving with judging** (`case.check(...)` inside the adapter).
- Shared oracles sit at `tools/benchmark_graphics.py` ~19-67 and hard-code solver
  conventions (`session_id='work'`, request ids, item ids, revisions).
- Prompts exist as one string per adapter (`case.begin(prompt)`), but they are
  not model-ready. They omit deliverable names. B17's says "the adapter will drop
  that successful response".
- `tools/agent_benchmark.py` ~118/127 hard-codes `actual_model_benchmark_complete=False`
  and null token fields. `--transport` accepts only `cli` and `mcp`.

**Execution boundary.** Harness preparation has no owner/credential dependency.
Implement prompts, fixtures, independent judges, reference solvers, check classes,
fake-driver tests and model/baseline transcript ingestion before requesting real
trial execution. External transcript imports must retain the exact prompt,
settings, input/workspace identities and observed usage; missing data stays
unknown. Fake or scripted runs never count as model evidence.

**Tasks**

1. **Split every adapter into four parts.**

   | Part | Responsibility |
   | --- | --- |
   | `fixture(case)` | Writes original inputs |
   | `prompt` | Versioned file `tools/benchmark_prompts/Bxx.md` |
   | `solve(case)` | The current scripted calls, which become the reference solver |
   | `judge(case)` | Reads only delivered artifacts and the workspace after solving |

   Tag judge-side engine calls `phase="judge"` (the field exists) and exclude them
   from task traffic. Judges must not rely on solver-chosen ids. Prompts name every
   required deliverable path and constraint instead.
2. **Make prompts model-ready.** Each prompt states the goal, the inputs, the exact
   deliverable paths and formats, and the constraints. It must not mention
   adapter internals. Keep task IDs and required outcomes unchanged; any criterion
   change needs a recorded reason (`docs/AGENT_READINESS.md` rule).
3. **Classify every check in `CHECKS`.**
   - `artifact`: applies to any arm (pixels, dimensions, alpha, physical boxes,
     no overwrite, source preservation).
   - `engine`: Inkbolt-specific (history, receipts, editable source, live
     dependencies).

   Other arms report `engine` checks as `not_applicable` explicitly, never by
   omission. Update `finish()` (~:297-299 in `benchmark_runtime.py`) accordingly.
4. **Model arm (`--arm model`).** Use a pluggable driver interface so the harness
   does not depend on one client:
   - **External client driver.** It runs a configured client command with the
     prompt file, an MCP config pointing at the exact release binary under test,
     a fixed working directory and a time limit. It collects the transcript and the
     client-reported usage from a declared JSON output.
   - **Transcript import.** It ingests a transcript plus workspace produced in an
     external model client and runs the same
     judges.

   Record the model id, settings, client version, prompt hashes and machine. Use
   at least five repetitions, and retain every failure. Fill `token_usage`,
   `model_calls` and `agent_seconds` only from observed data; unknown stays null.
   Credentials come from the environment only; never log them.
5. **Baseline arm (`--arm baseline`).**
   - **Setup:** the same prompts and the same model, with no Inkbolt. Tools are file
     writing and a shell with a pinned SVG rasterizer and a pinned Python imaging
     library, declared in `inputs.json`. These are benchmark-only tools, kept
     outside the repo and never engine dependencies.
   - **Scoring:** judged by the same `artifact` checks.
   - **Tasks that cannot apply:** tasks with no meaning without the engine (B17-B19)
     report `not_applicable` with the reason.
6. **Report.**
   - **Contents:** success rate per task per arm, calls, tokens, invalid calls,
     retries, first useful preview, wall time, peak memory and every failure.
   - **Completion flag:** set `actual_model_benchmark_complete=true` only for a full
     20-task, ≥5-repetition model-arm run.
   - **Losing tasks:** produce a "losing tasks" list (where baseline ≥ model arm on
     success, or the model arm needs far more tokens or calls).
7. **Tests.** Update `tests/test_agent_benchmark.py` (~:51-52 asserts null tokens
   and `model_trials=False`) to cover the new arms with a fake driver. Test that a
   model row without observed usage keeps nulls.

**How results change the work.** Compare matched artifact checks separately from
engine-only checks, using the same task inputs, model/settings and at least five
repetitions per arm. Report counts and uncertainty; equal results in five trials
are a prioritization signal, not proof of equivalence. Unknown usage cannot
establish an efficiency advantage. Define task categories before running trials,
retain every failure, and do not tune the judge after seeing which arm wins.

| Observed bottleneck | Planning consequence |
| --- | --- |
| Valid SVG input or awkward authoring prevents an artifact | Promote the smallest relevant W3a/W3b increment and rerun affected tasks |
| Comparable artifacts require more calls, retries or tokens with Inkbolt | Prioritize W5.1 and only the W5.2+ surfaces implicated by traces; drop redundant optional wrappers |
| A required workload exceeds measured memory, storage or latency bounds | Promote that W4 slice with its migration contract and independent workload oracle |
| A required input/delivery format is the cause of failure | Promote that W6 admission slice after the required specification/research review |
| Curved geometry is the blocker | Promote the relevant W3c case with declared approximation and fidelity checks |
| Revision, retry or history guarantees are the useful distinction | Report those engine checks separately and improve the demonstrated workflow; do not inflate the shared artifact score |

If the baseline matches or beats Inkbolt on most comparable task IDs without a
demonstrated efficiency or engine-workflow advantage, prioritize input admission,
SVG authoring and fewer required interactions. Hold optional broad storage,
interface and interchange expansion until a recorded failing task or required
scale case justifies the next increment. Cut speculative extra features and
redundant approaches, not the owner's accepted W0-W8 scope, A1-A7 gates, B01-B20
outcomes or unchanged 167 checkpoint criteria. Any actual scope reduction needs
an explicit owner decision.

Before beginning a substantial W3c/W4/W5.2+/W6 increment, record the motivating
tasks, expected improvement and remeasurement/stop condition in development
status. Update the priority table in place. A failing implementation hypothesis
can be abandoned without hiding failures or marking its required outcome done.

**Acceptance.** One complete model-arm run and one baseline-arm run, retained
privately. Aggregates may be published only where the research boundary permits.
The losing-tasks list is checked in as an aggregate summary and drives the
W3c/W4/W5.2+/W6 ordering above. Harness completion and trial acceptance are
reported separately.

---

## W3. Everyday vector input

### W3a. SVG import coverage (P1, M) [D3]

**Problem.** Ordinary SVGs fail whole-import (`src/svg_import.rs`, about 85
refusal sites):

- elliptical arcs `A` (`src/svg_import/numbers.rs:247`)
- rounded `rect` `rx`/`ry` (`svg_import.rs` ~465)
- nested `<svg>` (~634)
- `use`/`symbol`, `<image>`, CSS classes/selectors in `<style>`
- `tspan`/`textPath`, markers, multi-child clips

Most real icon and illustration SVGs use arcs, rounded rects, classes or `use`.

**Tasks** (in order of real-world frequency):

1. **Elliptical arcs.** Convert using the endpoint-to-center parameterization in
   the SVG specification's implementation notes. Split into ≤90° segments and
   approximate each by a cubic with a declared maximum radial error. Report the
   bound in the import receipt. Handle degenerate cases per spec: zero radii
   become a line, radii are scaled up when too small, and identical endpoints
   produce no segment.
2. **Rounded `rect`.** Map `rx`/`ry` (including auto and clamping rules) to the
   existing rounded-rectangle primitive, or to its path expansion when `rx != ry`
   is unsupported by the primitive.
3. **`<style>` with type, class, id and simple compound selectors.** Apply them
   with correct specificity and cascade against presentation attributes and
   `style=""`. Keep refusing unsupported selector syntax explicitly (located).
   Keep `!important` refused or implement it fully.
4. **`use`/`symbol`.** Map them to the existing component/instance system
   (`docs/COMPONENTS.md`) where the semantics match. Otherwise expand as groups
   with the correct `x`/`y`/viewBox transform. Refuse recursion and external
   references.
5. **Nested `<svg>`.** Apply the viewport transform with `preserveAspectRatio`,
   plus a clip.
6. **`<image>`.** Support `data:` URIs and local files under an explicit asset root,
   as placed images. Refuse remote URLs explicitly.
7. **`tspan`** with absolute and relative positioning and per-run style, as text
   ranges where the engine's text model can represent it.
8. **D3 policy.** Add `unsupported:"omit_and_report"`. It skips unsupported
   elements and records each with its source location and the reason. Never
   apply it silently; the default remains failure.

**Tests.** Use original synthetic SVG fixtures for every feature. Use independent
oracles: analytic geometry for arcs (sample points on the true ellipse versus the
imported cubics within the declared bound), the cascade order, and exact pixel
expectations for simple shapes. Extend `tests/test_svg_import_cli.py`,
`test_svg_definitions_cli.py` and `test_svg_text_cli.py`.

**Docs.** Update `docs/SVG_IMPORT.md` and the capabilities SVG section.

### W3b. Author in SVG, edit in Inkbolt (P1, S-M)

Models write SVG fluently. Add an atomic edit `Operation` (for example
`{"op":"add_svg","parent":..., "svg":"<g>...</g>", "unsupported":...}`) that
parses a fragment through the existing importer and inserts editable items. It
needs:

- stable generated IDs returned in the change details;
- normal lock, revision, undo and retry rules;
- size limits taken from the request ceiling.

Because it is an `Operation`, it works through CLI, MCP and sessions alike. Add a
schema example and tests. This is likely the single biggest usability win for
diagram and icon tasks (B01/B02). Confirm with W2 results.

### W3c. Robust curved booleans (P1, M-L) [D1] (advances `vector.booleans.extended`)

**Problem.** Booleans reject common shapes and return only straight segments.

- `document.boolean` (`src/lib.rs` ~847 → `src/booleans.rs` ~482) always returns
  **polygons** (Move/Line/Close only, ~584-589).
- It **refuses ellipses** (`booleans.rs` ~140-145) and compound regions (~146).
- It refuses tangencies needing non-rational junctions:
  `CURVE_TOPOLOGY_UNRESOLVED` at `booleans/topology/quadratic/contacts.rs` ~93
  and subdivision depth 20 (`topology.rs` ~343).
- It hits `RESOURCE_LIMIT` at 512 edges, 4096 atoms or 2,000,000 work units
  (`booleans.rs:15-18`).
- `PRECISION_LOSS` can fire on output rounding (~384-476).
- The docs say "There is no automatic approximation fallback" (`docs/BOOLEANS.md:29`).
- The certified arcs are collapsed to chords at `topology.rs` ~472-493, discarding
  curve data.

**Tasks**

1. **Ellipses.** Expand through `primitives::expand` and disclose the
   quarter-cubic error in `losses`/`inputs[]`, instead of refusing.
2. **`precision` field.** Add `"exact" | "auto" | "tolerance"`, with the default
   per D1.
   - `exact` is today's behavior.
   - `auto` tries exact under a reduced work budget. On
     `CURVE_TOPOLOGY_UNRESOLVED`, a curve-stage `RESOURCE_LIMIT`, `PRECISION_LOSS`
     or `TOPOLOGY_ERROR` it falls back to tolerance.
   - `tolerance` takes these steps:
     1. adaptively flatten cubics in f64 to ≤ `curve_tolerance/2`;
     2. snap vertices to a dyadic grid ≤ `curve_tolerance/8`;
     3. feed the snapped rational edges to the existing exact polygon arrangement
        (`booleans.rs` ~522-581);
     4. finish with snap-rounding (or round, then re-run as a nonzero self-union)
        so f64 output cannot break topology.
   - The response reports `certificate:"exact"|"tolerance_snap"`, the achieved
     deviation bound and the losses. Existing failure tests pin
     `precision:"exact"`.
3. **Performance.** Replace the O(n²) pair loops (~523, ~553-559, `left_sample`)
   with bounding-box culling or a sweep. Re-derive the edge, atom and work limits
   from measurement (curved inputs hit 512 edges quickly), and record them in W0's
   `limits.rs`.
4. **Curve output (`output:"curves"`, default once verified).**
   - Tag each certified arc with its source cubic and parameter interval instead
     of a bare chord. Carry the tag through raw, atoms and trace; atoms are keyed
     by `Segment` today, which drops it.
   - Emit the exact sub-cubics between crossings. A transverse crossing is at most
     one per arc (`topology.rs` ~462); solve it on the true curves inside the
     certified parameter box and split both cubics there.
   - In tolerance mode, emit sub-cubics of the source curves between the snapped
     crossing parameters.
   - Validate curve output by re-flattening and comparing coverage against the
     polygon arrangement within the declared tolerance.
   - Keep `output:"polygon"` available.
5. **Atomic `boolean` edit `Operation`.** It computes, adds the result with
   explicit paint, and optionally hides or removes sources, under the normal
   revision/lock/undo/retry rules. Agents should not need a read-then-add two-step
   for an everyday path combination.
6. **Coverage holes.** Compound regions (`work_path_combine` results) as operands:
   evaluate them to paths through the same tolerance path, or keep refusing
   explicitly and say so in the docs.

**Independent evidence for the checkpoint** (registry text: "Handle curves,
coincident edges, self-intersections and disjoint regions with deterministic
tolerance and topology"):

- an independent area oracle (Green's theorem on cubic segments);
- dense point-membership sampling against the operands' own winding, outside a
  tolerance band;
- coincident-edge, self-intersecting, tangent (including irrational tangency) and
  disjoint fixtures;
- determinism across runs and, once W1 lands, across OSes;
- curve-output deviation checks.

Update `docs/BOOLEANS.md` (including removing the "no fallback" statement once it
is true) and `features.json` only when the full criterion is independently
verified.

---

## W4. Practical raster scale (P1, multiple substantial milestones) [W0, D7] (A5)

**Problem.** Real photos and print pages exceed current ceilings, and several
operations are confined to tiny inline grids.

- **Inline pixels.** Inline mutable pixels are capped at 65,536 (256x256;
  `model.rs` `MAX_STORED_PIXELS`).
- **Whole evaluation.** Limited to 1,048,576 px (`render.rs:16`).
- **Tiled evaluation and native blocks.** Each is capped at 16,777,216 px. The
  real native ceiling is bytes: `MAX_NATIVE_DECODED_BYTES = 64 MiB`
  (`src/sample_import.rs:28`). That means RGBA16 reaches only ~8.4 MP and f32
  ~4.2 MP: a 12 MP 16-bit photo fails, and an A3 page at 300 ppi
  (3508x4961 = 17.4 MP) exceeds the tiled limit.
- **Encoded input.** Capped at 32 MiB (`assets.rs:20`) and read whole
  (`sample_import.rs` ~488).
- **Pending blocks.** Kept in memory until publish (`sample_store.rs` ~190
  `pending: BTreeMap`).
- **JPEG.** No native import at all; `sample.import` accepts only PNG and TIFF
  (`sample_import.rs` ~510). JPEG goes through full RGBA8 assets.
- **Lifetime patch cap.** Stored layers allow `MAX_PATCHES=256` and
  `MAX_PATCH_PIXELS=65_536` **in total over their lifetime**
  (`src/stored_samples.rs:19-20`, enforced ~87-119). After 256x256 pixels of
  total edits, a native layer can no longer be edited.
- **Operations confined to small or inline content.**
  - `assist.segment` accepts at most 65,536 px and rejects stored samples
    (`assistance/segment.rs` ~138-145).
  - `repair` accepts only inline RGBA8 `Content::Raster` (`repair.rs` ~101-115).
  - Mask application is limited to 65,536 output pixels (`masks.rs` ~270-325).
  - Per-edit retouch and brush regions are limited to 65,536 (`retouch.rs:296`,
    `pixel_brush.rs:563`).
- **Export and outputs.** Image export builds the complete RGBA8 image in memory
  (`render.rs` ~1353-1373, `image_io.rs` ~493). `MAX_OUTPUT_BYTES` is 32 MiB
  (`publish.rs:14`).
- **Tiled subset.** Artwork masks, `Raw`, `Object` and `Border::Wrap` are
  rejected (`render/tiled.rs` ~113-129).
- **Layered import.** It ignores profiles: a 1,048,576-px canvas and 65,536
  stored pixels (`layered.rs:34-36`; `layered/read.rs` ~566/621/771).
- **Session history.** It is 64 MiB (`sessions.rs`), and `MAX_STATE_BYTES` is
  derived from the vector limit only.

**Tasks** (W0 first; coordinate with the in-flight tiled work):

1. **Copy-on-write native edits.**
   - Replace the overlay patch model with block-granular copy-on-write. An edit
     writes new content-addressed 128x128 blocks plus a new manifest, and history
     stores manifests.
   - Remove the lifetime caps. Bound only per-edit work and the store size.
   - Keep `docs/NATIVE_SAMPLE_STORAGE.md` guarantees: immutable blocks,
     create-only publication, exact history.
   - Write a migration contract first if stored formats change
     (`docs/SESSION_LINEAGE.md` rule: migrations precede storage changes).
2. **Streaming import.**
   - Open the encoded file as `Read + Seek` instead of reading it whole.
   - Replace the whole-frame decoded-byte check with a per-band budget.
   - Spill completed blocks to the store as temporary create-only files and
     publish atomically via the manifest. Keep the existing identity and
     publication boundaries.
   - Handle TIFF chunk bands that span the full frame by decoding strips or tiles
     incrementally where the codec allows. Otherwise budget explicitly.
3. **Native JPEG import (baseline and progressive).**
   - Evaluate whether the locked decoder can deliver rows or bands. If it cannot,
     budget a whole-frame 8-bit decode explicitly (~201 MB at 67 MP RGB) and
     convert band by band.
   - Add an explicit EXIF orientation policy (`apply`/`ignore`, no implicit
     default), as already planned in `docs/METADATA.md`.
   - Treat any decoder change as a new locked dependency.
4. **Raise ceilings together (D7).**
   - Raise all of these to the target: native pixels, tiled pixels, coverage cache,
     asset pixels, sequences, `MAX_TILES` (4096 for 8192² at edge 128), the
     encoded input size and `MAX_OUTPUT_BYTES`.
   - Keep independent work and memory budgets; raising storage limits never raises
     processing budgets implicitly.
5. **Streaming export.**
   - Write PNG rows from tiled bands with a streaming PNG writer, keeping TIFF
     strips as today.
   - Encode JPEG band-wise, or budget whole-image explicitly if the locked encoder
     requires it.
   - Publish create-only from a temporary file instead of an in-memory buffer.
6. **Native operations.**
   - `repair` (fill/move/edge_correct) on stored-sample windows.
   - Mask application and selection-to-mask with native gray block masks.
   - `assist.segment` with an explicit `region` of interest at native resolution,
     plus an optional proxy-then-refine mode (graph cut on a declared downsample,
     then exact refinement in a band around the boundary). Report which mode ran.
   - Raise per-edit region limits for retouch and brush, using bounded windows.
7. **Tiled subset.** After the in-flight nonlocal work lands, admit artwork masks
   and wrap borders in tiled evaluation, or keep them refused with capabilities
   saying so.
8. **Layered import scale.** Wire the `large_raster` profile and the native sample
   store into `layered.import`, so layered files above 1 MP import as native
   blocks (feeds W6b).
9. **Sessions.** Verify that manifest-based states stay small. Re-derive
   `MAX_STATE_BYTES` per profile instead of from the vector limit.
10. **Measurement.** Add a new `scale-v2` suite. Do not alter `scale-v1` or the
    native-* suites. It contains:

    | Case | Content |
    | --- | --- |
    | 24 MP JPEG | Original synthetic photographic generator |
    | 50 MP RGBA16 TIFF edit/history | Patch, brush, repair, mask |
    | A2 page at 300 ppi | 4961x7016 PDF + PNG |
    | 8192x8192 RGBA8 render/export | |

    Give every case an independent per-sample oracle and create gates with
    `tools/workload_gates.py`. Extend `tools/benchmark_photo.py` B10 with a
    separate large variant, keeping the existing 256 MiB fixture budget
    unchanged.

**Acceptance.** The `scale-v2` cases pass with independent oracles within the D7
memory ceiling, measured on Windows and (after W1) one Unix platform.
`capabilities` and `docs/LIMITS.md` report the new limits. The native storage,
render quality, large raster and readiness docs are updated.

---

## W5. Agent interface weight (P0 for 5.1, otherwise P1 after W2)

Measured on the 11 Oct release build:

| Surface | Measured size |
| --- | --- |
| Core MCP catalog | 22 tools, 3 pages, ~72 KB (~18k tokens) before the first call |
| `operation` full schema | 126 KB, 111 variants, 233 definitions |
| `document` full schema | 77 KB |
| `item` full schema | 61 KB |
| Commands | 96 |
| `capabilities` | 256 KB |
| Full catalog | ~3.9 MB |

Largest core tools: `session_publish` 10.4 KB, `document_preview` 5.6 KB,
`session_diff_preview` 4.9 KB. Stateless `document.create`/`document.edit` return
full snapshots, and compact responses cover only six session commands
(`src/responses.rs:8-15`).

1. **Stop duplicating payloads (P0).** In JSON response mode
   (`src/mcp.rs` ~614-657):
   - **Images:** when image blocks are attached, replace the base64 in the envelope
     with a `payload_ref`, as preview mode does (`src/mcp_preview.rs`). Image bytes
     must cross the wire once.
   - **Text block:** the full envelope goes out both as text and as
     `structuredContent`. The MCP spec recommends including serialized JSON in
     text for backward compatibility, so keep that as the default. Add an explicit
     `response_format:"structured"` that sends a short text summary plus
     `structuredContent` for clients that read structured output.
   - **Measure:** record bytes before and after in `tools/measure_responses.py`.
2. **`--tools essentials` catalog.** At most 10 tools and ≤24 KiB, tested in
   `tests/agent_discovery.rs` (where `CORE_CATALOG_BYTES` lives, `mcp.rs:26`).
   - **Contents:** create session (blank/preset/import), inspect page, apply edits,
     preview, check, publish, import asset/font, lookup/help, run.
   - **Defaults:** recommend it in docs and config examples. Do not change the
     default of `inkbolt mcp` (existing-client compatibility rule).
3. **Slim the heaviest core schemas.** Defer rarely used option blocks (print,
   prepress, ink recipe, receipts) behind `schema.lookup` selectors, as is done
   for documents and operations.
4. **Examples-first discovery.**
   - Give every `Operation` variant a minimal valid example, returned first by
     `schema.lookup`.
   - Make the `operation` outline list variants with one-line descriptions.
   - Add a test that executes every example against a fixture document, so
     examples cannot rot.
5. **Compact by default for stateless edits.** Add `response_mode:"compact"` to
   `document.create`/`document.edit` (return a pinned reference + summary + change
   list). Allow pinned references in nested positions (for example
   `transfer.source`, `docs/AGENT_WORKSPACE.md:39`).
6. **High-level operations chosen from W2's losing tasks.** Likely candidates:
   `add_svg` (W3b), the `boolean` edit (W3c), image placement with fit modes, and
   a text box with fit-to-frame. Add them as real `Request`/`Operation` variants
   to keep CLI parity (A2). The touch points are:
   - the `Request` enum (`lib.rs` ~141);
   - the executor (~1739+);
   - the capabilities list (~1033);
   - MCP descriptions (`mcp.rs` ~124), `CORE` (~27) and the mutating list (~458);
   - the replayable/persistent lists (`request.rs` ~198) if durable.
7. **Actionable errors.** From W2 transcripts, take the 20 most frequent model
   errors. Make each one name the offending field, the valid alternatives and the
   `schema.lookup` selector to consult.

**Acceptance.** Byte budgets are enforced by tests. A W2 rerun shows fewer tokens
and calls per successful task with no correctness loss. Update
`docs/AGENT_DISCOVERY.md`, `AGENT_RESPONSES.md` and `AGENT_INTERFACE.md`.

---

## W6. Interchange checkpoints (P2, substantial scope per format)

All native-format work must follow `docs/RESEARCH.md`: public specifications
first, and only owner-reviewed minimal factual requirements. Prefer **admitting**
more of each format over adding diagnostics-only commits. Recent commits
(`16e1cf1`, `4273db4`, `4679ce7`, `ca42482`, `3a0f775`) diagnose layered text
controls without widening what imports. A new diagnostic should land together
with the admission it enables.

### W6a. Page exchange (`vector.pages.extended`)

Current state (`src/pdf.rs` and the `src/pdf/` submodules):

- **Text** is painted as glyph outlines (~558-576). There is no font embedding,
  subsetting or ToUnicode.
- **Streams** are unfiltered (~124).
- **Preflight** refuses non-normal blends, knockout, active masks, effects and
  more (~464-523).
- **BleedBox** always equals MediaBox (~954-974).
- **No PDF import.** The only reader, `src/vector_native/pdf_read.rs`, is a
  bounded container reader that never executes content.

Tasks:

1. **Embedded, searchable text.**
   - Embed TrueType outlines as Type0/CIDFontType2 with `FontFile2`. Embed CFF
     outlines as `FontFile3`.
   - Subset fonts (a locked subsetting dependency or an original subsetter).
   - Add a `ToUnicode` CMap built from shaping clusters, and `ActualText` for
     many-to-many clusters.
   - Respect OS/2 `fsType` embedding permissions: restricted fonts fall back to
     outlines with an explicit loss, or fail if the request demands embedding.
   - Keep outline mode as an option. Verify with the independent test PDF reader
     (`tests/pdf_reader.py`): extracted text matches the source, glyph positions
     match, and the fonts are subset and embedded.
2. **Compression.** Flate-compress content streams (flate2 is already locked).
3. **Transparency.**
   - Soft masks from engine masks.
   - `/BM` for the blend modes PDF defines; flatten or refuse the rest
     explicitly per mode.
   - Knockout groups and gradients with varying alpha.
4. **Page boxes.** Make BleedBox independent of MediaBox when marks or slug
   extend the media.
5. **Bounded reimport and encapsulated pages.** Write an original content-stream
   interpreter for a declared operator subset:
   - path construction and painting, graphics state, `cm`, `q`/`Q`;
   - DeviceGray/RGB/CMYK, Separation and ICCBased color;
   - Form and Image XObjects;
   - text with embedded TrueType/CFF.

   Every other operator is refused or reported as a located loss. First target:
   editable reimport of the engine's own PDF output. Then admit a bounded
   encapsulated-page subset as a placed object. Confirm with the owner that this
   interpretation meets the unchanged acceptance text before claiming it.

### W6b. Native layered (`raster.interchange.extended`)

Current state:

- **Canvas size:** imports are capped at 1 MP (see W4.8).
- **Masks:** only authored gray8. Refused: feather, inverted/derived, vector-mask
  parameters, combined masks (`src/layered/mask.rs` ~45-118).
- **Groups:** only normal isolated and pass-through. Refused: non-normal blends,
  clipping, fill opacity, knockout, unknown tags such as effects and vector masks
  (`src/layered/read.rs` ~79-280).
- **Text:** editable only as a single horizontal unwrapped point line
  (`docs/LAYERED_TEXT_IMPORT.md:46-59`).

Tasks, in this order:

1. Large documents through the native store (W4.8).
2. Group blend modes, clipping, fill opacity and knockout, mapped to existing
   engine semantics (`docs/BLENDING.md`, `KNOCKOUT.md`, `LAYER_CLIPPING.md`).
3. Masks:
   - feather, as a retained mask control rendered by the existing blur;
   - inverted;
   - vector masks, mapped to engine vector masks;
   - combined pixel and vector masks.
4. Paragraph/box text, using the existing story and frame engine and the controls
   already diagnosed (alignment, indents, spacing, hyphenation, frames, columns).
5. Layer effects mapped to `docs/LAYER_EFFECTS.md` where semantics match.

Each step needs original fixtures, independent pixel and structure oracles, and
return-trip checks.

### W6c. Native vector (`vector.interchange.extended`)

Current state:

- **Admitted subset:** flat layers, one closed opaque RGB filled contour per path,
  and artboards.
- **Unknown operators:** any unknown operator (text, gradients, images, clipping,
  effects) fails (`src/vector_native/artwork.rs` ~386).
- **Other versions:** refused outright with no loss report
  (`src/vector_native.rs` ~111/126/130).
- **Re-delivery:** regenerates everything, with no passthrough of unknown data.

Tasks:

1. Version-loss diagnostics instead of outright refusal.
2. Admit strokes (dash, caps, joins), groups and nesting, clipping, gradients and
   placed images.
3. Admit text (point, then area), reusing W6b's text mapping where the formats
   share semantics.
4. Preserve the bytes of untouched unknown objects on re-delivery, or report
   their loss explicitly per object.

---

## W7. Distribution (P1, S-M) [W1, D6]

1. **`[profile.release]`.** Use `lto`, `codegen-units = 1` and `strip = "symbols"`.
   **Keep `panic = "unwind"`**, because `catch_unwind` is relied on at `src/mcp.rs`
   ~680 and `src/jobs/worker.rs` ~522. Measure the binary size (currently ~31 MB)
   and startup time before and after.
2. **Version and doctor commands.** Add `inkbolt --version` and `inkbolt doctor`
   (workspace, store permissions, font roots, platform tier from `capabilities`;
   no network).
3. **Release workflow (owner approval before tags or pushes).**
   - Targets: Windows x64, Linux x64 (consider a static musl build; `rusqlite`
     `bundled` needs a C compiler), macOS arm64 and x64.
   - Contents: archives with `LICENSE` and `THIRD_PARTY_NOTICES.md`, SHA-256
     checksums and an SBOM.
   - Tests: run the CI matrix tests against the built artifacts.
4. **Install paths (D6).**
   - `cargo install --git https://github.com/skulitom/Inkbolt --locked`.
   - Prebuilt archives.
   - Optionally, thin launch shims so MCP clients can start it with one command.
     These need explicit owner approval because they are outward-facing.
5. **MCP config examples per OS** (from W1.7), and a quickstart that goes from
   install to first PNG in three commands.

---

## W8. README and positioning (headline now; evidence after W2/W7)

1. **Lead with what it does.**
   - Start with a 30-second quickstart per OS and a small gallery of original
     example outputs (generated by `examples/*.py`).
   - Check the guard's suffix allowlist before committing images. Otherwise link
     to release assets.
   - Keep the checkpoint score below quickstart and current limitations; this
     wording change does not wait for W2 or W7.
2. **State strengths plainly.** Deterministic revision-safe editing (dry runs,
   undo, receipts, create-only publish), print correctness (spots, separations,
   ICC, page boxes) and typography (bidi, shaping, hyphenation). State the
   platform tier and limits honestly, linking `docs/LIMITS.md`.
3. **Publish results.** Publish W2 aggregate results (model arm versus baseline,
   per task) where the research boundary permits, keeping losing categories
   visible.

---

## W9. Semantic assistance plugin (deferred) [D4]

Not in scope unless the owner approves D4. Sketch for later:

- **Selection method.** `assist.segment` gains `method:"external_model"`. It
  invokes a user-installed local executable through the contained job-process
  machinery, network-denied, with a pinned weights hash and declared inputs and
  outputs.
- **Repository contents.** No weights or model binaries in the repo, and no
  download or fallback (`docs/PIXEL_ASSISTANCE.md` rules).

---

## Definition of done (every task)

- [ ] Behavior is implemented with explicit failures for anything still unsupported.
- [ ] Tests use original fixtures and an **independent** oracle, not the engine's
      own output as the reference.
- [ ] `capabilities`, `docs/LIMITS.md` (after W0) and the relevant contract doc are
      updated in the same change.
- [ ] Quick `verify.py` passed during work. `--thorough` passed before any
      milestone or feature claim.
- [ ] `tools/check_repo.py` and `--staged` pass. No third-party names, assets or
      private research.
- [ ] `features.json` changes only when a full checkpoint criterion is
      independently verified, followed by `tools/update_report.py`.
- [ ] Outward-facing actions (push, tag, release, publish, CI on push) were
      approved by the owner.
