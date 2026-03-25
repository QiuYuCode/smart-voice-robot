# 机器人语音助手 (Robot Voice Assistant)

基于 [py_trees](https://py-trees.readthedocs.io/) 行为树实现的语音交互系统。通过行为树的 tick 驱动机制，将唤醒词检测、语音识别、意图分发、动作执行、语音合成等模块组织成可维护、可扩展的树形结构。

支持两种意图模式：**关键词匹配**（默认，轻量快速）和 **LLM 多指令规划**（基于 Function Calling，支持一句话触发多个动作）。

## 目录

- [系统架构](#系统架构)
- [行为树结构](#行为树结构)
- [运行流程](#运行流程)
- [数据流](#数据流)
- [节点详解](#节点详解)
- [Blackboard 数据共享](#blackboard-数据共享)
- [项目结构](#项目结构)
- [依赖与安装](#依赖与安装)
- [配置说明](#配置说明)
- [运行](#运行)
- [CLI 测试工具](#cli-测试工具)

---

## 系统架构

> 详细的可编辑架构图见 [`docs/architecture.drawio`](docs/architecture.drawio)，使用 [draw.io](https://app.diagrams.net/) 打开。

```mermaid
block-beta
    columns 3

    block:HW["硬件层"]:3
        Mic["🎤 麦克风\nsounddevice"]
        Speaker["🔊 扬声器\nsounddevice"]
        Peripherals["📷 相机 / 🤖 机械臂"]
    end

    space:3

    block:ENGINE["语音引擎 VoiceEngine"]:3
        Queue["dialog_audio_queue"]
        KWS["KWS 唤醒词\nsherpa-onnx"]
        ASR["ASR 语音识别\nsherpa-onnx"]
        VAD["VAD 语音活动检测\nSilero VAD"]
        TTS["TTS 语音合成\nVITS aishell3"]
    end

    space:3

    block:BT["行为树 py_trees BehaviourTree"]:3
        Root["Root Sequence"]
        Nodes["行为节点"]
        BB["Blackboard\n共享数据"]
    end

    space:3

    block:EXT["外部服务"]:3
        LLM["LLM (多 Provider)\nOllama / OpenAI / DeepSeek / Anthropic"]
        RK["RK3328 降噪板\n硬件唤醒 (可选)"]
        ROS["ROS 导航 (预留)"]
    end

    Mic --> Queue
    Queue --> KWS
    Queue --> ASR
    Queue --> VAD
    TTS --> Speaker
    Nodes --> BB
    Nodes --> LLM
```

系统分为四层：

| 层级 | 组件 | 职责 |
|------|------|------|
| **硬件层** | 麦克风、扬声器、相机、机械臂 | 音频采集与播放、外设交互 |
| **语音引擎** | `VoiceEngine` | 管理 KWS/ASR/VAD/TTS 模型，维护音频队列 |
| **行为树** | `py_trees.BehaviourTree` | 决策调度核心，tick 驱动所有节点 |
| **外部服务** | LLM (多 Provider)、RK3328 降噪板、ROS（预留） | 大模型对话/任务规划、硬件唤醒、机器人导航 |

---

## 行为树结构

这是系统的核心设计。行为树通过 `tick()` 循环驱动，每次 tick 从根节点递归向下执行，节点返回 `SUCCESS`、`FAILURE` 或 `RUNNING` 三种状态。

系统支持两种意图模式，通过 `config.use_llm_planner` 切换：

### 模式 A：关键词匹配（默认）

轻量快速，适合固定指令集场景。

```mermaid
graph TD
    Root["⟶ Root<br/><i>Sequence(memory=True)</i>"]
    WakeWord["🎤 WaitForWakeWord<br/>KWS / 硬件唤醒<br/><small>RUNNING → SUCCESS</small>"]
    WakeupSound["🔊 WakeupResponse<br/>播放 '我在，请说'<br/><small>阻塞式 TTS → SUCCESS</small>"]
    DialogRepeat["↻ DialogRepeat<br/><i>SuccessIsRunning 装饰器</i><br/><small>将 SUCCESS 映射为 RUNNING<br/>FAILURE 透传 → 回到唤醒</small>"]
    DialogLoop["⟶ DialogLoop<br/><i>Sequence(memory=False)</i><br/><small>每轮完成后自动重置</small>"]
    Listen["🎤 ListenCommand<br/>流式 ASR + VAD<br/><small>SUCCESS → bb.user_command<br/>FAILURE → VAD 静默超时</small>"]
    Intent["🧠 RecognizeIntent<br/>关键词匹配<br/><small>→ bb.intent</small>"]
    ActionSel["? ActionSelector<br/><i>Selector(memory=False)</i><br/><small>按优先级从左到右尝试</small>"]
    Speak["🔊 SpeakResponse<br/>TTS 语音播放<br/><small>← bb.response_text</small>"]
    Guard["🛡️ ContinueGuard<br/><small>intent==exit → FAILURE<br/>否则 → SUCCESS</small>"]

    Photo["📷 TakePhoto<br/><small>intent==take_photo</small>"]
    Video["🎬 RecordVideo<br/><small>intent==record_video</small>"]
    Arm["🦾 RobotArm<br/><small>intent==robot_arm</small>"]
    Nav["🗺️ Navigation<br/><small>intent==navigation</small>"]
    LLM["💬 LLMDialog<br/><small>intent==chat</small>"]
    Exit["🚪 BackToWakeUp<br/><small>intent==exit</small>"]
    Default["🔄 DefaultResponse<br/><small>兜底 always SUCCESS</small>"]

    Root -->|"① 唤醒"| WakeWord
    Root -->|"② 提示音"| WakeupSound
    Root -->|"③ 对话循环"| DialogRepeat
    DialogRepeat --> DialogLoop
    DialogLoop -->|"1"| Listen
    DialogLoop -->|"2"| Intent
    DialogLoop -->|"3"| ActionSel
    DialogLoop -->|"4"| Speak
    DialogLoop -->|"5"| Guard
    ActionSel --> Photo
    ActionSel --> Video
    ActionSel --> Arm
    ActionSel --> Nav
    ActionSel --> LLM
    ActionSel --> Exit
    ActionSel --> Default

    style Root fill:#d5e8d4,stroke:#82b366,stroke-width:2px
    style DialogRepeat fill:#d5e8d4,stroke:#82b366,stroke-width:2px
    style DialogLoop fill:#d5e8d4,stroke:#82b366,stroke-width:2px
    style ActionSel fill:#d5e8d4,stroke:#82b366,stroke-width:2px
    style WakeWord fill:#f8cecc,stroke:#b85450
    style WakeupSound fill:#f8cecc,stroke:#b85450
    style Listen fill:#f8cecc,stroke:#b85450
    style Intent fill:#f8cecc,stroke:#b85450
    style Speak fill:#f8cecc,stroke:#b85450
    style Guard fill:#dae8fc,stroke:#6c8ebf
    style Photo fill:#ffe6cc,stroke:#d79b00
    style Video fill:#ffe6cc,stroke:#d79b00
    style Arm fill:#ffe6cc,stroke:#d79b00
    style Nav fill:#ffe6cc,stroke:#d79b00
    style LLM fill:#ffe6cc,stroke:#d79b00
    style Exit fill:#ffe6cc,stroke:#d79b00
    style Default fill:#ffe6cc,stroke:#d79b00
```

### 模式 B：LLM 多指令规划

基于 LLM Function Calling，支持一句话触发多个动作（如"先拍张照再导航到厨房"）。

```mermaid
graph TD
    Root2["⟶ Root<br/><i>Sequence(memory=True)</i>"]
    WakeWord2["🎤 WaitForWakeWord<br/>KWS / 硬件唤醒"]
    WakeupSound2["🔊 WakeupResponse<br/>播放 '我在，请说'"]
    DialogRepeat2["↻ DialogRepeat<br/><i>SuccessIsRunning 装饰器</i>"]
    DialogLoop2["⟶ DialogLoop<br/><i>Sequence(memory=False)</i>"]
    Listen2["🎤 ListenCommand<br/>流式 ASR + VAD"]
    Planner["🧠 LLMTaskPlanner<br/>LLM Function Calling<br/><small>→ bb.action_plan / bb.intent</small>"]
    Executor["⚡ PlanExecutor<br/>依次执行 action_plan<br/><small>→ bb.response_text</small>"]
    Speak2["🔊 SpeakResponse<br/>TTS 语音播放"]
    Guard2["🛡️ ContinueGuard"]

    Root2 -->|"① 唤醒"| WakeWord2
    Root2 -->|"② 提示音"| WakeupSound2
    Root2 -->|"③ 对话循环"| DialogRepeat2
    DialogRepeat2 --> DialogLoop2
    DialogLoop2 -->|"1"| Listen2
    DialogLoop2 -->|"2"| Planner
    DialogLoop2 -->|"3"| Executor
    DialogLoop2 -->|"4"| Speak2
    DialogLoop2 -->|"5"| Guard2

    style Root2 fill:#d5e8d4,stroke:#82b366,stroke-width:2px
    style DialogRepeat2 fill:#d5e8d4,stroke:#82b366,stroke-width:2px
    style DialogLoop2 fill:#d5e8d4,stroke:#82b366,stroke-width:2px
    style WakeWord2 fill:#f8cecc,stroke:#b85450
    style WakeupSound2 fill:#f8cecc,stroke:#b85450
    style Listen2 fill:#f8cecc,stroke:#b85450
    style Planner fill:#e1d5e7,stroke:#9673a6
    style Executor fill:#e1d5e7,stroke:#9673a6
    style Speak2 fill:#f8cecc,stroke:#b85450
    style Guard2 fill:#dae8fc,stroke:#6c8ebf
```

### 关键设计决策

| 节点 | 类型 | memory | 原因 |
|------|------|--------|------|
| **Root** | Sequence | `True` | WakeWord SUCCESS 后记住状态，后续 tick 直接进入对话，不再重复唤醒 |
| **DialogRepeat** | SuccessIsRunning | - | 将 DialogLoop 的 SUCCESS 映射为 RUNNING，使对话持续循环；FAILURE 透传，触发回到唤醒 |
| **DialogLoop** | Sequence | `False` | 每轮对话完成后自动重置，从 Listen 重新开始下一轮 |
| **ActionSelector** | Selector | `False` | 每次都从头匹配，按优先级逐个尝试 action（仅关键词匹配模式） |
| **ContinueGuard** | Leaf | - | DialogLoop 末尾守卫：`intent == "exit"` 时返回 FAILURE 打断循环 |

### 回到唤醒的两条路径

| 触发条件 | 触发节点 | FAILURE 传播链路 |
|----------|----------|-----------------|
| VAD 检测到持续静默超过 `dialog_timeout` 秒 | `ListenCommand` → FAILURE | DialogLoop → SuccessIsRunning 透传 → Root FAILURE → `root.stop(INVALID)` |
| 用户说"退出/结束/停止/没事了" | `DialogContinueGuard` → FAILURE | DialogLoop → SuccessIsRunning 透传 → Root FAILURE → `root.stop(INVALID)` |

---

## 运行流程

### 主循环时序图

```mermaid
sequenceDiagram
    participant Main as main()
    participant Tree as BehaviourTree
    participant Root as Root Sequence
    participant WK as WaitForWakeWord
    participant WR as WakeupResponse
    participant DR as DialogRepeat
    participant DL as DialogLoop
    participant L as ListenCommand
    participant I as RecognizeIntent
    participant A as ActionSelector
    participant S as SpeakResponse
    participant G as ContinueGuard

    Main->>Tree: tree.tick()
    activate Tree

    Note over Main,Tree: === 阶段 1: 等待唤醒 ===

    loop 每次 tick (50ms 间隔)
        Tree->>Root: tick
        Root->>WK: tick
        WK-->>Root: RUNNING (未检测到唤醒词)
        Root-->>Tree: RUNNING
    end

    Note over WK: 检测到唤醒词!
    Tree->>Root: tick
    Root->>WK: tick
    WK-->>Root: SUCCESS

    Note over Main,Tree: === 阶段 2: 唤醒提示 ===

    Root->>WR: tick
    WR->>WR: speak_blocking("我在，请说")
    WR-->>Root: SUCCESS

    Note over Main,Tree: === 阶段 3: 对话循环 ===

    loop 持续对话 (SuccessIsRunning)
        Root->>DR: tick
        DR->>DL: tick

        DL->>L: tick
        Note over L: 流式 ASR + VAD 检测中...
        L-->>DL: RUNNING
        DL-->>DR: RUNNING
        DR-->>Root: RUNNING

        Note over L: 检测到语音端点
        DL->>L: tick
        L-->>DL: SUCCESS (user_command → Blackboard)

        DL->>I: tick
        I->>I: 关键词匹配
        I-->>DL: SUCCESS (intent → Blackboard)

        DL->>A: tick
        Note over A: 按优先级匹配 Action
        A-->>DL: SUCCESS (response_text → Blackboard)

        DL->>S: tick
        S->>S: TTS 合成 + 播放
        S-->>DL: SUCCESS

        DL->>G: tick
        G-->>DL: SUCCESS (intent != exit)

        DL-->>DR: SUCCESS
        Note over DR: SuccessIsRunning 将 SUCCESS → RUNNING
        DR-->>Root: RUNNING
    end

    Note over Main,Tree: === 退出路径 A: VAD 静默超时 ===

    DL->>L: tick
    Note over L: VAD 检测到持续静默 > dialog_timeout
    L->>L: speak_blocking("没有听到您的命令...")
    L-->>DL: FAILURE
    DL-->>DR: FAILURE
    Note over DR: SuccessIsRunning 透传 FAILURE
    DR-->>Root: FAILURE

    Note over Main,Tree: === 退出路径 B: 用户说"退出" ===

    DL->>L: tick
    L-->>DL: SUCCESS (user_command="退出")
    DL->>I: tick
    I-->>DL: SUCCESS (intent=exit)
    DL->>A: tick
    Note over A: BackToWakeUp 匹配 exit
    A-->>DL: SUCCESS (response_text="好的，我先休息了")
    DL->>S: tick
    S-->>DL: SUCCESS
    DL->>G: tick
    G-->>DL: FAILURE (intent == exit)
    DL-->>DR: FAILURE
    DR-->>Root: FAILURE

    Note over Main: root.status == FAILURE
    Main->>Root: root.stop(INVALID)
    Note over Main: 回到阶段 1

    deactivate Tree
```

### 状态机视图

```mermaid
stateDiagram-v2
    [*] --> Idle: 系统启动

    Idle --> WaitingWakeWord: tree.tick()
    WaitingWakeWord --> WaitingWakeWord: RUNNING (每 50ms tick)
    WaitingWakeWord --> WakeupPrompt: KWS / 硬件检测到唤醒词

    WakeupPrompt --> DialogActive: 播放"我在，请说"

    state DialogActive {
        [*] --> Listening
        Listening --> Listening: RUNNING (ASR + VAD 检测中)
        Listening --> IntentRecognition: ASR 端点检测 + 有文本
        IntentRecognition --> ActionExecution: 意图匹配 / LLM 规划完成
        ActionExecution --> Speaking: Action 生成 response_text
        Speaking --> ContinueCheck: TTS 播放完成
        ContinueCheck --> Listening: intent != exit → 下一轮
    }

    DialogActive --> Idle: VAD 静默超时 (ListenCommand FAILURE)\nroot.stop(INVALID)
    ContinueCheck --> Idle: intent == exit (ContinueGuard FAILURE)\nroot.stop(INVALID)
```

---

## 数据流

节点之间通过 py_trees 的 **Blackboard** 机制传递数据，所有键都在 `dialog` 命名空间下。

```mermaid
flowchart LR
    MIC["🎤 麦克风"] -->|"PCM float32"| Q["dialog_audio_queue"]
    Q -->|"待机态"| KWS["KWS\n唤醒词检测"]
    Q -->|"对话态"| ASR["ASR\n流式语音识别"]
    Q -->|"对话态"| VAD["VAD\n语音活动检测"]

    ASR -->|"user_command"| BB["📋 Blackboard"]
    VAD -->|"静默超时判断"| LISTEN["ListenCommand"]

    subgraph 关键词匹配模式
        BB -->|"user_command"| INTENT["🧠 意图识别"]
        INTENT -->|"intent"| BB2["📋 Blackboard"]
        BB2 -->|"intent +\nuser_command"| ACTION["⚡ Action 执行"]
    end

    subgraph LLM规划器模式
        BB -->|"user_command"| PLANNER["🧠 LLM Planner\nFunction Calling"]
        PLANNER -->|"action_plan\n+ intent"| BB3["📋 Blackboard"]
        BB3 -->|"action_plan"| EXEC["⚡ PlanExecutor"]
    end

    ACTION -->|"response_text"| BB4["📋 Blackboard"]
    EXEC -->|"response_text"| BB4
    BB4 -->|"response_text"| TTS["TTS\n语音合成"]
    TTS -->|"audio"| SPK["🔊 扬声器"]

    ACTION -.->|"intent==chat"| LLM["🤖 LLM"]
    LLM -.->|"AI 回复"| ACTION
    PLANNER -.->|"bind_tools"| LLM2["🤖 LLM"]
    LLM2 -.->|"tool_calls"| PLANNER

    style BB fill:#f0f0f0,stroke:#666
    style BB2 fill:#f0f0f0,stroke:#666
    style BB3 fill:#f0f0f0,stroke:#666
    style BB4 fill:#f0f0f0,stroke:#666
    style KWS fill:#e1d5e7,stroke:#9673a6
    style ASR fill:#e1d5e7,stroke:#9673a6
    style VAD fill:#e1d5e7,stroke:#9673a6
    style TTS fill:#e1d5e7,stroke:#9673a6
    style LLM fill:#e1d5e7,stroke:#9673a6
    style LLM2 fill:#e1d5e7,stroke:#9673a6
    style ACTION fill:#ffe6cc,stroke:#d79b00
    style EXEC fill:#ffe6cc,stroke:#d79b00
    style INTENT fill:#d5e8d4,stroke:#82b366
    style PLANNER fill:#d5e8d4,stroke:#82b366
    style LISTEN fill:#f8cecc,stroke:#b85450
```

---

## 节点详解

### 控制节点 (Composite / Decorator)

| 节点 | 类型 | 说明 |
|------|------|------|
| `Root` | `Sequence(memory=True)` | 根节点，按顺序执行唤醒→提示→对话循环。`memory=True` 保证唤醒后不再重复检测 |
| `DialogRepeat` | `SuccessIsRunning` 装饰器 | 将 `DialogLoop` 的 SUCCESS 转换为 RUNNING，实现无限对话循环；FAILURE 透传触发回到唤醒 |
| `DialogLoop` | `Sequence(memory=False)` | 单轮对话流程。`memory=False` 每轮自动重置 |
| `ActionSelector` | `Selector(memory=False)` | 意图分发器（仅关键词匹配模式），从左到右尝试匹配 action，第一个 SUCCESS 胜出 |

### 叶子节点 (Leaf Behaviour)

| 节点 | 文件 | 功能 | Blackboard I/O |
|------|------|------|----------------|
| `WaitForWakeWord` | `nodes/wake_word.py` | 软件 KWS 唤醒词检测 (`wake_mode=software`) | 无 (直接消费 audio_queue) |
| `HardwareWakeWord` | `nodes/hw_wake_word.py` | RK3328 降噪板硬件唤醒 (`wake_mode=hardware`) | 无 (消费 rk3328 wake_event_queue) |
| `WakeupResponse` | `nodes/speak.py` | 播放唤醒提示音 "我在，请说" (阻塞式 TTS) | 无 |
| `ListenCommand` | `nodes/listen.py` | 流式 ASR + VAD 检测。ASR 端点+有文本→SUCCESS；VAD 静默超时→FAILURE | Write: `user_command`, `last_activity_time` |
| `RecognizeIntent` | `nodes/intent.py` | 关键词匹配意图，无匹配则设为 `chat`（仅关键词匹配模式） | Read: `user_command` / Write: `intent` |
| `LLMTaskPlanner` | `nodes/planner.py` | LLM Function Calling 解析多步指令（仅 LLM 规划器模式） | Read: `user_command` / Write: `intent`, `action_plan`, `response_text` |
| `PlanExecutor` | `nodes/plan_executor.py` | 依次执行 `action_plan` 中的动作并汇总结果（仅 LLM 规划器模式） | Read: `intent`, `action_plan` / Write: `response_text` |
| `TakePhotoAction` | `nodes/actions/camera.py` | 拍摄照片 (OpenCV)，保存到 `captures/` | Read: `intent` / Write: `response_text` |
| `RecordVideoAction` | `nodes/actions/camera.py` | 录制视频 (OpenCV)，保存到 `captures/` | Read: `intent` / Write: `response_text` |
| `RobotArmAction` | `nodes/actions/robot_arm.py` | 控制机械臂 (预留接口) | Read: `intent`, `user_command` / Write: `response_text` |
| `NavigationAction` | `nodes/actions/navigation.py` | ROS 导航 (预留接口) | Read: `intent`, `user_command` / Write: `response_text` |
| `LLMDialogAction` | `nodes/actions/llm_dialog.py` | LLM 自由对话，支持多 provider、多轮会话 | Read: `intent`, `user_command` / Write: `response_text` |
| `BackToWakeUp` | `nodes/actions/back_to_wakeup.py` | 退出动作：`intent == "exit"` 时设置告别语并 SUCCESS | Read: `intent`, `user_command` / Write: `response_text` |
| `DefaultResponse` | `nodes/actions/default_response.py` | 兜底响应，始终 SUCCESS | Read: `user_command` / Write: `response_text` |
| `SpeakResponse` | `nodes/speak.py` | TTS 播放 response_text | Read: `response_text` / Write: `is_speaking`, `speak_start_time`, `last_activity_time` |
| `DialogContinueGuard` | `nodes/guards.py` | 对话循环守卫：`intent == "exit"` 时 FAILURE 终止循环，否则 SUCCESS | Read: `intent` |

### Action 节点的 Selector 匹配逻辑（关键词匹配模式）

每个 Action 节点在 `update()` 中首先检查 `blackboard.intent` 是否匹配自身的意图名称：
- **匹配** → 执行业务逻辑 → 返回 `SUCCESS`
- **不匹配** → 直接返回 `FAILURE`，Selector 继续尝试下一个

```mermaid
flowchart TD
    SEL["ActionSelector (Selector)"] --> C1{"intent ==\ntake_photo?"}
    C1 -->|"Yes → SUCCESS"| CAM["TakePhoto 执行"]
    C1 -->|"No → FAILURE"| C1B{"intent ==\nrecord_video?"}
    C1B -->|"Yes → SUCCESS"| VID["RecordVideo 执行"]
    C1B -->|"No → FAILURE"| C2{"intent ==\nrobot_arm?"}
    C2 -->|"Yes → SUCCESS"| ARM["RobotArm 执行"]
    C2 -->|"No → FAILURE"| C3{"intent ==\nnavigation?"}
    C3 -->|"Yes → SUCCESS"| NAV["Navigation 执行"]
    C3 -->|"No → FAILURE"| C4{"intent ==\nchat?"}
    C4 -->|"Yes → SUCCESS"| LLM["LLMDialog 执行"]
    C4 -->|"No → FAILURE"| C5{"intent ==\nexit?"}
    C5 -->|"Yes → SUCCESS"| EXIT["BackToWakeUp\n设置告别语"]
    C5 -->|"No → FAILURE"| DEF["DefaultResponse\n兜底 (always SUCCESS)"]

    style SEL fill:#d5e8d4,stroke:#82b366,stroke-width:2px
    style CAM fill:#ffe6cc,stroke:#d79b00
    style VID fill:#ffe6cc,stroke:#d79b00
    style ARM fill:#ffe6cc,stroke:#d79b00
    style NAV fill:#ffe6cc,stroke:#d79b00
    style LLM fill:#ffe6cc,stroke:#d79b00
    style EXIT fill:#ffe6cc,stroke:#d79b00
    style DEF fill:#ffe6cc,stroke:#d79b00
```

### LLM 规划器的 Function Calling 流程（LLM 规划器模式）

`LLMTaskPlanner` 将用户自然语言交给 LLM（带 `bind_tools`），LLM 返回 `tool_calls` 列表，`PlanExecutor` 依次执行：

| Tool 名称 | 描述 | 对应执行函数 |
|-----------|------|-------------|
| `take_photo` | 拍摄照片 | `execute_take_photo()` |
| `record_video` | 录制视频 (可指定时长) | `execute_record_video()` |
| `navigate` | 导航到指定位置 | `execute_navigate()` |
| `control_robot_arm` | 控制机械臂 | `execute_robot_arm()` |
| `exit_conversation` | 结束对话 | 设置告别语 |

无 `tool_calls` 时视为纯对话，直接将 LLM 回复写入 `response_text`。

---

## Blackboard 数据共享

py_trees 的 Blackboard 是节点间共享数据的中心化存储，采用命名空间隔离。本项目所有键均在 `dialog` 命名空间下：

| 键名 | 类型 | 写入者 | 读取者 | 说明 |
|------|------|--------|--------|------|
| `user_command` | `str` | ListenCommand | RecognizeIntent / LLMTaskPlanner, Actions | ASR 识别出的用户语音文本 |
| `intent` | `str` | RecognizeIntent / LLMTaskPlanner | 所有 Action 节点, ContinueGuard | 识别出的意图名称 |
| `action_plan` | `list[dict]` | LLMTaskPlanner | PlanExecutor | LLM 规划的动作列表（仅 LLM 规划器模式） |
| `response_text` | `str` | Action 节点 / LLMTaskPlanner / PlanExecutor | SpeakResponse | 待播放的回复文本 |
| `is_speaking` | `bool` | SpeakResponse | InterruptMonitor | TTS 是否正在播放 |
| `speak_start_time` | `float` | SpeakResponse | InterruptMonitor | TTS 播放开始时间戳 |
| `last_activity_time` | `float` | ListenCommand, SpeakResponse | InterruptMonitor | 最后一次活动时间 (用于超时检测) |
| `interrupted` | `bool` | InterruptMonitor | - | 是否被用户打断 |

---

## 项目结构

```
smart-voice-robot/
├── main.py                          # 入口：构建行为树 + 主循环
├── engine.py                        # VoiceEngine：管理 KWS/ASR/VAD/TTS 模型和音频流
├── config.py                        # RobotConfig：所有可配置参数
├── rk3328.py                        # RK3328 降噪板串口协议驱动 (硬件唤醒)
├── nodes/
│   ├── __init__.py                  # 节点模块导出
│   ├── wake_word.py                 # WaitForWakeWord - 软件唤醒词检测
│   ├── hw_wake_word.py              # HardwareWakeWord - 硬件唤醒 (RK3328)
│   ├── listen.py                    # ListenCommand - 流式 ASR + VAD 静默超时
│   ├── intent.py                    # RecognizeIntent - 关键词意图识别
│   ├── speak.py                     # SpeakResponse + WakeupResponse - TTS
│   ├── guards.py                    # DialogContinueGuard - 对话循环守卫
│   ├── interrupt.py                 # InterruptMonitor - 打断监控 (预留)
│   ├── planner.py                   # LLMTaskPlanner - LLM Function Calling 多指令规划
│   ├── plan_executor.py             # PlanExecutor - 多步动作执行器
│   └── actions/
│       ├── __init__.py
│       ├── camera.py                # TakePhotoAction + RecordVideoAction + execute_* 函数
│       ├── robot_arm.py             # RobotArmAction + execute_robot_arm
│       ├── navigation.py            # NavigationAction + execute_navigate
│       ├── llm_dialog.py            # LLMDialogAction - 多 provider LLM 对话
│       ├── back_to_wakeup.py        # BackToWakeUp - 退出回到唤醒
│       └── default_response.py      # DefaultResponse - 兜底响应
├── test/
│   ├── test_cli.py                  # CLI 测试工具 (文本模拟语音输入)
│   └── mic_phone_connect.py         # 硬件串口调试工具
├── docs/
│   └── architecture.drawio          # draw.io 可编辑架构图
├── model/                           # 模型文件目录 (gitignore)
├── examples/
│   └── pytree_lifycycle.py          # py_trees 生命周期演示
├── pyproject.toml
└── uv.lock
```

---

## 依赖与安装

### 前置条件

- Python >= 3.10
- [uv](https://docs.astral.sh/uv/) 包管理器
- [Ollama](https://ollama.ai/) (本地 LLM 对话需要，或使用在线 Provider)
- 麦克风和扬声器硬件

### 语音模型

需要下载 [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) 模型文件，放置到 `config.py` 中 `MODELS_BASE` 指定的路径：

| 模型 | 用途 | 文件/目录名 |
|------|------|--------|
| zipformer-bilingual-zh-en | 流式 ASR (中英双语) | `sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20/` |
| kws-zipformer-wenetspeech | 关键词检测 (KWS) | `sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01/` |
| VITS aishell3 | TTS 语音合成 (174 音色) | `vits-zh-aishell3/` |
| Silero VAD | 语音活动检测 (静默超时) | `silero_vad.onnx` |

### 安装依赖

```bash
# 克隆项目
git clone <repo-url>
cd smart-voice-robot

# 使用 uv 安装依赖
uv sync

# 安装在线 LLM 支持 (可选)
uv sync --extra openai       # OpenAI / DeepSeek
uv sync --extra anthropic    # Anthropic
uv sync --extra online       # 全部在线 Provider

# 拉取本地 LLM 模型 (Ollama, 可选)
ollama pull qwen2.5:3b
```

### 核心依赖

| 包 | 版本 | 用途 |
|---|---|---|
| `py-trees` | >= 2.4.0 | 行为树框架 |
| `sherpa-onnx` | >= 1.12.23 | KWS / ASR / TTS 推理引擎 |
| `sherpa-onnx-bin` | >= 1.12.23 | sherpa-onnx 预编译二进制 |
| `sounddevice` | >= 0.5.5 | 音频采集与播放 |
| `numpy` | latest | 音频数据处理 |
| `langchain-ollama` | latest | Ollama LLM 接口 |
| `langchain-core` | latest | LangChain 消息类型 & Tool 定义 |
| `ollama` | >= 0.6.1 | Ollama Python SDK |
| `opencv-python` | >= 4.13.0 | 相机拍照/录像 |
| `pyserial` | >= 3.5 | RK3328 串口通信 |

### 可选依赖

| 安装组 | 包 | 用途 |
|--------|---|---|
| `openai` | `langchain-openai` | OpenAI / DeepSeek API |
| `anthropic` | `langchain-anthropic` | Anthropic Claude API |
| `online` | 上述全部 | 所有在线 LLM Provider |

---

## 配置说明

所有参数集中在 `config.py` 的 `RobotConfig` dataclass 中，修改后无需改动业务代码：

```python
@dataclass
class RobotConfig:
    # === 唤醒模式 ===
    # "software": sherpa-onnx KWS 软件唤醒
    # "hardware": RK3328 降噪板硬件唤醒
    wake_mode: str = "software"

    # === 硬件唤醒 (RK3328 降噪板) ===
    hw_serial_port: str = "/dev/ttyUSB0"
    hw_serial_baudrate: int = 115200
    hw_mic_array: str = "mic6_circle"   # mic4 / mic6 / mic6_circle

    # === 唤醒词 (KWS, 仅 software 模式) ===
    kws_keywords_file: str = "..."
    kws_keywords_threshold: float = 0.25

    # === TTS 音色 ===
    # aishell3: sid 0-173, 共 174 种音色
    tts_speaker_id: int = 21
    tts_speed: float = 1.0
    tts_max_chars_per_chunk: int = 120  # 长文本自动分段
    tts_pause_seconds: float = 0.15     # 段间停顿

    # === VAD (语音活动检测) ===
    vad_threshold: float = 0.5
    vad_min_silence_duration: float = 0.25
    vad_min_speech_duration: float = 0.25

    # === 对话 ===
    dialog_timeout: float = 15.0        # VAD 无活动超时 (秒)

    # === 相机 ===
    camera_index: int = 4               # /dev/video 设备索引
    camera_save_dir: str = "captures"   # 照片/视频保存目录
    camera_record_seconds: float = 10.0 # 视频录制时长 (秒)

    # === LLM ===
    # provider: "ollama" | "openai" | "deepseek" | "anthropic"
    llm_provider: str = "ollama"
    llm_model: str = "qwen2.5:3b"
    llm_base_url: str = "http://localhost:11434"
    llm_api_key: str = ""               # 在线模型的 API Key
    llm_system_prompt: str = "..."
    llm_max_history: int = 10           # 保留最近 N 轮对话历史

    # === 任务规划器 (LLM Function Calling) ===
    use_llm_planner: bool = False       # True 启用多指令规划
    planner_system_prompt: str = "..."

    # === 意图关键词映射 (仅关键词匹配模式) ===
    intent_patterns: dict = {
        "take_photo":    ["拍照", "拍张照", "拍个照", ...],
        "record_video":  ["录像", "录制视频", ...],
        "robot_arm":     ["机械臂", "抓取", ...],
        "navigation":    ["导航", "前往", ...],
        "exit":          ["退出", "结束", "停止", "没事了"],
    }

    # === TTS 响应模板 ===
    tts_responses: dict = {
        "wakeup":  "我在，请说。",
        "timeout": "没有听到您的命令，有需要可以再叫我。",
    }

    # === 系统 ===
    tick_interval: float = 0.05         # 主循环 tick 间隔
    num_threads: int = 2                # 模型推理线程数
```

---

## 运行

```bash
# 启动语音助手 (默认: 软件唤醒 + 关键词匹配模式)
uv run main.py
```

启动后系统进入待机状态，等待唤醒词。说出唤醒词后系统回应"我在，请说"，随后可以进行多轮对话：

- 说 **"拍照"** → 触发拍照
- 说 **"录像"** → 触发视频录制
- 说 **"机械臂抓取"** → 触发机械臂控制
- 说 **"导航到厨房"** → 触发 ROS 导航
- 说其他内容 → 交由 LLM 进行自由对话
- 说 **"退出" / "结束" / "停止" / "没事了"** → 播放告别语后回到待机
- VAD 检测到持续静默超过 `dialog_timeout` (默认 15s) → 播放超时提示后回到待机

若启用 LLM 规划器模式，需在 `config.py` 中设置 `use_llm_planner = True`，此时支持一句话多指令（如"先拍张照再导航到客厅"）。

---

## CLI 测试工具

`test/test_cli.py` 提供无硬件的快速测试，用文本输入替代麦克风 + ASR：

```bash
# 交互模式 (关键词匹配)
uv run test/test_cli.py

# 单次模式
uv run test/test_cli.py "帮我拍照"

# LLM 多指令规划模式
uv run test/test_cli.py --planner

# 指定在线 LLM Provider
uv run test/test_cli.py --planner --provider deepseek --api-key sk-xxx

# 启用 TTS 语音播报
uv run test/test_cli.py --tts
```

---

## 扩展指南

### 关键词匹配模式：添加新动作

1. 在 `nodes/actions/` 下创建新的 Behaviour 类，实现 `intent != "xxx" → FAILURE` 的守卫逻辑
2. 在 `config.py` 的 `intent_patterns` 中添加对应的关键词映射
3. 在 `main.py` 的 `create_tree()` 中将新节点添加到 `ActionSelector` 的子节点列表中

```python
# 示例：添加一个 "播放音乐" 动作

# 1. nodes/actions/music.py
class PlayMusicAction(Behaviour):
    def update(self):
        if self.blackboard.intent != "play_music":
            return Status.FAILURE
        # ... 播放逻辑 ...
        self.blackboard.response_text = "正在为您播放音乐。"
        return Status.SUCCESS

# 2. config.py
intent_patterns = {
    ...,
    "play_music": ["播放音乐", "放首歌", "来点音乐"],
}

# 3. main.py - 在 BackToWakeUp / DefaultResponse 之前添加
action_selector.add_children([
    ...,
    PlayMusicAction("PlayMusic"),
    BackToWakeUp("BackToWakeUp"),
    DefaultResponse("DefaultResponse"),  # 兜底始终放最后
])
```

### LLM 规划器模式：添加新动作

1. 在 `nodes/planner.py` 的 `_build_planner_tools()` 中添加新的 `@tool` 定义（仅 schema）
2. 在 `nodes/actions/` 中实现 `execute_xxx()` 函数
3. 在 `nodes/plan_executor.py` 的 `_execute_action()` 中添加分发逻辑
