// Small stdio client shared by bundle discovery and verification. Node built-ins only.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';

export const inside = (base, file) => {
  const relative = path.relative(base, file);
  return relative !== '' && relative !== '..' && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative);
};

export async function mcpFolders(temp) {
  const folders = Object.fromEntries(['workspace', 'cwd', 'home', 'scratch'].map(name => [name, path.join(temp, name === 'scratch' ? 'tmp' : name)]));
  for (const directory of Object.values(folders)) await mkdir(directory);
  return folders;
}

export function startMcp({ manifest, extension, binary, workspace, cwd, home, scratch }) {
  const config = manifest.server.mcp_config;
  const substitute = value => value.replaceAll('${__dirname}', extension ?? '').replaceAll('${user_config.workspace}', workspace);
  // During a build, the supplied executable stands in for the packaged entry point.
  if (binary) assert.equal(config.command, '${__dirname}/' + manifest.server.entry_point);
  const pending = new Map();
  let id = 0, buffer = '', stderr = '', failure;
  const fail = error => { failure ??= error; for (const request of pending.values()) request.reject(error); pending.clear(); };
  const child = spawn(binary ? path.resolve(binary) : substitute(config.command), config.args.map(substitute), {
    cwd, env: { ...process.env, HOME: home, USERPROFILE: home, APPDATA: home, LOCALAPPDATA: home, TMP: scratch, TEMP: scratch },
    stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true
  });
  const closed = new Promise(resolve => child.once('close', (code, signal) => { fail(new Error(`MCP server exited (${code ?? signal}): ${stderr}`)); resolve(); }));
  child.on('error', fail); child.stdin.on('error', fail);
  child.stderr.setEncoding('utf8'); child.stderr.on('data', data => { stderr = (stderr + data).slice(-8000); });
  child.stdout.setEncoding('utf8');
  child.stdout.on('data', data => {
    try {
      buffer += data;
      assert.ok(buffer.length < 8 * 1024 * 1024, 'MCP response exceeds discovery/verification budget');
      let end;
      while ((end = buffer.indexOf('\n')) !== -1) {
        const line = buffer.slice(0, end); buffer = buffer.slice(end + 1);
        const message = JSON.parse(line), request = pending.get(message.id);
        assert.equal(message.jsonrpc, '2.0');
        if (!request) continue;
        pending.delete(message.id);
        if (message.error) request.reject(new Error(`${request.method}: ${JSON.stringify(message.error)}`));
        else request.resolve(message.result);
      }
    } catch (error) { fail(error); }
  });
  const timer = setTimeout(() => { fail(new Error(`MCP server timed out after 15 seconds. ${stderr}`)); child.kill(); }, 15000);
  const send = message => {
    if (failure) throw failure;
    child.stdin.write(JSON.stringify({ jsonrpc: '2.0', ...message }) + '\n');
  };
  const request = (method, params) => new Promise((resolve, reject) => {
    if (failure) { reject(failure); return; }
    const current = ++id; pending.set(current, { resolve, reject, method });
    try { send({ id: current, method, params }); } catch (error) { fail(error); }
  });
  return {
    request,
    async initialize() {
      const initialized = await request('initialize', { protocolVersion: '2025-11-25', capabilities: {}, clientInfo: { name: 'inkbolt-mcpb', version: '1.0.0' } });
      assert.equal(initialized.protocolVersion, '2025-11-25');
      assert.equal(initialized.serverInfo.version, manifest.version, 'binary version must equal manifest version');
      send({ method: 'notifications/initialized' });
    },
    async listTools() {
      const tools = [], cursors = new Set();
      let cursor;
      do {
        const listed = await request('tools/list', cursor ? { cursor } : {});
        assert.ok(Array.isArray(listed.tools), 'tools/list must return tools');
        tools.push(...listed.tools);
        cursor = listed.nextCursor;
        if (cursor !== undefined) {
          assert.ok(typeof cursor === 'string' && cursor && !cursors.has(cursor) && cursors.size < 100, 'Invalid or repeating catalog cursor');
          cursors.add(cursor);
        }
      } while (cursor !== undefined);
      assert.ok(tools.length > 0, 'MCP server lists no tools');
      assert.equal(new Set(tools.map(tool => tool.name)).size, tools.length, 'duplicate live tool names');
      return tools;
    },
    async stop() {
      clearTimeout(timer);
      child.kill();
      await closed;
    }
  };
}
