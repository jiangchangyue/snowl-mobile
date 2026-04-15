const fs = require('fs');
const path = require('path');

class RunStateStore {
  constructor({ stateFile }) {
    this.stateFile = stateFile;
    this.runs = new Map();
    this.unitToRunId = new Map();
    this._load();
  }

  list() {
    return Array.from(this.runs.values());
  }

  getByRunId(runId) {
    if (!runId) return null;
    return this.runs.get(runId) || null;
  }

  getByUnitId(unitId) {
    if (!unitId) return null;
    const runId = this.unitToRunId.get(unitId);
    return runId ? this.getByRunId(runId) : null;
  }

  upsert(descriptor) {
    const next = {
      ...descriptor,
      updatedAt: new Date().toISOString()
    };
    const previous = this.runs.get(next.runId);
    if (previous && previous.unitId && previous.unitId !== next.unitId) {
      this.unitToRunId.delete(previous.unitId);
    }
    this.runs.set(next.runId, next);
    if (next.unitId) {
      this.unitToRunId.set(next.unitId, next.runId);
    }
    this._persist();
    return next;
  }

  clearUnitBinding(unitId) {
    const existing = this.getByUnitId(unitId);
    if (!existing) return null;
    const updated = {
      ...existing,
      unitId: null
    };
    this.unitToRunId.delete(unitId);
    this.runs.set(updated.runId, updated);
    this._persist();
    return updated;
  }

  _load() {
    if (!fs.existsSync(this.stateFile)) {
      return;
    }
    try {
      const payload = JSON.parse(fs.readFileSync(this.stateFile, 'utf8'));
      const runs = Array.isArray(payload.runs) ? payload.runs : [];
      for (const descriptor of runs) {
        if (!descriptor || typeof descriptor !== 'object' || !descriptor.runId) {
          continue;
        }
        this.runs.set(descriptor.runId, descriptor);
        if (descriptor.unitId) {
          this.unitToRunId.set(descriptor.unitId, descriptor.runId);
        }
      }
    } catch {
      this.runs.clear();
      this.unitToRunId.clear();
    }
  }

  _persist() {
    fs.mkdirSync(path.dirname(this.stateFile), { recursive: true });
    const payload = {
      schemaVersion: 'snowl-mobile.ui-bridge.v1',
      runs: Array.from(this.runs.values())
    };
    const tmpFile = `${this.stateFile}.tmp`;
    fs.writeFileSync(tmpFile, JSON.stringify(payload, null, 2), 'utf8');
    fs.renameSync(tmpFile, this.stateFile);
  }
}

module.exports = {
  RunStateStore
};
