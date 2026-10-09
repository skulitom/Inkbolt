# Agent readiness plan

Accepted 9 October 2026. This work improves practical agent use without changing the original 167 engine checkpoints or awarding them credit for interface work. [features.json](features.json) governs engine completion. Completion of this plan requires current evidence for every gate below; implemented pieces, documentation and narrow fixtures alone do not establish the entire gate.

## Delivery gates

| Gate | Required behavior and evidence | Current state |
| --- | --- | --- |
| A1 Accurate baseline | Reconcile documentation/capabilities; reproducible approximately 20-task benchmark; exact-build scripted correctness and separate actual model-driven trials; report success, calls, bytes/tokens, retries, first preview, runtime and memory | In progress: reproducible discovery/receipt-volume measurements and task definitions; broad reconciliation and task trials remain |
| A2 Efficient interface | Compact catalog <=96 KiB; focused schemas; workspace defaults and explicit roots; pinned saved references; create-only document files; ordinary receipt target <=8 KiB; pagination/field selection; images without duplicate textual payloads; CLI parity | Implemented with contract checks: discovery, workspaces, pinned references/files, compact receipts, content-bound selected pages and explicit preview transport; final cross-workflow gate audit remains |
| A3 Editing and review | Revision-safe session dry runs; selected-region/artboard previews with coordinate mapping; contact sheets and visual/structural differences; actionable checks/errors; export preflight; seeded-problem repair without unintended changes | Implemented with contract checks: checked dry runs, structural/numerical/visual differences, mapped previews/contact sheets, bounded located checks and exact export preflight; scripted seeded repairs preserve text, unrelated artwork, source files and historical revisions. Complete gate audit remains |
| A4 Recovery | Durable bounded jobs, pinned inputs, progress/wait/cancel; durable publication receipts; checked backups, explicit migrations, recovery and history continuation; interruption/concurrency/retry evidence | In progress: checked backups/restoration, explicit version-1 to version-2 migration, and new-identity continuation with parent provenance and durable retries; crash/cancel/concurrency, full-history limits and explicit resource-rebinding checks. Optional durable document/session publication and history-creation receipts now cover exact-file recovery, interruption, retries, limits, preservation of later restored-session edits and cancellation. Durable Windows export jobs now connect pinned inputs, bounded workers, paged rediscovery, progress/wait/cancel and publication reconciliation; full A4 audit and wider writer coverage remain open |
| A5 Practical scale | Multi-megapixel raster editing, common screen/print outputs and thousands of mixed objects; retained precision and editability; chunked/shared storage, bounded incremental evaluation and identity-bound caches; measured latency/memory and independent fidelity | Existing bounded reference engine and partial sparse-vector evaluation; production workloads open |
| A6 Original engine scope | Independently verify all six remaining original checkpoints without weakening acceptance | Remains 161/167; see implementation registry |
| A7 Complete workflows | Tested agent instructions, recipes and typed presets; versioned content-bound still/sequence handoff with explicit linked revisions; release builds, local diagnostics and gates for every claimed platform | Existing examples and bounded still handoff; complete gate open |

Order: baseline and compact discovery; workspace/references/compact results; dry runs/previews/diagnostics; durable jobs and recovery; practical raster scale and caching; packaged workflows and final acceptance. Original engine completion proceeds alongside those stages where the dependencies allow. A migration contract precedes storage changes that need it. Cache correctness depends on fixed revisions and content identities. A job receipt must distinguish committed output from interrupted work before retry automation is enabled.

A4 process foundation: the Windows [contained worker library](JOB_PROCESSES.md) now has real-process checks for startup gating, supervisor death, owned cancellation, deadlines without polling, committed-memory caps, executable identity and OS lease recovery. The [durable queue](JOBS.md) connects submission, progress, cancellation, explicit resumption and serialized publication. Complete cross-workflow A4 audit and wider writer coverage remain open. Backup, restoration and migration now accept optional durable retry receipts shared with `publication.receipt`/`publication.recover`. Their original no-receipt calls retain create-only `OUTPUT_EXISTS` behavior. The remaining A4 audit must cover the complete writer inventory and user workflows, not infer completion from these fixtures. See [backup boundaries](SESSION_BACKUPS.md) and [migration](SESSION_LINEAGE.md).

Do not infer a Linux or macOS support promise from the sister project's roadmap. The initial measured environment is Windows; each additional claimed platform requires equivalent evidence. No network listener, hosted dependency, account or telemetry is introduced. Preserve the research boundary, immutable sources, create-only outputs, explicit color and unsupported-semantics policies, dependency notices and existing history guarantees.

## Benchmark tasks

Use original synthetic fixtures and explicit correctness oracles. Retain raw generated artifacts and model transcripts externally; publish only permitted aggregate results and original generators. Tasks below define the intended suite; they are not claims of implemented benchmark drivers or successful model runs.

| ID | Task | Required outcome |
| --- | --- | --- |
| B01 | Create a labelled diagram | Correct objects, labels and geometry; editable sources |
| B02 | Produce an aligned icon sheet | Stable IDs, expected spacing and independent artboards |
| B03 | Revise one object in a large layout | Intended object changes; unrelated state/output retained |
| B04 | Import and revise vector artwork | Required structure retained; declared losses; source bytes intact |
| B05 | Recolor a shared palette | All intended dependents change; unrelated paints unchanged |
| B06 | Correct linked-frame text overflow | Reading order, content and font identity preserved |
| B07 | Produce multilingual typography | Correct glyph/cluster order and bounded visual reference error |
| B08 | Select and mask a foreground region | Expected coverage with retained source pixels |
| B09 | Retouch a local image defect | Independent numerical/region checks and unaffected pixels |
| B10 | Edit a multi-megapixel photograph | Native precision/editability within memory budget |
| B11 | Revise a mixed masked/effect document | Composition and resource identity preserved |
| B12 | Generate a family of layout variants | Correct bindings and independently verified output sizes |
| B13 | Deliver transparent screen artwork | Correct alpha, color, dimensions and no unintended matte |
| B14 | Deliver a print page | Correct physical boxes, profiles, inks and declared losses |
| B15 | Recover missing or changed resources | Actionable diagnosis; explicit content-checked repair |
| B16 | Repair a seeded layout/export problem | Inspect, propose, preview and apply without collateral changes |
| B17 | Recover a lost editing response | Original receipt; no duplicate operation |
| B18 | Resolve conflicting writers | Stale proposal rejects; reviewed replacement preserves intent |
| B19 | Cancel/interruption/restart during output | No partial final file, overwrite or duplicate publication |
| B20 | Revise a linked graphic used by Cutbolt | Pinned manifest, explicit revision, correct alpha/color/timing |

For model trials, fix inputs, instructions, model/settings and machine; repeat at least five times and report every failure and variance. Mechanical correctness and source preservation are mandatory. Record model tool calls, actual available token usage, transferred bytes, invalid calls, retries, first useful preview, agent versus engine time and peak process memory. Do not estimate unknown token/memory measures as if observed. A scripted adapter run is a contract check, not an autonomous model trial. Benchmark task removal or altered criteria needs a recorded reason; failing/open tasks remain visible.

The initial byte budgets are explicit engineering targets, not measurements of agent preference. Set latency/memory gates from baseline workloads before claiming scale acceptance. Claims of a higher standard require matched-task evidence; ties and losing categories remain visible.

## Verification and completion

Keep targeted checks available during implementation, with the required `cargo fmt --check`, `cargo clippy --locked -- -D warnings`, `cargo test --locked` and `python tools/verify.py` before accepting a milestone. Run `tools/check_repo.py` and `--staged` before commits. Neither faster development tests nor interface benchmarks award engine points. Verification records identify their exact source state and remain stale if those inputs change.

The final audit covers every gate, all original checkpoint criteria, benchmark failures, documented limits, migration/recovery paths, actual delivered artifacts and every claimed platform. Unverified or missing evidence remains open. Broad readiness is not implied by a high engine-checkpoint percentage.
