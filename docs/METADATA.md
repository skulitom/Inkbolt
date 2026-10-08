# Descriptions, privacy and reproducible provenance

Documents and items can carry an optional `metadata` record with `title`, `description`, `author`, `rights`, `note`, ordered unique `tags`, a string-valued `properties` map and a string-valued `private` map. All values are caller-authored. Runtime resource paths, account names, clock values and source filenames are never discovered or inserted into these records.

Use `{"op":"metadata","value":{...}}` for the document, or add `"id":"item-id"` for an item. The operation replaces that record atomically; `value:null` clears it. Item locks and ancestor locks apply. Notes do not affect pixels, geometry or color. Inspect/select/query, structural diffs, duplication, cross-document transfer and durable history retain the records. Transferred items keep their own records while destination document metadata stays authoritative.

Each string permits up to 8192 UTF-8 bytes; tags permit 128 bytes and must be nonempty and unique. Records allow 64 tags and 64 entries in each map. Property keys use the portable ID syntax. Unsupported control characters fail. Serialized records have a 16 KiB limit and all document/item records together have a 64 KiB limit. Existing snapshot and request limits also apply.

## Export policy

`document.export`, `artboard.export` and publication `output` accept:

```json
"metadata_policy": {"mode":"public", "manifest":true, "provenance":true}
```

`mode` is `public` (default) or `strip`. Both exclude every `private` map. `public` retains the other descriptive fields; `strip` removes them. `manifest` and `provenance` default to false and can be requested independently of descriptions. Ordinary image/SVG delivery defaults to public descriptions. Empty public records produce no envelope unless one of those optional reports is requested.

Snapshot exports without a policy preserve complete source records, including private working notes. Explicit `public` or `strip` creates a sanitized snapshot copy without changing the source document. Its optional metadata envelope is returned separately in the artifact and publication receipt. Sessions always retain the source records for undo/recovery.

The privacy scope is descriptive records. Artwork text, item names, document geometry and supplied ICC profile contents retain their existing semantics. A caller should place private working paths in the `private` map. Explicitly placing a path in a public description makes it public. The policy does not attempt to recognize secrets inside arbitrary artwork or third-party profile bytes. Resource manifests contain IDs, dimensions, byte counts, image/font SHA-256 and font-license SHA-256; they contain no runtime paths. They inventory all resources in the export view and do not claim to verify files independently of ordinary resource resolution.

Provenance contains the engine version, source revision and SHA-256 of the export view after applying the metadata policy, serialized as sorted-key compact JSON. Arrays retain order and Rust's JSON number representation remains part of the contract. No time, output path or resource-store path participates. An artboard hashes its standalone export view. Changing private records alone at the same revision cannot change public output. A new revision or engine version intentionally changes provenance. These hashes support reproducibility; they are not signatures or proof of authorship.

## File representation and import

A bounded, original `inkbolt.metadata.v1` JSON envelope carries public document/item records, delivery interpretation and optional manifest/provenance. Non-ASCII characters use JSON UTF-16 escapes so the same exact packet is valid in each carrier. The packet is limited to 256 KiB.

| Format | Carrier |
| --- | --- |
| PNG | Uncompressed iTXt, keyword `Inkbolt Metadata`, empty language/translated-keyword fields |
| JPEG | COM segments before the first scan, `INKBOLT-META` plus NUL, big-endian 16-bit one-based part/count, at most 60000 JSON bytes per part |
| TIFF | ASCII ImageDescription, `Inkbolt metadata v1` plus newline followed by JSON |
| SVG | One root metadata element containing an `inkbolt` element in `urn:inkbolt:metadata:1`, with XML-escaped JSON text |
| Snapshot | Original typed records; optional sanitized copy and separate delivery envelope |

`asset.import` recovers recognized PNG/JPEG/TIFF envelopes into a separate `metadata` receipt. Metadata never participates in normalized pixel identity and never creates resource bindings. The receipt explicitly marks imported descriptions/provenance as untrusted. Source-byte hashes still cover the complete original file. Bad recognized JSON/records, duplicate packets, private records in delivery envelopes and missing/duplicate/inconsistent JPEG parts fail before any asset publication. JPEG parts can be reordered. Only the declared uncompressed PNG and pre-scan JPEG envelope forms are recognized; general XMP/EXIF/IPTC editing and additional image formats remain separate interoperability work.

SVG import preserves recognized public document records and maps item records through source IDs. Unmapped item descriptions produce an explicit loss. Manifests/provenance are not promoted into trusted resources or document identity. Unknown, nested or malformed metadata structures fail explicitly. SVG's existing geometry, text and source-size bounds still apply.

## Orientation, density and color

Delivery pixels use top-left orientation. TIFF explicitly writes Orientation 1; PNG/JPEG carry the corresponding already oriented pixel order without an additional rotation tag. Unsupported oriented input remains an explicit import failure. Source orientation is never blindly copied onto normalized pixels. Automatic EXIF rotation remains separate image-interchange work.

Resolution comes from the document's declared ppi times export scale, with PNG integer pixels/metre, JPEG whole ppi and TIFF 0.001 ppi rounding. Source image density does not resize placement. The envelope reports the actual format-rounded density and exported dimensions. Color follows the existing explicit working-sRGB and output-profile contracts. Descriptive stripping preserves required color/density interpretation, exact ICC bytes and encoded image samples. Removing a profile requires the ordinary explicit `output_profile` edit; descriptive stripping never silently changes color.

All exports preserve source documents and inputs. Publication is create-only and includes the applied policy and envelope hash in its receipt. Use the Rust `publish::export*` functions for the full delivery contract; `render::*` exposes lower-level pixel/render primitives.

## Evidence

`tests/test_metadata_cli.py` independently parses PNG chunks, JPEG comments, TIFF tags and XML; compares exact descriptions and codec bytes; verifies canonical hashes, private-path omission, source preservation, resource/license identities, color/density/orientation, malformed envelopes, Unicode, limits, locks, transfer, artboards and MCP durable history. The original [metadata workflow](../examples/metadata_workflow.py) produces public and stripped deliveries with preserved masters. External decoder checks and generated files remain in private verification storage.

Carriers follow the public [PNG textual-data specification](https://www.w3.org/TR/png-3/#11textinfo), [JPEG marker specification](https://www.w3.org/Graphics/JPEG/itu-t81.pdf), and [TIFF tag definitions](https://www.loc.gov/preservation/digital/formats/content/tiff_tags.shtml). Envelope design, privacy policy, fixture data and integration are original; no new dependency is required.

PDF applies the same public/strip policies to each selected page before outlining, embedding an ordered `inkbolt.pdf.metadata.v1` packet in RDF/XML. Unselected item descriptions are excluded. Resource manifests retain the all-resources-in-export-view contract. See [PDF.md](PDF.md).
