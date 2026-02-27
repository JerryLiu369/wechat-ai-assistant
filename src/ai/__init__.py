"""AI 后端模块"""
from .base import AIBackend, AIResult
from .qwen import QwenBackend

__all__ = ["AIBackend", "AIResult", "QwenBackend"]
