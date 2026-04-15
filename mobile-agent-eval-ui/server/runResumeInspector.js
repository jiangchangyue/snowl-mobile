const fs = require('fs');
const path = require('path');
const { resolveManagedOutputDir } = require('./outputDirResolver');

function readJsonIfExists(filePath) {
  if (!fs.existsSync(filePath)) {
    return null;
  }
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch {
    return null;
  }
}

function isDirectoryNonEmpty(runDir) {
  if (!fs.existsSync(runDir)) {
    return false;
  }
  try {
    return fs.statSync(runDir).isDirectory() && fs.readdirSync(runDir).length > 0;
  } catch {
    return false;
  }
}

function isResumableRunDirectory(runDir) {
  if (!fs.existsSync(runDir)) {
    return false;
  }
  try {
    if (!fs.statSync(runDir).isDirectory()) {
      return false;
    }
  } catch {
    return false;
  }
  return fs.existsSync(path.join(runDir, 'manifest.json'))
    && fs.existsSync(path.join(runDir, 'plan.json'))
    && fs.existsSync(path.join(runDir, 'trials'));
}

function deriveHistoryCounts(summary, plan) {
  const backendCounts = summary && summary.counts && typeof summary.counts === 'object'
    ? summary.counts
    : {};
  const trials = summary && Array.isArray(summary.trials) ? summary.trials : [];
  const plannedTasks = Number(
    backendCounts.planned_trials
    || (plan && plan.run && plan.run.planned_trials)
    || 0
  );
  const benchmarkSuccessTasks = trials.filter((trial) => Number(trial && trial.primary_metric || 0) > 0).length;
  const executionCompleted = Number(backendCounts.completed || 0);
  const executionFailed = Number(backendCounts.failed || 0) + Number(backendCounts.aborted || 0);
  const benchmarkFailedCompleted = Math.max(0, executionCompleted - benchmarkSuccessTasks);
  const failedTasks = benchmarkFailedCompleted + executionFailed;
  const unfinishedFromBackend = Number(backendCounts.queued || 0)
    + Number(backendCounts.running || 0)
    + Number(backendCounts.retrying || 0);
  const fallbackUnfinished = Math.max(
    0,
    plannedTasks
      - Number(backendCounts.completed || 0)
      - Number(backendCounts.failed || 0)
      - Number(backendCounts.aborted || 0)
      - Number(backendCounts.skipped || 0)
  );
  const unfinishedTasks = unfinishedFromBackend > 0 ? unfinishedFromBackend : fallbackUnfinished;

  return {
    plannedTasks: plannedTasks || null,
    successTasks: benchmarkSuccessTasks,
    failedTasks,
    unfinishedTasks,
    completedArtifacts: executionCompleted,
    skippedTasks: Number(backendCounts.skipped || 0),
    queuedTasks: Number(backendCounts.queued || 0),
    runningTasks: Number(backendCounts.running || 0),
    retryingTasks: Number(backendCounts.retrying || 0),
    rawCounts: backendCounts
  };
}

function buildNotes({ exists, nonEmpty, resumable, incompatible, historyFound, backendStatus, counts }) {
  if (!exists) {
    return ['目标 output_dir 当前不存在，本次将创建一个新的运行目录。'];
  }
  if (exists && !nonEmpty) {
    return ['目标 output_dir 已存在但为空目录，本次会在该目录下新建运行产物。'];
  }
  if (incompatible) {
    return ['目标 output_dir 已存在，但不是可恢复的 snowl-mobile 运行目录。请更换 output_dir，避免覆盖其他文件。'];
  }
  if (!historyFound) {
    return ['目录存在，但尚未发现可供恢复的历史运行结果。'];
  }
  if ((counts.unfinishedTasks || 0) > 0) {
    return [
      `检测到历史运行目录，后端会基于相同 output_dir 继续执行未完成或失败的任务。当前后端状态：${backendStatus || 'UNKNOWN'}。`,
      `根据现有 summary/plan，大约还有 ${counts.unfinishedTasks} 个任务未完成。`
    ];
  }
  return [
    '检测到历史运行目录，且当前看起来没有剩余未完成任务；如果重新启动，后端会沿用同一 output_dir，并快速跳过已完成项。',
    `当前后端状态：${backendStatus || 'UNKNOWN'}。`
  ];
}

function inspectOutputDir({
  repoRoot,
  requestedOutputDir,
  modelName,
  resolvedOutputDirName
}) {
  const resolved = resolveManagedOutputDir(repoRoot, {
    requestedOutputDir,
    modelName,
    resolvedOutputDirName
  });
  const exists = fs.existsSync(resolved.outputDirAbs);
  const nonEmpty = exists && isDirectoryNonEmpty(resolved.outputDirAbs);
  const resumable = nonEmpty && isResumableRunDirectory(resolved.outputDirAbs);
  const incompatible = nonEmpty && !resumable;
  const manifest = resumable ? readJsonIfExists(path.join(resolved.outputDirAbs, 'manifest.json')) : null;
  const plan = resumable ? readJsonIfExists(path.join(resolved.outputDirAbs, 'plan.json')) : null;
  const summary = resumable ? readJsonIfExists(path.join(resolved.outputDirAbs, 'summary.json')) : null;
  const trialsDir = path.join(resolved.outputDirAbs, 'trials');
  const hasTrialArtifacts = fs.existsSync(trialsDir)
    && fs.statSync(trialsDir).isDirectory()
    && fs.readdirSync(trialsDir).length > 0;
  const historyFound = resumable && Boolean(manifest || summary || hasTrialArtifacts);
  const counts = deriveHistoryCounts(summary, plan);
  const backendStatus = String(summary && summary.status || manifest && manifest.status || 'NOT_STARTED');
  const shouldResume = historyFound && ((counts.unfinishedTasks || 0) > 0 || backendStatus === 'RUNNING' || backendStatus === 'PLANNED');
  const completedHistory = historyFound && !shouldResume && (counts.plannedTasks || 0) > 0;

  return {
    requestedOutputDir: resolved.requestedOutputDir,
    modelName: resolved.modelName,
    resolvedOutputDirName: resolved.resolvedOutputDirName,
    outputDir: resolved.outputDirCliArg,
    outputDirRelative: resolved.outputDirRelative,
    outputDirAbs: resolved.outputDirAbs,
    exportFilename: `${resolved.resolvedOutputDirName}.zip`,
    exists,
    nonEmpty,
    resumable,
    incompatible,
    historyFound,
    shouldResume,
    completedHistory,
    backendStatus,
    runId: String(manifest && manifest.run_id || resolved.resolvedOutputDirName),
    projectName: String(manifest && manifest.project_name || ''),
    plannedTasks: counts.plannedTasks,
    successTasks: counts.successTasks,
    failedTasks: counts.failedTasks,
    unfinishedTasks: counts.unfinishedTasks,
    completedArtifacts: counts.completedArtifacts,
    skippedTasks: counts.skippedTasks,
    queuedTasks: counts.queuedTasks,
    runningTasks: counts.runningTasks,
    retryingTasks: counts.retryingTasks,
    notes: buildNotes({
      exists,
      nonEmpty,
      resumable,
      incompatible,
      historyFound,
      backendStatus,
      counts
    })
  };
}

module.exports = {
  inspectOutputDir,
  isDirectoryNonEmpty,
  isResumableRunDirectory
};
