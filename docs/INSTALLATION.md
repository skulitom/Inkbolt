# Install and connect Inkbolt

Use a release for an existing build, or build from source with the pinned Rust
toolchain. See [platform support](PLATFORMS.md) for verified coverage and current
limitations.

## Use a release

Download the archive for your system from
[Releases](https://github.com/skulitom/Inkbolt/releases), check it against
`SHA256SUMS`, and extract it, for example to `C:\Tools\Inkbolt`. Create your
workspace folder first.

### Claude Code

```powershell
claude mcp add inkbolt -- C:\Tools\Inkbolt\inkbolt.exe --workspace C:\Work\Graphics mcp --tools core
```

### Codex

Add this entry to `~/.codex/config.toml`, using your binary and workspace paths:

```toml
[mcp_servers.inkbolt]
command = 'C:\Tools\Inkbolt\inkbolt.exe'
args = ['--workspace', 'C:\Work\Graphics', 'mcp', '--tools', 'core']
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
stdio clients. The examples target current source builds with `essentials`;
use `core` with the v0.82.0 release.

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
