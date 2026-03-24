"""
机器人语音助手配置文件

所有可配置参数集中在 RobotConfig dataclass 中。
修改此文件即可调整唤醒词、音色、LLM 模型、意图关键词等，无需修改业务代码。
"""

from dataclasses import dataclass, field
from pathlib import Path


# ============================================================================
# 模型路径 (根据实际下载位置修改)
# ============================================================================

MODELS_BASE = Path("/home/nvidia/WorkSpace/models/voice_models")

# sherpa-onnx 流式 ASR
ASR_DIR = MODELS_BASE / "sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20"

# sherpa-onnx 关键词检测
KWS_DIR = MODELS_BASE / "sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01"

# sherpa-onnx VITS TTS (aishell3, 174 说话人)
TTS_DIR = MODELS_BASE / "vits-zh-aishell3"

# Silero VAD 模型
VAD_DIR = MODELS_BASE / "silero_vad.onnx"


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
    wake_mode: str = "software"

    # --- 硬件唤醒 (RK3328 降噪板) ---
    hw_serial_port: str = "/dev/ttyUSB0"
    hw_serial_baudrate: int = 115200
    hw_mic_array: str = "mic6_circle"  # mic4: 线性4麦, mic6: 线性6麦, mic6_circle: 环形6麦

    # --- 唤醒词 (KWS, 仅 software 模式) ---
    # 替换 keywords_file 路径即可更换唤醒词
    kws_keywords_file: str = str(KWS_DIR / "keywords.txt")
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

    # --- 相机 ---
    camera_index: int = 4  # /dev/video 设备索引 (RealSense 彩色流)
    camera_width: int = 640
    camera_height: int = 480
    camera_save_dir: str = "captures"  # 照片/视频保存目录 (相对于项目根目录)
    camera_record_seconds: float = 10.0  # 视频录制时长 (秒)
    camera_record_fps: float = 30.0  # 视频录制帧率 (相机未报告时使用)

    # --- LLM ---
    # provider: "ollama" | "openai" | "deepseek" | "anthropic"
    llm_provider: str = "ollama"
    llm_model: str = "qwen2.5:3b"
    llm_base_url: str = "http://localhost:11434"
    llm_api_key: str = ""  # 在线模型的 API Key (ollama 不需要)
    llm_system_prompt: str = "你是一个机器人助手，请用简短的中文回答用户的问题, 不要输出 emoji 表情和其他任何表情符号。"
    llm_max_history: int = 10  # 保留最近 N 轮对话历史

    # --- 任务规划器 (LLM Function Calling) ---
    # True 时使用 LLM 解析多步指令，False 时使用关键词匹配（原有行为）
    use_llm_planner: bool = False
    planner_system_prompt: str = (
        "你是一个机器人任务规划器。根据用户的自然语言指令，调用合适的工具来完成任务。\n"
        "规则：\n"
        "1. 如果用户给出多个指令，请按顺序调用多个工具。\n"
        "2. 如果用户只是闲聊或提问，直接用简短中文回复，不要调用任何工具。\n"
        "3. 不要输出 emoji 表情和其他任何表情符号。\n"
    )

    # --- 意图关键词映射 ---
    # key: 意图名称, value: 触发该意图的关键词列表
    intent_patterns: dict[str, list[str]] = field(default_factory=lambda: {
        "take_photo": ["拍照", "拍张照", "拍个照", "拍一张", "照片", "看一下"],
        "record_video": ["录像", "录制视频", "录视频", "录一段", "摄像"],
        "robot_arm": ["机械臂", "抓取", "拿起", "放下"],
        "navigation": ["导航", "前往", "去", "带我去"],
        "exit": ["退出", "结束", "停止", "没事了"],
    })

    # --- TTS 响应模板 ---
    tts_responses: dict[str, str] = field(default_factory=lambda: {
        "wakeup": "我在，请说。",
        "timeout": "没有听到您的命令，有需要可以再叫我。",
    })

    # --- 系统 ---
    tick_interval: float = 0.05  # 主循环心跳间隔 (秒)
    num_threads: int = 2  # 模型推理线程数
    verbose: bool = True


# 全局默认配置实例
default_config = RobotConfig()
