import {
  Cpu,
  Download,
  KeyRound,
  MonitorSmartphone,
  PauseCircle,
  PlayCircle,
  RefreshCw,
  Trash2,
  X
} from 'lucide-react';
import { useEffect, useRef } from 'react';
import type { AgentName, BenchmarkName, DetailSection, PanelTab, TestUnit, ViewMode } from '../types';
import { EmulatorPanel } from './EmulatorPanel';

const AGENTS: AgentName[] = ['AutoGLM', 'Mobile-Agent-E', 'Mobile-Agent-V3.5'];
// const BENCHMARKS: BenchmarkName[] = ['MobileSafetyBench', 'AndroidWorld', 'AutoArena'];
const BENCHMARKS: BenchmarkName[] = ['MobileSafetyBench', 'AndroidWorld'];

const BENCHMARK_HINT: Record<BenchmarkName, string> = {
  MobileSafetyBench: '核心指标：Safety Rate / Refusal Quality / Utility Retention',
  AndroidWorld: '核心指标：Task Success / Step Efficiency / Robustness',
  AutoArena: '核心指标：Dynamic Task Coverage / Safety / Utility'
};

function badgeText(status: TestUnit['status']) {
  switch (status) {
    case 'running':
      return '运行中';
    case 'done':
      return '已完成';
    case 'stopped':
      return '已停止';
    default:
      return '待启动';
  }
}

function TerminalPanel({ unit }: { unit: TestUnit }) {
  const terminalRef = useRef<HTMLDivElement | null>(null);
  const structuredLines = unit.logs.map((log) => {
    const ts = log.ts ? `[${log.ts}] ` : '';
    const source = log.source ? ` (${log.source})` : '';
    return `${ts}[${log.level}] ${log.message}${source}`;
  });

  useEffect(() => {
    if (!terminalRef.current) return;
    terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
  }, [structuredLines]);

  return (
    <div className="terminal-panel" ref={terminalRef}>
      {structuredLines.length === 0 ? (
        <div className="terminal-line muted">$ waiting for evaluation run...</div>
      ) : (
        structuredLines.map((line, idx) => (
          <div key={`${unit.id}_terminal_${idx}`} className="terminal-line">{line}</div>
        ))
      )}
    </div>
  );
}

function LogPanel({ unit }: { unit: TestUnit }) {
  const logRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!logRef.current) return;
    logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [unit.terminalLines]);

  return (
    <div className="terminal-panel" ref={logRef}>
      {unit.terminalLines.length === 0 ? (
        <div className="terminal-line muted">$ waiting for evaluation run...</div>
      ) : (
        unit.terminalLines.map((line, idx) => (
          <div key={`${unit.id}_terminal_${idx}`} className="terminal-line">{line}</div>
        ))
      )}
    </div>
  );
}

function DetailSections({ sections }: { sections: DetailSection[] }) {
  return (
    <div className="detail-sections">
      {sections.map((section, index) => (
        <section key={`${section.title}_${index}`} className="detail-section">
          <div className="section-title">{section.title}</div>
          {section.subtitle ? <div className="detail-section-subtitle">{section.subtitle}</div> : null}
          {section.fields && section.fields.length > 0 ? (
            <div className="detail-field-grid">
              {section.fields.map((field, fieldIndex) => (
                <div key={`${section.title}_${field.label}_${fieldIndex}`} className="detail-field-card">
                  <span>{field.label}</span>
                  <strong>{field.value || '--'}</strong>
                  {field.detail ? <small>{field.detail}</small> : null}
                </div>
              ))}
            </div>
          ) : null}
          {section.lines && section.lines.length > 0 ? (
            <div className="detail-lines">
              {section.lines.map((line, lineIndex) => (
                <p key={`${section.title}_line_${lineIndex}`}>{line}</p>
              ))}
            </div>
          ) : null}
          {typeof section.code === 'string' ? (
            <pre className="detail-code-block"><code>{section.code}</code></pre>
          ) : null}
        </section>
      ))}
    </div>
  );
}

function ClearableInput({
  value,
  type = 'text',
  placeholder,
  onChange,
  onClear
}: {
  value: string;
  type?: 'text' | 'password';
  placeholder?: string;
  onChange: (value: string) => void;
  onClear: () => void;
}) {
  return (
    <div className="clearable-input-wrap">
      <input
        className="input clearable-input"
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
      <button
        type="button"
        className="input-clear-button"
        onClick={onClear}
        title="清空输入"
        aria-label="清空输入"
      >
        <X size={13} />
      </button>
    </div>
  );
}

export function EvaluationUnitCard({
  unit,
  occupiedAvds,
  onUpdate,
  onBatchSizeChange,
  onStartRun,
  onStopRun,
  onResetRun,
  onRemove,
  onExport,
  onRefreshAvds,
  onSelectAvd,
  onStartEmulator,
  onStopEmulator,
  onToggleView,
  onRefreshXml,
  onAutoArenaFileSelected,
  onAutoArenaTaskCountInputChange,
  onApplyAutoArenaTaskCount
}: {
  unit: TestUnit;
  occupiedAvds: Set<string>;
  onUpdate: (id: string, patch: Partial<TestUnit>) => void;
  onBatchSizeChange: (id: string, batchSize: number) => void;
  onStartRun: (id: string) => void;
  onStopRun: (id: string) => void;
  onResetRun: (id: string) => void;
  onRemove: (id: string) => void;
  onExport: (id: string) => void;
  onRefreshAvds: (id: string) => void;
  onSelectAvd: (id: string, slotIndex: number, avd: string) => void;
  onStartEmulator: (id: string, slotIndex: number) => void;
  onStopEmulator: (id: string, slotIndex: number) => void;
  onToggleView: (id: string, mode: ViewMode) => void;
  onRefreshXml: (id: string, slotIndex: number) => void;
  onAutoArenaFileSelected: (id: string, file: File | null) => void;
  onAutoArenaTaskCountInputChange: (id: string, value: string) => void;
  onApplyAutoArenaTaskCount: (id: string) => void;
}) {
  const completedPct = unit.progress.total > 0 ? Math.round((unit.progress.completed / unit.progress.total) * 100) : 0;
  const readyEmulatorCount = unit.emulatorSlots.slice(0, unit.batchSize).filter((slot) => slot.emulatorStatus === 'ready').length;
  const tabs: PanelTab[] = ['terminal', 'logs', 'summary', 'config'];
  const isAutoArena = unit.benchmark === 'AutoArena';
  const outputDirBlocked = Boolean(unit.outputDirProbe?.incompatible);
  const fallbackConfigSections: DetailSection[] = [
    {
      title: '待提交配置',
      fields: [
        { label: 'agent', value: unit.agent },
        { label: 'benchmark', value: unit.benchmark },
        { label: 'model_name', value: unit.model.modelName || '--' },
        { label: 'base_url', value: unit.model.baseUrl || '--' },
        { label: 'api_key', value: unit.model.apiKey ? '***masked***' : '--' },
        { label: 'batch_size', value: String(unit.batchSize) },
        { label: 'max_steps', value: String(unit.maxSteps) },
        { label: 'requested_output_dir', value: unit.outputDir || '--' },
        { label: 'resolved_output_dir', value: unit.outputDirProbe?.outputDir || 'pending' }
      ]
    },
    {
      title: '说明',
      lines: isAutoArena
        ? [
            'AutoArena 当前仅保留前端入口，真实后端运行尚未接通。',
            '因此这里显示的是前端待提交配置，而不是已落盘的真实 project snapshot。'
          ]
        : [
            '尚未启动真实 run，当前仅显示前端待提交参数。',
            '启动后这里会切换为真实 CLI 参数回显、产物路径与 project.snapshot.yml。'
          ]
    }
  ];

  return (
    <section className="unit-card compact-unit-card">
      <div className="unit-card-top compact-unit-top">
        <div>
          <div className="unit-title-row">
            <h2 className="unit-title">{unit.name}</h2>
            <span className={`status-chip status-${unit.status}`}>{badgeText(unit.status)}</span>
            {isAutoArena ? <span className="status-chip status-stopped">Coming Soon</span> : null}
            <div className="unit-subtitle inline-unit-subtitle">{unit.agent} × {unit.benchmark}</div>
          </div>
        </div>

        <div className="button-row wrap compact-unit-actions">
          <button
            className="primary-button small"
            onClick={() => onStartRun(unit.id)}
            disabled={isAutoArena || outputDirBlocked}
            title={isAutoArena
              ? 'AutoArena 当前暂未接通真实后端运行能力。'
              : (outputDirBlocked ? '当前 output_dir 已存在但不是可恢复的 snowl-mobile 目录，请先修改。' : undefined)}
          >
            <PlayCircle size={15} />
            启动评测
          </button>
          <button className="warning-button small" onClick={() => onStopRun(unit.id)}>
            <PauseCircle size={15} />
            停止评测
          </button>
          <button className="ghost-button small" onClick={() => onResetRun(unit.id)}>
            <RefreshCw size={15} />
            重置
          </button>
          <button className="success-button small" onClick={() => onExport(unit.id)}>
            <Download size={15} />
            导出数据
          </button>
          <button className="danger-button small" onClick={() => onRemove(unit.id)}>
            <Trash2 size={15} />
            删除
          </button>
        </div>
      </div>

      <div className="unit-layout-grid">
        <div className="unit-left-column">
          <div className="unit-compact-config-grid">
            <div className="config-card compact-form-card compact-form-row">
              <label>选择手机智能体</label>
              <select value={unit.agent} className="input compact-input inline-form-control" onChange={(e) => onUpdate(unit.id, { agent: e.target.value as AgentName })}>
                {AGENTS.map((agent) => <option key={agent} value={agent}>{agent}</option>)}
              </select>
            </div>

            <div className="config-card compact-form-card compact-form-row">
              <label>选择 Benchmark</label>
              <select value={unit.benchmark} className="input compact-input inline-form-control" onChange={(e) => onUpdate(unit.id, { benchmark: e.target.value as BenchmarkName })}>
                {BENCHMARKS.map((benchmark) => <option key={benchmark} value={benchmark}>{benchmark}</option>)}
              </select>
            </div>

            <div className="config-card compact-form-card compact-form-row">
              <label>batch_size</label>
              <input className="input compact-input inline-form-control" type="number" min={1} max={8} value={unit.batchSize} onChange={(e) => onBatchSizeChange(unit.id, Number(e.target.value || 1))} />
            </div>

            <div className="config-card compact-form-card compact-form-row">
              <label>Max steps</label>
              <input className="input compact-input inline-form-control" type="number" min={1} max={200} value={unit.maxSteps} onChange={(e) => onUpdate(unit.id, { maxSteps: Math.max(1, Math.min(Number(e.target.value || 1), 200)) })} />
            </div>

            <div className="config-card compact-form-card compact-form-row">
              <label><MonitorSmartphone size={14} /> Base URL</label>
              <ClearableInput
                value={unit.model.baseUrl}
                onChange={(value) => onUpdate(unit.id, { model: { ...unit.model, baseUrl: value } })}
                onClear={() => onUpdate(unit.id, { model: { ...unit.model, baseUrl: '' } })}
              />
            </div>

            <div className="config-card compact-form-card compact-form-row">
              <label><KeyRound size={14} /> API Key</label>
              <ClearableInput
                type="password"
                value={unit.model.apiKey}
                onChange={(value) => onUpdate(unit.id, { model: { ...unit.model, apiKey: value } })}
                onClear={() => onUpdate(unit.id, { model: { ...unit.model, apiKey: '' } })}
              />
            </div>

            <div className="config-card compact-form-card compact-form-row">
              <label><Cpu size={14} /> Model Name</label>
              <ClearableInput
                value={unit.model.modelName}
                onChange={(value) => onUpdate(unit.id, { model: { ...unit.model, modelName: value } })}
                onClear={() => onUpdate(unit.id, { model: { ...unit.model, modelName: '' } })}
              />
            </div>

            <div className="config-card compact-form-card compact-form-row">
              <label>Output dir</label>
              <ClearableInput
                value={unit.outputDir}
                placeholder="如 autoglm-mobilesafetybench"
                onChange={(value) => onUpdate(unit.id, { outputDir: value })}
                onClear={() => onUpdate(unit.id, { outputDir: '' })}
              />
            </div>
          </div>

          {isAutoArena ? (
            <div className="autoarena-section compact-autoarena-section">
              <div className="autoarena-section-head">
                <div className="section-title">AutoArena 动态测试配置</div>
                <div className="panel-subtitle">当前版本仅保留前端入口，真实后端运行能力暂未实现。可继续填写预留配置，但“启动评测”不会触发真实 snowl-mobile run。</div>
              </div>

              <div className="autoarena-grid compact-autoarena-grid">
                <div className="config-card compact-form-card">
                  <label>评测需求文件</label>
                  <div className="autoarena-upload-row">
                    <label className="ghost-button upload-button small">
                      上传本地评测需求文件
                      <input
                        key={unit.autoArenaDemandFileName || 'empty-file'}
                        type="file"
                        hidden
                        onChange={(e) => onAutoArenaFileSelected(unit.id, e.target.files?.[0] || null)}
                      />
                    </label>
                    <div className={unit.autoArenaDemandFileName ? 'autoarena-file-badge selected' : 'autoarena-file-badge'}>
                      <span className="file-badge-text">{unit.autoArenaDemandFileName || '未选择需求文件'}</span>
                      {unit.autoArenaDemandFileName ? (
                        <button className="file-remove-button" onClick={() => onAutoArenaFileSelected(unit.id, null)} title="移除当前文件">
                          <X size={14} />
                        </button>
                      ) : null}
                    </div>
                  </div>
                </div>

                <div className="config-card compact-form-card">
                  <label>生成测试任务数量</label>
                  <div className="autoarena-count-row inline-row">
                    <input
                      className="input compact-input"
                      inputMode="numeric"
                      type="text"
                      value={unit.autoArenaTaskCountInput}
                      onChange={(e) => onAutoArenaTaskCountInputChange(unit.id, e.target.value)}
                      placeholder="如 100"
                    />
                    <button className="primary-button small" onClick={() => onApplyAutoArenaTaskCount(unit.id)}>
                      生成任务配置
                    </button>
                  </div>
                </div>
              </div>

              <div className="config-grid three-col autoarena-model-grid compact-autoarena-model-grid">
                <div className="config-card compact-form-card">
                  <label><MonitorSmartphone size={14} /> 动态出题模型 URL</label>
                  <input className="input compact-input" value={unit.autoArenaGeneratorModel.baseUrl} onChange={(e) => onUpdate(unit.id, { autoArenaGeneratorModel: { ...unit.autoArenaGeneratorModel, baseUrl: e.target.value } })} />
                </div>
                <div className="config-card compact-form-card">
                  <label><KeyRound size={14} /> 动态出题模型 KEY</label>
                  <input className="input compact-input" type="password" value={unit.autoArenaGeneratorModel.apiKey} onChange={(e) => onUpdate(unit.id, { autoArenaGeneratorModel: { ...unit.autoArenaGeneratorModel, apiKey: e.target.value } })} />
                </div>
                <div className="config-card compact-form-card">
                  <label><Cpu size={14} /> 动态出题 Model Name</label>
                  <input className="input compact-input" value={unit.autoArenaGeneratorModel.modelName} onChange={(e) => onUpdate(unit.id, { autoArenaGeneratorModel: { ...unit.autoArenaGeneratorModel, modelName: e.target.value } })} />
                </div>
              </div>
            </div>
          ) : null}

          <div className="progress-summary-card">
            <div className="progress-summary-stats">
              <div className="progress-stat-item"><span>总任务</span><strong>{unit.progress.total}</strong></div>
              <div className="progress-stat-item"><span>已完成</span><strong>{unit.progress.completed}</strong></div>
              <div className="progress-stat-item"><span>成功</span><strong>{unit.progress.success}</strong></div>
              <div className="progress-stat-item"><span>失败</span><strong>{unit.progress.failed}</strong></div>
              <div className="progress-stat-item"><span>运行时长</span><strong>{unit.metrics.runtimeSec}s</strong></div>
              <div className="progress-stat-item"><span>已就绪模拟器</span><strong>{readyEmulatorCount}/{unit.batchSize}</strong></div>
            </div>

            <div className="progress-summary-main">
              <div className="progress-inline-row">
                <span className="progress-inline-label">总进度</span>
                <div className="progress-track progress-track-inline"><div className="progress-bar" style={{ width: `${completedPct}%` }} /></div>
                <span className="progress-inline-percent">{completedPct}%</span>
              </div>
              <div className="progress-meta compact-progress-meta">
                <span>当前任务：{unit.currentTaskTitle || '--'}</span>
                <span>当前 Step：{unit.progress.currentStep}/{unit.progress.maxStepPerTask}</span>
                <span>{BENCHMARK_HINT[unit.benchmark]}</span>
              </div>
            </div>
          </div>

          <div className="panel-card output-panel-card compact-output-card">
            <div className="panel-head compact-panel-head">
              <div>
                <div className="panel-title">运行输出</div>
                <div className="panel-subtitle">展示测试任务的输出日志</div>
              </div>
              <div className="tab-row compact-tab-row">
                {tabs.map((tab) => (
                  <button key={tab} className={unit.activeTab === tab ? 'tab-button active compact-tab-button' : 'tab-button compact-tab-button'} onClick={() => onUpdate(unit.id, { activeTab: tab })}>
                    {tab}
                  </button>
                ))}
              </div>
            </div>

            {unit.activeTab === 'terminal' ? <TerminalPanel unit={unit} /> : null}

            {unit.activeTab === 'logs' ? (
              <LogPanel unit={unit} />
            ) : null}

            {unit.activeTab === 'summary' ? (
              <div className="summary-panel">
                {isAutoArena ? (
                  <div className="empty-state-text">AutoArena 当前暂未接入真实后端摘要数据。</div>
                ) : unit.summaryData ? (
                  <>
                    <div className="summary-metrics-grid">
                      {unit.summaryData.cards.map((card, index) => (
                        <div key={`${card.label}_${index}`} className="summary-metric">
                          <span>{card.label}</span>
                          <strong>{card.value}</strong>
                          {card.detail ? <small>{card.detail}</small> : null}
                        </div>
                      ))}
                    </div>
                    <DetailSections sections={unit.summaryData.sections} />
                  </>
                ) : (
                  <div className="empty-state-text">等待 `summary.json`、`events.jsonl` 和已完成 trial 结果。</div>
                )}
              </div>
            ) : null}

            {unit.activeTab === 'config' ? (
              <div className="config-panel-text">
                <DetailSections sections={unit.configData?.sections || fallbackConfigSections} />
              </div>
            ) : null}
          </div>
        </div>

        <EmulatorPanel
          unit={unit}
          occupiedAvds={occupiedAvds}
          onRefreshAvds={onRefreshAvds}
          onSelectAvd={onSelectAvd}
          onStartEmulator={onStartEmulator}
          onStopEmulator={onStopEmulator}
          onToggleView={onToggleView}
          onRefreshXml={onRefreshXml}
        />
      </div>
    </section>
  );
}
