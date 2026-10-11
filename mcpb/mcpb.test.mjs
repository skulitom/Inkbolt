import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFile, writeFile, mkdir, mkdtemp, rm, access, link } from 'node:fs/promises';
import path from 'node:path';
import { gunzipSync } from 'node:zlib';
import { archive } from './archive.mjs';
import { root, cargoVersion, assembleMcpb, buildMcpb, registryEntry, BUNDLE_NAME, json } from './build.mjs';
import { readZip, writeZip, sha256 } from './zip.mjs';
import { checkManifest, inside, verifyMcpb } from './verify.mjs';

let temp, base, binary, template, metadata, build;
const version = '7.8.9';
const writeJSON = (file, value) => writeFile(file, json(value));
const cargo = value => `[package]\nname = "fixture"\nversion = "${value}"\n\n[dependencies]\nunused = "0.1.0"\n`;
before(async () => {
  await mkdir(path.join(root, 'target'), { recursive: true });
  temp = await mkdtemp(path.join(root, 'target/mcpb-test-'));
  base = path.join(temp, 'source');
  await mkdir(path.join(base, 'mcpb'), { recursive: true });
  template = JSON.parse(await readFile(path.join(root, 'mcpb/manifest.json')));
  metadata = { ...JSON.parse(await readFile(path.join(root, 'server.json'))), version: '0.0.1' };
  await writeJSON(path.join(base, 'mcpb/manifest.json'), template);
  await writeJSON(path.join(base, 'server.json'), metadata);
  await writeFile(path.join(base, 'Cargo.toml'), cargo(version));
  await writeFile(path.join(base, 'LICENSE'), 'Fixture license\r\n');
  await writeFile(path.join(base, 'THIRD_PARTY_NOTICES.md'), 'Fixture notices\r\n');
  await writeFile(path.join(base, 'README.md'), 'Fixture readme\r\n');
  binary = path.join(base, 'stand-in.exe');
  await writeFile(binary, Buffer.from([77, 90, 0, 13, 10, 255]));
  build = await buildMcpb({ base, binary, out: path.join(temp, 'first') });
});
after(async () => {
  if (temp) {
    assert.ok(inside(path.join(root, 'target'), temp));
    await rm(temp, { recursive: true, force: true });
  }
});

test('metadata stays package-free with the required identity and short description', async () => {
  const server = JSON.parse(await readFile(path.join(root, 'server.json')));
  assert.equal(server.name, 'io.github.skulitom/inkbolt');
  assert.equal(server.title, 'Inkbolt vector and raster editor');
  assert.equal(server.$schema, 'https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json');
  assert.equal(server.repository.id, '1411041333');
  assert.equal(Object.hasOwn(server, 'packages'), false);
  assert.ok(server.description.length > 0 && server.description.length <= 100);
});

test('manifest template has no version and has valid binary-server fields', async () => {
  assert.equal(Object.hasOwn(template, 'version'), false);
  checkManifest({ ...template, version: await cargoVersion() }, await cargoVersion());
  assert.equal(template.tools.length, 22);
});

test('two builds are identical, with exactly the required entries and checksum', async () => {
  const second = await buildMcpb({ base, binary, out: path.join(temp, 'second') });
  assert.deepEqual(second.bytes, build.bytes);
  const entries = readZip(build.bytes);
  assert.deepEqual([...entries.keys()], ['LICENSE', 'THIRD_PARTY_NOTICES.md', 'manifest.json', 'server/inkbolt.exe']);
  assert.deepEqual(entries.get('server/inkbolt.exe').read(), await readFile(binary));
  assert.equal(entries.get('LICENSE').read().toString(), 'Fixture license\n');
  assert.equal(JSON.parse(entries.get('manifest.json').read()).version, version);
  assert.equal(await readFile(`${build.bundle}.sha256`, 'utf8'), `${sha256(build.bytes)}  ${BUNDLE_NAME}\n`);
  await writeFile(path.join(base, 'LICENSE'), 'Fixture license\n');
  assert.deepEqual((await assembleMcpb({ base, binary })).bytes, build.bytes);
  await buildMcpb({ base, binary, out: path.join(temp, 'first') });
});

test('builder refuses a template version, invalid package versions and missing binaries', async () => {
  try {
    await writeJSON(path.join(base, 'mcpb/manifest.json'), { ...template, version });
    await assert.rejects(assembleMcpb({ base, binary }), /must not contain version/);
  } finally { await writeJSON(path.join(base, 'mcpb/manifest.json'), template); }
  try {
    for (const value of ['1.0', 'v1.0.0', '01.0.0', '1.0.0-beta']) {
      await writeFile(path.join(base, 'Cargo.toml'), cargo(value));
      await assert.rejects(assembleMcpb({ base, binary }), /version must have the form X.Y.Z/);
    }
    await writeFile(path.join(base, 'Cargo.toml'), '[dependencies]\nversion = "1.2.3"\n');
    await assert.rejects(cargoVersion(base), /version must have the form X.Y.Z/);
  } finally { await writeFile(path.join(base, 'Cargo.toml'), cargo(version)); }
  await assert.rejects(assembleMcpb({ base }), /--binary is required/);
  await assert.rejects(assembleMcpb({ base, binary: path.join(temp, 'missing.exe') }), /Missing binary/);
});

test('existing different artifacts are preserved', async () => {
  const out = path.join(temp, 'occupied'); await mkdir(out);
  const file = path.join(out, BUNDLE_NAME); await writeFile(file, 'keep');
  await assert.rejects(buildMcpb({ base, binary, out }), /already exists with different contents/);
  assert.equal(await readFile(file, 'utf8'), 'keep');
});

test('native archives are deterministic and carry the binary, readme and licenses', async () => {
  for (const target of ['x86_64-pc-windows-msvc', 'x86_64-unknown-linux-gnu', 'aarch64-apple-darwin']) {
    const options = { base, binary, target, smoke: false, out: path.join(temp, 'archives') };
    const first = await archive(options), second = await archive(options);
    assert.deepEqual(first.bytes, second.bytes);
    const isWindows = target.includes('windows'), entries = new Map();
    if (isWindows) {
      for (const [name, entry] of readZip(first.bytes)) entries.set(name, entry.read());
    } else {
      const tar = gunzipSync(first.bytes);
      const string = (start, size) => tar.subarray(start, start + size).toString().replace(/\0.*$/s, '');
      for (let at = 0; tar[at];) {
        const name = string(at, 100), size = parseInt(string(at + 124, 12), 8);
        assert.equal(string(at + 257, 5), 'ustar');
        assert.equal(parseInt(string(at + 100, 8), 8), name === 'inkbolt' ? 0o755 : 0o644);
        const header = Buffer.from(tar.subarray(at, at + 512)), sum = parseInt(string(at + 148, 8), 8);
        header.fill(32, 148, 156);
        assert.equal(header.reduce((a, b) => a + b, 0), sum);
        entries.set(name, tar.subarray(at + 512, at + 512 + size));
        at += 512 + Math.ceil(size / 512) * 512;
      }
    }
    const executable = isWindows ? 'inkbolt.exe' : 'inkbolt';
    assert.deepEqual([...entries.keys()].sort(), ['LICENSE', 'README.md', 'THIRD_PARTY_NOTICES.md', executable].sort());
    assert.deepEqual(entries.get(executable), await readFile(binary));
    assert.equal(entries.get('README.md').toString(), 'Fixture readme\n');
  }
});

test('registry entry stamps Cargo version despite stale metadata and preserves inputs', async () => {
  const out = path.join(temp, 'server.registry.json'), before = await readFile(path.join(base, 'server.json'));
  const entry = await registryEntry({ base, tag: `v${version}`, bundle: build.bundle, out });
  assert.equal(entry.version, version);
  assert.deepEqual(entry.packages, [{ registryType: 'mcpb', identifier: `https://github.com/skulitom/Inkbolt/releases/download/v${version}/${BUNDLE_NAME}`, version, fileSha256: sha256(build.bytes), transport: { type: 'stdio' } }]);
  assert.deepEqual(JSON.parse(await readFile(out)), entry);
  assert.deepEqual(await readFile(path.join(base, 'server.json')), before);
  await registryEntry({ base, tag: `v${version}`, bundle: build.bundle, out });
});

test('a Cargo-only version bump needs no manifest or metadata edits', async () => {
  try {
    await writeFile(path.join(base, 'Cargo.toml'), cargo('7.9.0'));
    const next = await buildMcpb({ base, binary, out: path.join(temp, 'bumped') });
    const entry = await registryEntry({ base, tag: 'v7.9.0', bundle: next.bundle, out: path.join(temp, 'bumped-entry.json') });
    assert.equal(next.manifest.version, '7.9.0');
    assert.equal(entry.version, '7.9.0');
    assert.equal(entry.packages[0].version, '7.9.0');
    assert.deepEqual(JSON.parse(await readFile(path.join(base, 'server.json'))), metadata);
    assert.deepEqual(JSON.parse(await readFile(path.join(base, 'mcpb/manifest.json'))), template);
  } finally { await writeFile(path.join(base, 'Cargo.toml'), cargo(version)); }
});

test('registry entry rejects bad tags, version mismatch and packages in metadata', async () => {
  const options = { base, tag: `v${version}`, bundle: build.bundle, out: path.join(temp, 'refused.json') };
  for (const tag of ['7.8.9', 'v1.2', 'v01.2.3', 'v1.2.3-beta', '../v1.2.3', 'v1.2.3\n']) await assert.rejects(registryEntry({ ...options, tag }), /Tag must have the form/);
  await assert.rejects(registryEntry({ ...options, tag: 'v7.8.10' }), /Tag and Cargo.toml versions must match/);
  try {
    await writeJSON(path.join(base, 'server.json'), { ...metadata, packages: [] });
    await assert.rejects(registryEntry(options), /metadata-only/);
  } finally { await writeJSON(path.join(base, 'server.json'), metadata); }
  const files = new Map([...readZip(build.bytes)].map(([name, entry]) => [name, entry.read()]));
  files.set('manifest.json', json({ ...build.manifest, version: '7.8.8' }));
  const oldBundle = path.join(temp, 'old.mcpb'); await writeFile(oldBundle, writeZip(files));
  await assert.rejects(registryEntry({ ...options, bundle: oldBundle }), /Bundle manifest version must match/);
  files.delete('manifest.json'); await writeFile(oldBundle, writeZip(files));
  await assert.rejects(registryEntry({ ...options, bundle: oldBundle }), /Bundle has no manifest/);
});

test('registry output cannot overwrite metadata or bundle, including hard-link aliases', async () => {
  const alias = path.join(temp, 'alias.json'); await link(path.join(base, 'server.json'), alias);
  const outputs = [path.join(base, 'server.json'), build.bundle, alias, path.join(base, 'mcpb/../server.json')];
  if (process.platform === 'win32') outputs.push(path.join(base, 'SERVER.JSON'));
  for (const out of outputs) {
    const before = await readFile(out);
    await assert.rejects(registryEntry({ base, tag: `v${version}`, bundle: build.bundle, out }), /must not overwrite/);
    assert.deepEqual(await readFile(out), before);
  }
});

test('ZIP reader rejects malformed archives and detects CRC corruption', () => {
  assert.throws(() => readZip(Buffer.from('no')), /Not a ZIP/);
  const bytes = writeZip(new Map([['small', Buffer.from('abc')]]));
  bytes[30 + Buffer.byteLength('small')] ^= 1;
  assert.throws(() => readZip(bytes).get('small').read(), /damaged/);
});

test('verifier rejects incompatible manifest versions and launch commands', () => {
  assert.throws(() => checkManifest({ ...template, version: '1.0.0' }, '1.0.1'), /version must equal/);
  assert.throws(() => checkManifest({ ...build.manifest, compatibility: { platforms: ['linux'] } }, version));
  assert.throws(() => checkManifest({ ...build.manifest, server: { ...template.server, mcp_config: { command: 'unexpected' } } }, version));
});

test('non-Windows verification requires explicit allow-skip', { skip: process.platform === 'win32' }, async () => {
  await assert.rejects(verifyMcpb(build.bundle), /Windows only/);
  assert.deepEqual(await verifyMcpb(build.bundle, { allowSkip: true }), { skipped: true });
});

test('real release binary passes the standalone bundle smoke test', async context => {
  const realBinary = path.join(root, 'target/release/inkbolt.exe');
  if (process.platform !== 'win32') { context.skip('Windows only'); return; }
  try { await access(realBinary); } catch (error) { if (error.code !== 'ENOENT') throw error; context.skip('No release binary'); return; }
  const real = await buildMcpb({ binary: realBinary, out: path.join(temp, 'real') });
  const output = execFileSync(process.execPath, [path.join(root, 'mcpb/verify.mjs'), real.bundle], { encoding: 'utf8', timeout: 22000, windowsHide: true });
  assert.match(output, /MCPB verified: Inkbolt .*22 tools.*vector creation passed/);
});
