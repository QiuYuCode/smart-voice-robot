"""
机器人语音助手配置文件

所有可配置参数集中在 RobotConfig dataclass 中。
运行时配置从 config.yaml 加载；敏感字段（API Key 等）始终从环境变量读取。
"""
from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
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

    # --- 模型路径 ---
    # 相对路径以项目根目录为基准；绝对路径直接使用
    asr_model_dir: str = str(ASR_DIR)
    kws_model_dir: str = str(KWS_DIR)
    tts_model_dir: str = str(TTS_DIR)
    vad_model_path: str = str(VAD_DIR)

    # --- 唤醒模式 ---
    # "software": sherpa-onnx KWS 软件唤醒（唯一支持的模式）
    wake_mode: str = "software"

    # --- 唤醒词 (KWS) ---
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
    # 三路相机统一管理: head (头部 RealSense) / left_palm / right_palm
    # backend: "local" (本机 USB) | "http" (远端 FastAPI) | "ros" (rclpy 订阅)
    camera_backend: str = "local"
    default_camera: str = "head"  # describe_scene / take_photo / record_video 默认使用的相机

    # HTTP 后端: 远端 FastAPI 服务基址，URL 形如 {base}/snapshot/{camera_id}
    camera_http_base_url: str = ""          # e.g. http://10.168.1.101:8080
    camera_http_timeout: float = 5.0

    # ROS 后端 (rclpy + cv_bridge)
    camera_ros_node_name: str = "smart_voice_robot_camera_sub"
    camera_ros_qos_depth: int = 5
    camera_ros_warmup_seconds: float = 2.0  # 启动时等待首帧的超时

    # 每台相机的规格; YAML 中通过 cameras.{id}.{field} 覆盖
    cameras: dict[str, dict[str, Any]] = field(default_factory=lambda: {
        "head": {
            "index": 4,
            "width": 640,
            "height": 480,
            "ros_topic": "/camera/color/image_raw",
            "record_fps": 30.0,
        },
        "left_palm": {
            "index": 0,
            "width": 640,
            "height": 480,
            "ros_topic": "/left_gripper/image_raw",
            "record_fps": 30.0,
        },
        "right_palm": {
            "index": 2,
            "width": 640,
            "height": 480,
            "ros_topic": "/right_gripper/image_raw",
            "record_fps": 30.0,
        },
    })

    # 通用相机参数
    camera_save_dir: str = "captures"           # 照片/视频保存目录 (相对于项目根目录)
    camera_record_seconds: float = 10.0         # 视频录制时长 (秒)

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
    vlm_model: str = "qwen3.5:0.8b"
    vlm_base_url: str = "http://localhost:11434"
    vlm_api_key: str = ""
    vlm_system_prompt: str = (
        "你是一个机器人的视觉系统。根据图片内容，用简短自然的中文描述你看到的场景。\n"
        "用第一人称：我看到了。\n"
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
    interrupt_wakeup_responses: list[str] = field(default_factory=lambda: [
        "我在，请说。",
        "唉，我在。",
        "怎么了。",
    ])

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


# YAML 配置文件路径
CONFIG_YAML_PATH: Path = base_dir / "config.yaml"

# 不写入 YAML 的敏感字段，始终从环境变量读取
_SECRET_FIELDS: frozenset[str] = frozenset({
    "iflytek_iat_app_id",
    "iflytek_iat_api_key",
    "iflytek_iat_api_secret",
    "iflytek_tts_app_id",
    "iflytek_tts_api_key",
    "iflytek_tts_api_secret",
    "llm_api_key",
    "vlm_api_key",
})

# 相对路径字段：YAML 中若为相对路径，自动解析为相对项目根目录的绝对路径
_PATH_FIELDS: frozenset[str] = frozenset({
    "kws_keywords_file",
    "asr_model_dir",
    "kws_model_dir",
    "tts_model_dir",
    "vad_model_path",
})


def load_config(path: Path | str | None = None) -> RobotConfig:
    """从 YAML 文件加载配置，敏感字段始终从环境变量覆盖。

    Args:
        path: YAML 文件路径，默认为项目根目录下的 config.yaml。

    Returns:
        填充好的 RobotConfig 实例。
    """
    cfg = RobotConfig()
    yaml_path = Path(path) if path is not None else CONFIG_YAML_PATH

    if yaml_path.exists():
        with open(yaml_path, encoding="utf-8") as f:
            data: dict[str, Any] = yaml.safe_load(f) or {}

        # 旧版平铺相机字段 → 迁移到 cameras.head.*
        _LEGACY_CAMERA_MAP = {
            "camera_index": "index",
            "camera_width": "width",
            "camera_height": "height",
            "camera_record_fps": "record_fps",
        }
        legacy_head_overrides: dict[str, Any] = {}
        for legacy_key, new_key in _LEGACY_CAMERA_MAP.items():
            if legacy_key in data:
                legacy_head_overrides[new_key] = data.pop(legacy_key)
                logger.warning(
                    f"[config] {legacy_key!r} 已废弃，已自动映射到 cameras.head.{new_key}；"
                    f"请在 config.yaml 中迁移到新结构。"
                )

        for key, value in data.items():
            if key in _SECRET_FIELDS:
                continue
            if not hasattr(cfg, key):
                logger.warning(f"[config] 忽略未知配置项: {key!r}")
                continue
            if key == "cameras" and isinstance(value, dict):
                # 与默认字典合并，YAML 只需覆盖需要的相机/字段
                merged = {cid: dict(spec) for cid, spec in cfg.cameras.items()}
                for cid, spec in value.items():
                    if not isinstance(spec, dict):
                        logger.warning(f"[config] cameras.{cid} 应为 dict，忽略: {spec!r}")
                        continue
                    merged.setdefault(cid, {}).update(spec)
                value = merged
            if key in _PATH_FIELDS and isinstance(value, str) and not Path(value).is_absolute():
                value = str(base_dir / value)
            setattr(cfg, key, value)

        if legacy_head_overrides:
            head_spec = dict(cfg.cameras.get("head", {}))
            head_spec.update(legacy_head_overrides)
            cfg.cameras["head"] = head_spec

        logger.debug(f"[config] 已从 {yaml_path} 加载配置")
    else:
        logger.debug(f"[config] 配置文件不存在，使用内置默认值: {yaml_path}")

    # 敏感字段始终从环境变量读取（覆盖 YAML 或 dataclass 默认值）
    cfg.iflytek_iat_app_id = _read_env("XFYUN_IAT_APPID", "XFYUN_APPID")
    cfg.iflytek_iat_api_key = _read_env("XFYUN_IAT_API_KEY", "XFYUN_API_KEY")
    cfg.iflytek_iat_api_secret = _read_env("XFYUN_IAT_API_SECRET", "XFYUN_API_SECRET")
    cfg.iflytek_tts_app_id = _read_env("XFYUN_TTS_APPID", "XFYUN_APPID")
    cfg.iflytek_tts_api_key = _read_env("XFYUN_TTS_API_KEY", "XFYUN_API_KEY")
    cfg.iflytek_tts_api_secret = _read_env("XFYUN_TTS_API_SECRET", "XFYUN_API_SECRET")
    cfg.llm_api_key = _read_env("LLM_API_KEY")
    cfg.vlm_api_key = _read_env("VLM_API_KEY", "LLM_API_KEY")

    return cfg


def save_config(config: RobotConfig, path: Path | str | None = None) -> None:
    """将配置持久化到 YAML 文件（敏感字段不写入）。

    Args:
        config: 要保存的 RobotConfig 实例。
        path: 目标 YAML 文件路径，默认为 CONFIG_YAML_PATH。
    """
    yaml_path = Path(path) if path is not None else CONFIG_YAML_PATH
    raw = dataclasses.asdict(config)
    safe = {k: v for k, v in raw.items() if k not in _SECRET_FIELDS}
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(safe, f, allow_unicode=True, default_flow_style=False, sort_keys=True)
    logger.debug(f"[config] 配置已保存到 {yaml_path}")


# 全局默认配置实例（从 config.yaml 加载，文件不存在时使用内置默认值）
default_config = load_config()
