# Large-image workload suite

`tools/measure_scale.py` implements the four fixed `scale-v2` cases in
[the primary plan](../FIX_PLAN.md#w4-practical-raster-scale-p1-multiple-substantial-milestones-w0-d7-a5).
It is separate from `scale-v1`, the native-* suites and B10's unchanged 256 MiB
photo budget. All four fixed target-size cases pass independent Windows/Linux
fidelity checks, with fresh full suites on both platforms. Five-repeat regression
gates and Unix commit-budget evidence remain open. No new engine checkpoint is
awarded.

The first Windows target run passed JPEG, the complete photo workflow and A2
delivery, but refused the three-shape 8192 x 8192 render on the conservative
whole-canvas paint estimate. That failed attempt is retained. The renderer now
selects its existing bounded spatial index for this condition even below the
usual item-count threshold; actual overlapping paint work and replay budgets
still reject when exceeded. The unchanged target fixture now passes on Windows
and Linux. Its size, artwork, oracle and processing ceilings were not reduced or
relaxed to obtain the pass.

| Case | Fixed input and independently checked result |
| --- | --- |
| `jpeg-24mp` | 6000 x 4000 original analytic studio scene; baseline and progressive JPEG, native import, every RGB channel within three code values of the pinned independent decoder and exact alpha |
| `photo-50mp` | 8192 x 6144 true RGBA16 TIFF; cloned patch, selected brush, content-sensitive fill, feathered whole-image mask, TIFF delivery, every undo/redo state and pinned original history |
| `print-a2` | 4961 x 7016 at 300 ppi; every PNG pixel and independent PDF page, path and color checks |
| `rgba8-8192` | 8192 x 8192 render/export; opaque, translucent and transparent regions with every PNG channel checked |

The native photo fixture uses deterministic full-depth texture with a known
repair island. Expected samples come from original arithmetic and byte formulas,
never engine output or its receipts. Native checks validate every sample, block
header, content hash and manifest identity. TIFF checks independently parse every
strip. Each edit proposal must match the committed receipt, and all twelve
undo/redo steps must reproduce the exact retained document state. This exercises
the complete workflow, not every brush/repair mode or every layered-file format.

## Run and retain evidence

Use an external Python installation with **Pillow 10.3.0** for the JPEG generator
and independent decoder. It remains outside the repository and is not an engine
dependency. Its interpreter and installed package files are hashed in each JPEG
result. All fixture images are generated from original formulas; no photographs
or downloaded assets are used. The worker runs in isolated Python mode.

```powershell
python tools/measure_scale.py --output-root C:\Work\Evidence\scale-v2-01 --jpeg-python C:\Tools\scale-python\python.exe --conditions "Sequential local run; no concurrent verification; desktop load not controlled"
```

The parent directory must exist and the output directory must be new and outside
the repository. Run transports and verification sequentially for comparable
measurements. The default is five repetitions; `--repetitions` accepts 1-10.
`--case photo-50mp` selects a diagnostic subset. Duplicate cases reject. There is
no reduced-size command-line mode. Routine tests use smaller extents through an
internal fixture interface, explicitly record `fixed_fixture:false`, and cannot
establish scale acceptance or create a gate.

Each case gets a fresh workspace. Case order rotates; OS caches may be warm.
The runner retains source/build/host identities before starting, then every
command, response, error, source, output, oracle and final result. Earlier failed
attempts remain separate. Source preservation and unchanged candidate, executable
and host checks are mandatory. Exit 0 means the selected workflows passed on
unchanged inputs; it does not mean full scale acceptance. A failed workflow or
changed input returns 2. Missing final reports are incomplete runs.

Fixture generation, independent decoding and reporting are outside measured
engine lifetimes. Retained target-size sources and outputs consume multiple
gigabytes per repetition; the runner never deletes earlier evidence.

## Memory and regression gates

Every case records the separate [platform memory metrics](WORKLOAD_MEASUREMENT.md).
The fixed D7 ceiling is **512 MiB peak process commit**. Windows observations can
establish it; Linux RSS cannot. `commit_budget.status` is `passed`, `failed` or
`unavailable`; unavailable measurements never count as a budget pass. The report's
`full_suite_fidelity` concerns artifact correctness only, and
`complete_scale_acceptance` remains false.

`tools/workload_gates.py` accepts a complete successful Windows `scale-v2` report
with at least five repetitions. It checks every fixed command/oracle, dimensions,
commit observation, source/decoder identity and required helper hash. Reduced
fixtures, missing failures or changed JPEG tools cannot create a comparable gate.
The usual latency and memory regression policy applies, with memory headroom
capped at the fixed 512 MiB ceiling. An engine change cannot reset the original
budgets; a helper refresh requires an explicit reason and preserves them.

```powershell
python tools/workload_gates.py create --baseline C:\Work\Evidence\scale-v2-01\report.json --output C:\Work\Evidence\scale-v2-gate.json --reason "Five complete repetitions on the recorded host"
python tools/workload_gates.py check --gate C:\Work\Evidence\scale-v2-gate.json --report C:\Work\Evidence\scale-v2-02\report.json --output C:\Work\Evidence\scale-v2-check.json
```

Unix commit-budget evidence and host/gate comparability, the separate larger B10
variant, larger layered files and full W4 acceptance remain open. Tests of the
gate use synthetic records and make no engine performance claim.

## Target-size acceptance

| Platform | Fresh stages | Rust tests | Python executed | Explicit skips | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Windows | 270 | 309 | 2,799 | 24 | 881.891 |
| Linux / WSL | 270 | 275 | 2,772 | 51 | 596.554 |

Every stage passed on matching unchanged inputs, without reused, failed, pending
or out-of-scope stages. The five routine scale tests cover reduced fixtures,
independent sample/oracle failures, missing memory, retained helper failures and
gate rejection. They require no external JPEG package. Focused development
feedback passed in 117.0 seconds on Windows and 80.5 seconds on Linux.

One complete target-size repetition per platform passed all four cases. The
50 MP photo workflow has 30 engine calls and 31 independent checks, including
six reviewed edits and all twelve undo/redo steps. Edited/restored TIFF, A2 PDF
and PNG, and the 8192 x 8192 PNG hashes match across both platforms.

| Case | Windows engine seconds | Windows peak commit MiB | Linux engine seconds | Linux peak RSS MiB |
| --- | ---: | ---: | ---: | ---: |
| `jpeg-24mp` | 9.694 | 283.301 | 9.243 | 296.742 |
| `photo-50mp` | 61.824 | 36.676 | 41.725 | 50.656 |
| `print-a2` | 1.963 | 13.840 | 2.282 | 27.961 |
| `rgba8-8192` | 5.940 | 78.520 | 4.977 | 87.918 |

All observed Windows peaks are below the unchanged 512 MiB ceiling. Linux
resident measurements are complete; process commit remains unavailable. Engine
times exclude fixture generation, independent output checking and compilation.
Windows ran sequentially without another local verifier; the Linux diagnostic
allowed concurrent Windows full verification. Desktop load was uncontrolled and
OS caches may have been warm. These are fidelity/memory diagnostics, not latency
or five-repeat gate acceptance.

The original failed Windows attempt remains in `scale-v2-windows-target-01`.
The fixed Windows run is `scale-v2-windows-target-02`; the Linux run is
`scale-v2-linux-target-01`. Complete source, build, command, output and oracle
records are retained externally with `scale-v2-acceptance-02`.
Frozen source fingerprint:
`c00d31c65a3915ff24665b7e4b810d32979e01b5aa56b07a65cb0eefe1072ba1`.
Retained `audit.json` SHA-256:
`5aca800a3f1fc7b35191532ac96c70151c53a2b1e3d70614c4ca0c824302085f`.
The audit binds all 540 full-suite logs, exact binaries, every target evidence
file and matching output hashes. Subsequent Markdown-only updates are recorded
separately. Larger layered files, the separate large B10 variant, repeated gates,
Unix commit-budget acceptance and the remaining four original checkpoints stay
open; the registry remains 163/167.
