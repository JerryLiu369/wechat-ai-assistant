"""AI 后端模块"""
from .base import AIBackend, AIResult
from .iflow import IFlowBackend
from .qwen import QwenBackend

__all__ = ["AIBackend", "AIResult", "IFlowBackend", "QwenBackend"]
