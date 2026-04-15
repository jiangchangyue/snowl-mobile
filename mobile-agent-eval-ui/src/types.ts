export type AgentName = 'AutoGLM' | 'Mobile-Agent-E' | 'Mobile-Agent-V3.5';
export type BenchmarkName = 'MobileSafetyBench' | 'AndroidWorld' | 'AutoArena';
export type UnitStatus = 'idle' | 'running' | 'stopped' | 'done';
export type ViewMode = 'screenshot' | 'xml';
export type PanelTab = 'terminal' | 'logs' | 'summary' | 'config';
export type EmulatorStatus = 'idle' | 'starting' | 'ready' | 'error' | 'stopped';
export type ThemeMode = 'light' | 'dark';
export type BridgeStatus = 'starting' | 'running' | 'stopping' | 'stopped' | 'finished' | 'failed';

export type ModelConfig = {
  baseUrl: string;
  apiKey: string;
  modelName: string;
};

export type ProgressState = {
  total: number;
  completed: number;
  success: number;
  failed: number;
  currentTaskIndex: number;
  currentStep: number;
  maxStepPerTask: number;
};

export type LogEntry = {
  id: string;
  ts: string;
  level: 'INFO' | 'WARN' | 'ERROR' | 'ACTION';
  message: string;
  source?: string;
};

export type UnitMetrics = {
  safetyRate: number;
  successRate: number;
  avgSteps: number;
  runtimeSec: number;
};

export type RunConfigEcho = {
  runId: string;
  unitId: string;
  agent: AgentName;
  benchmark: BenchmarkName;
  backendAgentId: string;
  backendBenchmarkId: string;
  configPath: string;
  modelName: string;
  baseUrl: string;
  apiKeyRedacted: string;
  maxSteps: number;
  batchSize: number;
  requestedOutputDir: string;
  resolvedOutputDirName: string;
  outputDir: string;
  outputDirAbs: string;
  adbSerials: string[];
  commandPreview: string;
};

export type OutputDirProbe = {
  requestedOutputDir: string;
  modelName: string;
  resolvedOutputDirName: string;
  outputDir: string;
  outputDirRelative: string;
  outputDirAbs: string;
  exportFilename: string;
  exists: boolean;
  nonEmpty: boolean;
  resumable: boolean;
  incompatible: boolean;
  historyFound: boolean;
  shouldResume: boolean;
  completedHistory: boolean;
  backendStatus: string;
  runId: string;
  projectName?: string;
  plannedTasks: number | null;
  successTasks: number | null;
  failedTasks: number | null;
  unfinishedTasks: number | null;
  completedArtifacts: number | null;
  skippedTasks: number | null;
  queuedTasks: number | null;
  runningTasks: number | null;
  retryingTasks: number | null;
  notes: string[];
};

export type DetailField = {
  label: string;
  value: string;
  detail?: string;
};

export type DetailSection = {
  title: string;
  subtitle?: string;
  fields?: DetailField[];
  lines?: string[];
  code?: string;
};

export type ActiveTrialInfo = {
  trialId: string;
  instruction: string;
  device: string;
  avdName: string;
  currentIndex: number;
  totalTrials: number;
  currentStep: number | null;
  logPath?: string;
};

export type RunSummaryData = {
  benchmark: BenchmarkName;
  phase: 'pending' | 'running' | 'final';
  cards: DetailField[];
  sections: DetailSection[];
};

export type RunConfigData = {
  parsedFiles: string[];
  sections: DetailSection[];
};

export type ConnectedEmulatorDevice = {
  serial: string;
  unitId: string | null;
  slotIndex: number | null;
  selectedAvd: string;
  emulatorPid: number | null;
  emulatorStatus: EmulatorStatus | 'ready';
  grpcPort?: number | null;
};

export type EmulatorSlot = {
  slotIndex: number;
  selectedAvd: string;
  serial: string;
  emulatorPid: number | null;
  emulatorStatus: EmulatorStatus;
  lastError: string;
  imageTick: number;
  xmlText: string;
};

export type TestUnit = {
  id: string;
  runId?: string;
  name: string;
  agent: AgentName;
  benchmark: BenchmarkName;
  batchSize: number;
  outputDir: string;
  maxSteps: number;
  model: ModelConfig;
  autoArenaGeneratorModel: ModelConfig;
  status: UnitStatus;
  progress: ProgressState;
  logs: LogEntry[];
  terminalLines: string[];
  metrics: UnitMetrics;
  viewMode: ViewMode;
  activeApp: string;
  currentTaskTitle: string;
  activeTab: PanelTab;
  emulatorSlots: EmulatorSlot[];
  emulatorOptions: string[];
  autoArenaDemandFileName: string;
  autoArenaTaskCount: number;
  autoArenaTaskCountInput: string;
  bridgeStatus?: BridgeStatus;
  configEcho?: RunConfigEcho;
  outputDirProbe?: OutputDirProbe;
  summaryData?: RunSummaryData;
  configData?: RunConfigData;
  activeTrials?: ActiveTrialInfo[];
  lastToast?: string;
};

export type RemoteRunState = {
  unitId: string;
  runId: string;
  outputDir: string;
  outputDirAbs?: string;
  agent: AgentName;
  benchmark: BenchmarkName;
  batchSize: number;
  maxSteps: number;
  modelName: string;
  autoArenaGeneratorModelName?: string;
  status: UnitStatus;
  bridgeStatus?: BridgeStatus;
  backendStatus?: string;
  runtimeSec: number;
  currentTaskTitle: string;
  activeApp: string;
  progress: ProgressState;
  metrics: UnitMetrics;
  logs: LogEntry[];
  terminalLines: string[];
  adbSerials?: string[];
  processId?: number | null;
  processActive?: boolean;
  commandPreview?: string;
  configEcho?: RunConfigEcho;
  outputDirProbe?: OutputDirProbe;
  summaryData?: RunSummaryData;
  configData?: RunConfigData;
  activeTrials?: ActiveTrialInfo[];
  autoArenaDemandFileName?: string;
  autoArenaTaskCount?: number;
};

export type EmulatorStatePayload = {
  unitId: string;
  slots: EmulatorSlot[];
};
