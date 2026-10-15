# Native block editing and migration

This is the W4.1 implementation contract under [FIX_PLAN.md](../FIX_PLAN.md).
The explicit versioned layer and document/session commit path are implemented
and passed fresh full Windows/Linux suites, including default-import adoption
and aggregate native-store capacity admission. Larger-workload acceptance remains
pending. New stored imports default to version 2. Explicit
`storage:{"storage_version":1}` selects [retained patches](NATIVE_SAMPLE_STORAGE.md),
with their existing 256-patch and 65,536 aggregate patched-pixel limits.
Explicit `sample_storage_migrate` converts
one stored layer to `storage_version:2`; this mode retains current block manifests
and has no lifetime patch count or aggregate edited-pixel cap.

```json
{"op":"sample_storage_migrate","id":"pixels"}
```

Use this operation in a normal `document.edit` batch or session edit action.
Migration of an already-version-2 layer returns `MIGRATION_NOT_NEEDED`.
Versions 1 and 2 are explicit; missing `storage_version` means version 1 and
serializes without the field. `patches` are permitted only in version 1.
Version 2 may carry a `staged` version-1 candidate transfer during pure review;
its manifest must equal `base`. Committed states omit `staged` entirely.

Prepared documents admit at most 64 MiB of aggregate pending block bytes,
including headers. This bounds current private work, not lifetime edits or the
resource store. Unchanged blocks share immutable buffers. Durable manifest
snapshots retain the existing resource-profile byte budgets; pending bytes have
their separate budget. An explicitly requested review document must also fit a
conservative 16 MiB round-trip bound before its hexadecimal transport is built.
The same bound applies to snapshot export of a prepared document. Oversized
reviews can use the proposal and preview without `include_document`; committing
first produces a small manifest-only snapshot.
Existing region, input, source-pixel, history and rendering bounds still apply.

`edit::apply_with_resources` remains pure. Its returned document carries any
unpublished blocks and can render or round-trip them. The explicit Rust
`edit::commit_with_resources` boundary and CLI/MCP `document.edit` publish blocks
before returning a manifest-only document. Session preparation hashes the
manifest-only projection; dry runs retain staged blocks for rendering, while
commit publishes them before writing the state and original receipt. Session
creation also publishes incoming staged blocks before publishing its database.

## Required result

Each committed native layer should describe its current ordered immutable
128-by-128 blocks. Editing replaces only intersecting blocks. Repeated edits must
not accumulate an overlay log in that layer or impose a lifetime pixel budget.
Old states continue to reference their own immutable blocks. Per-operation work,
transient memory, request size, history size and store capacity remain separate
admission checks. No automatic deletion or history eviction is introduced.

The existing block and manifest version 1 byte formats remain unchanged. Native
channel bits, profiles, sampling and placement retain their exact meanings.
Document representation changes are separate from SQLite session storage versions
and from the existing document schema number.

## Migration and compatibility

The integrated implementation must introduce an explicit, versioned native-layer
storage mode. Absence means the existing retained-patch mode; serializing an old
document must not add a default field that changes historical fingerprints.
Unknown modes fail. Opening, reading, checking or replaying an old session never
implicitly migrates it.

Migration is an explicit revision-producing operation over selected native
layers. It verifies every old base dependency, including blocks hidden by
patches, applies the exact retained patches privately, then prepares the new
manifest. It must preserve every native sample and all interpretation metadata.
A failure preserves the source document and history. Undo returns the original
layer recipe; redo returns the migrated manifest. Existing state rows, request
fingerprints, receipts, snapshots and backups are never rewritten. A downgrade
is not implied by loading or undoing a newer representation.

This layer migration is not `session.migrate`, which retains its existing
[backup and lineage contract](SESSION_LINEAGE.md). Old session versions remain
supported without a database upgrade. Retrying a completed migration or edit
must return the original receipt before loading now-missing resource blocks.

New stored imports use version 2 after the explicit commit, preview and recovery
boundary passed full platform suites. `storage.storage_version` accepts 1 or 2;
other values reject before decoding or publication. Omitting `storage` still
selects inline samples. Old imports and caller-supplied legacy documents keep
their meanings; no accepted checkpoint or compatibility fixture is replaced.
Legacy import output and receipts retain their previous shape when version 1 is
selected explicitly. New version-2 import receipts declare `storage_version:2`.

## Prepare, review, publish, commit

1. Check revision, request identity, resource bindings and input budgets.
2. Prepare immutable candidates privately. Validate all operations and document
   constraints before publishing any candidate. Preserve source candidates.
3. Produce a durable document projection containing manifests and metadata, with
   no pending block payloads. A review proposal binds this exact projection and
   its original base state. Its preview must resolve pending blocks from private
   memory. A returned editable review document must carry the required pending
   bytes explicitly, never an unexplained reference to an unpublished file.
4. At commit, recheck proposal identity and publish every required immutable block
   into the document's saved, explicit resource root using create-only files.
   Workspace defaults must not silently replace a saved root.
5. Only after all blocks are available may the document/history/receipt
   transaction commit. The returned state hash names the durable projection,
   never a different preview encoding. Late cancellation preserves committed
   success. Replay does not repeat resource publication.

A pure library edit and session dry run must create no directories, files or
database rows. Publication failure or cancellation may leave complete
unreferenced cache blocks, as the existing store already permits; it cannot
publish a document or receipt pointing to incomplete blocks. Process termination
may also leave owned temporary files. Retries verify existing complete blocks
and preserve corrupt or foreign files. No orphan sweep, cross-filesystem atomic
transaction, power-loss guarantee or hostile-filesystem guarantee is claimed.

## Aggregate store admission

Publication serializes cooperating native writers through a persistent,
empty `.inkbolt-native.lock` file in the canonical store root. The operating
system releases its exclusive lock when the handle closes or the process dies;
the file itself is never removed or rewritten. When coordination is needed,
existing nonempty, non-file or symlink entries at that name fail without
replacement. Old stores acquire this
coordination file only when new native blocks need publication. Read, preview,
history replay and pure preparation do not acquire it.

The initial store budget is 16 GiB of native-file bytes and 65,536 root directory
entries. Byte accounting covers `*.native-tile` and `.inkbolt-native-*.tmp`,
including complete or partial orphan files. Other shared-root entries count
toward enumeration and entry admission, but their bytes are outside this native
publisher's budget. No directory links are traversed. Accounting is conservative
per directory entry, including hard-link aliases; it is not a filesystem free-space
or physical allocation measurement.

Under the lock, publication rechecks destinations, charges each missing identity
once, and reserves room for all missing blocks plus the largest current temporary
alias and one extra staging entry. This covers termination between linking the
final name and unlinking the owned temporary. If removing that temporary fails,
publication stops before another block is written; retry counts the retained
alias without deleting it. Existing identical blocks cost no
additional bytes. Entirely deduplicated publication verifies its dependencies and
returns without acquiring a lock or requiring spare capacity, even in an older
store already above the new limits. Growth in such a store fails explicitly.

The wait loop checks cancellation and deadlines between 5 ms sleeps, with a
30-second contention budget before returning `SAMPLE_STORE_BUSY`. Capacity failure returns
`RESOURCE_LIMIT` before new block writes. A failed first admission may leave the
empty coordination file or newly created root; existing files remain unchanged.
No orphan cleanup, historical-block deletion or automatic quota increase occurs.
The bound covers cooperating publishers from this implementation on trusted local
filesystems. Older binaries or unrelated writers do not participate in its lock.

The capacity checks change neither block bytes nor manifest, document, session
or receipt versions. Exact small-budget fixtures cover byte/entry boundaries,
deduplication, orphan stages, hard-link aliases and competing processes. Waiting
publishers are cancelled after observed lock contention; a terminated owner
releases the lock. A Windows reader that denies temporary-file deletion stops
further growth. Directory and Unix symlink fixtures preserve foreign entries.
Session tests check rejected edits leave history unchanged, successful retry,
and original receipt replay after blocks disappear. Fresh full-suite acceptance
passed on Windows and Linux. A separate public CLI check on both platforms
returned `SAMPLE_STORE_BUSY` after about 30 seconds, preserved the store/source,
then published the exact expected block after the lock was released. See the
[acceptance record](DEVELOPMENT_STATUS.md#w41-native-block-editing-and-store-admission).
The larger storage/scale milestone remains open.

## Candidate transfer primitive

`Candidate::transfer(max_pending_bytes, control)` returns a version-1 `Transfer`
containing the manifest and a strictly identity-sorted list of unique pending
blocks. Each block carries its lowercase SHA-256 and lowercase hexadecimal
canonical file bytes, including the typed header. Inherited published blocks
remain manifest references, resolved only by a later explicit resource root.
Profile and sampling metadata are still the enclosing document's responsibility.

`Transfer::prepare(max_pending_bytes, control)` validates the version, manifest,
references, ordering, exact block lengths and the aggregate caller-supplied byte
budget before decoding any block. It then checks each block's header, digest and
native sample range before accepting it. A repeated identity cannot stand for
different edge dimensions. Duplicate, extra, malformed and corrupt pending
blocks fail. Preparation does not open a resource store or write files; the
control may still check cancellation markers. Callers need `Candidate::verify`
to certify all external dependencies.

The budget counts unique decoded pending block bytes, including headers. It is
mandatory at both ends and has no implicit default. Hexadecimal transfer costs
two bytes per native byte, plus JSON framing; the caller must separately bound
input parsing, serialization and overall live memory. This format is a transport
for pure candidates, not the durable session representation. Normal in-process
preparation should retain shared immutable buffers instead of serializing them.
Transfer validation alone does not grant document admission; version, aggregate
pending-byte and document resource-profile checks apply separately.

The transfer primitive does not change existing manifests, legacy patch recipes,
publication receipts, resource-root handling or import limits. The remaining
storage-milestone acceptance follows the checks below.

## Storage-milestone acceptance

- Independent exact-byte oracles for every depth/channel/encoding combination,
  shortened edge blocks, repeated blocks, signed zero and subnormal float bits.
- More than 256 committed edits and more than 65,536 total edited pixels while
  each operation stays within its declared budget. Check outside pixels,
  deduplication and bounded current-state size, not only rendered similarity.
- Reopen every selected old state; verify undo, redo, named snapshots, backups,
  migration, proposal acceptance/refusal and original receipt replay.
- Fail and interrupt before/during block publication and before/after the
  document transaction. Check concurrent writers, stale proposals, corruption,
  missing dependencies and cancellation without rewriting old resources.
- Enforce aggregate native-store capacity across concurrent publishers, counting
  deduplicated new bytes and interrupted work without deleting historical blocks.
- Fresh Windows and Linux acceptance for the integrated boundary, including
  explicit platform skip accounting. Focused implementation checks remain within
  the normal 180-second feedback budget.

The explicit migration/commit increment passed all 256 fresh full-suite stages
on each platform; see [retained evidence](DEVELOPMENT_STATUS.md#w41-native-block-editing-and-store-admission).
Its document tests cover all six encoded-sRGB depth/channel layouts, exact
260-edit histories, continuation, backup recovery, pure review and publication
failures. Candidate-transfer tests separately cover every admitted encoding.
Profile/HDR document migration and default-import adoption also passed fresh
full suites on both platforms. Independent canonical block bytes check all
profiled depth/channel layouts, built-in/embedded profiles, signed zero,
subnormal and signed HDR values through review, commit and history. Default
imports survive 260 edits without the legacy cumulative caps. The B10 judge
checks both representations against the same independent samples and history.
Aggregate capacity admission across concurrent publishers also passed fresh full
platform suites, independently of per-document pending and transport budgets.
The full storage milestone and larger-workload memory target remain open.

Revise the design if those checks cannot preserve exact history or if measured
memory/state growth violates the declared budgets. W4.1 does not by itself meet
the accepted 50 MP RGBA16 / 512 MiB target. Streaming import/export, broader native
operators and the independent `scale-v2` workloads remain required under W4.
