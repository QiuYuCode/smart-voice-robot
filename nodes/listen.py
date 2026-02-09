"""语音指令监听节点"""

import time

import numpy as np
import py_trees
from py_trees.behaviour import Behaviour
from py_trees.common import Status

from config import SAMPLE_RATE


class ListenCommand(Behaviour):
    """
    监听用户语音指令 (流式 ASR)。

    使用 sherpa_onnx OnlineRecognizer 流式识别。
    检测到端点 (endpoint) 且有文本时返回 SUCCESS，
    将识别结果写入 blackboard.user_command。
    """

    def __init__(self, name: str, engine):
        super().__init__(name)
        self.engine = engine
        self.asr_stream = None

        self.blackboard = self.attach_blackboard_client(
            name="ListenCommand", namespace="dialog"
        )
        self.blackboard.register_key(
            key="user_command", access=py_trees.common.Access.WRITE
        )
        self.blackboard.register_key(
            key="last_activity_time", access=py_trees.common.Access.WRITE
        )

    def initialise(self):
        self.logger.info("正在聆听...")
        self.asr_stream = self.engine.asr.create_stream()
        # 清空对话队列，避免处理旧数据
        self.engine.clear_dialog_queue()
        self.blackboard.last_activity_time = time.time()

    def update(self):
        has_voice = False

        while not self.engine.dialog_audio_queue.empty():
            data = self.engine.dialog_audio_queue.get()
            samples = np.frombuffer(data, dtype=np.float32)
            self.asr_stream.accept_waveform(SAMPLE_RATE, samples)
            has_voice = True

        if has_voice:
            while self.engine.asr.is_ready(self.asr_stream):
                self.engine.asr.decode_stream(self.asr_stream)

            text = self.engine.asr.get_result(self.asr_stream).strip()
            is_endpoint = self.engine.asr.is_endpoint(self.asr_stream)

            if is_endpoint and len(text) > 0:
                self.logger.info(f"识别结果: {text}")
                self.blackboard.user_command = text
                self.blackboard.last_activity_time = time.time()
                return Status.SUCCESS

        return Status.RUNNING

    def terminate(self, new_status):
        self.asr_stream = None
