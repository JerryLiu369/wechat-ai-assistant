"""企业微信 API 客户端"""
import time
from typing import Optional

import httpx
from loguru import logger


class WeChatClient:
    """
    企业微信 API 客户端抽象

    负责：
    - Access Token 获取与缓存
    - 消息发送
    """

    def __init__(self, corp_id: str, agent_id: int, secret: str):
        """
        初始化客户端

        Args:
            corp_id: 企业 ID
            agent_id: 应用 AgentId
            secret: 应用 Secret
        """
        self.corp_id = corp_id
        self.agent_id = agent_id
        self.secret = secret

        self._access_token: Optional[str] = None
        self._token_expire_time: float = 0

        self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        """关闭 HTTP 客户端"""
        await self._client.aclose()

    async def get_access_token(self) -> str:
        """
        获取 Access Token（带缓存）

        Returns:
            Access Token
        """
        # 检查缓存是否有效（提前 5 分钟过期）
        if self._access_token and time.time() < self._token_expire_time:
            return self._access_token

        try:
            response = await self._client.get(
                "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
                params={
                    "corpid": self.corp_id,
                    "corpsecret": self.secret,
                },
            )
            response.raise_for_status()
            data = response.json()

            if data.get("errcode") == 0:
                self._access_token = data["access_token"]
                # 提前 5 分钟过期
                self._token_expire_time = time.time() + data["expires_in"] - 300
                logger.info("[WeChat] 获取 access_token 成功")
                return self._access_token
            else:
                raise RuntimeError(f"获取 token 失败：{data.get('errmsg')}")

        except Exception as e:
            logger.error(f"[WeChat] 获取 access_token 失败：{e}")
            raise

    async def send_text_message(self, user_id: str, content: str) -> bool:
        """
        发送文本消息

        Args:
            user_id: 接收消息的用户 ID
            content: 消息内容

        Returns:
            是否发送成功
        """
        token = await self.get_access_token()

        try:
            response = await self._client.post(
                f"https://qyapi.weixin.qq.com/cgi-bin/message/send",
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
