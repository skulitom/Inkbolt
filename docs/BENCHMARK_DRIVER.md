# External benchmark drivers and captured trials

The W2 external lifecycle supports B01-B20. B19 and B20 require Windows for
their measured process controls. The baseline reports B17-B19 as
`not_applicable` with engine-specific reasons. This is not a
complete model benchmark or evidence that Inkbolt beats the baseline.

## Configure a client

For an installed Codex CLI, use the [local evaluation adapter](BENCHMARK_CODEX.md).
Its model and settings are supplied entirely by external run configuration.

Keep configuration, transcripts, generated workspaces, tools and reports outside
the repository. A version-1 driver configuration has exactly these fields:

```json
{
  "schema_version": 1,
  "kind": "model",
  "client": {"id": "your-client", "version": "the-exact-client-version"},
  "model": {"id": "the-exact-model-id", "settings": {}},
  "argv": ["C:/Tools/client-adapter.exe"],
  "driver_files": ["C:/Tools/client-adapter.exe"],
  "timeout_seconds": 600
}
```

Use your actual executable paths and complete model settings. Include adapter
scripts/configuration files in `driver_files` so their hashes are checked before
and after execution. `argv[0]` must be an absolute executable file; the launcher
appends one argument, the absolute `evidence/request.json` path. It uses an owned
process tree, a fixed workspace and a deadline; there is no shell interpolation.
The client must enforce the request's tool policy. Process cleanup is not a
filesystem or security sandbox. Credentials come only from the inherited
environment, never configuration, settings or transcripts. Console output is
not retained; the adapter must produce its declared credential-free transcript.

Use `kind:"synthetic"` for any fake/scripted driver. Tests refuse to let the
repository's fake client impersonate a model. Its artifacts and usage can test
the lifecycle but never establish actual model-run completion.

```powershell
python tools/agent_benchmark.py --arm model --driver-config C:/Work/client.json --task B01 --repetitions 5 --output-root C:/Work/model-01 --conditions "Actual machine and load conditions"
```

The model arm builds and pins the release executable. Each request names its
workspace, exact prompt, output paths and MCP configuration (`--tools core`),
and supplies the executable for clients that use the CLI. A portable contract
binds task/repetition, arm, prompt, original fixture hashes, model/settings,
client version and executable/tool identities. The transcript and usage must
refer to this contract. `--transport` selects the reference runner's transport;
external-client reports describe the actual adapter protocol as external.

For B01, B06 and B07 native snapshots, the agent may choose any font store inside the captured
workspace. The judge finds a complete content-addressed font/license pair there,
checks both lengths and hashes against the original inputs, and supplies that
store when independently rendering the published snapshot. Missing, corrupted,
linked or external copies cannot substitute for retained resources. The judge
does not import the font on the agent's behalf or assume the default store name;
captured trials must also reopen after workspace relocation.

B07 accepts explicit first-baseline controls as well as default ascent placement.
The prompt prescribes local glyph origins and sheet baselines, not one storage
encoding for those positions. Independent authored glyph/cluster coordinates and
both delivered/fresh pixels still reject a shifted baseline; all other text,
font, frame, snapshot and history checks are unchanged.

B03 and B05-B12 likewise locate the session ID from `session.json` within the captured
workspace, using its canonical database filename. A missing, linked, external
or ambiguous store fails. The engine then reads both declared revisions and
verifies the full history from that explicit root; filename discovery alone
does not validate a database. Historical and current snapshots must still match
the original and delivered documents exactly after capture relocation.

## Pinned baseline

The no-engine arm uses the same prompt and original inputs. B01 includes the
original named font; B02 has no asset dependencies; B03 supplies the same original
5,000-object JSON layout to both arms; B04 supplies the same original SVG;
B05 supplies the same JSON palette and artwork; B06 supplies the same original
linked-flow JSON layout, geometric font and license; B07 supplies the same four
logical strings, directional geometric font and license; B08 and B09 each supply
an original RGBA raster JSON shared by both arms. The baseline does not build,
configure or launch Inkbolt. Provide an external JSON file with exactly `resvg`
and `python` absolute executable paths. The tools must be resvg **0.47.0** and a
Python environment containing Pillow **12.3.0**. Tool executable hashes and a
hash of the installed Pillow distribution files are recorded and rechecked.
Preserve downloaded package licenses; see [dependencies](DEPENDENCIES.md).

```powershell
python tools/agent_benchmark.py --arm baseline --driver-config C:/Work/client.json --baseline-tools C:/Work/baseline-tools.json --task B01 --repetitions 5 --output-root C:/Work/baseline-01 --conditions "Same machine and load conditions"
```

The request supplies only baseline tool identities and no Inkbolt MCP server or
executable. The client must disable other engine tools. B01 delivers editable SVG
and a PNG; its bounded source-judge contract is stated in the shared prompt.
The judge renders with system fonts disabled and only the original named font.
Artifact checks apply to both arms. The Inkbolt snapshot check is explicitly
`not_applicable` for the baseline, never omitted or counted as an artifact pass.

B02 delivers `editable.svg` and `board-0.png`, `board-1.png`, `board-2.png`.
The [shared icon-sheet prompt](../tools/benchmark_prompts/B02.md) specifies stable
board/icon IDs, spacing, ownership, sizes and colors. Its SVG source contains
three independent nested viewports; admission rejects external resources and
unbounded or changed geometry before rendering. Explicit `overflow="hidden"`
is also admitted on the outer canvas. Rectangle fill/stroke opacity attributes
are retained for independent rendering and the unchanged exact pixel checks.
The judge extracts each source viewport
into a fresh standalone SVG and compares its pinned-renderer output
and the delivered PNG with the same independently calculated pixels used by the
Inkbolt arm. No engine process or build is used in this baseline. The model arm
validates the delivered snapshot and freshly renders all three artboards; judge
traffic is recorded separately from the solve. Document, session and request names
are unconstrained; stable board/icon IDs are explicit task requirements.

B03 delivers `editable.svg` and `preview.png` in the baseline. The
[shared large-layout prompt](../tools/benchmark_prompts/B03.md) specifies all
5,000 stable IDs and local controls, and the one translated object. The SVG
judge rejects extra content, resources, changed controls and other transforms
before pinned rendering. Both arms compare every delivered and freshly rendered
pixel against the same independent geometry. The model arm also delivers
`editable.json`, `historical.png` and `session.json`; the locator names its chosen
session and original/current revisions. History must contain the exact fixture
and final snapshot, and its current revision must match the final delivery.
Those two engine-only history checks are explicitly not applicable in the baseline.

B04 delivers `revised.svg`, `preview.png` and `import-report.json` in both arms.
The [shared SVG-editing prompt](../tools/benchmark_prompts/B04.md) defines the
retained group/path controls, the one world translation and a bounded SVG subset.
The report binds the original source hash, source-to-delivery ID mapping and
actual ID/description losses. The baseline may retain both IDs and the description
without losses, or disclose their remapping/omission accurately; it cannot pass
by merely claiming a successful import. Its SVG is admitted before pinned
rendering. Inkbolt also supplies the unmodified `svg.import` result and an editable
snapshot. The judge independently repeats the import, validates the snapshot and
renders both that snapshot and the delivered SVG. The original receipt's full
disclosures must survive even if the final SVG restores its description.

B05 delivers `editable.svg` and `preview.png` in the baseline. The
[shared palette prompt](../tools/benchmark_prompts/B05.md) specifies its three
editable rectangles, two orange fills and unchanged green artwork. Bounded SVG
admission precedes independent pinned rendering; both the fresh render and
delivered PNG must match the common pixel oracle. Inkbolt also delivers
`editable.json`, `historical.png` and `session.json`. The snapshot must retain
both live swatch references with only the shared color and revision changed.
The saved original/current snapshots and session head must bind that exact
fixture and delivery. These three engine-only checks remain visible as
not applicable in the baseline; a successful artifact does not earn that credit.

B06 delivers `preview.png` and `flow-report.json` in both arms. The
[shared linked-flow prompt](../tools/benchmark_prompts/B06.md) defines the original
overflow diagnosis, final logical line intervals and the only permitted slot
repair. The baseline retains `layout.json` plus `editable.svg`: its editable
text and source intervals must agree with the retained logical story and frame
controls, before a fresh pinned rendering using only the supplied font. The
model arm delivers `editable.json` and `session.json`; independent inspection of
the delivered and original snapshots verifies both layouts and binds valid
history to the fixture, delivery and current head. Captured font stores are
checked in the imported workspace without relying on old absolute session roots.
Saved original flow and session integrity are explicitly engine-only checks.

B07 delivers `preview.png` and `shaping.json` in both arms. Its
[shared typography prompt](../tools/benchmark_prompts/B07.md) defines logical
source offsets, visual glyph order and local frame coordinates. The baseline
retains `editable.svg` with four editable Unicode rows and optional bounded flat
spans; its source must retain every logical scalar in order. The declared glyph
mapping is checked against authored intervals/metrics and a fresh pinned render
with distinct geometric glyphs. It is not attributed to the renderer's internal
cluster machinery, which its CLI does not expose. Inkbolt also delivers
`editable.json` and `session.json`; the judge reopens, freshly inspects/renders
the snapshot and binds it to valid current history. Exact pixels are unchanged
across arms; a plainly concatenated SVG run may fail even if its shaping report
claims the expected glyphs. Positioned editable spans are admitted, with the
same pixel oracle determining whether they succeed.

B08 delivers `editable.json` and `preview.png` in both arms. The
[shared masking prompt](../tools/benchmark_prompts/B08.md) specifies exact polygon
coverage, retained samples and zero RGBA outside the visible foreground. Inkbolt
delivers its native snapshot plus `historical.png` and `session.json`; the judge
reopens and freshly renders both saved states and binds the current head to the
delivery. The baseline's editable JSON is a bounded linked-layer manifest naming
`pixels.png`, `mask.png` and `selection.png`, with one shared layer/mask transform.
The original pixel layer remains complete. The pinned Pillow interpreter decodes
only the admitted local 16 by 16 PNG components and freshly composites layer and
mask. Selection/mask coverage, retained pixels, fresh composition and delivered
PNG are checked independently. The two history checks remain engine-only.

Observed first-preview timing is accepted only when its artifact hash matches a
delivered image whose corresponding pixel check passed. B02 can identify any of
its three board images; a failed board cannot supply a verified preview time.


B09 delivers `editable.json` and `preview.png` in both arms. Its
[local repair prompt](../tools/benchmark_prompts/B09.md) supplies the same original
16-by-16 raster and exact source/destination patch coordinates. The engine arm
retains the current snapshot, original revision image and `session.json` locator.
The judge compares all samples and unchanged document properties, then reopens
and checks both saved revisions against the current history head. Multiple edits
and independent session/request names are accepted. The no-engine arm retains
`pixels.png` and a fixed layer manifest; pinned Pillow independently decodes the
layer before either pixel check can pass. A correct preview cannot substitute for
correct retained pixels. Saved-history checks remain explicitly not applicable.

## Client result and observations

Write the requested `driver-result.json` and a separate transcript file in the
requested transcript directory. The result has exactly these fields:

```json
{
  "schema_version": 1,
  "contract_sha256": "copy the request's contract_sha256",
  "kind": "model",
  "client": {"id": "your-client", "version": "the-exact-client-version"},
  "model": {"id": "the-exact-model-id", "settings": {}},
  "transcript": "transcript.jsonl",
  "observations": null
}
```

Client/model/kind must match the request. The harness ignores solver verdicts
and runs the independent judge. Missing observations remain null. When the
client provides observed data, replace null with an object containing
`source:"client_reported"` and any available fields:

- `token_usage`: input/output/cached-input/reasoning token counts, using the keys
  `input_tokens`, `output_tokens`, `cached_input_tokens`, `reasoning_tokens`.
- `model_calls`, `engine_commands`, `request_bytes`, `response_bytes`,
  `invalid_calls`, `retries`: nonnegative integer observations.
- `agent_seconds`: observed nonnegative finite duration.
- `first_preview_seconds` and `first_preview_sha256`: a paired observation. Timing
  is accepted only when those PNG bytes pass the independent artifact judge.

Do not estimate unavailable metrics. Engine-only memory and engine round-trip
timing remain unknown unless a task's harness observes them separately, as in
B19 and B20 below; judge traffic is retained separately.
Reports preserve failures and distributions of available observations, including
token counts. Retained client reports are evidence, not authenticated attestations.

## Memory observation

The harness records `execution.memory` and the trial's separate
`external_process_tree_memory` field. On Windows it reads the owned Job Object's
lifetime commit peaks after cleanup, before releasing the handle. The
`peak_process_commit_bytes` value is the largest individual process peak;
`peak_job_commit_bytes` is the aggregate job peak, not a sum of individual peaks.
These counters retain short-lived children; see the public
[Windows job information contract](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information).

The scope is `owned_command_tree_including_launcher`: the Python launcher,
external client and locally spawned descendants, including tools and engine
processes through cleanup. Fixture generation and independent judging happen
outside that tree. Remote or already-running workers are outside this scope;
clients must not present offloaded work as a fully measured local solve. This
broader observation is not relabelled as engine-only memory. Without a separate
engine observation, `memory_complete` stays false and engine-only peak fields
stay null. B10 uses the
largest individual process peak as a conservative upper bound for the fixed
256 MiB budget. A larger enclosing-client peak does not prove an engine overrun,
but does fail to establish the budget. The aggregate job peak is reported
separately and is not compared with that per-process ceiling.

Only the harness supplies this field; client-reported memory is rejected.
Timeouts and failed clients retain available observations without becoming
passes. Unsupported platforms, failed queries, incomplete cleanup and older
captures without this field retain `available:false`, null peaks and a reason.
Linux resident-set memory is not substituted for Windows commit. Import validates
the recorded shape and preserves the original measurement; it never measures the
judge and attributes that result to the old solve. Capture identity is still not
an authenticated attestation.

B10's [shared prompt](../tools/benchmark_prompts/B10.md) retains the original
1920 by 1080 RGBA16 source and exact same-layer clone repair. The model arm
delivers the import and proposal results, original/edited/undone/redone snapshots,
focused PNG, two native TIFFs and a locator containing its chosen session/request
IDs. The judge independently builds native block identities from the original
channels, binds every snapshot and the review to durable receipts and the final
head, checks all immutable tile files, and freshly renders/exports the delivered
states. Its generated files stay outside external solver workspaces. Captures
rejudge after the original workspace and its absolute resource roots move.

The baseline retains an editable native TIFF with a bounded layer manifest and
the same focused PNG. Python byte processing is permitted to avoid accidental
8-bit multichannel conversion. The judge compares every TIFF channel with the
original numerical oracle and reopens the single-image RGBA16 TIFF with pinned
Pillow. The independent TIFF reader retains both BYTE and UNDEFINED byte fields,
including embedded-profile records, without changing native sample checks.
All original check IDs/classes and the 256 MiB budget remain unchanged;
the seven engine-specific checks are explicitly not applicable in the baseline.
Linux runs retain their artifact/history results but fail the memory-budget check
explicitly because this commit-memory observation is unavailable. They are not
reported as complete B10 passes.

B11's [shared prompt](../tools/benchmark_prompts/B11.md) retains the original
32 by 24 image under an isolated masked vector group. Only the shadow offset
changes. The judge reopens both snapshots, checks the complete composition and
canonical image bytes, renders current/original states, and binds them to the
saved revisions and final head. It accepts independently chosen IDs and multiple
editing steps; correct solver logs cannot replace the delivered evidence.
The image store is located by its exact canonical source bytes, and the saved
session by its ID; neither location must use the reference solver's folder name.

The baseline retains editable vector/group/shadow controls in a bounded manifest
and a separate opaque grayscale PNG mask. Pinned Pillow reopens the original and
mask; independent numeric composition retains intermediate precision until final
8-bit conversion. Both that fresh result and the delivered preview must match the
unchanged rational oracle. Image paths and all supported controls are admitted
before decoding. The five original check IDs/classes remain unchanged; historical
pixels and session integrity are explicitly not applicable in the baseline.

B12's [shared prompt](../tools/benchmark_prompts/B12.md) keeps the original font,
license and two image fixtures. A supplied named font companion changes only
naming/checksum metadata, so the baseline rasterizer can select the same glyphs
and metrics without changing the unnamed original. Both arms export the same
three artboard sizes and restore their editable base after selecting each row.
The model judge independently checks all snapshots, typed binding definitions,
inheritance, retained resource bytes, saved revisions and restored head. It
compares earlier PNGs with completed durable publication receipts and freshly
renders each selected artboard. Arbitrary non-artboard IDs and extra edit steps
are accepted; captures rejudge after their original resource roots move. The
judge finds intact font/license and image stores inside the capture. Publication
request IDs may live in separate retained receipt folders: read-only lookup
finds each ID, then the engine validates the selected ledger and receipt. Missing
or ambiguous receipt identities fail, and lookup never reconstructs resources
or receipts from the source fixtures.
The three binding keys may appear in any order, with their corresponding saved
base values. Their exact targets, types, dataset values and inheritance remain
required; reordering cannot substitute a different binding or change a snapshot.
Item roles are located through their type and parent, not a fixed flat-array
position. Full item data and each parent's sibling order remain exact; harmless
interleaving of different parents' items is accepted, including arrays produced
by native `add` operations. Saved snapshots must still match their actual history
and current head. The prompt's artboard names may be retained as matching display
labels or represented by the fixed IDs with default empty labels. Other labels,
changed parents, sibling order, geometry or properties still fail.

The baseline retains one shared text/image definition instanced by three SVG
viewports, the original and restored base SVGs, editable dataset values and
delivery hashes. It embeds only the exact supplied image bytes and renders with
system fonts disabled. Admission precedes the pinned rasterizer; the judge
independently renders each selected viewport and checks the delivered PNG too.
The original seven check IDs/classes remain fixed. Typed engine bindings and
session integrity are explicitly not applicable there. Retained delivery hashes
establish content identity, not authenticated filesystem history.

B13's [shared prompt](../tools/benchmark_prompts/B13.md) keeps the exact transparent
1920 by 1080 artwork, straight RGBA samples, stripped sRGB delivery and private
editable source note. The model judge reopens the source, checks the full preset
and artwork controls, and requires the exact note as a metadata value. The
author chooses its placement within Inkbolt's metadata schema; missing or
changed notes still fail.
It preflights and publishes a fresh PNG, and independently
attempts duplicate publication into a protected copy. Its three publication
calls use an explicitly recorded, judge-only CLI workspace, including when the
reference solve uses MCP. Captured workspaces remain unchanged. These calls and
their bytes are counted as judge work; they cannot supply solve preview timing.

The baseline retains a bounded editable SVG and a create-only delivery recipe.
Pinned Pillow encodes straight RGBA samples directly from the admitted geometry
and paint; its independent publication probe must refuse an existing protected
file and preserve its bytes. Both fresh and delivered PNGs face the same pixel,
sRGB and metadata checks. Missing/duplicate/invalid color tags, ICC profiles,
descriptive/private records and animation reject. All four original check IDs
and classes are unchanged; only the Inkbolt snapshot check is not applicable
to the baseline. Delivery hashes are content evidence, not authenticated client
action history.

B14's [shared prompt](../tools/benchmark_prompts/B14.md) retains the exact original
RGB and CMYK fixtures, fractional A4 trim size, asymmetric bleed, native process
and spot declarations and display preview. The model judge validates all editable
controls, saved source/current head and completed publication receipt; it freshly
preflights and publishes into an owned judge directory. Captures stay unchanged,
including after relocation. Fresh and delivered PDF identities, physical boxes,
embedded profiles and native operands must agree. Added swatch display labels
are caller-chosen; their ink definitions, profiles and tint controls remain exact.
The named deliverables may occupy subfolders inside the capture. Lookup requires
one contained, nonlinked file per name; missing or ambiguous files fail. Preview
timing, when supplied, binds the bytes at the admitted preview path.
Delivery limitations must include every engine-reported PDF loss and both prompt
disclaimers; additional disclosures are allowed. This artifact check is separate
from the engine-only history check, which still requires the selected completed
PDF receipt to match the delivery and saved source. A snapshot receipt cannot
stand in for the print publication.
The session and publication stores may use caller-chosen folders inside the
capture. Their delivered IDs must locate unique stores; the engine still checks
the retained receipt and saved history. Missing, ambiguous or corrupt stores fail.

The baseline retains a bounded logical print recipe and original profile files.
Ordinary Python may author native PDF; pinned Pillow color management derives
the display preview. Admission rejects altered controls, paths or profile hashes
before invoking that decoder. The bounded classic-xref PDF reader supports direct
and indirect resource arrays; a separate path interpreter checks actual painted
geometry, transforms, opacity and conversion state. Rendering intent set with
`ri` or cumulative `gs` dictionaries follows `q`/`Q` scope. Page and spot-alternate
color-space arrays may be indirect references; their resolved profiles remain
exact. Cyclic starts and reversed traversal of each simple rectangle are allowed;
crossed, missing or changed corners fail. For this standalone page's two opaque,
disjoint rectangles, either boolean page-group isolation/knockout flag is
equivalent. This does not admit nested groups, overlapping artwork, masks,
clipping or other effects. Explicit black-point compensation `OFF` remains
required; omission leaves processor choice, as explained in the
[PDF Association application note](https://pdfa.org/resource/pdf-2-0-application-note-001-black-point-compensation/).
These state/group rules follow ISO 32000-1 clauses 8.4.4-5 and 11.4/11.6.6.
Both previews face the original exact pixel oracle.
PDF deliveries are bounded to 1 MiB; recipes to 8 KiB. This proves the stated
synthetic native declarations and display result, not press calibration, general
PDF rendering or authenticated preflight history. All seven check IDs/classes
remain fixed; only the two Inkbolt source/history checks are not applicable.

B15's [shared prompt](../tools/benchmark_prompts/B15.md) preserves all four original
fixture hashes: two PNGs, one corrupt cache entry and the source document. The
model judge checks full document equality apart from revision, both replacement
cache identities, correctly paired diagnostic locations and a fresh preview.
Creation/repair receipts, current session state and history must agree with the
retained proposal's source/result hashes and resource-action fingerprint.
The full dry-run result may be retained directly or inside the CLI's exact
successful `{"ok":true,"result":...}` envelope. Error responses, extra envelope
fields and changed proposal data fail the same historical-binding check.
The saved session is located by its delivered ID inside the capture, without
requiring a default session folder. Missing, ambiguous or corrupt history fails.

The recorded absolute workspace root locates stored binding data; the judge
compares those paths lexically and never follows them after relocation. Only the
captured broken/repaired directories are used for fresh diagnosis and rendering.
Those two resource directory names remain explicit requirements of the task.
It neither repairs old states nor changes captured files. This establishes
consistent retained content, not authenticated historical review actions.

The baseline keeps the unchanged logical source and a separate before/after
binding recipe. Admission rejects changed artwork, descriptors, paths, malformed
cache entries and unrequested repair of the original missing entry before the
pinned imaging process runs. Pillow independently decodes the two original PNGs
and composes the repaired cache; both fresh and delivered pixels face the original
oracle. Diagnostic array order is immaterial, but exact code/location pairs are
required. All six check IDs/classes remain fixed, with only the two Inkbolt
history/binding checks explicitly not applicable to the baseline.

B16's [shared prompt](../tools/benchmark_prompts/B16.md) keeps the original
font/license hashes and overflow setup: AA at size 20, width 12, height 24,
without wrapping, plus an unrelated rectangle. Only the width changes to 24.
Its independent model judge reopens both snapshots, checks every normalized
control and actual font/license bytes, and reruns the original actionable
diagnosis, failed preflight, repaired preview and successful preflight. Durable
creation/repair/publication receipts, current history, retained proposal hashes
and the normalized text-action fingerprint must agree. The retained review
image and delivered PNG face the original exact pixel oracle. A new output name
lets the judge preflight without modifying the captured workspace. It uses local
captured font resources rather than following old stored resource paths.
The prompt requires the default font store, but does not prescribe session or
publication store folders. The judge locates the delivered IDs in unique,
contained captured stores and rejects missing, ambiguous or corrupt stores.
The full review may be stored directly or in the exact successful CLI
`{"ok":true,"result":{...}}` envelope; proposal and image checks remain identical.
Publication binding belongs to the engine-only history check, so a wrong receipt
cannot invalidate otherwise correct artifact pixels or delivery identities.
Snapshot comparison uses the reopened document values, so omitted defaults are
accepted only when every control has the same meaning. The delivered repaired
source must still reopen as revision 1 and match saved history; an omitted
revision defaults to 0 and fails. Version 2 makes that file requirement explicit.

The baseline retains before/after JSON recipes and editable SVG text in a bounded
16 KiB contract per source, with explicit no-wrap/error semantics in the recipe.
Prompt version 2 also specifies the font map, integer font-file byte length,
boolean wrap control and bare RGBA arrays. The version-1 trials exposed missing
type information in those instructions and remain separate preliminary evidence;
fresh matched version-2 trials are required before comparing repair reliability.
Its admission checks all controls and forbids external resources or unrequested
SVG constructs before launching the pinned rasterizer. Original SFNT advance
metrics independently establish overflow and the required width. A named font
companion differs only in the name table and associated checksums; original
font/license identities remain retained. Pinned resvg renders the actual repaired
SVG, and fresh/delivered/review pixels face the same oracle. The prepared and
published byte identities must match. Fresh renderer bytes may use a different
valid PNG encoding; decoded pixels must still match exactly. Both manifest
hashes must bind the actual final PNG. Reports establish content consistency, not
authenticated historical actions. All five fixed check IDs/classes remain;
only Inkbolt history is not applicable to the baseline. Synthetic client runs
remain infrastructure evidence, never model trials.

B17's [recovery prompt](../tools/benchmark_prompts/B17.md) starts the external
client after the harness has created work from the unchanged two-object fixture
and sent the exact retry-request.json once. The harness deliberately withholds
the successful move response from solver inputs. It retains that response in
lost-response.json outside the workspace, pins its identity before client launch,
and checks it again afterward. The client recovers the receipt, retries before
undo, reviews the moved image, undoes once, retries again and saves the restored
revision. The reference retains all nine original commands; external client
recovery has seven reference calls plus two separately measured setup calls.

`harness_setup` records file identities, engine command count, request/response
bytes and roundtrip duration. These are harness observations, separate from
client-reported metrics and the owned external process's memory measurements.
Missing client usage remains unknown. Captured trials retain and validate setup
identity/metrics and never reinject the edit on import. The setup and client
execute on the same shared host; this is not a security sandbox. The client's
tool policy forbids reading setup responses; capture hashes establish identity,
not an authenticated attestation that a client obeyed that policy.

The independent judge compares retained attempts with the withheld response and
fresh durable receipts, checks exact original/edit/undo sources and fresh pixels,
and repeats the historical retry on a bounded private copy of the captured
session. Original captured files remain unchanged. The copy must preserve head
revision 2 and the restored state while returning the original move receipt from
revision 1. Saved artwork is compared after reopening its ordinary defaults;
omitting a default field is valid, but missing/stale revisions or changed
resolution still fail. Wrong request fields, receipts, state IDs, extra revisions, changed
artwork and setup evidence fail. Both original fixture identity and all five
check IDs/classes remain fixed. The engine-specific no-engine baseline remains
explicitly not applicable, without launching Inkbolt or the client.

B18's [conflict prompt](../tools/benchmark_prompts/B18.md) starts the client at
revision 1 with an actual stale-request.json. Three separately measured harness
commands create revision 0, review the target move and commit the other writer's
move. The client submits the stale request unchanged, retains its actual error,
reviews/applies the replacement at revision 1 and delivers editable.json,
preview.png and historical.png. It also retains rejected.json and review.json.
The review accepts either the result object or its exact successful CLI envelope
(`ok: true` and an object `result`, with no extra envelope fields). Invalid
reviews fail the intent check while independent pixel/history checks still run.
The final document is compared after reopening defaults, with revision 2 and
every source control still required. The explicit rejected.json error contract
and B17 attempts.json result contracts are unchanged.
The original reference has ten commands including setup, seven after setup.

conflict-setup.json and a bounded copy of the pre-client database stay outside the
solver workspace. Their identities are pinned before launch, checked afterward
and preserved on import without rerunning setup. The supplied request is bound
to that evidence. The judge reopens all original/other-writer/final documents and
receipts, checks current and historical pixels, and binds the replacement's
normalized action fingerprint and base/result state hashes to its durable receipt.
It reproduces the original stale rejection on a private copy of the pre-client
database and checks that revision 1 stays unchanged. Testing only the final head
would instead encounter an already committed request ID and prove a different
condition. The private probe preserves resource bindings and workspace boundaries;
it does not render through resource paths outside that private workspace.

Original source bytes and all five check IDs/classes remain fixed. Extra commits,
lost edits, changed geometry/paint/controls, wrong proposals/errors and altered
setup evidence fail. Captured source files remain unchanged during import and
judging. These identity checks are not authenticated proof of historical client
behavior. The entire engine-specific no-engine baseline remains not applicable.

B19's [recovery prompt](../tools/benchmark_prompts/B19.md) uses a local command
bridge. Its request has recovery_bridge argv and no direct engine executable or
MCP configuration. The client sends sequential JSON command/control messages on
stdin. The harness owns every engine process and provides three bounded controls:
cancel-active, hold-queue and interrupt-queued. The client still imports, edits,
reviews, submits, inspects, resumes and retries through ordinary engine commands.
Controls accept no process IDs and use the observed owned runner/supervisor.
Admission must precede the newer edit; a client failure releases the queue gate
and closes both the separate client tree and engine tree. No network listener,
engine test hook or database mutation is introduced. Message/count/traffic bounds
and command/client deadlines are enforced. Preparation starts no processes.
The final overwrite refusal may use either `document.publish` or
`session.publish`; both trigger the same output-identity checkpoint. Reserved
`command` and `step` fields belong at message level. Nesting them in arguments
is an explicit protocol error before engine execution and still fails the trial,
even if later engine operations succeed.
Prompt version 3 explicitly fixes the observed job queue and publication ledger
at `.inkbolt/jobs`. Session and image-resource folders may be chosen within the
workspace; the judge locates the unique session and exact original image samples
without redirecting fault controls to another queue.

The request contract binds the control helper identities. recovery-control.json,
recovery-observations.json, recovery-evidence.json and actual engine traffic stay
outside the client workspace and are bound into harness_recovery. Capture
validation requires complete process accounting, measured traffic/memory and an
exact metric schema; imported metrics cannot supply a verdict or model credit.
Original artifact/history/fault checks remain mandatory. The harness reports
observed engine metrics and preview availability; client/model/token usage remains
separate and unknown unless supplied. B19's client-process memory excludes the
separately owned engine tree, whose individual process peaks are reported directly.
These are shared-host observations, not authentication or a security sandbox.
Returned engine errors remain in the observed calls and can be repaired by the
client; they do not by themselves fail a successfully judged external task.
Invalid-call counts use the same INVALID_JSON/INVALID_REQUEST classification
as the reference adapter. Unrecovered artifact, judge, protocol or containment
failures still fail, with identical scoring for live and imported evidence.

Import copies and validates retained evidence, reopens the captured documents,
job/session receipts and publication ledger, and rejudges without reinjecting
faults. Original before/after physical file identities must match each other;
the copied file's new identity is not compared to its original inode. File
content identities and unchanged source/destination captures remain mandatory.
The source check compares reopened semantics, allowing omitted optional defaults
while still requiring revision 1 and every original/edit control. Missing,
ambiguous or invalid session stores, missing/corrupt image samples, changed
resolution, artwork or resource bindings remain failures. The twelve independent
judge calls, original check IDs and observed process/publication checks remain.
Unix jobs remain unsupported, so B19's external model arm refuses those hosts
explicitly. Its entire no-engine baseline stays not applicable.

B20's [linked-graphic prompt](../tools/benchmark_prompts/B20.md) supplies the same
original two-frame source to both arms. Pass explicit `--cutbolt`, `--ffmpeg`
and `--ffprobe` paths; executable hashes are bound into the contract and checked
before and after execution. The request supplies handoff_bridge argv, with no
direct engine executable or MCP configuration. Send sequential JSON messages
with engine inkbolt or consumer, command, arguments and your own unique step
label. Capabilities/schema discovery goes through the same measured bridge.
The judge locates consumer actions by their actual requests and order, without
requiring reference-client step labels. Required object/session/request IDs
are stated in the prompt.
The post-relink snapshot may read the current head or explicitly request revision
2, between relink and undo. Its observed response must contain revision 2 and
match the independently reopened saved project. Historical reads still explicitly
request revision 1 and must return it. Wrong revisions or observations taken
after undo cannot supply the post-relink snapshot.

The stale mutation may use different operations from the relink. It must use
request ID `stale`, target revision 1 of the same `linked` project and owned
store, and contain a nonempty operation list. Its actual recorded response must
be `REVISION_CONFLICT`. The exact retry still repeats the complete relink request
and returns its saved receipt; undo, restored snapshots and independently checked
history must remain unchanged. Matching the stale operation list to the relink
is not part of the task contract.

The judge locates the unique retained Inkbolt session within the capture. It
independently reopens all three authored source snapshots, accepting omitted
optional defaults while requiring their explicit revisions and exact semantics.
The source review may be its result object or the exact successful CLI envelope;
malformed reviews fail that check without suppressing other independent checks.
Typed handoff source files, content hashes and observed consumer response objects
remain exact contracts. Reserved nested command/step fields are protocol errors
before either engine can run, and later successful calls cannot erase them.

All engine processes are harness-owned; consumer paths stay within the trial
workspace, with fixed store and output destinations. The broker limits message
size, count and total traffic, freezes delivered-file identities after compilation,
and retains actual command responses and complete process observations. Additional
optional files such as inspection reports may accompany either arm's required
delivery files. Every initially observed file must remain present with identical
bytes; extra files do not replace required sources, frames, manifests or movies.
The same bounded inventory and path checks apply to both arms. Ordinary
returned engine errors can be repaired; control, containment and judge failures
still fail. Preparation starts no engines. Consumer accounting currently requires
Windows, so this external adapter explicitly refuses other platforms.

handoff-control.json and handoff-observations.json remain outside the solver
workspace. harness_handoff binds their bytes, recorded requests/responses, fixed
metric fields and observed preview identities/timestamps. Import copies and
validates these two proof files, retains original solve costs, and independently
reopens histories and decodes outputs without launching the client. Separate raw
consumer logs remain in the original evidence directory. Moving a captured run
does not require rewriting saved assets or history. Capture identities are not
authenticated attestations or a filesystem security sandbox.

The model arm reports separately measured Inkbolt CLI memory, consumer process
tree memory and combined command/traffic totals. Client-tree memory excludes
these separately owned engine processes. Judge queries and decoders are excluded
from solve metrics. A verified model-arm preview uses its actual observed engine
response time and PNG hash; token/model usage remains unknown unless supplied.

The B20 baseline authors an editable layer manifest, exact PNG frames and ordinary
consumer scene/project JSON with the pinned image tools. It never builds or calls
Inkbolt, including during judging. Both arms use the same pinned Cutbolt consumer
solely to compile and render the required video. This is a common video dependency,
not an Inkbolt handoff or saved-history guarantee for the baseline. Pinned Pillow
reconstructs the edit, and independent decoding checks every video frame, timestamp
and silent PCM sample. Both arms retain eight artifact/source checks; all eight
engine checks stay visible as not applicable in the baseline. Its Inkbolt command
count is zero and Inkbolt memory is unavailable; consumer costs remain measured.

## Preparation and import

`--prepare-only` writes requests and fixtures without launching the client. B17
also executes its two harness setup calls and retains the withheld response;
B18 executes its three setup calls and retains the pre-client conflict state. It
returns `prepared`, never a task pass. For now, use a configured client adapter
to capture a prepared/external-client session in this protocol. Arbitrary older
client transcript formats require an adapter; automatic format detection and a
manual capture-sealing command are not implemented.

`--import-root C:/Work/model-01` rejudges a captured run into a **new** output
directory with the same arm/configuration/settings. Each `01-B01/` entry contains
`workspace/` plus `evidence/driver-result.json`, the transcript and `capture.json`.
Import verifies the prompt/fixture/tool contract, complete captured workspace,
result and transcript hashes before copying. Links and changed evidence reject.
Original captures stay intact; judge logs and renders are outside solver inputs.

The capture records the original host, driver identity, observed execution and
workspace files. Never relabel a synthetic capture as a model run. Exact content
identity cannot independently authenticate how an external transcript was made.

`actual_model_benchmark_complete` is derived from a complete fixed twenty-task,
at-least-five-repetition model-arm run with retained genuine-client evidence and
unchanged inputs. B01-only runs cannot set it. The
[matched comparison report](BENCHMARK_COMPARISON.md) checks retained identities,
separates artifact/workflow scores and produces a losing-task list with explicit
usage uncertainty. Genuine matched model/baseline trials remain required.
