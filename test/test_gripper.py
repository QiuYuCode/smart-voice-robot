"""DexHand 夹爪控制测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from config import RobotConfig
    from nodes.actions import gripper
except ModuleNotFoundError as exc:
    RobotConfig = None
    gripper = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


class _AdapterType:
    ZLG_MINI = 42
    ZLG_200U = 33
    LYS_MINI = 43


class _FakeDexHand:
    instances: list["_FakeDexHand"] = []

    def __init__(self, adapter_type, adapter_index):
        self.adapter_type = adapter_type
        self.adapter_index = adapter_index
        self.calls: list[tuple] = []
        _FakeDexHand.instances.append(self)

    def listen(self, enable):
        self.calls.append(("listen", enable))

    def get_device_id(self, channel=0):
        self.calls.append(("get_device_id", channel))
        return 1

    def enable_realtime_response(self, device_id, enable=True):
        self.calls.append(("enable_realtime_response", device_id, enable))

    def clear_error(self, device_id):
        self.calls.append(("clear_error", device_id))

    def reset_joints(self, device_id):
        self.calls.append(("reset_joints", device_id))

    def move_finger(self, device_id, finger_id, target, speed, mode, delay_ms):
        self.calls.append(("move_finger", device_id, finger_id, target, speed, mode, delay_ms))


class GripperTests(unittest.TestCase):
    def setUp(self):
        if _IMPORT_ERROR is not None:
            self.skipTest(f"项目依赖未安装: {_IMPORT_ERROR}")
        _FakeDexHand.instances = []
        self._old_adapter_type = gripper.AdapterType
        self._old_dexhand = gripper.DexHand021S
        gripper.AdapterType = _AdapterType
        gripper.DexHand021S = _FakeDexHand

    def tearDown(self):
        if gripper is not None:
            gripper.AdapterType = self._old_adapter_type
            gripper.DexHand021S = self._old_dexhand

    def test_parse_right_hand_move_command(self):
        self.assertEqual(("right", "shake"), gripper._parse_side_action("让右手动一下"))

    def test_auto_detects_right_hand_device_id_from_sdk(self):
        config = RobotConfig()
        config.gripper_set_safe_current = False
        config.gripper_post_reset_sleep = 0.0
        config.right_gripper = {
            "adapter_index": 1,
            "channel": 0,
            "device_id": 2,
            "has_pressure_sensor": False,
        }

        manager = gripper.DexHandManager(config)
        hand, spec = manager.get_hand("right")

        self.assertIs(hand, _FakeDexHand.instances[0])
        self.assertEqual(1, spec.device_id)
        self.assertIn(("get_device_id", 0), hand.calls)
        self.assertIn(("enable_realtime_response", 1, True), hand.calls)
        self.assertIn(("reset_joints", 1), hand.calls)


if __name__ == "__main__":
    unittest.main()
