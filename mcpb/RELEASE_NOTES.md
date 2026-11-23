Inkbolt 0.85 lets an agent reopen PDF artwork, edit placed images and move a saved session between Windows and Linux.

## Open and edit a PDF page

Use `pdf.import` to reopen filled paths, curves, groups and embedded RGB or grayscale images from a selected page. Repeated image placements share one asset and can be moved independently. The receipt identifies source objects and retained page coordinates. JPEG streams, embedded text and native print inks are still outside the import subset. [PDF import guide](https://github.com/skulitom/Inkbolt/blob/v0.85.0/docs/PDF.md#reopen-a-page-for-editing)

For PDF export, supported right-to-left labels retain reading order and word selection. CFF2 lettering can remain searchable at the selected font settings. Marked print sheets can carry searchable labels alongside spot-ink plates. [PDF text and print delivery](https://github.com/skulitom/Inkbolt/blob/v0.85.0/docs/PDF.md#searchable-text)

## Continue a saved edit

Back up a session on Windows or Linux and recover its history on the other platform. Transfer referenced image and font stores separately and rebind them at a new revision. A script that loses an edit reply can look up the original receipt by request ID. For new screen artwork, a four-request example creates the document and exports a transparent PNG from the saved revision. [Portable sessions](https://github.com/skulitom/Inkbolt/blob/v0.85.0/docs/SESSION_BACKUPS.md#resources-and-portability) · [Screen artwork](https://github.com/skulitom/Inkbolt/blob/v0.85.0/docs/AGENT_DISCOVERY.md#screen-artwork)

Layered RGB8 files can retain clipping relationships, group fill, pixel-layer knockout and eligible opaque backgrounds through import and export. [Layered artwork](https://github.com/skulitom/Inkbolt/blob/v0.85.0/docs/LAYERED.md)

## Downloads

Choose the native archive for Windows x64, Linux x64, Apple silicon or Intel Macs. A desktop MCP extension is also available for Windows. The archives include the executable, an editable postcard, licenses and a CycloneDX inventory. Background export jobs require Windows.

Extract the archive and run the following command from its folder to make `postcard.png`. [Installation guide](https://github.com/skulitom/Inkbolt/blob/v0.85.0/docs/INSTALLATION.md)

```sh
./inkbolt --workspace "$PWD" examples/first-png.json
```

Use `SHA256SUMS` to check the downloads. For example, verify the Windows extension's build provenance with this command.

```sh
gh attestation verify inkbolt-windows-x64.mcpb --repo skulitom/Inkbolt --signer-workflow skulitom/Inkbolt/.github/workflows/release.yml
```
