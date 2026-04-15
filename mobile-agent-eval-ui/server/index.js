const express = require('express');
const cors = require('cors');
const path = require('path');
const {
  listAvds,
  listConnectedEmulators,
  startEmulator,
  waitForNewEmulatorSerial,
  captureScreenshot,
  dumpXml,
  killEmulator
} = require('./adb');
const { RunStateStore } = require('./runStateStore');
const { RunSupervisor } = require('./runSupervisor');
const { streamDirectoryZip } = require('./zip');

const app = express();
const PORT = Number(process.env.PORT || 8787);

app.use(cors());
app.use(express.json());

const unitEmulatorMap = new Map();
const repoRoot = path.resolve(__dirname, '..', '..');
const runStateStore = new RunStateStore({
  stateFile: path.join(__dirname, '.bridge-state', 'runs.json')
});

function resolveReadySlots(unitId) {
  const state = getOrCreateUnitState(unitId);
  return state.slots
    .filter((slot) => slot.emulatorStatus === 'ready' && slot.serial)
    .sort((left, right) => left.slotIndex - right.slotIndex);
}

const runSupervisor = new RunSupervisor({
  repoRoot,
  store: runStateStore,
  resolveReadySlots
});

function createEmptySlot(slotIndex) {
  return {
    slotIndex,
    selectedAvd: '',
    serial: '',
    emulatorPid: null,
    emulatorStatus: 'idle',
    lastError: '',
    imageTick: Date.now(),
    xmlText: '',
    grpcPort: null
  };
}

function getOrCreateUnitState(unitId) {
  if (!unitEmulatorMap.has(unitId)) {
    unitEmulatorMap.set(unitId, {
      unitId,
      slots: [createEmptySlot(0)]
    });
  }
  return unitEmulatorMap.get(unitId);
}

function ensureSlot(unitId, slotIndex) {
  const state = getOrCreateUnitState(unitId);
  while (state.slots.length <= slotIndex) {
    state.slots.push(createEmptySlot(state.slots.length));
  }
  return state;
}

function visibleState(state) {
  return {
    unitId: state.unitId,
    slots: state.slots
  };
}

function listTrackedConnectedDevices(serials) {
  const ownership = new Map();
  for (const [unitId, state] of unitEmulatorMap.entries()) {
    for (const slot of state.slots) {
      if (!slot.serial) continue;
      ownership.set(slot.serial, {
        serial: slot.serial,
        unitId,
        slotIndex: slot.slotIndex,
        selectedAvd: slot.selectedAvd || '',
        emulatorPid: slot.emulatorPid || null,
        emulatorStatus: slot.emulatorStatus,
        grpcPort: slot.grpcPort || null
      });
    }
  }

  return serials.map((serial) => ownership.get(serial) || {
    serial,
    unitId: null,
    slotIndex: null,
    selectedAvd: '',
    emulatorPid: null,
    emulatorStatus: 'ready',
    grpcPort: null
  });
}

function isAvdOccupied(avdName, currentUnitId, currentSlotIndex) {
  for (const [unitId, state] of unitEmulatorMap.entries()) {
    for (const slot of state.slots) {
      if (slot.selectedAvd !== avdName) continue;
      if (!(slot.emulatorStatus === 'ready' || slot.emulatorStatus === 'starting')) continue;
      if (unitId === currentUnitId && slot.slotIndex === currentSlotIndex) continue;
      return true;
    }
  }
  return false;
}

async function stopAndClearUnit(unitId) {
  const state = getOrCreateUnitState(unitId);
  for (const slot of state.slots) {
    if (slot.serial || slot.emulatorPid) {
      try {
        await killEmulator(slot.serial, slot.emulatorPid);
      } catch {
        // ignore cleanup failures during reset
      }
    }
  }
  unitEmulatorMap.set(unitId, { unitId, slots: [createEmptySlot(0)] });
  return true;
}

app.get('/api/health', (_req, res) => {
  res.json({ ok: true });
});

app.get('/api/runs/catalog', (_req, res) => {
  res.json(runSupervisor.listSupportedCombinations());
});

app.post('/api/runs/output-dir/inspect', (req, res) => {
  const { outputDir, modelName, resolvedOutputDirName } = req.body || {};
  if (!outputDir || !String(outputDir).trim()) {
    return res.status(400).json({ error: 'output_dir 不能为空。' });
  }
  if (!modelName || !String(modelName).trim()) {
    return res.status(400).json({ error: 'modelName 不能为空。' });
  }
  try {
    const probe = runSupervisor.inspectOutputDir({
      outputDir,
      modelName,
      resolvedOutputDirName
    });
    res.json(probe);
  } catch (error) {
    res.status(500).json({
      error: '检查 output_dir 失败。',
      detail: String(error.message || error)
    });
  }
});

app.get('/api/emulators/avds', async (_req, res) => {
  try {
    const avds = await listAvds();
    res.json({ avds });
  } catch (error) {
    res.status(500).json({
      error: '无法列出本机已创建的 Android 模拟器。请确认 emulator 命令可直接在终端运行，或设置 ANDROID_EMULATOR_BIN 环境变量。',
      detail: String(error.message || error)
    });
  }
});

app.get('/api/emulators/connected', async (_req, res) => {
  try {
    const serials = await listConnectedEmulators();
    res.json({ devices: listTrackedConnectedDevices(serials) });
  } catch (error) {
    res.status(500).json({
      error: '无法查询当前已连接的模拟器设备。',
      detail: String(error.message || error)
    });
  }
});

app.post('/api/emulators/select', (req, res) => {
  const { unitId, slotIndex, avdName } = req.body || {};
  if (!unitId || typeof slotIndex !== 'number' || !avdName) {
    return res.status(400).json({ error: 'unitId、slotIndex 和 avdName 为必填项。' });
  }
  if (isAvdOccupied(avdName, unitId, slotIndex)) {
    return res.status(400).json({ error: `AVD ${avdName} 已被其他已启动槽位占用。` });
  }
  const state = ensureSlot(unitId, slotIndex);
  state.slots[slotIndex].selectedAvd = avdName;
  state.slots[slotIndex].lastError = '';
  res.json(visibleState(state));
});

app.post('/api/emulators/start', async (req, res) => {
  const { unitId, slotIndex } = req.body || {};
  if (!unitId || typeof slotIndex !== 'number') {
    return res.status(400).json({ error: 'unitId 和 slotIndex 为必填项。' });
  }

  const state = ensureSlot(unitId, slotIndex);
  const slot = state.slots[slotIndex];
  if (!slot.selectedAvd) {
    return res.status(400).json({ error: '请先为该槽位选择一个 AVD。' });
  }
  if (isAvdOccupied(slot.selectedAvd, unitId, slotIndex)) {
    return res.status(400).json({ error: `AVD ${slot.selectedAvd} 已被其他已启动槽位占用。` });
  }

  try {
    slot.emulatorStatus = 'starting';
    slot.lastError = '';
    const before = await listConnectedEmulators().catch(() => []);

    // AndroidWorld 模拟器需要额外参数：-no-snapshot -grpc <port>，端口从 8554 递增
    let extraArgs = [];
    if (/androidworld/i.test(slot.selectedAvd)) {
      const usedPorts = new Set();
      for (const [, uState] of unitEmulatorMap.entries()) {
        for (const s of uState.slots) {
          if (s.grpcPort) usedPorts.add(s.grpcPort);
        }
      }
      let port = 8554;
      while (usedPorts.has(port)) port++;
      extraArgs = ['-no-snapshot', '-grpc', String(port)];
      slot.grpcPort = port;
    }

    const { pid } = await startEmulator(slot.selectedAvd, extraArgs);
    slot.emulatorPid = pid || null;
    slot.serial = await waitForNewEmulatorSerial(before, 90000);
    slot.emulatorStatus = 'ready';
    slot.imageTick = Date.now();
    res.json(visibleState(state));
  } catch (error) {
    slot.emulatorStatus = 'error';
    slot.lastError = String(error.message || error);
    res.status(500).json({ error: '启动模拟器失败。', detail: slot.lastError });
  }
});

app.post('/api/emulators/stop', async (req, res) => {
  const { unitId, slotIndex } = req.body || {};
  if (!unitId || typeof slotIndex !== 'number') {
    return res.status(400).json({ error: 'unitId 和 slotIndex 为必填项。' });
  }

  const state = ensureSlot(unitId, slotIndex);
  const slot = state.slots[slotIndex];

  try {
    if (slot.serial || slot.emulatorPid) {
      await killEmulator(slot.serial, slot.emulatorPid);
    }
    state.slots[slotIndex] = {
      ...createEmptySlot(slotIndex),
      selectedAvd: slot.selectedAvd,
      emulatorStatus: 'stopped'
    };
    res.json(visibleState(state));
  } catch (error) {
    slot.emulatorStatus = 'error';
    slot.lastError = String(error.message || error);
    res.status(500).json({ error: '关闭模拟器失败。', detail: slot.lastError });
  }
});

app.post('/api/units/reset', async (req, res) => {
  const { unitId } = req.body || {};
  if (!unitId) {
    return res.status(400).json({ error: 'unitId 为必填项。' });
  }
  await stopAndClearUnit(unitId);
  res.json({ ok: true });
});

app.get('/api/emulators/:unitId/status', (req, res) => {
  const state = getOrCreateUnitState(req.params.unitId);
  res.json(visibleState(state));
});

app.get('/api/emulators/:unitId/slots/:slotIndex/screenshot', async (req, res) => {
  const state = ensureSlot(req.params.unitId, Number(req.params.slotIndex));
  const slot = state.slots[Number(req.params.slotIndex)];
  if (!slot.serial) return res.status(404).json({ error: '该槽位尚未绑定已启动的模拟器。' });

  try {
    const img = await captureScreenshot(slot.serial);
    slot.imageTick = Date.now();
    res.setHeader('Content-Type', 'image/png');
    res.send(img);
  } catch (error) {
    res.status(500).json({ error: '抓取模拟器截图失败。', detail: String(error.message || error) });
  }
});

app.get('/api/emulators/:unitId/slots/:slotIndex/xml', async (req, res) => {
  const state = ensureSlot(req.params.unitId, Number(req.params.slotIndex));
  const slot = state.slots[Number(req.params.slotIndex)];
  if (!slot.serial) return res.status(404).json({ error: '该槽位尚未绑定已启动的模拟器。' });

  try {
    const xml = await dumpXml(slot.serial);
    slot.xmlText = xml;
    res.type('text/plain').send(xml);
  } catch (error) {
    res.status(500).json({ error: '抓取 XML 失败。', detail: String(error.message || error) });
  }
});

app.post('/api/runs/start', (req, res) => {
  const {
    unitId,
    agent,
    benchmark,
    batchSize,
    outputDir,
    requestedOutputDir,
    resolvedOutputDirName,
    maxSteps,
    modelName,
    baseUrl,
    apiKey,
    adbSerials
  } = req.body || {};
  if (!outputDir || !String(outputDir).trim()) {
    return res.status(400).json({ error: 'output_dir 不能为空。' });
  }
  if (!modelName || !String(modelName).trim()) {
    return res.status(400).json({ error: 'modelName 不能为空。output_dir 需要基于 modelName 拼接真实目录名。' });
  }
  if (benchmark === 'AutoArena') {
    return res.status(501).json({
      error: 'AutoArena 当前仅保留前端入口，真实后端运行能力暂未实现。',
      availability: 'coming_soon'
    });
  }
  const readyCount = resolveReadySlots(unitId).length;
  if (readyCount < Number(batchSize || 1)) {
    return res.status(400).json({ error: `当前仅有 ${readyCount} 个模拟器槽位已就绪，少于 batch_size=${batchSize}。请先启动足够数量的模拟器。` });
  }
  try {
    const run = runSupervisor.startRun({
      unitId,
      agent,
      benchmark,
      batchSize,
      outputDir,
      requestedOutputDir,
      resolvedOutputDirName,
      maxSteps,
      modelName,
      baseUrl,
      apiKey,
      adbSerials
    });
    res.json(run);
  } catch (error) {
    const statusCode = Number(error.statusCode || 500);
    res.status(statusCode).json({
      error: statusCode === 501 ? '当前组合暂未实现真实后端运行。' : '启动评测失败。',
      detail: String(error.message || error),
      ...(error.payload && typeof error.payload === 'object' ? error.payload : {})
    });
  }
});

app.post('/api/runs/stop', (req, res) => {
  const { unitId, runId } = req.body || {};
  let run = null;
  try {
    run = runSupervisor.stopRun({ unitId, runId });
  } catch (error) {
    return res.status(500).json({ error: '停止评测失败。', detail: String(error.message || error) });
  }
  if (!run) return res.status(404).json({ error: '未找到对应测试单元的运行状态。' });
  res.json(run);
});

app.post('/api/runs/reset', (req, res) => {
  const { unitId } = req.body || {};
  const state = runSupervisor.getRunStateByUnitId(unitId);
  if (state && state.processActive) {
    return res.status(409).json({ error: '该测试单元仍有真实评测进程在运行，请先停止后再重置。' });
  }
  runSupervisor.clearUnitBinding(unitId);
  res.json({ ok: true });
});

app.get('/api/runs/:unitId/state', (req, res) => {
  const run = runSupervisor.getRunStateByUnitId(req.params.unitId);
  if (!run) return res.json(null);
  res.json(run);
});

app.get('/api/runs/:unitId/config', (req, res) => {
  const data = runSupervisor.getRunConfigByUnitId(req.params.unitId);
  if (!data) return res.status(404).json({ error: '未找到对应测试单元的真实运行配置。' });
  res.json(data);
});

app.get('/api/runs/id/:runId/state', (req, res) => {
  const run = runSupervisor.getRunStateByRunId(req.params.runId);
  if (!run) return res.json(null);
  res.json(run);
});

app.get('/api/runs/id/:runId/config', (req, res) => {
  const data = runSupervisor.getRunConfigByRunId(req.params.runId);
  if (!data) return res.status(404).json({ error: '未找到对应 run_id 的真实运行配置。' });
  res.json(data);
});

app.get('/api/runs/:unitId/export', (req, res) => {
  const run = runSupervisor.getRunStateByUnitId(req.params.unitId);
  if (!run) return res.status(404).json({ error: '未找到对应测试单元的运行状态。' });
  try {
    const filename = run.outputDirProbe && run.outputDirProbe.exportFilename
      ? run.outputDirProbe.exportFilename
      : `${run.runId}.zip`;
    streamDirectoryZip(run.outputDirAbs, res, filename);
  } catch (error) {
    res.status(500).json({
      error: '导出 output_dir 失败。',
      detail: String(error.message || error),
      runId: run.runId,
      outputDir: run.outputDir,
      outputDirAbs: run.outputDirAbs
    });
  }
});

app.listen(PORT, () => {
  console.log(`Mobile Agent Eval backend listening on http://localhost:${PORT}`);
});
