"""
企业微信模块 - 合并加解密、客户端、消息处理
"""
import base64
import hashlib
import os
import struct
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import httpx
import xmltodict
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from loguru import logger


# ============================================================================
# 加解密
# ============================================================================

class WeChatCrypto:
    """企业微信消息加解密"""

    def __init__(self, token: str, encoding_aes_key: str, corp_id: str):
        self.token = token
        self.corp_id = corp_id
        self.aes_key = base64.b64decode(encoding_aes_key + "=" * (4 - len(encoding_aes_key) % 4))

    def generate_signature(self, timestamp: str, nonce: str, echostr: str) -> str:
        data = sorted([self.token, timestamp, nonce, echostr])
        return hashlib.sha1("".join(data).encode()).hexdigest()

    def verify_signature(self, signature: str, timestamp: str, nonce: str, echostr: str) -> bool:
        return signature == self.generate_signature(timestamp, nonce, echostr)

    def decrypt(self, encrypted_text: str) -> Tuple[str, str]:
        encrypted = base64.b64decode(encrypted_text)
        iv = self.aes_key[:16]
        cipher = Cipher(algorithms.AES(self.aes_key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted = decryptor.update(encrypted) + decryptor.finalize()

        pad_len = decrypted[-1]
        decrypted = decrypted[:-pad_len]

        msg_len = struct.unpack(">I", decrypted[16:20])[0]
        message = decrypted[20:20 + msg_len]
        corp_id_len = struct.unpack(">I", decrypted[20 + msg_len:20 + msg_len + 4])[0]
        corp_id = decrypted[20 + msg_len + 4:20 + msg_len + 4 + corp_id_len].decode()

        return corp_id, message.decode()


# ============================================================================
# API 客户端
# ============================================================================

class WeChatClient:
    """企业微信 API 客户端"""

    def __init__(self, corp_id: str, agent_id: int, secret: str):
        self.corp_id = corp_id
        self.agent_id = agent_id
        self.secret = secret
        self._access_token: Optional[str] = None
        self._token_expire_time: float = 0
        self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        await self._client.aclose()

    async def get_access_token(self) -> str:
        if self._access_token and time.time() < self._token_expire_time:
            return self._access_token

        response = await self._client.get(
            "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
            params={"corpid": self.corp_id, "corpsecret": self.secret},
        )
        response.raise_for_status()
        data = response.json()

        if data.get("errcode") == 0:
            self._access_token = data["access_token"]
            self._token_expire_time = time.time() + data["expires_in"] - 300
            logger.info("[WeChat] 获取 access_token 成功")
            return self._access_token
        else:
            raise RuntimeError(f"获取 token 失败：{data.get('errmsg')}")

    async def send_text_message(self, user_id: str, content: str, prefix: str = "") -> int:
        """
        发送文本消息（自动分片，不超过 2048 字节）
        
        Args:
            user_id: 接收者
            content: 消息内容
            prefix: 第一条消息的前缀（如 "✅ "），分片消息自动添加 [2/3] 前缀
            
        Returns:
            发送的消息条数
        """
        chunks = self._split_message(content)
        
        for i, chunk in enumerate(chunks):
            msg = f"{prefix}{chunk}" if i == 0 else f"[{i+1}/{len(chunks)}] {chunk}"
            await self._send_single_message(user_id, msg)
        
        return len(chunks)

    async def _send_single_message(self, user_id: str, content: str) -> bool:
        """发送单条消息（内部方法）"""
        token = await self.get_access_token()

        try:
            response = await self._client.post(
                "https://qyapi.weixin.qq.com/cgi-bin/message/send",
                params={"access_token": token},
                json={
                    "touser": user_id,
                    "msgtype": "text",
                    "agentid": self.agent_id,
                    "text": {"content": content},
                    "safe": 0,
                },
            )
            response.raise_for_status()
            data = response.json()

            if data.get("errcode") == 0:
                logger.info(f"[WeChat] 消息发送成功 -> {user_id}")
                return True
            else:
                logger.error(f"[WeChat] 消息发送失败：{data.get('errmsg')}")
                return False
        except Exception as e:
            logger.error(f"[WeChat] 发送消息异常：{e}")
            return False

    def _split_message(self, content: str, max_bytes: int = 1500) -> list:
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
            chunk_bytes = encoded[start:start + max_bytes]
            
            try:
                chunk = chunk_bytes.decode('utf-8')
                chunks.append(chunk)
                start += max_bytes
            except UnicodeDecodeError:
                for i in range(len(chunk_bytes) - 1, 0, -1):
                    try:
                        chunk = chunk_bytes[:i].decode('utf-8')
                        chunks.append(chunk)
                        start += i
                        break
                    except UnicodeDecodeError:
                        continue
        
        return chunks


# ============================================================================
# 消息处理
# ============================================================================

@dataclass
class WeChatMessage:
    """企业微信消息"""
    from_user: str
    content: str
    msg_type: str
    agent_id: str
    create_time: int


class WeChatMessageHandler:
    """企业微信消息处理器"""

    def __init__(self, crypto: WeChatCrypto):
        self.crypto = crypto

    def verify_callback(self, msg_signature: str, timestamp: str, nonce: str, echostr: str) -> Optional[str]:
        if not self.crypto.verify_signature(msg_signature, timestamp, nonce, echostr):
            logger.warning("[WeChat] 签名验证失败")
            return None
        _, decrypted = self.crypto.decrypt(echostr)
        logger.info("[WeChat] 回调 URL 验证成功")
        return decrypted

    def parse_message(self, msg_signature: str, timestamp: str, nonce: str, encrypt: str) -> Optional[WeChatMessage]:
        expected_sig = self.crypto.generate_signature(timestamp, nonce, encrypt)
        if expected_sig != msg_signature:
            logger.warning("[WeChat] 签名验证失败")
            return None

        try:
            _, decrypted_xml = self.crypto.decrypt(encrypt)
            data = xmltodict.parse(decrypted_xml)
            xml_dict = data.get("xml", {})
        except Exception as e:
            logger.error(f"[WeChat] 解密或解析失败：{e}")
            return None

        msg_type = xml_dict.get("MsgType", "")
        if msg_type != "text":
            return None

        from_user = xml_dict.get("FromUserName", "")
        content = xml_dict.get("Content", "")
        agent_id = xml_dict.get("AgentID", "")
        create_time = int(xml_dict.get("CreateTime", 0))

        if not from_user or not content:
            logger.warning("[WeChat] 消息字段不完整")
            return None

        logger.info(f"[WeChat] 收到消息：{from_user} -> {content[:50]}...")
        return WeChatMessage(from_user, content, msg_type, agent_id, create_time)
