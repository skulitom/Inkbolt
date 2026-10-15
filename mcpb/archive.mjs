// Native release archives with fixed metadata. Node 20+, no external archiver.
import { readFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { gzipSync } from 'node:zlib';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { cargoVersion, root, textFile, writeUnchangedOrNew } from './build.mjs';
import { writeZip } from './zip.mjs';

export const TARGETS = {
  'x86_64-pc-windows-msvc': { platform: 'win32', arch: 'x64', binary: 'inkbolt.exe', extension: 'zip' },
  'x86_64-unknown-linux-gnu': { platform: 'linux', arch: 'x64', binary: 'inkbolt', extension: 'tar.gz' },
  'aarch64-apple-darwin': { platform: 'darwin', arch: 'arm64', binary: 'inkbolt', extension: 'tar.gz' }
};

// Four short root-level names fit the ustar name field; preserve the executable bit.
export function writeTarGz(files, executable) {
  const blocks = [], octal = (value, length) => value.toString(8).padStart(length - 1, '0') + '\0';
  for (const [name, data] of [...files].sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)) {
    if (!/^[A-Za-z0-9_.-]{1,100}$/.test(name)) throw new Error(`Unsupported tar entry name: ${name}`);
    const header = Buffer.alloc(512);
    header.write(name); header.write(octal(name === executable ? 0o755 : 0o644, 8), 100);
    header.write(octal(0, 8), 108); header.write(octal(0, 8), 116);
    header.write(octal(data.length, 12), 124); header.write(octal(315532800, 12), 136);
    header.fill(32, 148, 156); header.write('0', 156); header.write('ustar\0' + '00', 257);
    header.write(octal(header.reduce((sum, byte) => sum + byte, 0), 7) + ' ', 148);
    blocks.push(header, data, Buffer.alloc((512 - data.length % 512) % 512));
  }
  blocks.push(Buffer.alloc(1024));
  const bytes = gzipSync(Buffer.concat(blocks), { level: 9 });
  bytes[9] = 3; // Fixed gzip OS marker (Unix).
  return bytes;
}

export async function archive({ target, binary, base = root, out = path.join(root, 'target/dist/release'), smoke = true }) {
  const spec = TARGETS[target];
  if (!spec) throw new Error(`Unsupported release target: ${target}`);
  if (!binary) throw new Error('--binary is required.');
  if (smoke) {
    if (process.platform !== spec.platform || process.arch !== spec.arch) throw new Error(`Build ${target} on its native runner.`);
    const result = spawnSync(path.resolve(binary), [], { cwd: base, input: '{"command":"capabilities"}\n', encoding: 'utf8', timeout: 15000, maxBuffer: 8 * 1024 * 1024, windowsHide: true });
    if (result.error) throw result.error;
    if (result.status !== 0 || JSON.parse(result.stdout).ok !== true) throw new Error(`CLI capabilities smoke test failed: ${result.stderr}`);
  }
  const files = new Map([[spec.binary, await readFile(binary)]]);
  for (const name of ['LICENSE', 'README.md', 'THIRD_PARTY_NOTICES.md']) files.set(name, await textFile(path.join(base, name)));
  const bytes = spec.extension === 'zip' ? writeZip(files) : writeTarGz(files, spec.binary);
  const file = path.resolve(out, `inkbolt-v${await cargoVersion(base)}-${target}.${spec.extension}`);
  await writeUnchangedOrNew(file, bytes);
  return { file, bytes };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  Promise.resolve().then(async () => {
    const options = {}, args = process.argv.slice(2);
    for (let i = 0; i < args.length; i += 2) {
      if (!['--target', '--binary', '--out'].includes(args[i]) || !args[i + 1] || args[i + 1].startsWith('--') || Object.hasOwn(options, args[i].slice(2))) throw new Error(`Unknown or incomplete option: ${args[i]}`);
      options[args[i].slice(2)] = args[i + 1];
    }
    const result = await archive(options); console.log(`${result.file}: ${result.bytes.length} bytes; CLI capabilities passed.`);
  }).catch(error => { console.error(error.message); process.exitCode = 1; });
}
