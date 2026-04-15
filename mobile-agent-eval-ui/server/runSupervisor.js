const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const { resolveCombination, listSupportedCombinations } = require('./runCatalog');
const { buildRunCommand } = require('./snowlCommandBuilder');
const { ensureUiRequestManifest, buildConfigEcho, redactApiKey } = require('./uiRequestManifest');
const { readArtifacts } = require('./runArtifactReader');
const { inspectOutputDir, isDirectoryNonEmpty, isResumableRunDirectory } = require('./runResumeInspector');

function normalizeSerials(raw) {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => String(item || '').trim())
    .filter(Boolean)
    .filter((item, index, array) => array.indexOf(item) === index);
}

function isProcessRunning(pid) {
  if (!(Number(pid) > 0)) {
    return false;
  }
  try {
    process.kill(Number(pid), 0);
    return true;
  } catch {
    return false;
  }
}

function terminateProcess(pid, signal = 'SIGTERM') {
  if (!(Number(pid) > 0)) {
    return false;
  }
  if (process.platform !== 'win32') {
    try {
      process.kill(-Number(pid), signal);
      return true;
    } catch {
      // fallback below
    }
  }
  try {
    process.kill(Number(pid), signal);
    return true;
  } catch {
    return false;
  }
}

class RunSupervisor {
  constructor({
    repoRoot,
    store,
    resolveReadySlots
  }) {
    this.repoRoot = repoRoot;
    this.store = store;
    this.resolveReadySlots = resolveReadySlots;
    this.processes = new Map();
    this.bridgeLogDir = path.join(this.repoRoot, 'mobile-agent-eval-ui', 'server', '.bridge-state', 'logs');
  }

  listSupportedCombinations() {
    return listSupportedCombinations(this.repoRoot);
  }

  inspectOutputDir(input) {
    return inspectOutputDir({
      repoRoot: this.repoRoot,
      requestedOutputDir: input && (input.requestedOutputDir || input.outputDir),
      modelName: input && input.modelName,
      resolvedOutputDirName: input && input.resolvedOutputDirName
    });
  }

  startRun(input) {
    const unitId = String(input.unitId || '').trim();
    if (!unitId) {
      throw new Error('unitId 为必填项。');
    }

    const agent = String(input.agent || '').trim();
    const benchmark = String(input.benchmark || '').trim();
    const target = resolveCombination({ agent, benchmark });
    if (!target.supported) {
      const error = new Error(target.reason || '当前组合暂未实现。');
      error.statusCode = 501;
      error.payload = {
        supported: false,
        availability: target.availability || 'coming_soon',
        reason: target.reason || '当前组合暂未实现。'
      };
      throw error;
    }

    if (!(typeof input.outputDir === 'string' && input.outputDir.trim())) {
      throw new Error('output_dir 不能为空。');
    }

    const batchSize = Math.max(1, Number(input.batchSize) || 1);
    const readySlots = this.resolveReadySlots(unitId);
    const readySerials = readySlots.map((slot) => slot.serial);
    const requestedSerials = normalizeSerials(input.adbSerials);
    const adbSerials = requestedSerials.length > 0
      ? requestedSerials.filter((serial) => readySerials.includes(serial))
      : readySerials.slice(0, batchSize);

    if (adbSerials.length < batchSize) {
      throw new Error(
        `当前仅有 ${adbSerials.length} 个已校验的就绪设备 serial，可用数量少于 batch_size=${batchSize}。`
      );
    }

    const outputDirProbe = this.inspectOutputDir({
      outputDir: input.outputDir,
      requestedOutputDir: input.requestedOutputDir,
      modelName: input.modelName,
      resolvedOutputDirName: input.resolvedOutputDirName
    });
    if (outputDirProbe.incompatible) {
      throw new Error(
        `output_dir 已存在且不是可恢复的 snowl-mobile 运行目录：${outputDirProbe.outputDirAbs}`
      );
    }

    const command = buildRunCommand({
      repoRoot: this.repoRoot,
      configPath: target.configPath,
      modelName: input.modelName,
      baseUrl: input.baseUrl,
      apiKey: input.apiKey,
      maxSteps: input.maxSteps,
      batchSize,
      outputDir: input.requestedOutputDir || input.outputDir,
      resolvedOutputDirName: outputDirProbe.resolvedOutputDirName,
      adbSerials: adbSerials.slice(0, batchSize)
    });

    const runId = command.runId;
    const existingByUnit = this.store.getByUnitId(unitId);
    if (existingByUnit && this._descriptorIsActive(existingByUnit)) {
      throw new Error(`测试单元 ${unitId} 当前已有正在运行的真实评测，请先停止后再重新启动。`);
    }
    const existingByRun = this.store.getByRunId(runId);
    if (existingByRun && this._descriptorIsActive(existingByRun)) {
      throw new Error(`run_id=${runId} 当前已有正在运行的真实评测，请先停止后再重新启动。`);
    }

    if (fs.existsSync(command.resolvedOutputDirAbs)) {
      if (isDirectoryNonEmpty(command.resolvedOutputDirAbs) && !isResumableRunDirectory(command.resolvedOutputDirAbs)) {
        throw new Error(
          `output_dir 已存在且不是可恢复的 snowl-mobile 运行目录：${command.resolvedOutputDirAbs}`
        );
      }
    }

    const descriptor = {
      runId,
      unitId,
      agent,
      benchmark,
      backendAgentId: target.backendAgentId,
      backendBenchmarkId: target.backendBenchmarkId,
      configPath: target.configPath,
      resolvedConfigPath: command.resolvedConfigPath,
      modelName: String(input.modelName || '').trim(),
      baseUrl: String(input.baseUrl || '').trim(),
      apiKeyRedacted: redactApiKey(input.apiKey),
      maxSteps: Math.max(1, Number(input.maxSteps) || 1),
      batchSize,
      requestedOutputDir: String(input.requestedOutputDir || input.outputDir || '').trim(),
      resolvedOutputDirName: command.resolvedOutputDirName,
      outputDir: command.resolvedOutputDir,
      outputDirAbs: command.resolvedOutputDirAbs,
      adbSerials: adbSerials.slice(0, batchSize),
      commandPreview: command.commandPreview,
      bridgeStdoutPath: path.join(this.bridgeLogDir, `${runId}.stdout.log`),
      bridgeStderrPath: path.join(this.bridgeLogDir, `${runId}.stderr.log`),
      requestedAt: new Date().toISOString(),
      startedAt: new Date().toISOString(),
      finishedAt: null,
      processPid: null,
      exitCode: null,
      bridgeStatus: 'starting',
      stopRequestedAt: null
    };

    const env = {
      ...process.env,
      ...command.env
    };
    fs.mkdirSync(this.bridgeLogDir, { recursive: true });
    const stdoutStream = fs.createWriteStream(descriptor.bridgeStdoutPath, { flags: 'a' });
    const stderrStream = fs.createWriteStream(descriptor.bridgeStderrPath, { flags: 'a' });
    const child = spawn(command.command, command.args, {
      cwd: this.repoRoot,
      env,
      detached: process.platform !== 'win32',
      stdio: ['ignore', 'pipe', 'pipe']
    });
    child.stdout?.on('data', (chunk) => stdoutStream.write(chunk));
    child.stderr?.on('data', (chunk) => stderrStream.write(chunk));
    child.unref();

    descriptor.processPid = child.pid || null;
    descriptor.bridgeStatus = 'running';
    this.store.upsert(descriptor);
    this.processes.set(runId, child);
    this._attachChildLifecycle(runId, child, { stdoutStream, stderrStream });
    return this.getRunStateByRunId(runId);
  }

  stopRun({ unitId, runId }) {
    const descriptor = runId
      ? this.store.getByRunId(String(runId).trim())
      : this.store.getByUnitId(String(unitId || '').trim());
    if (!descriptor) {
      return null;
    }
    if (!this._descriptorIsActive(descriptor)) {
      const updated = {
        ...descriptor,
        bridgeStatus: descriptor.bridgeStatus === 'finished' ? 'finished' : 'stopped',
        finishedAt: descriptor.finishedAt || new Date().toISOString()
      };
      this.store.upsert(updated);
      return this._buildState(updated);
    }

    const updated = {
      ...descriptor,
      bridgeStatus: 'stopping',
      stopRequestedAt: new Date().toISOString()
    };
    this.store.upsert(updated);
    const pid = updated.processPid;
    if (!terminateProcess(pid, 'SIGTERM')) {
      throw new Error(`无法停止 run_id=${updated.runId}，没有可用的进程句柄。`);
    }
    setTimeout(() => {
      const latest = this.store.getByRunId(updated.runId);
      if (latest && this._descriptorIsActive(latest)) {
        terminateProcess(latest.processPid, 'SIGKILL');
      }
    }, 5000).unref?.();
    return this._buildState(updated);
  }

  clearUnitBinding(unitId) {
    return this.store.clearUnitBinding(unitId);
  }

  getRunStateByUnitId(unitId) {
    const descriptor = this.store.getByUnitId(unitId);
    return descriptor ? this._buildState(descriptor) : null;
  }

  getRunStateByRunId(runId) {
    const descriptor = this.store.getByRunId(runId);
    return descriptor ? this._buildState(descriptor) : null;
  }

  getRunConfigByUnitId(unitId) {
    const descriptor = this.store.getByUnitId(unitId);
    if (!descriptor) return null;
    const state = this._buildState(descriptor);
    return {
      runId: state.runId,
      unitId: state.unitId,
      outputDir: state.outputDir,
      outputDirAbs: state.outputDirAbs,
      configEcho: state.configEcho,
      configData: state.configData,
      outputDirProbe: state.outputDirProbe
    };
  }

  getRunConfigByRunId(runId) {
    const descriptor = this.store.getByRunId(runId);
    if (!descriptor) return null;
    const state = this._buildState(descriptor);
    return {
      runId: state.runId,
      unitId: state.unitId,
      outputDir: state.outputDir,
      outputDirAbs: state.outputDirAbs,
      configEcho: state.configEcho,
      configData: state.configData,
      outputDirProbe: state.outputDirProbe
    };
  }

  _attachChildLifecycle(runId, child, streams) {
    const closeStreams = () => {
      streams?.stdoutStream?.end();
      streams?.stderrStream?.end();
    };
    child.on('error', (error) => {
      const descriptor = this.store.getByRunId(runId);
      if (!descriptor) return;
      this.processes.delete(runId);
      closeStreams();
      this.store.upsert({
        ...descriptor,
        bridgeStatus: 'failed',
        finishedAt: new Date().toISOString(),
        exitCode: 1,
        lastError: String(error.message || error)
      });
    });

    child.on('exit', (code, signal) => {
      const descriptor = this.store.getByRunId(runId);
      if (!descriptor) return;
      this.processes.delete(runId);
      closeStreams();
      const stoppedByUser = Boolean(descriptor.stopRequestedAt);
      let nextStatus = 'finished';
      if (stoppedByUser) {
        nextStatus = 'stopped';
      } else if (signal || Number(code || 0) !== 0) {
        nextStatus = 'failed';
      }
      this.store.upsert({
        ...descriptor,
        bridgeStatus: nextStatus,
        finishedAt: new Date().toISOString(),
        exitCode: code === null ? null : code
      });
    });
  }

  _descriptorIsActive(descriptor) {
    if (!descriptor || !(Number(descriptor.processPid) > 0)) {
      return false;
    }
    if (this.processes.has(descriptor.runId)) {
      return true;
    }
    return isProcessRunning(descriptor.processPid);
  }

  _buildState(descriptor) {
    const processActive = this._descriptorIsActive(descriptor);
    const initialArtifacts = readArtifacts(descriptor, { processActive });
    const backendStatus = initialArtifacts.summary && initialArtifacts.summary.status
      ? String(initialArtifacts.summary.status)
      : 'NOT_STARTED';
    let normalizedBridgeStatus = descriptor.bridgeStatus;
    if (processActive) {
      normalizedBridgeStatus = descriptor.bridgeStatus === 'stopping' ? 'stopping' : 'running';
    } else if (descriptor.bridgeStatus === 'running' || descriptor.bridgeStatus === 'starting') {
      normalizedBridgeStatus = backendStatus === 'COMPLETED' ? 'finished' : 'stopped';
    }
    const normalized = {
      ...descriptor,
      bridgeStatus: normalizedBridgeStatus
    };
    if (fs.existsSync(normalized.outputDirAbs)) {
      ensureUiRequestManifest(normalized.outputDirAbs, normalized);
    }
    const artifacts = readArtifacts(normalized, { processActive });
    const outputDirProbe = inspectOutputDir({
      repoRoot: this.repoRoot,
      requestedOutputDir: normalized.requestedOutputDir || normalized.outputDir,
      modelName: normalized.modelName,
      resolvedOutputDirName: normalized.resolvedOutputDirName || normalized.outputDir
    });

    let status = 'idle';
    if (normalized.bridgeStatus === 'running' || normalized.bridgeStatus === 'starting' || normalized.bridgeStatus === 'stopping') {
      status = 'running';
    } else if (normalized.bridgeStatus === 'finished') {
      status = 'done';
    } else if (normalized.bridgeStatus === 'failed' || normalized.bridgeStatus === 'stopped') {
      status = 'stopped';
    }

    return {
      unitId: normalized.unitId || '',
      runId: normalized.runId,
      status,
      bridgeStatus: normalized.bridgeStatus,
      backendStatus,
      supported: true,
      outputDir: normalized.outputDir,
      outputDirAbs: normalized.outputDirAbs,
      requestedOutputDir: normalized.requestedOutputDir || '',
      resolvedOutputDirName: normalized.resolvedOutputDirName || '',
      agent: normalized.agent,
      benchmark: normalized.benchmark,
      batchSize: normalized.batchSize,
      maxSteps: normalized.maxSteps,
      modelName: normalized.modelName,
      adbSerials: normalized.adbSerials,
      processId: normalized.processPid,
      processActive,
      exitCode: normalized.exitCode,
      requestedAt: normalized.requestedAt,
      startedAt: normalized.startedAt,
      finishedAt: normalized.finishedAt,
      commandPreview: normalized.commandPreview,
      configEcho: artifacts.configEcho || buildConfigEcho(normalized),
      currentTaskTitle: artifacts.activeTrials && artifacts.activeTrials[0] && artifacts.activeTrials[0].instruction
        ? String(artifacts.activeTrials[0].instruction)
        : '--',
      activeApp: '--',
      progress: artifacts.progress,
      metrics: artifacts.metrics,
      logs: artifacts.structuredLogs,
      terminalLines: artifacts.terminalLines,
      summaryData: artifacts.summaryData,
      configData: artifacts.configData,
      outputDirProbe,
      backendSummary: artifacts.summary,
      backendPlan: artifacts.plan,
      activeTrials: artifacts.activeTrials
    };
  }
}

module.exports = {
  RunSupervisor
};
