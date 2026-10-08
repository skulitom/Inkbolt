# Retained raw development

`raw.retain` embeds exact sensor bytes and a versioned recipe in `content.type:"raw"`. `raw_settings` changes development without replacing the original capture; rendering always starts from that capture. `raw_expand` explicitly replaces the layer with ordinary developed samples. Snapshots and undo preserve either representation. The basic `raw.develop` command continues to return an ordinary sample document as documented in [RAW.md](RAW.md).

## Agent workflow

`raw.retain` takes the same `source_path`, optional `expected_sha256`, `id`, `capture`, `settings` and `control` as basic development, plus optional `corrections`. Each correction is optional; omitted controls do nothing. Returned raw layers are named `raw`.

```json
{
  "op": "raw_settings",
  "id": "raw",
  "settings": {
    "exposure_stops": 0.5,
    "white_balance": {"type":"gains", "rgb":[1.2,1,0.9]},
    "output":"srgb16", "range":"clip", "resolution_ppi":300
  },
  "corrections": {
    "denoise": {"radius":2, "threshold":0.08, "amount":0.75},
    "lens": {
      "center":[31.5,23.5], "focal":[64,48],
      "radial":[0.25,-0.0625,0.015625],
      "tangential":[0.0078125,-0.00390625], "border":"transparent"
    },
    "detail": {"radius":1, "threshold":0.01, "amount":0.5}
  }
}
```

Submit this operation through the ordinary atomic `document.edit` or `session.apply` path with the expected revision. It replaces the complete settings/corrections record and respects locks. Capture calibration and original bytes remain unchanged. Restoring the prior settings recomputes the prior result, including after the external source file is removed. Sample painting and source-profile/depth conversion require explicit `raw_expand` first; undo restores raw editability.

Layer transforms, sampling, masks, opacity, blending, background roles, canvas scaling and ordinary source-preserving document transfer retain their normal semantics. Raw correction coordinates stay tied to the sensor before layer placement. Linear output requires a linear document; changing one layer's output preference does not silently change the document working space. Recipe `resolution_ppi` is a preference used when creating/reopening a document; changing it on an existing layer leaves scene resolution untouched. Use the canvas resolution operation for that scene property.

## Processing contract

The order is sensor normalization/demosaic, white balance, camera matrix, exposure, **denoise, lens correction, detail, explicit output projection**. Corrections use signed linear sRGB in binary64. The selected output precision is applied afterward. Existing rendering then applies layer and scene controls.

Noise reduction computes a local mean of neighbours whose maximum absolute RGB difference from the centre is at most `threshold`, then blends that mean with the original by `amount`. The centre participates; edges use available neighbours. This is an original deterministic range-gated mean, not a trained model or temporal denoiser. The threshold uses post-exposure linear channel units. A threshold of zero combines only exactly equal colours. Amount zero is identity.

Detail uses the alpha-weighted box mean of available neighbours. For each channel, if `abs(original-mean)>threshold`, it adds `amount*(original-mean)`. Alpha stays unchanged, transparent centres stay transparent, and signed/HDR overshoot persists until the explicit output policy. Radius is 1..4 sensor pixels, thresholds 0..16 linear units, denoise amount 0..1 and detail amount 0..4. These controls do not claim removal of every noise type or recovered optical detail.

## Lens correction

Calibration uses three radial coefficients and two tangential coefficients with explicit optical centre and focal lengths. This bounded model follows the public [calibration equations](https://docs.opencv.org/4.13.0/d9/d0c/group__calib3d.html). No external calibration implementation or profile database is included. Zero-based integer coordinates denote sensor sample centres. Normalize `(x-cx)/fx,(y-cy)/fy`, apply the declared polynomial distortion, then map back to sensor pixels. Each corrected output centre pulls from that original distorted location, using bilinear linear-light interpolation.

`clamp` extends edge samples. `transparent` treats outside neighbours as transparent, with premultiplied interpolation and unassociated output colour. It does not secretly zoom/crop the result. The centre must lie within the sample-centre rectangle and focal lengths are 1..32768 pixels. Radial coefficients are in [-1,1], tangential coefficients in [-0.25,0.25].

Let `R` be the maximum normalized radius over the output rectangle. A conservative normalized Jacobian perturbation bound is `3|k1|R²+5|k2|R⁴+7|k3|R⁶+8(|p1|+|p2|)R`. It must be below 0.95. This bounds the symmetric Jacobian away from a fold over the entire convex rectangle; it is not sparse-grid sampling. Calibrations outside this sufficient bound fail `UNSUPPORTED_LENS_MAP` even when some might be invertible. Rational distortion denominators, thin-prism terms, fisheye models, automatic calibration, chromatic aberration and lens shading are unsupported.

## Sidecars and retention

`raw.recipe {document,id}` returns UTF-8 JSON in `data`, its SHA-256 and the parsed recipe. Save that text to a new file. `raw.reopen {source_path,recipe_path,id,control}` reads the sidecar and separately supplied original buffer, checks schema version 2, processing revision `inkbolt-raw-linear-v2`, strict field types and exact source SHA, then recreates an editable raw layer. Duplicate keys, malformed/truncated data, unsupported versions/algorithms and changed sources fail explicitly. No output or original file is overwritten by these commands.

Sidecars include capture calibration, all development/correction settings and source identity. They exclude layer placement, masks, opacity, sampling and scene state: those belong in snapshots. A sidecar does not contain original pixels and is not a source backup. A retained snapshot does contain exact original bytes, including padding. No proprietary sidecar compatibility is claimed.

The basic 16384-pixel bound still applies. Retained source bytes are limited to 128 KiB per layer, recipe input to 16 KiB, aggregate inline pixels to 65536, and all snapshots to 768 KiB. Source padding counts toward storage. Each correction has fixed bounded neighbourhood work; settings/import/expansion participate in existing cancellation and atomic-publication checks. Rendering uses the same bounded native-surface path as existing sampled content. File containers and larger camera sources remain unsupported.

`tests/test_raw_retained_cli.py` checks independent rational lens maps and convolution, actual reduction of noisy signal variation, sharpening/overshoot, order, alpha, source identity, masks/placement, sidecars, aggregate limits and durable history. `examples/raw_edit_workflow.py --output NEW_DIRECTORY` saves four editable original developments, sidecars, reopened documents and native/display deliveries.
