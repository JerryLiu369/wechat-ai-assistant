"""iFlow AI 后端实现"""
import asyncio
import shutil
from pathlib import Path
from typing import Dict, Optional

from loguru import logger

from .base import AIBackend, AIResult


class IFlowBackend(AIBackend):
    """iFlow CLI 后端 - 通过工作区隔离实现多用户会话管理"""

    def __init__(self, workspace_base: Optional[Path] = None):
        super().__init__("iflow")
        
        if workspace_base is None:
            workspace_base = Path.home() / ".wechat-ai-assistant" / "workspaces"
        
        self.workspace_base = workspace_base
        self.workspace_base.mkdir(parents=True, exist_ok=True)
        self._session_workspaces: Dict[str, Path] = {}
        
        logger.info(f"[iFlow] 工作区目录：{self.workspace_base}")

    async def execute(self, command: str, session_id: str) -> AIResult:
        """执行 iFlow 命令"""
        workspace = self._get_or_create_workspace(session_id)
        
        args = ["iflow", "--continue", "-p", command, "-o", str(workspace / "last_output.txt")]
        
        logger.info(f"[iFlow] 工作区：{workspace}")
        logger.info(f"[iFlow] 执行命令：{' '.join(args)}")

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(workspace),
            )

            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120.0)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return AIResult(success=False, output="", error="命令执行超时（>120 秒）")

            output = (stdout + stderr).decode("utf-8", errors="replace")
            cleaned_output = self._clean_output(output)

            if proc.returncode == 0:
                logger.info("[iFlow] 命令执行成功")
                return AIResult(success=True, output=cleaned_output or "命令执行完成")
            else:
                logger.warning(f"[iFlow] 命令执行失败，退出码：{proc.returncode}")
                return AIResult(success=False, output=cleaned_output or f"命令执行失败，退出码：{proc.returncode}")

        except FileNotFoundError:
            logger.error("[iFlow] 未找到 iflow 命令，请确保已安装")
            return AIResult(success=False, output="", error="未找到 iflow 命令，请确保已安装 iFlow CLI")
        except Exception as e:
            logger.error(f"[iFlow] 执行错误：{e}")
            return AIResult(success=False, output="", error=f"执行错误：{e}")

    async def create_session(self, user_id: str) -> str:
        """
        创建新会话

        Args:
            user_id: 用户 ID

        Returns:
            会话 ID
        """
        session_id = f"user:{user_id}"
        workspace = self._get_workspace_path(session_id)
        
        # 如果工作区已存在，清空它（开始新会话）
        if workspace.exists():
            shutil.rmtree(workspace)
        
        workspace.mkdir(parents=True, exist_ok=True)
        self._session_workspaces[session_id] = workspace
        
        logger.info(f"[iFlow] 为用户 {user_id} 创建新会话，工作区：{workspace}")
        return session_id

    async def get_session_info(self, session_id: str) -> dict:
        """
        获取会话信息

        Args:
            session_id: 会话 ID

        Returns:
            会话信息
        """
        workspace = self._session_workspaces.get(session_id)
        
        if workspace is None:
            return {
                "session_id": session_id,
                "has_session": False,
                "workspace": None,
            }
        
        # 查找工作区内的 session 文件
        session_files = list(workspace.glob("session-*.jsonl")) if workspace.exists() else []
        latest_session = max(session_files, key=lambda f: f.stat().st_mtime) if session_files else None
        
        return {
            "session_id": session_id,
            "has_session": True,
            "workspace": str(workspace),
            "session_file": str(latest_session) if latest_session else None,
            "session_count": len(session_files),
        }

    def _get_workspace_path(self, session_id: str) -> Path:
        """
        获取工作区路径

        Args:
            session_id: 会话 ID

        Returns:
            工作区路径
        """
        # 将会话 ID 转换为安全的目录名
        # 例如：user:zhangsan -> user_zhangsan
        safe_name = session_id.replace(":", "_").replace("/", "_")
        return self.workspace_base / safe_name

    def _get_or_create_workspace(self, session_id: str) -> Path:
        """
        获取或创建工作区

        Args:
            session_id: 会话 ID

        Returns:
            工作区路径
        """
        if session_id not in self._session_workspaces:
            workspace = self._get_workspace_path(session_id)
            workspace.mkdir(parents=True, exist_ok=True)
            self._session_workspaces[session_id] = workspace
        
        return self._session_workspaces[session_id]

    def _clean_output(self, output: str) -> str:
        """清理输出，移除 Node.js 警告"""
        cleaned = output
        cleaned = cleaned.replace("(node:1) ExperimentalWarning: buffer.File is an experimental feature. ", "")
        cleaned = cleaned.replace("This feature could change at any time", "")
        return cleaned.strip()

    async def close(self):
        """关闭后端资源"""
        logger.info("[iFlow] 关闭后端")
        # 不需要特殊清理，工作区目录保留供下次使用
