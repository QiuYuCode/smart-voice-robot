"""
语音引擎模块

管理 KWS / ASR / TTS 模型初始化和音频流。
提供独立的音频队列：
  - dialog_audio_queue: 供 ListenCommand (ASR) 消费
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
    SAMPLE_RATE,
    CHUNK_SIZE,
    RobotConfig,
)


class VoiceEngine:
    """语音引擎：管理所有语音模型和音频流"""

    def __init__(self, config: RobotConfig):
        self.config = config
        print("正在加载语音模型 (CPU)...")

        # 音频队列
        self.dialog_audio_queue: queue.Queue = queue.Queue()

        self.is_running = True
        self.mic_stream = None

        # 1. 唤醒检测（按模式选择）
        self.kws = None
        self.rk3328_driver = None

        if config.wake_mode == "software":
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
        elif config.wake_mode == "hardware":
            from rk3328 import RK3328Driver
            self.rk3328_driver = RK3328Driver(
                port=config.hw_serial_port,
                baudrate=config.hw_serial_baudrate,
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

        # 3. TTS (语音合成)
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
        """麦克风数据回调 - 写入对话队列"""
        if status:
            print(status, file=sys.stderr)
        raw_bytes = bytes(indata)
        self.dialog_audio_queue.put(raw_bytes)

    def start(self):
        """启动麦克风音频流和硬件驱动（如有）"""
        # 启动 RK3328 驱动（需在麦克风之前，确保握手响应及时）
        if self.rk3328_driver is not None:
            self.rk3328_driver.start()

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
        """停止音频流和硬件驱动"""
        self.is_running = False
        if self.mic_stream:
            self.mic_stream.stop()
            self.mic_stream.close()
        if self.rk3328_driver is not None:
            self.rk3328_driver.stop()

    # ------------------------------------------------------------------
    # TTS
    # ------------------------------------------------------------------

    def _split_tts_text(self, text: str) -> list[str]:
        cleaned = " ".join(text.strip().split())
        if not cleaned:
            return []
        max_len = self.config.tts_max_chars_per_chunk
        if len(cleaned) <= max_len:
            return [cleaned]

        # 先按常见句子分隔符切分
        separators = "。！？.!?;；\n"
        sentences: list[str] = []
        buf = []
        for ch in cleaned:
            buf.append(ch)
            if ch in separators:
                sentence = "".join(buf).strip()
                if sentence:
                    sentences.append(sentence)
                buf = []
        if buf:
            sentence = "".join(buf).strip()
            if sentence:
                sentences.append(sentence)

        # 进一步按最大长度拆分
        chunks: list[str] = []
        for sentence in sentences:
            if len(sentence) <= max_len:
                chunks.append(sentence)
            else:
                start = 0
                while start < len(sentence):
                    chunks.append(sentence[start : start + max_len])
                    start += max_len
        return chunks

    def generate_speech(self, text: str):
        """生成 TTS 音频 (不播放)，返回 (samples, sample_rate)"""
        chunks = self._split_tts_text(text)
        if not chunks:
            return np.array([], dtype=np.float32), SAMPLE_RATE

        combined = []
        sample_rate = None
        pause_samples = None

        for chunk in chunks:
            audio = self.tts.generate(
                chunk,
                sid=self.config.tts_speaker_id,
                speed=self.config.tts_speed,
            )
            if sample_rate is None:
                sample_rate = audio.sample_rate
                pause_len = int(sample_rate * self.config.tts_pause_seconds)
                pause_samples = np.zeros(pause_len, dtype=np.float32)
            combined.append(np.asarray(audio.samples, dtype=np.float32))
            combined.append(pause_samples)

        if combined and pause_samples is not None:
            combined = combined[:-1]
        if combined:
            return np.concatenate(combined), sample_rate
        return np.array([], dtype=np.float32), SAMPLE_RATE

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
        """兼容旧接口：当前未使用监控队列"""
        return

    def clear_all_queues(self):
        """清空所有音频队列"""
        self.clear_dialog_queue()
