# Source profile assignment and conversion

Agents can preserve an image's native values while changing its interpretation,
or explicitly convert those values to another RGB profile. `sample_profile`
works on retained normalized `samples` grids and promotes inline RGBA8 content
without changing its pixel bytes. It uses the existing library, JSON CLI and
MCP edit/session paths. Original caller snapshots and durable history retain the
source state; input files are never modified.

```json
{"op":"sample_profile","id":"pixels","action":{"type":"assign","profile":{"type":"builtin","name":"linear_srgb"}}}
```

Assignment changes only the source profile and encoding declaration. It retains
dimensions, depth, channels, sample bytes, alpha, hidden colour and appearance
controls. The new interpretation can change visible colour. A tagged grid uses
`encoding:"profiled_rgb"` and a `profile` field containing the existing builtin
or exact base64 ICC profile value. The two fields must occur together.

```json
{"op":"sample_profile","id":"pixels","action":{"type":"convert","profile":{"type":"builtin","name":"display_p3"},"intent":"relative_colorimetric"}}
```

Conversion transforms native straight RGB, clips to the normalized destination
range, and quantizes once at the retained u8/u16/f32 depth. Alpha remains exact,
including subnormal float alpha and zero-alpha hidden colour. A grayscale grid
represents the profile's R=G=B input axis; a nonidentity conversion promotes it
to RGBA so chromatic results are retained. An identical profile is an exact
identity, with no approximate connection-space round trip.

`profile:null` explicitly denotes the existing encoded-sRGB source convention.
Assigning null reinterprets unchanged values; converting to null rewrites values
into working sRGB and clears the profile. It does not mean an unknown external
colour space. Untagged external files still require the existing explicit import
policy. Neither action guesses a profile from pixel values.

## Intent and numerical policy

All four intent names are accepted: `relative_colorimetric` (default),
`absolute_colorimetric`, `perceptual` and `saturation`. The selected source A2B
and destination B2A tables are used independently; a missing requested table uses
the profile's default table when present. Matrix/TRC profiles use their shared
characterization. An unavailable directional transform fails explicitly.

Inkbolt applies no additional black-point mapping. Perceptual and saturation
colour rendering follows the selected profile tables, with the documented
matrix fallback. Their rendering is profile dependent; the ICC specification
does not prescribe a universal perceptual or saturation algorithm.
[ICC.1:2022, sections 6.2 and 6.3](https://archive.color.org/specification/ICC.1-2022-05.pdf).

Absolute conversion uses the colorimetric tables and multiplies connection-space
XYZ by source media white divided by destination media white, component by
component. Matrix sources apply this scale directly to their PCS matrix, retaining
negative adapted XYZ components. Table sources with unequal whites use an internal
linear matrix profile expressing XYZ/2 between two transforms. That intermediate
must remain finite in [0,1]; unsupported range fails without committing an edit.
Both media white points must have finite positive components. This implements
the relative/absolute scaling equations in
[ICC.1:2022, section 6.3.2.2](https://archive.color.org/specification/ICC.1-2022-05.pdf).

Profile table evaluation is supplied by the pinned external moxcms version.
The `extended_range` feature preserves signed matrix results at the explicitly
linear working boundary. Normalized source curves are evaluated first using the
bounded table path, followed by an identity-curve matrix stage. Nonlinear
destinations clip before inverse transfer evaluation. Legacy image-boundary
conversion keeps its prior options. Tables retain finite interpolation precision. Supplied
ICC bytes are never rewritten by intent selection or internal transform setup.
No extra dependency package, network service, GPU or model is required.

Version 0.73 corrects generated builtin display profiles to declare D50 media
white and a Bradford D65-to-D50 adaptation matrix, as required by ICC v4.
Their transfer curves and colourant matrices are unchanged. Builtin ICC byte
hashes therefore change; supplied ICC bytes remain exact. To pin a particular
definition across engine versions, retain its exported bytes as an `icc` profile.
[ICC.1:2022, sections 6.2.3 and 9.2.15](https://archive.color.org/specification/ICC.1-2022-05.pdf).

Receipts include source/destination ICC hashes, before/after sample hashes,
source/destination channels, observed destination-range clipping, colour
quantization count/error, intent and preservation policy. The clipping count
does not replace full gamut analysis: a profile's own tables may already map
or clip colours. General gamut diagnostics retain their separate checkpoint.

## Rendering and downstream edits

Source profiles are interpreted before reconstruction, compositing and item
effects. Encoded documents convert to normalized working sRGB. Linear documents
convert to linear sRGB before blending; floating matrix paths retain negative
and above-white colours. Source grids remain normalized native device values.
Existing HDR display views control their later projection. The view intent is
always relative colorimetric; an explicit conversion can bake a different intent.

Layer-local profiles allow differently tagged original images to share one
working document. This operation does not change the document's working-space
choice or its independent output-profile association. PNG/JPEG/TIFF delivery
still follows that output association; snapshots retain source profile bytes.
This is not native CMYK, Lab or grayscale ICC source support.

Native rectangle replacement writes values in the declared source encoding and
retains the profile. Before `sample_convert` depth/grayscale/HDR conversion or
local seeded selection, explicitly convert to `profile:null`. This prevents an
implicit profile discard. Other existing native-edit support limits remain.
Profile assignment to signed HDR source grids is rejected; project them into a
normalized source representation explicitly first.

Per-profile framing limits remain 256 KiB and 128 tags. All retained ICC base64
strings together are limited to 512 KiB per document, including hidden items.
Source pixel budgets remain unchanged. Transforms use bounded 4096-pixel rows
and joined setup workers; control checks prevent committing timed-out edits.

## Evidence and example

Independent tests distinguish unchanged assignment bytes from converted values,
exercise all three depths and hidden alpha, and use 50-digit transfer equations,
exact rational matrix solves, distinct source/destination intent tables,
gamma/sampled/channel-specific curves and media-white scaling. Original Bradford
equations check generated white-point metadata. A wide-gamut cube proves signed linear values survive into
compositing. Snapshots, profile embedding, locks, malformed declarations,
resource limits and MCP undo/reopen share the same path.

Run `python examples/sample_profile_workflow.py --output NEW_DIRECTORY` to save
an original chart, a reassigned chart and a converted chart, with editable
snapshots, PNGs and receipts. Float or 16-bit sources are preferable when repeated
colour conversions must avoid coarse byte quantization.
