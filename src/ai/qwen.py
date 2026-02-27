"""Qwen Code 执行器 - 简单直接的实现"""
import asyncio
import shutil
from pathlib import Path

from loguru import logger


class QwenExecutor:
    """
    Qwen Code 执行器
    
    会话管理：一个用户 = 一个工作区文件夹
    - 用户消息自动保存到 ~/.wechat-ai-assistant/workspaces/{user_id}/
    - qwen --continue 自动加载该目录的会话历史
    """

    def __init__(self):
        self.workspace_base = Path.home() / ".wechat-ai-assistant" / "workspaces"
        self.workspace_base.mkdir(parents=True, exist_ok=True)
        logger.info(f"[Qwen] 工作区目录：{self.workspace_base}")

    def _get_workspace(self, user_id: str) -> Path:
        """获取用户工作区"""
        return self.workspace_base / user_id

    async def execute(self, user_id: str, command: str) -> tuple[bool, str]:
        """
        执行 Qwen 命令
        
        Args:
            user_id: 用户 ID（企业微信 UserID）
            command: 命令内容
            
        Returns:
            (success, output) 元组
        """
        workspace = self._get_workspace(user_id)
        workspace.mkdir(parents=True, exist_ok=True)
        
        args = ["qwen", "--continue", "--yolo", command]
        
        logger.info(f"[Qwen] 用户 {user_id} -> 工作区：{workspace}")
        logger.info(f"[Qwen] 执行：{' '.join(args)}")

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
                return False, "命令执行超时（>120 秒）"

            output = (stdout + stderr).decode("utf-8", errors="replace").strip()

            if proc.returncode == 0:
                logger.info("[Qwen] 执行成功")
                return True, output or "命令执行完成"
            else:
                logger.warning(f"[Qwen] 执行失败，退出码：{proc.returncode}")
                return False, output or f"命令执行失败，退出码：{proc.returncode}"

        except FileNotFoundError:
            logger.error("[Qwen] 未找到 qwen 命令")
            return False, "未找到 qwen 命令，请确保已安装 Qwen Code CLI"
        except Exception as e:
            logger.error(f"[Qwen] 执行错误：{e}")
            return False, f"执行错误：{e}"

    async def reset_session(self, user_id: str) -> bool:
        """重置用户会话（清空工作区）"""
        workspace = self._get_workspace(user_id)
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True, exist_ok=True)
        logger.info(f"[Qwen] 用户 {user_id} 会话已重置")
        return True

    async def get_status(self, user_id: str) -> dict:
        """获取用户会话状态"""
        workspace = self._get_workspace(user_id)
        
        if not workspace.exists():
            return {"has_session": False}
        
        session_files = list(workspace.glob("*.json"))
        latest = max(session_files, key=lambda f: f.stat().st_mtime) if session_files else None
        
        return {
            "has_session": True,
            "workspace": str(workspace),
            "session_file": str(latest) if latest else None,
            "session_count": len(session_files),
        }
