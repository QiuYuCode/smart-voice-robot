"""
机器人语音助手 - 主程序

基于 py_trees 行为树实现的语音交互系统。
支持: 可配置唤醒词、可切换音色、关键词触发特定行为、
      LLM 自由对话、VAD 静默超时、语音退出指令。

行为树结构:

    Root (Sequence, memory=True)
    ├── WaitForWakeWord (KWS / 硬件唤醒)
    ├── WakeupResponse ("我在，请说")
    └── DialogRepeat (SuccessIsRunning 装饰器, 实现无限循环)
        └── DialogLoop (Sequence, memory=False)
            ├── ListenCommand (流式 ASR + VAD 静默超时)
            ├── RecognizeIntent
            ├── ActionSelector (Selector)
            │   ├── OpenCameraAction
            │   ├── RobotArmAction
            │   ├── NavigationAction (ROS 预留)
            │   ├── LLMDialogAction (LangChain + Ollama)
            │   ├── BackToWakeUp (intent==exit)
            │   └── DefaultResponse
            ├── SpeakResponse (阻塞式 TTS)
            └── DialogContinueGuard (exit → FAILURE 终止循环)

回到唤醒的两条路径:
    1. VAD 静默超时: ListenCommand FAILURE → DialogLoop FAILURE → Root FAILURE
    2. 用户说"退出": DialogContinueGuard FAILURE → DialogLoop FAILURE → Root FAILURE

用法:
    python main.py
"""

import time

import py_trees
from py_trees.common import Status

from config import default_config, RobotConfig
from engine import VoiceEngine
from nodes import (
    WaitForWakeWord,
    HardwareWakeWord,
    ListenCommand,
    RecognizeIntent,
    SpeakResponse,
    WakeupResponse,
    DialogContinueGuard,
    OpenCameraAction,
    RobotArmAction,
    NavigationAction,
    LLMDialogAction,
    DefaultResponse,
    BackToWakeUp,
)


def create_tree(
    engine: VoiceEngine, config: RobotConfig
) -> py_trees.behaviour.Behaviour:
    """
    构建完整的行为树。

    Returns:
        行为树根节点
    """
    # === 1. ActionSelector: 意图分发 ===
    # Selector(memory=False): 每次都从头匹配，按优先级尝试
    action_selector = py_trees.composites.Selector(
        name="ActionSelector", memory=False
    )
    action_selector.add_children([
        OpenCameraAction("OpenCamera"),
        RobotArmAction("RobotArm"),
        NavigationAction("Navigation"),
        LLMDialogAction("LLMDialog", config=config),
        BackToWakeUp("BackToWakeUp"),
        DefaultResponse("DefaultResponse"),
    ])

    # === 2. DialogLoop: 单轮对话流程 ===
    # memory=False: 每轮对话结束后自动重置，从 Listen 重新开始
    # DialogContinueGuard 放在末尾：当 intent == "exit" 时返回 FAILURE，
    # 使 DialogLoop 整体 FAILURE → SuccessIsRunning 透传 → Root FAILURE → 回到唤醒
    dialog_loop = py_trees.composites.Sequence(
        name="DialogLoop", memory=False
    )
    dialog_loop.add_children([
        ListenCommand("Listen", engine),
        RecognizeIntent("Intent", config=config),
        action_selector,
        SpeakResponse("Speak", engine),
        DialogContinueGuard("ContinueGuard"),
    ])

    # === 3. DialogRepeat: 无限循环对话 ===
    # SuccessIsRunning 装饰器: 将 DialogLoop 的 SUCCESS 映射为 RUNNING，
    # 使对话持续循环
    dialog_repeat = py_trees.decorators.SuccessIsRunning(
        name="DialogRepeat",
        child=dialog_loop,
    )

    # === 4. Root: 完整流程 ===
    # memory=True: WakeWord SUCCESS 后记住状态，下一 tick 直接进入对话循环
    root = py_trees.composites.Sequence(
        name="Root", memory=True
    )
    # 根据配置选择唤醒节点
    if config.wake_mode == "hardware":
        wake_node = HardwareWakeWord("WakeWord", engine)
    else:
        wake_node = WaitForWakeWord("WakeWord", engine)

    root.add_children([
        wake_node,
        WakeupResponse("WakeupSound", engine, config),
        dialog_repeat,
    ])

    return root


def main():
    config = default_config

    # 1. 初始化语音引擎
    engine = VoiceEngine(config)
    engine.start()

    # 2. 构建行为树
    root = create_tree(engine, config)
    tree = py_trees.trees.BehaviourTree(root)
    tree.setup(timeout=30)

    print("\n系统启动完毕! 等待唤醒词...")
    print(f"  唤醒模式: {config.wake_mode}")
    if config.wake_mode == "software":
        print(f"  唤醒词文件: {config.kws_keywords_file}")
    else:
        print(f"  串口设备: {config.hw_serial_port}")
        print(f"  麦克风阵列: {config.hw_mic_array}")
    print(f"  TTS 音色 ID: {config.tts_speaker_id}")
    print(f"  LLM 模型: {config.llm_model}")
    print(f"  对话超时: {config.dialog_timeout}s")
    print()

    try:
        while True:
            tree.tick()

            # 整个流程结束 (对话超时 / 打断)，重置回 idle
            if root.status in (Status.SUCCESS, Status.FAILURE):
                print("--- 回合结束，回到待机 ---\n")
                root.stop(Status.INVALID)
                time.sleep(0.5)

            time.sleep(config.tick_interval)

    except KeyboardInterrupt:
        print("\n停止中...")
        engine.stop()


if __name__ == "__main__":
    main()
