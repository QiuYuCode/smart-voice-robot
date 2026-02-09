"""打开相机动作节点"""

import py_trees
from py_trees.behaviour import Behaviour
from py_trees.common import Status


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

        # TODO: 实际相机逻辑
        # import cv2
        # cap = cv2.VideoCapture(0)
        # ret, frame = cap.read()
        # cv2.imshow("Camera", frame)
        # ...

        self.blackboard.response_text = "相机已打开。"
        return Status.SUCCESS
