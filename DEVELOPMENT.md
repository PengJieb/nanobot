# Nanobot 开发者指南

本文档面向新加入 nanobot 项目的开发者，帮助你快速理解项目全貌并高效参与开发。

---

## 目录

- [项目概览](#项目概览)
- [环境搭建](#环境搭建)
- [项目结构](#项目结构)
- [架构详解](#架构详解)
  - [数据流总览](#数据流总览)
  - [Agent 核心引擎](#agent-核心引擎)
  - [消息总线](#消息总线)
  - [Channel 系统](#channel-系统)
  - [Provider 系统](#provider-系统)
  - [Tool 系统](#tool-系统)
  - [Session 管理](#session-管理)
  - [Memory 系统](#memory-系统)
  - [Skill 系统](#skill-系统)
  - [Cron 定时任务](#cron-定时任务)
  - [Heartbeat 心跳服务](#heartbeat-心跳服务)
  - [Subagent 子代理](#subagent-子代理)
  - [MCP 集成](#mcp-集成)
  - [配置系统](#配置系统)
- [常用开发命令](#常用开发命令)
- [测试指南](#测试指南)
- [扩展开发指南](#扩展开发指南)
  - [添加新 Tool](#添加新-tool)
  - [添加新 Channel](#添加新-channel)
  - [添加新 Provider](#添加新-provider)
  - [添加新 Skill](#添加新-skill)
- [代码规范](#代码规范)
- [Docker 部署](#docker-部署)
- [调试技巧](#调试技巧)

---

## 项目概览

Nanobot 是一个超轻量级个人 AI 助手框架，核心代码约 4,000 行。它的设计目标是：

- **极简**：比同类项目小 99%，代码清晰易读
- **多平台**：支持 13+ 聊天平台（Telegram、Discord、Slack、WhatsApp、飞书、钉钉、Matrix、Email、QQ 等）
- **多模型**：通过 LiteLLM 支持 20+ LLM 提供商（OpenRouter、Anthropic、OpenAI、DeepSeek、Gemini 等）
- **可扩展**：插件式 Tool、Channel、Provider、Skill 架构
- **研究友好**：简洁的抽象层，适合快速实验

技术栈：Python 3.11+、Pydantic、Typer、LiteLLM、asyncio、prompt_toolkit、Rich。

---

## 环境搭建

### 前置要求

- Python >= 3.11
- Node.js >= 20（仅 WhatsApp bridge 需要）
- Git

### 安装步骤

```bash
# 1. 克隆仓库
git clone <repo-url> && cd nanobot

# 2. 创建虚拟环境（推荐使用 uv）
uv venv && source .venv/bin/activate

# 3. 安装项目及开发依赖
pip install -e ".[dev]"

# 4. 如需 Matrix 支持
pip install -e ".[dev,matrix]"

# 5. 初始化配置和工作区
nanobot onboard
```

`nanobot onboard` 会在 `~/.nanobot/` 下创建：
- `config.json` — 主配置文件
- `workspace/` — 工作区（memory、sessions、skills、模板文件）

### 配置 LLM Provider

编辑 `~/.nanobot/config.json`，至少需要配置一个 provider：

```json
{
  "agents": {
    "defaults": {
      "model": "claude-sonnet-4-20250514"
    }
  },
  "providers": {
    "anthropic": {
      "apiKey": "sk-ant-..."
    }
  }
}
```

系统会根据 model 名称自动匹配 provider，也可以显式指定：

```json
{
  "agents": {
    "defaults": {
      "model": "gpt-4o",
      "provider": "openai"
    }
  }
}
```

### 验证安装

```bash
nanobot status    # 检查配置状态
nanobot agent     # 交互式聊天（验证 LLM 连通性）
```

---

## 项目结构

```
nanobot/
├── nanobot/                    # 主 Python 包
│   ├── __init__.py             # 版本号 (__version__)
│   ├── __main__.py             # python -m nanobot 入口
│   ├── cli/
│   │   └── commands.py         # Typer CLI 命令定义（核心入口）
│   ├── agent/                  # 核心 Agent 引擎
│   │   ├── loop.py             # AgentLoop — 主循环（LLM 调用 ↔ Tool 执行）
│   │   ├── context.py          # ContextBuilder — 构建 system prompt 和消息序列
│   │   ├── memory.py           # MemoryStore — 两层持久化记忆
│   │   ├── skills.py           # SkillsLoader — 加载 markdown 技能文件
│   │   ├── subagent.py         # SubagentManager — 后台子代理
│   │   └── tools/              # 内置工具
│   │       ├── base.py         # Tool ABC — 所有工具的基类
│   │       ├── registry.py     # ToolRegistry — 动态注册和执行
│   │       ├── shell.py        # ExecTool — Shell 命令执行
│   │       ├── filesystem.py   # 文件操作（Read/Write/Edit/ListDir）
│   │       ├── web.py          # WebSearch + WebFetch
│   │       ├── message.py      # MessageTool — 向用户发送消息
│   │       ├── spawn.py        # SpawnTool — 创建后台子代理
│   │       ├── cron.py         # CronTool — 定时任务管理
│   │       └── mcp.py          # MCP 工具包装器
│   ├── bus/                    # 消息总线（解耦）
│   │   ├── events.py           # InboundMessage / OutboundMessage 数据类
│   │   └── queue.py            # MessageBus — 异步队列
│   ├── channels/               # 聊天平台集成
│   │   ├── base.py             # BaseChannel ABC
│   │   ├── manager.py          # ChannelManager — 管理所有 channel
│   │   ├── telegram.py         # Telegram
│   │   ├── discord.py          # Discord
│   │   ├── slack.py            # Slack
│   │   ├── whatsapp.py         # WhatsApp
│   │   ├── feishu.py           # 飞书
│   │   ├── dingtalk.py         # 钉钉
│   │   ├── matrix.py           # Matrix/Element
│   │   ├── email.py            # Email (IMAP/SMTP)
│   │   ├── qq.py               # QQ
│   │   └── mochat.py           # Mochat/Claw IM
│   ├── providers/              # LLM Provider 抽象
│   │   ├── base.py             # LLMProvider ABC + LLMResponse 数据类
│   │   ├── registry.py         # ProviderSpec 注册表（20+ provider 元数据）
│   │   ├── litellm_provider.py # LiteLLM 多 provider 实现
│   │   ├── custom_provider.py  # 直接 OpenAI 兼容端点
│   │   ├── openai_codex_provider.py  # OAuth 认证 provider
│   │   └── transcription.py    # 语音转写支持
│   ├── config/                 # 配置管理
│   │   ├── schema.py           # 所有 Pydantic 配置模型
│   │   └── loader.py           # 配置文件加载/保存/迁移
│   ├── session/
│   │   └── manager.py          # SessionManager — JSONL 会话持久化
│   ├── cron/                   # 定时任务
│   │   ├── types.py            # CronJob / CronSchedule 等数据类
│   │   └── service.py          # CronService — 基于 asyncio 的定时调度
│   ├── heartbeat/
│   │   └── service.py          # HeartbeatService — 周期性主动任务
│   ├── skills/                 # 内置技能（markdown 文件）
│   │   ├── README.md
│   │   ├── cron/               # 定时任务技能
│   │   ├── github/             # GitHub 集成
│   │   ├── memory/             # 记忆管理
│   │   ├── summarize/          # 内容摘要
│   │   ├── tmux/               # tmux 远程控制
│   │   ├── weather/            # 天气查询
│   │   ├── clawhub/            # 技能市场
│   │   └── skill-creator/      # 创建新技能
│   ├── templates/              # 工作区模板文件
│   │   ├── AGENTS.md           # Agent 行为指南
│   │   ├── HEARTBEAT.md        # 心跳任务定义
│   │   ├── SOUL.md             # 人格设定
│   │   ├── TOOLS.md            # 工具使用说明
│   │   ├── USER.md             # 用户画像
│   │   └── memory/
│   │       ├── MEMORY.md       # 长期记忆模板
│   │       └── HISTORY.md      # 历史日志模板
│   ├── app/                    # Application Builder 模块
│   │   ├── __init__.py
│   │   ├── schema.py           # AppSpec / BuildSession / ComponentLayout 等 Pydantic 模型
│   │   ├── manager.py          # AppManager — apps/ 目录的 CRUD 操作
│   │   └── builder.py          # AppBuilder — 10 问对话流程 + 调用 agent 生成 AppSpec
│   └── utils/
│       └── helpers.py          # 工具函数（路径、时间戳、模板同步）
├── bridge/                     # WhatsApp Node.js/TypeScript bridge
├── tests/                      # 测试套件
├── pyproject.toml              # 项目配置（依赖、ruff、pytest）
├── Dockerfile                  # Docker 构建
├── docker-compose.yml          # Docker Compose 编排
└── CLAUDE.md                   # Claude Code 上下文
```

---

## 架构详解

### 数据流总览

```
                          ┌──────────────────────────┐
                          │    ChannelManager         │
                          │  ┌────────┐ ┌──────────┐ │
    用户消息 ───────────►  │  │Telegram│ │ Discord  │ │
                          │  └───┬────┘ └────┬─────┘ │
                          │      │           │       │
                          └──────┼───────────┼───────┘
                                 │           │
                       ┌─────────▼───────────▼─────────┐
                       │       MessageBus               │
                       │  InboundQueue ──► OutboundQueue│
                       └─────────┬───────────▲─────────┘
                                 │           │
                       ┌─────────▼───────────┴─────────┐
                       │         AgentLoop              │
                       │                                │
                       │  ContextBuilder ◄── MemoryStore│
                       │       │           SkillsLoader │
                       │       ▼                        │
                       │  LLMProvider.chat()             │
                       │       │                        │
                       │       ▼                        │
                       │  ToolRegistry.execute()         │
                       │  ┌────┬─────┬─────┬──────┐    │
                       │  │File│Shell│ Web │Spawn │... │
                       │  └────┴─────┴─────┴──────┘    │
                       │       │                        │
                       │       ▼                        │
                       │  SessionManager.save()          │
                       └────────────────────────────────┘
```

**核心流程**：

1. 用户通过 Channel（Telegram/Discord/...）发送消息
2. Channel 将消息封装为 `InboundMessage`，发布到 `MessageBus`
3. `AgentLoop` 从 bus 消费消息，通过 `SessionManager` 加载会话历史
4. `ContextBuilder` 组装完整的 prompt（system prompt + 记忆 + 技能 + 历史 + 当前消息）
5. 调用 `LLMProvider.chat()` 获取 LLM 响应
6. 如果 LLM 返回 tool_calls，通过 `ToolRegistry` 执行工具
7. 将工具结果反馈给 LLM，循环直到 LLM 给出最终回复（最多 40 轮迭代）
8. 保存对话到 session，发布 `OutboundMessage` 到 bus
9. `ChannelManager` 将响应路由到对应的 Channel 发送给用户

### Agent 核心引擎

**文件**：`nanobot/agent/loop.py`

`AgentLoop` 是整个系统的核心编排器，负责：

- 消费 inbound 消息并分发处理
- 管理 agent 迭代循环（LLM 调用 → tool 执行 → 反馈结果）
- 触发 memory consolidation
- 处理 slash 命令（`/new`, `/help`, `/stop`）
- 懒加载 MCP 连接

**关键方法**：

| 方法 | 说明 |
|------|------|
| `run()` | 主事件循环，持续消费 inbound 消息 |
| `_process_message(msg)` | 处理单条消息的完整流程 |
| `_run_agent_loop()` | 同步迭代：LLM 调用 → tool 执行，直到结束或达到 max_iterations |
| `_dispatch(msg)` | 带全局锁的消息分发（含错误处理） |
| `_connect_mcp()` | 首次使用时懒连接 MCP 服务器 |
| `_consolidate_memory(session)` | 异步触发 memory consolidation |
| `process_direct(text)` | CLI/Cron 直接调用的处理接口 |
| `_register_default_tools()` | 注册所有内置工具 |
| `_set_tool_context(channel, chat_id, msg_id)` | 更新 message/spawn/cron tool 的路由上下文 |

**重要常量**：

- `_TOOL_RESULT_MAX_CHARS = 500`：存入 history 时截断 tool 结果
- `max_iterations = 40`：agent 循环最大迭代次数
- `memory_window = 100`：触发 memory consolidation 的消息数阈值

**Gateway 启动顺序**（在 `cli/commands.py` 的 `gateway` 命令中）：

```
1. load_config()
2. _make_provider(config)          → LLMProvider
3. MessageBus()
4. SessionManager(workspace)
5. CronService(store_path)         → 在 AgentLoop 之前创建
6. AgentLoop(provider, bus, sessions, cron_service, ...)
7. cron_service.on_job = callback  → 需要 agent 实例
8. ChannelManager(config, bus)     → 初始化所有启用的 channel
9. HeartbeatService(workspace, provider, on_execute, on_notify)
10. 启动所有服务
```

### 消息总线

**文件**：`nanobot/bus/queue.py`, `nanobot/bus/events.py`

`MessageBus` 使用两个 `asyncio.Queue` 实现 channel 和 agent 之间的完全解耦：

```python
class MessageBus:
    inbound: asyncio.Queue[InboundMessage]    # Channel → Agent
    outbound: asyncio.Queue[OutboundMessage]  # Agent → Channel
```

**消息数据类**：

```python
@dataclass
class InboundMessage:
    channel: str              # "telegram", "discord", "slack" 等
    sender_id: str            # 发送者 ID
    chat_id: str              # 聊天/群组 ID
    content: str              # 消息文本
    timestamp: datetime
    media: list[str]          # 媒体 URL 列表
    metadata: dict[str, Any]  # channel 特定数据
    session_key_override: str | None  # 可选的 session key 覆盖

    @property
    def session_key(self) -> str:  # 默认为 "{channel}:{chat_id}"

@dataclass
class OutboundMessage:
    channel: str
    chat_id: str
    content: str
    reply_to: str | None
    media: list[str]
    metadata: dict[str, Any]
```

### Channel 系统

**文件**：`nanobot/channels/base.py`, `nanobot/channels/manager.py`

所有 channel 继承 `BaseChannel` ABC：

```python
class BaseChannel(ABC):
    name: str = "base"        # channel 标识符
    config: Any               # channel 特定配置
    bus: MessageBus

    @abstractmethod
    async def start(self) -> None: ...     # 开始监听
    @abstractmethod
    async def stop(self) -> None: ...      # 清理资源
    @abstractmethod
    async def send(msg: OutboundMessage) -> None: ...  # 发送消息

    def is_allowed(sender_id: str) -> bool: ...        # 白名单检查
    async def _handle_message(...) -> None: ...        # 转发到 bus
```

`ChannelManager` 的职责：
- 根据配置动态实例化已启用的 channel
- `start_all()` / `stop_all()` 管理所有 channel 生命周期
- `_dispatch_outbound()` 后台任务持续消费 outbound 消息并路由到对应 channel
- 通过 `get_channel(name)` 按名查找 channel

**channel 启用方式**：在 `config.json` 中对应 channel 配置添加 `"enabled": true` 并填写必要的认证信息。

### Provider 系统

**文件**：`nanobot/providers/base.py`, `nanobot/providers/registry.py`, `nanobot/providers/litellm_provider.py`, `nanobot/providers/custom_provider.py`

#### 抽象层

```python
@dataclass
class ToolCallRequest:
    id: str
    name: str
    arguments: dict[str, Any]

@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCallRequest] = []
    finish_reason: str = "stop"
    usage: dict[str, int] = {}
    reasoning_content: str | None = None

class LLMProvider(ABC):
    @abstractmethod
    async def chat(self, messages, tools, model, max_tokens, temperature) -> LLMResponse: ...
    @abstractmethod
    def get_default_model(self) -> str: ...
```

#### Provider 注册表

`ProviderSpec` 是一个 frozen dataclass，包含每个 provider 的完整元数据：

```python
@dataclass(frozen=True)
class ProviderSpec:
    name: str                    # 配置字段名
    keywords: tuple[str, ...]    # model 名称关键字（用于自动匹配）
    env_key: str                 # LiteLLM 环境变量名
    litellm_prefix: str = ""     # LiteLLM model 前缀
    is_gateway: bool = False     # 是否为网关型 provider
    is_local: bool = False       # 是否为本地服务
    is_oauth: bool = False       # 是否使用 OAuth
    is_direct: bool = False      # 是否直接调用（不经过 LiteLLM）
    supports_prompt_caching: bool = False
    # ... 更多字段
```

**Provider 查找逻辑**（三种方式）：

1. `find_by_model(model)` — 根据 model 名称的关键字匹配
2. `find_by_name(name)` — 根据配置中的 provider 名称
3. `find_gateway(provider_name, api_key, api_base)` — 检测网关/本地 provider

#### 三种实现

| 实现 | 场景 | 说明 |
|------|------|------|
| `LiteLLMProvider` | 大多数 provider | 通过 LiteLLM 统一接口，自动处理 model 前缀、环境变量、prompt caching |
| `CustomProvider` | 自定义 OpenAI 兼容端点 | 直接使用 `AsyncOpenAI` 客户端，绕过 LiteLLM |
| `OpenAICodexProvider` | OAuth 认证 provider | OpenAI Codex、GitHub Copilot 等需要 OAuth 的服务 |

**Provider 选择流程**（在 `cli/commands.py` 的 `_make_provider` 中）：

```
model → find_by_model() → ProviderSpec
  ├─ is_oauth=True  → OpenAICodexProvider
  ├─ is_direct=True → CustomProvider
  └─ 其他           → LiteLLMProvider
```

### Tool 系统

**文件**：`nanobot/agent/tools/base.py`, `nanobot/agent/tools/registry.py`

#### Tool 基类

```python
class Tool(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...              # 工具标识符
    @property
    @abstractmethod
    def description(self) -> str: ...       # 人类可读描述
    @property
    @abstractmethod
    def parameters(self) -> dict: ...       # JSON Schema 参数定义

    @abstractmethod
    async def execute(self, **kwargs) -> str: ...  # 执行工具

    def validate_params(self, params: dict) -> list[str]: ...  # 参数校验
    def to_schema(self) -> dict: ...        # 转换为 OpenAI function 格式
```

#### ToolRegistry

```python
class ToolRegistry:
    def register(self, tool: Tool) -> None        # 注册工具
    def unregister(self, name: str) -> None        # 注销工具
    def get(self, name: str) -> Tool | None        # 按名获取
    def get_definitions(self) -> list[dict]        # 导出所有 OpenAI schema
    async def execute(self, name: str, params: dict) -> str  # 校验 + 执行
```

**执行流程**：
1. 根据名称查找 tool
2. `validate_params()` 校验参数（类型、required、enum、range 等）
3. 调用 `tool.execute(**params)`
4. 出错时自动附加提示：`[Analyze the error above and try a different approach.]`

#### 内置工具一览

| 工具类 | 名称 | 功能 |
|--------|------|------|
| `ReadFileTool` | `read_file` | 读取文件内容 |
| `WriteFileTool` | `write_file` | 写入文件（自动创建父目录） |
| `EditFileTool` | `edit_file` | 查找替换编辑（含 difflib 模糊匹配建议） |
| `ListDirTool` | `list_dir` | 列出目录内容 |
| `ExecTool` | `exec` | 执行 shell 命令（60s 超时，危险命令拦截，10K 字符输出限制） |
| `WebSearchTool` | `web_search` | Brave Search API 网络搜索 |
| `WebFetchTool` | `web_fetch` | 抓取网页并提取内容（Readability） |
| `MessageTool` | `message` | 向用户/channel 发送消息 |
| `SpawnTool` | `spawn` | 创建后台子代理 |
| `CronTool` | `cron` | 管理定时任务（add/list/remove） |
| `MCPToolWrapper` | `mcp_{server}_{tool}` | MCP 服务器工具的包装器 |

**ExecTool 安全机制**：
- 默认拒绝模式列表：`rm -rf /`, `format`, `dd`, `shutdown`, `reboot`, fork bombs, `mkfs`, raw disk 写入
- 可选 allow_patterns 白名单模式
- `restrict_to_workspace` 限制路径访问范围
- 超时后自动终止子进程
- 输出截断到 10,000 字符

### Session 管理

**文件**：`nanobot/session/manager.py`

```python
@dataclass
class Session:
    key: str                    # "{channel}:{chat_id}"
    messages: list[dict]        # append-only 消息列表
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any]
    last_consolidated: int      # 已 consolidation 的消息数量

    def add_message(role, content, **kwargs): ...
    def get_history(max_messages=500) -> list[dict]: ...  # 获取未 consolidation 的消息
    def clear(): ...
```

**SessionManager** 特性：
- 基于 JSONL 的持久化存储（每个 session 一个文件）
- 内存缓存加速访问
- `get_or_create(key)` 自动加载或新建
- 支持从旧版路径（`~/.nanobot/sessions/`）迁移到工作区路径
- `get_history()` 只返回 `last_consolidated` 之后的消息，并对齐到 user turn 边界

**Session key 格式**：`{channel}:{chat_id}`，如 `telegram:123456`、`cli:local`

### Memory 系统

**文件**：`nanobot/agent/memory.py`

两层持久化记忆架构：

```
workspace/memory/
├── MEMORY.md    # 长期事实记忆（LLM 自动 consolidation 更新）
└── HISTORY.md   # 可搜索的事件日志（append-only）
```

**MemoryStore 关键方法**：

| 方法 | 说明 |
|------|------|
| `read_long_term()` | 读取 MEMORY.md |
| `write_long_term(content)` | 写入 MEMORY.md |
| `append_history(entry)` | 追加到 HISTORY.md |
| `get_memory_context()` | 返回格式化的长期记忆（注入 system prompt） |
| `consolidate(session, provider, model)` | 核心 consolidation 流程 |

**Memory Consolidation 流程**：

```
session.messages 超过 memory_window 阈值
  ↓
提取 last_consolidated 之前的旧消息
  ↓
格式化为：timestamp + role + tools_used + content
  ↓
调用 LLM，提供 save_memory 工具定义
  ↓
LLM 返回 tool_call: {history_entry, memory_update}
  ↓
history_entry → 追加到 HISTORY.md
memory_update → 更新 MEMORY.md（如有变化）
  ↓
更新 session.last_consolidated 指针
```

这个机制确保了长期记忆的持久性，同时避免上下文窗口溢出。

### Skill 系统

**文件**：`nanobot/agent/skills.py`

Skill 是 markdown 文件，通过"教学"方式赋予 agent 新能力。

**Skill 文件格式**（`SKILL.md`）：

```markdown
---
name: my-skill
description: 简短描述
always: false           # true 则自动注入 system prompt
requires:
  bins: [git, gh]       # 依赖的系统命令
  env: [GITHUB_TOKEN]   # 依赖的环境变量
---

# 技能指令内容（markdown）

这里写给 agent 的指令...
```

**SkillsLoader 关键方法**：

| 方法 | 说明 |
|------|------|
| `list_skills()` | 列出所有可用技能（含需求检查） |
| `load_skill(name)` | 按名加载（workspace 优先于 builtin） |
| `load_skills_for_context()` | 加载多个技能用于 system prompt |
| `build_skills_summary()` | 生成 XML 格式的技能摘要 |
| `get_always_skills()` | 获取 `always=true` 的技能 |

**技能发现优先级**：
1. `workspace/skills/{name}/SKILL.md`（用户自定义，最高优先级）
2. `nanobot/skills/{name}/SKILL.md`（内置技能）

### Cron 定时任务

**文件**：`nanobot/cron/types.py`, `nanobot/cron/service.py`

#### 数据模型

```python
@dataclass
class CronSchedule:
    kind: str        # "at" | "every" | "cron"
    at_ms: int       # 一次性：毫秒时间戳
    every_ms: int    # 周期性：间隔毫秒
    expr: str        # cron 表达式，如 "0 9 * * *"
    tz: str          # IANA 时区，如 "Asia/Shanghai"

@dataclass
class CronJob:
    id: str          # 8 字符 UUID
    name: str
    enabled: bool
    schedule: CronSchedule
    payload: CronPayload    # message, channel, to, deliver
    state: CronJobState     # next_run_at_ms, last_status
    delete_after_run: bool  # 一次性任务执行后删除
```

#### CronService

基于 `asyncio.sleep` 的定时调度器（非系统 cron）：

| 方法 | 说明 |
|------|------|
| `start()` / `stop()` | 启动/停止服务 |
| `add_job(name, schedule, message, ...)` | 创建新任务 |
| `remove_job(job_id)` | 删除任务 |
| `enable_job(job_id, enabled)` | 启用/禁用 |
| `run_job(job_id)` | 手动执行 |
| `list_jobs(include_disabled)` | 列出所有任务 |

**调度机制**：
1. 加载持久化 store（JSON 文件）
2. 计算所有任务的下次执行时间
3. `asyncio.sleep` 到最近的触发时间
4. 执行到期任务（调用 `on_job` 回调）
5. 更新状态、重新计算、重新 arm timer

### Heartbeat 心跳服务

**文件**：`nanobot/heartbeat/service.py`

两阶段设计，避免不必要的 agent 调用：

**Phase 1 — 决策阶段**：
- 读取 `workspace/HEARTBEAT.md`（用户编辑的任务列表）
- 调用 LLM，提供虚拟 `heartbeat` tool（action: skip/run, tasks: 摘要）
- LLM 决定是否需要执行（skip = 无任务或都已完成）

**Phase 2 — 执行阶段**（仅当 action="run"）：
- 将 tasks 摘要传给 `on_execute` 回调（实际上调用 `agent.process_direct()`）
- 获得响应后通过 `on_notify` 回调发送到 channel

**关键配置**：
- `interval_s`：检查间隔，默认 1800 秒（30 分钟）
- `enabled`：全局开关
- `trigger_now()`：手动触发（用于测试/CLI）

### Subagent 子代理

**文件**：`nanobot/agent/subagent.py`

**SubagentManager** 提供后台异步任务能力：

- **受限工具集**：仅 file ops、shell、web（无 message、spawn、cron）
- **迭代限制**：最多 15 次（主 agent 为 40 次）
- **独立执行**：拥有自己的消息上下文和 agent 循环
- **结果通知**：完成后以 system message 注入主 agent 的 bus

```
SpawnTool.execute(task, label)
  → SubagentManager.spawn(task, label)
  → asyncio.create_task(_run_subagent())
  → [后台执行：构建 prompt → LLM 调用 → tool 执行]
  → _announce_result() → MessageBus.publish_inbound(system_msg)
  → 主 AgentLoop 处理结果，自然地告知用户
```

### Application Builder

**文件**：`nanobot/app/schema.py`, `nanobot/app/manager.py`, `nanobot/app/builder.py`

Application Builder 让用户通过 10 问对话流程生成可运行的 Web 应用。

#### 数据模型（`schema.py`）

```python
class AppSpec(BaseModel):          # 完整应用规格（持久化为 JSON）
    id: str                        # 12 位 hex ID
    title: str
    description: str
    version: str                   # 默认 "1.0"
    created_at: datetime
    layout: AppLayout              # type: "single-page"|"dashboard"|"wizard"
    state: AppState                # 应用状态变量列表
    components: list[AppComponent] # UI 组件列表

class AppComponent(BaseModel):
    id: str
    type: str                      # heading/text/input/textarea/select/button/...
    label: str
    properties: dict[str, Any]
    layout: ComponentLayout        # row/col/colSpan/rowSpan
    bind: str                      # 绑定的状态变量名
    events: dict[str, ComponentEvent]  # click/change/submit 等事件

class ComponentEvent(BaseModel):
    type: str                      # "local" | "agent"
    local_code: str                # 前端执行的 JS 代码
    agent_prompt: str              # 发送给 agent 的 prompt 模板
    result_bind: str               # 存储 agent 响应的状态变量

class BuildSession(BaseModel):     # 内存中的构建会话（10 问进度跟踪）
    session_id: str
    answers: list[str]
    created_at: datetime

    @property
    def current_question_index(self) -> int: ...   # = len(answers)
    @property
    def current_question(self) -> str | None: ...  # None when is_complete
    @property
    def is_complete(self) -> bool: ...             # len(answers) >= 10
```

**重要**：`QUESTIONS` 是包含 10 个问题的模块级列表，是构建流程的核心。

#### AppManager（`manager.py`）

CRUD 操作，将 `AppSpec` 持久化为 `workspace/apps/{id}.json`：

| 方法 | 说明 |
|------|------|
| `save(spec)` | 序列化并写入 JSON 文件 |
| `get(app_id)` | 加载并验证 AppSpec；无效或缺失时返回 None |
| `delete(app_id)` | 删除文件，返回 True/False |
| `list_apps()` | 按修改时间倒序返回摘要 dict 列表 |
| `new_id()` | 生成 12 字符 UUID hex |

注意：`get()` 和 `list_apps()` 对损坏的 JSON 文件静默返回 None/跳过，不抛出异常。

#### AppBuilder（`builder.py`）

管理构建会话的生命周期和 spec 生成：

```python
class AppBuilder:
    _sessions: dict[str, BuildSession] = {}  # 类级变量 — 跨实例共享

    @classmethod
    def start_session(cls) -> BuildSession: ...
    @classmethod
    def get_session(cls, session_id) -> BuildSession | None: ...
    @classmethod
    def answer(cls, session_id, answer) -> BuildSession | None: ...
    # 注意：当 is_complete 时忽略新 answer（防止超额添加）
    @classmethod
    def discard_session(cls, session_id) -> None: ...
    @classmethod
    async def generate(cls, session, agent, app_manager) -> AppSpec: ...
```

**`generate()` 流程**：
1. 将 10 问答案格式化为 requirements 文本
2. 调用 `agent.process_direct()` 传入生成 prompt（session_key = `app:build:{session_id}`）
3. `_parse_spec(raw)` 解析 agent 响应（处理 markdown fence、JSON 提取、colSpan 规整）
4. `AppManager.save(spec)` 持久化
5. `discard_session()` 清理内存会话

**`_parse_spec()` 容错逻辑**：
- 剥除 ` ``` ` 代码块 fence
- 提取第一个 `{` 到最后一个 `}` 之间的内容
- 将缺失 `colSpan`/`col_span` 的 layout 默认设为 12
- 补全 event 字段默认值
- 解析失败时返回 `_fallback_spec()`（含占位 heading + error text 组件）

#### Web 端点（`web/server.py`）

当 `app_manager is not None` 时激活以下端点：

| 端点 | 说明 |
|------|------|
| `POST /api/app/build/start` | 创建新 BuildSession，返回第一个问题 |
| `POST /api/app/build/{session_id}/answer` | 提交答案，返回下一个问题或 `status: complete` |
| `POST /api/app/build/{session_id}/generate` | 触发 spec 生成（SSE 流式返回进度） |
| `GET /api/apps` | 列出所有已存储的应用 |
| `GET /api/app/{app_id}` | 获取应用的完整 spec |
| `DELETE /api/app/{app_id}` | 删除应用 |
| `POST /api/app/{app_id}/action` | 执行 agent 事件（SSE 流式），session_key = `app:{app_id}` |

### MCP 集成

**文件**：`nanobot/agent/tools/mcp.py`

MCP（Model Context Protocol）集成支持两种传输方式：

- **stdio**：通过 `command` + `args` 启动子进程
- **HTTP/SSE**：通过 `url` + `headers` 连接远程服务

**MCPToolWrapper** 将 MCP 工具包装为 nanobot Tool：
- 名称空间化：`mcp_{server_name}_{tool_name}`
- 异步执行带超时（默认 30s，可配置 `tool_timeout`）
- 处理文本和非文本内容块

**连接时机**：懒加载，首条消息到来时在 `AgentLoop._connect_mcp()` 中连接。

### 配置系统

**文件**：`nanobot/config/schema.py`, `nanobot/config/loader.py`

所有配置使用 Pydantic 模型定义，支持 camelCase 和 snake_case 双向兼容。

#### 配置层次

```python
class Config(BaseSettings):
    agents: AgentsConfig           # model, provider, max_tokens, temperature, workspace, memory_window
    channels: ChannelsConfig       # 所有 channel 配置 + send_progress, send_tool_hints
    providers: ProvidersConfig     # 所有 provider 配置（api_key, api_base, extra_headers）
    gateway: GatewayConfig         # host, port, heartbeat(enabled, interval_s)
    tools: ToolsConfig             # web, exec, restrict_to_workspace, mcp_servers
```

#### 配置文件位置

| 路径 | 说明 |
|------|------|
| `~/.nanobot/config.json` | 主配置文件 |
| `~/.nanobot/workspace/` | 默认工作区 |
| `~/.nanobot/workspace/memory/` | 记忆文件 |
| `~/.nanobot/workspace/sessions/` | 会话文件 |
| `~/.nanobot/workspace/skills/` | 用户自定义技能 |
| `~/.nanobot/history/` | CLI 命令历史 |

#### Provider 自动匹配

`Config` 类提供了智能 provider 匹配：

```python
config.get_provider(model)       # 根据 model 名返回 ProviderConfig
config.get_provider_name(model)  # 根据 model 名返回 provider 名称
config.get_api_key(model)        # 根据 model 名返回 API key
```

匹配逻辑：显式指定的 `provider` 字段 > `ProviderSpec.find_by_model()` 按关键字匹配。

---

## 常用开发命令

### 安装与运行

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 初始化工作区
nanobot onboard

# 交互式聊天模式
nanobot agent

# 启动 gateway（所有 channel + 定时任务 + 心跳）
nanobot gateway

# 查看系统状态
nanobot status
```

### 测试

```bash
# 运行全部测试
pytest

# 运行单个测试文件
pytest tests/test_heartbeat_service.py

# 运行单个测试函数
pytest tests/test_heartbeat_service.py::test_trigger_now_executes_when_decision_is_run

# 首次失败即停止
pytest -x

# 显示详细输出
pytest -v

# 显示 print 输出
pytest -s
```

测试使用 `pytest-asyncio`，`asyncio_mode = "auto"`，无需手动添加 `@pytest.mark.asyncio`。

### 代码质量

```bash
# 检查代码风格
ruff check nanobot/

# 自动修复
ruff check --fix nanobot/

# 格式化代码
ruff format nanobot/

# 检查 + 格式化
ruff check --fix nanobot/ && ruff format nanobot/
```

### CLI 参考

```bash
nanobot --help                   # 查看所有命令
nanobot agent                    # 交互模式
nanobot agent -m "你好"          # 单次消息模式
nanobot gateway                  # 启动 gateway
nanobot gateway --port 8080      # 指定端口
nanobot channels status          # 查看 channel 状态
nanobot channels login whatsapp  # WhatsApp 登录
nanobot cron list                # 列出定时任务
nanobot cron add --every 3600 --message "检查邮件"  # 添加定时任务
nanobot provider login openai-codex   # OAuth 登录
```

---

## 测试指南

### 测试文件位置

所有测试在 `tests/` 目录下，命名规则 `test_*.py`。

### 常用测试模式

#### 1. Mock Provider

创建返回预定义响应的假 provider：

```python
from nanobot.providers.base import LLMProvider, LLMResponse, ToolCallRequest

class DummyProvider(LLMProvider):
    def __init__(self, responses):
        super().__init__(api_key=None, api_base=None)
        self.responses = list(responses)

    async def chat(self, messages, tools=None, **kwargs):
        return self.responses.pop(0)

    def get_default_model(self):
        return "dummy"
```

#### 2. 临时工作区

使用 pytest 的 `tmp_path` fixture 创建隔离的工作区：

```python
async def test_something(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "HEARTBEAT.md").write_text("# Tasks\n- Check email")
    # ...
```

#### 3. 回调跟踪

记录异步回调的调用情况：

```python
called_with = []

async def on_execute(tasks):
    called_with.append(tasks)
    return "Done"

# ... 执行测试 ...
assert len(called_with) == 1
assert "Check email" in called_with[0]
```

#### 4. Monkeypatch 外部依赖

使用 `monkeypatch` 替换外部库：

```python
def test_email(monkeypatch):
    class FakeIMAP:
        def login(self, user, pwd): pass
        def select(self, folder): return ("OK", [b"1"])
        # ...
    monkeypatch.setattr("imaplib.IMAP4_SSL", lambda *a, **k: FakeIMAP())
```

### 现有测试覆盖

| 测试文件 | 覆盖范围 |
|----------|----------|
| `test_heartbeat_service.py` | 心跳两阶段决策/执行流程 |
| `test_tool_validation.py` | Tool 参数校验（类型、range、enum、nested） |
| `test_email_channel.py` | Email channel IMAP/SMTP 集成 |
| `test_matrix_channel.py` | Matrix channel 完整集成（最大的测试文件） |
| `test_consolidate_offset.py` | Memory consolidation 偏移量跟踪 |
| `test_cli_input.py` | CLI 输入处理 |
| `test_commands.py` | CLI 命令 |
| `test_message_tool.py` | Message tool 基础 |
| `test_message_tool_suppress.py` | Message tool 抑制行为 |
| `test_task_cancel.py` | 任务取消 |
| `test_cron_commands.py` | Cron CLI 命令 |
| `test_cron_service.py` | Cron 服务 |
| `test_cron_edge_cases.py` | Cron 调度边界（zero/past interval、tz 校验、CRUD 操作） |
| `test_context_prompt_cache.py` | Prompt cache |
| `test_memory_consolidation_types.py` | Memory consolidation 类型 |
| `test_app_module.py` | App Builder 模块（AppManager CRUD、BuildSession 状态机、_parse_spec 解析、_fallback_spec） |

---

## 扩展开发指南

### 添加新 Tool

**步骤**：

1. 在 `nanobot/agent/tools/` 下创建新文件（或在已有文件中添加）
2. 继承 `Tool` ABC
3. 在 `AgentLoop._register_default_tools()` 中注册

**示例**：

```python
# nanobot/agent/tools/calculator.py
from nanobot.agent.tools.base import Tool

class CalculatorTool(Tool):
    @property
    def name(self) -> str:
        return "calculator"

    @property
    def description(self) -> str:
        return "Evaluate a mathematical expression."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Math expression to evaluate, e.g. '2 + 3 * 4'"
                }
            },
            "required": ["expression"]
        }

    async def execute(self, expression: str) -> str:
        try:
            result = eval(expression)  # 注意：生产环境应使用安全的解析器
            return str(result)
        except Exception as e:
            return f"Error: {e}"
```

注册（在 `nanobot/agent/loop.py`）：

```python
def _register_default_tools(self):
    # ... 现有工具 ...
    from nanobot.agent.tools.calculator import CalculatorTool
    self.tools.register(CalculatorTool())
```

### 添加新 Channel

**步骤**：

1. 在 `nanobot/channels/` 下创建新文件
2. 继承 `BaseChannel`，实现 `start()`、`stop()`、`send()`
3. 在 `config/schema.py` 添加配置模型
4. 在 `channels/manager.py` 的 `_init_channels()` 中注册

**示例骨架**：

```python
# nanobot/channels/my_platform.py
from nanobot.channels.base import BaseChannel
from nanobot.bus.events import OutboundMessage

class MyPlatformChannel(BaseChannel):
    name = "my_platform"

    async def start(self):
        self._running = True
        # 启动监听（webhook、轮询、websocket 等）
        # 收到消息时调用 self._handle_message(...)

    async def stop(self):
        self._running = False
        # 清理资源

    async def send(self, msg: OutboundMessage):
        # 将 msg.content 发送到平台
        pass
```

配置模型（在 `config/schema.py`）：

```python
class MyPlatformConfig(Base):
    enabled: bool = False
    api_token: str = ""
    allow_from: list[str] = []
```

### 添加新 Provider

只需在 `nanobot/providers/registry.py` 的 `PROVIDERS` 元组中添加一个 `ProviderSpec`：

```python
ProviderSpec(
    name="my_provider",
    keywords=("my-model-prefix",),
    env_key="MY_PROVIDER_API_KEY",
    display_name="My Provider",
    litellm_prefix="my_provider/",
),
```

同时在 `config/schema.py` 的 `ProvidersConfig` 中添加对应字段：

```python
class ProvidersConfig(Base):
    # ... 现有 providers ...
    my_provider: ProviderConfig = ProviderConfig()
```

### 添加新 Skill

最简单的扩展方式——无需修改代码：

1. 创建目录：`~/.nanobot/workspace/skills/my-skill/`
2. 创建 `SKILL.md`：

```markdown
---
name: my-skill
description: 简短描述这个技能做什么
always: false
requires:
  bins: []
  env: []
---

# My Skill

给 agent 的指令...

## 使用方式
...
```

设置 `always: true` 可将技能自动注入每次对话的 system prompt。

---

## 代码规范

### Ruff 配置

```toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W"]   # pycodestyle, pyflakes, isort, pep8-naming
ignore = ["E501"]                      # 忽略行长度（由 line-length 控制）
```

### 编码约定

- **Python 版本**：3.11+，可以使用 `match/case`、`type[X]` 等新语法
- **异步**：全面使用 `async/await`，核心循环基于 `asyncio`
- **类型标注**：使用 Python 3.11 风格（`list[str]` 而非 `List[str]`，`str | None` 而非 `Optional[str]`）
- **配置模型**：使用 Pydantic `BaseModel`，字段默认值提供合理的开箱即用行为
- **camelCase 兼容**：配置 JSON 使用 camelCase，Python 代码使用 snake_case，`Base` 模型类自动转换
- **日志**：使用 `loguru`（`from loguru import logger`）
- **错误处理**：Tool 执行错误包装在 result 字符串中返回，不抛出异常到 agent 循环

### Git 提交规范

查看近期 commit 风格：

```
e86cfcd Merge PR #1200 to update heartbeat tests to match two-phase tool-call architecture
fdd2c25 Merge PR #1222: fix runtime context leaking into session history
bc558d0 refactor: merge user-role branches in _save_turn
a6aa5fb Merge PR #1239: register Matrix channel in manager and schema
```

常用前缀：`feat:`, `fix:`, `refactor:`, `test:`, `docs:`

---

## Docker 部署

### 构建

```bash
docker compose build
```

### 运行

```bash
# Gateway 模式（后台运行）
docker compose up -d nanobot-gateway

# CLI 模式（交互式）
docker compose run --rm nanobot-cli agent

# 查看日志
docker compose logs -f nanobot-gateway
```

### Docker 架构

- **基础镜像**：`ghcr.io/astral-sh/uv:python3.12-bookworm-slim`（uv 加速依赖安装）
- **Node.js 20**：用于 WhatsApp bridge 构建
- **端口**：18790（gateway）
- **Volume**：`~/.nanobot:/root/.nanobot`（配置和工作区持久化）
- **资源限制**：1 CPU / 1GB RAM（上限），0.25 CPU / 256MB RAM（预留）

---

## 调试技巧

### 查看详细日志

```bash
# Agent 模式带详细日志
nanobot agent --log-level DEBUG

# 或设置环境变量
LOGURU_LEVEL=DEBUG nanobot gateway
```

### 检查配置

```bash
# 查看当前配置和状态
nanobot status

# 查看 channel 启用情况
nanobot channels status
```

### 常见问题排查

1. **LLM 调用失败**：检查 `nanobot status` 确认 API key 已配置，model 名称正确
2. **Channel 无响应**：检查 `channels status` 确认已启用，并查看 `allow_from` 白名单设置
3. **Tool 执行超时**：ExecTool 默认 60s 超时，MCP tool 默认 30s，可在 `config.json` 的 `tools` 部分调整
4. **Memory consolidation 问题**：检查 `workspace/memory/` 目录是否可写，查看 MEMORY.md 和 HISTORY.md 内容
5. **MCP 连接失败**：确认 MCP server 的 command/url 正确，检查 `tools.mcp_servers` 配置

### 交互式调试

在 `nanobot agent` 中可以使用 slash 命令：
- `/new` — 开始新会话（清除历史）
- `/help` — 显示帮助
- `/stop` — 停止当前任务
