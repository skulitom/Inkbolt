# Dependencies and provenance

The Windows `job_process` backend adds no package or copied SDK source. Original bindings use documented Windows job-object, process-time and memory APIs linked in [JOB_PROCESSES.md](JOB_PROCESSES.md). Persistent leases use the standard Rust file locking API available since Rust 1.89. Runtime dependencies, locked versions and licenses are unchanged.

Durable output receipts add no external package. An original Windows binding calls the documented GetFileInformationByHandleEx/FileIdInfo interface to identify retained staging links; SQLite uses the existing pinned rusqlite dependency. No SDK source is included. See [publication receipts](PUBLICATION_RECEIPTS.md) for public interface references and verified platform limits.

Combined prepress adds no external package. The existing pinned moxcms 0.9.1 `options` feature enables high-precision CMYK interpolation weights; LUT and extended-range features remain enabled. All 83 external versions, sources and licenses are unchanged. Original gamut evaluation reads public ICC encodings; it does not copy a color-engine evaluator. Private verification uses the existing external LittleCMS 2.12 C API with original floating-point table/curve fixtures, plus separately pinned PDF readers. These tools and generated profiles remain external and are not shipped.

Original engine code is MIT licensed. The material checker is adapted from original Cutbolt tooling; LICENSE retains its notice. No engine code or audit output from external applications is incorporated.

Cargo.lock records exact versions and checksums. Packages remain in Cargo's external cache; do not vendor them. Direct dependencies:

| Package | Purpose | License |
| --- | --- | --- |
| serde | Typed JSON contracts | MIT OR Apache-2.0 |
| serde_json with float_roundtrip | JSON transport with correctly rounded f64 input parsing | MIT OR Apache-2.0 |
| schemars | Request JSON Schema | MIT |
| tiny-skia 0.12.0 | CPU coverage rasterizer; std only, without SIMD or bundled PNG feature | BSD-3-Clause |
| png 0.18.1 | Bounded PNG decoding and tagged RGBA8 encoding | MIT OR Apache-2.0 |
| jpeg-decoder 0.3.2 | Scalar 8-bit grayscale/RGB JPEG decoding | MIT OR Apache-2.0 |
| jpeg-encoder 0.7.1 | JPEG encoding with explicit quality, chroma and matte policy | (MIT OR Apache-2.0) AND IJG |
| tiff 0.11.3 | Bounded TIFF strips/tiles, sample decoding and lossless encoding | MIT |
| base64 0.22.1 | Binary export envelope | MIT OR Apache-2.0 |
| sha2 0.10.9 | Image/font content and source-byte identities | MIT OR Apache-2.0 |
| crc32fast 1.5.2 | Validate every input PNG chunk checksum | MIT OR Apache-2.0 |
| rustybuzz 0.20.1 | Pinned-font run shaping and ttf-parser 0.25.1 outline access | MIT |
| unicode-segmentation 1.12.0 | Grapheme boundaries for text edits and wrapping | MIT OR Apache-2.0 |
| unicode-script 0.5.8 | Unicode script and script-extension itemization | MIT OR Apache-2.0 |
| unicode-bidi 0.3.18 | Unicode 16 paragraph levels and line reordering | MIT OR Apache-2.0 |
| roxmltree 0.21.1 | Bounded read-only XML parsing for original SVG import mapping | MIT OR Apache-2.0 |
| rusqlite 0.40.2 | Local transactional sessions; bundled SQLite through libsqlite3-sys 0.38.2 | MIT (SQLite public domain) |

Rust/Cargo, Python 3.11+ and Git are development tools. Python checks use only the standard library. Ghidra, Java and Anode are optional external research tools; exact local installations and verification receipts belong in the private research root. They are not runtime dependencies.

The coverage backend provides a bounded low-level path renderer; the project owns document semantics, editing, geometry inspection and compositing. Scalar coverage keeps this first implementation simple and reproducible within the tested environment. Its f32 geometry and RGBA8 coverage do not establish high-depth or extreme-scale fidelity. PNG encoding is independent of scene geometry; tests decode its chunks and filters using a separate standard-library implementation.

References: [tiny-skia 0.12.0 API](https://docs.rs/tiny-skia/0.12.0/tiny_skia/), [PNG encoder API](https://docs.rs/png/0.18.1/png/), [W3C compositing equations](https://www.w3.org/TR/compositing-1/), [SVG geometry](https://www.w3.org/TR/SVG2/paths.html). Only public interfaces and original algorithms/fixtures inform project code.

Hierarchy rendering also uses the public [group compositing model](https://www.w3.org/TR/compositing-1/#groupcompositing) and [SVG clipping model](https://www.w3.org/TR/css-masking-1/#the-clippath-element). Project-owned scene/edit/layout code defines stable identity, coordinate conversion and failure behavior. Independent tests parse exported clipping geometry and compare its coverage with decoded pixels.

The complete resolved graph and original license texts are retained in [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md), including transitive and build dependencies. Review notices and platform-specific distribution obligations before a release. A bounded PNG asset importer is implemented; bounded editable SVG import uses roxmltree XML parsing; SQLite supplies session persistence.

Gradient semantics use the public [SVG paint-server specification](https://www.w3.org/TR/SVG2/pservers.html), including separate color/opacity interpolation, repeated stops and user-space transforms. Linear RGB follows the [sRGB transfer function](https://www.w3.org/TR/css-color-4/#predefined-sRGB). No specification sample code is copied. The bounded freeform field, inline repeat sampler and ordered quantization policy are original project contracts documented in AGENT_INTERFACE.md. This slice adds no dependencies.

Image import follows the public [PNG specification](https://www.w3.org/TR/png-3/) through [png 0.18.1 decoding APIs](https://docs.rs/png/0.18.1/png/struct.Decoder.html), with original framing/limits/metadata policy and independent generated PNG tests. [sha2 0.10.9](https://docs.rs/sha2/0.10.9/sha2/) supplies SHA-256; no cryptographic primitive is reimplemented. The original store protocol publishes create-only hard links, preserving original inputs and existing cache bytes. SVG image sampling is a [consumer hint](https://www.w3.org/TR/css-images-3/#the-image-rendering); exact engine resampling is verified through PNG. No third-party image assets or implementation code are copied into fixtures.

Text uses the public [rustybuzz API](https://docs.rs/rustybuzz/0.20.1/rustybuzz/), [ttf-parser API](https://docs.rs/ttf-parser/0.25.1/ttf_parser/) and [grapheme segmentation API](https://docs.rs/unicode-segmentation/1.12.0/unicode_segmentation/). The original synthetic font generator follows public OpenType [glyph](https://learn.microsoft.com/en-us/typography/opentype/spec/glyf), [character mapping](https://learn.microsoft.com/en-us/typography/opentype/spec/cmap) and [font header](https://learn.microsoft.com/en-us/typography/opentype/spec/head) tables. Its rectangles, quadratic curves and metrics are original test data. External fonts are never bundled; users supply permitted local fonts with retained licenses. The diagram example was also exercised privately with OFL-licensed Noto Sans at its default instance. Shaping availability in a dependency does not imply complete product typography support.

The float_roundtrip feature preserves the correctly rounded binary value of JSON f64 inputs. An independent Python check compares exact float representations before editing, after CLI transport and after snapshot replay, including a value that exposed rounding drift in the implementation report. No extra crate is required.

Sessions use the public [rusqlite connection API](https://docs.rs/rusqlite/0.40.2/rusqlite/struct.Connection.html), [SQLite atomic commit design](https://sqlite.org/atomiccommit.html), [locking contract](https://sqlite.org/lockingv3.html) and [synchronous setting](https://sqlite.org/pragma.html#pragma_synchronous). Inkbolt owns schema, immutable-state semantics, bounded history, idempotence and recovery contracts. The bundled feature compiles the pinned public SQLite amalgamation from the external Cargo cache; no dependency source is copied into this repository. Nine additional runtime/build packages are locked with their complete supplied notices. Local Rust builds now require a C compiler supported by the cc build dependency.

Checked session backups enable the existing pinned rusqlite 0.40.2 `backup` feature, using its public stepped backup interface. No package, lockfile version or license changes. Source snapshot selection, validation, identities, cancellation, recovery and create-only publication are original engine logic; the dependency remains external.

Semantic comparisons, create-only export publication and MCP stdio add no Rust dependencies. The adapter is original code against the public protocol specification linked in AGENT_EXECUTION.md. MCP Inspector 2.9.0 is an external development-only compatibility check, run in CLI stdio mode. Its packages/licenses remain in the package cache and are not shipped with Inkbolt.

Curve simplification uses [num-rational 0.4.2](https://docs.rs/num-rational/0.4.2/num_rational/type.BigRational.html) and num-traits 0.2.19, resolved with num-bigint 0.4.8, num-integer 0.1.47 and build helper autocfg 1.5.1. All use MIT/Apache-2.0 licensing, remain in the external Cargo cache and are locked with checksums. Only arithmetic is supplied by these libraries; fitting, exact certificate construction, topology policy and fixtures are original Inkbolt code. The curve-simplification milestone had 69 external packages; editable SVG import adds roxmltree 0.21.1, bringing the complete graph to 70 external packages. Their distributed licenses are retained in THIRD_PARTY_NOTICES.md.

SVG import uses the public [roxmltree parser API](https://docs.rs/roxmltree/0.21.1/roxmltree/) with DTDs disabled, no entity resolver and an explicit node limit. Original number/path parsing, style resolution, geometry mapping and generated fixtures follow the public SVG specifications linked in SVG_IMPORT.md. This dependency remains in the external cache; both supplied licenses are retained in THIRD_PARTY_NOTICES.md. No XML/parser implementation is copied.

Stroke evaluation now uses original f64 subdivision, dash/profile cuts, cap/join ribbons, endpoint shapes and expansion. The existing tiny-skia 0.12.0 backend fills their shared nonzero outline; it no longer supplies stroke or dash geometry. Independent synthetic fixtures use periodic arithmetic, analytic curve lengths, rational polygon areas, segment-distance and corner-region predicates. No package, version, license or bundled asset was added.

JPEG/TIFF interchange uses the public [jpeg-decoder 0.3.2 API](https://docs.rs/jpeg-decoder/0.3.2/jpeg_decoder/struct.Decoder.html), [jpeg-encoder 0.7.1 API](https://docs.rs/jpeg-encoder/0.7.1/jpeg_encoder/struct.Encoder.html), [TIFF decoder API](https://docs.rs/tiff/0.11.3/tiff/decoder/struct.Decoder.html) and [TIFF encoder API](https://docs.rs/tiff/0.11.3/tiff/encoder/struct.TiffEncoder.html). Original Inkbolt code defines framing, metadata rejection, alpha/color policy, immutable identity and publication; these packages supply codecs. Default features are disabled: JPEG decoding is scalar/platform-independent, encoding uses std, and TIFF enables only Deflate and LZW beyond its base codecs. Ten new resolved packages bring the external graph to 80; all prior versions remain unchanged. All 21 distributed license/notice files from the additions are retained in THIRD_PARTY_NOTICES.md, including IJG terms. This software is based in part on the work of the Independent JPEG Group.

Private independent image verification uses externally installed Pillow 10.3.0 and tifffile 2023.4.12 with NumPy 1.26.4, without shipping those tools or generated assets. The normal Python suite still uses only the standard library, original TIFF fixtures and its independent PNG parser. Separate readers/writers verify JPEG errors and TIFF variants beyond self-roundtrips. Installed tifffile/imagecodecs could not decode Deflate even from its own writer; the independent Deflate checks use Pillow/libtiff and original strip parsing with Python zlib instead. See IMAGE_IO.md for the exact fidelity contract.

RGB ICC conversion uses external [moxcms 0.9.1 public APIs](https://docs.rs/moxcms/0.9.1/moxcms/struct.ColorProfile.html) and pxfm 0.1.30 arithmetic. Default features are disabled; LUT and extended-range support are enabled, preserving scalar paths. Both are BSD-3-Clause OR Apache-2.0 licensed and remain in the external Cargo cache. Their full supplied license texts are retained in THIRD_PARTY_NOTICES.md. The graph now contains 83 external packages; all prior versions remain unchanged. Original framing, color policies, profile association, normalized identity, metadata embedding, examples and synthetic fixtures belong to Inkbolt. ICC framing follows the public [ICC specification](https://www.color.org/icc_specs2.xalter); no implementation or profile fixture is copied. Independent private comparison uses external LittleCMS 2.16 through Pillow 10.3.0. See COLOR_PROFILES.md for finite table precision, worker-stack bounds and fixture tolerances.

Descriptive metadata adds no dependency. Original envelope framing uses existing JSON, SHA-256, PNG CRC and TIFF APIs, following public PNG iTXt, JPEG COM and TIFF ImageDescription carrier rules. The locked graph remains 82 external packages with unchanged versions, sources and licenses. Independent private verification uses external Pillow plus separate container/XML parsing. See METADATA.md.

Color meshes add no dependency: original shared-knot interpolation, derivative bounds, inversion and sampling use Rust arithmetic plus the existing PNG encoder. The locked graph remains 82 external packages with unchanged versions and licenses. Private compatibility checks use the externally bundled Sharp 0.35.4/libvips 8.18.6/librsvg 2.62.91 and Pillow 10.3.0; these development tools, their packages and generated delivery fixtures are not shipped. Public SVG pattern/image carrier rules are described by the [SVG specification](https://www.w3.org/TR/SVG11/pservers.html#PatternElement).

Text on paths adds no dependency. Original bounded line/cubic distance tables and glyph placement reuse the existing Rustybuzz/ttf-parser interfaces, primitive expansion, JSON and rendering backend. Independent adaptive Simpson integration, original geometric-font outlines, SVG reimport and external SVG/image consumers verify placement and delivery. The locked graph remains 82 external packages with unchanged versions, sources, licenses and notices.

Image tracing adds no dependency. Original integer classification, connected-region processing and directed grid contours reuse existing validated image assets, SHA-256 identities, ordinary vector geometry, sessions and exports. All external packages and retained licenses remain unchanged.

Pixel brushes add no dependency. Coverage integrals, path sampling, premultiplied transport and reservoir mixing are original; the existing external SHA-256 library supplies seeded digest words and content identities. Independent Python vertical-slice integrals and Pillow delivery decoding remain development verification only. Existing versions and licenses are unchanged.

Region retouching adds no dependency. Original affine source sampling, grid topology, sparse preconditioned healing and boundary measurements reuse existing JSON and SHA-256. Independent dense pivoted elimination and external Pillow decoding verify numerical and image delivery behavior. Existing external versions, sources and licenses are unchanged.

Content-sensitive repair adds no dependency. Exhaustive donor search, progressive frozen-patch synthesis, guided weighted medians and quality measurements are original Rust code; patch blending reuses the verified retouch solver. Independent Python numerical fixtures and external Pillow/Inspector checks remain development verification only. Locked external packages and licenses are unchanged.

Structured vector brushes add no dependency. Original rigid motif placement and affine geometry reuse the existing stroke evaluator, primitive conversion, nonzero rendering and session machinery. Independent Python geometry/coverage references and the externally installed Pillow and Sharp/librsvg consumers verify delivery. No package versions, sources, licenses or notices change.

Mixed-direction paragraphs add only external unicode-bidi 0.3.18 (MIT OR Apache-2.0), pinned with its default std/Unicode-data features. All 82 previous package versions, sources and licenses remain unchanged; the graph contains 83 external packages. Both supplied license files are retained in THIRD_PARTY_NOTICES.md. Inkbolt owns original paragraph/line integration, logical-index inspection, script/style/font itemization and synthetic glyph fixtures. Complete official Unicode 16 bidi tests remain external private development evidence; no conformance data or dependency implementation is vendored. See [BIDI_TEXT.md](BIDI_TEXT.md).

PDF delivery adds no dependency. Inkbolt owns the original bounded object/stream/xref writer and scene integration, based on public ISO format semantics. The locked graph remains 83 external packages with unchanged versions, sources, licenses and notices. Existing external pypdf and Poppler consumers are used only for private verification and are not shipped.

Source-profile editing uses the existing pinned moxcms extended-range feature for floating matrix/TRC transforms. It adds no package; see [SAMPLE_PROFILES.md](SAMPLE_PROFILES.md) for explicit intent selection and source preservation.
