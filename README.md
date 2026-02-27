# WeChat AI Assistant

通过企业微信远程控制 Qwen Code，支持连续对话和多用户隔离。

## 致谢

本项目灵感来源于 [iflow-wechat-assistant](https://github.com/wx7in8/iflow-wechat-assistant)，感谢原作者的开源贡献！

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入企业微信配置。

### 3. 启动服务

```bash
python main.py
```

## 功能特点

- **多用户支持** - 每个用户独立会话，消息回复给发送者
- **连续对话** - 自动保持会话上下文
- **纯文本消息** - 兼容所有微信客户端

## 可用命令

| 命令 | 说明 |
|------|------|
| 直接发送文本 | 执行 Qwen 命令（自动恢复会话） |
| `/help` | 显示帮助信息 |
| `/new` | 开始新会话（清除上下文） |
| `/status` | 查看服务状态 |

## 会话管理

每个用户对应一个独立的工作区目录：

```
~/.wechat-ai-assistant/workspaces/
├── user_zhangsan/    # 用户张三的会话
└── user_lisi/        # 用户李四的会话
```

Qwen Code 会在各自目录内自动保存会话历史，`--continue` 参数自动加载。

## 项目结构

```
wechat-ai-assistant/
├── src/
│   ├── config/
│   │   └── settings.py     # 配置管理
│   ├── wechat/
│   │   ├── crypto.py       # 消息加解密
│   │   ├── client.py       # API 客户端
│   │   └── handler.py      # 消息处理器
│   ├── ai/
│   │   └── qwen.py         # Qwen Code 执行器
│   └── server/
│       └── app.py          # FastAPI 应用
├── main.py                 # 入口文件
├── requirements.txt        # Python 依赖
├── .env.example            # 配置模板
├── .gitignore              # Git 忽略配置
├── LICENSE                 # MIT 许可证
└── README.md               # 本文件
```

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
