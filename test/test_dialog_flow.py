"""对话流程行为树结构测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import py_trees

from config import RobotConfig
from main import create_tree


class _DummyEngine:
    """仅用于构建行为树；测试不 tick 节点，也不初始化硬件。"""

    def __init__(self, config: RobotConfig):
        self.config = config


class DialogFlowTests(unittest.TestCase):
    def test_default_dialog_finishes_after_one_response(self):
        """默认不包 DialogRepeat，DialogLoop SUCCESS 会让 Root 回到唤醒。"""
        config = RobotConfig()
        config.continuous_dialog = False

        root = create_tree(_DummyEngine(config), config)

        self.assertEqual("DialogLoop", root.children[2].name)
        self.assertNotIsInstance(
            root.children[2], py_trees.decorators.SuccessIsRunning
        )

    def test_continuous_dialog_keeps_legacy_repeat_wrapper(self):
        """开启连续对话时保留旧的 SuccessIsRunning 循环行为。"""
        config = RobotConfig()
        config.continuous_dialog = True

        root = create_tree(_DummyEngine(config), config)

        self.assertEqual("DialogRepeat", root.children[2].name)
        self.assertIsInstance(root.children[2], py_trees.decorators.SuccessIsRunning)


if __name__ == "__main__":
    unittest.main()
