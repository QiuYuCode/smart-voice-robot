# 快速开始指南

## 一分钟上手

```bash
# 1. 启动程序
./run_assistant.sh
# 或
python voice_assistant.py

# 2. 使用
说 "你好助手" → 听到 "我在，请说"
说 "打开摄像头" → 摄像头打开
按 'q' 关闭 → 继续监听
说 "停止" → 回到待机

# 3. 退出
按 Ctrl+C
```

## 五分钟配置

```bash
# 1. 安装依赖
uv sync
sudo apt-get install espeak  # Linux TTS

# 2. 下载 Vosk 模型
wget https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip
unzip vosk-model-small-cn-0.22.zip -d model/

# 3. 修改配置（可选）
vi config.py
# 修改 VOSK_MODEL_PATH、WAKE_WORDS 等

# 4. 运行
python voice_assistant.py
```

## 支持的指令

| 说什么 | 做什么 |
|--------|--------|
| "你好助手" / "小助手" | 唤醒系统 |
| "打开摄像头" | 显示实时画面 |
| "查询天气" | 播报天气信息 |
| "播放音乐" | 播放音乐提示 |
| "停止" / "退出" / "休眠" | 回到待机状态 |

## 行为树结构（简化）

```
待机 → 唤醒词检测
  ↓
激活 → 播报 "我在，请说"
  ↓
监听 → 等待指令
  ↓
识别 → 匹配意图
  ↓
执行 → 打开摄像头/查天气/播音乐
  ↓
播报 → 结果反馈
  ↓
继续监听 或 超时待机 或 被打断待机
```

## 关键文件

| 文件 | 用途 |
|------|------|
| `voice_assistant.py` | 主程序 |
| `config.py` | 配置文件 |
| `run_assistant.sh` | 启动脚本 |
| `test_voice_assistant.py` | 测试指南 |
| `visualize_tree.py` | 可视化工具 |
| `README_VOICE_ASSISTANT.md` | 完整文档 |
| `USAGE.md` | 使用手册 |

## 常见问题

**Q: 麦克风无法识别？**
```bash
python -c "import speech_recognition as sr; print(sr.Microphone.list_microphone_names())"
```

**Q: TTS 无声音？**
```bash
sudo apt-get install espeak
```

**Q: 唤醒词不准？**
- 下载更大的 Vosk 模型
- 调整 `config.py` 中的参数

**Q: 打断延迟？**
- 降低 `INTERRUPT_TIMEOUT` 参数

## 测试流程

```bash
# 查看测试指南
python test_voice_assistant.py

# 可视化行为树
python visualize_tree.py

# 验证配置
python config.py
```

## 添加新指令（示例）

```python
# 1. config.py
INTENT_PATTERNS = {
    "open_light": ["打开", "灯"],
}

# 2. voice_assistant.py
class OpenLightAction(py_trees.behaviour.Behaviour):
    def update(self):
        if self.blackboard.intent != "open_light":
            return py_trees.common.Status.FAILURE
        print("💡 灯已打开")
        self.blackboard.response_text = "灯已打开"
        return py_trees.common.Status.SUCCESS

# 3. 添加到 action_selector
action_selector.add_children([
    OpenLightAction(),  # 新增
    OpenCameraAction(),
    # ...
])
```

## 目录结构

```
pytree_learing/
├── voice_assistant.py          # 主程序 (~700行)
├── config.py                   # 配置 (~200行)
├── run_assistant.sh            # 启动脚本
├── test_voice_assistant.py     # 测试指南
├── visualize_tree.py           # 可视化
├── README_VOICE_ASSISTANT.md   # 项目说明
├── USAGE.md                    # 使用手册
├── QUICK_START.md              # 本文件
├── IMPLEMENTATION_SUMMARY.md   # 实现总结
├── pyproject.toml              # 依赖
└── model/                      # Vosk 模型
    └── small/
```

## 技术栈

- **行为树**: py_trees 2.4+
- **语音识别**: Vosk 0.3+ (离线)
- **TTS**: pyttsx3 2.91+ (离线)
- **视觉**: OpenCV 4.13+
- **Python**: 3.12+

## 性能

- 启动: ~2-3s
- 唤醒延迟: ~500ms-1s
- CPU: 5-10% (待机), 20-30% (活跃)
- 内存: ~200MB (小模型)

## 完整文档

- 📖 项目说明: `README_VOICE_ASSISTANT.md`
- 📖 使用手册: `USAGE.md`
- 📖 实现总结: `IMPLEMENTATION_SUMMARY.md`
- 📖 快速开始: `QUICK_START.md` (本文件)

---

**提示**: 首次使用建议先查看 `test_voice_assistant.py` 了解测试流程！
