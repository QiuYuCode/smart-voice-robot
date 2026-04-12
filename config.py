"""
机器人语音助手配置文件

所有可配置参数集中在 RobotConfig dataclass 中。
修改此文件即可调整唤醒词、音色、LLM 模型、意图关键词等，无需修改业务代码。
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

def _read_env(*keys: str) -> str:
    """按顺序读取环境变量，并做去空白/去包裹引号清洗。"""
    for key in keys:
        value = os.getenv(key)
        if value is None:
            continue
        cleaned = value.strip().strip('"').strip("'").strip()
        if cleaned:
            return cleaned
    return ""


# 项目根目录
base_dir = Path(__file__).parent

# ============================================================================
# 模型路径 (根据实际下载位置修改)
# ============================================================================

MODELS_BASE = base_dir / "model" / "voice_models"

if not MODELS_BASE.exists():
    MODELS_BASE.mkdir(parents=True, exist_ok=True)
    logger.info(f"模型目录不存在，已创建: {MODELS_BASE}")
    
# sherpa-onnx 流式 ASR
ASR_DIR = MODELS_BASE / "sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20"

# sherpa-onnx 关键词检测
KWS_DIR = MODELS_BASE / "sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01"

# sherpa-onnx VITS TTS
TTS_DIR = MODELS_BASE / "vits-zh-hf-fanchen-C"

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

    # --- ASR 后端 ---
    # "local": 本地 sherpa-onnx 流式识别
    # "iflytek_cloud": 讯飞云识别
    asr_backend: str = "local"
    # "streaming": 逐帧上传(40ms)；"endpoint_once": 端点后一次性上传
    cloud_asr_strategy: str = "streaming"
    cloud_asr_fallback_to_local: bool = True

    # --- 讯飞云 ASR 配置 (/v2/iat) ---
    iflytek_iat_app_id: str = _read_env("XFYUN_IAT_APPID", "XFYUN_APPID")
    iflytek_iat_api_key: str = _read_env("XFYUN_IAT_API_KEY", "XFYUN_API_KEY")
    iflytek_iat_api_secret: str = _read_env("XFYUN_IAT_API_SECRET", "XFYUN_API_SECRET")
    iflytek_iat_language: str = "zh_cn"
    iflytek_iat_domain: str = "iat"
    iflytek_iat_accent: str = "mandarin"
    iflytek_iat_eos_ms: int = 1800
    iflytek_iat_ptt: int = 1
    iflytek_iat_audio_format: str = "audio/L16;rate=16000"
    iflytek_iat_encoding: str = "raw"
    cloud_asr_preroll_seconds: float = 0.3

    # --- TTS 音色 ---
    # fanchen-C 单说话人模型，sid 固定为 0
    tts_speaker_id: int = 0
    tts_speed: float = 1.2
    tts_volume: float = 1.0  # 本地 TTS 音量增益，1.0=原始，>1.0 放大，超出 [-1,1] 自动截断
    tts_max_chars_per_chunk: int = 80
    tts_sentence_pause: float = 0.40
    tts_clause_pause: float = 0.15
    tts_backend: str = "iflytek_cloud"  # "local" | "iflytek_cloud"
    cloud_tts_fallback_to_local: bool = True

    # --- 讯飞云 TTS 配置 (/v2/tts) ---
    iflytek_tts_app_id: str = _read_env("XFYUN_TTS_APPID", "XFYUN_APPID")
    iflytek_tts_api_key: str = _read_env("XFYUN_TTS_API_KEY", "XFYUN_API_KEY")
    iflytek_tts_api_secret: str = _read_env("XFYUN_TTS_API_SECRET", "XFYUN_API_SECRET")
    iflytek_tts_vcn: str = "xiaoyan"
    iflytek_tts_aue: str = "raw"
    iflytek_tts_auf: str = "audio/L16;rate=16000"
    iflytek_tts_speed: int = 50
    iflytek_tts_tte: str = "UTF8"
    iflytek_tts_request_text_encoding: str = "utf-8"
    iflytek_tts_max_bytes: int = 8000

    # --- VAD (语音活动检测) ---
    vad_threshold: float = 0.5
    vad_min_silence_duration: float = 0.25
    vad_min_speech_duration: float = 0.25

    # --- 音频设备选择 ---
    # 优先按子串匹配设备名；为空则使用系统默认设备。
    # 例如: "XFM-DP"、"C-Media"、"USB Audio"
    input_device_hint: str = "XFM-DP"
    output_device_hint: str = "C-Media"

    # --- 对话 ---
    dialog_timeout: float = 15.0  # 秒，无活动后超时回到 idle
    interrupt_min_speech_seconds: float = 0.6  # TTS 启动后延迟启用打断

    # --- 相机 ---
    camera_index: int = 0  # /dev/video 设备索引 (0=普通摄像头, 4=RealSense 彩色流)
    camera_width: int = 640
    camera_height: int = 480
    camera_save_dir: str = "captures"  # 照片/视频保存目录 (相对于项目根目录)
    camera_record_seconds: float = 10.0  # 视频录制时长 (秒)
    camera_record_fps: float = 30.0  # 视频录制帧率 (相机未报告时使用)

    # --- LLM ---
    # provider: "ollama" | "openai" | "deepseek" | "anthropic"
    llm_provider: str = "ollama"
    llm_model: str = "qwen2.5:0.5b"
    llm_base_url: str = "http://localhost:11434"
    llm_api_key: str = "" if llm_provider == "ollama" else _read_env("LLM_API_KEY") # 在线模型的 API Key (ollama 不需要)
    llm_system_prompt: str = (
        "你是一个机器人语音助手。回答要求：\n"
        "1. 用简短自然的口语化中文回答，像人在说话一样。\n"
        "2. 善用逗号断句，避免一口气说完长句子。\n"
        "3. 禁止输出 emoji、表情符号、括号注释、markdown 格式。\n"
        "4. 禁止输出列表编号，改用自然语言衔接，比如用首先、然后、最后。\n"
        "5. 数字用中文读法，比如三百二十，而非320。\n"
    )
    llm_max_history: int = 10  # 保留最近 N 轮对话历史
    llm_request_timeout: float = 12.0  # 单次 LLM 请求超时(秒)

    # --- VLM (视觉语言模型) ---
    # provider: "ollama" | "openai" | "deepseek" | "anthropic"
    vlm_provider: str = "ollama"
    vlm_model: str = "qwen2.5:0.5b"
    vlm_base_url: str = "http://localhost:11434"
    vlm_api_key: str = ""
    vlm_system_prompt: str = (
        "你是一个机器人的视觉系统。根据图片内容，用简短自然的中文描述你看到的场景。\n"
        "用第一人称：我"
        "禁止输出 emoji、表情符号、markdown 格式。\n"
    )

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
        "describe_scene": ["看一下", "看看", "这是什么", "前面有什么", "描述一下", "看到了什么"],
        "take_photo": ["拍照", "拍张照", "拍个照", "拍一张", "照片"],
        "record_video": ["录像", "录制视频", "录视频", "录一段", "摄像", "拍个视频", "拍视频"],
        "robot_arm": ["机械臂", "抓取", "拿起", "放下"],
        "navigation": ["导航", "前往", "去", "带我去"],
        "exit": ["退出", "结束", "停止", "没事了", "拜拜", "退下吧"],
    })

    # --- TTS 响应模板 ---
    tts_responses: dict[str, str] = field(default_factory=lambda: {
        "wakeup": "我在，请说。",
        "timeout": "没有听到您的命令，有需要可以再叫我。",
    })

    # --- 启动提示音 ---
    startup_sound_enabled: bool = True
    startup_sound_text: str = "系统启动完成"

    # --- 系统 ---
    tick_interval: float = 0.05  # 主循环心跳间隔 (秒)
    num_threads: int = 2  # 模型推理线程数
    onnx_provider: str = "cpu"  # ONNX 推理设备: "cuda" | "cpu"
    verbose: bool = True

    # --- 日志 ---
    log_dir: str = "logs"           # 日志文件保存目录
    log_retention: str = "7 days"   # 日志保留时长
    log_level: str = "DEBUG"        # 文件日志级别

    # --- 监控后台 ---
    enable_monitor: bool = True   # 是否启用 Web 监控面板
    monitor_port: int = 8765        # 监控面板端口


# 全局默认配置实例
default_config = RobotConfig()
