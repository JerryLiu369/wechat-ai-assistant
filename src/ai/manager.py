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

    def __init__(self, default_backend: str = "qwen"):
        self._backends: Dict[str, AIBackend] = {}
        self._user_sessions: Dict[str, str] = {}
        self._default_backend = default_backend

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
        backend_name: Optional[str] = None,
    ) -> AIResult:
        """执行用户命令"""
        backend_name = backend_name or self._default_backend
        
        backend = self.get_backend(backend_name)
        if not backend:
            return AIResult(
                success=False,
                output="",
                error=f"AI 后端 '{backend_name}' 不存在",
            )

        session_key = f"{user_id}:{backend_name}"
        session_id = self._user_sessions.get(session_key)

        if not session_id:
            session_id = await backend.create_session(user_id)
            self._user_sessions[session_key] = session_id
            logger.info(f"[AI] 为用户 {user_id} 创建会话：{session_id}")

        logger.info(f"[AI] 执行命令：{user_id} -> {command[:50]}...")
        return await backend.execute(command, session_id)

    async def new_session(self, user_id: str, backend_name: Optional[str] = None) -> bool:
        """创建新会话（清除上下文）"""
        backend_name = backend_name or self._default_backend
        
        backend = self.get_backend(backend_name)
        if not backend:
            return False

        session_key = f"{user_id}:{backend_name}"
        new_session_id = await backend.create_session(user_id)
        self._user_sessions[session_key] = new_session_id

        logger.info(f"[AI] 为用户 {user_id} 重置会话：{new_session_id}")
        return True

    async def get_status(self, user_id: str, backend_name: Optional[str] = None) -> dict:
        """获取用户会话状态"""
        backend_name = backend_name or self._default_backend
        
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
        return {"has_session": False, "backend": backend_name}

    async def close(self):
        """关闭所有 AI 后端"""
        for name, backend in self._backends.items():
            try:
                await backend.close()
                logger.info(f"[AI] 已关闭后端：{name}")
            except Exception as e:
                logger.error(f"[AI] 关闭后端 {name} 失败：{e}")
