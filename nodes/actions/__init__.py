"""动作节点模块"""

from nodes.actions.camera import (
    TakePhotoAction,
    RecordVideoAction,
    execute_take_photo,
    execute_record_video,
    capture_frame_as_base64,
)
from nodes.actions.robot_arm import RobotArmAction, execute_robot_arm
from nodes.actions.navigation import NavigationAction, execute_navigate
from nodes.actions.llm_dialog import LLMDialogAction
from nodes.actions.vision import (
    DescribeSceneAction,
    DescribeLeftPalmAction,
    DescribeRightPalmAction,
    execute_describe_scene,
)
from nodes.actions.back_to_wakeup import BackToWakeUp
from nodes.actions.default_response import DefaultResponse
from nodes.actions.fixed_response import FixedResponseAction
from nodes.actions.gripper import GripperAction, execute_gripper_action

__all__ = [
    "TakePhotoAction",
    "RecordVideoAction",
    "DescribeSceneAction",
    "DescribeLeftPalmAction",
    "DescribeRightPalmAction",
    "RobotArmAction",
    "NavigationAction",
    "LLMDialogAction",
    "BackToWakeUp",
    "FixedResponseAction",
    "DefaultResponse",
    "GripperAction",
    "execute_take_photo",
    "execute_record_video",
    "execute_describe_scene",
    "capture_frame_as_base64",
    "execute_robot_arm",
    "execute_navigate",
    "execute_gripper_action",
]
