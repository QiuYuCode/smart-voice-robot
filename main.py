"""
机器人语音助手 - 主程序

基于 py_trees 行为树实现的语音交互系统。
支持: 可配置唤醒词、可切换音色、关键词触发特定行为、
      LLM 自由对话、VAD 静默超时、语音退出指令。

行为树结构:

    关键词匹配模式 (use_llm_planner=False, 默认):

    Root (Sequence, memory=True)
    ├── WaitForWakeWord (KWS / 硬件唤醒)
    ├── WakeupResponse ("我在，请说")
    └── DialogRepeat (SuccessIsRunning 装饰器, 实现无限循环)
        └── DialogLoop (Sequence, memory=False)
            ├── ListenCommand (流式 ASR + VAD 静默超时)
            ├── RecognizeIntent
            ├── ActionSelector (Selector)
            │   ├── DescribeLeftPalmAction (VLM + 左掌心相机)
            │   ├── DescribeRightPalmAction (VLM + 右掌心相机)
            │   ├── DescribeSceneAction (VLM + 默认相机=head)
            │   ├── TakePhotoAction
            │   ├── RecordVideoAction
            │   ├── RobotArmAction
            │   ├── NavigationAction (ROS 预留)
            │   ├── LLMDialogAction (LangChain + Ollama)
            │   ├── BackToWakeUp (intent==exit)
            │   └── DefaultResponse
            ├── SpeakResponse (阻塞式 TTS)
            └── DialogContinueGuard (exit → FAILURE 终止循环)

    LLM 规划器模式 (use_llm_planner=True, 支持多指令):

    Root (Sequence, memory=True)
    ├── WaitForWakeWord (KWS / 硬件唤醒)
    ├── WakeupResponse ("我在，请说")
    └── DialogRepeat (SuccessIsRunning 装饰器, 实现无限循环)
        └── DialogLoop (Sequence, memory=False)
            ├── ListenCommand (流式 ASR + VAD 静默超时)
            ├── LLMTaskPlanner (LLM Function Calling 解析多步指令)
            ├── PlanExecutor (依次执行 action_plan)
            ├── SpeakResponse (阻塞式 TTS)
            └── DialogContinueGuard (exit → FAILURE 终止循环)

回到唤醒的两条路径:
    1. VAD 静默超时: ListenCommand FAILURE → DialogLoop FAILURE → Root FAILURE
    2. 用户说"退出": DialogContinueGuard FAILURE → DialogLoop FAILURE → Root FAILURE

用法:
    python main.py
"""

import sys
import time

import py_trees
from loguru import logger
from py_trees.common import Status

from config import default_config, RobotConfig
from engine import VoiceEngine
from nodes import (
    WaitForWakeWord,
    HardwareWakeWord,
    ListenCommand,
    ListenCloudCommand,
    RecognizeIntent,
    SpeakResponse,
    WakeupResponse,
    WakeWordInterruptMonitor,
    ResetWakeWordInterruptState,
    DialogContinueGuard,
    TakePhotoAction,
    RecordVideoAction,
    DescribeSceneAction,
    DescribeLeftPalmAction,
    DescribeRightPalmAction,
    RobotArmAction,
    GripperAction,
    NavigationAction,
    LLMDialogAction,
    DefaultResponse,
    BackToWakeUp,
    FixedResponseAction,
    LLMTaskPlanner,
    PlanExecutor,
)


def create_tree(
    engine: VoiceEngine, config: RobotConfig
) -> py_trees.behaviour.Behaviour:
    """
    构建完整的行为树。

    Returns:
        行为树根节点
    """
    # memory=True: 当前轮执行到 SpeakStage 时，后续 tick 持续停留在该阶段，
    # 不会回头重新执行 Listen/Intent，从而实现“Listen 挂起，WakeWord 仅在 TTS 阶段活跃”。
    dialog_loop = py_trees.composites.Sequence(name="DialogLoop", memory=True)

    listen_node = (
        ListenCloudCommand("ListenCloud", engine)
        if config.asr_backend == "iflytek_cloud"
        else ListenCommand("Listen", engine)
    )

    speak_parallel = py_trees.composites.Parallel(
        name="SpeakOrInterrupt",
        policy=py_trees.common.ParallelPolicy.SuccessOnOne(),
    )
    speak_parallel.add_children([
        SpeakResponse("Speak", engine),
        WakeWordInterruptMonitor("WakeWordInterrupt", engine, config),
    ])

    speak_stage = py_trees.composites.Sequence(name="SpeakStage", memory=False)
    speak_stage.add_children([
        speak_parallel,
        ResetWakeWordInterruptState("ResetWakeWordInterrupt", engine, config),
    ])

    if config.use_llm_planner:
        # === LLM 规划器模式: 支持一句话多指令 ===
        dialog_loop.add_children([
            listen_node,
            LLMTaskPlanner("Planner", config=config, engine=engine),
            PlanExecutor("Executor", config=config, engine=engine),
            speak_stage,
            DialogContinueGuard("ContinueGuard"),
        ])
    else:
        # === 关键词匹配模式 (原有行为) ===
        action_selector = py_trees.composites.Selector(
            name="ActionSelector", memory=False
        )
        action_selector.add_children([
            FixedResponseAction("FixedResponse", config=config),
            DescribeLeftPalmAction("DescribeLeftPalm", config=config),
            DescribeRightPalmAction("DescribeRightPalm", config=config),
            DescribeSceneAction("DescribeScene", config=config),
            TakePhotoAction("TakePhoto", config=config),
            RecordVideoAction("RecordVideo", config=config),
            GripperAction("Gripper", config=config),
            RobotArmAction("RobotArm"),
            NavigationAction("Navigation"),
            LLMDialogAction("LLMDialog", config=config),
            BackToWakeUp("BackToWakeUp"),
            DefaultResponse("DefaultResponse"),
        ])
        dialog_loop.add_children([
            listen_node,
            RecognizeIntent("Intent", config=config),
            action_selector,
            speak_stage,
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
        # DEPRECATED: RK3328 硬件唤醒已弃用
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

    # 配置 loguru：移除默认 handler，使用自定义格式
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - <level>{message}</level>",
        level="DEBUG",
        colorize=True,
    )
    logger.add(
        f"{config.log_dir}/robot_{{time:YYYY-MM-DD}}.log",
        rotation="00:00",
        retention=config.log_retention,
        encoding="utf-8",
        level=config.log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name} - {message}",
    )

    # 1. 初始化语音引擎
    engine = VoiceEngine(config)
    engine.start()

    # 2. 构建行为树
    root = create_tree(engine, config)
    tree = py_trees.trees.BehaviourTree(root)
    tree.setup(timeout=30)

    # 3. 可选：启动 Web 监控面板
    if config.enable_monitor:
        from monitor.server import MonitorServer
        from monitor.visitor import StateCapturingVisitor
        monitor = MonitorServer(port=config.monitor_port, config=config)
        monitor.start_background()
        engine.monitor = monitor
        visitor = StateCapturingVisitor(monitor.state_queue, monitor.conversation_log, root, monitor=monitor)
        tree.add_visitor(visitor)
        logger.info(f"监控面板: http://localhost:{config.monitor_port}")

    logger.info("系统启动完毕! 等待唤醒词...")
    logger.info(f"  唤醒模式: {config.wake_mode}")
    if config.wake_mode == "software":
        logger.info(f"  唤醒词文件: {config.kws_keywords_file}")
    logger.info(f"  TTS 音色 ID: {config.tts_speaker_id}")
    logger.info(f"  LLM 模型: {config.llm_model}")
    mode_label = "LLM 多指令规划" if config.use_llm_planner else "关键词匹配"
    logger.info(f"  意图模式: {mode_label}")
    logger.info(f"  对话超时: {config.dialog_timeout}s")

    if config.startup_sound_enabled:
        engine.speak_blocking(config.startup_sound_text)

    try:
        while True:
            tree.tick()

            # 整个流程结束 (对话超时 / 打断)，重置回 idle
            if root.status in (Status.SUCCESS, Status.FAILURE):
                logger.debug("回合结束，回到待机")
                root.stop(Status.INVALID)
                time.sleep(0.5)

            time.sleep(config.tick_interval)

    except KeyboardInterrupt:
        logger.info("停止中...")
        engine.stop()


if __name__ == "__main__":
    main()
