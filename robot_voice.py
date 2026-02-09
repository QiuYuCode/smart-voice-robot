import sys
import time
import queue
import numpy as np
import sounddevice as sd
import sherpa_onnx
import py_trees
from py_trees.behaviour import Behaviour
from py_trees.common import Status

# ================= 配置区域 =================
# 音频采样率 (Sherpa 默认 16k)
SAMPLE_RATE = 16000
# 每一帧的采样点数 (0.1秒)
CHUNK_SIZE = int(SAMPLE_RATE * 0.1)

# 模型路径配置 (请确保路径与你下载的一致)
ASR_DIR = "/home/create/DataDisk/WorkSpace/models/voice_models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20"
KWS_DIR = "/home/create/DataDisk/WorkSpace/models/voice_models/sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01"
TTS_DIR = "/home/create/DataDisk/WorkSpace/models/voice_models/vits-zh-aishell3"

# ================= 核心引擎 =================
class VoiceEngine:
    def __init__(self):
        print("正在加载语音模型 (CPU)...")
        
        # 1. 初始化 KWS (唤醒)
        self.kws = sherpa_onnx.KeywordSpotter(
            tokens=f"{KWS_DIR}/tokens.txt",
            encoder=f"{KWS_DIR}/encoder-epoch-12-avg-2-chunk-16-left-64.onnx",
            decoder=f"{KWS_DIR}/decoder-epoch-12-avg-2-chunk-16-left-64.onnx",
            joiner=f"{KWS_DIR}/joiner-epoch-12-avg-2-chunk-16-left-64.onnx",
            keywords_file=f"{KWS_DIR}/keywords.txt",  # 默认唤醒词在文件里，如 "你好世界"
            num_threads=2,
            sample_rate=SAMPLE_RATE,
        )

        # 2. 初始化 ASR (识别)
        self.asr = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=f"{ASR_DIR}/tokens.txt",
            encoder=f"{ASR_DIR}/encoder-epoch-99-avg-1.onnx",
            decoder=f"{ASR_DIR}/decoder-epoch-99-avg-1.onnx",
            joiner=f"{ASR_DIR}/joiner-epoch-99-avg-1.onnx",
            num_threads=2,
            sample_rate=SAMPLE_RATE,
            enable_endpoint_detection=True,
        )

        # 3. 初始化 TTS (合成)
        self.tts = sherpa_onnx.OfflineTts(
            config=sherpa_onnx.OfflineTtsConfig(
                model=sherpa_onnx.OfflineTtsModelConfig(
                    vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                        model=f"{TTS_DIR}/vits-aishell3.onnx",
                        lexicon=f"{TTS_DIR}/lexicon.txt",
                        tokens=f"{TTS_DIR}/tokens.txt",
                    )
                )
            )
        )
        
        self.audio_queue = queue.Queue()
        self.is_running = True
        self.stream = None

    def audio_callback(self, indata, frames, time, status):
        """麦克风数据回调"""
        if status:
            print(status, file=sys.stderr)
        self.audio_queue.put(bytes(indata))

    def start(self):
        # 查找输入设备，Jetson 上可能需要指定 device 参数
        self.stream = sd.RawInputStream(
            samplerate=SAMPLE_RATE, 
            channels=1, 
            dtype='float32', 
            blocksize=CHUNK_SIZE,
            callback=self.audio_callback
        )
        self.stream.start()

    def stop(self):
        self.is_running = False
        if self.stream:
            self.stream.stop()
            self.stream.close()

    def speak(self, text):
        """TTS 播放"""
        print(f"🤖 机器人说: {text}")
        audio = self.tts.generate(text, sid=0, speed=1.0)
        # 简单播放，会阻塞直到播放完成
        sd.play(audio.samples, samplerate=audio.sample_rate)
        sd.wait()

# ================= 行为树节点 =================
class WaitForWakeWord(Behaviour):
    def __init__(self, name, engine):
        super().__init__(name)
        self.engine = engine
        self.kws_stream = self.engine.kws.create_stream()

    def update(self):
        # 检查音频队列
        while not self.engine.audio_queue.empty():
            data = self.engine.audio_queue.get()
            samples = np.frombuffer(data, dtype=np.float32)
            
            # 送入 KWS
            self.logger.debug(f"🔍 送入 KWS: {samples}")
            self.kws_stream.accept_waveform(SAMPLE_RATE, samples)
            while self.engine.kws.is_ready(self.kws_stream):
                self.engine.kws.decode_stream(self.kws_stream)
                keyword = self.engine.kws.get_result(self.kws_stream)
                
                self.logger.debug(f"🔍 KWS 关键词: {keyword}")
                if keyword:
                    self.logger.info(f"✨ 唤醒成功! 关键词: {keyword}")
                    self.engine.kws.reset_stream(self.kws_stream)
                    return Status.SUCCESS
        return Status.RUNNING

class ListenCommand(Behaviour):
    def __init__(self, name, engine):
        super().__init__(name)
        self.engine = engine
        self.asr_stream = None
        self.silence_counter = 0
        self.blackboard = self.attach_blackboard_client(
            name="ListenCommand", namespace="dialog"
        )
        self.blackboard.register_key(
            key="user_command", access=py_trees.common.Access.WRITE
        )

    def initialise(self):
        print("👂 正在聆听...")
        self.asr_stream = self.engine.asr.create_stream()
        self.silence_counter = 0
        # 清空之前的音频缓存，避免处理旧数据
        with self.engine.audio_queue.mutex:
             self.engine.audio_queue.queue.clear()

    def update(self):
        has_voice = False
        text = ""
        
        # 处理一小段音频
        while not self.engine.audio_queue.empty():
            data = self.engine.audio_queue.get()
            samples = np.frombuffer(data, dtype=np.float32)
            self.asr_stream.accept_waveform(SAMPLE_RATE, samples)
            has_voice = True

        if has_voice:
            while self.engine.asr.is_ready(self.asr_stream):
                self.engine.asr.decode_stream(self.asr_stream)
            
            text = self.engine.asr.get_result(self.asr_stream)
            
            # 简单的端点检测 (VAD) 逻辑：
            # 如果有文本且结果不再变化 (Sherpa 会自动处理一部分，这里简化)
            # 或者通过 endpoint 判断
            is_endpoint = self.engine.asr.is_endpoint(self.asr_stream)
            
            if is_endpoint and len(text) > 0:
                print(f"📝 识别结果: {text}")
                # 将结果写入黑板供其他节点使用
                self.blackboard.user_command = text
                return Status.SUCCESS
            
        return Status.RUNNING

class ExecuteCommand(Behaviour):
    def __init__(self, name, engine):
        super().__init__(name)
        self.engine = engine
        self.blackboard = self.attach_blackboard_client(
            name="ExecuteCommand", namespace="dialog"
        )
        self.blackboard.register_key(
            key="user_command", access=py_trees.common.Access.READ
        )

    def update(self):
        cmd = getattr(self.blackboard, "user_command", "")
        print(f"⚙️ 处理指令: {cmd}")
        
        # 简单的逻辑分支
        if "你好" in cmd:
            self.engine.speak("你好呀，我是你的机器人助手。")
        elif "名字" in cmd:
            self.engine.speak("我的名字是 Jetson。")
        elif "时间" in cmd:
            self.engine.speak("现在是工作时间。")
        else:
            self.engine.speak(f"我听到了：{cmd}，但是我还不会处理这个指令。")
            
        return Status.SUCCESS

# ================= 主程序 =================
def main():
    # 1. 初始化引擎
    engine = VoiceEngine()
    engine.start()

    # 2. 构建行为树
    # 逻辑：无限循环 [等待唤醒 -> 听指令 -> 执行]
    root = py_trees.composites.Sequence("MainSequence", memory=True)
    
    # 这里的 Sequence 会按顺序执行子节点
    # 为了让它循环，我们在外部 while 中 reset 或者使用 Selector/Decorator
    # 简单起见，我们直接在 Sequence 中放三个步骤，执行完一次后在 main loop 中重置
    
    root.add_children([
        WaitForWakeWord("WaitWake", engine),
        ListenCommand("Listen", engine),
        ExecuteCommand("Action", engine)
    ])

    tree = py_trees.trees.BehaviourTree(root)
    tree.setup(timeout=15)

    print("\n✅ 系统启动完毕！请对麦克风说: '小爱同学' (默认唤醒词)")

    try:
        while True:
            tree.tick()
            
            # 如果整个流程跑完了一遍 (SUCCESS)，重置状态以重新开始等待唤醒
            if root.status == Status.SUCCESS:
                print("--- 回合结束，重置 ---")
                root.stop(Status.INVALID)
                time.sleep(1) # 休息一下
            
            time.sleep(0.05) # 避免 CPU 占用过高
            
    except KeyboardInterrupt:
        print("\n停止中...")
        engine.stop()

if __name__ == "__main__":
    main()