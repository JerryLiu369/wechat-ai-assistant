# 项目架构文档

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        企业微信客户端                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ HTTPS (回调)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      HTTP Server (FastAPI)                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  /wechat/callback (GET)  - 回调 URL 验证                   │  │
│  │  /wechat/callback (POST) - 接收用户消息                   │  │
│  │  /health                 - 健康检查                       │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ 内部调用
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      消息处理层 (WeChat)                        │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ WeChatCrypto    │  │ WeChatHandler   │  │ WeChatClient    │ │
│  │ - AES 加解密     │  │ - 签名验证      │  │ - Token 管理     │ │
│  │ - 签名生成      │  │ - 消息解析      │  │ - 消息发送      │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ 调用
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     AI 会话管理层 (AI Manager)                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  - 用户会话隔离 (user_id + backend -> session_id)         │  │
│  │  - 多后端支持 (iFlow, Qwen Code...)                       │  │
│  │  - 会话生命周期管理                                       │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ 接口调用
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      AI 后端层 (AIBackend)                       │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ AIBackend       │  │ IFlowBackend    │  │ QwenBackend     │ │
│  │ (抽象基类)      │  │ (iFlow CLI)     │  │ (预留)          │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ 子进程调用
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        iflow CLI                                │
└─────────────────────────────────────────────────────────────────┘
```

## 模块职责

### 1. config 模块
- **职责**: 配置加载、验证、管理
- **核心类**: `Settings` (pydantic-settings)
- **特性**: 
  - 环境变量自动加载
  - 配置验证与错误提示
  - 单例模式

### 2. wechat 模块
#### 2.1 crypto.py
- **职责**: 企业微信消息加解密
- **核心方法**:
  - `decrypt()`: AES-CBC 解密，PKCS7 去填充
  - `encrypt()`: AES-CBC 加密，PKCS7 填充
  - `verify_signature()`: SHA1 签名验证

#### 2.2 client.py
- **职责**: 企业微信 API 调用
- **核心方法**:
  - `get_access_token()`: Token 获取与缓存
  - `send_text_message()`: 发送文本消息
- **特性**: 
  - HTTP 连接池 (httpx)
  - Token 自动刷新

#### 2.3 handler.py
- **职责**: 消息解析与验证
- **核心类**: `WeChatMessage` (dataclass)
- **核心方法**:
  - `verify_callback()`: 回调 URL 验证
  - `parse_message()`: 消息解密与解析

### 3. ai 模块
#### 3.1 base.py
- **职责**: 定义 AI 后端抽象接口
- **核心类**: 
  - `AIBackend` (ABC): 抽象基类
  - `AIResult` (dataclass): 执行结果
- **设计模式**: 策略模式

#### 3.2 iflow.py
- **职责**: iFlow CLI 封装
- **核心机制**: 工作区隔离
  - 每个用户会话分配独立工作区目录
  - iflow 在工作区内自动生成 session 文件
  - 使用 `--continue` 加载当前目录最近会话
- **核心方法**:
  - `execute()`: 在工作区目录内执行命令
  - `create_session()`: 创建/清空工作区
  - `_get_workspace_path()`: 会话 ID 到目录路径映射
- **参数说明**:
  - `--continue`: 加载当前目录最近会话
  - `-p, --prompt`: 非交互式执行提示词
  - `-o, --output-file`: 输出执行信息到文件
- **特性**:
  - 异步子进程调用
  - 工作区目录隔离
  - 会话文件自动管理

#### 3.3 manager.py
- **职责**: 多用户会话管理
- **核心方法**:
  - `execute_command()`: 命令执行
  - `new_session()`: 重置会话
  - `get_status()`: 会话状态查询
- **特性**:
  - 用户隔离 (`user_id:backend` 映射)
  - 多后端注册

### 4. server 模块
- **职责**: HTTP 服务、路由分发
- **核心框架**: FastAPI
- **路由**:
  - `GET /wechat/callback`: 回调验证
  - `POST /wechat/callback`: 消息处理
  - `GET /health`: 健康检查

## 执行工作流

### 启动流程

```
1. main.py 入口
   │
   ├─→ 加载配置 (Settings)
   │    └─→ 验证 .env 配置完整性
   │
   ├─→ 初始化 WeChat 组件
   │    ├─→ WeChatClient (API 调用)
   │    ├─→ WeChatCrypto (加解密)
   │    └─→ WeChatHandler (消息处理)
   │
   ├─→ 初始化 AI 管理器
   │    ├─→ AISessionManager
   │    └─→ 注册 IFlowBackend
   │
   ├─→ 测试企业微信连接
   │    └─→ 获取 access_token
   │
   └─→ 启动 HTTP 服务
        └─→ uvicorn + FastAPI
```

### 消息处理流程

```
企业微信用户发送消息
        │
        ▼
1. HTTPS POST /wechat/callback
   ┌────────────────────────────┐
   │ msg_signature              │
   │ timestamp                  │
   │ nonce                      │
   │ encrypt (加密的 XML)        │
   └────────────────────────────┘
        │
        ▼
2. WeChatHandler.parse_message()
   ├─→ 验证签名
   ├─→ 解密消息 (AES-CBC)
   ├─→ 解析 XML (xmltodict)
   └─→ 返回 WeChatMessage
        │
        ▼
3. 命令解析 (parse_command())
   ├─→ /help → 返回帮助文本
   ├─→ /new  → 重置会话
   ├─→ /status → 返回状态
   └─→ 其他 → 执行 AI 命令
        │
        ▼
4. AI 命令执行
   ├─→ AISessionManager.execute_command()
   │    ├─→ 获取/创建用户会话 (user_id:iflow)
   │    └─→ IFlowBackend.execute()
   │         ├─→ 获取/创建工作区目录
   │         ├─→ 构建 iflow 命令 (--continue -p "命令")
   │         ├─→ 异步子进程执行 (cwd=工作区目录)
   │         ├─→ 输出清理
   │         └─→ iflow 自动在工作区内生成 session 文件
   │
   └─→ 返回 AIResult
        │
        ▼
5. 响应处理
   ├─→ 成功 → 分片发送 (4000 字节/条)
   └─→ 失败 → 发送错误信息
        │
        ▼
6. 返回 "success" 给企业微信
```

### 会话隔离机制

```
用户 A 发送消息
   │
   ├─→ session_key = "userA:iflow"
   │    └─→ workspace_A = ~/.wechat-ai-assistant/workspaces/user_userA/
   │         └─→ iflow --continue (在 workspace_A 内执行)
   │              └─→ session-xxx.jsonl 自动生成在 workspace_A 内

用户 B 发送消息
   │
   ├─→ session_key = "userB:iflow"
   │    └─→ workspace_B = ~/.wechat-ai-assistant/workspaces/user_userB/
   │         └─→ iflow --continue (在 workspace_B 内执行)
   │              └─→ session-yyy.jsonl 自动生成在 workspace_B 内

结果：
- 用户 A 和 B 的对话上下文完全隔离
- 每个工作区内的文件互不干扰
- iflow 自动管理 session 文件
```

## 设计模式

| 模式 | 应用位置 | 说明 |
|------|----------|------|
| **策略模式** | ai/base.py, ai/iflow.py | AIBackend 抽象，支持多后端切换 |
| **单例模式** | config/settings.py | lru_cache 保证配置单例 |
| **依赖注入** | server/app.py | create_app 注入依赖 |
| **工厂模式** | ai/manager.py | register_backend 动态注册 |
| **异步模式** | 全局 | asyncio + await/async |

## 扩展指南

### 添加新的 AI 后端 (如 Qwen Code)

1. 创建 `src/ai/qwen.py`
2. 继承 `AIBackend` 抽象类
3. 实现三个抽象方法
4. 在 `main.py` 中注册

```python
from src.ai.base import AIBackend, AIResult

class QwenBackend(AIBackend):
    def __init__(self, api_key: str):
        super().__init__("qwen")
        self.api_key = api_key
    
    async def execute(self, command: str, session_id: str) -> AIResult:
        # 调用 Qwen API
        pass
    
    async def create_session(self, user_id: str) -> str:
        return f"user:{user_id}"
    
    async def get_session_info(self, session_id: str) -> dict:
        return {"session_id": session_id}
```

### 添加新的消息渠道

1. 创建 `src/<platform>/` 目录
2. 实现消息收发接口
3. 在 `main.py` 中初始化
4. 在 `server/app.py` 中添加路由

## 最佳实践

1. **类型注解**: 所有函数都有完整的类型提示
2. **错误处理**: 使用 try-except 包裹外部调用
3. **日志记录**: 关键操作都有 loguru 日志
4. **异步优先**: IO 操作全部使用 async/await
5. **配置分离**: .env 管理敏感配置
6. **单一职责**: 每个模块只负责一个功能域
