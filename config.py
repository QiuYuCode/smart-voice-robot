"""
机器人语音助手配置文件

所有可配置参数集中在 RobotConfig dataclass 中。
修改此文件即可调整唤醒词、音色、LLM 模型、意图关键词等，无需修改业务代码。
"""

from dataclasses import dataclass, field


# ============================================================================
# 模型路径 (根据实际下载位置修改)
# ============================================================================

MODELS_BASE = "/home/create/DataDisk/WorkSpace/models/voice_models"

# sherpa-onnx 流式 ASR
ASR_DIR = f"{MODELS_BASE}/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20"

# sherpa-onnx 关键词检测
KWS_DIR = f"{MODELS_BASE}/sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01"

# sherpa-onnx VITS TTS (aishell3, 174 说话人)
TTS_DIR = f"{MODELS_BASE}/vits-zh-aishell3"

# Silero VAD 模型
VAD_MODEL = f"{MODELS_BASE}/silero_vad.onnx"


# ============================================================================
# 音频常量
# ============================================================================

SAMPLE_RATE = 16000
CHUNK_SIZE = int(SAMPLE_RATE * 0.1)  # 0.1 秒 = 1600 采样点


# ============================================================================
# 配置 dataclass
# ============================================================================

@dataclass
class RobotConfig:
    """机器人语音助手的全部可配置参数"""

    # --- 唤醒模式 ---
    # "software": sherpa-onnx KWS 软件唤醒
    # "hardware": RK3328 降噪板硬件唤醒
    wake_mode: str = "hardware"

    # --- 硬件唤醒 (RK3328 降噪板) ---
    hw_serial_port: str = "/dev/ttyUSB0"
    hw_serial_baudrate: int = 115200
    hw_mic_array: str = "mic6_circle"  # mic4: 线性4麦, mic6: 线性6麦, mic6_circle: 环形6麦

    # --- 唤醒词 (KWS, 仅 software 模式) ---
    # 替换 keywords_file 路径即可更换唤醒词
    kws_keywords_file: str = f"{KWS_DIR}/keywords.txt"
    kws_keywords_score: float = 1.0
    kws_keywords_threshold: float = 0.25
    kws_num_trailing_blanks: int = 1

    # --- TTS 音色 ---
    # aishell3 模型支持 sid 0-173，共 174 种音色
    tts_speaker_id: int = 21
    tts_speed: float = 1.0
    tts_max_chars_per_chunk: int = 120
    tts_pause_seconds: float = 0.15

    # --- VAD (语音活动检测) ---
    vad_threshold: float = 0.5
    vad_min_silence_duration: float = 0.25
    vad_min_speech_duration: float = 0.25

    # --- 对话 ---
    dialog_timeout: float = 15.0  # 秒，无活动后超时回到 idle
    interrupt_min_speech_seconds: float = 0.6  # TTS 启动后延迟启用打断

    # --- LLM (langchain-ollama) ---
    llm_model: str = "deepseek-r1:8b"
    llm_base_url: str = "http://localhost:11434"
    llm_system_prompt: str = "你是一个机器人助手，请用简短的中文回答用户的问题, 不要输出 emoji 表情和其他任何表情符号。"
    llm_max_history: int = 10  # 保留最近 N 轮对话历史

    # --- 意图关键词映射 ---
    # key: 意图名称, value: 触发该意图的关键词列表
    intent_patterns: dict[str, list[str]] = field(default_factory=lambda: {
        "open_camera": ["打开相机", "拍照", "看一下", "摄像头"],
        "robot_arm": ["机械臂", "抓取", "拿起", "放下"],
        "navigation": ["导航", "前往", "去", "带我去"],
    })

    # --- TTS 响应模板 ---
    tts_responses: dict[str, str] = field(default_factory=lambda: {
        "wakeup": "我在，请说。",
        "timeout": "好的，我先休息了。",
    })

    # --- 系统 ---
    tick_interval: float = 0.05  # 主循环心跳间隔 (秒)
    num_threads: int = 2  # 模型推理线程数
    verbose: bool = True


# 全局默认配置实例
default_config = RobotConfig()
