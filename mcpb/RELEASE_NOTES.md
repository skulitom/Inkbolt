Inkbolt 0.83.0 brings shape combinations, larger image workflows and a smaller MCP catalog to the local vector and raster editor.

## Editing

- Combine filled shapes with union, intersection, difference or xor in one undoable edit. Circles and ellipses are supported. Polygon output is the default. Request `"output":"curves"` to retain supported cubic spans and receive their integrated area and error bounds. [Shape combinations](https://github.com/skulitom/Inkbolt/blob/v0.83.0/docs/BOOLEANS.md)
- Import baseline and progressive JPEGs into native image storage. Work with editable RGB8 layered imports, feathered masks, guided selections, brushes and patch repair. Focused previews can render the selected region of a large image. [Image import](https://github.com/skulitom/Inkbolt/blob/v0.83.0/docs/NATIVE_JPEG_IMPORT.md) · [Layered import](https://github.com/skulitom/Inkbolt/blob/v0.83.0/docs/LAYERED_NATIVE_IMPORT.md) · [Image repair](https://github.com/skulitom/Inkbolt/blob/v0.83.0/docs/NATIVE_REPAIR.md)
- Checked Windows and Linux workflows include 24 MP JPEG import, a 50 MP 16-bit edit with history and TIFF export, A2 delivery at 300 ppi, and an 8192 × 8192 PNG render. Each workflow has its own input and memory limits. [Measured workflows](https://github.com/skulitom/Inkbolt/blob/v0.83.0/docs/SCALE_WORKLOADS.md)

## Using Inkbolt with an agent

Use `inkbolt --workspace PATH_TO_EXISTING_FOLDER mcp --tools essentials` for ten initial tools. An agent can request more schemas and focused request examples as it works. Existing `core` and `full` clients continue to work. [Agent discovery](https://github.com/skulitom/Inkbolt/blob/v0.83.0/docs/AGENT_DISCOVERY.md)

## Downloads

Choose the Windows x64 ZIP, Linux x64 tar.gz or macOS Apple silicon tar.gz. Each contains the binary, README, license and dependency notices. The Windows desktop extension is also available as `inkbolt-windows-x64.mcpb`. Background export jobs require Windows. [Installation](https://github.com/skulitom/Inkbolt/blob/v0.83.0/docs/INSTALLATION.md) · [Platform support](https://github.com/skulitom/Inkbolt/blob/v0.83.0/docs/PLATFORMS.md)

Compare your download's SHA-256 digest with its entry in `SHA256SUMS`. The Windows bundle also has a separate `.sha256` file. To check the GitHub build attestation, substitute the name of your downloaded asset in this command.

```sh
gh attestation verify inkbolt-windows-x64.mcpb --repo skulitom/Inkbolt --signer-workflow skulitom/Inkbolt/.github/workflows/release.yml
```
