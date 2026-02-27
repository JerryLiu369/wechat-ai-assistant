"""
WeChat AI Assistant - 入口文件

通过企业微信远程控制 AI 编程助手
"""
import asyncio
import sys

import uvicorn
from loguru import logger

from src.config import settings
from src.ai.manager import AISessionManager
from src.ai.qwen import QwenBackend
from src.wechat.client import WeChatClient
from src.wechat.crypto import WeChatCrypto
from src.wechat.handler import WeChatMessageHandler
from src.server.app import create_app


# 配置日志
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    level="INFO",
)


async def main():
    """主函数"""
    logger.info("=" * 50)
    logger.info("WeChat AI Assistant 启动中...")
    logger.info("=" * 50)

    # 验证配置
    if not settings.is_valid:
        logger.error("配置不完整，请检查 .env 文件")
        sys.exit(1)

    logger.info("配置验证通过 ✓")

    # 初始化企业微信组件
    logger.info("初始化企业微信组件...")
    wechat_client = WeChatClient(
        corp_id=settings.corp_id,
        agent_id=settings.agent_id,
        secret=settings.secret,
    )

    wechat_crypto = WeChatCrypto(
        token=settings.receive_token,
        encoding_aes_key=settings.receive_encoding_aes_key,
        corp_id=settings.corp_id,
    )

    wechat_handler = WeChatMessageHandler(wechat_crypto)

    # 初始化 AI 管理器
    logger.info("初始化 AI 管理器...")
    ai_manager = AISessionManager(default_backend=settings.ai_backend)

    # 注册 AI 后端
    if settings.ai_backend == "qwen":
        from pathlib import Path
        workspace_base = Path(settings.workspace) if settings.workspace else None
        ai_manager.register_backend(QwenBackend(workspace_base=workspace_base))
        logger.info("AI 后端：Qwen ✓")
    else:
        logger.warning(f"未知的 AI 后端：{settings.ai_backend}，默认使用 qwen")
        ai_manager.register_backend(QwenBackend())

    # 创建 FastAPI 应用
    app = create_app(wechat_client, wechat_handler, ai_manager)

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
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=settings.port,
        log_config=None,
    )
    server = uvicorn.Server(config)

    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
