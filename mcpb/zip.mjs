// ZIP helpers adapted from skulitom's MIT-licensed distribution scripts.
// No external package or runtime is bundled by this module.
import { createHash } from 'node:crypto';
import zlib from 'node:zlib';
export const sha256 = data => createHash('sha256').update(data).digest('hex');
const table = Uint32Array.from({ length: 256 }, (_, value) => {
  for (let bit = 0; bit < 8; bit++) value = (value >>> 1) ^ ((value & 1) ? 0xedb88320 : 0);
  return value >>> 0;
});
const checksum = zlib.crc32 ?? (data => {
  let value = 0xffffffff;
  for (const byte of data) value = table[(value ^ byte) & 255] ^ (value >>> 8);
  return (value ^ 0xffffffff) >>> 0;
});

// Reads a ZIP32 archive with stored or deflated entries; each entry is checked against its CRC when read.
export function readZip(buffer) {
  if (buffer.length < 22) throw new Error('Not a ZIP archive: too short');
  let end = buffer.length - 22;
  const floor = Math.max(0, end - 65535);
  while (end >= floor && buffer.readUInt32LE(end) !== 0x06054b50) end--;
  if (end < floor) throw new Error('Not a ZIP archive: no end-of-central-directory record');
  if (end + 22 + buffer.readUInt16LE(end + 20) !== buffer.length || buffer.readUInt32LE(end + 4) !== 0) throw new Error('Unsupported ZIP framing or multiple disks');
  const count = buffer.readUInt16LE(end + 10), entries = new Map();
  let at = buffer.readUInt32LE(end + 16);
  if (buffer.readUInt16LE(end + 8) !== count || at + buffer.readUInt32LE(end + 12) !== end) throw new Error('Damaged ZIP directory bounds');
  if (count === 0xffff || at === 0xffffffff) throw new Error('ZIP64 archives are not supported');
  for (let i = 0; i < count; i++) {
    if (at + 46 > end) throw new Error('Truncated ZIP central directory');
    if (buffer.readUInt32LE(at) !== 0x02014b50) throw new Error('Damaged ZIP central directory');
    const method = buffer.readUInt16LE(at + 10), crc = buffer.readUInt32LE(at + 16), packed = buffer.readUInt32LE(at + 20), size = buffer.readUInt32LE(at + 24);
    const nameLength = buffer.readUInt16LE(at + 28), local = buffer.readUInt32LE(at + 42), name = buffer.toString('utf8', at + 46, at + 46 + nameLength);
    const flags = buffer.readUInt16LE(at + 8);
    if (flags & ~0x800) throw new Error('Unsupported ZIP flags');
    if (size > 512 * 1024 * 1024) throw new Error('ZIP entry exceeds 512 MiB budget');
    if (entries.has(name)) throw new Error(`Duplicate ZIP entry: ${name}`);
    at += 46 + nameLength + buffer.readUInt16LE(at + 30) + buffer.readUInt16LE(at + 32);
    if (at > end || local + 30 > buffer.readUInt32LE(end + 16)) throw new Error('Damaged ZIP entry bounds');
    entries.set(name, { size, read() {
      if (buffer.readUInt32LE(local) !== 0x04034b50 || buffer.readUInt16LE(local + 6) !== flags || buffer.readUInt16LE(local + 8) !== method) throw new Error(`Damaged ZIP local header: ${name}`);
      if (buffer.toString('utf8', local + 30, local + 30 + buffer.readUInt16LE(local + 26)) !== name) throw new Error('ZIP entry names disagree');
      if (method !== 0 && method !== 8) throw new Error(`ZIP entry ${name} uses unsupported compression method ${method}`);
      const start = local + 30 + buffer.readUInt16LE(local + 26) + buffer.readUInt16LE(local + 28), raw = buffer.subarray(start, start + packed);
      if (start + packed > buffer.readUInt32LE(end + 16)) throw new Error(`Truncated ZIP entry: ${name}`);
      const data = method === 0 ? Buffer.from(raw) : zlib.inflateRawSync(raw, { maxOutputLength: Math.max(size, 1) });
      if (data.length !== size || checksum(data) !== crc) throw new Error(`ZIP entry ${name} is damaged`);
      return data;
    } });
  }
  if (at !== end) throw new Error('Unexpected ZIP central directory data');
  return entries;
}
// Deflated ZIP32 with a fixed timestamp and no host metadata, so the same files always give the same bytes
// (for one zlib; the build repacks under the pinned runtime where it can).
export function writeZip(files, { date = new Date(Date.UTC(1980, 0, 1)) } = {}) {
  if (files.size >= 65535) throw new Error('ZIP32 supports fewer than 65,535 entries');
  const time = date.getUTCHours() << 11 | date.getUTCMinutes() << 5 | date.getUTCSeconds() >> 1;
  const day = Math.max(0, date.getUTCFullYear() - 1980) << 9 | (date.getUTCMonth() + 1) << 5 | date.getUTCDate();
  const local = [], central = [];
  let offset = 0;
  for (const [filename, data] of [...files].sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)) {
    if (!/^[\x20-\x7e]+$/.test(filename) || /[\\:*?"<>|]/.test(filename)) throw new Error(`ZIP entry names must be plain ASCII with forward slashes: ${filename}`);
    const deflated = zlib.deflateRawSync(data, { level: 9 }), method = deflated.length < data.length ? 8 : 0, body = method ? deflated : data;
    const name = Buffer.from(filename), crc = checksum(data), header = Buffer.alloc(30), entry = Buffer.alloc(46);
    header.writeUInt32LE(0x04034b50, 0); header.writeUInt16LE(20, 4); header.writeUInt16LE(method, 8); header.writeUInt16LE(time, 10); header.writeUInt16LE(day, 12);
    header.writeUInt32LE(crc, 14); header.writeUInt32LE(body.length, 18); header.writeUInt32LE(data.length, 22); header.writeUInt16LE(name.length, 26);
    entry.writeUInt32LE(0x02014b50, 0); entry.writeUInt16LE(20, 4); entry.writeUInt16LE(20, 6); entry.writeUInt16LE(method, 10); entry.writeUInt16LE(time, 12); entry.writeUInt16LE(day, 14);
    entry.writeUInt32LE(crc, 16); entry.writeUInt32LE(body.length, 20); entry.writeUInt32LE(data.length, 24); entry.writeUInt16LE(name.length, 28); entry.writeUInt32LE(offset, 42);
    local.push(header, name, body); central.push(entry, name); offset += 30 + name.length + body.length;
  }
  const directory = Buffer.concat(central), end = Buffer.alloc(22);
  if (offset + directory.length + 22 > 0xffffffff) throw new Error('Archive exceeds the ZIP32 byte budget');
  end.writeUInt32LE(0x06054b50, 0); end.writeUInt16LE(files.size, 8); end.writeUInt16LE(files.size, 10); end.writeUInt32LE(directory.length, 12); end.writeUInt32LE(offset, 16);
  return Buffer.concat([...local, directory, end]);
}
