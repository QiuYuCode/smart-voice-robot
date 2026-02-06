# 语音助手系统使用指南

## 概述

这是一个基于 py_trees 行为树实现的语音交互系统，支持：
- 唤醒词检测
- 多指令识别（摄像头、天气、音乐）
- 随时打断功能
- 超时自动待机

## 系统架构

### 行为树结构

```
Root (Selector with memory=True)
├── WakeWordDetector (待机状态)
└── ActiveState (激活状态)
    └── Parallel (SuccessOnOne - 支持打断)
        ├── InterruptMonitor (打断监听器)
        └── DialogLoop (对话循环)
            └── Sequence
                ├── PlayWakeupSound (播报唤醒)
                ├── ListenForCommand (监听指令)
                ├── RecognizeIntent (识别意图)
                ├── ExecuteAction (执行动作)
                ├── PlayResponseSound (播报结果)
                └── CheckDialogTimeout (超时检查)
```

### 状态流转

```
[待机] → 检测唤醒词 → [激活] → 播报 → 监听 → 识别 → 执行 → 播报 → 监听...
                                                     ↓ (超时/打断)
                                                  [待机]
```

## 安装依赖

```bash
# 使用 uv 安装
uv pip install pyttsx3

# 或使用 pip
pip install pyttsx3

# 完整依赖列表
# - opencv-python>=4.13.0.90
# - py-trees>=2.4.0
# - pyaudio>=0.2.14
# - pyttsx3>=2.91
# - speechrecognition>=3.14.5
# - vosk>=0.3.45
```

## 运行程序

```bash
python voice_assistant.py
```

## 使用说明

### 1. 唤醒系统

**唤醒词**: "你好助手" 或 "小助手" 或 "助手"

```
[待机] 聆听唤醒词...
     ↓ (说 "你好助手")
[播报] "我在，请说"
```

### 2. 执行指令

系统支持以下指令：

#### 打开摄像头
- **指令**: "打开摄像头"
- **响应**: 打开摄像头窗口，显示实时画面
- **退出**: 按键盘 'q' 关闭摄像头

#### 查询天气
- **指令**: "查询天气" 或 "今天天气"
- **响应**: 播报天气信息（模拟数据）

#### 播放音乐
- **指令**: "播放音乐"
- **响应**: 播报音乐播放提示（模拟）

#### 未知指令
- **响应**: "抱歉，我还不能理解这个指令"

### 3. 打断功能

在任何时候（播报、执行、监听），说出打断词立即回到待机：

**打断词**: "停止" 或 "别说了" 或 "退出" 或 "休眠"

```
[执行] 摄像头正在运行...
     ↓ (说 "停止")
⚠️ 检测到打断指令
     ↓
[待机] 聆听唤醒词...
```

### 4. 超时机制

如果 10 秒内没有语音输入，系统自动回到待机状态：

```
[监听] 等待指令...
     ↓ (10秒无输入)
⏰ 对话超时
     ↓
[待机] 聆听唤醒词...
```

## 完整交互流程示例

### 示例 1: 正常流程

```
用户: "你好助手"
系统: [播报] "我在，请说"

用户: "打开摄像头"
系统: [执行] 打开摄像头窗口
系统: [播报] "摄像头已打开，按q关闭"

用户: 按 'q'
系统: [关闭] 摄像头窗口
系统: [监听] 等待下一个指令...

(10秒无输入)
系统: [超时] 回到待机状态
```

### 示例 2: 打断流程

```
用户: "你好助手"
系统: [播报] "我在，请说"

用户: "打开摄像头"
系统: [执行] 摄像头正在运行...

用户: "停止"
系统: [打断] 关闭摄像头
系统: [重置] 回到待机状态
```

### 示例 3: 连续指令

```
用户: "你好助手"
系统: [播报] "我在，请说"

用户: "查询天气"
系统: [播报] "今天天气晴朗，温度25度"
系统: [监听] 继续等待指令...

用户: "播放音乐"
系统: [播报] "正在为您播放音乐"
系统: [监听] 继续等待指令...

用户: "退出"
系统: [打断] 回到待机状态
```

## 调试技巧

### 1. 查看详细日志

修改 `voice_assistant.py` 中的日志级别：

```python
log_tree.Level = log_tree.Level.DEBUG  # 显示详细信息
```

### 2. 可视化行为树

在主程序中添加：

```python
import py_trees.display as display

tree = create_tree()
display.render_dot_tree(tree, name="voice_assistant_tree")
# 会生成 voice_assistant_tree.png 行为树图
```

### 3. 监控黑板状态

在每个节点的 `update()` 方法中添加：

```python
def update(self):
    self.logger.debug(f"黑板状态: {self.blackboard.__dict__}")
    # ... 正常逻辑
```

### 4. 测试单个节点

```python
# 测试唤醒词检测
detector = WakeWordDetector()
detector.setup()
status = detector.update()
print(f"状态: {status}")
```

## 常见问题

### Q1: 麦克风无法识别

**解决方案**:
```bash
# 检查麦克风设备
python -c "import speech_recognition as sr; print(sr.Microphone.list_microphone_names())"

# 调整环境噪音阈值
self.recognizer.energy_threshold = 4000  # 增加阈值
```

### Q2: TTS 播报失败

**解决方案**:
```bash
# Linux 需要安装 espeak
sudo apt-get install espeak

# 测试 TTS
python -c "import pyttsx3; engine = pyttsx3.init(); engine.say('测试'); engine.runAndWait()"
```

### Q3: Vosk 模型路径错误

**解决方案**:
修改 `voice_assistant.py` 中的模型路径：
```python
self.vosk_model_path = '/your/path/to/vosk/model'
```

### Q4: 唤醒词识别不准确

**解决方案**:
- 调整唤醒词列表：添加更多变体
```python
if any(wake in text for wake in ["你好助手", "小助手", "助手", "喂助手"]):
```

- 降低识别阈值
- 使用更大的 Vosk 模型

### Q5: 打断功能延迟

**原因**: `InterruptMonitor` 和主流程并行运行，存在轮询间隔

**优化方案**:
```python
# 减少超时时间
audio = self.recognizer.listen(source, timeout=0.3, phrase_time_limit=2)
```

## 性能优化

### 1. 减少模型加载时间

在 `setup()` 中只加载一次模型，多个节点共享：

```python
# 使用黑板共享模型
self.blackboard.vosk_model = vosk.Model(path)
```

### 2. 异步 TTS 播报

使用线程避免阻塞：

```python
def play_async(self, text):
    thread = threading.Thread(target=self.tts_engine.say, args=(text,))
    thread.start()
```

### 3. 降低 CPU 占用

调整主循环休眠时间：

```python
while True:
    tree.tick_once()
    time.sleep(0.05)  # 从 0.01 增加到 0.05
```

## 扩展功能

### 添加新指令

1. 在 `RecognizeIntent` 中添加意图模式：
```python
self.intent_patterns = {
    "your_intent": ["关键词1", "关键词2"]
}
```

2. 创建对应的动作节点：
```python
class YourAction(py_trees.behaviour.Behaviour):
    def update(self):
        # 执行逻辑
        pass
```

3. 添加到 `action_selector`：
```python
action_selector.add_children([
    YourAction(),
    # ... 其他动作
])
```

### 接入真实 API

修改动作节点中的模拟代码：

```python
class QueryWeatherAction(py_trees.behaviour.Behaviour):
    def update(self):
        import requests
        response = requests.get("https://api.weather.com/...")
        weather_data = response.json()
        self.blackboard.response_text = f"今天{weather_data['description']}"
        return py_trees.common.Status.SUCCESS
```

## 测试

运行测试脚本查看测试指南：

```bash
python test_voice_assistant.py
```

## 许可

MIT License
