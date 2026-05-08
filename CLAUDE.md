# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 提供该仓库的使用指南。

## 命令

```bash
# 安装
uv sync                    # 安装所有依赖
uv sync --extra online     # 安装可选在线依赖（openai、anthropic）
uv add <package>           # 添加新依赖

# 运行
uv run main.py             # 启动机器人助手

# 测试
uv run test/test_cli.py                         # 交互模式（关键词匹配）
uv run test/test_cli.py "帮我拍照"              # 单命令模式
uv run test/test_cli.py --planner               # LLM 多指令模式
uv run test/test_cli.py --planner --tts          # Planner + TTS 输出
uv run test/test_cli.py --provider deepseek     # 指定 LLM 提供商
```

## 架构

基于 **py_trees 行为树**编排完整语音交互流水线的语音控制机器人助手。

### 系统流程

```
麦克风 → dialog_audio_queue → 唤醒词检测 → ASR → 意图识别 → 动作执行 → TTS → 扬声器
```

**两种意图模式：**
- **关键词匹配**（默认）：快速、轻量、固定意图集，见 `nodes/intent.py`
- **LLM 规划器**（可选）：通过 LangChain Function Calling 实现多步自然语言指令，见 `nodes/planner.py` + `nodes/plan_executor.py`

### 核心组件

| 文件 | 职责 |
|------|------|
| `main.py` | 入口；构建并驱动行为树 |
| `config.py` | 统一的 `RobotConfig` 数据类 — 所有参数集中于此 |
| `engine.py` | `VoiceEngine` — 管理 KWS/ASR/VAD/TTS 模型生命周期和音频队列 |
| `nodes/` | 所有行为树节点实现 |
| `nodes/actions/` | 动作节点（摄像头、视觉、LLM 对话、机械臂、导航） |
| `test/test_cli.py` | 无硬件测试的 CLI 工具（使用 `SimpleTTS`） |

### Blackboard 通信

所有节点间状态通过 py_trees Blackboard 传递，命名空间为 `"dialog"`：

```python
self.blackboard = self.attach_blackboard_client(name="MyNode", namespace="dialog")
self.blackboard.register_key(key="intent", access=py_trees.common.Access.READ)
self.blackboard.register_key(key="response_text", access=py_trees.common.Access.WRITE)
```

关键 Blackboard 字段：`user_command`、`intent`、`response_text`、`is_speaking`、`exit_signal`

### 多 Provider 支持

- **ASR**：本地（sherpa-onnx Zipformer）或云端（讯飞）— 通过 `config.asr_backend` 配置
- **TTS**：本地（VITS aishell3）或云端（讯飞，带本地回退）— 通过 `config.tts_backend` 配置
- **LLM**：ollama、openai、deepseek、anthropic — 通过 `config.llm_provider` 配置
- **VLM**：ollama 或 openai — 用于视觉/摄像头描述动作

### 环境变量

```
XFYUN_IAT_APPID / _API_KEY / _API_SECRET   # 讯飞云 ASR
XFYUN_TTS_APPID / _API_KEY / _API_SECRET   # 讯飞云 TTS
LLM_API_KEY                                  # OpenAI / DeepSeek / Anthropic
```

## 代码风格

完整规范见 `AGENTS.md`。要点：
- Python 3.10+，使用 `from __future__ import annotations`
- 类型提示使用联合语法：`float | None` 而非 `Optional[float]`
- Google 风格文档字符串，中文
- 动作节点：意图不匹配时返回 `Status.FAILURE`（Selector 模式）
- 可选导入用 `try/except ImportError` 包裹，并将模块设为 `None`
