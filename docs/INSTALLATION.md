# Install and connect Inkbolt

Use a release for an existing build, or build from source with the pinned Rust
toolchain. See [platform support](PLATFORMS.md) for verified coverage and current
limitations.

With Inkbolt 0.84, run `inkbolt --version` to print the package name and version in
one JSON response. The same version appears in the MCP handshake. For the
v0.83.0 download, use the `version` field from `inkbolt capabilities`.

### Check a local installation

With Inkbolt 0.84, run `inkbolt doctor` for the platform tier and available job and
publication-receipt backends. To inspect the workspace your agent will use,
run `inkbolt --workspace PATH_TO_EXISTING_FOLDER doctor`. Each default store,
including the font store, reports whether its directory exists and whether the
current process can list it, create files and create subdirectories. For a
missing store, `checked_directory` identifies the existing parent whose
permissions were checked. A null permission means the OS could not determine
it. Both commands leave the workspace untouched.

## Use a release

Download the archive for your system from
[Releases](https://github.com/skulitom/Inkbolt/releases), check it against
`SHA256SUMS`, and extract it, for example to `C:\Tools\Inkbolt`. Create your
workspace folder first.

Each 0.84 archive includes an editable postcard. Copy `examples/first-png.json`
to your workspace. With the binary on your path, run
`inkbolt --workspace "$PWD" first-png.json` there to create `postcard.png`.
The example works offline.

Starting with 0.84, release archives include a software bill of materials in
`sbom.cdx.json`. Its application SHA-256 identifies the executable inside the
archive. Individual component entries identify the locked dependencies and
bundled SQLite. [Inventory contents](../mcpb/PUBLISHING.md#software-bill-of-materials)

### Claude Code

```powershell
claude mcp add inkbolt -- C:\Tools\Inkbolt\inkbolt.exe --workspace C:\Work\Graphics mcp --tools essentials
```

### Codex

Add this entry to `~/.codex/config.toml`, using your binary and workspace paths:

```toml
[mcp_servers.inkbolt]
command = 'C:\Tools\Inkbolt\inkbolt.exe'
args = ['--workspace', 'C:\Work\Graphics', 'mcp', '--tools', 'essentials']
```

### Claude Desktop on Windows

Double-click `inkbolt-windows-x64.mcpb` from the release, or use
Settings > Extensions > Advanced settings > Install Extension, then pick an
existing workspace.

### Linux and macOS

Run the extracted `inkbolt` binary with the same arguments, using paths for your
system. The macOS binary isn't notarized: after a browser download, run
`xattr -d com.apple.quarantine inkbolt` once.

See the [Windows](../examples/mcp-config.windows.json) and
[Unix](../examples/mcp-config.unix.json) MCP configuration examples for other
stdio clients. The v0.83.0 `essentials` catalog starts with ten tools and
supports on-demand command discovery. For a v0.82.0 installation, use `core`.

## Install the CLI with Cargo

To install directly from GitHub, use Rust, Cargo, Git and a C compiler for
your target. The repository lists the [tested Rust toolchain](../rust-toolchain.toml).

```sh
cargo install --git https://github.com/skulitom/Inkbolt --locked
```

This installs the current default branch. Add `--rev COMMIT` to install a
specific revision. Cargo normally places the executable in its `bin` directory.
Run `inkbolt --help` from your shell, or give your MCP client the full
path to the installed executable.

## Build from source

Install Rust with rustup, then build from the repository root using the pinned
toolchain and dependencies.

### Windows

```powershell
cargo build --locked
.\target\debug\inkbolt.exe examples/add-svg.json
.\target\debug\inkbolt.exe mcp --tools essentials
```

### Linux and macOS

```bash
cargo build --locked
./target/debug/inkbolt examples/add-svg.json
./target/debug/inkbolt mcp --tools essentials
```

The example returns editable artwork as JSON. The final command starts the MCP
adapter. Run `inkbolt --help` for command-line request examples.

Continue with [runnable examples](../examples/README.md),
[workspace setup](AGENT_WORKSPACE.md) and [tool discovery](AGENT_DISCOVERY.md).
Maintainers can find release procedures in [Publishing](../mcpb/PUBLISHING.md).
