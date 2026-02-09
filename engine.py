"""
语音引擎模块

管理 KWS / ASR / VAD / TTS 模型初始化和音频流。
提供两个独立的音频队列：
  - dialog_audio_queue: 供 ListenCommand (ASR) 消费
  - monitor_audio_queue: 供 InterruptMonitor (VAD) 消费
麦克风回调同时写入两个队列，互不干扰。
"""

import sys
import queue

import numpy as np
import sounddevice as sd
import sherpa_onnx

from config import (
    ASR_DIR,
    KWS_DIR,
    TTS_DIR,
    VAD_MODEL,
    SAMPLE_RATE,
    CHUNK_SIZE,
    RobotConfig,
)


class VoiceEngine:
    """语音引擎：管理所有语音模型和音频流"""

    def __init__(self, config: RobotConfig):
        self.config = config
        print("正在加载语音模型 (CPU)...")

        # 两个音频队列
        self.dialog_audio_queue: queue.Queue = queue.Queue()
        self.monitor_audio_queue: queue.Queue = queue.Queue()

        self.is_running = True
        self.mic_stream = None

        # 1. KWS (唤醒词检测)
        self.kws = sherpa_onnx.KeywordSpotter(
            tokens=f"{KWS_DIR}/tokens.txt",
            encoder=f"{KWS_DIR}/encoder-epoch-12-avg-2-chunk-16-left-64.onnx",
            decoder=f"{KWS_DIR}/decoder-epoch-12-avg-2-chunk-16-left-64.onnx",
            joiner=f"{KWS_DIR}/joiner-epoch-12-avg-2-chunk-16-left-64.onnx",
            keywords_file=config.kws_keywords_file,
            keywords_score=config.kws_keywords_score,
            keywords_threshold=config.kws_keywords_threshold,
            num_trailing_blanks=config.kws_num_trailing_blanks,
            num_threads=config.num_threads,
            sample_rate=SAMPLE_RATE,
        )

        # 2. ASR (流式语音识别)
        self.asr = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=f"{ASR_DIR}/tokens.txt",
            encoder=f"{ASR_DIR}/encoder-epoch-99-avg-1.onnx",
            decoder=f"{ASR_DIR}/decoder-epoch-99-avg-1.onnx",
            joiner=f"{ASR_DIR}/joiner-epoch-99-avg-1.onnx",
            num_threads=config.num_threads,
            sample_rate=SAMPLE_RATE,
            enable_endpoint_detection=True,
        )

        # 3. VAD (语音活动检测 - 用于 TTS 打断)
        vad_config = sherpa_onnx.VadModelConfig()
        vad_config.silero_vad.model = VAD_MODEL
        vad_config.silero_vad.threshold = config.vad_threshold
        vad_config.silero_vad.min_silence_duration = config.vad_min_silence_duration
        vad_config.silero_vad.min_speech_duration = config.vad_min_speech_duration
        vad_config.sample_rate = SAMPLE_RATE
        self.vad = sherpa_onnx.VoiceActivityDetector(
            vad_config, buffer_size_in_seconds=30
        )

        # 4. TTS (语音合成)
        self.tts = sherpa_onnx.OfflineTts(
            config=sherpa_onnx.OfflineTtsConfig(
                model=sherpa_onnx.OfflineTtsModelConfig(
                    vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                        model=f"{TTS_DIR}/vits-aishell3.onnx",
                        lexicon=f"{TTS_DIR}/lexicon.txt",
                        tokens=f"{TTS_DIR}/tokens.txt",
                    ),
                    num_threads=config.num_threads,
                )
            )
        )

        print("所有模型加载完成。")

    # ------------------------------------------------------------------
    # 音频流
    # ------------------------------------------------------------------

    def audio_callback(self, indata, frames, time_info, status):
        """麦克风数据回调 - 同时写入两个队列"""
        if status:
            print(status, file=sys.stderr)
        raw_bytes = bytes(indata)
        self.dialog_audio_queue.put(raw_bytes)
        self.monitor_audio_queue.put(raw_bytes)

    def start(self):
        """启动麦克风音频流"""
        self.mic_stream = sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=CHUNK_SIZE,
            callback=self.audio_callback,
        )
        self.mic_stream.start()
        print("麦克风已启动。")

    def stop(self):
        """停止音频流"""
        self.is_running = False
        if self.mic_stream:
            self.mic_stream.stop()
            self.mic_stream.close()

    # ------------------------------------------------------------------
    # TTS
    # ------------------------------------------------------------------

    def generate_speech(self, text: str):
        """生成 TTS 音频 (不播放)，返回 (samples, sample_rate)"""
        audio = self.tts.generate(
            text,
            sid=self.config.tts_speaker_id,
            speed=self.config.tts_speed,
        )
        return audio.samples, audio.sample_rate

    def speak_blocking(self, text: str):
        """阻塞式 TTS 播放 (用于简短提示音)"""
        print(f"[TTS] {text}")
        samples, sr = self.generate_speech(text)
        sd.play(samples, samplerate=sr)
        sd.wait()

    # ------------------------------------------------------------------
    # 队列管理
    # ------------------------------------------------------------------

    def clear_dialog_queue(self):
        """清空对话音频队列"""
        with self.dialog_audio_queue.mutex:
            self.dialog_audio_queue.queue.clear()

    def clear_monitor_queue(self):
        """清空监控音频队列"""
        with self.monitor_audio_queue.mutex:
            self.monitor_audio_queue.queue.clear()

    def clear_all_queues(self):
        """清空所有音频队列"""
        self.clear_dialog_queue()
        self.clear_monitor_queue()
