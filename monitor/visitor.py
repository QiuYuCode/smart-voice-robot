"""行为树状态捕获访问者"""
from __future__ import annotations

import queue
import time
from typing import Any

import py_trees
from loguru import logger


class StateCapturingVisitor(py_trees.visitors.VisitorBase):
    """在每次 tick 后，将完整树快照写入 queue 供监控服务消费。

    每次 tick 后采样一次，通过限速（5fps）避免 WebSocket 过载。
    入队后立即调用 monitor.notify_new_state() 唤醒 WebSocket handler，
    消除轮询引入的额外延迟。
    conversation_log 由外部（SpeakResponse 节点）直接追加。
    """

    def __init__(
        self,
        state_queue: queue.Queue,
        conversation_log: list[dict],
        root_node: py_trees.behaviour.Behaviour,
        monitor=None,
    ) -> None:
        super().__init__(full=True)
        self.state_queue = state_queue
        self.conversation_log = conversation_log
        self._root_node = root_node
        self._monitor = monitor        # MonitorServer 实例，用于即时唤醒 WebSocket handler
        self._tick_count = 0
        self._last_push_time = 0.0

    def finalise(self) -> None:
        self._tick_count += 1

        # 限速：最多 5fps
        now = time.time()
        if now - self._last_push_time < 0.2:
            return
        self._last_push_time = now

        try:
            payload = {
                "tick": self._tick_count,
                "tree": self._capture_node(self._root_node),
                "blackboard": self._capture_blackboard(),
                "conversation": list(self.conversation_log[-30:]),
                "timestamp": now,
            }
            # 队列满时，丢掉最旧帧再插入新帧，不阻塞主线程
            try:
                self.state_queue.put_nowait(payload)
            except queue.Full:
                try:
                    self.state_queue.get_nowait()
                    self.state_queue.put_nowait(payload)
                except queue.Empty:
                    pass

            # 立即唤醒 WebSocket handler，消除轮询延迟
            if self._monitor is not None:
                self._monitor.notify_new_state()

        except Exception as exc:
            logger.warning(f"[Monitor] 捕获树状态失败: {exc}")

    # ------------------------------------------------------------------
    # 私有方法
    # ------------------------------------------------------------------

    def _capture_node(self, node: py_trees.behaviour.Behaviour) -> dict:
        """递归捕获节点状态"""
        return {
            "id": str(node.id),
            "name": node.name,
            "type": type(node).__name__,
            "status": node.status.name,
            "children": [self._capture_node(c) for c in node.children],
        }

    def _capture_blackboard(self) -> dict:
        """读取黑板全部数据，序列化为 JSON 安全格式"""
        result = {}
        try:
            for k, v in py_trees.blackboard.Blackboard.storage.items():
                try:
                    result[str(k)] = self._to_json_safe(v)
                except Exception:
                    result[str(k)] = "<not serializable>"
        except Exception as exc:
            logger.warning(f"[Monitor] 黑板读取失败: {exc}")
        return result

    @staticmethod
    def _to_json_safe(value: Any) -> Any:
        """将任意值转换为 JSON 可序列化类型"""
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, list):
            return [StateCapturingVisitor._to_json_safe(v) for v in value]
        if isinstance(value, dict):
            return {
                str(k): StateCapturingVisitor._to_json_safe(v)
                for k, v in value.items()
            }
        return str(value)
