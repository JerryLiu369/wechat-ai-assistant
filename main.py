"""
WeChat AI Assistant - 基于 Qwen Code 的企业微信 AI 助手
"""
import asyncio
import sys
from functools import lru_cache
from pathlib import Path

import uvicorn
from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict


# ============================================================================
# 配置
# ============================================================================

class Settings(BaseSettings):
    """应用配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    corp_id: str
    agent_id: int
    secret: str
    receive_token: str
    receive_encoding_aes_key: str
    port: int = 3000

    @property
    def is_valid(self) -> bool:
        required = [self.corp_id, self.agent_id, self.secret,
                    self.receive_token, self.receive_encoding_aes_key]
        return all(bool(f) for f in required)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


# ============================================================================
# 日志配置
# ============================================================================

logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    level="INFO",
)


# ============================================================================
# 主程序
# ============================================================================

async def main():
    """主函数"""
    logger.info("=" * 50)
    logger.info("WeChat AI Assistant 启动中...")
    logger.info("=" * 50)

    if not settings.is_valid:
        logger.error("配置不完整，请检查 .env 文件")
        sys.exit(1)

    logger.info("配置验证通过 ✓")

    # 导入模块
    from src.wechat import WeChatClient, WeChatCrypto, WeChatMessageHandler
    from src.qwen import QwenExecutor
    from src.server import create_app

    # 初始化组件
    logger.info("初始化企业微信组件...")
    wechat_client = WeChatClient(settings.corp_id, settings.agent_id, settings.secret)
    wechat_crypto = WeChatCrypto(settings.receive_token, settings.receive_encoding_aes_key, settings.corp_id)
    wechat_handler = WeChatMessageHandler(wechat_crypto)

    logger.info("初始化 Qwen Executor...")
    qwen = QwenExecutor()

    # 创建 FastAPI 应用
    app = create_app(wechat_client, wechat_handler, qwen)

    # 测试企业微信连接
    logger.info("测试企业微信连接...")
    try:
        await wechat_client.get_access_token()
        logger.info("企业微信连接成功 ✓")
    except Exception as e:
        logger.error(f"企业微信连接失败：{e}")
        sys.exit(1)

    # 启动服务
    logger.info(f"启动 HTTP 服务，端口：{settings.port}")
    config = uvicorn.Config(app, host="0.0.0.0", port=settings.port, log_config=None)
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
