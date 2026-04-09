from __future__ import annotations

from snowl_mobile.adapters.agents.dummy import DummyTextAgentAdapter, DummyVisionAgentAdapter
from snowl_mobile.adapters.agents.mobile_agent_e import MobileAgentEAgentAdapter
from snowl_mobile.adapters.agents.mobile_agent_v3_5 import MobileAgentV35AgentAdapter
from snowl_mobile.adapters.agents.open_autoglm import OpenAutoGLMAgentAdapter
from snowl_mobile.adapters.benchmarks.androidworld import AndroidWorldBenchmarkAdapter
from snowl_mobile.adapters.benchmarks.dummy import DummyBenchmarkAdapter
from snowl_mobile.adapters.benchmarks.mobilesafetybench import MobileSafetyBenchBenchmarkAdapter
from snowl_mobile.adapters.bridges.dummy import DummyVisionBenchmarkBridgeAdapter
from snowl_mobile.adapters.bridges.mobile_agent_e_mobilesafetybench import (
    MobileAgentEMobileSafetyBenchBridgeAdapter,
)
from snowl_mobile.adapters.bridges.mobile_agent_e_androidworld import (
    MobileAgentEAndroidWorldBridgeAdapter,
)
from snowl_mobile.adapters.bridges.mobile_agent_v3_5_mobilesafetybench import (
    MobileAgentV35MobileSafetyBenchBridgeAdapter,
)
from snowl_mobile.adapters.bridges.mobile_agent_v3_5_androidworld import (
    MobileAgentV35AndroidWorldBridgeAdapter,
)
from snowl_mobile.adapters.bridges.open_autoglm_androidworld import (
    OpenAutoGLMAndroidWorldBridgeAdapter,
)
from snowl_mobile.adapters.bridges.open_autoglm_mobilesafetybench import (
    OpenAutoGLMMobileSafetyBenchBridgeAdapter,
)
from snowl_mobile.core.registry import Registry


def register_builtin_adapters(registry: Registry) -> Registry:
    registry.register_agent("dummy_text_agent", DummyTextAgentAdapter)
    registry.register_agent("dummy_vision_agent", DummyVisionAgentAdapter)
    registry.register_agent("mobile_agent_e", MobileAgentEAgentAdapter)
    registry.register_agent("mobile_agent_v3_5", MobileAgentV35AgentAdapter)
    registry.register_agent("open_autoglm", OpenAutoGLMAgentAdapter)
    registry.register_benchmark("androidworld", AndroidWorldBenchmarkAdapter)
    registry.register_benchmark("dummy_benchmark", DummyBenchmarkAdapter)
    registry.register_benchmark("mobilesafetybench", MobileSafetyBenchBenchmarkAdapter)
    registry.register_bridge("dummy_vision__dummy_benchmark", DummyVisionBenchmarkBridgeAdapter)
    registry.register_bridge("mobile_agent_e__androidworld", MobileAgentEAndroidWorldBridgeAdapter)
    registry.register_bridge("mobile_agent_e__mobilesafetybench", MobileAgentEMobileSafetyBenchBridgeAdapter)
    registry.register_bridge("mobile_agent_v3_5__androidworld", MobileAgentV35AndroidWorldBridgeAdapter)
    registry.register_bridge("mobile_agent_v3_5__mobilesafetybench", MobileAgentV35MobileSafetyBenchBridgeAdapter)
    registry.register_bridge("open_autoglm__androidworld", OpenAutoGLMAndroidWorldBridgeAdapter)
    registry.register_bridge("open_autoglm__mobilesafetybench", OpenAutoGLMMobileSafetyBenchBridgeAdapter)
    return registry


def create_builtin_registry() -> Registry:
    return register_builtin_adapters(Registry())
