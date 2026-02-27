# WeChat AI Assistant - 架构文档

## 一句话概述

通过企业微信远程控制 Qwen Code，支持多用户连续对话，每用户独立会话历史。

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                     企业微信客户端                           │
│                  (用户发消息 / 收回复)                        │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ HTTPS 回调
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI HTTP Server                       │
│              src/server.py - 接收消息 / 路由分发              │
└─────────────────────────────────────────────────────────────┘
                            │
                ┌───────────┴───────────┐
                │                       │
                ▼                       ▼
    ┌───────────────────┐   ┌─────────────────────┐
    │   WeChatClient    │   │    QwenExecutor     │
    │  src/wechat.py    │   │    src/qwen.py      │
    │  - 发送消息       │   │  - 执行 Qwen 命令     │
    │  - 自动分片       │   │  - 管理工作区        │
    │  - 进度汇报       │   │  - 超时处理         │
    └───────────────────┘   └─────────────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │     文件系统 (工作区)          │
                    │  ~/.wechat-ai-assistant/      │
                    │    workspaces/                │
                    │      ├── user_zhangsan/       │
                    │      └── user_lisi/           │
                    └───────────────────────────────┘
```

---

## 核心模块

### 1. src/main.py - 入口（~95 行）

**职责**: 配置加载、日志设置、组件初始化、启动服务

```python
# 配置
class Settings(BaseSettings):
    corp_id: str
    agent_id: int
    secret: str
    receive_token: str
    receive_encoding_aes_key: str
    port: int = 3000

# 启动流程
async def main():
    # 1. 验证配置
    # 2. 初始化 WeChatClient, WeChatCrypto, WeChatMessageHandler
    # 3. 初始化 QwenExecutor
    # 4. 创建 FastAPI 应用
    # 5. 测试企业微信连接
    # 6. 启动 uvicorn
```

---

### 2. src/wechat.py - 企业微信模块（~210 行）

**职责**: 消息加解密、API 调用、消息解析

**三个类**：

| 类 | 职责 |
|----|------|
| `WeChatCrypto` | AES 加解密、签名验证 |
| `WeChatClient` | Access Token 管理、发送消息（自动分片） |
| `WeChatMessageHandler` | 消息解密、XML 解析 |

**核心方法**：
```python
class WeChatClient:
    async def send_text_message(user_id, content, prefix="") -> int:
        """发送文本消息，自动按 2048 字节分片"""
```

---

### 3. src/qwen.py - Qwen 执行器（~155 行）

**职责**: 执行 Qwen Code 命令、管理工作区、超时处理、进度汇报

**会话管理**：
- **一个用户 = 一个工作区文件夹**
- `qwen --continue` 自动加载该目录的会话历史
- `/new` 命令清空文件夹，开始新会话

**核心方法**：
```python
class QwenExecutor:
    async def execute(user_id, command) -> (bool, str, str):
        """基础执行"""
    
    async def execute_with_progress(user_id, command, wechat_client) -> (bool, str, str):
        """带进度汇报（每 2 分钟发送"执行中..."）"""
```

**超时处理**：
- 超时时间：10 分钟（600 秒）
- 超时后自动发送总结请求

---

### 4. src/server.py - FastAPI 应用（~135 行）

**职责**: HTTP 路由、命令分发

**路由**：
| 路由 | 方法 | 职责 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/wechat/callback` | GET | 企业微信 URL 验证 |
| `/wechat/callback` | POST | 消息处理 |

**命令处理**：
```python
async def handle_ai_command(wechat_client, qwen, user_id, command):
    """
    处理 AI 命令（带超时处理和进度汇报）
    
    流程：
    1. 发送"⏳ 正在执行"
    2. 调用 qwen.execute_with_progress()
    3. 如果超时：发送通知 + 请求总结
    4. 如果成功/失败：发送结果
    """
```

---

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

3. FastAPI 接收 (src/server.py)
   ├─→ WeChatCrypto.decrypt() 解密
   ├─→ WeChatMessageHandler.parse_message() 解析
   └─→ 提取：from_user="zhangsan", content="帮我写个爬虫"

4. 命令识别
   └─→ 不是 /help, /new, /status
   └─→ 调用 handle_ai_command()

5. QwenExecutor.execute_with_progress()
   ├─→ workspace = ~/.wechat-ai-assistant/workspaces/zhangsan/
   ├─→ 启动子进程：qwen --continue --yolo "帮我写个爬虫"
   ├─→ 并发任务：
   │   ├─→ 读取输出
   │   └─→ 每 2 分钟发送"⏳ 执行中..."
   └─→ 超时控制：600 秒

6. Qwen Code 执行
   ├─→ 自动加载 workspaces/zhangsan/ 内的 session-*.json
   ├─→ 执行命令
   └─→ 更新 session 文件

7. 结果处理
   ├─→ 成功 → 发送 "✅ {output}"
   ├─→ 失败 → 发送 "❌ {output}"
   └─→ 超时 → 发送通知 + 请求总结

8. 回复用户
   └─→ WeChatClient.send_text_message("zhangsan", ...)
```

---

## 会话隔离机制

```
~/.wechat-ai-assistant/workspaces/
├── zhangsan/                   # 用户张三的工作区
│   ├── session-abc.json        # Qwen 自动生成的会话文件
│   └── last_output.txt
│
└── lisi/                       # 用户李四的工作区
    └── session-xyz.json

关键机制：
- 每个用户独立文件夹
- qwen --continue 自动加载当前目录的 session 文件
- 用户之间完全隔离
```

---

## 消息分片机制

**企业微信限制**：单条消息不超过 2048 字节

**自动分片**：
```python
# 短消息（<1500 字节）
"Hello" → 1 条：✅ Hello

# 长消息（>1500 字节）
3000 字中文 → 3 条：
  ✅ 第一段内容...
  [2/3] 第二段内容...
  [3/3] 第三段内容...
```

**实现**：
```python
def _split_message(content, max_bytes=1500):
    """按字节数分割，自动处理 UTF-8 中文截断"""
```

---

## 超时处理流程

```
执行开始
    │
    ├─→ 启动计时器（600 秒）
    │
    ├─→ 每 120 秒发送"⏳ 执行中... 已运行 X 分钟"
    │
    ├─→ [600 秒后] 超时
    │
    ├─→ 1. 终止 qwen 进程
    │
    ├─→ 2. 发送通知
    │     ⚠️ 执行超时（>10 分钟），已终止任务
    │
    ├─→ 3. 发送总结请求
    │     📝 正在请求总结...
    │
    └─→ 4. qwen 总结
          📋 总结：已完成 XXX，还有 XXX 没做...
```

---

## 代码统计

| 文件 | 行数 | 职责 |
|------|------|------|
| src/main.py | ~95 | 配置 + 日志 + 启动 |
| src/wechat.py | ~210 | 加解密 +API+ 消息处理 |
| src/qwen.py | ~155 | Qwen 执行 + 会话管理 |
| src/server.py | ~135 | HTTP 路由 + 命令分发 |
| **总计** | **~595 行** | **4 个文件** |

---

## 设计原则

### 1. 简单优先
- ✅ 无抽象基类
- ✅ 无多后端支持
- ✅ 无复杂的状态管理
- ✅ 一个函数搞定 AI 命令处理

### 2. 约定优于配置
- ✅ 默认工作区路径
- ✅ 默认超时 10 分钟
- ✅ 默认 2 分钟汇报一次

### 3. 用户隔离
- ✅ 每个用户独立文件夹
- ✅ Qwen 自动管理会话文件
- ✅ `/new` 命令清空重置

### 4. 异步非阻塞
- ✅ FastAPI 异步处理
- ✅ asyncio 子进程调用
- ✅ 并发执行（输出读取 + 进度汇报）

---

## 扩展指南

### 修改超时时间

```python
# src/qwen.py - execute_with_progress()
await asyncio.wait_for(read_task, timeout=600.0)  # 改为其他秒数
```

### 修改进度汇报间隔

```python
# src/qwen.py - report_progress()
interval = 120.0  # 改为其他秒数
```

### 添加新命令

```python
# src/server.py - wechat_callback_post()
elif content == "/mycommand":
    # 你的逻辑
    await wechat_client.send_text_message(user_id, "结果")
```

---

## 部署架构

```
┌──────────────────────────────────────────────────────┐
│  云服务器 (阿里云/腾讯云/...)                         │
│                                                       │
│  ┌────────────────────────────────────────────────┐ │
│  │  Docker Container (可选)                        │ │
│  │  ┌──────────────────────────────────────────┐  │ │
│  │  │  Python 3.11 + uvicorn                    │  │ │
│  │  │  ┌────────────────────────────────────┐  │  │ │
│  │  │  │  WeChat AI Assistant               │  │  │ │
│  │  │  └────────────────────────────────────┘  │  │ │
│  │  └──────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────┘ │
│                                                       │
│  ┌────────────────────────────────────────────────┐ │
│  │  cloudflared (内网穿透，可选)                    │ │
│  │  https://你的域名 → http://localhost:3000      │ │
│  └────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

---

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
- ❌ 需要复杂的权限控制
- ❌ 需要企业级高可用
