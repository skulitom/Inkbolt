# Focused previews and contact sheets

`document.preview` returns one PNG, exact document identity and explicit coordinate maps without changing a document or writing a file. It accepts inline snapshots, pinned saved revisions and hashed snapshot files through the shared JSON interface. Use the core MCP tool or JSON CLI; Rust callers use `previews::preview`. Ordinary resource roots and cancellation controls apply.

```json
{"command":"document.preview","document":{"session_id":"poster","revision":3},"options":{"focus":{"type":"items","ids":["title","badge"],"margin":8},"scale":2}}
```

The example uses an existing workspace session; provide the reference's explicit `session_root` outside a workspace. `options` defaults to canvas focus, scale 1 and ordinary render-quality defaults. `render_options` supports the existing antialiasing, averaging, padding, canvas crop and HDR view contract. Scale remains an integer from 1 through 4. MCP `response_format:"preview"` sends the PNG once with recoverable metadata; see [preview transport](AGENT_INSPECTION.md).

## Focus and composition

| Focus | Inputs | Meaning |
| --- | --- | --- |
| `canvas` | None | Complete ordinary rendered canvas, including explicit uncropped render padding |
| `region` | `bounds:[min_x,min_y,max_x,max_y]` | Document-world rectangle cropped from the complete composition |
| `items` | Nonempty unique `ids`, optional nonnegative `margin` | Union of selected unclipped world geometry, expanded by the margin; text uses its frame |
| `artboard` | `id`, optional `include_bleed` | Existing standalone artboard export, including owned content in local coordinates |

Item focus includes hidden items in its geometric bounds and excludes strokes/effects. Margin is explicit; no heuristic claims to find every painted pixel. Other artwork within the region stays visible. Bounds must be finite, within document coordinate limits, and have positive area. Empty geometric selections return `EMPTY_PREVIEW`; add a margin for a zero-height/width path or supply a region. A region with no rendered intersection returns `FOCUS_OUTSIDE_CANVAS`. Unknown/duplicate IDs and unsupported semantics fail explicitly.

Region and item views crop completed full-scene pixels outward to the original output grid, then clip to the rendered extent. This preserves filters, backgrounds, masks and canvas-relative operators. Full render pixel/work limits and evaluation cost still apply; a tiny crop does not enable an otherwise oversized render. The PNG uses the existing RGBA8 view, source-depth/ink losses, output-profile conversion and exact embedded ICC profile. Source precision and editable controls remain intact.

Artboard views use the existing standalone export contract: owned subtree only, excluding placement and all ancestor appearance, while retaining the artboard's own appearance. Asymmetric bleed, fractional logical sizes, masks and retained content share the ordinary exporter. Ancestor transforms still participate in the map back to document-world coordinates. Artboard export now carries the active cancellation context into preparation loops and rendering.

## Reading coordinates and identity

Every result contains `document_id`, `revision`, a SHA-256 of the canonical typed document, `focus`, `composition`, `artifact`, `source_changed:false`, and:

- `requested_bounds`, `actual_bounds` and `bounds_space` (`document` or `artboard_local`). Actual bounds describe output pixel edges after outward rounding and clipping; fractional logical edges may have partial coverage in the last pixel.
- `crop_pixels:[left,top,right,bottom]`, end-exclusive in the full rendered view, and `clipped_to_render` indicating clipping of the outward-rounded rectangle.
- `mapping.world_to_pixel`, `mapping.pixel_to_world` and the four ordered `world_corners` (top-left, top-right, bottom-right, bottom-left).
- `full_render`, describing original evaluation/output dimensions, quality, origin and color view. Its dimensions can exceed the focused PNG dimensions; it is not the crop's receipt.

Matrices use `[a,b,c,d,e,f]`, mapping `(x,y)` to `(a*x+c*y+e,b*x+d*y+f)`. Pixel coordinates describe edges; pixel `(x,y)` is sampled at center `(x+0.5,y+0.5)`. A rotated artboard needs the full matrix, not an axis-aligned translation. Coordinates and identities belong to this exact document revision/content; re-inspect after a topology or placement change. External resources are content-checked when read by rendering, under ordinary resource rules.

Both map directions evaluate scale, origin and placement as complete ordered
expressions, including the inverse or reciprocal scale before final coefficient
rounding. Unstable expressions use exact rational arithmetic over their binary64
inputs. This prevents cancellation from an independently rounded inverse; final
corner/point arithmetic and pixel sampling remain separate. See the
[coordinate precision contract](COORDINATE_PRECISION.md) and independent rational
mapping fixtures in `tests/test_coordinate_conversions_cli.py`.

For a proposed edit, request `include_document:true` from [session dry run](SESSION_PROPOSALS.md), preview its returned `proposed_document`, and commit the unchanged action/ticket through `session.apply_proposal`. The proposed document is not a saved revision reference until commit succeeds. Tests compare its preview to the eventual saved revision and prove the old saved view remains unchanged.

## Contact sheets

`document.contact_sheet` combines 1–16 explicit preview options for one document. It is available through the dispatcher, CLI and `contact_sheets::sheet`. Each view has the same focus/scale/render options described above.

```json
{"command":"document.contact_sheet","document":{"session_id":"poster","revision":3},"options":{"views":[{"focus":{"type":"canvas"}},{"focus":{"type":"items","ids":["title"],"margin":4}},{"focus":{"type":"artboard","id":"square","include_bleed":true}}],"columns":3,"cell_size":[256,256],"gap":8}}
```

The sheet uses row-major cells, transparent gaps and centered thumbnails with no enlargement. Columns default to 4 (1–8), cell axes to 256 (1–512), and gap to 8 (0–64). Unused final cells remain transparent. Thumbnail dimensions preserve aspect ratio up to integer rounding. Sampling selects the nearest source pixel at each thumbnail center; thin details can disappear. Use the full-resolution focused preview to judge fine edges or output fidelity. The sheet is a 96-ppi review image, with every tile retaining the one document's output color profile. No mixed-profile reinterpretation or second color conversion occurs.

`views` records every index, cell rectangle, actual image rectangle, source preview metadata, PNG source hash, and `world_to_sheet`/`sheet_to_world` maps. These matrices map continuous image edges; the pixel sample itself is discrete. Original per-view PNG payloads are omitted; the result carries one sheet PNG. Profile/loss metadata and source identities remain available per view. There are no text labels or font dependencies; indexes follow supplied order.

Before rendering, aggregate evaluation (including padding/supersampling) and final-sheet output are each limited to 4,194,304 pixels. Every individual render retains its original pixel/work budgets. Views execute sequentially and release temporary source pixels between tiles; no incremental-render/cache or measured-memory guarantee is claimed. Any error or cancellation returns no partial sheet and publishes no file.

`tests/test_focused_previews.py` independently checks sampled colors, coordinate equations, fractional coverage, composition crop parity, rotated/artboard maps, ICC bytes, transparency, sheet placement, admission limits, saved/proposed revisions, source-file identity and MCP reconstruction. Rust checks reject nonfinite typed options. [Document checks and export preflight](DOCUMENT_CHECKS.md) and [visual revision comparisons](VISUAL_COMPARISONS.md) extend this review workflow. Scale, actual-model benchmarks and the complete gate audit remain separate.
