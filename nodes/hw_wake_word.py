"""硬件唤醒节点 (RK3328 降噪板)

DEPRECATED: RK3328 硬件唤醒已弃用，本模块不再维护。
"""

import queue

import py_trees
from py_trees.behaviour import Behaviour
from py_trees.common import Status


class HardwareWakeWord(Behaviour):
    """
    等待 RK3328 降噪板的硬件唤醒事件。

    通过 engine.rk3328_driver.wake_event_queue 非阻塞轮询，
    检测到唤醒事件后返回 SUCCESS。
    唤醒信息（波束号、角度、唤醒词）写入 blackboard 供后续节点使用。
    """

    def __init__(self, name: str, engine):
        super().__init__(name)
        self.engine = engine

        self.blackboard = self.attach_blackboard_client(
            name="HardwareWakeWord", namespace="wake"
        )
        self.blackboard.register_key(
            key="beam", access=py_trees.common.Access.WRITE
        )
        self.blackboard.register_key(
            key="angle", access=py_trees.common.Access.WRITE
        )
        self.blackboard.register_key(
            key="keyword", access=py_trees.common.Access.WRITE
        )

    def initialise(self):
        self.logger.info("待机中，等待硬件唤醒...")
        # 清空旧的唤醒事件，避免处理过期数据
        self.engine.rk3328_driver.clear_wake_events()
        # 清空音频队列，避免 ASR 处理旧数据
        self.engine.clear_dialog_queue()

    def update(self):
        try:
            event = self.engine.rk3328_driver.wake_event_queue.get_nowait()
        except queue.Empty:
            return Status.RUNNING

        self.logger.info(
            f"硬件唤醒! keyword={event.keyword}, "
            f"beam={event.beam}, angle={event.angle}"
        )
        # 写入 blackboard，供导航等后续节点使用
        self.blackboard.beam = event.beam
        self.blackboard.angle = event.angle
        self.blackboard.keyword = event.keyword
        return Status.SUCCESS

    def terminate(self, new_status):
        pass
