"""FastAPI 应用"""
from typing import Tuple

from fastapi import FastAPI, Query, Request, Response
from loguru import logger

from ..ai.manager import AISessionManager
from ..wechat.client import WeChatClient
from ..wechat.crypto import WeChatCrypto
from ..wechat.handler import WeChatMessageHandler


def parse_command(content: str) -> Tuple[str, str]:
    """解析用户命令，返回 (command, command_type)"""
    content = content.strip()
    if content == "/help":
        return ("", "help")
    if content == "/new":
        return ("", "new")
    if content == "/status":
        return ("", "status")
    if content.startswith("/run "):
        return (content[5:].strip(), "run")
    if content and not content.startswith("/"):
        return (content, "run")
    return ("", "unknown")


def get_help_text() -> str:
    """获取帮助文本"""
    return """iFlow 企业微信助手

支持连续对话，自动保持上下文

可用命令：
- 直接发送消息：执行 iFlow 命令（自动恢复上次会话）
- /run <命令>：执行 iFlow 命令
- /new：开始新会话（清除上下文）
- /status：查看服务状态
- /help：显示此帮助

提示：默认会自动恢复最近的会话，保持对话连续性。如需重新开始，请使用 /new 命令。

示例：
帮我写一个 Python 爬虫脚本
再帮我添加异常处理
继续完善这个脚本
"""


def format_status_text(status: dict) -> str:
    """格式化状态文本"""
    if "error" in status:
        return f"错误：{status['error']}"
    lines = ["iFlow 服务状态", ""]
    if status.get("has_session"):
        session_id = status.get("session_id", "未知")
        iflow_id = status.get("iflow_session_id", "未知")
        lines.append(f"当前会话：{session_id}")
        if iflow_id:
            lines.append(f"iFlow Session: {iflow_id}")
    else:
        lines.append("当前会话：无活跃会话")
    return "\n".join(lines)


def create_app(
    wechat_client: WeChatClient,
    wechat_handler: WeChatMessageHandler,
    ai_manager: AISessionManager,
) -> FastAPI:
    """创建 FastAPI 应用"""
    app = FastAPI(title="WeChat AI Assistant")

    @app.get("/health")
    async def health_check():
        return {"status": "ok"}

    @app.get("/wechat/callback")
    async def wechat_callback_get(
        msg_signature: str = Query(...),
        timestamp: str = Query(...),
        nonce: str = Query(...),
        echostr: str = Query(...),
    ) -> Response:
        """企业微信回调 URL 验证（GET）"""
        logger.info("[HTTP] 收到回调验证请求")
        decrypted = wechat_handler.verify_callback(msg_signature, timestamp, nonce, echostr)
        if decrypted:
            logger.info("[HTTP] 回调验证成功，返回 echostr")
            return Response(content=decrypted, media_type="text/plain")
        logger.error("[HTTP] 回调验证失败")
        return Response(content="验证失败", status_code=403)

    @app.post("/wechat/callback")
    async def wechat_callback_post(
        request: Request,
        msg_signature: str = Query(...),
        timestamp: str = Query(...),
        nonce: str = Query(...),
    ) -> Response:
        """企业微信消息回调（POST）"""
        logger.info("[HTTP] 收到消息回调")
        body = await request.body()
        encrypt = body.decode("utf-8")
        message = wechat_handler.parse_message(msg_signature, timestamp, nonce, encrypt)

        if not message:
            logger.warning("[HTTP] 消息解析失败，忽略")
            return Response(content="success", media_type="text/plain")

        if message.msg_type != "text":
            return Response(content="success", media_type="text/plain")

        user_id = message.from_user
        content = message.content.strip()
        logger.info(f"[HTTP] 处理用户 {user_id} 的消息：{content}")

        command, command_type = parse_command(content)

        if command_type == "help":
            await wechat_client.send_text_message(user_id, get_help_text())

        elif command_type == "new":
            await ai_manager.new_session(user_id)
            await wechat_client.send_text_message(user_id, "✅ 已开始新会话，下次对话将清除之前的上下文")

        elif command_type == "status":
            status = await ai_manager.get_status(user_id)
            await wechat_client.send_text_message(user_id, format_status_text(status))

        elif command_type == "run":
            await wechat_client.send_text_message(user_id, f"⏳ 正在执行：{command}")
            result = await ai_manager.execute_command(user_id, command)

            if result.success:
                output = result.output
                if len(output) <= 4000:
                    await wechat_client.send_text_message(user_id, f"✅ {output}")
                else:
                    chunks = [output[i:i+4000] for i in range(0, len(output), 4000)]
                    for i, chunk in enumerate(chunks):
                        await wechat_client.send_text_message(user_id, f"[{i+1}/{len(chunks)}] {chunk}")
            else:
                error_msg = result.error or result.output
                await wechat_client.send_text_message(user_id, f"❌ {error_msg}")

        else:
            await wechat_client.send_text_message(user_id, "无法识别的命令，发送 /help 查看帮助")

        return Response(content="success", media_type="text/plain")

    return app
