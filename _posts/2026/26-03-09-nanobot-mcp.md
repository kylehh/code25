---
title: Nanobot MCP 集成 - 连接外部工具的桥梁
mathjax: true
toc: true
categories:
  - Study
tags:
  - Agent
  - MCP
  - Tools
---

[Nanobot](https://github.com/nanobot-ai/nanobot) 的核心定位是 **MCP Host** — 它不仅有内置工具，还能连接任意 MCP (Model Context Protocol) 服务器，动态扩展 Agent 能力。本文详解 MCP 在 nanobot 中的工作机制。

## 0 MCP 是什么

MCP (Model Context Protocol) 是 Anthropic 提出的开放协议，让 AI 应用能够标准化地连接外部工具和数据源。

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Nanobot   │────▶│ MCP Client  │────▶│ MCP Server  │
│   (Host)    │     │  (内置)      │     │  (外部)      │
└─────────────┘     └─────────────┘     └─────────────┘
```

Nanobot 作为 **MCP Host**，内置了 MCP Client，可以连接：
- **Remote HTTP MCP** — 通过 URL 连接远程服务
- **Local stdio MCP** — 通过命令行启动本地服务

## 1 配置 MCP Server

在 `~/.nanobot/config.json` 中添加：

```json
{
  "mcpServers": {
    "blackjack": {
      "url": "https://blackjack.nanobot.ai/mcp"
    },
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    },
    "myapi": {
      "url": "https://api.example.com/mcp",
      "headers": {
        "Authorization": "Bearer ${MY_TOKEN}"
      }
    }
  }
}
```

| 类型 | 配置项 | 说明 |
|------|--------|------|
| Remote HTTP | `url` | MCP 服务器地址 |
| Local stdio | `command` + `args` | 本地命令启动 |
| 认证 | `headers` | 支持环境变量 `${VAR}` |
| 超时 | `toolTimeout` | 工具执行超时（默认 30s）|

## 2 MCP 连接流程

### 2.1 启动时连接

```python
# loop.py
async def run(self) -> None:
    self._running = True
    await self._connect_mcp()  # 连接所有配置的 MCP servers
    
    while self._running:
        msg = await self.bus.consume_inbound()
        ...
```

### 2.2 连接与工具发现

```python
# mcp.py
async def connect_mcp_servers(mcp_configs, registry, exit_stack):
    for server_name, config in mcp_configs.items():
        # 1. 建立连接
        if "url" in config:
            # HTTP transport
            session = await connect_http(config["url"], config.get("headers"))
        else:
            # stdio transport
            session = await connect_stdio(config["command"], config["args"])
        
        # 2. 初始化握手
        await session.initialize()
        
        # 3. 发现工具
        tools = await session.list_tools()
        
        # 4. 包装并注册
        for tool_def in tools:
            wrapper = MCPToolWrapper(session, server_name, tool_def)
            registry.register(wrapper)
            # 工具名: mcp_{server}_{tool}
```

## 3 MCPToolWrapper 实现

MCP 工具被包装成 nanobot 原生工具：

```python
class MCPToolWrapper(Tool):
    def __init__(self, session, server_name: str, tool_def, tool_timeout: int = 30):
        self._session = session
        self._server_name = server_name
        self._original_name = tool_def.name
        self._tool_def = tool_def
        self._timeout = tool_timeout

    @property
    def name(self) -> str:
        # 命名规则: mcp_{server}_{tool}
        return f"mcp_{self._server_name}_{self._original_name}"

    @property
    def description(self) -> str:
        return self._tool_def.description or ""

    @property
    def parameters(self) -> dict:
        return self._tool_def.inputSchema or {"type": "object", "properties": {}}

    async def execute(self, **kwargs) -> str:
        # 调用远程 MCP 工具
        result = await asyncio.wait_for(
            self._session.call_tool(self._original_name, arguments=kwargs),
            timeout=self._timeout
        )
        # 解析返回内容
        return self._parse_result(result)
```

### 3.1 工具命名规则

```
MCP Server: blackjack
Tool Name:  chat
    ↓
Nanobot Tool: mcp_blackjack_chat
```

这样可以：
- 避免与内置工具冲突
- 清晰标识工具来源
- 支持多个 MCP server 同名工具

## 4 内置工具 vs MCP 工具

### 4.1 内置工具定义

```python
# filesystem.py
class ReadFileTool(Tool):
    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Read the contents of a file at the given path."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "The file path to read"}
            },
            "required": ["path"],
        }

    async def execute(self, path: str, **kwargs) -> str:
        file_path = _resolve_path(path, self._workspace)
        return file_path.read_text(encoding="utf-8")
```

### 4.2 对比

| 特性 | 内置工具 | MCP 工具 |
|------|----------|----------|
| 定义位置 | `nanobot/agent/tools/*.py` | 远程 MCP Server |
| 注册时机 | 启动时硬编码 | 启动时动态发现 |
| 命名 | `read_file`, `exec` | `mcp_{server}_{tool}` |
| 执行 | 本地 Python | 远程调用 / stdio |
| 扩展性 | 需改代码 | 配置即可 |

## 5 工具注册与执行流程

### 5.1 完整流程图

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Nanobot 启动                                │
├─────────────────────────────────────────────────────────────────────┤
│  1. _register_default_tools()                                       │
│     → ReadFileTool, WriteFileTool, ExecTool, WebSearchTool...       │
│                                                                     │
│  2. _connect_mcp()                                                  │
│     → 连接 mcpServers 配置的所有服务器                                │
│     → 发现工具，创建 MCPToolWrapper                                   │
│     → 注册到 ToolRegistry                                            │
│                                                                     │
│  3. ToolRegistry._tools = {                                         │
│       "read_file": <ReadFileTool>,                                  │
│       "write_file": <WriteFileTool>,                                │
│       "exec": <ExecTool>,                                           │
│       "mcp_blackjack_chat": <MCPToolWrapper>,  ← MCP 工具            │
│       ...                                                           │
│     }                                                               │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         用户发送消息                                 │
├─────────────────────────────────────────────────────────────────────┤
│  1. 构建 messages (system prompt + history + user message)          │
│                                                                     │
│  2. 调用 LLM:                                                       │
│     response = await provider.chat(                                 │
│         messages=messages,                                          │
│         tools=registry.get_definitions(),  ← 所有工具的 JSON Schema  │
│     )                                                               │
│                                                                     │
│  3. LLM 返回 tool_calls:                                            │
│     [{"name": "mcp_blackjack_chat", "arguments": {"prompt": "..."}}]│
│                                                                     │
│  4. 执行工具:                                                        │
│     result = await registry.execute("mcp_blackjack_chat", args)     │
│         → MCPToolWrapper.execute()                                  │
│         → session.call_tool("chat", arguments)                      │
│         → HTTP POST to blackjack.nanobot.ai/mcp                     │
│         ← 返回结果                                                   │
│                                                                     │
│  5. 将结果加入 messages，循环回到步骤 2                               │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.2 工具 Schema 格式

发送给 LLM 的工具定义：

```json
{
  "type": "function",
  "function": {
    "name": "mcp_blackjack_chat",
    "description": "Blackjack dealer with 40 years of experience...",
    "parameters": {
      "type": "object",
      "properties": {
        "prompt": {
          "type": "string",
          "description": "The input prompt"
        }
      },
      "required": ["prompt"]
    }
  }
}
```

## 6 实战：Blackjack MCP

### 6.1 配置

```json
"mcpServers": {
  "blackjack": {
    "url": "https://blackjack.nanobot.ai/mcp"
  }
}
```

### 6.2 使用

```
User: Let's play blackjack!

Agent: (调用 mcp_blackjack_chat)
       → HTTP POST to blackjack.nanobot.ai/mcp
       ← 返回游戏状态

Agent: 🃏 Your Hand: A♠ 8♥ = Soft 19
       Dealer Shows: A♥
       What would you like to do?
```

### 6.3 工具存储位置

| 问题 | 答案 |
|------|------|
| 工具定义存在哪？ | 内存中 `ToolRegistry._tools` |
| 持久化到磁盘吗？ | 否，每次启动重新发现 |
| 配置在哪？ | `~/.nanobot/config.json` |
| 如何查看日志？ | `nanobot agent --logs` |

## 7 常用 MCP Servers

| Server | 类型 | 用途 |
|--------|------|------|
| `@modelcontextprotocol/server-filesystem` | stdio | 文件系统访问 |
| `@modelcontextprotocol/server-github` | stdio | GitHub API |
| `@modelcontextprotocol/server-postgres` | stdio | PostgreSQL 查询 |
| `@modelcontextprotocol/server-brave-search` | stdio | Brave 搜索 |
| `blackjack.nanobot.ai/mcp` | HTTP | 21点游戏 Demo |

## 8 Key Takeaways

1. **Nanobot 是 MCP Host** — 内置 MCP Client，可连接任意 MCP Server
2. **动态发现** — 启动时自动发现并注册 MCP 工具
3. **统一接口** — MCP 工具和内置工具对 LLM 透明，都是 function calling
4. **命名规则** — `mcp_{server}_{tool}` 避免冲突
5. **配置简单** — 只需在 config.json 添加 URL 或命令
6. **内存存储** — 工具注册在内存，不持久化

MCP 让 nanobot 从一个固定能力的 agent 变成了**可无限扩展的 agent 平台**。
