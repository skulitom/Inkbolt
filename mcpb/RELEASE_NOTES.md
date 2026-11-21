Inkbolt 0.84 keeps curved shape combinations editable by default and adds native downloads for Intel Macs.

## Editable shape combinations

Union, intersection, difference and xor now keep Bézier handles on supported curved boundaries. An agent can change the resulting curve after combining shapes. For tangencies that need an approximation, the operation reports the precision it used. Explicit polygon output is still available. Edits and pending proposals saved in 0.83 keep the geometry originally reviewed when committed or retried. [Shape combinations](https://github.com/skulitom/Inkbolt/blob/v0.84.0/docs/BOOLEANS.md)

## Installation and examples

Copy `examples/first-png.json` from the archive into an empty workspace and run
`inkbolt --workspace "$PWD" first-png.json` there. It creates a four-shape
mountain postcard using only the downloaded files.

- Run `inkbolt --version` for a short JSON response. Run `inkbolt --workspace PATH_TO_EXISTING_FOLDER doctor` to check the platform and access to session, font and other stores. The check leaves the workspace untouched. [Installation guide](https://github.com/skulitom/Inkbolt/blob/v0.84.0/docs/INSTALLATION.md)
- Python examples can use an installed executable. Set `INKBOLT_EXE` to its full path, or put it on your shell's path when using a checkout without a development build. [Runnable examples](https://github.com/skulitom/Inkbolt/blob/v0.84.0/examples/README.md)

## Downloads

Choose the archive for Windows x64, Linux x64, Apple silicon (`aarch64-apple-darwin`) or Intel macOS (`x86_64-apple-darwin`). The Windows desktop extension is also available. Background export jobs require Windows. [Platform support](https://github.com/skulitom/Inkbolt/blob/v0.84.0/docs/PLATFORMS.md)

Each archive includes a CycloneDX inventory that identifies the executable, its Cargo build dependencies and bundled SQLite. The Windows extension carries the Windows inventory. Compare the download with its digest in `SHA256SUMS`. To verify its GitHub build attestation, substitute the filename in this command.

```sh
gh attestation verify inkbolt-windows-x64.mcpb --repo skulitom/Inkbolt --signer-workflow skulitom/Inkbolt/.github/workflows/release.yml
```
