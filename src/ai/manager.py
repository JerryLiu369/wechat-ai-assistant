"""AI 会话管理器"""
from typing import Dict, Optional

from loguru import logger

from .base import AIBackend, AIResult


class AISessionManager:
    """
    AI 会话管理器

    负责：
    - 管理多个 AI 后端
    - 用户会话隔离（每个用户独立会话）
    - 命令执行与回复
    """

    def __init__(self):
        self._backends: Dict[str, AIBackend] = {}
        self._user_sessions: Dict[str, str] = {}  # (user_id, backend_name) -> session_id

    def register_backend(self, backend: AIBackend):
        """
        注册 AI 后端

        Args:
            backend: AI 后端实例
        """
        self._backends[backend.name] = backend
        logger.info(f"[AI] 注册后端：{backend.name}")

    def get_backend(self, name: str) -> Optional[AIBackend]:
        """
        获取 AI 后端

        Args:
            name: 后端名称

        Returns:
            AI 后端实例（不存在返回 None）
        """
        return self._backends.get(name)

    async def execute_command(
        self,
        user_id: str,
        command: str,
        backend_name: str = "iflow",
    ) -> AIResult:
        """
        执行用户命令

        Args:
            user_id: 用户 ID
            command: 命令内容
            backend_name: AI 后端名称

        Returns:
            执行结果
        """
        backend = self.get_backend(backend_name)
        if not backend:
            return AIResult(
                success=False,
                output="",
                error=f"AI 后端 '{backend_name}' 不存在",
            )

        # 获取或创建用户会话
        session_key = f"{user_id}:{backend_name}"
        session_id = self._user_sessions.get(session_key)

        if not session_id:
            # 创建新会话
            session_id = await backend.create_session(user_id)
            self._user_sessions[session_key] = session_id
            logger.info(f"[AI] 为用户 {user_id} 创建会话：{session_id}")

        # 执行命令
        logger.info(f"[AI] 执行命令：{user_id} -> {command[:50]}...")
        result = await backend.execute(command, session_id)

        return result

    async def new_session(self, user_id: str, backend_name: str = "iflow") -> bool:
        """
        创建新会话（清除上下文）

        Args:
            user_id: 用户 ID
            backend_name: AI 后端名称

        Returns:
            是否成功
        """
        backend = self.get_backend(backend_name)
        if not backend:
            return False

        session_key = f"{user_id}:{backend_name}"
        new_session_id = await backend.create_session(user_id)
        self._user_sessions[session_key] = new_session_id

        logger.info(f"[AI] 为用户 {user_id} 重置会话：{new_session_id}")
        return True

    async def get_status(self, user_id: str, backend_name: str = "iflow") -> dict:
        """
        获取用户会话状态

        Args:
            user_id: 用户 ID
            backend_name: AI 后端名称

        Returns:
            状态信息
        """
        backend = self.get_backend(backend_name)
        if not backend:
            return {"error": f"AI 后端 '{backend_name}' 不存在"}

        session_key = f"{user_id}:{backend_name}"
        session_id = self._user_sessions.get(session_key)

        if session_id:
            info = await backend.get_session_info(session_id)
            return {
                "has_session": True,
                "session_id": session_id,
                "backend": backend_name,
                **info,
            }
        else:
            return {
                "has_session": False,
                "backend": backend_name,
            }

    async def close(self):
        """关闭所有 AI 后端"""
        for name, backend in self._backends.items():
            try:
                await backend.close()
                logger.info(f"[AI] 已关闭后端：{name}")
            except Exception as e:
                logger.error(f"[AI] 关闭后端 {name} 失败：{e}")
