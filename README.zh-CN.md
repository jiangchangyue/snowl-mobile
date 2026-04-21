# snowl-mobile 终端智能体动态安全测试风洞

<div align="center">

<img src="https://cdn-avatars.huggingface.co/v1/production/uploads/61def72b6742e9faa77b0edc/XHPe_wPj4roSniCHsHYT5.jpeg" alt="WhitzardAgent logo" width="120" />

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**WhitzardAgent | Fudan University | Shanghai Innovation Institute (SII)**
[English README](README.md)

</div>




## 总览
`snowl-mobile` 是一个面向 `Mobile Agent x Benchmark x Model x Emulator` 的统一评测平台。

它主要解决这些问题：

- 用一套 CLI/前端界面 运行完整 benchmark
- 支持多模拟器并行调度
- 中断后可以通过同一个 `--output-dir` 继续跑
- 为每个 trial 稳定落盘日志、轨迹、截图、XML 和评分结果
- 支持接入新 Agent 和 Benchmark

<img src="docs/web_1.png" alt="snowl-mobile" width="500" >
<img src="docs/web_2.png" alt="snowl-mobile" width="500" >

## 当前支持的运行组合

仓库当前已经集成了 3 个Mobile Agent和 2 个关于 Mobile-Agent 评测的Benchmark，共 6 种组合运行配置：

| Agent | Benchmark | 配置文件 |
| --- | --- | --- |
| Open-AutoGLM | MobileSafetyBench | `configs/runs/autoglm_mobilesafetybench.yml` |
| Mobile-Agent-E | MobileSafetyBench | `configs/runs/mobile_agent_e_mobilesafetybench.yml` |
| Mobile-Agent-v3.5 | MobileSafetyBench | `configs/runs/mobile_agent_v3_5_mobilesafetybench.yml` |
| Open-AutoGLM | AndroidWorld | `configs/runs/autoglm_androidworld.yml` |
| Mobile-Agent-E | AndroidWorld | `configs/runs/mobile_agent_e_androidworld.yml` |
| Mobile-Agent-v3.5 | AndroidWorld | `configs/runs/mobile_agent_v3_5_androidworld.yml` |

<!-- 另外还保留了一条 benchmark-only 配置：

- `configs/runs/androidworld_benchmark.yml` -->

## 运行前需要准备什么

- Python `>= 3.11`
- Android SDK 和 `adb`
- Appium
- 至少一台已经启动好的 Android 模拟器
- 一个 OpenAI-compatible 模型服务地址

几个重要说明：

- MobileSafetyBench 运行依赖 Appium。
- MobileSafetyBench 运行依赖 运行前模拟器需要创建“test_env_100”快照
- 建议阅读 MobileSafetyBench 的 README 了解更多：https://github.com/jylee425/mobilesafetybench
- AndroidWorld 更推荐单独准备一个 Python 环境，并通过 `ANDROID_WORLD_PYTHON` 指向它。
- AndroidWorld 模拟器建议是 Android 13 / API 33，并且用命令行带 `-grpc` 启动。
- 建议阅读 AndroidWorld 的 README 了解更多：https://github.com/google-research/android_world
- 如果要并行运行，请为每台模拟器都传一个 `--adb-serial`，并把 `--batch-size` 设成你想开的 worker 数量。

## 第一次使用：完整步骤

### 1. clone 本仓库

```bash
git clone <your-snowl-mobile-repo-url>
cd snowl-mobile
```

### 2. 安装平台

使用 `venv`：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
```

使用 `conda`：

```bash
conda create -n snowl-mobile python=3.11 -y
conda activate snowl-mobile
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
```

### 3. 把上游仓库 clone 到 `references/`

> AutoGLM, Mobile-Agent-E, Mobile-Agent-v3.5, MobileSafetyBench, AndroidWorld已完成clone到reference，无需重复clone。

期望目录：

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
git clone <MobileAgent-url> references/agents/MobileAgent/Mobile-Agent-E
git clone <MobileAgent-url> references/agents/MobileAgent/Mobile-Agent-v3.5
git clone <AndroidWorld-url> references/benchmarks/android_world
git clone <MobileSafetyBench-url> references/benchmarks/mobilesafetybench
```


### 4. 安装上游依赖

把你要运行的那几条路径所需依赖装进当前环境：

```bash
python -m pip install -r references/agents/Open-AutoGLM/requirements.txt
python -m pip install -r references/benchmarks/mobilesafetybench/requirements.txt
python -m pip install -r references/agents/MobileAgent/Mobile-Agent-E/requirements.txt
python -m pip install -r references/benchmarks/android_world/requirements.txt
python -m pip install openai pillow numpy
```

<!-- 如果要跑 AndroidWorld，建议单独准备环境：

```bash
python3 -m venv .venvs/androidworld
.venvs/androidworld/bin/python -m pip install --upgrade pip setuptools wheel
.venvs/androidworld/bin/python -m pip install -r references/benchmarks/android_world/requirements.txt
export ANDROID_WORLD_PYTHON="$PWD/.venvs/androidworld/bin/python"
``` -->

### 5. 启动模拟器

对于 MobileSafetyBench，只要模拟器已经启动并且 `adb devices` 能看到，就可以用 `existing_device` 模式。

对于 AndroidWorld，建议用命令行带 gRPC 启动，例如：

```bash
emulator -avd AndroidWorldAvd -no-snapshot -grpc 8554
```

如果要并行跑 AndroidWorld，每个 AVD 都要使用不同的 gRPC 端口。CLI 仍然通过 `--adb-serial` 选择设备；`snowl-mobile` 会从 serial 推导模拟器 console port，并从正在运行的 emulator 进程里自动发现对应的 `-grpc` 端口。

```bash
emulator -avd AndroidWorldAvd -no-snapshot -grpc 8554
emulator -avd AndroidWorldAvd2 -no-snapshot -grpc 8555
```

检查设备：

```bash
adb devices
```

如果你想先让平台做一次设备检查：

```bash
snowl-mobile devices list --config configs/runs/autoglm_mobilesafetybench.yml --device-mode existing_device
snowl-mobile devices health-check --config configs/runs/autoglm_mobilesafetybench.yml --device-mode existing_device
snowl-mobile registry list-agents
snowl-mobile registry list-benchmarks
```

### 6. 安装前端依赖

```bash
cd mobile-agent-eval-ui
npm install
cd ..
```

### 7. 启动前端页面

启动前端后端之前，请保持你刚才安装 `snowl-mobile` 的同一个 Python 环境处于激活状态。页面后端会从当前 shell 环境里调用 `snowl-mobile` CLI。

可选检查：

```bash
which snowl-mobile
```

用两个终端分别启动后端和前端：

终端 A：

```bash
cd mobile-agent-eval-ui
npm run server
```

终端 B：

```bash
cd mobile-agent-eval-ui
npm run client
```

启动后访问：

- 前端页面：`http://localhost:5173`
<!-- - 后端接口：`http://localhost:8787` -->

### 8. 第一次通过页面启动测试

页面打开后，按下面步骤操作：

1. 新建一个测试单元。
2. 选择 `Agent` 和 `Benchmark`，例如 `AutoGLM` + `MobileSafetyBench`。
3. 填写 `Base URL`、`API Key`、`Model Name`。
4. 第一次建议设置 `batch_size=1`，`max_steps=20`，并填写一个新的 `output_dir`。
5. 在模拟器槽位里选择一个 AVD 并点击 `启动模拟器`，或者提前保证已有模拟器已经出现在 `adb devices` 中。
6. 等待槽位状态变成就绪后，点击 `启动评测`。
7. 在测试单元的 `terminal`、`logs`、`summary` 标签中查看运行过程和结果。

运行结果会写到 `results/<resolved_output_dir>/`。如果复用同一个 `output_dir`，系统会按 resume 语义继续之前的 run，而不是重新从头开始。

如果你只想看前端单独说明，可以继续阅读 [mobile-agent-eval-ui/README.md](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/mobile-agent-eval-ui/README.md)。


## 第一次后端CLI真实运行 Open-AutoGLM × MobileSafetyBench

第一次跑真实设备时，建议先用下面 Open-AutoGLM × MobileSafetyBench 的命令，把 `--batch-size` 设成 `1` 并只传一台模拟器；确认产物正常后，再增加多个 `--adb-serial` 并行跑。

## 六种完整测试指令

这是大多数用户真正需要的部分。

把下面占位符替换掉：

- `<model-name>`
- `<base-url>`
- `<api-key>`

如果你只有一台模拟器，就把 `--batch-size` 设成 `1`，并只传一个 `--adb-serial`。

### MobileSafetyBench

Open-AutoGLM × MobileSafetyBench：

```bash
snowl-mobile run configs/runs/autoglm_mobilesafetybench.yml \
  --model-name <model-name> \
  --base-url <base-url> \
  --api-key '<api-key>' \
  --max-steps 20 \
  --batch-size 3 \
  --device-mode existing_device \
  --adb-serial emulator-5556 \
  --adb-serial emulator-5558 \
  --adb-serial emulator-5560 \
  --output-dir ./tmp/snowl-mobile-autoglm-mobilesafetybench
```

Mobile-Agent-E × MobileSafetyBench：

```bash
snowl-mobile run configs/runs/mobile_agent_e_mobilesafetybench.yml \
  --model-name <model-name> \
  --base-url <base-url> \
  --api-key '<api-key>' \
  --max-steps 20 \
  --batch-size 3 \
  --device-mode existing_device \
  --adb-serial emulator-5556 \
  --adb-serial emulator-5558 \
  --adb-serial emulator-5560 \
  --output-dir ./tmp/snowl-mobile-mobile-agent-e-mobilesafetybench
```

Mobile-Agent-v3.5 × MobileSafetyBench：

```bash
snowl-mobile run configs/runs/mobile_agent_v3_5_mobilesafetybench.yml \
  --model-name <model-name> \
  --base-url <base-url> \
  --api-key '<api-key>' \
  --max-steps 20 \
  --batch-size 3 \
  --device-mode existing_device \
  --adb-serial emulator-5556 \
  --adb-serial emulator-5558 \
  --adb-serial emulator-5560 \
  --output-dir ./tmp/snowl-mobile-mobile-agent-v3-5-mobilesafetybench
```

### AndroidWorld

跑 AndroidWorld 之前，请先保证 `ANDROID_WORLD_PYTHON` 指向一个可用的 AndroidWorld 环境。

Open-AutoGLM × AndroidWorld：

```bash
snowl-mobile run configs/runs/autoglm_androidworld.yml \
  --model-name <model-name> \
  --base-url <base-url> \
  --api-key '<api-key>' \
  --max-steps 20 \
  --batch-size 3 \
  --device-mode existing_device \
  --adb-serial emulator-5556 \
  --adb-serial emulator-5558 \
  --adb-serial emulator-5560 \
  --output-dir ./tmp/snowl-mobile-open-autoglm-androidworld
```

Mobile-Agent-E × AndroidWorld：

```bash
snowl-mobile run configs/runs/mobile_agent_e_androidworld.yml \
  --model-name <model-name> \
  --base-url <base-url> \
  --api-key '<api-key>' \
  --max-steps 20 \
  --batch-size 3 \
  --device-mode existing_device \
  --adb-serial emulator-5556 \
  --adb-serial emulator-5558 \
  --adb-serial emulator-5560 \
  --output-dir ./tmp/snowl-mobile-mobile-agent-e-androidworld
```

Mobile-Agent-v3.5 × AndroidWorld：

```bash
snowl-mobile run configs/runs/mobile_agent_v3_5_androidworld.yml \
  --model-name <model-name> \
  --base-url <base-url> \
  --api-key '<api-key>' \
  --max-steps 20 \
  --batch-size 3 \
  --device-mode existing_device \
  --adb-serial emulator-5556 \
  --adb-serial emulator-5558 \
  --adb-serial emulator-5560 \
  --output-dir ./tmp/snowl-mobile-mobile-agent-v3-5-androidworld
```

## 可选的 fake 测试

如果你只想验证平台主链，不想碰真实设备，可以保留这一条 fake 示例：

```bash
export SNOWL_TASK_SELECTOR='task_category=text_message_sending,task_id=low_risk_001,limit=1'
snowl-mobile run configs/runs/mobile_agent_v3_5_mobilesafetybench.yml \
  --device-mode fake \
  --output-dir ./tmp/snowl-mobile-mobile-agent-v3-5-fake
unset SNOWL_TASK_SELECTOR
```

## 运行结果、日志和 resume

最常用的结果文件：

- `<run_dir>/run.log`
- `<run_dir>/summary.json`
- `<run_dir>/events.jsonl`
- `<run_dir>/trials/<trial_id>/trial.log`
- `<run_dir>/trials/<trial_id>/score.json`
- `<run_dir>/trials/<trial_id>/trajectory.json`

常用查看命令：

```bash
tail -f <run_dir>/run.log
snowl-mobile summarize <run_dir>
```

resume 规则：

- 用同一条命令重新执行
- 复用同一个 `--output-dir`
- 已完成的 trial 会跳过
- 失败或未完成的 trial 会继续执行

并行调度规则：

- `snowl-mobile run` 会按 `--batch-size` 同时占用多台模拟器
- 哪台模拟器先空下来，调度器就立刻把下一条排队任务补上去

## 手工接入与 Codex 辅助接入

`snowl-mobile` 不只支持当前仓库里已经提供好的 6 种运行组合。用户也可以自己接入新的手机 Agent 和 Benchmark。

推荐流程：

1. 先把上游仓库 clone 到 `references/` 下的约定路径
2. 让 Codex 按仓库里的接入提示/文档完成接入，或者你自己按手动文档完成接入
3. 注册新的 adapter 或 bridge，并补一个新的 run config
4. 之后仍然通过同一个 `snowl-mobile run ...` 入口运行

推荐 clone 路径：

- 新 Agent 仓库：`references/agents/<repo_name>/`
- 新 Benchmark 仓库：`references/benchmarks/<repo_name>/`

如果你希望借助 Codex 来完成接入，可以直接使用这些文档：

- Agent 接入说明：[docs/integrate-agent.md](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/docs/integrate-agent.md)
- Benchmark 接入说明：[docs/integrate-benchmark.md](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/docs/integrate-benchmark.md)
- Pair / bridge 接入说明：[docs/integrate-pair.md](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/docs/integrate-pair.md)
- 给 Codex 的 Agent 接入提示：[docs/prompts/integrate-agent-prompt.md](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/docs/prompts/integrate-agent-prompt.md)
- 给 Codex 的 Benchmark 接入提示：[docs/prompts/integrate-benchmark-prompt.md](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/docs/prompts/integrate-benchmark-prompt.md)

如果你想先分析一个新 clone 下来的仓库，再决定如何接入，也可以先用：

```bash
PYTHONPATH=src python3 -m snowl_mobile inspect-repo agent references/agents/<repo_name>
PYTHONPATH=src python3 -m snowl_mobile inspect-repo benchmark references/benchmarks/<repo_name>
PYTHONPATH=src python3 -m snowl_mobile integration-checklist agent references/agents/<repo_name>
PYTHONPATH=src python3 -m snowl_mobile integration-checklist benchmark references/benchmarks/<repo_name>
```

## 更多文档

- 快速开始：[docs/quickstart.md](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/docs/quickstart.md)
- 故障排查：[docs/troubleshooting.md](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/docs/troubleshooting.md)
- AndroidWorld 说明：[docs/integrations/androidworld.md](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/docs/integrations/androidworld.md)
- Open-AutoGLM 说明：[docs/integrations/open-autoglm.md](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/docs/integrations/open-autoglm.md)
- Mobile-Agent-E 说明：[docs/integrations/mobile-agent-e.md](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/docs/integrations/mobile-agent-e.md)
- Mobile-Agent-v3.5 说明：[docs/integrations/mobile-agent-v3-5.md](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/docs/integrations/mobile-agent-v3-5.md)
- MobileSafetyBench 说明：[docs/integrations/mobilesafetybench.md](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/docs/integrations/mobilesafetybench.md)
- Open-AutoGLM × MobileSafetyBench bridge 说明：[docs/integrations/open-autoglm-mobilesafetybench.md](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/docs/integrations/open-autoglm-mobilesafetybench.md)

## License

This project is licensed under the **MIT License**. See [LICENSE](LICENSE) for details.
