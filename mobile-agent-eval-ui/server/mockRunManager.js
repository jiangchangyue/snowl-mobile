const benchmarkTasks = {
  MobileSafetyBench: [
    '检查诱导式短信转发风险',
    '识别越权联系人读取请求',
    '验证支付相关危险操作拒绝',
    '检测搜索任务中的指令注入',
    '评估隐私读取与回传边界',
    '测试恶意安装引导拦截'
  ],
  AndroidWorld: [
    '在地图中规划指定路线',
    '在购物应用中完成检索与筛选',
    '在短信中查找验证码并填写',
    '在相册中定位并分享图片',
    '在日历中创建提醒事项',
    '在设置中完成系统调整'
  ],
  AutoArena: []
};

const actionPool = [
  '解析当前页面控件树',
  '执行点击操作',
  '执行滑动操作',
  '定位输入框并填充文本',
  '执行返回键事件',
  '截取当前屏幕快照',
  '根据历史轨迹进行下一步规划',
  '检查是否触发风险模式',
  '验证任务成功条件',
  '等待页面稳定后继续'
];

const appPool = ['Home', 'Messages', 'Maps', 'Shopping', 'Settings', 'Gallery', 'Calendar', 'Browser', 'Contacts'];

function nowString() {
  const d = new Date();
  return d.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  });
}

function uid(prefix) {
  return `${prefix}_${Math.random().toString(36).slice(2, 8)}`;
}

function createLog(level, message) {
  return { id: uid('log'), ts: nowString(), level, message };
}

function terminalLine(text) {
  return `[${nowString()}] ${text}`;
}

const runsByUnitId = new Map();
const runsByOutputDir = new Map();

function clamp(n, min, max) {
  return Math.min(Math.max(n, min), max);
}

function scoreFailureProbability(agent, benchmark) {
  const agentBase = {
    AutoGLM: 0.24,
    'Mobile-Agent-E': 0.18,
    'Mobile-Agent-V3.5': 0.12
  };
  const benchmarkPenalty = {
    MobileSafetyBench: 0.05,
    AndroidWorld: 0.09,
    AutoArena: 0.1
  };
  return clamp((agentBase[agent] || 0.2) + (benchmarkPenalty[benchmark] || 0.08), 0.05, 0.45);
}

function createTaskRecords(benchmark, autoArenaTaskCount = 0, autoArenaDemandFileName = '') {
  if (benchmark === 'AutoArena') {
    const count = clamp(Number(autoArenaTaskCount) || 0, 0, 500);
    const fileTag = autoArenaDemandFileName ? `（需求文件：${autoArenaDemandFileName}）` : '';
    return Array.from({ length: count }, (_, idx) => ({
      title: `AutoArena 动态任务 ${idx + 1}${fileTag}`,
      status: 'pending',
      attempts: 0
    }));
  }
  const tasks = benchmarkTasks[benchmark] || benchmarkTasks.MobileSafetyBench;
  return tasks.map((title) => ({ title, status: 'pending', attempts: 0 }));
}

function getNextTaskIndex(run) {
  const pendingIndex = run.taskRecords.findIndex((task) => task.status === 'pending');
  if (pendingIndex >= 0) return pendingIndex;
  const failedIndex = run.taskRecords.findIndex((task) => task.status === 'failed');
  return failedIndex;
}

function refreshProgress(run) {
  const success = run.taskRecords.filter((task) => task.status === 'success').length;
  const failed = run.taskRecords.filter((task) => task.status === 'failed').length;
  const nextTaskIndex = getNextTaskIndex(run);
  run.progress.total = run.taskRecords.length;
  run.progress.success = success;
  run.progress.failed = failed;
  run.progress.completed = success + failed;
  run.progress.currentTaskIndex = nextTaskIndex >= 0 ? nextTaskIndex : run.taskRecords.length;
  run.progress.maxStepPerTask = run.maxSteps;
  run.currentTaskTitle = nextTaskIndex >= 0 ? run.taskRecords[nextTaskIndex].title : '全部任务完成';
}

function computeSummary(run) {
  const total = run.taskRecords.length;
  const success = run.taskRecords.filter((task) => task.status === 'success').length;
  const failed = run.taskRecords.filter((task) => task.status === 'failed').length;
  const successRate = total > 0 ? Number(((success / total) * 100).toFixed(1)) : 0;
  const safetyBase = run.benchmark === 'MobileSafetyBench' ? success : Math.max(success, total - failed);
  const safetyRate = total > 0 ? Number(((safetyBase / total) * 100).toFixed(1)) : 0;
  const avgSteps = run.completedAttempts > 0 ? Number((run.totalConsumedSteps / run.completedAttempts).toFixed(1)) : 0;
  return {
    safetyRate,
    successRate,
    avgSteps,
    runtimeSec: run.runtimeSec
  };
}

function pushTerminal(run, line) {
  run.terminalLines.push(terminalLine(line));
  run.terminalLines = run.terminalLines.slice(-500);
}

function createRunState({ unitId, agent, benchmark, batchSize, outputDir, maxSteps, modelName, autoArenaTaskCount, autoArenaDemandFileName, autoArenaGeneratorModelName }) {
  const taskRecords = createTaskRecords(benchmark, autoArenaTaskCount, autoArenaDemandFileName);
  const workerCount = clamp(Number(batchSize) || 1, 1, 8);
  const stepCap = clamp(Number(maxSteps) || 20, 1, 200);
  const currentTaskTitle = taskRecords[0]?.title || '--';
  return {
    unitId,
    outputDir,
    agent,
    benchmark,
    batchSize: workerCount,
    maxSteps: stepCap,
    modelName,
    autoArenaGeneratorModelName: String(autoArenaGeneratorModelName || ''),
    autoArenaTaskCount: clamp(Number(autoArenaTaskCount) || 0, 0, 500),
    autoArenaDemandFileName: String(autoArenaDemandFileName || ''),
    status: 'running',
    startedAt: Date.now(),
    runtimeSec: 0,
    totalConsumedSteps: 0,
    completedAttempts: 0,
    currentTaskTitle,
    activeApp: 'Home',
    progress: {
      total: taskRecords.length,
      completed: 0,
      success: 0,
      failed: 0,
      currentTaskIndex: 0,
      currentStep: 0,
      maxStepPerTask: stepCap
    },
    metrics: {
      safetyRate: 0,
      successRate: 0,
      avgSteps: 0,
      runtimeSec: 0
    },
    logs: [
      createLog('INFO', `准备启动 ${agent} × ${benchmark} 评测。`),
      createLog('INFO', `模型配置：${modelName}`),
      createLog('INFO', `输出目录：${outputDir}`),
      ...(benchmark === 'AutoArena'
        ? [
            createLog('INFO', `AutoArena 需求文件：${String(autoArenaDemandFileName || '--')}`),
            createLog('INFO', `AutoArena 动态任务数量：${clamp(Number(autoArenaTaskCount) || 0, 0, 500)}`),
            createLog('INFO', `AutoArena 生成模型：${String(autoArenaGeneratorModelName || '--')}`)
          ]
        : []),
      createLog('ACTION', `第 1 个任务载入：${currentTaskTitle || '--'}`)
    ],
    terminalLines: [
      terminalLine(`run init: ${agent} x ${benchmark}`),
      terminalLine(`workers=${workerCount}, output_dir=${outputDir}`),
      terminalLine(`max_steps=${stepCap}, model=${modelName}`),
      ...(benchmark === 'AutoArena'
        ? [
            terminalLine(`autoarena file=${String(autoArenaDemandFileName || '--')}`),
            terminalLine(`autoarena task_count=${clamp(Number(autoArenaTaskCount) || 0, 0, 500)}`),
            terminalLine(`autoarena generator_model=${String(autoArenaGeneratorModelName || '--')}`)
          ]
        : []),
      terminalLine(`task loaded: ${currentTaskTitle || '--'}`)
    ],
    taskRecords
  };
}

function startRun(input) {
  const outputDir = String(input.outputDir || '').trim();
  if (!outputDir) {
    throw new Error('output_dir 不能为空。');
  }

  const existing = runsByOutputDir.get(outputDir);
  if (existing) {
    if (existing.unitId !== input.unitId) {
      runsByUnitId.delete(existing.unitId);
      existing.unitId = input.unitId;
      runsByUnitId.set(input.unitId, existing);
    }
    if (existing.agent !== input.agent || existing.benchmark !== input.benchmark) {
      existing.logs.unshift(createLog('WARN', `检测到 output_dir=${outputDir} 已绑定到 ${existing.agent} × ${existing.benchmark}；本次将继续该历史任务，而不会切换到新的 Agent/Benchmark 组合。`));
      pushTerminal(existing, `resume keeps original config => ${existing.agent} x ${existing.benchmark}`);
    }
    existing.batchSize = clamp(Number(input.batchSize) || existing.batchSize || 1, 1, 8);
    existing.maxSteps = clamp(Number(input.maxSteps) || existing.maxSteps || 20, 1, 200);
    existing.modelName = input.modelName;
    existing.autoArenaGeneratorModelName = String(input.autoArenaGeneratorModelName || existing.autoArenaGeneratorModelName || '');
    existing.autoArenaTaskCount = clamp(Number(input.autoArenaTaskCount) || existing.autoArenaTaskCount || 0, 0, 500);
    existing.autoArenaDemandFileName = String(input.autoArenaDemandFileName || existing.autoArenaDemandFileName || '');
    refreshProgress(existing);

    const nextTaskIndex = getNextTaskIndex(existing);
    if (nextTaskIndex >= 0) {
      existing.status = 'running';
      existing.currentTaskTitle = existing.taskRecords[nextTaskIndex].title;
      existing.logs.unshift(createLog('INFO', `检测到相同 output_dir=${outputDir}，已恢复历史运行状态。`));
      pushTerminal(existing, `resume from output_dir=${outputDir}`);
    } else {
      existing.status = 'done';
      existing.logs.unshift(createLog('INFO', `output_dir=${outputDir} 下的任务均已完成，无需继续运行。`));
      pushTerminal(existing, 'resume requested but no pending/failed task remains');
    }
    existing.logs = existing.logs.slice(0, 100);
    existing.metrics = computeSummary(existing);
    return existing;
  }

  const run = createRunState({
    unitId: input.unitId,
    agent: input.agent,
    benchmark: input.benchmark,
    batchSize: input.batchSize,
    outputDir,
    maxSteps: input.maxSteps,
    modelName: input.modelName,
    autoArenaTaskCount: input.autoArenaTaskCount,
    autoArenaDemandFileName: input.autoArenaDemandFileName,
    autoArenaGeneratorModelName: input.autoArenaGeneratorModelName
  });
  runsByUnitId.set(input.unitId, run);
  runsByOutputDir.set(outputDir, run);
  return run;
}

function tickRun(run) {
  if (!run || run.status !== 'running') return;

  const nextTaskIndex = getNextTaskIndex(run);
  if (nextTaskIndex < 0) {
    run.status = 'done';
    run.currentTaskTitle = '全部任务完成';
    run.metrics = computeSummary(run);
    return;
  }

  const task = run.taskRecords[nextTaskIndex];
  run.progress.currentTaskIndex = nextTaskIndex;
  run.currentTaskTitle = task.title;
  run.runtimeSec += 1;
  run.metrics.runtimeSec = run.runtimeSec;

  const worker = Math.floor(Math.random() * run.batchSize) + 1;
  const action = actionPool[Math.floor(Math.random() * actionPool.length)];
  const app = appPool[Math.floor(Math.random() * appPool.length)];
  const nextStep = run.progress.currentStep + 1;

  run.activeApp = app;
  run.logs.unshift(createLog('ACTION', `${action}，目标应用：${app}`));
  run.logs = run.logs.slice(0, 100);
  pushTerminal(run, `worker-${worker} :: ${action} :: app=${app} :: task=${task.title}`);

  if (nextStep < run.maxSteps) {
    run.progress.currentStep = nextStep;
    return;
  }

  task.attempts += 1;
  run.totalConsumedSteps += run.maxSteps;
  run.completedAttempts += 1;

  const failureProb = scoreFailureProbability(run.agent, run.benchmark);
  const successThisTask = Math.random() > failureProb;
  task.status = successThisTask ? 'success' : 'failed';

  if (successThisTask) {
    run.logs.unshift(createLog('INFO', `任务 ${task.title} 完成，结果：SUCCESS`));
    pushTerminal(run, `worker-${worker} :: task=${task.title} :: SUCCESS`);
  } else {
    run.logs.unshift(createLog('ERROR', `任务 ${task.title} 触发 max_steps=${run.maxSteps} 后仍未完成，记为 FAILED`));
    pushTerminal(run, `worker-${worker} :: task=${task.title} :: FAILED at max_steps=${run.maxSteps}`);
  }

  run.progress.currentStep = 0;
  refreshProgress(run);
  run.metrics = computeSummary(run);

  const hasPending = run.taskRecords.some((item) => item.status === 'pending');
  if (!hasPending) {
    run.status = 'done';
    run.activeApp = 'Home';
    run.logs.unshift(createLog('INFO', `本轮遍历结束：成功 ${run.progress.success}，失败 ${run.progress.failed}。如需断点续跑，请保持 output_dir 不变后重新启动。`));
    pushTerminal(run, `round complete :: success=${run.progress.success} failed=${run.progress.failed}`);
  } else {
    const followingTaskIndex = getNextTaskIndex(run);
    if (followingTaskIndex >= 0) {
      const following = run.taskRecords[followingTaskIndex];
      run.currentTaskTitle = following.title;
      run.logs.unshift(createLog('ACTION', `载入下一个任务：${following.title}`));
      pushTerminal(run, `scheduler :: load next task => ${following.title}`);
    }
  }

  run.logs = run.logs.slice(0, 100);
}

setInterval(() => {
  for (const run of runsByOutputDir.values()) tickRun(run);
}, 1000);

function stopRun(unitId) {
  const run = runsByUnitId.get(unitId);
  if (!run) return null;
  run.status = 'stopped';
  run.logs.unshift(createLog('WARN', '用户已手动停止该测试单元。'));
  pushTerminal(run, 'run stopped by user');
  run.logs = run.logs.slice(0, 100);
  run.metrics = computeSummary(run);
  return run;
}

function resetRun(unitId) {
  const run = runsByUnitId.get(unitId);
  if (!run) return true;
  runsByUnitId.delete(unitId);
  if (run.outputDir) runsByOutputDir.delete(run.outputDir);
  return true;
}

function getRun(unitId) {
  return runsByUnitId.get(unitId) || null;
}

function exportRun(unitId) {
  const run = runsByUnitId.get(unitId);
  if (!run) return null;
  return {
    ...run,
    exportedAt: new Date().toISOString()
  };
}

module.exports = {
  benchmarkTasks,
  startRun,
  stopRun,
  resetRun,
  getRun,
  exportRun
};
