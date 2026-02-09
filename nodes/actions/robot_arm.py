"""机械臂控制动作节点"""

import py_trees
from py_trees.behaviour import Behaviour
from py_trees.common import Status


class RobotArmAction(Behaviour):
    """
    控制机械臂。

    当 intent == "robot_arm" 时执行，否则返回 FAILURE。
    """

    def __init__(self, name: str):
        super().__init__(name)

        self.blackboard = self.attach_blackboard_client(
            name="RobotArmAction", namespace="dialog"
        )
        self.blackboard.register_key(
            key="intent", access=py_trees.common.Access.READ
        )
        self.blackboard.register_key(
            key="user_command", access=py_trees.common.Access.READ
        )
        self.blackboard.register_key(
            key="response_text", access=py_trees.common.Access.WRITE
        )

    def update(self):
        if self.blackboard.intent != "robot_arm":
            return Status.FAILURE

        command = self.blackboard.user_command
        self.logger.info(f"执行: 机械臂控制 ({command})")

        # TODO: 实际机械臂控制逻辑
        # 通过串口 / ROS service / GPIO 等方式控制
        # import serial
        # ser = serial.Serial('/dev/ttyUSB0', 115200)
        # ser.write(b'move ...')

        self.blackboard.response_text = "机械臂指令已发送。"
        return Status.SUCCESS
