import { useEffect, useMemo, useRef, useState } from 'react';
import { Plus } from 'lucide-react';
import { DashboardHeader } from './components/DashboardHeader';
import { EvaluationUnitCard } from './components/EvaluationUnitCard';
import { Sidebar } from './components/Sidebar';
import {
  exportRun,
  fetchAvds,
  fetchEmulatorStatus,
  fetchRunState,
  fetchXml,
  inspectOutputDir,
  resetRun,
  resetUnitState,
  selectAvd,
  startEmulator,
  startRun,
  stopEmulator,
  stopRun
} from './api';
import type {
  AgentName,
  BenchmarkName,
  EmulatorSlot,
  LogEntry,
  ModelConfig,
  RemoteRunState,
  TestUnit,
  ThemeMode,
  UnitMetrics
} from './types';

function uid(prefix: string) {
  return `${prefix}_${Math.random().toString(36).slice(2, 8)}`;
}

function nowString() {
  return new Date().toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  });
}

function slugify(text: string) {
  return text
    .toLowerCase()
    .replace(/[/\\]+/g, '-')
    .replace(/\s+/g, '-')
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^[._-]+|[._-]+$/g, '') || 'run-output';
}

function buildResolvedOutputDirName(baseOutputDir: string, modelName: string) {
  const base = slugify(baseOutputDir || 'run-output');
  const model = slugify(modelName || 'model');
  return base.endsWith(`-${model}`) ? base : `${base}-${model}`;
}

function createLog(level: LogEntry['level'], message: string): LogEntry {
  return { id: uid('log'), ts: nowString(), level, message };
}

function defaultMetrics(): UnitMetrics {
  return {
    safetyRate: 0,
    successRate: 0,
    avgSteps: 0,
    runtimeSec: 0
  };
}

function createModelConfig(baseUrl = 'http://127.0.0.1:8000/v1', apiKey = 'sk-demo-key', modelName = 'qwen2.5-vl-72b-instruct'): ModelConfig {
  return { baseUrl, apiKey, modelName };
}

function createTerminalBanner(index: number, outputDir: string) {
  return [
    `$ unit-${index}: waiting for evaluation run`,
    '$ emulator slots: initialize and start required devices before running',
    `$ output_dir: ${outputDir}`,
    '$ status: idle'
  ];
}

function createEmulatorSlot(slotIndex: number): EmulatorSlot {
  return {
    slotIndex,
    selectedAvd: '',
    serial: '',
    emulatorPid: null,
    emulatorStatus: 'idle',
    lastError: '',
    imageTick: Date.now(),
    xmlText: ''
  };
}

function resizeEmulatorSlots(slots: EmulatorSlot[], batchSize: number): EmulatorSlot[] {
  const nextSize = Math.max(1, Math.min(batchSize, 8));
  return Array.from({ length: nextSize }, (_, idx) => {
    const existing = slots[idx];
    return existing ? { ...existing, slotIndex: idx } : createEmulatorSlot(idx);
  });
}

function createUnit(index: number): TestUnit {
  const agent: AgentName = index % 3 === 1 ? 'AutoGLM' : index % 3 === 2 ? 'Mobile-Agent-E' : 'Mobile-Agent-V3.5';
  const benchmark: BenchmarkName = index % 2 === 0 ? 'AndroidWorld' : 'MobileSafetyBench';
  const outputDir = `${slugify(agent)}-${slugify(benchmark)}`;

  return {
    id: uid('unit'),
    name: `测试单元 ${index}`,
    agent,
    benchmark,
    batchSize: 1,
    outputDir,
    maxSteps: 20,
    model: createModelConfig('http://127.0.0.1:8000/v1', 'sk-demo-key', benchmark === 'AndroidWorld' ? 'gpt-4.1-mini' : 'qwen2.5-vl-72b-instruct'),
    autoArenaGeneratorModel: createModelConfig('http://127.0.0.1:8001/v1', 'sk-generator-key', 'gpt-4.1-mini'),
    status: 'idle',
    progress: {
      total: 0,
      completed: 0,
      success: 0,
      failed: 0,
      currentTaskIndex: 0,
      currentStep: 0,
      maxStepPerTask: 0
    },
    logs: [
      createLog('INFO', '测试单元已创建，等待配置与启动。'),
      createLog('INFO', 'batch_size 默认值为 1；output_dir 将决定断点续跑与导出文件名。'),
      createLog('INFO', 'max_steps 默认值为 20，用于限制单任务最大交互步数，防止智能体死循环。')
    ],
    terminalLines: createTerminalBanner(index, outputDir),
    metrics: defaultMetrics(),
    viewMode: 'screenshot',
    activeApp: 'Home',
    currentTaskTitle: '--',
    activeTab: 'terminal',
    emulatorSlots: [createEmulatorSlot(0)],
    emulatorOptions: [],
    autoArenaDemandFileName: '',
    autoArenaTaskCount: 0,
    autoArenaTaskCountInput: '0'
  };
}

function applyEmulatorStatus(unit: TestUnit, payloadSlots: EmulatorSlot[]) {
  const visibleSlots = resizeEmulatorSlots(payloadSlots, unit.batchSize).map((slot) => ({
    ...slot,
    imageTick: slot.emulatorStatus === 'ready' ? Date.now() : slot.imageTick,
    xmlText: slot.xmlText || ''
  }));
  return {
    ...unit,
    emulatorSlots: visibleSlots
  };
}

function applyXmlPayload(unit: TestUnit, payload: Array<{ slotIndex: number; xmlText: string }>) {
  if (payload.length === 0) {
    return unit;
  }
  const bySlotIndex = new Map(payload.map((item) => [item.slotIndex, item.xmlText]));
  return {
    ...unit,
    emulatorSlots: unit.emulatorSlots.map((slot) => (
      bySlotIndex.has(slot.slotIndex)
        ? { ...slot, xmlText: bySlotIndex.get(slot.slotIndex) || slot.xmlText }
        : slot
    ))
  };
}

function applyRemoteRunState(unit: TestUnit, run: RemoteRunState): TestUnit {
  return {
    ...unit,
    runId: run.runId || unit.runId,
    status: run.status,
    progress: run.progress,
    logs: run.logs,
    terminalLines: run.terminalLines,
    metrics: run.metrics,
    activeApp: run.activeApp,
    currentTaskTitle: run.currentTaskTitle,
    maxSteps: run.maxSteps || unit.maxSteps,
    bridgeStatus: run.bridgeStatus || unit.bridgeStatus,
    configEcho: run.configEcho || unit.configEcho,
    outputDirProbe: run.outputDirProbe || unit.outputDirProbe,
    summaryData: run.summaryData || unit.summaryData,
    configData: run.configData || unit.configData,
    activeTrials: run.activeTrials || unit.activeTrials,
    model: {
      ...unit.model,
      modelName: run.modelName || unit.model.modelName,
      baseUrl: run.configEcho?.baseUrl || unit.model.baseUrl
    },
    autoArenaDemandFileName: run.autoArenaDemandFileName || unit.autoArenaDemandFileName,
    autoArenaTaskCount: run.autoArenaTaskCount ?? unit.autoArenaTaskCount,
    autoArenaTaskCountInput: String(run.autoArenaTaskCount ?? unit.autoArenaTaskCountInput),
    autoArenaGeneratorModel: run.autoArenaGeneratorModelName
      ? { ...unit.autoArenaGeneratorModel, modelName: run.autoArenaGeneratorModelName }
      : unit.autoArenaGeneratorModel
  };
}

export default function App() {
  const [units, setUnits] = useState<TestUnit[]>([createUnit(1)]);
  const [theme, setTheme] = useState<ThemeMode>(() => {
    const saved = localStorage.getItem('mobile-eval-theme');
    return saved === 'dark' ? 'dark' : 'light';
  });
  const unitsRef = useRef<TestUnit[]>(units);

  useEffect(() => {
    unitsRef.current = units;
  }, [units]);

  useEffect(() => {
    localStorage.setItem('mobile-eval-theme', theme);
  }, [theme]);

  useEffect(() => {
    refreshAllAvds();
  }, []);

  const outputDirProbeKey = units
    .map((unit) => `${unit.id}|${unit.outputDir}|${unit.model.modelName}`)
    .join('||');

  useEffect(() => {
    const timer = window.setTimeout(() => {
      unitsRef.current.forEach(async (unit) => {
        if (!unit.outputDir.trim() || !unit.model.modelName.trim()) {
          setUnits((prev) => prev.map((item) => item.id === unit.id ? {
            ...item,
            outputDirProbe: undefined
          } : item));
          return;
        }
        try {
          const probe = await inspectOutputDir({
            outputDir: unit.outputDir,
            modelName: unit.model.modelName
          });
          setUnits((prev) => prev.map((item) => item.id === unit.id ? {
            ...item,
            outputDirProbe: probe
          } : item));
        } catch {
          // noop
        }
      });
    }, 250);

    return () => window.clearTimeout(timer);
  }, [outputDirProbeKey]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      unitsRef.current.forEach(async (unit) => {
        let latestSlots: EmulatorSlot[] = unit.emulatorSlots;
        try {
          const emulatorState = await fetchEmulatorStatus(unit.id);
          latestSlots = emulatorState.slots;
          setUnits((prev) => prev.map((item) => item.id === unit.id ? applyEmulatorStatus(item, emulatorState.slots) : item));
        } catch {
          // noop
        }

        if (unit.viewMode === 'xml') {
          const readySlots = latestSlots
            .filter((slot) => slot.emulatorStatus === 'ready' && slot.serial)
            .slice(0, unit.batchSize);
          if (readySlots.length > 0) {
            const xmlPayload = await Promise.all(readySlots.map(async (slot) => {
              try {
                const xmlText = await fetchXml(unit.id, slot.slotIndex);
                return { slotIndex: slot.slotIndex, xmlText };
              } catch {
                return null;
              }
            }));
            const normalized = xmlPayload.filter((item): item is { slotIndex: number; xmlText: string } => Boolean(item));
            if (normalized.length > 0) {
              setUnits((prev) => prev.map((item) => item.id === unit.id ? applyXmlPayload(item, normalized) : item));
            }
          }
        }

        try {
          const run = await fetchRunState(unit.id);
          if (!run) return;
          setUnits((prev) => prev.map((item) => {
            if (item.id !== unit.id) return item;
            return applyRemoteRunState(item, run);
          }));
        } catch {
          // noop
        }
      });
    }, 1800);

    return () => window.clearInterval(timer);
  }, []);

  const runningCount = useMemo(() => units.filter((u) => u.status === 'running').length, [units]);
  const finishedCount = useMemo(() => units.filter((u) => u.status === 'done').length, [units]);
  const totalFinishedCases = useMemo(() => units.reduce((acc, u) => acc + u.progress.completed, 0), [units]);
  const boundRunCount = useMemo(() => units.filter((u) => Boolean(u.runId)).length, [units]);

  const occupiedAvds = useMemo(() => {
    const used = new Set<string>();
    units.forEach((unit) => {
      unit.emulatorSlots.forEach((slot) => {
        if ((slot.emulatorStatus === 'ready' || slot.emulatorStatus === 'starting') && slot.selectedAvd) {
          used.add(slot.selectedAvd);
        }
      });
    });
    return used;
  }, [units]);

  function updateUnit(id: string, patch: Partial<TestUnit>) {
    setUnits((prev) => prev.map((unit) => {
      if (unit.id !== id) return unit;
      const next = { ...unit, ...patch };
      return next;
    }));
  }

  function handleBatchSizeChange(id: string, batchSizeInput: number) {
    const batchSize = Math.max(1, Math.min(Number(batchSizeInput) || 1, 8));
    setUnits((prev) => prev.map((unit) => {
      if (unit.id !== id) return unit;
      return {
        ...unit,
        batchSize,
        emulatorSlots: resizeEmulatorSlots(unit.emulatorSlots, batchSize),
        logs: [createLog('INFO', `batch_size 已更新为 ${batchSize}，模拟器槽位已同步调整。`), ...unit.logs].slice(0, 100)
      };
    }));
  }

  async function refreshAllAvds() {
    try {
      const avds = await fetchAvds();
      setUnits((prev) => prev.map((unit) => ({ ...unit, emulatorOptions: avds })));
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'AVD 列表加载失败';
      setUnits((prev) => prev.map((unit) => ({
        ...unit,
        logs: [createLog('ERROR', `读取本地 AVD 列表失败：${msg}`), ...unit.logs].slice(0, 100),
        terminalLines: [...unit.terminalLines, `$ error: ${msg}`].slice(-300)
      })));
    }
  }

  async function refreshAvdsForUnit(id: string) {
    try {
      const avds = await fetchAvds();
      setUnits((prev) => prev.map((unit) => unit.id === id ? { ...unit, emulatorOptions: avds } : unit));
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'AVD 列表加载失败';
      setUnits((prev) => prev.map((unit) => unit.id === id ? {
        ...unit,
        logs: [createLog('ERROR', `读取本地 AVD 列表失败：${msg}`), ...unit.logs].slice(0, 100),
        terminalLines: [...unit.terminalLines, `$ error: ${msg}`].slice(-300)
      } : unit));
    }
  }

  async function handleSelectAvd(id: string, slotIndex: number, avd: string) {
    setUnits((prev) => prev.map((unit) => {
      if (unit.id !== id) return unit;
      const nextSlots = resizeEmulatorSlots(unit.emulatorSlots, unit.batchSize).map((slot) =>
        slot.slotIndex === slotIndex ? { ...slot, selectedAvd: avd, lastError: '' } : slot
      );
      return { ...unit, emulatorSlots: nextSlots };
    }));

    try {
      const state = await selectAvd(id, slotIndex, avd);
      setUnits((prev) => prev.map((unit) => unit.id === id ? {
        ...applyEmulatorStatus(unit, state.slots),
        logs: [createLog('INFO', `槽位 ${slotIndex + 1} 已选择 AVD：${avd}`), ...unit.logs].slice(0, 100),
        terminalLines: [...unit.terminalLines, `$ slot-${slotIndex + 1}: selected avd ${avd}`].slice(-300)
      } : unit));
    } catch (error) {
      const msg = error instanceof Error ? error.message : '选择 AVD 失败';
      setUnits((prev) => prev.map((unit) => unit.id === id ? {
        ...unit,
        logs: [createLog('ERROR', `选择 AVD 失败：${msg}`), ...unit.logs].slice(0, 100),
        terminalLines: [...unit.terminalLines, `$ error: ${msg}`].slice(-300)
      } : unit));
    }
  }

  async function handleStartEmulator(id: string, slotIndex: number) {
    setUnits((prev) => prev.map((unit) => {
      if (unit.id !== id) return unit;
      const nextSlots = unit.emulatorSlots.map((slot) =>
        slot.slotIndex === slotIndex ? { ...slot, emulatorStatus: 'starting', lastError: '' } : slot
      );
      return {
        ...unit,
        emulatorSlots: nextSlots,
        logs: [createLog('INFO', `正在启动槽位 ${slotIndex + 1} 的本地模拟器。`), ...unit.logs].slice(0, 100),
        terminalLines: [...unit.terminalLines, `$ slot-${slotIndex + 1}: starting emulator...`].slice(-300)
      };
    }));

    try {
      const state = await startEmulator(id, slotIndex);
      setUnits((prev) => prev.map((unit) => unit.id === id ? {
        ...applyEmulatorStatus(unit, state.slots),
        logs: [createLog('INFO', `槽位 ${slotIndex + 1} 模拟器已启动。`), ...unit.logs].slice(0, 100),
        terminalLines: [...unit.terminalLines, `$ slot-${slotIndex + 1}: emulator ready`].slice(-300)
      } : unit));
    } catch (error) {
      const msg = error instanceof Error ? error.message : '启动模拟器失败';
      setUnits((prev) => prev.map((unit) => unit.id === id ? {
        ...unit,
        logs: [createLog('ERROR', `启动模拟器失败：${msg}`), ...unit.logs].slice(0, 100),
        terminalLines: [...unit.terminalLines, `$ error: ${msg}`].slice(-300)
      } : unit));
    }
  }

  async function handleStopEmulator(id: string, slotIndex: number) {
    try {
      const state = await stopEmulator(id, slotIndex);
      setUnits((prev) => prev.map((unit) => unit.id === id ? {
        ...applyEmulatorStatus(unit, state.slots),
        logs: [createLog('WARN', `槽位 ${slotIndex + 1} 的模拟器已关闭。`), ...unit.logs].slice(0, 100),
        terminalLines: [...unit.terminalLines, `$ slot-${slotIndex + 1}: emulator stopped`].slice(-300)
      } : unit));
    } catch (error) {
      const msg = error instanceof Error ? error.message : '关闭模拟器失败';
      setUnits((prev) => prev.map((unit) => unit.id === id ? {
        ...unit,
        logs: [createLog('ERROR', `关闭模拟器失败：${msg}`), ...unit.logs].slice(0, 100),
        terminalLines: [...unit.terminalLines, `$ error: ${msg}`].slice(-300)
      } : unit));
    }
  }

  async function handleRefreshXml(id: string, slotIndex: number) {
    try {
      const xml = await fetchXml(id, slotIndex);
      setUnits((prev) => prev.map((unit) => {
        if (unit.id !== id) return unit;
        const nextSlots = unit.emulatorSlots.map((slot) => slot.slotIndex === slotIndex ? { ...slot, xmlText: xml } : slot);
        return {
          ...unit,
          emulatorSlots: nextSlots,
          terminalLines: [...unit.terminalLines, `$ slot-${slotIndex + 1}: xml refreshed`].slice(-300)
        };
      }));
    } catch (error) {
      const msg = error instanceof Error ? error.message : '读取 XML 失败';
      setUnits((prev) => prev.map((unit) => unit.id === id ? {
        ...unit,
        logs: [createLog('ERROR', `读取 XML 失败：${msg}`), ...unit.logs].slice(0, 100),
        terminalLines: [...unit.terminalLines, `$ error: ${msg}`].slice(-300)
      } : unit));
    }
  }

  function handleAutoArenaFileSelected(id: string, file: File | null) {
    const fileName = file?.name || '';
    setUnits((prev) => prev.map((item) => item.id === id ? {
      ...item,
      autoArenaDemandFileName: fileName,
      logs: fileName
        ? [createLog('INFO', `AutoArena 需求文件已选择：${fileName}`), ...item.logs].slice(0, 100)
        : [createLog('INFO', 'AutoArena 需求文件已移除。'), ...item.logs].slice(0, 100),
      terminalLines: fileName
        ? [...item.terminalLines, `$ autoarena: requirement file => ${fileName}`].slice(-300)
        : [...item.terminalLines, '$ autoarena: requirement file removed'].slice(-300)
    } : item));
  }

  function handleAutoArenaTaskCountInputChange(id: string, rawValue: string) {
    const normalized = rawValue.replace(/[^0-9]/g, '');
    setUnits((prev) => prev.map((item) => {
      if (item.id !== id) return item;
      return {
        ...item,
        autoArenaTaskCountInput: normalized,
        autoArenaTaskCount: normalized === '' ? 0 : Math.max(0, Math.min(Number(normalized), 500))
      };
    }));
  }

  function handleApplyAutoArenaTaskCount(id: string) {
    setUnits((prev) => prev.map((item) => {
      if (item.id !== id) return item;
      const inputText = item.autoArenaTaskCountInput.trim();
      const count = inputText === '' ? 0 : Math.max(0, Math.min(Number(inputText), 500));
      if (count <= 0) {
        return {
          ...item,
          autoArenaTaskCount: 0,
          logs: [createLog('WARN', 'AutoArena 任务数量尚未设置，无法生成任务配置。'), ...item.logs].slice(0, 100),
          terminalLines: [...item.terminalLines, '$ autoarena: invalid task count'].slice(-300)
        };
      }
      return {
        ...item,
        autoArenaTaskCount: count,
        autoArenaTaskCountInput: String(count),
        progress: item.status === 'idle' ? { ...item.progress, total: count } : item.progress,
        logs: [createLog('INFO', `AutoArena 已配置为动态生成 ${count} 个测试任务。`), ...item.logs].slice(0, 100),
        terminalLines: [...item.terminalLines, `$ autoarena: planned task_count=${count}`].slice(-300)
      };
    }));
  }

  async function handleStartRun(id: string) {
    const unit = unitsRef.current.find((u) => u.id === id);
    if (!unit) return;
    const resolvedOutputDirName = unit.outputDirProbe?.resolvedOutputDirName || buildResolvedOutputDirName(unit.outputDir, unit.model.modelName);
    const readySerials = unit.emulatorSlots
      .slice(0, unit.batchSize)
      .filter((slot) => slot.emulatorStatus === 'ready' && slot.serial)
      .map((slot) => slot.serial);

    try {
      const run = await startRun({
        unitId: unit.id,
        agent: unit.agent,
        benchmark: unit.benchmark,
        batchSize: unit.batchSize,
        outputDir: resolvedOutputDirName,
        requestedOutputDir: unit.outputDir,
        resolvedOutputDirName,
        maxSteps: unit.maxSteps,
        modelName: unit.model.modelName,
        baseUrl: unit.model.baseUrl,
        apiKey: unit.model.apiKey,
        adbSerials: readySerials,
        autoArenaDemandFileName: unit.autoArenaDemandFileName,
        autoArenaTaskCount: unit.autoArenaTaskCount,
        autoArenaGeneratorModelBaseUrl: unit.autoArenaGeneratorModel.baseUrl,
        autoArenaGeneratorModelApiKey: unit.autoArenaGeneratorModel.apiKey,
        autoArenaGeneratorModelName: unit.autoArenaGeneratorModel.modelName
      });
      setUnits((prev) => prev.map((item) => {
        if (item.id !== id) return item;
        const next = applyRemoteRunState(item, run);
        return {
          ...next,
          terminalLines: [
            ...next.terminalLines,
            `$ run: start ${item.agent} x ${item.benchmark}`,
            `$ run: run_id=${run.runId}`,
            `$ run: output_dir=${run.outputDir || item.outputDir}, max_steps=${run.maxSteps || item.maxSteps}`,
            `$ run: adb_serials=${(run.adbSerials || readySerials).join(', ') || '--'}`,
            ...(item.benchmark === 'AutoArena'
              ? [
                  `$ autoarena: file=${item.autoArenaDemandFileName || '--'}, task_count=${item.autoArenaTaskCount}`,
                  `$ autoarena: generator_model=${item.autoArenaGeneratorModel.modelName}`
                ]
              : [])
          ].slice(-300)
        };
      }));
    } catch (error) {
      const msg = error instanceof Error ? error.message : '启动评测失败';
      setUnits((prev) => prev.map((item) => item.id === id ? {
        ...item,
        logs: [createLog('ERROR', `启动评测失败：${msg}`), ...item.logs].slice(0, 100),
        terminalLines: [...item.terminalLines, `$ error: ${msg}`].slice(-300)
      } : item));
    }
  }

  async function handleStopRun(id: string) {
    try {
      const run = await stopRun(id);
      setUnits((prev) => prev.map((item) => {
        if (item.id !== id) return item;
        const next = applyRemoteRunState(item, run);
        return {
          ...next,
          terminalLines: [...next.terminalLines, '$ run: stopped by user'].slice(-300)
        };
      }));
    } catch (error) {
      const msg = error instanceof Error ? error.message : '停止评测失败';
      setUnits((prev) => prev.map((item) => item.id === id ? {
        ...item,
        logs: [createLog('ERROR', `停止评测失败：${msg}`), ...item.logs].slice(0, 100),
        terminalLines: [...item.terminalLines, `$ error: ${msg}`].slice(-300)
      } : item));
    }
  }

  async function handleResetRun(id: string) {
    const current = unitsRef.current.find((item) => item.id === id);
    if (!current) return;
    const unitIndex = Number(current.name.replace(/\D+/g, '') || '1');

    try {
      await Promise.all([resetRun(id), resetUnitState(id)]);
      const avds = await fetchAvds().catch(() => current.emulatorOptions);
      const fresh = createUnit(unitIndex);
      fresh.id = current.id;
      fresh.name = current.name;
      fresh.emulatorOptions = avds;
      setUnits((prev) => prev.map((item) => item.id === id ? {
        ...fresh,
        logs: [createLog('INFO', '测试单元已重置为默认配置。'), ...fresh.logs].slice(0, 100),
        terminalLines: [...fresh.terminalLines, '$ reset: all parameters restored to defaults'].slice(-300)
      } : item));
    } catch (error) {
      const msg = error instanceof Error ? error.message : '重置失败';
      setUnits((prev) => prev.map((item) => item.id === id ? {
        ...item,
        logs: [createLog('ERROR', `重置失败：${msg}`), ...item.logs].slice(0, 100),
        terminalLines: [...item.terminalLines, `$ error: ${msg}`].slice(-300)
      } : item));
    }
  }

  async function handleExport(id: string) {
    try {
      const { blob, filename } = await exportRun(id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      const msg = error instanceof Error ? error.message : '导出失败';
      setUnits((prev) => prev.map((item) => item.id === id ? {
        ...item,
        logs: [createLog('ERROR', `导出失败：${msg}`), ...item.logs].slice(0, 100),
        terminalLines: [...item.terminalLines, `$ error: ${msg}`].slice(-300)
      } : item));
    }
  }

  function handleRemove(id: string) {
    setUnits((prev) => prev.length === 1 ? prev : prev.filter((unit) => unit.id !== id));
  }

  function addUnit() {
    setUnits((prev) => [...prev, createUnit(prev.length + 1)]);
  }

  function scrollToUnit(id: string) {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function toggleView(id: string, viewMode: 'screenshot' | 'xml') {
    setUnits((prev) => prev.map((item) => item.id === id ? { ...item, viewMode } : item));
  }

  return (
    <div className="app-shell" data-theme={theme}>
      <div className="layout-grid">
        <Sidebar units={units} onAdd={addUnit} onScrollTo={scrollToUnit} />

        <main className="main-content">
      <DashboardHeader
        runningCount={runningCount}
        finishedCount={finishedCount}
        totalFinishedCases={totalFinishedCases}
        boundRunCount={boundRunCount}
        theme={theme}
        onThemeChange={setTheme}
      />

          <div className="units-stack">
            {units.map((unit) => (
              <div key={unit.id} id={unit.id}>
                <EvaluationUnitCard
                  unit={unit}
                  occupiedAvds={occupiedAvds}
                  onUpdate={updateUnit}
                  onBatchSizeChange={handleBatchSizeChange}
                  onStartRun={handleStartRun}
                  onStopRun={handleStopRun}
                  onResetRun={handleResetRun}
                  onRemove={handleRemove}
                  onExport={handleExport}
                  onRefreshAvds={refreshAvdsForUnit}
                  onSelectAvd={handleSelectAvd}
                  onStartEmulator={handleStartEmulator}
                  onStopEmulator={handleStopEmulator}
                  onToggleView={toggleView}
                  onRefreshXml={handleRefreshXml}
                  onAutoArenaFileSelected={handleAutoArenaFileSelected}
                  onAutoArenaTaskCountInputChange={handleAutoArenaTaskCountInputChange}
                  onApplyAutoArenaTaskCount={handleApplyAutoArenaTaskCount}
                />
              </div>
            ))}
          </div>
        </main>
      </div>

      <button className="floating-add-button" onClick={addUnit} title="添加测试单元">
        <Plus size={28} />
      </button>
    </div>
  );
}
