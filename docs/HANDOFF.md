# Pinned graphics handoff

`handoff.export` prepares a version-1 delivery for a local Cutbolt scene. It works
through the Rust library, JSON CLI and MCP dispatcher. `document` accepts the same
inline snapshot, content-bound file or exact saved-session reference as other
document commands. Source resources use the existing explicit or saved bindings.
No listener, companion process, file write or automatic relink occurs during export.

```json
{"command":"handoff.export","document":{"session_id":"graphic","revision":2},
 "options":{"link_key":"title","selection":{"type":"sequence"},
 "duration":{"num":2,"den":5},"frame_rate":{"num":25,"den":1},
 "timing":"strict","end":"loop","alpha":{"type":"transparent"}}}
```

Use a workspace or supply `session_root` inside the document reference. For a
still, choose `selection:{"type":"still"}`; if the source has a sequence, an
explicit `frame_id` is required. A still holds that one frame for the complete
destination duration. `scale` and `render_options` use the existing renderer.

The result contains `handoff:{sha256,manifest}`, a `manifest_file` identity and
base64 `files`. Files include the exact typed source snapshot, unique PNG images,
the Cutbolt scene JSON and the manifest itself. Each has a content-derived flat
filename, exact byte count and SHA-256. Repeated sequence entries remain distinct
in the ordered manifest even when they share one image file. The source snapshot
includes all retained metadata, including private working notes; it is a local
editable master, not a sanitized public export. History and external resource
stores are not included. PNG delivery strips descriptive metadata.

Write the returned files create-only in a new directory, with the manifest last.
Then call `handoff.inspect` with the pinned `handoff` and that `input_root` before
consuming the scene. Inspection reads the exact files once, checks lengths/hashes,
rejects indirect file paths, validates source identity/selection/dimensions and
static sRGB RGBA8 PNG decoding, and derives the scene again from the manifest.
It writes nothing. This verifies the declared delivery and trusted pin; it does
not re-render the source or establish authorship. A concurrent later file change
still fails Cutbolt's own content checks when it reads the scene's image identities.

Without `input_root`, inspection checks only the manifest and its timing contract
and reports `files_verified:false`. With a root it requires every file, including
the exact manifest, and reports `files_verified:true` only after all pass. The
editable source's external stores are never followed during inspection.

## Exact timing and color choices

All destination choices are explicit. Rates are 24, 25, 30, 50, 60, 24000/1001,
30000/1001 or 60000/1001. Duration must contain at least one complete output frame,
last at most 120 seconds, and land on a 48 kHz sample boundary. In particular, the
last two fractional clocks need multiples of five frames at the output boundary.

Sequence holds preserve original delay fractions. A zero source denominator means
100; zero-delay animation frames reject because their speed is consumer-dependent.
A selected still may use such a frame because its destination hold is explicit.
`timing:"strict"` requires every source hold to align with the destination clock.
`sample_start` explicitly samples exact output-frame start times into half-open
source intervals. Individual holds are never rounded. End behavior is explicitly
`loop`, `hold_last` or `transparent`. Source play count remains recorded; destination
duration and ending determine playback. `include_schedule:true` on inspection
returns the selected source index, or null, for every output frame. Default
inspection returns its count and content hash without the expanded schedule.

Images are flattened straight RGBA8 encoded sRGB. Output ICC associations reject;
clear them explicitly on a delivery copy rather than silently changing color.
The scene either uses `alpha:{"type":"matte","background":[R,G,B]}` for opaque
encoded-sRGB composition, or `alpha:{"type":"transparent"}` for a transparent
overlay. Cutbolt's transparent scene path uses separate 8-bit color/matte passes
and straight-alpha quantization; opaque and transparent endpoints are exact, but
partly transparent RGB can change through that quantization. The manifest retains
this loss declaration. Native depth, editable scene layers and resource stores are
not transferred by the flattened PNGs; keep the source master.

## Linked revisions

Pass the complete previous pinned `handoff` as `previous` when exporting an edited
source. The engine verifies its manifest digest and contract, requires the same
`link_key` and source document ID, and requires a strictly greater source revision.
The new manifest records its predecessor hash and revision. Different identities,
stale revisions and modified predecessor manifests reject. The pin is not a proof
of ancestry in an external session store: pass exact saved references when that
history matters, and retain both trusted receipts.

Save and verify the new delivery in a new directory, inspect/render its scene, then
explicitly replace the intended graphic in the destination project through its
normal reviewed revision workflow. Keep the old scene and compiled asset. Nothing
silently changes an existing Cutbolt project, scene or saved timeline revision.
Changing delivery settings at an unchanged source revision can be a separate export;
the version-1 predecessor relation specifically tracks edited source revisions.

`python examples/handoff_workflow.py --output NEW_ABSOLUTE_DIRECTORY` demonstrates
two pinned still revisions followed by an ordered sequence, verifies the old
delivery after the edits and checks source history. Optional `--cutbolt EXE`
inspects and renders all three scenes using that local installation.

## Bounds and evidence

Deliveries contain at most 256 ordered frames, 4096 pixels per axis, eight million
pixels per image, 16,777,216 aggregate frame pixels and 32 MiB of unique files
including source, scene and manifest. Existing render work, precision, source,
supersampling and resource limits still apply. Cancellation is checked during
planning, frame processing, file-reading blocks and before returning a complete
export. One bounded PNG codec operation can finish before the next check. A failed
export returns no partial batch and has no file side effects. Example publication
may leave its own incomplete new directory after interruption; it must pass file
inspection before use and is not a durable publication transaction.

`tests/test_handoff_cli.py` independently checks hashes, retained source, complete
pixels, all native frame clocks, exact loop/end selection, strict rejections,
damaged/missing files, workspace references and explicit saved-revision updates.
Scripted interface evidence remains distinct from actual model task trials. This
contract advances the readiness handoff requirement and awards no engine checkpoint.
