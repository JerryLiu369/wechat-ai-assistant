# WeChat AI Assistant - 架构文档

## 系统架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         企业微信客户端                                   │
│                    (用户发送消息 / 接收回复)                              │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ HTTPS 回调
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      FastAPI HTTP Server                                 │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  POST /wechat/callback                                            │  │
│  │  ├─ 解析加密消息                                                   │  │
│  │  ├─ 识别命令类型                                                   │  │
│  │  └─ 路由到对应处理函数                                             │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
                    ▼               ▼               ▼
        ┌───────────────┐  ┌───────────────┐  ┌───────────────┐
        │  /help 命令   │  │  /new 命令    │  │  /run 命令    │
        │  发送帮助文本  │  │  清空工作区   │  │  执行 Qwen    │
        └───────────────┘  └───────────────┘  └───────────────┘
                                                    │
                                                    ▼
                                    ┌───────────────────────────────┐
                                    │     QwenExecutor              │
                                    │  ┌─────────────────────────┐  │
                                    │  │ execute(user, cmd)      │  │
                                    │  │  ├─ 获取工作区          │  │
                                    │  │  ├─ 调用 qwen CLI       │  │
                                    │  │  └─ 返回结果            │  │
                                    │  └─────────────────────────┘  │
                                    └───────────────────────────────┘
                                                    │
                                                    ▼
                                    ┌───────────────────────────────┐
                                    │   文件系统 (工作区)            │
                                    │  ~/.wechat-ai-assistant/      │
                                    │    workspaces/                │
                                    │      ├── user_zhangsan/       │
                                    │      │   └── *.json (会话)    │
                                    │      └── user_lisi/           │
                                    │          └── *.json (会话)    │
                                    └───────────────────────────────┘
                                                    │
                                                    ▼
                                    ┌───────────────────────────────┐
                                    │     Qwen Code CLI             │
                                    │  qwen --continue --yolo cmd   │
                                    │  (cwd=用户工作区)             │
                                    └───────────────────────────────┘
```

## 核心组件

### 1. src/main.py - 主入口

**职责**: 配置加载、日志设置、组件初始化、启动服务

**代码结构**:
```python
# 配置
class Settings(BaseSettings):
    corp_id: str
    agent_id: int
    ...

# 日志
logger.remove()
logger.add(...)

# 主程序
async def main():
    # 验证配置
    # 初始化 WeChatClient, WeChatCrypto, WeChatMessageHandler
    # 初始化 QwenExecutor
    # 创建 FastAPI 应用
    # 启动 uvicorn
```

### 2. src/wechat.py - 企业微信模块（~200 行）

**职责**: 加解密、API 调用、消息解析

**三个类**:
- `WeChatCrypto` - AES 加解密、签名验证
- `WeChatClient` - Access Token 管理、发送消息
- `WeChatMessageHandler` - 消息解密、XML 解析

### 3. src/qwen.py - Qwen 执行器（~85 行）

**职责**: 执行 Qwen Code 命令、管理工作区

**核心方法**:
```python
class QwenExecutor:
    async def execute(user_id, command) -> (bool, str)
    async def reset_session(user_id)
```

### 4. src/server.py - FastAPI 应用（~120 行）

**职责**: HTTP 路由、命令分发

**路由**:
- `GET /wechat/callback` - URL 验证
- `POST /wechat/callback` - 消息处理
- `GET /health` - 健康检查

## 数据流

### 用户发送消息的完整流程

```
1. 用户在企业微信发送："帮我写个爬虫"

2. 企业微信服务器
   └─→ HTTPS POST https://你的域名/wechat/callback
       {
         "msg_signature": "...",
         "timestamp": "...",
         "nonce": "...",
         "encrypt": "<xml>...</xml>"  // AES 加密
       }

3. FastAPI 接收
   ├─→ WeChatCrypto.decrypt() 解密
   ├─→ WeChatMessageHandler.parse_message() 解析
   └─→ 提取：from_user="zhangsan", content="帮我写个爬虫"

4. 命令识别
   └─→ 不是 /help, /new, /status
   └─→ 视为直接命令

5. QwenExecutor.execute()
   ├─→ workspace = ~/.wechat-ai-assistant/workspaces/zhangsan/
   ├─→ 创建 subprocess:
   │   qwen --continue --yolo "帮我写个爬虫"
   │   cwd=~/.wechat-ai-assistant/workspaces/zhangsan/
   └─→ 等待 120 秒或完成

6. Qwen Code 执行
   ├─→ 自动加载 workspaces/zhangsan/ 内的 session-*.json
   ├─→ 执行命令
   └─→ 更新 session 文件

7. 回复用户
   └─→ WeChatClient.send_text_message("zhangsan", "✅ 爬虫代码...")
```

## 会话隔离机制

```
用户 A (zhangsan)                用户 B (lisi)
     │                               │
     ▼                               ▼
~/.wechat-ai-assistant/
  workspaces/
    ├── zhangsan/                   # 用户 A 的工作区
    │   ├── session-abc.json        # Qwen 自动生成的会话文件
    │   └── last_output.txt
    │
    └── lisi/                       # 用户 B 的工作区
        └── session-xyz.json

关键：qwen --continue 在当前工作目录内查找 session 文件
结果：用户 A 和 B 的对话历史完全隔离
```

## 设计原则

### 1. 简单优先
- ❌ 无抽象基类
- ❌ 无多后端支持
- ❌ 无会话管理器
- ✅ 一个 QwenExecutor 搞定

### 2. 约定优于配置
- ❌ 无需配置后端类型
- ❌ 无需配置工作区路径
- ✅ 默认 `~/.wechat-ai-assistant/workspaces/`

### 3. 用户隔离
- ✅ 每个用户独立文件夹
- ✅ Qwen 自动管理会话文件
- ✅ `/new` 命令清空重置

### 4. 异步非阻塞
- ✅ FastAPI 异步处理
- ✅ asyncio 子进程调用
- ✅ 120 秒超时保护

## 代码统计

| 文件 | 行数 | 职责 |
|------|------|------|
| src/main.py | ~100 | 配置 + 日志 + 启动 |
| src/wechat.py | ~200 | 加解密 +API+ 消息处理 |
| src/qwen.py | ~85 | Qwen 执行 |
| src/server.py | ~120 | HTTP 路由 |
| **总计** | **~505 行** | **4 个文件** | |

## 扩展指南

### 如果要添加新的 AI 后端

直接在 `src/ai/` 下创建新文件，例如 `src/ai/cursor.py`:

```python
class CursorExecutor:
    async def execute(self, user_id: str, command: str) -> tuple[bool, str]:
        workspace = Path.home() / ".cursor-workspaces" / user_id
        # 调用 cursor CLI
```

然后在 `main.py` 和 `app.py` 中替换即可。

### 如果要添加新的命令

在 `app.py` 的 `wechat_callback_post` 中添加分支：

```python
elif content == "/mycommand":
    # 你的逻辑
    await wechat_client.send_text_message(user_id, "结果")
```

## 总结

**架构特点**:
- 简单直接，无过度设计
- 文件系统 = 会话数据库
- 用户隔离天然安全
- 易于理解和维护

**适用场景**:
- ✅ 个人或小团队使用
- ✅ 快速迭代开发
- ✅ 需要连续对话

**不适用场景**:
- ❌ 需要支持多个 AI 后端
- ❌ 需要复杂的会话管理
- ❌ 需要企业级权限控制
