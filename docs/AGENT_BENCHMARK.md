# Reproducible agent task benchmark

`tools/agent_benchmark.py` records scripted reference workflows and separated
external-client trials for the fixed
B01-B20 tasks in [the readiness plan](AGENT_READINESS.md). Twenty
adapters exercise real CLI and compact MCP commands with independent output,
structure, resource, history and source-preservation checks. B20 also exercises
an explicitly selected local Cutbolt installation. This advances A1; it does not establish
autonomous agent success, a matched Cutbolt comparison or complete readiness.
`--arm reference` is the existing default. B01-B16 also support `--arm model` and
`--arm baseline`, with an [external driver/capture contract](BENCHMARK_DRIVER.md).
B17-B19 support the model arm; their engine-specific baselines remain explicitly not
applicable. The other external migrations and full matched-trial acceptance remain open.

## Running and preserving evidence

Use a new external directory under an existing parent. The tool builds the locked
release executable, records its identity and measures that exact binary. Run
transports sequentially, with no concurrent verification, edits or workload runs.
Describe actual machine/load conditions; the driver does not isolate the machine.

```powershell
$consumer = @('--cutbolt', 'C:\Tools\cutbolt.exe', '--ffmpeg', 'C:\Tools\ffmpeg.exe', '--ffprobe', 'C:\Tools\ffprobe.exe')
python tools/agent_benchmark.py --output-root C:\Work\Evidence\inkbolt-mcp-01 --conditions "Windows; no other test run active" --transport mcp @consumer
python tools/agent_benchmark.py --output-root C:\Work\Evidence\inkbolt-cli-01 --conditions "Windows; no other test run active" --transport cli @consumer
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
Use your actual local executable paths. A full run without the three consumer
tools fails B20 explicitly; it cannot receive complete-suite acceptance.
`actual_model_benchmark_complete` and
`matched_cutbolt_comparison` remain false for scripted runs.

## Current adapters and independent checks

B01 is the first W2 migration: `benchmark_diagram.py` separates fixture creation,
the versioned [prompt](../tools/benchmark_prompts/B01.md), reference solving and
judging. The judge reads `editable.json` and `preview.png`, accepts solver-chosen
document/object/font-binding IDs, validates the snapshot and independently checks
both delivered pixels and a fresh rendering against authored geometry. Prompt and
source hashes must remain unchanged. Tests alter names, geometry, visibility,
fonts, images and inputs. Its named font adds an optional public OpenType name
table so the same original outlines work in the pinned SVG baseline renderer;
older unnamed fixtures retain their exact bytes. Prompt version 2 describes both
editable deliverables and the baseline source-judge subset. Both arms compare the
delivered PNG and a fresh source render against the same authored pixel oracle.
`benchmark_icons.py` separates B02 into the same four parts with a versioned
[icon-sheet prompt](../tools/benchmark_prompts/B02.md). Judges read the editable
delivery and three independent board PNGs, then freshly render each source board.
Its original stable IDs, order, spacing, ownership and pixel checks remain;
the judge now also enforces the canvas/board dimensions stated in the original
task. These strengthen verification of the unchanged outcome, without adding
or removing check IDs. The baseline uses three editable SVG viewports, admitted
before independent pinned rendering. Tests cover different document/session names,
wrong geometry/ownership/IDs, stale correct solver logs, malformed or missing
images, baseline isolation and captured-trial import.

B03 now has its own fixture, [prompt](../tools/benchmark_prompts/B03.md), reference
solver and independent judge in `benchmark_large_layout.py`. The judge reads
the delivered snapshot, PNGs and a solver-chosen session locator. It checks the
entire normalized document for collateral changes, freshly renders both current
and original saved snapshots, and binds valid history to the original fixture,
final delivery and session's current revision. The baseline reads the identical
JSON fixture and delivers editable SVG and a PNG; its source controls, IDs,
order, transforms and every final pixel are checked without launching Inkbolt.
The original four check IDs remain; saved-revision pixels and history integrity
are explicitly engine-only. Negative fixtures cover unrelated edits, false or
stale session references, wrong/missing images and source changes. Rejudging a
captured trial retains its exact workspace bytes; the historical render uses
the saved resource-free snapshot without its old absolute resource roots.

B04 separates its original SVG fixture, [prompt](../tools/benchmark_prompts/B04.md),
reference solver and file-based judge in `benchmark_svg.py`. The unchanged source
hash, retained layer/path controls, exact world translation and every output pixel
are checked independently. Both arms report the actual delivered ID/description
losses; preserving a description needs no invented loss. Inkbolt's original import
receipt is also checked against a fresh import, including its complete disclosure.
The judge reads and validates the delivered SVG as well as the snapshot and PNG;
an unchanged correct preview cannot conceal altered SVG geometry or paint.
The original check IDs/classes remain. The engine-only snapshot check is explicitly
not applicable to the SVG baseline. Tests cover both transports, independent
document/session names, altered sources/deliveries/reports and captured-trial import.

B05 separates the shared-palette fixture, [prompt](../tools/benchmark_prompts/B05.md),
reference solve and judge in `benchmark_palette.py`. The same JSON fixture feeds
both arms. Inkbolt's delivered snapshot must differ only in the shared swatch
color and revision; both live fill references and all unrelated document state
must survive. The judge freshly renders current and saved original snapshots,
and binds history to the fixture, final delivery and current session revision.
Its chosen session name is read from the delivery, never inferred from solver
logs. The baseline retains three editable SVG rectangles and freshly renders
them with the pinned tool. Both arms compare every pixel of the fresh render
and delivered PNG. The original check IDs/classes remain; live Inkbolt swatch
references and the two history checks are explicitly not applicable in the
baseline. Tests reject flattened links even with correct pixels, unrelated edits,
false or stale histories, wrong images, source changes and unsafe SVG inputs.

B06 separates the linked-flow fixture, [prompt](../tools/benchmark_prompts/B06.md),
reference solve and judge in `benchmark_flow.py`. Both arms receive the same
original JSON layout, font and license; the geometric font gains only an optional
family name for baseline discovery, with unchanged outlines and layout metrics.
The judge independently checks the original overset, repaired logical intervals,
retained source and every output pixel. Inkbolt's snapshot must change only the
second slot and revision, and saved history must bind the source and delivery.
The baseline retains editable JSON layout data and SVG text with explicit source
intervals; neither a claimed flow report nor a correct PNG can conceal changed
source text, frames, fonts or unrelated artwork. The pinned renderer disables
system fonts and uses the original font. All six original check IDs/classes
remain; only the two history checks are not applicable to the baseline. Tests
cover both transports, independent session names, false reports, collateral
changes, unsafe SVG, wrong images and rejudging relocated captured font stores.

B07 separates the multilingual fixture, [prompt](../tools/benchmark_prompts/B07.md),
reference solve and judge in `benchmark_typography.py`. Both arms retain the same
four logical Unicode strings, original font and license. Only original font name
records are added for renderer discovery; existing unnamed fixture bytes and all
outlines, metrics and shaping tables remain unchanged. A common shaping artifact
declares glyph IDs, logical intervals, origins and advances. Inkbolt's judge
checks these against fresh text inspection and independent authored geometry,
reopens the editable snapshot and binds it to valid current history. The SVG
baseline retains logical text, admits bounded editable spans and checks its
declared mapping against authored intervals/metrics and a fresh glyph-distinct
raster. This is a delivered mapping, not an observation of renderer internals.
Both arms check every delivered and freshly rendered pixel. Author-selected
document/object/font/session IDs, labels and descriptive metadata are accepted.
The original four check IDs/classes
remain; the two engine-only checks are not applicable to the baseline.

B08 separates the original raster fixture, [prompt](../tools/benchmark_prompts/B08.md),
reference solve and judge in `benchmark_mask.py`. Both arms retain the same source
JSON and exactly 56 selected foreground pixels. Inkbolt's snapshot must preserve
the entire original layer and unrelated state while retaining a selection and
linked mask; equivalent mask storage extents are accepted. Fresh current/original
renders and exact saved snapshots bind history to the fixture and final head.
The baseline retains original pixels, coverage and selection in three separate
PNG files plus a linked-layer manifest. The pinned Pillow tool independently
decodes these bounded files and recomposes the output; its samples and the delivered
preview must match the common oracle. This prevents a correct preview from hiding
erased source pixels, a wrong mask or missing selection. All five original check
IDs/classes remain; only the two saved-history checks are not applicable in the
baseline. Captured trials rejudge after relocation without modifying their files.

B09 separates the unchanged local-defect fixture, [prompt](../tools/benchmark_prompts/B09.md),
reference solver and independent judge in `benchmark_retouch.py`. The judge checks
all 256 RGBA samples, requiring exactly the four defective pixels to change, and
compares the remaining normalized document properties with the original. It
reopens the delivery, renders fresh current/historical images and binds both
snapshots to the saved history head. Session names and the number of editing
steps are unconstrained. The baseline retains an editable pixel PNG and layer
manifest; pinned Pillow reopens that layer independently of the delivered preview.
Correct preview bytes cannot hide a wrong retained repair or unrelated pixels.
The four original check IDs and their artifact/engine classes are unchanged;
saved-revision and history checks are explicitly not applicable to the baseline.

B10 separates its original native photograph fixture, [shared prompt](../tools/benchmark_prompts/B10.md),
reference solver and delivered-evidence judge. Original native block identities,
exact reviewed patch, saved receipts, undo/redo, current head and every TIFF sample
are checked independently of solver logs. Both external arms retain the fixed
256 MiB budget; their broader owned-tree observation is an explicitly labelled
upper bound, never engine-only memory. See the [driver contract](BENCHMARK_DRIVER.md).
Linux artifact/history checks execute, while its unavailable commit-memory check
fails explicitly.

B11 separates its original mixed-image fixture, [shared prompt](../tools/benchmark_prompts/B11.md),
reference solver and delivered-evidence judge. Both saved compositions, canonical
image bytes, final head and every current/historical pixel are checked independently
of solver logs. The baseline retains editable vector/group/shadow controls and a
separate mask; pinned Pillow decodes both images before a fresh composition with
unquantized intermediate values. The fresh result and delivered preview face the
same unchanged rational oracle. Its two engine-only checks are explicitly not
applicable. See the [driver contract](BENCHMARK_DRIVER.md).

B12 separates its original variant fixture, [shared prompt](../tools/benchmark_prompts/B12.md),
reference solver and delivered-evidence judge. All five saved snapshots, the
restored head, retained resources, typed definitions/inheritance and completed
publication receipts are checked independently of solver logs. Each selected
artboard is freshly rendered against the original exact geometry. The baseline
keeps editable shared SVG instances, dataset values and restored base, with a
named rendering companion for the original unnamed font. The companion retains
every glyph/metric table. Its two engine-only checks are explicitly not applicable.

B13 separates its [creation prompt](../tools/benchmark_prompts/B13.md), reference
solve and delivery judge. It checks full editable controls, the private source note,
exact straight alpha, sRGB/metadata policy and create-only publication. Both arms
render fresh images and independently attempt duplicate publication into protected
copies outside the captured workspace. The baseline uses pinned Pillow and keeps
editable SVG plus its delivery recipe. The four original check IDs/classes remain
fixed; its Inkbolt snapshot check is explicitly not applicable.

B14 separates the original profile fixture, [shared print prompt](../tools/benchmark_prompts/B14.md),
seven-command solver and independent judge. Full editable controls, saved history,
fresh preview/PDF/preflight and completed publication receipts bind the delivered
page and its limitations. The baseline keeps a bounded editable print recipe and
the original RGB/CMYK profiles. Pinned Pillow regenerates the ICC preview; an
independent parser checks native PDF geometry, boxes, profiles and ink operands.
All seven check IDs/classes remain fixed; snapshot/history checks are explicitly
not applicable to the baseline. These display checks do not establish a press proof.

B15 separates its original missing/corrupt resource fixtures, [shared prompt](../tools/benchmark_prompts/B15.md),
eleven-command solver and independent judge. It checks exact replacement cache
bytes, complete unchanged artwork, paired diagnostic locations and both delivered
and fresh preview pixels. Retained proposals, action fingerprints and durable
receipts bind the original and repaired session resources. Relocated captures use
explicit local resource copies for diagnosis/rendering while saved roots remain
unchanged. The baseline retains the original document plus an editable binding
recipe, verifies original decoding with pinned Pillow and renders the repaired
cache. Its two engine-history checks are explicitly not applicable; all six check
IDs/classes remain fixed. Neither arm may fill the original missing cache file.

B16 separates the original font/license fixtures, [shared prompt](../tools/benchmark_prompts/B16.md),
eleven-command solve and independent overflow-repair judge. Full before/after
sources, font bytes, fresh diagnostics/preflight/rendering, retained proposal
fingerprints and durable receipts prove the width-only repair and final delivery.
A named rendering companion changes only font naming/checksums; it preserves the
original glyphs and metrics. Relocated captures use their local font copies.
The baseline keeps editable before/after recipes and SVG text, measures the
original font advances and renders with pinned resvg. Both arms retain the four
original artifact checks; only session history is not applicable to the baseline.

B17 separates the original two-object fixture, [recovery prompt](../tools/benchmark_prompts/B17.md),
solve and independent receipt/history judge. Its reference still has nine calls,
including creation and the withheld move. External runs prepare those two calls
in the harness before starting the client; their traffic and duration appear in
`harness_setup`, separately from client-reported recovery costs. The successful
response stays in evidence outside the solver workspace. Its pre-client identity
is checked again after execution and retained for import. The judge reopens
original/edit/undo states, compares actual durable receipts and fresh preview
pixels, then retries on a private session copy to prove undo preservation without
changing captured files. All five original checks remain; the whole no-engine
baseline stays explicitly not applicable.

B18 separates its unchanged two-object fixture, [conflict prompt](../tools/benchmark_prompts/B18.md),
solve and independent judge. The harness creates revision 0, reviews the target
move, then commits the other writer's move. External clients receive the stale
request at revision 1, reject it, review/apply a replacement and deliver current
and historical artwork. The reference retains ten calls: three setup and seven
solve calls. Setup retains a bounded pre-client database outside the workspace,
with pinned identities checked after execution and on import. The judge reopens
all three saved states and durable receipts, binds the reviewed replacement's
normalized action fingerprint and before/after state hashes, checks fresh pixels,
and reproduces the stale rejection against a private copy of the pre-client state.
That probe must preserve revision 1. Extra commits, lost edits, changed controls,
wrong proposals/errors or altered setup fail. All five checks remain fixed; the
whole no-engine baseline stays not applicable.

B19 now separates its original texture fixture, [recovery prompt](../tools/benchmark_prompts/B19.md),
controlled reference solve and independent judge. External clients use the
owned-process bridge described in the driver contract; captured evidence is
rejudged without repeating faults. B20 still interleaves solving and judging. All required checks
have explicit artifact/engine classes; classification does not migrate a judge.
No real model trial is claimed by synthetic driver tests or reference runs.

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
| B20 linked graphic | Reviewed animated source edit, pinned predecessor, real Cutbolt compilation and explicit timeline replacement, unchanged unrelated state and old revisions, decoded alpha/color/frames/timestamps/PCM, undo and exact retry |

The ordinary synchronous
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
The reference arm covers every solve engine call, including import, review, preview and full-size
delivery; MCP uses its complete persistent-server lifetime. It excludes the
Python fixture/judge and is not total system memory. Missing or zero observations
and even a one-byte overrun fail. `memory-budget.json` records the unchanged
ceiling, measurement scope and every observed process peak. The fixture generator
may reuse its immutable bytes between repetitions; every engine workspace,
import, session and delivery remains fresh, and generation precedes task timing.
External arms separately label their enclosing client/launcher process peak as a
conservative upper bound; they do not report it as exact engine-only memory.
Unavailable Linux commit observations fail this budget check explicitly.

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

The solve retains actual attempts in attempts.json and ends before judgment.
The harness freezes recovery-observations.json at that boundary, retaining the
fault states and output identities. At the post-interruption inspection
checkpoint it reads the checksummed ledger directly; short-lived states need not
be caught by periodic polling. The independent judge reopens both saved revisions,
current editable artwork, session/job receipts and the publication ledger, renders
fresh focused/full previews and performs a fresh overwrite refusal. It compares
every delivered pixel with the authored texture and green badge, and verifies
that the current orange edit changes no other controls. All eight check IDs and
the original PNG identity remain fixed. Judge requests/traffic/timing are separate
from the solve. Retained attempts and verdicts alone cannot establish success.

Terminal comparisons preserve attempt, worker/runner, pinned document, receipt,
progress and error identity. They allow the final worker memory report to arrive
after publication; updated timestamps are not publication identities. Complete
owned-process lifetime accounting remains mandatory at close. Negative artifact
tests reuse one independently queried durable state for mutations of retained
files; changed-engine-state tests and every benchmark trial reopen all oracles.

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
Container totals include the separate judge CLI processes; ordinary process/call
metrics exclude them. External clients use the local file-channel bridge to
request ordinary commands and owned fault controls. Their engine tree is measured
separately from their client/launcher tree. Captures retain the fault observations,
actual engine traffic, process accounting and preview availability; import never
reinjects faults. Required artifact checks remain independent of those recorded
metrics. Genuine model trials are still required.

B20 uses an original 32x16 two-frame transparent animation with 3/25- and
2/25-second holds, looped twice at 25 fps. A reviewed edit moves only the first
frame's artwork. Independent judges check the exact editable snapshots, every
PNG sample and the successor manifest. A real saved Cutbolt overlay timeline
receives the new compiled graphic only through explicit preview/apply. Complete
snapshot comparisons preserve unrelated clips, assets and old revisions; undo,
stale writers and the original receipt's retry are checked.

An independent FFmpeg/ffprobe invocation decodes both complete compiled animations
and the original, revised and undone timelines. Every RGBA byte is checked against
the original samples and the documented encoded-sRGB color/matte quantization;
every timestamp is within 1 ms container precision plus 1 microsecond text
precision. Stream dimensions/rate/codecs and all silent 48 kHz stereo PCM16 samples
are checked. Source and delivery files remain byte-identical. This is a bounded
interop workflow on identified builds, not a broad video-editing or performance
comparison. Cutbolt uses its synchronous CLI in both trials; `--transport` selects
the Inkbolt interface.

Consumer traffic lives under `consumer/`, with decoder arguments and output under
`consumer/judge/`. `consumer-report.json` retains executable identities, commands,
round trips, bytes, retries and OS process-tree accounting. The caller receives
its first JSON input only after joining a kill-on-close Windows job; descendants
cannot break away. The OS continuously tracks
[job and process commit peaks](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information),
including short-lived encoder/probe children. Every call must end with zero
active processes and positive complete memory observations. A timeout or failed
assignment fails the call and cleans up only its owned processes. Decoder/judge
work is recorded separately and excluded from consumer memory. The three explicit
executables are hashed before and after each trial and the complete suite.

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
  Report/row schema version 2 separates calls marked `phase:"judge"` from ordinary
  counts, bytes and round-trip time, preserving their raw records and separate
  `judge_*` totals. `judge_separated:true` identifies separated reference tasks
  (currently B01-B19); external lifecycle support is B01-B19, with B19 requiring Windows.
  Judge calls alone cannot establish a successful solve.
  For B20 these ordinary fields describe Inkbolt; `consumer` records the Cutbolt
  side. `total_engine_commands`, `total_engine_retries`, `total_request_bytes`,
  `total_response_bytes` and `total_engine_roundtrip_seconds` include both engines.
- Retries identify a previous byte-equivalent logical request through its canonical
  hash. Expected failures, invalid calls and replayed receipts are separate counts.
  B17 retains a deliberately dropped response for the judge and explicitly marks
  it unobserved by the scripted recovery path.
- Round-trip time includes process or stdio transport and JSON costs. For migrated
  tasks, scripted wall time stops before judging; other adapters still include
  their interleaved oracle work. Both include discovery after fixture setup.
  First verified preview is the recorded completion time of the earliest image
  response or delivery later accepted by its independent pixel oracle. It is a
  retrospective availability measure, not a model's assessment of usefulness.
  Separated reference tasks match judged PNG bytes to an observed solve preview
  response, or match both hash and length to a successful PNG publication result.
  A judge render, missing/lost response, wrong media type or mismatched identity
  cannot supply missing preview timing.
  B13/B14 independent publication probes use a separate judge-only CLI workspace;
  their reference solve transport remains unchanged. Explicit probe rows retain
  their command bytes, timing and process observations, counted once as judge
  traffic even in MCP trials. MCP server memory excludes these separate judge
  processes and the reported scope says so.
  B19's overlapping CLI callers mean summed round trips need not equal wall time.
- Windows memory uses OS lifetime high-water marks: the maximum individual CLI
  process peak (excluding separately tagged judge calls) or the persistent MCP
  server peak, which still includes judge activity and cannot be split into phases.
  B19 additionally includes every
  supervisor, runner and owned console host, with separate identities and peaks.
  These are maximum individual-process peaks, not a concurrent memory sum. The
  Python driver is excluded. Unavailable memory stays null; these records
  do not imply another platform is supported.
  B20 separately reports `consumer_peak_tree_commit_bytes`, the maximum of the
  consumer's per-call aggregate job peaks. It is not combined with individual
  Inkbolt process peaks or presented as whole-machine memory.
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

Use `python tools/verify.py --only test_agent_benchmark` for the common adapters.
Use `--only test_benchmark_diagram` for the separated B01 contract.
The photo and recovery workflows have focused `test_agent_benchmark_photo` and
`test_agent_benchmark_recovery` modules. `test_agent_benchmark_handoff` checks
fail-closed dependencies, independent alpha/time expectations and owned process
accounting/cleanup without external media tools. It does not substitute for B20:
run the release driver with `--task B20 --repetitions 1` and all three executable
paths for focused real-consumer feedback, on each changed transport. Run full
`python tools/verify.py --thorough` at a milestone. Repeated release benchmark
trials are milestone evidence, separate from the 180-second routine feedback loop.
