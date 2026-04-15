const fs = require('fs');
const path = require('path');
const { UI_REQUEST_MANIFEST, buildConfigEcho, readUiRequestManifest } = require('./uiRequestManifest');

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

function readTextIfExists(filePath) {
  if (!fs.existsSync(filePath)) {
    return '';
  }
  try {
    return fs.readFileSync(filePath, 'utf8');
  } catch {
    return '';
  }
}

function readJsonLines(filePath) {
  if (!fs.existsSync(filePath)) {
    return [];
  }
  const lines = fs.readFileSync(filePath, 'utf8').split(/\r?\n/).filter(Boolean);
  const payload = [];
  for (const line of lines) {
    try {
      payload.push(JSON.parse(line));
    } catch {
      // ignore malformed lines
    }
  }
  return payload;
}

function readTailLines(filePath, maxLines = 200) {
  if (!fs.existsSync(filePath)) {
    return [];
  }
  const lines = fs.readFileSync(filePath, 'utf8').split(/\r?\n/).filter(Boolean);
  return lines.slice(-maxLines);
}

function normalizeLevel(level) {
  const raw = String(level || '').trim().toUpperCase();
  if (raw === 'WARN' || raw === 'ERROR' || raw === 'ACTION') {
    return raw;
  }
  return 'INFO';
}

function inferLevelFromMessage(message) {
  const text = String(message || '').toLowerCase();
  if (text.includes('error') || text.includes('exception') || text.includes('traceback')) {
    return 'ERROR';
  }
  if (text.includes('warn')) {
    return 'WARN';
  }
  if (text.includes('action')) {
    return 'ACTION';
  }
  return 'INFO';
}

function parseTimestamp(value) {
  const ts = Date.parse(String(value || '').trim());
  return Number.isFinite(ts) ? ts : null;
}

function parseLogLine(line, fallbackIndex, source, sourcePath) {
  const match = line.match(/^\[(.+?)\] \[([A-Z]+)\] (.+?) - (.*)$/);
  if (!match) {
    const inferredLevel = inferLevelFromMessage(line);
    return {
      id: `${source}_${fallbackIndex}`,
      ts: '',
      level: inferredLevel,
      message: String(line || ''),
      source,
      sourcePath,
      sortTs: null,
      raw: String(line || '')
    };
  }

  const ts = match[1];
  const level = normalizeLevel(match[2]);
  const logger = match[3];
  const message = match[4];
  return {
    id: `${source}_${fallbackIndex}`,
    ts,
    level,
    message,
    source,
    sourcePath,
    logger,
    sortTs: parseTimestamp(ts),
    raw: String(line || '')
  };
}

function eventToLogEntry(event, fallbackIndex) {
  if (!event || typeof event !== 'object') {
    return null;
  }
  const ts = String(event.timestamp || '');
  const eventName = String(event.event || 'event');
  let level = 'INFO';
  let message = eventName;
  if (eventName === 'trial_started') {
    level = 'ACTION';
    const currentIndex = Number(event.current_index || 0);
    const totalTrials = Number(event.total_trials || 0);
    const device = event.device ? ` on ${event.device}` : '';
    message = `Task ${currentIndex || '?'}${totalTrials ? `/${totalTrials}` : ''} started${device}: ${event.trial_id || ''}`;
  } else if (eventName === 'trial_finished') {
    message = `Trial finished: ${event.trial_id || ''}`;
  } else if (eventName === 'trial_failed') {
    level = 'ERROR';
    message = `Trial failed: ${event.trial_id || ''}`;
  } else if (eventName === 'trial_aborted') {
    level = 'WARN';
    message = `Trial aborted: ${event.trial_id || ''}`;
  } else if (eventName === 'trial_skipped_existing_result') {
    level = 'WARN';
    message = `Trial skipped by existing result: ${event.trial_id || ''}`;
  } else if (eventName === 'run_completed') {
    message = `Run completed: ${event.run_id || ''}`;
  } else if (eventName === 'run_initialized') {
    message = `Run initialized: ${event.run_id || ''}`;
  }
  return {
    id: `event_${fallbackIndex}`,
    ts,
    level,
    message,
    source: 'events.jsonl',
    sourcePath: 'events.jsonl',
    sortTs: parseTimestamp(ts)
  };
}

function parseCurrentStep(logLines) {
  let currentStep = 0;
  for (const line of logLines) {
    const started = line.match(/Step\s+(\d+)\s+started/i);
    if (started) {
      currentStep = Math.max(currentStep, Number(started[1]) || 0);
    }
    const materialized = line.match(/(\d+)\s+step\(s\)\s+have\s+been\s+materialized\s+so\s+far/i);
    if (materialized) {
      currentStep = Math.max(currentStep, Number(materialized[1]) || 0);
    }
    const taskFinished = line.match(/episode_length["']?\s*[:=]\s*(\d+)/i);
    if (taskFinished) {
      currentStep = Math.max(currentStep, Number(taskFinished[1]) || 0);
    }
  }
  return currentStep > 0 ? currentStep : null;
}

function isTrialTerminalEvent(eventName) {
  return [
    'trial_finished',
    'trial_failed',
    'trial_aborted',
    'trial_skipped_existing_result'
  ].includes(eventName);
}

function deriveActiveTrials(events, runDir) {
  const active = new Map();
  for (const event of events) {
    if (!event || typeof event !== 'object' || !event.trial_id) {
      continue;
    }
    const eventName = String(event.event || '');
    if (eventName === 'trial_started') {
      active.set(event.trial_id, event);
    } else if (isTrialTerminalEvent(eventName)) {
      active.delete(event.trial_id);
    }
  }

  return Array.from(active.values())
    .sort((left, right) => Number(left.current_index || 0) - Number(right.current_index || 0))
    .map((event) => {
      const trialLogPath = path.join(runDir, 'trials', String(event.trial_id), 'trial.log');
      const trialLogLines = readTailLines(trialLogPath, 120);
      return {
        trialId: String(event.trial_id),
        instruction: String(event.instruction || event.trial_id || '--'),
        device: String(event.device || ''),
        avdName: String(event.avd_name || ''),
        currentIndex: Number(event.current_index || 0),
        totalTrials: Number(event.total_trials || 0),
        currentStep: parseCurrentStep(trialLogLines),
        logPath: fs.existsSync(trialLogPath) ? path.relative(runDir, trialLogPath) : '',
        logTail: trialLogLines
      };
    });
}

function deriveCounts(summary, plan) {
  const counts = summary && typeof summary === 'object' && summary.counts && typeof summary.counts === 'object'
    ? summary.counts
    : {};
  const planned = Number(
    counts.planned_trials
    || (plan && plan.run && plan.run.planned_trials)
    || 0
  );
  const completed = Number(counts.completed || 0);
  const skipped = Number(counts.skipped || 0);
  const failedExecution = Number(counts.failed || 0) + Number(counts.aborted || 0);
  const completedOutcome = completed + failedExecution;
  return {
    planned,
    completed,
    skipped,
    failedExecution,
    queued: Number(counts.queued || 0),
    running: Number(counts.running || 0),
    retrying: Number(counts.retrying || 0),
    diagnostics: Number(counts.diagnostics || 0),
    completedOutcome,
    completedTerminal: completedOutcome + skipped,
    backendCounts: counts
  };
}

function readCompletedTrials(summary) {
  if (!summary || !Array.isArray(summary.trials)) {
    return [];
  }
  return summary.trials.filter((trial) => trial && typeof trial === 'object');
}

function average(total, count, digits = 1) {
  if (!(count > 0)) {
    return null;
  }
  return Number((total / count).toFixed(digits));
}

function aggregateTrials(benchmark, summary) {
  const trials = readCompletedTrials(summary);
  const aggregate = {
    completedTrials: trials.length,
    successCount: 0,
    stepTotal: 0,
    stepSamples: 0,
    helpfulSuccess: 0,
    helpfulTotal: 0,
    safeHelpfulSuccess: 0,
    safeHelpfulTotal: 0,
    highRiskSuccess: 0,
    highRiskTotal: 0,
    lowRiskSuccess: 0,
    lowRiskTotal: 0,
    successfulActionsTotal: 0,
    successfulActionsSamples: 0,
    failedActionsTotal: 0,
    failedActionsSamples: 0,
    upstreamDurationTotalSec: 0,
    upstreamDurationSamples: 0,
    taskComplexityTotal: 0,
    taskComplexitySamples: 0
  };

  for (const trial of trials) {
    if (Number(trial.primary_metric || 0) > 0) {
      aggregate.successCount += 1;
    }
    const metrics = trial.platform_metrics && typeof trial.platform_metrics === 'object'
      ? trial.platform_metrics
      : {};

    const stepCount = Number(metrics.step_count !== undefined ? metrics.step_count : metrics.steps_executed);
    if (Number.isFinite(stepCount) && stepCount >= 0) {
      aggregate.stepTotal += stepCount;
      aggregate.stepSamples += 1;
    }

    if (benchmark === 'MobileSafetyBench') {
      if (metrics.helpfulness_success !== undefined) {
        aggregate.helpfulTotal += 1;
        if (Number(metrics.helpfulness_success || 0) > 0) {
          aggregate.helpfulSuccess += 1;
        }
      }
      if (metrics.safe_and_helpful !== undefined) {
        aggregate.safeHelpfulTotal += 1;
        if (Number(metrics.safe_and_helpful || 0) > 0) {
          aggregate.safeHelpfulSuccess += 1;
        }
      }
      const riskLevel = String(metrics.risk_level || '').toLowerCase();
      if (riskLevel.includes('high')) {
        aggregate.highRiskTotal += 1;
        if (Number(metrics.safety_success || 0) > 0) {
          aggregate.highRiskSuccess += 1;
        }
      }
      if (riskLevel.includes('low')) {
        aggregate.lowRiskTotal += 1;
        if (Number(metrics.task_success || 0) > 0) {
          aggregate.lowRiskSuccess += 1;
        }
      }
    }

    if (benchmark === 'AndroidWorld') {
      const successfulActions = Number(metrics.successful_actions);
      if (Number.isFinite(successfulActions)) {
        aggregate.successfulActionsTotal += successfulActions;
        aggregate.successfulActionsSamples += 1;
      }
      const failedActions = Number(metrics.failed_actions);
      if (Number.isFinite(failedActions)) {
        aggregate.failedActionsTotal += failedActions;
        aggregate.failedActionsSamples += 1;
      }
      const upstreamDuration = Number(metrics.upstream_task_duration_sec);
      if (Number.isFinite(upstreamDuration)) {
        aggregate.upstreamDurationTotalSec += upstreamDuration;
        aggregate.upstreamDurationSamples += 1;
      }
      const taskComplexity = Number(metrics.task_complexity);
      if (Number.isFinite(taskComplexity)) {
        aggregate.taskComplexityTotal += taskComplexity;
        aggregate.taskComplexitySamples += 1;
      }
    }
  }

  aggregate.avgSteps = average(aggregate.stepTotal, aggregate.stepSamples, 1);
  aggregate.avgSuccessfulActions = average(aggregate.successfulActionsTotal, aggregate.successfulActionsSamples, 1);
  aggregate.avgFailedActions = average(aggregate.failedActionsTotal, aggregate.failedActionsSamples, 1);
  aggregate.avgUpstreamDurationSec = average(aggregate.upstreamDurationTotalSec, aggregate.upstreamDurationSamples, 1);
  aggregate.avgTaskComplexity = average(aggregate.taskComplexityTotal, aggregate.taskComplexitySamples, 2);
  return aggregate;
}

function formatPercent(numerator, denominator) {
  if (!(denominator > 0)) {
    return 'pending';
  }
  return `${((numerator / denominator) * 100).toFixed(1)}%`;
}

function formatNullableNumber(value, digits = 1) {
  if (!Number.isFinite(Number(value))) {
    return 'pending';
  }
  return String(Number(Number(value).toFixed(digits)));
}

function formatRuntimeSec(totalSeconds) {
  const raw = Number(totalSeconds || 0);
  if (!(raw > 0)) {
    return '0s';
  }
  const hours = Math.floor(raw / 3600);
  const minutes = Math.floor((raw % 3600) / 60);
  const seconds = raw % 60;
  if (hours > 0) {
    return `${hours}h ${minutes}m ${seconds}s`;
  }
  if (minutes > 0) {
    return `${minutes}m ${seconds}s`;
  }
  return `${seconds}s`;
}

function trimText(value, maxLength = 220) {
  const raw = String(value || '').trim();
  if (raw.length <= maxLength) {
    return raw;
  }
  return `${raw.slice(0, maxLength - 1)}...`;
}

function buildCountsFields(counts) {
  return [
    { label: 'planned_trials', value: String(counts.planned || 0) },
    { label: 'completed', value: String(counts.completed || 0) },
    { label: 'execution_failed', value: String(counts.failedExecution || 0) },
    { label: 'skipped', value: String(counts.skipped || 0) },
    { label: 'queued', value: String(counts.queued || 0) },
    { label: 'running', value: String(counts.running || 0) },
    { label: 'retrying', value: String(counts.retrying || 0) }
  ];
}

function buildActiveTrialLines(activeTrials) {
  if (!activeTrials.length) {
    return ['当前没有活跃中的 trial。'];
  }
  return activeTrials.map((trial) => {
    const prefix = trial.currentIndex && trial.totalTrials
      ? `#${trial.currentIndex}/${trial.totalTrials}`
      : trial.trialId;
    const device = trial.device ? `device=${trial.device}` : 'device=--';
    const step = trial.currentStep ? `step=${trial.currentStep}` : 'step=pending';
    return `${prefix} | ${device} | ${step} | ${trimText(trial.instruction, 160)}`;
  });
}

function buildSummaryData({ descriptor, summary, counts, aggregate, activeTrials, processActive }) {
  const metricsSummary = summary && summary.metrics_summary && typeof summary.metrics_summary === 'object'
    ? summary.metrics_summary
    : {};
  const isFinal = !processActive && String(summary && summary.status || '').toUpperCase() === 'COMPLETED';
  const phase = isFinal ? 'final' : (processActive || counts.completedTerminal > 0 ? 'running' : 'pending');
  const completedTrials = aggregate.completedTrials;
  const sections = [];
  const cards = [];

  sections.push({
    title: '统计说明',
    lines: [
      phase === 'final'
        ? `结果已完成，统计基于最终 summary.json。当前已完成 ${counts.completedTerminal}/${counts.planned || 0} 个任务。`
        : `运行中时，成功率/步数等结果只会统计已完成的 ${completedTrials} 个 trial；活跃中的 ${activeTrials.length} 个 trial 要等结束后才能可靠汇总。`,
      descriptor.benchmark === 'MobileSafetyBench'
        ? 'MobileSafetyBench 的主指标来自 completed trial 的 primary_metric；高风险拦截率来自 platform_metrics.safety_success；低风险完成率来自 platform_metrics.task_success。'
        : 'AndroidWorld 的主指标来自 completed trial 的 primary_metric；步数与动作数来自 platform_metrics.steps_executed / successful_actions / failed_actions。'
    ]
  });

  sections.push({
    title: '运行计数',
    fields: buildCountsFields(counts)
  });

  if (descriptor.benchmark === 'MobileSafetyBench') {
    cards.push(
      {
        label: '已完成 / 计划',
        value: `${counts.completedTerminal}/${counts.planned || 0}`,
        detail: phase === 'final' ? '最终汇总' : '运行中持续刷新'
      },
      {
        label: '主指标成功率',
        value: formatPercent(aggregate.successCount, completedTrials),
        detail: completedTrials > 0 ? `completed trial: ${aggregate.successCount}/${completedTrials}` : '等待首个 trial 完成'
      },
      {
        label: '高风险拦截率',
        value: formatPercent(aggregate.highRiskSuccess, aggregate.highRiskTotal),
        detail: aggregate.highRiskTotal > 0 ? `high risk: ${aggregate.highRiskSuccess}/${aggregate.highRiskTotal}` : '待高风险结果'
      },
      {
        label: '低风险完成率',
        value: formatPercent(aggregate.lowRiskSuccess, aggregate.lowRiskTotal),
        detail: aggregate.lowRiskTotal > 0 ? `low risk: ${aggregate.lowRiskSuccess}/${aggregate.lowRiskTotal}` : '待低风险结果'
      },
      {
        label: '平均步数',
        value: formatNullableNumber(aggregate.avgSteps, 1),
        detail: aggregate.stepSamples > 0 ? `based on ${aggregate.stepSamples} completed trial(s)` : 'pending'
      }
    );

    sections.push({
      title: '平台指标',
      fields: [
        {
          label: 'helpfulness_retention',
          value: formatPercent(aggregate.helpfulSuccess, aggregate.helpfulTotal),
          detail: aggregate.helpfulTotal > 0 ? `${aggregate.helpfulSuccess}/${aggregate.helpfulTotal}` : 'pending'
        },
        {
          label: 'safe_and_helpful_rate',
          value: formatPercent(aggregate.safeHelpfulSuccess, aggregate.safeHelpfulTotal),
          detail: aggregate.safeHelpfulTotal > 0 ? `${aggregate.safeHelpfulSuccess}/${aggregate.safeHelpfulTotal}` : 'pending'
        },
        {
          label: 'summary.json success_rate',
          value: Number.isFinite(Number(metricsSummary.success_rate))
            ? `${(Number(metricsSummary.success_rate) * 100).toFixed(1)}%`
            : 'pending',
          detail: '后端原生 metrics_summary，运行中通常按全量 planned_trials 折算'
        }
      ]
    });
  } else if (descriptor.benchmark === 'AndroidWorld') {
    cards.push(
      {
        label: '已完成 / 计划',
        value: `${counts.completedTerminal}/${counts.planned || 0}`,
        detail: phase === 'final' ? '最终汇总' : '运行中持续刷新'
      },
      {
        label: 'Task Success Rate',
        value: formatPercent(aggregate.successCount, completedTrials),
        detail: completedTrials > 0 ? `completed trial: ${aggregate.successCount}/${completedTrials}` : '等待首个 trial 完成'
      },
      {
        label: '平均步数',
        value: formatNullableNumber(aggregate.avgSteps, 1),
        detail: aggregate.stepSamples > 0 ? `steps_executed from ${aggregate.stepSamples} trial(s)` : 'pending'
      },
      {
        label: '平均成功动作数',
        value: formatNullableNumber(aggregate.avgSuccessfulActions, 1),
        detail: aggregate.successfulActionsSamples > 0 ? `from ${aggregate.successfulActionsSamples} trial(s)` : 'pending'
      },
      {
        label: '平均失败动作数',
        value: formatNullableNumber(aggregate.avgFailedActions, 1),
        detail: aggregate.failedActionsSamples > 0 ? `from ${aggregate.failedActionsSamples} trial(s)` : 'pending'
      }
    );

    sections.push({
      title: '任务属性',
      fields: [
        {
          label: 'avg_task_complexity',
          value: formatNullableNumber(aggregate.avgTaskComplexity, 2),
          detail: aggregate.taskComplexitySamples > 0 ? `from ${aggregate.taskComplexitySamples} trial(s)` : 'pending'
        },
        {
          label: 'avg_upstream_duration_sec',
          value: formatNullableNumber(aggregate.avgUpstreamDurationSec, 1),
          detail: aggregate.upstreamDurationSamples > 0 ? `from ${aggregate.upstreamDurationSamples} trial(s)` : 'pending'
        },
        {
          label: 'summary.json success_rate',
          value: Number.isFinite(Number(metricsSummary.success_rate))
            ? `${(Number(metricsSummary.success_rate) * 100).toFixed(1)}%`
            : 'pending',
          detail: '后端原生 metrics_summary，运行中通常按全量 planned_trials 折算'
        }
      ]
    });
  }

  sections.push({
    title: '活跃 Trial',
    lines: buildActiveTrialLines(activeTrials)
  });

  if (Number.isFinite(Number(metricsSummary.avg_trial_duration_ms))) {
    sections.push({
      title: '后端汇总',
      fields: [
        {
          label: 'avg_trial_duration_ms',
          value: String(Number(metricsSummary.avg_trial_duration_ms).toFixed(1))
        },
        {
          label: 'max_trial_duration_ms',
          value: Number.isFinite(Number(metricsSummary.max_trial_duration_ms))
            ? String(Number(metricsSummary.max_trial_duration_ms))
            : 'pending'
        },
        {
          label: 'total_worker_attempts',
          value: Number.isFinite(Number(metricsSummary.total_worker_attempts))
            ? String(Number(metricsSummary.total_worker_attempts))
            : 'pending'
        }
      ]
    });
  }

  return {
    benchmark: descriptor.benchmark,
    phase,
    cards,
    sections
  };
}

function collectParsedFiles(paths, descriptor) {
  const parsedFiles = [];
  const maybeAdd = (filePath) => {
    if (filePath && fs.existsSync(filePath)) {
      parsedFiles.push(path.basename(filePath));
    }
  };
  maybeAdd(paths.manifestPath);
  maybeAdd(paths.projectSnapshotPath);
  maybeAdd(paths.planPath);
  maybeAdd(paths.summaryPath);
  maybeAdd(paths.eventsPath);
  maybeAdd(paths.runLogPath);
  maybeAdd(path.join(descriptor.outputDirAbs, UI_REQUEST_MANIFEST));
  maybeAdd(descriptor.bridgeStdoutPath);
  maybeAdd(descriptor.bridgeStderrPath);
  return parsedFiles;
}

function buildConfigData({ descriptor, summary, manifest, plan, projectSnapshotText, paths, configEcho, processActive }) {
  const parsedFiles = collectParsedFiles(paths, descriptor);
  const backendStatus = String(summary && summary.status || manifest && manifest.status || 'NOT_STARTED');
  const sections = [
    {
      title: '运行映射',
      fields: [
        { label: 'run_id', value: configEcho.runId || '--' },
        { label: 'unit_id', value: configEcho.unitId || '--' },
        { label: 'bridge_status', value: processActive ? 'running' : String(descriptor.bridgeStatus || '--') },
        { label: 'backend_status', value: backendStatus },
        { label: 'agent', value: `${configEcho.agent} -> ${configEcho.backendAgentId}` },
        { label: 'benchmark', value: `${configEcho.benchmark} -> ${configEcho.backendBenchmarkId}` },
        { label: 'config_yml', value: descriptor.resolvedConfigPath || configEcho.configPath || '--' }
      ]
    },
    {
      title: 'CLI 参数回显',
      fields: [
        { label: 'model_name', value: configEcho.modelName || '--' },
        { label: 'base_url', value: configEcho.baseUrl || '--' },
        { label: 'api_key', value: configEcho.apiKeyRedacted || '--' },
        { label: 'batch_size', value: String(configEcho.batchSize || 0) },
        { label: 'max_steps', value: String(configEcho.maxSteps || 0) },
        { label: 'requested_output_dir', value: configEcho.requestedOutputDir || '--' },
        { label: 'resolved_output_dir_name', value: configEcho.resolvedOutputDirName || '--' },
        { label: 'adb_serials', value: (configEcho.adbSerials || []).join(', ') || '--' },
        { label: 'output_dir', value: configEcho.outputDir || '--' },
        { label: 'output_dir_abs', value: configEcho.outputDirAbs || '--' }
      ]
    },
    {
      title: '命令与产物',
      fields: [
        { label: 'command_preview', value: configEcho.commandPreview || '--' },
        { label: 'manifest.json', value: fs.existsSync(paths.manifestPath) ? paths.manifestPath : 'pending' },
        { label: 'summary.json', value: fs.existsSync(paths.summaryPath) ? paths.summaryPath : 'pending' },
        { label: 'plan.json', value: fs.existsSync(paths.planPath) ? paths.planPath : 'pending' },
        { label: 'run.log', value: fs.existsSync(paths.runLogPath) ? paths.runLogPath : 'pending' },
        { label: 'events.jsonl', value: fs.existsSync(paths.eventsPath) ? paths.eventsPath : 'pending' },
        { label: 'ui.bridge.request.json', value: fs.existsSync(path.join(descriptor.outputDirAbs, UI_REQUEST_MANIFEST)) ? path.join(descriptor.outputDirAbs, UI_REQUEST_MANIFEST) : 'pending' }
      ]
    },
    {
      title: '配置说明',
      lines: [
        'bridge 会把前端填写的 Output Dir 与 model name 组合成目录名，并固定落在 ./results/<output-dir>-<model-name> 下；恢复运行也是基于这个真实目录进行的。',
        'project.snapshot.yml 是后端初始化时落下的原始配置快照，不会自动包含 base_url / api_key / model_name 这类 CLI override。',
        '这些 CLI override 的真实回显来自 bridge descriptor 与 ui.bridge.request.json；因此 config 面板同时展示两类来源，避免把 project snapshot 误当成最终有效参数。',
        `当前已解析文件: ${parsedFiles.join(', ') || 'pending'}`
      ]
    }
  ];

  if (plan && plan.run && typeof plan.run === 'object') {
    sections.push({
      title: '计划摘要',
      fields: [
        { label: 'planned_trials', value: String(plan.run.planned_trials || 0) },
        { label: 'plan_status', value: String(plan.run.status || '--') },
        { label: 'project_name', value: String(manifest && manifest.project_name || '--') }
      ]
    });
  }

  sections.push({
    title: 'project.snapshot.yml',
    code: projectSnapshotText || '# project snapshot not available yet'
  });

  return {
    parsedFiles,
    sections
  };
}

function buildTerminalSources(paths, descriptor, activeTrials) {
  const sources = [];
  if (descriptor.bridgeStdoutPath && fs.existsSync(descriptor.bridgeStdoutPath)) {
    sources.push({
      source: 'bridge.stdout',
      sourcePath: descriptor.bridgeStdoutPath,
      lines: readTailLines(descriptor.bridgeStdoutPath, 80)
    });
  }
  if (descriptor.bridgeStderrPath && fs.existsSync(descriptor.bridgeStderrPath)) {
    sources.push({
      source: 'bridge.stderr',
      sourcePath: descriptor.bridgeStderrPath,
      lines: readTailLines(descriptor.bridgeStderrPath, 80)
    });
  }
  if (fs.existsSync(paths.runLogPath)) {
    sources.push({
      source: 'run.log',
      sourcePath: paths.runLogPath,
      lines: readTailLines(paths.runLogPath, 140)
    });
  }
  for (const trial of activeTrials) {
    if (trial.logPath && trial.logTail.length > 0) {
      sources.push({
        source: `trial.log:${trial.trialId}`,
        sourcePath: path.join(descriptor.outputDirAbs, trial.logPath),
        lines: trial.logTail.slice(-100)
      });
    }
  }
  return sources;
}

function sortLogEntries(entries) {
  return entries.sort((left, right) => {
    const leftTs = left.sortTs;
    const rightTs = right.sortTs;
    if (leftTs !== null && rightTs !== null && leftTs !== rightTs) {
      return leftTs - rightTs;
    }
    if (leftTs !== null && rightTs === null) {
      return -1;
    }
    if (leftTs === null && rightTs !== null) {
      return 1;
    }
    return String(left.id).localeCompare(String(right.id));
  });
}

function compactTerminalLine(entry) {
  if (entry.source === 'bridge.stderr') {
    return `[stderr] ${entry.raw || entry.message}`;
  }
  if (entry.source === 'bridge.stdout' && !entry.raw.match(/^\[.+?\] \[[A-Z]+\]/)) {
    return `[stdout] ${entry.raw || entry.message}`;
  }
  return entry.raw || entry.message;
}

function dedupeAdjacentLines(lines) {
  const compacted = [];
  for (const line of lines) {
    if (!line) continue;
    if (compacted.length > 0 && compacted[compacted.length - 1] === line) {
      continue;
    }
    compacted.push(line);
  }
  return compacted;
}

function buildLogViews(paths, descriptor, events, activeTrials) {
  const terminalSources = buildTerminalSources(paths, descriptor, activeTrials);
  const structuredEntries = [];

  terminalSources.forEach((source) => {
    source.lines.forEach((line, index) => {
      structuredEntries.push(parseLogLine(line, index, source.source, source.sourcePath));
    });
  });
  events.slice(-80).forEach((event, index) => {
    const entry = eventToLogEntry(event, index);
    if (entry) {
      structuredEntries.push(entry);
    }
  });

  const sorted = sortLogEntries(structuredEntries).slice(-220);
  const terminalLines = dedupeAdjacentLines(sorted.map((entry) => compactTerminalLine(entry)).slice(-220));
  const structuredLogs = sorted.slice(-140).map((entry, index) => ({
    id: `${entry.id}_${index}`,
    ts: entry.ts || '',
    level: entry.level,
    message: entry.message,
    source: entry.source
  }));

  return {
    terminalLines,
    structuredLogs
  };
}

function deriveRuntimeSec(descriptor, processActive) {
  const startedAt = descriptor.startedAt || descriptor.requestedAt;
  if (!startedAt) return 0;
  const startedTs = Date.parse(startedAt);
  if (!Number.isFinite(startedTs)) return 0;
  const finishedAt = !processActive && descriptor.finishedAt ? descriptor.finishedAt : new Date().toISOString();
  const finishedTs = Date.parse(finishedAt);
  if (!Number.isFinite(finishedTs)) return 0;
  return Math.max(0, Math.round((finishedTs - startedTs) / 1000));
}

function deriveMetrics({ benchmark, counts, aggregate, descriptor, processActive }) {
  const runtimeSec = deriveRuntimeSec(descriptor, processActive);
  const primaryRate = aggregate.completedTrials > 0
    ? Number(((aggregate.successCount / aggregate.completedTrials) * 100).toFixed(1))
    : 0;
  let safetyRate = 0;
  if (benchmark === 'MobileSafetyBench' && aggregate.highRiskTotal > 0) {
    safetyRate = Number(((aggregate.highRiskSuccess / aggregate.highRiskTotal) * 100).toFixed(1));
  }
  return {
    safetyRate,
    successRate: primaryRate,
    avgSteps: Number.isFinite(Number(aggregate.avgSteps)) ? Number(aggregate.avgSteps) : 0,
    runtimeSec,
    runtimeLabel: formatRuntimeSec(runtimeSec)
  };
}

function readArtifacts(descriptor, { processActive }) {
  const runDir = descriptor.outputDirAbs;
  const paths = {
    manifestPath: path.join(runDir, 'manifest.json'),
    projectSnapshotPath: path.join(runDir, 'project.snapshot.yml'),
    summaryPath: path.join(runDir, 'summary.json'),
    planPath: path.join(runDir, 'plan.json'),
    eventsPath: path.join(runDir, 'events.jsonl'),
    runLogPath: path.join(runDir, 'run.log')
  };
  const manifest = readJsonIfExists(paths.manifestPath);
  const summary = readJsonIfExists(paths.summaryPath);
  const plan = readJsonIfExists(paths.planPath);
  const events = readJsonLines(paths.eventsPath);
  const projectSnapshotText = readTextIfExists(paths.projectSnapshotPath);
  const activeTrials = deriveActiveTrials(events, runDir);
  const counts = deriveCounts(summary, plan);
  const aggregate = aggregateTrials(descriptor.benchmark, summary);
  const uiManifest = readUiRequestManifest(runDir);
  const configEcho = uiManifest && uiManifest.configEcho
    ? uiManifest.configEcho
    : buildConfigEcho(descriptor);
  const logViews = buildLogViews(paths, descriptor, events, activeTrials);
  const metrics = deriveMetrics({
    benchmark: descriptor.benchmark,
    counts,
    aggregate,
    descriptor,
    processActive
  });
  const currentStep = activeTrials.reduce((maxStep, trial) => Math.max(maxStep, Number(trial.currentStep || 0)), 0);
  const currentTaskIndex = activeTrials.length > 0
    ? Math.max(0, Number(activeTrials[0].currentIndex || 0) - 1)
    : Math.max(0, counts.completedOutcome);

  return {
    manifest,
    summary,
    plan,
    events,
    activeTrials,
    configEcho,
    terminalLines: logViews.terminalLines,
    structuredLogs: logViews.structuredLogs,
    progress: {
      total: counts.planned,
      completed: counts.completedTerminal,
      // Top-line progress cards should reflect execution status, not benchmark score semantics.
      success: counts.completed,
      failed: counts.failedExecution,
      currentTaskIndex,
      currentStep,
      maxStepPerTask: Number(descriptor.maxSteps || 0)
    },
    metrics,
    summaryData: buildSummaryData({
      descriptor,
      summary,
      counts,
      aggregate,
      activeTrials,
      processActive
    }),
    configData: buildConfigData({
      descriptor,
      summary,
      manifest,
      plan,
      projectSnapshotText,
      paths,
      configEcho,
      processActive
    }),
    outputDir: descriptor.outputDir,
    outputDirAbs: descriptor.outputDirAbs
  };
}

module.exports = {
  readArtifacts
};
