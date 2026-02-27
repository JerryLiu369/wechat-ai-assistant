"""AI 后端抽象基类"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class AIResult:
    """AI 执行结果"""

    success: bool  # 是否成功
    output: str  # 输出内容
    error: Optional[str] = None  # 错误信息（如果有）


class AIBackend(ABC):
    """
    AI 后端抽象基类

    所有 AI 后端（iFlow、Qwen Code 等）必须实现此接口
    """

    def __init__(self, name: str):
        """
        初始化 AI 后端

        Args:
            name: 后端名称
        """
        self.name = name

    @abstractmethod
    async def execute(self, command: str, session_id: str) -> AIResult:
        """
        执行 AI 命令

        Args:
            command: 用户命令
            session_id: 会话 ID（用于保持上下文）

        Returns:
            执行结果
        """
        pass

    @abstractmethod
    async def create_session(self, user_id: str) -> str:
        """
        创建新会话

        Args:
            user_id: 用户 ID

        Returns:
            会话 ID
        """
        pass

    @abstractmethod
    async def get_session_info(self, session_id: str) -> dict:
        """
        获取会话信息

        Args:
            session_id: 会话 ID

        Returns:
            会话信息字典
        """
        pass

    async def close(self):
        """关闭后端资源（可选实现）"""
        pass
