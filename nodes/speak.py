"""语音合成播放节点"""

import time

import sounddevice as sd
import py_trees
from py_trees.behaviour import Behaviour
from py_trees.common import Status


class SpeakResponse(Behaviour):
    """
    非阻塞 TTS 播放。

    initialise(): 生成音频并启动播放 (不阻塞)
    update():     轮询播放状态，播放中返回 RUNNING，播放完返回 SUCCESS
    terminate():  被打断时立即 sd.stop() 停止播放

    配合 Parallel(SuccessOnOne) 实现: TTS 播放期间 InterruptMonitor
    可以并行 tick，检测到用户说话则 Parallel 终止，触发 terminate() 停播。
    """

    def __init__(self, name: str, engine):
        super().__init__(name)
        self.engine = engine
        self.is_playing = False
        self.play_start_time = 0.0
        self.play_duration = 0.0

        self.blackboard = self.attach_blackboard_client(
            name="SpeakResponse", namespace="dialog"
        )
        self.blackboard.register_key(
            key="response_text", access=py_trees.common.Access.READ
        )
        self.blackboard.register_key(
            key="is_speaking", access=py_trees.common.Access.WRITE
        )
        self.blackboard.register_key(
            key="last_activity_time", access=py_trees.common.Access.WRITE
        )

    def initialise(self):
        text = getattr(self.blackboard, "response_text", "")
        if not text:
            self.is_playing = False
            return

        self.logger.info(f"机器人说: {text}")
        samples, sample_rate = self.engine.generate_speech(text)

        # 非阻塞播放
        sd.play(samples, samplerate=sample_rate)
        self.is_playing = True
        self.play_start_time = time.time()
        self.play_duration = len(samples) / sample_rate
        self.blackboard.is_speaking = True

        # 清空监控队列，避免播放前积压的旧数据触发 VAD
        self.engine.clear_monitor_queue()

    def update(self):
        if not self.is_playing:
            self._finish()
            return Status.SUCCESS

        # 通过时间判断播放是否完毕
        elapsed = time.time() - self.play_start_time
        if elapsed >= self.play_duration:
            self._finish()
            return Status.SUCCESS

        return Status.RUNNING

    def terminate(self, new_status):
        """被打断或正常结束时，确保停止播放并重置标志"""
        if self.is_playing:
            sd.stop()
            self.is_playing = False
        try:
            self.blackboard.is_speaking = False
        except Exception:
            pass

    def _finish(self):
        """播放结束的清理"""
        sd.stop()
        self.is_playing = False
        self.blackboard.is_speaking = False
        self.blackboard.last_activity_time = time.time()


class WakeupResponse(Behaviour):
    """
    唤醒成功后的简短提示音 (阻塞式)。

    播放一句简短的 "我在，请说" 然后 SUCCESS。
    因为是极短的提示音 (~1 秒)，阻塞不影响体验。
    """

    def __init__(self, name: str, engine, config):
        super().__init__(name)
        self.engine = engine
        self.config = config

    def update(self):
        text = self.config.tts_responses.get("wakeup", "我在，请说。")
        self.engine.speak_blocking(text)
        return Status.SUCCESS
