# Publishing Inkbolt

Pushing a version tag runs **Release**: locked builds with the Rust toolchain pinned in `rust-toolchain.toml` for Windows x64 (C runtime linked statically, so no Visual C++ Redistributable is needed), Linux x64 and macOS arm64, a CLI startup check, tests against each extracted native archive, the Windows MCPB smoke test, Node tests and MCPB 2.1.2 validation. After every build succeeds, it attests the archives and bundle and creates the GitHub release with checksums. `inkbolt-mcpb` retains the bundle, its checksum and `server.registry.json` as a workflow artifact. Reruns skip identical release assets and fail on different bytes; they never replace assets. Only the highest stable tag becomes Latest.

Pull requests touching the distribution workflows, packaging scripts, installation checker, toolchain or server metadata run the builds and installation checks as a dry run. Branch pushes do not trigger Release. Registry publication is always a separate manual dispatch after testing. It uses GitHub OIDC and skips versions already listed.

**Published registry versions are immutable. Publishing metadata-only permanently prevents that version from ever getting its bundle.** The `metadata_only` dispatch checkbox is an explicit fallback only when the release has no bundle; an attached bundle takes precedence.

## Release

Bump `[package] version` in Cargo.toml in its own commit, then tag that commit and push the tag:

```sh
git tag vX.Y.Z
git push origin vX.Y.Z
```

The tag must be `v` plus Cargo.toml's `[package] version`, a stable `X.Y.Z`. A manual run that publishes downloads requires an existing tag. Never reuse a tag for changed bytes. The manifest template has no version: the builder inserts Cargo's version. `server.json` stays metadata-only and may retain an older version on main. The entry writer stamps the release version into its generated copy, checks the bundle's version and SHA-256, and never edits the source metadata. Metadata-only publication also stamps the release version.

The builder discovers every page of the binary's core tool catalog and logs added or dropped names; `mcpb/manifest.json` keeps curated descriptions as display overrides, not a fixed tool inventory. New tools use the first sentence of the server description, shortened to at most 160 characters on a word boundary.

## Test the download, then publish

On Windows, use a checkout whose Cargo.toml matches the release, with Node 20 or newer. Substitute the tag below:

```sh
gh release download vX.Y.Z -R skulitom/Inkbolt -p inkbolt-windows-x64.mcpb -p inkbolt-windows-x64.mcpb.sha256 -D target/release-test
gh attestation verify target/release-test/inkbolt-windows-x64.mcpb --repo skulitom/Inkbolt --signer-workflow skulitom/Inkbolt/.github/workflows/release.yml
node mcpb/verify.mjs target/release-test/inkbolt-windows-x64.mcpb
```

Compare `Get-FileHash target/release-test/inkbolt-windows-x64.mcpb -Algorithm SHA256` with the downloaded `.sha256`. The verifier extracts to fresh folders under `target/`, launches the manifest command with an existing temporary workspace, checks every catalog page and creates one tiny vector snapshot. It checks for unexpected writes in the temporary folders and changes elsewhere in the checkout, then kills the server and removes its folders. This is a regression check, not an OS sandbox or a system-wide write monitor. Non-Windows runs fail unless explicitly given `--allow-skip`; a skip is not verification.

Optionally install the downloaded bundle in Claude Desktop (double-click it, or **Settings > Extensions > Advanced settings > Install Extension**), choose an existing local workspace and create a small document. Then dispatch:

```sh
gh workflow run publish-registry.yml -R skulitom/Inkbolt -f tag=vX.Y.Z
```

Publication requires the release, verifies the bundle's attestation from the Release workflow, validates the generated entry with checksum-pinned mcp-publisher 1.8.1 and reads back the published `fileSha256`. Tagged Cargo.toml and server.json supply release metadata; publishing helpers come from the workflow commit. Read the step summary and [registry listing](https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.skulitom/inkbolt).

## Local distribution checks

### Release size and startup

Release builds use ThinLTO, one code generation unit and symbol stripping.
Panic unwinding preserves the MCP and job-worker recovery paths. Ordinary
development verification uses the development profile.

At `6d91a43`, two clean locked builds on each machine used the same source,
toolchain and packaging commands. Only the release profile differed. Each of
the four extracted archives passed all eight installation checks.

| Local x64 measurement | Windows standard → tuned | WSL Linux standard → tuned |
| --- | ---: | ---: |
| Executable (bytes) | 35,015,168 → 33,854,464 | 33,316,456 → 25,918,720 |
| Download (bytes) | 11,488,957 → 11,402,598 | 11,251,511 → 10,474,457 |
| Clean release build (seconds) | 273 → 673 | 163 → 390 |
| CLI version, median (ms) | 9.51 → 9.37 | 1.31 → 1.17 |
| MCP initialize, median (ms) | 18.97 → 18.20 | 12.38 → 11.50 |

The startup measurements used 30 interleaved launches per binary and command
after two warm-ups. CLI timing includes process exit. MCP timing ends when the
first initialization response arrives. The smaller downloads cost additional
time at release build time.

### Test an extracted archive

The release workflow extracts each native archive on its target OS, compares
the executable with the locked release build, and checks the packaged notices
and version. It then runs eight CLI and MCP tests with the extracted
executable. They cover the README postcard, discovery, workspace permissions,
saved revisions, publication, retries, undo and editable curve output. To repeat the check
against the matching source revision and an extracted archive, run:

```sh
python -B tools/verify_release_install.py PATH_TO_EXTRACTED_FOLDER
```

For a hosted dry run, dispatch **Release** on the desired revision with the
tag field empty. All target builds and installation checks run. The archives
are available as workflow artifacts. Supplying an existing version tag selects
the publishing path.

### Software bill of materials

The release workflow writes a CycloneDX 1.6 JSON inventory for each target.
The native archive carries `sbom.cdx.json`. The Windows extension carries the
same inventory as the Windows archive. Each inventory is also a separate
`.cdx.json` release asset covered by the checksums and build attestation.

The inventory identifies the packaged executable by SHA-256 and lists the
Cargo packages used to build it, including build dependencies and procedural
macros. It records the resolved dependency relationships, package licenses and
the locked SHA-256 of each source distribution. Bundled SQLite has its own
entry with the version and SHA-256 of the C amalgamation. The target and Rust
compiler are recorded with the application. The inventory covers these build
inputs. Operating-system libraries and the contents of the compiler's standard
library fall outside its scope.

To generate it locally, run the locked native release build with
`--message-format=json-render-diagnostics` and save standard output. From the
same Cargo workspace, pass that file to `python tools/release_sbom.py` with
`--build-log`, `--target`, `--binary` and `--out`. The generator uses the
local Cargo cache. Pass the output file to the packaging scripts with `--sbom`.
The packagers check its target, version and executable digest before embedding it.
[CycloneDX JSON specification](https://cyclonedx.org/docs/1.6/json/)

### Check the Windows extension

Run these checks on their own, without builds, verification runs or edits in the
same checkout. The bundle verifier inventories repository files, including build
outputs and Git metadata, to detect unexpected writes. Concurrent work can change
that inventory or exhaust the smoke test's existing deadline.

```sh
node mcpb/build.mjs --binary target/release/inkbolt.exe
node --test mcpb/mcpb.test.mjs
node mcpb/verify.mjs target/dist/mcpb/inkbolt-windows-x64.mcpb
node mcpb/build.mjs --registry-entry --tag vX.Y.Z --bundle target/dist/mcpb/inkbolt-windows-x64.mcpb
```

Extract the bundle to a fresh folder and run `mcpb validate <folder>/manifest.json` with MCPB 2.1.2. ZIP entry order, timestamps and text line endings are fixed; use the same binary and Node/zlib version for byte-identical rebuilds. Existing different outputs require a fresh `--out` directory. Outputs default to `target/dist/`, which Git ignores.

The workspace defaults to `${HOME}`, the existing user home; Documents can be redirected or absent. Startup and discovery create nothing. Commands create `.inkbolt/sessions`, `.inkbolt/assets`, `.inkbolt/fonts`, `.inkbolt/publications` and `.inkbolt/jobs` as needed, with exports inside the selected workspace. Workspace path checks are not an OS sandbox. Both distributions carry `LICENSE` and `THIRD_PARTY_NOTICES.md`; native archives also carry README.md. No fonts or external color profiles are bundled: users supply permitted fonts with licenses, and research profiles stay external. See [dependency provenance](../docs/DEPENDENCIES.md).

Glama and awesome-mcp-servers submissions and updates are manual.
