# Reproducible agent task benchmark

`tools/agent_benchmark.py` records scripted reference workflows for the fixed
B01-B20 tasks in [the readiness plan](AGENT_READINESS.md). Nineteen
adapters exercise real CLI and compact MCP commands with independent output,
structure, resource, history and source-preservation checks. The remaining
task stays explicit in every full report. This advances A1; it does not establish
autonomous agent success, a matched Cutbolt comparison or complete readiness.

## Running and preserving evidence

Use a new external directory under an existing parent. The tool builds the locked
release executable, records its identity and measures that exact binary. Run
transports sequentially, with no concurrent verification, edits or workload runs.
Describe actual machine/load conditions; the driver does not isolate the machine.

```powershell
python tools/agent_benchmark.py --output-root C:\Work\Evidence\inkbolt-mcp-01 --conditions "Windows; no other test run active" --transport mcp
python tools/agent_benchmark.py --output-root C:\Work\Evidence\inkbolt-cli-01 --conditions "Windows; no other test run active" --transport cli
```

Five repetitions are the default; `--repetitions` accepts 1-10. Each trial gets a
fresh workspace and, for MCP, a new persistent stdio server with the core catalog.
CLI starts one process per command. Task order rotates between repetitions; OS
caches may be warm. `--task B17 --task B18` selects a narrower investigation.
Unknown IDs and duplicate selections reject. Existing destinations, paths inside
the repository and optimized Python (`-O`) reject.

`inputs.json` retains the starting candidate-file map, release executable and
build evidence, toolchain, host identity, conditions and selections before trials
start. Every trial retains its original fixtures, task instructions, raw requests
and responses, stderr, delivered files and `result.json`. The final `report.json`
records unchanged-input checks, every trial and aggregate distributions. Missing
final reports indicate incomplete runs. Failed trials retain diagnostics and
their measurements; failed and open trials never become passes through averaging.
Keep reports and artifacts private; publish only permitted aggregates and the
original fixture generators.

Exit 0 means all **selected** tasks passed with unchanged inputs. Exit 2 means a
selected task failed or is not implemented, or inputs changed. Argument errors
also return 2 with a diagnostic. Unexpected driver/build errors are failures,
even when some earlier trial files exist. A selected subset cannot set
`complete_scripted_suite`; only a successful complete twenty-task run can.
The current default full run therefore returns 2 because one adapter remains
unimplemented. `actual_model_benchmark_complete` and
`matched_cutbolt_comparison` remain false for scripted runs.

## Current adapters and independent checks

| Tasks | Implemented evidence |
| --- | --- |
| B01 diagram; B02 icon sheet | Stable editable objects, original geometric font identity, exact label/connector/icon pixels and three independent artboard exports |
| B03 large layout | One requested change among 5,000 rectangles, every current and historical pixel, retained controls and checked history |
| B04 SVG revision | Original grouped editable path, explicit import losses, revised SVG structure, independent placement pixels and unchanged original bytes |
| B05 shared palette | Both live swatch dependencies, unrelated paint, current/original pixels and history |
| B06 linked text | Exact overset location, reviewed multi-column repair, ordered source intervals, font/license identity, complete glyph pixels and original overflowing revision |
| B07 multilingual typography | Authored glyph forms, visual order, logical clusters, mark anchors and exact pixels for Latin/Hebrew/numerals, Arabic joining, Han, Indic reordering and a Latin ligature |
| B08 foreground mask; B09 retouch | Complete independent selection coverage, retained source pixels, exact local repair, unaffected pixels and historical output |
| B10 native photograph | Original 1920x1080 synthetic studio image encoded directly at 16 bits, reviewed exact clone patch crossing four native blocks, every edited/historical TIFF sample, editable undo/redo, immutable tiles and a fixed 256 MiB engine commit budget |
| B11 mixed masks/effects | Pinned raster under an isolated masked vector group, exact rational shadow/fill/group composition, offset-only edit, source identity and historical pixels |
| B12 layout variants | Shared component with inherited text/image/position rows, three independently decoded output sizes, original resources, restored base and preserved earlier deliveries |
| B13 screen delivery | All 1920x1080 pixels, straight alpha without matte, explicit sRGB/metadata policy, editable source and overwrite rejection |
| B14 physical print | Independently parsed A4 trim/media/bleed boxes, exact RGB blending and CMYK source profiles, native process/spot operands, focused display preview, preflight identity and declared PDF losses |
| B15 resource repair | Located missing/corrupt resource diagnostics, content-checked replacements, reviewed binding-only repair and unchanged historical bindings |
| B16 seeded layout repair | Actionable text overflow, reviewed frame-width repair, exact font/text/unrelated artwork, preview pixels, preflight/publication identity and history |
| B17 lost response; B18 conflicting writers | Original receipts, exact retry hashes, undo preservation, stale-proposal rejection and reviewed replacement preserving both edits |
| B19 output recovery | Active cancellation, actual supervisor termination during rendering, contained runner exit, explicit restart of the pinned revision, complete independent image pixels, stable physical output/receipt and overwrite rejection |

B20 linked Cutbolt revisions still needs its adapter and complete independent
judge. Separate existing contract tests or handoff
evidence do not silently fill those benchmark slots. The ordinary synchronous
transport still rejects background-job commands; B19 uses a separate contained
recovery adapter with complete process accounting.

B10's original analytic studio fixture includes smooth illumination, object
edges, soft shadows, texture and grain. Linear-light values are encoded directly
into RGBA16 sRGB samples; the source is not an 8-bit image expanded to 16 bits.
The native TIFF judge compares every channel to the original generator bytes and
an independently copied donor rectangle. Snapshot comparisons require exactly
the reviewed native patch, unchanged base manifest and complete undo/redo state.
All original tile files and source bytes must retain their identities. This
bounded synthetic photographic study does not establish camera/RAW support,
production-photo representativeness or full A5 acceptance.

The B10 budget is fixed at **256 MiB peak committed memory** before measurement.
It covers every engine call, including import, review, preview and full-size
delivery; MCP uses its complete persistent-server lifetime. It excludes the
Python fixture/judge and is not total system memory. Missing or zero observations
and even a one-byte overrun fail. `memory-budget.json` records the unchanged
ceiling, measurement scope and every observed process peak. The fixture generator
may reuse its immutable bytes between repetitions; every engine workspace,
import, session and delivery remains fresh, and generation precedes task timing.

B19 uses the ordinary executable without test pause hooks or database writes by
the harness. It observes the owned queue's checksummed rows, cancels an active
export and terminates the exact recorded supervisor during rendering/encoding.
The judge proves its runner exits, inspection leaves the final path absent,
explicit resume produces every expected pixel of the original revision, and
repeated submission/result/resume retains one complete receipt and the same
physical file. Every observed final-file identity/hash must match that delivery.
This bounded rendering interruption complements the storage-boundary tests in
[recovery acceptance](RECOVERY_CONTRACTS.md); it does not inject a crash at every
write instruction or claim that file polling observes every instant.

Each B19 trial owns a Windows kill-on-close process tree before commands receive
their first input. Recorded workers require matching PID, creation time,
executable and container membership. Hidden Windows console hosts are recorded
separately. Retained handles supply lifetime memory; the complete container count
must match the measured command, supervisor, runner and console-host processes.
Incomplete live process lists receive at most four bounded queries, with each
retry recorded; the independent final lifetime count remains mandatory.
Command handles and creation identities remain retained until the trial closes,
so an exited caller is not mistaken for an unmeasured background process.
Missing identities or leaked workers fail the trial. Cleanup stops only that
owned tree. `recovery-evidence.json` retains ledger observations, interventions,
process identities, final-file observations and accounting. CLI launch teardown
may overlap an independent CLI cancellation caller; MCP stays serial on its
persistent connection. Both transports retain every request and response.

The fixture shapes, labels, fonts, image samples and failure conditions are
original and deliberately bounded. Exact integer geometry supplies an independent
pixel oracle; source snapshots, decoded PNG samples, resource hashes and history
checks establish the declared outcomes. These fixtures do not represent the full
range or subjective quality of production artwork. Task IDs and required outcomes
are checked against the accepted plan so incomplete tasks cannot disappear.

The multilingual font uses original, glyph-distinct geometric outlines; the judge
uses authored logical intervals, advances and rectangles rather than the engine's
render as its reference. The print fixture uses original analytic ICC profiles,
preserving declared process/spot values in PDF. Its display preview and calibrated
RGB blending do not claim a press proof or a real printer's measured condition.
Complete print/interchange scope remains governed by the original feature registry.

## Measurement meaning

- Engine commands and process calls are distinct. MCP protocol counts and bytes
  include initialization, the initialized notification and paged core discovery.
  Raw request/response lengths include actual framing and image payloads.
- Retries identify a previous byte-equivalent logical request through its canonical
  hash. Expected failures, invalid calls and replayed receipts are separate counts.
  B17 retains a deliberately dropped response for the judge and explicitly marks
  it unobserved by the scripted recovery path.
- Round-trip time includes process or stdio transport and JSON costs. Scripted
  wall time includes discovery and independent judge work after fixture setup.
  First verified preview is the recorded completion time of the earliest image
  response or delivery later accepted by its independent pixel oracle. It is a
  retrospective availability measure, not a model's assessment of usefulness.
  B19's overlapping CLI callers mean summed round trips need not equal wall time.
- Windows memory uses OS lifetime high-water marks: the maximum individual CLI
  process peak or the persistent MCP server peak. B19 additionally includes every
  supervisor, runner and owned console host, with separate identities and peaks.
  These are maximum individual-process peaks, not a concurrent memory sum. The
  Python driver is excluded. Unavailable memory stays null; these records
  do not imply another platform is supported.
- Per-task distributions include every measured attempt, with count, minimum,
  median, maximum and population standard deviation. Success/failure/open counts
  remain alongside them. Unknown token use, model calls and autonomous-agent time
  stay null. No simulated token estimate is reported as observed usage.

Actual model trials still require fixed instructions, inputs, model/settings and
machine; at least five repetitions; retained transcripts; every failure; and the
same independent judges. Matched Cutbolt comparisons and complete A1 acceptance
remain separate requirements. The existing [scale workload gates](WORKLOAD_MEASUREMENT.md)
retain their own baselines and budgets; task timings here do not replace them.

## Development checks

Use `python tools/verify.py --only test_agent_benchmark` while changing adapters.
It exercises every implemented task through both transports, checks exact retained
wire volumes and exercises failure/open-task accounting. Run full
`python tools/verify.py --thorough` at a milestone. Repeated release benchmark
trials are milestone evidence, separate from the 180-second routine feedback loop.
