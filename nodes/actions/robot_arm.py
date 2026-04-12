"""机械臂控制动作节点"""

from __future__ import annotations

from loguru import logger

import py_trees
from py_trees.behaviour import Behaviour
from py_trees.common import Status


# ============================================================================
# 独立执行函数 (供 Behaviour 节点和 planner tool 共同调用)
# ============================================================================

def execute_robot_arm(action: str) -> str:
    """机械臂控制核心逻辑。返回执行结果描述。

    TODO: 通过串口 / ROS service / GPIO 等方式控制
    """
    logger.info("执行机械臂控制: %s", action)
    # TODO: 实际机械臂控制实现
    return f"机械臂指令已发送: {action}。"


# ============================================================================
# 机械臂动作 (行为树节点)
# ============================================================================

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
        self.blackboard.response_text = execute_robot_arm(command)
        return Status.SUCCESS
