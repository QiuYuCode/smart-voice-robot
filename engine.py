"""
语音引擎模块

管理 KWS / ASR / TTS 模型初始化和音频流。
提供独立的音频队列：
  - dialog_audio_queue: 供 ListenCommand (ASR) 消费
"""

import base64
import hashlib
import hmac
import json
import sys
import queue
from email.utils import formatdate
from urllib.parse import urlencode

import numpy as np
import sounddevice as sd
import sherpa_onnx
import websocket  # type: ignore[import-not-found]

from config import (
    ASR_DIR,
    KWS_DIR,
    TTS_DIR,
    VAD_DIR,
    SAMPLE_RATE,
    CHUNK_SIZE,
    RobotConfig,
)


class VoiceEngine:
    """语音引擎：管理所有语音模型和音频流"""

    def __init__(self, config: RobotConfig):
        self.config = config
        print(f"正在加载语音模型 ({config.onnx_provider.upper()})...")

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
                provider=config.onnx_provider,
            )
        elif config.wake_mode == "hardware":
            from rk3328 import RK3328Driver
            self.rk3328_driver = RK3328Driver(
                port=config.hw_serial_port,
                baudrate=config.hw_serial_baudrate,
            )

        # 2. ASR (流式语音识别)
        self.asr = None
        if config.asr_backend == "local" or config.cloud_asr_fallback_to_local:
            self.asr = sherpa_onnx.OnlineRecognizer.from_transducer(
                tokens=f"{ASR_DIR}/tokens.txt",
                encoder=f"{ASR_DIR}/encoder-epoch-99-avg-1.onnx",
                decoder=f"{ASR_DIR}/decoder-epoch-99-avg-1.onnx",
                joiner=f"{ASR_DIR}/joiner-epoch-99-avg-1.onnx",
                num_threads=config.num_threads,
                sample_rate=SAMPLE_RATE,
                enable_endpoint_detection=True,
                provider=config.onnx_provider,
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
                    provider=config.onnx_provider,
                )
            )
        )

        # 4. VAD (语音活动检测 - Silero VAD)
        vad_config = sherpa_onnx.VadModelConfig()
        vad_config.silero_vad.model = str(VAD_DIR)
        vad_config.silero_vad.threshold = config.vad_threshold
        vad_config.silero_vad.min_silence_duration = config.vad_min_silence_duration
        vad_config.silero_vad.min_speech_duration = config.vad_min_speech_duration
        vad_config.sample_rate = SAMPLE_RATE

        self.vad = sherpa_onnx.VoiceActivityDetector(
            vad_config, buffer_size_in_seconds=30
        )
        self.vad_window_size = vad_config.silero_vad.window_size

        print("所有模型加载完成。")

    def _configure_audio_devices(self):
        """
        根据配置中的设备名提示词自动选择输入/输出设备。
        如果找不到匹配项，则回退到系统默认设备。
        """
        try:
            devices = sd.query_devices()
        except Exception as e:
            print(f"[Audio] 查询设备失败，使用系统默认: {e}")
            return

        # 在 Linux + ALSA 后端下，sounddevice 常见到的稳定入口是 "pulse"。
        # 优先绑定到 pulse，由 PulseAudio 负责路由到真实 USB 设备。
        pulse_idx = None
        for idx, dev in enumerate(devices):
            name_l = str(dev.get("name", "")).lower().strip()
            max_in = int(dev.get("max_input_channels", 0) or 0)
            max_out = int(dev.get("max_output_channels", 0) or 0)
            if name_l == "pulse" and max_in > 0 and max_out > 0:
                pulse_idx = idx
                break

        if pulse_idx is not None:
            sd.default.device = (pulse_idx, pulse_idx)
            try:
                pulse_name = sd.query_devices(pulse_idx)["name"]
                print(f"[Audio] 输入设备: {pulse_name}")
                print(f"[Audio] 输出设备: {pulse_name}")
            except Exception:
                pass
            return

        input_hint = (self.config.input_device_hint or "").strip().lower()
        output_hint = (self.config.output_device_hint or "").strip().lower()

        selected_input = None
        selected_output = None

        for idx, dev in enumerate(devices):
            name = str(dev.get("name", ""))
            name_l = name.lower()
            max_in = int(dev.get("max_input_channels", 0) or 0)
            max_out = int(dev.get("max_output_channels", 0) or 0)

            if selected_input is None and input_hint and input_hint in name_l and max_in > 0:
                selected_input = idx
            if selected_output is None and output_hint and output_hint in name_l and max_out > 0:
                selected_output = idx

        # 未命中 hint 时，选择首个包含 usb 的输入/输出设备作为兜底
        if selected_input is None:
            for idx, dev in enumerate(devices):
                name_l = str(dev.get("name", "")).lower()
                max_in = int(dev.get("max_input_channels", 0) or 0)
                if "usb" in name_l and max_in > 0:
                    selected_input = idx
                    break
        if selected_output is None:
            for idx, dev in enumerate(devices):
                name_l = str(dev.get("name", "")).lower()
                max_out = int(dev.get("max_output_channels", 0) or 0)
                if "usb" in name_l and max_out > 0:
                    selected_output = idx
                    break

        current_in, current_out = sd.default.device
        sd.default.device = (
            selected_input if selected_input is not None else current_in,
            selected_output if selected_output is not None else current_out,
        )

        try:
            in_name = sd.query_devices(sd.default.device[0])["name"]
            out_name = sd.query_devices(sd.default.device[1])["name"]
            print(f"[Audio] 输入设备: {in_name}")
            print(f"[Audio] 输出设备: {out_name}")
        except Exception:
            pass

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
        self._configure_audio_devices()

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

    # 句子终止符 → 长停顿；从句/逗号 → 短停顿
    _SENTENCE_END = set("。！？.!?\n")
    _CLAUSE_SEP = set(",，;；:：、—")

    def _split_tts_segments(self, text: str) -> list[tuple[str, str]]:
        """
        将文本按标点拆分为 (片段, 停顿类型) 列表。
        停顿类型: "sentence" | "clause" | "none"
        """
        cleaned = " ".join(text.strip().split())
        if not cleaned:
            return []

        max_len = self.config.tts_max_chars_per_chunk
        segments: list[tuple[str, str]] = []
        buf: list[str] = []

        for ch in cleaned:
            buf.append(ch)
            if ch in self._SENTENCE_END:
                seg = "".join(buf).strip()
                if seg:
                    segments.append((seg, "sentence"))
                buf = []
            elif ch in self._CLAUSE_SEP:
                seg = "".join(buf).strip()
                if seg:
                    segments.append((seg, "clause"))
                buf = []

        if buf:
            seg = "".join(buf).strip()
            if seg:
                segments.append((seg, "none"))

        # 对超长片段做二次拆分
        result: list[tuple[str, str]] = []
        for seg_text, pause_type in segments:
            if len(seg_text) <= max_len:
                result.append((seg_text, pause_type))
            else:
                start = 0
                while start < len(seg_text):
                    chunk = seg_text[start : start + max_len]
                    start += max_len
                    p = pause_type if start >= len(seg_text) else "clause"
                    result.append((chunk, p))
        return result

    def _split_text_by_bytes(self, text: str) -> list[str]:
        """
        按 UTF-8 bytes 长度切分文本，满足讯飞单次请求上限。
        """
        encoding = self.config.iflytek_tts_request_text_encoding
        max_bytes = max(1, self.config.iflytek_tts_max_bytes - 1)
        cleaned = " ".join(text.strip().split())
        if not cleaned:
            return []

        chunks: list[str] = []
        current_chars: list[str] = []
        current_size = 0
        for ch in cleaned:
            b = ch.encode(encoding, errors="ignore")
            if not b:
                continue
            if current_chars and current_size + len(b) > max_bytes:
                chunks.append("".join(current_chars))
                current_chars = [ch]
                current_size = len(b)
            else:
                current_chars.append(ch)
                current_size += len(b)
        if current_chars:
            chunks.append("".join(current_chars))
        return chunks

    @staticmethod
    def _pcm16_bytes_to_float32(pcm_bytes: bytes) -> np.ndarray:
        if not pcm_bytes:
            return np.array([], dtype=np.float32)
        pcm = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
        return pcm / 32768.0

    @staticmethod
    def _float32_to_pcm16_bytes(samples: np.ndarray) -> bytes:
        clamped = np.clip(samples, -1.0, 1.0)
        pcm = (clamped * 32767.0).astype(np.int16)
        return pcm.tobytes()

    @staticmethod
    def _build_iflytek_ws_url(base_url: str, api_key: str, api_secret: str) -> str:
        # e.g. base_url = "wss://tts-api.xfyun.cn/v2/tts"
        host = base_url.split("//", 1)[1].split("/", 1)[0]
        path = "/" + base_url.split("//", 1)[1].split("/", 1)[1]
        date = formatdate(timeval=None, localtime=False, usegmt=True)
        signature_origin = f"host: {host}\ndate: {date}\nGET {path} HTTP/1.1"
        signature_sha = hmac.new(
            api_secret.encode("utf-8"),
            signature_origin.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        signature = base64.b64encode(signature_sha).decode("utf-8")
        authorization_origin = (
            f'api_key="{api_key}", algorithm="hmac-sha256", '
            f'headers="host date request-line", signature="{signature}"'
        )
        authorization = base64.b64encode(
            authorization_origin.encode("utf-8")
        ).decode("utf-8")
        query = urlencode({"host": host, "date": date, "authorization": authorization})
        return f"{base_url}?{query}"

    def _generate_local_tts(self, segments: list[tuple[str, str]]) -> tuple[np.ndarray, int]:
        combined: list[np.ndarray] = []
        sample_rate = None
        sentence_pause = None
        clause_pause = None

        for seg_text, pause_type in segments:
            audio = self.tts.generate(
                seg_text,
                sid=self.config.tts_speaker_id,
                speed=self.config.tts_speed,
            )
            if sample_rate is None:
                sample_rate = audio.sample_rate
                sentence_pause = np.zeros(
                    int(sample_rate * self.config.tts_sentence_pause), dtype=np.float32
                )
                clause_pause = np.zeros(
                    int(sample_rate * self.config.tts_clause_pause), dtype=np.float32
                )

            combined.append(np.asarray(audio.samples, dtype=np.float32))
            if pause_type == "sentence":
                combined.append(sentence_pause)
            elif pause_type == "clause":
                combined.append(clause_pause)

        if combined:
            return np.concatenate(combined), sample_rate
        return np.array([], dtype=np.float32), SAMPLE_RATE

    def _generate_iflytek_tts(self, text: str) -> tuple[np.ndarray, int]:
        cfg = self.config
        if not (cfg.iflytek_tts_app_id and cfg.iflytek_tts_api_key and cfg.iflytek_tts_api_secret):
            raise RuntimeError("讯飞 TTS 密钥缺失，请设置 XFYUN_TTS_APPID/API_KEY/API_SECRET")

        ws_url = self._build_iflytek_ws_url(
            "wss://tts-api.xfyun.cn/v2/tts",
            cfg.iflytek_tts_api_key,
            cfg.iflytek_tts_api_secret,
        )
        print("[TTS][Cloud] 握手: wss://tts-api.xfyun.cn/v2/tts")

        chunks = self._split_text_by_bytes(text)
        all_samples: list[np.ndarray] = []
        for chunk_text in chunks:
            text_bytes = chunk_text.encode(cfg.iflytek_tts_request_text_encoding)
            req = {
                "common": {"app_id": cfg.iflytek_tts_app_id},
                "business": {
                    "aue": cfg.iflytek_tts_aue,
                    "auf": cfg.iflytek_tts_auf,
                    "vcn": cfg.iflytek_tts_vcn,
                    "speed": int(np.clip(cfg.iflytek_tts_speed, 0, 100)),
                    "tte": cfg.iflytek_tts_tte,
                },
                "data": {
                    "status": 2,
                    "text": base64.b64encode(text_bytes).decode("utf-8"),
                },
            }
            ws = websocket.create_connection(ws_url, timeout=10)
            try:
                ws.send(json.dumps(req, ensure_ascii=False))
                frame_count = 0
                while True:
                    raw = ws.recv()
                    if not raw:
                        continue
                    frame_count += 1
                    resp = json.loads(raw)
                    code = int(resp.get("code", -1))
                    if code != 0:
                        sid = resp.get("sid", "")
                        msg = resp.get("message", "")
                        raise RuntimeError(f"讯飞TTS失败 code={code} sid={sid} msg={msg}")
                    data = resp.get("data")
                    if not data:
                        continue
                    audio_b64 = data.get("audio") or ""
                    if audio_b64:
                        pcm_bytes = base64.b64decode(audio_b64)
                        all_samples.append(self._pcm16_bytes_to_float32(pcm_bytes))
                    if int(data.get("status", 1)) == 2:
                        print(f"[TTS][Cloud] 分片完成: frames={frame_count}")
                        break
            finally:
                ws.close()

        if all_samples:
            return np.concatenate(all_samples), SAMPLE_RATE
        raise RuntimeError("讯飞 TTS 未返回有效音频")

    def generate_speech(self, text: str):
        """生成 TTS 音频 (不播放)，返回 (samples, sample_rate)"""
        segments = self._split_tts_segments(text)
        if not segments:
            return np.array([], dtype=np.float32), SAMPLE_RATE

        if self.config.tts_backend == "iflytek_cloud":
            try:
                return self._generate_iflytek_tts(text)
            except Exception as e:
                print(f"[TTS][Cloud] 失败: {e}")
                if not self.config.cloud_tts_fallback_to_local:
                    raise
                print("[TTS][Cloud] 回落到本地 TTS")
        return self._generate_local_tts(segments)

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
