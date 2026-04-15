const path = require('path');

function sanitizeOutputSegment(value, fallback = 'run-output') {
  const raw = String(value || '').trim().toLowerCase();
  const normalized = raw
    .replace(/[/\\]+/g, '-')
    .replace(/\s+/g, '-')
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^[._-]+|[._-]+$/g, '');
  return normalized || fallback;
}

function extractResolvedOutputDirName(rawValue) {
  const raw = String(rawValue || '').trim();
  if (!raw) {
    return '';
  }
  const normalized = raw.replace(/\\/g, '/').replace(/^\.\/+/, '');
  if (normalized.startsWith('results/')) {
    return sanitizeOutputSegment(normalized.slice('results/'.length));
  }
  return sanitizeOutputSegment(path.basename(normalized));
}

function buildResolvedOutputDirName(requestedOutputDir, modelName) {
  const base = sanitizeOutputSegment(requestedOutputDir, 'run-output');
  const model = sanitizeOutputSegment(modelName, 'model');
  if (base.endsWith(`-${model}`)) {
    return base;
  }
  return `${base}-${model}`;
}

function resolveManagedOutputDir(repoRoot, {
  requestedOutputDir,
  modelName,
  resolvedOutputDirName
}) {
  const requested = String(requestedOutputDir || '').trim();
  const resolvedName = extractResolvedOutputDirName(resolvedOutputDirName)
    || buildResolvedOutputDirName(requested, modelName);
  const relativePath = path.posix.join('results', resolvedName);
  return {
    requestedOutputDir: requested,
    modelName: String(modelName || '').trim(),
    resolvedOutputDirName: resolvedName,
    outputDirRelative: relativePath,
    outputDirCliArg: `./${relativePath}`,
    outputDirAbs: path.resolve(repoRoot, relativePath)
  };
}

module.exports = {
  buildResolvedOutputDirName,
  extractResolvedOutputDirName,
  resolveManagedOutputDir,
  sanitizeOutputSegment
};
