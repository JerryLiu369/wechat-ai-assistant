"""FastAPI 应用"""
from fastapi import FastAPI, Query, Request, Response
from loguru import logger


def get_help_text() -> str:
    """获取帮助文本"""
    return """AI 企业微信助手

支持连续对话，自动保持上下文

可用命令：
- 直接发送消息：执行 AI 命令（自动恢复上次会话）
- /run <命令>：执行 AI 命令
- /new：开始新会话（清除上下文）
- /help：显示此帮助

示例：
帮我写一个 Python 爬虫脚本
再帮我添加异常处理
继续完善这个脚本
"""


async def handle_ai_command(wechat_client, qwen, user_id: str, command: str):
    """
    处理 AI 命令（带超时处理和进度汇报）
    
    Args:
        wechat_client: 微信客户端
        qwen: Qwen 执行器
        user_id: 用户 ID
        command: 命令内容
    """
    await wechat_client.send_text_message(user_id, f"⏳ 正在执行：{command}")
    success, output, status = await qwen.execute_with_progress(user_id, command, wechat_client)

    if status == "timeout":
        await wechat_client.send_text_message(user_id, "⚠️ 执行超时（>10 分钟），已终止任务")
        await wechat_client.send_text_message(user_id, "📝 正在请求总结...")
        
        summary_command = "上次执行超时，任务被终止了。请快速总结一下目前执行到哪一步了，已完成哪些工作，还有什么没做的？要求简洁明了。"
        summary_success, summary_output, _ = await qwen.execute(user_id, summary_command)
        
        if summary_success:
            await wechat_client.send_text_message(user_id, summary_output, "📋 总结：")
        else:
            await wechat_client.send_text_message(user_id, "❌ 总结失败")
    elif success:
        await wechat_client.send_text_message(user_id, output, "✅ ")
    else:
        await wechat_client.send_text_message(user_id, output, "❌ ")


def create_app(wechat_client, wechat_handler, qwen) -> FastAPI:
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
            logger.info("[HTTP] 回调验证成功")
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

        try:
            import xmltodict
            data = xmltodict.parse(body.decode("utf-8"))
            encrypt = data.get("xml", {}).get("Encrypt", "")
            if not encrypt:
                logger.warning("[HTTP] 消息体中未找到 Encrypt 字段")
                return Response(content="success", media_type="text/plain")
        except Exception as e:
            logger.error(f"[HTTP] XML 解析失败：{e}")
            return Response(content="success", media_type="text/plain")

        message = wechat_handler.parse_message(msg_signature, timestamp, nonce, encrypt)

        if not message:
            logger.warning("[HTTP] 消息解析失败，忽略")
            return Response(content="success", media_type="text/plain")

        if message.msg_type != "text":
            return Response(content="success", media_type="text/plain")

        user_id = message.from_user
        content = message.content.strip()
        logger.info(f"[HTTP] 用户 {user_id} 消息：{content}")

        # 解析命令
        if content == "/help":
            await wechat_client.send_text_message(user_id, get_help_text())

        elif content == "/new":
            await qwen.reset_session(user_id)
            await wechat_client.send_text_message(user_id, "✅ 已开始新会话，下次对话将清除之前的上下文")

        elif content.startswith("/run "):
            command = content[5:].strip()
            await handle_ai_command(wechat_client, qwen, user_id, command)

        elif content and not content.startswith("/"):
            await handle_ai_command(wechat_client, qwen, user_id, content)

        else:
            await wechat_client.send_text_message(user_id, "无法识别的命令，发送 /help 查看帮助")

        return Response(content="success", media_type="text/plain")

    return app
