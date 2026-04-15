const path = require('path');

const AGENTS = Object.freeze([
  {
    id: 'AutoGLM',
    backendAgentId: 'open_autoglm',
    displayName: 'AutoGLM'
  },
  {
    id: 'Mobile-Agent-E',
    backendAgentId: 'mobile_agent_e',
    displayName: 'Mobile-Agent-E'
  },
  {
    id: 'Mobile-Agent-V3.5',
    backendAgentId: 'mobile_agent_v3_5',
    displayName: 'Mobile-Agent-V3.5'
  }
]);

const BENCHMARKS = Object.freeze([
  {
    id: 'MobileSafetyBench',
    backendBenchmarkId: 'mobilesafetybench',
    displayName: 'MobileSafetyBench',
    supported: true
  },
  {
    id: 'AndroidWorld',
    backendBenchmarkId: 'androidworld',
    displayName: 'AndroidWorld',
    supported: true
  },
  {
    id: 'AutoArena',
    backendBenchmarkId: 'autoarena',
    displayName: 'AutoArena',
    supported: false,
    availability: 'coming_soon',
    reason: 'AutoArena 当前仅保留前端入口，真实后端运行能力暂未实现。'
  }
]);

const COMBINATIONS = Object.freeze([
  {
    agent: 'AutoGLM',
    benchmark: 'MobileSafetyBench',
    backendAgentId: 'open_autoglm',
    backendBenchmarkId: 'mobilesafetybench',
    configPath: 'configs/runs/autoglm_mobilesafetybench.yml',
    supported: true
  },
  {
    agent: 'AutoGLM',
    benchmark: 'AndroidWorld',
    backendAgentId: 'open_autoglm',
    backendBenchmarkId: 'androidworld',
    configPath: 'configs/runs/autoglm_androidworld.yml',
    supported: true
  },
  {
    agent: 'Mobile-Agent-E',
    benchmark: 'MobileSafetyBench',
    backendAgentId: 'mobile_agent_e',
    backendBenchmarkId: 'mobilesafetybench',
    configPath: 'configs/runs/mobile_agent_e_mobilesafetybench.yml',
    supported: true
  },
  {
    agent: 'Mobile-Agent-E',
    benchmark: 'AndroidWorld',
    backendAgentId: 'mobile_agent_e',
    backendBenchmarkId: 'androidworld',
    configPath: 'configs/runs/mobile_agent_e_androidworld.yml',
    supported: true
  },
  {
    agent: 'Mobile-Agent-V3.5',
    benchmark: 'MobileSafetyBench',
    backendAgentId: 'mobile_agent_v3_5',
    backendBenchmarkId: 'mobilesafetybench',
    configPath: 'configs/runs/mobile_agent_v3_5_mobilesafetybench.yml',
    supported: true
  },
  {
    agent: 'Mobile-Agent-V3.5',
    benchmark: 'AndroidWorld',
    backendAgentId: 'mobile_agent_v3_5',
    backendBenchmarkId: 'androidworld',
    configPath: 'configs/runs/mobile_agent_v3_5_androidworld.yml',
    supported: true
  }
]);

function listSupportedCombinations(repoRoot) {
  const supportedByPair = new Map(
    COMBINATIONS.map((entry) => [`${entry.agent}::${entry.benchmark}`, entry])
  );
  const combinations = [];

  for (const agent of AGENTS) {
    for (const benchmark of BENCHMARKS) {
      const key = `${agent.id}::${benchmark.id}`;
      const supported = supportedByPair.get(key);
      if (supported) {
        combinations.push({
          ...supported,
          resolvedConfigPath: path.resolve(repoRoot, supported.configPath)
        });
        continue;
      }
      combinations.push({
        agent: agent.id,
        benchmark: benchmark.id,
        backendAgentId: agent.backendAgentId,
        backendBenchmarkId: benchmark.backendBenchmarkId,
        configPath: null,
        resolvedConfigPath: null,
        supported: false,
        availability: benchmark.availability || 'unsupported',
        reason: benchmark.reason || '当前组合暂无真实后端实现。'
      });
    }
  }

  return {
    agents: AGENTS,
    benchmarks: BENCHMARKS,
    combinations
  };
}

function resolveCombination({ agent, benchmark }) {
  const exact = COMBINATIONS.find((item) => item.agent === agent && item.benchmark === benchmark);
  if (exact) {
    return { ...exact };
  }
  const benchmarkRecord = BENCHMARKS.find((item) => item.id === benchmark);
  const agentRecord = AGENTS.find((item) => item.id === agent);
  return {
    agent,
    benchmark,
    backendAgentId: agentRecord ? agentRecord.backendAgentId : '',
    backendBenchmarkId: benchmarkRecord ? benchmarkRecord.backendBenchmarkId : '',
    configPath: null,
    supported: false,
    availability: benchmarkRecord && benchmarkRecord.availability ? benchmarkRecord.availability : 'unsupported',
    reason: benchmarkRecord && benchmarkRecord.reason
      ? benchmarkRecord.reason
      : '当前组合暂无真实后端实现。'
  };
}

module.exports = {
  listSupportedCombinations,
  resolveCombination
};
