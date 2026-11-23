Inkbolt 0.85.1 corrects the replay flag on durable publication receipts when multiple processes submit the same request concurrently.

The caller that created the receipt now gets `replayed: false` even if another caller finishes publishing first. Retries get `replayed: true`. This covers document and session exports, backups, restores and migrations. In v0.85.0 the race affected the response flag. Callers still received the same output identity and the file was created once. [Durable receipt contract](https://github.com/skulitom/Inkbolt/blob/v0.85.1/docs/PUBLICATION_RECEIPTS.md)

The [v0.85.0 release notes](https://github.com/skulitom/Inkbolt/releases/tag/v0.85.0) cover editable PDF artwork and moving saved edits between Windows and Linux.

## Downloads

Choose the native archive for Windows x64, Linux x64, Apple silicon or Intel Macs. A desktop MCP extension is also available for Windows. Extract the archive and run the following command from its folder to render the included postcard. [Installation guide](https://github.com/skulitom/Inkbolt/blob/v0.85.1/docs/INSTALLATION.md)

```sh
./inkbolt --workspace "$PWD" examples/first-png.json
```

Use `SHA256SUMS` to verify the downloads. The four archives, their CycloneDX inventories and the Windows extension carry build attestations.
