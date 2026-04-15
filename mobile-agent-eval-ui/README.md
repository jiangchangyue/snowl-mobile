# Mobile Agent Eval UI

这是一个可本地运行的“手机智能体评测平台前端原型 + 本地模拟器控制后端”。

当前版本已经包含以下改动：

1. 每个测试单元的模拟器区域会随 `batch_size` 动态扩展。
2. 每个模拟器槽位都可以单独“选择 AVD / 启动模拟器 / 关闭模拟器”。
3. 运行输出新增 `terminal` 标签，用于展示类似真实终端的 agent 运行轨迹流。
4. 新增“设置”按钮，可切换明亮版与暗黑版界面，默认是明亮版。
5. 初始不确定数据默认显示为 `0`，`batch_size` 默认值为 `1`。

需要说明的是：

- 页面中展示的仍然是通过 `adb` 抓取的真实模拟器截图/XML 投影视图。
- 它不是浏览器内可直接鼠标操控的 Android Emulator 原生窗口；这部分当前没有改成嵌入式交互模拟器。

---

## 1. 目录结构

```text
mobile-agent-eval-ui/
├─ package.json
├─ vite.config.ts
├─ tsconfig.json
├─ index.html
├─ README.md
├─ server/
│  ├─ index.js
│  ├─ adb.js
│  └─ mockRunManager.js
└─ src/
   ├─ main.tsx
   ├─ App.tsx
   ├─ api.ts
   ├─ types.ts
   ├─ styles.css
   └─ components/
      ├─ DashboardHeader.tsx
      ├─ Sidebar.tsx
      ├─ EmulatorPanel.tsx
      └─ EvaluationUnitCard.tsx
```

---

## 2. 运行前要求

你的电脑需要满足：

- 已安装 Node.js 18 或更高版本
- 已安装 Android SDK，并且 `emulator` 与 `adb` 命令在终端可直接运行
- 已经提前创建好一个或多个 AVD，例如：
  - `Pixel_4_API_30`
  - `Pixel_6_API_33`

如果 `emulator` 或 `adb` 不能直接运行，也可以配置环境变量：

- `ANDROID_EMULATOR_BIN`
- `ADB_BIN`

例如：

```bash
export ANDROID_EMULATOR_BIN=/Users/yourname/Library/Android/sdk/emulator/emulator
export ADB_BIN=/Users/yourname/Library/Android/sdk/platform-tools/adb
```

---

## 3. 安装与启动

在项目根目录执行：

```bash
npm install
npm run dev
```

启动后：

- 前端地址：`http://localhost:5173`
- 后端地址：`http://localhost:8787`

---

## 4. 页面使用方式

### 4.1 新建测试单元

点击左侧“添加新测试单元”或右下角加号按钮。

### 4.2 配置评测组合

在每个测试单元中分别选择：

- 手机智能体：`AutoGLM` / `Mobile-Agent-E` / `Mobile-Agent-V3.5`
- Benchmark：`MobileSafetyBench` / `AndroidWorld`
- 模型配置：`Base URL / API KEY / Model Name`
- `batch_size` / `output_dir` / `max_steps`

### 4.3 batch_size 与模拟器槽位

`batch_size` 表示该测试单元期望并行运行的任务数。

因此：

- `batch_size = 1` 时，界面展示 1 个模拟器槽位
- `batch_size = 4` 时，界面展示 4 个模拟器槽位

只有在至少准备好与 `batch_size` 相同数量的“已就绪模拟器槽位”后，后端才允许启动该测试单元的评测。

### 4.4 启动本地模拟器

在每个模拟器槽位中：

1. 选择一个 AVD
2. 点击“启动模拟器”
3. 如需结束该槽位对应的模拟器，点击“关闭模拟器”

后端会在你的电脑上执行与下面等价的命令：

```bash
emulator -avd <你选择的AVD名称>
```

关闭时会优先尝试：

```bash
adb -s <serial> emu kill
```

---

## 5. 运行输出说明

每个测试单元的“运行输出”区域包含四个标签：

- `terminal`：动态滚动展示 agent 运行轨迹，风格近似终端
- `logs`：结构化日志卡片
- `summary`：结果摘要指标
- `config`：当前单元配置与建议接口说明

其中 `terminal` 当前接入的是 mock 轨迹流，用来模拟真实评测中 agent 的多步执行过程。

---

## 6. 当前项目里哪些是真实的，哪些是演示的

### 已经是真实接入的部分

- 本地 AVD 列表获取：`emulator -list-avds`
- 启动本地模拟器：`emulator -avd <name>`
- 关闭模拟器：`adb -s <serial> emu kill`
- 获取模拟器设备 serial：`adb devices`
- 获取模拟器截图：`adb exec-out screencap -p`
- 获取 XML：`adb exec-out uiautomator dump /dev/tty`

### 目前仍然是演示型 mock 的部分

- “启动评测”后的任务进度推进
- success / failed 统计
- safety rate / success rate / avg steps
- terminal 中的 agent 轨迹流

这些状态目前由 `server/mockRunManager.js` 内部定时生成。

---

## 7. 后续如何接你的真实评测平台

你当前已经有统一评测平台，并已集成：

- Agents: `AutoGLM`, `Mobile-Agent-E`, `Mobile-Agent-V3.5`
- Benchmarks: `MobileSafetyBench`, `AndroidWorld`

因此，你后续主要替换后端中这些接口即可：

- `POST /api/runs/start`
- `POST /api/runs/stop`
- `GET /api/runs/:unitId/state`
- `GET /api/runs/:unitId/export`

如果你后端已经能提供更真实的轨迹流，也可以顺带替换 `terminalLines` 字段。

---

## 8. 适用边界

这个项目已经适合用于：

- 展示你的平台整体能力
- 演示 Agent × Benchmark 任意组合
- 演示多并行任务下的多模拟器准备流程
- 演示设备画面、terminal、日志、进度、摘要指标
- 为后续真实后端对接提供前端骨架

但它还不是最终生产版控制台。若你后续继续扩展，通常还会增加：

- WebSocket / SSE 实时流
- 历史运行记录列表
- 任务级结果详情页
- 截图时间轴 / XML 时间轴
- 资源占用监控
- 真正的远程设备流媒体或 WebRTC 控制层
