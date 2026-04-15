import { Activity, ChevronDown, Cpu, Eye, Layers3, Settings, Smartphone, Sun, Moon } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import type { ThemeMode } from '../types';

export function DashboardHeader({
  runningCount,
  finishedCount,
  totalFinishedCases,
  boundRunCount,
  theme,
  onThemeChange
}: {
  runningCount: number;
  finishedCount: number;
  totalFinishedCases: number;
  boundRunCount: number;
  theme: ThemeMode;
  onThemeChange: (theme: ThemeMode) => void;
}) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (!menuRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <section className="hero-card">
      <div className="hero-top">
        <div>
          <div className="hero-badge">
            <Smartphone size={14} />
            Mobile Agent Evaluation Dashboard
          </div>
          <h1 className="hero-title">Snowl-Mobile （多手机智能体 × 多 Benchmark 统一评测平台）</h1>
          <p className="hero-description">
            面向已集成的 AutoGLM、Mobile-Agent-E、Mobile-Agent-V3.5 与 MobileSafetyBench、AndroidWorld、AutoArena。
            用户可以在同一页面中动态创建多个测试单元，分别选择 Agent、Benchmark、模型配置与本地模拟器，随后查看设备画面、日志流、terminal 轨迹与评测摘要；若选择 AutoArena，则可额外配置需求文件与动态任务数量。
          </p>
        </div>

        <div className="hero-actions" ref={menuRef}>
          <button className="ghost-button" onClick={() => setOpen((v) => !v)}>
            <Settings size={16} />
            设置
            <ChevronDown size={15} />
          </button>
          {open ? (
            <div className="settings-menu">
              <div className="settings-menu-title">界面主题</div>
              <button className={theme === 'light' ? 'settings-option active' : 'settings-option'} onClick={() => { onThemeChange('light'); setOpen(false); }}>
                <Sun size={15} /> 明亮版
              </button>
              <button className={theme === 'dark' ? 'settings-option active' : 'settings-option'} onClick={() => { onThemeChange('dark'); setOpen(false); }}>
                <Moon size={15} /> 暗黑版
              </button>
            </div>
          ) : null}
        </div>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label"><Cpu size={16} /> 已集成智能体</div>
          <div className="stat-value">3</div>
        </div>
        <div className="stat-card">
          <div className="stat-label"><Layers3 size={16} /> 已集成基准</div>
          <div className="stat-value">3</div>
        </div>
        <div className="stat-card">
          <div className="stat-label"><Activity size={16} /> 运行中单元</div>
          <div className="stat-value accent-cyan">{runningCount}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label"><Eye size={16} /> 已绑定真实 Run</div>
          <div className="stat-value accent-green">{boundRunCount}</div>
        </div>
      </div>

      <div className="overview-grid">
        <div className="overview-card">
          <div className="section-title">当前能力</div>
          <p>任意 Agent × Benchmark 组合展示；支持多测试单元动态扩展；支持多模拟器区域与本地 AVD 选择、启动、关闭、截图/XML 双视图，并预留 AutoArena 动态任务生成入口。</p>
        </div>
        <div className="overview-card">
          <div className="section-title">运行概览</div>
          <p>累计已完成任务数 {totalFinishedCases}；已完成测试单元 {finishedCount}。界面右下角按钮可继续追加新的测试单元。</p>
        </div>
        <div className="overview-card">
          <div className="section-title">适配方式</div>
          <p>当前项目已把“前端展示 + 本地模拟器控制 + 真实 run bridge + 结果解析层”拆开；summary / config / terminal / logs 均优先映射真实产物，不再依赖 mock 结果字段。</p>
        </div>
      </div>
    </section>
  );
}
