const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

function makeCrcTable() {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n += 1) {
    let c = n;
    for (let k = 0; k < 8; k += 1) {
      c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
    }
    table[n] = c >>> 0;
  }
  return table;
}

const CRC_TABLE = makeCrcTable();

function crc32(buffer) {
  let crc = 0xffffffff;
  for (const byte of buffer) {
    crc = CRC_TABLE[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function getDosDateTime(date = new Date()) {
  const year = Math.max(1980, date.getFullYear());
  const dosTime = ((date.getHours() & 0x1f) << 11) | ((date.getMinutes() & 0x3f) << 5) | ((Math.floor(date.getSeconds() / 2)) & 0x1f);
  const dosDate = (((year - 1980) & 0x7f) << 9) | (((date.getMonth() + 1) & 0x0f) << 5) | (date.getDate() & 0x1f);
  return { dosDate, dosTime };
}

function createSingleFileZip(filename, fileBuffer) {
  const nameBuffer = Buffer.from(filename, 'utf8');
  const dataBuffer = Buffer.isBuffer(fileBuffer) ? fileBuffer : Buffer.from(fileBuffer);
  const { dosDate, dosTime } = getDosDateTime();
  const crc = crc32(dataBuffer);

  const localHeader = Buffer.alloc(30 + nameBuffer.length);
  let o = 0;
  localHeader.writeUInt32LE(0x04034b50, o); o += 4;
  localHeader.writeUInt16LE(20, o); o += 2;
  localHeader.writeUInt16LE(0, o); o += 2;
  localHeader.writeUInt16LE(0, o); o += 2;
  localHeader.writeUInt16LE(dosTime, o); o += 2;
  localHeader.writeUInt16LE(dosDate, o); o += 2;
  localHeader.writeUInt32LE(crc, o); o += 4;
  localHeader.writeUInt32LE(dataBuffer.length, o); o += 4;
  localHeader.writeUInt32LE(dataBuffer.length, o); o += 4;
  localHeader.writeUInt16LE(nameBuffer.length, o); o += 2;
  localHeader.writeUInt16LE(0, o); o += 2;
  nameBuffer.copy(localHeader, o);

  const centralHeader = Buffer.alloc(46 + nameBuffer.length);
  o = 0;
  centralHeader.writeUInt32LE(0x02014b50, o); o += 4;
  centralHeader.writeUInt16LE(20, o); o += 2;
  centralHeader.writeUInt16LE(20, o); o += 2;
  centralHeader.writeUInt16LE(0, o); o += 2;
  centralHeader.writeUInt16LE(0, o); o += 2;
  centralHeader.writeUInt16LE(dosTime, o); o += 2;
  centralHeader.writeUInt16LE(dosDate, o); o += 2;
  centralHeader.writeUInt32LE(crc, o); o += 4;
  centralHeader.writeUInt32LE(dataBuffer.length, o); o += 4;
  centralHeader.writeUInt32LE(dataBuffer.length, o); o += 4;
  centralHeader.writeUInt16LE(nameBuffer.length, o); o += 2;
  centralHeader.writeUInt16LE(0, o); o += 2;
  centralHeader.writeUInt16LE(0, o); o += 2;
  centralHeader.writeUInt16LE(0, o); o += 2;
  centralHeader.writeUInt16LE(0, o); o += 2;
  centralHeader.writeUInt32LE(0, o); o += 4;
  centralHeader.writeUInt32LE(0, o); o += 4;
  nameBuffer.copy(centralHeader, o);

  const endRecord = Buffer.alloc(22);
  o = 0;
  endRecord.writeUInt32LE(0x06054b50, o); o += 4;
  endRecord.writeUInt16LE(0, o); o += 2;
  endRecord.writeUInt16LE(0, o); o += 2;
  endRecord.writeUInt16LE(1, o); o += 2;
  endRecord.writeUInt16LE(1, o); o += 2;
  endRecord.writeUInt32LE(centralHeader.length, o); o += 4;
  endRecord.writeUInt32LE(localHeader.length + dataBuffer.length, o); o += 4;
  endRecord.writeUInt16LE(0, o);

  return Buffer.concat([localHeader, dataBuffer, centralHeader, endRecord]);
}

function streamDirectoryZip(directoryPath, response, downloadName) {
  if (!fs.existsSync(directoryPath) || !fs.statSync(directoryPath).isDirectory()) {
    throw new Error(`无法导出不存在的目录：${directoryPath}`);
  }
  const parentDir = path.dirname(directoryPath);
  const basename = path.basename(directoryPath);
  const child = spawn('/usr/bin/zip', ['-r', '-q', '-', basename], {
    cwd: parentDir,
    stdio: ['ignore', 'pipe', 'pipe']
  });

  let stderrText = '';
  child.stderr.on('data', (chunk) => {
    stderrText += String(chunk || '');
  });

  response.setHeader('Content-Type', 'application/zip');
  response.setHeader('Content-Disposition', `attachment; filename="${downloadName}"`);
  child.stdout.pipe(response);

  child.on('error', (error) => {
    if (!response.headersSent) {
      response.status(500).json({ error: '打包 output_dir 失败。', detail: String(error.message || error) });
      return;
    }
    response.destroy(error);
  });

  child.on('exit', (code) => {
    if (Number(code || 0) === 0) {
      return;
    }
    const error = new Error(stderrText.trim() || `zip exited with code ${code}`);
    if (!response.headersSent) {
      response.status(500).json({ error: '打包 output_dir 失败。', detail: String(error.message || error) });
      return;
    }
    response.destroy(error);
  });
}

module.exports = {
  createSingleFileZip,
  streamDirectoryZip
};
