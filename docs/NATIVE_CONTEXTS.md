# Retained source colour contexts in print preparation

Retained objects use their working artwork as an isolated source. A saved
`ink_recipe` remains nonprinting; a saved RGB output profile remains a later
image-delivery setting. Neither changes the retained source's working colours
or merges saved channel plates into its artwork. Source snapshots, recipes and
profile bytes remain unchanged. Native object receipts disclose these contexts
under `coverage_sources.source_context` when either is present.

The root native-preparation request still rejects separate channel recipes and
RGB output profiles. Choose the explicit recipe/combined delivery mode for those
plates, or supply an ordinary artwork document for native process/spot delivery.
Source RGB sample profiles are different: they describe sample values and continue
to control conversion before native composition.

## Explicit HDR object views

A retained linear object in an encoded parent requires an explicit object view:

```json
{"view":{"tone_map":"reinhard","exposure":-1}}
```

Native print preparation now supports both existing views, `clip` and `reinhard`.
The original linear renderer evaluates the source, including its supported
linear blends, exposure/gain grades, raw development, masks and nested objects.
It averages the source's associated linear samples before applying the requested
view. See [HDR.md](HDR.md) for the exact equations and supported linear contexts.

The resulting encoded RGB and alpha retain binary64 precision. Placement then
reconstructs associated encoded samples using the selected object sampling and
warp. The declared print profile converts reconstructed straight RGB into process
inks before composition in the parent. There is no intermediate byte image.
The source's signed samples remain editable and unchanged.

This is an explicitly selected display-view boundary. Any source colour visible
through that view becomes process colour; independent native spot channels do not
cross it. Ink bindings that enter a projected subtree fail with
`INVALID_INK_BINDING`. Ordinary retained native objects keep their independent
process/spot behaviour and can use [INK_BINDINGS.md](INK_BINDINGS.md).

Receipts identify the exact source snapshot, view, sampling, output dimensions,
projection/conversion order and lack of link refresh. Direct whole-document
linear native preparation still requires an explicit retained view; it never
guesses a tone map. Root recipes, HDR views and RGB delivery profiles are distinct
choices.

## Planning and control

The ordinary sample renderer and explicit print-view path share one prepared
source-tree implementation. It plans nested objects before surface evaluation,
charges raw development, reconstruction, masks, work and retained buffers, and
carries the active control into nested rendering and raw development. Aggregate
native object/profile bounds include projected children. Cancellation or failure
prevents publication of a partial file. Sources and linked files are never
implicitly refreshed.

`tests/test_native_contexts_cli.py` checks independent view/composition equations,
all five reconstruction methods, all retained warp families, nonprinting metadata,
source identity, explicit errors, resource bounds, PDF samples and agent history.
The registry remains the authority for complete-checkpoint verification.
