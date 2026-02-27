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


def split_message_by_bytes(content: str, max_bytes: int = 1500) -> list:
    """
    按字节数分割消息（企业微信限制 2048 字节）
    
    Args:
        content: 消息内容
        max_bytes: 每片最大字节数（默认 1500，留余量）
        
    Returns:
        分割后的消息列表
    """
    encoded = content.encode('utf-8')
    
    if len(encoded) <= max_bytes:
        return [content]
    
    chunks = []
    start = 0
    
    while start < len(encoded):
        # 截取分片
        chunk_bytes = encoded[start:start + max_bytes]
        
        # 尝试解码，如果截断在中文中间会失败
        try:
            chunk = chunk_bytes.decode('utf-8')
            chunks.append(chunk)
            start += max_bytes
        except UnicodeDecodeError:
            # 截断位置不对，减少字节数直到能正确解码
            for i in range(len(chunk_bytes) - 1, 0, -1):
                try:
                    chunk = chunk_bytes[:i].decode('utf-8')
                    chunks.append(chunk)
                    start += i
                    break
                except UnicodeDecodeError:
                    continue
    
    return chunks


async def send_split_message(wechat_client, user_id: str, content: str):
    """发送分片消息"""
    chunks = split_message_by_bytes(content)
    
    if len(chunks) == 1:
        await wechat_client.send_text_message(user_id, f"✅ {content}")
    else:
        for i, chunk in enumerate(chunks):
            await wechat_client.send_text_message(
                user_id,
                f"[{i+1}/{len(chunks)}] {chunk}" if i > 0 else f"✅ {chunk}"
            )


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
            await wechat_client.send_text_message(user_id, f"⏳ 正在执行：{command}")
            success, output = await qwen.execute(user_id, command)

            if success:
                await send_split_message(wechat_client, user_id, output)
            else:
                await wechat_client.send_text_message(user_id, f"❌ {output}")

        elif content and not content.startswith("/"):
            await wechat_client.send_text_message(user_id, f"⏳ 正在执行：{content}")
            success, output = await qwen.execute(user_id, content)

            if success:
                await send_split_message(wechat_client, user_id, output)
            else:
                await wechat_client.send_text_message(user_id, f"❌ {output}")

        else:
            await wechat_client.send_text_message(user_id, "无法识别的命令，发送 /help 查看帮助")

        return Response(content="success", media_type="text/plain")

    return app
