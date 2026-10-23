# Native storage for layered imports

`layered.import` can retain admitted RGB8 pixel layers as immutable native blocks.
This removes the inline-pixel limit for those layers. Larger canvases additionally
require `resource_profile:"large_raster"`. Existing requests keep their inline
representation and limits. This is an import increment; the original extended
layered-interchange checkpoint and full W4 acceptance remain open.

With a selected workspace:

```json
{"command":"layered.import","source_path":"original.psd","id":"editable","color_policy":"assume_srgb","resource_profile":"large_raster","storage":{}}
```

Without a workspace, provide an absolute `source_path` and
`storage.store_root`. The workspace's normal asset directory is the default
store. Storage version 2 is required; explicitly requesting version 1 fails.
The Rust entry point is `layered::import_with_options` with `ImportOptions`.
Earlier Rust import functions retain their original behavior.

## Retained content

Pixel layers become `stored_samples` with exact RGBA8 samples, including RGB
under zero alpha. Missing layer alpha becomes opaque. Layer bounds, order,
visibility, names, byte opacity, supported groups and authored masks retain the
[existing interchange contract](LAYERED.md).
Explicit profile conversion still converts RGB to working sRGB and reports that
interpretation. It preserves alpha but is not a promise of matching another
consumer's compositing.

Raw, RLE, ZIP and ZIP prediction decode one row per channel. The merged cache is
also decoded, validated and hashed by row; it is never substituted for editable
layers. Both container versions retain their framing and trailing-data checks.
Nested embedded sources use the same native storage and shared import budgets;
their explicit reconstruction policy and cache limits remain unchanged.

The resulting document works with native edits, snapshots, pinned session
references, undo/redo and the existing image export paths. Saving a snapshot or
session does not embed all pixel data: preserve its asset store as well.
Native layers are not yet supported by layered-format export. Large masks,
higher-depth layered channels and broader appearance semantics remain separate
work; unsupported inputs fail explicitly.

## Bounds and publication

| Resource | Bound |
| --- | ---: |
| Encoded input, still read as one bounded file | 32 MiB |
| Canvas with explicit native storage and `large_raster` | 67,108,864 pixels |
| Aggregate retained layer/cache and mask pixels across nested sources | 67,108,864 pixels |
| Aggregate decoded layer, mask and merged-cache work, conservatively charged as RGBA8 | 512 MiB |
| Private retained pixel extents | 256 MiB |
| Native tiles per layer | 4,096 |
| Inline authored masks per document | 65,536 pixels |
| Text and embedded-placement cache per record | 65,536 pixels |

Axis, coordinate, item, hierarchy, snapshot, store and render limits still apply.
In particular, partial edge blocks consume tile entries. Storage admission does
not raise rendering or editing work budgets. `capabilities.layered_interchange`
reports default bounds separately from `native_import`.

Decoded pixel extents use private temporary handles. Public blocks are written
only after the complete source framing, channels, merged cache, nested sources
and resulting documents validate. A malformed source, source-hash mismatch or
invalid document publishes no blocks. Cancellation or I/O failure during final
publication can leave complete unreferenced immutable blocks, as in ordinary
native sample import; it never returns a successful partial document or
overwrites an existing block or source. Private extents close on success or
failure. There is no automatic store deletion.

## Verification scope

`tests/test_layered_native.py` uses original synthetic inputs and independent
per-sample block and manifest checks. It covers both versions and all four
codecs, a two-megapixel import, block-crossing edits, historical snapshots,
undo/redo, independently calculated preview pixels, native nested sources,
groups/masks/profile conversion, opaque RGB, workspace/MCP defaults, admission
refusals and late failures without publication. Existing layered tests continue
to cover the inline route. These checks alone do not establish the full W4
memory/performance or editable layered return-trip gates.

### Windows and Linux acceptance, 23 October 2026

Both full runs executed all 271 stages on matching source inputs. Each retained
270 passing stages and one failed capability-limit registration check. The
follow-up added five bound mappings and the storage-version classification to
`tests/test_resource_limits.py`; no engine code changed. Fresh `--last-failed`
runs then passed all eight resource-limit tests on both platforms. The original
full-run failure and focused follow-up reports are retained separately.

Combined coverage is 309 Rust and 2,807 Python tests on Windows, and 275 Rust and
2,780 Python tests on Linux. The 24 Windows and 51 Linux platform skips remain
explicit and grant no feature credit. Focused implementation feedback took
69-118 seconds; the final registration checks took 20 seconds on Windows and
7 seconds on Linux.

A separate original 8192 x 8192 RGB8 fixture passed on both verified debug
binaries. Independent checks covered every native channel, block framing/hash,
manifest identity, merged-cache hash and unchanged source. Its encoded file is
1,287,936 bytes and its editable document is 279,205 bytes. Both platforms produce
manifest `670106bcf3b068a9a911088fe63a3ba704dd34c7972b3c27f33ed562f2bb0b38`.

| Single debug import | Windows | Linux |
| --- | ---: | ---: |
| CLI lifetime | 8.36 s | 7.53 s |
| Peak process commit | 12.27 MiB | Unavailable |
| Peak resident/working set | 27.97 MiB | 55.88 MiB |

These are one-fixture diagnostics, not a repeated performance gate. Fixture
generation and independent checks are excluded from CLI time; desktop activity
is uncontrolled and OS caches may be warm. Linux uses the isolated RSS
supervisor, which does not establish commit-budget acceptance.

Evidence is retained externally under `layered-native-acceptance-02`, alongside
`layered-native-windows-target-02` and `layered-native-linux-target-01`. The audit
SHA-256 is `6575d7c62187859e22f9d6b71ef307cf53a5a857ee59448a300913cba5ca818f`.
The full-run source fingerprint is
`2c10c3855d55ce70dee4d4bf311bda64e5a64c3f7e47fe655b985abd515a9ce4`;
the focused repair and target checks bind
`4dde68e0263bc18cf486a79599bff65104d8d90be69f67356c703de7082ff97b`.
Subsequent publication edits are confined to Markdown and recorded separately.
The original checkpoint count remains 163/167; complete W4 and extended layered
interchange remain open.
