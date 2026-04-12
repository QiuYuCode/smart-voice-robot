"""视觉理解动作节点 - 拍照 + VLM 多模态分析"""

from __future__ import annotations

from loguru import logger

import py_trees
from py_trees.behaviour import Behaviour
from py_trees.common import Status

from config import RobotConfig
from nodes.actions.camera import capture_frame_as_base64


def _create_vlm(config: RobotConfig):
    """根据 config.vlm_provider 创建对应的 LangChain Chat Model 实例（需支持多模态）。"""
    provider = config.vlm_provider.lower()

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=config.vlm_model,
            base_url=config.vlm_base_url,
        )

    elif provider == "openai":
        from langchain_openai import ChatOpenAI

        base_url = config.vlm_base_url
        if not base_url or "localhost" in base_url or "127.0.0.1" in base_url:
            base_url = None

        return ChatOpenAI(
            model=config.vlm_model,
            api_key=config.vlm_api_key,
            base_url=base_url,
        )

    elif provider == "deepseek":
        from langchain_openai import ChatOpenAI

        base_url = config.vlm_base_url
        if not base_url or "localhost" in base_url or "127.0.0.1" in base_url:
            base_url = "https://api.deepseek.com"

        return ChatOpenAI(
            model=config.vlm_model,
            api_key=config.vlm_api_key,
            base_url=base_url,
        )

    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=config.vlm_model,
            api_key=config.vlm_api_key,
        )

    else:
        raise ValueError(f"不支持的 VLM provider: {provider}")


def execute_describe_scene(config: RobotConfig, question: str = "请描述你看到的场景") -> str:
    """拍照 + VLM 分析：返回场景的文字描述。

    Raises:
        RuntimeError: 相机或 VLM 不可用。
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    b64, filepath = capture_frame_as_base64(config, save_copy=True)

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
    logger.info("视觉分析完成: {} (图片: {})", desc[:80], filepath or "未保存")
    return desc


class DescribeSceneAction(Behaviour):
    """
    视觉理解动作：拍照并通过 VLM 分析场景。

    intent == "describe_scene" 时执行（非 planner 模式），否则返回 FAILURE。
    """

    def __init__(self, name: str, config: RobotConfig):
        super().__init__(name)
        self._config = config

        self.blackboard = self.attach_blackboard_client(
            name="DescribeSceneAction", namespace="dialog"
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
        if self.blackboard.intent != "describe_scene":
            return Status.FAILURE

        command = self.blackboard.user_command
        self.logger.info(f"执行: 视觉理解 ({command})")

        try:
            desc = execute_describe_scene(self._config, question=command)
            self.blackboard.response_text = desc
            return Status.SUCCESS
        except Exception as e:
            self.logger.error(f"视觉理解失败: {e}")
            self.blackboard.response_text = f"视觉分析失败: {e}"
            return Status.SUCCESS
