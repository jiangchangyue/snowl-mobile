# snowl-mobile

[English README](README.md)

snowl-mobile 是一个面向 `Mobile Agent x Benchmark x Model x Emulator` 统一编排的评测平台。

当前仓库的真实状态可以直接概括为：

- 平台骨架已经基本成型：配置、契约、registry、planner、scheduler、artifact、device backend、integration toolkit、CLI 都已经落地。
- `mobilesafetybench` 已经作为第一个真实 Benchmark 被接入。
- `androidworld` 现在已经作为真实 benchmark adapter 注册进平台，并支持 benchmark 侧的 `validate-config -> plan -> benchmark-setup -> benchmark-run`。
- `open_autoglm` 已经作为第一个真实 Agent 被接入。
- `mobile_agent_e` 现在也已经作为第二个真实 Agent adapter 注册进平台，并且可以通过平台的 wrap-first subprocess 路径被真实调用。
- `mobile_agent_v3_5` 现在也已经作为第三个真实 Agent adapter 注册进平台，并且已经有了 `mobile_agent_v3_5__mobilesafetybench` 专用 pair bridge，用于打通第一条真实 MobileSafetyBench 闭环。
- `open_autoglm x mobilesafetybench` 已经打通了第一条真实组合主流程：`validate-config -> plan -> run -> summarize`。
- `open_autoglm x androidworld` 现在也已经有了第一条最小真实 pair bridge，重点是先用极少量任务和单设备打通链路，而不是立即追求全量跑通。
- `mobile_agent_e x androidworld` 现在也已经有了专用 pair bridge，复用了同一套 AndroidWorld benchmark adapter、runtime recipe 模式和 artifact 布局。
- `mobile_agent_v3_5 x androidworld` 现在也已经有了专用 pair bridge，复用了同一套 AndroidWorld benchmark/bootstrap/scoring 路径，同时仍然保持 Mobile-Agent-v3.5 自己的 wrapped runner 和 ADB 动作循环。
- 现在 checked-in pair config 已经支持通过 CLI 覆盖模型/运行参数，并且在 `run` 命令下支持多模拟器并行调度；但整体仍然是 in-process bridge 架构，不是最终形态的通用生产系统。

## 当前已经能做什么

- `validate-config`
- `plan`
- `run`
- `summarize`
- `registry` 查看已注册的 agent / benchmark / bridge
- `mobile_agent_e` 的最小配置校验、plan、dry-run，以及平台驱动的 wrapped run
- `mobile_agent_v3_5` 的最小配置校验、plan、dry-run，以及平台驱动的 wrapped run
- `devices list`
- `devices health-check`
- fake device 路径上的 dry-run 与 dummy pipeline
- `existing_device` 模式下通过真实 `adb` 发现并绑定已启动的 Android 模拟器
- `mobile_agent_e__mobilesafetybench` pair bridge，负责在 Mobile-Agent-E subprocess 启动前完成 MobileSafetyBench reset / seed / bootstrap
- `mobile_agent_v3_5__mobilesafetybench` pair bridge，负责在 Mobile-Agent-v3.5 subprocess 前后完成 MobileSafetyBench reset / bootstrap observation / final-state evaluation
- AndroidWorld benchmark 已经完成 registry 注册、真实仓库 task discovery 接入、benchmark-side runtime probe，以及 checked-in configs：
  - `configs/integrations/androidworld/minimal.yml`
  - `configs/runs/androidworld_benchmark.yml`
- AndroidWorld 第一条真实 pair config：
  - `configs/runs/autoglm_androidworld.yml`
- AndroidWorld 统一的 Mobile-Agent-E pair config：
  - `configs/runs/mobile_agent_e_androidworld.yml`
- AndroidWorld 统一的 Mobile-Agent-v3.5 pair config：
  - `configs/runs/mobile_agent_v3_5_androidworld.yml`
- 首个真实组合配置：
  - `configs/runs/autoglm_mobilesafetybench.yml`

## 当前仍然有哪些边界

- 真实组合路径当前是 `in_process bridge`，所以运行 `snowl-mobile run` 的 Python 环境必须同时能 import 两个上游仓库及其依赖。
- `mobile_agent_e` 当前仍然没有平台创建和管理的 dedicated worker env。AndroidWorld 这条 pair bridge 已经可以指向 `ANDROID_WORLD_PYTHON`，但平台还不会替你创建或管理那个解释器。
- `mobile_agent_v3_5` 现在已经有 checked-in real pair config 和 pair bridge，但仍然没有 dedicated worker env。
- `mobile_agent_v3_5` 仍然通过它自己的 ADB loop 在 `MobileSafetyEnv.step()` 之外执行动作，所以 evaluator progress 现在主要依赖 bootstrap/final-state 边界上的对账，而不是完整的逐步原生更新。
- 当前 `mobile_agent_v3_5` wrapper 有意保持对上游决策的忠实性：平台只负责设备绑定、必要的执行翻译、流式日志和产物落盘，不再把 agent 原始动作改写成 benchmark-specific fallback 动作。
- `open_autoglm x androidworld` 现在也收敛成和其他 AndroidWorld pair 一样的统一配置模式：`configs/runs/autoglm_androidworld.yml` 默认就是当前 full suite，smoke run 通过 `SNOWL_ANDROIDWORLD_SUITE_FAMILY=android` 和 `SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend` 这类环境变量来选。
- 真实 full-suite 的 `open_autoglm x androidworld` 运行仍然依赖一个同时能 import AndroidWorld 和 Open-AutoGLM 上游依赖的 Python 环境。
- `mobile_agent_e x androidworld` 现在已经走通同一套 AndroidWorld benchmark/bootstrap/scoring 路径，但当前仍然是 first minimal pair bridge，真实 full-suite 还没有在这个工作区完整验证。
- `configs/runs/mobile_agent_e_androidworld.yml` 是 Mobile-Agent-E × AndroidWorld 的统一 checked-in 配置。它默认面向 full-suite，并且已经通过 `plan` / `fake run` 验证；真实运行仍然依赖一个同时能 import AndroidWorld 和 Mobile-Agent-E 上游依赖的 Python 环境。
- `mobile_agent_v3_5 x androidworld` 现在也已经走通同一套 AndroidWorld benchmark/bootstrap/scoring 路径，但真实长跑/full-suite 还没有在这个工作区完整验证。
- `configs/runs/mobile_agent_v3_5_androidworld.yml` 是 Mobile-Agent-v3.5 × AndroidWorld 的统一 checked-in 配置。它默认面向 full-suite，并且已经通过 `plan` / `fake run` 验证；真实运行仍然依赖一个同时能 import AndroidWorld 和 Mobile-Agent-v3.5 上游依赖的 Python 环境。
- pair run 现在已经支持在同一次 `run` 调用里把多个 `existing_device` 模拟器同时跑满，但 in-process bridge 仍然共享同一个宿主 Python 环境，benchmark-side `benchmark-run` 也还是更简单的单链路路径。
- 当前优先支持 `existing_device`；`managed_avd` 还不是完整方案。
- AndroidWorld full run 现在已经支持和平台其它 real run 一样的同目录 resume：复用同一个 `--output-dir` 重新执行相同命令后，已经完成/跳过的 trial 会被自动复用，之前失败/中止的 trial 会被清理后重新执行。这里是基于 artifact 的 trial 级 resume，不是单个 trial 内部 step 级别的断点续跑。
- Appium、上游 runtime、模型 endpoint 出错时现在能 fail-fast，但自动恢复能力还比较有限。
- 如果你之前在 shell 里执行过 `export MOBILE_AGENT_E_LIGHTWEIGHT_PERCEPTION=1`，仅仅删除某个配置文件里的这一行，并不会清掉当前终端里的环境变量；测试完整感知链前请先执行 `unset MOBILE_AGENT_E_LIGHTWEIGHT_PERCEPTION`。

## 前置准备

运行平台本体至少需要：

- Python `>= 3.11`
- `pip`

运行第一个真实组合至少还需要：

- Android Studio / Android SDK
- `adb` 可用
- 用户自己先手动启动 Android 模拟器
- Appium 可执行
- 一个 OpenAI-compatible 模型服务地址，供 Open-AutoGLM 使用

## 第一次使用：完整步骤

### 1. clone 本仓库

```bash
git clone <your-snowl-mobile-repo-url>
cd snowl-mobile
```

### 2. 创建虚拟环境并安装平台

使用 `venv`：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -e .
```

使用 `conda`：

```bash
conda create -n snowl-mobile python=3.11 -y
conda activate snowl-mobile
pip install --upgrade pip setuptools wheel
pip install -e .
```


安装完成后，后续命令建议直接使用：

- `snowl-mobile ...`
- 或 `python -m snowl_mobile ...`

如果你暂时不安装包，也可以这样运行：

```bash
PYTHONPATH=src python3 -m snowl_mobile ...
```

如果你所在环境很干净、又暂时不能联网，`pip install -e .` 可能因为缺少 `setuptools` backend 而失败。这时可以先直接用 `PYTHONPATH=src` 从源码运行，具体见 `docs/troubleshooting.md`。

### 3. 手动 clone 第三方仓库到固定目录

当前第一条真实闭环要求用户自己手动放置两个上游仓库：

```text
references/agents/Open-AutoGLM/
references/agents/MobileAgent/Mobile-Agent-E/
references/agents/MobileAgent/Mobile-Agent-v3.5/
references/benchmarks/android_world/
references/benchmarks/mobilesafetybench/
```

例如：

```bash
git clone <Open-AutoGLM-url> references/agents/Open-AutoGLM
git clone <MobileAgent-url> references/agents/MobileAgent/Mobile-Agent-v3.5
git clone <MobileSafetyBench-url> references/benchmarks/mobilesafetybench
```

注意：

- Agent 路径当前使用 `references/agents/Open-AutoGLM`
- Benchmark 路径当前使用 `references/benchmarks/mobilesafetybench`
- `mobilesafetybench` 这里请按小写目录使用，避免在 Linux 上因为大小写不一致而失败

### 4. 安装你要使用的真实路径所需的上游依赖

因为当前真实执行路径仍然共用 host Python 环境，所以仅仅 clone 仓库还不够，必须把上游依赖也装进当前这个 Python 环境：

```bash
python -m pip install -r references/agents/Open-AutoGLM/requirements.txt
python -m pip install -r references/benchmarks/mobilesafetybench/requirements.txt
python -m pip install -r references/agents/MobileAgent/Mobile-Agent-E/requirements.txt
python -m pip install openai pillow numpy
```

如果你现在要在平台里使用 AndroidWorld，也请把 `references/benchmarks/android_world` clone 下来。当前它已经可以用于 `validate-config / plan / benchmark-setup / benchmark-run`，并且已经有三条 checked-in pair config：`configs/runs/autoglm_androidworld.yml`、`configs/runs/mobile_agent_e_androidworld.yml` 和 `configs/runs/mobile_agent_v3_5_androidworld.yml`。不过仍然更建议用独立 Python 环境准备 AndroidWorld 依赖，并把 `ANDROID_WORLD_PYTHON` 指向那个环境。

### 5. 填写环境变量

不再需要依赖 `.env.local`。CLI 现在不会自动加载 `.env` / `.env.local`。

平台现在会尽量自动解析这些路径：

- `OPEN_AUTOGLM_HOME`
- `MOBILE_AGENT_E_HOME`
- `MOBILE_AGENT_V3_5_HOME`
- `MOBILE_SAFETY_HOME`
- `ANDROID_WORLD_HOME`
- `APPIUM_BIN`，前提是 `appium` 已经在 `PATH` 中

你通常还需要自己提供的运行时输入主要是：

- `PHONE_AGENT_BASE_URL`
- `PHONE_AGENT_API_KEY`
- `PHONE_AGENT_MODEL`，或者直接用 `--model-name`
- `ANDROID_WORLD_PYTHON`，如果 AndroidWorld 依赖放在单独虚拟环境里
- `ANDROID_SDK_ROOT`

其中：

- 最推荐的方式是直接在 `snowl-mobile run` 里传 `--model-name / --base-url / --api-key / --max-steps / --batch-size`
- 或者你也可以继续自己在 shell 里 `export PHONE_AGENT_* / ANDROID_WORLD_*`
- 模型 provider / `api_style` / modalities 仍然在 run config 的 `models:` 里
- `base_url` 和 `api_key` 当前通过环境变量提供
- `PHONE_AGENT_MODEL` 现在就是默认最小配置使用的模型名
- Mobile-Agent-E 这一侧现在已经有平台侧 env 映射，并会被真实 wrapped run 使用：
- 如果 Mobile-Agent-E 自己那套 reasoning 变量留空，当前 wrapped 路径会自动回退复用 `PHONE_AGENT_BASE_URL`、`PHONE_AGENT_API_KEY`、`PHONE_AGENT_MODEL`
- Mobile-Agent-E 专用的 override 变量有：
  - `MOBILE_AGENT_E_HOME`
  - `MOBILE_AGENT_E_API_KEY`
  - `MOBILE_AGENT_E_BASE_URL`
  - `MOBILE_AGENT_E_REASONING_MODEL`
  - `MOBILE_AGENT_E_CAPTION_API_KEY`
  - `MOBILE_AGENT_E_CAPTION_BASE_URL`
  - `MOBILE_AGENT_E_CAPTION_MODEL`
  - `MOBILE_AGENT_E_CAPTION_CALL_METHOD`
  - `MOBILE_AGENT_E_ADB_PATH`
  - `MOBILE_AGENT_E_PERCEPTION_DEVICE`
  - `MOBILE_AGENT_E_STEP_SLEEP_SEC`
  - `MOBILE_AGENT_E_LIGHTWEIGHT_PERCEPTION`
- 对第一次 smoke 来说，你通常只需要补 `MOBILE_AGENT_E_HOME`；现有 `PHONE_AGENT_*` 可以直接被 Mobile-Agent-E 复用
- 第一次真实 smoke 建议设置 `MOBILE_AGENT_E_LIGHTWEIGHT_PERCEPTION=1`；在这个模式下可以先不填 `MOBILE_AGENT_E_CAPTION_API_KEY`，wrapper 也会改走轻量 OCR / icon stub，而不是完整的 ModelScope 感知链
- 只有当你想让 Mobile-Agent-E 使用不同于 Open-AutoGLM 的 endpoint / model 时，才需要再单独填写 `MOBILE_AGENT_E_BASE_URL`、`MOBILE_AGENT_E_API_KEY`、`MOBILE_AGENT_E_REASONING_MODEL`
- 如果你在 shell 里执行 `adb devices` 正常，但 wrapped run 里仍然找不到设备，优先把 `MOBILE_AGENT_E_ADB_PATH` 指向 SDK 的完整 `adb` 路径，例如 `/Users/<you>/Library/Android/sdk/platform-tools/adb`
- Mobile-Agent-v3.5 现在也已经接入同样的平台侧 env 映射：
- 如果 `MOBILE_AGENT_V3_5_BASE_URL`、`MOBILE_AGENT_V3_5_API_KEY`、`MOBILE_AGENT_V3_5_MODEL` 留空，当前 wrapped 路径会自动回退复用 `PHONE_AGENT_BASE_URL`、`PHONE_AGENT_API_KEY`、`PHONE_AGENT_MODEL`
- Mobile-Agent-v3.5 专用 override 变量有：
  - `MOBILE_AGENT_V3_5_HOME`
  - `MOBILE_AGENT_V3_5_BASE_URL`
  - `MOBILE_AGENT_V3_5_API_KEY`
  - `MOBILE_AGENT_V3_5_MODEL`
  - `MOBILE_AGENT_V3_5_ADB_PATH`
  - `MOBILE_AGENT_V3_5_APP_RESOLVER_API_KEY`
  - `MOBILE_AGENT_V3_5_APP_RESOLVER_BASE_URL`
  - `MOBILE_AGENT_V3_5_APP_RESOLVER_MODEL`
- 对第一次真实 smoke 来说，你通常只需要补 `MOBILE_AGENT_V3_5_HOME`；现有 `PHONE_AGENT_*` 可以直接被 Mobile-Agent-v3.5 复用
- Mobile-Agent-v3.5 的真实 wrapped path 仍然依赖设备侧 ADB Keyboard 风格输入法支持

相关文件：

- `.env.example`
- `configs/runs/autoglm_mobilesafetybench.yml`
- `configs/runs/mobile_agent_v3_5_mobilesafetybench.yml`

### 6. 手动启动 Android 模拟器

当前首个真实闭环优先走 `existing_device`，也就是：

- 平台不会负责替你启动模拟器
- 你必须先自己启动一个已经可用的 emulator

可以用：

- Android Studio
- 或 `emulator -avd <your_avd_name>`

然后确认：

```bash
adb devices
```

你应该能看到类似 `emulator-5554` 的设备。

## 先确认平台能看到什么

### 看 CLI 帮助

```bash
snowl-mobile --help
python -m snowl_mobile.cli --help
```

### 看 registry

```bash
snowl-mobile registry summary
snowl-mobile registry list-agents
snowl-mobile registry list-benchmarks
snowl-mobile registry list-bridges
```

当前你应该至少能看到：

- agent: `mobile_agent_e`
- agent: `mobile_agent_v3_5`
- agent: `open_autoglm`
- benchmark: `androidworld`
- benchmark: `mobilesafetybench`
- bridge: `mobile_agent_e__androidworld`
- bridge: `open_autoglm__androidworld`
- bridge: `open_autoglm__mobilesafetybench`

### 看 device backend

```bash
snowl-mobile devices list --config configs/runs/autoglm_mobilesafetybench.yml --device-mode existing_device
snowl-mobile devices health-check --config configs/runs/autoglm_mobilesafetybench.yml --device-mode existing_device
```

如果你要锁定某一台模拟器：

```bash
snowl-mobile devices list --config configs/runs/autoglm_mobilesafetybench.yml --device-mode existing_device --adb-serial emulator-5554
```

## AndroidWorld Benchmark 侧验证

仓库里现在已经有一个 checked-in AndroidWorld benchmark-side config：

```bash
snowl-mobile registry list-benchmarks --metadata
snowl-mobile validate-config configs/runs/androidworld_benchmark.yml
snowl-mobile plan configs/runs/androidworld_benchmark.yml
snowl-mobile benchmark-setup configs/runs/androidworld_benchmark.yml --output-dir /tmp/snowl-mobile-androidworld-setup
snowl-mobile benchmark-run configs/runs/androidworld_benchmark.yml --output-dir /tmp/snowl-mobile-androidworld-benchmark
```

当前范围：

- task discovery 已经来自真实 AndroidWorld 仓库结构
- AndroidWorld 专有 benchmark 配置现在统一放在 `benchmarks[*].options`
- benchmark-native setup / bootstrap / observation / scoring 已经会落到平台 artifact 目录
- checked-in config 默认是 `device_mode: fake`，所以这套命令可以先作为仓库内 smoke test
- 如果要连真实模拟器，显式加设备覆盖：

```bash
snowl-mobile benchmark-setup configs/runs/androidworld_benchmark.yml --device-mode existing_device --adb-serial emulator-5554 --output-dir /tmp/snowl-mobile-androidworld-setup-real
snowl-mobile benchmark-run configs/runs/androidworld_benchmark.yml --device-mode existing_device --adb-serial emulator-5554 --output-dir /tmp/snowl-mobile-androidworld-benchmark-real
```

- AndroidWorld 要求模拟器用命令行带 gRPC 启动，例如：

```bash
emulator -avd AndroidWorldAvd -no-snapshot -grpc 8554
```

- AndroidWorld 上游还要求这个 AVD 本身是 Android 13 / API 33（`Tiramisu`）。不能只是名字叫 `AndroidWorldAvd`。可以快速检查：

```bash
adb -s emulator-5554 shell getprop ro.build.version.sdk   # 应该输出 33
adb -s emulator-5554 shell getprop ro.boot.qemu.avd_name  # 应该输出 AndroidWorldAvd
```

- `benchmark-run` 现在还不会执行外部 agent，所以即使 benchmark bootstrap 成功，`task_success` 也可能仍然是 `0`

## 第一次真实运行 Open-AutoGLM × AndroidWorld

推荐顺序：

1. 先准备独立 AndroidWorld Python 环境，并把 `ANDROID_WORLD_PYTHON` 指向它。
2. 用命令行带 gRPC 启动 AndroidWorld AVD，并确认它实际是 Android 13 / API 33，而不是 API 34 / Android 14。
3. 用 `adb devices` 确认目标模拟器在线。
4. 对 checked-in real-pair config 先做 `validate-config` 和 `plan`。
5. 先直接执行第一条最小真实 pair run。
6. 如果你想先做 benchmark 侧预检，或者想显式准备一台全新的 emulator，再额外执行 `benchmark-setup`。
7. 最后用 `summarize` 查看结果。

示例：

```bash
emulator -avd AndroidWorldAvd -no-snapshot -grpc 8554
adb devices

snowl-mobile validate-config configs/runs/autoglm_androidworld.yml
snowl-mobile plan configs/runs/autoglm_androidworld.yml

snowl-mobile run configs/runs/autoglm_androidworld.yml \
  --device-mode existing_device \
  --adb-serial emulator-5554 \
  --output-dir /tmp/snowl-mobile-open-autoglm-androidworld

snowl-mobile benchmark-setup configs/runs/androidworld_benchmark.yml \
  --device-mode existing_device \
  --adb-serial emulator-5554 \
  --output-dir /tmp/snowl-mobile-androidworld-setup-real

snowl-mobile summarize /tmp/snowl-mobile-open-autoglm-androidworld
```

当前范围：

- 统一 checked-in run config 现在默认面向当前 full `android_world` suite；如果只想 smoke run，请用 `SNOWL_ANDROIDWORLD_SUITE_FAMILY=android` 和 `SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend`
- pair bridge 负责 AndroidWorld bootstrap、task setup、native scoring、日志和 artifact capture
- direct pair run 现在会为当前 AndroidWorld 任务执行 task-scoped app setup，所以 fresh emulator 不再严格依赖先手跑一次 `benchmark-setup`
- 第一版 step loop 仍然沿用 Open-AutoGLM 的 ADB 设备控制路径，而不是直接改成 AndroidWorld-native JSONAction 执行
- `benchmark-setup` 仍然适合作为可选的 benchmark-side 预检路径，尤其是在你想先看 AndroidWorld 自己的 setup 诊断时
- 最近这条 bridge 也开始把“模型端点连不上”和“AndroidWorld bootstrap 失败”分开报错，并且如果模拟器里已经装过 accessibility forwarder，就会直接复用，不再每个 trial 都强制重新下载 APK
- bridge 现在也会尽量复用模拟器里已经安装过的 task-scoped app，并在 AndroidWorld 读取 `adb shell date` 输出前自动清洗夹杂的 gRPC/adb 噪声

## Open-AutoGLM × AndroidWorld 全量运行

现在 smoke 和 full-suite 共用同一份 checked-in config。

当前 checkout 的行为：

- `configs/runs/autoglm_androidworld.yml` 是统一 canonical config
- 默认使用 `suite_family=android_world`、`tasks=[]`、`max_steps=30`、`timeout_sec=3600`、`max_trial_retries=1`
- smoke run 请通过环境变量覆盖：`SNOWL_ANDROIDWORLD_SUITE_FAMILY=android` 和 `SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend`
- 该配置保持同样的 `artifact level = standard`、`device_mode = existing_device` 和 `open_autoglm__androidworld` bridge；并发度请在运行时用 `--batch-size` 覆盖
- 在当前 AndroidWorld checkout 中，默认 full-suite 会展开成 `148` 个 planned trials

推荐顺序：

1. 先确认最小 config 已经能在目标 emulator 上稳定运行。
2. 继续使用独立的 `ANDROID_WORLD_PYTHON` 环境。
3. 对全新 emulator 先执行一次 `benchmark-setup`。
4. 对同一份 config 在默认 full-suite 模式下先做 `validate-config` 和 `plan`。
5. 用一个新的平台 `--output-dir` 启动 full run。
6. 运行过程中持续查看 `run.log` 和 `summarize`。

命令：

```bash
snowl-mobile validate-config configs/runs/autoglm_androidworld.yml
snowl-mobile plan configs/runs/autoglm_androidworld.yml

snowl-mobile run configs/runs/autoglm_androidworld.yml \
  --device-mode existing_device \
  --adb-serial emulator-5554 \
  --output-dir /tmp/snowl-mobile-open-autoglm-androidworld-full

snowl-mobile summarize /tmp/snowl-mobile-open-autoglm-androidworld-full
```

查看进度和结果：

- `tail -f /tmp/snowl-mobile-open-autoglm-androidworld-full/run.log`
- `snowl-mobile summarize /tmp/snowl-mobile-open-autoglm-androidworld-full`
- `/tmp/snowl-mobile-open-autoglm-androidworld-full/summary.json`
- `/tmp/snowl-mobile-open-autoglm-androidworld-full/events.jsonl`
- `/tmp/snowl-mobile-open-autoglm-androidworld-full/trials/<trial_id>/score.json`
- `/tmp/snowl-mobile-open-autoglm-androidworld-full/trials/<trial_id>/trajectory.json`
- `/tmp/snowl-mobile-open-autoglm-androidworld-full/trials/<trial_id>/raw/open_autoglm_androidworld/`

checkpoint / restart 说明：

- full config 默认把 `SNOWL_ANDROIDWORLD_CHECKPOINT_DIR` 和 `SNOWL_ANDROIDWORLD_OUTPUT_PATH` 留空
- 如果你手动设置它们，bridge 会把这些上游 benchmark 输出复制回每个 trial 的 `raw/open_autoglm_androidworld/` 目录，方便排查
- 直接复用同一个 `--output-dir` 重新执行同样的命令即可 resume；已经完成/跳过的 trial 会被自动复用，失败/中止的 trial 会重新排队执行，部分写入的 trial 目录会从头重跑

当前已知限制：

- 第一版 bridge 仍然通过 Open-AutoGLM 自己的 ADB 路径执行动作，而不是直接走 AndroidWorld-native JSONAction
- 在当前工作区里，真实 full-suite 还没有完全验证通过，因为本机还没有一个能同时 import AndroidWorld 和 Open-AutoGLM 依赖的 Python 解释器

## Mobile-Agent-E × AndroidWorld 第一次运行

如果你想把同样的 AndroidWorld benchmark 支持扩展到 Mobile-Agent-E，优先建议先在同一台 emulator 上把 Open-AutoGLM 的 AndroidWorld smoke 路径跑稳定，再切到 Mobile-Agent-E。

仓库里当前有两份 checked-in config：

- 统一配置：`configs/runs/mobile_agent_e_androidworld.yml`

当前 checkout 下两者的区别：

- 这份统一配置默认跑当前 `android_world` 全量 family，在当前 checkout 中会展开成 `148` 个 planned trials
- 如果要先做 smoke run，就在同一份配置上加环境变量覆盖：`SNOWL_ANDROIDWORLD_SUITE_FAMILY=android`、`SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend`
- 统一配置保持同样的 `artifact level = standard`、`device_mode = existing_device` 和 `mobile_agent_e__androidworld` bridge；并发度请在运行时用 `--batch-size` 覆盖

推荐顺序：

1. 继续使用独立的 `ANDROID_WORLD_PYTHON` 环境。
2. 复用同一台用 `-grpc 8554` 启动的 `AndroidWorldAvd`。
3. 对 fresh emulator 可以先选做一次 `benchmark-setup`。
4. 先在同一份配置上用 smoke override 做 `validate-config` 和 `plan`。
5. 用新的平台 `--output-dir` 启动 run。
6. 运行过程中持续查看 `run.log` 和 `summarize`。

命令：

```bash
SNOWL_ANDROIDWORLD_SUITE_FAMILY=android \
SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend \
snowl-mobile validate-config configs/runs/mobile_agent_e_androidworld.yml

SNOWL_ANDROIDWORLD_SUITE_FAMILY=android \
SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend \
snowl-mobile plan configs/runs/mobile_agent_e_androidworld.yml

SNOWL_ANDROIDWORLD_SUITE_FAMILY=android \
SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend \
snowl-mobile run configs/runs/mobile_agent_e_androidworld.yml \
  --device-mode existing_device \
  --adb-serial emulator-5554 \
  --output-dir /tmp/snowl-mobile-mobile-agent-e-androidworld

snowl-mobile summarize /tmp/snowl-mobile-mobile-agent-e-androidworld
```

对应的默认 full-suite 命令：

```bash
snowl-mobile validate-config configs/runs/mobile_agent_e_androidworld.yml
snowl-mobile plan configs/runs/mobile_agent_e_androidworld.yml

snowl-mobile run configs/runs/mobile_agent_e_androidworld.yml \
  --device-mode existing_device \
  --adb-serial emulator-5554 \
  --output-dir /tmp/snowl-mobile-mobile-agent-e-androidworld-full

snowl-mobile summarize /tmp/snowl-mobile-mobile-agent-e-androidworld-full
```

查看进度和结果：

- `tail -f /tmp/snowl-mobile-mobile-agent-e-androidworld-full/run.log`
- `snowl-mobile summarize /tmp/snowl-mobile-mobile-agent-e-androidworld-full`
- `/tmp/snowl-mobile-mobile-agent-e-androidworld-full/summary.json`
- `/tmp/snowl-mobile-mobile-agent-e-androidworld-full/events.jsonl`
- `/tmp/snowl-mobile-mobile-agent-e-androidworld-full/trials/<trial_id>/score.json`
- `/tmp/snowl-mobile-mobile-agent-e-androidworld-full/trials/<trial_id>/trajectory.json`
- `/tmp/snowl-mobile-mobile-agent-e-androidworld-full/trials/<trial_id>/raw/mobile_agent_e_androidworld/`
- `/tmp/snowl-mobile-mobile-agent-e-androidworld-full/trials/<trial_id>/raw/mobile_agent_e/`

当前已知限制：

- 这条 bridge 仍然保留 Mobile-Agent-E 自己的 ADB action loop，而不是把动作重写成 AndroidWorld-native `JSONAction`
- 在当前工作区里，真实 full-suite 还没有完全验证通过，因为本机还没有一个能同时 import AndroidWorld 和 Mobile-Agent-E 依赖的 Python 解释器
- 最小 AndroidWorld smoke 路径现在也会正确尊重 `MOBILE_AGENT_E_LIGHTWEIGHT_PERCEPTION=1`，因此第一条 bridge 不再为了启动 wrapped runner 就提前强制要求 `torch`

## Mobile-Agent-v3.5 × AndroidWorld 第一次运行

这条路径现在也复用了同一套 AndroidWorld benchmark adapter、benchmark-native bootstrap/scoring 和同目录 resume 语义。Mobile-Agent-v3.5 仍然保持自己的 wrapped runner 和 ADB 动作循环。

仓库里当前有一份统一 checked-in config：

- 统一配置：`configs/runs/mobile_agent_v3_5_androidworld.yml`

当前 checkout 下的行为：

- 这份统一配置默认跑当前 `android_world` 全量 family，在当前 checkout 中会展开成 `148` 个 planned trials
- 如果要先做 smoke run，就在同一份配置上加环境变量覆盖：`SNOWL_ANDROIDWORLD_SUITE_FAMILY=android`、`SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend`
- 统一配置保持同样的 `artifact level = standard`、`device_mode = existing_device` 和 `mobile_agent_v3_5__androidworld` bridge；并发度请在运行时用 `--batch-size` 覆盖

推荐顺序：

1. 继续使用独立的 `ANDROID_WORLD_PYTHON` 环境。
2. 复用同一台用 `-grpc 8554` 启动的 `AndroidWorldAvd`。
3. 对 fresh emulator 可以先选做一次 `benchmark-setup`。
4. 先在同一份配置上用 smoke override 做 `validate-config` 和 `plan`。
5. 用新的平台 `--output-dir` 启动 run。
6. 运行过程中持续查看 `run.log` 和 `summarize`。

命令：

```bash
SNOWL_ANDROIDWORLD_SUITE_FAMILY=android \
SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend \
snowl-mobile validate-config configs/runs/mobile_agent_v3_5_androidworld.yml

SNOWL_ANDROIDWORLD_SUITE_FAMILY=android \
SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend \
snowl-mobile plan configs/runs/mobile_agent_v3_5_androidworld.yml

SNOWL_ANDROIDWORLD_SUITE_FAMILY=android \
SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend \
snowl-mobile run configs/runs/mobile_agent_v3_5_androidworld.yml \
  --device-mode existing_device \
  --adb-serial emulator-5554 \
  --output-dir /tmp/snowl-mobile-mobile-agent-v3-5-androidworld

snowl-mobile summarize /tmp/snowl-mobile-mobile-agent-v3-5-androidworld
```

对应的默认 full-suite 命令：

```bash
snowl-mobile validate-config configs/runs/mobile_agent_v3_5_androidworld.yml
snowl-mobile plan configs/runs/mobile_agent_v3_5_androidworld.yml

snowl-mobile run configs/runs/mobile_agent_v3_5_androidworld.yml \
  --device-mode existing_device \
  --adb-serial emulator-5554 \
  --output-dir /tmp/snowl-mobile-mobile-agent-v3-5-androidworld-full

snowl-mobile summarize /tmp/snowl-mobile-mobile-agent-v3-5-androidworld-full
```

查看进度和结果：

- `tail -f /tmp/snowl-mobile-mobile-agent-v3-5-androidworld-full/run.log`
- `snowl-mobile summarize /tmp/snowl-mobile-mobile-agent-v3-5-androidworld-full`
- `/tmp/snowl-mobile-mobile-agent-v3-5-androidworld-full/summary.json`
- `/tmp/snowl-mobile-mobile-agent-v3-5-androidworld-full/events.jsonl`
- `/tmp/snowl-mobile-mobile-agent-v3-5-androidworld-full/trials/<trial_id>/score.json`
- `/tmp/snowl-mobile-mobile-agent-v3-5-androidworld-full/trials/<trial_id>/trajectory.json`
- `/tmp/snowl-mobile-mobile-agent-v3-5-androidworld-full/trials/<trial_id>/raw/mobile_agent_v3_5_androidworld/`
- `/tmp/snowl-mobile-mobile-agent-v3-5-androidworld-full/trials/<trial_id>/raw/mobile_agent_v3_5/`

当前已知限制：

- 这条 bridge 仍然保留 Mobile-Agent-v3.5 自己的 ADB action loop，而不是把动作重写成 AndroidWorld-native `JSONAction`
- 在当前工作区里，真实 full-suite 还没有完全验证通过，因为本机还没有一个能同时 import AndroidWorld 和 Mobile-Agent-v3.5 依赖的 Python 解释器

## 第一次真实运行 Open-AutoGLM × MobileSafetyBench

### 1. 校验配置

```bash
snowl-mobile validate-config configs/runs/autoglm_mobilesafetybench.yml
```

### 2. 生成运行计划

```bash
snowl-mobile plan configs/runs/autoglm_mobilesafetybench.yml
```

这里应该能明确看到：

- `bridge_id = open_autoglm__mobilesafetybench`
- `pair_recipe_id = open_autoglm_mobilesafetybench_existing_device`

### 3. 执行真实最小运行

```bash
snowl-mobile run configs/runs/autoglm_mobilesafetybench.yml \
  --device-mode existing_device \
  --adb-serial emulator-5554 \
  --output-dir ./tmp/snowl-mobile-real-pair
```

现在 `--output-dir` 本身就是这次 run 的实际目录。CLI 会直接把 `run.log`、`summary.json`、`trials/` 等写到这个目录下，不会再额外套一层时间戳子目录。之后如果你用同一个 `--output-dir` 再次执行同样的命令，平台会自动进入 resume 模式：已完成/跳过的 trial 会被复用，失败或未完成的 trial 会继续跑。

你不需要为了换模型自己手动新建一个新的 YAML。现在仓库已经提供了通用的成对配置，默认做法是：

- 一直使用 `configs/runs/autoglm_mobilesafetybench.yml`
- 通过 `--model-name` 覆盖模型名，或者在 shell 里改 `PHONE_AGENT_MODEL`
- 只有当 pair contract 真变了，才需要去改 YAML 里的 provider / `api_style`

如果你想让平台同时在两台已有模拟器上并行执行，并且哪个设备先空闲就立刻补下一个任务，可以直接这样跑：

```bash
snowl-mobile run configs/runs/autoglm_mobilesafetybench.yml \
  --model-name Qwen2.5-VL-72B-Instruct \
  --base-url https://your-openai-compatible-endpoint/v1 \
  --api-key <your-api-key> \
  --max-steps 20 \
  --batch-size 2 \
  --device-mode existing_device \
  --adb-serial emulator-5556 \
  --adb-serial emulator-5560 \
  --output-dir ./tmp/snowl-mobile-autoglm-mobilesafetybench-batch2
```

当前这个仓库内置配置现在默认是**跑全部任务**的，配置里写的是：

- `task_source.selector = ${SNOWL_TASK_SELECTOR:-all}`

如果你想先做一个小规模 smoke run，而不是直接全量跑：

- 设置 `SNOWL_TASK_SELECTOR='task_category=text_message_sending,task_id=high_risk_001,limit=1'`
- 或者直接修改 `benchmarks[*].task_source.selector`
- `limit=-1` 也表示“不限量”

每个选中的 task 都会被展开成独立 trial。每个 trial 开始前，平台都会重新执行当前配置的 reset 流程（这里是 `restore_snapshot_then_seed`），所以后一个任务不会继承前一个任务留下的状态。

### 4. 查看总结

```bash
snowl-mobile summarize ./tmp/snowl-mobile-real-pair
```

## 实验性真实 pair run：Mobile-Agent-E × MobileSafetyBench

这条路径仍然保留了 Mobile-Agent-E 的 subprocess wrapper，但现在已经切到专用的 `mobile_agent_e_mobilesafetybench` pair bridge。

现在在第一次模型调用之前会先做：

- 对租到的 emulator 恢复 snapshot
- 由 MobileSafetyBench 完成 task seeding 和环境初始化
- 从 `MobileSafetyEnv` 捕获真实 bootstrap observation
- 在 `raw/mobile_agent_e_mobilesafetybench/` 下落 pair 级 raw artifacts
- 然后才启动 Mobile-Agent-E subprocess

真实运行前请先确认：

- `references/agents/MobileAgent/Mobile-Agent-E/` 已存在
- Mobile-Agent-E 的 requirements 已安装到当前 Python 环境，或者第一次 smoke 已启用 `MOBILE_AGENT_E_LIGHTWEIGHT_PERCEPTION=1`
- `PHONE_AGENT_BASE_URL`、`PHONE_AGENT_API_KEY`、`PHONE_AGENT_MODEL` 已经通过 shell export、CLI 的 `--base-url / --api-key / --model-name`，或者直接写入 run config 提供
- 如果关闭 lightweight perception 且仍使用 caption `api` 模式，`MOBILE_AGENT_E_CAPTION_API_KEY` 也已设置
- Android 模拟器已启动，并且 `adb devices` 能看到目标 serial
- 如果任务需要输入文本，设备里已经准备好 ADB Keyboard 一类输入支持
- 如有需要，`MOBILE_AGENT_E_ADB_PATH` 已指向能看到该模拟器的 SDK `adb` 可执行文件
- snapshot restore 之后，当前 wrapped 路径会短暂等待 emulator 重新回到 adb-ready；如果第一次探测仍失败，先等几秒，再换一个新的 `--output-dir` 重跑
- 环境初始化完成后，pair bridge 现在会持续打印 live progress 提示；即使上游 subprocess 正在等待模型响应，终端也不会再长时间完全沉默
- 已完成的 step 现在会增量落盘到 `trial.log`、`steps/*.jpg|xml` 和 `raw/mobile_agent_e_mobilesafetybench/steps/*.console.txt`，而不是等 subprocess 退出后再一次性补齐

统一后的 canonical 配置：

- `configs/runs/mobile_agent_e_mobilesafetybench.yml`

为什么现在可以收成一份：

- 之前的 `minimal` 和 `full` 本质上只差默认 selector 和少量 runtime 参数
- 两者底层结构、adapter、backend、artifact、CLI 流程都一样
- 现在统一文件默认走 full manifest，首次 smoke 通过 `SNOWL_TASK_SELECTOR` 这类 env override 来做

推荐首次运行顺序：

1. 手动启动模拟器
2. 运行 `adb devices`，确认目标 serial 处于 `device`
3. 运行 `snowl-mobile validate-config configs/runs/mobile_agent_e_mobilesafetybench.yml`
4. 运行 `snowl-mobile plan configs/runs/mobile_agent_e_mobilesafetybench.yml`
   这里现在应该能看到 `bridge_id = mobile_agent_e__mobilesafetybench` 和 `pair_recipe_id = mobile_agent_e_mobilesafetybench_existing_device`
5. 直接通过 shell / CLI / run config 提供运行参数：确保 `MOBILE_AGENT_E_HOME` 可解析，设置 `MOBILE_AGENT_E_LIGHTWEIGHT_PERCEPTION=1`；只有当你希望 Mobile-Agent-E 不复用当前默认端点时，才需要额外传 `--base-url / --api-key / --model-name`
6. 导出 `SNOWL_TASK_SELECTOR='task_category=text_message_sending,task_id=low_risk_001,limit=1'` 作为第一次 smoke run
7. 执行真实 1-task smoke run
8. 运行 `snowl-mobile summarize <run_dir>`

命令：

```bash
export SNOWL_TASK_SELECTOR='task_category=text_message_sending,task_id=low_risk_001,limit=1'
snowl-mobile validate-config configs/runs/mobile_agent_e_mobilesafetybench.yml
snowl-mobile plan configs/runs/mobile_agent_e_mobilesafetybench.yml
snowl-mobile run configs/runs/mobile_agent_e_mobilesafetybench.yml \
  --device-mode existing_device \
  --adb-serial emulator-5554 \
  --output-dir ./tmp/snowl-mobile-mobile-agent-e
snowl-mobile summarize ./tmp/snowl-mobile-mobile-agent-e
```

当 smoke 已经能在你的 emulator 和模型 endpoint 上稳定后，再切回 full-manifest 默认行为：

```bash
unset SNOWL_TASK_SELECTOR
snowl-mobile validate-config configs/runs/mobile_agent_e_mobilesafetybench.yml
snowl-mobile plan configs/runs/mobile_agent_e_mobilesafetybench.yml
snowl-mobile run configs/runs/mobile_agent_e_mobilesafetybench.yml \
  --device-mode existing_device \
  --adb-serial emulator-5554 \
  --output-dir ./tmp/snowl-mobile-mobile-agent-e-full
snowl-mobile summarize ./tmp/snowl-mobile-mobile-agent-e-full
```

长跑时查看进度的方法：

- `tail -f ./tmp/snowl-mobile-mobile-agent-e-full/run.log`
- `tail -f ./tmp/snowl-mobile-mobile-agent-e-full/trials/<trial_id>/trial.log`
- 查看 `./tmp/snowl-mobile-mobile-agent-e-full/events.jsonl`
- 查看 `./tmp/snowl-mobile-mobile-agent-e-full/trials/<trial_id>/raw/mobile_agent_e_mobilesafetybench/`
- 查看 `./tmp/snowl-mobile-mobile-agent-e-full/trials/<trial_id>/raw/mobile_agent_e/`
- 如果中断，直接复用同一个 `--output-dir` 重新执行 `snowl-mobile run`，平台会进入 resume

当前限制：

- MobileSafetyBench 的 reset / seed / final-state evaluation 现在已经由 dedicated pair bridge 接管
- 上游依赖栈很重，而且上游 README 仍然更偏向 Python 3.10
- benchmark task context 现在已经会被带进 wrapped task instruction 和 raw artifacts，但 MobileSafetyBench evaluator progress 还没有像 Open-AutoGLM pair bridge 那样逐步原生更新，因为 Mobile-Agent-E 仍然通过它自己的 ADB loop 在 `MobileSafetyEnv.step()` 之外执行动作
- 请先跑 1-task 的 `SNOWL_TASK_SELECTOR` smoke，再跑 full manifest；如果 smoke 还不稳定，full run 只会把这种不稳定按任务数放大
- 当前仍不建议 `batch_size > 1`
- 长跑的稳定性仍然直接依赖 host Python 环境、adb / Appium 稳定性以及模型 endpoint 的可用性；平台现在能 resume 和分类失败，但还不能替你掩盖这些限制
<!-- - 在 macOS 上，`/tmp/...` 实际映射到 `/private/tmp/...`；如果你传了 `--output-dir /tmp/...`，但一时在终端或 Finder 里没看到，优先去 `/private/tmp/...` 下确认 -->
- 当关闭 `MOBILE_AGENT_E_LIGHTWEIGHT_PERCEPTION` 时，第一次完整感知运行可能会先花很久下载或加载 ModelScope OCR / GroundingDINO 资产；这时 step artifact 还没出现是正常的，请直接实时查看 `raw/mobile_agent_e/runner.stdout.txt`
- 如果 wrapped run 现在报 `MODEL_CALL_FAILED`，优先查看 `raw/mobile_agent_e/reasoning_request_diagnostics.json`；runner 会先把 HTTP 状态码、响应体摘要和请求异常写进去，再抛出外层的通用错误

## 实验性真实 pair 路径：Mobile-Agent-v3.5 x MobileSafetyBench

这条路径现在已经走 `mobile_agent_v3_5__mobilesafetybench` 专用 pair bridge。平台负责配置、设备绑定、MobileSafetyBench reset / seed / bootstrap observation、trajectory 与最终评估落盘；Mobile-Agent-v3.5 subprocess wrapper 继续负责截图、prompt 构造、模型调用和 ADB 动作执行。

当前 wrapper 路径有意保持对上游行为的忠实性：平台不会把 Mobile-Agent-v3.5 的动作选择改写成 benchmark-aware fallback 动作，只做运行所必需的执行翻译，以及流式日志和 artifact 落盘。

真实运行前请先确认：

- `references/agents/MobileAgent/Mobile-Agent-v3.5/` 已存在
- 当前 Python 环境已经安装 `openai`、`pillow`、`numpy`
- 已填写 `MOBILE_AGENT_V3_5_HOME`，并且 `MOBILE_AGENT_V3_5_*` 或回退 `PHONE_AGENT_*` endpoint 变量可用
- Android 模拟器已经启动，并且 `adb devices` 能看到目标 serial
- 如果有需要，`MOBILE_AGENT_V3_5_ADB_PATH` 已指向真正能看到该设备的 SDK `adb` 二进制
- 如果任务需要输入文本，设备端已经具备 ADB Keyboard 风格输入法支持

当前 canonical config：

- `configs/runs/mobile_agent_v3_5_mobilesafetybench.yml`

minimal 和 full 的区别：

- 当前 checked-in config 默认 selector 是 `all`，也就是当前 checkout 下的 `250` 个 MobileSafetyBench 任务
- 同一个文件可以通过 `SNOWL_TASK_SELECTOR='task_category=text_message_sending,task_id=low_risk_001,limit=1'` 切成 1-task smoke
- 当前 checked-in config 保持 `timeout_sec=2400`、`artifact level = standard`、`device_mode = existing_device`、`max_trial_retries = 1`，不再额外维护第二个 smoke YAML；并发度请在运行时用 `--batch-size` 覆盖

建议第一次这样跑：

1. 手动启动模拟器。
2. 执行 `adb devices`，确认目标 serial 状态是 `device`。
3. 先导出一任务 `SNOWL_TASK_SELECTOR`。
4. 只有 smoke 稳定后，再 `unset SNOWL_TASK_SELECTOR` 切回 full manifest 默认行为。
5. 每次跑完都执行一次 `snowl-mobile summarize <run_dir>`。

最小 smoke 命令：

```bash
export SNOWL_TASK_SELECTOR='task_category=text_message_sending,task_id=low_risk_001,limit=1'
snowl-mobile validate-config configs/runs/mobile_agent_v3_5_mobilesafetybench.yml
snowl-mobile plan configs/runs/mobile_agent_v3_5_mobilesafetybench.yml
snowl-mobile run configs/runs/mobile_agent_v3_5_mobilesafetybench.yml \
  --device-mode existing_device \
  --adb-serial emulator-5554 \
  --output-dir ./tmp/snowl-mobile-mobile-agent-v3-5-smoke
snowl-mobile summarize ./tmp/snowl-mobile-mobile-agent-v3-5-smoke
unset SNOWL_TASK_SELECTOR
```

canonical full run 命令：

```bash
snowl-mobile validate-config configs/runs/mobile_agent_v3_5_mobilesafetybench.yml
snowl-mobile plan configs/runs/mobile_agent_v3_5_mobilesafetybench.yml
snowl-mobile run configs/runs/mobile_agent_v3_5_mobilesafetybench.yml \
  --device-mode existing_device \
  --adb-serial emulator-5554 \
  --output-dir ./tmp/snowl-mobile-mobile-agent-v3-5-full
snowl-mobile summarize ./tmp/snowl-mobile-mobile-agent-v3-5-full
```

如果你只想验证平台主链而不碰真实设备，可以先跑 fake mode：

```bash
export SNOWL_TASK_SELECTOR='task_category=text_message_sending,task_id=low_risk_001,limit=1'
snowl-mobile run configs/runs/mobile_agent_v3_5_mobilesafetybench.yml \
  --device-mode fake \
  --output-dir ./tmp/snowl-mobile-mobile-agent-v3-5-fake
unset SNOWL_TASK_SELECTOR
```

重点查看这些产物：

- `./tmp/snowl-mobile-mobile-agent-v3-5-full/run.log`
- `./tmp/snowl-mobile-mobile-agent-v3-5-full/summary.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/trial.log`
- `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/score.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/trajectory.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5_mobilesafetybench/bridge_request.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5_mobilesafetybench/environment_init.console.txt`
- `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5_mobilesafetybench/bootstrap_observation.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5_mobilesafetybench/final_observation.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5_mobilesafetybench/final_result.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5/request.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5/task_payload.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5/benchmark_context.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5/runner_request.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5/runner_result.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5/wrapped_result.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5/steps/0001.model_response.json`

长跑时建议这样看进度：

- `tail -f ./tmp/snowl-mobile-mobile-agent-v3-5-full/run.log`
- `tail -f ./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/trial.log`
- 查看 `./tmp/snowl-mobile-mobile-agent-v3-5-full/events.jsonl`
- 查看 `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5_mobilesafetybench/`
- 查看 `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5/`
- 如果中途中断，直接用同一个 `--output-dir ./tmp/snowl-mobile-mobile-agent-v3-5-full` 重新执行 `snowl-mobile run ...` 来 resume

当前已知限制：

- 逐步 evaluator progress 现在仍然是不完整的，因为 Mobile-Agent-v3.5 通过它自己的 ADB loop 在 `MobileSafetyEnv.step()` 之外执行动作
- benchmark-aware app alias 现在已经进了 bridge，但仍然只是最小覆盖
- 这条 wrapped path 仍然依赖 host Python 环境和 `mobile_use` 的上游依赖
- 请先跑一任务 `SNOWL_TASK_SELECTOR` 再跑 full manifest；如果 smoke 还不稳定，full run 只会把这种不稳定按任务数放大
- 当前仍不建议 `batch_size > 1`
- 长跑稳定性仍然直接依赖 host Python、adb / Appium 稳定性以及模型 endpoint 可用性；平台可以 resume 和分类失败，但不会替你掩盖这些外部限制
- 某些模拟器上，外层 snapshot restore 或 adb health probe 可能在 pair bridge 开始前就卡住；如果出现这种情况，先重启模拟器、确认 `adb devices`，再回到一任务 `SNOWL_TASK_SELECTOR` smoke 重试

## 关键字段去哪里改

- Agent 名字：
  - `agents[*].id`
- Benchmark 名字：
  - `benchmarks[*].id`
- 模型 provider / model id / modalities：
  - `models[*]`
- device mode：
  - `devices.device_mode`
  - 也可以用 `--device-mode` 覆盖
- adb serial：
  - `devices.adb_serials`
  - 或 `--adb-serial`
- batch size：
  - `runtime.batch_size`
- task limit / selector：
  - `benchmarks[*].task_source.selector`
  - 默认是 `all`；如果想采样，写 `limit=N`；如果想显式表达“跑全部”，也可以写 `limit=-1`
- artifact level：
  - `artifacts.level`

## 运行中和运行后去哪里看

运行中：

- 终端 stdout 会打印进度与错误
- run 目录是：
  - 你显式传入的 `--output-dir`
  - 或者未指定时默认使用 `runs/<run_name_slug>/`
- run 级日志在：
  - `<run_dir>/run.log`
  - 这里现在是偏总览的日志：任务序号、instruction、trial 路径、reset 状态、执行开始、评估开始/完成以及最终结果
- trial 级日志在：
  - `<run_dir>/trials/<trial_id>/trial.log`
  - 这里记录单个 task 的细粒度执行过程
  - 在 Mobile-Agent-E 这条 pair 路径里，现在还会补进重建后的 step 摘要，例如 manager thought、当前 subgoal、action thought、action description、selected action 和 reflection outcome

运行后：

- 总结：
  - `<run_dir>/summary.json`
- 计划：
  - `<run_dir>/plan.json`
- 事件流：
  - `<run_dir>/events.jsonl`
- 单 trial 元数据：
  - `<run_dir>/trials/<trial_id>/meta.json`
  - 主要是平台内部的 trial 生命周期、错误历史和重试信息
- 单 trial 实际运行配方：
  - `<run_dir>/trials/<trial_id>/runtime_recipe.json`
  - 记录这次 trial 实际使用的 bridge / backend / reset / worker 配置
- 单 trial 分数：
  - `<run_dir>/trials/<trial_id>/score.json`
  - 这里是平台映射后的 MobileSafetyBench 评估结果
- 单 trial 轨迹：
  - `<run_dir>/trials/<trial_id>/trajectory.json`
  - 这里现在是面向用户的简版轨迹：Instruction、Thought、Action、Action Input、Observation 摘要，以及截图/XML 路径
- 原始模型输出：
  - `<run_dir>/trials/<trial_id>/raw/open_autoglm_mobilesafetybench/steps/0001.model_response.txt`
  - `<run_dir>/trials/<trial_id>/raw/open_autoglm_mobilesafetybench/steps/0001.model_response.json`
  - 这些路径现在也会直接出现在 `trajectory.json` 里
- Mobile-Agent-E wrapped-agent 原始输出：
  - `<run_dir>/trials/<trial_id>/raw/mobile_agent_e/request.json`
  - `<run_dir>/trials/<trial_id>/raw/mobile_agent_e/runner_request.json`
  - `<run_dir>/trials/<trial_id>/raw/mobile_agent_e/runner_result.json`
  - `<run_dir>/trials/<trial_id>/raw/mobile_agent_e/wrapped_result.json`
  - `<run_dir>/trials/<trial_id>/raw/mobile_agent_e/steps/0001.model_response.json`
- Mobile-Agent-E pair bridge 的逐步 transcript 原始输出：
  - `<run_dir>/trials/<trial_id>/raw/mobile_agent_e_mobilesafetybench/steps/0001.console.txt`
  - `<run_dir>/trials/<trial_id>/raw/mobile_agent_e_mobilesafetybench/steps/0001.model_response.txt`
  - `<run_dir>/trials/<trial_id>/raw/mobile_agent_e_mobilesafetybench/steps/0001.model_response.json`
- 每步截图和 XML：
  - `<run_dir>/trials/<trial_id>/steps/0001.png`
  - `<run_dir>/trials/<trial_id>/steps/0001.xml`
  - 在 Mobile-Agent-E 这条 pair 路径里，现在会优先把“动作后的观测”落到这些 step 产物里；如果上游 runner 也生成了同名 XML sidecar，最后一步的最终截图/XML 也会一起保留下来

## 手工接入与 Codex 辅助接入

Agent：

- `docs/integrate-agent.md`
- `docs/prompts/integrate-agent-prompt.md`

Benchmark：

- `docs/integrate-benchmark.md`
- `docs/prompts/integrate-benchmark-prompt.md`

Pair-specific bridge：

- `docs/integrate-pair.md`

其他操作文档：

- `docs/integration-readiness-checklist.md`
- `docs/quickstart.md`
- `docs/troubleshooting.md`

## 目录结构

```text
src/snowl_mobile/   核心平台代码
configs/            真实运行配置与集成示例配置
docs/               用户文档与接入文档
examples/           脚手架示例与未来集成示例
references/         用户手动 clone 的第三方仓库
tests/              单测、集成测试、e2e
runs/               默认运行产物目录
scripts/            开发辅助脚本
```

## 常用命令

```bash
make lint
make test
make validate-example
make plan-example
make dry-run-example
make devices-list-example
make devices-health-check-example
make run-example
```

## 更具体的真实集成说明

- `docs/integrations/mobile-agent-e.md`
- `docs/integrations/mobile-agent-v3-5.md`
- `docs/integrations/open-autoglm.md`
- `docs/integrations/mobilesafetybench.md`
- `docs/integrations/open-autoglm-mobilesafetybench.md`

## 常见问题

先看：

- `docs/troubleshooting.md`

第一次真实运行最常见的问题是：

- registry 里看不到 `mobile_agent_e`、`open_autoglm` 或 `mobilesafetybench`
- registry 里看不到 `mobile_agent_v3_5`，或者 `MOBILE_AGENT_V3_5_HOME` 指到了错误的本地仓库
- 第三方仓库没有放到固定 `references/` 路径
- 当前 Python 环境没有安装上游依赖
- 没有设置 `PHONE_AGENT_BASE_URL / PHONE_AGENT_API_KEY / APPIUM_BIN`
- 没有设置 `MOBILE_AGENT_E_HOME`，或者既没有 `PHONE_AGENT_*` 也没有 Mobile-Agent-E 自己的 endpoint 变量
- `adb devices` 看不到模拟器
- `references/benchmarks/mobilesafetybench` 大小写写错


## License

本仓库采用 MIT License。
