# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Nanobot is an ultra-lightweight personal AI assistant framework (~4,000 lines of core code). It connects to 13+ chat platforms (Telegram, Discord, Slack, WhatsApp, Feishu, DingTalk, Matrix, Email, QQ, etc.) and supports 20+ LLM providers via LiteLLM.

## Common Commands

### Install & Setup
```bash
pip install -e ".[dev]"          # Install with dev dependencies
pip install -e ".[dev,matrix]"   # Include optional Matrix support
```

### Testing
```bash
pytest                           # Run all tests
pytest tests/test_foo.py         # Run a single test file
pytest tests/test_foo.py::test_bar  # Run a single test function
pytest -x                        # Stop on first failure
```
Tests use `pytest-asyncio` with `asyncio_mode = "auto"` — async test functions are detected automatically without `@pytest.mark.asyncio`.

### Linting
```bash
ruff check nanobot/              # Lint
ruff check --fix nanobot/        # Lint with auto-fix
ruff format nanobot/             # Format
```
Ruff config: line-length 100, target Python 3.11, rules E/F/I/N/W (E501 ignored).

### Running
```bash
nanobot onboard                  # First-time setup (creates ~/.nanobot/config.json)
nanobot agent                    # Interactive CLI chat
nanobot gateway                  # Start gateway with all enabled channels
```

## Architecture

### Data Flow
```
Channels (input) → MessageBus (async queues) → AgentLoop (LLM ↔ tools) → MessageBus → Channels (output)
```

### Core Modules (`nanobot/`)

| Module | Purpose |
|--------|---------|
| `agent/loop.py` | **Main orchestrator** — consumes messages, builds context, calls LLM, executes tools, sends responses |
| `agent/context.py` | `ContextBuilder` — assembles system prompt from identity + memory + skills + history |
| `agent/memory.py` | `MemoryStore` — two-layer persistence: `MEMORY.md` (consolidated facts) + `HISTORY.md` (searchable log) |
| `agent/skills.py` | `SkillsLoader` — loads markdown-based skill files that teach the agent capabilities |
| `agent/subagent.py` | `SubagentManager` — spawns background tasks |
| `agent/tools/` | Built-in tools: `shell`, `filesystem`, `web`, `message`, `spawn`, `cron`, `mcp`; all extend `Tool` ABC in `base.py` |
| `bus/` | `MessageBus` with `InboundMessage`/`OutboundMessage` dataclasses — decouples channels from agent |
| `channels/` | Chat platform integrations; all extend `BaseChannel` ABC in `base.py`; `ChannelManager` initializes enabled channels |
| `providers/` | LLM abstraction; `LLMProvider` ABC with `chat()` method; `ProviderRegistry` holds `ProviderSpec` metadata for auto-detection |
| `config/schema.py` | All Pydantic models for configuration (`Config`, `ChannelsConfig`, `ProvidersConfig`, etc.) |
| `config/loader.py` | Loads/saves `~/.nanobot/config.json` |
| `session/manager.py` | `SessionManager` — JSONL-based conversation persistence per channel:chat_id |
| `cli/commands.py` | Typer CLI — entry point for all commands; wires up all dependencies in `gateway` command |
| `cron/` | Scheduled task execution via croniter |
| `heartbeat/` | Periodic proactive tasks (reads `HEARTBEAT.md` every 30 min) |
| `skills/` | Bundled skill markdown files (cron, github, memory, summarize, tmux, weather, etc.) |

### Key Patterns

- **Constructor-based DI**: Components receive dependencies as constructor arguments. The `gateway` command in `cli/commands.py` wires everything together — no DI container.
- **Metadata-driven provider registry**: `ProviderSpec` dataclasses in `providers/registry.py` store keywords, env vars, and prefixing rules. Add a provider by adding a `ProviderSpec` entry.
- **Tool registration**: Tools extend `Tool` ABC (`agent/tools/base.py`) providing `execute(**kwargs) → str` and a JSON schema. Registered dynamically via `ToolRegistry`.
- **Memory consolidation**: When session messages exceed `memory_window` threshold, the LLM summarizes old messages into `MEMORY.md` and logs events to `HISTORY.md`.
- **Skills as markdown**: Skills are `SKILL.md` files in `skills/` or `workspace/skills/`. "Always-on" skills are auto-injected into the system prompt; others are loaded on demand.

### Extension Points

- **New tool**: Implement `Tool` ABC, register in `AgentLoop._register_default_tools()`
- **New channel**: Implement `BaseChannel` ABC, add to `ChannelManager._init_channels()` and `ChannelsConfig` in `config/schema.py`
- **New LLM provider**: Add `ProviderSpec` to `providers/registry.py`, add field to `ProvidersConfig`
- **New skill**: Create `nanobot/skills/{name}/SKILL.md` (built-in) or `workspace/skills/{name}/SKILL.md` (user)

### Bridge

`bridge/` contains a Node.js/TypeScript WhatsApp bridge using Baileys. It is force-included in the wheel build and lives alongside the Python package.

## Config & Workspace

- User config: `~/.nanobot/config.json` (Pydantic-validated via `config/schema.py`)
- Workspace: `~/.nanobot/workspace/` (memory files, skills, sessions)
- Templates: `nanobot/templates/` (auto-synced to workspace)