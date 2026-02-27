"""
企业微信消息加解密

参考企业微信官方文档：
https://developer.work.weixin.qq.com/document/path/90937
"""
import base64
import hashlib
import os
import struct
from typing import Tuple

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend


class WeChatCrypto:
    """企业微信消息加解密工具"""

    def __init__(self, token: str, encoding_aes_key: str, corp_id: str):
        """
        初始化加解密工具

        Args:
            token: 企业微信后台设置的 Token
            encoding_aes_key: 企业微信后台生成的 EncodingAESKey
            corp_id: 企业 ID
        """
        self.token = token
        self.corp_id = corp_id
        # AES Key 是 Base64 编码的 256 位密钥
        self.aes_key = base64.b64decode(encoding_aes_key + "=" * (4 - len(encoding_aes_key) % 4))

    def generate_signature(self, timestamp: str, nonce: str, echostr: str) -> str:
        """
        生成签名（用于验证回调 URL）

        Args:
            timestamp: 时间戳
            nonce: 随机数
            echostr: 随机字符串

        Returns:
            SHA1 签名
        """
        data = [self.token, timestamp, nonce, echostr]
        data.sort()
        return hashlib.sha1("".join(data).encode()).hexdigest()

    def verify_signature(self, signature: str, timestamp: str, nonce: str, echostr: str) -> bool:
        """
        验证签名

        Args:
            signature: 企业微信传来的签名
            timestamp: 时间戳
            nonce: 随机数
            echostr: 随机字符串

        Returns:
            签名是否有效
        """
        expected = self.generate_signature(timestamp, nonce, echostr)
        return signature == expected

    def decrypt(self, encrypted_text: str) -> Tuple[str, str]:
        """
        解密消息

        Args:
            encrypted_text: Base64 编码的加密消息

        Returns:
            (corp_id, content) 元组
        """
        # Base64 解码
        encrypted = base64.b64decode(encrypted_text)

        # AES 解密（CBC 模式，PKCS7 填充）
        iv = self.aes_key[:16]
        cipher = Cipher(algorithms.AES(self.aes_key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted = decryptor.update(encrypted) + decryptor.finalize()

        # 去除 PKCS7 填充
        pad_len = decrypted[-1]
        decrypted = decrypted[:-pad_len]

        # 解析数据结构：
        # 16 字节随机数 + 4 字节消息长度 + 消息内容 + 4 字节 corp_id 长度 + corp_id
        random_prefix = decrypted[:16]
        length_bytes = decrypted[16:20]
        msg_len = struct.unpack(">I", length_bytes)[0]
        message = decrypted[20:20 + msg_len]
        corp_id_len_bytes = decrypted[20 + msg_len:20 + msg_len + 4]
        corp_id_len = struct.unpack(">I", corp_id_len_bytes)[0]
        corp_id = decrypted[20 + msg_len + 4:20 + msg_len + 4 + corp_id_len].decode()

        return corp_id, message.decode()

    def encrypt(self, message: str) -> str:
        """
        加密消息

        Args:
            message: 要加密的消息内容

        Returns:
            Base64 编码的加密消息
        """
        # 生成 16 字节随机数
        random_bytes = os.urandom(16)

        # 构建数据结构
        msg_bytes = message.encode()
        msg_len = struct.pack(">I", len(msg_bytes))
        corp_id_bytes = self.corp_id.encode()
        corp_id_len = struct.pack(">I", len(corp_id_bytes))

        # 拼接：随机数 + 长度 + 消息 + corp_id 长度 + corp_id
        data = random_bytes + msg_len + msg_bytes + corp_id_len + corp_id_bytes

        # PKCS7 填充
        pad_len = 32 - (len(data) % 32)
        data += bytes([pad_len]) * pad_len

        # AES 加密（CBC 模式）
        iv = self.aes_key[:16]
        cipher = Cipher(algorithms.AES(self.aes_key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        encrypted = encryptor.update(data) + encryptor.finalize()

        return base64.b64encode(encrypted).decode()
