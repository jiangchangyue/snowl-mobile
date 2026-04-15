import type {
  AgentName,
  BenchmarkName,
  ConnectedEmulatorDevice,
  EmulatorStatePayload,
  OutputDirProbe,
  RunConfigData,
  RemoteRunState,
  RunConfigEcho
} from './types';

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let text = '';
    try {
      const data = await response.json();
      text = data.error || data.detail || JSON.stringify(data);
    } catch {
      text = await response.text();
    }
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function fetchAvds(): Promise<string[]> {
  const data = await parseResponse<{ avds: string[] }>(await fetch('/api/emulators/avds'));
  return data.avds;
}

export async function fetchEmulatorStatus(unitId: string): Promise<EmulatorStatePayload> {
  return parseResponse<EmulatorStatePayload>(await fetch(`/api/emulators/${unitId}/status`));
}

export async function fetchConnectedEmulators(): Promise<ConnectedEmulatorDevice[]> {
  const data = await parseResponse<{ devices: ConnectedEmulatorDevice[] }>(await fetch('/api/emulators/connected'));
  return data.devices;
}

export async function selectAvd(unitId: string, slotIndex: number, avdName: string): Promise<EmulatorStatePayload> {
  return parseResponse<EmulatorStatePayload>(await fetch('/api/emulators/select', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ unitId, slotIndex, avdName })
  }));
}

export async function startEmulator(unitId: string, slotIndex: number): Promise<EmulatorStatePayload> {
  return parseResponse<EmulatorStatePayload>(await fetch('/api/emulators/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ unitId, slotIndex })
  }));
}

export async function stopEmulator(unitId: string, slotIndex: number): Promise<EmulatorStatePayload> {
  return parseResponse<EmulatorStatePayload>(await fetch('/api/emulators/stop', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ unitId, slotIndex })
  }));
}

export async function resetUnitState(unitId: string): Promise<{ ok: boolean }> {
  return parseResponse<{ ok: boolean }>(await fetch('/api/units/reset', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ unitId })
  }));
}

export async function fetchXml(unitId: string, slotIndex: number): Promise<string> {
  const response = await fetch(`/api/emulators/${unitId}/slots/${slotIndex}/xml`);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.text();
}

export async function startRun(payload: {
  unitId: string;
  agent: string;
  benchmark: string;
  batchSize: number;
  outputDir: string;
  requestedOutputDir?: string;
  resolvedOutputDirName?: string;
  maxSteps: number;
  modelName: string;
  baseUrl: string;
  apiKey: string;
  adbSerials: string[];
  autoArenaDemandFileName?: string;
  autoArenaTaskCount?: number;
  autoArenaGeneratorModelBaseUrl?: string;
  autoArenaGeneratorModelApiKey?: string;
  autoArenaGeneratorModelName?: string;
}): Promise<RemoteRunState> {
  return parseResponse<RemoteRunState>(await fetch('/api/runs/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }));
}

export async function stopRun(unitId: string): Promise<RemoteRunState> {
  return parseResponse<RemoteRunState>(await fetch('/api/runs/stop', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ unitId })
  }));
}

export async function resetRun(unitId: string): Promise<{ ok: boolean }> {
  return parseResponse<{ ok: boolean }>(await fetch('/api/runs/reset', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ unitId })
  }));
}

export async function fetchRunState(unitId: string): Promise<RemoteRunState | null> {
  return parseResponse<RemoteRunState | null>(await fetch(`/api/runs/${unitId}/state`));
}

export async function fetchRunStateByRunId(runId: string): Promise<RemoteRunState | null> {
  return parseResponse<RemoteRunState | null>(await fetch(`/api/runs/id/${runId}/state`));
}

export async function fetchRunConfig(unitId: string): Promise<{
  runId: string;
  unitId: string;
  outputDir: string;
  outputDirAbs: string;
  configEcho: RunConfigEcho;
  configData?: RunConfigData;
  outputDirProbe?: OutputDirProbe;
}> {
  return parseResponse<{
    runId: string;
    unitId: string;
    outputDir: string;
    outputDirAbs: string;
    configEcho: RunConfigEcho;
    configData?: RunConfigData;
    outputDirProbe?: OutputDirProbe;
  }>(await fetch(`/api/runs/${unitId}/config`));
}

export async function inspectOutputDir(payload: {
  outputDir: string;
  modelName: string;
  resolvedOutputDirName?: string;
}): Promise<OutputDirProbe> {
  return parseResponse<OutputDirProbe>(await fetch('/api/runs/output-dir/inspect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }));
}

export async function fetchSupportedRunCatalog(): Promise<{
  agents: Array<{ id: AgentName; backendAgentId: string; displayName: string }>;
  benchmarks: Array<{ id: BenchmarkName; backendBenchmarkId: string; displayName: string; supported?: boolean; availability?: string; reason?: string }>;
  combinations: Array<{
    agent: AgentName;
    benchmark: BenchmarkName;
    backendAgentId: string;
    backendBenchmarkId: string;
    configPath: string | null;
    resolvedConfigPath: string | null;
    supported: boolean;
    availability?: string;
    reason?: string;
  }>;
}> {
  return parseResponse<{
    agents: Array<{ id: AgentName; backendAgentId: string; displayName: string }>;
    benchmarks: Array<{ id: BenchmarkName; backendBenchmarkId: string; displayName: string; supported?: boolean; availability?: string; reason?: string }>;
    combinations: Array<{
      agent: AgentName;
      benchmark: BenchmarkName;
      backendAgentId: string;
      backendBenchmarkId: string;
      configPath: string | null;
      resolvedConfigPath: string | null;
      supported: boolean;
      availability?: string;
      reason?: string;
    }>;
  }>(await fetch('/api/runs/catalog'));
}

export async function exportRun(unitId: string): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(`/api/runs/${unitId}/export`);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  const disposition = response.headers.get('Content-Disposition') || '';
  const match = disposition.match(/filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i);
  const filename = decodeURIComponent(match?.[1] || match?.[2] || `${unitId}.zip`);
  const blob = await response.blob();
  return { blob, filename };
}
