"""企业微信消息处理器"""
from dataclasses import dataclass
from typing import Optional

import xmltodict
from loguru import logger

from .crypto import WeChatCrypto


@dataclass
class WeChatMessage:
    """企业微信消息"""

    from_user: str  # 发送者 UserID
    content: str  # 消息内容
    msg_type: str  # 消息类型
    agent_id: str  # 应用 ID
    create_time: int  # 消息创建时间


class WeChatMessageHandler:
    """
    企业微信消息处理器

    负责：
    - 回调 URL 验证（echostr）
    - 消息解密与解析
    - 签名验证
    """

    def __init__(self, crypto: WeChatCrypto):
        """
        初始化消息处理器

        Args:
            crypto: 加解密工具
        """
        self.crypto = crypto

    def verify_callback(
        self,
        msg_signature: str,
        timestamp: str,
        nonce: str,
        echostr: str,
    ) -> Optional[str]:
        """
        验证回调 URL（GET 请求）

        Args:
            msg_signature: 企业微信签名
            timestamp: 时间戳
            nonce: 随机数
            echostr: 加密的随机字符串

        Returns:
            解密后的 echostr（验证失败返回 None）
        """
        # 验证签名
        if not self.crypto.verify_signature(msg_signature, timestamp, nonce, echostr):
            logger.warning("[WeChat] 签名验证失败")
            return None

        # 解密 echostr 并原样返回
        _, decrypted = self.crypto.decrypt(echostr)
        logger.info("[WeChat] 回调 URL 验证成功")
        return decrypted

    def parse_message(
        self,
        msg_signature: str,
        timestamp: str,
        nonce: str,
        encrypt: str,
    ) -> Optional[WeChatMessage]:
        """
        解析消息（POST 请求）

        Args:
            msg_signature: 企业微信签名
            timestamp: 时间戳
            nonce: 随机数
            encrypt: 加密的消息内容

        Returns:
            解析后的消息（解析失败返回 None）
        """
        # 验证签名
        expected_sig = self.crypto.generate_signature(timestamp, nonce, encrypt)
        if expected_sig != msg_signature:
            logger.warning("[WeChat] 签名验证失败")
            return None

        # 解密消息
        try:
            _, decrypted_xml = self.crypto.decrypt(encrypt)
        except Exception as e:
            logger.error(f"[WeChat] 解密失败：{e}")
            return None

        # 解析 XML
        try:
            data = xmltodict.parse(decrypted_xml)
            xml_dict = data.get("xml", {})
        except Exception as e:
            logger.error(f"[WeChat] XML 解析失败：{e}")
            return None

        # 提取消息字段
        msg_type = xml_dict.get("MsgType", "")
        if msg_type != "text":
            # 忽略非文本消息
            return None

        from_user = xml_dict.get("FromUserName", "")
        content = xml_dict.get("Content", "")
        agent_id = xml_dict.get("AgentID", "")
        create_time = int(xml_dict.get("CreateTime", 0))

        if not from_user or not content:
            logger.warning("[WeChat] 消息字段不完整")
            return None

        message = WeChatMessage(
            from_user=from_user,
            content=content,
            msg_type=msg_type,
            agent_id=agent_id,
            create_time=create_time,
        )

        logger.info(f"[WeChat] 收到消息：{from_user} -> {content[:50]}...")
        return message
