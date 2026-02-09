"""打断监控节点"""

import time

import numpy as np
import py_trees
from py_trees.behaviour import Behaviour
from py_trees.common import Status

from config import SAMPLE_RATE, RobotConfig


class InterruptMonitor(Behaviour):
    """
    打断监控器，与 DialogLoop 在 Parallel(SuccessOnOne) 中并行运行。

    检测两种打断条件:
      1. VAD: TTS 播放期间 is_speech_detected() 检测到用户说话
      2. Timeout: 超过 dialog_timeout 无活动

    任一条件满足返回 SUCCESS，触发 Parallel 终止整个 ActiveState。
    """

    def __init__(self, name: str, engine, config: RobotConfig):
        super().__init__(name)
        self.engine = engine
        self.config = config

        self.blackboard = self.attach_blackboard_client(
            name="InterruptMonitor", namespace="dialog"
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
        self.blackboard.register_key(
            key="interrupted", access=py_trees.common.Access.WRITE
        )

    def initialise(self):
        self.blackboard.interrupted = False
        # 初始化 is_speaking，避免首次进入时 KeyError
        self.blackboard.is_speaking = False
        self.blackboard.speak_start_time = 0.0
        # 确保 last_activity_time 存在，避免首次进入时 KeyError
        self.blackboard.last_activity_time = time.time()
        # 重置 VAD 状态
        self.engine.vad.reset()
        self.engine.clear_monitor_queue()

    def update(self):
        # --- 条件 1: 超时检测 ---
        last_activity = self.blackboard.last_activity_time
        if time.time() - last_activity > self.config.dialog_timeout:
            self.logger.info(
                f"对话超时 ({self.config.dialog_timeout}s)，回到待机"
            )
            self.blackboard.interrupted = True
            return Status.SUCCESS

        # --- 条件 2: VAD 检测 (仅在 TTS 播放期间) ---
        is_speaking = getattr(self.blackboard, "is_speaking", False)

        if is_speaking:
            speak_start_time = getattr(self.blackboard, "speak_start_time", 0.0)
            if time.time() - speak_start_time < self.config.interrupt_min_speech_seconds:
                # TTS 刚开始播放，忽略短暂的回声触发
                return Status.RUNNING
            # 将监控队列中的音频喂给 VAD
            while not self.engine.monitor_audio_queue.empty():
                data = self.engine.monitor_audio_queue.get()
                samples = np.frombuffer(data, dtype=np.float32)
                self.engine.vad.accept_waveform(samples)

            # is_speech_detected() 检测当前是否有语音活动 (实时，无需等完整段落)
            if self.engine.vad.is_speech_detected():
                self.logger.info("检测到用户说话，打断 TTS 播放")
                self.blackboard.interrupted = True
                # 清空已检测到的片段
                while not self.engine.vad.empty():
                    self.engine.vad.pop()
                self.engine.vad.reset()
                return Status.SUCCESS
        else:
            # 非播放期间，丢弃监控队列数据防止积压
            self.engine.clear_monitor_queue()

        return Status.RUNNING

    def terminate(self, new_status):
        self.engine.vad.reset()
