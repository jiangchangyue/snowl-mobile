const { spawn } = require('child_process');

function run(command, args, name, color) {
  const child = spawn(command, args, {
    stdio: 'pipe',
    shell: process.platform === 'win32'
  });

  const prefix = `\x1b[${color}m[${name}]\x1b[0m`;

  child.stdout.on('data', (data) => {
    process.stdout.write(`${prefix} ${data}`);
  });

  child.stderr.on('data', (data) => {
    process.stderr.write(`${prefix} ${data}`);
  });

  child.on('exit', (code, signal) => {
    if (signal) {
      process.stdout.write(`${prefix} exited with signal ${signal}\n`);
    } else if (code !== 0) {
      process.stdout.write(`${prefix} exited with code ${code}\n`);
      shutdown(code || 1);
    }
  });

  return child;
}

const npmCmd = process.platform === 'win32' ? 'npm.cmd' : 'npm';
const server = run(npmCmd, ['run', 'server'], 'server', '36');
const client = run(npmCmd, ['run', 'client'], 'client', '35');

let closed = false;
function shutdown(code = 0) {
  if (closed) return;
  closed = true;
  for (const child of [server, client]) {
    if (child && !child.killed) {
      try {
        child.kill('SIGTERM');
      } catch {}
    }
  }
  setTimeout(() => process.exit(code), 300);
}

process.on('SIGINT', () => shutdown(0));
process.on('SIGTERM', () => shutdown(0));
