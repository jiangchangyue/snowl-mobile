import { Layers3, Plus } from 'lucide-react';
import type { TestUnit } from '../types';

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

export function Sidebar({
  units,
  onAdd,
  onScrollTo
}: {
  units: TestUnit[];
  onAdd: () => void;
  onScrollTo: (id: string) => void;
}) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-icon"><Layers3 size={24} /></div>
        <div>
          <div className="brand-title">Snowl Mobile Eval</div>
          <div className="brand-subtitle">手机智能体统一评测平台</div>
        </div>
      </div>

      <button className="primary-button full-width" onClick={onAdd}>
        <Plus size={16} />
        添加新测试单元
      </button>

      <div className="sidebar-list">
        {units.map((unit, index) => (
          <button key={unit.id} className="sidebar-card" onClick={() => onScrollTo(unit.id)}>
            <div className="sidebar-card-top">
              <div className="sidebar-card-title">单元 {index + 1}</div>
              <span className={`status-chip status-${unit.status}`}>{badgeText(unit.status)}</span>
            </div>
            <div className="sidebar-card-meta">{unit.agent} × {unit.benchmark}</div>
            <div className="sidebar-card-submeta">已完成 {unit.progress.completed}/{unit.progress.total} · 批大小 {unit.batchSize}</div>
            <div className="sidebar-card-submeta">输出目录 {unit.outputDir}</div>
          </button>
        ))}
      </div>

      <div className="sidebar-help sidebar-help-small">
        <div className="section-title">说明</div>
        <p>每个测试单元可独立选择 Agent、Benchmark、模型配置、本地 AVD、output_dir 与 max_steps；当 Benchmark 选择 AutoArena 时，还可配置需求文件、动态任务生成数量与独立的出题模型配置。</p>
        <p>在当前平台设计中，batch_size 已经等价于并行模拟器数量；每个并行任务都需要绑定并启动一个模拟器槽位。</p>
        <p>前端填写的 Output Dir 会和 model name 组合成真实目录名，并固定落在 <code>results/&lt;output-dir&gt;-&lt;model-name&gt;</code> 下；相同目录再次启动时，后端会按原生 resume 语义继续运行。</p>
      </div>
    </aside>
  );
}
