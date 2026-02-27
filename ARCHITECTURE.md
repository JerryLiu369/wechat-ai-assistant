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

### 1. HTTP Server (`src/server/app.py`)

**职责**: 接收企业微信回调，路由命令

**核心逻辑**:
```python
@app.post("/wechat/callback")
async def wechat_callback_post():
    # 1. 解密消息
    message = wechat_handler.parse_message(...)
    
    # 2. 识别命令
    if content == "/help": ...
    elif content == "/new": ...
    elif content.startswith("/run "): ...
    else: # 直接执行
    
    # 3. 调用 QwenExecutor
    success, output = await qwen.execute(user_id, command)
    
    # 4. 回复用户
    await wechat_client.send_text_message(user_id, output)
```

### 2. QwenExecutor (`src/ai/qwen.py`)

**职责**: 执行 Qwen Code 命令，管理用户工作区

**核心方法**:
```python
class QwenExecutor:
    def __init__(self):
        self.workspace_base = Path.home() / ".wechat-ai-assistant" / "workspaces"
    
    async def execute(self, user_id: str, command: str) -> tuple[bool, str]:
        workspace = self._get_workspace(user_id)  # 获取用户工作区
        # 执行：qwen --continue --yolo <command>
        # 工作目录：workspace
```

**会话管理**:
- **一个用户 = 一个文件夹**
- `qwen --continue` 自动加载该文件夹内的会话历史
- `/new` 命令清空文件夹，开始新会话

### 3. WeChat 模块

#### 3.1 WeChatClient (`src/wechat/client.py`)

**职责**: 调用企业微信 API

```python
class WeChatClient:
    async def get_access_token(self) -> str:
        # 获取并缓存 token
        
    async def send_text_message(self, user_id: str, content: str) -> bool:
        # 发送文本消息
```

#### 3.2 WeChatCrypto (`src/wechat/crypto.py`)

**职责**: AES 加解密、签名验证

```python
class WeChatCrypto:
    def decrypt(self, encrypted_text: str) -> Tuple[str, str]:
        # AES-CBC 解密
        
    def verify_signature(self, ...) -> bool:
        # SHA1 签名验证
```

#### 3.3 WeChatMessageHandler (`src/wechat/handler.py`)

**职责**: 消息解析

```python
class WeChatMessageHandler:
    def parse_message(...) -> Optional[WeChatMessage]:
        # 1. 验证签名
        # 2. 解密消息
        # 3. 解析 XML
        # 4. 返回 WeChatMessage dataclass
```

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

| 模块 | 文件 | 行数 | 职责 |
|------|------|------|------|
| config | settings.py | ~40 | 配置加载 |
| wechat | crypto.py | ~130 | 加解密 |
| wechat | client.py | ~100 | API 调用 |
| wechat | handler.py | ~100 | 消息解析 |
| ai | qwen.py | ~90 | Qwen 执行 |
| server | app.py | ~150 | HTTP 路由 |
| **总计** | **6 文件** | **~610 行** | |

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
