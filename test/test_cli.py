"""
CLI 测试工具 - 模拟语音输入，测试意图识别和动作节点

绕过麦克风、唤醒词检测，用文本输入替代 ASR 输出。
默认用控制台打印替代 TTS 播放，加 --tts 可启用语音播报。

用法:
    python test/test_cli.py                      # 交互模式 (关键词匹配)
    python test/test_cli.py "帮我拍照"            # 单次模式
    python test/test_cli.py --planner             # LLM 多指令规划模式
    python test/test_cli.py --planner --tts       # 规划模式 + 语音播报
    python test/test_cli.py --provider deepseek   # 指定 LLM provider
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import py_trees
from py_trees.behaviour import Behaviour
from py_trees.common import Status

from config import default_config, RobotConfig, TTS_DIR, SAMPLE_RATE
from nodes.intent import RecognizeIntent
from nodes.guards import DialogContinueGuard
from nodes.planner import LLMTaskPlanner
from nodes.plan_executor import PlanExecutor
from nodes.actions import (
    TakePhotoAction,
    RecordVideoAction,
    RobotArmAction,
    NavigationAction,
    LLMDialogAction,
    DefaultResponse,
    BackToWakeUp,
)


# ---------------------------------------------------------------------------
# 轻量级 TTS 引擎 (仅加载语音合成模型，不需要麦克风/ASR/KWS)
# ---------------------------------------------------------------------------

class SimpleTTS:
    """仅包含 TTS 的轻量引擎，用于 CLI 测试时播报任务结果。"""

    def __init__(self, config: RobotConfig):
        import sherpa_onnx
        import sounddevice as sd  # noqa: F401 — 确保音频输出可用

        self._config = config
        self._tts = sherpa_onnx.OfflineTts(
            config=sherpa_onnx.OfflineTtsConfig(
                model=sherpa_onnx.OfflineTtsModelConfig(
                    vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                        model=f"{TTS_DIR}/vits-aishell3.onnx",
                        lexicon=f"{TTS_DIR}/lexicon.txt",
                        tokens=f"{TTS_DIR}/tokens.txt",
                    ),
                    num_threads=config.num_threads,
                )
            )
        )
        print("[TTS] 语音合成模型已加载")

    def speak_blocking(self, text: str):
        """阻塞式 TTS：合成 + 播放，播放完毕后返回。"""
        import sounddevice as sd

        if not text:
            return
        audio = self._tts.generate(
            text,
            sid=self._config.tts_speaker_id,
            speed=self._config.tts_speed,
        )
        samples = np.asarray(audio.samples, dtype=np.float32)
        sd.play(samples, samplerate=audio.sample_rate)
        sd.wait()


# ---------------------------------------------------------------------------
# Mock 行为节点
# ---------------------------------------------------------------------------

class TextInputCommand(Behaviour):
    """替代 ListenCommand：从 text_source callable 获取用户文本命令。"""

    def __init__(self, name: str, text_source):
        super().__init__(name)
        self._text_source = text_source

        self.blackboard = self.attach_blackboard_client(
            name="TextInputCommand", namespace="dialog"
        )
        self.blackboard.register_key(
            key="user_command", access=py_trees.common.Access.WRITE
        )
        self.blackboard.register_key(
            key="last_activity_time", access=py_trees.common.Access.WRITE
        )

    def update(self):
        text = self._text_source()
        if not text:
            return Status.FAILURE

        self.blackboard.user_command = text
        self.blackboard.last_activity_time = time.time()
        return Status.SUCCESS


class PrintResponse(Behaviour):
    """替代 SpeakResponse：将 response_text 打印到控制台，可选 TTS 语音播报。"""

    def __init__(self, name: str, tts: SimpleTTS | None = None):
        super().__init__(name)
        self._tts = tts

        self.blackboard = self.attach_blackboard_client(
            name="PrintResponse", namespace="dialog"
        )
        self.blackboard.register_key(
            key="response_text", access=py_trees.common.Access.READ
        )
        self.blackboard.register_key(
            key="is_speaking", access=py_trees.common.Access.WRITE
        )
        self.blackboard.register_key(
            key="speak_start_time", access=py_trees.common.Access.WRITE
        )
        self.blackboard.register_key(
            key="last_activity_time", access=py_trees.common.Access.WRITE
        )

    def update(self):
        text = getattr(self.blackboard, "response_text", "")
        print(f"[机器人] {text}")
        if self._tts and text:
            self._tts.speak_blocking(text)
        self.blackboard.is_speaking = False
        self.blackboard.speak_start_time = 0.0
        self.blackboard.last_activity_time = time.time()
        return Status.SUCCESS


# ---------------------------------------------------------------------------
# 行为树构建
# ---------------------------------------------------------------------------

def create_test_tree(
    config: RobotConfig,
    text_source,
    tts: SimpleTTS | None = None,
) -> py_trees.behaviour.Behaviour:
    """
    构建测试用行为树。

    关键词匹配模式:
        TestDialogLoop (Sequence, memory=False)
          +-- TextInputCommand
          +-- RecognizeIntent
          +-- ActionSelector (与 main.py 一致)
          +-- PrintResponse
          +-- DialogContinueGuard

    LLM 规划器模式 (--planner):
        TestDialogLoop (Sequence, memory=False)
          +-- TextInputCommand
          +-- LLMTaskPlanner
          +-- PlanExecutor
          +-- PrintResponse
          +-- DialogContinueGuard
    """
    dialog_loop = py_trees.composites.Sequence(
        name="TestDialogLoop", memory=False
    )

    if config.use_llm_planner:
        dialog_loop.add_children([
            TextInputCommand("TextInput", text_source),
            LLMTaskPlanner("Planner", config=config),
            PlanExecutor("Executor", config=config),
            PrintResponse("Print", tts=tts),
            DialogContinueGuard("ContinueGuard"),
        ])
    else:
        action_selector = py_trees.composites.Selector(
            name="ActionSelector", memory=False
        )
        action_selector.add_children([
            TakePhotoAction("TakePhoto", config=config),
            RecordVideoAction("RecordVideo", config=config),
            RobotArmAction("RobotArm"),
            NavigationAction("Navigation"),
            LLMDialogAction("LLMDialog", config=config),
            BackToWakeUp("BackToWakeUp"),
            DefaultResponse("DefaultResponse"),
        ])
        dialog_loop.add_children([
            TextInputCommand("TextInput", text_source),
            RecognizeIntent("Intent", config=config),
            action_selector,
            PrintResponse("Print", tts=tts),
            DialogContinueGuard("ContinueGuard"),
        ])

    return dialog_loop


# ---------------------------------------------------------------------------
# 运行模式
# ---------------------------------------------------------------------------

def _interactive_source():
    """交互模式：从 stdin 读取一行文本。"""
    try:
        text = input("[你] ").strip()
    except EOFError:
        return None
    return text or None


def _oneshot_source(command: str):
    """单次模式：返回一个只产出一次的 callable。"""
    fired = False

    def source():
        nonlocal fired
        if fired:
            return None
        fired = True
        print(f"[你] {command}")
        return command

    return source


def _init_tts(config: RobotConfig, enable: bool) -> SimpleTTS | None:
    """按需初始化 TTS 引擎，失败时降级为纯文本输出。"""
    if not enable:
        return None
    try:
        return SimpleTTS(config)
    except Exception as e:
        print(f"[警告] TTS 初始化失败，降级为纯文本输出: {e}")
        return None


def run_interactive(config: RobotConfig, tts: SimpleTTS | None = None):
    """交互模式：循环接收文本输入，直到用户退出。"""
    root = create_test_tree(config, _interactive_source, tts=tts)
    loop = py_trees.decorators.SuccessIsRunning(
        name="TestLoop", child=root
    )
    tree = py_trees.trees.BehaviourTree(loop)
    tree.setup(timeout=30)

    mode = "LLM 多指令规划" if config.use_llm_planner else "关键词匹配"
    tts_label = "开启" if tts else "关闭"
    print(f"\n=== 语音机器人 CLI 测试 ({mode}, TTS {tts_label}) ===")
    print("输入文本模拟语音命令，输入空行或 Ctrl+C 退出\n")

    try:
        while True:
            tree.tick()
            if loop.status in (Status.SUCCESS, Status.FAILURE):
                print("--- 对话结束 ---")
                break
            time.sleep(0.01)
    except KeyboardInterrupt:
        print("\n已退出。")


def run_oneshot(config: RobotConfig, command: str, tts: SimpleTTS | None = None):
    """单次模式：处理单条命令后退出。"""
    root = create_test_tree(config, _oneshot_source(command), tts=tts)
    tree = py_trees.trees.BehaviourTree(root)
    tree.setup(timeout=30)

    tree.tick()
    if root.status == Status.FAILURE:
        print("--- 对话结束 ---")


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="CLI 测试工具 - 模拟语音输入测试动作节点"
    )
    parser.add_argument(
        "command", nargs="?", default=None,
        help="单次模式: 要测试的文本命令 (不指定则进入交互模式)",
    )
    parser.add_argument(
        "--planner", action="store_true",
        help="启用 LLM 多指令规划模式 (默认: 关键词匹配模式)",
    )
    parser.add_argument(
        "--provider", default=None,
        help="覆盖 LLM provider (ollama / openai / deepseek / anthropic)",
    )
    parser.add_argument(
        "--model", default=None,
        help="覆盖 LLM 模型名称",
    )
    parser.add_argument(
        "--base-url", default=None,
        help="覆盖 LLM base URL",
    )
    parser.add_argument(
        "--api-key", default=None,
        help="覆盖 LLM API key",
    )
    parser.add_argument(
        "--tts", action="store_true",
        help="启用 TTS 语音播报 (默认关闭，仅打印文本)",
    )
    return parser.parse_args()


_PROVIDER_DEFAULT_MODELS = {
    "deepseek": "deepseek-chat",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-20250514",
}


def main():
    args = parse_args()
    config = default_config

    if args.planner:
        config.use_llm_planner = True
    if args.provider:
        config.llm_provider = args.provider
        if not args.model and args.provider in _PROVIDER_DEFAULT_MODELS:
            config.llm_model = _PROVIDER_DEFAULT_MODELS[args.provider]
    if args.model:
        config.llm_model = args.model
    if args.base_url:
        config.llm_base_url = args.base_url
    if args.api_key:
        config.llm_api_key = args.api_key

    py_trees.logging.level = py_trees.logging.Level.INFO

    tts = _init_tts(config, args.tts)

    if args.command:
        run_oneshot(config, args.command, tts=tts)
    else:
        run_interactive(config, tts=tts)


if __name__ == "__main__":
    main()
