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
        self.stream = None

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
            key="speak_start_time", access=py_trees.common.Access.WRITE
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
        self.blackboard.is_speaking = True
        self.blackboard.speak_start_time = time.time()
        # 改为阻塞式播放，确保语音完整播放
        self.engine.speak_blocking(text)
        self.blackboard.is_speaking = False
        self.blackboard.speak_start_time = 0.0

    def update(self):
        # 阻塞式播放在 initialise 中已完成
        self._finish()
        return Status.SUCCESS

    def terminate(self, new_status):
        """被打断或正常结束时，确保停止播放并重置标志"""
        if self.is_playing:
            sd.stop()
            self.is_playing = False
            self.stream = None
        try:
            self.blackboard.is_speaking = False
            self.blackboard.speak_start_time = 0.0
        except Exception:
            pass

    def _finish(self):
        """播放结束的清理"""
        sd.stop()
        self.is_playing = False
        self.stream = None
        self.blackboard.is_speaking = False
        self.blackboard.speak_start_time = 0.0
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
