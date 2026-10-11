# Publishing Inkbolt

Pushing a version tag runs **Release**: locked Rust 1.98.1 builds for Windows x64, Linux x64 and macOS arm64, a CLI startup check, native archives, the Windows MCPB smoke test, Node tests and MCPB 2.1.2 validation. After every build succeeds, it attests the archives and bundle and creates the GitHub release with checksums. `inkbolt-mcpb` retains the bundle, its checksum and `server.registry.json` as a workflow artifact. Reruns skip identical release assets and fail on different bytes; they never replace assets. Only the highest stable tag becomes Latest.

Pull requests touching the distribution workflows, `mcpb/` or `server.json` run the builds and Windows checks as a dry run, without attestation or release. Branch pushes do not trigger Release. Registry publication is always a separate manual dispatch after testing. It uses GitHub OIDC and skips versions already listed.

**Published registry versions are immutable. Publishing metadata-only permanently prevents that version from ever getting its bundle.** The `metadata_only` dispatch checkbox is an explicit fallback only when the release has no bundle; an attached bundle takes precedence.

## Release

Use Artem's usual Cargo.toml version-bump commit, then tag that commit and push the tag:

```sh
git tag vX.Y.Z
git push origin vX.Y.Z
```

The tag must be `v` plus Cargo.toml's `[package] version`, a stable `X.Y.Z`. A manual Release run also requires an existing tag. Never reuse a tag for changed bytes. The manifest template has no version: the builder inserts Cargo's version. `server.json` stays metadata-only and may retain an older version on main. The entry writer stamps the release version into its generated copy, checks the bundle's version and SHA-256, and never edits the source metadata. Metadata-only publication also stamps the release version.

The builder discovers every page of the binary's core tool catalog and logs added or dropped names; `mcpb/manifest.json` keeps curated descriptions as display overrides, not a fixed tool inventory. New tools use the first sentence of the server description, shortened to at most 160 characters on a word boundary.

## Test the download, then publish

On Windows, use a checkout whose Cargo.toml matches the release, with Node 20 or newer. Substitute the tag below:

```sh
gh release download vX.Y.Z -R skulitom/Inkbolt -p inkbolt-windows-x64.mcpb -p inkbolt-windows-x64.mcpb.sha256 -D target/release-test
gh attestation verify target/release-test/inkbolt-windows-x64.mcpb --repo skulitom/Inkbolt --signer-workflow skulitom/Inkbolt/.github/workflows/release.yml
node mcpb/verify.mjs target/release-test/inkbolt-windows-x64.mcpb
```

Compare `Get-FileHash target/release-test/inkbolt-windows-x64.mcpb -Algorithm SHA256` with the downloaded `.sha256`. The verifier extracts to fresh folders under `target/`, launches the manifest command with an existing temporary workspace, checks every catalog page and creates one tiny vector snapshot. It checks for unexpected writes in the temporary folders and changes elsewhere in the checkout, then kills the server and removes its folders. This is a regression check, not an OS sandbox or a system-wide write monitor. Non-Windows runs fail unless explicitly given `--allow-skip`; a skip is not verification.

Optionally install the downloaded bundle in Claude Desktop: **Settings > Extensions > Install from file**, choose an existing local workspace and create a small document. Then dispatch:

```sh
gh workflow run publish-registry.yml -R skulitom/Inkbolt -f tag=vX.Y.Z
```

Publication requires the release, verifies the bundle's attestation from the Release workflow, validates the generated entry with checksum-pinned mcp-publisher 1.8.1 and reads back the published `fileSha256`. Tagged Cargo.toml and server.json supply release metadata; publishing helpers come from the workflow commit. Read the step summary and [registry listing](https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.skulitom/inkbolt).

## Local distribution checks

```sh
node mcpb/build.mjs --binary target/release/inkbolt.exe
node --test mcpb/mcpb.test.mjs
node mcpb/verify.mjs target/dist/mcpb/inkbolt-windows-x64.mcpb
node mcpb/build.mjs --registry-entry --tag vX.Y.Z --bundle target/dist/mcpb/inkbolt-windows-x64.mcpb
```

Extract the bundle to a fresh folder and run `mcpb validate <folder>/manifest.json` with MCPB 2.1.2. ZIP entry order, timestamps and text line endings are fixed; use the same binary and Node/zlib version for byte-identical rebuilds. Existing different outputs require a fresh `--out` directory. Outputs default to `target/dist/`, which Git ignores.

The workspace defaults to `${HOME}`, the existing user home; Documents can be redirected or absent. Startup and discovery create nothing. Commands create `.inkbolt/sessions`, `.inkbolt/assets`, `.inkbolt/fonts`, `.inkbolt/publications` and `.inkbolt/jobs` as needed, with exports inside the selected workspace. Workspace path checks are not an OS sandbox. Both distributions carry `LICENSE` and `THIRD_PARTY_NOTICES.md`; native archives also carry README.md. No fonts or external color profiles are bundled: users supply permitted fonts with licenses, and research profiles stay external. See [dependency provenance](../docs/DEPENDENCIES.md).

Glama and awesome-mcp-servers submissions and updates are manual.
