"""相机动作节点 - 拍照 & 录制视频"""

from __future__ import annotations

import logging
import platform
import time
from datetime import datetime
from pathlib import Path

import py_trees
from py_trees.behaviour import Behaviour
from py_trees.common import Status

from config import RobotConfig

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

logger = logging.getLogger(__name__)


# ============================================================================
# 内部工具函数
# ============================================================================

def _preferred_backend():
    """根据操作系统返回最合适的 VideoCapture 后端。"""
    if cv2 is None:
        return None
    system = platform.system()
    if system == "Windows":
        return cv2.CAP_DSHOW
    if system == "Linux":
        return cv2.CAP_V4L2
    return cv2.CAP_ANY


def _open_camera(camera_index: int, width: int, height: int):
    """
    打开相机并配置分辨率。

    Returns:
        cv2.VideoCapture | None: 成功返回 capture 对象，失败返回 None。
    """
    backend = _preferred_backend()
    cap = cv2.VideoCapture(camera_index, backend)
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def _warmup_and_grab(cap, warmup_frames: int = 30):
    """
    跳过前几帧(曝光预热)，返回稳定帧。

    Returns:
        numpy.ndarray | None
    """
    frame = None
    for _ in range(warmup_frames):
        ok, frame = cap.read()
    if frame is not None:
        return frame
    ok, frame = cap.read()
    return frame if ok else None


def _ensure_save_dir(save_dir: str) -> Path:
    """确保保存目录存在并返回 Path 对象。"""
    p = Path(save_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _timestamp() -> str:
    """生成文件名用时间戳: 20260210_181530"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# ============================================================================
# 独立执行函数 (供 Behaviour 节点和 planner tool 共同调用)
# ============================================================================

def execute_take_photo(config: RobotConfig) -> str:
    """拍照核心逻辑。成功返回结果描述，失败抛出 RuntimeError。"""
    if cv2 is None:
        raise RuntimeError("相机依赖缺失，请先安装 opencv-python。")

    cap = _open_camera(config.camera_index, config.camera_width, config.camera_height)
    if cap is None:
        raise RuntimeError("相机打开失败，请检查设备连接。")

    try:
        frame = _warmup_and_grab(cap)
        if frame is None:
            raise RuntimeError("相机无画面输出，请稍后再试。")

        save_dir = _ensure_save_dir(config.camera_save_dir)
        filename = f"photo_{_timestamp()}.jpg"
        filepath = save_dir / filename
        cv2.imwrite(str(filepath), frame)

        logger.info("照片已保存: %s", filepath)
        return "拍照成功，照片已保存。"
    finally:
        cap.release()


def execute_record_video(config: RobotConfig, duration: float | None = None) -> str:
    """录制视频核心逻辑。成功返回结果描述，失败抛出 RuntimeError。"""
    if cv2 is None:
        raise RuntimeError("相机依赖缺失，请先安装 opencv-python。")

    cap = _open_camera(config.camera_index, config.camera_width, config.camera_height)
    if cap is None:
        raise RuntimeError("相机打开失败，请检查设备连接。")

    if duration is None:
        duration = config.camera_record_seconds

    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            fps = config.camera_record_fps

        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        save_dir = _ensure_save_dir(config.camera_save_dir)
        filename = f"video_{_timestamp()}.mp4"
        filepath = save_dir / filename

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(filepath), fourcc, fps, (w, h))

        if not writer.isOpened():
            raise RuntimeError("视频录制初始化失败。")

        logger.info("开始录制: %.0fs, %dx%d@%.0ffps", duration, w, h, fps)

        for _ in range(30):
            cap.read()

        start = time.monotonic()
        while time.monotonic() - start < duration:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            writer.write(frame)

        writer.release()
        elapsed = time.monotonic() - start

        logger.info("视频已保存: %s (%.1fs)", filepath, elapsed)
        return f"视频录制完成，共 {elapsed:.0f} 秒，已保存。"
    finally:
        cap.release()


# ============================================================================
# 拍照动作 (行为树节点)
# ============================================================================

class TakePhotoAction(Behaviour):
    """
    拍照并保存到本地。

    intent == "take_photo" 时执行，否则返回 FAILURE。
    """

    def __init__(self, name: str, config: RobotConfig):
        super().__init__(name)
        self._config = config

        self.blackboard = self.attach_blackboard_client(
            name="TakePhotoAction", namespace="dialog"
        )
        self.blackboard.register_key(
            key="intent", access=py_trees.common.Access.READ
        )
        self.blackboard.register_key(
            key="response_text", access=py_trees.common.Access.WRITE
        )

    def update(self):
        if self.blackboard.intent != "take_photo":
            return Status.FAILURE

        self.logger.info("执行: 拍照")
        try:
            self.blackboard.response_text = execute_take_photo(self._config)
            return Status.SUCCESS
        except RuntimeError as e:
            self.logger.error(str(e))
            self.blackboard.response_text = str(e)
            return Status.FAILURE


# ============================================================================
# 录制视频动作 (行为树节点)
# ============================================================================

class RecordVideoAction(Behaviour):
    """
    录制视频并保存到本地。

    intent == "record_video" 时执行，否则返回 FAILURE。
    录制时长由 config.camera_record_seconds 控制。
    """

    def __init__(self, name: str, config: RobotConfig):
        super().__init__(name)
        self._config = config

        self.blackboard = self.attach_blackboard_client(
            name="RecordVideoAction", namespace="dialog"
        )
        self.blackboard.register_key(
            key="intent", access=py_trees.common.Access.READ
        )
        self.blackboard.register_key(
            key="response_text", access=py_trees.common.Access.WRITE
        )

    def update(self):
        if self.blackboard.intent != "record_video":
            return Status.FAILURE

        self.logger.info("执行: 录制视频")
        try:
            self.blackboard.response_text = execute_record_video(self._config)
            return Status.SUCCESS
        except RuntimeError as e:
            self.logger.error(str(e))
            self.blackboard.response_text = str(e)
            return Status.FAILURE
