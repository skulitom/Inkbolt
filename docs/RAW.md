# Explicit raw sensor development

`raw.develop` reads an original Bayer sensor buffer and returns a new editable raster document, a versioned recipe, source identity and range diagnostics. The Rust library exposes `raw::develop` for byte slices and `raw::import` for an absolute local path. CLI and MCP stdio share the implementation. Nothing writes to the input file.

This is a sensor-buffer interface. It does not identify camera containers, read embedded calibration, guess a camera model or infer colour from a filename. Callers supply sensor layout and calibration. The four little-endian word layouts follow the public [sensor format description](https://docs.kernel.org/userspace-api/media/v4l/pixfmt-srggb16.html); byte and big-endian word buffers have separate packing choices. No external camera SDK or new dependency is used.

## Request

```json
{
  "command": "raw.develop",
  "source_path": "C:/inputs/original.sensor",
  "id": "developed-photo",
  "capture": {
    "width": 64, "height": 48,
    "packing": "u16_le", "row_stride": 128, "pattern": "rggb",
    "black": [64, 64, 64, 64],
    "white": [4095, 4095, 4095, 4095],
    "camera_to_linear_srgb": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
  },
  "settings": {
    "exposure_stops": 0,
    "white_balance": {"type": "gains", "rgb": [1, 1, 1]},
    "output": "linear_srgb32", "range": "preserve", "resolution_ppi": 300
  }
}
```

The identity matrix declares an ideal synthetic sensor already calibrated to linear sRGB. It is not calibration for an arbitrary camera. The row-major matrix maps **white-balanced** linear camera RGB to linear sRGB under the intended reference illuminant. There is no additional chromatic adaptation or normalization.

All capture/settings fields above are required. Optional `expected_sha256` pins exact source bytes; mismatch returns `SOURCE_MISMATCH`. `control` accepts ordinary cancellation/deadline settings. Unknown fields and enumerated choices fail.

## Processing

- Packing is `u8`, `u16_le` or `u16_be`, unsigned bytes/words. Samples with fewer significant bits can use unpacked words and explicit white levels. Packed bitstreams are unsupported.
- Pattern is `rggb`, `grbg`, `gbrg` or `bggr`, starting at the top-left sensor site. `black`/`white` contain four row-major 2×2 **site** levels; the two greens can have different calibration.
- `row_stride` includes padding on every row, including the last. File length equals stride times height exactly. No header, trailer, orientation transform, active-area crop or colour metadata is interpreted.
- Normalize each site with `(code-black)/(white-black)` before interpolation. Below-black noise and above-white samples retain their signed scene values.
- Known channels retain normalized sensor values. Missing green uses axial neighbours; missing red/blue at green uses corresponding horizontal/vertical neighbours; opposite red/blue uses diagonals. Available neighbours have equal weights, renormalized at edges. Bilinear reconstruction cannot recover detail absent from the mosaic.
- White balance precedes the camera matrix. `gains` supplies direct RGB multipliers. `neutral` supplies a measured linear camera neutral and resolves gains to `[g/r,1,g/b]`. No automatic exposure, neutral selection or highlight reconstruction is applied.
- Matrix conversion precedes multiplication by `2^exposure_stops`. Output projection and quantization occur last.

`srgb8`/`srgb16` require `range:"clip"`: clamp to `[0,1]`, apply the sRGB transfer function and round to the nearest unsigned code. `linear_srgb32` stores signed binary32 scene values with `range:"preserve"`, or clips explicitly with `range:"clip"`. All outputs have opaque alpha. Float rounding is declared precision loss; there is no hidden eight-bit intermediate.

Diagnostics include effective white-balance gains, source counts below black and at/above white, developed per-channel extrema before projection, out-of-range channel counts and actual clipping counts. Saturation counts describe sensor codes, not reconstructed highlights.

## Source and delivery

The recipe contains schema version, algorithm revision `inkbolt-bayer-bilinear-v1`, SHA-256 of the original buffer including padding, calibration and settings. Original bytes remain external; the document contains developed samples. Save the recipe alongside the original, then pass its hash on later developments. A recipe alone is not a source backup. For retained in-document sources, editable corrections and strict sidecar reopening, use [RAW_EDITING.md](RAW_EDITING.md).

Samples share native TIFF delivery, display PNG/JPEG export, snapshots, ordinary edits, sessions and undo. Linear samples need a display view for display export; native float TIFF retains radiance. Delivery resolution derives from requested ppi. Existing create-only publication protects files.

## Bounds and evidence

Dimensions are 2..32768 per axis with at most **16384 sensor pixels**, ensuring supported float output fits shared snapshot/request limits. Row padding is at most 4096 bytes; total source is at most 32 MiB. Each finite black/white interval spans at least one code inside the packing range. Matrix entries are finite in `[-16,16]`, determinant magnitude at least `1e-12`. White-balance inputs are finite in `(0,64]`; effective gains in `[1/64,64]`. Exposure is `[-32,32]` stops, resolution `[1,9600]` ppi. Cancellation is checked before reading and each row.

Full-size camera files and compressed/container import remain unsupported. Retained raw layers add explicit lens correction, noise/detail controls and sidecars through the separate APIs in [RAW_EDITING.md](RAW_EDITING.md). Basic and extended development remain separate registry criteria.

`tests/test_raw_cli.py` uses original fixtures and independent rational stencils/colour equations. It covers all patterns/packings, odd sizes, borders, nonintegral calibration, affine reconstruction, matrix/white-balance/exposure order, signed range, clipping, encoded output, float precision, TIFF/PNG samples, physical resolution, source hashes, snapshots, agent history, limits and failures.

`python examples/raw_workflow.py --output NEW_DIRECTORY` creates an original chart with neutral, warmer and brighter developments, retained recipes and create-only image delivery.
