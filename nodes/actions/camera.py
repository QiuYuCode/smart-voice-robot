"""打开相机动作节点"""

import platform

import py_trees
from py_trees.behaviour import Behaviour
from py_trees.common import Status

try:
    import cv2
except ImportError:  # pragma: no cover - fallback when依赖 missing
    cv2 = None


def _preferred_backend():
    """根据操作系统返回最合适的 VideoCapture 后端。"""
    if cv2 is None:
        return None
    system = platform.system()
    if system == "Windows":
        return cv2.CAP_DSHOW
    if system == "Linux":
        return cv2.CAP_V4L2
    # macOS / 其他: 让 OpenCV 自动选择
    return cv2.CAP_ANY


class OpenCameraAction(Behaviour):
    """
    打开相机。

    当 intent == "open_camera" 时执行，否则返回 FAILURE
    让 Selector 继续尝试下一个 action。
    """

    def __init__(self, name: str):
        super().__init__(name)

        self.blackboard = self.attach_blackboard_client(
            name="OpenCameraAction", namespace="dialog"
        )
        self.blackboard.register_key(
            key="intent", access=py_trees.common.Access.READ
        )
        self.blackboard.register_key(
            key="response_text", access=py_trees.common.Access.WRITE
        )

    def update(self):
        if self.blackboard.intent != "open_camera":
            return Status.FAILURE

        self.logger.info("执行: 打开相机")

        if cv2 is None:
            self.logger.error("opencv-python 未安装，无法打开相机。")
            self.blackboard.response_text = "相机依赖缺失，请先安装 opencv-python。"
            return Status.FAILURE

        camera_index = 4
        target_width, target_height = 640, 480
        frames_to_skip = 2
        capture = None

        try:
            backend = _preferred_backend()
            capture = cv2.VideoCapture(camera_index, backend)

            if not capture.isOpened():
                self.logger.error("无法打开默认相机。")
                self.blackboard.response_text = "相机打开失败，请检查设备连接。"
                return Status.FAILURE

            capture.set(cv2.CAP_PROP_FRAME_WIDTH, target_width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, target_height)
            if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
                capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            frame = None
            for _ in range(frames_to_skip + 1):
                ok, frame = capture.read()
                if ok and frame is not None:
                    break

            if frame is None:
                self.logger.error("相机没有返回画面。")
                self.blackboard.response_text = "相机无画面输出，请稍后再试。"
                return Status.FAILURE

            self.latest_frame = frame

        finally:
            if capture is not None:
                capture.release()

        self.blackboard.response_text = "相机已打开。"
        return Status.SUCCESS
