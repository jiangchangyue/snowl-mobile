const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const { resolveManagedOutputDir } = require('./outputDirResolver');

function resolveOutputDir(repoRoot, outputDir, modelName, resolvedOutputDirName) {
  if (!outputDir || !String(outputDir).trim()) {
    throw new Error('output_dir 不能为空。');
  }
  return resolveManagedOutputDir(repoRoot, {
    requestedOutputDir: outputDir,
    modelName,
    resolvedOutputDirName
  });
}

function resolveRunId(outputDir) {
  return path.basename(path.resolve(outputDir));
}

function resolveCliInvocation(repoRoot) {
  const explicitBin = String(process.env.SNOWL_MOBILE_BIN || '').trim();
  if (explicitBin) {
    return {
      command: explicitBin,
      argsPrefix: ['run'],
      env: {}
    };
  }
  const discoveredBin = spawnSync('which', ['snowl-mobile'], { encoding: 'utf8' });
  const snowlMobileBin = discoveredBin.status === 0 ? String(discoveredBin.stdout || '').trim() : '';
  if (snowlMobileBin) {
    return {
      command: snowlMobileBin,
      argsPrefix: ['run'],
      env: {}
    };
  }
  const pythonBin = String(process.env.SNOWL_MOBILE_PYTHON || 'python3').trim() || 'python3';
  const pythonPathEntries = [path.join(repoRoot, 'src')];
  if (process.env.PYTHONPATH) {
    pythonPathEntries.push(process.env.PYTHONPATH);
  }
  return {
    command: pythonBin,
    argsPrefix: ['-m', 'snowl_mobile.cli.main', 'run'],
    env: {
      PYTHONPATH: pythonPathEntries.join(path.delimiter)
    }
  };
}

function redactArgs(args) {
  const redacted = [];
  for (let index = 0; index < args.length; index += 1) {
    const value = args[index];
    redacted.push(value);
    if (value === '--api-key' && index + 1 < args.length) {
      redacted.push('<redacted>');
      index += 1;
    }
  }
  return redacted;
}

function buildRunCommand({
  repoRoot,
  configPath,
  modelName,
  baseUrl,
  apiKey,
  maxSteps,
  batchSize,
  outputDir,
  resolvedOutputDirName,
  adbSerials
}) {
  const resolvedConfigPath = path.resolve(repoRoot, configPath);
  if (!fs.existsSync(resolvedConfigPath)) {
    throw new Error(`未找到后端运行配置文件：${resolvedConfigPath}`);
  }
  const resolvedOutput = resolveOutputDir(repoRoot, outputDir, modelName, resolvedOutputDirName);
  const invocation = resolveCliInvocation(repoRoot);
  const args = [...invocation.argsPrefix, resolvedConfigPath];

  if (modelName && String(modelName).trim()) {
    args.push('--model-name', String(modelName).trim());
  }
  if (baseUrl && String(baseUrl).trim()) {
    args.push('--base-url', String(baseUrl).trim());
  }
  if (apiKey && String(apiKey).trim()) {
    args.push('--api-key', String(apiKey).trim());
  }

  args.push('--max-steps', String(Math.max(1, Number(maxSteps) || 1)));
  args.push('--batch-size', String(Math.max(1, Number(batchSize) || 1)));
  args.push('--device-mode', 'existing_device');

  for (const serial of adbSerials) {
    args.push('--adb-serial', serial);
  }

  args.push('--output-dir', resolvedOutput.outputDirCliArg);

  const previewArgs = redactArgs(args);
  return {
    command: invocation.command,
    args,
    env: invocation.env,
    resolvedConfigPath,
    resolvedOutputDir: resolvedOutput.outputDirCliArg,
    resolvedOutputDirAbs: resolvedOutput.outputDirAbs,
    resolvedOutputDirRelative: resolvedOutput.outputDirRelative,
    resolvedOutputDirName: resolvedOutput.resolvedOutputDirName,
    requestedOutputDir: resolvedOutput.requestedOutputDir,
    runId: resolveRunId(resolvedOutput.outputDirCliArg),
    commandPreview: [invocation.command, ...previewArgs].join(' ')
  };
}

module.exports = {
  buildRunCommand,
  resolveOutputDir,
  resolveRunId
};
