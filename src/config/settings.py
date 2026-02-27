"""应用配置管理"""
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 企业微信配置
    corp_id: str
    agent_id: int
    secret: str

    # 消息接收配置
    receive_token: str
    receive_encoding_aes_key: str

    # 服务配置
    port: int = 3000

    # AI 后端配置
    ai_backend: str = "qwen"

    # 工作区目录
    workspace: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        """验证配置是否完整"""
        required = [self.corp_id, self.agent_id, self.secret,
                    self.receive_token, self.receive_encoding_aes_key]
        return all(bool(f) for f in required)


@lru_cache
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


settings = get_settings()
