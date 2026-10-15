Inkbolt is a local vector and raster editing engine for agents, with a JSON CLI and MCP over stdio. It requires no network listener or account at runtime. Editing and interchange retain the documented bounds.

The Windows x64 ZIP, Linux x64 tar.gz and macOS arm64 tar.gz contain the native binary, README, MIT license and dependency notices. Extract the archive for your system and select an existing workspace. `inkbolt-windows-x64.mcpb` contains the Windows x64 binary and compact MCP catalog for Claude Desktop: double-click it, or use Settings > Extensions > Advanced settings > Install Extension.

Check native archives and the bundle against `SHA256SUMS`. The bundle also has `inkbolt-windows-x64.mcpb.sha256`. On PowerShell, compare `(Get-FileHash inkbolt-windows-x64.mcpb -Algorithm SHA256).Hash` with that file. On systems with sha256sum, use `sha256sum --check SHA256SUMS` after downloading all listed assets.

Verify build provenance (substitute an archive filename to verify another asset):

```sh
gh attestation verify inkbolt-windows-x64.mcpb --repo skulitom/Inkbolt --signer-workflow skulitom/Inkbolt/.github/workflows/release.yml
```

The bundle is available immediately with the release. MCP Registry publication is a separate manual step after testing; see [Publishing](https://github.com/skulitom/Inkbolt/blob/main/mcpb/PUBLISHING.md).
