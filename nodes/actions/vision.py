"""视觉理解动作节点 - 拍照 + VLM 多模态分析 (多路相机)"""

from __future__ import annotations

import py_trees
from loguru import logger
from py_trees.behaviour import Behaviour
from py_trees.common import Status

from config import RobotConfig
from nodes.actions.camera import capture_frame_as_base64


# ============================================================================
# VLM 构造
# ============================================================================

def _create_vlm(config: RobotConfig):
    """根据 config.vlm_provider 创建 LangChain Chat Model (需支持多模态)。"""
    provider = config.vlm_provider.lower()

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=config.vlm_model,
            base_url=config.vlm_base_url,
        )

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        base_url = config.vlm_base_url
        if not base_url or "localhost" in base_url or "127.0.0.1" in base_url:
            base_url = None
        return ChatOpenAI(
            model=config.vlm_model,
            api_key=config.vlm_api_key,
            base_url=base_url,
        )

    if provider == "deepseek":
        from langchain_openai import ChatOpenAI

        base_url = config.vlm_base_url
        if not base_url or "localhost" in base_url or "127.0.0.1" in base_url:
            base_url = "https://api.deepseek.com"
        return ChatOpenAI(
            model=config.vlm_model,
            api_key=config.vlm_api_key,
            base_url=base_url,
        )

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=config.vlm_model,
            api_key=config.vlm_api_key,
        )

    raise ValueError(f"不支持的 VLM provider: {provider}")


# ============================================================================
# 独立执行函数
# ============================================================================

def execute_describe_scene(
    config: RobotConfig,
    question: str = "请描述你看到的场景",
    camera_id: str | None = None,
) -> str:
    """拍照 + VLM 分析。`camera_id=None` 时使用 config.default_camera。"""
    from langchain_core.messages import HumanMessage, SystemMessage

    cid = camera_id or config.default_camera
    b64, filepath = capture_frame_as_base64(config, save_copy=True, camera_id=cid)

    vlm = _create_vlm(config)
    messages = [
        SystemMessage(content=config.vlm_system_prompt),
        HumanMessage(content=[
            {"type": "text", "text": question},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            },
        ]),
    ]
    response = vlm.invoke(messages)
    desc = response.content
    logger.info(
        "视觉分析完成 [{}]: {} (图片: {})",
        cid, desc[:80], filepath or "未保存",
    )
    return desc


# ============================================================================
# 行为树节点
# ============================================================================

class DescribeSceneAction(Behaviour):
    """
    通用视觉理解动作: 根据 intent 决定触发条件与使用的相机。

    默认实例触发 intent == "describe_scene"，使用 config.default_camera。
    通过子类或参数可扩展出 describe_left_palm / describe_right_palm。
    """

    INTENT: str = "describe_scene"
    CAMERA_ID: str | None = None

    def __init__(
        self,
        name: str,
        config: RobotConfig,
        intent: str | None = None,
        camera_id: str | None = None,
    ):
        super().__init__(name)
        self._config = config
        self._intent = intent or self.INTENT
        self._camera_id = camera_id if camera_id is not None else self.CAMERA_ID

        self.blackboard = self.attach_blackboard_client(
            name=name, namespace="dialog"
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
        if self.blackboard.intent != self._intent:
            return Status.FAILURE

        command = self.blackboard.user_command
        cid = self._camera_id or self._config.default_camera
        self.logger.info(f"执行: 视觉理解 intent={self._intent} camera={cid} ({command})")

        try:
            desc = execute_describe_scene(
                self._config, question=command, camera_id=cid,
            )
            self.blackboard.response_text = desc
            return Status.SUCCESS
        except Exception as e:
            self.logger.error(f"视觉理解失败: {e}")
            self.blackboard.response_text = f"视觉分析失败: {e}"
            return Status.SUCCESS


class DescribeLeftPalmAction(DescribeSceneAction):
    """intent == 'describe_left_palm' 时，用左掌心相机触发 VLM 分析。"""
    INTENT = "describe_left_palm"
    CAMERA_ID = "left_palm"


class DescribeRightPalmAction(DescribeSceneAction):
    """intent == 'describe_right_palm' 时，用右掌心相机触发 VLM 分析。"""
    INTENT = "describe_right_palm"
    CAMERA_ID = "right_palm"
