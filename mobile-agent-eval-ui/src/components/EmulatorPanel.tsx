import { MonitorSmartphone, Play, Power, RefreshCw, Smartphone } from 'lucide-react';
import type { EmulatorSlot, TestUnit } from '../types';

function statusText(status: EmulatorSlot['emulatorStatus']) {
  switch (status) {
    case 'starting':
      return '启动中';
    case 'ready':
      return '已连接';
    case 'error':
      return '启动失败';
    case 'stopped':
      return '已关闭';
    default:
      return '未启动';
  }
}

export function EmulatorPanel({
  unit,
  occupiedAvds,
  onRefreshAvds,
  onSelectAvd,
  onStartEmulator,
  onStopEmulator,
  onToggleView,
  onRefreshXml
}: {
  unit: TestUnit;
  occupiedAvds: Set<string>;
  onRefreshAvds: (id: string) => void;
  onSelectAvd: (id: string, slotIndex: number, avd: string) => void;
  onStartEmulator: (id: string, slotIndex: number) => void;
  onStopEmulator: (id: string, slotIndex: number) => void;
  onToggleView: (id: string, mode: 'screenshot' | 'xml') => void;
  onRefreshXml: (id: string, slotIndex: number) => void;
}) {
  return (
    <div className="emulator-card">
      <div className="panel-head emulator-panel-head">
        <div>
          <div className="panel-title">模拟器区域</div>
          <div className="panel-subtitle">batch_size = {unit.batchSize}，因此当前需要 {unit.batchSize} 个模拟器槽位。每个槽位都需单独选择 AVD 并启动。</div>
        </div>
        <div className="panel-head-actions compact-emulator-actions">
          <button className="ghost-button small refresh-avd-button" onClick={() => onRefreshAvds(unit.id)}>
            <RefreshCw size={14} />
            刷新 AVD 列表
          </button>
          <button className={unit.viewMode === 'screenshot' ? 'tab-button active compact-tab-button' : 'tab-button compact-tab-button'} onClick={() => onToggleView(unit.id, 'screenshot')}>
            Screenshot
          </button>
          <button className={unit.viewMode === 'xml' ? 'tab-button active compact-tab-button' : 'tab-button compact-tab-button'} onClick={() => onToggleView(unit.id, 'xml')}>
            XML
          </button>
        </div>
      </div>

      <div className={unit.batchSize === 1 ? 'emulator-slots-grid cols-single' : unit.batchSize <= 2 ? 'emulator-slots-grid cols-2' : 'emulator-slots-grid cols-4'}>
        {unit.emulatorSlots.slice(0, unit.batchSize).map((slot) => {
          const imageUrl = slot.serial ? `/api/emulators/${unit.id}/slots/${slot.slotIndex}/screenshot?tick=${slot.imageTick}` : '';
          const isSingle = unit.batchSize === 1;
          return (
            <div className={isSingle ? 'emulator-slot-card single-slot' : 'emulator-slot-card'} key={`${unit.id}_${slot.slotIndex}`}>
              <div className="emulator-slot-head">
                <div className="emulator-slot-title-row">
                  <div className="emulator-slot-title">模拟器槽位 {slot.slotIndex + 1}</div>
                  <div className="emulator-slot-meta inline-emulator-meta">Serial：{slot.serial || '--'}</div>
                </div>
                <span className={`status-chip emulator-${slot.emulatorStatus}`}>{statusText(slot.emulatorStatus)}</span>
              </div>

              <div className="field-group compact inline-field-group avd-inline-field">
                <label>选择模拟器 (AVD)</label>
                <select value={slot.selectedAvd} onChange={(e) => onSelectAvd(unit.id, slot.slotIndex, e.target.value)} className="input compact-input inline-field-input">
                  <option value="">请选择本机 AVD</option>
                  {unit.emulatorOptions.map((avd) => {
                    const disabled = occupiedAvds.has(avd) && slot.selectedAvd !== avd;
                    return (
                      <option key={`${slot.slotIndex}_${avd}`} value={avd} disabled={disabled}>
                        {disabled ? `${avd}（已占用）` : avd}
                      </option>
                    );
                  })}
                </select>
              </div>

              <div className="button-row wrap compact-gap">
                <button className="primary-button small" onClick={() => onStartEmulator(unit.id, slot.slotIndex)}>
                  <Play size={14} /> 启动模拟器
                </button>
                <button className="danger-button small" onClick={() => onStopEmulator(unit.id, slot.slotIndex)}>
                  <Power size={14} /> 关闭模拟器
                </button>
                {unit.viewMode === 'xml' ? (
                  <button className="ghost-button small" onClick={() => onRefreshXml(unit.id, slot.slotIndex)}>
                    <RefreshCw size={13} /> 刷新 XML
                  </button>
                ) : null}
              </div>

              {slot.lastError ? <div className="error-banner">{slot.lastError}</div> : null}

              <div className={isSingle ? 'phone-shell single-phone-shell' : 'phone-shell compact-shell'}>
                <div className="phone-topbar">
                  <span>12:01</span>
                  <span className="phone-topbar-status"><span className="live-dot" /> 本地模拟器</span>
                </div>

                {slot.emulatorStatus !== 'ready' ? (
                  <div className={isSingle ? 'phone-placeholder single-placeholder' : 'phone-placeholder compact-placeholder'}>
                    <Smartphone size={34} />
                    <div className="phone-placeholder-title">等待模拟器启动</div>
                    <div className="phone-placeholder-desc">当前展示的是 adb 抓取的实时投影视图，不是可直接鼠标操控的原生窗口。</div>
                  </div>
                ) : unit.viewMode === 'screenshot' ? (
                  <div className={isSingle ? 'phone-screen-wrap single-screen-wrap' : 'phone-screen-wrap compact-screen-wrap'}>
                    <img className="phone-screen-image" src={imageUrl} alt={`emulator slot ${slot.slotIndex + 1}`} />
                  </div>
                ) : (
                  <div className={isSingle ? 'xml-wrap single-xml-wrap' : 'xml-wrap compact-xml-wrap'}>
                    <div className="xml-toolbar">
                      <span><MonitorSmartphone size={14} /> XML 视图</span>
                      <span className="text-soft">自动轮询中</span>
                    </div>
                    <pre className={isSingle ? 'xml-content single-xml-content' : 'xml-content compact-xml-content'}>{slot.xmlText || 'XML 视图开启后会自动轮询；也可以手动点击“刷新 XML”。'}</pre>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
