const fs = require('fs');
const path = require('path');

const UI_REQUEST_MANIFEST = 'ui.bridge.request.json';

function redactApiKey(apiKey) {
  const raw = String(apiKey || '').trim();
  if (!raw) {
    return '';
  }
  if (raw.length <= 6) {
    return `${raw.slice(0, 1)}***`;
  }
  return `${raw.slice(0, 3)}***${raw.slice(-2)}`;
}

function buildConfigEcho(descriptor) {
  return {
    runId: descriptor.runId,
    unitId: descriptor.unitId || '',
    agent: descriptor.agent,
    benchmark: descriptor.benchmark,
    backendAgentId: descriptor.backendAgentId,
    backendBenchmarkId: descriptor.backendBenchmarkId,
    configPath: descriptor.configPath,
    modelName: descriptor.modelName,
    baseUrl: descriptor.baseUrl,
    apiKeyRedacted: descriptor.apiKeyRedacted || '',
    maxSteps: descriptor.maxSteps,
    batchSize: descriptor.batchSize,
    requestedOutputDir: descriptor.requestedOutputDir || '',
    resolvedOutputDirName: descriptor.resolvedOutputDirName || '',
    outputDir: descriptor.outputDir,
    outputDirAbs: descriptor.outputDirAbs,
    adbSerials: Array.isArray(descriptor.adbSerials) ? descriptor.adbSerials : [],
    commandPreview: descriptor.commandPreview
  };
}

function buildRequestManifest(descriptor) {
  return {
    schemaVersion: 'snowl-mobile.ui-bridge.v1',
    createdAt: new Date().toISOString(),
    runId: descriptor.runId,
    unitId: descriptor.unitId || '',
    configEcho: buildConfigEcho(descriptor)
  };
}

function readUiRequestManifest(runDir) {
  const manifestPath = path.join(runDir, UI_REQUEST_MANIFEST);
  if (!fs.existsSync(manifestPath)) {
    return null;
  }
  try {
    return JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  } catch {
    return null;
  }
}

function ensureUiRequestManifest(runDir, descriptor) {
  const manifestPath = path.join(runDir, UI_REQUEST_MANIFEST);
  const backendManifestPath = path.join(runDir, 'manifest.json');
  if (!fs.existsSync(runDir) || !fs.existsSync(backendManifestPath)) {
    return null;
  }
  const payload = buildRequestManifest(descriptor);
  const serialized = JSON.stringify(payload, null, 2);
  const current = fs.existsSync(manifestPath) ? fs.readFileSync(manifestPath, 'utf8') : null;
  if (current !== serialized) {
    fs.writeFileSync(manifestPath, serialized, 'utf8');
  }
  return manifestPath;
}

module.exports = {
  UI_REQUEST_MANIFEST,
  buildConfigEcho,
  ensureUiRequestManifest,
  readUiRequestManifest,
  redactApiKey
};
