# WeChat AI Assistant

通过企业微信远程控制 AI 编程助手，支持连续对话和多用户隔离。

## 致谢

本项目灵感来源于 [iflow-wechat-assistant](https://github.com/wx7in8/iflow-wechat-assistant) by @wx7in8，感谢原作者的开源贡献！

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入企业微信配置：

```env
# 企业微信配置（必填）
CORP_ID=你的企业 ID
AGENT_ID=你的应用 AgentId
SECRET=你的应用 Secret

# 消息接收配置（必填）
RECEIVE_TOKEN=你设置的 Token
RECEIVE_ENCODING_AES_KEY=随机获取的 EncodingAESKey

# 服务端口（可选，默认 3000）
PORT=3000

# AI 后端配置（可选，默认 qwen）
AI_BACKEND=qwen
```

### 3. 启动服务

```bash
python main.py
```

## 功能特点

- **多用户支持** - 每个用户独立会话，消息回复给发送者
- **连续对话** - 自动保持会话上下文
- **模块化设计** - 易于扩展新的 AI 后端
- **纯文本消息** - 兼容所有微信客户端

## 可用命令

| 命令 | 说明 |
|------|------|
| 直接发送文本 | 执行 AI 命令（自动恢复会话） |
| `/help` | 显示帮助信息 |
| `/new` | 开始新会话（清除上下文） |
| `/status` | 查看服务状态 |

## 项目结构

```
wechat-ai-assistant/
├── src/
│   ├── config/         # 配置管理
│   ├── wechat/         # 企业微信 API
│   │   ├── crypto.py   # 消息加解密
│   │   ├── client.py   # API 客户端
│   │   └── handler.py  # 消息处理器
│   ├── ai/             # AI 后端
│   │   ├── base.py     # 抽象基类
│   │   ├── iflow.py    # iFlow 实现
│   │   ├── qwen.py     # Qwen Code 实现
│   │   └── manager.py  # 会话管理器
│   └── server/         # HTTP 服务
│       └── app.py      # FastAPI 应用
├── main.py             # 入口文件
├── requirements.txt    # Python 依赖
├── .env.example        # 配置模板
└── README.md           # 本文件
```

## 扩展 AI 后端

项目已支持 iFlow 和 Qwen Code，通过 `AI_BACKEND` 环境变量切换。

如需添加其他后端，实现 `AIBackend` 抽象基类即可：

```python
from src.ai.base import AIBackend, AIResult

class QwenBackend(AIBackend):
    async def execute(self, command: str, session_id: str) -> AIResult:
        # 实现 Qwen Code 调用逻辑
        pass
    
    async def create_session(self, user_id: str) -> str:
        # 创建会话逻辑
        pass
    
    async def get_session_info(self, session_id: str) -> dict:
        # 获取会话信息逻辑
        pass
```

然后在 `main.py` 中注册即可。

## 企业微信配置说明

1. **获取企业 ID** - 企业微信管理后台 → 我的企业
2. **创建自建应用** - 应用管理 → 自建 → 创建应用
3. **获取 AgentId 和 Secret** - 应用详情页面
4. **配置消息接收** - 应用 → 接收消息 → 设置 API 接收
   - URL: `https://你的域名/wechat/callback`
   - Token: 自定义
   - EncodingAESKey: 随机生成

## 内网穿透

开发测试时可使用 Cloudflare Tunnel：

```bash
cloudflared tunnel --url http://localhost:3000
```
