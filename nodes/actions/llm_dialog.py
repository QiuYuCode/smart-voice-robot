"""LLM 对话动作节点 (langchain-ollama)"""

import py_trees
from py_trees.behaviour import Behaviour
from py_trees.common import Status

from config import RobotConfig


class LLMDialogAction(Behaviour):
    """
    LLM 自由对话 (fallback)。

    当 intent == "chat" 时执行 (所有关键词 action 都 FAILURE 后)。
    使用 langchain-ollama 的 ChatOllama 连接本地 Ollama 大模型，
    维护对话历史实现多轮会话。
    """

    def __init__(self, name: str, config: RobotConfig):
        super().__init__(name)
        self.config = config
        self.conversation_history: list = []
        self.llm = None

        self.blackboard = self.attach_blackboard_client(
            name="LLMDialogAction", namespace="dialog"
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

    def setup(self, **kwargs):
        """延迟初始化 LLM 连接"""
        try:
            from langchain_ollama import ChatOllama

            self.llm = ChatOllama(
                model=self.config.llm_model,
                base_url=self.config.llm_base_url,
            )
            self.logger.info(f"LLM 已连接: {self.config.llm_model}")
        except ImportError:
            self.logger.warning(
                "langchain-ollama 未安装，LLM 对话不可用。"
                "请运行: uv add langchain-ollama langchain-core"
            )
        except Exception as e:
            self.logger.warning(f"LLM 初始化失败: {e}")

    def update(self):
        if self.blackboard.intent != "chat":
            return Status.FAILURE

        if self.llm is None:
            self.blackboard.response_text = "大模型未就绪，请稍后再试。"
            return Status.SUCCESS

        command = self.blackboard.user_command
        self.logger.info(f"LLM 对话: {command}")

        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            messages = [
                SystemMessage(content=self.config.llm_system_prompt),
                *self.conversation_history,
                HumanMessage(content=command),
            ]

            response = self.llm.invoke(messages)

            # 更新对话历史
            self.conversation_history.append(HumanMessage(content=command))
            self.conversation_history.append(response)

            # 限制历史长度 (每轮 2 条: Human + AI)
            max_msgs = self.config.llm_max_history * 2
            if len(self.conversation_history) > max_msgs:
                self.conversation_history = self.conversation_history[-max_msgs:]

            self.blackboard.response_text = response.content

        except Exception as e:
            self.logger.error(f"LLM 调用失败: {e}")
            self.blackboard.response_text = "抱歉，我暂时无法回答。"

        return Status.SUCCESS
