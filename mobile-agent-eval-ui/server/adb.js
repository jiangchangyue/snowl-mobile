const { spawn } = require('child_process');

function getCommand(name, envKey) {
  return process.env[envKey] || name;
}

function runCommand(cmd, args = [], options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, args, {
      shell: false,
      windowsHide: true,
      ...options
    });

    let stdout = Buffer.alloc(0);
    let stderr = Buffer.alloc(0);

    child.stdout?.on('data', (chunk) => {
      stdout = Buffer.concat([stdout, Buffer.from(chunk)]);
    });

    child.stderr?.on('data', (chunk) => {
      stderr = Buffer.concat([stderr, Buffer.from(chunk)]);
    });

    child.on('error', reject);
    child.on('close', (code) => {
      if (code === 0) {
        resolve({ stdout, stderr, code });
      } else {
        reject(new Error(stderr.toString('utf8') || `${cmd} exited with code ${code}`));
      }
    });
  });
}

async function listAvds() {
  const emulatorBin = getCommand('emulator', 'ANDROID_EMULATOR_BIN');
  const { stdout } = await runCommand(emulatorBin, ['-list-avds']);
  return stdout
    .toString('utf8')
    .split(/\r?\n/)
    .map((x) => x.trim())
    .filter(Boolean);
}

async function listConnectedEmulators() {
  const adbBin = getCommand('adb', 'ADB_BIN');
  const { stdout } = await runCommand(adbBin, ['devices']);
  return stdout
    .toString('utf8')
    .split(/\r?\n/)
    .slice(1)
    .map((line) => line.trim())
    .filter((line) => line.startsWith('emulator-') && line.includes('\tdevice'))
    .map((line) => line.split('\t')[0]);
}

async function startEmulator(avdName, extraArgs = []) {
  const emulatorBin = getCommand('emulator', 'ANDROID_EMULATOR_BIN');
  const child = spawn(emulatorBin, ['-avd', avdName, ...extraArgs], {
    detached: true,
    stdio: 'ignore',
    windowsHide: false
  });
  child.unref();
  return { pid: child.pid };
}

async function waitForNewEmulatorSerial(beforeList = [], timeoutMs = 90000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const current = await listConnectedEmulators().catch(() => []);
    const diff = current.find((serial) => !beforeList.includes(serial));
    if (diff) return diff;
    await new Promise((r) => setTimeout(r, 2000));
  }
  throw new Error('等待新的模拟器设备连接超时，请检查 emulator/adb 是否可用。');
}

async function captureScreenshot(serial) {
  const adbBin = getCommand('adb', 'ADB_BIN');
  const { stdout } = await runCommand(adbBin, ['-s', serial, 'exec-out', 'screencap', '-p']);
  return stdout;
}

async function dumpXml(serial) {
  const adbBin = getCommand('adb', 'ADB_BIN');
  const { stdout } = await runCommand(adbBin, ['-s', serial, 'exec-out', 'uiautomator', 'dump', '/dev/tty']);
  const text = stdout.toString('utf8');
  const start = text.indexOf('<?xml');
  return start >= 0 ? text.slice(start) : text;
}

async function killEmulator(serial, pid) {
  const adbBin = getCommand('adb', 'ADB_BIN');
  if (serial) {
    try {
      await runCommand(adbBin, ['-s', serial, 'emu', 'kill']);
      return true;
    } catch {
      // fallback below
    }
  }

  if (pid) {
    try {
      process.kill(pid);
      return true;
    } catch {
      // ignore and fail below
    }
  }

  throw new Error('无法关闭模拟器：缺少可用的 serial 或 pid。');
}

module.exports = {
  listAvds,
  listConnectedEmulators,
  startEmulator,
  waitForNewEmulatorSerial,
  captureScreenshot,
  dumpXml,
  killEmulator
};
